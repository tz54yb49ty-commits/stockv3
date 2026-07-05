import tempfile
import unittest
import json
import sys
from pathlib import Path

from ashare_v3.runtime.fastlane_contract import (
    load_json_file,
    run_bundle_from_child_command_dicts,
    run_bundle_from_step_dicts,
    validate_fastlane_artifact_schema,
    write_bundle_report_files,
)
import scripts.run_n3_a1_fastlane_bundle_once as n3_runner


class N3A1FastLaneBundleTest(unittest.TestCase):
    def test_n3_a1_bundle_blocks_b1_c1_b2_and_downstream_commands(self) -> None:
        forbidden_commands = [
            "scripts/run_realtime_snapshot_once.py",
            "scripts/run_today_minute_bar_1m_once.py",
            "scripts/run_realtime_projection_metric_once.py",
            "scripts/run_n4_20260605_v4_corrected_execute_once.py",
            "scripts/run_action_consumer_once.py",
            "scripts/run_n6_projection_once.py",
        ]

        for command_path in forbidden_commands:
            with self.subTest(command_path=command_path):
                report = run_bundle_from_step_dicts(
                    bundle_kind="n3_a1",
                    for_trade_date="20260609",
                    step_dicts=[
                        {
                            "step_id": "forbidden",
                            "layer_role": "N3_market_data",
                            "command": ["python3", command_path, "--execute", "--user-confirmed"],
                            "is_execute_step": True,
                            "status": "passed",
                        }
                    ],
                )
                self.assertEqual(report["status"], "blocked")
                self.assertTrue(any("forbidden_command" in blocker for blocker in report["blockers"]))

    def test_sub_step_failure_stops_bundle_before_later_report_paths(self) -> None:
        report = run_bundle_from_step_dicts(
            bundle_kind="n3_a1",
            for_trade_date="20260609",
            step_dicts=[
                {
                    "step_id": "subscription",
                    "layer_role": "N3_market_data",
                    "command": [
                        "python3",
                        "scripts/run_market_data_subscription_execute.py",
                        "--execute",
                        "--user-confirmed",
                    ],
                    "is_execute_step": True,
                    "status": "failed",
                    "sub_report_paths": ["docs/N3_subscription_failed.json"],
                },
                {
                    "step_id": "a1_preload",
                    "layer_role": "N3_market_data",
                    "command": [
                        "python3",
                        "scripts/run_previous_day_minute_preload_execute.py",
                        "--execute",
                        "--user-confirmed",
                    ],
                    "is_execute_step": True,
                    "status": "passed",
                    "sub_report_paths": ["docs/N3_A1_should_not_run.json"],
                },
            ],
        )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["sub_report_paths"], ["docs/N3_subscription_failed.json"])
        self.assertTrue(any("sub_step_failed" in blocker for blocker in report["blockers"]))

    def test_n3_a1_report_json_schema_round_trip(self) -> None:
        report = run_bundle_from_step_dicts(
            bundle_kind="n3_a1",
            for_trade_date="20260609",
            step_dicts=[
                {
                    "step_id": "a1_preload",
                    "layer_role": "N3_market_data",
                    "command": [
                        "python3",
                        "scripts/run_previous_day_minute_preload_execute.py",
                        "--execute",
                        "--user-confirmed",
                    ],
                    "is_execute_step": True,
                    "status": "passed",
                    "sub_report_paths": ["docs/N3_A1.json"],
                    "quality_summary": {"P0": 0, "P1": 0, "P2": 0},
                }
            ],
        )

        self.assertTrue(validate_fastlane_artifact_schema("n3_a1_bundle_report", report))
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "report.json"
            md_path = Path(tmp) / "report.md"
            write_bundle_report_files(report, json_report_path=json_path, markdown_report_path=md_path)
            self.assertEqual(load_json_file(json_path)["status"], "passed")
            self.assertIn("n3_a1", md_path.read_text(encoding="utf-8"))

    def test_n3_a1_real_orchestration_executes_same_layer_a1_child(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            child_report = Path(tmp) / "n3_a1_child.json"
            report = run_bundle_from_child_command_dicts(
                bundle_kind="n3_a1",
                for_trade_date="20260609",
                command_dicts=[
                    {
                        "step_id": "a1_preload",
                        "layer_role": "N3_market_data",
                        "command": [
                            sys.executable,
                            "-c",
                            "from pathlib import Path; import json, sys; "
                            "Path(sys.argv[1]).write_text(json.dumps({'result':'EXECUTE_PASS','quality':{'p0_count':0,'p1_count':0,'p2_count':0}}), encoding='utf-8')",
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
            self.assertEqual(report["sub_steps"][0]["command_result"]["returncode"], 0)

    def test_n3_a1_cli_runs_child_command_json_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            child_report = Path(tmp) / "child.json"
            json_path = Path(tmp) / "bundle.json"
            md_path = Path(tmp) / "bundle.md"
            child_step = {
                "step_id": "a1_preload",
                "layer_role": "N3_market_data",
                "command": [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; import json, sys; "
                    "Path(sys.argv[1]).write_text(json.dumps({'result':'EXECUTE_PASS','quality_summary':{'P0':0,'P1':0,'P2':0}}), encoding='utf-8')",
                    str(child_report),
                    "--execute",
                    "--user-confirmed",
                ],
                "is_execute_step": True,
                "sub_report_paths": [str(child_report)],
            }

            rc = n3_runner.main(
                [
                    "--for-trade-date",
                    "20260609",
                    "--json-report-path",
                    str(json_path),
                    "--markdown-report-path",
                    str(md_path),
                    "--child-command-json",
                    json.dumps(child_step),
                    "--orchestrate-child-commands",
                    "--execute",
                    "--user-confirmed",
                ]
            )

            self.assertEqual(rc, 0)
            self.assertEqual(load_json_file(json_path)["status"], "passed")
            self.assertTrue(child_report.exists())
            self.assertTrue(md_path.exists())


if __name__ == "__main__":
    unittest.main()
