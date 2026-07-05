import unittest

from ashare_v3.market.schema_migration_plan import (
    build_market_data_schema_migration_plan_from_inputs,
)
from ashare_v3.market.schema_migration_review import REQUIRED_MARKET_CONTROL_TABLES


class MarketDataSchemaMigrationPlanTest(unittest.TestCase):
    def test_plan_is_ready_for_confirmation_but_not_execute_allowed_without_user_confirmation(self) -> None:
        report = build_market_data_schema_migration_plan_from_inputs(
            schema_path="sql/006_market_data_layer_schema.sql",
            review=sample_review(),
            subscription_report=sample_subscription_report(),
            subscription_report_path="docs/N3_0_market_data_subscription_plan_20260525.json",
            user_confirmation=False,
        )

        self.assertTrue(report["ready_for_user_confirmation"])
        self.assertTrue(report["user_confirmation_required"])
        self.assertFalse(report["user_confirmation_present"])
        self.assertFalse(report["execute_allowed"])
        self.assertIn("pending_explicit_user_confirmation", report["not_ready_reasons"])
        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertEqual(report["quality"]["p1_count"], 1)
        self.assertFalse(report["side_effects"]["will_execute_sql"])

    def test_plan_execute_allowed_only_when_confirmation_is_present(self) -> None:
        report = build_market_data_schema_migration_plan_from_inputs(
            schema_path="sql/006_market_data_layer_schema.sql",
            review=sample_review(),
            subscription_report=sample_subscription_report(),
            subscription_report_path="docs/N3_0_market_data_subscription_plan_20260525.json",
            user_confirmation=True,
        )

        self.assertTrue(report["ready_for_user_confirmation"])
        self.assertTrue(report["user_confirmation_present"])
        self.assertTrue(report["execute_allowed"])
        self.assertEqual(report["not_ready_reasons"], [])
        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertEqual(report["quality"]["p1_count"], 0)

    def test_missing_subscription_report_is_p0_blocker(self) -> None:
        report = build_market_data_schema_migration_plan_from_inputs(
            schema_path="sql/006_market_data_layer_schema.sql",
            review=sample_review(),
            subscription_report=None,
            subscription_report_path="missing.json",
            user_confirmation=True,
        )

        self.assertFalse(report["ready_for_user_confirmation"])
        self.assertFalse(report["execute_allowed"])
        self.assertIn("subscription_plan_not_ready", report["not_ready_reasons"])
        self.assertGreater(report["quality"]["p0_count"], 0)

    def test_rollback_sql_preview_drops_new_control_tables_in_reverse_order(self) -> None:
        report = build_market_data_schema_migration_plan_from_inputs(
            schema_path="sql/006_market_data_layer_schema.sql",
            review=sample_review(),
            subscription_report=sample_subscription_report(),
            subscription_report_path="docs/N3_0_market_data_subscription_plan_20260525.json",
            user_confirmation=False,
        )

        rollback = report["rollback_sql_preview"]
        self.assertEqual(rollback[0], "-- Only for a later user-confirmed first-apply migration, before business rows exist.")
        drop_lines = [line for line in rollback if line.startswith("DROP TABLE")]
        self.assertEqual(
            drop_lines,
            [
                "DROP TABLE IF EXISTS common_market_data_pull_plan;",
                "DROP TABLE IF EXISTS common_market_data_subscription;",
                "DROP TABLE IF EXISTS common_market_data_subscription_candidate;",
                "DROP TABLE IF EXISTS common_market_data_quality_item;",
                "DROP TABLE IF EXISTS common_market_data_run;",
            ],
        )


def sample_review() -> dict[str, object]:
    return {
        "stage": "N3-0C",
        "schema_path": "sql/006_market_data_layer_schema.sql",
        "migration_required": True,
        "ready_for_user_migration_review": True,
        "migration_safe_to_apply_after_user_confirmation": True,
        "manual_review_required": False,
        "database_status": {
            "market_tables_existing": [],
            "market_tables_missing": list(REQUIRED_MARKET_CONTROL_TABLES),
            "dependency_missing": [],
            "all_market_tables_missing": True,
        },
        "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0},
    }


def sample_subscription_report() -> dict[str, object]:
    return {
        "source_condition_run_id": "condition_layer_20260522_to_20260525_test_execute",
        "for_trade_date": "20260525",
        "source_scope_row_count": 7875,
        "candidate_row_count": 23625,
        "subscription_row_count": 6561,
        "subscription_object_count": 2187,
        "required_data_kind_counts": {
            "realtime_daily_snapshot": 2187,
            "minute_bar_1m": 2187,
            "previous_day_minute_bar_1m": 2187,
        },
        "dedup_ratio": 0.277714,
        "passed": True,
        "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0},
    }


if __name__ == "__main__":
    unittest.main()
