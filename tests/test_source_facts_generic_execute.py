import unittest
import contextlib
import importlib.util
import io
import json
import tempfile
from pathlib import Path

from ashare_v3.ingestion.source_facts_20260608_execute import (
    SourceFacts20260608Blocked,
    validate_trade_date as validate_dedicated_trade_date,
)
from ashare_v3.ingestion import source_facts_20260608_execute as dedicated
from ashare_v3.ingestion.source_facts_generic_execute import (
    SourceFactsGenericBlocked,
    apply_official_expectations,
    assert_approved_command,
    derive_official_expectations_from_bundle,
    derive_official_expectations_from_snapshot,
    build_source_facts_run_config,
    patched_source_facts_module,
    render_rollback_sql,
    validate_rollback_sql_text,
)
from tests.test_source_facts_20260608_execute import SourceFactsRunnerHarness


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_n1_source_facts_once.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("n1_source_facts_generic_runner", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SourceFactsGenericExecuteTests(unittest.TestCase):
    def test_builds_date_scoped_config_for_20260609(self) -> None:
        config = build_source_facts_run_config(
            trade_date="20260609",
            for_trade_date="20260610",
            prev_trade_date="20260608",
            next_trade_date="20260610",
        )

        self.assertEqual(config.trade_date, "20260609")
        self.assertEqual(config.for_trade_date, "20260610")
        self.assertEqual(config.official_daily_batch_id, "official_daily_ingest_20260609_v1")
        self.assertEqual(config.condition_source_batch_id, "condition_source_activation_20260609_v1")
        self.assertEqual(config.official_source_versions["stock"], "stock_daily_20260609_v1")
        self.assertEqual(config.condition_source_versions["stock_daily_basic"], "stock_daily_basic_20260609_v1")
        self.assertEqual(
            config.rollback_sql_path,
            Path("sql/N1_20260609_source_facts_guarded_runner_rollback.sql"),
        )

    def test_patch_allows_dedicated_module_to_run_for_configured_date_and_restores(self) -> None:
        config = build_source_facts_run_config(
            trade_date="20260609",
            for_trade_date="20260610",
            prev_trade_date="20260608",
            next_trade_date="20260610",
        )

        with self.assertRaisesRegex(SourceFacts20260608Blocked, "20260608"):
            validate_dedicated_trade_date("20260609")

        with patched_source_facts_module(config):
            validate_dedicated_trade_date("20260609")

        with self.assertRaisesRegex(SourceFacts20260608Blocked, "20260608"):
            validate_dedicated_trade_date("20260609")

    def test_generic_command_shape_is_strict_and_forbids_incremental_runner(self) -> None:
        self.assertTrue(
            assert_approved_command(
                "PYTHONPATH=src python3 scripts/run_n1_source_facts_once.py "
                "--trade-date 20260609 --execute --user-confirmed "
                "--source-fetch-enabled --postgres-commit-enabled",
                trade_date="20260609",
            )
        )

        with self.assertRaisesRegex(SourceFactsGenericBlocked, "run_real_daily_incremental"):
            assert_approved_command(
                "PYTHONPATH=src python3 scripts/run_real_daily_incremental.py "
                "--trade-date 20260609 --execute --user-confirmed "
                "--source-fetch-enabled --postgres-commit-enabled",
                trade_date="20260609",
            )

        with self.assertRaisesRegex(SourceFactsGenericBlocked, "--postgres-commit-enabled"):
            assert_approved_command(
                "PYTHONPATH=src python3 scripts/run_n1_source_facts_once.py "
                "--trade-date 20260609 --execute --user-confirmed --source-fetch-enabled",
                trade_date="20260609",
            )

    def test_rendered_rollback_sql_is_scoped_and_static_safe(self) -> None:
        config = build_source_facts_run_config(
            trade_date="20260610",
            for_trade_date="20260611",
            prev_trade_date="20260609",
            next_trade_date="20260611",
        )
        sql = render_rollback_sql(config)
        check = validate_rollback_sql_text(sql, config)

        self.assertTrue(check["passed"])
        self.assertIn("official_daily_ingest_20260610_v1", sql)
        self.assertIn("condition_source_activation_20260610_v1", sql)
        self.assertIn("stock_daily_20260610_v1", sql)
        self.assertIn("stock_daily_basic_20260610_v1", sql)
        self.assertTrue(check["hard_fail_before_delete"])
        self.assertTrue(check["no_drop_truncate_cascade"])
        self.assertTrue(check["no_forbidden_table_dml"])

    def test_derives_official_expectations_from_source_breakdown(self) -> None:
        expectations = derive_official_expectations_from_bundle(
            {
                "stock": [{"identity_key": "stock:SZ:000001"}] * 5513,
                "index": [{}] * 83,
                "board": [{}] * 428,
                "official_no_trade_manifest": [{}] * 13,
                "source_breakdown": {
                    "stock_adj_factor_rows": 5528,
                    "matched_identity_rows": 5514,
                    "unmapped_tushare_daily_rows": 1,
                    "stale_identity_excluded": 1,
                    "official_no_trade": 13,
                },
            }
        )

        self.assertEqual(expectations["official_daily"]["stock_daily_bar_fact"], 5513)
        self.assertEqual(expectations["official_daily"]["total_daily_fact"], 6024)
        self.assertEqual(expectations["stock_adj_factor_rows"], 5528)
        self.assertEqual(expectations["matched_stock_identity_rows"], 5513)
        self.assertEqual(expectations["unmapped_tushare_daily_rows"], 1)

    def test_apply_official_expectations_updates_condition_stock_expected_rows(self) -> None:
        expectations = {
            "official_daily": {
                "stock_daily_bar_fact": 5513,
                "index_daily_bar_fact": 83,
                "board_daily_bar_fact": 428,
                "total_daily_fact": 6024,
            },
            "stock_adj_factor_rows": 5528,
            "matched_stock_identity_rows": 5513,
            "unmapped_tushare_daily_rows": 1,
            "stock_scope_breakdown": {},
            "index_scope_breakdown": {},
            "board_scope_breakdown": {},
        }
        original = dedicated.ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY
        try:
            apply_official_expectations(expectations)
            condition = dedicated.ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY["condition_source"]
            self.assertEqual(condition["stock_daily_basic"], 5513)
            self.assertEqual(condition["stock_financial_metrics_fact"], 5513)
        finally:
            dedicated.ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY = original

    def test_derives_official_expectations_from_existing_snapshot_rows_for_resume(self) -> None:
        expectations = derive_official_expectations_from_snapshot(
            {"current_daily_fact_rows": {"stock": 5513, "index": 83, "board": 428, "total": 6024}}
        )

        self.assertEqual(expectations["official_daily"]["stock_daily_bar_fact"], 5513)
        self.assertEqual(expectations["official_daily"]["total_daily_fact"], 6024)
        self.assertEqual(expectations["matched_stock_identity_rows"], 5513)

    def test_cli_writes_date_scoped_implementation_and_rollback_without_execute(self) -> None:
        runner = load_runner_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            impl_json = Path(tmpdir) / "implementation.json"
            impl_md = Path(tmpdir) / "implementation.md"
            rollback_sql = Path(tmpdir) / "rollback.sql"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = runner.main(
                    [
                        "--trade-date",
                        "20260609",
                        "--for-trade-date",
                        "20260610",
                        "--prev-trade-date",
                        "20260608",
                        "--next-trade-date",
                        "20260610",
                        "--implementation-json",
                        str(impl_json),
                        "--implementation-md",
                        str(impl_md),
                        "--rollback-sql-path",
                        str(rollback_sql),
                    ]
                )

            self.assertEqual(result, 0)
            report = json.loads(impl_json.read_text())
            self.assertEqual(report["result"], "IMPLEMENTATION_PASS")
            self.assertEqual(report["trade_date"], "20260609")
            self.assertTrue(impl_md.exists())
            self.assertIn("official_daily_ingest_20260609_v1", rollback_sql.read_text())

    def test_cli_execute_uses_date_scoped_preflight_and_mocked_commit_path(self) -> None:
        runner = load_runner_module()
        harness = SourceFactsRunnerHarness()
        with tempfile.TemporaryDirectory() as tmpdir:
            contract = Path(tmpdir) / "contract.json"
            preflight = Path(tmpdir) / "preflight.json"
            execute_json = Path(tmpdir) / "execute.json"
            execute_md = Path(tmpdir) / "execute.md"
            contract.write_text(json.dumps({"result": "CONTRACT_PASS"}))
            preflight.write_text(
                json.dumps(
                    {
                        "preflight_result": "PREFLIGHT_PASS",
                        "final_execute_gate_allowed": True,
                        "p0_p1_p2": {"P0": 0, "P1": 0, "P2": 0},
                        "blockers": [],
                    }
                )
            )
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = runner.main(
                    [
                        "--trade-date",
                        "20260609",
                        "--for-trade-date",
                        "20260610",
                        "--prev-trade-date",
                        "20260608",
                        "--next-trade-date",
                        "20260610",
                        "--contract-path",
                        str(contract),
                        "--preflight-path",
                        str(preflight),
                        "--execute-report-json",
                        str(execute_json),
                        "--execute-report-md",
                        str(execute_md),
                        "--execute",
                        "--user-confirmed",
                        "--source-fetch-enabled",
                        "--postgres-commit-enabled",
                        "--no-write-report",
                    ],
                    dependencies=harness.deps(),
                )

        self.assertEqual(result, 0)
        self.assertIn("official_execute_commit_transaction", harness.calls)
        self.assertIn("condition_execute_commit_transaction", harness.calls)

    def test_patched_reports_and_ingest_sources_are_date_scoped(self) -> None:
        config = build_source_facts_run_config(
            trade_date="20260609",
            for_trade_date="20260610",
            prev_trade_date="20260608",
            next_trade_date="20260610",
        )

        class Cursor:
            def __init__(self) -> None:
                self.sql: list[str] = []

            def execute(self, sql, params=None):
                self.sql.append(str(sql))

        with patched_source_facts_module(config):
            markdown = dedicated.render_execute_report_markdown(
                {
                    "result": "EXECUTE_PASS",
                    "layer_role": "N1_ingestion",
                    "execute_authorized": True,
                    "row_counts": {},
                    "skip_policy": {},
                }
            )
            cursor = Cursor()
            dedicated.official_insert_ingest_batch(cursor, {"row_counts": {"total": 1}})
            dedicated.condition_insert_ingest_batch(cursor, {"row_counts": {"total": 1}, "manifests": {}})

        self.assertIn("N1 20260609 Source Facts Execute Report", markdown)
        joined_sql = "\n".join(cursor.sql)
        self.assertIn("n1.source_facts_20260609.official_daily", joined_sql)
        self.assertIn("n1.source_facts_20260609.condition_source", joined_sql)


if __name__ == "__main__":
    unittest.main()
