import unittest

from ashare_v3.action.schema_migration_execute import (
    N5_TARGET_TABLES,
    ROW_COUNT_GUARD_TABLES,
    build_post_migration_checks,
    load_n5_3_review_summary,
)
from ashare_v3.action.schema_migration_review import DEFAULT_N5_3_JSON_REPORT_PATH


class ActionSchemaMigrationExecuteTest(unittest.TestCase):
    def test_post_checks_pass_when_targets_empty_and_guards_unchanged(self) -> None:
        pre_snapshot = {
            "guard_row_counts": {
                table: {"exists": True, "row_count": 10, "status": "present"}
                for table in ROW_COUNT_GUARD_TABLES
            }
        }
        for table in N5_TARGET_TABLES:
            pre_snapshot["guard_row_counts"][table] = {"exists": False, "row_count": None, "status": "missing"}
        post_snapshot = {
            "target_row_counts": {
                table: {"exists": True, "row_count": 0, "status": "present"}
                for table in N5_TARGET_TABLES
            },
            "guard_row_counts": {
                table: {"exists": True, "row_count": 10, "status": "present"}
                for table in ROW_COUNT_GUARD_TABLES
            },
        }
        for table in N5_TARGET_TABLES:
            post_snapshot["guard_row_counts"][table] = {"exists": True, "row_count": 0, "status": "present"}
        for table in ("common_event_outbox", "common_event_inbox", "common_event_consumer_checkpoint"):
            pre_snapshot["guard_row_counts"][table] = {"exists": True, "row_count": 7, "status": "present"}
            post_snapshot["guard_row_counts"][table] = {"exists": True, "row_count": 7, "status": "present"}
        post_review = {"quality": {"p0_count": 0}, "migration_review": {"migration_ready": True}}

        checks = build_post_migration_checks(
            pre_snapshot=pre_snapshot,
            post_snapshot=post_snapshot,
            post_review=post_review,
        )

        self.assertTrue(all(checks.values()))

    def test_post_checks_fail_if_event_outbox_changes(self) -> None:
        pre_snapshot = minimal_snapshot(outbox_count=7, inbox_count=3, checkpoint_count=2)
        post_snapshot = minimal_snapshot(outbox_count=8, inbox_count=3, checkpoint_count=2)
        post_review = {"quality": {"p0_count": 0}, "migration_review": {"migration_ready": True}}

        checks = build_post_migration_checks(
            pre_snapshot=pre_snapshot,
            post_snapshot=post_snapshot,
            post_review=post_review,
        )

        self.assertFalse(checks["common_event_outbox_unchanged"])

    def test_load_n5_3_review_summary_reads_existing_report(self) -> None:
        summary = load_n5_3_review_summary(DEFAULT_N5_3_JSON_REPORT_PATH)

        self.assertTrue(summary["exists"])
        self.assertTrue(summary["migration_ready"])


def minimal_snapshot(*, outbox_count: int, inbox_count: int, checkpoint_count: int) -> dict[str, object]:
    target_counts = {
        table: {"exists": True, "row_count": 0, "status": "present"}
        for table in N5_TARGET_TABLES
    }
    guard_counts = dict(target_counts)
    guard_counts.update(
        {
            "common_event_outbox": {"exists": True, "row_count": outbox_count, "status": "present"},
            "common_event_inbox": {"exists": True, "row_count": inbox_count, "status": "present"},
            "common_event_consumer_checkpoint": {
                "exists": True,
                "row_count": checkpoint_count,
                "status": "present",
            },
        }
    )
    return {"target_row_counts": target_counts, "guard_row_counts": guard_counts}


if __name__ == "__main__":
    unittest.main()
