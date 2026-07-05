import re
import unittest

from ashare_v3.condition.execute_preflight import REQUIRED_SCHEMA_TABLES
from ashare_v3.condition.schema_gap_plan import (
    CurrentColumn,
    build_condition_schema_gap_report_from_columns,
    generate_additive_migration_sql,
    parse_target_columns,
)


class ConditionSchemaGapPlanTest(unittest.TestCase):
    def test_parser_ignores_multiline_check_continuations(self) -> None:
        sql_text = """
        CREATE TABLE stock_condition_pool (
          run_id TEXT NOT NULL,
          lane TEXT NOT NULL CHECK (lane IN ('stock_trade', 'stock_alert')),
          policy_name TEXT NOT NULL,
          CHECK (
            lane <> 'stock_trade'
            OR (policy_name <> '')
          )
        );
        """

        columns = parse_target_columns(sql_text)["stock_condition_pool"]

        self.assertIn("policy_name", columns)
        self.assertNotIn("or", columns)
        self.assertEqual(columns["policy_name"].target_type, "TEXT")

    def test_gap_report_detects_missing_policy_columns_without_type_mismatch(self) -> None:
        sql_text = """
        CREATE TABLE stock_condition_basis (
          existing TEXT,
          is_st BOOLEAN NOT NULL DEFAULT false,
          financial_quality_status TEXT CHECK (financial_quality_status IS NULL OR financial_quality_status IN ('passed', 'warning', 'failed'))
        );
        CREATE TABLE stock_condition_pool (
          existing TEXT,
          policy_name TEXT NOT NULL,
          selected_reason TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
        );
        """
        target_columns = parse_target_columns(sql_text)
        current_columns = {
            table_name: {
                "existing": CurrentColumn(
                    table_name=table_name,
                    column_name="existing",
                    formatted_type="text",
                    not_null=False,
                    default_expr=None,
                )
            }
            for table_name in REQUIRED_SCHEMA_TABLES
        }

        report = build_condition_schema_gap_report_from_columns(
            target_columns=target_columns,
            current_columns=current_columns,
        )
        missing = {(item.table_name, item.column_name) for item in report.missing_columns}

        self.assertIn(("stock_condition_basis", "is_st"), missing)
        self.assertIn(("stock_condition_basis", "financial_quality_status"), missing)
        self.assertIn(("stock_condition_pool", "policy_name"), missing)
        self.assertIn(("stock_condition_pool", "selected_reason"), missing)
        self.assertFalse(report.type_mismatches)
        self.assertTrue(report.not_null_risks)
        self.assertTrue(report.constraint_deferred)

    def test_generated_sql_is_additive_and_nullable(self) -> None:
        sql_text = """
        CREATE TABLE stock_condition_pool (
          existing TEXT,
          policy_name TEXT NOT NULL,
          selected_reason TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
        );
        """
        target_columns = parse_target_columns(sql_text)
        current_columns = {
            table_name: {
                "existing": CurrentColumn(
                    table_name=table_name,
                    column_name="existing",
                    formatted_type="text",
                    not_null=False,
                    default_expr=None,
                )
            }
            for table_name in REQUIRED_SCHEMA_TABLES
        }
        report = build_condition_schema_gap_report_from_columns(
            target_columns=target_columns,
            current_columns=current_columns,
        )

        migration_sql = generate_additive_migration_sql(report)

        self.assertIn("ADD COLUMN IF NOT EXISTS policy_name TEXT", migration_sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS selected_reason TEXT[]", migration_sql)
        self.assertIsNone(re.search(r"ADD COLUMN IF NOT EXISTS .* NOT NULL", migration_sql))
        self.assertIsNone(re.search(r"ADD COLUMN IF NOT EXISTS .* DEFAULT", migration_sql))
        self.assertIsNone(re.search(r"ADD COLUMN IF NOT EXISTS .* CHECK", migration_sql))


if __name__ == "__main__":
    unittest.main()
