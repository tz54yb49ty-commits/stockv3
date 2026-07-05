import unittest

from ashare_v3.ingestion.common import IngestionValidationError
from ashare_v3.ingestion.parquet_archive import build_parquet_archive_plan


class ParquetArchivePlanTest(unittest.TestCase):
    def test_stock_daily_archive_plan_uses_table_name_path(self) -> None:
        plan = build_parquet_archive_plan(
            dataset="stock_daily_bar_fact",
            rows=[
                {"stock_identity_key": "stock:SZ:000001", "trade_date": "20260521"},
                {"stock_identity_key": "stock:SH:600000", "trade_date": "20260521"},
            ],
            source_batch_id="stock_daily_20260521_v1",
            source_version="stock_daily_20260521_v1",
            data_root="/Volumes/MacRaid/database",
        )

        self.assertTrue(plan.passed)
        self.assertEqual(plan.row_count, 2)
        self.assertEqual(plan.partition_keys, ("trade_date",))
        self.assertEqual(len(plan.files), 1)
        self.assertEqual(
            plan.files[0].path,
            "/Volumes/MacRaid/database/data_lake/stock_daily_bar_fact/source_version=stock_daily_20260521_v1/trade_date=20260521/part-00000.parquet",
        )
        self.assertEqual(
            plan.manifest_path,
            "/Volumes/MacRaid/database/data_lake/_manifests/stock_daily_bar_fact/source_version=stock_daily_20260521_v1/stock_daily_20260521_v1.manifest.json",
        )
        self.assertFalse(plan.to_manifest_dict()["will_write_data_files"])

    def test_archive_plan_groups_multiple_partitions(self) -> None:
        plan = build_parquet_archive_plan(
            dataset="stock_daily_basic",
            rows=[
                {"stock_identity_key": "stock:SZ:000001", "trade_date": "20260520"},
                {"stock_identity_key": "stock:SZ:000001", "trade_date": "20260521"},
            ],
            source_batch_id="stock_daily_basic_202605_v1",
            source_version="stock_daily_basic_202605_v1",
        )

        self.assertEqual(len(plan.files), 2)
        self.assertEqual([file.row_count for file in plan.files], [1, 1])
        self.assertIn("trade_date=20260520", plan.files[0].path)
        self.assertIn("trade_date=20260521", plan.files[1].path)

    def test_stock_financial_archive_uses_asof_date_partition(self) -> None:
        plan = build_parquet_archive_plan(
            dataset="stock_financial_metrics_fact",
            rows=[{"stock_identity_key": "stock:SZ:000001", "asof_date": "20260521"}],
            source_batch_id="stock_financial_20260521_v1",
            source_version="stock_financial_20260521_v1",
        )

        self.assertEqual(plan.partition_keys, ("asof_date",))
        self.assertIn("asof_date=20260521", plan.files[0].path)

    def test_missing_partition_key_is_rejected_before_plan(self) -> None:
        with self.assertRaises(IngestionValidationError):
            build_parquet_archive_plan(
                dataset="board_membership_fact",
                rows=[{"board_identity_key": "board:TDX:881002"}],
                source_batch_id="board_membership_20260521_v1",
                source_version="board_membership_20260521_v1",
            )

    def test_rollback_paths_include_manifest_and_files(self) -> None:
        plan = build_parquet_archive_plan(
            dataset="index_membership_fact",
            rows=[{"index_identity_key": "index:SH:000300", "trade_date": "20260521"}],
            source_batch_id="index_membership_20260521_v1",
            source_version="index_membership_20260521_v1",
        )

        manifest = plan.to_manifest_dict()
        self.assertEqual(manifest["rollback"]["paths"], plan.rollback_paths)
        self.assertEqual(plan.rollback_paths[0], plan.manifest_path)
        self.assertEqual(plan.rollback_paths[1], plan.files[0].path)

    def test_unsupported_dataset_is_rejected(self) -> None:
        with self.assertRaises(IngestionValidationError):
            build_parquet_archive_plan(
                dataset="daily_bar_fact",
                rows=[{"trade_date": "20260521"}],
                source_batch_id="bad_20260521_v1",
                source_version="bad_20260521_v1",
            )


if __name__ == "__main__":
    unittest.main()
