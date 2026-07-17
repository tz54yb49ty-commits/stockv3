import plistlib
import tempfile
import unittest
from pathlib import Path


RELEASE_ID = "20260716_103000__" + "a" * 40
RELEASE_PATH = Path("/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track") / RELEASE_ID
RUNTIME_ENV_PATH = Path(
    "/Users/chuanfuchen/.local/share/ashare-v3/runtime-envs/n6-b-track/"
    "n6-b-track-bounded-canary-dual-lock-cas-fix-forward-v4-20260716"
)
LINEAGE_PATH = Path(
    "/Users/chuanfuchen/Documents/A股监控系统v3/docs/runtime/current_intraday_worker_lineage.json"
)
STATE_ROOT = Path("/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track")


class N6BTrackSignalLaunchdPlanTest(unittest.TestCase):
    def test_builds_immutable_batch_oneshot_plist(self):
        from scripts.plan_n6_b_track_signal_projection_launchd import build_launchd_plan

        plan = build_launchd_plan(
            release_path=RELEASE_PATH,
            runtime_env_path=RUNTIME_ENV_PATH,
        )

        self.assertEqual(plan["release_id"], RELEASE_ID)
        self.assertEqual(plan["launchd_plist_keys"], ["n6_b_track_signal"])
        plist = plan["n6_b_track_signal"]["plist"]
        self.assertEqual(plist["Label"], "com.ashare-v3.n6.b-track-signal-projection-batch-v1")
        self.assertEqual(plist["WorkingDirectory"], str(STATE_ROOT / "cwd"))
        self.assertEqual(plist["StartInterval"], 3)
        self.assertFalse(plist["RunAtLoad"])
        self.assertFalse(plist["KeepAlive"])
        self.assertEqual(
            plist["EnvironmentVariables"],
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "PYTHONPATH": ":".join(
                    (str(RELEASE_PATH / "src"), str(RELEASE_PATH / "scripts"), str(RELEASE_PATH))
                ),
            },
        )

        args = plist["ProgramArguments"]
        self.assertEqual(
            args,
            [
                str(RUNTIME_ENV_PATH / "bin/python3.11"),
                str(RELEASE_PATH / "scripts/run_n6_b_track_signal_projection_poller_once.py"),
                "--lineage-config",
                str(LINEAGE_PATH),
                "--consumer-name",
                "n6_b_track_signal_projection_poller_v1",
                "--max-events",
                "100",
                "--singleton-lock-path",
                str(STATE_ROOT / "locks/n6_b_track_signal_projection_poller.lock"),
                "--cas-authority-mode",
                "internal_one_shot",
                "--execute",
                "--user-confirmed",
                "--json-report-path",
                str(STATE_ROOT / "reports/N6_b_track_signal_projection_batch_v1_report.json"),
                "--history-path",
                str(STATE_ROOT / "history/N6_b_track_signal_projection_batch_v1_history.jsonl"),
            ],
        )
        joined = " ".join(args)
        for forbidden in (
            "--dsn",
            "--for-trade-date",
            "--historical-backfill",
            "external_bounded_canary",
            "scripts/run_n3",
            "scripts/run_n4",
            "scripts/run_n5",
        ):
            self.assertNotIn(forbidden, joined)
        self.assertFalse(plan["side_effects"]["launchd_mutated"])
        self.assertFalse(plan["side_effects"]["worker_started"])
        self.assertFalse(plan["side_effects"]["writes_database"])

    def test_rejects_relative_or_unversioned_runtime_paths(self):
        from scripts.plan_n6_b_track_signal_projection_launchd import build_launchd_plan

        with self.assertRaisesRegex(ValueError, "release_path must be absolute"):
            build_launchd_plan(release_path=Path("relative"), runtime_env_path=RUNTIME_ENV_PATH)
        with self.assertRaisesRegex(ValueError, "runtime_env_path must be absolute"):
            build_launchd_plan(release_path=RELEASE_PATH, runtime_env_path=Path("relative"))
        with self.assertRaisesRegex(ValueError, "release_path must end"):
            build_launchd_plan(
                release_path=RELEASE_PATH.parent / "mutable-active",
                runtime_env_path=RUNTIME_ENV_PATH,
            )

    def test_materialized_plist_is_valid_and_versioned(self):
        from scripts.plan_n6_b_track_signal_projection_launchd import write_launchd_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            report = write_launchd_plan(
                output_dir=Path(tmpdir),
                release_path=RELEASE_PATH,
                runtime_env_path=RUNTIME_ENV_PATH,
            )

            plist_path = Path(report["n6_b_track_signal"]["plist_path"])
            self.assertEqual(
                plist_path.name,
                f"{RELEASE_ID}.com.ashare-v3.n6.b-track-signal-projection-batch-v1.plist",
            )
            plist = plistlib.loads(plist_path.read_bytes())
            self.assertEqual(plist, report["n6_b_track_signal"]["plist"])
            self.assertEqual(plist["Label"], "com.ashare-v3.n6.b-track-signal-projection-batch-v1")


if __name__ == "__main__":
    unittest.main()
