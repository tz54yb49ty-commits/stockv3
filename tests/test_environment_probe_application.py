from __future__ import annotations

import unittest

from ashare_v3.ingestion.environment_probe_application import (
    REQUIRED_PROBE_OPERATOR_APPROVALS,
    build_environment_probe_application_package,
)
from ashare_v3.ingestion.environment_probe_plan import REQUIRED_PROBE_CATEGORIES, REQUIRED_PROBE_ITEM_IDS


class EnvironmentProbeApplicationPackageTest(unittest.TestCase):
    def test_application_passes_but_is_not_ready_to_probe(self) -> None:
        package = build_environment_probe_application_package()

        self.assertTrue(package.passed)
        self.assertFalse(package.ready_to_probe)
        self.assertTrue(package.input_review_passed)
        self.assertFalse(package.input_review_ready_for_execution_review)
        self.assertFalse(package.will_authorize_real_execution)

    def test_probe_requests_cover_all_required_items_and_stay_pending(self) -> None:
        package = build_environment_probe_application_package()

        self.assertEqual(set(package.probe_request_item_ids), set(REQUIRED_PROBE_ITEM_IDS))
        self.assertEqual(len(package.probe_requests), 14)
        self.assertEqual(len(package.pending_probe_request_ids), 14)
        for request in package.probe_requests:
            self.assertEqual(request.approval_status, "pending_user_confirmation")
            self.assertFalse(request.will_run)
            self.assertEqual(request.expected_result_status_values, ("passed", "failed", "skipped"))

    def test_probe_requests_cover_required_categories(self) -> None:
        package = build_environment_probe_application_package()

        self.assertEqual(set(package.category_counts), set(REQUIRED_PROBE_CATEGORIES))
        self.assertEqual(package.category_counts["security"], 2)
        self.assertEqual(package.category_counts["database"], 2)
        self.assertEqual(package.category_counts["archive"], 3)
        self.assertEqual(package.category_counts["tdx"], 2)
        self.assertEqual(package.category_counts["source"], 2)
        self.assertEqual(package.category_counts["runtime"], 1)
        self.assertEqual(package.category_counts["safety"], 2)

    def test_redaction_and_evidence_policies_are_specific(self) -> None:
        package = build_environment_probe_application_package()
        requests = {request.item_id: request for request in package.probe_requests}

        self.assertEqual(
            requests["security.env_tushare_token_present"].redaction_policy,
            "env_var_name_only_secret_value_never_logged",
        )
        self.assertEqual(
            requests["database.postgresql_connectivity"].redaction_policy,
            "dsn_env_name_only_dsn_value_never_logged",
        )
        self.assertEqual(
            requests["tdx.board_txt_files_readable"].redaction_policy,
            "path_status_only_no_file_content",
        )
        self.assertEqual(
            requests["source.tushare_reachable"].evidence_policy,
            "connectivity_status_without_response_payload",
        )

    def test_operator_approvals_are_all_pending(self) -> None:
        package = build_environment_probe_application_package()

        self.assertEqual({item.item_id for item in package.operator_approval_items}, set(REQUIRED_PROBE_OPERATOR_APPROVALS))
        self.assertEqual(len(package.pending_approval_item_ids), len(REQUIRED_PROBE_OPERATOR_APPROVALS))
        self.assertTrue(all(item.status == "pending_user_confirmation" for item in package.operator_approval_items))
        self.assertEqual(package.required_env_vars, ("TUSHARE_TOKEN", "ASHARE_V3_POSTGRES_DSN"))
        self.assertEqual(package.data_root, "/Volumes/MacRaid/database")
        self.assertEqual(package.tdx_root, "/Volumes/MacRaid/tdxdata/tdx")

    def test_application_inherits_review_blockers(self) -> None:
        package = build_environment_probe_application_package()

        self.assertIn("probe_plan_not_ready", package.inherited_blocking_finding_ids)
        self.assertEqual(len(package.inherited_blocking_finding_ids), 15)
        self.assertIn("__probe_plan__", package.inherited_blocking_result_item_ids)
        self.assertEqual(len(package.inherited_blocking_result_item_ids), 15)

    def test_quality_gate_names_are_explicit(self) -> None:
        package = build_environment_probe_application_package()

        self.assertEqual(
            [gate.gate_name for gate in package.quality_gates],
            [
                "probe_application_review_passed_but_not_ready",
                "probe_application_requests_cover_required_items",
                "probe_application_categories_cover_required",
                "probe_application_requests_pending_and_disabled",
                "probe_application_operator_approvals_pending",
                "probe_application_inherits_review_blockers",
                "probe_application_redaction_policy_present",
                "probe_application_not_ready_to_probe",
                "probe_application_no_side_effects",
            ],
        )
        self.assertTrue(all(gate.passed for gate in package.quality_gates))

    def test_payload_has_no_side_effects(self) -> None:
        payload = build_environment_probe_application_package().to_dict()

        self.assertFalse(payload["ready_to_probe"])
        self.assertEqual(payload["probe_request_count"], 14)
        self.assertEqual(len(payload["pending_probe_request_ids"]), 14)
        self.assertEqual(len(payload["pending_approval_item_ids"]), 8)
        self.assertTrue(all(value is False for value in payload["side_effects"].values()))


if __name__ == "__main__":
    unittest.main()
