from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "windows_rebuild_w0_bounded_v1"


def load_policy() -> dict[str, Any]:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    begin = f"<!-- policy:{POLICY_ID}:begin -->"
    end = f"<!-- policy:{POLICY_ID}:end -->"
    block = text[text.index(begin) + len(begin) : text.index(end)]
    match = re.fullmatch(r"\s*```json\s*(\{.*\})\s*```\s*", block, re.DOTALL)
    if match is None:
        raise AssertionError("W0 policy must contain exactly one valid JSON fence")
    return json.loads(match.group(1))


def canonical_request(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy_id": policy["policy_id"],
        "layer_role": policy["layer_role"],
        "phase_mode": "w0_prepare_and_mutate",
        "phase_attempts": 1,
        "explicit_current_request_authorization": True,
        "independent_execution_session": True,
        "pre_evidence_complete": True,
        "identity_acl_effective_access_proven": True,
        "existing_target_path_conflict": False,
        **{name: 0 for name in policy["required_zero_attempts"]},
    }


def evaluate(policy: dict[str, Any], request: dict[str, Any]) -> str:
    reject = policy["default_runtime_execution_decision"]
    if request.get("policy_id") != policy["policy_id"]:
        return reject
    if request.get("layer_role") != "runtime_control":
        return reject
    if request.get("phase_mode") not in policy["phase_contract"]["allowed_phase_modes"]:
        return reject
    if request.get("phase_attempts") != policy["phase_contract"]["attempts_per_phase"]:
        return reject
    for field in (
        "explicit_current_request_authorization",
        "independent_execution_session",
        "pre_evidence_complete",
        "identity_acl_effective_access_proven",
    ):
        if request.get(field) is not True:
            return reject
    if request.get("existing_target_path_conflict") is not False:
        return reject
    if any(request.get(name) != 0 for name in policy["required_zero_attempts"]):
        return reject
    return policy["accept_decision"]


class WindowsRebuildW0BoundedPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()
        cls.request = canonical_request(cls.policy)

    def decision(self, **overrides: Any) -> str:
        request = copy.deepcopy(self.request)
        request.update(overrides)
        return evaluate(self.policy, request)

    def test_exact_independent_contract_accepts(self) -> None:
        self.assertEqual(self.decision(), "ACCEPT")
        self.assertTrue(self.policy["governance_session_cannot_execute"])
        self.assertEqual(self.policy["policy_state"], "POLICY_READY_NOT_EXECUTED")

    def test_general_or_same_governance_session_rejects(self) -> None:
        self.assertEqual(self.decision(policy_id="general_windows_setup"), "REJECT")
        self.assertEqual(self.decision(independent_execution_session=False), "REJECT")
        self.assertEqual(self.decision(phase_attempts=2), "REJECT")

    def test_every_forbidden_attempt_is_fail_closed(self) -> None:
        for field in self.policy["required_zero_attempts"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: 1}), "REJECT")

    def test_identity_acl_and_path_authority_fail_closed(self) -> None:
        self.assertEqual(self.decision(pre_evidence_complete=False), "REJECT")
        self.assertEqual(
            self.decision(identity_acl_effective_access_proven=False), "REJECT"
        )
        self.assertEqual(self.decision(existing_target_path_conflict=True), "REJECT")
        acl = self.policy["identity_acl_contract"]
        self.assertTrue(acl["application_identity_must_be_non_admin"])
        self.assertTrue(acl["codex_identity_must_be_non_admin"])
        self.assertIn("take_ownership", acl["application_and_codex_denied_rights"])

    def test_empty_cluster_and_windows_only_n1_sources_are_frozen(self) -> None:
        empty = self.policy["empty_cluster_contract"]
        for field, value in empty.items():
            if field.endswith("_attempts"):
                self.assertEqual(value, 0)
        handoff = self.policy["n1_handoff"]
        self.assertEqual(
            handoff["allowed_sources"],
            ["TQ", "eltdx_finance", "self_built_trade_calendar"],
        )
        self.assertIn("Tushare", handoff["forbidden_sources"])
        self.assertIn("Mootdx", handoff["forbidden_sources"])

    def test_scheduler_service_and_shutdown_boundaries_are_exact(self) -> None:
        allowlist = self.policy["exact_allowlist"]
        self.assertEqual(
            allowlist["scheduler_operations"],
            ["export_exact_definition", "disable_exact_task"],
        )
        self.assertEqual(allowlist["legacy_service_name"], "postgresql-x64-18")
        self.assertEqual(
            allowlist["software_package_ids"],
            ["Git.Git", "PostgreSQL.PostgreSQL.16"],
        )
        self.assertEqual(
            allowlist["postgresql_backup_staging"],
            r"D:\PostgreSQL\backup-staging",
        )
        self.assertEqual(
            self.policy["phase_contract"]["shutdown_phase_requires_prior_result"],
            "RESTART_REQUIRED",
        )
        self.assertIn(
            "wsl_shutdown_attempts_in_prepare_phase",
            self.policy["required_zero_attempts"],
        )

    def test_control_plan_references_policy_and_new_empty_cluster(self) -> None:
        plan = (ROOT / "docs" / "WINDOWS_REBUILD_V1_TEST_PLAN.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(POLICY_ID, plan)
        self.assertRegex(plan, r"new empty\s+cluster")
        self.assertIn("Tushare, Mootdx", plan)
        self.assertIn("otherwise fail closed", plan)
        self.assertIn("Build the three-year daily-bar base from zero", plan)
        self.assertIn("never use a Mac database dump", plan)


if __name__ == "__main__":
    unittest.main()
