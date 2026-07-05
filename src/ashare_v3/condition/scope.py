"""Read-only minute_target_scope dry-run builder."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row

from ashare_v3.condition.basis import (
    DateContext,
    SYMMETRY_TARGET_FIELDS,
    STOCK_FINANCIAL_PASS_THROUGH_FIELDS,
    STANDARD_SIGNAL_TYPES,
    active_versions_from_ready_check,
    canonical_target_fields_for_direction,
    count_quality_severities,
    infer_date_context,
    normalize_mapping,
    period_trigger_baseline_has_required_shape,
    quality_item,
)
from ashare_v3.condition.pool import (
    allowed_board_types_from_policy,
    allowed_index_identity_keys_from_policy,
    build_condition_pool_dry_run,
    default_condition_pool_policy,
    missing_required_period_trigger_baseline_periods,
)
from ashare_v3.condition.scope_policy import (
    default_scope_policy,
    filter_scope_rows,
    normalize_scope_policy,
    scope_policy_warnings,
)
from ashare_v3.ingestion.common import require_yyyymmdd


FIXED_INDEX_TARGETS: tuple[tuple[int, str, str], ...] = (
    (1, "000905", "SH"),
    (2, "399303", "SZ"),
    (3, "000001", "SH"),
    (4, "000852", "SH"),
    (5, "399001", "SZ"),
    (6, "399006", "SZ"),
    (7, "000300", "SH"),
    (8, "000016", "SH"),
    (9, "000688", "SH"),
)
FIXED_INDEX_CODES: tuple[str, ...] = tuple(item[1] for item in FIXED_INDEX_TARGETS)

BUY_SCOPE_SIGNAL_TYPES = ("BUY",)
SELL_SCOPE_SIGNAL_TYPES = ("SELL",)
ORDINARY_PERIODS = frozenset({"Y", "Q", "M", "W", "D"})
REQUIRED_SCOPE_DATA_TYPES = ("stock_daily", "index_daily", "board_daily")
MINUTE_SIGNAL_TYPES = frozenset({"BUY", "SELL", "BUY:FULL", "SELL:FULL", "BUY_HINT", "SELL_HINT"})
RUNTIME_MONITOR_MINUTE_SCOPE_POLICY = "condition_pool_runtime_monitor_requires_minute"
STOCK_SCOPE_MIN_TOTAL_MV_WAN = Decimal("1000000")


def build_minute_target_scope_dry_run(
    *,
    dsn: str,
    source_trade_date: str,
    ready_check: Mapping[str, Any],
    scope_policy: Mapping[str, Any] | None = None,
    condition_pool_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    effective_policy = normalize_scope_policy(scope_policy or default_scope_policy())
    condition_pool_report = build_condition_pool_dry_run(
        dsn=dsn,
        source_trade_date=source_trade_date,
        ready_check=ready_check,
        condition_pool_policy=condition_pool_policy,
    )
    active_versions = active_versions_from_ready_check(ready_check)
    missing_active = [data_type for data_type in REQUIRED_SCOPE_DATA_TYPES if data_type not in active_versions]
    if missing_active:
        raise ValueError(f"ready check is missing active versions: {missing_active}")

    with psycopg.connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        date_context = infer_date_context(cur, source_trade_date)
        index_scope = build_index_condition_scope_from_pool_report(condition_pool_report, date_context)
        board_scope = build_board_condition_scope_from_pool_report(condition_pool_report, date_context)
        stock_scope = build_stock_condition_scope_from_pool_report(condition_pool_report, date_context)
    candidate_preview = {
        "index": index_scope,
        "board": board_scope,
        "stock": stock_scope,
    }
    scope_preview, policy_diagnostics = apply_scope_policy_to_preview(candidate_preview, effective_policy, date_context)

    quality_items = build_scope_quality_items(
        ready_check=ready_check,
        date_context=date_context,
        condition_pool_report=condition_pool_report,
        index_scope=scope_preview["index"],
        board_scope=scope_preview["board"],
        stock_scope=scope_preview["stock"],
    )
    severity_counts = count_quality_severities(quality_items)
    return {
        "stage": "N2-D",
        "mode": "dry_run",
        "writes_performed": False,
        "condition_pool_written": False,
        "minute_kline_pulled": False,
        "run_id": f"minute_target_scope_{date_context.source_trade_date}_to_{date_context.for_trade_date}_dry_run",
        "source_trade_date": date_context.source_trade_date,
        "for_trade_date": date_context.for_trade_date,
        "prev_trade_date": date_context.prev_trade_date,
        "for_trade_calendar_row_exists": date_context.for_trade_calendar_row_exists,
        "source_versions": {
            data_type: active_versions[data_type]["active_source_version"]
            for data_type in REQUIRED_SCOPE_DATA_TYPES
        },
        "source_ready_passed": bool(ready_check.get("passed")),
        "condition_pool_source": {
            "mode": "condition_pool_dry_run",
            "run_id": condition_pool_report.get("run_id"),
            "persisted_condition_pool_read": False,
            "source_condition_pool_ids_available": False,
            "pool_p0_count": condition_pool_report.get("quality", {}).get("p0_count"),
            "pool_p1_count": condition_pool_report.get("quality", {}).get("p1_count"),
            "pool_p2_count": condition_pool_report.get("quality", {}).get("p2_count"),
        },
        "scope_policy": {
            "policy_name": effective_policy.get("policy_name"),
            "mode": "default" if not scope_policy else "custom",
            "effective_policy": effective_policy,
            "warnings": scope_policy_warnings(effective_policy),
            "diagnostics": policy_diagnostics,
        },
        "scope_candidate_preview": {
            domain: summarize_scope_candidate(candidate_preview[domain])
            for domain in ("index", "board", "stock")
        },
        "scope_preview": {
            "index": scope_preview["index"],
            "board": scope_preview["board"],
            "stock": scope_preview["stock"],
        },
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "passed": severity_counts["P0"] == 0 and bool(ready_check.get("passed")),
    }


def apply_scope_policy_to_preview(
    candidate_preview: Mapping[str, Mapping[str, Any]],
    policy: Mapping[str, Any],
    dates: DateContext,
) -> tuple[dict[str, Any], dict[str, Any]]:
    selected_preview: dict[str, Any] = {}
    diagnostics: dict[str, Any] = {}
    for domain in ("index", "board", "stock"):
        candidate_scope = candidate_preview[domain]
        filter_result = filter_scope_rows(domain, list(candidate_scope.get("scope_rows") or []), policy[domain])
        selected_scope = rebuild_scope_summary(
            domain=domain,
            candidate_scope=candidate_scope,
            selected_rows=filter_result["selected_rows"],
            dates=dates,
        )
        selected_scope["policy_selected_count"] = filter_result["selected_count"]
        selected_scope["policy_excluded_count"] = filter_result["excluded_count"]
        selected_scope["policy_excluded_reason_counts"] = filter_result["excluded_reason_counts"]
        selected_scope["policy_selected_samples"] = filter_result["selected_samples"]
        selected_scope["policy_excluded_samples"] = filter_result["excluded_samples"]
        selected_scope["policy_distribution"] = scope_distribution_report(domain, filter_result["selected_rows"])
        selected_scope["policy_name"] = policy.get("policy_name")
        selected_preview[domain] = selected_scope
        diagnostics[domain] = {
            "candidate_count": filter_result["candidate_count"],
            "selected_count": filter_result["selected_count"],
            "excluded_count": filter_result["excluded_count"],
            "excluded_reason_counts": filter_result["excluded_reason_counts"],
            "selected_samples": filter_result["selected_samples"],
            "excluded_samples": filter_result["excluded_samples"],
            "distribution": selected_scope["policy_distribution"],
        }
    return selected_preview, diagnostics


def scope_distribution_report(domain: str, rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    report = {
        "condition_key_counts": sorted_counter(row.get("condition_key") for row in rows),
        "direction_counts": sorted_counter(row.get("direction") for row in rows),
        "scope_source_counts": sorted_counter(row.get("scope_source") for row in rows),
    }
    if domain == "stock":
        report.update(
            {
                "total_mv_bucket_counts": total_mv_bucket_counts(rows),
                "preferred_board_code_counts": top_counter(row.get("preferred_board_code") for row in rows),
                "recommendation_level_counts": sorted_counter(row.get("recommendation_level") for row in rows),
                "lane_counts": sorted_counter(row.get("lane") for row in rows),
            }
        )
    return report


def sorted_counter(values: Any) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for value in values:
        if value not in (None, ""):
            counts[str(value)] += 1
    return dict(sorted(counts.items()))


def top_counter(values: Any, limit: int = 20) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for value in values:
        if value not in (None, ""):
            counts[str(value)] += 1
    return dict(counts.most_common(limit))


def total_mv_bucket_counts(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    buckets = {
        "100-300yi": 0,
        "300-500yi": 0,
        "500-1000yi": 0,
        "1000yi_plus": 0,
        "missing": 0,
    }
    for row in rows:
        value = decimal_or_none(row.get("total_mv"))
        if value is None:
            buckets["missing"] += 1
        elif value < Decimal("3000000"):
            buckets["100-300yi"] += 1
        elif value < Decimal("5000000"):
            buckets["300-500yi"] += 1
        elif value < Decimal("10000000"):
            buckets["500-1000yi"] += 1
        else:
            buckets["1000yi_plus"] += 1
    return {key: value for key, value in buckets.items() if value}


def decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def rebuild_scope_summary(
    *,
    domain: str,
    candidate_scope: Mapping[str, Any],
    selected_rows: list[Mapping[str, Any]],
    dates: DateContext,
) -> dict[str, Any]:
    selected_rows = [normalize_mapping(row) for row in selected_rows]
    selected_scope = dict(candidate_scope)
    selected_scope["candidate_object_count"] = candidate_scope.get("object_count")
    selected_scope["candidate_scope_row_count"] = candidate_scope.get("scope_row_count")
    selected_scope["scope_rows"] = selected_rows
    selected_scope["sample_scope_rows"] = selected_rows[:6]
    selected_scope["scope_row_count"] = len(selected_rows)
    selected_scope["object_count"] = count_scope_objects(domain, selected_rows)
    selected_scope.update(scope_row_diagnostics(selected_rows, dates.prev_trade_date))
    if domain == "index":
        selected_scope["objects"] = filter_scope_objects("index", list(candidate_scope.get("objects") or []), selected_rows)
        selected_scope["missing_daily_codes"] = [
            row["code"]
            for row in selected_scope["objects"]
            if not row.get("daily_row_exists")
        ]
    elif domain == "board":
        selected_scope["objects"] = filter_scope_objects("board", list(candidate_scope.get("objects") or []), selected_rows)
        selected_scope["missing_daily_codes"] = [
            row["board_code"]
            for row in selected_scope["objects"]
            if not row.get("daily_row_exists")
        ]
    return selected_scope


def filter_scope_objects(domain: str, objects: list[Mapping[str, Any]], selected_rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if domain == "index":
        selected_codes = {str(row.get("code") or "") for row in selected_rows}
        return [normalize_mapping(row) for row in objects if str(row.get("code") or "") in selected_codes]
    if domain == "board":
        selected_codes = {str(row.get("board_code") or "") for row in selected_rows}
        return [normalize_mapping(row) for row in objects if str(row.get("board_code") or "") in selected_codes]
    return [normalize_mapping(row) for row in objects]


def count_scope_objects(domain: str, scope_rows: list[Mapping[str, Any]]) -> int:
    if domain == "board":
        return len({row.get("identity_key") or row.get("board_code") for row in scope_rows if row.get("identity_key") or row.get("board_code")})
    return len({row.get("identity_key") or row.get("code") for row in scope_rows if row.get("identity_key") or row.get("code")})


def summarize_scope_candidate(scope: Mapping[str, Any]) -> dict[str, Any]:
    summary_keys = (
        "scope_source",
        "condition_pool_source",
        "object_count",
        "scope_row_count",
        "previous_day_minute_required_count",
        "previous_day_minute_date_mismatch_count",
        "excluded_below_min_total_mv_count",
        "missing_total_mv_count",
        "missing_identity_codes",
        "missing_daily_codes",
    )
    return {key: scope.get(key) for key in summary_keys if key in scope}


def fetch_stock_condition_scope(
    cur: psycopg.Cursor[dict[str, Any]],
    dates: DateContext,
) -> dict[str, Any]:
    cur.execute("SELECT to_regclass('public.stock_condition_pool')")
    table_exists = cur.fetchone()["to_regclass"] is not None
    if not table_exists:
        return {
            "scope_source": "condition_pool",
            "condition_pool_exists": False,
            "condition_pool_source": "persisted_condition_pool",
            "persisted_condition_pool_read": True,
            "object_count": 0,
            "scope_row_count": 0,
            **scope_row_diagnostics([], dates.prev_trade_date),
            "min_total_mv_wan": str(STOCK_SCOPE_MIN_TOTAL_MV_WAN),
            "excluded_below_min_total_mv_count": 0,
            "missing_total_mv_count": 0,
            "eligible_condition_keys": ["BUY:*", "SELL:*", "BUY:FULL", "SELL:FULL", "BUY_HINT", "SELL_HINT"],
            "scope_rows": [],
            "sample_scope_rows": [],
        }

    cur.execute(
        """
        SELECT stock_condition_pool_id,
               run_id,
               p.for_trade_date,
               p.source_trade_date,
               p.stock_identity_key,
               p.code,
               p.exchange,
               p.name,
               p.lane,
               p.direction,
               p.condition_key,
               p.condition_periods,
               p.allowed_signal_types,
               p.is_hint_scope,
               p.source_version,
               p.active_target,
               p.quality_status,
               p.quality_reason,
               b.total_mv,
               b.circ_mv
        FROM stock_condition_pool p
        JOIN stock_condition_basis b
          ON b.stock_condition_basis_id = p.source_condition_basis_id
        WHERE p.for_trade_date = %s
          AND p.source_trade_date = %s
          AND p.active_target = true
          AND p.direction IN ('buy', 'sell')
          AND (
            p.condition_key LIKE 'BUY:%%'
            OR p.condition_key LIKE 'SELL:%%'
            OR p.condition_key IN ('BUY_HINT', 'SELL_HINT')
          )
        ORDER BY p.stock_identity_key, p.lane, p.direction, p.condition_key
        """,
        (dates.for_trade_date, dates.source_trade_date),
    )
    eligible_condition_rows = [
        normalize_mapping(row)
        for row in cur.fetchall()
        if is_stock_condition_key_scope_eligible(str(row.get("condition_key") or ""))
    ]
    pool_rows = [
        row
        for row in eligible_condition_rows
        if stock_total_mv_is_scope_eligible(row.get("total_mv"))
    ]
    scope_rows = [make_stock_scope_row(row, dates) for row in pool_rows]
    object_keys = {row["stock_identity_key"] for row in pool_rows}
    diagnostics = scope_row_diagnostics(scope_rows, dates.prev_trade_date)
    return {
        "scope_source": "condition_pool",
        "condition_pool_exists": True,
        "condition_pool_source": "persisted_condition_pool",
        "persisted_condition_pool_read": True,
        "object_count": len(object_keys),
        "scope_row_count": len(scope_rows),
        **diagnostics,
        "min_total_mv_wan": str(STOCK_SCOPE_MIN_TOTAL_MV_WAN),
        "excluded_below_min_total_mv_count": sum(
            1
            for row in eligible_condition_rows
            if row.get("total_mv") not in (None, "") and not stock_total_mv_is_scope_eligible(row.get("total_mv"))
        ),
        "missing_total_mv_count": sum(1 for row in eligible_condition_rows if row.get("total_mv") in (None, "")),
        "eligible_condition_keys": ["BUY:*", "SELL:*", "BUY:FULL", "SELL:FULL", "BUY_HINT", "SELL_HINT"],
        "scope_rows": scope_rows,
        "sample_scope_rows": scope_rows[:6],
    }


def build_index_condition_scope_from_pool_report(
    condition_pool_report: Mapping[str, Any],
    dates: DateContext,
) -> dict[str, Any]:
    pool_preview = condition_pool_report.get("pool_preview", {}).get("index", {})
    raw_pool_rows = [normalize_mapping(row) for row in pool_preview.get("pool_rows") or []]
    eligible_rows = [
        {**row, "run_id": condition_pool_report.get("run_id")}
        for row in raw_pool_rows
        if row.get("active_target") is True
        and row.get("direction") in {"buy", "sell"}
    ]
    scope_rows = [make_index_scope_row_from_pool(row, dates) for row in eligible_rows]
    object_keys = {
        row.get("index_identity_key") or row.get("identity_key")
        for row in eligible_rows
        if row.get("index_identity_key") or row.get("identity_key")
    }
    diagnostics = scope_row_diagnostics(scope_rows, dates.prev_trade_date)
    present_codes = sorted({str(row.get("code")) for row in eligible_rows if row.get("code")})
    return {
        "scope_source": "condition_pool",
        "condition_pool_exists": True,
        "condition_pool_source": "condition_pool_dry_run",
        "condition_pool_run_id": condition_pool_report.get("run_id"),
        "persisted_condition_pool_read": False,
        "source_condition_pool_ids_available": False,
        "condition_pool_p0_count": condition_pool_report.get("quality", {}).get("p0_count"),
        "condition_pool_p1_count": condition_pool_report.get("quality", {}).get("p1_count"),
        "condition_pool_p2_count": condition_pool_report.get("quality", {}).get("p2_count"),
        "condition_pool_row_count": len(raw_pool_rows),
        "eligible_condition_pool_row_count": len(eligible_rows),
        "fixed_codes": list(FIXED_INDEX_CODES),
        "present_fixed_codes": [code for code in FIXED_INDEX_CODES if code in present_codes],
        "missing_fixed_codes": [code for code in FIXED_INDEX_CODES if code not in present_codes],
        "object_count": len(object_keys),
        "scope_row_count": len(scope_rows),
        **diagnostics,
        "scope_rows": scope_rows,
        "sample_scope_rows": scope_rows[:6],
    }


def build_board_condition_scope_from_pool_report(
    condition_pool_report: Mapping[str, Any],
    dates: DateContext,
) -> dict[str, Any]:
    pool_preview = condition_pool_report.get("pool_preview", {}).get("board", {})
    raw_pool_rows = [normalize_mapping(row) for row in pool_preview.get("pool_rows") or []]
    eligible_rows = [
        {**row, "run_id": condition_pool_report.get("run_id")}
        for row in raw_pool_rows
        if row.get("active_target") is True
        and row.get("direction") in {"buy", "sell"}
    ]
    scope_rows = [make_board_scope_row_from_pool(row, dates) for row in eligible_rows]
    object_keys = {
        row.get("board_identity_key") or row.get("identity_key")
        for row in eligible_rows
        if row.get("board_identity_key") or row.get("identity_key")
    }
    diagnostics = scope_row_diagnostics(scope_rows, dates.prev_trade_date)
    return {
        "scope_source": "condition_pool",
        "condition_pool_exists": True,
        "condition_pool_source": "condition_pool_dry_run",
        "condition_pool_run_id": condition_pool_report.get("run_id"),
        "persisted_condition_pool_read": False,
        "source_condition_pool_ids_available": False,
        "condition_pool_p0_count": condition_pool_report.get("quality", {}).get("p0_count"),
        "condition_pool_p1_count": condition_pool_report.get("quality", {}).get("p1_count"),
        "condition_pool_p2_count": condition_pool_report.get("quality", {}).get("p2_count"),
        "condition_pool_row_count": len(raw_pool_rows),
        "eligible_condition_pool_row_count": len(eligible_rows),
        "object_count": len(object_keys),
        "scope_row_count": len(scope_rows),
        **diagnostics,
        "scope_rows": scope_rows,
        "sample_scope_rows": scope_rows[:6],
    }


def build_stock_condition_scope_from_pool_report(
    condition_pool_report: Mapping[str, Any],
    dates: DateContext,
) -> dict[str, Any]:
    stock_pool_preview = condition_pool_report.get("pool_preview", {}).get("stock", {})
    raw_pool_rows = [normalize_mapping(row) for row in stock_pool_preview.get("pool_rows") or []]
    eligible_condition_rows = [
        row
        for row in raw_pool_rows
        if row.get("active_target") is True
        and row.get("direction") in {"buy", "sell"}
        and is_stock_condition_key_scope_eligible(str(row.get("condition_key") or ""))
    ]
    pool_rows = [
        {**row, "run_id": condition_pool_report.get("run_id")}
        for row in eligible_condition_rows
        if stock_total_mv_is_scope_eligible(row.get("total_mv"))
    ]
    scope_rows = [make_stock_scope_row(row, dates) for row in pool_rows]
    object_keys = {
        row.get("stock_identity_key") or row.get("identity_key")
        for row in pool_rows
        if row.get("stock_identity_key") or row.get("identity_key")
    }
    diagnostics = scope_row_diagnostics(scope_rows, dates.prev_trade_date)
    return {
        "scope_source": "condition_pool",
        "condition_pool_exists": True,
        "condition_pool_source": "condition_pool_dry_run",
        "condition_pool_run_id": condition_pool_report.get("run_id"),
        "persisted_condition_pool_read": False,
        "source_condition_pool_ids_available": False,
        "condition_pool_p0_count": condition_pool_report.get("quality", {}).get("p0_count"),
        "condition_pool_p1_count": condition_pool_report.get("quality", {}).get("p1_count"),
        "condition_pool_p2_count": condition_pool_report.get("quality", {}).get("p2_count"),
        "condition_pool_row_count": len(raw_pool_rows),
        "eligible_condition_pool_row_count": len(eligible_condition_rows),
        "object_count": len(object_keys),
        "scope_row_count": len(scope_rows),
        **diagnostics,
        "min_total_mv_wan": str(STOCK_SCOPE_MIN_TOTAL_MV_WAN),
        "excluded_below_min_total_mv_count": sum(
            1
            for row in eligible_condition_rows
            if row.get("total_mv") not in (None, "") and not stock_total_mv_is_scope_eligible(row.get("total_mv"))
        ),
        "missing_total_mv_count": sum(1 for row in eligible_condition_rows if row.get("total_mv") in (None, "")),
        "eligible_condition_keys": ["BUY:*", "SELL:*", "BUY:FULL", "SELL:FULL", "BUY_HINT", "SELL_HINT"],
        "scope_rows": scope_rows,
        "sample_scope_rows": scope_rows[:6],
    }


def scope_row_diagnostics(scope_rows: list[Mapping[str, Any]], prev_trade_date: str) -> dict[str, Any]:
    source_counts = Counter(str(row.get("scope_source") or "unknown") for row in scope_rows)
    consumer_counts = Counter(str(row.get("market_data_consumer") or "unknown") for row in scope_rows)
    signal_type_counts: Counter[str] = Counter()
    previous_day_minute_required_count = 0
    previous_day_minute_date_mismatch_count = 0
    for row in scope_rows:
        for signal_type in row.get("allowed_signal_types") or []:
            signal_type_counts[str(signal_type)] += 1
        if row.get("previous_day_minute_required"):
            previous_day_minute_required_count += 1
            if row.get("previous_day_minute_date") != prev_trade_date:
                previous_day_minute_date_mismatch_count += 1
    return {
        "scope_source_counts": dict(sorted(source_counts.items())),
        "market_data_consumer_counts": dict(sorted(consumer_counts.items())),
        "allowed_signal_type_counts": dict(sorted(signal_type_counts.items())),
        "previous_day_minute_required_count": previous_day_minute_required_count,
        "previous_day_minute_date_mismatch_count": previous_day_minute_date_mismatch_count,
    }


def make_index_scope_row_from_pool(pool_row: Mapping[str, Any], dates: DateContext) -> dict[str, Any]:
    direction = str(pool_row["direction"])
    condition_key = str(pool_row["condition_key"])
    signal_types = list(pool_row.get("allowed_signal_types") or [])
    if not signal_types:
        signal_types = signal_types_for_condition_key(condition_key, direction)
    minute_required = minute_required_for_signal_types(signal_types)
    code = str(pool_row.get("code") or "")
    exchange = str(pool_row.get("exchange") or "")
    return {
        "for_trade_date": dates.for_trade_date,
        "source_trade_date": dates.source_trade_date,
        "prev_trade_date": dates.prev_trade_date,
        "identity_key": pool_row.get("index_identity_key") or pool_row.get("identity_key") or f"index:{exchange}:{code}",
        "index_identity_key": pool_row.get("index_identity_key") or pool_row.get("identity_key"),
        "code": code,
        "exchange": exchange,
        "name": pool_row.get("name") or code,
        "lane": pool_row.get("lane"),
        "direction": direction,
        "condition_key": condition_key,
        "condition_periods": list(pool_row.get("condition_periods") or []),
        "allowed_signal_types": signal_types,
        "is_hint_scope": bool(pool_row.get("is_hint_scope")) or has_hint_signal(signal_types),
        "scope_source": "condition_pool",
        "source_condition_pool_id": pool_row.get("index_condition_pool_id"),
        "source_condition_pool_ref": pool_row.get("condition_pool_ref"),
        "reason": "index condition_pool eligible signal scope",
        **scope_static_filter_fields(pool_row),
        "daily_snapshot_required": True,
        "minute_required": minute_required,
        "previous_day_minute_required": previous_day_minute_required_for_signal_types(signal_types),
        "previous_day_minute_date": dates.prev_trade_date if previous_day_minute_required_for_signal_types(signal_types) else None,
        "previous_day_minute_quality_required": previous_day_minute_required_for_signal_types(signal_types),
        "minute_scope_reason": minute_scope_reason_for_signal_types(signal_types),
        "market_data_consumer": market_data_consumer_for_signal_types(signal_types),
        "source_version": pool_row.get("source_version"),
        "scope_status": "planned",
        "raw_json": {
            "condition_pool_run_id": pool_row.get("run_id"),
            "quality_status": pool_row.get("quality_status"),
            "quality_reason": pool_row.get("quality_reason"),
            "scope_policy": RUNTIME_MONITOR_MINUTE_SCOPE_POLICY,
        },
    }


def make_board_scope_row_from_pool(pool_row: Mapping[str, Any], dates: DateContext) -> dict[str, Any]:
    direction = str(pool_row["direction"])
    condition_key = str(pool_row["condition_key"])
    signal_types = list(pool_row.get("allowed_signal_types") or [])
    if not signal_types:
        signal_types = signal_types_for_condition_key(condition_key, direction)
    minute_required = minute_required_for_signal_types(signal_types)
    return {
        "for_trade_date": dates.for_trade_date,
        "source_trade_date": dates.source_trade_date,
        "prev_trade_date": dates.prev_trade_date,
        "identity_key": pool_row.get("board_identity_key") or pool_row.get("identity_key"),
        "board_identity_key": pool_row.get("board_identity_key") or pool_row.get("identity_key"),
        "board_code": pool_row.get("board_code"),
        "board_name": pool_row.get("board_name") or pool_row.get("name"),
        "board_type": pool_row.get("board_type"),
        "lane": pool_row.get("lane"),
        "direction": direction,
        "condition_key": condition_key,
        "condition_periods": list(pool_row.get("condition_periods") or []),
        "allowed_signal_types": signal_types,
        "is_hint_scope": bool(pool_row.get("is_hint_scope")) or has_hint_signal(signal_types),
        "scope_source": "condition_pool",
        "source_condition_pool_id": pool_row.get("board_condition_pool_id"),
        "source_condition_pool_ref": pool_row.get("condition_pool_ref"),
        "reason": "board condition_pool eligible signal scope",
        **scope_static_filter_fields(pool_row),
        "daily_snapshot_required": True,
        "minute_required": minute_required,
        "previous_day_minute_required": previous_day_minute_required_for_signal_types(signal_types),
        "previous_day_minute_date": dates.prev_trade_date if previous_day_minute_required_for_signal_types(signal_types) else None,
        "previous_day_minute_quality_required": previous_day_minute_required_for_signal_types(signal_types),
        "minute_scope_reason": minute_scope_reason_for_signal_types(signal_types),
        "market_data_consumer": market_data_consumer_for_signal_types(signal_types),
        "source_version": pool_row.get("source_version"),
        "scope_status": "planned",
        "raw_json": {
            "condition_pool_run_id": pool_row.get("run_id"),
            "quality_status": pool_row.get("quality_status"),
            "quality_reason": pool_row.get("quality_reason"),
            "scope_policy": RUNTIME_MONITOR_MINUTE_SCOPE_POLICY,
        },
    }


def make_stock_scope_row(pool_row: Mapping[str, Any], dates: DateContext) -> dict[str, Any]:
    direction = str(pool_row["direction"])
    condition_key = str(pool_row["condition_key"])
    signal_types = list(pool_row.get("allowed_signal_types") or [])
    if not signal_types:
        signal_types = signal_types_for_condition_key(condition_key, direction)
    return {
        "for_trade_date": dates.for_trade_date,
        "source_trade_date": dates.source_trade_date,
        "prev_trade_date": dates.prev_trade_date,
        "identity_key": pool_row.get("stock_identity_key") or pool_row.get("identity_key"),
        "stock_identity_key": pool_row.get("stock_identity_key") or pool_row.get("identity_key"),
        "code": pool_row.get("code"),
        "exchange": pool_row.get("exchange"),
        "name": pool_row.get("name"),
        "lane": pool_row.get("lane"),
        "direction": direction,
        "condition_key": condition_key,
        "condition_periods": list(pool_row.get("condition_periods") or []),
        "allowed_signal_types": signal_types,
        "is_hint_scope": bool(pool_row.get("is_hint_scope")) or has_hint_signal(signal_types),
        "scope_source": "condition_pool",
        "source_condition_pool_id": pool_row.get("stock_condition_pool_id"),
        "source_condition_pool_ref": pool_row.get("condition_pool_ref"),
        "reason": "stock condition_pool eligible signal scope",
        "total_mv": pool_row.get("total_mv"),
        "circ_mv": pool_row.get("circ_mv"),
        "market_value_threshold": str(STOCK_SCOPE_MIN_TOTAL_MV_WAN),
        "period_grade_y": pool_row.get("period_grade_y"),
        "period_grade_q": pool_row.get("period_grade_q"),
        "period_grade_m": pool_row.get("period_grade_m"),
        "period_grade_w": pool_row.get("period_grade_w"),
        "period_grade_d": pool_row.get("period_grade_d"),
        "period_transition_y": pool_row.get("period_transition_y"),
        "period_transition_q": pool_row.get("period_transition_q"),
        "period_transition_m": pool_row.get("period_transition_m"),
        "period_transition_w": pool_row.get("period_transition_w"),
        "period_transition_d": pool_row.get("period_transition_d"),
        "level_up_score": pool_row.get("level_up_score"),
        "level_down_score": pool_row.get("level_down_score"),
        "period_trigger_baseline_json": normalize_mapping(pool_row.get("period_trigger_baseline_json") or {}),
        "main_up_anchor": pool_row.get("main_up_anchor"),
        "main_down_anchor": pool_row.get("main_down_anchor"),
        "buy_target_price": pool_row.get("buy_target_price"),
        "sell_target_price": pool_row.get("sell_target_price"),
        "up_sell_reference_period": pool_row.get("up_sell_reference_period"),
        "down_buy_reference_period": pool_row.get("down_buy_reference_period"),
        "clear_sell_ref_period": pool_row.get("clear_sell_ref_period"),
        "period_trigger_baseline_json": normalize_mapping(pool_row.get("period_trigger_baseline_json") or {}),
        "main_index_code": pool_row.get("main_index_code"),
        "preferred_board_code": pool_row.get("preferred_board_code"),
        "pe_core": pool_row.get("pe_core"),
        "score": pool_row.get("score"),
        **{field: pool_row.get(field) for field in STOCK_FINANCIAL_PASS_THROUGH_FIELDS},
        "recommendation_level": pool_row.get("recommendation_level"),
        **canonical_scope_target_fields(pool_row),
        "daily_snapshot_required": True,
        "minute_required": minute_required_for_signal_types(signal_types),
        "previous_day_minute_required": previous_day_minute_required_for_signal_types(signal_types),
        "previous_day_minute_date": dates.prev_trade_date if previous_day_minute_required_for_signal_types(signal_types) else None,
        "previous_day_minute_quality_required": previous_day_minute_required_for_signal_types(signal_types),
        "minute_scope_reason": minute_scope_reason_for_signal_types(signal_types),
        "market_data_consumer": market_data_consumer_for_signal_types(signal_types),
        "source_version": pool_row.get("source_version"),
        "scope_status": "planned",
        "raw_json": {
            "condition_pool_run_id": pool_row.get("run_id"),
            "quality_status": pool_row.get("quality_status"),
            "quality_reason": pool_row.get("quality_reason"),
            "scope_policy": RUNTIME_MONITOR_MINUTE_SCOPE_POLICY,
        },
    }


def scope_static_filter_fields(pool_row: Mapping[str, Any]) -> dict[str, Any]:
    up_sell_reference_period = normalize_scope_reference_period(pool_row.get("up_sell_reference_period"))
    down_buy_reference_period = normalize_scope_reference_period(pool_row.get("down_buy_reference_period"))
    fields = {
        "period_grade_y": pool_row.get("period_grade_y"),
        "period_grade_q": pool_row.get("period_grade_q"),
        "period_grade_m": pool_row.get("period_grade_m"),
        "period_grade_w": pool_row.get("period_grade_w"),
        "period_grade_d": pool_row.get("period_grade_d"),
        "period_transition_y": pool_row.get("period_transition_y"),
        "period_transition_q": pool_row.get("period_transition_q"),
        "period_transition_m": pool_row.get("period_transition_m"),
        "period_transition_w": pool_row.get("period_transition_w"),
        "period_transition_d": pool_row.get("period_transition_d"),
        "level_up_score": pool_row.get("level_up_score"),
        "level_down_score": pool_row.get("level_down_score"),
        "main_up_anchor": pool_row.get("main_up_anchor"),
        "main_down_anchor": pool_row.get("main_down_anchor"),
        "buy_target_price": pool_row.get("buy_target_price"),
        "sell_target_price": pool_row.get("sell_target_price"),
        "up_sell_reference_period": up_sell_reference_period,
        "down_buy_reference_period": down_buy_reference_period,
        "clear_sell_ref_period": up_sell_reference_period,
        "period_trigger_baseline_json": normalize_mapping(pool_row.get("period_trigger_baseline_json") or {}),
        "recommendation_level": pool_row.get("recommendation_level"),
    }
    fields.update(canonical_scope_target_fields(pool_row))
    return fields


def canonical_scope_target_fields(pool_row: Mapping[str, Any]) -> dict[str, Any]:
    fields = {field: pool_row.get(field) for field in SYMMETRY_TARGET_FIELDS}
    if all(value in (None, "", {}) for value in fields.values()):
        fields.update(canonical_target_fields_for_direction(pool_row, str(pool_row.get("direction") or "")))
    for field in SYMMETRY_TARGET_FIELDS:
        fields.setdefault(field, None)
    return fields


def normalize_scope_reference_period(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text if text in ORDINARY_PERIODS else "D"


def signal_types_for_direction(direction: str) -> list[str]:
    if direction == "buy":
        return list(BUY_SCOPE_SIGNAL_TYPES)
    if direction == "sell":
        return list(SELL_SCOPE_SIGNAL_TYPES)
    raise ValueError(f"unsupported direction: {direction!r}")


def signal_types_for_condition_key(condition_key: str, direction: str) -> list[str]:
    if condition_key == "BUY_HINT":
        return ["BUY_HINT"]
    if condition_key == "SELL_HINT":
        return ["SELL_HINT"]
    if condition_key == "BUY:FULL":
        return ["BUY:FULL"]
    if condition_key == "SELL:FULL":
        return ["SELL:FULL"]
    if condition_key.startswith("BUY:"):
        return ["BUY"]
    if condition_key.startswith("SELL:"):
        return ["SELL"]
    return signal_types_for_direction(direction)


def is_stock_condition_key_scope_eligible(condition_key: str) -> bool:
    if condition_key in {"BUY_HINT", "SELL_HINT", "BUY:FULL", "SELL:FULL"}:
        return True
    if condition_key.startswith("BUY:"):
        return ordinary_period_key_is_valid(condition_key.removeprefix("BUY:"))
    if condition_key.startswith("SELL:"):
        return ordinary_period_key_is_valid(condition_key.removeprefix("SELL:"))
    return False


def stock_total_mv_is_scope_eligible(total_mv: Any) -> bool:
    if total_mv in (None, ""):
        return False
    try:
        return Decimal(str(total_mv)) >= STOCK_SCOPE_MIN_TOTAL_MV_WAN
    except (InvalidOperation, ValueError):
        return False


def ordinary_period_key_is_valid(period_key: str) -> bool:
    periods = [period.strip() for period in period_key.split(",") if period.strip()]
    return bool(periods) and all(period in ORDINARY_PERIODS for period in periods)


def has_hint_signal(signal_types: list[str]) -> bool:
    return "BUY_HINT" in signal_types or "SELL_HINT" in signal_types


def minute_required_for_signal_types(signal_types: list[str]) -> bool:
    return any(signal_type in MINUTE_SIGNAL_TYPES for signal_type in signal_types)


def previous_day_minute_required_for_signal_types(signal_types: list[str]) -> bool:
    return minute_required_for_signal_types(signal_types)


def minute_scope_reason_for_signal_types(signal_types: list[str]) -> str | None:
    if minute_required_for_signal_types(signal_types):
        return "condition_pool runtime monitor scope requires minute and previous day minute bars"
    return None


def market_data_consumer_for_signal_types(signal_types: list[str]) -> str:
    return "both" if minute_required_for_signal_types(signal_types) else "trigger_daily_snapshot"


def build_scope_quality_items(
    *,
    ready_check: Mapping[str, Any],
    date_context: DateContext,
    condition_pool_report: Mapping[str, Any],
    index_scope: Mapping[str, Any],
    board_scope: Mapping[str, Any],
    stock_scope: Mapping[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    items.append(quality_item("P0", "passed" if ready_check.get("passed") else "failed", "condition_source_ready", "入库层条件源 ready check"))
    items.append(quality_item("P0", "passed", "for_trade_date_inferred", "for_trade_date 由 common_trade_calendar 推导", actual=date_context.for_trade_date))
    items.append(quality_item("P0", "passed", "prev_trade_date_match", "prev_trade_date(for_trade_date) 等于 source_trade_date", expected=date_context.source_trade_date, actual=date_context.prev_trade_date))
    items.append(quality_item("P0", "passed", "no_database_write", "minute_target_scope dry-run 不写数据库"))
    items.append(quality_item("P0", "passed", "no_minute_kline_pull", "条件层只输出行情范围，不拉一分钟 K"))
    pool_p0_count = int(condition_pool_report.get("quality", {}).get("p0_count") or 0)
    items.append(
        quality_item(
            "P0",
            "passed" if pool_p0_count == 0 else "failed",
            "condition_pool_dry_run_p0_clean",
            "minute_target_scope dry-run 必须来自 P0=0 的 condition_pool dry-run",
            expected="0",
            actual=str(pool_p0_count),
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

    all_scope_rows = [
        row
        for scope in (index_scope, board_scope, stock_scope)
        for row in scope.get("scope_rows") or []
    ]
    previous_day_mismatches = [
        str(row.get("identity_key") or row.get("code") or row.get("board_code"))
        for row in all_scope_rows
        if row.get("previous_day_minute_required") and row.get("previous_day_minute_date") != date_context.prev_trade_date
    ]
    invalid_signal_types = sorted(
        {
            str(signal_type)
            for row in all_scope_rows
            for signal_type in row.get("allowed_signal_types") or []
            if signal_type not in STANDARD_SIGNAL_TYPES
        }
    )
    invalid_consumers = sorted(
        {
            str(row.get("market_data_consumer"))
            for row in all_scope_rows
            if row.get("market_data_consumer") not in {"trigger_daily_snapshot", "action_minute_bar", "both"}
        }
    )
    missing_baseline_rows = [
        str(row.get("identity_key") or row.get("code") or row.get("board_code"))
        for row in all_scope_rows
        if not period_trigger_baseline_has_required_shape(row.get("period_trigger_baseline_json"))
    ]
    missing_required_baseline_rows = [
        {
            "identity_key": str(row.get("identity_key") or row.get("code") or row.get("board_code")),
            "condition_key": str(row.get("condition_key") or ""),
            "missing_periods": missing_required_period_trigger_baseline_periods(row),
        }
        for row in all_scope_rows
        if missing_required_period_trigger_baseline_periods(row)
    ]
    items.extend(
        [
            quality_item(
                "P0",
                "passed" if not previous_day_mismatches else "failed",
                "previous_day_minute_date_match",
                "previous_day_minute_required=true 时 previous_day_minute_date 必须等于 prev_trade_date",
                expected=date_context.prev_trade_date,
                actual="passed" if not previous_day_mismatches else ",".join(previous_day_mismatches[:20]),
            ),
            quality_item(
                "P0",
                "passed" if not invalid_signal_types else "failed",
                "scope_allowed_signal_type_whitelist",
                "minute_target_scope 只能声明 N2 canonical signal_type，不表达 30m action mark",
                expected=",".join(STANDARD_SIGNAL_TYPES),
                actual="whitelist_only" if not invalid_signal_types else ",".join(invalid_signal_types),
            ),
            quality_item(
                "P0",
                "passed" if not invalid_consumers else "failed",
                "scope_market_data_consumer_whitelist",
                "market_data_consumer 只能是 trigger_daily_snapshot/action_minute_bar/both",
                expected="trigger_daily_snapshot,action_minute_bar,both",
                actual="whitelist_only" if not invalid_consumers else ",".join(invalid_consumers),
            ),
            quality_item(
                "P0",
                "passed" if not missing_baseline_rows else "failed",
                "period_trigger_baseline_json_full_chain_scope",
                "minute_target_scope dry-run 必须从 condition_pool 继承 period_trigger_baseline_json，供 N4 本地化",
                expected="missing=0",
                actual="0" if not missing_baseline_rows else str(len(missing_baseline_rows)),
                details={"missing_samples": missing_baseline_rows[:20]},
            ),
            quality_item(
                "P0",
                "passed" if not missing_required_baseline_rows else "failed",
                "period_trigger_baseline_required_periods_scope",
                "minute_target_scope 不得承接 condition_key 必要周期缺 previous_entity_high/low 或金额基准的交易链路行",
                expected="missing_required_periods=0",
                actual="0" if not missing_required_baseline_rows else str(len(missing_required_baseline_rows)),
                details={"missing_required_samples": missing_required_baseline_rows[:20]},
            ),
        ]
    )

    items.append(
        quality_item(
            "P0",
            "passed" if index_scope.get("condition_pool_exists") and index_scope.get("condition_pool_source") in {"condition_pool", "condition_pool_dry_run", "persisted_condition_pool"} else "failed",
            "index_scope_from_condition_pool",
            "指数 minute_target_scope 必须来自 index_condition_pool 或等价 condition_pool dry-run",
            expected="condition_pool/condition_pool_dry_run",
            actual=str(index_scope.get("condition_pool_source") or "missing"),
        )
    )
    pool_preview = condition_pool_report.get("pool_preview") or {}
    index_policy = (
        dict(pool_preview.get("index", {}).get("condition_pool_selection_policy") or {})
        or default_condition_pool_policy("index")
    )
    board_policy = (
        dict(pool_preview.get("board", {}).get("condition_pool_selection_policy") or {})
        or default_condition_pool_policy("board")
    )
    allowed_index_identities = allowed_index_identity_keys_from_policy(index_policy)
    allowed_board_types = allowed_board_types_from_policy(board_policy)
    index_outside = sorted({
        str(row.get("identity_key") or row.get("index_identity_key") or row.get("code"))
        for row in index_scope.get("scope_rows") or []
        if allowed_index_identities is not None
        and str(row.get("identity_key") or row.get("index_identity_key") or "") not in allowed_index_identities
    })
    items.append(
        quality_item(
            "P0",
            "passed" if not index_outside else "failed",
            "index_scope_default_universe",
            "指数 minute_target_scope 只能来自本次 policy 允许的 condition_pool 行",
            expected="all_index_identities" if allowed_index_identities is None else ",".join(sorted(allowed_index_identities)),
            actual="passed" if not index_outside else ",".join(index_outside[:20]),
        )
    )

    items.append(
        quality_item(
            "P0",
            "passed" if board_scope.get("condition_pool_exists") and board_scope.get("condition_pool_source") in {"condition_pool", "condition_pool_dry_run", "persisted_condition_pool"} else "failed",
            "board_scope_from_condition_pool",
            "板块 minute_target_scope 必须来自 board_condition_pool 或等价 condition_pool dry-run",
            expected="condition_pool/condition_pool_dry_run",
            actual=str(board_scope.get("condition_pool_source") or "missing"),
        )
    )
    board_outside = sorted({
        str(row.get("board_identity_key") or row.get("board_code"))
        for row in board_scope.get("scope_rows") or []
        if str(row.get("board_type") or "") not in allowed_board_types
    })
    items.append(
        quality_item(
            "P0",
            "passed" if not board_outside else "failed",
            "board_scope_default_universe",
            "板块 minute_target_scope 只能来自本次 policy 允许的 board_type condition_pool 行",
            expected="board_type in " + ",".join(sorted(allowed_board_types)),
            actual="passed" if not board_outside else ",".join(board_outside[:20]),
        )
    )

    items.append(
        quality_item(
            "P0",
            "passed" if stock_scope.get("condition_pool_exists") and stock_scope.get("condition_pool_source") in {"condition_pool", "condition_pool_dry_run", "persisted_condition_pool"} else "failed",
            "stock_scope_from_condition_pool",
            "个股 minute_target_scope 必须来自 stock_condition_pool 或等价 condition_pool dry-run",
            expected="condition_pool/condition_pool_dry_run",
            actual=str(stock_scope.get("condition_pool_source") or "missing"),
        )
    )
    if not stock_scope.get("condition_pool_exists"):
        items.append(
            quality_item(
                "P1",
                "warning",
                "stock_condition_pool_missing",
                "stock_minute_target_scope 个股范围必须来自 stock_condition_pool，并过滤 total_mv >= 100 亿；当前 schema 未迁移或表不存在",
                expected="stock_condition_pool",
                actual="missing",
            )
        )
    elif int(stock_scope.get("scope_row_count") or 0) == 0:
        items.append(
            quality_item(
                "P1",
                "warning",
                "stock_condition_scope_empty",
                "stock_condition_pool 暂无具备 BUY/SELL/FULL/Hint 条件的个股范围",
                expected=">0 when condition_pool is generated",
                actual="0",
            )
        )
    invalid_stock_market_value_rows = [
        str(row.get("identity_key"))
        for row in stock_scope.get("scope_rows") or []
        if not stock_total_mv_is_scope_eligible(row.get("total_mv"))
    ]
    items.append(
        quality_item(
            "P0",
            "passed" if not invalid_stock_market_value_rows else "failed",
            "stock_scope_total_mv_threshold",
            "stock_minute_target_scope 个股必须满足 total_mv >= 100 亿",
            expected=f">={STOCK_SCOPE_MIN_TOTAL_MV_WAN}",
            actual="passed" if not invalid_stock_market_value_rows else ",".join(invalid_stock_market_value_rows[:20]),
        )
    )
    if stock_scope.get("condition_pool_exists") and int(stock_scope.get("missing_total_mv_count") or 0) > 0:
        items.append(
            quality_item(
                "P1",
                "warning",
                "stock_scope_total_mv_missing",
                "部分具备条件池资格的个股缺少 total_mv，已排除出 stock_minute_target_scope",
                expected="total_mv >= 100亿",
                actual=str(stock_scope.get("missing_total_mv_count")),
            )
        )
    if stock_scope.get("condition_pool_exists") and not stock_scope.get("source_condition_pool_ids_available", True):
        items.append(
            quality_item(
                "P2",
                "warning",
                "source_condition_pool_id_unavailable_in_dry_run",
                "N2-D 使用 condition_pool dry-run 结果；正式 source_condition_pool_id 要等 execute/migration 后才有",
            )
        )
    return items
