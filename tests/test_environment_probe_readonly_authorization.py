from __future__ import annotations

import unittest

from ashare_v3.ingestion.environment_probe_application import REQUIRED_PROBE_OPERATOR_APPROVALS
from ashare_v3.ingestion.environment_probe_authorization_summary import (
    AUTHORIZATION_BLOCKERS,
    SENSITIVE_REAL_PROBE_ACTIONS,
)
from ashare_v3.ingestion.environment_probe_readonly_authorization import (
    READONLY_AUTHORIZATION_FORBIDDEN_OUTPUTS,
    READONLY_AUTHORIZATION_OUTPUT_FIELDS,
    REQUIRED_READONLY_AUTHORIZATION_PHRASE,
    build_environment_probe_readonly_authorization_request,
)


class EnvironmentProbeReadOnlyAuthorizationRequestTest(unittest.TestCase):
    def test_request_passes_but_is_not_ready_for_real_probe(self) -> None:
        request = build_environment_probe_readonly_authorization_request()

        self.assertTrue(request.passed)
        self.assertFalse(request.ready_for_real_probe)
        self.assertTrue(request.input_summary_passed)
        self.assertFalse(request.input_summary_ready_for_real_probe)
        self.assertFalse(request.authorization_phrase_present)
        self.assertEqual(request.required_authorization_phrase, REQUIRED_READONLY_AUTHORIZATION_PHRASE)

    def test_action_requests_cover_sensitive_actions_and_stay_disabled(self) -> None:
        request = build_environment_probe_readonly_authorization_request()

        self.assertEqual(request.action_ids, SENSITIVE_REAL_PROBE_ACTIONS)
        self.assertEqual(len(request.sensitive_action_requests), 7)
        self.assertEqual(len(request.pending_action_ids), 7)
        for action_request in request.sensitive_action_requests:
            self.assertEqual(action_request.approval_status, "pending_user_confirmation")
            self.assertFalse(action_request.will_execute)
            self.assertIn(action_request.required_approval_item, REQUIRED_PROBE_OPERATOR_APPROVALS)

    def test_output_policies_block_secrets_payloads_and_rows(self) -> None:
        request = build_environment_probe_readonly_authorization_request()

        for action_request in request.sensitive_action_requests:
            self.assertEqual(action_request.allowed_outputs, READONLY_AUTHORIZATION_OUTPUT_FIELDS)
            self.assertEqual(action_request.forbidden_outputs, READONLY_AUTHORIZATION_FORBIDDEN_OUTPUTS)
            self.assertTrue(action_request.redaction_policy)
        self.assertIn("tushare_token_value", READONLY_AUTHORIZATION_FORBIDDEN_OUTPUTS)
        self.assertIn("postgres_dsn_value", READONLY_AUTHORIZATION_FORBIDDEN_OUTPUTS)
        self.assertIn("tdx_file_content", READONLY_AUTHORIZATION_FORBIDDEN_OUTPUTS)
        self.assertIn("external_api_payload", READONLY_AUTHORIZATION_FORBIDDEN_OUTPUTS)

    def test_requested_scopes_are_specific(self) -> None:
        request = build_environment_probe_readonly_authorization_request()
        requests = {action_request.action_id: action_request for action_request in request.sensitive_action_requests}

        self.assertIn("environment variable names", requests["read_environment_variable_metadata"].requested_scope)
        self.assertIn("do not read file contents", requests["check_tdx_root_and_txt_file_metadata"].requested_scope)
        self.assertIn("readonly PostgreSQL", requests["open_short_postgresql_readonly_connection"].requested_scope)
        self.assertIn("discard response payload", requests["call_tushare_connectivity_probe"].requested_scope)
        self.assertIn("discard response payload", requests["call_mootdx_connectivity_probe"].requested_scope)

    def test_inherits_approvals_and_blockers(self) -> None:
        request = build_environment_probe_readonly_authorization_request()

        self.assertEqual(request.pending_approval_item_ids, REQUIRED_PROBE_OPERATOR_APPROVALS)
        self.assertEqual(len(request.pending_approval_item_ids), 8)
        self.assertEqual(len(request.inherited_blocking_finding_ids), 15)
        self.assertIn("probe_plan_not_ready", request.inherited_blocking_finding_ids)
        self.assertIn("__probe_plan__", request.inherited_blocking_result_item_ids)
        self.assertEqual(request.inherited_authorization_blockers, AUTHORIZATION_BLOCKERS)

    def test_quality_gate_names_are_explicit(self) -> None:
        request = build_environment_probe_readonly_authorization_request()

        self.assertEqual(
            [gate.gate_name for gate in request.quality_gates],
            [
                "readonly_authorization_summary_passed_but_not_ready",
                "readonly_authorization_actions_cover_sensitive_scope",
                "readonly_authorization_actions_pending_and_disabled",
                "readonly_authorization_exact_phrase_required",
                "readonly_authorization_approval_refs_valid",
                "readonly_authorization_output_policies_explicit",
                "readonly_authorization_blockers_carried_forward",
                "readonly_authorization_not_ready_for_real_probe",
                "readonly_authorization_no_side_effects",
            ],
        )
        self.assertTrue(all(gate.passed for gate in request.quality_gates))

    def test_payload_has_no_side_effects(self) -> None:
        payload = build_environment_probe_readonly_authorization_request().to_dict()

        self.assertFalse(payload["ready_for_real_probe"])
        self.assertFalse(payload["authorization_phrase_present"])
        self.assertEqual(payload["sensitive_action_count"], 7)
        self.assertEqual(len(payload["pending_action_ids"]), 7)
        self.assertEqual(len(payload["pending_approval_item_ids"]), 8)
        self.assertEqual(len(payload["inherited_blocking_finding_ids"]), 15)
        self.assertTrue(all(value is False for value in payload["side_effects"].values()))


if __name__ == "__main__":
    unittest.main()
