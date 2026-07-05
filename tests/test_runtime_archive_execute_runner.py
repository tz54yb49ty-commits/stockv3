import json
from pathlib import Path
import tempfile
import unittest

from scripts.run_v3_runtime_archive_once import run_v3_runtime_archive_once


class RuntimeArchiveExecuteRunnerTest(unittest.TestCase):
    def test_default_plan_only_does_not_call_archive_executor(self) -> None:
        calls: list[dict] = []
        with tempfile.TemporaryDirectory() as tmp:
            report = run_v3_runtime_archive_once(
                trade_date="20260612",
                archive_root=Path(tmp) / "archive",
                report_dir=Path(tmp) / "docs",
                archive_executor=lambda **kwargs: calls.append(kwargs) or {},
            )

            self.assertEqual(report["result"], "PLAN_ONLY")
            self.assertEqual(calls, [])
            self.assertFalse(report["side_effects"]["writes_archive_files"])
            self.assertFalse(report["side_effects"]["writes_database"])
            self.assertTrue(Path(report["docs_report_path"]).exists())

    def test_execute_requires_user_confirmed_before_archive_executor(self) -> None:
        calls: list[dict] = []
        with tempfile.TemporaryDirectory() as tmp:
            report = run_v3_runtime_archive_once(
                trade_date="20260612",
                archive_root=Path(tmp) / "archive",
                report_dir=Path(tmp) / "docs",
                execute=True,
                user_confirmed=False,
                archive_executor=lambda **kwargs: calls.append(kwargs) or {},
            )

            self.assertEqual(report["result"], "BLOCKED")
            self.assertEqual(report["blocked_reason"], "missing_user_confirmed_flag")
            self.assertEqual(calls, [])

    def test_user_confirmed_requires_execute_before_archive_executor(self) -> None:
        calls: list[dict] = []
        with tempfile.TemporaryDirectory() as tmp:
            report = run_v3_runtime_archive_once(
                trade_date="20260612",
                archive_root=Path(tmp) / "archive",
                report_dir=Path(tmp) / "docs",
                execute=False,
                user_confirmed=True,
                archive_executor=lambda **kwargs: calls.append(kwargs) or {},
            )

            self.assertEqual(report["result"], "BLOCKED")
            self.assertEqual(report["blocked_reason"], "missing_execute_flag")
            self.assertEqual(calls, [])

    def test_execute_writes_docs_status_from_archive_manifest(self) -> None:
        calls: list[dict] = []

        def executor(**kwargs) -> dict:
            calls.append(kwargs)
            return {
                "result": "ARCHIVED_VERIFIED",
                "manifest_path": "/tmp/archive_manifest.json",
                "report_path": "/tmp/archive_report.json",
                "file_count": 2,
                "total_rows": 3,
                "row_count_match": True,
                "cleanup_eligible": False,
                "cleanup_blockers": ["manual_cleanup_required"],
            }

        with tempfile.TemporaryDirectory() as tmp:
            report = run_v3_runtime_archive_once(
                trade_date="20260612",
                archive_root=Path(tmp) / "archive",
                report_dir=Path(tmp) / "docs",
                execute=True,
                user_confirmed=True,
                archive_executor=executor,
            )

            self.assertEqual(report["result"], "EXECUTE_PASS")
            self.assertEqual(len(calls), 1)
            self.assertTrue(report["side_effects"]["writes_archive_files"])
            self.assertFalse(report["side_effects"]["writes_database"])
            saved = json.loads(Path(report["docs_report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(saved["manifest_path"], "/tmp/archive_manifest.json")
            self.assertEqual(saved["total_rows"], 3)

    def test_execute_treats_existing_verified_archive_as_pass_without_writes(self) -> None:
        def executor(**kwargs) -> dict:
            return {
                "result": "IDEMPOTENT_ARCHIVE_ALREADY_VERIFIED",
                "manifest_path": "/tmp/archive_manifest.json",
                "report_path": "/tmp/archive_report.json",
                "file_count": 2,
                "total_rows": 3,
                "row_count_match": True,
                "cleanup_eligible": False,
                "cleanup_blockers": ["manual_cleanup_required"],
                "side_effects": {
                    "writes_archive_files": False,
                    "writes_database": False,
                    "cleanup_local_runtime": False,
                },
            }

        with tempfile.TemporaryDirectory() as tmp:
            report = run_v3_runtime_archive_once(
                trade_date="20260612",
                archive_root=Path(tmp) / "archive",
                report_dir=Path(tmp) / "docs",
                execute=True,
                user_confirmed=True,
                archive_executor=executor,
            )

            self.assertEqual(report["result"], "EXECUTE_PASS")
            self.assertEqual(report["reason"], "archive_already_verified")
            self.assertEqual(report["archive_result"], "IDEMPOTENT_ARCHIVE_ALREADY_VERIFIED")
            self.assertFalse(report["side_effects"]["writes_archive_files"])
            self.assertFalse(report["side_effects"]["writes_database"])

    def test_execute_status_includes_table_timing_summary(self) -> None:
        def executor(**kwargs) -> dict:
            return {
                "result": "ARCHIVED_VERIFIED",
                "manifest_path": "/tmp/archive_manifest.json",
                "report_path": "/tmp/archive_report.json",
                "file_count": 1,
                "total_rows": 2,
                "row_count_match": True,
                "cleanup_eligible": False,
                "cleanup_blockers": ["manual_cleanup_required"],
                "table_timings": [
                    {
                        "layer": "n3",
                        "table": "stock_action_confirmation_projection_metric",
                        "status": "passed",
                        "read_duration_ms": 12.0,
                        "write_duration_ms": 3.0,
                        "row_count": 2,
                        "verified_row_count": 2,
                    }
                ],
            }

        with tempfile.TemporaryDirectory() as tmp:
            report = run_v3_runtime_archive_once(
                trade_date="20260612",
                archive_root=Path(tmp) / "archive",
                report_dir=Path(tmp) / "docs",
                execute=True,
                user_confirmed=True,
                archive_executor=executor,
            )

            self.assertEqual(report["result"], "EXECUTE_PASS")
            self.assertEqual(report["table_timing_summary"][0]["table"], "stock_action_confirmation_projection_metric")
            saved = json.loads(Path(report["docs_report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(saved["table_timing_summary"][0]["read_duration_ms"], 12.0)


if __name__ == "__main__":
    unittest.main()
