"""N2 web policy helpers for the condition-layer console.

The helpers in this module are intentionally read-only. They adapt the JSON
edited in the web console to the existing minute_target_scope dry-run policy
shape, and provide small summaries that the FastAPI layer can render.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import psycopg
from psycopg.rows import dict_row

from ashare_v3.condition.active_status import active_status_order_sql, active_status_sql_list
from ashare_v3.condition.basis import (
    period_trigger_baseline_has_required_shape,
    period_trigger_baseline_not_ready_periods,
)
from ashare_v3.condition.pool import default_condition_pool_policy, required_periods_for_condition_key
from ashare_v3.condition.scope import build_minute_target_scope_dry_run
from ashare_v3.condition.scope_policy import normalize_scope_policy


DEFAULT_DSN = "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3"
DEFAULT_POLICY_DRAFT_RELATIVE_PATH = Path("configs/n2_policy/default_policy_draft.json")
EXECUTE_GATE_DRAFT_JSON_RELATIVE_PATH = Path("docs/N2_web_policy_execute_gate_draft.json")
EXECUTE_GATE_DRAFT_MD_RELATIVE_PATH = Path("docs/N2_WEB_POLICY_EXECUTE_GATE_DRAFT.md")
DEFAULT_POLICY_ID = "n2_default_policy"
POLICY_SOURCE_8782 = "8782_console"
POLICY_DOMAINS = ("index", "board", "stock")
PERIODS = ("y", "q", "m", "w", "d")
DIRECTION_OPTIONS = ("buy", "sell")
CONDITION_FAMILY_OPTIONS = ("ordinary", "full", "hint")
CONDITION_KEY_OPTIONS = ("*", "BUY:*", "SELL:*", "BUY:FULL", "SELL:FULL", "BUY_HINT", "SELL_HINT")
GRADE_OPTIONS = ("volume_up", "low_volume_up", "volume_down", "low_volume_down", "flat", "unknown")
DOMAIN_LABELS = {"index": "指数筛选", "board": "板块筛选", "stock": "个股筛选"}
INDEX_ALL_SELECTION = "__all__"
BOARD_SEGMENT_OPTIONS = (
    {"key": "industry", "label": "行业", "board_type": "tdx_industry"},
    {"key": "concept", "label": "概念", "board_type": "tdx_concept"},
    {"key": "region", "label": "地区", "board_type": "tdx_region"},
)
BOARD_SEGMENT_TYPES = {item["key"]: item["board_type"] for item in BOARD_SEGMENT_OPTIONS}
DEFAULT_INDEX_IDENTITIES = (
    "index:SH:000905",
    "index:SZ:399303",
    "index:SH:000001",
    "index:SH:000852",
    "index:SZ:399001",
    "index:SZ:399006",
    "index:SH:000300",
    "index:SH:000016",
    "index:SH:000688",
)
DETAIL_TABLE_KINDS = ("basis", "pool", "scope", "display")
DETAIL_TABLE_LABELS = {
    "basis": "condition_basis",
    "pool": "condition_pool",
    "scope": "minute_target_scope / trigger_target_scope",
    "display": "condition_display_basis",
}
DETAIL_DOMAIN_LABELS = {"index": "指数", "board": "板块", "stock": "个股"}
DETAIL_STOCK_PAGE_SIZE = 100
DETAIL_MAX_PAGE_SIZE = 300
DETAIL_EXPORT_MAX_ROWS = 100_000
DETAIL_OMITTED_COLUMNS = {"raw_json", "missing_fields_json"}
DETAIL_BASELINE_COLUMNS = (
    "period_trigger_baseline_summary",
    "baseline_status",
    "baseline_ready",
    "baseline_ready_periods",
    "baseline_not_ready_periods",
    "baseline_required_periods",
    "required_period_not_ready",
    "period_trigger_baseline_json",
)
DETAIL_COLUMN_PRIORITY = {
    "basis": (
        "{id_col}",
        "{identity_col}",
        "{code_col}",
        "{name_col}",
        "direction_scope",
        "buy_necessary_key",
        "sell_necessary_key",
        "buy_full_necessary_key",
        "sell_full_necessary_key",
        "oversold_hint_key",
        "overbought_hint_key",
        "period_transition_y",
        "period_transition_q",
        "period_transition_m",
        "period_transition_w",
        "period_transition_d",
        "period_trigger_baseline_summary",
        "baseline_status",
        "baseline_ready",
        "baseline_not_ready_periods",
        "period_trigger_baseline_json",
        "buy_target_price",
        "sell_target_price",
        "up_sell_reference_period",
        "down_buy_reference_period",
        "clear_sell_ref_period",
        "total_mv",
        "score",
        "official_daily_proof",
        "financial_quality_passed",
        "is_st",
        "source_trade_date",
        "created_at",
    ),
    "pool": (
        "{id_col}",
        "{identity_col}",
        "{code_col}",
        "{name_col}",
        "direction",
        "condition_key",
        "condition_family",
        "selected_reason",
        "excluded_reason",
        "allowed_signal_types",
        "basis_period_transition_y",
        "basis_period_transition_q",
        "basis_period_transition_m",
        "basis_period_transition_w",
        "basis_period_transition_d",
        "period_trigger_baseline_summary",
        "baseline_status",
        "baseline_ready",
        "baseline_required_periods",
        "required_period_not_ready",
        "period_trigger_baseline_json",
        "basis_buy_target_price",
        "basis_sell_target_price",
        "basis_up_sell_reference_period",
        "basis_down_buy_reference_period",
        "basis_clear_sell_ref_period",
        "basis_total_mv",
        "basis_score",
        "source_condition_basis_id",
        "source_trade_date",
        "created_at",
    ),
    "scope": (
        "{id_col}",
        "{identity_col}",
        "{code_col}",
        "{name_col}",
        "direction",
        "condition_key",
        "required_data_kind",
        "scope_reason",
        "minute_scope_reason",
        "market_data_consumer",
        "daily_snapshot_required",
        "minute_required",
        "previous_day_minute_required",
        "previous_day_minute_date",
        "basis_period_transition_y",
        "basis_period_transition_q",
        "basis_period_transition_m",
        "basis_period_transition_w",
        "basis_period_transition_d",
        "period_trigger_baseline_summary",
        "baseline_status",
        "baseline_ready",
        "baseline_required_periods",
        "required_period_not_ready",
        "period_trigger_baseline_json",
        "basis_buy_target_price",
        "basis_sell_target_price",
        "basis_up_sell_reference_period",
        "basis_down_buy_reference_period",
        "basis_clear_sell_ref_period",
        "basis_total_mv",
        "basis_score",
        "source_condition_pool_id",
        "for_trade_date",
        "created_at",
    ),
    "display": (
        "{id_col}",
        "{identity_col}",
        "{code_col}",
        "{name_col}",
        "display_title",
        "selected_directions",
        "selected_condition_keys",
        "selected_signal_types",
        "display_scope_reason",
        "period_transition_y",
        "period_transition_q",
        "period_transition_m",
        "period_transition_w",
        "period_transition_d",
        "period_trigger_baseline_summary",
        "baseline_status",
        "baseline_ready",
        "baseline_required_periods",
        "required_period_not_ready",
        "period_trigger_baseline_json",
        "buy_target_price",
        "sell_target_price",
        "up_sell_reference_period",
        "down_buy_reference_period",
        "clear_sell_ref_period",
        "total_mv",
        "score",
        "primary_source_condition_basis_id",
        "primary_source_condition_pool_id",
        "primary_source_minute_target_scope_id",
        "source_trade_date",
        "created_at",
    ),
}

def default_web_policy() -> dict[str, Any]:
    """Return the MVP policy JSON shape described by the N2 web design doc."""
    return {
        "policy_name": "default_adjusted_by_user",
        "index": {
            "selected_identity_key": INDEX_ALL_SELECTION,
            "enabled_identities": [],
            "directions": ["buy", "sell"],
            "condition_family": ["ordinary", "full", "hint"],
            "condition_keys": ["*"],
            "period_grade": {},
            "period_transition": {},
            "prev_up_str": "",
            "prev_dn_str": "",
            "include_codes": [],
            "exclude_codes": [],
            "require_buy_target_price": False,
            "require_sell_target_price": False,
            "require_up_sell_reference_period": False,
            "require_down_buy_reference_period": False,
            "require_clear_sell_ref_period": False,
        },
        "board": {
            "board_segments": ["industry", "concept", "region"],
            "board_types": ["tdx_industry", "tdx_concept", "tdx_region"],
            "board_code_prefixes": [],
            "board_code_prefix": "",
            "include_codes": [],
            "exclude_codes": [],
            "directions": ["buy", "sell"],
            "condition_family": ["ordinary", "full", "hint"],
            "condition_keys": ["*"],
            "period_grade": {},
            "period_transition": {},
            "prev_up_str": "",
            "prev_dn_str": "",
            "require_buy_target_price": False,
            "require_sell_target_price": False,
            "require_up_sell_reference_period": False,
            "require_down_buy_reference_period": False,
            "require_clear_sell_ref_period": False,
        },
        "stock": {
            "min_total_mv_yi": None,
            "exclude_st": False,
            "exclude_bj": False,
            "require_official_daily_proof": False,
            "require_financial_quality_passed": False,
            "allowed_monitor_types": [],
            "allow_financial_key_fields_missing": True,
            "directions": ["buy", "sell"],
            "condition_keys": ["*"],
            "condition_family": ["ordinary", "full", "hint"],
            "period_grade": {},
            "period_transition": {},
            "prev_up_str": "",
            "prev_dn_str": "",
            "require_buy_target_price": False,
            "require_sell_target_price": False,
            "require_up_sell_reference_period": False,
            "require_down_buy_reference_period": False,
            "require_clear_sell_ref_period": False,
            "min_score": None,
            "recommendation_levels": [],
            "include_codes": [],
            "exclude_codes": [],
            "limit": None,
        },
    }


def policy_json_text(policy: Mapping[str, Any] | None = None) -> str:
    return json.dumps(policy or default_web_policy(), ensure_ascii=False, indent=2, default=str)


def policy_form_model(
    policy: Mapping[str, Any] | None = None,
    *,
    index_object_options: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return stable UI metadata for the three-tab policy form."""
    effective = merge_web_policy(policy or default_web_policy())
    return {
        "policy": effective,
        "domains": {
            domain: {
                "key": domain,
                "label": DOMAIN_LABELS[domain],
                "policy": effective[domain],
            }
            for domain in POLICY_DOMAINS
        },
        "periods": list(PERIODS),
        "direction_options": list(DIRECTION_OPTIONS),
        "condition_family_options": list(CONDITION_FAMILY_OPTIONS),
        "condition_key_options": list(CONDITION_KEY_OPTIONS),
        "grade_options": list(GRADE_OPTIONS),
        "fixed_index_identities": list(DEFAULT_INDEX_IDENTITIES),
        "index_object_options": list(index_object_options or default_index_object_options()),
        "board_segment_options": list(BOARD_SEGMENT_OPTIONS),
    }


def merge_web_policy(policy: Mapping[str, Any]) -> dict[str, Any]:
    base = default_web_policy()
    merged = deepcopy(base)
    merged.update({key: deepcopy(value) for key, value in policy.items() if key not in POLICY_DOMAINS})
    for domain in POLICY_DOMAINS:
        if domain in policy and isinstance(policy[domain], Mapping):
            merged[domain].update(deepcopy(dict(policy[domain])))
    return merged


def policy_from_control_payload(values: Mapping[str, Any]) -> dict[str, Any]:
    """Build web policy JSON from form control fields.

    This mirrors the browser-side JSON sync and gives the server a no-JS
    fallback for the same controls.
    """
    policy = default_web_policy()
    policy["policy_name"] = _first(values, "policy_name") or policy["policy_name"]

    for domain in POLICY_DOMAINS:
        section = policy[domain]
        section["directions"] = _list_values(values, f"{domain}.directions") or section.get("directions", [])
        section["condition_family"] = _list_values(values, f"{domain}.condition_family") or section.get("condition_family", [])
        condition_keys = _list_values(values, f"{domain}.condition_keys")
        section["condition_keys"] = condition_keys or ["*"]
        section["period_grade"] = _period_filter_from_values(values, domain, "period_grade")
        section["period_transition"] = _period_filter_from_values(values, domain, "period_transition")
        section["prev_up_str"] = _first(values, f"{domain}.prev_up_str")
        section["prev_dn_str"] = _first(values, f"{domain}.prev_dn_str")
        section["include_codes"] = _code_list(_first(values, f"{domain}.include_codes"))
        section["exclude_codes"] = _code_list(_first(values, f"{domain}.exclude_codes"))
        section["require_buy_target_price"] = _bool_present(values, f"{domain}.require_buy_target_price")
        section["require_sell_target_price"] = _bool_present(values, f"{domain}.require_sell_target_price")
        section["require_up_sell_reference_period"] = _bool_present(values, f"{domain}.require_up_sell_reference_period")
        section["require_down_buy_reference_period"] = _bool_present(values, f"{domain}.require_down_buy_reference_period")
        section["require_clear_sell_ref_period"] = _bool_present(values, f"{domain}.require_clear_sell_ref_period")

    selected_index_identity = _first(values, "index.selected_identity_key")
    policy["index"]["selected_identity_key"] = selected_index_identity
    if selected_index_identity == INDEX_ALL_SELECTION:
        policy["index"]["enabled_identities"] = []
    elif selected_index_identity:
        policy["index"]["enabled_identities"] = [selected_index_identity]
    else:
        enabled_identities = _list_values(values, "index.enabled_identities")
        policy["index"]["selected_identity_key"] = INDEX_ALL_SELECTION if not enabled_identities else ""
        policy["index"]["enabled_identities"] = enabled_identities
    board_segments = _list_values(values, "board.board_segments") or ["industry", "concept", "region"]
    policy["board"]["board_segments"] = board_segments
    policy["board"]["board_types"] = board_types_for_segments(board_segments)
    policy["board"]["board_code_prefixes"] = []
    policy["board"]["board_code_prefix"] = _first(values, "board.board_code_prefix")

    stock = policy["stock"]
    stock["min_total_mv_yi"] = _number_or_none(_first(values, "stock.min_total_mv_yi"))
    stock["max_total_mv_yi"] = _number_or_none(_first(values, "stock.max_total_mv_yi"))
    stock["exclude_st"] = _bool_present(values, "stock.exclude_st")
    stock["exclude_bj"] = _bool_present(values, "stock.exclude_bj")
    stock["require_official_daily_proof"] = _bool_present(values, "stock.require_official_daily_proof")
    stock["require_financial_quality_passed"] = _bool_present(values, "stock.require_financial_quality_passed")
    stock["min_score"] = _number_or_none(_first(values, "stock.min_score"))
    stock["recommendation_levels"] = _code_list(_first(values, "stock.recommendation_levels"))
    stock["main_index_code"] = _first(values, "stock.main_index_code")
    stock["preferred_board_code"] = _first(values, "stock.preferred_board_code")
    limit = _number_or_none(_first(values, "stock.limit"))
    stock["limit"] = int(limit) if limit is not None else None
    return policy


def parse_policy_json(payload: str) -> dict[str, Any]:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"policy JSON parse failed at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("policy JSON must be an object")
    return parsed


def _first(values: Mapping[str, Any], key: str) -> str:
    value = values.get(key)
    if isinstance(value, list):
        return str(value[0]) if value else ""
    if value is None:
        return ""
    return str(value)


def _list_values(values: Mapping[str, Any], key: str) -> list[str]:
    getlist = getattr(values, "getlist", None)
    if callable(getlist):
        listed = getlist(key)
        if listed not in (None, "", []):
            return [str(item) for item in listed if item not in (None, "")]
    value = values.get(key)
    if value in (None, "", []):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return _code_list(str(value))


def _period_filter_from_values(values: Mapping[str, Any], domain: str, field: str) -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}
    for period in PERIODS:
        selected = _list_values(values, f"{domain}.{field}.{period}")
        if selected:
            filters[period] = selected
    return filters


def _code_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        raw_parts = value
    else:
        raw_parts = str(value).replace("\n", ",").replace("，", ",").split(",")
    return [str(part).strip() for part in raw_parts if str(part).strip()]


def _bool_present(values: Mapping[str, Any], key: str) -> bool:
    value = values.get(key)
    if isinstance(value, list):
        return any(str(item).lower() in {"1", "true", "on", "yes"} for item in value)
    return str(value).lower() in {"1", "true", "on", "yes"}


def _number_or_none(value: Any) -> int | float | None:
    if value in (None, ""):
        return None
    decimal_value = Decimal(str(value))
    if decimal_value == decimal_value.to_integral_value():
        return int(decimal_value)
    return float(decimal_value)


def stable_policy_hash(policy: Mapping[str, Any]) -> str:
    payload = json.dumps(policy, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def next_policy_version(previous_artifact: Mapping[str, Any] | None) -> str:
    if not previous_artifact:
        return "v1"
    version = str(previous_artifact.get("policy_version") or "").strip()
    match = re.fullmatch(r"v(\d+)", version)
    if not match:
        return "v1"
    return f"v{int(match.group(1)) + 1}"


def policy_diff_summary(
    previous_policy: Mapping[str, Any] | None,
    current_policy: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    previous = merge_web_policy(previous_policy or {}) if previous_policy else {}
    current = merge_web_policy(current_policy)
    summary: dict[str, dict[str, Any]] = {}
    for domain in POLICY_DOMAINS:
        before = dict(previous.get(domain) or {})
        after = dict(current.get(domain) or {})
        keys = sorted(set(before) | set(after))
        changed_keys = [key for key in keys if before.get(key) != after.get(key)]
        summary[domain] = {
            "changed": bool(changed_keys),
            "changed_keys": changed_keys,
            "before_key_count": len(before),
            "after_key_count": len(after),
            "summary": "initial_policy" if previous_policy is None else ("changed" if changed_keys else "unchanged"),
        }
    return summary


def load_policy_artifact(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def web_policy_to_scope_policy(policy: Mapping[str, Any]) -> dict[str, Any]:
    """Convert web policy JSON to the existing scope dry-run policy contract."""
    merged = merge_web_policy(policy)
    scope_policy: dict[str, Any] = {"policy_name": str(merged.get("policy_name") or "web_policy")}
    scope_policy["index"] = _index_web_to_scope(merged["index"])
    scope_policy["board"] = _board_web_to_scope(merged["board"])
    scope_policy["stock"] = _stock_web_to_scope(merged["stock"])
    return normalize_scope_policy(scope_policy)


def web_policy_to_condition_pool_policy(policy: Mapping[str, Any]) -> dict[str, Any]:
    """Convert web policy JSON to the condition_pool dry-run policy contract.

    The web console edits condition-pool eligibility, then the scope policy can
    only narrow that pool. Keep this separate from web_policy_to_scope_policy so
    controls such as board_types and "all indexes" can expand the pool before
    minute_target_scope applies its final narrowing pass.
    """
    merged = merge_web_policy(policy)
    scope_policy = web_policy_to_scope_policy(merged)
    pool_policy: dict[str, Any] = {"policy_name": scope_policy["policy_name"]}
    for domain in POLICY_DOMAINS:
        pool_policy[domain] = {
            **default_condition_pool_policy(domain),
            **scope_policy[domain],
        }
    selected_index_identity = str(merged.get("index", {}).get("selected_identity_key") or "").strip()
    if selected_index_identity == INDEX_ALL_SELECTION:
        pool_policy["index"]["include_all_identities"] = True
        pool_policy["index"]["include_identity_keys"] = []
        pool_policy["index"]["include_codes"] = []
    return pool_policy


def _index_web_to_scope(section: Mapping[str, Any]) -> dict[str, Any]:
    selected_identity = str(section.get("selected_identity_key") or "").strip()
    if selected_identity == INDEX_ALL_SELECTION:
        identities: list[str] = []
    elif selected_identity:
        identities = [selected_identity]
    else:
        identities = list(_string_list(section.get("enabled_identities") or section.get("include_identity_keys")))
    include_codes = list(_string_list(section.get("include_codes")))
    if identities and not include_codes:
        include_codes = [identity.split(":")[-1] for identity in identities]
    output = {
        "enabled": section.get("enabled", True),
        "source": "condition_pool",
        "include_identity_keys": identities,
        "include_codes": include_codes,
        "exclude_identity_keys": list(_string_list(section.get("exclude_identity_keys"))),
        "exclude_codes": list(_string_list(section.get("exclude_codes"))),
        "directions": list(_string_list(section.get("directions") or ["buy", "sell"])),
        "require_buy_target_price": bool(section.get("require_buy_target_price", False)),
        "require_sell_target_price": bool(section.get("require_sell_target_price", False)),
        "require_up_sell_reference_period": bool(section.get("require_up_sell_reference_period", False)),
        "require_down_buy_reference_period": bool(section.get("require_down_buy_reference_period", False)),
        "require_clear_sell_ref_period": bool(section.get("require_clear_sell_ref_period", False)),
    }
    _copy_condition_families(section, output)
    _copy_condition_keys(section, output)
    _copy_period_filters(section, output)
    _copy_if_present(section, output, "prev_up_str")
    _copy_if_present(section, output, "prev_dn_str")
    return output


def _board_web_to_scope(section: Mapping[str, Any]) -> dict[str, Any]:
    board_types = board_types_for_segments(section.get("board_segments"))
    if not board_types:
        board_types = list(_string_list(section.get("board_types")))
    prefixes = list(_string_list(section.get("board_code_prefixes")))
    if not prefixes and section.get("board_code_prefix"):
        prefixes = [str(section.get("board_code_prefix"))]
    output = {
        "enabled": section.get("enabled", True),
        "source": "condition_pool",
        "board_types": board_types,
        "board_code_prefix": prefixes[0] if prefixes else "",
        "board_code_prefixes": prefixes,
        "include_board_codes": list(_string_list(section.get("include_board_codes") or section.get("include_codes"))),
        "exclude_board_codes": list(_string_list(section.get("exclude_board_codes") or section.get("exclude_codes"))),
        "directions": list(_string_list(section.get("directions") or ["buy", "sell"])),
        "require_buy_target_price": bool(section.get("require_buy_target_price", False)),
        "require_sell_target_price": bool(section.get("require_sell_target_price", False)),
        "require_up_sell_reference_period": bool(section.get("require_up_sell_reference_period", False)),
        "require_down_buy_reference_period": bool(section.get("require_down_buy_reference_period", False)),
        "require_clear_sell_ref_period": bool(section.get("require_clear_sell_ref_period", False)),
    }
    _copy_condition_families(section, output)
    _copy_condition_keys(section, output)
    _copy_period_filters(section, output)
    _copy_if_present(section, output, "prev_up_str")
    _copy_if_present(section, output, "prev_dn_str")
    _copy_if_present(section, output, "main_up_anchor")
    _copy_if_present(section, output, "main_down_anchor")
    return output


def _stock_web_to_scope(section: Mapping[str, Any]) -> dict[str, Any]:
    output = {
        "enabled": section.get("enabled", True),
        "source": "condition_pool",
        "directions": list(_string_list(section.get("directions") or ["buy", "sell"])),
        "include_condition_families": list(
            _string_list(section.get("include_condition_families") or section.get("condition_family") or ["ordinary", "full", "hint"])
        ),
        "include_codes": list(_string_list(section.get("include_codes"))),
        "exclude_codes": list(_string_list(section.get("exclude_codes"))),
        "min_total_mv_wan": _market_value_wan(section),
        "max_total_mv_wan": _market_value_wan(section, web_key="max_total_mv_yi", scope_key="max_total_mv_wan"),
        "market_value_compare": section.get("market_value_compare", ">="),
        "exclude_bj": bool(section.get("exclude_bj", False)),
        "allowed_monitor_types": list(_string_list(section.get("allowed_monitor_types"))),
        "require_financial_key_field": bool(
            section.get("require_financial_key_field")
            if "require_financial_key_field" in section
            else not bool(section.get("allow_financial_key_fields_missing", False))
        ),
        "require_buy_target_price": bool(section.get("require_buy_target_price", False)),
        "require_sell_target_price": bool(section.get("require_sell_target_price", False)),
        "require_up_sell_reference_period": bool(section.get("require_up_sell_reference_period", False)),
        "require_down_buy_reference_period": bool(section.get("require_down_buy_reference_period", False)),
        "require_clear_sell_ref_period": bool(section.get("require_clear_sell_ref_period", False)),
        "min_score": section.get("min_score"),
        "recommendation_levels": list(_string_list(section.get("recommendation_levels"))),
        "limit": section.get("limit"),
    }
    _copy_condition_keys(section, output)
    _copy_if_present(section, output, "prev_up_str")
    _copy_if_present(section, output, "prev_dn_str")
    _copy_period_filters(section, output)
    _copy_if_present(section, output, "main_index_code")
    _copy_if_present(section, output, "preferred_board_code")
    return output


def _copy_condition_keys(source: Mapping[str, Any], target: dict[str, Any]) -> None:
    condition_keys = list(_string_list(source.get("condition_keys") or source.get("include_condition_keys")))
    if condition_keys and "*" not in condition_keys:
        target["include_condition_keys"] = condition_keys


def _copy_condition_families(source: Mapping[str, Any], target: dict[str, Any]) -> None:
    families = list(_string_list(source.get("include_condition_families") or source.get("condition_family")))
    if families:
        target["include_condition_families"] = families


def _copy_period_filters(source: Mapping[str, Any], target: dict[str, Any]) -> None:
    for prefix in ("period_grade", "period_transition"):
        value = source.get(prefix)
        if isinstance(value, Mapping):
            for period, allowed_values in value.items():
                key = f"{prefix}_{str(period).lower()}"
                if allowed_values not in (None, "", []):
                    target[key] = list(_string_list(allowed_values))
        for period in ("y", "q", "m", "w", "d"):
            key = f"{prefix}_{period}"
            if key in source and source[key] not in (None, "", []):
                target[key] = list(_string_list(source[key]))


def _copy_if_present(source: Mapping[str, Any], target: dict[str, Any], key: str) -> None:
    if source.get(key) not in (None, "", []):
        target[key] = source[key]


def _string_list(value: Any) -> tuple[str, ...]:
    if value in (None, "", []):
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value if item not in (None, ""))


def board_types_for_segments(segments: Any) -> list[str]:
    board_types: list[str] = []
    for segment in _string_list(segments):
        board_type = BOARD_SEGMENT_TYPES.get(segment)
        if board_type and board_type not in board_types:
            board_types.append(board_type)
    return board_types


def default_index_object_options() -> list[dict[str, str]]:
    return [
        {"identity_key": identity, "label": identity}
        for identity in DEFAULT_INDEX_IDENTITIES
    ]


def _market_value_wan(
    section: Mapping[str, Any],
    *,
    web_key: str = "min_total_mv_yi",
    scope_key: str = "min_total_mv_wan",
) -> str | None:
    if section.get(scope_key) not in (None, ""):
        return str(section[scope_key])
    if section.get(web_key) in (None, ""):
        return None
    try:
        value = Decimal(str(section[web_key])) * Decimal("10000")
        return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{web_key} must be numeric") from exc


def detail_filter_model() -> dict[str, Any]:
    """Return UI metadata for the read-only active-run detail browser."""
    return {
        "domains": [
            {"key": domain, "label": DETAIL_DOMAIN_LABELS[domain]}
            for domain in POLICY_DOMAINS
        ],
        "table_kinds": [
            {"key": table_kind, "label": DETAIL_TABLE_LABELS[table_kind]}
            for table_kind in DETAIL_TABLE_KINDS
        ],
        "direction_options": ["", *DIRECTION_OPTIONS],
        "period_transition_options": list(GRADE_OPTIONS),
        "target_status_options": [
            {"value": "", "label": "全部"},
            {"value": "present", "label": "有目标价"},
            {"value": "missing", "label": "无目标价"},
        ],
        "baseline_status_options": [
            {"value": "", "label": "全部"},
            {"value": "ready", "label": "baseline ready"},
            {"value": "partial", "label": "baseline 部分缺口"},
            {"value": "missing", "label": "baseline 缺失"},
        ],
        "required_period_not_ready_options": [
            {"value": "", "label": "全部"},
            {"value": "yes", "label": "required period not ready"},
            {"value": "no", "label": "required period ready"},
        ],
        "clear_ref_options": [
            {"value": "", "label": "全部"},
            {"value": "present", "label": "有值"},
            {"value": "missing", "label": "无值"},
        ],
        "reference_period_options": [
            {"value": "", "label": "全部"},
            {"value": "present", "label": "有值"},
            {"value": "missing", "label": "无值"},
        ],
        "stock_page_size": DETAIL_STOCK_PAGE_SIZE,
        "stock_max_page_size": DETAIL_MAX_PAGE_SIZE,
    }


def detail_table_spec(domain: str, table_kind: str) -> dict[str, Any]:
    if domain not in POLICY_DOMAINS:
        raise ValueError(f"unsupported detail domain: {domain}")
    if table_kind not in DETAIL_TABLE_KINDS:
        raise ValueError(f"unsupported detail table kind: {table_kind}")
    prefix = f"{domain}_condition"
    identity_col = {
        "index": "index_identity_key",
        "board": "board_identity_key",
        "stock": "stock_identity_key",
    }[domain]
    code_col = "board_code" if domain == "board" else "code"
    name_col = "board_name" if domain == "board" else "name"
    table = {
        "basis": f"{prefix}_basis",
        "pool": f"{prefix}_pool",
        "scope": f"{domain}_minute_target_scope",
        "display": f"{prefix}_display_basis",
    }[table_kind]
    id_col = {
        "basis": f"{prefix}_basis_id",
        "pool": f"{prefix}_pool_id",
        "scope": f"{domain}_minute_target_scope_id",
        "display": f"{prefix}_display_basis_id",
    }[table_kind]
    return {
        "domain": domain,
        "table_kind": table_kind,
        "table": table,
        "id_col": id_col,
        "identity_col": identity_col,
        "code_col": code_col,
        "name_col": name_col,
        "basis_table": f"{prefix}_basis",
        "basis_id_col": f"{prefix}_basis_id",
        "pool_table": f"{prefix}_pool",
        "pool_id_col": f"{prefix}_pool_id",
        "pagination_enabled": domain == "stock",
    }


def detail_visible_columns(domain: str, table_kind: str, columns: list[str]) -> list[str]:
    """Return a focused column order for the detail browser.

    The database remains the source of truth; this only prevents the web table
    from hiding code/name/condition fields behind low-value technical columns.
    """
    spec = detail_table_spec(domain, table_kind)
    available = [column for column in columns if column not in DETAIL_OMITTED_COLUMNS]
    available_set = set(available)
    priority = [
        item.format(**spec)
        for item in DETAIL_COLUMN_PRIORITY[table_kind]
    ]
    visible = [column for column in priority if column in available_set]
    if not visible:
        return available
    return visible


def enrich_detail_rows_with_baseline(rows: list[dict[str, Any]], table_kind: str) -> list[dict[str, Any]]:
    """Add compact N2-R4 baseline fields for detail display/export."""
    enriched_rows: list[dict[str, Any]] = []
    for row in rows:
        enriched = dict(row)
        if "period_trigger_baseline_json" in enriched:
            enriched.update(detail_baseline_summary(enriched, table_kind=table_kind))
            baseline = enriched.get("period_trigger_baseline_json")
            if isinstance(baseline, (dict, list)):
                enriched["period_trigger_baseline_json"] = json.dumps(
                    baseline,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                    separators=(",", ":"),
                )
        enriched_rows.append(enriched)
    return enriched_rows


def detail_columns_with_baseline(columns: list[str], rows: list[Mapping[str, Any]]) -> list[str]:
    has_baseline = "period_trigger_baseline_json" in columns or any(
        "period_trigger_baseline_json" in row
        for row in rows
    )
    if not has_baseline:
        return list(columns)
    output = list(columns)
    for column in DETAIL_BASELINE_COLUMNS:
        if column not in output:
            output.append(column)
    return output


def detail_baseline_summary(row: Mapping[str, Any], *, table_kind: str) -> dict[str, Any]:
    baseline = _baseline_value(row.get("period_trigger_baseline_json"))
    periods = [period.upper() for period in PERIODS]
    has_shape = period_trigger_baseline_has_required_shape(baseline)
    not_ready = period_trigger_baseline_not_ready_periods(baseline, periods) if has_shape else periods
    ready_periods = [period for period in periods if period not in set(not_ready)] if has_shape else []
    condition_key = str(row.get("condition_key") or "")
    required_periods = required_periods_for_condition_key(condition_key)
    if table_kind == "basis":
        required_not_ready = bool(not_ready)
    else:
        required_not_ready = bool(period_trigger_baseline_not_ready_periods(baseline, required_periods))
    if not has_shape:
        status = "missing"
    elif not not_ready:
        status = "ready"
    else:
        status = "partial"
    summary = status if status == "missing" else f"{status}:{','.join(ready_periods) or '-'}"
    if not_ready:
        summary = f"{summary};not_ready:{','.join(not_ready)}"
    return {
        "period_trigger_baseline_summary": summary,
        "baseline_status": status,
        "baseline_ready": status == "ready",
        "baseline_ready_periods": ",".join(ready_periods),
        "baseline_not_ready_periods": ",".join(not_ready),
        "baseline_required_periods": ",".join(required_periods),
        "required_period_not_ready": required_not_ready,
    }


def detail_baseline_counts(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    counts = {"ready": 0, "partial": 0, "missing": 0, "required_period_not_ready": 0}
    for row in rows:
        status = str(row.get("baseline_status") or "")
        if status in ("ready", "partial", "missing"):
            counts[status] += 1
        if row.get("required_period_not_ready"):
            counts["required_period_not_ready"] += 1
    return {"loaded_row_count": len(rows), **counts}


def _baseline_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def normalize_detail_filters(values: Mapping[str, Any] | None, *, domain: str = "index") -> dict[str, Any]:
    values = {} if values is None else values
    page = _positive_int(_first(values, "page"), default=1)
    page_size = _positive_int(_first(values, "page_size"), default=DETAIL_STOCK_PAGE_SIZE)
    page_size = min(max(page_size, 1), DETAIL_MAX_PAGE_SIZE)
    period_transitions = _list_values(values, "period_transition")
    return {
        "code_query": _first(values, "code_query").strip(),
        "name_query": _first(values, "name_query").strip(),
        "condition_key": _first(values, "condition_key").strip(),
        "direction": _first(values, "direction").strip(),
        "period_transition": period_transitions[0] if period_transitions else "",
        "period_transitions": period_transitions,
        "target_status": _first(values, "target_status").strip(),
        "baseline_status": _first(values, "baseline_status").strip(),
        "required_period_not_ready": _first(values, "required_period_not_ready").strip(),
        "min_total_mv_yi": _decimal_or_none(_first(values, "min_total_mv_yi")),
        "max_total_mv_yi": _decimal_or_none(_first(values, "max_total_mv_yi")),
        "up_sell_reference_period": _first(values, "up_sell_reference_period").strip(),
        "down_buy_reference_period": _first(values, "down_buy_reference_period").strip(),
        "clear_ref_period": _first(values, "clear_ref_period").strip(),
        "min_score": _decimal_or_none(_first(values, "min_score")),
        "max_score": _decimal_or_none(_first(values, "max_score")),
        "page": page if domain == "stock" else 1,
        "page_size": page_size,
    }


def detail_query_parts(
    domain: str,
    table_kind: str,
    filters: Mapping[str, Any],
    *,
    run_id: str,
    paginate: bool = True,
) -> dict[str, Any]:
    """Build parameterized SQL fragments for the read-only detail browser."""
    spec = detail_table_spec(domain, table_kind)
    joins = _detail_joins(spec)
    clauses = ["t.run_id = %s"]
    params: list[Any] = [run_id]

    if filters.get("code_query"):
        clauses.append(f"t.{spec['code_col']} ILIKE %s")
        params.append(f"%{filters['code_query']}%")
    if filters.get("name_query"):
        clauses.append(f"t.{spec['name_col']} ILIKE %s")
        params.append(f"%{filters['name_query']}%")
    if filters.get("condition_key"):
        condition_clause, condition_params = _condition_key_clause(table_kind, str(filters["condition_key"]))
        clauses.append(condition_clause)
        params.extend(condition_params)
    if filters.get("direction"):
        direction_clause, direction_params = _direction_clause(table_kind, str(filters["direction"]))
        clauses.append(direction_clause)
        params.extend(direction_params)
    period_transitions = list(filters.get("period_transitions") or [])
    if not period_transitions and filters.get("period_transition"):
        period_transitions = [str(filters["period_transition"])]
    if period_transitions:
        transition_clause, transition_params = _period_transition_clause(table_kind, period_transitions)
        clauses.append(transition_clause)
        params.extend(transition_params)
    if filters.get("target_status"):
        clauses.append(_target_status_clause(table_kind, str(filters["target_status"])))
    if filters.get("baseline_status"):
        clauses.append(_baseline_status_clause(str(filters["baseline_status"])))
    if filters.get("required_period_not_ready"):
        clauses.append(
            _required_period_not_ready_clause(
                table_kind,
                str(filters["required_period_not_ready"]),
            )
        )
    for filter_key, field in (
        ("up_sell_reference_period", "up_sell_reference_period"),
        ("down_buy_reference_period", "down_buy_reference_period"),
        ("clear_ref_period", "clear_sell_ref_period"),
    ):
        if filters.get(filter_key):
            ref_clause, ref_params = _reference_period_clause(table_kind, field, str(filters[filter_key]))
            clauses.append(ref_clause)
            params.extend(ref_params)
    if domain == "stock":
        clauses.extend(_stock_numeric_clauses(table_kind, filters, params))

    order_sql = _detail_order_sql(spec)
    from_sql = f"FROM {spec['table']} t {joins}".strip()
    where_sql = " AND ".join(f"({clause})" for clause in clauses)
    select_extra = _detail_select_extra(spec)
    count_sql = f"SELECT count(*)::bigint AS row_count {from_sql} WHERE {where_sql}"
    data_sql = f"SELECT t.*{select_extra} {from_sql} WHERE {where_sql} ORDER BY {order_sql}"
    pagination_enabled = bool(spec["pagination_enabled"] and paginate)
    if pagination_enabled:
        offset = (int(filters["page"]) - 1) * int(filters["page_size"])
        data_sql = f"{data_sql} LIMIT %s OFFSET %s"
        data_params = [*params, int(filters["page_size"]), offset]
    else:
        data_params = list(params)
    return {
        "spec": spec,
        "count_sql": count_sql,
        "data_sql": data_sql,
        "count_params": list(params),
        "data_params": data_params,
        "pagination_enabled": pagination_enabled,
    }


def _detail_joins(spec: Mapping[str, Any]) -> str:
    table_kind = str(spec["table_kind"])
    if table_kind == "basis":
        return ""
    if table_kind == "pool":
        return (
            f"LEFT JOIN {spec['basis_table']} b "
            f"ON b.{spec['basis_id_col']} = t.source_condition_basis_id"
        )
    if table_kind == "display":
        return (
            f"LEFT JOIN {spec['basis_table']} b "
            f"ON b.{spec['basis_id_col']} = t.primary_source_condition_basis_id "
            f"LEFT JOIN {spec['pool_table']} p "
            f"ON p.{spec['pool_id_col']} = t.primary_source_condition_pool_id"
        )
    return (
        f"LEFT JOIN {spec['pool_table']} p "
        f"ON p.{spec['pool_id_col']} = t.source_condition_pool_id "
        f"LEFT JOIN {spec['basis_table']} b "
        f"ON b.{spec['basis_id_col']} = p.source_condition_basis_id"
    )


def _detail_select_extra(spec: Mapping[str, Any]) -> str:
    if spec["table_kind"] == "basis":
        return ""
    if spec["table_kind"] == "display":
        return ""
    extras = [
        "b.period_transition_y AS basis_period_transition_y",
        "b.period_transition_q AS basis_period_transition_q",
        "b.period_transition_m AS basis_period_transition_m",
        "b.period_transition_w AS basis_period_transition_w",
        "b.period_transition_d AS basis_period_transition_d",
        "b.buy_target_price AS basis_buy_target_price",
        "b.sell_target_price AS basis_sell_target_price",
        "b.up_sell_reference_period AS basis_up_sell_reference_period",
        "b.down_buy_reference_period AS basis_down_buy_reference_period",
        "b.clear_sell_ref_period AS basis_clear_sell_ref_period",
    ]
    if spec["domain"] == "stock":
        extras.extend(["b.total_mv AS basis_total_mv", "b.score AS basis_score"])
    return ", " + ", ".join(extras)


def _detail_order_sql(spec: Mapping[str, Any]) -> str:
    pieces = [f"t.{spec['code_col']} NULLS LAST"]
    if spec["table_kind"] not in ("basis", "display"):
        pieces.extend(["t.direction NULLS LAST", "t.condition_key NULLS LAST"])
    pieces.append(f"t.{spec['id_col']} NULLS LAST")
    return ", ".join(pieces)


def _condition_key_clause(table_kind: str, value: str) -> tuple[str, list[Any]]:
    pattern = f"%{value}%"
    if table_kind == "display":
        return "array_to_string(t.selected_condition_keys, ',') ILIKE %s", [pattern]
    if table_kind != "basis":
        return "t.condition_key ILIKE %s", [pattern]
    columns = (
        "buy_necessary_key",
        "sell_necessary_key",
        "buy_full_necessary_key",
        "sell_full_necessary_key",
        "oversold_hint_key",
        "overbought_hint_key",
    )
    return " OR ".join(f"t.{column} ILIKE %s" for column in columns), [pattern] * len(columns)


def _direction_clause(table_kind: str, value: str) -> tuple[str, list[Any]]:
    if table_kind == "display":
        return "%s = ANY(t.selected_directions)", [value]
    if table_kind != "basis":
        return "t.direction = %s", [value]
    return "t.direction_scope::text ILIKE %s", [f"%{value}%"]


def _period_transition_clause(table_kind: str, values: list[str]) -> tuple[str, list[Any]]:
    alias = "t" if table_kind in ("basis", "display") else "b"
    columns = tuple(f"{alias}.period_transition_{period}" for period in PERIODS)
    selected = [value for value in values if value]
    if not selected:
        return "TRUE", []
    placeholders = ", ".join(["%s"] * len(selected))
    return " OR ".join(f"{column} IN ({placeholders})" for column in columns), selected * len(columns)


def _target_status_clause(table_kind: str, value: str) -> str:
    alias = "t" if table_kind in ("basis", "display") else "b"
    has_target = (
        f"NULLIF(({alias}.buy_target_price)::text, '') IS NOT NULL "
        f"OR NULLIF(({alias}.sell_target_price)::text, '') IS NOT NULL"
    )
    return f"NOT ({has_target})" if value == "missing" else has_target


def _stock_numeric_clauses(table_kind: str, filters: Mapping[str, Any], params: list[Any]) -> list[str]:
    clauses: list[str] = []
    total_mv_expr = (
        "t.total_mv"
        if table_kind in ("basis", "display")
        else "COALESCE(t.total_mv, b.total_mv)"
        if table_kind == "scope"
        else "b.total_mv"
    )
    score_expr = "t.score" if table_kind in ("basis", "display") else "b.score"
    min_total_mv = filters.get("min_total_mv_yi")
    max_total_mv = filters.get("max_total_mv_yi")
    min_score = filters.get("min_score")
    max_score = filters.get("max_score")
    if min_total_mv is not None:
        clauses.append(f"NULLIF(({total_mv_expr})::text, '')::numeric >= %s")
        params.append(min_total_mv * Decimal("10000"))
    if max_total_mv is not None:
        clauses.append(f"NULLIF(({total_mv_expr})::text, '')::numeric <= %s")
        params.append(max_total_mv * Decimal("10000"))
    if min_score is not None:
        clauses.append(f"NULLIF(({score_expr})::text, '')::numeric >= %s")
        params.append(min_score)
    if max_score is not None:
        clauses.append(f"NULLIF(({score_expr})::text, '')::numeric <= %s")
        params.append(max_score)
    return clauses


def _reference_period_clause(table_kind: str, field: str, value: str) -> tuple[str, list[Any]]:
    expr = f"t.{field}" if table_kind in ("basis", "display") else f"COALESCE(t.{field}, b.{field})"
    has_clear_ref = f"NULLIF(({expr})::text, '') IS NOT NULL"
    if value == "present":
        return has_clear_ref, []
    if value == "missing":
        return f"NOT ({has_clear_ref})", []
    return f"{expr} = %s", [value]


def _baseline_json_missing_expr(alias: str = "t") -> str:
    return (
        f"{alias}.period_trigger_baseline_json IS NULL "
        f"OR NULLIF(({alias}.period_trigger_baseline_json)::text, '') IS NULL "
        f"OR ({alias}.period_trigger_baseline_json)::text = '{{}}'"
    )


def _baseline_period_ready_expr(alias: str, period: str) -> str:
    return (
        f"COALESCE({alias}.period_trigger_baseline_json->'periods'->'{period}'->>'baseline_ready', "
        "'false') = 'true'"
    )


def _baseline_period_not_ready_expr(alias: str, period: str) -> str:
    return f"NOT ({_baseline_period_ready_expr(alias, period)})"


def _baseline_any_not_ready_expr(alias: str = "t") -> str:
    return " OR ".join(_baseline_period_not_ready_expr(alias, period.upper()) for period in PERIODS)


def _baseline_status_clause(value: str) -> str:
    missing = _baseline_json_missing_expr("t")
    any_not_ready = _baseline_any_not_ready_expr("t")
    if value == "missing":
        return missing
    if value == "ready":
        return f"NOT ({missing}) AND NOT ({any_not_ready})"
    if value == "partial":
        return f"NOT ({missing}) AND ({any_not_ready})"
    return "TRUE"


def _required_period_not_ready_clause(table_kind: str, value: str) -> str:
    expr = _required_period_not_ready_expr("t", has_condition_key=table_kind != "basis")
    if value == "yes":
        return expr
    if value == "no":
        return f"NOT ({expr})"
    return "TRUE"


def _required_period_not_ready_expr(alias: str = "t", *, has_condition_key: bool) -> str:
    if not has_condition_key:
        return f"({_baseline_any_not_ready_expr(alias)})"
    condition_key = f"UPPER(COALESCE({alias}.condition_key, ''))"
    period_text = f"UPPER(split_part(COALESCE({alias}.condition_key, ''), ':', 2))"
    clauses = []
    for period in PERIODS:
        upper = period.upper()
        ordinary_needs_period = f"(',' || {period_text} || ',') LIKE '%%,{upper},%%'"
        if upper == "D":
            needs_period = f"{condition_key} IN ('BUY:FULL', 'SELL:FULL') OR {ordinary_needs_period}"
        else:
            needs_period = ordinary_needs_period
        clauses.append(f"(({needs_period}) AND {_baseline_period_not_ready_expr(alias, upper)})")
    return " OR ".join(clauses) or "FALSE"


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


@dataclass(frozen=True)
class N2PolicyConsoleConfig:
    project_root: Path
    dsn: str = os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN)
    use_database: bool = True


class N2PolicyConsoleService:
    """Read-only service used by the N2 policy console."""

    def __init__(self, config: N2PolicyConsoleConfig | None = None) -> None:
        self.config = config or N2PolicyConsoleConfig(project_root=default_project_root())

    def default_policy_for_console(self) -> dict[str, Any]:
        artifact = load_policy_artifact(self.config.project_root / DEFAULT_POLICY_DRAFT_RELATIVE_PATH)
        if isinstance(artifact, Mapping) and isinstance(artifact.get("web_policy"), Mapping):
            return merge_web_policy(artifact["web_policy"])
        return default_web_policy()

    def console_context(self) -> dict[str, Any]:
        active_run = self.active_run()
        summaries = self.pool_scope_summaries(active_run.get("run_id"))
        baseline_gate = self.baseline_gate_summary(active_run.get("run_id"))
        index_object_options = self.index_object_options(active_run.get("run_id"))
        default_policy = self.default_policy_for_console()
        return {
            "layer_role": "N2_condition",
            "active_run": active_run,
            "summaries": summaries,
            "baseline_gate": baseline_gate,
            "initial_detail": self.condition_detail("index", "basis", {}, active_run=active_run),
            "detail_model": detail_filter_model(),
            "default_policy": default_policy,
            "default_policy_json": policy_json_text(default_policy),
            "form_model": policy_form_model(default_policy, index_object_options=index_object_options),
            "execute_overwrite_enabled": False,
        }

    def active_run(self) -> dict[str, Any]:
        if self.config.use_database:
            try:
                row = self._active_run_from_db()
                if row:
                    return {**row, "source": "postgres_read_only"}
            except Exception as exc:
                return unavailable_active_run(str(exc))
        return unavailable_active_run("database disabled; fixed local report fallback is disabled")

    def active_run_for_source_trade_date(self, source_trade_date: str | None) -> dict[str, Any]:
        source_trade_date = str(source_trade_date or "")
        if self.config.use_database and source_trade_date:
            try:
                row = self._active_run_from_db(source_trade_date=source_trade_date)
                if row:
                    return {**row, "source": "postgres_read_only"}
            except Exception as exc:
                return unavailable_active_run(str(exc))
        active = self.active_run()
        if source_trade_date and str(active.get("source_trade_date") or "") != source_trade_date:
            return unavailable_active_run(f"no active condition run found for source_trade_date={source_trade_date}")
        return active

    def pool_scope_summaries(self, run_id: str | None = None) -> dict[str, Any]:
        if self.config.use_database and run_id:
            try:
                db_summary = self._pool_scope_summaries_from_db(run_id)
                if db_summary:
                    return {"source": "postgres_read_only", "domains": db_summary}
            except Exception as exc:
                return empty_summary(f"postgres_unavailable:{exc}")
        return empty_summary("no_active_run")

    def index_object_options(self, run_id: str | None = None) -> list[dict[str, str]]:
        if self.config.use_database and run_id:
            try:
                rows = self._index_object_options_from_db(run_id)
                if rows:
                    return rows
            except Exception:
                return default_index_object_options()
        return default_index_object_options()

    def baseline_gate_summary(self, run_id: str | None = None) -> dict[str, Any]:
        if self.config.use_database and run_id:
            try:
                return self._baseline_gate_summary_from_db(run_id)
            except Exception as exc:
                return empty_baseline_gate_summary(f"postgres_unavailable:{exc}")
        return empty_baseline_gate_summary("no_active_run")

    def condition_detail(
        self,
        domain: str,
        table_kind: str,
        filters: Mapping[str, Any] | None = None,
        *,
        active_run: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            spec = detail_table_spec(domain, table_kind)
        except ValueError as exc:
            return empty_detail(str(exc))
        normalized_filters = normalize_detail_filters(filters, domain=domain)
        active = dict(active_run or self.active_run())
        run_id = str(active.get("run_id") or "")
        if not self.config.use_database:
            return empty_detail(
                "database disabled; fixed local report fallback is disabled",
                domain=domain,
                table_kind=table_kind,
                table_name=spec["table"],
                filters=normalized_filters,
                run_id=run_id,
            )
        if not run_id:
            return empty_detail(
                "no active condition run available",
                domain=domain,
                table_kind=table_kind,
                table_name=spec["table"],
                filters=normalized_filters,
            )
        try:
            return self._condition_detail_from_db(
                domain=domain,
                table_kind=table_kind,
                filters=normalized_filters,
                run_id=run_id,
            )
        except Exception as exc:
            return empty_detail(
                f"postgres_unavailable:{exc}",
                domain=domain,
                table_kind=table_kind,
                table_name=spec["table"],
                filters=normalized_filters,
                run_id=run_id,
            )

    def condition_detail_export(
        self,
        domain: str,
        table_kind: str,
        filters: Mapping[str, Any] | None = None,
        *,
        active_run: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            spec = detail_table_spec(domain, table_kind)
        except ValueError as exc:
            return empty_detail_export(str(exc), domain=domain, table_kind=table_kind)
        normalized_filters = normalize_detail_filters(filters, domain=domain)
        active = dict(active_run or self.active_run())
        run_id = str(active.get("run_id") or "")
        if not self.config.use_database:
            return empty_detail_export(
                "database disabled; fixed local report fallback is disabled",
                domain=domain,
                table_kind=table_kind,
                table_name=spec["table"],
                filters=normalized_filters,
                run_id=run_id,
            )
        if not run_id:
            return empty_detail_export(
                "no active condition run available",
                domain=domain,
                table_kind=table_kind,
                table_name=spec["table"],
                filters=normalized_filters,
            )
        try:
            return self._condition_detail_export_from_db(
                domain=domain,
                table_kind=table_kind,
                filters=normalized_filters,
                run_id=run_id,
            )
        except Exception as exc:
            return empty_detail_export(
                f"postgres_unavailable:{exc}",
                domain=domain,
                table_kind=table_kind,
                table_name=spec["table"],
                filters=normalized_filters,
                run_id=run_id,
            )

    def dry_run_policy(self, policy_payload: str, source_trade_date: str | None = None) -> dict[str, Any]:
        policy = parse_policy_json(policy_payload)
        scope_policy = web_policy_to_scope_policy(policy)
        condition_pool_policy = web_policy_to_condition_pool_policy(policy)
        policy_hash = stable_policy_hash(policy)
        source_trade_date = source_trade_date or str(self.active_run().get("source_trade_date") or "")

        if not self.config.use_database:
            return {
                "ok": False,
                "error": "database disabled; fixed local report dry-run replay is disabled",
                "writes_performed": False,
                "minute_kline_pulled": False,
            }
        if not source_trade_date:
            return {
                "ok": False,
                "error": "no active source_trade_date available for N2 dry-run",
                "writes_performed": False,
                "minute_kline_pulled": False,
            }
        return self._dry_run_from_database(
            policy=policy,
            scope_policy=scope_policy,
            condition_pool_policy=condition_pool_policy,
            policy_hash=policy_hash,
            source_trade_date=source_trade_date,
        )

    def save_default_policy_draft(self, policy_payload: str) -> dict[str, Any]:
        policy = merge_web_policy(parse_policy_json(policy_payload))
        path = self.config.project_root / DEFAULT_POLICY_DRAFT_RELATIVE_PATH
        previous_artifact = load_policy_artifact(path)
        payload = self._policy_artifact_payload(
            policy,
            artifact_type="n2_web_policy_default_draft",
            previous_artifact=previous_artifact,
        )
        write_json_artifact(path, payload)
        return {
            "ok": True,
            "artifact_type": payload["artifact_type"],
            "policy_path": str(path),
            "policy_relative_path": DEFAULT_POLICY_DRAFT_RELATIVE_PATH.as_posix(),
            "policy_id": payload["policy_id"],
            "policy_version": payload["policy_version"],
            "policy_hash": payload["policy_hash"],
            "previous_policy_hash": payload["previous_policy_hash"],
            "policy_diff_summary": payload["policy_diff_summary"],
            "writes_performed": False,
            "database_written": False,
            "execute_authorized": False,
            "message": "默认策略草案已保存；N2 runner 会优先读取它，正式写库仍需 execute gate 和用户确认。",
        }

    def generate_execute_gate_draft(self, policy_payload: str, source_trade_date: str | None = None) -> dict[str, Any]:
        policy = merge_web_policy(parse_policy_json(policy_payload))
        saved = self.save_default_policy_draft(policy_json_text(policy))
        source_trade_date = source_trade_date or str(self.active_run().get("source_trade_date") or "")
        active_run = self.active_run_for_source_trade_date(source_trade_date)
        scope_policy = web_policy_to_scope_policy(policy)
        condition_pool_policy = web_policy_to_condition_pool_policy(policy)
        dry_run = self.dry_run_policy(policy_json_text(policy), source_trade_date=source_trade_date)
        proposed_run_id = proposed_policy_run_id(source_trade_date or "<source_trade_date>", active_run.get("run_id"))
        expected_rows = self._execute_gate_expected_rows(
            policy=policy,
            scope_policy=scope_policy,
            condition_pool_policy=condition_pool_policy,
            source_trade_date=source_trade_date,
        )
        command = n2_execute_command(
            source_trade_date or "<source_trade_date>",
            run_id=proposed_run_id,
            overwrite=bool(active_run.get("run_id")),
        )
        gate_pass = bool(dry_run.get("ok")) and int(dry_run.get("p0_count") or 0) == 0
        rollback_path = policy_gate_rollback_path(source_trade_date or "<source_trade_date>", proposed_run_id)
        rollback_full_path = self.config.project_root / rollback_path
        write_text_artifact(
            rollback_full_path,
            policy_gate_rollback_sql(
                rollback_run_id=proposed_run_id,
                restore_run_id=str(active_run.get("run_id") or ""),
            ),
        )
        result = {
            "ok": gate_pass,
            "artifact_type": "n2_web_policy_execute_gate_draft",
            "generated_at": utc_now_iso(),
            "gate_result": "PASS" if gate_pass else "BLOCKED",
            "proposed_run_id": proposed_run_id,
            "policy_hash": saved["policy_hash"],
            "policy_id": saved["policy_id"],
            "policy_version": saved["policy_version"],
            "previous_policy_hash": saved["previous_policy_hash"],
            "policy_source": POLICY_SOURCE_8782,
            "policy_diff_summary": saved["policy_diff_summary"],
            "policy_path": saved["policy_relative_path"],
            "policy_artifact_path": saved["policy_path"],
            "policy_relative_path": saved["policy_relative_path"],
            "source_trade_date": source_trade_date,
            "for_trade_date": dry_run.get("for_trade_date"),
            "prev_trade_date": dry_run.get("prev_trade_date"),
            "dry_run": dry_run,
            "expected_row_counts": expected_rows,
            "expected_rows": expected_rows,
            "active_lineage_plan": {
                "current_active_run_id": active_run.get("run_id"),
                "current_active_status": active_run.get("status"),
                "proposed_next_run_id": proposed_run_id,
                "overwrite": bool(active_run.get("run_id")),
                "overwrite_semantics": "lineage_supersede_only",
                "delete_previous_rows": False,
                "update_previous_rows": False,
                "mark_previous_run_superseded_after_postcheck": True,
                "n3_lineage_auto_switch": False,
            },
            "overwrite_semantics": "lineage_supersede_only",
            "n3_lineage_auto_switch": False,
            "rollback_sql_path": str(rollback_full_path),
            "rollback_sql_relative_path": str(rollback_path),
            "execute_allowed_candidate": gate_pass,
            "execute_command": command,
            "execute_command_candidate": command,
            "forbidden_scopes": [
                "common_event_outbox",
                "common_event_inbox",
                "common_event_consumer_checkpoint",
                "N3/N4/N5/N6",
                "market_data_pull",
                "worker",
                "old_system",
            ],
            "post_review_checklist": [
                "active passed run count = 1",
                "new run status = passed_active",
                "previous active run = superseded after postcheck",
                "common_event_outbox delta = 0",
                "N3 lineage auto switch = false",
                "policy_hash matches saved default draft",
            ],
            "n3_rebuild_required": True,
            "scope_delta_summary": scope_delta_summary_from_dry_run(dry_run),
            "writes_performed": False,
            "database_written": False,
            "execute_authorized": False,
            "next_gate_required": "N2 active run execute final gate with explicit user confirmation",
        }
        json_path = self.config.project_root / EXECUTE_GATE_DRAFT_JSON_RELATIVE_PATH
        md_path = self.config.project_root / EXECUTE_GATE_DRAFT_MD_RELATIVE_PATH
        write_json_artifact(json_path, result)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(execute_gate_markdown(result), encoding="utf-8")
        return {
            **result,
            "gate_json_path": str(json_path),
            "gate_markdown_path": str(md_path),
        }

    def regenerate_execute_gate_from_default_draft(self, *, source_trade_date: str | None = None) -> dict[str, Any]:
        artifact_path = self.config.project_root / DEFAULT_POLICY_DRAFT_RELATIVE_PATH
        artifact = load_policy_artifact(artifact_path)
        if not artifact:
            return {
                "ok": False,
                "gate_result": "BLOCKED",
                "blocked_reasons": ["default_policy_draft_missing"],
                "policy_path": DEFAULT_POLICY_DRAFT_RELATIVE_PATH.as_posix(),
                "writes_performed": False,
                "database_written": False,
                "execute_authorized": False,
            }
        policy = merge_web_policy(dict(artifact.get("web_policy") or default_web_policy()))
        source_trade_date = source_trade_date or str(self.active_run().get("source_trade_date") or "")
        active_run = self.active_run_for_source_trade_date(source_trade_date)
        return self._write_execute_gate_artifacts(
            policy=policy,
            policy_artifact=artifact,
            active_run=active_run,
            source_trade_date=source_trade_date,
        )

    def _write_execute_gate_artifacts(
        self,
        *,
        policy: Mapping[str, Any],
        policy_artifact: Mapping[str, Any],
        active_run: Mapping[str, Any],
        source_trade_date: str | None,
    ) -> dict[str, Any]:
        source_trade_date = source_trade_date or str(active_run.get("source_trade_date") or "")
        scope_policy = web_policy_to_scope_policy(policy)
        condition_pool_policy = web_policy_to_condition_pool_policy(policy)
        dry_run = self.dry_run_policy(policy_json_text(policy), source_trade_date=source_trade_date)
        proposed_run_id = proposed_policy_run_id(source_trade_date or "<source_trade_date>", active_run.get("run_id"))
        expected_rows = self._execute_gate_expected_rows(
            policy=policy,
            scope_policy=scope_policy,
            condition_pool_policy=condition_pool_policy,
            source_trade_date=source_trade_date,
        )
        command = n2_execute_command(
            source_trade_date or "<source_trade_date>",
            run_id=proposed_run_id,
            overwrite=bool(active_run.get("run_id")),
        )
        gate_pass = bool(dry_run.get("ok")) and int(dry_run.get("p0_count") or 0) == 0
        rollback_path = policy_gate_rollback_path(source_trade_date or "<source_trade_date>", proposed_run_id)
        rollback_full_path = self.config.project_root / rollback_path
        write_text_artifact(
            rollback_full_path,
            policy_gate_rollback_sql(
                rollback_run_id=proposed_run_id,
                restore_run_id=str(active_run.get("run_id") or ""),
            ),
        )
        result = {
            "ok": gate_pass,
            "artifact_type": "n2_web_policy_execute_gate_draft",
            "generated_at": utc_now_iso(),
            "gate_result": "PASS" if gate_pass else "BLOCKED",
            "proposed_run_id": proposed_run_id,
            "policy_hash": policy_artifact.get("policy_hash") or stable_policy_hash(policy),
            "policy_id": policy_artifact.get("policy_id") or DEFAULT_POLICY_ID,
            "policy_version": policy_artifact.get("policy_version") or "",
            "previous_policy_hash": policy_artifact.get("previous_policy_hash"),
            "policy_source": POLICY_SOURCE_8782,
            "policy_diff_summary": policy_artifact.get("policy_diff_summary") or {},
            "policy_path": DEFAULT_POLICY_DRAFT_RELATIVE_PATH.as_posix(),
            "policy_artifact_path": str(self.config.project_root / DEFAULT_POLICY_DRAFT_RELATIVE_PATH),
            "policy_relative_path": DEFAULT_POLICY_DRAFT_RELATIVE_PATH.as_posix(),
            "source_trade_date": source_trade_date,
            "for_trade_date": dry_run.get("for_trade_date"),
            "prev_trade_date": dry_run.get("prev_trade_date"),
            "dry_run": dry_run,
            "expected_row_counts": expected_rows,
            "expected_rows": expected_rows,
            "active_lineage_plan": {
                "current_active_run_id": active_run.get("run_id"),
                "current_active_status": active_run.get("status"),
                "proposed_next_run_id": proposed_run_id,
                "overwrite": bool(active_run.get("run_id")),
                "overwrite_semantics": "lineage_supersede_only",
                "delete_previous_rows": False,
                "update_previous_rows": False,
                "mark_previous_run_superseded_after_postcheck": True,
                "n3_lineage_auto_switch": False,
            },
            "overwrite_semantics": "lineage_supersede_only",
            "n3_lineage_auto_switch": False,
            "rollback_sql_path": str(rollback_full_path),
            "rollback_sql_relative_path": str(rollback_path),
            "execute_allowed_candidate": gate_pass,
            "execute_command": command,
            "execute_command_candidate": command,
            "forbidden_scopes": [
                "common_event_outbox",
                "common_event_inbox",
                "common_event_consumer_checkpoint",
                "N3/N4/N5/N6",
                "market_data_pull",
                "worker",
                "old_system",
            ],
            "post_review_checklist": [
                "active passed run count = 1",
                "new run status = passed_active",
                "previous active run = superseded after postcheck",
                "common_event_outbox delta = 0",
                "N3 lineage auto switch = false",
                "policy_hash matches saved default draft",
            ],
            "n3_rebuild_required": True,
            "scope_delta_summary": scope_delta_summary_from_dry_run(dry_run),
            "writes_performed": False,
            "database_written": False,
            "execute_authorized": False,
            "next_gate_required": "N2 active run execute final gate with explicit user confirmation",
        }
        json_path = self.config.project_root / EXECUTE_GATE_DRAFT_JSON_RELATIVE_PATH
        md_path = self.config.project_root / EXECUTE_GATE_DRAFT_MD_RELATIVE_PATH
        write_json_artifact(json_path, result)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(execute_gate_markdown(result), encoding="utf-8")
        return {
            **result,
            "gate_json_path": str(json_path),
            "gate_markdown_path": str(md_path),
        }

    def latest_execute_gate_artifact(self) -> dict[str, Any] | None:
        return load_policy_artifact(self.config.project_root / EXECUTE_GATE_DRAFT_JSON_RELATIVE_PATH)

    def overwrite_confirmation_model(self, *, source_trade_date: str | None = None) -> dict[str, Any]:
        gate = self.latest_execute_gate_artifact()
        policy_artifact = load_policy_artifact(self.config.project_root / DEFAULT_POLICY_DRAFT_RELATIVE_PATH)
        active_run = self.active_run()
        blocked_reasons: list[str] = []
        source_trade_date = str(source_trade_date or active_run.get("source_trade_date") or "")

        if not gate:
            blocked_reasons.append("latest_gate_missing")
            gate = {}
        if not policy_artifact:
            blocked_reasons.append("default_policy_draft_missing")
            policy_artifact = {}

        gate_result = str(gate.get("gate_result") or "")
        if gate and gate_result != "PASS":
            blocked_reasons.append("gate_result_not_pass")

        gate_policy_hash = str(gate.get("policy_hash") or "")
        current_policy_hash = str(policy_artifact.get("policy_hash") or "")
        if gate and policy_artifact and gate_policy_hash != current_policy_hash:
            blocked_reasons.append("policy_hash_mismatch")

        gate_source_trade_date = str(gate.get("source_trade_date") or "")
        if gate and source_trade_date and gate_source_trade_date != source_trade_date:
            blocked_reasons.append("source_trade_date_mismatch")

        lineage = dict(gate.get("active_lineage_plan") or {})
        expected_rows = dict(gate.get("expected_rows") or gate.get("expected_row_counts") or {})
        confirmation_enabled = not blocked_reasons
        return {
            "ok": confirmation_enabled,
            "confirmation_enabled": confirmation_enabled,
            "manual_confirm_status": "READY_FOR_SECOND_CONFIRM" if confirmation_enabled else "BLOCKED",
            "blocked_reasons": blocked_reasons,
            "gate_result": gate_result or "MISSING",
            "source_trade_date": source_trade_date,
            "gate_source_trade_date": gate_source_trade_date,
            "current_active_run_id": lineage.get("current_active_run_id") or active_run.get("run_id"),
            "proposed_run_id": gate.get("proposed_run_id") or lineage.get("proposed_next_run_id"),
            "policy_version": gate.get("policy_version") or policy_artifact.get("policy_version"),
            "policy_hash": gate_policy_hash or current_policy_hash,
            "current_policy_hash": current_policy_hash,
            "policy_diff_summary": gate.get("policy_diff_summary") or policy_artifact.get("policy_diff_summary") or {},
            "expected_rows": expected_rows,
            "rollback_sql_path": gate.get("rollback_sql_path"),
            "execute_command_candidate": gate.get("execute_command_candidate") or gate.get("execute_command"),
            "n3_rebuild_required": bool(gate.get("n3_rebuild_required", True)),
            "n3_lineage_auto_switch": bool(gate.get("n3_lineage_auto_switch", False)),
            "n4_n5_n6_auto_replay": False,
            "execute_authorized": False,
            "writes_performed": False,
            "database_written": False,
            "latest_gate_path": str(self.config.project_root / EXECUTE_GATE_DRAFT_JSON_RELATIVE_PATH),
            "policy_path": DEFAULT_POLICY_DRAFT_RELATIVE_PATH.as_posix(),
            "message": (
                "latest gate is ready for manual copy command confirmation"
                if confirmation_enabled
                else "latest gate is not eligible for overwrite confirmation"
            ),
        }

    def confirm_overwrite_gate(self, *, source_trade_date: str | None = None, confirmation_text: str = "") -> dict[str, Any]:
        model = self.overwrite_confirmation_model(source_trade_date=source_trade_date)
        token = confirmation_text.strip()
        expected_tokens = {
            str(model.get("proposed_run_id") or ""),
            str(model.get("policy_hash") or ""),
        }
        expected_tokens.discard("")
        if not model.get("confirmation_enabled"):
            return {**model, "ok": False, "manual_confirm_status": "BLOCKED"}
        if token not in expected_tokens:
            return {
                **model,
                "ok": False,
                "manual_confirm_status": "BLOCKED",
                "blocked_reasons": [*list(model.get("blocked_reasons") or []), "confirmation_text"],
                "message": "confirmation_text must equal proposed_run_id or policy_hash",
            }
        return {
            **model,
            "ok": True,
            "manual_confirm_status": "WAIT_MANUAL_CONFIRM",
            "confirmation_matched": "proposed_run_id" if token == model.get("proposed_run_id") else "policy_hash",
            "execute_authorized": False,
            "writes_performed": False,
            "database_written": False,
            "message": "Manual confirmation captured for copy-only command review; web console still does not execute N2.",
        }

    def _policy_artifact_payload(
        self,
        policy: Mapping[str, Any],
        *,
        artifact_type: str,
        previous_artifact: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        merged = merge_web_policy(policy)
        previous_policy = previous_artifact.get("web_policy") if previous_artifact else None
        created_at = utc_now_iso()
        return {
            "artifact_type": artifact_type,
            "generated_at": created_at,
            "source": POLICY_SOURCE_8782,
            "created_by": POLICY_SOURCE_8782,
            "created_at": created_at,
            "policy_id": str((previous_artifact or {}).get("policy_id") or DEFAULT_POLICY_ID),
            "policy_version": next_policy_version(previous_artifact),
            "policy_hash": stable_policy_hash(merged),
            "previous_policy_hash": (previous_artifact or {}).get("policy_hash"),
            "policy_diff_summary": policy_diff_summary(previous_policy, merged),
            "web_policy": normalize_db_value(merged),
            "scope_policy": normalize_db_value(web_policy_to_scope_policy(merged)),
            "condition_pool_policy": normalize_db_value(web_policy_to_condition_pool_policy(merged)),
            "writes_performed": False,
            "database_written": False,
            "execute_authorized": False,
        }

    def _execute_gate_expected_rows(
        self,
        *,
        policy: Mapping[str, Any],
        scope_policy: Mapping[str, Any],
        condition_pool_policy: Mapping[str, Any],
        source_trade_date: str | None,
    ) -> dict[str, Any]:
        if not self.config.use_database or not source_trade_date:
            return empty_execute_gate_expected_rows("database_unavailable")
        try:
            return self._execute_gate_expected_rows_from_database(
                scope_policy=scope_policy,
                condition_pool_policy=condition_pool_policy,
                source_trade_date=str(source_trade_date),
            )
        except Exception as exc:
            rows = empty_execute_gate_expected_rows(f"postgres_unavailable:{exc}")
            rows["error"] = str(exc)
            return rows

    def _execute_gate_expected_rows_from_database(
        self,
        *,
        scope_policy: Mapping[str, Any],
        condition_pool_policy: Mapping[str, Any],
        source_trade_date: str,
    ) -> dict[str, Any]:
        try:
            from scripts.check_condition_source_ready import run_check
        except ModuleNotFoundError:
            from check_condition_source_ready import run_check
        from ashare_v3.condition.basis import build_condition_basis_dry_run
        from ashare_v3.condition.execute import expected_rows_with_display
        from ashare_v3.condition.pool import build_condition_pool_dry_run
        from ashare_v3.condition.readiness_plan import build_condition_layer_execute_readiness_plan

        ready = run_check(self.config.dsn, source_trade_date)
        basis_report = build_condition_basis_dry_run(
            dsn=self.config.dsn,
            source_trade_date=source_trade_date,
            ready_check=ready,
        )
        pool_report = build_condition_pool_dry_run(
            dsn=self.config.dsn,
            source_trade_date=source_trade_date,
            ready_check=ready,
            condition_pool_policy=condition_pool_policy,
        )
        scope_report = build_minute_target_scope_dry_run(
            dsn=self.config.dsn,
            source_trade_date=source_trade_date,
            ready_check=ready,
            scope_policy=scope_policy,
            condition_pool_policy=condition_pool_policy,
        )
        readiness_plan = build_condition_layer_execute_readiness_plan(
            basis_report=basis_report,
            pool_report=pool_report,
            scope_report=scope_report,
        )
        display_report = build_policy_gate_display_preview(
            planned_run_id=str(readiness_plan["planned_run_id"]),
            basis_report=basis_report,
            pool_report=pool_report,
            scope_report=scope_report,
        )
        display_counts = {
            domain: int(display_report["display_preview"][domain]["row_count"])
            for domain in POLICY_DOMAINS
        }
        expected = expected_rows_with_display(
            readiness_plan["would_write"],
            display_quality_item_count=policy_gate_display_quality_item_count(display_report),
            display_row_counts=display_counts,
        )
        return gate_expected_rows_from_execute_counts(expected)

    def _active_run_from_db(self, *, source_trade_date: str | None = None) -> dict[str, Any] | None:
        with psycopg.connect(
            self.config.dsn,
            connect_timeout=3,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.common_condition_run') AS regclass")
            if cur.fetchone()["regclass"] is None:
                return None
            source_clause = " AND source_trade_date = %s" if source_trade_date else ""
            params = [source_trade_date] if source_trade_date else []
            cur.execute(
                """
                SELECT run_id, status, source_trade_date, for_trade_date, prev_trade_date,
                       source_versions, p0_count, p1_count, p2_count,
                       started_at, finished_at, created_at
                FROM common_condition_run
                WHERE status IN (""" + active_status_sql_list() + """)
                """ + source_clause + """
                ORDER BY """ + active_status_order_sql("status") + """,
                         finished_at DESC NULLS LAST,
                         created_at DESC
                LIMIT 1
                """,
                params,
            )
            row = cur.fetchone()
        return normalize_db_row(row) if row else None

    def _pool_scope_summaries_from_db(self, run_id: str) -> dict[str, Any]:
        domains: dict[str, Any] = {}
        table_specs = {
            "index": ("index_condition_pool", "index_minute_target_scope", "index_identity_key"),
            "board": ("board_condition_pool", "board_minute_target_scope", "board_identity_key"),
            "stock": ("stock_condition_pool", "stock_minute_target_scope", "stock_identity_key"),
        }
        with psycopg.connect(
            self.config.dsn,
            connect_timeout=3,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            for domain, (pool_table, scope_table, identity_column) in table_specs.items():
                domains[domain] = {
                    "pool": self._table_count(cur, pool_table, identity_column, run_id),
                    "scope": self._table_count(cur, scope_table, identity_column, run_id),
                }
        return domains

    def _index_object_options_from_db(self, run_id: str) -> list[dict[str, str]]:
        with psycopg.connect(
            self.config.dsn,
            connect_timeout=3,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.index_condition_basis') AS regclass")
            if cur.fetchone()["regclass"] is None:
                return default_index_object_options()
            cur.execute(
                """
                SELECT DISTINCT index_identity_key, code, name
                FROM index_condition_basis
                WHERE run_id = %s
                ORDER BY code, index_identity_key
                """,
                (run_id,),
            )
            rows = cur.fetchall()
        return [
            {
                "identity_key": str(row["index_identity_key"]),
                "label": f"{row['index_identity_key']} · {row.get('name') or row.get('code') or ''}".strip(),
            }
            for row in rows
            if row.get("index_identity_key")
        ]

    def _table_count(self, cur: Any, table_name: str, identity_column: str, run_id: str) -> dict[str, Any]:
        cur.execute("SELECT to_regclass(%s) AS regclass", (f"public.{table_name}",))
        if cur.fetchone()["regclass"] is None:
            return {"table": table_name, "exists": False, "row_count": 0, "object_count": 0}
        cur.execute(
            f"""
            SELECT count(*)::bigint AS row_count,
                   count(DISTINCT {identity_column})::bigint AS object_count,
                   count(*) FILTER (WHERE direction = 'buy')::bigint AS buy_count,
                   count(*) FILTER (WHERE direction = 'sell')::bigint AS sell_count
            FROM {table_name}
            WHERE run_id = %s
            """,
            (run_id,),
        )
        return {"table": table_name, "exists": True, **normalize_db_row(cur.fetchone())}

    def _baseline_gate_summary_from_db(self, run_id: str) -> dict[str, Any]:
        domains: dict[str, Any] = {}
        table_specs = {
            "index": ("index_identity_key", "index_condition_basis", "index_condition_pool", "index_minute_target_scope"),
            "board": ("board_identity_key", "board_condition_basis", "board_condition_pool", "board_minute_target_scope"),
            "stock": ("stock_identity_key", "stock_condition_basis", "stock_condition_pool", "stock_minute_target_scope"),
        }
        with psycopg.connect(
            self.config.dsn,
            connect_timeout=3,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            for domain, (identity_column, basis_table, pool_table, scope_table) in table_specs.items():
                domains[domain] = {
                    "basis": self._baseline_table_summary(cur, basis_table, run_id, has_condition_key=False),
                    "pool": self._baseline_table_summary(cur, pool_table, run_id, has_condition_key=True),
                    "scope": self._baseline_table_summary(cur, scope_table, run_id, has_condition_key=True),
                }
                if domain == "index":
                    domains[domain]["fixed_9_scope_ready_object_count"] = self._fixed_index_baseline_ready_count(
                        cur,
                        table_name=scope_table,
                        identity_column=identity_column,
                        run_id=run_id,
                    )
        total_required_not_ready = sum(
            int(domains[domain][stage].get("required_period_not_ready_rows") or 0)
            for domain in POLICY_DOMAINS
            for stage in ("pool", "scope")
        )
        total_missing = sum(
            int(domains[domain][stage].get("baseline_missing_rows") or 0)
            for domain in POLICY_DOMAINS
            for stage in DETAIL_TABLE_KINDS
        )
        return {
            "source": "postgres_read_only",
            "status": "passed" if total_required_not_ready == 0 and total_missing == 0 else "needs_review",
            "domains": domains,
            "required_period_not_ready_rows": total_required_not_ready,
            "baseline_missing_rows": total_missing,
            "fixed_9_index_expected": len(DEFAULT_INDEX_IDENTITIES),
        }

    def _baseline_table_summary(
        self,
        cur: Any,
        table_name: str,
        run_id: str,
        *,
        has_condition_key: bool,
    ) -> dict[str, Any]:
        cur.execute("SELECT to_regclass(%s) AS regclass", (f"public.{table_name}",))
        if cur.fetchone()["regclass"] is None:
            return {"table": table_name, "exists": False, "row_count": 0, "baseline_column": False}
        if not self._table_has_column(cur, table_name, "period_trigger_baseline_json"):
            return {"table": table_name, "exists": True, "row_count": 0, "baseline_column": False}
        missing = _baseline_json_missing_expr("t")
        any_not_ready = _baseline_any_not_ready_expr("t")
        required_not_ready = _required_period_not_ready_expr("t", has_condition_key=has_condition_key)
        cur.execute(
            f"""
            SELECT count(*)::bigint AS row_count,
                   count(*) FILTER (WHERE {missing})::bigint AS baseline_missing_rows,
                   count(*) FILTER (WHERE NOT ({missing}) AND ({any_not_ready}))::bigint AS baseline_partial_rows,
                   count(*) FILTER (WHERE NOT ({missing}) AND NOT ({any_not_ready}))::bigint AS baseline_ready_rows,
                   count(*) FILTER (WHERE {required_not_ready})::bigint AS required_period_not_ready_rows
            FROM {table_name} t
            WHERE t.run_id = %s
            """,
            (run_id,),
        )
        return {
            "table": table_name,
            "exists": True,
            "baseline_column": True,
            **normalize_db_row(cur.fetchone()),
        }

    def _fixed_index_baseline_ready_count(
        self,
        cur: Any,
        *,
        table_name: str,
        identity_column: str,
        run_id: str,
    ) -> int:
        if not self._table_has_column(cur, table_name, "period_trigger_baseline_json"):
            return 0
        required_not_ready = _required_period_not_ready_expr("t", has_condition_key=True)
        cur.execute(
            f"""
            SELECT count(DISTINCT {identity_column})::bigint AS object_count
            FROM {table_name} t
            WHERE t.run_id = %s
              AND t.{identity_column} = ANY(%s)
              AND NOT ({_baseline_json_missing_expr('t')})
              AND NOT ({required_not_ready})
            """,
            (run_id, list(DEFAULT_INDEX_IDENTITIES)),
        )
        return int((cur.fetchone() or {}).get("object_count") or 0)

    def _table_has_column(self, cur: Any, table_name: str, column_name: str) -> bool:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = %s
            LIMIT 1
            """,
            (table_name, column_name),
        )
        return cur.fetchone() is not None

    def _condition_detail_from_db(
        self,
        *,
        domain: str,
        table_kind: str,
        filters: Mapping[str, Any],
        run_id: str,
    ) -> dict[str, Any]:
        query = detail_query_parts(domain, table_kind, filters, run_id=run_id)
        spec = query["spec"]
        with psycopg.connect(
            self.config.dsn,
            connect_timeout=3,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s) AS regclass", (f"public.{spec['table']}",))
            if cur.fetchone()["regclass"] is None:
                return empty_detail(
                    f"table not found: {spec['table']}",
                    domain=domain,
                    table_kind=table_kind,
                    table_name=spec["table"],
                    filters=filters,
                    run_id=run_id,
                )
            cur.execute(query["count_sql"], query["count_params"])
            total_count = int((cur.fetchone() or {}).get("row_count") or 0)
            cur.execute(query["data_sql"], query["data_params"])
            columns = [getattr(item, "name", item[0]) for item in cur.description or []]
            rows = [normalize_db_row(row) for row in cur.fetchall()]
        rows = enrich_detail_rows_with_baseline(rows, table_kind)
        columns = detail_columns_with_baseline(columns, rows)
        display_columns = [column for column in columns if column not in DETAIL_OMITTED_COLUMNS]
        visible_columns = detail_visible_columns(domain, table_kind, display_columns)
        visible_rows = [
            {key: value for key, value in row.items() if key in visible_columns}
            for row in rows
        ]
        pagination_enabled = bool(query["pagination_enabled"])
        page_size = int(filters["page_size"]) if pagination_enabled else max(total_count, 1)
        page = int(filters["page"]) if pagination_enabled else 1
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        return {
            "ok": True,
            "source": "postgres_read_only",
            "run_id": run_id,
            "domain": domain,
            "domain_label": DETAIL_DOMAIN_LABELS[domain],
            "table_kind": table_kind,
            "table_label": DETAIL_TABLE_LABELS[table_kind],
            "table_name": spec["table"],
            "filters": normalize_db_value(dict(filters)),
            "columns": visible_columns,
            "baseline_counts": detail_baseline_counts(visible_rows),
            "all_column_count": len(display_columns),
            "hidden_column_count": max(len(display_columns) - len(visible_columns), 0),
            "rows": visible_rows,
            "total_count": total_count,
            "shown_count": len(visible_rows),
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_prev": pagination_enabled and page > 1,
            "has_next": pagination_enabled and page < total_pages,
            "pagination_enabled": pagination_enabled,
            "writes_performed": False,
            "minute_kline_pulled": False,
        }

    def _condition_detail_export_from_db(
        self,
        *,
        domain: str,
        table_kind: str,
        filters: Mapping[str, Any],
        run_id: str,
    ) -> dict[str, Any]:
        query = detail_query_parts(domain, table_kind, filters, run_id=run_id, paginate=False)
        spec = query["spec"]
        with psycopg.connect(
            self.config.dsn,
            connect_timeout=3,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s) AS regclass", (f"public.{spec['table']}",))
            if cur.fetchone()["regclass"] is None:
                return empty_detail_export(
                    f"table not found: {spec['table']}",
                    domain=domain,
                    table_kind=table_kind,
                    table_name=spec["table"],
                    filters=filters,
                    run_id=run_id,
                )
            cur.execute(query["count_sql"], query["count_params"])
            total_count = int((cur.fetchone() or {}).get("row_count") or 0)
            if total_count > DETAIL_EXPORT_MAX_ROWS:
                return empty_detail_export(
                    f"export row count {total_count} exceeds max {DETAIL_EXPORT_MAX_ROWS}; tighten filters first",
                    domain=domain,
                    table_kind=table_kind,
                    table_name=spec["table"],
                    filters=filters,
                    run_id=run_id,
                )
            cur.execute(query["data_sql"], query["data_params"])
            columns = [getattr(item, "name", item[0]) for item in cur.description or []]
            rows = [normalize_db_row(row) for row in cur.fetchall()]

        rows = enrich_detail_rows_with_baseline(rows, table_kind)
        columns = detail_columns_with_baseline(columns, rows)
        export_columns = [column for column in columns if column not in DETAIL_OMITTED_COLUMNS]
        export_rows = [
            {key: value for key, value in row.items() if key in export_columns}
            for row in rows
        ]
        filename = detail_export_filename(domain=domain, table_kind=table_kind, run_id=run_id)
        content = build_detail_export_xlsx(
            metadata={
                "domain": domain,
                "table_kind": table_kind,
                "table_name": spec["table"],
                "run_id": run_id,
                "total_count": total_count,
                "exported_count": len(export_rows),
                "filters": normalize_db_value(dict(filters)),
                "writes_performed": False,
                "minute_kline_pulled": False,
            },
            columns=export_columns,
            rows=export_rows,
        )
        return {
            "ok": True,
            "source": "postgres_read_only",
            "run_id": run_id,
            "domain": domain,
            "table_kind": table_kind,
            "table_name": spec["table"],
            "filters": normalize_db_value(dict(filters)),
            "filename": filename,
            "content": content,
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "total_count": total_count,
            "exported_count": len(export_rows),
            "writes_performed": False,
            "minute_kline_pulled": False,
        }

    def _dry_run_from_database(
        self,
        *,
        policy: Mapping[str, Any],
        scope_policy: Mapping[str, Any],
        condition_pool_policy: Mapping[str, Any],
        policy_hash: str,
        source_trade_date: str,
    ) -> dict[str, Any]:
        try:
            try:
                from scripts.check_condition_source_ready import run_check
            except ModuleNotFoundError:
                from check_condition_source_ready import run_check
        except Exception as exc:
            return {"ok": False, "db_warning": f"source ready check import failed: {exc}"}

        try:
            ready = run_check(self.config.dsn, source_trade_date)
        except Exception as exc:
            return {"ok": False, "db_warning": f"database dry-run unavailable: {exc}"}
        if not ready.get("passed"):
            return build_n1_blocker(ready)
        try:
            report = build_minute_target_scope_dry_run(
                dsn=self.config.dsn,
                source_trade_date=source_trade_date,
                ready_check=ready,
                scope_policy=scope_policy,
                condition_pool_policy=condition_pool_policy,
            )
        except Exception as exc:
            return {"ok": False, "db_warning": f"database dry-run failed: {exc}"}
        return dry_run_response_from_scope_report(
            report=report,
            policy=policy,
            policy_hash=policy_hash,
            source="postgres_read_only",
        )



def dry_run_response_from_scope_report(
    *,
    report: Mapping[str, Any],
    policy: Mapping[str, Any],
    policy_hash: str,
    source: str,
) -> dict[str, Any]:
    diagnostics = dict(report.get("scope_policy", {}).get("diagnostics") or {})
    scope_preview = dict(report.get("scope_preview") or {})
    domains: dict[str, Any] = {}
    for domain in POLICY_DOMAINS:
        item = dict(diagnostics.get(domain) or {})
        preview = dict(scope_preview.get(domain) or {})
        reason_counts = item.get("excluded_reason_counts", {})
        baseline_reason_count = int(reason_counts.get("missing_period_trigger_baseline") or 0)
        domains[domain] = {
            "candidate_count": item.get("candidate_count", 0),
            "selected_count": item.get("selected_count", 0),
            "excluded_count": item.get("excluded_count", 0),
            "reason_counts": reason_counts,
            "excluded_reason_counts": reason_counts,
            "selected_reason_counts": item.get("selected_reason_counts", {}),
            "selected_samples": item.get("selected_samples", []),
            "excluded_samples": item.get("excluded_samples", []),
            "distribution": item.get("distribution", {}),
            "pool": {
                "row_count": preview.get("condition_pool_row_count", 0),
                "object_count": preview.get("object_count", 0),
            },
            "scope": {
                "row_count": preview.get("scope_row_count", item.get("selected_count", 0)),
                "object_count": preview.get("object_count", 0),
            },
            "baseline_gate": {
                "excluded_missing_period_trigger_baseline": baseline_reason_count,
                "required_period_not_ready_count": baseline_reason_count,
            },
            "candidate_scope_row_count": preview.get("candidate_scope_row_count", item.get("candidate_count", 0)),
        }
    quality = dict(report.get("quality") or {})
    baseline_gate = dry_run_baseline_gate_from_report(report, domains)
    return {
        "ok": True,
        "source": source,
        "mode": "dry_run",
        "writes_performed": False,
        "minute_kline_pulled": False,
        "run_id": report.get("run_id"),
        "source_trade_date": report.get("source_trade_date"),
        "for_trade_date": report.get("for_trade_date"),
        "prev_trade_date": report.get("prev_trade_date"),
        "policy_name": policy.get("policy_name"),
        "policy_hash": policy_hash,
        "domains": domains,
        "quality": quality,
        "baseline_gate": baseline_gate,
        "p0_count": int(quality.get("p0_count") or 0),
        "p1_count": int(quality.get("p1_count") or 0),
        "p2_count": int(quality.get("p2_count") or 0),
    }


def dry_run_baseline_gate_from_report(
    report: Mapping[str, Any],
    domains: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    quality_items = list(dict(report.get("quality") or {}).get("items") or [])
    baseline_items = [
        item
        for item in quality_items
        if "period_trigger_baseline" in str(item.get("gate_code") or item.get("code") or item.get("name") or "")
        or "required_period_not_ready" in str(item.get("gate_code") or item.get("code") or item.get("name") or "")
    ]
    domain_counts = {
        domain: {
            "required_period_not_ready_count": int(item.get("baseline_gate", {}).get("required_period_not_ready_count") or 0),
            "excluded_missing_period_trigger_baseline": int(
                item.get("baseline_gate", {}).get("excluded_missing_period_trigger_baseline") or 0
            ),
        }
        for domain, item in domains.items()
    }
    required_period_not_ready_count = sum(
        item["required_period_not_ready_count"]
        for item in domain_counts.values()
    )
    failed_quality_items = [
        item
        for item in baseline_items
        if str(item.get("status") or "").lower() in {"failed", "fail", "blocked"}
        or int(item.get("fail_count") or item.get("failed_count") or 0) > 0
    ]
    return {
        "status": "passed" if required_period_not_ready_count == 0 and not failed_quality_items else "needs_review",
        "required_period_not_ready_count": required_period_not_ready_count,
        "domains": domain_counts,
        "quality_items": baseline_items,
        "failed_quality_count": len(failed_quality_items),
    }


def build_n1_blocker(ready_check: Mapping[str, Any]) -> dict[str, Any]:
    missing = list(ready_check.get("missing_data_types") or [])
    failed = [
        {
            "data_type": item.get("data_type"),
            "failure_reasons": item.get("failure_reasons") or [],
        }
        for item in ready_check.get("checks") or []
        if not item.get("passed")
    ]
    evidence = []
    if missing:
        evidence.append(f"missing_data_types={missing}")
    if failed:
        evidence.append(f"failed_checks={failed[:5]}")
    prompt = "\n".join(
        [
            "blocked_by_layer=N1_ingestion",
            "source_layer=N2_condition",
            f"证据：{'; '.join(evidence) if evidence else 'condition source ready check failed'}",
            "建议下一步：切换到 layer_role=N1_ingestion，补齐 active source_version 或对应 fact/identity quality gate 后，再回到 N2 dry-run。",
            "禁止本层继续做：不得在 N2 外拉行情、修 N1 fact、写 ingest 表或绕过 condition_pool。",
        ]
    )
    return {
        "ok": False,
        "blocked_by_layer": "N1_ingestion",
        "source_layer": "N2_condition",
        "evidence": evidence,
        "handoff_prompt": prompt,
        "ready_check": dict(ready_check),
    }


def unavailable_active_run(reason: str) -> dict[str, Any]:
    return {
        "run_id": None,
        "status": "unavailable",
        "source_trade_date": None,
        "for_trade_date": None,
        "prev_trade_date": None,
        "source_versions": {},
        "policy_name": None,
        "policy_hash": None,
        "p0_count": None,
        "p1_count": None,
        "p2_count": None,
        "source": "postgres_unavailable",
        "db_warning": reason,
    }


def empty_summary(source: str) -> dict[str, Any]:
    empty_counts = {
        "exists": False,
        "row_count": 0,
        "object_count": 0,
        "buy_count": 0,
        "sell_count": 0,
        "selected_count": None,
        "excluded_count": None,
        "excluded_reason_counts": {},
    }
    return {
        "source": source,
        "domains": {
            domain: {"pool": dict(empty_counts), "scope": dict(empty_counts)}
            for domain in POLICY_DOMAINS
        },
    }


def empty_baseline_gate_summary(source: str) -> dict[str, Any]:
    empty_stage = {
        "exists": False,
        "baseline_column": False,
        "row_count": 0,
        "baseline_missing_rows": 0,
        "baseline_partial_rows": 0,
        "baseline_ready_rows": 0,
        "required_period_not_ready_rows": 0,
    }
    return {
        "source": source,
        "status": "unavailable",
        "domains": {
            domain: {stage: dict(empty_stage) for stage in DETAIL_TABLE_KINDS}
            for domain in POLICY_DOMAINS
        },
        "required_period_not_ready_rows": 0,
        "baseline_missing_rows": 0,
        "fixed_9_index_expected": len(DEFAULT_INDEX_IDENTITIES),
    }


def empty_detail(
    source: str,
    *,
    domain: str = "index",
    table_kind: str = "basis",
    table_name: str | None = None,
    filters: Mapping[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    normalized_filters = normalize_detail_filters(filters, domain=domain)
    return {
        "ok": False,
        "source": source,
        "run_id": run_id,
        "domain": domain,
        "domain_label": DETAIL_DOMAIN_LABELS.get(domain, domain),
        "table_kind": table_kind,
        "table_label": DETAIL_TABLE_LABELS.get(table_kind, table_kind),
        "table_name": table_name or "",
        "filters": normalize_db_value(dict(normalized_filters)),
        "columns": [],
        "baseline_counts": detail_baseline_counts([]),
        "all_column_count": 0,
        "hidden_column_count": 0,
        "rows": [],
        "total_count": 0,
        "shown_count": 0,
        "page": int(normalized_filters.get("page") or 1),
        "page_size": int(normalized_filters.get("page_size") or DETAIL_STOCK_PAGE_SIZE),
        "total_pages": 1,
        "has_prev": False,
        "has_next": False,
        "pagination_enabled": domain == "stock",
        "writes_performed": False,
        "minute_kline_pulled": False,
    }


def empty_detail_export(
    source: str,
    *,
    domain: str = "index",
    table_kind: str = "basis",
    table_name: str | None = None,
    filters: Mapping[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    normalized_filters = normalize_detail_filters(filters, domain=domain)
    return {
        "ok": False,
        "source": source,
        "run_id": run_id,
        "domain": domain,
        "domain_label": DETAIL_DOMAIN_LABELS.get(domain, domain),
        "table_kind": table_kind,
        "table_label": DETAIL_TABLE_LABELS.get(table_kind, table_kind),
        "table_name": table_name or "",
        "filters": normalize_db_value(dict(normalized_filters)),
        "filename": "",
        "total_count": 0,
        "exported_count": 0,
        "writes_performed": False,
        "minute_kline_pulled": False,
    }


def detail_export_filename(*, domain: str, table_kind: str, run_id: str | None) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_token = re.sub(r"[^A-Za-z0-9_-]+", "_", run_id or "active")[:80].strip("_") or "active"
    return f"n2_{domain}_{table_kind}_{run_token}_{timestamp}.xlsx"


def build_detail_export_xlsx(
    *,
    metadata: Mapping[str, Any],
    columns: list[str],
    rows: list[Mapping[str, Any]],
) -> bytes:
    exported_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    metadata_rows = [
        ["export_type", "N2 condition detail"],
        ["domain", metadata.get("domain", ""), "table_kind", metadata.get("table_kind", "")],
        ["table_name", metadata.get("table_name", ""), "run_id", metadata.get("run_id", "")],
        ["total_count", metadata.get("total_count", 0), "exported_count", metadata.get("exported_count", len(rows))],
        ["exported_at", exported_at],
        ["writes_performed", metadata.get("writes_performed", False), "minute_kline_pulled", metadata.get("minute_kline_pulled", False)],
        ["filters_json", json.dumps(metadata.get("filters") or {}, ensure_ascii=False, sort_keys=True, default=str)],
    ]
    matrix: list[list[Any]] = [*metadata_rows, [], list(columns)]
    matrix.extend([[row.get(column, "") for column in columns] for row in rows])
    header_row = len(metadata_rows) + 2
    return _xlsx_from_matrix(matrix=matrix, sheet_name="N2_detail", header_row=header_row)


_INVALID_XML_CHARS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


def _xlsx_from_matrix(*, matrix: list[list[Any]], sheet_name: str, header_row: int) -> bytes:
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    max_columns = max((len(row) for row in matrix), default=1)
    max_rows = max(len(matrix), 1)
    dimension = f"A1:{_xlsx_col_ref(max_columns)}{max_rows}"
    sheet_xml = _worksheet_xml(matrix=matrix, dimension=dimension, header_row=header_row)
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{_xml_text(_safe_sheet_name(sheet_name))}" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )
    core_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:creator>ashare_v3</dc:creator>'
        '<cp:lastModifiedBy>ashare_v3</cp:lastModifiedBy>'
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{created_at}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created_at}</dcterms:modified>'
        '</cp:coreProperties>'
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml())
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("docProps/app.xml", _app_xml())
        archive.writestr("docProps/core.xml", core_xml)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml())
        archive.writestr("xl/styles.xml", _styles_xml())
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return buffer.getvalue()


def _worksheet_xml(*, matrix: list[list[Any]], dimension: str, header_row: int) -> str:
    rows_xml = []
    for row_index, row in enumerate(matrix, start=1):
        cells = "".join(
            _cell_xml(row_index=row_index, col_index=col_index, value=value)
            for col_index, value in enumerate(row, start=1)
        )
        rows_xml.append(f'<row r="{row_index}">{cells}</row>')
    max_columns = max((len(row) for row in matrix), default=1)
    max_rows = max(len(matrix), 1)
    cols_xml = "".join(
        f'<col min="{idx}" max="{idx}" width="{width}" customWidth="1"/>'
        for idx, width in enumerate(_column_widths(matrix, max_columns), start=1)
    )
    auto_filter = (
        f'<autoFilter ref="A{header_row}:{_xlsx_col_ref(max_columns)}{max_rows}"/>'
        if max_rows >= header_row and max_columns > 0
        else ""
    )
    freeze_top_left = f"A{header_row + 1}"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<dimension ref="{dimension}"/>'
        '<sheetViews><sheetView workbookViewId="0">'
        f'<pane ySplit="{header_row}" topLeftCell="{freeze_top_left}" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        f'<cols>{cols_xml}</cols>'
        f'<sheetData>{"".join(rows_xml)}</sheetData>'
        f'{auto_filter}'
        '</worksheet>'
    )


def _cell_xml(*, row_index: int, col_index: int, value: Any) -> str:
    cell_ref = f"{_xlsx_col_ref(col_index)}{row_index}"
    text = _xlsx_cell_text(value)
    if text == "":
        return f'<c r="{cell_ref}"/>'
    preserve = ' xml:space="preserve"' if text != text.strip() else ""
    return f'<c r="{cell_ref}" t="inlineStr"><is><t{preserve}>{_xml_text(text)}</t></is></c>'


def _xlsx_cell_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (list, dict)):
        text = json.dumps(value, ensure_ascii=False, default=str)
    else:
        text = str(value)
    text = _INVALID_XML_CHARS.sub("", text)
    if len(text) > 32_000:
        text = f"{text[:32_000]}...[truncated]"
    return text


def _xml_text(value: str) -> str:
    return escape(_INVALID_XML_CHARS.sub("", str(value)), {'"': "&quot;"})


def _xlsx_col_ref(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result or "A"


def _column_widths(matrix: list[list[Any]], max_columns: int) -> list[int]:
    widths: list[int] = []
    sample = matrix[:200]
    for col_index in range(max_columns):
        max_len = max((len(_xlsx_cell_text(row[col_index])) for row in sample if col_index < len(row)), default=8)
        widths.append(min(max(max_len + 2, 10), 42))
    return widths


def _safe_sheet_name(value: str) -> str:
    cleaned = re.sub(r"[\[\]:*?/\\]+", "_", value).strip("'")[:31]
    return cleaned or "Sheet1"


def _content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '</Types>'
    )


def _root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        '</Relationships>'
    )


def _workbook_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '</Relationships>'
    )


def _app_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>ashare_v3</Application>'
        '</Properties>'
    )


def _styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    )


def normalize_db_row(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    output: dict[str, Any] = {}
    for key, value in dict(row).items():
        output[key] = normalize_db_value(value)
    return output


def proposed_policy_run_id(source_trade_date: str, current_active_run_id: Any = None) -> str:
    source = str(source_trade_date or "<source_trade_date>")
    current = str(current_active_run_id or "")
    pattern = re.compile(rf"^condition_layer_{re.escape(source)}_source_{re.escape(source)}_v(\d+)$")
    match = pattern.fullmatch(current)
    version = int(match.group(1)) + 1 if match else 1
    return f"condition_layer_{source}_source_{source}_v{version}"


def policy_gate_rollback_path(source_trade_date: str, proposed_run_id: str) -> Path:
    safe_source = re.sub(r"[^0-9A-Za-z_]+", "_", str(source_trade_date or "unknown")).strip("_") or "unknown"
    version_match = re.fullmatch(
        rf"condition_layer_{re.escape(safe_source)}_source_{re.escape(safe_source)}_v(\d+)",
        str(proposed_run_id or ""),
    )
    if version_match:
        return Path("sql") / f"N2_condition_layer_{safe_source}_v{version_match.group(1)}_web_policy_rollback.sql"
    safe_run_id = re.sub(r"[^0-9A-Za-z_]+", "_", str(proposed_run_id or "run")).strip("_") or "run"
    return Path("sql") / f"N2_condition_layer_{safe_source}_{safe_run_id}_rollback.sql"


def policy_gate_rollback_sql(*, rollback_run_id: str, restore_run_id: str) -> str:
    rollback_id = sql_literal(rollback_run_id)
    restore_id = sql_literal(restore_run_id)
    return f"""-- Rollback draft for N2 web policy execute gate.
-- Do not execute without explicit user confirmation.
--
-- Scope:
--   Delete only {rollback_run_id} rows.
--   Restore {restore_run_id or '<previous_active_run_id>'} to passed_active.
--
-- Boundary:
--   Does not touch N1 source_version.
--   Does not touch common_event_outbox / common_event_inbox / common_event_consumer_checkpoint.
--   Does not touch N3/N4/N5/N6 business rows.
--   Blocks if {rollback_run_id} already has event infra or downstream N3/N4/N5/N6 refs.

BEGIN;

DO $$
DECLARE
  rollback_run_id text := {rollback_id};
  restore_run_id text := {restore_id};
  event_refs bigint := 0;
  downstream_refs bigint := 0;
BEGIN
  SELECT
      COALESCE((SELECT count(*) FROM common_event_outbox WHERE source_run_id = rollback_run_id OR payload_json::text LIKE '%' || rollback_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_event_inbox WHERE source_run_id = rollback_run_id OR payload_json::text LIKE '%' || rollback_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_event_consumer_checkpoint WHERE COALESCE(checkpoint_payload::text, '') LIKE '%' || rollback_run_id || '%'), 0)
  INTO event_refs;

  IF event_refs > 0 THEN
    RAISE EXCEPTION 'rollback blocked: event infra refs exist for % (% rows)', rollback_run_id, event_refs;
  END IF;

  SELECT
      COALESCE((SELECT count(*) FROM common_market_data_run WHERE source_condition_run_id = rollback_run_id OR run_id LIKE '%' || rollback_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_trigger_run WHERE source_condition_run_id = rollback_run_id OR run_id LIKE '%' || rollback_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_action_run WHERE source_condition_run_id = rollback_run_id OR run_id LIKE '%' || rollback_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM user_projection_run WHERE source_display_condition_run_id = rollback_run_id OR user_projection_run_id LIKE '%' || rollback_run_id || '%'), 0)
    + COALESCE((
        SELECT count(*)
        FROM user_signal_projection
        WHERE source_condition_display_run_id = rollback_run_id
           OR source_condition_display_basis_id IN (
                SELECT stock_condition_display_basis_id FROM stock_condition_display_basis WHERE run_id = rollback_run_id
                UNION ALL
                SELECT index_condition_display_basis_id FROM index_condition_display_basis WHERE run_id = rollback_run_id
                UNION ALL
                SELECT board_condition_display_basis_id FROM board_condition_display_basis WHERE run_id = rollback_run_id
           )
      ), 0)
  INTO downstream_refs;

  IF downstream_refs > 0 THEN
    RAISE EXCEPTION 'rollback blocked: downstream N3/N4/N5/N6 refs exist for % (% rows)', rollback_run_id, downstream_refs;
  END IF;

  IF restore_run_id = '' THEN
    RAISE EXCEPTION 'rollback blocked: restore_run_id is empty';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM common_condition_run
    WHERE run_id = restore_run_id
      AND status IN ('superseded', 'passed_active', 'passed')
  ) THEN
    RAISE EXCEPTION 'rollback blocked: prior run % is not restorable', restore_run_id;
  END IF;
END $$;

DELETE FROM stock_condition_display_basis WHERE run_id = {rollback_id};
DELETE FROM index_condition_display_basis WHERE run_id = {rollback_id};
DELETE FROM board_condition_display_basis WHERE run_id = {rollback_id};

DELETE FROM stock_minute_target_scope WHERE run_id = {rollback_id};
DELETE FROM index_minute_target_scope WHERE run_id = {rollback_id};
DELETE FROM board_minute_target_scope WHERE run_id = {rollback_id};

DELETE FROM stock_condition_pool WHERE run_id = {rollback_id};
DELETE FROM index_condition_pool WHERE run_id = {rollback_id};
DELETE FROM board_condition_pool WHERE run_id = {rollback_id};

DELETE FROM stock_condition_basis WHERE run_id = {rollback_id};
DELETE FROM index_condition_basis WHERE run_id = {rollback_id};
DELETE FROM board_condition_basis WHERE run_id = {rollback_id};

DELETE FROM stock_monitor_target WHERE source_version = {rollback_id};
DELETE FROM index_monitor_target WHERE source_version = {rollback_id};
DELETE FROM board_monitor_target WHERE source_version = {rollback_id};

DELETE FROM common_condition_quality_item WHERE run_id = {rollback_id};
DELETE FROM common_condition_run WHERE run_id = {rollback_id};

UPDATE common_condition_run
SET status = 'passed_active', updated_at = now()
WHERE run_id = {restore_id}
  AND status IN ('superseded', 'passed');

COMMIT;
"""


def sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def empty_execute_gate_expected_rows(reason: str) -> dict[str, Any]:
    return {
        "condition_basis": {"stock": 0, "index": 0, "board": 0},
        "condition_pool": {"stock": 0, "index": 0, "board": 0},
        "minute_target_scope": {"stock": 0, "index": 0, "board": 0},
        "condition_display_basis": {"stock": 0, "index": 0, "board": 0},
        "monitor_target": {"stock": 0, "index": 0, "board": 0},
        "quality_item": 0,
        "source": reason,
    }


def gate_expected_rows_from_execute_counts(expected: Mapping[str, Any]) -> dict[str, Any]:
    def table_count(table_name: str) -> int:
        spec = expected.get(table_name) if isinstance(expected, Mapping) else None
        return int(dict(spec or {}).get("row_count") or 0)

    return {
        "condition_basis": {
            "stock": table_count("stock_condition_basis"),
            "index": table_count("index_condition_basis"),
            "board": table_count("board_condition_basis"),
        },
        "condition_pool": {
            "stock": table_count("stock_condition_pool"),
            "index": table_count("index_condition_pool"),
            "board": table_count("board_condition_pool"),
        },
        "minute_target_scope": {
            "stock": table_count("stock_minute_target_scope"),
            "index": table_count("index_minute_target_scope"),
            "board": table_count("board_minute_target_scope"),
        },
        "condition_display_basis": {
            "stock": table_count("stock_condition_display_basis"),
            "index": table_count("index_condition_display_basis"),
            "board": table_count("board_condition_display_basis"),
        },
        "monitor_target": {
            "stock": table_count("stock_monitor_target"),
            "index": table_count("index_monitor_target"),
            "board": table_count("board_monitor_target"),
        },
        "quality_item": table_count("common_condition_quality_item"),
    }


def scope_delta_summary_from_dry_run(dry_run: Mapping[str, Any]) -> dict[str, Any]:
    domains = dict(dry_run.get("domains") or {})
    summary: dict[str, Any] = {}
    for domain in POLICY_DOMAINS:
        item = dict(domains.get(domain) or {})
        pool = dict(item.get("pool") or {})
        scope = dict(item.get("scope") or {})
        summary[domain] = {
            "condition_pool_rows": int(pool.get("row_count") or pool.get("pool_row_count") or 0),
            "minute_target_scope_rows": int(scope.get("row_count") or scope.get("scope_row_count") or 0),
            "minute_target_scope_objects": int(scope.get("object_count") or 0),
        }
    return summary


def daily_runner_policy_audit(project_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(project_root) if project_root is not None else default_project_root()
    runner_relative_path = Path("scripts/run_condition_layer_execute.py")
    runner_path = root / runner_relative_path
    default_policy_path = root / DEFAULT_POLICY_DRAFT_RELATIVE_PATH
    blocked_reasons: list[str] = []

    runner_source = ""
    if runner_path.exists():
        runner_source = runner_path.read_text(encoding="utf-8")
    else:
        blocked_reasons.append(f"runner_missing:{runner_relative_path}")

    uses_default_policy = (
        "DEFAULT_POLICY_DRAFT_RELATIVE_PATH" in runner_source
        and "resolve_condition_runner_policy" in runner_source
    )
    if not uses_default_policy:
        blocked_reasons.append("runner_default_policy_loader_missing")

    default_policy_artifact = load_policy_artifact(default_policy_path) or {}
    default_policy_exists = default_policy_path.exists()
    if not default_policy_exists:
        blocked_reasons.append(f"default_policy_draft_missing:{DEFAULT_POLICY_DRAFT_RELATIVE_PATH.as_posix()}")

    override_hits = _scan_scheduler_policy_overrides(root)
    for hit in override_hits:
        blocked_reasons.append(
            f"scheduler_policy_override:{hit['path']}:{hit['policy_path']}"
        )

    return {
        "audit_result": "BLOCKED" if blocked_reasons else "PASS",
        "layer_role": "N2_condition",
        "runner_path": str(runner_relative_path),
        "daily_runner_uses_run_condition_layer_execute": runner_path.exists(),
        "runner_uses_default_policy_draft_when_policy_missing": uses_default_policy,
        "default_policy_path": DEFAULT_POLICY_DRAFT_RELATIVE_PATH.as_posix(),
        "default_policy_exists": default_policy_exists,
        "default_policy_hash": default_policy_artifact.get("policy_hash"),
        "default_policy_version": default_policy_artifact.get("policy_version"),
        "scheduler_registry_policy_override_detected": bool(override_hits),
        "scheduler_registry_policy_override_hits": override_hits,
        "blocked_reasons": blocked_reasons,
        "writes_performed": False,
        "database_written": False,
    }


def _scan_scheduler_policy_overrides(root: Path) -> list[dict[str, str]]:
    scan_roots = [
        root / "docs" / "runtime_registry",
        root / "docs" / "runtime",
        root / "configs" / "runtime",
        root / "configs" / "scheduler",
    ]
    allowed = DEFAULT_POLICY_DRAFT_RELATIVE_PATH.as_posix()
    hits: list[dict[str, str]] = []
    pattern = re.compile(r"run_condition_layer_execute\.py[\s\S]{0,800}")
    policy_pattern = re.compile(r"--policy\s+([^\s\\]+)")
    for scan_root in scan_roots:
        if not scan_root.exists():
            continue
        for path in scan_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".json", ".toml", ".yaml", ".yml", ".txt"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for command_match in pattern.finditer(text):
                command_text = command_match.group(0)
                policy_match = policy_pattern.search(command_text)
                if not policy_match:
                    continue
                policy_path = policy_match.group(1).strip("'\"")
                if policy_path != allowed:
                    hits.append(
                        {
                            "path": str(path.relative_to(root)),
                            "policy_path": policy_path,
                            "command_excerpt": command_text.strip()[:500],
                        }
                    )
    return hits


def build_policy_gate_display_preview(
    *,
    planned_run_id: str,
    basis_report: Mapping[str, Any],
    pool_report: Mapping[str, Any],
    scope_report: Mapping[str, Any],
) -> dict[str, Any]:
    from ashare_v3.condition.display_basis import (
        DOMAIN_CONFIGS,
        build_display_rows_for_domain,
        build_domain_report,
    )

    domain_reports: dict[str, Any] = {}
    for domain in POLICY_DOMAINS:
        config = DOMAIN_CONFIGS[domain]
        basis_rows, pool_rows, scope_rows = attach_policy_gate_synthetic_ids(
            domain=domain,
            planned_run_id=planned_run_id,
            basis_rows=list(basis_report["basis_preview"][domain].get("basis_rows") or []),
            pool_rows=list(pool_report["pool_preview"][domain].get("pool_rows") or []),
            scope_rows=list(scope_report["scope_preview"][domain].get("scope_rows") or []),
        )
        rows = build_display_rows_for_domain(
            config,
            basis_rows=basis_rows,
            pool_rows=pool_rows,
            scope_rows=scope_rows,
        )
        domain_reports[domain] = build_domain_report(config, rows, include_rows=False)
    return {
        "stage": "N2-web-policy-gate-display-preview",
        "run_id": planned_run_id,
        "source_trade_date": basis_report.get("source_trade_date"),
        "for_trade_date": basis_report.get("for_trade_date"),
        "prev_trade_date": basis_report.get("prev_trade_date"),
        "display_preview": domain_reports,
        "writes_performed": False,
        "display_basis_written": False,
    }


def attach_policy_gate_synthetic_ids(
    *,
    domain: str,
    planned_run_id: str,
    basis_rows: list[Mapping[str, Any]],
    pool_rows: list[Mapping[str, Any]],
    scope_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    from ashare_v3.condition.display_basis import DOMAIN_CONFIGS

    config = DOMAIN_CONFIGS[domain]
    basis_id_by_ref: dict[str, int] = {}
    output_basis: list[dict[str, Any]] = []
    for index, row in enumerate(basis_rows, start=1):
        copied = dict(row)
        copied["run_id"] = planned_run_id
        copied[config.basis_id_col] = index
        identity_key = copied.get(config.identity_col)
        basis_ref = f"dry_run:{domain}:{index}:{identity_key}"
        basis_id_by_ref[basis_ref] = index
        output_basis.append(copied)

    pool_id_by_ref: dict[str, int] = {}
    output_pool: list[dict[str, Any]] = []
    for index, row in enumerate(pool_rows, start=1):
        copied = dict(row)
        copied["run_id"] = planned_run_id
        copied[config.pool_id_col] = index
        copied["source_condition_basis_id"] = basis_id_by_ref.get(str(copied.get("source_condition_basis_ref") or ""))
        pool_ref = str(copied.get("condition_pool_ref") or f"dry_run:{domain}:condition_pool:{index}")
        pool_id_by_ref[pool_ref] = index
        output_pool.append(copied)

    output_scope: list[dict[str, Any]] = []
    for index, row in enumerate(scope_rows, start=1):
        copied = dict(row)
        copied["run_id"] = planned_run_id
        copied[config.scope_id_col] = index
        copied["source_condition_pool_id"] = pool_id_by_ref.get(str(copied.get("source_condition_pool_ref") or ""))
        output_scope.append(copied)
    return output_basis, output_pool, output_scope


def policy_gate_display_quality_item_count(display_report: Mapping[str, Any]) -> int:
    return sum(9 for _ in dict(display_report.get("display_preview") or {})) + 1


def normalize_db_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [normalize_db_value(item) for item in value]
    if isinstance(value, tuple):
        return [normalize_db_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalize_db_value(item) for key, item in value.items()}
    return value


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json_artifact(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalize_db_value(dict(payload)), ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_text_artifact(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def n2_execute_command(source_trade_date: str, *, run_id: str | None = None, overwrite: bool = True) -> str:
    lines = [
        "PYTHONPATH=src python3 scripts/run_condition_layer_execute.py \\",
        f"  --source-trade-date {source_trade_date} \\",
        f"  --policy {DEFAULT_POLICY_DRAFT_RELATIVE_PATH.as_posix()} \\",
    ]
    if run_id:
        lines.append(f"  --run-id {run_id} \\")
    lines.append("  --execute \\")
    if overwrite:
        lines.append("  --overwrite \\")
    lines.extend(
        [
            "  --user-confirmed \\",
            "  --operator codex \\",
            "  --confirmation-note N2-web-policy-active-supersede \\",
            "  --report-path docs/N2_web_policy_execute_report.json",
        ]
    )
    return "\n".join(lines)


def execute_gate_markdown(result: Mapping[str, Any]) -> str:
    dry_run = dict(result.get("dry_run") or {})
    domains = dict(dry_run.get("domains") or {})
    lineage = dict(result.get("active_lineage_plan") or {})
    expected_rows = dict(result.get("expected_row_counts") or {})
    lines = [
        "# N2 Web Policy Execute Gate Draft",
        "",
        "This artifact is generated by the N2 policy console. It does not execute N2 and does not write PostgreSQL business rows.",
        "When the default draft exists, the N2 runner reads it before falling back to the built-in default policy.",
        "",
        "```text",
        f"gate_result={result.get('gate_result')}",
        f"proposed_run_id={result.get('proposed_run_id')}",
        f"source_trade_date={result.get('source_trade_date')}",
        f"for_trade_date={result.get('for_trade_date')}",
        f"prev_trade_date={result.get('prev_trade_date')}",
        f"policy_id={result.get('policy_id')}",
        f"policy_version={result.get('policy_version')}",
        f"policy_hash={result.get('policy_hash')}",
        f"execute_allowed_candidate={result.get('execute_allowed_candidate')}",
        f"current_active_run_id={lineage.get('current_active_run_id')}",
        f"overwrite_semantics={lineage.get('overwrite_semantics')}",
        f"n3_lineage_auto_switch={lineage.get('n3_lineage_auto_switch')}",
        f"P0/P1/P2={dry_run.get('p0_count', 0)}/{dry_run.get('p1_count', 0)}/{dry_run.get('p2_count', 0)}",
        "writes_performed=false",
        "database_written=false",
        "execute_authorized=false",
        "```",
        "",
        "## Dry-run Rows",
        "",
        "| domain | pool rows | scope rows | objects |",
        "|---|---:|---:|---:|",
    ]
    for domain in POLICY_DOMAINS:
        item = dict(domains.get(domain) or {})
        lines.append(
            f"| {domain} | {dict(item.get('pool') or {}).get('row_count', 0)} | "
            f"{dict(item.get('scope') or {}).get('row_count', 0)} | "
            f"{dict(item.get('scope') or {}).get('object_count', 0)} |"
        )
    lines.extend(
        [
            "",
            "## Expected Write Rows",
            "",
            "| stage | stock | index | board |",
            "|---|---:|---:|---:|",
        ]
    )
    for stage in ("condition_basis", "condition_pool", "minute_target_scope", "condition_display_basis", "monitor_target"):
        row = dict(expected_rows.get(stage) or {})
        lines.append(f"| {stage} | {row.get('stock', 0)} | {row.get('index', 0)} | {row.get('board', 0)} |")
    lines.append(f"| quality_item | {expected_rows.get('quality_item', 0)} |  |  |")
    lines.extend(
        [
            "",
            "## Execute Command Candidate",
            "",
            "Only after N2 execute final gate review and explicit user confirmation:",
            "",
            "```bash",
            str(result.get("execute_command_candidate") or result.get("execute_command") or ""),
            "```",
            "",
            f"Rollback SQL path: `{result.get('rollback_sql_path')}`",
            "",
            "Boundary: no N3/N4/N5/N6 auto rebuild, no worker, no market data pull.",
        ]
    )
    return "\n".join(lines) + "\n"


def default_project_root() -> Path:
    return Path(__file__).resolve().parents[3]
