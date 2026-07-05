import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

from ashare_v3.ingestion.official_daily_20260601_execute import (
    ALLOWED_FUTURE_WRITE_TABLES,
    BATCH_ID,
    EXPECTED_STOCK_ADJ_FACTOR_ROWS,
    EXPECTED_ROWS,
    FIXED_9_INDEX_IDENTITIES,
    INDEX_TUSHARE_FALLBACK_IDENTITIES,
    OFFICIAL_NO_TRADE_IDENTITIES,
    SOURCE_VERSIONS,
    STALE_IDENTITY_KEY,
    TRADE_DATE,
    OfficialDaily20260601ExecuteBlocked,
    build_commit_plan,
    build_index_board_source_probe_report,
    build_dry_run_report,
    build_execute_contract,
    build_execute_preflight_report,
    build_index_board_probe_from_adapter,
    execute_commit_transaction,
    fetch_official_daily_sources,
    sample_pass_snapshot,
    sample_stock_source_probe,
    sort_index_probe_candidates,
    validate_execute_request,
    validate_source_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_official_daily_ingestion_20260601_once.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("n1_official_daily_20260601_runner", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def stock_scope_rows() -> list[dict]:
    rows: list[dict] = []
    for index in range(1, EXPECTED_ROWS["stock_daily_bar_fact"] + 1):
        code = f"{750000 + index:06d}"
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
                "ts_code": identity_key.replace("stock:", "").replace(":", "."),
                "disposition": "official_no_trade",
                "writes_stock_daily_bar_fact": False,
                "source_proof_json": {
                    "suspend_d": {"trade_date": TRADE_DATE, "suspend_type": "S"},
                    "bak_daily": {"vol": 0.0, "amount": 0.0},
                },
            }
            for identity_key in OFFICIAL_NO_TRADE_IDENTITIES
        ],
        "stale_identity_manifest": [
            {
                "identity_key": STALE_IDENTITY_KEY,
                "superseded_by_identity_key": "stock:SZ:302132",
                "disposition": "exclude_from_expected_universe",
            }
        ],
        "unresolved_source_gap": [],
    }


class Fake20260601Adapter:
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
        self.bundle = valid_bundle(self.scope)
        self.adapter = Fake20260601Adapter(self.bundle)
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
            "write_contract_files": self.write_contract_files,
            "write_dry_run_files": self.write_dry_run_files,
        }

    def load_execute_contract(self, path: str) -> dict:
        self.calls.append("load_execute_contract")
        return {"result": "DESIGN_PASS", "source_batch_id": BATCH_ID, "source_versions": dict(SOURCE_VERSIONS)}

    def build_snapshot_from_db(self, **kwargs) -> dict:
        self.calls.append("build_snapshot_from_db")
        return self.snapshot

    def build_expected_scope_from_db(self, **kwargs) -> dict:
        self.calls.append("build_expected_scope_from_db")
        return self.scope

    def source_adapter_factory(self, **kwargs) -> Fake20260601Adapter:
        self.calls.append("source_adapter_factory")
        return self.adapter

    def connect(self, dsn: str) -> RecordingConnection:
        self.calls.append("connect")
        return self.conn

    def write_preflight_files(self, *args, **kwargs) -> None:
        self.calls.append("write_preflight_files")

    def write_contract_files(self, *args, **kwargs) -> None:
        self.calls.append("write_contract_files")

    def write_dry_run_files(self, *args, **kwargs) -> None:
        self.calls.append("write_dry_run_files")


class OfficialDaily20260601GateTest(unittest.TestCase):
    def test_reports_capture_20260601_nonproduction_gate(self) -> None:
        snapshot = sample_pass_snapshot()
        stock_probe = sample_stock_source_probe()

        dry_run = build_dry_run_report(snapshot=snapshot, stock_probe=stock_probe)
        contract = build_execute_contract(snapshot=snapshot, stock_probe=stock_probe)
        preflight = build_execute_preflight_report(
            snapshot=snapshot,
            stock_probe=stock_probe,
            execute_requested=False,
            user_confirmed=False,
            source_fetch_enabled=False,
            postgres_commit_enabled=False,
        )

        self.assertEqual(TRADE_DATE, dry_run["trade_date"])
        self.assertEqual(BATCH_ID, contract["source_batch_id"])
        self.assertEqual(SOURCE_VERSIONS, contract["source_versions"])
        self.assertEqual(EXPECTED_ROWS, dry_run["expected_rows"])
        self.assertEqual("DRY_RUN_PASS_WITH_DEFERRED_FINAL_SOURCE_PROBE", dry_run["result"])
        self.assertEqual("DESIGN_PASS", contract["result"])
        self.assertEqual("PREFLIGHT_PASS", preflight["result"])
        self.assertEqual("ready_for_final_gate", preflight["runner_readiness"])
        self.assertFalse(preflight["execute_authorized"])
        self.assertTrue(preflight["final_execute_gate_allowed"])
        self.assertEqual(tuple(ALLOWED_FUTURE_WRITE_TABLES), tuple(contract["future_write_scope"]["allowed_tables"]))

    def test_runner_writes_reports_without_execute_and_requires_flags_for_execute(self) -> None:
        runner = load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            args = [
                "--dry-run-json-path",
                str(tmp_path / "dry.json"),
                "--dry-run-md-path",
                str(tmp_path / "dry.md"),
                "--execute-contract-json",
                str(tmp_path / "contract.json"),
                "--execute-contract-md",
                str(tmp_path / "contract.md"),
                "--json-report-path",
                str(tmp_path / "preflight.json"),
                "--markdown-report-path",
                str(tmp_path / "preflight.md"),
            ]
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = runner.main(args, dependencies={
                    "build_snapshot_from_db": lambda **_: sample_pass_snapshot(),
                    "load_stock_source_probe": lambda *_args, **_kwargs: sample_stock_source_probe(),
                    "load_index_board_source_probe": lambda *_args, **_kwargs: None,
                })
            self.assertEqual(0, rc)
            self.assertTrue((tmp_path / "dry.json").exists())
            self.assertTrue((tmp_path / "contract.json").exists())
            self.assertTrue((tmp_path / "preflight.json").exists())

            execute_args_missing_flag = [
                *args,
                "--execute",
                "--user-confirmed",
                "--postgres-commit-enabled",
            ]
            err = io.StringIO()
            execute_out = io.StringIO()
            with contextlib.redirect_stdout(execute_out), contextlib.redirect_stderr(err):
                rc = runner.main(execute_args_missing_flag, dependencies={
                    "build_snapshot_from_db": lambda **_: sample_pass_snapshot(),
                    "load_stock_source_probe": lambda *_args, **_kwargs: sample_stock_source_probe(),
                    "load_index_board_source_probe": lambda *_args, **_kwargs: None,
                })
        self.assertEqual(2, rc)
        self.assertIn("--source-fetch-enabled", err.getvalue())

    def test_success_commit_plan_has_5508_83_428(self) -> None:
        scope = expected_scope()
        source_bundle = fetch_official_daily_sources(
            adapter=Fake20260601Adapter(valid_bundle(scope)),
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

        self.assertEqual("VALIDATION_PASS", validation["result"])
        self.assertEqual(0, validation["p0_count"])
        self.assertEqual(EXPECTED_ROWS["stock_daily_bar_fact"], validation["source_probe_counts"]["matched_identity_rows"])
        self.assertEqual(EXPECTED_STOCK_ADJ_FACTOR_ROWS, validation["source_probe_counts"]["stock_adj_factor_rows"])
        self.assertEqual({"stock": 5508, "index": 83, "board": 428, "total": 6019}, plan["row_counts"])
        self.assertEqual(17, len(plan["manifest"]["official_no_trade"]))

    def test_commit_writes_allowed_tables_only(self) -> None:
        scope = expected_scope()
        bundle = fetch_official_daily_sources(
            adapter=Fake20260601Adapter(valid_bundle(scope)),
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
        for forbidden in ("common_event_outbox", "common_event_inbox", "common_event_consumer_checkpoint", "stock_daily_basic", "parquet"):
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
        self.assertTrue(harness.conn.committed)
        self.assertTrue(harness.adapter.called)
        self.assertIn("connect", harness.calls)

    def test_missing_each_final_flag_blocks(self) -> None:
        cases = [
            (False, True, True, True, "--execute"),
            (True, False, True, True, "--user-confirmed"),
            (True, True, False, True, "--source-fetch-enabled"),
            (True, True, True, False, "--postgres-commit-enabled"),
        ]
        for execute, confirmed, source_fetch, commit, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(OfficialDaily20260601ExecuteBlocked, message):
                    validate_execute_request(
                        execute_requested=execute,
                        user_confirmed=confirmed,
                        source_fetch_enabled=source_fetch,
                        postgres_commit_enabled=commit,
                    )

    def test_index_board_probe_sample_mode_is_nonblocking(self) -> None:
        report = build_index_board_source_probe_report(
            trade_date=TRADE_DATE,
            mode="sample",
            selected_index_count=3,
            selected_board_count=4,
            index_source_rows=[
                {"identity_key": "index:SH:000001"},
                {"identity_key": "index:SH:000016"},
                {"identity_key": "index:SZ:399001"},
            ],
            board_source_rows=[
                {"identity_key": "board:TDX:881001"},
                {"identity_key": "board:TDX:881002"},
                {"identity_key": "board:TDX:880001"},
                {"identity_key": "board:TDX:885001"},
            ],
        )

        self.assertEqual("SAMPLE_PROBE_PASS", report["result"])
        self.assertEqual(0, report["quality"]["p0_count"])
        self.assertEqual(1, report["quality"]["p1_count"])
        self.assertTrue(report["full_probe_required_before_production_execute"])
        self.assertFalse(report["side_effects"]["writes_performed"])

    def test_index_board_probe_full_mode_blocks_on_missing_rows(self) -> None:
        report = build_index_board_source_probe_report(
            trade_date=TRADE_DATE,
            mode="full",
            selected_index_count=83,
            selected_board_count=428,
            index_source_rows=[{"identity_key": "index:SH:000001"}],
            board_source_rows=[{"identity_key": "board:TDX:881001"}],
        )

        self.assertEqual("FULL_PROBE_BLOCKED", report["result"])
        self.assertGreater(report["quality"]["p0_count"], 0)
        self.assertIn("index_full_coverage", report["quality"]["p0_items"])
        self.assertIn("board_full_coverage", report["quality"]["p0_items"])

    def test_preflight_clears_deferred_warning_after_full_index_board_probe(self) -> None:
        full_probe = build_index_board_source_probe_report(
            trade_date=TRADE_DATE,
            mode="full",
            selected_index_count=83,
            selected_board_count=428,
            index_source_rows=[{"identity_key": row["identity_key"]} for row in index_scope_rows()],
            board_source_rows=[{"identity_key": row["identity_key"]} for row in board_scope_rows()],
        )

        preflight = build_execute_preflight_report(
            snapshot=sample_pass_snapshot(),
            stock_probe=sample_stock_source_probe(),
            index_board_probe=full_probe,
            execute_requested=False,
            user_confirmed=False,
            source_fetch_enabled=False,
            postgres_commit_enabled=False,
        )

        self.assertEqual(0, preflight["quality"]["p1_count"])
        self.assertEqual("FULL_PROBE_PASS", preflight["source_readiness"]["index"])
        self.assertNotIn(
            "index_board_source_probe_deferred_to_final_gate",
            [item["gate_name"] for item in preflight["quality"]["items"]],
        )

    def test_index_probe_candidates_prioritize_fixed_core_indexes(self) -> None:
        candidates = [
            {"index_identity_key": "index:BJ:899050", "code": "899050"},
            {"index_identity_key": "index:SH:000905", "code": "000905"},
            {"index_identity_key": "index:SZ:399001", "code": "399001"},
            {"index_identity_key": "index:CNI:470006", "code": "470006"},
        ]

        sorted_candidates = sort_index_probe_candidates(candidates)

        self.assertEqual(
            ["index:SH:000905", "index:SZ:399001", "index:BJ:899050", "index:CNI:470006"],
            [row["index_identity_key"] for row in sorted_candidates],
        )

    def test_full_index_board_probe_reuses_production_adapter_routes(self) -> None:
        scope = expected_scope()
        adapter = Fake20260601Adapter(valid_bundle(scope))

        report = build_index_board_probe_from_adapter(
            adapter=adapter,
            trade_date=TRADE_DATE,
            mode="full",
            index_scope=scope["index"],
            board_scope=scope["board"],
        )

        self.assertEqual("FULL_PROBE_PASS", report["result"])
        self.assertEqual(83, report["source_counts"]["index"])
        self.assertEqual(428, report["source_counts"]["board"])
        self.assertFalse(report["full_probe_required_before_production_execute"])


if __name__ == "__main__":
    unittest.main()
