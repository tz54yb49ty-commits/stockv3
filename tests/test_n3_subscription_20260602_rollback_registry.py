import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROLLBACK_SQL = ROOT / "sql/N3_subscription_20260602_rollback.sql"
EXECUTE_REPORT = ROOT / "docs/N3_subscription_20260602_execute_report.json"
RUN_ID = "market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1"


class N3Subscription20260602RollbackRegistryTest(unittest.TestCase):
    def test_rollback_sql_exists_and_hard_fails_before_delete(self) -> None:
        sql = ROLLBACK_SQL.read_text()

        self.assertIn(RUN_ID, sql)
        self.assertIn("RAISE EXCEPTION", sql)
        self.assertLess(sql.index("RAISE EXCEPTION"), sql.index("DELETE FROM"))
        self.assertIn("common_event_outbox", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)

    def test_rollback_sql_guards_downstream_and_fact_refs(self) -> None:
        sql = ROLLBACK_SQL.read_text()

        for token in [
            "stock_realtime_daily_snapshot",
            "index_realtime_daily_snapshot",
            "board_realtime_daily_snapshot",
            "stock_minute_bar_1m",
            "index_minute_bar_1m",
            "board_minute_bar_1m",
            "stock_action_confirmation_projection_metric",
            "index_action_confirmation_projection_metric",
            "board_action_confirmation_projection_metric",
            "trigger",
            "action",
            "user",
        ]:
            self.assertIn(token, sql)

    def test_rollback_sql_only_deletes_subscription_control_rows(self) -> None:
        sql = ROLLBACK_SQL.read_text()
        allowed_deletes = [
            "DELETE FROM common_market_data_pull_plan",
            "DELETE FROM common_market_data_subscription",
            "DELETE FROM common_market_data_subscription_candidate",
            "DELETE FROM common_market_data_quality_item",
            "DELETE FROM common_market_data_run",
        ]
        for statement in allowed_deletes:
            self.assertIn(statement, sql)
        for forbidden in [
            "DELETE FROM stock_realtime_daily_snapshot",
            "DELETE FROM index_realtime_daily_snapshot",
            "DELETE FROM board_realtime_daily_snapshot",
            "DELETE FROM stock_minute_bar_1m",
            "DELETE FROM index_minute_bar_1m",
            "DELETE FROM board_minute_bar_1m",
            "DELETE FROM stock_action_confirmation_projection_metric",
            "UPDATE common_event_outbox",
        ]:
            self.assertNotIn(forbidden, sql)

    def test_execute_report_registers_rollback_sql_path(self) -> None:
        report = json.loads(EXECUTE_REPORT.read_text())

        self.assertEqual(report["market_data_run_id"], RUN_ID)
        self.assertEqual(report["rollback_sql_path"], "sql/N3_subscription_20260602_rollback.sql")
        self.assertEqual(report["rollback"]["rollback_sql_path"], "sql/N3_subscription_20260602_rollback.sql")
        self.assertTrue(report["rollback"]["rollback_safe"])


if __name__ == "__main__":
    unittest.main()
