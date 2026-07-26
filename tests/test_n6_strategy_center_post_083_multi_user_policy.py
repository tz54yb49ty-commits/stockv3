from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "n6_strategy_center_post_083_multi_user_pending_v2_revision_v1"


def load_policy() -> dict[str, Any]:
    text = (ROOT / "docs/EXECUTION_KERNEL.md").read_text(encoding="utf-8")
    begin = f"<!-- policy:{POLICY_ID}:begin -->"
    end = f"<!-- policy:{POLICY_ID}:end -->"
    body = text[text.index(begin) + len(begin) : text.index(end)]
    match = re.search(r"```json\s*(\{.*?\})\s*```", body, re.DOTALL)
    if match is None:
        raise AssertionError("policy JSON missing")
    return json.loads(match.group(1))


def evaluate(policy: dict[str, Any], request: dict[str, Any]) -> str:
    if request.get("policy_id") != policy["policy_id"]:
        return "REJECT"
    if request.get("layer_role") != policy["layer_role"]:
        return "REJECT"
    if not request.get("explicit_user_authorization"):
        return "REJECT"
    if request.get("scope_count") != 1 or request.get("all_users"):
        return "REJECT"
    for key in (
        "migration_081_committed",
        "migration_082_committed",
        "migration_083_committed",
        "current_authority_verified",
        "predecessor_cas_verified",
        "v2_catalog_active",
        "strategy_write_zero",
        "evaluator_absent",
        "pending_zero",
        "v2_item_zero",
        "owner_function_attested",
    ):
        if request.get(key) is not True:
            return "REJECT"
    if request.get("virtual_executor_operations") != 0:
        return "REJECT"
    if request.get("mutation_attempts") != 1 or request.get("retries") != 0:
        return "REJECT"
    if request.get("projection_change_writes") != 0:
        return "REJECT"
    if request.get("write_tables") != policy["allowed_write_tables"]:
        return "REJECT"
    if request.get("function") != policy["allowed_write_function"]:
        return "REJECT"
    if request.get("forbidden_path"):
        return "REJECT"
    return policy["accept_decision"]


class MultiUserV2PolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()
        cls.request = {
            "policy_id": POLICY_ID,
            "layer_role": "N6_user",
            "explicit_user_authorization": True,
            "scope_count": 1,
            "all_users": False,
            "migration_081_committed": True,
            "migration_082_committed": True,
            "migration_083_committed": True,
            "current_authority_verified": True,
            "predecessor_cas_verified": True,
            "v2_catalog_active": True,
            "strategy_write_zero": True,
            "evaluator_absent": True,
            "pending_zero": True,
            "v2_item_zero": True,
            "owner_function_attested": True,
            "virtual_executor_operations": 0,
            "mutation_attempts": 1,
            "retries": 0,
            "projection_change_writes": 0,
            "write_tables": list(cls.policy["allowed_write_tables"]),
            "function": cls.policy["allowed_write_function"],
            "forbidden_path": False,
        }

    def decision(self, **changes: Any) -> str:
        request = copy.deepcopy(self.request)
        request.update(changes)
        return evaluate(self.policy, request)

    def test_exact_single_scope_accepts(self) -> None:
        self.assertEqual(self.decision(), "ACCEPT")

    def test_all_users_and_multiple_scopes_reject(self) -> None:
        self.assertEqual(self.decision(all_users=True), "REJECT")
        self.assertEqual(self.decision(scope_count=7), "REJECT")

    def test_missing_or_drifted_prerequisites_reject(self) -> None:
        for field in (
            "migration_081_committed",
            "migration_082_committed",
            "migration_083_committed",
            "current_authority_verified",
            "predecessor_cas_verified",
            "v2_catalog_active",
            "strategy_write_zero",
            "evaluator_absent",
            "pending_zero",
            "v2_item_zero",
            "owner_function_attested",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")

    def test_forbidden_writes_and_retry_reject(self) -> None:
        for changes in (
            {"virtual_executor_operations": 1},
            {"projection_change_writes": 1},
            {"mutation_attempts": 2},
            {"retries": 1},
            {"forbidden_path": True},
            {"function": "manual_dml"},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(self.decision(**changes), "REJECT")

    def test_general_runtime_and_database_write_remain_reject(self) -> None:
        self.assertEqual(self.decision(policy_id="general_runtime_execute"), "REJECT")
        self.assertEqual(self.decision(layer_role="runtime_control"), "REJECT")

    def test_decision_enum_is_stable(self) -> None:
        self.assertEqual(
            self.policy["decision_states"], ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"]
        )


if __name__ == "__main__":
    unittest.main()
