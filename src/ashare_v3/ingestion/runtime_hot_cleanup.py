"""Plan and execute controlled cleanup for dirty runtime hot-store rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

import psycopg
from psycopg import sql

from ashare_v3.ingestion.common import require_yyyymmdd
from ashare_v3.ingestion.runtime_archive import (
    DEFAULT_RUNTIME_ARCHIVE_ROOT,
    make_runtime_archive_manifest_path,
    runtime_archive_side_effects,
)
from ashare_v3.ingestion.runtime_archive_execute import (
    DEFAULT_DSN,
    EOD_RECONCILIATION_ITEM_TABLES,
    runtime_table_specs,
)


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
CONFIRM_TOKEN = "DIRTY_HOT_KEEP_2_CLEANUP_CONFIRMED"
KEEP5_CONFIRM_TOKEN = "RUNTIME_HOT_KEEP5_CLEANUP_CONFIRMED"
DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN = "RUNTIME_HOT_KEEP5_DIRECT_DELETE_NO_ARCHIVE_CONFIRMED"
DEFAULT_PLAN_PATH = "docs/runtime_archive/dirty_hot_cleanup/keep2_cleanup_plan.json"
DEFAULT_CLOSEOUT_PATH = "docs/runtime_archive/dirty_hot_cleanup/keep2_cleanup_closeout.json"
DEFAULT_RETENTION_TRADE_DAYS = 2
COUNT_STATEMENT_TIMEOUT_MS = 30_000
COUNT_TIMEOUT_RETRIES = 2
DELETE_STATEMENT_TIMEOUT_MS = 30_000
DELETE_LOCK_TIMEOUT_MS = 1_000
INBOX_ID_BATCH_SIZE = 50
EVENT_ID_BATCH_SIZE = 250
SUBSCRIPTION_ID_BATCH_SIZE = 250
ACTION_FACT_ID_BATCH_SIZE = 250
TRIGGER_STATE_ID_CHUNK_SIZE = 1_000
HOT_TRADE_DATE_DRIVER_QUERIES = (
    "select distinct for_trade_date::text from common_market_data_run where for_trade_date is not null",
    "select distinct for_trade_date::text from common_trigger_run where for_trade_date is not null",
    "select distinct for_trade_date::text from common_action_run where for_trade_date is not null",
    "select distinct trade_date::text from common_event_outbox where trade_date is not null",
)
SOURCE_LAYER_BY_RUNTIME_LAYER = {
    "n3": "N3_market_data",
    "n4": "N4_trigger",
    "n5": "N5_action",
}
TRIGGER_REPLAY_AUDIT_TABLES = (
    "stock_trigger_replay_audit",
    "index_trigger_replay_audit",
    "board_trigger_replay_audit",
)
N6_USER_PROJECTION_DEPENDENT_TABLES = (
    "user_notification_queue",
    "user_signal_card",
    "user_signal_projection",
)


def _intraday_time_windows_1m() -> tuple[tuple[str, str, str], ...]:
    windows: list[tuple[str, str, str]] = []
    for prefix, hour, start_minute, end_minute in (
        ("morning", 9, 30, 60),
        ("morning", 10, 0, 60),
        ("morning", 11, 0, 31),
        ("afternoon", 13, 0, 60),
        ("afternoon", 14, 0, 60),
        ("afternoon", 15, 0, 1),
    ):
        for minute in range(start_minute, end_minute):
            next_hour = hour + 1 if minute == 59 else hour
            next_minute = 0 if minute == 59 else minute + 1
            windows.append(
                (
                    f"{prefix}_{hour:02d}{minute:02d}_{next_hour:02d}{next_minute:02d}",
                    f"{hour:02d}:{minute:02d}:00",
                    f"{next_hour:02d}:{next_minute:02d}:00",
                )
            )
    return tuple(windows)


INTRADAY_TIME_WINDOWS = (
    ("morning_0900_1000", "09:00:00", "10:00:00"),
    ("morning_1000_1100", "10:00:00", "11:00:00"),
    ("morning_1100_1131", "11:00:00", "11:31:00"),
    ("afternoon_1300_1400", "13:00:00", "14:00:00"),
    ("afternoon_1400_1501", "14:00:00", "15:01:00"),
)
INTRADAY_TIME_WINDOWS_FINE = (
    ("morning_0930_1000", "09:30:00", "10:00:00"),
    ("morning_1000_1030", "10:00:00", "10:30:00"),
    ("morning_1030_1100", "10:30:00", "11:00:00"),
    ("morning_1100_1131", "11:00:00", "11:31:00"),
    ("afternoon_1300_1330", "13:00:00", "13:30:00"),
    ("afternoon_1330_1400", "13:30:00", "14:00:00"),
    ("afternoon_1400_1430", "14:00:00", "14:30:00"),
    ("afternoon_1430_1501", "14:30:00", "15:01:00"),
)
INTRADAY_TIME_WINDOWS_STOCK_15M = (
    ("morning_0930_0945", "09:30:00", "09:45:00"),
    ("morning_0945_1000", "09:45:00", "10:00:00"),
    ("morning_1000_1015", "10:00:00", "10:15:00"),
    ("morning_1015_1030", "10:15:00", "10:30:00"),
    ("morning_1030_1045", "10:30:00", "10:45:00"),
    ("morning_1045_1100", "10:45:00", "11:00:00"),
    ("morning_1100_1115", "11:00:00", "11:15:00"),
    ("morning_1115_1131", "11:15:00", "11:31:00"),
    ("afternoon_1300_1315", "13:00:00", "13:15:00"),
    ("afternoon_1315_1330", "13:15:00", "13:30:00"),
    ("afternoon_1330_1345", "13:30:00", "13:45:00"),
    ("afternoon_1345_1400", "13:45:00", "14:00:00"),
    ("afternoon_1400_1415", "14:00:00", "14:15:00"),
    ("afternoon_1415_1430", "14:15:00", "14:30:00"),
    ("afternoon_1430_1445", "14:30:00", "14:45:00"),
    ("afternoon_1445_1501", "14:45:00", "15:01:00"),
)
INTRADAY_TIME_WINDOWS_STOCK_5M = (
    ("morning_0930_0935", "09:30:00", "09:35:00"),
    ("morning_0935_0940", "09:35:00", "09:40:00"),
    ("morning_0940_0945", "09:40:00", "09:45:00"),
    ("morning_0945_0950", "09:45:00", "09:50:00"),
    ("morning_0950_0955", "09:50:00", "09:55:00"),
    ("morning_0955_1000", "09:55:00", "10:00:00"),
    ("morning_1000_1005", "10:00:00", "10:05:00"),
    ("morning_1005_1010", "10:05:00", "10:10:00"),
    ("morning_1010_1015", "10:10:00", "10:15:00"),
    ("morning_1015_1020", "10:15:00", "10:20:00"),
    ("morning_1020_1025", "10:20:00", "10:25:00"),
    ("morning_1025_1030", "10:25:00", "10:30:00"),
    ("morning_1030_1035", "10:30:00", "10:35:00"),
    ("morning_1035_1040", "10:35:00", "10:40:00"),
    ("morning_1040_1045", "10:40:00", "10:45:00"),
    ("morning_1045_1050", "10:45:00", "10:50:00"),
    ("morning_1050_1055", "10:50:00", "10:55:00"),
    ("morning_1055_1100", "10:55:00", "11:00:00"),
    ("morning_1100_1105", "11:00:00", "11:05:00"),
    ("morning_1105_1110", "11:05:00", "11:10:00"),
    ("morning_1110_1115", "11:10:00", "11:15:00"),
    ("morning_1115_1120", "11:15:00", "11:20:00"),
    ("morning_1120_1125", "11:20:00", "11:25:00"),
    ("morning_1125_1131", "11:25:00", "11:31:00"),
    ("afternoon_1300_1305", "13:00:00", "13:05:00"),
    ("afternoon_1305_1310", "13:05:00", "13:10:00"),
    ("afternoon_1310_1315", "13:10:00", "13:15:00"),
    ("afternoon_1315_1320", "13:15:00", "13:20:00"),
    ("afternoon_1320_1325", "13:20:00", "13:25:00"),
    ("afternoon_1325_1330", "13:25:00", "13:30:00"),
    ("afternoon_1330_1335", "13:30:00", "13:35:00"),
    ("afternoon_1335_1340", "13:35:00", "13:40:00"),
    ("afternoon_1340_1345", "13:40:00", "13:45:00"),
    ("afternoon_1345_1350", "13:45:00", "13:50:00"),
    ("afternoon_1350_1355", "13:50:00", "13:55:00"),
    ("afternoon_1355_1400", "13:55:00", "14:00:00"),
    ("afternoon_1400_1405", "14:00:00", "14:05:00"),
    ("afternoon_1405_1410", "14:05:00", "14:10:00"),
    ("afternoon_1410_1415", "14:10:00", "14:15:00"),
    ("afternoon_1415_1420", "14:15:00", "14:20:00"),
    ("afternoon_1420_1425", "14:20:00", "14:25:00"),
    ("afternoon_1425_1430", "14:25:00", "14:30:00"),
    ("afternoon_1430_1435", "14:30:00", "14:35:00"),
    ("afternoon_1435_1440", "14:35:00", "14:40:00"),
    ("afternoon_1440_1445", "14:40:00", "14:45:00"),
    ("afternoon_1445_1450", "14:45:00", "14:50:00"),
    ("afternoon_1450_1455", "14:50:00", "14:55:00"),
    ("afternoon_1455_1501", "14:55:00", "15:01:00"),
)
INTRADAY_TIME_WINDOWS_STOCK_1M = _intraday_time_windows_1m()
INTRADAY_LABEL_WINDOWS = (
    ("morning_0900_1000", "09:00", "10:00"),
    ("morning_1000_1100", "10:00", "11:00"),
    ("morning_1100_1131", "11:00", "11:31"),
    ("afternoon_1300_1400", "13:00", "14:00"),
    ("afternoon_1400_1501", "14:00", "15:01"),
)
INTRADAY_LABEL_WINDOWS_5M = tuple(
    (label, start_time[:5], end_time[:5])
    for label, start_time, end_time in INTRADAY_TIME_WINDOWS_STOCK_5M
)
LARGE_TABLE_BATCH_CONFIG = {
    ("n3", "stock_minute_bar_1m"): ("bar_time", "intraday_time_windows_stock_1m"),
    ("n3", "index_minute_bar_1m"): ("bar_time", "intraday_time_windows_fine"),
    ("n3", "board_minute_bar_1m"): ("bar_time", "intraday_time_windows_stock_5m"),
    ("n3", "stock_realtime_projection_metric"): ("snapshot_time", "intraday_time_windows_fine"),
    ("n3", "index_action_confirmation_projection_metric"): ("metric_minute_label", "intraday_label_windows_5m"),
    ("n3", "board_action_confirmation_projection_metric"): ("metric_minute_label", "intraday_label_windows_5m"),
    ("n3", "stock_action_confirmation_projection_metric"): ("metric_minute_label", "intraday_label_windows_5m"),
}
TRIGGER_RUN_ID_BATCH_TABLES = {
    ("n4", "common_trigger_match"),
}
TRIGGER_STATE_ID_CHUNK_TABLES = {
    ("n4", "common_trigger_state"),
}
MARKET_DATA_RUN_ID_BATCH_TABLES = {
    ("n3", "common_market_data_subscription"),
}
ACTION_FACT_ID_BATCH_TABLES = {
    ("n5", "stock_action_fact"),
    ("n5", "index_action_fact"),
    ("n5", "board_action_fact"),
}
SUBSCRIPTION_ID_CHILD_TABLES = {
    ("n3", "stock_minute_bar_1m"): "subscription_id",
    ("n3", "index_minute_bar_1m"): "subscription_id",
    ("n3", "board_minute_bar_1m"): "subscription_id",
    ("n3", "stock_previous_day_minute_preload_status"): "subscription_id",
    ("n3", "index_previous_day_minute_preload_status"): "subscription_id",
    ("n3", "board_previous_day_minute_preload_status"): "subscription_id",
    ("n3", "stock_realtime_daily_snapshot"): "subscription_id",
    ("n3", "index_realtime_daily_snapshot"): "subscription_id",
    ("n3", "board_realtime_daily_snapshot"): "subscription_id",
    ("n3", "stock_realtime_projection_metric"): "subscription_id",
    ("n3", "index_realtime_projection_metric"): "subscription_id",
    ("n3", "board_realtime_projection_metric"): "subscription_id",
    ("n4", "stock_trigger_context_snapshot"): "source_market_subscription_id",
    ("n4", "index_trigger_context_snapshot"): "source_market_subscription_id",
    ("n4", "board_trigger_context_snapshot"): "source_market_subscription_id",
    ("n4", "common_trigger_match"): "source_market_subscription_id",
}
DIRECT_COUNT_BATCH_SKIP_STRATEGIES = {
    "event_id_chunks_direct_delete",
    "subscription_id_chunks_direct_delete",
    "action_fact_id_chunks_direct_delete",
}


@dataclass(frozen=True)
class RuntimeHotCleanupBatch:
    label: str
    start_time: str
    end_time: str


@dataclass(frozen=True)
class RuntimeHotCleanupSpec:
    layer: str
    table: str
    count_sql: str
    delete_sql: str
    params: tuple[Any, ...]
    batch_column: str | None = None
    batch_strategy: str | None = None
    batches: tuple[RuntimeHotCleanupBatch, ...] = ()
    batch_source_sql: str | None = None


@dataclass(frozen=True)
class RuntimeHotCountResult:
    rows: int
    timing: dict[str, Any]
    blocker: dict[str, Any] | None = None
    timings: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class RuntimeHotDeleteResult:
    deleted_rows: list[dict[str, Any]]
    delete_units_total: int
    delete_units_executed: int
    delete_units_limit: int | None = None

    @property
    def delete_units_remaining(self) -> int:
        return max(0, self.delete_units_total - self.delete_units_executed)


class RuntimeHotDeleteError(RuntimeError):
    def __init__(
        self,
        *,
        trade_date: str,
        spec: RuntimeHotCleanupSpec,
        exc: Exception,
        duration_ms: float,
    ) -> None:
        self.trade_date = trade_date
        self.spec = spec
        self.original_exception = exc
        self.duration_ms = duration_ms
        super().__init__(f"{spec.layer}.{spec.table}:{trade_date}: {type(exc).__name__}: {exc}")

    def blocker(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "trade_date": self.trade_date,
            "layer": self.spec.layer,
            "table": self.spec.table,
            "duration_ms": self.duration_ms,
            "error": f"{type(self.original_exception).__name__}: {self.original_exception}",
        }
        if self.spec.batches:
            batch = self.spec.batches[0]
            batch_start, batch_end = batch_timing_bounds(self.spec)
            payload.update(
                {
                    "batch_label": batch.label,
                    "batch_start": batch_start,
                    "batch_end": batch_end,
                }
            )
        return payload


@dataclass(frozen=True)
class RuntimeHotCleanupPlan:
    """Calendar-authoritative, independently discovered keep-5 cleanup plan."""

    current_trade_date: str
    retained_trade_dates: tuple[str, ...]
    database_trade_dates: tuple[str, ...]
    database_protected_future_trade_dates: tuple[str, ...]
    database_cleanup_trade_dates: tuple[str, ...]
    local_trade_dates: tuple[str, ...]
    local_cleanup_trade_dates: tuple[str, ...]
    database_delete_plan: tuple[dict[str, Any], ...]
    inbox_delete_units: tuple[dict[str, Any], ...]
    local_allowlist: tuple[dict[str, Any], ...]
    blockers: tuple[str, ...] = ()
    local_archive_verified: bool = False
    database_discovery_blocker: str = ""
    database_cleanup_enabled: bool = True
    direct_delete_no_archive: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "RuntimeHotCleanupPlan.v2",
            "retention_policy": "current_trade_date_plus_previous_5_completed_trade_dates_v1",
            "trade_calendar_authority": "common_trade_calendar",
            "current_trade_date": self.current_trade_date,
            "retained_trade_dates": list(self.retained_trade_dates),
            "database_trade_dates": list(self.database_trade_dates),
            "database_protected_future_trade_dates": list(self.database_protected_future_trade_dates),
            "database_cleanup_trade_dates": list(self.database_cleanup_trade_dates),
            "local_trade_dates": list(self.local_trade_dates),
            "local_cleanup_trade_dates": list(self.local_cleanup_trade_dates),
            "database_delete_plan": [dict(row) for row in self.database_delete_plan],
            "inbox_delete_units": [dict(unit) for unit in self.inbox_delete_units],
            "local_allowlist": [dict(entry) for entry in self.local_allowlist],
            "local_cleanup_policy": "verified-archive-required",
            "local_archive_verified": self.local_archive_verified,
            "database_discovery_blocker": self.database_discovery_blocker,
            "database_cleanup_mode": (
                "enabled" if self.database_cleanup_enabled else "disabled_by_layer_policy"
            ),
            "database_failure_blocks_verified_local": False,
            "direct_delete_no_archive": self.direct_delete_no_archive,
            "blocked_by_layer": [
                {"scope": "n6_user_projection", "layer_role": "N6_user"},
            ],
            "excluded_scopes": [
                {"scope": "n3_previous_day_minute_cumulative", "layer_role": "N3_market_data"},
                {"scope": "n3t_action_confirmation_projection_metric", "layer_role": "N3_market_data"},
                {"scope": "n6_user_projection", "layer_role": "N6_user"},
            ],
            "blockers": list(self.blockers),
        }


def build_keep2_dirty_hot_cleanup_plan(
    *,
    dsn: str = DEFAULT_DSN,
    trade_dates: Iterable[str] | None = None,
    retention_trade_days: int = DEFAULT_RETENTION_TRADE_DAYS,
    plan_path: str | Path = DEFAULT_PLAN_PATH,
    archive_root: str | Path = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    require_verified_archive: bool = False,
    direct_delete_no_archive: bool = False,
    skip_row_count_plan: bool = False,
    connection_factory: Callable[[str], Any] = psycopg.connect,
    table_counter: Callable[[RuntimeHotCleanupSpec, str], int] | None = None,
    running_writer_trade_dates: Iterable[str] = (),
    active_archive_processes: Iterable[dict[str, Any]] = (),
    fk_closure_auditor: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if require_verified_archive and direct_delete_no_archive:
        raise ValueError("require_verified_archive and direct_delete_no_archive are mutually exclusive")
    retention = normalize_retention_trade_days(retention_trade_days)
    discovered_trade_dates = (
        sorted({require_yyyymmdd(str(item), "trade_date") for item in trade_dates})
        if trade_dates is not None
        else discover_hot_trade_dates(dsn=dsn, connection_factory=connection_factory)
    )
    retained = discovered_trade_dates[-retention:]
    cleanup_dates = discovered_trade_dates[:-retention]
    running_writer_set = {require_yyyymmdd(str(item), "running_writer_trade_date") for item in running_writer_trade_dates}
    blockers: list[str] = []
    if set(retained) & set(cleanup_dates):
        blockers.append("retained_trade_date_in_cleanup_scope")
    writer_overlap = sorted(running_writer_set & set(cleanup_dates))
    blockers.extend(f"writer_running_for_cleanup_trade_date:{trade_date}" for trade_date in writer_overlap)
    active_archive_process_evidence = list(active_archive_processes)
    if direct_delete_no_archive and active_archive_process_evidence:
        blockers.append("archive_process_conflict")
    archive_manifest_evidence: dict[str, Any] = {}
    if require_verified_archive:
        archive_manifest_evidence, archive_blockers = verified_archive_manifest_evidence(
            cleanup_dates=cleanup_dates,
            archive_root=archive_root,
        )
        blockers.extend(archive_blockers)

    specs = build_hot_cleanup_specs(direct_event_infra=direct_delete_no_archive)
    fk_closure_evidence: dict[str, Any] = {}
    if direct_delete_no_archive and not blockers:
        fk_closure_evidence = (
            fk_closure_auditor(
                dsn=dsn,
                cleanup_dates=cleanup_dates,
                connection_factory=connection_factory,
            )
            if fk_closure_auditor
            else audit_runtime_hot_cleanup_fk_closure(
                dsn=dsn,
                cleanup_dates=cleanup_dates,
                connection_factory=connection_factory,
            )
        )
        if int(fk_closure_evidence.get("missing_child_scope_count") or 0):
            blockers.append("fk_closure_missing_child_scope")
        if int(fk_closure_evidence.get("order_bad_count") or 0):
            blockers.append("fk_closure_order_bad")
    table_plan: list[dict[str, Any]] = []
    count_timings: list[dict[str, Any]] = []
    slow_or_blocked_table: dict[str, Any] | None = None
    if not blockers and skip_row_count_plan:
        table_plan = [
            {
                "trade_date": trade_date,
                "layer": spec.layer,
                "table": spec.table,
                "planned_delete_rows": -1,
                "row_count_skipped": True,
            }
            for trade_date in cleanup_dates
            for spec in specs
        ]
    elif not blockers:
        for trade_date in cleanup_dates:
            for spec_template in specs:
                spec = bind_cleanup_spec(spec_template, trade_date)
                count_result = count_rows_with_timing(
                    dsn=dsn,
                    spec=spec,
                    connection_factory=connection_factory,
                    table_counter=table_counter,
                )
                count_timings.extend(count_result.timings or (count_result.timing,))
                if count_result.blocker:
                    slow_or_blocked_table = count_result.blocker
                    blockers.append(f"count_blocked:{spec.layer}.{spec.table}:{trade_date}")
                    break
                rows = count_result.rows
                if rows:
                    table_plan.append(
                        {
                            "trade_date": trade_date,
                            "layer": spec.layer,
                            "table": spec.table,
                            "planned_delete_rows": rows,
                        }
                    )
            if slow_or_blocked_table:
                break

    result = "DIRTY_HOT_KEEP2_CLEANUP_PLAN_PASS" if not blockers else "DIRTY_HOT_KEEP2_CLEANUP_PLAN_BLOCKED"
    side_effects = {
        **runtime_archive_side_effects(),
        "writes_database": False,
        "cleanup_local_runtime": False,
        "cleanup_local_runtime_files": False,
    }
    payload = {
        "result": result,
        "component": "Runtime Dirty Hot Keep2 Cleanup",
        "mode": "plan_only",
        "layer_role": "runtime_control",
        "created_at": datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat(),
        "retention_trade_days": retention,
        "retention_policy": "latest_trade_dates_from_hot_runtime_store",
        "archive_required": bool(require_verified_archive),
        "direct_delete_no_archive": bool(direct_delete_no_archive),
        "cleanup_policy": (
            "direct_delete_no_archive_v1" if direct_delete_no_archive else "manifest_gated_or_legacy_cleanup_v1"
        ),
        "row_count_plan_skipped": bool(skip_row_count_plan),
        "archive_root": str(archive_root),
        "archive_manifest_evidence": archive_manifest_evidence,
        "active_archive_processes": active_archive_process_evidence,
        "archive_process_conflict": bool(active_archive_process_evidence),
        "fk_closure_evidence": fk_closure_evidence,
        "trade_dates": discovered_trade_dates,
        "retained_trade_dates": retained,
        "cleanup_trade_dates": cleanup_dates,
        "cleanup_authorized": False,
        "cleanup_executed": False,
        "confirm_token_required": (
            DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN if direct_delete_no_archive else CONFIRM_TOKEN
        ),
        "table_delete_plan": table_plan,
        "planned_delete_total_rows": (
            None if skip_row_count_plan else sum(int(row["planned_delete_rows"]) for row in table_plan)
        ),
        "count_timings": count_timings,
        "slow_or_blocked_table": slow_or_blocked_table or {},
        "blockers": blockers,
        "plan_path": str(plan_path),
        "side_effects": side_effects,
    }
    write_json(plan_path, payload)
    return payload


def audit_runtime_hot_cleanup_fk_closure(
    *,
    dsn: str = DEFAULT_DSN,
    cleanup_dates: Iterable[str],
    connection_factory: Callable[[str], Any] = psycopg.connect,
) -> dict[str, Any]:
    normalized_dates = tuple(require_yyyymmdd(str(item), "cleanup_trade_date") for item in cleanup_dates)
    specs = build_hot_cleanup_specs()
    scoped_tables = {spec.table for spec in specs}
    delete_order: dict[str, int] = {}
    for index, spec in enumerate(specs):
        delete_order.setdefault(spec.table, index)
    parent_date_col = {table: date_column for _layer, table, date_column in runtime_table_specs()}
    fk_query = """
        select
          con.conname,
          child.relname as child_table,
          parent.relname as parent_table,
          array_agg(child_att.attname order by k.ord) as child_cols,
          array_agg(parent_att.attname order by k.ord) as parent_cols
        from pg_constraint con
        join pg_class child on child.oid = con.conrelid
        join pg_namespace child_ns on child_ns.oid = child.relnamespace
        join pg_class parent on parent.oid = con.confrelid
        join pg_namespace parent_ns on parent_ns.oid = parent.relnamespace
        join unnest(con.conkey, con.confkey) with ordinality as k(child_attnum, parent_attnum, ord) on true
        join pg_attribute child_att on child_att.attrelid = child.oid and child_att.attnum = k.child_attnum
        join pg_attribute parent_att on parent_att.attrelid = parent.oid and parent_att.attnum = k.parent_attnum
        where con.contype = 'f'
          and child_ns.nspname = 'public'
          and parent_ns.nspname = 'public'
        group by con.conname, child.relname, parent.relname
        order by parent.relname, child.relname, con.conname
    """
    missing_child_scope: list[dict[str, Any]] = []
    order_bad: list[dict[str, Any]] = []
    unknown_parent_scope: list[dict[str, Any]] = []

    def qident(name: str) -> sql.Identifier:
        return sql.Identifier(name)

    def join_predicate(child_alias: str, parent_alias: str, child_cols: list[str], parent_cols: list[str]) -> sql.Composed:
        parts = [
            sql.SQL("{}.{} = {}.{}").format(
                sql.Identifier(child_alias),
                qident(child_col),
                sql.Identifier(parent_alias),
                qident(parent_col),
            )
            for child_col, parent_col in zip(child_cols, parent_cols)
        ]
        return sql.SQL(" and ").join(parts)

    with connection_factory(dsn) as conn:
        conn.execute("begin read only")
        conn.execute("set local statement_timeout = 15000")
        fk_rows = conn.execute(fk_query).fetchall()
        for constraint_name, child_table, parent_table, child_cols, parent_cols in fk_rows:
            child_cols = list(child_cols)
            parent_cols = list(parent_cols)
            if parent_table not in scoped_tables:
                continue
            if parent_table not in parent_date_col:
                unknown_parent_scope.append(
                    {
                        "constraint": constraint_name,
                        "child_table": child_table,
                        "parent_table": parent_table,
                        "child_cols": child_cols,
                        "parent_cols": parent_cols,
                    }
                )
                continue
            parent_date_column = parent_date_col[parent_table]
            count_query = sql.SQL(
                "select count(*) from {} c "
                "where exists (select 1 from {} p where {} and p.{} = any(%s))"
            ).format(
                qident(child_table),
                qident(parent_table),
                join_predicate("c", "p", child_cols, parent_cols),
                qident(parent_date_column),
            )
            if child_table not in scoped_tables:
                ref_count = int(conn.execute(count_query, (list(normalized_dates),)).fetchone()[0])
                if ref_count:
                    missing_child_scope.append(
                        {
                            "constraint": constraint_name,
                            "child_table": child_table,
                            "parent_table": parent_table,
                            "child_cols": child_cols,
                            "parent_cols": parent_cols,
                            "ref_count": ref_count,
                        }
                    )
                continue
            if delete_order.get(parent_table, 10**9) < delete_order.get(child_table, -1):
                ref_count = int(conn.execute(count_query, (list(normalized_dates),)).fetchone()[0])
                if ref_count:
                    order_bad.append(
                        {
                            "constraint": constraint_name,
                            "child_table": child_table,
                            "parent_table": parent_table,
                            "child_order": delete_order.get(child_table),
                            "parent_order": delete_order.get(parent_table),
                            "ref_count": ref_count,
                        }
                    )
        conn.rollback()
    return {
        "policy": "runtime_hot_cleanup_fk_closure_v1",
        "cleanup_trade_dates": list(normalized_dates),
        "scoped_table_count": len(scoped_tables),
        "fk_constraint_count": len(fk_rows),
        "missing_child_scope_count": len(missing_child_scope),
        "missing_child_scope": missing_child_scope,
        "order_bad_count": len(order_bad),
        "order_bad": order_bad,
        "unknown_parent_scope_count": len(unknown_parent_scope),
        "unknown_parent_scope": unknown_parent_scope,
    }


def execute_keep2_dirty_hot_cleanup(
    *,
    plan_path: str | Path,
    confirm_token: str,
    dsn: str = DEFAULT_DSN,
    closeout_path: str | Path = DEFAULT_CLOSEOUT_PATH,
    current_trade_dates: Iterable[str] | None = None,
    expected_confirm_token: str = CONFIRM_TOKEN,
    connection_factory: Callable[[str], Any] = psycopg.connect,
    table_counter: Callable[[RuntimeHotCleanupSpec, str], int] | None = None,
    table_deleter: Callable[[RuntimeHotCleanupSpec, str], int] | None = None,
    max_delete_units: int | None = None,
) -> dict[str, Any]:
    plan = load_json(plan_path)
    side_effects = {
        **runtime_archive_side_effects(),
        "writes_database": False,
        "cleanup_local_runtime": False,
        "cleanup_local_runtime_files": False,
    }
    if str(confirm_token or "").strip() != str(expected_confirm_token):
        return blocked_closeout(
            result="BLOCKED_CONFIRM_TOKEN_REQUIRED",
            plan=plan,
            closeout_path=closeout_path,
            side_effects=side_effects,
        )
    if plan.get("result") != "DIRTY_HOT_KEEP2_CLEANUP_PLAN_PASS":
        return blocked_closeout(
            result="BLOCKED_PLAN_NOT_PASS",
            plan=plan,
            closeout_path=closeout_path,
            side_effects=side_effects,
        )

    current_dates = (
        sorted({require_yyyymmdd(str(item), "trade_date") for item in current_trade_dates})
        if current_trade_dates is not None
        else discover_hot_trade_dates(dsn=dsn, connection_factory=connection_factory)
    )
    retention = int(plan["retention_trade_days"])
    current_retained = current_dates[-retention:]
    planned_retained = list(plan.get("retained_trade_dates") or [])
    if current_retained != planned_retained:
        payload = blocked_closeout(
            result="BLOCKED_RETAINED_TRADE_DATES_CHANGED",
            plan=plan,
            closeout_path=closeout_path,
            side_effects=side_effects,
        )
        payload["current_retained_trade_dates"] = current_retained
        write_json(closeout_path, payload)
        return payload

    cleanup_dates = list(plan.get("cleanup_trade_dates") or [])
    retained_overlap = sorted(set(cleanup_dates) & set(planned_retained))
    if retained_overlap:
        payload = blocked_closeout(
            result="BLOCKED_RETAINED_TRADE_DATE_IN_CLEANUP_SCOPE",
            plan=plan,
            closeout_path=closeout_path,
            side_effects=side_effects,
        )
        payload["retained_overlap"] = retained_overlap
        write_json(closeout_path, payload)
        return payload
    if bool(plan.get("archive_required")):
        _archive_evidence, archive_blockers = verified_archive_manifest_evidence(
            cleanup_dates=cleanup_dates,
            archive_root=Path(str(plan.get("archive_root") or DEFAULT_RUNTIME_ARCHIVE_ROOT)),
        )
        if archive_blockers:
            payload = blocked_closeout(
                result="BLOCKED_ARCHIVE_MANIFEST_NOT_VERIFIED",
                plan=plan,
                closeout_path=closeout_path,
                side_effects=side_effects,
            )
            payload["archive_blockers"] = archive_blockers
            write_json(closeout_path, payload)
            return payload

    expected = {
        (row["trade_date"], row["layer"], row["table"]): int(row["planned_delete_rows"])
        for row in list(plan.get("table_delete_plan") or [])
    }
    specs = build_hot_cleanup_specs(direct_event_infra=bool(plan.get("direct_delete_no_archive")))
    specs_to_delete: list[tuple[str, RuntimeHotCleanupSpec, int]] = []
    # Delete in dependency/spec order across all cleanup dates. Some child rows for
    # date T+1 reference parent N3 runs from date T (previous-day minute inputs).
    for spec_template in specs:
        for trade_date in cleanup_dates:
            spec = bind_cleanup_spec(spec_template, trade_date)
            key = (trade_date, spec.layer, spec.table)
            planned_count = expected.get(key, 0)
            if bool(plan.get("row_count_plan_skipped")):
                specs_to_delete.append((trade_date, spec, -1))
                continue
            count_result = count_rows_with_timing(
                dsn=dsn,
                spec=spec,
                connection_factory=connection_factory,
                table_counter=table_counter,
            )
            if count_result.blocker:
                payload = blocked_closeout(
                    result="BLOCKED_ROW_COUNT_RECHECK_TIMEOUT",
                    plan=plan,
                    closeout_path=closeout_path,
                    side_effects=side_effects,
                )
                payload["slow_or_blocked_table"] = count_result.blocker
                payload["count_timing"] = count_result.timing
                payload["count_timings"] = list(count_result.timings or (count_result.timing,))
                write_json(closeout_path, payload)
                return payload
            current_count = count_result.rows
            if current_count != planned_count:
                payload = blocked_closeout(
                    result="BLOCKED_ROW_COUNT_DRIFT",
                    plan=plan,
                    closeout_path=closeout_path,
                    side_effects=side_effects,
                )
                payload["drift"] = {
                    "trade_date": trade_date,
                    "layer": spec.layer,
                    "table": spec.table,
                    "planned_delete_rows": planned_count,
                    "current_rows": current_count,
                }
                write_json(closeout_path, payload)
                return payload
            if planned_count:
                specs_to_delete.append((trade_date, spec, planned_count))

    try:
        delete_result = delete_planned_rows(
            dsn=dsn,
            specs_to_delete=specs_to_delete,
            connection_factory=connection_factory,
            table_deleter=table_deleter,
            max_delete_units=max_delete_units,
        )
    except RuntimeHotDeleteError as exc:
        payload = blocked_closeout(
            result="BLOCKED_DELETE_TIMEOUT" if is_count_timeout_exception(exc.original_exception) else "BLOCKED_DELETE_FAILED",
            plan=plan,
            closeout_path=closeout_path,
            side_effects=side_effects,
        )
        payload["delete_blocker"] = exc.blocker()
        write_json(closeout_path, payload)
        return payload

    deleted_rows = delete_result.deleted_rows
    cleanup_complete = delete_result.delete_units_remaining == 0
    side_effects["writes_database"] = bool(deleted_rows)
    payload = {
        "result": (
            "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS"
            if cleanup_complete
            else "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PARTIAL_PASS"
        ),
        "component": "Runtime Dirty Hot Keep2 Cleanup",
        "mode": "execute",
        "layer_role": "runtime_control",
        "created_at": datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat(),
        "plan_path": str(plan_path),
        "closeout_path": str(closeout_path),
        "retention_trade_days": retention,
        "retained_trade_dates": planned_retained,
        "cleanup_trade_dates": cleanup_dates,
        "cleanup_executed": True,
        "cleanup_complete": cleanup_complete,
        "direct_delete_no_archive": bool(plan.get("direct_delete_no_archive")),
        "row_count_plan_skipped": bool(plan.get("row_count_plan_skipped")),
        "resume_required": not cleanup_complete,
        "delete_units_limit": delete_result.delete_units_limit,
        "delete_units_total": delete_result.delete_units_total,
        "delete_units_executed": delete_result.delete_units_executed,
        "delete_units_remaining": delete_result.delete_units_remaining,
        "deleted_rows": deleted_rows,
        "deleted_total_rows": sum(int(row["deleted_rows"]) for row in deleted_rows),
        "blockers": [],
        "side_effects": side_effects,
    }
    write_json(closeout_path, payload)
    return payload


def build_hot_cleanup_specs(*, direct_event_infra: bool = False) -> tuple[RuntimeHotCleanupSpec, ...]:
    specs: list[RuntimeHotCleanupSpec] = []
    for layer, source_layer in reversed(tuple(SOURCE_LAYER_BY_RUNTIME_LAYER.items())):
        specs.extend(event_infra_cleanup_specs(layer, source_layer, direct_by_trade_date=direct_event_infra))
    specs.extend(n6_cleanup_specs())
    specs.extend(trigger_replay_audit_cleanup_specs())
    specs.extend(eod_reconciliation_item_cleanup_specs())
    for layer, table, date_column in reversed(runtime_table_specs()):
        subscription_column = SUBSCRIPTION_ID_CHILD_TABLES.get((layer, table))
        if direct_event_infra and subscription_column:
            specs.append(
                RuntimeHotCleanupSpec(
                    layer=layer,
                    table=table,
                    count_sql=(
                        f"select count(*) from {table} where {subscription_column} in ("
                        "select subscription_id from common_market_data_subscription "
                        "where run_id in ("
                        "select run_id from common_market_data_run where for_trade_date = %s"
                        "))"
                    ),
                    delete_sql=f"delete from {table} where {subscription_column} = any(%s)",
                    params=(),
                    batch_column=subscription_column,
                    batch_strategy="subscription_id_chunks_direct_delete",
                    batch_source_sql=(
                        "select subscription_id from common_market_data_subscription "
                        "where run_id in ("
                        "select run_id from common_market_data_run where for_trade_date = %s"
                        ") "
                        "order by subscription_id"
                    ),
                )
            )
        if (layer, table) in MARKET_DATA_RUN_ID_BATCH_TABLES:
            specs.append(
                RuntimeHotCleanupSpec(
                    layer=layer,
                    table=table,
                    count_sql=f"select count(*) from {table} where run_id = %s",
                    delete_sql=f"delete from {table} where run_id = %s",
                    params=(),
                    batch_column="run_id",
                    batch_strategy="market_data_run_id",
                    batch_source_sql=(
                        "select run_id from common_market_data_run "
                        "where for_trade_date = %s "
                        "order by run_id"
                    ),
                )
            )
            continue
        if (layer, table) in TRIGGER_RUN_ID_BATCH_TABLES:
            specs.append(
                RuntimeHotCleanupSpec(
                    layer=layer,
                    table=table,
                    count_sql=f"select count(*) from {table} where run_id = %s",
                    delete_sql=f"delete from {table} where run_id = %s",
                    params=(),
                    batch_column="run_id",
                    batch_strategy="trigger_run_id",
                    batch_source_sql=(
                        "select run_id from common_trigger_run "
                        "where for_trade_date = %s "
                        "order by run_id"
                    ),
                )
            )
            continue
        if (layer, table) in TRIGGER_STATE_ID_CHUNK_TABLES:
            specs.append(
                RuntimeHotCleanupSpec(
                    layer=layer,
                    table=table,
                    count_sql=(
                        f"select count(*) from {table} "
                        "where run_id = %s and trigger_state_id >= %s and trigger_state_id <= %s"
                    ),
                    delete_sql=(
                        f"delete from {table} "
                        "where run_id = %s and trigger_state_id >= %s and trigger_state_id <= %s"
                    ),
                    params=(),
                    batch_column="trigger_state_id",
                    batch_strategy="trigger_state_id_chunks",
                    batch_source_sql=(
                        "select s.run_id, s.trigger_state_id from common_trigger_state s "
                        "where s.run_id in ("
                        "select run_id from common_trigger_run where for_trade_date = %s"
                        ") "
                        "order by s.run_id, s.trigger_state_id"
                    ),
                )
            )
            continue
        if direct_event_infra and (layer, table) in ACTION_FACT_ID_BATCH_TABLES:
            specs.append(
                RuntimeHotCleanupSpec(
                    layer=layer,
                    table=table,
                    count_sql=f"select count(*) from {table} where {date_column} = %s",
                    delete_sql=f"delete from {table} where action_fact_id = any(%s)",
                    params=(),
                    batch_column="action_fact_id",
                    batch_strategy="action_fact_id_chunks_direct_delete",
                    batch_source_sql=(
                        f"select action_fact_id from {table} "
                        f"where {date_column} = %s "
                        "order by action_fact_id"
                    ),
                )
            )
            continue
        batch_column, batch_strategy = LARGE_TABLE_BATCH_CONFIG.get((layer, table), (None, None))
        batches = cleanup_batches(batch_strategy)
        specs.append(
            RuntimeHotCleanupSpec(
                layer=layer,
                table=table,
                count_sql=f"select count(*) from {table} where {date_column} = %s",
                delete_sql=f"delete from {table} where {date_column} = %s",
                params=(),
                batch_column=batch_column,
                batch_strategy=batch_strategy,
                batches=batches,
            )
        )
    return tuple(specs)


def eod_reconciliation_item_cleanup_specs() -> tuple[RuntimeHotCleanupSpec, ...]:
    return tuple(
        RuntimeHotCleanupSpec(
            layer="n3",
            table=child_table,
            count_sql=(
                f"select count(*) from {child_table} child "
                f"join {parent_table} parent on parent.eod_snapshot_id = child.eod_snapshot_id "
                "where parent.trade_date = %s"
            ),
            delete_sql=(
                f"delete from {child_table} child "
                f"using {parent_table} parent "
                "where parent.eod_snapshot_id = child.eod_snapshot_id "
                "and parent.trade_date = %s"
            ),
            params=(),
        )
        for child_table, parent_table in EOD_RECONCILIATION_ITEM_TABLES
    )


def trigger_replay_audit_cleanup_specs() -> tuple[RuntimeHotCleanupSpec, ...]:
    return tuple(
        RuntimeHotCleanupSpec(
            layer="n4",
            table=table,
            count_sql=f"select count(*) from {table} where for_trade_date = %s or trade_date = %s",
            delete_sql=f"delete from {table} where for_trade_date = %s or trade_date = %s",
            params=(),
        )
        for table in TRIGGER_REPLAY_AUDIT_TABLES
    )


def event_infra_cleanup_specs(
    layer: str,
    source_layer: str,
    *,
    direct_by_trade_date: bool = False,
) -> tuple[RuntimeHotCleanupSpec, ...]:
    if direct_by_trade_date:
        return (
            RuntimeHotCleanupSpec(
                layer=layer,
                table="common_event_delivery_attempt",
                count_sql=(
                    "select count(*) from common_event_delivery_attempt d "
                    "where exists (select 1 from common_event_outbox o "
                    "where o.event_id = d.event_id and o.trade_date = %s and o.source_layer = %s)"
                ),
                delete_sql=(
                    "delete from common_event_delivery_attempt d "
                    "where exists (select 1 from common_event_outbox o "
                    "where o.event_id = d.event_id and o.trade_date = %s and o.source_layer = %s)"
                ),
                params=(source_layer,),
            ),
            RuntimeHotCleanupSpec(
                layer=layer,
                table="common_event_inbox",
                count_sql=(
                    "select count(*) from common_event_inbox i "
                    "where exists (select 1 from common_event_outbox o "
                    "where o.event_id = i.event_id and o.trade_date = %s and o.source_layer = %s) "
                    "and i.source_layer = %s"
                ),
                delete_sql=(
                    "delete from common_event_inbox where source_layer = %s and event_id = any(%s)"
                ),
                params=(source_layer, source_layer),
                batch_column="event_id",
                batch_strategy="event_id_chunks_direct_delete",
                batch_source_sql=(
                    "select event_id from common_event_outbox "
                    "where trade_date = %s and source_layer = %s "
                    "order by event_id"
                ),
            ),
            RuntimeHotCleanupSpec(
                layer=layer,
                table="common_event_consumer_checkpoint",
                count_sql=(
                    "select count(*) from common_event_consumer_checkpoint "
                    "where source_layer = %s and last_event_time::date = to_date(%s, 'YYYYMMDD')"
                ),
                delete_sql=(
                    "delete from common_event_consumer_checkpoint "
                    "where source_layer = %s and last_event_time::date = to_date(%s, 'YYYYMMDD')"
                ),
                params=(source_layer,),
            ),
            RuntimeHotCleanupSpec(
                layer=layer,
                table="common_event_ledger",
                count_sql="select count(*) from common_event_ledger where trade_date = %s and source_layer = %s",
                delete_sql="delete from common_event_ledger where trade_date = %s and source_layer = %s",
                params=(source_layer,),
            ),
            RuntimeHotCleanupSpec(
                layer=layer,
                table="common_event_outbox",
                count_sql="select count(*) from common_event_outbox where trade_date = %s and source_layer = %s",
                delete_sql="delete from common_event_outbox where source_layer = %s and event_id = any(%s)",
                params=(source_layer,),
                batch_column="event_id",
                batch_strategy="event_id_chunks_direct_delete",
                batch_source_sql=(
                    "select event_id from common_event_outbox "
                    "where trade_date = %s and source_layer = %s "
                    "order by event_id"
                ),
            ),
        )
    return (
        RuntimeHotCleanupSpec(
            layer=layer,
            table="common_event_delivery_attempt",
            count_sql=(
                "select count(*) from common_event_delivery_attempt d "
                "where exists (select 1 from common_event_outbox o "
                "where o.event_id = d.event_id and o.trade_date = %s and o.source_layer = %s)"
            ),
            delete_sql=(
                "delete from common_event_delivery_attempt d "
                "where exists (select 1 from common_event_outbox o "
                "where o.event_id = d.event_id and o.trade_date = %s and o.source_layer = %s)"
            ),
            params=(source_layer,),
        ),
        RuntimeHotCleanupSpec(
            layer=layer,
            table="common_event_inbox",
            count_sql="select count(*) from common_event_inbox where source_layer = %s and event_id = any(%s)",
            delete_sql="delete from common_event_inbox where source_layer = %s and event_id = any(%s)",
            params=(source_layer,),
            batch_column="event_id",
            batch_strategy="event_id_chunks",
            batch_source_sql=(
                "select event_id from common_event_outbox "
                "where trade_date = %s and source_layer = %s "
                "order by event_id"
            ),
        ),
        RuntimeHotCleanupSpec(
            layer=layer,
            table="common_event_consumer_checkpoint",
            count_sql=(
                "select count(*) from common_event_consumer_checkpoint "
                "where source_layer = %s and last_event_time::date = to_date(%s, 'YYYYMMDD')"
            ),
            delete_sql=(
                "delete from common_event_consumer_checkpoint "
                "where source_layer = %s and last_event_time::date = to_date(%s, 'YYYYMMDD')"
            ),
            params=(source_layer,),
        ),
        RuntimeHotCleanupSpec(
            layer=layer,
            table="common_event_ledger",
            count_sql="select count(*) from common_event_ledger where trade_date = %s and source_layer = %s",
            delete_sql="delete from common_event_ledger where trade_date = %s and source_layer = %s",
            params=(source_layer,),
        ),
        RuntimeHotCleanupSpec(
            layer=layer,
            table="common_event_outbox",
            count_sql="select count(*) from common_event_outbox where source_layer = %s and event_id = any(%s)",
            delete_sql="delete from common_event_outbox where source_layer = %s and event_id = any(%s)",
            params=(source_layer,),
            batch_column="event_id",
            batch_strategy="event_id_chunks",
            batch_source_sql=(
                "select event_id from common_event_outbox "
                "where trade_date = %s and source_layer = %s "
                "order by event_id"
            ),
        ),
    )


def n6_cleanup_specs() -> tuple[RuntimeHotCleanupSpec, ...]:
    run_filter = "select run_id from common_action_run where for_trade_date = %s"
    projection_filter = (
        "select user_projection_run_id from user_projection_run "
        f"where source_action_run_id in ({run_filter})"
    )
    projection_dependent_specs = tuple(
        RuntimeHotCleanupSpec(
            layer="n6",
            table=table,
            count_sql=f"select count(*) from {table} where user_projection_run_id = %s",
            delete_sql=f"delete from {table} where user_projection_run_id = %s",
            params=(),
            batch_column="user_projection_run_id",
            batch_strategy="user_projection_run_id",
            batch_source_sql=projection_filter,
        )
        for table in N6_USER_PROJECTION_DEPENDENT_TABLES
    )
    return (
        *projection_dependent_specs,
        RuntimeHotCleanupSpec(
            layer="n6",
            table="user_projection_run",
            count_sql=f"select count(*) from user_projection_run where source_action_run_id in ({run_filter})",
            delete_sql=f"delete from user_projection_run where source_action_run_id in ({run_filter})",
            params=(),
        ),
    )


def bind_cleanup_spec(spec: RuntimeHotCleanupSpec, trade_date: str) -> RuntimeHotCleanupSpec:
    normalized = require_yyyymmdd(str(trade_date), "trade_date")
    if spec.table == "common_event_inbox" and spec.batch_strategy == "event_id_chunks_direct_delete":
        params = (normalized, spec.params[0], spec.params[1])
    elif spec.table in {"common_event_inbox", "common_event_outbox"} and spec.batch_strategy in {
        "event_id_chunks",
        "event_id_chunks_direct_delete",
    }:
        params = (normalized, spec.params[0])
    elif spec.batch_strategy in {
        "trigger_run_id",
        "trigger_state_id_chunks",
        "market_data_run_id",
        "subscription_id_chunks_direct_delete",
        "action_fact_id_chunks_direct_delete",
    }:
        params = (normalized,)
    elif spec.table in {"common_event_inbox"}:
        params = (normalized, spec.params[0], spec.params[1])
    elif spec.table in {"common_event_consumer_checkpoint"}:
        params = (spec.params[0], normalized)
    elif spec.table in {"common_event_outbox", "common_event_ledger", "common_event_delivery_attempt"}:
        params = (normalized, spec.params[0])
    elif spec.table in TRIGGER_REPLAY_AUDIT_TABLES:
        params = (normalized, normalized)
    else:
        params = (normalized,)
    return RuntimeHotCleanupSpec(
        spec.layer,
        spec.table,
        spec.count_sql,
        spec.delete_sql,
        params,
        spec.batch_column,
        spec.batch_strategy,
        spec.batches,
        spec.batch_source_sql,
    )


def discover_hot_trade_dates(*, dsn: str, connection_factory: Callable[[str], Any] = psycopg.connect) -> list[str]:
    trade_dates: set[str] = set()
    with connection_factory(dsn) as conn:
        for sql in HOT_TRADE_DATE_DRIVER_QUERIES:
            for row in conn.execute(sql):
                value = str(row[0] or "")
                if len(value) == 8 and value.isdigit():
                    trade_dates.add(value)
    return sorted(trade_dates)


def discover_calendar_retained_trade_dates(
    *,
    current_trade_date: str,
    dsn: str = DEFAULT_DSN,
    connection_factory: Callable[[str], Any] = psycopg.connect,
) -> list[str]:
    """Return current date plus the previous five completed open dates."""

    current = require_yyyymmdd(current_trade_date, "current_trade_date")
    query = (
        "select trade_date::text from common_trade_calendar "
        "where is_open = true and trade_date < %s "
        "order by trade_date desc limit 5"
    )
    with connection_factory(dsn) as conn:
        previous = [require_yyyymmdd(str(row[0]), "completed_trade_date") for row in conn.execute(query, (current,))]
    if len(previous) != 5:
        raise ValueError(f"common_trade_calendar_previous_completed_dates_must_equal_5:{len(previous)}")
    return sorted({current, *previous})


def runtime_hot_cleanup_v2_specs() -> tuple[RuntimeHotCleanupSpec, ...]:
    """Keep existing DB scope except explicitly excluded N3T and N6 facts."""

    return tuple(
        spec
        for spec in build_hot_cleanup_specs()
        if spec.layer != "n6" and "action_confirmation_projection_metric" not in spec.table
    )


def discover_database_trade_dates(
    *,
    dsn: str = DEFAULT_DSN,
    connection_factory: Callable[[str], Any] = psycopg.connect,
) -> list[str]:
    """Discover the actual DB date domain from every in-scope table, not drivers."""

    allowed_tables = {(spec.layer, spec.table) for spec in runtime_hot_cleanup_v2_specs()}
    table_dates = {
        (table, date_column)
        for layer, table, date_column in runtime_table_specs()
        if (layer, table) in allowed_tables
    }
    table_dates.update((table, "trade_date") for table in TRIGGER_REPLAY_AUDIT_TABLES)
    table_dates.update(
        (table, "trade_date")
        for table in ("common_event_outbox", "common_event_ledger")
    )
    discovered: set[str] = set()
    with connection_factory(dsn) as conn:
        for table, date_column in sorted(table_dates):
            query = f"select distinct {date_column}::text from {table} where {date_column} is not null"
            for row in conn.execute(query):
                value = str(row[0] or "")
                if len(value) == 8 and value.isdigit():
                    discovered.add(require_yyyymmdd(value, f"{table}.{date_column}"))
    return sorted(discovered)


def freeze_inbox_delete_units(
    *,
    cleanup_trade_dates: Iterable[str],
    dsn: str = DEFAULT_DSN,
    connection_factory: Callable[[str], Any] = psycopg.connect,
) -> list[dict[str, Any]]:
    """Freeze exact inbox ids in deterministic 50-row units before mutation."""

    units: list[dict[str, Any]] = []
    query = (
        "select i.inbox_id from common_event_inbox i "
        "join common_event_outbox o on o.event_id = i.event_id "
        "where o.trade_date = %s and o.source_layer = %s and i.source_layer = %s "
        "and i.status in ('processed', 'skipped') "
        "order by i.inbox_id"
    )
    with connection_factory(dsn) as conn:
        for trade_date in sorted({require_yyyymmdd(str(item), "cleanup_trade_date") for item in cleanup_trade_dates}):
            for layer, source_layer in reversed(tuple(SOURCE_LAYER_BY_RUNTIME_LAYER.items())):
                inbox_ids = [int(row[0]) for row in conn.execute(query, (trade_date, source_layer, source_layer))]
                for offset in range(0, len(inbox_ids), INBOX_ID_BATCH_SIZE):
                    batch = inbox_ids[offset : offset + INBOX_ID_BATCH_SIZE]
                    units.append(
                        {
                            "unit_id": f"inbox:{trade_date}:{layer}:{offset // INBOX_ID_BATCH_SIZE:05d}",
                            "trade_date": trade_date,
                            "layer": layer,
                            "table": "common_event_inbox",
                            "inbox_ids": batch,
                            "planned_rows": len(batch),
                            "active_rows_excluded": True,
                        }
                    )
    return units


def build_runtime_hot_cleanup_plan_v2(
    *,
    current_trade_date: str,
    local_files: Iterable[dict[str, Any]],
    dsn: str = DEFAULT_DSN,
    connection_factory: Callable[[str], Any] = psycopg.connect,
    retained_trade_dates: Iterable[str] | None = None,
    database_trade_dates: Iterable[str] | None = None,
    inbox_delete_units: Iterable[dict[str, Any]] | None = None,
    table_counter: Callable[[RuntimeHotCleanupSpec, str], int] | None = None,
    local_archive_evidence: dict[str, Any] | None = None,
    database_cleanup_enabled: bool = True,
    direct_delete_no_archive: bool = False,
) -> RuntimeHotCleanupPlan:
    current = require_yyyymmdd(current_trade_date, "current_trade_date")
    retained = sorted(
        {
            require_yyyymmdd(str(item), "retained_trade_date")
            for item in (
                retained_trade_dates
                if retained_trade_dates is not None
                else discover_calendar_retained_trade_dates(
                    current_trade_date=current,
                    dsn=dsn,
                    connection_factory=connection_factory,
                )
            )
        }
    )
    if current not in retained or len(retained) != 6:
        raise ValueError("calendar_retained_set_must_be_current_plus_previous_5")
    database_discovery_blocker = ""
    try:
        db_date_values = (
            []
            if not database_cleanup_enabled
            else database_trade_dates
            if database_trade_dates is not None
            else discover_database_trade_dates(dsn=dsn, connection_factory=connection_factory)
        )
        db_dates = sorted(
            {require_yyyymmdd(str(item), "database_trade_date") for item in db_date_values}
        )
    except Exception as exc:
        db_dates = []
        database_discovery_blocker = f"database_date_discovery_failed:{type(exc).__name__}"
    local_entries = [dict(entry) for entry in local_files]
    local_dates = sorted(
        {require_yyyymmdd(str(entry["trade_date"]), "local_trade_date") for entry in local_entries}
    )
    retained_set = set(retained)
    protected_future_db_dates = sorted(date_value for date_value in db_dates if date_value > current)
    db_cleanup = sorted(
        date_value
        for date_value in db_dates
        if date_value < current and date_value not in retained_set
    )
    local_cleanup = sorted(set(local_dates) - retained_set)
    blockers: list[str] = []
    archive_evidence = dict(local_archive_evidence or {})
    local_archive_verified = (
        local_archive_evidence is not None
        and
        archive_evidence.get("local_policy") == "verified-archive-required"
        and archive_evidence.get("manifest_verified") is True
        and archive_evidence.get("restore_proof_result") == "RESTORE_PROOF_PASS"
        and archive_evidence.get("exact_allowlist_verified") is True
    )
    if direct_delete_no_archive:
        blockers.append("direct-delete-no-archive_rejected")
    if local_archive_evidence is not None and not local_archive_verified:
        blockers.append("verified_archive_contract_incomplete")
    if database_discovery_blocker:
        blockers.append(database_discovery_blocker)
    if inbox_delete_units is not None:
        frozen_inbox = list(inbox_delete_units)
    elif database_discovery_blocker:
        frozen_inbox = []
    else:
        frozen_inbox = freeze_inbox_delete_units(
            cleanup_trade_dates=db_cleanup,
            dsn=dsn,
            connection_factory=connection_factory,
        )
    database_delete_plan: list[dict[str, Any]] = []
    database_plan_failed = False
    for trade_date in db_cleanup:
        for template in runtime_hot_cleanup_v2_specs():
            spec = bind_cleanup_spec(template, trade_date)
            if spec.table == "common_event_inbox":
                planned_rows = sum(
                    int(unit["planned_rows"])
                    for unit in frozen_inbox
                    if unit["trade_date"] == trade_date and unit["layer"] == spec.layer
                )
            else:
                try:
                    planned_rows = count_rows_once_v2(
                        dsn=dsn,
                        spec=spec,
                        connection_factory=connection_factory,
                        table_counter=table_counter,
                    )
                except Exception as exc:
                    blockers.append(
                        f"database_plan_count_failed:{trade_date}:{spec.layer}:{spec.table}:{type(exc).__name__}"
                    )
                    database_plan_failed = True
                    break
            if planned_rows:
                database_delete_plan.append(
                    {
                        "trade_date": trade_date,
                        "layer": spec.layer,
                        "table": spec.table,
                        "planned_rows": int(planned_rows),
                    }
                )
        if database_plan_failed:
            break
    verified_local_entries: list[dict[str, Any]] = []
    for entry in local_entries if local_archive_evidence is not None else []:
        if str(entry.get("trade_date")) not in set(local_cleanup):
            continue
        source_path = str(entry.get("source_path") or "")
        if int(entry.get("retained_date_overlap") or 0):
            blockers.append(f"retained_local_entry_excluded:{source_path}")
            continue
        if int(entry.get("active_current_lineage_overlap") or 0):
            blockers.append(f"active_local_entry_excluded:{source_path}")
            continue
        if entry.get("archive_fully_verified") is not True or entry.get("exact_allowlisted") is not True:
            blockers.append(f"unverified_local_entry_excluded:{source_path}")
            continue
        verified_local_entries.append(entry)
    return RuntimeHotCleanupPlan(
        current_trade_date=current,
        retained_trade_dates=tuple(retained),
        database_trade_dates=tuple(db_dates),
        database_protected_future_trade_dates=tuple(protected_future_db_dates),
        database_cleanup_trade_dates=tuple(db_cleanup),
        local_trade_dates=tuple(local_dates),
        local_cleanup_trade_dates=tuple(local_cleanup),
        database_delete_plan=tuple(database_delete_plan),
        inbox_delete_units=tuple(dict(unit) for unit in frozen_inbox),
        local_allowlist=tuple(verified_local_entries),
        blockers=tuple(sorted(set(blockers))),
        local_archive_verified=local_archive_verified,
        database_discovery_blocker=database_discovery_blocker,
        database_cleanup_enabled=database_cleanup_enabled,
        direct_delete_no_archive=direct_delete_no_archive,
    )


def append_durable_progress_journal(path: str | Path, entry: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False, sort_keys=True, default=str) + "\n"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def execute_frozen_inbox_units(
    *,
    units: Iterable[dict[str, Any]],
    progress_journal_path: str | Path,
    dsn: str = DEFAULT_DSN,
    connection_factory: Callable[[str], Any] = psycopg.connect,
) -> dict[str, Any]:
    """Commit each frozen inbox-id unit independently; stop once, never retry."""

    committed: list[dict[str, Any]] = []
    committed_inbox_ids: list[int] = []
    seen_inbox_ids: set[int] = set()
    attempted = 0
    for unit in units:
        attempted += 1
        started = perf_counter()
        inbox_ids = [int(value) for value in list(unit.get("inbox_ids") or [])]
        if (
            unit.get("table") != "common_event_inbox"
            or unit.get("layer") not in {"n3", "n4", "n5"}
            or not inbox_ids
            or len(inbox_ids) > INBOX_ID_BATCH_SIZE
            or any(value <= 0 or value in seen_inbox_ids for value in inbox_ids)
        ):
            return {
                "result": "BLOCKED_INVALID_FROZEN_INBOX_UNIT",
                "cleanup_complete": False,
                "retry_attempts": 0,
                "attempted_units": attempted,
                "committed_units": committed,
                "committed_unit_count": len(committed),
                "committed_inbox_ids": committed_inbox_ids,
                "failed_unit": dict(unit),
                "rollback_claimed": False,
            }
        seen_inbox_ids.update(inbox_ids)
        try:
            with connection_factory(dsn) as conn:
                with conn.transaction():
                    conn.execute(f"set local lock_timeout = '{DELETE_LOCK_TIMEOUT_MS}ms'")
                    conn.execute(f"set local statement_timeout = '{DELETE_STATEMENT_TIMEOUT_MS}ms'")
                    cursor = conn.execute(
                        "delete from common_event_inbox where inbox_id = any(%s)",
                        (inbox_ids,),
                    )
                    deleted = int(cursor.rowcount or 0)
                    if deleted != int(unit["planned_rows"]):
                        raise RuntimeError(
                            f"frozen_inbox_id_count_drift:{unit['unit_id']}:{unit['planned_rows']}:{deleted}"
                        )
            journal_entry = {
                "schema": "RuntimeHotCleanupProgressJournal.v1",
                "unit_id": str(unit["unit_id"]),
                "status": "committed",
                "deleted_rows": deleted,
                "inbox_ids": inbox_ids,
                "committed_at": datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat(),
            }
            append_durable_progress_journal(progress_journal_path, journal_entry)
            committed.append(journal_entry)
            committed_inbox_ids.extend(inbox_ids)
        except Exception as exc:
            return {
                "result": "BLOCKED_DATABASE_DELETE_TIMEOUT" if is_count_timeout_exception(exc) else "BLOCKED_DATABASE_DELETE_FAILED",
                "cleanup_complete": False,
                "retry_attempts": 0,
                "attempted_units": attempted,
                "committed_units": committed,
                "committed_unit_count": len(committed),
                "committed_inbox_ids": committed_inbox_ids,
                "failed_unit": dict(unit),
                "error": f"{type(exc).__name__}: {exc}",
                "duration_ms": elapsed_ms(started),
                "rollback_claimed": False,
            }
    return {
        "result": "DATABASE_INBOX_MICROTRANSACTIONS_PASS",
        "cleanup_complete": True,
        "retry_attempts": 0,
        "attempted_units": attempted,
        "committed_units": committed,
        "committed_unit_count": len(committed),
        "committed_inbox_ids": committed_inbox_ids,
        "rollback_claimed": False,
    }


def execute_runtime_hot_cleanup_database_v2(
    *,
    plan: RuntimeHotCleanupPlan,
    progress_journal_path: str | Path,
    dsn: str = DEFAULT_DSN,
    connection_factory: Callable[[str], Any] = psycopg.connect,
    table_counter: Callable[[RuntimeHotCleanupSpec, str], int] | None = None,
    table_deleter: Callable[[RuntimeHotCleanupSpec, str], int] | None = None,
) -> dict[str, Any]:
    """Execute v2 DB units with one transaction and durable journal per unit."""

    expected = {
        (str(row["trade_date"]), str(row["layer"]), str(row["table"])): int(row["planned_rows"])
        for row in plan.database_delete_plan
    }
    committed: list[dict[str, Any]] = []
    attempted = 0

    def stop(unit: dict[str, Any], exc: Exception) -> dict[str, Any]:
        return {
            "result": "BLOCKED_DATABASE_DELETE_TIMEOUT" if is_count_timeout_exception(exc) else "BLOCKED_DATABASE_DELETE_FAILED",
            "cleanup_complete": False,
            "retry_attempts": 0,
            "attempted_units": attempted,
            "committed_units": committed,
            "committed_unit_count": len(committed),
            "failed_unit": unit,
            "error": f"{type(exc).__name__}: {exc}",
            "rollback_claimed": False,
        }

    for template in runtime_hot_cleanup_v2_specs():
        for trade_date in plan.database_cleanup_trade_dates:
            key = (trade_date, template.layer, template.table)
            if key not in expected:
                continue
            spec = bind_cleanup_spec(template, trade_date)
            if spec.table == "common_event_inbox":
                result = execute_frozen_inbox_units(
                    units=(
                        unit for unit in plan.inbox_delete_units
                        if unit["trade_date"] == trade_date and unit["layer"] == spec.layer
                    ),
                    progress_journal_path=progress_journal_path,
                    dsn=dsn,
                    connection_factory=connection_factory,
                )
                attempted += int(result["attempted_units"])
                committed.extend(result["committed_units"])
                if not result["cleanup_complete"]:
                    result["attempted_units"] = attempted
                    result["committed_units"] = committed
                    result["committed_unit_count"] = len(committed)
                    return result
                continue
            try:
                current_rows = count_rows_once_v2(
                    dsn=dsn, spec=spec, connection_factory=connection_factory, table_counter=table_counter
                )
                if current_rows != expected[key]:
                    raise RuntimeError(
                        f"row_count_drift:{trade_date}:{spec.layer}:{spec.table}:{expected[key]}:{current_rows}"
                    )
                if table_deleter is not None:
                    unit_specs = (spec,)
                elif is_batched_parent_spec(spec):
                    with connection_factory(dsn) as discovery_conn:
                        unit_specs = tuple(iter_delete_batch_specs(conn=discovery_conn, spec=spec))
                else:
                    unit_specs = (spec,)
                for index, unit_spec in enumerate(unit_specs):
                    attempted += 1
                    unit = {
                        "unit_id": f"{trade_date}:{spec.layer}:{spec.table}:{index:05d}",
                        "trade_date": trade_date,
                        "layer": spec.layer,
                        "table": spec.table,
                    }
                    if table_deleter is not None:
                        deleted = int(table_deleter(unit_spec, trade_date))
                    else:
                        with connection_factory(dsn) as conn:
                            with conn.transaction():
                                conn.execute(f"set local lock_timeout = '{DELETE_LOCK_TIMEOUT_MS}ms'")
                                conn.execute(f"set local statement_timeout = '{DELETE_STATEMENT_TIMEOUT_MS}ms'")
                                deleted = int(conn.execute(unit_spec.delete_sql, unit_spec.params).rowcount or 0)
                    journal_entry = {
                        "schema": "RuntimeHotCleanupProgressJournal.v1",
                        **unit,
                        "status": "committed",
                        "deleted_rows": deleted,
                        "committed_at": datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat(),
                    }
                    append_durable_progress_journal(progress_journal_path, journal_entry)
                    committed.append(journal_entry)
            except Exception as exc:
                return stop(
                    {
                        "trade_date": trade_date,
                        "layer": spec.layer,
                        "table": spec.table,
                    },
                    exc,
                )
    return {
        "result": "DATABASE_RUNTIME_HOT_CLEANUP_V2_PASS",
        "cleanup_complete": True,
        "retry_attempts": 0,
        "attempted_units": attempted,
        "committed_units": committed,
        "committed_unit_count": len(committed),
        "rollback_claimed": False,
    }


def count_rows_once_v2(
    *,
    dsn: str,
    spec: RuntimeHotCleanupSpec,
    connection_factory: Callable[[str], Any],
    table_counter: Callable[[RuntimeHotCleanupSpec, str], int] | None,
) -> int:
    """Single-attempt count used by v2; timeout/error is terminal."""

    trade_date = extract_trade_date(spec)
    if table_counter is not None:
        return int(table_counter(spec, trade_date))
    if is_batched_parent_spec(spec) and spec.batch_strategy not in DIRECT_COUNT_BATCH_SKIP_STRATEGIES:
        batch_specs = iter_count_batch_specs(dsn=dsn, spec=spec, connection_factory=connection_factory)
        return sum(
            count_rows_once_v2(
                dsn=dsn,
                spec=batch_spec,
                connection_factory=connection_factory,
                table_counter=None,
            )
            for batch_spec in batch_specs
        )
    with connection_factory(dsn) as conn:
        with conn.transaction():
            conn.execute("set local transaction read only")
            conn.execute(f"set local lock_timeout = '{DELETE_LOCK_TIMEOUT_MS}ms'")
            conn.execute(f"set local statement_timeout = '{COUNT_STATEMENT_TIMEOUT_MS}ms'")
            row = conn.execute(spec.count_sql, spec.params).fetchone()
    return int(row[0] if row else 0)


def verified_archive_manifest_evidence(
    *,
    cleanup_dates: Iterable[str],
    archive_root: str | Path = DEFAULT_RUNTIME_ARCHIVE_ROOT,
) -> tuple[dict[str, Any], list[str]]:
    evidence: dict[str, Any] = {}
    blockers: list[str] = []
    for trade_date in cleanup_dates:
        normalized = require_yyyymmdd(str(trade_date), "trade_date")
        manifest_path = Path(
            make_runtime_archive_manifest_path(
                archive_root=str(archive_root),
                trade_date=normalized,
            )
        )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            blockers.append(f"archive_manifest_not_verified:{normalized}")
            evidence[normalized] = {"manifest_path": str(manifest_path), "result": "MISSING_OR_INVALID"}
            continue
        verified = (
            manifest.get("result") == "ARCHIVED_VERIFIED"
            and manifest.get("row_count_match") is True
            and manifest.get("checksum_algorithm") == "sha256"
            and manifest.get("cleanup_eligible") is False
        )
        evidence[normalized] = {
            "manifest_path": str(manifest_path),
            "result": str(manifest.get("result") or ""),
            "row_count_match": bool(manifest.get("row_count_match")),
            "checksum_algorithm": str(manifest.get("checksum_algorithm") or ""),
            "cleanup_eligible": bool(manifest.get("cleanup_eligible")),
            "file_count": int(manifest.get("file_count") or 0),
            "total_rows": int(manifest.get("total_rows") or 0),
        }
        if not verified:
            blockers.append(f"archive_manifest_not_verified:{normalized}")
    return evidence, blockers


def count_rows(
    *,
    dsn: str,
    spec: RuntimeHotCleanupSpec,
    connection_factory: Callable[[str], Any],
    table_counter: Callable[[RuntimeHotCleanupSpec, str], int] | None,
) -> int:
    trade_date = extract_trade_date(spec)
    if table_counter is not None:
        return int(table_counter(spec, trade_date))
    if is_batched_parent_spec(spec) and spec.batch_strategy not in DIRECT_COUNT_BATCH_SKIP_STRATEGIES:
        return sum(
            count_rows(
                dsn=dsn,
                spec=batch_spec,
                connection_factory=connection_factory,
                table_counter=None,
            )
            for batch_spec in iter_count_batch_specs(dsn=dsn, spec=spec, connection_factory=connection_factory)
        )
    for attempt in range(COUNT_TIMEOUT_RETRIES + 1):
        try:
            with connection_factory(dsn) as conn:
                with conn.transaction():
                    conn.execute("set local transaction read only")
                    conn.execute(f"set local statement_timeout = '{COUNT_STATEMENT_TIMEOUT_MS}ms'")
                    row = conn.execute(spec.count_sql, spec.params).fetchone()
            return int(row[0] if row else 0)
        except Exception as exc:
            if attempt < COUNT_TIMEOUT_RETRIES and is_count_timeout_exception(exc):
                continue
            raise
    raise RuntimeError("unreachable count_rows retry state")


def is_count_timeout_exception(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    return "timeout" in text or "querycanceled" in name or "query canceled" in text


def count_rows_with_timing(
    *,
    dsn: str,
    spec: RuntimeHotCleanupSpec,
    connection_factory: Callable[[str], Any],
    table_counter: Callable[[RuntimeHotCleanupSpec, str], int] | None,
) -> RuntimeHotCountResult:
    started = perf_counter()
    trade_date = extract_trade_date(spec)
    timing = {
        "trade_date": trade_date,
        "layer": spec.layer,
        "table": spec.table,
        "status": "started",
        "duration_ms": 0.0,
        "row_count": 0,
    }
    if (
        table_counter is None
        and is_batched_parent_spec(spec)
        and spec.batch_strategy not in DIRECT_COUNT_BATCH_SKIP_STRATEGIES
    ):
        rows = 0
        batch_timings: list[dict[str, Any]] = []
        try:
            batch_specs = iter_count_batch_specs(dsn=dsn, spec=spec, connection_factory=connection_factory)
        except Exception as exc:
            duration_ms = elapsed_ms(started)
            timing.update(
                {
                    "status": "blocked",
                    "duration_ms": duration_ms,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            blocker = {
                "trade_date": trade_date,
                "layer": spec.layer,
                "table": spec.table,
                "batch_label": "batch_source",
                "duration_ms": duration_ms,
                "error": f"{type(exc).__name__}: {exc}",
            }
            return RuntimeHotCountResult(0, timing, blocker)
        for batch_spec in batch_specs:
            batch_started = perf_counter()
            batch = batch_spec.batches[0]
            batch_start, batch_end = batch_timing_bounds(batch_spec)
            batch_timing = {
                "trade_date": trade_date,
                "layer": spec.layer,
                "table": spec.table,
                "batch_label": batch.label,
                "batch_start": batch_start,
                "batch_end": batch_end,
                "status": "started",
                "duration_ms": 0.0,
                "row_count": 0,
            }
            try:
                batch_rows = count_rows(
                    dsn=dsn,
                    spec=batch_spec,
                    connection_factory=connection_factory,
                    table_counter=None,
                )
            except Exception as exc:
                duration_ms = elapsed_ms(batch_started)
                batch_timing.update(
                    {
                        "status": "blocked",
                        "duration_ms": duration_ms,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                batch_timings.append(batch_timing)
                blocker = {
                    "trade_date": trade_date,
                    "layer": spec.layer,
                    "table": spec.table,
                    "batch_label": batch.label,
                    "batch_start": batch_start,
                    "batch_end": batch_end,
                    "duration_ms": duration_ms,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                timing.update(
                    {
                        "status": "blocked",
                        "duration_ms": elapsed_ms(started),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                return RuntimeHotCountResult(0, timing, blocker, tuple(batch_timings))
            rows += batch_rows
            batch_timing.update(
                {
                    "status": "ok",
                    "duration_ms": elapsed_ms(batch_started),
                    "row_count": batch_rows,
                }
            )
            batch_timings.append(batch_timing)
        timing.update(
            {
                "status": "ok",
                "duration_ms": elapsed_ms(started),
                "row_count": rows,
            }
        )
        return RuntimeHotCountResult(rows, timing, None, tuple(batch_timings))
    try:
        rows = count_rows(
            dsn=dsn,
            spec=spec,
            connection_factory=connection_factory,
            table_counter=table_counter,
        )
    except Exception as exc:
        duration_ms = elapsed_ms(started)
        timing.update(
            {
                "status": "blocked",
                "duration_ms": duration_ms,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        blocker = {
            "trade_date": trade_date,
            "layer": spec.layer,
            "table": spec.table,
            "duration_ms": duration_ms,
            "error": f"{type(exc).__name__}: {exc}",
        }
        return RuntimeHotCountResult(0, timing, blocker)
    timing.update(
        {
            "status": "ok",
            "duration_ms": elapsed_ms(started),
            "row_count": rows,
        }
    )
    return RuntimeHotCountResult(rows, timing, None, (timing,))


def delete_planned_rows(
    *,
    dsn: str,
    specs_to_delete: list[tuple[str, RuntimeHotCleanupSpec, int]],
    connection_factory: Callable[[str], Any],
    table_deleter: Callable[[RuntimeHotCleanupSpec, str], int] | None,
    max_delete_units: int | None = None,
) -> RuntimeHotDeleteResult:
    deleted_rows: list[dict[str, Any]] = []
    limit = int(max_delete_units) if max_delete_units and int(max_delete_units) > 0 else None
    delete_units_total = 0
    delete_units_executed = 0
    if table_deleter is not None:
        for trade_date, spec, _planned_count in specs_to_delete:
            delete_units_total += 1
            if limit is not None and delete_units_executed >= limit:
                continue
            deleted_rows.append(
                {
                    "trade_date": trade_date,
                    "layer": spec.layer,
                    "table": spec.table,
                    "deleted_rows": int(table_deleter(spec, trade_date)),
                }
            )
            delete_units_executed += 1
        return RuntimeHotDeleteResult(deleted_rows, delete_units_total, delete_units_executed, limit)
    with connection_factory(dsn) as conn:
        with conn.transaction():
            conn.execute(f"set local statement_timeout = '{DELETE_STATEMENT_TIMEOUT_MS}ms'")
            for trade_date, spec, _planned_count in specs_to_delete:
                unit_specs = iter_delete_batch_specs(conn=conn, spec=spec) if is_batched_parent_spec(spec) else (spec,)
                for unit_spec in unit_specs:
                    delete_units_total += 1
                    if limit is not None and delete_units_executed >= limit:
                        continue
                    if is_batched_parent_spec(spec):
                        batch_spec = unit_spec
                        batch = batch_spec.batches[0]
                        batch_start, batch_end = batch_timing_bounds(batch_spec)
                        started = perf_counter()
                        try:
                            cursor = conn.execute(batch_spec.delete_sql, batch_spec.params)
                        except Exception as exc:
                            raise RuntimeHotDeleteError(
                                trade_date=trade_date,
                                spec=batch_spec,
                                exc=exc,
                                duration_ms=elapsed_ms(started),
                            ) from exc
                        deleted_rows.append(
                            {
                                "trade_date": trade_date,
                                "layer": spec.layer,
                                "table": spec.table,
                                "batch_label": batch.label,
                                "batch_start": batch_start,
                                "batch_end": batch_end,
                                "deleted_rows": int(cursor.rowcount or 0),
                            }
                        )
                    else:
                        started = perf_counter()
                        try:
                            cursor = conn.execute(unit_spec.delete_sql, unit_spec.params)
                        except Exception as exc:
                            raise RuntimeHotDeleteError(
                                trade_date=trade_date,
                                spec=unit_spec,
                                exc=exc,
                                duration_ms=elapsed_ms(started),
                            ) from exc
                        deleted_rows.append(
                            {
                                "trade_date": trade_date,
                                "layer": unit_spec.layer,
                                "table": unit_spec.table,
                                "deleted_rows": int(cursor.rowcount or 0),
                            }
                        )
                    delete_units_executed += 1
    return RuntimeHotDeleteResult(deleted_rows, delete_units_total, delete_units_executed, limit)


def extract_trade_date(spec: RuntimeHotCleanupSpec) -> str:
    for item in spec.params:
        text = str(item)
        if len(text) == 8 and text.isdigit():
            return text
    return ""


def normalize_retention_trade_days(value: int) -> int:
    return max(1, min(int(value or DEFAULT_RETENTION_TRADE_DAYS), 30))


def intraday_batches() -> tuple[RuntimeHotCleanupBatch, ...]:
    return tuple(RuntimeHotCleanupBatch(*item) for item in INTRADAY_TIME_WINDOWS)


def intraday_fine_batches() -> tuple[RuntimeHotCleanupBatch, ...]:
    return tuple(RuntimeHotCleanupBatch(*item) for item in INTRADAY_TIME_WINDOWS_FINE)


def intraday_stock_15m_batches() -> tuple[RuntimeHotCleanupBatch, ...]:
    return tuple(RuntimeHotCleanupBatch(*item) for item in INTRADAY_TIME_WINDOWS_STOCK_15M)


def intraday_stock_5m_batches() -> tuple[RuntimeHotCleanupBatch, ...]:
    return tuple(RuntimeHotCleanupBatch(*item) for item in INTRADAY_TIME_WINDOWS_STOCK_5M)


def intraday_stock_1m_batches() -> tuple[RuntimeHotCleanupBatch, ...]:
    return tuple(RuntimeHotCleanupBatch(*item) for item in INTRADAY_TIME_WINDOWS_STOCK_1M)


def intraday_label_batches() -> tuple[RuntimeHotCleanupBatch, ...]:
    return tuple(RuntimeHotCleanupBatch(*item) for item in INTRADAY_LABEL_WINDOWS)


def intraday_label_5m_batches() -> tuple[RuntimeHotCleanupBatch, ...]:
    return tuple(RuntimeHotCleanupBatch(*item) for item in INTRADAY_LABEL_WINDOWS_5M)


def cleanup_batches(batch_strategy: str | None) -> tuple[RuntimeHotCleanupBatch, ...]:
    if batch_strategy == "intraday_time_windows":
        return intraday_batches()
    if batch_strategy == "intraday_time_windows_fine":
        return intraday_fine_batches()
    if batch_strategy == "intraday_time_windows_stock_15m":
        return intraday_stock_15m_batches()
    if batch_strategy == "intraday_time_windows_stock_5m":
        return intraday_stock_5m_batches()
    if batch_strategy == "intraday_time_windows_stock_1m":
        return intraday_stock_1m_batches()
    if batch_strategy == "intraday_label_windows":
        return intraday_label_batches()
    if batch_strategy == "intraday_label_windows_5m":
        return intraday_label_5m_batches()
    return ()


def iter_count_batch_specs(
    *,
    dsn: str,
    spec: RuntimeHotCleanupSpec,
    connection_factory: Callable[[str], Any],
) -> tuple[RuntimeHotCleanupSpec, ...]:
    if spec.batch_strategy == "user_projection_run_id":
        return fetch_count_batch_specs_with_retry(
            dsn=dsn,
            spec=spec,
            connection_factory=connection_factory,
            fetcher=fetch_user_projection_run_ids,
            builder=user_projection_run_id_batch_specs,
        )
    if spec.batch_strategy == "event_id_chunks":
        return fetch_count_batch_specs_with_retry(
            dsn=dsn,
            spec=spec,
            connection_factory=connection_factory,
            fetcher=fetch_event_ids,
            builder=event_id_chunk_batch_specs,
        )
    if spec.batch_strategy == "trigger_run_id":
        return fetch_count_batch_specs_with_retry(
            dsn=dsn,
            spec=spec,
            connection_factory=connection_factory,
            fetcher=fetch_trigger_run_ids,
            builder=trigger_run_id_batch_specs,
        )
    if spec.batch_strategy == "trigger_state_id_chunks":
        return fetch_count_batch_specs_with_retry(
            dsn=dsn,
            spec=spec,
            connection_factory=connection_factory,
            fetcher=fetch_trigger_state_id_rows,
            builder=trigger_state_id_chunk_batch_specs,
        )
    if spec.batch_strategy == "market_data_run_id":
        return fetch_count_batch_specs_with_retry(
            dsn=dsn,
            spec=spec,
            connection_factory=connection_factory,
            fetcher=fetch_market_data_run_ids,
            builder=market_data_run_id_batch_specs,
        )
    if spec.batch_strategy == "subscription_id_chunks_direct_delete":
        return fetch_count_batch_specs_with_retry(
            dsn=dsn,
            spec=spec,
            connection_factory=connection_factory,
            fetcher=fetch_subscription_ids,
            builder=subscription_id_chunk_batch_specs,
        )
    if spec.batch_strategy == "action_fact_id_chunks_direct_delete":
        return fetch_count_batch_specs_with_retry(
            dsn=dsn,
            spec=spec,
            connection_factory=connection_factory,
            fetcher=fetch_action_fact_ids,
            builder=action_fact_id_chunk_batch_specs,
        )
    return iter_batch_specs(spec)


def fetch_count_batch_specs_with_retry(
    *,
    dsn: str,
    spec: RuntimeHotCleanupSpec,
    connection_factory: Callable[[str], Any],
    fetcher: Callable[[Any, RuntimeHotCleanupSpec], tuple[str, ...]],
    builder: Callable[[RuntimeHotCleanupSpec, Iterable[str]], tuple[RuntimeHotCleanupSpec, ...]],
) -> tuple[RuntimeHotCleanupSpec, ...]:
    for attempt in range(COUNT_TIMEOUT_RETRIES + 1):
        try:
            with connection_factory(dsn) as conn:
                with conn.transaction():
                    conn.execute("set local transaction read only")
                    conn.execute(f"set local statement_timeout = '{COUNT_STATEMENT_TIMEOUT_MS}ms'")
                    return builder(spec, fetcher(conn, spec))
        except Exception as exc:
            if attempt < COUNT_TIMEOUT_RETRIES and is_count_timeout_exception(exc):
                continue
            raise
    raise RuntimeError("unreachable batch source retry state")


def iter_delete_batch_specs(*, conn: Any, spec: RuntimeHotCleanupSpec) -> tuple[RuntimeHotCleanupSpec, ...]:
    if spec.batch_strategy == "user_projection_run_id":
        return user_projection_run_id_batch_specs(spec, fetch_user_projection_run_ids(conn, spec))
    if spec.batch_strategy in {"event_id_chunks", "event_id_chunks_direct_delete"}:
        return event_id_chunk_batch_specs(spec, fetch_event_ids(conn, spec))
    if spec.batch_strategy == "trigger_run_id":
        return trigger_run_id_batch_specs(spec, fetch_trigger_run_ids(conn, spec))
    if spec.batch_strategy == "trigger_state_id_chunks":
        return trigger_state_id_chunk_batch_specs(spec, fetch_trigger_state_id_rows(conn, spec))
    if spec.batch_strategy == "market_data_run_id":
        return market_data_run_id_batch_specs(spec, fetch_market_data_run_ids(conn, spec))
    if spec.batch_strategy == "subscription_id_chunks_direct_delete":
        return subscription_id_chunk_batch_specs(spec, fetch_subscription_ids(conn, spec))
    if spec.batch_strategy == "action_fact_id_chunks_direct_delete":
        return action_fact_id_chunk_batch_specs(spec, fetch_action_fact_ids(conn, spec))
    return iter_batch_specs(spec)


def fetch_user_projection_run_ids(conn: Any, spec: RuntimeHotCleanupSpec) -> tuple[str, ...]:
    if not spec.batch_source_sql:
        return ()
    return tuple(str(row[0]) for row in conn.execute(spec.batch_source_sql, spec.params))


def fetch_event_ids(conn: Any, spec: RuntimeHotCleanupSpec) -> tuple[str, ...]:
    if not spec.batch_source_sql:
        return ()
    return tuple(str(row[0]) for row in conn.execute(spec.batch_source_sql, spec.params[:2]))


def fetch_trigger_run_ids(conn: Any, spec: RuntimeHotCleanupSpec) -> tuple[str, ...]:
    if not spec.batch_source_sql:
        return ()
    return tuple(str(row[0]) for row in conn.execute(spec.batch_source_sql, spec.params))


def fetch_trigger_state_id_rows(conn: Any, spec: RuntimeHotCleanupSpec) -> tuple[tuple[str, int], ...]:
    if not spec.batch_source_sql:
        return ()
    return tuple((str(row[0]), int(row[1])) for row in conn.execute(spec.batch_source_sql, spec.params))


def fetch_market_data_run_ids(conn: Any, spec: RuntimeHotCleanupSpec) -> tuple[str, ...]:
    if not spec.batch_source_sql:
        return ()
    return tuple(str(row[0]) for row in conn.execute(spec.batch_source_sql, spec.params))


def fetch_subscription_ids(conn: Any, spec: RuntimeHotCleanupSpec) -> tuple[int, ...]:
    if not spec.batch_source_sql:
        return ()
    return tuple(int(row[0]) for row in conn.execute(spec.batch_source_sql, spec.params[:1]))


def fetch_action_fact_ids(conn: Any, spec: RuntimeHotCleanupSpec) -> tuple[int, ...]:
    if not spec.batch_source_sql:
        return ()
    return tuple(int(row[0]) for row in conn.execute(spec.batch_source_sql, spec.params[:1]))


def user_projection_run_id_batch_specs(
    spec: RuntimeHotCleanupSpec,
    user_projection_run_ids: Iterable[str],
) -> tuple[RuntimeHotCleanupSpec, ...]:
    batch_specs: list[RuntimeHotCleanupSpec] = []
    for user_projection_run_id in user_projection_run_ids:
        batch = RuntimeHotCleanupBatch(
            label=f"user_projection_run_id:{user_projection_run_id}",
            start_time=user_projection_run_id,
            end_time=user_projection_run_id,
        )
        batch_specs.append(
            RuntimeHotCleanupSpec(
                layer=spec.layer,
                table=spec.table,
                count_sql=spec.count_sql,
                delete_sql=spec.delete_sql,
                params=(user_projection_run_id,),
                batch_column=spec.batch_column,
                batch_strategy=spec.batch_strategy,
                batches=(batch,),
            )
        )
    return tuple(batch_specs)


def trigger_run_id_batch_specs(
    spec: RuntimeHotCleanupSpec,
    trigger_run_ids: Iterable[str],
) -> tuple[RuntimeHotCleanupSpec, ...]:
    batch_specs: list[RuntimeHotCleanupSpec] = []
    for trigger_run_id in trigger_run_ids:
        batch = RuntimeHotCleanupBatch(
            label=f"trigger_run_id:{trigger_run_id}",
            start_time=trigger_run_id,
            end_time=trigger_run_id,
        )
        batch_specs.append(
            RuntimeHotCleanupSpec(
                layer=spec.layer,
                table=spec.table,
                count_sql=spec.count_sql,
                delete_sql=spec.delete_sql,
                params=(trigger_run_id,),
                batch_column=spec.batch_column,
                batch_strategy=spec.batch_strategy,
                batches=(batch,),
            )
        )
    return tuple(batch_specs)


def trigger_state_id_chunk_batch_specs(
    spec: RuntimeHotCleanupSpec,
    trigger_state_rows: Iterable[tuple[str, int]],
) -> tuple[RuntimeHotCleanupSpec, ...]:
    batch_specs: list[RuntimeHotCleanupSpec] = []
    current_run_id = ""
    current_chunk: list[int] = []
    run_chunk_index = 0

    def flush() -> None:
        nonlocal current_chunk, run_chunk_index
        if not current_chunk:
            return
        start_id = current_chunk[0]
        end_id = current_chunk[-1]
        batch = RuntimeHotCleanupBatch(
            label=f"trigger_state_id_chunk:{current_run_id}:{run_chunk_index:05d}",
            start_time=str(start_id),
            end_time=str(end_id),
        )
        batch_specs.append(
            RuntimeHotCleanupSpec(
                layer=spec.layer,
                table=spec.table,
                count_sql=spec.count_sql,
                delete_sql=spec.delete_sql,
                params=(current_run_id, start_id, end_id),
                batch_column=spec.batch_column,
                batch_strategy=spec.batch_strategy,
                batches=(batch,),
            )
        )
        run_chunk_index += 1
        current_chunk = []

    for run_id, trigger_state_id in trigger_state_rows:
        if current_run_id != run_id:
            flush()
            current_run_id = run_id
            run_chunk_index = 0
        current_chunk.append(int(trigger_state_id))
        if len(current_chunk) >= TRIGGER_STATE_ID_CHUNK_SIZE:
            flush()
    flush()
    return tuple(batch_specs)


def market_data_run_id_batch_specs(
    spec: RuntimeHotCleanupSpec,
    market_data_run_ids: Iterable[str],
) -> tuple[RuntimeHotCleanupSpec, ...]:
    batch_specs: list[RuntimeHotCleanupSpec] = []
    for market_data_run_id in market_data_run_ids:
        batch = RuntimeHotCleanupBatch(
            label=f"market_data_run_id:{market_data_run_id}",
            start_time=market_data_run_id,
            end_time=market_data_run_id,
        )
        batch_specs.append(
            RuntimeHotCleanupSpec(
                layer=spec.layer,
                table=spec.table,
                count_sql=spec.count_sql,
                delete_sql=spec.delete_sql,
                params=(market_data_run_id,),
                batch_column=spec.batch_column,
                batch_strategy=spec.batch_strategy,
                batches=(batch,),
            )
        )
    return tuple(batch_specs)


def event_id_chunk_batch_specs(
    spec: RuntimeHotCleanupSpec,
    event_ids: Iterable[str],
    *,
    chunk_size: int = EVENT_ID_BATCH_SIZE,
) -> tuple[RuntimeHotCleanupSpec, ...]:
    source_layer = str(spec.params[-1]) if spec.params else ""
    event_id_list = [str(item) for item in event_ids]
    batch_specs: list[RuntimeHotCleanupSpec] = []
    for index, start in enumerate(range(0, len(event_id_list), max(1, int(chunk_size)))):
        chunk = event_id_list[start : start + max(1, int(chunk_size))]
        label = f"event_id_chunk:{index:05d}"
        batch = RuntimeHotCleanupBatch(
            label=label,
            start_time=chunk[0] if chunk else "",
            end_time=chunk[-1] if chunk else "",
        )
        batch_specs.append(
            RuntimeHotCleanupSpec(
                layer=spec.layer,
                table=spec.table,
                count_sql=spec.count_sql,
                delete_sql=spec.delete_sql,
                params=(source_layer, chunk),
                batch_column=spec.batch_column,
                batch_strategy=spec.batch_strategy,
                batches=(batch,),
            )
        )
    return tuple(batch_specs)


def subscription_id_chunk_batch_specs(
    spec: RuntimeHotCleanupSpec,
    subscription_ids: Iterable[int],
    *,
    chunk_size: int = SUBSCRIPTION_ID_BATCH_SIZE,
) -> tuple[RuntimeHotCleanupSpec, ...]:
    id_list = [int(item) for item in subscription_ids]
    batch_specs: list[RuntimeHotCleanupSpec] = []
    for index, start in enumerate(range(0, len(id_list), max(1, int(chunk_size)))):
        chunk = id_list[start : start + max(1, int(chunk_size))]
        label = f"subscription_id_chunk:{index:05d}"
        batch = RuntimeHotCleanupBatch(
            label=label,
            start_time=str(chunk[0]) if chunk else "",
            end_time=str(chunk[-1]) if chunk else "",
        )
        batch_specs.append(
            RuntimeHotCleanupSpec(
                layer=spec.layer,
                table=spec.table,
                count_sql=spec.count_sql,
                delete_sql=spec.delete_sql,
                params=(chunk,),
                batch_column=spec.batch_column,
                batch_strategy=spec.batch_strategy,
                batches=(batch,),
            )
        )
    return tuple(batch_specs)


def action_fact_id_chunk_batch_specs(
    spec: RuntimeHotCleanupSpec,
    action_fact_ids: Iterable[int],
    *,
    chunk_size: int = ACTION_FACT_ID_BATCH_SIZE,
) -> tuple[RuntimeHotCleanupSpec, ...]:
    id_list = [int(item) for item in action_fact_ids]
    batch_specs: list[RuntimeHotCleanupSpec] = []
    for index, start in enumerate(range(0, len(id_list), max(1, int(chunk_size)))):
        chunk = id_list[start : start + max(1, int(chunk_size))]
        label = f"action_fact_id_chunk:{index:05d}"
        batch = RuntimeHotCleanupBatch(
            label=label,
            start_time=str(chunk[0]) if chunk else "",
            end_time=str(chunk[-1]) if chunk else "",
        )
        batch_specs.append(
            RuntimeHotCleanupSpec(
                layer=spec.layer,
                table=spec.table,
                count_sql=spec.count_sql,
                delete_sql=spec.delete_sql,
                params=(chunk,),
                batch_column=spec.batch_column,
                batch_strategy=spec.batch_strategy,
                batches=(batch,),
            )
        )
    return tuple(batch_specs)


def iter_batch_specs(spec: RuntimeHotCleanupSpec) -> tuple[RuntimeHotCleanupSpec, ...]:
    trade_date = extract_trade_date(spec)
    if not trade_date or not spec.batch_column:
        return ()
    if spec.batch_strategy not in {
        "intraday_time_windows",
        "intraday_time_windows_fine",
        "intraday_time_windows_stock_15m",
        "intraday_time_windows_stock_5m",
        "intraday_time_windows_stock_1m",
        "intraday_label_windows",
        "intraday_label_windows_5m",
    }:
        return ()
    start_prefix = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
    date_param = spec.params[0]
    batch_specs: list[RuntimeHotCleanupSpec] = []
    for batch in spec.batches:
        if spec.batch_strategy in {
            "intraday_time_windows",
            "intraday_time_windows_fine",
            "intraday_time_windows_stock_15m",
            "intraday_time_windows_stock_5m",
            "intraday_time_windows_stock_1m",
        }:
            start = f"{start_prefix} {batch.start_time}+08"
            end = f"{start_prefix} {batch.end_time}+08"
            count_sql = (
                f"select count(*) from {spec.table} "
                f"where trade_date = %s and {spec.batch_column} >= %s::timestamptz "
                f"and {spec.batch_column} < %s::timestamptz"
            )
            delete_sql = (
                f"delete from {spec.table} "
                f"where trade_date = %s and {spec.batch_column} >= %s::timestamptz "
                f"and {spec.batch_column} < %s::timestamptz"
            )
        else:
            start = batch.start_time
            end = batch.end_time
            count_sql = (
                f"select count(*) from {spec.table} "
                f"where trade_date = %s and {spec.batch_column} >= %s "
                f"and {spec.batch_column} < %s"
            )
            delete_sql = (
                f"delete from {spec.table} "
                f"where trade_date = %s and {spec.batch_column} >= %s "
                f"and {spec.batch_column} < %s"
            )
        batch_specs.append(
            RuntimeHotCleanupSpec(
                layer=spec.layer,
                table=spec.table,
                count_sql=count_sql,
                delete_sql=delete_sql,
                params=(date_param, start, end),
                batch_column=spec.batch_column,
                batch_strategy=spec.batch_strategy,
                batches=(batch,),
            )
        )
    return tuple(batch_specs)


def is_batched_parent_spec(spec: RuntimeHotCleanupSpec) -> bool:
    if spec.batch_strategy == "user_projection_run_id":
        return bool(spec.batch_source_sql and spec.batch_column and len(spec.params) == 1)
    if spec.batch_strategy == "event_id_chunks":
        return bool(spec.batch_source_sql and spec.batch_column and len(spec.params) == 2)
    if spec.batch_strategy == "event_id_chunks_direct_delete":
        return bool(spec.batch_source_sql and spec.batch_column and len(spec.params) >= 2)
    if spec.batch_strategy == "trigger_run_id":
        return bool(spec.batch_source_sql and spec.batch_column and len(spec.params) == 1)
    if spec.batch_strategy == "trigger_state_id_chunks":
        return bool(spec.batch_source_sql and spec.batch_column and len(spec.params) == 1)
    if spec.batch_strategy == "market_data_run_id":
        return bool(spec.batch_source_sql and spec.batch_column and len(spec.params) == 1)
    if spec.batch_strategy == "subscription_id_chunks_direct_delete":
        return bool(spec.batch_source_sql and spec.batch_column and len(spec.params) == 1)
    if spec.batch_strategy == "action_fact_id_chunks_direct_delete":
        return bool(spec.batch_source_sql and spec.batch_column and len(spec.params) == 1)
    return bool(spec.batches and spec.batch_column and spec.batch_strategy and len(spec.params) < 3)


def batch_timing_bounds(batch_spec: RuntimeHotCleanupSpec) -> tuple[str, str]:
    batch = batch_spec.batches[0]
    if len(batch_spec.params) >= 3:
        return str(batch_spec.params[-2]), str(batch_spec.params[-1])
    return batch.start_time, batch.end_time


def elapsed_ms(start: float) -> float:
    return (perf_counter() - start) * 1000


def blocked_closeout(
    *,
    result: str,
    plan: dict[str, Any],
    closeout_path: str | Path,
    side_effects: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "result": result,
        "component": "Runtime Dirty Hot Keep2 Cleanup",
        "mode": "execute",
        "created_at": datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat(),
        "plan_path": str(plan.get("plan_path") or ""),
        "closeout_path": str(closeout_path),
        "retained_trade_dates": list(plan.get("retained_trade_dates") or []),
        "cleanup_trade_dates": list(plan.get("cleanup_trade_dates") or []),
        "cleanup_executed": False,
        "deleted_total_rows": 0,
        "blockers": [result],
        "side_effects": side_effects,
    }
    write_json(closeout_path, payload)
    return payload


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
