from __future__ import annotations

import plistlib
import tempfile
import unittest
from pathlib import Path


COMMIT = "a" * 40
RELEASE = Path(
    "/Users/chuanfuchen/.local/share/ashare-v3/releases/trigger-status/"
    f"20260803_120000__{COMMIT}"
)
RUNTIME_ENV = Path(
    "/Users/chuanfuchen/.local/share/ashare-v3/runtime-envs/trigger-status/v1"
)
LINEAGE = Path(
    "/Users/chuanfuchen/Documents/A股监控系统v3/docs/runtime/"
    "current_intraday_worker_lineage.json"
)
STATE = Path("/Users/chuanfuchen/.local/state/ashare-v3/trigger-status")


class TriggerStatusLaunchdPlanTest(unittest.TestCase):
    def test_builds_two_ordered_30_second_oneshots(self) -> None:
        from scripts.plan_n5_n6_trigger_status_launchd import build_launchd_plan

        plan = build_launchd_plan(release_path=RELEASE, runtime_env_path=RUNTIME_ENV)
        self.assertEqual(plan["result"], "PLAN_ONLY_PASS")
        self.assertEqual(plan["activation_order"], ["n5", "n6"])
        self.assertEqual(
            [plan[key]["label"] for key in plan["activation_order"]],
            [
                "com.ashare-v3.n5.trigger-status-forward-v1",
                "com.ashare-v3.n6.trigger-status-projection-v1",
            ],
        )
        for key in plan["activation_order"]:
            plist = plan[key]["plist"]
            self.assertEqual(plist["StartInterval"], 30)
            self.assertFalse(plist["RunAtLoad"])
            self.assertFalse(plist["KeepAlive"])
            self.assertEqual(plist["WorkingDirectory"], str(STATE / "cwd"))
            self.assertNotIn("--dsn", plist["ProgramArguments"])
            self.assertIn("--execute", plist["ProgramArguments"])
            self.assertIn("--user-confirmed", plist["ProgramArguments"])
            self.assertNotIn("trigger_pct", " ".join(plist["ProgramArguments"]))
        self.assertIn(
            "run_n5_trigger_status_forward_current_once.py",
            plan["n5"]["plist"]["ProgramArguments"][1],
        )
        self.assertIn(
            "run_n6_trigger_status_projection_current_once.py",
            plan["n6"]["plist"]["ProgramArguments"][1],
        )
        self.assertEqual(
            plan["side_effects"],
            {
                "release_materialized": False,
                "launchd_mutated": False,
                "worker_started": False,
                "database_written": False,
                "service_rebound": False,
            },
        )

    def test_rejects_mutable_or_wrong_release_root(self) -> None:
        from scripts.plan_n5_n6_trigger_status_launchd import build_launchd_plan

        with self.assertRaisesRegex(ValueError, "fixed trigger-status release root"):
            build_launchd_plan(
                release_path=Path("/private/tmp") / RELEASE.name,
                runtime_env_path=RUNTIME_ENV,
            )
        with self.assertRaisesRegex(ValueError, "must end with"):
            build_launchd_plan(
                release_path=RELEASE.parent / "mutable-active",
                runtime_env_path=RUNTIME_ENV,
            )

    def test_materializes_two_valid_plists_without_runtime_effects(self) -> None:
        from scripts.plan_n5_n6_trigger_status_launchd import write_launchd_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            report = write_launchd_plan(
                output_dir=Path(tmpdir),
                release_path=RELEASE,
                runtime_env_path=RUNTIME_ENV,
            )
            for key in report["activation_order"]:
                path = Path(report[key]["plist_path"])
                self.assertTrue(path.is_file())
                self.assertEqual(plistlib.loads(path.read_bytes()), report[key]["plist"])


if __name__ == "__main__":
    unittest.main()
