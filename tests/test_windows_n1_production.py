from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ashare_v3.ingestion.windows_n1_bootstrap import BootstrapResult, WindowsN1BootstrapConfig
from ashare_v3.ingestion.windows_n1_production import WindowsN1ProductionHandlers, normalize_eltdx_code


class FakeTQ:
    def fetch_market_members(self):
        return [
            {"market": "5", "Code": "600000.SH", "Name": "浦发银行"},
            {"market": "9", "Code": "999999.SH", "Name": "上证指数"},
            {"market": "11", "Code": "881001.SH", "Name": "行业"},
            {"market": "12", "Code": "880501.SH", "Name": "概念"},
            {"market": "14", "Code": "880201.SH", "Name": "地区"},
        ]

    def fetch_sector_members(self, block_code):
        return [{"Code": "600000.SH", "Name": "浦发银行"}]

    def fetch_daily(self, symbol, **kwargs):
        return [{"Date": "20260102", "Open": 10, "High": 11, "Low": 9, "Close": 10, "Volume": 1, "Amount": 10}]


class FakeEltdx:
    def fetch_finance_batch(self, codes):
        return [{
            "code": "600000",
            "zong_gu_ben_raw_float": 100,
            "liu_tong_gu_ben_raw_float": 60,
            "zhu_ying_shou_ru_raw_float": 1000,
            "jing_li_run_raw_float": 100,
            "jing_zi_chan_raw_float": 500,
            "mei_gu_jing_zi_chan_raw_float": 5,
            "eps_raw": 0.5,
        }]

    def fetch_three_reports(self, code):
        return {"balance": [{"code": code}], "income": [{"code": code}], "cashflow": [{"code": code}]}


class FakeRepository:
    def __init__(self):
        self.tables = []
        self.activations = []
        self.business = {"common_trade_calendar": 0}

    def verify_authority(self): pass
    def business_row_counts(self): return dict(self.business)
    def downstream_row_counts(self): return {}
    def persist_batch(self, **kwargs): self.tables.append((kwargs["table"], kwargs["rows"]))
    def activate_source(self, **kwargs): self.activations.append(kwargs["data_type"])
    def assert_n1_data_ready(self, scope_key): return {name: 1 for name in self.activations}


class WindowsN1ProductionTest(unittest.TestCase):
    def test_eltdx_exchange_prefixed_code_normalization(self):
        self.assertEqual(normalize_eltdx_code("sz000001"), "000001")

    def test_full_production_handler_dag_reaches_ready_boundary(self):
        with TemporaryDirectory() as directory:
            config = WindowsN1BootstrapConfig(
                artifact_root=Path(directory), start_date="20230101", end_date="20260826"
            )
            repository = FakeRepository()
            handlers = WindowsN1ProductionHandlers(
                config=config, tq=FakeTQ(), eltdx=FakeEltdx(), repository=repository
            )
            result = BootstrapResult(run_id="test")
            for stage in ("schema", "scope", "identity_membership", "daily_bars", "eltdx_finance", "daily_basic", "activate_n1_sources", "n1_data_ready"):
                getattr(handlers, stage)(result)
            self.assertTrue(result.finance_gate_passed)
            self.assertEqual(len(repository.activations), 10)
            self.assertEqual(result.security_failures, [])
            self.assertEqual(result.evidence["common_trade_calendar_delta"], 0)
            tables = {table for table, _rows in repository.tables}
            self.assertIn("stock_daily_basic", tables)
            self.assertNotIn("common_trade_calendar", tables)
            financial = next(rows[0] for table, rows in repository.tables if table == "stock_financial_metrics_fact")
            self.assertEqual(
                (financial["total_revenue"], financial["net_profit"], financial["net_assets"]),
                (1000, 100, 500),
            )
            self.assertEqual((financial["eps"], financial["bps"]), (0.5, 5))
            self.assertEqual((financial["total_mv"], financial["circ_mv"]), (1000.0, 600.0))
            daily_basic = next(rows[0] for table, rows in repository.tables if table == "stock_daily_basic")
            self.assertEqual((daily_basic["total_mv"], daily_basic["circ_mv"]), (1000.0, 600.0))
            self.assertIn("_v2_", financial["source_batch_id"])
            self.assertIn("_v2_", daily_basic["source_batch_id"])


if __name__ == "__main__": unittest.main()
