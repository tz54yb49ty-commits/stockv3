import unittest
from datetime import datetime, timezone
from pathlib import Path

from psycopg.types.json import Jsonb

from ashare_v3.market.fact_writer import (
    write_market_quality_with_event,
    write_market_snapshot_with_event,
    write_minute_bar_closed_with_event,
)
from scripts.check_event_contract import run_check


class MarketDataFactWriterContractTest(unittest.TestCase):
    def test_snapshot_fact_and_event_are_written_in_one_transaction(self) -> None:
        conn = FakeConnection()

        result = write_market_snapshot_with_event(conn, sample_snapshot())

        self.assertEqual(result["snapshot_id"], 101)
        self.assertEqual(conn.transaction_commits, 1)
        self.assertEqual(conn.transaction_rollbacks, 0)
        self.assertEqual(conn.sql_kinds(), ["snapshot_fact", "outbox"])
        self.assertEqual(result["event"].event_type, "MarketSnapshotUpdated")
        self.assertEqual(result["event"].payload_json["snapshot_id"], 101)
        self.assertEqual(result["event"].payload_json["subscription_id"], 11)
        self.assertIn("stock_realtime_daily_snapshot", conn.executed_sql[0])

    def test_minute_fact_and_event_are_written_in_one_transaction(self) -> None:
        conn = FakeConnection()

        result = write_minute_bar_closed_with_event(conn, sample_minute_bar())

        self.assertEqual(result["minute_bar_id"], 202)
        self.assertEqual(conn.transaction_commits, 1)
        self.assertEqual(conn.transaction_rollbacks, 0)
        self.assertEqual(conn.sql_kinds(), ["minute_fact", "outbox"])
        self.assertEqual(result["event"].event_type, "MinuteBarClosed")
        self.assertEqual(result["event"].payload_json["minute_bar_id"], 202)
        self.assertIn("stock_minute_bar_1m", conn.executed_sql[0])

    def test_quality_fact_and_delayed_event_are_written_in_one_transaction(self) -> None:
        conn = FakeConnection()

        result = write_market_quality_with_event(
            conn,
            sample_quality_item(),
            event_type="MarketDataDelayed",
        )

        self.assertEqual(result["quality_item_id"], 303)
        self.assertEqual(conn.transaction_commits, 1)
        self.assertEqual(conn.transaction_rollbacks, 0)
        self.assertEqual(conn.sql_kinds(), ["quality_fact", "outbox"])
        self.assertEqual(result["event"].event_type, "MarketDataDelayed")
        self.assertEqual(result["event"].payload_json["quality_item_id"], 303)
        self.assertIn("common_market_data_quality_item", conn.executed_sql[0])

    def test_quality_fact_and_missing_event_are_written_in_one_transaction(self) -> None:
        conn = FakeConnection()

        result = write_market_quality_with_event(
            conn,
            {**sample_quality_item(), "gate_code": "market_data_missing", "status_kind": "missing"},
            event_type="MarketDataMissing",
        )

        self.assertEqual(result["event"].event_type, "MarketDataMissing")
        self.assertEqual(result["event"].payload_json["quality_item_id"], 303)
        self.assertEqual(conn.transaction_commits, 1)

    def test_fact_write_failure_prevents_outbox_write(self) -> None:
        conn = FakeConnection(fail_on="stock_realtime_daily_snapshot")

        with self.assertRaises(RuntimeError):
            write_market_snapshot_with_event(conn, sample_snapshot())

        self.assertEqual(conn.sql_kinds(), ["snapshot_fact"])
        self.assertEqual(conn.transaction_commits, 0)
        self.assertEqual(conn.transaction_rollbacks, 1)

    def test_outbox_write_failure_rolls_back_fact_transaction(self) -> None:
        conn = FakeConnection(fail_on="common_event_outbox")

        with self.assertRaises(RuntimeError):
            write_market_snapshot_with_event(conn, sample_snapshot())

        self.assertEqual(conn.sql_kinds(), ["snapshot_fact", "outbox"])
        self.assertEqual(conn.transaction_commits, 0)
        self.assertEqual(conn.transaction_rollbacks, 1)

    def test_payload_trace_fields_are_complete(self) -> None:
        conn = FakeConnection()

        result = write_market_snapshot_with_event(conn, sample_snapshot())
        payload = result["event"].payload_json

        for key in (
            "subscription_id",
            "pull_plan_id",
            "run_id",
            "source_adapter",
            "data_quality_status",
            "snapshot_id",
        ):
            self.assertIn(key, payload)
            self.assertIsNotNone(payload[key])

    def test_snapshot_payload_includes_source_time_normalization_trace(self) -> None:
        conn = FakeConnection()
        snapshot = {
            **sample_snapshot(),
            "asset_kind": "board",
            "identity_key": "board:TDX:881478",
            "source_adapter": "BoardMarketDataAdapter",
            "data_quality_status": "partial",
            "quality_status": "partial",
            "raw_json": Jsonb(
                {
                    "source_time_status": "source_time_label_normalized",
                    "raw_snapshot_time_label": "2026-06-11T15:00:00+08:00",
                    "raw_snapshot_time_semantics": "tdx_index_frequency_9_period_label",
                    "source_time_trust_level": "untrusted_period_label",
                    "observed_at": "2026-06-11T13:11:00+08:00",
                    "fetched_at": "2026-06-11T13:11:00+08:00",
                    "source_time_label_normalized": True,
                    "snapshot_time_policy": "observed_at_when_raw_source_time_is_label",
                    "source_time_status_reason": (
                        "raw snapshot time label normalized to observed_at by explicit reviewed policy"
                    ),
                }
            ),
        }

        result = write_market_snapshot_with_event(conn, snapshot)
        payload = result["event"].payload_json

        self.assertEqual(payload["raw_snapshot_time_label"], "2026-06-11T15:00:00+08:00")
        self.assertEqual(payload["raw_snapshot_time_semantics"], "tdx_index_frequency_9_period_label")
        self.assertEqual(payload["source_time_trust_level"], "untrusted_period_label")
        self.assertEqual(payload["observed_at"], "2026-06-11T13:11:00+08:00")
        self.assertEqual(payload["fetched_at"], "2026-06-11T13:11:00+08:00")
        self.assertTrue(payload["source_time_label_normalized"])
        self.assertEqual(
            payload["normalized_event_time_reason"],
            "raw snapshot time label normalized to observed_at by explicit reviewed policy",
        )

    def test_fact_writer_contract_scan_has_no_forbidden_names(self) -> None:
        for path in (
            Path("src/ashare_v3/market/repositories.py"),
            Path("src/ashare_v3/market/fact_writer.py"),
        ):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("UserMarketProjectionUpdated", text)
            self.assertNotRegex(text, r"CREATE\s+TABLE\s+.*_runtime")

        result = run_check()
        self.assertTrue(result["passed"], result["findings"])


def sample_snapshot() -> dict[str, object]:
    return {
        "asset_kind": "stock",
        "run_id": "market_data_run_20260525_093000",
        "subscription_id": 11,
        "pull_plan_id": 22,
        "source_condition_run_id": "condition_run_1",
        "for_trade_date": "20260525",
        "trade_date": "20260525",
        "snapshot_time": datetime(2026, 5, 25, 1, 31, 3, tzinfo=timezone.utc),
        "identity_key": "stock:SH:600000",
        "exchange": "SH",
        "code": "600000",
        "display_code": "600000.SH",
        "name": "浦发银行",
        "open": 10,
        "high": 10.2,
        "low": 9.9,
        "close": 10.1,
        "current_price": 10.1,
        "pre_close": 10,
        "volume": 1000,
        "amount": 10100,
        "source_adapter": "mootdx",
        "source_version": "mock",
        "quality_status": "passed",
        "source_scope_ids": [1, 2],
        "source_condition_pool_ids": [101, 102],
        "raw_json": {"dry_run": True},
    }


def sample_minute_bar() -> dict[str, object]:
    return {
        "asset_kind": "stock",
        "run_id": "market_data_run_20260525_093000",
        "subscription_id": 11,
        "pull_plan_id": 22,
        "source_condition_run_id": "condition_run_1",
        "for_trade_date": "20260525",
        "trade_date": "20260525",
        "bar_time": datetime(2026, 5, 25, 1, 31, 0, tzinfo=timezone.utc),
        "identity_key": "stock:SH:600000",
        "exchange": "SH",
        "code": "600000",
        "display_code": "600000.SH",
        "name": "浦发银行",
        "open": 10,
        "high": 10.2,
        "low": 9.9,
        "close": 10.1,
        "volume": 1000,
        "amount": 10100,
        "source_adapter": "mootdx",
        "source_version": "mock",
        "quality_status": "passed",
        "source_scope_ids": [1, 2],
        "source_condition_pool_ids": [101, 102],
        "raw_json": {"dry_run": True},
    }


def sample_quality_item() -> dict[str, object]:
    return {
        "asset_kind": "stock",
        "run_id": "market_data_run_20260525_093000",
        "subscription_id": 11,
        "pull_plan_id": 22,
        "source_condition_run_id": "condition_run_1",
        "for_trade_date": "20260525",
        "source_trade_date": "20260522",
        "data_domain": "stock",
        "layer_scope": "market_data_run",
        "table_name": "stock_realtime_daily_snapshot",
        "gate_code": "market_data_delayed",
        "gate_name": "market data delayed",
        "severity": "P1",
        "status": "warning",
        "expected_value": "fresh snapshot",
        "actual_value": "adapter timeout then retry",
        "identity_key": "stock:SH:600000",
        "details": {"dry_run": True},
        "required_data_kind": "realtime_daily_snapshot",
        "status_kind": "delayed",
        "source_adapter": "mootdx",
        "quality_status": "warning",
        "event_time": datetime(2026, 5, 25, 1, 31, 3, tzinfo=timezone.utc),
    }


class FakeConnection:
    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.executed_sql: list[str] = []
        self.transaction_commits = 0
        self.transaction_rollbacks = 0
        self.cursor_obj = FakeCursor(self)

    def transaction(self) -> "FakeTransaction":
        return FakeTransaction(self)

    def cursor(self) -> "FakeCursor":
        return self.cursor_obj

    def sql_kinds(self) -> list[str]:
        kinds: list[str] = []
        for sql in self.executed_sql:
            if "common_event_outbox" in sql:
                kinds.append("outbox")
            elif "realtime_daily_snapshot" in sql:
                kinds.append("snapshot_fact")
            elif "minute_bar_1m" in sql:
                kinds.append("minute_fact")
            elif "common_market_data_quality_item" in sql:
                kinds.append("quality_fact")
            else:
                kinds.append("unknown")
        return kinds


class FakeTransaction:
    def __init__(self, conn: FakeConnection) -> None:
        self.conn = conn

    def __enter__(self) -> "FakeTransaction":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        if exc_type is None:
            self.conn.transaction_commits += 1
        else:
            self.conn.transaction_rollbacks += 1
        return False


class FakeCursor:
    def __init__(self, conn: FakeConnection) -> None:
        self.conn = conn
        self.last_sql = ""
        self.last_params: list[object] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    def execute(self, sql: str, params: list[object]) -> None:
        self.last_sql = sql
        self.last_params = params
        self.conn.executed_sql.append(sql)
        if self.conn.fail_on and self.conn.fail_on in sql:
            raise RuntimeError(f"forced failure on {self.conn.fail_on}")

    def fetchone(self) -> tuple[object]:
        if "common_event_outbox" in self.last_sql:
            return (self.last_params[0],)
        if "common_market_data_quality_item" in self.last_sql:
            return (303,)
        if "minute_bar_1m" in self.last_sql:
            return (202,)
        if "realtime_daily_snapshot" in self.last_sql:
            return (101,)
        return (0,)
