from pathlib import Path
import tempfile
import unittest

from ashare_v3.runtime_control.intraday import (
    build_intraday_pipeline_readiness,
    expected_intraday_run_ids,
    rollback_has_hard_fail_before_delete,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RuntimeIntradayPipelineCheckerTest(unittest.TestCase):
    def test_expected_run_ids_are_stable_for_b1_to_n5(self) -> None:
        run_ids = expected_intraday_run_ids(
            for_trade_date="20260602",
            minute_label="1105",
            condition_run_id="condition_layer_20260601_source_20260601_v1",
            b1_label="live3_outbox",
        )

        self.assertEqual(
            run_ids["subscription_run_id"],
            "market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1",
        )
        self.assertEqual(
            run_ids["b1_snapshot_run_id"],
            "realtime_snapshot_20260602_live3_outbox_"
            "market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1",
        )
        self.assertEqual(
            run_ids["c1_today_minute_run_id"],
            "today_minute_bar_1m_20260602_until_1105__"
            "market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1",
        )
        self.assertEqual(
            run_ids["n4_execute_run_id"],
            "trigger_action_confirmation_metric_execute_20260602_1105__"
            "condition_layer_20260601_source_20260601_v1",
        )
        self.assertEqual(
            run_ids["n5_action_run_id"],
            "action_consumer_action_confirmation_metric_execute_20260602_1105__"
            "trigger_action_confirmation_metric_execute_20260602_1105__"
            "condition_layer_20260601_source_20260601_v1",
        )

    def test_checker_reports_current_20260602_chain_with_warnings_only(self) -> None:
        report = build_intraday_pipeline_readiness(
            for_trade_date="20260602",
            minute_label="1105",
            condition_run_id="condition_layer_20260601_source_20260601_v1",
            b1_label="live3_outbox",
            docs_dir=PROJECT_ROOT / "docs",
            sql_dir=PROJECT_ROOT / "sql",
        )

        self.assertEqual(report["result"], "WARNING")
        self.assertEqual(report["blockers"], [])
        self.assertTrue(report["warnings"])
        self.assertEqual(
            [stage["stage_id"] for stage in report["stages"]],
            ["b1", "c1", "n3_action_confirmation_projection", "n4", "n5"],
        )
        self.assertTrue(all(stage["status"] in {"PASS", "WARNING"} for stage in report["stages"]))
        self.assertEqual(report["rollback_registry"]["missing_paths"], [])
        self.assertEqual(report["run_id_rules"]["status"], "PASS")
        self.assertEqual(report["excluded_lanes"]["c2_closed_30m"], "separate_gate")
        self.assertEqual(report["excluded_lanes"]["c3_minute_bar_closed"], "separate_gate")
        self.assertFalse(report["side_effects"]["writes_database"])
        self.assertFalse(report["side_effects"]["executes_n3_n5"])
        self.assertFalse(report["side_effects"]["starts_worker"])
        self.assertFalse(report["side_effects"]["triggers_delivery_or_notification"])
        self.assertEqual(report["event_summary"]["n5_pending_outbox"]["ActionExecuted"], 4)
        self.assertEqual(report["event_summary"]["n5_pending_outbox"]["ActionBlocked"], 1)

    def test_checker_blocks_when_required_intraday_rollback_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sql_dir = Path(tmp)
            for required in (
                "N3_B1_realtime_snapshot_20260602_live3_outbox_rollback.sql",
                "N3_C1_today_minute_bar_1m_20260602_until_1105_rollback.sql",
                "N3_action_confirmation_projection_metric_business_rollback.sql",
                "N4_action_confirmation_metric_business_execute_rollback.sql",
            ):
                (sql_dir / required).write_text("DO $$ BEGIN RAISE EXCEPTION 'blocked'; END $$;\n", encoding="utf-8")

            report = build_intraday_pipeline_readiness(
                for_trade_date="20260602",
                minute_label="1105",
                condition_run_id="condition_layer_20260601_source_20260601_v1",
                b1_label="live3_outbox",
                docs_dir=PROJECT_ROOT / "docs",
                sql_dir=sql_dir,
            )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn(
            "sql/N5_20260602_action_confirmation_metric_execute_rollback.sql",
            report["missing_rollback_paths"],
        )

    def test_rollback_hard_fail_check_ignores_delete_in_sql_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rollback.sql"
            path.write_text(
                "-- This comment mentions DELETE before the guard.\n"
                "DO $$ BEGIN RAISE EXCEPTION 'blocked'; END $$;\n"
                "DELETE FROM scoped_table;\n",
                encoding="utf-8",
            )

            self.assertTrue(rollback_has_hard_fail_before_delete(path))

    def test_c1_rollback_sql_has_downstream_hard_fail_guards(self) -> None:
        path = PROJECT_ROOT / "sql" / "N3_C1_today_minute_bar_1m_20260602_until_1105_rollback.sql"
        sql = path.read_text(encoding="utf-8")

        self.assertTrue(rollback_has_hard_fail_before_delete(path))
        self.assertIn("RAISE EXCEPTION", sql)
        self.assertIn("common_event_outbox", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)
        self.assertIn("stock_closed_30m_summary", sql)
        self.assertIn("MinuteBarClosed", sql)
        self.assertIn("action_confirmation_projection_metric", sql)
        self.assertIn("common_trigger_run", sql)
        self.assertIn("common_action_run", sql)
        self.assertIn("user_projection_run", sql)
        self.assertIn("voice", sql)
        self.assertIn("mobile", sql)
        self.assertIn("sim", sql)
        self.assertIn("position", sql)
        self.assertIn("worker_started", sql)
        self.assertIn("downstream_layers_touched", sql)
        self.assertIn("run_id = :'today_minute_run_id'", sql)
        self.assertNotIn("DELETE FROM common_trigger_run", sql)
        self.assertNotIn("DELETE FROM common_action_run", sql)
        self.assertNotIn("DELETE FROM user_projection_run", sql)

    def test_b1_rollback_sql_has_downstream_hard_fail_guards(self) -> None:
        path = PROJECT_ROOT / "sql" / "N3_B1_realtime_snapshot_20260602_live3_outbox_rollback.sql"
        sql = path.read_text(encoding="utf-8")

        self.assertTrue(rollback_has_hard_fail_before_delete(path))
        self.assertIn("RAISE EXCEPTION", sql)
        self.assertIn("status IN ('delivering', 'delivered')", sql)
        self.assertIn("common_event_outbox", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)
        self.assertIn("action_confirmation_projection_metric", sql)
        self.assertIn("common_trigger_run", sql)
        self.assertIn("common_action_run", sql)
        self.assertIn("user_projection_run", sql)
        self.assertIn("voice", sql)
        self.assertIn("mobile", sql)
        self.assertIn("sim", sql)
        self.assertIn("position", sql)
        self.assertIn("worker_started", sql)
        self.assertIn("downstream_layers_touched", sql)
        self.assertIn("run_id = :'snapshot_run_id'", sql)
        self.assertNotIn("DELETE FROM common_trigger_run", sql)
        self.assertNotIn("DELETE FROM common_action_run", sql)
        self.assertNotIn("DELETE FROM user_projection_run", sql)


if __name__ == "__main__":
    unittest.main()
