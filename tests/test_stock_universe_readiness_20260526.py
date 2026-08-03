import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ashare_v3.ingestion.stock_universe_readiness_20260526 import (
    DAILY_MISSING_ACTIVE_IDENTITIES,
    DefaultMootdxStockDailyProbe,
    STALE_IDENTITY_KEY,
    SUPERSEDED_BY_IDENTITY_KEY,
    TRADE_DATE,
    build_readiness_report,
)
from ashare_v3.mootdx_client import EndpointConfig, MootdxEndpointManager


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "plan_stock_universe_readiness_20260526.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("n1_stock_universe_readiness_20260526", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def identity_row(identity_key: str, *, name: str = "样本", is_st: bool = False, source: str = "tushare.stock_basic") -> dict:
    _, exchange, code = identity_key.split(":")
    return {
        "stock_identity_key": identity_key,
        "identity_key": identity_key,
        "ts_code": f"{code}.{exchange}",
        "code": code,
        "exchange": exchange,
        "name": name,
        "listed_date": "20200101",
        "delisted_date": None,
        "is_st": is_st,
        "status": "active",
        "source": source,
        "source_version": "stock_identity_20260526_v1",
    }


def base_db_snapshot() -> dict:
    stock_rows = [identity_row(key, is_st=("*ST" in key)) for key in DAILY_MISSING_ACTIVE_IDENTITIES]
    stock_rows.append(
        identity_row(
            STALE_IDENTITY_KEY,
            name="中航成飞",
            source="tushare.namechange+bak_basic.identity_supplement",
        )
    )
    stock_rows.append(identity_row(SUPERSEDED_BY_IDENTITY_KEY, name="中航成飞"))
    return {
        "trade_date": TRADE_DATE,
        "raw_active_universe": 5523,
        "candidate_rows": stock_rows,
        "read_only_database_checks": True,
    }


def base_tushare_snapshot() -> dict:
    daily_present = []
    adj_present = [key_to_ts_code(key) for key in DAILY_MISSING_ACTIVE_IDENTITIES]
    stock_basic = {
        key_to_ts_code(key): {"ts_code": key_to_ts_code(key), "list_status": "L", "name": "样本"}
        for key in DAILY_MISSING_ACTIVE_IDENTITIES
    }
    stock_basic[key_to_ts_code(SUPERSEDED_BY_IDENTITY_KEY)] = {
        "ts_code": key_to_ts_code(SUPERSEDED_BY_IDENTITY_KEY),
        "list_status": "L",
        "name": "中航成飞",
    }
    return {
        "trade_date": TRADE_DATE,
        "daily_present_ts_codes": daily_present,
        "adj_factor_present_ts_codes": adj_present,
        "stock_basic_by_ts_code": stock_basic,
        "source": "tushare.readonly",
    }


def key_to_ts_code(identity_key: str) -> str:
    _, exchange, code = identity_key.split(":")
    return f"{code}.{exchange}"


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


def make_endpoint_manager(cache_path):
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
        n1_failover_mode="observe",
        n3_failover_mode="observe",
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


class StockUniverseReadiness20260526Tests(unittest.TestCase):
    def test_default_probe_uses_shared_manager_and_freezes_endpoint_provenance(self) -> None:
        candidates = [identity_row(key) for key in DAILY_MISSING_ACTIVE_IDENTITIES[:3]]
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
            for row in candidates
        }
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeMootdxClient(rows_by_symbol)
            factory_calls = []
            probe = DefaultMootdxStockDailyProbe(
                endpoint_manager=make_endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=passing_endpoint_probe,
                client_factory=lambda selection, profile: factory_calls.append(
                    (selection, profile)
                )
                or client,
                attempt_id="readiness-attempt",
            )

            snapshot = probe.fetch_snapshot(candidates=candidates, trade_date=TRADE_DATE)

        self.assertTrue(snapshot["source_available"])
        self.assertEqual(len(factory_calls), 1)
        self.assertEqual(factory_calls[0][0].server, ("115.238.56.198", 7709))
        provenance = snapshot["mootdx_endpoint_provenance"]
        self.assertEqual(provenance["endpoint_pool_version"], "test-pool-v1")
        self.assertEqual(provenance["endpoint_id"], "primary")
        self.assertEqual(provenance["attempt_id"], "readiness-attempt")
        first = snapshot["presence_by_identity_key"][candidates[0]["identity_key"]]
        self.assertEqual(
            first["evidence"]["mootdx_endpoint_provenance"]["endpoint_id"],
            "primary",
        )

    def test_readiness_observe_failure_records_secondary_without_business_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            factory_calls = []

            def endpoint_probe(endpoint, make_client):
                del make_client
                return {
                    "checks": {
                        "stock_quote": True,
                        "stock_daily_bars": True,
                        "index_daily_bars": True,
                        "scope_sentinels": endpoint.endpoint_id == "secondary",
                    }
                }

            endpoint_manager_instance = make_endpoint_manager(Path(tmp) / "health.json")
            probe = DefaultMootdxStockDailyProbe(
                endpoint_manager=endpoint_manager_instance,
                endpoint_probe=endpoint_probe,
                client_factory=lambda selection, profile: factory_calls.append(
                    (selection, profile)
                ),
                attempt_id="readiness-observe",
            )
            snapshot = probe.fetch_snapshot(
                candidates=[identity_row(DAILY_MISSING_ACTIVE_IDENTITIES[0])],
                trade_date=TRADE_DATE,
            )

        self.assertFalse(snapshot["source_available"])
        self.assertEqual(factory_calls, [])
        self.assertEqual(
            snapshot["mootdx_endpoint_provenance"]["would_switch_to"],
            "secondary",
        )

    def test_readiness_three_empty_objects_discards_all_partial_presence(self) -> None:
        candidates = [identity_row(key) for key in DAILY_MISSING_ACTIVE_IDENTITIES[:3]]
        with tempfile.TemporaryDirectory() as tmp:
            probe = DefaultMootdxStockDailyProbe(
                endpoint_manager=make_endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=passing_endpoint_probe,
                client_factory=lambda selection, profile: FakeMootdxClient({}),
                attempt_id="readiness-empty",
            )
            snapshot = probe.fetch_snapshot(candidates=candidates, trade_date=TRADE_DATE)

        self.assertFalse(snapshot["source_available"])
        self.assertEqual(snapshot["presence_by_identity_key"], {})
        self.assertIn("complete readiness attempt discarded", snapshot["source_unavailable_reason"])

    def test_readiness_repeated_empty_identity_does_not_open_circuit(self) -> None:
        repeated = identity_row(DAILY_MISSING_ACTIVE_IDENTITIES[0])
        with tempfile.TemporaryDirectory() as tmp:
            probe = DefaultMootdxStockDailyProbe(
                endpoint_manager=make_endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=passing_endpoint_probe,
                client_factory=lambda selection, profile: FakeMootdxClient({}),
                attempt_id="readiness-repeat-empty",
            )
            snapshot = probe.fetch_snapshot(
                candidates=[dict(repeated) for _ in range(3)],
                trade_date=TRADE_DATE,
            )

        self.assertTrue(snapshot["source_available"])
        self.assertEqual(
            snapshot["presence_by_identity_key"][repeated["identity_key"]]["present"],
            False,
        )

    def test_readiness_tdxpy_flag_binds_preflight_fetch_and_provenance(self) -> None:
        candidates = [identity_row(key) for key in DAILY_MISSING_ACTIVE_IDENTITIES[:3]]
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
            for row in candidates
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

            def endpoint_probe(endpoint, make_client):
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
            probe = DefaultMootdxStockDailyProbe(
                endpoint_manager=endpoint_manager_instance,
                endpoint_probe=endpoint_probe,
                transport_factory=transport_factory,
                quote_transport="tdxpy",
                attempt_id="readiness-tdxpy",
            )
            with patch.object(
                endpoint_manager_instance,
                "record_required_object_result",
                wraps=endpoint_manager_instance.record_required_object_result,
            ) as record_result:
                snapshot = probe.fetch_snapshot(
                    candidates=candidates,
                    trade_date=TRADE_DATE,
                )

        self.assertTrue(snapshot["source_available"])
        self.assertEqual(
            [call[:4] for call in factory_calls],
            [
                ("tdxpy", "tdxpy", "mandatory_protocol_preflight_probe", "primary"),
                ("tdxpy", "tdxpy", "mandatory_protocol_preflight_probe", "secondary"),
                ("tdxpy", "tdxpy", "stable_priority_primary_healthy", "primary"),
            ],
        )
        self.assertEqual(
            snapshot["mootdx_endpoint_provenance"]["transport"],
            "tdxpy",
        )
        self.assertTrue(
            all(
                call.kwargs["transport"] == "tdxpy"
                for call in record_result.call_args_list
            )
        )
        self.assertEqual(
            [
                row["endpoint_id"]
                for row in snapshot["mootdx_endpoint_provenance"][
                    "endpoint_probe_results"
                ]
            ],
            ["primary", "secondary"],
        )
        self.assertEqual(snapshot["source"], "mootdx.stock_daily.readonly")

    def test_readiness_tdxpy_failure_records_actual_transport(self) -> None:
        class FailingClient:
            def bars(self, **kwargs):
                raise TimeoutError("fake tdxpy failure")

        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager_instance = make_endpoint_manager(Path(tmp) / "health.json")
            probe = DefaultMootdxStockDailyProbe(
                endpoint_manager=endpoint_manager_instance,
                endpoint_probe=passing_endpoint_probe,
                transport_factory=lambda selection, profile, *, transport: FailingClient(),
                quote_transport="tdxpy",
            )
            with patch.object(
                endpoint_manager_instance,
                "record_transport_failure",
                wraps=endpoint_manager_instance.record_transport_failure,
            ) as record_failure:
                snapshot = probe.fetch_snapshot(
                    candidates=[identity_row(DAILY_MISSING_ACTIVE_IDENTITIES[0])],
                    trade_date=TRADE_DATE,
                )

        self.assertFalse(snapshot["source_available"])
        self.assertEqual(record_failure.call_count, 1)
        self.assertEqual(record_failure.call_args.kwargs["transport"], "tdxpy")

    def test_readiness_closes_business_client_once_after_success(self) -> None:
        class ClosingClient(FakeMootdxClient):
            def __init__(self, rows_by_symbol):
                super().__init__(rows_by_symbol)
                self.close_count = 0

            def close(self):
                self.close_count += 1

        candidate = identity_row(DAILY_MISSING_ACTIVE_IDENTITIES[0])
        client = ClosingClient(
            {
                candidate["code"]: [
                    {
                        "datetime": "2026-05-26 00:00:00",
                        "open": "10",
                        "high": "11",
                        "low": "9",
                        "close": "10.5",
                    }
                ]
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            probe = DefaultMootdxStockDailyProbe(
                endpoint_manager=make_endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=passing_endpoint_probe,
                client_factory=lambda selection, profile: client,
            )
            snapshot = probe.fetch_snapshot(
                candidates=[candidate],
                trade_date=TRADE_DATE,
            )
            probe.close()

        self.assertTrue(snapshot["source_available"])
        self.assertEqual(client.close_count, 1)

    def test_readiness_close_failure_discards_snapshot_and_traces_error(self) -> None:
        class CloseFailClient(FakeMootdxClient):
            def close(self):
                raise RuntimeError("fake close failure")

        candidate = identity_row(DAILY_MISSING_ACTIVE_IDENTITIES[0])
        client = CloseFailClient(
            {
                candidate["code"]: [
                    {
                        "datetime": "2026-05-26 00:00:00",
                        "open": "10",
                        "high": "11",
                        "low": "9",
                        "close": "10.5",
                    }
                ]
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            probe = DefaultMootdxStockDailyProbe(
                endpoint_manager=make_endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=passing_endpoint_probe,
                client_factory=lambda selection, profile: client,
            )
            snapshot = probe.fetch_snapshot(
                candidates=[candidate],
                trade_date=TRADE_DATE,
            )

        self.assertFalse(snapshot["source_available"])
        self.assertEqual(snapshot["presence_by_identity_key"], {})
        self.assertIn("close failed", snapshot["source_unavailable_reason"])
        self.assertEqual(
            snapshot["mootdx_endpoint_provenance"]["business_client_close_error"],
            "RuntimeError",
        )

    def test_report_blocks_unresolved_source_gaps_and_marks_stale_identity(self) -> None:
        tdx_snapshot = {
            "source_available": True,
            "presence_by_identity_key": {},
            "source": "mootdx.stock_daily.readonly",
        }

        report = build_readiness_report(
            db_snapshot=base_db_snapshot(),
            tushare_snapshot=base_tushare_snapshot(),
            tdx_snapshot=tdx_snapshot,
        )

        self.assertEqual(report["result"], "READINESS_BLOCKED")
        self.assertEqual(report["raw_active_universe"], 5523)
        self.assertEqual(report["effective_active_universe"], 5522)
        self.assertEqual(report["tushare_daily_matched"], 5504)
        self.assertEqual(report["unresolved_daily_missing_active"], 18)
        self.assertEqual(report["quality"]["p0_count"], 18)
        self.assertGreaterEqual(report["quality"]["p1_count"], 1)
        self.assertEqual(
            report["stale_identity_candidates"][0]["superseded_by_identity_key"],
            SUPERSEDED_BY_IDENTITY_KEY,
        )

    def test_report_allows_v2_contract_when_all_missing_have_tdx_supplement(self) -> None:
        tdx_snapshot = {
            "source_available": True,
            "presence_by_identity_key": {
                identity_key: {"present": True, "source": "mootdx.stock_daily", "evidence": {"trade_date": TRADE_DATE}}
                for identity_key in DAILY_MISSING_ACTIVE_IDENTITIES
            },
            "source": "mootdx.stock_daily.readonly",
        }

        report = build_readiness_report(
            db_snapshot=base_db_snapshot(),
            tushare_snapshot=base_tushare_snapshot(),
            tdx_snapshot=tdx_snapshot,
        )

        self.assertEqual(report["result"], "READINESS_PASS")
        self.assertEqual(report["expected_daily_bar_scope"]["stock"], 5522)
        self.assertEqual(report["unresolved_daily_missing_active"], 0)
        self.assertEqual(report["supplemental_source_available"], 18)
        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertEqual(report["quality"]["p1_count"], 19)

    def test_tdx_unavailable_keeps_gate_blocked(self) -> None:
        tdx_snapshot = {
            "source_available": False,
            "source_unavailable_reason": "mootdx import failed",
            "presence_by_identity_key": {},
            "source": "mootdx.stock_daily.readonly",
        }

        report = build_readiness_report(
            db_snapshot=base_db_snapshot(),
            tushare_snapshot=base_tushare_snapshot(),
            tdx_snapshot=tdx_snapshot,
        )

        self.assertEqual(report["result"], "READINESS_BLOCKED")
        self.assertIn("tdx_mootdx_unavailable", report["blockers"])
        self.assertGreaterEqual(report["quality"]["p0_count"], 1)

    def test_cli_execute_is_rejected_before_dependencies_run(self) -> None:
        runner = load_runner_module()
        called = {"planner": False}

        def forbidden_planner(*args, **kwargs):
            called["planner"] = True
            return {}

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = runner.main(["--execute"], dependencies={"run_planner": forbidden_planner})

        self.assertEqual(result, 2)
        self.assertFalse(called["planner"])

    def test_cli_writes_json_and_markdown_report_with_injected_planner(self) -> None:
        runner = load_runner_module()
        report = build_readiness_report(
            db_snapshot=base_db_snapshot(),
            tushare_snapshot=base_tushare_snapshot(),
            tdx_snapshot={"source_available": True, "presence_by_identity_key": {}, "source": "mootdx.stock_daily.readonly"},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "report.json"
            md_path = Path(tmpdir) / "report.md"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = runner.main(
                    ["--json-path", str(json_path), "--md-path", str(md_path), "--json"],
                    dependencies={"run_planner": lambda **kwargs: report},
                )

            self.assertEqual(result, 0)
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            parsed = json.loads(json_path.read_text())
            self.assertEqual(parsed["result"], "READINESS_BLOCKED")
            self.assertIn("READINESS_BLOCKED", md_path.read_text())
            self.assertEqual(json.loads(stdout.getvalue())["result"], "READINESS_BLOCKED")


if __name__ == "__main__":
    unittest.main()
