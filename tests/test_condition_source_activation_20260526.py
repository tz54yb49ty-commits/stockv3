import contextlib
import importlib.util
import io
import unittest
from pathlib import Path

from ashare_v3.ingestion.condition_source_activation_20260526 import (
    ACTIVE_SCOPES,
    ALLOWED_FUTURE_WRITE_TABLES,
    BATCH_ID,
    SOURCE_VERSIONS,
    TRADE_DATE,
    build_contract,
    build_dry_run_report,
    build_preflight,
    build_rollback_sql,
    sample_pass_snapshot,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "plan_condition_source_activation_20260526.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("n1_condition_source_activation_runner", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ConditionSourceActivation20260526Tests(unittest.TestCase):
    def test_dry_run_passes_with_expected_rows_and_no_side_effects(self) -> None:
        report = build_dry_run_report(sample_pass_snapshot())

        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertEqual(
            report["expected_rows"],
            {
                "stock_daily_basic": 5520,
                "stock_financial": 5520,
                "index_membership": 12841,
                "board_membership": 56872,
                "total": 80753,
            },
        )
        self.assertEqual(report["quality"], {"p0_count": 0, "p1_count": 0, "p2_count": 0})
        self.assertFalse(report["side_effects"]["writes_postgres"])
        self.assertFalse(report["side_effects"]["writes_parquet"])
        self.assertFalse(report["side_effects"]["enters_n2_n3_n4_n5_n6"])

    def test_contract_uses_requested_batch_versions_scopes_and_write_scope(self) -> None:
        contract = build_contract(sample_pass_snapshot())

        self.assertEqual(contract["result"], "DESIGN_PASS")
        self.assertEqual(contract["source_batch_id"], BATCH_ID)
        self.assertEqual(contract["source_versions"], SOURCE_VERSIONS)
        self.assertEqual(contract["active_scopes"], ACTIVE_SCOPES)
        self.assertEqual(set(contract["future_write_scope"]["allowed_tables"]), set(ALLOWED_FUTURE_WRITE_TABLES))
        self.assertFalse(contract["future_write_scope"]["writes_parquet"])
        self.assertFalse(contract["future_write_scope"]["writes_outbox"])
        self.assertIn("stock_daily_basic", contract["source_strategy"])
        self.assertIn("stock_financial", contract["source_strategy"])
        self.assertIn("index_membership", contract["source_strategy"])
        self.assertIn("board_membership", contract["source_strategy"])

    def test_preflight_is_ready_for_final_gate_after_execute_runner_implementation(self) -> None:
        preflight = build_preflight(sample_pass_snapshot())

        self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
        self.assertEqual(preflight["runner_readiness"], "ready_for_final_gate")
        self.assertTrue(preflight["execute_runner_implemented"])
        self.assertTrue(preflight["postgres_commit_implemented"])
        self.assertTrue(preflight["final_execute_gate_allowed"])
        self.assertFalse(preflight["execute_runner_implementation_allowed"])

    def test_existing_target_rows_block(self) -> None:
        snapshot = sample_pass_snapshot()
        snapshot["current_target_fact_rows"]["stock_daily_basic"] = 1
        snapshot["active_target_source_versions"] = [
            {
                "data_domain": "stock",
                "data_type": "stock_daily_basic",
                "scope_key": "20260526",
                "source_version": "stock_daily_basic_20260526_v1",
            }
        ]

        report = build_dry_run_report(snapshot)

        self.assertEqual(report["result"], "DRY_RUN_BLOCKED")
        self.assertIn("target_fact_already_exists", report["blockers"])
        self.assertIn("active_source_version_conflict", report["blockers"])
        self.assertGreater(report["quality"]["p0_count"], 0)

    def test_stale_and_no_trade_not_required_in_stock_scope(self) -> None:
        report = build_dry_run_report(sample_pass_snapshot())

        stock_scope = report["stock_scope_policy"]
        self.assertEqual(stock_scope["expected_stock_rows"], 5520)
        self.assertEqual(stock_scope["stale_identity_excluded"], ["stock:SZ:300114"])
        self.assertEqual(stock_scope["official_no_trade_excluded"], ["stock:BJ:920058", "stock:BJ:920305"])
        self.assertFalse(stock_scope["requires_no_trade_bj_daily_basic_rows"])

    def test_rollback_sql_targets_only_condition_source_activation_scope(self) -> None:
        sql = build_rollback_sql()

        self.assertIn(BATCH_ID, sql)
        for source_version in SOURCE_VERSIONS.values():
            self.assertIn(source_version, sql)
        self.assertIn("stock_daily_basic", sql)
        self.assertIn("stock_financial_metrics_fact", sql)
        self.assertIn("index_membership_fact", sql)
        self.assertIn("board_membership_fact", sql)
        self.assertNotIn("common_event_outbox", sql)
        self.assertNotIn("condition_basis", sql)
        self.assertNotIn("stock_daily_bar_fact", sql)

    def test_runner_rejects_execute_flag(self) -> None:
        module = load_runner_module()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = module.main(["--execute"])

        self.assertEqual(exit_code, 2)
        self.assertIn("dry-run/contract generator only", stderr.getvalue())

    def test_runner_can_emit_json_without_writing_artifacts(self) -> None:
        module = load_runner_module()
        sample = sample_pass_snapshot()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = module.main(
                ["--no-write", "--json"],
                dependencies={"build_snapshot_from_db": lambda **_: sample},
            )

        self.assertEqual(exit_code, 0)
        self.assertIn('"result": "IMPLEMENTATION_PASS"', stdout.getvalue())
        self.assertIn('"trade_date": "20260526"', stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
