import contextlib
import importlib.util
import io
import unittest
from pathlib import Path

from ashare_v3.ingestion.index_daily_20260526_expansion_execute import (
    ALLOWED_FUTURE_WRITE_TABLES,
    BATCH_ID,
    CANONICAL_IDENTITY_MAPPING,
    EXPECTED_ROWS,
    FIXED_9_INDEX_IDENTITIES,
    PREVIOUS_SOURCE_VERSION,
    SOURCE_VERSION,
    TRADE_DATE,
    IndexDaily20260526ExpansionBlocked,
    build_commit_plan,
    build_execute_preflight_report,
    build_source_bundle,
    execute_commit_transaction,
    sample_pass_snapshot,
    validate_commit_preconditions,
    validate_execute_request,
    validate_source_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_index_daily_20260526_expansion_once.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("n1_index_daily_20260526_expansion_runner", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def expected_scope() -> list[dict]:
    rows: list[dict] = []
    for index in range(1, 82):
        if index <= 9:
            identity_key = FIXED_9_INDEX_IDENTITIES[index - 1]
            _, exchange, code = identity_key.split(":")
        else:
            exchange = "SH" if index % 2 == 0 else "SZ"
            code = f"{300000 + index:06d}"[-6:]
            identity_key = f"index:{exchange}:{code}"
        rows.append(
            {
                "index_identity_key": identity_key,
                "ts_code": f"{code}.{exchange}",
                "code": code,
                "exchange": exchange,
                "name": f"index-{code}",
                "source_membership_identity_key": identity_key,
            }
        )
    rows.extend(
        [
            {
                "index_identity_key": "index:BJ:899050",
                "source_membership_identity_key": "index:UNKNOWN:899050",
                "ts_code": "899050.BJ",
                "code": "899050",
                "exchange": "BJ",
                "name": "北证50",
            },
            {
                "index_identity_key": "index:BJ:899601",
                "source_membership_identity_key": "index:UNKNOWN:899601",
                "ts_code": "899601.BJ",
                "code": "899601",
                "exchange": "BJ",
                "name": "北证专精特新",
            },
        ]
    )
    return rows


def index_row(scope_row: dict, *, source_type: str) -> dict:
    return {
        "index_identity_key": scope_row["index_identity_key"],
        "trade_date": TRADE_DATE,
        "code": scope_row["code"],
        "exchange": scope_row["exchange"],
        "name": scope_row["name"],
        "open": 10.0,
        "high": 10.8,
        "low": 9.9,
        "close": 10.3,
        "volume": 12345.0,
        "amount": 56789.0,
        "source": "mootdx.index" if source_type == "mootdx" else "tushare.index_daily.fallback",
        "source_type": source_type,
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSION,
        "raw_payload": {
            "mock": True,
            "source_type": source_type,
            "source_membership_identity_key": scope_row.get("source_membership_identity_key"),
        },
    }


class FakeAdapter:
    def __init__(self, scope: list[dict] | None = None) -> None:
        self.scope = scope or expected_scope()
        self.calls: list[str] = []

    def fetch_mootdx_index_daily(self, *, trade_date: str, expected_scope: list[dict]) -> list[dict]:
        self.calls.append("fetch_mootdx_index_daily")
        return [index_row(row, source_type="mootdx") for row in expected_scope if row["exchange"] != "BJ"]

    def fetch_tushare_index_daily_fallback(self, *, trade_date: str, missing_scope: list[dict]) -> list[dict]:
        self.calls.append("fetch_tushare_index_daily_fallback")
        return [index_row(row, source_type="tushare") for row in missing_scope]


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
    def __init__(self, *, snapshot: dict | None = None, scope: list[dict] | None = None) -> None:
        self.snapshot = snapshot or sample_pass_snapshot()
        self.scope = scope or expected_scope()
        self.adapter = FakeAdapter(self.scope)
        self.conn = RecordingConnection()
        self.calls: list[str] = []

    def deps(self) -> dict:
        return {
            "build_snapshot_from_db": self.build_snapshot_from_db,
            "build_expected_scope_from_db": self.build_expected_scope_from_db,
            "source_adapter_factory": self.source_adapter_factory,
            "connect": self.connect,
            "write_preflight_files": self.write_preflight_files,
            "write_contract_files": self.write_contract_files,
        }

    def build_snapshot_from_db(self, **kwargs) -> dict:
        self.calls.append("build_snapshot_from_db")
        return self.snapshot

    def build_expected_scope_from_db(self, **kwargs) -> list[dict]:
        self.calls.append("build_expected_scope_from_db")
        return self.scope

    def source_adapter_factory(self, **kwargs) -> FakeAdapter:
        self.calls.append("source_adapter_factory")
        return self.adapter

    def connect(self, dsn: str) -> RecordingConnection:
        self.calls.append("connect")
        return self.conn

    def write_preflight_files(self, *args, **kwargs) -> None:
        self.calls.append("write_preflight_files")

    def write_contract_files(self, *args, **kwargs) -> None:
        self.calls.append("write_contract_files")


class IndexDaily20260526ExpansionExecuteTests(unittest.TestCase):
    def test_missing_required_flags_block_before_fetch(self) -> None:
        cases = [
            (False, True, True, "--execute"),
            (True, False, True, "--user-confirmed"),
            (True, True, False, "--postgres-commit-enabled"),
        ]
        for execute, confirmed, commit, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(IndexDaily20260526ExpansionBlocked, message):
                    validate_execute_request(
                        execute_requested=execute,
                        user_confirmed=confirmed,
                        postgres_commit_enabled=commit,
                    )

    def test_existing_v3_rows_block(self) -> None:
        snapshot = sample_pass_snapshot()
        snapshot["existing_v3_rows"] = 1
        with self.assertRaisesRegex(IndexDaily20260526ExpansionBlocked, "existing index_daily_20260526_v3 rows"):
            validate_commit_preconditions(
                snapshot=snapshot,
                validation_report={"p0_count": 0},
                postgres_commit_enabled=True,
            )

    def test_active_source_version_must_be_v2(self) -> None:
        snapshot = sample_pass_snapshot()
        snapshot["active_source_version"] = "index_daily_20260526_v1"
        with self.assertRaisesRegex(IndexDaily20260526ExpansionBlocked, PREVIOUS_SOURCE_VERSION):
            validate_commit_preconditions(
                snapshot=snapshot,
                validation_report={"p0_count": 0},
                postgres_commit_enabled=True,
            )

    def test_mocked_source_fetch_builds_83_rows_with_bj_fallback(self) -> None:
        scope = expected_scope()
        bundle = build_source_bundle(
            adapter=FakeAdapter(scope),
            trade_date=TRADE_DATE,
            expected_scope=scope,
            source_fetch_enabled=True,
        )
        report = validate_source_bundle(bundle=bundle, expected_scope=scope)
        self.assertEqual(report["p0_count"], 0)
        self.assertEqual(report["p1_count"], 1)
        self.assertEqual(report["row_count"], EXPECTED_ROWS)
        self.assertEqual(report["mootdx_rows"], 81)
        self.assertEqual(report["tushare_fallback_rows"], 2)
        self.assertEqual(report["unknown_writes"], 0)
        self.assertEqual(report["duplicate_identity_key"], 0)
        self.assertEqual(set(report["tushare_fallback_identities"]), set(CANONICAL_IDENTITY_MAPPING.values()))

    def test_unknown_identity_write_blocks(self) -> None:
        scope = expected_scope()
        rows = [index_row(row, source_type="mootdx") for row in scope]
        rows[-1]["index_identity_key"] = "index:UNKNOWN:899601"
        with self.assertRaisesRegex(IndexDaily20260526ExpansionBlocked, "UNKNOWN"):
            validate_source_bundle(bundle={"rows": rows}, expected_scope=scope)

    def test_missing_fixed_9_blocks(self) -> None:
        scope = expected_scope()
        rows = [index_row(row, source_type="mootdx") for row in scope if row["index_identity_key"] != FIXED_9_INDEX_IDENTITIES[0]]
        with self.assertRaisesRegex(IndexDaily20260526ExpansionBlocked, "fixed 9"):
            validate_source_bundle(bundle={"rows": rows}, expected_scope=scope)

    def test_count_mismatch_blocks(self) -> None:
        scope = expected_scope()
        rows = [index_row(row, source_type="mootdx") for row in scope[:-1]]
        with self.assertRaisesRegex(IndexDaily20260526ExpansionBlocked, "expected 83"):
            validate_source_bundle(bundle={"rows": rows}, expected_scope=scope)

    def test_success_commit_plan_has_allowed_writes_only(self) -> None:
        scope = expected_scope()
        bundle = build_source_bundle(
            adapter=FakeAdapter(scope),
            trade_date=TRADE_DATE,
            expected_scope=scope,
            source_fetch_enabled=True,
        )
        report = validate_source_bundle(bundle=bundle, expected_scope=scope)
        plan = build_commit_plan(bundle=bundle, validation_report=report, baseline=sample_pass_snapshot())
        self.assertEqual(plan["row_counts"]["index_daily_bar_fact"], EXPECTED_ROWS)
        self.assertEqual(tuple(plan["allowed_write_tables"]), ALLOWED_FUTURE_WRITE_TABLES)
        self.assertEqual(plan["active_source_version"]["source_version"], SOURCE_VERSION)
        self.assertEqual(plan["active_source_version"]["previous_source_version"], PREVIOUS_SOURCE_VERSION)
        forbidden = {"stock_daily_bar_fact", "board_daily_bar_fact", "common_event_outbox", "common_event_inbox", "common_event_consumer_checkpoint"}
        self.assertFalse(forbidden & set(plan["allowed_write_tables"]))

    def test_execute_commit_transaction_writes_only_allowed_tables(self) -> None:
        scope = expected_scope()
        bundle = build_source_bundle(
            adapter=FakeAdapter(scope),
            trade_date=TRADE_DATE,
            expected_scope=scope,
            source_fetch_enabled=True,
        )
        report = validate_source_bundle(bundle=bundle, expected_scope=scope)
        plan = build_commit_plan(bundle=bundle, validation_report=report, baseline=sample_pass_snapshot())
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
        self.assertEqual(result["row_counts"]["index_daily_bar_fact"], EXPECTED_ROWS)
        self.assertIn("index_daily_bar_fact", statements)
        self.assertIn("common_active_source_version", statements)
        self.assertNotIn("stock_daily_bar_fact", statements)
        self.assertNotIn("board_daily_bar_fact", statements)
        self.assertNotIn("common_event_outbox", statements)
        self.assertNotIn("common_event_inbox", statements)

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
        self.assertEqual(exit_code, 0)
        self.assertIn("source_adapter_factory", harness.calls)
        self.assertIn("connect", harness.calls)
        self.assertTrue(harness.conn.committed)
        self.assertIn("EXECUTE_PASS", stdout.getvalue())

    def test_runner_missing_flag_blocks_before_fetch(self) -> None:
        module = load_runner_module()
        harness = RunnerHarness()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = module.main(
                ["--trade-date", TRADE_DATE, "--execute", "--user-confirmed", "--no-write-report"],
                dependencies=harness.deps(),
            )
        self.assertEqual(exit_code, 2)
        self.assertNotIn("source_adapter_factory", harness.calls)
        self.assertIn("--postgres-commit-enabled", stderr.getvalue())

    def test_rollback_sql_exists(self) -> None:
        self.assertTrue((PROJECT_ROOT / "sql" / "N1_index_daily_20260526_expansion_rollback.sql").exists())


if __name__ == "__main__":
    unittest.main()
