import unittest

from ashare_v3.trigger.migration_execute import (
    build_post_migration_checks,
    format_trigger_schema_010_migration_report,
)
from ashare_v3.trigger.schema_review import REQUIRED_TRIGGER_TABLES


def row_counts(*, exists: bool, row_count: int | None) -> dict[str, dict[str, object]]:
    return {
        table: {
            "exists": exists,
            "row_count": row_count,
            "status": "present" if exists else "missing",
        }
        for table in REQUIRED_TRIGGER_TABLES
    }


class TriggerSchemaMigrationExecuteTest(unittest.TestCase):
    def test_post_checks_pass_for_empty_n4_tables(self):
        pre_backup = {
            "target_row_counts": row_counts(exists=False, row_count=None),
            "guard_row_counts": {
                **row_counts(exists=False, row_count=None),
                "common_event_outbox": {"exists": True, "row_count": 0, "status": "present"},
            },
            "active_snapshot": {"condition": "same"},
        }
        post_backup = {
            "target_row_counts": row_counts(exists=True, row_count=0),
            "guard_row_counts": {
                **row_counts(exists=True, row_count=0),
                "common_event_outbox": {"exists": True, "row_count": 0, "status": "present"},
            },
            "active_snapshot": {"condition": "same"},
        }
        post_review = {
            "target_tables_missing": [],
            "missing_dependency_tables": [],
            "missing_columns": [],
            "type_mismatch": [],
            "missing_unique_constraints": [],
            "quality": {"p0_count": 0},
            "static_review": {"static_ready": True},
        }

        checks = build_post_migration_checks(
            pre_backup=pre_backup,
            post_backup=post_backup,
            post_review=post_review,
        )

        self.assertTrue(all(checks.values()))

    def test_post_checks_fail_when_trigger_rows_are_written(self):
        pre_backup = {
            "target_row_counts": row_counts(exists=False, row_count=None),
            "guard_row_counts": {
                **row_counts(exists=False, row_count=None),
                "common_event_outbox": {"exists": True, "row_count": 0, "status": "present"},
            },
            "active_snapshot": {},
        }
        post_counts = row_counts(exists=True, row_count=0)
        post_counts["common_trigger_match"]["row_count"] = 1
        post_backup = {
            "target_row_counts": post_counts,
            "guard_row_counts": {
                **post_counts,
                "common_event_outbox": {"exists": True, "row_count": 0, "status": "present"},
            },
            "active_snapshot": {},
        }
        post_review = {
            "target_tables_missing": [],
            "missing_dependency_tables": [],
            "missing_columns": [],
            "type_mismatch": [],
            "missing_unique_constraints": [],
            "quality": {"p0_count": 0},
            "static_review": {"static_ready": True},
        }

        checks = build_post_migration_checks(
            pre_backup=pre_backup,
            post_backup=post_backup,
            post_review=post_review,
        )

        self.assertFalse(checks["n4_target_tables_row_count_zero"])
        self.assertFalse(checks["trigger_business_rows_zero"])

    def test_report_boundary_mentions_no_event_consumption_or_worker(self):
        report = {
            "stage": "N4-2",
            "layer_role": "N4_trigger",
            "sql_path": "sql/010_trigger_layer_schema.sql",
            "rollback_sql_path": "sql/N4_2_trigger_schema_rollback.sql",
            "migration_executed": True,
            "pre_backup_path": "docs/before.json",
            "post_backup_path": "docs/after.json",
            "started_at": "2026-05-24T00:00:00+00:00",
            "finished_at": "2026-05-24T00:00:01+00:00",
            "preconditions": {
                "ready_for_n4_2_user_confirmation": True,
                "migration_safe_to_apply_after_user_confirmation": True,
                "rollback_preview_exists": True,
                "additive_create_only": True,
                "review_p0_count": 0,
                "review_p1_count": 1,
                "review_p2_count": 0,
            },
            "pre_migration": {
                "review_summary": {
                    "target_tables_missing": list(REQUIRED_TRIGGER_TABLES),
                    "missing_dependency_tables": [],
                }
            },
            "post_migration": {
                "review_summary": {
                    "target_tables_missing": [],
                    "missing_dependency_tables": [],
                    "missing_columns_count": 0,
                    "type_mismatch_count": 0,
                    "missing_unique_constraints_count": 0,
                },
                "target_row_counts": row_counts(exists=True, row_count=0),
            },
            "post_checks": {"missing_n4_tables_zero": True},
            "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0, "items": []},
            "side_effects": {
                "will_execute_sql": True,
                "migration_executed": True,
                "writes_performed": False,
                "market_data_pulled": False,
                "n3_event_consumed": False,
                "trigger_context_snapshot_written": False,
                "trigger_state_written": False,
                "trigger_match_written": False,
                "event_outbox_written": False,
                "downstream_layers_touched": False,
                "worker_started": False,
                "old_system_touched": False,
            },
        }

        text = format_trigger_schema_010_migration_report(report)

        self.assertIn("n3_event_consumed: false", text)
        self.assertIn("worker_started: false", text)
        self.assertIn("sql/N4_2_trigger_schema_rollback.sql", text)


if __name__ == "__main__":
    unittest.main()
