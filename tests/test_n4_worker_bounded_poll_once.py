import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

import run_n4_worker_bounded_poll_once as poll_runner


ASIA_SHANGHAI = timezone(timedelta(hours=8))


class N4WorkerBoundedPollOnceTests(unittest.TestCase):
    def test_plan_only_builds_dynamic_child_command_without_invoking_child(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report_path = root / "wrapper_report.json"
            report = poll_runner.run_bounded_poll_once(
                for_trade_date="20260611",
                source_run_id="snapshot_run_20260611",
                source_event_type="MarketSnapshotUpdated",
                source_trade_date="20260611",
                consumer_name="n4_trigger_worker_v1_bounded_polling_20260611",
                max_events=50,
                max_runtime_seconds=120,
                heartbeat_interval_seconds=10,
                docs_root=root / "docs",
                sql_root=root / "sql",
                tmp_root=root / "tmp",
                wrapper_json_report_path=report_path,
                now=datetime(2026, 6, 11, 9, 46, 7, tzinfo=ASIA_SHANGHAI),
                command_runner=lambda argv: calls.append(argv),
            )

            self.assertEqual(report["result"], "PLAN_ONLY")
            self.assertFalse(report["child_invoked"])
            self.assertEqual(calls, [])
            self.assertEqual(
                report["generated"]["smoke_run_id"],
                "n4_worker_bounded_poll_20260611_20260611T094607+0800",
            )
            self.assertTrue(report["generated"]["status_json"].endswith("_094607_STATUS.json"))
            self.assertTrue(report["generated"]["json_report_path"].endswith("_094607_EXECUTE_REPORT.json"))
            self.assertTrue(report["generated"]["rollback_sql_path"].endswith("_094607_rollback.sql"))
            self.assertIsInstance(report["child_argv_for_execute"], list)
            self.assertIn("--execute", report["child_argv_for_execute"])
            self.assertIn("--user-confirmed", report["child_argv_for_execute"])
            self.assertTrue(report_path.exists())

    def test_execute_requires_user_confirmed_before_child_invocation(self):
        calls = []
        probe_calls = []
        with tempfile.TemporaryDirectory() as tmpdir:
            report = poll_runner.run_bounded_poll_once(
                for_trade_date="20260611",
                source_run_id="snapshot_run_20260611",
                source_event_type="MarketSnapshotUpdated",
                source_trade_date="20260611",
                consumer_name="n4_trigger_worker_v1_bounded_polling_20260611",
                docs_root=Path(tmpdir) / "docs",
                sql_root=Path(tmpdir) / "sql",
                tmp_root=Path(tmpdir) / "tmp",
                now=datetime(2026, 6, 11, 9, 46, 7, tzinfo=ASIA_SHANGHAI),
                execute=True,
                user_confirmed=False,
                command_runner=lambda argv: calls.append(argv),
                source_event_probe=lambda context: probe_calls.append(context),
            )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["blocked_reason"], "missing --user-confirmed")
        self.assertEqual(calls, [])
        self.assertEqual(probe_calls, [])

    def test_user_confirmed_without_execute_blocks_before_child_invocation(self):
        calls = []
        probe_calls = []
        with tempfile.TemporaryDirectory() as tmpdir:
            report = poll_runner.run_bounded_poll_once(
                for_trade_date="20260611",
                source_run_id="snapshot_run_20260611",
                source_event_type="MarketSnapshotUpdated",
                source_trade_date="20260611",
                consumer_name="n4_trigger_worker_v1_bounded_polling_20260611",
                docs_root=Path(tmpdir) / "docs",
                sql_root=Path(tmpdir) / "sql",
                tmp_root=Path(tmpdir) / "tmp",
                now=datetime(2026, 6, 11, 9, 46, 7, tzinfo=ASIA_SHANGHAI),
                execute=False,
                user_confirmed=True,
                command_runner=lambda argv: calls.append(argv),
                source_event_probe=lambda context: probe_calls.append(context),
            )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["blocked_reason"], "missing --execute")
        self.assertEqual(calls, [])
        self.assertEqual(probe_calls, [])

    def test_execute_no_source_returns_true_noop_without_child_invocation_or_db_write(self):
        calls = []
        probe_contexts = []

        def source_event_probe(context):
            probe_contexts.append(context)
            return []

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report_path = root / "wrapper_noop.json"
            markdown_path = root / "wrapper_noop.md"
            report = poll_runner.run_bounded_poll_once(
                for_trade_date="20260611",
                source_run_id="snapshot_run_20260611",
                source_event_type="MarketSnapshotUpdated",
                source_trade_date="20260611",
                consumer_name="n4_trigger_worker_v1_bounded_polling_20260611",
                max_events=50,
                docs_root=root / "docs",
                sql_root=root / "sql",
                tmp_root=root / "tmp",
                wrapper_json_report_path=report_path,
                wrapper_markdown_report_path=markdown_path,
                now=datetime(2026, 6, 11, 20, 0, 22, tzinfo=ASIA_SHANGHAI),
                execute=True,
                user_confirmed=True,
                command_runner=lambda argv: calls.append(argv),
                source_event_probe=source_event_probe,
            )
            saved = json.loads(report_path.read_text(encoding="utf-8"))
            markdown_exists = markdown_path.exists()

        self.assertTrue(markdown_exists)
        self.assertEqual(report["result"], "NOOP_PASS")
        self.assertEqual(report["reason"], "no_unprocessed_source_events")
        self.assertFalse(report["child_invoked"])
        self.assertEqual(calls, [])
        self.assertEqual(len(probe_contexts), 1)
        self.assertEqual(probe_contexts[0]["consumer_name"], "n4_trigger_worker_v1_bounded_polling_20260611")
        self.assertEqual(probe_contexts[0]["source_run_id"], "snapshot_run_20260611")
        self.assertEqual(probe_contexts[0]["max_events"], 50)
        self.assertEqual(report["source_probe"]["accepted_source_event_count"], 0)
        self.assertFalse(report["source_probe"]["has_unprocessed_source_events"])
        self.assertFalse(report["side_effects"]["scoped_n4_database_writes"])
        self.assertFalse(report["side_effects"]["database_written"])
        self.assertFalse(report["side_effects"]["trigger_run_written"])
        self.assertEqual(saved["result"], "NOOP_PASS")

    def test_execute_invokes_smoke_runner_with_argv_list_and_dynamic_paths(self):
        calls = []
        probe_contexts = []

        class Completed:
            returncode = 0
            stdout = "child ok"
            stderr = ""

        def source_event_probe(context):
            probe_contexts.append(context)
            return [{"event_id": "evt_unprocessed_1"}]

        def command_runner(argv):
            calls.append(argv)
            return Completed()

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = poll_runner.run_bounded_poll_once(
                for_trade_date="20260611",
                source_run_id="snapshot_run_20260611",
                source_event_type="MarketSnapshotUpdated",
                source_trade_date="20260611",
                consumer_name="n4_trigger_worker_v1_bounded_polling_20260611",
                max_events=50,
                max_runtime_seconds=120,
                heartbeat_interval_seconds=10,
                docs_root=root / "docs",
                sql_root=root / "sql",
                tmp_root=root / "tmp",
                now=datetime(2026, 6, 11, 9, 46, 7, tzinfo=ASIA_SHANGHAI),
                execute=True,
                user_confirmed=True,
                command_runner=command_runner,
                source_event_probe=source_event_probe,
            )

        self.assertEqual(report["result"], "EXECUTE_PASS")
        self.assertTrue(report["child_invoked"])
        self.assertEqual(report["source_probe"]["accepted_source_event_count"], 1)
        self.assertTrue(report["source_probe"]["has_unprocessed_source_events"])
        self.assertEqual(len(probe_contexts), 1)
        self.assertEqual(len(calls), 1)
        child_argv = calls[0]
        self.assertIsInstance(child_argv, list)
        self.assertEqual(child_argv[0], sys.executable)
        self.assertNotEqual(child_argv[0], "python3")
        self.assertEqual(child_argv[1], "scripts/run_n4_worker_bounded_smoke_once.py")
        self.assertIn("--smoke-run-id", child_argv)
        self.assertIn("n4_worker_bounded_poll_20260611_20260611T094607+0800", child_argv)
        self.assertIn("--execute", child_argv)
        self.assertIn("--user-confirmed", child_argv)
        self.assertIn(str(root / "docs" / "N4_WORKER_BOUNDED_POLLING_20260611_094607_STATUS.json"), child_argv)
        self.assertIn(str(root / "sql" / "N4_worker_bounded_polling_20260611_094607_rollback.sql"), child_argv)
        self.assertFalse(report["forbidden_scope_proof"]["scheduler_installed_or_enabled"])
        self.assertFalse(report["forbidden_scope_proof"]["long_running_worker_started"])
        self.assertFalse(report["forbidden_scope_proof"]["n5_entered"])
        self.assertFalse(report["forbidden_scope_proof"]["n6_entered"])

    def test_default_child_command_uses_wrapper_runtime_python_not_bare_python3(self):
        argv = poll_runner.build_child_argv(
            python_executable=poll_runner.default_child_python_executable(),
            child_contract_path="docs/contract.json",
            smoke_run_id="n4_worker_bounded_poll_20260611_20260611T094607+0800",
            consumer_name="n4_trigger_worker_v1_bounded_polling_20260611",
            source_run_id="snapshot_run_20260611",
            source_event_type="MarketSnapshotUpdated",
            source_trade_date="20260611",
            max_events=50,
            max_runtime_seconds=120,
            heartbeat_interval_seconds=10,
            stop_file="tmp/stop",
            status_json="docs/status.json",
            json_report_path="docs/report.json",
            markdown_report_path="docs/report.md",
            rollback_sql_path="sql/rollback.sql",
        )

        self.assertEqual(argv[0], sys.executable)
        self.assertNotEqual(argv[0], "python3")

    def test_main_writes_json_report_and_returns_blocked_code_for_missing_confirmation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report_path = root / "wrapper.json"
            rc = poll_runner.main(
                [
                    "--for-trade-date",
                    "20260611",
                    "--source-run-id",
                    "snapshot_run_20260611",
                    "--source-event-type",
                    "MarketSnapshotUpdated",
                    "--source-trade-date",
                    "20260611",
                    "--consumer-name",
                    "n4_trigger_worker_v1_bounded_polling_20260611",
                    "--docs-root",
                    str(root / "docs"),
                    "--sql-root",
                    str(root / "sql"),
                    "--tmp-root",
                    str(root / "tmp"),
                    "--wrapper-json-report-path",
                    str(report_path),
                    "--execute",
                ],
                command_runner=lambda argv: None,
                now=datetime(2026, 6, 11, 9, 46, 7, tzinfo=ASIA_SHANGHAI),
            )
            saved = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(rc, 2)
        self.assertEqual(saved["result"], "BLOCKED")
        self.assertEqual(saved["blocked_reason"], "missing --user-confirmed")


if __name__ == "__main__":
    unittest.main()
