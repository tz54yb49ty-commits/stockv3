import importlib.util
import unittest
from pathlib import Path

from ashare_v3.ingestion.stock_financial_canonical_metrics import SOURCE_TDX, SOURCE_TUSHARE_FALLBACK
from ashare_v3.ingestion.stock_financial_canonical_source_bundle import (
    StockFinancialCanonicalSourceBundleBlocked,
    build_source_bundle_report,
    cached_tushare_symbol_entry,
    compute_financial_canonical_delta,
    compute_financial_canonical_delta_identity_keys,
    fetch_tushare_rows_from_client,
    financial_source_signature,
    incremental_delta_guard_probe,
    parse_symbol_shard,
    select_probe_symbols,
    validate_source_bundle_request,
)
from ashare_v3.ingestion.stock_financial import StockFinancialSymbol


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "plan_stock_financial_canonical_source_bundle_20260529.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("stock_financial_canonical_source_bundle_runner", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def tdx_row(identity_key: str, report_period: str = "20260331", announcement_date: str = "20260425") -> dict:
    return {
        "stock_identity_key": identity_key,
        "ts_code": identity_key.split(":")[-1] + "." + identity_key.split(":")[1],
        "code": identity_key.split(":")[-1],
        "exchange": identity_key.split(":")[1],
        "source_type": SOURCE_TDX,
        "report_period": report_period,
        "announcement_date": announcement_date,
        "operating_revenue": "1000",
        "operating_cost": "600",
        "taxes_and_surcharges": "10",
        "selling_expense": "20",
        "admin_expense": "30",
        "rd_expense": "40",
        "interest_expense": "10",
        "operating_cashflow": "580",
    }


class StockFinancialCanonicalSourceBundleTest(unittest.TestCase):
    def test_incremental_delta_selects_only_new_or_changed_symbols(self) -> None:
        unchanged = tdx_row("stock:SH:600000")
        changed = {**tdx_row("stock:SH:600001"), "announcement_date": "20260510"}
        new = tdx_row("stock:SH:600002")
        previous_snapshot = {
            "schema_version": "financial_canonical_snapshot_v1",
            "rows_by_identity": {
                "stock:SH:600000": {
                    "source_signature": financial_source_signature([unchanged]),
                    "financial_rows": [unchanged],
                },
                "stock:SH:600001": {
                    "source_signature": financial_source_signature([changed]),
                    "financial_rows": [changed],
                },
            },
        }
        current_rows = [
            unchanged,
            {**changed, "announcement_date": "20260520"},
            new,
        ]

        delta = compute_financial_canonical_delta_identity_keys(
            current_rows,
            previous_snapshot=previous_snapshot,
        )

        self.assertEqual(delta, ["stock:SH:600001", "stock:SH:600002"])

    def test_incremental_delta_requires_snapshot_unless_full_rebuild_is_explicit(self) -> None:
        current_rows = [tdx_row("stock:SH:600000")]

        with self.assertRaises(StockFinancialCanonicalSourceBundleBlocked):
            compute_financial_canonical_delta_identity_keys(current_rows, previous_snapshot=None)

        self.assertEqual(
            compute_financial_canonical_delta_identity_keys(
                current_rows,
                previous_snapshot=None,
                full_rebuild_confirmed=True,
            ),
            ["stock:SH:600000"],
        )

    def test_financial_signature_ignores_daily_basic_and_source_metadata(self) -> None:
        previous = {
            **tdx_row("stock:SH:600000"),
            "source_trade_date": "20260616",
            "source_version": "stock_financial_20260616_v1",
            "source_batch_id": "stock_financial_20260616_v1",
            "raw_payload": {
                "daily_basic": {
                    "trade_date": "20260616",
                    "close": "10.11",
                    "total_mv": "100000",
                    "circ_mv": "90000",
                },
                "latest_source": {
                    "operating_revenue": "1000",
                    "operating_cost": "600",
                    "taxes_and_surcharges": "10",
                    "selling_expense": "20",
                    "admin_expense": "30",
                    "rd_expense": "40",
                    "interest_expense": "10",
                    "operating_cashflow": "580",
                },
            },
        }
        current = {
            **previous,
            "source_trade_date": "20260617",
            "source_version": "stock_financial_20260617_v1",
            "source_batch_id": "stock_financial_20260617_v1",
            "raw_payload": {
                "daily_basic": {
                    "trade_date": "20260617",
                    "close": "10.37",
                    "total_mv": "102000",
                    "circ_mv": "91800",
                },
                "latest_source": previous["raw_payload"]["latest_source"],
            },
        }

        self.assertEqual(financial_source_signature([previous]), financial_source_signature([current]))
        previous_snapshot = {
            "schema_version": "financial_canonical_snapshot_v1",
            "rows_by_identity": {
                "stock:SH:600000": {
                    "source_signature": financial_source_signature([previous]),
                    "financial_rows": [previous],
                }
            },
        }

        delta = compute_financial_canonical_delta(
            [current],
            previous_snapshot=previous_snapshot,
        )

        self.assertEqual(delta["identity_keys"], [])
        self.assertEqual(delta["reason_distribution"], {})

    def test_incremental_delta_recomputes_stable_signature_from_legacy_snapshot_rows(self) -> None:
        previous = {
            **tdx_row("stock:SH:600000"),
            "raw_payload": {
                "daily_basic": {"trade_date": "20260616", "close": "10.11", "total_mv": "100000"},
                "latest_source": {"operating_cost": "600", "operating_cashflow": "580"},
            },
        }
        current = {
            **previous,
            "raw_payload": {
                "daily_basic": {"trade_date": "20260617", "close": "10.37", "total_mv": "102000"},
                "latest_source": {"operating_cost": "600", "operating_cashflow": "580"},
            },
        }
        previous_snapshot = {
            "schema_version": "financial_canonical_snapshot_v1",
            "rows_by_identity": {
                "stock:SH:600000": {
                    "source_signature": "legacy_signature_that_included_daily_basic",
                    "financial_rows": [previous],
                }
            },
        }

        delta = compute_financial_canonical_delta(
            [current],
            previous_snapshot=previous_snapshot,
        )

        self.assertEqual(delta["identity_keys"], [])

    def test_incremental_delta_does_not_downgrade_when_current_active_report_is_older_than_snapshot(self) -> None:
        previous = tdx_row("stock:SH:600000", report_period="20260331", announcement_date="20260425")
        current = {
            **tdx_row("stock:SH:600000", report_period="20251231", announcement_date="20260420"),
            "raw_payload": {
                "selected_financial": {
                    "report_period": "20251231",
                    "announcement_date": "20260420",
                    "source": "financial_asof_snapshot.tushare_fallback+daily_basic",
                }
            },
        }
        previous_snapshot = {
            "schema_version": "financial_canonical_snapshot_v1",
            "rows_by_identity": {
                "stock:SH:600000": {
                    "source_signature": "legacy_signature_that_included_daily_basic",
                    "financial_rows": [previous],
                }
            },
        }

        delta = compute_financial_canonical_delta(
            [current],
            previous_snapshot=previous_snapshot,
        )

        self.assertEqual(delta["identity_keys"], [])

    def test_financial_signature_detects_financial_line_item_changes(self) -> None:
        previous = {
            **tdx_row("stock:SH:600000"),
            "raw_payload": {
                "latest_source": {
                    "operating_revenue": "1000",
                    "operating_cost": "600",
                    "operating_cashflow": "580",
                }
            },
        }
        previous.pop("operating_cost")
        current = {
            **previous,
            "raw_payload": {
                "latest_source": {
                    "operating_revenue": "1000",
                    "operating_cost": "601",
                    "operating_cashflow": "580",
                }
            },
        }
        previous_snapshot = {
            "schema_version": "financial_canonical_snapshot_v1",
            "rows_by_identity": {
                "stock:SH:600000": {
                    "source_signature": financial_source_signature([previous]),
                    "financial_rows": [previous],
                }
            },
        }

        delta = compute_financial_canonical_delta(
            [current],
            previous_snapshot=previous_snapshot,
        )

        self.assertEqual(delta["identity_keys"], ["stock:SH:600000"])
        self.assertEqual(delta["reason_distribution"], {"financial_source_signature_changed": 1})

    def test_explicit_changed_identity_key_forces_delta(self) -> None:
        unchanged = tdx_row("stock:SH:600000")
        previous_snapshot = {
            "schema_version": "financial_canonical_snapshot_v1",
            "rows_by_identity": {
                "stock:SH:600000": {
                    "source_signature": financial_source_signature([unchanged]),
                    "financial_rows": [unchanged],
                }
            },
        }

        delta = compute_financial_canonical_delta(
            [unchanged],
            previous_snapshot=previous_snapshot,
            explicit_changed_identity_keys=["stock:SH:600000"],
        )

        self.assertEqual(delta["identity_keys"], ["stock:SH:600000"])
        self.assertEqual(delta["reason_distribution"], {"explicit_changed_identity_key": 1})

    def test_incremental_delta_guard_blocks_near_full_universe_without_full_rebuild_confirmation(self) -> None:
        blocked = incremental_delta_guard_probe(
            active_universe_count=100,
            delta_symbol_count=21,
            incremental_enabled=True,
            full_rebuild_confirmed=False,
        )
        allowed = incremental_delta_guard_probe(
            active_universe_count=100,
            delta_symbol_count=21,
            incremental_enabled=True,
            full_rebuild_confirmed=True,
        )

        self.assertTrue(blocked["incremental_delta_guard_blocked"])
        self.assertEqual(blocked["incremental_delta_guard_threshold_ratio"], 0.2)
        self.assertFalse(allowed["incremental_delta_guard_blocked"])

    def test_tushare_fallback_uses_bulk_pages_filtered_to_active_symbols(self) -> None:
        class FakePro:
            def __init__(self) -> None:
                self.calls = []

            def income(self, **kwargs):
                self.calls.append(("income", kwargs))
                if kwargs.get("offset", 0) > 0:
                    return []
                return [
                    {
                        "ts_code": "600000.SH",
                        "ann_date": "20260425",
                        "end_date": "20260331",
                        "total_revenue": "1000",
                        "oper_cost": "600",
                        "biz_tax_surchg": "10",
                        "sell_exp": "20",
                        "admin_exp": "30",
                        "rd_exp": "40",
                        "fin_exp": "10",
                    },
                    {"ts_code": "000001.SZ", "ann_date": "20260425", "end_date": "20260331", "total_revenue": "1"},
                ]

            def cashflow(self, **kwargs):
                self.calls.append(("cashflow", kwargs))
                if kwargs.get("offset", 0) > 0:
                    return []
                return [{"ts_code": "600000.SH", "ann_date": "20260425", "end_date": "20260331", "n_cashflow_act": "580"}]

            def forecast(self, **kwargs):
                self.calls.append(("forecast", kwargs))
                if kwargs.get("offset", 0) > 0:
                    return []
                return [{"ts_code": "600000.SH", "ann_date": "20260501", "end_date": "20260630", "type": "预增"}]

            def daily_basic(self, **kwargs):
                self.calls.append(("daily_basic", kwargs))
                if kwargs.get("offset", 0) > 0:
                    return []
                return [{"ts_code": "600000.SH", "trade_date": "20260529", "total_mv": "1200", "circ_mv": "900"}]

        pro = FakePro()
        bundle = fetch_tushare_rows_from_client(
            pro=pro,
            symbols=[StockFinancialSymbol(code="600000", exchange="SH")],
            source_trade_date="20260529",
        )

        self.assertEqual(len(bundle["financial_rows"]), 1)
        self.assertEqual(bundle["financial_rows"][0]["stock_identity_key"], "stock:SH:600000")
        self.assertEqual(bundle["financial_rows"][0]["operating_cashflow"], "580")
        self.assertEqual(len(bundle["forecast_rows"]), 1)
        self.assertEqual(len(bundle["daily_basic_rows"]), 1)
        financial_calls = [kwargs for name, kwargs in pro.calls if name in {"income", "cashflow", "forecast"}]
        self.assertTrue(financial_calls)
        self.assertTrue(all(kwargs.get("ts_code") == "600000.SH" for kwargs in financial_calls))
        self.assertEqual(bundle["stats"]["tushare_income_ok_count"], 1)
        self.assertEqual(bundle["stats"]["tushare_cashflow_ok_count"], 1)
        self.assertEqual(bundle["stats"]["forecast_ok_count"], 1)
        self.assertEqual(bundle["stats"]["daily_basic_ok_count"], 1)

    def test_tushare_fallback_bulk_fetches_many_symbols_without_per_symbol_calls(self) -> None:
        class FakePro:
            def __init__(self) -> None:
                self.calls = []

            def income(self, **kwargs):
                self.calls.append(("income", kwargs))
                if kwargs.get("offset", 0) > 0:
                    return []
                return [
                    {
                        "ts_code": "600000.SH",
                        "ann_date": "20260425",
                        "end_date": "20260331",
                        "total_revenue": "1000",
                        "oper_cost": "600",
                        "biz_tax_surchg": "10",
                        "sell_exp": "20",
                        "admin_exp": "30",
                        "rd_exp": "40",
                        "fin_exp": "10",
                    },
                    {
                        "ts_code": "000001.SZ",
                        "ann_date": "20260425",
                        "end_date": "20260331",
                        "total_revenue": "900",
                        "oper_cost": "500",
                        "biz_tax_surchg": "10",
                        "sell_exp": "20",
                        "admin_exp": "30",
                        "rd_exp": "40",
                        "fin_exp": "10",
                    },
                    {"ts_code": "999999.SH", "ann_date": "20260425", "end_date": "20260331", "total_revenue": "1"},
                ]

            def cashflow(self, **kwargs):
                self.calls.append(("cashflow", kwargs))
                if kwargs.get("offset", 0) > 0:
                    return []
                return [
                    {"ts_code": "600000.SH", "ann_date": "20260425", "end_date": "20260331", "n_cashflow_act": "580"},
                    {"ts_code": "000001.SZ", "ann_date": "20260425", "end_date": "20260331", "n_cashflow_act": "480"},
                ]

            def forecast(self, **kwargs):
                self.calls.append(("forecast", kwargs))
                return []

            def daily_basic(self, **kwargs):
                self.calls.append(("daily_basic", kwargs))
                if kwargs.get("offset", 0) > 0:
                    return []
                return [
                    {"ts_code": "600000.SH", "trade_date": "20260529", "total_mv": "1200", "circ_mv": "900"},
                    {"ts_code": "000001.SZ", "trade_date": "20260529", "total_mv": "900", "circ_mv": "700"},
                ]

        pro = FakePro()
        bundle = fetch_tushare_rows_from_client(
            pro=pro,
            symbols=[
                StockFinancialSymbol(code="600000", exchange="SH"),
                StockFinancialSymbol(code="000001", exchange="SZ"),
            ],
            source_trade_date="20260529",
            announcement_dates=["20260425"],
        )

        self.assertEqual(len(bundle["financial_rows"]), 2)
        self.assertEqual({row["stock_identity_key"] for row in bundle["financial_rows"]}, {"stock:SH:600000", "stock:SZ:000001"})
        financial_calls = [kwargs for name, kwargs in pro.calls if name in {"income", "cashflow", "forecast"}]
        self.assertTrue(financial_calls)
        self.assertTrue(all("ts_code" not in kwargs for kwargs in financial_calls))
        self.assertTrue(all(kwargs.get("ann_date") == "20260425" for kwargs in financial_calls))
        self.assertEqual(bundle["stats"]["tushare_income_ok_count"], 2)
        self.assertEqual(bundle["stats"]["tushare_cashflow_ok_count"], 2)
        self.assertEqual(bundle["stats"]["daily_basic_ok_count"], 2)

    def test_tushare_batch_unsupported_falls_back_to_per_symbol_fetch(self) -> None:
        class FakePro:
            def __init__(self) -> None:
                self.calls = []

            def income(self, **kwargs):
                self.calls.append(("income", kwargs))
                if "ts_code" not in kwargs:
                    raise Exception("必填参数, ts_code")
                if kwargs.get("offset", 0) > 0:
                    return []
                return [
                    {
                        "ts_code": kwargs["ts_code"],
                        "ann_date": "20260425",
                        "end_date": "20260331",
                        "total_revenue": "1000",
                        "oper_cost": "600",
                        "biz_tax_surchg": "10",
                        "sell_exp": "20",
                        "admin_exp": "30",
                        "rd_exp": "40",
                        "fin_exp": "10",
                    }
                ]

            def cashflow(self, **kwargs):
                self.calls.append(("cashflow", kwargs))
                if "ts_code" not in kwargs:
                    raise Exception("必填参数, ts_code")
                if kwargs.get("offset", 0) > 0:
                    return []
                return [
                    {
                        "ts_code": kwargs["ts_code"],
                        "ann_date": "20260425",
                        "end_date": "20260331",
                        "n_cashflow_act": "580",
                    }
                ]

            def forecast(self, **kwargs):
                self.calls.append(("forecast", kwargs))
                return []

            def daily_basic(self, **kwargs):
                self.calls.append(("daily_basic", kwargs))
                if kwargs.get("offset", 0) > 0:
                    return []
                return [
                    {"ts_code": "600000.SH", "trade_date": "20260529", "total_mv": "1200", "circ_mv": "900"},
                    {"ts_code": "000001.SZ", "trade_date": "20260529", "total_mv": "900", "circ_mv": "700"},
                ]

        pro = FakePro()
        bundle = fetch_tushare_rows_from_client(
            pro=pro,
            symbols=[
                StockFinancialSymbol(code="600000", exchange="SH"),
                StockFinancialSymbol(code="000001", exchange="SZ"),
            ],
            source_trade_date="20260529",
            announcement_dates=["20260425"],
        )

        self.assertEqual(len(bundle["financial_rows"]), 2)
        self.assertEqual({row["stock_identity_key"] for row in bundle["financial_rows"]}, {"stock:SH:600000", "stock:SZ:000001"})
        per_symbol_calls = [
            kwargs for name, kwargs in pro.calls if name in {"income", "cashflow"} and kwargs.get("ts_code")
        ]
        self.assertEqual({kwargs["ts_code"] for kwargs in per_symbol_calls}, {"600000.SH", "000001.SZ"})
        self.assertEqual(bundle["stats"]["tushare_income_ok_count"], 2)
        self.assertEqual(bundle["stats"]["tushare_cashflow_ok_count"], 2)
        self.assertEqual(bundle["source_errors"], [])

    def test_tushare_per_symbol_fetch_accepts_bounded_concurrency(self) -> None:
        class FakePro:
            def income(self, **kwargs):
                if kwargs.get("offset", 0) > 0:
                    return []
                return [
                    {
                        "ts_code": kwargs["ts_code"],
                        "ann_date": "20260425",
                        "end_date": "20260331",
                        "total_revenue": "1000",
                        "oper_cost": "600",
                        "biz_tax_surchg": "10",
                        "admin_exp": "30",
                        "fin_exp": "10",
                    }
                ]

            def cashflow(self, **kwargs):
                if kwargs.get("offset", 0) > 0:
                    return []
                return [
                    {
                        "ts_code": kwargs["ts_code"],
                        "ann_date": "20260425",
                        "end_date": "20260331",
                        "n_cashflow_act": "580",
                    }
                ]

            def forecast(self, **kwargs):
                return []

            def daily_basic(self, **kwargs):
                if kwargs.get("offset", 0) > 0:
                    return []
                return [{"ts_code": "600000.SH", "trade_date": "20260529", "total_mv": "1200"}]

        bundle = fetch_tushare_rows_from_client(
            pro=FakePro(),
            symbols=[StockFinancialSymbol(code="600000", exchange="SH")],
            source_trade_date="20260529",
            tushare_concurrency=2,
        )

        self.assertEqual(len(bundle["financial_rows"]), 1)
        self.assertEqual(bundle["stats"]["tushare_income_ok_count"], 1)

    def test_empty_tushare_financial_cache_entry_is_not_valid_hit(self) -> None:
        entry = cached_tushare_symbol_entry(
            {
                "600000.SH": {
                    "source_trade_date": "20260529",
                    "income_rows": [],
                    "cashflow_rows": [],
                    "forecast_rows": [],
                }
            },
            "600000.SH",
            "20260529",
        )

        self.assertIsNone(entry)

    def test_tushare_cashflow_falls_back_to_same_report_period_when_ann_date_differs(self) -> None:
        class FakePro:
            def income(self, **kwargs):
                if kwargs.get("offset", 0) > 0:
                    return []
                return [
                    {
                        "ts_code": "600000.SH",
                        "ann_date": "20260425",
                        "end_date": "20260331",
                        "total_revenue": "1000",
                        "oper_cost": "600",
                        "biz_tax_surchg": "10",
                        "sell_exp": "20",
                        "admin_exp": "30",
                        "rd_exp": "40",
                        "fin_exp": "10",
                    }
                ]

            def cashflow(self, **kwargs):
                if kwargs.get("offset", 0) > 0:
                    return []
                return [{"ts_code": "600000.SH", "ann_date": "20260426", "end_date": "20260331", "n_cashflow_act": "580"}]

            def forecast(self, **kwargs):
                return []

            def daily_basic(self, **kwargs):
                return [{"ts_code": "600000.SH", "trade_date": "20260529", "total_mv": "1200"}]

        bundle = fetch_tushare_rows_from_client(
            pro=FakePro(),
            symbols=[StockFinancialSymbol(code="600000", exchange="SH")],
            source_trade_date="20260529",
        )

        self.assertEqual(bundle["financial_rows"][0]["operating_cashflow"], "580")
        self.assertEqual(bundle["financial_rows"][0]["cashflow_merge_strategy"], "report_period")

    def test_expense_fallbacks_warn_but_do_not_block_source_bundle(self) -> None:
        row = tdx_row("stock:SH:600000")
        row["rd_expense"] = None
        row["selling_expense"] = None

        report = build_source_bundle_report(
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000"],
            tdx_rows=[row],
            tushare_rows=[],
            daily_basic_rows=[{"stock_identity_key": "stock:SH:600000", "total_mv": "1000"}],
            forecast_rows=[],
            baseline={"conflicts": {"batch_conflict": 0, "quality_conflict": 0, "active_conflict": 0, "target_source_version_rows": 0}},
        )

        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["source_coverage"]["missing_line_item_count"], 0)
        self.assertEqual(report["source_coverage"]["warning_distribution"]["rd_expense_missing_fallback_zero"], 1)
        self.assertEqual(report["source_coverage"]["warning_distribution"]["selling_expense_missing_fallback_zero"], 1)
        self.assertEqual(report["rows_sample"][0]["rd_expense"], "0")
        self.assertEqual(report["rows_sample"][0]["selling_expense"], "0")
        self.assertIn("rd_expense_missing_fallback_zero", report["rows_sample"][0]["financial_warning_json"]["warnings"])
        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertGreaterEqual(report["quality"]["p1_count"], 1)

    def test_operating_cashflow_missing_warns_but_does_not_block_source_bundle(self) -> None:
        row = tdx_row("stock:SH:600000")
        row["operating_cashflow"] = None

        report = build_source_bundle_report(
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000"],
            tdx_rows=[row],
            tushare_rows=[],
            daily_basic_rows=[{"stock_identity_key": "stock:SH:600000", "total_mv": "1000"}],
            forecast_rows=[],
            baseline={"conflicts": {"batch_conflict": 0, "quality_conflict": 0, "active_conflict": 0, "target_source_version_rows": 0}},
        )

        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["source_coverage"]["missing_line_item_count"], 0)
        self.assertEqual(report["source_coverage"]["warning_distribution"]["operating_cashflow_missing_latest"], 1)

    def test_non_finite_interest_alias_continues_to_finance_expense(self) -> None:
        row = tdx_row("stock:SH:600000")
        row["interest_expense"] = "nan"
        row["finance_expense"] = "15"

        report = build_source_bundle_report(
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000"],
            tdx_rows=[row],
            tushare_rows=[],
            daily_basic_rows=[{"stock_identity_key": "stock:SH:600000", "total_mv": "1000"}],
            forecast_rows=[],
            baseline={"conflicts": {"batch_conflict": 0, "quality_conflict": 0, "active_conflict": 0, "target_source_version_rows": 0}},
        )

        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["source_coverage"]["missing_line_item_count"], 0)

    def test_default_probe_selection_is_bounded_to_ten_symbols(self) -> None:
        symbols = [StockFinancialSymbol(code=f"{idx:06d}", exchange="SH") for idx in range(30)]

        selected, metadata = select_probe_symbols(symbols, max_symbols=None, symbol_shard=None, full_fetch_confirmed=False)

        self.assertEqual(len(selected), 10)
        self.assertEqual(metadata["selection_mode"], "small_sample")
        self.assertFalse(metadata["full_fetch_confirmed"])

    def test_symbol_shard_filters_before_sample_cap(self) -> None:
        symbols = [StockFinancialSymbol(code=f"{idx:06d}", exchange="SH") for idx in range(10)]

        selected, metadata = select_probe_symbols(symbols, max_symbols=10, symbol_shard="2/3", full_fetch_confirmed=False)

        self.assertEqual([symbol.code for symbol in selected], ["000001", "000004", "000007"])
        self.assertEqual(metadata["symbol_shard"], "2/3")
        self.assertEqual(parse_symbol_shard("2/3"), (2, 3))

    def test_tushare_cache_avoids_repeated_symbol_requests(self) -> None:
        class FakePro:
            def __init__(self) -> None:
                self.calls = []

            def income(self, **kwargs):
                self.calls.append(("income", kwargs))
                return [{"ts_code": "600000.SH", "ann_date": "20260425", "end_date": "20260331", "total_revenue": "100"}]

            def cashflow(self, **kwargs):
                self.calls.append(("cashflow", kwargs))
                return [{"ts_code": "600000.SH", "ann_date": "20260425", "end_date": "20260331", "n_cashflow_act": "50"}]

            def forecast(self, **kwargs):
                self.calls.append(("forecast", kwargs))
                return []

            def daily_basic(self, **kwargs):
                self.calls.append(("daily_basic", kwargs))
                return [{"ts_code": "600000.SH", "trade_date": "20260529", "total_mv": "1000"}]

        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "probe_cache.json"
            symbols = [StockFinancialSymbol(code="600000", exchange="SH")]
            first = fetch_tushare_rows_from_client(pro=FakePro(), symbols=symbols, source_trade_date="20260529", resume_cache_path=cache_path)
            second_pro = FakePro()
            second = fetch_tushare_rows_from_client(pro=second_pro, symbols=symbols, source_trade_date="20260529", resume_cache_path=cache_path)

        self.assertEqual(len(first["financial_rows"]), 1)
        self.assertEqual(len(second["financial_rows"]), 1)
        self.assertEqual(second_pro.calls, [])
        self.assertTrue(second["stats"]["cache_hit_count"] >= 1)

    def test_tdx_primary_is_preferred_and_tushare_fills_missing_identity(self) -> None:
        report = build_source_bundle_report(
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000", "stock:SZ:000001"],
            tdx_rows=[
                tdx_row("stock:SH:600000"),
                {**tdx_row("stock:SZ:000001"), "announcement_date": "20260601"},
            ],
            tushare_rows=[
                {**tdx_row("stock:SH:600000"), "source_type": SOURCE_TUSHARE_FALLBACK, "operating_revenue": "1"},
                {**tdx_row("stock:SZ:000001"), "source_type": SOURCE_TUSHARE_FALLBACK},
            ],
            daily_basic_rows=[
                {"stock_identity_key": "stock:SH:600000", "total_mv": "1000"},
                {"stock_identity_key": "stock:SZ:000001", "total_mv": "2000"},
            ],
            forecast_rows=[{"stock_identity_key": "stock:SZ:000001", "forecast_type": "预增", "announcement_date": "20260520"}],
            baseline={"conflicts": {"batch_conflict": 0, "quality_conflict": 0, "active_conflict": 0, "target_source_version_rows": 0}},
        )

        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["source_coverage"]["tdx_primary_count"], 1)
        self.assertEqual(report["source_coverage"]["tushare_fallback_count"], 1)
        self.assertEqual(report["source_coverage"]["future_excluded_count"], 1)
        self.assertEqual(report["source_coverage"]["missing_line_item_count"], 0)
        self.assertEqual(report["source_coverage"]["forecast_coverage_count"], 1)
        self.assertEqual(report["quality"]["p0_count"], 0)

    def test_missing_line_items_block_bundle_readiness(self) -> None:
        row = tdx_row("stock:SH:600000")
        row.pop("operating_cost")
        report = build_source_bundle_report(
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000"],
            tdx_rows=[row],
            tushare_rows=[],
            daily_basic_rows=[{"stock_identity_key": "stock:SH:600000", "total_mv": "1000"}],
            forecast_rows=[],
            baseline={"conflicts": {"batch_conflict": 0, "quality_conflict": 0, "active_conflict": 0, "target_source_version_rows": 0}},
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("canonical_source_line_items_missing", report["blockers"])
        self.assertEqual(report["source_coverage"]["missing_line_item_count"], 1)
        self.assertEqual(report["quality"]["p0_count"], 1)

    def test_latest_missing_core_line_items_warns_when_prior_period_is_usable(self) -> None:
        latest = tdx_row("stock:SH:600000", report_period="20260331")
        latest.pop("taxes_and_surcharges")
        prior = tdx_row("stock:SH:600000", report_period="20251231")
        report = build_source_bundle_report(
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000"],
            tdx_rows=[latest, prior],
            tushare_rows=[],
            daily_basic_rows=[{"stock_identity_key": "stock:SH:600000", "total_mv": "1000"}],
            forecast_rows=[],
            baseline={"conflicts": {"batch_conflict": 0, "quality_conflict": 0, "active_conflict": 0, "target_source_version_rows": 0}},
        )

        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["source_coverage"]["missing_line_item_count"], 0)
        self.assertEqual(report["source_coverage"]["latest_core_line_item_missing_fallback_count"], 1)
        self.assertEqual(report["source_coverage"]["warning_distribution"]["latest_core_line_items_missing_fallback_prior_period"], 1)
        self.assertEqual(report["quality"]["p0_count"], 0)

    def test_finance_sector_missing_operating_cost_warns_without_blocking(self) -> None:
        row = tdx_row("stock:SH:600000")
        row.pop("operating_cost")
        report = build_source_bundle_report(
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000"],
            tdx_rows=[row],
            tushare_rows=[],
            daily_basic_rows=[{"stock_identity_key": "stock:SH:600000", "total_mv": "1000", "industry": "银行"}],
            forecast_rows=[],
            baseline={"conflicts": {"batch_conflict": 0, "quality_conflict": 0, "active_conflict": 0, "target_source_version_rows": 0}},
        )

        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["source_coverage"]["missing_line_item_count"], 0)
        self.assertEqual(report["source_coverage"]["finance_sector_policy_warning_count"], 1)
        self.assertEqual(report["source_coverage"]["warning_distribution"]["finance_sector_policy_not_supported_v1"], 1)
        self.assertIn("finance_sector_policy_not_supported_v1", report["rows_sample"][0]["financial_warning_json"]["warnings"])
        self.assertEqual(report["quality"]["p0_count"], 0)

    def test_pre_revenue_missing_revenue_and_cost_warns_without_blocking(self) -> None:
        row = tdx_row("stock:SH:688759")
        row.pop("operating_revenue")
        row.pop("operating_cost")
        report = build_source_bundle_report(
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:688759"],
            tdx_rows=[row],
            tushare_rows=[],
            daily_basic_rows=[{"stock_identity_key": "stock:SH:688759", "total_mv": "1000", "industry": "生物制药"}],
            forecast_rows=[],
            baseline={"conflicts": {"batch_conflict": 0, "quality_conflict": 0, "active_conflict": 0, "target_source_version_rows": 0}},
        )

        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["source_coverage"]["missing_line_item_count"], 0)
        self.assertEqual(report["source_coverage"]["pre_revenue_policy_warning_count"], 1)
        self.assertEqual(report["source_coverage"]["warning_distribution"]["pre_revenue_or_missing_revenue_cost"], 1)
        self.assertIn("pre_revenue_or_missing_revenue_cost", report["rows_sample"][0]["financial_warning_json"]["warnings"])
        self.assertEqual(report["quality"]["p0_count"], 0)

    def test_missing_announcement_without_asof_proof_is_excluded(self) -> None:
        report = build_source_bundle_report(
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000"],
            tdx_rows=[{**tdx_row("stock:SH:600000"), "announcement_date": ""}],
            tushare_rows=[],
            daily_basic_rows=[{"stock_identity_key": "stock:SH:600000", "total_mv": "1000"}],
            forecast_rows=[],
            baseline={"conflicts": {"batch_conflict": 0, "quality_conflict": 0, "active_conflict": 0, "target_source_version_rows": 0}},
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["source_coverage"]["missing_announcement_date_excluded_count"], 1)
        self.assertIn("canonical_source_missing_identity", report["blockers"])

    def test_execute_flag_is_rejected(self) -> None:
        with self.assertRaises(StockFinancialCanonicalSourceBundleBlocked):
            validate_source_bundle_request(execute_requested=True)

    def test_runner_main_blocks_execute_before_database_work(self) -> None:
        runner = load_runner_module()
        exit_code = runner.main(["--execute"], dependencies={"build_snapshot_from_db": lambda **_: self.fail("db should not be touched")})

        self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()
