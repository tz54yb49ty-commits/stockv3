import json
import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_MD = PROJECT_ROOT / "docs" / "N1_STOCK_FINANCIAL_CANONICAL_METRICS_SPEC.md"
READINESS_JSON = PROJECT_ROOT / "docs" / "N1_stock_financial_canonical_metrics_schema_readiness.json"
CONTRACT_MD = PROJECT_ROOT / "docs" / "N1_STOCK_FINANCIAL_CANONICAL_METRICS_DRY_RUN_CONTRACT.md"
CONTRACT_JSON = PROJECT_ROOT / "docs" / "N1_stock_financial_canonical_metrics_dry_run_contract.json"
MIGRATION_SQL = PROJECT_ROOT / "sql" / "028_stock_financial_canonical_metrics_schema.sql"
ROLLBACK_SQL = PROJECT_ROOT / "sql" / "028_stock_financial_canonical_metrics_schema_rollback.sql"

CANONICAL_FIELDS = (
    "cash_realization_rate",
    "revenue_yoy_pct",
    "core_profit_yoy_pct",
    "report_core_revenue",
    "report_core_profit",
    "core_profit_ttm",
    "core_gt_revenue_yoy",
    "revenue_growth_streak_q",
    "core_growth_streak_q",
    "core_gt_revenue_streak_q",
    "forecast_type",
    "forecast_score",
    "score_breakdown_json",
    "financial_warning_json",
    "financial_metric_version",
)

FORBIDDEN_TABLE_PATTERNS = (
    r"\bcondition_",
    r"\bcommon_condition_",
    r"\bmarket_data_",
    r"\btrigger_",
    r"\baction_",
    r"\bvoice",
    r"\bmobile",
    r"\bsim",
)


class StockFinancialCanonicalMetricsDesignTest(unittest.TestCase):
    def test_migration_is_additive_stock_financial_schema_only(self) -> None:
        sql = strip_sql_comments(MIGRATION_SQL.read_text(encoding="utf-8"))

        self.assertIn("BEGIN;", sql)
        self.assertIn("COMMIT;", sql)
        self.assertEqual(
            set(re.findall(r"ALTER\s+TABLE\s+([a-z_]+)", sql, flags=re.IGNORECASE)),
            {"stock_financial_metrics_fact"},
        )
        self.assertNotRegex(sql, r"\b(INSERT|UPDATE|DELETE|TRUNCATE|COPY|CREATE\s+TABLE|DROP\s+TABLE)\b")
        for field in CANONICAL_FIELDS:
            self.assertIn(f"ADD COLUMN IF NOT EXISTS {field}", sql)
        for pattern in FORBIDDEN_TABLE_PATTERNS:
            self.assertIsNone(re.search(pattern, sql, flags=re.IGNORECASE), pattern)
        self.assertNotIn("locked_target_price", sql)
        self.assertNotIn("target_lock_status", sql)

    def test_migration_constraints_encode_canonical_quality_rules(self) -> None:
        sql = strip_sql_comments(MIGRATION_SQL.read_text(encoding="utf-8"))

        self.assertIn("score IS NULL OR (score >= 0 AND score <= 100)", sql)
        self.assertIn("forecast_score IS NULL OR (forecast_score >= 0 AND forecast_score <= 3)", sql)
        for field in ("revenue_growth_streak_q", "core_growth_streak_q", "core_gt_revenue_streak_q"):
            self.assertIn(f"{field} IS NULL OR {field} >= 0", sql)
        self.assertIn("announcement_date IS NULL OR announcement_date <= source_trade_date", sql)
        self.assertIn("financial_metric_version IS NULL OR financial_metric_version IN ('financial_metric_v1')", sql)
        self.assertIn("score_breakdown_json IS NULL OR jsonb_typeof(score_breakdown_json) = 'object'", sql)
        self.assertIn("financial_warning_json IS NULL OR jsonb_typeof(financial_warning_json) = 'object'", sql)

    def test_rollback_only_removes_028_stock_financial_columns_and_constraints(self) -> None:
        sql = strip_sql_comments(ROLLBACK_SQL.read_text(encoding="utf-8"))

        self.assertIn("BEGIN;", sql)
        self.assertIn("COMMIT;", sql)
        self.assertEqual(
            set(re.findall(r"ALTER\s+TABLE\s+([a-z_]+)", sql, flags=re.IGNORECASE)),
            {"stock_financial_metrics_fact"},
        )
        self.assertNotRegex(sql, r"\b(INSERT|UPDATE|DELETE|TRUNCATE|COPY|CREATE\s+TABLE)\b")
        for field in CANONICAL_FIELDS:
            self.assertIn(f"DROP COLUMN IF EXISTS {field}", sql)

    def test_readiness_documents_current_gap_and_no_execute(self) -> None:
        readiness = json.loads(READINESS_JSON.read_text(encoding="utf-8"))

        self.assertEqual(readiness["result"], "DESIGN_PASS")
        self.assertEqual(readiness["layer_role"], "N1_ingestion")
        self.assertFalse(readiness["migration_execute_allowed"])
        self.assertFalse(readiness["writes_performed"])
        self.assertFalse(readiness["backfill_performed"])
        self.assertEqual(readiness["target_table"], "stock_financial_metrics_fact")
        self.assertEqual(readiness["existing_canonical_coverage"]["fully_supported"], False)
        for field in CANONICAL_FIELDS:
            self.assertIn(field, readiness["new_nullable_fields"])
        self.assertEqual(readiness["source_version_strategy"]["new_active_source_version"], "stock_financial_20260529_v2")
        self.assertEqual(readiness["source_version_strategy"]["previous_source_version"], "stock_financial_20260529_v1")

    def test_dry_run_contract_freezes_asof_and_source_priority(self) -> None:
        contract = json.loads(CONTRACT_JSON.read_text(encoding="utf-8"))
        markdown = CONTRACT_MD.read_text(encoding="utf-8")

        self.assertEqual(contract["result"], "DESIGN_PASS")
        self.assertEqual(contract["layer_role"], "N1_ingestion")
        self.assertEqual(contract["source_priority"], ["tdx_mootdx_finance", "tushare_fallback"])
        self.assertTrue(contract["asof_rules"]["exclude_announcement_after_source_trade_date"])
        self.assertTrue(contract["asof_rules"]["exclude_unproven_missing_announcement_date"])
        self.assertFalse(contract["side_effects"]["writes_performed"])
        self.assertFalse(contract["side_effects"]["writes_condition_tables"])
        for key in (
            "tdx_primary_count",
            "tushare_fallback_count",
            "asof_excluded_future_rows",
            "missing_announcement_date_excluded_rows",
            "interest_expense_missing_fallback_count",
            "ttm_annualized_count",
            "forecast_coverage_count",
            "score_distribution",
            "warning_distribution",
            "P0/P1/P2",
        ):
            self.assertIn(key, contract["dry_run_summary_schema"])
        self.assertIn("TDX/Mootdx 财务包优先", markdown)
        self.assertIn("N2 不得重算", markdown)

    def test_metric_definitions_cover_requested_calculator_behaviors(self) -> None:
        spec = SPEC_MD.read_text(encoding="utf-8")

        required_phrases = (
            "report_core_profit",
            "经营活动现金流 / report_core_profit",
            "core_profit_ttm",
            "已有单季核心利润合计 * 4 / 已有季度数",
            "total_mv / core_profit_ttm",
            "revenue_yoy_pct",
            "core_profit_yoy_pct",
            "core_gt_revenue_yoy",
            "revenue_growth_streak_q",
            "core_growth_streak_q",
            "core_gt_revenue_streak_q",
            "forecast_score",
            "score 满分封顶 100",
            "financial_warning_json",
        )
        for phrase in required_phrases:
            self.assertIn(phrase, spec)

    def test_n2_handoff_is_read_only_transparent_pass_through(self) -> None:
        contract = json.loads(CONTRACT_JSON.read_text(encoding="utf-8"))

        self.assertEqual(contract["n2_handoff"]["mode"], "read_active_stock_financial_only")
        self.assertTrue(contract["n2_handoff"]["must_not_recompute_financial_metrics"])
        self.assertIn("stock_condition_basis", contract["n2_handoff"]["future_reader_tables"])
        self.assertIn("stock_condition_display_basis", contract["n2_handoff"]["future_reader_tables"])


def strip_sql_comments(sql: str) -> str:
    lines = []
    for line in sql.splitlines():
        stripped = line.split("--", 1)[0]
        if stripped.strip():
            lines.append(stripped)
    return "\n".join(lines)


if __name__ == "__main__":
    unittest.main()
