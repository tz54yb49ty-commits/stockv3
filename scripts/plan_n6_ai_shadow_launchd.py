#!/usr/bin/env python3
"""Build plan-only immutable LaunchAgents for the N6 AI shadow phase."""

from __future__ import annotations

import argparse
import json
import plistlib
import re
from pathlib import Path
from typing import Any, Mapping

from ashare_v3.user.ai_agent import (
    AI_AGENT_SERVICE,
    AUTONOMOUS_FEATURE_FLAG,
    CONTEXT_KNOWLEDGE_BUNDLE_SHA256,
    MAX_CONTEXT_SIGNALS,
    PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV,
    PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256,
    PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV,
    SHADOW_SCHEDULE_POLICY_VERSION,
    SHADOW_SCHEDULE_SLOTS,
    SHADOW_FEATURE_FLAG,
)
from ashare_v3.user.n6_ai_deepseek_adapter import (
    DEEPSEEK_API_KEY_FILE,
    DEEPSEEK_API_KEY_FILE_ENV,
    DEEPSEEK_EGRESS_MODE_ENV,
    DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
    DEEPSEEK_FINGERPRINT_PAUSE_FILE,
    DEEPSEEK_MODEL_PROVIDER,
    DEEPSEEK_MODEL_PROVIDER_ENV,
    DEEPSEEK_SYSTEM_FINGERPRINT_ENV,
    DeepSeekAdapterError,
    LEGACY_OPENAI_API_KEY_FILE_ENV,
    validate_system_fingerprint,
)
from scripts.run_n6_ai_strategy_policy_once import (
    STRATEGY_POLICY_SHADOW_FEATURE_FLAG,
)


AGENT_LABEL = "com.ashare-v3.n6.ai-agent-shadow-v1"
STRATEGY_POLICY_LABEL = (
    "com.ashare-v3.n6.ai-strategy-policy-shadow-v1"
)
DAILY_SUMMARY_LABEL = "com.ashare-v3.n6.ai-daily-summary-v1"
PUBLIC_SNAPSHOT_LABEL = (
    "com.ashare-v3.n6.ai-public-snapshot-v1"
)
AGENT_START_CALENDAR_INTERVALS = [
    {"Hour": hour, "Minute": minute}
    for hour, minute, _label, _window in SHADOW_SCHEDULE_SLOTS
]
AGENT_RECOVERY_WINDOWS_MINUTES = {
    label: window
    for _hour, _minute, label, window in SHADOW_SCHEDULE_SLOTS
}
STRATEGY_POLICY_START_INTERVAL_SECONDS = 300
DEFAULT_STATE_ROOT = Path(
    "/Users/chuanfuchen/.local/state/ashare-v3/n6-ai-agent"
)
RELEASE_ID_PATTERN = re.compile(
    r"^[0-9]{8}_[0-9]{6}__[0-9a-f]{40}$"
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
N1_N5_RUNNER_PATTERN = re.compile(r"run_n[1-5](?:[^a-z0-9]|$)")
SHELL_METACHAR_PATTERN = re.compile(r"[;&|`$<>]")
ENV_ASSIGNMENT_PATTERN = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$"
)
ENV_EXECUTABLE = Path("/usr/bin/env")

_DB_ENV_KEYS = frozenset(
    {
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONNOUSERSITE",
        "PYTHONPATH",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGPASSFILE",
    }
)
_AGENT_ENV_KEYS = _DB_ENV_KEYS | frozenset(
    {
        SHADOW_FEATURE_FLAG,
        PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV,
        PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV,
        DEEPSEEK_MODEL_PROVIDER_ENV,
        DEEPSEEK_API_KEY_FILE_ENV,
        DEEPSEEK_EGRESS_MODE_ENV,
        DEEPSEEK_SYSTEM_FINGERPRINT_ENV,
    }
)
_STRATEGY_POLICY_ENV_KEYS = _DB_ENV_KEYS | frozenset(
    {STRATEGY_POLICY_SHADOW_FEATURE_FLAG}
)


def build_launchd_plan(
    *,
    release_path: Path,
    runtime_env_path: Path,
    pg_service_file: Path,
    pg_pass_file: Path,
    deepseek_api_key_file: Path,
    deepseek_system_fingerprint: str,
    state_root: Path = DEFAULT_STATE_ROOT,
) -> dict[str, Any]:
    """Return two reviewed shadow plists without touching launchd."""

    release = _absolute_path(release_path, "release_path")
    runtime_env = _absolute_path(runtime_env_path, "runtime_env_path")
    service_file = _absolute_path(pg_service_file, "pg_service_file")
    pass_file = _absolute_path(pg_pass_file, "pg_pass_file")
    api_key_file = _absolute_path(
        deepseek_api_key_file, "deepseek_api_key_file"
    )
    reviewed_system_fingerprint = _validated_system_fingerprint(
        deepseek_system_fingerprint
    )
    state = _absolute_path(state_root, "state_root")
    if state != DEFAULT_STATE_ROOT:
        raise ValueError("state_root must match fixed authority")
    if not RELEASE_ID_PATTERN.fullmatch(release.name):
        raise ValueError(
            "release_path must end with <YYYYMMDD_HHMMSS>__<40hex>"
        )
    _assert_credential_path_names(
        pg_service_file=service_file,
        pg_pass_file=pass_file,
        deepseek_api_key_file=api_key_file,
    )

    python_executable = runtime_env / "bin/python3.11"
    python_path = ":".join(
        (str(release / "src"), str(release / "scripts"), str(release))
    )
    manifest_file = (
        release
        / "docs/N6_AI_PRODUCTION_KNOWLEDGE_BUNDLE_MANIFEST_V1.json"
    )
    database_environment = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": python_path,
        "PGSERVICE": AI_AGENT_SERVICE,
        "PGSERVICEFILE": str(service_file),
        "PGPASSFILE": str(pass_file),
    }
    agent_environment = {
        **database_environment,
        SHADOW_FEATURE_FLAG: "1",
        PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV: str(manifest_file),
        PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV:
            PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256,
        DEEPSEEK_MODEL_PROVIDER_ENV: DEEPSEEK_MODEL_PROVIDER,
        DEEPSEEK_API_KEY_FILE_ENV: str(api_key_file),
        DEEPSEEK_EGRESS_MODE_ENV:
            DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
        DEEPSEEK_SYSTEM_FINGERPRINT_ENV:
            reviewed_system_fingerprint,
    }
    strategy_policy_environment = {
        **database_environment,
        STRATEGY_POLICY_SHADOW_FEATURE_FLAG: "1",
    }
    logs = state / "logs"
    agent_plist = {
        "Label": AGENT_LABEL,
        "ProgramArguments": _build_isolated_program_arguments(
            agent_environment,
            [
                str(python_executable),
                str(release / "scripts/run_n6_ai_agent_once.py"),
                "--max-signals",
                str(MAX_CONTEXT_SIGNALS),
                "--execute",
            ],
        ),
        "WorkingDirectory": str(state / "cwd"),
        "RunAtLoad": False,
        "KeepAlive": False,
        "StartCalendarInterval":
            AGENT_START_CALENDAR_INTERVALS,
        "ProcessType": "Background",
        "StandardOutPath": str(logs / f"{AGENT_LABEL}.out.log"),
        "StandardErrorPath": str(logs / f"{AGENT_LABEL}.err.log"),
    }
    _assert_plist_safe(
        agent_plist,
        expected_label=AGENT_LABEL,
        expected_env_keys=_AGENT_ENV_KEYS,
        release_path=release,
        runtime_env_path=runtime_env,
        state_root=state,
        expected_schedule={
            "StartCalendarInterval":
                AGENT_START_CALENDAR_INTERVALS
        },
        required_feature_flags={
            SHADOW_FEATURE_FLAG: "1",
            DEEPSEEK_EGRESS_MODE_ENV:
                DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            DEEPSEEK_SYSTEM_FINGERPRINT_ENV:
                reviewed_system_fingerprint,
        },
    )
    strategy_policy_plist = {
        "Label": STRATEGY_POLICY_LABEL,
        "ProgramArguments": _build_isolated_program_arguments(
            strategy_policy_environment,
            [
                str(python_executable),
                str(
                    release
                    / "scripts/run_n6_ai_strategy_policy_once.py"
                ),
                "--mode",
                "shadow",
                "--execute",
            ],
        ),
        "WorkingDirectory": str(state / "cwd"),
        "RunAtLoad": False,
        "KeepAlive": False,
        "StartInterval":
            STRATEGY_POLICY_START_INTERVAL_SECONDS,
        "ProcessType": "Background",
        "StandardOutPath":
            str(logs / f"{STRATEGY_POLICY_LABEL}.out.log"),
        "StandardErrorPath":
            str(logs / f"{STRATEGY_POLICY_LABEL}.err.log"),
    }
    _assert_plist_safe(
        strategy_policy_plist,
        expected_label=STRATEGY_POLICY_LABEL,
        expected_env_keys=_STRATEGY_POLICY_ENV_KEYS,
        release_path=release,
        runtime_env_path=runtime_env,
        state_root=state,
        expected_schedule={
            "StartInterval":
                STRATEGY_POLICY_START_INTERVAL_SECONDS
        },
        required_feature_flags={
            STRATEGY_POLICY_SHADOW_FEATURE_FLAG: "1",
        },
    )
    if (
        agent_environment[
            PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV
        ]
        != PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256
        or CONTEXT_KNOWLEDGE_BUNDLE_SHA256
        != "1a873d69ef8f14e329b744460d549bcb3c35d99bb6af5fd10c16fc1a9dda15bc"
    ):
        raise ValueError("production knowledge authority drift")

    return {
        "stage": "N6_AI_AGENT_V1_SHADOW_LAUNCHD_PLAN",
        "result": "PLAN_ONLY_PASS",
        "release_id": release.name,
        "knowledge_bundle_sha256": CONTEXT_KNOWLEDGE_BUNDLE_SHA256,
        "manifest_file_sha256":
            PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256,
        "launchd_plist_keys": [
            "agent_shadow",
            "strategy_policy_shadow",
        ],
        "agent_shadow": {
            "label": AGENT_LABEL,
            "plist": agent_plist,
        },
        "strategy_policy_shadow": {
            "label": STRATEGY_POLICY_LABEL,
            "plist": strategy_policy_plist,
        },
        "runtime_contract": {
            "shadow_enabled": True,
            "strategy_policy_shadow_enabled": True,
            "autonomous_enabled": False,
            "model_provider": DEEPSEEK_MODEL_PROVIDER,
            "deepseek_egress_mode":
                DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
            "reviewed_system_fingerprint":
                reviewed_system_fingerprint,
            "fingerprint_pause_file":
                str(DEEPSEEK_FINGERPRINT_PAUSE_FILE),
            "raw_n6_egress": False,
            "pseudonymous_shadow": True,
            "daily_summary_enabled": False,
            "public_snapshot_managed": False,
            "preserve_existing_public_snapshot": True,
            "resident_worker": False,
            "agent_schedule_policy_version":
                SHADOW_SCHEDULE_POLICY_VERSION,
            "agent_start_calendar_intervals":
                AGENT_START_CALENDAR_INTERVALS,
            "agent_recovery_window_minutes": 5,
            "agent_recovery_windows_minutes":
                AGENT_RECOVERY_WINDOWS_MINUTES,
            "strategy_policy_interval_seconds":
                STRATEGY_POLICY_START_INTERVAL_SECONDS,
            "credentials_embedded": False,
            "credential_paths_only": True,
            "launchd_environment_isolated": True,
            "launchd_environment_inheritance_allowed": False,
            "n1_n5_write_enabled": False,
            "real_broker_enabled": False,
        },
        "side_effects": {
            "files_written": False,
            "launchd_mutated": False,
            "worker_started": False,
            "runtime_executed": False,
            "database_connected": False,
            "database_written": False,
            "model_called": False,
            "proposal_created": False,
            "order_created": False,
            "trade_created": False,
            "position_mutated": False,
            "cash_mutated": False,
        },
    }


def write_launchd_plan(
    *,
    output_dir: Path,
    release_path: Path,
    runtime_env_path: Path,
    pg_service_file: Path,
    pg_pass_file: Path,
    deepseek_api_key_file: Path,
    deepseek_system_fingerprint: str,
    state_root: Path = DEFAULT_STATE_ROOT,
) -> dict[str, Any]:
    """Materialize candidate plists in an explicitly selected evidence dir."""

    report = build_launchd_plan(
        release_path=release_path,
        runtime_env_path=runtime_env_path,
        pg_service_file=pg_service_file,
        pg_pass_file=pg_pass_file,
        deepseek_api_key_file=deepseek_api_key_file,
        deepseek_system_fingerprint=deepseek_system_fingerprint,
        state_root=state_root,
    )
    output = _absolute_path(output_dir, "output_dir")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    output.chmod(0o700)
    for key in report["launchd_plist_keys"]:
        item = report[key]
        path = output / f"{report['release_id']}.{item['label']}.plist"
        with path.open("xb") as file_handle:
            plistlib.dump(item["plist"], file_handle, sort_keys=True)
        path.chmod(0o600)
        item["plist_path"] = str(path)
    report["side_effects"]["files_written"] = True
    return report


def _absolute_path(value: Path, name: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{name} must be absolute")
    if "\x00" in str(path) or "\n" in str(path) or "\r" in str(path):
        raise ValueError(f"{name} contains invalid characters")
    return path


def _validated_system_fingerprint(value: str) -> str:
    try:
        return validate_system_fingerprint(value)
    except DeepSeekAdapterError:
        raise ValueError(
            "deepseek_system_fingerprint is invalid"
        ) from None


def _assert_credential_path_names(
    *,
    pg_service_file: Path,
    pg_pass_file: Path,
    deepseek_api_key_file: Path,
) -> None:
    expected = {
        pg_service_file: "pg_service.conf",
        pg_pass_file: "n6_ai_agent.pgpass",
        deepseek_api_key_file: "n6_ai_agent_api_key",
    }
    for path, basename in expected.items():
        if path.name != basename:
            raise ValueError(
                f"credential path must end with {basename}"
            )
    if len(set(expected)) != len(expected):
        raise ValueError("credential paths must be distinct")
    if deepseek_api_key_file != DEEPSEEK_API_KEY_FILE:
        raise ValueError("DeepSeek API key path must match fixed authority")


def _assert_plist_safe(
    plist: Mapping[str, Any],
    *,
    expected_label: str,
    expected_env_keys: frozenset[str],
    release_path: Path,
    runtime_env_path: Path,
    state_root: Path,
    expected_schedule: Mapping[str, Any],
    required_feature_flags: Mapping[str, str],
) -> None:
    if plist.get("Label") != expected_label:
        raise ValueError("unexpected LaunchAgent label")
    if plist.get("RunAtLoad") is not False:
        raise ValueError("AI one-shot must not run at plist load")
    if plist.get("KeepAlive") is not False:
        raise ValueError("AI one-shot must not be resident")
    if plist.get("ProcessType") != "Background":
        raise ValueError("AI one-shot must use Background process type")
    for key in ("StartInterval", "StartCalendarInterval"):
        actual = plist.get(key)
        expected = expected_schedule.get(key)
        if actual != expected:
            if actual is not None or expected is not None:
                raise ValueError("LaunchAgent schedule drift")
    working_directory = str(plist.get("WorkingDirectory") or "")
    if working_directory != str(state_root / "cwd"):
        raise ValueError("unexpected WorkingDirectory")

    if "EnvironmentVariables" in plist:
        raise ValueError(
            "LaunchAgent must not use EnvironmentVariables"
        )
    args = [str(item) for item in plist.get("ProgramArguments") or []]
    environment, command_args = _parse_isolated_program_arguments(args)
    if frozenset(environment) != expected_env_keys:
        raise ValueError("LaunchAgent environment allowlist drift")
    if environment.get("PGSERVICE") != AI_AGENT_SERVICE:
        raise ValueError("AI LaunchAgent must use n6_ai_agent service")
    if expected_label == AGENT_LABEL:
        if (
            environment.get(DEEPSEEK_MODEL_PROVIDER_ENV)
            != DEEPSEEK_MODEL_PROVIDER
            or environment.get(DEEPSEEK_API_KEY_FILE_ENV)
            != str(DEEPSEEK_API_KEY_FILE)
            or environment.get(DEEPSEEK_EGRESS_MODE_ENV)
            != DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW
            or not environment.get(DEEPSEEK_SYSTEM_FINGERPRINT_ENV)
        ):
            raise ValueError("DeepSeek provider configuration drift")
        _validated_system_fingerprint(
            str(environment[DEEPSEEK_SYSTEM_FINGERPRINT_ENV])
        )
    elif any(
        key in environment
        for key in (
            DEEPSEEK_MODEL_PROVIDER_ENV,
            DEEPSEEK_API_KEY_FILE_ENV,
            DEEPSEEK_EGRESS_MODE_ENV,
            DEEPSEEK_SYSTEM_FINGERPRINT_ENV,
            LEGACY_OPENAI_API_KEY_FILE_ENV,
        )
    ):
        raise ValueError(
            "non-agent LaunchAgent must not receive model configuration"
        )
    for key, value in required_feature_flags.items():
        if environment.get(key) != value:
            raise ValueError(f"{key} must be enabled")
    if AUTONOMOUS_FEATURE_FLAG in environment:
        raise ValueError("autonomous feature must remain absent")
    for key, value in environment.items():
        upper_key = str(key).upper()
        text_value = str(value)
        if (
            upper_key in {
                "PGPASSWORD",
                "DEEPSEEK_API_KEY",
                LEGACY_OPENAI_API_KEY_FILE_ENV,
                "DATABASE_URL",
                "ASHARE_V3_POSTGRES_DSN",
            }
            or "PASSWORD" in upper_key
            or "DSN" in upper_key
            or "BEGIN PRIVATE KEY" in text_value
            or re.search(r"(?i)sk-(?:proj-)?[A-Za-z0-9_-]{16,}", text_value)
        ):
            raise ValueError("secret or DSN embedded in LaunchAgent")
    manifest_hash = environment.get(
        PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV
    )
    if manifest_hash is not None and (
        not SHA256_PATTERN.fullmatch(str(manifest_hash))
        or manifest_hash
        != PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256
    ):
        raise ValueError("knowledge manifest SHA drift")

    if (
        not command_args
        or command_args[0]
        != str(runtime_env_path / "bin/python3.11")
    ):
        raise ValueError("unexpected Python executable")
    if len(command_args) < 2 or not command_args[1].startswith(
        str(release_path / "scripts/")
    ):
        raise ValueError("runner must come from immutable release")
    if expected_label == STRATEGY_POLICY_LABEL and command_args[1:] != [
        str(release_path / "scripts/run_n6_ai_strategy_policy_once.py"),
        "--mode",
        "shadow",
        "--execute",
    ]:
        raise ValueError("unexpected strategy policy runner")
    _assert_program_arguments_safe(args)


def _build_isolated_program_arguments(
    environment: Mapping[str, str],
    command_args: list[str],
) -> list[str]:
    """Build an env(1) boundary that discards launchd domain state."""

    assignments: list[str] = []
    for key in sorted(environment):
        value = str(environment[key])
        if (
            not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(key))
            or any(character in value for character in "\x00\r\n")
        ):
            raise ValueError("invalid isolated environment assignment")
        assignments.append(f"{key}={value}")
    if not command_args:
        raise ValueError("isolated environment command is required")
    arguments = [
        str(ENV_EXECUTABLE),
        "-i",
        *assignments,
        *(str(item) for item in command_args),
    ]
    _parse_isolated_program_arguments(arguments)
    return arguments


def _parse_isolated_program_arguments(
    args: list[str],
) -> tuple[dict[str, str], list[str]]:
    """Return the exact env -i allowlist and wrapped command."""

    if len(args) < 4 or args[:2] != [str(ENV_EXECUTABLE), "-i"]:
        raise ValueError("LaunchAgent env -i isolation required")
    environment: dict[str, str] = {}
    assignment_names: list[str] = []
    command_index = 2
    for command_index in range(2, len(args)):
        token = str(args[command_index])
        match = ENV_ASSIGNMENT_PATTERN.fullmatch(token)
        if match is None:
            break
        key, value = match.groups()
        if (
            key in environment
            or any(character in value for character in "\x00\r\n")
        ):
            raise ValueError("invalid isolated environment assignment")
        environment[key] = value
        assignment_names.append(key)
    else:
        command_index = len(args)
    if assignment_names != sorted(assignment_names):
        raise ValueError("isolated environment order drift")
    command_args = [str(item) for item in args[command_index:]]
    if not environment or not command_args:
        raise ValueError("isolated environment command is required")
    return environment, command_args


def _assert_program_arguments_safe(args: list[str]) -> None:
    """Reject executable controls without matching harmless path substrings."""

    found: list[str] = []
    forbidden_options = ("--autonomous", "--dsn", "--password")
    shell_executables = frozenset(
        {"sh", "bash", "dash", "ksh", "zsh", "fish", "shell"}
    )
    for arg in args:
        lowered = arg.lower()
        basename = Path(lowered).name
        if lowered == "-c":
            found.append("-c")
        for option in forbidden_options:
            if lowered == option or lowered.startswith(f"{option}="):
                found.append(option)
        if basename in shell_executables:
            found.append(basename)
        if basename == "launchctl":
            found.append("launchctl")
        if "broker" in lowered:
            found.append("broker")
        if N1_N5_RUNNER_PATTERN.search(lowered):
            found.append("N1-N5 runner")
        if (
            any(
                ord(character) < 32 or ord(character) == 127
                for character in arg
            )
            or SHELL_METACHAR_PATTERN.search(arg)
        ):
            found.append("control/metacharacter")
    unique_found = list(dict.fromkeys(found))
    if unique_found:
        raise ValueError(
            f"unsafe ProgramArguments token(s): {unique_found}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--release-path", required=True)
    parser.add_argument("--runtime-env-path", required=True)
    parser.add_argument("--pg-service-file", required=True)
    parser.add_argument("--pg-pass-file", required=True)
    parser.add_argument("--deepseek-api-key-file", required=True)
    parser.add_argument(
        "--deepseek-system-fingerprint",
        required=True,
    )
    parser.add_argument("--state-root", default=str(DEFAULT_STATE_ROOT))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = write_launchd_plan(
        output_dir=Path(args.output_dir),
        release_path=Path(args.release_path),
        runtime_env_path=Path(args.runtime_env_path),
        pg_service_file=Path(args.pg_service_file),
        pg_pass_file=Path(args.pg_pass_file),
        deepseek_api_key_file=Path(args.deepseek_api_key_file),
        deepseek_system_fingerprint=args.deepseek_system_fingerprint,
        state_root=Path(args.state_root),
    )
    if args.json:
        print(
            json.dumps(
                report, ensure_ascii=False, indent=2, sort_keys=True
            )
        )
    else:
        print(
            "PLAN_ONLY_PASS "
            f"labels={AGENT_LABEL},{STRATEGY_POLICY_LABEL} "
            f"release_id={report['release_id']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
