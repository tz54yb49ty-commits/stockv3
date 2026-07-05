import unittest

from ashare_v3.ingestion.execution_preflight import build_execution_preflight_checklist
from ashare_v3.ingestion.ingestion_dry_run_control import build_ingestion_dry_run_control_report


class ExecutionPreflightChecklistTest(unittest.TestCase):
    def test_preflight_checklist_builds_but_is_not_ready_by_default(self) -> None:
        checklist = build_default_preflight()

        self.assertTrue(checklist.passed)
        self.assertFalse(checklist.ready_to_execute)
        self.assertEqual(len(checklist.confirmation_items), 13)
        self.assertEqual(len(checklist.pending_item_ids), 13)

    def test_preflight_categories_cover_real_execution_risks(self) -> None:
        checklist = build_default_preflight()

        self.assertEqual(
            checklist.category_counts,
            {
                "scope": 1,
                "stage": 1,
                "secret": 2,
                "source": 3,
                "database": 1,
                "archive": 1,
                "quality_gate": 1,
                "rollback": 1,
                "safety": 2,
            },
        )

    def test_preflight_items_cover_paths_env_and_permissions(self) -> None:
        checklist = build_default_preflight()
        items = {item.item_id: item for item in checklist.confirmation_items}

        self.assertEqual(items["secret.tushare_token_env"].evidence["env_var"], "TUSHARE_TOKEN")
        self.assertEqual(items["secret.postgres_dsn_env"].evidence["env_var"], "ASHARE_V3_POSTGRES_DSN")
        self.assertEqual(items["source.tdx_local_txt_read"].evidence["tdx_root"], "/Volumes/MacRaid/tdxdata/tdx")
        self.assertEqual(items["archive.data_root_write"].evidence["data_root"], "/Volumes/MacRaid/database")
        self.assertTrue(items["source.tushare_network"].evidence["requires_network"])

    def test_preflight_items_cover_database_quality_rollback_and_safety(self) -> None:
        checklist = build_default_preflight()
        item_ids = {item.item_id for item in checklist.confirmation_items}

        self.assertIn("database.postgresql_schema_and_write", item_ids)
        self.assertIn("quality_gate.activation_blocking", item_ids)
        self.assertIn("rollback.source_batch_restore", item_ids)
        self.assertIn("safety.old_system_boundary", item_ids)
        self.assertIn("safety.no_worker_or_service_start", item_ids)

    def test_preflight_can_model_user_confirmations_without_side_effects(self) -> None:
        control_report = build_ingestion_dry_run_control_report()
        all_item_ids = [item.item_id for item in build_execution_preflight_checklist(control_report).confirmation_items]
        checklist = build_execution_preflight_checklist(control_report, confirmed_item_ids=all_item_ids)

        self.assertTrue(checklist.passed)
        self.assertTrue(checklist.ready_to_execute)
        self.assertEqual(checklist.pending_item_ids, ())
        self.assertFalse(checklist.will_call_external_sources)
        self.assertFalse(checklist.will_read_tdx_files)
        self.assertFalse(checklist.will_connect_database)
        self.assertFalse(checklist.will_execute_sql)
        self.assertFalse(checklist.will_write_data_files)

    def test_preflight_quality_gates_cover_required_topics(self) -> None:
        checklist = build_default_preflight()
        gate_names = {gate.gate_name for gate in checklist.quality_gates}

        self.assertIn("preflight_control_report_passed", gate_names)
        self.assertIn("preflight_items_present", gate_names)
        self.assertIn("preflight_required_categories_present", gate_names)
        self.assertIn("preflight_confirmation_state_explicit", gate_names)
        self.assertIn("preflight_no_side_effects", gate_names)
        self.assertTrue(all(gate.passed for gate in checklist.quality_gates))


def build_default_preflight():
    return build_execution_preflight_checklist(build_ingestion_dry_run_control_report())


if __name__ == "__main__":
    unittest.main()
