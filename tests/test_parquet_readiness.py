import unittest

from ashare_v3.ingestion.parquet_archive import DATASET_PARTITION_KEYS
from ashare_v3.ingestion.parquet_readiness import (
    EXPECTED_ARCHIVE_DATASET_COUNT,
    build_parquet_readiness_report,
)


class ParquetReadinessTest(unittest.TestCase):
    def test_parquet_readiness_passes_for_default_data_root(self) -> None:
        report = build_parquet_readiness_report()

        self.assertTrue(report.passed)
        self.assertEqual(report.data_root, "/Volumes/MacRaid/database")
        self.assertEqual(report.data_lake_dir, "data_lake")
        self.assertEqual(report.dataset_count, EXPECTED_ARCHIVE_DATASET_COUNT)
        self.assertEqual({summary.dataset for summary in report.dataset_summaries}, set(DATASET_PARTITION_KEYS))

    def test_partition_keys_match_archive_plan(self) -> None:
        report = build_parquet_readiness_report()
        summaries = {summary.dataset: summary for summary in report.dataset_summaries}

        self.assertEqual(summaries["stock_financial_metrics_fact"].partition_keys, ("asof_date",))
        for dataset, summary in summaries.items():
            if dataset != "stock_financial_metrics_fact":
                self.assertEqual(summary.partition_keys, ("trade_date",), dataset)

    def test_sample_paths_are_under_expected_data_lake(self) -> None:
        report = build_parquet_readiness_report()

        for summary in report.dataset_summaries:
            self.assertTrue(
                summary.sample_parquet_path.startswith(f"/Volumes/MacRaid/database/data_lake/{summary.dataset}/"),
                summary.sample_parquet_path,
            )
            self.assertIn(f"source_version={summary.sample_source_version}", summary.sample_parquet_path)
            self.assertTrue(summary.sample_parquet_path.endswith("/part-00000.parquet"))
            self.assertTrue(
                summary.sample_manifest_path.startswith(
                    f"/Volumes/MacRaid/database/data_lake/_manifests/{summary.dataset}/"
                ),
                summary.sample_manifest_path,
            )
            self.assertTrue(summary.sample_manifest_path.endswith(f"/{summary.sample_source_batch_id}.manifest.json"))

    def test_rollback_paths_include_manifest_and_parquet_sample(self) -> None:
        report = build_parquet_readiness_report()

        for summary in report.dataset_summaries:
            self.assertEqual(summary.sample_rollback_paths[0], summary.sample_manifest_path)
            self.assertEqual(summary.sample_rollback_paths[1], summary.sample_parquet_path)

    def test_readiness_report_has_no_side_effects(self) -> None:
        report = build_parquet_readiness_report()
        payload = report.to_dict()

        self.assertFalse(report.will_create_directories)
        self.assertFalse(report.will_write_data_files)
        self.assertFalse(report.will_connect_database)
        self.assertFalse(report.will_execute_sql)
        self.assertFalse(report.will_call_external_sources)
        self.assertFalse(report.will_read_tdx_files)
        self.assertEqual(
            payload["side_effects"],
            {
                "will_create_directories": False,
                "will_write_data_files": False,
                "will_connect_database": False,
                "will_execute_sql": False,
                "will_call_external_sources": False,
                "will_read_tdx_files": False,
            },
        )

    def test_non_default_data_root_fails_expected_root_gate(self) -> None:
        report = build_parquet_readiness_report(data_root="/tmp/ashare_v3_database")
        failed_gate_names = {gate.gate_name for gate in report.quality_gates if not gate.passed}

        self.assertFalse(report.passed)
        self.assertIn("parquet_data_root_expected", failed_gate_names)


if __name__ == "__main__":
    unittest.main()
