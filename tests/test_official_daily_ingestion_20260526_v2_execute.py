import contextlib
import importlib.util
import io
import unittest
from pathlib import Path

from ashare_v3.ingestion.official_daily_20260526_v2_execute import (
    ALLOWED_FUTURE_WRITE_TABLES,
    BATCH_ID,
    EXPECTED_ROWS,
    FIXED_9_INDEX_IDENTITIES,
    OFFICIAL_NO_TRADE_IDENTITIES,
    SOURCE_VERSIONS,
    STALE_IDENTITY_KEY,
    SUPPLEMENTAL_IDENTITIES,
    TRADE_DATE,
    OfficialDaily20260526V2ExecuteBlocked,
    build_commit_plan,
    build_execute_preflight_report,
    execute_commit_transaction,
    fetch_official_daily_sources,
    sample_pass_snapshot,
    validate_commit_preconditions,
    validate_execute_request,
    validate_source_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_official_daily_ingestion_20260526_v2_once.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("n1_official_daily_20260526_v2_runner", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def stock_scope_rows() -> list[dict]:
    rows: list[dict] = []
    for index in range(1, 5505):
        code = f"{700000 + index:06d}"
        exchange = "SH" if index % 2 == 0 else "SZ"
        rows.append(
            {
                "identity_key": f"stock:{exchange}:{code}",
                "exchange": exchange,
                "code": code,
                "name": f"stock-{code}",
                "ts_code": f"{code}.{exchange}",
                "expected_source_type": "tushare_daily",
            }
        )
    for identity_key in SUPPLEMENTAL_IDENTITIES:
        _, exchange, code = identity_key.split(":")
        rows.append(
            {
                "identity_key": identity_key,
                "exchange": exchange,
                "code": code,
                "name": f"supplemental-{code}",
                "ts_code": f"{code}.{exchange}",
                "expected_source_type": "supplemental_source_bar",
            }
        )
    return rows


def expected_scope() -> dict:
    board_rows = []
    for index in range(1, 429):
        code = f"881{index:03d}" if index <= 127 else f"880{index:03d}"
        board_rows.append(
            {
                "identity_key": f"board:TDX:{code}",
                "exchange": "TDX",
                "code": code,
                "name": f"board-{code}",
                "board_type": "tdx_industry" if code.startswith("881") else "tdx_other",
            }
        )
    return {
        "stock": stock_scope_rows(),
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
        "board": board_rows,
    }


def row_for(asset: str, scope_row: dict, *, stock_source_type: str | None = None) -> dict:
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
        source_type = stock_source_type or scope_row.get("expected_source_type") or "tushare_daily"
        row.update(
            {
                "ts_code": scope_row["ts_code"],
                "adj_factor": 1.0,
                "official_daily_proof": True,
                "source_type": source_type,
            }
        )
        if source_type == "supplemental_source_bar":
            proof = {
                "source": "mootdx.stock_daily",
                "trade_date": TRADE_DATE,
                "identity_key": scope_row["identity_key"],
            }
            row["source"] = "mootdx.stock_daily.supplemental"
            row["source_proof_json"] = proof
            row["raw_payload"] = {"mock": True, "source_proof_json": proof}
    if asset == "board":
        row["board_code"] = scope_row["code"]
        row["board_name"] = scope_row.get("name")
        row["board_type"] = scope_row.get("board_type")
    return row


def valid_bundle(scope: dict | None = None) -> dict:
    scope = scope or expected_scope()
    stock_rows = [row_for("stock", row, stock_source_type=row["expected_source_type"]) for row in scope["stock"]]
    return {
        "stock": stock_rows,
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


class FakeV2Adapter:
    def __init__(self, bundle: dict) -> None:
        self.bundle = bundle
        self.called = False

    def fetch_stock_daily(self, *, trade_date: str, expected_scope: list[dict]) -> list[dict]:
        self.called = True
        return [row for row in self.bundle["stock"] if row.get("source_type") == "tushare_daily"]

    def fetch_supplemental_stock_daily(self, *, trade_date: str, expected_scope: list[dict]) -> list[dict]:
        self.called = True
        return [row for row in self.bundle["stock"] if row.get("source_type") == "supplemental_source_bar"]

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
    def __init__(self, *, snapshot: dict | None = None, bundle: dict | None = None) -> None:
        self.snapshot = snapshot or sample_pass_snapshot()
        self.scope = expected_scope()
        self.bundle = bundle or valid_bundle(self.scope)
        self.adapter = FakeV2Adapter(self.bundle)
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

    def source_adapter_factory(self, **kwargs) -> FakeV2Adapter:
        self.calls.append("source_adapter_factory")
        return self.adapter

    def connect(self, dsn: str) -> RecordingConnection:
        self.calls.append("connect")
        return self.conn

    def write_preflight_files(self, *args, **kwargs) -> None:
        self.calls.append("write_preflight_files")

    def write_contract_files(self, *args, **kwargs) -> None:
        self.calls.append("write_contract_files")


class OfficialDaily20260526V2ExecuteTests(unittest.TestCase):
    def test_missing_each_final_flag_blocks(self) -> None:
        cases = [
            (False, True, True, True, "--execute"),
            (True, False, True, True, "--user-confirmed"),
            (True, True, False, True, "--source-fetch-enabled"),
            (True, True, True, False, "--postgres-commit-enabled"),
        ]
        for execute, confirmed, fetch, commit, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(OfficialDaily20260526V2ExecuteBlocked, message):
                    validate_execute_request(
                        execute_requested=execute,
                        user_confirmed=confirmed,
                        source_fetch_enabled=fetch,
                        postgres_commit_enabled=commit,
                    )

    def test_baseline_conflict_blocks(self) -> None:
        snapshot = sample_pass_snapshot()
        snapshot["current_daily_fact_rows"]["stock"] = 1
        snapshot["active_daily_source_versions"] = [{"data_domain": "stock", "data_type": "stock_daily", "source_version": "stock_daily_20260526_v1"}]
        snapshot["contract_batch_exists"] = True

        report = build_execute_preflight_report(snapshot, execute_requested=False, user_confirmed=False)

        self.assertEqual(report["result"], "PREFLIGHT_BLOCKED")
        self.assertIn("daily_fact_already_exists", report["blockers"])
        self.assertIn("active_source_version_conflict", report["blockers"])
        self.assertIn("batch_id_conflict", report["blockers"])

    def test_unresolved_source_gap_blocks_validation(self) -> None:
        bundle = valid_bundle()
        bundle["unresolved_source_gap"] = [{"identity_key": "stock:BJ:920058"}]

        validation = validate_source_bundle(bundle=bundle, expected_scope=expected_scope(), trade_date=TRADE_DATE)

        self.assertEqual(validation["result"], "VALIDATION_BLOCKED")
        self.assertIn("unresolved_source_gap", validation["blockers"])

    def test_supplemental_count_less_than_16_blocks_validation(self) -> None:
        bundle = valid_bundle()
        bundle["stock"] = [row for row in bundle["stock"] if row.get("identity_key") != SUPPLEMENTAL_IDENTITIES[0]]

        validation = validate_source_bundle(bundle=bundle, expected_scope=expected_scope(), trade_date=TRADE_DATE)

        self.assertEqual(validation["result"], "VALIDATION_BLOCKED")
        self.assertIn("stock_expected_coverage", validation["blockers"])
        self.assertIn("supplemental_source_bar_count_mismatch", validation["blockers"])

    def test_official_no_trade_inserted_as_bar_blocks_validation(self) -> None:
        bundle = valid_bundle()
        scope_row = {"identity_key": OFFICIAL_NO_TRADE_IDENTITIES[0], "exchange": "BJ", "code": "920058", "name": "华洋赛车", "ts_code": "920058.BJ"}
        bundle["stock"].append(row_for("stock", scope_row))

        validation = validate_source_bundle(bundle=bundle, expected_scope=expected_scope(), trade_date=TRADE_DATE)

        self.assertEqual(validation["result"], "VALIDATION_BLOCKED")
        self.assertIn("official_no_trade_inserted_as_bar", validation["blockers"])

    def test_official_no_trade_manifest_less_than_2_blocks_validation(self) -> None:
        bundle = valid_bundle()
        bundle["official_no_trade_manifest"] = bundle["official_no_trade_manifest"][:1]

        validation = validate_source_bundle(bundle=bundle, expected_scope=expected_scope(), trade_date=TRADE_DATE)

        self.assertEqual(validation["result"], "VALIDATION_BLOCKED")
        self.assertIn("official_no_trade_manifest_mismatch", validation["blockers"])

    def test_stale_identity_inserted_as_bar_blocks_validation(self) -> None:
        bundle = valid_bundle()
        scope_row = {"identity_key": STALE_IDENTITY_KEY, "exchange": "SZ", "code": "300114", "name": "stale", "ts_code": "300114.SZ"}
        bundle["stock"].append(row_for("stock", scope_row))

        validation = validate_source_bundle(bundle=bundle, expected_scope=expected_scope(), trade_date=TRADE_DATE)

        self.assertEqual(validation["result"], "VALIDATION_BLOCKED")
        self.assertIn("stale_identity_inserted_as_bar", validation["blockers"])

    def test_success_commit_plan_has_5520_9_428(self) -> None:
        scope = expected_scope()
        source_bundle = fetch_official_daily_sources(
            adapter=FakeV2Adapter(valid_bundle(scope)),
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

        self.assertEqual(validation["result"], "VALIDATION_PASS")
        self.assertEqual(validation["p0_count"], 0)
        self.assertEqual(validation["quality"]["p1_count"], 19)
        self.assertEqual(plan["row_counts"], {"stock": 5520, "index": 9, "board": 428, "total": 5957})
        self.assertEqual(plan["row_counts"]["stock"], EXPECTED_ROWS["stock_daily_bar_fact"])

    def test_commit_writes_allowed_tables_only(self) -> None:
        scope = expected_scope()
        bundle = fetch_official_daily_sources(
            adapter=FakeV2Adapter(valid_bundle(scope)),
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
        for forbidden in ("common_event_outbox", "common_event_inbox", "common_event_consumer_checkpoint", "parquet"):
            self.assertNotIn(forbidden, joined_sql)

    def test_commit_preconditions_block_existing_v1_active_version(self) -> None:
        snapshot = sample_pass_snapshot()
        snapshot["active_daily_source_versions"] = [{"data_domain": "stock", "data_type": "stock_daily", "source_version": "stock_daily_20260526_v1"}]
        validation = validate_source_bundle(bundle=valid_bundle(), expected_scope=expected_scope(), trade_date=TRADE_DATE)

        with self.assertRaisesRegex(OfficialDaily20260526V2ExecuteBlocked, "active_source_version_conflict"):
            validate_commit_preconditions(
                snapshot=snapshot,
                validation_report=validation,
                source_fetch_enabled=True,
                postgres_commit_enabled=True,
            )

    def test_rollback_sql_path_exists(self) -> None:
        self.assertTrue((PROJECT_ROOT / "sql" / "N1_official_daily_20260526_v2_ingestion_rollback.sql").exists())

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
