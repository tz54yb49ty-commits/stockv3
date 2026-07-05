import contextlib
import importlib.util
import io
import unittest
from pathlib import Path

from ashare_v3.ingestion.stock_identity_refresh_20260605_920211_execute import (
    ACTIVE_SCOPE_KEY,
    ALLOWED_FUTURE_WRITE_TABLES,
    BATCH_ID,
    EXPECTED_IDENTITY_KEY,
    EXPECTED_TS_CODE,
    SOURCE_VERSION,
    TRADE_DATE,
    StockIdentityRefresh20260605920211Blocked,
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
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_stock_identity_refresh_20260605_920211_once.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("n1_stock_identity_refresh_20260605_920211_runner", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def source_evidence() -> dict:
    return {
        "stock_basic": [
            {
                "ts_code": "920211.BJ",
                "symbol": "920211",
                "name": "测试股",
                "area": "北京",
                "industry": "软件服务",
                "market": "北交所",
                "list_date": TRADE_DATE,
                "delist_date": None,
                "list_status": "L",
                "exchange": "BSE",
            }
        ],
        "daily": [
            {
                "ts_code": "920211.BJ",
                "trade_date": TRADE_DATE,
                "open": 10.0,
                "high": 12.0,
                "low": 9.5,
                "close": 11.0,
                "vol": 100000.0,
                "amount": 200000.0,
            }
        ],
        "adj_factor": [{"ts_code": "920211.BJ", "trade_date": TRADE_DATE, "adj_factor": 1.0}],
        "suspend_d": [],
        "bak_daily": [
            {
                "ts_code": "920211.BJ",
                "trade_date": TRADE_DATE,
                "name": "N测试",
                "open": 10.0,
                "high": 12.0,
                "low": 9.5,
                "close": 11.0,
                "vol": 100000.0,
                "amount": 200000.0,
            }
        ],
    }


class FakeSourceAdapter:
    def __init__(self, evidence: dict | None = None) -> None:
        self.evidence = evidence or source_evidence()
        self.called = False

    def fetch_source_evidence(self, *, trade_date: str, ts_code: str) -> dict:
        self.called = True
        self.trade_date = trade_date
        self.ts_code = ts_code
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


class StockIdentityRefresh20260605920211ExecuteTests(unittest.TestCase):
    def test_missing_required_flags_block_before_source_fetch(self) -> None:
        cases = [
            (False, True, "--execute"),
            (True, False, "--user-confirmed"),
        ]
        for execute, confirmed, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(StockIdentityRefresh20260605920211Blocked, message):
                    validate_execute_request(execute_requested=execute, user_confirmed=confirmed)

    def test_build_target_identity_row_from_evidence(self) -> None:
        rows = build_target_identity_rows(source_evidence())

        self.assertEqual(1, len(rows))
        row = rows[0]
        self.assertEqual(EXPECTED_IDENTITY_KEY, row["stock_identity_key"])
        self.assertEqual(EXPECTED_TS_CODE, row["ts_code"])
        self.assertEqual("920211", row["code"])
        self.assertEqual("BJ", row["exchange"])
        self.assertEqual("测试股", row["name"])
        self.assertEqual("北京", row["area"])
        self.assertEqual("软件服务", row["industry"])
        self.assertEqual("北交所", row["market"])
        self.assertEqual(TRADE_DATE, row["listed_date"])
        self.assertEqual(SOURCE_VERSION, row["source_version"])
        self.assertIn("source_evidence", row["raw_payload"])

    def test_contract_preflight_and_commit_plan_use_20260605_scope(self) -> None:
        rows = build_target_identity_rows(source_evidence())
        report = validate_source_rows(rows)
        snapshot = sample_pass_snapshot()
        plan = build_commit_plan(rows=rows, validation_report=report, baseline=snapshot)
        contract = build_execute_contract(snapshot, source_report=validate_source_evidence(source_evidence()))
        preflight = build_execute_preflight_report(
            snapshot,
            source_report=validate_source_evidence(source_evidence()),
            execute_requested=False,
            user_confirmed=False,
        )

        self.assertEqual(BATCH_ID, plan["source_batch_id"])
        self.assertEqual(SOURCE_VERSION, plan["source_version"])
        self.assertEqual(ACTIVE_SCOPE_KEY, plan["active_source_version"]["scope_key"])
        self.assertIn("20260605", contract["stage"])
        self.assertIn("920211", contract["new_identity_rows"][0]["stock_identity_key"])
        self.assertEqual("PREFLIGHT_PASS", preflight["result"])
        self.assertIn("run_stock_identity_refresh_20260605_920211_once.py", preflight["execute_command_candidate"])

    def test_existing_conflicts_block_commit_preconditions(self) -> None:
        report = validate_source_rows(build_target_identity_rows(source_evidence()))
        snapshot = sample_pass_snapshot()
        snapshot["target_stock_identity_rows"] = 1
        with self.assertRaisesRegex(StockIdentityRefresh20260605920211Blocked, "existing target stock_identity"):
            validate_commit_preconditions(snapshot=snapshot, validation_report=report)

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
        for forbidden in ("stock_daily_bar_fact", "common_event_outbox", "common_event_inbox"):
            self.assertNotIn(f"INSERT INTO {forbidden}", statements)

    def test_runner_preflight_does_not_connect_or_write_without_execute(self) -> None:
        runner = load_runner_module()
        harness = RunnerHarness()

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = runner.main(["--trade-date", TRADE_DATE, "--no-write-report"], dependencies=harness.deps())

        self.assertEqual(0, exit_code)
        self.assertIn("source_adapter_factory", harness.calls)
        self.assertNotIn("connect", harness.calls)
        self.assertFalse(harness.conn.committed)

    def test_runner_missing_user_confirmation_blocks_before_source_fetch(self) -> None:
        runner = load_runner_module()
        harness = RunnerHarness()

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = runner.main(["--trade-date", TRADE_DATE, "--execute", "--no-write-report"], dependencies=harness.deps())

        self.assertEqual(2, exit_code)
        self.assertIn("missing --user-confirmed", stderr.getvalue())
        self.assertEqual([], harness.calls)
        self.assertFalse(harness.adapter.called)


if __name__ == "__main__":
    unittest.main()
