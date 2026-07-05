import unittest

from ashare_v3.ingestion.backfill_plan import (
    DEFAULT_BACKFILL_END_DATE,
    DEFAULT_BACKFILL_START_DATE,
    MONTHLY_TASK_SPECS,
    SNAPSHOT_TASK_SPECS,
    build_initial_backfill_plan,
    clipped_month_range,
    month_periods_between,
)
from ashare_v3.ingestion.common import IngestionValidationError


class InitialBackfillPlanTest(unittest.TestCase):
    def test_default_backfill_plan_matches_documented_range_and_count(self) -> None:
        plan = build_initial_backfill_plan()

        self.assertTrue(plan.passed)
        self.assertEqual(plan.start_date, DEFAULT_BACKFILL_START_DATE)
        self.assertEqual(plan.end_date, DEFAULT_BACKFILL_END_DATE)
        self.assertEqual(plan.snapshot_date, DEFAULT_BACKFILL_END_DATE)
        self.assertEqual(len(plan.monthly_periods), 41)
        self.assertEqual(plan.batch_count, 1 + len(SNAPSHOT_TASK_SPECS) + 41 * len(MONTHLY_TASK_SPECS))
        self.assertEqual(plan.batch_count, 211)

    def test_expected_first_batches_are_range_then_snapshots(self) -> None:
        plan = build_initial_backfill_plan()

        first_batch_ids = [batch.source_batch_id for batch in plan.batches[:6]]
        self.assertEqual(
            first_batch_ids,
            [
                "trade_calendar_20230101_20260521_v1",
                "stock_identity_20260521_v1",
                "index_identity_20260521_v1",
                "board_identity_20260521_v1",
                "index_membership_20260521_v1",
                "board_membership_20260521_v1",
            ],
        )

    def test_monthly_fact_batches_use_monthly_batch_and_aggregate_source_version(self) -> None:
        plan = build_initial_backfill_plan()
        stock_daily_batches = [batch for batch in plan.batches if batch.spec.data_type == "stock_daily"]

        self.assertEqual(stock_daily_batches[0].source_batch_id, "stock_daily_202301_v1")
        self.assertEqual(stock_daily_batches[-1].source_batch_id, "stock_daily_202605_v1")
        self.assertEqual(stock_daily_batches[0].source_version, "stock_daily_20230101_20260521_v1")
        self.assertTrue(all(batch.source_version == "stock_daily_20230101_20260521_v1" for batch in stock_daily_batches))

    def test_membership_batches_are_snapshot_only(self) -> None:
        plan = build_initial_backfill_plan()
        membership_batches = [batch for batch in plan.batches if batch.spec.data_type in {"index_membership", "board_membership"}]

        self.assertEqual(len(membership_batches), 2)
        self.assertTrue(all(batch.start_date == "20260521" for batch in membership_batches))
        self.assertTrue(all(batch.end_date == "20260521" for batch in membership_batches))
        self.assertFalse(any(batch.spec.slice_kind == "month" for batch in membership_batches))

    def test_physical_tables_are_split_and_no_mixed_daily_table_exists(self) -> None:
        plan = build_initial_backfill_plan()
        tables = [batch.spec.table_name for batch in plan.batches]

        self.assertIn("stock_daily_bar_fact", tables)
        self.assertIn("index_daily_bar_fact", tables)
        self.assertIn("board_daily_bar_fact", tables)
        self.assertNotIn("daily_bar_fact", tables)
        for batch in plan.batches:
            self.assertTrue(batch.spec.table_name.startswith(f"{batch.spec.data_domain}_"))

    def test_plan_has_no_side_effects(self) -> None:
        plan = build_initial_backfill_plan()

        self.assertFalse(plan.will_call_external_sources)
        self.assertFalse(plan.will_read_tdx_files)
        self.assertFalse(plan.will_connect_database)
        self.assertFalse(plan.will_execute_sql)
        self.assertFalse(plan.will_write_data_files)
        for batch in plan.batches:
            self.assertFalse(batch.will_call_external_source)
            self.assertFalse(batch.will_read_tdx_files)
            self.assertFalse(batch.will_connect_database)
            self.assertFalse(batch.will_execute_sql)
            self.assertFalse(batch.will_write_data_files)

    def test_month_period_helpers_clip_edges(self) -> None:
        self.assertEqual(month_periods_between("20230115", "20230303"), ("202301", "202302", "202303"))
        self.assertEqual(clipped_month_range("202301", "20230115", "20230303"), ("20230115", "20230131"))
        self.assertEqual(clipped_month_range("202303", "20230115", "20230303"), ("20230301", "20230303"))

    def test_invalid_range_is_rejected(self) -> None:
        with self.assertRaises(IngestionValidationError):
            build_initial_backfill_plan(start_date="20260521", end_date="20230101")

    def test_snapshot_outside_range_is_rejected(self) -> None:
        with self.assertRaises(IngestionValidationError):
            build_initial_backfill_plan(start_date="20230101", end_date="20260521", snapshot_date="20270101")

    def test_invalid_version_is_rejected(self) -> None:
        with self.assertRaises(IngestionValidationError):
            build_initial_backfill_plan(version="version1")


if __name__ == "__main__":
    unittest.main()
