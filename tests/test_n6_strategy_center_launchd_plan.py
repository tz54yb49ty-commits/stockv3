from __future__ import annotations

import hashlib
import json
import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.plan_n6_strategy_center_launchd as planner_module
from scripts.plan_n6_strategy_center_launchd import (
    LABEL,
    MAX_RUNTIME_SECONDS,
    START_INTERVAL_SECONDS,
    _validate_immutable_release,
    build_launchd_plan,
    write_launchd_plan,
)


RELEASE_ID = "20260722_120000__" + "a" * 40
RELEASE_PATH = Path(
    "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track"
) / RELEASE_ID
RUNTIME_ENV_PATH = Path(
    "/Users/chuanfuchen/.local/share/ashare-v3/runtime-envs/n6-b-track/"
    "n6-strategy-center-auto-v1-20260722"
)
STATE_ROOT = Path("/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track")
SERVICE_FILE = Path("/Users/chuanfuchen/.config/ashare-v3/postgresql/pg_service.conf")
PASS_FILE = Path(
    "/Users/chuanfuchen/.config/ashare-v3/postgresql/n6_strategy_worker.pgpass"
)


class N6StrategyCenterLaunchdPlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validation_patch = patch.object(
            planner_module,
            "_validate_immutable_release",
            return_value={
                "validation_path": "/fixed/release-validation.json",
                "manifest_path": "/fixed/git-ls-tree.nul",
                "manifest_sha256": "c" * 64,
                "commit": "a" * 40,
                "tree": "d" * 40,
                "file_count": 7,
            },
        )
        self.validation_patch.start()
        self.addCleanup(self.validation_patch.stop)

    def test_exact_nonresident_five_second_plist_and_environment(self) -> None:
        plan = build_launchd_plan(
            release_path=RELEASE_PATH,
            runtime_env_path=RUNTIME_ENV_PATH,
        )
        self.assertEqual(plan["result"], "PLAN_ONLY_PASS")
        self.assertEqual(plan["launchd_plist_keys"], ["strategy_center_evaluator"])
        plist = plan["strategy_center_evaluator"]["plist"]
        self.assertEqual(plist["Label"], LABEL)
        self.assertEqual(plist["StartInterval"], 5)
        self.assertEqual(plist["ThrottleInterval"], 5)
        self.assertEqual(plist["Umask"], 0o077)
        self.assertFalse(plist["RunAtLoad"])
        self.assertFalse(plist["KeepAlive"])
        self.assertEqual(plist["ProcessType"], "Background")
        self.assertNotIn("EnvironmentVariables", plist)
        self.assertEqual(plist["ProgramArguments"][:2], ["/usr/bin/env", "-i"])
        self.assertEqual(
            plist["ProgramArguments"][2:8],
            [
                f"PGPASSFILE={PASS_FILE}",
                "PGSERVICE=n6_strategy_worker",
                f"PGSERVICEFILE={SERVICE_FILE}",
                "PYTHONDONTWRITEBYTECODE=1",
                "PYTHONNOUSERSITE=1",
                "PYTHONPATH="
                + ":".join(
                    (
                        str(RELEASE_PATH / "src"),
                        str(RELEASE_PATH / "scripts"),
                        str(RELEASE_PATH),
                    )
                ),
            ],
        )
        joined = " ".join(plist["ProgramArguments"])
        for required in (
            "run_n6_strategy_center_auto_once.py",
            "--singleton-lock-path",
            "--json-report-path",
            "--history-path",
            "--release-id",
            "--signal-source-user-id 1",
            "--max-runtime-seconds 12",
            "--execute --runtime-authorized",
        ):
            self.assertIn(required, joined)
        self.assertEqual(MAX_RUNTIME_SECONDS, 12)
        self.assertEqual(START_INTERVAL_SECONDS, 5)
        max_runtime_index = plist["ProgramArguments"].index(
            "--max-runtime-seconds"
        )
        self.assertEqual(
            plist["ProgramArguments"][max_runtime_index + 1],
            "12",
        )
        for forbidden in (
            "--trade-date",
            "--evaluator-run-id",
            "--dsn",
            "PGPASSWORD",
            "DATABASE_URL",
            "run_n3",
            "run_n4",
            "run_n5",
            "proposal",
            "executor",
            "launchctl",
            "rollback",
        ):
            self.assertNotIn(forbidden, joined)
        self.assertEqual(
            plan["runtime_write_scope"],
            [
                "n6_user_strategy_selection_revision.replay_status",
                "n6_user_strategy_selection_revision.selection_status",
                "n6_user_strategy_selection_revision.activated_at",
                "n6_user_strategy_selection_revision.superseded_at",
                "n6_strategy_match_projection",
                "n6_strategy_match_change",
            ],
        )
        self.assertEqual(
            plan["immutable_release_attestation"]["commit"], "a" * 40
        )
        self.assertEqual(
            plan["hard_preconditions"]["strategy_state_directory_mode"],
            "0700",
        )
        self.assertFalse(
            plan["hard_preconditions"]["launchagent_install_authorized"]
        )
        self.assertFalse(any(plan["side_effects"].values()))

    def test_rejects_relative_or_mutable_release_paths(self) -> None:
        with self.assertRaisesRegex(ValueError, "release_path must be absolute"):
            build_launchd_plan(
                release_path=Path("relative"),
                runtime_env_path=RUNTIME_ENV_PATH,
            )
        with self.assertRaisesRegex(ValueError, "runtime_env_path must be absolute"):
            build_launchd_plan(
                release_path=RELEASE_PATH,
                runtime_env_path=Path("relative"),
            )
        with self.assertRaisesRegex(ValueError, "release_path must end"):
            build_launchd_plan(
                release_path=RELEASE_PATH.parent / "mutable-active",
                runtime_env_path=RUNTIME_ENV_PATH,
            )
        with self.assertRaisesRegex(ValueError, "pass_file must be absolute"):
            build_launchd_plan(
                release_path=RELEASE_PATH,
                runtime_env_path=RUNTIME_ENV_PATH,
                pass_file=Path("relative.pgpass"),
            )
        with self.assertRaisesRegex(ValueError, "state_root must equal fixed"):
            build_launchd_plan(
                release_path=RELEASE_PATH,
                runtime_env_path=RUNTIME_ENV_PATH,
                state_root=Path("/tmp/alternate-state"),
            )
        with self.assertRaisesRegex(ValueError, "service_file must equal fixed"):
            build_launchd_plan(
                release_path=RELEASE_PATH,
                runtime_env_path=RUNTIME_ENV_PATH,
                service_file=Path("/tmp/alternate-service.conf"),
            )

    def test_materialized_plist_round_trips_with_versioned_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = write_launchd_plan(
                output_dir=Path(directory),
                release_path=RELEASE_PATH,
                runtime_env_path=RUNTIME_ENV_PATH,
            )
            path = Path(report["strategy_center_evaluator"]["plist_path"])
            self.assertEqual(path.name, f"{RELEASE_ID}.{LABEL}.plist")
            self.assertEqual(
                plistlib.loads(path.read_bytes()),
                report["strategy_center_evaluator"]["plist"],
            )

    def test_immutable_release_requires_matching_validation_and_manifest(self) -> None:
        self.validation_patch.stop()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                release_root = root / "releases"
                manifest_root = root / "manifests"
                release_root.mkdir(mode=0o700)
                manifest_root.mkdir(mode=0o700)
                release = release_root / RELEASE_ID
                scripts_dir = release / "scripts"
                scripts_dir.mkdir(parents=True, mode=0o755)
                src_dir = release / "src"
                src_dir.mkdir(mode=0o755)
                runner = scripts_dir / "run_n6_strategy_center_auto_once.py"
                runner_bytes = b"print('ok')\n"
                runner.write_bytes(runner_bytes)
                authority = src_dir / "authority.py"
                authority_bytes = b"AUTHORITY = 'display-only'\n"
                authority.write_bytes(authority_bytes)
                runner_blob = hashlib.sha1(
                    f"blob {len(runner_bytes)}\0".encode("ascii") + runner_bytes
                ).hexdigest()
                authority_blob = hashlib.sha1(
                    f"blob {len(authority_bytes)}\0".encode("ascii")
                    + authority_bytes
                ).hexdigest()
                manifest = manifest_root / f"{RELEASE_ID}.git-ls-tree.nul"
                manifest_bytes = (
                    f"100644 blob {runner_blob}\t"
                    "scripts/run_n6_strategy_center_auto_once.py\0"
                    f"100644 blob {authority_blob}\tsrc/authority.py\0"
                ).encode("utf-8")
                manifest.write_bytes(manifest_bytes)
                validation_path = (
                    manifest_root / f"{RELEASE_ID}.release-validation.json"
                )
                validation = {
                    "status": "PASS",
                    "atomic_rename_completed": True,
                    "read_only": True,
                    "release_id": RELEASE_ID,
                    "final_path": str(release),
                    "commit": "a" * 40,
                    "tree": "b" * 40,
                    "missing_count": 0,
                    "extra_count": 0,
                    "symlink_count": 0,
                    "directory_count": 2,
                    "file_count": 2,
                    "git_mode_counts": {"100644": 2, "100755": 0},
                    "manifest_sha256": hashlib.sha256(
                        manifest.read_bytes()
                    ).hexdigest(),
                }
                validation_path.write_text(
                    json.dumps(validation), encoding="utf-8"
                )
                runner.chmod(0o444)
                authority.chmod(0o444)
                scripts_dir.chmod(0o555)
                src_dir.chmod(0o555)
                release.chmod(0o555)
                try:
                    with patch.object(
                        planner_module, "RELEASE_ROOT", release_root
                    ), patch.object(
                        planner_module, "MANIFEST_ROOT", manifest_root
                    ):
                        attestation = _validate_immutable_release(release)
                        self.assertEqual(attestation["tree"], "b" * 40)
                        self.assertEqual(
                            attestation["entity_validation"],
                            "file-set+git-blob-sha1+git-mode+read-only",
                        )

                        authority.chmod(0o644)
                        with self.assertRaisesRegex(
                            ValueError, "read-only/Git mode drift"
                        ):
                            _validate_immutable_release(release)
                        authority.chmod(0o444)

                        authority.chmod(0o644)
                        authority.write_bytes(b"tampered\n")
                        authority.chmod(0o444)
                        with self.assertRaisesRegex(
                            ValueError, "Git blob SHA-1 drift"
                        ):
                            _validate_immutable_release(release)
                        authority.chmod(0o644)
                        authority.write_bytes(authority_bytes)
                        authority.chmod(0o444)

                        release.chmod(0o755)
                        extra = release / "extra.py"
                        extra.write_text("extra\n", encoding="utf-8")
                        extra.chmod(0o444)
                        release.chmod(0o555)
                        with self.assertRaisesRegex(ValueError, "extra file"):
                            _validate_immutable_release(release)
                        release.chmod(0o755)
                        extra.unlink()
                        release.chmod(0o555)

                        src_dir.chmod(0o755)
                        authority.unlink()
                        src_dir.chmod(0o555)
                        with self.assertRaisesRegex(ValueError, "missing file"):
                            _validate_immutable_release(release)
                        src_dir.chmod(0o755)
                        authority.write_bytes(authority_bytes)
                        authority.chmod(0o444)
                        src_dir.chmod(0o555)

                        manifest.write_bytes(b"tampered")
                        with self.assertRaisesRegex(
                            ValueError, "manifest SHA256 mismatch"
                        ):
                            _validate_immutable_release(release)
                finally:
                    release.chmod(0o755)
                    scripts_dir.chmod(0o755)
                    src_dir.chmod(0o755)
                    runner.chmod(0o644)
                    if authority.exists():
                        authority.chmod(0o644)
        finally:
            self.validation_patch.start()


if __name__ == "__main__":
    unittest.main()
