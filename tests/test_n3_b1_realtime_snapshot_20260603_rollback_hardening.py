import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROLLBACK_SQL = ROOT / "sql" / "N3_B1_realtime_snapshot_20260603_rollback.sql"
CONTRACT_JSON = ROOT / "docs" / "N3_B1_realtime_snapshot_20260603_execute_contract.json"
PREFLIGHT_JSON = ROOT / "docs" / "N3_B1_realtime_snapshot_20260603_execute_preflight.json"


class N3B1RealtimeSnapshot20260603RollbackHardeningTest(unittest.TestCase):
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

    def test_event_downstream_and_worker_guards_are_present(self) -> None:
        sql = self._sql()
        required_tokens = [
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "common_trigger_%",
            "common_action_%",
            "user_projection",
            "user_signal",
            "notification",
            "downstream_layers_touched",
            "worker_started",
        ]

        for token in required_tokens:
            with self.subTest(token=token):
                self.assertIn(token, sql)

    def test_delete_scope_excludes_event_and_downstream_tables(self) -> None:
        sql = self._executable_sql().lower()
        delete_targets = re.findall(r"\bdelete\s+from\s+([a-zA-Z0-9_]+)", sql)

        self.assertEqual(
            delete_targets,
            [
                "stock_realtime_daily_snapshot",
                "index_realtime_daily_snapshot",
                "board_realtime_daily_snapshot",
                "common_market_data_quality_item",
                "common_market_data_run",
            ],
        )

        forbidden_dml = [
            "delete from common_event_outbox",
            "delete from common_event_inbox",
            "delete from common_event_consumer_checkpoint",
            "update common_event_outbox",
            "update common_event_inbox",
            "update common_event_consumer_checkpoint",
            "delete from stock_minute_bar_1m",
            "delete from index_minute_bar_1m",
            "delete from board_minute_bar_1m",
            "delete from common_trigger_",
            "delete from common_action_",
            "delete from user_projection",
            "delete from user_signal",
            "delete from notification",
        ]

        for token in forbidden_dml:
            with self.subTest(token=token):
                self.assertNotIn(token, sql)

    def test_b1_artifacts_reference_the_hardened_rollback_sql(self) -> None:
        contract = json.loads(CONTRACT_JSON.read_text(encoding="utf-8"))
        preflight = json.loads(PREFLIGHT_JSON.read_text(encoding="utf-8"))

        self.assertEqual(
            contract["rollback_sql_path"],
            "sql/N3_B1_realtime_snapshot_20260603_rollback.sql",
        )
        self.assertTrue(preflight["ready"])
