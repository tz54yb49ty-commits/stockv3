import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DRY_RUN_JSON = PROJECT_ROOT / "docs" / "N1_official_daily_20260525_ingestion_dry_run_plan.json"
EXECUTE_JSON = PROJECT_ROOT / "docs" / "N1_official_daily_20260525_ingestion_execute_contract.json"
ROLLBACK_SQL = PROJECT_ROOT / "sql" / "N1_official_daily_20260525_ingestion_rollback.sql"


class N1OfficialDailyIngestionContractTest(unittest.TestCase):
    def test_dry_run_plan_covers_eod_missing_scope_and_has_no_side_effects(self) -> None:
        plan = json.loads(DRY_RUN_JSON.read_text())

        self.assertEqual(plan["result"], "DESIGN_PASS")
        self.assertEqual(plan["layer_role"], "N1_ingestion")
        self.assertEqual(plan["contract_batch_id"], "official_daily_ingest_20260525_v1")
        self.assertEqual(plan["expected_eod_coverage_objects"], {"stock": 2052, "index": 9, "board": 127, "total": 2188})
        self.assertEqual(plan["available_official_daily_before_execute"], {"stock": 0, "index": 0, "board": 0, "total": 0})
        self.assertEqual(plan["source_versions"]["stock"], "stock_daily_20260525_v1")
        self.assertEqual(plan["source_versions"]["index"], "index_daily_20260525_v1")
        self.assertEqual(plan["source_versions"]["board"], "board_daily_20260525_v1")
        self.assertFalse(plan["future_write_scope"]["writes_parquet"])
        self.assertFalse(any(plan["side_effects"].values()))

    def test_execute_contract_requires_dual_confirmation_and_blocks_overwrite(self) -> None:
        contract = json.loads(EXECUTE_JSON.read_text())

        self.assertEqual(contract["result"], "DESIGN_PASS")
        self.assertEqual(set(contract["execute_flags_required"]), {"--execute", "--user-confirmed"})
        self.assertEqual(contract["idempotency_policy"]["mode"], "block_on_existing")
        self.assertTrue(contract["idempotency_policy"]["block_if_common_ingest_batch_exists"])
        self.assertTrue(contract["idempotency_policy"]["block_if_fact_source_version_exists"])
        self.assertTrue(contract["idempotency_policy"]["block_if_active_source_version_scope_exists"])
        self.assertFalse(contract["idempotency_policy"]["overwrite_active_source_version"])
        self.assertEqual(contract["quality_commit_gate"]["p0_required"], 0)
        self.assertFalse(contract["future_write_scope"]["writes_parquet"])
        self.assertFalse(contract["future_write_scope"]["writes_outbox"])
        self.assertFalse(contract["future_write_scope"]["consumes_c3_outbox"])

    def test_future_write_scope_is_limited_to_n1_official_daily_tables(self) -> None:
        contract = json.loads(EXECUTE_JSON.read_text())
        allowed = set(contract["future_write_scope"]["allowed_tables"])

        self.assertEqual(
            allowed,
            {
                "common_ingest_batch",
                "common_quality_gate_result",
                "common_active_source_version",
                "stock_daily_bar_fact",
                "index_daily_bar_fact",
                "board_daily_bar_fact",
            },
        )
        forbidden_text = " ".join(contract["forbidden_write_tables"])
        self.assertIn("common_event_outbox", forbidden_text)
        self.assertIn("stock_eod_snapshot", forbidden_text)
        self.assertIn("condition tables", forbidden_text)
        self.assertIn("trigger/action/user/voice/mobile/sim/position tables", forbidden_text)

    def test_rollback_sql_only_targets_n1_contract_batch(self) -> None:
        sql = ROLLBACK_SQL.read_text()

        self.assertIn("official_daily_ingest_20260525_v1", sql)
        self.assertIn("stock_daily_20260525_v1", sql)
        self.assertIn("index_daily_20260525_v1", sql)
        self.assertIn("board_daily_20260525_v1", sql)
        self.assertIn("DELETE FROM stock_daily_bar_fact", sql)
        self.assertIn("DELETE FROM index_daily_bar_fact", sql)
        self.assertIn("DELETE FROM board_daily_bar_fact", sql)
        self.assertIn("DELETE FROM common_quality_gate_result", sql)
        self.assertIn("DELETE FROM common_ingest_batch", sql)
        self.assertNotIn("common_event_outbox", sql)
        self.assertNotIn("stock_eod_snapshot", sql)
        self.assertNotIn("common_trigger", sql)
        self.assertNotIn("common_action", sql)


if __name__ == "__main__":
    unittest.main()
