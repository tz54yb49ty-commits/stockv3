import unittest

from ashare_v3.market.schema_migration_review import (
    REQUIRED_MARKET_CONTROL_TABLES,
    build_market_data_schema_review_report,
    review_market_data_schema_sql,
)


class MarketDataSchemaMigrationReviewTest(unittest.TestCase):
    def test_review_accepts_006_schema_draft(self) -> None:
        with open("sql/006_market_data_layer_schema.sql", encoding="utf-8") as handle:
            review = review_market_data_schema_sql(handle.read())

        self.assertTrue(review.static_ready)
        self.assertTrue(review.additive_create_only)
        self.assertEqual(review.created_tables, REQUIRED_MARKET_CONTROL_TABLES)
        self.assertEqual(review.required_tables_missing, ())
        self.assertEqual(review.forbidden_created_tables, ())
        self.assertEqual(review.unsafe_sql_hits, ())
        self.assertTrue(review.required_data_kind_whitelist_present)
        self.assertTrue(review.trace_columns_present)
        self.assertTrue(review.dry_run_guard_columns_present)

    def test_review_rejects_market_fact_and_downstream_tables(self) -> None:
        sql = """
        BEGIN;
        CREATE TABLE common_market_data_run (
          run_id TEXT,
          source_condition_run_id TEXT,
          for_trade_date TEXT,
          source_trade_date TEXT,
          prev_trade_date TEXT,
          mode TEXT,
          status TEXT,
          p0_count INTEGER,
          p1_count INTEGER,
          p2_count INTEGER,
          source_scope_row_count INTEGER,
          candidate_row_count INTEGER,
          subscription_row_count INTEGER,
          subscription_object_count INTEGER,
          dedup_ratio NUMERIC,
          market_data_pulled BOOLEAN,
          market_data_fact_written BOOLEAN,
          downstream_layers_touched BOOLEAN,
          worker_started BOOLEAN
        );
        CREATE TABLE stock_minute_bar_1m (run_id TEXT);
        CREATE TABLE common_action_event (run_id TEXT);
        COMMIT;
        """

        review = review_market_data_schema_sql(sql)

        self.assertFalse(review.static_ready)
        self.assertFalse(review.additive_create_only)
        self.assertIn("stock_minute_bar_1m", review.forbidden_created_tables)
        self.assertIn("common_action_event", review.forbidden_created_tables)
        self.assertIn("action", review.forbidden_keyword_hits)

    def test_report_ready_for_first_apply_when_market_tables_all_missing(self) -> None:
        with open("sql/006_market_data_layer_schema.sql", encoding="utf-8") as handle:
            sql_review = review_market_data_schema_sql(handle.read())
        database_status = {
            "read_only_database_checks": True,
            "required_market_tables": list(REQUIRED_MARKET_CONTROL_TABLES),
            "market_tables_existing": [],
            "market_tables_missing": list(REQUIRED_MARKET_CONTROL_TABLES),
            "market_table_existing_count": 0,
            "market_table_missing_count": len(REQUIRED_MARKET_CONTROL_TABLES),
            "dependency_tables": [
                "common_condition_run",
                "stock_minute_target_scope",
                "index_minute_target_scope",
                "board_minute_target_scope",
            ],
            "dependency_missing": [],
            "missing_columns_existing_tables": {},
            "all_market_tables_missing": True,
            "all_market_tables_existing": False,
            "partial_market_tables_existing": False,
        }

        report = build_market_data_schema_review_report(
            schema_path="sql/006_market_data_layer_schema.sql",
            sql_review=sql_review,
            database_status=database_status,
        )

        self.assertTrue(report["ready_for_first_apply"])
        self.assertTrue(report["ready_for_user_migration_review"])
        self.assertTrue(report["migration_safe_to_apply_after_user_confirmation"])
        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertEqual(report["quality"]["p1_count"], 0)
        self.assertFalse(report["planned_migration"]["will_execute_sql"])

    def test_report_marks_partial_existing_tables_for_manual_review(self) -> None:
        with open("sql/006_market_data_layer_schema.sql", encoding="utf-8") as handle:
            sql_review = review_market_data_schema_sql(handle.read())
        database_status = {
            "read_only_database_checks": True,
            "required_market_tables": list(REQUIRED_MARKET_CONTROL_TABLES),
            "market_tables_existing": ["common_market_data_run"],
            "market_tables_missing": [table for table in REQUIRED_MARKET_CONTROL_TABLES if table != "common_market_data_run"],
            "market_table_existing_count": 1,
            "market_table_missing_count": len(REQUIRED_MARKET_CONTROL_TABLES) - 1,
            "dependency_tables": [
                "common_condition_run",
                "stock_minute_target_scope",
                "index_minute_target_scope",
                "board_minute_target_scope",
            ],
            "dependency_missing": [],
            "missing_columns_existing_tables": {},
            "all_market_tables_missing": False,
            "all_market_tables_existing": False,
            "partial_market_tables_existing": True,
        }

        report = build_market_data_schema_review_report(
            schema_path="sql/006_market_data_layer_schema.sql",
            sql_review=sql_review,
            database_status=database_status,
        )

        self.assertFalse(report["ready_for_first_apply"])
        self.assertTrue(report["manual_review_required"])
        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertEqual(report["quality"]["p1_count"], 1)


if __name__ == "__main__":
    unittest.main()
