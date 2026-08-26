import plistlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.run_runtime_hot_keep5_cleanup_once as keep5_runner
from scripts.plan_runtime_archive_cleanup_launchd import build_runtime_archive_cleanup_launchd_plan, materialize_plists


class RuntimeArchiveCleanupLaunchdPlanTest(unittest.TestCase):
    POINTER_PATH = "/Volumes/MacRaid/stock_db_archive/v3_runtime_artifacts/current_verified_batch.json"

    def test_builds_cleanup_only_calendar_plist_for_verified_archive_cleanup(self) -> None:
        plan = build_runtime_archive_cleanup_launchd_plan(
            project_root=Path("/Users/chuanfuchen/Documents/A股监控系统v3"),
            python_executable="/usr/bin/python3",
            local_archive_current_pointer_path=self.POINTER_PATH,
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
        self.assertEqual(plan["schema"], "RuntimeHotCleanupPlan.v2")
        self.assertEqual(plan["local_cleanup_policy"], "verified-archive-required")
        self.assertIn("--local-archive-current-pointer-path", argv)
        self.assertEqual(
            argv[argv.index("--local-archive-current-pointer-path") + 1],
            self.POINTER_PATH,
        )
        self.assertIn("--local-only", argv)
        self.assertNotIn("--local-archive-manifest-path", argv)
        self.assertNotIn("--local-archive-batch-summary-path", argv)
        self.assertNotIn("--local-archive-allowlist-path", argv)
        self.assertNotIn("--local-archive-restore-proof-path", argv)
        self.assertNotIn("--direct-delete-no-archive", argv)
        self.assertNotIn("--skip-row-count-plan", argv)
        self.assertNotIn("--confirm-token", argv)
        joined = " ".join(argv)
        self.assertNotIn("scripts/run_v3_runtime_archive_keep5_daily_once.py", joined)
        self.assertNotIn("sh -c", joined)
        self.assertNotIn("rm ", joined)
        self.assertNotIn("psql", joined)
        with patch.object(sys, "argv", ["runner", *argv[2:]]):
            parsed = keep5_runner.parse_args()
        self.assertEqual(parsed.local_archive_current_pointer_path, self.POINTER_PATH)
        self.assertTrue(parsed.local_only)

    def test_missing_verified_archive_evidence_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "local_archive_current_pointer_path is required"):
            build_runtime_archive_cleanup_launchd_plan()

    def test_materialized_plists_are_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = materialize_plists(
                output_dir=Path(tmp),
                project_root=Path("/Users/chuanfuchen/Documents/A股监控系统v3"),
                python_executable="/usr/bin/python3",
                local_archive_current_pointer_path=self.POINTER_PATH,
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
