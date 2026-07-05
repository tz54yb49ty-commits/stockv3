import contextlib
import importlib.util
import io
import unittest
from pathlib import Path

from ashare_v3.ingestion.official_daily_20260602_execute import (
    ALLOWED_FUTURE_WRITE_TABLES,
    BATCH_ID,
    EXPECTED_ROWS,
    EXPECTED_STOCK_ADJ_FACTOR_ROWS,
    FIXED_9_INDEX_IDENTITIES,
    INDEX_TUSHARE_FALLBACK_IDENTITIES,
    OFFICIAL_NO_TRADE_IDENTITIES,
    SOURCE_VERSIONS,
    TRADE_DATE,
    OfficialDaily20260602ExecuteBlocked,
    build_commit_plan,
    execute_commit_transaction,
    fetch_official_daily_sources,
    sample_pass_snapshot,
    validate_execute_request,
    validate_source_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_official_daily_ingestion_20260602_once.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("n1_official_daily_20260602_runner", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def stock_scope_rows() -> list[dict]:
    rows: list[dict] = []
    for index in range(1, EXPECTED_ROWS["stock_daily_bar_fact"] + 1):
        code = f"{760000 + index:06d}"
        exchange = "SH" if index % 2 == 0 else "SZ"
        rows.append(
            {
                "identity_key": f"stock:{exchange}:{code}",
                "exchange": exchange,
                "code": code,
                "name": f"stock-{code}",
                "ts_code": f"{code}.{exchange}",
            }
        )
    return rows


def index_scope_rows() -> list[dict]:
    rows: list[dict] = []
    fixed = set(FIXED_9_INDEX_IDENTITIES)
    fallback = set(INDEX_TUSHARE_FALLBACK_IDENTITIES)
    for identity_key in sorted(fixed | fallback):
        _, exchange, code = identity_key.split(":")
        rows.append(
            {
                "identity_key": identity_key,
                "exchange": exchange,
                "code": code,
                "name": f"index-{code}",
                "ts_code": f"{code}.{exchange}",
                "expected_source_type": "tushare_fallback" if identity_key in fallback else "mootdx",
            }
        )
    while len(rows) < EXPECTED_ROWS["index_daily_bar_fact"]:
        idx = len(rows) + 1
        code = f"88{idx:04d}"[-6:]
        identity_key = f"index:SH:{code}"
        if identity_key in fixed or identity_key in fallback:
            continue
        rows.append(
            {
                "identity_key": identity_key,
                "exchange": "SH",
                "code": code,
                "name": f"index-{code}",
                "ts_code": f"{code}.SH",
                "expected_source_type": "mootdx",
            }
        )
    return rows


def board_scope_rows() -> list[dict]:
    rows: list[dict] = []
    for index in range(1, EXPECTED_ROWS["board_daily_bar_fact"] + 1):
        code = f"881{index:03d}" if index <= 127 else f"880{index:03d}"
        rows.append(
            {
                "identity_key": f"board:TDX:{code}",
                "exchange": "TDX",
                "code": code,
                "name": f"board-{code}",
                "board_type": "tdx_industry" if code.startswith("881") else "tdx_other",
            }
        )
    return rows


def expected_scope() -> dict:
    return {"stock": stock_scope_rows(), "index": index_scope_rows(), "board": board_scope_rows()}


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
        row.update(
            {
                "ts_code": scope_row["ts_code"],
                "adj_factor": 1.0,
                "official_daily_proof": True,
                "source_type": "tushare_daily",
            }
        )
    if asset == "index":
        row["source_type"] = scope_row.get("expected_source_type", "mootdx")
        row["source"] = "tushare.index_daily.fallback" if row["source_type"] == "tushare_fallback" else "mootdx.index"
    if asset == "board":
        row["board_code"] = scope_row["code"]
        row["board_name"] = scope_row.get("name")
        row["board_type"] = scope_row.get("board_type")
    return row


def valid_bundle(scope: dict | None = None) -> dict:
    scope = scope or expected_scope()
    return {
        "stock": [row_for("stock", row) for row in scope["stock"]],
        "index": [row_for("index", row) for row in scope["index"]],
        "board": [row_for("board", row) for row in scope["board"]],
        "official_no_trade_manifest": [
            {
                "identity_key": identity_key,
                "disposition": "official_no_trade",
                "writes_stock_daily_bar_fact": False,
                "source_proof_json": {"suspend_d": {"trade_date": TRADE_DATE}},
            }
            for identity_key in OFFICIAL_NO_TRADE_IDENTITIES
        ],
        "stale_identity_manifest": [
            {
                "identity_key": "stock:SZ:300114",
                "superseded_by_identity_key": "stock:SZ:302132",
                "disposition": "exclude_from_expected_universe",
            }
        ],
        "unresolved_source_gap": [],
    }


class Fake20260602Adapter:
    def __init__(self, bundle: dict) -> None:
        self.bundle = bundle
        self.called = False
        self.stock_daily_source_count = EXPECTED_ROWS["stock_daily_bar_fact"]
        self.stock_adj_factor_source_count = EXPECTED_STOCK_ADJ_FACTOR_ROWS
        self.stock_matched_identity_count = EXPECTED_ROWS["stock_daily_bar_fact"]
        self.stock_unmapped_daily_source_count = 0

    def fetch_stock_daily(self, *, trade_date: str, expected_scope: list[dict]) -> list[dict]:
        self.called = True
        return list(self.bundle["stock"])

    def fetch_official_no_trade_manifest(self, *, trade_date: str, identities: tuple[str, ...]) -> list[dict]:
        self.called = True
        return list(self.bundle["official_no_trade_manifest"])

    def fetch_index_daily(self, *, trade_date: str, expected_scope: list[dict]) -> list[dict]:
        self.called = True
        return list(self.bundle["index"])

    def fetch_board_daily(self, *, trade_date: str, expected_scope: list[dict]) -> list[dict]:
        self.called = True
        return list(self.bundle["board"])


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
    def __init__(self) -> None:
        self.snapshot = sample_pass_snapshot()
        self.scope = expected_scope()
        self.adapter = Fake20260602Adapter(valid_bundle(self.scope))
        self.conn = RecordingConnection()
        self.calls: list[str] = []

    def deps(self) -> dict:
        return {
            "build_snapshot_from_db": self.build_snapshot_from_db,
            "build_expected_scope_from_db": self.build_expected_scope_from_db,
            "source_adapter_factory": self.source_adapter_factory,
            "connect": self.connect,
            "load_stock_source_probe": lambda *_args, **_kwargs: {"result": "STOCK_PROBE_PASS", "stock_source": {}},
            "load_index_board_source_probe": lambda *_args, **_kwargs: {"result": "FULL_PROBE_PASS"},
            "load_execute_contract": lambda *_args, **_kwargs: {"result": "DESIGN_PASS", "source_batch_id": BATCH_ID, "source_versions": SOURCE_VERSIONS},
            "write_dry_run_files": lambda *args, **kwargs: None,
            "write_contract_files": lambda *args, **kwargs: None,
            "write_preflight_files": lambda *args, **kwargs: None,
        }

    def build_snapshot_from_db(self, **kwargs) -> dict:
        self.calls.append("build_snapshot_from_db")
        return self.snapshot

    def build_expected_scope_from_db(self, **kwargs) -> dict:
        self.calls.append("build_expected_scope_from_db")
        return self.scope

    def source_adapter_factory(self, **kwargs) -> Fake20260602Adapter:
        self.calls.append("source_adapter_factory")
        return self.adapter

    def connect(self, dsn: str) -> RecordingConnection:
        self.calls.append("connect")
        return self.conn


class OfficialDaily20260602ExecuteTests(unittest.TestCase):
    def test_constants_match_20260602_contract(self) -> None:
        self.assertEqual("20260602", TRADE_DATE)
        self.assertEqual(
            {"stock_daily_bar_fact": 5507, "index_daily_bar_fact": 83, "board_daily_bar_fact": 428, "total_daily_fact": 6018},
            EXPECTED_ROWS,
        )
        self.assertEqual(18, len(OFFICIAL_NO_TRADE_IDENTITIES))
        self.assertEqual(tuple(ALLOWED_FUTURE_WRITE_TABLES), (
            "common_ingest_batch",
            "common_quality_gate_result",
            "common_active_source_version",
            "stock_daily_bar_fact",
            "index_daily_bar_fact",
            "board_daily_bar_fact",
        ))

    def test_missing_each_final_flag_blocks(self) -> None:
        cases = [
            (False, True, True, True, "--execute"),
            (True, False, True, True, "--user-confirmed"),
            (True, True, False, True, "--source-fetch-enabled"),
            (True, True, True, False, "--postgres-commit-enabled"),
        ]
        for execute, confirmed, source_fetch, commit, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(OfficialDaily20260602ExecuteBlocked, message):
                    validate_execute_request(
                        execute_requested=execute,
                        user_confirmed=confirmed,
                        source_fetch_enabled=source_fetch,
                        postgres_commit_enabled=commit,
                    )

    def test_success_commit_plan_has_expected_rows(self) -> None:
        scope = expected_scope()
        bundle = fetch_official_daily_sources(
            adapter=Fake20260602Adapter(valid_bundle(scope)),
            trade_date=TRADE_DATE,
            expected_scope=scope,
            source_fetch_enabled=True,
        )
        validation = validate_source_bundle(bundle=bundle, expected_scope=scope, trade_date=TRADE_DATE)
        plan = build_commit_plan(bundle=bundle, validation_report=validation, baseline=sample_pass_snapshot(), trade_date=TRADE_DATE)

        self.assertEqual("VALIDATION_PASS", validation["result"])
        self.assertEqual(0, validation["p0_count"])
        self.assertEqual({"stock": 5507, "index": 83, "board": 428, "total": 6018}, plan["row_counts"])
        self.assertEqual(18, len(plan["manifest"]["official_no_trade"]))

    def test_commit_writes_allowed_tables_only(self) -> None:
        scope = expected_scope()
        bundle = fetch_official_daily_sources(
            adapter=Fake20260602Adapter(valid_bundle(scope)),
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
        joined_sql = "\n".join(conn.cursor_obj.statements).lower()
        for forbidden in ("common_event_outbox", "common_event_inbox", "common_event_consumer_checkpoint", "stock_daily_basic", "condition_"):
            self.assertNotIn(forbidden, joined_sql)

    def test_cli_four_flags_reaches_execute_path_with_mocked_fetch_and_commit(self) -> None:
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
        self.assertEqual(0, result, stderr.getvalue())
        self.assertTrue(harness.adapter.called)
        self.assertTrue(harness.conn.committed)
        self.assertIn("connect", harness.calls)


if __name__ == "__main__":
    unittest.main()
