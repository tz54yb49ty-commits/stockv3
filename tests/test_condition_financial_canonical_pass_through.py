import re
import unittest
from pathlib import Path

from ashare_v3.condition.basis import (
    DateContext,
    STOCK_CANONICAL_FINANCIAL_FIELDS,
    STOCK_FINANCIAL_COMPATIBILITY_FIELDS,
    STOCK_FINANCIAL_JSON_FIELDS,
    make_stock_sample_basis,
)
from ashare_v3.condition.display_basis import stock_display_fields
from ashare_v3.condition.execute import (
    BOARD_BASIS_COLUMNS,
    BOARD_DISPLAY_COLUMNS,
    BOARD_POOL_COLUMNS,
    BOARD_SCOPE_COLUMNS,
    INDEX_BASIS_COLUMNS,
    INDEX_DISPLAY_COLUMNS,
    INDEX_POOL_COLUMNS,
    INDEX_SCOPE_COLUMNS,
    STOCK_BASIS_COLUMNS,
    STOCK_DISPLAY_COLUMNS,
    STOCK_POOL_COLUMNS,
    STOCK_SCOPE_COLUMNS,
    basis_insert_row,
    display_insert_row,
    pool_insert_row,
    scope_insert_row,
)
from ashare_v3.condition.execute_preflight import (
    STOCK_FINANCIAL_SCHEMA_COLUMNS,
    STOCK_FINANCIAL_SCHEMA_TABLES,
)
from ashare_v3.condition.pool import build_pool_rows_for_basis
from ashare_v3.condition.scope import make_stock_scope_row


MIGRATION_PATH = Path("sql/029_condition_stock_financial_canonical_columns_migration.sql")
ROLLBACK_PATH = Path("sql/029_condition_stock_financial_canonical_columns_rollback.sql")


class ConditionFinancialCanonicalPassThroughTest(unittest.TestCase):
    def test_stock_basis_passes_through_n1_canonical_financial_fields(self) -> None:
        basis = make_stock_sample_basis(financial_source_row(), sample_dates(), period_context={})

        for field in STOCK_CANONICAL_FINANCIAL_FIELDS:
            self.assertIn(field, basis)
        self.assertEqual(basis["cash_realization_rate"], "1.23")
        self.assertEqual(basis["revenue_yoy_pct"], "15.6")
        self.assertEqual(basis["core_profit_yoy_pct"], "22.1")
        self.assertEqual(basis["report_core_revenue"], "100000")
        self.assertEqual(basis["report_core_profit"], "30000")
        self.assertEqual(basis["core_profit_ttm"], "120000")
        self.assertTrue(basis["core_gt_revenue_yoy"])
        self.assertEqual(basis["revenue_growth_streak_q"], 3)
        self.assertEqual(basis["core_growth_streak_q"], 2)
        self.assertEqual(basis["core_gt_revenue_streak_q"], 2)
        self.assertEqual(basis["forecast_type"], "预增")
        self.assertEqual(basis["forecast_score"], "3")
        self.assertEqual(basis["score_breakdown_json"]["forecast"], "3")
        self.assertEqual(basis["financial_warning_json"]["warnings"], ["finance_sector_policy_not_supported_v1"])
        self.assertEqual(basis["financial_metric_version"], "financial_metric_v1")
        self.assertEqual(basis["financial_source_version"], "stock_financial_20260529_v2")
        for field in STOCK_FINANCIAL_COMPATIBILITY_FIELDS:
            self.assertEqual(basis[field], canonical_financial_payload()[field])

    def test_pool_scope_and_display_inherit_stock_financial_fields_without_recompute(self) -> None:
        basis = {
            **minimal_condition_basis_row(),
            **canonical_financial_payload(),
        }
        pool_row = build_pool_rows_for_basis("stock", basis)[0]
        scope_row = make_stock_scope_row(pool_row, sample_dates())
        display_fields = stock_display_fields(basis)

        for field in STOCK_CANONICAL_FINANCIAL_FIELDS + STOCK_FINANCIAL_COMPATIBILITY_FIELDS:
            self.assertEqual(pool_row[field], basis[field])
            self.assertEqual(scope_row[field], basis[field])
            self.assertEqual(display_fields[field], basis[field])

    def test_execute_column_lists_include_financial_fields_for_stock_only(self) -> None:
        stock_column_sets = (STOCK_BASIS_COLUMNS, STOCK_POOL_COLUMNS, STOCK_SCOPE_COLUMNS, STOCK_DISPLAY_COLUMNS)
        for columns in stock_column_sets:
            for field in STOCK_CANONICAL_FINANCIAL_FIELDS + STOCK_FINANCIAL_COMPATIBILITY_FIELDS:
                self.assertIn(field, columns)

        non_stock_columns = (
            INDEX_BASIS_COLUMNS,
            INDEX_POOL_COLUMNS,
            INDEX_SCOPE_COLUMNS,
            INDEX_DISPLAY_COLUMNS,
            BOARD_BASIS_COLUMNS,
            BOARD_POOL_COLUMNS,
            BOARD_SCOPE_COLUMNS,
            BOARD_DISPLAY_COLUMNS,
        )
        for columns in non_stock_columns:
            for field in STOCK_CANONICAL_FINANCIAL_FIELDS + STOCK_FINANCIAL_COMPATIBILITY_FIELDS:
                self.assertNotIn(field, columns)

    def test_execute_insert_rows_keep_financial_json_fields_as_jsonb_payloads(self) -> None:
        basis_row = {**minimal_condition_basis_row(), **canonical_financial_payload()}
        pool_row = {**build_pool_rows_for_basis("stock", basis_row)[0], "source_condition_basis_id": 1}
        scope_row = make_stock_scope_row(pool_row, sample_dates())
        display_row = {
            "stock_identity_key": "stock:SH:600000",
            "code": "600000",
            "exchange": "SH",
            "name": "浦发银行",
            **basis_row,
            **stock_display_fields(basis_row),
        }

        inserted_basis = basis_insert_row("stock", "run_x", basis_row, monitor_id=1)
        inserted_pool = pool_insert_row("stock", "run_x", pool_row, basis_id=1)
        inserted_scope = scope_insert_row("stock", "run_x", scope_row, {pool_row["condition_pool_ref"]: 1})
        inserted_display = display_insert_row("stock", display_row)

        for row in (inserted_basis, inserted_pool, inserted_scope, inserted_display):
            for field in STOCK_FINANCIAL_JSON_FIELDS:
                self.assertEqual(row[field].obj, canonical_financial_payload()[field])

    def test_schema_readiness_tracks_stock_financial_fields_on_four_stock_tables(self) -> None:
        self.assertEqual(
            STOCK_FINANCIAL_SCHEMA_TABLES,
            (
                "stock_condition_basis",
                "stock_condition_pool",
                "stock_minute_target_scope",
                "stock_condition_display_basis",
            ),
        )
        for field in STOCK_CANONICAL_FINANCIAL_FIELDS:
            self.assertIn(field, STOCK_FINANCIAL_SCHEMA_COLUMNS)

    def test_migration_draft_is_additive_nullable_stock_only(self) -> None:
        sql = MIGRATION_PATH.read_text(encoding="utf-8")
        executable_sql = strip_sql_comments(sql)

        self.assertIn("BEGIN;", sql)
        self.assertIn("COMMIT;", sql)
        self.assertNotRegex(executable_sql, r"\b(INSERT|UPDATE|DELETE|TRUNCATE|COPY|CREATE\s+TABLE|DROP\s+TABLE)\b")
        for table in STOCK_FINANCIAL_SCHEMA_TABLES:
            self.assertIn(f"ALTER TABLE {table}", sql)
        for table in ("index_condition_basis", "index_condition_pool", "board_condition_basis", "board_condition_pool"):
            self.assertNotIn(f"ALTER TABLE {table}", sql)
        for field in STOCK_CANONICAL_FINANCIAL_FIELDS:
            self.assertIn(f"ADD COLUMN IF NOT EXISTS {field}", sql)
        self.assertNotIn("locked_target_price", executable_sql)
        self.assertNotIn("target_lock_status", executable_sql)

    def test_rollback_draft_only_drops_added_stock_financial_columns(self) -> None:
        sql = ROLLBACK_PATH.read_text(encoding="utf-8")
        executable_sql = strip_sql_comments(sql)

        self.assertIn("BEGIN;", sql)
        self.assertIn("COMMIT;", sql)
        self.assertNotRegex(executable_sql, r"\b(INSERT|UPDATE|DELETE|TRUNCATE|COPY|CREATE\s+TABLE|DROP\s+TABLE)\b")
        for table in STOCK_FINANCIAL_SCHEMA_TABLES:
            self.assertIn(f"ALTER TABLE {table}", sql)
        for field in STOCK_CANONICAL_FINANCIAL_FIELDS:
            self.assertIn(f"DROP COLUMN IF EXISTS {field}", sql)


def sample_dates() -> DateContext:
    return DateContext(
        source_trade_date="20260529",
        source_prev_trade_date="20260528",
        for_trade_date="20260601",
        prev_trade_date="20260529",
        for_trade_calendar_row_exists=True,
    )


def financial_source_row() -> dict[str, object]:
    return {
        "stock_identity_key": "stock:SH:600000",
        "code": "600000",
        "exchange": "SH",
        "ts_code": "600000.SH",
        "name": "浦发银行",
        "is_st": False,
        "stock_status": "active",
        "official_daily_proof": True,
        "total_mv": "1200000",
        "circ_mv": "900000",
        "pe_core": "12.34",
        "score": "88",
        "financial_asof_date": "20260529",
        "financial_quality_status": "passed",
        "financial_source_version": "stock_financial_20260529_v2",
        "source_version": "stock_daily_20260529_v1",
        **canonical_financial_payload(),
    }


def canonical_financial_payload() -> dict[str, object]:
    return {
        "cash_realization_rate": "1.23",
        "revenue_yoy_pct": "15.6",
        "core_profit_yoy_pct": "22.1",
        "report_core_revenue": "100000",
        "report_core_profit": "30000",
        "core_profit_ttm": "120000",
        "core_gt_revenue_yoy": True,
        "revenue_growth_streak_q": 3,
        "core_growth_streak_q": 2,
        "core_gt_revenue_streak_q": 2,
        "forecast_type": "预增",
        "forecast_score": "3",
        "score_breakdown_json": {"core_profit": "10", "forecast": "3"},
        "financial_warning_json": {"warnings": ["finance_sector_policy_not_supported_v1"]},
        "financial_metric_version": "financial_metric_v1",
        "pe_core": "12.34",
        "score": "88",
        "financial_quality_status": "passed",
    }


def minimal_condition_basis_row() -> dict[str, object]:
    return {
        "for_trade_date": "20260601",
        "source_trade_date": "20260529",
        "prev_trade_date": "20260529",
        "stock_identity_key": "stock:SH:600000",
        "asset_kind": "stock",
        "code": "600000",
        "exchange": "SH",
        "name": "浦发银行",
        "is_st": False,
        "stock_status": "active",
        "official_daily_proof": True,
        "lane": "stock_alert",
        "monitor_type": "source_universe_preview",
        "total_mv": "1200000",
        "circ_mv": "900000",
        "financial_asof_date": "20260529",
        "period_trigger_baseline_json": {"baseline_version": "test", "periods": {}},
        "up_sell_reference_period": "D",
        "down_buy_reference_period": "D",
        "clear_sell_ref_period": "D",
        "buy_necessary_base": True,
        "buy_necessary_periods": ["D"],
        "sell_necessary_base": False,
        "buy_full_necessary_base": False,
        "sell_full_necessary_base": False,
        "oversold_hint_necessary_base": False,
        "overbought_hint_necessary_base": False,
        "source_version": "stock_daily_20260529_v1",
        "quality_status": "passed",
        "missing_fields_json": {},
        "raw_json": {},
    }


def strip_sql_comments(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))


if __name__ == "__main__":
    unittest.main()
