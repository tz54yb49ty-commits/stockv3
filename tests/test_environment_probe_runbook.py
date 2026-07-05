from __future__ import annotations

import unittest

from ashare_v3.ingestion.environment_probe_application import REQUIRED_PROBE_OPERATOR_APPROVALS
from ashare_v3.ingestion.environment_probe_plan import REQUIRED_PROBE_ITEM_IDS
from ashare_v3.ingestion.environment_probe_runbook import RUNBOOK_CATEGORY_ORDER, build_environment_probe_runbook


class EnvironmentProbeRunbookTest(unittest.TestCase):
    def test_runbook_passes_but_is_not_ready_to_run(self) -> None:
        runbook = build_environment_probe_runbook()

        self.assertTrue(runbook.passed)
        self.assertFalse(runbook.ready_to_run)
        self.assertTrue(runbook.input_application_passed)
        self.assertFalse(runbook.input_application_ready_to_probe)

    def test_runbook_has_fourteen_pending_steps(self) -> None:
        runbook = build_environment_probe_runbook()

        self.assertEqual(len(runbook.steps), 14)
        self.assertEqual(set(runbook.step_item_ids), set(REQUIRED_PROBE_ITEM_IDS))
        self.assertEqual(len(runbook.pending_step_ids), 14)
        for order, step in enumerate(runbook.steps, start=1):
            self.assertEqual(step.step_order, order)
            self.assertEqual(step.approval_status, "pending_user_confirmation")
            self.assertFalse(step.will_run)
            self.assertTrue(step.abort_on_failure)

    def test_runbook_category_order_is_stable(self) -> None:
        runbook = build_environment_probe_runbook()

        self.assertEqual(runbook.category_order, RUNBOOK_CATEGORY_ORDER)
        self.assertEqual(runbook.steps[0].item_id, "security.env_tushare_token_present")
        self.assertEqual(runbook.steps[-1].item_id, "safety.no_worker_or_service_start")

    def test_runbook_approval_dependencies_are_declared(self) -> None:
        runbook = build_environment_probe_runbook()

        dependencies = {step.approval_dependency for step in runbook.steps}
        self.assertTrue(dependencies.issubset(set(REQUIRED_PROBE_OPERATOR_APPROVALS)))
        self.assertIn("probe.security_env_metadata", dependencies)
        self.assertIn("probe.database_readonly", dependencies)
        self.assertIn("probe.archive_filesystem_metadata", dependencies)
        self.assertIn("probe.tdx_local_file_metadata", dependencies)
        self.assertIn("probe.source_connectivity", dependencies)
        self.assertIn("probe.runtime_import_checks", dependencies)
        self.assertIn("probe.safety_boundary", dependencies)
        self.assertIn("probe.no_writes_or_workers", dependencies)

    def test_runbook_inherits_pending_approvals_and_blockers(self) -> None:
        runbook = build_environment_probe_runbook()

        self.assertEqual(set(runbook.inherited_pending_approval_item_ids), set(REQUIRED_PROBE_OPERATOR_APPROVALS))
        self.assertEqual(len(runbook.inherited_blocking_finding_ids), 15)
        self.assertIn("probe_plan_not_ready", runbook.inherited_blocking_finding_ids)
        self.assertIn("__probe_plan__", runbook.inherited_blocking_result_item_ids)

    def test_runbook_steps_have_cleanup_policies(self) -> None:
        runbook = build_environment_probe_runbook()
        cleanup_by_category = {step.category: step.cleanup_policy for step in runbook.steps}

        self.assertEqual(cleanup_by_category["security"], "no_secret_values_captured")
        self.assertEqual(cleanup_by_category["database"], "close_probe_connection_without_writes")
        self.assertEqual(cleanup_by_category["archive"], "no_files_or_directories_created")
        self.assertEqual(cleanup_by_category["tdx"], "no_file_content_captured")
        self.assertEqual(cleanup_by_category["source"], "discard_connectivity_response_payload")
        self.assertEqual(cleanup_by_category["runtime"], "no_runtime_state_persisted")
        self.assertEqual(cleanup_by_category["safety"], "no_services_or_workers_started")

    def test_quality_gate_names_are_explicit(self) -> None:
        runbook = build_environment_probe_runbook()

        self.assertEqual(
            [gate.gate_name for gate in runbook.quality_gates],
            [
                "probe_runbook_application_passed_but_not_ready",
                "probe_runbook_steps_cover_required_items",
                "probe_runbook_category_order_valid",
                "probe_runbook_steps_pending_and_disabled",
                "probe_runbook_approval_dependencies_valid",
                "probe_runbook_abort_and_cleanup_explicit",
                "probe_runbook_inherits_application_blockers",
                "probe_runbook_not_ready_to_run",
                "probe_runbook_no_side_effects",
            ],
        )
        self.assertTrue(all(gate.passed for gate in runbook.quality_gates))

    def test_payload_has_no_side_effects(self) -> None:
        payload = build_environment_probe_runbook().to_dict()

        self.assertFalse(payload["ready_to_run"])
        self.assertEqual(payload["step_count"], 14)
        self.assertEqual(len(payload["pending_step_ids"]), 14)
        self.assertEqual(len(payload["inherited_pending_approval_item_ids"]), 8)
        self.assertTrue(all(value is False for value in payload["side_effects"].values()))


if __name__ == "__main__":
    unittest.main()
