import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

from ashare_v3.ingestion.stock_identity_920206_repair_20260608 import (
    ACTIVE_SCOPE_KEY,
    ALLOWED_FUTURE_WRITE_TABLES,
    BATCH_ID,
    EXPECTED_IDENTITY_KEY,
    EXPECTED_TS_CODE,
    IMPLEMENTATION_REPORT_JSON,
    SOURCE_VERSION,
    TRADE_DATE,
    StockIdentity920206Repair20260608Blocked,
    build_commit_plan,
    build_implementation_report,
    build_target_identity_rows,
    execute_commit_transaction,
    sample_pass_snapshot,
    validate_commit_preconditions,
    validate_execute_request,
    validate_source_evidence,
    validate_source_rows,
    validate_target_request,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_n1_20260608_stock_identity_920206_repair_once.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("n1_stock_identity_920206_20260608_runner", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def source_evidence() -> dict:
    return {
        "stock_basic": [
            {
                "ts_code": "920206.BJ",
                "symbol": "920206",
                "name": "彩客科技",
                "area": "河北",
                "industry": "染料涂料",
                "market": "北交所",
                "list_date": TRADE_DATE,
                "delist_date": None,
                "list_status": "L",
                "exchange": "BSE",
            }
        ],
        "daily": [
            {
                "ts_code": "920206.BJ",
                "trade_date": TRADE_DATE,
                "open": 78.11,
                "high": 116.85,
                "low": 78.11,
                "close": 81.87,
                "vol": 101534.79,
                "amount": 914213.061,
            }
        ],
        "adj_factor": [{"ts_code": "920206.BJ", "trade_date": TRADE_DATE, "adj_factor": 1.0}],
        "suspend_d": [{"ts_code": "920206.BJ", "trade_date": TRADE_DATE, "suspend_type": "S"}],
        "bak_daily": [
            {
                "ts_code": "920206.BJ",
                "trade_date": TRADE_DATE,
                "name": "N彩客",
                "open": 78.11,
                "high": 116.85,
                "low": 78.11,
                "close": 81.87,
                "vol": 101535.0,
                "amount": 91421.31,
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
            "write_preflight_files": lambda *args, **kwargs: self.calls.append("write_preflight_files"),
            "write_contract_files": lambda *args, **kwargs: self.calls.append("write_contract_files"),
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


class StockIdentity920206Repair20260608Tests(unittest.TestCase):
    def test_missing_required_flags_block_before_source_fetch(self) -> None:
        cases = [
            (False, True, True, True, "--execute"),
            (True, False, True, True, "--user-confirmed"),
            (True, True, False, True, "--source-fetch-enabled"),
            (True, True, True, False, "--postgres-commit-enabled"),
        ]
        for execute, confirmed, source_fetch, commit, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(StockIdentity920206Repair20260608Blocked, message):
                    validate_execute_request(
                        execute_requested=execute,
                        user_confirmed=confirmed,
                        source_fetch_enabled=source_fetch,
                        postgres_commit_enabled=commit,
                    )

    def test_wrong_trade_date_or_identity_blocks(self) -> None:
        with self.assertRaisesRegex(StockIdentity920206Repair20260608Blocked, "20260608"):
            validate_target_request(trade_date="20260605", identity_key=EXPECTED_IDENTITY_KEY, ts_code=EXPECTED_TS_CODE)
        with self.assertRaisesRegex(StockIdentity920206Repair20260608Blocked, EXPECTED_IDENTITY_KEY):
            validate_target_request(trade_date=TRADE_DATE, identity_key="stock:BJ:920211", ts_code=EXPECTED_TS_CODE)
        with self.assertRaisesRegex(StockIdentity920206Repair20260608Blocked, EXPECTED_TS_CODE):
            validate_target_request(trade_date=TRADE_DATE, identity_key=EXPECTED_IDENTITY_KEY, ts_code="920211.BJ")

    def test_build_target_identity_row_from_evidence(self) -> None:
        rows = build_target_identity_rows(source_evidence())

        self.assertEqual(1, len(rows))
        row = rows[0]
        self.assertEqual(EXPECTED_IDENTITY_KEY, row["stock_identity_key"])
        self.assertEqual(EXPECTED_TS_CODE, row["ts_code"])
        self.assertEqual("920206", row["code"])
        self.assertEqual("BJ", row["exchange"])
        self.assertEqual("彩客科技", row["name"])
        self.assertEqual("河北", row["area"])
        self.assertEqual("染料涂料", row["industry"])
        self.assertEqual("北交所", row["market"])
        self.assertEqual(TRADE_DATE, row["listed_date"])
        self.assertEqual(SOURCE_VERSION, row["source_version"])
        self.assertIn("source_evidence", row["raw_payload"])

    def test_p0_duplicate_or_conflict_blocks(self) -> None:
        rows = build_target_identity_rows(source_evidence())
        report = validate_source_rows(rows)
        snapshot = sample_pass_snapshot()
        snapshot["target_stock_identity_rows"] = 1

        with self.assertRaisesRegex(StockIdentity920206Repair20260608Blocked, "existing target stock_identity"):
            validate_commit_preconditions(snapshot=snapshot, validation_report=report)

    def test_commit_plan_uses_20260608_scope(self) -> None:
        rows = build_target_identity_rows(source_evidence())
        report = validate_source_rows(rows)
        plan = build_commit_plan(rows=rows, validation_report=report, baseline=sample_pass_snapshot())

        self.assertEqual(BATCH_ID, plan["source_batch_id"])
        self.assertEqual(SOURCE_VERSION, plan["source_version"])
        self.assertEqual(ACTIVE_SCOPE_KEY, plan["active_source_version"]["scope_key"])
        self.assertEqual("stock_identity_20260605_v1", plan["previous_source_version"])
        self.assertEqual(1, plan["row_counts"]["stock_identity"])
        self.assertEqual(tuple(plan["allowed_write_tables"]), ALLOWED_FUTURE_WRITE_TABLES)

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
            source_fetch_enabled=True,
            postgres_commit_enabled=True,
        )

        statements = " ".join(conn.cursor_obj.statements).lower()
        self.assertTrue(conn.committed)
        self.assertEqual(1, result["row_counts"]["stock_identity"])
        for table_name in ALLOWED_FUTURE_WRITE_TABLES:
            self.assertIn(table_name, statements)
        for forbidden in (
            "stock_daily_bar_fact",
            "index_daily_bar_fact",
            "board_daily_bar_fact",
            "stock_daily_basic",
            "stock_financial_metrics_fact",
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "common_condition_run",
            "common_market_data_run",
        ):
            self.assertNotIn(f"insert into {forbidden}", statements)
            self.assertNotIn(f"update {forbidden}", statements)
            self.assertNotIn(f"delete from {forbidden}", statements)

    def test_runner_missing_flag_blocks_before_source_fetch(self) -> None:
        runner = load_runner_module()
        harness = RunnerHarness()
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            exit_code = runner.main(
                ["--trade-date", TRADE_DATE, "--execute", "--user-confirmed", "--postgres-commit-enabled", "--no-write-report"],
                dependencies=harness.deps(),
            )

        self.assertEqual(2, exit_code)
        self.assertIn("--source-fetch-enabled", stderr.getvalue())
        self.assertEqual([], harness.calls)
        self.assertFalse(harness.adapter.called)

    def test_runner_all_flags_reaches_mock_commit(self) -> None:
        runner = load_runner_module()
        harness = RunnerHarness()
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = runner.main(
                [
                    "--trade-date",
                    TRADE_DATE,
                    "--identity-key",
                    EXPECTED_IDENTITY_KEY,
                    "--ts-code",
                    EXPECTED_TS_CODE,
                    "--execute",
                    "--user-confirmed",
                    "--source-fetch-enabled",
                    "--postgres-commit-enabled",
                    "--no-write-report",
                ],
                dependencies=harness.deps(),
            )

        self.assertEqual(0, exit_code, stderr.getvalue())
        self.assertTrue(harness.adapter.called)
        self.assertTrue(harness.conn.committed)
        self.assertIn("connect", harness.calls)

    def test_runner_wrong_identity_blocks_before_source_fetch(self) -> None:
        runner = load_runner_module()
        harness = RunnerHarness()
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            exit_code = runner.main(
                ["--trade-date", TRADE_DATE, "--identity-key", "stock:BJ:920211", "--ts-code", EXPECTED_TS_CODE, "--no-write-report"],
                dependencies=harness.deps(),
            )

        self.assertEqual(2, exit_code)
        self.assertIn(EXPECTED_IDENTITY_KEY, stderr.getvalue())
        self.assertEqual([], harness.calls)
        self.assertFalse(harness.adapter.called)

    def test_implementation_report_records_ready_for_final_gate(self) -> None:
        report = build_implementation_report()

        self.assertEqual("IMPLEMENTATION_PASS", report["result"])
        self.assertEqual("ready_for_final_gate", report["runner_readiness"])
        self.assertTrue(report["final_execute_gate_allowed"])
        self.assertEqual(str(IMPLEMENTATION_REPORT_JSON), "docs/N1_20260608_STOCK_IDENTITY_920206_REPAIR_RUNNER_IMPLEMENTATION.json")


if __name__ == "__main__":
    unittest.main()
