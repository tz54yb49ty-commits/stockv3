import unittest

from ashare_v3.ingestion.backfill_config import build_initial_backfill_plan_from_config
from ashare_v3.ingestion.backfill_plan import build_initial_backfill_plan
from ashare_v3.ingestion.backfill_summary import build_backfill_execution_checklist


class BackfillExecutionChecklistTest(unittest.TestCase):
    def test_default_summary_counts_match_backfill_plan(self) -> None:
        checklist = build_backfill_execution_checklist(build_initial_backfill_plan())

        self.assertTrue(checklist.passed)
        self.assertEqual(checklist.batch_count, 211)
        self.assertEqual(checklist.monthly_period_count, 41)
        self.assertEqual(
            checklist.domain_counts,
            {"common": 1, "stock": 124, "index": 43, "board": 43},
        )
        self.assertEqual(
            checklist.slice_kind_counts,
            {"range": 1, "snapshot": 5, "month": 205},
        )

    def test_table_summaries_are_physical_and_compressed(self) -> None:
        checklist = build_backfill_execution_checklist(build_initial_backfill_plan())
        summaries = {summary.target_table: summary for summary in checklist.table_summaries}

        self.assertEqual(len(summaries), 11)
        self.assertNotIn("daily_bar_fact", summaries)
        self.assertEqual(summaries["stock_daily_bar_fact"].batch_count, 41)
        self.assertEqual(summaries["stock_daily_bar_fact"].first_source_batch_id, "stock_daily_202301_v1")
        self.assertEqual(summaries["stock_daily_bar_fact"].last_source_batch_id, "stock_daily_202605_v1")
        self.assertEqual(summaries["stock_daily_bar_fact"].source_versions, ("stock_daily_20230101_20260521_v1",))
        self.assertEqual(summaries["index_membership_fact"].batch_count, 1)
        self.assertEqual(summaries["board_membership_fact"].batch_count, 1)

    def test_activation_groups_include_full_range_fact_versions(self) -> None:
        checklist = build_backfill_execution_checklist(build_initial_backfill_plan())
        groups = {group.source_version: group for group in checklist.activation_groups}

        self.assertEqual(len(groups), 11)
        self.assertEqual(groups["stock_daily_20230101_20260521_v1"].batch_count, 41)
        self.assertEqual(groups["stock_daily_basic_20230101_20260521_v1"].batch_count, 41)
        self.assertEqual(groups["index_daily_20230101_20260521_v1"].batch_count, 41)
        self.assertEqual(groups["board_daily_20230101_20260521_v1"].batch_count, 41)
        self.assertEqual(groups["stock_financial_20230101_20260521_v1"].batch_count, 41)
        self.assertEqual(groups["index_membership_20260521_v1"].batch_count, 1)
        self.assertEqual(groups["board_membership_20260521_v1"].batch_count, 1)

    def test_rollback_groups_cover_all_batches(self) -> None:
        checklist = build_backfill_execution_checklist(build_initial_backfill_plan())

        self.assertEqual(len(checklist.rollback_groups), len(checklist.activation_groups))
        self.assertEqual(sum(group.source_batch_count for group in checklist.rollback_groups), 211)
        stock_daily_group = next(group for group in checklist.rollback_groups if group.source_version == "stock_daily_20230101_20260521_v1")
        self.assertEqual(stock_daily_group.source_batch_ids[0], "stock_daily_202301_v1")
        self.assertEqual(stock_daily_group.source_batch_ids[-1], "stock_daily_202605_v1")

    def test_membership_summaries_are_snapshot_only(self) -> None:
        checklist = build_backfill_execution_checklist(build_initial_backfill_plan())
        membership = [
            summary
            for summary in checklist.table_summaries
            if summary.data_type in {"index_membership", "board_membership"}
        ]

        self.assertEqual(len(membership), 2)
        self.assertTrue(all(summary.start_date == "20260521" for summary in membership))
        self.assertTrue(all(summary.end_date == "20260521" for summary in membership))
        self.assertTrue(all(summary.slice_kinds == ("snapshot",) for summary in membership))

    def test_summary_has_no_side_effects(self) -> None:
        checklist = build_backfill_execution_checklist(build_initial_backfill_plan())

        self.assertFalse(checklist.will_call_external_sources)
        self.assertFalse(checklist.will_read_tdx_files)
        self.assertFalse(checklist.will_connect_database)
        self.assertFalse(checklist.will_execute_sql)
        self.assertFalse(checklist.will_write_data_files)

    def test_summary_can_be_built_from_config_plan(self) -> None:
        plan = build_initial_backfill_plan_from_config("configs/initial_backfill.example.toml")
        checklist = build_backfill_execution_checklist(plan)

        self.assertTrue(checklist.passed)
        self.assertEqual(checklist.batch_count, 211)
        self.assertEqual(checklist.data_root, "/Volumes/MacRaid/database")


if __name__ == "__main__":
    unittest.main()
