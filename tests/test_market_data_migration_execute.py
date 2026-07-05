import unittest

from ashare_v3.market.migration_execute import (
    N3_TARGET_TABLES,
    build_post_migration_checks,
    summarize_gap,
)


class MarketDataMigrationExecuteTest(unittest.TestCase):
    def test_post_checks_pass_when_schema_ready_rows_empty_and_active_snapshot_unchanged(self) -> None:
        row_counts = {
            table_name: {"exists": True, "row_count": 0, "status": "present"}
            for table_name in N3_TARGET_TABLES
        }
        active_snapshot = {"common_condition_run_active": {"exists": True, "rows": [{"run_id": "r1"}]}}
        checks = build_post_migration_checks(
            pre_backup={"active_snapshot": active_snapshot},
            post_backup={"active_snapshot": active_snapshot, "n3_target_row_counts": row_counts},
            post_gap=ready_gap(),
            post_review={"passed": True, "quality": {"p0_count": 0}},
        )

        self.assertTrue(all(checks.values()))

    def test_post_checks_detect_active_snapshot_change(self) -> None:
        row_counts = {
            table_name: {"exists": True, "row_count": 0, "status": "present"}
            for table_name in N3_TARGET_TABLES
        }
        checks = build_post_migration_checks(
            pre_backup={"active_snapshot": {"common_condition_run_active": {"rows": [{"run_id": "before"}]}}},
            post_backup={
                "active_snapshot": {"common_condition_run_active": {"rows": [{"run_id": "after"}]}},
                "n3_target_row_counts": row_counts,
            },
            post_gap=ready_gap(),
            post_review={"passed": True, "quality": {"p0_count": 0}},
        )

        self.assertFalse(checks["n1_n2_active_run_unchanged"])

    def test_post_checks_detect_market_fact_or_outbox_rows(self) -> None:
        row_counts = {
            table_name: {"exists": True, "row_count": 0, "status": "present"}
            for table_name in N3_TARGET_TABLES
        }
        row_counts["common_event_outbox"] = {"exists": True, "row_count": 1, "status": "present"}
        active_snapshot = {"common_condition_run_active": {"rows": [{"run_id": "r1"}]}}

        checks = build_post_migration_checks(
            pre_backup={"active_snapshot": active_snapshot},
            post_backup={"active_snapshot": active_snapshot, "n3_target_row_counts": row_counts},
            post_gap=ready_gap(),
            post_review={"passed": True, "quality": {"p0_count": 0}},
        )

        self.assertFalse(checks["n3_target_tables_row_count_zero"])
        self.assertFalse(checks["no_market_fact_or_outbox_business_events"])

    def test_summarize_gap_counts_core_gap_fields(self) -> None:
        summary = summarize_gap(
            {
                "migration_required": False,
                "migration_safe_to_apply": True,
                "manual_review_required": False,
                "missing_tables": [],
                "missing_columns": [],
                "type_mismatch": [],
                "missing_unique_constraints": [],
                "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0},
            }
        )

        self.assertEqual(summary["missing_columns_count"], 0)
        self.assertEqual(summary["type_mismatch_count"], 0)
        self.assertEqual(summary["missing_unique_constraints_count"], 0)


def ready_gap() -> dict[str, object]:
    return {
        "missing_tables": [],
        "missing_columns": [],
        "type_mismatch": [],
        "missing_unique_constraints": [],
    }


if __name__ == "__main__":
    unittest.main()
