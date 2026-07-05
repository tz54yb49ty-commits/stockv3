import unittest

from ashare_v3.ingestion.backfill_config import build_initial_backfill_plan_from_config
from ashare_v3.ingestion.backfill_plan import build_initial_backfill_plan
from ashare_v3.ingestion.backfill_summary import build_backfill_execution_checklist
from ashare_v3.ingestion.ingestion_acceptance import build_ingestion_acceptance_checklist


class IngestionAcceptanceChecklistTest(unittest.TestCase):
    def test_acceptance_checklist_passes_for_default_backfill(self) -> None:
        checklist = build_ingestion_acceptance_checklist(
            build_backfill_execution_checklist(build_initial_backfill_plan())
        )

        self.assertTrue(checklist.passed)
        self.assertEqual(checklist.batch_count, 211)
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

    def test_acceptance_items_cover_required_ingestion_gates(self) -> None:
        checklist = build_ingestion_acceptance_checklist(
            build_backfill_execution_checklist(build_initial_backfill_plan())
        )
        item_ids = {item.item_id for item in checklist.acceptance_items}

        self.assertIn("structure.physical_split", item_ids)
        self.assertIn("structure.daily_basic_separate", item_ids)
        self.assertIn("source_trace.batch_count", item_ids)
        self.assertIn("source_trace.source_version_groups", item_ids)
        self.assertIn("quality_gate.identity_key_required", item_ids)
        self.assertIn("quality_gate.official_daily_proof_required", item_ids)
        self.assertIn("quality_gate.stock_daily_basic_universe_required", item_ids)
        self.assertIn("quality_gate.no_code_pollution_required", item_ids)
        self.assertIn("archive.parquet_manifest_planned", item_ids)
        self.assertIn("rollback.delete_by_source_batch_id", item_ids)
        self.assertIn("safety.forbidden_layers_absent", item_ids)

    def test_acceptance_evidence_keeps_membership_snapshot_only(self) -> None:
        checklist = build_ingestion_acceptance_checklist(
            build_backfill_execution_checklist(build_initial_backfill_plan())
        )
        membership_item = next(item for item in checklist.acceptance_items if item.item_id == "quality_gate.membership_snapshot_only")

        self.assertTrue(membership_item.passed)
        self.assertEqual(membership_item.evidence["index_membership"]["start_date"], "20260521")
        self.assertEqual(membership_item.evidence["board_membership"]["end_date"], "20260521")

    def test_acceptance_evidence_keeps_monthly_fact_source_versions(self) -> None:
        checklist = build_ingestion_acceptance_checklist(
            build_backfill_execution_checklist(build_initial_backfill_plan())
        )
        monthly_item = next(item for item in checklist.acceptance_items if item.item_id == "source_trace.monthly_fact_versions")

        self.assertTrue(monthly_item.passed)
        self.assertIn("stock_daily_20230101_20260521_v1", monthly_item.evidence["monthly_fact_versions"])
        self.assertIn("stock_daily_basic_20230101_20260521_v1", monthly_item.evidence["monthly_fact_versions"])

    def test_acceptance_has_no_side_effects(self) -> None:
        checklist = build_ingestion_acceptance_checklist(
            build_backfill_execution_checklist(build_initial_backfill_plan())
        )

        self.assertFalse(checklist.will_call_external_sources)
        self.assertFalse(checklist.will_read_tdx_files)
        self.assertFalse(checklist.will_connect_database)
        self.assertFalse(checklist.will_execute_sql)
        self.assertFalse(checklist.will_write_data_files)
        self.assertTrue(next(item for item in checklist.acceptance_items if item.item_id == "safety.no_side_effects").passed)

    def test_acceptance_can_be_built_from_config_plan(self) -> None:
        plan = build_initial_backfill_plan_from_config("configs/initial_backfill.example.toml")
        checklist = build_ingestion_acceptance_checklist(build_backfill_execution_checklist(plan))

        self.assertTrue(checklist.passed)
        self.assertEqual(checklist.batch_count, 211)
        self.assertEqual(checklist.start_date, "20230101")
        self.assertEqual(checklist.end_date, "20260521")


if __name__ == "__main__":
    unittest.main()
