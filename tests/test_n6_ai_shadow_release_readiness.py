import json
import os
from hashlib import sha256
from pathlib import Path
import plistlib
import stat
import tempfile
import unittest
from unittest import mock

from ashare_v3.user.ai_agent import AUTONOMOUS_FEATURE_FLAG
from ashare_v3.user.n6_ai_deepseek_adapter import (
    DEEPSEEK_API_KEY_FILE as FIXED_DEEPSEEK_API_KEY_FILE,
    DEEPSEEK_API_KEY_FILE_ENV,
    DEEPSEEK_EGRESS_MODE_ENV,
    DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
    DEEPSEEK_FINGERPRINT_PAUSE_FILE,
    DEEPSEEK_MODEL_PROVIDER,
    DEEPSEEK_MODEL_PROVIDER_ENV,
    DEEPSEEK_SYSTEM_FINGERPRINT_ENV,
    LEGACY_OPENAI_API_KEY_FILE_ENV,
)
import scripts.check_n6_ai_shadow_release_readiness as readiness_module
from scripts.check_n6_ai_shadow_release_readiness import (
    check_release_readiness,
    compute_immutable_tree_sha256,
)
import scripts.plan_n6_ai_shadow_launchd as launchd_module
from scripts.plan_n6_ai_shadow_launchd import (
    AGENT_LABEL,
    DAILY_SUMMARY_LABEL,
    PUBLIC_SNAPSHOT_LABEL,
    _build_isolated_program_arguments,
    _parse_isolated_program_arguments,
    write_launchd_plan,
)


COMMIT = "a" * 40
TREE = "b" * 40
RELEASE_ID = "20260718_130000__" + COMMIT
REVIEWED_SYSTEM_FINGERPRINT = "fp_reviewed_readiness_v1"


def _chmod_tree_readonly(root: Path) -> None:
    for current, directory_names, file_names in os.walk(root):
        for name in file_names:
            path = Path(current) / name
            path.chmod(0o555 if os.access(path, os.X_OK) else 0o444)
        for name in directory_names:
            (Path(current) / name).chmod(0o555)
    root.chmod(0o555)


def _agent_environment(payload):
    return _parse_isolated_program_arguments(
        payload["ProgramArguments"]
    )[0]


def _replace_agent_environment(payload, environment):
    _current_environment, command = (
        _parse_isolated_program_arguments(
            payload["ProgramArguments"]
        )
    )
    payload["ProgramArguments"] = (
        _build_isolated_program_arguments(environment, command)
    )


class ReadinessFixture:
    def __init__(self, root: Path) -> None:
        root = root.resolve()
        self.root = root
        self.release = root / "releases" / RELEASE_ID
        (self.release / "docs").mkdir(parents=True)
        (self.release / "scripts").mkdir()
        source_manifest = (
            Path(__file__).resolve().parents[1]
            / "docs/N6_AI_PRODUCTION_KNOWLEDGE_BUNDLE_MANIFEST_V1.json"
        )
        (self.release / source_manifest.relative_to(
            Path(__file__).resolve().parents[1]
        )).write_bytes(source_manifest.read_bytes())
        for name in (
            "run_n6_ai_agent_once.py",
            "run_n6_ai_strategy_policy_once.py",
            "run_n6_ai_daily_summary_once.py",
            "run_n6_ai_public_snapshot_once.py",
        ):
            (self.release / "scripts" / name).write_text(
                "#!/usr/bin/env python3\n",
                encoding="utf-8",
            )
        (self.release / ".git").write_text(
            "gitdir: /tmp/read-only-test-gitdir\n",
            encoding="utf-8",
        )

        self.runtime_env = root / "runtime-env"
        (self.runtime_env / "bin").mkdir(parents=True)
        self.python = self.runtime_env / "bin/python3.11"
        self.python.write_text("#!/bin/sh\n", encoding="utf-8")
        self.python.chmod(0o555)
        (self.runtime_env / "bin/python3").symlink_to("python3.11")
        (self.runtime_env / "empty-marker").write_bytes(b"")

        self.config = root / "config"
        (self.config / "postgresql").mkdir(parents=True)
        (self.config / "deepseek").mkdir()
        self.pg_service = self.config / "postgresql/pg_service.conf"
        self.pg_pass = self.config / "postgresql/n6_ai_agent.pgpass"
        self.api_key = (
            self.config / "deepseek/n6_ai_agent_api_key"
        )
        for path, payload in (
            (self.pg_service, b"[n6_ai_agent]\n"),
            (self.pg_pass, b"not-read-by-preflight\n"),
            (self.api_key, b"\xff\xfeopaque-key-metadata-only\n"),
        ):
            path.write_bytes(payload)
            path.chmod(0o600)

        self.state = root / "state"
        (self.state / "cwd").mkdir(parents=True)
        (self.state / "logs").mkdir()
        for path in (self.state, self.state / "cwd", self.state / "logs"):
            path.chmod(0o700)
        self.pause_file = (
            self.state / DEEPSEEK_FINGERPRINT_PAUSE_FILE.name
        )

        self.evidence = root / "evidence"
        with (
            mock.patch.object(
                launchd_module,
                "DEEPSEEK_API_KEY_FILE",
                self.api_key,
            ),
            mock.patch.object(
                launchd_module,
                "DEEPSEEK_FINGERPRINT_PAUSE_FILE",
                self.pause_file,
            ),
            mock.patch.object(
                launchd_module,
                "DEFAULT_STATE_ROOT",
                self.state,
            ),
        ):
            plan = write_launchd_plan(
                output_dir=self.evidence,
                release_path=self.release,
                runtime_env_path=self.runtime_env,
                pg_service_file=self.pg_service,
                pg_pass_file=self.pg_pass,
                deepseek_api_key_file=self.api_key,
                deepseek_system_fingerprint=(
                    REVIEWED_SYSTEM_FINGERPRINT
                ),
                state_root=self.state,
            )
        self.agent_plist = Path(plan["agent_shadow"]["plist_path"])
        self.launch_agents = root / "LaunchAgents"
        self.launch_agents.mkdir()
        self.launch_agents.chmod(0o700)
        self.preserved_public_snapshot_plist = (
            self.launch_agents
            / f"{PUBLIC_SNAPSHOT_LABEL}.plist"
        )
        self.public_snapshot_payload = {
            "Label": PUBLIC_SNAPSHOT_LABEL,
            "ProgramArguments": [
                str(self.python),
                str(
                    self.release
                    / "scripts/run_n6_ai_public_snapshot_once.py"
                ),
                "--execute",
            ],
            "WorkingDirectory": str(self.state / "cwd"),
            "EnvironmentVariables": {
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "PGSERVICE": "n6_ai_agent",
                "PGSERVICEFILE": str(self.pg_service),
                "PGPASSFILE": str(self.pg_pass),
                "ASHARE_V3_N6_AI_PUBLIC_SNAPSHOT_ENABLED": "1",
                "ASHARE_V3_N6_AI_PUBLIC_SNAPSHOT_FILE": str(
                    root / "public-snapshot.json"
                ),
            },
            "RunAtLoad": False,
            "KeepAlive": False,
            "StartInterval": 300,
            "ProcessType": "Background",
            "StandardOutPath": str(
                self.state
                / "logs"
                / f"{PUBLIC_SNAPSHOT_LABEL}.out.log"
            ),
            "StandardErrorPath": str(
                self.state
                / "logs"
                / f"{PUBLIC_SNAPSHOT_LABEL}.err.log"
            ),
        }
        with self.preserved_public_snapshot_plist.open(
            "xb"
        ) as file_handle:
            plistlib.dump(
                self.public_snapshot_payload,
                file_handle,
                sort_keys=True,
            )
        self.preserved_public_snapshot_plist.chmod(0o600)
        self.public_snapshot_sha256 = sha256(
            self.preserved_public_snapshot_plist.read_bytes()
        ).hexdigest()
        _chmod_tree_readonly(self.release)
        _chmod_tree_readonly(self.runtime_env)
        self.runtime_env_sha256 = compute_immutable_tree_sha256(
            self.runtime_env
        )

    def check(
        self,
        probe=None,
        *,
        preserved_public_snapshot_plist_path: Path | None = None,
        expected_public_snapshot_sha256: str | None = None,
        deepseek_api_key_file: Path | None = None,
        expected_deepseek_system_fingerprint: str = (
            REVIEWED_SYSTEM_FINGERPRINT
        ),
        pseudonymous_egress_authorized: bool = True,
    ):
        values = {
            "head": COMMIT,
            "tree": TREE,
            "status": "",
        }
        with (
            mock.patch.object(
                readiness_module,
                "DEEPSEEK_API_KEY_FILE",
                self.api_key,
            ),
            mock.patch.object(
                readiness_module,
                "DEEPSEEK_FINGERPRINT_PAUSE_FILE",
                self.pause_file,
            ),
            mock.patch.object(
                launchd_module,
                "DEEPSEEK_API_KEY_FILE",
                self.api_key,
            ),
            mock.patch.object(
                launchd_module,
                "DEEPSEEK_FINGERPRINT_PAUSE_FILE",
                self.pause_file,
            ),
            mock.patch.object(
                launchd_module,
                "DEFAULT_STATE_ROOT",
                self.state,
            ),
        ):
            return check_release_readiness(
                release_path=self.release,
                expected_commit=COMMIT,
                expected_tree=TREE,
                runtime_env_path=self.runtime_env,
                expected_runtime_env_sha256=self.runtime_env_sha256,
                pg_service_file=self.pg_service,
                pg_pass_file=self.pg_pass,
                deepseek_api_key_file=(
                    deepseek_api_key_file or self.api_key
                ),
                expected_deepseek_system_fingerprint=(
                    expected_deepseek_system_fingerprint
                ),
                pseudonymous_egress_authorized=(
                    pseudonymous_egress_authorized
                ),
                state_root=self.state,
                agent_plist_path=self.agent_plist,
                preserved_public_snapshot_plist_path=(
                    preserved_public_snapshot_plist_path
                    or self.preserved_public_snapshot_plist
                ),
                expected_preserved_public_snapshot_plist_sha256=(
                    expected_public_snapshot_sha256
                    or self.public_snapshot_sha256
                ),
                launch_agents_dir=self.launch_agents,
                git_probe=probe or (
                    lambda _release, operation: values[operation]
                ),
            )


class N6AIShadowReleaseReadinessTest(unittest.TestCase):
    def test_fixed_deepseek_paths_match_runtime_contract(self):
        self.assertEqual(
            FIXED_DEEPSEEK_API_KEY_FILE,
            Path(
                "/Users/chuanfuchen/.config/ashare-v3/deepseek/"
                "n6_ai_agent_api_key"
            ),
        )
        self.assertEqual(
            DEEPSEEK_FINGERPRINT_PAUSE_FILE,
            Path(
                "/Users/chuanfuchen/.local/state/ashare-v3/"
                "n6-ai-agent/deepseek_system_fingerprint.paused"
            ),
        )

    def test_ready_probe_is_read_only_and_does_not_parse_secrets(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReadinessFixture(Path(temporary))

            report = fixture.check()

            self.assertEqual(report["result"], "READY_READONLY")
            self.assertEqual(report["blockers"], [])
            self.assertEqual(
                report["checks"]["model_provider"],
                DEEPSEEK_MODEL_PROVIDER,
            )
            self.assertFalse(
                report["checks"]["legacy_openai_fallback_enabled"]
            )
            self.assertTrue(
                report["checks"]["system_ca_bundle_ready"]
            )
            self.assertTrue(
                report["checks"]["tls_environment_safe"]
            )
            self.assertTrue(
                report["checks"]["tls_context_prebuilt"]
            )
            self.assertTrue(
                report["checks"]["deepseek_api_key_path_exact"]
            )
            self.assertTrue(
                report["checks"][
                    "deepseek_fingerprint_pause_path_exact"
                ]
            )
            self.assertTrue(
                report["checks"][
                    "deepseek_fingerprint_pause_marker_absent"
                ]
            )
            self.assertFalse(report["checks"]["raw_n6_egress"])
            self.assertTrue(
                report["checks"]["pseudonymous_shadow"]
            )
            self.assertEqual(
                report["egress_contract"],
                {
                    "raw_n6_egress": False,
                    "pseudonymous_shadow": True,
                    "explicit_runtime_authorization_required": True,
                    "explicit_runtime_authorization_present": True,
                },
            )
            self.assertTrue(
                report["checks"][
                    "pseudonymous_egress_authorized"
                ]
            )
            self.assertEqual(
                report["checks"]["release_writable_entry_count"], 0
            )
            self.assertEqual(
                report["checks"]["release_unsafe_symlink_count"], 0
            )
            self.assertTrue(
                report["checks"]["agent_runner"]["ready"]
            )
            self.assertTrue(
                report["checks"]["strategy_policy_runner"]["ready"]
            )
            self.assertEqual(
                report["checks"]["runtime_env_sha256"],
                fixture.runtime_env_sha256,
            )
            self.assertEqual(
                report["checks"]["runtime_env_unsafe_symlink_count"],
                0,
            )
            self.assertEqual(
                report["checks"]["knowledge_bundle_sha256"],
                "1a873d69ef8f14e329b744460d549bcb3c35d99bb6af5fd10c16fc1a9dda15bc",
            )
            self.assertTrue(
                report["checks"]["production_agent_usable"]
            )
            self.assertFalse(
                report["checks"]["autonomous_trading_usable"]
            )
            self.assertNotIn(
                LEGACY_OPENAI_API_KEY_FILE_ENV,
                _agent_environment(
                    plistlib.loads(
                        fixture.agent_plist.read_bytes()
                    )
                ),
            )
            agent_payload = plistlib.loads(
                fixture.agent_plist.read_bytes()
            )
            self.assertNotIn(
                "EnvironmentVariables", agent_payload
            )
            agent_environment = _agent_environment(agent_payload)
            self.assertEqual(
                agent_environment[DEEPSEEK_MODEL_PROVIDER_ENV],
                DEEPSEEK_MODEL_PROVIDER,
            )
            self.assertEqual(
                agent_environment[DEEPSEEK_API_KEY_FILE_ENV],
                str(fixture.api_key),
            )
            self.assertEqual(
                agent_environment[DEEPSEEK_EGRESS_MODE_ENV],
                DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            )
            self.assertEqual(
                agent_environment[
                    DEEPSEEK_SYSTEM_FINGERPRINT_ENV
                ],
                REVIEWED_SYSTEM_FINGERPRINT,
            )
            self.assertNotIn(
                AUTONOMOUS_FEATURE_FLAG,
                agent_environment,
            )
            self.assertTrue(
                report["checks"][
                    "agent_plist_environment_variables_absent"
                ]
            )
            self.assertTrue(
                report["checks"][
                    "agent_plist_environment_isolated"
                ]
            )
            self.assertTrue(
                report["checks"][
                    "agent_plist_environment_allowlist_exact"
                ]
            )
            self.assertRegex(
                report["checks"]["agent_plist_sha256"],
                r"^[0-9a-f]{64}$",
            )
            self.assertEqual(
                report["checks"][
                    "preserved_public_snapshot_plist_sha256"
                ],
                fixture.public_snapshot_sha256,
            )
            self.assertTrue(
                report["checks"][
                    "preserved_public_snapshot_plist_exact"
                ]
            )
            self.assertTrue(
                report["side_effects"]["credential_contents_read"]
                is False
            )
            for name in (
                "database_connected",
                "database_written",
                "launchctl_called",
                "worker_started",
                "model_called",
                "network_called",
            ):
                self.assertFalse(report["side_effects"][name])

    def test_blocks_release_missing_agent_or_strategy_runner(self):
        for runner_name, blocker in (
            (
                "run_n6_ai_agent_once.py",
                "agent_runner_missing",
            ),
            (
                "run_n6_ai_strategy_policy_once.py",
                "strategy_policy_runner_missing",
            ),
        ):
            with self.subTest(runner_name=runner_name):
                with tempfile.TemporaryDirectory() as temporary:
                    fixture = ReadinessFixture(Path(temporary))
                    scripts_dir = fixture.release / "scripts"
                    scripts_dir.chmod(0o755)
                    (scripts_dir / runner_name).unlink()
                    scripts_dir.chmod(0o555)

                    report = fixture.check()

                    self.assertEqual(
                        report["result"], "BLOCKED_READONLY"
                    )
                    self.assertIn(blocker, report["blockers"])
                    self.assertFalse(
                        report["side_effects"]["database_connected"]
                    )
                    self.assertFalse(
                        report["side_effects"]["launchctl_called"]
                    )

    def test_pseudonymous_egress_requires_explicit_runtime_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReadinessFixture(Path(temporary))

            report = fixture.check(
                pseudonymous_egress_authorized=False
            )

            self.assertEqual(report["result"], "BLOCKED_READONLY")
            self.assertIn(
                "pseudonymous_egress_authorization_missing",
                report["blockers"],
            )
            self.assertFalse(
                report["checks"]["pseudonymous_egress_authorized"]
            )
            self.assertFalse(
                report["egress_contract"][
                    "explicit_runtime_authorization_present"
                ]
            )
            self.assertFalse(report["side_effects"]["network_called"])
            self.assertFalse(
                report["side_effects"]["database_connected"]
            )

    def test_readiness_never_opens_deepseek_key_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReadinessFixture(Path(temporary))
            secure_read = (
                readiness_module._read_regular_file_nofollow
            )

            def guarded_read(path, **kwargs):
                if Path(path) == fixture.api_key:
                    raise AssertionError(
                        "readiness must not open DeepSeek key content"
                    )
                return secure_read(path, **kwargs)

            with mock.patch.object(
                readiness_module,
                "_read_regular_file_nofollow",
                side_effect=guarded_read,
            ):
                report = fixture.check()

            self.assertEqual(report["result"], "READY_READONLY")
            self.assertFalse(
                report["side_effects"]["credential_contents_read"]
            )

    def test_blocks_dirty_writable_tampered_or_active_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReadinessFixture(Path(temporary))
            dirty = fixture.check(
                lambda _release, operation: (
                    " M scripts/run_n6_ai_agent_once.py"
                    if operation == "status"
                    else COMMIT if operation == "head" else TREE
                )
            )
            self.assertIn(
                "release_worktree_not_clean", dirty["blockers"]
            )

            target = fixture.release / "scripts/run_n6_ai_agent_once.py"
            target.chmod(0o644)
            writable = fixture.check()
            self.assertIn(
                "release_contains_writable_entries",
                writable["blockers"],
            )
            target.chmod(0o444)

            fixture.release.chmod(0o755)
            writable_root = fixture.check()
            self.assertIn("release_writable", writable_root["blockers"])
            fixture.release.chmod(0o555)

            fixture.runtime_env.chmod(0o755)
            writable_runtime_root = fixture.check()
            self.assertIn(
                "runtime_env_writable",
                writable_runtime_root["blockers"],
            )
            fixture.runtime_env.chmod(0o555)

            fixture.state.chmod(0o755)
            weak_state_root = fixture.check()
            self.assertIn(
                "state_root_mode_mismatch",
                weak_state_root["blockers"],
            )
            fixture.state.chmod(0o700)

            fixture.python.chmod(0o755)
            writable_python = fixture.check()
            self.assertIn(
                "runtime_python_writable",
                writable_python["blockers"],
            )
            self.assertIn(
                "runtime_env_contains_writable_entries",
                writable_python["blockers"],
            )
            fixture.python.chmod(0o555)

            fixture.api_key.chmod(0o644)
            weak_key = fixture.check()
            self.assertIn(
                "deepseek_api_key_file_mode_mismatch",
                weak_key["blockers"],
            )
            fixture.api_key.chmod(0o600)

            fixture.api_key.write_bytes(b"x" * 19)
            short_key = fixture.check()
            self.assertIn(
                "deepseek_api_key_file_size_invalid",
                short_key["blockers"],
            )
            fixture.api_key.write_bytes(b"x" * 513)
            long_key = fixture.check()
            self.assertIn(
                "deepseek_api_key_file_size_invalid",
                long_key["blockers"],
            )
            fixture.api_key.write_bytes(
                b"\xff\xfeopaque-key-metadata-only\n"
            )

            active = (
                fixture.launch_agents / f"{AGENT_LABEL}.plist"
            )
            active.write_bytes(fixture.agent_plist.read_bytes())
            active_state = fixture.check()
            self.assertIn(
                "ai_launchagent_plist_already_installed",
                active_state["blockers"],
            )

    def test_allows_exact_preserved_public_snapshot_and_blocks_drift(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReadinessFixture(Path(temporary))

            exact = fixture.check()

            self.assertEqual(exact["result"], "READY_READONLY")
            self.assertEqual(exact["blockers"], [])
            self.assertTrue(
                exact["checks"][
                    "preserved_public_snapshot_plist_exact"
                ]
            )
            payload = plistlib.loads(
                fixture.preserved_public_snapshot_plist.read_bytes()
            )
            payload["KeepAlive"] = True
            with fixture.preserved_public_snapshot_plist.open(
                "wb"
            ) as file_handle:
                plistlib.dump(payload, file_handle)
            fixture.preserved_public_snapshot_plist.chmod(0o600)

            drift = fixture.check()

            self.assertIn(
                "preserved_public_snapshot_sha256_mismatch",
                drift["blockers"],
            )
            self.assertIn(
                "preserved_public_snapshot_keep_alive_invalid",
                drift["blockers"],
            )

    def test_blocks_daily_summary_but_not_preserved_public_snapshot(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReadinessFixture(Path(temporary))
            baseline = fixture.check()
            self.assertEqual(baseline["result"], "READY_READONLY")

            daily = (
                fixture.launch_agents
                / f"{DAILY_SUMMARY_LABEL}.plist"
            )
            daily.write_bytes(b"installed")
            daily.chmod(0o600)

            report = fixture.check()

            self.assertIn(
                "ai_launchagent_plist_already_installed",
                report["blockers"],
            )
            self.assertEqual(
                report["checks"]["active_plist_conflicts"],
                [str(daily)],
            )

    def test_blocks_preserved_public_snapshot_path_hash_and_contract_drift(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReadinessFixture(Path(temporary))

            wrong_hash = fixture.check(
                expected_public_snapshot_sha256="0" * 64
            )
            self.assertIn(
                "preserved_public_snapshot_sha256_mismatch",
                wrong_hash["blockers"],
            )

            alternate = fixture.root / "alternate-public.plist"
            alternate.write_bytes(
                fixture.preserved_public_snapshot_plist.read_bytes()
            )
            alternate.chmod(0o600)
            wrong_path = fixture.check(
                preserved_public_snapshot_plist_path=alternate
            )
            self.assertIn(
                "preserved_public_snapshot_path_invalid",
                wrong_path["blockers"],
            )

            fixture.preserved_public_snapshot_plist.chmod(0o644)
            weak_mode = fixture.check()
            self.assertIn(
                "preserved_public_snapshot_plist_mode_mismatch",
                weak_mode["blockers"],
            )
            fixture.preserved_public_snapshot_plist.chmod(0o600)

            for key, value, blocker in (
                (
                    DEEPSEEK_MODEL_PROVIDER_ENV,
                    DEEPSEEK_MODEL_PROVIDER,
                    "preserved_public_snapshot_model_environment_present",
                ),
                (
                    AUTONOMOUS_FEATURE_FLAG,
                    "1",
                    "preserved_public_snapshot_model_environment_present",
                ),
                (
                    "PGPASSWORD",
                    "not-a-real-secret",
                    "preserved_public_snapshot_secret_present",
                ),
            ):
                with self.subTest(key=key):
                    payload = dict(fixture.public_snapshot_payload)
                    payload["EnvironmentVariables"] = dict(
                        payload["EnvironmentVariables"]
                    )
                    payload["EnvironmentVariables"][key] = value
                    with fixture.preserved_public_snapshot_plist.open(
                        "wb"
                    ) as file_handle:
                        plistlib.dump(payload, file_handle, sort_keys=True)
                    fixture.preserved_public_snapshot_plist.chmod(0o600)
                    current_sha = sha256(
                        fixture.preserved_public_snapshot_plist.read_bytes()
                    ).hexdigest()

                    report = fixture.check(
                        expected_public_snapshot_sha256=current_sha
                    )

                    self.assertIn(blocker, report["blockers"])

            payload = dict(fixture.public_snapshot_payload)
            payload["ProgramArguments"] = [
                str(fixture.python),
                str(
                    fixture.release
                    / "scripts/run_n6_ai_daily_summary_once.py"
                ),
                "--execute",
            ]
            with fixture.preserved_public_snapshot_plist.open(
                "wb"
            ) as file_handle:
                plistlib.dump(payload, file_handle, sort_keys=True)
            fixture.preserved_public_snapshot_plist.chmod(0o600)
            current_sha = sha256(
                fixture.preserved_public_snapshot_plist.read_bytes()
            ).hexdigest()

            wrong_runner = fixture.check(
                expected_public_snapshot_sha256=current_sha
            )

            self.assertIn(
                "preserved_public_snapshot_runner_invalid",
                wrong_runner["blockers"],
            )

            payload = dict(fixture.public_snapshot_payload)
            payload["ProgramArguments"] = [
                *payload["ProgramArguments"],
                "sk-not-a-real-secret-value",
            ]
            with fixture.preserved_public_snapshot_plist.open(
                "wb"
            ) as file_handle:
                plistlib.dump(payload, file_handle, sort_keys=True)
            fixture.preserved_public_snapshot_plist.chmod(0o600)
            current_sha = sha256(
                fixture.preserved_public_snapshot_plist.read_bytes()
            ).hexdigest()

            secret_argument = fixture.check(
                expected_public_snapshot_sha256=current_sha
            )

            self.assertIn(
                "preserved_public_snapshot_secret_present",
                secret_argument["blockers"],
            )

    def test_missing_deepseek_key_is_reported_without_throwing(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReadinessFixture(Path(temporary))
            fixture.api_key.unlink()

            report = fixture.check()

            self.assertEqual(report["result"], "BLOCKED_READONLY")
            self.assertIn(
                "deepseek_api_key_file_missing",
                report["blockers"],
            )
            self.assertFalse(
                report["checks"]["deepseek_api_key_file"]["ready"]
            )

    def test_ambient_tls_key_logging_blocks_readiness(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReadinessFixture(Path(temporary))
            with mock.patch.dict(
                os.environ,
                {"SSLKEYLOGFILE": "/tmp/forbidden-keylog"},
                clear=False,
            ):
                report = fixture.check()

            self.assertEqual(report["result"], "BLOCKED_READONLY")
            self.assertFalse(
                report["checks"]["tls_environment_safe"]
            )
            self.assertIn(
                "tls_environment_not_safe", report["blockers"]
            )

    def test_tls_context_must_prebuild_without_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReadinessFixture(Path(temporary))
            with mock.patch.object(
                readiness_module,
                "validate_tls_runtime",
                side_effect=ValueError("synthetic TLS failure"),
            ):
                report = fixture.check()

            self.assertEqual(report["result"], "BLOCKED_READONLY")
            self.assertFalse(
                report["checks"]["tls_context_prebuilt"]
            )
            self.assertIn(
                "tls_context_prebuild_failed", report["blockers"]
            )
            self.assertFalse(report["side_effects"]["network_called"])

    def test_blocks_fingerprint_pause_marker_and_api_key_path_drift(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReadinessFixture(Path(temporary))
            fixture.pause_file.write_text(
                "review required\n", encoding="utf-8"
            )
            fixture.pause_file.chmod(0o600)

            paused = fixture.check()

            self.assertIn(
                "deepseek_fingerprint_pause_marker_present",
                paused["blockers"],
            )
            fixture.pause_file.unlink()
            alternate_key = fixture.api_key.with_name(
                "alternate_n6_ai_agent_api_key"
            )
            alternate_key.write_bytes(b"x" * 35)
            alternate_key.chmod(0o600)

            wrong_key_path = fixture.check(
                deepseek_api_key_file=alternate_key
            )

            self.assertIn(
                "deepseek_api_key_path_invalid",
                wrong_key_path["blockers"],
            )

    def test_blocks_candidate_egress_fingerprint_key_and_autonomy_drift(
        self,
    ):
        mutations = (
            (
                DEEPSEEK_EGRESS_MODE_ENV,
                "synthetic_only",
                "agent_plist_egress_mode_invalid",
            ),
            (
                DEEPSEEK_SYSTEM_FINGERPRINT_ENV,
                "unsafe fingerprint value",
                "agent_plist_system_fingerprint_invalid",
            ),
            (
                DEEPSEEK_API_KEY_FILE_ENV,
                "/tmp/n6_ai_agent_api_key",
                "agent_plist_api_key_path_invalid",
            ),
            (
                AUTONOMOUS_FEATURE_FLAG,
                "1",
                "agent_plist_autonomous_present",
            ),
        )
        for key, value, blocker in mutations:
            with self.subTest(key=key):
                with tempfile.TemporaryDirectory() as temporary:
                    fixture = ReadinessFixture(Path(temporary))
                    payload = plistlib.loads(
                        fixture.agent_plist.read_bytes()
                    )
                    environment = _agent_environment(payload)
                    environment[key] = value
                    _replace_agent_environment(
                        payload, environment
                    )
                    with fixture.agent_plist.open(
                        "wb"
                    ) as file_handle:
                        plistlib.dump(
                            payload, file_handle, sort_keys=True
                        )
                    fixture.agent_plist.chmod(0o600)

                    report = fixture.check()

                    self.assertIn(blocker, report["blockers"])

    def test_blocks_missing_env_i_plist_environment_and_extra_env(self):
        mutation_cases = (
            "direct_python",
            "plist_environment",
            "owner_dsn",
            "http_proxy",
            "https_proxy_lower",
            "all_proxy",
        )
        for mutation in mutation_cases:
            with self.subTest(mutation=mutation):
                with tempfile.TemporaryDirectory() as temporary:
                    fixture = ReadinessFixture(Path(temporary))
                    payload = plistlib.loads(
                        fixture.agent_plist.read_bytes()
                    )
                    environment, command = (
                        _parse_isolated_program_arguments(
                            payload["ProgramArguments"]
                        )
                    )
                    expected_blocker = (
                        "agent_plist_environment_allowlist_invalid"
                    )
                    if mutation == "direct_python":
                        payload["ProgramArguments"] = command
                        expected_blocker = (
                            "agent_plist_environment_isolation_invalid"
                        )
                    elif mutation == "plist_environment":
                        payload["EnvironmentVariables"] = environment
                        expected_blocker = (
                            "agent_plist_environment_variables_present"
                        )
                    else:
                        extra_key = {
                            "owner_dsn": "ASHARE_V3_POSTGRES_DSN",
                            "http_proxy": "HTTP_PROXY",
                            "https_proxy_lower": "https_proxy",
                            "all_proxy": "ALL_PROXY",
                        }[mutation]
                        environment[extra_key] = (
                            "inherited-owner-value"
                        )
                        _replace_agent_environment(
                            payload, environment
                        )
                    with fixture.agent_plist.open(
                        "wb"
                    ) as file_handle:
                        plistlib.dump(
                            payload, file_handle, sort_keys=True
                        )
                    fixture.agent_plist.chmod(0o600)

                    report = fixture.check()

                    self.assertEqual(
                        report["result"], "BLOCKED_READONLY"
                    )
                    self.assertIn(
                        expected_blocker, report["blockers"]
                    )
                    self.assertIn(
                        "agent_plist_content_drift",
                        report["blockers"],
                    )

    def test_blocks_valid_candidate_fingerprint_that_differs_from_expected(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReadinessFixture(Path(temporary))

            report = fixture.check(
                expected_deepseek_system_fingerprint=(
                    "fp_independently_reviewed_v2"
                )
            )

            self.assertEqual(report["result"], "BLOCKED_READONLY")
            self.assertEqual(
                report["checks"][
                    "agent_plist_deepseek_system_fingerprint"
                ],
                "<invalid>",
            )
            self.assertEqual(
                report["checks"][
                    "expected_deepseek_system_fingerprint"
                ],
                "fp_independently_reviewed_v2",
            )
            self.assertIn(
                "agent_plist_system_fingerprint_mismatch",
                report["blockers"],
            )
            self.assertIn(
                "agent_plist_content_drift",
                report["blockers"],
            )

    def test_invalid_candidate_values_are_not_echoed_in_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReadinessFixture(Path(temporary))
            payload = plistlib.loads(fixture.agent_plist.read_bytes())
            injected_secret = "sk-sensitive-value-must-not-be-reported"
            environment = _agent_environment(payload)
            environment[DEEPSEEK_EGRESS_MODE_ENV] = injected_secret
            environment[DEEPSEEK_API_KEY_FILE_ENV] = injected_secret
            environment[DEEPSEEK_SYSTEM_FINGERPRINT_ENV] = (
                injected_secret
            )
            _replace_agent_environment(payload, environment)
            with fixture.agent_plist.open("wb") as file_handle:
                plistlib.dump(payload, file_handle, sort_keys=True)
            fixture.agent_plist.chmod(0o600)

            report = fixture.check()

            self.assertNotIn(
                injected_secret,
                json.dumps(report, sort_keys=True),
            )
            self.assertEqual(
                report["checks"]["agent_plist_deepseek_egress_mode"],
                "<invalid>",
            )
            self.assertEqual(
                report["checks"]["agent_plist_deepseek_api_key_path"],
                "<invalid>",
            )
            self.assertEqual(
                report["checks"][
                    "agent_plist_deepseek_system_fingerprint"
                ],
                "<invalid>",
            )

    def test_blocks_invalid_independent_expected_fingerprint(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReadinessFixture(Path(temporary))

            report = fixture.check(
                expected_deepseek_system_fingerprint=(
                    "unsafe expected fingerprint"
                )
            )

            self.assertEqual(report["result"], "BLOCKED_READONLY")
            self.assertEqual(
                report["checks"][
                    "expected_deepseek_system_fingerprint"
                ],
                "<invalid>",
            )
            self.assertIn(
                "expected_deepseek_system_fingerprint_invalid",
                report["blockers"],
            )

    def test_blocks_candidate_plist_drift_and_extra_plist(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReadinessFixture(Path(temporary))
            payload = plistlib.loads(fixture.agent_plist.read_bytes())
            payload["KeepAlive"] = True
            fixture.agent_plist.chmod(0o600)
            with fixture.agent_plist.open("wb") as file_handle:
                plistlib.dump(payload, file_handle)
            fixture.agent_plist.chmod(0o600)

            drift = fixture.check()

            self.assertIn(
                "agent_plist_content_drift", drift["blockers"]
            )
            extra = fixture.evidence / "unreviewed.plist"
            extra.write_bytes(b"not a plist")
            extra.chmod(0o600)
            extra_state = fixture.check()
            self.assertIn(
                "candidate_evidence_contains_extra_entries",
                extra_state["blockers"],
            )

    def test_blocks_manifest_tamper_and_external_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReadinessFixture(Path(temporary))
            manifest = (
                fixture.release
                / "docs/N6_AI_PRODUCTION_KNOWLEDGE_BUNDLE_MANIFEST_V1.json"
            )
            manifest.chmod(0o644)
            manifest.write_bytes(manifest.read_bytes() + b"\n")
            manifest.chmod(0o444)
            tampered = fixture.check()
            self.assertIn(
                "production_manifest_sha_mismatch",
                tampered["blockers"],
            )

        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReadinessFixture(Path(temporary))
            link = fixture.release / "external"
            fixture.release.chmod(0o755)
            link.symlink_to("/tmp")
            fixture.release.chmod(0o555)
            external = fixture.check()
            self.assertIn(
                "release_contains_external_symlink",
                external["blockers"],
            )

    def test_rejects_relative_paths_before_probing(self):
        with self.assertRaisesRegex(
            ValueError, "release_path must be absolute"
        ):
            check_release_readiness(
                release_path=Path("relative"),
                expected_commit=COMMIT,
                expected_tree=TREE,
                runtime_env_path=Path("/tmp/runtime"),
                expected_runtime_env_sha256="c" * 64,
                pg_service_file=Path("/tmp/pg_service.conf"),
                pg_pass_file=Path("/tmp/n6_ai_agent.pgpass"),
                deepseek_api_key_file=Path(
                    "/tmp/n6_ai_agent_api_key"
                ),
                expected_deepseek_system_fingerprint=(
                    REVIEWED_SYSTEM_FINGERPRINT
                ),
                pseudonymous_egress_authorized=True,
                state_root=Path("/tmp/state"),
                agent_plist_path=Path("/tmp/agent.plist"),
                preserved_public_snapshot_plist_path=Path(
                    "/tmp/public-snapshot.plist"
                ),
                expected_preserved_public_snapshot_plist_sha256=(
                    "d" * 64
                ),
                launch_agents_dir=Path("/tmp/LaunchAgents"),
            )

    def test_rejects_symlink_ancestor_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReadinessFixture(Path(temporary))
            alias = fixture.root / "release-alias"
            alias.symlink_to(
                fixture.release.parent, target_is_directory=True
            )
            with self.assertRaisesRegex(
                ValueError, "canonical and contain no symlink ancestors"
            ):
                check_release_readiness(
                    release_path=alias / RELEASE_ID,
                    expected_commit=COMMIT,
                    expected_tree=TREE,
                    runtime_env_path=fixture.runtime_env,
                    expected_runtime_env_sha256=(
                        fixture.runtime_env_sha256
                    ),
                    pg_service_file=fixture.pg_service,
                    pg_pass_file=fixture.pg_pass,
                    deepseek_api_key_file=fixture.api_key,
                    expected_deepseek_system_fingerprint=(
                        REVIEWED_SYSTEM_FINGERPRINT
                    ),
                    pseudonymous_egress_authorized=True,
                    state_root=fixture.state,
                    agent_plist_path=fixture.agent_plist,
                    preserved_public_snapshot_plist_path=(
                        fixture.preserved_public_snapshot_plist
                    ),
                    expected_preserved_public_snapshot_plist_sha256=(
                        fixture.public_snapshot_sha256
                    ),
                    launch_agents_dir=fixture.launch_agents,
                )

    def test_tree_hash_has_unambiguous_entry_boundaries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            tree_a = root / "tree-a"
            tree_b = root / "tree-b"
            tree_a.mkdir()
            tree_b.mkdir()
            (tree_a / "a").write_bytes(
                b"x\x00b\x00444\x00file\x00y"
            )
            (tree_b / "a").write_bytes(b"x")
            (tree_b / "b").write_bytes(b"y")
            _chmod_tree_readonly(tree_a)
            _chmod_tree_readonly(tree_b)

            hash_a = compute_immutable_tree_sha256(tree_a)
            hash_b = compute_immutable_tree_sha256(tree_b)

            self.assertNotEqual(hash_a, hash_b)


if __name__ == "__main__":
    unittest.main()
