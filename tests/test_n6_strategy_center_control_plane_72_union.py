from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "docs" / "EXECUTION_KERNEL.md"
L2 = (
    ROOT
    / "docs"
    / "N6_STRATEGY_CENTER_SHADOW_ACTIVATION_GRANT_V1_SUPERSESSION_L2_20260726.json"
)


def load_policy(policy_id: str) -> dict[str, Any]:
    text = KERNEL.read_text(encoding="utf-8")
    begin = f"<!-- policy:{policy_id}:begin -->"
    end = f"<!-- policy:{policy_id}:end -->"
    block = text[text.index(begin) + len(begin) : text.index(end)]
    match = re.fullmatch(r"\s*```json\s*(\{.*\})\s*```\s*", block, re.DOTALL)
    if match is None:
        raise AssertionError(f"invalid policy block: {policy_id}")
    return json.loads(match.group(1))


class N6StrategyCenterControlPlane72UnionTest(unittest.TestCase):
    def test_canary_and_scheduled_evaluator_require_write_zero(self) -> None:
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

    def test_pre_canary_gate3_contract_is_preserved(self) -> None:
        policy = load_policy(
            "n6_strategy_center_pre_canary_web_write_quiesce_v1"
        )
        self.assertEqual(policy["required_flag_before"], "1")
        self.assertEqual(policy["required_flag_target"], "0")
        self.assertEqual(policy["source_target_release_relation"], "same_exact_immutable_release")
        self.assertEqual(policy["required_singleton_counts"]["evaluator_operation_attempts"], 0)
        self.assertIn("evaluator_job_absent_verified", policy["required_true_fields"])
        self.assertIn("bounded_canary_requested_in_same_gate", policy["required_false_fields"])

    def test_resumable_policy_is_web_first_and_evaluator_blocked(self) -> None:
        policy = load_policy("n6_strategy_center_shadow_activation_grant_v1")
        self.assertEqual(
            policy["required_internal_checkpoints"],
            {
                "BOUNDED_REBIND_WEB_TARGET": "planned",
                "BOUNDED_REBIND_EVALUATOR_TARGET": "blocked_pending_canary",
            },
        )
        self.assertEqual(policy["required_web_strategy_write_before"], "0")
        self.assertEqual(policy["required_web_strategy_write_after"], "0")
        self.assertTrue(policy["web_target_evaluator_job_must_remain_absent"])
        self.assertEqual(policy["web_target_evaluator_runner_count"], 0)
        self.assertEqual(policy["evaluator_target_pre_canary_bootstrap_attempts"], 0)
        self.assertTrue(
            policy["evaluator_target_requires_current_date_bounded_canary_pass"]
        )

    def test_l2_binds_72_and_non_regressing_f464(self) -> None:
        document = json.loads(L2.read_text(encoding="utf-8"))
        payload = document["supersession_payload"]
        self.assertEqual(
            payload["control_plane_authority"],
            {
                "commit": "72b1d50b6658d89e3aff6ed15619b875814f8e5e",
                "tree": "f7e835e53146e30b8ab4ed8096133b1e14b14a12",
                "integration_mode": "explicit_merge_parent_plus_blob_union",
                "final_governance_binding": "external_post_commit_attestation",
            },
        )
        non_regression = payload["semantic_non_regression"]
        self.assertTrue(non_regression["d85_to_f464_compatible_successor"])
        for key in (
            "candidate_sha256",
            "canonical_sha256",
            "web_api_sha256",
            "migration_085_forward_sha256",
            "migration_085_rollback_sha256",
            "migration_086_forward_sha256",
            "migration_086_rollback_sha256",
        ):
            self.assertRegex(non_regression[key], r"^[0-9a-f]{64}$")
        self.assertFalse(
            payload["bundle_supersession"][
                "historical_anchor_is_execution_authority"
            ]
        )

    def test_control_contracts_discover_both_policies(self) -> None:
        for path in (
            ROOT / "AGENTS.md",
            ROOT / "docs" / "EXECUTION_COMPILER.md",
            ROOT / "docs" / "EXECUTION_RUNTIME_GATE.md",
            ROOT / "docs" / "EXECUTION_SANDBOX.md",
            ROOT / "docs" / "EXECUTION_TEST_SUITE.md",
            ROOT / "docs" / "EXECUTION_TRACE_SYSTEM.md",
        ):
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                "n6_strategy_center_pre_canary_web_write_quiesce_v1",
                text,
            )
            self.assertIn("n6_strategy_center_shadow_activation_grant_v1", text)


if __name__ == "__main__":
    unittest.main()
