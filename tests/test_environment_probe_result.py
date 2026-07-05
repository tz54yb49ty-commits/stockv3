import unittest

from ashare_v3.ingestion.environment_probe_plan import REQUIRED_PROBE_ITEM_IDS
from ashare_v3.ingestion.environment_probe_result import (
    DEFAULT_SKIPPED_ERROR_SUMMARY,
    RESULT_STATUS_VALUES,
    build_environment_probe_result_template,
)


class EnvironmentProbeResultTemplateTest(unittest.TestCase):
    def test_result_template_passes_but_is_not_ready_for_execution_review(self) -> None:
        template = build_environment_probe_result_template()

        self.assertTrue(template.passed)
        self.assertFalse(template.ready_for_execution_review)
        self.assertTrue(template.probe_plan_passed)
        self.assertFalse(template.probe_plan_ready_to_probe)
        self.assertIn("pending_user_confirmation", template.execution_blockers)
        self.assertIn("real_execution_config_disabled", template.execution_blockers)
        self.assertFalse(template.will_authorize_real_execution)

    def test_result_records_cover_all_probe_items(self) -> None:
        template = build_environment_probe_result_template()

        self.assertEqual(set(template.result_item_ids), set(REQUIRED_PROBE_ITEM_IDS))
        self.assertEqual(len(template.result_records), 14)
        self.assertEqual(template.result_status_counts, {"skipped": 14})
        self.assertEqual(set(template.blocking_result_item_ids), set(REQUIRED_PROBE_ITEM_IDS))

    def test_result_status_schema_is_explicit(self) -> None:
        template = build_environment_probe_result_template()
        payload = template.to_dict()

        self.assertEqual(payload["result_status_values"], list(RESULT_STATUS_VALUES))
        self.assertEqual(tuple(payload["result_status_values"]), ("passed", "failed", "skipped"))
        self.assertTrue(all(record.result_status == "skipped" for record in template.result_records))
        self.assertTrue(all(record.probe_executed is False for record in template.result_records))
        self.assertTrue(all(record.error_summary == DEFAULT_SKIPPED_ERROR_SUMMARY for record in template.result_records))

    def test_result_records_include_severity_and_blocking_fields(self) -> None:
        template = build_environment_probe_result_template()
        records = {record.item_id: record for record in template.result_records}

        self.assertEqual(records["security.env_tushare_token_present"].severity, "P0")
        self.assertEqual(records["database.postgresql_connectivity"].severity, "P0")
        self.assertEqual(records["archive.data_root_writable"].severity, "P0")
        self.assertEqual(records["runtime.python_dependencies_available"].severity, "P1")
        self.assertTrue(all(record.blocking for record in template.result_records))

    def test_result_template_keeps_paths_and_env_names_from_probe_plan(self) -> None:
        template = build_environment_probe_result_template()

        self.assertEqual(template.data_root, "/Volumes/MacRaid/database")
        self.assertEqual(template.tdx_root, "/Volumes/MacRaid/tdxdata/tdx")
        self.assertEqual(template.required_env_vars, ("TUSHARE_TOKEN", "ASHARE_V3_POSTGRES_DSN"))

    def test_result_quality_gates_cover_template_boundary(self) -> None:
        template = build_environment_probe_result_template()
        gate_names = {gate.gate_name for gate in template.quality_gates}

        self.assertIn("probe_result_plan_passed_but_not_ready", gate_names)
        self.assertIn("probe_result_records_cover_plan_items", gate_names)
        self.assertIn("probe_result_status_domain_valid", gate_names)
        self.assertIn("probe_result_template_all_skipped", gate_names)
        self.assertIn("probe_result_blockers_explicit", gate_names)
        self.assertIn("probe_result_error_summary_present", gate_names)
        self.assertIn("probe_result_no_real_authorization", gate_names)
        self.assertIn("probe_result_no_side_effects", gate_names)
        self.assertTrue(all(gate.passed for gate in template.quality_gates))

    def test_result_template_has_no_side_effects(self) -> None:
        template = build_environment_probe_result_template()
        payload = template.to_dict()

        self.assertFalse(template.will_read_environment)
        self.assertFalse(template.will_check_filesystem)
        self.assertFalse(template.will_call_external_sources)
        self.assertFalse(template.will_read_tdx_files)
        self.assertFalse(template.will_connect_database)
        self.assertFalse(template.will_execute_sql)
        self.assertFalse(template.will_create_directories)
        self.assertFalse(template.will_write_data_files)
        self.assertFalse(template.will_start_worker)
        self.assertFalse(template.will_authorize_real_execution)
        self.assertEqual(
            payload["side_effects"],
            {
                "will_read_environment": False,
                "will_check_filesystem": False,
                "will_call_external_sources": False,
                "will_read_tdx_files": False,
                "will_connect_database": False,
                "will_execute_sql": False,
                "will_create_directories": False,
                "will_write_data_files": False,
                "will_start_worker": False,
                "will_authorize_real_execution": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
