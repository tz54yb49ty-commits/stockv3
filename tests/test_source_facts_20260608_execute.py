import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

from ashare_v3.ingestion.source_facts_20260608_execute import (
    ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY,
    ALLOWED_WRITE_TABLES,
    CONDITION_SOURCE_BATCH_ID,
    CONTRACT_PATH,
    FORBIDDEN_SCOPE_MARKERS,
    IDENTITY_REPAIR_HANDOFF_PATH,
    MISSING_STOCK_IDENTITY_SKIP_THRESHOLD,
    OFFICIAL_DAILY_BATCH_ID,
    PREFLIGHT_PATH,
    ROLLBACK_SQL_PATH,
    SKIP_POLICY_NAME,
    TRADE_DATE,
    SourceFacts20260608Blocked,
    assert_approved_command,
    apply_missing_stock_identity_skip_policy_to_condition_bundle,
    apply_missing_stock_identity_skip_policy_to_official_bundle,
    build_missing_stock_identity_skip_manifest,
    build_handoff_report,
    build_implementation_report,
    build_runner_plan,
    evaluate_missing_identity_policy,
    load_contract,
    load_preflight,
    official_phase_already_committed,
    reconcile_official_no_trade_scope,
    validate_execute_request,
    validate_preflight_allows_execute,
    validate_rollback_sql,
    validate_trade_date,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_n1_20260608_source_facts_once.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("n1_source_facts_20260608_runner", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RecordingConnection:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        raise AssertionError("mock execute_commit_transaction should not use cursor directly")

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class SourceFactsRunnerHarness:
    def __init__(self) -> None:
        self.official_conn = RecordingConnection()
        self.condition_conn = RecordingConnection()
        self.calls: list[str] = []

    def deps(self) -> dict:
        return {
            "connect": self.connect,
            "official_load_execute_contract": self.official_load_execute_contract,
            "official_validate_execute_contract": self.official_validate_execute_contract,
            "official_build_snapshot_from_db": self.official_build_snapshot_from_db,
            "official_build_dry_run_report": self.official_build_dry_run_report,
            "official_build_execute_contract": self.official_build_execute_contract,
            "official_build_execute_preflight_report": self.official_build_execute_preflight_report,
            "official_build_expected_scope_from_db": self.official_build_expected_scope_from_db,
            "official_source_adapter_factory": self.official_source_adapter_factory,
            "official_fetch_official_daily_sources": self.official_fetch_official_daily_sources,
            "official_validate_source_bundle": self.official_validate_source_bundle,
            "official_validate_commit_preconditions": self.official_validate_commit_preconditions,
            "official_build_commit_plan": self.official_build_commit_plan,
            "official_execute_commit_transaction": self.official_execute_commit_transaction,
            "official_load_stock_source_probe": lambda *_args, **_kwargs: {"result": "STOCK_PROBE_PASS", "stock_source": {}},
            "official_load_index_board_source_probe": lambda *_args, **_kwargs: {"result": "FULL_PROBE_PASS"},
            "condition_build_snapshot_from_db": self.condition_build_snapshot_from_db,
            "condition_build_dry_run_report": self.condition_build_dry_run_report,
            "condition_build_execute_contract": self.condition_build_execute_contract,
            "condition_build_execute_preflight_report": self.condition_build_execute_preflight_report,
            "condition_source_builder_factory": self.condition_source_builder_factory,
            "condition_validate_source_bundle": self.condition_validate_source_bundle,
            "condition_validate_commit_preconditions": self.condition_validate_commit_preconditions,
            "condition_build_commit_plan": self.condition_build_commit_plan,
            "condition_execute_commit_transaction": self.condition_execute_commit_transaction,
            "write_dry_run_files": lambda *args, **kwargs: None,
            "write_contract_files": lambda *args, **kwargs: None,
            "write_preflight_files": lambda *args, **kwargs: None,
            "write_execute_report_files": lambda *args, **kwargs: None,
        }

    def connect(self, dsn: str) -> RecordingConnection:
        self.calls.append(f"connect:{len([item for item in self.calls if item.startswith('connect')]) + 1}")
        return self.official_conn if not self.official_conn.committed else self.condition_conn

    def official_load_execute_contract(self, *_args, **_kwargs) -> dict:
        self.calls.append("official_load_execute_contract")
        return {"result": "DESIGN_PASS"}

    def official_validate_execute_contract(self, contract: dict) -> None:
        self.calls.append("official_validate_execute_contract")

    def official_build_snapshot_from_db(self, **_kwargs) -> dict:
        self.calls.append("official_build_snapshot_from_db")
        return {"official_snapshot": True}

    def official_build_dry_run_report(self, **_kwargs) -> dict:
        self.calls.append("official_build_dry_run_report")
        return {"result": "DRY_RUN_PASS"}

    def official_build_execute_contract(self, **_kwargs) -> dict:
        self.calls.append("official_build_execute_contract")
        return {"result": "DESIGN_PASS"}

    def official_build_execute_preflight_report(self, **_kwargs) -> dict:
        self.calls.append("official_build_execute_preflight_report")
        return {"result": "PREFLIGHT_PASS", "quality": {"p0_count": 0}, "production_execute_blockers": []}

    def official_build_expected_scope_from_db(self, **_kwargs) -> dict:
        self.calls.append("official_build_expected_scope_from_db")
        return {"stock": [], "index": [], "board": []}

    def official_source_adapter_factory(self, **_kwargs):
        self.calls.append("official_source_adapter_factory")
        return object()

    def official_fetch_official_daily_sources(self, **_kwargs) -> dict:
        self.calls.append("official_fetch_official_daily_sources")
        return {"stock": [], "index": [], "board": [], "official_no_trade_manifest": [], "stale_identity_manifest": []}

    def official_validate_source_bundle(self, **_kwargs) -> dict:
        self.calls.append("official_validate_source_bundle")
        return {"result": "VALIDATION_PASS", "p0_count": 0, "quality_items": []}

    def official_validate_commit_preconditions(self, **_kwargs) -> None:
        self.calls.append("official_validate_commit_preconditions")

    def official_build_commit_plan(self, **_kwargs) -> dict:
        self.calls.append("official_build_commit_plan")
        return {
            "batch_id": OFFICIAL_DAILY_BATCH_ID,
            "allowed_tables": [
                "common_ingest_batch",
                "common_quality_gate_result",
                "common_active_source_version",
                "stock_daily_bar_fact",
                "index_daily_bar_fact",
                "board_daily_bar_fact",
            ],
            "row_counts": {"stock": 5514, "index": 83, "board": 428, "total": 6025},
        }

    def official_execute_commit_transaction(self, conn, **_kwargs) -> dict:
        self.calls.append("official_execute_commit_transaction")
        conn.commit()
        return {"committed": True, "batch_id": OFFICIAL_DAILY_BATCH_ID, "row_counts": {"total": 6025}}

    def condition_build_snapshot_from_db(self, **_kwargs) -> dict:
        self.calls.append("condition_build_snapshot_from_db")
        return {"condition_snapshot": True}

    def condition_build_dry_run_report(self, *_args, **_kwargs) -> dict:
        self.calls.append("condition_build_dry_run_report")
        return {"result": "DRY_RUN_PASS"}

    def condition_build_execute_contract(self, *_args, **_kwargs) -> dict:
        self.calls.append("condition_build_execute_contract")
        return {"result": "DESIGN_PASS"}

    def condition_build_execute_preflight_report(self, *_args, **_kwargs) -> dict:
        self.calls.append("condition_build_execute_preflight_report")
        return {"result": "PREFLIGHT_PASS", "quality": {"p0_count": 0}, "blockers": []}

    def condition_source_builder_factory(self, **_kwargs):
        self.calls.append("condition_source_builder_factory")
        return self

    def build_source_bundle(self, **_kwargs) -> dict:
        self.calls.append("condition_build_source_bundle")
        return {"stock_daily_basic": [], "stock_financial": [], "index_membership": [], "board_membership": [], "manifests": {}}

    def condition_validate_source_bundle(self, **_kwargs) -> dict:
        self.calls.append("condition_validate_source_bundle")
        return {"result": "VALIDATION_PASS", "p0_count": 0, "quality_items": []}

    def condition_validate_commit_preconditions(self, **_kwargs) -> None:
        self.calls.append("condition_validate_commit_preconditions")

    def condition_build_commit_plan(self, **_kwargs) -> dict:
        self.calls.append("condition_build_commit_plan")
        return {
            "batch_id": CONDITION_SOURCE_BATCH_ID,
            "allowed_tables": [
                "common_ingest_batch",
                "common_quality_gate_result",
                "common_active_source_version",
                "stock_daily_basic",
                "stock_financial_metrics_fact",
                "index_membership_fact",
                "board_membership_fact",
            ],
            "row_counts": {
                "stock_daily_basic": 5514,
                "stock_financial": 5514,
                "index_membership": 12841,
                "board_membership": 56962,
                "total": 80831,
            },
        }

    def condition_execute_commit_transaction(self, conn, **_kwargs) -> dict:
        self.calls.append("condition_execute_commit_transaction")
        conn.commit()
        return {"committed": True, "batch_id": CONDITION_SOURCE_BATCH_ID, "row_counts": {"total": 80831}}


class SourceFacts20260608GuardedRunnerTests(unittest.TestCase):
    def test_missing_each_final_flag_blocks(self) -> None:
        cases = [
            (False, True, True, True, "--execute"),
            (True, False, True, True, "--user-confirmed"),
            (True, True, False, True, "--source-fetch-enabled"),
            (True, True, True, False, "--postgres-commit-enabled"),
        ]

        for execute, confirmed, source_fetch, commit, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(SourceFacts20260608Blocked, message):
                    validate_execute_request(
                        execute_requested=execute,
                        user_confirmed=confirmed,
                        source_fetch_enabled=source_fetch,
                        postgres_commit_enabled=commit,
                    )

    def test_wrong_trade_date_blocks(self) -> None:
        with self.assertRaisesRegex(SourceFacts20260608Blocked, "20260608"):
            validate_trade_date("20260605")

    def test_missing_stock_identity_count_one_skip_pass(self) -> None:
        result = evaluate_missing_identity_policy(
            asset_kind="stock",
            missing_identities=[{"ts_code": "920206.BJ", "canonical_identity_key": "stock:BJ:920206"}],
        )

        self.assertEqual(result["policy_name"], SKIP_POLICY_NAME)
        self.assertEqual(result["threshold"], MISSING_STOCK_IDENTITY_SKIP_THRESHOLD)
        self.assertEqual(result["decision"], "SKIP")
        self.assertEqual(result["severity"], "P1")
        self.assertEqual(result["p0_count"], 0)
        self.assertEqual(result["skipped_count"], 1)

    def test_missing_stock_identity_count_ten_skip_pass(self) -> None:
        result = evaluate_missing_identity_policy(
            asset_kind="stock",
            missing_identities=[
                {"ts_code": f"9202{i:02d}.BJ", "canonical_identity_key": f"stock:BJ:9202{i:02d}"}
                for i in range(10)
            ],
        )

        self.assertEqual(result["decision"], "SKIP")
        self.assertEqual(result["p0_count"], 0)
        self.assertEqual(result["skipped_count"], 10)

    def test_missing_stock_identity_count_eleven_blocks(self) -> None:
        result = evaluate_missing_identity_policy(
            asset_kind="stock",
            missing_identities=[
                {"ts_code": f"9202{i:02d}.BJ", "canonical_identity_key": f"stock:BJ:9202{i:02d}"}
                for i in range(11)
            ],
        )

        self.assertEqual(result["decision"], "BLOCK")
        self.assertEqual(result["severity"], "P0")
        self.assertEqual(result["p0_count"], 1)

    def test_index_or_board_missing_identity_blocks(self) -> None:
        for asset_kind in ("index", "board"):
            with self.subTest(asset_kind=asset_kind):
                result = evaluate_missing_identity_policy(
                    asset_kind=asset_kind,
                    missing_identities=[{"ts_code": "899050.BJ", "canonical_identity_key": "index:BJ:899050"}],
                )

                self.assertEqual(result["decision"], "BLOCK")
                self.assertEqual(result["severity"], "P0")
                self.assertEqual(result["p0_count"], 1)

    def test_skipped_rows_not_written_to_daily_basic_or_financial(self) -> None:
        manifest = build_missing_stock_identity_skip_manifest()

        self.assertEqual(len(manifest), 1)
        self.assertEqual(manifest[0]["ts_code"], "920206.BJ")
        self.assertEqual(manifest[0]["canonical_identity_key"], "stock:BJ:920206")
        self.assertFalse(manifest[0]["writes_stock_daily_bar_fact"])
        self.assertFalse(manifest[0]["writes_stock_daily_basic"])
        self.assertFalse(manifest[0]["writes_stock_financial_metrics_fact"])

    def test_expected_row_shape_matches_contract(self) -> None:
        contract = load_contract(CONTRACT_PATH)
        plan = build_runner_plan(contract=contract, preflight=load_preflight(PREFLIGHT_PATH))

        self.assertEqual(plan["trade_date"], TRADE_DATE)
        self.assertEqual(plan["official_daily_batch_id"], OFFICIAL_DAILY_BATCH_ID)
        self.assertEqual(plan["condition_source_batch_id"], CONDITION_SOURCE_BATCH_ID)
        self.assertEqual(plan["adjusted_expected_rows_with_skip_policy"], ADJUSTED_EXPECTED_ROWS_WITH_SKIP_POLICY)
        self.assertEqual(tuple(plan["allowed_write_tables"]), ALLOWED_WRITE_TABLES)
        self.assertFalse(plan["execute_authorized"])
        self.assertTrue(plan["source_facts_execute_final_gate_review_allowed"])

    def test_allowed_table_scope_and_forbidden_markers(self) -> None:
        self.assertEqual(
            ALLOWED_WRITE_TABLES,
            (
                "common_ingest_batch",
                "common_quality_gate_result",
                "common_active_source_version",
                "stock_daily_bar_fact",
                "index_daily_bar_fact",
                "board_daily_bar_fact",
                "stock_daily_basic",
                "stock_financial_metrics_fact",
                "index_membership_fact",
                "board_membership_fact",
            ),
        )
        self.assertIn("common_event_outbox", FORBIDDEN_SCOPE_MARKERS)
        self.assertIn("N2/N3/N4/N5/N6", FORBIDDEN_SCOPE_MARKERS)

    def test_rollback_sql_static_safe(self) -> None:
        result = validate_rollback_sql(ROLLBACK_SQL_PATH)

        self.assertTrue(result["hard_fail_before_delete"])
        self.assertTrue(result["no_drop_truncate_cascade"])
        self.assertTrue(result["no_forbidden_table_dml"])
        self.assertTrue(result["scope_ids_present"])

    def test_run_real_daily_incremental_is_not_approved_command(self) -> None:
        with self.assertRaisesRegex(SourceFacts20260608Blocked, "not an approved"):
            assert_approved_command("PYTHONPATH=src python3 scripts/run_real_daily_incremental.py --trade-date 20260608")

    def test_dedicated_script_is_approved_command_shape(self) -> None:
        command = (
            "PYTHONPATH=src python3 scripts/run_n1_20260608_source_facts_once.py "
            "--trade-date 20260608 --execute --user-confirmed --source-fetch-enabled --postgres-commit-enabled"
        )

        self.assertTrue(assert_approved_command(command))

    def test_identity_repair_handoff_is_superseded_by_skip_policy(self) -> None:
        handoff = build_handoff_report()

        self.assertEqual(handoff["decision"], "SUPERSEDED_BY_SMALL_MISSING_STOCK_IDENTITY_SKIP_POLICY")
        self.assertEqual(handoff["missing_identity"]["ts_code"], "920206.BJ")
        self.assertEqual(handoff["missing_identity"]["canonical_identity_key"], "stock:BJ:920206")
        self.assertFalse(handoff["source_facts_runner_writes_stock_identity"])
        self.assertEqual(str(IDENTITY_REPAIR_HANDOFF_PATH), "docs/N1_20260608_STOCK_IDENTITY_920206_REPAIR_HANDOFF.json")

    def test_implementation_report_records_policy_pass(self) -> None:
        report = build_implementation_report()

        self.assertEqual(report["result"], "IMPLEMENTATION_PASS")
        self.assertEqual(report["identity_p0_handling"]["decision"], SKIP_POLICY_NAME)
        self.assertEqual(report["remaining_blockers"], [])
        self.assertTrue(report["source_facts_execute_final_gate_review_allowed"])

    def test_cli_execute_after_policy_reaches_non_authorized_write_path(self) -> None:
        runner = load_runner_module()
        harness = SourceFactsRunnerHarness()
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = runner.main(
                [
                    "--trade-date",
                    "20260608",
                    "--execute",
                    "--user-confirmed",
                    "--source-fetch-enabled",
                    "--postgres-commit-enabled",
                    "--no-write-report",
                ],
                dependencies=harness.deps(),
            )

        self.assertEqual(result, 0, stderr.getvalue())
        self.assertIn("official_execute_commit_transaction", harness.calls)
        self.assertIn("condition_execute_commit_transaction", harness.calls)
        self.assertLess(harness.calls.index("official_execute_commit_transaction"), harness.calls.index("condition_build_snapshot_from_db"))
        self.assertTrue(harness.official_conn.committed)
        self.assertTrue(harness.condition_conn.committed)

    def test_cli_missing_execute_flag_blocks_before_any_phase_fetch_or_commit(self) -> None:
        runner = load_runner_module()
        harness = SourceFactsRunnerHarness()

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = runner.main(
                [
                    "--trade-date",
                    "20260608",
                    "--user-confirmed",
                    "--source-fetch-enabled",
                    "--postgres-commit-enabled",
                    "--no-write-report",
                ],
                dependencies=harness.deps(),
            )

        self.assertEqual(result, 0)
        self.assertNotIn("official_fetch_official_daily_sources", harness.calls)
        self.assertNotIn("official_execute_commit_transaction", harness.calls)
        self.assertNotIn("condition_build_source_bundle", harness.calls)
        self.assertNotIn("condition_execute_commit_transaction", harness.calls)

    def test_skip_policy_filters_920206_from_official_and_condition_bundles(self) -> None:
        official = apply_missing_stock_identity_skip_policy_to_official_bundle(
            {
                "stock": [
                    {"ts_code": "920206.BJ", "identity_key": "stock:BJ:920206"},
                    {"ts_code": "000001.SZ", "identity_key": "stock:SZ:000001"},
                ],
                "source_breakdown": {"unmapped_tushare_daily_rows": 1},
            }
        )
        condition = apply_missing_stock_identity_skip_policy_to_condition_bundle(
            {
                "stock_daily_basic": [
                    {"ts_code": "920206.BJ", "stock_identity_key": "stock:BJ:920206"},
                    {"ts_code": "000001.SZ", "stock_identity_key": "stock:SZ:000001"},
                ],
                "stock_financial": [
                    {"ts_code": "920206.BJ", "stock_identity_key": "stock:BJ:920206"},
                    {"ts_code": "000001.SZ", "stock_identity_key": "stock:SZ:000001"},
                ],
                "manifests": {},
            }
        )

        self.assertEqual([row["ts_code"] for row in official["stock"]], ["000001.SZ"])
        self.assertEqual([row["ts_code"] for row in condition["stock_daily_basic"]], ["000001.SZ"])
        self.assertEqual([row["ts_code"] for row in condition["stock_financial"]], ["000001.SZ"])
        self.assertEqual(official["source_breakdown"]["skipped_missing_stock_identity_rows"], 1)
        self.assertEqual(len(condition["manifests"]["missing_stock_identity_skip_manifest"]), 1)

    def test_noncritical_missing_board_daily_is_removed_from_adjusted_expected_scope(self) -> None:
        fixed = reconcile_official_no_trade_scope(
            bundle={
                "stock": [],
                "index": [],
                "board": [{"identity_key": "board:TDX:881001", "board_code": "881001"}],
                "source_breakdown": {},
            },
            expected_scope={
                "stock": [],
                "index": [],
                "board": [
                    {
                        "identity_key": "board:TDX:881001",
                        "code": "881001",
                        "name": "行业样本",
                        "board_type": "tdx_industry",
                    },
                    {
                        "identity_key": "board:TDX:880719",
                        "code": "880719",
                        "name": "地摊经济",
                        "board_type": "tdx_concept",
                    },
                ],
            },
        )

        adjusted_ids = [row["identity_key"] for row in fixed["_source_facts_adjusted_expected_scope"]["board"]]
        self.assertEqual(adjusted_ids, ["board:TDX:881001"])
        self.assertEqual(
            [row["identity_key"] for row in fixed["missing_noncritical_board_daily_skip_manifest"]],
            ["board:TDX:880719"],
        )
        self.assertEqual(fixed["source_breakdown"]["skipped_missing_noncritical_board_daily_rows"], 1)

    def test_missing_industry_board_daily_remains_in_adjusted_expected_scope(self) -> None:
        fixed = reconcile_official_no_trade_scope(
            bundle={"stock": [], "index": [], "board": [], "source_breakdown": {}},
            expected_scope={
                "stock": [],
                "index": [],
                "board": [
                    {
                        "identity_key": "board:TDX:881001",
                        "code": "881001",
                        "name": "行业样本",
                        "board_type": "tdx_industry",
                    }
                ],
            },
        )

        adjusted_ids = [row["identity_key"] for row in fixed["_source_facts_adjusted_expected_scope"]["board"]]
        self.assertEqual(adjusted_ids, ["board:TDX:881001"])
        self.assertEqual(fixed["missing_noncritical_board_daily_skip_manifest"], [])

    def test_official_phase_already_committed_detects_expected_rows_and_active_versions(self) -> None:
        self.assertTrue(
            official_phase_already_committed(
                {
                    "current_daily_fact_rows": {"stock": 5514, "index": 83, "board": 428, "total": 6025},
                    "contract_batch_exists": True,
                    "active_daily_source_versions": [
                        {"source_version": "stock_daily_20260608_v1"},
                        {"source_version": "index_daily_20260608_v1"},
                        {"source_version": "board_daily_20260608_v1"},
                    ],
                }
            )
        )

    def test_cli_writes_reports_without_execute(self) -> None:
        runner = load_runner_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            impl_json = Path(tmpdir) / "implementation.json"
            impl_md = Path(tmpdir) / "implementation.md"
            handoff_json = Path(tmpdir) / "handoff.json"
            handoff_md = Path(tmpdir) / "handoff.md"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = runner.main(
                    [
                        "--trade-date",
                        "20260608",
                        "--implementation-json",
                        str(impl_json),
                        "--implementation-md",
                        str(impl_md),
                        "--handoff-json",
                        str(handoff_json),
                        "--handoff-md",
                        str(handoff_md),
                    ]
                )

            self.assertEqual(result, 0)
            self.assertTrue(impl_json.exists())
            self.assertTrue(impl_md.exists())
            self.assertTrue(handoff_json.exists())
            self.assertTrue(handoff_md.exists())
            self.assertEqual(json.loads(impl_json.read_text())["result"], "IMPLEMENTATION_PASS")


if __name__ == "__main__":
    unittest.main()
