import unittest
from pathlib import Path

from ashare_v3.condition.basis import empty_static_structure_fields
from ashare_v3.condition.execute import (
    BOARD_BASIS_COLUMNS,
    BOARD_POOL_COLUMNS,
    BOARD_SCOPE_COLUMNS,
    INDEX_BASIS_COLUMNS,
    INDEX_POOL_COLUMNS,
    INDEX_SCOPE_COLUMNS,
    STOCK_BASIS_COLUMNS,
    STOCK_POOL_COLUMNS,
    STOCK_SCOPE_COLUMNS,
)
from ashare_v3.condition.pool import static_pool_fields
from ashare_v3.condition.scope import scope_static_filter_fields


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_FIELDS = (
    "up_sell_reference_period",
    "down_buy_reference_period",
    "clear_sell_ref_period",
)
PERIOD_TRIGGER_BASELINE_FIELD = "period_trigger_baseline_json"
CANONICAL_TARGET_FIELDS = (
    "symmetry_anchor",
    "secondary_symmetry_anchor",
    "amplitude_source_period",
    "a_segment_start_date",
    "a_segment_end_date",
    "a_segment_high",
    "a_segment_low",
    "a_segment_amplitude",
    "base_price_policy",
    "base_price",
    "reference_target_price",
    "secondary_target_price",
    "target_price_trace_json",
)
FORBIDDEN_TARGET_FIELDS = ("locked_target_price", "target_lock_status")
TABLES = (
    "stock_condition_basis",
    "index_condition_basis",
    "board_condition_basis",
    "stock_condition_pool",
    "index_condition_pool",
    "board_condition_pool",
    "stock_minute_target_scope",
    "index_minute_target_scope",
    "board_minute_target_scope",
)


class ConditionStaticReferencePeriodChainTest(unittest.TestCase):
    def test_empty_static_structure_defaults_reference_periods_to_d(self) -> None:
        fields = empty_static_structure_fields()

        self.assertEqual(fields["up_sell_reference_period"], "D")
        self.assertEqual(fields["down_buy_reference_period"], "D")
        self.assertEqual(fields["clear_sell_ref_period"], "D")

    def test_pool_and_scope_normalize_reference_alias(self) -> None:
        pool_fields = static_pool_fields(
            {
                "up_sell_reference_period": "w",
                "down_buy_reference_period": "",
                "clear_sell_ref_period": "Q",
            }
        )
        scope_fields = scope_static_filter_fields(pool_fields)

        self.assertEqual(pool_fields["up_sell_reference_period"], "W")
        self.assertEqual(pool_fields["down_buy_reference_period"], "D")
        self.assertEqual(pool_fields["clear_sell_ref_period"], "W")
        self.assertEqual(scope_fields["up_sell_reference_period"], "W")
        self.assertEqual(scope_fields["down_buy_reference_period"], "D")
        self.assertEqual(scope_fields["clear_sell_ref_period"], "W")

    def test_execute_columns_cover_pool_and_scope_tables(self) -> None:
        for columns in (
            STOCK_POOL_COLUMNS,
            INDEX_POOL_COLUMNS,
            BOARD_POOL_COLUMNS,
            STOCK_SCOPE_COLUMNS,
            INDEX_SCOPE_COLUMNS,
            BOARD_SCOPE_COLUMNS,
        ):
            for field in REFERENCE_FIELDS:
                self.assertIn(field, columns)

    def test_execute_columns_cover_period_trigger_baseline_dry_run_chain(self) -> None:
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
        ):
            self.assertIn(PERIOD_TRIGGER_BASELINE_FIELD, columns)

    def test_execute_columns_cover_canonical_target_fields_without_locked_fields(self) -> None:
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
        ):
            for field in CANONICAL_TARGET_FIELDS:
                self.assertIn(field, columns)
            for field in FORBIDDEN_TARGET_FIELDS:
                self.assertNotIn(field, columns)

    def test_pool_and_scope_map_reference_target_by_direction(self) -> None:
        basis_row = {
            "direction": "buy",
            "main_up_anchor": "Q",
            "up_reference_period": "M",
            "up_amplitude": "10",
            "up_base_price": "14",
            "buy_target_price": "24",
            "main_down_anchor": "W",
            "down_reference_period": "D",
            "down_amplitude": "2",
            "down_base_price": "13",
            "sell_target_price": "11",
            "up_sell_reference_period": "M",
            "down_buy_reference_period": "D",
            "clear_sell_ref_period": "M",
        }

        buy_pool_fields = static_pool_fields({**basis_row, "direction": "buy"})
        sell_pool_fields = static_pool_fields({**basis_row, "direction": "sell"})
        buy_scope_fields = scope_static_filter_fields(buy_pool_fields)
        sell_scope_fields = scope_static_filter_fields(sell_pool_fields)

        self.assertEqual(buy_pool_fields["reference_target_price"], "24")
        self.assertIsNone(buy_pool_fields["secondary_target_price"])
        self.assertEqual(sell_pool_fields["reference_target_price"], "11")
        self.assertIsNone(sell_pool_fields["secondary_target_price"])
        self.assertEqual(buy_scope_fields["reference_target_price"], "24")
        self.assertEqual(sell_scope_fields["reference_target_price"], "11")
        self.assertNotIn("locked_target_price", buy_pool_fields)
        self.assertNotIn("target_lock_status", sell_scope_fields)

    def test_002_schema_declares_reference_fields_for_all_nine_tables(self) -> None:
        sql = (PROJECT_ROOT / "sql/002_condition_layer_schema.sql").read_text(encoding="utf-8")

        for table in TABLES:
            start = sql.index(f"CREATE TABLE {table}")
            end = sql.index(");", start)
            table_sql = sql[start:end]
            for field in REFERENCE_FIELDS:
                self.assertIn(field, table_sql, table)
            self.assertIn("period_trigger_baseline_json JSONB", table_sql, table)

    def test_012_migration_is_additive_nullable_for_all_nine_tables(self) -> None:
        sql = (PROJECT_ROOT / "sql/012_condition_static_reference_period_full_chain_migration.sql").read_text(encoding="utf-8")
        executable_sql = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
        upper_sql = executable_sql.upper()

        self.assertNotIn("UPDATE ", upper_sql)
        self.assertNotIn("INSERT ", upper_sql)
        self.assertNotIn("DELETE ", upper_sql)
        self.assertNotIn(" NOT NULL", upper_sql)
        self.assertNotIn(" CHECK ", upper_sql)
        for table in TABLES:
            self.assertIn(f"ALTER TABLE {table}", sql)
            table_start = sql.index(f"ALTER TABLE {table}")
            table_end = sql.index(";", table_start)
            table_sql = sql[table_start:table_end]
            for field in REFERENCE_FIELDS:
                self.assertIn(f"ADD COLUMN IF NOT EXISTS {field} TEXT", table_sql, table)

    def test_013_migration_is_additive_nullable_for_period_trigger_baseline(self) -> None:
        sql = (PROJECT_ROOT / "sql/013_condition_period_trigger_baseline_migration.sql").read_text(encoding="utf-8")
        executable_sql = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
        upper_sql = executable_sql.upper()

        self.assertNotIn("UPDATE ", upper_sql)
        self.assertNotIn("INSERT ", upper_sql)
        self.assertNotIn("DELETE ", upper_sql)
        self.assertNotIn(" NOT NULL", upper_sql)
        self.assertNotIn(" CHECK ", upper_sql)
        self.assertNotIn("REFERENCES", upper_sql)
        for table in TABLES:
            self.assertIn(f"ALTER TABLE {table}", sql)
            table_start = sql.index(f"ALTER TABLE {table}")
            table_end = sql.index(";", table_start)
            table_sql = sql[table_start:table_end]
            self.assertIn("ADD COLUMN IF NOT EXISTS period_trigger_baseline_json JSONB", table_sql, table)


if __name__ == "__main__":
    unittest.main()
