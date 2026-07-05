import unittest

from ashare_v3.condition.readiness_plan import (
    ROLLBACK_ORDER,
    WRITE_ORDER,
    build_condition_layer_execute_readiness_plan,
)


class ConditionReadinessPlanTest(unittest.TestCase):
    def test_readiness_plan_combines_basis_pool_and_scope_counts(self) -> None:
        plan = build_condition_layer_execute_readiness_plan(
            basis_report=sample_basis_report(),
            pool_report=sample_pool_report(),
            scope_report=sample_scope_report(),
        )

        self.assertEqual(plan["stage"], "N2-E0")
        self.assertEqual(plan["planned_run_id"], "condition_layer_20260522_to_20260525_execute")
        self.assertEqual(plan["write_order"], list(WRITE_ORDER))
        self.assertEqual(plan["stage_counts"]["condition_basis"], {"stock": 5376, "index": 9, "board": 127})
        self.assertEqual(plan["stage_counts"]["condition_pool"], {"stock": 20246, "index": 273, "board": 1575})
        self.assertEqual(plan["stage_counts"]["minute_target_scope"], {"stock": 7438, "index": 18, "board": 254})
        self.assertEqual(plan["would_write"]["common_condition_run"]["row_count"], 1)
        self.assertEqual(plan["would_write"]["stock_monitor_target"]["row_count"], 5376)
        self.assertEqual(plan["would_write"]["stock_condition_pool"]["row_count"], 20246)
        self.assertEqual(plan["would_write"]["stock_minute_target_scope"]["row_count"], 7438)
        self.assertFalse(plan["will_execute_sql"])
        self.assertFalse(plan["writes_performed"])
        self.assertFalse(plan["minute_kline_pulled"])

    def test_readiness_plan_records_dependencies_and_rollback_order(self) -> None:
        plan = build_condition_layer_execute_readiness_plan(
            basis_report=sample_basis_report(),
            pool_report=sample_pool_report(),
            scope_report=sample_scope_report(),
        )

        self.assertTrue(plan["dependency_plan"]["condition_pool_source_basis_id"]["required"])
        self.assertTrue(plan["dependency_plan"]["condition_basis_source_monitor_target_id"]["required"])
        self.assertTrue(plan["dependency_plan"]["stock_scope_source_pool_id"]["required"])
        self.assertEqual([item["table_name"] for item in plan["rollback_plan"]["delete_order"]], list(ROLLBACK_ORDER))
        self.assertEqual(
            plan["rollback_plan"]["delete_order"][0]["sql_template"],
            "DELETE FROM stock_minute_target_scope WHERE run_id = :run_id;",
        )
        self.assertIn(
            "DELETE FROM stock_monitor_target WHERE source_version = :run_id;",
            [item["sql_template"] for item in plan["rollback_plan"]["delete_order"]],
        )

    def test_readiness_plan_requires_confirmation_for_p1_but_has_clean_p0(self) -> None:
        plan = build_condition_layer_execute_readiness_plan(
            basis_report=sample_basis_report(),
            pool_report=sample_pool_report(),
            scope_report=sample_scope_report(),
        )

        self.assertTrue(plan["execute_preconditions_passed"])
        self.assertTrue(plan["requires_user_confirmation"])
        self.assertEqual(plan["blocked_reasons"], [])
        self.assertIn("p1_user_confirmation_required", plan["not_ready_reasons"])
        self.assertIn("n2_e0_plan_only_execute_not_supported", plan["not_ready_reasons"])

    def test_readiness_plan_blocks_on_p0(self) -> None:
        basis = sample_basis_report()
        basis["quality"]["p0_count"] = 1

        plan = build_condition_layer_execute_readiness_plan(
            basis_report=basis,
            pool_report=sample_pool_report(),
            scope_report=sample_scope_report(),
        )

        self.assertFalse(plan["execute_preconditions_passed"])
        self.assertIn("aggregate_p0_clean", plan["blocked_reasons"])

    def test_readiness_plan_blocks_when_date_contexts_differ(self) -> None:
        scope = sample_scope_report()
        scope["for_trade_date"] = "20260526"

        plan = build_condition_layer_execute_readiness_plan(
            basis_report=sample_basis_report(),
            pool_report=sample_pool_report(),
            scope_report=scope,
        )

        self.assertFalse(plan["execute_preconditions_passed"])
        self.assertIn("date_context_consistent", plan["blocked_reasons"])


def sample_basis_report() -> dict[str, object]:
    return {
        "run_id": "condition_basis_20260522_to_20260525_dry_run",
        "source_trade_date": "20260522",
        "for_trade_date": "20260525",
        "prev_trade_date": "20260522",
        "source_ready_passed": True,
        "source_versions": {
            "stock_daily": "stock_daily_20260522_v1",
            "index_daily": "index_daily_20260522_v1",
            "board_daily": "board_daily_20260522_v1",
        },
        "basis_preview": {
            "stock": {"row_count": 5376},
            "index": {"row_count": 9},
            "board": {"row_count": 127},
        },
        "quality": {
            "p0_count": 0,
            "p1_count": 3,
            "p2_count": 2,
            "items": [{"gate_code": "basis_a"}, {"gate_code": "basis_b"}],
        },
    }


def sample_pool_report() -> dict[str, object]:
    return {
        "run_id": "condition_pool_20260522_to_20260525_dry_run",
        "source_trade_date": "20260522",
        "for_trade_date": "20260525",
        "prev_trade_date": "20260522",
        "source_ready_passed": True,
        "pool_preview": {
            "stock": {"pool_row_count": 20246},
            "index": {"pool_row_count": 273},
            "board": {"pool_row_count": 1575},
        },
        "quality": {
            "p0_count": 0,
            "p1_count": 1,
            "p2_count": 1,
            "items": [{"gate_code": "pool_a"}],
        },
    }


def sample_scope_report() -> dict[str, object]:
    return {
        "run_id": "minute_target_scope_20260522_to_20260525_dry_run",
        "source_trade_date": "20260522",
        "for_trade_date": "20260525",
        "prev_trade_date": "20260522",
        "for_trade_calendar_row_exists": False,
        "source_ready_passed": True,
        "source_versions": {
            "stock_daily": "stock_daily_20260522_v1",
            "index_daily": "index_daily_20260522_v1",
            "board_daily": "board_daily_20260522_v1",
        },
        "scope_policy": {
            "policy_name": "default_scope_policy",
            "effective_policy": {
                "policy_name": "default_scope_policy",
                "stock": {"min_total_mv_wan": "1000000"},
            },
        },
        "scope_preview": {
            "stock": {"scope_row_count": 7438},
            "index": {"scope_row_count": 18},
            "board": {"scope_row_count": 254},
        },
        "quality": {
            "p0_count": 0,
            "p1_count": 2,
            "p2_count": 1,
            "items": [{"gate_code": "scope_a"}, {"gate_code": "scope_b"}],
        },
    }


if __name__ == "__main__":
    unittest.main()
