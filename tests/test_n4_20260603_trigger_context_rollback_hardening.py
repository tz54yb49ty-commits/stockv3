import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROLLBACK_SQL = ROOT / "sql" / "N4_20260603_trigger_context_rebuild_rollback.sql"


class N4TriggerContext20260603RollbackHardeningTest(unittest.TestCase):
    def _sql(self) -> str:
        return ROLLBACK_SQL.read_text(encoding="utf-8")

    def _executable_sql(self) -> str:
        return "\n".join(
            line for line in self._sql().splitlines() if not line.lstrip().startswith("--")
        )

    def test_hard_fail_guard_raises_before_first_delete(self) -> None:
        sql = self._sql().lower()
        first_delete = re.search(r"\bdelete\s+from\b", sql)

        self.assertIsNotNone(first_delete, "rollback SQL must contain scoped DELETE statements")
        self.assertIn("do $$", sql)
        self.assertIn("raise exception", sql)
        self.assertLess(sql.index("raise exception"), first_delete.start())

    def test_downstream_guards_include_n4_n5_and_n6_refs(self) -> None:
        sql = self._sql()
        required_tokens = [
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "common_trigger_match",
            "common_trigger_state",
            "common_action_run",
            "common_action_event",
            "user_projection_run",
            "user_signal_projection",
            "user_signal_card",
            "user_notification_queue",
            "to_regclass('public.user_projection_run')",
            "to_regclass('public.user_signal_projection')",
            "to_regclass('public.user_signal_card')",
            "to_regclass('public.user_notification_queue')",
        ]

        for token in required_tokens:
            with self.subTest(token=token):
                self.assertIn(token, sql)

    def test_delete_scope_only_removes_context_rows(self) -> None:
        sql = self._executable_sql().lower()
        delete_targets = re.findall(r"\bdelete\s+from\s+([a-zA-Z0-9_]+)", sql)

        self.assertEqual(
            delete_targets,
            [
                "common_trigger_quality_item",
                "stock_trigger_context_snapshot",
                "index_trigger_context_snapshot",
                "board_trigger_context_snapshot",
                "common_trigger_run",
            ],
        )

        forbidden_dml = [
            "delete from common_event_outbox",
            "delete from common_event_inbox",
            "delete from common_event_consumer_checkpoint",
            "delete from common_trigger_state",
            "delete from common_trigger_match",
            "delete from common_action_run",
            "delete from common_action_event",
            "delete from user_projection_run",
            "delete from user_signal_projection",
            "delete from user_signal_card",
            "delete from user_notification_queue",
            "delete from common_condition_run",
            "delete from common_market_data_run",
            "delete from stock_realtime_daily_snapshot",
            "delete from index_realtime_daily_snapshot",
            "delete from board_realtime_daily_snapshot",
        ]

        for token in forbidden_dml:
            with self.subTest(token=token):
                self.assertNotIn(token, sql)


if __name__ == "__main__":
    unittest.main()
