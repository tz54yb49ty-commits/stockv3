import unittest

from ashare_v3.ingestion.real_execution_application import (
    ARCHIVE_DATASET_COUNT,
    CORE_TARGET_TABLE_COUNT,
    REQUIRED_APPLICATION_STAGES,
    REQUIRED_OPERATOR_APPROVALS,
    build_real_execution_application_package,
)


class RealExecutionApplicationPackageTest(unittest.TestCase):
    def test_application_package_passes_but_is_not_executable(self) -> None:
        package = build_real_execution_application_package()

        self.assertTrue(package.passed)
        self.assertFalse(package.ready_to_execute)
        self.assertTrue(package.readiness_passed)
        self.assertFalse(package.readiness_ready_to_execute)
        self.assertIn("pending_user_confirmation", package.execution_blockers)
        self.assertIn("real_execution_config_disabled", package.execution_blockers)
        self.assertFalse(package.will_authorize_real_execution)

    def test_application_package_has_two_stage_requests(self) -> None:
        package = build_real_execution_application_package()
        stages = {stage.stage_id: stage for stage in package.stages}

        self.assertEqual(set(stages), set(REQUIRED_APPLICATION_STAGES))
        self.assertEqual(stages["initial_backfill"].batch_count, 211)
        self.assertEqual(stages["daily_incremental"].batch_count, 11)
        for stage in stages.values():
            self.assertEqual(stage.target_table_count, CORE_TARGET_TABLE_COUNT)
            self.assertEqual(stage.source_request_count, CORE_TARGET_TABLE_COUNT)
            self.assertEqual(stage.archive_request_count, ARCHIVE_DATASET_COUNT)
            self.assertEqual(stage.rollback_request_count, CORE_TARGET_TABLE_COUNT)
            self.assertEqual(stage.approval_status, "pending_user_confirmation")

    def test_application_sources_list_network_and_tdx_permissions(self) -> None:
        package = build_real_execution_application_package()

        for stage in package.stages:
            network_sources = [request for request in stage.source_requests if request.requires_network]
            tdx_sources = [request for request in stage.source_requests if request.requires_tdx_file_read]
            self.assertEqual(len(network_sources), 8, stage.stage_id)
            self.assertEqual(len(tdx_sources), 3, stage.stage_id)
            self.assertIn("stock_daily_basic", {request.task_id for request in network_sources})
            self.assertIn("board_identity", {request.task_id for request in tdx_sources})
            self.assertIn("index_membership", {request.task_id for request in tdx_sources})
            self.assertTrue(all(request.approval_status == "pending_user_confirmation" for request in stage.source_requests))

    def test_application_archive_requests_cover_data_lake_and_versions(self) -> None:
        package = build_real_execution_application_package()
        stages = {stage.stage_id: stage for stage in package.stages}

        for stage in stages.values():
            datasets = {request.dataset: request for request in stage.archive_requests}
            self.assertEqual(len(datasets), 7)
            self.assertIn("stock_daily_bar_fact", datasets)
            self.assertIn("stock_daily_basic", datasets)
            self.assertTrue(datasets["stock_daily_bar_fact"].dataset_root.startswith("/Volumes/MacRaid/database/data_lake/"))
            self.assertTrue(datasets["stock_daily_bar_fact"].manifest_root.startswith("/Volumes/MacRaid/database/data_lake/_manifests/"))
            self.assertTrue(datasets["stock_daily_bar_fact"].rollback_paths)
            self.assertTrue(datasets["stock_daily_bar_fact"].source_versions)
        self.assertEqual(stages["daily_incremental"].archive_requests[0].approval_status, "pending_user_confirmation")

    def test_application_operator_approvals_are_all_pending(self) -> None:
        package = build_real_execution_application_package()

        self.assertEqual({item.item_id for item in package.operator_approval_items}, set(REQUIRED_OPERATOR_APPROVALS))
        self.assertEqual(len(package.pending_approval_item_ids), len(REQUIRED_OPERATOR_APPROVALS))
        self.assertTrue(all(item.status == "pending_user_confirmation" for item in package.operator_approval_items))
        self.assertEqual(package.required_env_vars, ("TUSHARE_TOKEN", "ASHARE_V3_POSTGRES_DSN"))
        self.assertEqual(package.data_root, "/Volumes/MacRaid/database")
        self.assertEqual(package.tdx_root, "/Volumes/MacRaid/tdxdata/tdx")

    def test_application_quality_gates_cover_boundary(self) -> None:
        package = build_real_execution_application_package()
        gate_names = {gate.gate_name for gate in package.quality_gates}

        self.assertIn("application_readiness_summary_passed", gate_names)
        self.assertIn("application_stages_present", gate_names)
        self.assertIn("application_stage_counts_match", gate_names)
        self.assertIn("application_physical_tables_split", gate_names)
        self.assertIn("application_archive_and_rollback_coverage", gate_names)
        self.assertIn("application_operator_approvals_pending", gate_names)
        self.assertIn("application_no_real_authorization", gate_names)
        self.assertIn("application_no_side_effects", gate_names)
        self.assertTrue(all(gate.passed for gate in package.quality_gates))

    def test_application_has_no_side_effects(self) -> None:
        package = build_real_execution_application_package()
        payload = package.to_dict()

        self.assertFalse(package.will_call_external_sources)
        self.assertFalse(package.will_read_tdx_files)
        self.assertFalse(package.will_connect_database)
        self.assertFalse(package.will_execute_sql)
        self.assertFalse(package.will_create_directories)
        self.assertFalse(package.will_write_data_files)
        self.assertFalse(package.will_authorize_real_execution)
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


if __name__ == "__main__":
    unittest.main()
