import contextlib
import importlib.util
import io
import unittest
from pathlib import Path

from ashare_v3.ingestion.stock_identity_refresh_20260529_execute import (
    ACTIVE_SCOPE_KEY,
    ALLOWED_FUTURE_WRITE_TABLES,
    BATCH_ID,
    EXPECTED_IDENTITY_KEY,
    EXPECTED_TS_CODE,
    SOURCE_VERSION,
    TRADE_DATE,
    StockIdentityRefresh20260529Blocked,
    build_commit_plan,
    build_execute_contract,
    build_execute_preflight_report,
    build_target_identity_rows,
    execute_commit_transaction,
    sample_pass_snapshot,
    validate_commit_preconditions,
    validate_execute_request,
    validate_source_evidence,
    validate_source_rows,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_stock_identity_refresh_20260529_once.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("n1_stock_identity_refresh_20260529_runner", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def source_evidence() -> dict:
    return {
        "stock_basic": [
            {
                "ts_code": "920218.BJ",
                "symbol": "920218",
                "name": "\u65b0\u5929\u529b",
                "area": "\u6d59\u6c5f",
                "industry": "\u5851\u6599",
                "market": "\u5317\u4ea4\u6240",
                "list_date": TRADE_DATE,
                "delist_date": None,
                "list_status": "L",
                "exchange": "BSE",
            }
        ],
        "daily": [
            {
                "ts_code": "920218.BJ",
                "trade_date": TRADE_DATE,
                "open": 44.97,
                "high": 58.18,
                "low": 38.11,
                "close": 45.2,
                "vol": 202087.92,
                "amount": 893068.69949,
            }
        ],
        "adj_factor": [{"ts_code": "920218.BJ", "trade_date": TRADE_DATE, "adj_factor": 1.0}],
        "suspend_d": [],
        "bak_daily": [
            {
                "ts_code": "920218.BJ",
                "trade_date": TRADE_DATE,
                "name": "N\u65b0\u5929\u529b",
                "open": 44.97,
                "high": 58.18,
                "low": 38.11,
                "close": 45.2,
                "vol": 202087.92,
                "amount": 893068.69949,
            }
        ],
    }


class FakeSourceAdapter:
    def __init__(self, evidence: dict | None = None) -> None:
        self.evidence = evidence or source_evidence()
        self.called = False

    def fetch_source_evidence(self, *, trade_date: str, ts_code: str) -> dict:
        self.called = True
        return self.evidence


class RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.executemany_calls: list[tuple[str, int]] = []

    def execute(self, sql: str, params=None) -> None:
        self.statements.append(" ".join(sql.split()))

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
    def __init__(self, *, snapshot: dict | None = None, evidence: dict | None = None) -> None:
        self.snapshot = snapshot or sample_pass_snapshot()
        self.adapter = FakeSourceAdapter(evidence)
        self.conn = RecordingConnection()
        self.calls: list[str] = []

    def deps(self) -> dict:
        return {
            "build_snapshot_from_db": self.build_snapshot_from_db,
            "source_adapter_factory": self.source_adapter_factory,
            "connect": self.connect,
            "write_preflight_files": self.write_preflight_files,
            "write_contract_files": self.write_contract_files,
        }

    def build_snapshot_from_db(self, **kwargs) -> dict:
        self.calls.append("build_snapshot_from_db")
        return self.snapshot

    def source_adapter_factory(self, **kwargs) -> FakeSourceAdapter:
        self.calls.append("source_adapter_factory")
        return self.adapter

    def connect(self, dsn: str) -> RecordingConnection:
        self.calls.append("connect")
        return self.conn

    def write_preflight_files(self, *args, **kwargs) -> None:
        self.calls.append("write_preflight_files")

    def write_contract_files(self, *args, **kwargs) -> None:
        self.calls.append("write_contract_files")


class StockIdentityRefresh20260529ExecuteTests(unittest.TestCase):
    def test_missing_required_flags_block_before_source_fetch(self) -> None:
        cases = [
            (False, True, "--execute"),
            (True, False, "--user-confirmed"),
        ]
        for execute, confirmed, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(StockIdentityRefresh20260529Blocked, message):
                    validate_execute_request(execute_requested=execute, user_confirmed=confirmed)

    def test_validate_source_evidence_requires_all_tushare_proofs(self) -> None:
        evidence = source_evidence()
        report = validate_source_evidence(evidence)

        self.assertEqual(0, report["p0_count"])
        self.assertTrue(report["stock_basic_present"])
        self.assertTrue(report["daily_present"])
        self.assertTrue(report["adj_factor_present"])
        self.assertTrue(report["bak_daily_present"])
        self.assertFalse(report["suspend_d_present"])

        missing_daily = source_evidence()
        missing_daily["daily"] = []
        with self.assertRaisesRegex(StockIdentityRefresh20260529Blocked, "daily"):
            validate_source_evidence(missing_daily)

    def test_build_target_identity_row_from_evidence(self) -> None:
        rows = build_target_identity_rows(source_evidence())

        self.assertEqual(1, len(rows))
        row = rows[0]
        self.assertEqual(EXPECTED_IDENTITY_KEY, row["stock_identity_key"])
        self.assertEqual(EXPECTED_TS_CODE, row["ts_code"])
        self.assertEqual("920218", row["code"])
        self.assertEqual("BJ", row["exchange"])
        self.assertEqual("\u65b0\u5929\u529b", row["name"])
        self.assertEqual("\u6d59\u6c5f", row["area"])
        self.assertEqual("\u5851\u6599", row["industry"])
        self.assertEqual("\u5317\u4ea4\u6240", row["market"])
        self.assertEqual(TRADE_DATE, row["listed_date"])
        self.assertEqual(SOURCE_VERSION, row["source_version"])
        self.assertIn("source_evidence", row["raw_payload"])

    def test_existing_conflicts_block_commit_preconditions(self) -> None:
        report = validate_source_rows(build_target_identity_rows(source_evidence()))

        snapshot = sample_pass_snapshot()
        snapshot["target_stock_identity_rows"] = 1
        with self.assertRaisesRegex(StockIdentityRefresh20260529Blocked, "existing target stock_identity"):
            validate_commit_preconditions(snapshot=snapshot, validation_report=report)

        snapshot = sample_pass_snapshot()
        snapshot["batch_conflict_count"] = 1
        with self.assertRaisesRegex(StockIdentityRefresh20260529Blocked, "existing batch"):
            validate_commit_preconditions(snapshot=snapshot, validation_report=report)

        snapshot = sample_pass_snapshot()
        snapshot["existing_active_scope_key_count"] = 1
        with self.assertRaisesRegex(StockIdentityRefresh20260529Blocked, "existing active source_version"):
            validate_commit_preconditions(snapshot=snapshot, validation_report=report)

    def test_success_commit_plan_allowed_writes_only(self) -> None:
        rows = build_target_identity_rows(source_evidence())
        report = validate_source_rows(rows)
        plan = build_commit_plan(rows=rows, validation_report=report, baseline=sample_pass_snapshot())

        self.assertEqual(1, plan["row_counts"]["stock_identity"])
        self.assertEqual(ACTIVE_SCOPE_KEY, plan["active_source_version"]["scope_key"])
        self.assertEqual(tuple(plan["allowed_write_tables"]), ALLOWED_FUTURE_WRITE_TABLES)
        self.assertEqual("stock_identity_20260527_v1", plan["previous_source_version"])
        forbidden = {
            "stock_daily_bar_fact",
            "index_daily_bar_fact",
            "board_daily_bar_fact",
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
        }
        self.assertFalse(forbidden & set(plan["allowed_write_tables"]))

    def test_execute_commit_transaction_writes_only_allowed_tables(self) -> None:
        rows = build_target_identity_rows(source_evidence())
        report = validate_source_rows(rows)
        plan = build_commit_plan(rows=rows, validation_report=report, baseline=sample_pass_snapshot())
        conn = RecordingConnection()

        result = execute_commit_transaction(
            conn,
            commit_plan=plan,
            execute_requested=True,
            user_confirmed=True,
        )

        statements = " ".join(conn.cursor_obj.statements)
        self.assertTrue(conn.committed)
        self.assertEqual(1, result["row_counts"]["stock_identity"])
        for table_name in ALLOWED_FUTURE_WRITE_TABLES:
            self.assertIn(table_name, statements)
        self.assertNotIn("stock_daily_bar_fact", statements)
        self.assertNotIn("index_daily_bar_fact", statements)
        self.assertNotIn("board_daily_bar_fact", statements)
        self.assertNotIn("common_event_outbox", statements)
        self.assertNotIn("common_event_inbox", statements)

    def test_preflight_and_contract_ready_for_final_gate(self) -> None:
        snapshot = sample_pass_snapshot()
        preflight = build_execute_preflight_report(
            snapshot,
            source_report=validate_source_evidence(source_evidence()),
            execute_requested=False,
            user_confirmed=False,
        )
        contract = build_execute_contract(snapshot, source_report=validate_source_evidence(source_evidence()))

        self.assertEqual("PREFLIGHT_PASS", preflight["result"])
        self.assertEqual("ready_for_final_gate", preflight["runner_readiness"])
        self.assertTrue(preflight["final_execute_gate_allowed"])
        self.assertFalse(preflight["execute_authorized"])
        self.assertEqual("ready_for_final_gate", contract["runner_readiness"])

    def test_runner_reaches_execute_path_with_all_flags(self) -> None:
        module = load_runner_module()
        harness = RunnerHarness()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = module.main(
                [
                    "--trade-date",
                    TRADE_DATE,
                    "--execute",
                    "--user-confirmed",
                    "--no-write-report",
                ],
                dependencies=harness.deps(),
            )
        self.assertEqual(0, exit_code)
        self.assertIn("source_adapter_factory", harness.calls)
        self.assertIn("connect", harness.calls)
        self.assertTrue(harness.adapter.called)
        self.assertTrue(harness.conn.committed)
        self.assertIn("EXECUTE_PASS", stdout.getvalue())

    def test_runner_missing_flag_blocks_before_source_fetch(self) -> None:
        module = load_runner_module()
        harness = RunnerHarness()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = module.main(
                ["--trade-date", TRADE_DATE, "--execute", "--no-write-report"],
                dependencies=harness.deps(),
            )
        self.assertEqual(2, exit_code)
        self.assertNotIn("source_adapter_factory", harness.calls)
        self.assertFalse(harness.adapter.called)
        self.assertIn("--user-confirmed", stderr.getvalue())

    def test_rollback_sql_exists(self) -> None:
        self.assertTrue((PROJECT_ROOT / "sql" / "N1_stock_identity_refresh_20260529_rollback.sql").exists())


if __name__ == "__main__":
    unittest.main()
