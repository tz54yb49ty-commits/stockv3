import json
import unittest
from pathlib import Path

from ashare_v3.ingestion.stock_financial_002831_tdx_parity_repair import (
    EXPECTED_ROW_COUNT,
    TARGET_IDENTITY_KEY,
    TARGET_SOURCE_VERSION,
    StockFinancial002831RepairBlocked,
    build_repair_commit_plan,
    load_source_proof,
    validate_execute_flags,
    validate_rollback_sql_static,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROOF_PATH = PROJECT_ROOT / "docs" / "N1_STOCK_FINANCIAL_002831_TDX_FULL_LINE_ITEM_SOURCE_PROOF.json"
ROLLBACK_PATH = PROJECT_ROOT / "sql" / "N1_stock_financial_002831_tdx_parity_repair_20260615_rollback.sql"


def v2_row(identity_key: str = TARGET_IDENTITY_KEY) -> dict:
    code = identity_key.rsplit(":", 1)[-1]
    exchange = identity_key.split(":")[1]
    return {
        "stock_identity_key": identity_key,
        "asof_date": "20260615",
        "source_trade_date": "20260615",
        "announcement_date": "20260428",
        "report_period": "20260331",
        "ts_code": f"{code}.{exchange}",
        "code": code,
        "exchange": exchange,
        "roe": None,
        "revenue_yoy": "2.550315514",
        "profit_yoy": "15.7585516772",
        "total_revenue": "3793341905.18",
        "net_profit": None,
        "net_assets": None,
        "eps": None,
        "bps": None,
        "pe_core": "0.0009382111",
        "total_mv": "3929409.6385",
        "circ_mv": "2178376.9994",
        "score": "65.6617734382",
        "warning": "forecast_missing;interest_expense_missing_finance_expense_used;tushare_fallback_used",
        "quality_status": "warning",
        "source": "stock_financial_canonical.tdx_mootdx_first.tushare_fallback",
        "source_batch_id": "stock_financial_canonical_20260615_v1",
        "source_version": "stock_financial_20260615_v2",
        "raw_payload": {
            "latest_source": {
                "source_type": "tushare_fallback",
                "finance_expense": "68186034.99",
                "interest_expense": None,
            }
        },
        "cash_realization_rate": "2.2436682482",
        "revenue_yoy_pct": "2.550315514",
        "core_profit_yoy_pct": "15.7585516772",
        "report_core_revenue": "3793341905.18",
        "report_core_profit": "293144510.81",
        "core_profit_ttm": "4188193627.27",
        "core_gt_revenue_yoy": True,
        "revenue_growth_streak_q": 9,
        "core_growth_streak_q": 1,
        "core_gt_revenue_streak_q": 0,
        "forecast_type": None,
        "forecast_score": "0",
        "score_breakdown_json": {"old": "value"},
        "financial_warning_json": {"warnings": ["forecast_missing", "tushare_fallback_used"]},
        "financial_metric_version": "financial_metric_v1",
    }


class StockFinancial002831TdxParityRepairTest(unittest.TestCase):
    def test_source_proof_parses_and_passes_asof(self) -> None:
        proof = load_source_proof(PROOF_PATH, source_trade_date="20260615", stock_identity_key=TARGET_IDENTITY_KEY)

        self.assertEqual(proof["source_type"], "tdx_financial_package")
        self.assertEqual(proof["line_items"]["interest_expense"], "19744658")
        self.assertEqual(proof["announcement_date"], "20260428")
        self.assertLessEqual(proof["announcement_date"], "20260615")
        self.assertEqual(proof["expected_metrics"]["score"], "87")

    def test_build_repair_commit_plan_has_full_rows_and_exactly_one_semantic_change(self) -> None:
        proof = load_source_proof(PROOF_PATH, source_trade_date="20260615", stock_identity_key=TARGET_IDENTITY_KEY)
        previous_rows = [v2_row()]
        previous_rows.extend(v2_row(f"stock:SH:{i:06d}") for i in range(1, EXPECTED_ROW_COUNT))

        plan = build_repair_commit_plan(
            previous_rows=previous_rows,
            proof=proof,
            source_trade_date="20260615",
            previous_source_version="stock_financial_20260615_v2",
            target_source_version=TARGET_SOURCE_VERSION,
        )

        self.assertEqual(plan["row_counts"]["stock_financial_metrics_fact"], EXPECTED_ROW_COUNT)
        self.assertEqual(plan["semantic_changed_rows_count"], 1)
        repaired = [row for row in plan["stock_financial_rows"] if row["stock_identity_key"] == TARGET_IDENTITY_KEY][0]
        self.assertEqual(repaired["source_version"], TARGET_SOURCE_VERSION)
        self.assertEqual(repaired["source_batch_id"], "stock_financial_002831_tdx_parity_repair_20260615_v1")
        self.assertEqual(repaired["report_core_profit"], "341586050")
        self.assertEqual(repaired["core_profit_ttm"], "1940382164")
        self.assertEqual(repaired["pe_core"], "20.2506996374")
        self.assertEqual(repaired["score"], "87")
        self.assertEqual(repaired["raw_payload"]["latest_source"]["source_type"], "tdx_financial_package")
        self.assertEqual(repaired["raw_payload"]["latest_source"]["interest_expense"], "19744658")
        self.assertFalse(repaired["raw_payload"]["latest_source"]["finance_expense_used_as_interest"])

    def test_missing_execute_confirmations_block_before_write(self) -> None:
        with self.assertRaises(StockFinancial002831RepairBlocked):
            validate_execute_flags(execute_requested=False, user_confirmed=True, postgres_commit_enabled=True)
        with self.assertRaises(StockFinancial002831RepairBlocked):
            validate_execute_flags(execute_requested=True, user_confirmed=False, postgres_commit_enabled=True)
        with self.assertRaises(StockFinancial002831RepairBlocked):
            validate_execute_flags(execute_requested=True, user_confirmed=True, postgres_commit_enabled=False)

    def test_rollback_sql_static_safety(self) -> None:
        result = validate_rollback_sql_static(ROLLBACK_PATH)

        self.assertTrue(result["raise_before_delete_or_update"])
        self.assertEqual(result["forbidden_tokens"], [])

    def test_source_proof_json_is_valid(self) -> None:
        payload = json.loads(PROOF_PATH.read_text())

        self.assertEqual(payload["stock_identity_key"], TARGET_IDENTITY_KEY)
        self.assertEqual(payload["source_trade_date"], "20260615")


if __name__ == "__main__":
    unittest.main()
