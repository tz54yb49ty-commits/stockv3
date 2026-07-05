import unittest

from ashare_v3.ingestion.trade_calendar_patch_generic import (
    ALLOWED_WRITE_TABLES,
    CalendarPatchGenericBlocked,
    TradeCalendarPatchConfig,
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
                "trade_date": "20260529",
                "exchange": "SSE",
                "is_open": True,
                "prev_trade_date": "20260528",
                "next_trade_date": "20260601",
                "source_version": "trade_calendar_20260529_patch_v1",
                "source_batch_id": "trade_calendar_20260529_patch_v1",
            }
        ],
        "outbox_rows_before": 151341,
    }


def tushare_source_result() -> dict:
    return {
        "available": True,
        "source": "tushare.trade_cal",
        "error": None,
        "rows": [
            {
                "trade_date": "20260601",
                "exchange": "SSE",
                "is_open": True,
                "prev_trade_date": "20260529",
                "next_trade_date": "20260602",
                "raw_payload": {
                    "exchange": "SSE",
                    "cal_date": "20260601",
                    "is_open": 1,
                    "pretrade_date": "20260529",
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


class TradeCalendarPatchGenericTests(unittest.TestCase):
    def test_20260601_tushare_source_builds_passed_patch_plan(self) -> None:
        config = TradeCalendarPatchConfig(
            trade_date="20260601",
            expected_prev_trade_date="20260529",
            fallback_next_trade_date="20260602",
        )

        report = build_calendar_patch_preflight(
            config=config,
            snapshot=baseline_snapshot(),
            source_result=tushare_source_result(),
            allow_minimal_fallback=False,
        )

        self.assertEqual("PREFLIGHT_PASS", report["result"])
        self.assertEqual("N1 trade calendar 20260601 patch preflight", report["stage"])
        self.assertEqual("trade_calendar_20260601_patch_v1", report["patch"]["source_batch_id"])
        self.assertEqual("SSE:20260601", report["scope_key"])
        self.assertEqual("20260529", report["patch"]["calendar_row"]["prev_trade_date"])
        self.assertEqual("20260602", report["patch"]["calendar_row"]["next_trade_date"])
        self.assertEqual(0, report["quality"]["p0_count"])
        self.assertEqual(list(ALLOWED_WRITE_TABLES), report["future_write_scope"]["allowed_tables"])
        self.assertFalse(report["side_effects"]["writes_postgres"])
        self.assertFalse(report["side_effects"]["enters_n2_n3_n4_n5_n6"])

    def test_previous_calendar_next_trade_date_guard_blocks_mismatch(self) -> None:
        config = TradeCalendarPatchConfig(
            trade_date="20260601",
            expected_prev_trade_date="20260529",
            fallback_next_trade_date="20260602",
        )
        snapshot = baseline_snapshot()
        snapshot["calendar_window"][0]["next_trade_date"] = "20260602"

        report = build_calendar_patch_preflight(
            config=config,
            snapshot=snapshot,
            source_result=tushare_source_result(),
            allow_minimal_fallback=False,
        )

        self.assertEqual("PREFLIGHT_BLOCKED", report["result"])
        self.assertIn("previous_next_trade_date_mismatch", report["blockers"])

    def test_execute_requires_all_flags(self) -> None:
        with self.assertRaises(CalendarPatchGenericBlocked):
            validate_execute_request(
                execute_requested=False,
                user_confirmed=True,
                postgres_commit_enabled=True,
            )
        with self.assertRaises(CalendarPatchGenericBlocked):
            validate_execute_request(
                execute_requested=True,
                user_confirmed=False,
                postgres_commit_enabled=True,
            )
        with self.assertRaises(CalendarPatchGenericBlocked):
            validate_execute_request(
                execute_requested=True,
                user_confirmed=True,
                postgres_commit_enabled=False,
            )

    def test_commit_sql_only_targets_allowed_tables(self) -> None:
        config = TradeCalendarPatchConfig(
            trade_date="20260601",
            expected_prev_trade_date="20260529",
            fallback_next_trade_date="20260602",
        )
        report = build_calendar_patch_preflight(
            config=config,
            snapshot=baseline_snapshot(),
            source_result=tushare_source_result(),
            allow_minimal_fallback=False,
        )
        conn = RecordingConnection()

        result = execute_patch_transaction(
            config=config,
            conn=conn,
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
        for token in (
            "stock_daily_bar_fact",
            "index_daily_bar_fact",
            "board_daily_bar_fact",
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
        ):
            self.assertNotIn(token, sql_text)


if __name__ == "__main__":
    unittest.main()
