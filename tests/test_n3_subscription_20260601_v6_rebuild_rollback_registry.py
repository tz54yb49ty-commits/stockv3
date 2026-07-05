import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROLLBACK_SQL = ROOT / "sql/N3_subscription_20260601_v6_rebuild_20260602_rollback.sql"
REGISTRY_JSON = ROOT / "docs/N3_subscription_20260601_v6_rebuild_20260602_rollback_registry.json"
PREFLIGHT_JSON = ROOT / "docs/N3_latest_N2_v6_rebuild_preflight.json"
RUN_ID = "market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6_rebuild_20260602_v1"
OLD_RUN_ID = "market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6"


class N3Subscription20260601V6RebuildRollbackRegistryTest(unittest.TestCase):
    def test_rollback_sql_exists_and_hard_fails_before_delete(self) -> None:
        sql = ROLLBACK_SQL.read_text()

        self.assertIn(RUN_ID, sql)
        self.assertIn("RAISE EXCEPTION", sql)
        self.assertLess(sql.index("RAISE EXCEPTION"), sql.index("DELETE FROM"))
        for token in [
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
        ]:
            self.assertIn(token, sql)

    def test_rollback_guards_downstream_refs(self) -> None:
        sql = ROLLBACK_SQL.read_text()

        for token in [
            "common_market_data_run",
            "stock_realtime_daily_snapshot",
            "index_realtime_daily_snapshot",
            "board_realtime_daily_snapshot",
            "stock_minute_bar_1m",
            "index_minute_bar_1m",
            "board_minute_bar_1m",
            "stock_previous_day_minute_preload_status",
            "stock_realtime_projection_metric",
            "stock_action_confirmation_projection_metric",
            "stock_eod_snapshot",
            "trigger",
            "action",
            "user",
            "voice",
            "mobile",
            "sim",
            "position",
            "trade",
        ]:
            self.assertIn(token, sql)

    def test_rollback_sql_only_deletes_subscription_control_rows(self) -> None:
        sql = ROLLBACK_SQL.read_text()

        for statement in [
            "DELETE FROM common_market_data_pull_plan",
            "DELETE FROM common_market_data_subscription",
            "DELETE FROM common_market_data_subscription_candidate",
            "DELETE FROM common_market_data_quality_item",
            "DELETE FROM common_market_data_run",
        ]:
            self.assertIn(statement, sql)
        for forbidden in [
            "DELETE FROM stock_realtime_daily_snapshot",
            "DELETE FROM index_realtime_daily_snapshot",
            "DELETE FROM board_realtime_daily_snapshot",
            "DELETE FROM stock_minute_bar_1m",
            "DELETE FROM stock_realtime_projection_metric",
            "DELETE FROM stock_action_confirmation_projection_metric",
            "DELETE FROM stock_eod_snapshot",
            "UPDATE common_event_outbox",
        ]:
            self.assertNotIn(forbidden, sql)

    def test_rollback_does_not_target_old_run_id(self) -> None:
        sql = ROLLBACK_SQL.read_text()

        self.assertIn(RUN_ID, sql)
        self.assertNotIn(f"'{OLD_RUN_ID}'", sql)

    def test_registry_and_preflight_register_rollback_sql_path(self) -> None:
        registry = json.loads(REGISTRY_JSON.read_text())
        preflight = json.loads(PREFLIGHT_JSON.read_text())

        self.assertEqual(registry["market_data_run_id"], RUN_ID)
        self.assertEqual(
            registry["rollback_sql_path"],
            "sql/N3_subscription_20260601_v6_rebuild_20260602_rollback.sql",
        )
        self.assertEqual(
            preflight["rollback_registry"]["rollback_sql_path"],
            registry["rollback_sql_path"],
        )
        self.assertTrue(registry["rollback_safe_before_execute"])


if __name__ == "__main__":
    unittest.main()
