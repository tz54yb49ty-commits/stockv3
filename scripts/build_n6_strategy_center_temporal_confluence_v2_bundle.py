from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any


BUNDLE_ID = "N6_SC_TEMPORAL_CONFLUENCE_V2_SHADOW_BUNDLE_20260723"
PACKAGE_ID = "N6_SC_TEMPORAL_CONFLUENCE_V2_CANDIDATE_20260723"
STRATEGY_VERSION = "N6_STRATEGY_CENTER_TEMPORAL_CONFLUENCE_V2"
POLICY_VERSION = "n6_strategy_center_matcher_v2"
ALLOWED_PACKAGE_KEYS = ("package_1", "package_2")
CANDIDATE_PATH = (
    "docs/N6_SC_TEMPORAL_CONFLUENCE_V2_CANDIDATE_20260723.json"
)
CANONICAL_PATH = (
    "docs/N6_STRATEGY_CENTER_TEMPORAL_CONFLUENCE_V2_SHADOW_CANONICAL.md"
)
MIGRATION_PATH = (
    "sql/081_n6_strategy_center_temporal_confluence_v2_catalog.sql"
)
ROLLBACK_PATH = (
    "sql/081_n6_strategy_center_temporal_confluence_v2_catalog_rollback.sql"
)
COMPENSATION_MIGRATION_PATH = (
    "sql/082_n6_strategy_center_v2_user_compensation.sql"
)
COMPENSATION_ROLLBACK_PATH = (
    "sql/082_n6_strategy_center_v2_user_compensation_rollback.sql"
)
ACTIVATION_MIGRATION_PATH = (
    "sql/083_n6_strategy_center_v2_catalog_activation.sql"
)
ACTIVATION_ROLLBACK_PATH = (
    "sql/083_n6_strategy_center_v2_catalog_activation_rollback.sql"
)
TRADE_DATE_AUTHORITY_MIGRATION_PATH = (
    "sql/084_n6_strategy_center_n6_trade_date_authority.sql"
)
TRADE_DATE_AUTHORITY_ROLLBACK_PATH = (
    "sql/084_n6_strategy_center_n6_trade_date_authority_rollback.sql"
)
EXPECTED_CANDIDATE_SHA256 = (
    "94f5a6d88717688bfe079930edb956c20acd6c0c66aef870b332d5c2b221e489"
)
EXPECTED_CANONICAL_SHA256 = (
    "17c655213243a820955fe154ac981f1d2b9f16e580bc93a1042d0d9e846986f9"
)
RUNTIME_FILES = (
    "src/ashare_v3/user/strategy_center.py",
    "src/ashare_v3/user/strategy_center_repository.py",
    "src/ashare_v3/user/strategy_center_worker.py",
    "scripts/run_n6_strategy_center_once.py",
    "scripts/run_n6_strategy_center_auto_once.py",
    "scripts/plan_n6_strategy_center_launchd.py",
    "src/ashare_v3/web/n6_app_v1.py",
    "src/ashare_v3/web/n6_user_app.py",
    "src/ashare_v3/web/templates/n6_app_shell.html",
)
EVALUATION_TIME_CONTRACT_MARKERS = {
    "src/ashare_v3/user/strategy_center_worker.py": (
        "evaluation_time=plan.evaluation_time",
        "strategy_evaluation_time_required_for_execute",
        "evaluation_time=plan.evaluation_time,",
    ),
    "scripts/run_n6_strategy_center_once.py": ("--evaluation-time",),
}
TRADE_DATE_AUTHORITY_CONTRACT_MARKERS = {
    "src/ashare_v3/user/strategy_center_worker.py": (
        "N6_TRADE_DATE_AUTHORITY_SQL =",
        "v_n6_stock_condition_display_basis",
        "v_n6_index_condition_display_basis",
        "v_n6_board_condition_display_basis",
        "AUTO_TRADE_DATE_SQL = N6_TRADE_DATE_AUTHORITY_SQL",
        "FROM user_signal_projection p",
        "FROM user_signal_card c",
        "membership.trade_date <= %(membership_asof_upper_bound)s",
        "reviewed_n6_natural_event_group_missing",
    ),
    "scripts/run_n6_strategy_center_auto_once.py": (
        '"reviewed_n6_display_consensus"',
        '"trade_date_authority"',
        '"noop_waiting_for_reviewed_n6_events"',
    ),
}
AUTO_RESUME_CONTRACT_MARKERS = {
    "src/ashare_v3/user/strategy_center_worker.py": (
        "replay_pending_active_scopes",
        'str(row.get("replay_status") or "") != "passed"',
    ),
    "scripts/run_n6_strategy_center_auto_once.py": (
        "DEFAULT_MAX_RUNTIME_SECONDS = 12",
        '"WAITING_OPEN_TRADE_DATE"',
        '"BLOCKED_STALE_TRADE_DATE_AUTHORITY"',
        '"active_replay_pending"',
        "HISTORY_MAX_BYTES",
        "HISTORY_ROTATION_COUNT",
        "_evidence_timeout_handler",
        "_should_emit_report",
    ),
    "scripts/plan_n6_strategy_center_launchd.py": (
        "MAX_RUNTIME_SECONDS = 12",
    ),
}
ALLOWED_WRITE_TABLES = (
    "n6_user_strategy_selection_revision",
    "n6_strategy_match_projection",
    "n6_strategy_match_change",
    "n6_strategy_observation_projection",
)
FORBIDDEN_MUTATIONS = (
    "proposal",
    "order",
    "trade",
    "position",
    "lot",
    "cash",
    "n1_n5",
    "autonomous_trading",
    "real_trading",
)
HEX40 = re.compile(r"^[0-9a-f]{40}$")
REGULAR_GIT_MODES = ("100644", "100755")
FROZEN_IMPLEMENTATION_FILES = (
    CANDIDATE_PATH,
    CANONICAL_PATH,
    MIGRATION_PATH,
    ROLLBACK_PATH,
    COMPENSATION_MIGRATION_PATH,
    COMPENSATION_ROLLBACK_PATH,
    ACTIVATION_MIGRATION_PATH,
    ACTIVATION_ROLLBACK_PATH,
    TRADE_DATE_AUTHORITY_MIGRATION_PATH,
    TRADE_DATE_AUTHORITY_ROLLBACK_PATH,
    *RUNTIME_FILES,
)


def canonical_hash(value: Any) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _git_output(root: Path, *args: str, error: str) -> bytes:
    result = subprocess.run(
        ("git", "-C", str(root), *args),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise ValueError(error)
    return result.stdout


def _read_regular_file(path: Path, relative_path: str) -> tuple[bytes, str]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        file_descriptor = os.open(path, flags)
    except (FileNotFoundError, NotADirectoryError):
        raise ValueError(f"git_frozen_file_missing:{relative_path}") from None
    except OSError:
        raise ValueError(
            f"git_frozen_file_not_regular:{relative_path}"
        ) from None
    try:
        file_stat = os.fstat(file_descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise ValueError(
                f"git_frozen_file_not_regular:{relative_path}"
            )
        mode = "100755" if file_stat.st_mode & 0o111 else "100644"
        with os.fdopen(file_descriptor, "rb", closefd=False) as handle:
            content = handle.read()
    finally:
        os.close(file_descriptor)
    return content, mode


def _git_entry(
    root: Path,
    implementation_commit: str,
    relative_path: str,
) -> tuple[str, str, str]:
    raw = _git_output(
        root,
        "ls-tree",
        "-z",
        "--full-tree",
        implementation_commit,
        "--",
        f":(literal){relative_path}",
        error=f"git_frozen_path_lookup_failed:{relative_path}",
    )
    entries = [entry for entry in raw.split(b"\0") if entry]
    if not entries:
        raise ValueError(
            f"git_frozen_path_missing_or_untracked:{relative_path}"
        )
    if len(entries) != 1 or b"\t" not in entries[0]:
        raise ValueError(f"git_frozen_path_ambiguous:{relative_path}")
    header, encoded_path = entries[0].split(b"\t", 1)
    header_parts = header.split(b" ")
    if len(header_parts) != 3:
        raise ValueError(f"git_frozen_path_invalid:{relative_path}")
    try:
        mode, object_type, object_id = (
            part.decode("ascii") for part in header_parts
        )
        stored_path = encoded_path.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError(f"git_frozen_path_invalid:{relative_path}") from None
    if stored_path != relative_path:
        raise ValueError(f"git_frozen_path_ambiguous:{relative_path}")
    return mode, object_type, object_id


def _validate_git_frozen_inputs(
    root: Path,
    *,
    implementation_commit: str,
    implementation_tree: str,
) -> dict[str, bytes]:
    if not HEX40.fullmatch(implementation_commit):
        raise ValueError("implementation_commit_invalid")
    if not HEX40.fullmatch(implementation_tree):
        raise ValueError("implementation_tree_invalid")
    try:
        resolved_root = root.resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError):
        raise ValueError("implementation_root_missing") from None
    if not resolved_root.is_dir():
        raise ValueError("implementation_root_not_directory")
    top_level_raw = _git_output(
        resolved_root,
        "rev-parse",
        "--show-toplevel",
        error="implementation_root_not_git_repository",
    )
    try:
        top_level = Path(top_level_raw.decode("utf-8").strip()).resolve()
    except UnicodeDecodeError:
        raise ValueError("implementation_git_toplevel_invalid") from None
    if top_level != resolved_root:
        raise ValueError("implementation_root_not_git_toplevel")

    object_type = _git_output(
        resolved_root,
        "cat-file",
        "-t",
        implementation_commit,
        error="implementation_commit_not_commit",
    ).decode("ascii", errors="replace").strip()
    if object_type != "commit":
        raise ValueError("implementation_commit_not_commit")
    resolved_commit = _git_output(
        resolved_root,
        "rev-parse",
        "--verify",
        f"{implementation_commit}^{{commit}}",
        error="implementation_commit_not_commit",
    ).decode("ascii", errors="replace").strip()
    if resolved_commit != implementation_commit:
        raise ValueError("implementation_commit_identity_mismatch")
    resolved_tree = _git_output(
        resolved_root,
        "rev-parse",
        "--verify",
        f"{implementation_commit}^{{tree}}",
        error="implementation_commit_tree_missing",
    ).decode("ascii", errors="replace").strip()
    if resolved_tree != implementation_tree:
        raise ValueError("implementation_tree_mismatch")

    frozen_bytes: dict[str, bytes] = {}
    for relative_path in FROZEN_IMPLEMENTATION_FILES:
        git_mode, object_type, object_id = _git_entry(
            resolved_root,
            implementation_commit,
            relative_path,
        )
        if object_type != "blob" or git_mode not in REGULAR_GIT_MODES:
            raise ValueError(
                f"git_frozen_path_not_regular_blob:{relative_path}"
            )
        current_bytes, current_mode = _read_regular_file(
            resolved_root / relative_path,
            relative_path,
        )
        if current_mode != git_mode:
            raise ValueError(f"git_frozen_file_mode_mismatch:{relative_path}")
        committed_bytes = _git_output(
            resolved_root,
            "cat-file",
            "blob",
            object_id,
            error=f"git_frozen_blob_unreadable:{relative_path}",
        )
        if current_bytes != committed_bytes:
            raise ValueError(
                f"git_frozen_file_bytes_mismatch:{relative_path}"
            )
        frozen_bytes[relative_path] = current_bytes
    for relative_path, markers in EVALUATION_TIME_CONTRACT_MARKERS.items():
        source = frozen_bytes[relative_path].decode("utf-8")
        if any(marker not in source for marker in markers):
            raise ValueError(
                f"evaluation_time_contract_missing:{relative_path}"
            )
    for relative_path, markers in (
        TRADE_DATE_AUTHORITY_CONTRACT_MARKERS.items()
    ):
        source = frozen_bytes[relative_path].decode("utf-8")
        if any(marker not in source for marker in markers):
            raise ValueError(
                f"n6_trade_date_authority_contract_missing:{relative_path}"
            )
        if "common_trade_calendar" in source:
            raise ValueError(
                f"n6_trade_date_authority_raw_calendar_present:"
                f"{relative_path}"
            )
    for relative_path, markers in AUTO_RESUME_CONTRACT_MARKERS.items():
        source = frozen_bytes[relative_path].decode("utf-8")
        if any(marker not in source for marker in markers):
            raise ValueError(
                f"auto_resume_contract_missing:{relative_path}"
            )
    return frozen_bytes


def _policy_authority(root: Path) -> tuple[str, dict[str, Any], dict[str, str]]:
    src = root / "src"
    sys.path.insert(0, str(src))
    try:
        from ashare_v3.user.strategy_center import (
            APPROVED_PACKAGE_POLICY_HASHES,
            APPROVED_PACKAGE_POLICY_PAYLOADS,
            EVALUATOR_POLICY_HASH,
        )
    finally:
        sys.path.pop(0)
    if not re.fullmatch(r"[0-9a-f]{64}", EVALUATOR_POLICY_HASH):
        raise ValueError("evaluator_policy_hash_invalid")
    package_payloads = {
        key: dict(value)
        for key, value in APPROVED_PACKAGE_POLICY_PAYLOADS.items()
    }
    package_hashes = dict(APPROVED_PACKAGE_POLICY_HASHES)
    if set(package_payloads) != set(ALLOWED_PACKAGE_KEYS):
        raise ValueError("approved_package_policy_payloads_invalid")
    if set(package_hashes) != set(ALLOWED_PACKAGE_KEYS):
        raise ValueError("approved_package_policy_hashes_invalid")
    for package_key in ALLOWED_PACKAGE_KEYS:
        if canonical_hash(package_payloads[package_key]) != package_hashes[package_key]:
            raise ValueError(f"approved_package_policy_hash_invalid:{package_key}")
    return EVALUATOR_POLICY_HASH, package_payloads, package_hashes


def _candidate_package_payload(
    candidate: dict[str, Any], package_key: str
) -> dict[str, Any]:
    return {
        "package_id": candidate["package_id"],
        "strategy_version": candidate["strategy_version"],
        "proposed_policy": candidate["proposed_policy"],
        "package_key": package_key,
        "package_version": candidate["package_versions"][package_key],
        "rules": candidate["rules"],
        "market_heat_indices": candidate["market_heat_indices"],
        "market_heat_policy": candidate["market_heat_policy"],
        "membership_indices": candidate["membership_indices"],
        f"{package_key}_rule": candidate[f"{package_key}_rule"],
        "risk_boundaries": candidate["risk_boundaries"],
    }


def build_bundle(
    root: Path,
    *,
    implementation_commit: str,
    implementation_tree: str,
) -> dict[str, Any]:
    frozen_bytes = _validate_git_frozen_inputs(
        root,
        implementation_commit=implementation_commit,
        implementation_tree=implementation_tree,
    )

    candidate_bytes = frozen_bytes[CANDIDATE_PATH]
    canonical_bytes = frozen_bytes[CANONICAL_PATH]
    if sha256(candidate_bytes).hexdigest() != EXPECTED_CANDIDATE_SHA256:
        raise ValueError("approved_candidate_sha256_mismatch")
    if sha256(canonical_bytes).hexdigest() != EXPECTED_CANONICAL_SHA256:
        raise ValueError("canonical_strategy_sha256_mismatch")
    candidate = json.loads(candidate_bytes.decode("utf-8"))
    if (
        candidate.get("package_id") != PACKAGE_ID
        or candidate.get("strategy_version") != STRATEGY_VERSION
        or candidate.get("proposed_policy") != POLICY_VERSION
        or candidate.get("package_versions")
        != {"package_1": "v2", "package_2": "v2"}
    ):
        raise ValueError("approved_candidate_identity_mismatch")
    risk = candidate.get("risk_boundaries")
    if not isinstance(risk, dict):
        raise ValueError("approved_candidate_risk_boundary_missing")
    for field in (
        "proposal_authorized",
        "order_authorized",
        "trade_authorized",
        "position_or_cash_mutation_authorized",
        "autonomous_trading_authorized",
        "real_trading_authorized",
    ):
        if risk.get(field) is not False:
            raise ValueError(f"approved_candidate_boundary_invalid:{field}")
    if risk.get("display_only") is not True or risk.get("shadow_only") is not True:
        raise ValueError("approved_candidate_shadow_boundary_invalid")
    deployment_gates = candidate.get("deployment_gates")
    if not isinstance(deployment_gates, dict):
        raise ValueError("approved_candidate_deployment_gates_missing")
    if (
        deployment_gates.get(
            "selection_write_quiesce_during_schema_release_transition"
        )
        is not True
        or deployment_gates.get("per_user_compensation_gate")
        != "owner_only_append_only_v1_revision_or_pending_v2_abandonment"
        or deployment_gates.get("v1_grandfather_activation")
        != "separate_gate_after_v2_runtime_ready"
        or deployment_gates.get("catalog_activation_migration")
        != "083_owner_only_fail_closed"
    ):
        raise ValueError("approved_candidate_deployment_gates_invalid")

    runtime_files = []
    for relative_path in RUNTIME_FILES:
        runtime_files.append(
            {
                "path": relative_path,
                "sha256": sha256(frozen_bytes[relative_path]).hexdigest(),
            }
        )

    policy_hash, package_payloads, package_hashes = _policy_authority(root)
    for package_key in ALLOWED_PACKAGE_KEYS:
        if package_payloads[package_key] != _candidate_package_payload(
            candidate, package_key
        ):
            raise ValueError(
                f"approved_candidate_package_policy_mismatch:{package_key}"
            )

    payload: dict[str, Any] = {
        "bundle_id": BUNDLE_ID,
        "bundle_schema_version": 2,
        "package_id": PACKAGE_ID,
        "strategy_version": STRATEGY_VERSION,
        "policy_version": POLICY_VERSION,
        "implementation_commit": implementation_commit,
        "implementation_tree": implementation_tree,
        "implementation_policy_hash": policy_hash,
        "approved_package_policy_hashes": package_hashes,
        "candidate": {
            "path": CANDIDATE_PATH,
            "sha256": EXPECTED_CANDIDATE_SHA256,
        },
        "canonical_strategy": {
            "path": CANONICAL_PATH,
            "sha256": EXPECTED_CANONICAL_SHA256,
        },
        "catalog_artifacts": {
            "migration": {
                "path": MIGRATION_PATH,
                "sha256": sha256(frozen_bytes[MIGRATION_PATH]).hexdigest(),
                "applied": False,
            },
            "rollback": {
                "path": ROLLBACK_PATH,
                "sha256": sha256(frozen_bytes[ROLLBACK_PATH]).hexdigest(),
                "applied": False,
            },
            "user_compensation_migration": {
                "path": COMPENSATION_MIGRATION_PATH,
                "sha256": sha256(
                    frozen_bytes[COMPENSATION_MIGRATION_PATH]
                ).hexdigest(),
                "applied": False,
            },
            "user_compensation_rollback": {
                "path": COMPENSATION_ROLLBACK_PATH,
                "sha256": sha256(
                    frozen_bytes[COMPENSATION_ROLLBACK_PATH]
                ).hexdigest(),
                "applied": False,
            },
            "catalog_activation_migration": {
                "path": ACTIVATION_MIGRATION_PATH,
                "sha256": sha256(
                    frozen_bytes[ACTIVATION_MIGRATION_PATH]
                ).hexdigest(),
                "applied": False,
            },
            "catalog_activation_rollback": {
                "path": ACTIVATION_ROLLBACK_PATH,
                "sha256": sha256(
                    frozen_bytes[ACTIVATION_ROLLBACK_PATH]
                ).hexdigest(),
                "applied": False,
            },
            "trade_date_authority_migration": {
                "path": TRADE_DATE_AUTHORITY_MIGRATION_PATH,
                "sha256": sha256(
                    frozen_bytes[TRADE_DATE_AUTHORITY_MIGRATION_PATH]
                ).hexdigest(),
                "applied": False,
            },
            "trade_date_authority_rollback": {
                "path": TRADE_DATE_AUTHORITY_ROLLBACK_PATH,
                "sha256": sha256(
                    frozen_bytes[TRADE_DATE_AUTHORITY_ROLLBACK_PATH]
                ).hexdigest(),
                "applied": False,
            },
            "single_scope_revision_generated_on_apply": False,
            "all_users_transaction": False,
        },
        "runtime_files": runtime_files,
        "package_versions": {
            "package_1": "v2",
            "package_2": "v2",
        },
        "scheduler_contract": {
            "max_scopes_per_tick": 1,
            "max_runtime_seconds": 12,
            "pending_precedes_active": True,
            "active_replay_pending_precedes_round_robin": True,
            "pending_scope_order": [
                "selection_revision_id",
                "principal_id",
                "user_id",
            ],
            "active_scope_cursor_mode": "persistent_round_robin",
            "future_reviewed_trade_date_status": "WAITING_OPEN_TRADE_DATE",
            "stale_reviewed_trade_date_status":
                "BLOCKED_STALE_TRADE_DATE_AUTHORITY",
            "evidence_phase": "independent_bounded_after_evaluator_deadline",
            "history_persistence":
                "o1_append_atomic_bounded_size_rotation",
            "quiet_logging":
                "state_change_error_success_or_rotation",
            "transaction_scope": "single_principal_user_revision",
            "all_users_transaction": False,
        },
        "runtime_boundary": {
            "display_only": True,
            "shadow_only": True,
            "allowed_write_tables": list(ALLOWED_WRITE_TABLES),
            "forbidden_mutations": list(FORBIDDEN_MUTATIONS),
            "deepseek_required": False,
        },
        "trade_date_authority_contract": {
            "authority": "reviewed_n6_display_view_consensus",
            "required_asset_kinds": ["stock", "index", "board"],
            "per_asset_latest_batch":
                "nonempty_singleton_source_trade_date_for_trade_date_run_id",
            "cross_asset_for_trade_date_consensus_required": True,
            "per_asset_lineage_frozen": [
                "source_trade_date",
                "for_trade_date",
                "source_run_id",
                "row_count",
            ],
            "reviewed_current_date_sources": [
                "user_signal_projection",
                "user_signal_card",
            ],
            "pending_revision_allowed_without_reviewed_events": True,
            "bounded_canary_requires_natural_event_group": True,
            "membership_authority":
                "max_membership_trade_date_lte_event_source_trade_date",
            "common_trade_calendar_required": False,
        },
        "activation": {
            "status": "BLOCKED_PENDING_SCHEMA_RELEASE_CANARY",
            "current_kernel_policy_update_required": False,
            "evaluator_rebind_contract_required": True,
            "fresh_current_reviewed_n6_trade_date_exact_release_canary_required": True,
            "v2_package_catalog_required": True,
            "single_scope_v2_selection_revision_required": True,
            "qualified_and_observation_surfaces_required": True,
            "v2_catalog_build_complete": True,
            "single_scope_v2_selection_revision_build_complete": True,
            "qualified_and_observation_surfaces_build_complete": True,
            "canonical_signal_dto_isolation_build_complete": True,
            "v1_v2_coexistence_build_complete": True,
            "per_user_v2_to_v1_compensation_build_complete": True,
            "failed_pending_v2_abandonment_build_complete": True,
            "v2_catalog_activation_migration_build_complete": True,
            "n6_trade_date_authority_migration_build_complete": True,
            "selection_write_quiesce_during_schema_release_transition_required": True,
            "v1_grandfather_activation_is_separate_gate": True,
            "historical_selection_rewrite_authorized": False,
            "launch_agent_switch_authorized_by_bundle": False,
        },
        "rollback_conditions": list(candidate["rollback_conditions"]),
    }
    _validate_git_frozen_inputs(
        root,
        implementation_commit=implementation_commit,
        implementation_tree=implementation_tree,
    )
    return {**payload, "bundle_sha256": canonical_hash(payload)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--implementation-commit", required=True)
    parser.add_argument("--implementation-tree", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_bundle(
        args.root.resolve(),
        implementation_commit=args.implementation_commit,
        implementation_tree=args.implementation_tree,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
