import inspect
import unittest
from datetime import datetime

from ashare_v3.market import today_minute_execute
from ashare_v3.market.today_minute_execute import (
    ASIA_SHANGHAI,
    MootdxTodayMinuteAdapter,
    TodayMinuteExecuteError,
    build_post_execute_checks,
    build_post_execute_quality_items,
    build_today_minute_fact_records,
    classify_today_minute_object_status,
    ensure_executable_plan,
    filter_closed_today_minute_rows,
)


class TodayMinuteExecuteTest(unittest.TestCase):
    def test_today_minute_execute_uses_c1_physical_normalizer_not_legacy_bridge(self) -> None:
        source = inspect.getsource(today_minute_execute)

        self.assertIn("normalize_c1_physical_intraday_1m_labels", source)
        self.assertNotIn("normalize_mootdx_intraday_1m_labels", source)
        self.assertNotIn("mootdx_intraday_1300_to_1130", source)

    def test_execute_requires_double_confirmation(self) -> None:
        with self.assertRaises(TodayMinuteExecuteError):
            ensure_executable_plan(
                sample_c0_plan(),
                execute=True,
                user_confirmed=False,
                for_trade_date="20260525",
                today_minute_run_id="today_minute_bar_1m_20260525_until_1411__source",
            )

    def test_execute_rejects_run_id_mismatch(self) -> None:
        with self.assertRaises(TodayMinuteExecuteError):
            ensure_executable_plan(
                sample_c0_plan(),
                execute=True,
                user_confirmed=True,
                for_trade_date="20260525",
                today_minute_run_id="today_minute_bar_1m_20260525_until_1410__source",
            )

    def test_execute_rejects_invalid_expected_bar_count_before_writing(self) -> None:
        cases = ["missing", None, 0]
        for value in cases:
            with self.subTest(value=value):
                plan = sample_c0_plan()
                if value == "missing":
                    plan.pop("expected_bar_count_per_object")
                else:
                    plan["expected_bar_count_per_object"] = value

                with self.assertRaisesRegex(TodayMinuteExecuteError, "expected_bar_count_per_object"):
                    ensure_executable_plan(
                        plan,
                        execute=True,
                        user_confirmed=True,
                        for_trade_date="20260525",
                        today_minute_run_id="today_minute_bar_1m_20260525_until_1411__source",
                    )

    def test_filter_closed_today_minute_rows_keeps_trade_date_and_closed_session_minutes(self) -> None:
        latest = datetime(2026, 5, 25, 14, 11, tzinfo=ASIA_SHANGHAI)
        rows = [
            minute_row("2026-05-25 09:31"),
            minute_row("2026-05-25 11:31"),
            minute_row("2026-05-25 14:11"),
            minute_row("2026-05-25 14:12"),
            minute_row("2026-05-22 14:11"),
        ]

        filtered = filter_closed_today_minute_rows(rows, trade_date="20260525", latest_closed_minute=latest)

        self.assertEqual([row["bar_time"].strftime("%H:%M") for row in filtered], ["09:31", "14:11"])

    def test_mootdx_current_day_raw_1300_remains_physical_c1_label(self) -> None:
        client = FakeMootdxClient(
            rows=[
                raw_minute_row("2026-06-22 11:29"),
                raw_minute_row("2026-06-22 13:00"),
                raw_minute_row("2026-06-22 13:01"),
            ]
        )
        adapter = MootdxTodayMinuteAdapter(client=client, intraday_trade_date="20260622")

        rows = adapter.fetch_minute_bars(subscription("stock", "600036"), "20260622")

        self.assertEqual([row["bar_time"].strftime("%H:%M") for row in rows], ["11:29", "13:00", "13:01"])
        self.assertNotIn("time_label_normalization", rows[1]["raw_payload"])

    def test_mootdx_current_day_raw_1130_fails_closed_for_physical_c1(self) -> None:
        client = FakeMootdxClient(rows=[raw_minute_row("2026-06-22 11:30")])
        adapter = MootdxTodayMinuteAdapter(client=client, intraday_trade_date="20260622")

        with self.assertRaisesRegex(TodayMinuteExecuteError, "BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE"):
            adapter.fetch_minute_bars(subscription("stock", "600036"), "20260622")

    def test_mootdx_historical_1130_is_not_rewritten_or_required_to_have_1300(self) -> None:
        client = FakeMootdxClient(
            rows=[
                raw_minute_row("2026-06-18 11:29"),
                raw_minute_row("2026-06-18 11:30"),
                raw_minute_row("2026-06-18 13:01"),
            ]
        )
        adapter = MootdxTodayMinuteAdapter(client=client, intraday_trade_date="20260622")

        rows = adapter.fetch_minute_bars(subscription("stock", "600036"), "20260618")

        self.assertEqual([row["bar_time"].strftime("%H:%M") for row in rows], ["11:29", "11:30", "13:01"])
        self.assertNotIn("time_label_normalization", rows[1]["raw_payload"])

    def test_mootdx_current_day_raw_1130_and_1300_fail_closed(self) -> None:
        client = FakeMootdxClient(
            rows=[
                raw_minute_row("2026-06-22 11:30"),
                raw_minute_row("2026-06-22 13:00"),
            ]
        )
        adapter = MootdxTodayMinuteAdapter(client=client, intraday_trade_date="20260622")

        with self.assertRaises(TodayMinuteExecuteError):
            adapter.fetch_minute_bars(subscription("stock", "600036"), "20260622")

    def test_mootdx_current_day_without_1130_or_1300_remains_missing(self) -> None:
        client = FakeMootdxClient(
            rows=[
                raw_minute_row("2026-06-22 11:29"),
                raw_minute_row("2026-06-22 13:01"),
            ]
        )
        adapter = MootdxTodayMinuteAdapter(client=client, intraday_trade_date="20260622")

        rows = adapter.fetch_minute_bars(subscription("stock", "600036"), "20260622")

        self.assertEqual([row["bar_time"].strftime("%H:%M") for row in rows], ["11:29", "13:01"])
        status, _ = classify_today_minute_object_status(
            actual_count=len(rows),
            expected_count=3,
            error_message=None,
            quality_visible_no_trade_proof=None,
        )
        self.assertEqual(status, "partial")

    def test_default_no_trade_proof_supports_20260622_002217(self) -> None:
        adapter = MootdxTodayMinuteAdapter(client=FakeMootdxClient(), intraday_trade_date="20260622")

        proof = adapter.quality_visible_no_trade_proof(
            subscription={**sample_subscription(), "identity_key": "stock:SZ:002217", "code": "002217"},
            trade_date="20260622",
            actual_rows=[minute_row("2026-06-22 13:01")],
            expected_bar_count=190,
            latest_closed_minute=datetime(2026, 6, 22, 14, 10, tzinfo=ASIA_SHANGHAI),
        )

        self.assertIsNotNone(proof)
        self.assertEqual(proof["reason"], "source_suspended")
        self.assertEqual(proof["identity_key"], "stock:SZ:002217")

    def test_adapter_routes_stock_to_bars_and_index_board_to_index_bars(self) -> None:
        client = FakeMootdxClient()
        adapter = MootdxTodayMinuteAdapter(client=client)

        adapter.fetch_minute_bars(subscription("stock", "600000"), "20260525")
        adapter.fetch_minute_bars(subscription("index", "000905"), "20260525")
        adapter.fetch_minute_bars(subscription("board", "881001"), "20260525")

        self.assertEqual(client.calls, [("bars", "600000", 8), ("index_bars", "000905", 8), ("index_bars", "881001", 8)])

    def test_build_today_minute_fact_records_marks_rows_as_today_and_no_outbox_trace(self) -> None:
        records = build_today_minute_fact_records(
            plan=sample_c0_plan(),
            subscription=sample_subscription(),
            normalized_rows=[minute_row("2026-05-25 14:11")],
            adapter_name="StockMarketDataAdapter",
            adapter=FakeAdapter(),
        )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["run_id"], "today_minute_bar_1m_20260525_until_1411__source")
        self.assertEqual(record["trade_date"], "20260525")
        self.assertFalse(record["is_previous_day_preload"])
        self.assertEqual(record["raw_json"]["required_data_kind"], "minute_bar_1m")
        self.assertEqual(record["raw_json"]["writes_outbox"], False)
        self.assertNotIn("event_id", record["raw_json"])

    def test_source_no_trade_proof_marks_partial_object_quality_visible(self) -> None:
        status, quality_status = classify_today_minute_object_status(
            actual_count=120,
            expected_count=190,
            error_message=None,
            quality_visible_no_trade_proof={"reason": "source_suspended", "identity_key": "stock:SZ:002217"},
        )

        self.assertEqual(status, "source_no_trade_quality_visible")
        self.assertEqual(quality_status, "source_no_trade_quality_visible")

    def test_non_suspended_missing_minutes_remain_partial(self) -> None:
        status, quality_status = classify_today_minute_object_status(
            actual_count=120,
            expected_count=190,
            error_message=None,
            quality_visible_no_trade_proof=None,
        )

        self.assertEqual(status, "partial")
        self.assertEqual(quality_status, "partial")

    def test_quality_visible_no_trade_is_reported_without_ordinary_partial_blocker(self) -> None:
        object_results = [
            {
                "asset_kind": "stock",
                "identity_key": "stock:SZ:002217",
                "status": "source_no_trade_quality_visible",
                "quality_status": "source_no_trade_quality_visible",
                "expected_bar_count": 190,
                "actual_bar_count": 120,
                "missing_bar_count": 70,
                "minute_rows_written": 120,
                "error_message": None,
                "quality_visible": {
                    "status": "source_no_trade",
                    "reason": "source_suspended",
                    "identity_key": "stock:SZ:002217",
                },
            }
        ]
        checks = build_post_execute_checks(
            plan=sample_c0_plan(),
            pre_backup={"outbox_rows_for_run": 0, "inbox_rows_for_run": 0, "active_snapshot": {"run": "before"}},
            data_snapshot={
                "target_today_minute_run_row_counts_by_asset": {
                    "stock": {"minute_row_count": 120, "minute_object_count": 1},
                    "index": {"minute_row_count": 0, "minute_object_count": 0},
                    "board": {"minute_row_count": 0, "minute_object_count": 0},
                },
                "duplicate_minute_key_count_by_asset": {"stock": 0, "index": 0, "board": 0},
                "physical_isolation_violation_count_by_asset": {"stock": 0, "index": 0, "board": 0},
                "outbox_rows_for_run": 0,
                "inbox_rows_for_run": 0,
                "active_snapshot": {"run": "before"},
            },
            object_results=object_results,
        )

        items = build_post_execute_quality_items(
            plan=sample_c0_plan(),
            post_checks=checks,
            object_results=object_results,
        )

        self.assertEqual(checks["n3_c1_partial_or_missing_objects"], 0)
        self.assertEqual(checks["n3_c1_quality_visible_no_trade_objects"], 1)
        self.assertIn("n3_c1_quality_visible_no_trade_objects", {item["gate_code"] for item in items})
        self.assertNotIn("n3_c1_partial_or_missing_objects", {item["gate_code"] for item in items})

    def test_ordinary_partial_object_is_p0_failed_quality_gate(self) -> None:
        object_results = [
            {
                "asset_kind": "stock",
                "identity_key": "stock:SH:600036",
                "status": "partial",
                "quality_status": "partial",
                "expected_bar_count": 190,
                "actual_bar_count": 120,
                "missing_bar_count": 70,
                "minute_rows_written": 120,
                "error_message": None,
            }
        ]
        checks = build_post_execute_checks(
            plan=sample_c0_plan(),
            pre_backup={"outbox_rows_for_run": 0, "inbox_rows_for_run": 0, "active_snapshot": {"run": "before"}},
            data_snapshot={
                "target_today_minute_run_row_counts_by_asset": {
                    "stock": {"minute_row_count": 120, "minute_object_count": 1},
                    "index": {"minute_row_count": 0, "minute_object_count": 0},
                    "board": {"minute_row_count": 0, "minute_object_count": 0},
                },
                "duplicate_minute_key_count_by_asset": {"stock": 0, "index": 0, "board": 0},
                "physical_isolation_violation_count_by_asset": {"stock": 0, "index": 0, "board": 0},
                "outbox_rows_for_run": 0,
                "inbox_rows_for_run": 0,
                "active_snapshot": {"run": "before"},
            },
            object_results=object_results,
        )

        items = build_post_execute_quality_items(
            plan=sample_c0_plan(),
            post_checks=checks,
            object_results=object_results,
        )
        partial_item = next(item for item in items if item["gate_code"] == "n3_c1_partial_or_missing_objects")

        self.assertEqual(checks["n3_c1_partial_or_missing_objects"], 1)
        self.assertEqual(partial_item["severity"], "P0")
        self.assertEqual(partial_item["status"], "failed")


class FakeMootdxClient:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows or [raw_minute_row()]
        self.calls: list[tuple[str, str, int]] = []

    def bars(self, *, symbol: str, frequency: int, start: int, offset: int) -> list[dict[str, object]]:
        self.calls.append(("bars", symbol, frequency))
        return list(self.rows)

    def index_bars(self, *, symbol: str, frequency: int, start: int, offset: int) -> list[dict[str, object]]:
        self.calls.append(("index_bars", symbol, frequency))
        return list(self.rows)


class FakeAdapter:
    source_version = "fake.today.minute.v1"
    external_source = "fake"


def sample_c0_plan() -> dict[str, object]:
    return {
        "stage": "N3-C0",
        "layer_role": "N3_market_data",
        "blocked": False,
        "source_market_data_run_id": "source",
        "today_minute_run_id": "today_minute_bar_1m_20260525_until_1411__source",
        "source_condition_run_id": "condition_layer",
        "source_trade_date": "20260522",
        "for_trade_date": "20260525",
        "prev_trade_date": "20260522",
        "latest_closed_minute": "2026-05-25T14:11:00+08:00",
        "expected_bar_count_per_object": 191,
        "expected_minute_rows": 191,
        "expected_minute_rows_by_asset_kind": {"stock": 191, "index": 0, "board": 0},
        "today_minute_object_count_by_asset_kind": {"stock": 1, "index": 0, "board": 0},
        "event_outbox_write_required_in_execute": False,
        "generated_event_types_for_execute": [],
        "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0},
        "execute_contract": {"writes_outbox": False},
    }


def sample_subscription() -> dict[str, object]:
    return {
        "subscription_id": 11,
        "pull_plan_id": 22,
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "exchange": "SH",
        "code": "600000",
        "display_code": "600000.SH",
        "name": "浦发银行",
        "source_scope_ids": [1],
        "source_condition_pool_ids": [101],
    }


def subscription(asset_kind: str, code: str) -> dict[str, object]:
    return {"asset_kind": asset_kind, "code": code}


def minute_row(value: str) -> dict[str, object]:
    return {
        "bar_time": datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=ASIA_SHANGHAI),
        "open": 10,
        "high": 10.1,
        "low": 9.9,
        "close": 10.05,
        "volume": 100,
        "amount": 1000,
        "raw_payload": {"datetime": value},
    }


def raw_minute_row(value: str = "2026-05-25 14:11") -> dict[str, object]:
    parsed = datetime.strptime(value, "%Y-%m-%d %H:%M")
    return {
        "datetime": value,
        "open": 10,
        "high": 10.1,
        "low": 9.9,
        "close": 10.05,
        "vol": 100,
        "amount": 1000,
        "year": parsed.year,
        "month": parsed.month,
        "day": parsed.day,
        "hour": parsed.hour,
        "minute": parsed.minute,
    }


if __name__ == "__main__":
    unittest.main()
