from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "docs" / "EXECUTION_KERNEL.md"


def load_policy(policy_id: str) -> dict[str, Any]:
    text = KERNEL.read_text(encoding="utf-8")
    begin = f"<!-- policy:{policy_id}:begin -->"
    end = f"<!-- policy:{policy_id}:end -->"
    block = text[text.index(begin) + len(begin) : text.index(end)]
    match = re.fullmatch(r"\s*```json\s*(\{.*\})\s*```\s*", block, re.DOTALL)
    if match is None:
        raise AssertionError(f"invalid policy block: {policy_id}")
    return json.loads(match.group(1))


def evaluate_matrix(policy: dict[str, Any], request: dict[str, Any]) -> str:
    reject = policy["default_runtime_execution_decision"]
    if request.get("explicit_user_authorization_current_request") is not True:
        return reject
    if any(request.get(field) is not True for field in policy["required_true_fields"]):
        return reject
    if any(request.get(field) is not False for field in policy["required_false_fields"]):
        return reject
    return policy["accept_decision"]


def canonical_request(policy: dict[str, Any]) -> dict[str, Any]:
    request = {
        "explicit_user_authorization_current_request": True,
    }
    request.update({field: True for field in policy["required_true_fields"]})
    request.update({field: False for field in policy["required_false_fields"]})
    return request


class N6StrategyCenterGate3PlusGovernanceUnionTest(unittest.TestCase):
    def test_reviewed_n6_authority_is_the_only_strategy_date_authority(self) -> None:
        policy = load_policy(
            "n6_strategy_center_reviewed_view_date_authority_084_v1"
        )
        self.assertEqual(len(policy["required_authority_views"]), 3)
        self.assertEqual(
            policy["authority_rule"],
            "latest_complete_single_batch_for_trade_date_consensus",
        )
        self.assertEqual(
            policy["membership_rule"],
            "max_trade_date_lte_source_trade_date",
        )
        self.assertIn("common_trade_calendar", policy["forbidden_objects"])
        self.assertIn("n1_n5_raw_tables", policy["forbidden_objects"])

        bounded = load_policy(
            "n6_strategy_center_display_only_bounded_run_once_v1"
        )
        coexistence = bounded["virtual_executor_coexistence_contract"]
        self.assertEqual(
            coexistence["trade_date_authority"],
            "reviewed_n6_display_basis_consensus",
        )
        self.assertNotIn("required_trade_date", coexistence)
        self.assertNotIn("required_selection_revision_id", coexistence)

        scheduled = load_policy(
            "n6_strategy_center_display_only_scheduled_evaluator_v1"
        )
        self.assertNotIn("trade_calendar_date_field", scheduled)
        self.assertNotIn("trade_calendar_open_field", scheduled)
        self.assertEqual(len(scheduled["reviewed_authority_views"]), 3)

    def test_current_date_bounded_canary_accept_reject_matrix(self) -> None:
        policy = load_policy(
            "n6_strategy_center_display_only_bounded_run_once_v1"
        )
        request = canonical_request(policy)
        self.assertEqual(evaluate_matrix(policy, request), "ACCEPT")
        for field in (
            "reviewed_n6_authority_consensus_verified",
            "reviewed_n6_latest_complete_batches_verified",
            "reviewed_n6_projection_card_watermarks_frozen",
            "membership_asof_provenance_frozen",
            "natural_current_date_reviewed_events_present",
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(request)
                changed[field] = False
                self.assertEqual(evaluate_matrix(policy, changed), "REJECT")
        for field in (
            "common_trade_calendar_authority_requested",
            "n1_n5_raw_table_authority_requested",
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(request)
                changed[field] = True
                self.assertEqual(evaluate_matrix(policy, changed), "REJECT")

    def test_scheduled_evaluator_contract_requires_twelve_tick_observation(self) -> None:
        policy = load_policy(
            "n6_strategy_center_display_only_scheduled_evaluator_v1"
        )
        self.assertEqual(policy["start_interval_seconds"], 5)
        self.assertEqual(policy["max_scopes_per_tick"], 1)
        self.assertEqual(
            policy["scheduler_mode"],
            "current_open_trade_date_pending_first_active_round_robin",
        )
        self.assertEqual(policy["required_post_activation_tick_observation_count"], 12)
        self.assertIn("twelve_tick_observation_contract_frozen", policy["required_true_fields"])
        self.assertIn("virtual_executor_operation_requested", policy["required_false_fields"])
        self.assertNotIn("virtual_executor_unloaded_verified", policy["required_true_fields"])

    def test_canary_and_evaluator_require_write_quiesced(self) -> None:
        for policy_id in (
            "n6_strategy_center_display_only_bounded_run_once_v1",
            "n6_strategy_center_display_only_scheduled_evaluator_v1",
        ):
            policy = load_policy(policy_id)
            self.assertEqual(policy["required_strategy_write_flag_value"], "0")
            self.assertIn("strategy_write_zero_verified", policy["required_true_fields"])
            self.assertIn("strategy_write_nonzero_detected", policy["required_false_fields"])

    def test_web_write_restore_contract_is_flag_only_after_stable_ticks(self) -> None:
        policy = load_policy(
            "n6_strategy_center_post_canary_web_write_restore_v1"
        )
        self.assertEqual(policy["required_flag_before"], "0")
        self.assertEqual(policy["required_flag_after"], "1")
        self.assertEqual(policy["required_evaluator_ticks"], 12)
        self.assertEqual(policy["required_pending_count"], 0)
        self.assertEqual(policy["max_bootout_attempts"], 1)
        self.assertEqual(policy["max_bootstrap_attempts"], 1)
        self.assertEqual(policy["max_retries"], 0)
        self.assertEqual(policy["virtual_executor_operations"], 0)
        self.assertEqual(policy["database_writes"], 0)
        self.assertEqual(policy["trade_writes"], 0)

    def test_each_remaining_user_is_one_dynamic_cas_gate(self) -> None:
        policy = load_policy(
            "n6_strategy_center_post_083_remaining_users_pending_v2_revision_v1"
        )
        request = canonical_request(policy)
        self.assertEqual(evaluate_matrix(policy, request), "ACCEPT")
        self.assertEqual(policy["expected_rollout_gate_count"], 7)
        self.assertEqual(policy["required_singleton_counts"]["scope_count"], 1)
        self.assertEqual(policy["required_operation_counts"]["target_mutation_attempts"], 1)
        self.assertEqual(policy["required_operation_counts"]["target_mutation_retries"], 0)
        self.assertNotIn("revision_id", json.dumps(policy))
        self.assertNotIn("202607", json.dumps(policy))
        for field in (
            "all_users_requested",
            "multi_scope_requested",
            "revision_activation_requested",
            "projection_write_requested",
            "change_write_requested",
            "common_trade_calendar_authority_requested",
            "n1_n5_raw_table_authority_requested",
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(request)
                changed[field] = True
                self.assertEqual(evaluate_matrix(policy, changed), "REJECT")

    def test_v1_retirement_is_final_catalog_only_gate(self) -> None:
        policy = load_policy(
            "n6_strategy_center_v1_retirement_after_all_users_v2_v1"
        )
        request = canonical_request(policy)
        self.assertEqual(evaluate_matrix(policy, request), "ACCEPT")
        self.assertEqual(policy["allowed_write_tables"], ["n6_strategy_package_catalog"])
        self.assertEqual(policy["required_completed_remaining_user_gate_count"], 7)
        self.assertEqual(policy["required_pending_count"], 0)
        self.assertEqual(policy["required_remaining_v1_active_user_count"], 0)
        self.assertEqual(policy["attempts"], 1)
        self.assertEqual(policy["retries"], 0)
        for field in (
            "any_active_v1_user_detected",
            "any_pending_revision_detected",
            "selection_revision_write_requested",
            "projection_write_requested",
            "change_write_requested",
            "evaluator_operation_requested",
            "virtual_executor_operation_requested",
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(request)
                changed[field] = True
                self.assertEqual(evaluate_matrix(policy, changed), "REJECT")

    def test_existing_ff3_policies_are_preserved(self) -> None:
        for policy_id in (
            "n6_strategy_center_evaluator_quiesce_for_web_rebind_v1",
            "n6_strategy_center_post_083_v2_web_bounded_rebind_v1",
            "n6_immutable_release_privileged_materialize_and_install_v1",
        ):
            policy = load_policy(policy_id)
            self.assertEqual(policy["default_runtime_execution_decision"], "REJECT")
            self.assertEqual(policy["accept_decision"], "ACCEPT")

    def test_general_runtime_and_database_writes_still_default_reject(self) -> None:
        for policy_id in (
            "n6_strategy_center_display_only_bounded_run_once_v1",
            "n6_strategy_center_display_only_scheduled_evaluator_v1",
            "n6_strategy_center_post_canary_web_write_restore_v1",
            "n6_strategy_center_pre_canary_web_write_quiesce_v1",
            "n6_strategy_center_post_083_remaining_users_pending_v2_revision_v1",
            "n6_strategy_center_v1_retirement_after_all_users_v2_v1",
        ):
            with self.subTest(policy_id=policy_id):
                self.assertEqual(
                    load_policy(policy_id)["default_runtime_execution_decision"],
                    "REJECT",
                )


if __name__ == "__main__":
    unittest.main()
