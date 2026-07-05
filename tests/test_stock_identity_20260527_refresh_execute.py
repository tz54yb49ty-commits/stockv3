import contextlib
import importlib.util
import io
import unittest
from pathlib import Path

from ashare_v3.ingestion.stock_identity_20260527_refresh_execute import (
    ACTIVE_SCOPE_KEY,
    ALLOWED_FUTURE_WRITE_TABLES,
    BATCH_ID,
    EXPECTED_IDENTITIES,
    SOURCE_VERSION,
    TRADE_DATE,
    StockIdentity20260527RefreshBlocked,
    build_commit_plan,
    build_execute_contract,
    build_execute_preflight_report,
    build_target_identity_rows,
    execute_commit_transaction,
    sample_pass_snapshot,
    validate_commit_preconditions,
    validate_execute_request,
    validate_source_rows,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_stock_identity_20260527_refresh_once.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("n1_stock_identity_20260527_refresh_runner", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def target_stock_basic_rows() -> list[dict]:
    return [
        {
            "ts_code": "688635.SH",
            "symbol": "688635",
            "name": "\u957f\u8fdb\u5149\u5b50",
            "area": "\u6e56\u5317",
            "industry": "\u901a\u4fe1\u8bbe\u5907",
            "market": "\u79d1\u521b\u677f",
            "list_date": TRADE_DATE,
            "delist_date": None,
            "list_status": "L",
        },
        {
            "ts_code": "920161.BJ",
            "symbol": "920161",
            "name": "\u9f99\u8fb0\u79d1\u6280",
            "area": "\u6e56\u5317",
            "industry": "\u5143\u5668\u4ef6",
            "market": "\u5317\u4ea4\u6240",
            "list_date": TRADE_DATE,
            "delist_date": None,
            "list_status": "L",
        },
    ]


class FakeSourceAdapter:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows or target_stock_basic_rows()
        self.called = False

    def fetch_stock_basic(self, *, trade_date: str, ts_codes: tuple[str, ...]) -> list[dict]:
        self.called = True
        return [dict(row) for row in self.rows if row["ts_code"] in ts_codes]


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
    def __init__(self, *, snapshot: dict | None = None, rows: list[dict] | None = None) -> None:
        self.snapshot = snapshot or sample_pass_snapshot()
        self.adapter = FakeSourceAdapter(rows)
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


class StockIdentity20260527RefreshExecuteTests(unittest.TestCase):
    def test_missing_required_flags_block_before_source_fetch(self) -> None:
        cases = [
            (False, True, True, "--execute"),
            (True, False, True, "--user-confirmed"),
            (True, True, False, "--postgres-commit-enabled"),
        ]
        for execute, confirmed, commit, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(StockIdentity20260527RefreshBlocked, message):
                    validate_execute_request(
                        execute_requested=execute,
                        user_confirmed=confirmed,
                        postgres_commit_enabled=commit,
                    )

    def test_build_target_identity_rows_from_tushare_stock_basic(self) -> None:
        rows = build_target_identity_rows(target_stock_basic_rows())

        self.assertEqual(2, len(rows))
        self.assertEqual(set(EXPECTED_IDENTITIES), {row["stock_identity_key"] for row in rows})
        self.assertEqual({"688635.SH", "920161.BJ"}, {row["ts_code"] for row in rows})
        self.assertEqual({TRADE_DATE}, {row["listed_date"] for row in rows})
        self.assertEqual({SOURCE_VERSION}, {row["source_version"] for row in rows})
        self.assertTrue(all(row["status"] == "active" for row in rows))
        self.assertFalse(any(row["is_st"] for row in rows))

    def test_missing_tushare_target_blocks(self) -> None:
        with self.assertRaisesRegex(StockIdentity20260527RefreshBlocked, "missing target stock_basic"):
            build_target_identity_rows(target_stock_basic_rows()[:1])

    def test_wrong_list_date_blocks(self) -> None:
        rows = target_stock_basic_rows()
        rows[0]["list_date"] = "20260528"
        with self.assertRaisesRegex(StockIdentity20260527RefreshBlocked, "list_date"):
            build_target_identity_rows(rows)

    def test_existing_conflicts_block_commit_preconditions(self) -> None:
        snapshot = sample_pass_snapshot()
        snapshot["target_stock_identity_rows"] = 1
        report = validate_source_rows(build_target_identity_rows(target_stock_basic_rows()))
        with self.assertRaisesRegex(StockIdentity20260527RefreshBlocked, "existing target stock_identity"):
            validate_commit_preconditions(snapshot=snapshot, validation_report=report, postgres_commit_enabled=True)

        snapshot = sample_pass_snapshot()
        snapshot["batch_conflict_count"] = 1
        with self.assertRaisesRegex(StockIdentity20260527RefreshBlocked, "existing batch"):
            validate_commit_preconditions(snapshot=snapshot, validation_report=report, postgres_commit_enabled=True)

        snapshot = sample_pass_snapshot()
        snapshot["existing_active_scope_key_count"] = 1
        with self.assertRaisesRegex(StockIdentity20260527RefreshBlocked, "existing active source_version"):
            validate_commit_preconditions(snapshot=snapshot, validation_report=report, postgres_commit_enabled=True)

    def test_stale_identity_is_manifest_only_not_written(self) -> None:
        rows = build_target_identity_rows(target_stock_basic_rows())
        report = validate_source_rows(rows)
        plan = build_commit_plan(rows=rows, validation_report=report, baseline=sample_pass_snapshot())

        self.assertEqual(1, report["p1_count"])
        self.assertNotIn("stock:SZ:300114", {row["stock_identity_key"] for row in plan["rows"]})
        self.assertEqual("stale_identity_not_modified", report["p1_items"][0]["gate_name"])

    def test_success_commit_plan_allowed_writes_only(self) -> None:
        rows = build_target_identity_rows(target_stock_basic_rows())
        report = validate_source_rows(rows)
        plan = build_commit_plan(rows=rows, validation_report=report, baseline=sample_pass_snapshot())

        self.assertEqual(2, plan["row_counts"]["stock_identity"])
        self.assertEqual(ACTIVE_SCOPE_KEY, plan["active_source_version"]["scope_key"])
        self.assertEqual(tuple(plan["allowed_write_tables"]), ALLOWED_FUTURE_WRITE_TABLES)
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
        rows = build_target_identity_rows(target_stock_basic_rows())
        report = validate_source_rows(rows)
        plan = build_commit_plan(rows=rows, validation_report=report, baseline=sample_pass_snapshot())
        conn = RecordingConnection()

        result = execute_commit_transaction(
            conn,
            commit_plan=plan,
            execute_requested=True,
            user_confirmed=True,
            postgres_commit_enabled=True,
        )

        statements = " ".join(conn.cursor_obj.statements)
        self.assertTrue(conn.committed)
        self.assertEqual(2, result["row_counts"]["stock_identity"])
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
            execute_requested=False,
            user_confirmed=False,
            postgres_commit_enabled=False,
        )
        contract = build_execute_contract(snapshot)

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
                    "--postgres-commit-enabled",
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
                ["--trade-date", TRADE_DATE, "--execute", "--user-confirmed", "--no-write-report"],
                dependencies=harness.deps(),
            )
        self.assertEqual(2, exit_code)
        self.assertNotIn("source_adapter_factory", harness.calls)
        self.assertFalse(harness.adapter.called)
        self.assertIn("--postgres-commit-enabled", stderr.getvalue())

    def test_rollback_sql_exists(self) -> None:
        self.assertTrue((PROJECT_ROOT / "sql" / "N1_stock_identity_20260527_refresh_rollback.sql").exists())


if __name__ == "__main__":
    unittest.main()
