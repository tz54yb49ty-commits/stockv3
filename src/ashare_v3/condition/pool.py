"""Read-only condition_pool dry-run builder."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any, Iterable, Mapping

from ashare_v3.condition.basis import (
    DEFAULT_INDEX_POOL_IDENTITIES,
    PERIODS,
    SYMMETRY_TARGET_FIELDS,
    STOCK_FINANCIAL_PASS_THROUGH_FIELDS,
    STANDARD_SIGNAL_TYPES,
    build_condition_basis_dry_run,
    canonical_target_fields_for_direction,
    count_quality_severities,
    normalize_mapping,
    period_trigger_baseline_has_required_shape,
    period_trigger_baseline_not_ready_periods,
    quality_item,
)
from ashare_v3.ingestion.common import require_yyyymmdd


BUY_POOL_SIGNAL_TYPES = ("BUY",)
SELL_POOL_SIGNAL_TYPES = ("SELL",)
BUY_FULL_POOL_SIGNAL_TYPES = ("BUY:FULL",)
SELL_FULL_POOL_SIGNAL_TYPES = ("SELL:FULL",)
HINT_POOL_SIGNAL_TYPES = ("BUY_HINT", "SELL_HINT")
MINUTE_POOL_SIGNAL_TYPES = frozenset({"BUY_HINT", "SELL_HINT"})
ORDINARY_CONDITION_GROUPS = ("BUY:*", "SELL:*")
FULL_CONDITION_KEYS = ("BUY:FULL", "SELL:FULL")
HINT_CONDITION_KEYS = ("BUY_HINT", "SELL_HINT")
SUPPORTED_CONDITION_GROUPS = ORDINARY_CONDITION_GROUPS + FULL_CONDITION_KEYS + HINT_CONDITION_KEYS
DEFAULT_INDEX_POOL_CODES = ("000905", "399303", "000001", "000852", "399001", "399006", "000300", "000016", "000688")
DEFAULT_STOCK_MIN_TOTAL_MV_WAN = Decimal("0")


def build_condition_pool_dry_run(
    *,
    dsn: str,
    source_trade_date: str,
    ready_check: Mapping[str, Any],
    condition_pool_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    basis_report = build_condition_basis_dry_run(
        dsn=dsn,
        source_trade_date=source_trade_date,
        ready_check=ready_check,
    )
    pool_preview = build_condition_pool_preview_from_basis_report(
        basis_report,
        condition_pool_policy=condition_pool_policy,
    )
    quality_items = build_condition_pool_quality_items(
        basis_report=basis_report,
        pool_preview=pool_preview,
    )
    severity_counts = count_quality_severities(quality_items)
    return {
        "stage": "N2-C",
        "mode": "dry_run",
        "writes_performed": False,
        "condition_pool_written": False,
        "minute_kline_pulled": False,
        "run_id": f"condition_pool_{basis_report['source_trade_date']}_to_{basis_report['for_trade_date']}_dry_run",
        "basis_run_id": basis_report["run_id"],
        "source_trade_date": basis_report["source_trade_date"],
        "for_trade_date": basis_report["for_trade_date"],
        "prev_trade_date": basis_report["prev_trade_date"],
        "for_trade_calendar_row_exists": basis_report["for_trade_calendar_row_exists"],
        "calendar_detail": calendar_detail_from_basis_report(basis_report),
        "source_versions": basis_report["source_versions"],
        "source_ready_passed": bool(basis_report["source_ready_passed"]),
        "basis_source": {
            "mode": "basis_dry_run_preview",
            "persisted_condition_basis_read": False,
            "source_condition_basis_ids_available": False,
            "basis_total_rows": {
                "stock": basis_report["basis_preview"]["stock"]["row_count"],
                "index": basis_report["basis_preview"]["index"]["row_count"],
                "board": basis_report["basis_preview"]["board"]["row_count"],
            },
            "basis_preview_rows": {
                domain: pool_preview[domain]["basis_preview_row_count"]
                for domain in ("stock", "index", "board")
            },
        },
        "supported_condition_groups": list(SUPPORTED_CONDITION_GROUPS),
        "allowed_signal_type_whitelist": list(STANDARD_SIGNAL_TYPES),
        "pool_preview": pool_preview,
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "passed": severity_counts["P0"] == 0 and bool(basis_report["source_ready_passed"]),
    }


def calendar_detail_from_basis_report(basis_report: Mapping[str, Any]) -> dict[str, Any]:
    row_exists = bool(basis_report.get("for_trade_calendar_row_exists"))
    detail = {
        "for_trade_date": basis_report.get("for_trade_date"),
        "prev_trade_date": basis_report.get("prev_trade_date"),
        "row_exists": row_exists,
        "checked_readonly": True,
    }
    if not row_exists:
        detail.update(
            {
                "repair_owner": "ingestion_layer",
                "repair_suggestion": (
                    "补齐 common_trade_calendar 的 for_trade_date 详情行，条件层不得硬造交易日；"
                    "补齐后再重跑 N2-C dry-run。"
                ),
            }
        )
    return detail


def build_condition_pool_preview_from_basis_report(
    basis_report: Mapping[str, Any],
    *,
    condition_pool_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    preview: dict[str, Any] = {}
    for domain in ("stock", "index", "board"):
        basis_rows = list(
            basis_report["basis_preview"][domain].get("basis_rows")
            or basis_report["basis_preview"][domain].get("sample_basis_rows")
            or []
        )
        candidate_pool_rows = [
            pool_row
            for basis_index, basis_row in enumerate(basis_rows, start=1)
            for pool_row in build_pool_rows_for_basis(domain, basis_row, basis_index)
        ]
        policy = condition_pool_policy_for_domain(domain, condition_pool_policy)
        policy_hash = condition_pool_policy_hash(policy)
        policy_result = apply_default_condition_pool_policy(domain, candidate_pool_rows, policy=policy)
        pool_rows = policy_result["selected_rows"]
        preview[domain] = {
            "basis_preview_row_count": len(basis_rows),
            "candidate_pool_row_count": len(candidate_pool_rows),
            "pool_row_count": len(pool_rows),
            "candidate_object_count": len({row.get("identity_key") for row in candidate_pool_rows if row.get("identity_key")}),
            "object_count": len({row.get("identity_key") for row in pool_rows if row.get("identity_key")}),
            "condition_pool_selection_policy": policy,
            "condition_pool_selection_policy_hash": policy_hash,
            "policy_selected_count": policy_result["selected_count"],
            "policy_excluded_count": policy_result["excluded_count"],
            "policy_excluded_reason_counts": policy_result["excluded_reason_counts"],
            "policy_selected_reason_counts": policy_result["selected_reason_counts"],
            "policy_excluded_samples": policy_result["excluded_samples"],
            "policy_selected_samples": policy_result["selected_samples"],
            "condition_key_counts": dict(sorted(Counter(str(row["condition_key"]) for row in pool_rows).items())),
            "condition_group_counts": dict(sorted(Counter(condition_group_for_key(str(row["condition_key"])) for row in pool_rows).items())),
            "direction_counts": dict(sorted(Counter(str(row["direction"]) for row in pool_rows).items())),
            "allowed_signal_type_counts": dict(sorted(count_allowed_signal_types(pool_rows).items())),
            "pool_rows": pool_rows,
            "sample_pool_rows": pool_rows[:6],
        }
    return preview


def default_condition_pool_policy(domain: str) -> dict[str, Any]:
    if domain == "index":
        return {
            "policy_name": "default_condition_pool_policy",
            "policy_version": "N2-E5",
            "source": "condition_pool_candidate",
            "include_all_identities": True,
            "include_codes": [],
            "include_identity_keys": [],
            "directions": ["buy", "sell"],
            "allowed_lanes": ["market_alert"],
            "allowed_monitor_types": ["source_universe_preview"],
        }
    if domain == "board":
        return {
            "policy_name": "default_condition_pool_policy",
            "policy_version": "N2-E5",
            "source": "condition_pool_candidate",
            "board_types": ["tdx_industry", "tdx_concept", "tdx_region"],
            "board_code_prefix": "",
            "directions": ["buy", "sell"],
            "allowed_lanes": ["market_alert"],
            "allowed_monitor_types": ["source_universe_preview"],
        }
    if domain == "stock":
        return {
            "policy_name": "default_condition_pool_policy",
            "policy_version": "N2-E5",
            "source": "condition_pool_candidate",
            "directions": ["buy", "sell"],
            "include_condition_families": ["ordinary", "full", "hint"],
            "min_total_mv_wan": None,
            "market_value_compare": ">=",
            "exclude_st_or_risk_name": False,
            "allowed_stock_statuses": [],
            "require_official_daily_proof": False,
            "require_financial_snapshot": False,
            "require_financial_key_field": False,
            "blocked_financial_quality_statuses": [],
            "allowed_lanes": ["stock_alert", "stock_trade"],
            "allowed_monitor_types": ["source_universe_preview"],
        }
    raise ValueError(f"unsupported condition_pool domain: {domain!r}")


def condition_pool_policy_for_domain(domain: str, condition_pool_policy: Mapping[str, Any] | None) -> dict[str, Any]:
    policy = default_condition_pool_policy(domain)
    if not condition_pool_policy:
        return policy
    custom = condition_pool_policy.get(domain)
    if not isinstance(custom, Mapping):
        return policy
    merged = {**policy, **dict(custom)}
    return merged


def condition_pool_policy_hash(policy: Mapping[str, Any]) -> str:
    payload = json.dumps(policy, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def allowed_index_identity_keys_from_policy(policy: Mapping[str, Any]) -> set[str] | None:
    if bool(policy.get("include_all_identities")):
        return None
    return {str(item) for item in policy.get("include_identity_keys") or DEFAULT_INDEX_POOL_IDENTITIES}


def allowed_board_types_from_policy(policy: Mapping[str, Any]) -> set[str]:
    return {str(item) for item in policy.get("board_types") or []} or {
        "tdx_industry",
        "tdx_concept",
        "tdx_region",
    }


def apply_default_condition_pool_policy(
    domain: str,
    rows: list[Mapping[str, Any]],
    *,
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    policy = dict(policy or default_condition_pool_policy(domain))
    policy_name = str(policy.get("policy_name") or "default_condition_pool_policy")
    policy_hash = condition_pool_policy_hash(policy)
    selected_rows: list[dict[str, Any]] = []
    excluded_samples: list[dict[str, Any]] = []
    selected_samples: list[dict[str, Any]] = []
    excluded_reason_counts: Counter[str] = Counter()
    selected_reason_counts: Counter[str] = Counter()
    for row in rows:
        excluded_reasons = default_condition_pool_exclusion_reasons(domain, row, policy=policy)
        if excluded_reasons:
            for reason in excluded_reasons:
                excluded_reason_counts[reason] += 1
            if len(excluded_samples) < 6:
                excluded_samples.append(
                    {
                        "policy_name": policy_name,
                        "policy_hash": policy_hash,
                        "excluded_reason": excluded_reasons,
                        "row": compact_pool_row(row),
                    }
                )
        else:
            selected_reasons = default_condition_pool_selected_reasons(domain, row, policy=policy)
            for reason in selected_reasons:
                selected_reason_counts[reason] += 1
            selected_row = pool_row_with_policy_metadata(
                row,
                policy_name=policy_name,
                policy_hash=policy_hash,
                selected_reason=selected_reasons,
                excluded_reason=[],
            )
            selected_rows.append(selected_row)
            if len(selected_samples) < 6:
                selected_samples.append(compact_pool_row(selected_row))
    return {
        "selected_rows": selected_rows,
        "selected_count": len(selected_rows),
        "excluded_count": len(rows) - len(selected_rows),
        "selected_reason_counts": dict(sorted(selected_reason_counts.items())),
        "excluded_reason_counts": dict(sorted(excluded_reason_counts.items())),
        "selected_samples": selected_samples,
        "excluded_samples": excluded_samples,
    }


def default_condition_pool_exclusion_reasons(
    domain: str,
    row: Mapping[str, Any],
    *,
    policy: Mapping[str, Any] | None = None,
) -> list[str]:
    policy = policy or default_condition_pool_policy(domain)
    reasons: list[str] = []
    directions = set(str(item) for item in policy.get("directions") or ["buy", "sell"])
    if row.get("direction") not in directions:
        reasons.append("direction")
    if not field_in_allowlist(row.get("lane"), policy.get("allowed_lanes")):
        reasons.append("lane")
    if not field_in_allowlist(row.get("monitor_type"), policy.get("allowed_monitor_types")):
        reasons.append("monitor_type")
    if domain == "index":
        if not bool(policy.get("include_all_identities")):
            identity_allowlist = allowed_index_identity_keys_from_policy(policy) or set()
            if str(row.get("identity_key") or "") not in identity_allowlist:
                reasons.append("index_identity_not_in_default_universe")
            elif str(row.get("code") or "") not in set(str(item) for item in policy.get("include_codes") or DEFAULT_INDEX_POOL_CODES):
                reasons.append("index_code_not_in_default_universe")
    elif domain == "board":
        board_types = allowed_board_types_from_policy(policy)
        if board_types:
            if str(row.get("board_type") or "") not in board_types:
                reasons.append("board_type")
        else:
            prefix = str(policy.get("board_code_prefix") or "881")
            if not str(row.get("board_code") or "").startswith(prefix):
                reasons.append("board_code_prefix")
    elif domain == "stock":
        if condition_group_for_key(str(row.get("condition_key") or "")) not in {"ordinary_buy", "ordinary_sell", "full", "hint"}:
            reasons.append("condition_family")
        total_mv = decimal_or_none(row.get("total_mv"))
        min_total_mv = decimal_or_none(policy.get("min_total_mv_wan"))
        if min_total_mv is not None:
            if total_mv is None:
                reasons.append("missing_total_mv")
            elif total_mv < min_total_mv:
                reasons.append("min_total_mv_wan")
        if bool(policy.get("exclude_st_or_risk_name")) and is_st_or_risk_stock(row):
            reasons.append("st_or_risk_stock")
        if not field_in_allowlist(row.get("stock_status"), policy.get("allowed_stock_statuses")):
            reasons.append("stock_status")
        if bool(policy.get("require_official_daily_proof")) and not normalize_bool(row.get("official_daily_proof")):
            reasons.append("official_daily_missing")
        financial_quality_status = str(row.get("financial_quality_status") or "")
        if financial_quality_status in set(str(item) for item in policy.get("blocked_financial_quality_statuses") or []):
            reasons.append("financial_quality_failed")
        if bool(policy.get("require_financial_snapshot")) and row.get("financial_asof_date") in (None, ""):
            reasons.append("financial_snapshot_missing")
        if bool(policy.get("require_financial_key_field")) and row.get("pe_core") in (None, "") and row.get("score") in (None, ""):
            reasons.append("financial_key_fields_missing")
    else:
        reasons.append("unsupported_domain")
    if missing_required_period_trigger_baseline_periods(row):
        reasons.append("missing_period_trigger_baseline")
    return reasons


def default_condition_pool_selected_reasons(
    domain: str,
    row: Mapping[str, Any],
    *,
    policy: Mapping[str, Any] | None = None,
) -> list[str]:
    policy = policy or default_condition_pool_policy(domain)
    reasons = ["condition_candidate_eligible", "default_policy_matched"]
    if domain == "index":
        if bool(policy.get("include_all_identities")):
            reasons.append("all_index_universe")
        else:
            reasons.append("fixed_index_universe")
    elif domain == "board":
        board_type = str(row.get("board_type") or "")
        reasons.append(f"board_type_{board_type}" if board_type else "board_type_matched")
    elif domain == "stock":
        if decimal_or_none(policy.get("min_total_mv_wan")) is not None:
            reasons.append("market_value_passed")
        else:
            reasons.append("all_stock_universe")
        if bool(policy.get("exclude_st_or_risk_name")):
            reasons.append("non_st_risk")
        if bool(policy.get("require_official_daily_proof")):
            reasons.append("official_daily_proof")
        if bool(policy.get("require_financial_snapshot")):
            reasons.append("financial_snapshot_available")
    return reasons


def pool_row_with_policy_metadata(
    row: Mapping[str, Any],
    *,
    policy_name: str,
    policy_hash: str,
    selected_reason: list[str],
    excluded_reason: list[str],
) -> dict[str, Any]:
    output = dict(row)
    output["policy_name"] = policy_name
    output["policy_hash"] = policy_hash
    output["selected_reason"] = list(selected_reason)
    output["excluded_reason"] = list(excluded_reason)
    output["quality_reason"] = "selected by default_condition_pool_policy; source condition_basis is not persisted"
    raw_json = normalize_mapping(output.get("raw_json") or {})
    raw_json["condition_pool_selection"] = {
        "policy_name": policy_name,
        "policy_hash": policy_hash,
        "selected_reason": list(selected_reason),
        "excluded_reason": list(excluded_reason),
    }
    output["raw_json"] = raw_json
    return output


def field_in_allowlist(value: Any, allowed_values: Any) -> bool:
    if not allowed_values:
        return True
    return str(value or "") in {str(item) for item in allowed_values}


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (1, "1"):
        return True
    if value in (0, "0", None, ""):
        return False
    return str(value).strip().lower() in {"true", "t", "yes", "y"}


def is_st_or_risk_stock(row: Mapping[str, Any]) -> bool:
    if normalize_bool(row.get("is_st")):
        return True
    name = str(row.get("name") or "")
    upper_name = name.upper()
    return any(marker in upper_name for marker in ("ST", "*ST")) or "退" in name


def compact_pool_row(row: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "identity_key",
        "code",
        "board_code",
        "name",
        "board_name",
        "direction",
        "condition_key",
        "required_periods",
        "missing_period_trigger_baseline_periods",
        "total_mv",
        "is_st",
        "stock_status",
        "official_daily_proof",
        "financial_asof_date",
        "financial_quality_status",
        "lane",
        "monitor_type",
        "policy_name",
        "policy_hash",
        "selected_reason",
        "source_condition_basis_ref",
    )
    return {key: row.get(key) for key in keys if row.get(key) not in (None, "")}


def build_pool_rows_for_basis(domain: str, basis_row: Mapping[str, Any], basis_index: int = 1) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    buy_periods = normalize_periods(basis_row.get("buy_necessary_periods"))
    sell_periods = normalize_periods(basis_row.get("sell_necessary_periods"))
    if bool(basis_row.get("buy_necessary_base")) and buy_periods:
        rows.append(make_pool_row(domain, basis_row, "buy", f"BUY:{','.join(buy_periods)}", buy_periods, list(BUY_POOL_SIGNAL_TYPES), basis_index))
    if bool(basis_row.get("sell_necessary_base")) and sell_periods:
        rows.append(make_pool_row(domain, basis_row, "sell", f"SELL:{','.join(sell_periods)}", sell_periods, list(SELL_POOL_SIGNAL_TYPES), basis_index))
    if bool(basis_row.get("buy_full_necessary_base")):
        rows.append(make_pool_row(domain, basis_row, "buy", "BUY:FULL", ["D"], list(BUY_FULL_POOL_SIGNAL_TYPES), basis_index))
    if bool(basis_row.get("sell_full_necessary_base")):
        rows.append(make_pool_row(domain, basis_row, "sell", "SELL:FULL", ["D"], list(SELL_FULL_POOL_SIGNAL_TYPES), basis_index))
    if bool(basis_row.get("oversold_hint_necessary_base")):
        rows.append(make_pool_row(domain, basis_row, "buy", "BUY_HINT", [], ["BUY_HINT"], basis_index))
    if bool(basis_row.get("overbought_hint_necessary_base")):
        rows.append(make_pool_row(domain, basis_row, "sell", "SELL_HINT", [], ["SELL_HINT"], basis_index))
    return rows


def required_periods_for_condition_key(condition_key: str) -> list[str]:
    if condition_key in HINT_CONDITION_KEYS:
        return []
    if condition_key in FULL_CONDITION_KEYS:
        return ["D"]
    if condition_key.startswith("BUY:") or condition_key.startswith("SELL:"):
        _, _, period_text = condition_key.partition(":")
        return normalize_periods(period_text)
    return []


def missing_required_period_trigger_baseline_periods(row: Mapping[str, Any]) -> list[str]:
    required_periods = row.get("required_periods")
    if required_periods in (None, ""):
        required_periods = required_periods_for_condition_key(str(row.get("condition_key") or ""))
    return period_trigger_baseline_not_ready_periods(row.get("period_trigger_baseline_json"), required_periods)


def make_pool_row(
    domain: str,
    basis_row: Mapping[str, Any],
    direction: str,
    condition_key: str,
    condition_periods: list[str],
    allowed_signal_types: list[str],
    basis_index: int,
) -> dict[str, Any]:
    identity_key = identity_key_for_domain(domain, basis_row)
    minute_required = minute_required_for_signal_types(allowed_signal_types)
    required_periods = required_periods_for_condition_key(condition_key)
    base = {
        "for_trade_date": basis_row.get("for_trade_date"),
        "source_trade_date": basis_row.get("source_trade_date"),
        "prev_trade_date": basis_row.get("prev_trade_date"),
        "identity_key": identity_key,
        "asset_kind": domain,
        "lane": basis_row.get("lane"),
        "direction": direction,
        "condition_key": condition_key,
        "condition_periods": condition_periods,
        "required_periods": required_periods,
        "allowed_signal_types": allowed_signal_types,
        "is_hint_scope": condition_key in HINT_CONDITION_KEYS,
        "daily_snapshot_required": True,
        "minute_required": minute_required,
        "previous_day_minute_required": minute_required,
        "previous_day_minute_date": basis_row.get("prev_trade_date") if minute_required else None,
        "previous_day_minute_quality_required": minute_required,
        "minute_scope_reason": minute_scope_reason_for_signal_types(allowed_signal_types),
        "market_data_consumer": "both" if minute_required else "trigger_daily_snapshot",
        "monitor_type": basis_row.get("monitor_type"),
        "condition_pool_ref": f"dry_run:{domain}:condition_pool:{basis_index}:{identity_key}:{condition_key}",
        "source_condition_basis_id": None,
        "source_condition_basis_ref": f"dry_run:{domain}:{basis_index}:{identity_key}",
        "source_version": basis_row.get("source_version"),
        "active_target": True,
        "quality_status": "warning" if basis_row.get("quality_status") != "passed" else "passed",
        "quality_reason": "condition_pool dry-run preview; source condition_basis is not persisted",
        "missing_fields_json": normalize_mapping(basis_row.get("missing_fields_json") or {}),
        "raw_json": {
            "source_basis_quality_status": basis_row.get("quality_status"),
            "source_basis_quality_reason": basis_row.get("quality_reason"),
            "source_basis_raw_json": normalize_mapping(basis_row.get("raw_json") or {}),
        },
    }
    base.update(domain_identity_fields(domain, basis_row))
    base.update(static_pool_fields(basis_row, direction=direction))
    missing_required_periods = missing_required_period_trigger_baseline_periods(base)
    base["missing_period_trigger_baseline_periods"] = missing_required_periods
    if missing_required_periods:
        raw_json = normalize_mapping(base.get("raw_json") or {})
        raw_json["period_trigger_baseline_gate"] = {
            "required_periods": required_periods,
            "missing_periods": missing_required_periods,
        }
        base["raw_json"] = raw_json
    return base


def identity_key_for_domain(domain: str, basis_row: Mapping[str, Any]) -> Any:
    return basis_row.get(f"{domain}_identity_key")


def domain_identity_fields(domain: str, basis_row: Mapping[str, Any]) -> dict[str, Any]:
    if domain == "stock":
        return {
            "stock_identity_key": basis_row.get("stock_identity_key"),
            "code": basis_row.get("code"),
            "exchange": basis_row.get("exchange"),
            "ts_code": basis_row.get("ts_code"),
            "display_code": basis_row.get("display_code") or basis_row.get("code"),
            "name": basis_row.get("name"),
        }
    if domain == "index":
        return {
            "index_identity_key": basis_row.get("index_identity_key"),
            "code": basis_row.get("code"),
            "exchange": basis_row.get("exchange"),
            "ts_code": basis_row.get("ts_code"),
            "display_code": basis_row.get("display_code") or basis_row.get("code"),
            "name": basis_row.get("name"),
        }
    if domain == "board":
        return {
            "board_identity_key": basis_row.get("board_identity_key"),
            "board_code": basis_row.get("board_code"),
            "board_name": basis_row.get("board_name"),
            "board_type": basis_row.get("board_type"),
            "display_code": basis_row.get("board_code"),
            "name": basis_row.get("board_name"),
        }
    raise ValueError(f"unsupported condition_pool domain: {domain!r}")


def static_pool_fields(basis_row: Mapping[str, Any], *, direction: str | None = None) -> dict[str, Any]:
    up_sell_reference_period = normalize_reference_period(basis_row.get("up_sell_reference_period"))
    down_buy_reference_period = normalize_reference_period(basis_row.get("down_buy_reference_period"))
    fields = {
        "period_grade_y": basis_row.get("period_grade_y"),
        "period_grade_q": basis_row.get("period_grade_q"),
        "period_grade_m": basis_row.get("period_grade_m"),
        "period_grade_w": basis_row.get("period_grade_w"),
        "period_grade_d": basis_row.get("period_grade_d"),
        "period_transition_y": basis_row.get("period_transition_y"),
        "period_transition_q": basis_row.get("period_transition_q"),
        "period_transition_m": basis_row.get("period_transition_m"),
        "period_transition_w": basis_row.get("period_transition_w"),
        "period_transition_d": basis_row.get("period_transition_d"),
        "level_up_score": basis_row.get("level_up_score"),
        "level_down_score": basis_row.get("level_down_score"),
        "prev_up_str": basis_row.get("prev_up_str"),
        "prev_dn_str": basis_row.get("prev_dn_str"),
        "period_trigger_baseline_json": normalize_mapping(basis_row.get("period_trigger_baseline_json") or {}),
        "main_up_anchor": basis_row.get("main_up_anchor"),
        "up_reference_period": basis_row.get("up_reference_period"),
        "buy_target_price": basis_row.get("buy_target_price"),
        "buy_expected_return_pct": basis_row.get("buy_expected_return_pct"),
        "main_down_anchor": basis_row.get("main_down_anchor"),
        "down_reference_period": basis_row.get("down_reference_period"),
        "sell_target_price": basis_row.get("sell_target_price"),
        "sell_expected_return_pct": basis_row.get("sell_expected_return_pct"),
        "up_sell_reference_period": up_sell_reference_period,
        "down_buy_reference_period": down_buy_reference_period,
        "clear_sell_ref_period": up_sell_reference_period,
        "total_mv": basis_row.get("total_mv"),
        "circ_mv": basis_row.get("circ_mv"),
        "pe_core": basis_row.get("pe_core"),
        "score": basis_row.get("score"),
        "is_st": basis_row.get("is_st"),
        "stock_status": basis_row.get("stock_status"),
        "official_daily_proof": basis_row.get("official_daily_proof"),
        "financial_asof_date": basis_row.get("financial_asof_date"),
        "financial_quality_status": basis_row.get("financial_quality_status"),
        "recommendation_level": basis_row.get("recommendation_level"),
        "recommendation_reason": basis_row.get("recommendation_reason"),
        "main_index_identity_key": basis_row.get("main_index_identity_key"),
        "main_index_code": basis_row.get("main_index_code"),
        "main_index_name": basis_row.get("main_index_name"),
        "main_index_expected_return_pct": basis_row.get("main_index_expected_return_pct"),
        "preferred_board_identity_key": basis_row.get("preferred_board_identity_key"),
        "preferred_board_code": basis_row.get("preferred_board_code"),
        "preferred_board_name": basis_row.get("preferred_board_name"),
        "preferred_board_expected_return_pct": basis_row.get("preferred_board_expected_return_pct"),
        "linked_board_identity_keys": list(basis_row.get("linked_board_identity_keys") or []),
    }
    fields.update({field: basis_row.get(field) for field in STOCK_FINANCIAL_PASS_THROUGH_FIELDS})
    fields.update(canonical_target_fields_for_direction(basis_row, direction or str(basis_row.get("direction") or "")))
    for field in SYMMETRY_TARGET_FIELDS:
        fields.setdefault(field, None)
    return fields


def normalize_reference_period(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text if text in PERIODS else "D"


def normalize_periods(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        raw_periods = [part.strip() for part in value.split(",") if part.strip()]
    else:
        raw_periods = [str(part).strip() for part in value if str(part).strip()]
    allowed = [period for period in PERIODS if period in raw_periods]
    return allowed


def condition_group_for_key(condition_key: str) -> str:
    if condition_key.startswith("BUY:") and condition_key != "BUY:FULL":
        return "ordinary_buy"
    if condition_key.startswith("SELL:") and condition_key != "SELL:FULL":
        return "ordinary_sell"
    if condition_key in FULL_CONDITION_KEYS:
        return "full"
    if condition_key in HINT_CONDITION_KEYS:
        return "hint"
    return "unknown"


def count_allowed_signal_types(pool_rows: Iterable[Mapping[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in pool_rows:
        for signal_type in row.get("allowed_signal_types") or []:
            counts[str(signal_type)] += 1
    return counts


def minute_required_for_signal_types(signal_types: list[str]) -> bool:
    return any(signal_type in MINUTE_POOL_SIGNAL_TYPES for signal_type in signal_types)


def minute_scope_reason_for_signal_types(signal_types: list[str]) -> str | None:
    if minute_required_for_signal_types(signal_types):
        return "allowed signal types include canonical hint candidates; realtime layer should preload previous day minute bars"
    return None


def decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def build_condition_pool_quality_items(
    *,
    basis_report: Mapping[str, Any],
    pool_preview: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    items.append(quality_item("P0", "passed" if basis_report.get("source_ready_passed") else "failed", "condition_source_ready", "入库层条件源 ready check"))
    basis_p0_count = int((basis_report.get("quality") or {}).get("p0_count") or 0)
    items.append(
        quality_item(
            "P0",
            "passed" if basis_p0_count == 0 else "failed",
            "condition_basis_p0_zero",
            "condition_pool 只能从 P0=0 的 condition_basis 生成通过态结果",
            expected="0",
            actual=str(basis_p0_count),
        )
    )
    items.append(quality_item("P0", "passed", "for_trade_date_inferred", "for_trade_date 由 common_trade_calendar 推导", actual=str(basis_report.get("for_trade_date"))))
    items.append(quality_item("P0", "passed", "prev_trade_date_match", "prev_trade_date(for_trade_date) 等于 source_trade_date", expected=str(basis_report.get("source_trade_date")), actual=str(basis_report.get("prev_trade_date"))))
    items.append(quality_item("P0", "passed", "no_database_write", "condition_pool dry-run 不写数据库"))
    items.append(quality_item("P0", "passed", "no_market_data_pull", "condition_pool dry-run 不拉行情或一分钟 K"))
    items.append(quality_item("P0", "passed", "physical_table_family_split", "stock/index/board pool 预览按物理表族分开生成"))
    if not basis_report.get("for_trade_calendar_row_exists"):
        items.append(
            quality_item(
                "P1",
                "warning",
                "for_trade_calendar_row_missing",
                "source row exposes next_trade_date, but common_trade_calendar has no detail row for inferred for_trade_date yet",
                expected=str(basis_report.get("for_trade_date")),
                actual="missing",
            )
        )

    all_rows = [row for domain in ("stock", "index", "board") for row in pool_preview[domain]["pool_rows"]]
    items.extend(default_condition_pool_policy_quality_items(pool_preview))
    items.extend(pool_contract_quality_items(all_rows))
    items.extend(pool_period_trigger_baseline_quality_items(all_rows))
    if not all_rows:
        items.append(
            quality_item(
                "P1",
                "warning",
                "condition_pool_empty_from_basis_preview",
                "N2-B dry-run basis preview 尚未计算周期/FULL/Hint 必要条件，因此 N2-C 不生成真实 pool 行",
                expected="ordinary/FULL/Hint necessary condition rows",
                actual="0",
            )
        )
    items.append(
        quality_item(
            "P2",
            "warning",
            "source_condition_basis_id_unavailable",
            "N2-C 使用 condition_basis dry-run preview；正式 source_condition_basis_id 要等 execute/migration 后才有",
        )
    )
    return items


def pool_period_trigger_baseline_quality_items(pool_rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    missing = [
        str(row.get("identity_key") or row.get("code") or row.get("board_code"))
        for row in pool_rows
        if not period_trigger_baseline_has_required_shape(row.get("period_trigger_baseline_json"))
    ]
    missing_required = [
        {
            "identity_key": str(row.get("identity_key") or row.get("code") or row.get("board_code")),
            "condition_key": str(row.get("condition_key") or ""),
            "missing_periods": missing_required_period_trigger_baseline_periods(row),
        }
        for row in pool_rows
        if missing_required_period_trigger_baseline_periods(row)
    ]
    return [
        quality_item(
            "P0",
            "passed" if not missing else "failed",
            "period_trigger_baseline_json_full_chain_pool",
            "condition_pool dry-run 必须继承 condition_basis 的 period_trigger_baseline_json",
            expected="missing=0",
            actual="0" if not missing else str(len(missing)),
            details={"missing_samples": missing[:20]},
        ),
        quality_item(
            "P0",
            "passed" if not missing_required else "failed",
            "period_trigger_baseline_required_periods_pool",
            "condition_pool 不得承接 condition_key 必要周期缺 previous_entity_high/low 或金额基准的交易链路行；BUY_HINT/SELL_HINT 不要求周期实体阈值",
            expected="missing_required_periods=0",
            actual="0" if not missing_required else str(len(missing_required)),
            details={"missing_required_samples": missing_required[:20]},
        ),
    ]


def default_condition_pool_policy_quality_items(pool_preview: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    index_policy = pool_preview["index"].get("condition_pool_selection_policy") or default_condition_pool_policy("index")
    board_policy = pool_preview["board"].get("condition_pool_selection_policy") or default_condition_pool_policy("board")
    stock_policy = pool_preview["stock"].get("condition_pool_selection_policy") or default_condition_pool_policy("stock")
    allowed_index_identities = allowed_index_identity_keys_from_policy(index_policy)
    allowed_board_types = allowed_board_types_from_policy(board_policy)
    index_outside = [
        str(row.get("identity_key") or row.get("index_identity_key"))
        for row in pool_preview["index"].get("pool_rows") or []
        if allowed_index_identities is not None
        and str(row.get("identity_key") or row.get("index_identity_key") or "") not in allowed_index_identities
    ]
    board_outside = [
        str(row.get("board_identity_key") or row.get("board_code"))
        for row in pool_preview["board"].get("pool_rows") or []
        if str(row.get("board_type") or "") not in allowed_board_types
    ]
    min_total_mv = decimal_or_none(stock_policy.get("min_total_mv_wan"))
    stock_below = [
        str(row.get("code"))
        for row in pool_preview["stock"].get("pool_rows") or []
        if min_total_mv is not None
        and (decimal_or_none(row.get("total_mv")) is None or decimal_or_none(row.get("total_mv")) < min_total_mv)
    ]
    stock_risk = [
        str(row.get("code"))
        for row in pool_preview["stock"].get("pool_rows") or []
        if (bool(stock_policy.get("exclude_st_or_risk_name")) and is_st_or_risk_stock(row))
        or (stock_policy.get("allowed_stock_statuses") and not field_in_allowlist(row.get("stock_status"), stock_policy.get("allowed_stock_statuses")))
    ]
    stock_official_missing = [
        str(row.get("code"))
        for row in pool_preview["stock"].get("pool_rows") or []
        if bool(stock_policy.get("require_official_daily_proof")) and not normalize_bool(row.get("official_daily_proof"))
    ]
    stock_financial_missing = [
        str(row.get("code"))
        for row in pool_preview["stock"].get("pool_rows") or []
        if (bool(stock_policy.get("require_financial_snapshot")) and row.get("financial_asof_date") in (None, ""))
        or (str(row.get("financial_quality_status") or "") in set(str(item) for item in stock_policy.get("blocked_financial_quality_statuses") or []))
        or (bool(stock_policy.get("require_financial_key_field")) and row.get("pe_core") in (None, "") and row.get("score") in (None, ""))
    ]
    stock_policy_lane_monitor = [
        str(row.get("code"))
        for row in pool_preview["stock"].get("pool_rows") or []
        if row.get("lane") not in {"stock_alert", "stock_trade"} or row.get("monitor_type") != "source_universe_preview"
    ]
    return [
        quality_item(
            "P0",
            "passed" if not index_outside else "failed",
            "index_condition_pool_default_universe",
            "index_condition_pool 必须只保留本次 policy 允许的 exchange-qualified 指数合格条件",
            expected="all_index_identities" if allowed_index_identities is None else ",".join(sorted(allowed_index_identities)),
            actual="passed" if not index_outside else ",".join(index_outside[:20]),
        ),
        quality_item(
            "P0",
            "passed" if not board_outside else "failed",
            "board_condition_pool_default_universe",
            "board_condition_pool 必须只保留本次 policy 允许的 board_type 板块合格条件",
            expected="board_type in " + ",".join(sorted(allowed_board_types)),
            actual="passed" if not board_outside else ",".join(board_outside[:20]),
        ),
        quality_item(
            "P0",
            "passed" if not stock_below else "failed",
            "stock_condition_pool_default_market_value",
            "stock_condition_pool 不得违反当前 policy 的可选市值下限",
            expected="no_market_value_filter" if min_total_mv is None else f"total_mv >= {min_total_mv}",
            actual="passed" if not stock_below else ",".join(stock_below[:20]),
        ),
        quality_item(
            "P0",
            "passed" if not stock_risk else "failed",
            "stock_condition_pool_default_risk_filter",
            "stock_condition_pool 不得违反当前 policy 的风险和状态过滤设置",
            expected="no_risk_or_status_filter" if not stock_policy.get("exclude_st_or_risk_name") and not stock_policy.get("allowed_stock_statuses") else "policy_matched",
            actual="passed" if not stock_risk else ",".join(stock_risk[:20]),
        ),
        quality_item(
            "P0",
            "passed" if not stock_official_missing else "failed",
            "stock_condition_pool_official_daily_required",
            "stock_condition_pool 不得违反当前 policy 的 official daily 要求",
            expected="not_required" if not stock_policy.get("require_official_daily_proof") else "official_daily_proof=true",
            actual="passed" if not stock_official_missing else ",".join(stock_official_missing[:20]),
        ),
        quality_item(
            "P0",
            "passed" if not stock_financial_missing else "failed",
            "stock_condition_pool_financial_snapshot_required",
            "stock_condition_pool 不得违反当前 policy 的财务字段要求",
            expected="not_required" if not stock_policy.get("require_financial_snapshot") and not stock_policy.get("require_financial_key_field") else "policy_matched",
            actual="passed" if not stock_financial_missing else ",".join(stock_financial_missing[:20]),
        ),
        quality_item(
            "P0",
            "passed" if not stock_policy_lane_monitor else "failed",
            "stock_condition_pool_lane_monitor_policy",
            "stock_condition_pool 默认要求 lane/monitor_type 合规",
            expected="lane=stock_alert|stock_trade,monitor_type=source_universe_preview",
            actual="passed" if not stock_policy_lane_monitor else ",".join(stock_policy_lane_monitor[:20]),
        ),
    ]


def pool_contract_quality_items(pool_rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    invalid_directions = sorted({str(row.get("direction")) for row in pool_rows if row.get("direction") not in {"buy", "sell"}})
    invalid_signal_types = sorted(
        {
            str(signal_type)
            for row in pool_rows
            for signal_type in row.get("allowed_signal_types") or []
            if signal_type not in STANDARD_SIGNAL_TYPES
        }
    )
    hint_direction_violations = [
        str(row.get("condition_key"))
        for row in pool_rows
        if (row.get("condition_key") == "BUY_HINT" and row.get("direction") != "buy")
        or (row.get("condition_key") == "SELL_HINT" and row.get("direction") != "sell")
    ]
    full_downgrade_violations = [
        str(row.get("condition_key"))
        for row in pool_rows
        if row.get("raw_json", {}).get("full_source") and row.get("condition_key") in {"BUY:D", "SELL:D"}
    ]
    hint_period_violations = [
        str(row.get("condition_key"))
        for row in pool_rows
        if row.get("condition_key") in HINT_CONDITION_KEYS and row.get("condition_periods")
    ]
    previous_day_minute_violations = [
        str(row.get("condition_key"))
        for row in pool_rows
        if row.get("previous_day_minute_required") and row.get("previous_day_minute_date") != row.get("prev_trade_date")
    ]
    return [
        quality_item(
            "P0",
            "passed" if not invalid_directions else "failed",
            "pool_direction_whitelist",
            "condition_pool direction 只能是 buy/sell",
            expected="buy/sell",
            actual=",".join(invalid_directions) if invalid_directions else "buy/sell",
        ),
        quality_item(
            "P0",
            "passed" if not invalid_signal_types else "failed",
            "pool_allowed_signal_type_whitelist",
            "allowed_signal_types 只能使用 N2 canonical signal_type，不表达 30m action mark",
            expected=",".join(STANDARD_SIGNAL_TYPES),
            actual=",".join(invalid_signal_types) if invalid_signal_types else "whitelist_only",
        ),
        quality_item(
            "P0",
            "passed" if not hint_direction_violations else "failed",
            "hint_direction_is_buy_sell",
            "BUY_HINT/SELL_HINT 不能使用 direction=hint",
            expected="BUY_HINT=buy,SELL_HINT=sell",
            actual=",".join(hint_direction_violations) if hint_direction_violations else "passed",
        ),
        quality_item(
            "P0",
            "passed" if not full_downgrade_violations else "failed",
            "full_not_downgraded_to_d",
            "BUY:FULL/SELL:FULL 不得降级为 BUY:D/SELL:D",
            expected="BUY:FULL/SELL:FULL",
            actual=",".join(full_downgrade_violations) if full_downgrade_violations else "passed",
        ),
        quality_item(
            "P0",
            "passed" if not hint_period_violations else "failed",
            "hint_not_ordinary_periods",
            "BUY_HINT/SELL_HINT 不得混入普通 BUY/SELL 周期集合",
            expected="no condition_periods",
            actual=",".join(hint_period_violations) if hint_period_violations else "passed",
        ),
        quality_item(
            "P0",
            "passed" if not previous_day_minute_violations else "failed",
            "previous_day_minute_date_match",
            "previous_day_minute_required=true 时 previous_day_minute_date 必须等于 prev_trade_date",
            expected="prev_trade_date",
            actual=",".join(previous_day_minute_violations) if previous_day_minute_violations else "passed",
        ),
        quality_item(
            "P0",
            "passed",
            "condition_groups_supported",
            "condition_pool dry-run 支持普通 BUY/SELL、BUY:FULL/SELL:FULL、BUY_HINT/SELL_HINT 三类必要条件",
            expected=",".join(SUPPORTED_CONDITION_GROUPS),
            actual=",".join(SUPPORTED_CONDITION_GROUPS),
        ),
    ]
