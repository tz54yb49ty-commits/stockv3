from __future__ import annotations

import unittest

from ashare_v3.ingestion.environment_probe_plan import REQUIRED_PROBE_ITEM_IDS
from ashare_v3.ingestion.environment_probe_review import (
    REVIEW_REASON_VALUES,
    build_environment_probe_review_report,
)


class EnvironmentProbeReviewReportTest(unittest.TestCase):
    def test_default_review_passes_but_is_not_ready(self) -> None:
        report = build_environment_probe_review_report()

        self.assertTrue(report.passed)
        self.assertFalse(report.ready_for_execution_review)
        self.assertEqual(report.result_status_counts, {"skipped": 14})

    def test_default_review_blocks_probe_plan_and_each_skipped_item(self) -> None:
        report = build_environment_probe_review_report()

        self.assertIn("probe_plan_not_ready", report.blocking_finding_ids)
        self.assertEqual(len(report.blocking_finding_ids), 15)
        self.assertEqual(len(report.blocking_result_item_ids), 15)
        self.assertIn("__probe_plan__", report.blocking_result_item_ids)
        self.assertEqual(
            {
                finding.item_id
                for finding in report.findings
                if finding.reason == "probe_status_skipped"
            },
            set(REQUIRED_PROBE_ITEM_IDS),
        )

    def test_findings_use_declared_reason_domain(self) -> None:
        report = build_environment_probe_review_report()

        self.assertEqual(
            set(finding.reason for finding in report.findings),
            {"probe_plan_not_ready", "probe_status_skipped"},
        )
        for finding in report.findings:
            self.assertIn(finding.reason, REVIEW_REASON_VALUES)
            self.assertTrue(finding.blocking)
            self.assertIn(finding.severity, {"P0", "P1"})
        self.assertEqual(
            [finding.item_id for finding in report.findings if finding.severity == "P1"],
            ["runtime.python_dependencies_available"],
        )

    def test_report_preserves_roots_and_result_record_count(self) -> None:
        report = build_environment_probe_review_report(data_root="/Volumes/MacRaid/database")

        self.assertEqual(report.data_root, "/Volumes/MacRaid/database")
        self.assertEqual(report.tdx_root, "/Volumes/MacRaid/tdxdata/tdx")
        self.assertEqual(len(report.result_records), len(REQUIRED_PROBE_ITEM_IDS))
        self.assertEqual(report.result_report_id, "environment_probe_result_template_n3_7")
        self.assertEqual(report.probe_plan_id, "environment_probe_plan_n3_6")

    def test_quality_gate_names_are_explicit(self) -> None:
        report = build_environment_probe_review_report()

        self.assertEqual(
            [gate.gate_name for gate in report.quality_gates],
            [
                "probe_review_input_result_template_passed",
                "probe_review_required_items_present",
                "probe_review_status_domain_valid",
                "probe_review_failed_skipped_have_error_summary",
                "probe_review_unready_results_are_blocking",
                "probe_review_default_template_not_ready",
                "probe_review_no_real_authorization",
                "probe_review_no_side_effects",
            ],
        )
        self.assertTrue(all(gate.passed for gate in report.quality_gates))

    def test_to_dict_summarizes_blockers_and_side_effects(self) -> None:
        payload = build_environment_probe_review_report().to_dict()

        self.assertFalse(payload["ready_for_execution_review"])
        self.assertEqual(payload["result_status_counts"], {"skipped": 14})
        self.assertEqual(len(payload["blocking_finding_ids"]), 15)
        self.assertEqual(len(payload["findings"]), 15)
        self.assertTrue(all(value is False for value in payload["side_effects"].values()))

    def test_no_probe_execution_or_authorization_flags_are_set(self) -> None:
        report = build_environment_probe_review_report()

        self.assertFalse(report.will_read_environment)
        self.assertFalse(report.will_check_filesystem)
        self.assertFalse(report.will_call_external_sources)
        self.assertFalse(report.will_read_tdx_files)
        self.assertFalse(report.will_connect_database)
        self.assertFalse(report.will_execute_sql)
        self.assertFalse(report.will_create_directories)
        self.assertFalse(report.will_write_data_files)
        self.assertFalse(report.will_start_worker)
        self.assertFalse(report.will_authorize_real_execution)


if __name__ == "__main__":
    unittest.main()
