from pathlib import Path
import unittest

from ashare_v3.runtime.fastlane_contract import (
    BUNDLE_SPECS,
    SideEffectFlags,
    build_fastlane_artifact_paths,
    validate_fastlane_artifact_schema,
)


class FastLaneContractTest(unittest.TestCase):
    def test_artifact_path_builder_uses_fastlane_trade_date_directory(self) -> None:
        paths = build_fastlane_artifact_paths(for_trade_date="20260609", docs_root=Path("docs"))

        self.assertEqual(
            paths["runtime_readiness_json"],
            Path("docs/fastlane/20260609/01_runtime_readiness.json"),
        )
        self.assertEqual(
            paths["n3_a1_bundle_report_md"],
            Path("docs/fastlane/20260609/04_n3_a1_bundle_execute_report.md"),
        )
        self.assertEqual(
            paths["closeout_registration_json"],
            Path("docs/fastlane/20260609/05_closeout_registration.json"),
        )

    def test_bundle_specs_lock_layer_roles_and_report_names(self) -> None:
        self.assertEqual(BUNDLE_SPECS["n1"].layer_role, "N1_ingestion")
        self.assertEqual(BUNDLE_SPECS["n2"].layer_role, "N2_condition")
        self.assertEqual(BUNDLE_SPECS["n3_a1"].layer_role, "N3_market_data")
        self.assertEqual(BUNDLE_SPECS["n1"].report_json_name, "02_n1_bundle_execute_report.json")
        self.assertEqual(BUNDLE_SPECS["n2"].report_json_name, "03_n2_bundle_execute_report.json")
        self.assertEqual(BUNDLE_SPECS["n3_a1"].report_json_name, "04_n3_a1_bundle_execute_report.json")

    def test_side_effect_flags_default_to_forbidden_scope_false(self) -> None:
        flags = SideEffectFlags().to_dict()

        self.assertTrue(flags)
        self.assertTrue(all(value is False for value in flags.values()))
        self.assertIn("database_written", flags)
        self.assertIn("worker_started", flags)
        self.assertIn("old_system_touched", flags)

    def test_bundle_report_schema_requires_sub_reports_and_side_effect_flags(self) -> None:
        valid = {
            "bundle_run_id": "n1_fastlane_20260609",
            "layer_role": "N1_ingestion",
            "status": "passed",
            "sub_steps": [],
            "sub_report_paths": ["docs/N1_report.json"],
            "quality_summary": {"P0": 0, "P1": 0, "P2": 0},
            "rollback_paths": ["sql/N1_rollback.sql"],
            "side_effect_flags": SideEffectFlags().to_dict(),
            "blockers": [],
            "next_gate": "N2_CONDITION_FAST_LANE_BUNDLE_EXECUTE_GATE",
        }

        self.assertTrue(validate_fastlane_artifact_schema("n1_bundle_report", valid))

        invalid = dict(valid)
        invalid.pop("sub_report_paths")
        with self.assertRaises(ValueError):
            validate_fastlane_artifact_schema("n1_bundle_report", invalid)


if __name__ == "__main__":
    unittest.main()
