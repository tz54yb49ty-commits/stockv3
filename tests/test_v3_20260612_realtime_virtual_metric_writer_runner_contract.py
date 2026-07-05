import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_JSON = ROOT / "docs/V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_RUNNER_CONTRACT.json"
PREFLIGHT_JSON = ROOT / "docs/V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_RUNNER_PREFLIGHT.json"
DRY_RUN_JSON = ROOT / "docs/V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_RUNNER_DRY_RUN.json"
ROLLBACK_SQL = ROOT / "sql/V3_20260612_realtime_virtual_metric_writer_runner_rollback.sql"
SOURCE_SNAPSHOT_RUN_ID = (
    "realtime_daily_snapshot_20260612_standard_outbox_until_1500__"
    "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1"
)
SOURCE_TODAY_MINUTE_RUN_ID = (
    "today_minute_bar_1m_20260612_until_1500__"
    "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1"
)
SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID = (
    "previous_day_minute_preload_20260611_for_20260612__"
    "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1"
)


class V320260612RealtimeVirtualMetricWriterRunnerContractTest(unittest.TestCase):
    def test_contract_freezes_deterministic_run_id_scope_and_rows(self) -> None:
        contract = json.loads(CONTRACT_JSON.read_text())

        self.assertEqual(contract["result"], "CONTRACT_PASS")
        self.assertEqual(contract["layer_owner"], "N3_market_data")
        self.assertEqual(
            contract["target_run_id"],
            "action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__condition_layer_20260611_source_20260611_for_20260612_v1",
        )
        self.assertEqual(contract["source_scope"]["for_trade_date"], "20260612")
        self.assertEqual(
            contract["source_scope"]["source_condition_run_id"],
            "condition_layer_20260611_source_20260611_for_20260612_v1",
        )
        self.assertEqual(contract["source_scope"]["source_snapshot_run_id"], SOURCE_SNAPSHOT_RUN_ID)
        self.assertEqual(contract["source_scope"]["source_today_minute_run_id"], SOURCE_TODAY_MINUTE_RUN_ID)
        self.assertEqual(contract["source_scope"]["source_previous_day_minute_run_id"], SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID)
        self.assertEqual(contract["expected_rows"]["total"], 100)
        self.assertEqual(contract["expected_rows"]["by_signal_type"], {"B_BUY": 76, "S_SELL": 24})
        self.assertEqual(contract["expected_downstream_dry_run"]["n4_trigger_matched"], 96)
        self.assertEqual(contract["source_scope"]["retained_1m_source_facts"]["stock_minute_bar_1m"], 705120)
        self.assertEqual(contract["source_scope"]["retained_1m_source_facts"]["index_minute_bar_1m"], 90144)
        self.assertEqual(contract["source_scope"]["retained_1m_source_facts"]["board_minute_bar_1m"], 56832)

    def test_contract_allows_only_n3_metric_write_scope(self) -> None:
        contract = json.loads(CONTRACT_JSON.read_text())

        self.assertEqual(
            contract["allowed_write_tables"],
            [
                "common_market_data_run",
                "common_market_data_quality_item",
                "stock_action_confirmation_projection_metric",
                "index_action_confirmation_projection_metric",
                "board_action_confirmation_projection_metric",
            ],
        )
        forbidden = set(contract["forbidden_write_tables"])
        self.assertIn("common_event_outbox", forbidden)
        self.assertIn("common_event_inbox", forbidden)
        self.assertIn("common_event_consumer_checkpoint", forbidden)
        self.assertIn("common_trigger_match", forbidden)
        self.assertIn("common_action_event", forbidden)
        self.assertIn("user_signal_projection", forbidden)
        self.assertTrue(contract["side_effects"]["database_written_by_this_gate"] is False)
        self.assertTrue(contract["side_effects"]["outbox_inbox_checkpoint_consumed_or_updated"] is False)
        self.assertTrue(contract["side_effects"]["n4_n5_executed"] is False)

    def test_contract_uses_lowercase_db_columns_and_preserves_display_aliases(self) -> None:
        contract = json.loads(CONTRACT_JSON.read_text())
        registry = contract["field_registry"]

        self.assertEqual(registry["db_column_canonical_form"], "postgresql_lowercase_identifiers")
        self.assertEqual(registry["display_alias_to_db_column"]["current_D_body_high"], "current_d_body_high")
        self.assertEqual(registry["display_alias_to_db_column"]["previous_Y_amount"], "previous_y_amount")
        write_columns = set(registry["writer_columns"])
        self.assertIn("current_d_body_high", write_columns)
        self.assertIn("previous_y_amount", write_columns)
        self.assertIn("trace_json", write_columns)
        self.assertNotIn("current_D_body_high", write_columns)
        self.assertNotIn("previous_Y_amount", write_columns)

    def test_contract_defines_session_context_idempotency_and_runner_status(self) -> None:
        contract = json.loads(CONTRACT_JSON.read_text())

        self.assertEqual(
            contract["session_policy"]["auction_0920_0930"],
            "mootdx_0931_label_as_auction_realtime_virtual_1m",
        )
        self.assertEqual(
            contract["session_policy"]["midday_bridge"],
            "13:00_label_equivalent_to_missing_11:30_for_13:01_previous_1m",
        )
        self.assertEqual(contract["higher_period_context_input"]["required_periods"], ["D", "W", "M", "Q", "Y"])
        self.assertEqual(contract["higher_period_context_input"]["source"], "N2_period_trigger_baseline_json_or_localized_N4_context_copy")
        self.assertEqual(contract["idempotency"]["target_run_baseline_required"], 0)
        self.assertEqual(contract["idempotency"]["duplicate_metric_grain_allowed"], 0)
        self.assertEqual(
            contract["runner_status"],
            "implemented_contract_driven_source_payload_runner_schema_ready_after_source_run_id_fk_repair",
        )
        self.assertTrue(contract["execute_ready"])
        self.assertEqual(contract["blockers"], [])
        nullable_schema = contract["source_snapshot_id_nullable_schema"]["live_schema"]
        for table_proof in nullable_schema.values():
            self.assertEqual(table_proof["source_snapshot_id_is_nullable"], "YES")
            self.assertTrue(table_proof["fk_present"])

    def test_contract_and_preflight_freeze_source_run_id_fk_lineage(self) -> None:
        contract = json.loads(CONTRACT_JSON.read_text())
        preflight = json.loads(PREFLIGHT_JSON.read_text())

        for artifact in (contract, preflight):
            policy = artifact["source_run_id_fk_lineage_policy"]
            self.assertEqual(policy["lineage_policy"], "contract_reviewed_source_run_id_fk_lineage")
            self.assertEqual(policy["source_snapshot_run_id"], SOURCE_SNAPSHOT_RUN_ID)
            self.assertEqual(policy["source_today_minute_run_id"], SOURCE_TODAY_MINUTE_RUN_ID)
            self.assertEqual(policy["source_previous_day_minute_run_id"], SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID)
            self.assertEqual(policy["writer_validation_blocker"], "source_run_id_fk_lineage_unresolved")
        materialized = preflight["source_run_id_fk_lineage_policy"]["materialized_payload_check"]
        self.assertEqual(materialized["fallback_source_run_id_prefix_rows"], 0)
        self.assertEqual(
            materialized["lineage_policy_distribution"],
            {"contract_reviewed_source_run_id_fk_lineage": 100},
        )

    def test_dry_run_and_preflight_are_side_effect_free_and_consistent(self) -> None:
        dry_run = json.loads(DRY_RUN_JSON.read_text())
        preflight = json.loads(PREFLIGHT_JSON.read_text())
        contract = json.loads(CONTRACT_JSON.read_text())

        self.assertEqual(dry_run["result"], "DRY_RUN_PASS")
        self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
        self.assertEqual(dry_run["target_run_id"], contract["target_run_id"])
        self.assertEqual(preflight["target_run_id"], contract["target_run_id"])
        self.assertEqual(dry_run["planned_rows"], contract["expected_rows"])
        self.assertEqual(preflight["baseline"]["target_metric_rows"], 0)
        self.assertEqual(preflight["P0_P1_P2"], {"P0": 0, "P1": 0, "P2": 0})
        self.assertEqual(preflight["P1_notes"], [])
        self.assertTrue(preflight["execute_ready"])
        self.assertEqual(preflight["blockers"], [])
        self.assertEqual(
            preflight["runner_status"],
            "implemented_contract_driven_source_payload_runner_schema_ready_after_source_run_id_fk_repair",
        )
        for artifact in (dry_run, preflight):
            self.assertFalse(artifact["side_effects"]["database_written"])
            self.assertFalse(artifact["side_effects"]["outbox_inbox_checkpoint_consumed_or_updated"])
            self.assertFalse(artifact["side_effects"]["n4_n5_executed"])

    def test_rollback_sql_hard_fails_and_scopes_only_target_run(self) -> None:
        rollback = ROLLBACK_SQL.read_text()
        first_raise = rollback.index("RAISE EXCEPTION")
        first_delete = rollback.index("DELETE")

        self.assertLess(first_raise, first_delete)
        self.assertIn("v3 realtime virtual metric writer rollback blocked by default", rollback)
        self.assertIn("SET LOCAL ashare_v3.rollback_target_run_id = :'target_run_id'", rollback)
        self.assertIn("projection_run_id = current_setting('ashare_v3.rollback_target_run_id')", rollback)
        self.assertIn("common_market_data_quality_item", rollback)
        self.assertIn("common_market_data_run", rollback)
        self.assertIn("common_event_outbox", rollback)
        self.assertIn("common_event_inbox", rollback)
        self.assertIn("common_event_consumer_checkpoint", rollback)
        self.assertIn("common_trigger_match", rollback)
        self.assertIn("common_action_event", rollback)
        self.assertIn("user_signal_projection", rollback)
        self.assertNotRegex(rollback.upper(), r"\b(CASCADE|TRUNCATE|DROP)\b")
        self.assertNotIn("stock_minute_bar_1m", rollback)
        self.assertNotIn("index_minute_bar_1m", rollback)
        self.assertNotIn("board_minute_bar_1m", rollback)


if __name__ == "__main__":
    unittest.main()
