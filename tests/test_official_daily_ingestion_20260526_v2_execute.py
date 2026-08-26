import contextlib
import importlib.util
import io
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

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
    DefaultOfficialDaily20260526V2SourceAdapter,
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
from ashare_v3.mootdx_client import EndpointConfig, MootdxEndpointManager


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


class FakeFrame:
    def __init__(self, rows):
        self.rows = list(rows)

    def to_dict(self, orient="records"):
        if orient != "records":
            raise AssertionError(orient)
        return list(self.rows)


class FakeMootdxClient:
    def __init__(self, rows_by_symbol):
        self.rows_by_symbol = rows_by_symbol
        self.calls = []

    def bars(self, **kwargs):
        self.calls.append(kwargs)
        return FakeFrame(self.rows_by_symbol.get(kwargs["symbol"], []))

    def index(self, **kwargs):
        self.calls.append(kwargs)
        return FakeFrame(self.rows_by_symbol.get(kwargs["symbol"], []))


def make_endpoint_manager(cache_path, *, mode="observe"):
    def endpoint(endpoint_id, host, priority):
        return EndpointConfig(
            endpoint_id=endpoint_id,
            host=host,
            port=7709,
            priority=priority,
            enabled=True,
            quarantined=False,
            provenance_url="https://example.invalid/frozen",
            provenance_commit="3b7ce97f2a6942cf9f39e25ee29c4e113bcfc69f",
            local_validation_status="protocol_passed",
        )

    return MootdxEndpointManager(
        endpoint_pool_version="test-pool-v1",
        transport="mootdx",
        endpoints=(
            endpoint("primary", "115.238.56.198", 10),
            endpoint("secondary", "180.153.18.170", 20),
        ),
        n1_failover_mode=mode,
        n3_failover_mode=mode,
        circuit_open_seconds=300,
        required_empty_object_threshold=3,
        health_cache_path=cache_path,
    )


def passing_endpoint_probe(endpoint, make_client):
    del endpoint, make_client
    return {
        "checks": {
            "stock_quote": True,
            "stock_daily_bars": True,
            "index_daily_bars": True,
            "scope_sentinels": True,
        }
    }


class FakeV2Adapter:
    def __init__(self, bundle: dict) -> None:
        self.bundle = bundle
        self.called = False
        self.prepared = False

    def prepare_mootdx_bundle(self, *, trade_date: str, expected_scope: dict) -> None:
        self.prepared = True

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
        self.executions: list[tuple[str, object]] = []

    def execute(self, sql: str, params=None) -> None:
        normalized_sql = " ".join(sql.split())
        self.statements.append(normalized_sql)
        self.executions.append((normalized_sql, params))


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
    def test_active_runtime_failure_discards_bundle_and_replays_once_on_secondary(self) -> None:
        bar = {
            "datetime": "2026-05-26 00:00:00",
            "open": "10",
            "high": "11",
            "low": "9",
            "close": "10.5",
            "vol": "100",
            "amount": "1000",
        }

        class RuntimeClient(FakeMootdxClient):
            def __init__(self, endpoint_id):
                super().__init__({"000001": [bar], "881001": [bar]})
                self.endpoint_id = endpoint_id
                self.closed = False
                self.close_count = 0

            def index(self, **kwargs):
                self.calls.append(kwargs)
                if self.endpoint_id == "primary" and kwargs["symbol"] == "881001":
                    raise TimeoutError("fake primary board failure")
                return FakeFrame(self.rows_by_symbol.get(kwargs["symbol"], []))

            def close(self):
                self.close_count += 1
                self.closed = True

        with tempfile.TemporaryDirectory() as tmp:
            clients = []
            adapter = DefaultOfficialDaily20260526V2SourceAdapter(
                tushare_token="fake",
                endpoint_manager=make_endpoint_manager(
                    Path(tmp) / "health.json",
                    mode="active",
                ),
                endpoint_probe=passing_endpoint_probe,
                mootdx_client_factory=lambda selection, profile: clients.append(
                    RuntimeClient(selection.endpoint_id)
                )
                or clients[-1],
                attempt_id="active-whole-bundle",
            )
            adapter.fetch_stock_daily = lambda **kwargs: []
            adapter.fetch_supplemental_stock_daily = lambda **kwargs: []
            adapter.fetch_official_no_trade_manifest = lambda **kwargs: []
            bundle = fetch_official_daily_sources(
                adapter=adapter,
                trade_date=TRADE_DATE,
                expected_scope={
                    "stock": [],
                    "index": [
                        {
                            "identity_key": "index:SH:000001",
                            "exchange": "SH",
                            "code": "000001",
                            "name": "上证指数",
                        }
                    ],
                    "board": [
                        {
                            "identity_key": "board:TDX:881001",
                            "exchange": "TDX",
                            "code": "881001",
                            "name": "行业",
                            "board_type": "tdx_industry",
                        }
                    ],
                },
                source_fetch_enabled=True,
            )

        self.assertEqual([client.endpoint_id for client in clients], ["primary", "secondary"])
        self.assertTrue(clients[0].closed)
        self.assertEqual([client.close_count for client in clients], [1, 1])
        self.assertEqual(
            {
                bundle["index"][0]["raw_payload"]["mootdx_endpoint_provenance"]["endpoint_id"],
                bundle["board"][0]["raw_payload"]["mootdx_endpoint_provenance"]["endpoint_id"],
            },
            {"secondary"},
        )
        self.assertEqual(adapter.endpoint_provenance["replay_count"], 1)
        self.assertTrue(adapter.endpoint_provenance["failover_performed"])
        self.assertEqual(
            [row["status"] for row in adapter.endpoint_provenance["attempts"]],
            ["failed", "winning"],
        )
        self.assertEqual(
            adapter.endpoint_provenance["winning_attempt_id"],
            adapter.endpoint_provenance["attempt_id"],
        )

    def test_observe_runtime_failure_records_would_retry_without_secondary_business_fetch(self) -> None:
        class RuntimeClient(FakeMootdxClient):
            def index(self, **kwargs):
                raise TimeoutError("fake primary failure")

        with tempfile.TemporaryDirectory() as tmp:
            factory_endpoints = []
            adapter = DefaultOfficialDaily20260526V2SourceAdapter(
                tushare_token="fake",
                endpoint_manager=make_endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=passing_endpoint_probe,
                mootdx_client_factory=lambda selection, profile: factory_endpoints.append(
                    selection.endpoint_id
                )
                or RuntimeClient({}),
                attempt_id="observe-whole-bundle",
            )
            adapter.fetch_stock_daily = lambda **kwargs: []
            adapter.fetch_supplemental_stock_daily = lambda **kwargs: []
            adapter.fetch_official_no_trade_manifest = lambda **kwargs: []

            with self.assertRaisesRegex(Exception, "transport failure"):
                fetch_official_daily_sources(
                    adapter=adapter,
                    trade_date=TRADE_DATE,
                    expected_scope={
                        "stock": [],
                        "index": [
                            {
                                "identity_key": "index:SH:000001",
                                "exchange": "SH",
                                "code": "000001",
                            }
                        ],
                        "board": [
                            {
                                "identity_key": "board:TDX:881001",
                                "exchange": "TDX",
                                "code": "881001",
                                "board_type": "tdx_industry",
                            }
                        ],
                    },
                    source_fetch_enabled=True,
                )

        self.assertEqual(factory_endpoints, ["primary"])
        self.assertEqual(adapter._v1._mootdx_source._client, None)
        self.assertTrue(adapter.endpoint_provenance["would_retry"])
        self.assertEqual(adapter.endpoint_provenance["replay_count"], 0)
        self.assertEqual(
            adapter.endpoint_provenance["attempts"][0]["status"],
            "failed",
        )

    def test_success_closes_winning_business_client_once_before_return(self) -> None:
        bar = {
            "datetime": "2026-05-26 00:00:00",
            "open": "10",
            "high": "11",
            "low": "9",
            "close": "10.5",
            "vol": "100",
            "amount": "1000",
        }

        class ClosingClient(FakeMootdxClient):
            def __init__(self):
                super().__init__({"000001": [bar], "881001": [bar]})
                self.close_count = 0

            def close(self):
                self.close_count += 1

        with tempfile.TemporaryDirectory() as tmp:
            client = ClosingClient()
            adapter = DefaultOfficialDaily20260526V2SourceAdapter(
                tushare_token="fake",
                endpoint_manager=make_endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=passing_endpoint_probe,
                mootdx_client_factory=lambda selection, profile: client,
                attempt_id="success-close",
            )
            adapter.fetch_stock_daily = lambda **kwargs: []
            adapter.fetch_supplemental_stock_daily = lambda **kwargs: []
            adapter.fetch_official_no_trade_manifest = lambda **kwargs: []
            bundle = fetch_official_daily_sources(
                adapter=adapter,
                trade_date=TRADE_DATE,
                expected_scope={
                    "stock": [],
                    "index": [
                        {
                            "identity_key": "index:SH:000001",
                            "exchange": "SH",
                            "code": "000001",
                        }
                    ],
                    "board": [
                        {
                            "identity_key": "board:TDX:881001",
                            "exchange": "TDX",
                            "code": "881001",
                            "board_type": "tdx_industry",
                        }
                    ],
                },
                source_fetch_enabled=True,
            )

        self.assertEqual(client.close_count, 1)
        self.assertEqual(bundle["row_counts"]["total"], 2)
        self.assertEqual(
            bundle["mootdx_endpoint_provenance"]["winning_attempt_id"],
            "success-close",
        )

    def test_success_close_failure_blocks_bundle_and_records_trace(self) -> None:
        class CloseFailClient(FakeMootdxClient):
            def close(self):
                raise RuntimeError("fake close failure")

        with tempfile.TemporaryDirectory() as tmp:
            adapter = DefaultOfficialDaily20260526V2SourceAdapter(
                tushare_token="fake",
                endpoint_manager=make_endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=passing_endpoint_probe,
                mootdx_client_factory=lambda selection, profile: CloseFailClient(
                    {
                        "000001": [],
                        "881001": [],
                    }
                ),
                attempt_id="close-fail",
            )
            adapter.fetch_stock_daily = lambda **kwargs: []
            adapter.fetch_supplemental_stock_daily = lambda **kwargs: []
            adapter.fetch_official_no_trade_manifest = lambda **kwargs: []

            with self.assertRaisesRegex(
                OfficialDaily20260526V2ExecuteBlocked,
                "close failed",
            ):
                fetch_official_daily_sources(
                    adapter=adapter,
                    trade_date=TRADE_DATE,
                    expected_scope={
                        "stock": [],
                        "index": [],
                        "board": [{"code": "881001"}],
                    },
                    source_fetch_enabled=True,
                )

        self.assertEqual(
            adapter.endpoint_provenance["business_client_close_error"],
            "RuntimeError",
        )

    def test_bundle_preflight_uses_board_sentinels_even_without_supplemental_stock(self) -> None:
        captured = []
        with tempfile.TemporaryDirectory() as tmp:
            adapter = DefaultOfficialDaily20260526V2SourceAdapter(
                tushare_token="fake",
                endpoint_manager=make_endpoint_manager(Path(tmp) / "health.json"),
                mootdx_client_factory=lambda selection, profile: FakeMootdxClient({}),
                attempt_id="bundle-board-preflight",
            )
            with patch(
                "ashare_v3.ingestion.official_daily_20260526_v2_execute.build_n1_protocol_probe",
                side_effect=lambda **kwargs: captured.append(kwargs) or passing_endpoint_probe,
            ):
                adapter.prepare_mootdx_bundle(
                    trade_date=TRADE_DATE,
                    expected_scope={
                        "stock": [],
                        "index": [{"code": "000001"}],
                        "board": [
                            {"code": code}
                            for code in ("881001", "881002", "881003", "881004", "881005")
                        ],
                    },
                )

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["scope_kind"], "board")
        self.assertEqual(
            captured[0]["symbols"],
            ["881001", "881002", "881003", "881004", "881005"],
        )
        self.assertNotIn("000001", captured[0]["symbols"])

    def test_missing_board_sentinel_target_fails_before_any_business_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            factory_calls = []
            adapter = DefaultOfficialDaily20260526V2SourceAdapter(
                tushare_token="fake",
                endpoint_manager=make_endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=lambda endpoint, make_client: {
                    "checks": {
                        "stock_quote": True,
                        "stock_daily_bars": True,
                        "index_daily_bars": True,
                        "scope_sentinels": False,
                    }
                },
                mootdx_client_factory=lambda selection, profile: factory_calls.append(
                    selection
                ),
                attempt_id="bundle-board-sentinel-missing",
            )

            with self.assertRaisesRegex(
                OfficialDaily20260526V2ExecuteBlocked,
                "preflight failed closed",
            ):
                adapter.prepare_mootdx_bundle(
                    trade_date=TRADE_DATE,
                    expected_scope={
                        "stock": [],
                        "index": [{"code": "000001"}],
                        "board": [{"code": "881001"}],
                    },
                )

        self.assertEqual(factory_calls, [])

    def test_legacy_supplemental_source_uses_shared_manager_and_traces_endpoint(self) -> None:
        scope = stock_scope_rows()
        supplemental = [
            row for row in scope if row["identity_key"] in set(SUPPLEMENTAL_IDENTITIES)
        ]
        rows_by_symbol = {
            row["code"]: [
                {
                    "datetime": "2026-05-26 00:00:00",
                    "open": "10",
                    "high": "11",
                    "low": "9",
                    "close": "10.5",
                    "vol": "100",
                    "amount": "1000",
                }
            ]
            for row in supplemental
        }
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeMootdxClient(rows_by_symbol)
            factory_calls = []
            adapter = DefaultOfficialDaily20260526V2SourceAdapter(
                tushare_token="fake",
                endpoint_manager=make_endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=passing_endpoint_probe,
                mootdx_client_factory=lambda selection, profile: factory_calls.append(
                    (selection, profile)
                )
                or client,
                attempt_id="legacy-v2-attempt",
            )

            rows = adapter.fetch_supplemental_stock_daily(
                trade_date=TRADE_DATE,
                expected_scope=scope,
            )

        self.assertEqual(len(rows), len(SUPPLEMENTAL_IDENTITIES))
        self.assertEqual(len(factory_calls), 1)
        self.assertEqual(factory_calls[0][0].server, ("115.238.56.198", 7709))
        provenance = rows[0]["source_proof_json"]["mootdx_endpoint_provenance"]
        self.assertEqual(provenance["endpoint_pool_version"], "test-pool-v1")
        self.assertEqual(provenance["endpoint_id"], "primary")
        self.assertEqual(provenance["attempt_id"], "legacy-v2-attempt")
        self.assertEqual(provenance["transport"], "mootdx")

    def test_v2_supplemental_index_and_board_share_one_selection_and_attempt(self) -> None:
        stock_scope = stock_scope_rows()
        supplemental = [
            row
            for row in stock_scope
            if row["identity_key"] in set(SUPPLEMENTAL_IDENTITIES)
        ][:1]
        index_scope = [
            {
                "identity_key": "index:SH:000001",
                "exchange": "SH",
                "code": "000001",
                "name": "上证指数",
            }
        ]
        board_scope = [
            {
                "identity_key": "board:TDX:881001",
                "exchange": "TDX",
                "code": "881001",
                "name": "行业",
                "board_type": "tdx_industry",
            }
        ]
        bar = {
            "datetime": "2026-05-26 00:00:00",
            "open": "10",
            "high": "11",
            "low": "9",
            "close": "10.5",
            "vol": "100",
            "amount": "1000",
        }
        rows_by_symbol = {
            supplemental[0]["code"]: [dict(bar)],
            "000001": [dict(bar)],
            "881001": [dict(bar)],
        }
        with tempfile.TemporaryDirectory() as tmp:
            factory_calls = []
            adapter = DefaultOfficialDaily20260526V2SourceAdapter(
                tushare_token="fake",
                endpoint_manager=make_endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=passing_endpoint_probe,
                mootdx_client_factory=lambda selection, profile: factory_calls.append(
                    selection
                )
                or FakeMootdxClient(rows_by_symbol),
                attempt_id="whole-bundle-attempt",
            )

            stock_rows = adapter.fetch_supplemental_stock_daily(
                trade_date=TRADE_DATE,
                expected_scope=supplemental,
            )
            index_rows = adapter.fetch_index_daily(
                trade_date=TRADE_DATE,
                expected_scope=index_scope,
            )
            board_rows = adapter.fetch_board_daily(
                trade_date=TRADE_DATE,
                expected_scope=board_scope,
            )

        self.assertEqual(len(factory_calls), 1)
        provenances = [
            stock_rows[0]["source_proof_json"]["mootdx_endpoint_provenance"],
            index_rows[0]["raw_payload"]["mootdx_endpoint_provenance"],
            board_rows[0]["raw_payload"]["mootdx_endpoint_provenance"],
        ]
        self.assertEqual({row["endpoint_id"] for row in provenances}, {"primary"})
        self.assertEqual({row["attempt_id"] for row in provenances}, {"whole-bundle-attempt"})

    def test_legacy_supplemental_three_empty_objects_discards_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter = DefaultOfficialDaily20260526V2SourceAdapter(
                tushare_token="fake",
                endpoint_manager=make_endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=passing_endpoint_probe,
                mootdx_client_factory=lambda selection, profile: FakeMootdxClient({}),
                attempt_id="legacy-v2-empty",
            )

            with self.assertRaisesRegex(
                OfficialDaily20260526V2ExecuteBlocked,
                "discard the complete supplemental attempt",
            ):
                adapter.fetch_supplemental_stock_daily(
                    trade_date=TRADE_DATE,
                    expected_scope=stock_scope_rows(),
                )

    def test_legacy_supplemental_repeated_empty_identity_does_not_open_circuit(self) -> None:
        repeated = next(
            row
            for row in stock_scope_rows()
            if row["identity_key"] in set(SUPPLEMENTAL_IDENTITIES)
        )
        with tempfile.TemporaryDirectory() as tmp:
            adapter = DefaultOfficialDaily20260526V2SourceAdapter(
                tushare_token="fake",
                endpoint_manager=make_endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=passing_endpoint_probe,
                mootdx_client_factory=lambda selection, profile: FakeMootdxClient({}),
                attempt_id="legacy-v2-repeat-empty",
            )

            rows = adapter.fetch_supplemental_stock_daily(
                trade_date=TRADE_DATE,
                expected_scope=[dict(repeated) for _ in range(3)],
            )

        self.assertEqual(rows, [])

    def test_supplemental_tdxpy_flag_binds_preflight_fetch_and_provenance(self) -> None:
        scope = stock_scope_rows()
        supplemental = [
            row for row in scope if row["identity_key"] in set(SUPPLEMENTAL_IDENTITIES)
        ]
        rows_by_symbol = {
            row["code"]: [
                {
                    "datetime": "2026-05-26 00:00:00",
                    "open": "10",
                    "high": "11",
                    "low": "9",
                    "close": "10.5",
                    "vol": "100",
                    "amount": "1000",
                }
            ]
            for row in supplemental
        }
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeMootdxClient(rows_by_symbol)
            factory_calls = []

            def transport_factory(selection, profile, *, transport):
                factory_calls.append(
                    (
                        transport,
                        selection.transport,
                        selection.selection_reason,
                        selection.endpoint_id,
                        profile,
                    )
                )
                return client

            def probe(endpoint, make_client):
                self.assertIs(make_client("std"), client)
                return {
                    "checks": {
                        "stock_quote": True,
                        "stock_daily_bars": True,
                        "index_daily_bars": True,
                        "scope_sentinels": True,
                    }
                }

            endpoint_manager_instance = make_endpoint_manager(Path(tmp) / "health.json")
            adapter = DefaultOfficialDaily20260526V2SourceAdapter(
                tushare_token="fake",
                endpoint_manager=endpoint_manager_instance,
                endpoint_probe=probe,
                transport_factory=transport_factory,
                quote_transport="tdxpy",
                attempt_id="legacy-v2-tdxpy",
            )
            with patch.object(
                endpoint_manager_instance,
                "record_required_object_result",
                wraps=endpoint_manager_instance.record_required_object_result,
            ) as record_result:
                rows = adapter.fetch_supplemental_stock_daily(
                    trade_date=TRADE_DATE,
                    expected_scope=scope,
                )

        self.assertEqual(
            [call[:4] for call in factory_calls],
            [
                ("tdxpy", "tdxpy", "mandatory_protocol_preflight_probe", "primary"),
                ("tdxpy", "tdxpy", "mandatory_protocol_preflight_probe", "secondary"),
                ("tdxpy", "tdxpy", "stable_priority_primary_healthy", "primary"),
            ],
        )
        proof = rows[0]["source_proof_json"]
        self.assertEqual(proof["source"], "mootdx.stock_daily")
        self.assertEqual(
            proof["mootdx_endpoint_provenance"]["transport"],
            "tdxpy",
        )
        self.assertTrue(
            all(
                call.kwargs["transport"] == "tdxpy"
                for call in record_result.call_args_list
            )
        )
        attempt = adapter.endpoint_provenance["attempts"][0]
        self.assertEqual(attempt["transport"], "tdxpy")
        self.assertEqual(
            [row["endpoint_id"] for row in attempt["endpoint_probe_results"]],
            ["primary", "secondary"],
        )
        self.assertEqual(
            attempt["pool_probe_summary"]["passed_endpoint_ids"],
            ["primary", "secondary"],
        )
        self.assertEqual(rows[0]["source_version"], SOURCE_VERSIONS["stock"])

    def test_supplemental_tdxpy_failure_records_actual_transport(self) -> None:
        class FailingClient:
            def bars(self, **kwargs):
                raise TimeoutError("fake tdxpy failure")

        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager_instance = make_endpoint_manager(Path(tmp) / "health.json")
            adapter = DefaultOfficialDaily20260526V2SourceAdapter(
                tushare_token="fake",
                endpoint_manager=endpoint_manager_instance,
                endpoint_probe=passing_endpoint_probe,
                transport_factory=lambda selection, profile, *, transport: FailingClient(),
                quote_transport="tdxpy",
                attempt_id="legacy-v2-tdxpy-failure",
            )
            with patch.object(
                endpoint_manager_instance,
                "record_transport_failure",
                wraps=endpoint_manager_instance.record_transport_failure,
            ) as record_failure:
                with self.assertRaises(OfficialDaily20260526V2ExecuteBlocked):
                    adapter.fetch_supplemental_stock_daily(
                        trade_date=TRADE_DATE,
                        expected_scope=stock_scope_rows(),
                    )

        self.assertEqual(record_failure.call_count, 1)
        self.assertEqual(record_failure.call_args.kwargs["transport"], "tdxpy")

    def test_legacy_supplemental_observe_failure_does_not_create_business_client(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            factory_calls = []

            def probe(endpoint, make_client):
                del make_client
                return {
                    "checks": {
                        "stock_quote": True,
                        "stock_daily_bars": True,
                        "index_daily_bars": True,
                        "scope_sentinels": endpoint.endpoint_id == "secondary",
                    }
                }

            adapter = DefaultOfficialDaily20260526V2SourceAdapter(
                tushare_token="fake",
                endpoint_manager=make_endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=probe,
                mootdx_client_factory=lambda selection, profile: factory_calls.append(
                    (selection, profile)
                ),
            )

            with self.assertRaisesRegex(
                OfficialDaily20260526V2ExecuteBlocked,
                "would_switch_to=secondary",
            ):
                adapter.fetch_supplemental_stock_daily(
                    trade_date=TRADE_DATE,
                    expected_scope=stock_scope_rows(),
                )

        self.assertEqual(factory_calls, [])

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

    def test_common_ingest_batch_persists_transport_pool_provenance(self) -> None:
        scope = expected_scope()
        bundle = fetch_official_daily_sources(
            adapter=FakeV2Adapter(valid_bundle(scope)),
            trade_date=TRADE_DATE,
            expected_scope=scope,
            source_fetch_enabled=True,
        )
        provenance = {
            "endpoint_pool_version": "test-pool-v1",
            "endpoint_id": "primary",
            "transport": "tdxpy",
            "source_transport": "tdxpy",
            "attempt_id": "provenance-attempt",
            "endpoint_probe_results": [
                {
                    "endpoint_id": "primary",
                    "state": "healthy",
                    "passed": True,
                    "failure_kind": None,
                },
                {
                    "endpoint_id": "secondary",
                    "state": "degraded",
                    "passed": False,
                    "failure_kind": "mandatory_probe_failed",
                },
            ],
            "pool_probe_summary": {
                "passed_endpoint_ids": ["primary"],
                "failed_endpoint_ids": ["secondary"],
            },
        }
        bundle["mootdx_endpoint_provenance"] = provenance
        validation = validate_source_bundle(
            bundle=bundle,
            expected_scope=scope,
            trade_date=TRADE_DATE,
        )
        plan = build_commit_plan(
            bundle=bundle,
            validation_report=validation,
            baseline=sample_pass_snapshot(),
            trade_date=TRADE_DATE,
        )
        conn = RecordingConnection()

        execute_commit_transaction(
            conn,
            commit_plan=plan,
            execute_requested=True,
            user_confirmed=True,
            source_fetch_enabled=True,
            postgres_commit_enabled=True,
        )

        _, params = next(
            (sql, params)
            for sql, params in conn.cursor_obj.executions
            if sql.startswith("INSERT INTO common_ingest_batch")
        )
        self.assertEqual(
            params["source_params"].obj["mootdx_endpoint_provenance"],
            provenance,
        )
        self.assertEqual(
            params["quality_gate_summary"].obj["mootdx_endpoint_provenance"],
            provenance,
        )

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

    def test_cli_active_all_endpoints_failed_has_zero_commit_fact_or_activation(self) -> None:
        runner = load_runner_module()
        harness = RunnerHarness()
        with tempfile.TemporaryDirectory() as tmp:
            harness.adapter = DefaultOfficialDaily20260526V2SourceAdapter(
                tushare_token="fake",
                endpoint_manager=make_endpoint_manager(
                    Path(tmp) / "health.json",
                    mode="active",
                ),
                endpoint_probe=lambda endpoint, make_client: {
                    "checks": {
                        **passing_endpoint_probe(endpoint, make_client)["checks"],
                        "scope_sentinels": False,
                    }
                },
                mootdx_client_factory=lambda selection, profile: self.fail(
                    "business client must not be created when all probes fail"
                ),
                attempt_id="active-all-endpoints-failed",
            )
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                io.StringIO()
            ):
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

        self.assertEqual(result, 2)
        self.assertNotIn("connect", harness.calls)
        self.assertFalse(harness.conn.committed)
        self.assertFalse(harness.conn.rolled_back)
        self.assertEqual(harness.conn.cursor_obj.statements, [])

if __name__ == "__main__":
    unittest.main()
