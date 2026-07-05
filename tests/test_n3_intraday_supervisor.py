import contextlib
import io
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ashare_v3.market.intraday_supervisor import (
    build_intraday_supervisor_plan,
    load_intraday_supervisor_report,
    run_intraday_supervisor_plan,
    validate_child_command,
)
import scripts.run_n3_intraday_b1_c1_b2_supervisor_once as supervisor_cli


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
SUBSCRIPTION_RUN_ID = "market_data_subscription_20260611_condition_layer_x"
PRELOAD_RUN_ID = "previous_day_minute_preload_20260610_for_20260611__market_data_subscription_x"


class N3IntradaySupervisorTest(unittest.TestCase):
    def test_auction_0919_plan_only_prewarms_without_execute_steps(self) -> None:
        report = build_intraday_supervisor_plan(
            for_trade_date="20260611",
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            as_of=datetime(2026, 6, 11, 9, 19, 30, tzinfo=ASIA_SHANGHAI),
            passed_run_ids=set(),
            python_executable=sys.executable,
        )

        self.assertEqual(report["status"], "noop")
        self.assertEqual(report["reason"], "auction_preopen_plan_only")
        self.assertEqual(report["stage_order_policy"], "B1_B2_PREWARM_ONLY")
        self.assertEqual(report["child_steps"], [])

    def test_auction_0920_builds_b1_b2_execute_commands_and_skips_c1(self) -> None:
        report = build_intraday_supervisor_plan(
            for_trade_date="20260611",
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            as_of=datetime(2026, 6, 11, 9, 20, 0, tzinfo=ASIA_SHANGHAI),
            passed_run_ids=set(),
            python_executable=sys.executable,
        )

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["reason"], "auction_snapshot_projection_ready")
        self.assertEqual(report["latest_closed_minute_hhmm"], None)
        self.assertEqual(report["effective_hhmm"], "0920")
        self.assertEqual(report["projection_input_mode"], "auction_or_snapshot_only")
        self.assertEqual([step["stage"] for step in report["child_steps"]], ["B1", "B2"])
        self.assertEqual(report["skipped_child_steps"][0]["stage"], "C1")
        self.assertEqual(report["skipped_child_steps"][0]["reason"], "no_closed_minute_available")
        self.assertIn("auction", report["child_steps"][0]["run_id"])
        self.assertIn("auction", report["child_steps"][1]["run_id"])
        for step in report["child_steps"]:
            self.assertIn("--execute", step["command"])
            self.assertIn("--user-confirmed", step["command"])

    def test_auction_0925_builds_b1_b2_execute_commands_and_skips_c1(self) -> None:
        report = build_intraday_supervisor_plan(
            for_trade_date="20260611",
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            as_of=datetime(2026, 6, 11, 9, 25, 5, tzinfo=ASIA_SHANGHAI),
            passed_run_ids=set(),
            python_executable=sys.executable,
        )

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["effective_hhmm"], "0925")
        self.assertEqual(report["stage_order_policy"], "B1_B2_BEFORE_FIRST_CLOSED_MINUTE")
        self.assertEqual([step["stage"] for step in report["child_steps"]], ["B1", "B2"])
        self.assertEqual(report["skipped_child_steps"][0]["stage"], "C1")

    def test_new_closed_minute_builds_b1_c1_b2_execute_commands_in_order(self) -> None:
        report = build_intraday_supervisor_plan(
            for_trade_date="20260611",
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            as_of=datetime(2026, 6, 11, 9, 32, 5, tzinfo=ASIA_SHANGHAI),
            passed_run_ids=set(),
            python_executable=sys.executable,
        )

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["latest_closed_minute_hhmm"], "0931")
        self.assertEqual([step["stage"] for step in report["child_steps"]], ["B1", "C1", "B2"])
        for step in report["child_steps"]:
            self.assertIsInstance(step["command"], list)
            self.assertIn("--execute", step["command"])
            self.assertIn("--user-confirmed", step["command"])
            joined = " ".join(step["command"])
            self.assertNotIn("run_n4", joined)
            self.assertNotIn("run_n5", joined)
            self.assertNotIn("run_n6", joined)
            self.assertNotIn("worker", joined)
        self.assertIn("realtime_daily_snapshot_20260611_until_0931__", report["child_steps"][0]["run_id"])
        self.assertIn("today_minute_bar_1m_20260611_until_0931__", report["child_steps"][1]["run_id"])
        self.assertIn("realtime_projection_metric_20260611_until_0931__", report["child_steps"][2]["run_id"])

    def test_b1_child_step_exposes_rollback_path_without_passing_unsupported_runner_arg(self) -> None:
        report = build_intraday_supervisor_plan(
            for_trade_date="20260611",
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            as_of=datetime(2026, 6, 11, 9, 32, 5, tzinfo=ASIA_SHANGHAI),
            passed_run_ids=set(),
            python_executable=sys.executable,
        )

        b1_step = report["child_steps"][0]
        self.assertEqual(b1_step["stage"], "B1")
        self.assertEqual(
            b1_step["rollback_sql_path"],
            "sql/N3_B1_realtime_snapshot_20260611_until_0931_rollback.sql",
        )
        self.assertNotIn("--rollback-sql-path", b1_step["command"])

    def test_noops_when_latest_projection_run_already_passed(self) -> None:
        probe = build_intraday_supervisor_plan(
            for_trade_date="20260611",
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            as_of=datetime(2026, 6, 11, 9, 32, 5, tzinfo=ASIA_SHANGHAI),
            passed_run_ids=set(),
            python_executable=sys.executable,
        )
        projection_run_id = probe["child_steps"][2]["run_id"]

        report = build_intraday_supervisor_plan(
            for_trade_date="20260611",
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            as_of=datetime(2026, 6, 11, 9, 32, 30, tzinfo=ASIA_SHANGHAI),
            passed_run_ids={projection_run_id},
            python_executable=sys.executable,
        )

        self.assertEqual(report["status"], "noop")
        self.assertEqual(report["reason"], "latest_closed_minute_already_processed")
        self.assertEqual(report["child_steps"], [])

    def test_runner_stops_after_first_failed_child_step(self) -> None:
        plan = build_intraday_supervisor_plan(
            for_trade_date="20260611",
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            as_of=datetime(2026, 6, 11, 9, 32, 5, tzinfo=ASIA_SHANGHAI),
            passed_run_ids=set(),
            python_executable=sys.executable,
        )
        executed: list[str] = []

        def fake_runner(command: list[str]) -> object:
            executed.append(command[1])

            class Result:
                returncode = 2
                stdout = "blocked"
                stderr = "P0"

            return Result()

        report = run_intraday_supervisor_plan(plan, command_runner=fake_runner)

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["failed_stage"], "B1")
        self.assertEqual(len(executed), 1)

    def test_blocks_when_current_local_date_is_not_for_trade_date(self) -> None:
        report = build_intraday_supervisor_plan(
            for_trade_date="20260611",
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            as_of=datetime(2026, 6, 12, 9, 32, 5, tzinfo=ASIA_SHANGHAI),
            passed_run_ids=set(),
            python_executable=sys.executable,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "current_date_mismatch")
        self.assertEqual(report["child_steps"], [])

    def test_cli_defaults_to_plan_only_and_writes_report_without_running_children(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "supervisor.json"
            md_path = Path(tmp) / "supervisor.md"

            with contextlib.redirect_stdout(io.StringIO()):
                rc = supervisor_cli.main(
                    [
                        "--for-trade-date",
                        "20260611",
                        "--subscription-run-id",
                        SUBSCRIPTION_RUN_ID,
                        "--preload-run-id",
                        PRELOAD_RUN_ID,
                        "--as-of",
                        "2026-06-11T09:32:05+08:00",
                        "--skip-db-watermark",
                        "--json-report-path",
                        str(json_path),
                        "--markdown-report-path",
                        str(md_path),
                        "--json",
                    ]
                )

            self.assertEqual(rc, 0)
            report = load_intraday_supervisor_report(json_path)
            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["execution_mode"], "plan_only")
            self.assertEqual(report["executed_child_command_count"], 0)
            self.assertTrue(md_path.exists())

    def test_child_command_guard_blocks_old_system_and_event_mutation_markers(self) -> None:
        forbidden_commands = [
            [sys.executable, "/Users/chuanfuchen/stock_monitor_isolated/run.py", "--execute", "--user-confirmed"],
            [sys.executable, "scripts/update_common_event_outbox.py", "--execute", "--user-confirmed"],
            [sys.executable, "scripts/run_proposal_order_trade.py", "--execute", "--user-confirmed"],
        ]

        for command in forbidden_commands:
            with self.subTest(command=command):
                with self.assertRaises(ValueError):
                    validate_child_command(command)

    def test_child_command_guard_ignores_forbidden_marker_in_artifact_paths(self) -> None:
        validate_child_command(
            [
                sys.executable,
                "scripts/run_today_minute_bar_1m_once.py",
                "--c0-plan-path",
                "/tmp/pnl_artifacts/c0_plan.json",
                "--pre-backup-path",
                "/tmp/pnl_artifacts/pre.json",
                "--post-backup-path",
                "/tmp/pnl_artifacts/post.json",
                "--json-report-path",
                "/tmp/pnl_artifacts/report.json",
                "--markdown-report-path",
                "/tmp/pnl_artifacts/report.md",
                "--rollback-sql-path",
                "/tmp/pnl_artifacts/rollback.sql",
                "--for-trade-date",
                "20260611",
                "--today-minute-run-id",
                "today_minute_run_1",
                "--execute",
                "--user-confirmed",
                "--json",
            ]
        )

    def test_child_command_guard_blocks_forbidden_script_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "forbidden_command_marker"):
            validate_child_command(
                [
                    sys.executable,
                    "scripts/run_action_consumer_once.py",
                    "--json-report-path",
                    "/tmp/report.json",
                    "--execute",
                    "--user-confirmed",
                ]
            )

    def test_child_command_guard_blocks_forbidden_semantic_token(self) -> None:
        with self.assertRaisesRegex(ValueError, "forbidden_command_marker:pnl"):
            validate_child_command(
                [
                    sys.executable,
                    "scripts/run_realtime_projection_metric_once.py",
                    "--json-report-path",
                    "/tmp/report.json",
                    "--rollback-sql-path",
                    "/tmp/rollback.sql",
                    "--projection-run-id",
                    "pnl_projection_run",
                    "--for-trade-date",
                    "20260611",
                    "--execute",
                    "--user-confirmed",
                    "--json",
                ]
            )

    def test_child_command_guard_requires_execute_flag(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing_confirmation_flags"):
            validate_child_command(
                [
                    sys.executable,
                    "scripts/run_realtime_projection_metric_once.py",
                    "--json-report-path",
                    "/tmp/report.json",
                    "--rollback-sql-path",
                    "/tmp/rollback.sql",
                    "--projection-run-id",
                    "projection_run_1",
                    "--for-trade-date",
                    "20260611",
                    "--user-confirmed",
                    "--json",
                ]
            )

    def test_child_command_guard_requires_user_confirmed_flag(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing_confirmation_flags"):
            validate_child_command(
                [
                    sys.executable,
                    "scripts/run_realtime_projection_metric_once.py",
                    "--json-report-path",
                    "/tmp/report.json",
                    "--rollback-sql-path",
                    "/tmp/rollback.sql",
                    "--projection-run-id",
                    "projection_run_1",
                    "--for-trade-date",
                    "20260611",
                    "--execute",
                    "--json",
                ]
            )


if __name__ == "__main__":
    unittest.main()
