import json
import inspect
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


def _args(**overrides):
    values = {
        "for_trade_date": "20260630",
        "n4_context_run_id": "trigger_context_snapshot_20260630_condition_layer_20260629_source_20260629_for_20260630_v1__atomic_rule_v1",
        "subscription_run_id": "market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1",
        "target_run_id": "n3p_mixed_realtime_source_payload_20260630_until_1016_v1",
        "requested_until_hhmm": "1016",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _report():
    return {"step_id": "n3p_current_source_fetch", "target_absence_checked": True}


class _FakeCursor:
    def __init__(self, rows):
        self.rows = list(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class _FakeScopeConnection:
    def __init__(
        self,
        *,
        subscription_status="passed",
        n4_context_status="passed",
        stock_rows=None,
        index_rows=None,
        board_rows=None,
        cumulative_counts=None,
    ) -> None:
        self.subscription_status = subscription_status
        self.n4_context_status = n4_context_status
        self.stock_rows = stock_rows if stock_rows is not None else [
            (1, "stock", "stock:SH:600000", "SH", "600000", "600000", "浦发银行", "buy", "BUY:D", False, "passed", 101, 1001),
            (2, "stock", "stock:SH:600000", "SH", "600000", "600000", "浦发银行", "sell", "SELL:D", False, "passed", 102, 1002),
            (3, "stock", "stock:SZ:300001", "SZ", "300001", "300001", "特锐德", "buy", "BUY_HINT", True, "passed", 103, 1003),
        ]
        self.index_rows = index_rows if index_rows is not None else [
            (10, "index", "index:SH:000001", "SH", "000001", "000001", "上证指数", "buy", "BUY:D", False, "passed", 201, 2001),
            (11, "index", "index:SH:000001", "SH", "000001", "000001", "上证指数", "sell", "SELL:D", False, "passed", 202, 2002),
        ]
        self.board_rows = board_rows if board_rows is not None else [
            (20, "board", "board:TDX:881001", "TDX", "881001", "881001", "行业A", "buy", "BUY:D", False, "passed", 301, 3001),
            (21, "board", "board:TDX:881001", "TDX", "881001", "881001", "行业A", "sell", "SELL_HINT", True, "passed", 302, 3002),
        ]
        self.cumulative_counts = cumulative_counts or {
            "stock_previous_day_minute_cumulative": 240,
            "index_previous_day_minute_cumulative": 240,
            "board_previous_day_minute_cumulative": 240,
        }
        self.commands: list[str] = []
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(str(sql).split())
        self.commands.append(normalized)
        upper = normalized.upper()
        if upper.startswith(("INSERT", "UPDATE", "DELETE", "TRUNCATE", "ALTER", "CREATE", "DROP")):
            raise AssertionError(f"write SQL forbidden in fake scope loader: {normalized}")
        if upper.startswith(("BEGIN READ ONLY", "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY", "ROLLBACK")):
            rows = []
            self._rows = rows
            return _FakeCursor(rows)
        if "FROM COMMON_TRADE_CALENDAR" in upper:
            rows = [(True, "20260629")]
            self._rows = rows
            return _FakeCursor(rows)
        if "FROM COMMON_MARKET_DATA_RUN" in upper:
            run_id = params[0]
            if "P0_COUNT" in upper and str(run_id).startswith("n3p_mixed_realtime_source_payload_"):
                rows = []
            else:
                status = self.subscription_status if str(run_id).startswith("market_data_subscription_") else "passed"
                rows = [(status,)]
            self._rows = rows
            return _FakeCursor(rows)
        if "FROM COMMON_TRIGGER_RUN" in upper:
            rows = [(self.n4_context_status,)]
            self._rows = rows
            return _FakeCursor(rows)
        for table, count in self.cumulative_counts.items():
            if f"FROM {table.upper()}" in upper:
                rows = [(count,)]
                self._rows = rows
                return _FakeCursor(rows)
        if "FROM STOCK_TRIGGER_CONTEXT_SNAPSHOT" in upper:
            rows = self.stock_rows
            self._rows = list(rows)
            return _FakeCursor(rows)
        if "FROM INDEX_TRIGGER_CONTEXT_SNAPSHOT" in upper:
            rows = self.index_rows
            self._rows = list(rows)
            return _FakeCursor(rows)
        if "FROM BOARD_TRIGGER_CONTEXT_SNAPSHOT" in upper:
            rows = self.board_rows
            self._rows = list(rows)
            return _FakeCursor(rows)
        raise AssertionError(f"unexpected SQL in fake scope loader: {normalized}")

    def cursor(self):
        return self

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class N3PCurrentSourceFetchProviderBackendTest(unittest.TestCase):
    def test_stock_quote_canonical_proof_minute_policy_examples(self) -> None:
        from scripts.n3p_current_source_fetch_provider import canonicalize_stock_quote_proof_minute

        examples = {
            "09:26:00": "09:31",
            "09:30:33": "09:31",
            "09:31:00": "09:31",
            "09:32:44": "09:33",
            "11:39:00": "11:30",
            "15:45:00": "15:00",
            "14:52:04.662": "14:53",
        }

        for raw_time, expected_label in examples.items():
            with self.subTest(raw_time=raw_time):
                result = canonicalize_stock_quote_proof_minute(raw_time, for_trade_date="20260630")
                self.assertEqual(result["canonical_stock_quote_proof_minute"], expected_label)
                self.assertEqual(result["stock_quote_time_mapping_policy"], "stock_quote_servertime_to_a1_canonical_proof_minute_v1")

    def test_default_scope_loader_reads_db_and_dedupes_context_scope_before_fetcher(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourceFetchBackend, N3PCurrentSourceFetchProvider

        fake_conn = _FakeScopeConnection()
        captured: dict[str, object] = {}

        class Fetcher:
            def fetch_n3p_current_market_rows(self, *, args, report, dependencies, scope, config):
                captured["scope"] = scope
                return {"result": "BLOCKED_TEST_FETCHER", "market_data_pulled": False, "database_written": False}

        backend = N3PCurrentSourceFetchBackend(
            env={"DATABASE_URL": "postgresql://unit-test"},
            market_fetcher=Fetcher(),
        )
        provider = N3PCurrentSourceFetchProvider(backend=backend)

        with patch("scripts.n3p_current_source_fetch_provider._connect_db", return_value=fake_conn):
            payload = provider.fetch_n3p_current_source_payload(args=_args(), report=_report(), dependencies=SimpleNamespace())

        scope = captured["scope"]
        self.assertEqual(payload["result"], "BLOCKED_TEST_FETCHER")
        self.assertEqual(scope["stock_object_count"], 1)
        self.assertEqual(scope["index_object_count"], 1)
        self.assertEqual(scope["board_object_count"], 1)
        self.assertEqual(scope["stock_quote_count"], 1)
        self.assertEqual(scope["index_board_1m_count"], 2)
        self.assertEqual(scope["stock_minute_bar_scope_count"], 0)
        self.assertEqual(scope["stock_hint_excluded_count"], 1)
        self.assertEqual(scope["context_row_counts"], {"stock": 3, "index": 2, "board": 2})
        self.assertEqual(scope["dedupe_counts"], {"stock": 1, "index": 1, "board": 1})
        self.assertEqual(scope["stock_quote_objects"][0]["identity_key"], "stock:SH:600000")
        self.assertEqual(scope["index_1m_objects"][0]["identity_key"], "index:SH:000001")
        self.assertEqual(scope["board_1m_objects"][0]["identity_key"], "board:TDX:881001")
        self.assertIn("BEGIN READ ONLY", fake_conn.commands[0])
        self.assertIn("ROLLBACK", fake_conn.commands[-1])

    def test_default_scope_loader_fails_closed_when_n4_context_not_passed(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourceFetchBackend, N3PCurrentSourceFetchProvider

        fake_conn = _FakeScopeConnection(n4_context_status="failed")
        backend = N3PCurrentSourceFetchBackend(env={"DATABASE_URL": "postgresql://unit-test"})
        provider = N3PCurrentSourceFetchProvider(backend=backend)

        with patch("scripts.n3p_current_source_fetch_provider._connect_db", return_value=fake_conn):
            payload = provider.fetch_n3p_current_source_payload(args=_args(), report=_report(), dependencies=SimpleNamespace())

        self.assertEqual(payload["result"], "BLOCKED_N3P_SOURCE_SCOPE_NOT_READY")
        self.assertIn("n4_context_status=failed", payload["reason"])
        self.assertFalse(payload["market_data_pulled"])
        self.assertFalse(payload["database_written"])

    def test_default_scope_loader_fails_closed_when_subscription_not_passed(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourceFetchBackend, N3PCurrentSourceFetchProvider

        fake_conn = _FakeScopeConnection(subscription_status="failed")
        backend = N3PCurrentSourceFetchBackend(env={"DATABASE_URL": "postgresql://unit-test"})
        provider = N3PCurrentSourceFetchProvider(backend=backend)

        with patch("scripts.n3p_current_source_fetch_provider._connect_db", return_value=fake_conn):
            payload = provider.fetch_n3p_current_source_payload(args=_args(), report=_report(), dependencies=SimpleNamespace())

        self.assertEqual(payload["result"], "BLOCKED_N3P_SOURCE_SCOPE_NOT_READY")
        self.assertIn("subscription_status=failed", payload["reason"])

    def test_default_scope_loader_fails_closed_on_duplicate_identity_ambiguity(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourceFetchBackend, N3PCurrentSourceFetchProvider

        ambiguous_stock = [
            (1, "stock", "stock:SH:600000", "SH", "600000", "600000", "浦发银行", "buy", "BUY:D", False, "passed", 101, 1001),
            (2, "stock", "stock:SH:600000", "SZ", "600000", "600000", "同码污染", "sell", "SELL:D", False, "passed", 102, 1002),
        ]
        fake_conn = _FakeScopeConnection(stock_rows=ambiguous_stock)
        backend = N3PCurrentSourceFetchBackend(env={"DATABASE_URL": "postgresql://unit-test"})
        provider = N3PCurrentSourceFetchProvider(backend=backend)

        with patch("scripts.n3p_current_source_fetch_provider._connect_db", return_value=fake_conn):
            payload = provider.fetch_n3p_current_source_payload(args=_args(), report=_report(), dependencies=SimpleNamespace())

        self.assertEqual(payload["result"], "BLOCKED_N3P_SOURCE_SCOPE_NOT_READY")
        self.assertIn("duplicate_identity_ambiguity", payload["reason"])

    def test_scope_validator_rejects_stock_minute_scope(self) -> None:
        from scripts.n3p_current_source_fetch_provider import validate_n3p_current_source_scope

        validation = validate_n3p_current_source_scope(
            {
                "stock_quote_objects": [],
                "index_1m_objects": [],
                "board_1m_objects": [],
                "stock_minute_bar_scope_count": 1,
            }
        )

        self.assertFalse(validation["valid"])
        self.assertIn("stock_minute_bar_scope_forbidden", validation["blocked_reasons"])

    def test_config_resolver_accepts_explicit_project_and_legacy_sources_without_fetching(self) -> None:
        from scripts.check_condition_source_ready import DEFAULT_DSN
        from scripts.n3p_current_source_fetch_provider import (
            N3PCurrentSourceFetchBackend,
            N3PCurrentSourceFetchProvider,
        )

        class ScopeLoader:
            def __init__(self) -> None:
                self.configs: list[dict[str, object]] = []

            def load_n3p_current_source_scope(self, *, args, report, dependencies, config):
                self.configs.append(dict(config))
                return {
                    "for_trade_date": args.for_trade_date,
                    "n4_context_status": "passed",
                    "subscription_status": "passed",
                    "a1_cumulative_status": "passed",
                }

        cases = [
            (
                "explicit_config_wins",
                {"ASHARE_V3_POSTGRES_DSN": "postgresql://env-ignored"},
                {"database_url": "postgresql://explicit"},
                {"database_url": "postgresql://explicit"},
            ),
            (
                "ashare_v3_postgres_dsn",
                {"ASHARE_V3_POSTGRES_DSN": "postgresql://ashare-v3"},
                None,
                {"database_url": "postgresql://ashare-v3"},
            ),
            (
                "database_url",
                {"DATABASE_URL": "postgresql://database-url"},
                None,
                {"database_url": "postgresql://database-url"},
            ),
            (
                "pg_dsn",
                {"PG_DSN": "postgresql://pg-dsn"},
                None,
                {"database_url": "postgresql://pg-dsn"},
            ),
            (
                "postgres_dsn",
                {"POSTGRES_DSN": "postgresql://postgres-dsn"},
                None,
                {"database_url": "postgresql://postgres-dsn"},
            ),
            (
                "pghost_pgdatabase",
                {"PGHOST": "127.0.0.1", "PGDATABASE": "ashare_v3", "PGUSER": "ashare_v3_user", "PGPORT": "5432"},
                None,
                {
                    "pg_host": "127.0.0.1",
                    "pg_database": "ashare_v3",
                    "pg_user": "ashare_v3_user",
                    "pg_port": "5432",
                },
            ),
            (
                "project_default_dsn",
                {},
                None,
                {"database_url": DEFAULT_DSN},
            ),
        ]

        for name, env, explicit_config, expected_config in cases:
            with self.subTest(name=name):
                scope_loader = ScopeLoader()
                backend = N3PCurrentSourceFetchBackend(
                    env=env,
                    config=explicit_config,
                    scope_loader=scope_loader,
                )
                provider = N3PCurrentSourceFetchProvider(backend=backend)

                payload = provider.fetch_n3p_current_source_payload(
                    args=_args(),
                    report=_report(),
                    dependencies=SimpleNamespace(),
                )

                self.assertEqual(payload["result"], "BLOCKED_N3P_SOURCE_FETCH_BACKEND_FETCHER")
                self.assertEqual(scope_loader.configs, [expected_config])
                self.assertFalse(payload["market_data_pulled"])
                self.assertFalse(payload["database_written"])

    def test_config_resolver_does_not_expose_secret_dsn_in_reports(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourceFetchBackend, N3PCurrentSourceFetchProvider

        class ScopeLoader:
            def load_n3p_current_source_scope(self, *, args, report, dependencies, config):
                return {
                    "for_trade_date": args.for_trade_date,
                    "n4_context_status": "passed",
                    "subscription_status": "passed",
                    "a1_cumulative_status": "passed",
                }

        sensitive_dsn = "postgresql://ashare_v3_user:" + "super-secret-password" + "@127.0.0.1:5432/ashare_v3"
        backend = N3PCurrentSourceFetchBackend(
            env={"ASHARE_V3_POSTGRES_DSN": sensitive_dsn},
            scope_loader=ScopeLoader(),
        )
        provider = N3PCurrentSourceFetchProvider(backend=backend)

        payload = provider.fetch_n3p_current_source_payload(args=_args(), report=_report(), dependencies=SimpleNamespace())
        serialized_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)

        self.assertEqual(payload["result"], "BLOCKED_N3P_SOURCE_FETCH_BACKEND_FETCHER")
        self.assertNotIn("super-secret-password", serialized_payload)
        self.assertNotIn(sensitive_dsn, serialized_payload)
        self.assertFalse(payload["market_data_pulled"])
        self.assertFalse(payload["database_written"])

    def test_default_backend_binds_scope_loader_and_blocks_on_missing_fetcher(self) -> None:
        from scripts.n3p_current_source_fetch_provider import (
            N3PCurrentSourceFetchBackend,
            N3PCurrentSourceFetchProvider,
        )

        fake_conn = _FakeScopeConnection()
        provider = N3PCurrentSourceFetchProvider(backend=N3PCurrentSourceFetchBackend(env={}))
        with (
            patch("scripts.n3p_current_source_fetch_provider._connect_db", return_value=fake_conn),
            patch("scripts.n3p_current_source_fetch_provider._default_mootdx_client", return_value=None),
        ):
            payload = provider.fetch_n3p_current_source_payload(args=_args(), report=_report(), dependencies=SimpleNamespace())

        self.assertEqual(payload["result"], "BLOCKED_N3P_SOURCE_FETCH_BACKEND_FETCHER")
        self.assertIn("market fetch dependency", payload["reason"])
        self.assertFalse(payload["market_data_pulled"])
        self.assertFalse(payload["database_written"])

        default_provider = N3PCurrentSourceFetchProvider()
        with (
            patch("scripts.n3p_current_source_fetch_provider._connect_db", return_value=fake_conn),
            patch("scripts.n3p_current_source_fetch_provider._default_mootdx_client", return_value=None),
        ):
            default_payload = default_provider.fetch_n3p_current_source_payload(
                args=_args(),
                report=_report(),
                dependencies=SimpleNamespace(),
            )
        self.assertEqual(default_payload["result"], "BLOCKED_N3P_SOURCE_FETCH_BACKEND_FETCHER")
        self.assertTrue(str(default_payload["reason"]).startswith("BLOCKED_N3P_SOURCE_FETCH_BACKEND_FETCHER"))

    def test_production_market_adapter_constructs_without_network_call(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentMarketFetchAdapter

        calls: list[str] = []

        adapter = N3PCurrentMarketFetchAdapter(client_factory=lambda: calls.append("factory"))

        self.assertEqual(calls, [])
        self.assertTrue(callable(getattr(adapter, "quotes")))
        self.assertTrue(callable(getattr(adapter, "index_bars")))

    def test_production_market_adapter_normalizes_client_method_calls(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentMarketFetchAdapter

        calls: list[tuple] = []

        class Client:
            def quotes(self, *, symbol):
                calls.append(("quotes", symbol))
                return [{"code": symbol, "price": 1, "amount": 2, "servertime": "10:16:00"}]

            def index(self, *, symbol, frequency, start, offset, market):
                calls.append(("index", symbol, frequency, start, offset, market))
                return [{"datetime": "2026-06-30 10:16", "open": 1, "high": 1, "low": 1, "close": 1, "amount": 1}]

        adapter = N3PCurrentMarketFetchAdapter(client_factory=Client)

        self.assertEqual(adapter.quotes(symbol="600000"), [{"code": "600000", "price": 1, "amount": 2, "servertime": "10:16:00"}])
        self.assertEqual(adapter.index_bars(symbol="000001", frequency=8, start=0, offset=800, market=1), [{"datetime": "2026-06-30 10:16", "open": 1, "high": 1, "low": 1, "close": 1, "amount": 1}])
        self.assertEqual(calls, [
            ("quotes", "600000"),
            ("index", "000001", 8, 0, 800, 1),
        ])

    def test_default_market_fetcher_uses_injected_client_and_preserves_actual_hhmm(self) -> None:
        from scripts.n3p_current_source_fetch_provider import (
            N3PCurrentSourceFetchBackend,
            N3PCurrentSourceFetchProvider,
            compute_n3p_current_source_payload_hash,
        )

        calls: list[tuple] = []

        class ScopeLoader:
            def load_n3p_current_source_scope(self, *, args, report, dependencies, config):
                return {
                    "for_trade_date": args.for_trade_date,
                    "n4_context_status": "passed",
                    "subscription_status": "passed",
                    "a1_cumulative_status": "passed",
                    "stock_quote_objects": [
                        {"asset_kind": "stock", "identity_key": "stock:SH:600000", "exchange": "SH", "code": "600000", "name": "浦发银行"},
                    ],
                    "index_1m_objects": [
                        {"asset_kind": "index", "identity_key": "index:SH:000001", "exchange": "SH", "code": "000001", "name": "上证指数"},
                    ],
                    "board_1m_objects": [
                        {"asset_kind": "board", "identity_key": "board:TDX:881001", "exchange": "TDX", "code": "881001", "name": "行业A"},
                    ],
                    "stock_object_count": 1,
                    "index_object_count": 1,
                    "board_object_count": 1,
                    "stock_minute_bar_scope_count": 0,
                }

        class FakeMootdxClient:
            def quotes(self, *, symbol):
                calls.append(("quotes", symbol))
                return [
                    {
                        "code": symbol,
                        "price": 10.5,
                        "open": 10.0,
                        "high": 11.0,
                        "low": 9.8,
                        "amount": 123456.0,
                        "volume": 1000,
                            "servertime": "10:16:00",
                        "source_marker": "mootdx_quotes",
                    }
                ]

            def index_bars(self, *, symbol, frequency, start, offset):
                calls.append(("index_bars", symbol, frequency, start, offset))
                return [
                    {
                        "datetime": "2026-06-30 10:15",
                        "open": 1,
                        "high": 2,
                        "low": 1,
                        "close": 2,
                        "amount": 100.0,
                        "volume": 10,
                    },
                    {
                        "datetime": "2026-06-30 10:16",
                        "open": 2,
                        "high": 3,
                        "low": 2,
                        "close": 3,
                        "amount": 200.0,
                        "volume": 20,
                    },
                ]

        class ArtifactWriter:
            def write_n3p_current_source_artifacts(self, *, args, report, dependencies, payload, fetch_report, config):
                return {
                    "payload_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1016_source_fetch_payload.json",
                    "report_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1016_source_fetch_report.json",
                    "payload_hash": compute_n3p_current_source_payload_hash(payload),
                }

        backend = N3PCurrentSourceFetchBackend(
            env={"DATABASE_URL": "postgresql://unit-test"},
            scope_loader=ScopeLoader(),
            market_fetcher=FakeMootdxClient(),
            artifact_writer=ArtifactWriter(),
        )
        provider = N3PCurrentSourceFetchProvider(backend=backend)

        payload = provider.fetch_n3p_current_source_payload(args=_args(), report=_report(), dependencies=SimpleNamespace())

        self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertEqual(payload["actual_until_hhmm"], "1016")
        self.assertEqual(payload["source_payload_counts"], {"stock_quote_rows": 1, "index_board_1m_rows": 4})
        self.assertEqual(payload["stock_quote_rows"][0]["source_adapter_method"], "quotes")
        self.assertEqual({row["source_frequency"] for row in payload["index_board_1m_rows"]}, {8})
        self.assertEqual(calls, [
            ("quotes", "600000"),
            ("index_bars", "000001", 8, 0, 800),
            ("index_bars", "881001", 8, 0, 800),
        ])
        self.assertNotIn("stock_minute_rows", payload)
        self.assertFalse(payload["database_written"])
        self.assertFalse(payload["writes_outbox"])

    def test_market_fetcher_filters_date_1130_and_exact_duplicates_before_validation(self) -> None:
        from scripts.n3p_current_source_fetch_provider import (
            N3PCurrentSourceFetchBackend,
            N3PCurrentSourceFetchProvider,
            compute_n3p_current_source_payload_hash,
        )

        class ScopeLoader:
            def load_n3p_current_source_scope(self, *, args, report, dependencies, config):
                return {
                    "for_trade_date": args.for_trade_date,
                    "n4_context_status": "passed",
                    "subscription_status": "passed",
                    "a1_cumulative_status": "passed",
                    "stock_quote_objects": [
                        {"asset_kind": "stock", "identity_key": "stock:SH:600000", "exchange": "SH", "code": "600000"},
                    ],
                    "index_1m_objects": [
                        {"asset_kind": "index", "identity_key": "index:SH:000001", "exchange": "SH", "code": "000001"},
                    ],
                    "board_1m_objects": [],
                    "stock_object_count": 1,
                    "index_object_count": 1,
                    "board_object_count": 0,
                    "stock_minute_bar_scope_count": 0,
                }

        class FakeMootdxClient:
            def quotes(self, *, symbol):
                return [{"code": symbol, "price": 10.5, "amount": 123456.0, "servertime": "10:16:00"}]

            def index_bars(self, *, symbol, frequency, start, offset):
                good = {
                    "datetime": "2026-06-30 10:16",
                    "open": 1,
                    "high": 2,
                    "low": 1,
                    "close": 2,
                    "amount": 100.0,
                }
                return [
                    {"datetime": "2026-06-29 10:16", "open": 1, "high": 2, "low": 1, "close": 2, "amount": 90.0},
                    {"datetime": "2026-06-30 11:30", "open": 1, "high": 2, "low": 1, "close": 2, "amount": 10.0},
                    dict(good),
                    dict(good),
                ]

        class ArtifactWriter:
            def write_n3p_current_source_artifacts(self, *, args, report, dependencies, payload, fetch_report, config):
                return {
                    "payload_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1016_source_fetch_payload.json",
                    "report_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1016_source_fetch_report.json",
                    "payload_hash": compute_n3p_current_source_payload_hash(payload),
                }

        backend = N3PCurrentSourceFetchBackend(
            env={"DATABASE_URL": "postgresql://unit-test"},
            scope_loader=ScopeLoader(),
            market_fetcher=FakeMootdxClient(),
            artifact_writer=ArtifactWriter(),
        )
        provider = N3PCurrentSourceFetchProvider(backend=backend)

        payload = provider.fetch_n3p_current_source_payload(args=_args(), report=_report(), dependencies=SimpleNamespace())

        self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertEqual(payload["actual_until_hhmm"], "1016")
        self.assertEqual(payload["source_payload_counts"], {"stock_quote_rows": 1, "index_board_1m_rows": 1})
        self.assertEqual(payload["index_board_1m_rows"][0]["minute_label"], "10:16")
        self.assertEqual(payload["index_board_1m_rows"][0]["trade_date"], "20260630")
        trace = payload["normalization_trace"]
        self.assertEqual(trace["raw_rows_before_filter"], {"stock_quote_rows": 1, "index_board_1m_rows": 4})
        self.assertEqual(trace["rows_dropped_date_mismatch"], 1)
        self.assertEqual(trace["rows_dropped_1130"], 1)
        self.assertEqual(trace["duplicate_rows_collapsed"], 1)
        self.assertEqual(trace["duplicate_conflicts"], 0)
        self.assertEqual(payload["payload_hash"], compute_n3p_current_source_payload_hash(payload))

    def test_source_fetch_blocks_post_close_index_board_proof_minute_before_artifact(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourceFetchBackend, N3PCurrentSourceFetchProvider

        calls: list[str] = []

        class ScopeLoader:
            def load_n3p_current_source_scope(self, *, args, report, dependencies, config):
                calls.append("scope")
                return {
                    "for_trade_date": args.for_trade_date,
                    "n4_context_status": "passed",
                    "subscription_status": "passed",
                    "a1_cumulative_status": "passed",
                    "stock_quote_objects": [],
                    "index_1m_objects": [
                        {"asset_kind": "index", "identity_key": "index:SH:000001", "exchange": "SH", "code": "000001"},
                    ],
                    "board_1m_objects": [],
                    "stock_object_count": 0,
                    "index_object_count": 1,
                    "board_object_count": 0,
                    "stock_minute_bar_scope_count": 0,
                }

        class Fetcher:
            def fetch_n3p_current_market_rows(self, *, args, report, dependencies, scope, config):
                calls.append("fetch")
                return {
                    "stock_quote_rows": [],
                    "index_board_1m_rows": [
                        {
                            "asset_kind": "index",
                            "identity_key": "index:SH:000001",
                            "bar_time": "2026-06-30T15:30:00+08:00",
                            "open": 1,
                            "high": 2,
                            "low": 1,
                            "close": 2,
                            "amount": 100.0,
                            "source_marker": "mootdx_index_frequency_8",
                        }
                    ],
                }

        class ArtifactWriter:
            def write_n3p_current_source_artifacts(self, **_kwargs):
                calls.append("artifact")
                raise AssertionError("post-close source must not reach artifact writer")

        backend = N3PCurrentSourceFetchBackend(
            env={"DATABASE_URL": "postgresql://unit-test"},
            scope_loader=ScopeLoader(),
            market_fetcher=Fetcher(),
            artifact_writer=ArtifactWriter(),
        )
        provider = N3PCurrentSourceFetchProvider(backend=backend)

        payload = provider.fetch_n3p_current_source_payload(
            args=_args(target_run_id="n3p_mixed_realtime_source_payload_20260630_until_1530_v1", requested_until_hhmm="1530"),
            report=_report(),
            dependencies=SimpleNamespace(),
        )

        self.assertEqual(payload["result"], "BLOCKED_N3P_SOURCE_POST_CLOSE_PROOF_MINUTE")
        self.assertEqual(payload["actual_until_hhmm"], "1530")
        self.assertEqual(payload["max_canonical_proof_hhmm"], "1500")
        self.assertTrue(payload["post_close_proof_minute_blocked"])
        self.assertFalse(payload["artifact_written"])
        self.assertFalse(payload["source_payload_registered"])
        self.assertFalse(payload["database_written"])
        self.assertEqual(calls, ["scope", "fetch"])

    def test_source_fetch_maps_post_close_stock_quote_to_canonical_close(self) -> None:
        from scripts.n3p_current_source_fetch_provider import (
            N3PCurrentSourceFetchBackend,
            N3PCurrentSourceFetchProvider,
            compute_n3p_current_source_payload_hash,
        )

        class ScopeLoader:
            def load_n3p_current_source_scope(self, *, args, report, dependencies, config):
                return {
                    "for_trade_date": args.for_trade_date,
                    "n4_context_status": "passed",
                    "subscription_status": "passed",
                    "a1_cumulative_status": "passed",
                    "stock_quote_objects": [
                        {"asset_kind": "stock", "identity_key": "stock:SH:600000", "exchange": "SH", "code": "600000"},
                    ],
                    "index_1m_objects": [
                        {"asset_kind": "index", "identity_key": "index:SH:000001", "exchange": "SH", "code": "000001"},
                    ],
                    "board_1m_objects": [],
                    "stock_object_count": 1,
                    "index_object_count": 1,
                    "board_object_count": 0,
                    "stock_minute_bar_scope_count": 0,
                }

        class Fetcher:
            def fetch_n3p_current_market_rows(self, *, args, report, dependencies, scope, config):
                return {
                    "stock_quote_rows": [
                        {
                            "asset_kind": "stock",
                            "identity_key": "stock:SH:600000",
                            "code": "600000",
                            "price": 10.5,
                            "amount": 123456.0,
                            "source_time": "2026-06-30T15:45:00+08:00",
                            "source_marker": "mootdx_quotes",
                        }
                    ],
                    "index_board_1m_rows": [
                        {
                            "asset_kind": "index",
                            "identity_key": "index:SH:000001",
                            "bar_time": "2026-06-30T15:00:00+08:00",
                            "open": 1,
                            "high": 2,
                            "low": 1,
                            "close": 2,
                            "amount": 100.0,
                            "source_marker": "mootdx_index_frequency_8",
                        }
                    ],
                }

        class ArtifactWriter:
            def write_n3p_current_source_artifacts(self, *, args, report, dependencies, payload, fetch_report, config):
                return {
                    "payload_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1500_source_fetch_payload.json",
                    "report_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1500_source_fetch_report.json",
                    "payload_hash": compute_n3p_current_source_payload_hash(payload),
                }

        backend = N3PCurrentSourceFetchBackend(
            env={"DATABASE_URL": "postgresql://unit-test"},
            scope_loader=ScopeLoader(),
            market_fetcher=Fetcher(),
            artifact_writer=ArtifactWriter(),
        )
        provider = N3PCurrentSourceFetchProvider(backend=backend)

        payload = provider.fetch_n3p_current_source_payload(
            args=_args(target_run_id="n3p_mixed_realtime_source_payload_20260630_until_1500_v1", requested_until_hhmm="1500"),
            report=_report(),
            dependencies=SimpleNamespace(),
        )

        self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertEqual(payload["actual_until_hhmm"], "1500")
        self.assertEqual(payload["proof_input_time"], "2026-06-30T15:00:00+08:00")
        self.assertEqual(payload["stock_quote_rows"][0]["canonical_stock_quote_proof_minute"], "15:00")
        self.assertEqual(payload["stock_quote_rows"][0]["raw_source_time"], "2026-06-30T15:45:00+08:00")
        self.assertFalse(payload.get("post_close_proof_minute_blocked", False))

    def test_source_fetch_allows_adjacent_mixed_stock_and_index_board_canonical_minutes(self) -> None:
        from scripts.n3p_current_source_fetch_provider import (
            N3PCurrentSourceFetchBackend,
            N3PCurrentSourceFetchProvider,
            compute_n3p_current_source_payload_hash,
        )

        calls: list[str] = []
        written_payloads: list[dict] = []
        written_reports: list[dict] = []

        class ScopeLoader:
            def load_n3p_current_source_scope(self, *, args, report, dependencies, config):
                return {
                    "for_trade_date": args.for_trade_date,
                    "n4_context_status": "passed",
                    "subscription_status": "passed",
                    "a1_cumulative_status": "passed",
                    "stock_quote_objects": [
                        {"asset_kind": "stock", "identity_key": "stock:SH:600000", "exchange": "SH", "code": "600000"},
                    ],
                    "index_1m_objects": [
                        {"asset_kind": "index", "identity_key": "index:SH:000001", "exchange": "SH", "code": "000001"},
                    ],
                    "board_1m_objects": [],
                    "stock_object_count": 1,
                    "index_object_count": 1,
                    "board_object_count": 0,
                    "stock_minute_bar_scope_count": 0,
                }

        class Fetcher:
            def fetch_n3p_current_market_rows(self, *, args, report, dependencies, scope, config):
                return {
                    "stock_quote_rows": [
                        {
                            "asset_kind": "stock",
                            "identity_key": "stock:SH:600000",
                            "code": "600000",
                            "price": 10.5,
                            "amount": 123456.0,
                            "source_time": "2026-06-30T14:52:04.662+08:00",
                            "source_marker": "mootdx_quotes",
                        }
                    ],
                    "index_board_1m_rows": [
                        {
                            "asset_kind": "index",
                            "identity_key": "index:SH:000001",
                            "bar_time": "2026-06-30T14:52:00+08:00",
                            "open": 1,
                            "high": 2,
                            "low": 1,
                            "close": 2,
                            "amount": 100.0,
                            "source_marker": "mootdx_index_frequency_8",
                        }
                    ],
                }

        class ArtifactWriter:
            def write_n3p_current_source_artifacts(self, **kwargs):
                calls.append("artifact")
                payload = dict(kwargs["payload"])
                fetch_report = dict(kwargs["fetch_report"])
                written_payloads.append(payload)
                written_reports.append(fetch_report)
                return {"payload_hash": compute_n3p_current_source_payload_hash(payload)}

        backend = N3PCurrentSourceFetchBackend(
            env={"DATABASE_URL": "postgresql://unit-test"},
            scope_loader=ScopeLoader(),
            market_fetcher=Fetcher(),
            artifact_writer=ArtifactWriter(),
        )
        provider = N3PCurrentSourceFetchProvider(backend=backend)

        payload = provider.fetch_n3p_current_source_payload(
            args=_args(target_run_id="n3p_mixed_realtime_source_payload_20260630_until_1453_v1", requested_until_hhmm="1453"),
            report=_report(),
            dependencies=SimpleNamespace(),
        )

        self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertEqual(payload["actual_until_hhmm"], "1453")
        self.assertEqual(payload["stock_canonical_until_hhmm"], "1453")
        self.assertEqual(payload["index_board_until_hhmm"], "1452")
        self.assertEqual(payload["stock_canonical_hhmm"], "1453")
        self.assertEqual(payload["index_board_hhmm"], "1452")
        self.assertEqual(payload["minute_delta"], 1)
        self.assertEqual(payload["alignment_status"], "independent_realtime_sources_ok")
        self.assertEqual(payload["source_minute_alignment"]["stock_canonical_hhmm"], "1453")
        self.assertEqual(payload["source_minute_alignment"]["index_board_hhmm"], "1452")
        self.assertEqual(payload["source_minute_alignment"]["minute_delta"], 1)
        self.assertEqual(payload["source_minute_alignment"]["alignment_status"], "independent_realtime_sources_ok")
        self.assertEqual(calls, ["artifact"])
        self.assertEqual(written_payloads[0]["stock_canonical_hhmm"], "1453")
        self.assertEqual(written_payloads[0]["index_board_hhmm"], "1452")
        self.assertEqual(written_payloads[0]["alignment_status"], "independent_realtime_sources_ok")
        self.assertEqual(written_reports[0]["source_minute_alignment"]["alignment_status"], "independent_realtime_sources_ok")

    def test_source_fetch_allows_non_adjacent_mixed_stock_and_index_board_canonical_minutes(self) -> None:
        from scripts.n3p_current_source_fetch_provider import (
            N3PCurrentSourceFetchBackend,
            N3PCurrentSourceFetchProvider,
            compute_n3p_current_source_payload_hash,
        )

        written_payloads: list[dict] = []

        class ScopeLoader:
            def load_n3p_current_source_scope(self, *, args, report, dependencies, config):
                return {
                    "for_trade_date": args.for_trade_date,
                    "n4_context_status": "passed",
                    "subscription_status": "passed",
                    "a1_cumulative_status": "passed",
                    "stock_quote_objects": [
                        {"asset_kind": "stock", "identity_key": "stock:SH:600000", "exchange": "SH", "code": "600000"},
                    ],
                    "index_1m_objects": [
                        {"asset_kind": "index", "identity_key": "index:SH:000001", "exchange": "SH", "code": "000001"},
                    ],
                    "board_1m_objects": [],
                    "stock_object_count": 1,
                    "index_object_count": 1,
                    "board_object_count": 0,
                    "stock_minute_bar_scope_count": 0,
                }

        class Fetcher:
            def fetch_n3p_current_market_rows(self, *, args, report, dependencies, scope, config):
                return {
                    "stock_quote_rows": [
                        {
                            "asset_kind": "stock",
                            "identity_key": "stock:SH:600000",
                            "code": "600000",
                            "price": 10.5,
                            "amount": 123456.0,
                            "source_time": "2026-06-30T09:31:04.662+08:00",
                            "source_marker": "mootdx_quotes",
                        }
                    ],
                    "index_board_1m_rows": [
                        {
                            "asset_kind": "index",
                            "identity_key": "index:SH:000001",
                            "bar_time": "2026-06-30T09:37:00+08:00",
                            "open": 1,
                            "high": 2,
                            "low": 1,
                            "close": 2,
                            "amount": 100.0,
                            "source_marker": "mootdx_index_frequency_8",
                        }
                    ],
                }

        class ArtifactWriter:
            def write_n3p_current_source_artifacts(self, **kwargs):
                payload = dict(kwargs["payload"])
                written_payloads.append(payload)
                return {"payload_hash": compute_n3p_current_source_payload_hash(payload)}

        provider = N3PCurrentSourceFetchProvider(
            backend=N3PCurrentSourceFetchBackend(
                env={"DATABASE_URL": "postgresql://unit-test"},
                scope_loader=ScopeLoader(),
                market_fetcher=Fetcher(),
                artifact_writer=ArtifactWriter(),
            )
        )

        payload = provider.fetch_n3p_current_source_payload(
            args=_args(target_run_id="n3p_mixed_realtime_source_payload_20260630_until_0937_v1", requested_until_hhmm="0937"),
            report=_report(),
            dependencies=SimpleNamespace(),
        )

        self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertEqual(payload["actual_until_hhmm"], "0937")
        self.assertEqual(payload["stock_canonical_hhmm"], "0932")
        self.assertEqual(payload["index_board_hhmm"], "0937")
        self.assertEqual(payload["minute_delta"], 5)
        self.assertEqual(payload["alignment_status"], "independent_realtime_sources_ok")
        self.assertEqual(payload["source_minute_alignment"]["stock_canonical_hhmm"], "0932")
        self.assertEqual(payload["source_minute_alignment"]["index_board_hhmm"], "0937")
        self.assertEqual(payload["source_minute_alignment"]["minute_delta"], 5)
        self.assertEqual(written_payloads[0]["stock_canonical_hhmm"], "0932")
        self.assertEqual(written_payloads[0]["index_board_hhmm"], "0937")

    def test_source_fetch_traces_non_adjacent_mixed_canonical_minutes_without_blocking(self) -> None:
        from scripts.n3p_current_source_fetch_provider import _source_canonical_minute_alignment_blocker

        payload = _source_canonical_minute_alignment_blocker(
            stock_quote_rows=[
                {
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "canonical_stock_quote_proof_time": "2026-06-30T14:55:00+08:00",
                }
            ],
            index_board_1m_rows=[
                {
                    "asset_kind": "index",
                    "identity_key": "index:SH:000001",
                    "bar_time": "2026-06-30T14:52:00+08:00",
                }
            ],
        )

        self.assertIsNone(payload)

    def test_source_fetch_classifies_midday_stock_time_stale_without_artifact_registration(self) -> None:
        from scripts.n3p_current_source_fetch_provider import _source_canonical_minute_alignment_blocker

        payload = _source_canonical_minute_alignment_blocker(
            stock_quote_rows=[
                {
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "canonical_stock_quote_proof_time": "2026-06-30T11:30:00+08:00",
                }
            ],
            index_board_1m_rows=[
                {
                    "asset_kind": "index",
                    "identity_key": "index:SH:000001",
                    "bar_time": "2026-06-30T13:00:00+08:00",
                }
            ],
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["result"], "BLOCKED_N3P_SOURCE_MIDDAY_STOCK_TIME_STALE")
        self.assertEqual(payload["reason"], "BLOCKED_N3P_SOURCE_MIDDAY_STOCK_TIME_STALE:stock_quote_servertime_stale_at_midday_wait_for_alignment")
        self.assertIn("midday_stock_quote_time_stale_wait_for_alignment", payload["blocked_reasons"])
        self.assertEqual(payload["stock_canonical_hhmm"], "1130")
        self.assertEqual(payload["index_board_hhmm"], "1300")
        self.assertEqual(payload["minute_delta"], 90)
        self.assertEqual(payload["alignment_failure_class"], "midday_stock_quote_time_stale")
        self.assertFalse(payload["artifact_written"])
        self.assertFalse(payload["source_payload_registered"])
        self.assertFalse(payload["database_written"])
        self.assertFalse(payload["writes_n3p_metric_rows"])
        self.assertFalse(payload["writes_outbox"])

    def test_source_fetch_allows_stock_quote_ceil_when_index_board_matches(self) -> None:
        from scripts.n3p_current_source_fetch_provider import (
            N3PCurrentSourceFetchBackend,
            N3PCurrentSourceFetchProvider,
            compute_n3p_current_source_payload_hash,
        )

        class ScopeLoader:
            def load_n3p_current_source_scope(self, *, args, report, dependencies, config):
                return {
                    "for_trade_date": args.for_trade_date,
                    "n4_context_status": "passed",
                    "subscription_status": "passed",
                    "a1_cumulative_status": "passed",
                    "stock_quote_objects": [
                        {"asset_kind": "stock", "identity_key": "stock:SH:600000", "exchange": "SH", "code": "600000"},
                    ],
                    "index_1m_objects": [
                        {"asset_kind": "index", "identity_key": "index:SH:000001", "exchange": "SH", "code": "000001"},
                    ],
                    "board_1m_objects": [],
                    "stock_object_count": 1,
                    "index_object_count": 1,
                    "board_object_count": 0,
                    "stock_minute_bar_scope_count": 0,
                }

        class Fetcher:
            def fetch_n3p_current_market_rows(self, *, args, report, dependencies, scope, config):
                return {
                    "stock_quote_rows": [
                        {
                            "asset_kind": "stock",
                            "identity_key": "stock:SH:600000",
                            "code": "600000",
                            "price": 10.5,
                            "amount": 123456.0,
                            "source_time": "2026-06-30T14:52:04.662+08:00",
                            "source_marker": "mootdx_quotes",
                        }
                    ],
                    "index_board_1m_rows": [
                        {
                            "asset_kind": "index",
                            "identity_key": "index:SH:000001",
                            "bar_time": "2026-06-30T14:53:00+08:00",
                            "open": 1,
                            "high": 2,
                            "low": 1,
                            "close": 2,
                            "amount": 100.0,
                            "source_marker": "mootdx_index_frequency_8",
                        }
                    ],
                }

        class ArtifactWriter:
            def write_n3p_current_source_artifacts(self, *, args, report, dependencies, payload, fetch_report, config):
                return {
                    "payload_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1453_source_fetch_payload.json",
                    "report_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1453_source_fetch_report.json",
                    "payload_hash": compute_n3p_current_source_payload_hash(payload),
                }

        backend = N3PCurrentSourceFetchBackend(
            env={"DATABASE_URL": "postgresql://unit-test"},
            scope_loader=ScopeLoader(),
            market_fetcher=Fetcher(),
            artifact_writer=ArtifactWriter(),
        )
        provider = N3PCurrentSourceFetchProvider(backend=backend)

        payload = provider.fetch_n3p_current_source_payload(
            args=_args(target_run_id="n3p_mixed_realtime_source_payload_20260630_until_1453_v1", requested_until_hhmm="1453"),
            report=_report(),
            dependencies=SimpleNamespace(),
        )

        self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertEqual(payload["proof_input_time"], "2026-06-30T14:53:00+08:00")
        self.assertEqual(payload["actual_until_hhmm"], "1453")
        stock_row = payload["stock_quote_rows"][0]
        self.assertEqual(stock_row["canonical_stock_quote_proof_minute"], "14:53")
        self.assertEqual(stock_row["canonical_stock_quote_proof_time"], "2026-06-30T14:53:00+08:00")
        self.assertEqual(stock_row["raw_source_time"], "2026-06-30T14:52:04.662000+08:00")
        self.assertEqual(payload["index_board_1m_rows"][0]["bar_time"], "2026-06-30T14:53:00+08:00")
        self.assertEqual(payload["normalization_trace"]["stock_quote_canonicalized_rows"], 1)

    def test_market_fetcher_duplicate_conflicts_fail_closed_before_artifact(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourceFetchBackend, N3PCurrentSourceFetchProvider

        calls: list[str] = []

        class ScopeLoader:
            def load_n3p_current_source_scope(self, *, args, report, dependencies, config):
                return {
                    "for_trade_date": args.for_trade_date,
                    "n4_context_status": "passed",
                    "subscription_status": "passed",
                    "a1_cumulative_status": "passed",
                    "stock_quote_objects": [],
                    "index_1m_objects": [
                        {"asset_kind": "index", "identity_key": "index:SH:000001", "exchange": "SH", "code": "000001"},
                    ],
                    "board_1m_objects": [],
                    "stock_object_count": 0,
                    "index_object_count": 1,
                    "board_object_count": 0,
                    "stock_minute_bar_scope_count": 0,
                }

        class FakeMootdxClient:
            def index_bars(self, *, symbol, frequency, start, offset):
                calls.append("fetch")
                return [
                    {"datetime": "2026-06-30 10:16", "open": 1, "high": 2, "low": 1, "close": 2, "amount": 100.0},
                    {"datetime": "2026-06-30 10:16", "open": 1, "high": 3, "low": 1, "close": 3, "amount": 101.0},
                ]

        class ArtifactWriter:
            def write_n3p_current_source_artifacts(self, **_kwargs):
                calls.append("artifact")
                return {}

        backend = N3PCurrentSourceFetchBackend(
            env={"DATABASE_URL": "postgresql://unit-test"},
            scope_loader=ScopeLoader(),
            market_fetcher=FakeMootdxClient(),
            artifact_writer=ArtifactWriter(),
        )
        provider = N3PCurrentSourceFetchProvider(backend=backend)

        payload = provider.fetch_n3p_current_source_payload(args=_args(), report=_report(), dependencies=SimpleNamespace())

        self.assertEqual(payload["result"], "BLOCKED_N3P_SOURCE_PAYLOAD_INVALID")
        self.assertIn("duplicate_object_minute_conflict", payload["blocked_reasons"])
        self.assertEqual(payload["normalization_trace"]["duplicate_conflicts"], 1)
        self.assertEqual(calls, ["fetch"])
        self.assertFalse(payload["database_written"])
        self.assertFalse(payload["writes_outbox"])

    def test_production_artifact_writer_writes_payload_and_report_with_actual_hhmm(self) -> None:
        from scripts.n3p_current_source_fetch_provider import (
            N3PCurrentSourceArtifactWriter,
            compute_n3p_current_source_payload_hash,
        )

        payload = {
            "source_model": "n3p_trigger_proof_realtime_v1",
            "source_origin": "local_mootdx_fetch_artifact",
            "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260630_until_1016_v1",
            "proof_input_time": "2026-06-30T10:16:00+08:00",
            "actual_until_hhmm": "1016",
            "for_trade_date": "20260630",
            "stock_quote_rows": [
                {
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "price": 10.5,
                    "amount": 123456.0,
                    "source_marker": "mootdx_quotes",
                }
            ],
            "index_board_1m_rows": [
                {
                    "asset_kind": "index",
                    "identity_key": "index:SH:000001",
                    "bar_time": "2026-06-30T10:16:00+08:00",
                    "open": 1,
                    "high": 2,
                    "low": 1,
                    "close": 2,
                    "amount": 100.0,
                    "source_marker": "mootdx_index_frequency_8",
                }
            ],
            "normalization_trace": {
                "raw_rows_before_filter": {"stock_quote_rows": 1, "index_board_1m_rows": 2},
                "rows_dropped_date_mismatch": 0,
                "rows_dropped_1130": 1,
                "duplicate_rows_collapsed": 0,
                "duplicate_conflicts": 0,
            },
            "writes_outbox": False,
            "writes_n3p_metric_rows": False,
            "not_n5_final_proof": True,
        }
        fetch_report = {
            "source_scope": {"stock_object_count": 1, "index_object_count": 1, "board_object_count": 0},
            "source_payload_counts": {"stock_quote_rows": 1, "index_board_1m_rows": 1},
            "proof_input_time": "2026-06-30T10:16:00+08:00",
            "actual_until_hhmm": "1016",
            "normalization_trace": payload["normalization_trace"],
            "writes_outbox": False,
            "writes_n3p_metric_rows": False,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            writer = N3PCurrentSourceArtifactWriter(output_root=tmpdir)
            result = writer.write_n3p_current_source_artifacts(
                args=_args(requested_until_hhmm="0935"),
                report={"step_id": "n3p_current_source_fetch"},
                dependencies=SimpleNamespace(),
                payload=payload,
                fetch_report=fetch_report,
                config={"database_url": "postgresql://user:" + "secret-password" + "@localhost/db"},
            )

            payload_path = Path(result["payload_path"])
            report_path = Path(result["report_path"])
            written_payload = json.loads(payload_path.read_text())
            written_report = json.loads(report_path.read_text())

        self.assertTrue(result["artifact_written"])
        self.assertTrue(str(payload_path).endswith("20260630/N3P_mixed_realtime_1016_source_fetch_payload.json"))
        self.assertTrue(str(report_path).endswith("20260630/N3P_mixed_realtime_1016_source_fetch_report.json"))
        self.assertNotIn("0935", str(payload_path))
        self.assertEqual(result["payload_hash"], compute_n3p_current_source_payload_hash(written_payload))
        self.assertEqual(written_payload["payload_hash"], result["payload_hash"])
        self.assertEqual(written_report["payload_hash"], result["payload_hash"])
        self.assertEqual(written_report["normalization_trace"], payload["normalization_trace"])
        self.assertFalse(written_report["writes_outbox"])
        self.assertFalse(written_report["writes_n3p_metric_rows"])
        self.assertFalse(written_report["database_written"])
        self.assertFalse(written_report["touches_n4_n5_n6"])
        serialized = json.dumps({"payload": written_payload, "report": written_report}, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("secret-password", serialized)
        self.assertNotIn("postgresql://", serialized)

    def test_artifact_writer_file_error_fails_closed(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourceArtifactWriter

        with tempfile.TemporaryDirectory() as tmpdir:
            root_file = Path(tmpdir) / "not_a_directory"
            root_file.write_text("blocked")
            writer = N3PCurrentSourceArtifactWriter(output_root=str(root_file))

            result = writer.write_n3p_current_source_artifacts(
                args=_args(),
                report=_report(),
                dependencies=SimpleNamespace(),
                payload={
                    "proof_input_time": "2026-06-30T10:16:00+08:00",
                    "actual_until_hhmm": "1016",
                    "for_trade_date": "20260630",
                    "stock_quote_rows": [],
                    "index_board_1m_rows": [],
                },
                fetch_report={"actual_until_hhmm": "1016"},
                config={},
            )

        self.assertEqual(result["result"], "BLOCKED_N3P_SOURCE_FETCH_BACKEND_ARTIFACT_WRITER")
        self.assertFalse(result["database_written"])
        self.assertFalse(result["writes_outbox"])

    def test_artifact_writer_is_write_once_and_reuses_same_source_hash_without_touching_bytes(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourceArtifactWriter

        payload = {
            "for_trade_date": "20260630",
            "actual_until_hhmm": "1016",
            "proof_input_time": "2026-06-30T10:16:00+08:00",
            "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260630_until_1016_v1",
            "subscription_run_id": _args().subscription_run_id,
            "n4_context_run_id": _args().n4_context_run_id,
            "stock_quote_rows": [{"identity_key": "stock:SH:600000", "price": 10}],
            "index_board_1m_rows": [{"identity_key": "index:SH:000001", "close": 3000}],
            "normalization_trace": {"attempt": 1},
        }
        fetch_report = {"actual_until_hhmm": "1016", "normalization_trace": {"attempt": 1}}
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = N3PCurrentSourceArtifactWriter(output_root=tmpdir)
            first = writer.write_n3p_current_source_artifacts(
                args=_args(), report=_report(), dependencies=SimpleNamespace(), payload=payload, fetch_report=fetch_report
            )
            payload_path = Path(first["payload_path"])
            report_path = Path(first["report_path"])
            before = {
                "payload": (payload_path.read_bytes(), payload_path.stat().st_mtime_ns, payload_path.stat().st_ino),
                "report": (report_path.read_bytes(), report_path.stat().st_mtime_ns, report_path.stat().st_ino),
            }
            changed_metadata = dict(payload)
            changed_metadata["normalization_trace"] = {"attempt": 2, "endpoint": "different-audit-metadata"}
            second = writer.write_n3p_current_source_artifacts(
                args=_args(),
                report=_report(),
                dependencies=SimpleNamespace(),
                payload=changed_metadata,
                fetch_report={"actual_until_hhmm": "1016", "normalization_trace": changed_metadata["normalization_trace"]},
            )
            after = {
                "payload": (payload_path.read_bytes(), payload_path.stat().st_mtime_ns, payload_path.stat().st_ino),
                "report": (report_path.read_bytes(), report_path.stat().st_mtime_ns, report_path.stat().st_ino),
            }

        self.assertTrue(first["artifact_written"])
        self.assertFalse(first["artifact_reused"])
        self.assertFalse(second["artifact_written"])
        self.assertTrue(second["artifact_reused"])
        self.assertEqual(second["file_sha256"], first["file_sha256"])
        self.assertEqual(after, before)

    def test_artifact_writer_blocks_different_hash_partial_symlink_and_required_missing_pair(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourceArtifactWriter

        base_payload = {
            "for_trade_date": "20260630",
            "actual_until_hhmm": "1016",
            "proof_input_time": "2026-06-30T10:16:00+08:00",
            "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260630_until_1016_v1",
            "subscription_run_id": _args().subscription_run_id,
            "n4_context_run_id": _args().n4_context_run_id,
            "stock_quote_rows": [{"identity_key": "stock:SH:600000", "price": 10}],
            "index_board_1m_rows": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = N3PCurrentSourceArtifactWriter(output_root=tmpdir)
            first = writer.write_n3p_current_source_artifacts(
                args=_args(), report=_report(), dependencies=SimpleNamespace(), payload=base_payload,
                fetch_report={"actual_until_hhmm": "1016"},
            )
            payload_file = Path(first["payload_path"])
            report_file = Path(first["report_path"])
            before_different = {
                "payload": (payload_file.read_bytes(), payload_file.stat().st_mtime_ns, payload_file.stat().st_ino),
                "report": (report_file.read_bytes(), report_file.stat().st_mtime_ns, report_file.stat().st_ino),
            }
            changed = dict(base_payload)
            changed["stock_quote_rows"] = [{"identity_key": "stock:SH:600000", "price": 11}]
            different = writer.write_n3p_current_source_artifacts(
                args=_args(), report=_report(), dependencies=SimpleNamespace(), payload=changed,
                fetch_report={"actual_until_hhmm": "1016"},
            )
            after_different = {
                "payload": (payload_file.read_bytes(), payload_file.stat().st_mtime_ns, payload_file.stat().st_ino),
                "report": (report_file.read_bytes(), report_file.stat().st_mtime_ns, report_file.stat().st_ino),
            }
            Path(first["report_path"]).unlink()
            partial = writer.write_n3p_current_source_artifacts(
                args=_args(), report=_report(), dependencies=SimpleNamespace(), payload=base_payload,
                fetch_report={"actual_until_hhmm": "1016"},
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            writer = N3PCurrentSourceArtifactWriter(output_root=tmpdir)
            date_dir = Path(tmpdir) / "20260630"
            date_dir.mkdir()
            target = date_dir / "target.json"
            target.write_text("{}", encoding="utf-8")
            payload_path = date_dir / "N3P_mixed_realtime_1016_source_fetch_payload.json"
            report_path = date_dir / "N3P_mixed_realtime_1016_source_fetch_report.json"
            payload_path.symlink_to(target)
            report_path.write_text("{}", encoding="utf-8")
            symlink = writer.write_n3p_current_source_artifacts(
                args=_args(), report=_report(), dependencies=SimpleNamespace(), payload=base_payload,
                fetch_report={"actual_until_hhmm": "1016"},
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            missing = N3PCurrentSourceArtifactWriter(output_root=tmpdir).write_n3p_current_source_artifacts(
                args=_args(), report=_report(), dependencies=SimpleNamespace(), payload=base_payload,
                fetch_report={"actual_until_hhmm": "1016", "require_existing_artifact_pair": True},
            )

        self.assertTrue(str(different["result"]).startswith("BLOCKED"))
        self.assertIn("artifact_pair_contract_mismatch", different["reason"])
        self.assertEqual(after_different, before_different)
        self.assertTrue(partial["reason"].endswith(":artifact_pair_partial"))
        self.assertTrue(symlink["reason"].endswith(":payload_artifact_symlink"))
        self.assertTrue(
            missing["reason"].endswith(
                ":existing_source_lineage_artifact_pair_missing"
            )
        )

    def test_artifact_writer_blocks_tampered_counts_self_hash_nonregular_and_create_race(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourceArtifactWriter

        base_payload = {
            "for_trade_date": "20260630",
            "actual_until_hhmm": "1016",
            "proof_input_time": "2026-06-30T10:16:00+08:00",
            "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260630_until_1016_v1",
            "subscription_run_id": _args().subscription_run_id,
            "n4_context_run_id": _args().n4_context_run_id,
            "stock_quote_rows": [{"identity_key": "stock:SH:600000", "price": 10}],
            "index_board_1m_rows": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            writer = N3PCurrentSourceArtifactWriter(output_root=tmpdir)
            first = writer.write_n3p_current_source_artifacts(
                args=_args(), report=_report(), dependencies=SimpleNamespace(), payload=base_payload,
                fetch_report={"actual_until_hhmm": "1016"},
            )
            payload_path = Path(first["payload_path"])
            report_path = Path(first["report_path"])
            payload_doc = json.loads(payload_path.read_text(encoding="utf-8"))
            report_doc = json.loads(report_path.read_text(encoding="utf-8"))
            payload_doc["source_payload_counts"] = {
                "stock_quote_rows": "not-an-integer",
                "index_board_1m_rows": 0,
            }
            payload_path.write_text(json.dumps(payload_doc, sort_keys=True), encoding="utf-8")
            import hashlib

            report_doc["file_sha256"] = hashlib.sha256(payload_path.read_bytes()).hexdigest()
            report_path.write_text(json.dumps(report_doc, sort_keys=True), encoding="utf-8")
            bad_counts = writer.write_n3p_current_source_artifacts(
                args=_args(), report=_report(), dependencies=SimpleNamespace(), payload=base_payload,
                fetch_report={"actual_until_hhmm": "1016"},
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            writer = N3PCurrentSourceArtifactWriter(output_root=tmpdir)
            first = writer.write_n3p_current_source_artifacts(
                args=_args(), report=_report(), dependencies=SimpleNamespace(), payload=base_payload,
                fetch_report={"actual_until_hhmm": "1016"},
            )
            payload_path = Path(first["payload_path"])
            report_path = Path(first["report_path"])
            payload_doc = json.loads(payload_path.read_text(encoding="utf-8"))
            report_doc = json.loads(report_path.read_text(encoding="utf-8"))
            payload_doc["payload_hash"] = "0" * 64
            payload_path.write_text(json.dumps(payload_doc, sort_keys=True), encoding="utf-8")
            report_doc["file_sha256"] = hashlib.sha256(payload_path.read_bytes()).hexdigest()
            report_path.write_text(json.dumps(report_doc, sort_keys=True), encoding="utf-8")
            bad_self_hash = writer.write_n3p_current_source_artifacts(
                args=_args(), report=_report(), dependencies=SimpleNamespace(), payload=base_payload,
                fetch_report={"actual_until_hhmm": "1016"},
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            writer = N3PCurrentSourceArtifactWriter(output_root=tmpdir)
            first = writer.write_n3p_current_source_artifacts(
                args=_args(), report=_report(), dependencies=SimpleNamespace(), payload=base_payload,
                fetch_report={"actual_until_hhmm": "1016"},
            )
            Path(first["payload_path"]).write_text("{malformed", encoding="utf-8")
            malformed = writer.write_n3p_current_source_artifacts(
                args=_args(), report=_report(), dependencies=SimpleNamespace(), payload=base_payload,
                fetch_report={"actual_until_hhmm": "1016"},
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            date_dir = Path(tmpdir) / "20260630"
            date_dir.mkdir()
            (date_dir / "N3P_mixed_realtime_1016_source_fetch_payload.json").mkdir()
            (date_dir / "N3P_mixed_realtime_1016_source_fetch_report.json").write_text("{}", encoding="utf-8")
            nonregular = N3PCurrentSourceArtifactWriter(output_root=tmpdir).write_n3p_current_source_artifacts(
                args=_args(), report=_report(), dependencies=SimpleNamespace(), payload=base_payload,
                fetch_report={"actual_until_hhmm": "1016"},
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            writer = N3PCurrentSourceArtifactWriter(output_root=tmpdir)
            date_dir = Path(tmpdir) / "20260630"
            report_path = date_dir / "N3P_mixed_realtime_1016_source_fetch_report.json"
            original_open = Path.open

            def racing_open(path, mode="r", *args, **kwargs):
                if path == report_path and mode == "xb" and not report_path.exists():
                    with original_open(report_path, "xb") as competitor:
                        competitor.write(b"competitor")
                return original_open(path, mode, *args, **kwargs)

            with patch.object(Path, "open", new=racing_open):
                raced = writer.write_n3p_current_source_artifacts(
                    args=_args(), report=_report(), dependencies=SimpleNamespace(), payload=base_payload,
                    fetch_report={"actual_until_hhmm": "1016"},
                )
            payload_path = date_dir / "N3P_mixed_realtime_1016_source_fetch_payload.json"
            competitor_bytes = report_path.read_bytes()

        self.assertIn("payload_counts_match_rows", bad_counts["reason"])
        self.assertIn("embedded_payload_hash_matches", bad_self_hash["reason"])
        self.assertIn("artifact_json_invalid", malformed["reason"])
        self.assertTrue(nonregular["reason"].endswith(":payload_artifact_not_regular_file"))
        self.assertIn("artifact_create_race", raced["reason"])
        self.assertFalse(payload_path.exists())
        self.assertEqual(competitor_bytes, b"competitor")

    def test_source_lineage_and_existing_proof_target_classifiers_fail_closed(self) -> None:
        from scripts.n3p_current_source_fetch_provider import (
            classify_existing_n3p_trigger_proof_target,
            classify_n3p_current_source_lineage,
        )

        source_snapshot = {
            "exists": True,
            "run_status": "passed",
            "p0_count": 0,
            "source_payload_hash": "a" * 64,
            "source_payload_counts": {"stock_quote_rows": 1, "index_board_1m_rows": 1},
            "source_artifact_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1016_source_fetch_payload.json",
            "expected_source_artifact_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1016_source_fetch_payload.json",
            "source_artifact_path_matches": True,
            "quality_count": 1,
            "quality_passed_count": 1,
            "quality_p0_failed_count": 0,
        }
        source_ok = classify_n3p_current_source_lineage(
            snapshot=source_snapshot,
            candidate_payload_hash="a" * 64,
            candidate_counts={"stock_quote_rows": 1, "index_board_1m_rows": 1},
        )
        source_bad = classify_n3p_current_source_lineage(
            snapshot=source_snapshot,
            candidate_payload_hash="b" * 64,
            candidate_counts={"stock_quote_rows": 1, "index_board_1m_rows": 1},
        )
        bad_path_snapshot = dict(source_snapshot)
        bad_path_snapshot.update(
            {
                "source_artifact_path": "docs/intraday_live_current/20260630/wrong.json",
                "source_artifact_path_matches": False,
            }
        )
        source_bad_path = classify_n3p_current_source_lineage(
            snapshot=bad_path_snapshot,
            candidate_payload_hash="a" * 64,
            candidate_counts={"stock_quote_rows": 1, "index_board_1m_rows": 1},
        )
        historical_overwrites = {
            "0932": (
                "9056caf78cc28507cdfd542ebabcbf987facf5b7f1d4e61d7fce604b19857759",
                "07dc56a2fb33d14520a38f0d540f19a4604413582e947bd1943e44711ab3c401",
            ),
            "0935": (
                "b9626244cc1d22260b652ac09ee4ca066c7a446b558fc5c09ec9567ee960d0ce",
                "890e9d539b367a3454e7c9f42267b4084943c40dc3a525b76d4051b053bea9dd",
            ),
        }
        for minute, (registered_hash, overwritten_hash) in historical_overwrites.items():
            with self.subTest(historical_overwrite_minute=minute):
                historical_snapshot = dict(source_snapshot)
                historical_snapshot["source_payload_hash"] = registered_hash
                historical = classify_n3p_current_source_lineage(
                    snapshot=historical_snapshot,
                    candidate_payload_hash=overwritten_hash,
                    candidate_counts={"stock_quote_rows": 1, "index_board_1m_rows": 1},
                )
                self.assertEqual(historical["decision"], "blocked")
                self.assertIn("payload_hash_matches", historical["reason"])
        source_run_id = "n3p_mixed_realtime_source_payload_20260630_until_1016_v1"
        rows_by_asset = {
            "stock": [{"metric_ready": True}],
            "index": [{"metric_ready": False}],
            "board": [],
        }
        metric = lambda count, ready: {
            "row_count": count,
            "ready_count": ready,
            "not_ready_count": count - ready,
            "min_source_snapshot_run_id": source_run_id if count else "",
            "max_source_snapshot_run_id": source_run_id if count else "",
            "min_source_subscription_run_id": _args().subscription_run_id if count else "",
            "max_source_subscription_run_id": _args().subscription_run_id if count else "",
            "min_metric_minute_label": "10:16" if count else "",
            "max_metric_minute_label": "10:16" if count else "",
        }
        target_snapshot = {
            "counts": {
                "common_market_data_run": 1,
                "stock_action_confirmation_projection_metric": 1,
                "index_action_confirmation_projection_metric": 1,
                "board_action_confirmation_projection_metric": 0,
                "common_market_data_quality_item": 1,
                "common_event_outbox": 0,
                "common_event_inbox": 0,
                "common_event_consumer_checkpoint": 0,
            },
            "run": {
                "exists": True,
                "status": "passed",
                "p0_count": 0,
                "source_scope_row_count": 2,
                "candidate_row_count": 2,
                "subscription_row_count": 2,
                "subscription_object_count": 2,
            },
            "metrics": {"stock": metric(1, 1), "index": metric(1, 0), "board": metric(0, 0)},
            "quality": {"quality_count": 1, "accepted_count": 1, "p0_failed_count": 0},
        }
        target_ok = classify_existing_n3p_trigger_proof_target(
            snapshot=target_snapshot,
            target_run_id="target",
            source_payload_run_id=source_run_id,
            subscription_run_id=_args().subscription_run_id,
            actual_until_hhmm="1016",
            rows_by_asset=rows_by_asset,
            ready_count=1,
            not_ready_count=1,
        )
        dirty_snapshot = json.loads(json.dumps(target_snapshot))
        dirty_snapshot["counts"]["common_event_outbox"] = 1
        target_bad = classify_existing_n3p_trigger_proof_target(
            snapshot=dirty_snapshot,
            target_run_id="target",
            source_payload_run_id=source_run_id,
            subscription_run_id=_args().subscription_run_id,
            actual_until_hhmm="1016",
            rows_by_asset=rows_by_asset,
            ready_count=1,
            not_ready_count=1,
        )
        dirty_row_snapshot = json.loads(json.dumps(target_snapshot))
        dirty_row_snapshot["metrics"]["stock"]["row_count"] = 2
        target_bad_row = classify_existing_n3p_trigger_proof_target(
            snapshot=dirty_row_snapshot,
            target_run_id="target",
            source_payload_run_id=source_run_id,
            subscription_run_id=_args().subscription_run_id,
            actual_until_hhmm="1016",
            rows_by_asset=rows_by_asset,
            ready_count=1,
            not_ready_count=1,
        )
        dirty_ready_snapshot = json.loads(json.dumps(target_snapshot))
        dirty_ready_snapshot["metrics"]["stock"]["ready_count"] = 0
        target_bad_ready = classify_existing_n3p_trigger_proof_target(
            snapshot=dirty_ready_snapshot,
            target_run_id="target",
            source_payload_run_id=source_run_id,
            subscription_run_id=_args().subscription_run_id,
            actual_until_hhmm="1016",
            rows_by_asset=rows_by_asset,
            ready_count=1,
            not_ready_count=1,
        )

        self.assertEqual(source_ok["decision"], "reuse_existing")
        self.assertEqual(source_bad["decision"], "blocked")
        self.assertEqual(source_bad_path["decision"], "blocked")
        self.assertIn("source_artifact_path_matches", source_bad_path["reason"])
        self.assertEqual(target_ok["decision"], "idempotent_pass")
        self.assertEqual(target_bad["decision"], "blocked")
        self.assertIn("outbox_zero", target_bad["reason"])
        self.assertIn("stock_row_count_matches", target_bad_row["reason"])
        self.assertIn("stock_ready_count_matches", target_bad_ready["reason"])

    def test_source_lineage_and_target_noop_queries_use_repeatable_read_only_transactions(self) -> None:
        from scripts.n3p_current_source_fetch_provider import (
            N3PCurrentSourceFetchBackend,
            N3PTriggerProofPreflightBackend,
        )

        transaction = "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
        self.assertIn(transaction, inspect.getsource(N3PCurrentSourceFetchBackend.load_n3p_current_source_lineage_snapshot))
        self.assertIn(transaction, inspect.getsource(N3PTriggerProofPreflightBackend.build_n3p_trigger_proof_preflight))

    def test_default_backend_artifact_writer_success_reaches_registration_blocker(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourceFetchBackend, N3PCurrentSourceFetchProvider

        class ScopeLoader:
            def load_n3p_current_source_scope(self, *, args, report, dependencies, config):
                return {
                    "for_trade_date": args.for_trade_date,
                    "n4_context_status": "passed",
                    "subscription_status": "passed",
                    "a1_cumulative_status": "passed",
                    "stock_quote_objects": [],
                    "index_1m_objects": [
                        {"asset_kind": "index", "identity_key": "index:SH:000001", "exchange": "SH", "code": "000001"},
                    ],
                    "board_1m_objects": [],
                    "stock_object_count": 0,
                    "index_object_count": 1,
                    "board_object_count": 0,
                    "stock_minute_bar_scope_count": 0,
                }

        class Fetcher:
            def fetch_n3p_current_market_rows(self, *, args, report, dependencies, scope, config):
                return {
                    "proof_input_time": "2026-06-30T10:16:00+08:00",
                    "stock_quote_rows": [],
                    "index_board_1m_rows": [
                        {
                            "asset_kind": "index",
                            "identity_key": "index:SH:000001",
                            "bar_time": "2026-06-30T10:16:00+08:00",
                            "open": 1,
                            "high": 1,
                            "low": 1,
                            "close": 1,
                            "amount": 100,
                            "source_marker": "mootdx_index_frequency_8",
                        }
                    ],
                }

        with tempfile.TemporaryDirectory() as tmpdir:
            backend = N3PCurrentSourceFetchBackend(
                config={"database_url": "postgresql://unit-test", "artifact_output_root": tmpdir},
                scope_loader=ScopeLoader(),
                market_fetcher=Fetcher(),
            )
            provider = N3PCurrentSourceFetchProvider(backend=backend)

            with patch("scripts.n3p_current_source_fetch_provider._connect_db", return_value=_FakeScopeConnection()):
                fetched = provider.fetch_n3p_current_source_payload(args=_args(), report=_report(), dependencies=SimpleNamespace())
            registered = provider.register_n3p_source_payload_run(
                args=_args(),
                report=_report(),
                dependencies=SimpleNamespace(),
                source_payload=fetched,
            )

            self.assertTrue(Path(fetched["payload_path"]).exists())
            self.assertTrue(Path(fetched["report_path"]).exists())

        self.assertEqual(fetched["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertEqual(fetched["actual_until_hhmm"], "1016")
        self.assertEqual(registered["result"], "BLOCKED_N3P_SOURCE_FETCH_BACKEND_REGISTRATION")
        self.assertFalse(registered["writes_outbox"])

    def test_default_market_fetcher_blocks_partial_scoped_object_coverage_before_artifact(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourceFetchBackend, N3PCurrentSourceFetchProvider

        calls: list[str] = []

        class ScopeLoader:
            def load_n3p_current_source_scope(self, *, args, report, dependencies, config):
                return {
                    "for_trade_date": args.for_trade_date,
                    "n4_context_status": "passed",
                    "subscription_status": "passed",
                    "a1_cumulative_status": "passed",
                    "stock_quote_objects": [
                        {"asset_kind": "stock", "identity_key": "stock:SH:600000", "exchange": "SH", "code": "600000"},
                        {"asset_kind": "stock", "identity_key": "stock:SH:600001", "exchange": "SH", "code": "600001"},
                    ],
                    "index_1m_objects": [],
                    "board_1m_objects": [],
                    "stock_object_count": 2,
                    "index_object_count": 0,
                    "board_object_count": 0,
                    "stock_minute_bar_scope_count": 0,
                }

        class FakeMootdxClient:
            def quotes(self, *, symbol):
                calls.append(f"quotes:{symbol}")
                if symbol == "600001":
                    return []
                return [{"code": symbol, "price": 10.5, "amount": 123456.0, "servertime": "10:16:00"}]

        class ArtifactWriter:
            def write_n3p_current_source_artifacts(self, **_kwargs):
                calls.append("artifact")
                return {}

        backend = N3PCurrentSourceFetchBackend(
            env={"DATABASE_URL": "postgresql://unit-test"},
            scope_loader=ScopeLoader(),
            market_fetcher=FakeMootdxClient(),
            artifact_writer=ArtifactWriter(),
        )
        provider = N3PCurrentSourceFetchProvider(backend=backend)

        payload = provider.fetch_n3p_current_source_payload(args=_args(), report=_report(), dependencies=SimpleNamespace())

        self.assertEqual(payload["result"], "BLOCKED_N3P_SOURCE_PAYLOAD_INVALID")
        self.assertIn("missing_stock_quote_objects:1", payload["blocked_reasons"])
        self.assertEqual(calls, ["quotes:600000", "quotes:600001"])
        self.assertFalse(payload["database_written"])
        self.assertFalse(payload["writes_outbox"])

    def test_market_fetch_payload_validation_fails_closed_for_unsafe_rows(self) -> None:
        from scripts.n3p_current_source_fetch_provider import validate_n3p_current_source_payload

        valid_index_row = {
            "asset_kind": "index",
            "identity_key": "index:SH:000001",
            "bar_time": "2026-06-30T10:16:00+08:00",
            "open": 1,
            "high": 2,
            "low": 1,
            "close": 2,
            "amount": 100,
            "source_marker": "mootdx_index_frequency_8",
            "trade_date": "20260630",
        }
        valid_stock_row = {
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
            "price": 10,
            "amount": 1000,
            "source_time": "2026-06-30T10:16:00+08:00",
            "source_marker": "mootdx_quotes",
            "trade_date": "20260630",
        }
        scope = {
            "stock_quote_objects": [{"identity_key": "stock:SH:600000"}],
            "index_1m_objects": [{"identity_key": "index:SH:000001"}],
            "board_1m_objects": [{"identity_key": "board:TDX:881009"}],
            "stock_object_count": 1,
            "index_object_count": 1,
            "board_object_count": 1,
        }

        validation = validate_n3p_current_source_payload(
            {
                "stock_quote_rows": [valid_stock_row],
                "index_board_1m_rows": [
                    valid_index_row,
                    dict(valid_index_row),
                    {
                        **valid_index_row,
                        "identity_key": "board:TDX:881001",
                        "bar_time": "2026-06-30T11:30:00+08:00",
                    },
                    {
                        **valid_index_row,
                        "identity_key": "board:TDX:881002",
                        "bar_time": "2026-06-30T10:17:00+08:00",
                    },
                    {
                        **valid_index_row,
                        "identity_key": "board:TDX:881003",
                        "trade_date": "20260629",
                    },
                    {
                        **valid_index_row,
                        "identity_key": "board:TDX:881004",
                        "source_marker": "synthetic_test_marker",
                    },
                ],
                "stock_minute_rows": [{"identity_key": "stock:SH:600000"}],
            },
            for_trade_date="20260630",
            proof_input_time="2026-06-30T10:16:00+08:00",
            source_scope=scope,
        )

        self.assertFalse(validation["valid"])
        self.assertIn("stock_minute_rows_forbidden", validation["blocked_reasons"])
        self.assertIn("missing_index_board_1m_objects:1", validation["blocked_reasons"])
        self.assertIn("duplicate_object_minute", validation["blocked_reasons"])
        self.assertIn("canonical_1130_forbidden", validation["blocked_reasons"])
        self.assertIn("row_after_proof_input_time", validation["blocked_reasons"])
        self.assertIn("source_trade_date_mismatch", validation["blocked_reasons"])
        self.assertIn("fake_source_marker", validation["blocked_reasons"])

    def test_concrete_backend_success_uses_actual_hhmm_and_registers_after_validation(self) -> None:
        from scripts.n3p_current_source_fetch_provider import (
            N3PCurrentSourceFetchBackend,
            N3PCurrentSourceFetchProvider,
            compute_n3p_current_source_payload_hash,
        )

        calls: list[str] = []

        class ScopeLoader:
            def load_n3p_current_source_scope(self, *, args, report, dependencies, config):
                calls.append("scope")
                return {
                    "for_trade_date": args.for_trade_date,
                    "n4_context_status": "passed",
                    "subscription_status": "passed",
                    "a1_cumulative_status": "passed",
                    "stock_object_count": 1,
                    "index_object_count": 1,
                    "board_object_count": 0,
                }

        class Fetcher:
            def fetch_n3p_current_market_rows(self, *, args, report, dependencies, scope, config):
                calls.append("fetch")
                return {
                    "proof_input_time": "2026-06-30T10:16:00+08:00",
                    "stock_quote_rows": [
                        {
                            "asset_kind": "stock",
                            "identity_key": "stock:SZ:300001",
                            "price": 10,
                            "amount": 1000,
                            "source_time": "2026-06-30T10:16:00+08:00",
                            "source_marker": "mootdx_stock_quotes",
                        }
                    ],
                    "index_board_1m_rows": [
                        {
                            "asset_kind": "index",
                            "identity_key": "index:SH:000001",
                            "bar_time": "2026-06-30T10:16:00+08:00",
                            "open": 1,
                            "high": 1,
                            "low": 1,
                            "close": 1,
                            "amount": 100,
                            "source_marker": "mootdx_index_frequency_8",
                        }
                    ],
                }

        class ArtifactWriter:
            def write_n3p_current_source_artifacts(self, *, args, report, dependencies, payload, fetch_report, config):
                calls.append("artifact")
                return {
                    "payload_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1016_source_fetch_payload.json",
                    "report_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1016_source_fetch_report.json",
                    "payload_hash": compute_n3p_current_source_payload_hash(payload),
                    "file_sha256": "file_hash",
                }

        class Registrar:
            def register_n3p_source_payload_run(self, *, args, report, dependencies, source_payload, config):
                calls.append("register")
                self.registered_run_id = source_payload["source_payload_run_id"]
                return {"database_written": True, "source_payload_registered": True}

        registrar = Registrar()
        backend = N3PCurrentSourceFetchBackend(
            env={"DATABASE_URL": "postgresql://unit-test"},
            scope_loader=ScopeLoader(),
            market_fetcher=Fetcher(),
            artifact_writer=ArtifactWriter(),
            registrar=registrar,
        )
        provider = N3PCurrentSourceFetchProvider(backend=backend)
        with patch("scripts.n3p_current_source_fetch_provider._connect_db", return_value=_FakeScopeConnection()):
            fetched = provider.fetch_n3p_current_source_payload(args=_args(), report=_report(), dependencies=SimpleNamespace())
        registered = provider.register_n3p_source_payload_run(
            args=_args(),
            report=_report(),
            dependencies=SimpleNamespace(),
            source_payload=fetched,
        )

        self.assertEqual(calls, ["scope", "fetch", "artifact", "register"])
        self.assertEqual(fetched["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertEqual(fetched["actual_until_hhmm"], "1016")
        self.assertEqual(fetched["source_payload_run_id"], "n3p_mixed_realtime_source_payload_20260630_until_1016_v1")
        self.assertEqual(fetched["source_payload_counts"], {"stock_quote_rows": 1, "index_board_1m_rows": 1})
        self.assertTrue(fetched["market_data_pulled"])
        self.assertFalse(fetched["writes_n3p_metric_rows"])
        self.assertFalse(fetched["writes_outbox"])
        self.assertTrue(registered["database_written"])
        self.assertEqual(registrar.registered_run_id, "n3p_mixed_realtime_source_payload_20260630_until_1016_v1")

    def test_missing_fetcher_and_registration_dependencies_fail_closed(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourceFetchBackend, N3PCurrentSourceFetchProvider

        class ScopeLoader:
            def load_n3p_current_source_scope(self, *, args, report, dependencies, config):
                return {
                    "for_trade_date": args.for_trade_date,
                    "n4_context_status": "passed",
                    "subscription_status": "passed",
                    "a1_cumulative_status": "passed",
                }

        backend = N3PCurrentSourceFetchBackend(
            env={"DATABASE_URL": "postgresql://unit-test"},
            scope_loader=ScopeLoader(),
            registrar=SimpleNamespace(),
        )
        provider = N3PCurrentSourceFetchProvider(backend=backend)

        fetched = provider.fetch_n3p_current_source_payload(args=_args(), report=_report(), dependencies=SimpleNamespace())
        self.assertEqual(fetched["result"], "BLOCKED_N3P_SOURCE_FETCH_BACKEND_FETCHER")

        registered = provider.register_n3p_source_payload_run(
            args=_args(),
            report=_report(),
            dependencies=SimpleNamespace(),
            source_payload={"source_payload_run_id": "n3p_mixed_realtime_source_payload_20260630_until_1016_v1"},
        )
        self.assertEqual(registered["result"], "BLOCKED_N3P_SOURCE_FETCH_BACKEND_REGISTRATION")
        self.assertFalse(registered["source_payload_registered"])
        self.assertTrue(registered["registration_attempted"])
        self.assertEqual(registered["registration_result"], "BLOCKED_N3P_SOURCE_FETCH_BACKEND_REGISTRATION")
        self.assertFalse(registered["database_written"])

    def test_default_backend_binds_mixed_realtime_source_payload_registrar(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourceFetchBackend, N3PCurrentSourceFetchProvider

        class FakeCursor:
            def __init__(self):
                self.executed: list[tuple[str, object]] = []

            def execute(self, sql, params=None):
                normalized = " ".join(str(sql).split())
                self.executed.append((normalized, params))
                return self

            def fetchone(self):
                return None

        class FakeConnection:
            def __init__(self):
                self.cursor_obj = FakeCursor()
                self.commits = 0

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def cursor(self):
                return self.cursor_obj

            def commit(self):
                self.commits += 1

        fake_conn = FakeConnection()
        backend = N3PCurrentSourceFetchBackend(env={"DATABASE_URL": "postgresql://unit-test"})
        provider = N3PCurrentSourceFetchProvider(backend=backend)
        source_payload = {
            "source_model": "n3p_trigger_proof_realtime_v1",
            "source_mode": "b1_source_returned_snapshot",
            "source_variant": "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1",
            "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260630_until_1530_v1",
            "for_trade_date": "20260630",
            "source_trade_date": "20260629",
            "proof_input_time": "2026-06-30T15:30:03.246000+08:00",
            "payload_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1530_source_fetch_payload.json",
            "report_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1530_source_fetch_report.json",
            "payload_hash": "payload_hash_1530",
            "source_artifact_file_sha256": "file_hash_1530",
            "source_scope": {"stock_object_count": 1761, "index_object_count": 9, "board_object_count": 127},
            "source_payload_counts": {"stock_quote_rows": 1761, "index_board_1m_rows": 32504},
            "stock_quote_rows": [{"identity_key": "stock:SH:600000"}],
            "index_board_1m_rows": [{"identity_key": "index:SH:000001"}],
            "writes_outbox": False,
            "writes_n3p_metric_rows": False,
            "not_n5_final_proof": True,
        }

        with patch("scripts.n3p_current_source_fetch_provider._connect_db", return_value=fake_conn):
            registered = provider.register_n3p_source_payload_run(
                args=_args(target_run_id="n3p_mixed_realtime_source_payload_20260630_until_actual_v1"),
                report=_report(),
                dependencies=SimpleNamespace(),
                source_payload=source_payload,
            )

        executed_sql = "\n".join(sql for sql, _params in fake_conn.cursor_obj.executed)
        run_insert_params = next(
            params
            for sql, params in fake_conn.cursor_obj.executed
            if "INSERT INTO common_market_data_run" in sql
        )
        self.assertEqual(registered["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertTrue(registered["source_payload_registered"])
        self.assertTrue(registered["registration_attempted"])
        self.assertEqual(registered["registration_result"], "registered")
        self.assertTrue(registered["database_written"])
        self.assertEqual(registered["source_payload_run_id"], "n3p_mixed_realtime_source_payload_20260630_until_1530_v1")
        self.assertEqual(run_insert_params[1], "condition_layer_20260629_source_20260629_for_20260630_v1")
        self.assertIn("INSERT INTO common_market_data_run", executed_sql)
        self.assertIn("INSERT INTO common_market_data_quality_item", executed_sql)
        self.assertNotIn("common_event_outbox", executed_sql)
        self.assertNotIn("action_confirmation_projection_metric", executed_sql)
        self.assertEqual(fake_conn.commits, 1)

    def test_default_registrar_captures_started_at_before_transaction_timestamp(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourcePayloadRegistrar

        transaction_now = "2026-06-30T20:58:33.731217+08:00"
        before_transaction = "2026-06-30T20:58:33.700000+08:00"
        after_transaction = "2026-06-30T20:58:33.753028+08:00"
        state = {"select_seen": False}

        class FakeCursor:
            def __init__(self):
                self.executed: list[tuple[str, object]] = []

            def execute(self, sql, params=None):
                normalized = " ".join(str(sql).split())
                self.executed.append((normalized, params))
                if "SELECT status, raw_json FROM common_market_data_run" in normalized:
                    state["select_seen"] = True
                if "INSERT INTO common_market_data_run" in normalized:
                    started_at = params[9]
                    if started_at > transaction_now:
                        raise AssertionError("common_market_data_run_check1 would reject finished_at before started_at")
                return self

            def fetchone(self):
                return None

        class FakeConnection:
            def __init__(self):
                self.cursor_obj = FakeCursor()
                self.commits = 0

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def cursor(self):
                return self.cursor_obj

            def commit(self):
                self.commits += 1

        def fake_now():
            return after_transaction if state["select_seen"] else before_transaction

        registrar = N3PCurrentSourcePayloadRegistrar()
        fake_conn = FakeConnection()
        with (
            patch("scripts.n3p_current_source_fetch_provider._connect_db", return_value=fake_conn),
            patch("scripts.n3p_current_source_fetch_provider._now_shanghai_iso", side_effect=fake_now),
        ):
            result = registrar.register_n3p_source_payload_run(
                args=_args(target_run_id="n3p_mixed_realtime_source_payload_20260630_until_actual_v1"),
                report=_report(),
                dependencies=SimpleNamespace(),
                source_payload={
                    "source_model": "n3p_trigger_proof_realtime_v1",
                    "source_mode": "b1_source_returned_snapshot",
                    "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260630_until_1530_v1",
                    "for_trade_date": "20260630",
                    "source_trade_date": "20260629",
                    "payload_hash": "payload_hash_1530",
                    "stock_quote_rows": [{"identity_key": "stock:SH:600000"}],
                    "index_board_1m_rows": [{"identity_key": "index:SH:000001"}],
                    "writes_outbox": False,
                    "writes_n3p_metric_rows": False,
                    "not_n5_final_proof": True,
                },
                config={"database_url": "postgresql://unit-test"},
            )

        run_insert_params = next(
            params
            for sql, params in fake_conn.cursor_obj.executed
            if "INSERT INTO common_market_data_run" in sql
        )
        self.assertEqual(result["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertEqual(run_insert_params[9], before_transaction)
        self.assertEqual(run_insert_params[10], before_transaction)
        self.assertEqual(result["started_at"], before_transaction)
        self.assertEqual(result["finished_at"], before_transaction)
        self.assertTrue(result["timestamp_order_valid"])
        self.assertEqual(fake_conn.commits, 1)

    def test_default_registrar_allows_same_hash_idempotent_pass(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourcePayloadRegistrar

        class FakeCursor:
            def __init__(self):
                self.executed: list[tuple[str, object]] = []

            def execute(self, sql, params=None):
                self.executed.append((" ".join(str(sql).split()), params))
                return self

            def fetchone(self):
                sql = self.executed[-1][0]
                if "SELECT status, raw_json FROM common_market_data_run" in sql:
                    return ("passed", {"source_payload_hash": "same_hash"})
                if "count(*) FROM common_event_outbox" in sql or "count(*) FROM common_event_inbox" in sql:
                    return (0,)
                if "count(*) FROM common_trigger_run" in sql or "count(*) FROM common_action_run" in sql:
                    return (0,)
                return None

        class FakeConnection:
            def __init__(self):
                self.cursor_obj = FakeCursor()
                self.commits = 0

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def cursor(self):
                return self.cursor_obj

            def commit(self):
                self.commits += 1

        registrar = N3PCurrentSourcePayloadRegistrar()
        fake_conn = FakeConnection()
        with patch("scripts.n3p_current_source_fetch_provider._connect_db", return_value=fake_conn):
            result = registrar.register_n3p_source_payload_run(
                args=_args(),
                report=_report(),
                dependencies=SimpleNamespace(),
                source_payload={
                    "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260630_until_1530_v1",
                    "source_payload_hash": "same_hash",
                    "writes_outbox": False,
                    "writes_n3p_metric_rows": False,
                },
                config={"database_url": "postgresql://unit-test"},
            )

        executed_sql = "\n".join(sql for sql, _params in fake_conn.cursor_obj.executed)
        self.assertEqual(result["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertEqual(result["registration_result"], "idempotent_pass")
        self.assertTrue(result["source_payload_registered"])
        self.assertFalse(result["database_written"])
        self.assertNotIn("INSERT INTO common_market_data_run", executed_sql)
        self.assertEqual(fake_conn.commits, 0)

    def test_default_registrar_blocks_existing_run_with_different_hash(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourcePayloadRegistrar

        class FakeCursor:
            def __init__(self):
                self.executed: list[tuple[str, object]] = []

            def execute(self, sql, params=None):
                self.executed.append((" ".join(str(sql).split()), params))
                return self

            def fetchone(self):
                if "SELECT status, raw_json FROM common_market_data_run" in self.executed[-1][0]:
                    return ("passed", {"source_payload_hash": "old_hash"})
                return None

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def cursor(self):
                return FakeCursor()

        registrar = N3PCurrentSourcePayloadRegistrar()
        with patch("scripts.n3p_current_source_fetch_provider._connect_db", return_value=FakeConnection()):
            result = registrar.register_n3p_source_payload_run(
                args=_args(),
                report=_report(),
                dependencies=SimpleNamespace(),
                source_payload={
                    "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260630_until_1530_v1",
                    "source_payload_hash": "new_hash",
                    "writes_outbox": False,
                    "writes_n3p_metric_rows": False,
                },
                config={"database_url": "postgresql://unit-test"},
            )

        self.assertEqual(result["result"], "BLOCKED_N3P_SOURCE_FETCH_BACKEND_REGISTRATION")
        self.assertEqual(result["registration_result"], "dirty_target_payload_hash_mismatch")
        self.assertFalse(result["source_payload_registered"])
        self.assertFalse(result["database_written"])

    def test_registration_is_not_called_when_payload_validation_fails(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourceFetchBackend, N3PCurrentSourceFetchProvider

        calls: list[str] = []

        class ScopeLoader:
            def load_n3p_current_source_scope(self, *, args, report, dependencies, config):
                calls.append("scope")
                return {
                    "for_trade_date": args.for_trade_date,
                    "n4_context_status": "passed",
                    "subscription_status": "passed",
                    "a1_cumulative_status": "passed",
                    "stock_object_count": 1,
                    "index_object_count": 1,
                    "board_object_count": 0,
                }

        class Fetcher:
            def fetch_n3p_current_market_rows(self, *, args, report, dependencies, scope, config):
                calls.append("fetch")
                return {
                    "proof_input_time": "2026-06-30T10:16:00+08:00",
                    "stock_quote_rows": [],
                    "index_board_1m_rows": [
                        {
                            "asset_kind": "index",
                            "identity_key": "index:SH:000001",
                            "bar_time": "2026-06-30T11:30:00+08:00",
                            "open": 1,
                            "high": 1,
                            "low": 1,
                            "close": 1,
                            "amount": 100,
                            "source_marker": "mootdx_index_frequency_8",
                        }
                    ],
                }

        class Registrar:
            def register_n3p_source_payload_run(self, **_kwargs):
                calls.append("register")
                return {"database_written": True}

        backend = N3PCurrentSourceFetchBackend(
            env={"DATABASE_URL": "postgresql://unit-test"},
            scope_loader=ScopeLoader(),
            market_fetcher=Fetcher(),
            registrar=Registrar(),
        )
        provider = N3PCurrentSourceFetchProvider(backend=backend)
        fetched = provider.fetch_n3p_current_source_payload(args=_args(), report=_report(), dependencies=SimpleNamespace())

        self.assertEqual(fetched["result"], "BLOCKED_N3P_SOURCE_PAYLOAD_INVALID")
        self.assertIn("missing_stock_quote_rows_for_scope", fetched["blocked_reasons"])
        self.assertIn("missing_index_board_1m_rows_for_scope", fetched["blocked_reasons"])
        self.assertEqual(fetched["normalization_trace"]["rows_dropped_1130"], 1)
        self.assertEqual(calls, ["scope", "fetch"])

    def test_n3p_trigger_proof_preflight_blocks_without_exact_source_run_id_before_db(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PTriggerProofPreflightBackend

        backend = N3PTriggerProofPreflightBackend(config={"database_url": "postgresql://unit-test"})
        result = backend.build_n3p_trigger_proof_preflight(
            args=_args(source_run_id="", source_payload_path="unused.json"),
            report={"step_id": "n3p_trigger_proof_preflight"},
            dependencies=SimpleNamespace(),
        )

        self.assertEqual(result["result"], "BLOCKED_SOURCE_PAYLOAD_CONTRACT")
        self.assertIn("missing_preflight_input:source_run_id", result["reason"])
        self.assertFalse(result["database_written"])
        self.assertFalse(result["market_data_pulled"])

    def test_n3p_trigger_proof_preflight_blocks_payload_hash_mismatch_before_db(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PTriggerProofPreflightBackend

        with tempfile.TemporaryDirectory() as tmpdir:
            payload_path = Path(tmpdir) / "payload.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260630_until_1530_v1",
                        "proof_input_time": "2026-06-30T15:30:03+08:00",
                        "actual_until_hhmm": "1530",
                        "payload_hash": "not_the_canonical_payload_hash",
                        "stock_quote_rows": [],
                        "index_board_1m_rows": [],
                    }
                ),
                encoding="utf-8",
            )

            backend = N3PTriggerProofPreflightBackend(config={"database_url": "postgresql://unit-test"})
            result = backend.build_n3p_trigger_proof_preflight(
                args=_args(
                    source_run_id="n3p_mixed_realtime_source_payload_20260630_until_1530_v1",
                    source_payload_path=str(payload_path),
                    target_run_id=(
                        "realtime_action_confirmation_metric_20260630_until_1530__asset_all__"
                        "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
                        "market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1"
                    ),
                ),
                report={"step_id": "n3p_trigger_proof_preflight"},
                dependencies=SimpleNamespace(),
            )

        self.assertEqual(result["result"], "BLOCKED_SOURCE_PAYLOAD_CONTRACT")
        self.assertEqual(result["reason"], "BLOCKED_SOURCE_PAYLOAD_CONTRACT:source_payload_hash_mismatch")
        self.assertNotEqual(result["expected_payload_hash"], result["observed_payload_hash"])
        self.assertFalse(result["database_written"])
        self.assertFalse(result["market_data_pulled"])

    def test_n3p_trigger_proof_preflight_blocks_post_close_payload_before_db_and_a1(self) -> None:
        from scripts.n3p_current_source_fetch_provider import (
            N3PTriggerProofPreflightBackend,
            compute_n3p_current_source_payload_hash,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            payload_path = Path(tmpdir) / "payload.json"
            payload = {
                "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260630_until_1530_v1",
                "proof_input_time": "2026-06-30T15:30:03+08:00",
                "actual_until_hhmm": "1530",
                "stock_quote_rows": [],
                "index_board_1m_rows": [],
            }
            payload["payload_hash"] = compute_n3p_current_source_payload_hash(payload)
            payload_path.write_text(json.dumps(payload), encoding="utf-8")

            backend = N3PTriggerProofPreflightBackend(config={"database_url": "postgresql://unit-test"})
            with patch("scripts.n3p_current_source_fetch_provider._connect_db", side_effect=AssertionError("DB must not be opened")):
                result = backend.build_n3p_trigger_proof_preflight(
                    args=_args(
                        source_run_id="n3p_mixed_realtime_source_payload_20260630_until_1530_v1",
                        source_payload_path=str(payload_path),
                        target_run_id=(
                            "realtime_action_confirmation_metric_20260630_until_1530__asset_all__"
                            "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
                            "market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1"
                        ),
                    ),
                    report={"step_id": "n3p_trigger_proof_preflight"},
                    dependencies=SimpleNamespace(),
                )

        self.assertEqual(result["result"], "BLOCKED_N3P_SOURCE_POST_CLOSE_PROOF_MINUTE")
        self.assertEqual(result["actual_until_hhmm"], "1530")
        self.assertEqual(result["max_canonical_proof_hhmm"], "1500")
        self.assertTrue(result["post_close_proof_minute_blocked"])
        self.assertEqual(result["source_payload_classification"], "historical_bad_source_payload")
        self.assertFalse(result["source_payload_registered"])
        self.assertFalse(result["database_written"])
        self.assertNotIn("previous_day_cumulative_row_missing", result["reason"])

    def test_n3p_trigger_proof_preflight_contract_uses_explicit_table_policy_without_writer_constants(self) -> None:
        from scripts import n3p_current_source_fetch_provider as provider

        writer_without_table_constants = SimpleNamespace()
        contract = provider._build_n3p_trigger_proof_preflight_contract(
            writer=writer_without_table_constants,
            target_run_id=(
                "realtime_action_confirmation_metric_20260630_until_1530__asset_all__"
                "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
                "market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1"
            ),
            parsed_target={"until_hhmm": "1530", "source_variant": "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1"},
            for_trade_date="20260630",
            source_trade_date="20260629",
            source_condition_run_id="condition_layer_20260629_source_20260629_for_20260630_v1",
            subscription_run_id="market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1",
            n4_context_run_id="trigger_context_snapshot_20260630_condition_layer_20260629_source_20260629_for_20260630_v1__atomic_rule_v1",
            source_payload_run_id="n3p_mixed_realtime_source_payload_20260630_until_1530_v1",
            source_previous_day_minute_run_id=(
                "previous_day_minute_preload_20260629_for_20260630__"
                "market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1"
            ),
            source_payload={"source_artifact_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1530_source_fetch_payload.json"},
            source_payload_hash="hash",
            proof_input_time="2026-06-30T15:30:03+08:00",
            context_rows=[{"asset_kind": "stock", "identity_key": "stock:SH:600000"}],
        )

        self.assertEqual(
            contract["allowed_write_tables"],
            [
                "common_market_data_run",
                "common_market_data_quality_item",
                "stock_action_confirmation_projection_metric",
                "index_action_confirmation_projection_metric",
                "board_action_confirmation_projection_metric",
            ],
        )
        forbidden = set(contract["forbidden_write_tables"])
        self.assertIn("common_event_outbox", forbidden)
        self.assertIn("common_event_inbox", forbidden)
        self.assertIn("common_event_consumer_checkpoint", forbidden)
        self.assertIn("common_trigger_run", forbidden)
        self.assertIn("common_trigger_state", forbidden)
        self.assertIn("common_trigger_match", forbidden)
        self.assertIn("common_action_run", forbidden)
        self.assertIn("common_action_event", forbidden)
        self.assertIn("stock_action_fact", forbidden)
        self.assertIn("user_signal_projection", forbidden)
        self.assertIn("user_sim_order", forbidden)
        self.assertTrue(forbidden.isdisjoint(contract["allowed_write_tables"]))
        self.assertIn(
            "stock_quote_zero_price_ohlc_volume",
            contract["expected_not_ready_blocked_reasons"],
        )
        self.assertIn(
            "formal_amount_chain_missing:",
            contract["expected_not_ready_blocked_reason_prefixes"],
        )

    def test_n3p_trigger_proof_preflight_provider_materializes_writer_artifacts(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PTriggerProofPreflightProvider

        target_run_id = (
            "realtime_action_confirmation_metric_20260701_until_0946__asset_all__"
            "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
            "market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1"
        )
        source_run_id = "n3p_mixed_realtime_source_payload_20260701_until_0946_v1"

        class Backend:
            def build_n3p_trigger_proof_preflight(self, *, args, report, dependencies):
                return {
                    "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                    "target_run_id": args.target_run_id,
                    "source_payload_run_id": args.source_run_id,
                    "source_payload_hash": "payload_hash",
                    "for_trade_date": args.for_trade_date,
                    "source_trade_date": "20260630",
                    "n4_context_run_id": args.n4_context_run_id,
                    "subscription_run_id": args.subscription_run_id,
                    "plan_only_row_counts": {"stock": 1817, "index": 18, "board": 260, "total": 2095},
                    "metric_ready": 2071,
                    "metric_not_ready": 24,
                    "target_absence": {"status": "passed", "run_rows": 0},
                    "rollback_readiness": {"status": "ready", "rollback_sql_path": "sql/rollback.sql"},
                    "not_n5_final_proof": True,
                    "writes_outbox": False,
                    "writer_contract": {
                        "result": "CONTRACT_PASS",
                        "target_run_id": args.target_run_id,
                        "source_scope": {
                            "for_trade_date": args.for_trade_date,
                            "source_trade_date": "20260630",
                            "source_payload_run_id": args.source_run_id,
                            "source_payload_hash": "payload_hash",
                            "n4_context_run_id": args.n4_context_run_id,
                            "source_subscription_run_id": args.subscription_run_id,
                            "writes_outbox": False,
                        },
                        "expected_rows": {
                            "stock": 1817,
                            "index": 18,
                            "board": 260,
                            "total": 2095,
                            "metric_ready": 2071,
                            "metric_not_ready": 24,
                        },
                        "allowed_write_tables": ["common_market_data_run"],
                        "forbidden_write_tables": ["common_event_outbox"],
                        "materialized_source_payload_overlay": {
                            "candidates": [{"identity_key": "stock:SH:600000"}],
                            "n4_context_snapshot_rows": [{"identity_key": "stock:SH:600000"}],
                            "previous_day_cumulative_rows": [{"identity_key": "stock:SH:600000", "previous_day_elapsed_amount": Decimal("123.45")}],
                            "previous_day_minute_rows": [],
                            "require_previous_day_cumulative_rows": True,
                        },
                    },
                    "writer_preflight": {"result": "PREFLIGHT_PASS"},
                }

        with tempfile.TemporaryDirectory() as tmpdir:
            contract_path = Path(tmpdir) / "contract.json"
            preflight_path = Path(tmpdir) / "preflight.json"
            args = _args(
                for_trade_date="20260701",
                source_run_id=source_run_id,
                target_run_id=target_run_id,
                n4_context_run_id="trigger_context_snapshot_20260701_condition_layer_20260630_source_20260630_for_20260701_v1__atomic_rule_v1",
                subscription_run_id="market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1",
                contract_path=str(contract_path),
                preflight_path=str(preflight_path),
            )
            payload = N3PTriggerProofPreflightProvider(backend=Backend()).build_n3p_trigger_proof_preflight(
                args=args,
                report={"step_id": "n3p_trigger_proof_preflight"},
                dependencies=SimpleNamespace(),
            )

            self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
            self.assertTrue(payload["preflight_artifacts_materialized"])
            self.assertEqual(payload["contract_path"], str(contract_path))
            self.assertEqual(payload["preflight_path"], str(preflight_path))

            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            preflight = json.loads(preflight_path.read_text(encoding="utf-8"))

        self.assertEqual(contract["target_run_id"], target_run_id)
        self.assertEqual(contract["source_scope"]["source_payload_run_id"], source_run_id)
        self.assertEqual(contract["source_scope"]["source_payload_hash"], "payload_hash")
        self.assertEqual(contract["expected_rows"]["total"], 2095)
        self.assertEqual(contract["expected_rows"]["metric_ready"], 2071)
        self.assertIn("common_event_outbox", contract["forbidden_write_tables"])
        self.assertIn("materialized_source_payload_overlay", contract)
        self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
        self.assertEqual(preflight["target_run_id"], target_run_id)
        self.assertEqual(preflight["source_payload_run_id"], source_run_id)
        self.assertEqual(preflight["plan_only_row_counts"]["total"], 2095)
        self.assertEqual(preflight["metric_ready"], 2071)
        self.assertEqual(preflight["metric_not_ready"], 24)
        self.assertEqual(preflight["target_absence"]["status"], "passed")
        self.assertFalse(preflight["writes_outbox"])
        self.assertTrue(preflight["not_n5_final_proof"])

    def test_n3p_trigger_proof_preflight_provider_preserves_exact_target_noop_without_artifacts(self) -> None:
        from scripts.n3p_current_source_fetch_provider import (
            N3PTriggerProofPreflightProvider,
            N3P_TRIGGER_PROOF_IDEMPOTENT_NOOP_REASON,
            N3P_TRIGGER_PROOF_IDEMPOTENT_NOOP_RESULT,
        )

        class Backend:
            def build_n3p_trigger_proof_preflight(self, *, args, report, dependencies):
                del report, dependencies
                return {
                    "result": N3P_TRIGGER_PROOF_IDEMPOTENT_NOOP_RESULT,
                    "status": "noop",
                    "execution_mode": "noop",
                    "idempotency_decision": "idempotent_pass",
                    "reason": N3P_TRIGGER_PROOF_IDEMPOTENT_NOOP_REASON,
                    "target_run_id": args.target_run_id,
                    "source_payload_run_id": args.source_run_id,
                    "target_idempotency": {
                        "decision": "idempotent_pass",
                        "reason": N3P_TRIGGER_PROOF_IDEMPOTENT_NOOP_REASON,
                        "checks": {"run_status_passed": True},
                    },
                    "preflight_artifacts_materialized": False,
                    "execute_contract_ready": False,
                    "database_written": False,
                    "market_data_pulled": False,
                    "writes_n3p_metric_rows": False,
                    "writes_outbox": False,
                }

        with tempfile.TemporaryDirectory() as tmpdir:
            contract_path = Path(tmpdir) / "contract.json"
            preflight_path = Path(tmpdir) / "preflight.json"
            payload = N3PTriggerProofPreflightProvider(backend=Backend()).build_n3p_trigger_proof_preflight(
                args=_args(
                    source_run_id="n3p_mixed_realtime_source_payload_20260701_until_0946_v1",
                    target_run_id="target",
                    contract_path=str(contract_path),
                    preflight_path=str(preflight_path),
                ),
                report={"step_id": "n3p_trigger_proof_preflight"},
                dependencies=SimpleNamespace(),
            )

            self.assertFalse(contract_path.exists())
            self.assertFalse(preflight_path.exists())

        self.assertEqual(payload["status"], "noop")
        self.assertEqual(payload["idempotency_decision"], "idempotent_pass")
        self.assertFalse(payload["preflight_artifacts_materialized"])
        self.assertFalse(payload["database_written"])

    def test_n3p_trigger_proof_preflight_provider_blocks_missing_artifact_paths(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PTriggerProofPreflightProvider

        class Backend:
            def build_n3p_trigger_proof_preflight(self, *, args, report, dependencies):
                return {
                    "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                    "target_run_id": args.target_run_id,
                    "source_payload_run_id": args.source_run_id,
                    "writer_contract": {"target_run_id": args.target_run_id},
                    "writer_preflight": {"result": "PREFLIGHT_PASS"},
                }

        payload = N3PTriggerProofPreflightProvider(backend=Backend()).build_n3p_trigger_proof_preflight(
            args=_args(
                source_run_id="n3p_mixed_realtime_source_payload_20260701_until_0946_v1",
                contract_path="",
                preflight_path="",
            ),
            report={"step_id": "n3p_trigger_proof_preflight"},
            dependencies=SimpleNamespace(),
        )

        self.assertEqual(payload["result"], "BLOCKED_N3P_PREFLIGHT_ARTIFACT_MATERIALIZATION")
        self.assertIn("contract_path", payload["reason"])
        self.assertFalse(payload["database_written"])
        self.assertFalse(payload["market_data_pulled"])
        self.assertFalse(payload["writes_outbox"])

    def test_n3p_trigger_proof_preflight_provider_blocks_artifact_write_failure(self) -> None:
        from scripts.n3p_current_source_fetch_provider import N3PTriggerProofPreflightProvider

        class Backend:
            def build_n3p_trigger_proof_preflight(self, *, args, report, dependencies):
                return {
                    "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                    "target_run_id": args.target_run_id,
                    "source_payload_run_id": args.source_run_id,
                    "writer_contract": {
                        "target_run_id": args.target_run_id,
                        "source_scope": {
                            "source_payload_run_id": args.source_run_id,
                            "source_payload_hash": "payload_hash",
                        },
                    },
                    "writer_preflight": {"result": "PREFLIGHT_PASS"},
                }

        with tempfile.TemporaryDirectory() as tmpdir:
            contract_path = Path(tmpdir) / "contract_as_directory"
            contract_path.mkdir()
            preflight_path = Path(tmpdir) / "preflight.json"

            payload = N3PTriggerProofPreflightProvider(backend=Backend()).build_n3p_trigger_proof_preflight(
                args=_args(
                    source_run_id="n3p_mixed_realtime_source_payload_20260701_until_0946_v1",
                    contract_path=str(contract_path),
                    preflight_path=str(preflight_path),
                ),
                report={"step_id": "n3p_trigger_proof_preflight"},
                dependencies=SimpleNamespace(),
            )

        self.assertEqual(payload["result"], "BLOCKED_N3P_PREFLIGHT_ARTIFACT_MATERIALIZATION")
        self.assertIn("artifact_write_failed", payload["reason"])
        self.assertFalse(payload["database_written"])
        self.assertFalse(payload["market_data_pulled"])
        self.assertFalse(payload["writes_outbox"])
