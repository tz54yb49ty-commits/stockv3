import unittest
import sys
import tempfile
from pathlib import Path

from ashare_v3.runtime.fastlane_contract import run_bundle_from_child_command_dicts, run_bundle_from_step_dicts


class N2FastLaneBundleTest(unittest.TestCase):
    def test_n2_bundle_blocks_n3_command_and_market_data_pull(self) -> None:
        report = run_bundle_from_step_dicts(
            bundle_kind="n2",
            for_trade_date="20260609",
            step_dicts=[
                {
                    "step_id": "bad_market_data",
                    "layer_role": "N3_market_data",
                    "command": [
                        "python3",
                        "scripts/run_market_data_subscription_execute.py",
                        "--execute",
                        "--user-confirmed",
                    ],
                    "is_execute_step": True,
                    "status": "passed",
                }
            ],
        )

        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any("cross_layer" in blocker or "forbidden" in blocker for blocker in report["blockers"]))

    def test_n2_bundle_blocks_missing_confirmation_and_p0(self) -> None:
        missing_flags = run_bundle_from_step_dicts(
            bundle_kind="n2",
            for_trade_date="20260609",
            step_dicts=[
                {
                    "step_id": "condition_execute",
                    "layer_role": "N2_condition",
                    "command": ["python3", "scripts/run_condition_once.py", "--execute"],
                    "is_execute_step": True,
                    "status": "passed",
                }
            ],
        )
        self.assertEqual(missing_flags["status"], "blocked")
        self.assertTrue(any("missing_user_confirmed" in blocker for blocker in missing_flags["blockers"]))

        p0_report = run_bundle_from_step_dicts(
            bundle_kind="n2",
            for_trade_date="20260609",
            step_dicts=[
                {
                    "step_id": "condition_preflight",
                    "layer_role": "N2_condition",
                    "command": ["python3", "scripts/plan_condition_execute_preflight.py"],
                    "is_execute_step": False,
                    "status": "passed",
                    "quality_summary": {"P0": 1, "P1": 0, "P2": 0},
                }
            ],
        )
        self.assertEqual(p0_report["status"], "blocked")
        self.assertTrue(any("p0_nonzero" in blocker for blocker in p0_report["blockers"]))

    def test_n2_bundle_blocks_unexpected_event_delta(self) -> None:
        report = run_bundle_from_step_dicts(
            bundle_kind="n2",
            for_trade_date="20260609",
            step_dicts=[
                {
                    "step_id": "condition_execute",
                    "layer_role": "N2_condition",
                    "command": [
                        "python3",
                        "scripts/run_condition_once.py",
                        "--execute",
                        "--user-confirmed",
                    ],
                    "is_execute_step": True,
                    "status": "passed",
                    "event_counts_before": {"outbox": 0, "inbox": 0, "checkpoint": 0},
                    "event_counts_after": {"outbox": 1, "inbox": 0, "checkpoint": 0},
                    "allowed_event_delta": {"outbox": 0, "inbox": 0, "checkpoint": 0},
                }
            ],
        )

        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any("unexpected_event_delta" in blocker for blocker in report["blockers"]))

    def test_n2_real_orchestration_executes_same_layer_condition_child(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            child_report = Path(tmp) / "n2_child.json"
            report = run_bundle_from_child_command_dicts(
                bundle_kind="n2",
                for_trade_date="20260609",
                command_dicts=[
                    {
                        "step_id": "condition_execute",
                        "layer_role": "N2_condition",
                        "command": [
                            sys.executable,
                            "-c",
                            "from pathlib import Path; import json, sys; "
                            "Path(sys.argv[1]).write_text(json.dumps({'result':'EXECUTE_PASS','p0_p1_p2':{'P0':0,'P1':0,'P2':0}}), encoding='utf-8')",
                            str(child_report),
                            "--execute",
                            "--user-confirmed",
                        ],
                        "is_execute_step": True,
                        "sub_report_paths": [str(child_report)],
                    }
                ],
                wrapper_execute=True,
                wrapper_user_confirmed=True,
                orchestrate_child_commands=True,
            )

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["orchestration"]["executed_child_command_count"], 1)
            self.assertEqual(report["quality_summary"], {"P0": 0, "P1": 0, "P2": 0})


if __name__ == "__main__":
    unittest.main()
