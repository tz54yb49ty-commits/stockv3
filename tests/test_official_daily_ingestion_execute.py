import json
import contextlib
import importlib.util
import io
import subprocess
import sys
import unittest
from pathlib import Path

from ashare_v3.ingestion.official_daily_ingestion_execute import (
    ALLOWED_EXECUTE_WRITE_TABLES,
    CONTRACT_BATCH_ID,
    DEFAULT_ROLLBACK_SQL_PATH,
    FORBIDDEN_WRITE_TABLES,
    OfficialDailyExecuteBlocked,
    build_commit_plan,
    build_execute_preflight_report,
    execute_commit_transaction,
    fetch_official_daily_sources,
    validate_commit_preconditions,
    validate_execute_request,
    validate_source_bundle,
)
from ashare_v3.ingestion.official_daily_ingestion_plan import FIXED_9_INDEX_IDENTITIES, SOURCE_VERSIONS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_official_daily_ingestion_20260525_once.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("n1_official_daily_runner", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def base_dry_run_report() -> dict:
    return {
        "result": "DRY_RUN_PASS",
        "blocked": False,
        "for_trade_date": "20260525",
        "contract_batch_id": CONTRACT_BATCH_ID,
        "source_versions": dict(SOURCE_VERSIONS),
        "expected_eod_coverage_objects": {"stock": 2052, "index": 9, "board": 127, "total": 2188},
        "available_official_daily_before_execute": {"stock": 0, "index": 0, "board": 0, "total": 0},
        "missing_official_daily": {
            "missing_by_asset": {"stock": 2052, "index": 9, "board": 127, "total": 2188},
        },
        "quality": {"p0_count": 0, "p1_count": 2, "p2_count": 1, "items": []},
        "side_effects": {
            "will_call_external_sources": False,
            "writes_postgres": False,
            "writes_parquet": False,
            "updates_active_source_version": False,
            "writes_outbox": False,
            "consumes_c3_outbox": False,
            "enters_n3_n4_n5_n6": False,
            "worker_started": False,
            "old_system_touched": False,
            "real_trading": False,
        },
    }


def base_baseline() -> dict:
    return {
        "common_ingest_batch_exists": False,
        "target_source_version_conflicts": {"stock": 0, "index": 0, "board": 0},
        "active_source_versions_for_trade_date": [],
        "current_official_daily_rows": {"stock": 0, "index": 0, "board": 0, "total": 0},
        "eod_snapshot_rows": {"stock": 0, "index": 0, "board": 0, "total": 0},
        "c3_outbox_status": {"pending": 17432, "delivered": 0, "delivering": 0, "total": 17432},
    }


def expected_scope() -> dict:
    return {
        "stock": [
            {"identity_key": "stock:SH:600000", "exchange": "SH", "code": "600000", "name": "浦发银行"},
            {"identity_key": "stock:SZ:000001", "exchange": "SZ", "code": "000001", "name": "平安银行"},
        ],
        "index": [
            {
                "identity_key": identity_key,
                "exchange": identity_key.split(":")[1],
                "code": identity_key.split(":")[2],
                "name": f"index-{identity_key.split(':')[2]}",
            }
            for identity_key in FIXED_9_INDEX_IDENTITIES
        ],
        "board": [
            {"identity_key": "board:TDX:881001", "exchange": "TDX", "code": "881001", "name": "行业板块1"},
            {"identity_key": "board:TDX:881002", "exchange": "TDX", "code": "881002", "name": "行业板块2"},
        ],
    }


def row_for(asset: str, scope_row: dict) -> dict:
    row = {
        "asset_kind": asset,
        "identity_key": scope_row["identity_key"],
        "trade_date": "20260525",
        "exchange": scope_row["exchange"],
        "code": scope_row["code"],
        "name": scope_row["name"],
        "open": 10.0,
        "high": 10.8,
        "low": 9.8,
        "close": 10.5,
        "volume": 100000.0,
        "amount": 1234567.0,
        "source": "mock.official_daily",
        "source_batch_id": CONTRACT_BATCH_ID,
        "source_version": SOURCE_VERSIONS[asset],
        "raw_payload": {"mock": True},
    }
    if asset == "stock":
        row["ts_code"] = f"{scope_row['code']}.{scope_row['exchange']}"
        row["adj_factor"] = 1.0
        row["official_daily_proof"] = True
    if asset == "board":
        row["board_code"] = scope_row["code"]
        row["board_name"] = scope_row["name"]
        row["board_type"] = "industry"
    return row


def valid_source_bundle(scope: dict | None = None) -> dict:
    scope = scope or expected_scope()
    return {
        asset: [row_for(asset, scope_row) for scope_row in scope[asset]]
        for asset in ("stock", "index", "board")
    }


class FakeOfficialDailyAdapter:
    def __init__(self, bundle: dict) -> None:
        self.bundle = bundle

    def fetch_stock_daily(self, *, for_trade_date: str, expected_scope: list[dict]) -> list[dict]:
        return list(self.bundle["stock"])

    def fetch_index_daily(self, *, for_trade_date: str, expected_scope: list[dict]) -> list[dict]:
        return list(self.bundle["index"])

    def fetch_board_daily(self, *, for_trade_date: str, expected_scope: list[dict]) -> list[dict]:
        return list(self.bundle["board"])


class RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, sql: str, params: tuple | dict | None = None) -> None:
        self.statements.append(" ".join(sql.split()))


class RecordingConnection:
    def __init__(self) -> None:
        self.cursor_obj = RecordingCursor()
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> RecordingCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class RunnerHarness:
    def __init__(self, *, bundle: dict | None = None, baseline: dict | None = None) -> None:
        self.scope = expected_scope()
        self.bundle = bundle or valid_source_bundle(self.scope)
        self.baseline = baseline or base_baseline()
        self.conn = RecordingConnection()
        self.calls: list[str] = []
        self.real_source_fetch_called = False

    def deps(self) -> dict:
        return {
            "load_execute_contract": self.load_execute_contract,
            "load_dry_run_report": self.load_dry_run_report,
            "build_baseline_snapshot_from_db": self.build_baseline_snapshot_from_db,
            "build_expected_scope_from_db": self.build_expected_scope_from_db,
            "source_adapter_factory": self.source_adapter_factory,
            "connect": self.connect,
            "fetch_official_daily_sources": self.fetch_sources,
            "validate_source_bundle": self.validate_bundle,
            "validate_commit_preconditions": self.validate_preconditions,
            "build_commit_plan": self.build_plan,
            "execute_commit_transaction": self.execute_commit,
            "write_preflight_files": self.write_preflight_files,
        }

    def load_execute_contract(self, path: str) -> dict:
        self.calls.append("load_execute_contract")
        return {
            "result": "DESIGN_PASS",
            "contract_batch_id": CONTRACT_BATCH_ID,
            "source_versions": dict(SOURCE_VERSIONS),
        }

    def load_dry_run_report(self, path: str) -> dict:
        self.calls.append("load_dry_run_report")
        return base_dry_run_report()

    def build_baseline_snapshot_from_db(self, **kwargs) -> dict:
        self.calls.append("build_baseline_snapshot_from_db")
        return self.baseline

    def build_expected_scope_from_db(self, **kwargs) -> dict:
        self.calls.append("build_expected_scope_from_db")
        return self.scope

    def source_adapter_factory(self, **kwargs) -> FakeOfficialDailyAdapter:
        self.calls.append("source_adapter_factory")
        return FakeOfficialDailyAdapter(self.bundle)

    def connect(self, dsn: str) -> RecordingConnection:
        self.calls.append("connect")
        return self.conn

    def fetch_sources(self, **kwargs) -> dict:
        self.calls.append("fetch_official_daily_sources")
        return fetch_official_daily_sources(**kwargs)

    def validate_bundle(self, **kwargs) -> dict:
        self.calls.append("validate_source_bundle")
        return validate_source_bundle(**kwargs)

    def validate_preconditions(self, **kwargs) -> None:
        self.calls.append("validate_commit_preconditions")
        validate_commit_preconditions(**kwargs)

    def build_plan(self, **kwargs) -> dict:
        self.calls.append("build_commit_plan")
        return build_commit_plan(**kwargs)

    def execute_commit(self, *args, **kwargs) -> dict:
        self.calls.append("execute_commit_transaction")
        return execute_commit_transaction(*args, **kwargs)

    def write_preflight_files(self, *args, **kwargs) -> None:
        self.calls.append("write_preflight_files")


class OfficialDailyExecutePreflightTests(unittest.TestCase):
    def test_preflight_passes_with_clean_baseline_without_authorizing_execute(self) -> None:
        report = build_execute_preflight_report(
            dry_run_report=base_dry_run_report(),
            baseline=base_baseline(),
            execute_requested=False,
            user_confirmed=False,
            rollback_sql_path=DEFAULT_ROLLBACK_SQL_PATH,
        )

        self.assertEqual(report["result"], "PREFLIGHT_PASS")
        self.assertFalse(report["blocked"])
        self.assertFalse(report["execute_authorized"])
        self.assertEqual(report["runner_readiness"], "ready_for_final_gate")
        self.assertEqual(report["missing_official_daily"], {"stock": 2052, "index": 9, "board": 127, "total": 2188})
        self.assertEqual(report["baseline_rows"]["eod_snapshot_rows"]["total"], 0)
        self.assertEqual(report["baseline_rows"]["c3_outbox_status"]["pending"], 17432)

    def test_missing_execute_flag_is_blocked_for_execute_request_validation(self) -> None:
        with self.assertRaisesRegex(OfficialDailyExecuteBlocked, "--execute"):
            validate_execute_request(execute_requested=False, user_confirmed=True)

    def test_missing_user_confirmed_flag_is_blocked(self) -> None:
        with self.assertRaisesRegex(OfficialDailyExecuteBlocked, "--user-confirmed"):
            validate_execute_request(execute_requested=True, user_confirmed=False)

    def test_existing_source_version_blocks_preflight(self) -> None:
        baseline = base_baseline()
        baseline["target_source_version_conflicts"] = {"stock": 1, "index": 0, "board": 0}

        report = build_execute_preflight_report(
            dry_run_report=base_dry_run_report(),
            baseline=baseline,
            execute_requested=False,
            user_confirmed=False,
            rollback_sql_path=DEFAULT_ROLLBACK_SQL_PATH,
        )

        self.assertEqual(report["result"], "PREFLIGHT_BLOCKED")
        self.assertIn("existing_source_version", report["blockers"])

    def test_existing_batch_id_blocks_preflight(self) -> None:
        baseline = base_baseline()
        baseline["common_ingest_batch_exists"] = True

        report = build_execute_preflight_report(
            dry_run_report=base_dry_run_report(),
            baseline=baseline,
            execute_requested=False,
            user_confirmed=False,
            rollback_sql_path=DEFAULT_ROLLBACK_SQL_PATH,
        )

        self.assertEqual(report["result"], "PREFLIGHT_BLOCKED")
        self.assertIn("existing_batch_id", report["blockers"])

    def test_existing_active_source_version_blocks_preflight(self) -> None:
        baseline = base_baseline()
        baseline["active_source_versions_for_trade_date"] = [{"data_domain": "stock", "data_type": "stock_daily"}]

        report = build_execute_preflight_report(
            dry_run_report=base_dry_run_report(),
            baseline=baseline,
            execute_requested=False,
            user_confirmed=False,
            rollback_sql_path=DEFAULT_ROLLBACK_SQL_PATH,
        )

        self.assertEqual(report["result"], "PREFLIGHT_BLOCKED")
        self.assertIn("existing_active_source_version", report["blockers"])

    def test_eod_snapshot_rows_or_c3_outbox_drift_blocks_preflight(self) -> None:
        baseline = base_baseline()
        baseline["eod_snapshot_rows"] = {"stock": 1, "index": 0, "board": 0, "total": 1}
        baseline["c3_outbox_status"] = {"pending": 100, "delivered": 1, "delivering": 0, "total": 101}

        report = build_execute_preflight_report(
            dry_run_report=base_dry_run_report(),
            baseline=baseline,
            execute_requested=False,
            user_confirmed=False,
            rollback_sql_path=DEFAULT_ROLLBACK_SQL_PATH,
        )

        self.assertEqual(report["result"], "PREFLIGHT_BLOCKED")
        self.assertIn("eod_snapshot_rows_not_zero", report["blockers"])
        self.assertIn("c3_outbox_pending_drift", report["blockers"])

    def test_allowed_write_scope_and_side_effect_contract(self) -> None:
        report = build_execute_preflight_report(
            dry_run_report=base_dry_run_report(),
            baseline=base_baseline(),
            execute_requested=False,
            user_confirmed=False,
            rollback_sql_path=DEFAULT_ROLLBACK_SQL_PATH,
        )

        self.assertEqual(
            ALLOWED_EXECUTE_WRITE_TABLES,
            (
                "common_ingest_batch",
                "common_quality_gate_result",
                "common_active_source_version",
                "stock_daily_bar_fact",
                "index_daily_bar_fact",
                "board_daily_bar_fact",
            ),
        )
        self.assertEqual(report["expected_future_writes"]["allowed_tables"], list(ALLOWED_EXECUTE_WRITE_TABLES))
        self.assertIn("common_event_outbox", FORBIDDEN_WRITE_TABLES)
        self.assertIn("common_event_inbox", FORBIDDEN_WRITE_TABLES)
        self.assertIn("common_event_consumer_checkpoint", FORBIDDEN_WRITE_TABLES)
        self.assertIn("stock_eod_snapshot", FORBIDDEN_WRITE_TABLES)
        self.assertFalse(report["side_effects"]["will_call_external_sources"])
        self.assertFalse(report["side_effects"]["writes_postgres"])
        self.assertFalse(report["side_effects"]["writes_parquet"])
        self.assertFalse(report["side_effects"]["writes_outbox"])
        self.assertFalse(report["side_effects"]["worker_started"])
        self.assertFalse(report["side_effects"]["enters_n3_n4_n5_n6"])

    def test_rollback_sql_path_is_integrated_and_exists(self) -> None:
        report = build_execute_preflight_report(
            dry_run_report=base_dry_run_report(),
            baseline=base_baseline(),
            execute_requested=False,
            user_confirmed=False,
            rollback_sql_path=DEFAULT_ROLLBACK_SQL_PATH,
        )

        self.assertTrue((PROJECT_ROOT / report["rollback"]["path"]).exists())
        self.assertEqual(report["rollback"]["batch_id"], CONTRACT_BATCH_ID)
        self.assertEqual(report["rollback"]["source_versions"], dict(SOURCE_VERSIONS))

    def test_execute_cli_with_missing_user_confirmed_is_blocked(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--execute", "--no-write-report"],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--user-confirmed", result.stderr)

    def test_preflight_report_json_is_serializable(self) -> None:
        report = build_execute_preflight_report(
            dry_run_report=base_dry_run_report(),
            baseline=base_baseline(),
            execute_requested=False,
            user_confirmed=False,
            rollback_sql_path=DEFAULT_ROLLBACK_SQL_PATH,
        )

        encoded = json.dumps(report, ensure_ascii=False)
        self.assertIn("PREFLIGHT_PASS", encoded)
        self.assertIn("official_daily_ingest_20260525_v1", encoded)

    def test_source_fetch_disabled_blocks_execute(self) -> None:
        with self.assertRaisesRegex(OfficialDailyExecuteBlocked, "source_fetch_enabled"):
            fetch_official_daily_sources(
                adapter=FakeOfficialDailyAdapter(valid_source_bundle()),
                for_trade_date="20260525",
                expected_scope=expected_scope(),
                source_fetch_enabled=False,
            )

    def test_mocked_source_fetch_returns_expected_rows(self) -> None:
        bundle = fetch_official_daily_sources(
            adapter=FakeOfficialDailyAdapter(valid_source_bundle()),
            for_trade_date="20260525",
            expected_scope=expected_scope(),
            source_fetch_enabled=True,
        )

        self.assertEqual(bundle["row_counts"], {"stock": 2, "index": 9, "board": 2, "total": 13})
        self.assertEqual(bundle["routes"]["stock"]["primary"], "Tushare daily + adj_factor proof")
        self.assertEqual(bundle["routes"]["index"]["primary"], "TDX/Mootdx")
        self.assertEqual(bundle["routes"]["board"]["primary"], "TDX/Mootdx industry board daily")

    def test_missing_expected_object_blocks_commit(self) -> None:
        scope = expected_scope()
        bundle = valid_source_bundle(scope)
        bundle["stock"] = bundle["stock"][:1]

        validation = validate_source_bundle(bundle=bundle, expected_scope=scope, for_trade_date="20260525")

        self.assertGreater(validation["p0_count"], 0)
        self.assertIn("missing_expected_stock", validation["blockers"])

    def test_duplicate_identity_blocks_commit(self) -> None:
        scope = expected_scope()
        bundle = valid_source_bundle(scope)
        bundle["index"].append(dict(bundle["index"][0]))

        validation = validate_source_bundle(bundle=bundle, expected_scope=scope, for_trade_date="20260525")

        self.assertGreater(validation["p0_count"], 0)
        self.assertIn("duplicate_identity_key", validation["blockers"])

    def test_same_code_contamination_blocks_commit(self) -> None:
        scope = expected_scope()
        bundle = valid_source_bundle(scope)
        bundle["stock"][0]["identity_key"] = "index:SH:600000"

        validation = validate_source_bundle(bundle=bundle, expected_scope=scope, for_trade_date="20260525")

        self.assertGreater(validation["p0_count"], 0)
        self.assertIn("same_code_contamination", validation["blockers"])

    def test_stock_adj_factor_proof_missing_blocks_commit(self) -> None:
        scope = expected_scope()
        bundle = valid_source_bundle(scope)
        bundle["stock"][0]["official_daily_proof"] = False
        bundle["stock"][0]["adj_factor"] = None

        validation = validate_source_bundle(bundle=bundle, expected_scope=scope, for_trade_date="20260525")

        self.assertGreater(validation["p0_count"], 0)
        self.assertIn("stock_official_daily_proof_missing", validation["blockers"])

    def test_commit_preconditions_block_existing_batch_source_version_and_active(self) -> None:
        baseline = base_baseline()
        baseline["common_ingest_batch_exists"] = True
        baseline["target_source_version_conflicts"] = {"stock": 0, "index": 1, "board": 0}
        baseline["active_source_versions_for_trade_date"] = [{"data_domain": "index", "data_type": "index_daily"}]

        validation = validate_source_bundle(
            bundle=valid_source_bundle(),
            expected_scope=expected_scope(),
            for_trade_date="20260525",
        )

        with self.assertRaisesRegex(OfficialDailyExecuteBlocked, "existing_batch_id"):
            validate_commit_preconditions(
                dry_run_report=base_dry_run_report(),
                baseline=baseline,
                validation_report=validation,
                source_fetch_enabled=True,
                postgres_commit_enabled=True,
            )

    def test_commit_writes_only_allowed_tables(self) -> None:
        scope = expected_scope()
        bundle = valid_source_bundle(scope)
        validation = validate_source_bundle(bundle=bundle, expected_scope=scope, for_trade_date="20260525")
        plan = build_commit_plan(
            bundle=bundle,
            validation_report=validation,
            baseline=base_baseline(),
            for_trade_date="20260525",
        )
        conn = RecordingConnection()

        result = execute_commit_transaction(
            conn,
            commit_plan=plan,
            execute_requested=True,
            user_confirmed=True,
            source_fetch_enabled=True,
            postgres_commit_enabled=True,
        )

        self.assertTrue(result["committed"])
        self.assertTrue(conn.committed)
        joined_sql = "\n".join(conn.cursor_obj.statements)
        for table in result["written_tables"]:
            self.assertIn(table, ALLOWED_EXECUTE_WRITE_TABLES)
        for forbidden in ("common_event_outbox", "stock_eod_snapshot", "stock_minute_bar_1m"):
            self.assertNotIn(forbidden, joined_sql)

    def test_rollback_sql_token_guard(self) -> None:
        rollback_sql = (PROJECT_ROOT / DEFAULT_ROLLBACK_SQL_PATH).read_text()

        self.assertIn(CONTRACT_BATCH_ID, rollback_sql)
        for source_version in SOURCE_VERSIONS.values():
            self.assertIn(source_version, rollback_sql)
        self.assertNotIn("common_event_outbox", rollback_sql)
        self.assertNotIn("stock_eod_snapshot", rollback_sql)
        self.assertNotIn("condition_", rollback_sql)

    def test_final_preflight_marks_fetch_and_commit_implemented_without_side_effects(self) -> None:
        report = build_execute_preflight_report(
            dry_run_report=base_dry_run_report(),
            baseline=base_baseline(),
            execute_requested=False,
            user_confirmed=False,
            rollback_sql_path=DEFAULT_ROLLBACK_SQL_PATH,
        )

        self.assertTrue(report["source_fetch"]["implemented"])
        self.assertTrue(report["postgres_commit"]["implemented"])
        self.assertTrue(report["final_gate_required"])
        self.assertFalse(report["execute_authorized"])
        self.assertFalse(report["expected_future_writes"]["writes_parquet"])
        self.assertFalse(report["side_effects"]["will_call_external_sources"])
        self.assertFalse(report["side_effects"]["writes_postgres"])
        self.assertFalse(report["side_effects"]["writes_outbox"])
        self.assertFalse(report["side_effects"]["writes_inbox_or_checkpoint"])
        self.assertFalse(report["side_effects"]["enters_n3_n4_n5_n6"])

    def test_cli_all_four_flags_reaches_execute_path_with_mocked_fetch_and_commit(self) -> None:
        runner = load_runner_module()
        harness = RunnerHarness()
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = runner.main(
                [
                    "--trade-date",
                    "20260525",
                    "--execute",
                    "--user-confirmed",
                    "--source-fetch-enabled",
                    "--postgres-commit-enabled",
                    "--no-write-report",
                ],
                dependencies=harness.deps(),
            )

        self.assertEqual(result, 0, stderr.getvalue())
        self.assertIn("execute_commit_transaction", harness.calls)
        self.assertTrue(harness.conn.committed)
        self.assertFalse(harness.real_source_fetch_called)
        self.assertNotIn("final execute gate is not open", stderr.getvalue())
        joined_sql = "\n".join(harness.conn.cursor_obj.statements)
        for forbidden in ("common_event_outbox", "common_event_inbox", "common_event_consumer_checkpoint", "stock_eod_snapshot"):
            self.assertNotIn(forbidden, joined_sql)

    def test_cli_missing_any_final_gate_flag_blocks_before_source_fetch(self) -> None:
        runner = load_runner_module()
        flag_sets = [
            ["--execute", "--user-confirmed", "--postgres-commit-enabled"],
            ["--execute", "--user-confirmed", "--source-fetch-enabled"],
            ["--execute", "--source-fetch-enabled", "--postgres-commit-enabled"],
        ]

        for flags in flag_sets:
            with self.subTest(flags=flags):
                harness = RunnerHarness()
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    result = runner.main(["--trade-date", "20260525", *flags, "--no-write-report"], dependencies=harness.deps())

                self.assertNotEqual(result, 0)
                self.assertNotIn("fetch_official_daily_sources", harness.calls)
                self.assertNotIn("execute_commit_transaction", harness.calls)

    def test_cli_source_validation_p0_blocks_before_commit(self) -> None:
        runner = load_runner_module()
        bundle = valid_source_bundle()
        bundle["stock"] = bundle["stock"][:1]
        harness = RunnerHarness(bundle=bundle)

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = runner.main(
                [
                    "--trade-date",
                    "20260525",
                    "--execute",
                    "--user-confirmed",
                    "--source-fetch-enabled",
                    "--postgres-commit-enabled",
                    "--no-write-report",
                ],
                dependencies=harness.deps(),
            )

        self.assertNotEqual(result, 0)
        self.assertIn("validate_source_bundle", harness.calls)
        self.assertIn("validate_commit_preconditions", harness.calls)
        self.assertNotIn("execute_commit_transaction", harness.calls)
        self.assertFalse(harness.conn.committed)

    def test_cli_baseline_conflict_blocks_before_source_fetch_and_commit(self) -> None:
        runner = load_runner_module()
        baseline = base_baseline()
        baseline["common_ingest_batch_exists"] = True
        harness = RunnerHarness(baseline=baseline)

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = runner.main(
                [
                    "--trade-date",
                    "20260525",
                    "--execute",
                    "--user-confirmed",
                    "--source-fetch-enabled",
                    "--postgres-commit-enabled",
                    "--no-write-report",
                ],
                dependencies=harness.deps(),
            )

        self.assertNotEqual(result, 0)
        self.assertNotIn("fetch_official_daily_sources", harness.calls)
        self.assertNotIn("execute_commit_transaction", harness.calls)


if __name__ == "__main__":
    unittest.main()
