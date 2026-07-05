import unittest

from ashare_v3.ingestion.environment_probe_plan import (
    REQUIRED_PROBE_CATEGORIES,
    REQUIRED_PROBE_ITEM_IDS,
    build_environment_probe_plan_report,
)


class EnvironmentProbePlanTest(unittest.TestCase):
    def test_probe_plan_passes_but_is_not_ready_to_probe(self) -> None:
        report = build_environment_probe_plan_report()

        self.assertTrue(report.passed)
        self.assertFalse(report.ready_to_probe)
        self.assertTrue(report.application_passed)
        self.assertFalse(report.application_ready_to_execute)
        self.assertIn("pending_user_confirmation", report.execution_blockers)
        self.assertIn("real_execution_config_disabled", report.execution_blockers)
        self.assertEqual(len(report.pending_probe_item_ids), len(REQUIRED_PROBE_ITEM_IDS))

    def test_probe_items_and_categories_are_complete(self) -> None:
        report = build_environment_probe_plan_report()

        self.assertEqual(set(report.probe_item_ids), set(REQUIRED_PROBE_ITEM_IDS))
        self.assertEqual({item.category for item in report.probe_items}, set(REQUIRED_PROBE_CATEGORIES))
        self.assertTrue(all(item.approval_status == "pending_user_confirmation" for item in report.probe_items))
        self.assertTrue(all(item.actual_status == "not_checked" for item in report.probe_items))
        self.assertTrue(all(item.will_run is False for item in report.probe_items))

    def test_security_and_database_probe_targets_are_names_only(self) -> None:
        report = build_environment_probe_plan_report()
        items = {item.item_id: item for item in report.probe_items}

        self.assertEqual(report.required_env_vars, ("TUSHARE_TOKEN", "ASHARE_V3_POSTGRES_DSN"))
        self.assertEqual(items["security.env_tushare_token_present"].target, "TUSHARE_TOKEN")
        self.assertEqual(items["security.env_postgres_dsn_present"].target, "ASHARE_V3_POSTGRES_DSN")
        self.assertEqual(items["database.postgresql_connectivity"].target, "ASHARE_V3_POSTGRES_DSN")
        self.assertFalse(items["database.postgresql_connectivity"].evidence["writes_allowed"])

    def test_archive_and_tdx_probe_paths_are_planned_without_access(self) -> None:
        report = build_environment_probe_plan_report()
        items = {item.item_id: item for item in report.probe_items}

        self.assertEqual(report.data_root, "/Volumes/MacRaid/database")
        self.assertEqual(report.tdx_root, "/Volumes/MacRaid/tdxdata/tdx")
        self.assertEqual(items["archive.data_root_present"].target, "/Volumes/MacRaid/database")
        self.assertEqual(items["archive.manifest_root_writable"].target, "/Volumes/MacRaid/database/data_lake/_manifests")
        tdx_required_files = items["tdx.board_txt_files_readable"].evidence["required_files"]
        self.assertIn("/Volumes/MacRaid/tdxdata/tdx/指数板块.txt", tdx_required_files)
        self.assertEqual(items["tdx.board_txt_files_readable"].evidence["encoding"], "GBK")

    def test_source_and_runtime_probe_targets_are_planned(self) -> None:
        report = build_environment_probe_plan_report()
        items = {item.item_id: item for item in report.probe_items}

        self.assertEqual(items["source.tushare_reachable"].target, "tushare")
        self.assertEqual(items["source.mootdx_reachable"].target, "mootdx")
        self.assertIn("TUSHARE_TOKEN", items["source.tushare_reachable"].evidence["env_var"])
        self.assertEqual(
            items["runtime.python_dependencies_available"].evidence["packages"],
            ["pandas", "pyarrow", "psycopg", "tushare", "mootdx"],
        )

    def test_probe_quality_gates_cover_no_execution_boundary(self) -> None:
        report = build_environment_probe_plan_report()
        gate_names = {gate.gate_name for gate in report.quality_gates}

        self.assertIn("environment_probe_application_package_passed", gate_names)
        self.assertIn("environment_probe_items_present", gate_names)
        self.assertIn("environment_probe_categories_present", gate_names)
        self.assertIn("environment_probe_required_targets_planned", gate_names)
        self.assertIn("environment_probe_not_executed", gate_names)
        self.assertIn("environment_probe_approvals_pending", gate_names)
        self.assertIn("environment_probe_no_real_authorization", gate_names)
        self.assertIn("environment_probe_no_side_effects", gate_names)
        self.assertTrue(all(gate.passed for gate in report.quality_gates))

    def test_probe_plan_has_no_side_effects(self) -> None:
        report = build_environment_probe_plan_report()
        payload = report.to_dict()

        self.assertFalse(report.will_read_environment)
        self.assertFalse(report.will_check_filesystem)
        self.assertFalse(report.will_call_external_sources)
        self.assertFalse(report.will_read_tdx_files)
        self.assertFalse(report.will_connect_database)
        self.assertFalse(report.will_execute_sql)
        self.assertFalse(report.will_create_directories)
        self.assertFalse(report.will_write_data_files)
        self.assertFalse(report.will_start_worker)
        self.assertFalse(report.will_authorize_real_execution)
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
