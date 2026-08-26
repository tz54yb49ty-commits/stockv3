"""N1 stock financial canonical metrics dry-run planner.

This module is intentionally dry-run first. It computes canonical financial
metrics from supplied source rows, writes no database rows, and exposes a
preflight report for a future `stock_financial_${source_trade_date}_v2`
execute gate.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.ingestion.common import require_yyyymmdd


TRADE_DATE = "20260529"
BATCH_ID = "stock_financial_canonical_20260529_v1"
SOURCE_VERSION = "stock_financial_20260529_v2"
PREVIOUS_SOURCE_VERSION = "stock_financial_20260529_v1"
FINANCIAL_METRIC_VERSION = "financial_metric_v1"
FINANCIAL_SOURCE_POLICY_VERSION = "affair_authoritative_no_forecast_v1"
FINANCIAL_AUTHORITY = "mootdx_affair"
EFFECTIVE_SCORE_MAX = Decimal("97")
FINANCIAL_NULL_WARNING_CODE = "financial_source_unavailable_null_metrics"
FINANCIAL_HISTORY_INCOMPLETE_WARNING = "financial_history_incomplete_metrics_null"
DAILY_BASIC_MISSING_WARNING = "daily_basic_total_mv_missing_pe_core_score_null"
SOURCE_TDX = "tdx_mootdx_finance"
SOURCE_TUSHARE_FALLBACK = "tushare_fallback"

ZERO_FALLBACK_WARNING_CODES = (
    "rd_expense_missing_fallback_zero",
    "selling_expense_missing_fallback_zero",
)
P1_WARNING_CODES = (
    "interest_expense_missing_finance_expense_used",
    "rd_expense_missing_fallback_zero",
    "selling_expense_missing_fallback_zero",
    "operating_cashflow_missing_latest",
)
P2_WARNING_CODES = (
    "operating_cashflow_missing_historical",
)

FINANCE_SECTOR_INDUSTRIES = frozenset({"银行", "证券", "保险", "多元金融"})
FINANCE_SECTOR_POLICY_WARNING = "finance_sector_policy_not_supported_v1"
PRE_REVENUE_POLICY_WARNING = "pre_revenue_or_missing_revenue_cost"
PRE_REVENUE_IDENTITY_KEYS = frozenset({"stock:SH:688759"})
LATEST_CORE_LINE_ITEMS_MISSING_FALLBACK_WARNING = "latest_core_line_items_missing_fallback_prior_period"
HISTORICAL_CORE_LINE_ITEMS_MISSING_WARNING = "historical_core_line_items_missing"
POLICY_DISABLED_COMPONENTS = (
    "report_core_profit",
    "cash_realization_rate",
    "core_profit_ttm",
    "pe_core",
    "score",
)

DEFAULT_PATHS = {
    "dry_run_json": Path("docs/N1_stock_financial_canonical_metrics_dry_run_report.json"),
    "dry_run_md": Path("docs/N1_STOCK_FINANCIAL_CANONICAL_METRICS_DRY_RUN_REPORT.md"),
    "contract_json": Path("docs/N1_stock_financial_canonical_metrics_execute_contract.json"),
    "contract_md": Path("docs/N1_STOCK_FINANCIAL_CANONICAL_METRICS_EXECUTE_CONTRACT.md"),
    "preflight_json": Path("docs/N1_stock_financial_canonical_metrics_execute_preflight.json"),
    "preflight_md": Path("docs/N1_STOCK_FINANCIAL_CANONICAL_METRICS_EXECUTE_PREFLIGHT.md"),
    "rollback_sql": Path("sql/N1_stock_financial_canonical_metrics_20260529_rollback.sql"),
}

DEFAULT_SOURCE_BUNDLE_CACHE_PATH = Path("docs/N1_stock_financial_canonical_source_bundle_20260529_full_fetch_cache.json")
FINANCIAL_CANONICAL_SNAPSHOT_SCHEMA_VERSION = "financial_canonical_snapshot_v1"
FINANCIAL_CANONICAL_SNAPSHOT_SCHEMA_VERSION_V2 = "financial_canonical_snapshot_v2"
SUPPORTED_FINANCIAL_CANONICAL_SNAPSHOT_SCHEMA_VERSIONS = frozenset(
    {
        FINANCIAL_CANONICAL_SNAPSHOT_SCHEMA_VERSION,
        FINANCIAL_CANONICAL_SNAPSHOT_SCHEMA_VERSION_V2,
    }
)


def canonical_ids_for(source_trade_date: str) -> dict[str, str]:
    source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    return {
        "trade_date": source_trade_date,
        "batch_id": f"stock_financial_canonical_{source_trade_date}_v1",
        "source_version": f"stock_financial_{source_trade_date}_v2",
        "previous_source_version": f"stock_financial_{source_trade_date}_v1",
        "activated_by": f"n1_stock_financial_canonical_{source_trade_date}_execute_runner",
    }


def default_paths_for(source_trade_date: str) -> dict[str, Path]:
    source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    return {
        "dry_run_json": Path(f"docs/N1_stock_financial_canonical_metrics_{source_trade_date}_dry_run_report.json"),
        "dry_run_md": Path(f"docs/N1_STOCK_FINANCIAL_CANONICAL_METRICS_{source_trade_date}_DRY_RUN_REPORT.md"),
        "contract_json": Path(f"docs/N1_stock_financial_canonical_metrics_{source_trade_date}_execute_contract.json"),
        "contract_md": Path(f"docs/N1_STOCK_FINANCIAL_CANONICAL_METRICS_{source_trade_date}_EXECUTE_CONTRACT.md"),
        "preflight_json": Path(f"docs/N1_stock_financial_canonical_metrics_{source_trade_date}_execute_preflight.json"),
        "preflight_md": Path(f"docs/N1_STOCK_FINANCIAL_CANONICAL_METRICS_{source_trade_date}_EXECUTE_PREFLIGHT.md"),
        "rollback_sql": Path(f"sql/N1_stock_financial_canonical_metrics_{source_trade_date}_rollback.sql"),
    }


def default_source_bundle_cache_path_for(source_trade_date: str) -> Path:
    source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    return Path(f"docs/N1_stock_financial_canonical_source_bundle_{source_trade_date}_full_fetch_cache.json")


def apply_canonical_context(source_trade_date: str) -> None:
    ids = canonical_ids_for(source_trade_date)
    globals()["TRADE_DATE"] = ids["trade_date"]
    globals()["BATCH_ID"] = ids["batch_id"]
    globals()["SOURCE_VERSION"] = ids["source_version"]
    globals()["PREVIOUS_SOURCE_VERSION"] = ids["previous_source_version"]
    globals()["DEFAULT_PATHS"] = default_paths_for(source_trade_date)
    globals()["DEFAULT_SOURCE_BUNDLE_CACHE_PATH"] = default_source_bundle_cache_path_for(source_trade_date)

ALLOWED_FUTURE_WRITE_TABLES = (
    "common_ingest_batch",
    "common_quality_gate_result",
    "common_active_source_version",
    "stock_financial_metrics_fact",
)

FORBIDDEN_SCOPE = (
    "condition_*",
    "stock_daily_bar_fact",
    "index_daily_bar_fact",
    "board_daily_bar_fact",
    "outbox/inbox/checkpoint",
    "Parquet",
    "N2/N3/N4/N5/N6",
    "worker",
    "old_system",
    "real_trading",
)


class StockFinancialCanonicalBlocked(Exception):
    """Raised when dry-run/future execute guard blocks."""


def identity_keys_sha256(identity_keys: Sequence[str]) -> str:
    payload = json.dumps(
        sorted({str(key) for key in identity_keys if key}),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_financial_warning_only_row(row: Mapping[str, Any]) -> bool:
    raw_payload = row.get("raw_payload")
    warning_payload = row.get("financial_warning_json")
    return bool(
        isinstance(raw_payload, Mapping)
        and raw_payload.get("financial_warning_only") is True
        and raw_payload.get("financial_values_fabricated") is False
        and isinstance(warning_payload, Mapping)
        and FINANCIAL_NULL_WARNING_CODE in {
            str(code) for code in warning_payload.get("warnings") or [] if code
        }
    )


def financial_warning_only_contract(
    *,
    financial_rows: Sequence[Mapping[str, Any]],
    expected_identity_keys: Sequence[str],
    source_probe: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    warning_rows = [dict(row) for row in financial_rows if is_financial_warning_only_row(row)]
    warning_by_identity: dict[str, dict[str, Any]] = {}
    duplicate_keys: list[str] = []
    for row in warning_rows:
        identity_key = str(row.get("stock_identity_key") or "")
        if not identity_key or identity_key in warning_by_identity:
            duplicate_keys.append(identity_key)
            continue
        warning_by_identity[identity_key] = row

    actual_keys = sorted(warning_by_identity)
    expected_set = set(str(key) for key in expected_identity_keys)
    declared_keys = sorted(
        {str(key) for key in source_probe.get("financial_null_warning_identity_keys") or [] if key}
    )
    errors: list[str] = []
    if duplicate_keys:
        errors.append("financial_null_warning_duplicate_identity")
    if source_probe.get("financial_degraded_but_fastlane_allowed") is not True and actual_keys:
        errors.append("financial_null_warning_degraded_flag_missing")
    if declared_keys != actual_keys:
        errors.append("financial_null_warning_identity_keys_mismatch")
    try:
        declared_count = int(source_probe.get("financial_null_warning_identity_count"))
    except (TypeError, ValueError):
        declared_count = -1
    if declared_count != len(actual_keys):
        errors.append("financial_null_warning_identity_count_mismatch")
    if source_probe.get("financial_null_warning_identity_sha256") != identity_keys_sha256(actual_keys):
        errors.append("financial_null_warning_identity_sha256_mismatch")
    if not set(actual_keys).issubset(expected_set):
        errors.append("financial_null_warning_identity_outside_universe")
    return warning_by_identity, sorted(set(errors))


def validate_dry_run_request(*, execute_requested: bool) -> None:
    if execute_requested:
        raise StockFinancialCanonicalBlocked("this runner is dry-run/preflight only; execute is not implemented in this gate")


def validate_execute_request(
    *,
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> None:
    if not execute_requested:
        raise StockFinancialCanonicalBlocked("missing required final flag: --execute")
    if not user_confirmed:
        raise StockFinancialCanonicalBlocked("missing required final flag: --user-confirmed")
    if not postgres_commit_enabled:
        raise StockFinancialCanonicalBlocked("missing required final flag: --postgres-commit-enabled")


def calculate_canonical_financial_metrics(
    *,
    financial_rows: Sequence[Mapping[str, Any]],
    daily_basic_rows: Sequence[Mapping[str, Any]],
    source_trade_date: str,
    expected_identity_keys: Sequence[str],
    source_probe: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    expected_keys = sorted({str(key) for key in expected_identity_keys})
    probe = dict(source_probe or {})
    affair_policy = (
        probe.get("financial_source_policy_version")
        == FINANCIAL_SOURCE_POLICY_VERSION
    )
    warning_by_identity: dict[str, dict[str, Any]] = {}
    warning_contract_errors: list[str] = []
    source_financial_rows = list(financial_rows)
    if affair_policy:
        warning_by_identity, warning_contract_errors = financial_warning_only_contract(
            financial_rows=financial_rows,
            expected_identity_keys=expected_keys,
            source_probe=probe,
        )
        source_financial_rows = [
            row for row in financial_rows if not is_financial_warning_only_row(row)
        ]
    daily_basic_by_key = {
        str(row.get("stock_identity_key")): dict(row)
        for row in daily_basic_rows
        if row.get("stock_identity_key")
    }
    filtered, asof_counts = filter_asof_safe_rows(source_financial_rows, source_trade_date)
    chosen_rows = choose_source_rows(filtered)
    rows_by_identity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_counts: Counter[str] = Counter()
    for row in chosen_rows:
        identity_key = str(row.get("stock_identity_key") or "")
        if not identity_key:
            continue
        rows_by_identity[identity_key].append(row)
        source_counts[str(row.get("source_type") or SOURCE_TDX)] += 1
    if affair_policy and set(warning_by_identity).intersection(rows_by_identity):
        warning_contract_errors.append("financial_null_warning_has_financial_rows")
        warning_contract_errors = sorted(set(warning_contract_errors))

    canonical_rows: list[dict[str, Any]] = []
    warnings: Counter[str] = Counter()
    blockers: list[str] = []
    missing_core_inputs: list[str] = []
    ttm_annualized_count = 0
    forecast_coverage_count = 0
    for identity_key in expected_keys:
        source_rows = rows_by_identity.get(identity_key, [])
        if not source_rows:
            if (
                affair_policy
                and not warning_contract_errors
                and identity_key in warning_by_identity
            ):
                row, row_warnings = build_financial_warning_only_canonical_row(
                    identity_key=identity_key,
                    source_row=warning_by_identity[identity_key],
                    daily_basic=daily_basic_by_key.get(identity_key) or {},
                    source_trade_date=source_trade_date,
                )
                canonical_rows.append(row)
                warnings.update(row_warnings)
                continue
            missing_core_inputs.append(identity_key)
            warnings["canonical_core_line_items_missing"] += 1
            continue
        row, row_warnings = build_canonical_row(
            identity_key=identity_key,
            rows=source_rows,
            daily_basic=daily_basic_by_key.get(identity_key) or {},
            source_trade_date=source_trade_date,
            affair_policy=affair_policy,
        )
        if row is None:
            missing_core_inputs.append(identity_key)
            warnings.update(row_warnings)
            continue
        canonical_rows.append(row)
        warnings.update(row_warnings)
        if "ttm_annualized" in row_warnings:
            ttm_annualized_count += 1
        if row.get("forecast_type"):
            forecast_coverage_count += 1

    duplicate_count = len(canonical_rows) - len({row["stock_identity_key"] for row in canonical_rows})
    missing_expected = sorted(set(expected_keys) - {row["stock_identity_key"] for row in canonical_rows})
    if missing_core_inputs:
        blockers.append("canonical_core_line_items_missing")
    if duplicate_count:
        blockers.append("duplicate_identity_key")
    if missing_expected:
        blockers.append("expected_identity_missing")
    blockers.extend(warning_contract_errors)

    p0_items = []
    if missing_core_inputs:
        p0_items.append(quality_item("canonical_core_line_items_missing", "P0", "failed", "0", str(len(missing_core_inputs)), {"samples": missing_core_inputs[:20]}))
    else:
        p0_items.append(quality_item("canonical_core_line_items_available", "P0", "passed", "all expected identities", str(len(canonical_rows)), {}))
    if duplicate_count:
        p0_items.append(quality_item("duplicate_identity_key", "P0", "failed", "0", str(duplicate_count), {}))
    else:
        p0_items.append(quality_item("duplicate_identity_key", "P0", "passed", "0", "0", {}))
    if warning_contract_errors:
        p0_items.append(
            quality_item(
                "financial_null_warning_lineage",
                "P0",
                "failed",
                "valid count/hash/identity binding",
                str(len(warning_contract_errors)),
                {"errors": warning_contract_errors},
            )
        )
    elif affair_policy:
        p0_items.append(
            quality_item(
                "financial_null_warning_lineage",
                "P0",
                "passed",
                "valid count/hash/identity binding",
                str(len(warning_by_identity)),
                {},
            )
        )

    p1_items = []
    if source_counts[SOURCE_TUSHARE_FALLBACK]:
        p1_items.append(quality_item("tushare_fallback_used", "P1", "warning", "0", str(source_counts[SOURCE_TUSHARE_FALLBACK]), {}))
    if warnings["interest_expense_missing_finance_expense_used"]:
        p1_items.append(quality_item("interest_expense_missing_fallback", "P1", "warning", "0", str(warnings["interest_expense_missing_finance_expense_used"]), {}))
    for warning_code in ZERO_FALLBACK_WARNING_CODES:
        if warnings[warning_code]:
            p1_items.append(quality_item(warning_code, "P1", "warning", "0", str(warnings[warning_code]), {}))
    if warnings["operating_cashflow_missing_latest"]:
        p1_items.append(quality_item("operating_cashflow_missing_latest", "P1", "warning", "0", str(warnings["operating_cashflow_missing_latest"]), {}))
    if warnings[FINANCE_SECTOR_POLICY_WARNING]:
        p1_items.append(
            quality_item(
                FINANCE_SECTOR_POLICY_WARNING,
                "P1",
                "warning",
                "0",
                str(warnings[FINANCE_SECTOR_POLICY_WARNING]),
                {},
            )
        )
    if warnings[PRE_REVENUE_POLICY_WARNING]:
        p1_items.append(
            quality_item(
                PRE_REVENUE_POLICY_WARNING,
                "P1",
                "warning",
                "0",
                str(warnings[PRE_REVENUE_POLICY_WARNING]),
                {},
            )
        )
    if warnings[LATEST_CORE_LINE_ITEMS_MISSING_FALLBACK_WARNING]:
        p1_items.append(
            quality_item(
                LATEST_CORE_LINE_ITEMS_MISSING_FALLBACK_WARNING,
                "P1",
                "warning",
                "0",
                str(warnings[LATEST_CORE_LINE_ITEMS_MISSING_FALLBACK_WARNING]),
                {},
            )
        )
    if warnings[FINANCIAL_NULL_WARNING_CODE]:
        p1_items.append(
            quality_item(
                FINANCIAL_NULL_WARNING_CODE,
                "P1",
                "warning",
                "0",
                str(warnings[FINANCIAL_NULL_WARNING_CODE]),
                {
                    "identity_keys": sorted(warning_by_identity),
                    "financial_degraded_but_fastlane_allowed": True,
                },
            )
        )
    if warnings[FINANCIAL_HISTORY_INCOMPLETE_WARNING]:
        p1_items.append(
            quality_item(
                FINANCIAL_HISTORY_INCOMPLETE_WARNING,
                "P1",
                "warning",
                "0",
                str(warnings[FINANCIAL_HISTORY_INCOMPLETE_WARNING]),
                {},
            )
        )
    if warnings[DAILY_BASIC_MISSING_WARNING]:
        p1_items.append(
            quality_item(
                DAILY_BASIC_MISSING_WARNING,
                "P1",
                "warning",
                "0",
                str(warnings[DAILY_BASIC_MISSING_WARNING]),
                {},
            )
        )
    if ttm_annualized_count:
        p1_items.append(quality_item("ttm_annualized", "P1", "warning", "0", str(ttm_annualized_count), {}))
    if not p1_items:
        p1_items.append(quality_item("canonical_warning_distribution", "P1", "passed", "reviewed", "0", {}))

    p2_items = [
        quality_item(
            "asof_exclusions",
            "P2",
            "warning" if asof_counts["future"] or asof_counts["missing_announcement"] else "passed",
            "0",
            str(asof_counts["future"] + asof_counts["missing_announcement"]),
            dict(asof_counts),
        )
    ]
    if warnings["operating_cashflow_missing_historical"]:
        p2_items.append(
            quality_item(
                "operating_cashflow_missing_historical",
                "P2",
                "warning",
                "0",
                str(warnings["operating_cashflow_missing_historical"]),
                {},
            )
        )
    if warnings[HISTORICAL_CORE_LINE_ITEMS_MISSING_WARNING]:
        p2_items.append(
            quality_item(
                HISTORICAL_CORE_LINE_ITEMS_MISSING_WARNING,
                "P2",
                "warning",
                "0",
                str(warnings[HISTORICAL_CORE_LINE_ITEMS_MISSING_WARNING]),
                {},
            )
        )
    items = p0_items + p1_items + p2_items
    severity = summarize_quality(items)
    return {
        "result": "DRY_RUN_PASS" if severity["P0"] == 0 else "DRY_RUN_BLOCKED",
        "layer_role": "N1_ingestion",
        "source_trade_date": source_trade_date,
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSION,
        "previous_source_version": PREVIOUS_SOURCE_VERSION,
        "financial_metric_version": FINANCIAL_METRIC_VERSION,
        **(
            {
                "financial_source_policy_version": FINANCIAL_SOURCE_POLICY_VERSION,
                "forecast_disabled": True,
                "effective_score_max": str(EFFECTIVE_SCORE_MAX),
            }
            if affair_policy
            else {}
        ),
        "row_counts": {"stock_financial_metrics_fact": len(canonical_rows)},
        "expected_rows": len(expected_keys),
        "rows": canonical_rows,
        "blockers": blockers,
        "summary": {
            "expected_rows": len(expected_keys),
            "tdx_primary_count": int(source_counts[SOURCE_TDX]),
            "tushare_fallback_count": int(source_counts[SOURCE_TUSHARE_FALLBACK]),
            "asof_excluded_future_rows": asof_counts["future"],
            "missing_announcement_date_excluded_rows": asof_counts["missing_announcement"],
            "interest_expense_missing_fallback_count": int(warnings["interest_expense_missing_finance_expense_used"]),
            "ttm_annualized_count": ttm_annualized_count,
            "forecast_coverage_count": forecast_coverage_count,
            **(
                {
                    "financial_null_warning_identity_count": len(warning_by_identity),
                    "financial_degraded_but_fastlane_allowed": bool(
                        probe.get("financial_degraded_but_fastlane_allowed")
                    ),
                }
                if affair_policy
                else {}
            ),
            "score_distribution": score_distribution(canonical_rows),
            "warning_distribution": dict(sorted(warnings.items())),
        },
        "quality": {"p0_count": severity["P0"], "p1_count": severity["P1"], "p2_count": severity["P2"], "items": items},
        "side_effects": default_side_effects(),
    }


def filter_asof_safe_rows(rows: Sequence[Mapping[str, Any]], source_trade_date: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    accepted: list[dict[str, Any]] = []
    counts = {"future": 0, "missing_announcement": 0}
    for row in rows:
        ann = optional_date_text(row.get("announcement_date") or row.get("ann_date"))
        if not ann:
            if bool(row.get("asof_safe")):
                accepted.append({**dict(row), "announcement_date": source_trade_date})
            else:
                counts["missing_announcement"] += 1
            continue
        if ann > source_trade_date:
            counts["future"] += 1
            continue
        accepted.append({**dict(row), "announcement_date": ann})
    return accepted, counts


def choose_source_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        identity_key = str(row.get("stock_identity_key") or "")
        report_period = optional_date_text(row.get("report_period"))
        if not identity_key or not report_period:
            continue
        key = (identity_key, report_period)
        current = by_key.get(key)
        if current is None or source_rank(row) < source_rank(current):
            by_key[key] = {**dict(row), "report_period": report_period, "source_type": source_type(row)}
    return list(by_key.values())


AFFAIR_CUMULATIVE_FIELDS = (
    "revenue",
    "operating_revenue",
    "operating_cost",
    "taxes_and_surcharges",
    "selling_expense",
    "admin_expense",
    "rd_expense",
    "interest_expense",
    "finance_expense",
    "operating_cashflow",
)


def affair_cumulative_to_single_quarter(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], Counter[str]]:
    """Convert Affair cumulative values to single-quarter values without fabricating predecessors."""

    by_period = {str(row.get("report_period") or ""): dict(row) for row in rows}
    warnings: Counter[str] = Counter()
    converted: list[dict[str, Any]] = []
    for report_period in sorted(by_period):
        row = by_period[report_period]
        suffix = report_period[4:] if len(report_period) == 8 else ""
        predecessor_suffix = {"0630": "0331", "0930": "0630", "1231": "0930"}.get(suffix)
        predecessor = by_period.get(report_period[:4] + predecessor_suffix) if predecessor_suffix else None
        item = dict(row)
        for field in AFFAIR_CUMULATIVE_FIELDS:
            current = decimal_or_none(row.get(field))
            if current is None:
                item[field] = None
                continue
            if suffix == "0331":
                item[field] = current
                continue
            if predecessor_suffix is None:
                item[field] = None
                warnings["cumulative_report_period_invalid"] += 1
                continue
            previous = decimal_or_none((predecessor or {}).get(field))
            if previous is None:
                item[field] = None
                warnings["cumulative_predecessor_missing"] += 1
            else:
                item[field] = current - previous
        item["financial_period_basis"] = "single_quarter"
        converted.append(item)
    return sorted(converted, key=lambda row: str(row.get("report_period") or ""), reverse=True), warnings


def build_canonical_row(
    *,
    identity_key: str,
    rows: Sequence[Mapping[str, Any]],
    daily_basic: Mapping[str, Any],
    source_trade_date: str,
    affair_policy: bool = False,
) -> tuple[dict[str, Any] | None, Counter[str]]:
    raw_ordered = sorted((dict(row) for row in rows), key=lambda row: str(row.get("report_period") or ""), reverse=True)
    ordered = raw_ordered
    computed_quarters: list[dict[str, Any]] = []
    warnings: Counter[str] = Counter()
    if affair_policy:
        ordered, cumulative_warnings = affair_cumulative_to_single_quarter(ordered)
        warnings.update(cumulative_warnings)
    policy_warning = canonical_policy_warning_code(identity_key=identity_key, rows=ordered, daily_basic=daily_basic)
    if policy_warning:
        return build_policy_canonical_row(
            identity_key=identity_key,
            rows=ordered,
            daily_basic=daily_basic,
            source_trade_date=source_trade_date,
            warning_code=policy_warning,
            affair_policy=affair_policy,
        )
    for row in ordered:
        warnings.update(existing_financial_warnings(row))
        core, core_warnings = compute_core_profit(row)
        if core is None:
            core_warnings.pop("canonical_core_line_items_missing", None)
            warnings.update(core_warnings)
            warnings[
                LATEST_CORE_LINE_ITEMS_MISSING_FALLBACK_WARNING
                if not computed_quarters
                else HISTORICAL_CORE_LINE_ITEMS_MISSING_WARNING
            ] += 1
            continue
        warnings.update(core_warnings)
        revenue = first_decimal(row, "report_core_revenue", "operating_revenue", "total_revenue", "revenue")
        cashflow = first_decimal(row, "operating_cashflow", "net_cashflow_operating", "n_cashflow_act")
        if cashflow is None:
            warnings["operating_cashflow_missing_latest" if not computed_quarters else "operating_cashflow_missing_historical"] += 1
        computed_quarters.append(
            {
                **row,
                "report_core_revenue": revenue,
                "report_core_profit": core,
                "operating_cashflow": cashflow,
            }
        )
    if not computed_quarters:
        if affair_policy:
            warnings[FINANCIAL_HISTORY_INCOMPLETE_WARNING] += 1
            return build_incomplete_financial_canonical_row(
                identity_key=identity_key,
                latest_source=raw_ordered[0] if raw_ordered else {},
                daily_basic=daily_basic,
                source_trade_date=source_trade_date,
                warnings=warnings,
            )
        warnings["canonical_core_line_items_missing"] = 1
        return None, warnings

    latest = computed_quarters[0]
    if source_type(latest) == SOURCE_TUSHARE_FALLBACK:
        warnings["tushare_fallback_used"] += 1
    latest_period = str(latest["report_period"])
    ttm_rows = contiguous_quarter_rows(computed_quarters, limit=4) if affair_policy else computed_quarters[:4]
    complete_four_quarter_chain = len(ttm_rows) == 4
    core_profit_ttm = sum_decimal(row["report_core_profit"] for row in ttm_rows)
    annualized = False
    if affair_policy and not complete_four_quarter_chain:
        core_profit_ttm = None
        warnings[FINANCIAL_HISTORY_INCOMPLETE_WARNING] += 1
    elif 0 < len(ttm_rows) < 4:
        core_profit_ttm = (core_profit_ttm * Decimal("4")) / Decimal(str(len(ttm_rows)))
        annualized = True
        warnings["ttm_annualized"] += 1
    latest_core_profit = decimal_or_none(latest.get("report_core_profit"))
    cash_realization_rate = (
        safe_divide(latest.get("operating_cashflow"), latest_core_profit)
        if not affair_policy or (latest_core_profit is not None and latest_core_profit > 0)
        else None
    )
    if affair_policy and latest_core_profit is not None and latest_core_profit <= 0:
        warnings["cash_realization_rate_nonpositive_core_profit"] += 1
    if cash_realization_rate is None:
        warnings["cash_realization_rate_unavailable"] += 1
    if affair_policy:
        revenue_yoy_pct = (
            calculate_yoy(latest, computed_quarters, "report_core_revenue")
            if complete_four_quarter_chain
            else None
        )
        core_profit_yoy_pct = (
            calculate_yoy(latest, computed_quarters, "report_core_profit")
            if complete_four_quarter_chain
            else None
        )
    else:
        revenue_yoy_pct = first_decimal(latest, "revenue_yoy_pct", "revenue_yoy", "or_yoy")
        if revenue_yoy_pct is None:
            revenue_yoy_pct = calculate_yoy(latest, computed_quarters, "report_core_revenue")
        core_profit_yoy_pct = first_decimal(latest, "core_profit_yoy_pct", "profit_yoy", "netprofit_yoy")
        if core_profit_yoy_pct is None:
            core_profit_yoy_pct = calculate_yoy(latest, computed_quarters, "report_core_profit")
    core_gt_revenue_yoy = (
        bool(core_profit_yoy_pct > revenue_yoy_pct)
        if revenue_yoy_pct is not None and core_profit_yoy_pct is not None
        else None
    )
    if affair_policy:
        total_mv = first_decimal(daily_basic, "total_mv")
        circ_mv = first_decimal(daily_basic, "circ_mv")
    else:
        total_mv = first_decimal(daily_basic, "total_mv") or first_decimal(latest, "total_mv")
        circ_mv = first_decimal(daily_basic, "circ_mv") or first_decimal(latest, "circ_mv")
    if affair_policy and total_mv is None:
        warnings[DAILY_BASIC_MISSING_WARNING] += 1
    if affair_policy and daily_basic.get("daily_basic_carried_forward") is True:
        warnings["daily_basic_total_mv_carried_forward"] += 1
    pe_core = None
    if total_mv is not None and core_profit_ttm not in (None, Decimal("0")):
        pe_core = safe_divide(
            total_mv * Decimal("10000") if affair_policy else total_mv,
            core_profit_ttm,
        )
    forecast_type = None if affair_policy else optional_text(latest.get("forecast_type"))
    forecast_score = None if affair_policy else forecast_score_for(forecast_type)
    if not affair_policy and not forecast_type:
        warnings["forecast_missing"] += 1
    if affair_policy:
        revenue_growth_streak_q = (
            affair_yoy_streak(computed_quarters, "report_core_revenue")
            if complete_four_quarter_chain
            else None
        )
        core_growth_streak_q = (
            affair_yoy_streak(computed_quarters, "report_core_profit")
            if complete_four_quarter_chain
            else None
        )
        core_gt_revenue_streak_q = (
            affair_core_gt_streak(computed_quarters)
            if complete_four_quarter_chain
            else None
        )
    else:
        revenue_growth_streak_q = streak(computed_quarters, "revenue_yoy_pct", positive=True)
        core_growth_streak_q = streak(computed_quarters, "core_profit_yoy_pct", positive=True)
        core_gt_revenue_streak_q = core_gt_streak(computed_quarters)
    breakdown = score_breakdown(
        report_core_profit=latest["report_core_profit"],
        cash_realization_rate=cash_realization_rate,
        pe_core=pe_core,
        revenue_yoy_pct=revenue_yoy_pct,
        core_profit_yoy_pct=core_profit_yoy_pct,
        core_gt_revenue_yoy=core_gt_revenue_yoy,
        revenue_growth_streak_q=revenue_growth_streak_q,
        core_growth_streak_q=core_growth_streak_q,
        core_gt_revenue_streak_q=core_gt_revenue_streak_q,
        forecast_score=forecast_score,
    )
    score = (
        None
        if affair_policy and (not complete_four_quarter_chain or total_mv is None)
        else min(EFFECTIVE_SCORE_MAX if affair_policy else Decimal("100"), sum_decimal(breakdown.values()))
    )
    warning_json = {"warnings": sorted(warnings.keys()), "ttm_annualized": annualized}
    exchange, code = parse_identity(identity_key)
    return {
        "stock_identity_key": identity_key,
        "asof_date": source_trade_date,
        "source_trade_date": source_trade_date,
        "announcement_date": latest.get("announcement_date"),
        "report_period": latest_period,
        "ts_code": str(latest.get("ts_code") or f"{code}.{exchange}"),
        "code": code,
        "exchange": exchange,
        "roe": first_decimal(latest, "roe"),
        "revenue_yoy": revenue_yoy_pct,
        "profit_yoy": core_profit_yoy_pct,
        "total_revenue": latest.get("report_core_revenue"),
        "net_profit": first_decimal(latest, "net_profit"),
        "net_assets": first_decimal(latest, "net_assets"),
        "eps": first_decimal(latest, "eps"),
        "bps": first_decimal(latest, "bps"),
        "pe_core": quantize_decimal(pe_core),
        "total_mv": total_mv,
        "circ_mv": circ_mv,
        "score": quantize_decimal(score),
        "warning": ";".join(warning_json["warnings"]) if warning_json["warnings"] else None,
        "quality_status": "warning" if warning_json["warnings"] else "passed",
        "cash_realization_rate": quantize_decimal(cash_realization_rate),
        "revenue_yoy_pct": quantize_decimal(revenue_yoy_pct),
        "core_profit_yoy_pct": quantize_decimal(core_profit_yoy_pct),
        "report_core_revenue": latest.get("report_core_revenue"),
        "report_core_profit": latest.get("report_core_profit"),
        "core_profit_ttm": quantize_decimal(core_profit_ttm),
        "core_gt_revenue_yoy": core_gt_revenue_yoy,
        "revenue_growth_streak_q": revenue_growth_streak_q,
        "core_growth_streak_q": core_growth_streak_q,
        "core_gt_revenue_streak_q": core_gt_revenue_streak_q,
        "forecast_type": forecast_type,
        "forecast_score": forecast_score,
        "score_breakdown_json": {key: str(value) for key, value in breakdown.items()},
        "financial_warning_json": warning_json,
        "financial_metric_version": FINANCIAL_METRIC_VERSION,
        **({"financial_source_policy_version": FINANCIAL_SOURCE_POLICY_VERSION} if affair_policy else {}),
        "source": FINANCIAL_AUTHORITY if affair_policy else "stock_financial_canonical.tdx_mootdx_first.tushare_fallback",
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSION,
        "raw_payload": {
            "latest_source": json_safe(latest),
            "quarter_count": len(computed_quarters),
            **(
                {
                    "financial_source_policy_version": FINANCIAL_SOURCE_POLICY_VERSION,
                    "complete_four_quarter_chain": complete_four_quarter_chain,
                }
                if affair_policy
                else {}
            ),
        },
    }, warnings


def canonical_policy_warning_code(
    *,
    identity_key: str,
    rows: Sequence[Mapping[str, Any]],
    daily_basic: Mapping[str, Any],
) -> str | None:
    latest = rows[0] if rows else {}
    industry = canonical_industry(latest, daily_basic)
    if industry in FINANCE_SECTOR_INDUSTRIES:
        return FINANCE_SECTOR_POLICY_WARNING
    missing = set(missing_core_policy_fields(latest))
    if identity_key in PRE_REVENUE_IDENTITY_KEYS and {"operating_revenue", "operating_cost"}.issubset(missing):
        return PRE_REVENUE_POLICY_WARNING
    return None


def build_policy_canonical_row(
    *,
    identity_key: str,
    rows: Sequence[Mapping[str, Any]],
    daily_basic: Mapping[str, Any],
    source_trade_date: str,
    warning_code: str,
    affair_policy: bool = False,
) -> tuple[dict[str, Any], Counter[str]]:
    latest = dict(rows[0] if rows else {})
    warnings = Counter({warning_code: 1})
    for row in rows:
        for code in existing_financial_warnings(row):
            if code not in {FINANCE_SECTOR_POLICY_WARNING, PRE_REVENUE_POLICY_WARNING, "canonical_core_line_items_missing"}:
                warnings[code] += 1
    industry = canonical_industry(latest, daily_basic)
    exchange, code = parse_identity(identity_key)
    if affair_policy:
        total_mv = first_decimal(daily_basic, "total_mv")
        circ_mv = first_decimal(daily_basic, "circ_mv")
    else:
        total_mv = first_decimal(daily_basic, "total_mv") or first_decimal(latest, "total_mv")
        circ_mv = first_decimal(daily_basic, "circ_mv") or first_decimal(latest, "circ_mv")
    if affair_policy and total_mv is None:
        warnings[DAILY_BASIC_MISSING_WARNING] += 1
    if affair_policy and daily_basic.get("daily_basic_carried_forward") is True:
        warnings["daily_basic_total_mv_carried_forward"] += 1
    forecast_type = None if affair_policy else optional_text(latest.get("forecast_type"))
    forecast_score = None if affair_policy else forecast_score_for(forecast_type)
    if not affair_policy and not forecast_type:
        warnings["forecast_missing"] += 1
    warning_json = {
        "warnings": sorted(warnings.keys()),
        "severity": "P1",
        "sector_policy": warning_code,
        "industry": industry,
        "disabled_components": list(POLICY_DISABLED_COMPONENTS),
    }
    return {
        "stock_identity_key": identity_key,
        "asof_date": source_trade_date,
        "source_trade_date": source_trade_date,
        "announcement_date": latest.get("announcement_date"),
        "report_period": str(latest.get("report_period") or ""),
        "ts_code": str(latest.get("ts_code") or f"{code}.{exchange}"),
        "code": code,
        "exchange": exchange,
        "roe": first_decimal(latest, "roe"),
        "revenue_yoy": None,
        "profit_yoy": None,
        "total_revenue": first_decimal(latest, "total_revenue", "operating_revenue", "report_core_revenue"),
        "net_profit": first_decimal(latest, "net_profit"),
        "net_assets": first_decimal(latest, "net_assets"),
        "eps": first_decimal(latest, "eps"),
        "bps": first_decimal(latest, "bps"),
        "pe_core": None,
        "total_mv": total_mv,
        "circ_mv": circ_mv,
        "score": None,
        "warning": ";".join(warning_json["warnings"]),
        "quality_status": "warning",
        "cash_realization_rate": None,
        "revenue_yoy_pct": None,
        "core_profit_yoy_pct": None,
        "report_core_revenue": None,
        "report_core_profit": None,
        "core_profit_ttm": None,
        "core_gt_revenue_yoy": None,
        "revenue_growth_streak_q": None,
        "core_growth_streak_q": None,
        "core_gt_revenue_streak_q": None,
        "forecast_type": forecast_type,
        "forecast_score": forecast_score,
        "score_breakdown_json": {
            "policy": "disabled",
            "reason": warning_code,
            "disabled_components": list(POLICY_DISABLED_COMPONENTS),
            **({"forecast_score": "0"} if affair_policy else {}),
        },
        "financial_warning_json": warning_json,
        "financial_metric_version": FINANCIAL_METRIC_VERSION,
        **({"financial_source_policy_version": FINANCIAL_SOURCE_POLICY_VERSION} if affair_policy else {}),
        "source": FINANCIAL_AUTHORITY if affair_policy else "stock_financial_canonical.policy_v1",
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSION,
        "raw_payload": {
            "latest_source": json_safe(latest),
            "quarter_count": len(rows),
            "sector_policy": warning_code,
            **(
                {"financial_source_policy_version": FINANCIAL_SOURCE_POLICY_VERSION}
                if affair_policy
                else {}
            ),
        },
    }, warnings


def build_financial_warning_only_canonical_row(
    *,
    identity_key: str,
    source_row: Mapping[str, Any],
    daily_basic: Mapping[str, Any],
    source_trade_date: str,
) -> tuple[dict[str, Any], Counter[str]]:
    if not is_financial_warning_only_row(source_row):
        raise StockFinancialCanonicalBlocked("financial_null_warning_row_not_authorized")
    exchange, code = parse_identity(identity_key)
    warnings = Counter({FINANCIAL_NULL_WARNING_CODE: 1})
    total_mv = first_decimal(daily_basic, "total_mv")
    circ_mv = first_decimal(daily_basic, "circ_mv")
    if total_mv is None:
        warnings[DAILY_BASIC_MISSING_WARNING] += 1
    warning_payload = source_row.get("financial_warning_json")
    warning_reason = (
        warning_payload.get("reason")
        if isinstance(warning_payload, Mapping)
        else None
    )
    warning_json = {
        "warnings": sorted(warnings),
        "severity": "P1",
        "reason": warning_reason or "financial_source_unavailable",
        "financial_degraded_but_fastlane_allowed": True,
    }
    return {
        "stock_identity_key": identity_key,
        "asof_date": source_trade_date,
        "source_trade_date": source_trade_date,
        "announcement_date": None,
        "report_period": None,
        "ts_code": str(source_row.get("ts_code") or f"{code}.{exchange}"),
        "code": code,
        "exchange": exchange,
        "roe": None,
        "revenue_yoy": None,
        "profit_yoy": None,
        "total_revenue": None,
        "net_profit": None,
        "net_assets": None,
        "eps": None,
        "bps": None,
        "pe_core": None,
        "total_mv": total_mv,
        "circ_mv": circ_mv,
        "score": None,
        "warning": ";".join(warning_json["warnings"]),
        "quality_status": "warning",
        "cash_realization_rate": None,
        "revenue_yoy_pct": None,
        "core_profit_yoy_pct": None,
        "report_core_revenue": None,
        "report_core_profit": None,
        "core_profit_ttm": None,
        "core_gt_revenue_yoy": None,
        "revenue_growth_streak_q": None,
        "core_growth_streak_q": None,
        "core_gt_revenue_streak_q": None,
        "forecast_type": None,
        "forecast_score": None,
        "score_breakdown_json": {
            "policy": "financial_warning_only",
            "reason": FINANCIAL_NULL_WARNING_CODE,
            "forecast_score": "0",
        },
        "financial_warning_json": warning_json,
        "financial_metric_version": FINANCIAL_METRIC_VERSION,
        "financial_source_policy_version": FINANCIAL_SOURCE_POLICY_VERSION,
        "source": FINANCIAL_AUTHORITY,
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSION,
        "raw_payload": {
            "financial_source_policy_version": FINANCIAL_SOURCE_POLICY_VERSION,
            "financial_warning_only": True,
            "financial_values_fabricated": False,
            "warning_code": FINANCIAL_NULL_WARNING_CODE,
            "reason": warning_json["reason"],
        },
    }, warnings


def build_incomplete_financial_canonical_row(
    *,
    identity_key: str,
    latest_source: Mapping[str, Any],
    daily_basic: Mapping[str, Any],
    source_trade_date: str,
    warnings: Counter[str],
) -> tuple[dict[str, Any], Counter[str]]:
    """Keep an Affair identity without claiming metrics that need a provable single quarter."""

    exchange, code = parse_identity(identity_key)
    row_warnings = Counter(warnings)
    for code_to_remove in (
        "canonical_core_line_items_missing",
        "interest_expense_missing_finance_expense_used",
        LATEST_CORE_LINE_ITEMS_MISSING_FALLBACK_WARNING,
        HISTORICAL_CORE_LINE_ITEMS_MISSING_WARNING,
        *ZERO_FALLBACK_WARNING_CODES,
    ):
        row_warnings.pop(code_to_remove, None)
    row_warnings[FINANCIAL_HISTORY_INCOMPLETE_WARNING] = max(
        1,
        row_warnings[FINANCIAL_HISTORY_INCOMPLETE_WARNING],
    )
    total_mv = first_decimal(daily_basic, "total_mv")
    circ_mv = first_decimal(daily_basic, "circ_mv")
    if total_mv is None:
        row_warnings[DAILY_BASIC_MISSING_WARNING] += 1
    warning_json = {
        "warnings": sorted(row_warnings),
        "severity": "P1",
        "reason": FINANCIAL_HISTORY_INCOMPLETE_WARNING,
        "financial_degraded_but_fastlane_allowed": True,
    }
    return {
        "stock_identity_key": identity_key,
        "asof_date": source_trade_date,
        "source_trade_date": source_trade_date,
        "announcement_date": latest_source.get("announcement_date"),
        "report_period": latest_source.get("report_period"),
        "ts_code": str(latest_source.get("ts_code") or f"{code}.{exchange}"),
        "code": code,
        "exchange": exchange,
        "roe": first_decimal(latest_source, "roe"),
        "revenue_yoy": None,
        "profit_yoy": None,
        "total_revenue": None,
        "net_profit": first_decimal(latest_source, "net_profit"),
        "net_assets": first_decimal(latest_source, "net_assets"),
        "eps": first_decimal(latest_source, "eps"),
        "bps": first_decimal(latest_source, "bps"),
        "pe_core": None,
        "total_mv": total_mv,
        "circ_mv": circ_mv,
        "score": None,
        "warning": FINANCIAL_HISTORY_INCOMPLETE_WARNING,
        "quality_status": "warning",
        "cash_realization_rate": None,
        "revenue_yoy_pct": None,
        "core_profit_yoy_pct": None,
        "report_core_revenue": None,
        "report_core_profit": None,
        "core_profit_ttm": None,
        "core_gt_revenue_yoy": None,
        "revenue_growth_streak_q": None,
        "core_growth_streak_q": None,
        "core_gt_revenue_streak_q": None,
        "forecast_type": None,
        "forecast_score": None,
        "score_breakdown_json": {
            "policy": "financial_history_incomplete",
            "reason": FINANCIAL_HISTORY_INCOMPLETE_WARNING,
            "forecast_score": "0",
        },
        "financial_warning_json": warning_json,
        "financial_metric_version": FINANCIAL_METRIC_VERSION,
        "financial_source_policy_version": FINANCIAL_SOURCE_POLICY_VERSION,
        "source": FINANCIAL_AUTHORITY,
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSION,
        "raw_payload": {
            "financial_source_policy_version": FINANCIAL_SOURCE_POLICY_VERSION,
            "financial_history_incomplete": True,
            "financial_values_fabricated": False,
            "latest_source": json_safe(latest_source),
        },
    }, row_warnings


def compute_core_profit(row: Mapping[str, Any]) -> tuple[Decimal | None, Counter[str]]:
    warnings: Counter[str] = Counter()
    revenue = first_decimal(row, "report_core_revenue", "operating_revenue", "total_revenue", "revenue")
    operating_cost = first_decimal(row, "operating_cost", "total_operating_cost")
    taxes = first_decimal(row, "taxes_and_surcharges", "biz_tax_surchg")
    selling = first_decimal(row, "selling_expense", "sell_exp")
    if selling is None:
        selling = Decimal("0")
        warnings["selling_expense_missing_fallback_zero"] += 1
    admin = first_decimal(row, "admin_expense", "admin_exp")
    rd = first_decimal(row, "rd_expense", "研发费用")
    if rd is None:
        rd = Decimal("0")
        warnings["rd_expense_missing_fallback_zero"] += 1
    interest = first_decimal(row, "interest_expense", "interest_exp")
    if interest is None:
        interest = first_decimal(row, "finance_expense", "fin_exp")
        if interest is not None:
            warnings["interest_expense_missing_finance_expense_used"] += 1
    costs = [operating_cost, taxes, selling, admin, rd]
    if revenue is None or operating_cost is None or taxes is None or admin is None or interest is None:
        warnings["canonical_core_line_items_missing"] += 1
        return None, warnings
    return revenue - sum_decimal(costs) - interest, warnings


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


def missing_core_policy_fields(row: Mapping[str, Any]) -> list[str]:
    missing = []
    if first_decimal(row, "report_core_revenue", "operating_revenue", "total_revenue", "revenue") is None:
        missing.append("operating_revenue")
    if first_decimal(row, "operating_cost", "total_operating_cost") is None:
        missing.append("operating_cost")
    return missing


def existing_financial_warnings(row: Mapping[str, Any]) -> Counter[str]:
    warnings: Counter[str] = Counter()
    payload = row.get("financial_warning_json")
    if not isinstance(payload, Mapping):
        return warnings
    raw_warnings = payload.get("warnings") or []
    if isinstance(raw_warnings, Sequence) and not isinstance(raw_warnings, (str, bytes, bytearray)):
        for warning in raw_warnings:
            warnings[str(warning)] += 1
    return warnings


def build_snapshot_from_db(*, dsn: str, source_trade_date: str = TRADE_DATE) -> dict[str, Any]:
    source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    with psycopg.connect(dsn, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            def one(sql: str, params: Sequence[Any] = ()) -> Any:
                cur.execute(sql, params)
                return cur.fetchone()["value"]

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
                       total_revenue, net_profit, total_mv, circ_mv, pe_core, score, quality_status,
                       source, raw_payload
                FROM stock_financial_metrics_fact
                WHERE source_trade_date=%s AND source_version=%s
                ORDER BY stock_identity_key
                """,
                (source_trade_date, active_version),
            )
            active_rows = [dict(row) for row in cur.fetchall()]
            expected_keys = [str(row["stock_identity_key"]) for row in active_rows]
            source_rows = source_rows_from_existing_active(active_rows)
            daily_basic_rows = daily_basic_rows_from_existing_active(active_rows)
            event_counts = {
                "common_event_outbox": one("SELECT count(*)::bigint AS value FROM common_event_outbox"),
                "common_event_inbox": one("SELECT count(*)::bigint AS value FROM common_event_inbox"),
                "common_event_consumer_checkpoint": one("SELECT count(*)::bigint AS value FROM common_event_consumer_checkpoint"),
            }
            conflicts = {
                "batch_conflict": one("SELECT count(*)::bigint AS value FROM common_ingest_batch WHERE batch_id=%s", (BATCH_ID,)),
                "quality_conflict": one("SELECT count(*)::bigint AS value FROM common_quality_gate_result WHERE source_batch_id=%s", (BATCH_ID,)),
                "active_conflict": one(
                    """
                    SELECT count(*)::bigint AS value
                    FROM common_active_source_version
                    WHERE data_domain='stock' AND data_type='stock_financial' AND scope_key=%s AND source_version=%s
                    """,
                    (source_trade_date, SOURCE_VERSION),
                ),
                "target_source_version_rows": one(
                    "SELECT count(*)::bigint AS value FROM stock_financial_metrics_fact WHERE source_trade_date=%s AND source_version=%s",
                    (source_trade_date, SOURCE_VERSION),
                ),
            }
    return {
        "source_trade_date": source_trade_date,
        "active_source_version": active_version,
        "active_source_batch_id": active.get("source_batch_id"),
        "expected_identity_keys": expected_keys,
        "financial_rows": source_rows,
        "daily_basic_rows": daily_basic_rows,
        "baseline": {
            "active_rows": len(active_rows),
            "conflicts": conflicts,
            "event_counts": event_counts,
        },
        "source_probe": {
            "uses_existing_active_raw_payload": True,
            "external_tdx_fetch_performed": False,
            "external_tushare_fetch_performed": False,
        },
    }


def build_snapshot_from_cache(
    *,
    dsn: str,
    source_trade_date: str = TRADE_DATE,
    source_bundle_cache_path: str | Path,
) -> dict[str, Any]:
    """Build the execute source snapshot from the approved read-only source bundle cache."""
    from ashare_v3.ingestion.stock_financial import StockFinancialSymbol
    from ashare_v3.ingestion.stock_financial_canonical_source_bundle import (
        build_snapshot_from_db as build_source_bundle_snapshot_from_db,
        fetch_tushare_rows_from_client,
        merge_daily_basic_metadata,
    )

    cache_path = Path(source_bundle_cache_path)
    if not cache_path.exists():
        raise StockFinancialCanonicalBlocked(f"source bundle cache path does not exist: {cache_path}")
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, Mapping) and payload.get("schema_version") in SUPPORTED_FINANCIAL_CANONICAL_SNAPSHOT_SCHEMA_VERSIONS:
        snapshot = snapshot_payload_to_metrics_snapshot(payload)
        if snapshot["source_trade_date"] != source_trade_date:
            raise StockFinancialCanonicalBlocked(
                f"financial_canonical_snapshot_trade_date_mismatch: expected={source_trade_date}, actual={snapshot['source_trade_date']}"
            )
        return snapshot

    class CacheOnlyTushareClient:
        def income(self, **_: Any) -> list[dict[str, Any]]:
            raise StockFinancialCanonicalBlocked("source bundle cache miss would require live Tushare income fetch")

        def cashflow(self, **_: Any) -> list[dict[str, Any]]:
            raise StockFinancialCanonicalBlocked("source bundle cache miss would require live Tushare cashflow fetch")

        def forecast(self, **_: Any) -> list[dict[str, Any]]:
            raise StockFinancialCanonicalBlocked("source bundle cache miss would require live Tushare forecast fetch")

        def daily_basic(self, **_: Any) -> list[dict[str, Any]]:
            raise StockFinancialCanonicalBlocked("source bundle cache miss would require live Tushare daily_basic fetch")

    source_snapshot = build_source_bundle_snapshot_from_db(
        dsn=dsn,
        source_trade_date=source_trade_date,
        source_fetch_enabled=False,
        max_symbols=0,
        full_fetch_confirmed=True,
    )
    expected_keys = list(source_snapshot.get("expected_identity_keys") or [])
    symbols = [
        StockFinancialSymbol(code=str(key).split(":", 2)[2], exchange=str(key).split(":", 2)[1])
        for key in expected_keys
    ]
    source_bundle = fetch_tushare_rows_from_client(
        pro=CacheOnlyTushareClient(),
        symbols=symbols,
        source_trade_date=source_trade_date,
        resume_cache_path=cache_path,
        rate_limit_ms=0,
        sleep_fn=lambda _: None,
    )
    source_errors = list(source_bundle.get("source_errors") or [])
    if source_errors:
        raise StockFinancialCanonicalBlocked(f"source bundle cache has source errors: {source_errors[:3]}")
    daily_basic_rows = merge_daily_basic_metadata(
        source_bundle.get("daily_basic_rows") or [],
        source_snapshot.get("daily_basic_rows") or [],
    )
    return {
        "source_trade_date": source_trade_date,
        "active_source_version": (source_snapshot.get("baseline") or {}).get("active_stock_financial_source_version"),
        "expected_identity_keys": expected_keys,
        "financial_rows": source_bundle.get("financial_rows") or [],
        "daily_basic_rows": daily_basic_rows,
        "baseline": {
            "active_rows": (source_snapshot.get("baseline") or {}).get("active_stock_financial_rows"),
            "conflicts": (source_snapshot.get("baseline") or {}).get("conflicts") or {},
            "event_counts": (source_snapshot.get("baseline") or {}).get("event_counts") or {},
        },
        "source_probe": {
            "uses_canonical_source_bundle_cache": True,
            "source_bundle_cache_path": str(cache_path),
            "source_bundle_cache_rows": len(source_bundle.get("financial_rows") or []),
            "source_bundle_cache_forecast_rows": len(source_bundle.get("forecast_rows") or []),
            "source_errors": source_errors,
            "writes_performed": False,
        },
    }


def snapshot_payload_to_metrics_snapshot(payload: Mapping[str, Any]) -> dict[str, Any]:
    schema_version = payload.get("schema_version")
    if schema_version not in SUPPORTED_FINANCIAL_CANONICAL_SNAPSHOT_SCHEMA_VERSIONS:
        raise StockFinancialCanonicalBlocked("source bundle cache is not a supported financial canonical snapshot")
    from ashare_v3.ingestion.stock_financial_canonical_source_bundle import (
        validate_financial_canonical_snapshot,
    )

    if (
        schema_version == FINANCIAL_CANONICAL_SNAPSHOT_SCHEMA_VERSION_V2
        and validate_financial_canonical_snapshot(payload) is None
    ):
        raise StockFinancialCanonicalBlocked("financial canonical snapshot integrity validation failed")
    source_trade_date = require_yyyymmdd(str(payload.get("source_trade_date") or ""), "source_trade_date")
    expected_identity_keys = [str(key) for key in list(payload.get("expected_identity_keys") or []) if key]
    financial_rows = [dict(row) for row in list(payload.get("financial_rows") or []) if isinstance(row, Mapping)]
    daily_basic_rows = [dict(row) for row in list(payload.get("daily_basic_rows") or []) if isinstance(row, Mapping)]
    return {
        "source_trade_date": source_trade_date,
        "active_source_version": payload.get("active_source_version") or PREVIOUS_SOURCE_VERSION,
        "expected_identity_keys": expected_identity_keys,
        "financial_rows": financial_rows,
        "daily_basic_rows": daily_basic_rows,
        "baseline": payload.get("baseline") or {"conflicts": {}, "event_counts": {}, "active_rows": len(expected_identity_keys)},
        "source_probe": {
            **dict(payload.get("source_probe") or {}),
            "uses_financial_canonical_snapshot_v1": schema_version == FINANCIAL_CANONICAL_SNAPSHOT_SCHEMA_VERSION,
            "uses_financial_canonical_snapshot_v2": schema_version == FINANCIAL_CANONICAL_SNAPSHOT_SCHEMA_VERSION_V2,
            "source_bundle_cache_rows": len(financial_rows),
            "writes_performed": False,
        },
    }


def source_rows_from_existing_active(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    source_rows = []
    for row in rows:
        raw_payload = row.get("raw_payload") or {}
        selected = raw_payload.get("selected_financial") if isinstance(raw_payload, Mapping) else None
        source_rows.append(
            {
                "stock_identity_key": row.get("stock_identity_key"),
                "ts_code": row.get("ts_code"),
                "code": row.get("code"),
                "exchange": row.get("exchange"),
                "report_period": row.get("report_period"),
                "announcement_date": row.get("announcement_date"),
                "source_type": SOURCE_TDX if "tdx" in str(row.get("source") or "").lower() or "mootdx" in str(row.get("source") or "").lower() else SOURCE_TUSHARE_FALLBACK,
                "total_revenue": row.get("total_revenue") or (selected or {}).get("total_revenue") if isinstance(selected, Mapping) else row.get("total_revenue"),
                "net_profit": row.get("net_profit") or (selected or {}).get("net_profit") if isinstance(selected, Mapping) else row.get("net_profit"),
                "total_mv": row.get("total_mv"),
                "circ_mv": row.get("circ_mv"),
                "forecast_type": None,
            }
        )
    return source_rows


def daily_basic_rows_from_existing_active(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        raw_payload = row.get("raw_payload") or {}
        daily_basic = raw_payload.get("daily_basic") if isinstance(raw_payload, Mapping) else None
        output.append(
            {
                "stock_identity_key": row.get("stock_identity_key"),
                "total_mv": (daily_basic or {}).get("total_mv") if isinstance(daily_basic, Mapping) else row.get("total_mv"),
                "circ_mv": (daily_basic or {}).get("circ_mv") if isinstance(daily_basic, Mapping) else row.get("circ_mv"),
            }
        )
    return output


def build_dry_run_report(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    calc = calculate_canonical_financial_metrics(
        financial_rows=snapshot.get("financial_rows") or [],
        daily_basic_rows=snapshot.get("daily_basic_rows") or [],
        source_trade_date=str(snapshot.get("source_trade_date") or TRADE_DATE),
        expected_identity_keys=snapshot.get("expected_identity_keys") or [],
        source_probe=snapshot.get("source_probe") or {},
    )
    baseline = snapshot.get("baseline") or {}
    return json_safe(
        {
            **{key: value for key, value in calc.items() if key != "rows"},
            "stage": "N1 stock_financial canonical metrics dry-run",
            "mode": "dry_run",
            "rows_sample": calc["rows"][:5],
            "baseline": baseline,
            "source_probe": snapshot.get("source_probe") or {},
            "writes_performed": False,
            "target_source_version_rows": (baseline.get("conflicts") or {}).get("target_source_version_rows"),
        }
    )


def build_execute_contract(snapshot: Mapping[str, Any], dry_run: Mapping[str, Any]) -> dict[str, Any]:
    conflicts = ((snapshot.get("baseline") or {}).get("conflicts") or {})
    source_probe = snapshot.get("source_probe") if isinstance(snapshot.get("source_probe"), Mapping) else {}
    affair_policy = source_probe.get("financial_source_policy_version") == FINANCIAL_SOURCE_POLICY_VERSION
    blockers = list(dry_run.get("blockers") or [])
    for name, count in conflicts.items():
        if int(count or 0) != 0:
            blockers.append(name)
    if (snapshot.get("active_source_version") or PREVIOUS_SOURCE_VERSION) != PREVIOUS_SOURCE_VERSION:
        blockers.append("active_stock_financial_v1_not_current")
    return json_safe(
        {
            "result": "DESIGN_PASS",
            "stage": "N1 stock_financial canonical metrics execute contract",
            "layer_role": "N1_ingestion",
            "source_trade_date": snapshot.get("source_trade_date") or TRADE_DATE,
            "source_batch_id": BATCH_ID,
            "source_version": SOURCE_VERSION,
            "previous_source_version": snapshot.get("active_source_version") or PREVIOUS_SOURCE_VERSION,
            "financial_metric_version": FINANCIAL_METRIC_VERSION,
            **(
                {
                    "financial_source_policy_version": FINANCIAL_SOURCE_POLICY_VERSION,
                    "financial_authority": FINANCIAL_AUTHORITY,
                    "tushare_allowed_endpoints": ["daily_basic"],
                    "forecast_disabled": True,
                    "effective_score_max": str(EFFECTIVE_SCORE_MAX),
                }
                if affair_policy
                else {}
            ),
            "expected_rows": dry_run.get("expected_rows"),
            "dry_run_result": dry_run.get("result"),
            "allowed_future_write_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
            "forbidden_scope": list(FORBIDDEN_SCOPE),
            "source_priority": [FINANCIAL_AUTHORITY] if affair_policy else [SOURCE_TDX, SOURCE_TUSHARE_FALLBACK],
            "asof_guard": "announcement_date <= source_trade_date; unproven missing announcement_date excluded",
            "line_item_fallback_policy": {
                "rd_expense": {
                    "fallback": "0",
                    "warning_code": "rd_expense_missing_fallback_zero",
                    "severity": "P1",
                    "financial_warning_json_required": True,
                },
                "selling_expense": {
                    "fallback": "0",
                    "warning_code": "selling_expense_missing_fallback_zero",
                    "severity": "P1",
                    "financial_warning_json_required": True,
                },
                "operating_cashflow": {
                    "latest_missing_behavior": "cash_realization_rate_null_and_cash_score_zero",
                    "warning_code": "operating_cashflow_missing_latest",
                    "severity": "P1",
                    "financial_warning_json_required": True,
                },
                "finance_sector_policy": {
                    "industries": sorted(FINANCE_SECTOR_INDUSTRIES),
                    "warning_code": FINANCE_SECTOR_POLICY_WARNING,
                    "severity": "P1",
                    "output": {
                        "report_core_profit": None,
                        "cash_realization_rate": None,
                        "core_profit_ttm": None,
                        "pe_core": None,
                        "score": None,
                    },
                    "financial_warning_json_required": True,
                },
                "pre_revenue_policy": {
                    "identity_keys": sorted(PRE_REVENUE_IDENTITY_KEYS),
                    "warning_code": PRE_REVENUE_POLICY_WARNING,
                    "severity": "P1",
                    "output": {
                        "report_core_profit": None,
                        "cash_realization_rate": None,
                        "core_profit_ttm": None,
                        "pe_core": None,
                        "score": None,
                    },
                    "financial_warning_json_required": True,
                },
                "operating_cost": {"fallback": None, "severity": "P0 unless finance/pre-revenue policy applies"},
                "operating_revenue": {"fallback": None, "severity": "P0 unless pre-revenue policy applies"},
            },
            "execute_flags_required": ["--execute", "--user-confirmed", "--postgres-commit-enabled"],
            "source_bundle_cache_input_required": True,
            "execute_command_template": (
                "PYTHONPATH=src python3 scripts/run_stock_financial_canonical_metrics_once.py "
                f"--source-trade-date {snapshot.get('source_trade_date') or TRADE_DATE} "
                "--source-bundle-cache-path "
                f"{DEFAULT_SOURCE_BUNDLE_CACHE_PATH} "
                "--execute --user-confirmed --postgres-commit-enabled"
            ),
            "final_execute_gate_allowed": not blockers and (dry_run.get("quality") or {}).get("p0_count") == 0,
            "final_execute_blockers": blockers,
            "rollback_sql_path": str(DEFAULT_PATHS["rollback_sql"]),
            "side_effects": default_side_effects(),
        }
    )


def build_execute_preflight_report(snapshot: Mapping[str, Any], dry_run: Mapping[str, Any]) -> dict[str, Any]:
    conflicts = ((snapshot.get("baseline") or {}).get("conflicts") or {})
    source_probe = snapshot.get("source_probe") if isinstance(snapshot.get("source_probe"), Mapping) else {}
    affair_policy = source_probe.get("financial_source_policy_version") == FINANCIAL_SOURCE_POLICY_VERSION
    blockers = list(dry_run.get("blockers") or [])
    for name, count in conflicts.items():
        if int(count or 0) != 0:
            blockers.append(name)
    if (snapshot.get("active_source_version") or PREVIOUS_SOURCE_VERSION) != PREVIOUS_SOURCE_VERSION:
        blockers.append("active_stock_financial_v1_not_current")
    if (dry_run.get("quality") or {}).get("p0_count", 0) != 0:
        blockers.append("canonical_metrics_p0_not_zero")
    blockers = sorted(set(blockers))
    return json_safe(
        {
            "result": "PREFLIGHT_PASS" if not blockers else "BLOCKED",
            "stage": "N1 stock_financial canonical metrics execute preflight",
            "layer_role": "N1_ingestion",
            "source_trade_date": snapshot.get("source_trade_date") or TRADE_DATE,
            "source_batch_id": BATCH_ID,
            "source_version": SOURCE_VERSION,
            "previous_source_version": snapshot.get("active_source_version") or PREVIOUS_SOURCE_VERSION,
            **(
                {
                    "financial_source_policy_version": FINANCIAL_SOURCE_POLICY_VERSION,
                    "financial_authority": FINANCIAL_AUTHORITY,
                    "tushare_allowed_endpoints": ["daily_basic"],
                    "forecast_disabled": True,
                    "effective_score_max": str(EFFECTIVE_SCORE_MAX),
                }
                if affair_policy
                else {}
            ),
            "runner_readiness": "ready_for_final_gate" if not blockers else "blocked",
            "execute_runner_implemented": True,
            "execute_authorized": False,
            "final_execute_gate_allowed": not blockers,
            "blockers": blockers,
            "expected_rows": dry_run.get("expected_rows"),
            "row_counts": dry_run.get("row_counts"),
            "summary": dry_run.get("summary"),
            "quality": dry_run.get("quality"),
            "baseline": snapshot.get("baseline") or {},
            "allowed_future_write_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
            "forbidden_scope": list(FORBIDDEN_SCOPE),
            "rollback_sql_path": str(DEFAULT_PATHS["rollback_sql"]),
            "execute_command_template": (
                "PYTHONPATH=src python3 scripts/run_stock_financial_canonical_metrics_once.py "
                f"--source-trade-date {snapshot.get('source_trade_date') or TRADE_DATE} "
                "--source-bundle-cache-path "
                f"{DEFAULT_SOURCE_BUNDLE_CACHE_PATH} "
                "--execute --user-confirmed --postgres-commit-enabled"
            ),
            "side_effects": default_side_effects(),
        }
    )


def validate_commit_preconditions(
    *,
    snapshot: Mapping[str, Any],
    dry_run: Mapping[str, Any],
    postgres_commit_enabled: bool,
) -> None:
    if not postgres_commit_enabled:
        raise StockFinancialCanonicalBlocked("missing required final flag: --postgres-commit-enabled")
    if (dry_run.get("quality") or {}).get("p0_count", 0) != 0:
        blockers = dry_run.get("blockers") or ["canonical_metrics_p0_not_zero"]
        raise StockFinancialCanonicalBlocked(", ".join(str(item) for item in blockers))
    if dry_run.get("result") != "DRY_RUN_PASS":
        raise StockFinancialCanonicalBlocked(str(dry_run.get("result") or "dry_run_not_passed"))
    if int((dry_run.get("row_counts") or {}).get("stock_financial_metrics_fact") or 0) != int(dry_run.get("expected_rows") or 0):
        raise StockFinancialCanonicalBlocked("stock_financial_metrics_fact_row_count_mismatch")
    if (snapshot.get("active_source_version") or PREVIOUS_SOURCE_VERSION) != PREVIOUS_SOURCE_VERSION:
        raise StockFinancialCanonicalBlocked("active_stock_financial_v1_not_current")
    conflicts = ((snapshot.get("baseline") or {}).get("conflicts") or {})
    conflicting = [name for name, count in conflicts.items() if int(count or 0) != 0]
    if conflicting:
        raise StockFinancialCanonicalBlocked(", ".join(conflicting))


def build_commit_plan(*, snapshot: Mapping[str, Any], dry_run: Mapping[str, Any]) -> dict[str, Any]:
    rows = list(dry_run.get("rows") or [])
    if not rows:
        calc = calculate_canonical_financial_metrics(
            financial_rows=snapshot.get("financial_rows") or [],
            daily_basic_rows=snapshot.get("daily_basic_rows") or [],
            source_trade_date=str(snapshot.get("source_trade_date") or TRADE_DATE),
            expected_identity_keys=snapshot.get("expected_identity_keys") or [],
            source_probe=snapshot.get("source_probe") or {},
        )
        rows = list(calc.get("rows") or [])
    expected_rows = int((dry_run.get("row_counts") or {}).get("stock_financial_metrics_fact") or 0)
    if len(rows) != expected_rows:
        raise StockFinancialCanonicalBlocked(
            f"stock_financial_commit_plan_row_count_mismatch: expected={expected_rows}, actual={len(rows)}"
        )
    quality_items = list((dry_run.get("quality") or {}).get("items") or [])
    quality_rows = [
        {
            "source_batch_id": BATCH_ID,
            "source_version": SOURCE_VERSION,
            "data_domain": "stock",
            "data_type": "stock_financial_canonical_metrics",
            **dict(item),
        }
        for item in quality_items
    ]
    active_metadata = snapshot.get("active_source_metadata")
    if not isinstance(active_metadata, Mapping):
        raise StockFinancialCanonicalBlocked("active_stock_financial_metadata_missing")
    previous_source_version = str(snapshot.get("active_source_version") or PREVIOUS_SOURCE_VERSION)
    expected_active_metadata = {
        "data_domain": "stock",
        "data_type": "stock_financial",
        "scope_key": TRADE_DATE,
        "source_version": previous_source_version,
    }
    mismatched_active_metadata = [
        key
        for key, expected in expected_active_metadata.items()
        if str(active_metadata.get(key) or "") != expected
    ]
    if mismatched_active_metadata:
        raise StockFinancialCanonicalBlocked(
            "active_stock_financial_metadata_mismatch: " + ",".join(mismatched_active_metadata)
        )
    previous_source_batch_id = str(active_metadata.get("source_batch_id") or "").strip()
    if not previous_source_batch_id:
        raise StockFinancialCanonicalBlocked("active_stock_financial_source_batch_id_missing")
    previous_row_count = int(active_metadata.get("row_count") or 0)
    previous_identity_count = int(active_metadata.get("identity_count") or 0)
    if previous_row_count != expected_rows or previous_identity_count != expected_rows:
        raise StockFinancialCanonicalBlocked(
            "active_stock_financial_metadata_count_mismatch: "
            f"expected={expected_rows}, rows={previous_row_count}, identities={previous_identity_count}"
        )
    active_row = {
        "data_domain": "stock",
        "data_type": "stock_financial",
        "scope_key": TRADE_DATE,
        "source_version": SOURCE_VERSION,
        "source_batch_id": BATCH_ID,
        "previous_source_version": previous_source_version,
        "activated_by": canonical_ids_for(TRADE_DATE)["activated_by"],
    }
    return json_safe(
        {
            "batch_id": BATCH_ID,
            "trade_date": TRADE_DATE,
            "source_version": SOURCE_VERSION,
            "previous_source_version": previous_source_version,
            "allowed_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
            "stock_financial_rows": rows,
            "quality_rows": quality_rows,
            "active_source_version_row": active_row,
            "row_counts": {"stock_financial_metrics_fact": len(rows), "total": len(rows)},
            "quality_summary": dry_run.get("quality"),
            "source_probe": snapshot.get("source_probe") or {},
            "rollback_sql_path": str(DEFAULT_PATHS["rollback_sql"]),
            "rollback_context": {
                "data_domain": "stock",
                "data_type": "stock_financial",
                "scope_key": TRADE_DATE,
                "source_batch_id": BATCH_ID,
                "source_version": SOURCE_VERSION,
                "previous_source_version": previous_source_version,
                "previous_source_batch_id": previous_source_batch_id,
                "previous_previous_source_version": active_metadata.get("previous_source_version"),
                "previous_row_count": previous_row_count,
                "previous_identity_count": previous_identity_count,
                "target_row_count": len(rows),
                "quality_row_count": len(quality_rows),
                "activated_by": f"rollback.{SOURCE_VERSION}",
            },
        }
    )


def load_active_source_metadata(*, dsn: str, source_trade_date: str) -> dict[str, Any]:
    source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    with psycopg.connect(
        dsn,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT data_domain, data_type, scope_key, source_version,
                       source_batch_id, previous_source_version
                FROM common_active_source_version
                WHERE data_domain='stock'
                  AND data_type='stock_financial'
                  AND scope_key=%s
                """,
                (source_trade_date,),
            )
            active = dict(cur.fetchone() or {})
            if not active:
                raise StockFinancialCanonicalBlocked("active_stock_financial_metadata_missing")
            cur.execute(
                """
                SELECT count(*)::bigint AS row_count,
                       count(DISTINCT stock_identity_key)::bigint AS identity_count
                FROM stock_financial_metrics_fact
                WHERE source_trade_date=%s
                  AND source_version=%s
                  AND source_batch_id=%s
                """,
                (
                    source_trade_date,
                    active.get("source_version"),
                    active.get("source_batch_id"),
                ),
            )
            counts = dict(cur.fetchone() or {})
    return json_safe({**active, **counts})


def _rollback_context(commit_plan: Mapping[str, Any]) -> dict[str, Any]:
    context = commit_plan.get("rollback_context")
    if not isinstance(context, Mapping):
        raise StockFinancialCanonicalBlocked("rollback_context_missing")
    trade_date = require_yyyymmdd(str(commit_plan.get("trade_date") or ""), "trade_date")
    canonical = canonical_ids_for(trade_date)
    expected = {
        "data_domain": "stock",
        "data_type": "stock_financial",
        "scope_key": trade_date,
        "source_batch_id": canonical["batch_id"],
        "source_version": canonical["source_version"],
        "previous_source_version": canonical["previous_source_version"],
        "activated_by": f"rollback.{canonical['source_version']}",
    }
    mismatched = [
        key for key, value in expected.items() if str(context.get(key) or "") != value
    ]
    if mismatched:
        raise StockFinancialCanonicalBlocked("rollback_context_mismatch: " + ",".join(mismatched))
    previous_source_batch_id = str(context.get("previous_source_batch_id") or "").strip()
    if not previous_source_batch_id:
        raise StockFinancialCanonicalBlocked("rollback_previous_source_batch_id_missing")
    target_row_count = int(context.get("target_row_count") or 0)
    previous_row_count = int(context.get("previous_row_count") or 0)
    previous_identity_count = int(context.get("previous_identity_count") or 0)
    quality_row_count = int(context.get("quality_row_count") or 0)
    if target_row_count <= 0:
        raise StockFinancialCanonicalBlocked("rollback_target_row_count_invalid")
    if previous_row_count != target_row_count or previous_identity_count != target_row_count:
        raise StockFinancialCanonicalBlocked(
            "rollback_previous_count_mismatch: "
            f"target={target_row_count}, rows={previous_row_count}, identities={previous_identity_count}"
        )
    if quality_row_count <= 0:
        raise StockFinancialCanonicalBlocked("rollback_quality_row_count_invalid")
    return {
        **dict(context),
        "trade_date": trade_date,
        "previous_source_batch_id": previous_source_batch_id,
        "target_row_count": target_row_count,
        "previous_row_count": previous_row_count,
        "previous_identity_count": previous_identity_count,
        "quality_row_count": quality_row_count,
    }


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def render_rollback_sql(commit_plan: Mapping[str, Any]) -> str:
    context = _rollback_context(commit_plan)
    trade_date = _sql_literal(context["trade_date"])
    batch_id = _sql_literal(context["source_batch_id"])
    source_version = _sql_literal(context["source_version"])
    previous_version = _sql_literal(context["previous_source_version"])
    previous_batch_id = _sql_literal(context["previous_source_batch_id"])
    previous_previous_version = _sql_literal(context.get("previous_previous_source_version"))
    activated_by = _sql_literal(context["activated_by"])
    target_row_count = context["target_row_count"]
    previous_row_count = context["previous_row_count"]
    previous_identity_count = context["previous_identity_count"]
    quality_row_count = context["quality_row_count"]
    return f"""-- Rollback for stock_financial canonical metrics {context['trade_date']} v2 execute.
-- Generated and verified before database commit. Execute only under a separate authorized rollback gate.
-- Scope: only {context['source_batch_id']} / {context['source_version']}.

BEGIN;

DO $$
DECLARE
  v_active_count bigint;
  v_target_row_count bigint;
  v_target_identity_count bigint;
  v_previous_row_count bigint;
  v_previous_identity_count bigint;
  v_quality_row_count bigint;
  v_batch_count bigint;
  v_affected_count bigint;
BEGIN
  SELECT count(*) INTO v_active_count
  FROM common_active_source_version
  WHERE data_domain = 'stock'
    AND data_type = 'stock_financial'
    AND scope_key = {trade_date}
    AND source_version = {source_version}
    AND source_batch_id = {batch_id};

  SELECT count(*), count(DISTINCT stock_identity_key)
  INTO v_target_row_count, v_target_identity_count
  FROM stock_financial_metrics_fact
  WHERE source_trade_date = {trade_date}
    AND source_batch_id = {batch_id}
    AND source_version = {source_version};

  SELECT count(*), count(DISTINCT stock_identity_key)
  INTO v_previous_row_count, v_previous_identity_count
  FROM stock_financial_metrics_fact
  WHERE source_trade_date = {trade_date}
    AND source_batch_id = {previous_batch_id}
    AND source_version = {previous_version};

  SELECT count(*) INTO v_quality_row_count
  FROM common_quality_gate_result
  WHERE source_batch_id = {batch_id}
    AND source_version = {source_version}
    AND data_domain = 'stock'
    AND data_type = 'stock_financial_canonical_metrics';

  SELECT count(*) INTO v_batch_count
  FROM common_ingest_batch
  WHERE batch_id = {batch_id}
    AND trade_date = {trade_date}
    AND source_version = {source_version}
    AND data_domain = 'stock'
    AND data_type = 'stock_financial_canonical_metrics'
    AND status = 'passed'
    AND row_count = {target_row_count};

  IF v_active_count <> 1
     OR v_target_row_count <> {target_row_count}
     OR v_target_identity_count <> {target_row_count}
     OR v_previous_row_count <> {previous_row_count}
     OR v_previous_identity_count <> {previous_identity_count}
     OR v_quality_row_count <> {quality_row_count}
     OR v_batch_count <> 1 THEN
    RAISE EXCEPTION
      'Refusing stock_financial canonical rollback: active %, target rows %, target identities %, previous rows %, previous identities %, quality %, batch %',
      v_active_count, v_target_row_count, v_target_identity_count,
      v_previous_row_count, v_previous_identity_count, v_quality_row_count, v_batch_count;
  END IF;

  DELETE FROM stock_financial_metrics_fact
  WHERE source_trade_date = {trade_date}
    AND source_batch_id = {batch_id}
    AND source_version = {source_version};
  GET DIAGNOSTICS v_affected_count = ROW_COUNT;
  IF v_affected_count <> {target_row_count} THEN
    RAISE EXCEPTION 'Rollback fact delete count mismatch: %', v_affected_count;
  END IF;

  DELETE FROM common_quality_gate_result
  WHERE source_batch_id = {batch_id}
    AND source_version = {source_version}
    AND data_domain = 'stock'
    AND data_type = 'stock_financial_canonical_metrics';
  GET DIAGNOSTICS v_affected_count = ROW_COUNT;
  IF v_affected_count <> {quality_row_count} THEN
    RAISE EXCEPTION 'Rollback quality delete count mismatch: %', v_affected_count;
  END IF;

  UPDATE common_active_source_version
  SET source_version = {previous_version},
      previous_source_version = {previous_previous_version},
      source_batch_id = {previous_batch_id},
      activated_at = now(),
      activated_by = {activated_by}
  WHERE data_domain = 'stock'
    AND data_type = 'stock_financial'
    AND scope_key = {trade_date}
    AND source_version = {source_version}
    AND source_batch_id = {batch_id};
  GET DIAGNOSTICS v_affected_count = ROW_COUNT;
  IF v_affected_count <> 1 THEN
    RAISE EXCEPTION 'Rollback active update count mismatch: %', v_affected_count;
  END IF;

  DELETE FROM common_ingest_batch
  WHERE batch_id = {batch_id}
    AND trade_date = {trade_date}
    AND source_version = {source_version}
    AND data_domain = 'stock'
    AND data_type = 'stock_financial_canonical_metrics'
    AND status = 'passed'
    AND row_count = {target_row_count};
  GET DIAGNOSTICS v_affected_count = ROW_COUNT;
  IF v_affected_count <> 1 THEN
    RAISE EXCEPTION 'Rollback batch delete count mismatch: %', v_affected_count;
  END IF;
END $$;

COMMIT;
"""


def validate_rollback_sql_text(commit_plan: Mapping[str, Any], sql_text: str) -> None:
    expected = render_rollback_sql(commit_plan)
    if sql_text != expected:
        raise StockFinancialCanonicalBlocked("rollback_sql_content_mismatch")


def verify_persisted_rollback_sql(
    commit_plan: Mapping[str, Any],
    *,
    reused: bool,
) -> dict[str, Any]:
    raw_path = str(commit_plan.get("rollback_sql_path") or "").strip()
    if not raw_path:
        raise StockFinancialCanonicalBlocked("rollback_sql_path_missing")
    path = Path(raw_path)
    if path.is_symlink():
        raise StockFinancialCanonicalBlocked(f"rollback_sql_symlink_forbidden: {path}")
    if not path.is_file():
        raise StockFinancialCanonicalBlocked(f"rollback_sql_missing: {path}")
    try:
        sql_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StockFinancialCanonicalBlocked(
            f"rollback_sql_read_failed: {type(exc).__name__}: {exc}"
        ) from exc
    validate_rollback_sql_text(commit_plan, sql_text)
    encoded = sql_text.encode("utf-8")
    return {
        "path": str(path),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "size_bytes": len(encoded),
        "reused": reused,
        "verified": True,
    }


def persist_rollback_sql_atomic(commit_plan: Mapping[str, Any]) -> dict[str, Any]:
    raw_path = str(commit_plan.get("rollback_sql_path") or "").strip()
    if not raw_path:
        raise StockFinancialCanonicalBlocked("rollback_sql_path_missing")
    path = Path(raw_path)
    expected = render_rollback_sql(commit_plan)
    if path.exists():
        if path.is_symlink():
            raise StockFinancialCanonicalBlocked(f"rollback_sql_symlink_forbidden: {path}")
        if not path.is_file():
            raise StockFinancialCanonicalBlocked(f"rollback_sql_not_regular_file: {path}")
        try:
            actual = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise StockFinancialCanonicalBlocked(
                f"rollback_sql_read_failed: {type(exc).__name__}: {exc}"
            ) from exc
        if actual != expected:
            raise StockFinancialCanonicalBlocked(f"rollback_sql_content_conflict: {path}")
        return verify_persisted_rollback_sql(commit_plan, reused=True)

    temp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temp_path = Path(temp_name)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(expected)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp_path, path)
        except FileExistsError:
            if path.is_symlink():
                raise StockFinancialCanonicalBlocked(f"rollback_sql_symlink_forbidden: {path}")
            if not path.is_file():
                raise StockFinancialCanonicalBlocked(f"rollback_sql_not_regular_file: {path}")
            actual = path.read_text(encoding="utf-8")
            if actual != expected:
                raise StockFinancialCanonicalBlocked(f"rollback_sql_content_conflict: {path}")
            temp_path.unlink()
            temp_path = None
            return verify_persisted_rollback_sql(commit_plan, reused=True)
        temp_path.unlink()
        temp_path = None
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except StockFinancialCanonicalBlocked:
        raise
    except OSError as exc:
        raise StockFinancialCanonicalBlocked(
            f"rollback_sql_persistence_failed: {type(exc).__name__}: {exc}"
        ) from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
    return verify_persisted_rollback_sql(commit_plan, reused=False)


def validate_current_active_metadata_for_commit(cur: Any, commit_plan: Mapping[str, Any]) -> None:
    context = _rollback_context(commit_plan)
    cur.execute(
        """
        SELECT data_domain, data_type, scope_key, source_version,
               source_batch_id, previous_source_version
        FROM common_active_source_version
        WHERE data_domain='stock'
          AND data_type='stock_financial'
          AND scope_key=%s
        FOR UPDATE
        """,
        (context["scope_key"],),
    )
    row = cur.fetchone()
    if not row:
        raise StockFinancialCanonicalBlocked("active_stock_financial_metadata_missing_at_commit")
    if isinstance(row, Mapping):
        actual = dict(row)
    else:
        actual = dict(
            zip(
                (
                    "data_domain",
                    "data_type",
                    "scope_key",
                    "source_version",
                    "source_batch_id",
                    "previous_source_version",
                ),
                row,
            )
        )
    expected = {
        "data_domain": context["data_domain"],
        "data_type": context["data_type"],
        "scope_key": context["scope_key"],
        "source_version": context["previous_source_version"],
        "source_batch_id": context["previous_source_batch_id"],
        "previous_source_version": context.get("previous_previous_source_version"),
    }
    mismatched = [key for key, value in expected.items() if actual.get(key) != value]
    if mismatched:
        raise StockFinancialCanonicalBlocked(
            "active_stock_financial_metadata_drift_at_commit: " + ",".join(mismatched)
        )


def validate_previous_fact_metadata_for_commit(cur: Any, commit_plan: Mapping[str, Any]) -> None:
    context = _rollback_context(commit_plan)
    cur.execute(
        """
        SELECT count(*)::bigint AS row_count,
               count(DISTINCT stock_identity_key)::bigint AS identity_count
        FROM stock_financial_metrics_fact
        WHERE source_trade_date=%s
          AND source_version=%s
          AND source_batch_id=%s
        """,
        (
            context["scope_key"],
            context["previous_source_version"],
            context["previous_source_batch_id"],
        ),
    )
    row = cur.fetchone()
    if isinstance(row, Mapping):
        actual_row_count = int(row.get("row_count") or 0)
        actual_identity_count = int(row.get("identity_count") or 0)
    elif row:
        actual_row_count = int(row[0] or 0)
        actual_identity_count = int(row[1] or 0)
    else:
        actual_row_count = 0
        actual_identity_count = 0
    if (
        actual_row_count != context["previous_row_count"]
        or actual_identity_count != context["previous_identity_count"]
    ):
        raise StockFinancialCanonicalBlocked(
            "active_stock_financial_fact_drift_at_commit: "
            f"expected_rows={context['previous_row_count']}, actual_rows={actual_row_count}, "
            f"expected_identities={context['previous_identity_count']}, "
            f"actual_identities={actual_identity_count}"
        )


def execute_commit_transaction(
    conn: Any,
    *,
    commit_plan: Mapping[str, Any],
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    validate_execute_request(
        execute_requested=execute_requested,
        user_confirmed=user_confirmed,
        postgres_commit_enabled=postgres_commit_enabled,
    )
    unexpected = sorted(set(commit_plan.get("allowed_tables") or []) - set(ALLOWED_FUTURE_WRITE_TABLES))
    if unexpected:
        raise StockFinancialCanonicalBlocked(f"unexpected write tables: {unexpected}")
    try:
        cur = conn.cursor()
        validate_current_active_metadata_for_commit(cur, commit_plan)
        validate_previous_fact_metadata_for_commit(cur, commit_plan)
        rollback_artifact = persist_rollback_sql_atomic(commit_plan)
        insert_ingest_batch(cur, commit_plan)
        insert_stock_financial_rows(cur, list(commit_plan.get("stock_financial_rows") or []))
        insert_quality_rows(cur, list(commit_plan.get("quality_rows") or []))
        upsert_active_source_version(cur, dict(commit_plan.get("active_source_version_row") or {}))
        update_ingest_batch_passed(cur)
        rollback_artifact = verify_persisted_rollback_sql(
            commit_plan,
            reused=bool(rollback_artifact.get("reused")),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return json_safe(
        {
            "committed": True,
            "batch_id": BATCH_ID,
            "source_version": SOURCE_VERSION,
            "written_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
            "row_counts": commit_plan.get("row_counts") or {},
            "rollback_safe": bool(rollback_artifact.get("verified")),
            "rollback_sql_path": rollback_artifact.get("path"),
            "rollback_artifact": rollback_artifact,
        }
    )


def insert_ingest_batch(cur: Any, commit_plan: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO common_ingest_batch (
          batch_id, trade_date, data_domain, data_type, source, source_version,
          source_path, source_params, raw_hash, row_count, error_count,
          quality_gate_summary, error_summary, rollback_strategy, status, started_at
        )
        VALUES (
          %(batch_id)s, %(trade_date)s, 'stock', 'stock_financial_canonical_metrics',
          %(source)s, %(source_version)s,
          NULL, %(source_params)s, NULL, %(row_count)s, 0,
          %(quality_gate_summary)s, NULL, %(rollback_strategy)s, 'running', now()
        )
        """,
        {
            "batch_id": BATCH_ID,
            "trade_date": TRADE_DATE,
            "source": f"n1.stock_financial_canonical.{TRADE_DATE}.v1",
            "source_version": SOURCE_VERSION,
            "source_params": Jsonb(json_safe({"source_probe": commit_plan.get("source_probe") or {}})),
            "row_count": int((commit_plan.get("row_counts") or {}).get("stock_financial_metrics_fact") or 0),
            "quality_gate_summary": Jsonb(json_safe(commit_plan.get("quality_summary") or {})),
            "rollback_strategy": str(DEFAULT_PATHS["rollback_sql"]),
        },
    )


def insert_stock_financial_rows(cur: Any, rows: list[Mapping[str, Any]]) -> None:
    if not rows:
        raise StockFinancialCanonicalBlocked("stock_financial_commit_plan_has_no_fact_rows")
    cur.executemany(
        """
        INSERT INTO stock_financial_metrics_fact (
          stock_identity_key, asof_date, source_trade_date, announcement_date, report_period,
          ts_code, code, exchange, roe, revenue_yoy, profit_yoy, total_revenue,
          net_profit, net_assets, eps, bps, pe_core, total_mv, circ_mv,
          score, warning, quality_status, source, source_batch_id, source_version, raw_payload,
          cash_realization_rate, revenue_yoy_pct, core_profit_yoy_pct, report_core_revenue,
          report_core_profit, core_profit_ttm, core_gt_revenue_yoy, revenue_growth_streak_q,
          core_growth_streak_q, core_gt_revenue_streak_q, forecast_type, forecast_score,
          score_breakdown_json, financial_warning_json, financial_metric_version
        )
        VALUES (
          %(stock_identity_key)s, %(asof_date)s, %(source_trade_date)s, %(announcement_date)s, %(report_period)s,
          %(ts_code)s, %(code)s, %(exchange)s, %(roe)s, %(revenue_yoy)s, %(profit_yoy)s, %(total_revenue)s,
          %(net_profit)s, %(net_assets)s, %(eps)s, %(bps)s, %(pe_core)s, %(total_mv)s, %(circ_mv)s,
          %(score)s, %(warning)s, %(quality_status)s, %(source)s, %(source_batch_id)s, %(source_version)s, %(raw_payload)s,
          %(cash_realization_rate)s, %(revenue_yoy_pct)s, %(core_profit_yoy_pct)s, %(report_core_revenue)s,
          %(report_core_profit)s, %(core_profit_ttm)s, %(core_gt_revenue_yoy)s, %(revenue_growth_streak_q)s,
          %(core_growth_streak_q)s, %(core_gt_revenue_streak_q)s, %(forecast_type)s, %(forecast_score)s,
          %(score_breakdown_json)s, %(financial_warning_json)s, %(financial_metric_version)s
        )
        """,
        [stock_financial_jsonb_row(row) for row in rows],
    )


def stock_financial_jsonb_row(row: Mapping[str, Any]) -> dict[str, Any]:
    converted = dict(row)
    for key in ("raw_payload", "score_breakdown_json", "financial_warning_json"):
        converted[key] = Jsonb(strict_json_payload(converted.get(key) or {}, key))
    return converted


def insert_quality_rows(cur: Any, rows: list[Mapping[str, Any]]) -> None:
    cur.executemany(
        """
        INSERT INTO common_quality_gate_result (
          source_batch_id, source_version, data_domain, data_type, gate_name,
          severity, status, expected_value, actual_value, details
        )
        VALUES (
          %(source_batch_id)s, %(source_version)s, %(data_domain)s, %(data_type)s,
          %(gate_name)s, %(severity)s, %(status)s, %(expected_value)s, %(actual_value)s, %(details)s
        )
        """,
        [{**dict(row), "details": Jsonb(json_safe(row.get("details") or {}))} for row in rows],
    )


def upsert_active_source_version(cur: Any, row: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO common_active_source_version (
          data_domain, data_type, scope_key, source_version, source_batch_id,
          previous_source_version, activated_at, activated_by
        )
        VALUES (
          %(data_domain)s, %(data_type)s, %(scope_key)s, %(source_version)s, %(source_batch_id)s,
          %(previous_source_version)s, now(), %(activated_by)s
        )
        ON CONFLICT (data_domain, data_type, scope_key)
        DO UPDATE SET
          previous_source_version = common_active_source_version.source_version,
          source_version = EXCLUDED.source_version,
          source_batch_id = EXCLUDED.source_batch_id,
          activated_at = now(),
          activated_by = EXCLUDED.activated_by
        """,
        dict(row),
    )


def update_ingest_batch_passed(cur: Any) -> None:
    cur.execute(
        """
        UPDATE common_ingest_batch
        SET status = 'passed',
            finished_at = now()
        WHERE batch_id = %s
        """,
        (BATCH_ID,),
    )


def write_artifacts(dry_run: Mapping[str, Any], contract: Mapping[str, Any], preflight: Mapping[str, Any]) -> None:
    write_json(DEFAULT_PATHS["dry_run_json"], dry_run)
    write_markdown(DEFAULT_PATHS["dry_run_md"], dry_run, "N1 Stock Financial Canonical Metrics Dry-Run Report")
    write_json(DEFAULT_PATHS["contract_json"], contract)
    write_markdown(DEFAULT_PATHS["contract_md"], contract, "N1 Stock Financial Canonical Metrics Execute Contract")
    write_json(DEFAULT_PATHS["preflight_json"], preflight)
    write_markdown(DEFAULT_PATHS["preflight_md"], preflight, "N1 Stock Financial Canonical Metrics Execute Preflight")


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: Path, payload: Mapping[str, Any], title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "result": payload.get("result"),
        "source_trade_date": payload.get("source_trade_date"),
        "source_batch_id": payload.get("source_batch_id"),
        "source_version": payload.get("source_version"),
        "expected_rows": payload.get("expected_rows"),
        "row_counts": payload.get("row_counts"),
        "quality": payload.get("quality"),
        "blockers": payload.get("blockers"),
        "side_effects": payload.get("side_effects"),
    }
    path.write_text(f"# {title}\n\n```json\n{json.dumps(json_safe(summary), ensure_ascii=False, indent=2)}\n```\n", encoding="utf-8")


def default_side_effects() -> dict[str, bool]:
    return {
        "writes_performed": False,
        "writes_postgres": False,
        "writes_stock_financial_metrics_fact": False,
        "updates_active_source_version": False,
        "writes_condition_tables": False,
        "writes_parquet": False,
        "writes_outbox": False,
        "writes_inbox_or_checkpoint": False,
        "enters_n2_n3_n4_n5_n6": False,
        "worker_started": False,
        "old_system_touched": False,
        "real_trading": False,
    }


def quality_item(name: str, severity: str, status: str, expected: str, actual: str, details: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "gate_name": name,
        "severity": severity,
        "status": status,
        "expected_value": expected,
        "actual_value": actual,
        "details": dict(details),
    }


def summarize_quality(items: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"P0": 0, "P1": 0, "P2": 0}
    for item in items:
        if item.get("status") in {"failed", "warning"}:
            severity = str(item.get("severity") or "")
            if severity in counts:
                counts[severity] += 1
    return counts


def source_type(row: Mapping[str, Any]) -> str:
    value = str(row.get("source_type") or row.get("source") or SOURCE_TDX).lower()
    if "tushare" in value:
        return SOURCE_TUSHARE_FALLBACK
    return SOURCE_TDX


def source_rank(row: Mapping[str, Any]) -> int:
    return 0 if source_type(row) == SOURCE_TDX else 1


def first_decimal(row: Mapping[str, Any], *fields: str) -> Decimal | None:
    for field in fields:
        if field in row and row.get(field) not in (None, ""):
            value = decimal_or_none(row.get(field))
            if value is not None:
                return value
    return None


def decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    return parsed


def sum_decimal(values: Iterable[Decimal | None]) -> Decimal:
    total = Decimal("0")
    for value in values:
        if value is not None:
            total += value
    return total


def safe_divide(numerator: Any, denominator: Any) -> Decimal | None:
    n = decimal_or_none(numerator)
    d = decimal_or_none(denominator)
    if n is None or d in (None, Decimal("0")):
        return None
    return quantize_decimal(n / d)


def quantize_decimal(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_UP).normalize()


def optional_text(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip()


def optional_date_text(value: Any) -> str | None:
    text = optional_text(value)
    if not text:
        return None
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y%m%d")
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        text = text[:10].replace("-", "")
    return require_yyyymmdd(text[:8], "date")


def parse_identity(identity_key: str) -> tuple[str, str]:
    _, exchange, code = identity_key.split(":", 2)
    return exchange, code


def same_quarter_prior_year(report_period: str) -> str:
    return f"{int(report_period[:4]) - 1}{report_period[4:]}"


def previous_quarter_period(report_period: str) -> str | None:
    if len(report_period) != 8 or not report_period.isdigit():
        return None
    year = int(report_period[:4])
    suffix = report_period[4:]
    return {
        "0331": f"{year - 1}1231",
        "0630": f"{year}0331",
        "0930": f"{year}0630",
        "1231": f"{year}0930",
    }.get(suffix)


def contiguous_quarter_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    limit: int,
) -> list[Mapping[str, Any]]:
    contiguous: list[Mapping[str, Any]] = []
    expected_period: str | None = None
    for row in rows:
        report_period = str(row.get("report_period") or "")
        if expected_period is not None and report_period != expected_period:
            break
        contiguous.append(row)
        if len(contiguous) >= limit:
            break
        expected_period = previous_quarter_period(report_period)
        if expected_period is None:
            break
    return contiguous


def calculate_yoy(latest: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], field: str) -> Decimal | None:
    latest_value = decimal_or_none(latest.get(field))
    if latest_value is None:
        return None
    prior_period = same_quarter_prior_year(str(latest.get("report_period") or ""))
    prior = next((row for row in rows if str(row.get("report_period") or "") == prior_period), None)
    prior_value = decimal_or_none((prior or {}).get(field))
    if prior_value in (None, Decimal("0")):
        return None
    return quantize_decimal((latest_value - prior_value) * Decimal("100") / prior_value)


def streak(rows: Sequence[Mapping[str, Any]], field: str, *, positive: bool) -> int:
    count = 0
    for row in rows:
        value = first_decimal(row, field)
        if value is None:
            value = calculate_yoy(row, rows, "report_core_revenue" if field == "revenue_yoy_pct" else "report_core_profit")
        if value is not None and ((value > 0) if positive else bool(value)):
            count += 1
        else:
            break
    return count


def affair_yoy_streak(rows: Sequence[Mapping[str, Any]], field: str) -> int:
    count = 0
    expected_period: str | None = None
    for row in rows:
        report_period = str(row.get("report_period") or "")
        if expected_period is not None and report_period != expected_period:
            break
        value = calculate_yoy(row, rows, field)
        if value is None or value <= 0:
            break
        count += 1
        expected_period = previous_quarter_period(report_period)
    return count


def affair_core_gt_streak(rows: Sequence[Mapping[str, Any]]) -> int:
    count = 0
    expected_period: str | None = None
    for row in rows:
        report_period = str(row.get("report_period") or "")
        if expected_period is not None and report_period != expected_period:
            break
        revenue_yoy = calculate_yoy(row, rows, "report_core_revenue")
        core_yoy = calculate_yoy(row, rows, "report_core_profit")
        if revenue_yoy is None or core_yoy is None or core_yoy <= revenue_yoy:
            break
        count += 1
        expected_period = previous_quarter_period(report_period)
    return count


def core_gt_streak(rows: Sequence[Mapping[str, Any]]) -> int:
    count = 0
    for row in rows:
        revenue = first_decimal(row, "revenue_yoy_pct")
        core = first_decimal(row, "core_profit_yoy_pct")
        if revenue is not None and core is not None and core > revenue:
            count += 1
        else:
            break
    return count


def forecast_score_for(forecast_type: str | None) -> Decimal | None:
    if not forecast_type:
        return None
    if forecast_type in {"预增", "扭亏"}:
        return Decimal("3")
    if forecast_type == "略增":
        return Decimal("2")
    if forecast_type == "续盈":
        return Decimal("1.5")
    if forecast_type == "略减":
        return Decimal("0.5")
    if forecast_type in {"预减", "首亏", "续亏"}:
        return Decimal("0")
    return Decimal("0")


def score_breakdown(
    *,
    report_core_profit: Decimal | None,
    cash_realization_rate: Decimal | None,
    pe_core: Decimal | None,
    revenue_yoy_pct: Decimal | None,
    core_profit_yoy_pct: Decimal | None,
    core_gt_revenue_yoy: bool | None,
    revenue_growth_streak_q: int | None,
    core_growth_streak_q: int | None,
    core_gt_revenue_streak_q: int | None,
    forecast_score: Decimal | None,
) -> dict[str, Decimal]:
    return {
        "positive_core_profit": Decimal("10") if report_core_profit is not None and report_core_profit > 0 else Decimal("0"),
        "cash_realization_rate": min(Decimal("15"), max(Decimal("0"), (cash_realization_rate or Decimal("0")) * Decimal("15"))),
        "pe_core": pe_score(pe_core),
        "revenue_yoy_pct": min(Decimal("10"), max(Decimal("0"), (revenue_yoy_pct or Decimal("0")) / Decimal("5"))),
        "core_profit_yoy_pct": min(Decimal("15"), max(Decimal("0"), (core_profit_yoy_pct or Decimal("0")) / Decimal("5"))),
        "core_gt_revenue_yoy": Decimal("10") if core_gt_revenue_yoy else Decimal("0"),
        "revenue_growth_streak_q": min(Decimal("5"), Decimal(str(revenue_growth_streak_q or 0))),
        "core_growth_streak_q": min(Decimal("8"), Decimal(str((core_growth_streak_q or 0) * 2))),
        "core_gt_revenue_streak_q": min(Decimal("4"), Decimal(str(core_gt_revenue_streak_q or 0))),
        "forecast_score": forecast_score or Decimal("0"),
    }


def pe_score(pe_core: Decimal | None) -> Decimal:
    if pe_core is None or pe_core <= 0:
        return Decimal("0")
    if pe_core <= 20:
        return Decimal("20")
    if pe_core <= 40:
        return Decimal("10")
    if pe_core <= 60:
        return Decimal("5")
    return Decimal("0")


def score_distribution(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    buckets = {"0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0, "missing": 0}
    for row in rows:
        score = decimal_or_none(row.get("score"))
        if score is None:
            buckets["missing"] += 1
        elif score < 20:
            buckets["0-20"] += 1
        elif score < 40:
            buckets["20-40"] += 1
        elif score < 60:
            buckets["40-60"] += 1
        elif score < 80:
            buckets["60-80"] += 1
        else:
            buckets["80-100"] += 1
    return {key: value for key, value in buckets.items() if value}


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value) if value.is_finite() else None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return value


def strict_json_payload(value: Any, payload_name: str) -> Any:
    payload = json_safe(value)
    try:
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise StockFinancialCanonicalBlocked(f"{payload_name}_not_json_serializable: {exc}") from exc
    return payload
