import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from ashare_v3.ingestion.daily_bars import BoardDailySymbol, IndexDailySymbol
from ashare_v3.ingestion.mootdx_daily_source import (
    MootdxDailyBarSource,
    MootdxDailyBarSourceError,
    _deterministic_sentinels,
)
from ashare_v3.mootdx_client import EndpointConfig, MootdxEndpointManager


class FakeFrame:
    def __init__(self, rows):
        self._rows = rows

    def to_dict(self, orient="records"):
        if orient != "records":
            raise AssertionError(f"unexpected orient: {orient}")
        return list(self._rows)


class FakeMootdxClient:
    def __init__(self, rows=None):
        self.index_calls = []
        self._rows = rows

    def index(self, **kwargs):
        self.index_calls.append(kwargs)
        if self._rows is not None:
            return FakeFrame(self._rows)
        return FakeFrame(
            [
                {
                    "datetime": "2026-05-20 00:00:00",
                    "open": "1",
                    "high": "2",
                    "low": "1",
                    "close": "2",
                    "vol": "10",
                    "amount": "20",
                },
                {
                    "datetime": "2026-05-21 00:00:00",
                    "open": "3",
                    "high": "4",
                    "low": "3",
                    "close": "4",
                    "vol": "30",
                    "amount": "40",
                },
            ]
        )


class FailingMootdxClient:
    def index(self, **kwargs):
        raise TimeoutError("fake transport failure")


def endpoint_manager(cache_path):
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


def passing_probe(endpoint, make_client):
    del endpoint, make_client
    return {
        "checks": {
            "stock_quote": True,
            "stock_daily_bars": True,
            "index_daily_bars": True,
            "scope_sentinels": True,
        }
    }


class MootdxDailySourceTest(unittest.TestCase):
    def test_fetch_index_and_board_daily_bars_enriches_and_filters_rows(self) -> None:
        client = FakeMootdxClient()
        source = MootdxDailyBarSource(client=client, frequency=9, offset=800)

        index_rows = source.fetch_index_daily_bars(
            indexes=[IndexDailySymbol(code="000001", exchange="SH", name="上证指数")],
            start_date="20260521",
            end_date="20260521",
        )
        board_rows = source.fetch_board_daily_bars(
            boards=[BoardDailySymbol(board_code="881002", board_name="煤炭开采", board_type="tdx_industry")],
            start_date="20260521",
            end_date="20260521",
        )

        self.assertEqual(len(index_rows), 1)
        self.assertEqual(len(board_rows), 1)
        self.assertEqual(index_rows[0]["code"], "000001")
        self.assertEqual(index_rows[0]["exchange"], "SH")
        self.assertEqual(board_rows[0]["board_code"], "881002")
        self.assertEqual(board_rows[0]["board_type"], "tdx_industry")
        self.assertEqual([call["symbol"] for call in client.index_calls], ["000001", "881002"])
        self.assertEqual(client.index_calls[0]["frequency"], 9)

    def test_shared_manager_pins_primary_and_adds_complete_provenance_to_raw_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeMootdxClient()
            factory_calls = []
            source = MootdxDailyBarSource(
                endpoint_manager=endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=passing_probe,
                client_factory=lambda selection, profile: factory_calls.append(
                    (selection, profile)
                )
                or client,
                attempt_id="source-attempt-1",
                frequency=9,
                offset=800,
            )

            rows = source.fetch_board_daily_bars(
                boards=[
                    BoardDailySymbol(
                        board_code="881002",
                        board_name="煤炭开采",
                        board_type="tdx_industry",
                    )
                ],
                start_date="20260521",
                end_date="20260521",
            )

        self.assertEqual(len(factory_calls), 1)
        selection, profile = factory_calls[0]
        self.assertEqual(selection.server, ("115.238.56.198", 7709))
        self.assertEqual(profile, "std")
        provenance = rows[0]["mootdx_endpoint_provenance"]
        self.assertEqual(provenance["endpoint_pool_version"], "test-pool-v1")
        self.assertEqual(provenance["endpoint_id"], "primary")
        self.assertEqual(provenance["transport"], "mootdx")
        self.assertEqual(provenance["source_transport"], "mootdx")
        self.assertEqual(provenance["attempt_id"], "source-attempt-1")
        self.assertEqual(provenance["selection_reason"], "stable_priority_primary_healthy")
        self.assertFalse(provenance["failover_performed"])

    def test_injected_selection_reuses_client_without_reselecting_and_preserves_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager_instance = endpoint_manager(Path(tmp) / "health.json")
            selection = endpoint_manager_instance.select_for_run(
                run_id="bundle",
                attempt_id="bundle-attempt",
                probe=passing_probe,
            )
            client = FakeMootdxClient()
            source = MootdxDailyBarSource(
                client=client,
                endpoint_manager=endpoint_manager_instance,
                endpoint_probe=lambda endpoint, make_client: self.fail(
                    "injected pinned source must not reselect"
                ),
                selection=selection,
            )

            rows = source.fetch_board_daily_bars(
                boards=[
                    BoardDailySymbol(
                        board_code="881002",
                        board_name="煤炭开采",
                        board_type="tdx_industry",
                    )
                ],
                start_date="20260521",
                end_date="20260521",
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["mootdx_endpoint_provenance"]["attempt_id"],
            "bundle-attempt",
        )
        self.assertEqual(
            rows[0]["mootdx_endpoint_provenance"]["endpoint_id"],
            "primary",
        )

    def test_observe_mode_primary_failure_records_would_switch_and_creates_no_client(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            factory_calls = []

            def probe(endpoint, make_client):
                del make_client
                checks = {
                    "stock_quote": True,
                    "stock_daily_bars": True,
                    "index_daily_bars": True,
                    "scope_sentinels": endpoint.endpoint_id == "secondary",
                }
                return {"checks": checks}

            source = MootdxDailyBarSource(
                endpoint_manager=endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=probe,
                client_factory=lambda selection, profile: factory_calls.append(
                    (selection, profile)
                ),
                attempt_id="source-attempt-observe",
            )

            with self.assertRaisesRegex(
                MootdxDailyBarSourceError,
                "would_switch_to=secondary",
            ):
                source.fetch_board_daily_bars(
                    boards=[
                        BoardDailySymbol(
                            board_code="881002",
                            board_name="煤炭开采",
                            board_type="tdx_industry",
                        )
                    ],
                    start_date="20260521",
                    end_date="20260521",
                )

        self.assertEqual(factory_calls, [])
        self.assertEqual(source.endpoint_provenance["would_switch_to"], "secondary")
        self.assertFalse(source.endpoint_provenance["selectable"])

    def test_runtime_failure_marks_attempt_would_retry_without_fetching_secondary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            factory_calls = []
            source = MootdxDailyBarSource(
                endpoint_manager=endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=passing_probe,
                client_factory=lambda selection, profile: factory_calls.append(
                    selection.endpoint_id
                )
                or FailingMootdxClient(),
                attempt_id="runtime-failure-attempt",
            )

            with self.assertRaisesRegex(
                MootdxDailyBarSourceError,
                "transport failure",
            ):
                source.fetch_board_daily_bars(
                    boards=[
                        BoardDailySymbol(
                            board_code="881001",
                            board_name="行业",
                            board_type="tdx_industry",
                        )
                    ],
                    start_date="20260521",
                    end_date="20260521",
                )

        self.assertEqual(factory_calls, ["primary"])
        self.assertTrue(source.endpoint_provenance["would_retry"])
        self.assertEqual(
            source.endpoint_provenance["retry_reason"],
            "source_fetch_transport_exception",
        )

    def test_tdxpy_runtime_failure_records_actual_transport(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager_instance = endpoint_manager(Path(tmp) / "health.json")
            with patch.object(
                endpoint_manager_instance,
                "record_transport_failure",
                wraps=endpoint_manager_instance.record_transport_failure,
            ) as record_failure:
                source = MootdxDailyBarSource(
                    endpoint_manager=endpoint_manager_instance,
                    endpoint_probe=passing_probe,
                    transport_factory=lambda selection, profile, *, transport: (
                        FailingMootdxClient()
                    ),
                    quote_transport="tdxpy",
                )
                with self.assertRaises(MootdxDailyBarSourceError):
                    source.fetch_board_daily_bars(
                        boards=[
                            BoardDailySymbol(
                                board_code="881001",
                                board_name="行业",
                                board_type="tdx_industry",
                            )
                        ],
                        start_date="20260521",
                        end_date="20260521",
                    )

        self.assertEqual(record_failure.call_count, 1)
        self.assertEqual(record_failure.call_args.kwargs["transport"], "tdxpy")

    def test_close_releases_pinned_business_client_once(self) -> None:
        class ClosingClient(FakeMootdxClient):
            def __init__(self):
                super().__init__()
                self.close_count = 0

            def close(self):
                self.close_count += 1

        with tempfile.TemporaryDirectory() as tmp:
            client = ClosingClient()
            source = MootdxDailyBarSource(
                endpoint_manager=endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=passing_probe,
                client_factory=lambda selection, profile: client,
            )
            source.fetch_board_daily_bars(
                boards=[
                    BoardDailySymbol(
                        board_code="881001",
                        board_name="行业",
                        board_type="tdx_industry",
                    )
                ],
                start_date="20260521",
                end_date="20260521",
            )

            source.close()
            source.close()

        self.assertEqual(client.close_count, 1)

    def test_close_failure_is_traced_and_fails_closed(self) -> None:
        class CloseFailClient(FakeMootdxClient):
            def close(self):
                raise RuntimeError("fake close failure")

        with tempfile.TemporaryDirectory() as tmp:
            source = MootdxDailyBarSource(
                endpoint_manager=endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=passing_probe,
                client_factory=lambda selection, profile: CloseFailClient(),
            )
            source.fetch_board_daily_bars(
                boards=[
                    BoardDailySymbol(
                        board_code="881001",
                        board_name="行业",
                        board_type="tdx_industry",
                    )
                ],
                start_date="20260521",
                end_date="20260521",
            )

            with self.assertRaisesRegex(MootdxDailyBarSourceError, "close failed"):
                source.close()

        self.assertEqual(
            source.endpoint_provenance["business_client_close_error"],
            "RuntimeError",
        )

    def test_tdxpy_flag_uses_same_transport_factory_for_probe_and_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeMootdxClient()
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
                probe_client = make_client("std")
                self.assertIs(probe_client, client)
                return {
                    "checks": {
                        "stock_quote": True,
                        "stock_daily_bars": True,
                        "index_daily_bars": True,
                        "scope_sentinels": True,
                    }
                }

            source = MootdxDailyBarSource(
                endpoint_manager=endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=probe,
                transport_factory=transport_factory,
                quote_transport="tdxpy",
                attempt_id="source-attempt-tdxpy",
            )
            rows = source.fetch_board_daily_bars(
                boards=[
                    BoardDailySymbol(
                        board_code="881002",
                        board_name="煤炭开采",
                        board_type="tdx_industry",
                    )
                ],
                start_date="20260521",
                end_date="20260521",
            )

        self.assertEqual(
            factory_calls,
            [
                (
                    "tdxpy",
                    "tdxpy",
                    "mandatory_protocol_preflight_probe",
                    "primary",
                    "std",
                ),
                (
                    "tdxpy",
                    "tdxpy",
                    "mandatory_protocol_preflight_probe",
                    "secondary",
                    "std",
                ),
                (
                    "tdxpy",
                    "tdxpy",
                    "stable_priority_primary_healthy",
                    "primary",
                    "std",
                ),
            ],
        )
        self.assertEqual(
            rows[0]["mootdx_endpoint_provenance"]["transport"],
            "tdxpy",
        )
        self.assertEqual(
            rows[0]["mootdx_endpoint_provenance"]["source_transport"],
            "tdxpy",
        )

    def test_three_required_empty_board_objects_discard_complete_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = MootdxDailyBarSource(
                endpoint_manager=endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=passing_probe,
                client_factory=lambda selection, profile: FakeMootdxClient(rows=[]),
                attempt_id="source-attempt-empty",
            )

            with self.assertRaisesRegex(
                MootdxDailyBarSourceError,
                "discard the complete source-fetch attempt",
            ):
                source.fetch_board_daily_bars(
                    boards=[
                        BoardDailySymbol(
                            board_code=code,
                            board_name=code,
                            board_type="tdx_industry",
                        )
                        for code in ("881001", "881002", "881003")
                    ],
                    start_date="20260521",
                    end_date="20260521",
                )

    def test_tdxpy_empty_results_record_actual_transport(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager_instance = endpoint_manager(Path(tmp) / "health.json")
            with patch.object(
                endpoint_manager_instance,
                "record_required_object_result",
                wraps=endpoint_manager_instance.record_required_object_result,
            ) as record_empty:
                source = MootdxDailyBarSource(
                    endpoint_manager=endpoint_manager_instance,
                    endpoint_probe=passing_probe,
                    transport_factory=lambda selection, profile, *, transport: (
                        FakeMootdxClient(rows=[])
                    ),
                    quote_transport="tdxpy",
                )
                with self.assertRaises(MootdxDailyBarSourceError):
                    source.fetch_board_daily_bars(
                        boards=[
                            BoardDailySymbol(
                                board_code=code,
                                board_name=code,
                                board_type="tdx_industry",
                            )
                            for code in ("881001", "881002", "881003")
                        ],
                        start_date="20260521",
                        end_date="20260521",
                    )

        self.assertEqual(record_empty.call_count, 3)
        self.assertTrue(
            all(
                call.kwargs["transport"] == "tdxpy"
                for call in record_empty.call_args_list
            )
        )

    def test_repeated_same_empty_board_object_does_not_open_circuit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = MootdxDailyBarSource(
                endpoint_manager=endpoint_manager(Path(tmp) / "health.json"),
                endpoint_probe=passing_probe,
                client_factory=lambda selection, profile: FakeMootdxClient(rows=[]),
                attempt_id="source-attempt-repeat-empty",
            )

            rows = source.fetch_board_daily_bars(
                boards=[
                    BoardDailySymbol(
                        board_code="881001",
                        board_name="same",
                        board_type="tdx_industry",
                    )
                    for _ in range(3)
                ],
                start_date="20260521",
                end_date="20260521",
            )

        self.assertEqual(rows, [])

    def test_default_protocol_probe_rejects_wrong_identity_date_and_empty_sentinel(self) -> None:
        class ProtocolClient:
            def quotes(self, **kwargs):
                return FakeFrame([{"code": "600001", "price": "10"}])

            def bars(self, **kwargs):
                return FakeFrame(
                    [
                        {"code": "600000", "datetime": "2026-05-19"},
                        {"code": "600000", "datetime": "2026-05-20"},
                        {"code": "600000", "datetime": "2026-05-21"},
                    ]
                )

            def index(self, **kwargs):
                if kwargs["symbol"] == "000001":
                    return FakeFrame([{"code": "000001", "datetime": "2026-05-21"}])
                return FakeFrame([{"datetime": "2026-05-20"}])

        with tempfile.TemporaryDirectory() as tmp:
            source = MootdxDailyBarSource(
                endpoint_manager=endpoint_manager(Path(tmp) / "health.json"),
                client_factory=lambda selection, profile: ProtocolClient(),
            )
            with patch(
                "ashare_v3.mootdx_client.create_mootdx_client",
                return_value=ProtocolClient(),
            ):
                with self.assertRaisesRegex(
                    MootdxDailyBarSourceError,
                    "endpoint preflight failed closed",
                ):
                    source.fetch_board_daily_bars(
                        boards=[
                            BoardDailySymbol(
                                board_code="881002",
                                board_name="煤炭开采",
                                board_type="tdx_industry",
                            )
                        ],
                        start_date="20260521",
                        end_date="20260521",
                    )

    def test_sentinels_are_deterministic_first_middle_last(self) -> None:
        self.assertEqual(
            _deterministic_sentinels(["881001", "881002", "881003", "881004", "881005"]),
            ("881001", "881003", "881005"),
        )


if __name__ == "__main__":
    unittest.main()
