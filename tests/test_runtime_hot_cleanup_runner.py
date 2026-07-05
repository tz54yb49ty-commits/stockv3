import json
from pathlib import Path
import tempfile
import unittest

from scripts.run_runtime_dirty_hot_keep2_cleanup_once import (
    is_success_result,
    run_runtime_dirty_hot_keep2_cleanup_once,
)
from scripts.run_runtime_hot_keep5_cleanup_once import run_runtime_hot_keep5_cleanup_once
from ashare_v3.ingestion.runtime_hot_cleanup import DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN, KEEP5_CONFIRM_TOKEN


class RuntimeHotCleanupRunnerTest(unittest.TestCase):
    def test_default_run_writes_plan_only_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = run_runtime_dirty_hot_keep2_cleanup_once(
                report_dir=Path(tmp) / "docs",
                trade_dates=["20260612", "20260701", "20260702"],
                table_counter=lambda _spec, trade_date: 1 if trade_date == "20260612" else 0,
            )

            saved = json.loads(Path(report["docs_report_path"]).read_text(encoding="utf-8"))

        self.assertEqual(report["result"], "DIRTY_HOT_KEEP2_CLEANUP_PLAN_PASS")
        self.assertFalse(report["execute"])
        self.assertFalse(report["cleanup_executed"])
        self.assertEqual(report["retained_trade_dates"], ["20260701", "20260702"])
        self.assertEqual(saved["cleanup_trade_dates"], ["20260612"])
        self.assertFalse(report["side_effects"]["writes_database"])

    def test_execute_requires_confirm_token_before_deleter(self) -> None:
        calls: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            report = run_runtime_dirty_hot_keep2_cleanup_once(
                report_dir=Path(tmp) / "docs",
                execute=True,
                confirm_token="WRONG",
                trade_dates=["20260612", "20260701", "20260702"],
                table_counter=lambda _spec, _trade_date: 1,
                table_deleter=lambda spec, _trade_date: calls.append(spec.table) or 1,
            )

        self.assertEqual(report["result"], "BLOCKED_CONFIRM_TOKEN_REQUIRED")
        self.assertEqual(calls, [])
        self.assertFalse(report["cleanup_executed"])
        self.assertFalse(report["side_effects"]["writes_database"])

    def test_blocked_plan_not_pass_is_not_success_result(self) -> None:
        self.assertTrue(is_success_result("DIRTY_HOT_KEEP2_CLEANUP_PLAN_PASS"))
        self.assertTrue(is_success_result("DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS"))
        self.assertFalse(is_success_result("BLOCKED_PLAN_NOT_PASS"))

    def test_keep5_runner_requires_verified_archive_before_cleanup_plan_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=Path(tmp) / "docs",
                archive_root=Path(tmp) / "archive",
                trade_dates=["20260612", "20260615", "20260616", "20260617", "20260618", "20260619"],
                table_counter=lambda _spec, _trade_date: 1,
            )

            saved = json.loads(Path(report["docs_report_path"]).read_text(encoding="utf-8"))

        self.assertEqual(report["result"], "DIRTY_HOT_KEEP2_CLEANUP_PLAN_BLOCKED")
        self.assertTrue(report["archive_required"])
        self.assertEqual(report["retained_trade_dates"], ["20260615", "20260616", "20260617", "20260618", "20260619"])
        self.assertIn("archive_manifest_not_verified:20260612", report["blockers"])
        self.assertFalse(saved["side_effects"]["writes_database"])

    def test_keep5_direct_delete_no_archive_plan_skips_manifest_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=Path(tmp) / "docs",
                archive_root=Path(tmp) / "archive",
                direct_delete_no_archive=True,
                trade_dates=["20260612", "20260615", "20260616", "20260617", "20260618", "20260619"],
                table_counter=lambda _spec, trade_date: 1 if trade_date == "20260612" else 0,
                runtime_writer_process_detector=lambda: [],
                fk_closure_auditor=lambda **_kwargs: {
                    "missing_child_scope_count": 0,
                    "order_bad_count": 0,
                    "missing_child_scope": [],
                    "order_bad": [],
                },
            )

        self.assertEqual(report["result"], "DIRTY_HOT_KEEP2_CLEANUP_PLAN_PASS")
        self.assertFalse(report["archive_required"])
        self.assertTrue(report["direct_delete_no_archive"])
        self.assertEqual(report["confirm_token_required"], DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN)
        self.assertEqual(report["cleanup_trade_dates"], ["20260612"])

    def test_keep5_direct_delete_no_archive_execute_requires_direct_confirm_token(self) -> None:
        deleted: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=Path(tmp) / "docs",
                archive_root=Path(tmp) / "archive",
                direct_delete_no_archive=True,
                execute=True,
                confirm_token=KEEP5_CONFIRM_TOKEN,
                trade_dates=["20260612", "20260615", "20260616", "20260617", "20260618", "20260619"],
                table_counter=lambda _spec, trade_date: 1 if trade_date == "20260612" else 0,
                table_deleter=lambda spec, _trade_date: deleted.append(spec.table) or 1,
                runtime_writer_process_detector=lambda: [],
                fk_closure_auditor=lambda **_kwargs: {
                    "missing_child_scope_count": 0,
                    "order_bad_count": 0,
                    "missing_child_scope": [],
                    "order_bad": [],
                },
            )

        self.assertEqual(report["result"], "BLOCKED_CONFIRM_TOKEN_REQUIRED")
        self.assertEqual(deleted, [])
        self.assertFalse(report["cleanup_executed"])

    def test_keep5_direct_delete_no_archive_blocks_active_archive_process(self) -> None:
        counter_calls: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=Path(tmp) / "docs",
                archive_root=Path(tmp) / "archive",
                direct_delete_no_archive=True,
                trade_dates=["20260612", "20260615", "20260616", "20260617", "20260618", "20260619"],
                table_counter=lambda spec, trade_date: counter_calls.append(f"{trade_date}:{spec.table}") or 1,
                archive_process_detector=lambda: [{"pid": 60731, "command": "run_v3_runtime_archive_keep5_daily_once.py"}],
                runtime_writer_process_detector=lambda: [],
                fk_closure_auditor=lambda **_kwargs: {
                    "missing_child_scope_count": 0,
                    "order_bad_count": 0,
                    "missing_child_scope": [],
                    "order_bad": [],
                },
            )

        self.assertEqual(report["result"], "DIRTY_HOT_KEEP2_CLEANUP_PLAN_BLOCKED")
        self.assertIn("archive_process_conflict", report["blockers"])
        self.assertEqual(counter_calls, [])

    def test_keep5_direct_delete_no_archive_blocks_active_runtime_writer_before_plan(self) -> None:
        counter_calls: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=Path(tmp) / "docs",
                archive_root=Path(tmp) / "archive",
                direct_delete_no_archive=True,
                trade_dates=["20260612", "20260615", "20260616", "20260617", "20260618", "20260619"],
                table_counter=lambda spec, trade_date: counter_calls.append(f"{trade_date}:{spec.table}") or 1,
                archive_process_detector=lambda: [],
                runtime_writer_process_detector=lambda: [{"pid": 60732, "command": "python3 scripts/run_n4_intraday_proof_discovery_poll_once.py"}],
                fk_closure_auditor=lambda **_kwargs: {
                    "missing_child_scope_count": 0,
                    "order_bad_count": 0,
                    "missing_child_scope": [],
                    "order_bad": [],
                },
            )

        self.assertEqual(report["result"], "BLOCKED_RUNTIME_WRITER_ACTIVE")
        self.assertEqual(report["active_runtime_writer_processes"][0]["pid"], 60732)
        self.assertEqual(counter_calls, [])
        self.assertFalse(report["cleanup_executed"])
        self.assertFalse(report["cleanup_success"])
        self.assertFalse(report["side_effects"]["writes_database"])

    def test_keep5_direct_delete_no_archive_can_skip_row_count_plan_for_fast_execute(self) -> None:
        counter_calls: list[str] = []
        deleted: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=Path(tmp) / "docs",
                archive_root=Path(tmp) / "archive",
                direct_delete_no_archive=True,
                skip_row_count_plan=True,
                execute=True,
                confirm_token=DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN,
                trade_dates=["20260612", "20260615", "20260616", "20260617", "20260618", "20260619"],
                table_counter=lambda spec, trade_date: counter_calls.append(f"{trade_date}:{spec.table}") or 1,
                table_deleter=lambda spec, _trade_date: deleted.append(spec.table) or 0,
                runtime_writer_process_detector=lambda: [],
                fk_closure_auditor=lambda **_kwargs: {
                    "missing_child_scope_count": 0,
                    "order_bad_count": 0,
                    "missing_child_scope": [],
                    "order_bad": [],
                },
            )

        self.assertEqual(report["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        self.assertEqual(counter_calls, [])
        self.assertTrue(deleted)
        self.assertTrue(report["row_count_plan_skipped"])

    def test_keep5_direct_delete_execute_report_contains_compact_table_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=Path(tmp) / "docs",
                archive_root=Path(tmp) / "archive",
                direct_delete_no_archive=True,
                skip_row_count_plan=True,
                execute=True,
                confirm_token=DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN,
                trade_dates=["20260612", "20260615", "20260616", "20260617", "20260618", "20260619"],
                archive_process_detector=lambda: [],
                runtime_writer_process_detector=lambda: [],
                table_deleter=lambda spec, _trade_date: 7 if spec.table == "common_market_data_run" else 0,
                fk_closure_auditor=lambda **_kwargs: {
                    "missing_child_scope_count": 0,
                    "order_bad_count": 0,
                    "missing_child_scope": [],
                    "order_bad": [],
                },
            )
            saved = json.loads(Path(report["docs_report_path"]).read_text(encoding="utf-8"))
            closeout = json.loads((Path(tmp) / "docs" / "keep5_cleanup_closeout.json").read_text(encoding="utf-8"))

        self.assertEqual(report["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        self.assertTrue(report["cleanup_success"])
        self.assertIn("started_at", report)
        self.assertIn("finished_at", report)
        self.assertGreaterEqual(report["duration_ms"], 0)
        summary = [row for row in report["deleted_table_summary"] if row["table"] == "common_market_data_run"]
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["trade_date_count"], 1)
        self.assertEqual(summary[0]["deleted_rows"], 7)
        self.assertEqual(report["deleted_table_summary_count"], len(report["deleted_table_summary"]))
        self.assertEqual(report["retained_trade_dates_after"], ["20260615", "20260616", "20260617", "20260618", "20260619"])
        self.assertEqual(report["current_hot_trade_dates_after"], ["20260615", "20260616", "20260617", "20260618", "20260619"])
        self.assertEqual(saved["deleted_table_summary"], report["deleted_table_summary"])
        self.assertEqual(closeout["deleted_table_summary"], report["deleted_table_summary"])


if __name__ == "__main__":
    unittest.main()
