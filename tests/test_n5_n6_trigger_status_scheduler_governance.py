from __future__ import annotations

import copy
from hashlib import sha256
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/N6_B_TRACK_DELIVERY_GOVERNANCE_V1.json"
POLICY_ID = "n5_n6_trigger_status_scheduled_convergence_30s_v1"
RECOVERY_POLICY_ID = "n5_trigger_status_scheduler_timeout_recovery_20260804_v1"
N5_PHASE = "trigger_status_n5_forward_scheduler_activation"
N6_PHASE = "trigger_status_n6_projection_scheduler_activation"
RECOVERY_PHASE = "trigger_status_n5_scheduler_timeout_recovery_20260804"
RECOVERY_PHASE_HASH = "be588f7842e0f0d0667a9113c6d446f5db94b15755f51da87bfe0da63e1f75f6"
PHASE_HASHES = {
    N5_PHASE: "8acdfe1a7dea74cab97224fab0dc1775fafd83e61e9cf1ded280b0b7ef023215",
    N6_PHASE: "083acdcce8df5e9f845785a1136e758fbc0ae1f00f3fc0e35021acce6d709e81",
}


def canonical_hash(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return sha256(payload).hexdigest()


class TriggerStatusSchedulerGovernanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.phases = cls.contract["lanes"]["L2"]["scheduled_convergence_phases"]
        cls.recovery = cls.contract["lanes"]["L2"]["scheduled_recovery_phases"][
            RECOVERY_PHASE
        ]

    def test_exact_phases_are_hash_locked_and_ordered(self) -> None:
        self.assertEqual(list(self.phases), [N5_PHASE, N6_PHASE])
        for phase_id, expected_hash in PHASE_HASHES.items():
            phase = self.phases[phase_id]
            self.assertEqual(canonical_hash(phase), expected_hash)
            self.assertEqual(phase["policy_id"], POLICY_ID)
            self.assertEqual(phase["default_decision"], "REJECT")
            self.assertTrue(phase["separate_current_request_authorization_required"])
            self.assertTrue(phase["governance_session_cannot_execute"])

    def test_n5_phase_is_status_outbox_only(self) -> None:
        phase = self.phases[N5_PHASE]
        self.assertEqual(phase["layer_role"], "N5_action")
        runtime = phase["runtime_contract"]
        self.assertEqual(runtime["label"], "com.ashare-v3.n5.trigger-status-forward-v1")
        self.assertEqual(runtime["start_interval_seconds"], 30)
        self.assertFalse(runtime["run_at_load"])
        self.assertFalse(runtime["keep_alive"])
        self.assertEqual(runtime["bootstrap_attempts"], 1)
        self.assertEqual(runtime["kickstart_attempts"], 0)
        self.assertEqual(runtime["retry_attempts"], 0)
        authority = phase["date_and_authority_contract"]
        self.assertEqual(authority["action_eligible_authority_count"], 1)
        self.assertEqual(authority["closed_date_decision"], "NOOP")
        self.assertIn("common_action_event_or_tracking_write", phase["forbidden_effects"])
        self.assertIn("n6_projection_write", phase["forbidden_effects"])

    def test_n6_phase_requires_n5_and_isolated_checkpoint(self) -> None:
        phase = self.phases[N6_PHASE]
        self.assertEqual(phase["layer_role"], "N6_user")
        self.assertEqual(
            phase["prerequisites"]["n5_scheduler_activation_and_natural_tick_observation"],
            "PASS",
        )
        runtime = phase["runtime_contract"]
        self.assertEqual(runtime["label"], "com.ashare-v3.n6.trigger-status-projection-v1")
        self.assertEqual(runtime["consumer_name"], "n6_trigger_status_projection_v1")
        self.assertEqual(runtime["steady_state_convergence_seconds"], 60)
        self.assertIn("common_event_outbox_status_update", phase["forbidden_effects"])
        self.assertIn("other_consumer_or_checkpoint_change", phase["forbidden_effects"])
        self.assertIn("trigger_pct_surface", phase["forbidden_effects"])

    def test_any_activation_drift_rejects(self) -> None:
        for phase_id in (N5_PHASE, N6_PHASE):
            phase = self.phases[phase_id]
            candidate = copy.deepcopy(phase)
            candidate["runtime_contract"]["start_interval_seconds"] = 29
            self.assertNotEqual(canonical_hash(candidate), PHASE_HASHES[phase_id])
            candidate = copy.deepcopy(phase)
            candidate["runtime_contract"]["retry_attempts"] = 1
            self.assertNotEqual(canonical_hash(candidate), PHASE_HASHES[phase_id])

    def test_timeout_recovery_is_hash_locked_and_n5_only(self) -> None:
        phase = self.recovery
        self.assertEqual(canonical_hash(phase), RECOVERY_PHASE_HASH)
        self.assertEqual(phase["policy_id"], RECOVERY_POLICY_ID)
        self.assertEqual(phase["layer_role"], "N5_action")
        self.assertEqual(phase["default_decision"], "REJECT")
        self.assertTrue(phase["governance_session_cannot_execute"])
        self.assertEqual(
            phase["implementation_contract"]["exact_diff_allowlist"],
            [
                "scripts/run_n5_trigger_status_forward_once.py",
                "scripts/run_n5_trigger_status_forward_current_once.py",
                "tests/test_n5_trigger_status_forward_current.py",
            ],
        )
        self.assertEqual(
            phase["implementation_contract"]["plan_failure_verdict"],
            "BLOCKED_CORE_PLAN_READ",
        )
        self.assertFalse(
            phase["implementation_contract"]["plan_failure_requires_post_check"]
        )
        self.assertTrue(
            phase["implementation_contract"]["write_failure_requires_post_check"]
        )
        self.assertFalse(phase["implementation_contract"]["schema_or_index_change_allowed"])
        runtime = phase["runtime_contract"]
        self.assertEqual(runtime["label"], "com.ashare-v3.n5.trigger-status-forward-v1")
        self.assertEqual(runtime["bootout_attempts"], 1)
        self.assertEqual(runtime["bootstrap_attempts"], 1)
        self.assertEqual(runtime["kickstart_attempts"], 0)
        self.assertEqual(runtime["retry_attempts"], 0)
        self.assertIn("n6_label_or_projection_operation", phase["forbidden_effects"])

    def test_policy_is_synchronized_across_control_documents(self) -> None:
        paths = (
            ROOT / "AGENTS.md",
            ROOT / "docs/N5_N6_TRIGGER_STATUS_FORWARD_CONTRACT_V1.md",
            ROOT / "docs/Tasks.md",
            ROOT / "docs/Roadmap.md",
            ROOT / "docs/EXECUTION_KERNEL.md",
            ROOT / "docs/EXECUTION_COMPILER.md",
            ROOT / "docs/EXECUTION_RUNTIME_GATE.md",
            CONTRACT,
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertIn(POLICY_ID, path.read_text(encoding="utf-8"))
                self.assertIn(RECOVERY_POLICY_ID, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
