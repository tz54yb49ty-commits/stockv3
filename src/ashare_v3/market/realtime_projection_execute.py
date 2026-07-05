"""N3-B2 realtime projection metric run-once executor.

This module is intentionally scoped to N3 market-data projection facts. It
does not write common_event_outbox, consume events, update existing
MarketSnapshotUpdated payloads, enter downstream layers, or start workers.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP, getcontext
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_execute_connect
from psycopg.types.json import Jsonb

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.b2_projection_proof import (
    B2_DIRECT_30M_K_SOURCE_MODE,
    b2_30m_projection_adapter_contract,
    build_b2_30m_projection_proof_fields,
)
from ashare_v3.market.minute_label_normalization import (
    MinuteLabelNormalizationError,
    minute_label_normalization_trace,
    normalize_mootdx_intraday_1m_labels,
)
from ashare_v3.market.previous_day_preload_execute import json_safe, utc_now_iso, write_json, write_text


getcontext().prec = 28

ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_B2_CONTRACT_JSON_PATH = "docs/N3_B2_realtime_projection_execute_contract.json"
DEFAULT_B2_PREFLIGHT_JSON_PATH = "docs/N3_B2_realtime_projection_execute_preflight.json"
DEFAULT_B2_DRY_RUN_JSON_PATH = "docs/N3_B2_realtime_projection_dry_run_after_A1_fill_and_C1.json"
DEFAULT_B2_JSON_REPORT_PATH = "docs/N3_B2_realtime_projection_execute_report.json"
DEFAULT_B2_MD_REPORT_PATH = "docs/N3_B2_REALTIME_PROJECTION_EXECUTE_REPORT.md"
DEFAULT_B2_ROLLBACK_SQL_PATH = "sql/N3_B2_realtime_projection_rollback.sql"

PROJECTION_SCHEMA_VERSION = "n3.realtime_projection.v1"
PROJECTION_METRIC_SCOPE = "realtime_projection_metric"
B2_QUALITY_LAYER_SCOPE = "market_data_run"
PROJECTION_WINDOW_KIND = "active_30m_bucket_projection"
LIVE_CURRENT_1M_SOURCE_MODE = "live_current_1m"
DIRECT_30M_K_SOURCE_MODE = B2_DIRECT_30M_K_SOURCE_MODE
ASSET_CONFIG = {
    "stock": {
        "snapshot_table": "stock_realtime_daily_snapshot",
        "minute_table": "stock_minute_bar_1m",
        "projection_table": "stock_realtime_projection_metric",
        "identity_column": "stock_identity_key",
    },
    "index": {
        "snapshot_table": "index_realtime_daily_snapshot",
        "minute_table": "index_minute_bar_1m",
        "projection_table": "index_realtime_projection_metric",
        "identity_column": "index_identity_key",
    },
    "board": {
        "snapshot_table": "board_realtime_daily_snapshot",
        "minute_table": "board_minute_bar_1m",
        "projection_table": "board_realtime_projection_metric",
        "identity_column": "board_identity_key",
    },
}
TRADING_BUCKETS = (
    ("09:30", "10:00"),
    ("10:00", "10:30"),
    ("10:30", "11:00"),
    ("11:00", "11:30"),
    ("13:00", "13:30"),
    ("13:30", "14:00"),
    ("14:00", "14:30"),
    ("14:30", "15:00"),
)
ALLOWED_WRITE_TABLES = (
    "common_market_data_run",
    "common_market_data_quality_item",
    "stock_realtime_projection_metric",
    "index_realtime_projection_metric",
    "board_realtime_projection_metric",
)
FORBIDDEN_WRITE_TABLES = (
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "stock_realtime_daily_snapshot",
    "index_realtime_daily_snapshot",
    "board_realtime_daily_snapshot",
    "stock_minute_bar_1m",
    "index_minute_bar_1m",
    "board_minute_bar_1m",
)
ALLOWED_QUALITY_DATA_DOMAINS = ("common", "stock", "index", "board")
ALLOWED_QUALITY_LAYER_SCOPES = (
    "active_condition_run",
    "market_data_subscription_candidate",
    "market_data_subscription_dedup",
    "market_data_pull_plan",
    "market_data_run",
)
PROJECTION_QUALITY_TABLE_BY_DOMAIN = {
    "common": "stock/index/board_realtime_projection_metric",
    "stock": "stock_realtime_projection_metric",
    "index": "index_realtime_projection_metric",
    "board": "board_realtime_projection_metric",
}


class RealtimeProjectionExecuteError(RuntimeError):
    """Raised when N3-B2 execute violates its reviewed contract."""


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def resolve_source_run_ids(source_runs: Mapping[str, Any], singular_key: str, plural_key: str) -> list[str]:
    """Return source run ids from legacy single-run and additive multi-run fields."""

    values: list[str] = []
    singular_value = source_runs.get(singular_key)
    if singular_value:
        values.append(str(singular_value))
    plural_value = source_runs.get(plural_key) or []
    if isinstance(plural_value, str):
        values.append(plural_value)
    else:
        values.extend(str(value) for value in plural_value if value)
    resolved = list(dict.fromkeys(value for value in values if value))
    if not resolved:
        raise RealtimeProjectionExecuteError(f"N3-B2 blocked: missing source run id field {singular_key}/{plural_key}")
    return resolved


def projection_source_mode(contract: Mapping[str, Any]) -> str:
    source_runs = contract.get("source_runs") if isinstance(contract.get("source_runs"), Mapping) else {}
    source_contract = contract.get("source_contract") if isinstance(contract.get("source_contract"), Mapping) else {}
    return str(
        contract.get("source_mode")
        or source_runs.get("source_mode")
        or source_contract.get("source_mode")
        or ""
    )


def projection_uses_live_current_1m(contract: Mapping[str, Any]) -> bool:
    return projection_source_mode(contract) == LIVE_CURRENT_1M_SOURCE_MODE


def projection_uses_direct_30m_k(contract: Mapping[str, Any]) -> bool:
    return projection_source_mode(contract) == DIRECT_30M_K_SOURCE_MODE


def projection_c1_dependency(contract: Mapping[str, Any]) -> bool:
    if projection_uses_live_current_1m(contract) or projection_uses_direct_30m_k(contract):
        return False
    return True


def live_current_minute_source_run_id(contract: Mapping[str, Any]) -> str | None:
    source_runs = contract.get("source_runs") if isinstance(contract.get("source_runs"), Mapping) else {}
    value = (
        contract.get("source_live_minute_run_id")
        or source_runs.get("source_live_minute_run_id")
        or source_runs.get("live_current_minute_run_id")
    )
    return str(value) if value else None


def today_minute_run_ids_for_contract(contract: Mapping[str, Any]) -> list[str]:
    if projection_uses_live_current_1m(contract):
        live_run_id = live_current_minute_source_run_id(contract)
        return [live_run_id] if live_run_id else []
    if projection_uses_direct_30m_k(contract):
        return []
    return resolve_source_run_ids(contract["source_runs"], "today_minute_run_id", "today_minute_run_ids")


def source_30m_k_run_ids_for_contract(contract: Mapping[str, Any]) -> list[str]:
    source_runs = contract.get("source_runs") if isinstance(contract.get("source_runs"), Mapping) else {}
    if not projection_uses_direct_30m_k(contract):
        return []
    return resolve_source_run_ids(source_runs, "source_30m_k_run_id", "source_30m_k_run_ids")


def source_runs_with_live_trace(contract: Mapping[str, Any]) -> dict[str, Any]:
    source_runs = dict(contract.get("source_runs") or {})
    source_mode = projection_source_mode(contract)
    if source_mode:
        source_runs.setdefault("source_mode", source_mode)
    live_run_id = live_current_minute_source_run_id(contract)
    if live_run_id:
        source_runs.setdefault("source_live_minute_run_id", live_run_id)
    source_30m_run_ids = source_30m_k_run_ids_for_contract(contract) if projection_uses_direct_30m_k(contract) else []
    if source_30m_run_ids:
        source_runs.setdefault("source_30m_k_run_ids", source_30m_run_ids)
        source_runs.setdefault("source_30m_k_run_id", source_30m_run_ids[0])
    return source_runs


def run_realtime_projection_metric_execute(
    *,
    dsn: str,
    contract_path: str = DEFAULT_B2_CONTRACT_JSON_PATH,
    preflight_path: str = DEFAULT_B2_PREFLIGHT_JSON_PATH,
    dry_run_path: str = DEFAULT_B2_DRY_RUN_JSON_PATH,
    json_report_path: str = DEFAULT_B2_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_B2_MD_REPORT_PATH,
    rollback_sql_path: str = DEFAULT_B2_ROLLBACK_SQL_PATH,
    projection_run_id: str | None = None,
    for_trade_date: str | None = None,
    execute: bool = False,
    user_confirmed: bool = False,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Execute one reviewed N3-B2 projection fact write, then exit."""

    contract = read_json(contract_path)
    preflight = read_json(preflight_path)
    dry_run = read_json(dry_run_path)
    ensure_projection_execute_contract(
        contract,
        preflight,
        execute=execute,
        user_confirmed=user_confirmed,
        projection_run_id=projection_run_id,
        for_trade_date=for_trade_date,
    )
    ensure_dry_run_matches_contract(dry_run, contract)

    resolved_run_id = str(contract["projection_run_id"])
    source_runs = contract["source_runs"]
    dates = contract["dates"]
    started_at = utc_now_iso()

    if projection_contract_requests_snapshot_only_noop(contract):
        if progress_callback:
            progress_callback("N3-B2 auction/snapshot-only metric path is not materialized; returning NOOP without writes")
        rollback_sql = build_projection_rollback_sql(resolved_run_id)
        write_text(rollback_sql_path, rollback_sql)
        report = build_snapshot_only_projection_noop_report(
            contract=contract,
            started_at=started_at,
            contract_path=contract_path,
            preflight_path=preflight_path,
            dry_run_path=dry_run_path,
            rollback_sql_path=rollback_sql_path,
        )
        write_json(json_report_path, report)
        write_text(markdown_report_path, format_projection_execute_report(report))
        return report

    pre_backup = capture_projection_execute_snapshot(
        dsn,
        projection_run_id=resolved_run_id,
        source_runs=source_runs_with_live_trace(contract),
    )
    ensure_clean_projection_target(pre_backup, resolved_run_id)
    ensure_source_runs_passed(pre_backup, contract)

    projection_time_policy_noop = detect_projection_time_policy_noop(dsn=dsn, contract=contract)
    if projection_time_policy_noop.get("should_noop"):
        if progress_callback:
            progress_callback("N3-B2 source snapshot_time is outside trading buckets; returning NOOP without writes")
        rollback_sql = build_projection_rollback_sql(resolved_run_id)
        write_text(rollback_sql_path, rollback_sql)
        report = build_projection_noop_report(
            contract=contract,
            started_at=started_at,
            contract_path=contract_path,
            preflight_path=preflight_path,
            dry_run_path=dry_run_path,
            rollback_sql_path=rollback_sql_path,
            pre_backup=pre_backup,
            projection_time_policy_noop=projection_time_policy_noop,
        )
        write_json(json_report_path, report)
        write_text(markdown_report_path, format_projection_execute_report(report))
        return report

    projection_time_alignment = detect_projection_time_alignment_blocker(dsn=dsn, contract=contract)
    if projection_time_alignment.get("blocked"):
        raise RealtimeProjectionExecuteError(
            "N3-B2 blocked: snapshot_time_after_c1_latest_closed_minute "
            + json.dumps(json_safe(projection_time_alignment), ensure_ascii=False, sort_keys=True)
        )

    if progress_callback:
        progress_callback("N3-B2 building realtime projection rows")
    projection_rows = build_projection_rows(dsn=dsn, contract=contract)
    validate_projection_rows_against_contract(projection_rows, contract)

    quality_items = build_projection_quality_items(
        contract=contract,
        rows=projection_rows,
        pre_backup=pre_backup,
    )
    quality_counts = count_quality_severities(quality_items)
    status = "passed" if quality_counts["P0"] == 0 else "failed"

    if progress_callback:
        progress_callback(f"N3-B2 writing {len(projection_rows)} projection facts")
    write_projection_execute_transaction(
        dsn=dsn,
        contract=contract,
        rows=projection_rows,
        quality_items=quality_items,
        status=status,
        started_at=started_at,
        contract_path=contract_path,
        preflight_path=preflight_path,
        dry_run_path=dry_run_path,
    )

    post_backup = capture_projection_execute_snapshot(
        dsn,
        projection_run_id=resolved_run_id,
        source_runs=source_runs_with_live_trace(contract),
    )
    rollback_sql = build_projection_rollback_sql(resolved_run_id)
    write_text(rollback_sql_path, rollback_sql)

    row_summary = summarize_projection_rows(projection_rows)
    report = {
        "stage": "N3-B2",
        "layer_role": "N3_market_data",
        "execution_mode": "realtime_projection_metric_run_once_execute",
        "projection_run_id": resolved_run_id,
        "source_condition_run_id": source_runs["source_condition_run_id"],
        "subscription_run_id": source_runs["subscription_run_id"],
        "snapshot_run_id": source_runs.get("snapshot_run_id"),
        "source_30m_k_run_id": source_runs.get("source_30m_k_run_id"),
        "preload_run_id": source_runs["preload_run_id"],
        "today_minute_run_id": source_runs.get("today_minute_run_id") or live_current_minute_source_run_id(contract),
        "source_mode": projection_source_mode(contract) or None,
        "c1_dependency": projection_c1_dependency(contract),
        "for_trade_date": dates["for_trade_date"],
        "source_trade_date": dates["source_trade_date"],
        "prev_trade_date": dates["prev_trade_date"],
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "contract_path": contract_path,
        "preflight_path": preflight_path,
        "dry_run_path": dry_run_path,
        "rollback_sql_path": rollback_sql_path,
        "expected_projection_rows": contract["expected_projection_rows"],
        "actual_projection_rows": row_summary,
        "write_result": {
            "projection_rows_written": len(projection_rows),
            "quality_item_rows_written": len(quality_items),
            "event_outbox_rows_written": 0,
            "writes_outbox": False,
            "updates_market_snapshot_payload": False,
        },
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
        },
        "pre_execute": pre_backup,
        "post_execute": post_backup,
        "side_effects": {
            "writes_performed": True,
            "projection_fact_written": len(projection_rows) > 0,
            "quality_item_written": len(quality_items) > 0,
            "event_outbox_written": False,
            "event_inbox_written": False,
            "outbox_consumed": False,
            "market_snapshot_payload_modified": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_projection_execute_report(report))
    return report


def projection_contract_requests_snapshot_only_noop(contract: Mapping[str, Any]) -> bool:
    """Return true for reviewed auction/snapshot-only B2 paths that must not touch DB.

    The first auction path can have a passed B1 snapshot before any C1 closed-minute
    run exists. Until a dedicated snapshot-only metric writer is available, the
    reviewed behavior is an explicit NOOP_PASS instead of trying to resolve a
    non-existent today_minute_run_id.
    """

    source_runs = contract.get("source_runs") or {}
    source_requirements = contract.get("source_requirements") or {}
    policy = contract.get("snapshot_only_execution_policy") or {}
    return (
        str(contract.get("projection_input_mode") or "") == "auction_or_snapshot_only"
        and not bool(source_requirements.get("requires_today_minute_run", True))
        and not source_runs.get("today_minute_run_id")
        and bool(policy.get("noop_pass_no_write_allowed"))
    )


def build_snapshot_only_projection_noop_report(
    *,
    contract: Mapping[str, Any],
    started_at: str,
    contract_path: str,
    preflight_path: str,
    dry_run_path: str,
    rollback_sql_path: str,
) -> dict[str, Any]:
    """Build a no-write B2 report for reviewed auction/snapshot-only policy."""

    source_runs = contract["source_runs"]
    dates = contract["dates"]
    source_trade_date = str(dates.get("source_trade_date") or dates.get("prev_trade_date") or dates["for_trade_date"])
    prev_trade_date = str(dates.get("prev_trade_date") or source_trade_date)
    row_summary = summarize_projection_rows([])
    policy = dict(contract.get("snapshot_only_execution_policy") or {})
    trace_json = {
        "projection_input_mode": contract.get("projection_input_mode"),
        "source_runs": json_safe(source_runs),
        "source_requirements": json_safe(contract.get("source_requirements") or {}),
        "snapshot_run_id": source_runs.get("snapshot_run_id"),
        "subscription_run_id": source_runs.get("subscription_run_id"),
        "preload_run_id": source_runs.get("preload_run_id"),
        "source_condition_run_id": source_runs.get("source_condition_run_id"),
        "today_minute_run_id": source_runs.get("today_minute_run_id"),
        "today_minute_run_required": False,
        "closed_minute_forged": False,
        "minute_bar_closed_written": False,
        "writes_outbox": False,
        "consumes_outbox": False,
        "n4_n5_n6_entered": False,
    }
    snapshot_only_metric_policy = {
        "is_auction_virtual": bool(policy.get("is_auction_virtual")),
        "period_source": str(policy.get("period_source") or "snapshot_only_no_closed_1m"),
        "quality_status": str(policy.get("quality_status") or "pending_market_data"),
        "trace_json": trace_json,
        "no_closed_1m_forged": True,
        "minute_bar_closed_written": False,
    }
    quality_items = [
        quality_item(
            "P1",
            "warning",
            "n3_b2_auction_snapshot_only_pending_metric_noop",
            "B2 auction/snapshot-only metric materialization is not ready; returning no-write NOOP_PASS",
            expected="snapshot-only metric writer ready or safe no-write noop",
            actual=json.dumps(json_safe(snapshot_only_metric_policy), ensure_ascii=False, sort_keys=True),
        )
    ]
    quality_counts = count_quality_severities(quality_items)
    pre_execute = {
        "db_probe_skipped": True,
        "reason": "auction_or_snapshot_only_no_today_minute_run",
        "projection_run_exists": False,
        "projection_run_table_counts": {
            "stock_realtime_projection_metric": 0,
            "index_realtime_projection_metric": 0,
            "board_realtime_projection_metric": 0,
        },
        "quality_rows_for_projection_run": 0,
        "outbox_rows_for_projection_run": 0,
        "inbox_rows_for_projection_run": 0,
        "checkpoint_refs_for_projection_run": 0,
    }
    return {
        "stage": "N3-B2",
        "layer_role": "N3_market_data",
        "result": "NOOP_PASS",
        "noop_reason": str(policy.get("noop_reason") or "auction_or_snapshot_only_waiting_for_metric_runner"),
        "execution_mode": "realtime_projection_metric_run_once_execute",
        "projection_run_id": contract["projection_run_id"],
        "source_condition_run_id": source_runs["source_condition_run_id"],
        "subscription_run_id": source_runs["subscription_run_id"],
        "snapshot_run_id": source_runs.get("snapshot_run_id"),
        "source_30m_k_run_id": source_runs.get("source_30m_k_run_id"),
        "preload_run_id": source_runs["preload_run_id"],
        "today_minute_run_id": source_runs.get("today_minute_run_id"),
        "for_trade_date": dates["for_trade_date"],
        "source_trade_date": source_trade_date,
        "prev_trade_date": prev_trade_date,
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "contract_path": contract_path,
        "preflight_path": preflight_path,
        "dry_run_path": dry_run_path,
        "rollback_sql_path": rollback_sql_path,
        "expected_projection_rows": contract["expected_projection_rows"],
        "actual_projection_rows": row_summary,
        "snapshot_only_metric_policy": snapshot_only_metric_policy,
        "write_result": {
            "projection_rows_written": 0,
            "quality_item_rows_written": 0,
            "event_outbox_rows_written": 0,
            "writes_outbox": False,
            "updates_market_snapshot_payload": False,
        },
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
            "quality_rows_written": 0,
        },
        "pre_execute": pre_execute,
        "post_execute": pre_execute,
        "side_effects": {
            "writes_performed": False,
            "projection_fact_written": False,
            "quality_item_written": False,
            "event_outbox_written": False,
            "event_inbox_written": False,
            "outbox_consumed": False,
            "market_snapshot_payload_modified": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }


def build_projection_noop_report(
    *,
    contract: Mapping[str, Any],
    started_at: str,
    contract_path: str,
    preflight_path: str,
    dry_run_path: str,
    rollback_sql_path: str,
    pre_backup: Mapping[str, Any],
    projection_time_policy_noop: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a no-write B2 report for reviewed off-bucket source snapshot_time policy."""

    source_runs = contract["source_runs"]
    dates = contract["dates"]
    row_summary = summarize_projection_rows([])
    quality_items = [
        quality_item(
            "P1",
            "warning",
            "n3_b2_fact_only_source_snapshot_time_off_bucket_deferred",
            "Fact-only B2 deferred because source snapshot_time is outside reviewed trading buckets",
            expected="source snapshot_time inside trading bucket or no-op defer",
            actual=json.dumps(json_safe(projection_time_policy_noop), ensure_ascii=False, sort_keys=True),
        )
    ]
    quality_counts = count_quality_severities(quality_items)
    return {
        "stage": "N3-B2",
        "layer_role": "N3_market_data",
        "result": "NOOP_PASS",
        "noop_reason": projection_time_policy_noop.get("reason", "off_bucket_source_snapshot_time"),
        "execution_mode": "realtime_projection_metric_run_once_execute",
        "projection_run_id": contract["projection_run_id"],
        "source_condition_run_id": source_runs["source_condition_run_id"],
        "subscription_run_id": source_runs["subscription_run_id"],
        "snapshot_run_id": source_runs.get("snapshot_run_id"),
        "source_30m_k_run_id": source_runs.get("source_30m_k_run_id"),
        "preload_run_id": source_runs["preload_run_id"],
        "today_minute_run_id": source_runs.get("today_minute_run_id") or live_current_minute_source_run_id(contract),
        "source_mode": projection_source_mode(contract) or None,
        "c1_dependency": projection_c1_dependency(contract),
        "for_trade_date": dates["for_trade_date"],
        "source_trade_date": dates["source_trade_date"],
        "prev_trade_date": dates["prev_trade_date"],
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "contract_path": contract_path,
        "preflight_path": preflight_path,
        "dry_run_path": dry_run_path,
        "rollback_sql_path": rollback_sql_path,
        "expected_projection_rows": contract["expected_projection_rows"],
        "actual_projection_rows": row_summary,
        "projection_time_policy_noop": projection_time_policy_noop,
        "write_result": {
            "projection_rows_written": 0,
            "quality_item_rows_written": 0,
            "event_outbox_rows_written": 0,
            "writes_outbox": False,
            "updates_market_snapshot_payload": False,
        },
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
            "quality_rows_written": 0,
        },
        "pre_execute": pre_backup,
        "post_execute": pre_backup,
        "side_effects": {
            "writes_performed": False,
            "projection_fact_written": False,
            "quality_item_written": False,
            "event_outbox_written": False,
            "event_inbox_written": False,
            "outbox_consumed": False,
            "market_snapshot_payload_modified": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }


def ensure_projection_execute_contract(
    contract: Mapping[str, Any],
    preflight: Mapping[str, Any],
    *,
    execute: bool,
    user_confirmed: bool,
    projection_run_id: str | None,
    for_trade_date: str | None,
) -> None:
    if not execute:
        raise RealtimeProjectionExecuteError("N3-B2 projection execute requires explicit --execute")
    if not user_confirmed:
        raise RealtimeProjectionExecuteError("N3-B2 projection execute requires explicit --user-confirmed")
    if contract.get("stage") != "N3-B2-realtime-projection-execute-contract":
        raise RealtimeProjectionExecuteError("N3-B2 blocked: contract stage mismatch")
    if contract.get("layer_role") != "N3_market_data":
        raise RealtimeProjectionExecuteError("N3-B2 blocked: contract layer_role mismatch")
    if contract.get("execution_mode") != "realtime_projection_metric_run_once_execute":
        raise RealtimeProjectionExecuteError("N3-B2 blocked: execution_mode mismatch")
    if preflight.get("stage") != "N3-B2-realtime-projection-execute-preflight":
        raise RealtimeProjectionExecuteError("N3-B2 blocked: preflight stage mismatch")
    if preflight.get("result") != "PREFLIGHT_PASS":
        raise RealtimeProjectionExecuteError("N3-B2 blocked: preflight did not pass")
    if projection_run_id and projection_run_id != str(contract.get("projection_run_id") or ""):
        raise RealtimeProjectionExecuteError("N3-B2 blocked: CLI projection_run_id does not match contract")
    if preflight.get("projection_run_id") != contract.get("projection_run_id"):
        raise RealtimeProjectionExecuteError("N3-B2 blocked: preflight projection_run_id does not match contract")
    if for_trade_date and for_trade_date != str((contract.get("dates") or {}).get("for_trade_date") or ""):
        raise RealtimeProjectionExecuteError("N3-B2 blocked: CLI for_trade_date does not match contract")
    if bool(contract.get("writes_outbox")) or bool((preflight.get("contract_summary") or {}).get("writes_outbox")):
        raise RealtimeProjectionExecuteError("N3-B2 blocked: contract must keep writes_outbox=false")
    if bool(contract.get("updates_market_snapshot_payload")) or bool(
        (preflight.get("contract_summary") or {}).get("updates_market_snapshot_payload")
    ):
        raise RealtimeProjectionExecuteError("N3-B2 blocked: contract must not update MarketSnapshotUpdated payload")
    if bool(contract.get("consumes_outbox")) or bool((preflight.get("contract_summary") or {}).get("consumes_outbox")):
        raise RealtimeProjectionExecuteError("N3-B2 blocked: contract must not consume outbox")
    failed_lineage = [row for row in preflight.get("lineage_checks", []) if not bool(row.get("passed"))]
    if failed_lineage:
        raise RealtimeProjectionExecuteError(f"N3-B2 blocked: lineage check failed: {failed_lineage}")


def ensure_dry_run_matches_contract(dry_run: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    if dry_run.get("result") != "DRY_RUN_PASS":
        raise RealtimeProjectionExecuteError("N3-B2 blocked: dry-run result is not DRY_RUN_PASS")
    if dry_run.get("projection_run_id_candidate") != contract.get("projection_run_id"):
        raise RealtimeProjectionExecuteError("N3-B2 blocked: dry-run projection_run_id does not match contract")


def ensure_clean_projection_target(snapshot: Mapping[str, Any], projection_run_id: str) -> None:
    if bool(snapshot.get("projection_run_exists")):
        raise RealtimeProjectionExecuteError(f"N3-B2 blocked: projection run already exists: {projection_run_id}")
    dirty_tables = {
        table_name: count
        for table_name, count in (snapshot.get("projection_run_table_counts") or {}).items()
        if int(count or 0) != 0
    }
    if dirty_tables:
        raise RealtimeProjectionExecuteError(f"N3-B2 blocked: projection rows already exist: {dirty_tables}")
    if int(snapshot.get("quality_rows_for_projection_run") or 0) != 0:
        raise RealtimeProjectionExecuteError("N3-B2 blocked: quality rows already exist for projection_run_id")
    if int(snapshot.get("outbox_rows_for_projection_run") or 0) != 0:
        raise RealtimeProjectionExecuteError("N3-B2 blocked: projection_run_id already has outbox rows")
    if int(snapshot.get("inbox_rows_for_projection_run") or 0) != 0:
        raise RealtimeProjectionExecuteError("N3-B2 blocked: projection_run_id already has inbox rows")
    if int(snapshot.get("checkpoint_refs_for_projection_run") or 0) != 0:
        raise RealtimeProjectionExecuteError("N3-B2 blocked: projection_run_id already has checkpoint refs")


def ensure_source_runs_passed(snapshot: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    rows = snapshot.get("source_run_rows") or {}
    source_runs = contract.get("source_runs") or {}
    expected_pulled: list[tuple[str, bool]] = [
        (str(source_runs.get("subscription_run_id") or ""), False),
    ]
    if projection_uses_direct_30m_k(contract):
        expected_pulled.extend((run_id, True) for run_id in source_30m_k_run_ids_for_contract(contract))
    else:
        expected_pulled.append((str(source_runs.get("snapshot_run_id") or ""), True))
    expected_pulled.extend((run_id, True) for run_id in resolve_source_run_ids(source_runs, "preload_run_id", "preload_run_ids"))
    if projection_uses_live_current_1m(contract):
        live_run_id = live_current_minute_source_run_id(contract)
        if live_run_id:
            expected_pulled.append((live_run_id, False))
    elif projection_uses_direct_30m_k(contract):
        pass
    else:
        expected_pulled.extend(
            (run_id, True) for run_id in resolve_source_run_ids(source_runs, "today_minute_run_id", "today_minute_run_ids")
        )
    for run_id, expected_fact_written in expected_pulled:
        row = rows.get(run_id)
        if row is None or row.get("status") != "passed":
            raise RealtimeProjectionExecuteError(f"N3-B2 blocked: source run is not passed: {run_id}")
        if bool(row.get("market_data_fact_written")) != expected_fact_written:
            raise RealtimeProjectionExecuteError(f"N3-B2 blocked: source run fact flag mismatch: {run_id}")


def capture_projection_execute_snapshot(
    dsn: str,
    *,
    projection_run_id: str,
    source_runs: Mapping[str, Any],
) -> dict[str, Any]:
    run_ids = [
        source_runs["subscription_run_id"],
        source_runs.get("snapshot_run_id"),
        projection_run_id,
    ]
    if source_runs.get("expansion_subscription_run_id"):
        run_ids.append(source_runs["expansion_subscription_run_id"])
    run_ids.extend(resolve_source_run_ids(source_runs, "preload_run_id", "preload_run_ids"))
    run_ids.extend(today_minute_run_ids_for_contract({"source_runs": source_runs, "source_mode": source_runs.get("source_mode")}))
    if source_runs.get("source_mode") == DIRECT_30M_K_SOURCE_MODE:
        run_ids.extend(resolve_source_run_ids(source_runs, "source_30m_k_run_id", "source_30m_k_run_ids"))
    run_ids = list(dict.fromkeys(str(run_id) for run_id in run_ids if run_id))
    with audited_n3_market_execute_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT run_id, status, source_condition_run_id, for_trade_date,
                   source_trade_date, prev_trade_date, market_data_pulled,
                   market_data_fact_written, p0_count, p1_count, p2_count
            FROM common_market_data_run
            WHERE run_id = ANY(%s)
            """,
            (run_ids,),
        )
        source_run_rows = {row["run_id"]: normalize_json_row(row) for row in cur.fetchall()}
        projection_run_exists = projection_run_id in source_run_rows
        projection_table_counts_total: dict[str, int] = {}
        projection_run_table_counts: dict[str, int] = {}
        for config in ASSET_CONFIG.values():
            table = config["projection_table"]
            cur.execute(f"SELECT count(*) AS count FROM {table}")
            projection_table_counts_total[table] = int(cur.fetchone()["count"])
            cur.execute(f"SELECT count(*) AS count FROM {table} WHERE projection_run_id = %s", (projection_run_id,))
            projection_run_table_counts[table] = int(cur.fetchone()["count"])
        cur.execute("SELECT count(*) AS count FROM common_market_data_quality_item WHERE run_id = %s", (projection_run_id,))
        quality_rows = int(cur.fetchone()["count"])
        cur.execute("SELECT count(*) AS count FROM common_event_outbox WHERE source_run_id = %s", (projection_run_id,))
        outbox_rows = int(cur.fetchone()["count"])
        cur.execute("SELECT count(*) AS count FROM common_event_inbox WHERE source_run_id = %s", (projection_run_id,))
        inbox_rows = int(cur.fetchone()["count"])
        cur.execute(
            """
            SELECT count(*) AS count
            FROM common_event_consumer_checkpoint
            WHERE checkpoint_payload::TEXT LIKE %s
               OR last_event_id LIKE %s
            """,
            (f"%{projection_run_id}%", f"%{projection_run_id}%"),
        )
        checkpoint_refs = int(cur.fetchone()["count"])
        snapshot_outbox_status: dict[str, int] = {}
        if source_runs.get("snapshot_run_id"):
            cur.execute(
                "SELECT status, count(*) AS count FROM common_event_outbox WHERE source_run_id = %s GROUP BY status",
                (source_runs["snapshot_run_id"],),
            )
            snapshot_outbox_status = {str(row["status"]): int(row["count"]) for row in cur.fetchall()}
    return {
        "projection_run_exists": projection_run_exists,
        "source_run_rows": source_run_rows,
        "projection_table_counts_total": projection_table_counts_total,
        "projection_run_table_counts": projection_run_table_counts,
        "quality_rows_for_projection_run": quality_rows,
        "outbox_rows_for_projection_run": outbox_rows,
        "inbox_rows_for_projection_run": inbox_rows,
        "checkpoint_refs_for_projection_run": checkpoint_refs,
        "snapshot_outbox_status": snapshot_outbox_status,
    }


def detect_projection_time_policy_noop(*, dsn: str, contract: Mapping[str, Any]) -> dict[str, Any]:
    """Return reviewed no-op evidence when fact-only source snapshot_time is outside trading buckets."""

    policy = contract.get("projection_time_policy") or {}
    if not projection_time_policy_requests_off_bucket_noop(policy):
        return {"should_noop": False, "reason": None, "policy": dict(policy)}
    if projection_uses_direct_30m_k(contract):
        return {"should_noop": False, "reason": None, "policy": dict(policy), "source_mode": DIRECT_30M_K_SOURCE_MODE}

    source_runs = contract["source_runs"]
    snapshot_run_id = str(source_runs["snapshot_run_id"])
    off_bucket_by_asset: dict[str, int] = {}
    samples: list[dict[str, Any]] = []
    total_rows = 0
    with audited_n3_market_execute_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        for asset_kind, asset_config in ASSET_CONFIG.items():
            identity_column = asset_config["identity_column"]
            cur.execute(
                f"""
                SELECT {identity_column} AS identity_key, snapshot_time
                FROM {asset_config["snapshot_table"]}
                WHERE run_id = %s
                ORDER BY {identity_column}
                """,
                (snapshot_run_id,),
            )
            rows = cur.fetchall()
            total_rows += len(rows)
            for row in rows:
                snapshot_time = ensure_shanghai_timezone(row["snapshot_time"])
                if snapshot_time_is_inside_trading_bucket(snapshot_time):
                    continue
                off_bucket_by_asset[asset_kind] = off_bucket_by_asset.get(asset_kind, 0) + 1
                if len(samples) < 10:
                    samples.append(
                        {
                            "asset_kind": asset_kind,
                            "identity_key": str(row["identity_key"]),
                            "snapshot_time": snapshot_time.isoformat(),
                        }
                    )

    off_bucket_count = sum(off_bucket_by_asset.values())
    return {
        "should_noop": off_bucket_count > 0,
        "reason": "off_bucket_source_snapshot_time" if off_bucket_count > 0 else None,
        "policy": dict(policy),
        "snapshot_run_id": snapshot_run_id,
        "snapshot_rows_checked": total_rows,
        "off_bucket_count": off_bucket_count,
        "off_bucket_by_asset": off_bucket_by_asset,
        "sample": samples,
        "no_closed_data_forged": True,
        "maps_midday_to_trading_bucket": False,
    }


def detect_projection_time_alignment_blocker(*, dsn: str, contract: Mapping[str, Any]) -> dict[str, Any]:
    """Return fail-closed evidence when fact-only B1 snapshot_time is ahead of C1 minute coverage."""

    if not projection_time_alignment_policy_required(contract):
        return {"blocked": False, "reason": None, "policy": dict(contract.get("projection_time_policy") or {})}

    source_runs = contract["source_runs"]
    snapshot_run_id = str(source_runs["snapshot_run_id"])
    today_minute_run_ids = resolve_source_run_ids(source_runs, "today_minute_run_id", "today_minute_run_ids")
    with audited_n3_market_execute_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        latest_closed = fetch_latest_closed_minute_for_runs(cur, today_minute_run_ids)
        snapshot_rows_by_asset: dict[str, list[dict[str, Any]]] = {}
        for asset_kind, asset_config in ASSET_CONFIG.items():
            identity_column = asset_config["identity_column"]
            cur.execute(
                f"""
                SELECT {identity_column} AS identity_key, snapshot_time
                FROM {asset_config["snapshot_table"]}
                WHERE run_id = %s
                ORDER BY {identity_column}
                """,
                (snapshot_run_id,),
            )
            snapshot_rows_by_asset[asset_kind] = [dict(row) for row in cur.fetchall()]

    return build_projection_time_alignment_evidence(
        contract=contract,
        latest_closed_minute=latest_closed,
        snapshot_rows_by_asset=snapshot_rows_by_asset,
    )


def projection_time_alignment_policy_required(contract: Mapping[str, Any]) -> bool:
    source_runs = contract.get("source_runs") or {}
    source_requirements = contract.get("source_requirements") or {}
    requires_today_minute = bool(
        source_requirements.get(
            "requires_today_minute_run",
            bool(source_runs.get("today_minute_run_id") or source_runs.get("today_minute_run_ids")),
        )
    )
    policy = contract.get("projection_time_policy") or {}
    return (
        requires_today_minute
        and str(policy.get("mode") or "") == "fact_only_defer_off_bucket_source_snapshot_time"
        and str(policy.get("bucket_time_source") or "") == "source_snapshot_time"
    )


def build_projection_time_alignment_evidence(
    *,
    contract: Mapping[str, Any],
    latest_closed_minute: datetime,
    snapshot_rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    latest_closed = ensure_shanghai_timezone(latest_closed_minute).replace(second=0, microsecond=0)
    after_latest_closed_rows: list[dict[str, Any]] = []
    max_required_closed_label: datetime | None = None
    checked_rows = 0
    for asset_kind, rows in snapshot_rows_by_asset.items():
        for row in rows:
            checked_rows += 1
            projection_time = resolve_projection_time_for_snapshot(
                row["snapshot_time"],
                contract=contract,
                latest_closed_minute=latest_closed,
            )
            required_closed_label = ensure_shanghai_timezone(projection_time["projection_closed_label"])
            if max_required_closed_label is None or required_closed_label > max_required_closed_label:
                max_required_closed_label = required_closed_label
            if required_closed_label <= latest_closed:
                continue
            if len(after_latest_closed_rows) < 10:
                after_latest_closed_rows.append(
                    {
                        "asset_kind": asset_kind,
                        "identity_key": str(row.get("identity_key") or ""),
                        "snapshot_time": ensure_shanghai_timezone(row["snapshot_time"]).isoformat(),
                        "required_closed_label": required_closed_label.isoformat(),
                    }
                )
    return {
        "blocked": False,
        "reason": None,
        "latest_closed_minute": latest_closed.isoformat(),
        "max_required_closed_label": max_required_closed_label.isoformat() if max_required_closed_label else None,
        "checked_rows": checked_rows,
        "after_latest_closed_count": len(after_latest_closed_rows),
        "after_latest_closed_sample": after_latest_closed_rows,
        "n4_trigger_allowed_without_closed_minute": True,
        "n5_actionexecuted_confirmation_required": bool(after_latest_closed_rows),
        "policy": dict(contract.get("projection_time_policy") or {}),
    }


def projection_time_policy_requests_off_bucket_noop(policy: Mapping[str, Any]) -> bool:
    return (
        str(policy.get("mode") or "") == "fact_only_defer_off_bucket_source_snapshot_time"
        and str(policy.get("off_bucket_source_snapshot_time_handling") or "") == "NOOP_PASS_NO_WRITE"
    )


def snapshot_time_is_inside_trading_bucket(snapshot_time: datetime) -> bool:
    try:
        projection_window_for_snapshot(snapshot_time)
    except RealtimeProjectionExecuteError:
        return False
    return True


def live_current_minute_rows_by_identity(contract: Mapping[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    rows_by_asset = contract.get("live_current_minute_rows_by_asset") or contract.get("live_current_minute_rows") or {}
    output: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    if not isinstance(rows_by_asset, Mapping):
        return output
    dates = contract.get("dates") if isinstance(contract.get("dates"), Mapping) else {}
    trade_date = str(dates.get("for_trade_date") or contract.get("for_trade_date") or "")
    intraday_trade_date = str(contract.get("intraday_trade_date") or trade_date)
    source_adapter = str(contract.get("source_adapter") or "")
    for asset_kind, rows in rows_by_asset.items():
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            continue
        normalized_input_rows = []
        for raw_row in rows:
            if not isinstance(raw_row, Mapping):
                continue
            row = dict(raw_row)
            identity_key = str(row.get("identity_key") or row.get(f"{asset_kind}_identity_key") or "")
            if not identity_key:
                continue
            if "bar_time" in row:
                row["bar_time"] = parse_datetime_value(row["bar_time"])
            normalized_input_rows.append(row)
        try:
            normalized_rows = normalize_mootdx_intraday_1m_labels(
                normalized_input_rows,
                trade_date=trade_date,
                intraday_trade_date=intraday_trade_date,
                source_adapter=source_adapter,
            )
        except MinuteLabelNormalizationError as exc:
            raise RealtimeProjectionExecuteError(f"N3-B2 blocked: {exc}") from exc
        for row in normalized_rows:
            identity_key = str(row.get("identity_key") or row.get(f"{asset_kind}_identity_key") or "")
            output[(str(asset_kind), identity_key)].append(row)
    return output


def parse_datetime_value(value: Any) -> datetime:
    if isinstance(value, datetime):
        return ensure_shanghai_timezone(value)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        return ensure_shanghai_timezone(datetime.fromisoformat(normalized))
    raise RealtimeProjectionExecuteError(f"N3-B2 blocked: invalid live_current_1m bar_time: {value!r}")


def latest_live_current_minute_label(contract: Mapping[str, Any], snapshots: Mapping[str, Sequence[Mapping[str, Any]]]) -> datetime:
    labels: list[datetime] = []
    for rows in live_current_minute_rows_by_identity(contract).values():
        labels.extend(ensure_shanghai_timezone(row["bar_time"]) for row in rows if row.get("bar_time"))
    if labels:
        return max(labels).replace(second=0, microsecond=0)
    snapshot_times = [
        ensure_shanghai_timezone(row["snapshot_time"]).replace(second=0, microsecond=0)
        for rows in snapshots.values()
        for row in rows
        if row.get("snapshot_time")
    ]
    if snapshot_times:
        return max(snapshot_times)
    raise RealtimeProjectionExecuteError("N3-B2 blocked: live_current_1m source has no minute rows or snapshot times")


def direct_30m_k_rows_for_contract(contract: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    containers: list[Mapping[str, Any]] = [contract]
    for key in ("source_payload", "source_contract", "projection_source_payload"):
        value = contract.get(key)
        if isinstance(value, Mapping):
            containers.append(value)
    for container in containers:
        rows = container.get("source_30m_k_rows") or container.get("materialized_source_30m_k_rows")
        if rows:
            if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
                raise RealtimeProjectionExecuteError("N3-B2 blocked: direct_30m_k source_30m_k_rows must be a sequence")
            return [row for row in rows if isinstance(row, Mapping)]
    raise RealtimeProjectionExecuteError("BLOCKED_DIRECT_30M_K_ROWS_MISSING")


def build_direct_30m_k_projection_rows_from_contract(contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    source_rows = direct_30m_k_rows_for_contract(contract)
    source_runs = contract["source_runs"]
    dates = contract["dates"]
    for_trade_date = str(dates["for_trade_date"])
    projection_run_id = str(contract["projection_run_id"])
    source_condition_run_id = str(source_runs["source_condition_run_id"])
    source_30m_k_run_id = str(source_runs.get("source_30m_k_run_id") or "")
    calculation_config = contract.get("calculation_config") if isinstance(contract.get("calculation_config"), Mapping) else {}
    calculation_method = str(calculation_config.get("calculation_method") or "direct_30m_k_projection_proof_v1")
    calculation_config_hash = str(calculation_config.get("calculation_config_hash") or "direct_30m_k_projection_proof_v1")
    output: list[dict[str, Any]] = []
    for source_row in source_rows:
        row = dict(source_row)
        asset_kind = str(row.get("asset_kind") or "")
        if asset_kind not in ASSET_CONFIG:
            raise RealtimeProjectionExecuteError(f"N3-B2 blocked: unsupported direct_30m_k asset_kind: {asset_kind}")
        adapter_contract = b2_30m_projection_adapter_contract(asset_kind)
        adapter_method = str(
            row.get("source_30m_k_adapter_method")
            or row.get("adapter_method")
            or adapter_contract["adapter_method"]
        )
        if adapter_method != adapter_contract["adapter_method"]:
            raise RealtimeProjectionExecuteError("N3-B2 blocked: direct_30m_k adapter method mismatch")
        source_time_value = row.get("source_30m_k_time") or row.get("bar_time") or row.get("time")
        projection_signal_status = str(row.get("projection_signal_status") or "unknown")
        proof_fields = build_b2_30m_projection_proof_fields(
            asset_kind=asset_kind,
            projection_run_id=projection_run_id,
            projection_id=row.get("projection_id"),
            projection_time=row.get("projection_time") or source_time_value,
            projection_signal_status=projection_signal_status,
            projection_30m_type=row.get("projection_30m_type"),
            source_mode=DIRECT_30M_K_SOURCE_MODE,
            for_trade_date=for_trade_date,
            source_30m_k_run_id=row.get("source_30m_k_run_id") or source_30m_k_run_id,
            source_30m_k_bar_id=row.get("source_30m_k_bar_id") or row.get("bar_id"),
            source_30m_k_row_key=row.get("source_30m_k_row_key") or row.get("row_key"),
            source_30m_k_time=source_time_value,
            source_30m_k_adapter_method=adapter_method,
            source_30m_k_source_marker=row.get("source_30m_k_source_marker") or row.get("source_marker"),
        )
        window_start = parse_datetime_value(proof_fields["source_30m_k_window_start"])
        window_end = parse_datetime_value(proof_fields["source_30m_k_window_end"])
        snapshot_time = parse_datetime_value(proof_fields["source_30m_k_time"])
        identity_key = str(row.get("identity_key") or "")
        identity_parts = identity_key.split(":")
        exchange = str(row.get("exchange") or (identity_parts[1] if len(identity_parts) > 2 else ""))
        code = str(row.get("code") or (identity_parts[2] if len(identity_parts) > 2 else ""))
        elapsed_seconds = int(row.get("elapsed_seconds") or max(0, min(1800, int((snapshot_time - window_start).total_seconds()))))
        window_total_seconds = int(row.get("window_total_seconds") or 1800)
        completion_ratio = row.get("completion_ratio")
        if completion_ratio is None:
            completion_ratio = Decimal(elapsed_seconds) / Decimal(window_total_seconds)
        projection_status = str(
            row.get("projection_status")
            or ("not_ready" if projection_signal_status in {"missing", "unknown", ""} else "ready")
        )
        projection_quality_status = str(row.get("projection_quality_status") or ("passed" if projection_status == "ready" else "blocked"))
        trace_status = str(row.get("trace_status") or ("passed" if projection_status == "ready" else "blocked"))
        price_direction_status = str(
            row.get("price_direction_status")
            or ("up" if projection_signal_status == "up_volume_expanding" else "down" if projection_signal_status == "down_volume_shrinking" else "unknown")
        )
        source_fact_ids = {
            **(row.get("source_fact_ids") if isinstance(row.get("source_fact_ids"), Mapping) else {}),
            "source_mode": DIRECT_30M_K_SOURCE_MODE,
            "source_30m_k_run_id": row.get("source_30m_k_run_id") or source_30m_k_run_id,
            "source_30m_k_bar_id": row.get("source_30m_k_bar_id") or row.get("bar_id"),
            "source_30m_k_row_key": row.get("source_30m_k_row_key") or row.get("row_key"),
            "missing_reason": row.get("missing_reason") or [],
            **proof_fields,
        }
        raw_json = {
            **(row.get("raw_json") if isinstance(row.get("raw_json"), Mapping) else {}),
            "stage": "N3-B2",
            "projection_run_id": projection_run_id,
            "source_mode": DIRECT_30M_K_SOURCE_MODE,
            "source_time_policy": proof_fields["source_time_policy"],
            "required_data_kind": proof_fields["required_data_kind"],
            "projection_mode": proof_fields["projection_mode"],
            "writes_outbox": False,
            "updates_market_snapshot_payload": False,
            **proof_fields,
        }
        output.append(
            {
                "asset_kind": asset_kind,
                "projection_run_id": projection_run_id,
                "source_snapshot_run_id": None,
                "source_condition_run_id": source_condition_run_id,
                "snapshot_id": None,
                "snapshot_event_id": None,
                "subscription_id": row.get("subscription_id"),
                "pull_plan_id": row.get("pull_plan_id"),
                "for_trade_date": for_trade_date,
                "trade_date": for_trade_date,
                "identity_key": identity_key,
                "exchange": exchange,
                "code": code,
                "display_code": row.get("display_code") or code,
                "name": row.get("name"),
                "projection_schema_version": PROJECTION_SCHEMA_VERSION,
                "projection_window_kind": PROJECTION_WINDOW_KIND,
                "projection_window_id": f"{for_trade_date}_{window_start.strftime('%H%M')}_{window_end.strftime('%H%M')}",
                "window_start": window_start,
                "window_end": window_end,
                "snapshot_time": snapshot_time,
                "elapsed_seconds": elapsed_seconds,
                "window_total_seconds": window_total_seconds,
                "completion_ratio": completion_ratio,
                "is_window_closed": False,
                "session_id": "afternoon" if window_start.hour >= 13 else "morning",
                "rolling_5m_amount_avg": row.get("rolling_5m_amount_avg"),
                "elapsed_amount": row.get("elapsed_amount"),
                "projected_30m_amount": row.get("projected_30m_amount"),
                "previous_day_same_window_amount": row.get("previous_day_same_window_amount"),
                "previous_day_same_elapsed_amount": row.get("previous_day_same_elapsed_amount"),
                "amount_projection_ratio": row.get("amount_projection_ratio"),
                "elapsed_amount_ratio": row.get("elapsed_amount_ratio"),
                "latest_price": row.get("latest_price"),
                "window_open_price": row.get("window_open_price"),
                "window_high_price": row.get("window_high_price"),
                "window_low_price": row.get("window_low_price"),
                "price_change_pct": row.get("price_change_pct"),
                "price_direction_status": price_direction_status,
                "projection_status": projection_status,
                "projection_signal_status": projection_signal_status,
                "projection_quality_status": projection_quality_status,
                "trace_status": trace_status,
                "amount_basis_kind": str(row.get("amount_basis_kind") or "direct_30m_k"),
                "source_fact_kind": str(row.get("source_fact_kind") or "mixed"),
                "source_fact_ids": source_fact_ids,
                "minute_bar_ids_used": [],
                "previous_day_minute_bar_ids_used": [],
                "quality_item_ids": [],
                "source_adapter": str(row.get("source_adapter") or f"direct_30m_k:{adapter_method}"),
                "calculation_method": calculation_method,
                "calculation_config_hash": calculation_config_hash,
                "raw_json": raw_json,
            }
        )
    return output


def build_projection_rows(*, dsn: str, contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    if projection_uses_direct_30m_k(contract):
        return build_direct_30m_k_projection_rows_from_contract(contract)
    source_runs = contract["source_runs"]
    dates = contract["dates"]
    config = contract["calculation_config"]
    snapshot_run_id = str(source_runs["snapshot_run_id"])
    live_mode = projection_uses_live_current_1m(contract)
    today_minute_run_ids = [] if live_mode else resolve_source_run_ids(source_runs, "today_minute_run_id", "today_minute_run_ids")
    preload_run_ids = resolve_source_run_ids(source_runs, "preload_run_id", "preload_run_ids")
    for_trade_date = str(dates["for_trade_date"])
    prev_trade_date = str(dates["prev_trade_date"])
    source_condition_run_id = str(source_runs["source_condition_run_id"])
    projection_run_id = str(contract["projection_run_id"])

    with audited_n3_market_execute_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        outbox = fetch_snapshot_outbox(cur, snapshot_run_id)
        pull_plan_ids = fetch_snapshot_pull_plan_ids(cur, str(source_runs["subscription_run_id"]), for_trade_date)

        snapshots: dict[str, list[dict[str, Any]]] = {}
        window_ranges: list[tuple[datetime, datetime]] = []
        for asset_kind, asset_config in ASSET_CONFIG.items():
            identity_column = asset_config["identity_column"]
            cur.execute(
                f"""
                SELECT *, {identity_column} AS identity_key
                FROM {asset_config["snapshot_table"]}
                WHERE run_id = %s
                ORDER BY {identity_column}
                """,
                (snapshot_run_id,),
            )
            rows = [dict(row) for row in cur.fetchall()]
            snapshots[asset_kind] = rows
        latest_closed = (
            latest_live_current_minute_label(contract, snapshots)
            if live_mode
            else fetch_latest_closed_minute_for_runs(cur, today_minute_run_ids)
        )
        for asset_kind, rows in snapshots.items():
            for row in rows:
                projection_time = resolve_projection_time_for_snapshot(
                    row["snapshot_time"],
                    contract=contract,
                    latest_closed_minute=latest_closed,
                )
                window_start, window_end, _closed_label = projection_window_for_snapshot(
                    projection_time["projection_snapshot_time"]
                )
                window_ranges.append((window_start, window_end))
        if not window_ranges:
            return []

        today_bars: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        previous_bars: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        today_bar_seen: set[tuple[str, str, int]] = set()
        previous_bar_seen: set[tuple[str, str, int]] = set()
        min_window_start = min(item[0] for item in window_ranges)
        max_window_end = max(item[1] for item in window_ranges)
        prev_min_window_start = previous_day_datetime(min_window_start, prev_trade_date)
        prev_max_window_end = previous_day_datetime(max_window_end, prev_trade_date)

        for asset_kind, asset_config in ASSET_CONFIG.items():
            identity_column = asset_config["identity_column"]
            minute_table = asset_config["minute_table"]
            if live_mode:
                for (live_asset_kind, identity_key), rows in live_current_minute_rows_by_identity(contract).items():
                    if live_asset_kind != asset_kind:
                        continue
                    for row in rows:
                        bar_id = int(row.get("bar_id") or 0)
                        key = (asset_kind, identity_key, bar_id)
                        if key in today_bar_seen:
                            continue
                        today_bar_seen.add(key)
                        today_bars[(asset_kind, identity_key)].append(dict(row))
            else:
                for today_minute_run_id in today_minute_run_ids:
                    cur.execute(
                        f"""
                        SELECT bar_id, bar_time, {identity_column} AS identity_key,
                               open, high, low, close, volume, amount, quality_status
                        FROM {minute_table}
                        WHERE run_id = %s
                          AND bar_time > %s
                          AND bar_time <= %s
                        ORDER BY {identity_column}, bar_time
                        """,
                        (today_minute_run_id, min_window_start, max_window_end),
                    )
                    for row in cur.fetchall():
                        key = (asset_kind, str(row["identity_key"]), int(row["bar_id"]))
                        if key in today_bar_seen:
                            continue
                        today_bar_seen.add(key)
                        today_bars[(asset_kind, row["identity_key"])].append(dict(row))
            for preload_run_id in preload_run_ids:
                cur.execute(
                    f"""
                    SELECT bar_id, bar_time, {identity_column} AS identity_key,
                           open, high, low, close, volume, amount, quality_status
                    FROM {minute_table}
                    WHERE run_id = %s
                      AND bar_time > %s
                      AND bar_time <= %s
                    ORDER BY {identity_column}, bar_time
                    """,
                    (preload_run_id, prev_min_window_start, prev_max_window_end),
                )
                for row in cur.fetchall():
                    key = (asset_kind, str(row["identity_key"]), int(row["bar_id"]))
                    if key in previous_bar_seen:
                        continue
                    previous_bar_seen.add(key)
                    previous_bars[(asset_kind, row["identity_key"])].append(dict(row))

    projection_rows: list[dict[str, Any]] = []
    for asset_kind, snapshot_rows in snapshots.items():
        for snapshot in snapshot_rows:
            projection_rows.append(
                build_projection_row(
                    asset_kind=asset_kind,
                    snapshot=snapshot,
                    event=outbox.get((asset_kind, snapshot["identity_key"])),
                    pull_plan_id=pull_plan_ids.get(asset_kind),
                    today_bars=today_bars.get((asset_kind, snapshot["identity_key"]), []),
                    previous_bars=previous_bars.get((asset_kind, snapshot["identity_key"]), []),
                    latest_closed_minute=latest_closed,
                    contract=contract,
                    source_condition_run_id=source_condition_run_id,
                    projection_run_id=projection_run_id,
                    for_trade_date=for_trade_date,
                    prev_trade_date=prev_trade_date,
                    calculation_config=config,
                )
            )
    return projection_rows


def build_projection_row(
    *,
    asset_kind: str,
    snapshot: Mapping[str, Any],
    event: Mapping[str, Any] | None,
    pull_plan_id: int | None,
    today_bars: Sequence[Mapping[str, Any]],
    previous_bars: Sequence[Mapping[str, Any]],
    latest_closed_minute: datetime,
    contract: Mapping[str, Any],
    source_condition_run_id: str,
    projection_run_id: str,
    for_trade_date: str,
    prev_trade_date: str,
    calculation_config: Mapping[str, Any],
) -> dict[str, Any]:
    identity_key = str(snapshot["identity_key"])
    projection_time = resolve_projection_time_for_snapshot(
        snapshot["snapshot_time"],
        contract=contract,
        latest_closed_minute=latest_closed_minute,
    )
    source_snapshot_time = projection_time["source_snapshot_time"]
    snapshot_time = projection_time["projection_snapshot_time"]
    window_start, window_end, derived_closed_label = projection_window_for_snapshot(snapshot_time)
    closed_label = projection_time.get("projection_closed_label") or derived_closed_label
    prev_window_start = previous_day_datetime(window_start, prev_trade_date)
    prev_window_end = previous_day_datetime(window_end, prev_trade_date)
    prev_closed_label = previous_day_datetime(closed_label, prev_trade_date)
    current_rows = [row for row in today_bars if window_start < ensure_shanghai_timezone(row["bar_time"]) <= closed_label]
    minute_label_normalizations = [trace for row in current_rows if (trace := minute_label_normalization_trace(row))]
    previous_elapsed_rows = [
        row for row in previous_bars if prev_window_start < ensure_shanghai_timezone(row["bar_time"]) <= prev_closed_label
    ]
    previous_window_rows = [
        row for row in previous_bars if prev_window_start < ensure_shanghai_timezone(row["bar_time"]) <= prev_window_end
    ]

    window_total_seconds = int(calculation_config.get("window_total_seconds") or 1800)
    elapsed_seconds = max(0, int((closed_label - window_start).total_seconds()))
    completion_ratio = Decimal(elapsed_seconds) / Decimal(window_total_seconds) if elapsed_seconds else Decimal("0")
    completion_min = Decimal(str(calculation_config.get("completion_ratio_min_ready") or "0.2"))
    expand_threshold = Decimal(str(calculation_config.get("amount_projection_expand_threshold") or "1.2"))
    shrink_threshold = Decimal(str(calculation_config.get("amount_projection_shrink_threshold") or "0.8"))
    flat_threshold = Decimal(str(calculation_config.get("price_flat_abs_pct_threshold") or "0.001"))

    missing_reasons: list[str] = []
    if completion_ratio < completion_min:
        missing_reasons.append("completion_ratio_below_min_ready")
    source_snapshot_after_latest_closed_minute = closed_label > latest_closed_minute
    if not current_rows:
        missing_reasons.append("missing_today_minute_elapsed")
    if not previous_elapsed_rows:
        missing_reasons.append("missing_current_lineage_previous_day_elapsed")
    if not previous_window_rows:
        missing_reasons.append("missing_current_lineage_previous_day_window")

    elapsed_amount = sum_decimal(current_rows, "amount")
    elapsed_volume = sum_decimal(current_rows, "volume")
    previous_elapsed_amount = sum_decimal(previous_elapsed_rows, "amount")
    previous_window_amount = sum_decimal(previous_window_rows, "amount")
    previous_elapsed_volume = sum_decimal(previous_elapsed_rows, "volume")
    previous_window_volume = sum_decimal(previous_window_rows, "volume")
    projected_amount = elapsed_amount / completion_ratio if elapsed_amount is not None and completion_ratio > 0 else None
    projected_volume = elapsed_volume / completion_ratio if elapsed_volume is not None and completion_ratio > 0 else None
    amount_projection_ratio = (
        projected_amount / previous_window_amount
        if projected_amount is not None and previous_window_amount is not None and previous_window_amount > 0
        else None
    )
    elapsed_amount_ratio = (
        elapsed_amount / previous_elapsed_amount
        if elapsed_amount is not None and previous_elapsed_amount is not None and previous_elapsed_amount > 0
        else None
    )
    volume_projection_ratio = (
        projected_volume / previous_window_volume
        if projected_volume is not None and previous_window_volume is not None and previous_window_volume > 0
        else None
    )
    elapsed_volume_ratio = (
        elapsed_volume / previous_elapsed_volume
        if elapsed_volume is not None and previous_elapsed_volume is not None and previous_elapsed_volume > 0
        else None
    )
    if amount_projection_ratio is None:
        missing_reasons.append("amount_projection_ratio_not_computable")

    latest_price = last_decimal(current_rows, "close") or decimal_or_none(snapshot.get("current_price")) or decimal_or_none(
        snapshot.get("close")
    )
    window_open_price = first_decimal(current_rows, "open")
    window_high_price = max_decimal(current_rows, "high")
    window_low_price = min_decimal(current_rows, "low")
    price_change_pct = (
        (latest_price - window_open_price) / window_open_price
        if latest_price is not None and window_open_price is not None and window_open_price != 0
        else None
    )
    price_direction_status = classify_price_direction(price_change_pct, flat_threshold)
    if price_direction_status == "unknown":
        missing_reasons.append("price_direction_unknown")
    projection_signal_status = classify_projection_signal(
        price_direction_status,
        amount_projection_ratio,
        expand_threshold=expand_threshold,
        shrink_threshold=shrink_threshold,
    )

    snapshot_event_id = str((event or {}).get("event_id") or "")
    payload = (event or {}).get("payload_json") or (event or {}).get("payload") or {}
    resolved_pull_plan_id = payload.get("pull_plan_id") or pull_plan_id
    trace_policy = contract.get("fact_only_snapshot_trace_policy") or {}
    allow_fact_only_snapshot_trace = bool(trace_policy.get("allow_missing_snapshot_event_id"))
    mandatory_trace_ok = all(
        [
            snapshot.get("snapshot_id"),
            snapshot.get("subscription_id"),
            resolved_pull_plan_id,
            snapshot.get("source_adapter"),
        ]
    )
    if not allow_fact_only_snapshot_trace:
        mandatory_trace_ok = mandatory_trace_ok and bool(snapshot_event_id)
    if not mandatory_trace_ok:
        missing_reasons.append("mandatory_trace_field_missing")
    unique_reasons = sorted(set(missing_reasons))
    ready = not unique_reasons and amount_projection_ratio is not None and price_direction_status != "unknown"
    projection_status = "ready" if ready else "not_ready"
    projection_quality_status = "passed" if ready else "blocked"
    trace_status = "passed" if ready else "blocked"
    minute_bar_ids = [int(row["bar_id"]) for row in current_rows]
    previous_day_minute_bar_ids = [int(row["bar_id"]) for row in previous_window_rows]
    source_mode = projection_source_mode(contract)
    c1_dependency = projection_c1_dependency(contract)
    source_live_minute_run_id = live_current_minute_source_run_id(contract)
    live_current_1m = source_mode == LIVE_CURRENT_1M_SOURCE_MODE
    canonical_source_fact_kind = LIVE_CURRENT_1M_SOURCE_MODE if live_current_1m else "mixed"
    no_c1_table_rows_read = live_current_1m
    no_c1_table_rows_written = live_current_1m
    closed_minute_confirmation_available = (not live_current_1m) and (not source_snapshot_after_latest_closed_minute)
    n5_actionexecuted_confirmation_required = (not live_current_1m) and source_snapshot_after_latest_closed_minute
    b2_projection_proof_fields = build_b2_30m_projection_proof_fields(
        asset_kind=asset_kind,
        projection_run_id=projection_run_id,
        projection_id=None,
        projection_time=snapshot_time.isoformat(),
        projection_signal_status=projection_signal_status,
    )
    source_fact_ids = {
        "snapshot_id": snapshot.get("snapshot_id"),
        "snapshot_event_id": snapshot_event_id,
        "anchor_snapshot_id": snapshot.get("snapshot_id"),
        "minute_bar_ids_used": minute_bar_ids,
        "previous_day_minute_bar_ids_used": previous_day_minute_bar_ids,
        "previous_day_elapsed_minute_bar_ids_used": [int(row["bar_id"]) for row in previous_elapsed_rows],
        "quality_item_ids": [],
        "missing_reason": unique_reasons,
        "closed_label_used": closed_label.isoformat(),
        "latest_closed_minute": ensure_shanghai_timezone(latest_closed_minute).isoformat(),
        "source_snapshot_after_latest_closed_minute": source_snapshot_after_latest_closed_minute,
        "closed_minute_confirmation_available": closed_minute_confirmation_available,
        "n5_actionexecuted_confirmation_required": n5_actionexecuted_confirmation_required,
        "source_snapshot_time": source_snapshot_time.isoformat(),
        "projection_snapshot_time": snapshot_time.isoformat(),
        "projection_time_policy": projection_time["policy"],
        "source_mode": source_mode or None,
        "canonical_source_fact_kind": canonical_source_fact_kind,
        "source_live_minute_run_id": source_live_minute_run_id,
        "source_live_minute_kind": LIVE_CURRENT_1M_SOURCE_MODE if source_mode == LIVE_CURRENT_1M_SOURCE_MODE else None,
        "c1_dependency": c1_dependency,
        "no_c1_table_rows_read": no_c1_table_rows_read,
        "no_c1_table_rows_written": no_c1_table_rows_written,
        "is_closed_1m": False if live_current_1m else not source_snapshot_after_latest_closed_minute,
        "minute_label_normalization": minute_label_normalizations,
        **b2_projection_proof_fields,
    }
    return {
        "asset_kind": asset_kind,
        "projection_run_id": projection_run_id,
        "source_snapshot_run_id": contract["source_runs"]["snapshot_run_id"],
        "source_condition_run_id": source_condition_run_id,
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_event_id": snapshot_event_id,
        "subscription_id": snapshot["subscription_id"],
        "pull_plan_id": resolved_pull_plan_id,
        "for_trade_date": for_trade_date,
        "trade_date": for_trade_date,
        "identity_key": identity_key,
        "exchange": snapshot["exchange"],
        "code": snapshot["code"],
        "display_code": snapshot.get("display_code"),
        "name": snapshot.get("name"),
        "projection_schema_version": PROJECTION_SCHEMA_VERSION,
        "projection_window_kind": PROJECTION_WINDOW_KIND,
        "projection_window_id": f"{for_trade_date}_{window_start.strftime('%H%M')}_{window_end.strftime('%H%M')}",
        "window_start": window_start,
        "window_end": window_end,
        "snapshot_time": snapshot_time,
        "elapsed_seconds": elapsed_seconds,
        "window_total_seconds": window_total_seconds,
        "completion_ratio": completion_ratio,
        "is_window_closed": closed_label >= window_end,
        "session_id": "afternoon" if window_start.hour >= 13 else "morning",
        "rolling_5m_amount_avg": rolling_average_amount(current_rows, count=5),
        "elapsed_amount": elapsed_amount,
        "projected_30m_amount": projected_amount,
        "previous_day_same_window_amount": previous_window_amount,
        "previous_day_same_elapsed_amount": previous_elapsed_amount,
        "amount_projection_ratio": amount_projection_ratio,
        "elapsed_amount_ratio": elapsed_amount_ratio,
        "latest_price": latest_price,
        "window_open_price": window_open_price,
        "window_high_price": window_high_price,
        "window_low_price": window_low_price,
        "price_change_pct": price_change_pct,
        "price_direction_status": price_direction_status,
        "projection_status": projection_status,
        "projection_signal_status": projection_signal_status,
        "projection_quality_status": projection_quality_status,
        "trace_status": trace_status,
        "amount_basis_kind": "previous_day_same_window" if amount_projection_ratio is not None else "not_available",
        "source_fact_kind": "mixed",
        "source_fact_ids": source_fact_ids,
        "minute_bar_ids_used": minute_bar_ids,
        "previous_day_minute_bar_ids_used": previous_day_minute_bar_ids,
        "quality_item_ids": [],
        "source_adapter": snapshot["source_adapter"],
        "calculation_method": str(calculation_config["calculation_method"]),
        "calculation_config_hash": str(calculation_config["calculation_config_hash"]),
        "raw_json": {
            "stage": "N3-B2",
            "projection_run_id": projection_run_id,
            "today_minute_run_id": contract["source_runs"].get("today_minute_run_id") or source_live_minute_run_id,
            "today_minute_run_ids": today_minute_run_ids_for_contract(contract),
            "preload_run_id": contract["source_runs"]["preload_run_id"],
            "preload_run_ids": resolve_source_run_ids(contract["source_runs"], "preload_run_id", "preload_run_ids"),
            "snapshot_run_id": contract["source_runs"]["snapshot_run_id"],
            "source_mode": source_mode or None,
            "canonical_source_fact_kind": canonical_source_fact_kind,
            "source_live_minute_run_id": source_live_minute_run_id,
            "source_live_minute_kind": LIVE_CURRENT_1M_SOURCE_MODE if live_current_1m else None,
            "c1_dependency": c1_dependency,
            "no_c1_table_rows_read": no_c1_table_rows_read,
            "no_c1_table_rows_written": no_c1_table_rows_written,
            "is_closed_1m": False if live_current_1m else not source_snapshot_after_latest_closed_minute,
            "minute_label_normalization": minute_label_normalizations,
            "source_snapshot_time": source_snapshot_time.isoformat(),
            "projection_snapshot_time": snapshot_time.isoformat(),
            "projection_bucket_closed_label": closed_label.isoformat(),
            "latest_closed_minute": ensure_shanghai_timezone(latest_closed_minute).isoformat(),
            "source_snapshot_after_latest_closed_minute": source_snapshot_after_latest_closed_minute,
            "closed_minute_confirmed_for_actionexecuted": closed_minute_confirmation_available,
            "n4_trigger_allowed_without_closed_minute": True,
            "n5_actionexecuted_confirmation_required": n5_actionexecuted_confirmation_required,
            "evidence_role": (
                "live_current_1m_projection_evidence"
                if live_current_1m
                else "provisional_trigger_evidence"
                if source_snapshot_after_latest_closed_minute
                else "closed_minute_confirmation_evidence"
            ),
            "projection_time_policy": projection_time["policy"],
            "projection_status": projection_status,
            "projection_signal_status": projection_signal_status,
            "missing_reason": unique_reasons,
            **b2_projection_proof_fields,
            "fact_only_snapshot_trace_compatible": allow_fact_only_snapshot_trace and not bool(snapshot_event_id),
            "volume_projection_ratio": decimal_to_string(volume_projection_ratio),
            "elapsed_volume_ratio": decimal_to_string(elapsed_volume_ratio),
            "previous_day_same_window_volume": decimal_to_string(previous_window_volume),
            "previous_day_same_elapsed_volume": decimal_to_string(previous_elapsed_volume),
            "projected_window_volume": decimal_to_string(projected_volume),
            "writes_outbox": False,
            "updates_market_snapshot_payload": False,
        },
    }


def validate_projection_rows_against_contract(rows: Sequence[Mapping[str, Any]], contract: Mapping[str, Any]) -> None:
    summary = summarize_projection_rows(rows)
    expected_rows = contract.get("expected_projection_rows") or {}
    expected_distribution = materialize_expected_distribution_for_contract(contract, summary)
    if int(summary["total_rows"]) != int(expected_rows.get("total") or 0):
        raise RealtimeProjectionExecuteError("N3-B2 blocked: projection total rows differ from contract")
    if normalize_projection_rows_by_asset(summary["rows_by_asset"]) != expected_projection_rows_by_asset(expected_rows):
        raise RealtimeProjectionExecuteError("N3-B2 blocked: projection rows by asset differ from contract")
    if int(summary["projection_status"].get("ready", 0)) != int(expected_distribution.get("ready_rows") or 0):
        raise RealtimeProjectionExecuteError("N3-B2 blocked: ready row count differs from contract")
    if int(summary["projection_status"].get("not_ready", 0)) != int(expected_distribution.get("not_ready_rows") or 0):
        raise RealtimeProjectionExecuteError("N3-B2 blocked: not_ready row count differs from contract")
    if summary["ready_by_asset"] != expected_distribution.get("ready_by_asset", {}):
        raise RealtimeProjectionExecuteError("N3-B2 blocked: ready_by_asset differs from contract")
    if summary["not_ready_by_asset"] != expected_distribution.get("not_ready_by_asset", {}):
        raise RealtimeProjectionExecuteError("N3-B2 blocked: not_ready_by_asset differs from contract")
    expected_signal = expected_distribution.get("projection_signal_status") or {}
    if summary["projection_signal_status"] != expected_signal:
        raise RealtimeProjectionExecuteError("N3-B2 blocked: projection_signal_status distribution differs from contract")
    expected_board_not_ready = expected_distribution.get("board_not_ready")
    if expected_board_not_ready is not None and int(summary["board_not_ready"]) != int(expected_board_not_ready):
        raise RealtimeProjectionExecuteError("N3-B2 blocked: board not_ready count changed")
    expected_bj_920xxx_not_ready = expected_distribution.get("bj_920xxx_not_ready")
    if expected_bj_920xxx_not_ready is not None and int(summary["bj_920xxx_not_ready"]) != int(
        expected_bj_920xxx_not_ready
    ):
        raise RealtimeProjectionExecuteError("N3-B2 blocked: BJ 920xxx not_ready count changed")


def expected_projection_rows_by_asset(expected_rows: Mapping[str, Any]) -> dict[str, int]:
    by_asset = expected_rows.get("by_asset") if isinstance(expected_rows.get("by_asset"), Mapping) else expected_rows
    return normalize_projection_rows_by_asset(by_asset)


def normalize_projection_rows_by_asset(rows_by_asset: Mapping[str, Any]) -> dict[str, int]:
    return {
        asset: int((rows_by_asset or {}).get(asset) or 0)
        for asset in ASSET_CONFIG
        if int((rows_by_asset or {}).get(asset) or 0) != 0
    }


def materialize_expected_distribution_for_contract(
    contract: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    expected_distribution = dict(contract.get("expected_distribution") or {})
    policy = contract.get("expected_distribution_policy") or {}
    if policy.get("mode") != "derive_from_projection_rows":
        return expected_distribution
    if contract.get("artifact_generation_mode") != "dynamic_intraday_child_artifact":
        raise RealtimeProjectionExecuteError(
            "N3-B2 blocked: derive_from_projection_rows expected_distribution policy is only allowed for dynamic child artifacts"
        )
    derived = build_expected_distribution_from_summary(summary)
    if isinstance(contract, dict):
        contract["expected_distribution"] = derived
        policy_copy = dict(policy)
        policy_copy["materialized_by_runner"] = True
        contract["expected_distribution_policy"] = policy_copy
    return derived


def build_expected_distribution_from_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ready_rows": int((summary.get("projection_status") or {}).get("ready", 0)),
        "ready_by_asset": {key: int(value) for key, value in (summary.get("ready_by_asset") or {}).items()},
        "not_ready_rows": int((summary.get("projection_status") or {}).get("not_ready", 0)),
        "not_ready_by_asset": {key: int(value) for key, value in (summary.get("not_ready_by_asset") or {}).items()},
        "projection_signal_status": {
            key: int(value) for key, value in (summary.get("projection_signal_status") or {}).items()
        },
        "projection_quality_status": {
            key: int(value) for key, value in (summary.get("projection_quality_status") or {}).items()
        },
        "trace_status": {key: int(value) for key, value in (summary.get("trace_status") or {}).items()},
        "board_not_ready": int(summary.get("board_not_ready") or 0),
        "bj_920xxx_not_ready": int(summary.get("bj_920xxx_not_ready") or 0),
        "distribution_status": "materialized_from_projection_rows",
    }


def summarize_projection_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows_by_asset = Counter(str(row.get("asset_kind") or "") for row in rows)
    status = Counter(str(row.get("projection_status") or "") for row in rows)
    quality = Counter(str(row.get("projection_quality_status") or "") for row in rows)
    trace = Counter(str(row.get("trace_status") or "") for row in rows)
    signal = Counter(str(row.get("projection_signal_status") or "") for row in rows)
    ready_by_asset = Counter(
        str(row.get("asset_kind") or "") for row in rows if str(row.get("projection_status") or "") == "ready"
    )
    not_ready_by_asset = Counter(
        str(row.get("asset_kind") or "") for row in rows if str(row.get("projection_status") or "") == "not_ready"
    )
    return {
        "total_rows": len(rows),
        "rows_by_asset": dict(rows_by_asset),
        "projection_status": dict(status),
        "projection_quality_status": dict(quality),
        "trace_status": dict(trace),
        "projection_signal_status": dict(signal),
        "ready_by_asset": dict(ready_by_asset),
        "not_ready_by_asset": dict(not_ready_by_asset),
        "board_not_ready": sum(
            1
            for row in rows
            if row.get("asset_kind") == "board" and row.get("projection_status") == "not_ready"
        ),
        "bj_920xxx_not_ready": sum(
            1
            for row in rows
            if str(row.get("identity_key") or "").startswith("stock:BJ:920")
            and row.get("projection_status") == "not_ready"
        ),
    }


def write_projection_execute_transaction(
    *,
    dsn: str,
    contract: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    quality_items: Sequence[Mapping[str, Any]],
    status: str,
    started_at: str,
    contract_path: str,
    preflight_path: str,
    dry_run_path: str,
) -> None:
    with audited_n3_market_execute_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                insert_projection_run(
                    cur,
                    contract=contract,
                    status="running",
                    started_at=started_at,
                    contract_path=contract_path,
                    preflight_path=preflight_path,
                    dry_run_path=dry_run_path,
                )
                insert_projection_rows(cur, rows)
                insert_projection_quality_items(cur, contract=contract, quality_items=quality_items)
                counts = count_quality_severities(list(quality_items))
                cur.execute(
                    """
                    UPDATE common_market_data_run
                    SET status = %s,
                        p0_count = %s,
                        p1_count = %s,
                        p2_count = %s,
                        market_data_pulled = false,
                        market_data_fact_written = true,
                        downstream_layers_touched = false,
                        worker_started = false,
                        finished_at = now(),
                        updated_at = now()
                    WHERE run_id = %s
                    """,
                    (
                        status,
                        counts["P0"],
                        counts["P1"],
                        counts["P2"],
                        contract["projection_run_id"],
                    ),
                )


def insert_projection_run(
    cur: Any,
    *,
    contract: Mapping[str, Any],
    status: str,
    started_at: str,
    contract_path: str,
    preflight_path: str,
    dry_run_path: str,
) -> None:
    source_run = fetch_run_for_insert(cur, str(contract["source_runs"]["subscription_run_id"]))
    expected_rows = contract["expected_projection_rows"]
    cur.execute(
        """
        INSERT INTO common_market_data_run (
          run_id, source_condition_run_id, for_trade_date, source_trade_date,
          prev_trade_date, mode, status, p0_count, p1_count, p2_count,
          source_scope_row_count, candidate_row_count, subscription_row_count,
          subscription_object_count, dedup_ratio, generated_by,
          market_data_pulled, market_data_fact_written,
          downstream_layers_touched, worker_started, started_at, raw_json
        )
        VALUES (%s, %s, %s, %s, %s, 'execute', %s, 0, 0, 0,
                %s, %s, %s, %s, %s, 'N3-B2-realtime-projection-execute',
                false, false, false, false, %s, %s)
        """,
        (
            contract["projection_run_id"],
            contract["source_runs"]["source_condition_run_id"],
            contract["dates"]["for_trade_date"],
            contract["dates"]["source_trade_date"],
            contract["dates"]["prev_trade_date"],
            status,
            int(source_run.get("source_scope_row_count") or 0),
            int(source_run.get("candidate_row_count") or 0),
            int(expected_rows.get("total") or 0),
            int(expected_rows.get("total") or 0),
            source_run.get("dedup_ratio"),
            started_at,
            Jsonb(
                {
                    "stage": "N3-B2",
                    "projection_run_id": contract["projection_run_id"],
                    "source_runs": contract["source_runs"],
                    "contract_path": contract_path,
                    "preflight_path": preflight_path,
                    "dry_run_path": dry_run_path,
                    "writes_outbox": False,
                    "updates_market_snapshot_payload": False,
                    "run_once_only": True,
                }
            ),
        ),
    )


def fetch_run_for_insert(cur: Any, run_id: str) -> Mapping[str, Any]:
    cur.execute(
        """
        SELECT source_scope_row_count, candidate_row_count, dedup_ratio
        FROM common_market_data_run
        WHERE run_id = %s
        """,
        (run_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise RealtimeProjectionExecuteError(f"N3-B2 blocked: source subscription run missing: {run_id}")
    return row


def insert_projection_rows(cur: Any, rows: Sequence[Mapping[str, Any]]) -> int:
    count = 0
    for asset_kind, config in ASSET_CONFIG.items():
        asset_rows = [row for row in rows if row["asset_kind"] == asset_kind]
        if not asset_rows:
            continue
        identity_column = config["identity_column"]
        columns = (
            "projection_run_id",
            "source_snapshot_run_id",
            "source_condition_run_id",
            "snapshot_id",
            "snapshot_event_id",
            "subscription_id",
            "pull_plan_id",
            "for_trade_date",
            "trade_date",
            identity_column,
            "exchange",
            "code",
            "display_code",
            "name",
            "projection_schema_version",
            "projection_window_kind",
            "projection_window_id",
            "window_start",
            "window_end",
            "snapshot_time",
            "elapsed_seconds",
            "window_total_seconds",
            "completion_ratio",
            "is_window_closed",
            "session_id",
            "rolling_5m_amount_avg",
            "elapsed_amount",
            "projected_30m_amount",
            "previous_day_same_window_amount",
            "previous_day_same_elapsed_amount",
            "amount_projection_ratio",
            "elapsed_amount_ratio",
            "latest_price",
            "window_open_price",
            "window_high_price",
            "window_low_price",
            "price_change_pct",
            "price_direction_status",
            "projection_status",
            "projection_signal_status",
            "projection_quality_status",
            "trace_status",
            "amount_basis_kind",
            "source_fact_kind",
            "source_fact_ids",
            "minute_bar_ids_used",
            "previous_day_minute_bar_ids_used",
            "quality_item_ids",
            "source_adapter",
            "calculation_method",
            "calculation_config_hash",
            "raw_json",
        )
        values = []
        for row in asset_rows:
            values.append(
                (
                    row["projection_run_id"],
                    row["source_snapshot_run_id"],
                    row["source_condition_run_id"],
                    row["snapshot_id"],
                    row["snapshot_event_id"],
                    row["subscription_id"],
                    row["pull_plan_id"],
                    row["for_trade_date"],
                    row["trade_date"],
                    row["identity_key"],
                    row["exchange"],
                    row["code"],
                    row.get("display_code"),
                    row.get("name"),
                    row["projection_schema_version"],
                    row["projection_window_kind"],
                    row["projection_window_id"],
                    row["window_start"],
                    row["window_end"],
                    row["snapshot_time"],
                    row["elapsed_seconds"],
                    row["window_total_seconds"],
                    row["completion_ratio"],
                    row["is_window_closed"],
                    row["session_id"],
                    row.get("rolling_5m_amount_avg"),
                    row.get("elapsed_amount"),
                    row.get("projected_30m_amount"),
                    row.get("previous_day_same_window_amount"),
                    row.get("previous_day_same_elapsed_amount"),
                    row.get("amount_projection_ratio"),
                    row.get("elapsed_amount_ratio"),
                    row.get("latest_price"),
                    row.get("window_open_price"),
                    row.get("window_high_price"),
                    row.get("window_low_price"),
                    row.get("price_change_pct"),
                    row["price_direction_status"],
                    row["projection_status"],
                    row["projection_signal_status"],
                    row["projection_quality_status"],
                    row["trace_status"],
                    row["amount_basis_kind"],
                    row["source_fact_kind"],
                    Jsonb(row["source_fact_ids"]),
                    row["minute_bar_ids_used"],
                    row["previous_day_minute_bar_ids_used"],
                    row["quality_item_ids"],
                    row["source_adapter"],
                    row["calculation_method"],
                    row["calculation_config_hash"],
                    Jsonb(json_safe(row["raw_json"])),
                )
            )
        cur.executemany(
            f"""
            INSERT INTO {config["projection_table"]} ({", ".join(columns)})
            VALUES ({", ".join(["%s"] * len(columns))})
            """,
            values,
        )
        count += len(values)
    return count


def insert_projection_quality_items(
    cur: Any,
    *,
    contract: Mapping[str, Any],
    quality_items: Sequence[Mapping[str, Any]],
) -> int:
    if not quality_items:
        return 0
    columns = (
        "run_id",
        "source_condition_run_id",
        "for_trade_date",
        "source_trade_date",
        "data_domain",
        "layer_scope",
        "table_name",
        "gate_code",
        "gate_name",
        "severity",
        "status",
        "expected_value",
        "actual_value",
        "identity_key",
        "details",
    )
    rows = []
    for item in quality_items:
        data_domain = str(item.get("data_domain") or "common")
        if data_domain not in ALLOWED_QUALITY_DATA_DOMAINS:
            raise RealtimeProjectionExecuteError(
                f"N3-B2 blocked: illegal quality data_domain for common_market_data_quality_item: {data_domain}"
            )
        details = dict(item.get("details") or {})
        details.setdefault("metric_scope", PROJECTION_METRIC_SCOPE)
        details.setdefault("projection_run_id", contract["projection_run_id"])
        details.setdefault("asset_kind", data_domain)
        details.setdefault("projection_schema_version", PROJECTION_SCHEMA_VERSION)
        layer_scope = str(item.get("layer_scope") or B2_QUALITY_LAYER_SCOPE)
        if layer_scope != B2_QUALITY_LAYER_SCOPE:
            raise RealtimeProjectionExecuteError(
                f"N3-B2 blocked: quality layer_scope must be {B2_QUALITY_LAYER_SCOPE}: {layer_scope}"
            )
        rows.append(
            (
                contract["projection_run_id"],
                contract["source_runs"]["source_condition_run_id"],
                contract["dates"]["for_trade_date"],
                contract["dates"]["source_trade_date"],
                data_domain,
                layer_scope,
                item.get("table_name"),
                item.get("gate_code"),
                item.get("gate_name"),
                item.get("severity"),
                item.get("status"),
                item.get("expected_value"),
                item.get("actual_value"),
                item.get("identity_key"),
                Jsonb(json_safe(details)),
            )
        )
    cur.executemany(
        f"""
        INSERT INTO common_market_data_quality_item ({", ".join(columns)})
        VALUES ({", ".join(["%s"] * len(columns))})
        """,
        rows,
    )
    return len(rows)


def build_projection_quality_items(
    *,
    contract: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    pre_backup: Mapping[str, Any],
) -> list[dict[str, Any]]:
    summary = summarize_projection_rows(rows)
    expected = materialize_expected_distribution_for_contract(contract, summary)
    items = [
        quality_item(
            "P0",
            "passed",
            "n3_b2_execute_projection_rows_match_contract",
            "B2 execute projection rows must match contract counts",
            expected=json.dumps(contract["expected_projection_rows"], ensure_ascii=False, sort_keys=True),
            actual=json.dumps(summary["rows_by_asset"] | {"total": summary["total_rows"]}, ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed",
            "n3_b2_execute_ready_distribution_match_contract",
            "B2 ready/not_ready distribution must match reviewed dry-run contract",
            expected=json.dumps(
                {"ready": expected["ready_by_asset"], "not_ready": expected["not_ready_by_asset"]},
                ensure_ascii=False,
                sort_keys=True,
            ),
            actual=json.dumps(
                {"ready": summary["ready_by_asset"], "not_ready": summary["not_ready_by_asset"]},
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        quality_item(
            "P0",
            "passed",
            "n3_b2_execute_writes_outbox_false",
            "B2 execute must not write common_event_outbox",
            expected="0",
            actual=str(pre_backup.get("outbox_rows_for_projection_run") or 0),
        ),
        quality_item(
            "P1",
            "warning",
            "n3_b2_execute_board_not_ready_visible",
            "board rows remain explicit not_ready because snapshot_time is later than C1 latest closed minute",
            expected=f"board not_ready={contract['expected_distribution'].get('board_not_ready', 0)}",
            actual=str(summary["board_not_ready"]),
        ),
        quality_item(
            "P1",
            "warning",
            "n3_b2_execute_bj_920xxx_not_ready_visible",
            "BJ 920xxx stock rows remain explicit not_ready/warning",
            expected=f"BJ 920xxx not_ready={contract['expected_distribution'].get('bj_920xxx_not_ready', 0)}",
            actual=str(summary["bj_920xxx_not_ready"]),
        ),
        quality_item(
            "P1",
            "warning",
            "n3_b2_execute_stock_index_completion_not_ready_visible",
            "stock/index rows that are below the reviewed completion ratio remain explicit not_ready",
            expected="stock/index not_ready visible when completion_ratio_below_min_ready remains",
            actual=json.dumps(
                {
                    asset: summary["not_ready_by_asset"].get(asset, 0)
                    for asset in ("stock", "index")
                    if summary["not_ready_by_asset"].get(asset, 0)
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        quality_item(
            "P1",
            "warning",
            "n3_b2_execute_input_p1_carried",
            "B1/A1/C1 non-blocking P1 warnings remain visible",
            expected="visible carried P1",
            actual="B1=1,A1=2,C1=1",
        ),
    ]
    for item in items:
        if item["gate_code"] == "n3_b2_execute_board_not_ready_visible":
            attach_projection_quality_context(
                item,
                contract=contract,
                data_domain="board",
                table_name="board_realtime_projection_metric",
            )
        elif item["gate_code"] == "n3_b2_execute_bj_920xxx_not_ready_visible":
            attach_projection_quality_context(
                item,
                contract=contract,
                data_domain="stock",
                table_name="stock_realtime_projection_metric",
            )
        elif item["gate_code"] == "n3_b2_execute_stock_index_completion_not_ready_visible":
            attach_projection_quality_context(
                item,
                contract=contract,
                data_domain="common",
                table_name=PROJECTION_QUALITY_TABLE_BY_DOMAIN["common"],
            )
        else:
            attach_projection_quality_context(
                item,
                contract=contract,
                data_domain="common",
                table_name=PROJECTION_QUALITY_TABLE_BY_DOMAIN["common"],
            )
    return items


def attach_projection_quality_context(
    item: dict[str, Any],
    *,
    contract: Mapping[str, Any],
    data_domain: str,
    table_name: str,
) -> dict[str, Any]:
    if data_domain not in ALLOWED_QUALITY_DATA_DOMAINS:
        raise RealtimeProjectionExecuteError(f"N3-B2 blocked: illegal projection quality data_domain: {data_domain}")
    item["data_domain"] = data_domain
    item["layer_scope"] = B2_QUALITY_LAYER_SCOPE
    item["table_name"] = table_name
    details = dict(item.get("details") or {})
    details.setdefault("metric_scope", PROJECTION_METRIC_SCOPE)
    details.setdefault("projection_run_id", contract["projection_run_id"])
    details.setdefault("asset_kind", data_domain)
    details.setdefault("projection_schema_version", PROJECTION_SCHEMA_VERSION)
    item["details"] = details
    return item


def build_projection_rollback_sql(projection_run_id: str) -> str:
    return f"""-- N3-B2 realtime projection rollback.
-- Boundary: rollback only projection facts/quality/run for the listed projection_run_id.
-- Hard-fail before row removal if event infra or downstream N4/N5/N6 refs exist.
\\set ON_ERROR_STOP on

BEGIN;

SELECT set_config('app.n3_b2_projection_run_id', '{projection_run_id}', false);

DO $$
DECLARE
  target_run_id TEXT := current_setting('app.n3_b2_projection_run_id');
  outbox_refs BIGINT := 0;
  inbox_refs BIGINT := 0;
  checkpoint_refs BIGINT := 0;
  trigger_state_refs BIGINT := 0;
  trigger_match_refs BIGINT := 0;
  action_refs BIGINT := 0;
  n6_refs BIGINT := 0;
  downstream_flags BIGINT := 0;
BEGIN
  SELECT count(*) INTO outbox_refs
  FROM common_event_outbox
  WHERE source_run_id = target_run_id OR payload_json::TEXT LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO inbox_refs
  FROM common_event_inbox
  WHERE source_run_id = target_run_id
     OR payload_json::TEXT LIKE '%' || target_run_id || '%'
     OR raw_json::TEXT LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || target_run_id || '%'
     OR last_event_id LIKE '%' || target_run_id || '%';

  IF to_regclass('common_trigger_state') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_trigger_state WHERE to_jsonb(common_trigger_state)::TEXT LIKE $1'
      INTO trigger_state_refs USING '%' || target_run_id || '%';
  END IF;
  IF to_regclass('common_trigger_match') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_trigger_match WHERE to_jsonb(common_trigger_match)::TEXT LIKE $1'
      INTO trigger_match_refs USING '%' || target_run_id || '%';
  END IF;
  IF to_regclass('common_action_event') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_action_event WHERE to_jsonb(common_action_event)::TEXT LIKE $1'
      INTO action_refs USING '%' || target_run_id || '%';
  END IF;
  IF to_regclass('user_projection_run') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_projection_run WHERE to_jsonb(user_projection_run)::TEXT LIKE $1'
      INTO n6_refs USING '%' || target_run_id || '%';
  END IF;
  IF to_regclass('user_signal_projection') IS NOT NULL THEN
    EXECUTE 'SELECT $1 + count(*) FROM user_signal_projection WHERE to_jsonb(user_signal_projection)::TEXT LIKE $2'
      INTO n6_refs USING n6_refs, '%' || target_run_id || '%';
  END IF;
  IF to_regclass('user_signal_card') IS NOT NULL THEN
    EXECUTE 'SELECT $1 + count(*) FROM user_signal_card WHERE to_jsonb(user_signal_card)::TEXT LIKE $2'
      INTO n6_refs USING n6_refs, '%' || target_run_id || '%';
  END IF;
  IF to_regclass('user_notification_queue') IS NOT NULL THEN
    EXECUTE 'SELECT $1 + count(*) FROM user_notification_queue WHERE to_jsonb(user_notification_queue)::TEXT LIKE $2'
      INTO n6_refs USING n6_refs, '%' || target_run_id || '%';
  END IF;

  SELECT count(*) INTO downstream_flags
  FROM common_market_data_run
  WHERE run_id = target_run_id
    AND (coalesce(downstream_layers_touched, false) OR coalesce(worker_started, false));

  IF outbox_refs <> 0
     OR inbox_refs <> 0
     OR checkpoint_refs <> 0
     OR trigger_state_refs <> 0
     OR trigger_match_refs <> 0
     OR action_refs <> 0
     OR n6_refs <> 0
     OR downstream_flags <> 0 THEN
    RAISE EXCEPTION 'N3-B2 rollback blocked for %, outbox=%, inbox=%, checkpoint=%, trigger_state=%, trigger_match=%, action=%, n6=%, downstream_or_worker=%',
      target_run_id, outbox_refs, inbox_refs, checkpoint_refs, trigger_state_refs, trigger_match_refs, action_refs, n6_refs, downstream_flags;
  END IF;
END $$;

DELETE FROM common_market_data_quality_item
WHERE run_id = current_setting('app.n3_b2_projection_run_id')
   OR details::TEXT LIKE '%' || current_setting('app.n3_b2_projection_run_id') || '%';

DELETE FROM stock_realtime_projection_metric
WHERE projection_run_id = current_setting('app.n3_b2_projection_run_id');

DELETE FROM index_realtime_projection_metric
WHERE projection_run_id = current_setting('app.n3_b2_projection_run_id');

DELETE FROM board_realtime_projection_metric
WHERE projection_run_id = current_setting('app.n3_b2_projection_run_id');

DELETE FROM common_market_data_run
WHERE run_id = current_setting('app.n3_b2_projection_run_id')
  AND coalesce(downstream_layers_touched, false) = false
  AND coalesce(worker_started, false) = false;

COMMIT;
"""


def fetch_latest_closed_minute_for_runs(cur: Any, today_minute_run_ids: Sequence[str]) -> datetime:
    latest_values = [fetch_latest_closed_minute(cur, run_id) for run_id in today_minute_run_ids]
    return max(latest_values)


def fetch_latest_closed_minute(cur: Any, today_minute_run_id: str) -> datetime:
    latest_values = []
    for config in ASSET_CONFIG.values():
        cur.execute(f"SELECT max(bar_time) AS max_bar_time FROM {config['minute_table']} WHERE run_id = %s", (today_minute_run_id,))
        value = cur.fetchone()["max_bar_time"]
        if value is not None:
            latest_values.append(ensure_shanghai_timezone(value))
    if not latest_values:
        raise RealtimeProjectionExecuteError("N3-B2 blocked: no today minute rows found for current run")
    return max(latest_values)


def fetch_snapshot_outbox(cur: Any, snapshot_run_id: str) -> dict[tuple[str, str], dict[str, Any]]:
    cur.execute(
        """
        SELECT event_id, asset_kind, identity_key, payload_json
        FROM common_event_outbox
        WHERE source_run_id = %s
          AND event_type = 'MarketSnapshotUpdated'
        """,
        (snapshot_run_id,),
    )
    return {
        (row["asset_kind"], row["identity_key"]): {
            "event_id": row["event_id"],
            "payload_json": row["payload_json"],
        }
        for row in cur.fetchall()
    }


def fetch_snapshot_pull_plan_ids(cur: Any, subscription_run_id: str, for_trade_date: str) -> dict[str, int]:
    cur.execute(
        """
        SELECT asset_kind, pull_plan_id
        FROM common_market_data_pull_plan
        WHERE run_id = %s
          AND required_data_kind = 'realtime_daily_snapshot'
          AND data_trade_date = %s
        """,
        (subscription_run_id, for_trade_date),
    )
    return {str(row["asset_kind"]): int(row["pull_plan_id"]) for row in cur.fetchall()}


def projection_window_for_snapshot(snapshot_time: datetime) -> tuple[datetime, datetime, datetime]:
    snapshot_time = ensure_shanghai_timezone(snapshot_time)
    closed_label = snapshot_time.replace(second=0, microsecond=0) - timedelta(minutes=1)
    for start_label, end_label in TRADING_BUCKETS:
        start = combine_date_time(closed_label.date(), start_label)
        end = combine_date_time(closed_label.date(), end_label)
        if start < closed_label <= end:
            return start, end, closed_label
    raise RealtimeProjectionExecuteError(f"N3-B2 blocked: snapshot_time outside trading buckets: {snapshot_time}")


def resolve_projection_time_for_snapshot(
    snapshot_time: datetime,
    *,
    contract: Mapping[str, Any],
    latest_closed_minute: datetime,
) -> dict[str, Any]:
    source_snapshot_time = ensure_shanghai_timezone(snapshot_time)
    policy = dict(contract.get("projection_time_policy") or {})
    mode = str(policy.get("mode") or "").strip()
    if projection_uses_live_current_1m(contract) and not mode:
        closed_label = source_snapshot_time.replace(second=0, microsecond=0)
        projection_snapshot_time = closed_label + timedelta(minutes=1)
        return {
            "source_snapshot_time": source_snapshot_time,
            "projection_snapshot_time": projection_snapshot_time,
            "projection_closed_label": closed_label,
            "policy": {
                "mode": LIVE_CURRENT_1M_SOURCE_MODE,
                "bucket_time_source": "live_current_1m_observed_at",
                "source_snapshot_time": source_snapshot_time.isoformat(),
                "projection_snapshot_time": projection_snapshot_time.isoformat(),
                "projection_bucket_closed_label": closed_label.isoformat(),
                "is_closed_1m": False,
                "c1_dependency": False,
            },
        }
    if not mode:
        closed_label = closed_label_for_observation(source_snapshot_time)
        return {
            "source_snapshot_time": source_snapshot_time,
            "projection_snapshot_time": source_snapshot_time,
            "projection_closed_label": closed_label,
            "policy": {
                "mode": "source_snapshot_time",
                "bucket_time_source": "source_snapshot_time",
                "source_snapshot_time": source_snapshot_time.isoformat(),
                "projection_snapshot_time": source_snapshot_time.isoformat(),
                "projection_bucket_closed_label": closed_label.isoformat(),
            },
        }

    if mode == "fact_only_defer_off_bucket_source_snapshot_time":
        if str(policy.get("bucket_time_source") or "") != "source_snapshot_time":
            raise RealtimeProjectionExecuteError(
                "N3-B2 blocked: fact-only defer projection_time_policy requires bucket_time_source=source_snapshot_time"
            )
        closed_label = closed_label_for_observation(source_snapshot_time)
        projection_snapshot_time = fact_only_projection_bucket_time(source_snapshot_time)
        return {
            "source_snapshot_time": source_snapshot_time,
            "projection_snapshot_time": projection_snapshot_time,
            "projection_closed_label": closed_label,
            "policy": {
                **policy,
                "mode": mode,
                "bucket_time_source": "source_snapshot_time",
                "source_snapshot_time": source_snapshot_time.isoformat(),
                "projection_bucket_closed_label": closed_label.isoformat(),
                "projection_snapshot_time": projection_snapshot_time.isoformat(),
                "snapshot_time_column_semantics": "projection_bucket_time_clamped_to_window_end",
                "off_bucket_source_snapshot_time_handling": "NOOP_PASS_NO_WRITE",
                "no_closed_data_forged": True,
                "maps_midday_to_trading_bucket": False,
            },
        }

    if mode != "standard_outbox_observed_at_to_latest_closed_minute":
        raise RealtimeProjectionExecuteError(f"N3-B2 blocked: unsupported projection_time_policy mode: {mode}")

    bucket_time_source = str(policy.get("bucket_time_source") or "").strip()
    if bucket_time_source != "latest_closed_minute":
        raise RealtimeProjectionExecuteError(
            "N3-B2 blocked: standard outbox projection_time_policy requires bucket_time_source=latest_closed_minute"
        )
    closed_label = ensure_shanghai_timezone(latest_closed_minute).replace(second=0, microsecond=0)
    unclamped_projection_snapshot_time = closed_label + timedelta(minutes=1)
    projection_snapshot_time = clamp_projection_bucket_time_to_window_end(unclamped_projection_snapshot_time)
    resolved_policy = {
        **policy,
        "mode": mode,
        "bucket_time_source": bucket_time_source,
        "source_snapshot_time": source_snapshot_time.isoformat(),
        "projection_bucket_closed_label": closed_label.isoformat(),
        "unclamped_projection_snapshot_time": unclamped_projection_snapshot_time.isoformat(),
        "projection_snapshot_time": projection_snapshot_time.isoformat(),
        "snapshot_time_column_semantics": "projection_bucket_time",
        "projection_snapshot_time_clamped_to_window_end": projection_snapshot_time != unclamped_projection_snapshot_time,
    }
    return {
        "source_snapshot_time": source_snapshot_time,
        "projection_snapshot_time": projection_snapshot_time,
        "projection_closed_label": closed_label,
        "policy": resolved_policy,
    }


def closed_label_for_observation(value: datetime) -> datetime:
    value = ensure_shanghai_timezone(value)
    return value.replace(second=0, microsecond=0) - timedelta(minutes=1)


def fact_only_projection_bucket_time(source_snapshot_time: datetime) -> datetime:
    """Return a DB-valid projection bucket timestamp while preserving source time in trace."""

    source_snapshot_time = ensure_shanghai_timezone(source_snapshot_time)
    _, window_end, _ = projection_window_for_snapshot(source_snapshot_time)
    bucket_time = source_snapshot_time.replace(second=0, microsecond=0)
    if bucket_time > window_end:
        return window_end
    return bucket_time


def clamp_projection_bucket_time_to_window_end(projection_snapshot_time: datetime) -> datetime:
    """Keep projection metric snapshot_time inside the DB-checked active window."""

    projection_snapshot_time = ensure_shanghai_timezone(projection_snapshot_time)
    _, window_end, _ = projection_window_for_snapshot(projection_snapshot_time)
    if projection_snapshot_time > window_end:
        return window_end
    return projection_snapshot_time


def combine_date_time(day: date, hhmm: str) -> datetime:
    hour, minute = [int(part) for part in hhmm.split(":")]
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=ASIA_SHANGHAI)


def previous_day_datetime(value: datetime, previous_trade_date: str) -> datetime:
    day = date(int(previous_trade_date[:4]), int(previous_trade_date[4:6]), int(previous_trade_date[6:8]))
    return datetime(day.year, day.month, day.day, value.hour, value.minute, value.second, value.microsecond, tzinfo=ASIA_SHANGHAI)


def ensure_shanghai_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=ASIA_SHANGHAI)
    return value.astimezone(ASIA_SHANGHAI)


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def decimal_to_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    quantized = value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    return format(quantized.normalize(), "f")


def sum_decimal(rows: Sequence[Mapping[str, Any]], key: str) -> Decimal | None:
    total = Decimal("0")
    seen = False
    for row in rows:
        value = decimal_or_none(row.get(key))
        if value is not None:
            total += value
            seen = True
    return total if seen else None


def first_decimal(rows: Sequence[Mapping[str, Any]], key: str) -> Decimal | None:
    return decimal_or_none(rows[0].get(key)) if rows else None


def last_decimal(rows: Sequence[Mapping[str, Any]], key: str) -> Decimal | None:
    return decimal_or_none(rows[-1].get(key)) if rows else None


def max_decimal(rows: Sequence[Mapping[str, Any]], key: str) -> Decimal | None:
    values = [decimal_or_none(row.get(key)) for row in rows if row.get(key) is not None]
    return max(values) if values else None


def min_decimal(rows: Sequence[Mapping[str, Any]], key: str) -> Decimal | None:
    values = [decimal_or_none(row.get(key)) for row in rows if row.get(key) is not None]
    return min(values) if values else None


def rolling_average_amount(rows: Sequence[Mapping[str, Any]], *, count: int) -> Decimal | None:
    if not rows:
        return None
    last_rows = rows[-count:]
    total = sum_decimal(last_rows, "amount")
    return total / Decimal(len(last_rows)) if total is not None and last_rows else None


def classify_price_direction(price_change_pct: Decimal | None, flat_threshold: Decimal) -> str:
    if price_change_pct is None:
        return "unknown"
    if abs(price_change_pct) <= flat_threshold:
        return "flat"
    return "up" if price_change_pct > 0 else "down"


def classify_projection_signal(
    price_direction_status: str,
    amount_projection_ratio: Decimal | None,
    *,
    expand_threshold: Decimal,
    shrink_threshold: Decimal,
) -> str:
    if price_direction_status == "unknown" or amount_projection_ratio is None:
        return "unknown"
    if price_direction_status == "flat":
        return "flat"
    if price_direction_status == "up":
        if amount_projection_ratio >= expand_threshold:
            return "up_volume_expanding"
        if amount_projection_ratio <= shrink_threshold:
            return "up_volume_shrinking"
        return "up_volume_flat"
    if price_direction_status == "down":
        if amount_projection_ratio <= shrink_threshold:
            return "down_volume_shrinking"
        if amount_projection_ratio >= expand_threshold:
            return "down_volume_expanding"
        return "down_volume_flat"
    return "unknown"


def normalize_json_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            output[key] = value.isoformat()
        elif isinstance(value, Decimal):
            output[key] = str(value)
        else:
            output[key] = value
    return output


def format_projection_execute_report(report: Mapping[str, Any]) -> str:
    actual = report["actual_projection_rows"]
    quality = report["quality"]
    return "\n".join(
        [
            "# N3-B2 Realtime Projection Execute Report",
            "",
            "## Summary",
            "",
            f"- result: `{report.get('result', 'EXECUTE_PASS')}`",
            f"- projection_run_id: `{report['projection_run_id']}`",
            f"- status: `{(report.get('post_execute') or {}).get('source_run_rows', {}).get(report['projection_run_id'], {}).get('status', 'unknown')}`",
            f"- projection_rows_written: `{actual['total_rows']}`",
            f"- ready_by_asset: `{json.dumps(actual['ready_by_asset'], ensure_ascii=False, sort_keys=True)}`",
            f"- not_ready_by_asset: `{json.dumps(actual['not_ready_by_asset'], ensure_ascii=False, sort_keys=True)}`",
            f"- projection_signal_status: `{json.dumps(actual['projection_signal_status'], ensure_ascii=False, sort_keys=True)}`",
            f"- P0/P1/P2: `{quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}`",
            f"- rollback_sql_path: `{report['rollback_sql_path']}`",
            "",
            "## Boundary",
            "",
            "- writes_outbox: `false`",
            "- updates_market_snapshot_payload: `false`",
            "- outbox_consumed: `false`",
            "- downstream_layers_touched: `false`",
            "- worker_started: `false`",
        ]
    ) + "\n"
