import unittest

from ashare_v3.ingestion.ingestion_dry_run_control import build_ingestion_dry_run_control_report


class IngestionDryRunControlReportTest(unittest.TestCase):
    def test_control_report_passes_for_example_configs(self) -> None:
        report = build_ingestion_dry_run_control_report()

        self.assertTrue(report.passed)
        self.assertEqual(report.initial_backfill.batch_count, 211)
        self.assertEqual(report.daily_incremental.task_count, 11)
        self.assertEqual(report.initial_backfill.table_count, 11)
        self.assertEqual(report.daily_incremental.table_count, 11)
        self.assertEqual(report.initial_backfill.acceptance_item_count, 17)
        self.assertEqual(report.daily_incremental.acceptance_item_count, 17)

    def test_control_report_keeps_expected_domain_counts(self) -> None:
        report = build_ingestion_dry_run_control_report()

        self.assertEqual(report.initial_backfill.domain_counts, {"common": 1, "stock": 124, "index": 43, "board": 43})
        self.assertEqual(report.daily_incremental.domain_counts, {"common": 1, "stock": 4, "index": 3, "board": 3})

    def test_control_report_requires_daily_after_backfill(self) -> None:
        report = build_ingestion_dry_run_control_report()
        gates = {gate.gate_name: gate for gate in report.quality_gates}

        self.assertEqual(report.initial_backfill.end_date, "20260521")
        self.assertEqual(report.daily_incremental.trade_date, "20260522")
        self.assertTrue(gates["control_daily_after_backfill"].passed)

    def test_control_report_covers_archive_and_rollback_counts(self) -> None:
        report = build_ingestion_dry_run_control_report()

        self.assertEqual(report.initial_backfill.archive_dataset_count, 7)
        self.assertEqual(report.daily_incremental.archive_dataset_count, 7)
        self.assertEqual(report.initial_backfill.rollback_group_count, 11)
        self.assertEqual(report.daily_incremental.rollback_group_count, 11)

    def test_control_quality_gates_cover_required_topics(self) -> None:
        report = build_ingestion_dry_run_control_report()
        gate_names = {gate.gate_name for gate in report.quality_gates}

        self.assertIn("control_initial_backfill_passed", gate_names)
        self.assertIn("control_daily_incremental_passed", gate_names)
        self.assertIn("control_daily_after_backfill", gate_names)
        self.assertIn("control_source_trace_coverage", gate_names)
        self.assertIn("control_physical_tables_split", gate_names)
        self.assertIn("control_acceptance_categories_present", gate_names)
        self.assertIn("control_no_side_effects", gate_names)
        self.assertTrue(all(gate.passed for gate in report.quality_gates))

    def test_control_report_has_no_side_effects(self) -> None:
        report = build_ingestion_dry_run_control_report()

        self.assertFalse(report.will_call_external_sources)
        self.assertFalse(report.will_read_tdx_files)
        self.assertFalse(report.will_connect_database)
        self.assertFalse(report.will_execute_sql)
        self.assertFalse(report.will_write_data_files)


if __name__ == "__main__":
    unittest.main()
