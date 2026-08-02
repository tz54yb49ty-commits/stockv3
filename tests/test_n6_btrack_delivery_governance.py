from __future__ import annotations

import ast
import copy
from hashlib import sha256
import importlib.util
import json
import plistlib
import posixpath
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "N6_B_TRACK_DELIVERY_GOVERNANCE_V1.json"
REGISTRY_PATH = ROOT / "docs" / "N6_B_TRACK_BASELINE_REGISTRY_V1.json"
SCRIPT_PATH = ROOT / "scripts" / "plan_n6_btrack_delivery.py"
SPEC = importlib.util.spec_from_file_location("plan_n6_btrack_delivery", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

LEGACY_L1_SHA256 = "ff9d899636e0e742d833709eb3e778781522b33b0800557ce2ef30173b2f1a47"
LEGACY_KERNEL_L1_SHA256 = (
    "64c31c8b992029072461aaee430bc44f3724a803ff3edb48ce6a3bb339d5dd13"
)
LEGACY_L1_KEYS = (
    "policy_id",
    "title",
    "classification",
    "implementation_layer_role",
    "deployment_layer_role",
    "maximum_mutating_gates",
    "required_sequence",
    "required_evidence",
    "forbidden_effects",
)
LEGACY_KERNEL_L1_KEYS = (
    "policy_id",
    "policy_family",
    "layer_role",
    "lane",
    "default_runtime_execution_decision",
    "required_brief_fields",
    "allowed_effects",
    "forbidden_effects",
    "max_mutating_gates",
    "governance_session_cannot_execute",
)
CANONICAL_RETIREMENT_EXCLUSION_SET = (
    "config/n6_strategy_center/N6_SC_TEMPORAL_CONFLUENCE_V2_SHADOW_BUNDLE_20260723.json",
    "scripts/build_n6_strategy_center_temporal_confluence_v2_bundle.py",
    "scripts/plan_n6_strategy_center_launchd.py",
    "scripts/run_n6_strategy_center_auto_once.py",
    "scripts/run_n6_strategy_center_once.py",
    "src/ashare_v3/user/strategy_center.py",
    "src/ashare_v3/user/strategy_center_repository.py",
    "src/ashare_v3/user/strategy_center_worker.py",
    "scripts/n6_f464_privileged_materialize_and_install_v2.c",
    "scripts/n6_f464_release_root_owner_remediation_v1.c",
    "src/ashare_v3/runtime_control/resumable_activation.py",
)

PHASE_REQUIRED_VALUES = {
    ("phase_id",): "post_decommission_web_readonly_rebind",
    ("policy_id",): "n6_btrack_delivery_l1_web_readonly_v1",
    ("layer_role",): "runtime_control",
    ("default_decision",): "REJECT",
    ("separate_current_request_authorization_required",): True,
    ("applicability", "l1_classification_decision"): "ACCEPT",
    ("applicability", "candidate_scope"): "web_read_only_ux_only",
    ("applicability", "strategy_surface_state_source"): "decommissioned",
    ("applicability", "strategy_surface_state_target"): "decommissioned",
    ("applicability", "strategy_surface_restore_allowed"): False,
    ("applicability", "non_regression_candidate_required"): True,
    ("exact_services", "web", "label"): "com.ashare-v3.n6.user-web",
    ("exact_services", "web", "only_mutable_service"): True,
    (
        "exact_services",
        "strategy_evaluator",
        "label",
    ): "com.ashare-v3.n6.strategy-center-evaluator-v1",
    ("exact_services", "strategy_evaluator", "job_present"): False,
    ("exact_services", "strategy_evaluator", "pid_present"): False,
    ("exact_services", "strategy_evaluator", "operation_attempts"): 0,
    (
        "exact_services",
        "virtual_executor",
        "label",
    ): "com.ashare-v3.n6.virtual-executor-v1",
    (
        "exact_services",
        "virtual_executor",
        "loaded_and_natural_startinterval_rotation_allowed",
    ): True,
    (
        "exact_services",
        "virtual_executor",
        "pid_or_runs_change_alone_is_drift",
    ): False,
    ("exact_services", "virtual_executor", "operation_attempts"): 0,
    ("strategy_write_contract", "live_before"): 0,
    ("strategy_write_contract", "source_plist"): 0,
    ("strategy_write_contract", "target_plist"): 0,
    ("strategy_write_contract", "after_readiness"): 0,
    ("strategy_write_contract", "after_rollback"): 0,
    ("route_contract", "/n6/app/strategy-center", "method"): "GET",
    ("route_contract", "/n6/app/strategy-center", "status"): 307,
    (
        "route_contract",
        "/n6/app/strategy-center",
        "location",
    ): "/n6/app/signals?notice=strategy_center_retired",
    ("release_contract", "source_immutable"): True,
    ("release_contract", "target_immutable"): True,
    ("release_contract", "target_non_regression_lineage_required"): True,
    ("release_contract", "candidate_exact_diff_allowlist_required"): True,
    ("release_contract", "diff_scope"): "web_only_ux_only_non_strategy",
    (
        "release_contract",
        "strategy_surface_files_or_routes_in_diff_allowed",
    ): False,
    (
        "release_contract",
        "exactly_one_source_evidence_mode_required",
    ): True,
    (
        "release_contract",
        "legacy_read_only_reconstructed_source",
        "pre_manifest_release_only",
    ): True,
    (
        "release_contract",
        "legacy_read_only_reconstructed_source",
        "source_writeback_or_modification_allowed",
    ): False,
    (
        "release_contract",
        "legacy_read_only_reconstructed_source",
        "scope",
    ): "source_and_rollback_freeze_only",
    (
        "release_contract",
        "legacy_read_only_reconstructed_source",
        "may_substitute_for_target_manifest",
    ): False,
    (
        "release_contract",
        "target_release_specific_immutable_manifest",
        "required",
    ): True,
    (
        "release_contract",
        "target_release_specific_immutable_manifest",
        "legacy_reconstruction_allowed",
    ): False,
    ("plist_contract", "only_release_binding_may_change"): True,
    ("plist_contract", "exactly_one_runner_mode_required"): True,
    ("plist_contract", "mixed_runner_mode_allowed"): False,
    (
        "plist_contract",
        "program_arguments",
        "exact_token_count",
    ): 2,
    (
        "plist_contract",
        "program_arguments",
        "source_target_tokens_byte_identical",
    ): True,
    (
        "plist_contract",
        "program_arguments",
        "extra_argv_allowed",
    ): False,
    (
        "plist_contract",
        "program_arguments",
        "relative_script_token",
    ): "scripts/run_n6_user_app.py",
    (
        "plist_contract",
        "program_arguments",
        "relative_script_must_not_be_absolute",
    ): True,
    (
        "plist_contract",
        "program_arguments",
        "relative_script_parent_escape_allowed",
    ): False,
    (
        "plist_contract",
        "program_arguments",
        "working_directory_exact_source_to_target",
    ): True,
    (
        "plist_contract",
        "program_arguments",
        "pythonpath_exact_source_to_target",
    ): True,
    (
        "plist_contract",
        "literal_python3_interpreter",
        "token",
    ): "python3",
    (
        "plist_contract",
        "literal_python3_interpreter",
        "source_target_byte_identical",
    ): True,
    (
        "plist_contract",
        "absolute_system_interpreter",
        "trusted_path_chain_root",
    ): "/Library",
    (
        "plist_contract",
        "absolute_system_interpreter",
        "trusted_boundary",
    ): "/Library/Frameworks/Python.framework/Versions/3.11/bin",
    (
        "plist_contract",
        "absolute_system_interpreter",
        "must_be_absolute",
    ): True,
    ("plist_contract", "absolute_system_interpreter", "release_bound"): False,
    (
        "plist_contract",
        "absolute_system_interpreter",
        "replacement_allowed",
    ): False,
    (
        "plist_contract",
        "absolute_system_interpreter",
        "replacement_attempts",
    ): 0,
    (
        "plist_contract",
        "absolute_system_interpreter",
        "source_target_byte_identical",
    ): True,
    (
        "plist_contract",
        "absolute_system_interpreter",
        "symlink_chain_allowed",
    ): True,
    (
        "plist_contract",
        "absolute_system_interpreter",
        "every_hop_must_remain_in_trusted_boundary",
    ): True,
    (
        "plist_contract",
        "absolute_system_interpreter",
        "escape_cycle_or_ambiguity_allowed",
    ): False,
    (
        "primary_operation_budget",
        "safe_plist_replace_or_swap_attempts",
    ): 1,
    ("primary_operation_budget", "bootout_attempts"): 1,
    ("primary_operation_budget", "minimum_wait_after_bootout_seconds"): 1,
    (
        "primary_operation_budget",
        "old_job_and_pid_absence_required_before_bootstrap",
    ): True,
    ("primary_operation_budget", "bootstrap_attempts"): 1,
    ("primary_operation_budget", "kickstart_attempts"): 0,
    ("primary_operation_budget", "retry_attempts"): 0,
    ("primary_operation_budget", "fallback_or_downgrade_attempts"): 0,
    ("rollback_contract", "trigger"): "primary_failure_only",
    ("rollback_contract", "frozen_source_rollback_max_attempts"): 1,
    ("rollback_contract", "success_path_rollback_attempts"): 0,
    ("rollback_contract", "second_primary_attempt_allowed"): False,
}


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def nested_value(value: object, path: tuple[str, ...]) -> object:
    current = value
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise KeyError(path)
        current = current[key]
    return current


def static_phase_decision(phase: dict[str, object]) -> str:
    try:
        for path, expected in PHASE_REQUIRED_VALUES.items():
            if nested_value(phase, path) != expected:
                return "REJECT"
        routes = phase["route_contract"]
        assert isinstance(routes, dict)
        for path, method in (
            ("/api/n6/app/v3/strategy-center", "GET"),
            ("/api/n6/app/v3/strategy-center/selection", "PUT"),
            ("/api/n6/app/v3/strategy-center/stream", "GET"),
        ):
            row = routes[path]
            assert isinstance(row, dict)
            if row != {
                "method": method,
                "status": 410,
                "cache_control": "no-store",
                "json": {"ok": False, "code": "strategy_center_retired"},
            }:
                return "REJECT"
        executor = phase["exact_services"]
        assert isinstance(executor, dict)
        executor = executor["virtual_executor"]
        assert isinstance(executor, dict)
        if executor["must_be_disjoint_from_web_on"] != [
            "label",
            "plist",
            "release",
            "runner",
            "role",
            "acl",
            "ownership",
            "object_boundary",
            "hash",
        ]:
            return "REJECT"
        plist = phase["plist_contract"]
        assert isinstance(plist, dict)
        if plist["allowed_runner_modes"] != [
            "absolute_immutable_system_interpreter_plus_relative_script",
            "literal_python3_interpreter_plus_relative_script",
        ]:
            return "REJECT"
        if plist["absolute_system_interpreter"]["required_frozen_checks"] != [
            "trusted_path_chain_owner_group_mode_acl_flags",
            "trusted_path_chain_effective_non_writable_by_service_principal",
            "absolute_token_path",
            "symlink_hop_paths",
            "symlink_readlink_text_per_hop",
            "resolved_canonical_path",
            "all_paths_within_trusted_boundary",
            "no_escape_cycle_or_ambiguity",
            "symlink_owner_group_mode_per_hop",
            "resolved_target_regular_file",
            "resolved_target_owner",
            "resolved_target_group",
            "resolved_target_mode",
            "resolved_target_sha256",
            "acl_and_flags_do_not_grant_service_write",
            "service_principal_uid_and_groups",
            "service_principal_is_not_owner",
            "service_principal_not_in_write_enabled_group",
            "effective_non_writable_by_service_principal",
            "source_target_complete_chain_evidence_identical",
        ]:
            return "REJECT"
        if plist["target_relative_script_checks"] != [
            "contained_in_target_release",
            "regular_file",
            "not_symlink",
            "no_write_bits",
            "owner_matches_manifest",
            "mode_matches_manifest",
            "sha256_matches_manifest",
            "manifest_entry_exact",
        ]:
            return "REJECT"
        release = phase["release_contract"]
        assert isinstance(release, dict)
        if release["source_evidence_modes"] != [
            "release_specific_immutable_manifest",
            "legacy_read_only_reconstructed",
        ]:
            return "REJECT"
        if release["canonical_retirement_exclusion_set"] != list(
            CANONICAL_RETIREMENT_EXCLUSION_SET
        ):
            return "REJECT"
        if release["legacy_read_only_reconstructed_source"][
            "required_checks"
        ] != [
            "exact_source_commit",
            "exact_source_tree",
            "exact_canonical_retirement_exclusion_set",
            "full_present_fileset_git_blob_equivalence",
            "full_present_fileset_git_mode_equivalence",
            "no_extra_files",
            "sealed_owner_and_mode",
            "no_write_bits",
            "no_symlinks",
            "deterministic_filesystem_object_sha256",
        ]:
            return "REJECT"
        if release["target_release_specific_immutable_manifest"][
            "required_bindings"
        ] != [
            "target_commit",
            "target_tree",
            "exact_archive_fileset",
            "mode_owner_sha256_per_entry",
            "exact_canonical_retirement_exclusion_set",
            "filesystem_object_sha256",
        ]:
            return "REJECT"
        forbidden = phase["forbidden_effect_counts"]
        assert isinstance(forbidden, dict)
        if set(forbidden) != {
            "database",
            "n1_n5",
            "strategy_evaluator",
            "virtual_executor",
            "business",
            "proposal",
            "cash",
            "position",
            "trade",
        } or any(value != 0 for value in forbidden.values()):
            return "REJECT"
        if set(phase["reject_on"]) != {
            "missing_required_field",
            "classification_drift",
            "mixed_runner_mode",
            "strategy_write_nonzero",
            "strategy_evaluator_present_or_operated",
            "virtual_executor_boundary_or_operation_drift",
            "strategy_route_or_api_drift",
            "strategy_surface_restore",
            "release_or_lineage_drift",
            "diff_allowlist_drift",
            "plist_delta_beyond_release_binding",
            "runner_validation_failure",
            "interpreter_or_argv_drift",
            "legacy_source_reconstruction_drift",
            "target_manifest_missing_or_drifted",
            "operation_count_drift",
            "forbidden_effect_nonzero",
        }:
            return "REJECT"
    except (AssertionError, KeyError, TypeError):
        return "REJECT"
    return "ACCEPT"


def static_runner_decision(
    phase: dict[str, object],
    source_argv: list[str],
    target_argv: list[str],
    *,
    absolute_interpreter_evidence: dict[str, bool] | None = None,
    target_script_evidence: dict[str, bool] | None = None,
    working_directory_rebound_exactly: bool = True,
    pythonpath_rebound_exactly: bool = True,
) -> str:
    plist = phase["plist_contract"]
    assert isinstance(plist, dict)
    program = plist["program_arguments"]
    assert isinstance(program, dict)
    if len(source_argv) != program["exact_token_count"]:
        return "REJECT"
    if source_argv != target_argv:
        return "REJECT"
    if not working_directory_rebound_exactly or not pythonpath_rebound_exactly:
        return "REJECT"

    interpreter, script = source_argv
    script_path = Path(script)
    if script != program["relative_script_token"]:
        return "REJECT"
    if script_path.is_absolute() or ".." in script_path.parts:
        return "REJECT"

    literal = plist["literal_python3_interpreter"]
    absolute = plist["absolute_system_interpreter"]
    assert isinstance(literal, dict) and isinstance(absolute, dict)
    if interpreter == literal["token"]:
        if absolute_interpreter_evidence is not None:
            return "REJECT"
    elif Path(interpreter).is_absolute():
        if absolute["release_bound"] or absolute["replacement_allowed"]:
            return "REJECT"
        if absolute_interpreter_evidence is None:
            return "REJECT"
        if static_absolute_interpreter_evidence_decision(
            absolute,
            interpreter,
            absolute_interpreter_evidence,
        ) != "ACCEPT":
            return "REJECT"
    else:
        return "REJECT"

    required_script_checks = plist["target_relative_script_checks"]
    if target_script_evidence is None:
        return "REJECT"
    if set(target_script_evidence) != set(required_script_checks):
        return "REJECT"
    if not all(target_script_evidence.values()):
        return "REJECT"
    return "ACCEPT"


def static_absolute_interpreter_evidence_decision(
    contract: dict[str, object],
    interpreter_token: str,
    evidence: dict[str, object],
) -> str:
    try:
        if evidence != live_absolute_interpreter_evidence():
            return "REJECT"
        if evidence["replacement_attempts"] != 0:
            return "REJECT"
        source = evidence["source_chain"]
        target_chain = evidence["target_chain"]
        service = evidence["service_principal"]
        assert isinstance(source, dict) and isinstance(target_chain, dict)
        assert isinstance(service, dict)
        if source != target_chain:
            return "REJECT"
        if set(service) != {"uid", "primary_gid", "groups"}:
            return "REJECT"

        boundary = str(contract["trusted_boundary"])
        root = str(contract["trusted_path_chain_root"])
        if not interpreter_token.startswith(boundary + "/"):
            return "REJECT"
        if source["token_path"] != interpreter_token:
            return "REJECT"
        if any(source[key] for key in ("escape", "cycle", "ambiguous")):
            return "REJECT"

        path_chain = source["trusted_path_chain"]
        expected_paths = [
            root,
            root + "/Frameworks",
            root + "/Frameworks/Python.framework",
            root + "/Frameworks/Python.framework/Versions",
            root + "/Frameworks/Python.framework/Versions/3.11",
            boundary,
        ]
        assert isinstance(path_chain, list)
        if [node["path"] for node in path_chain] != expected_paths:
            return "REJECT"
        service_groups = set(service["groups"])

        def effectively_writable(node: dict[str, object]) -> bool:
            mode = int(node["mode"])
            return bool(
                (service["uid"] == node["uid"] and mode & 0o200)
                or (node["gid"] in service_groups and mode & 0o020)
                or mode & 0o002
                or node["acl_write_grant"]
                or node["flags_write_grant"]
            )

        node_fields = {
            "path",
            "uid",
            "gid",
            "mode",
            "acl",
            "flags",
            "acl_write_grant",
            "flags_write_grant",
        }
        for node in path_chain:
            assert isinstance(node, dict)
            if set(node) != node_fields or effectively_writable(node):
                return "REJECT"

        hops = source["symlink_hops"]
        target = source["resolved_target"]
        assert isinstance(hops, list) and hops
        assert isinstance(target, dict) and isinstance(service, dict)

        current = interpreter_token
        seen = set()
        for hop in hops:
            assert isinstance(hop, dict)
            if set(hop) != {
                "path",
                "readlink_text",
                "uid",
                "gid",
                "mode",
                "acl",
                "flags",
                "acl_write_grant",
                "flags_write_grant",
            }:
                return "REJECT"
            if hop["path"] != current or current in seen:
                return "REJECT"
            seen.add(current)
            if effectively_writable(hop):
                return "REJECT"
            link_text = str(hop["readlink_text"])
            if not link_text or posixpath.isabs(link_text):
                return "REJECT"
            current = posixpath.normpath(
                posixpath.join(posixpath.dirname(current), link_text)
            )
            if not current.startswith(boundary + "/"):
                return "REJECT"

        if source["resolved_canonical_path"] != current:
            return "REJECT"
        if target["path"] != current or target["kind"] != "regular_file":
            return "REJECT"
        if set(target) != {
            "path",
            "kind",
            "uid",
            "gid",
            "mode",
            "sha256",
            "acl",
            "flags",
            "acl_write_grant",
            "flags_write_grant",
        }:
            return "REJECT"
        if not target["sha256"] or effectively_writable(target):
            return "REJECT"
        if service["uid"] == target["uid"]:
            return "REJECT"
        if target["mode"] & 0o020 and target["gid"] in service_groups:
            return "REJECT"
        if target["mode"] & 0o002:
            return "REJECT"
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        return "REJECT"
    return "ACCEPT"


def live_absolute_interpreter_evidence() -> dict[str, object]:
    boundary = "/Library/Frameworks/Python.framework/Versions/3.11/bin"

    def path_node(path: str, mode: int, flags: list[str]) -> dict[str, object]:
        return {
            "path": path,
            "uid": 0,
            "gid": 0,
            "mode": mode,
            "acl": [],
            "flags": flags,
            "acl_write_grant": False,
            "flags_write_grant": False,
        }

    chain = {
        "trusted_path_chain": [
            path_node("/Library", 0o755, ["sunlnk"]),
            path_node("/Library/Frameworks", 0o755, ["sunlnk"]),
            path_node("/Library/Frameworks/Python.framework", 0o755, []),
            path_node("/Library/Frameworks/Python.framework/Versions", 0o775, []),
            path_node(
                "/Library/Frameworks/Python.framework/Versions/3.11",
                0o775,
                [],
            ),
            path_node(boundary, 0o775, []),
        ],
        "token_path": boundary + "/python3",
        "symlink_hops": [
            {
                **path_node(boundary + "/python3", 0o775, []),
                "readlink_text": "python3.11",
            }
        ],
        "resolved_canonical_path": boundary + "/python3.11",
        "resolved_target": {
            **path_node(boundary + "/python3.11", 0o775, []),
            "kind": "regular_file",
            "sha256": "09e1a00906ae3a7cf190155f47d0c23fc0b40d207997a9c44c7995ba9db896c2",
        },
        "escape": False,
        "cycle": False,
        "ambiguous": False,
    }
    return {
        "replacement_attempts": 0,
        "service_principal": {
            "uid": 501,
            "primary_gid": 20,
            "groups": [20, 12, 61, 79, 80, 81, 98, 399, 33, 100, 204, 250, 395, 398, 400],
        },
        "source_chain": chain,
        "target_chain": copy.deepcopy(chain),
    }


def strict_manifest_evidence(release: dict[str, object]) -> dict[str, object]:
    manifest = release["target_release_specific_immutable_manifest"]
    assert isinstance(manifest, dict)
    return {
        "release_specific": True,
        "immutable": True,
        "canonical_retirement_exclusion_set": list(
            CANONICAL_RETIREMENT_EXCLUSION_SET
        ),
        **{key: True for key in manifest["required_bindings"]},
    }


def static_release_evidence_decision(
    phase: dict[str, object], evidence: dict[str, object]
) -> str:
    release = phase["release_contract"]
    assert isinstance(release, dict)
    target = evidence.get("target_manifest")
    if not isinstance(target, dict):
        return "REJECT"
    expected_manifest = strict_manifest_evidence(release)
    if target != expected_manifest:
        return "REJECT"

    source_mode = evidence.get("source_mode")
    if source_mode not in release["source_evidence_modes"]:
        return "REJECT"
    source = evidence.get("source")
    if not isinstance(source, dict):
        return "REJECT"
    if source_mode == "release_specific_immutable_manifest":
        return "ACCEPT" if source == expected_manifest else "REJECT"

    legacy = release["legacy_read_only_reconstructed_source"]
    assert isinstance(legacy, dict)
    expected_legacy = {
        "source_modified_or_written_back": False,
        "used_as_target_manifest": False,
        "canonical_retirement_exclusion_set": list(
            CANONICAL_RETIREMENT_EXCLUSION_SET
        ),
        **{key: True for key in legacy["required_checks"]},
    }
    return "ACCEPT" if source == expected_legacy else "REJECT"


def request_payload(**profile: object) -> dict[str, object]:
    return {
        "page_or_feature": "B轨筛选中心",
        "users": "N6 human users",
        "expected_behavior": "更清晰地筛选本人监控对象",
        "affects_virtual_money_proposals_or_positions": False,
        "change_profile": profile,
    }


class N6BTrackDeliveryGovernanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    def test_contract_has_three_reusable_lanes(self) -> None:
        self.assertEqual(
            {
                lane: row["policy_id"]
                for lane, row in self.contract["lanes"].items()
            },
            {
                "L1": "n6_btrack_delivery_l1_web_readonly_v1",
                "L2": "n6_btrack_delivery_l2_n6_business_v1",
                "L3": "n6_btrack_delivery_l3_virtual_runtime_v1",
            },
        )
        self.assertFalse(
            self.contract["policy_lifecycle"][
                "new_one_off_policy_for_normal_n6_delivery_allowed"
            ]
        )

    def test_l1_ui_read_only_classification(self) -> None:
        result = MODULE.classify_request(
            request_payload(ui_only=True, read_only_query_only=True),
            self.contract,
        )
        self.assertEqual(result["decision"], "ACCEPT")
        self.assertEqual(result["lane"], "L1")
        self.assertNotIn("migration", result["required_sequence"])

    def test_l2_business_or_scope_write_classification(self) -> None:
        result = MODULE.classify_request(
            request_payload(monitor_scope_write=True),
            self.contract,
        )
        self.assertEqual(result["decision"], "ACCEPT")
        self.assertEqual(result["lane"], "L2")

    def test_l3_virtual_money_or_runtime_classification(self) -> None:
        payload = request_payload(executor_change=True)
        payload["affects_virtual_money_proposals_or_positions"] = True
        result = MODULE.classify_request(payload, self.contract)
        self.assertEqual(result["decision"], "ACCEPT")
        self.assertEqual(result["lane"], "L3")
        self.assertIn("bounded_virtual_smoke", result["required_sequence"])

    def test_real_trading_and_upstream_writeback_rejected(self) -> None:
        for profile, reason in (
            ({"real_broker": True}, "real_trading_forbidden"),
            ({"writes_n1_n5": True}, "n6_upstream_writeback_forbidden"),
            (
                {"automatic_proposal_creation": True},
                "automatic_proposal_creation_or_confirmation_forbidden",
            ),
        ):
            with self.subTest(profile=profile):
                result = MODULE.classify_request(
                    request_payload(**profile),
                    self.contract,
                )
                self.assertEqual(result["decision"], "REJECT")
                self.assertEqual(result["reason"], reason)

    def test_missing_or_ambiguous_input_blocks(self) -> None:
        result = MODULE.classify_request({}, self.contract)
        self.assertEqual(result["decision"], "BLOCK")
        self.assertEqual(set(result["missing_fields"]), set(MODULE.REQUIRED_BRIEF_FIELDS))
        ambiguous = MODULE.classify_request(request_payload(), self.contract)
        self.assertEqual(ambiguous["decision"], "BLOCK")
        self.assertEqual(ambiguous["reason"], "ambiguous_change_profile")

    def test_mixed_lane_and_new_one_off_policy_are_rejected(self) -> None:
        mixed = MODULE.classify_request(
            request_payload(ui_only=True, n6_schema_change=True),
            self.contract,
        )
        self.assertEqual(mixed["decision"], "BLOCK")
        self.assertEqual(mixed["reason"], "mixed_delivery_lanes")
        one_off = MODULE.classify_request(
            request_payload(
                ui_only=True,
                requested_new_one_off_policy=True,
            ),
            self.contract,
        )
        self.assertEqual(one_off["decision"], "REJECT")
        self.assertEqual(
            one_off["reason"],
            "normal_delivery_must_reuse_lane_policy",
        )

    def test_baseline_registry_is_honest_about_fragmentation(self) -> None:
        self.assertEqual(self.registry["lineage"]["status"], "FRAGMENTED")
        self.assertFalse(self.registry["lineage"]["single_release_ready"])
        self.assertFalse(
            self.registry["canonical_integration"]["deployment_authorized"]
        )
        self.assertEqual(
            self.registry["convergence"]["required_next_gate"],
            "n6_btrack_canonical_integration_fast_forward_v1",
        )
        self.assertEqual(
            self.registry["migration_identity_anomalies"][0]["numeric_id"],
            "087",
        )

    def test_plist_inspection_is_read_only_and_extracts_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "service.plist"
            payload = {
                "WorkingDirectory": (
                    "/tmp/20260727_174450__"
                    "081bd74ae07c327452b2a1fc67bf7df3d73a4b6c"
                )
            }
            with path.open("wb") as handle:
                plistlib.dump(payload, handle)
            fake_git = mock.Mock(returncode=0, stdout="tree-sha\n", stderr="")
            with mock.patch.object(MODULE, "run_git", return_value=fake_git):
                result = MODULE.release_id_from_plist(path)
        self.assertTrue(result["present"])
        self.assertEqual(
            result["commit"],
            "081bd74ae07c327452b2a1fc67bf7df3d73a4b6c",
        )
        self.assertEqual(result["tree"], "tree-sha")

    def test_governance_is_synchronized_across_control_documents(self) -> None:
        policy_ids = {
            row["policy_id"] for row in self.contract["lanes"].values()
        }
        paths = (
            ROOT / "AGENTS.md",
            ROOT / "docs/EXECUTION_COMPILER.md",
            ROOT / "docs/EXECUTION_KERNEL.md",
            ROOT / "docs/EXECUTION_RUNTIME_GATE.md",
            ROOT / "docs/EXECUTION_SANDBOX.md",
            ROOT / "docs/EXECUTION_TEST_SUITE.md",
            ROOT / "docs/EXECUTION_TRACE_SYSTEM.md",
            ROOT / "docs/Architecture.md",
            ROOT / "docs/Roadmap.md",
            ROOT / "docs/Tasks.md",
            ROOT / "docs/RUNTIME_PIPELINE_CONTROL_V0.md",
        )
        for path in paths:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path):
                for policy_id in policy_ids:
                    self.assertIn(policy_id, text)

    def test_planner_has_no_database_or_launchctl_mutation_surface(self) -> None:
        text = SCRIPT_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "psycopg",
            "psql",
            '["launchctl"',
            "['launchctl'",
            "bootout",
            "bootstrap",
            "INSERT INTO",
            "UPDATE ",
            "DELETE FROM",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_l1_legacy_contracts_are_hash_locked(self) -> None:
        l1 = self.contract["lanes"]["L1"]
        legacy = {key: l1[key] for key in LEGACY_L1_KEYS}
        self.assertEqual(canonical_sha256(legacy), LEGACY_L1_SHA256)
        self.assertEqual(l1["legacy_contract_sha256"], LEGACY_L1_SHA256)

        kernel_text = (ROOT / "docs/EXECUTION_KERNEL.md").read_text(
            encoding="utf-8"
        )
        marker = "<!-- policy:n6_btrack_delivery_l1_web_readonly_v1:begin -->"
        block = kernel_text.split(marker, 1)[1].split("```json\n", 1)[1]
        kernel_l1 = json.loads(block.split("\n```", 1)[0])
        kernel_legacy = {key: kernel_l1[key] for key in LEGACY_KERNEL_L1_KEYS}
        self.assertEqual(
            canonical_sha256(kernel_legacy),
            LEGACY_KERNEL_L1_SHA256,
        )
        self.assertEqual(
            kernel_l1["legacy_contract_sha256"],
            LEGACY_KERNEL_L1_SHA256,
        )
        binding = kernel_l1["deployment_phase_contract"]
        self.assertTrue(binding["exact_source_object_required"])
        self.assertEqual(binding["missing_or_source_mismatch_decision"], "REJECT")
        self.assertFalse(binding["governance_session_runtime_operation_allowed"])
        self.assertEqual(
            binding["source_policy_legacy_contract_sha256"],
            LEGACY_L1_SHA256,
        )

    def test_l1_post_decommission_phase_is_exact_and_fail_closed(self) -> None:
        phase = self.contract["lanes"]["L1"]["deployment_phases"][
            "post_decommission_web_readonly_rebind"
        ]
        self.assertEqual(static_phase_decision(phase), "ACCEPT")
        self.assertFalse(
            phase["exact_services"]["virtual_executor"][
                "pid_or_runs_change_alone_is_drift"
            ]
        )
        self.assertEqual(
            phase["route_contract"]["/n6/app/strategy-center"],
            {
                "method": "GET",
                "status": 307,
                "location": "/n6/app/signals?notice=strategy_center_retired",
            },
        )
        retirement_source = (
            ROOT / "tests/test_n6_strategy_center_retirement.py"
        ).read_text(encoding="utf-8")
        tree = compile(retirement_source, "retirement.py", "exec", ast.PyCF_ONLY_AST)
        assignment = next(
            node
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "RELEASE_EXCLUDED_PATHS"
                for target in node.targets
            )
        )
        self.assertEqual(
            tuple(ast.literal_eval(assignment.value)),
            CANONICAL_RETIREMENT_EXCLUSION_SET,
        )

    def test_l1_runner_accepts_live_absolute_and_literal_python3_forms(self) -> None:
        phase = self.contract["lanes"]["L1"]["deployment_phases"][
            "post_decommission_web_readonly_rebind"
        ]
        plist = phase["plist_contract"]
        absolute_checks = live_absolute_interpreter_evidence()
        script_checks = {
            key: True for key in plist["target_relative_script_checks"]
        }
        live_argv = [
            "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3",
            "scripts/run_n6_user_app.py",
        ]
        self.assertEqual(
            static_runner_decision(
                phase,
                live_argv,
                list(live_argv),
                absolute_interpreter_evidence=absolute_checks,
                target_script_evidence=script_checks,
            ),
            "ACCEPT",
        )
        literal_argv = ["python3", "scripts/run_n6_user_app.py"]
        self.assertEqual(
            static_runner_decision(
                phase,
                literal_argv,
                list(literal_argv),
                target_script_evidence=script_checks,
            ),
            "ACCEPT",
        )

    def test_l1_runner_rejects_interpreter_argv_and_script_drift(self) -> None:
        phase = self.contract["lanes"]["L1"]["deployment_phases"][
            "post_decommission_web_readonly_rebind"
        ]
        plist = phase["plist_contract"]
        absolute_checks = live_absolute_interpreter_evidence()
        script_checks = {
            key: True for key in plist["target_relative_script_checks"]
        }
        live = [
            "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3",
            "scripts/run_n6_user_app.py",
        ]
        fixtures = (
            (live, ["python3", live[1]], absolute_checks, script_checks),
            (live + ["--extra"], live + ["--extra"], absolute_checks, script_checks),
            ([live[0], "../scripts/run_n6_user_app.py"], [live[0], "../scripts/run_n6_user_app.py"], absolute_checks, script_checks),
            ([live[0], "/target/scripts/run_n6_user_app.py"], [live[0], "/target/scripts/run_n6_user_app.py"], absolute_checks, script_checks),
            (["python", live[1]], ["python", live[1]], None, script_checks),
            (live, live, None, script_checks),
            (["python3", live[1]], ["python3", live[1]], absolute_checks, script_checks),
        )
        for source, target, interpreter, script in fixtures:
            with self.subTest(source=source, target=target):
                self.assertEqual(
                    static_runner_decision(
                        phase,
                        list(source),
                        list(target),
                        absolute_interpreter_evidence=interpreter,
                        target_script_evidence=script,
                    ),
                    "REJECT",
                )
        chain_drifts = (
            ("path_chain", ("trusted_path_chain", 0, "path"), "/escape"),
            ("path_chain_owner", ("trusted_path_chain", 0, "uid"), 501),
            ("path_chain_group", ("trusted_path_chain", 3, "gid"), 20),
            ("path_chain_mode", ("trusted_path_chain", 0, "mode"), 0o757),
            ("path_chain_acl", ("trusted_path_chain", 0, "acl_write_grant"), True),
            ("path_chain_flags", ("trusted_path_chain", 0, "flags_write_grant"), True),
            ("symlink_hop_path", ("symlink_hops", 0, "path"), "/escape/python3"),
            ("readlink_text", ("symlink_hops", 0, "readlink_text"), "../../escape"),
            ("symlink_owner", ("symlink_hops", 0, "uid"), 501),
            ("symlink_group", ("symlink_hops", 0, "gid"), 20),
            ("symlink_mode", ("symlink_hops", 0, "mode"), 0o777),
            ("symlink_acl", ("symlink_hops", 0, "acl_write_grant"), True),
            ("symlink_flags", ("symlink_hops", 0, "flags_write_grant"), True),
            ("target_hash", ("resolved_target", "sha256"), "drift"),
            ("target_owner", ("resolved_target", "uid"), 501),
            ("target_group", ("resolved_target", "gid"), 20),
            ("target_mode", ("resolved_target", "mode"), 0o777),
            ("target_acl", ("resolved_target", "acl_write_grant"), True),
            ("target_flags", ("resolved_target", "flags_write_grant"), True),
            ("escape", ("escape",), True),
            ("cycle", ("cycle",), True),
            ("ambiguous", ("ambiguous",), True),
        )
        for name, path, replacement in chain_drifts:
            with self.subTest(absolute_chain_drift=name):
                drifted = copy.deepcopy(absolute_checks)
                for side in ("source_chain", "target_chain"):
                    parent = drifted[side]
                    for key in path[:-1]:
                        parent = parent[key]
                    parent[path[-1]] = replacement
                self.assertEqual(
                    static_runner_decision(
                        phase,
                        live,
                        live,
                        absolute_interpreter_evidence=drifted,
                        target_script_evidence=script_checks,
                    ),
                    "REJECT",
                )
        with self.subTest(absolute_chain_drift="source_target_mismatch"):
            drifted = copy.deepcopy(absolute_checks)
            drifted["target_chain"]["resolved_target"]["sha256"] = "drift"
            self.assertEqual(
                static_runner_decision(
                    phase,
                    live,
                    live,
                    absolute_interpreter_evidence=drifted,
                    target_script_evidence=script_checks,
                ),
                "REJECT",
            )
        with self.subTest(absolute_chain_drift="service_group_membership"):
            drifted = copy.deepcopy(absolute_checks)
            drifted["service_principal"]["groups"].append(0)
            self.assertEqual(
                static_runner_decision(
                    phase,
                    live,
                    live,
                    absolute_interpreter_evidence=drifted,
                    target_script_evidence=script_checks,
                ),
                "REJECT",
            )
        for check in script_checks:
            with self.subTest(script_check=check):
                drifted = dict(script_checks)
                drifted[check] = False
                self.assertEqual(
                    static_runner_decision(
                        phase,
                        live,
                        live,
                        absolute_interpreter_evidence=absolute_checks,
                        target_script_evidence=drifted,
                    ),
                    "REJECT",
                )
        with self.subTest(absolute_chain_drift="replacement_attempt"):
            drifted = copy.deepcopy(absolute_checks)
            drifted["replacement_attempts"] = 1
            self.assertEqual(
                static_runner_decision(
                    phase,
                    live,
                    live,
                    absolute_interpreter_evidence=drifted,
                    target_script_evidence=script_checks,
                ),
                "REJECT",
            )

    def test_l1_release_evidence_accepts_legacy_source_with_strict_target(self) -> None:
        phase = self.contract["lanes"]["L1"]["deployment_phases"][
            "post_decommission_web_readonly_rebind"
        ]
        release = phase["release_contract"]
        target = strict_manifest_evidence(release)
        legacy = release["legacy_read_only_reconstructed_source"]
        legacy_source = {
            "source_modified_or_written_back": False,
            "used_as_target_manifest": False,
            "canonical_retirement_exclusion_set": list(
                CANONICAL_RETIREMENT_EXCLUSION_SET
            ),
            **{key: True for key in legacy["required_checks"]},
        }
        self.assertEqual(
            static_release_evidence_decision(
                phase,
                {
                    "source_mode": "legacy_read_only_reconstructed",
                    "source": legacy_source,
                    "target_manifest": target,
                },
            ),
            "ACCEPT",
        )
        self.assertEqual(
            static_release_evidence_decision(
                phase,
                {
                    "source_mode": "release_specific_immutable_manifest",
                    "source": target,
                    "target_manifest": target,
                },
            ),
            "ACCEPT",
        )

    def test_l1_release_evidence_rejects_legacy_or_target_drift(self) -> None:
        phase = self.contract["lanes"]["L1"]["deployment_phases"][
            "post_decommission_web_readonly_rebind"
        ]
        release = phase["release_contract"]
        target = strict_manifest_evidence(release)
        legacy = release["legacy_read_only_reconstructed_source"]
        legacy_source = {
            "source_modified_or_written_back": False,
            "used_as_target_manifest": False,
            "canonical_retirement_exclusion_set": list(
                CANONICAL_RETIREMENT_EXCLUSION_SET
            ),
            **{key: True for key in legacy["required_checks"]},
        }
        for key in legacy["required_checks"]:
            with self.subTest(legacy_check=key):
                source = copy.deepcopy(legacy_source)
                source[key] = False
                self.assertEqual(
                    static_release_evidence_decision(
                        phase,
                        {
                            "source_mode": "legacy_read_only_reconstructed",
                            "source": source,
                            "target_manifest": target,
                        },
                    ),
                    "REJECT",
                )
        for key in target:
            with self.subTest(target_check=key):
                manifest = copy.deepcopy(target)
                manifest[key] = False
                self.assertEqual(
                    static_release_evidence_decision(
                        phase,
                        {
                            "source_mode": "legacy_read_only_reconstructed",
                            "source": legacy_source,
                            "target_manifest": manifest,
                        },
                    ),
                    "REJECT",
                )
        for field, value in (
            ("source_modified_or_written_back", True),
            ("used_as_target_manifest", True),
            (
                "canonical_retirement_exclusion_set",
                [*CANONICAL_RETIREMENT_EXCLUSION_SET, "extra"],
            ),
        ):
            with self.subTest(legacy_field=field):
                source = copy.deepcopy(legacy_source)
                source[field] = value
                self.assertEqual(
                    static_release_evidence_decision(
                        phase,
                        {
                            "source_mode": "legacy_read_only_reconstructed",
                            "source": source,
                            "target_manifest": target,
                        },
                    ),
                    "REJECT",
                )
        self.assertEqual(
            static_release_evidence_decision(
                phase,
                {
                    "source_mode": "legacy_read_only_reconstructed",
                    "source": legacy_source,
                    "target_manifest": legacy_source,
                },
            ),
            "REJECT",
        )

    def test_l1_post_decommission_missing_or_drifted_field_rejects(self) -> None:
        phase = self.contract["lanes"]["L1"]["deployment_phases"][
            "post_decommission_web_readonly_rebind"
        ]
        for path in PHASE_REQUIRED_VALUES:
            with self.subTest(kind="missing", path=path):
                candidate = copy.deepcopy(phase)
                parent = candidate
                for key in path[:-1]:
                    parent = parent[key]
                del parent[path[-1]]
                self.assertEqual(static_phase_decision(candidate), "REJECT")
            with self.subTest(kind="drift", path=path):
                candidate = copy.deepcopy(phase)
                parent = candidate
                for key in path[:-1]:
                    parent = parent[key]
                parent[path[-1]] = "drift"
                self.assertEqual(static_phase_decision(candidate), "REJECT")

        for key in (
            "route_contract",
            "forbidden_effect_counts",
            "reject_on",
        ):
            with self.subTest(kind="missing_top_level", key=key):
                candidate = copy.deepcopy(phase)
                del candidate[key]
                self.assertEqual(static_phase_decision(candidate), "REJECT")

    def test_l1_post_decommission_runner_route_and_effect_drift_rejects(self) -> None:
        phase = self.contract["lanes"]["L1"]["deployment_phases"][
            "post_decommission_web_readonly_rebind"
        ]
        mutations = (
            ("runner_modes", ("plist_contract", "allowed_runner_modes"), []),
            (
                "runner_checks",
                ("plist_contract", "target_relative_script_checks"),
                [],
            ),
            (
                "source_evidence_modes",
                ("release_contract", "source_evidence_modes"),
                [],
            ),
            (
                "retirement_exclusions",
                ("release_contract", "canonical_retirement_exclusion_set"),
                [],
            ),
            (
                "executor_disjoint",
                (
                    "exact_services",
                    "virtual_executor",
                    "must_be_disjoint_from_web_on",
                ),
                [],
            ),
            (
                "api_route",
                (
                    "route_contract",
                    "/api/n6/app/v3/strategy-center",
                    "status",
                ),
                200,
            ),
            (
                "forbidden_effect",
                ("forbidden_effect_counts", "database"),
                1,
            ),
            ("reject_surface", ("reject_on",), []),
        )
        for name, path, replacement in mutations:
            with self.subTest(name=name):
                candidate = copy.deepcopy(phase)
                parent = candidate
                for key in path[:-1]:
                    parent = parent[key]
                parent[path[-1]] = replacement
                self.assertEqual(static_phase_decision(candidate), "REJECT")

    def test_l1_phase_does_not_revive_historical_one_off_policy(self) -> None:
        phase = self.contract["lanes"]["L1"]["deployment_phases"][
            "post_decommission_web_readonly_rebind"
        ]
        phase_text = json.dumps(phase, ensure_ascii=False, sort_keys=True)
        self.assertIsNone(
            re.search(r"n6_strategy_center_[a-z0-9_]*decommission[a-z0-9_]*_v1", phase_text)
        )
        self.assertEqual(
            phase["policy_id"],
            "n6_btrack_delivery_l1_web_readonly_v1",
        )

    def test_l1_post_decommission_contract_is_synchronized(self) -> None:
        paths = (
            ROOT / "AGENTS.md",
            ROOT / "docs/EXECUTION_COMPILER.md",
            ROOT / "docs/EXECUTION_KERNEL.md",
            ROOT / "docs/EXECUTION_RUNTIME_GATE.md",
            ROOT / "docs/EXECUTION_SANDBOX.md",
            ROOT / "docs/EXECUTION_TEST_SUITE.md",
            ROOT / "docs/EXECUTION_TRACE_SYSTEM.md",
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertIn(
                    "post_decommission_web_readonly_rebind",
                    path.read_text(encoding="utf-8"),
                )


if __name__ == "__main__":
    unittest.main()
