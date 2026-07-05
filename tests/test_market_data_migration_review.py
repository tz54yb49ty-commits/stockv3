import unittest

from ashare_v3.market.migration_review import (
    review_market_data_009_migration,
)


class MarketDataMigrationReviewTest(unittest.TestCase):
    def test_current_009_migration_review_passes(self) -> None:
        with open("sql/009_market_data_schema_migration.sql", encoding="utf-8") as handle:
            report = review_market_data_009_migration(handle.read())

        self.assertTrue(report["passed"])
        self.assertTrue(report["additive_only"])
        self.assertTrue(report["target_scope_valid"])
        self.assertTrue(report["outbox_unique_constraints_present"])
        self.assertEqual(
            report["common_event_outbox_unique_constraints"],
            [
                ["event_id"],
                ["source_layer", "event_type", "source_run_id", "dedup_key", "event_schema_version"],
            ],
        )
        self.assertEqual(report["forbidden_executable_hits"], [])
        self.assertEqual(report["runtime_identifier_hits"], [])
        self.assertEqual(report["user_event_hits"], [])
        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertGreater(report["foreign_key_on_delete_count"], 0)
        self.assertFalse(report["foreign_key_on_delete_is_dml_delete"])

    def test_review_rejects_destructive_and_dml_sql(self) -> None:
        sql = """
        BEGIN;
        DROP TABLE common_market_data_run;
        DELETE FROM common_event_outbox;
        UPDATE common_market_data_run SET status = 'failed';
        TRUNCATE common_event_ledger;
        ALTER TABLE common_event_outbox DROP COLUMN event_id;
        INSERT INTO stock_minute_bar_1m(run_id) VALUES ('x');
        COMMIT;
        """

        report = review_market_data_009_migration(sql)

        self.assertFalse(report["passed"])
        self.assertFalse(report["additive_only"])
        self.assertIn("drop_statement", report["forbidden_executable_hits"])
        self.assertIn("delete_statement", report["forbidden_executable_hits"])
        self.assertIn("update_statement", report["forbidden_executable_hits"])
        self.assertIn("truncate_statement", report["forbidden_executable_hits"])
        self.assertIn("alter_table_drop", report["forbidden_executable_hits"])
        self.assertIn("insert_into", report["forbidden_executable_hits"])

    def test_review_rejects_out_of_scope_tables_runtime_names_and_user_events(self) -> None:
        sql = """
        BEGIN;
        CREATE TABLE IF NOT EXISTS stock_minute_bar_1m_runtime (
          event_type TEXT DEFAULT 'UserMarketProjectionUpdated'
        );
        CREATE TABLE IF NOT EXISTS user_card_projection (
          projection_id BIGINT PRIMARY KEY
        );
        COMMIT;
        """

        report = review_market_data_009_migration(sql)

        self.assertFalse(report["passed"])
        self.assertFalse(report["target_scope_valid"])
        self.assertIn("stock_minute_bar_1m_runtime", report["out_of_scope_tables"])
        self.assertIn("user_card_projection", report["out_of_scope_tables"])
        self.assertIn("stock_minute_bar_1m_runtime", report["runtime_identifier_hits"])
        self.assertIn("'UserMarketProjectionUpdated'", report["user_event_hits"])

    def test_review_requires_common_event_outbox_unique_constraints(self) -> None:
        sql = """
        BEGIN;
        CREATE TABLE IF NOT EXISTS common_event_outbox (
          outbox_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          event_id TEXT NOT NULL,
          event_type TEXT NOT NULL,
          event_schema_version TEXT NOT NULL,
          source_layer TEXT NOT NULL,
          source_run_id TEXT NOT NULL,
          dedup_key TEXT NOT NULL
        );
        COMMIT;
        """

        report = review_market_data_009_migration(sql)

        self.assertFalse(report["passed"])
        self.assertFalse(report["outbox_unique_constraints_present"])
        self.assertFalse(report["common_event_outbox_event_id_unique_present"])
        self.assertFalse(report["common_event_outbox_dedup_unique_present"])

    def test_review_allows_fk_on_delete_but_not_delete_from(self) -> None:
        sql = """
        BEGIN;
        CREATE TABLE IF NOT EXISTS common_market_data_run (
          run_id TEXT PRIMARY KEY
        );
        CREATE TABLE IF NOT EXISTS common_market_data_quality_item (
          quality_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS common_event_outbox (
          outbox_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          event_id TEXT NOT NULL,
          event_type TEXT NOT NULL,
          event_schema_version TEXT NOT NULL,
          source_layer TEXT NOT NULL,
          source_run_id TEXT NOT NULL,
          dedup_key TEXT NOT NULL,
          CONSTRAINT uq_common_event_outbox_event_id UNIQUE(event_id),
          CONSTRAINT uq_common_event_outbox_dedup UNIQUE(source_layer, event_type, source_run_id, dedup_key, event_schema_version)
        );
        COMMIT;
        """

        report = review_market_data_009_migration(sql)

        self.assertNotIn("delete_statement", report["forbidden_executable_hits"])
        self.assertEqual(report["foreign_key_on_delete_count"], 1)


if __name__ == "__main__":
    unittest.main()
