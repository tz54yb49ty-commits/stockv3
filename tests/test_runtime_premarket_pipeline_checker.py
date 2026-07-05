from pathlib import Path
import tempfile
import unittest

from ashare_v3.runtime_control.premarket import (
    build_premarket_pipeline_readiness,
    expected_premarket_run_ids,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RuntimePremarketPipelineCheckerTest(unittest.TestCase):
    def test_expected_run_ids_are_stable_for_n1_to_n3_to_a1(self) -> None:
        run_ids = expected_premarket_run_ids(
            source_trade_date="20260529",
            for_trade_date="20260601",
            condition_run_id="condition_layer_20260529_source_20260529_v6",
        )

        self.assertEqual(run_ids["n1_official_daily_batch_id"], "official_daily_ingest_20260529_v1")
        self.assertEqual(run_ids["n2_condition_run_id"], "condition_layer_20260529_source_20260529_v6")
        self.assertEqual(
            run_ids["n3_subscription_run_id"],
            "market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6",
        )
        self.assertEqual(
            run_ids["a1_preload_run_id"],
            "previous_day_minute_preload_20260529_for_20260601__"
            "market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6",
        )

    def test_checker_passes_current_documented_20260529_to_20260601_pipeline(self) -> None:
        report = build_premarket_pipeline_readiness(
            source_trade_date="20260529",
            for_trade_date="20260601",
            condition_run_id="condition_layer_20260529_source_20260529_v6",
            docs_dir=PROJECT_ROOT / "docs",
            sql_dir=PROJECT_ROOT / "sql",
        )

        self.assertEqual(report["result"], "PASS")
        self.assertFalse(report["side_effects"]["writes_database"])
        self.assertFalse(report["side_effects"]["executes_n1_n6"])
        self.assertFalse(report["side_effects"]["starts_worker"])
        self.assertEqual([stage["stage_id"] for stage in report["stages"]], ["n1", "n2", "n3", "a1"])
        self.assertTrue(all(stage["status"] in {"READY", "PASS"} for stage in report["stages"]))
        self.assertEqual(report["run_id_rules"]["status"], "PASS")
        self.assertEqual(report["rollback_registry"]["status"], "PASS")
        self.assertEqual(report["risk_summary"]["worker_risk"], "manual_pre_execute_check_required")
        self.assertIn("N3_market_data", report["next_step"])

    def test_checker_blocks_when_required_rollback_sql_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sql_dir = Path(tmp)
            for required in (
                "N1_official_daily_20260529_ingestion_rollback.sql",
                "N1_condition_source_20260529_activation_rollback.sql",
                "N2_level_score_20260529_v6_rollback.sql",
                "N3_subscription_20260601_rollback.sql",
            ):
                (sql_dir / required).write_text("-- rollback stub\n", encoding="utf-8")

            report = build_premarket_pipeline_readiness(
                source_trade_date="20260529",
                for_trade_date="20260601",
                condition_run_id="condition_layer_20260529_source_20260529_v6",
                docs_dir=PROJECT_ROOT / "docs",
                sql_dir=sql_dir,
            )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("sql/N3_A1_previous_day_minute_20260601_rollback.sql", report["missing_rollback_paths"])


if __name__ == "__main__":
    unittest.main()
