import re
import unittest
from pathlib import Path

from ashare_v3.condition.basis import DateContext, computed_condition_fields, make_stock_sample_basis
from ashare_v3.condition.display_basis import DOMAIN_CONFIGS, build_display_rows_for_domain
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
)
from ashare_v3.condition.pool import static_pool_fields
from ashare_v3.condition.scope import build_stock_condition_scope_from_pool_report, scope_static_filter_fields


MIGRATION_PATH = Path("sql/031_condition_level_score_columns_migration.sql")
ROLLBACK_PATH = Path("sql/031_condition_level_score_columns_rollback.sql")
LEVEL_SCORE_FIELDS = ("level_up_score", "level_down_score")
N2_TABLES = (
    "stock_condition_basis",
    "index_condition_basis",
    "board_condition_basis",
    "stock_condition_pool",
    "index_condition_pool",
    "board_condition_pool",
    "stock_minute_target_scope",
    "index_minute_target_scope",
    "board_minute_target_scope",
    "stock_condition_display_basis",
    "index_condition_display_basis",
    "board_condition_display_basis",
)


class ConditionLevelScoreTest(unittest.TestCase):
    def test_computed_condition_fields_calculates_level_scores_from_transitions(self) -> None:
        fields = computed_condition_fields(
            period_context_for_transitions(
                {
                    "Y": "volume_up",
                    "Q": "low_volume_up",
                    "M": "volume_up",
                    "W": "volume_up",
                    "D": "volume_up",
                }
            ),
            sample_dates(),
        )

        self.assertEqual(fields["level_up_score"], 2999)
        self.assertEqual(fields["level_down_score"], 125)

    def test_unknown_transition_defaults_to_flat_rank(self) -> None:
        fields = computed_condition_fields(
            period_context_for_transitions(
                {
                    "Y": "unknown",
                    "Q": None,
                    "M": "",
                    "W": "flat",
                    "D": "not_a_grade",
                }
            ),
            sample_dates(),
        )

        self.assertEqual(fields["level_up_score"], 1562)
        self.assertEqual(fields["level_down_score"], 1562)

    def test_stock_golden_scores_match_target_machine_ordering_examples(self) -> None:
        all_volume_up = make_stock_sample_basis(
            stock_source_row("000543", "皖能电力"),
            sample_dates(),
            period_context_for_transitions({period: "volume_up" for period in ("Y", "Q", "M", "W", "D")}),
        )
        split_anchor = make_stock_sample_basis(
            stock_source_row("300327", "中颖电子"),
            sample_dates(),
            period_context_for_transitions(
                {
                    "Y": "volume_up",
                    "Q": "low_volume_up",
                    "M": "volume_up",
                    "W": "volume_up",
                    "D": "volume_up",
                }
            ),
        )

        self.assertEqual(all_volume_up["level_up_score"], 3124)
        self.assertEqual(all_volume_up["level_down_score"], 0)
        self.assertEqual(split_anchor["level_up_score"], 2999)
        self.assertEqual(split_anchor["level_down_score"], 125)

    def test_pool_scope_and_display_inherit_level_scores_without_recompute(self) -> None:
        basis = {
            **stock_source_row("300327", "中颖电子"),
            "run_id": "run1",
            "source_version": "run1",
            "for_trade_date": "20260601",
            "source_trade_date": "20260529",
            "prev_trade_date": "20260529",
            "stock_condition_basis_id": 1,
            "asset_kind": "stock",
            "lane": "stock_alert",
            "monitor_type": "source_universe_preview",
            "direction": "buy",
            "up_sell_reference_period": "D",
            "down_buy_reference_period": "D",
            "clear_sell_ref_period": "D",
            "buy_target_price": "38.27",
            "sell_target_price": None,
            "period_trigger_baseline_json": {"baseline_version": "test", "periods": {}},
            "level_up_score": 2999,
            "level_down_score": 125,
        }
        pool_fields = static_pool_fields(basis, direction="buy")
        scope_fields = scope_static_filter_fields(pool_fields)
        display_rows = build_display_rows_for_domain(
            DOMAIN_CONFIGS["stock"],
            basis_rows=[basis],
            pool_rows=[
                {
                    **pool_fields,
                    "stock_condition_pool_id": 10,
                    "stock_identity_key": "stock:SZ:300327",
                    "condition_key": "BUY:Y",
                    "allowed_signal_types": ["BUY"],
                    "lane": "stock_alert",
                    "monitor_type": "source_universe_preview",
                    "selected_reason": ["test"],
                }
            ],
            scope_rows=[
                {
                    **scope_fields,
                    "stock_minute_target_scope_id": 20,
                    "stock_identity_key": "stock:SZ:300327",
                    "source_condition_pool_id": 10,
                }
            ],
        )

        self.assertEqual(pool_fields["level_up_score"], 2999)
        self.assertEqual(pool_fields["level_down_score"], 125)
        self.assertEqual(scope_fields["level_up_score"], 2999)
        self.assertEqual(scope_fields["level_down_score"], 125)
        self.assertEqual(display_rows[0]["level_up_score"], 2999)
        self.assertEqual(display_rows[0]["level_down_score"], 125)

    def test_stock_scope_dry_run_rows_inherit_level_scores_from_pool(self) -> None:
        scope = build_stock_condition_scope_from_pool_report(
            {
                "run_id": "pool-run",
                "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0},
                "pool_preview": {
                    "stock": {
                        "pool_rows": [
                            {
                                **stock_source_row("300327", "中颖电子"),
                                "active_target": True,
                                "direction": "buy",
                                "condition_key": "BUY:Y",
                                "condition_periods": ["Y"],
                                "allowed_signal_types": ["BUY"],
                                "condition_pool_ref": "dry_run:stock:condition_pool:1",
                                "level_up_score": 2999,
                                "level_down_score": 125,
                            }
                        ]
                    }
                },
            },
            sample_dates(),
        )

        self.assertEqual(scope["scope_rows"][0]["level_up_score"], 2999)
        self.assertEqual(scope["scope_rows"][0]["level_down_score"], 125)

    def test_execute_column_lists_cover_level_scores_for_12_n2_tables(self) -> None:
        for columns in (
            STOCK_BASIS_COLUMNS,
            INDEX_BASIS_COLUMNS,
            BOARD_BASIS_COLUMNS,
            STOCK_POOL_COLUMNS,
            INDEX_POOL_COLUMNS,
            BOARD_POOL_COLUMNS,
            STOCK_SCOPE_COLUMNS,
            INDEX_SCOPE_COLUMNS,
            BOARD_SCOPE_COLUMNS,
            STOCK_DISPLAY_COLUMNS,
            INDEX_DISPLAY_COLUMNS,
            BOARD_DISPLAY_COLUMNS,
        ):
            for field in LEVEL_SCORE_FIELDS:
                self.assertIn(field, columns)

    def test_031_migration_is_additive_nullable_for_12_n2_tables(self) -> None:
        sql = MIGRATION_PATH.read_text(encoding="utf-8")
        executable_sql = strip_sql_comments(sql)

        self.assertIn("BEGIN;", sql)
        self.assertIn("COMMIT;", sql)
        self.assertNotRegex(executable_sql, r"\b(INSERT|UPDATE|DELETE|TRUNCATE|COPY|CREATE\s+TABLE|DROP\s+TABLE)\b")
        self.assertNotIn(" NOT NULL", executable_sql.upper())
        for table in N2_TABLES:
            self.assertIn(f"ALTER TABLE {table}", sql)
        for field in LEVEL_SCORE_FIELDS:
            self.assertIn(f"ADD COLUMN IF NOT EXISTS {field} INTEGER", sql)
            self.assertIn(f"CHECK ({field} IS NULL OR ({field} >= 0 AND {field} <= 3124))", sql)

    def test_031_rollback_only_drops_level_score_columns(self) -> None:
        sql = ROLLBACK_PATH.read_text(encoding="utf-8")
        executable_sql = strip_sql_comments(sql)

        self.assertIn("BEGIN;", sql)
        self.assertIn("COMMIT;", sql)
        self.assertNotRegex(executable_sql, r"\b(INSERT|UPDATE|DELETE|TRUNCATE|COPY|CREATE\s+TABLE)\b")
        for table in N2_TABLES:
            self.assertIn(f"ALTER TABLE {table}", sql)
        for field in LEVEL_SCORE_FIELDS:
            self.assertIn(f"DROP COLUMN IF EXISTS {field}", sql)


def sample_dates() -> DateContext:
    return DateContext(
        source_trade_date="20260529",
        source_prev_trade_date="20260528",
        for_trade_date="20260601",
        prev_trade_date="20260529",
        for_trade_calendar_row_exists=True,
    )


def period_context_for_transitions(transitions: dict[str, object]) -> dict[str, object]:
    return {
        period: {
            "current": {
                "open": "10",
                "close": "10",
                "high": "10",
                "low": "10",
                "amount": "100",
                "day_count": 1,
                "start_date": "20260529",
                "end_date": "20260529",
            },
            "previous": {
                "open": "10",
                "close": "10",
                "amount": "100",
            },
            "grade": value,
            "transition": value,
        }
        for period, value in transitions.items()
    }


def stock_source_row(code: str, name: str) -> dict[str, object]:
    return {
        "stock_identity_key": f"stock:SZ:{code}",
        "code": code,
        "exchange": "SZ",
        "name": name,
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
    }


def strip_sql_comments(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))


if __name__ == "__main__":
    unittest.main()
