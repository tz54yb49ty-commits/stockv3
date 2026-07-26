import copy
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ashare_v3.user.ai_agent import (
    AUTONOMOUS_FEATURE_FLAG,
    CONTEXT_KNOWLEDGE_BUNDLE_SHA256,
    MAX_CONTEXT_SIGNALS,
    PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV,
    PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256,
    PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV,
    SHADOW_FEATURE_FLAG,
)
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
from scripts.plan_n6_ai_shadow_launchd import (
    AGENT_LABEL,
    AGENT_START_CALENDAR_INTERVALS,
    STRATEGY_POLICY_LABEL,
    STRATEGY_POLICY_START_INTERVAL_SECONDS,
    _AGENT_ENV_KEYS,
    _STRATEGY_POLICY_ENV_KEYS,
    _build_isolated_program_arguments,
    _parse_isolated_program_arguments,
    _assert_plist_safe,
    _assert_program_arguments_safe,
    build_launchd_plan,
    main,
    write_launchd_plan,
)
from scripts.run_n6_ai_strategy_policy_once import (
    STRATEGY_POLICY_SHADOW_FEATURE_FLAG,
)


RELEASE_ID = "20260718_120000__" + "a" * 40
RELEASE_PATH = (
    Path("/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-ai")
    / RELEASE_ID
)
RUNTIME_ENV_PATH = Path(
    "/Users/chuanfuchen/.local/share/ashare-v3/runtime-envs/"
    "n6-ai/n6-ai-shadow-v1-20260718"
)
REVIEWED_RUNTIME_ENV_PATH = Path(
    "/Users/chuanfuchen/.local/share/ashare-v3/runtime-envs/"
    "n6-b-track/"
    "n6-b-track-bounded-canary-dual-lock-cas-fix-forward-v4-20260716"
)
CANDIDATE_RUNTIME_ENV_PATH = Path(
    "/Users/chuanfuchen/.local/share/ashare-v3/runtime-envs/"
    "n6-b-track/n6-b-track-candidate-v1-20260718"
)
CONFIG_ROOT = Path("/Users/chuanfuchen/.config/ashare-v3")
PG_SERVICE_FILE = CONFIG_ROOT / "postgresql/pg_service.conf"
PG_PASS_FILE = CONFIG_ROOT / "postgresql/n6_ai_agent.pgpass"
DEEPSEEK_API_KEY_FILE = (
    CONFIG_ROOT / "deepseek/n6_ai_agent_api_key"
)
DEEPSEEK_SYSTEM_FINGERPRINT = "fp_reviewed_test_v1"
STATE_ROOT = Path(
    "/Users/chuanfuchen/.local/state/ashare-v3/n6-ai-agent"
)


def plan():
    return build_launchd_plan(
        release_path=RELEASE_PATH,
        runtime_env_path=RUNTIME_ENV_PATH,
        pg_service_file=PG_SERVICE_FILE,
        pg_pass_file=PG_PASS_FILE,
        deepseek_api_key_file=DEEPSEEK_API_KEY_FILE,
        deepseek_system_fingerprint=DEEPSEEK_SYSTEM_FINGERPRINT,
        state_root=STATE_ROOT,
    )


def isolated_environment(plist):
    return _parse_isolated_program_arguments(
        plist["ProgramArguments"]
    )[0]


def isolated_command(plist):
    return _parse_isolated_program_arguments(
        plist["ProgramArguments"]
    )[1]


def replace_isolated_environment(plist, environment):
    _current_environment, command = _parse_isolated_program_arguments(
        plist["ProgramArguments"]
    )
    plist["ProgramArguments"] = _build_isolated_program_arguments(
        environment,
        command,
    )


class N6AIShadowLaunchdPlanTest(unittest.TestCase):
    def assert_agent_plist_rejected(
        self,
        plist,
        expected_message,
    ):
        with self.assertRaisesRegex(ValueError, expected_message):
            _assert_plist_safe(
                plist,
                expected_label=AGENT_LABEL,
                expected_env_keys=_AGENT_ENV_KEYS,
                release_path=RELEASE_PATH,
                runtime_env_path=RUNTIME_ENV_PATH,
                state_root=STATE_ROOT,
                expected_schedule={
                    "StartCalendarInterval":
                        AGENT_START_CALENDAR_INTERVALS,
                },
                required_feature_flags={
                    SHADOW_FEATURE_FLAG: "1",
                    DEEPSEEK_EGRESS_MODE_ENV:
                        DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
                    DEEPSEEK_SYSTEM_FINGERPRINT_ENV:
                        DEEPSEEK_SYSTEM_FINGERPRINT,
                },
            )

    def assert_strategy_plist_rejected(
        self,
        plist,
        expected_message,
    ):
        with self.assertRaisesRegex(ValueError, expected_message):
            _assert_plist_safe(
                plist,
                expected_label=STRATEGY_POLICY_LABEL,
                expected_env_keys=_STRATEGY_POLICY_ENV_KEYS,
                release_path=RELEASE_PATH,
                runtime_env_path=RUNTIME_ENV_PATH,
                state_root=STATE_ROOT,
                expected_schedule={
                    "StartInterval":
                        STRATEGY_POLICY_START_INTERVAL_SECONDS,
                },
                required_feature_flags={
                    STRATEGY_POLICY_SHADOW_FEATURE_FLAG: "1",
                },
            )

    def test_allows_reviewed_canary_and_candidate_runtime_env_paths(self):
        for runtime_env_path in (
            REVIEWED_RUNTIME_ENV_PATH,
            CANDIDATE_RUNTIME_ENV_PATH,
        ):
            with self.subTest(runtime_env_path=runtime_env_path):
                report = build_launchd_plan(
                    release_path=RELEASE_PATH,
                    runtime_env_path=runtime_env_path,
                    pg_service_file=PG_SERVICE_FILE,
                    pg_pass_file=PG_PASS_FILE,
                    deepseek_api_key_file=DEEPSEEK_API_KEY_FILE,
                    deepseek_system_fingerprint=
                        DEEPSEEK_SYSTEM_FINGERPRINT,
                    state_root=STATE_ROOT,
                )
                self.assertEqual(report["result"], "PLAN_ONLY_PASS")
                self.assertEqual(
                    isolated_command(
                        report["agent_shadow"]["plist"]
                    )[0],
                    str(runtime_env_path / "bin/python3.11"),
                )

    def test_program_argument_guard_rejects_control_tokens(self):
        unsafe_arguments = (
            ["python3.11", "runner.py", "-c", "pass"],
            ["/bin/sh", "runner.py"],
            ["python3.11", "launchctl"],
            ["python3.11", "broker"],
            ["python3.11", "runner.py", "--autonomous"],
            ["python3.11", "runner.py", "--dsn=postgresql://local"],
            ["python3.11", "runner.py", "--password", "secret"],
            ["python3.11", "runner.py;other.py"],
            ["python3.11", "runner.py\nother.py"],
        ) + tuple(
            ["python3.11", f"run_n{layer}_worker.py"]
            for layer in range(1, 6)
        )
        for arguments in unsafe_arguments:
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(
                    ValueError, "unsafe ProgramArguments"
                ):
                    _assert_program_arguments_safe(arguments)

    def test_builds_two_isolated_nonresident_shadow_plists(self):
        report = plan()

        self.assertEqual(report["result"], "PLAN_ONLY_PASS")
        self.assertEqual(report["release_id"], RELEASE_ID)
        self.assertEqual(
            report["launchd_plist_keys"],
            ["agent_shadow", "strategy_policy_shadow"],
        )
        self.assertEqual(
            report["knowledge_bundle_sha256"],
            CONTEXT_KNOWLEDGE_BUNDLE_SHA256,
        )
        self.assertEqual(
            report["manifest_file_sha256"],
            PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256,
        )
        self.assertFalse(
            report["runtime_contract"]["autonomous_enabled"]
        )
        self.assertEqual(
            report["runtime_contract"]["model_provider"],
            DEEPSEEK_MODEL_PROVIDER,
        )
        self.assertFalse(
            report["runtime_contract"]["raw_n6_egress"]
        )
        self.assertTrue(
            report["runtime_contract"]["pseudonymous_shadow"]
        )
        self.assertEqual(
            report["runtime_contract"]["deepseek_egress_mode"],
            DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
        )
        self.assertEqual(
            report["runtime_contract"][
                "reviewed_system_fingerprint"
            ],
            DEEPSEEK_SYSTEM_FINGERPRINT,
        )
        self.assertEqual(
            report["runtime_contract"]["fingerprint_pause_file"],
            str(DEEPSEEK_FINGERPRINT_PAUSE_FILE),
        )
        self.assertEqual(
            DEEPSEEK_FINGERPRINT_PAUSE_FILE,
            STATE_ROOT / "deepseek_system_fingerprint.paused",
        )
        self.assertFalse(
            report["runtime_contract"]["daily_summary_enabled"]
        )
        self.assertFalse(
            report["runtime_contract"]["public_snapshot_managed"]
        )
        self.assertTrue(
            report["runtime_contract"][
                "strategy_policy_shadow_enabled"
            ]
        )
        self.assertEqual(
            report["runtime_contract"][
                "strategy_policy_interval_seconds"
            ],
            STRATEGY_POLICY_START_INTERVAL_SECONDS,
        )
        self.assertTrue(
            report["runtime_contract"][
                "preserve_existing_public_snapshot"
            ]
        )
        self.assertFalse(
            report["runtime_contract"]["credentials_embedded"]
        )
        self.assertFalse(report["side_effects"]["launchd_mutated"])
        self.assertFalse(report["side_effects"]["database_connected"])
        self.assertFalse(report["side_effects"]["model_called"])
        self.assertFalse(report["side_effects"]["proposal_created"])

        self.assertNotIn("daily_summary", report)
        self.assertNotIn("public_snapshot", report)
        agent = report["agent_shadow"]["plist"]
        self.assertEqual(agent["Label"], AGENT_LABEL)
        self.assertFalse(agent["RunAtLoad"])
        self.assertFalse(agent["KeepAlive"])
        self.assertEqual(agent["ProcessType"], "Background")
        self.assertEqual(
            agent["WorkingDirectory"], str(STATE_ROOT / "cwd")
        )
        self.assertEqual(
            isolated_environment(agent)["PGSERVICE"],
            "n6_ai_agent",
        )
        self.assertNotIn("EnvironmentVariables", agent)
        self.assertNotIn(
            AUTONOMOUS_FEATURE_FLAG,
            isolated_environment(agent),
        )
        self.assertEqual(
            agent["ProgramArguments"][:2],
            ["/usr/bin/env", "-i"],
        )
        self.assertNotIn("--autonomous", agent["ProgramArguments"])
        self.assertNotIn("/bin/sh", agent["ProgramArguments"])

        self.assertNotIn("StartInterval", agent)
        self.assertEqual(
            agent["StartCalendarInterval"],
            AGENT_START_CALENDAR_INTERVALS,
        )
        self.assertEqual(
            isolated_command(agent),
            [
                str(RUNTIME_ENV_PATH / "bin/python3.11"),
                str(RELEASE_PATH / "scripts/run_n6_ai_agent_once.py"),
                "--max-signals",
                str(MAX_CONTEXT_SIGNALS),
                "--execute",
            ],
        )
        agent_environment = isolated_environment(agent)
        self.assertEqual(
            agent_environment[
                PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV
            ],
            str(
                RELEASE_PATH
                / "docs/N6_AI_PRODUCTION_KNOWLEDGE_BUNDLE_MANIFEST_V1.json"
            ),
        )
        self.assertEqual(
            agent_environment[
                PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV
            ],
            PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256,
        )
        self.assertEqual(
            agent_environment[
                DEEPSEEK_MODEL_PROVIDER_ENV
            ],
            DEEPSEEK_MODEL_PROVIDER,
        )
        self.assertEqual(
            agent_environment[DEEPSEEK_API_KEY_FILE_ENV],
            str(DEEPSEEK_API_KEY_FILE),
        )
        self.assertEqual(
            DEEPSEEK_API_KEY_FILE,
            FIXED_DEEPSEEK_API_KEY_FILE,
        )
        self.assertEqual(
            agent_environment[DEEPSEEK_EGRESS_MODE_ENV],
            DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
        )
        self.assertEqual(
            agent_environment[
                DEEPSEEK_SYSTEM_FINGERPRINT_ENV
            ],
            DEEPSEEK_SYSTEM_FINGERPRINT,
        )
        self.assertNotIn(
            LEGACY_OPENAI_API_KEY_FILE_ENV,
            agent_environment,
        )
        self.assertTrue(
            report["runtime_contract"]["launchd_environment_isolated"]
        )
        self.assertFalse(
            report["runtime_contract"][
                "launchd_environment_inheritance_allowed"
            ]
        )

        strategy = report["strategy_policy_shadow"]["plist"]
        self.assertEqual(strategy["Label"], STRATEGY_POLICY_LABEL)
        self.assertFalse(strategy["RunAtLoad"])
        self.assertFalse(strategy["KeepAlive"])
        self.assertEqual(strategy["ProcessType"], "Background")
        self.assertEqual(
            strategy["WorkingDirectory"], str(STATE_ROOT / "cwd")
        )
        self.assertEqual(
            strategy["StartInterval"],
            STRATEGY_POLICY_START_INTERVAL_SECONDS,
        )
        self.assertNotIn("StartCalendarInterval", strategy)
        self.assertNotIn("EnvironmentVariables", strategy)
        self.assertEqual(
            strategy["ProgramArguments"][:2],
            ["/usr/bin/env", "-i"],
        )
        self.assertEqual(
            isolated_command(strategy),
            [
                str(RUNTIME_ENV_PATH / "bin/python3.11"),
                str(
                    RELEASE_PATH
                    / "scripts/run_n6_ai_strategy_policy_once.py"
                ),
                "--mode",
                "shadow",
                "--execute",
            ],
        )
        strategy_environment = isolated_environment(strategy)
        self.assertEqual(
            frozenset(strategy_environment),
            _STRATEGY_POLICY_ENV_KEYS,
        )
        self.assertEqual(
            strategy_environment[
                STRATEGY_POLICY_SHADOW_FEATURE_FLAG
            ],
            "1",
        )
        for forbidden_key in (
            AUTONOMOUS_FEATURE_FLAG,
            PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV,
            PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV,
            DEEPSEEK_MODEL_PROVIDER_ENV,
            DEEPSEEK_API_KEY_FILE_ENV,
            DEEPSEEK_EGRESS_MODE_ENV,
            DEEPSEEK_SYSTEM_FINGERPRINT_ENV,
            LEGACY_OPENAI_API_KEY_FILE_ENV,
        ):
            self.assertNotIn(forbidden_key, strategy_environment)

    def test_env_i_clears_inherited_owner_dsn_and_proxy_variables(self):
        hostile_keys = (
            "ASHARE_V3_POSTGRES_DSN",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        )
        with tempfile.TemporaryDirectory() as temporary:
            probe = Path(temporary) / "probe.py"
            probe.write_text(
                "import json, os\n"
                f"keys = {hostile_keys!r}\n"
                "print(json.dumps({key: os.environ.get(key) "
                "for key in keys}))\n"
                "print(os.environ.get('PGSERVICE', ''))\n",
                encoding="utf-8",
            )
            arguments = _build_isolated_program_arguments(
                {"PGSERVICE": "n6_ai_agent"},
                [sys.executable, str(probe)],
            )
            inherited = {
                **os.environ,
                **{key: "inherited-owner-value" for key in hostile_keys},
            }

            completed = subprocess.run(
                arguments,
                check=True,
                capture_output=True,
                text=True,
                env=inherited,
            )

        lines = completed.stdout.splitlines()
        self.assertEqual(
            json.loads(lines[0]),
            {key: None for key in hostile_keys},
        )
        self.assertEqual(lines[1], "n6_ai_agent")

    def test_rejects_direct_python_or_plist_environment_inheritance(self):
        base_agent = plan()["agent_shadow"]["plist"]
        environment = isolated_environment(base_agent)
        command = isolated_command(base_agent)

        direct_python = copy.deepcopy(base_agent)
        direct_python["ProgramArguments"] = command
        self.assert_agent_plist_rejected(
            direct_python,
            "env -i isolation required",
        )

        plist_environment = copy.deepcopy(base_agent)
        plist_environment["EnvironmentVariables"] = environment
        self.assert_agent_plist_rejected(
            plist_environment,
            "must not use EnvironmentVariables",
        )

        for inherited_key in (
            "ASHARE_V3_POSTGRES_DSN",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ):
            with self.subTest(inherited_key=inherited_key):
                extra_environment = copy.deepcopy(base_agent)
                mutated = isolated_environment(extra_environment)
                mutated[inherited_key] = "inherited-owner-value"
                replace_isolated_environment(
                    extra_environment, mutated
                )
                self.assert_agent_plist_rejected(
                    extra_environment,
                    "environment allowlist drift",
                )

    def test_plists_contain_paths_but_no_secret_values_or_dsn(self):
        report = plan()
        for key in report["launchd_plist_keys"]:
            plist = report[key]["plist"]
            serialized = plistlib.dumps(plist).decode("utf-8")
            lowered = serialized.lower()
            self.assertNotIn("pgpassword", lowered)
            self.assertNotIn("database_url", lowered)
            self.assertNotIn("postgres_dsn", lowered)
            self.assertNotIn("deepseek_api_key</key>", lowered)
            self.assertNotIn("openai", lowered)
            self.assertNotIn("synthetic_only", lowered)
            self.assertNotIn("raw_n6", lowered)
            self.assertNotRegex(
                serialized, r"(?i)sk-(?:proj-)?[A-Za-z0-9_-]{16,}"
            )
            self.assertNotIn("BEGIN PRIVATE KEY", serialized)
        self.assertIn(
            str(PG_PASS_FILE),
            plistlib.dumps(
                report["agent_shadow"]["plist"]
            ).decode("utf-8"),
        )
        self.assertIn(
            str(DEEPSEEK_API_KEY_FILE),
            plistlib.dumps(
                report["agent_shadow"]["plist"]
            ).decode("utf-8"),
        )

    def test_rejects_relative_unversioned_or_misnamed_paths(self):
        base = {
            "release_path": RELEASE_PATH,
            "runtime_env_path": RUNTIME_ENV_PATH,
            "pg_service_file": PG_SERVICE_FILE,
            "pg_pass_file": PG_PASS_FILE,
            "deepseek_api_key_file": DEEPSEEK_API_KEY_FILE,
            "deepseek_system_fingerprint":
                DEEPSEEK_SYSTEM_FINGERPRINT,
            "state_root": STATE_ROOT,
        }
        for key in (
            "release_path",
            "runtime_env_path",
            "pg_service_file",
            "pg_pass_file",
            "deepseek_api_key_file",
            "state_root",
        ):
            with self.subTest(key=key):
                invalid = dict(base)
                invalid[key] = Path("relative")
                with self.assertRaisesRegex(
                    ValueError, f"{key} must be absolute"
                ):
                    build_launchd_plan(**invalid)
        invalid = dict(base)
        invalid["release_path"] = RELEASE_PATH.parent / "mutable"
        with self.assertRaisesRegex(ValueError, "release_path must end"):
            build_launchd_plan(**invalid)
        invalid = dict(base)
        invalid["state_root"] = Path("/tmp/n6-ai-state-drift")
        with self.assertRaisesRegex(
            ValueError,
            "state_root must match fixed authority",
        ):
            build_launchd_plan(**invalid)
        for key, wrong_name in (
            ("pg_service_file", "service.conf"),
            ("pg_pass_file", "shared.pgpass"),
            ("deepseek_api_key_file", "api-key"),
        ):
            with self.subTest(key=key):
                invalid = dict(base)
                invalid[key] = base[key].with_name(wrong_name)
                with self.assertRaisesRegex(
                    ValueError, "credential path must end"
                ):
                    build_launchd_plan(**invalid)
        invalid = dict(base)
        invalid["deepseek_api_key_file"] = (
            Path("/tmp/deepseek") / DEEPSEEK_API_KEY_FILE.name
        )
        with self.assertRaisesRegex(
            ValueError,
            "API key path must match fixed authority",
        ):
            build_launchd_plan(**invalid)

    def test_write_and_cli_reject_absolute_state_root_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            output_dir = root / "candidate"
            with self.assertRaisesRegex(
                ValueError,
                "state_root must match fixed authority",
            ):
                write_launchd_plan(
                    output_dir=output_dir,
                    release_path=RELEASE_PATH,
                    runtime_env_path=RUNTIME_ENV_PATH,
                    pg_service_file=PG_SERVICE_FILE,
                    pg_pass_file=PG_PASS_FILE,
                    deepseek_api_key_file=DEEPSEEK_API_KEY_FILE,
                    deepseek_system_fingerprint=(
                        DEEPSEEK_SYSTEM_FINGERPRINT
                    ),
                    state_root=root / "state-drift",
                )
            self.assertFalse(output_dir.exists())

            argv = [
                "plan_n6_ai_shadow_launchd.py",
                "--output-dir",
                str(output_dir),
                "--release-path",
                str(RELEASE_PATH),
                "--runtime-env-path",
                str(RUNTIME_ENV_PATH),
                "--pg-service-file",
                str(PG_SERVICE_FILE),
                "--pg-pass-file",
                str(PG_PASS_FILE),
                "--deepseek-api-key-file",
                str(DEEPSEEK_API_KEY_FILE),
                "--deepseek-system-fingerprint",
                DEEPSEEK_SYSTEM_FINGERPRINT,
                "--state-root",
                str(root / "state-drift"),
            ]
            with mock.patch("sys.argv", argv):
                with self.assertRaisesRegex(
                    ValueError,
                    "state_root must match fixed authority",
                ):
                    main()
            self.assertFalse(output_dir.exists())

    def test_requires_safe_reviewed_system_fingerprint(self):
        base = {
            "release_path": RELEASE_PATH,
            "runtime_env_path": RUNTIME_ENV_PATH,
            "pg_service_file": PG_SERVICE_FILE,
            "pg_pass_file": PG_PASS_FILE,
            "deepseek_api_key_file": DEEPSEEK_API_KEY_FILE,
            "deepseek_system_fingerprint":
                DEEPSEEK_SYSTEM_FINGERPRINT,
            "state_root": STATE_ROOT,
        }
        missing = dict(base)
        missing.pop("deepseek_system_fingerprint")
        with self.assertRaises(TypeError):
            build_launchd_plan(**missing)
        for invalid_fingerprint in (
            "",
            "fp not safe",
            "fp_bad\ninjected",
            "fp_雪",
            "x" * 201,
        ):
            with self.subTest(
                deepseek_system_fingerprint=invalid_fingerprint
            ):
                invalid = dict(base)
                invalid["deepseek_system_fingerprint"] = (
                    invalid_fingerprint
                )
                with self.assertRaises(ValueError):
                    build_launchd_plan(**invalid)

    def test_rejects_non_pseudonymous_or_extra_agent_environment(self):
        base_agent = plan()["agent_shadow"]["plist"]
        for egress_mode in (
            "raw_n6",
            "synthetic_only",
        ):
            with self.subTest(egress_mode=egress_mode):
                mutated = copy.deepcopy(base_agent)
                environment = isolated_environment(mutated)
                environment[DEEPSEEK_EGRESS_MODE_ENV] = egress_mode
                replace_isolated_environment(mutated, environment)
                self.assert_agent_plist_rejected(
                    mutated,
                    "DeepSeek provider configuration drift",
                )

        missing_fingerprint = copy.deepcopy(base_agent)
        environment = isolated_environment(missing_fingerprint)
        del environment[DEEPSEEK_SYSTEM_FINGERPRINT_ENV]
        replace_isolated_environment(
            missing_fingerprint, environment
        )
        self.assert_agent_plist_rejected(
            missing_fingerprint,
            "environment allowlist drift",
        )

        invalid_fingerprint = copy.deepcopy(base_agent)
        environment = isolated_environment(invalid_fingerprint)
        environment[DEEPSEEK_SYSTEM_FINGERPRINT_ENV] = (
            "fp_bad;launchctl"
        )
        replace_isolated_environment(
            invalid_fingerprint, environment
        )
        self.assert_agent_plist_rejected(
            invalid_fingerprint,
            "system_fingerprint",
        )

        extra_environment = copy.deepcopy(base_agent)
        environment = isolated_environment(extra_environment)
        environment["ASHARE_V3_N6_AI_RAW_N6_EGRESS"] = "1"
        replace_isolated_environment(
            extra_environment, environment
        )
        self.assert_agent_plist_rejected(
            extra_environment,
            "environment allowlist drift",
        )

    def test_strategy_plist_rejects_model_pollution_and_missing_authority(
        self,
    ):
        base_strategy = plan()["strategy_policy_shadow"]["plist"]
        for key, value in (
            (DEEPSEEK_MODEL_PROVIDER_ENV, DEEPSEEK_MODEL_PROVIDER),
            (DEEPSEEK_API_KEY_FILE_ENV, str(DEEPSEEK_API_KEY_FILE)),
            (LEGACY_OPENAI_API_KEY_FILE_ENV, "/tmp/openai-key"),
            (AUTONOMOUS_FEATURE_FLAG, "1"),
        ):
            with self.subTest(polluted_key=key):
                mutated = copy.deepcopy(base_strategy)
                environment = isolated_environment(mutated)
                environment[key] = value
                replace_isolated_environment(mutated, environment)
                self.assert_strategy_plist_rejected(
                    mutated,
                    "environment allowlist drift",
                )

        missing_flag = copy.deepcopy(base_strategy)
        environment = isolated_environment(missing_flag)
        del environment[STRATEGY_POLICY_SHADOW_FEATURE_FLAG]
        replace_isolated_environment(missing_flag, environment)
        self.assert_strategy_plist_rejected(
            missing_flag,
            "environment allowlist drift",
        )

        wrong_runner = copy.deepcopy(base_strategy)
        command = isolated_command(wrong_runner)
        command[1] = str(
            RELEASE_PATH / "scripts/run_n6_ai_agent_once.py"
        )
        wrong_runner["ProgramArguments"] = (
            _build_isolated_program_arguments(
                isolated_environment(wrong_runner),
                command,
            )
        )
        self.assert_strategy_plist_rejected(
            wrong_runner,
            "unexpected strategy policy runner",
        )

    def test_materializes_two_valid_shadow_candidate_plists(self):
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary).resolve() / "candidate"
            report = write_launchd_plan(
                output_dir=output_dir,
                release_path=RELEASE_PATH,
                runtime_env_path=RUNTIME_ENV_PATH,
                pg_service_file=PG_SERVICE_FILE,
                pg_pass_file=PG_PASS_FILE,
                deepseek_api_key_file=DEEPSEEK_API_KEY_FILE,
                deepseek_system_fingerprint=
                    DEEPSEEK_SYSTEM_FINGERPRINT,
                state_root=STATE_ROOT,
            )

            self.assertTrue(report["side_effects"]["files_written"])
            self.assertEqual(
                output_dir.stat().st_mode & 0o777, 0o700
            )
            paths = sorted(output_dir.glob("*.plist"))
            self.assertEqual(len(paths), 2)
            for key in report["launchd_plist_keys"]:
                expected = report[key]["plist"]
                path = Path(report[key]["plist_path"])
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(
                    path.name,
                    f"{RELEASE_ID}.{expected['Label']}.plist",
                )
                self.assertEqual(
                    plistlib.loads(path.read_bytes()), expected
                )
            self.assertFalse(report["side_effects"]["launchd_mutated"])
            self.assertFalse(report["side_effects"]["worker_started"])
            self.assertFalse(report["side_effects"]["runtime_executed"])
            with self.assertRaises(FileExistsError):
                write_launchd_plan(
                    output_dir=output_dir,
                    release_path=RELEASE_PATH,
                    runtime_env_path=RUNTIME_ENV_PATH,
                    pg_service_file=PG_SERVICE_FILE,
                    pg_pass_file=PG_PASS_FILE,
                    deepseek_api_key_file=DEEPSEEK_API_KEY_FILE,
                    deepseek_system_fingerprint=
                        DEEPSEEK_SYSTEM_FINGERPRINT,
                    state_root=STATE_ROOT,
                )


if __name__ == "__main__":
    unittest.main()
