import plistlib
import tempfile
import unittest
from pathlib import Path

from scripts.plan_runtime_archive_cleanup_launchd import build_runtime_archive_cleanup_launchd_plan, materialize_plists
from ashare_v3.ingestion.runtime_hot_cleanup import DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN


class RuntimeArchiveCleanupLaunchdPlanTest(unittest.TestCase):
    def test_builds_cleanup_only_calendar_plist_for_daily_direct_delete(self) -> None:
        plan = build_runtime_archive_cleanup_launchd_plan(
            project_root=Path("/Users/chuanfuchen/Documents/A股监控系统v3"),
            python_executable="/usr/bin/python3",
        )

        self.assertEqual(plan["launchd_plist_keys"], ["cleanup"])
        self.assertNotIn("archive", plan)
        cleanup = plan["cleanup"]["plist"]
        self.assertEqual(cleanup["Label"], "com.ashare-v3.runtime-hot-cleanup-keep5-daily")
        self.assertEqual(cleanup["StartCalendarInterval"], {"Hour": 1, "Minute": 0})
        self.assertFalse(cleanup["RunAtLoad"])
        self.assertFalse(cleanup["KeepAlive"])
        argv = cleanup["ProgramArguments"]
        self.assertIn("scripts/run_runtime_hot_keep5_cleanup_once.py", argv)
        self.assertIn("--execute", argv)
        self.assertIn("--direct-delete-no-archive", argv)
        self.assertIn("--skip-row-count-plan", argv)
        self.assertIn("--confirm-token", argv)
        self.assertIn(DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN, argv)
        joined = " ".join(argv)
        self.assertNotIn("scripts/run_v3_runtime_archive_keep5_daily_once.py", joined)
        self.assertNotIn("sh -c", joined)
        self.assertNotIn("rm ", joined)
        self.assertNotIn("psql", joined)

    def test_materialized_plists_are_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = materialize_plists(
                output_dir=Path(tmp),
                project_root=Path("/Users/chuanfuchen/Documents/A股监控系统v3"),
                python_executable="/usr/bin/python3",
            )

            self.assertEqual(report["launchd_plist_keys"], ["cleanup"])
            for key in ("cleanup",):
                path = Path(report[key]["plist_path"])
                self.assertTrue(path.exists())
                plist = plistlib.loads(path.read_bytes())
                self.assertFalse(plist["RunAtLoad"])
                self.assertFalse(plist["KeepAlive"])


if __name__ == "__main__":
    unittest.main()
