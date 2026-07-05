"""Policy filtering for minute_target_scope dry-run rows."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any, Mapping


DEFAULT_MIN_TOTAL_MV_WAN = Decimal("1000000")
DEFAULT_INDEX_CODES = ("000905", "399303", "000001", "000852", "399001", "399006", "000300", "000016", "000688")
POLICY_DOMAINS = ("index", "board", "stock")


def default_scope_policy() -> dict[str, Any]:
    return {
        "policy_name": "default_scope_policy",
        "index": {
            "enabled": True,
            "source": "condition_pool",
            "include_codes": list(DEFAULT_INDEX_CODES),
            "directions": ["buy", "sell"],
        },
        "board": {
            "enabled": True,
            "source": "condition_pool",
            "board_types": ["tdx_industry"],
            "board_code_prefix": "",
            "board_code_prefixes": [],
            "directions": ["buy", "sell"],
        },
        "stock": {
            "enabled": True,
            "source": "condition_pool",
            "directions": ["buy", "sell"],
            "include_condition_families": ["ordinary", "full", "hint"],
            "include_condition_keys": [],
            "min_total_mv_wan": str(DEFAULT_MIN_TOTAL_MV_WAN),
            "market_value_compare": ">=",
            "require_buy_target_price": False,
            "require_sell_target_price": False,
            "require_up_sell_reference_period": False,
            "require_down_buy_reference_period": False,
            "require_clear_sell_ref_period": False,
            "exclude_bj": False,
            "limit": None,
        },
    }


def load_scope_policy(path: str | Path) -> dict[str, Any]:
    policy_path = Path(path)
    payload = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("scope policy JSON must be an object")
    return normalize_scope_policy(payload)


def normalize_scope_policy(policy: Mapping[str, Any] | None) -> dict[str, Any]:
    merged = default_scope_policy()
    if policy:
        merged.update({key: deepcopy(value) for key, value in policy.items() if key not in POLICY_DOMAINS})
        for domain in POLICY_DOMAINS:
            if domain in policy:
                section = policy[domain]
                if not isinstance(section, Mapping):
                    raise ValueError(f"scope policy section must be an object: {domain}")
                merged[domain].update(deepcopy(dict(section)))
    validate_scope_policy(merged)
    return merged


def validate_scope_policy(policy: Mapping[str, Any]) -> None:
    for domain in POLICY_DOMAINS:
        if domain not in policy:
            raise ValueError(f"scope policy missing section: {domain}")
    stock_policy = policy["stock"]
    min_total_mv = decimal_or_none(stock_policy.get("min_total_mv_wan"))
    if min_total_mv is not None and min_total_mv < DEFAULT_MIN_TOTAL_MV_WAN:
        raise ValueError("stock.min_total_mv_wan cannot be below 1000000")
    if stock_policy.get("market_value_compare", ">=") not in {">=", ">"}:
        raise ValueError("stock.market_value_compare must be >= or >")
    limit = stock_policy.get("limit")
    if limit is not None and (not isinstance(limit, int) or limit < 0):
        raise ValueError("stock.limit must be a non-negative integer or null")


def filter_scope_rows(
    domain: str,
    rows: list[Mapping[str, Any]],
    policy: Mapping[str, Any],
    *,
    sample_size: int = 6,
) -> dict[str, Any]:
    selected_rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, Any]] = []
    excluded_samples: list[dict[str, Any]] = []
    excluded_reason_counts: dict[str, int] = {}
    for row in rows:
        reasons = exclusion_reasons(domain, row, policy)
        if reasons:
            row_copy = dict(row)
            excluded_rows.append(row_copy)
            for reason in reasons:
                excluded_reason_counts[reason] = excluded_reason_counts.get(reason, 0) + 1
            if len(excluded_samples) < sample_size:
                excluded_samples.append({"reasons": reasons, "row": compact_scope_row(row_copy)})
        else:
            selected_rows.append(dict(row))

    limit = policy.get("limit")
    if isinstance(limit, int) and limit >= 0 and len(selected_rows) > limit:
        over_limit = selected_rows[limit:]
        selected_rows = selected_rows[:limit]
        excluded_reason_counts["limit"] = excluded_reason_counts.get("limit", 0) + len(over_limit)
        excluded_rows.extend(over_limit)
        for row in over_limit:
            if len(excluded_samples) < sample_size:
                excluded_samples.append({"reasons": ["limit"], "row": compact_scope_row(row)})

    return {
        "selected_rows": selected_rows,
        "excluded_rows": excluded_rows,
        "candidate_count": len(rows),
        "selected_count": len(selected_rows),
        "excluded_count": len(rows) - len(selected_rows),
        "excluded_reason_counts": dict(sorted(excluded_reason_counts.items())),
        "selected_samples": [compact_scope_row(row) for row in selected_rows[:sample_size]],
        "excluded_samples": excluded_samples,
    }


def scope_policy_warnings(policy: Mapping[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    stock_policy = policy.get("stock", {})
    if normalize_str_set(stock_policy.get("include_condition_keys")) and normalize_str_set(stock_policy.get("include_condition_families")):
        warnings.append(
            {
                "severity": "P2",
                "code": "stock_condition_key_overrides_family",
                "message": "stock.include_condition_keys and include_condition_families are both set; include_condition_keys takes precedence.",
            }
        )
    return warnings


def compact_scope_row(row: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "identity_key",
        "code",
        "board_code",
        "name",
        "board_name",
        "direction",
        "condition_key",
        "lane",
        "total_mv",
        "preferred_board_code",
        "recommendation_level",
        "scope_source",
        "market_data_consumer",
        "previous_day_minute_date",
    )
    return {key: row.get(key) for key in keys if key in row and row.get(key) not in (None, "")}


def exclusion_reasons(domain: str, row: Mapping[str, Any], policy: Mapping[str, Any]) -> list[str]:
    if not bool(policy.get("enabled", True)):
        return ["policy_disabled"]

    reasons: list[str] = []
    if directions := normalize_str_set(policy.get("directions")):
        if str(row.get("direction") or "") not in directions:
            reasons.append("direction")

    if domain == "index":
        reasons.extend(index_exclusion_reasons(row, policy))
    elif domain == "board":
        reasons.extend(board_exclusion_reasons(row, policy))
    elif domain == "stock":
        reasons.extend(stock_exclusion_reasons(row, policy))
    else:
        reasons.append("unsupported_domain")

    reasons.extend(common_field_exclusion_reasons(row, policy))
    return reasons


def index_exclusion_reasons(row: Mapping[str, Any], policy: Mapping[str, Any]) -> list[str]:
    code = str(row.get("code") or "")
    identity_key = str(row.get("identity_key") or row.get("index_identity_key") or "")
    condition_key = str(row.get("condition_key") or "")
    reasons: list[str] = []
    if families := normalize_str_set(policy.get("include_condition_families")):
        if condition_family(condition_key) not in families:
            reasons.append("include_condition_families")
    if include_identity_keys := normalize_str_set(policy.get("include_identity_keys") or policy.get("enabled_identities")):
        if identity_key not in include_identity_keys:
            reasons.append("include_identity_keys")
    if exclude_identity_keys := normalize_str_set(policy.get("exclude_identity_keys")):
        if identity_key in exclude_identity_keys:
            reasons.append("exclude_identity_keys")
    if include_codes := normalize_str_set(policy.get("include_codes")):
        if code not in include_codes:
            reasons.append("include_codes")
    if exclude_codes := normalize_str_set(policy.get("exclude_codes")):
        if code in exclude_codes:
            reasons.append("exclude_codes")
    if include_keys := normalize_str_set(policy.get("include_condition_keys")):
        if condition_key not in include_keys:
            reasons.append("include_condition_keys")
    return reasons


def board_exclusion_reasons(row: Mapping[str, Any], policy: Mapping[str, Any]) -> list[str]:
    code = str(row.get("board_code") or row.get("code") or "")
    board_type = str(row.get("board_type") or "")
    condition_key = str(row.get("condition_key") or "")
    reasons: list[str] = []
    if families := normalize_str_set(policy.get("include_condition_families")):
        if condition_family(condition_key) not in families:
            reasons.append("include_condition_families")
    board_types = normalize_str_set(policy.get("board_types"))
    if board_types:
        if board_type not in board_types:
            reasons.append("board_type")
    else:
        prefixes = list(normalize_str_set(policy.get("board_code_prefixes")))
        if not prefixes and policy.get("board_code_prefix"):
            prefixes = [str(policy.get("board_code_prefix"))]
        if prefixes and not any(code.startswith(prefix) for prefix in prefixes):
            reasons.append("board_code_prefix")
    if include_codes := normalize_str_set(policy.get("include_board_codes") or policy.get("include_codes")):
        if code not in include_codes:
            reasons.append("include_board_codes")
    if exclude_codes := normalize_str_set(policy.get("exclude_board_codes") or policy.get("exclude_codes")):
        if code in exclude_codes:
            reasons.append("exclude_board_codes")
    if include_keys := normalize_str_set(policy.get("include_condition_keys")):
        if condition_key not in include_keys:
            reasons.append("include_condition_keys")
    return reasons


def stock_exclusion_reasons(row: Mapping[str, Any], policy: Mapping[str, Any]) -> list[str]:
    code = str(row.get("code") or "")
    condition_key = str(row.get("condition_key") or "")
    reasons: list[str] = []
    if include_codes := normalize_str_set(policy.get("include_codes")):
        if code not in include_codes:
            reasons.append("include_codes")
    if exclude_codes := normalize_str_set(policy.get("exclude_codes")):
        if code in exclude_codes:
            reasons.append("exclude_codes")
    if lanes := normalize_str_set(policy.get("lanes") or policy.get("lane")):
        if str(row.get("lane") or "") not in lanes:
            reasons.append("lane")
    if include_keys := normalize_str_set(policy.get("include_condition_keys")):
        if condition_key not in include_keys:
            reasons.append("include_condition_keys")
    elif families := normalize_str_set(policy.get("include_condition_families")):
        if condition_family(condition_key) not in families:
            reasons.append("include_condition_families")
    min_total_mv = decimal_or_none(policy.get("min_total_mv_wan"))
    if min_total_mv is not None and not market_value_passes(
        row.get("total_mv"),
        min_total_mv,
        str(policy.get("market_value_compare") or ">="),
    ):
        reasons.append("min_total_mv_wan")
    max_total_mv = decimal_or_none(policy.get("max_total_mv_wan"))
    if max_total_mv is not None and not market_value_at_most(row.get("total_mv"), max_total_mv):
        reasons.append("max_total_mv_wan")
    min_score = decimal_or_none(policy.get("min_score"))
    if min_score is not None and not score_passes(row.get("score"), min_score):
        reasons.append("min_score")
    if normalize_bool(policy.get("exclude_st")) and (
        normalize_bool(row.get("is_st")) or "ST" in str(row.get("name") or "").upper() or "退" in str(row.get("name") or "")
    ):
        reasons.append("st_or_risk_stock")
    if normalize_bool(policy.get("require_official_daily_proof")) and not normalize_bool(row.get("official_daily_proof")):
        reasons.append("official_daily_missing")
    if normalize_bool(policy.get("require_financial_quality_passed")) and str(row.get("financial_quality_status") or "") != "passed":
        reasons.append("financial_quality_not_passed")
    if normalize_bool(policy.get("exclude_bj")) and is_bj_stock(row):
        reasons.append("bj_stock")
    if normalize_bool(policy.get("require_buy_target_price")) and row.get("direction") == "buy" and not row.get("buy_target_price"):
        reasons.append("require_buy_target_price")
    if normalize_bool(policy.get("require_sell_target_price")) and row.get("direction") == "sell" and not row.get("sell_target_price"):
        reasons.append("require_sell_target_price")
    if normalize_bool(policy.get("require_up_sell_reference_period")) and not row.get("up_sell_reference_period"):
        reasons.append("require_up_sell_reference_period")
    if normalize_bool(policy.get("require_down_buy_reference_period")) and not row.get("down_buy_reference_period"):
        reasons.append("require_down_buy_reference_period")
    if normalize_bool(policy.get("require_clear_sell_ref_period")) and not row.get("clear_sell_ref_period"):
        reasons.append("require_clear_sell_ref_period")
    return reasons


def common_field_exclusion_reasons(row: Mapping[str, Any], policy: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field_name in (
        "period_grade_y",
        "period_grade_q",
        "period_grade_m",
        "period_grade_w",
        "period_grade_d",
        "period_transition_y",
        "period_transition_q",
        "period_transition_m",
        "period_transition_w",
        "period_transition_d",
        "main_up_anchor",
        "main_down_anchor",
        "prev_up_str",
        "prev_dn_str",
    ):
        allowed_values = normalize_str_set(policy.get(field_name))
        if allowed_values and str(row.get(field_name) or "") not in allowed_values:
            reasons.append(field_name)
    recommendation_levels = normalize_str_set(policy.get("recommendation_levels") or policy.get("recommendation_level"))
    if recommendation_levels and str(row.get("recommendation_level") or "") not in recommendation_levels:
        reasons.append("recommendation_level")
    return reasons


def condition_family(condition_key: str) -> str:
    if condition_key in {"BUY_HINT", "SELL_HINT"}:
        return "hint"
    if condition_key in {"BUY:FULL", "SELL:FULL"}:
        return "full"
    if (condition_key.startswith("BUY:") or condition_key.startswith("SELL:")) and ":" in condition_key:
        return "ordinary"
    return "scope"


def market_value_passes(total_mv: Any, threshold: Decimal, operator: str) -> bool:
    value = decimal_or_none(total_mv)
    if value is None:
        return False
    if operator == ">":
        return value > threshold
    return value >= threshold


def market_value_at_most(total_mv: Any, threshold: Decimal) -> bool:
    value = decimal_or_none(total_mv)
    return value is not None and value <= threshold


def score_passes(score: Any, threshold: Decimal) -> bool:
    value = decimal_or_none(score)
    return value is not None and value >= threshold


def decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def is_bj_stock(row: Mapping[str, Any]) -> bool:
    identity_key = str(row.get("identity_key") or row.get("stock_identity_key") or "").upper()
    exchange = str(row.get("exchange") or "").upper()
    code = str(row.get("code") or "").upper()
    return exchange == "BJ" or ":BJ:" in identity_key or identity_key.endswith(":BJ") or code.endswith(".BJ") or code.endswith("BJ")


def normalize_str_set(value: Any) -> set[str]:
    if value in (None, "", []):
        return set()
    if isinstance(value, str):
        return {value}
    return {str(item) for item in value}
