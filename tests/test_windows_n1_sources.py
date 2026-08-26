from __future__ import annotations

from datetime import date
import unittest

from ashare_v3.ingestion.windows_n1_sources import (
    EltdxWindowsSource,
    TQ_MARKETS,
    TQHttpClient,
    TQWindowsSource,
    calculate_market_values,
    load_vendor_module,
    three_year_start,
    validate_ohlc_rows,
)


class FakeTQ:
    def __init__(self): self.calls = []
    def get_stock_list_in_sector(self, market):
        self.calls.append(("sector", market)); return [{"code": market + "00001"}]
    def get_daily_bars(self, symbol, **kwargs):
        self.calls.append(("daily", symbol, kwargs)); return [{"trade_date": "20260102", "open": 1, "high": 2, "low": 1, "close": 2}]


class FakeEltdx:
    def finance_batch(self, codes): return [{"code": code} for code in codes]
    def finance_report(self, code, report): return [{"code": code, "report": report}]


class WindowsN1SourcesTest(unittest.TestCase):
    def test_tq_uses_exact_markets_and_adjustment_authority(self):
        client = FakeTQ(); source = TQWindowsSource(client)
        self.assertEqual([row["market"] for row in source.fetch_market_members()], list(TQ_MARKETS))
        source.fetch_daily("600000.SH", asset_kind="stock", start_date="20230101", end_date="20260102")
        source.fetch_daily("000001.SH", asset_kind="index", start_date="20230101", end_date="20260102")
        self.assertEqual(client.calls[-2][2], {"start_date": "20230101", "end_date": "20260102", "adjust": "qfq", "fill_data": False})
        self.assertEqual(client.calls[-1][2]["adjust"], None)

    def test_http_client_uses_native_tdxw_json_rpc_contract(self):
        client = TQHttpClient()
        calls = []
        client.call = lambda method, params: calls.append((method, params)) or {"Time": ["20260102"], "Close": [10]}
        rows = client.get_daily_bars("600000.SH", start_date="20230101", end_date="20260102", adjust="qfq", fill_data=False)
        self.assertEqual(calls[0][0], "get_market_data")
        self.assertEqual(calls[0][1]["dividend_type"], "front")
        self.assertFalse(calls[0][1]["fill_data"])
        self.assertEqual(rows, [{"Time": "20260102", "Close": 10}])
        client.get_stock_list_in_sector("5")
        self.assertEqual(calls[-1], ("get_stock_list_in_sector", {"block_code": "5"}))

    def test_no_forbidden_source_fallback(self):
        with self.assertRaisesRegex(RuntimeError, "forbidden"):
            load_vendor_module("tushare")
        with self.assertRaisesRegex(RuntimeError, "forbidden"):
            load_vendor_module("mootdx.client")

    def test_eltdx_requires_exact_three_reports(self):
        result = EltdxWindowsSource(FakeEltdx()).fetch_three_reports("600000")
        self.assertEqual(tuple(result), ("balance", "income", "cashflow"))

    def test_three_year_start_market_values_and_invalid_ohlc(self):
        self.assertEqual(three_year_start(date(2026, 8, 26)), "20230101")
        self.assertEqual(calculate_market_values(close=10, total_share=100, float_share=60), (1000.0, 600.0))
        self.assertEqual(calculate_market_values(close=10, total_share=None, float_share=None), (None, None))
        rows = [{"trade_date": "20260102", "open": 1, "high": 2, "low": 1, "close": 2}, {"trade_date": "20260103", "open": 1, "high": 0, "low": 1, "close": 2}]
        self.assertEqual(len(validate_ohlc_rows(rows)), 1)


if __name__ == "__main__": unittest.main()
