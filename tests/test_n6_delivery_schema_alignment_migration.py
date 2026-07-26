import re
import unittest
from pathlib import Path


MIGRATION = Path("sql/035_n6_delivery_notification_queue_schema_alignment.sql")
ROLLBACK = Path("sql/035_n6_delivery_notification_queue_schema_alignment_rollback.sql")
DOC_MD = Path("docs/N6_DELIVERY_SCHEMA_ALIGNMENT_MIGRATION_DRAFT.md")


class N6DeliverySchemaAlignmentMigrationTest(unittest.TestCase):
    def test_required_tracked_artifacts_document_draft_boundary(self) -> None:
        self.assertTrue(MIGRATION.exists())
        self.assertTrue(ROLLBACK.exists())
        self.assertTrue(DOC_MD.exists())

        document = DOC_MD.read_text(encoding="utf-8")
        self.assertIn("Status: DRAFT_PASS", document)
        self.assertIn("execute=false", document)
        self.assertIn("database_write=false", document)

    def test_migration_only_touches_user_notification_queue_constraints(self) -> None:
        sql = MIGRATION.read_text(encoding="utf-8")
        normalized = normalize(sql)

        self.assertIn("alter table user_notification_queue", normalized)
        self.assertIn("add constraint chk_unq_notification_source_n6_delivery", normalized)
        self.assertIn("add constraint chk_unq_channel_n6_delivery", normalized)
        self.assertNotRegex(normalized, forbidden_business_dml_regex())

        touched_tables = set(re.findall(r"alter table\s+([a-z0-9_]+)", normalized))
        self.assertEqual(touched_tables, {"user_notification_queue"})

    def test_migration_preserves_existing_values_and_adds_only_delivery_values(self) -> None:
        sql = MIGRATION.read_text(encoding="utf-8")

        for value in (
            "index_signal",
            "board_signal",
            "stock_filter_signal",
            "n5_action_event",
            "n5_hint_event",
            "n5_action_eligible",
            "n5_action_blocked",
            "n5_action_executed",
            "n5_action_skipped",
            "broadcast_queue",
            "voice_future",
            "mobile_future",
            "in_app_future",
        ):
            self.assertIn(value, sql)

        self.assertIn("n6_delivery_materialized_noop", sql)
        self.assertIn("in_app_notification_preview", sql)
        self.assertNotIn("real_trade", sql)
        self.assertNotIn("voice_delivery", sql)
        self.assertNotIn("mobile_delivery", sql)

    def test_rollback_hard_fails_before_constraint_restore_when_new_rows_exist(self) -> None:
        sql = ROLLBACK.read_text(encoding="utf-8")
        normalized = normalize(sql)

        first_raise = normalized.find("raise exception")
        first_alter = normalized.find("alter table user_notification_queue")

        self.assertGreaterEqual(first_raise, 0)
        self.assertGreaterEqual(first_alter, 0)
        self.assertLess(first_raise, first_alter)
        self.assertIn("notification_source = 'n6_delivery_materialized_noop'", normalized)
        self.assertIn("channel = 'in_app_notification_preview'", normalized)
        self.assertNotRegex(normalized, forbidden_business_dml_regex())

    def test_rollback_restores_old_values_without_delivery_values(self) -> None:
        sql = ROLLBACK.read_text(encoding="utf-8")
        restore_region = sql.split("ADD CONSTRAINT", 1)[1]

        self.assertIn("n5_action_blocked", restore_region)
        self.assertIn("in_app_future", restore_region)
        self.assertNotIn("n6_delivery_materialized_noop", restore_region)
        self.assertNotIn("in_app_notification_preview", restore_region)


def normalize(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.lower())


def forbidden_business_dml_regex() -> str:
    return r"\b(insert|update|delete|truncate|copy)\b"


if __name__ == "__main__":
    unittest.main()
