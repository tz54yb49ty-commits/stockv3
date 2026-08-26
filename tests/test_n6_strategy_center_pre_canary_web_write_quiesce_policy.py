from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "n6_strategy_center_pre_canary_web_write_quiesce_v1"


def load_policy(policy_id: str) -> dict[str, Any]:
    text = (ROOT / "docs" / "EXECUTION_KERNEL.md").read_text(encoding="utf-8")
    begin = f"<!-- policy:{policy_id}:begin -->"
    end = f"<!-- policy:{policy_id}:end -->"
    block = text[text.index(begin) + len(begin) : text.index(end)]
    match = re.fullmatch(r"\s*```json\s*(\{.*\})\s*```\s*", block, re.DOTALL)
    if match is None:
        raise AssertionError(f"invalid policy block: {policy_id}")
    return json.loads(match.group(1))


def canonical_request(policy: dict[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {}
    request.update({field: "a" * 64 for field in policy["required_hash_fields"]})
    request.update(policy["required_singleton_counts"])
    request.update({field: True for field in policy["required_true_fields"]})
    request.update({field: False for field in policy["required_false_fields"]})
    return request


def evaluate(policy: dict[str, Any], request: dict[str, Any]) -> str:
    reject = policy["default_runtime_execution_decision"]
    if any(request.get(field) is not True for field in policy["required_true_fields"]):
        return reject
    if any(request.get(field) is not False for field in policy["required_false_fields"]):
        return reject
    for field, expected in policy["required_singleton_counts"].items():
        if request.get(field) != expected:
            return reject
    for field, pattern in policy["required_hash_fields"].items():
        value = request.get(field)
        if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
            return reject
    return policy["accept_decision"]


class N6StrategyCenterPreCanaryWebWriteQuiescePolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy(POLICY_ID)
        cls.request = canonical_request(cls.policy)

    def test_complete_contract_accepts(self) -> None:
        self.assertEqual(evaluate(self.policy, self.request), "ACCEPT")
        self.assertEqual(self.policy["layer_role"], "runtime_control")
        self.assertEqual(self.policy["required_flag_before"], "1")
        self.assertEqual(self.policy["required_flag_target"], "0")
        self.assertEqual(self.policy["required_flag_after"], "0")
        self.assertEqual(self.policy["rollback_flag_value"], "1")
        self.assertEqual(
            self.policy["source_target_release_relation"],
            "same_exact_immutable_release",
        )

    def test_evaluator_must_already_be_quiesced(self) -> None:
        for field in (
            "evaluator_job_absent_verified",
            "evaluator_runner_process_count_zero_verified",
            "evaluator_not_operated_verified",
        ):
            request = copy.deepcopy(self.request)
            request[field] = False
            self.assertEqual(evaluate(self.policy, request), "REJECT")
        request = copy.deepcopy(self.request)
        request["evaluator_operation_requested"] = True
        self.assertEqual(evaluate(self.policy, request), "REJECT")

    def test_release_and_plist_delta_are_exact(self) -> None:
        self.assertEqual(
            self.policy["required_release_commit"],
            "d85df6328bde223e912dabc3bd65e16df984aa45",
        )
        self.assertEqual(
            self.policy["required_release_tree"],
            "d6d5ae1d68a1255ea9f05d8e7ce40a837a572ea1",
        )
        for field in (
            "web_release_change_requested",
            "working_directory_change_requested",
            "pythonpath_change_requested",
            "non_flag_environment_change_requested",
            "release_or_plist_hash_drift_detected",
        ):
            request = copy.deepcopy(self.request)
            request[field] = True
            self.assertEqual(evaluate(self.policy, request), "REJECT")

    def test_attempts_and_rollback_are_bounded(self) -> None:
        counts = self.policy["required_singleton_counts"]
        self.assertEqual(counts["web_bootout_attempts"], 1)
        self.assertEqual(counts["web_bootstrap_attempts"], 1)
        self.assertEqual(counts["primary_retries"], 0)
        self.assertEqual(self.policy["maximum_rollback_bootout_attempts"], 1)
        self.assertEqual(self.policy["maximum_rollback_bootstrap_attempts"], 1)
        self.assertTrue(self.policy["rollback_requires_primary_health_failure"])
        for field in ("web_bootout_attempts", "web_bootstrap_attempts"):
            request = copy.deepcopy(self.request)
            request[field] = 2
            self.assertEqual(evaluate(self.policy, request), "REJECT")

    def test_virtual_executor_database_and_trading_reject(self) -> None:
        for field in (
            "virtual_executor_operation_requested",
            "database_connection_requested",
            "migration_requested",
            "bounded_canary_requested_in_same_gate",
            "selection_projection_change_requested",
            "n1_n5_write_requested",
            "proposal_touched",
            "order_touched",
            "trade_touched",
            "position_touched",
            "cash_touched",
            "real_broker_connected",
        ):
            request = copy.deepcopy(self.request)
            request[field] = True
            self.assertEqual(evaluate(self.policy, request), "REJECT")

    def test_bounded_and_scheduled_require_strategy_write_zero(self) -> None:
        for policy_id in (
            "n6_strategy_center_display_only_bounded_run_once_v1",
            "n6_strategy_center_display_only_scheduled_evaluator_v1",
        ):
            policy = load_policy(policy_id)
            self.assertEqual(policy["required_strategy_write_flag_value"], "0")
            self.assertIn("strategy_write_zero_verified", policy["required_true_fields"])
            self.assertIn(
                "strategy_write_nonzero_detected",
                policy["required_false_fields"],
            )

    def test_policy_is_discoverable_across_control_contracts(self) -> None:
        for path in (
            ROOT / "AGENTS.md",
            ROOT / "docs" / "EXECUTION_COMPILER.md",
            ROOT / "docs" / "EXECUTION_RUNTIME_GATE.md",
            ROOT / "docs" / "EXECUTION_SANDBOX.md",
            ROOT / "docs" / "EXECUTION_TEST_SUITE.md",
            ROOT / "docs" / "EXECUTION_TRACE_SYSTEM.md",
        ):
            self.assertIn(POLICY_ID, path.read_text(encoding="utf-8"))

    def test_general_runtime_remains_default_reject(self) -> None:
        self.assertEqual(
            self.policy["default_runtime_execution_decision"],
            "REJECT",
        )
        self.assertTrue(self.policy["governance_session_cannot_execute"])


if __name__ == "__main__":
    unittest.main()
