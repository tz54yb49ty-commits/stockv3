from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from ashare_v3.ingestion.windows_n1_sources import (
    ELTDX_FINANCE_BATCH_SIZE,
    EltdxWindowsSource,
    LocalTradeCalendarProvider,
    TQ_MARKETS,
    TQHttpClient,
    TQWindowsSource,
    calculate_market_values,
    load_vendor_module,
    normalize_tq_daily_rows,
    three_year_start,
    validate_ohlc_rows,
)


class FakeTQ:
    def __init__(self): self.calls = []
    def get_stock_list_in_sector(self, market):
        self.calls.append(("sector", market)); return [{"code": market + "00001"}]
    def get_stock_list(self, market):
        self.calls.append(("market", market)); return [{"code": market + "00001"}]
    def get_daily_bars(self, symbol, **kwargs):
        self.calls.append(("daily", symbol, kwargs)); return [{"trade_date": "20260102", "open": 1, "high": 2, "low": 1, "close": 2}]


class FakeEltdx:
    def __init__(self):
        self.corporate = self; self.f10 = self; self.reports = []; self.finance_requests = []
    def finance_batch(self, codes):
        self.finance_requests.append(tuple(codes)); return [{"code": code} for code in codes]
    def finance_report(self, code, report_type):
        self.reports.append(report_type); return [{"code": code, "report": report_type}]


class WindowsN1SourcesTest(unittest.TestCase):
    def test_local_trade_calendar_provider_uses_get_only_and_validates_contract(self):
        payloads = [
            {"status": "ok", "database": "up"},
            {"exchange": "SSE", "min": "20260101", "max": "20260103"},
            {
                "total": 3,
                "items": [
                    {"exchange": "SSE", "cal_date": "20260101", "is_open": "0", "pretrade_date": "20251231"},
                    {"exchange": "SSE", "cal_date": "20260102", "is_open": "1", "pretrade_date": "20251231"},
                    {"exchange": "SSE", "cal_date": "20260103", "is_open": "0", "pretrade_date": "20260102"},
                ],
            },
        ]
        requests = []

        class Response:
            def __init__(self, payload): self.payload = payload
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def read(self):
                import json
                return json.dumps(self.payload).encode()

        def open_request(request, timeout):
            requests.append((request.get_method(), request.full_url, timeout))
            return Response(payloads.pop(0))

        provider = LocalTradeCalendarProvider(timeout_seconds=3)
        with patch("ashare_v3.ingestion.windows_n1_sources.urlopen", side_effect=open_request):
            self.assertEqual(provider.health()["status"], "ok")
            available = provider.range()
            rows = provider.fetch(available["min"], available["max"])
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(method == "GET" for method, _url, _timeout in requests))
        self.assertTrue(all(url.startswith("http://127.0.0.1:8000/") for _method, url, _timeout in requests))

    def test_local_trade_calendar_rejects_partial_response(self):
        provider = LocalTradeCalendarProvider()
        payload = {
            "total": 2,
            "items": [{"exchange": "SSE", "cal_date": "20260101", "is_open": "0"}],
        }
        with patch.object(LocalTradeCalendarProvider, "_get", return_value=payload):
            with self.assertRaisesRegex(RuntimeError, "total/items mismatch"):
                provider.fetch("20260101", "20260102")

    def test_tq_uses_exact_markets_and_adjustment_authority(self):
        client = FakeTQ(); source = TQWindowsSource(client)
        self.assertEqual([row["market"] for row in source.fetch_market_members()], list(TQ_MARKETS))
        self.assertEqual([call for call in client.calls if call[0] == "market"], [("market", m) for m in TQ_MARKETS])
        source.fetch_daily("600000.SH", asset_kind="stock", start_date="20230101", end_date="20260102")
        source.fetch_daily("000001.SH", asset_kind="index", start_date="20230101", end_date="20260102")
        self.assertEqual(client.calls[-2][2], {"start_date": "20230101", "end_date": "20260102", "adjust": "qfq", "fill_data": False})
        self.assertEqual(client.calls[-1][2]["adjust"], None)

    def test_http_client_uses_native_tdxw_json_rpc_contract(self):
        client = TQHttpClient()
        calls = []
        client.call = lambda method, params: calls.append((method, params)) or {"600000.SH": {"Time": ["20260102"], "Close": [10]}}
        rows = client.get_daily_bars("600000.SH", start_date="20230101", end_date="20260102", adjust="qfq", fill_data=False)
        self.assertEqual(calls[0][0], "get_market_data")
        self.assertEqual(calls[0][1]["dividend_type"], "front")
        self.assertEqual(calls[0][1]["stock_list"], ["600000.SH"])
        self.assertFalse(calls[0][1]["fill_data"])
        self.assertEqual(rows, [{"Time": "20260102", "Close": 10}])
        client.get_stock_list_in_sector("5")
        self.assertEqual(calls[-1], ("get_stock_list_in_sector", {"block_code": "5", "list_type": 1}))
        client.get_stock_list("5")
        self.assertEqual(calls[-1], ("get_stock_list", {"market": "5", "list_type": 1}))

    def test_no_forbidden_source_fallback(self):
        with self.assertRaisesRegex(RuntimeError, "forbidden"):
            load_vendor_module("tushare")
        with self.assertRaisesRegex(RuntimeError, "forbidden"):
            load_vendor_module("mootdx.client")

    def test_eltdx_requires_exact_three_reports(self):
        client = FakeEltdx(); result = EltdxWindowsSource(client).fetch_three_reports("600000")
        self.assertEqual(tuple(result), ("balance", "income", "cashflow"))
        self.assertEqual(client.reports, ["zcfzb", "lrb", "xjllb"])

    def test_eltdx_finance_batch_is_chunked_at_server_limit(self):
        client = FakeEltdx(); codes = [f"code-{index}" for index in range(205)]
        result = EltdxWindowsSource(client).fetch_finance_batch(codes)
        self.assertEqual([len(batch) for batch in client.finance_requests], [100, 100, 5])
        self.assertEqual([row["code"] for row in result], codes)
        self.assertEqual(ELTDX_FINANCE_BATCH_SIZE, 100)

    def test_three_year_start_market_values_and_invalid_ohlc(self):
        self.assertEqual(three_year_start(date(2026, 8, 26)), "20230101")
        self.assertEqual(calculate_market_values(close=10, total_share=100, float_share=60), (1000.0, 600.0))
        self.assertEqual(calculate_market_values(close=10, total_share=None, float_share=None), (None, None))
        rows = [{"trade_date": "20260102", "open": 1, "high": 2, "low": 1, "close": 2}, {"trade_date": "20260103", "open": 1, "high": 0, "low": 1, "close": 2}]
        self.assertEqual(len(validate_ohlc_rows(rows)), 1)
        normalized = normalize_tq_daily_rows([{"Date": "20260102.0", "Open": "1", "High": "2", "Low": "1", "Close": "2", "Volume": "3", "Amount": "4"}])
        self.assertEqual(normalized[0]["trade_date"], "20260102")

    def test_eltdx_model_containers_are_normalized(self):
        class Row:
            def __init__(self): self.code = "000001"
        class Batch:
            records = [Row()]
        client = FakeEltdx()
        client.finance_batch = lambda codes: Batch()
        self.assertEqual(EltdxWindowsSource(client).fetch_finance_batch(["sz000001"]), [{"code": "000001"}])


if __name__ == "__main__": unittest.main()
