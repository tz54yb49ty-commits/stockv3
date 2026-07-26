#!/usr/bin/env python3
"""Read-only filesystem preflight for an N6 AI shadow immutable release."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from hashlib import sha256
import json
import os
from pathlib import Path
import plistlib
import re
import stat
import subprocess
from typing import Any

from ashare_v3.user.ai_agent import (
    AI_AGENT_SERVICE,
    AUTONOMOUS_FEATURE_FLAG,
    CONTEXT_KNOWLEDGE_BUNDLE_SHA256,
    PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV,
    PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256,
    PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV,
    load_production_knowledge_manifest,
    validate_agent_environment,
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
    SYSTEM_CA_BUNDLE,
    validate_system_ca_bundle,
    validate_system_fingerprint,
    validate_tls_environment,
    validate_tls_runtime,
)
from scripts.plan_n6_ai_shadow_launchd import (
    AGENT_LABEL,
    DAILY_SUMMARY_LABEL,
    PUBLIC_SNAPSHOT_LABEL,
    STRATEGY_POLICY_LABEL,
    _AGENT_ENV_KEYS,
    _parse_isolated_program_arguments,
    _assert_program_arguments_safe,
    build_launchd_plan,
)


GitProbe = Callable[[Path, str], str]


def check_release_readiness(
    *,
    release_path: Path,
    expected_commit: str,
    expected_tree: str,
    runtime_env_path: Path,
    expected_runtime_env_sha256: str,
    pg_service_file: Path,
    pg_pass_file: Path,
    deepseek_api_key_file: Path,
    expected_deepseek_system_fingerprint: str,
    pseudonymous_egress_authorized: bool,
    state_root: Path,
    agent_plist_path: Path,
    preserved_public_snapshot_plist_path: Path,
    expected_preserved_public_snapshot_plist_sha256: str,
    launch_agents_dir: Path,
    git_probe: GitProbe | None = None,
) -> dict[str, Any]:
    """Validate only local immutable artifacts and return all blockers."""

    paths = {
        "release_path": _absolute(release_path, "release_path"),
        "runtime_env_path": _absolute(
            runtime_env_path, "runtime_env_path"
        ),
        "pg_service_file": _absolute(
            pg_service_file, "pg_service_file"
        ),
        "pg_pass_file": _absolute(pg_pass_file, "pg_pass_file"),
        "deepseek_api_key_file": _absolute(
            deepseek_api_key_file,
            "deepseek_api_key_file",
            allow_missing_file=True,
        ),
        "state_root": _absolute(state_root, "state_root"),
        "agent_plist_path": _absolute(
            agent_plist_path, "agent_plist_path"
        ),
        "preserved_public_snapshot_plist_path": _absolute(
            preserved_public_snapshot_plist_path,
            "preserved_public_snapshot_plist_path",
            allow_missing_file=True,
        ),
        "launch_agents_dir": _absolute(
            launch_agents_dir, "launch_agents_dir"
        ),
    }
    blockers: list[str] = []
    checks: dict[str, Any] = {
        "model_provider": DEEPSEEK_MODEL_PROVIDER,
        "legacy_openai_fallback_enabled": False,
        "system_ca_bundle_path": str(SYSTEM_CA_BUNDLE),
        "deepseek_api_key_path": str(DEEPSEEK_API_KEY_FILE),
        "deepseek_fingerprint_pause_file": str(
            DEEPSEEK_FINGERPRINT_PAUSE_FILE
        ),
        "raw_n6_egress": False,
        "pseudonymous_shadow": True,
        "pseudonymous_egress_authorized": (
            pseudonymous_egress_authorized is True
        ),
    }
    if pseudonymous_egress_authorized is not True:
        blockers.append("pseudonymous_egress_authorization_missing")
    try:
        reviewed_expected_system_fingerprint = (
            validate_system_fingerprint(
                expected_deepseek_system_fingerprint
            )
        )
    except (TypeError, ValueError, RuntimeError):
        reviewed_expected_system_fingerprint = None
        blockers.append(
            "expected_deepseek_system_fingerprint_invalid"
        )
    checks["expected_deepseek_system_fingerprint"] = (
        reviewed_expected_system_fingerprint
        if reviewed_expected_system_fingerprint is not None
        else "<invalid>"
    )
    try:
        validate_tls_environment()
    except Exception:
        checks["tls_environment_safe"] = False
        blockers.append("tls_environment_not_safe")
    else:
        checks["tls_environment_safe"] = True
    try:
        validate_system_ca_bundle()
    except Exception:
        checks["system_ca_bundle_ready"] = False
        blockers.append("system_ca_bundle_not_ready")
    else:
        checks["system_ca_bundle_ready"] = True
    try:
        validate_tls_runtime()
    except Exception:
        checks["tls_context_prebuilt"] = False
        blockers.append("tls_context_prebuild_failed")
    else:
        checks["tls_context_prebuilt"] = True
    api_key_path_exact = (
        paths["deepseek_api_key_file"] == DEEPSEEK_API_KEY_FILE
    )
    checks["deepseek_api_key_path_exact"] = api_key_path_exact
    if not api_key_path_exact:
        blockers.append("deepseek_api_key_path_invalid")
    pause_path_exact = (
        DEEPSEEK_FINGERPRINT_PAUSE_FILE.parent
        == paths["state_root"]
    )
    checks["deepseek_fingerprint_pause_path_exact"] = (
        pause_path_exact
    )
    if not pause_path_exact:
        blockers.append("deepseek_fingerprint_pause_path_invalid")
    try:
        os.lstat(DEEPSEEK_FINGERPRINT_PAUSE_FILE)
    except FileNotFoundError:
        pause_marker_absent = True
    except OSError:
        pause_marker_absent = False
    else:
        pause_marker_absent = False
    checks["deepseek_fingerprint_pause_marker_absent"] = (
        pause_marker_absent
    )
    if not pause_marker_absent:
        blockers.append("deepseek_fingerprint_pause_marker_present")
    if (
        len(expected_commit) != 40
        or any(character not in "0123456789abcdef" for character in expected_commit)
    ):
        blockers.append("expected_commit_invalid")
    if (
        len(expected_tree) != 40
        or any(character not in "0123456789abcdef" for character in expected_tree)
    ):
        blockers.append("expected_tree_invalid")
    if (
        len(expected_runtime_env_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in expected_runtime_env_sha256
        )
    ):
        blockers.append("expected_runtime_env_sha256_invalid")
    if (
        len(expected_preserved_public_snapshot_plist_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in
            expected_preserved_public_snapshot_plist_sha256
        )
    ):
        blockers.append(
            "expected_preserved_public_snapshot_plist_sha256_invalid"
        )
    release = paths["release_path"]
    expected_suffix = f"__{expected_commit}"
    checks["release_name_matches_commit"] = (
        release.name.endswith(expected_suffix)
    )
    if not checks["release_name_matches_commit"]:
        blockers.append("release_name_commit_mismatch")

    release_metadata = _directory_metadata(
        release, require_not_writable=True
    )
    checks["release"] = release_metadata
    if not release_metadata["ready"]:
        blockers.extend(
            f"release_{item}"
            for item in release_metadata["blockers"]
        )
    probe = git_probe or _default_git_probe
    if release_metadata["ready"]:
        for operation, expected, blocker in (
            ("head", expected_commit, "release_head_mismatch"),
            ("tree", expected_tree, "release_tree_mismatch"),
            ("status", "", "release_worktree_not_clean"),
        ):
            try:
                actual = probe(release, operation).strip()
            except Exception:
                actual = "<probe_failed>"
                blockers.append(f"{operation}_probe_failed")
            checks[f"git_{operation}"] = actual
            if actual != expected:
                blockers.append(blocker)
        writable, unsafe_links = _scan_immutable_tree(release)
        checks["release_writable_entry_count"] = len(writable)
        checks["release_unsafe_symlink_count"] = len(unsafe_links)
        if writable:
            blockers.append("release_contains_writable_entries")
        if unsafe_links:
            blockers.append("release_contains_external_symlink")

    for check_name, runner_name in (
        ("agent_runner", "run_n6_ai_agent_once.py"),
        (
            "strategy_policy_runner",
            "run_n6_ai_strategy_policy_once.py",
        ),
    ):
        runner_metadata = _regular_file_metadata(
            release / "scripts" / runner_name,
            expected_mode=0o444,
            require_owner=True,
            require_not_writable=True,
        )
        checks[check_name] = runner_metadata
        if not runner_metadata["ready"]:
            blockers.extend(
                f"{check_name}_{item}"
                for item in runner_metadata["blockers"]
            )

    manifest_path = (
        release
        / "docs/N6_AI_PRODUCTION_KNOWLEDGE_BUNDLE_MANIFEST_V1.json"
    )
    manifest_metadata = _regular_file_metadata(
        manifest_path,
        expected_mode=None,
        require_owner=True,
        require_not_writable=True,
    )
    checks["production_manifest"] = manifest_metadata
    if not manifest_metadata["ready"]:
        blockers.extend(
            f"production_manifest_{item}"
            for item in manifest_metadata["blockers"]
        )
    else:
        try:
            manifest_bytes = _read_regular_file_nofollow(
                manifest_path,
                expected_mode=None,
                require_not_writable=True,
                require_nonempty=True,
                max_size=1_000_000,
            )
        except (OSError, ValueError):
            manifest_bytes = b""
            blockers.append("production_manifest_secure_read_failed")
        actual_manifest_sha = sha256(manifest_bytes).hexdigest()
        checks["production_manifest_sha256"] = actual_manifest_sha
        if actual_manifest_sha != PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256:
            blockers.append("production_manifest_sha_mismatch")
        manifest_environment = {
            "PGSERVICE": AI_AGENT_SERVICE,
            "PGSERVICEFILE": str(paths["pg_service_file"]),
            "PGPASSFILE": str(paths["pg_pass_file"]),
            DEEPSEEK_MODEL_PROVIDER_ENV: DEEPSEEK_MODEL_PROVIDER,
            DEEPSEEK_API_KEY_FILE_ENV: str(
                paths["deepseek_api_key_file"]
            ),
            PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV: str(
                manifest_path
            ),
            PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV:
                PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256,
        }
        try:
            validate_agent_environment(manifest_environment)
            manifest = load_production_knowledge_manifest(
                manifest_environment
            )
            checks["knowledge_bundle_sha256"] = manifest.get(
                "bundle_sha256"
            )
            checks["production_agent_usable"] = manifest.get(
                "production_agent_usable"
            )
            checks["autonomous_trading_usable"] = manifest.get(
                "autonomous_trading_usable"
            )
            if (
                manifest.get("bundle_sha256")
                != CONTEXT_KNOWLEDGE_BUNDLE_SHA256
                or manifest.get("production_agent_usable") is not True
                or manifest.get("autonomous_trading_usable") is not False
            ):
                blockers.append("production_manifest_contract_mismatch")
        except (OSError, ValueError):
            blockers.append("production_manifest_validation_failed")

    runtime_env_metadata = _directory_metadata(
        paths["runtime_env_path"], require_not_writable=True
    )
    checks["runtime_env"] = runtime_env_metadata
    if not runtime_env_metadata["ready"]:
        blockers.extend(
            f"runtime_env_{item}"
            for item in runtime_env_metadata["blockers"]
        )
    runtime_writable: list[str] = []
    runtime_unsafe_links: list[str] = []
    if runtime_env_metadata["ready"]:
        runtime_writable, runtime_unsafe_links = _scan_immutable_tree(
            paths["runtime_env_path"]
        )
    checks["runtime_env_writable_entry_count"] = len(runtime_writable)
    checks["runtime_env_unsafe_symlink_count"] = len(
        runtime_unsafe_links
    )
    if runtime_writable:
        blockers.append("runtime_env_contains_writable_entries")
    if runtime_unsafe_links:
        blockers.append("runtime_env_contains_external_symlink")
    try:
        actual_runtime_env_sha256 = compute_immutable_tree_sha256(
            paths["runtime_env_path"]
        )
    except (OSError, ValueError):
        actual_runtime_env_sha256 = "<hash_failed>"
        blockers.append("runtime_env_hash_failed")
    checks["runtime_env_sha256"] = actual_runtime_env_sha256
    if actual_runtime_env_sha256 != expected_runtime_env_sha256:
        blockers.append("runtime_env_sha_mismatch")

    python_path = paths["runtime_env_path"] / "bin/python3.11"
    python_metadata = _regular_file_metadata(
        python_path,
        expected_mode=None,
        require_owner=True,
        require_not_writable=True,
    )
    python_metadata["executable"] = (
        python_path.exists() and os.access(python_path, os.X_OK)
    )
    checks["runtime_python"] = python_metadata
    if not python_metadata["ready"]:
        blockers.extend(
            f"runtime_python_{item}"
            for item in python_metadata["blockers"]
        )
    if not python_metadata["executable"]:
        blockers.append("runtime_python_not_executable")

    for name in (
        "pg_service_file",
        "pg_pass_file",
        "deepseek_api_key_file",
    ):
        metadata = _regular_file_metadata(
            paths[name],
            expected_mode=0o600,
            require_owner=True,
            require_not_writable=False,
        )
        checks[name] = metadata
        if not metadata["ready"]:
            blockers.extend(
                f"{name}_{item}" for item in metadata["blockers"]
            )
        size = metadata["size"]
        if name == "deepseek_api_key_file":
            if size is not None and not 20 <= size <= 512:
                blockers.append(f"{name}_size_invalid")
        elif size is not None and size <= 0:
            blockers.append(f"{name}_empty")

    for suffix in ("", "cwd", "logs"):
        directory = (
            paths["state_root"]
            if suffix == ""
            else paths["state_root"] / suffix
        )
        name = "state_root" if suffix == "" else f"state_{suffix}"
        metadata = _directory_metadata(directory, expected_mode=0o700)
        checks[name] = metadata
        if not metadata["ready"]:
            blockers.extend(
                f"{name}_{item}" for item in metadata["blockers"]
            )

    candidate_path = paths["agent_plist_path"]
    candidate_parent = candidate_path.parent
    strategy_candidate_path = (
        candidate_parent
        / f"{release.name}.{STRATEGY_POLICY_LABEL}.plist"
    )
    candidate_parent_metadata = _directory_metadata(
        candidate_parent, expected_mode=0o700
    )
    checks["candidate_evidence_dir"] = candidate_parent_metadata
    if not candidate_parent_metadata["ready"]:
        blockers.extend(
            f"candidate_evidence_dir_{item}"
            for item in candidate_parent_metadata["blockers"]
        )
    if candidate_parent_metadata["ready"]:
        extras = sorted(
            path.name
            for path in candidate_parent.iterdir()
            if path not in {candidate_path, strategy_candidate_path}
        )
        checks["candidate_extra_entries"] = extras
        if extras:
            blockers.append("candidate_evidence_contains_extra_entries")
    agent_metadata = _regular_file_metadata(
        candidate_path,
        expected_mode=0o600,
        require_owner=True,
        require_not_writable=False,
    )
    checks["agent_plist"] = agent_metadata
    if not agent_metadata["ready"]:
        blockers.extend(
            f"agent_plist_{item}"
            for item in agent_metadata["blockers"]
        )
        agent_payload = None
    else:
        try:
            agent_plist_bytes = _read_regular_file_nofollow(
                candidate_path,
                expected_mode=0o600,
                require_not_writable=False,
                require_nonempty=True,
                max_size=1_000_000,
            )
            agent_payload = plistlib.loads(agent_plist_bytes)
            checks["agent_plist_sha256"] = sha256(
                agent_plist_bytes
            ).hexdigest()
        except (OSError, ValueError, plistlib.InvalidFileException):
            agent_payload = None
            blockers.append("agent_plist_invalid")
        if (
            agent_payload is not None
            and not isinstance(agent_payload, Mapping)
        ):
            agent_payload = None
            blockers.append("agent_plist_invalid")

    strategy_metadata = _regular_file_metadata(
        strategy_candidate_path,
        expected_mode=0o600,
        require_owner=True,
        require_not_writable=False,
    )
    checks["strategy_policy_plist"] = strategy_metadata
    if not strategy_metadata["ready"]:
        blockers.extend(
            f"strategy_policy_plist_{item}"
            for item in strategy_metadata["blockers"]
        )
        strategy_payload = None
    else:
        try:
            strategy_plist_bytes = _read_regular_file_nofollow(
                strategy_candidate_path,
                expected_mode=0o600,
                require_not_writable=False,
                require_nonempty=True,
                max_size=1_000_000,
            )
            strategy_payload = plistlib.loads(strategy_plist_bytes)
            checks["strategy_policy_plist_sha256"] = sha256(
                strategy_plist_bytes
            ).hexdigest()
        except (OSError, ValueError, plistlib.InvalidFileException):
            strategy_payload = None
            blockers.append("strategy_policy_plist_invalid")
        if (
            strategy_payload is not None
            and not isinstance(strategy_payload, Mapping)
        ):
            strategy_payload = None
            blockers.append("strategy_policy_plist_invalid")

    candidate_system_fingerprint: str | None = None
    if agent_payload is not None:
        label = str(agent_payload.get("Label") or "")
        checks["agent_plist_label"] = (
            label if label == AGENT_LABEL else "<invalid>"
        )
        if label != AGENT_LABEL:
            blockers.append("agent_plist_label_invalid")
        if candidate_path.name != (
            f"{release.name}.{AGENT_LABEL}.plist"
        ):
            blockers.append("agent_plist_filename_invalid")
        environment: Mapping[str, str] | None = None
        environment_variables_absent = (
            "EnvironmentVariables" not in agent_payload
        )
        checks["agent_plist_environment_variables_absent"] = (
            environment_variables_absent
        )
        if not environment_variables_absent:
            blockers.append(
                "agent_plist_environment_variables_present"
            )
        arguments = [
            str(item)
            for item in agent_payload.get("ProgramArguments") or []
        ]
        try:
            parsed_environment, _command_args = (
                _parse_isolated_program_arguments(arguments)
            )
        except ValueError:
            checks["agent_plist_environment_isolated"] = False
            checks["agent_plist_environment_allowlist_exact"] = False
            blockers.append(
                "agent_plist_environment_isolation_invalid"
            )
        else:
            checks["agent_plist_environment_isolated"] = True
            allowlist_exact = (
                frozenset(parsed_environment) == _AGENT_ENV_KEYS
            )
            checks["agent_plist_environment_allowlist_exact"] = (
                allowlist_exact
            )
            if not allowlist_exact:
                blockers.append(
                    "agent_plist_environment_allowlist_invalid"
                )
            environment = parsed_environment
        if environment is not None:
            candidate_egress_mode = environment.get(
                DEEPSEEK_EGRESS_MODE_ENV
            )
            checks["agent_plist_deepseek_egress_mode"] = (
                candidate_egress_mode
                if candidate_egress_mode
                == DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW
                else "<invalid>"
            )
            if (
                candidate_egress_mode
                != DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW
            ):
                blockers.append("agent_plist_egress_mode_invalid")
            candidate_api_key_path = environment.get(
                DEEPSEEK_API_KEY_FILE_ENV
            )
            checks["agent_plist_deepseek_api_key_path"] = (
                candidate_api_key_path
                if candidate_api_key_path
                == str(DEEPSEEK_API_KEY_FILE)
                else "<invalid>"
            )
            if candidate_api_key_path != str(DEEPSEEK_API_KEY_FILE):
                blockers.append("agent_plist_api_key_path_invalid")
            candidate_fingerprint = environment.get(
                DEEPSEEK_SYSTEM_FINGERPRINT_ENV
            )
            try:
                candidate_system_fingerprint = (
                    validate_system_fingerprint(candidate_fingerprint)
                )
            except (TypeError, ValueError, RuntimeError):
                blockers.append(
                    "agent_plist_system_fingerprint_invalid"
                )
            if (
                candidate_system_fingerprint is not None
                and reviewed_expected_system_fingerprint is not None
                and candidate_system_fingerprint
                != reviewed_expected_system_fingerprint
            ):
                blockers.append(
                    "agent_plist_system_fingerprint_mismatch"
                )
            checks["agent_plist_deepseek_system_fingerprint"] = (
                candidate_system_fingerprint
                if (
                    candidate_system_fingerprint is not None
                    and candidate_system_fingerprint
                    == reviewed_expected_system_fingerprint
                )
                else "<invalid>"
            )
            if AUTONOMOUS_FEATURE_FLAG in environment:
                blockers.append("agent_plist_autonomous_present")

    expected_plan: dict[str, Any] | None = None
    if reviewed_expected_system_fingerprint is not None:
        try:
            expected_plan = build_launchd_plan(
                release_path=release,
                runtime_env_path=paths["runtime_env_path"],
                pg_service_file=paths["pg_service_file"],
                pg_pass_file=paths["pg_pass_file"],
                deepseek_api_key_file=paths[
                    "deepseek_api_key_file"
                ],
                deepseek_system_fingerprint=(
                    reviewed_expected_system_fingerprint
                ),
                state_root=paths["state_root"],
            )
        except ValueError:
            blockers.append("launchd_plan_inputs_invalid")
    expected_by_label = (
        {
            expected_plan[key]["label"]: expected_plan[key]["plist"]
            for key in expected_plan["launchd_plist_keys"]
        }
        if expected_plan is not None
        else {}
    )
    if (
        agent_payload is not None
        and reviewed_expected_system_fingerprint is not None
        and agent_payload != expected_by_label.get(AGENT_LABEL)
    ):
        blockers.append("agent_plist_content_drift")
    if (
        strategy_payload is not None
        and strategy_payload
        != expected_by_label.get(STRATEGY_POLICY_LABEL)
    ):
        blockers.append("strategy_policy_plist_content_drift")

    launch_agents_metadata = _directory_metadata(
        paths["launch_agents_dir"], expected_mode=None
    )
    checks["launch_agents_dir"] = launch_agents_metadata
    if not launch_agents_metadata["ready"]:
        blockers.extend(
            f"launch_agents_dir_{item}"
            for item in launch_agents_metadata["blockers"]
        )
    active_conflicts: list[str] = []
    for label in (
        AGENT_LABEL,
        STRATEGY_POLICY_LABEL,
        DAILY_SUMMARY_LABEL,
    ):
        active_path = (
            paths["launch_agents_dir"] / f"{label}.plist"
        )
        if active_path.exists() or active_path.is_symlink():
            active_conflicts.append(str(active_path))
    checks["active_plist_conflicts"] = active_conflicts
    if active_conflicts:
        blockers.append("ai_launchagent_plist_already_installed")

    preserved_public_path = paths[
        "preserved_public_snapshot_plist_path"
    ]
    expected_public_path = (
        paths["launch_agents_dir"]
        / f"{PUBLIC_SNAPSHOT_LABEL}.plist"
    )
    path_matches = preserved_public_path == expected_public_path
    checks["preserved_public_snapshot_path_exact"] = path_matches
    if not path_matches:
        blockers.append("preserved_public_snapshot_path_invalid")
    preserved_metadata = _regular_file_metadata(
        preserved_public_path,
        expected_mode=0o600,
        require_owner=True,
        require_not_writable=False,
    )
    checks["preserved_public_snapshot_plist"] = preserved_metadata
    if not preserved_metadata["ready"]:
        blockers.extend(
            f"preserved_public_snapshot_plist_{item}"
            for item in preserved_metadata["blockers"]
        )
    preserved_contract_blockers: list[str] = []
    preserved_hash_matches = False
    if preserved_metadata["ready"]:
        try:
            preserved_bytes = _read_regular_file_nofollow(
                preserved_public_path,
                expected_mode=0o600,
                require_not_writable=False,
                require_nonempty=True,
                max_size=1_000_000,
            )
            preserved_payload = plistlib.loads(preserved_bytes)
            preserved_sha256 = sha256(preserved_bytes).hexdigest()
            checks[
                "preserved_public_snapshot_plist_sha256"
            ] = preserved_sha256
            preserved_hash_matches = (
                preserved_sha256
                == expected_preserved_public_snapshot_plist_sha256
            )
            preserved_contract_blockers = (
                _preserved_public_snapshot_contract_blockers(
                    preserved_payload
                )
            )
        except (OSError, ValueError, plistlib.InvalidFileException):
            blockers.append("preserved_public_snapshot_plist_invalid")
    checks[
        "preserved_public_snapshot_sha256_matches"
    ] = preserved_hash_matches
    if not preserved_hash_matches:
        blockers.append("preserved_public_snapshot_sha256_mismatch")
    blockers.extend(preserved_contract_blockers)
    checks["preserved_public_snapshot_plist_exact"] = (
        path_matches
        and preserved_metadata["ready"]
        and preserved_hash_matches
        and not preserved_contract_blockers
    )

    unique_blockers = sorted(set(blockers))
    return {
        "stage": "N6_AI_AGENT_V1_SHADOW_RELEASE_READINESS",
        "result": (
            "READY_READONLY"
            if not unique_blockers
            else "BLOCKED_READONLY"
        ),
        "expected_commit": expected_commit,
        "expected_tree": expected_tree,
        "expected_runtime_env_sha256": expected_runtime_env_sha256,
        "expected_preserved_public_snapshot_plist_sha256": (
            expected_preserved_public_snapshot_plist_sha256
        ),
        "egress_contract": {
            "raw_n6_egress": False,
            "pseudonymous_shadow": True,
            "explicit_runtime_authorization_required": True,
            "explicit_runtime_authorization_present": (
                pseudonymous_egress_authorized is True
            ),
        },
        "blockers": unique_blockers,
        "checks": checks,
        "unverified_by_this_probe": [
            "postgres_hba",
            "database_role_and_function_acl",
            "055_058_migration_state",
            "launchd_loaded_label_state",
            "deepseek_network_and_model_response",
            "provider_contractual_data_processing_commitments",
        ],
        "side_effects": {
            "files_written": False,
            "credential_contents_read": False,
            "database_connected": False,
            "database_written": False,
            "launchctl_called": False,
            "worker_started": False,
            "model_called": False,
            "network_called": False,
        },
    }


def _preserved_public_snapshot_contract_blockers(
    payload: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if payload.get("Label") != PUBLIC_SNAPSHOT_LABEL:
        blockers.append("preserved_public_snapshot_label_invalid")
    if payload.get("RunAtLoad") is not False:
        blockers.append("preserved_public_snapshot_run_at_load_invalid")
    if payload.get("KeepAlive") is not False:
        blockers.append("preserved_public_snapshot_keep_alive_invalid")

    environment = payload.get("EnvironmentVariables")
    if not isinstance(environment, Mapping):
        blockers.append("preserved_public_snapshot_environment_invalid")
    else:
        for key, value in environment.items():
            upper_key = str(key).upper()
            text_value = str(value)
            if (
                key in {
                    DEEPSEEK_MODEL_PROVIDER_ENV,
                    DEEPSEEK_API_KEY_FILE_ENV,
                }
                or "OPENAI" in upper_key
                or "DEEPSEEK" in upper_key
                or key == AUTONOMOUS_FEATURE_FLAG
            ):
                blockers.append(
                    "preserved_public_snapshot_model_environment_present"
                )
            if (
                upper_key == "PGPASSWORD"
                or "PASSWORD" in upper_key
                or "DSN" in upper_key
                or upper_key.endswith("DATABASE_URL")
                or "BEGIN PRIVATE KEY" in text_value
                or re.search(
                    r"(?i)sk-(?:proj-)?[A-Za-z0-9_-]{16,}",
                    text_value,
                )
            ):
                blockers.append(
                    "preserved_public_snapshot_secret_present"
                )

    arguments = [
        str(item) for item in payload.get("ProgramArguments") or []
    ]
    if (
        len(arguments) < 2
        or Path(arguments[1]).name
        != "run_n6_ai_public_snapshot_once.py"
    ):
        blockers.append(
            "preserved_public_snapshot_runner_invalid"
        )
    try:
        _assert_program_arguments_safe(arguments)
    except ValueError:
        blockers.append(
            "preserved_public_snapshot_program_arguments_unsafe"
        )
    if any(
        "BEGIN PRIVATE KEY" in argument
        or re.search(
            r"(?i)sk-(?:proj-)?[A-Za-z0-9_-]{16,}",
            argument,
        )
        for argument in arguments
    ):
        blockers.append("preserved_public_snapshot_secret_present")
    return sorted(set(blockers))


def _absolute(
    path: Path,
    name: str,
    *,
    allow_missing_file: bool = False,
) -> Path:
    value = Path(path)
    if not value.is_absolute():
        raise ValueError(f"{name} must be absolute")
    if any(character in str(value) for character in "\x00\r\n"):
        raise ValueError(f"{name} contains invalid characters")
    if allow_missing_file and not value.exists():
        try:
            canonical_parent = value.parent.resolve(strict=True)
        except OSError as exc:
            raise ValueError(
                f"{name} parent must exist"
            ) from exc
        if value.parent != canonical_parent:
            raise ValueError(
                f"{name} must be canonical and contain no symlink ancestors"
            )
        return value
    try:
        canonical = value.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"{name} must exist") from exc
    if value != canonical:
        raise ValueError(
            f"{name} must be canonical and contain no symlink ancestors"
        )
    return value


def _directory_metadata(
    path: Path,
    expected_mode: int | None = None,
    require_not_writable: bool = False,
) -> dict[str, Any]:
    blockers: list[str] = []
    try:
        metadata = path.lstat()
    except OSError:
        return {
            "ready": False,
            "blockers": ["missing"],
            "owner_matches": False,
            "mode": None,
        }
    if stat.S_ISLNK(metadata.st_mode):
        blockers.append("symlink")
    if not stat.S_ISDIR(metadata.st_mode):
        blockers.append("not_directory")
    owner_matches = metadata.st_uid == os.getuid()
    if not owner_matches:
        blockers.append("owner_mismatch")
    mode = stat.S_IMODE(metadata.st_mode)
    if expected_mode is not None and mode != expected_mode:
        blockers.append("mode_mismatch")
    elif require_not_writable and mode & 0o222:
        blockers.append("writable")
    elif mode & (stat.S_IWGRP | stat.S_IWOTH):
        blockers.append("group_or_world_writable")
    return {
        "ready": not blockers,
        "blockers": blockers,
        "owner_matches": owner_matches,
        "mode": oct(mode),
    }


def _regular_file_metadata(
    path: Path,
    *,
    expected_mode: int | None,
    require_owner: bool,
    require_not_writable: bool,
) -> dict[str, Any]:
    blockers: list[str] = []
    try:
        metadata = path.lstat()
    except OSError:
        return {
            "ready": False,
            "blockers": ["missing"],
            "owner_matches": False,
            "mode": None,
            "size": None,
        }
    if stat.S_ISLNK(metadata.st_mode):
        blockers.append("symlink")
    if not stat.S_ISREG(metadata.st_mode):
        blockers.append("not_regular")
    owner_matches = metadata.st_uid == os.getuid()
    if require_owner and not owner_matches:
        blockers.append("owner_mismatch")
    mode = stat.S_IMODE(metadata.st_mode)
    if expected_mode is not None and mode != expected_mode:
        blockers.append("mode_mismatch")
    if require_not_writable and mode & 0o222:
        blockers.append("writable")
    if mode & (stat.S_IWGRP | stat.S_IWOTH):
        blockers.append("group_or_world_writable")
    return {
        "ready": not blockers,
        "blockers": blockers,
        "owner_matches": owner_matches,
        "mode": oct(mode),
        "size": metadata.st_size,
    }


def _scan_immutable_tree(
    release_path: Path,
) -> tuple[list[str], list[str]]:
    writable: list[str] = []
    unsafe_links: list[str] = []
    root = release_path.resolve()
    for current, directory_names, file_names in os.walk(
        release_path, followlinks=False
    ):
        for name in [*directory_names, *file_names]:
            path = Path(current) / name
            try:
                metadata = path.lstat()
            except OSError:
                unsafe_links.append(str(path))
                continue
            if stat.S_ISLNK(metadata.st_mode):
                try:
                    path.resolve(strict=True).relative_to(root)
                except (OSError, ValueError):
                    unsafe_links.append(str(path))
                continue
            if stat.S_IMODE(metadata.st_mode) & 0o222:
                writable.append(str(path))
    return writable, unsafe_links


def compute_immutable_tree_sha256(root: Path) -> str:
    """Hash one already immutable tree, including relative names and modes."""

    root_path = _absolute(root, "immutable_tree_root")
    root_metadata = _directory_metadata(
        root_path, require_not_writable=True
    )
    if not root_metadata["ready"]:
        raise ValueError("immutable tree root is not read-only")
    writable, unsafe_links = _scan_immutable_tree(root_path)
    if writable or unsafe_links:
        raise ValueError("immutable tree contains unsafe entries")
    digest = sha256()
    digest.update(b"N6_AI_IMMUTABLE_TREE_V1\0")
    for path in sorted(
        (item for item in root_path.rglob("*")),
        key=lambda item: item.relative_to(root_path).as_posix(),
    ):
        relative = path.relative_to(root_path).as_posix()
        metadata = path.lstat()
        mode = stat.S_IMODE(metadata.st_mode)
        _update_length_prefixed(digest, relative.encode("utf-8"))
        _update_length_prefixed(digest, f"{mode:o}".encode("ascii"))
        if stat.S_ISDIR(metadata.st_mode):
            _update_length_prefixed(digest, b"directory")
            _update_length_prefixed(digest, b"")
            continue
        if stat.S_ISLNK(metadata.st_mode):
            resolved = path.resolve(strict=True)
            try:
                resolved.relative_to(root_path)
            except ValueError as exc:
                raise ValueError(
                    "immutable tree contains external symlink"
                ) from exc
            _update_length_prefixed(digest, b"symlink")
            _update_length_prefixed(
                digest, os.readlink(path).encode("utf-8")
            )
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("immutable tree contains non-regular entry")
        _update_length_prefixed(digest, b"file")
        _update_length_prefixed(
            digest,
            _read_regular_file_nofollow(
                path,
                expected_mode=mode,
                require_not_writable=True,
                require_nonempty=False,
                max_size=256 * 1024 * 1024,
            ),
        )
    return digest.hexdigest()


def _update_length_prefixed(digest: Any, payload: bytes) -> None:
    digest.update(len(payload).to_bytes(8, "big", signed=False))
    digest.update(payload)


def _read_regular_file_nofollow(
    path: Path,
    *,
    expected_mode: int | None,
    require_not_writable: bool,
    require_nonempty: bool,
    max_size: int,
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        mode = stat.S_IMODE(metadata.st_mode)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or (expected_mode is not None and mode != expected_mode)
            or (require_not_writable and mode & 0o222)
            or mode & (stat.S_IWGRP | stat.S_IWOTH)
            or (require_nonempty and metadata.st_size <= 0)
            or metadata.st_size < 0
            or metadata.st_size > max_size
        ):
            raise ValueError("secure file metadata mismatch")
        remaining = metadata.st_size + 1
        chunks: list[bytes] = []
        while remaining > 0:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) != metadata.st_size:
            raise ValueError("secure file size changed")
        return payload
    finally:
        os.close(descriptor)


def _default_git_probe(release_path: Path, operation: str) -> str:
    commands = {
        "head": ["rev-parse", "HEAD"],
        "tree": ["rev-parse", "HEAD^{tree}"],
        "status": [
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
    }
    if operation not in commands:
        raise ValueError("unsupported git probe")
    result = subprocess.run(
        [
            "/usr/bin/git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-C",
            str(release_path),
            *commands[operation],
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
        env={
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(Path.home()),
            "GIT_OPTIONAL_LOCKS": "0",
        },
    )
    return result.stdout


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-path", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-tree", required=True)
    parser.add_argument("--runtime-env-path", required=True)
    parser.add_argument("--expected-runtime-env-sha256", required=True)
    parser.add_argument("--pg-service-file", required=True)
    parser.add_argument("--pg-pass-file", required=True)
    parser.add_argument("--deepseek-api-key-file", required=True)
    parser.add_argument(
        "--deepseek-system-fingerprint", required=True
    )
    parser.add_argument(
        "--authorize-pseudonymous-egress",
        action="store_true",
        help=(
            "Explicit runtime-gate acceptance of documented "
            "pseudonymous DeepSeek egress residual risk."
        ),
    )
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--agent-plist-path", required=True)
    parser.add_argument(
        "--preserved-public-snapshot-plist-path", required=True
    )
    parser.add_argument(
        "--expected-preserved-public-snapshot-plist-sha256",
        required=True,
    )
    parser.add_argument("--launch-agents-dir", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = check_release_readiness(
        release_path=Path(args.release_path),
        expected_commit=args.expected_commit,
        expected_tree=args.expected_tree,
        runtime_env_path=Path(args.runtime_env_path),
        expected_runtime_env_sha256=args.expected_runtime_env_sha256,
        pg_service_file=Path(args.pg_service_file),
        pg_pass_file=Path(args.pg_pass_file),
        deepseek_api_key_file=Path(args.deepseek_api_key_file),
        expected_deepseek_system_fingerprint=(
            args.deepseek_system_fingerprint
        ),
        pseudonymous_egress_authorized=(
            args.authorize_pseudonymous_egress
        ),
        state_root=Path(args.state_root),
        agent_plist_path=Path(args.agent_plist_path),
        preserved_public_snapshot_plist_path=Path(
            args.preserved_public_snapshot_plist_path
        ),
        expected_preserved_public_snapshot_plist_sha256=(
            args.expected_preserved_public_snapshot_plist_sha256
        ),
        launch_agents_dir=Path(args.launch_agents_dir),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["result"] == "READY_READONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
