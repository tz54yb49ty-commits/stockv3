import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLEANUP_SQL = ROOT / "sql" / "N3_20260612_B1_fact_only_failed_runs_cleanup.sql"


class N3B1FactOnly20260612CleanupSqlTest(unittest.TestCase):
    def test_cleanup_sql_hard_fails_before_first_delete(self) -> None:
        sql = CLEANUP_SQL.read_text(encoding="utf-8")
        executable_sql = "\n".join(
            line for line in sql.splitlines() if not line.strip().startswith("--")
        )

        self.assertIn("RAISE EXCEPTION", executable_sql)
        self.assertIn("DELETE FROM", executable_sql)
        self.assertLess(executable_sql.index("RAISE EXCEPTION"), executable_sql.index("DELETE FROM"))

    def test_cleanup_sql_uses_runtime_schema_run_id_scope(self) -> None:
        sql = CLEANUP_SQL.read_text(encoding="utf-8")

        self.assertIn("DELETE FROM stock_realtime_daily_snapshot\nWHERE run_id = ANY", sql)
        self.assertIn("DELETE FROM index_realtime_daily_snapshot\nWHERE run_id = ANY", sql)
        self.assertIn("DELETE FROM board_realtime_daily_snapshot\nWHERE run_id = ANY", sql)
        self.assertIn("DELETE FROM common_market_data_quality_item\nWHERE run_id = ANY", sql)
        self.assertNotIn("snapshot_run_id =", sql)
        self.assertNotIn("common_market_data_quality_item WHERE run_id =", sql)
        self.assertNotIn("source_run_id = 'realtime_daily_snapshot_20260612", sql)

    def test_cleanup_sql_guards_event_infra_and_downstream_refs(self) -> None:
        sql = CLEANUP_SQL.read_text(encoding="utf-8")

        for token in [
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "stock_realtime_projection_metric",
            "index_realtime_projection_metric",
            "board_realtime_projection_metric",
            "common_trigger_state",
            "common_trigger_match",
            "common_action_confirmation",
            "common_action_event",
            "user_signal_projection",
            "user_signal_card",
            "user_notification_queue",
            "user_sim_order",
            "n6_virtual_order",
            "n6_virtual_position",
        ]:
            self.assertIn(token, sql)

        upper = sql.upper()
        self.assertNotIn("DROP ", upper)
        self.assertNotIn("TRUNCATE", upper)
        self.assertNotIn("CASCADE", upper)


if __name__ == "__main__":
    unittest.main()
