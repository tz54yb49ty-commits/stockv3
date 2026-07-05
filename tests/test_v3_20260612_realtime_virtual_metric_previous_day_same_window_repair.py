import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_JSON = ROOT / "docs/V3_20260612_REALTIME_VIRTUAL_METRIC_PREVIOUS_DAY_SAME_WINDOW_AMOUNT_REPAIR.json"
REPORT_MD = ROOT / "docs/V3_20260612_REALTIME_VIRTUAL_METRIC_PREVIOUS_DAY_SAME_WINDOW_AMOUNT_REPAIR.md"
REPAIR_SQL = ROOT / "sql/V3_20260612_realtime_virtual_metric_previous_day_same_window_amount_repair.sql"
CONTRACT_JSON = ROOT / "docs/V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_RUNNER_CONTRACT.json"
PREFLIGHT_JSON = ROOT / "docs/V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_RUNNER_PREFLIGHT.json"


class V320260612RealtimeVirtualMetricPreviousDaySameWindowRepairTest(unittest.TestCase):
    def test_repair_artifacts_freeze_schema_and_payload_coverage(self) -> None:
        report = json.loads(REPORT_JSON.read_text())

        self.assertEqual(report["result"], "REPAIR_PASS")
        self.assertEqual(report["layer_role"], "N3_market_data")
        self.assertEqual(report["target_run_id"], "action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__condition_layer_20260611_source_20260611_for_20260612_v1")
        self.assertEqual(report["payload_coverage"]["rows_total"], 100)
        self.assertEqual(report["payload_coverage"]["previous_day_same_window_amount_non_null"], 100)
        self.assertEqual(report["payload_coverage"]["by_asset_kind"], {"board": 38, "index": 0, "stock": 62})
        self.assertEqual(report["live_schema_before_repair"]["missing_column_tables"], [
            "board_action_confirmation_projection_metric",
            "index_action_confirmation_projection_metric",
            "stock_action_confirmation_projection_metric",
        ])
        self.assertEqual(report["repair_sql"], str(REPAIR_SQL.relative_to(ROOT)))
        self.assertEqual(report["guard_policy"]["n4_refs"], "allowed_reviewed_refs_preserved")
        self.assertEqual(report["guard_policy"]["n5_n6_user_sim_voice_mobile_refs"], "hard_fail")
        self.assertFalse(report["side_effects"]["database_written"])
        self.assertFalse(report["side_effects"]["n4_n5_executed"])

    def test_contract_and_preflight_require_same_window_amount_policy(self) -> None:
        contract = json.loads(CONTRACT_JSON.read_text())
        preflight = json.loads(PREFLIGHT_JSON.read_text())

        for artifact in (contract, preflight):
            policy = artifact["previous_day_same_window_amount_policy"]
            self.assertTrue(policy["required_for_metric_ready_rows"])
            self.assertEqual(policy["writer_validation_blocker"], "previous_day_same_window_amount_missing")
            self.assertEqual(policy["expected_non_null_rows"], 100)
            self.assertEqual(policy["materialized_payload_check"]["non_null_rows"], 100)
            self.assertEqual(policy["materialized_payload_check"]["missing_rows"], 0)

    def test_repair_sql_is_additive_scoped_and_hard_fails_by_default(self) -> None:
        sql = REPAIR_SQL.read_text()
        first_raise = sql.index("RAISE EXCEPTION")
        first_alter = sql.index("ALTER TABLE")
        first_update = sql.index("UPDATE")

        self.assertLess(first_raise, first_alter)
        self.assertLess(first_raise, first_update)
        self.assertIn("previous_day_same_window_amount repair blocked by default", sql)
        self.assertIn("allow_reviewed_n4_refs", sql)
        self.assertIn("reviewed_n4_trigger_refs", sql)
        self.assertIn("TriggerMatched", sql)
        self.assertIn("TriggerStateChanged", sql)
        self.assertIn("TriggerPendingMarketData", sql)
        self.assertNotIn("repair blocked: common_trigger_match refs", sql)
        for asset in ("stock", "index", "board"):
            table = f"{asset}_action_confirmation_projection_metric"
            self.assertIn(f"ALTER TABLE {table}", sql)
            self.assertIn("ADD COLUMN IF NOT EXISTS previous_day_same_window_amount NUMERIC", sql)
            self.assertIn(f"UPDATE {table}", sql)
            self.assertIn("projection_run_id = current_setting('ashare_v3.repair_target_run_id')", sql)
        self.assertIn("expected total rows 100", sql)
        self.assertNotRegex(sql.upper(), r"\b(CASCADE|TRUNCATE|DROP)\b")
        for downstream_guard in (
            "common_action_event",
            "user_signal_projection",
            "user_signal_card",
            "user_notification_queue",
            "user_sim_order",
            "user_sim_trade",
            "user_sim_position",
            "n6_virtual_account",
            "n6_virtual_order",
            "n6_virtual_trade",
            "n6_virtual_position",
            "n6_virtual_position_event",
            "n6_virtual_pnl_snapshot",
        ):
            self.assertIn(downstream_guard, sql)
        self.assertIsNone(
            re.search(
                r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(common_event_outbox|common_event_inbox|common_event_consumer_checkpoint)",
                sql,
                flags=re.IGNORECASE,
            )
        )
        self.assertIsNone(
            re.search(
                r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(common_trigger_|common_action_|user_|n6_|sim_)",
                sql,
                flags=re.IGNORECASE,
            )
        )

    def test_markdown_records_forbidden_scope(self) -> None:
        md = REPORT_MD.read_text()

        self.assertIn("不执行 N4/N5", md)
        self.assertIn("不消费/update outbox/inbox/checkpoint", md)
        self.assertIn("不进入 N6/voice/mobile/sim/position/order/trade", md)
        self.assertIn("runtime_control", md)


if __name__ == "__main__":
    unittest.main()
