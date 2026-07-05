import unittest
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime

from ashare_v3.market.previous_day_preload_execute import (
    ASIA_SHANGHAI,
    MootdxPreviousDayMinuteAdapter,
    PreviousDayMinutePreloadExecuteError,
    build_post_execute_quality_items,
    build_post_execute_checks,
    bulk_upsert_minute_bars,
    ensure_clean_preload_target,
    ensure_execute_authorized,
    normalize_minute_bar_records,
)
from scripts.check_event_contract import run_check


class PreviousDayMinutePreloadExecuteTest(unittest.TestCase):
    def test_execute_requires_execute_flag_before_adapter_or_db_path(self) -> None:
        with self.assertRaisesRegex(PreviousDayMinutePreloadExecuteError, "--execute"):
            ensure_execute_authorized(execute=False, user_confirmed=True)

    def test_execute_requires_user_confirmed_flag_before_adapter_or_db_path(self) -> None:
        with self.assertRaisesRegex(PreviousDayMinutePreloadExecuteError, "--user-confirmed"):
            ensure_execute_authorized(execute=True, user_confirmed=False)

    def test_execute_allows_fetch_and_commit_path_only_with_double_confirmation(self) -> None:
        self.assertIsNone(ensure_execute_authorized(execute=True, user_confirmed=True))

    def test_clean_target_allows_global_outbox_when_scoped_refs_are_zero(self) -> None:
        backup = sample_preload_backup(
            global_outbox=74176,
            scoped_refs={"common_event_outbox": 0, "common_event_inbox": 0, "common_event_consumer_checkpoint": 0},
        )

        self.assertIsNone(ensure_clean_preload_target(backup, "previous_day_minute_preload_test"))

    def test_clean_target_blocks_scoped_event_refs(self) -> None:
        for table_name in ("common_event_outbox", "common_event_inbox", "common_event_consumer_checkpoint"):
            with self.subTest(table_name=table_name):
                backup = sample_preload_backup(
                    global_outbox=74176,
                    scoped_refs={table_name: 1},
                )

                with self.assertRaisesRegex(PreviousDayMinutePreloadExecuteError, table_name):
                    ensure_clean_preload_target(backup, "previous_day_minute_preload_test")

    def test_normalize_minute_bar_records_filters_target_trade_date(self) -> None:
        rows = normalize_minute_bar_records(
            [
                {
                    "datetime": "2026-05-22 09:31:00",
                    "open": 10,
                    "high": 10.1,
                    "low": 9.9,
                    "close": 10.05,
                    "vol": 100,
                    "amount": 1000,
                },
                {
                    "datetime": "2026-05-21 09:31:00",
                    "open": 9,
                    "high": 9.1,
                    "low": 8.9,
                    "close": 9.05,
                    "vol": 90,
                    "amount": 900,
                },
            ],
            trade_date="20260522",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["bar_time"], datetime(2026, 5, 22, 9, 31, tzinfo=ASIA_SHANGHAI))
        self.assertEqual(rows[0]["volume"], 100)

    def test_adapter_uses_stock_bars_and_index_bars(self) -> None:
        client = FakeMootdxClient()
        adapter = MootdxPreviousDayMinuteAdapter(client=client)

        stock_rows = adapter.fetch_minute_bars(subscription("stock", "600000"), "20260522")
        index_rows = adapter.fetch_minute_bars(subscription("index", "000905"), "20260522")
        board_rows = adapter.fetch_minute_bars(subscription("board", "881001"), "20260522")

        self.assertEqual(len(stock_rows), 1)
        self.assertEqual(len(index_rows), 1)
        self.assertEqual(len(board_rows), 1)
        self.assertEqual(client.calls, [("bars", "600000", 8), ("index_bars", "000905", 8), ("index_bars", "881001", 8)])

    def test_bulk_upsert_targets_physical_minute_table_without_outbox(self) -> None:
        cursor = FakeCursor()
        count = bulk_upsert_minute_bars(
            cursor,
            "stock",
            [
                {
                    "run_id": "preload_run",
                    "subscription_id": 1,
                    "source_condition_run_id": "condition_run",
                    "for_trade_date": "20260525",
                    "trade_date": "20260522",
                    "bar_time": datetime(2026, 5, 22, 9, 31, tzinfo=ASIA_SHANGHAI),
                    "identity_key": "stock:SH:600000",
                    "exchange": "SH",
                    "code": "600000",
                    "display_code": "600000.SH",
                    "name": "600000",
                    "open": 10,
                    "high": 10,
                    "low": 10,
                    "close": 10,
                    "volume": 100,
                    "amount": 1000,
                    "source_adapter": "StockMarketDataAdapter",
                    "source_version": "test",
                    "quality_status": "passed",
                    "is_previous_day_preload": True,
                    "source_scope_ids": [1],
                    "source_condition_pool_ids": [101],
                    "raw_json": {"source_run_id": "source", "preload_run_id": "preload"},
                }
            ],
        )

        self.assertEqual(count, 1)
        self.assertIn("INSERT INTO stock_minute_bar_1m", cursor.sql)
        self.assertNotIn("common_event_outbox", cursor.sql)

    def test_missing_objects_are_warning_when_status_evidence_exists(self) -> None:
        post_checks = {
            "n3_a1_asset_object_count_matches_a0": True,
            "n3_a1_expected_status_counts": {"stock": 1, "index": 0, "board": 0},
            "n3_a1_actual_status_counts": {"stock": 1, "index": 0, "board": 0},
            "n3_a1_minute_rows_reasonable": True,
            "n3_a1_total_minute_rows_present": True,
            "n3_a1_expected_minute_rows_by_asset": {"stock": 240, "index": 0, "board": 0},
            "n3_a1_actual_minute_rows_by_asset": {"stock": 0, "index": 0, "board": 0},
            "n3_a1_duplicate_minute_key_zero": True,
            "n3_a1_duplicate_minute_key_count_by_asset": {"stock": 0, "index": 0, "board": 0},
            "n3_a1_missing_object_not_silent": True,
            "n3_a1_object_status_counts": {"missing": 1},
            "n3_a1_physical_table_isolation": True,
            "n3_a1_physical_isolation_violation_count_by_asset": {"stock": 0, "index": 0, "board": 0},
            "n3_a1_outbox_rows_zero": True,
            "n3_a1_n1_n2_active_snapshot_unchanged": True,
        }
        items = build_post_execute_quality_items(
            contract=sample_contract(p1_count=0),
            post_checks=post_checks,
            object_results=[
                {
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "status": "missing",
                    "actual_bar_count": 0,
                }
            ],
        )

        failed_p0 = [item for item in items if item["severity"] == "P0" and item["status"] == "failed"]
        warning_codes = {item["gate_code"] for item in items if item["status"] == "warning"}
        self.assertEqual(failed_p0, [])
        self.assertIn("n3_a1_missing_or_partial_objects_recorded", warning_codes)

    def test_postcheck_uses_scoped_event_refs_and_warns_on_global_count_change(self) -> None:
        post_checks = build_post_execute_checks(
            contract={**sample_contract(p1_count=0), "expected_asset_counts": {}},
            pre_backup=sample_preload_backup(
                global_outbox=74176,
                global_inbox=100,
                global_checkpoint=50,
                scoped_refs={"common_event_outbox": 0, "common_event_inbox": 0, "common_event_consumer_checkpoint": 0},
            ),
            data_snapshot=sample_preload_backup(
                global_outbox=74177,
                global_inbox=101,
                global_checkpoint=51,
                scoped_refs={"common_event_outbox": 0, "common_event_inbox": 0, "common_event_consumer_checkpoint": 0},
            ),
            object_results=[],
        )
        items = build_post_execute_quality_items(
            contract=sample_contract(p1_count=0),
            post_checks=post_checks,
            object_results=[],
        )
        failed_p0 = [item for item in items if item["severity"] == "P0" and item["status"] == "failed"]
        warning_codes = {item["gate_code"] for item in items if item["status"] == "warning"}

        self.assertTrue(post_checks["n3_a1_scoped_event_refs_zero"])
        self.assertFalse(post_checks["n3_a1_global_event_counts_unchanged"])
        self.assertEqual(failed_p0, [])
        self.assertIn("n3_a1_global_event_counts_changed_scoped_safe", warning_codes)

    def test_execute_contract_scan_still_has_no_forbidden_event_or_runtime_names(self) -> None:
        result = run_check()
        self.assertTrue(result["passed"], result["findings"])

    def test_cli_help_exposes_historical_preload_direct_aliases(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/run_previous_day_minute_preload_execute.py", "--help"],
            check=True,
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertIn("--historical-preload", result.stdout)
        self.assertIn("--source-subscription-run-id", result.stdout)
        self.assertIn("--preload-run-id", result.stdout)
        self.assertIn("--data-trade-date", result.stdout)

    def test_cli_blocks_direct_alias_contract_mismatch_before_db_path(self) -> None:
        contract = {
            "stage": "N3-A1-preflight",
            "layer_role": "N3_market_data",
            "source_run_id": "source_subscription_run",
            "source_subscription_run_id": "source_subscription_run",
            "preload_run_id": "preload_run",
            "source_condition_run_id": "condition_run",
            "for_trade_date": "20260529",
            "source_trade_date": "20260528",
            "previous_day_minute_date": "20260528",
            "data_trade_date": "20260528",
            "required_data_kind": "previous_day_minute_bar_1m",
            "historical_preload": True,
            "target_tables": {},
            "expected_asset_counts": {},
            "quality": {"p0_count": 0},
            "writes_outbox": False,
            "writes_event_outbox": False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            contract_path = Path(tmp) / "contract.json"
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/run_previous_day_minute_preload_execute.py",
                    "--contract-path",
                    str(contract_path),
                    "--historical-preload",
                    "--source-subscription-run-id",
                    "wrong_source_subscription_run",
                    "--preload-run-id",
                    "preload_run",
                    "--data-trade-date",
                    "20260528",
                    "--execute",
                    "--user-confirmed",
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["result"], "BLOCKED")
        self.assertIn("--source-subscription-run-id", payload["reason"])
        self.assertFalse(payload["market_data_pulled"])
        self.assertFalse(payload["market_data_fact_written"])


class FakeMootdxClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    def bars(self, *, symbol: str, frequency: int, start: int, offset: int) -> list[dict[str, object]]:
        self.calls.append(("bars", symbol, frequency))
        return [minute_row()]

    def index_bars(self, *, symbol: str, frequency: int, start: int, offset: int) -> list[dict[str, object]]:
        self.calls.append(("index_bars", symbol, frequency))
        return [minute_row()]


class FakeCursor:
    def __init__(self) -> None:
        self.sql = ""
        self.values: object = None

    def executemany(self, sql: str, values: object) -> None:
        self.sql = sql
        self.values = values


def minute_row() -> dict[str, object]:
    return {
        "year": 2026,
        "month": 5,
        "day": 22,
        "hour": 9,
        "minute": 31,
        "open": 10,
        "high": 10.1,
        "low": 9.9,
        "close": 10.05,
        "vol": 100,
        "amount": 1000,
    }


def subscription(asset_kind: str, code: str) -> dict[str, object]:
    return {"asset_kind": asset_kind, "code": code}


def sample_contract(*, p1_count: int = 1) -> dict[str, object]:
    return {
        "source_run_id": "market_data_subscription_20260525_test_execute",
        "preload_run_id": "previous_day_minute_preload_test",
        "source_condition_run_id": "condition_layer_test",
        "for_trade_date": "20260525",
        "source_trade_date": "20260522",
        "previous_day_minute_date": "20260522",
        "quality": {"p1_count": p1_count},
    }


def sample_preload_backup(
    *,
    global_outbox: int = 0,
    global_inbox: int = 0,
    global_checkpoint: int = 0,
    scoped_refs: dict[str, int] | None = None,
) -> dict[str, object]:
    refs = {"common_event_outbox": 0, "common_event_inbox": 0, "common_event_consumer_checkpoint": 0}
    refs.update(scoped_refs or {})
    return {
        "preload_run_exists": False,
        "target_preload_run_row_counts": {
            "stock_minute_bar_1m": 0,
            "index_minute_bar_1m": 0,
            "board_minute_bar_1m": 0,
            "stock_previous_day_minute_preload_status": 0,
            "index_previous_day_minute_preload_status": 0,
            "board_previous_day_minute_preload_status": 0,
            "common_market_data_quality_item": 0,
            "common_market_data_run": 0,
        },
        "target_preload_run_row_counts_by_asset": {},
        "duplicate_minute_key_count_by_asset": {},
        "physical_isolation_violation_count_by_asset": {},
        "active_snapshot": {"active": "unchanged"},
        "common_event_outbox_row_count": global_outbox,
        "common_event_inbox_row_count": global_inbox,
        "common_event_consumer_checkpoint_row_count": global_checkpoint,
        "scoped_event_ref_counts": refs,
    }


if __name__ == "__main__":
    unittest.main()
