import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_JSON = PROJECT_ROOT / "docs" / "N2_condition_layer_20260526_v2_execute_contract.json"
PREFLIGHT_JSON = PROJECT_ROOT / "docs" / "N2_condition_layer_20260526_v2_execute_preflight.json"
ROLLBACK_SQL = PROJECT_ROOT / "sql" / "N2_condition_layer_20260526_v2_rollback.sql"


class ConditionV2ArtifactAlignmentTest(unittest.TestCase):
    def test_contract_uses_passed_active_lineage_supersede_semantics(self) -> None:
        contract = json.loads(CONTRACT_JSON.read_text(encoding="utf-8"))

        self.assertEqual(contract["write_contract"]["common_condition_run_success_status"], "passed_active")
        self.assertEqual(contract["active_run_contract"]["active_pointer"], "common_condition_run.status = 'passed_active'")
        self.assertEqual(contract["active_run_contract"]["legacy_active_pointer_read_compat"], "common_condition_run.status = 'passed'")
        self.assertEqual(contract["active_run_contract"]["active_run_policy"], "lineage_supersede_only")
        self.assertTrue(contract["active_run_contract"]["mark_previous_run_superseded_after_postcheck"])
        self.assertFalse(contract["active_run_contract"]["delete_previous_rows"])
        self.assertFalse(contract["active_run_contract"]["update_previous_rows"])
        self.assertFalse(contract["active_run_contract"]["n3_lineage_auto_switch"])
        self.assertIn("passed_active", contract["active_run_contract"]["switch_after_postcheck_sql_templates"][1])
        self.assertIn("--overwrite", contract["execute_command"]["command"])

    def test_preflight_records_schema_ready_and_passed_active_supported(self) -> None:
        preflight = json.loads(PREFLIGHT_JSON.read_text(encoding="utf-8"))

        self.assertTrue(preflight["schema_status"]["schema_ready"])
        self.assertTrue(preflight["schema_status"]["passed_active_status_supported"])
        self.assertTrue(preflight["execute_allowed"])
        self.assertEqual(preflight["blocked_reasons"], [])
        self.assertEqual(preflight["active_run_status"]["canonical_active_run_count"], 0)
        self.assertEqual(preflight["active_run_status"]["legacy_active_run_count"], 1)
        self.assertEqual(preflight["run_id_status"]["total_existing_rows"], 0)
        self.assertTrue(preflight["run_id_status"]["run_id_available"])

    def test_rollback_deletes_only_v2_and_restores_v1_passed_active_with_guards(self) -> None:
        sql = ROLLBACK_SQL.read_text(encoding="utf-8")

        self.assertIn("condition_layer_20260526_source_20260526_v2", sql)
        self.assertIn("condition_layer_20260526_source_20260526_v1", sql)
        self.assertIn("common_event_outbox", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)
        self.assertIn("RAISE EXCEPTION", sql)
        self.assertIn("UPDATE common_condition_run", sql)
        self.assertIn("status = 'passed_active'", sql)
        self.assertNotIn("DELETE FROM common_condition_run WHERE run_id = :'previous_active_run_id'", sql)
        self.assertNotIn("DELETE FROM stock_condition_basis WHERE run_id = :'previous_active_run_id'", sql)


if __name__ == "__main__":
    unittest.main()
