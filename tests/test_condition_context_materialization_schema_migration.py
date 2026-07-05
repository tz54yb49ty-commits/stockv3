from pathlib import Path
import re
import unittest


MIGRATION = Path("sql/033_condition_context_enrichment_materialization_schema.sql")
ROLLBACK = Path("sql/033_condition_context_enrichment_materialization_schema_rollback.sql")


class ConditionContextMaterializationSchemaMigrationTest(unittest.TestCase):
    def test_migration_creates_four_n2_context_materialization_tables(self) -> None:
        sql = MIGRATION.read_text(encoding="utf-8")

        for table in (
            "common_condition_context_enrichment_run",
            "stock_condition_context_enrichment",
            "index_condition_context_enrichment",
            "board_condition_context_enrichment",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", sql)

        for field in (
            "materialization_run_id",
            "spec_version",
            "policy_hash",
            "context_materialization_row_key",
            "context_enrichment_hash",
            "period_trigger_baseline_json JSONB",
            "trigger_amount_chain_baseline_json JSONB",
            "FULL_prerequisite_trace_json JSONB",
            "HINT_prerequisite_trace_json JSONB",
            "payload_json JSONB",
        ):
            self.assertIn(field, sql)

        self.assertIn("UNIQUE(materialization_run_id, context_materialization_row_key)", sql)
        self.assertIn("UNIQUE(materialization_run_id, source_minute_target_scope_id)", sql)
        self.assertIn("USING GIN (payload_json)", sql)

    def test_migration_is_schema_only_without_dml_or_downstream_tables(self) -> None:
        sql = MIGRATION.read_text(encoding="utf-8")

        self.assertIsNone(re.search(r"\b(INSERT|UPDATE|DELETE|TRUNCATE|COPY)\b", sql, re.IGNORECASE))
        self.assertNotIn("trigger_match", sql)
        self.assertNotIn("action_fact", sql)
        self.assertNotIn("user_", sql)
        self.assertNotIn("common_event_outbox", sql)
        self.assertNotIn("common_event_inbox", sql)
        self.assertNotIn("common_event_consumer_checkpoint", sql)

    def test_rollback_blocks_when_rows_exist_and_drops_only_new_tables(self) -> None:
        sql = ROLLBACK.read_text(encoding="utf-8")

        self.assertIn("RAISE EXCEPTION", sql)
        self.assertLess(sql.index("RAISE EXCEPTION"), sql.index("DROP TABLE"))
        for table in (
            "board_condition_context_enrichment",
            "index_condition_context_enrichment",
            "stock_condition_context_enrichment",
            "common_condition_context_enrichment_run",
        ):
            self.assertIn(f"DROP TABLE IF EXISTS {table}", sql)
        self.assertNotIn("DROP TABLE IF EXISTS stock_minute_target_scope", sql)
        self.assertIsNone(re.search(r"\b(INSERT|UPDATE|DELETE|TRUNCATE|COPY)\b", sql, re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
