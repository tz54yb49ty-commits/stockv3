from __future__ import annotations

import unittest

from ashare_v3.ingestion.environment_probe_application import REQUIRED_PROBE_OPERATOR_APPROVALS
from ashare_v3.ingestion.environment_probe_artifact_plan import REQUIRED_ARTIFACT_KINDS
from ashare_v3.ingestion.environment_probe_authorization_summary import (
    AUTHORIZATION_BLOCKERS,
    SENSITIVE_REAL_PROBE_ACTIONS,
    build_environment_probe_authorization_summary,
)
from ashare_v3.ingestion.environment_probe_plan import REQUIRED_PROBE_ITEM_IDS


class EnvironmentProbeAuthorizationSummaryTest(unittest.TestCase):
    def test_summary_passes_but_is_not_ready_for_real_probe(self) -> None:
        summary = build_environment_probe_authorization_summary()

        self.assertTrue(summary.passed)
        self.assertFalse(summary.ready_for_real_probe)
        self.assertTrue(summary.input_artifact_plan_passed)
        self.assertFalse(summary.input_artifact_plan_ready_to_write)
        self.assertFalse(summary.will_authorize_real_probe)

    def test_summary_carries_probe_scope(self) -> None:
        summary = build_environment_probe_authorization_summary()

        self.assertEqual(summary.probe_item_ids, REQUIRED_PROBE_ITEM_IDS)
        self.assertEqual(len(summary.runbook_step_ids), len(REQUIRED_PROBE_ITEM_IDS))
        self.assertEqual(summary.artifact_kinds, REQUIRED_ARTIFACT_KINDS)
        self.assertEqual(summary.data_root, "/Volumes/MacRaid/database")
        self.assertEqual(summary.audit_root, "/Volumes/MacRaid/database/audit/environment_probe")

    def test_summary_carries_pending_approvals_and_blockers(self) -> None:
        summary = build_environment_probe_authorization_summary()

        self.assertEqual(summary.pending_approval_item_ids, REQUIRED_PROBE_OPERATOR_APPROVALS)
        self.assertEqual(len(summary.pending_approval_item_ids), 8)
        self.assertEqual(len(summary.inherited_blocking_finding_ids), 15)
        self.assertIn("probe_plan_not_ready", summary.inherited_blocking_finding_ids)
        self.assertIn("__probe_plan__", summary.inherited_blocking_result_item_ids)
        self.assertEqual(summary.authorization_blockers, AUTHORIZATION_BLOCKERS)

    def test_sensitive_actions_are_declared_and_disabled(self) -> None:
        summary = build_environment_probe_authorization_summary()

        self.assertEqual(summary.sensitive_action_ids, SENSITIVE_REAL_PROBE_ACTIONS)
        for action in summary.sensitive_actions:
            self.assertFalse(action.allowed_in_n3_12)
            self.assertIn(action.required_approval_item, REQUIRED_PROBE_OPERATOR_APPROVALS)
        self.assertIn("read_environment_variable_metadata", summary.sensitive_action_ids)
        self.assertIn("open_short_postgresql_readonly_connection", summary.sensitive_action_ids)
        self.assertIn("call_tushare_connectivity_probe", summary.sensitive_action_ids)
        self.assertIn("call_mootdx_connectivity_probe", summary.sensitive_action_ids)

    def test_quality_gate_names_are_explicit(self) -> None:
        summary = build_environment_probe_authorization_summary()

        self.assertEqual(
            [gate.gate_name for gate in summary.quality_gates],
            [
                "probe_authorization_artifact_plan_passed_but_not_ready",
                "probe_authorization_probe_scope_complete",
                "probe_authorization_artifacts_complete",
                "probe_authorization_approvals_still_pending",
                "probe_authorization_blockers_carried_forward",
                "probe_authorization_sensitive_actions_declared",
                "probe_authorization_blockers_explicit",
                "probe_authorization_not_ready_for_real_probe",
                "probe_authorization_no_side_effects",
            ],
        )
        self.assertTrue(all(gate.passed for gate in summary.quality_gates))

    def test_payload_counts_are_explicit(self) -> None:
        payload = build_environment_probe_authorization_summary().to_dict()

        self.assertFalse(payload["ready_for_real_probe"])
        self.assertEqual(payload["probe_item_count"], 14)
        self.assertEqual(payload["runbook_step_count"], 14)
        self.assertEqual(payload["artifact_count"], 4)
        self.assertEqual(payload["pending_approval_count"], 8)
        self.assertEqual(payload["inherited_blocking_finding_count"], 15)
        self.assertEqual(len(payload["sensitive_action_ids"]), 7)

    def test_no_side_effects_are_enabled(self) -> None:
        payload = build_environment_probe_authorization_summary().to_dict()

        self.assertTrue(all(value is False for value in payload["side_effects"].values()))


if __name__ == "__main__":
    unittest.main()
