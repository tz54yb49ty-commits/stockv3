import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace

from ashare_v3.runtime.post_close_fastlane import (
    _refresh_latest_after_status,
    build_launchd_plist,
    build_oneshot_child_commands,
    n4_context_run_id_for,
    run_post_close_oneshot,
)


class PostCloseFastLaneOneShotTest(unittest.TestCase):
    def test_builds_20260611_to_20260612_child_commands_in_fixed_order(self) -> None:
        commands = build_oneshot_child_commands(
            source_trade_date="20260611",
            for_trade_date="20260612",
            prev_trade_date="20260610",
            next_trade_date="20260615",
            dsn="postgresql://example/db",
            docs_root=Path("docs/post_close_fastlane"),
            sql_root=Path("sql"),
            include_calendar_repair=True,
        )

        self.assertEqual(
            [command.step_id for command in commands],
            [
                "calendar_repair",
                "n1_source_facts",
                "n1_stock_financial_canonical_source_bundle",
                "n1_stock_financial_canonical_metrics",
                "n2_condition",
                "n3_subscription",
                "n3_a0_preload_dry_run",
                "n3_a1_contract",
                "n3_a1_preload",
                "n3_a1_cumulative_amount",
                "n4_trigger_context_snapshot",
                "n4_context_rollback_ready",
                "preopen_readiness_noop",
                "lineage_pollution_guard",
                "worker_launchd_guard",
            ],
        )
        self.assertIn("scripts/run_trade_calendar_patch_once.py", commands[0].argv)
        self.assertIn("scripts/run_n1_source_facts_once.py", commands[1].argv)
        self.assertIn("scripts/plan_stock_financial_canonical_source_bundle_once.py", commands[2].argv)
        self.assertIn("--incremental", commands[2].argv)
        self.assertIn("--previous-snapshot-path", commands[2].argv)
        self.assertIn("docs/post_close_fastlane/20260611/21_n1_stock_financial_canonical_snapshot_v1.json", commands[2].argv)
        self.assertIn("--snapshot-cache-path", commands[2].argv)
        self.assertIn("docs/post_close_fastlane/20260612/21_n1_stock_financial_canonical_snapshot_v1.json", commands[2].argv)
        self.assertNotIn("--full-fetch-confirmed", commands[2].argv)
        self.assertIn("scripts/run_stock_financial_canonical_metrics_once.py", commands[3].argv)
        self.assertIn("docs/post_close_fastlane/20260612/21_n1_stock_financial_canonical_snapshot_v1.json", commands[3].argv)
        self.assertIn("--source-trade-date", commands[3].argv)
        self.assertIn("20260611", commands[3].argv)
        self.assertIn("stock_financial_20260611_v2", " ".join(commands[3].argv))
        self.assertIn("scripts/run_condition_layer_execute.py", commands[4].argv)
        self.assertIn("scripts/run_market_data_subscription_execute.py", commands[5].argv)
        self.assertIn("scripts/plan_previous_day_minute_preload.py", commands[6].argv)
        self.assertIn("scripts/plan_previous_day_minute_execute_contract.py", commands[7].argv)
        self.assertIn("scripts/run_previous_day_minute_preload_execute.py", commands[8].argv)
        self.assertIn("scripts/run_previous_day_cumulative_amount_execute.py", commands[9].argv)
        self.assertIn("--source-previous-day-minute-run-id", commands[9].argv)
        self.assertIn(
            "previous_day_minute_preload_20260611_for_20260612__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
            commands[9].argv,
        )
        self.assertIn(
            "docs/post_close_fastlane/20260612/51_n3_a1_cumulative_amount_execute_report.json",
            commands[9].report_paths,
        )
        self.assertIn("scripts/run_trigger_context_snapshot_execute.py", commands[10].argv)
        self.assertIn("--condition-run-id", commands[10].argv)
        self.assertIn("condition_layer_20260611_source_20260611_for_20260612_v1", commands[10].argv)
        self.assertIn("docs/post_close_fastlane/20260612/52_n4_trigger_context_snapshot_execute_report.json", commands[10].report_paths)
        self.assertIn("sql/N4_trigger_context_snapshot_20260612_rollback.sql", commands[10].report_paths)
        self.assertIn("scripts/review_post_close_preopen_guards.py", commands[11].argv)
        self.assertIn("--check", commands[11].argv)
        self.assertIn("n4_context_rollback_ready", commands[11].argv)
        self.assertIn("scripts/review_post_close_preopen_guards.py", commands[12].argv)
        self.assertIn("preopen_readiness_noop", commands[12].argv)
        self.assertIn("scripts/review_post_close_preopen_guards.py", commands[13].argv)
        self.assertIn("lineage_pollution_guard", commands[13].argv)
        self.assertIn("scripts/review_post_close_preopen_guards.py", commands[14].argv)
        self.assertIn("worker_launchd_guard", commands[14].argv)
        self.assertIn(
            "sql/N3_A1_previous_day_minute_cumulative_20260611_for_20260612_rollback.sql",
            commands[9].report_paths,
        )
        self.assertTrue(Path("scripts/run_previous_day_cumulative_amount_execute.py").exists())
        forbidden_markers = (
            "n3p",
            "run_n4_provisional_ordinary_execute_once.py",
            "provisional_projection_execute",
            "run_n5",
            "action_consumer",
            "checkpoint",
            "bootstrap",
            "bootout",
        )
        for command in commands:
            command_text = " ".join(command.argv).lower()
            for marker in forbidden_markers:
                self.assertNotIn(marker, command_text)
        for command in [commands[0], commands[1], commands[3], commands[4], commands[5], commands[8], commands[9], commands[10]]:
            self.assertIn("--execute", command.argv)
            self.assertIn("--user-confirmed", command.argv)
        self.assertIn("--postgres-commit-enabled", commands[0].argv)
        self.assertIn("--postgres-commit-enabled", commands[1].argv)
        self.assertIn("--postgres-commit-enabled", commands[3].argv)

    def test_oneshot_stops_after_child_failure_and_writes_report(self) -> None:
        calls = []

        def fake_runner(argv):
            calls.append(argv)
            if "scripts/run_condition_layer_execute.py" in argv:
                return SimpleNamespace(returncode=3, stdout="", stderr="n2 failed")
            return SimpleNamespace(returncode=0, stdout=json.dumps({"result": "EXECUTE_PASS"}), stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            report = run_post_close_oneshot(
                source_trade_date="20260611",
                for_trade_date="20260612",
                prev_trade_date="20260610",
                next_trade_date="20260615",
                dsn="postgresql://example/db",
                docs_root=Path(tmp) / "docs",
                sql_root=Path(tmp) / "sql",
                execute=True,
                user_confirmed=True,
                postgres_commit_enabled=True,
                include_calendar_repair=False,
                command_runner=fake_runner,
            )

            self.assertEqual(report["result"], "PARTIAL_BLOCKED")
            self.assertEqual(report["failed_step_id"], "n2_condition")
            self.assertEqual(len(calls), 4)
            self.assertTrue((Path(tmp) / "docs" / "20260612" / "01_oneshot_execute_report.json").exists())
            self.assertFalse(report["forbidden_scope_proof"]["n4_n5_n6_entered"])

    def test_partial_blocked_refreshes_latest_attempted_pointer_after_status_write(self) -> None:
        calls = []

        def fake_runner(argv):
            calls.append(argv)
            if "scripts/run_condition_layer_execute.py" in argv:
                return SimpleNamespace(returncode=3, stdout="", stderr="n2 failed")
            return SimpleNamespace(returncode=0, stdout=json.dumps({"result": "EXECUTE_PASS"}), stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "docs"
            docs_root.mkdir()
            (docs_root / "20260611").mkdir()
            (docs_root / "latest").symlink_to("20260611")

            report = run_post_close_oneshot(
                source_trade_date="20260611",
                for_trade_date="20260612",
                prev_trade_date="20260610",
                next_trade_date="20260615",
                dsn="postgresql://example/db",
                docs_root=docs_root,
                sql_root=Path(tmp) / "sql",
                execute=True,
                user_confirmed=True,
                postgres_commit_enabled=True,
                include_calendar_repair=False,
                command_runner=fake_runner,
            )

            latest = docs_root / "latest"
            self.assertEqual(report["result"], "PARTIAL_BLOCKED")
            self.assertTrue(latest.is_symlink())
            self.assertEqual(latest.resolve().name, "20260612")
            self.assertFalse((docs_root / "runtime" / "current_intraday_worker_lineage.json").exists())

    def test_execute_pass_writes_intraday_worker_lineage_config_after_status_write(self) -> None:
        def fake_runner(argv):
            return SimpleNamespace(returncode=0, stdout=json.dumps({"result": "EXECUTE_PASS"}), stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "docs" / "post_close_fastlane"
            report = run_post_close_oneshot(
                source_trade_date="20260611",
                for_trade_date="20260612",
                prev_trade_date="20260610",
                next_trade_date="20260615",
                dsn="postgresql://example/db",
                docs_root=docs_root,
                sql_root=Path(tmp) / "sql",
                execute=True,
                user_confirmed=True,
                postgres_commit_enabled=True,
                include_calendar_repair=False,
                command_runner=fake_runner,
            )

            config_path = docs_root.parent / "runtime" / "current_intraday_worker_lineage.json"
            payload = json.loads(config_path.read_text(encoding="utf-8"))

            self.assertEqual(report["result"], "EXECUTE_PASS")
            self.assertTrue(payload["enabled"])
            self.assertEqual(payload["for_trade_date"], "20260612")
            self.assertEqual(payload["source_trade_date"], "20260611")
            self.assertEqual(payload["n2_run_id"], "condition_layer_20260611_source_20260611_for_20260612_v1")
            self.assertEqual(
                payload["subscription_run_id"],
                "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
            )
            self.assertEqual(
                payload["a1_preload_run_id"],
                "previous_day_minute_preload_20260611_for_20260612__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
            )
            self.assertEqual(payload["n4_context_run_id"], n4_context_run_id_for("20260611", "20260612"))
            self.assertEqual(payload["source_status_path"], str(docs_root / "20260612" / "00_status.json"))
            self.assertEqual(payload["source_oneshot_report_path"], str(docs_root / "20260612" / "01_oneshot_execute_report.json"))

    def test_execute_pass_does_not_rewrite_identical_intraday_worker_lineage_config(self) -> None:
        def fake_runner(argv):
            return SimpleNamespace(returncode=0, stdout=json.dumps({"result": "EXECUTE_PASS"}), stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "docs" / "post_close_fastlane"
            config_path = docs_root.parent / "runtime" / "current_intraday_worker_lineage.json"
            config_path.parent.mkdir(parents=True)
            existing_payload = {
                "enabled": True,
                "for_trade_date": "20260612",
                "source_trade_date": "20260611",
                "n2_run_id": "condition_layer_20260611_source_20260611_for_20260612_v1",
                "subscription_run_id": "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
                "a1_preload_run_id": "previous_day_minute_preload_20260611_for_20260612__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
                "n4_context_run_id": n4_context_run_id_for("20260611", "20260612"),
                "updated_by": "runtime_control_explicit_lineage_materialization",
                "updated_at": "2026-06-12T02:06:21+08:00",
                "source_status_path": str(docs_root / "20260612" / "00_status.json"),
                "source_oneshot_report_path": str(docs_root / "20260612" / "01_oneshot_execute_report.json"),
            }
            config_path.write_text(json.dumps(existing_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            report = run_post_close_oneshot(
                source_trade_date="20260611",
                for_trade_date="20260612",
                prev_trade_date="20260610",
                next_trade_date="20260615",
                dsn="postgresql://example/db",
                docs_root=docs_root,
                sql_root=Path(tmp) / "sql",
                execute=True,
                user_confirmed=True,
                postgres_commit_enabled=True,
                include_calendar_repair=False,
                command_runner=fake_runner,
            )

            payload = json.loads(config_path.read_text(encoding="utf-8"))

            self.assertEqual(report["result"], "EXECUTE_PASS")
            self.assertEqual(payload, existing_payload)

    def test_latest_attempted_pointer_not_refreshed_for_malformed_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "docs"
            old_dir = docs_root / "20260611"
            new_dir = docs_root / "20260612"
            old_dir.mkdir(parents=True)
            new_dir.mkdir()
            (docs_root / "latest").symlink_to("20260611")
            (new_dir / "00_status.json").write_text("{invalid", encoding="utf-8")

            refreshed = _refresh_latest_after_status(docs_root, new_dir)

            self.assertFalse(refreshed)
            self.assertEqual((docs_root / "latest").resolve().name, "20260611")

    def test_completed_status_file_returns_noop_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status_path = Path(tmp) / "docs" / "20260612" / "00_status.json"
            status_path.parent.mkdir(parents=True)
            status_path.write_text(json.dumps({"result": "EXECUTE_PASS"}), encoding="utf-8")
            (status_path.parent / "01_oneshot_execute_report.json").write_text(
                json.dumps(
                    {
                        "result": "EXECUTE_PASS",
                        "sub_steps": [
                            {"step_id": "n1_source_facts", "returncode": 0},
                            {"step_id": "n1_stock_financial_canonical_source_bundle", "returncode": 0},
                            {"step_id": "n1_stock_financial_canonical_metrics", "returncode": 0},
                            {"step_id": "n2_condition", "returncode": 0},
                            {"step_id": "n3_subscription", "returncode": 0},
                            {"step_id": "n3_a0_preload_dry_run", "returncode": 0},
                            {"step_id": "n3_a1_contract", "returncode": 0},
                            {"step_id": "n3_a1_preload", "returncode": 0},
                            {"step_id": "n3_a1_cumulative_amount", "returncode": 0},
                            {"step_id": "n4_trigger_context_snapshot", "returncode": 0},
                            {"step_id": "n4_context_rollback_ready", "returncode": 0},
                            {"step_id": "preopen_readiness_noop", "returncode": 0},
                            {"step_id": "lineage_pollution_guard", "returncode": 0},
                            {"step_id": "worker_launchd_guard", "returncode": 0},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = run_post_close_oneshot(
                source_trade_date="20260611",
                for_trade_date="20260612",
                prev_trade_date="20260610",
                next_trade_date="20260615",
                dsn="postgresql://example/db",
                docs_root=Path(tmp) / "docs",
                sql_root=Path(tmp) / "sql",
                execute=True,
                user_confirmed=True,
                postgres_commit_enabled=True,
                command_runner=lambda argv: (_ for _ in ()).throw(AssertionError("must not run")),
            )

            self.assertEqual(report["result"], "NOOP")
            self.assertEqual(report["reason"], "already_execute_pass")

    def test_completed_status_missing_preopen_steps_resumes_only_appended_steps(self) -> None:
        calls = []

        def fake_runner(argv):
            calls.append(argv)
            return SimpleNamespace(returncode=0, stdout=json.dumps({"result": "PASS"}), stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp) / "docs" / "20260612"
            report_dir.mkdir(parents=True)
            (report_dir / "00_status.json").write_text(json.dumps({"result": "EXECUTE_PASS"}), encoding="utf-8")
            (report_dir / "01_oneshot_execute_report.json").write_text(
                json.dumps(
                    {
                        "result": "EXECUTE_PASS",
                        "sub_steps": [
                            {"step_id": "n1_source_facts", "returncode": 0},
                            {"step_id": "n1_stock_financial_canonical_source_bundle", "returncode": 0},
                            {"step_id": "n1_stock_financial_canonical_metrics", "returncode": 0},
                            {"step_id": "n2_condition", "returncode": 0},
                            {"step_id": "n3_subscription", "returncode": 0},
                            {"step_id": "n3_a0_preload_dry_run", "returncode": 0},
                            {"step_id": "n3_a1_contract", "returncode": 0},
                            {"step_id": "n3_a1_preload", "returncode": 0},
                            {"step_id": "n3_a1_cumulative_amount", "returncode": 0},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = run_post_close_oneshot(
                source_trade_date="20260611",
                for_trade_date="20260612",
                prev_trade_date="20260610",
                next_trade_date="20260615",
                dsn="postgresql://example/db",
                docs_root=Path(tmp) / "docs",
                sql_root=Path(tmp) / "sql",
                execute=True,
                user_confirmed=True,
                postgres_commit_enabled=True,
                include_calendar_repair=False,
                command_runner=fake_runner,
            )

            self.assertEqual(report["result"], "EXECUTE_PASS")
            self.assertEqual(len(calls), 5)
            self.assertIn("scripts/run_trigger_context_snapshot_execute.py", calls[0])
            self.assertIn("n4_context_rollback_ready", calls[1])
            self.assertIn("preopen_readiness_noop", calls[2])
            self.assertIn("lineage_pollution_guard", calls[3])
            self.assertIn("worker_launchd_guard", calls[4])
            self.assertEqual(report["sub_steps"][-1]["step_id"], "worker_launchd_guard")
            self.assertEqual(report["sub_steps"][-1]["returncode"], 0)
            self.assertTrue(all(step.get("skipped") for step in report["sub_steps"][:-5]))

    def test_existing_calendar_row_skips_explicit_calendar_repair_on_rerun(self) -> None:
        calls = []

        def fake_runner(argv):
            calls.append(argv)
            return SimpleNamespace(returncode=0, stdout=json.dumps({"result": "EXECUTE_PASS"}), stderr="")

        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "ashare_v3.runtime.post_close_fastlane.calendar_date_exists",
            return_value=True,
        ):
            report = run_post_close_oneshot(
                source_trade_date="20260611",
                for_trade_date="20260612",
                prev_trade_date="20260610",
                next_trade_date="20260615",
                dsn="postgresql://example/db",
                docs_root=Path(tmp) / "docs",
                sql_root=Path(tmp) / "sql",
                execute=True,
                user_confirmed=True,
                postgres_commit_enabled=True,
                include_calendar_repair=True,
                command_runner=fake_runner,
            )

            self.assertEqual(report["result"], "EXECUTE_PASS")
            self.assertFalse(report["calendar_repair"]["will_run"])
            self.assertIn("scripts/run_n1_source_facts_once.py", calls[0])
            self.assertNotIn("scripts/run_trade_calendar_patch_once.py", calls[0])

    def test_force_rerun_after_partial_blocked_skips_previously_successful_steps(self) -> None:
        calls = []

        def fake_runner(argv):
            calls.append(argv)
            return SimpleNamespace(returncode=0, stdout=json.dumps({"result": "EXECUTE_PASS"}), stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "docs" / "20260612" / "01_oneshot_execute_report.json"
            report_path.parent.mkdir(parents=True)
            report_path.write_text(
                json.dumps(
                    {
                        "result": "PARTIAL_BLOCKED",
                        "sub_steps": [
                            {"step_id": "n1_source_facts", "returncode": 0},
                            {"step_id": "n1_stock_financial_canonical_source_bundle", "returncode": 0},
                            {"step_id": "n1_stock_financial_canonical_metrics", "returncode": 0},
                            {"step_id": "n2_condition", "returncode": 0},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = run_post_close_oneshot(
                source_trade_date="20260611",
                for_trade_date="20260612",
                prev_trade_date="20260610",
                next_trade_date="20260615",
                dsn="postgresql://example/db",
                docs_root=Path(tmp) / "docs",
                sql_root=Path(tmp) / "sql",
                execute=True,
                user_confirmed=True,
                postgres_commit_enabled=True,
                include_calendar_repair=False,
                force_rerun_after_blocked=True,
                command_runner=fake_runner,
            )

            self.assertEqual(report["result"], "EXECUTE_PASS")
            self.assertTrue(report["sub_steps"][0]["skipped"])
            self.assertTrue(report["sub_steps"][1]["skipped"])
            self.assertIn("scripts/run_market_data_subscription_execute.py", calls[0])

    def test_force_rerun_skips_failed_source_bundle_when_recovery_preflight_passed(self) -> None:
        calls = []

        def fake_runner(argv):
            calls.append(argv)
            return SimpleNamespace(returncode=0, stdout=json.dumps({"result": "EXECUTE_PASS"}), stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp) / "docs" / "20260612"
            report_dir.mkdir(parents=True)
            (report_dir / "01_oneshot_execute_report.json").write_text(
                json.dumps(
                    {
                        "result": "PARTIAL_BLOCKED",
                        "failed_step_id": "n1_stock_financial_canonical_source_bundle",
                        "sub_steps": [
                            {"step_id": "n1_source_facts", "returncode": 0},
                            {"step_id": "n1_stock_financial_canonical_source_bundle", "returncode": 2},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (report_dir / "21_n1_stock_financial_canonical_source_bundle_preflight.json").write_text(
                json.dumps({"result": "PREFLIGHT_PASS"}),
                encoding="utf-8",
            )

            report = run_post_close_oneshot(
                source_trade_date="20260611",
                for_trade_date="20260612",
                prev_trade_date="20260610",
                next_trade_date="20260615",
                dsn="postgresql://example/db",
                docs_root=Path(tmp) / "docs",
                sql_root=Path(tmp) / "sql",
                execute=True,
                user_confirmed=True,
                postgres_commit_enabled=True,
                include_calendar_repair=False,
                force_rerun_after_blocked=True,
                command_runner=fake_runner,
            )

            self.assertEqual(report["result"], "EXECUTE_PASS")
            skipped_steps = [step["step_id"] for step in report["sub_steps"] if step.get("skipped")]
            self.assertIn("n1_stock_financial_canonical_source_bundle", skipped_steps)
            self.assertIn("scripts/run_stock_financial_canonical_metrics_once.py", calls[0])

    def test_force_rerun_skips_existing_passed_source_facts_artifact_after_report_overwrite(self) -> None:
        calls = []

        def fake_runner(argv):
            calls.append(argv)
            return SimpleNamespace(returncode=0, stdout=json.dumps({"result": "EXECUTE_PASS"}), stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp) / "docs" / "20260612"
            report_dir.mkdir(parents=True)
            (report_dir / "01_oneshot_execute_report.json").write_text(
                json.dumps(
                    {
                        "result": "BLOCKED",
                        "failed_step_id": "n1_source_facts",
                        "sub_steps": [{"step_id": "n1_source_facts", "returncode": 2}],
                    }
                ),
                encoding="utf-8",
            )
            (report_dir / "20_n1_source_facts_execute_report.json").write_text(
                json.dumps({"result": "EXECUTE_PASS"}),
                encoding="utf-8",
            )

            report = run_post_close_oneshot(
                source_trade_date="20260611",
                for_trade_date="20260612",
                prev_trade_date="20260610",
                next_trade_date="20260615",
                dsn="postgresql://example/db",
                docs_root=Path(tmp) / "docs",
                sql_root=Path(tmp) / "sql",
                execute=True,
                user_confirmed=True,
                postgres_commit_enabled=True,
                include_calendar_repair=False,
                force_rerun_after_blocked=True,
                command_runner=fake_runner,
            )

            self.assertEqual(report["result"], "EXECUTE_PASS")
            self.assertEqual(report["sub_steps"][0]["step_id"], "n1_source_facts")
            self.assertTrue(report["sub_steps"][0]["skipped"])
            self.assertIn("scripts/plan_stock_financial_canonical_source_bundle_once.py", calls[0])

    def test_launchd_plist_runs_daily_at_18_without_keepalive(self) -> None:
        plist = build_launchd_plist(
            project_root=Path("/Users/chuanfuchen/Documents/A股监控系统v3"),
            python_executable="/usr/bin/python3",
            dsn="postgresql://example/db",
        )

        self.assertIn("<key>Hour</key>", plist)
        self.assertIn("<integer>18</integer>", plist)
        self.assertIn("<key>KeepAlive</key>\n  <false/>", plist)
        self.assertIn("scripts/run_post_close_n1_n2_n3a1_oneshot.py", plist)
        self.assertIn("<string>src:scripts</string>", plist)


if __name__ == "__main__":
    unittest.main()
