from pathlib import Path
import unittest

from ashare_v3.runtime_control.pipeline import (
    WAIT_MANUAL_CONFIRM,
    build_action_confirmation_pipeline_run,
    build_nightly_pipeline_run,
    render_dashboard_markdown,
)
from ashare_v3.runtime_control.registry import (
    build_action_confirmation_execute_command_registry,
    build_action_confirmation_rollback_registry,
    build_default_execute_command_registry,
    build_default_rollback_registry,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RuntimePipelineControlTest(unittest.TestCase):
    def test_nightly_pipeline_run_covers_current_fact_only_sequence(self) -> None:
        run = build_nightly_pipeline_run(trade_date="20260527")

        self.assertEqual(run.layer_role, "runtime_control")
        self.assertEqual(run.pipeline_name, "nightly_runtime_v0")
        self.assertEqual(
            [stage.stage_id for stage in run.stages],
            [
                "calendar",
                "n1_official_daily",
                "n1_condition_source",
                "n2_condition_layer",
                "n3_subscription",
                "a1_previous_day_preload",
                "b1_realtime_snapshot_fact_only",
            ],
        )
        self.assertTrue(all(not stage.modifies_execute_contract for stage in run.stages))
        self.assertTrue(all(not stage.starts_worker for stage in run.stages))

    def test_action_confirmation_pipeline_run_covers_20260602_run_once_chain(self) -> None:
        run = build_action_confirmation_pipeline_run(trade_date="20260602")

        self.assertEqual(run.layer_role, "runtime_control")
        self.assertEqual(run.pipeline_name, "action_confirmation_runtime_v0_2")
        self.assertEqual(
            [stage.stage_id for stage in run.stages],
            [
                "n2_condition_layer_active",
                "n3_subscription",
                "n3_a1_previous_day_preload",
                "n3_b1_live3_snapshot",
                "n3_c1_today_minute",
                "n3_action_confirmation_projection",
                "n4_action_confirmation_metric_execute",
                "n5_action_confirmation_metric_execute",
                "n6_shadow_projection",
            ],
        )
        self.assertTrue(all(not stage.modifies_execute_contract for stage in run.stages))
        self.assertTrue(all(not stage.starts_worker for stage in run.stages))
        self.assertFalse(run.side_effects["executes_commands"])
        self.assertFalse(run.side_effects["starts_worker"])

    def test_wait_manual_confirm_blocks_execute_until_user_confirms(self) -> None:
        run = build_nightly_pipeline_run(trade_date="20260527")
        manual_stage = run.stage_by_id("b1_realtime_snapshot_fact_only")

        self.assertEqual(manual_stage.status, WAIT_MANUAL_CONFIRM)
        self.assertTrue(manual_stage.requires_manual_confirm)
        self.assertFalse(manual_stage.can_execute(user_confirmed=False))
        self.assertTrue(manual_stage.can_execute(user_confirmed=True))

    def test_execute_command_registry_records_existing_commands_without_running(self) -> None:
        registry = build_default_execute_command_registry(trade_date="20260527")

        self.assertGreaterEqual(
            set(registry),
            {
                "calendar",
                "n1_official_daily",
                "n1_condition_source",
                "n2_condition_layer",
                "n3_subscription",
                "a1_previous_day_preload",
                "b1_realtime_snapshot_fact_only",
            },
        )
        b1 = registry["b1_realtime_snapshot_fact_only"]
        self.assertEqual(b1.command[0], "python3")
        self.assertIn("scripts/run_realtime_daily_snapshot_once.py", b1.command)
        self.assertIn("--no-outbox", b1.command)
        self.assertTrue(b1.requires_manual_confirm)
        self.assertFalse(b1.has_side_effects_in_registry)
        self.assertFalse(b1.modifies_execute_contract)

    def test_action_confirmation_command_registry_records_copy_text_without_running(self) -> None:
        registry = build_action_confirmation_execute_command_registry(trade_date="20260602")

        self.assertIn("n6_shadow_projection", registry)
        n6 = registry["n6_shadow_projection"]
        self.assertIn("scripts/run_n6_projection_once.py", n6.command)
        self.assertIn("--expected-n5-outbox-count", n6.command)
        self.assertTrue(n6.requires_manual_confirm)
        self.assertFalse(n6.has_side_effects_in_registry)
        self.assertFalse(n6.starts_worker)

    def test_rollback_registry_maps_stage_to_reviewed_sql_path(self) -> None:
        registry = build_default_rollback_registry(trade_date="20260527")

        self.assertEqual(registry["calendar"].rollback_sql_path, "sql/N1_trade_calendar_20260527_patch_rollback.sql")
        self.assertEqual(registry["n3_subscription"].rollback_sql_path, "sql/N3_subscription_20260527_rollback.sql")
        self.assertEqual(
            registry["a1_previous_day_preload"].rollback_sql_path,
            "sql/N3_A1_previous_day_minute_20260527_rollback.sql",
        )
        self.assertEqual(
            registry["b1_realtime_snapshot_fact_only"].rollback_sql_path,
            "sql/N3_B1_realtime_snapshot_20260527_rollback.sql",
        )
        self.assertTrue(all(not item.executes_rollback for item in registry.values()))

    def test_action_confirmation_rollback_registry_maps_complete_chain(self) -> None:
        registry = build_action_confirmation_rollback_registry(trade_date="20260602")

        self.assertEqual(
            registry["n2_condition_layer_active"].rollback_sql_path,
            "sql/N2_condition_layer_20260601_to_20260602_rollback.sql",
        )
        self.assertEqual(
            registry["n3_subscription"].rollback_sql_path,
            "sql/N3_subscription_20260602_rollback.sql",
        )
        self.assertEqual(
            registry["n3_action_confirmation_projection"].rollback_sql_path,
            "sql/N3_action_confirmation_projection_metric_business_rollback.sql",
        )
        self.assertEqual(
            registry["n5_action_confirmation_metric_execute"].rollback_sql_path,
            "sql/N5_20260602_action_confirmation_metric_execute_rollback.sql",
        )
        self.assertEqual(
            registry["n6_shadow_projection"].rollback_sql_path,
            "sql/N6_projection_business_rollback.sql",
        )
        self.assertTrue(all(not item.executes_rollback for item in registry.values()))

    def test_dashboard_markdown_contains_timeline_and_no_execute_boundary(self) -> None:
        run = build_nightly_pipeline_run(trade_date="20260527")
        dashboard = render_dashboard_markdown(run)

        self.assertIn("# Runtime Pipeline Dashboard v0", dashboard)
        self.assertIn("layer_role=runtime_control", dashboard)
        self.assertIn("WAIT_MANUAL_CONFIRM", dashboard)
        self.assertIn("b1_realtime_snapshot_fact_only", dashboard)
        self.assertIn("does not execute nightly run", dashboard)
        self.assertIn("does not modify N1-N6 execute contracts", dashboard)

    def test_runtime_pipeline_schema_draft_contains_required_tables(self) -> None:
        sql = (PROJECT_ROOT / "sql" / "021_runtime_pipeline_control_schema.sql").read_text()

        self.assertIn("CREATE TABLE IF NOT EXISTS runtime_pipeline_run", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS runtime_pipeline_stage", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS runtime_execute_command_registry", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS runtime_rollback_registry", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS runtime_pipeline_timeline", sql)
        self.assertIn("WAIT_MANUAL_CONFIRM", sql)


if __name__ == "__main__":
    unittest.main()
