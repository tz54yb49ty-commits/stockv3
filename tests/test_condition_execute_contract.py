import unittest

from ashare_v3.condition.execute_contract import (
    FORBIDDEN_WRITE_DOMAINS,
    RUN_ID_TEMPLATE,
    build_condition_execute_contract,
)
from ashare_v3.condition.active_status import CANONICAL_ACTIVE_STATUS, LEGACY_ACTIVE_STATUS
from ashare_v3.condition.readiness_plan import ROLLBACK_ORDER, WRITE_ORDER


class ConditionExecuteContractTest(unittest.TestCase):
    def test_contract_defaults_to_no_overwrite_and_requires_confirmation_for_p1(self) -> None:
        contract = build_condition_execute_contract(sample_readiness_plan())

        self.assertEqual(contract["stage"], "N2-E1")
        self.assertEqual(contract["run_id_contract"]["execute_run_id_template"], RUN_ID_TEMPLATE)
        self.assertTrue(contract["run_id_contract"]["must_generate_new_run_id_per_execute"])
        self.assertFalse(contract["overwrite"])
        self.assertEqual(contract["active_run_contract"]["active_run_policy"], "reject_if_active_exists")
        self.assertTrue(contract["quality_policy"]["user_confirmation_required"])
        self.assertFalse(contract["execute_request_allowed"])
        self.assertFalse(contract["will_execute_sql"])
        self.assertFalse(contract["writes_performed"])
        self.assertIn("user_confirmation_required", contract["not_ready_reasons"])

    def test_contract_allows_execute_request_only_after_user_confirmation(self) -> None:
        contract = build_condition_execute_contract(sample_readiness_plan(), user_confirmed=True, operator="chuan")

        self.assertTrue(contract["execute_request_allowed"])
        self.assertFalse(contract["execute_ready"])
        self.assertFalse(contract["execute_supported"])
        self.assertEqual(contract["operator"], "chuan")
        self.assertEqual(contract["blocked_reasons"], [])
        self.assertEqual(contract["not_ready_reasons"], ["n2_e1_contract_only_execute_not_supported"])

    def test_overwrite_contract_requires_confirmation_and_uses_superseded_policy(self) -> None:
        contract = build_condition_execute_contract(sample_readiness_plan(), overwrite=True)

        self.assertFalse(contract["execute_request_allowed"])
        self.assertEqual(contract["active_run_contract"]["active_run_policy"], "overwrite_requires_confirmation")
        self.assertTrue(contract["active_run_contract"]["overwrite_requires_user_confirmation"])
        self.assertIn("overwrite_requires_user_confirmation", contract["not_ready_reasons"])
        self.assertIn("superseded", " ".join(contract["active_run_contract"]["switch_after_postcheck_sql_templates"]))

    def test_contract_contains_write_rollback_and_verification_requirements(self) -> None:
        contract = build_condition_execute_contract(sample_readiness_plan(), user_confirmed=True)

        self.assertEqual(contract["write_contract"]["write_order"], list(WRITE_ORDER))
        self.assertEqual(contract["write_contract"]["common_condition_run_success_status"], CANONICAL_ACTIVE_STATUS)
        self.assertEqual(contract["active_run_contract"]["canonical_active_status"], CANONICAL_ACTIVE_STATUS)
        self.assertEqual(contract["active_run_contract"]["legacy_active_status"], LEGACY_ACTIVE_STATUS)
        self.assertIn("passed_active", contract["active_run_contract"]["active_run_lookup_sql_template"])
        self.assertIn("passed", contract["active_run_contract"]["active_run_lookup_sql_template"])
        self.assertEqual(
            [item["table_name"] for item in contract["rollback_contract"]["delete_order"]],
            list(ROLLBACK_ORDER),
        )
        self.assertEqual(
            contract["rollback_contract"]["delete_order"][0]["sql_template"],
            "DELETE FROM stock_minute_target_scope WHERE run_id = :execute_run_id;",
        )
        self.assertIn(
            "DELETE FROM stock_monitor_target WHERE source_version = :execute_run_id;",
            [item["sql_template"] for item in contract["rollback_contract"]["delete_order"]],
        )
        self.assertIn("condition_basis_source_monitor_target_id", contract["write_contract"]["id_mapping_requirements"])
        self.assertEqual(contract["verification_contract"]["forbidden_write_domains"], list(FORBIDDEN_WRITE_DOMAINS))
        self.assertIn("forbidden_field_scan_passed", contract["verification_contract"]["post_execute"])
        self.assertIn(CANONICAL_ACTIVE_STATUS, contract["rollback_contract"]["restore_previous_active_sql_template"])

    def test_contract_blocks_on_readiness_p0(self) -> None:
        readiness = sample_readiness_plan()
        readiness["execute_preconditions_passed"] = False
        readiness["quality_summary"]["p0_count"] = 1

        contract = build_condition_execute_contract(readiness, user_confirmed=True)

        self.assertFalse(contract["execute_request_allowed"])
        self.assertIn("readiness_preconditions_failed", contract["blocked_reasons"])
        self.assertIn("p0_quality_failures", contract["blocked_reasons"])


def sample_readiness_plan() -> dict[str, object]:
    return {
        "planned_run_id": "condition_layer_20260522_to_20260525_execute",
        "source_trade_date": "20260522",
        "for_trade_date": "20260525",
        "prev_trade_date": "20260522",
        "source_versions": {
            "stock_daily": "stock_daily_20260522_v1",
            "index_daily": "index_daily_20260522_v1",
            "board_daily": "board_daily_20260522_v1",
        },
        "policy_name": "default_scope_policy",
        "policy_hash": "abc123",
        "stage_counts": {
            "condition_basis": {"stock": 5504, "index": 80, "board": 428},
            "condition_pool": {"stock": 20246, "index": 273, "board": 1575},
            "minute_target_scope": {"stock": 7438, "index": 18, "board": 254},
        },
        "quality_summary": {
            "p0_count": 0,
            "p1_count": 9,
            "p2_count": 3,
            "quality_item_count": 61,
        },
        "would_write": {
            "common_condition_run": {"row_count": 1},
            "common_condition_quality_item": {"row_count": 61},
            "stock_condition_basis": {"row_count": 5504},
            "index_condition_basis": {"row_count": 80},
            "board_condition_basis": {"row_count": 428},
            "stock_condition_pool": {"row_count": 20246},
            "index_condition_pool": {"row_count": 273},
            "board_condition_pool": {"row_count": 1575},
            "index_minute_target_scope": {"row_count": 18},
            "board_minute_target_scope": {"row_count": 254},
            "stock_minute_target_scope": {"row_count": 7438},
        },
        "rollback_plan": {
            "strategy": "delete_by_run_id",
            "run_id": "condition_layer_20260522_to_20260525_execute",
        },
        "execute_preconditions_passed": True,
    }


if __name__ == "__main__":
    unittest.main()
