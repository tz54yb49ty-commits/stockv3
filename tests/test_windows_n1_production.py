from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ashare_v3.ingestion.windows_n1_bootstrap import BootstrapResult, WindowsN1BootstrapConfig
from ashare_v3.ingestion.windows_n1_production import (
    WindowsN1ProductionHandlers,
    chunked,
    finance_report_fingerprint,
    normalize_eltdx_code,
    persist_daily_bars_batched,
)


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

    def fetch_daily_batch(self, symbols, **kwargs):
        trade_date = kwargs["start_date"]
        return {
            symbol: [{
                "Date": trade_date,
                "Open": 10,
                "High": 11,
                "Low": 9,
                "Close": 10,
                "Volume": 1,
                "Amount": 10,
            }]
            for symbol in symbols
        }


class FakeEltdx:
    def __init__(self):
        self.report_calls = []

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
        self.report_calls.append(code)
        return {"balance": [{"code": code}], "income": [{"code": code}], "cashflow": [{"code": code}]}


class FakeRepository:
    def __init__(self):
        self.tables = []
        self.activations = []
        self.activation_batch_ids = []
        self.business = {"common_trade_calendar": 1096}

    def verify_authority(self): pass
    def business_row_counts(self): return dict(self.business)
    def downstream_row_counts(self): return {}
    def persist_batch(self, **kwargs): self.tables.append((kwargs["table"], kwargs["rows"]))
    def daily_bar_source_counts(self, trade_date, source_version):
        result = {}
        for asset, table in (
            ("stock", "stock_daily_bar_fact"),
            ("index", "index_daily_bar_fact"),
            ("board", "board_daily_bar_fact"),
        ):
            identity_column = f"{asset}_identity_key"
            rows = [
                row
                for saved_table, saved_rows in self.tables
                if saved_table == table
                for row in saved_rows
                if row["trade_date"] == trade_date
                and row["source_version"] == source_version
            ]
            unique_rows = {
                (row[identity_column], row["trade_date"], row["source_version"])
                for row in rows
            }
            result[asset] = {
                "rows": len(unique_rows),
                "entities": len({row[identity_column] for row in rows}),
            }
        return result
    def activate_source(self, **kwargs):
        self.activations.append(kwargs["data_type"])
        self.activation_batch_ids.append(kwargs["batch_id"])
    def assert_n1_data_ready(self, scope_key): return {name: 1 for name in self.activations}
    def latest_stock_finance_payloads(self):
        return {
            "600000": {
                "finance_batch": FakeEltdx().fetch_finance_batch([])[0],
                "reports": {
                    "balance": [{"code": "600000"}],
                    "income": [{"code": "600000"}],
                    "cashflow": [{"code": "600000"}],
                },
            }
        }


class WindowsN1ProductionTest(unittest.TestCase):
    def test_eltdx_exchange_prefixed_code_normalization(self):
        self.assertEqual(normalize_eltdx_code("sz000001"), "000001")

    def test_5562_symbols_are_split_into_56_batches_of_at_most_100(self):
        batches = chunked(tuple(str(value) for value in range(5562)))
        self.assertEqual(len(batches), 56)
        self.assertTrue(all(len(batch) <= 100 for batch in batches))
        self.assertEqual(len(batches[-1]), 62)

    def test_finance_report_fingerprint_prefers_report_update_markers(self):
        first = {
            "updated_date": "20260826",
            "finance_info_raw": "2026Q2",
            "jing_li_run_raw_float": 100,
        }
        same_report_new_quote = {**first, "jing_li_run_raw_float": 101}
        next_report = {**first, "updated_date": "20260827"}
        self.assertEqual(
            finance_report_fingerprint(first),
            finance_report_fingerprint(same_report_new_quote),
        )
        self.assertNotEqual(
            finance_report_fingerprint(first),
            finance_report_fingerprint(next_report),
        )

    def test_one_normally_empty_daily_batch_does_not_block_other_batches(self):
        class PartlyEmptyTQ(FakeTQ):
            def fetch_daily_batch(self, symbols, **kwargs):
                if "600000.SH" in symbols:
                    return {symbol: [] for symbol in symbols}
                return super().fetch_daily_batch(symbols, **kwargs)

        repository = FakeRepository()
        result = BootstrapResult(run_id="partly_empty")
        tq = PartlyEmptyTQ()
        scopes = {market: [] for market in ("5", "9", "11", "12", "14")}
        for row in tq.fetch_market_members():
            scopes[row["market"]].append(row)
        batch_result = persist_daily_bars_batched(
            start_date="20260827",
            end_date="20260827",
            source_version="windows_n1_20260827_20260827_v1",
            run_id="partly_empty",
            scopes=scopes,
            tq=tq,
            repository=repository,
            result=result,
        )
        self.assertEqual(batch_result["batch_counts"], {
            "requested": 5, "completed": 5, "empty": 1, "failed": 0,
        })
        self.assertEqual(batch_result["row_counts"]["stock_daily_bar_fact"], 0)
        self.assertEqual(result.security_failures, [])

    def test_one_empty_symbol_does_not_block_valid_symbol_in_same_batch(self):
        class OneEmptySymbolTQ(FakeTQ):
            def fetch_market_members(self):
                return [
                    *super().fetch_market_members(),
                    {"market": "5", "Code": "000001.SZ", "Name": "平安银行"},
                ]

            def fetch_daily_batch(self, symbols, **kwargs):
                fetched = super().fetch_daily_batch(symbols, **kwargs)
                if "600000.SH" in fetched:
                    fetched["600000.SH"] = []
                return fetched

        repository = FakeRepository()
        result = BootstrapResult(run_id="one_empty_symbol")
        tq = OneEmptySymbolTQ()
        scopes = {market: [] for market in ("5", "9", "11", "12", "14")}
        for row in tq.fetch_market_members():
            scopes[row["market"]].append(row)
        batch_result = persist_daily_bars_batched(
            start_date="20260827",
            end_date="20260827",
            source_version="windows_n1_20260827_20260827_v1",
            run_id="one_empty_symbol",
            scopes=scopes,
            tq=tq,
            repository=repository,
            result=result,
        )
        self.assertEqual(batch_result["row_counts"]["stock_daily_bar_fact"], 1)
        self.assertEqual(batch_result["batch_counts"]["failed"], 0)

    def test_all_empty_daily_batches_fail_as_source_unavailable(self):
        class AllEmptyTQ(FakeTQ):
            def fetch_daily_batch(self, symbols, **kwargs):
                return {symbol: [] for symbol in symbols}

        tq = AllEmptyTQ()
        scopes = {market: [] for market in ("5", "9", "11", "12", "14")}
        for row in tq.fetch_market_members():
            scopes[row["market"]].append(row)
        with self.assertRaisesRegex(RuntimeError, "no valid rows"):
            persist_daily_bars_batched(
                start_date="20260827",
                end_date="20260827",
                source_version="windows_n1_20260827_20260827_v1",
                run_id="all_empty",
                scopes=scopes,
                tq=tq,
                repository=FakeRepository(),
                result=BootstrapResult(run_id="all_empty"),
            )

    def test_daily_source_row_count_mismatch_fails(self):
        class MismatchRepository(FakeRepository):
            def daily_bar_source_counts(self, trade_date, source_version):
                counts = super().daily_bar_source_counts(trade_date, source_version)
                counts["stock"]["rows"] += 1
                return counts

        tq = FakeTQ()
        scopes = {market: [] for market in ("5", "9", "11", "12", "14")}
        for row in tq.fetch_market_members():
            scopes[row["market"]].append(row)
        with self.assertRaisesRegex(RuntimeError, "row-count mismatch"):
            persist_daily_bars_batched(
                start_date="20260827",
                end_date="20260827",
                source_version="windows_n1_20260827_20260827_v1",
                run_id="mismatch",
                scopes=scopes,
                tq=tq,
                repository=MismatchRepository(),
                result=BootstrapResult(run_id="mismatch"),
            )

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
            self.assertTrue(all(
                row["source_batch_id"].startswith("test_")
                for _table, rows in repository.tables
                for row in rows
            ))
            self.assertTrue(all(
                batch_id.startswith("test_activate_")
                for batch_id in repository.activation_batch_ids
            ))

    def test_daily_mode_batches_kline_finance_and_daily_basic(self):
        with TemporaryDirectory() as directory:
            config = WindowsN1BootstrapConfig(
                artifact_root=Path(directory), start_date="20260827", end_date="20260827"
            )
            repository = FakeRepository()
            eltdx = FakeEltdx()
            handlers = WindowsN1ProductionHandlers(
                config=config,
                tq=FakeTQ(),
                eltdx=eltdx,
                repository=repository,
                daily_mode=True,
            )
            result = BootstrapResult(run_id="daily")
            for stage in (
                "schema", "scope", "identity_membership", "daily_bars",
                "eltdx_finance", "daily_basic", "activate_n1_sources", "n1_data_ready",
            ):
                getattr(handlers, stage)(result)
            self.assertEqual(
                result.evidence["daily_bar_batches"]["batch_counts"]["failed"], 0
            )
            self.assertEqual(result.evidence["finance_incremental"]["report_refresh_count"], 0)
            self.assertEqual(result.evidence["finance_incremental"]["report_reuse_count"], 1)
            self.assertEqual(eltdx.report_calls, [])
            self.assertEqual(result.evidence["daily_basic_incremental"]["row_count"], 1)


if __name__ == "__main__": unittest.main()
