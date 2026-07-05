import io
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts import run_n6_projection_once


class N6ProjectionCliTest(unittest.TestCase):
    def test_zero_user_message_projection_returns_success_exit_code(self) -> None:
        argv = [
            "run_n6_projection_once.py",
            "--projection-run-id",
            "test_projection_run",
            "--source-action-run-id",
            "test_action_run",
            "--expected-n5-outbox-count",
            "ActionBlocked:pending=836",
            "--contract-json-path",
            "docs/V3_20260615_N6_USER_PROJECTION_CONTRACT.json",
            "--preflight-json-path",
            "docs/V3_20260615_N6_USER_PROJECTION_PREFLIGHT.json",
            "--execute",
            "--user-confirmed",
            "--json",
        ]
        report = {
            "result": "PROJECTION_PASS_ZERO_USER_MESSAGES",
            "write_summary": {
                "write_counts": {
                    "user_projection_run": 1,
                    "user_signal_projection": 0,
                    "user_signal_card": 0,
                    "user_notification_queue": 0,
                }
            },
        }

        with patch.object(sys, "argv", argv), patch.object(
            run_n6_projection_once,
            "run_projection_shadow_execute",
            return_value=report,
        ) as execute_mock, redirect_stdout(io.StringIO()) as stdout:
            exit_code = run_n6_projection_once.main()

        self.assertEqual(exit_code, 0)
        self.assertIn("PROJECTION_PASS_ZERO_USER_MESSAGES", stdout.getvalue())
        execute_mock.assert_called_once()

    def test_blocked_projection_report_returns_nonzero_exit_code(self) -> None:
        argv = [
            "run_n6_projection_once.py",
            "--projection-run-id",
            "test_projection_run",
            "--source-action-run-id",
            "test_action_run",
            "--execute",
            "--user-confirmed",
            "--json",
        ]

        with patch.object(sys, "argv", argv), patch.object(
            run_n6_projection_once,
            "run_projection_shadow_execute",
            return_value={"result": "BLOCKED", "blockers": ["test_blocker"]},
        ), redirect_stdout(io.StringIO()) as stdout:
            exit_code = run_n6_projection_once.main()

        self.assertEqual(exit_code, 2)
        self.assertIn("BLOCKED", stdout.getvalue())

    def test_custom_rollback_sql_path_is_passed_to_execute_runner(self) -> None:
        argv = [
            "run_n6_projection_once.py",
            "--projection-run-id",
            "test_projection_run",
            "--source-action-run-id",
            "test_action_run",
            "--expected-n5-outbox-count",
            "ActionExecuted:pending=49",
            "--rollback-sql-path",
            "sql/custom_n6_projection_rollback.sql",
            "--execute",
            "--user-confirmed",
            "--json",
        ]
        report = {"result": "EXECUTED", "write_summary": {"write_counts": {"user_projection_run": 1}}}

        with patch.object(sys, "argv", argv), patch.object(
            run_n6_projection_once,
            "run_projection_shadow_execute",
            return_value=report,
        ) as execute_mock, redirect_stdout(io.StringIO()):
            exit_code = run_n6_projection_once.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(execute_mock.call_args.kwargs["rollback_sql_path"], "sql/custom_n6_projection_rollback.sql")


if __name__ == "__main__":
    unittest.main()
