import unittest

from ashare_v3.ingestion.batch_orchestration import CORE_DAILY_TASK_SPECS, build_daily_ingestion_orchestration_plan
from ashare_v3.ingestion.common import IngestionValidationError
from ashare_v3.ingestion.parquet_archive import DATASET_PARTITION_KEYS


class BatchOrchestrationPlanTest(unittest.TestCase):
    def test_daily_plan_covers_core_tables_in_order(self) -> None:
        plan = build_daily_ingestion_orchestration_plan(trade_date="20260521")

        self.assertTrue(plan.passed)
        self.assertEqual(len(plan.tasks), 11)
        self.assertEqual(
            [task.spec.table_name for task in plan.tasks],
            [spec.table_name for spec in CORE_DAILY_TASK_SPECS],
        )
        self.assertNotIn("daily_bar_fact", [task.spec.table_name for task in plan.tasks])

    def test_daily_plan_has_no_side_effects(self) -> None:
        plan = build_daily_ingestion_orchestration_plan(trade_date="20260521")

        self.assertFalse(plan.will_call_external_sources)
        self.assertFalse(plan.will_read_tdx_files)
        self.assertFalse(plan.will_connect_database)
        self.assertFalse(plan.will_execute_sql)
        self.assertFalse(plan.will_write_data_files)
        for task in plan.tasks:
            self.assertFalse(task.will_call_external_source)
            self.assertFalse(task.will_read_tdx_files)
            self.assertFalse(task.will_connect_database)
            self.assertFalse(task.will_execute_sql)
            self.assertFalse(task.will_write_data_files)
            self.assertFalse(task.target_write_plan.will_execute_sql)
            self.assertFalse(task.active_source_version_plan.will_execute_sql)

    def test_each_task_has_batch_version_and_rollback_plan(self) -> None:
        plan = build_daily_ingestion_orchestration_plan(trade_date="20260521", version="v2")

        batch_ids = [task.batch_spec.batch_id for task in plan.tasks]
        self.assertEqual(len(batch_ids), len(set(batch_ids)))
        for task in plan.tasks:
            self.assertTrue(task.batch_spec.batch_id.endswith("_20260521_v2"))
            self.assertEqual(task.batch_spec.source_version, task.batch_spec.batch_id)
            self.assertTrue(task.active_source_version_plan.activation_allowed)
            self.assertIn("DELETE FROM", task.target_write_plan.rollback_sql_template)
            self.assertTrue(task.quality_gate_write_plan.passed)

    def test_archive_plan_only_for_archive_datasets(self) -> None:
        plan = build_daily_ingestion_orchestration_plan(trade_date="20260521")

        for task in plan.tasks:
            if task.spec.table_name in DATASET_PARTITION_KEYS:
                self.assertIsNotNone(task.archive_plan)
                assert task.archive_plan is not None
                self.assertFalse(task.archive_plan.will_write_data_files)
                self.assertIn("/Volumes/MacRaid/database/data_lake/", task.archive_plan.manifest_path)
            else:
                self.assertIsNone(task.archive_plan)

    def test_dependencies_precede_dependent_tasks(self) -> None:
        plan = build_daily_ingestion_orchestration_plan(trade_date="20260521")
        positions = {task.spec.task_id: index for index, task in enumerate(plan.tasks)}

        for task in plan.tasks:
            for dependency in task.spec.dependencies:
                self.assertLess(positions[dependency], positions[task.spec.task_id])

    def test_invalid_trade_date_is_rejected(self) -> None:
        with self.assertRaises(IngestionValidationError):
            build_daily_ingestion_orchestration_plan(trade_date="2026-05-21")

    def test_invalid_version_is_rejected(self) -> None:
        with self.assertRaises(IngestionValidationError):
            build_daily_ingestion_orchestration_plan(trade_date="20260521", version="version1")


if __name__ == "__main__":
    unittest.main()
