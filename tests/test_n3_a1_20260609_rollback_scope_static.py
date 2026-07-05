from pathlib import Path
import unittest


ROLLBACK_SQL = Path("sql/N3_A1_previous_day_minute_20260609_rollback.sql")


class N3A120260609RollbackScopeStaticTest(unittest.TestCase):
    def test_rollback_hard_fails_before_stage_deletes(self) -> None:
        sql = ROLLBACK_SQL.read_text(encoding="utf-8")
        prefix = sql[: sql.upper().index("DELETE FROM")]

        self.assertIn("RAISE EXCEPTION", prefix)
        self.assertIn("v_subscription_run_id", prefix)
        self.assertIn("v_preload_run_id", prefix)
        self.assertIn("common_event_outbox", prefix)
        self.assertIn("common_event_inbox", prefix)
        self.assertIn("common_event_consumer_checkpoint", prefix)
        self.assertIn("downstream_layers_touched", prefix)
        self.assertIn("worker_started", prefix)
        self.assertIn("stock_realtime_daily_snapshot", prefix)
        self.assertIn("stock_realtime_projection_metric", prefix)
        self.assertIn("common_trigger_state", prefix)
        self.assertIn("common_action_run", prefix)
        self.assertIn("user_signal_projection", prefix)
        self.assertIn("n6_virtual_order", prefix)

    def test_rollback_contains_stage2_and_stage1_delete_scopes(self) -> None:
        sql = ROLLBACK_SQL.read_text(encoding="utf-8")

        for table_name in (
            "stock_previous_day_minute_preload_status",
            "index_previous_day_minute_preload_status",
            "board_previous_day_minute_preload_status",
            "stock_minute_bar_1m",
            "index_minute_bar_1m",
            "board_minute_bar_1m",
        ):
            self.assertIn(f"DELETE FROM {table_name}", sql)

        self.assertIn("raw_json ->> 'source_run_id' = :'source_run_id'", sql)
        self.assertIn("raw_json ->> 'preload_run_id' = :'preload_run_id'", sql)

        for table_name in (
            "common_market_data_pull_plan",
            "common_market_data_subscription",
            "common_market_data_subscription_candidate",
        ):
            self.assertIn(f"DELETE FROM {table_name}", sql)
            self.assertIn("run_id = :'subscription_run_id'", sql)

        self.assertIn("WHERE run_id = :'preload_run_id'", sql)
        self.assertIn("WHERE run_id = :'subscription_run_id'", sql)

    def test_rollback_does_not_mutate_event_infra_or_use_destructive_ddl(self) -> None:
        sql = ROLLBACK_SQL.read_text(encoding="utf-8").lower()

        forbidden = (
            "delete from common_event_outbox",
            "delete from common_event_inbox",
            "delete from common_event_consumer_checkpoint",
            "update common_event_outbox",
            "update common_event_inbox",
            "update common_event_consumer_checkpoint",
            "truncate",
            " drop ",
            " cascade",
        )
        for snippet in forbidden:
            self.assertNotIn(snippet, sql)


if __name__ == "__main__":
    unittest.main()
