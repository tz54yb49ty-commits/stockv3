"""N1 canonical stock financial source bundle dry-run probe.

This module prepares a no-write source bundle for the future
`stock_financial_${source_trade_date}_v2` canonical metrics calculator. It
deliberately does not write `stock_financial_metrics_fact` or activate any
source version.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from decimal import Decimal
import base64
import hashlib
import importlib
import json
import os
from pathlib import Path
import time
from typing import Any, Iterable, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row

from ashare_v3.ingestion.tushare_env import load_tushare_token
from ashare_v3.ingestion.common import require_yyyymmdd
from ashare_v3.ingestion.mootdx_financial_source import MootdxAffairFinancialSource
from ashare_v3.ingestion.stock_financial import StockFinancialSymbol
from ashare_v3.ingestion.stock_financial_canonical_metrics import (
    BATCH_ID,
    FINANCIAL_METRIC_VERSION,
    PREVIOUS_SOURCE_VERSION,
    SOURCE_TDX,
    SOURCE_TUSHARE_FALLBACK,
    SOURCE_VERSION,
    TRADE_DATE,
    default_side_effects,
    first_decimal,
    json_safe,
    optional_date_text,
    quality_item,
    source_type,
    summarize_quality,
)


SOURCE_BUNDLE_BATCH_ID = "stock_financial_canonical_source_bundle_20260529_v1"
FINANCIAL_CANONICAL_SNAPSHOT_SCHEMA_VERSION = "financial_canonical_snapshot_v1"
DEFAULT_SMALL_SAMPLE_SIZE = 10
INCREMENTAL_DELTA_FULL_FETCH_GUARD_RATIO = 0.20
DEFAULT_TUSHARE_CACHE_PATH = Path("tmp/N1_stock_financial_canonical_source_bundle_20260529_tushare_cache.json")
SOURCE_MOOTDX_AFFAIR = "mootdx_affair"
FINANCIAL_SOURCE_POLICY_VERSION = "affair_authoritative_no_forecast_v1"
FINANCIAL_NULL_WARNING_CODE = "financial_source_unavailable_null_metrics"
FINANCIAL_FRESH_COVERAGE_MIN_RATIO = Decimal("0.90")
LEGACY_FINANCIAL_UNAVAILABLE_WARNING_CODES = frozenset(
    {
        "emergency_previous_snapshot_financial_missing",
        "current_only_financial_unavailable",
    }
)

DEFAULT_PATHS = {
    "dry_run_json": Path("docs/N1_stock_financial_canonical_source_bundle_20260529_dry_run_report.json"),
    "dry_run_md": Path("docs/N1_STOCK_FINANCIAL_CANONICAL_SOURCE_BUNDLE_20260529_DRY_RUN_REPORT.md"),
    "contract_json": Path("docs/N1_stock_financial_canonical_source_bundle_20260529_contract.json"),
    "contract_md": Path("docs/N1_STOCK_FINANCIAL_CANONICAL_SOURCE_BUNDLE_20260529_CONTRACT.md"),
    "preflight_json": Path("docs/N1_stock_financial_canonical_source_bundle_20260529_preflight.json"),
    "preflight_md": Path("docs/N1_STOCK_FINANCIAL_CANONICAL_SOURCE_BUNDLE_20260529_PREFLIGHT.md"),
}


def source_bundle_batch_id_for(source_trade_date: str) -> str:
    source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    return f"stock_financial_canonical_source_bundle_{source_trade_date}_v1"


def default_tushare_cache_path_for(source_trade_date: str) -> Path:
    source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    return Path(f"tmp/N1_stock_financial_canonical_source_bundle_{source_trade_date}_tushare_cache.json")


def default_paths_for(source_trade_date: str) -> dict[str, Path]:
    source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    return {
        "dry_run_json": Path(f"docs/N1_stock_financial_canonical_source_bundle_{source_trade_date}_dry_run_report.json"),
        "dry_run_md": Path(f"docs/N1_STOCK_FINANCIAL_CANONICAL_SOURCE_BUNDLE_{source_trade_date}_DRY_RUN_REPORT.md"),
        "contract_json": Path(f"docs/N1_stock_financial_canonical_source_bundle_{source_trade_date}_contract.json"),
        "contract_md": Path(f"docs/N1_STOCK_FINANCIAL_CANONICAL_SOURCE_BUNDLE_{source_trade_date}_CONTRACT.md"),
        "preflight_json": Path(f"docs/N1_stock_financial_canonical_source_bundle_{source_trade_date}_preflight.json"),
        "preflight_md": Path(f"docs/N1_STOCK_FINANCIAL_CANONICAL_SOURCE_BUNDLE_{source_trade_date}_PREFLIGHT.md"),
    }


def apply_source_bundle_context(source_trade_date: str) -> None:
    source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    metrics_module = importlib.import_module("ashare_v3.ingestion.stock_financial_canonical_metrics")
    metrics_module.apply_canonical_context(source_trade_date)
    globals()["TRADE_DATE"] = metrics_module.TRADE_DATE
    globals()["BATCH_ID"] = metrics_module.BATCH_ID
    globals()["SOURCE_VERSION"] = metrics_module.SOURCE_VERSION
    globals()["PREVIOUS_SOURCE_VERSION"] = metrics_module.PREVIOUS_SOURCE_VERSION
    globals()["SOURCE_BUNDLE_BATCH_ID"] = source_bundle_batch_id_for(source_trade_date)
    globals()["DEFAULT_TUSHARE_CACHE_PATH"] = default_tushare_cache_path_for(source_trade_date)
    globals()["DEFAULT_PATHS"] = default_paths_for(source_trade_date)


FINANCIAL_SOURCE_SIGNATURE_ALIASES = {
    "stock_identity_key": ("stock_identity_key",),
    "report_period": ("report_period", "end_date"),
    "announcement_date": ("announcement_date", "ann_date"),
    "source_type": ("source_type", "source"),
    "operating_revenue": ("operating_revenue", "total_revenue", "revenue", "report_core_revenue"),
    "operating_cost": ("operating_cost", "total_operating_cost", "oper_cost"),
    "taxes_and_surcharges": ("taxes_and_surcharges", "biz_tax_surchg"),
    "selling_expense": ("selling_expense", "sell_exp"),
    "admin_expense": ("admin_expense", "admin_exp"),
    "rd_expense": ("rd_expense",),
    "interest_expense": ("interest_expense", "interest_exp"),
    "finance_expense": ("finance_expense", "fin_exp"),
    "operating_cashflow": ("operating_cashflow", "net_cashflow_operating", "n_cashflow_act"),
    "net_profit": ("net_profit", "n_income_attr_p", "report_core_profit"),
    "forecast_type": ("forecast_type", "type"),
}

FINANCIAL_SIGNATURE_EXCLUDED_BRANCH_KEYS = frozenset(
    {
        "daily_basic",
        "score_breakdown_json",
        "financial_warning_json",
        "sector_policy_json",
        "warning",
        "warnings",
    }
)


def _first_financial_signature_value(value: Any, aliases: Sequence[str], *, depth: int = 0) -> Any:
    if depth > 6:
        return None
    if isinstance(value, Mapping):
        for alias in aliases:
            item = value.get(alias)
            if item not in (None, "") and not isinstance(item, (Mapping, list, tuple, set)):
                return item
        priority_keys = ("latest_source", "source_row", "selected_financial", "forecast", "raw_payload")
        remaining_keys = sorted(str(key) for key in value.keys() if str(key) not in priority_keys)
        for key in (*priority_keys, *remaining_keys):
            if key in FINANCIAL_SIGNATURE_EXCLUDED_BRANCH_KEYS or key not in value:
                continue
            item = _first_financial_signature_value(value.get(key), aliases, depth=depth + 1)
            if item not in (None, ""):
                return item
    elif isinstance(value, (list, tuple)):
        for item in value:
            found = _first_financial_signature_value(item, aliases, depth=depth + 1)
            if found not in (None, ""):
                return found
    return None


def financial_source_signature_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field: _first_financial_signature_value(row, aliases)
        for field, aliases in FINANCIAL_SOURCE_SIGNATURE_ALIASES.items()
    }


def _signature_sort_key(payload: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(payload.get("report_period") or ""),
        str(payload.get("announcement_date") or ""),
        str(payload.get("stock_identity_key") or ""),
    )


def latest_financial_source_signature_payload(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    payloads = [financial_source_signature_payload(row) for row in rows]
    payloads = [payload for payload in payloads if payload.get("stock_identity_key")]
    if not payloads:
        return {}
    return sorted(payloads, key=_signature_sort_key, reverse=True)[0]


def financial_source_signature(rows: Sequence[Mapping[str, Any]]) -> str:
    normalized = []
    for row in sorted(
        (dict(row) for row in rows),
        key=lambda item: (
            str(_first_financial_signature_value(item, FINANCIAL_SOURCE_SIGNATURE_ALIASES["stock_identity_key"]) or ""),
            str(_first_financial_signature_value(item, FINANCIAL_SOURCE_SIGNATURE_ALIASES["report_period"]) or ""),
            str(_first_financial_signature_value(item, FINANCIAL_SOURCE_SIGNATURE_ALIASES["announcement_date"]) or ""),
            str(_first_financial_signature_value(item, FINANCIAL_SOURCE_SIGNATURE_ALIASES["source_type"]) or ""),
        ),
    ):
        normalized.append(financial_source_signature_payload(row))
    raw = json.dumps(json_strict_safe(normalized), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalized_delta_compare_value(field: str, value: Any) -> Any:
    if value in (None, ""):
        return None
    if field == "source_type":
        text = str(value)
        if text.startswith("financial_asof_snapshot"):
            return None
        lowered = text.lower()
        if "tdx" in lowered:
            return "tdx"
        if "tushare" in lowered:
            return "tushare"
        return text
    return value


def _signature_date_text(value: Any) -> str | None:
    normalized = optional_date_text(value)
    if normalized:
        return normalized
    if value not in (None, ""):
        return str(value)
    return None


def financial_source_payload_changed(
    current_rows: Sequence[Mapping[str, Any]],
    previous_rows: Sequence[Mapping[str, Any]],
) -> bool:
    current_payload = latest_financial_source_signature_payload(current_rows)
    previous_payload = latest_financial_source_signature_payload(previous_rows)
    if not current_payload or not previous_payload:
        return financial_source_signature(current_rows) != financial_source_signature(previous_rows)
    if str(current_payload.get("stock_identity_key") or "") != str(previous_payload.get("stock_identity_key") or ""):
        return True
    current_period = _signature_date_text(current_payload.get("report_period"))
    previous_period = _signature_date_text(previous_payload.get("report_period"))
    if current_period and previous_period:
        if current_period > previous_period:
            return True
        if current_period < previous_period:
            return False
    current_announcement = _signature_date_text(current_payload.get("announcement_date"))
    previous_announcement = _signature_date_text(previous_payload.get("announcement_date"))
    if current_announcement and previous_announcement:
        if current_announcement > previous_announcement:
            return True
        if current_announcement < previous_announcement:
            return False
    strict_fields = ("stock_identity_key", "report_period", "announcement_date")
    for field in FINANCIAL_SOURCE_SIGNATURE_ALIASES:
        if field in strict_fields:
            continue
        current_value = _normalized_delta_compare_value(field, current_payload.get(field))
        previous_value = _normalized_delta_compare_value(field, previous_payload.get(field))
        if current_value is None or previous_value is None:
            continue
        if str(current_value) != str(previous_value):
            return True
    return False


def group_rows_by_identity_key(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        identity_key = str(row.get("stock_identity_key") or "")
        if identity_key:
            grouped[identity_key].append(dict(row))
    return grouped


def canonical_payload_sha256(value: Any) -> str:
    raw = json.dumps(json_strict_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def identity_keys_sha256(identity_keys: Sequence[str]) -> str:
    return canonical_payload_sha256(sorted({str(key) for key in identity_keys if key}))


def is_financial_null_warning_row(row: Mapping[str, Any]) -> bool:
    raw_payload = row.get("raw_payload")
    return bool(
        isinstance(raw_payload, Mapping)
        and raw_payload.get("financial_warning_only") is True
        and raw_payload.get("financial_values_fabricated") is False
        and raw_payload.get("warning_code") == FINANCIAL_NULL_WARNING_CODE
    )


def is_legacy_financial_unavailable_row(row: Mapping[str, Any]) -> bool:
    warning_payload = row.get("financial_warning_json")
    warnings = (
        warning_payload.get("warnings")
        if isinstance(warning_payload, Mapping)
        else []
    ) or []
    return bool(
        LEGACY_FINANCIAL_UNAVAILABLE_WARNING_CODES.intersection(
            str(code) for code in warnings if code
        )
    )


def build_financial_null_warning_row(
    identity_key: str,
    *,
    source_trade_date: str,
    reason: str,
) -> dict[str, Any]:
    parts = str(identity_key).split(":", 2)
    if len(parts) != 3 or parts[0] != "stock" or not parts[1] or not parts[2]:
        raise StockFinancialCanonicalSourceBundleBlocked("financial_null_warning_identity_invalid")
    _, exchange, code = parts
    return {
        "stock_identity_key": identity_key,
        "ts_code": f"{code}.{exchange}",
        "code": code,
        "exchange": exchange,
        "source_type": SOURCE_MOOTDX_AFFAIR,
        "source_trade_date": source_trade_date,
        "report_period": None,
        "announcement_date": None,
        "forecast_type": None,
        "forecast_score": None,
        "financial_warning_json": {
            "warnings": [FINANCIAL_NULL_WARNING_CODE],
            "reason": reason,
            "severity": "P1",
        },
        "raw_payload": {
            "financial_warning_only": True,
            "financial_values_fabricated": False,
            "warning_code": FINANCIAL_NULL_WARNING_CODE,
            "reason": reason,
        },
    }


def dedupe_exact_financial_rows(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Drop byte-equivalent canonical rows while preserving first-seen order."""

    unique_rows: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    dropped_hashes: list[str] = []
    for row in rows:
        row_dict = dict(row)
        row_hash = canonical_payload_sha256(row_dict)
        if row_hash in seen_hashes:
            dropped_hashes.append(row_hash)
            continue
        seen_hashes.add(row_hash)
        unique_rows.append(row_dict)
    return unique_rows, dropped_hashes


def resolve_legacy_carry_grain_conflicts(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Preserve the first immutable snapshot row for legacy grain conflicts.

    Fresh Affair rows never use this compatibility path; a same-grain payload
    conflict in fresh data therefore remains a P0 integrity failure.
    """

    selected_rows: list[dict[str, Any]] = []
    selected_by_grain: dict[tuple[str, str, str], tuple[str, dict[str, Any]]] = {}
    conflicts: list[dict[str, str]] = []
    for row in rows:
        row_dict = dict(row)
        if is_financial_null_warning_row(row_dict) or is_legacy_financial_unavailable_row(row_dict):
            selected_rows.append(row_dict)
            continue
        grain = (
            str(row_dict.get("stock_identity_key") or ""),
            str(row_dict.get("report_period") or ""),
            str(row_dict.get("announcement_date") or ""),
        )
        row_hash = canonical_payload_sha256(row_dict)
        selected = selected_by_grain.get(grain)
        if selected is None:
            selected_by_grain[grain] = (row_hash, row_dict)
            selected_rows.append(row_dict)
            continue
        selected_hash, _ = selected
        if row_hash == selected_hash:
            selected_rows.append(row_dict)
            continue
        conflicts.append(
            {
                "stock_identity_key": grain[0],
                "report_period": grain[1],
                "announcement_date": grain[2],
                "selected_row_sha256": selected_hash,
                "rejected_row_sha256": row_hash,
            }
        )
    return selected_rows, conflicts


def merge_financial_only_rows(
    *,
    expected_identity_keys: Sequence[str],
    refreshed_rows: Sequence[Mapping[str, Any]],
    previous_snapshot: Mapping[str, Any] | None = None,
    source_trade_date: str = TRADE_DATE,
    force_full_fallback: bool = False,
    fallback_reason: str | None = None,
    carry_limit: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Merge Affair rows without allowing financial availability to stop Fast Lane.

    Data-integrity failures remain fail-closed. Source availability and coverage
    failures are converted into a fully reconciled previous-snapshot fallback,
    with explicit NULL warning rows for identities that have no prior history.
    """

    source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    raw_expected = [str(key) for key in expected_identity_keys]
    expected = sorted(set(raw_expected))
    if not expected or len(expected) != len(raw_expected) or any(not key for key in raw_expected):
        raise StockFinancialCanonicalSourceBundleBlocked("financial_frozen_universe_duplicate_or_empty")
    expected_set = set(expected)
    refreshed_unknown = sorted(
        {
            str(row.get("stock_identity_key") or "")
            for row in refreshed_rows
            if str(row.get("stock_identity_key") or "") not in expected_set
        }
    )
    if refreshed_unknown:
        raise StockFinancialCanonicalSourceBundleBlocked("financial_refreshed_identity_outside_frozen_universe")
    refreshed: list[dict[str, Any]] = []
    refreshed_missing_announcement_count = 0
    refreshed_future_announcement_count = 0
    refreshed_invalid_report_period_count = 0
    for row in refreshed_rows:
        try:
            announcement_date = optional_date_text(
                row.get("announcement_date") or row.get("ann_date")
            )
        except (TypeError, ValueError):
            announcement_date = None
        try:
            report_period = optional_date_text(
                row.get("report_period") or row.get("end_date")
            )
        except (TypeError, ValueError):
            report_period = None
        if not announcement_date:
            refreshed_missing_announcement_count += 1
            continue
        if announcement_date > source_trade_date:
            refreshed_future_announcement_count += 1
            continue
        if not report_period:
            refreshed_invalid_report_period_count += 1
            continue
        refreshed.append(
            {
                **dict(row),
                "announcement_date": announcement_date,
                "report_period": report_period,
                "forecast_type": None,
                "forecast_score": None,
            }
        )
    current_by_key = group_rows_by_identity_key(refreshed)
    previous_rows = [
        {**dict(row), "forecast_type": None, "forecast_score": None}
        for row in snapshot_financial_rows(previous_snapshot or {})
        if str(row.get("stock_identity_key") or "") in expected_set
    ]
    previous_by_key = group_rows_by_identity_key(previous_rows)
    missing = sorted(expected_set - set(current_by_key))
    incomplete = sorted(
        key for key, rows in current_by_key.items()
        if not any(not missing_p0_line_items(row) for row in rows)
    )
    fresh_identity_keys = sorted(
        key
        for key, rows in current_by_key.items()
        if any(not missing_p0_line_items(row) for row in rows)
    )
    fresh_count = len(fresh_identity_keys)
    fresh_ratio = Decimal(fresh_count) / Decimal(len(expected))
    threshold_count = (len(expected) * 9 + 9) // 10
    bounded_carry_limit = len(expected) - threshold_count if carry_limit is None else int(carry_limit)
    use_full_fallback = bool(force_full_fallback or fresh_count < threshold_count)
    requested_carry_keys = expected if use_full_fallback else sorted(set(missing) | set(incomplete))
    final_rows: list[dict[str, Any]] = []
    carried_keys: list[str] = []
    null_warning_keys: list[str] = []
    legacy_grain_conflicts: list[dict[str, str]] = []
    for key in expected:
        if key in requested_carry_keys:
            previous_for_key = previous_by_key.get(key) or []
            previous_is_unavailable_warning = bool(
                previous_for_key
                and all(
                    is_financial_null_warning_row(row)
                    or is_legacy_financial_unavailable_row(row)
                    for row in previous_for_key
                )
            )
            if previous_for_key and not previous_is_unavailable_warning:
                resolved_previous, identity_conflicts = (
                    resolve_legacy_carry_grain_conflicts(previous_for_key)
                )
                final_rows.extend(resolved_previous)
                legacy_grain_conflicts.extend(identity_conflicts)
                carried_keys.append(key)
            else:
                reason = fallback_reason or (
                    "fresh_coverage_below_90pct"
                    if use_full_fallback and not force_full_fallback
                    else "financial_source_unavailable"
                    if use_full_fallback
                    else "financial_identity_missing_or_incomplete"
                )
                final_rows.append(
                    build_financial_null_warning_row(
                        key,
                        source_trade_date=source_trade_date,
                        reason=reason,
                    )
                )
                null_warning_keys.append(key)
        else:
            selected = current_by_key.get(key) or []
            if not selected:
                raise StockFinancialCanonicalSourceBundleBlocked("financial_merge_selected_identity_missing")
            final_rows.extend(selected)

    final_by_key = group_rows_by_identity_key(final_rows)
    final_keys = sorted(final_by_key)
    if final_keys != expected:
        raise StockFinancialCanonicalSourceBundleBlocked("financial_final_identity_exact_equality_failed")
    if len(final_keys) != len(expected):
        raise StockFinancialCanonicalSourceBundleBlocked("financial_final_identity_count_mismatch")

    pre_dedup_rows = [
        {**dict(row), "forecast_type": None, "forecast_score": None}
        for row in final_rows
    ]
    final_rows_normalized, dropped_exact_row_hashes = (
        dedupe_exact_financial_rows(pre_dedup_rows)
    )
    final_identity_sha256 = identity_keys_sha256(final_keys)
    null_warning_sha256 = identity_keys_sha256(null_warning_keys)
    effective_fallback_reason = fallback_reason or (
        "fresh_coverage_below_90pct"
        if use_full_fallback and not force_full_fallback
        else None
    )
    lineage = {
        "financial_only": True,
        "financial_source_policy_version": FINANCIAL_SOURCE_POLICY_VERSION,
        "financial_authority": SOURCE_MOOTDX_AFFAIR,
        "forecast_disabled": True,
        "financial_degraded_but_fastlane_allowed": True,
        "financial_refresh_mode": (
            "previous_snapshot_full_carry_forward" if use_full_fallback else "affair_fresh_90pct"
        ),
        "financial_fallback_reason": effective_fallback_reason,
        "expected_identity_count": len(expected),
        "expected_identity_sha256": identity_keys_sha256(expected),
        "financial_fresh_coverage_min_ratio": str(FINANCIAL_FRESH_COVERAGE_MIN_RATIO),
        "financial_fresh_coverage_threshold_count": threshold_count,
        "financial_fresh_coverage_count": fresh_count,
        "financial_fresh_coverage_ratio": str(fresh_ratio),
        "financial_fresh_identity_keys": fresh_identity_keys,
        "financial_fresh_identity_sha256": identity_keys_sha256(fresh_identity_keys),
        "refreshed_financial_row_count": len(refreshed),
        "refreshed_missing_announcement_count": refreshed_missing_announcement_count,
        "refreshed_future_announcement_count": refreshed_future_announcement_count,
        "refreshed_invalid_report_period_count": refreshed_invalid_report_period_count,
        "refreshed_financial_identity_count": len(current_by_key),
        "refreshed_financial_identity_keys": sorted(current_by_key),
        "financial_refreshed_missing_identity_keys": missing,
        "financial_refreshed_incomplete_identity_keys": incomplete,
        "financial_requested_carry_identity_keys": requested_carry_keys,
        "financial_carry_limit": bounded_carry_limit,
        "financial_carried_forward_identity_keys": carried_keys,
        "financial_carried_forward_count": len(carried_keys),
        "financial_carried_forward_identity_sha256": identity_keys_sha256(carried_keys),
        "financial_null_warning_identity_keys": null_warning_keys,
        "financial_null_warning_identity_count": len(null_warning_keys),
        "financial_null_warning_identity_sha256": null_warning_sha256,
        "financial_pre_dedup_row_count": len(pre_dedup_rows),
        "financial_exact_duplicate_dropped_count": len(
            dropped_exact_row_hashes
        ),
        "financial_exact_duplicate_dropped_row_hashes_sha256": (
            canonical_payload_sha256(sorted(dropped_exact_row_hashes))
        ),
        "financial_exact_duplicate_dropped_row_hash_samples": sorted(
            set(dropped_exact_row_hashes)
        )[:20],
        "financial_legacy_grain_conflict_resolved_count": len(
            legacy_grain_conflicts
        ),
        "financial_legacy_grain_conflict_manifest_sha256": (
            canonical_payload_sha256(legacy_grain_conflicts)
        ),
        "financial_legacy_grain_conflict_samples": (
            legacy_grain_conflicts[:20]
        ),
        "financial_before_legacy_resolution_row_count": (
            len(pre_dedup_rows)
            + len(legacy_grain_conflicts)
        ),
        "financial_final_row_count": len(final_rows_normalized),
        "financial_final_rows_sha256": canonical_payload_sha256(final_rows_normalized),
        "financial_final_identity_count": len(final_keys),
        "financial_final_identity_sha256": final_identity_sha256,
    }
    return final_rows_normalized, lineage


def merge_financial_only_daily_basic_rows(
    *,
    expected_identity_keys: Sequence[str],
    current_rows: Sequence[Mapping[str, Any]],
    previous_snapshot: Mapping[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    expected = sorted({str(key) for key in expected_identity_keys})
    expected_set = set(expected)

    def unique_by_key(rows: Sequence[Mapping[str, Any]], label: str) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = str(row.get("stock_identity_key") or "")
            if not key or key not in expected_set:
                continue
            if key in output:
                raise StockFinancialCanonicalSourceBundleBlocked(
                    f"{label}_daily_basic_duplicate_identity"
                )
            output[key] = dict(row)
        return output

    current_by_key = unique_by_key(current_rows, "current")
    previous_rows = [
        dict(row)
        for row in (previous_snapshot or {}).get("daily_basic_rows") or []
        if isinstance(row, Mapping)
    ]
    previous_by_key = unique_by_key(previous_rows, "previous")
    final_rows: list[dict[str, Any]] = []
    carried_keys: list[str] = []
    missing_keys: list[str] = []
    for key in expected:
        row = current_by_key.get(key)
        if row is not None:
            final_rows.append(row)
            continue
        row = previous_by_key.get(key)
        if row is not None:
            final_rows.append({**row, "daily_basic_carried_forward": True})
            carried_keys.append(key)
        else:
            missing_keys.append(key)
    return final_rows, {
        "daily_basic_identity_count": len(current_by_key),
        "daily_basic_carried_forward_identity_keys": carried_keys,
        "daily_basic_carried_forward_count": len(carried_keys),
        "daily_basic_missing_identity_keys": missing_keys,
        "daily_basic_missing_identity_count": len(missing_keys),
    }


def load_financial_canonical_snapshot_v1(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    snapshot_path = Path(path)
    if not snapshot_path.exists():
        return None
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, Mapping):
        return None
    if payload.get("schema_version") != FINANCIAL_CANONICAL_SNAPSHOT_SCHEMA_VERSION:
        return None
    expected_raw = [str(key) for key in payload.get("expected_identity_keys") or []]
    expected = sorted(set(expected_raw))
    rows_by_identity = payload.get("rows_by_identity")
    if (
        not expected
        or len(expected) != len(expected_raw)
        or not isinstance(rows_by_identity, Mapping)
        or sorted(str(key) for key in rows_by_identity) != expected
    ):
        return None
    financial_rows = [
        dict(row)
        for row in payload.get("financial_rows") or []
        if isinstance(row, Mapping)
    ]
    if any(
        str(row.get("stock_identity_key") or "") not in set(expected)
        for row in financial_rows
    ):
        return None
    declared_count = payload.get("expected_identity_count")
    declared_hash = payload.get("expected_identity_sha256")
    if declared_count is not None and int(declared_count) != len(expected):
        return None
    if declared_hash is not None and str(declared_hash) != identity_keys_sha256(expected):
        return None
    return dict(payload)


def stable_snapshot_source_signature(previous_entry: Mapping[str, Any]) -> str:
    financial_rows = previous_entry.get("financial_rows") or []
    if isinstance(financial_rows, Sequence) and not isinstance(financial_rows, (str, bytes, bytearray)):
        rows = [dict(row) for row in financial_rows if isinstance(row, Mapping)]
        if rows:
            return financial_source_signature(rows)
    return str(previous_entry.get("source_signature") or "")


def snapshot_financial_rows(previous_entry: Mapping[str, Any]) -> list[dict[str, Any]]:
    financial_rows = previous_entry.get("financial_rows") or []
    if isinstance(financial_rows, Sequence) and not isinstance(financial_rows, (str, bytes, bytearray)):
        return [dict(row) for row in financial_rows if isinstance(row, Mapping)]
    return []


def compute_financial_canonical_delta(
    current_rows: Sequence[Mapping[str, Any]],
    *,
    previous_snapshot: Mapping[str, Any] | None,
    explicit_changed_identity_keys: Sequence[str] | None = None,
    full_rebuild_confirmed: bool = False,
) -> dict[str, Any]:
    current_by_identity = group_rows_by_identity_key(current_rows)
    if full_rebuild_confirmed:
        identities = sorted(current_by_identity)
        return {
            "identity_keys": identities,
            "reasons_by_identity": {identity_key: "full_rebuild_confirmed" for identity_key in identities},
            "reason_distribution": {"full_rebuild_confirmed": len(identities)},
        }
    if not previous_snapshot or previous_snapshot.get("schema_version") != FINANCIAL_CANONICAL_SNAPSHOT_SCHEMA_VERSION:
        raise StockFinancialCanonicalSourceBundleBlocked(
            "financial_canonical_snapshot_v1_missing; full rebuild requires explicit --full-rebuild-confirmed"
        )
    previous_by_identity = previous_snapshot.get("rows_by_identity") or {}
    if not isinstance(previous_by_identity, Mapping):
        raise StockFinancialCanonicalSourceBundleBlocked("financial_canonical_snapshot_v1_invalid_rows_by_identity")
    explicit = {str(key) for key in explicit_changed_identity_keys or [] if key}
    reasons_by_identity: dict[str, str] = {
        identity_key: "explicit_changed_identity_key" for identity_key in explicit
    }
    for identity_key, rows in current_by_identity.items():
        if identity_key in reasons_by_identity:
            continue
        previous_entry = previous_by_identity.get(identity_key)
        if not isinstance(previous_entry, Mapping):
            reasons_by_identity[identity_key] = "new_identity"
            continue
        previous_rows = snapshot_financial_rows(previous_entry)
        if previous_rows:
            changed = financial_source_payload_changed(rows, previous_rows)
        else:
            changed = stable_snapshot_source_signature(previous_entry) != financial_source_signature(rows)
        if changed:
            reasons_by_identity[identity_key] = "financial_source_signature_changed"
    reason_distribution = Counter(reasons_by_identity.values())
    return {
        "identity_keys": sorted(reasons_by_identity),
        "reasons_by_identity": dict(sorted(reasons_by_identity.items())),
        "reason_distribution": dict(sorted(reason_distribution.items())),
    }


def compute_financial_canonical_delta_identity_keys(
    current_rows: Sequence[Mapping[str, Any]],
    *,
    previous_snapshot: Mapping[str, Any] | None,
    explicit_changed_identity_keys: Sequence[str] | None = None,
    full_rebuild_confirmed: bool = False,
) -> list[str]:
    return list(
        compute_financial_canonical_delta(
            current_rows,
            previous_snapshot=previous_snapshot,
            explicit_changed_identity_keys=explicit_changed_identity_keys,
            full_rebuild_confirmed=full_rebuild_confirmed,
        )["identity_keys"]
    )


def incremental_delta_guard_probe(
    *,
    active_universe_count: int,
    delta_symbol_count: int,
    incremental_enabled: bool,
    full_rebuild_confirmed: bool,
    threshold_ratio: float = INCREMENTAL_DELTA_FULL_FETCH_GUARD_RATIO,
) -> dict[str, Any]:
    active_count = max(0, int(active_universe_count or 0))
    delta_count = max(0, int(delta_symbol_count or 0))
    ratio = (delta_count / active_count) if active_count else 0.0
    blocked = bool(
        incremental_enabled
        and not full_rebuild_confirmed
        and active_count > 0
        and ratio > float(threshold_ratio)
    )
    return {
        "incremental_delta_guard_blocked": blocked,
        "incremental_delta_guard_threshold_ratio": float(threshold_ratio),
        "incremental_delta_ratio": round(ratio, 6),
        "incremental_delta_guard_reason": "delta_symbol_count_exceeds_guard_threshold_without_full_rebuild_confirmed"
        if blocked
        else None,
    }


def split_financial_rows_by_source(rows: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tdx_rows: list[dict[str, Any]] = []
    tushare_rows: list[dict[str, Any]] = []
    for row in rows:
        row_dict = dict(row)
        if source_type(row_dict) == SOURCE_TUSHARE_FALLBACK:
            tushare_rows.append(row_dict)
        else:
            tdx_rows.append(row_dict)
    return tdx_rows, tushare_rows


def snapshot_rows_for_identity(previous_snapshot: Mapping[str, Any] | None, identity_key: str, row_key: str) -> list[dict[str, Any]]:
    if not previous_snapshot:
        return []
    entry = (previous_snapshot.get("rows_by_identity") or {}).get(identity_key)
    if not isinstance(entry, Mapping):
        return []
    rows = entry.get(row_key) or []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def merge_incremental_source_rows(
    *,
    expected_identity_keys: Sequence[str],
    previous_snapshot: Mapping[str, Any] | None,
    delta_financial_rows: Sequence[Mapping[str, Any]],
    delta_forecast_rows: Sequence[Mapping[str, Any]],
    delta_identity_keys: Sequence[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    delta_keys = {str(key) for key in delta_identity_keys}
    delta_financial_by_key = group_rows_by_identity_key(delta_financial_rows)
    delta_forecast_by_key = group_rows_by_identity_key(delta_forecast_rows)
    financial_rows: list[dict[str, Any]] = []
    forecast_rows: list[dict[str, Any]] = []
    for identity_key in sorted({str(key) for key in expected_identity_keys}):
        if identity_key in delta_keys:
            financial_rows.extend(delta_financial_by_key.get(identity_key) or [])
            forecast_rows.extend(delta_forecast_by_key.get(identity_key) or [])
        else:
            financial_rows.extend(snapshot_rows_for_identity(previous_snapshot, identity_key, "financial_rows"))
            forecast_rows.extend(snapshot_rows_for_identity(previous_snapshot, identity_key, "forecast_rows"))
    return financial_rows, forecast_rows


def build_financial_canonical_snapshot_v1(
    *,
    source_trade_date: str,
    active_source_version: str | None,
    expected_identity_keys: Sequence[str],
    current_signature_rows: Sequence[Mapping[str, Any]],
    financial_rows: Sequence[Mapping[str, Any]],
    forecast_rows: Sequence[Mapping[str, Any]],
    daily_basic_rows: Sequence[Mapping[str, Any]],
    source_probe: Mapping[str, Any],
) -> dict[str, Any]:
    financial_by_identity = group_rows_by_identity_key(financial_rows)
    current_signature_by_identity = {
        identity_key: financial_source_signature(rows)
        for identity_key, rows in group_rows_by_identity_key(current_signature_rows).items()
    }
    signature_by_identity = {
        identity_key: financial_source_signature(rows)
        for identity_key, rows in financial_by_identity.items()
    }
    forecast_by_identity = group_rows_by_identity_key(forecast_rows)
    rows_by_identity: dict[str, Any] = {}
    for identity_key in sorted({str(key) for key in expected_identity_keys}):
        rows_by_identity[identity_key] = {
            "source_signature": signature_by_identity.get(identity_key) or current_signature_by_identity.get(identity_key) or financial_source_signature([]),
            "financial_rows": json_strict_safe(financial_by_identity.get(identity_key) or []),
            "forecast_rows": json_strict_safe(forecast_by_identity.get(identity_key) or []),
        }
    return {
        "schema_version": FINANCIAL_CANONICAL_SNAPSHOT_SCHEMA_VERSION,
        "source_trade_date": source_trade_date,
        "active_source_version": active_source_version,
        "expected_identity_keys": sorted({str(key) for key in expected_identity_keys}),
        "expected_identity_count": len(sorted({str(key) for key in expected_identity_keys})),
        "expected_identity_sha256": identity_keys_sha256(expected_identity_keys),
        "financial_rows": json_strict_safe(list(financial_rows)),
        "financial_rows_sha256": canonical_payload_sha256(list(financial_rows)),
        "forecast_rows": json_strict_safe(list(forecast_rows)),
        "daily_basic_rows": json_strict_safe(list(daily_basic_rows)),
        "rows_by_identity": rows_by_identity,
        "source_probe": json_strict_safe(dict(source_probe)),
    }


def write_financial_canonical_snapshot_v1(path: str | Path | None, payload: Mapping[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(json_strict_safe(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

ALLOWED_FUTURE_READ_SOURCES = (
    "mootdx.affair",
    "tushare.daily_basic",
)

FORBIDDEN_SCOPE = (
    "stock_financial_metrics_fact writes",
    "common_active_source_version updates",
    "condition_*",
    "N2/N3/N4/N5/N6",
    "outbox/inbox/checkpoint",
    "Parquet",
    "worker",
    "old_system",
    "real_trading",
)

REQUIRED_LINE_ITEM_FIELDS = {
    "operating_revenue": ("report_core_revenue", "operating_revenue", "total_revenue", "revenue", "营业收入", "zhuyingshouru"),
    "operating_cost": ("operating_cost", "total_operating_cost", "oper_cost", "营业成本", "yingyechengben"),
    "taxes_and_surcharges": ("taxes_and_surcharges", "biz_tax_surchg", "营业税金及附加"),
    "selling_expense": ("selling_expense", "sell_exp", "销售费用"),
    "admin_expense": ("admin_expense", "admin_exp", "管理费用"),
    "rd_expense": ("rd_expense", "研发费用"),
    "interest_or_finance_expense": ("interest_expense", "interest_exp", "利息费用", "finance_expense", "fin_exp", "财务费用"),
    "operating_cashflow": ("operating_cashflow", "net_cashflow_operating", "n_cashflow_act", "经营活动产生的现金流量净额"),
}

P0_LINE_ITEM_FIELDS = {
    "operating_revenue": REQUIRED_LINE_ITEM_FIELDS["operating_revenue"],
    "operating_cost": REQUIRED_LINE_ITEM_FIELDS["operating_cost"],
    "taxes_and_surcharges": REQUIRED_LINE_ITEM_FIELDS["taxes_and_surcharges"],
    "admin_expense": REQUIRED_LINE_ITEM_FIELDS["admin_expense"],
    "interest_or_finance_expense": REQUIRED_LINE_ITEM_FIELDS["interest_or_finance_expense"],
}

ZERO_FALLBACK_LINE_ITEM_WARNINGS = {
    "rd_expense": "rd_expense_missing_fallback_zero",
    "selling_expense": "selling_expense_missing_fallback_zero",
}

OPERATING_CASHFLOW_WARNINGS = {
    "latest": "operating_cashflow_missing_latest",
    "historical": "operating_cashflow_missing_historical",
}

HISTORICAL_CORE_LINE_ITEMS_MISSING_WARNING = "historical_core_line_items_missing"
LATEST_CORE_LINE_ITEMS_MISSING_FALLBACK_WARNING = "latest_core_line_items_missing_fallback_prior_period"
FINANCE_SECTOR_INDUSTRIES = frozenset({"银行", "证券", "保险", "多元金融"})
FINANCE_SECTOR_POLICY_WARNING = "finance_sector_policy_not_supported_v1"
PRE_REVENUE_POLICY_WARNING = "pre_revenue_or_missing_revenue_cost"
PRE_REVENUE_IDENTITY_KEYS = frozenset({"stock:SH:688759"})

CANONICAL_FIELD_ALIASES = {
    "operating_revenue": REQUIRED_LINE_ITEM_FIELDS["operating_revenue"],
    "operating_cost": REQUIRED_LINE_ITEM_FIELDS["operating_cost"],
    "taxes_and_surcharges": REQUIRED_LINE_ITEM_FIELDS["taxes_and_surcharges"],
    "selling_expense": REQUIRED_LINE_ITEM_FIELDS["selling_expense"],
    "admin_expense": REQUIRED_LINE_ITEM_FIELDS["admin_expense"],
    "rd_expense": REQUIRED_LINE_ITEM_FIELDS["rd_expense"],
    "interest_expense": ("interest_expense", "interest_exp", "利息费用"),
    "finance_expense": ("finance_expense", "fin_exp", "财务费用"),
    "operating_cashflow": REQUIRED_LINE_ITEM_FIELDS["operating_cashflow"],
}


class StockFinancialCanonicalSourceBundleBlocked(Exception):
    """Raised when this dry-run/probe runner is asked to execute/write."""


def validate_source_bundle_request(*, execute_requested: bool) -> None:
    if execute_requested:
        raise StockFinancialCanonicalSourceBundleBlocked(
            "this runner is source-bundle dry-run only; execute/write is not implemented in this gate"
        )


def parse_symbol_shard(value: str | None) -> tuple[int, int] | None:
    if value in (None, ""):
        return None
    parts = str(value).split("/")
    if len(parts) != 2:
        raise ValueError("symbol_shard must use N/M format")
    shard_index = int(parts[0])
    shard_total = int(parts[1])
    if shard_total <= 0 or shard_index <= 0 or shard_index > shard_total:
        raise ValueError("symbol_shard must satisfy 1 <= N <= M")
    return shard_index, shard_total


def select_probe_symbols(
    symbols: Sequence[StockFinancialSymbol],
    *,
    max_symbols: int | None,
    symbol_shard: str | None,
    full_fetch_confirmed: bool,
    default_sample_size: int = DEFAULT_SMALL_SAMPLE_SIZE,
) -> tuple[list[StockFinancialSymbol], dict[str, Any]]:
    selected = list(symbols)
    shard = parse_symbol_shard(symbol_shard)
    if shard:
        shard_index, shard_total = shard
        selected = [symbol for idx, symbol in enumerate(selected) if idx % shard_total == shard_index - 1]

    if full_fetch_confirmed and (max_symbols is None or max_symbols <= 0):
        capped = selected
        selection_mode = "full_fetch"
    else:
        cap = max_symbols if max_symbols and max_symbols > 0 else default_sample_size
        capped = selected[:cap]
        selection_mode = "symbol_shard_sample" if shard else "small_sample"

    metadata = {
        "active_universe_count": len(symbols),
        "post_shard_symbol_count": len(selected),
        "selected_symbol_count": len(capped),
        "max_symbols": max_symbols,
        "symbol_shard": symbol_shard,
        "full_fetch_confirmed": bool(full_fetch_confirmed),
        "selection_mode": selection_mode,
        "default_sample_size": default_sample_size,
        "bounded": not (full_fetch_confirmed and (max_symbols is None or max_symbols <= 0)),
    }
    return capped, metadata


def build_source_bundle_report(
    *,
    source_trade_date: str,
    expected_identity_keys: Sequence[str],
    tdx_rows: Sequence[Mapping[str, Any]],
    tushare_rows: Sequence[Mapping[str, Any]],
    daily_basic_rows: Sequence[Mapping[str, Any]],
    forecast_rows: Sequence[Mapping[str, Any]],
    baseline: Mapping[str, Any] | None = None,
    source_probe: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    raw_expected = [str(key) for key in expected_identity_keys]
    expected = sorted(set(raw_expected))
    probe = dict(source_probe or {})
    financial_only = bool(probe.get("financial_only"))
    affair_policy = bool(
        financial_only
        and probe.get("financial_source_policy_version") == FINANCIAL_SOURCE_POLICY_VERSION
        and probe.get("forecast_disabled") is True
    )
    financial_source_name = SOURCE_MOOTDX_AFFAIR if financial_only else SOURCE_TUSHARE_FALLBACK
    financial_integrity_errors: list[str] = []
    if affair_policy:
        all_financial_rows = [*tdx_rows, *tushare_rows]
        computed_final_keys = sorted(group_rows_by_identity_key(all_financial_rows))
        final_row_hashes = [
            canonical_payload_sha256(dict(row))
            for row in all_financial_rows
        ]
        financial_grains = [
            (
                str(row.get("stock_identity_key") or ""),
                str(row.get("report_period") or ""),
                str(row.get("announcement_date") or ""),
            )
            for row in all_financial_rows
        ]
        computed_warning_keys = sorted(
            str(row.get("stock_identity_key") or "")
            for row in all_financial_rows
            if is_financial_null_warning_row(row)
        )
        registered_warning_keys = sorted(
            str(key) for key in probe.get("financial_null_warning_identity_keys") or []
        )
        registered_fresh_keys = sorted(
            str(key) for key in probe.get("financial_fresh_identity_keys") or []
        )
        registered_carried_keys = sorted(
            str(key) for key in probe.get("financial_carried_forward_identity_keys") or []
        )
        exact_duplicate_dropped_count = int(
            probe.get("financial_exact_duplicate_dropped_count") or 0
        )
        exact_duplicate_dropped_samples = [
            str(value)
            for value in probe.get(
                "financial_exact_duplicate_dropped_row_hash_samples"
            )
            or []
        ]
        exact_duplicate_dropped_hash = str(
            probe.get(
                "financial_exact_duplicate_dropped_row_hashes_sha256"
            )
            or ""
        )
        legacy_conflict_count = int(
            probe.get("financial_legacy_grain_conflict_resolved_count")
            or 0
        )
        legacy_conflict_manifest_sha256 = str(
            probe.get("financial_legacy_grain_conflict_manifest_sha256")
            or ""
        )
        legacy_conflict_samples = list(
            probe.get("financial_legacy_grain_conflict_samples") or []
        )
        package_manifest = probe.get("package_manifest") or probe.get("affair_file_manifest") or []
        package_manifest_valid = True
        if package_manifest:
            package_manifest_valid = bool(
                isinstance(package_manifest, Sequence)
                and not isinstance(package_manifest, (str, bytes, bytearray))
                and len(package_manifest) == 10
                and int(probe.get("package_count") or len(package_manifest)) == len(package_manifest)
                and str(
                    probe.get("package_manifest_sha256")
                    or probe.get("affair_file_manifest_sha256")
                    or ""
                )
                == canonical_payload_sha256(list(package_manifest))
                and len(
                    {
                        str(item.get("filename") or "")
                        for item in package_manifest
                        if isinstance(item, Mapping)
                    }
                )
                == len(package_manifest)
            )
        checks = {
            "expected_identity_unique": len(raw_expected) == len(expected) and bool(expected),
            "registered_expected_count": int(probe.get("expected_identity_count") or -1) == len(expected),
            "registered_expected_hash": str(probe.get("expected_identity_sha256") or "") == identity_keys_sha256(expected),
            "final_identity_exact": computed_final_keys == expected,
            "registered_final_count": int(probe.get("financial_final_identity_count") or -1) == len(computed_final_keys),
            "registered_final_hash": str(probe.get("financial_final_identity_sha256") or "") == identity_keys_sha256(computed_final_keys),
            "registered_final_row_count": int(probe.get("financial_final_row_count") or -1) == len(all_financial_rows),
            "registered_final_rows_hash": str(probe.get("financial_final_rows_sha256") or "") == canonical_payload_sha256(all_financial_rows),
            "final_exact_rows_unique": len(final_row_hashes) == len(set(final_row_hashes)),
            "financial_grain_unique": len(financial_grains) == len(set(financial_grains)),
            "exact_duplicate_count_nonnegative": exact_duplicate_dropped_count >= 0,
            "pre_dedup_row_count": int(probe.get("financial_pre_dedup_row_count") or -1) == len(all_financial_rows) + exact_duplicate_dropped_count,
            "exact_duplicate_hash_present": len(exact_duplicate_dropped_hash) == 64,
            "exact_duplicate_samples_bounded": len(exact_duplicate_dropped_samples) <= min(20, exact_duplicate_dropped_count),
            "exact_duplicate_sample_hashes_valid": all(len(value) == 64 for value in exact_duplicate_dropped_samples),
            "legacy_conflict_count_nonnegative": legacy_conflict_count >= 0,
            "before_legacy_resolution_row_count": int(probe.get("financial_before_legacy_resolution_row_count") or -1) == len(all_financial_rows) + exact_duplicate_dropped_count + legacy_conflict_count,
            "legacy_conflict_manifest_hash_present": len(legacy_conflict_manifest_sha256) == 64,
            "legacy_conflict_samples_bounded": len(legacy_conflict_samples) <= min(20, legacy_conflict_count),
            "legacy_conflict_sample_shape": all(
                isinstance(item, Mapping)
                and str(item.get("stock_identity_key") or "") in set(expected)
                and len(str(item.get("selected_row_sha256") or "")) == 64
                and len(str(item.get("rejected_row_sha256") or "")) == 64
                for item in legacy_conflict_samples
            ),
            "fresh_count": int(probe.get("financial_fresh_coverage_count") or 0) == len(registered_fresh_keys),
            "fresh_hash": str(probe.get("financial_fresh_identity_sha256") or "") == identity_keys_sha256(registered_fresh_keys),
            "fresh_subset": set(registered_fresh_keys).issubset(set(expected)),
            "carried_count": int(probe.get("financial_carried_forward_count") or 0) == len(registered_carried_keys),
            "carried_hash": str(probe.get("financial_carried_forward_identity_sha256") or "") == identity_keys_sha256(registered_carried_keys),
            "carried_subset": set(registered_carried_keys).issubset(set(expected)),
            "warning_keys_unique": len(computed_warning_keys) == len(set(computed_warning_keys)),
            "warning_keys_exact": computed_warning_keys == registered_warning_keys,
            "warning_count": int(probe.get("financial_null_warning_identity_count") or 0) == len(computed_warning_keys),
            "warning_hash": str(probe.get("financial_null_warning_identity_sha256") or "") == identity_keys_sha256(computed_warning_keys),
            "package_manifest": package_manifest_valid,
        }
        financial_integrity_errors = sorted(name for name, passed in checks.items() if not passed)
    tdx_valid, tdx_exclusions = asof_filter_rows(tdx_rows, source_trade_date, SOURCE_TDX)
    tushare_valid, tushare_exclusions = asof_filter_rows(tushare_rows, source_trade_date, financial_source_name)
    forecast_valid, forecast_exclusions = asof_filter_rows(forecast_rows, source_trade_date, "tushare.forecast") if not financial_only else ([], Counter())
    daily_basic_by_key = {str(row.get("stock_identity_key")): dict(row) for row in daily_basic_rows if row.get("stock_identity_key")}
    forecast_by_key = latest_forecast_by_identity(forecast_valid)

    tdx_by_key = group_rows_by_identity(normalize_source_rows(tdx_valid, SOURCE_TDX))
    tushare_by_key = group_rows_by_identity(normalize_source_rows(tushare_valid, financial_source_name))
    selected_bundle_rows: list[dict[str, Any]] = []
    missing_line_items: list[dict[str, Any]] = []
    missing_source_identities: list[str] = []
    missing_daily_basic_total_mv: list[str] = []
    source_counts: Counter[str] = Counter()
    interest_fallback_count = 0
    forecast_covered = 0
    warning_distribution: Counter[str] = Counter()
    missing_line_item_field_distribution: Counter[str] = Counter()
    missing_line_item_combo_distribution: Counter[str] = Counter()
    finance_sector_policy_warning_count = 0
    pre_revenue_policy_warning_count = 0
    historical_core_line_item_missing_count = 0
    latest_core_line_item_missing_fallback_count = 0
    finance_sector_industry_distribution: Counter[str] = Counter()
    pre_revenue_samples: list[dict[str, Any]] = []

    for identity_key in expected:
        selected_source, selected_rows = select_identity_rows(
            tdx_by_key.get(identity_key) or [],
            tushare_by_key.get(identity_key) or [],
            preferred_fallback_source=financial_source_name,
        )
        if not selected_rows:
            missing_source_identities.append(identity_key)
            missing_line_items.append({"stock_identity_key": identity_key, "missing": ["source_rows"]})
            missing_line_item_field_distribution.update(["source_rows"])
            missing_line_item_combo_distribution.update(["source_rows"])
            continue
        source_counts[selected_source] += 1
        daily_basic = daily_basic_by_key.get(identity_key) or {}
        if first_decimal(daily_basic, "total_mv") is None:
            missing_daily_basic_total_mv.append(identity_key)
        warning_rows = [row for row in selected_rows if is_financial_null_warning_row(row)]
        if warning_rows:
            if len(warning_rows) != 1 or len(selected_rows) != 1:
                financial_integrity_errors.append("financial_null_warning_row_not_singleton")
                continue
            warning_distribution.update([FINANCIAL_NULL_WARNING_CODE])
            warning_row = dict(warning_rows[0])
            raw_payload = dict(warning_row.get("raw_payload") or {})
            raw_payload["daily_basic"] = json_safe(daily_basic)
            warning_row.update(
                {
                    "source_trade_date": source_trade_date,
                    "industry": canonical_industry(warning_row, daily_basic),
                    "forecast_type": None,
                    "forecast_score": None,
                    "total_mv": daily_basic.get("total_mv"),
                    "circ_mv": daily_basic.get("circ_mv"),
                    "raw_payload": raw_payload,
                    "financial_warning_json": {
                        "warnings": [FINANCIAL_NULL_WARNING_CODE],
                        "reason": raw_payload.get("reason"),
                        "severity": "P1",
                    },
                }
            )
            selected_bundle_rows.append(warning_row)
            continue
        forecast_type = forecast_by_key.get(identity_key, {}).get("forecast_type")
        if forecast_type:
            forecast_covered += 1
        identity_has_missing_line_item = False
        identity_missing_fields: set[str] = set()
        identity_latest_missing_fields: set[str] = set()
        identity_has_usable_core_row = False
        identity_policy_warning_codes: set[str] = set()
        identity_policy_missing_fields: set[str] = set()
        industry = canonical_industry(selected_rows[0] if selected_rows else {}, daily_basic)
        for row_index, row in enumerate(selected_rows):
            row, row_warnings = apply_line_item_fallback_policy(row, is_latest=(row_index == 0))
            finance_policy_applies = is_finance_sector(industry)
            if finance_policy_applies:
                row_warnings[FINANCE_SECTOR_POLICY_WARNING] += 1
                identity_policy_warning_codes.add(FINANCE_SECTOR_POLICY_WARNING)
            missing_fields = missing_p0_line_items(row)
            if missing_fields:
                policy_warning = line_item_policy_warning_code(
                    identity_key=identity_key,
                    row=row,
                    daily_basic=daily_basic,
                    missing_fields=missing_fields,
                )
                if finance_policy_applies:
                    identity_policy_missing_fields.update(missing_fields)
                elif policy_warning:
                    row_warnings[policy_warning] += 1
                    identity_policy_warning_codes.add(policy_warning)
                    identity_policy_missing_fields.update(missing_fields)
                elif row_index > 0:
                    row_warnings[HISTORICAL_CORE_LINE_ITEMS_MISSING_WARNING] += 1
                    historical_core_line_item_missing_count += 1
                else:
                    row_warnings[LATEST_CORE_LINE_ITEMS_MISSING_FALLBACK_WARNING] += 1
                    identity_latest_missing_fields.update(missing_fields)
                    latest_core_line_item_missing_fallback_count += 1
            else:
                identity_has_usable_core_row = True
            warning_distribution.update(row_warnings)
            if first_decimal(row, "interest_expense", "interest_exp", "利息费用") is None and first_decimal(row, "finance_expense", "fin_exp", "财务费用") is not None:
                interest_fallback_count += 1
            enriched = {
                **row,
                "source_type": selected_source,
                "source_trade_date": source_trade_date,
                "industry": industry,
                "forecast_type": forecast_type,
                "total_mv": daily_basic.get("total_mv"),
                "circ_mv": daily_basic.get("circ_mv"),
                "raw_payload": {
                    "source_row": json_safe(row),
                    "daily_basic": json_safe(daily_basic),
                    "forecast": json_safe(forecast_by_key.get(identity_key) or {}),
                },
                "financial_warning_json": {"warnings": sorted(row_warnings.keys())},
            }
            if FINANCE_SECTOR_POLICY_WARNING in row_warnings:
                enriched["sector_policy_json"] = finance_sector_policy_json(industry)
                enriched["financial_warning_json"].update(enriched["sector_policy_json"])
            if PRE_REVENUE_POLICY_WARNING in row_warnings:
                enriched["sector_policy_json"] = pre_revenue_policy_json()
                enriched["financial_warning_json"].update(enriched["sector_policy_json"])
            selected_bundle_rows.append(enriched)
        if FINANCE_SECTOR_POLICY_WARNING in identity_policy_warning_codes:
            finance_sector_policy_warning_count += 1
            finance_sector_industry_distribution.update([industry or "unknown"])
        if PRE_REVENUE_POLICY_WARNING in identity_policy_warning_codes:
            pre_revenue_policy_warning_count += 1
            pre_revenue_samples.append(
                {"stock_identity_key": identity_key, "industry": industry, "missing": sorted(identity_policy_missing_fields)}
            )
        if identity_latest_missing_fields and not identity_has_usable_core_row:
            identity_has_missing_line_item = True
            identity_missing_fields.update(identity_latest_missing_fields)
        if identity_has_missing_line_item:
            missing = sorted(identity_missing_fields)
            missing_line_item_field_distribution.update(missing)
            missing_line_item_combo_distribution.update(["+".join(missing)])
            missing_line_items.append(
                {
                    "stock_identity_key": identity_key,
                    "missing": missing,
                }
            )

    exclusions = Counter()
    for counts in (tdx_exclusions, tushare_exclusions, forecast_exclusions):
        exclusions.update(counts)
    duplicate_count = len({row.get("stock_identity_key") for row in selected_bundle_rows}) - len(expected) if selected_bundle_rows else 0
    duplicate_count = max(0, duplicate_count)

    tushare_stats = dict(probe.get("tushare_stats") or {})

    def probe_int(name: str, default: int = 0) -> int:
        value = probe.get(name)
        if value is None:
            return default
        return int(value or 0)

    quality_items = [
        quality_item(
            "financial_degraded_lineage_integrity",
            "P0",
            "passed" if not financial_integrity_errors else "failed",
            "all lineage checks pass",
            str(len(financial_integrity_errors)),
            {"failed_checks": sorted(set(financial_integrity_errors))},
        ),
        quality_item(
            "canonical_source_line_items",
            "P1" if affair_policy else "P0",
            "passed" if not missing_line_items else ("warning" if affair_policy else "failed"),
            "0 missing",
            str(len(missing_line_items)),
            {
                "samples": missing_line_items[:20],
                "policy": (
                    "incomplete Affair metrics become NULL/P1 without blocking Fast Lane"
                    if affair_policy
                    else None
                ),
            },
        ),
        quality_item(
            "canonical_source_missing_identity",
            "P0",
            "passed" if not missing_source_identities else "failed",
            "0 missing",
            str(len(missing_source_identities)),
            {"samples": missing_source_identities[:20]},
        ),
        quality_item(
            "daily_basic_total_mv_coverage",
            "P1" if financial_only else "P0",
            "passed" if not missing_daily_basic_total_mv else ("warning" if financial_only else "failed"),
            "0 missing",
            str(len(missing_daily_basic_total_mv)),
            {"samples": missing_daily_basic_total_mv[:20]},
        ),
        quality_item(
            "duplicate_identity_key",
            "P0",
            "passed" if duplicate_count == 0 else "failed",
            "0",
            str(duplicate_count),
            {},
        ),
    ]
    if financial_only and probe_int("financial_null_warning_identity_count"):
        quality_items.append(
            quality_item(
                FINANCIAL_NULL_WARNING_CODE,
                "P1",
                "warning",
                "0",
                str(probe_int("financial_null_warning_identity_count")),
                {
                    "samples": list(probe.get("financial_null_warning_identity_keys") or [])[:20],
                    "policy": "preserve frozen-universe identity with NULL financial metrics",
                },
            )
        )
    if financial_only and probe_int("financial_exact_duplicate_dropped_count"):
        quality_items.append(
            quality_item(
                "financial_exact_duplicate_rows_dropped",
                "P1",
                "warning",
                "0",
                str(probe_int("financial_exact_duplicate_dropped_count")),
                {
                    "row_hash_manifest_sha256": probe.get(
                        "financial_exact_duplicate_dropped_row_hashes_sha256"
                    ),
                    "samples": list(
                        probe.get(
                            "financial_exact_duplicate_dropped_row_hash_samples"
                        )
                        or []
                    )[:20],
                    "policy": "exact canonical duplicates are removed; same-grain payload conflicts remain P0",
                },
            )
        )
    if financial_only and probe_int("financial_legacy_grain_conflict_resolved_count"):
        quality_items.append(
            quality_item(
                "financial_legacy_snapshot_grain_conflict_resolved",
                "P1",
                "warning",
                "0",
                str(
                    probe_int(
                        "financial_legacy_grain_conflict_resolved_count"
                    )
                ),
                {
                    "manifest_sha256": probe.get(
                        "financial_legacy_grain_conflict_manifest_sha256"
                    ),
                    "samples": list(
                        probe.get(
                            "financial_legacy_grain_conflict_samples"
                        )
                        or []
                    )[:20],
                    "policy": "immutable previous snapshot keeps its first row; fresh Affair same-grain conflicts remain P0",
                },
            )
        )
    if source_counts[SOURCE_TUSHARE_FALLBACK]:
        quality_items.append(
            quality_item("tushare_fallback_used", "P1", "warning", "0", str(source_counts[SOURCE_TUSHARE_FALLBACK]), {})
        )
    if not financial_only and forecast_covered < len(expected):
        quality_items.append(
            quality_item(
                "forecast_type_coverage",
                "P1",
                "warning",
                str(len(expected)),
                str(forecast_covered),
                {"missing_count": len(expected) - forecast_covered},
            )
        )
    if financial_only and probe_int("announcement_date_unverified_count"):
        quality_items.append(
            quality_item(
                "affair_announcement_date_unverified",
                "P1",
                "warning",
                "0",
                str(probe_int("announcement_date_unverified_count")),
                {"policy": "carry_previous_snapshot_when_cutoff_cannot_be_proven"},
            )
        )
    if interest_fallback_count:
        quality_items.append(
            quality_item("interest_expense_missing_finance_expense_used", "P1", "warning", "0", str(interest_fallback_count), {})
        )
    if warning_distribution:
        quality_items.append(
            quality_item(
                "line_item_fallback_warning_distribution",
                "P1",
                "warning",
                "0",
                str(sum(warning_distribution.values())),
                {"warning_distribution": dict(sorted(warning_distribution.items()))},
            )
        )
    if finance_sector_policy_warning_count:
        quality_items.append(
            quality_item(
                FINANCE_SECTOR_POLICY_WARNING,
                "P1",
                "warning",
                "0",
                str(finance_sector_policy_warning_count),
                {"industry_distribution": dict(sorted(finance_sector_industry_distribution.items()))},
            )
        )
    if pre_revenue_policy_warning_count:
        quality_items.append(
            quality_item(
                PRE_REVENUE_POLICY_WARNING,
                "P1",
                "warning",
                "0",
                str(pre_revenue_policy_warning_count),
                {"samples": pre_revenue_samples[:20]},
            )
        )
    if latest_core_line_item_missing_fallback_count:
        quality_items.append(
            quality_item(
                LATEST_CORE_LINE_ITEMS_MISSING_FALLBACK_WARNING,
                "P1",
                "warning",
                "0",
                str(latest_core_line_item_missing_fallback_count),
                {"reason": "latest report has missing core line items; prior as-of usable report period remains available"},
            )
        )
    if historical_core_line_item_missing_count:
        quality_items.append(
            quality_item(
                HISTORICAL_CORE_LINE_ITEMS_MISSING_WARNING,
                "P2",
                "warning",
                "0",
                str(historical_core_line_item_missing_count),
                {"reason": "historical quarter gaps do not block latest canonical row readiness"},
            )
        )
    if not any(item["severity"] == "P1" for item in quality_items):
        quality_items.append(quality_item("source_bundle_warning_distribution", "P1", "passed", "reviewed", "0", {}))
    quality_items.append(
        quality_item(
            "asof_exclusions",
            "P2",
            "warning" if exclusions["future"] or exclusions["missing_announcement"] else "passed",
            "0",
            str(exclusions["future"] + exclusions["missing_announcement"]),
            dict(exclusions),
        )
    )
    if probe.get("source_fetch_enabled") is False:
        quality_items.append(
            quality_item(
                "source_fetch_enabled",
                "P1" if financial_only else "P0",
                "warning" if financial_only else "failed",
                "true",
                "false",
                {
                    "reason": "financial source probe was not enabled; previous snapshot/NULL fallback used",
                    "financial_degraded_but_fastlane_allowed": bool(
                        probe.get("financial_degraded_but_fastlane_allowed")
                    ),
                },
            )
        )
    if probe.get("incremental_delta_guard_blocked"):
        quality_items.append(
            quality_item(
                "incremental_delta_full_fetch_guard",
                "P0",
                "failed",
                f"<= {probe.get('incremental_delta_guard_threshold_ratio')}",
                str(probe.get("incremental_delta_ratio")),
                {
                    "delta_symbol_count": probe.get("delta_symbol_count"),
                    "active_universe_count": probe.get("active_universe_count"),
                    "delta_reason_distribution": probe.get("delta_reason_distribution") or {},
                    "reason": probe.get("incremental_delta_guard_reason"),
                },
            )
        )
    financial_only_p1_errors = {"announcement_date_unverified"}
    for error in probe.get("source_errors") or []:
        error_code = str(error.get("error") or "")
        recovered_financial_error = bool(
            financial_only
            and probe.get("financial_degraded_but_fastlane_allowed") is True
            and not financial_integrity_errors
        )
        severity = "P1" if financial_only and (error_code in financial_only_p1_errors or recovered_financial_error) else "P0"
        quality_items.append(
            quality_item("source_error", severity, "warning" if severity == "P1" else "failed", "0", "1", {"source": error.get("source"), "error": error_code})
        )

    blockers = []
    if missing_line_items and not affair_policy:
        blockers.append("canonical_source_line_items_missing")
    if missing_source_identities:
        blockers.append("canonical_source_missing_identity")
    if missing_daily_basic_total_mv:
        if not financial_only:
            blockers.append("daily_basic_total_mv_missing")
    if duplicate_count:
        blockers.append("duplicate_identity_key")
    if financial_integrity_errors:
        blockers.append("financial_degraded_lineage_integrity_failed")
    conflicts = ((baseline or {}).get("conflicts") or {})
    for name, count in conflicts.items():
        if int(count or 0) != 0:
            blockers.append(name)
    if probe.get("source_fetch_enabled") is False and not financial_only:
        blockers.append("source_fetch_not_enabled")
    if probe.get("incremental_delta_guard_blocked"):
        blockers.append("incremental_delta_full_fetch_guard")
    for error in probe.get("source_errors") or []:
        error_code = str(error.get("error") or "")
        recovered_financial_error = bool(
            financial_only
            and probe.get("financial_degraded_but_fastlane_allowed") is True
            and not financial_integrity_errors
        )
        if not (financial_only and (error_code in financial_only_p1_errors or recovered_financial_error)):
            blockers.append(f"source_error:{error.get('source')}")

    quality = summarize_quality(quality_items)
    result = "PASS" if quality["P0"] == 0 and not blockers else "BLOCKED"
    return json_safe(
        {
            "result": result,
            "stage": "N1 stock_financial canonical source bundle dry-run",
            "layer_role": "N1_ingestion",
            "source_trade_date": source_trade_date,
            "target_source_batch_id": BATCH_ID,
            "target_source_version": SOURCE_VERSION,
            "previous_source_version": PREVIOUS_SOURCE_VERSION,
            "financial_metric_version": FINANCIAL_METRIC_VERSION,
            "financial_source_policy_version": (
                FINANCIAL_SOURCE_POLICY_VERSION if affair_policy else None
            ),
            "financial_authority": SOURCE_MOOTDX_AFFAIR if affair_policy else None,
            "forecast_disabled": bool(affair_policy),
            "financial_degraded_but_fastlane_allowed": bool(
                probe.get("financial_degraded_but_fastlane_allowed")
            ),
            "expected_rows": len(expected),
            "source_bundle_rows": len(selected_bundle_rows),
            "source_coverage": {
                "active_universe_count": probe_int("active_universe_count", len(expected)),
                "selected_symbol_count": probe_int("selected_symbol_count", len(expected)),
                "tdx_primary_count": int(source_counts[SOURCE_TDX]),
                "mootdx_affair_count": int(source_counts[SOURCE_MOOTDX_AFFAIR]),
                "tushare_fallback_count": int(source_counts[SOURCE_TUSHARE_FALLBACK]),
                "tushare_income_ok_count": int(tushare_stats.get("tushare_income_ok_count") or 0),
                "tushare_cashflow_ok_count": int(tushare_stats.get("tushare_cashflow_ok_count") or 0),
                "forecast_ok_count": int(tushare_stats.get("forecast_ok_count") or 0),
                "daily_basic_ok_count": int(tushare_stats.get("daily_basic_ok_count") or 0),
                "cache_hit_count": int(tushare_stats.get("cache_hit_count") or 0),
                "cache_miss_count": int(tushare_stats.get("cache_miss_count") or 0),
                "missing_line_item_count": len(missing_line_items),
                "missing_line_item_field_distribution": dict(sorted(missing_line_item_field_distribution.items())),
                "missing_line_item_combo_distribution": dict(missing_line_item_combo_distribution.most_common()),
                "warning_distribution": dict(sorted(warning_distribution.items())),
                "finance_sector_policy_warning_count": finance_sector_policy_warning_count,
                "finance_sector_policy_industry_distribution": dict(sorted(finance_sector_industry_distribution.items())),
                "pre_revenue_policy_warning_count": pre_revenue_policy_warning_count,
                "pre_revenue_policy_samples": pre_revenue_samples[:20],
                "historical_core_line_item_missing_count": historical_core_line_item_missing_count,
                "latest_core_line_item_missing_fallback_count": latest_core_line_item_missing_fallback_count,
                "future_excluded_count": int(exclusions["future"]),
                "missing_announcement_date_excluded_count": int(exclusions["missing_announcement"]),
                "forecast_coverage_count": forecast_covered,
                "interest_expense_missing_finance_expense_used_count": interest_fallback_count,
                "daily_basic_total_mv_missing_count": len(missing_daily_basic_total_mv),
                "source_errors": probe.get("source_errors") or [],
                "financial_refresh_mode": probe.get("financial_refresh_mode"),
                "financial_fresh_coverage_count": probe_int("financial_fresh_coverage_count"),
                "financial_fresh_coverage_ratio": probe.get("financial_fresh_coverage_ratio"),
                "financial_carried_forward_count": probe_int("financial_carried_forward_count"),
                "financial_null_warning_identity_count": probe_int("financial_null_warning_identity_count"),
                "financial_final_identity_count": probe_int("financial_final_identity_count"),
                "financial_final_identity_sha256": probe.get("financial_final_identity_sha256"),
                "financial_degraded_but_fastlane_allowed": bool(
                    probe.get("financial_degraded_but_fastlane_allowed")
                ),
                "delta_symbol_count": int(probe.get("delta_symbol_count") or 0),
                "delta_reason_distribution": probe.get("delta_reason_distribution") or {},
                "incremental_delta_ratio": probe.get("incremental_delta_ratio"),
                "incremental_delta_guard_blocked": bool(probe.get("incremental_delta_guard_blocked")),
            },
            "rows_sample": selected_bundle_rows[:5],
            "blockers": blockers,
            "quality": {"p0_count": quality["P0"], "p1_count": quality["P1"], "p2_count": quality["P2"], "items": quality_items},
            "baseline": baseline or {},
            "source_probe": source_probe or {},
            "side_effects": default_side_effects(),
        }
    )


def asof_filter_rows(rows: Sequence[Mapping[str, Any]], source_trade_date: str, default_source: str) -> tuple[list[dict[str, Any]], Counter[str]]:
    accepted: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for row in rows:
        if is_financial_null_warning_row(row):
            accepted.append({**dict(row), "source_type": source_type_or_default(row, default_source)})
            counts["financial_null_warning"] += 1
            continue
        ann = optional_date_text(row.get("announcement_date") or row.get("ann_date"))
        if not ann:
            if row.get("asof_safe"):
                accepted.append({**dict(row), "announcement_date": source_trade_date, "source_type": source_type_or_default(row, default_source)})
            else:
                counts["missing_announcement"] += 1
            continue
        if ann > source_trade_date:
            counts["future"] += 1
            continue
        accepted.append({**dict(row), "announcement_date": ann, "source_type": source_type_or_default(row, default_source)})
    return accepted, counts


def source_type_or_default(row: Mapping[str, Any], default: str) -> str:
    raw_source = str(row.get("source_type") or row.get("source") or "").lower()
    if "affair" in raw_source:
        return SOURCE_MOOTDX_AFFAIR
    if row.get("source_type") or row.get("source"):
        return source_type(row)
    return default


def normalize_source_rows(rows: Sequence[Mapping[str, Any]], default_source: str) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        item = dict(row)
        item["source_type"] = source_type_or_default(item, default_source)
        for canonical, aliases in CANONICAL_FIELD_ALIASES.items():
            if item.get(canonical) in (None, ""):
                value = first_present(item, aliases)
                if value is not None:
                    item[canonical] = value
        if not item.get("stock_identity_key"):
            exchange = str(item.get("exchange") or "").upper()
            code = str(item.get("code") or "").strip()
            if not exchange and item.get("ts_code"):
                ts_code = str(item["ts_code"])
                code, exchange = ts_code.split(".", 1)
                exchange = exchange.upper()
            if exchange and code:
                item["stock_identity_key"] = f"stock:{exchange}:{code}"
        normalized.append(item)
    return normalized


def first_present(row: Mapping[str, Any], fields: Sequence[str]) -> Any:
    for field in fields:
        if row.get(field) not in (None, ""):
            return row.get(field)
    return None


def group_rows_by_identity(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        identity_key = row.get("stock_identity_key")
        if identity_key and is_financial_null_warning_row(row):
            grouped[str(identity_key)].append(dict(row))
            continue
        report_period = optional_date_text(row.get("report_period") or row.get("end_date"))
        if not identity_key or not report_period:
            continue
        grouped[str(identity_key)].append({**dict(row), "report_period": report_period})
    return {key: sorted(value, key=lambda row: str(row.get("report_period") or ""), reverse=True) for key, value in grouped.items()}


def select_identity_rows(
    tdx_rows: Sequence[Mapping[str, Any]],
    tushare_rows: Sequence[Mapping[str, Any]],
    *,
    preferred_fallback_source: str = SOURCE_TUSHARE_FALLBACK,
) -> tuple[str, list[dict[str, Any]]]:
    if tdx_rows and not all_rows_missing_required_line_items(tdx_rows):
        if any("affair" in str(row.get("source_type") or row.get("source") or "").lower() for row in tdx_rows):
            return SOURCE_MOOTDX_AFFAIR, [dict(row) for row in tdx_rows]
        return SOURCE_TDX, [dict(row) for row in tdx_rows]
    if tushare_rows:
        return preferred_fallback_source, [dict(row) for row in tushare_rows]
    if tdx_rows:
        return SOURCE_TDX, [dict(row) for row in tdx_rows]
    return SOURCE_TDX, []


def all_rows_missing_required_line_items(rows: Sequence[Mapping[str, Any]]) -> bool:
    return all(missing_p0_line_items(row) for row in rows)


def missing_required_line_items(row: Mapping[str, Any]) -> list[str]:
    missing = []
    for group_name, aliases in REQUIRED_LINE_ITEM_FIELDS.items():
        if first_decimal(row, *aliases) is None:
            missing.append(group_name)
    return missing


def missing_p0_line_items(row: Mapping[str, Any]) -> list[str]:
    missing = []
    for group_name, aliases in P0_LINE_ITEM_FIELDS.items():
        if first_decimal(row, *aliases) is None:
            missing.append(group_name)
    return missing


def canonical_industry(row: Mapping[str, Any], daily_basic: Mapping[str, Any] | None = None) -> str | None:
    for source in (row, daily_basic or {}):
        value = source.get("industry") or source.get("stock_industry")
        if value not in (None, ""):
            return str(value).strip()
        raw_payload = source.get("raw_payload")
        if isinstance(raw_payload, Mapping):
            value = raw_payload.get("industry") or raw_payload.get("stock_industry")
            if value not in (None, ""):
                return str(value).strip()
    return None


def is_finance_sector(industry: str | None) -> bool:
    return str(industry or "").strip() in FINANCE_SECTOR_INDUSTRIES


def is_pre_revenue_policy_candidate(
    *,
    identity_key: str,
    missing_fields: Sequence[str],
) -> bool:
    missing = set(missing_fields)
    return identity_key in PRE_REVENUE_IDENTITY_KEYS and {"operating_revenue", "operating_cost"}.issubset(missing)


def line_item_policy_warning_code(
    *,
    identity_key: str,
    row: Mapping[str, Any],
    daily_basic: Mapping[str, Any] | None,
    missing_fields: Sequence[str],
) -> str | None:
    industry = canonical_industry(row, daily_basic)
    if is_finance_sector(industry):
        return FINANCE_SECTOR_POLICY_WARNING
    if is_pre_revenue_policy_candidate(identity_key=identity_key, missing_fields=missing_fields):
        return PRE_REVENUE_POLICY_WARNING
    return None


def finance_sector_policy_json(industry: str | None) -> dict[str, Any]:
    return {
        "sector_policy": FINANCE_SECTOR_POLICY_WARNING,
        "industry": industry,
        "severity": "P1",
        "disabled_components": [
            "report_core_profit",
            "cash_realization_rate",
            "core_profit_ttm",
            "pe_core",
            "score",
        ],
    }


def pre_revenue_policy_json() -> dict[str, Any]:
    return {
        "sector_policy": PRE_REVENUE_POLICY_WARNING,
        "severity": "P1",
        "disabled_components": [
            "report_core_profit",
            "cash_realization_rate",
            "core_profit_ttm",
            "pe_core",
            "score",
        ],
    }


def apply_line_item_fallback_policy(row: Mapping[str, Any], *, is_latest: bool) -> tuple[dict[str, Any], Counter[str]]:
    item = dict(row)
    warnings: Counter[str] = Counter()
    for field, warning_code in ZERO_FALLBACK_LINE_ITEM_WARNINGS.items():
        if first_decimal(item, *REQUIRED_LINE_ITEM_FIELDS[field]) is None:
            item[field] = "0"
            warnings[warning_code] += 1
    if first_decimal(item, *REQUIRED_LINE_ITEM_FIELDS["operating_cashflow"]) is None:
        warnings[OPERATING_CASHFLOW_WARNINGS["latest" if is_latest else "historical"]] += 1
    existing = item.get("financial_warning_json")
    existing_warnings: list[str] = []
    if isinstance(existing, Mapping):
        raw_warnings = existing.get("warnings") or []
        if isinstance(raw_warnings, Sequence) and not isinstance(raw_warnings, (str, bytes, bytearray)):
            existing_warnings = [str(warning) for warning in raw_warnings]
    if warnings or existing_warnings:
        item["financial_warning_json"] = {"warnings": sorted(set(existing_warnings) | set(warnings.keys()))}
    return item, warnings


def latest_forecast_by_identity(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        identity_key = str(row.get("stock_identity_key") or "")
        if not identity_key:
            continue
        forecast_type = row.get("forecast_type") or row.get("type")
        if not forecast_type:
            continue
        current = by_key.get(identity_key)
        if current is None or str(row.get("announcement_date") or "") > str(current.get("announcement_date") or ""):
            by_key[identity_key] = {**dict(row), "forecast_type": str(forecast_type)}
    return by_key


def build_snapshot_from_db(
    *,
    dsn: str,
    source_trade_date: str = TRADE_DATE,
    source_fetch_enabled: bool = False,
    max_symbols: int | None = None,
    symbol_shard: str | None = None,
    resume_cache_path: str | Path | None = None,
    rate_limit_ms: int = 0,
    full_fetch_confirmed: bool = False,
    incremental_enabled: bool = False,
    previous_snapshot_path: str | Path | None = None,
    snapshot_cache_path: str | Path | None = None,
    changed_identity_keys: Sequence[str] | None = None,
    full_rebuild_confirmed: bool = False,
    use_tdx_source: bool = True,
    tushare_concurrency: int = 1,
    tushare_token: str | None = None,
    financial_only: bool = True,
    affair_cache_dir: str | Path | None = None,
) -> dict[str, Any]:
    source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    with psycopg.connect(dsn, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_version, source_batch_id
                FROM common_active_source_version
                WHERE data_domain='stock' AND data_type='stock_financial' AND scope_key=%s
                """,
                (source_trade_date,),
            )
            active = dict(cur.fetchone() or {})
            active_version = str(active.get("source_version") or PREVIOUS_SOURCE_VERSION)
            cur.execute(
                """
                SELECT stock_identity_key, ts_code, code, exchange, report_period, announcement_date,
                       total_revenue, net_profit, source, raw_payload
                FROM stock_financial_metrics_fact
                WHERE source_trade_date=%s AND source_version=%s
                ORDER BY stock_identity_key
                """,
                (source_trade_date, active_version),
            )
            active_rows = [dict(row) for row in cur.fetchall()]
            announcement_dates = sorted(
                {
                    str(row.get("announcement_date"))
                    for row in active_rows
                    if row.get("announcement_date") not in (None, "")
                }
            )
            cur.execute(
                """
                SELECT source_version
                FROM common_active_source_version
                WHERE data_domain='stock' AND data_type='stock_daily_basic' AND scope_key=%s
                """,
                (source_trade_date,),
            )
            daily_basic_active = dict(cur.fetchone() or {})
            cur.execute(
                """
                SELECT db.stock_identity_key, db.total_mv, db.circ_mv, db.raw_payload,
                       si.industry, si.name, si.market
                FROM stock_daily_basic db
                LEFT JOIN stock_identity si ON si.stock_identity_key = db.stock_identity_key
                WHERE db.trade_date=%s AND db.source_version=%s
                ORDER BY db.stock_identity_key
                """,
                (source_trade_date, daily_basic_active.get("source_version")),
            )
            daily_basic_rows = [dict(row) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT source_version
                FROM common_active_source_version
                WHERE data_domain='stock' AND data_type='stock_daily' AND scope_key=%s
                """,
                (source_trade_date,),
            )
            stock_daily_active = dict(cur.fetchone() or {})
            cur.execute(
                """
                SELECT stock_identity_key
                FROM stock_daily_bar_fact
                WHERE trade_date=%s AND source_version=%s
                ORDER BY stock_identity_key
                """,
                (source_trade_date, stock_daily_active.get("source_version")),
            )
            frozen_stock_identity_keys = [
                str(row.get("stock_identity_key") or "")
                for row in cur.fetchall()
            ]

            def count(sql: str, params: Sequence[Any] = ()) -> int:
                cur.execute(sql, params)
                return int(cur.fetchone()["value"] or 0)

            baseline = {
                "active_stock_financial_source_version": active_version,
                "active_stock_financial_rows": len(active_rows),
                "active_stock_daily_basic_source_version": daily_basic_active.get("source_version"),
                "active_stock_daily_basic_rows": len(daily_basic_rows),
                "active_stock_daily_source_version": stock_daily_active.get("source_version"),
                "frozen_stock_universe_rows": len(frozen_stock_identity_keys),
                "conflicts": {
                    "batch_conflict": count("SELECT count(*) AS value FROM common_ingest_batch WHERE batch_id=%s", (BATCH_ID,)),
                    "quality_conflict": count("SELECT count(*) AS value FROM common_quality_gate_result WHERE source_batch_id=%s", (BATCH_ID,)),
                    "active_conflict": count(
                        """
                        SELECT count(*) AS value
                        FROM common_active_source_version
                        WHERE data_domain='stock' AND data_type='stock_financial' AND scope_key=%s AND source_version=%s
                        """,
                        (source_trade_date, SOURCE_VERSION),
                    ),
                    "target_source_version_rows": count(
                        "SELECT count(*) AS value FROM stock_financial_metrics_fact WHERE source_trade_date=%s AND source_version=%s",
                        (source_trade_date, SOURCE_VERSION),
                    ),
                },
                "event_counts": {
                    "common_event_outbox": count("SELECT count(*) AS value FROM common_event_outbox"),
                    "common_event_inbox": count("SELECT count(*) AS value FROM common_event_inbox"),
                    "common_event_consumer_checkpoint": count("SELECT count(*) AS value FROM common_event_consumer_checkpoint"),
                },
            }

    previous_snapshot = load_financial_canonical_snapshot_v1(previous_snapshot_path) if (incremental_enabled or financial_only) else None
    if financial_only:
        expected_identity_keys = list(frozen_stock_identity_keys)
        if (
            not expected_identity_keys
            or any(not key for key in expected_identity_keys)
            or len(expected_identity_keys) != len(set(expected_identity_keys))
        ):
            raise StockFinancialCanonicalSourceBundleBlocked(
                "financial_frozen_universe_daily_basic_duplicate_or_empty"
            )
        affair_lineage: dict[str, Any] = {}
        source_errors: list[dict[str, str]] = []
        refreshed_rows: list[dict[str, Any]] = []
        selected_financial_only_daily_basic_rows = list(daily_basic_rows)
        force_full_fallback = not source_fetch_enabled
        fallback_reason: str | None = "financial_source_fetch_disabled" if not source_fetch_enabled else None
        if source_fetch_enabled:
            try:
                affair_source = MootdxAffairFinancialSource(cache_dir=affair_cache_dir)
                refreshed_rows = affair_source.fetch_all_financial_metrics(
                    expected_identity_keys=expected_identity_keys,
                    source_trade_date=source_trade_date,
                    previous_snapshot=previous_snapshot,
                    cutoff_date=source_trade_date,
                    source_batch_id=source_bundle_batch_id_for(source_trade_date),
                    source_version=f"stock_financial_{source_trade_date}_affair_v1",
                )
                affair_lineage = dict(affair_source.last_lineage)
                if affair_lineage.get("announcement_date_unverified_count"):
                    source_errors.append({"source": SOURCE_MOOTDX_AFFAIR, "error": "announcement_date_unverified"})
                warning_codes = [
                    str(code)
                    for code in affair_lineage.get("warning_codes") or []
                    if code
                ]
                for warning_code in warning_codes:
                    source_errors.append(
                        {"source": SOURCE_MOOTDX_AFFAIR, "error": warning_code, "recovered": "true"}
                    )
            except Exception as exc:  # pragma: no cover - live source availability varies.
                source_errors.append({"source": SOURCE_MOOTDX_AFFAIR, "error": exc.__class__.__name__})
                force_full_fallback = True
                fallback_reason = f"affair_source_error:{exc.__class__.__name__}"
        else:
            refreshed_rows = []
            affair_lineage = {
                "source": SOURCE_MOOTDX_AFFAIR,
                "source_fetch_enabled": False,
                "announcement_date_unverified_count": 0,
            }
        final_rows, financial_lineage = merge_financial_only_rows(
            expected_identity_keys=expected_identity_keys,
            refreshed_rows=refreshed_rows,
            previous_snapshot=previous_snapshot,
            source_trade_date=source_trade_date,
            force_full_fallback=force_full_fallback,
            fallback_reason=fallback_reason,
        )
        selected_financial_only_daily_basic_rows, daily_basic_lineage = (
            merge_financial_only_daily_basic_rows(
                expected_identity_keys=expected_identity_keys,
                current_rows=selected_financial_only_daily_basic_rows,
                previous_snapshot=previous_snapshot,
            )
        )
        return {
            "source_trade_date": source_trade_date,
            "expected_identity_keys": expected_identity_keys,
            "tdx_rows": [],
            "tushare_rows": final_rows,
            "forecast_rows": [],
            "daily_basic_rows": selected_financial_only_daily_basic_rows,
            "current_signature_rows": active_rows,
            "baseline": baseline,
            "source_probe": {
                "financial_only": True,
                "financial_source_policy_version": FINANCIAL_SOURCE_POLICY_VERSION,
                "financial_authority": SOURCE_MOOTDX_AFFAIR,
                "source_fetch_enabled": source_fetch_enabled,
                "use_tdx_source": False,
                "forecast_disabled": True,
                "forecast_type": None,
                "forecast_score": None,
                "tushare_financial_call_count": 0,
                "forecast_call_count": 0,
                "daily_basic_source": "stock_daily_basic_read_only",
                "daily_basic_external_call_count": 0,
                "source_errors": source_errors,
                "writes_performed": False,
                **affair_lineage,
                **financial_lineage,
                **daily_basic_lineage,
            },
        }
    all_symbols = [symbol_from_active_row(row) for row in active_rows]
    delta_identity_keys: list[str] = []
    delta_reason_distribution: dict[str, int] = {}
    delta_guard = incremental_delta_guard_probe(
        active_universe_count=len(all_symbols),
        delta_symbol_count=0,
        incremental_enabled=False,
        full_rebuild_confirmed=full_rebuild_confirmed,
    )
    if incremental_enabled:
        delta = compute_financial_canonical_delta(
            active_rows,
            previous_snapshot=previous_snapshot,
            explicit_changed_identity_keys=changed_identity_keys,
            full_rebuild_confirmed=full_rebuild_confirmed,
        )
        delta_identity_keys = list(delta["identity_keys"])
        delta_reason_distribution = dict(delta.get("reason_distribution") or {})
        delta_guard = incremental_delta_guard_probe(
            active_universe_count=len(all_symbols),
            delta_symbol_count=len(delta_identity_keys),
            incremental_enabled=True,
            full_rebuild_confirmed=full_rebuild_confirmed,
        )
        delta_set = set(delta_identity_keys)
        delta_symbols = [symbol for symbol in all_symbols if symbol.stock_identity_key in delta_set]
        symbols = [] if delta_guard["incremental_delta_guard_blocked"] else delta_symbols
        selection = {
            "active_universe_count": len(all_symbols),
            "post_shard_symbol_count": len(delta_symbols),
            "selected_symbol_count": len(symbols),
            "selected_symbol_count_before_guard": len(delta_symbols),
            "max_symbols": max_symbols,
            "symbol_shard": symbol_shard,
            "full_fetch_confirmed": bool(full_fetch_confirmed),
            "incremental_enabled": True,
            "selection_mode": "incremental_delta",
            "delta_symbol_count": len(delta_identity_keys),
            "delta_identity_keys_sample": delta_identity_keys[:20],
            "delta_reason_distribution": delta_reason_distribution,
            "previous_snapshot_path": str(previous_snapshot_path) if previous_snapshot_path else None,
            "snapshot_cache_path": str(snapshot_cache_path) if snapshot_cache_path else None,
            "bounded": True,
            **delta_guard,
        }
        selected_daily_basic_rows = list(daily_basic_rows)
    else:
        symbols, selection = select_probe_symbols(
            all_symbols,
            max_symbols=max_symbols,
            symbol_shard=symbol_shard,
            full_fetch_confirmed=full_fetch_confirmed,
        )
        selected_identity_keys = {symbol.stock_identity_key for symbol in symbols}
        selected_daily_basic_rows = [row for row in daily_basic_rows if str(row.get("stock_identity_key") or "") in selected_identity_keys]
    tdx_rows: list[dict[str, Any]] = []
    tushare_rows: list[dict[str, Any]] = []
    forecast_rows: list[dict[str, Any]] = []
    tushare_stats: dict[str, Any] = {}
    source_errors: list[dict[str, str]] = []
    source_fetch_skipped_reason: str | None = None
    if source_fetch_enabled and not symbols:
        source_fetch_skipped_reason = "no_delta_symbols"
    if source_fetch_enabled and symbols and not delta_guard["incremental_delta_guard_blocked"]:
        if use_tdx_source:
            try:
                tdx_rows = list(fetch_tdx_mootdx_rows(symbols=symbols, source_trade_date=source_trade_date))
            except Exception as exc:  # pragma: no cover - live source availability varies.
                source_errors.append({"source": "tdx_mootdx.finance", "error": exc.__class__.__name__})
        try:
            tushare_bundle = fetch_tushare_rows(
                symbols=symbols,
                source_trade_date=source_trade_date,
                token=tushare_token,
                resume_cache_path=resume_cache_path,
                rate_limit_ms=rate_limit_ms,
                announcement_dates=announcement_dates,
                tushare_concurrency=tushare_concurrency,
            )
            tushare_rows = list(tushare_bundle.get("financial_rows") or [])
            forecast_rows = list(tushare_bundle.get("forecast_rows") or [])
            selected_daily_basic_rows = merge_daily_basic_metadata(
                list(tushare_bundle.get("daily_basic_rows") or []),
                selected_daily_basic_rows,
            )
            tushare_stats = dict(tushare_bundle.get("stats") or {})
            source_errors.extend(tushare_bundle.get("source_errors") or [])
        except Exception as exc:  # pragma: no cover - live source availability varies.
            source_errors.append({"source": "tushare.financial_bundle", "error": exc.__class__.__name__})
    elif source_fetch_enabled and delta_guard["incremental_delta_guard_blocked"]:
        source_errors.append(
            {
                "source": "incremental_delta_guard",
                "error": "delta_symbol_count_exceeds_guard_threshold_without_full_rebuild_confirmed",
            }
        )
    if incremental_enabled:
        delta_financial_rows = [*tdx_rows, *tushare_rows]
        merged_financial_rows, forecast_rows = merge_incremental_source_rows(
            expected_identity_keys=[symbol.stock_identity_key for symbol in all_symbols],
            previous_snapshot=previous_snapshot,
            delta_financial_rows=delta_financial_rows,
            delta_forecast_rows=forecast_rows,
            delta_identity_keys=delta_identity_keys,
        )
        tdx_rows, tushare_rows = split_financial_rows_by_source(merged_financial_rows)
    return {
        "source_trade_date": source_trade_date,
        "expected_identity_keys": [symbol.stock_identity_key for symbol in (all_symbols if incremental_enabled else symbols)],
        "tdx_rows": tdx_rows,
        "tushare_rows": tushare_rows,
        "forecast_rows": forecast_rows,
        "daily_basic_rows": selected_daily_basic_rows,
        "current_signature_rows": active_rows,
        "baseline": baseline,
        "source_probe": {
            "source_fetch_enabled": source_fetch_enabled,
            "source_fetch_skipped_reason": source_fetch_skipped_reason,
            "use_tdx_source": use_tdx_source,
            "max_symbols": max_symbols,
            "symbol_shard": symbol_shard,
            "resume_cache_path": str(resume_cache_path) if resume_cache_path else None,
            "previous_snapshot_path": str(previous_snapshot_path) if previous_snapshot_path else None,
            "snapshot_cache_path": str(snapshot_cache_path) if snapshot_cache_path else None,
            "rate_limit_ms": rate_limit_ms,
            "tushare_concurrency": int(tushare_concurrency),
            "full_fetch_confirmed": full_fetch_confirmed,
            "full_rebuild_confirmed": full_rebuild_confirmed,
            "announcement_date_count": len(announcement_dates),
            **selection,
            "tdx_rows": len(tdx_rows),
            "tushare_rows": len(tushare_rows),
            "forecast_rows": len(forecast_rows),
            "tushare_stats": tushare_stats,
            "source_errors": source_errors,
            "writes_performed": False,
        },
    }


def symbol_from_active_row(row: Mapping[str, Any]) -> StockFinancialSymbol:
    return StockFinancialSymbol(code=str(row.get("code")), exchange=str(row.get("exchange")), name=None)


def merge_daily_basic_metadata(
    primary_rows: Sequence[Mapping[str, Any]],
    metadata_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not primary_rows:
        return [dict(row) for row in metadata_rows]
    metadata_by_key = {
        str(row.get("stock_identity_key")): dict(row)
        for row in metadata_rows
        if row.get("stock_identity_key")
    }
    merged = []
    seen: set[str] = set()
    for row in primary_rows:
        key = str(row.get("stock_identity_key") or "")
        seen.add(key)
        metadata = metadata_by_key.get(key) or {}
        merged.append({**metadata, **dict(row), "industry": row.get("industry") or metadata.get("industry")})
    for key, row in metadata_by_key.items():
        if key not in seen:
            merged.append(dict(row))
    return merged


def fetch_tdx_mootdx_rows(*, symbols: Sequence[StockFinancialSymbol], source_trade_date: str) -> Sequence[Mapping[str, Any]]:
    return MootdxAffairFinancialSource().fetch_all_financial_metrics(
        expected_identity_keys=[symbol.stock_identity_key for symbol in symbols],
        source_trade_date=source_trade_date,
        cutoff_date=source_trade_date,
    )


def fetch_tushare_rows(
    *,
    symbols: Sequence[StockFinancialSymbol],
    source_trade_date: str,
    token: str | None,
    resume_cache_path: str | Path | None = None,
    rate_limit_ms: int = 0,
    announcement_dates: Sequence[str] | None = None,
    tushare_concurrency: int = 1,
) -> dict[str, Any]:
    token = token or load_tushare_token()
    if not token:
        raise StockFinancialCanonicalSourceBundleBlocked("TUSHARE_TOKEN is required for Tushare fallback source probe")
    module = importlib.import_module("tushare")
    pro = module.pro_api(token)
    return fetch_tushare_rows_from_client(
        pro=pro,
        symbols=symbols,
        source_trade_date=source_trade_date,
        resume_cache_path=resume_cache_path,
        rate_limit_ms=rate_limit_ms,
        announcement_dates=announcement_dates,
        tushare_concurrency=tushare_concurrency,
    )


def fetch_tushare_daily_basic_rows_from_client(
    *,
    pro: Any,
    source_trade_date: str,
    expected_identity_keys: Sequence[str],
) -> list[dict[str, Any]]:
    """Fetch only daily_basic for the financial-only path; never forecast or per-symbol finance."""

    frame = pro.daily_basic(
        trade_date=require_yyyymmdd(source_trade_date, "source_trade_date"),
        fields="ts_code,trade_date,total_mv,circ_mv,pe,pe_ttm,pb",
    )
    records = frame.to_dict(orient="records") if hasattr(frame, "to_dict") else frame
    expected = set(str(key) for key in expected_identity_keys)
    rows: list[dict[str, Any]] = []
    for raw in records or []:
        item = dict(raw)
        ts_code = str(item.get("ts_code") or "")
        if "." not in ts_code:
            continue
        code, exchange = ts_code.split(".", 1)
        identity_key = f"stock:{exchange.upper()}:{code.zfill(6)}"
        if identity_key not in expected:
            continue
        rows.append(
            {
                **item,
                "stock_identity_key": identity_key,
                "ts_code": f"{code.zfill(6)}.{exchange.upper()}",
                "total_mv": item.get("total_mv"),
                "circ_mv": item.get("circ_mv"),
                "pe_core": item.get("pe_ttm") if item.get("pe_ttm") is not None else item.get("pe"),
                "source": "tushare.daily_basic",
                "source_type": "tushare.daily_basic",
                "source_trade_date": source_trade_date,
            }
        )
    return rows


def fetch_tushare_daily_basic_rows(
    *,
    token: str | None,
    source_trade_date: str,
    expected_identity_keys: Sequence[str],
) -> list[dict[str, Any]]:
    token = token or load_tushare_token()
    if not token:
        raise StockFinancialCanonicalSourceBundleBlocked("TUSHARE_TOKEN is required for daily_basic")
    module = importlib.import_module("tushare")
    return fetch_tushare_daily_basic_rows_from_client(
        pro=module.pro_api(token),
        source_trade_date=source_trade_date,
        expected_identity_keys=expected_identity_keys,
    )


def fetch_tushare_rows_from_client(
    *,
    pro: Any,
    symbols: Sequence[StockFinancialSymbol],
    source_trade_date: str,
    resume_cache_path: str | Path | None = None,
    rate_limit_ms: int = 0,
    announcement_dates: Sequence[str] | None = None,
    tushare_concurrency: int = 1,
    sleep_fn: Any | None = None,
) -> dict[str, Any]:
    source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    cache = load_tushare_probe_cache(resume_cache_path)
    cache.setdefault("schema_version", 1)
    cache.setdefault("symbols", {})
    cache.setdefault("source_trade_dates", {})
    symbol_cache: dict[str, Any] = cache["symbols"]
    symbol_by_ts_code = {symbol.ts_code: symbol for symbol in symbols}
    requested_ts_codes = list(symbol_by_ts_code.keys())
    financial_rows: list[dict[str, Any]] = []
    forecast_rows: list[dict[str, Any]] = []
    daily_basic_rows: list[dict[str, Any]] = []
    source_errors: list[dict[str, str]] = []
    stats = Counter()

    def pause() -> None:
        if rate_limit_ms and rate_limit_ms > 0:
            sleeper = sleep_fn or time.sleep
            sleeper(rate_limit_ms / 1000)

    def fetch_symbol_entry(symbol: StockFinancialSymbol) -> tuple[str, dict[str, Any], list[dict[str, str]]]:
        entry: dict[str, Any] = {"source_trade_date": source_trade_date}
        errors: list[dict[str, str]] = []
        for source_name, func, kwargs in (
            (
                "tushare.income",
                pro.income,
                {
                    "ts_code": symbol.ts_code,
                    "start_date": "20230101",
                    "end_date": source_trade_date,
                    "fields": "ts_code,ann_date,end_date,total_revenue,oper_cost,biz_tax_surchg,sell_exp,admin_exp,rd_exp,fin_exp,int_exp",
                },
            ),
            (
                "tushare.cashflow",
                pro.cashflow,
                {
                    "ts_code": symbol.ts_code,
                    "start_date": "20230101",
                    "end_date": source_trade_date,
                    "fields": "ts_code,ann_date,end_date,n_cashflow_act",
                },
            ),
            (
                "tushare.forecast",
                pro.forecast,
                {
                    "ts_code": symbol.ts_code,
                    "start_date": "20230101",
                    "end_date": source_trade_date,
                    "fields": "ts_code,ann_date,end_date,type",
                },
            ),
        ):
            try:
                key = source_name.rsplit(".", 1)[-1] + "_rows"
                rows = [
                    row
                    for row in fetch_tushare_pages(func, **kwargs)
                    if str(row.get("ts_code") or symbol.ts_code) == symbol.ts_code
                ]
                entry[key] = json_strict_safe(rows)
            except Exception as exc:  # pragma: no cover - live source availability varies.
                errors.append({"source": source_name, "ts_code": symbol.ts_code, "error": exc.__class__.__name__, "message": str(exc)})
                entry[source_name.rsplit(".", 1)[-1] + "_rows"] = []
            pause()
        return symbol.ts_code, entry, errors

    missing_symbols: list[StockFinancialSymbol] = []
    for symbol in symbols:
        cached = cached_tushare_symbol_entry(symbol_cache, symbol.ts_code, source_trade_date)
        if cached is not None:
            stats["cache_hit_count"] += 1
            continue
        missing_symbols.append(symbol)
        stats["cache_miss_count"] += 1

    batch_announcement_dates = sorted({str(value) for value in announcement_dates or [] if value})
    per_symbol_fetch_symbols = list(missing_symbols)
    if len(missing_symbols) > 1 and batch_announcement_dates:
        missing_ts_codes = {symbol.ts_code for symbol in missing_symbols}
        grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: {"income_rows": [], "cashflow_rows": [], "forecast_rows": []})
        batch_source_errors_start = len(source_errors)
        for source_name, func, cache_key, base_kwargs in (
            (
                "tushare.income",
                pro.income,
                "income_rows",
                {
                    "fields": "ts_code,ann_date,end_date,total_revenue,oper_cost,biz_tax_surchg,sell_exp,admin_exp,rd_exp,fin_exp,int_exp",
                },
            ),
            (
                "tushare.cashflow",
                pro.cashflow,
                "cashflow_rows",
                {
                    "fields": "ts_code,ann_date,end_date,n_cashflow_act",
                },
            ),
            (
                "tushare.forecast",
                pro.forecast,
                "forecast_rows",
                {
                    "fields": "ts_code,ann_date,end_date,type",
                },
            ),
        ):
            for ann_date in batch_announcement_dates:
                try:
                    rows = [
                        row
                        for row in fetch_tushare_pages(func, **{**base_kwargs, "ann_date": ann_date})
                        if str(row.get("ts_code") or "") in missing_ts_codes
                    ]
                    for row in rows:
                        grouped[str(row.get("ts_code"))][cache_key].append(dict(row))
                except Exception as exc:  # pragma: no cover - live source availability varies.
                    source_errors.append({"source": source_name, "ann_date": ann_date, "error": exc.__class__.__name__, "message": str(exc)})
                pause()
        new_batch_errors = source_errors[batch_source_errors_start:]
        financial_batch_unsupported = any(
            error.get("source") in {"tushare.income", "tushare.cashflow"}
            and "ts_code" in str(error.get("message") or "")
            for error in new_batch_errors
        )
        if not financial_batch_unsupported:
            for symbol in missing_symbols:
                symbol_cache[symbol.ts_code] = {
                    "source_trade_date": source_trade_date,
                    "income_rows": json_strict_safe(grouped[symbol.ts_code]["income_rows"]),
                    "cashflow_rows": json_strict_safe(grouped[symbol.ts_code]["cashflow_rows"]),
                    "forecast_rows": json_strict_safe(grouped[symbol.ts_code]["forecast_rows"]),
                }
            write_tushare_probe_cache(resume_cache_path, cache)
            per_symbol_fetch_symbols = []
        else:
            del source_errors[batch_source_errors_start:]

    if per_symbol_fetch_symbols and tushare_concurrency > 1:
        max_workers = max(1, min(int(tushare_concurrency), len(per_symbol_fetch_symbols)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(fetch_symbol_entry, symbol) for symbol in per_symbol_fetch_symbols]
            for future in as_completed(futures):
                ts_code, entry, errors = future.result()
                symbol_cache[ts_code] = entry
                source_errors.extend(errors)
                write_tushare_probe_cache(resume_cache_path, cache)
    else:
        for symbol in per_symbol_fetch_symbols:
            ts_code, entry, errors = fetch_symbol_entry(symbol)
            symbol_cache[ts_code] = entry
            source_errors.extend(errors)
            write_tushare_probe_cache(resume_cache_path, cache)

    if any(not cached_tushare_symbol_entry(symbol_cache, ts_code, source_trade_date).get("daily_basic_rows") for ts_code in requested_ts_codes if cached_tushare_symbol_entry(symbol_cache, ts_code, source_trade_date) is not None):
        try:
            rows = fetch_tushare_pages(pro.daily_basic, trade_date=source_trade_date, fields="ts_code,trade_date,total_mv,circ_mv")
            daily_basic_by_ts_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in rows:
                ts_code = str(row.get("ts_code") or "")
                if ts_code in symbol_by_ts_code:
                    daily_basic_by_ts_code[ts_code].append(dict(row))
            for ts_code in requested_ts_codes:
                entry = cached_tushare_symbol_entry(symbol_cache, ts_code, source_trade_date)
                if entry is not None:
                    entry["daily_basic_rows"] = json_strict_safe(daily_basic_by_ts_code.get(ts_code) or [])
            write_tushare_probe_cache(resume_cache_path, cache)
        except Exception as exc:  # pragma: no cover - live source availability varies.
            source_errors.append({"source": "tushare.daily_basic", "error": exc.__class__.__name__})
        pause()

    for symbol in symbols:
        entry = cached_tushare_symbol_entry(symbol_cache, symbol.ts_code, source_trade_date) or {}
        income_rows = [dict(row) for row in entry.get("income_rows") or []]
        cashflow_rows = [dict(row) for row in entry.get("cashflow_rows") or []]
        symbol_forecast_rows = [dict(row) for row in entry.get("forecast_rows") or []]
        symbol_daily_basic_rows = [dict(row) for row in entry.get("daily_basic_rows") or []]

        if income_rows:
            stats["tushare_income_ok_count"] += 1
        if cashflow_rows:
            stats["tushare_cashflow_ok_count"] += 1
        if symbol_forecast_rows:
            stats["forecast_ok_count"] += 1
        if symbol_daily_basic_rows:
            stats["daily_basic_ok_count"] += 1

        cashflow_by_key = {
            (str(row.get("ts_code") or ""), str(row.get("end_date") or ""), str(row.get("ann_date") or "")): row
            for row in cashflow_rows
        }
        cashflow_by_period: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in cashflow_rows:
            if row.get("n_cashflow_act") in (None, ""):
                continue
            ann_date = optional_date_text(row.get("ann_date"))
            if ann_date and ann_date > source_trade_date:
                continue
            cashflow_by_period[(str(row.get("ts_code") or ""), str(row.get("end_date") or ""))].append(row)
        for income in income_rows:
            key = (str(income.get("ts_code") or ""), str(income.get("end_date") or ""), str(income.get("ann_date") or ""))
            cashflow = cashflow_by_key.get(key)
            merge_strategy = "exact"
            if not cashflow or cashflow.get("n_cashflow_act") in (None, ""):
                period_key = (str(income.get("ts_code") or ""), str(income.get("end_date") or ""))
                period_candidates = sorted(
                    cashflow_by_period.get(period_key) or [],
                    key=lambda row: str(row.get("ann_date") or ""),
                    reverse=True,
                )
                cashflow = period_candidates[0] if period_candidates else {}
                merge_strategy = "report_period" if cashflow else "missing"
            merged = {
                **dict(cashflow or {}),
                **income,
                "n_cashflow_act": (cashflow or {}).get("n_cashflow_act"),
                "cashflow_ann_date": (cashflow or {}).get("ann_date"),
                "cashflow_merge_strategy": merge_strategy,
            }
            financial_rows.append(
                normalize_tushare_financial_row(
                    merged,
                    identity_key=symbol.stock_identity_key,
                    code=symbol.code,
                    exchange=symbol.exchange,
                )
            )
        for row in symbol_forecast_rows:
            forecast_rows.append(normalize_tushare_forecast_row(row, identity_key=symbol.stock_identity_key))
        for row in symbol_daily_basic_rows:
            daily_basic_rows.append(
                {
                    "stock_identity_key": symbol.stock_identity_key,
                    "total_mv": row.get("total_mv"),
                    "circ_mv": row.get("circ_mv"),
                    "raw_payload": dict(row),
                }
            )

    write_tushare_probe_cache(resume_cache_path, cache)
    stats["requested_symbol_count"] = len(symbols)
    stats["source_error_count"] = len(source_errors)
    return {
        "financial_rows": financial_rows,
        "forecast_rows": forecast_rows,
        "daily_basic_rows": daily_basic_rows,
        "stats": {key: int(value) for key, value in stats.items()},
        "source_errors": source_errors,
    }


def cached_tushare_symbol_entry(symbol_cache: Mapping[str, Any], ts_code: str, source_trade_date: str) -> dict[str, Any] | None:
    entry = symbol_cache.get(ts_code)
    if not isinstance(entry, Mapping):
        return None
    if entry.get("source_trade_date") != source_trade_date:
        return None
    if not all(key in entry for key in ("income_rows", "cashflow_rows", "forecast_rows")):
        return None
    if not entry.get("income_rows") and not entry.get("cashflow_rows"):
        return None
    return entry  # type: ignore[return-value]


def load_tushare_probe_cache(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    cache_path = Path(path)
    if not cache_path.exists():
        return {}
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if isinstance(payload, Mapping):
        return dict(payload)
    return {}


def write_tushare_probe_cache(path: str | Path | None, payload: Mapping[str, Any]) -> None:
    if not path:
        return
    cache_path = Path(path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(json_strict_safe(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fetch_tushare_pages(func: Any, *, page_limit: int = 5000, max_pages: int = 200, **kwargs: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    for _ in range(max_pages):
        try:
            page = frame_to_records(func(**kwargs, limit=page_limit, offset=offset))
        except TypeError:
            if offset != 0:
                break
            return frame_to_records(func(**kwargs))
        if not page:
            break
        rows.extend(page)
        if len(page) < page_limit:
            break
        offset += page_limit
    return rows


def normalize_tushare_financial_row(row: Mapping[str, Any], *, identity_key: str, code: str, exchange: str) -> dict[str, Any]:
    return {
        "stock_identity_key": identity_key,
        "ts_code": row.get("ts_code") or f"{code}.{exchange}",
        "code": code,
        "exchange": exchange,
        "source_type": SOURCE_TUSHARE_FALLBACK,
        "report_period": row.get("end_date"),
        "announcement_date": row.get("ann_date"),
        "operating_revenue": row.get("total_revenue"),
        "operating_cost": row.get("oper_cost"),
        "taxes_and_surcharges": row.get("biz_tax_surchg"),
        "selling_expense": row.get("sell_exp"),
        "admin_expense": row.get("admin_exp"),
        "rd_expense": row.get("rd_exp"),
        "interest_expense": row.get("int_exp"),
        "finance_expense": row.get("fin_exp"),
        "operating_cashflow": row.get("n_cashflow_act"),
        "cashflow_announcement_date": row.get("cashflow_ann_date"),
        "cashflow_merge_strategy": row.get("cashflow_merge_strategy"),
        "raw_payload": dict(row),
    }


def normalize_tushare_forecast_row(row: Mapping[str, Any], *, identity_key: str) -> dict[str, Any]:
    return {
        "stock_identity_key": identity_key,
        "forecast_type": row.get("type"),
        "report_period": row.get("end_date"),
        "announcement_date": row.get("ann_date"),
        "source_type": "tushare.forecast",
        "raw_payload": dict(row),
    }


def frame_to_records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        try:
            return [dict(row) for row in frame.to_dict(orient="records")]
        except TypeError:
            return [dict(row) for row in frame.to_dict("records")]
    if isinstance(frame, Mapping):
        return [dict(frame)]
    if isinstance(frame, Iterable) and not isinstance(frame, (str, bytes, bytearray)):
        return [dict(row) for row in frame]
    return []


def calculator_refresh_allowed(report: Mapping[str, Any]) -> bool:
    probe = report.get("source_probe") or {}
    return (
        report.get("result") == "PASS"
        and bool(probe.get("full_fetch_confirmed"))
        and int(probe.get("selected_symbol_count") or 0) == int(probe.get("active_universe_count") or -1)
    )


def full_fetch_command_plan(report: Mapping[str, Any]) -> dict[str, Any]:
    source_trade_date = report.get("source_trade_date") or TRADE_DATE
    return {
        "requires_user_confirmation": True,
        "writes_database": False,
        "writes_cache_only": True,
        "command": (
            "set -a && source /Users/chuanfuchen/.secrets/ashare_v3_tushare.env && set +a && "
            "PYTHONPATH=src python3 scripts/plan_stock_financial_canonical_source_bundle_once.py "
            f"--source-trade-date {source_trade_date} --source-fetch-enabled --full-fetch-confirmed --max-symbols 0 "
            f"--resume-cache-path {DEFAULT_TUSHARE_CACHE_PATH} --rate-limit-ms 300"
        ),
    }


def build_contract(report: Mapping[str, Any]) -> dict[str, Any]:
    return json_safe(
        {
            "result": "DESIGN_PASS",
            "stage": "N1 stock_financial canonical source bundle contract",
            "layer_role": "N1_ingestion",
            "source_trade_date": report.get("source_trade_date") or TRADE_DATE,
            "source_bundle_batch_id": SOURCE_BUNDLE_BATCH_ID,
            "target_source_batch_id": BATCH_ID,
            "target_source_version": SOURCE_VERSION,
            "previous_source_version": PREVIOUS_SOURCE_VERSION,
            "financial_metric_version": FINANCIAL_METRIC_VERSION,
            "source_priority": ["TDX/Mootdx finance", "Tushare income/cashflow/forecast/daily_basic fallback"],
            "asof_guard": "announcement_date <= source_trade_date; missing announcement_date requires explicit asof_safe proof",
            "line_item_fallback_policy": {
                "rd_expense": {
                    "fallback": "0",
                    "warning_code": "rd_expense_missing_fallback_zero",
                    "severity": "P1",
                    "blocks_readiness": False,
                },
                "selling_expense": {
                    "fallback": "0",
                    "warning_code": "selling_expense_missing_fallback_zero",
                    "severity": "P1",
                    "blocks_readiness": False,
                },
                "operating_cashflow": {
                    "merge_priority": ["ts_code+report_period+announcement_date", "ts_code+report_period"],
                    "latest_missing_behavior": "cash_realization_rate_null_and_cash_score_zero",
                    "warning_code": "operating_cashflow_missing_latest",
                    "severity": "P1",
                    "blocks_readiness": False,
                },
                "historical_core_line_items": {
                    "warning_code": HISTORICAL_CORE_LINE_ITEMS_MISSING_WARNING,
                    "severity": "P2",
                    "blocks_readiness": False,
                    "latest_row_still_required": True,
                },
                "latest_core_line_items_fallback_prior_period": {
                    "warning_code": LATEST_CORE_LINE_ITEMS_MISSING_FALLBACK_WARNING,
                    "severity": "P1",
                    "blocks_readiness": False,
                    "requires_prior_usable_report_period": True,
                },
                "finance_sector_policy": {
                    "industries": sorted(FINANCE_SECTOR_INDUSTRIES),
                    "warning_code": FINANCE_SECTOR_POLICY_WARNING,
                    "severity": "P1",
                    "blocks_readiness": False,
                    "industrial_formula": "not_applicable_v1",
                },
                "pre_revenue_policy": {
                    "identity_keys": sorted(PRE_REVENUE_IDENTITY_KEYS),
                    "warning_code": PRE_REVENUE_POLICY_WARNING,
                    "severity": "P1",
                    "blocks_readiness": False,
                },
                "operating_cost": {
                    "fallback": None,
                    "severity": "P0 unless finance_sector_policy/pre_revenue_policy applies",
                    "blocks_readiness": True,
                },
                "operating_revenue": {
                    "fallback": None,
                    "severity": "P0 unless pre_revenue_policy applies",
                    "blocks_readiness": True,
                },
            },
            "controlled_probe_contract": {
                "default_mode": "small_sample",
                "default_sample_size": DEFAULT_SMALL_SAMPLE_SIZE,
                "full_run_default": False,
                "full_fetch_requires": "--full-fetch-confirmed plus explicit --max-symbols 0",
                "supported_flags": ["--source-fetch-enabled", "--max-symbols", "--symbol-shard", "--resume-cache-path", "--rate-limit-ms"],
                "cache_path_default": str(DEFAULT_TUSHARE_CACHE_PATH),
            },
            "full_fetch_plan": full_fetch_command_plan(report),
            "required_line_item_fields": REQUIRED_LINE_ITEM_FIELDS,
            "allowed_future_read_sources": list(ALLOWED_FUTURE_READ_SOURCES),
            "forbidden_scope": list(FORBIDDEN_SCOPE),
            "calculator_refresh_allowed": calculator_refresh_allowed(report),
            "side_effects": default_side_effects(),
        }
    )


def build_preflight(report: Mapping[str, Any]) -> dict[str, Any]:
    blockers = list(report.get("blockers") or [])
    return json_safe(
        {
            "result": "PREFLIGHT_PASS" if report.get("result") == "PASS" else "BLOCKED",
            "stage": "N1 stock_financial canonical source bundle preflight",
            "layer_role": "N1_ingestion",
            "source_trade_date": report.get("source_trade_date") or TRADE_DATE,
            "source_bundle_batch_id": SOURCE_BUNDLE_BATCH_ID,
            "target_source_batch_id": BATCH_ID,
            "target_source_version": SOURCE_VERSION,
            "runner_readiness": "source_bundle_dry_run_ready",
            "execute_authorized": False,
            "calculator_refresh_allowed": calculator_refresh_allowed(report),
            "full_fetch_plan": full_fetch_command_plan(report),
            "blockers": blockers,
            "source_coverage": report.get("source_coverage"),
            "source_probe": report.get("source_probe"),
            "quality": report.get("quality"),
            "baseline": report.get("baseline"),
            "side_effects": default_side_effects(),
        }
    )


def write_artifacts(report: Mapping[str, Any], contract: Mapping[str, Any], preflight: Mapping[str, Any]) -> None:
    write_json(DEFAULT_PATHS["dry_run_json"], report)
    write_markdown(DEFAULT_PATHS["dry_run_md"], report, "N1 Stock Financial Canonical Source Bundle Dry-Run Report")
    write_json(DEFAULT_PATHS["contract_json"], contract)
    write_markdown(DEFAULT_PATHS["contract_md"], contract, "N1 Stock Financial Canonical Source Bundle Contract")
    write_json(DEFAULT_PATHS["preflight_json"], preflight)
    write_markdown(DEFAULT_PATHS["preflight_md"], preflight, "N1 Stock Financial Canonical Source Bundle Preflight")


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: Path, payload: Mapping[str, Any], title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "result": payload.get("result"),
        "source_trade_date": payload.get("source_trade_date"),
        "source_coverage": payload.get("source_coverage"),
        "quality": payload.get("quality"),
        "blockers": payload.get("blockers"),
        "side_effects": payload.get("side_effects"),
    }
    path.write_text(f"# {title}\n\n```json\n{json.dumps(json_safe(summary), ensure_ascii=False, indent=2)}\n```\n", encoding="utf-8")


def json_strict_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        try:
            return bytes(value).decode("utf-8")
        except UnicodeDecodeError:
            return base64.b64encode(bytes(value)).decode("ascii")
    if isinstance(value, Mapping):
        return {str(key): json_strict_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_strict_safe(item) for item in value]
    return value
