import contextlib
import importlib.util
import io
import unittest
from pathlib import Path

from ashare_v3.ingestion.condition_source_activation_20260601_execute import (
    ALLOWED_FUTURE_WRITE_TABLES,
    BATCH_ID,
    EXPECTED_REFERENCE_ROWS,
    OFFICIAL_NO_TRADE_IDENTITIES,
    SOURCE_VERSIONS,
    TRADE_DATE,
    ConditionSourceActivation20260601Blocked,
    build_commit_plan,
    build_execute_preflight_report,
    execute_commit_transaction,
    official_no_trade_manifest,
    sample_pass_snapshot,
    validate_commit_preconditions,
    validate_execute_request,
    validate_source_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_condition_source_activation_20260601_once.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("n1_condition_source_activation_20260601_runner", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def stock_daily_basic_row(index: int) -> dict:
    code = f"{500000 + index:06d}"
    return {
        "stock_identity_key": f"stock:SH:{code}",
        "trade_date": TRADE_DATE,
        "ts_code": f"{code}.SH",
        "code": code,
        "exchange": "SH",
        "close": 10.0,
        "turnover_rate": 1.0,
        "turnover_rate_f": 1.0,
        "volume_ratio": 1.0,
        "pe": 12.0,
        "pe_ttm": 11.0,
        "pb": 1.2,
        "ps": 2.1,
        "ps_ttm": 2.0,
        "dv_ratio": None,
        "dv_ttm": None,
        "total_share": 100000.0,
        "float_share": 80000.0,
        "free_share": 60000.0,
        "total_mv": 1200000.0,
        "circ_mv": 900000.0,
        "source": "mock.tushare.daily_basic",
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSIONS["stock_daily_basic"],
        "raw_payload": {"mock": True, "i": index},
    }


def stock_financial_row(index: int) -> dict:
    code = f"{500000 + index:06d}"
    return {
        "stock_identity_key": f"stock:SH:{code}",
        "asof_date": TRADE_DATE,
        "source_trade_date": TRADE_DATE,
        "announcement_date": "20260430",
        "report_period": "20260331",
        "ts_code": f"{code}.SH",
        "code": code,
        "exchange": "SH",
        "roe": 5.0,
        "revenue_yoy": 3.0,
        "profit_yoy": 2.0,
        "total_revenue": 1000.0,
        "net_profit": 100.0,
        "net_assets": 2000.0,
        "eps": 0.1,
        "bps": 2.0,
        "pe_core": 11.0,
        "total_mv": 1200000.0,
        "circ_mv": 900000.0,
        "score": 1,
        "warning": None,
        "quality_status": "passed",
        "source": "mock.financial_asof",
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSIONS["stock_financial"],
        "raw_payload": {"mock": True, "i": index},
    }


def index_membership_row(index: int) -> dict:
    code = f"{index % 90 + 1:06d}"
    stock_code = f"{500000 + index:06d}"
    return {
        "trade_date": TRADE_DATE,
        "index_identity_key": f"index:SH:{code}",
        "stock_identity_key": f"stock:SH:{stock_code}",
        "index_code": code,
        "index_name": f"index-{code}",
        "stock_code": stock_code,
        "stock_name": f"stock-{stock_code}",
        "source": "mock.tdx.index",
        "source_file": "指数板块.txt",
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSIONS["index_membership"],
        "raw_payload": {"mock": True, "i": index},
    }


def board_membership_row(index: int) -> dict:
    code = f"881{index % 428 + 1:03d}"
    stock_code = f"{500000 + index:06d}"
    return {
        "trade_date": TRADE_DATE,
        "board_identity_key": f"board:TDX:{code}",
        "stock_identity_key": f"stock:SH:{stock_code}",
        "board_code": code,
        "board_name": f"board-{code}",
        "board_type": "tdx_industry",
        "stock_code": stock_code,
        "stock_name": f"stock-{stock_code}",
        "source": "mock.tdx.board",
        "source_file": "行业板块.txt",
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSIONS["board_membership"],
        "raw_payload": {"mock": True, "i": index},
    }


def valid_source_bundle() -> dict:
    return {
        "stock_daily_basic": [stock_daily_basic_row(i) for i in range(EXPECTED_REFERENCE_ROWS["stock_daily_basic"])],
        "stock_financial": [stock_financial_row(i) for i in range(EXPECTED_REFERENCE_ROWS["stock_financial"])],
        "index_membership": [index_membership_row(i) for i in range(EXPECTED_REFERENCE_ROWS["index_membership"])],
        "board_membership": [board_membership_row(i) for i in range(EXPECTED_REFERENCE_ROWS["board_membership"])],
        "manifests": {
            "condition_source_gap_manifest": official_no_trade_manifest(),
            "official_no_trade_manifest": official_no_trade_manifest(),
            "stale_identity_manifest": [
                {
                    "identity_key": "stock:SZ:300114",
                    "superseded_by_identity_key": "stock:SZ:302132",
                    "severity": "P1",
                }
            ],
            "board_unmapped_raw_count": 12,
            "board_unmapped_unique_identity_count": 8,
        },
    }


class FakeSourceBuilder:
    def __init__(self, bundle: dict | None = None) -> None:
        self.bundle = bundle or valid_source_bundle()
        self.called = False

    def build_source_bundle(self, *, dsn: str, trade_date: str, snapshot: dict) -> dict:
        self.called = True
        return self.bundle


class RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.execute_calls: list[tuple[str, object]] = []
        self.executemany_calls: list[tuple[str, int]] = []

    def execute(self, sql: str, params=None) -> None:
        normalized = " ".join(sql.split())
        self.statements.append(normalized)
        self.execute_calls.append((normalized, params))

    def executemany(self, sql: str, params_seq) -> None:
        rows = list(params_seq)
        self.statements.append(" ".join(sql.split()))
        self.executemany_calls.append((" ".join(sql.split()), len(rows)))


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
    def __init__(self, *, snapshot: dict | None = None, bundle: dict | None = None) -> None:
        self.snapshot = snapshot or sample_pass_snapshot()
        self.builder = FakeSourceBuilder(bundle)
        self.conn = RecordingConnection()
        self.calls: list[str] = []

    def deps(self) -> dict:
        return {
            "build_snapshot_from_db": self.build_snapshot_from_db,
            "source_builder_factory": self.source_builder_factory,
            "connect": self.connect,
            "write_dry_run_files": self.write_dry_run_files,
            "write_preflight_files": self.write_preflight_files,
            "write_contract_files": self.write_contract_files,
        }

    def build_snapshot_from_db(self, **kwargs) -> dict:
        self.calls.append("build_snapshot_from_db")
        return self.snapshot

    def source_builder_factory(self, **kwargs) -> FakeSourceBuilder:
        self.calls.append("source_builder_factory")
        return self.builder

    def connect(self, dsn: str) -> RecordingConnection:
        self.calls.append("connect")
        return self.conn

    def write_preflight_files(self, *args, **kwargs) -> None:
        self.calls.append("write_preflight_files")

    def write_contract_files(self, *args, **kwargs) -> None:
        self.calls.append("write_contract_files")

    def write_dry_run_files(self, *args, **kwargs) -> None:
        self.calls.append("write_dry_run_files")


class ConditionSourceActivation20260601ExecuteTests(unittest.TestCase):
    def test_missing_required_flags_block(self) -> None:
        cases = [
            (False, True, True, "--execute"),
            (True, False, True, "--user-confirmed"),
            (True, True, False, "--postgres-commit-enabled"),
        ]
        for execute, confirmed, commit, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ConditionSourceActivation20260601Blocked, message):
                    validate_execute_request(
                        execute_requested=execute,
                        user_confirmed=confirmed,
                        postgres_commit_enabled=commit,
                    )

    def test_preflight_ready_for_final_gate(self) -> None:
        report = build_execute_preflight_report(
            sample_pass_snapshot(),
            execute_requested=False,
            user_confirmed=False,
            postgres_commit_enabled=False,
        )

        self.assertEqual(report["result"], "PREFLIGHT_PASS")
        self.assertEqual(report["runner_readiness"], "ready_for_final_gate")
        self.assertTrue(report["final_execute_gate_allowed"])
        self.assertTrue(report["execute_runner_implemented"])
        self.assertEqual(report["quality"], {"p0_count": 0, "p1_count": 2, "p2_count": 1})
        self.assertIn("20260601", report["execute_command_template"])

    def test_success_commit_plan_has_expected_counts_and_manifest_quality(self) -> None:
        bundle = valid_source_bundle()
        validation = validate_source_bundle(bundle=bundle, snapshot=sample_pass_snapshot())
        plan = build_commit_plan(bundle=bundle, validation_report=validation, baseline=sample_pass_snapshot())

        self.assertEqual(validation["result"], "VALIDATION_PASS")
        self.assertEqual(validation["quality"], {"p0_count": 0, "p1_count": 2, "p2_count": 1})
        self.assertEqual(
            plan["row_counts"],
            {
                "stock_daily_basic": 5508,
                "stock_financial": 5508,
                "index_membership": 12841,
                "board_membership": 56960,
                "total": 80817,
            },
        )
        self.assertEqual(len(plan["manifests"]["official_no_trade_manifest"]), 17)
        self.assertEqual(len(plan["manifests"]["stale_identity_manifest"]), 1)
        self.assertEqual(plan["active_source_version_rows"][0]["activated_by"], "n1_condition_source_activation_20260601_execute_runner")

    def test_20260601_no_trade_manifest_matches_official_daily_post_review(self) -> None:
        manifest_keys = {row["identity_key"] for row in official_no_trade_manifest()}

        self.assertIn("stock:SH:603721", manifest_keys)
        self.assertIn("stock:SZ:001331", manifest_keys)
        self.assertIn("stock:SZ:300685", manifest_keys)
        self.assertNotIn("stock:SZ:000691", manifest_keys)
        self.assertNotIn("stock:SZ:300561", manifest_keys)
        self.assertEqual(len(manifest_keys), 17)

    def test_commit_writes_allowed_tables_only_and_uses_20260601_source(self) -> None:
        bundle = valid_source_bundle()
        validation = validate_source_bundle(bundle=bundle, snapshot=sample_pass_snapshot())
        plan = build_commit_plan(bundle=bundle, validation_report=validation, baseline=sample_pass_snapshot())
        conn = RecordingConnection()

        result = execute_commit_transaction(
            conn,
            commit_plan=plan,
            execute_requested=True,
            user_confirmed=True,
            postgres_commit_enabled=True,
        )

        self.assertTrue(result["committed"])
        self.assertTrue(conn.committed)
        self.assertEqual(tuple(result["written_tables"]), ALLOWED_FUTURE_WRITE_TABLES)
        joined = "\n".join(conn.cursor_obj.statements).lower()
        self.assertIn("n1.condition_source_activation.20260601.v1", joined)
        self.assertNotIn("n1.condition_source_activation.20260529.v1", joined)
        status_updates = [
            params
            for sql, params in conn.cursor_obj.execute_calls
            if sql.startswith("UPDATE common_ingest_batch SET status = 'passed'")
        ]
        self.assertEqual(status_updates, [(BATCH_ID,)])
        for forbidden in (
            "stock_daily_bar_fact",
            "index_daily_bar_fact",
            "board_daily_bar_fact",
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "parquet",
        ):
            self.assertNotIn(forbidden, joined)

    def test_commit_preconditions_block_p0_validation(self) -> None:
        validation = {"p0_count": 1, "blockers": ["stock_daily_basic_row_count_mismatch"]}
        with self.assertRaisesRegex(ConditionSourceActivation20260601Blocked, "stock_daily_basic_row_count_mismatch"):
            validate_commit_preconditions(
                snapshot=sample_pass_snapshot(),
                validation_report=validation,
                postgres_commit_enabled=True,
            )

    def test_rollback_sql_exists(self) -> None:
        self.assertTrue((PROJECT_ROOT / "sql" / "N1_condition_source_20260601_activation_rollback.sql").exists())

    def test_cli_all_flags_reaches_execute_path_with_mocked_builder_and_commit(self) -> None:
        runner = load_runner_module()
        harness = RunnerHarness()
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = runner.main(
                ["--execute", "--user-confirmed", "--postgres-commit-enabled", "--no-write-report"],
                dependencies=harness.deps(),
            )

        self.assertEqual(result, 0, stderr.getvalue())
        self.assertTrue(harness.builder.called)
        self.assertTrue(harness.conn.committed)
        self.assertIn("connect", harness.calls)

    def test_cli_missing_flag_blocks_before_source_build(self) -> None:
        runner = load_runner_module()
        harness = RunnerHarness()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = runner.main(
                ["--execute", "--user-confirmed", "--no-write-report"],
                dependencies=harness.deps(),
            )

        self.assertNotEqual(result, 0)
        self.assertFalse(harness.builder.called)
        self.assertFalse(harness.conn.committed)


if __name__ == "__main__":
    unittest.main()
