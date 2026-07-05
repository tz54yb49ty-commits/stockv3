import unittest

from ashare_v3.ingestion.real_execution_config import EXPECTED_CONFIRMATION_ITEMS
from ashare_v3.ingestion.real_execution_readiness import (
    REQUIRED_READINESS_COMPONENTS,
    build_real_execution_readiness_report,
)


class RealExecutionReadinessTest(unittest.TestCase):
    def test_readiness_summary_passes_but_does_not_authorize_execution(self) -> None:
        report = build_real_execution_readiness_report()

        self.assertTrue(report.passed)
        self.assertFalse(report.ready_to_execute)
        self.assertIn("pending_user_confirmation", report.execution_blockers)
        self.assertIn("real_execution_config_disabled", report.execution_blockers)
        self.assertFalse(report.will_authorize_real_execution)

    def test_readiness_components_are_complete(self) -> None:
        report = build_real_execution_readiness_report()
        components = {status.component_id: status for status in report.component_statuses}

        self.assertEqual(set(components), set(REQUIRED_READINESS_COMPONENTS))
        self.assertTrue(all(status.passed for status in components.values()))
        self.assertEqual(components["dry_run_control"].summary["initial_batch_count"], 211)
        self.assertEqual(components["dry_run_control"].summary["daily_task_count"], 11)
        self.assertEqual(components["schema_readiness"].summary["table_count"], 14)
        self.assertEqual(components["parquet_readiness"].summary["dataset_count"], 7)

    def test_preflight_and_config_state_are_explicit(self) -> None:
        report = build_real_execution_readiness_report()
        components = {status.component_id: status for status in report.component_statuses}

        self.assertFalse(components["execution_preflight"].ready_to_execute)
        self.assertEqual(components["execution_preflight"].summary["pending_item_count"], 13)
        self.assertFalse(components["real_execution_config"].ready_to_execute)
        self.assertEqual(components["real_execution_config"].summary["mode"], "preflight_only")
        self.assertEqual(components["real_execution_config"].summary["approved_stage"], "none")
        self.assertEqual(components["real_execution_config"].summary["enabled_permission_count"], 0)

    def test_all_preflight_confirmed_still_requires_real_config_authorization(self) -> None:
        report = build_real_execution_readiness_report(confirmed_item_ids=EXPECTED_CONFIRMATION_ITEMS)

        self.assertTrue(report.passed)
        self.assertFalse(report.ready_to_execute)
        self.assertEqual(report.pending_preflight_item_ids, ())
        self.assertEqual(report.execution_blockers, ("real_execution_config_disabled",))

    def test_readiness_has_no_side_effects(self) -> None:
        report = build_real_execution_readiness_report()
        payload = report.to_dict()

        self.assertFalse(report.will_call_external_sources)
        self.assertFalse(report.will_read_tdx_files)
        self.assertFalse(report.will_connect_database)
        self.assertFalse(report.will_execute_sql)
        self.assertFalse(report.will_create_directories)
        self.assertFalse(report.will_write_data_files)
        self.assertFalse(report.will_authorize_real_execution)
        self.assertEqual(
            payload["side_effects"],
            {
                "will_call_external_sources": False,
                "will_read_tdx_files": False,
                "will_connect_database": False,
                "will_execute_sql": False,
                "will_create_directories": False,
                "will_write_data_files": False,
                "will_authorize_real_execution": False,
            },
        )

    def test_quality_gates_cover_static_readiness_and_authorization_boundary(self) -> None:
        report = build_real_execution_readiness_report()
        gate_names = {gate.gate_name for gate in report.quality_gates}

        self.assertIn("readiness_components_present", gate_names)
        self.assertIn("readiness_components_passed", gate_names)
        self.assertIn("readiness_preflight_state_explicit", gate_names)
        self.assertIn("readiness_real_config_template_safe", gate_names)
        self.assertIn("readiness_real_execution_not_authorized", gate_names)
        self.assertIn("readiness_no_side_effects", gate_names)
        self.assertTrue(all(gate.passed for gate in report.quality_gates))


if __name__ == "__main__":
    unittest.main()
