import tempfile
import unittest
import fcntl
from pathlib import Path

from run_runtime_hot_keep5_cleanup_once import run_runtime_hot_keep5_cleanup_once

from ashare_v3.ingestion.runtime_hot_cleanup import (
    CONFIRM_TOKEN,
    COUNT_STATEMENT_TIMEOUT_MS,
    DELETE_STATEMENT_TIMEOUT_MS,
    DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN,
    EVENT_ID_BATCH_SIZE,
    KEEP5_CONFIRM_TOKEN,
    TRIGGER_STATE_ID_CHUNK_SIZE,
    audit_runtime_hot_cleanup_fk_closure,
    bind_cleanup_spec,
    build_keep2_dirty_hot_cleanup_plan,
    build_hot_cleanup_specs,
    discover_hot_trade_dates,
    execute_keep2_dirty_hot_cleanup,
)


CLOSED_30M_SUMMARY_TABLES = {
    "stock_closed_30m_summary",
    "index_closed_30m_summary",
    "board_closed_30m_summary",
}
CLOSED_30M_ENRICHMENT_TABLES = {
    "stock_closed_30m_signal_enrichment",
    "index_closed_30m_signal_enrichment",
    "board_closed_30m_signal_enrichment",
}
CLOSED_30M_TABLES = CLOSED_30M_SUMMARY_TABLES | CLOSED_30M_ENRICHMENT_TABLES
EOD_SNAPSHOT_TABLES = {
    "stock_eod_snapshot",
    "index_eod_snapshot",
    "board_eod_snapshot",
}
EOD_RECONCILIATION_ITEM_TABLES = {
    "stock_eod_reconciliation_item",
    "index_eod_reconciliation_item",
    "board_eod_reconciliation_item",
}
PROJECTION_ENRICHMENT_V4_TABLES = {
    "stock_projection_enrichment_v4_metric",
    "index_projection_enrichment_v4_metric",
    "board_projection_enrichment_v4_metric",
}
REALTIME_HINT_PROJECTION_METRIC_TABLES = {
    "index_realtime_hint_projection_metric",
    "board_realtime_hint_projection_metric",
}


class _FakeScalarResult:
    def __init__(self, value: int) -> None:
        self.value = value

    def fetchone(self):
        return (self.value,)


class _FakeRowsResult:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows

    def fetchall(self):
        return list(self.rows)


class _FakeTransaction:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeCleanupConnection:
    def __init__(
        self,
        counts_by_batch: dict[str, int] | None = None,
        deleted_by_batch: dict[str, int] | None = None,
        errors_by_batch: dict[str, Exception] | None = None,
        errors_by_table_batch: dict[tuple[str, str], Exception] | None = None,
        transient_errors_by_table_batch: dict[tuple[str, str], list[Exception]] | None = None,
        projection_run_ids_by_date: dict[str, list[str]] | None = None,
        event_ids_by_date_layer: dict[tuple[str, str], list[str]] | None = None,
        transient_event_source_errors_by_date_layer: dict[tuple[str, str], list[Exception]] | None = None,
        subscription_ids_by_date: dict[str, list[int]] | None = None,
        action_fact_ids_by_date_table: dict[tuple[str, str], list[int]] | None = None,
        trigger_run_ids_by_date: dict[str, list[str]] | None = None,
        trigger_state_ids_by_date: dict[str, list[tuple[str, int]]] | None = None,
        market_data_run_ids_by_date: dict[str, list[str]] | None = None,
        counts_by_table: dict[str, int] | None = None,
        deleted_by_table: dict[str, int] | None = None,
        delete_errors_by_table_batch: dict[tuple[str, str], Exception] | None = None,
    ) -> None:
        self.counts_by_batch = counts_by_batch or {}
        self.deleted_by_batch = deleted_by_batch or {}
        self.errors_by_batch = errors_by_batch or {}
        self.errors_by_table_batch = errors_by_table_batch or {}
        self.transient_errors_by_table_batch = {
            key: list(value) for key, value in (transient_errors_by_table_batch or {}).items()
        }
        self.projection_run_ids_by_date = projection_run_ids_by_date or {}
        self.event_ids_by_date_layer = event_ids_by_date_layer or {}
        self.transient_event_source_errors_by_date_layer = {
            key: list(value) for key, value in (transient_event_source_errors_by_date_layer or {}).items()
        }
        self.subscription_ids_by_date = subscription_ids_by_date or {}
        self.action_fact_ids_by_date_table = action_fact_ids_by_date_table or {}
        self.trigger_run_ids_by_date = trigger_run_ids_by_date or {}
        self.trigger_state_ids_by_date = trigger_state_ids_by_date or {}
        self.market_data_run_ids_by_date = market_data_run_ids_by_date or {}
        self.counts_by_table = counts_by_table or {}
        self.deleted_by_table = deleted_by_table or {}
        self.delete_errors_by_table_batch = delete_errors_by_table_batch or {}
        self.count_calls: list[tuple[str, tuple]] = []
        self.delete_calls: list[tuple[str, tuple]] = []
        self.batch_source_calls: list[tuple[str, tuple]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def transaction(self):
        return _FakeTransaction()

    def execute(self, sql, params=None):
        params_tuple = tuple(params or ())
        sql_lower = str(sql).lower()
        if sql_lower.startswith("set local"):
            return _FakeScalarResult(0)
        if sql_lower.startswith("select user_projection_run_id"):
            self.batch_source_calls.append((str(sql), params_tuple))
            trade_date = str(params_tuple[0]) if params_tuple else ""
            return [(item,) for item in self.projection_run_ids_by_date.get(trade_date, [])]
        if sql_lower.startswith("select event_id from common_event_outbox"):
            self.batch_source_calls.append((str(sql), params_tuple))
            key = (str(params_tuple[0]), str(params_tuple[1]))
            transient_errors = self.transient_event_source_errors_by_date_layer.get(key, [])
            if transient_errors:
                raise transient_errors.pop(0)
            return [(item,) for item in self.event_ids_by_date_layer.get(key, [])]
        if sql_lower.startswith("select subscription_id from common_market_data_subscription"):
            self.batch_source_calls.append((str(sql), params_tuple))
            trade_date = str(params_tuple[0]) if params_tuple else ""
            return [(item,) for item in self.subscription_ids_by_date.get(trade_date, [])]
        if sql_lower.startswith("select action_fact_id from"):
            self.batch_source_calls.append((str(sql), params_tuple))
            trade_date = str(params_tuple[0]) if params_tuple else ""
            table_name = _table_name_from_sql(sql)
            return [(item,) for item in self.action_fact_ids_by_date_table.get((trade_date, table_name), [])]
        if sql_lower.startswith("select run_id from common_trigger_run"):
            self.batch_source_calls.append((str(sql), params_tuple))
            trade_date = str(params_tuple[0]) if params_tuple else ""
            return [(item,) for item in self.trigger_run_ids_by_date.get(trade_date, [])]
        if sql_lower.startswith("select s.run_id, s.trigger_state_id from common_trigger_state"):
            self.batch_source_calls.append((str(sql), params_tuple))
            trade_date = str(params_tuple[0]) if params_tuple else ""
            return list(self.trigger_state_ids_by_date.get(trade_date, []))
        if sql_lower.startswith("select run_id from common_market_data_run"):
            self.batch_source_calls.append((str(sql), params_tuple))
            trade_date = str(params_tuple[0]) if params_tuple else ""
            return [(item,) for item in self.market_data_run_ids_by_date.get(trade_date, [])]
        if sql_lower.startswith("select count(*)"):
            self.count_calls.append((str(sql), params_tuple))
            batch_key = _batch_key_from_params(params_tuple)
            table_name = _table_name_from_sql(sql)
            transient_errors = self.transient_errors_by_table_batch.get((table_name, batch_key), [])
            if transient_errors:
                raise transient_errors.pop(0)
            if (table_name, batch_key) in self.errors_by_table_batch:
                raise self.errors_by_table_batch[(table_name, batch_key)]
            if batch_key in self.errors_by_batch:
                raise self.errors_by_batch[batch_key]
            return _FakeScalarResult(self.counts_by_batch.get(batch_key, self.counts_by_table.get(table_name, 0)))
        if sql_lower.startswith("delete"):
            self.delete_calls.append((str(sql), params_tuple))
            batch_key = _batch_key_from_params(params_tuple)
            table_name = _table_name_from_sql(sql)
            if (table_name, batch_key) in self.delete_errors_by_table_batch:
                raise self.delete_errors_by_table_batch[(table_name, batch_key)]

            class _Cursor:
                rowcount = self.deleted_by_batch.get(batch_key, self.deleted_by_table.get(table_name, 0))

            return _Cursor()
        raise AssertionError(f"unexpected sql: {sql}")


class _FakeFkClosureConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        sql_lower = str(sql).lower()
        if sql_lower.startswith("begin") or sql_lower.startswith("set local"):
            return _FakeRowsResult([])
        if "from pg_constraint" in sql_lower:
            return _FakeRowsResult([])
        raise AssertionError(f"unexpected sql: {sql}")

    def rollback(self):
        return None


def _batch_key_from_params(params: tuple) -> str:
    if len(params) == 2 and isinstance(params[1], (list, tuple)):
        return "event_ids:" + ",".join(str(item) for item in params[1])
    if (
        len(params) == 3
        and isinstance(params[0], str)
        and not (len(params[0]) == 8 and params[0].isdigit())
        and all(isinstance(item, int) for item in params[1:])
    ):
        return f"{params[0]}:{params[1]}->{params[2]}"
    if len(params) >= 3:
        return f"{params[-2]}->{params[-1]}"
    if len(params) == 1 and not (isinstance(params[0], str) and len(params[0]) == 8 and params[0].isdigit()):
        return str(params[0])
    return "full_day"


def _table_name_from_sql(sql: str) -> str:
    tokens = str(sql).replace("\n", " ").split()
    lowered = [token.lower() for token in tokens]
    for keyword in ("from", "delete"):
        if keyword in lowered:
            index = lowered.index(keyword)
            if keyword == "delete" and index + 1 < len(lowered) and lowered[index + 1] == "from":
                index += 1
            if index + 1 < len(tokens):
                return tokens[index + 1]
    return ""


def _fine_time_counts() -> dict[str, int]:
    return {
        "2026-06-12 09:30:00+08->2026-06-12 10:00:00+08": 2,
        "2026-06-12 10:00:00+08->2026-06-12 10:30:00+08": 3,
        "2026-06-12 10:30:00+08->2026-06-12 11:00:00+08": 4,
        "2026-06-12 11:00:00+08->2026-06-12 11:31:00+08": 5,
        "2026-06-12 13:00:00+08->2026-06-12 13:30:00+08": 6,
        "2026-06-12 13:30:00+08->2026-06-12 14:00:00+08": 7,
        "2026-06-12 14:00:00+08->2026-06-12 14:30:00+08": 8,
        "2026-06-12 14:30:00+08->2026-06-12 15:01:00+08": 9,
    }


def _stock_15m_time_counts() -> dict[str, int]:
    return {
        "2026-06-12 09:30:00+08->2026-06-12 09:45:00+08": 3,
        "2026-06-12 09:45:00+08->2026-06-12 10:00:00+08": 4,
        "2026-06-12 10:00:00+08->2026-06-12 10:15:00+08": 5,
        "2026-06-12 10:15:00+08->2026-06-12 10:30:00+08": 6,
        "2026-06-12 10:30:00+08->2026-06-12 10:45:00+08": 7,
        "2026-06-12 10:45:00+08->2026-06-12 11:00:00+08": 8,
        "2026-06-12 11:00:00+08->2026-06-12 11:15:00+08": 9,
        "2026-06-12 11:15:00+08->2026-06-12 11:31:00+08": 10,
        "2026-06-12 13:00:00+08->2026-06-12 13:15:00+08": 11,
        "2026-06-12 13:15:00+08->2026-06-12 13:30:00+08": 12,
        "2026-06-12 13:30:00+08->2026-06-12 13:45:00+08": 13,
        "2026-06-12 13:45:00+08->2026-06-12 14:00:00+08": 14,
        "2026-06-12 14:00:00+08->2026-06-12 14:15:00+08": 15,
        "2026-06-12 14:15:00+08->2026-06-12 14:30:00+08": 16,
        "2026-06-12 14:30:00+08->2026-06-12 14:45:00+08": 17,
        "2026-06-12 14:45:00+08->2026-06-12 15:01:00+08": 18,
    }


def _stock_5m_time_counts() -> dict[str, int]:
    ranges = (
        ("09:30:00", "09:35:00"),
        ("09:35:00", "09:40:00"),
        ("09:40:00", "09:45:00"),
        ("09:45:00", "09:50:00"),
        ("09:50:00", "09:55:00"),
        ("09:55:00", "10:00:00"),
        ("10:00:00", "10:05:00"),
        ("10:05:00", "10:10:00"),
        ("10:10:00", "10:15:00"),
        ("10:15:00", "10:20:00"),
        ("10:20:00", "10:25:00"),
        ("10:25:00", "10:30:00"),
        ("10:30:00", "10:35:00"),
        ("10:35:00", "10:40:00"),
        ("10:40:00", "10:45:00"),
        ("10:45:00", "10:50:00"),
        ("10:50:00", "10:55:00"),
        ("10:55:00", "11:00:00"),
        ("11:00:00", "11:05:00"),
        ("11:05:00", "11:10:00"),
        ("11:10:00", "11:15:00"),
        ("11:15:00", "11:20:00"),
        ("11:20:00", "11:25:00"),
        ("11:25:00", "11:31:00"),
        ("13:00:00", "13:05:00"),
        ("13:05:00", "13:10:00"),
        ("13:10:00", "13:15:00"),
        ("13:15:00", "13:20:00"),
        ("13:20:00", "13:25:00"),
        ("13:25:00", "13:30:00"),
        ("13:30:00", "13:35:00"),
        ("13:35:00", "13:40:00"),
        ("13:40:00", "13:45:00"),
        ("13:45:00", "13:50:00"),
        ("13:50:00", "13:55:00"),
        ("13:55:00", "14:00:00"),
        ("14:00:00", "14:05:00"),
        ("14:05:00", "14:10:00"),
        ("14:10:00", "14:15:00"),
        ("14:15:00", "14:20:00"),
        ("14:20:00", "14:25:00"),
        ("14:25:00", "14:30:00"),
        ("14:30:00", "14:35:00"),
        ("14:35:00", "14:40:00"),
        ("14:40:00", "14:45:00"),
        ("14:45:00", "14:50:00"),
        ("14:50:00", "14:55:00"),
        ("14:55:00", "15:01:00"),
    )
    return {f"2026-06-12 {start}+08->2026-06-12 {end}+08": index for index, (start, end) in enumerate(ranges, 1)}


def _stock_1m_time_counts() -> dict[str, int]:
    ranges: list[tuple[str, str]] = []
    for hour, start_minute, end_minute in ((9, 30, 60), (10, 0, 60), (11, 0, 31), (13, 0, 60), (14, 0, 60), (15, 0, 1)):
        for minute in range(start_minute, end_minute):
            next_hour = hour + 1 if minute == 59 else hour
            next_minute = 0 if minute == 59 else minute + 1
            ranges.append((f"{hour:02d}:{minute:02d}:00", f"{next_hour:02d}:{next_minute:02d}:00"))
    return {f"2026-06-12 {start}+08->2026-06-12 {end}+08": 1 for start, end in ranges}


class RuntimeHotCleanupTest(unittest.TestCase):
    def test_keep5_manifest_gated_plan_blocks_without_verified_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive_root = Path(tmp) / "archive"
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=[
                    "20260612",
                    "20260615",
                    "20260616",
                    "20260617",
                    "20260618",
                    "20260619",
                    "20260622",
                ],
                retention_trade_days=5,
                require_verified_archive=True,
                archive_root=archive_root,
                table_counter=lambda _spec, _trade_date: 0,
                plan_path=Path(tmp) / "plan.json",
            )

        self.assertEqual(plan["result"], "DIRTY_HOT_KEEP2_CLEANUP_PLAN_BLOCKED")
        self.assertEqual(plan["retained_trade_dates"], ["20260616", "20260617", "20260618", "20260619", "20260622"])
        self.assertEqual(plan["cleanup_trade_dates"], ["20260612", "20260615"])
        self.assertIn("archive_manifest_not_verified:20260612", plan["blockers"])
        self.assertTrue(plan["archive_required"])

    def test_keep5_manifest_gated_plan_allows_only_verified_archive_dates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive_root = Path(tmp) / "archive"
            _write_verified_runtime_archive_manifest(archive_root, "20260612")
            _write_verified_runtime_archive_manifest(archive_root, "20260615")
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=[
                    "20260612",
                    "20260615",
                    "20260616",
                    "20260617",
                    "20260618",
                    "20260619",
                    "20260622",
                ],
                retention_trade_days=5,
                require_verified_archive=True,
                archive_root=archive_root,
                table_counter=lambda _spec, trade_date: 3 if trade_date == "20260612" else 0,
                plan_path=Path(tmp) / "plan.json",
            )

        self.assertEqual(plan["result"], "DIRTY_HOT_KEEP2_CLEANUP_PLAN_PASS")
        self.assertEqual(plan["cleanup_trade_dates"], ["20260612", "20260615"])
        self.assertEqual(plan["archive_manifest_evidence"]["20260612"]["result"], "ARCHIVED_VERIFIED")
        self.assertFalse(set(plan["retained_trade_dates"]) & set(plan["cleanup_trade_dates"]))

    def test_keep5_execute_rechecks_archive_manifest_before_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive_root = Path(tmp) / "archive"
            _write_verified_runtime_archive_manifest(archive_root, "20260612")
            plan_path = Path(tmp) / "plan.json"
            closeout_path = Path(tmp) / "closeout.json"
            build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260615", "20260616", "20260617", "20260618", "20260619"],
                retention_trade_days=5,
                require_verified_archive=True,
                archive_root=archive_root,
                table_counter=lambda _spec, trade_date: 1 if trade_date == "20260612" else 0,
                plan_path=plan_path,
            )
            manifest = archive_root / "trade_date=20260612" / "manifests" / "archive_manifest.json"
            manifest.unlink()
            deleted: list[str] = []
            result = execute_keep2_dirty_hot_cleanup(
                plan_path=plan_path,
                confirm_token=KEEP5_CONFIRM_TOKEN,
                expected_confirm_token=KEEP5_CONFIRM_TOKEN,
                current_trade_dates=["20260612", "20260615", "20260616", "20260617", "20260618", "20260619"],
                table_counter=lambda _spec, trade_date: 1 if trade_date == "20260612" else 0,
                table_deleter=lambda spec, _trade_date: deleted.append(spec.table) or 1,
                closeout_path=closeout_path,
            )

        self.assertEqual(result["result"], "BLOCKED_ARCHIVE_MANIFEST_NOT_VERIFIED")
        self.assertEqual(deleted, [])
        self.assertFalse(result["side_effects"]["writes_database"])

    def test_direct_delete_no_archive_uses_direct_event_infra_counts(self) -> None:
        fake_conn = _FakeCleanupConnection(counts_by_table={"common_event_inbox": 1, "common_event_outbox": 1})

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                direct_delete_no_archive=True,
                connection_factory=lambda _dsn: fake_conn,
                fk_closure_auditor=lambda **_kwargs: {
                    "missing_child_scope_count": 0,
                    "order_bad_count": 0,
                    "missing_child_scope": [],
                    "order_bad": [],
                },
                plan_path=Path(tmp) / "plan.json",
            )

        self.assertEqual(plan["result"], "DIRTY_HOT_KEEP2_CLEANUP_PLAN_PASS")
        self.assertFalse(
            any("select event_id from common_event_outbox" in sql for sql, _params in fake_conn.batch_source_calls)
        )
        inbox_count_calls = [sql for sql, _params in fake_conn.count_calls if "from common_event_inbox" in sql]
        self.assertTrue(any("exists (select 1 from common_event_outbox" in sql for sql in inbox_count_calls))

    def test_direct_delete_no_archive_deletes_event_infra_by_event_id_chunks(self) -> None:
        fake_conn = _FakeCleanupConnection(
            counts_by_table={"common_event_inbox": 2, "common_event_outbox": 2},
            deleted_by_batch={"event_ids:event-a,event-b": 2},
            event_ids_by_date_layer={("20260612", "N4_trigger"): ["event-a", "event-b"]},
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                direct_delete_no_archive=True,
                connection_factory=lambda _dsn: fake_conn,
                fk_closure_auditor=lambda **_kwargs: {
                    "missing_child_scope_count": 0,
                    "order_bad_count": 0,
                    "missing_child_scope": [],
                    "order_bad": [],
                },
                plan_path=plan_path,
            )
            result = execute_keep2_dirty_hot_cleanup(
                plan_path=plan_path,
                confirm_token=DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN,
                expected_confirm_token=DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN,
                current_trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
            )

        inbox_deletes = [call for call in fake_conn.delete_calls if "delete from common_event_inbox" in call[0]]
        outbox_deletes = [call for call in fake_conn.delete_calls if "delete from common_event_outbox" in call[0]]
        self.assertEqual(result["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        self.assertTrue(inbox_deletes)
        self.assertTrue(outbox_deletes)
        self.assertTrue(any(params == ("N4_trigger", ["event-a", "event-b"]) for _sql, params in inbox_deletes))
        self.assertTrue(any(params == ("N4_trigger", ["event-a", "event-b"]) for _sql, params in outbox_deletes))

    def test_direct_delete_no_archive_deletes_action_fact_by_action_fact_id_chunks(self) -> None:
        fake_conn = _FakeCleanupConnection(
            action_fact_ids_by_date_table={("20260612", "stock_action_fact"): [101, 102]},
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                direct_delete_no_archive=True,
                skip_row_count_plan=True,
                connection_factory=lambda _dsn: fake_conn,
                fk_closure_auditor=lambda **_kwargs: {
                    "missing_child_scope_count": 0,
                    "order_bad_count": 0,
                    "missing_child_scope": [],
                    "order_bad": [],
                },
                plan_path=plan_path,
            )
            result = execute_keep2_dirty_hot_cleanup(
                plan_path=plan_path,
                confirm_token=DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN,
                expected_confirm_token=DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN,
                current_trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
            )

        action_fact_deletes = [
            call for call in fake_conn.delete_calls if "delete from stock_action_fact" in call[0]
        ]
        self.assertEqual(result["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        self.assertTrue(action_fact_deletes)
        self.assertTrue(any(params == ([101, 102],) for _sql, params in action_fact_deletes))
        self.assertFalse(any(params == ("20260612",) for _sql, params in action_fact_deletes))

    def test_direct_delete_no_archive_deletes_subscription_children_by_subscription_id_chunks(self) -> None:
        fake_conn = _FakeCleanupConnection(
            subscription_ids_by_date={"20260612": [1, 2]},
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                direct_delete_no_archive=True,
                skip_row_count_plan=True,
                connection_factory=lambda _dsn: fake_conn,
                fk_closure_auditor=lambda **_kwargs: {
                    "missing_child_scope_count": 0,
                    "order_bad_count": 0,
                    "missing_child_scope": [],
                    "order_bad": [],
                },
                plan_path=plan_path,
            )
            result = execute_keep2_dirty_hot_cleanup(
                plan_path=plan_path,
                confirm_token=DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN,
                expected_confirm_token=DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN,
                current_trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
            )

        board_minute_deletes = [
            call for call in fake_conn.delete_calls if "delete from board_minute_bar_1m" in call[0]
        ]
        self.assertEqual(result["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        self.assertTrue(
            any("subscription_id = any(%s)" in sql and params == ([1, 2],) for sql, params in board_minute_deletes)
        )

    def test_fk_closure_auditor_entrypoint_does_not_require_execute_plan_context(self) -> None:
        evidence = audit_runtime_hot_cleanup_fk_closure(
            cleanup_dates=["20260612"],
            connection_factory=lambda _dsn: _FakeFkClosureConnection(),
        )

        self.assertEqual(evidence["missing_child_scope_count"], 0)
        self.assertEqual(evidence["order_bad_count"], 0)

    def test_event_infra_index_migration_draft_is_safe(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        migration = repo_root / "sql" / "runtime_dirty_hot_keep2_event_infra_indexes.sql"
        rollback = repo_root / "sql" / "runtime_dirty_hot_keep2_event_infra_indexes_rollback.sql"

        migration_sql = migration.read_text(encoding="utf-8").lower()
        rollback_sql = rollback.read_text(encoding="utf-8").lower()

        self.assertIn("create index if not exists idx_common_event_outbox_trade_source_event", migration_sql)
        self.assertIn("on common_event_outbox (trade_date, source_layer, event_id)", migration_sql)
        self.assertIn("create index if not exists idx_common_event_inbox_source_event", migration_sql)
        self.assertIn("on common_event_inbox (source_layer, event_id)", migration_sql)
        self.assertIn("drop index if exists idx_common_event_inbox_source_event", rollback_sql)
        self.assertIn("drop index if exists idx_common_event_outbox_trade_source_event", rollback_sql)
        forbidden_tokens = ("drop table", "delete from", "update ", "truncate ", "macraid", "condition_", "n1_", "n2_")
        for token in forbidden_tokens:
            self.assertNotIn(token, migration_sql)
            self.assertNotIn(token, rollback_sql)

    def test_stock_minute_bar_index_migration_draft_is_safe(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        migration = repo_root / "sql" / "runtime_dirty_hot_keep2_stock_minute_bar_indexes.sql"
        rollback = repo_root / "sql" / "runtime_dirty_hot_keep2_stock_minute_bar_indexes_rollback.sql"

        migration_sql = migration.read_text(encoding="utf-8").lower()
        rollback_sql = rollback.read_text(encoding="utf-8").lower()

        self.assertIn("create index if not exists idx_stock_minute_bar_1m_trade_bar_time", migration_sql)
        self.assertIn("on stock_minute_bar_1m (trade_date, bar_time)", migration_sql)
        self.assertIn("drop index if exists idx_stock_minute_bar_1m_trade_bar_time", rollback_sql)
        forbidden_tokens = (
            "drop table",
            "delete from",
            "update ",
            "insert ",
            "truncate ",
            "macraid",
            "condition_",
            "n1_",
            "n2_",
        )
        for token in forbidden_tokens:
            self.assertNotIn(token, migration_sql)
            self.assertNotIn(token, rollback_sql)

    def test_market_subscription_fk_index_migration_draft_is_safe(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        migration = repo_root / "sql" / "runtime_dirty_hot_keep2_market_subscription_fk_indexes.sql"
        rollback = repo_root / "sql" / "runtime_dirty_hot_keep2_market_subscription_fk_indexes_rollback.sql"

        self.assertTrue(migration.exists(), migration)
        self.assertTrue(rollback.exists(), rollback)
        migration_sql = migration.read_text(encoding="utf-8").lower()
        rollback_sql = rollback.read_text(encoding="utf-8").lower()
        expected_indexes = {
            "idx_stock_realtime_daily_snapshot_subscription": ("stock_realtime_daily_snapshot", "subscription_id"),
            "idx_index_realtime_daily_snapshot_subscription": ("index_realtime_daily_snapshot", "subscription_id"),
            "idx_board_realtime_daily_snapshot_subscription": ("board_realtime_daily_snapshot", "subscription_id"),
            "idx_stock_minute_bar_1m_subscription": ("stock_minute_bar_1m", "subscription_id"),
            "idx_index_minute_bar_1m_subscription": ("index_minute_bar_1m", "subscription_id"),
            "idx_board_minute_bar_1m_subscription": ("board_minute_bar_1m", "subscription_id"),
            "idx_stock_prev_day_preload_status_subscription": (
                "stock_previous_day_minute_preload_status",
                "subscription_id",
            ),
            "idx_index_prev_day_preload_status_subscription": (
                "index_previous_day_minute_preload_status",
                "subscription_id",
            ),
            "idx_board_prev_day_preload_status_subscription": (
                "board_previous_day_minute_preload_status",
                "subscription_id",
            ),
            "idx_stock_realtime_projection_metric_subscription": (
                "stock_realtime_projection_metric",
                "subscription_id",
            ),
            "idx_index_realtime_projection_metric_subscription": (
                "index_realtime_projection_metric",
                "subscription_id",
            ),
            "idx_board_realtime_projection_metric_subscription": (
                "board_realtime_projection_metric",
                "subscription_id",
            ),
            "idx_stock_trigger_context_subscription": (
                "stock_trigger_context_snapshot",
                "source_market_subscription_id",
            ),
            "idx_index_trigger_context_subscription": (
                "index_trigger_context_snapshot",
                "source_market_subscription_id",
            ),
            "idx_board_trigger_context_subscription": (
                "board_trigger_context_snapshot",
                "source_market_subscription_id",
            ),
            "idx_common_trigger_match_market_subscription": (
                "common_trigger_match",
                "source_market_subscription_id",
            ),
        }

        for index_name, (table_name, column_name) in expected_indexes.items():
            self.assertIn(f"create index if not exists {index_name}", migration_sql)
            self.assertIn(f"on {table_name} ({column_name})", migration_sql)

        rollback_drops = {
            line.removeprefix("drop index if exists ").rstrip(";")
            for line in rollback_sql.splitlines()
            if line.startswith("drop index if exists ")
        }
        self.assertEqual(rollback_drops, set(expected_indexes))
        self.assertNotIn("create index", rollback_sql)

        forbidden_tokens = (
            "concurrently",
            "drop table",
            "delete from",
            "update ",
            "insert ",
            "truncate ",
            "macraid",
            "condition_",
            "n1_",
            "n2_",
            "docs/",
            "tmp/",
        )
        for token in forbidden_tokens:
            self.assertNotIn(token, migration_sql)
            self.assertNotIn(token, rollback_sql)

    def test_market_data_run_fk_index_migration_draft_is_safe(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        migration = repo_root / "sql" / "runtime_hot_keep5_market_data_run_fk_indexes.sql"
        rollback = repo_root / "sql" / "runtime_hot_keep5_market_data_run_fk_indexes_rollback.sql"

        self.assertTrue(migration.exists(), migration)
        self.assertTrue(rollback.exists(), rollback)
        migration_sql = migration.read_text(encoding="utf-8").lower()
        rollback_sql = rollback.read_text(encoding="utf-8").lower()
        expected_indexes = {
            "idx_board_acpm_prev_day_run": (
                "board_action_confirmation_projection_metric",
                "source_previous_day_minute_run_id",
            ),
            "idx_board_acpm_subscription_run": (
                "board_action_confirmation_projection_metric",
                "source_subscription_run_id",
            ),
            "idx_board_acpm_today_minute_run": (
                "board_action_confirmation_projection_metric",
                "source_today_minute_run_id",
            ),
            "idx_board_action_fact_market_data_run": ("board_action_fact", "source_market_data_run_id"),
            "idx_board_c30_enrich_prev_day_run": (
                "board_closed_30m_signal_enrichment",
                "source_previous_day_minute_run_id",
            ),
            "idx_board_c30_enrich_subscription_run": (
                "board_closed_30m_signal_enrichment",
                "source_subscription_run_id",
            ),
            "idx_board_c30_summary_subscription_run": (
                "board_closed_30m_summary",
                "source_subscription_run_id",
            ),
            "idx_board_eod_snapshot_c3_run": ("board_eod_snapshot", "source_c3_run_id"),
            "idx_board_proj_enrich_prev_day_run": (
                "board_projection_enrichment_v4_metric",
                "source_previous_day_minute_run_id",
            ),
            "idx_board_proj_enrich_subscription_run": (
                "board_projection_enrichment_v4_metric",
                "source_subscription_run_id",
            ),
            "idx_board_proj_enrich_today_minute_run": (
                "board_projection_enrichment_v4_metric",
                "source_today_minute_run_id",
            ),
            "idx_board_hint_proj_prev_day_run": (
                "board_realtime_hint_projection_metric",
                "source_previous_day_minute_run_id",
            ),
            "idx_board_hint_proj_subscription_run": (
                "board_realtime_hint_projection_metric",
                "source_subscription_run_id",
            ),
            "idx_common_action_event_market_data_run": ("common_action_event", "source_market_data_run_id"),
            "idx_common_position_event_market_data_run": ("common_position_event", "source_market_data_run_id"),
            "idx_common_trigger_run_market_data_run": ("common_trigger_run", "source_market_data_run_id"),
            "idx_index_acpm_prev_day_run": (
                "index_action_confirmation_projection_metric",
                "source_previous_day_minute_run_id",
            ),
            "idx_index_acpm_subscription_run": (
                "index_action_confirmation_projection_metric",
                "source_subscription_run_id",
            ),
            "idx_index_acpm_today_minute_run": (
                "index_action_confirmation_projection_metric",
                "source_today_minute_run_id",
            ),
            "idx_index_action_fact_market_data_run": ("index_action_fact", "source_market_data_run_id"),
            "idx_index_c30_enrich_prev_day_run": (
                "index_closed_30m_signal_enrichment",
                "source_previous_day_minute_run_id",
            ),
            "idx_index_c30_enrich_subscription_run": (
                "index_closed_30m_signal_enrichment",
                "source_subscription_run_id",
            ),
            "idx_index_c30_summary_subscription_run": (
                "index_closed_30m_summary",
                "source_subscription_run_id",
            ),
            "idx_index_eod_snapshot_c3_run": ("index_eod_snapshot", "source_c3_run_id"),
            "idx_index_proj_enrich_prev_day_run": (
                "index_projection_enrichment_v4_metric",
                "source_previous_day_minute_run_id",
            ),
            "idx_index_proj_enrich_subscription_run": (
                "index_projection_enrichment_v4_metric",
                "source_subscription_run_id",
            ),
            "idx_index_proj_enrich_today_minute_run": (
                "index_projection_enrichment_v4_metric",
                "source_today_minute_run_id",
            ),
            "idx_index_hint_proj_prev_day_run": (
                "index_realtime_hint_projection_metric",
                "source_previous_day_minute_run_id",
            ),
            "idx_index_hint_proj_subscription_run": (
                "index_realtime_hint_projection_metric",
                "source_subscription_run_id",
            ),
            "idx_stock_acpm_prev_day_run": (
                "stock_action_confirmation_projection_metric",
                "source_previous_day_minute_run_id",
            ),
            "idx_stock_acpm_subscription_run": (
                "stock_action_confirmation_projection_metric",
                "source_subscription_run_id",
            ),
            "idx_stock_acpm_today_minute_run": (
                "stock_action_confirmation_projection_metric",
                "source_today_minute_run_id",
            ),
            "idx_stock_action_fact_market_data_run": ("stock_action_fact", "source_market_data_run_id"),
            "idx_stock_c30_enrich_prev_day_run": (
                "stock_closed_30m_signal_enrichment",
                "source_previous_day_minute_run_id",
            ),
            "idx_stock_c30_enrich_subscription_run": (
                "stock_closed_30m_signal_enrichment",
                "source_subscription_run_id",
            ),
            "idx_stock_c30_summary_subscription_run": (
                "stock_closed_30m_summary",
                "source_subscription_run_id",
            ),
            "idx_stock_eod_snapshot_c3_run": ("stock_eod_snapshot", "source_c3_run_id"),
            "idx_stock_proj_enrich_prev_day_run": (
                "stock_projection_enrichment_v4_metric",
                "source_previous_day_minute_run_id",
            ),
            "idx_stock_proj_enrich_subscription_run": (
                "stock_projection_enrichment_v4_metric",
                "source_subscription_run_id",
            ),
            "idx_stock_proj_enrich_today_minute_run": (
                "stock_projection_enrichment_v4_metric",
                "source_today_minute_run_id",
            ),
        }

        for index_name, (table_name, column_name) in expected_indexes.items():
            self.assertIn(f"create index if not exists {index_name}", migration_sql)
            self.assertIn(f"on {table_name} ({column_name})", migration_sql)

        rollback_drops = {
            line.removeprefix("drop index if exists ").rstrip(";")
            for line in rollback_sql.splitlines()
            if line.startswith("drop index if exists ")
        }
        self.assertEqual(rollback_drops, set(expected_indexes))
        self.assertNotIn("create index", rollback_sql)

        forbidden_tokens = (
            "concurrently",
            "drop table",
            "delete from",
            "update ",
            "insert ",
            "truncate ",
            "macraid",
            "condition_",
            "n1_",
            "n2_",
            "docs/",
            "tmp/",
        )
        for token in forbidden_tokens:
            self.assertNotIn(token, migration_sql)
            self.assertNotIn(token, rollback_sql)

    def test_realtime_snapshot_trade_date_index_migration_draft_is_safe(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        migration = repo_root / "sql" / "runtime_hot_keep5_realtime_snapshot_trade_date_indexes.sql"
        rollback = repo_root / "sql" / "runtime_hot_keep5_realtime_snapshot_trade_date_indexes_rollback.sql"

        self.assertTrue(migration.exists(), migration)
        self.assertTrue(rollback.exists(), rollback)
        migration_sql = migration.read_text(encoding="utf-8").lower()
        rollback_sql = rollback.read_text(encoding="utf-8").lower()
        expected_indexes = {
            "idx_stock_realtime_daily_snapshot_trade_date": ("stock_realtime_daily_snapshot", "trade_date"),
            "idx_index_realtime_daily_snapshot_trade_date": ("index_realtime_daily_snapshot", "trade_date"),
            "idx_board_realtime_daily_snapshot_trade_date": ("board_realtime_daily_snapshot", "trade_date"),
        }

        for index_name, (table_name, column_name) in expected_indexes.items():
            self.assertIn(f"create index if not exists {index_name}", migration_sql)
            self.assertIn(f"on {table_name} ({column_name})", migration_sql)

        rollback_drops = {
            line.removeprefix("drop index if exists ").rstrip(";")
            for line in rollback_sql.splitlines()
            if line.startswith("drop index if exists ")
        }
        self.assertEqual(rollback_drops, set(expected_indexes))
        self.assertNotIn("create index", rollback_sql)

        forbidden_tokens = (
            "concurrently",
            "drop table",
            "delete from",
            "update ",
            "insert ",
            "truncate ",
            "macraid",
            "condition_",
            "n1_",
            "n2_",
            "docs/",
            "tmp/",
        )
        for token in forbidden_tokens:
            self.assertNotIn(token, migration_sql)
            self.assertNotIn(token, rollback_sql)

    def test_discovery_uses_driver_tables_not_large_fact_tables(self) -> None:
        executed_sql: list[str] = []
        case = self

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql, params=None):
                executed_sql.append(sql)
                case.assertNotIn("stock_minute_bar_1m", sql)
                case.assertNotIn("stock_action_confirmation_projection_metric", sql)
                case.assertNotIn("common_trigger_state", sql)
                if "common_market_data_run" in sql:
                    return [("20260612",), ("20260701",)]
                if "common_trigger_run" in sql:
                    return [("20260702",)]
                if "common_action_run" in sql:
                    return []
                if "common_event_outbox" in sql:
                    return [("20260703",)]
                return []

        dates = discover_hot_trade_dates(connection_factory=lambda _dsn: FakeConnection(), dsn="unused")

        self.assertEqual(dates, ["20260612", "20260701", "20260702", "20260703"])
        self.assertTrue(any("common_market_data_run" in sql for sql in executed_sql))
        self.assertTrue(any("common_trigger_run" in sql for sql in executed_sql))
        self.assertTrue(any("common_action_run" in sql for sql in executed_sql))
        self.assertTrue(any("common_event_outbox" in sql for sql in executed_sql))

    def test_keep2_plan_retains_latest_two_trade_dates(self) -> None:
        rows = {
            ("n3", "stock_minute_bar_1m", "20260612"): 10,
            ("n4", "common_trigger_state", "20260612"): 3,
            ("n3", "stock_minute_bar_1m", "20260701"): 99,
            ("n4", "common_trigger_state", "20260702"): 88,
        }

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260615", "20260701", "20260702"],
                table_counter=lambda spec, trade_date: rows.get((spec.layer, spec.table, trade_date), 0),
                plan_path=Path(tmp) / "plan.json",
            )

        self.assertEqual(plan["result"], "DIRTY_HOT_KEEP2_CLEANUP_PLAN_PASS")
        self.assertEqual(plan["retained_trade_dates"], ["20260701", "20260702"])
        self.assertEqual(plan["cleanup_trade_dates"], ["20260612", "20260615"])
        self.assertNotIn("20260701", plan["cleanup_trade_dates"])
        self.assertNotIn("20260702", plan["cleanup_trade_dates"])
        self.assertFalse(plan["cleanup_executed"])
        self.assertFalse(plan["side_effects"]["writes_database"])
        self.assertIn(
            {"trade_date": "20260612", "layer": "n3", "table": "stock_minute_bar_1m", "planned_delete_rows": 10},
            plan["table_delete_plan"],
        )
        self.assertTrue(plan["count_timings"])

    def test_plan_includes_closed_30m_tables_for_cleanup_dates_only(self) -> None:
        def counter(spec, trade_date):
            if trade_date == "20260612" and spec.table in CLOSED_30M_TABLES:
                return 1
            if trade_date == "20260701" and spec.table in CLOSED_30M_TABLES:
                return 99
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                table_counter=counter,
                plan_path=Path(tmp) / "plan.json",
            )

        planned_tables = {
            item["table"]
            for item in plan["table_delete_plan"]
            if item["trade_date"] == "20260612" and item["layer"] == "n3"
        }
        self.assertTrue(CLOSED_30M_TABLES <= planned_tables)
        self.assertFalse(any(item["trade_date"] == "20260701" for item in plan["table_delete_plan"]))
        self.assertFalse(any(item["trade_date"] == "20260702" for item in plan["table_delete_plan"]))

    def test_plan_includes_eod_snapshot_tables_for_cleanup_dates_only(self) -> None:
        def counter(spec, trade_date):
            if trade_date == "20260612" and spec.table in EOD_SNAPSHOT_TABLES:
                return 1
            if trade_date == "20260701" and spec.table in EOD_SNAPSHOT_TABLES:
                return 99
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                table_counter=counter,
                plan_path=Path(tmp) / "plan.json",
            )

        planned_tables = {
            item["table"]
            for item in plan["table_delete_plan"]
            if item["trade_date"] == "20260612" and item["layer"] == "n3"
        }
        self.assertTrue(EOD_SNAPSHOT_TABLES <= planned_tables)
        self.assertFalse(any(item["trade_date"] == "20260701" for item in plan["table_delete_plan"]))
        self.assertFalse(any(item["trade_date"] == "20260702" for item in plan["table_delete_plan"]))

    def test_plan_includes_eod_reconciliation_item_tables_for_cleanup_dates_only(self) -> None:
        def counter(spec, trade_date):
            if trade_date == "20260612" and spec.table in EOD_RECONCILIATION_ITEM_TABLES:
                return 1
            if trade_date == "20260701" and spec.table in EOD_RECONCILIATION_ITEM_TABLES:
                return 99
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                table_counter=counter,
                plan_path=Path(tmp) / "plan.json",
            )

        planned_tables = {
            item["table"]
            for item in plan["table_delete_plan"]
            if item["trade_date"] == "20260612" and item["layer"] == "n3"
        }
        self.assertTrue(EOD_RECONCILIATION_ITEM_TABLES <= planned_tables)
        self.assertFalse(any(item["trade_date"] == "20260701" for item in plan["table_delete_plan"]))
        self.assertFalse(any(item["trade_date"] == "20260702" for item in plan["table_delete_plan"]))

    def test_plan_includes_projection_enrichment_v4_tables_for_cleanup_dates_only(self) -> None:
        def counter(spec, trade_date):
            if trade_date == "20260612" and spec.table in PROJECTION_ENRICHMENT_V4_TABLES:
                return 1
            if trade_date == "20260701" and spec.table in PROJECTION_ENRICHMENT_V4_TABLES:
                return 99
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                table_counter=counter,
                plan_path=Path(tmp) / "plan.json",
            )

        planned_tables = {
            item["table"]
            for item in plan["table_delete_plan"]
            if item["trade_date"] == "20260612" and item["layer"] == "n3"
        }
        self.assertTrue(PROJECTION_ENRICHMENT_V4_TABLES <= planned_tables)
        self.assertFalse(any(item["trade_date"] == "20260701" for item in plan["table_delete_plan"]))
        self.assertFalse(any(item["trade_date"] == "20260702" for item in plan["table_delete_plan"]))

    def test_plan_includes_realtime_hint_projection_metric_tables_for_cleanup_dates_only(self) -> None:
        def counter(spec, trade_date):
            if trade_date == "20260612" and spec.table in REALTIME_HINT_PROJECTION_METRIC_TABLES:
                return 1
            if trade_date == "20260701" and spec.table in REALTIME_HINT_PROJECTION_METRIC_TABLES:
                return 99
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                table_counter=counter,
                plan_path=Path(tmp) / "plan.json",
            )

        planned_tables = {
            item["table"]
            for item in plan["table_delete_plan"]
            if item["trade_date"] == "20260612" and item["layer"] == "n3"
        }
        self.assertTrue(REALTIME_HINT_PROJECTION_METRIC_TABLES <= planned_tables)
        self.assertFalse(any(item["trade_date"] == "20260701" for item in plan["table_delete_plan"]))
        self.assertFalse(any(item["trade_date"] == "20260702" for item in plan["table_delete_plan"]))

    def test_cleanup_deletes_closed_30m_children_before_market_data_run(self) -> None:
        specs = build_hot_cleanup_specs()
        names = [(spec.layer, spec.table) for spec in specs]
        market_data_run_index = names.index(("n3", "common_market_data_run"))

        for table in CLOSED_30M_TABLES:
            self.assertLess(names.index(("n3", table)), market_data_run_index)

        for table in CLOSED_30M_SUMMARY_TABLES:
            asset = table.removesuffix("_closed_30m_summary")
            enrichment_table = f"{asset}_closed_30m_signal_enrichment"
            self.assertLess(names.index(("n3", enrichment_table)), names.index(("n3", table)))

    def test_cleanup_deletes_eod_snapshot_before_market_data_run(self) -> None:
        specs = build_hot_cleanup_specs()
        names = [(spec.layer, spec.table) for spec in specs]
        market_data_run_index = names.index(("n3", "common_market_data_run"))

        for table in EOD_SNAPSHOT_TABLES:
            self.assertLess(names.index(("n3", table)), market_data_run_index)

    def test_cleanup_deletes_eod_reconciliation_items_before_eod_snapshot(self) -> None:
        specs = build_hot_cleanup_specs()
        names = [(spec.layer, spec.table) for spec in specs]

        for table in EOD_RECONCILIATION_ITEM_TABLES:
            asset = table.removesuffix("_eod_reconciliation_item")
            parent_table = f"{asset}_eod_snapshot"
            self.assertLess(names.index(("n3", table)), names.index(("n3", parent_table)))

    def test_cleanup_deletes_projection_enrichment_v4_before_realtime_snapshot_and_market_data_run(self) -> None:
        specs = build_hot_cleanup_specs()
        names = [(spec.layer, spec.table) for spec in specs]
        market_data_run_index = names.index(("n3", "common_market_data_run"))

        for table in PROJECTION_ENRICHMENT_V4_TABLES:
            asset = table.removesuffix("_projection_enrichment_v4_metric")
            snapshot_table = f"{asset}_realtime_daily_snapshot"
            self.assertLess(names.index(("n3", table)), names.index(("n3", snapshot_table)))
            self.assertLess(names.index(("n3", table)), market_data_run_index)

    def test_cleanup_deletes_realtime_hint_projection_metric_before_market_data_run(self) -> None:
        specs = build_hot_cleanup_specs()
        names = [(spec.layer, spec.table) for spec in specs]
        market_data_run_index = names.index(("n3", "common_market_data_run"))

        for table in REALTIME_HINT_PROJECTION_METRIC_TABLES:
            self.assertLess(names.index(("n3", table)), market_data_run_index)

    def test_plan_blocks_with_slow_table_evidence_when_count_times_out(self) -> None:
        def counter(spec, trade_date):
            if spec.table == "stock_minute_bar_1m" and trade_date == "20260612":
                raise TimeoutError("statement timeout")
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                table_counter=counter,
                plan_path=Path(tmp) / "plan.json",
            )

        self.assertEqual(plan["result"], "DIRTY_HOT_KEEP2_CLEANUP_PLAN_BLOCKED")
        self.assertEqual(plan["slow_or_blocked_table"]["trade_date"], "20260612")
        self.assertEqual(plan["slow_or_blocked_table"]["layer"], "n3")
        self.assertEqual(plan["slow_or_blocked_table"]["table"], "stock_minute_bar_1m")
        self.assertIn("statement timeout", plan["slow_or_blocked_table"]["error"])
        self.assertTrue(any(row["status"] == "blocked" for row in plan["count_timings"]))

    def test_event_inbox_cleanup_uses_bounded_join_sql(self) -> None:
        inbox_template = next(
            spec
            for spec in build_hot_cleanup_specs()
            if spec.layer == "n4" and spec.table == "common_event_inbox"
        )
        bound = bind_cleanup_spec(inbox_template, "20260622")

        self.assertEqual(bound.batch_strategy, "event_id_chunks")
        self.assertIn("from common_event_outbox", bound.batch_source_sql or "")
        self.assertIn("trade_date = %s and source_layer = %s", bound.batch_source_sql or "")
        self.assertIn("event_id = any(%s)", bound.count_sql)
        self.assertNotIn("exists (select 1 from common_event_outbox", bound.count_sql)
        self.assertIn("event_id = any(%s)", bound.delete_sql)
        self.assertNotIn("exists (select 1 from common_event_outbox", bound.delete_sql)
        self.assertEqual(bound.params, ("20260622", "N4_trigger"))

    def test_event_inbox_uses_event_id_chunk_batches_for_count(self) -> None:
        fake_conn = _FakeCleanupConnection(
            event_ids_by_date_layer={("20260612", "N4_trigger"): ["evt-a", "evt-b", "evt-c"]},
            counts_by_batch={"event_ids:evt-a,evt-b,evt-c": 3},
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )

        row = next(
            item
            for item in plan["table_delete_plan"]
            if item["trade_date"] == "20260612" and item["layer"] == "n4" and item["table"] == "common_event_inbox"
        )
        self.assertEqual(row["planned_delete_rows"], 3)
        inbox_calls = [call for call in fake_conn.count_calls if "from common_event_inbox" in call[0]]
        self.assertEqual(len(inbox_calls), 1)
        self.assertIn("where source_layer = %s and event_id = any(%s)", inbox_calls[0][0])
        self.assertNotIn("join common_event_outbox", inbox_calls[0][0])
        self.assertEqual(inbox_calls[0][1], ("N4_trigger", ["evt-a", "evt-b", "evt-c"]))
        self.assertTrue(fake_conn.batch_source_calls)
        self.assertIn("from common_event_outbox", fake_conn.batch_source_calls[0][0])
        self.assertIn("trade_date = %s and source_layer = %s", fake_conn.batch_source_calls[0][0])

    def test_event_outbox_uses_event_id_chunk_batches_for_count_and_delete(self) -> None:
        outbox_template = next(
            spec
            for spec in build_hot_cleanup_specs()
            if spec.layer == "n4" and spec.table == "common_event_outbox"
        )
        bound = bind_cleanup_spec(outbox_template, "20260612")

        self.assertEqual(bound.batch_strategy, "event_id_chunks")
        self.assertIn("from common_event_outbox", bound.batch_source_sql or "")
        self.assertIn("trade_date = %s and source_layer = %s", bound.batch_source_sql or "")
        self.assertIn("event_id = any(%s)", bound.count_sql)
        self.assertIn("event_id = any(%s)", bound.delete_sql)
        self.assertNotIn("where trade_date = %s and source_layer = %s", bound.delete_sql)
        self.assertEqual(bound.params, ("20260612", "N4_trigger"))

    def test_event_inbox_batch_source_retries_transient_timeout_twice(self) -> None:
        fake_conn = _FakeCleanupConnection(
            event_ids_by_date_layer={("20260612", "N4_trigger"): ["evt-a", "evt-b", "evt-c"]},
            transient_event_source_errors_by_date_layer={
                ("20260612", "N4_trigger"): [
                    TimeoutError("statement timeout"),
                    TimeoutError("statement timeout"),
                ]
            },
            counts_by_batch={"event_ids:evt-a,evt-b,evt-c": 3},
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )

        row = next(
            item
            for item in plan["table_delete_plan"]
            if item["trade_date"] == "20260612" and item["layer"] == "n4" and item["table"] == "common_event_inbox"
        )
        self.assertEqual(row["planned_delete_rows"], 3)
        self.assertEqual(
            sum(1 for _sql, params in fake_conn.batch_source_calls if params == ("20260612", "N4_trigger")),
            4,
        )
        self.assertFalse(plan["blockers"])

    def test_event_inbox_event_id_chunk_size_is_250(self) -> None:
        self.assertEqual(EVENT_ID_BATCH_SIZE, 250)

    def test_trigger_state_id_chunk_size_is_1000(self) -> None:
        self.assertEqual(TRIGGER_STATE_ID_CHUNK_SIZE, 1_000)

    def test_count_statement_timeout_is_bounded_at_30_seconds(self) -> None:
        self.assertEqual(COUNT_STATEMENT_TIMEOUT_MS, 30_000)

    def test_delete_statement_timeout_is_bounded_at_30_seconds(self) -> None:
        self.assertEqual(DELETE_STATEMENT_TIMEOUT_MS, 30_000)

    def test_event_inbox_splits_1000_event_ids_into_250_id_chunks(self) -> None:
        event_ids = [f"evt-{index:04d}" for index in range(1000)]
        expected_batch_keys = [
            "event_ids:" + ",".join(event_ids[start : start + 250])
            for start in range(0, 1000, 250)
        ]
        current_1000_key = "event_ids:" + ",".join(event_ids)
        fake_conn = _FakeCleanupConnection(
            event_ids_by_date_layer={("20260612", "N4_trigger"): event_ids},
            counts_by_batch={**{batch_key: 250 for batch_key in expected_batch_keys}, current_1000_key: 1000},
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )

        row = next(
            item
            for item in plan["table_delete_plan"]
            if item["trade_date"] == "20260612" and item["layer"] == "n4" and item["table"] == "common_event_inbox"
        )
        self.assertEqual(row["planned_delete_rows"], 1000)
        inbox_calls = [call for call in fake_conn.count_calls if "from common_event_inbox" in call[0]]
        self.assertEqual(len(inbox_calls), 4)
        self.assertEqual(inbox_calls[0][1], ("N4_trigger", event_ids[:250]))
        self.assertEqual(inbox_calls[1][1], ("N4_trigger", event_ids[250:500]))
        self.assertEqual(inbox_calls[2][1], ("N4_trigger", event_ids[500:750]))
        self.assertEqual(inbox_calls[3][1], ("N4_trigger", event_ids[750:1000]))

    def test_event_infra_execute_deletes_event_id_chunks_before_outbox(self) -> None:
        fake_conn = _FakeCleanupConnection(
            event_ids_by_date_layer={("20260612", "N4_trigger"): ["evt-a", "evt-b", "evt-c"]},
            counts_by_batch={"event_ids:evt-a,evt-b,evt-c": 3},
            deleted_by_batch={"event_ids:evt-a,evt-b,evt-c": 3},
        )

        with tempfile.TemporaryDirectory() as tmp:
            build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )
            result = execute_keep2_dirty_hot_cleanup(
                plan_path=Path(tmp) / "plan.json",
                confirm_token=CONFIRM_TOKEN,
                current_trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                closeout_path=Path(tmp) / "closeout.json",
            )

        self.assertEqual(result["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        n4_inbox_index = next(
            index
            for index, (sql, params) in enumerate(fake_conn.delete_calls)
            if _table_name_from_sql(sql) == "common_event_inbox" and params[0] == "N4_trigger"
        )
        n4_outbox_index = next(
            index
            for index, (sql, params) in enumerate(fake_conn.delete_calls)
            if _table_name_from_sql(sql) == "common_event_outbox" and params[0] == "N4_trigger"
        )
        self.assertLess(n4_inbox_index, n4_outbox_index)
        inbox_deletes = [call for call in fake_conn.delete_calls if "common_event_inbox" in call[0]]
        self.assertEqual(len(inbox_deletes), 1)
        self.assertIn("where source_layer = %s and event_id = any(%s)", inbox_deletes[0][0])
        self.assertEqual(inbox_deletes[0][1], ("N4_trigger", ["evt-a", "evt-b", "evt-c"]))
        outbox_deletes = [call for call in fake_conn.delete_calls if "common_event_outbox" in call[0]]
        self.assertEqual(len(outbox_deletes), 1)
        self.assertIn("where source_layer = %s and event_id = any(%s)", outbox_deletes[0][0])
        self.assertEqual(outbox_deletes[0][1], ("N4_trigger", ["evt-a", "evt-b", "evt-c"]))
        self.assertFalse(
            any(
                _table_name_from_sql(sql) == "common_event_outbox" and params == ("20260612", "N4_trigger")
                for sql, params in fake_conn.delete_calls
            )
        )

    def test_event_inbox_batch_timeout_reports_chunk_evidence(self) -> None:
        fake_conn = _FakeCleanupConnection(
            event_ids_by_date_layer={("20260612", "N4_trigger"): ["evt-a", "evt-b"]},
            errors_by_batch={"event_ids:evt-a,evt-b": TimeoutError("statement timeout")},
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )

        self.assertEqual(plan["result"], "DIRTY_HOT_KEEP2_CLEANUP_PLAN_BLOCKED")
        self.assertEqual(plan["slow_or_blocked_table"]["table"], "common_event_inbox")
        self.assertEqual(plan["slow_or_blocked_table"]["batch_label"], "event_id_chunk:00000")
        self.assertIn("statement timeout", plan["slow_or_blocked_table"]["error"])

    def test_event_inbox_batch_timeout_reports_250_id_chunk_evidence(self) -> None:
        event_ids = [f"evt-{index:04d}" for index in range(1000)]
        first_batch = "event_ids:" + ",".join(event_ids[:250])
        second_batch = "event_ids:" + ",".join(event_ids[250:500])
        current_1000_key = "event_ids:" + ",".join(event_ids)
        fake_conn = _FakeCleanupConnection(
            event_ids_by_date_layer={("20260612", "N4_trigger"): event_ids},
            counts_by_batch={first_batch: 250},
            errors_by_batch={
                second_batch: TimeoutError("statement timeout"),
                current_1000_key: TimeoutError("statement timeout"),
            },
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )

        self.assertEqual(plan["result"], "DIRTY_HOT_KEEP2_CLEANUP_PLAN_BLOCKED")
        self.assertEqual(plan["slow_or_blocked_table"]["table"], "common_event_inbox")
        self.assertEqual(plan["slow_or_blocked_table"]["batch_label"], "event_id_chunk:00001")
        self.assertEqual(plan["slow_or_blocked_table"]["batch_start"], "evt-0250")
        self.assertEqual(plan["slow_or_blocked_table"]["batch_end"], "evt-0499")

    def test_common_trigger_match_uses_trigger_run_id_batches_for_count(self) -> None:
        template = next(
            spec
            for spec in build_hot_cleanup_specs()
            if spec.layer == "n4" and spec.table == "common_trigger_match"
        )
        bound = bind_cleanup_spec(template, "20260612")

        self.assertEqual(bound.batch_strategy, "trigger_run_id")
        self.assertEqual(bound.batch_column, "run_id")
        self.assertIn("from common_trigger_run", bound.batch_source_sql or "")
        self.assertIn("for_trade_date = %s", bound.batch_source_sql or "")
        self.assertEqual(bound.count_sql, "select count(*) from common_trigger_match where run_id = %s")
        self.assertEqual(bound.delete_sql, "delete from common_trigger_match where run_id = %s")
        self.assertEqual(bound.params, ("20260612",))

        fake_conn = _FakeCleanupConnection(
            trigger_run_ids_by_date={"20260612": ["trigger-run-a", "trigger-run-b"]},
            counts_by_batch={"trigger-run-a": 5, "trigger-run-b": 7},
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )

        row = next(
            item
            for item in plan["table_delete_plan"]
            if item["trade_date"] == "20260612" and item["layer"] == "n4" and item["table"] == "common_trigger_match"
        )
        self.assertEqual(row["planned_delete_rows"], 12)
        match_calls = [call for call in fake_conn.count_calls if "from common_trigger_match" in call[0]]
        self.assertEqual(len(match_calls), 2)
        self.assertTrue(all("where run_id = %s" in sql for sql, _params in match_calls))
        self.assertFalse(any("for_trade_date = %s" in sql for sql, _params in match_calls))
        self.assertEqual([params for _sql, params in match_calls], [("trigger-run-a",), ("trigger-run-b",)])
        trigger_source_calls = [
            call for call in fake_conn.batch_source_calls if "select run_id from common_trigger_run" in call[0]
        ]
        self.assertTrue(trigger_source_calls)
        self.assertTrue(all("where for_trade_date = %s" in sql for sql, _params in trigger_source_calls))

    def test_common_trigger_state_uses_trigger_state_id_chunks_for_count(self) -> None:
        template = next(
            spec
            for spec in build_hot_cleanup_specs()
            if spec.layer == "n4" and spec.table == "common_trigger_state"
        )
        bound = bind_cleanup_spec(template, "20260612")

        self.assertEqual(bound.batch_strategy, "trigger_state_id_chunks")
        self.assertEqual(bound.batch_column, "trigger_state_id")
        self.assertIn("from common_trigger_state", bound.batch_source_sql or "")
        self.assertIn("common_trigger_run", bound.batch_source_sql or "")
        self.assertEqual(
            bound.count_sql,
            "select count(*) from common_trigger_state "
            "where run_id = %s and trigger_state_id >= %s and trigger_state_id <= %s",
        )
        self.assertEqual(
            bound.delete_sql,
            "delete from common_trigger_state "
            "where run_id = %s and trigger_state_id >= %s and trigger_state_id <= %s",
        )
        self.assertEqual(bound.params, ("20260612",))

        trigger_state_rows = [
            ("trigger-run-a", 1),
            ("trigger-run-a", 2),
            ("trigger-run-b", 10),
        ]
        fake_conn = _FakeCleanupConnection(
            trigger_state_ids_by_date={"20260612": trigger_state_rows},
            counts_by_batch={"trigger-run-a:1->2": 2, "trigger-run-b:10->10": 1},
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )

        row = next(
            item
            for item in plan["table_delete_plan"]
            if item["trade_date"] == "20260612" and item["layer"] == "n4" and item["table"] == "common_trigger_state"
        )
        self.assertEqual(row["planned_delete_rows"], 3)
        state_calls = [call for call in fake_conn.count_calls if "from common_trigger_state" in call[0]]
        self.assertEqual(len(state_calls), 2)
        self.assertTrue(all("trigger_state_id >=" in sql for sql, _params in state_calls))
        self.assertEqual([params for _sql, params in state_calls], [("trigger-run-a", 1, 2), ("trigger-run-b", 10, 10)])
        self.assertTrue(
            any("select s.run_id, s.trigger_state_id from common_trigger_state" in sql for sql, _params in fake_conn.batch_source_calls)
        )

    def test_common_trigger_match_execute_deletes_run_id_batches_before_trigger_run(self) -> None:
        counts = {"trigger-run-a": 5, "trigger-run-b": 7}
        fake_conn = _FakeCleanupConnection(
            trigger_run_ids_by_date={"20260612": ["trigger-run-a", "trigger-run-b"]},
            counts_by_batch=counts,
            deleted_by_batch=counts,
            counts_by_table={"common_trigger_run": 1},
            deleted_by_table={"common_trigger_run": 1},
        )

        with tempfile.TemporaryDirectory() as tmp:
            build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )
            result = execute_keep2_dirty_hot_cleanup(
                plan_path=Path(tmp) / "plan.json",
                confirm_token=CONFIRM_TOKEN,
                current_trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                closeout_path=Path(tmp) / "closeout.json",
            )

        self.assertEqual(result["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        deleted_tables = [_table_name_from_sql(sql) for sql, _params in fake_conn.delete_calls]
        match_indexes = [index for index, table in enumerate(deleted_tables) if table == "common_trigger_match"]
        trigger_run_index = deleted_tables.index("common_trigger_run")
        self.assertEqual(len(match_indexes), 2)
        self.assertTrue(all(index < trigger_run_index for index in match_indexes))
        match_deletes = [call for call in fake_conn.delete_calls if "common_trigger_match" in call[0]]
        self.assertEqual([params for _sql, params in match_deletes], [("trigger-run-a",), ("trigger-run-b",)])
        self.assertTrue(all("where run_id = %s" in sql for sql, _params in match_deletes))

    def test_common_trigger_state_execute_deletes_trigger_state_id_chunks_before_trigger_run(self) -> None:
        trigger_state_rows = [
            ("trigger-run-a", 1),
            ("trigger-run-a", 2),
            ("trigger-run-b", 10),
        ]
        counts = {"trigger-run-a:1->2": 2, "trigger-run-b:10->10": 1}
        fake_conn = _FakeCleanupConnection(
            trigger_state_ids_by_date={"20260612": trigger_state_rows},
            counts_by_batch=counts,
            deleted_by_batch=counts,
            counts_by_table={"common_trigger_run": 1},
            deleted_by_table={"common_trigger_run": 1},
        )

        with tempfile.TemporaryDirectory() as tmp:
            build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )
            result = execute_keep2_dirty_hot_cleanup(
                plan_path=Path(tmp) / "plan.json",
                confirm_token=CONFIRM_TOKEN,
                current_trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                closeout_path=Path(tmp) / "closeout.json",
            )

        self.assertEqual(result["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        deleted_tables = [_table_name_from_sql(sql) for sql, _params in fake_conn.delete_calls]
        state_indexes = [index for index, table in enumerate(deleted_tables) if table == "common_trigger_state"]
        trigger_run_index = deleted_tables.index("common_trigger_run")
        self.assertEqual(len(state_indexes), 2)
        self.assertTrue(all(index < trigger_run_index for index in state_indexes))
        state_deletes = [call for call in fake_conn.delete_calls if "common_trigger_state" in call[0]]
        self.assertEqual(
            [params for _sql, params in state_deletes],
            [("trigger-run-a", 1, 2), ("trigger-run-b", 10, 10)],
        )
        self.assertTrue(all("trigger_state_id >=" in sql for sql, _params in state_deletes))

    def test_execute_can_limit_delete_units_for_resumable_cleanup(self) -> None:
        fake_conn = _FakeCleanupConnection(
            counts_by_table={
                "common_action_run": 1,
                "common_trigger_run": 1,
                "common_market_data_run": 1,
            },
            deleted_by_table={
                "common_action_run": 1,
                "common_trigger_run": 1,
                "common_market_data_run": 1,
            },
        )

        with tempfile.TemporaryDirectory() as tmp:
            build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )
            result = execute_keep2_dirty_hot_cleanup(
                plan_path=Path(tmp) / "plan.json",
                confirm_token=CONFIRM_TOKEN,
                current_trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                closeout_path=Path(tmp) / "closeout.json",
                max_delete_units=2,
            )

        self.assertEqual(result["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PARTIAL_PASS")
        self.assertTrue(result["cleanup_executed"])
        self.assertFalse(result["cleanup_complete"])
        self.assertTrue(result["resume_required"])
        self.assertEqual(result["delete_units_executed"], 2)
        self.assertEqual(result["delete_units_total"], 3)
        self.assertEqual(result["delete_units_remaining"], 1)
        self.assertEqual(len(fake_conn.delete_calls), 2)

    def test_common_trigger_match_batch_timeout_reports_run_id_evidence(self) -> None:
        fake_conn = _FakeCleanupConnection(
            trigger_run_ids_by_date={"20260612": ["trigger-run-a", "trigger-run-b"]},
            errors_by_batch={"trigger-run-b": TimeoutError("statement timeout")},
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )

        self.assertEqual(plan["result"], "DIRTY_HOT_KEEP2_CLEANUP_PLAN_BLOCKED")
        self.assertEqual(plan["slow_or_blocked_table"]["table"], "common_trigger_match")
        self.assertEqual(plan["slow_or_blocked_table"]["batch_label"], "trigger_run_id:trigger-run-b")
        self.assertIn("statement timeout", plan["slow_or_blocked_table"]["error"])

    def test_market_data_subscription_uses_market_data_run_id_batches(self) -> None:
        template = next(
            spec
            for spec in build_hot_cleanup_specs()
            if spec.layer == "n3" and spec.table == "common_market_data_subscription"
        )
        bound = bind_cleanup_spec(template, "20260612")

        self.assertEqual(bound.batch_strategy, "market_data_run_id")
        self.assertEqual(bound.batch_column, "run_id")
        self.assertIn("select run_id from common_market_data_run", bound.batch_source_sql or "")
        self.assertIn("where for_trade_date = %s", bound.batch_source_sql or "")
        self.assertEqual(bound.count_sql, "select count(*) from common_market_data_subscription where run_id = %s")
        self.assertEqual(bound.delete_sql, "delete from common_market_data_subscription where run_id = %s")
        self.assertEqual(bound.params, ("20260612",))

        fake_conn = _FakeCleanupConnection(
            market_data_run_ids_by_date={"20260612": ["market-run-a", "market-run-b"]},
            counts_by_batch={"market-run-a": 11, "market-run-b": 13},
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )

        row = next(
            item
            for item in plan["table_delete_plan"]
            if item["trade_date"] == "20260612"
            and item["layer"] == "n3"
            and item["table"] == "common_market_data_subscription"
        )
        self.assertEqual(row["planned_delete_rows"], 24)
        subscription_calls = [
            call for call in fake_conn.count_calls if "from common_market_data_subscription where" in call[0]
        ]
        self.assertEqual(len(subscription_calls), 2)
        self.assertTrue(all("where run_id = %s" in sql for sql, _params in subscription_calls))
        self.assertEqual([params for _sql, params in subscription_calls], [("market-run-a",), ("market-run-b",)])

    def test_market_data_subscription_execute_deletes_run_id_batches_before_market_data_run(self) -> None:
        counts = {"market-run-a": 11, "market-run-b": 13}
        fake_conn = _FakeCleanupConnection(
            market_data_run_ids_by_date={"20260612": ["market-run-a", "market-run-b"]},
            counts_by_batch=counts,
            deleted_by_batch=counts,
            counts_by_table={"common_market_data_run": 2},
            deleted_by_table={"common_market_data_run": 2},
        )

        with tempfile.TemporaryDirectory() as tmp:
            build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )
            result = execute_keep2_dirty_hot_cleanup(
                plan_path=Path(tmp) / "plan.json",
                confirm_token=CONFIRM_TOKEN,
                current_trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                closeout_path=Path(tmp) / "closeout.json",
            )

        self.assertEqual(result["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        deleted_tables = [_table_name_from_sql(sql) for sql, _params in fake_conn.delete_calls]
        subscription_indexes = [
            index for index, table in enumerate(deleted_tables) if table == "common_market_data_subscription"
        ]
        market_data_run_index = deleted_tables.index("common_market_data_run")
        self.assertEqual(len(subscription_indexes), 2)
        self.assertTrue(all(index < market_data_run_index for index in subscription_indexes))
        subscription_deletes = [
            call for call in fake_conn.delete_calls if "common_market_data_subscription" in call[0]
        ]
        self.assertEqual([params for _sql, params in subscription_deletes], [("market-run-a",), ("market-run-b",)])
        self.assertTrue(all("where run_id = %s" in sql for sql, _params in subscription_deletes))

    def test_execute_uses_global_spec_order_across_cleanup_dates_for_cross_date_fk_refs(self) -> None:
        counts = {
            ("20260617", "common_market_data_run"): 1,
            ("20260618", "index_action_confirmation_projection_metric"): 1,
        }
        delete_order: list[tuple[str, str]] = []

        def counter(spec, trade_date):
            return counts.get((trade_date, spec.table), 0)

        def deleter(spec, trade_date):
            delete_order.append((trade_date, spec.table))
            return counter(spec, trade_date)

        with tempfile.TemporaryDirectory() as tmp:
            build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260617", "20260618", "20260701", "20260702"],
                table_counter=counter,
                plan_path=Path(tmp) / "plan.json",
            )
            result = execute_keep2_dirty_hot_cleanup(
                plan_path=Path(tmp) / "plan.json",
                confirm_token=CONFIRM_TOKEN,
                current_trade_dates=["20260617", "20260618", "20260701", "20260702"],
                table_counter=counter,
                table_deleter=deleter,
                closeout_path=Path(tmp) / "closeout.json",
            )

        self.assertEqual(result["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        self.assertLess(
            delete_order.index(("20260618", "index_action_confirmation_projection_metric")),
            delete_order.index(("20260617", "common_market_data_run")),
        )

    def test_trigger_replay_audit_specs_are_before_trigger_run(self) -> None:
        specs = list(build_hot_cleanup_specs())
        names = [(spec.layer, spec.table) for spec in specs]

        replay_tables = {
            "stock_trigger_replay_audit",
            "index_trigger_replay_audit",
            "board_trigger_replay_audit",
        }
        trigger_run_index = names.index(("n4", "common_trigger_run"))
        for table in replay_tables:
            index = names.index(("n4", table))
            self.assertLess(index, trigger_run_index)
            bound = bind_cleanup_spec(specs[index], "20260612")
            self.assertIn("for_trade_date = %s", bound.count_sql)
            self.assertIn("trade_date = %s", bound.count_sql)
            self.assertIn("for_trade_date = %s", bound.delete_sql)
            self.assertIn("trade_date = %s", bound.delete_sql)
            self.assertEqual(bound.params, ("20260612", "20260612"))

    def test_execute_deletes_trigger_replay_audit_before_trigger_run(self) -> None:
        deleted: list[tuple[str, str, str]] = []
        replay_tables = {
            "stock_trigger_replay_audit",
            "index_trigger_replay_audit",
            "board_trigger_replay_audit",
        }

        def counter(spec, trade_date):
            if trade_date == "20260612" and spec.layer == "n4" and spec.table in replay_tables | {"common_trigger_run"}:
                return 1
            return 0

        def deleter(spec, trade_date):
            deleted.append((trade_date, spec.layer, spec.table))
            return counter(spec, trade_date)

        with tempfile.TemporaryDirectory() as tmp:
            build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                table_counter=counter,
                plan_path=Path(tmp) / "plan.json",
            )
            result = execute_keep2_dirty_hot_cleanup(
                plan_path=Path(tmp) / "plan.json",
                confirm_token=CONFIRM_TOKEN,
                current_trade_dates=["20260612", "20260701", "20260702"],
                table_counter=counter,
                table_deleter=deleter,
            )

        self.assertEqual(result["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        deleted_tables = [item[2] for item in deleted]
        trigger_run_index = deleted_tables.index("common_trigger_run")
        for table in replay_tables:
            self.assertIn(table, deleted_tables)
            self.assertLess(deleted_tables.index(table), trigger_run_index)

    def test_stock_minute_bar_uses_intraday_batch_metadata(self) -> None:
        template = next(
            spec
            for spec in build_hot_cleanup_specs()
            if spec.layer == "n3" and spec.table == "stock_minute_bar_1m"
        )

        self.assertEqual(template.batch_column, "bar_time")
        self.assertEqual(template.batch_strategy, "intraday_time_windows_stock_1m")
        self.assertEqual(len(template.batches), 242)
        self.assertTrue(all(batch.start_time >= "09:30:00" for batch in template.batches))

    def test_stock_minute_bar_plan_counts_intraday_batches(self) -> None:
        fake_conn = _FakeCleanupConnection(counts_by_batch=_stock_1m_time_counts())

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )

        row = next(
            item
            for item in plan["table_delete_plan"]
            if item["trade_date"] == "20260612" and item["layer"] == "n3" and item["table"] == "stock_minute_bar_1m"
        )
        self.assertEqual(row["planned_delete_rows"], 242)
        stock_calls = [call for call in fake_conn.count_calls if "stock_minute_bar_1m" in call[0]]
        self.assertEqual(len(stock_calls), 242)
        self.assertTrue(all("bar_time >=" in sql and "bar_time <" in sql for sql, _params in stock_calls))
        self.assertFalse(any("09:00:00+08" in str(params) or "09:15:00+08" in str(params) for _sql, params in stock_calls))
        self.assertTrue(any("10:30:00+08" in str(params) and "10:31:00+08" in str(params) for _sql, params in stock_calls))
        self.assertTrue(any("10:34:00+08" in str(params) and "10:35:00+08" in str(params) for _sql, params in stock_calls))
        self.assertFalse(any("10:30:00+08" in str(params) and "10:35:00+08" in str(params) for _sql, params in stock_calls))
        batch_timings = [
            item
            for item in plan["count_timings"]
            if item["trade_date"] == "20260612" and item["layer"] == "n3" and item["table"] == "stock_minute_bar_1m"
        ]
        self.assertEqual(len(batch_timings), 242)
        self.assertTrue(all(item.get("batch_label") for item in batch_timings))

    def test_stock_minute_bar_plan_retries_transient_batch_timeout_twice(self) -> None:
        counts = _stock_1m_time_counts()
        batch_key = "2026-06-12 09:31:00+08->2026-06-12 09:32:00+08"
        fake_conn = _FakeCleanupConnection(
            counts_by_batch=counts,
            transient_errors_by_table_batch={
                ("stock_minute_bar_1m", batch_key): [
                    TimeoutError("statement timeout"),
                    TimeoutError("statement timeout"),
                ],
            },
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )

        self.assertEqual(plan["result"], "DIRTY_HOT_KEEP2_CLEANUP_PLAN_PASS")
        stock_calls = [call for call in fake_conn.count_calls if "stock_minute_bar_1m" in call[0]]
        self.assertEqual(len(stock_calls), 244)
        self.assertEqual(
            sum(1 for _sql, params in stock_calls if _batch_key_from_params(params) == batch_key),
            3,
        )
        self.assertFalse(plan["blockers"])

    def test_stock_minute_bar_execute_deletes_intraday_batches(self) -> None:
        counts = _stock_1m_time_counts()
        fake_conn = _FakeCleanupConnection(counts_by_batch=counts, deleted_by_batch=counts)

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )
            result = execute_keep2_dirty_hot_cleanup(
                plan_path=Path(tmp) / "plan.json",
                confirm_token=CONFIRM_TOKEN,
                current_trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                closeout_path=Path(tmp) / "closeout.json",
            )

        self.assertEqual(result["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        stock_deletes = [call for call in fake_conn.delete_calls if "stock_minute_bar_1m" in call[0]]
        self.assertEqual(len(stock_deletes), 242)
        self.assertTrue(all("bar_time >=" in sql and "bar_time <" in sql for sql, _params in stock_deletes))
        self.assertFalse(any("09:00:00+08" in str(params) or "09:15:00+08" in str(params) for _sql, params in stock_deletes))
        self.assertTrue(any("10:30:00+08" in str(params) and "10:31:00+08" in str(params) for _sql, params in stock_deletes))
        self.assertTrue(any("10:34:00+08" in str(params) and "10:35:00+08" in str(params) for _sql, params in stock_deletes))
        self.assertFalse(any("10:30:00+08" in str(params) and "10:35:00+08" in str(params) for _sql, params in stock_deletes))
        deleted_stock_rows = [
            row
            for row in result["deleted_rows"]
            if row["trade_date"] == "20260612" and row["layer"] == "n3" and row["table"] == "stock_minute_bar_1m"
        ]
        self.assertEqual(sum(row["deleted_rows"] for row in deleted_stock_rows), 242)

    def test_index_board_minute_bars_use_expected_batch_metadata(self) -> None:
        specs = {(spec.layer, spec.table): spec for spec in build_hot_cleanup_specs()}

        index_template = specs[("n3", "index_minute_bar_1m")]
        self.assertEqual(index_template.batch_column, "bar_time")
        self.assertEqual(index_template.batch_strategy, "intraday_time_windows_fine")
        self.assertEqual(len(index_template.batches), 8)
        self.assertTrue(all(batch.start_time >= "09:30:00" for batch in index_template.batches))

        board_template = specs[("n3", "board_minute_bar_1m")]
        self.assertEqual(board_template.batch_column, "bar_time")
        self.assertEqual(board_template.batch_strategy, "intraday_time_windows_stock_5m")
        self.assertEqual(len(board_template.batches), 48)
        self.assertTrue(all(batch.start_time >= "09:30:00" for batch in board_template.batches))

    def test_index_minute_bar_plan_counts_intraday_batches(self) -> None:
        fake_conn = _FakeCleanupConnection(counts_by_batch=_fine_time_counts())

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )

        row = next(
            item
            for item in plan["table_delete_plan"]
            if item["trade_date"] == "20260612" and item["layer"] == "n3" and item["table"] == "index_minute_bar_1m"
        )
        self.assertEqual(row["planned_delete_rows"], 44)
        table_calls = [call for call in fake_conn.count_calls if "index_minute_bar_1m" in call[0]]
        self.assertEqual(len(table_calls), 8)
        self.assertTrue(all("bar_time >=" in sql and "bar_time <" in sql for sql, _params in table_calls))
        self.assertFalse(any("09:00:00+08" in str(params) for _sql, params in table_calls))
        batch_timings = [
            item
            for item in plan["count_timings"]
            if item["trade_date"] == "20260612"
            and item["layer"] == "n3"
            and item["table"] == "index_minute_bar_1m"
        ]
        self.assertEqual(len(batch_timings), 8)
        self.assertTrue(all(item.get("batch_label") for item in batch_timings))

    def test_board_minute_bar_plan_counts_5m_batches(self) -> None:
        fake_conn = _FakeCleanupConnection(counts_by_batch=_stock_5m_time_counts())

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )

        row = next(
            item
            for item in plan["table_delete_plan"]
            if item["trade_date"] == "20260612" and item["layer"] == "n3" and item["table"] == "board_minute_bar_1m"
        )
        self.assertEqual(row["planned_delete_rows"], 1176)
        board_calls = [call for call in fake_conn.count_calls if "board_minute_bar_1m" in call[0]]
        self.assertEqual(len(board_calls), 48)
        self.assertTrue(all("bar_time >=" in sql and "bar_time <" in sql for sql, _params in board_calls))
        self.assertFalse(any("09:00:00+08" in str(params) or "09:15:00+08" in str(params) for _sql, params in board_calls))
        self.assertTrue(any("09:30:00+08" in str(params) and "09:35:00+08" in str(params) for _sql, params in board_calls))
        batch_timings = [
            item
            for item in plan["count_timings"]
            if item["trade_date"] == "20260612"
            and item["layer"] == "n3"
            and item["table"] == "board_minute_bar_1m"
        ]
        self.assertEqual(len(batch_timings), 48)
        self.assertTrue(all(item.get("batch_label") for item in batch_timings))

    def test_index_minute_bar_execute_deletes_intraday_batches(self) -> None:
        counts = _fine_time_counts()
        fake_conn = _FakeCleanupConnection(counts_by_batch=counts, deleted_by_batch=counts)

        with tempfile.TemporaryDirectory() as tmp:
            build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )
            result = execute_keep2_dirty_hot_cleanup(
                plan_path=Path(tmp) / "plan.json",
                confirm_token=CONFIRM_TOKEN,
                current_trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                closeout_path=Path(tmp) / "closeout.json",
            )

        self.assertEqual(result["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        table_deletes = [call for call in fake_conn.delete_calls if "index_minute_bar_1m" in call[0]]
        self.assertEqual(len(table_deletes), 8)
        self.assertTrue(all("bar_time >=" in sql and "bar_time <" in sql for sql, _params in table_deletes))
        self.assertFalse(any("09:00:00+08" in str(params) for _sql, params in table_deletes))
        deleted_rows = [
            row
            for row in result["deleted_rows"]
            if row["trade_date"] == "20260612" and row["layer"] == "n3" and row["table"] == "index_minute_bar_1m"
        ]
        self.assertEqual(sum(row["deleted_rows"] for row in deleted_rows), 44)

    def test_board_minute_bar_execute_deletes_5m_batches(self) -> None:
        counts = _stock_5m_time_counts()
        fake_conn = _FakeCleanupConnection(counts_by_batch=counts, deleted_by_batch=counts)

        with tempfile.TemporaryDirectory() as tmp:
            build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )
            result = execute_keep2_dirty_hot_cleanup(
                plan_path=Path(tmp) / "plan.json",
                confirm_token=CONFIRM_TOKEN,
                current_trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                closeout_path=Path(tmp) / "closeout.json",
            )

        self.assertEqual(result["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        board_deletes = [call for call in fake_conn.delete_calls if "board_minute_bar_1m" in call[0]]
        self.assertEqual(len(board_deletes), 48)
        self.assertTrue(all("bar_time >=" in sql and "bar_time <" in sql for sql, _params in board_deletes))
        self.assertFalse(any("09:00:00+08" in str(params) or "09:15:00+08" in str(params) for _sql, params in board_deletes))
        self.assertTrue(any("09:30:00+08" in str(params) and "09:35:00+08" in str(params) for _sql, params in board_deletes))
        deleted_rows = [
            row
            for row in result["deleted_rows"]
            if row["trade_date"] == "20260612" and row["layer"] == "n3" and row["table"] == "board_minute_bar_1m"
        ]
        self.assertEqual(sum(row["deleted_rows"] for row in deleted_rows), 1176)

    def test_action_confirmation_metric_uses_label_batch_metadata(self) -> None:
        for table in (
            "stock_action_confirmation_projection_metric",
            "index_action_confirmation_projection_metric",
            "board_action_confirmation_projection_metric",
        ):
            with self.subTest(table=table):
                template = next(
                    spec
                    for spec in build_hot_cleanup_specs()
                    if spec.layer == "n3" and spec.table == table
                )

                self.assertEqual(template.batch_column, "metric_minute_label")
                self.assertEqual(template.batch_strategy, "intraday_label_windows_5m")
                self.assertEqual(len(template.batches), 48)
                self.assertEqual(template.batches[0].label, "morning_0930_0935")

    def test_stock_realtime_projection_metric_uses_snapshot_time_batch_metadata(self) -> None:
        template = next(
            spec
            for spec in build_hot_cleanup_specs()
            if spec.layer == "n3" and spec.table == "stock_realtime_projection_metric"
        )

        self.assertEqual(template.batch_column, "snapshot_time")
        self.assertEqual(template.batch_strategy, "intraday_time_windows_fine")
        self.assertEqual(len(template.batches), 8)

    def test_stock_realtime_projection_metric_plan_counts_snapshot_time_batches(self) -> None:
        fake_conn = _FakeCleanupConnection(
            counts_by_batch={
                "2026-06-12 09:30:00+08->2026-06-12 10:00:00+08": 2,
                "2026-06-12 10:00:00+08->2026-06-12 10:30:00+08": 3,
                "2026-06-12 10:30:00+08->2026-06-12 11:00:00+08": 5,
                "2026-06-12 11:00:00+08->2026-06-12 11:31:00+08": 7,
                "2026-06-12 13:00:00+08->2026-06-12 13:30:00+08": 11,
                "2026-06-12 13:30:00+08->2026-06-12 14:00:00+08": 13,
                "2026-06-12 14:00:00+08->2026-06-12 14:30:00+08": 17,
                "2026-06-12 14:30:00+08->2026-06-12 15:01:00+08": 19,
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )

        row = next(
            item
            for item in plan["table_delete_plan"]
            if item["trade_date"] == "20260612"
            and item["layer"] == "n3"
            and item["table"] == "stock_realtime_projection_metric"
        )
        self.assertEqual(row["planned_delete_rows"], 77)
        projection_calls = [
            call for call in fake_conn.count_calls if "stock_realtime_projection_metric" in call[0]
        ]
        self.assertEqual(len(projection_calls), 8)
        self.assertTrue(
            all("snapshot_time >=" in sql and "snapshot_time <" in sql for sql, _params in projection_calls)
        )
        self.assertTrue(all("trade_date = %s" in sql for sql, _params in projection_calls))
        batch_timings = [
            item
            for item in plan["count_timings"]
            if item["trade_date"] == "20260612"
            and item["layer"] == "n3"
            and item["table"] == "stock_realtime_projection_metric"
        ]
        self.assertEqual(len(batch_timings), 8)
        self.assertTrue(all(item.get("batch_label") for item in batch_timings))

    def test_stock_realtime_projection_metric_execute_deletes_snapshot_time_batches(self) -> None:
        counts = {
            "2026-06-12 09:30:00+08->2026-06-12 10:00:00+08": 2,
            "2026-06-12 10:00:00+08->2026-06-12 10:30:00+08": 3,
            "2026-06-12 10:30:00+08->2026-06-12 11:00:00+08": 5,
            "2026-06-12 11:00:00+08->2026-06-12 11:31:00+08": 7,
            "2026-06-12 13:00:00+08->2026-06-12 13:30:00+08": 11,
            "2026-06-12 13:30:00+08->2026-06-12 14:00:00+08": 13,
            "2026-06-12 14:00:00+08->2026-06-12 14:30:00+08": 17,
            "2026-06-12 14:30:00+08->2026-06-12 15:01:00+08": 19,
        }
        fake_conn = _FakeCleanupConnection(counts_by_batch=counts, deleted_by_batch=counts)

        with tempfile.TemporaryDirectory() as tmp:
            build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )
            result = execute_keep2_dirty_hot_cleanup(
                plan_path=Path(tmp) / "plan.json",
                confirm_token=CONFIRM_TOKEN,
                current_trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                closeout_path=Path(tmp) / "closeout.json",
            )

        self.assertEqual(result["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        projection_deletes = [
            call for call in fake_conn.delete_calls if "stock_realtime_projection_metric" in call[0]
        ]
        self.assertEqual(len(projection_deletes), 8)
        self.assertTrue(
            all("snapshot_time >=" in sql and "snapshot_time <" in sql for sql, _params in projection_deletes)
        )
        deleted_rows = [
            row
            for row in result["deleted_rows"]
            if row["trade_date"] == "20260612"
            and row["layer"] == "n3"
            and row["table"] == "stock_realtime_projection_metric"
        ]
        self.assertEqual(sum(row["deleted_rows"] for row in deleted_rows), 77)

    def test_stock_realtime_projection_metric_batch_timeout_reports_batch_evidence(self) -> None:
        fake_conn = _FakeCleanupConnection(
            errors_by_table_batch={
                (
                    "stock_realtime_projection_metric",
                    "2026-06-12 10:30:00+08->2026-06-12 11:00:00+08",
                ): TimeoutError("statement timeout"),
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )

        self.assertEqual(plan["result"], "DIRTY_HOT_KEEP2_CLEANUP_PLAN_BLOCKED")
        self.assertEqual(plan["slow_or_blocked_table"]["table"], "stock_realtime_projection_metric")
        self.assertEqual(plan["slow_or_blocked_table"]["batch_label"], "morning_1030_1100")
        self.assertIn("statement timeout", plan["slow_or_blocked_table"]["error"])

    def test_action_confirmation_metric_plan_counts_label_batches(self) -> None:
        fake_conn = _FakeCleanupConnection(
            counts_by_batch={
                "09:30->09:35": 2,
                "09:35->09:40": 3,
                "09:40->09:45": 5,
                "14:55->15:01": 11,
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )

        row = next(
            item
            for item in plan["table_delete_plan"]
            if item["trade_date"] == "20260612"
            and item["layer"] == "n3"
            and item["table"] == "stock_action_confirmation_projection_metric"
        )
        self.assertEqual(row["planned_delete_rows"], 21)
        metric_calls = [
            call for call in fake_conn.count_calls if "stock_action_confirmation_projection_metric" in call[0]
        ]
        self.assertTrue(metric_calls)
        self.assertTrue(
            all("metric_minute_label >=" in sql and "metric_minute_label <" in sql for sql, _params in metric_calls)
        )
        self.assertFalse(any("::timestamptz" in sql for sql, _params in metric_calls))
        batch_timings = [
            item
            for item in plan["count_timings"]
            if item["trade_date"] == "20260612"
            and item["layer"] == "n3"
            and item["table"] == "stock_action_confirmation_projection_metric"
        ]
        self.assertEqual(len(batch_timings), 48)
        self.assertTrue(all(item.get("batch_label") for item in batch_timings))

    def test_action_confirmation_metric_execute_deletes_label_batches(self) -> None:
        counts = {
            "09:30->09:35": 2,
            "09:35->09:40": 3,
            "09:40->09:45": 5,
            "14:55->15:01": 11,
        }
        fake_conn = _FakeCleanupConnection(counts_by_batch=counts, deleted_by_batch=counts)

        with tempfile.TemporaryDirectory() as tmp:
            build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )
            result = execute_keep2_dirty_hot_cleanup(
                plan_path=Path(tmp) / "plan.json",
                confirm_token=CONFIRM_TOKEN,
                current_trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                closeout_path=Path(tmp) / "closeout.json",
            )

        self.assertEqual(result["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        metric_deletes = [
            call for call in fake_conn.delete_calls if "stock_action_confirmation_projection_metric" in call[0]
        ]
        self.assertEqual(len(metric_deletes), 48)
        self.assertTrue(
            all("metric_minute_label >=" in sql and "metric_minute_label <" in sql for sql, _params in metric_deletes)
        )
        deleted_metric_rows = [
            row
            for row in result["deleted_rows"]
            if row["trade_date"] == "20260612"
            and row["layer"] == "n3"
            and row["table"] == "stock_action_confirmation_projection_metric"
        ]
        self.assertEqual(sum(row["deleted_rows"] for row in deleted_metric_rows), 21)

    def test_action_confirmation_metric_batch_timeout_reports_batch_evidence(self) -> None:
        fake_conn = _FakeCleanupConnection(
            errors_by_table_batch={
                ("stock_action_confirmation_projection_metric", "09:35->09:40"): TimeoutError(
                    "statement timeout"
                ),
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )

        self.assertEqual(plan["result"], "DIRTY_HOT_KEEP2_CLEANUP_PLAN_BLOCKED")
        self.assertEqual(plan["slow_or_blocked_table"]["table"], "stock_action_confirmation_projection_metric")
        self.assertEqual(plan["slow_or_blocked_table"]["batch_label"], "morning_0935_0940")
        self.assertIn("statement timeout", plan["slow_or_blocked_table"]["error"])

    def test_n6_projection_dependents_use_user_projection_run_id_batches(self) -> None:
        fake_conn = _FakeCleanupConnection(
            projection_run_ids_by_date={"20260612": ["projection-run-a", "projection-run-b"]},
            counts_by_batch={"projection-run-a": 5, "projection-run-b": 7},
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )

        for table in ("user_signal_projection", "user_signal_card", "user_notification_queue"):
            row = next(
                item
                for item in plan["table_delete_plan"]
                if item["trade_date"] == "20260612" and item["layer"] == "n6" and item["table"] == table
            )
            self.assertEqual(row["planned_delete_rows"], 12)
            table_calls = [call for call in fake_conn.count_calls if f"from {table}" in call[0]]
            self.assertEqual(len(table_calls), 2)
            self.assertTrue(all(f"from {table} where user_projection_run_id = %s" in sql for sql, _params in table_calls))
            self.assertFalse(any("source_action_run_id in" in sql for sql, _params in table_calls))
            self.assertEqual([params for _sql, params in table_calls], [("projection-run-a",), ("projection-run-b",)])

        projection_source_calls = [
            call for call in fake_conn.batch_source_calls if "select user_projection_run_id" in call[0]
        ]
        self.assertTrue(projection_source_calls)
        self.assertTrue(all("common_action_run where for_trade_date = %s" in sql for sql, _params in projection_source_calls))

    def test_n6_projection_dependents_execute_before_user_projection_run(self) -> None:
        counts = {"projection-run-a": 5, "projection-run-b": 7}
        fake_conn = _FakeCleanupConnection(
            projection_run_ids_by_date={"20260612": ["projection-run-a", "projection-run-b"]},
            counts_by_batch=counts,
            deleted_by_batch=counts,
            counts_by_table={"user_projection_run": 2},
            deleted_by_table={"user_projection_run": 2},
        )

        with tempfile.TemporaryDirectory() as tmp:
            build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )
            result = execute_keep2_dirty_hot_cleanup(
                plan_path=Path(tmp) / "plan.json",
                confirm_token=CONFIRM_TOKEN,
                current_trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                closeout_path=Path(tmp) / "closeout.json",
            )

        self.assertEqual(result["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        deleted_tables = [sql.split()[2] for sql, _params in fake_conn.delete_calls if sql.startswith("delete from user_")]
        projection_run_index = deleted_tables.index("user_projection_run")
        for table in ("user_notification_queue", "user_signal_card", "user_signal_projection"):
            self.assertIn(table, deleted_tables)
            self.assertLess(deleted_tables.index(table), projection_run_index)
        projection_deletes = [call for call in fake_conn.delete_calls if "user_signal_projection" in call[0]]
        self.assertEqual([params for _sql, params in projection_deletes], [("projection-run-a",), ("projection-run-b",)])
        self.assertTrue(all("where user_projection_run_id = %s" in sql for sql, _params in projection_deletes))

    def test_n6_projection_batch_timeout_reports_run_id_evidence(self) -> None:
        fake_conn = _FakeCleanupConnection(
            projection_run_ids_by_date={"20260612": ["projection-run-a", "projection-run-b"]},
            errors_by_batch={"projection-run-b": TimeoutError("statement timeout")},
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=Path(tmp) / "plan.json",
            )

        self.assertEqual(plan["result"], "DIRTY_HOT_KEEP2_CLEANUP_PLAN_BLOCKED")
        self.assertEqual(plan["slow_or_blocked_table"]["table"], "user_notification_queue")
        self.assertEqual(plan["slow_or_blocked_table"]["batch_label"], "user_projection_run_id:projection-run-b")
        self.assertIn("statement timeout", plan["slow_or_blocked_table"]["error"])

    def test_execute_requires_confirmation_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                table_counter=lambda _spec, _trade_date: 1,
                plan_path=Path(tmp) / "plan.json",
            )
            plan_path = Path(tmp) / "plan.json"

            result = execute_keep2_dirty_hot_cleanup(
                plan_path=plan_path,
                confirm_token="WRONG",
                current_trade_dates=["20260612", "20260701", "20260702"],
                table_counter=lambda _spec, _trade_date: 1,
                table_deleter=lambda _spec, _trade_date: 1,
            )

        self.assertEqual(result["result"], "BLOCKED_CONFIRM_TOKEN_REQUIRED")
        self.assertFalse(result["cleanup_executed"])
        self.assertFalse(result["side_effects"]["writes_database"])

    def test_execute_blocks_when_retained_trade_dates_changed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                table_counter=lambda _spec, _trade_date: 1,
                plan_path=Path(tmp) / "plan.json",
            )
            plan_path = Path(tmp) / "plan.json"

            result = execute_keep2_dirty_hot_cleanup(
                plan_path=plan_path,
                confirm_token=CONFIRM_TOKEN,
                current_trade_dates=["20260612", "20260701", "20260702", "20260703"],
                table_counter=lambda _spec, _trade_date: 1,
                table_deleter=lambda _spec, _trade_date: 1,
            )

        self.assertEqual(result["result"], "BLOCKED_RETAINED_TRADE_DATES_CHANGED")
        self.assertFalse(result["cleanup_executed"])
        self.assertFalse(result["side_effects"]["writes_database"])

    def test_execute_blocks_with_batch_evidence_when_recheck_times_out(self) -> None:
        fake_conn = _FakeCleanupConnection(
            counts_by_batch={
                "09:30->09:35": 2,
                "09:35->09:40": 3,
            },
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            closeout_path = Path(tmp) / "closeout.json"
            build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=plan_path,
            )
            fake_conn.errors_by_table_batch[
                ("stock_action_confirmation_projection_metric", "09:35->09:40")
            ] = TimeoutError("statement timeout")

            result = execute_keep2_dirty_hot_cleanup(
                plan_path=plan_path,
                confirm_token=CONFIRM_TOKEN,
                current_trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                closeout_path=closeout_path,
            )

        self.assertEqual(result["result"], "BLOCKED_ROW_COUNT_RECHECK_TIMEOUT")
        self.assertFalse(result["cleanup_executed"])
        self.assertFalse(result["side_effects"]["writes_database"])
        self.assertEqual(result["slow_or_blocked_table"]["table"], "stock_action_confirmation_projection_metric")
        self.assertEqual(result["slow_or_blocked_table"]["batch_label"], "morning_0935_0940")
        self.assertFalse(fake_conn.delete_calls)

    def test_execute_blocks_with_batch_evidence_when_delete_times_out(self) -> None:
        fake_conn = _FakeCleanupConnection(
            market_data_run_ids_by_date={"20260612": ["market-run-a", "market-run-b"]},
            counts_by_batch={"market-run-a": 11, "market-run-b": 13},
            deleted_by_batch={"market-run-a": 11},
        )

        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            closeout_path = Path(tmp) / "closeout.json"
            build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                plan_path=plan_path,
            )
            fake_conn.delete_errors_by_table_batch[
                ("common_market_data_subscription", "market-run-b")
            ] = TimeoutError("statement timeout")

            result = execute_keep2_dirty_hot_cleanup(
                plan_path=plan_path,
                confirm_token=CONFIRM_TOKEN,
                current_trade_dates=["20260612", "20260701", "20260702"],
                connection_factory=lambda _dsn: fake_conn,
                closeout_path=closeout_path,
            )

        self.assertEqual(result["result"], "BLOCKED_DELETE_TIMEOUT")
        self.assertFalse(result["cleanup_executed"])
        self.assertFalse(result["side_effects"]["writes_database"])
        self.assertEqual(result["delete_blocker"]["table"], "common_market_data_subscription")
        self.assertEqual(result["delete_blocker"]["batch_label"], "market_data_run_id:market-run-b")
        self.assertIn("statement timeout", result["delete_blocker"]["error"])

    def test_execute_deletes_only_cleanup_dates_and_records_counts(self) -> None:
        deleted: list[tuple[str, str, str]] = []

        def counter(spec, trade_date):
            return 2 if trade_date == "20260612" and spec.table in {"stock_minute_bar_1m", "common_trigger_state"} else 0

        def deleter(spec, trade_date):
            deleted.append((trade_date, spec.layer, spec.table))
            return counter(spec, trade_date)

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_keep2_dirty_hot_cleanup_plan(
                trade_dates=["20260612", "20260701", "20260702"],
                table_counter=counter,
                plan_path=Path(tmp) / "plan.json",
            )
            plan_path = Path(tmp) / "plan.json"

            result = execute_keep2_dirty_hot_cleanup(
                plan_path=plan_path,
                confirm_token=CONFIRM_TOKEN,
                current_trade_dates=["20260612", "20260701", "20260702"],
                table_counter=counter,
                table_deleter=deleter,
            )

        self.assertEqual(result["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        self.assertTrue(result["cleanup_executed"])
        self.assertTrue(result["side_effects"]["writes_database"])
        self.assertFalse(result["side_effects"]["cleanup_local_runtime_files"])
        self.assertEqual(result["retained_trade_dates"], ["20260701", "20260702"])
        self.assertEqual(result["cleanup_trade_dates"], ["20260612"])
        self.assertEqual(result["deleted_total_rows"], 4)
        self.assertTrue(all(row[0] == "20260612" for row in deleted))
        self.assertFalse(any(row[0] in {"20260701", "20260702"} for row in deleted))

    def test_keep5_wrapper_blocks_when_single_flight_lock_is_held(self) -> None:
        counter_calls: list[str] = []
        deleter_calls: list[str] = []

        def counter(spec, trade_date):
            counter_calls.append(f"{trade_date}:{spec.table}")
            return 1

        def deleter(spec, trade_date):
            deleter_calls.append(f"{trade_date}:{spec.table}")
            return 1

        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp) / "reports"
            report_dir.mkdir(parents=True)
            lock_path = report_dir / ".keep5_cleanup.lock"
            with lock_path.open("w+", encoding="utf-8") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                result = run_runtime_hot_keep5_cleanup_once(
                    report_dir=report_dir,
                    archive_root=Path(tmp) / "archive",
                    execute=True,
                    confirm_token=KEEP5_CONFIRM_TOKEN,
                    trade_dates=["20260612", "20260701", "20260702"],
                    table_counter=counter,
                    table_deleter=deleter,
                )

        self.assertEqual(result["result"], "BLOCKED_CLEANUP_ALREADY_RUNNING")
        self.assertFalse(result["cleanup_executed"])
        self.assertFalse(result["side_effects"]["writes_database"])
        self.assertFalse(counter_calls)
        self.assertFalse(deleter_calls)


def _write_verified_runtime_archive_manifest(archive_root: Path, trade_date: str) -> None:
    manifest_path = archive_root / f"trade_date={trade_date}" / "manifests" / "archive_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        """{
  "result": "ARCHIVED_VERIFIED",
  "row_count_match": true,
  "checksum_algorithm": "sha256",
  "cleanup_eligible": false,
  "cleanup_blockers": ["manual_cleanup_required"],
  "file_count": 1,
  "total_rows": 1,
  "files": [],
  "side_effects": {
    "writes_database": false,
    "writes_archive_files": true,
    "cleanup_local_runtime": false
  }
}
""",
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
