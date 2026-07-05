import tempfile
import unittest
from pathlib import Path

from scripts.run_v3_runtime_archive_keep5_daily_once import (
    select_archive_trade_dates,
    run_v3_runtime_archive_keep5_daily_once,
)


class RuntimeArchiveKeep5DailyRunnerTest(unittest.TestCase):
    def test_select_archive_trade_dates_keeps_latest_five_trade_dates(self) -> None:
        selection = select_archive_trade_dates(
            ["20260612", "20260615", "20260616", "20260617", "20260618", "20260619", "20260622"],
            retention_trade_days=5,
        )

        self.assertEqual(selection["retained_trade_dates"], ["20260616", "20260617", "20260618", "20260619", "20260622"])
        self.assertEqual(selection["archive_trade_dates"], ["20260612", "20260615"])

    def test_plan_only_does_not_call_archive_runner(self) -> None:
        calls: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            report = run_v3_runtime_archive_keep5_daily_once(
                trade_dates=["20260612", "20260615", "20260616", "20260617", "20260618", "20260619"],
                report_dir=Path(tmp) / "docs",
                archive_runner=lambda **kwargs: calls.append(kwargs["trade_date"]) or {},
            )

        self.assertEqual(report["result"], "PLAN_ONLY")
        self.assertEqual(report["archive_trade_dates"], ["20260612"])
        self.assertEqual(calls, [])
        self.assertFalse(report["side_effects"]["writes_database"])

    def test_execute_runs_archive_for_only_non_retained_dates(self) -> None:
        calls: list[str] = []

        def runner(**kwargs) -> dict:
            calls.append(kwargs["trade_date"])
            return {
                "result": "EXECUTE_PASS",
                "archive_result": "ARCHIVED_VERIFIED",
                "trade_date": kwargs["trade_date"],
                "manifest_path": f"/archive/{kwargs['trade_date']}/archive_manifest.json",
                "row_count_match": True,
                "side_effects": {"writes_archive_files": True, "writes_database": False},
            }

        with tempfile.TemporaryDirectory() as tmp:
            report = run_v3_runtime_archive_keep5_daily_once(
                trade_dates=["20260612", "20260615", "20260616", "20260617", "20260618", "20260619"],
                report_dir=Path(tmp) / "docs",
                execute=True,
                user_confirmed=True,
                archive_runner=runner,
            )

        self.assertEqual(report["result"], "EXECUTE_PASS")
        self.assertEqual(calls, ["20260612"])
        self.assertEqual(report["retained_trade_dates"], ["20260615", "20260616", "20260617", "20260618", "20260619"])


if __name__ == "__main__":
    unittest.main()
