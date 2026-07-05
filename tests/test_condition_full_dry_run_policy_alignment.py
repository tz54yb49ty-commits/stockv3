import inspect
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from scripts import plan_condition_full_dry_run as full_dry_run


class ConditionFullDryRunPolicyAlignmentTest(unittest.TestCase):
    def test_full_dry_run_resolves_8782_policy_like_execute_runner(self) -> None:
        policy_path = ROOT / "configs/n2_policy/default_policy_draft.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        bundle = full_dry_run.resolve_full_dry_run_policy(policy_path)

        self.assertEqual(bundle.policy_source, "8782_console")
        self.assertEqual(bundle.policy_id, "n2_default_policy")
        self.assertEqual(bundle.policy_version, policy["policy_version"])
        self.assertEqual(bundle.policy_hash, policy["policy_hash"])
        self.assertEqual(
            bundle.condition_pool_policy["index"]["include_identity_keys"],
            policy["web_policy"]["index"]["enabled_identities"],
        )
        self.assertEqual(
            bundle.condition_pool_policy["board"]["board_types"],
            policy["web_policy"]["board"]["board_types"],
        )

    def test_full_dry_run_passes_condition_pool_policy_to_pool_and_scope(self) -> None:
        source = inspect.getsource(full_dry_run.main)

        self.assertIn("condition_pool_policy=condition_pool_policy", source)
        self.assertIn("scope_policy=scope_policy", source)

    def test_full_dry_run_ignores_planned_run_monitor_targets_for_artifact_refresh(self) -> None:
        basis_report = {
            "monitor_targets": {
                "stock": {"active_count": 10, "mode": "monitor_target"},
                "index": {"active_count": 2, "mode": "monitor_target"},
                "board": {"active_count": 3, "mode": "monitor_target"},
            },
            "quality": {
                "p0_count": 0,
                "p1_count": 0,
                "p2_count": 0,
                "items": [],
            },
        }

        full_dry_run.normalize_basis_monitor_target_status_for_planned_run(
            basis_report,
            planned_run_id="condition_layer_20260602_source_20260602_v1",
            planned_run_monitor_counts={"stock": 10, "index": 2, "board": 3},
        )

        self.assertEqual(basis_report["monitor_targets"]["stock"]["active_count"], 0)
        self.assertEqual(basis_report["monitor_targets"]["index"]["active_count"], 0)
        self.assertEqual(basis_report["monitor_targets"]["board"]["active_count"], 0)
        self.assertEqual(basis_report["quality"]["p1_count"], 3)
        self.assertEqual(
            {
                item["gate_code"]
                for item in basis_report["quality"]["items"]
                if item["status"] == "warning"
            },
            {
                "stock_monitor_target_fallback",
                "index_monitor_target_fallback",
                "board_monitor_target_fallback",
            },
        )

    def test_full_dry_run_keeps_external_monitor_targets_available(self) -> None:
        basis_report = {
            "monitor_targets": {
                "stock": {"active_count": 12, "mode": "monitor_target"},
            },
            "quality": {
                "p0_count": 0,
                "p1_count": 0,
                "p2_count": 0,
                "items": [],
            },
        }

        full_dry_run.normalize_basis_monitor_target_status_for_planned_run(
            basis_report,
            planned_run_id="condition_layer_20260602_source_20260602_v1",
            planned_run_monitor_counts={"stock": 10},
        )

        self.assertEqual(basis_report["monitor_targets"]["stock"]["active_count"], 2)
        self.assertEqual(basis_report["monitor_targets"]["stock"]["mode"], "monitor_target")
        self.assertEqual(basis_report["quality"]["p1_count"], 0)

    def test_full_dry_run_display_quality_count_matches_execute_writer(self) -> None:
        domain_report = {
            "row_count": 1,
            "uniqueness": {"duplicate_count": 0},
            "field_integrity": {
                "source_condition_basis_ids_missing": 0,
                "selected_condition_keys_invalid": 0,
                "selected_signal_types_invalid": 0,
                "period_trigger_baseline_invalid_shape": 0,
                "clear_sell_ref_period_mismatch": 0,
                "invalid_reference_period": 0,
            },
            "traceability": {
                "source_minute_target_scope_ids_empty_explained": True,
            },
            "forbidden_field_check": {"forbidden_field_count": 0},
        }
        report = full_dry_run.build_display_quality_for_full_dry_run(
            domain_reports={
                "stock": {"display_table": "stock_condition_display_basis", **domain_report},
                "index": {"display_table": "index_condition_display_basis", **domain_report},
                "board": {"display_table": "board_condition_display_basis", **domain_report},
            },
            before_counts={},
            after_counts={},
        )

        self.assertEqual(len(report["items"]), 28)
        self.assertEqual(report["items"][-1]["gate_code"], "display_rows_written_matches_plan")
        self.assertEqual(report["p0_count"], 0)
        self.assertEqual(report["p1_count"], 0)


if __name__ == "__main__":
    unittest.main()
