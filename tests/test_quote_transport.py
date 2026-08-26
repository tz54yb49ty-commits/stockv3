from __future__ import annotations

from dataclasses import replace
import unittest

from ashare_v3.mootdx_client import EndpointSelection
from ashare_v3.quote_transport import (
    DEFAULT_QUOTE_TRANSPORT,
    MootdxQuoteTransport,
    QuoteTransportConfigError,
    QuoteTransportConnectionError,
    QuoteTransportUnsupportedCall,
    TDXPY_BJ_STOCK_QUOTE_BLOCKER,
    TdxpyQuoteTransport,
    create_quote_transport,
    quote_transport_scope_blocker,
    resolve_quote_transport_name,
    transport_provenance,
)


def selection(
    *,
    selectable: bool = True,
    transport: str = "mootdx",
) -> EndpointSelection:
    return EndpointSelection(
        endpoint_pool_version="test-pool-v1",
        endpoint_id="primary",
        host="115.238.56.198",
        port=7709,
        transport=transport,
        health_state="healthy",
        health_checked_at="2026-07-19T00:00:00+00:00",
        probe_summary={"passed": True},
        attempt_id="attempt-1",
        selection_reason="test",
        failover_mode="observe",
        selectable=selectable,
    )


class FakeTdxpyApi:
    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.calls = []
        self.connect_result = self
        self.responses = {}
        self.disconnect_calls = 0
        self.close_calls = 0

    def connect(self, host, port, *, time_out):
        self.calls.append(("connect", host, port, time_out))
        return self.connect_result

    def get_security_quotes(self, routed):
        self.calls.append(("quotes", routed))
        return self.responses.get("quotes", [{"price": 10}])

    def get_security_bars(self, frequency, market, code, start, count):
        self.calls.append(("bars", frequency, market, code, start, count))
        return self.responses.get("bars", [{"datetime": "2026-07-17", "open": 1}])

    def get_index_bars(self, frequency, market, code, start, count):
        self.calls.append(("index_bars", frequency, market, code, start, count))
        return self.responses.get("index_bars", [{"datetime": "2026-07-17", "open": 1}])

    def get_minute_time_data(self, market, code):
        self.calls.append(("minute", market, code))
        return self.responses.get("minute", [{"price": 1}])

    def get_history_minute_time_data(self, market, code, trade_date):
        self.calls.append(("history_minute", market, code, trade_date))
        return self.responses.get("history_minute", [{"price": 1}])

    def disconnect(self):
        self.disconnect_calls += 1

    def close(self):
        self.close_calls += 1


class QuoteTransportTest(unittest.TestCase):
    def test_tdxpy_bj_stock_scope_is_blocked_before_transport_construction(self) -> None:
        objects = [
            {
                "asset_kind": "stock",
                "identity_key": "stock:BJ:830001",
                "exchange": "BJ",
            }
        ]

        blocker = quote_transport_scope_blocker("tdxpy", objects)

        self.assertEqual(
            blocker,
            {
                "blocker": TDXPY_BJ_STOCK_QUOTE_BLOCKER,
                "reason": "tdxpy transport does not support Beijing stock quotes",
                "transport": "tdxpy",
                "unsupported_identity_keys": ["stock:BJ:830001"],
            },
        )
        self.assertIsNone(quote_transport_scope_blocker("mootdx", objects))

    def test_default_is_mootdx_and_missing_flag_is_rollback(self) -> None:
        calls = []
        transport = create_quote_transport(
            selection(),
            environ={},
            mootdx_client_factory=lambda selected, profile: calls.append(
                (selected.server, profile)
            )
            or FakeTdxpyApi(),
        )

        self.assertEqual(DEFAULT_QUOTE_TRANSPORT, "mootdx")
        self.assertIsInstance(transport, MootdxQuoteTransport)
        self.assertEqual(calls, [(("115.238.56.198", 7709), "std")])
        self.assertEqual(resolve_quote_transport_name(environ={}), "mootdx")

    def test_mootdx_adds_requested_symbol_only_when_response_identity_is_missing(self) -> None:
        class RawClient:
            def bars(self, **kwargs):
                return [
                    {"datetime": "2026-07-17", "open": 1},
                    {"code": "600037", "datetime": "2026-07-17", "open": 2},
                    {"symbol": "600038", "datetime": "2026-07-17", "open": 3},
                ]

        transport = MootdxQuoteTransport(
            selection=selection(),
            client=RawClient(),
        )
        rows = transport.bars(symbol="600036")

        self.assertEqual(rows[0]["code"], "600036")
        self.assertEqual(rows[1]["code"], "600037")
        self.assertNotIn("code", rows[2])
        self.assertEqual(rows[2]["symbol"], "600038")

    def test_mootdx_close_is_idempotent(self) -> None:
        class ClosableClient:
            def __init__(self):
                self.close_calls = 0

            def close(self):
                self.close_calls += 1

        client = ClosableClient()
        transport = MootdxQuoteTransport(
            selection=selection(),
            client=client,
        )

        transport.close()
        transport.close()

        self.assertEqual(client.close_calls, 1)

    def test_tdxpy_flag_consumes_only_endpoint_selection_server(self) -> None:
        tempting_cached_server = ("218.6.170.47", 7709)
        del tempting_cached_server
        api = FakeTdxpyApi()
        transport = create_quote_transport(
            selection(transport="tdxpy"),
            environ={"ASHARE_V3_QUOTE_TRANSPORT": "tdxpy"},
            tdxpy_api_factory=lambda **kwargs: self._configure(api, kwargs),
        )

        self.assertIsInstance(transport, TdxpyQuoteTransport)
        self.assertEqual(
            api.init_kwargs,
            {"auto_retry": False, "heartbeat": False, "raise_exception": True},
        )
        self.assertEqual(
            api.calls,
            [("connect", "115.238.56.198", 7709, 5)],
        )
        self.assertEqual(transport.server, ("115.238.56.198", 7709))

    def test_tdxpy_routes_stock_index_board_and_minute(self) -> None:
        api = FakeTdxpyApi()
        transport = TdxpyQuoteTransport(
            selection=selection(transport="tdxpy"),
            api_factory=lambda **kwargs: self._configure(api, kwargs),
        )

        transport.quotes(["600036", "000001"])
        transport.bars(symbol="600036", frequency=9, start=2, offset=900)
        transport.index(symbol="000001", frequency="day", offset=10)
        transport.index_bars(symbol="399006", frequency="1m", offset=10)
        transport.index_bars(symbol="881001", frequency=9, offset=10)
        transport.index_bars(symbol="899050", frequency=9, offset=10)
        transport.minute(symbol="000001")
        transport.minute(symbol="600036", date="2026-07-17")

        self.assertIn(("quotes", [(1, "600036"), (0, "000001")]), api.calls)
        self.assertIn(("bars", 9, 1, "600036", 2, 800), api.calls)
        self.assertIn(("index_bars", 9, 1, "000001", 0, 10), api.calls)
        self.assertIn(("index_bars", 8, 0, "399006", 0, 10), api.calls)
        self.assertIn(("index_bars", 9, 1, "881001", 0, 10), api.calls)
        self.assertIn(("index_bars", 9, 2, "899050", 0, 10), api.calls)
        self.assertIn(("minute", 0, "000001"), api.calls)
        self.assertIn(("history_minute", 1, "600036", 20260717), api.calls)

    def test_tdxpy_routes_historical_and_new_beijing_stock_prefixes(self) -> None:
        api = FakeTdxpyApi()
        transport = TdxpyQuoteTransport(
            selection=selection(transport="tdxpy"),
            api_factory=lambda **kwargs: self._configure(api, kwargs),
        )

        transport.bars(symbol="430047")
        transport.bars(symbol="830799")
        transport.bars(symbol="920211")
        transport.bars(symbol="900901")

        self.assertIn(("bars", 9, 2, "430047", 0, 800), api.calls)
        self.assertIn(("bars", 9, 2, "830799", 0, 800), api.calls)
        self.assertIn(("bars", 9, 2, "920211", 0, 800), api.calls)
        self.assertIn(("bars", 9, 1, "900901", 0, 800), api.calls)

    def test_tdxpy_beijing_quotes_fail_closed_before_api_call(self) -> None:
        for code in ("430047", "830799", "920211"):
            with self.subTest(code=code):
                api = FakeTdxpyApi()
                transport = TdxpyQuoteTransport(
                    selection=selection(transport="tdxpy"),
                    api_factory=lambda **kwargs: self._configure(api, kwargs),
                )

                with self.assertRaisesRegex(
                    QuoteTransportUnsupportedCall,
                    "Beijing stock quotes are unsupported",
                ):
                    transport.quotes(code)

                self.assertNotIn("quotes", [call[0] for call in api.calls])

    def test_one_tdxpy_instance_never_changes_endpoint(self) -> None:
        primary_api = FakeTdxpyApi()
        secondary_api = FakeTdxpyApi()
        primary = TdxpyQuoteTransport(
            selection=selection(transport="tdxpy"),
            api_factory=lambda **kwargs: self._configure(primary_api, kwargs),
        )
        secondary = TdxpyQuoteTransport(
            selection=replace(
                selection(transport="tdxpy"),
                endpoint_id="secondary",
                host="180.153.18.170",
            ),
            api_factory=lambda **kwargs: self._configure(secondary_api, kwargs),
        )

        primary.bars(symbol="600036")
        secondary.bars(symbol="600036")

        self.assertEqual(primary.server, ("115.238.56.198", 7709))
        self.assertEqual(secondary.server, ("180.153.18.170", 7709))
        self.assertEqual(primary_api.calls[0][1:3], primary.server)
        self.assertEqual(secondary_api.calls[0][1:3], secondary.server)

    def test_tdxpy_close_prefers_disconnect_and_is_idempotent(self) -> None:
        api = FakeTdxpyApi()
        transport = TdxpyQuoteTransport(
            selection=selection(transport="tdxpy"),
            api_factory=lambda **kwargs: self._configure(api, kwargs),
        )

        transport.close()
        transport.close()

        self.assertEqual(api.disconnect_calls, 1)
        self.assertEqual(api.close_calls, 0)

    def test_none_false_and_empty_are_explicit_empty_rows(self) -> None:
        api = FakeTdxpyApi()
        api.responses = {"quotes": None, "bars": False, "index_bars": []}
        transport = TdxpyQuoteTransport(
            selection=selection(transport="tdxpy"),
            api_factory=lambda **kwargs: self._configure(api, kwargs),
        )

        self.assertEqual(transport.quotes("600036"), [])
        self.assertEqual(transport.bars("600036"), [])
        self.assertEqual(transport.index("000001"), [])

    def test_tdxpy_adds_requested_symbol_without_overwriting_wrong_identity(self) -> None:
        api = FakeTdxpyApi()
        api.responses = {
            "bars": [
                {"datetime": "2026-07-17", "open": 1},
                {"code": "600037", "datetime": "2026-07-17", "open": 2},
            ]
        }
        transport = TdxpyQuoteTransport(
            selection=selection(transport="tdxpy"),
            api_factory=lambda **kwargs: self._configure(api, kwargs),
        )

        rows = transport.bars("600036")

        self.assertEqual(rows[0]["code"], "600036")
        self.assertEqual(rows[1]["code"], "600037")

    def test_exception_is_not_converted_to_empty(self) -> None:
        class FailingApi(FakeTdxpyApi):
            def get_security_bars(self, *args):
                raise TimeoutError("fake timeout")

        transport = TdxpyQuoteTransport(
            selection=selection(transport="tdxpy"),
            api_factory=FailingApi,
        )
        with self.assertRaisesRegex(TimeoutError, "fake timeout"):
            transport.bars("600036")

    def test_unsupported_calls_and_invalid_flag_fail_closed(self) -> None:
        api = FakeTdxpyApi()
        transport = TdxpyQuoteTransport(
            selection=selection(transport="tdxpy"),
            api_factory=lambda **kwargs: self._configure(api, kwargs),
        )

        with self.assertRaises(QuoteTransportUnsupportedCall):
            transport.bars("600036", adjust="qfq")
        with self.assertRaises(QuoteTransportUnsupportedCall):
            transport.minute("600036", asset_kind="index")
        with self.assertRaises(QuoteTransportConfigError):
            resolve_quote_transport_name(environ={"ASHARE_V3_QUOTE_TRANSPORT": "cached-bestip"})

    def test_missing_selection_authority_and_connect_false_fail_closed(self) -> None:
        api = FakeTdxpyApi()
        api.connect_result = False
        with self.assertRaises(QuoteTransportConnectionError):
            TdxpyQuoteTransport(
                selection=selection(transport="tdxpy"),
                api_factory=lambda **kwargs: self._configure(api, kwargs),
            )
        with self.assertRaisesRegex(Exception, "fail-closed"):
            create_quote_transport(
                selection=selection(selectable=False),
                environ={},
                mootdx_client_factory=lambda selected, profile: object(),
            )

    def test_provenance_preserves_endpoint_and_adds_actual_transport(self) -> None:
        api = FakeTdxpyApi()
        transport = TdxpyQuoteTransport(
            selection=selection(transport="tdxpy"),
            api_factory=lambda **kwargs: self._configure(api, kwargs),
        )

        provenance = transport_provenance(transport)

        self.assertEqual(provenance["endpoint_id"], "primary")
        self.assertEqual(provenance["endpoint_host"], "115.238.56.198")
        self.assertEqual(provenance["attempt_id"], "attempt-1")
        self.assertEqual(provenance["transport"], "tdxpy")

    def test_selection_and_requested_transport_mismatch_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            QuoteTransportConfigError,
            "transport mismatch",
        ):
            create_quote_transport(
                selection(),
                transport="tdxpy",
                tdxpy_api_factory=FakeTdxpyApi,
            )

    @staticmethod
    def _configure(api, kwargs):
        api.init_kwargs = kwargs
        return api


if __name__ == "__main__":
    unittest.main()
