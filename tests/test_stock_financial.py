from decimal import Decimal
import unittest
from typing import Any, Mapping, Sequence

from ashare_v3.ingestion.stock_financial import (
    StockFinancialSymbol,
    normalize_stock_financial_metrics_row,
    run_stock_financial_ingestion_dry_run,
)


class FakeFinancialSource:
    def fetch_stock_financial_metrics(
        self,
        *,
        symbols: Sequence[StockFinancialSymbol],
        asof_date: str,
    ) -> Sequence[Mapping[str, Any]]:
        return [
            {
                "code": symbols[0].code,
                "updated_date": asof_date,
                "zhuyingshouru": "1000000",
                "jinglirun": "10000",
                "jingzichan": "500000",
                "meigujingzichan": "3.21",
                "meigushouyi": "0.12",
            }
        ]


class MissingFinancialSource(FakeFinancialSource):
    def fetch_stock_financial_metrics(
        self,
        *,
        symbols: Sequence[StockFinancialSymbol],
        asof_date: str,
    ) -> Sequence[Mapping[str, Any]]:
        return []


class ExtraUniverseFinancialSource(FakeFinancialSource):
    def fetch_stock_financial_metrics(
        self,
        *,
        symbols: Sequence[StockFinancialSymbol],
        asof_date: str,
    ) -> Sequence[Mapping[str, Any]]:
        return [
            {
                "code": "600000",
                "updated_date": asof_date,
                "jinglirun": "100",
            }
        ]


class StockFinancialTest(unittest.TestCase):
    def test_stock_financial_dry_run_passes(self) -> None:
        result = run_stock_financial_ingestion_dry_run(
            FakeFinancialSource(),
            symbols=[StockFinancialSymbol(code="000001", exchange="SZ", name="平安银行")],
            asof_date="20260521",
            version="v1",
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.batches["stock_financial_metrics_fact"], "stock_financial_20260521_v1")
        row = result.stock_financial_metrics_rows[0]
        self.assertEqual(row["stock_identity_key"], "stock:SZ:000001")
        self.assertEqual(row["ts_code"], "000001.SZ")
        self.assertEqual(row["total_revenue"], Decimal("1000000"))
        self.assertEqual(row["net_profit"], Decimal("10000"))
        self.assertFalse(result.summary()["will_connect_database"])

    def test_normalizer_maps_tdx_fields(self) -> None:
        row = normalize_stock_financial_metrics_row(
            {
                "code": "600000",
                "updated_date": "2026-05-21",
                "report_period": "20251231",
                "roe": "9.5",
                "or_yoy": "1.2",
                "netprofit_yoy": "2.3",
                "zhuyingshouru": "10,000",
                "jinglirun": "200",
                "jingzichan": "300",
                "meigushouyi": "0.10",
                "meigujingzichan": "5.60",
            },
            source="mootdx.finance",
            source_batch_id="stock_financial_20260521_v1",
            source_version="stock_financial_20260521_v1",
            fallback_asof_date="20260521",
        )

        self.assertEqual(row["stock_identity_key"], "stock:SH:600000")
        self.assertEqual(row["asof_date"], "20260521")
        self.assertEqual(row["report_period"], "20251231")
        self.assertEqual(row["revenue_yoy"], Decimal("1.2"))
        self.assertEqual(row["profit_yoy"], Decimal("2.3"))
        self.assertEqual(row["total_revenue"], Decimal("10000"))

    def test_missing_financial_row_fails_requested_key_gate(self) -> None:
        result = run_stock_financial_ingestion_dry_run(
            MissingFinancialSource(),
            symbols=[StockFinancialSymbol(code="000001", exchange="SZ")],
            asof_date="20260521",
            version="v1",
        )

        self.assertFalse(result.passed)
        failed_gate_names = {gate.gate_name for gate in result.quality_gates if not gate.passed}
        self.assertIn("stock_financial_requested_keys_present", failed_gate_names)

    def test_universe_alignment_fails_for_unexpected_stock(self) -> None:
        result = run_stock_financial_ingestion_dry_run(
            ExtraUniverseFinancialSource(),
            symbols=[StockFinancialSymbol(code="000001", exchange="SZ")],
            asof_date="20260521",
            version="v1",
            stock_universe_keys=["stock:SZ:000001"],
        )

        self.assertFalse(result.passed)
        failed_gate_names = {gate.gate_name for gate in result.quality_gates if not gate.passed}
        self.assertIn("stock_financial_universe_alignment", failed_gate_names)

    def test_88xxxx_stock_financial_rejected_by_normalizer(self) -> None:
        with self.assertRaises(ValueError):
            normalize_stock_financial_metrics_row(
                {"code": "881001", "updated_date": "20260521", "jinglirun": "1"},
                source="mootdx.finance",
                source_batch_id="stock_financial_20260521_v1",
                source_version="stock_financial_20260521_v1",
                fallback_asof_date="20260521",
            )


if __name__ == "__main__":
    unittest.main()
