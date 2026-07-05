import unittest

from ashare_v3.ingestion.trade_calendar_patch_20260527 import (
    ALLOWED_WRITE_TABLES,
    CalendarPatch20260527Blocked,
    build_calendar_patch_preflight,
    execute_patch_transaction,
    validate_execute_request,
)


def baseline_snapshot() -> dict:
    return {
        "target_calendar_rows": [],
        "target_active_rows": [],
        "patch_batch_conflict": [],
        "patch_active_conflict": [],
        "patch_quality_conflict_rows": 0,
        "calendar_window": [
            {
                "trade_date": "20260526",
                "exchange": "SSE",
                "is_open": True,
                "prev_trade_date": "20260525",
                "next_trade_date": "20260527",
                "source_version": "trade_calendar_20260526_patch_v1",
                "source_batch_id": "trade_calendar_20260526_patch_v1",
            }
        ],
        "outbox_rows_before": 74176,
    }


def tushare_source_result() -> dict:
    return {
        "available": True,
        "source": "tushare.trade_cal",
        "error": None,
        "rows": [
            {
                "trade_date": "20260527",
                "exchange": "SSE",
                "is_open": True,
                "prev_trade_date": "20260526",
                "next_trade_date": "20260528",
                "raw_payload": {
                    "exchange": "SSE",
                    "cal_date": "20260527",
                    "is_open": 1,
                    "pretrade_date": "20260526",
                },
            }
        ],
    }


class RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, sql: str, params: dict | tuple | None = None) -> None:
        self.statements.append(" ".join(sql.split()))


class RecordingConnection:
    def __init__(self) -> None:
        self.cursor_obj = RecordingCursor()
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> RecordingCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class TradeCalendarPatch20260527Tests(unittest.TestCase):
    def test_tushare_source_builds_passed_patch_plan(self) -> None:
        report = build_calendar_patch_preflight(
            snapshot=baseline_snapshot(),
            source_result=tushare_source_result(),
            allow_minimal_fallback=False,
        )

        self.assertEqual("PREFLIGHT_PASS", report["result"])
        self.assertTrue(report["tushare"]["available"])
        self.assertFalse(report["fallback"]["used"])
        self.assertEqual("trade_calendar_20260527_patch_v1", report["patch"]["source_batch_id"])
        self.assertEqual("SSE:20260527", report["scope_key"])
        self.assertEqual("20260526", report["patch"]["calendar_row"]["prev_trade_date"])
        self.assertEqual("20260528", report["patch"]["calendar_row"]["next_trade_date"])
        self.assertEqual(0, report["quality"]["p0_count"])
        self.assertEqual(0, report["quality"]["p2_count"])
        self.assertEqual(list(ALLOWED_WRITE_TABLES), report["future_write_scope"]["allowed_tables"])
        self.assertFalse(report["side_effects"]["writes_postgres"])
        self.assertFalse(report["side_effects"]["writes_parquet"])
        self.assertFalse(report["side_effects"]["enters_n2_n3_n4_n5_n6"])

    def test_previous_calendar_next_trade_date_guard_blocks_mismatch(self) -> None:
        snapshot = baseline_snapshot()
        snapshot["calendar_window"][0]["next_trade_date"] = "20260528"

        report = build_calendar_patch_preflight(
            snapshot=snapshot,
            source_result=tushare_source_result(),
            allow_minimal_fallback=False,
        )

        self.assertEqual("PREFLIGHT_BLOCKED", report["result"])
        self.assertIn("previous_next_trade_date_mismatch", report["blockers"])

    def test_fallback_requires_flag_and_records_p2_warning(self) -> None:
        unavailable = {"available": False, "source": "tushare.trade_cal", "error": "token missing", "rows": []}

        blocked = build_calendar_patch_preflight(
            snapshot=baseline_snapshot(),
            source_result=unavailable,
            allow_minimal_fallback=False,
        )
        self.assertEqual("PREFLIGHT_BLOCKED", blocked["result"])
        self.assertIn("tushare_calendar_unavailable", blocked["blockers"])

        fallback = build_calendar_patch_preflight(
            snapshot=baseline_snapshot(),
            source_result=unavailable,
            allow_minimal_fallback=True,
        )
        self.assertEqual("PREFLIGHT_PASS", fallback["result"])
        self.assertTrue(fallback["fallback"]["used"])
        self.assertEqual("manual.calendar_patch", fallback["patch"]["calendar_row"]["source"])
        self.assertEqual("20260526", fallback["patch"]["calendar_row"]["prev_trade_date"])
        self.assertEqual(1, fallback["quality"]["p2_count"])
        self.assertIn("manual_calendar_patch_used", [item["gate_name"] for item in fallback["quality"]["items"]])

    def test_execute_requires_all_flags(self) -> None:
        with self.assertRaises(CalendarPatch20260527Blocked):
            validate_execute_request(
                execute_requested=False,
                user_confirmed=True,
                postgres_commit_enabled=True,
            )
        with self.assertRaises(CalendarPatch20260527Blocked):
            validate_execute_request(
                execute_requested=True,
                user_confirmed=False,
                postgres_commit_enabled=True,
            )
        with self.assertRaises(CalendarPatch20260527Blocked):
            validate_execute_request(
                execute_requested=True,
                user_confirmed=True,
                postgres_commit_enabled=False,
            )

    def test_commit_sql_only_targets_allowed_tables(self) -> None:
        report = build_calendar_patch_preflight(
            snapshot=baseline_snapshot(),
            source_result=tushare_source_result(),
            allow_minimal_fallback=False,
        )
        conn = RecordingConnection()

        result = execute_patch_transaction(
            conn,
            report=report,
            execute_requested=True,
            user_confirmed=True,
            postgres_commit_enabled=True,
        )

        self.assertEqual("EXECUTE_PASS", result["result"])
        self.assertTrue(conn.committed)
        sql_text = "\n".join(conn.cursor_obj.statements)
        for table_name in ALLOWED_WRITE_TABLES:
            self.assertIn(table_name, sql_text)
        forbidden_tokens = [
            "stock_daily_bar_fact",
            "index_daily_bar_fact",
            "board_daily_bar_fact",
            "stock_daily_basic",
            "stock_financial_metrics_fact",
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
        ]
        for token in forbidden_tokens:
            self.assertNotIn(token, sql_text)


if __name__ == "__main__":
    unittest.main()
