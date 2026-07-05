import unittest

from ashare_v3.condition.execute_plan import (
    ROLLBACK_ORDER,
    WRITE_ORDER,
    build_minute_scope_execute_plan,
    stable_policy_hash,
)


class ConditionExecutePlanTest(unittest.TestCase):
    def test_plan_execute_counts_writes_and_never_executes_sql(self) -> None:
        plan = build_minute_scope_execute_plan(sample_scope_report())

        self.assertEqual(plan["stage"], "N2-D3")
        self.assertEqual(plan["plan_mode"], "plan_execute")
        self.assertEqual(plan["planned_run_id"], "minute_target_scope_20260522_to_20260525_execute")
        self.assertEqual(plan["write_order"], list(WRITE_ORDER))
        self.assertEqual(plan["would_write"]["common_condition_run"]["row_count"], 1)
        self.assertEqual(plan["would_write"]["common_condition_quality_item"]["row_count"], 3)
        self.assertEqual(plan["would_write"]["index_minute_target_scope"]["row_count"], 18)
        self.assertEqual(plan["would_write"]["board_minute_target_scope"]["row_count"], 254)
        self.assertEqual(plan["would_write"]["stock_minute_target_scope"]["row_count"], 7438)
        self.assertEqual(plan["row_count_total"], 7714)
        self.assertFalse(plan["will_connect_database"])
        self.assertFalse(plan["will_execute_sql"])
        self.assertFalse(plan["writes_performed"])
        self.assertFalse(plan["execute_ready"])
        self.assertFalse(plan["execute_supported"])

    def test_plan_execute_reports_confirmation_and_pool_id_dependency(self) -> None:
        plan = build_minute_scope_execute_plan(sample_scope_report())

        self.assertTrue(plan["execute_preconditions_passed"])
        self.assertTrue(plan["requires_user_confirmation"])
        self.assertTrue(plan["requires_persisted_condition_pool_ids"])
        self.assertEqual(plan["blocked_reasons"], [])
        self.assertIn("p1_user_confirmation_required", plan["not_ready_reasons"])
        self.assertIn("source_condition_pool_ids_unavailable", plan["not_ready_reasons"])
        guard_status = {guard["gate_code"]: guard["status"] for guard in plan["execute_guards"]}
        self.assertEqual(guard_status["dry_run_p1_confirmation"], "warning")
        self.assertEqual(guard_status["source_condition_pool_ids_available"], "warning")

    def test_plan_execute_blocks_on_p0_or_source_not_ready(self) -> None:
        report = sample_scope_report()
        report["source_ready_passed"] = False
        report["quality"]["p0_count"] = 2

        plan = build_minute_scope_execute_plan(report)

        self.assertFalse(plan["execute_preconditions_passed"])
        self.assertIn("condition_source_not_ready", plan["blocked_reasons"])
        self.assertIn("p0_quality_failures", plan["blocked_reasons"])

    def test_rollback_plan_deletes_by_run_id_in_reverse_table_order(self) -> None:
        plan = build_minute_scope_execute_plan(sample_scope_report())
        rollback = plan["rollback_plan"]

        self.assertEqual([item["table_name"] for item in rollback["delete_order"]], list(ROLLBACK_ORDER))
        self.assertEqual(
            rollback["delete_order"][0]["sql_template"],
            "DELETE FROM stock_minute_target_scope WHERE run_id = :run_id;",
        )
        self.assertFalse(rollback["will_execute_sql"])

    def test_policy_hash_is_stable_for_key_order(self) -> None:
        left = {"policy_name": "x", "stock": {"directions": ["buy"], "min_total_mv_wan": "1000000"}}
        right = {"stock": {"min_total_mv_wan": "1000000", "directions": ["buy"]}, "policy_name": "x"}

        self.assertEqual(stable_policy_hash(left), stable_policy_hash(right))


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
        "condition_pool_source": {
            "source_condition_pool_ids_available": False,
        },
        "scope_policy": {
            "policy_name": "default_scope_policy",
            "effective_policy": {
                "policy_name": "default_scope_policy",
                "index": {"include_codes": ["000905"], "directions": ["buy", "sell"]},
                "board": {"board_code_prefix": "881", "directions": ["buy", "sell"]},
                "stock": {"min_total_mv_wan": "1000000", "directions": ["buy", "sell"]},
            },
        },
        "scope_preview": {
            "index": {"scope_row_count": 18, "scope_source_counts": {"condition_pool": 18}},
            "board": {"scope_row_count": 254, "scope_source_counts": {"condition_pool": 254}},
            "stock": {"scope_row_count": 7438, "scope_source_counts": {"condition_pool": 7438}},
        },
        "quality": {
            "p0_count": 0,
            "p1_count": 2,
            "p2_count": 1,
            "items": [{"gate_code": "a"}, {"gate_code": "b"}, {"gate_code": "c"}],
        },
    }


if __name__ == "__main__":
    unittest.main()
