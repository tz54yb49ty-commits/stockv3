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
from ashare_v3.runtime.intraday_worker_lineage import (
    build_intraday_worker_lineage_refresh_report,
)
from ashare_v3.web.post_close_fastlane_status import read_post_close_fastlane_status


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

    def test_repair_refresh_writes_intraday_worker_lineage_config_after_status_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "docs" / "post_close_fastlane"
            docs_dir = docs_root / "20260612"
            docs_dir.mkdir(parents=True)
            (docs_dir / "00_status.json").write_text(
                json.dumps(
                    {
                        "result": "EXECUTE_PASS",
                        "source_trade_date": "20260611",
                        "for_trade_date": "20260612",
                        "failed_step_id": None,
                    }
                ),
                encoding="utf-8",
            )
            (docs_dir / "01_oneshot_execute_report.json").write_text(
                json.dumps(
                    {
                        "result": "EXECUTE_PASS",
                        "source_trade_date": "20260611",
                        "for_trade_date": "20260612",
                        "run_ids": {
                            "condition_run_id": "condition_layer_20260611_source_20260611_for_20260612_v1",
                            "subscription_run_id": "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
                            "preload_run_id": "previous_day_minute_preload_20260611_for_20260612__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
                        },
                    }
                ),
                encoding="utf-8",
            )

            report = build_intraday_worker_lineage_refresh_report(
                docs_root=docs_root,
                docs_dir=docs_dir,
                updated_by="runtime_control_status_repair",
                execute=True,
            )
            config_path = docs_root.parent / "runtime" / "current_intraday_worker_lineage.json"
            payload = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(report["result"], "LINEAGE_REFRESH_PASS")
        self.assertTrue(report["lineage_written"])
        self.assertEqual(payload["for_trade_date"], "20260612")
        self.assertEqual(payload["source_trade_date"], "20260611")
        self.assertEqual(payload["updated_by"], "runtime_control_status_repair")

    def test_repair_refresh_noops_when_intraday_worker_lineage_already_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "docs" / "post_close_fastlane"
            docs_dir = docs_root / "20260612"
            docs_dir.mkdir(parents=True)
            status_path = docs_dir / "00_status.json"
            report_path = docs_dir / "01_oneshot_execute_report.json"
            status_path.write_text(
                json.dumps(
                    {
                        "result": "EXECUTE_PASS",
                        "source_trade_date": "20260611",
                        "for_trade_date": "20260612",
                    }
                ),
                encoding="utf-8",
            )
            report_path.write_text(
                json.dumps(
                    {
                        "result": "EXECUTE_PASS",
                        "run_ids": {
                            "condition_run_id": "condition_layer_20260611_source_20260611_for_20260612_v1",
                            "subscription_run_id": "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
                            "preload_run_id": "previous_day_minute_preload_20260611_for_20260612__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
                        },
                    }
                ),
                encoding="utf-8",
            )
            config_path = docs_root.parent / "runtime" / "current_intraday_worker_lineage.json"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                json.dumps(
                    {
                        "enabled": True,
                        "for_trade_date": "20260612",
                        "source_trade_date": "20260611",
                        "n2_run_id": "condition_layer_20260611_source_20260611_for_20260612_v1",
                        "subscription_run_id": "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
                        "a1_preload_run_id": "previous_day_minute_preload_20260611_for_20260612__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
                        "n4_context_run_id": n4_context_run_id_for("20260611", "20260612"),
                        "updated_by": "previous_refresh",
                        "updated_at": "2026-06-12T02:06:21+08:00",
                        "source_status_path": str(status_path),
                        "source_oneshot_report_path": str(report_path),
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            report = build_intraday_worker_lineage_refresh_report(docs_root=docs_root, docs_dir=docs_dir, execute=True)
            payload = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(report["result"], "LINEAGE_REFRESH_NOOP_ALREADY_CURRENT")
        self.assertFalse(report["lineage_written"])
        self.assertEqual(payload["updated_by"], "previous_refresh")

    def test_repair_refresh_blocks_when_fastlane_status_is_not_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "docs" / "post_close_fastlane"
            docs_dir = docs_root / "20260612"
            docs_dir.mkdir(parents=True)
            (docs_dir / "00_status.json").write_text(
                json.dumps(
                    {
                        "result": "PARTIAL_BLOCKED",
                        "source_trade_date": "20260611",
                        "for_trade_date": "20260612",
                        "failed_step_id": "n4_trigger_context_snapshot",
                    }
                ),
                encoding="utf-8",
            )
            (docs_dir / "01_oneshot_execute_report.json").write_text(
                json.dumps({"result": "PARTIAL_BLOCKED"}),
                encoding="utf-8",
            )

            report = build_intraday_worker_lineage_refresh_report(docs_root=docs_root, docs_dir=docs_dir, execute=True)

        self.assertEqual(report["result"], "BLOCKED_FASTLANE_NOT_PASS")
        self.assertEqual(report["blocked_reason"], "fastlane_not_execute_pass")

    def test_n5_n3t_readiness_rollover_failure_does_not_fail_main_post_close_result(self) -> None:
        calls = []

        def fake_runner(argv):
            calls.append(argv)
            if "scripts/plan_n5_n3t_fastlane_launchd.py" in argv:
                return SimpleNamespace(returncode=2, stdout="", stderr="rollover failed")
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
                enable_n5_n3t_readiness_rollover=True,
                command_runner=fake_runner,
            )

        self.assertEqual(report["result"], "EXECUTE_PASS")
        self.assertIsNone(report["failed_step_id"])
        self.assertEqual(report["n5_n3t_readiness_blocker"], "n5_n3t_next_trade_day_readiness_rollover_failed")
        self.assertEqual(report["n5_n3t_next_trade_day_readiness"]["returncode"], 2)
        self.assertIn("rollover failed", report["n5_n3t_next_trade_day_readiness"]["stderr_tail"])
        self.assertTrue(any("scripts/plan_n5_n3t_fastlane_launchd.py" in call for call in calls))
        self.assertEqual(report["sub_steps"][-1]["step_id"], "worker_launchd_guard")

    def test_n5_n3t_readiness_rollover_uses_source_trade_date_and_current_stable_base(self) -> None:
        calls = []

        def fake_runner(argv):
            calls.append(argv)
            if "scripts/plan_n5_n3t_fastlane_launchd.py" in argv:
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps(
                        {
                            "result": "PASS",
                            "next_trade_date": "20260612",
                            "stable_activation_config_path": "tmp/N5_N3T_action_confirmation_fastlane_activation_config/write_enabled_activation_config_current_runtime_deferred_v1.json",
                            "dated_activation_config_path": "tmp/N5_N3T_action_confirmation_fastlane_activation_config/write_enabled_activation_config_20260612_runtime_deferred_v1.json",
                            "active_worker_policy_review_path": "tmp/N5_N3T_action_confirmation_fastlane_open_monitor_precheck/20260612/active_worker_policy_review_current_latest.json",
                            "active_worker_policy_review": {
                                "result": "WAITING",
                                "active_worker_write_enabled_ready": False,
                            },
                        }
                    ),
                    stderr="",
                )
            return SimpleNamespace(returncode=0, stdout=json.dumps({"result": "EXECUTE_PASS"}), stderr="")

        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "ashare_v3.runtime.post_close_fastlane.select_n5_n3t_readiness_rollover_base_activation_config",
            return_value=Path(
                "tmp/N5_N3T_action_confirmation_fastlane_activation_config/write_enabled_activation_config_current_runtime_deferred_v1.json"
            ),
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
                include_calendar_repair=False,
                enable_n5_n3t_readiness_rollover=True,
                command_runner=fake_runner,
            )

        rollover_call = next(call for call in calls if "scripts/plan_n5_n3t_fastlane_launchd.py" in call)
        self.assertEqual(rollover_call[rollover_call.index("--for-trade-date") + 1], "20260611")
        self.assertEqual(
            rollover_call[rollover_call.index("--base-activation-config") + 1],
            "tmp/N5_N3T_action_confirmation_fastlane_activation_config/write_enabled_activation_config_current_runtime_deferred_v1.json",
        )
        self.assertEqual(rollover_call[rollover_call.index("--current-exchange-time") + 1], "2026-06-11T18:00:00+08:00")
        self.assertEqual(report["result"], "EXECUTE_PASS")
        self.assertEqual(report["n5_n3t_next_trade_day_readiness"]["result"], "PASS")

    def test_n5_n3t_readiness_rollover_base_config_prefers_matching_stable_then_source_dated(self) -> None:
        from ashare_v3.runtime.post_close_fastlane import select_n5_n3t_readiness_rollover_base_activation_config

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            stable = output_dir / "write_enabled_activation_config_current_runtime_deferred_v1.json"
            source_dated = output_dir / "write_enabled_activation_config_20260611_runtime_deferred_v1.json"
            stable.write_text(
                json.dumps({"artifact_type": "n5_n3t_fastlane_activation_config_v1", "for_trade_date": "20260611"}),
                encoding="utf-8",
            )
            source_dated.write_text(
                json.dumps({"artifact_type": "n5_n3t_fastlane_activation_config_v1", "for_trade_date": "20260611"}),
                encoding="utf-8",
            )

            selected = select_n5_n3t_readiness_rollover_base_activation_config(
                output_dir=output_dir,
                source_trade_date="20260611",
            )

            self.assertEqual(selected, stable)

            stable.write_text(
                json.dumps({"artifact_type": "n5_n3t_fastlane_activation_config_v1", "for_trade_date": "20260610"}),
                encoding="utf-8",
            )

            selected = select_n5_n3t_readiness_rollover_base_activation_config(
                output_dir=output_dir,
                source_trade_date="20260611",
            )

            self.assertEqual(selected, source_dated)

    def test_status_helper_exposes_n5_n3t_next_trade_day_readiness_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "docs"
            run_dir = docs_root / "20260612"
            run_dir.mkdir(parents=True)
            (run_dir / "00_status.json").write_text(
                json.dumps(
                    {
                        "result": "EXECUTE_PASS",
                        "source_trade_date": "20260611",
                        "for_trade_date": "20260612",
                        "failed_step_id": None,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (run_dir / "01_oneshot_execute_report.json").write_text(
                json.dumps(
                    {
                        "result": "EXECUTE_PASS",
                        "source_trade_date": "20260611",
                        "for_trade_date": "20260612",
                        "n5_n3t_next_trade_day_readiness": {
                            "result": "PASS",
                            "next_trade_date": "20260615",
                            "stable_activation_config_path": "tmp/N5_N3T_action_confirmation_fastlane_activation_config/write_enabled_activation_config_current_runtime_deferred_v1.json",
                            "active_worker_policy_review_path": "tmp/N5_N3T_action_confirmation_fastlane_open_monitor_precheck/20260615/active_worker_policy_review_current_latest.json",
                            "review_result": "WAITING",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            status = read_post_close_fastlane_status(docs_root=docs_root, for_trade_date="20260612")

        readiness = status["n5_n3t_next_trade_day_readiness"]
        self.assertEqual(readiness["next_trade_date"], "20260615")
        self.assertEqual(readiness["review_result"], "WAITING")
        readiness_steps = [
            row for row in status["sub_steps"] if row["step_id"] == "n5_n3t_next_trade_day_readiness_rollover"
        ]
        self.assertEqual(len(readiness_steps), 1)
        self.assertEqual(readiness_steps[0]["layer_role"], "runtime_control")
        self.assertEqual(readiness_steps[0]["status"], "PASS")
        self.assertEqual(readiness_steps[0]["report_paths"][0], "tmp/N5_N3T_action_confirmation_fastlane_activation_config/write_enabled_activation_config_current_runtime_deferred_v1.json")
        labels = [item["label"] for item in status["artifacts"]]
        self.assertIn("N5/N3T stable activation config", labels)
        self.assertIn("N5/N3T active worker policy review", labels)

    def test_status_helper_derives_n5_n3t_readiness_from_local_artifacts_when_report_is_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            docs_root = project_root / "docs" / "post_close_fastlane"
            run_dir = docs_root / "20260612"
            run_dir.mkdir(parents=True)
            (run_dir / "00_status.json").write_text(
                json.dumps(
                    {
                        "result": "EXECUTE_PASS",
                        "source_trade_date": "20260611",
                        "for_trade_date": "20260612",
                        "failed_step_id": None,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (run_dir / "01_oneshot_execute_report.json").write_text(
                json.dumps(
                    {
                        "result": "EXECUTE_PASS",
                        "source_trade_date": "20260611",
                        "for_trade_date": "20260612",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            stable_path = (
                project_root
                / "tmp"
                / "N5_N3T_action_confirmation_fastlane_activation_config"
                / "write_enabled_activation_config_current_runtime_deferred_v1.json"
            )
            review_path = (
                project_root
                / "tmp"
                / "N5_N3T_action_confirmation_fastlane_open_monitor_precheck"
                / "20260615"
                / "active_worker_policy_review_current_latest.json"
            )
            rollover_path = (
                project_root
                / "tmp"
                / "N5_N3T_action_confirmation_fastlane_activation_config"
                / "n5_n3t_post_close_readiness_config_rollover_20260615.json"
            )
            stable_path.parent.mkdir(parents=True)
            review_path.parent.mkdir(parents=True)
            stable_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260615",
                        "active_worker_policy_review_path": (
                            "tmp/N5_N3T_action_confirmation_fastlane_open_monitor_precheck/"
                            "20260615/active_worker_policy_review_current_latest.json"
                        ),
                        "policy": {"authorization_timing": "runtime_deferred_to_runner"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            review_path.write_text(
                json.dumps(
                    {
                        "for_trade_date": "20260615",
                        "result": "WAITING",
                        "active_worker_write_enabled_ready": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            rollover_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_post_close_readiness_config_rollover_v1",
                        "for_trade_date": "20260612",
                        "next_trade_date": "20260615",
                        "result": "PASS",
                        "stable_activation_config_path": (
                            "tmp/N5_N3T_action_confirmation_fastlane_activation_config/"
                            "write_enabled_activation_config_current_runtime_deferred_v1.json"
                        ),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            status = read_post_close_fastlane_status(docs_root=docs_root, for_trade_date="20260612")

        readiness = status["n5_n3t_next_trade_day_readiness"]
        self.assertEqual(readiness["source"], "derived_from_local_readiness_artifacts")
        self.assertEqual(readiness["next_trade_date"], "20260615")
        self.assertEqual(readiness["result"], "PASS")
        self.assertEqual(readiness["review_result"], "WAITING")
        self.assertFalse(readiness["active_worker_write_enabled_ready"])
        self.assertEqual(readiness["launchd_live_state"], "not_checked_by_status_page")
        readiness_steps = [
            row for row in status["sub_steps"] if row["step_id"] == "n5_n3t_next_trade_day_readiness_rollover"
        ]
        self.assertEqual(len(readiness_steps), 1)
        self.assertEqual(readiness_steps[0]["status"], "PASS")
        self.assertEqual(readiness_steps[0]["returncode"], "—")
        labels = [item["label"] for item in status["artifacts"]]
        self.assertIn("N5/N3T readiness rollover report", labels)
        self.assertIn("N5/N3T stable activation config", labels)
        self.assertIn("N5/N3T active worker policy review", labels)

    def test_status_helper_overrides_stale_blocked_n5_n3t_readiness_from_local_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            docs_root = project_root / "docs" / "post_close_fastlane"
            run_dir = docs_root / "20260708"
            run_dir.mkdir(parents=True)
            (run_dir / "00_status.json").write_text(
                json.dumps(
                    {
                        "result": "EXECUTE_PASS",
                        "source_trade_date": "20260707",
                        "for_trade_date": "20260708",
                        "failed_step_id": None,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (run_dir / "01_oneshot_execute_report.json").write_text(
                json.dumps(
                    {
                        "result": "EXECUTE_PASS",
                        "source_trade_date": "20260707",
                        "for_trade_date": "20260708",
                        "n5_n3t_next_trade_day_readiness": {
                            "result": "BLOCKED",
                            "next_trade_date": "",
                            "stable_activation_config_path": "",
                            "active_worker_policy_review_path": "",
                            "review_result": "",
                        },
                        "n5_n3t_readiness_blocker": "n5_n3t_next_trade_day_readiness_rollover_failed",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            stable_path = (
                project_root
                / "tmp"
                / "N5_N3T_action_confirmation_fastlane_activation_config"
                / "write_enabled_activation_config_current_runtime_deferred_v1.json"
            )
            review_path = (
                project_root
                / "tmp"
                / "N5_N3T_action_confirmation_fastlane_open_monitor_precheck"
                / "20260708"
                / "active_worker_policy_review_current_latest.json"
            )
            rollover_path = (
                project_root
                / "tmp"
                / "N5_N3T_action_confirmation_fastlane_activation_config"
                / "n5_n3t_post_close_readiness_config_rollover_20260708.json"
            )
            stable_path.parent.mkdir(parents=True)
            review_path.parent.mkdir(parents=True)
            stable_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260708",
                        "active_worker_policy_review_path": (
                            "tmp/N5_N3T_action_confirmation_fastlane_open_monitor_precheck/"
                            "20260708/active_worker_policy_review_current_latest.json"
                        ),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            review_path.write_text(
                json.dumps(
                    {
                        "for_trade_date": "20260708",
                        "result": "WAITING",
                        "active_worker_write_enabled_ready": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            rollover_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_post_close_readiness_config_rollover_v1",
                        "for_trade_date": "20260707",
                        "next_trade_date": "20260708",
                        "result": "PASS",
                        "stable_activation_config_path": (
                            "tmp/N5_N3T_action_confirmation_fastlane_activation_config/"
                            "write_enabled_activation_config_current_runtime_deferred_v1.json"
                        ),
                        "active_worker_policy_review_path": (
                            "tmp/N5_N3T_action_confirmation_fastlane_open_monitor_precheck/"
                            "20260708/active_worker_policy_review_current_latest.json"
                        ),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            status = read_post_close_fastlane_status(docs_root=docs_root, for_trade_date="20260708")

        readiness = status["n5_n3t_next_trade_day_readiness"]
        self.assertEqual(readiness["source"], "derived_from_local_readiness_artifacts")
        self.assertEqual(readiness["result"], "PASS")
        self.assertEqual(readiness["next_trade_date"], "20260708")
        self.assertEqual(readiness["review_result"], "WAITING")
        self.assertFalse(readiness["active_worker_write_enabled_ready"])
        self.assertEqual(status["result"], "EXECUTE_PASS")
        labels = [item["label"] for item in status["artifacts"]]
        self.assertIn("N5/N3T readiness rollover report", labels)
        self.assertIn("N5/N3T stable activation config", labels)
        self.assertIn("N5/N3T active worker policy review", labels)

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
