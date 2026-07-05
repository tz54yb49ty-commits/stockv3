import unittest

from ashare_v3.ingestion.daily_incremental_acceptance import build_daily_incremental_acceptance_checklist
from ashare_v3.ingestion.daily_incremental_config import load_daily_incremental_config
from ashare_v3.ingestion.daily_incremental_summary import build_daily_incremental_execution_checklist


class DailyIncrementalAcceptanceChecklistTest(unittest.TestCase):
    def test_acceptance_checklist_passes_for_example_daily_config(self) -> None:
        checklist = build_daily_acceptance()

        self.assertTrue(checklist.passed)
        self.assertEqual(checklist.trade_date, "20260522")
        self.assertEqual(checklist.version, "v1")
        self.assertEqual(checklist.task_count, 11)
        self.assertEqual(len(checklist.acceptance_items), 17)
        self.assertEqual(
            checklist.category_counts,
            {
                "structure": 3,
                "source_trace": 4,
                "quality_gate": 5,
                "archive": 1,
                "rollback": 2,
                "safety": 2,
            },
        )

    def test_acceptance_items_cover_daily_incremental_gates(self) -> None:
        checklist = build_daily_acceptance()
        item_ids = {item.item_id for item in checklist.acceptance_items}

        self.assertIn("structure.physical_split", item_ids)
        self.assertIn("structure.daily_basic_separate", item_ids)
        self.assertIn("source_trace.batch_count", item_ids)
        self.assertIn("source_trace.single_day_source_versions", item_ids)
        self.assertIn("source_trace.tdx_refresh_tasks", item_ids)
        self.assertIn("quality_gate.identity_key_required", item_ids)
        self.assertIn("quality_gate.membership_daily_refresh_required", item_ids)
        self.assertIn("quality_gate.official_daily_proof_required", item_ids)
        self.assertIn("quality_gate.stock_daily_basic_universe_required", item_ids)
        self.assertIn("quality_gate.no_code_pollution_required", item_ids)
        self.assertIn("archive.parquet_manifest_planned", item_ids)
        self.assertIn("rollback.delete_by_source_batch_id", item_ids)
        self.assertIn("safety.forbidden_layers_absent", item_ids)

    def test_acceptance_evidence_keeps_single_day_source_versions(self) -> None:
        checklist = build_daily_acceptance()
        source_version_item = next(item for item in checklist.acceptance_items if item.item_id == "source_trace.single_day_source_versions")

        self.assertTrue(source_version_item.passed)
        self.assertIn("stock_daily_20260522_v1", source_version_item.evidence["source_versions"])
        self.assertIn("stock_daily_basic_20260522_v1", source_version_item.evidence["source_versions"])
        self.assertTrue(all(source_version.endswith("_20260522_v1") for source_version in source_version_item.evidence["source_versions"]))

    def test_acceptance_evidence_keeps_tdx_daily_refresh_tasks(self) -> None:
        checklist = build_daily_acceptance()
        refresh_item = next(item for item in checklist.acceptance_items if item.item_id == "source_trace.tdx_refresh_tasks")
        membership_item = next(item for item in checklist.acceptance_items if item.item_id == "quality_gate.membership_daily_refresh_required")

        self.assertTrue(refresh_item.passed)
        self.assertEqual(refresh_item.evidence["tdx_refresh_task_ids"], ["board_identity", "index_membership", "board_membership"])
        self.assertTrue(membership_item.passed)
        self.assertIn("index_membership_fact", membership_item.evidence["tdx_refresh_tables"])
        self.assertIn("board_membership_fact", membership_item.evidence["tdx_refresh_tables"])

    def test_acceptance_evidence_keeps_archive_and_rollback_coverage(self) -> None:
        checklist = build_daily_acceptance()
        archive_item = next(item for item in checklist.acceptance_items if item.item_id == "archive.parquet_manifest_planned")
        rollback_item = next(item for item in checklist.acceptance_items if item.item_id == "rollback.rollback_groups_complete")

        self.assertTrue(archive_item.passed)
        self.assertEqual(len(archive_item.evidence["archive_datasets"]), 7)
        self.assertIn("stock_daily_basic", archive_item.evidence["archive_datasets"])
        self.assertTrue(rollback_item.passed)
        self.assertEqual(rollback_item.evidence["rollback_group_count"], 11)
        self.assertEqual(rollback_item.evidence["covered_batch_count"], 11)

    def test_acceptance_has_no_side_effects(self) -> None:
        checklist = build_daily_acceptance()

        self.assertFalse(checklist.will_call_external_sources)
        self.assertFalse(checklist.will_read_tdx_files)
        self.assertFalse(checklist.will_connect_database)
        self.assertFalse(checklist.will_execute_sql)
        self.assertFalse(checklist.will_write_data_files)
        self.assertTrue(next(item for item in checklist.acceptance_items if item.item_id == "safety.no_side_effects").passed)


def build_daily_acceptance():
    config = load_daily_incremental_config("configs/daily_incremental.example.toml")
    summary = build_daily_incremental_execution_checklist(config.to_plan(), source_configs=config.sources)
    return build_daily_incremental_acceptance_checklist(summary)


if __name__ == "__main__":
    unittest.main()
