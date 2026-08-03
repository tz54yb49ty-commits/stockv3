import contextlib
import importlib.util
import io
import unittest
from pathlib import Path
from unittest import mock

from ashare_v3.ingestion.official_daily_20260526_contract import (
    ALLOWED_FUTURE_WRITE_TABLES,
    BATCH_ID,
    FIXED_9_INDEX_IDENTITIES,
    SOURCE_VERSIONS,
    TRADE_DATE,
    sample_pass_snapshot,
)
from ashare_v3.ingestion.official_daily_20260526_execute import (
    DefaultOfficialDaily20260526SourceAdapter,
    OfficialDaily20260526ExecuteBlocked,
    build_commit_plan,
    build_execute_preflight_report,
    execute_commit_transaction,
    fetch_official_daily_sources,
    validate_commit_preconditions,
    validate_execute_request,
    validate_source_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_official_daily_ingestion_20260526_once.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("n1_official_daily_20260526_runner", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def expected_scope() -> dict:
    return {
        "stock": [
            {"identity_key": "stock:SH:600000", "exchange": "SH", "code": "600000", "name": "浦发银行", "ts_code": "600000.SH"},
            {"identity_key": "stock:SZ:000001", "exchange": "SZ", "code": "000001", "name": "平安银行", "ts_code": "000001.SZ"},
        ],
        "index": [
            {
                "identity_key": key,
                "exchange": key.split(":")[1],
                "code": key.split(":")[2],
                "name": f"index-{key.split(':')[2]}",
                "ts_code": f"{key.split(':')[2]}.{key.split(':')[1]}",
            }
            for key in FIXED_9_INDEX_IDENTITIES
        ],
        "board": [
            {"identity_key": "board:TDX:881001", "exchange": "TDX", "code": "881001", "name": "行业1", "board_type": "tdx_industry"},
            {"identity_key": "board:TDX:881002", "exchange": "TDX", "code": "881002", "name": "行业2", "board_type": "tdx_industry"},
            {"identity_key": "board:TDX:880001", "exchange": "TDX", "code": "880001", "name": "概念1", "board_type": "tdx_concept"},
        ],
    }


def row_for(asset: str, scope_row: dict) -> dict:
    row = {
        "asset_kind": asset,
        "identity_key": scope_row["identity_key"],
        "trade_date": TRADE_DATE,
        "exchange": scope_row.get("exchange"),
        "code": scope_row["code"],
        "name": scope_row.get("name"),
        "open": 10.0,
        "high": 10.8,
        "low": 9.7,
        "close": 10.2,
        "volume": 100000.0,
        "amount": 1234567.0,
        "source": "mock.official_daily",
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSIONS[asset],
        "raw_payload": {"mock": True},
    }
    if asset == "stock":
        row["ts_code"] = scope_row["ts_code"]
        row["adj_factor"] = 1.0
        row["official_daily_proof"] = True
    if asset == "board":
        row["board_code"] = scope_row["code"]
        row["board_name"] = scope_row.get("name")
        row["board_type"] = scope_row.get("board_type")
    return row


def valid_bundle(scope: dict | None = None) -> dict:
    scope = scope or expected_scope()
    return {asset: [row_for(asset, row) for row in scope[asset]] for asset in ("stock", "index", "board")}


class FakeOfficialDailyAdapter:
    def __init__(self, bundle: dict) -> None:
        self.bundle = bundle
        self.called = False

    def fetch_stock_daily(self, *, trade_date: str, expected_scope: list[dict]) -> list[dict]:
        self.called = True
        return list(self.bundle["stock"])

    def fetch_index_daily(self, *, trade_date: str, expected_scope: list[dict]) -> list[dict]:
        self.called = True
        return list(self.bundle["index"])

    def fetch_board_daily(self, *, trade_date: str, expected_scope: list[dict]) -> list[dict]:
        self.called = True
        return list(self.bundle["board"])


class FakePinnedMootdxSource:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch_index_daily_bars(self, **kwargs):
        self.calls.append("index")
        return [
            {
                "code": symbol.code,
                "exchange": symbol.exchange,
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "vol": 100,
                "amount": 1000,
            }
            for symbol in kwargs["indexes"]
        ]

    def fetch_board_daily_bars(self, **kwargs):
        self.calls.append("board")
        return [
            {
                "board_code": symbol.board_code,
                "board_name": symbol.board_name,
                "board_type": symbol.board_type,
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "vol": 100,
                "amount": 1000,
            }
            for symbol in kwargs["boards"]
        ]


class RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, sql: str, params=None) -> None:
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
    def __init__(self, *, snapshot: dict | None = None, bundle: dict | None = None) -> None:
        self.snapshot = snapshot or sample_pass_snapshot()
        self.scope = expected_scope()
        self.bundle = bundle or valid_bundle(self.scope)
        self.adapter = FakeOfficialDailyAdapter(self.bundle)
        self.conn = RecordingConnection()
        self.calls: list[str] = []

    def deps(self) -> dict:
        return {
            "load_execute_contract": self.load_execute_contract,
            "build_snapshot_from_db": self.build_snapshot_from_db,
            "build_expected_scope_from_db": self.build_expected_scope_from_db,
            "source_adapter_factory": self.source_adapter_factory,
            "connect": self.connect,
            "write_preflight_files": self.write_preflight_files,
        }

    def load_execute_contract(self, path: str) -> dict:
        self.calls.append("load_execute_contract")
        return {"result": "DESIGN_PASS", "contract_batch_id": BATCH_ID, "source_versions": dict(SOURCE_VERSIONS)}

    def build_snapshot_from_db(self, **kwargs) -> dict:
        self.calls.append("build_snapshot_from_db")
        return self.snapshot

    def build_expected_scope_from_db(self, **kwargs) -> dict:
        self.calls.append("build_expected_scope_from_db")
        return self.scope

    def source_adapter_factory(self, **kwargs) -> FakeOfficialDailyAdapter:
        self.calls.append("source_adapter_factory")
        return self.adapter

    def connect(self, dsn: str) -> RecordingConnection:
        self.calls.append("connect")
        return self.conn

    def write_preflight_files(self, *args, **kwargs) -> None:
        self.calls.append("write_preflight_files")


class OfficialDaily20260526ExecuteTests(unittest.TestCase):
    def test_v1_adapter_reuses_one_injected_mootdx_source_for_index_and_board(self) -> None:
        scope = expected_scope()
        source = FakePinnedMootdxSource()
        adapter = DefaultOfficialDaily20260526SourceAdapter(
            tushare_token="fake",
            mootdx_source=source,
        )

        index_rows = adapter.fetch_index_daily(
            trade_date=TRADE_DATE,
            expected_scope=scope["index"],
        )
        board_rows = adapter.fetch_board_daily(
            trade_date=TRADE_DATE,
            expected_scope=scope["board"],
        )

        self.assertEqual(source.calls, ["index", "board"])
        self.assertEqual(len(index_rows), len(scope["index"]))
        self.assertEqual(len(board_rows), len(scope["board"]))

    def test_missing_required_flags_block(self) -> None:
        cases = [
            (False, True, True, True, "--execute"),
            (True, False, True, True, "--user-confirmed"),
            (True, True, False, True, "--source-fetch-enabled"),
            (True, True, True, False, "--postgres-commit-enabled"),
        ]
        for execute, confirmed, fetch, commit, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(OfficialDaily20260526ExecuteBlocked, message):
                    validate_execute_request(
                        execute_requested=execute,
                        user_confirmed=confirmed,
                        source_fetch_enabled=fetch,
                        postgres_commit_enabled=commit,
                    )

    def test_preflight_blocks_existing_facts_active_and_calendar_missing(self) -> None:
        snapshot = sample_pass_snapshot()
        snapshot["current_daily_fact_rows"]["stock"] = 1
        snapshot["active_daily_source_versions"] = [{"data_domain": "stock", "data_type": "stock_daily"}]
        snapshot["calendar"]["row_count"] = 0

        report = build_execute_preflight_report(snapshot, execute_requested=False, user_confirmed=False)

        self.assertEqual(report["result"], "PREFLIGHT_BLOCKED")
        self.assertIn("calendar_not_ready", report["blockers"])
        self.assertIn("daily_fact_already_exists", report["blockers"])
        self.assertIn("active_source_version_conflict", report["blockers"])

    def test_mocked_source_fetch_success_creates_commit_plan(self) -> None:
        scope = expected_scope()
        source_bundle = fetch_official_daily_sources(
            adapter=FakeOfficialDailyAdapter(valid_bundle(scope)),
            trade_date=TRADE_DATE,
            expected_scope=scope,
            source_fetch_enabled=True,
        )
        validation = validate_source_bundle(bundle=source_bundle, expected_scope=scope, trade_date=TRADE_DATE)
        plan = build_commit_plan(
            bundle=source_bundle,
            validation_report=validation,
            baseline=sample_pass_snapshot(),
            trade_date=TRADE_DATE,
        )

        self.assertEqual(source_bundle["row_counts"], {"stock": 2, "index": 9, "board": 3, "total": 14})
        self.assertEqual(validation["result"], "VALIDATION_PASS")
        self.assertEqual(plan["row_counts"], {"stock": 2, "index": 9, "board": 3, "total": 14})
        self.assertEqual(plan["batch_id"], BATCH_ID)

    def test_validation_requires_stock_adj_factor_fixed_9_and_board_881(self) -> None:
        scope = expected_scope()
        bundle = valid_bundle(scope)
        bundle["stock"][0]["adj_factor"] = None
        bundle["stock"][0]["official_daily_proof"] = False
        bundle["index"] = bundle["index"][:-1]
        bundle["board"] = [row for row in bundle["board"] if not str(row["board_code"]).startswith("881")]

        validation = validate_source_bundle(bundle=bundle, expected_scope=scope, trade_date=TRADE_DATE)

        self.assertEqual(validation["result"], "VALIDATION_BLOCKED")
        self.assertIn("stock_adj_factor_proof_missing", validation["blockers"])
        self.assertIn("fixed_9_index_missing", validation["blockers"])
        self.assertIn("board_881_coverage_missing", validation["blockers"])

    def test_missing_tushare_token_blocks_real_stock_fetch(self) -> None:
        with mock.patch.dict("os.environ", {"ASHARE_V3_TUSHARE_ENV_PATH": "/tmp/missing-ashare-v3-tushare.env"}, clear=True):
            adapter = DefaultOfficialDaily20260526SourceAdapter(tushare_token=None)
            with self.assertRaisesRegex(OfficialDaily20260526ExecuteBlocked, "TUSHARE_TOKEN"):
                adapter.fetch_stock_daily(trade_date=TRADE_DATE, expected_scope=expected_scope()["stock"])

    def test_duplicate_identity_and_same_code_contamination_block(self) -> None:
        scope = expected_scope()
        bundle = valid_bundle(scope)
        bundle["index"].append(dict(bundle["index"][0]))
        bundle["stock"][0]["identity_key"] = "index:SH:600000"

        validation = validate_source_bundle(bundle=bundle, expected_scope=scope, trade_date=TRADE_DATE)

        self.assertEqual(validation["result"], "VALIDATION_BLOCKED")
        self.assertIn("duplicate_identity_key", validation["blockers"])
        self.assertIn("same_code_contamination", validation["blockers"])

    def test_commit_preconditions_block_conflicts(self) -> None:
        snapshot = sample_pass_snapshot()
        snapshot["contract_batch_exists"] = True
        validation = validate_source_bundle(bundle=valid_bundle(), expected_scope=expected_scope(), trade_date=TRADE_DATE)

        with self.assertRaisesRegex(OfficialDaily20260526ExecuteBlocked, "batch_id_conflict"):
            validate_commit_preconditions(
                snapshot=snapshot,
                validation_report=validation,
                source_fetch_enabled=True,
                postgres_commit_enabled=True,
            )

    def test_commit_writes_only_allowed_tables_and_no_outbox(self) -> None:
        scope = expected_scope()
        bundle = fetch_official_daily_sources(
            adapter=FakeOfficialDailyAdapter(valid_bundle(scope)),
            trade_date=TRADE_DATE,
            expected_scope=scope,
            source_fetch_enabled=True,
        )
        validation = validate_source_bundle(bundle=bundle, expected_scope=scope, trade_date=TRADE_DATE)
        plan = build_commit_plan(bundle=bundle, validation_report=validation, baseline=sample_pass_snapshot(), trade_date=TRADE_DATE)
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
        self.assertEqual(tuple(result["written_tables"]), ALLOWED_FUTURE_WRITE_TABLES)
        joined_sql = "\n".join(conn.cursor_obj.statements)
        for forbidden in ("common_event_outbox", "common_event_inbox", "common_event_consumer_checkpoint", "parquet"):
            self.assertNotIn(forbidden, joined_sql.lower())

    def test_rollback_sql_path_exists(self) -> None:
        self.assertTrue((PROJECT_ROOT / "sql" / "N1_official_daily_20260526_ingestion_rollback.sql").exists())

    def test_cli_all_four_flags_reaches_execute_path_with_mocked_fetch_and_commit(self) -> None:
        runner = load_runner_module()
        harness = RunnerHarness()
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = runner.main(
                [
                    "--trade-date",
                    TRADE_DATE,
                    "--execute",
                    "--user-confirmed",
                    "--source-fetch-enabled",
                    "--postgres-commit-enabled",
                    "--no-write-report",
                ],
                dependencies=harness.deps(),
            )

        self.assertEqual(result, 0, stderr.getvalue())
        self.assertTrue(harness.conn.committed)
        self.assertTrue(harness.adapter.called)
        self.assertIn("connect", harness.calls)

    def test_cli_missing_flag_blocks_before_source_fetch(self) -> None:
        runner = load_runner_module()
        harness = RunnerHarness()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = runner.main(
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

        self.assertNotEqual(result, 0)
        self.assertFalse(harness.adapter.called)
        self.assertFalse(harness.conn.committed)


if __name__ == "__main__":
    unittest.main()
