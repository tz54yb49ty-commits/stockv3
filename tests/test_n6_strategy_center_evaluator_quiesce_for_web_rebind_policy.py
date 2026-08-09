from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "n6_strategy_center_evaluator_quiesce_for_web_rebind_v1"
WEB_POLICY_ID = "n6_user_web_immutable_release_bounded_rebind_v1"
SCHEDULED_POLICY_ID = "n6_strategy_center_display_only_scheduled_evaluator_v1"


def load_policy(policy_id: str = POLICY_ID) -> dict[str, Any]:
    text = (ROOT / "docs" / "EXECUTION_KERNEL.md").read_text(encoding="utf-8")
    begin = f"<!-- policy:{policy_id}:begin -->"
    end = f"<!-- policy:{policy_id}:end -->"
    start = text.index(begin) + len(begin)
    stop = text.index(end, start)
    fenced = text[start:stop].strip()
    match = re.fullmatch(r"```json\s*(\{.*\})\s*```", fenced, re.DOTALL)
    if match is None:
        raise AssertionError(f"{policy_id} must contain exactly one valid JSON fence")
    return json.loads(match.group(1))


def canonical_request(policy: dict[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {
        "policy_id": policy["policy_id"],
        "layer_role": policy["layer_role"],
        "scope_mode": policy["scope_mode"],
        "phase_mode": policy["phase_mode"],
        "launch_agent_label": policy["launch_agent_label"],
        "launch_agent_plist_path": policy["launch_agent_plist_path"],
        "web_launch_agent_label": policy["web_launch_agent_label"],
        "virtual_executor_launch_agent_label": policy[
            "virtual_executor_launch_agent_label"
        ],
        "strategy_write_flag": policy["required_strategy_write_flag_value"],
        "declared_mutation_resources": list(policy["allowed_mutation_resources"]),
        "declared_runtime_operations": list(policy["allowed_runtime_operations"]),
        "evaluator_bootout_attempts": policy["evaluator_bootout_attempts"],
        "evaluator_bootstrap_attempts": policy["evaluator_bootstrap_attempts"],
        "retry_attempts": policy["maximum_retries"],
        "teardown_timeout_seconds": policy["teardown_timeout_seconds"],
        "failure_auto_restore_evaluator": policy[
            "failure_auto_restore_evaluator"
        ],
        "normal_virtual_executor_pid_runs_change_is_configuration_drift": policy[
            "normal_virtual_executor_pid_runs_change_is_configuration_drift"
        ],
    }
    request.update(policy["required_singleton_counts"])
    request.update({field: "a" * 64 for field in policy["required_hash_fields"]})
    request.update({field: True for field in policy["required_true_fields"]})
    request.update({field: False for field in policy["required_false_fields"]})
    return request


def strict_non_negative_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def evaluate(policy: dict[str, Any], request: dict[str, Any]) -> str:
    reject = policy["default_runtime_execution_decision"]
    for field in (
        "policy_id",
        "layer_role",
        "scope_mode",
        "phase_mode",
        "launch_agent_label",
        "launch_agent_plist_path",
        "web_launch_agent_label",
        "virtual_executor_launch_agent_label",
    ):
        if request.get(field) != policy[field]:
            return reject

    for field, pattern in policy["required_hash_fields"].items():
        value = request.get(field)
        if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
            return reject

    for field, expected in policy["required_singleton_counts"].items():
        value = request.get(field)
        if not strict_non_negative_int(value) or value != expected:
            return reject

    if any(request.get(field) is not True for field in policy["required_true_fields"]):
        return reject
    if any(request.get(field) is not False for field in policy["required_false_fields"]):
        return reject

    if request.get("strategy_write_flag") != policy[
        "required_strategy_write_flag_value"
    ]:
        return reject
    if request.get("declared_mutation_resources") != policy[
        "allowed_mutation_resources"
    ]:
        return reject
    if request.get("declared_runtime_operations") != policy[
        "allowed_runtime_operations"
    ]:
        return reject
    if request.get("evaluator_bootout_attempts") != policy[
        "evaluator_bootout_attempts"
    ]:
        return reject
    if request.get("evaluator_bootstrap_attempts") != policy[
        "evaluator_bootstrap_attempts"
    ]:
        return reject
    if request.get("retry_attempts") != policy["maximum_retries"]:
        return reject
    if request.get("teardown_timeout_seconds") != policy[
        "teardown_timeout_seconds"
    ]:
        return reject
    if request.get("failure_auto_restore_evaluator") is not policy[
        "failure_auto_restore_evaluator"
    ]:
        return reject
    if request.get(
        "normal_virtual_executor_pid_runs_change_is_configuration_drift"
    ) is not policy[
        "normal_virtual_executor_pid_runs_change_is_configuration_drift"
    ]:
        return reject
    return policy["accept_decision"]


class N6StrategyCenterEvaluatorQuiesceForWebRebindPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()
        cls.request = canonical_request(cls.policy)

    def decision(self, **changes: Any) -> str:
        request = copy.deepcopy(self.request)
        request.update(changes)
        return evaluate(self.policy, request)

    def test_complete_exact_quiesce_contract_accepts(self) -> None:
        self.assertEqual(self.decision(), "ACCEPT")
        self.assertEqual(self.policy["runtime_gate_decision"], "ACCEPT")
        self.assertEqual(
            self.policy["decision_states"],
            ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"],
        )

    def test_default_and_unknown_runtime_execution_reject(self) -> None:
        self.assertEqual(self.policy["default_runtime_execution_decision"], "REJECT")
        self.assertEqual(self.decision(policy_id="general_runtime_execute"), "REJECT")

    def test_current_request_authorization_is_required(self) -> None:
        self.assertEqual(
            self.decision(explicit_user_authorization_current_request=False),
            "REJECT",
        )

    def test_exact_runtime_control_scope_phase_labels_and_plist_are_required(
        self,
    ) -> None:
        cases = {
            "layer_role": "N6_user",
            "scope_mode": "all_services",
            "phase_mode": "normal_web_rebind",
            "launch_agent_label": "com.ashare-v3.n6.other",
            "launch_agent_plist_path": "/tmp/other.plist",
            "web_launch_agent_label": "com.ashare-v3.n6.other",
            "virtual_executor_launch_agent_label": "com.ashare-v3.n6.other",
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: value}), "REJECT")

    def test_post_083_and_strategy_write_one_are_required(self) -> None:
        self.assertEqual(self.decision(post_083_state_verified=False), "REJECT")
        self.assertEqual(self.decision(strategy_write_flag="0"), "REJECT")
        self.assertEqual(
            self.decision(strategy_write_flag_one_verified=False),
            "REJECT",
        )

    def test_all_frozen_hashes_are_strict_and_required(self) -> None:
        for field in self.policy["required_hash_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: "bad"}), "REJECT")

    def test_all_required_true_fields_fail_closed(self) -> None:
        for field in self.policy["required_true_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")

    def test_all_required_false_fields_fail_closed(self) -> None:
        for field in self.policy["required_false_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_exact_single_target_counts_are_required(self) -> None:
        for field in self.policy["required_singleton_counts"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: 2}), "REJECT")
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_only_exact_evaluator_job_resource_is_mutable(self) -> None:
        self.assertEqual(
            self.policy["allowed_mutation_resources"],
            ["gui/current-user/com.ashare-v3.n6.strategy-center-evaluator-v1"],
        )
        self.assertEqual(
            self.decision(declared_mutation_resources=[]),
            "REJECT",
        )
        self.assertEqual(
            self.decision(
                declared_mutation_resources=[
                    *self.policy["allowed_mutation_resources"],
                    "gui/current-user/com.ashare-v3.n6.user-web",
                ]
            ),
            "REJECT",
        )

    def test_only_bootout_wait_and_evidence_operations_are_allowed(self) -> None:
        self.assertEqual(
            self.decision(declared_runtime_operations=["launchctl_bootout"]),
            "REJECT",
        )
        self.assertNotIn(
            "launchctl_bootstrap_exact_evaluator_label",
            self.policy["allowed_runtime_operations"],
        )

    def test_exactly_one_bootout_zero_bootstrap_and_zero_retry_are_required(
        self,
    ) -> None:
        cases = {
            "evaluator_bootout_attempts": 0,
            "evaluator_bootstrap_attempts": 1,
            "retry_attempts": 1,
            "teardown_timeout_seconds": 60,
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: value}), "REJECT")

    def test_bootstrap_kickstart_kill_execution_and_restore_reject(self) -> None:
        fields = (
            "evaluator_execute_requested",
            "evaluator_bootstrap_requested",
            "evaluator_kickstart_requested",
            "evaluator_kill_or_signal_requested",
            "evaluator_retry_requested",
            "evaluator_automatic_restore_requested",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")
        self.assertEqual(self.decision(failure_auto_restore_evaluator=True), "REJECT")

    def test_web_operations_reject(self) -> None:
        for field in (
            "web_operation_requested",
            "web_plist_modification_requested",
            "web_bootout_requested",
            "web_bootstrap_requested",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_virtual_executor_operation_and_configuration_drift_reject(self) -> None:
        for field in (
            "virtual_executor_operation_requested",
            "virtual_executor_configuration_drift_detected",
            "virtual_executor_role_acl_drift_detected",
            "virtual_executor_object_boundary_drift_detected",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_normal_virtual_executor_pid_runs_cycle_is_not_drift(self) -> None:
        self.assertFalse(
            self.policy[
                "normal_virtual_executor_pid_runs_change_is_configuration_drift"
            ]
        )
        self.assertEqual(
            self.decision(
                normal_virtual_executor_pid_runs_change_is_configuration_drift=False,
                normal_virtual_executor_pid_runs_change_treated_as_drift=False,
            ),
            "ACCEPT",
        )
        self.assertEqual(
            self.decision(
                normal_virtual_executor_pid_runs_change_treated_as_drift=True
            ),
            "REJECT",
        )

    def test_database_migration_and_strategy_business_paths_reject(self) -> None:
        fields = (
            "database_connection_requested",
            "database_write_requested",
            "migration_requested",
            "selection_projection_change_touched",
            "outbox_inbox_checkpoint_mutation_requested",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_trading_and_n1_n5_paths_reject(self) -> None:
        fields = (
            "proposal_touched",
            "order_touched",
            "trade_touched",
            "position_touched",
            "cash_touched",
            "real_broker_connected",
            "n1_n5_write_requested",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_ownership_and_identity_drift_reject(self) -> None:
        fields = (
            "runtime_ownership_ambiguous",
            "evaluator_label_drift_detected",
            "evaluator_plist_drift_detected",
            "evaluator_runner_drift_detected",
            "evaluator_release_drift_detected",
            "evaluator_role_acl_drift_detected",
            "concurrent_runtime_change",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_existing_web_and_scheduled_policies_remain_unchanged(self) -> None:
        web = load_policy(WEB_POLICY_ID)
        scheduled = load_policy(SCHEDULED_POLICY_ID)
        self.assertEqual(web["required_strategy_write_flag_value"], "1")
        self.assertEqual(scheduled["layer_role"], "N6_user")
        self.assertNotEqual(web["policy_id"], self.policy["policy_id"])
        self.assertNotEqual(scheduled["policy_id"], self.policy["policy_id"])

    def test_all_control_documents_name_the_policy(self) -> None:
        for relative in (
            "AGENTS.md",
            "docs/EXECUTION_KERNEL.md",
            "docs/EXECUTION_COMPILER.md",
            "docs/EXECUTION_RUNTIME_GATE.md",
            "docs/EXECUTION_SANDBOX.md",
            "docs/EXECUTION_TEST_SUITE.md",
            "docs/EXECUTION_TRACE_SYSTEM.md",
        ):
            with self.subTest(path=relative):
                self.assertIn(
                    POLICY_ID,
                    (ROOT / relative).read_text(encoding="utf-8"),
                )


if __name__ == "__main__":
    unittest.main()
