import unittest

from ashare_v3.ingestion.daily_incremental_config import load_daily_incremental_config
from ashare_v3.ingestion.daily_incremental_summary import build_daily_incremental_execution_checklist


class DailyIncrementalExecutionChecklistTest(unittest.TestCase):
    def test_summary_counts_match_daily_plan(self) -> None:
        checklist = build_daily_checklist()

        self.assertTrue(checklist.passed)
        self.assertEqual(checklist.task_count, 11)
        self.assertEqual(checklist.domain_counts, {"common": 1, "stock": 4, "index": 3, "board": 3})
        self.assertEqual(checklist.trade_date, "20260522")
        self.assertEqual(checklist.version, "v1")

    def test_table_summaries_are_physical_daily_tables(self) -> None:
        checklist = build_daily_checklist()
        summaries = {summary.target_table: summary for summary in checklist.table_summaries}

        self.assertEqual(len(summaries), 11)
        self.assertNotIn("daily_bar_fact", summaries)
        self.assertEqual(summaries["stock_daily_bar_fact"].source_batch_id, "stock_daily_20260522_v1")
        self.assertEqual(summaries["stock_daily_bar_fact"].source_version, "stock_daily_20260522_v1")
        self.assertEqual(summaries["stock_daily_basic"].source_batch_id, "stock_daily_basic_20260522_v1")
        self.assertEqual(summaries["index_membership_fact"].source_batch_id, "index_membership_20260522_v1")
        self.assertEqual(summaries["board_membership_fact"].source_batch_id, "board_membership_20260522_v1")

    def test_activation_groups_are_single_day_versions(self) -> None:
        checklist = build_daily_checklist()
        groups = {group.source_version: group for group in checklist.activation_groups}

        self.assertEqual(len(groups), 11)
        self.assertEqual(groups["stock_daily_20260522_v1"].source_batch_count, 1)
        self.assertEqual(groups["stock_daily_basic_20260522_v1"].source_batch_count, 1)
        self.assertEqual(groups["index_daily_20260522_v1"].source_batch_count, 1)
        self.assertEqual(groups["board_daily_20260522_v1"].source_batch_count, 1)
        for source_version, group in groups.items():
            self.assertTrue(source_version.endswith("_20260522_v1"))
            self.assertEqual(group.source_batch_ids, (source_version,))

    def test_rollback_groups_cover_all_daily_batches(self) -> None:
        checklist = build_daily_checklist()

        self.assertEqual(len(checklist.rollback_groups), len(checklist.activation_groups))
        self.assertEqual(sum(group.source_batch_count for group in checklist.rollback_groups), 11)
        stock_daily_group = next(group for group in checklist.rollback_groups if group.source_version == "stock_daily_20260522_v1")
        self.assertEqual(stock_daily_group.source_batch_ids, ("stock_daily_20260522_v1",))
        self.assertEqual(stock_daily_group.rollback_strategy, "delete_source_batch_id_then_restore_previous_active_source_version")

    def test_tdx_refresh_tasks_are_explicit(self) -> None:
        checklist = build_daily_checklist()

        self.assertEqual(
            tuple(task.task_id for task in checklist.tdx_refresh_tasks),
            ("board_identity", "index_membership", "board_membership"),
        )
        self.assertTrue(all(task.refresh_policy == "daily_read_local_txt" for task in checklist.tdx_refresh_tasks))
        self.assertEqual(checklist.tdx_refresh_tasks[1].source_file, "指数板块.txt")

    def test_summary_has_no_side_effects(self) -> None:
        checklist = build_daily_checklist()

        self.assertFalse(checklist.will_call_external_sources)
        self.assertFalse(checklist.will_read_tdx_files)
        self.assertFalse(checklist.will_connect_database)
        self.assertFalse(checklist.will_execute_sql)
        self.assertFalse(checklist.will_write_data_files)


def build_daily_checklist():
    config = load_daily_incremental_config("configs/daily_incremental.example.toml")
    return build_daily_incremental_execution_checklist(config.to_plan(), source_configs=config.sources)


if __name__ == "__main__":
    unittest.main()
