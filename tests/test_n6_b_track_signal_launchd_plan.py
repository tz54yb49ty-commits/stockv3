import plistlib
import tempfile
import unittest
from pathlib import Path


class N6BTrackSignalLaunchdPlanTest(unittest.TestCase):
    def test_builds_safe_b_track_signal_poller_plist(self):
        from scripts.plan_n6_b_track_signal_projection_launchd import build_launchd_plan

        plan = build_launchd_plan(
            project_root=Path("/Users/chuanfuchen/Documents/A股监控系统v3"),
            python_executable="/Library/Frameworks/Python.framework/Versions/3.11/bin/python3",
        )

        self.assertEqual(plan["launchd_plist_keys"], ["n6_b_track_signal"])
        plist = plan["n6_b_track_signal"]["plist"]
        self.assertEqual(plist["Label"], "com.ashare-v3.n6.b-track-signal-poller")
        self.assertEqual(plist["StartInterval"], 3)
        self.assertFalse(plist["RunAtLoad"])
        self.assertFalse(plist["KeepAlive"])
        self.assertEqual(plist["EnvironmentVariables"]["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(plist["EnvironmentVariables"]["PYTHONPATH"], "src:scripts:.")
        self.assertNotIn("ASHARE_V3_POSTGRES_DSN", plist["EnvironmentVariables"])

        args = plist["ProgramArguments"]
        self.assertEqual(args[0], "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3")
        self.assertIn("scripts/run_n6_b_track_signal_projection_poller_once.py", args)
        self.assertIn("--lineage-config", args)
        self.assertIn("docs/runtime/current_intraday_worker_lineage.json", args)
        self.assertIn("--execute", args)
        self.assertIn("--user-confirmed", args)
        self.assertIn("--json-report-path", args)
        self.assertIn("tmp/N6_b_track_signal_projection_poller_launchd_report.json", args)
        joined = " ".join(args).lower()
        for forbidden in ("run_n3", "run_n4", "run_n5", "archive", "cleanup", "launchctl", "rollback"):
            self.assertNotIn(forbidden, joined)
        self.assertFalse(plan["side_effects"]["launchd_mutated"])
        self.assertFalse(plan["side_effects"]["worker_started"])
        self.assertFalse(plan["side_effects"]["writes_database"])

    def test_materialized_plist_is_valid(self):
        from scripts.plan_n6_b_track_signal_projection_launchd import write_launchd_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            report = write_launchd_plan(output_dir=Path(tmpdir))

            plist_path = Path(report["n6_b_track_signal"]["plist_path"])
            self.assertTrue(plist_path.exists())
            plist = plistlib.loads(plist_path.read_bytes())
            self.assertEqual(plist["Label"], "com.ashare-v3.n6.b-track-signal-poller")
