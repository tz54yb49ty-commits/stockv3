import unittest
from pathlib import Path

from ashare_v3.market.schema_gap_plan import CurrentSchemaMetadata, parse_target_schema
from ashare_v3.trigger.schema_review import (
    DEFAULT_TRIGGER_SCHEMA_PATH,
    REQUIRED_TRIGGER_TABLES,
    build_trigger_schema_migration_review_from_metadata,
    build_trigger_schema_rollback_sql,
    review_trigger_schema_sql,
)


class TriggerSchemaReviewTest(unittest.TestCase):
    def test_clean_first_apply_review_is_ready_for_n4_2_confirmation(self) -> None:
        target_schema = parse_target_schema((DEFAULT_TRIGGER_SCHEMA_PATH,))
        report = build_trigger_schema_migration_review_from_metadata(
            target_schema=target_schema,
            current_metadata=clean_first_apply_metadata(),
        )

        self.assertTrue(report["passed"], report["quality"]["items"])
        self.assertTrue(report["migration_required"])
        self.assertTrue(report["ready_for_n4_2_user_confirmation"])
        self.assertTrue(report["migration_safe_to_apply_after_user_confirmation"])
        self.assertFalse(report["manual_review_required"])
        self.assertEqual(report["target_tables_existing"], [])
        self.assertEqual(report["target_tables_missing"], list(REQUIRED_TRIGGER_TABLES))
        self.assertEqual(report["quality"]["p0_count"], 0)

    def test_missing_dependency_table_is_p0_blocker(self) -> None:
        target_schema = parse_target_schema((DEFAULT_TRIGGER_SCHEMA_PATH,))
        report = build_trigger_schema_migration_review_from_metadata(
            target_schema=target_schema,
            current_metadata=CurrentSchemaMetadata(
                checked_readonly=True,
                existing_tables=(),
                missing_dependency_tables=("common_event_outbox",),
                columns_by_table={},
                unique_constraints_by_table={},
            ),
        )

        self.assertFalse(report["ready_for_n4_2_user_confirmation"])
        self.assertGreater(report["quality"]["p0_count"], 0)
        failed_codes = {item["gate_code"] for item in report["quality"]["items"] if item["status"] == "failed"}
        self.assertIn("n4_dependency_tables_exist", failed_codes)

    def test_static_review_rejects_downstream_event_and_table(self) -> None:
        sql_text = Path(DEFAULT_TRIGGER_SCHEMA_PATH).read_text(encoding="utf-8")
        bad_sql = sql_text + "\nCREATE TABLE action_order (action_id TEXT DEFAULT 'ActionEvent');\n"

        review = review_trigger_schema_sql(bad_sql)

        self.assertFalse(review["static_ready"])
        self.assertIn("action_order", review["forbidden_downstream_table_hits"])
        self.assertIn("ActionEvent", review["forbidden_output_event_hits"])

    def test_rollback_preview_only_drops_n4_tables(self) -> None:
        rollback_sql = build_trigger_schema_rollback_sql()

        self.assertIn("DROP TABLE IF EXISTS common_trigger_match", rollback_sql)
        self.assertIn("DROP TABLE IF EXISTS common_trigger_run", rollback_sql)
        self.assertNotIn("DROP TABLE IF EXISTS common_condition_run", rollback_sql)
        self.assertNotIn("DROP TABLE IF EXISTS common_market_data_run", rollback_sql)
        self.assertNotIn("DROP TABLE IF EXISTS common_event_outbox", rollback_sql)


def clean_first_apply_metadata() -> CurrentSchemaMetadata:
    return CurrentSchemaMetadata(
        checked_readonly=True,
        existing_tables=(),
        missing_dependency_tables=(),
        columns_by_table={},
        unique_constraints_by_table={},
    )


if __name__ == "__main__":
    unittest.main()
