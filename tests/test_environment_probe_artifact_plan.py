from __future__ import annotations

import unittest

from ashare_v3.ingestion.environment_probe_artifact_plan import (
    FORBIDDEN_PERSISTED_FIELDS,
    PROBE_RESULT_REQUIRED_FIELDS,
    REQUIRED_ARTIFACT_KINDS,
    RESULT_ARTIFACT_REQUIRED_FIELDS,
    build_environment_probe_artifact_plan,
)
from ashare_v3.ingestion.environment_probe_plan import REQUIRED_PROBE_ITEM_IDS


class EnvironmentProbeArtifactPlanTest(unittest.TestCase):
    def test_artifact_plan_passes_but_is_not_ready_to_write(self) -> None:
        plan = build_environment_probe_artifact_plan()

        self.assertTrue(plan.passed)
        self.assertFalse(plan.ready_to_write)
        self.assertTrue(plan.input_runbook_passed)
        self.assertFalse(plan.input_runbook_ready_to_run)
        self.assertFalse(plan.will_write_data_files)

    def test_artifact_files_are_complete_and_under_audit_root(self) -> None:
        plan = build_environment_probe_artifact_plan()

        self.assertEqual(plan.artifact_kinds, REQUIRED_ARTIFACT_KINDS)
        self.assertEqual(len(plan.artifact_files), 4)
        self.assertEqual(plan.audit_root, "/Volumes/MacRaid/database/audit/environment_probe")
        for path in plan.planned_paths:
            self.assertTrue(path.startswith("/Volumes/MacRaid/database/audit/environment_probe/"))
            self.assertIn("probe_run_id=env_probe_YYYYMMDDThhmmssZ_vN", path)

    def test_result_schema_and_probe_result_schema_are_explicit(self) -> None:
        plan = build_environment_probe_artifact_plan()

        self.assertEqual(plan.result_artifact_required_fields, RESULT_ARTIFACT_REQUIRED_FIELDS)
        self.assertEqual(plan.probe_result_required_fields, PROBE_RESULT_REQUIRED_FIELDS)
        self.assertIn("probe_results", plan.result_artifact_required_fields)
        self.assertIn("evidence", plan.probe_result_required_fields)
        self.assertIn("blocking_result_item_ids", plan.result_artifact_required_fields)

    def test_forbidden_persisted_fields_block_secrets_and_payloads(self) -> None:
        plan = build_environment_probe_artifact_plan()

        self.assertEqual(plan.forbidden_persisted_fields, FORBIDDEN_PERSISTED_FIELDS)
        self.assertIn("tushare_token_value", plan.forbidden_persisted_fields)
        self.assertIn("postgres_dsn_value", plan.forbidden_persisted_fields)
        self.assertIn("tdx_file_content", plan.forbidden_persisted_fields)
        self.assertIn("external_api_payload", plan.forbidden_persisted_fields)
        self.assertIn("market_data_payload", plan.forbidden_persisted_fields)

    def test_artifact_files_require_redaction_and_delete_by_probe_run_id(self) -> None:
        plan = build_environment_probe_artifact_plan()

        for file_plan in plan.artifact_files:
            self.assertEqual(file_plan.file_format, "json")
            self.assertTrue(file_plan.redaction_required)
            self.assertEqual(file_plan.deletion_strategy, "delete_probe_run_directory_by_probe_run_id")
            self.assertEqual(file_plan.forbidden_fields, FORBIDDEN_PERSISTED_FIELDS)

    def test_artifact_plan_inherits_runbook_scope_and_blockers(self) -> None:
        plan = build_environment_probe_artifact_plan()

        self.assertEqual(len(plan.inherited_step_ids), len(REQUIRED_PROBE_ITEM_IDS))
        self.assertEqual(len(plan.inherited_blocking_finding_ids), 15)
        self.assertIn("probe_plan_not_ready", plan.inherited_blocking_finding_ids)
        self.assertIn("__probe_plan__", plan.inherited_blocking_result_item_ids)

    def test_quality_gate_names_are_explicit(self) -> None:
        plan = build_environment_probe_artifact_plan()

        self.assertEqual(
            [gate.gate_name for gate in plan.quality_gates],
            [
                "probe_artifact_plan_runbook_passed_but_not_ready",
                "probe_artifact_plan_kinds_complete",
                "probe_artifact_plan_paths_under_audit_root",
                "probe_artifact_plan_result_schema_complete",
                "probe_artifact_plan_forbidden_fields_explicit",
                "probe_artifact_plan_redaction_and_deletion_explicit",
                "probe_artifact_plan_inherits_runbook_scope",
                "probe_artifact_plan_not_ready_to_write",
                "probe_artifact_plan_no_side_effects",
            ],
        )
        self.assertTrue(all(gate.passed for gate in plan.quality_gates))

    def test_payload_has_no_side_effects(self) -> None:
        payload = build_environment_probe_artifact_plan().to_dict()

        self.assertFalse(payload["ready_to_write"])
        self.assertEqual(payload["artifact_count"], 4)
        self.assertEqual(len(payload["inherited_step_ids"]), 14)
        self.assertEqual(len(payload["inherited_blocking_finding_ids"]), 15)
        self.assertTrue(all(value is False for value in payload["side_effects"].values()))


if __name__ == "__main__":
    unittest.main()
