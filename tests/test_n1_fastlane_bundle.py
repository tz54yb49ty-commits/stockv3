import tempfile
import unittest
import sys
from pathlib import Path

from ashare_v3.runtime.fastlane_contract import (
    load_json_file,
    run_bundle_from_child_command_dicts,
    run_bundle_from_step_dicts,
)

import scripts.run_n1_fastlane_bundle_once as n1_runner


class N1FastLaneBundleTest(unittest.TestCase):
    def test_n1_bundle_preserves_original_report_paths(self) -> None:
        report = run_bundle_from_step_dicts(
            bundle_kind="n1",
            for_trade_date="20260609",
            step_dicts=[
                {
                    "step_id": "official_daily",
                    "layer_role": "N1_ingestion",
                    "command": [
                        "python3",
                        "scripts/run_official_daily_ingestion_20260605_once.py",
                        "--execute",
                        "--user-confirmed",
                        "--postgres-commit-enabled",
                    ],
                    "is_execute_step": True,
                    "status": "passed",
                    "sub_report_paths": ["docs/N1_official_daily_execute_report.json"],
                    "quality_summary": {"P0": 0, "P1": 0, "P2": 0},
                }
            ],
        )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["sub_report_paths"], ["docs/N1_official_daily_execute_report.json"])
        self.assertFalse(report["side_effect_flags"]["worker_started"])

    def test_n1_bundle_blocks_n2_or_n3_child_commands(self) -> None:
        report = run_bundle_from_step_dicts(
            bundle_kind="n1",
            for_trade_date="20260609",
            step_dicts=[
                {
                    "step_id": "bad_n2",
                    "layer_role": "N2_condition",
                    "command": [
                        "python3",
                        "scripts/run_condition_layer_once.py",
                        "--execute",
                        "--user-confirmed",
                    ],
                    "is_execute_step": True,
                    "status": "passed",
                }
            ],
        )

        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any("cross_layer" in blocker for blocker in report["blockers"]))

    def test_n1_runner_writes_mock_report_without_running_business_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "n1_report.json"
            md_path = Path(tmp) / "n1_report.md"
            rc = n1_runner.main(
                [
                    "--for-trade-date",
                    "20260609",
                    "--json-report-path",
                    str(json_path),
                    "--markdown-report-path",
                    str(md_path),
                    "--child-step-json",
                    '{"step_id":"calendar","layer_role":"N1_ingestion","command":["python3","scripts/run_calendar_once.py","--execute","--user-confirmed"],"is_execute_step":true,"status":"passed","sub_report_paths":["docs/calendar.json"],"quality_summary":{"P0":0,"P1":0,"P2":0}}',
                    "--execute",
                    "--user-confirmed",
                ]
            )

            self.assertEqual(rc, 0)
            written = load_json_file(json_path)
            self.assertEqual(written["status"], "passed")
            self.assertEqual(written["sub_report_paths"], ["docs/calendar.json"])
            self.assertTrue(md_path.exists())

    def test_real_orchestration_executes_same_layer_child_and_preserves_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            child_report = Path(tmp) / "child.json"
            report = run_bundle_from_child_command_dicts(
                bundle_kind="n1",
                for_trade_date="20260609",
                command_dicts=[
                    {
                        "step_id": "n1_source_facts",
                        "layer_role": "N1_ingestion",
                        "command": [
                            sys.executable,
                            "-c",
                            "from pathlib import Path; import json, sys; "
                            "Path(sys.argv[1]).write_text(json.dumps({'result':'EXECUTE_PASS','quality_summary':{'P0':0,'P1':0,'P2':0}}), encoding='utf-8')",
                            str(child_report),
                            "--execute",
                            "--user-confirmed",
                            "--postgres-commit-enabled",
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
            self.assertEqual(report["sub_report_paths"], [str(child_report)])
            self.assertTrue(child_report.exists())
            self.assertEqual(report["sub_steps"][0]["command_result"]["returncode"], 0)
            self.assertEqual(report["orchestration"]["executed_child_command_count"], 1)

    def test_real_orchestration_requires_explicit_wrapper_opt_in_before_running_child(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            child_report = Path(tmp) / "should_not_exist.json"
            report = run_bundle_from_child_command_dicts(
                bundle_kind="n1",
                for_trade_date="20260609",
                command_dicts=[
                    {
                        "step_id": "n1_source_facts",
                        "layer_role": "N1_ingestion",
                        "command": [
                            sys.executable,
                            "-c",
                            "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('ran', encoding='utf-8')",
                            str(child_report),
                            "--execute",
                            "--user-confirmed",
                            "--postgres-commit-enabled",
                        ],
                        "is_execute_step": True,
                    }
                ],
                wrapper_execute=True,
                wrapper_user_confirmed=True,
                orchestrate_child_commands=False,
            )

            self.assertEqual(report["status"], "blocked")
            self.assertFalse(child_report.exists())
            self.assertTrue(any("wrapper_missing_orchestrate_child_commands" in blocker for blocker in report["blockers"]))

    def test_n1_real_orchestration_blocks_missing_postgres_commit_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            child_report = Path(tmp) / "should_not_exist.json"
            report = run_bundle_from_child_command_dicts(
                bundle_kind="n1",
                for_trade_date="20260609",
                command_dicts=[
                    {
                        "step_id": "source_facts",
                        "layer_role": "N1_ingestion",
                        "command": [
                            sys.executable,
                            "scripts/run_n1_source_facts_once.py",
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

            self.assertEqual(report["status"], "blocked")
            self.assertFalse(child_report.exists())
            self.assertTrue(any("missing_postgres_commit_enabled" in blocker for blocker in report["blockers"]))

    def test_real_orchestration_stops_after_child_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            should_not_run = Path(tmp) / "second.json"
            report = run_bundle_from_child_command_dicts(
                bundle_kind="n1",
                for_trade_date="20260609",
                command_dicts=[
                    {
                        "step_id": "fails",
                        "layer_role": "N1_ingestion",
                        "command": [sys.executable, "-c", "raise SystemExit(7)", "--execute", "--user-confirmed"],
                        "is_execute_step": True,
                    },
                    {
                        "step_id": "second",
                        "layer_role": "N1_ingestion",
                        "command": [
                            sys.executable,
                            "-c",
                            "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('ran', encoding='utf-8')",
                            str(should_not_run),
                            "--execute",
                            "--user-confirmed",
                        ],
                        "is_execute_step": True,
                    },
                ],
                wrapper_execute=True,
                wrapper_user_confirmed=True,
                orchestrate_child_commands=True,
            )

            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["sub_steps"][0]["command_result"]["returncode"], 7)
            self.assertEqual(len(report["sub_steps"]), 1)
            self.assertFalse(should_not_run.exists())


if __name__ == "__main__":
    unittest.main()
