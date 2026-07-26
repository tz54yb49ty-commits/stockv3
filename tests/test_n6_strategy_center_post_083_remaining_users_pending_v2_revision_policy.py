from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "n6_strategy_center_post_083_remaining_users_pending_v2_revision_v1"
BEGIN = f"<!-- policy:{POLICY_ID}:begin -->"
END = f"<!-- policy:{POLICY_ID}:end -->"


def load_policy() -> dict[str, Any]:
    text = (ROOT / "docs/EXECUTION_KERNEL.md").read_text(encoding="utf-8")
    start = text.index(BEGIN) + len(BEGIN)
    end = text.index(END, start)
    match = re.fullmatch(r"```json\s*(\{.*\})\s*```", text[start:end].strip(), re.S)
    if match is None:
        raise AssertionError("remaining-users policy must contain one JSON fence")
    return json.loads(match.group(1))


def canonical_request(policy: dict[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {
        "policy_id": policy["policy_id"],
        "layer_role": policy["layer_role"],
        "scope_mode": policy["scope_mode"],
        "phase_mode": policy["phase_mode"],
        "database_authority_mode": policy["database_authority_mode"],
        "selection_creation_authority_mode": policy[
            "selection_creation_authority_mode"
        ],
        "strategy_write_flag": policy["required_strategy_write_flag_value"],
        "runtime_execution_requested": True,
        "explicit_user_authorization_current_request": True,
        "principal_id": 3,
        "user_id": 3,
        "principal_type": "human_user",
        "active_revision_id": 17,
        "active_revision_no": 3,
        "target_revision_no": 4,
        "previous_revision_id": 17,
        "for_trade_date": "20260724",
        "active_package_keys": ["package_1", "package_2"],
        "target_package_items": [
            {"package_key": "package_1", "package_version": "v2"},
            {"package_key": "package_2", "package_version": "v2"},
        ],
    }
    request.update({field: True for field in policy["required_true_fields"]})
    request.update({field: False for field in policy["required_false_fields"]})
    request.update(policy["required_singleton_counts"])
    request.update(policy["required_operation_counts"])
    return request


def evaluate(policy: dict[str, Any], request: dict[str, Any]) -> str:
    reject = policy["default_runtime_execution_decision"]
    for field in ("policy_id", "layer_role", "scope_mode", "phase_mode"):
        if request.get(field) != policy[field]:
            return reject
    if request.get("runtime_execution_requested") is not True:
        return reject
    if request.get("database_authority_mode") != policy["database_authority_mode"]:
        return reject
    if request.get("selection_creation_authority_mode") != policy[
        "selection_creation_authority_mode"
    ]:
        return reject
    if request.get("strategy_write_flag") != policy["required_strategy_write_flag_value"]:
        return reject
    if not request.get("explicit_user_authorization_current_request"):
        return reject
    positive = ("principal_id", "user_id", "active_revision_id", "active_revision_no",
                "target_revision_no", "previous_revision_id")
    if any(
        isinstance(request.get(field), bool)
        or not isinstance(request.get(field), int)
        or request[field] <= 0
        for field in positive
    ):
        return reject
    if request["target_revision_no"] != request["active_revision_no"] + 1:
        return reject
    if request["previous_revision_id"] != request["active_revision_id"]:
        return reject
    if not re.fullmatch(r"\d{8}", str(request.get("for_trade_date", ""))):
        return reject
    if request.get("target_package_items") is None or [
        item["package_key"] for item in request["target_package_items"]
    ] != request.get("active_package_keys"):
        return reject
    if any(item.get("package_version") != "v2" for item in request["target_package_items"]):
        return reject
    for field, expected in policy["required_singleton_counts"].items():
        if request.get(field) != expected:
            return reject
    for field, expected in policy["required_operation_counts"].items():
        if request.get(field) != expected:
            return reject
    if any(request.get(field) is not True for field in policy["required_true_fields"]):
        return reject
    if any(request.get(field) is not False for field in policy["required_false_fields"]):
        return reject
    return policy["accept_decision"]


class RemainingUsersPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()
        cls.request = canonical_request(cls.policy)

    def decision(self, **changes: Any) -> str:
        request = copy.deepcopy(self.request)
        request.update(changes)
        return evaluate(self.policy, request)

    def test_parameterized_single_scope_accepts(self) -> None:
        self.assertEqual(self.decision(), "ACCEPT")
        self.assertEqual(self.policy["runtime_gate_decision"], "ACCEPT")
        self.assertTrue(self.policy["strategy_write_must_remain_one"])

    def test_all_control_documents_name_policy(self) -> None:
        for relative in (
            "AGENTS.md",
            "docs/EXECUTION_COMPILER.md",
            "docs/EXECUTION_RUNTIME_GATE.md",
            "docs/EXECUTION_SANDBOX.md",
            "docs/EXECUTION_TEST_SUITE.md",
            "docs/EXECUTION_TRACE_SYSTEM.md",
        ):
            with self.subTest(path=relative):
                self.assertIn(POLICY_ID, (ROOT / relative).read_text(encoding="utf-8"))

    def test_first_user_hardcoded_scope_is_not_required(self) -> None:
        self.assertEqual(self.decision(principal_id=5, user_id=5), "ACCEPT")

    def test_scope_and_cas_are_strict(self) -> None:
        for change in (
            {"all_users_requested": True},
            {"multi_scope_requested": True},
            {"target_revision_no": 9},
            {"previous_revision_id": 16},
            {"current_trade_date_matches_n6_authority": False},
            {"target_package_items": [{"package_key": "package_1", "package_version": "v2"}]},
        ):
            with self.subTest(change=change):
                self.assertEqual(self.decision(**change), "REJECT")

    def test_missing_owner_function_is_fail_closed(self) -> None:
        self.assertEqual(self.decision(owner_selection_function_missing=True), "REJECT")
        self.assertTrue(self.policy["owner_selection_function_attestation_required"])
        self.assertEqual(
            self.policy["scope_expansion_if_owner_function_missing"],
            "owner_selection_function",
        )

    def test_web_evaluator_and_forbidden_writes_reject(self) -> None:
        for field in (
            "web_put_requested",
            "evaluator_operation_requested",
            "projection_write_requested",
            "change_write_requested",
            "revision_activation_requested",
            "n1_n5_write_requested",
            "real_broker_connected",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_retry_and_general_runtime_default_reject(self) -> None:
        self.assertEqual(self.decision(retry_requested=True), "REJECT")
        self.assertEqual(self.decision(second_mutation_attempt_requested=True), "REJECT")
        self.assertEqual(self.decision(policy_id="general_runtime_execute"), "REJECT")
        self.assertEqual(self.policy["default_runtime_execution_decision"], "REJECT")

    def test_decision_enumeration_is_unified(self) -> None:
        self.assertEqual(
            self.policy["decision_states"], ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"]
        )


if __name__ == "__main__":
    unittest.main()
