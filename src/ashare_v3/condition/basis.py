"""Read-only condition_basis dry-run builder."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping

import psycopg
from psycopg.rows import dict_row

from ashare_v3.condition.context_enrichment import attach_context_enrichment_to_row
from ashare_v3.ingestion.common import require_yyyymmdd


REQUIRED_ACTIVE_DATA_TYPES = (
    "stock_daily",
    "stock_daily_basic",
    "stock_financial",
    "index_daily",
    "index_membership",
    "board_daily",
    "board_membership",
)
PERIODS = ("Y", "Q", "M", "W", "D")
STANDARD_SIGNAL_TYPES = ("BUY", "BUY:FULL", "SELL", "SELL:FULL", "BUY_HINT", "SELL_HINT")
STOCK_SCOPE_MIN_TOTAL_MV_WAN = Decimal("1000000")
DEFAULT_INDEX_POOL_IDENTITIES = (
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
PENDING_BASIS_REASON = (
    "N2-B dry-run freezes source facts and schema-aligned placeholders only; "
    "period aggregation, static targets, FULL/Hint necessary conditions, and condition_pool writes remain pending."
)
COMPUTED_BASIS_REASON = (
    "N2-R dry-run computed Y/Q/M/W/D period grades using previous-period entity bounds and avg_amount baselines, ordinary/FULL/Hint "
    "necessary conditions, static targets, anchors, up_sell_reference_period, down_buy_reference_period, legacy clear alias, "
    "and period_trigger_baseline_json from read-only daily facts; "
    "monitor targets remain pending."
)
UP_GRADES = frozenset({"volume_up", "low_volume_up"})
DOWN_GRADES = frozenset({"volume_down", "low_volume_down"})
BUY_ALLOWED_GRADES = frozenset({"low_volume_up", "volume_down", "low_volume_down", "flat"})
SELL_ALLOWED_GRADES = frozenset({"volume_up", "low_volume_up", "volume_down", "flat"})
RISK_GRADES = frozenset({"flat", "low_volume_down", "volume_down"})
OPPORTUNITY_GRADES = frozenset({"flat", "low_volume_up", "volume_up"})
PERIOD_FIELD_SUFFIX = {"Y": "y", "Q": "q", "M": "m", "W": "w", "D": "d"}
LEVEL_SCORE_FIELDS = ("level_up_score", "level_down_score")
LEVEL_UP_TRANSITION_RANK = {
    "low_volume_down": 0,
    "volume_down": 1,
    "flat": 2,
    "low_volume_up": 3,
    "volume_up": 4,
}
LEVEL_DOWN_TRANSITION_RANK = {
    "volume_up": 0,
    "low_volume_up": 1,
    "flat": 2,
    "volume_down": 3,
    "low_volume_down": 4,
}
STATIC_ANCHOR_PERIODS = ("Y", "Q", "M", "W")
LOWER_PERIOD = {"Y": "Q", "Q": "M", "M": "W", "W": "D"}
TRANSITION_WINDOWS = {"Y": 66, "Q": 22, "M": 5, "W": 1}
PERIOD_TRIGGER_BASELINE_VERSION = "N2-R4-period-trigger-baseline-v1"
PERIOD_ESCALATION_CONTEXT_VERSION = "N2-period-escalation-context-v1"
PERIOD_ESCALATION_CONTEXT_GENERATION_MODE = "N2-period-escalation-daily-incremental-v1"
CONDITION_PROJECTION_CONTEXT_VERSION = "N2-condition-projection-context-v1"
CONDITION_PROJECTION_COMMON_FIELDS = (
    "name",
    "close",
    "up_reference_period",
    "buy_target_price",
    "buy_expected_return_pct",
    "down_reference_period",
    "sell_target_price",
    "sell_expected_return_pct",
    "clear_sell_ref_period",
    "up_secondary_target_price",
    "up_secondary_expected_return_pct",
)
CONDITION_PROJECTION_STOCK_FIELDS = CONDITION_PROJECTION_COMMON_FIELDS + ("score", "pe_core")
CONDITION_PROJECTION_NUMERIC_FIELDS = frozenset(
    {
        "close",
        "buy_target_price",
        "buy_expected_return_pct",
        "sell_target_price",
        "sell_expected_return_pct",
        "up_secondary_target_price",
        "up_secondary_expected_return_pct",
        "score",
        "pe_core",
    }
)
CONDITION_PROJECTION_PERIOD_FIELDS = frozenset(
    {"up_reference_period", "down_reference_period", "clear_sell_ref_period"}
)
PERIOD_ESCALATION_REQUIREMENTS = {
    "W": {"prerequisite_period": "D", "window_kind": "week"},
    "M": {"prerequisite_period": "W", "window_kind": "month"},
    "Q": {"prerequisite_period": "M", "window_kind": "quarter"},
    "Y": {"prerequisite_period": "Q", "window_kind": "year"},
}
PERIOD_ESCALATION_DIRECTION_TRANSITIONS = {
    "buy": "volume_up",
    "sell": "low_volume_down",
}
PERIOD_ESCALATION_BASIS_TABLES = {
    "stock": ("stock_condition_basis", "stock_identity_key", "stock_condition_basis_id"),
    "index": ("index_condition_basis", "index_identity_key", "index_condition_basis_id"),
    "board": ("board_condition_basis", "board_identity_key", "board_condition_basis_id"),
}
PERIOD_TRIGGER_BASELINE_REQUIRED_KEYS = (
    "current_open_seed",
    "current_close_seed",
    "current_amount_seed",
    "current_trade_days_seed",
    "previous_open",
    "previous_close",
    "previous_entity_high",
    "previous_entity_low",
    "previous_amount",
    "previous_avg_amount",
    "amount_metric",
    "current_window_start",
    "current_window_end",
    "previous_window_start",
    "previous_window_end",
)
_BASIS_DRY_RUN_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
SYMMETRY_TARGET_BASE_PRICE_POLICY = "MIN_CLOSE_AFTER_LAST_LOWER_UP_SEGMENT_PLUS_TRIGGER_OPEN"
SYMMETRY_TARGET_TRACE_VERSION = "N2-symmetry-target-v1"
DOWN_SECONDARY_TARGET_PRICE_NON_POSITIVE_REASON = "down_secondary_target_price_non_positive"
DOWN_SECONDARY_TARGET_PRICE_INVALID_REASON = "down_secondary_target_price_invalid"
SYMMETRY_TARGET_AMPLITUDE_PRICE_POLICY = "OFFICIAL_HIGH_LOW"
SYMMETRY_TARGET_ADJUSTMENT_POLICY = "ROW_ADJ_FACTOR_TO_CURRENT_ADJ_FACTOR"
SYMMETRY_TARGET_PRICE_QUANT = Decimal("0.01")
SYMMETRY_TARGET_PERIODS = frozenset({"Y", "Q", "M", "W"})
SYMMETRY_SECONDARY_TARGET_FIELDS = (
    "up_secondary_anchor",
    "up_secondary_reference_period",
    "up_secondary_trend_start_date",
    "up_secondary_trend_end_date",
    "up_secondary_amplitude",
    "up_secondary_base_price",
    "up_secondary_target_price",
    "up_secondary_expected_return_pct",
    "down_secondary_anchor",
    "down_secondary_reference_period",
    "down_secondary_trend_start_date",
    "down_secondary_trend_end_date",
    "down_secondary_amplitude",
    "down_secondary_base_price",
    "down_secondary_target_price",
    "down_secondary_expected_return_pct",
)
SYMMETRY_TARGET_FIELDS = (
    "symmetry_anchor",
    "secondary_symmetry_anchor",
    "amplitude_source_period",
    "a_segment_start_date",
    "a_segment_end_date",
    "a_segment_high",
    "a_segment_low",
    "a_segment_amplitude",
    "base_price_policy",
    "base_price",
    "reference_target_price",
    "secondary_target_price",
    "target_price_trace_json",
) + SYMMETRY_SECONDARY_TARGET_FIELDS
STOCK_CANONICAL_FINANCIAL_FIELDS = (
    "cash_realization_rate",
    "revenue_yoy_pct",
    "core_profit_yoy_pct",
    "report_core_revenue",
    "report_core_profit",
    "core_profit_ttm",
    "core_gt_revenue_yoy",
    "revenue_growth_streak_q",
    "core_growth_streak_q",
    "core_gt_revenue_streak_q",
    "forecast_type",
    "forecast_score",
    "score_breakdown_json",
    "financial_warning_json",
    "financial_metric_version",
)
STOCK_FINANCIAL_COMPATIBILITY_FIELDS = (
    "pe_core",
    "score",
    "financial_quality_status",
)
STOCK_FINANCIAL_JSON_FIELDS = (
    "score_breakdown_json",
    "financial_warning_json",
)
STOCK_FINANCIAL_PASS_THROUGH_FIELDS = STOCK_CANONICAL_FINANCIAL_FIELDS + STOCK_FINANCIAL_COMPATIBILITY_FIELDS


@dataclass(frozen=True)
class DateContext:
    source_trade_date: str
    source_prev_trade_date: str
    for_trade_date: str
    prev_trade_date: str
    for_trade_calendar_row_exists: bool


def active_versions_from_ready_check(ready_check: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    versions: dict[str, dict[str, Any]] = {}
    for item in ready_check.get("checks", []):
        data_type = str(item.get("data_type") or "")
        active_source_version = str(item.get("active_source_version") or "")
        if data_type and active_source_version:
            versions[data_type] = dict(item)
    return versions


def infer_date_context(cur: psycopg.Cursor[dict[str, Any]], source_trade_date: str) -> DateContext:
    source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    cur.execute(
        """
        SELECT prev_trade_date, next_trade_date
        FROM common_trade_calendar
        WHERE trade_date = %s
          AND is_open = true
        """,
        (source_trade_date,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"source_trade_date is not an open trade date in common_trade_calendar: {source_trade_date}")

    source_prev_trade_date = require_yyyymmdd(str(row.get("prev_trade_date") or ""), "source_prev_trade_date")
    for_trade_date = str(row.get("next_trade_date") or "")
    if not for_trade_date:
        cur.execute(
            """
            SELECT trade_date
            FROM common_trade_calendar
            WHERE trade_date > %s
              AND is_open = true
            ORDER BY trade_date
            LIMIT 1
            """,
            (source_trade_date,),
        )
        next_row = cur.fetchone()
        if next_row is None:
            raise ValueError(f"cannot infer next open trade date after source_trade_date={source_trade_date}")
        for_trade_date = str(next_row["trade_date"])

    for_trade_date = require_yyyymmdd(for_trade_date, "for_trade_date")
    cur.execute(
        """
        SELECT prev_trade_date
        FROM common_trade_calendar
        WHERE trade_date = %s
          AND is_open = true
        """,
        (for_trade_date,),
    )
    for_row = cur.fetchone()
    if for_row is None:
        prev_trade_date = source_trade_date
        for_trade_calendar_row_exists = False
    else:
        prev_trade_date = str(for_row.get("prev_trade_date") or "")
        for_trade_calendar_row_exists = True
    prev_trade_date = require_yyyymmdd(prev_trade_date, "prev_trade_date")
    if prev_trade_date != source_trade_date:
        raise ValueError(
            "calendar mismatch: prev_trade_date(for_trade_date) must equal source_trade_date "
            f"({prev_trade_date} != {source_trade_date})"
        )
    return DateContext(
        source_trade_date=source_trade_date,
        source_prev_trade_date=source_prev_trade_date,
        for_trade_date=for_trade_date,
        prev_trade_date=prev_trade_date,
        for_trade_calendar_row_exists=for_trade_calendar_row_exists,
    )


def build_condition_basis_dry_run(
    *,
    dsn: str,
    source_trade_date: str,
    ready_check: Mapping[str, Any],
) -> dict[str, Any]:
    source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    active_versions = active_versions_from_ready_check(ready_check)
    missing_active = [data_type for data_type in REQUIRED_ACTIVE_DATA_TYPES if data_type not in active_versions]
    if missing_active:
        raise ValueError(f"ready check is missing active versions: {missing_active}")
    with psycopg.connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        date_context = infer_date_context(cur, source_trade_date)
        previous_context_run = fetch_period_escalation_previous_context_run(cur, date_context)
        incremental_epoch = period_escalation_incremental_epoch(previous_context_run)
        open_source_dates = fetch_period_escalation_window_trade_dates(cur, date_context)
        cache_key = (
            dsn,
            source_trade_date,
            tuple(
                (data_type, active_versions[data_type].get("active_source_version"), active_versions[data_type].get("source_batch_id"))
                for data_type in REQUIRED_ACTIVE_DATA_TYPES
            ),
            incremental_epoch,
            tuple(open_source_dates),
            bool(ready_check.get("passed")),
            ready_check.get("expected_condition_stock_universe"),
            ready_check.get("excluded_from_condition_universe"),
        )
        if cache_key in _BASIS_DRY_RUN_CACHE:
            return deepcopy(_BASIS_DRY_RUN_CACHE[cache_key])
        monitor_targets = fetch_monitor_target_status(cur, date_context.for_trade_date)
        stock_summary = fetch_stock_basis_preview(cur, date_context, active_versions)
        index_summary = fetch_index_basis_preview(cur, date_context, active_versions)
        board_summary = fetch_board_basis_preview(cur, date_context, active_versions)
        attach_period_escalation_contexts(
            cur,
            date_context,
            {
                "stock": stock_summary,
                "index": index_summary,
                "board": board_summary,
            },
            previous_context_run=previous_context_run,
            open_source_dates=open_source_dates,
        )
        membership_summary = fetch_membership_summary(cur, date_context, active_versions)

    stock_summary.update(stock_condition_universe_summary(ready_check))
    quality_items = build_quality_items(
        ready_check=ready_check,
        date_context=date_context,
        monitor_targets=monitor_targets,
        stock_summary=stock_summary,
        index_summary=index_summary,
        board_summary=board_summary,
    )
    severity_counts = count_quality_severities(quality_items)
    report = {
        "stage": "N2-B",
        "mode": "dry_run",
        "writes_performed": False,
        "condition_pool_written": False,
        "minute_kline_pulled": False,
        "run_id": f"condition_basis_{date_context.source_trade_date}_to_{date_context.for_trade_date}_dry_run",
        "source_trade_date": date_context.source_trade_date,
        "source_prev_trade_date": date_context.source_prev_trade_date,
        "for_trade_date": date_context.for_trade_date,
        "prev_trade_date": date_context.prev_trade_date,
        "for_trade_calendar_row_exists": date_context.for_trade_calendar_row_exists,
        "source_versions": {
            data_type: active_versions[data_type]["active_source_version"]
            for data_type in REQUIRED_ACTIVE_DATA_TYPES
        },
        "source_batches": {
            data_type: active_versions[data_type]["source_batch_id"]
            for data_type in REQUIRED_ACTIVE_DATA_TYPES
        },
        "source_ready_passed": bool(ready_check.get("passed")),
        "condition_source_gap_manifest": ready_check.get("condition_source_gap_manifest") or {},
        "stock_condition_universe": ready_check.get("stock_condition_universe") or {},
        "monitor_targets": monitor_targets,
        "basis_preview": {
            "stock": stock_summary,
            "index": index_summary,
            "board": board_summary,
        },
        "membership_summary": membership_summary,
        "runtime_scope_contract": {
            "daily_snapshot_required_default": True,
            "minute_required_default": False,
            "previous_day_minute_required_default": False,
            "previous_day_minute_date_when_required": date_context.prev_trade_date,
            "previous_day_minute_quality_required_when_required": True,
            "minute_kline_pulled": False,
        },
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "passed": severity_counts["P0"] == 0 and bool(ready_check.get("passed")),
    }
    _BASIS_DRY_RUN_CACHE[cache_key] = deepcopy(report)
    return report


def fetch_monitor_target_status(cur: psycopg.Cursor[dict[str, Any]], for_trade_date: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for domain, table in (
        ("stock", "stock_monitor_target"),
        ("index", "index_monitor_target"),
        ("board", "board_monitor_target"),
    ):
        cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
        exists = cur.fetchone()["to_regclass"] is not None
        count = 0
        if exists:
            date_column = resolve_table_date_column(cur, table)
            cur.execute(
                f"""
                SELECT count(*)::bigint
                FROM {table}
                WHERE {date_column} = %s
                  AND status = 'active'
                """,
                (for_trade_date,),
            )
            count = int(cur.fetchone()["count"])
        result[domain] = {
            "table_name": table,
            "exists": exists,
            "date_column": None if not exists else date_column,
            "active_count": count,
            "mode": "monitor_target" if exists and count > 0 else "fact_universe_fallback",
        }
    return result


def resolve_table_date_column(cur: psycopg.Cursor[dict[str, Any]], table_name: str) -> str:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name IN ('for_trade_date', 'trade_date')
        ORDER BY CASE column_name WHEN 'for_trade_date' THEN 0 ELSE 1 END
        LIMIT 1
        """,
        (table_name,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"{table_name} has no for_trade_date/trade_date column")
    return str(row["column_name"])


def fetch_stock_basis_preview(
    cur: psycopg.Cursor[dict[str, Any]],
    dates: DateContext,
    active_versions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    stock_daily_version = str(active_versions["stock_daily"]["active_source_version"])
    stock_basic_version = str(active_versions["stock_daily_basic"]["active_source_version"])
    stock_financial_version = str(active_versions["stock_financial"]["active_source_version"])
    cur.execute(
        """
        SELECT count(*)::bigint AS row_count,
               count(*) FILTER (WHERE d.stock_identity_key IS NULL OR d.stock_identity_key = '')::bigint AS missing_identity_key_count,
               count(*) FILTER (WHERE d.code ~ '^88[0-9]{4}$')::bigint AS board_code_violation_count,
               count(b.stock_identity_key)::bigint AS daily_basic_join_count,
               count(f.stock_identity_key)::bigint AS financial_join_count,
               count(*) FILTER (WHERE b.total_mv IS NULL)::bigint AS missing_total_mv_count,
               count(*) FILTER (WHERE b.total_mv > %s)::bigint AS total_mv_over_100yi_count,
               count(*) FILTER (WHERE d.official_daily_proof = false)::bigint AS official_daily_unproved_count
        FROM stock_daily_bar_fact d
        JOIN stock_daily_basic b
          ON b.stock_identity_key = d.stock_identity_key
         AND b.trade_date = d.trade_date
         AND b.source_version = %s
        JOIN stock_financial_metrics_fact f
          ON f.stock_identity_key = d.stock_identity_key
         AND f.source_trade_date = d.trade_date
         AND f.source_version = %s
        WHERE d.trade_date = %s
          AND d.source_version = %s
        """,
        (STOCK_SCOPE_MIN_TOTAL_MV_WAN, stock_basic_version, stock_financial_version, dates.source_trade_date, stock_daily_version),
    )
    metrics = normalize_mapping(cur.fetchone())
    period_contexts = fetch_period_contexts(
        cur,
        table_name="stock_daily_bar_fact",
        identity_column="stock_identity_key",
        source_trade_date=dates.source_trade_date,
        source_prev_trade_date=dates.source_prev_trade_date,
        current_source_version=stock_daily_version,
    )
    cur.execute(
        """
        SELECT d.stock_identity_key,
               d.code,
               d.exchange,
               d.ts_code,
               COALESCE(d.name, si.name) AS name,
               si.is_st,
               si.status AS stock_status,
               d.official_daily_proof,
               d.open,
               d.high,
               d.low,
               d.close,
               d.volume,
               d.amount,
               b.turnover_rate,
               b.pe_ttm,
               b.pb,
               b.total_mv,
               b.circ_mv,
               f.pe_core,
               f.score,
               f.cash_realization_rate,
               f.revenue_yoy_pct,
               f.core_profit_yoy_pct,
               f.report_core_revenue,
               f.report_core_profit,
               f.core_profit_ttm,
               f.core_gt_revenue_yoy,
               f.revenue_growth_streak_q,
               f.core_growth_streak_q,
               f.core_gt_revenue_streak_q,
               f.forecast_type,
               f.forecast_score,
               f.score_breakdown_json,
               f.financial_warning_json,
               f.financial_metric_version,
               f.asof_date AS financial_asof_date,
               f.quality_status AS financial_quality_status,
               f.source_version AS financial_source_version,
               d.source_version
        FROM stock_daily_bar_fact d
        LEFT JOIN stock_identity si
          ON si.stock_identity_key = d.stock_identity_key
        JOIN stock_daily_basic b
          ON b.stock_identity_key = d.stock_identity_key
         AND b.trade_date = d.trade_date
         AND b.source_version = %s
        JOIN stock_financial_metrics_fact f
          ON f.stock_identity_key = d.stock_identity_key
         AND f.source_trade_date = d.trade_date
         AND f.source_version = %s
        WHERE d.trade_date = %s
          AND d.source_version = %s
        ORDER BY d.stock_identity_key
        """,
        (stock_basic_version, stock_financial_version, dates.source_trade_date, stock_daily_version),
    )
    samples = [
        make_stock_sample_basis(row, dates, period_contexts.get(str(row.get("stock_identity_key") or ""), {}))
        for row in cur.fetchall()
    ]
    summary = summarize_basis_rows(samples)
    return {
        **metrics,
        "source_version": stock_daily_version,
        "daily_basic_source_version": stock_basic_version,
        "financial_source_version": stock_financial_version,
        **summary,
        "basis_rows": samples,
        "sample_basis_rows": samples[:3],
    }


def fetch_index_basis_preview(
    cur: psycopg.Cursor[dict[str, Any]],
    dates: DateContext,
    active_versions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    source_version = str(active_versions["index_daily"]["active_source_version"])
    cur.execute(
        """
        SELECT count(*)::bigint AS row_count,
               count(*) FILTER (WHERE index_identity_key IS NULL OR index_identity_key = '')::bigint AS missing_identity_key_count
        FROM index_daily_bar_fact
        WHERE trade_date = %s
          AND source_version = %s
        """,
        (dates.source_trade_date, source_version),
    )
    metrics = normalize_mapping(cur.fetchone())
    period_contexts = fetch_period_contexts(
        cur,
        table_name="index_daily_bar_fact",
        identity_column="index_identity_key",
        source_trade_date=dates.source_trade_date,
        source_prev_trade_date=dates.source_prev_trade_date,
        current_source_version=source_version,
    )
    cur.execute(
        """
        SELECT index_identity_key, code, exchange, name, open, high, low, close, volume, amount, source_version
        FROM index_daily_bar_fact
        WHERE trade_date = %s
          AND source_version = %s
        ORDER BY index_identity_key
        """,
        (dates.source_trade_date, source_version),
    )
    samples = [
        make_index_sample_basis(row, dates, period_contexts.get(str(row.get("index_identity_key") or ""), {}))
        for row in cur.fetchall()
    ]
    summary = summarize_basis_rows(samples)
    fixed_index_identity_keys = {str(row.get("index_identity_key") or "") for row in samples}
    fixed_index_missing_basis = [
        identity_key
        for identity_key in DEFAULT_INDEX_POOL_IDENTITIES
        if identity_key not in fixed_index_identity_keys
    ]
    fixed_index_amount_baseline_warnings = [
        {
            "identity_key": row.get("index_identity_key"),
            "code": row.get("code"),
            "name": row.get("name"),
            "amount_quality_status": row.get("amount_quality_status"),
        }
        for row in samples
        if str(row.get("index_identity_key") or "") in DEFAULT_INDEX_POOL_IDENTITIES
        and row.get("amount_quality_status") != "passed"
    ]
    return {
        **metrics,
        "source_version": source_version,
        "fixed_default_index_identity_keys": list(DEFAULT_INDEX_POOL_IDENTITIES),
        "fixed_default_index_present_basis": [
            identity_key
            for identity_key in DEFAULT_INDEX_POOL_IDENTITIES
            if identity_key in fixed_index_identity_keys
        ],
        "fixed_default_index_missing_basis": fixed_index_missing_basis,
        "fixed_default_index_missing_basis_count": len(fixed_index_missing_basis),
        "fixed_default_index_amount_baseline_warnings": fixed_index_amount_baseline_warnings,
        "fixed_default_index_amount_baseline_warning_count": len(fixed_index_amount_baseline_warnings),
        **summary,
        "basis_rows": samples,
        "sample_basis_rows": samples[:3],
    }


def fetch_board_basis_preview(
    cur: psycopg.Cursor[dict[str, Any]],
    dates: DateContext,
    active_versions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    source_version = str(active_versions["board_daily"]["active_source_version"])
    cur.execute(
        """
        SELECT count(*)::bigint AS row_count,
               count(*) FILTER (WHERE board_identity_key IS NULL OR board_identity_key = '')::bigint AS missing_identity_key_count,
               count(*) FILTER (WHERE board_code !~ '^88[0-9]{4}$')::bigint AS non_board_code_count
        FROM board_daily_bar_fact
        WHERE trade_date = %s
          AND source_version = %s
        """,
        (dates.source_trade_date, source_version),
    )
    metrics = normalize_mapping(cur.fetchone())
    period_contexts = fetch_period_contexts(
        cur,
        table_name="board_daily_bar_fact",
        identity_column="board_identity_key",
        source_trade_date=dates.source_trade_date,
        source_prev_trade_date=dates.source_prev_trade_date,
        current_source_version=source_version,
    )
    cur.execute(
        """
        SELECT board_identity_key, board_code, board_name, board_type, open, high, low, close, volume, amount, source_version
        FROM board_daily_bar_fact
        WHERE trade_date = %s
          AND source_version = %s
        ORDER BY board_identity_key
        """,
        (dates.source_trade_date, source_version),
    )
    samples = [
        make_board_sample_basis(row, dates, period_contexts.get(str(row.get("board_identity_key") or ""), {}))
        for row in cur.fetchall()
    ]
    summary = summarize_basis_rows(samples)
    return {
        **metrics,
        "source_version": source_version,
        **summary,
        "basis_rows": samples,
        "sample_basis_rows": samples[:3],
    }


def fetch_period_escalation_previous_context_run(
    cur: psycopg.Cursor[dict[str, Any]],
    dates: DateContext,
) -> dict[str, Any] | None:
    """Resolve exactly zero or one eligible immediate predecessor run."""

    cur.execute(
        """
        SELECT run_id,
               updated_at::text AS updated_at
        FROM common_condition_run
        WHERE status = 'passed_active'
          AND source_trade_date = %s
          AND for_trade_date = %s
        ORDER BY run_id
        """,
        (dates.source_prev_trade_date, dates.source_trade_date),
    )
    rows = [normalize_mapping(row) for row in cur.fetchall()]
    if len(rows) > 1:
        raise ValueError("period_escalation_previous_run_ambiguous")
    return rows[0] if rows else None


def period_escalation_incremental_epoch(previous_context_run: Mapping[str, Any] | None) -> tuple[str, str]:
    if not previous_context_run:
        return "", ""
    return (
        str(previous_context_run.get("run_id") or ""),
        str(previous_context_run.get("updated_at") or ""),
    )


def attach_period_escalation_contexts(
    cur: psycopg.Cursor[dict[str, Any]],
    dates: DateContext,
    summaries: Mapping[str, dict[str, Any]],
    *,
    previous_context_run: Mapping[str, Any] | None,
    open_source_dates: Iterable[str],
) -> None:
    """Attach prior-day directional state without scanning historical basis rows."""

    previous_run_id = str((previous_context_run or {}).get("run_id") or "")
    for asset_kind, summary in summaries.items():
        current_rows = list(summary.get("basis_rows") or [])
        previous_context_rows = fetch_period_escalation_previous_context_rows(
            cur,
            asset_kind=asset_kind,
            identity_keys=[basis_identity_key(row) for row in current_rows],
            source_prev_trade_date=dates.source_prev_trade_date,
            previous_run_id=previous_run_id,
        )
        previous_context_by_identity = index_period_escalation_previous_context_rows(previous_context_rows)
        updated_rows = [
            attach_period_escalation_context_to_row(
                row,
                dates=dates,
                previous_context_by_identity=previous_context_by_identity,
                open_source_dates=open_source_dates,
            )
            for row in current_rows
        ]
        summary["basis_rows"] = updated_rows
        summary["sample_basis_rows"] = updated_rows[:3]


def fetch_period_escalation_window_trade_dates(
    cur: psycopg.Cursor[dict[str, Any]],
    dates: DateContext,
) -> list[str]:
    cur.execute(
        """
        SELECT trade_date
        FROM common_trade_calendar
        WHERE is_open = true
          AND trade_date <= %s
          AND trade_date >= %s
        ORDER BY trade_date
        """,
        (
            dates.source_trade_date,
            format_yyyymmdd(parse_yyyymmdd(dates.for_trade_date).replace(month=1, day=1)),
        ),
    )
    return [
        format_yyyymmdd(value) if isinstance(value := row.get("trade_date"), date) else str(value).replace("-", "")
        for row in cur.fetchall()
        if row.get("trade_date")
    ]


def fetch_period_escalation_previous_context_rows(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    asset_kind: str,
    identity_keys: Iterable[str],
    source_prev_trade_date: str,
    previous_run_id: str,
) -> list[dict[str, Any]]:
    """Read only the immediately preceding passed-active basis context."""

    table_name, identity_column, basis_id_column = PERIOD_ESCALATION_BASIS_TABLES[asset_kind]
    keys = sorted({str(key) for key in identity_keys if key})
    if not keys or not previous_run_id:
        return []
    cur.execute(
        f"""
        SELECT b.source_trade_date,
               b.{identity_column} AS identity_key,
               b.run_id AS source_condition_run_id,
               b.{basis_id_column} AS source_basis_id,
               b.period_transition_d,
               b.period_transition_w,
               b.period_transition_m,
               b.period_transition_q,
               b.period_trigger_baseline_json
        FROM {table_name} b
        WHERE b.run_id = %s
          AND b.source_trade_date = %s
          AND b.{identity_column} = ANY(%s)
        ORDER BY b.{identity_column}, b.{basis_id_column}
        """,
        (previous_run_id, source_prev_trade_date, keys),
    )
    return [normalize_mapping(row) for row in cur.fetchall()]


def index_period_escalation_previous_context_rows(
    previous_context_rows: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build the single fail-closed identity index for one asset-kind batch."""

    output: dict[str, dict[str, Any]] = {}
    for item in previous_context_rows:
        row = normalize_mapping(item)
        identity_key = str(row.get("identity_key") or "")
        if not identity_key:
            raise ValueError("period_escalation_previous_context_missing_identity")
        if identity_key in output:
            raise ValueError("period_escalation_previous_context_duplicate_identity")
        output[identity_key] = row
    return output


def attach_period_escalation_context_to_row(
    row: Mapping[str, Any],
    *,
    dates: DateContext,
    previous_context_by_identity: Mapping[str, Mapping[str, Any]],
    open_source_dates: Iterable[str],
) -> dict[str, Any]:
    output = dict(row)
    identity_key = basis_identity_key(output)
    baseline = normalize_mapping(output.get("period_trigger_baseline_json") or {})
    previous_context = previous_context_by_identity.get(identity_key)
    baseline["period_escalation_context"] = build_period_escalation_context(
        dates=dates,
        asset_kind=str(output.get("asset_kind") or ""),
        identity_key=identity_key,
        current_row=output,
        previous_context=previous_context,
        open_source_dates=open_source_dates,
    )
    output["period_trigger_baseline_json"] = baseline
    baseline["condition_projection_context"] = build_condition_projection_context(
        dates=dates,
        current_row=output,
        baseline=baseline,
    )
    output["period_trigger_baseline_json"] = baseline
    return attach_context_enrichment_to_row(output)


def build_period_escalation_context(
    *,
    dates: DateContext,
    asset_kind: str,
    identity_key: str,
    current_row: Mapping[str, Any],
    previous_context: Mapping[str, Any] | None,
    open_source_dates: Iterable[str],
) -> dict[str, Any]:
    """Build the immutable directional incremental W/M/Q/Y prerequisite context."""

    source_day = parse_yyyymmdd(dates.source_trade_date)
    previous = normalized_previous_incremental_context(
        previous_context,
        dates=dates,
        asset_kind=asset_kind,
        identity_key=identity_key,
    )
    directions = {
        direction: {
            period: build_incremental_period_escalation_entry(
                dates=dates,
                source_day=source_day,
                target_period=period,
                direction=direction,
                current_row=current_row,
                previous_context=previous,
                asset_kind=asset_kind,
                identity_key=identity_key,
                open_source_dates=open_source_dates,
            )
            for period in ("W", "M", "Q", "Y")
        }
        for direction in ("buy", "sell")
    }
    payload = {
        "contract_version": PERIOD_ESCALATION_CONTEXT_VERSION,
        "generation_mode": PERIOD_ESCALATION_CONTEXT_GENERATION_MODE,
        "state_epoch_trade_date": dates.source_trade_date,
        "previous_context_hash": previous.get("context_hash") if previous else None,
        "previous_source_condition_run_id": previous.get("_previous_source_condition_run_id") if previous else None,
        "source_layer": "N2_condition",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "for_trade_date": dates.for_trade_date,
        "source_trade_date": dates.source_trade_date,
        "directions": directions,
    }
    return {**payload, "context_hash": stable_json_hash(payload)}


def normalized_previous_incremental_context(
    previous_context_row: Mapping[str, Any] | None,
    *,
    dates: DateContext,
    asset_kind: str,
    identity_key: str,
) -> Mapping[str, Any] | None:
    """Accept only the previous day generated by this directional mode."""

    if not isinstance(previous_context_row, Mapping):
        return None
    if "period_escalation_context" in previous_context_row:
        context = normalize_mapping(previous_context_row.get("period_escalation_context") or {})
    elif "directions" in previous_context_row:
        context = normalize_mapping(previous_context_row)
    else:
        baseline = normalize_mapping(previous_context_row.get("period_trigger_baseline_json") or {})
        context = normalize_mapping(baseline.get("period_escalation_context") or {})
    if context.get("generation_mode") != PERIOD_ESCALATION_CONTEXT_GENERATION_MODE:
        return None
    if context.get("contract_version") != PERIOD_ESCALATION_CONTEXT_VERSION:
        return None
    if context.get("asset_kind") != asset_kind or context.get("identity_key") != identity_key:
        return None
    if context.get("source_trade_date") != dates.source_prev_trade_date:
        return None
    if context.get("for_trade_date") != dates.source_trade_date:
        return None
    if context.get("state_epoch_trade_date") != dates.source_prev_trade_date:
        return None
    context_hash = context.get("context_hash")
    if not isinstance(context_hash, str):
        return None
    hashed = dict(context)
    hashed.pop("context_hash", None)
    if stable_json_hash(hashed) != context_hash:
        return None
    output = dict(context)
    previous_run_id = str(
        previous_context_row.get("source_condition_run_id")
        or previous_context_row.get("run_id")
        or ""
    )
    if previous_run_id:
        output["_previous_source_condition_run_id"] = previous_run_id
    return output


def prior_incremental_entry(
    previous_context: Mapping[str, Any] | None,
    *,
    direction: str,
    target_period: str,
    window_key: str,
    window_start: str,
) -> Mapping[str, Any] | None:
    if not isinstance(previous_context, Mapping):
        return None
    directions = previous_context.get("directions")
    if not isinstance(directions, Mapping):
        return None
    by_direction = directions.get(direction)
    if not isinstance(by_direction, Mapping):
        return None
    entry = by_direction.get(target_period)
    if not isinstance(entry, Mapping):
        return None
    requirement = PERIOD_ESCALATION_REQUIREMENTS[target_period]
    expected_semantics = {
        "target_period": target_period,
        "prerequisite_period": requirement["prerequisite_period"],
        "window_kind": requirement["window_kind"],
        "window_key": window_key,
        "window_start": window_start,
        "reset_for_trade_date": False,
        "required_transition": PERIOD_ESCALATION_DIRECTION_TRANSITIONS[direction],
    }
    if any(entry.get(field) != value for field, value in expected_semantics.items()):
        return None
    entry_hash = entry.get("entry_hash")
    if not isinstance(entry_hash, str):
        return None
    hashed = dict(entry)
    hashed.pop("entry_hash", None)
    if stable_json_hash(hashed) != entry_hash:
        return None
    return entry


def valid_prior_incremental_entry(
    entry: Mapping[str, Any] | None,
    *,
    expected_dates: list[str],
    asset_kind: str,
    identity_key: str,
) -> bool:
    """Validate the previous entry without requiring complete negative coverage."""

    if not isinstance(entry, Mapping):
        return False
    coverage_status = entry.get("coverage_status")
    status = entry.get("status")
    seen = entry.get("seen")
    expected_count = entry.get("expected_source_trade_date_count")
    observed_count = entry.get("observed_source_trade_date_count")
    observation_count = entry.get("observation_count")
    previous_state_used = entry.get("previous_incremental_state_used")
    missing_dates = entry.get("missing_source_trade_dates")
    state_epoch_trade_date = entry.get("state_epoch_trade_date")
    if coverage_status not in {"passed", "incomplete"}:
        return False
    if status not in {"ready", "not_seen", "not_ready"} or type(seen) is not bool:
        return False
    if any(type(value) is not int for value in (expected_count, observed_count, observation_count)):
        return False
    if type(previous_state_used) is not bool:
        return False
    if not isinstance(missing_dates, list) or any(not isinstance(value, str) for value in missing_dates):
        return False
    if expected_count != len(expected_dates):
        return False
    unique_missing_dates = sorted(set(missing_dates))
    if unique_missing_dates != missing_dates:
        return False
    if any(value not in expected_dates for value in missing_dates):
        return False
    if observed_count != expected_count - len(missing_dates):
        return False
    if previous_state_used != (observed_count > 1):
        return False
    observed_dates = [value for value in expected_dates if value not in missing_dates]
    if not observed_dates or state_epoch_trade_date != observed_dates[0]:
        return False
    if entry.get("observation_end") != expected_dates[-1]:
        return False
    if coverage_status == "passed":
        if missing_dates or observed_count != expected_count:
            return False
    elif not missing_dates or observed_count >= expected_count:
        return False
    if observation_count < 0 or observation_count > observed_count:
        return False
    if seen:
        first_source_trade_date = entry.get("first_source_trade_date")
        last_source_trade_date = entry.get("last_source_trade_date")
        latest_source_basis_ref = entry.get("latest_source_basis_ref")
        latest_source_condition_run_id = entry.get("latest_source_condition_run_id")
        return (
            status == "ready"
            and observation_count > 0
            and first_source_trade_date in observed_dates
            and last_source_trade_date in observed_dates
            and first_source_trade_date <= last_source_trade_date
            and latest_source_basis_ref
            == f"current:{asset_kind}:{identity_key}:{last_source_trade_date}"
            and (
                latest_source_condition_run_id is None
                or isinstance(latest_source_condition_run_id, str)
            )
        )
    if observation_count != 0:
        return False
    if any(
        entry.get(field) is not None
        for field in (
            "first_source_trade_date",
            "last_source_trade_date",
            "latest_source_condition_run_id",
            "latest_source_basis_ref",
        )
    ):
        return False
    return (
        coverage_status == "passed" and status == "not_seen"
    ) or (
        coverage_status == "incomplete" and status == "not_ready"
    )


def build_incremental_period_escalation_entry(
    *,
    dates: DateContext,
    source_day: date,
    target_period: str,
    direction: str,
    current_row: Mapping[str, Any],
    previous_context: Mapping[str, Any] | None,
    asset_kind: str,
    identity_key: str,
    open_source_dates: Iterable[str],
) -> dict[str, Any]:
    requirement = PERIOD_ESCALATION_REQUIREMENTS[target_period]
    prerequisite_period = requirement["prerequisite_period"]
    window_start = period_escalation_window_start(target_period, dates.for_trade_date)
    reset = source_day < window_start
    required_transition = PERIOD_ESCALATION_DIRECTION_TRANSITIONS[direction]
    window_key = period_key(target_period, dates.for_trade_date)
    calendar_dates = sorted({str(value) for value in open_source_dates if str(value)})
    window_start_text = format_yyyymmdd(window_start)
    expected_dates = [
        value
        for value in calendar_dates
        if window_start_text <= value <= dates.source_trade_date
    ]
    previous_expected_dates = [
        value
        for value in expected_dates
        if value <= dates.source_prev_trade_date
    ]
    candidate_prior = None if reset else prior_incremental_entry(
        previous_context,
        direction=direction,
        target_period=target_period,
        window_key=window_key,
        window_start=window_start_text,
    )
    prior_state_valid = valid_prior_incremental_entry(
        candidate_prior,
        expected_dates=previous_expected_dates,
        asset_kind=asset_kind,
        identity_key=identity_key,
    )
    can_continue = (
        not reset
        and prior_state_valid
        and expected_dates
        and expected_dates[-1] == dates.source_trade_date
        and len(expected_dates) == len(previous_expected_dates) + 1
    )
    prior = candidate_prior if can_continue else None
    prior_seen = bool(prior and prior.get("seen") is True)
    prior_count = int(prior.get("observation_count") or 0) if prior else 0
    current_match = (
        not reset
        and dates.source_trade_date in expected_dates
        and str(current_row.get(f"period_transition_{PERIOD_FIELD_SUFFIX[prerequisite_period]}") or "") == required_transition
    )
    current_observation = period_escalation_observation(
        current_row,
        source_basis_ref=f"current:{asset_kind}:{identity_key}:{dates.source_trade_date}",
    )
    current_observation["source_trade_date"] = dates.source_trade_date
    if reset:
        coverage_status = "not_applicable"
        missing_dates: list[str] = []
        observed_count = 0
    elif prior:
        missing_dates = list(prior.get("missing_source_trade_dates") or [])
        observed_count = int(prior.get("observed_source_trade_date_count") or 0) + 1
        coverage_status = "passed" if not missing_dates else "incomplete"
    else:
        current_observed = dates.source_trade_date in expected_dates
        missing_dates = [
            value
            for value in expected_dates
            if not current_observed or value != dates.source_trade_date
        ]
        observed_count = 1 if current_observed else 0
        coverage_status = "passed" if current_observed and not missing_dates else "incomplete"
    seen = (prior_seen or current_match) if not reset else False
    observation_count = prior_count + (1 if current_match else 0) if not reset else 0
    if current_match:
        first_source_trade_date = prior.get("first_source_trade_date") if prior_seen else current_observation["source_trade_date"]
        last_source_trade_date = current_observation["source_trade_date"]
        latest_source_condition_run_id = current_observation["source_condition_run_id"]
        latest_source_basis_ref = current_observation["source_basis_ref"]
    elif prior_seen:
        first_source_trade_date = prior.get("first_source_trade_date")
        last_source_trade_date = prior.get("last_source_trade_date")
        latest_source_condition_run_id = prior.get("latest_source_condition_run_id")
        latest_source_basis_ref = prior.get("latest_source_basis_ref")
    else:
        first_source_trade_date = None
        last_source_trade_date = None
        latest_source_condition_run_id = None
        latest_source_basis_ref = None
    payload = {
        "target_period": target_period,
        "prerequisite_period": prerequisite_period,
        "window_kind": requirement["window_kind"],
        "window_key": window_key,
        "window_start": window_start_text,
        "observation_end": dates.source_trade_date,
        "reset_for_trade_date": reset,
        "state_epoch_trade_date": (
            prior.get("state_epoch_trade_date")
            if prior
            else (dates.source_trade_date if not reset and dates.source_trade_date in expected_dates else None)
        ),
        "required_transition": required_transition,
        "status": "ready" if seen else ("not_ready" if coverage_status == "incomplete" else "not_seen"),
        "coverage_status": coverage_status,
        "seen": seen,
        "expected_source_trade_date_count": len(expected_dates),
        "observed_source_trade_date_count": observed_count,
        "missing_source_trade_dates": missing_dates,
        "observation_count": observation_count,
        "previous_incremental_state_used": bool(prior),
        "first_source_trade_date": first_source_trade_date,
        "last_source_trade_date": last_source_trade_date,
        "latest_source_condition_run_id": latest_source_condition_run_id,
        "latest_source_basis_ref": latest_source_basis_ref,
    }
    return {**payload, "entry_hash": stable_json_hash(payload)}


def period_escalation_window_start(target_period: str, for_trade_date: str) -> date:
    value = parse_yyyymmdd(for_trade_date)
    if target_period == "W":
        return value - timedelta(days=value.weekday())
    if target_period == "M":
        return value.replace(day=1)
    if target_period == "Q":
        return first_day_of_quarter(value)
    if target_period == "Y":
        return value.replace(month=1, day=1)
    raise ValueError(f"unsupported escalation target period: {target_period!r}")


def period_escalation_observation(
    row: Mapping[str, Any],
    *,
    source_basis_ref: str | None = None,
) -> dict[str, Any]:
    source_date = str(row.get("source_trade_date") or "")
    return {
        "source_trade_date": source_date,
        "source_condition_run_id": row.get("source_condition_run_id") or row.get("run_id"),
        "source_basis_ref": source_basis_ref
        or (
            f"basis:{row.get('source_condition_run_id') or row.get('run_id')}:{row.get('source_basis_id')}"
            if row.get("source_basis_id") is not None
            else None
        ),
        "period_transition_d": row.get("period_transition_d"),
        "period_transition_w": row.get("period_transition_w"),
        "period_transition_m": row.get("period_transition_m"),
        "period_transition_q": row.get("period_transition_q"),
    }


def basis_identity_key(row: Mapping[str, Any]) -> str:
    return str(
        row.get("identity_key")
        or row.get("stock_identity_key")
        or row.get("index_identity_key")
        or row.get("board_identity_key")
        or ""
    )


def build_condition_projection_context(
    *,
    dates: DateContext,
    current_row: Mapping[str, Any],
    baseline: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Freeze N2-owned condition fields for downstream projection messages."""

    asset_kind = str(current_row.get("asset_kind") or "").strip().lower()
    identity_key = basis_identity_key(current_row)
    source_trade_date = str(dates.source_trade_date or "")
    for_trade_date = str(dates.for_trade_date or "")
    raw_json = normalize_mapping(current_row.get("raw_json") or {})
    baseline_json = normalize_mapping(baseline or current_row.get("period_trigger_baseline_json") or {})
    periods = baseline_json.get("periods") if isinstance(baseline_json.get("periods"), Mapping) else {}
    d_baseline = periods.get("D") if isinstance(periods.get("D"), Mapping) else {}

    raw_close = condition_projection_decimal_or_none(raw_json.get("close"))
    d_close = condition_projection_decimal_or_none(d_baseline.get("current_close_seed"))
    field_names = CONDITION_PROJECTION_STOCK_FIELDS if asset_kind == "stock" else CONDITION_PROJECTION_COMMON_FIELDS
    fields: dict[str, Any] = {}
    for field in field_names:
        if field == "name":
            value = current_row.get("board_name") if asset_kind == "board" else current_row.get("name")
            fields[field] = str(value).strip() if value not in (None, "") else None
        elif field == "close":
            fields[field] = decimal_to_string(raw_close)
        elif field in CONDITION_PROJECTION_NUMERIC_FIELDS:
            fields[field] = decimal_to_string(
                condition_projection_decimal_or_none(current_row.get(field))
            )
        elif field in CONDITION_PROJECTION_PERIOD_FIELDS:
            fields[field] = condition_projection_period_or_none(current_row.get(field))
        else:
            fields[field] = current_row.get(field)

    reasons: list[str] = []
    if asset_kind not in PERIOD_ESCALATION_BASIS_TABLES:
        reasons.append("invalid_asset_kind")
    if not identity_key or not identity_key.startswith(f"{asset_kind}:"):
        reasons.append("invalid_identity_key")
    if not valid_yyyymmdd_text(source_trade_date):
        reasons.append("invalid_source_trade_date")
    if not valid_yyyymmdd_text(for_trade_date):
        reasons.append("invalid_for_trade_date")
    row_source_trade_date = str(current_row.get("source_trade_date") or "")
    row_for_trade_date = str(current_row.get("for_trade_date") or "")
    if row_source_trade_date and row_source_trade_date != source_trade_date:
        reasons.append("source_trade_date_mismatch")
    if row_for_trade_date and row_for_trade_date != for_trade_date:
        reasons.append("for_trade_date_mismatch")
    if valid_yyyymmdd_text(source_trade_date) and valid_yyyymmdd_text(for_trade_date) and source_trade_date >= for_trade_date:
        reasons.append("trade_date_order_invalid")
    if not fields.get("name"):
        reasons.append("name_missing")
    if raw_close is None or raw_close <= 0:
        reasons.append("raw_close_missing_or_non_positive")
    if d_close is None or d_close <= 0:
        reasons.append("d_current_close_seed_missing_or_non_positive")
    if raw_close is not None and d_close is not None and raw_close != d_close:
        reasons.append("close_source_mismatch")
    up_reference_period = condition_projection_period_or_none(current_row.get("up_sell_reference_period"))
    clear_sell_ref_period = fields.get("clear_sell_ref_period")
    if up_reference_period != clear_sell_ref_period:
        reasons.append("clear_sell_ref_period_alias_mismatch")

    optional_fields = [field for field in field_names if field not in {"name", "close"}]
    payload = {
        "contract_version": CONDITION_PROJECTION_CONTEXT_VERSION,
        "source_layer": "N2_condition",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "source_trade_date": source_trade_date,
        "for_trade_date": for_trade_date,
        "status": "not_ready" if reasons else "ready",
        "fields": fields,
        "nullable_fields": [field for field in optional_fields if fields.get(field) is None],
        "not_ready_reasons": reasons,
    }
    return {**payload, "context_hash": stable_json_hash(payload)}


def condition_projection_context_hash_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    actual_hash = str(value.get("context_hash") or "")
    payload = {str(key): item for key, item in value.items() if key != "context_hash"}
    return bool(actual_hash) and actual_hash == stable_json_hash(payload)


def condition_projection_decimal_or_none(value: Any) -> Decimal | None:
    try:
        numeric = decimal_or_none(value)
    except (InvalidOperation, TypeError, ValueError):
        return None
    return numeric if numeric is None or numeric.is_finite() else None


def condition_projection_period_or_none(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text if text in PERIODS else None


def valid_yyyymmdd_text(value: Any) -> bool:
    text = str(value or "")
    if len(text) != 8 or not text.isdigit():
        return False
    try:
        parse_yyyymmdd(text)
    except ValueError:
        return False
    return True


def stable_json_hash(value: Mapping[str, Any]) -> str:
    return sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def fetch_membership_summary(
    cur: psycopg.Cursor[dict[str, Any]],
    dates: DateContext,
    active_versions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for data_type, table_name, version_key in (
        ("index_membership", "index_membership_fact", "index_membership"),
        ("board_membership", "board_membership_fact", "board_membership"),
    ):
        source_version = str(active_versions[version_key]["active_source_version"])
        cur.execute(
            f"""
            SELECT count(*)::bigint AS row_count
            FROM {table_name}
            WHERE trade_date = %s
              AND source_version = %s
            """,
            (dates.source_trade_date, source_version),
        )
        output[data_type] = {
            "table_name": table_name,
            "source_version": source_version,
            **normalize_mapping(cur.fetchone()),
        }
    return output


def make_stock_sample_basis(row: Mapping[str, Any], dates: DateContext, period_context: Mapping[str, Any]) -> dict[str, Any]:
    condition_fields = computed_condition_fields(period_context, dates)
    amount_baseline_complete = bool(condition_fields.pop("amount_baseline_complete"))
    condition_calculation_version = str(condition_fields.pop("condition_calculation_version"))
    static_complete = static_structure_complete(condition_fields)
    basis = {
        "for_trade_date": dates.for_trade_date,
        "source_trade_date": dates.source_trade_date,
        "prev_trade_date": dates.prev_trade_date,
        "stock_identity_key": row.get("stock_identity_key"),
        "asset_kind": "stock",
        "exchange": row.get("exchange"),
        "ts_code": row.get("ts_code"),
        "display_code": row.get("code"),
        "code": row.get("code"),
        "name": row.get("name"),
        "is_st": row.get("is_st"),
        "stock_status": row.get("stock_status"),
        "official_daily_proof": row.get("official_daily_proof"),
        "lane": "stock_alert",
        "monitor_type": "source_universe_preview",
        "monitor_status": "active",
        "direction_scope": ["buy", "sell"],
        "amount_source": "stock_daily_bar_fact.amount",
        "pe_core": row.get("pe_core"),
        "total_mv": row.get("total_mv"),
        "circ_mv": row.get("circ_mv"),
        "score": row.get("score"),
        "recommendation_level": None,
        "recommendation_reason": None,
        "financial_asof_date": row.get("financial_asof_date"),
        "financial_quality_status": row.get("financial_quality_status"),
        "financial_source_version": row.get("financial_source_version"),
        "main_index_identity_key": None,
        "preferred_board_identity_key": None,
        "linked_board_identity_keys": [],
        "source_version": row.get("source_version"),
        "source_batch_id": None,
        "quality_status": "warning",
        "quality_reason": COMPUTED_BASIS_REASON,
        "missing_fields_json": {
            "period_aggregation": False,
            "static_targets": not static_complete,
            "condition_necessary_rules": False,
            "amount_baseline": not amount_baseline_complete,
            "monitor_target": True,
        },
        "raw_json": {
            **normalize_mapping(row),
            "source_prev_trade_date": dates.source_prev_trade_date,
            "condition_calculation_version": condition_calculation_version,
        },
    }
    basis.update(stock_financial_pass_through_fields(row))
    basis.update(condition_fields)
    return attach_context_enrichment_to_row(basis)


def stock_financial_pass_through_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    return {field: row.get(field) for field in STOCK_FINANCIAL_PASS_THROUGH_FIELDS}


def make_index_sample_basis(row: Mapping[str, Any], dates: DateContext, period_context: Mapping[str, Any]) -> dict[str, Any]:
    condition_fields = computed_condition_fields(period_context, dates)
    amount_baseline_complete = bool(condition_fields.pop("amount_baseline_complete"))
    condition_calculation_version = str(condition_fields.pop("condition_calculation_version"))
    static_complete = static_structure_complete(condition_fields)
    basis = {
        "for_trade_date": dates.for_trade_date,
        "source_trade_date": dates.source_trade_date,
        "prev_trade_date": dates.prev_trade_date,
        "index_identity_key": row.get("index_identity_key"),
        "asset_kind": "index",
        "exchange": row.get("exchange"),
        "display_code": row.get("code"),
        "code": row.get("code"),
        "name": row.get("name"),
        "lane": "market_alert",
        "monitor_type": "source_universe_preview",
        "monitor_status": "active",
        "direction_scope": ["buy", "sell"],
        "amount_source": "index_daily_bar_fact.amount",
        "source_version": row.get("source_version"),
        "source_batch_id": None,
        "quality_status": "warning",
        "quality_reason": COMPUTED_BASIS_REASON,
        "missing_fields_json": {
            "period_aggregation": False,
            "static_targets": not static_complete,
            "condition_necessary_rules": False,
            "amount_baseline": not amount_baseline_complete,
            "monitor_target": True,
        },
        "raw_json": {
            **normalize_mapping(row),
            "source_prev_trade_date": dates.source_prev_trade_date,
            "condition_calculation_version": condition_calculation_version,
        },
    }
    basis.update(condition_fields)
    return attach_context_enrichment_to_row(basis)


def make_board_sample_basis(row: Mapping[str, Any], dates: DateContext, period_context: Mapping[str, Any]) -> dict[str, Any]:
    condition_fields = computed_condition_fields(period_context, dates)
    amount_baseline_complete = bool(condition_fields.pop("amount_baseline_complete"))
    condition_calculation_version = str(condition_fields.pop("condition_calculation_version"))
    static_complete = static_structure_complete(condition_fields)
    basis = {
        "for_trade_date": dates.for_trade_date,
        "source_trade_date": dates.source_trade_date,
        "prev_trade_date": dates.prev_trade_date,
        "board_identity_key": row.get("board_identity_key"),
        "asset_kind": "board",
        "board_code": row.get("board_code"),
        "board_name": row.get("board_name"),
        "board_type": row.get("board_type"),
        "lane": "market_alert",
        "monitor_type": "source_universe_preview",
        "monitor_status": "active",
        "direction_scope": ["buy", "sell"],
        "amount_source": "board_daily_bar_fact.amount",
        "source_version": row.get("source_version"),
        "source_batch_id": None,
        "quality_status": "warning",
        "quality_reason": COMPUTED_BASIS_REASON,
        "missing_fields_json": {
            "period_aggregation": False,
            "static_targets": not static_complete,
            "condition_necessary_rules": False,
            "amount_baseline": not amount_baseline_complete,
            "monitor_target": True,
        },
        "raw_json": {
            **normalize_mapping(row),
            "source_prev_trade_date": dates.source_prev_trade_date,
            "condition_calculation_version": condition_calculation_version,
        },
    }
    basis.update(condition_fields)
    return attach_context_enrichment_to_row(basis)


def fetch_period_contexts(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    table_name: str,
    identity_column: str,
    source_trade_date: str,
    source_prev_trade_date: str,
    current_source_version: str,
) -> dict[str, dict[str, Any]]:
    if table_name not in {"stock_daily_bar_fact", "index_daily_bar_fact", "board_daily_bar_fact"}:
        raise ValueError(f"unsupported period fact table: {table_name}")
    if identity_column not in {"stock_identity_key", "index_identity_key", "board_identity_key"}:
        raise ValueError(f"unsupported period identity column: {identity_column}")

    ranges = period_ranges(source_trade_date, source_prev_trade_date)
    min_start = min(item["start_date"] for item in ranges)
    values_sql = ", ".join(["(%s, %s, %s, %s)"] * len(ranges))
    is_stock = table_name == "stock_daily_bar_fact"
    params: list[Any] = []
    for item in ranges:
        params.extend([item["period"], item["slot"], item["start_date"], item["end_date"]])
    if is_stock:
        params.extend([source_trade_date, current_source_version, min_start, source_trade_date, source_trade_date, current_source_version])
        cur.execute(
            f"""
            WITH period_ranges(period, slot, start_date, end_date) AS (
              VALUES {values_sql}
            ),
            current_adj AS (
              SELECT {identity_column} AS identity_key,
                     adj_factor AS current_adj_factor
              FROM {table_name}
              WHERE trade_date = %s
                AND source_version = %s
            ),
            facts AS (
              SELECT f.{identity_column} AS identity_key,
                     f.trade_date,
                     f.open AS raw_open,
                     f.high AS raw_high,
                     f.low AS raw_low,
                     f.close AS raw_close,
                     f.open * f.adj_factor / NULLIF(ca.current_adj_factor, 0) AS open,
                     f.high * f.adj_factor / NULLIF(ca.current_adj_factor, 0) AS high,
                     f.low * f.adj_factor / NULLIF(ca.current_adj_factor, 0) AS low,
                     f.close * f.adj_factor / NULLIF(ca.current_adj_factor, 0) AS close,
                     f.amount,
                     f.adj_factor,
                     ca.current_adj_factor,
                     'ROW_ADJ_FACTOR_TO_CURRENT_ADJ_FACTOR'::text AS adjustment_policy,
                     f.source_version
              FROM {table_name} f
              LEFT JOIN current_adj ca
                ON ca.identity_key = f.{identity_column}
              WHERE f.trade_date BETWEEN %s AND %s
                AND (f.trade_date <> %s OR f.source_version = %s)
            )
            SELECT f.identity_key,
                   p.period,
                   p.slot,
                   min(f.trade_date) AS start_trade_date,
                   max(f.trade_date) AS end_trade_date,
                   (array_agg(f.open ORDER BY f.trade_date ASC))[1] AS open,
                   max(f.high) AS high,
                   min(f.low) AS low,
                   (array_agg(f.close ORDER BY f.trade_date DESC))[1] AS close,
                   min(f.close) AS min_close,
                   max(f.close) AS max_close,
                   CASE WHEN p.period = 'D' THEN sum(f.amount) ELSE avg(f.amount) END AS amount,
                   avg(f.amount) AS avg_amount,
                   sum(f.amount) AS amount_total,
                   count(*)::bigint AS day_count,
                   (array_agg(f.raw_open ORDER BY f.trade_date ASC))[1] AS raw_open,
                   (array_agg(f.raw_close ORDER BY f.trade_date DESC))[1] AS raw_close,
                   (array_agg(f.adj_factor ORDER BY f.trade_date ASC))[1] AS start_adj_factor,
                   (array_agg(f.adj_factor ORDER BY f.trade_date DESC))[1] AS end_adj_factor,
                   max(f.current_adj_factor) AS current_adj_factor,
                   max(f.adjustment_policy) AS adjustment_policy,
                   count(*) FILTER (
                     WHERE f.adj_factor IS NULL
                        OR f.current_adj_factor IS NULL
                        OR f.current_adj_factor = 0
                   )::bigint AS adj_factor_missing_count
            FROM period_ranges p
            JOIN facts f
              ON f.trade_date BETWEEN p.start_date AND p.end_date
            GROUP BY f.identity_key, p.period, p.slot
            ORDER BY f.identity_key, p.period, p.slot
            """,
            params,
        )
    else:
        params.extend([min_start, source_trade_date, source_trade_date, current_source_version])
        cur.execute(
            f"""
            WITH period_ranges(period, slot, start_date, end_date) AS (
              VALUES {values_sql}
            ),
            facts AS (
              SELECT {identity_column} AS identity_key,
                     trade_date,
                     open,
                     high,
                     low,
                     close,
                     amount,
                     source_version
              FROM {table_name}
              WHERE trade_date BETWEEN %s AND %s
                AND (trade_date <> %s OR source_version = %s)
            )
            SELECT f.identity_key,
                   p.period,
                   p.slot,
                   min(f.trade_date) AS start_trade_date,
                   max(f.trade_date) AS end_trade_date,
                   (array_agg(f.open ORDER BY f.trade_date ASC))[1] AS open,
                   max(f.high) AS high,
                   min(f.low) AS low,
                   (array_agg(f.close ORDER BY f.trade_date DESC))[1] AS close,
                   min(f.close) AS min_close,
                   max(f.close) AS max_close,
                   CASE WHEN p.period = 'D' THEN sum(f.amount) ELSE avg(f.amount) END AS amount,
                   avg(f.amount) AS avg_amount,
                   sum(f.amount) AS amount_total,
                   count(*)::bigint AS day_count
            FROM period_ranges p
            JOIN facts f
              ON f.trade_date BETWEEN p.start_date AND p.end_date
            GROUP BY f.identity_key, p.period, p.slot
            ORDER BY f.identity_key, p.period, p.slot
            """,
            params,
        )
    contexts: dict[str, dict[str, Any]] = {}
    for row in cur.fetchall():
        identity_key = str(row["identity_key"])
        period = str(row["period"])
        slot = str(row["slot"])
        contexts.setdefault(identity_key, {}).setdefault(period, {})[slot] = normalize_mapping(row)
    for context in contexts.values():
        enrich_period_context(context, source_trade_date, source_prev_trade_date)
    if is_stock:
        cur.execute(
            f"""
            WITH current_adj AS (
              SELECT {identity_column} AS identity_key,
                     adj_factor AS current_adj_factor
              FROM {table_name}
              WHERE trade_date = %s
                AND source_version = %s
            )
            SELECT f.{identity_column} AS identity_key,
                   f.trade_date,
                   f.open AS raw_open,
                   f.high AS raw_high,
                   f.low AS raw_low,
                   f.close AS raw_close,
                   f.open * f.adj_factor / NULLIF(ca.current_adj_factor, 0) AS open,
                   f.high * f.adj_factor / NULLIF(ca.current_adj_factor, 0) AS high,
                   f.low * f.adj_factor / NULLIF(ca.current_adj_factor, 0) AS low,
                   f.close * f.adj_factor / NULLIF(ca.current_adj_factor, 0) AS close,
                   f.amount,
                   f.adj_factor,
                   ca.current_adj_factor,
                   'ROW_ADJ_FACTOR_TO_CURRENT_ADJ_FACTOR'::text AS adjustment_policy,
                   f.source_version
            FROM {table_name} f
            LEFT JOIN current_adj ca
              ON ca.identity_key = f.{identity_column}
            WHERE f.trade_date BETWEEN %s AND %s
              AND (f.trade_date <> %s OR f.source_version = %s)
            ORDER BY f.{identity_column}, f.trade_date
            """,
            (source_trade_date, current_source_version, min_start, source_trade_date, source_trade_date, current_source_version),
        )
    else:
        cur.execute(
            f"""
            SELECT {identity_column} AS identity_key,
                   trade_date,
                   open,
                   high,
                   low,
                   close,
                   amount,
                   source_version
            FROM {table_name}
            WHERE trade_date BETWEEN %s AND %s
              AND (trade_date <> %s OR source_version = %s)
            ORDER BY {identity_column}, trade_date
            """,
            (min_start, source_trade_date, source_trade_date, current_source_version),
        )
    for row in cur.fetchall():
        identity_key = str(row["identity_key"])
        contexts.setdefault(identity_key, {}).setdefault("_daily_rows", []).append(normalize_mapping(row))
    return contexts


def period_ranges(source_trade_date: str, source_prev_trade_date: str) -> list[dict[str, str]]:
    source_day = parse_yyyymmdd(source_trade_date)
    previous_source_day = parse_yyyymmdd(source_prev_trade_date)
    quarter_start = first_day_of_quarter(source_day)
    previous_quarter_end = quarter_start - timedelta(days=1)
    previous_quarter_start = first_day_of_quarter(previous_quarter_end)
    seed_quarter_end = previous_quarter_start - timedelta(days=1)
    seed_quarter_start = first_day_of_quarter(seed_quarter_end)
    month_start = source_day.replace(day=1)
    previous_month_end = month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    seed_month_end = previous_month_start - timedelta(days=1)
    seed_month_start = seed_month_end.replace(day=1)
    week_start = source_day - timedelta(days=source_day.weekday())
    previous_week_start = week_start - timedelta(days=7)
    previous_week_end = week_start - timedelta(days=1)
    seed_week_start = previous_week_start - timedelta(days=7)
    seed_week_end = previous_week_start - timedelta(days=1)
    return [
        period_range("Y", "current", source_day.replace(month=1, day=1), source_day),
        period_range("Y", "previous", source_day.replace(year=source_day.year - 1, month=1, day=1), source_day.replace(year=source_day.year - 1, month=12, day=31)),
        period_range("Y", "seed", source_day.replace(year=source_day.year - 2, month=1, day=1), source_day.replace(year=source_day.year - 2, month=12, day=31)),
        period_range("Q", "current", quarter_start, source_day),
        period_range("Q", "previous", previous_quarter_start, previous_quarter_end),
        period_range("Q", "seed", seed_quarter_start, seed_quarter_end),
        period_range("M", "current", month_start, source_day),
        period_range("M", "previous", previous_month_start, previous_month_end),
        period_range("M", "seed", seed_month_start, seed_month_end),
        period_range("W", "current", week_start, source_day),
        period_range("W", "previous", previous_week_start, previous_week_end),
        period_range("W", "seed", seed_week_start, seed_week_end),
        period_range("D", "current", source_day, source_day),
        period_range("D", "previous", previous_source_day, previous_source_day),
    ]


def period_range(period: str, slot: str, start_day: date, end_day: date) -> dict[str, str]:
    return {
        "period": period,
        "slot": slot,
        "start_date": format_yyyymmdd(start_day),
        "end_date": format_yyyymmdd(end_day),
    }


def parse_yyyymmdd(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()


def format_yyyymmdd(value: date) -> str:
    return value.strftime("%Y%m%d")


def first_day_of_quarter(value: date) -> date:
    month = ((value.month - 1) // 3) * 3 + 1
    return value.replace(month=month, day=1)


def enrich_period_context(context: dict[str, Any], source_trade_date: str, source_prev_trade_date: str) -> None:
    for period in PERIODS:
        current = context.get(period, {}).get("current")
        previous = context.get(period, {}).get("previous")
        if current:
            current["period_key"] = period_key(period, source_trade_date)
        if previous:
            previous["period_key"] = previous_period_key(period, source_trade_date, source_prev_trade_date)
        grade = period_grade(current, previous)
        seed_grade = period_grade(previous, context.get(period, {}).get("seed")) if previous else "unknown"
        context.setdefault(period, {})["grade"] = grade
        context[period]["transition_seed"] = seed_grade
        context[period]["transition"] = transition_grade(period, grade, seed_grade, current)


def period_key(period: str, source_trade_date: str) -> str:
    source_day = parse_yyyymmdd(source_trade_date)
    if period == "Y":
        return source_day.strftime("%Y")
    if period == "Q":
        return f"{source_day.year}Q{((source_day.month - 1) // 3) + 1}"
    if period == "M":
        return source_day.strftime("%Y%m")
    if period == "W":
        iso = source_day.isocalendar()
        return f"{iso.year}W{iso.week:02d}"
    if period == "D":
        return source_trade_date
    raise ValueError(f"unsupported period: {period!r}")


def previous_period_key(period: str, source_trade_date: str, source_prev_trade_date: str) -> str:
    source_day = parse_yyyymmdd(source_trade_date)
    if period == "Y":
        return str(source_day.year - 1)
    if period == "Q":
        previous_quarter_day = first_day_of_quarter(source_day) - timedelta(days=1)
        return f"{previous_quarter_day.year}Q{((previous_quarter_day.month - 1) // 3) + 1}"
    if period == "M":
        previous_month_day = source_day.replace(day=1) - timedelta(days=1)
        return previous_month_day.strftime("%Y%m")
    if period == "W":
        previous_week_day = source_day - timedelta(days=source_day.weekday() + 1)
        iso = previous_week_day.isocalendar()
        return f"{iso.year}W{iso.week:02d}"
    if period == "D":
        return source_prev_trade_date
    raise ValueError(f"unsupported period: {period!r}")


def period_grade(current: Mapping[str, Any] | None, previous: Mapping[str, Any] | None) -> str:
    if not current or not previous:
        return "unknown"
    current_close = decimal_or_none(current.get("close"))
    previous_open = decimal_or_none(previous.get("open"))
    previous_close = decimal_or_none(previous.get("close"))
    current_amount = decimal_or_none(current.get("amount"))
    previous_amount = decimal_or_none(previous.get("amount"))
    if None in (current_close, previous_open, previous_close, current_amount, previous_amount):
        return "unknown"
    if previous_amount <= 0:
        return "flat"
    previous_entity_high = max(previous_open, previous_close)
    previous_entity_low = min(previous_open, previous_close)
    amount_expanded = current_amount > previous_amount
    amount_shrunk = current_amount < previous_amount
    if current_close > previous_entity_high and amount_expanded:
        return "volume_up" if amount_expanded else "low_volume_up"
    if current_close > previous_entity_high and amount_shrunk:
        return "low_volume_up"
    if current_close < previous_entity_low and amount_expanded:
        return "volume_down"
    if current_close < previous_entity_low and amount_shrunk:
        return "low_volume_down"
    return "flat"


def transition_grade(
    period: str,
    current_grade: str,
    previous_transition_seed: str,
    current: Mapping[str, Any] | None,
) -> str:
    if current_grade == "unknown":
        return "unknown"
    if period not in TRANSITION_WINDOWS:
        return current_grade
    if current_grade in {"volume_up", "low_volume_down"}:
        return current_grade
    day_count = int(current.get("day_count") or 1) if current else 1
    if day_count <= TRANSITION_WINDOWS[period]:
        if previous_transition_seed == "volume_up" and current_grade in {"low_volume_up", "flat"}:
            return "volume_up"
        if previous_transition_seed == "low_volume_down" and current_grade in {"volume_down", "flat"}:
            return "low_volume_down"
    return current_grade


def decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))


def computed_condition_fields(period_context: Mapping[str, Any], dates: DateContext) -> dict[str, Any]:
    fields = empty_period_fields()
    amount_baseline_complete = True
    for period in PERIODS:
        suffix = PERIOD_FIELD_SUFFIX[period]
        current = period_context.get(period, {}).get("current") if period_context else None
        previous = period_context.get(period, {}).get("previous") if period_context else None
        grade = str(period_context.get(period, {}).get("grade") or "unknown") if period_context else "unknown"
        transition = str(period_context.get(period, {}).get("transition") or grade)
        fields[f"period_grade_{suffix}"] = grade
        fields[f"period_transition_{suffix}"] = transition
        if period != "D":
            fields[f"period_key_{suffix}"] = period_key(period, dates.source_trade_date)
        else:
            fields["period_key_d"] = dates.source_trade_date
        set_amount_fields(fields, period, current, previous)
        if current is None or current.get("amount") in (None, "") or previous is None or previous.get("amount") in (None, ""):
            amount_baseline_complete = False

    transitions = {
        period: fields[f"period_transition_{PERIOD_FIELD_SUFFIX[period]}"]
        for period in PERIODS
    }
    fields.update(compute_level_scores_from_transitions(transitions))
    buy_periods = [period for period in PERIODS if transitions[period] in BUY_ALLOWED_GRADES]
    sell_periods = [period for period in PERIODS if transitions[period] in SELL_ALLOWED_GRADES]
    prev_up_str = build_up_string(transitions)
    prev_dn_str = build_dn_string(transitions)
    fields["prev_up_str"] = prev_up_str
    fields["prev_dn_str"] = prev_dn_str

    d_transition = fields["period_transition_d"]
    buy_full = prev_up_str == "YQMWD" and d_transition == "volume_up"
    sell_full = prev_dn_str.lower() == "yqmwd" and d_transition == "low_volume_down"
    oversold_hint = detect_oversold_hint_condition(prev_up_str, transitions)
    overbought_hint = detect_overbought_hint_condition(prev_dn_str, transitions)
    necessary = {
        "buy_necessary_base": bool(buy_periods),
        "buy_necessary_key": f"BUY:{','.join(buy_periods)}" if buy_periods else None,
        "buy_necessary_periods": buy_periods,
        "sell_necessary_base": bool(sell_periods),
        "sell_necessary_key": f"SELL:{','.join(sell_periods)}" if sell_periods else None,
        "sell_necessary_periods": sell_periods,
        "buy_full_necessary_base": buy_full,
        "buy_full_necessary_key": "BUY:FULL" if buy_full else None,
        "sell_full_necessary_base": sell_full,
        "sell_full_necessary_key": "SELL:FULL" if sell_full else None,
        "oversold_hint_necessary_base": oversold_hint,
        "oversold_hint_key": "BUY_HINT" if oversold_hint else None,
        "overbought_hint_necessary_base": overbought_hint,
        "overbought_hint_key": "SELL_HINT" if overbought_hint else None,
    }
    fields.update(necessary)
    fields.update(compute_static_structure_fields(period_context))
    fields["period_trigger_baseline_json"] = build_period_trigger_baseline_json(period_context)
    fields["amount_quality_status"] = "passed" if amount_baseline_complete else "warning"
    fields["amount_baseline_complete"] = amount_baseline_complete
    fields["condition_calculation_version"] = "N2-R-target-parity-v1"
    return fields


def compute_level_scores_from_transitions(transitions: Mapping[str, Any]) -> dict[str, int]:
    """Encode Y/Q/M/W/D transition grades into up/down five-base ordering scores."""
    return {
        "level_up_score": transition_score(transitions, LEVEL_UP_TRANSITION_RANK),
        "level_down_score": transition_score(transitions, LEVEL_DOWN_TRANSITION_RANK),
    }


def transition_score(transitions: Mapping[str, Any], rank_map: Mapping[str, int]) -> int:
    score = 0
    for period in PERIODS:
        transition = str(transitions.get(period) or "flat")
        score = score * 5 + int(rank_map.get(transition, rank_map["flat"]))
    return score


def build_up_string(transitions: Mapping[str, str]) -> str:
    return "".join(period if transitions.get(period) == "volume_up" else "-" for period in PERIODS)


def build_dn_string(transitions: Mapping[str, str]) -> str:
    marks = {"Y": "y", "Q": "q", "M": "m", "W": "w", "D": "d"}
    return "".join(marks[period] if transitions.get(period) == "low_volume_down" else "-" for period in PERIODS)


def find_smallest_trend_period(up_str: str) -> str | None:
    if len(up_str or "") < 5:
        return None
    mapping = {"Y": up_str[0], "Q": up_str[1], "M": up_str[2], "W": up_str[3], "D": up_str[4]}
    for period in ("W", "M", "Q", "Y"):
        if mapping.get(period) != "-":
            return period
    return None


def find_smallest_down_period(dn_str: str) -> str | None:
    if len(dn_str or "") < 5:
        return None
    mapping = {"Y": dn_str[0], "Q": dn_str[1], "M": dn_str[2], "W": dn_str[3], "D": dn_str[4]}
    for period in ("W", "M", "Q", "Y"):
        if mapping.get(period) != "-":
            return period
    return None


def small_periods_below(anchor: str) -> list[str]:
    order = ["D", "W", "M", "Q", "Y"]
    if anchor not in order:
        return []
    return order[: order.index(anchor)]


def detect_oversold_hint_condition(prev_up_str: str, transitions: Mapping[str, str]) -> bool:
    anchor = find_smallest_trend_period(prev_up_str)
    if not anchor:
        return False
    periods = small_periods_below(anchor)
    if not periods:
        return False
    return all(transitions.get(period) in DOWN_GRADES for period in periods)


def detect_overbought_hint_condition(prev_dn_str: str, transitions: Mapping[str, str]) -> bool:
    anchor = find_smallest_down_period(prev_dn_str)
    if not anchor:
        return False
    periods = small_periods_below(anchor)
    if not periods:
        return False
    return all(transitions.get(period) in UP_GRADES for period in periods)


def build_period_trigger_baseline_json(period_context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "baseline_version": PERIOD_TRIGGER_BASELINE_VERSION,
        "baseline_source": "condition_basis",
        "amount_metric_rule": {
            "D": "amount",
            "W/M/Q/Y": "avg_amount",
        },
        "periods": {
            period: period_trigger_baseline_entry(period, period_context.get(period, {}))
            for period in PERIODS
        },
    }


def period_trigger_baseline_entry(period: str, period_node: Mapping[str, Any]) -> dict[str, Any]:
    current = period_node.get("current")
    previous = period_node.get("previous")
    previous_open = decimal_or_none(None if previous is None else previous.get("open"))
    previous_close = decimal_or_none(None if previous is None else previous.get("close"))
    if previous_open is not None and previous_close is not None:
        previous_entity_high = max(previous_open, previous_close)
        previous_entity_low = min(previous_open, previous_close)
    else:
        previous_entity_high = None
        previous_entity_low = None
    amount_metric = "amount" if period == "D" else "avg_amount"
    missing_fields = period_trigger_baseline_missing_fields(
        previous_entity_high=previous_entity_high,
        previous_entity_low=previous_entity_low,
        previous_amount=decimal_or_none(None if previous is None else previous.get("amount")),
        previous_avg_amount=decimal_or_none(None if previous is None else previous.get("avg_amount")),
        amount_metric=amount_metric,
    )
    return {
        "period": period,
        "calculable": current is not None and previous is not None,
        "baseline_ready": not missing_fields,
        "baseline_missing_fields": missing_fields,
        "period_key_current": None if current is None else current.get("period_key"),
        "period_key_previous": None if previous is None else previous.get("period_key"),
        "period_grade": period_node.get("grade"),
        "period_transition": period_node.get("transition"),
        "current_open_seed": decimal_text_from_mapping(current, "open"),
        "current_close_seed": decimal_text_from_mapping(current, "close"),
        "current_amount_seed": decimal_text_from_mapping(current, "amount"),
        "current_avg_amount_seed": decimal_text_from_mapping(current, "avg_amount"),
        "current_amount_total_seed": decimal_text_from_mapping(current, "amount_total"),
        "current_trade_days_seed": None if current is None else current.get("day_count"),
        "previous_open": decimal_text_from_mapping(previous, "open"),
        "previous_close": decimal_text_from_mapping(previous, "close"),
        "previous_entity_high": decimal_to_string(previous_entity_high),
        "previous_entity_low": decimal_to_string(previous_entity_low),
        "previous_amount": decimal_text_from_mapping(previous, "amount"),
        "previous_avg_amount": decimal_text_from_mapping(previous, "avg_amount"),
        "previous_amount_total": decimal_text_from_mapping(previous, "amount_total"),
        "amount_metric": amount_metric,
        "current_window_start": None if current is None else current.get("start_trade_date"),
        "current_window_end": None if current is None else current.get("end_trade_date"),
        "previous_window_start": None if previous is None else previous.get("start_trade_date"),
        "previous_window_end": None if previous is None else previous.get("end_trade_date"),
    }


def period_trigger_baseline_missing_fields(
    *,
    previous_entity_high: Any,
    previous_entity_low: Any,
    previous_amount: Any,
    previous_avg_amount: Any,
    amount_metric: str,
) -> list[str]:
    missing: list[str] = []
    if previous_entity_high in (None, ""):
        missing.append("previous_entity_high")
    if previous_entity_low in (None, ""):
        missing.append("previous_entity_low")
    if amount_metric == "amount":
        if previous_amount in (None, ""):
            missing.append("previous_amount")
    elif previous_avg_amount in (None, ""):
        missing.append("previous_avg_amount")
    return missing


def decimal_text_from_mapping(row: Mapping[str, Any] | None, key: str) -> str | None:
    return None if row is None else decimal_to_string(decimal_or_none(row.get(key)))


def compute_static_structure_fields(period_context: Mapping[str, Any]) -> dict[str, Any]:
    fields = empty_static_structure_fields()
    up_runs = find_anchor_runs(period_context, "volume_up")
    if up_runs:
        fields.update(compute_up_static_fields(period_context, up_runs[0]))
        if len(up_runs) > 1:
            secondary_side = symmetry_target_side_values(period_context, up_runs[1], "buy")
            fields["_secondary_buy_target_side"] = secondary_side
            fields.update(compute_secondary_static_fields(period_context, secondary_side, "buy"))
    down_runs = find_anchor_runs(period_context, "low_volume_down")
    if down_runs:
        fields.update(compute_down_static_fields(period_context, down_runs[0]))
        if len(down_runs) > 1:
            secondary_side = symmetry_target_side_values(period_context, down_runs[1], "sell")
            fields["_secondary_sell_target_side"] = secondary_side
            fields.update(compute_secondary_static_fields(period_context, secondary_side, "sell"))
    fields["up_sell_reference_period"] = compute_up_sell_reference_period(
        period_context,
        fields.get("main_up_anchor"),
        fields.get("up_reference_period"),
    )
    fields["down_buy_reference_period"] = compute_down_buy_reference_period(
        period_context,
        fields.get("main_down_anchor"),
        fields.get("down_reference_period"),
    )
    # Compatibility alias until N5 consumes up_sell_reference_period directly.
    fields["clear_sell_ref_period"] = fields["up_sell_reference_period"]
    fields.update(canonical_target_fields_for_direction(fields, "buy"))
    return fields


def find_anchor_runs(period_context: Mapping[str, Any], grade: str) -> list[list[str]]:
    runs: list[list[str]] = []
    current_run: list[str] = []
    for period in STATIC_ANCHOR_PERIODS:
        period_grade_value = str(period_context.get(period, {}).get("transition") or "unknown")
        if period_grade_value == grade:
            current_run.append(period)
            continue
        if current_run:
            runs.append(current_run)
            current_run = []
    if current_run:
        runs.append(current_run)
    return runs


def find_anchor_run(period_context: Mapping[str, Any], grade: str) -> list[str]:
    runs = find_anchor_runs(period_context, grade)
    return runs[0] if runs else []


def compute_up_static_fields(period_context: Mapping[str, Any], run: list[str]) -> dict[str, Any]:
    side = symmetry_target_side_values(period_context, run, "buy")
    current_close = current_day_close(period_context)
    buy_target_price = decimal_or_none(side["target_price"])
    return {
        "_primary_buy_target_side": side,
        "main_up_anchor": side["anchor"],
        "up_reference_period": side["reference_period"],
        "up_amplitude": side["amplitude"],
        "up_base_price": side["base_price"],
        "buy_target_price": side["target_price"],
        "buy_expected_return_pct": decimal_to_string(expected_up_return_pct(current_close, buy_target_price)),
        "up_trend_start_date": side["segment_start_date"],
        "up_trend_end_date": side["segment_end_date"],
        "up_segment_high": side["segment_high"],
        "up_segment_low": side["segment_low"],
        "up_trend_break_date": side["trend_break_date"],
        "up_reference_window_start": side["base_window_start"],
        "up_reference_window_end": side["base_window_end"],
    }


def compute_down_static_fields(period_context: Mapping[str, Any], run: list[str]) -> dict[str, Any]:
    side = symmetry_target_side_values(period_context, run, "sell")
    current_close = current_day_close(period_context)
    sell_target_price = decimal_or_none(side["target_price"])
    return {
        "_primary_sell_target_side": side,
        "main_down_anchor": side["anchor"],
        "down_reference_period": side["reference_period"],
        "down_amplitude": side["amplitude"],
        "down_base_price": side["base_price"],
        "sell_target_price": side["target_price"],
        "sell_expected_return_pct": decimal_to_string(expected_down_return_pct(current_close, sell_target_price)),
        "down_trend_start_date": side["segment_start_date"],
        "down_trend_end_date": side["segment_end_date"],
        "down_segment_high": side["segment_high"],
        "down_segment_low": side["segment_low"],
        "down_trend_break_date": side["trend_break_date"],
        "down_reference_window_start": side["base_window_start"],
        "down_reference_window_end": side["base_window_end"],
    }


def compute_secondary_static_fields(
    period_context: Mapping[str, Any],
    side: Mapping[str, Any],
    direction: str,
) -> dict[str, Any]:
    current_close = current_day_close(period_context)
    raw_target_price = side.get("target_price")
    stored_target_price = raw_target_price
    warning_reason = None
    if direction == "sell":
        stored_target_price, warning_reason = normalized_down_secondary_target_price(raw_target_price)
    target_price = decimal_or_none(stored_target_price)
    if direction == "sell":
        prefix = "down_secondary"
        expected_return = expected_down_return_pct(current_close, target_price)
    else:
        prefix = "up_secondary"
        expected_return = expected_up_return_pct(current_close, target_price)
    fields = {
        f"{prefix}_anchor": side.get("anchor"),
        f"{prefix}_reference_period": side.get("reference_period"),
        f"{prefix}_trend_start_date": side.get("segment_start_date"),
        f"{prefix}_trend_end_date": side.get("segment_end_date"),
        f"{prefix}_amplitude": side.get("amplitude"),
        f"{prefix}_base_price": side.get("base_price"),
        f"{prefix}_target_price": stored_target_price,
        f"{prefix}_expected_return_pct": decimal_to_string(expected_return),
    }
    if direction == "sell" and warning_reason is not None:
        fields["_down_secondary_target_price_raw_candidate"] = raw_target_price
        fields["_down_secondary_target_price_warning_reason"] = warning_reason
    return fields


def normalized_down_secondary_target_price(value: Any) -> tuple[str | None, str | None]:
    if value in (None, ""):
        return None, None
    try:
        decimal_value = decimal_or_none(value)
    except (InvalidOperation, ValueError):
        return None, DOWN_SECONDARY_TARGET_PRICE_INVALID_REASON
    if decimal_value is None:
        return None, None
    if not decimal_value.is_finite():
        return None, DOWN_SECONDARY_TARGET_PRICE_INVALID_REASON
    if decimal_value <= Decimal("0"):
        return None, DOWN_SECONDARY_TARGET_PRICE_NON_POSITIVE_REASON
    return decimal_to_string(decimal_value), None


def symmetry_target_side_values(period_context: Mapping[str, Any], run: list[str], direction: str) -> dict[str, Any]:
    main_anchor = run[-1]
    reference_period = LOWER_PERIOD[main_anchor]
    segment = symmetry_target_segment(period_context, main_anchor, direction)
    reference_window = symmetry_reference_window(period_context, direction=direction, reference_period=reference_period)
    amplitude = segment["amplitude"]
    base_price = reference_window["base_price"]
    if direction == "sell":
        target_price = base_price - amplitude if base_price is not None and amplitude is not None else None
    else:
        target_price = base_price + amplitude if base_price is not None and amplitude is not None else None
    return {
        "direction": direction,
        "anchor": main_anchor,
        "amplitude_source_period": canonical_symmetry_period(main_anchor),
        "amplitude": decimal_to_string(amplitude),
        "base_price": decimal_to_string(base_price),
        "target_price": decimal_to_string(target_price),
        "reference_period": reference_period,
        "segment_start_date": segment["segment_start_date"],
        "segment_end_date": segment["segment_end_date"],
        "segment_high": decimal_to_string(segment["segment_high"]),
        "segment_low": decimal_to_string(segment["segment_low"]),
        "segment_high_date": segment.get("segment_high_date"),
        "segment_low_date": segment.get("segment_low_date"),
        "segment_high_raw_open": decimal_to_string(segment.get("segment_high_raw_open")),
        "segment_high_raw_close": decimal_to_string(segment.get("segment_high_raw_close")),
        "segment_high_adj_factor": decimal_to_string(segment.get("segment_high_adj_factor")),
        "segment_low_raw_open": decimal_to_string(segment.get("segment_low_raw_open")),
        "segment_low_raw_close": decimal_to_string(segment.get("segment_low_raw_close")),
        "segment_low_adj_factor": decimal_to_string(segment.get("segment_low_adj_factor")),
        "amplitude_price_policy": SYMMETRY_TARGET_AMPLITUDE_PRICE_POLICY,
        "adjustment_policy": segment["adjustment_policy"],
        "current_adj_factor": decimal_to_string(segment["current_adj_factor"]),
        "trend_break_date": reference_window["trend_break_date"],
        "base_window_start": reference_window["base_window_start"],
        "base_window_end": reference_window["base_window_end"],
    }


def symmetry_target_segment(period_context: Mapping[str, Any], main_anchor: str, direction: str) -> dict[str, Any]:
    target_grade = "low_volume_down" if direction == "sell" else "volume_up"
    segment_window = current_anchor_period_segment_window(period_context, main_anchor, target_grade)
    parent_period = symmetry_segment_parent_period(main_anchor)
    parent_current = period_context.get(parent_period, {}).get("current") if parent_period else None
    source_current = period_context.get("D", {}).get("current")
    start_date = (
        segment_window["start_trade_date"]
        if segment_window
        else None if parent_current is None else parent_current.get("start_trade_date")
    )
    end_date = (
        segment_window["end_trade_date"]
        if segment_window
        else None if source_current is None else source_current.get("end_trade_date")
    )
    rows = daily_rows_between(period_context, start_date, end_date)
    current_adj_factor = current_adj_factor_for_daily_rows(rows)
    if rows:
        bounds = target_machine_adjusted_bound_details_for_daily_rows(rows)
        segment_high = bounds["segment_high"]
        segment_low = bounds["segment_low"]
    else:
        segment_high, segment_low = segment_bounds_for_run(period_context, [parent_period])
        bounds = {}
        current = period_context.get(parent_period, {}).get("current")
        start_date = None if current is None else current.get("start_trade_date")
        end_date = None if current is None else current.get("end_trade_date")
        current_adj_factor = None
    amplitude = segment_high - segment_low if segment_high is not None and segment_low is not None else None
    return {
        "segment_start_date": start_date,
        "segment_end_date": end_date,
        "segment_high": segment_high,
        "segment_low": segment_low,
        "amplitude": amplitude,
        "segment_high_date": bounds.get("segment_high_date"),
        "segment_low_date": bounds.get("segment_low_date"),
        "segment_high_raw_open": bounds.get("segment_high_raw_open"),
        "segment_high_raw_close": bounds.get("segment_high_raw_close"),
        "segment_high_adj_factor": bounds.get("segment_high_adj_factor"),
        "segment_low_raw_open": bounds.get("segment_low_raw_open"),
        "segment_low_raw_close": bounds.get("segment_low_raw_close"),
        "segment_low_adj_factor": bounds.get("segment_low_adj_factor"),
        "adjustment_policy": SYMMETRY_TARGET_ADJUSTMENT_POLICY if current_adj_factor is not None else None,
        "current_adj_factor": current_adj_factor,
    }


def symmetry_segment_parent_period(main_anchor: str) -> str:
    if main_anchor == "W":
        return "M"
    if main_anchor == "M":
        return "Q"
    if main_anchor == "Q":
        return "Y"
    return "Y"


def current_anchor_period_segment_window(
    period_context: Mapping[str, Any],
    anchor_period: str,
    target_grade: str,
) -> dict[str, Any] | None:
    """Return the current continuing anchor-period segment window.

    The symmetric A segment must be measured on the anchor period itself. A
    weekly anchor, for example, is the current continuous run of weekly
    `volume_up` bars, not the enclosing monthly window.
    """
    rows = sorted_daily_rows(period_context)
    bars = aggregate_daily_rows_by_period(rows, anchor_period)
    if len(bars) < 2:
        return None
    previous_transition = "unknown"
    transitions: list[str] = []
    for index, bar in enumerate(bars):
        previous = bars[index - 1] if index > 0 else None
        grade = period_grade(bar, previous)
        transition = transition_grade(anchor_period, grade, previous_transition, bar)
        transitions.append(transition)
        previous_transition = transition
    current_index = len(bars) - 1
    if transitions[current_index] != target_grade:
        return None
    start_index = current_index
    while start_index > 0 and transitions[start_index - 1] == target_grade:
        start_index -= 1
    return {
        "start_trade_date": bars[start_index].get("start_trade_date"),
        "end_trade_date": bars[current_index].get("end_trade_date"),
    }


def aggregate_daily_rows_by_period(rows: Iterable[Mapping[str, Any]], period: str) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    order: list[str] = []
    for row in sorted(rows, key=lambda item: str(item.get("trade_date") or "")):
        trade_date = str(row.get("trade_date") or "")
        if not trade_date:
            continue
        key = period_key(period, trade_date)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)
    bars: list[dict[str, Any]] = []
    for key in order:
        period_rows = groups[key]
        amounts = [decimal_or_none(row.get("amount")) for row in period_rows]
        valid_amounts = [amount for amount in amounts if amount is not None]
        amount_total = sum(valid_amounts, Decimal("0")) if valid_amounts else None
        avg_amount = amount_total / Decimal(len(valid_amounts)) if amount_total is not None and valid_amounts else None
        bars.append(
            {
                "period_key": key,
                "start_trade_date": period_rows[0].get("trade_date"),
                "end_trade_date": period_rows[-1].get("trade_date"),
                "open": period_rows[0].get("open"),
                "high": max_decimal(row.get("high") for row in period_rows),
                "low": min_decimal(row.get("low") for row in period_rows),
                "close": period_rows[-1].get("close"),
                "amount": amount_total if period == "D" else avg_amount,
                "avg_amount": avg_amount,
                "amount_total": amount_total,
                "day_count": len(period_rows),
            }
        )
    return bars


def max_decimal(values: Iterable[Any]) -> Decimal | None:
    decimals = [decimal_or_none(value) for value in values]
    valid = [value for value in decimals if value is not None]
    return max(valid) if valid else None


def min_decimal(values: Iterable[Any]) -> Decimal | None:
    decimals = [decimal_or_none(value) for value in values]
    valid = [value for value in decimals if value is not None]
    return min(valid) if valid else None


def symmetry_reference_window(period_context: Mapping[str, Any], *, direction: str, reference_period: str) -> dict[str, Any]:
    rows = sorted_daily_rows(period_context)
    source_current = period_context.get("D", {}).get("current")
    source_date = None if source_current is None else source_current.get("end_trade_date")
    if source_date is None and rows:
        source_date = rows[-1].get("trade_date")
    trend_break_date = latest_completed_reference_segment_end(
        rows,
        direction=direction,
        source_date=source_date,
        reference_period=reference_period,
    )
    window_rows: list[Mapping[str, Any]] = []
    if trend_break_date:
        window_rows = [row for row in rows if str(row.get("trade_date") or "") > trend_break_date and str(row.get("trade_date") or "") <= str(source_date or "")]
    if not window_rows:
        current = period_context.get(reference_period, {}).get("current")
        start = None if current is None else current.get("start_trade_date")
        end = None if current is None else current.get("end_trade_date")
        window_rows = daily_rows_between(period_context, start, end)
    if not window_rows:
        reference = period_context.get(reference_period, {}).get("current")
        base_key = "max_close" if direction == "sell" else "min_close"
        return {
            "trend_break_date": trend_break_date,
            "base_window_start": None if reference is None else reference.get("start_trade_date"),
            "base_window_end": None if reference is None else reference.get("end_trade_date"),
            "base_price": decimal_or_none(None if reference is None else reference.get(base_key)),
        }
    closes = [decimal_or_none(row.get("close")) for row in window_rows]
    valid_closes = [value for value in closes if value is not None]
    if not valid_closes:
        base_price = None
    elif direction == "sell":
        base_price = max(valid_closes)
    else:
        base_price = min(valid_closes)
    return {
        "trend_break_date": trend_break_date,
        "base_window_start": window_rows[0].get("trade_date"),
        "base_window_end": window_rows[-1].get("trade_date"),
        "base_price": base_price,
    }


def latest_completed_reference_segment_end(
    rows: list[Mapping[str, Any]],
    *,
    direction: str,
    source_date: Any,
    reference_period: str,
) -> str | None:
    if len(rows) < 2:
        return None
    source_text = str(source_date or rows[-1].get("trade_date") or "")
    eligible = [row for row in rows if str(row.get("trade_date") or "") <= source_text]
    bars = aggregate_daily_rows_by_period(eligible, reference_period)
    if len(bars) < 2:
        return None
    target_grade = "low_volume_down" if direction == "sell" else "volume_up"
    completed_run_ends: list[str] = []
    current_run_end: str | None = None
    current_run_reaches_source = False
    previous_transition = "unknown"
    for index, bar in enumerate(bars):
        previous = bars[index - 1] if index > 0 else None
        grade = period_grade(bar, previous)
        transition = transition_grade(reference_period, grade, previous_transition, bar)
        previous_transition = transition
        if transition == target_grade:
            current_run_end = str(bar.get("end_trade_date") or "")
            current_run_reaches_source = current_run_reaches_source or bar_contains_source_date(bar, source_text)
            continue
        if current_run_end and not current_run_reaches_source:
            completed_run_ends.append(current_run_end)
        current_run_end = None
        current_run_reaches_source = False
    if current_run_end and not current_run_reaches_source:
        completed_run_ends.append(current_run_end)
    return completed_run_ends[-1] if completed_run_ends else None


def bar_contains_source_date(bar: Mapping[str, Any], source_text: str) -> bool:
    start = str(bar.get("start_trade_date") or "")
    end = str(bar.get("end_trade_date") or "")
    return bool(start and end and start <= source_text <= end)


def latest_completed_lower_segment_end(
    rows: list[Mapping[str, Any]],
    *,
    direction: str,
    source_date: Any,
) -> str | None:
    if len(rows) < 2:
        return None
    source_text = str(source_date or rows[-1].get("trade_date") or "")
    eligible = [row for row in rows if str(row.get("trade_date") or "") <= source_text]
    if len(eligible) < 2:
        return None
    target_grade = "low_volume_down" if direction == "sell" else "volume_up"
    completed_run_ends: list[str] = []
    current_run_end: str | None = None
    current_run_reaches_source = False
    for idx in range(1, len(eligible)):
        grade = daily_row_transition_grade(eligible[idx], eligible[idx - 1])
        trade_date = str(eligible[idx].get("trade_date") or "")
        if grade == target_grade:
            current_run_end = trade_date
            current_run_reaches_source = trade_date == source_text
            continue
        if current_run_end and not current_run_reaches_source:
            completed_run_ends.append(current_run_end)
        current_run_end = None
        current_run_reaches_source = False
    if current_run_end and not current_run_reaches_source:
        completed_run_ends.append(current_run_end)
    return completed_run_ends[-1] if completed_run_ends else None


def daily_row_transition_grade(current: Mapping[str, Any], previous: Mapping[str, Any]) -> str:
    return period_grade(
        {
            "close": current.get("close"),
            "amount": current.get("amount"),
        },
        {
            "open": previous.get("open"),
            "close": previous.get("close"),
            "amount": previous.get("amount"),
        },
    )


def daily_rows_between(period_context: Mapping[str, Any], start_date: Any, end_date: Any) -> list[Mapping[str, Any]]:
    if not start_date or not end_date:
        return []
    start = str(start_date)
    end = str(end_date)
    return [
        row for row in sorted_daily_rows(period_context)
        if start <= str(row.get("trade_date") or "") <= end
    ]


def sorted_daily_rows(period_context: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = period_context.get("_daily_rows") or []
    return sorted(
        [row for row in rows if isinstance(row, Mapping) and row.get("trade_date")],
        key=lambda row: str(row.get("trade_date") or ""),
    )


def target_machine_adjusted_bounds_for_daily_rows(rows: Iterable[Mapping[str, Any]]) -> tuple[Decimal | None, Decimal | None]:
    details = target_machine_adjusted_bound_details_for_daily_rows(rows)
    return details["segment_high"], details["segment_low"]


def target_machine_adjusted_bound_details_for_daily_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    row_list = list(rows)
    current_adj_factor = current_adj_factor_for_daily_rows(row_list)
    high_entry: dict[str, Any] | None = None
    low_entry: dict[str, Any] | None = None
    for row in row_list:
        open_price = target_machine_boundary_price(row, "open", current_adj_factor)
        close_price = target_machine_boundary_price(row, "close", current_adj_factor)
        if open_price is None or close_price is None:
            continue
        row_high = max(open_price, close_price)
        row_low = min(open_price, close_price)
        if high_entry is None or row_high > high_entry["value"]:
            high_entry = target_machine_bound_entry(row, row_high)
        if low_entry is None or row_low < low_entry["value"]:
            low_entry = target_machine_bound_entry(row, row_low)
    return {
        "segment_high": None if high_entry is None else high_entry["value"],
        "segment_low": None if low_entry is None else low_entry["value"],
        "segment_high_date": None if high_entry is None else high_entry["trade_date"],
        "segment_low_date": None if low_entry is None else low_entry["trade_date"],
        "segment_high_raw_open": None if high_entry is None else high_entry["raw_open"],
        "segment_high_raw_close": None if high_entry is None else high_entry["raw_close"],
        "segment_high_adj_factor": None if high_entry is None else high_entry["adj_factor"],
        "segment_low_raw_open": None if low_entry is None else low_entry["raw_open"],
        "segment_low_raw_close": None if low_entry is None else low_entry["raw_close"],
        "segment_low_adj_factor": None if low_entry is None else low_entry["adj_factor"],
    }


def target_machine_boundary_price(
    row: Mapping[str, Any],
    field: str,
    current_adj_factor: Decimal | None,
) -> Decimal | None:
    raw_key = f"raw_{field}"
    if row.get(raw_key) not in (None, ""):
        return adjusted_price_to_current_factor(row.get(raw_key), row, current_adj_factor)
    price_decimal = decimal_or_none(row.get(field))
    if price_decimal is None:
        return None
    if row.get("current_adj_factor") not in (None, "") or row.get("adjustment_policy") == SYMMETRY_TARGET_ADJUSTMENT_POLICY:
        return price_decimal.quantize(SYMMETRY_TARGET_PRICE_QUANT, rounding=ROUND_HALF_UP)
    return adjusted_price_to_current_factor(row.get(field), row, current_adj_factor)


def target_machine_bound_entry(row: Mapping[str, Any], value: Decimal) -> dict[str, Any]:
    return {
        "value": value,
        "trade_date": None if row.get("trade_date") in (None, "") else str(row.get("trade_date")),
        "raw_open": decimal_or_none(row.get("raw_open")),
        "raw_close": decimal_or_none(row.get("raw_close")),
        "adj_factor": decimal_or_none(row.get("adj_factor")),
    }


def current_adj_factor_for_daily_rows(rows: Iterable[Mapping[str, Any]]) -> Decimal | None:
    for row in reversed(sorted(rows, key=lambda item: str(item.get("trade_date") or ""))):
        adj_factor = decimal_or_none(row.get("adj_factor"))
        if adj_factor is not None and adj_factor > 0:
            return adj_factor
    return None


def adjusted_price_to_current_factor(
    price: Any,
    row: Mapping[str, Any],
    current_adj_factor: Decimal | None,
) -> Decimal | None:
    price_decimal = decimal_or_none(price)
    if price_decimal is None:
        return None
    row_adj_factor = decimal_or_none(row.get("adj_factor"))
    if (
        current_adj_factor is None
        or current_adj_factor <= 0
        or row_adj_factor is None
        or row_adj_factor <= 0
    ):
        return price_decimal
    return (price_decimal * row_adj_factor / current_adj_factor).quantize(
        SYMMETRY_TARGET_PRICE_QUANT,
        rounding=ROUND_HALF_UP,
    )


def entity_bounds_for_daily_rows(rows: Iterable[Mapping[str, Any]]) -> tuple[Decimal | None, Decimal | None]:
    return target_machine_adjusted_bounds_for_daily_rows(rows)


def amplitude_for_run(period_context: Mapping[str, Any], run: list[str]) -> Decimal | None:
    segment_high, segment_low = segment_bounds_for_run(period_context, run)
    if segment_high is None or segment_low is None:
        return None
    return segment_high - segment_low


def segment_bounds_for_run(period_context: Mapping[str, Any], run: list[str]) -> tuple[Decimal | None, Decimal | None]:
    highs = [
        decimal_or_none(period_context.get(period, {}).get("current", {}).get("high"))
        for period in run
    ]
    lows = [
        decimal_or_none(period_context.get(period, {}).get("current", {}).get("low"))
        for period in run
    ]
    valid_highs = [value for value in highs if value is not None]
    valid_lows = [value for value in lows if value is not None]
    if not valid_highs or not valid_lows:
        return None, None
    return max(valid_highs), min(valid_lows)


def current_day_close(period_context: Mapping[str, Any]) -> Decimal | None:
    return decimal_or_none(period_context.get("D", {}).get("current", {}).get("close"))


def canonical_target_fields_for_direction(row: Mapping[str, Any], direction: str | None = None) -> dict[str, Any]:
    """Map legacy N2 target fields into canonical 027 target fields.

    `condition_basis` has both buy and sell structures, while pool/scope rows
    are directional. The mapping keeps N2 as the owner of immutable target
    candidates and never emits user/position lock fields.
    """

    direction = (direction or str(row.get("direction") or "") or "buy").lower()
    if direction not in {"buy", "sell"}:
        direction = "buy" if row.get("buy_target_price") not in (None, "") else "sell"
    if direction == "sell" and row.get("sell_target_price") in (None, "") and row.get("buy_target_price") not in (None, ""):
        direction = "buy"
    if direction == "buy" and row.get("buy_target_price") in (None, "") and row.get("sell_target_price") not in (None, ""):
        direction = "sell"

    primary = target_side_values(row, direction)
    secondary = secondary_target_side_values(row, direction)
    down_secondary_warning = row.get("_down_secondary_target_price_warning_reason")
    down_secondary_raw_candidate = row.get("_down_secondary_target_price_raw_candidate")
    down_secondary = secondary_target_side_values(row, "sell") if down_secondary_warning else {}
    target_price_normalization = {}
    warnings = []
    if down_secondary_warning is not None:
        warnings.append(str(down_secondary_warning))
        target_price_normalization["down_secondary_target_price"] = {
            "raw_target_price": down_secondary_raw_candidate,
            "stored_target_price": row.get("down_secondary_target_price"),
            "reason": down_secondary_warning,
        }
    reference_target_price = nonnegative_decimal_text(primary["target_price"])
    secondary_target_price = nonnegative_decimal_text(secondary["target_price"])
    base_price = nonnegative_decimal_text(primary["base_price"])
    amplitude = nonnegative_decimal_text(primary["amplitude"])
    segment_high = nonnegative_decimal_text(primary["segment_high"])
    segment_low = nonnegative_decimal_text(primary["segment_low"])
    has_primary_target_context = any(value not in (None, "") for value in (reference_target_price, base_price, amplitude, primary["anchor"]))
    trace = {
        "version": SYMMETRY_TARGET_TRACE_VERSION,
        "primary_direction": direction if has_primary_target_context else None,
        "base_price_policy": SYMMETRY_TARGET_BASE_PRICE_POLICY if has_primary_target_context else None,
        "amplitude_price_policy": SYMMETRY_TARGET_AMPLITUDE_PRICE_POLICY if has_primary_target_context else None,
        "adjustment_policy": primary["adjustment_policy"] if has_primary_target_context else None,
        "primary": primary if has_primary_target_context else {},
        "compatibility_mapping": {
            "reference_target_price": f"{direction}_target_price" if reference_target_price not in (None, "") else None,
            "secondary_target_price": "secondary_target_price" if secondary_target_price not in (None, "") else None,
        },
        "buy": target_side_values(row, "buy"),
        "sell": target_side_values(row, "sell"),
        "secondary": secondary if secondary_target_price not in (None, "") else {},
        "secondary_anchor": secondary["anchor"] if secondary_target_price not in (None, "") else None,
        "secondary_target_price": secondary_target_price,
        "down_secondary": down_secondary,
        "target_price_normalization": target_price_normalization,
        "warnings": warnings,
        "legacy_alias": {
            "clear_sell_ref_period": row.get("clear_sell_ref_period"),
            "up_sell_reference_period": row.get("up_sell_reference_period"),
            "alias_match": row.get("clear_sell_ref_period") == row.get("up_sell_reference_period"),
        },
    }
    return {
        "symmetry_anchor": canonical_symmetry_period(primary["anchor"]),
        "secondary_symmetry_anchor": canonical_symmetry_period(secondary["anchor"]) if secondary_target_price not in (None, "") else None,
        "amplitude_source_period": canonical_symmetry_period(primary["amplitude_source_period"]),
        "a_segment_start_date": primary["segment_start_date"],
        "a_segment_end_date": primary["segment_end_date"],
        "a_segment_high": segment_high,
        "a_segment_low": segment_low,
        "a_segment_amplitude": amplitude,
        "base_price_policy": SYMMETRY_TARGET_BASE_PRICE_POLICY if has_primary_target_context else None,
        "base_price": base_price,
        "reference_target_price": reference_target_price,
        "secondary_target_price": secondary_target_price,
        "target_price_trace_json": trace,
    }


def secondary_target_side_values(row: Mapping[str, Any], direction: str) -> dict[str, Any]:
    side = row.get("_secondary_buy_target_side") if direction == "buy" else row.get("_secondary_sell_target_side")
    if isinstance(side, Mapping):
        return {
            "direction": side.get("direction") or direction,
            "anchor": side.get("anchor"),
            "amplitude_source_period": side.get("amplitude_source_period"),
            "amplitude": side.get("amplitude"),
            "base_price": side.get("base_price"),
            "target_price": side.get("target_price"),
            "reference_period": side.get("reference_period"),
            "later_reference_period": None,
            "segment_start_date": side.get("segment_start_date"),
            "segment_end_date": side.get("segment_end_date"),
            "segment_high": side.get("segment_high"),
            "segment_low": side.get("segment_low"),
            "segment_high_date": side.get("segment_high_date"),
            "segment_low_date": side.get("segment_low_date"),
            "segment_high_raw_open": side.get("segment_high_raw_open"),
            "segment_high_raw_close": side.get("segment_high_raw_close"),
            "segment_high_adj_factor": side.get("segment_high_adj_factor"),
            "segment_low_raw_open": side.get("segment_low_raw_open"),
            "segment_low_raw_close": side.get("segment_low_raw_close"),
            "segment_low_adj_factor": side.get("segment_low_adj_factor"),
            "amplitude_price_policy": side.get("amplitude_price_policy"),
            "adjustment_policy": side.get("adjustment_policy"),
            "current_adj_factor": side.get("current_adj_factor"),
            "trend_break_date": side.get("trend_break_date"),
            "base_window_start": side.get("base_window_start"),
            "base_window_end": side.get("base_window_end"),
            "expected_return_pct": None,
        }
    trace = row.get("target_price_trace_json")
    if isinstance(trace, Mapping):
        secondary = trace.get("secondary")
        if isinstance(secondary, Mapping):
            values = empty_target_side_values(direction)
            values.update(dict(secondary))
            return values
    prefix = "up_secondary" if direction == "buy" else "down_secondary"
    if any(row.get(f"{prefix}_{field}") not in (None, "") for field in ("anchor", "target_price", "amplitude", "base_price")):
        return {
            "direction": direction,
            "anchor": row.get(f"{prefix}_anchor"),
            "amplitude_source_period": canonical_symmetry_period(row.get(f"{prefix}_anchor")),
            "amplitude": row.get(f"{prefix}_amplitude"),
            "base_price": row.get(f"{prefix}_base_price"),
            "target_price": row.get(f"{prefix}_target_price"),
            "reference_period": row.get(f"{prefix}_reference_period"),
            "later_reference_period": None,
            "segment_start_date": row.get(f"{prefix}_trend_start_date"),
            "segment_end_date": row.get(f"{prefix}_trend_end_date"),
            "segment_high": None,
            "segment_low": None,
            "amplitude_price_policy": SYMMETRY_TARGET_AMPLITUDE_PRICE_POLICY,
            "adjustment_policy": None,
            "current_adj_factor": None,
            "trend_break_date": None,
            "base_window_start": None,
            "base_window_end": None,
            "expected_return_pct": row.get(f"{prefix}_expected_return_pct"),
        }
    return empty_target_side_values(direction)


def empty_target_side_values(direction: str) -> dict[str, Any]:
    return {
        "direction": direction,
        "anchor": None,
        "amplitude_source_period": None,
        "amplitude": None,
        "base_price": None,
        "target_price": None,
        "reference_period": None,
        "later_reference_period": None,
        "segment_start_date": None,
        "segment_end_date": None,
        "segment_high": None,
        "segment_low": None,
        "segment_high_date": None,
        "segment_low_date": None,
        "segment_high_raw_open": None,
        "segment_high_raw_close": None,
        "segment_high_adj_factor": None,
        "segment_low_raw_open": None,
        "segment_low_raw_close": None,
        "segment_low_adj_factor": None,
        "amplitude_price_policy": SYMMETRY_TARGET_AMPLITUDE_PRICE_POLICY,
        "adjustment_policy": None,
        "current_adj_factor": None,
        "trend_break_date": None,
        "base_window_start": None,
        "base_window_end": None,
        "expected_return_pct": None,
    }


def target_side_values(row: Mapping[str, Any], direction: str) -> dict[str, Any]:
    side = row.get("_primary_sell_target_side") if direction == "sell" else row.get("_primary_buy_target_side")
    if isinstance(side, Mapping):
        return {
            "direction": side.get("direction") or direction,
            "anchor": side.get("anchor"),
            "amplitude_source_period": side.get("amplitude_source_period"),
            "amplitude": side.get("amplitude"),
            "base_price": side.get("base_price"),
            "target_price": side.get("target_price"),
            "reference_period": side.get("reference_period"),
            "later_reference_period": None,
            "segment_start_date": side.get("segment_start_date"),
            "segment_end_date": side.get("segment_end_date"),
            "segment_high": side.get("segment_high"),
            "segment_low": side.get("segment_low"),
            "segment_high_date": side.get("segment_high_date"),
            "segment_low_date": side.get("segment_low_date"),
            "segment_high_raw_open": side.get("segment_high_raw_open"),
            "segment_high_raw_close": side.get("segment_high_raw_close"),
            "segment_high_adj_factor": side.get("segment_high_adj_factor"),
            "segment_low_raw_open": side.get("segment_low_raw_open"),
            "segment_low_raw_close": side.get("segment_low_raw_close"),
            "segment_low_adj_factor": side.get("segment_low_adj_factor"),
            "amplitude_price_policy": side.get("amplitude_price_policy"),
            "adjustment_policy": side.get("adjustment_policy"),
            "current_adj_factor": side.get("current_adj_factor"),
            "trend_break_date": side.get("trend_break_date"),
            "base_window_start": side.get("base_window_start"),
            "base_window_end": side.get("base_window_end"),
            "expected_return_pct": None,
        }
    if direction == "sell":
        return {
            "direction": "sell",
            "anchor": row.get("main_down_anchor"),
            "amplitude_source_period": canonical_symmetry_period(row.get("main_down_anchor")),
            "amplitude": row.get("down_amplitude"),
            "base_price": row.get("down_base_price"),
            "target_price": row.get("sell_target_price"),
            "reference_period": row.get("down_reference_period"),
            "later_reference_period": row.get("down_buy_reference_period"),
            "segment_start_date": row.get("down_trend_start_date"),
            "segment_end_date": row.get("down_trend_end_date"),
            "segment_high": row.get("down_segment_high"),
            "segment_low": row.get("down_segment_low"),
            "amplitude_price_policy": SYMMETRY_TARGET_AMPLITUDE_PRICE_POLICY,
            "adjustment_policy": None,
            "current_adj_factor": None,
            "trend_break_date": row.get("down_trend_break_date"),
            "base_window_start": row.get("down_reference_window_start"),
            "base_window_end": row.get("down_reference_window_end"),
            "expected_return_pct": row.get("sell_expected_return_pct"),
        }
    return {
        "direction": "buy",
        "anchor": row.get("main_up_anchor"),
        "amplitude_source_period": canonical_symmetry_period(row.get("main_up_anchor")),
        "amplitude": row.get("up_amplitude"),
        "base_price": row.get("up_base_price"),
        "target_price": row.get("buy_target_price"),
        "reference_period": row.get("up_reference_period"),
        "later_reference_period": row.get("up_sell_reference_period"),
        "segment_start_date": row.get("up_trend_start_date"),
        "segment_end_date": row.get("up_trend_end_date"),
        "segment_high": row.get("up_segment_high"),
        "segment_low": row.get("up_segment_low"),
        "amplitude_price_policy": SYMMETRY_TARGET_AMPLITUDE_PRICE_POLICY,
        "adjustment_policy": None,
        "current_adj_factor": None,
        "trend_break_date": row.get("up_trend_break_date"),
        "base_window_start": row.get("up_reference_window_start"),
        "base_window_end": row.get("up_reference_window_end"),
        "expected_return_pct": row.get("buy_expected_return_pct"),
    }


def canonical_symmetry_period(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text if text in SYMMETRY_TARGET_PERIODS else None


def nonnegative_decimal_text(value: Any) -> str | None:
    decimal_value = decimal_or_none(value)
    if decimal_value is None or decimal_value < 0:
        return None
    return decimal_to_string(decimal_value)


def expected_up_return_pct(current_close: Decimal | None, target_price: Decimal | None) -> Decimal | None:
    if current_close in (None, Decimal("0")) or target_price is None:
        return None
    return ((target_price - current_close) / current_close) * Decimal("100")


def expected_down_return_pct(current_close: Decimal | None, target_price: Decimal | None) -> Decimal | None:
    if current_close in (None, Decimal("0")) or target_price is None:
        return None
    return ((current_close - target_price) / current_close) * Decimal("100")


def trend_start_date(period_context: Mapping[str, Any], run: list[str]) -> Any:
    if not run:
        return None
    current = period_context.get(run[0], {}).get("current")
    return None if current is None else current.get("start_trade_date")


def trend_end_date(period_context: Mapping[str, Any], run: list[str]) -> Any:
    if not run:
        return None
    current = period_context.get(run[-1], {}).get("current")
    return None if current is None else current.get("end_trade_date")


def compute_reference_period_by_grade(
    period_context: Mapping[str, Any],
    main_anchor: Any,
    grades: frozenset[str],
) -> str | None:
    if not main_anchor:
        return None
    start_period = LOWER_PERIOD.get(str(main_anchor))
    if start_period is None:
        return None
    start_index = PERIODS.index(start_period)
    for period in PERIODS[start_index:]:
        grade = str(period_context.get(period, {}).get("transition") or "unknown")
        if grade in grades:
            return period
    return None


def fallback_static_reference_period(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip().upper()
        if text in PERIODS:
            return text
    return "D"


def compute_up_sell_reference_period(
    period_context: Mapping[str, Any],
    main_up_anchor: Any,
    up_reference_period: Any = None,
) -> str:
    computed = compute_reference_period_by_grade(period_context, main_up_anchor, RISK_GRADES)
    return fallback_static_reference_period(computed, up_reference_period, main_up_anchor, "D")


def compute_down_buy_reference_period(
    period_context: Mapping[str, Any],
    main_down_anchor: Any,
    down_reference_period: Any = None,
) -> str:
    computed = compute_reference_period_by_grade(period_context, main_down_anchor, OPPORTUNITY_GRADES)
    return fallback_static_reference_period(computed, down_reference_period, main_down_anchor, "D")


def compute_clear_sell_ref_period(period_context: Mapping[str, Any], main_up_anchor: Any) -> str:
    return compute_up_sell_reference_period(period_context, main_up_anchor)


def decimal_to_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def static_structure_complete(fields: Mapping[str, Any]) -> bool:
    return all(
        fields.get(field) not in (None, "")
        for field in (
            "main_up_anchor",
            "up_reference_period",
            "up_amplitude",
            "up_base_price",
            "buy_target_price",
            "main_down_anchor",
            "down_reference_period",
            "down_amplitude",
            "down_base_price",
            "sell_target_price",
            "up_sell_reference_period",
            "down_buy_reference_period",
            "clear_sell_ref_period",
        )
    )


def set_amount_fields(
    fields: dict[str, Any],
    period: str,
    current: Mapping[str, Any] | None,
    previous: Mapping[str, Any] | None,
) -> None:
    current_amount = None if current is None else current.get("amount")
    previous_amount = None if previous is None else previous.get("amount")
    if period == "Y":
        fields["amount_year"] = current_amount
        fields["amount_prev_year"] = previous_amount
    elif period == "Q":
        fields["amount_quarter"] = current_amount
        fields["amount_prev_quarter"] = previous_amount
    elif period == "M":
        fields["amount_month"] = current_amount
        fields["amount_prev_month"] = previous_amount
    elif period == "W":
        fields["amount_week"] = current_amount
        fields["amount_prev_week"] = previous_amount
    elif period == "D":
        fields["amount_day"] = current_amount
        fields["amount_prev_day"] = previous_amount
    else:
        raise ValueError(f"unsupported amount period: {period!r}")


def summarize_basis_rows(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    necessary_counts = {
        "ordinary_buy_objects": sum(1 for row in rows if row.get("buy_necessary_base")),
        "ordinary_sell_objects": sum(1 for row in rows if row.get("sell_necessary_base")),
        "buy_full_objects": sum(1 for row in rows if row.get("buy_full_necessary_base")),
        "sell_full_objects": sum(1 for row in rows if row.get("sell_full_necessary_base")),
        "buy_hint_objects": sum(1 for row in rows if row.get("oversold_hint_necessary_base")),
        "sell_hint_objects": sum(1 for row in rows if row.get("overbought_hint_necessary_base")),
    }
    grade_counts = {
        period: count_values(rows, f"period_grade_{PERIOD_FIELD_SUFFIX[period]}")
        for period in PERIODS
    }
    missing_amount_fields = {
        field: sum(1 for row in rows if row.get(field) in (None, ""))
        for field in (
            "amount_day",
            "amount_prev_day",
            "amount_week",
            "amount_prev_week",
            "amount_month",
            "amount_prev_month",
            "amount_quarter",
            "amount_prev_quarter",
            "amount_year",
            "amount_prev_year",
        )
    }
    return {
        "necessary_counts": necessary_counts,
        "period_grade_counts": grade_counts,
        "missing_amount_fields": missing_amount_fields,
        "static_structure_coverage": static_structure_coverage(rows),
        "static_structure_missing_samples": static_structure_missing_samples(rows),
        "period_trigger_baseline_coverage": period_trigger_baseline_coverage(rows),
        "period_trigger_baseline_missing_samples": period_trigger_baseline_missing_samples(rows),
        "period_trigger_baseline_not_ready_samples": period_trigger_baseline_not_ready_samples(rows),
        "amount_baseline_complete_count": sum(1 for row in rows if row.get("amount_quality_status") == "passed"),
        "amount_baseline_warning_count": sum(1 for row in rows if row.get("amount_quality_status") != "passed"),
    }


def count_values(rows: list[Mapping[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(field) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def static_structure_coverage(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    coverage = {
        "main_up_anchor": count_present(rows, "main_up_anchor"),
        "buy_target_price": count_present(rows, "buy_target_price"),
        "main_down_anchor": count_present(rows, "main_down_anchor"),
        "sell_target_price": count_present(rows, "sell_target_price"),
        "up_sell_reference_period": count_present(rows, "up_sell_reference_period"),
        "down_buy_reference_period": count_present(rows, "down_buy_reference_period"),
        "clear_sell_ref_period": count_present(rows, "clear_sell_ref_period"),
    }
    for field in SYMMETRY_TARGET_FIELDS:
        coverage[field] = count_present(rows, field)
    return coverage


def count_present(rows: list[Mapping[str, Any]], field: str) -> int:
    return sum(1 for row in rows if row.get(field) not in (None, ""))


def static_structure_missing_samples(rows: list[Mapping[str, Any]], limit: int = 5) -> dict[str, list[dict[str, Any]]]:
    return {
        field: [basis_row_sample(row) for row in rows if row.get(field) in (None, "")][:limit]
        for field in (
            "buy_target_price",
            "sell_target_price",
            "reference_target_price",
            "base_price_policy",
            "target_price_trace_json",
            "up_sell_reference_period",
            "down_buy_reference_period",
            "clear_sell_ref_period",
        )
    }


def period_trigger_baseline_coverage(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    ready_counts = {
        period: sum(
            1
            for row in rows
            if period_trigger_baseline_period_ready(row.get("period_trigger_baseline_json"), period)
        )
        for period in PERIODS
    }
    all_ready = sum(
        1
        for row in rows
        if all(period_trigger_baseline_period_ready(row.get("period_trigger_baseline_json"), period) for period in PERIODS)
    )
    return {
        "row_count": len(rows),
        "present": sum(1 for row in rows if row.get("period_trigger_baseline_json") not in (None, "")),
        "valid_shape": sum(1 for row in rows if period_trigger_baseline_has_required_shape(row.get("period_trigger_baseline_json"))),
        "ready_all_periods": all_ready,
        "not_ready_all_periods": max(len(rows) - all_ready, 0),
        "ready_by_period": ready_counts,
        "not_ready_by_period": {period: max(len(rows) - ready_counts[period], 0) for period in PERIODS},
    }


def period_trigger_baseline_missing_samples(rows: list[Mapping[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    return [
        basis_row_sample(row)
        for row in rows
        if not period_trigger_baseline_has_required_shape(row.get("period_trigger_baseline_json"))
    ][:limit]


def period_trigger_baseline_not_ready_samples(rows: list[Mapping[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for row in rows:
        missing_periods = period_trigger_baseline_not_ready_periods(row.get("period_trigger_baseline_json"), PERIODS)
        if missing_periods:
            sample = basis_row_sample(row)
            sample["not_ready_periods"] = missing_periods
            samples.append(sample)
            if len(samples) >= limit:
                break
    return samples


def period_trigger_baseline_has_required_shape(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    periods = value.get("periods")
    if not isinstance(periods, Mapping):
        return False
    for period in PERIODS:
        entry = periods.get(period)
        if not isinstance(entry, Mapping):
            return False
        if any(key not in entry for key in PERIOD_TRIGGER_BASELINE_REQUIRED_KEYS):
            return False
    return True


def period_trigger_baseline_period_ready(value: Any, period: str) -> bool:
    if not isinstance(value, Mapping):
        return False
    periods = value.get("periods")
    if not isinstance(periods, Mapping):
        return False
    entry = periods.get(period)
    if not isinstance(entry, Mapping):
        return False
    if "baseline_ready" in entry:
        return bool(entry.get("baseline_ready"))
    amount_metric = str(entry.get("amount_metric") or ("amount" if period == "D" else "avg_amount"))
    amount_key = "previous_amount" if amount_metric == "amount" else "previous_avg_amount"
    return all(entry.get(key) not in (None, "") for key in ("previous_entity_high", "previous_entity_low", amount_key))


def period_trigger_baseline_not_ready_periods(value: Any, required_periods: Iterable[str]) -> list[str]:
    return [
        period
        for period in PERIODS
        if period in set(str(item).upper() for item in required_periods)
        and not period_trigger_baseline_period_ready(value, period)
    ]


def basis_row_sample(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "identity_key": row.get("stock_identity_key") or row.get("index_identity_key") or row.get("board_identity_key"),
        "code": row.get("code") or row.get("board_code"),
        "name": row.get("name") or row.get("board_name"),
        "period_grades": {
            period: row.get(f"period_grade_{PERIOD_FIELD_SUFFIX[period]}")
            for period in PERIODS
        },
    }


def empty_period_fields() -> dict[str, Any]:
    return {
        "period_key_y": None,
        "period_key_q": None,
        "period_key_m": None,
        "period_key_w": None,
        "period_key_d": None,
        "period_grade_y": "unknown",
        "period_grade_q": "unknown",
        "period_grade_m": "unknown",
        "period_grade_w": "unknown",
        "period_grade_d": "unknown",
        "period_transition_y": "unknown",
        "period_transition_q": "unknown",
        "period_transition_m": "unknown",
        "period_transition_w": "unknown",
        "period_transition_d": "unknown",
        "prev_up_str": "",
        "prev_dn_str": "",
        "amount_prev_day": None,
        "amount_week": None,
        "amount_prev_week": None,
        "amount_month": None,
        "amount_prev_month": None,
        "amount_quarter": None,
        "amount_prev_quarter": None,
        "amount_year": None,
        "amount_prev_year": None,
    }


def stock_condition_universe_summary(ready_check: Mapping[str, Any]) -> dict[str, Any]:
    universe = dict(ready_check.get("stock_condition_universe") or {})
    manifest = dict(ready_check.get("condition_source_gap_manifest") or {})
    summary = {
        "stock_daily_fact_row_count": universe.get("stock_daily_row_count"),
        "expected_condition_stock_universe": ready_check.get("expected_condition_stock_universe")
        or universe.get("expected_condition_stock_universe"),
        "excluded_from_condition_universe": ready_check.get("excluded_from_condition_universe")
        or universe.get("excluded_from_condition_universe")
        or manifest.get("excluded_from_condition_universe"),
        "condition_source_gap_manifest_count": universe.get("condition_source_gap_manifest_count")
        or manifest.get("manifest_count"),
        "condition_source_gap_manifest_valid_exclusion_actions": manifest.get("valid_exclusion_actions"),
    }
    return {key: value for key, value in summary.items() if value is not None}


def empty_static_structure_fields() -> dict[str, Any]:
    fields = {
        "main_up_anchor": None,
        "up_reference_period": None,
        "up_amplitude": None,
        "up_base_price": None,
        "buy_target_price": None,
        "buy_expected_return_pct": None,
        "up_trend_start_date": None,
        "up_trend_end_date": None,
        "up_reference_window_start": None,
        "up_reference_window_end": None,
        "main_down_anchor": None,
        "down_reference_period": None,
        "down_amplitude": None,
        "down_base_price": None,
        "sell_target_price": None,
        "sell_expected_return_pct": None,
        "down_trend_start_date": None,
        "down_trend_end_date": None,
        "down_reference_window_start": None,
        "down_reference_window_end": None,
        "up_sell_reference_period": "D",
        "down_buy_reference_period": "D",
        "clear_sell_ref_period": "D",
    }
    fields.update({field: None for field in SYMMETRY_TARGET_FIELDS})
    return fields


def empty_necessary_condition_fields() -> dict[str, Any]:
    return {
        "buy_necessary_base": False,
        "buy_necessary_key": None,
        "buy_necessary_periods": [],
        "sell_necessary_base": False,
        "sell_necessary_key": None,
        "sell_necessary_periods": [],
        "buy_full_necessary_base": False,
        "buy_full_necessary_key": None,
        "sell_full_necessary_base": False,
        "sell_full_necessary_key": None,
        "oversold_hint_necessary_base": False,
        "oversold_hint_key": None,
        "overbought_hint_necessary_base": False,
        "overbought_hint_key": None,
    }


def build_quality_items(
    *,
    ready_check: Mapping[str, Any],
    date_context: DateContext,
    monitor_targets: Mapping[str, Mapping[str, Any]],
    stock_summary: Mapping[str, Any],
    index_summary: Mapping[str, Any],
    board_summary: Mapping[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    items.append(quality_item("P0", "passed" if ready_check.get("passed") else "failed", "condition_source_ready", "入库层条件源 ready check"))
    items.extend(ready_check_failure_quality_items(ready_check))
    items.append(quality_item("P0", "passed", "for_trade_date_inferred", "for_trade_date 由 common_trade_calendar 推导", actual=date_context.for_trade_date))
    items.append(quality_item("P0", "passed", "prev_trade_date_match", "prev_trade_date(for_trade_date) 等于 source_trade_date", expected=date_context.source_trade_date, actual=date_context.prev_trade_date))
    items.append(quality_item("P0", "passed", "no_market_data_pull", "N2-B 条件层 dry-run 不拉实时行情或一分钟 K"))
    items.append(
        quality_item(
            "P0",
            "passed",
            "previous_day_minute_date_contract",
            "后续 scope 若声明 previous_day_minute_required=true，则 previous_day_minute_date 必须等于 prev_trade_date",
            expected=date_context.prev_trade_date,
            actual=date_context.prev_trade_date,
        )
    )
    if not date_context.for_trade_calendar_row_exists:
        items.append(
            quality_item(
                "P1",
                "warning",
                "for_trade_calendar_row_missing",
                "source row exposes next_trade_date, but common_trade_calendar has no detail row for inferred for_trade_date yet",
                expected=date_context.for_trade_date,
                actual="missing",
            )
        )
    items.append(quality_item("P0", "passed" if int(stock_summary.get("missing_identity_key_count") or 0) == 0 else "failed", "stock_identity_key_coverage", "stock basis identity_key coverage"))
    items.append(quality_item("P0", "passed" if int(index_summary.get("missing_identity_key_count") or 0) == 0 else "failed", "index_identity_key_coverage", "index basis identity_key coverage"))
    items.append(quality_item("P0", "passed" if int(board_summary.get("missing_identity_key_count") or 0) == 0 else "failed", "board_identity_key_coverage", "board basis identity_key coverage"))
    fixed_index_missing = list(index_summary.get("fixed_default_index_missing_basis") or [])
    items.append(
        quality_item(
            "P0",
            "passed" if not fixed_index_missing else "failed",
            "fixed_9_index_basis_coverage",
            "固定 9 指数必须存在 exchange-qualified index_condition_basis 来源",
            expected=",".join(DEFAULT_INDEX_POOL_IDENTITIES),
            actual="missing:" + ",".join(fixed_index_missing) if fixed_index_missing else "complete",
            details={"missing_identity_keys": fixed_index_missing},
        )
    )
    fixed_index_amount_warnings = list(index_summary.get("fixed_default_index_amount_baseline_warnings") or [])
    items.append(
        quality_item(
            "P0",
            "passed" if not fixed_index_amount_warnings else "failed",
            "fixed_9_index_amount_baseline_coverage",
            "固定 9 指数必须具备完整周期金额基准，才能生成可信 condition_basis",
            expected="amount_quality_status=passed for all fixed 9 index basis rows",
            actual="passed" if not fixed_index_amount_warnings else ",".join(str(item.get("identity_key")) for item in fixed_index_amount_warnings[:20]),
            details={"warning_samples": fixed_index_amount_warnings[:20]},
        )
    )
    items.append(quality_item("P0", "passed" if int(stock_summary.get("board_code_violation_count") or 0) == 0 else "failed", "stock_88xxxx_violation", "88xxxx 不得进入 stock basis"))
    items.append(quality_item("P0", "passed" if int(board_summary.get("non_board_code_count") or 0) == 0 else "failed", "board_code_namespace", "board basis 只允许 88xxxx"))
    items.append(quality_item("P0", "passed" if int(stock_summary.get("official_daily_unproved_count") or 0) == 0 else "failed", "stock_official_daily_proof", "stock official daily proof 完整"))
    stock_rows = int(stock_summary.get("row_count") or 0)
    daily_basic_join_count = int(stock_summary.get("daily_basic_join_count") or 0)
    financial_join_count = int(stock_summary.get("financial_join_count") or 0)
    expected_stock_universe = int(stock_summary.get("expected_condition_stock_universe") or 0)
    excluded_from_condition_universe = int(stock_summary.get("excluded_from_condition_universe") or 0)
    stock_daily_fact_row_count = int(stock_summary.get("stock_daily_fact_row_count") or stock_rows)
    if expected_stock_universe:
        items.append(
            quality_item(
                "P0",
                "passed" if stock_rows == expected_stock_universe else "failed",
                "stock_condition_universe_count",
                "stock condition_basis 必须使用 stock_daily_basic ∩ stock_financial ∩ eligible stock_daily 口径",
                expected=str(expected_stock_universe),
                actual=str(stock_rows),
                details={
                    "stock_daily_fact_row_count": stock_daily_fact_row_count,
                    "excluded_from_condition_universe": excluded_from_condition_universe,
                    "condition_source_gap_manifest_count": stock_summary.get("condition_source_gap_manifest_count"),
                    "valid_exclusion_actions": stock_summary.get("condition_source_gap_manifest_valid_exclusion_actions"),
                },
            )
        )
    if excluded_from_condition_universe:
        actual_excluded = stock_daily_fact_row_count - stock_rows
        items.append(
            quality_item(
                "P0",
                "passed" if actual_excluded == excluded_from_condition_universe else "failed",
                "condition_source_gap_excluded_from_basis",
                "condition_source_gap_manifest action=exclude_from_condition_universe 的个股不得进入 stock_condition_basis",
                expected=str(excluded_from_condition_universe),
                actual=str(actual_excluded),
                details={
                    "stock_daily_fact_row_count": stock_daily_fact_row_count,
                    "stock_condition_basis_rows": stock_rows,
                    "excluded_from_condition_universe": excluded_from_condition_universe,
                },
            )
        )
    items.append(
        quality_item(
            "P0",
            "passed" if stock_rows == daily_basic_join_count else "failed",
            "stock_daily_basic_join_coverage",
            "stock condition_basis 必须能关联 stock_daily_basic 市值/估值",
            expected=str(stock_rows),
            actual=str(daily_basic_join_count),
        )
    )
    items.append(
        quality_item(
            "P0",
            "passed" if stock_rows == financial_join_count else "failed",
            "stock_financial_join_coverage",
            "stock condition_basis 必须能关联 stock_financial 财务快照",
            expected=str(stock_rows),
            actual=str(financial_join_count),
        )
    )
    missing_total_mv = int(stock_summary.get("missing_total_mv_count") or 0)
    if missing_total_mv:
        items.append(
            quality_item(
                "P1",
                "warning",
                "stock_total_mv_missing",
                "部分 stock basis 缺少 total_mv；后续 stock_minute_target_scope 会排除这些个股",
                expected="0",
                actual=str(missing_total_mv),
            )
        )
    for domain, status in monitor_targets.items():
        if not status.get("exists") or int(status.get("active_count") or 0) == 0:
            items.append(
                quality_item(
                    "P1",
                    "warning",
                    f"{domain}_monitor_target_fallback",
                    f"{domain} monitor target not available for dry-run; using fact universe fallback preview",
                )
            )
    items.append(
        quality_item(
            "P0",
            "passed",
            "necessary_family_diagnostics_present",
            "普通 BUY/SELL、BUY:FULL/SELL:FULL、BUY_HINT/SELL_HINT 必要条件已独立计算和计数",
        )
    )
    amount_warning_count = sum(
        int(summary.get("amount_baseline_warning_count") or 0)
        for summary in (stock_summary, index_summary, board_summary)
    )
    if amount_warning_count:
        items.append(
            quality_item(
                "P1",
                "warning",
                "amount_baseline_missing",
                "部分对象缺少周期成交额基准，相关周期会得到 unknown 分级",
                expected="0",
                actual=str(amount_warning_count),
            )
        )
    items.append(
        quality_item(
            "P0",
            "passed",
            "static_structure_calculated",
            "main_up/down_anchor、目标价、预期收益、up_sell_reference_period/down_buy_reference_period 与 legacy clear alias 已在条件层 dry-run 计算",
        )
    )
    static_missing = static_structure_missing_summary(stock_summary, index_summary, board_summary)
    baseline_missing = period_trigger_baseline_missing_summary(stock_summary, index_summary, board_summary)
    items.append(
        quality_item(
            "P0",
            "passed" if int(baseline_missing.get("missing_total") or 0) == 0 else "failed",
            "period_trigger_baseline_json_full_chain_basis",
            "condition_basis dry-run 必须为 stock/index/board 全量 basis 冻结 period_trigger_baseline_json",
            expected="missing=0",
            actual=str(baseline_missing.get("missing_total") or 0),
            details=baseline_missing,
        )
    )
    if int(baseline_missing.get("not_ready_total") or 0) > 0:
        items.append(
            quality_item(
                "P1",
                "warning",
                "period_trigger_baseline_partial_readiness",
                "condition_basis 可保留全量 baseline 缺口，但必须记录每周期 baseline_ready 与缺口样本；condition_pool/scope 不得承接必要周期缺口",
                expected="ready_all_periods for every row, or downstream exclusion",
                actual=str(baseline_missing.get("not_ready_total") or 0),
                details=baseline_missing,
            )
        )
    if int(static_missing.get("reference_missing_total") or 0) > 0:
        items.append(
            quality_item(
                "P0",
                "failed",
                "static_reference_period_missing",
                "up_sell_reference_period / down_buy_reference_period / legacy clear alias 必须有值",
                expected="0",
                actual=str(static_missing.get("reference_missing_total") or 0),
                details=static_missing,
            )
        )
    if static_missing["missing_total"] > 0:
        items.append(
            quality_item(
                "P1",
                "warning",
                "static_structure_partial_coverage",
                "部分对象缺少上涨/下跌主锚或目标价，参考周期字段必须非空并保留样本",
                expected="full static structure coverage",
                actual=str(static_missing["missing_total"]),
                details=static_missing,
            )
        )
    items.append(
        quality_item(
            "P2",
            "warning",
            "monitor_target_pending",
            "N2-B3 仍使用 fact universe fallback；正式 monitor target 迁移后需复跑",
        )
    )
    return items


def period_trigger_baseline_missing_summary(*summaries: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {"missing_total": 0, "not_ready_total": 0, "domains": {}}
    for domain, summary in zip(("stock", "index", "board"), summaries):
        row_count = int(summary.get("row_count") or 0)
        coverage = dict(summary.get("period_trigger_baseline_coverage") or {})
        valid_shape = int(coverage.get("valid_shape") or 0)
        missing_count = max(row_count - valid_shape, 0)
        not_ready_count = int(coverage.get("not_ready_all_periods") or 0)
        output["missing_total"] += missing_count
        output["not_ready_total"] += not_ready_count
        output["domains"][domain] = {
            "row_count": row_count,
            "coverage": coverage,
            "missing_count": missing_count,
            "not_ready_count": not_ready_count,
            "samples": summary.get("period_trigger_baseline_missing_samples") or [],
            "not_ready_samples": summary.get("period_trigger_baseline_not_ready_samples") or [],
        }
    return output


def static_structure_missing_summary(*summaries: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {"missing_total": 0, "reference_missing_total": 0, "domains": {}}
    for domain, summary in zip(("stock", "index", "board"), summaries):
        row_count = int(summary.get("row_count") or 0)
        coverage = dict(summary.get("static_structure_coverage") or {})
        missing = {
            field: max(row_count - int(coverage.get(field) or 0), 0)
            for field in ("buy_target_price", "sell_target_price")
        }
        reference_missing = {
            field: max(row_count - int(coverage.get(field) or 0), 0)
            for field in ("up_sell_reference_period", "down_buy_reference_period", "clear_sell_ref_period")
        }
        output["missing_total"] += sum(missing.values())
        output["reference_missing_total"] += sum(reference_missing.values())
        output["domains"][domain] = {
            "row_count": row_count,
            "coverage": coverage,
            "missing": missing,
            "reference_missing": reference_missing,
            "samples": summary.get("static_structure_missing_samples") or {},
        }
    return output

def ready_check_failure_quality_items(ready_check: Mapping[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for check in ready_check.get("checks", []):
        if check.get("passed"):
            continue
        data_type = str(check.get("data_type") or "unknown")
        reasons = check.get("failure_reasons") or []
        fact = check.get("fact") or {}
        items.append(
            quality_item(
                "P0",
                "failed",
                f"condition_source_ready_{data_type}",
                f"{data_type} active source is not ready for condition_basis",
                expected="ready",
                actual="; ".join(str(reason) for reason in reasons) or "not ready",
                details=fact if isinstance(fact, Mapping) else None,
            )
        )
    return items


def quality_item(
    severity: str,
    status: str,
    gate_code: str,
    gate_name: str,
    *,
    expected: str | None = None,
    actual: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    item = {
        "severity": severity,
        "status": status,
        "gate_code": gate_code,
        "gate_name": gate_name,
        "expected_value": expected,
        "actual_value": actual,
    }
    if details is not None:
        item["details"] = dict(details)
    return item


def count_quality_severities(items: list[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"P0": 0, "P1": 0, "P2": 0}
    for item in items:
        if item.get("status") in {"failed", "warning"}:
            severity = str(item.get("severity") or "")
            if severity in counts:
                counts[severity] += 1
    return counts


def normalize_mapping(row: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            output[key] = str(value)
        else:
            output[key] = value
    return output
