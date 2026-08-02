from __future__ import annotations

import ast
import copy
from hashlib import sha256
import importlib.util
import json
import plistlib
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
LEGACY_L2_SHA256 = "1fa5a2d2810fe32656605341859685bca2694f5ac4bb5b7c0a02c1271d5caa20"
LEGACY_KERNEL_L2_SHA256 = (
    "414d17930972249f918616156fda4f37cd1d23154f7d053b5e9d2fae16de88a7"
)
L2_TRIGGER_STATUS_PHASE_SHA256 = (
    "4b6047b093affd3ca31ab7f7ea62f73a80eba0d9bbe25143ffa5c8ca697a8dde"
)
L2_TRIGGER_STATUS_PHASE_ID = "trigger_status_projection_20260731_backfill"
L2_TRIGGER_STATUS_WEB_PHASE_SHA256 = (
    "37d1b82cedeac6e62ab640df64e3587ca9f97e8f07e018450b74c16b44945994"
)
L2_TRIGGER_STATUS_WEB_REGISTRY_SHA256 = (
    "af9039218167ca60a4027f9353ce9328c2e782109cf6de4935680a25584357d7"
)
L2_TRIGGER_STATUS_WEB_PHASE_ID = "trigger_status_web_immutable_release_rebind"
L2_TRIGGER_STATUS_WEB_RECOVERY_PHASE_ID = (
    "trigger_status_web_failed_release_recovery_once_v1"
)
L2_TRIGGER_STATUS_WEB_RECOVERY_PHASE_SHA256 = (
    "09b5864c49c5db0bf279dee7fda76b0f48c2603a9320452d2ea5da40650e905b"
)
L2_TRIGGER_STATUS_WEB_RECOVERY_REGISTRY_SHA256 = (
    "1b13dc9169ff1609d8e262453cff135cb0dc8338e7eeead550180026cf2232cc"
)
L2_TRIGGER_STATUS_WEB_RECOVERY_REQUEST = {
    "policy_id": "n6_btrack_delivery_l2_n6_business_v1",
    "phase_id": L2_TRIGGER_STATUS_WEB_RECOVERY_PHASE_ID,
    "operation_class": "single_web_immutable_release_rebind_eacces_recovery",
    "executor_role": "runtime_control",
    "current_request_authorized": True,
    "governance_session": False,
    "prior_phase_consumed": True,
    "failed_evidence_matches": True,
    "current_state_matches": True,
    "invalid_staging_preserved_in_place": True,
    "fresh_release_id_and_path": True,
    "prior_recovery_execution_count": 0,
}
L2_TRIGGER_STATUS_REVIEWED_FILES = (
    "AGENTS.md",
    "docs/Architecture.md",
    "docs/EXECUTION_COMPILER.md",
    "docs/EXECUTION_KERNEL.md",
    "docs/EXECUTION_RUNTIME_GATE.md",
    "docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md",
    "docs/N5_CANONICAL_ACTION_FLOW_v0.1.md",
    "docs/N5_N6_TRIGGER_STATUS_FORWARD_CONTRACT_V1.md",
    "docs/N6_B_TRACK_DELIVERY_GOVERNANCE_V1.json",
    "docs/Tasks.md",
    "scripts/run_n5_trigger_status_forward_once.py",
    "scripts/run_n6_trigger_status_projection_once.py",
    "sql/089_n6_trigger_status_current.sql",
    "sql/089_n6_trigger_status_current_rollback.sql",
    "sql/N5_trigger_status_forward_only_rollback.sql",
    "sql/N6_trigger_status_projection_20260731_backfill_v1_exact_rollback.sql",
    "src/ashare_v3/action/live_tracking_poller.py",
    "src/ashare_v3/events/models.py",
    "src/ashare_v3/user/trigger_status_projection.py",
    "src/ashare_v3/web/n6_app_v1.py",
    "src/ashare_v3/web/n6_user_app.py",
    "src/ashare_v3/web/templates/n6_app_shell.html",
    "tests/test_n5_n6_trigger_status_forward_contract.py",
    "tests/test_n6_btrack_delivery_governance.py",
    "tests/test_n6_trigger_status_pg16.py",
    "tests/test_n6_trigger_status_projection.py",
    "tests/test_n6_user_app.py",
)
L2_WEB_REQUEST = {
    "policy_id": "n6_btrack_delivery_l2_n6_business_v1",
    "phase_id": L2_TRIGGER_STATUS_WEB_PHASE_ID,
    "operation_class": "single_web_immutable_release_rebind",
    "executor_role": "runtime_control",
    "requested_service_labels": ["com.ashare-v3.n6.user-web"],
    "prior_successful_execution_count": 0,
    "strategy_write": 0,
    "strategy_evaluator_baseline_frozen": True,
    "strategy_evaluator_operation_attempts": 0,
    "virtual_executor_loaded": True,
    "virtual_executor_operation_attempts": 0,
    "target_release_path_preexisting": False,
}
LEGACY_L2_KEYS = (
    "policy_id",
    "title",
    "classification",
    "implementation_layer_role",
    "migration_layer_role",
    "release_rebind_layer_role",
    "required_sequence",
    "required_evidence",
    "forbidden_effects",
)
LEGACY_KERNEL_L2_KEYS = (
    "policy_id",
    "policy_family",
    "layer_role",
    "lane",
    "default_runtime_execution_decision",
    "required_phases",
    "required_controls",
    "forbidden_effects",
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
RUNNER_MODES = (
    "absolute_immutable_system_interpreter_plus_relative_script",
    "literal_python3_interpreter_plus_relative_script",
)
ABSOLUTE_INTERPRETER_FROZEN_CHECKS = (
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
)
TARGET_RELATIVE_SCRIPT_CHECKS = (
    "contained_in_target_release",
    "regular_file",
    "not_symlink",
    "no_write_bits",
    "owner_matches_manifest",
    "mode_matches_manifest",
    "sha256_matches_manifest",
    "manifest_entry_exact",
)
SOURCE_EVIDENCE_MODES = (
    "release_specific_immutable_manifest",
    "legacy_read_only_reconstructed",
)
LEGACY_SOURCE_CHECKS = (
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
)
TARGET_MANIFEST_BINDINGS = (
    "target_commit",
    "target_tree",
    "exact_archive_fileset",
    "mode_owner_sha256_per_entry",
    "exact_canonical_retirement_exclusion_set",
    "filesystem_object_sha256",
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
    ("release_contract", "exactly_one_source_evidence_mode_required"): True,
    ("release_contract", "legacy_read_only_reconstructed_source", "pre_manifest_release_only"): True,
    ("release_contract", "legacy_read_only_reconstructed_source", "source_writeback_or_modification_allowed"): False,
    ("release_contract", "legacy_read_only_reconstructed_source", "scope"): "source_and_rollback_freeze_only",
    ("release_contract", "legacy_read_only_reconstructed_source", "may_substitute_for_target_manifest"): False,
    ("release_contract", "target_release_specific_immutable_manifest", "required"): True,
    ("release_contract", "target_release_specific_immutable_manifest", "legacy_reconstruction_allowed"): False,
    ("plist_contract", "only_release_binding_may_change"): True,
    ("plist_contract", "exactly_one_runner_mode_required"): True,
    ("plist_contract", "mixed_runner_mode_allowed"): False,
    ("plist_contract", "program_arguments", "exact_token_count"): 2,
    ("plist_contract", "program_arguments", "source_target_tokens_byte_identical"): True,
    ("plist_contract", "program_arguments", "extra_argv_allowed"): False,
    ("plist_contract", "program_arguments", "relative_script_token"): "scripts/run_n6_user_app.py",
    ("plist_contract", "program_arguments", "relative_script_must_not_be_absolute"): True,
    ("plist_contract", "program_arguments", "relative_script_parent_escape_allowed"): False,
    ("plist_contract", "program_arguments", "working_directory_exact_source_to_target"): True,
    ("plist_contract", "program_arguments", "pythonpath_exact_source_to_target"): True,
    ("plist_contract", "literal_python3_interpreter", "token"): "python3",
    ("plist_contract", "literal_python3_interpreter", "source_target_byte_identical"): True,
    ("plist_contract", "absolute_system_interpreter", "trusted_path_chain_root"): "/Library",
    ("plist_contract", "absolute_system_interpreter", "trusted_boundary"): "/Library/Frameworks/Python.framework/Versions/3.11/bin",
    ("plist_contract", "absolute_system_interpreter", "must_be_absolute"): True,
    ("plist_contract", "absolute_system_interpreter", "release_bound"): False,
    ("plist_contract", "absolute_system_interpreter", "replacement_allowed"): False,
    ("plist_contract", "absolute_system_interpreter", "replacement_attempts"): 0,
    ("plist_contract", "absolute_system_interpreter", "source_target_byte_identical"): True,
    ("plist_contract", "absolute_system_interpreter", "symlink_chain_allowed"): True,
    ("plist_contract", "absolute_system_interpreter", "every_hop_must_remain_in_trusted_boundary"): True,
    ("plist_contract", "absolute_system_interpreter", "escape_cycle_or_ambiguity_allowed"): False,
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
        if tuple(plist["allowed_runner_modes"]) != RUNNER_MODES:
            return "REJECT"
        if tuple(
            plist["absolute_system_interpreter"]["required_frozen_checks"]
        ) != ABSOLUTE_INTERPRETER_FROZEN_CHECKS:
            return "REJECT"
        if tuple(plist["target_relative_script_checks"]) != (
            TARGET_RELATIVE_SCRIPT_CHECKS
        ):
            return "REJECT"
        release = phase["release_contract"]
        assert isinstance(release, dict)
        if tuple(release["source_evidence_modes"]) != SOURCE_EVIDENCE_MODES:
            return "REJECT"
        if release["canonical_retirement_exclusion_set"] != list(
            CANONICAL_RETIREMENT_EXCLUSION_SET
        ):
            return "REJECT"
        if tuple(
            release["legacy_read_only_reconstructed_source"]["required_checks"]
        ) != LEGACY_SOURCE_CHECKS:
            return "REJECT"
        if tuple(
            release["target_release_specific_immutable_manifest"][
                "required_bindings"
            ]
        ) != TARGET_MANIFEST_BINDINGS:
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


def l2_web_phase_request(**overrides: object) -> dict[str, object]:
    request = copy.deepcopy(L2_WEB_REQUEST)
    request.update(overrides)
    return request


def static_l2_web_phase_decision(
    phase: dict[str, object], request: dict[str, object]
) -> str:
    return (
        "ACCEPT"
        if canonical_sha256(phase) == L2_TRIGGER_STATUS_WEB_PHASE_SHA256
        and request == L2_WEB_REQUEST
        else "REJECT"
    )


def l2_web_recovery_request(**overrides: object) -> dict[str, object]:
    request = copy.deepcopy(L2_TRIGGER_STATUS_WEB_RECOVERY_REQUEST)
    request.update(overrides)
    return request


def static_l2_web_recovery_phase_decision(
    phase: dict[str, object], request: dict[str, object]
) -> str:
    return (
        "ACCEPT"
        if canonical_sha256(phase) == L2_TRIGGER_STATUS_WEB_RECOVERY_PHASE_SHA256
        and request == L2_TRIGGER_STATUS_WEB_RECOVERY_REQUEST
        else "REJECT"
    )


def request_payload(**profile: object) -> dict[str, object]:
    return {
        "page_or_feature": "B轨筛选中心",
        "users": "N6 human users",
        "expected_behavior": "更清晰地筛选本人监控对象",
        "affects_virtual_money_proposals_or_positions": False,
        "change_profile": profile,
    }


def mutated_fixture(
    value: dict[str, object],
    path: tuple[str, ...],
    replacement: object,
) -> dict[str, object]:
    candidate = copy.deepcopy(value)
    parent = candidate
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = replacement
    return candidate


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
            self.registry["canonical_integration"]["current_commit"],
            "985202144febffeef3302012675f285e1cf1061a",
        )
        self.assertEqual(
            self.registry["canonical_integration"]["current_tree"],
            "f741f0f0cd7d80648f9897267eb0b2ac8410f9f0",
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

    def test_l1_static_runner_and_release_examples_are_exact(self) -> None:
        phase = self.contract["lanes"]["L1"]["deployment_phases"][
            "post_decommission_web_readonly_rebind"
        ]
        plist = phase["plist_contract"]
        program = plist["program_arguments"]
        script = program["relative_script_token"]
        runner_examples = (
            (RUNNER_MODES[0], plist["absolute_system_interpreter"]["trusted_boundary"] + "/python3"),
            (RUNNER_MODES[1], plist["literal_python3_interpreter"]["token"]),
        )
        self.assertEqual(tuple(mode for mode, _ in runner_examples), RUNNER_MODES)
        for mode, interpreter in runner_examples:
            with self.subTest(mode=mode):
                self.assertEqual(program["exact_token_count"], 2)
                self.assertEqual([interpreter, script][1], "scripts/run_n6_user_app.py")
                self.assertFalse(Path(script).is_absolute())
                self.assertNotIn("..", Path(script).parts)

        absolute = plist["absolute_system_interpreter"]
        self.assertEqual(
            tuple(absolute["required_frozen_checks"]),
            ABSOLUTE_INTERPRETER_FROZEN_CHECKS,
        )
        self.assertEqual(
            tuple(plist["target_relative_script_checks"]),
            TARGET_RELATIVE_SCRIPT_CHECKS,
        )
        for key in (
            "source_target_tokens_byte_identical",
            "working_directory_exact_source_to_target",
            "pythonpath_exact_source_to_target",
        ):
            self.assertTrue(program[key])
        self.assertFalse(program["extra_argv_allowed"])
        self.assertTrue(absolute["symlink_chain_allowed"])
        self.assertTrue(absolute["every_hop_must_remain_in_trusted_boundary"])
        self.assertFalse(absolute["escape_cycle_or_ambiguity_allowed"])
        self.assertTrue(absolute["source_target_byte_identical"])
        self.assertEqual(absolute["replacement_attempts"], 0)

        release = phase["release_contract"]
        legacy = release["legacy_read_only_reconstructed_source"]
        target = release["target_release_specific_immutable_manifest"]
        self.assertEqual(tuple(release["source_evidence_modes"]), SOURCE_EVIDENCE_MODES)
        self.assertEqual(tuple(legacy["required_checks"]), LEGACY_SOURCE_CHECKS)
        self.assertEqual(legacy["scope"], "source_and_rollback_freeze_only")
        self.assertFalse(legacy["source_writeback_or_modification_allowed"])
        self.assertFalse(legacy["may_substitute_for_target_manifest"])
        self.assertTrue(target["required"])
        self.assertFalse(target["legacy_reconstruction_allowed"])
        self.assertEqual(tuple(target["required_bindings"]), TARGET_MANIFEST_BINDINGS)

    def test_l1_security_drift_examples_fail_closed(self) -> None:
        phase = self.contract["lanes"]["L1"]["deployment_phases"][
            "post_decommission_web_readonly_rebind"
        ]
        absolute = ("plist_contract", "absolute_system_interpreter")
        target = ("release_contract", "target_release_specific_immutable_manifest")
        legacy = ("release_contract", "legacy_read_only_reconstructed_source")
        frozen = list(ABSOLUTE_INTERPRETER_FROZEN_CHECKS)
        bindings = list(TARGET_MANIFEST_BINDINGS)
        without = lambda values, item: [value for value in values if value != item]
        mutations = (
            ("symlink_escape", absolute + ("every_hop_must_remain_in_trusted_boundary",), False),
            ("symlink_cycle", absolute + ("escape_cycle_or_ambiguity_allowed",), True),
            ("symlink_hop_drift", absolute + ("required_frozen_checks",), without(frozen, "symlink_readlink_text_per_hop")),
            ("principal_owner_write", absolute + ("required_frozen_checks",), without(frozen, "service_principal_is_not_owner")),
            ("principal_group_write", absolute + ("required_frozen_checks",), without(frozen, "service_principal_not_in_write_enabled_group")),
            ("principal_acl_write", absolute + ("required_frozen_checks",), without(frozen, "acl_and_flags_do_not_grant_service_write")),
            ("source_target_drift", absolute + ("source_target_byte_identical",), False),
            ("target_manifest_missing", target + ("required",), False),
            ("target_manifest_drift", target + ("required_bindings",), without(bindings, "target_tree")),
            ("legacy_target_substitution", legacy + ("may_substitute_for_target_manifest",), True),
        )
        for name, path, replacement in mutations:
            with self.subTest(name=name):
                candidate = mutated_fixture(phase, path, replacement)
                self.assertEqual(static_phase_decision(candidate), "REJECT")

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

    def test_l2_legacy_contracts_are_hash_locked(self) -> None:
        l2 = self.contract["lanes"]["L2"]
        legacy = {key: l2[key] for key in LEGACY_L2_KEYS}
        self.assertEqual(canonical_sha256(legacy), LEGACY_L2_SHA256)

        kernel_text = (ROOT / "docs/EXECUTION_KERNEL.md").read_text(
            encoding="utf-8"
        )
        marker = "<!-- policy:n6_btrack_delivery_l2_n6_business_v1:begin -->"
        block = kernel_text.split(marker, 1)[1].split("```json\n", 1)[1]
        kernel_l2 = json.loads(block.split("\n```", 1)[0])
        kernel_legacy = {key: kernel_l2[key] for key in LEGACY_KERNEL_L2_KEYS}
        self.assertEqual(
            canonical_sha256(kernel_legacy),
            LEGACY_KERNEL_L2_SHA256,
        )
        binding = kernel_l2["bounded_consumer_phase_contract"]
        self.assertEqual(binding["phase_id"], L2_TRIGGER_STATUS_PHASE_ID)
        self.assertEqual(binding["layer_role"], "N6_user")
        self.assertTrue(binding["exact_source_object_required"])
        self.assertEqual(binding["missing_or_source_mismatch_decision"], "REJECT")
        self.assertFalse(binding["governance_session_runtime_operation_allowed"])
        web_binding = kernel_l2["web_deployment_phase_contract"]
        self.assertEqual(web_binding["phase_id"], L2_TRIGGER_STATUS_WEB_PHASE_ID)
        self.assertEqual(
            web_binding["operation_class"],
            "single_web_immutable_release_rebind",
        )
        self.assertEqual(web_binding["executor_role"], "runtime_control")
        self.assertTrue(web_binding["exact_source_object_required"])
        self.assertEqual(
            web_binding["legacy_named_policy_or_l1_substitution_decision"],
            "REJECT",
        )
        self.assertFalse(web_binding["governance_session_runtime_operation_allowed"])

    def test_l2_trigger_status_backfill_phase_is_exact_and_fail_closed(self) -> None:
        phase = self.contract["lanes"]["L2"]["bounded_consumer_phases"][
            L2_TRIGGER_STATUS_PHASE_ID
        ]
        self.assertEqual(canonical_sha256(phase), L2_TRIGGER_STATUS_PHASE_SHA256)
        self.assertEqual(phase["policy_id"], "n6_btrack_delivery_l2_n6_business_v1")
        self.assertEqual(phase["layer_role"], "N6_user")
        self.assertEqual(phase["default_decision"], "REJECT")
        self.assertTrue(phase["separate_current_request_authorization_required"])
        self.assertTrue(phase["governance_session_cannot_execute"])

        scope = phase["scope_lock"]
        self.assertEqual(scope["consumer_name"], "n6_trigger_status_projection_v1")
        self.assertEqual(scope["for_trade_date"], "20260731")
        self.assertEqual(
            scope["projection_run_id"],
            "n6_trigger_status_projection_20260731_backfill_v1",
        )
        self.assertEqual(scope["runner"], "scripts/run_n6_trigger_status_projection_once.py")
        self.assertEqual(scope["limit"], 2296)
        self.assertEqual(scope["bounded_run_once_invocations"], 1)
        self.assertEqual(scope["execute_attempts"], 1)
        self.assertEqual(scope["retry_attempts"], 0)
        self.assertFalse(scope["arbitrary_date_or_current_date_bypass_allowed"])

        input_contract = phase["input_contract"]
        self.assertEqual(input_contract["read_table"], "common_event_outbox")
        self.assertEqual(input_contract["access"], "SELECT_ONLY")
        self.assertEqual(input_contract["selected_input_count"], 2296)
        self.assertEqual(input_contract["min_outbox_id"], 4103761)
        self.assertEqual(input_contract["max_outbox_id"], 4107616)
        self.assertEqual(
            input_contract["event_type_counts"],
            {
                "ActionEligible": 1042,
                "ActionExecuted": 723,
                "TriggerStatusUpdated": 194,
                "TriggerStatusInvalidated": 337,
            },
        )
        self.assertEqual(sum(input_contract["event_type_counts"].values()), 2296)
        self.assertEqual(input_contract["other_event_type_count"], 0)

        mutation = phase["mutation_contract"]
        self.assertEqual(
            mutation["allowed_write_tables"],
            [
                "n6_trigger_status_current",
                "common_event_inbox",
                "common_event_consumer_checkpoint",
            ],
        )
        self.assertEqual(mutation["common_event_outbox_status_updates"], 0)
        self.assertEqual(phase["semantic_locks"]["ActionExecuted"], "no_op")
        self.assertFalse(
            phase["semantic_locks"][
                "trigger_pct_allowed_in_trigger_status_schema_api_ui_or_payload"
            ]
        )
        self.assertFalse(
            phase["semantic_locks"][
                "action_eligible_immutable_payload_mutation_allowed"
            ]
        )

        rollback = phase["rollback_prerequisite"]
        self.assertTrue(rollback["required_before_execute"])
        self.assertTrue(rollback["static_verification_required"])
        self.assertTrue(rollback["pg16_verification_required"])
        self.assertFalse(rollback["drop_089_table_allowed"])
        self.assertFalse(rollback["delete_other_consumer_or_projection_state_allowed"])
        self.assertFalse(rollback["existing_089_schema_rollback_acceptable"])
        self.assertFalse(rollback["rollback_execution_in_this_phase_allowed"])

    def test_l2_trigger_status_backfill_phase_drift_rejects(self) -> None:
        phase = self.contract["lanes"]["L2"]["bounded_consumer_phases"][
            L2_TRIGGER_STATUS_PHASE_ID
        ]

        def decision(candidate: object) -> str:
            return (
                "ACCEPT"
                if canonical_sha256(candidate) == L2_TRIGGER_STATUS_PHASE_SHA256
                else "REJECT"
            )

        self.assertEqual(decision(phase), "ACCEPT")
        mutations = (
            ("date", ("scope_lock", "for_trade_date"), "20260803"),
            ("run", ("scope_lock", "projection_run_id"), "other"),
            ("limit", ("scope_lock", "limit"), 2295),
            ("retry", ("scope_lock", "retry_attempts"), 1),
            ("census", ("input_contract", "selected_input_count"), 2295),
            ("outbox_write", ("mutation_contract", "common_event_outbox_status_updates"), 1),
            ("protected_consumer", ("protected_consumers",), []),
            ("drop_table", ("rollback_prerequisite", "drop_089_table_allowed"), True),
            ("trigger_pct", (
                "semantic_locks",
                "trigger_pct_allowed_in_trigger_status_schema_api_ui_or_payload",
            ), True),
        )
        for name, path, replacement in mutations:
            with self.subTest(name=name):
                self.assertEqual(
                    decision(mutated_fixture(phase, path, replacement)),
                    "REJECT",
                )

        for key in phase:
            with self.subTest(missing=key):
                candidate = copy.deepcopy(phase)
                del candidate[key]
                self.assertEqual(decision(candidate), "REJECT")

    def test_l2_trigger_status_backfill_contract_is_synchronized(self) -> None:
        paths = (
            ROOT / "AGENTS.md",
            ROOT / "docs/N6_B_TRACK_DELIVERY_GOVERNANCE_V1.json",
            ROOT / "docs/EXECUTION_KERNEL.md",
            ROOT / "docs/EXECUTION_COMPILER.md",
            ROOT / "docs/EXECUTION_RUNTIME_GATE.md",
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertIn(
                    L2_TRIGGER_STATUS_PHASE_ID,
                    path.read_text(encoding="utf-8"),
                )

    def test_l2_trigger_status_web_phase_is_exact_and_registered(self) -> None:
        phase = self.contract["lanes"]["L2"]["deployment_phases"][
            L2_TRIGGER_STATUS_WEB_PHASE_ID
        ]
        self.assertEqual(canonical_sha256(phase), L2_TRIGGER_STATUS_WEB_PHASE_SHA256)
        expected = {
            ("policy_id",): "n6_btrack_delivery_l2_n6_business_v1",
            ("operation_class",): "single_web_immutable_release_rebind",
            ("executor_role",): "runtime_control",
            ("governance_session_cannot_execute",): True,
            ("canonical_target", "commit"): "985202144febffeef3302012675f285e1cf1061a",
            ("canonical_target", "tree"): "f741f0f0cd7d80648f9897267eb0b2ac8410f9f0",
            ("canonical_target", "exact_changed_file_count"): 27,
            ("completed_prerequisite_evidence", "schema_089", "status"): "PASS",
            ("completed_prerequisite_evidence", "trigger_status_consumer", "processed_input_count"): 2296,
            ("active_source_and_rollback_target", "unique_rollback_target_required"): True,
            ("active_source_and_rollback_target", "observed_pid"): 67945,
            ("active_source_and_rollback_target", "listen_port"): 8786,
            ("fresh_immutable_release_contract", "fresh_release_count"): 1,
            ("service_rebind_contract", "exact_label"): "com.ashare-v3.n6.user-web",
            ("service_rebind_contract", "bootout_attempts"): 1,
            ("service_rebind_contract", "bootstrap_attempts"): 1,
            ("service_rebind_contract", "retry_attempts"): 0,
            ("service_rebind_contract", "second_primary_attempt_allowed"): False,
            ("business_state_contract", "trigger_status_surface", "trigger_pct_allowed_in_schema_api_ui_or_payload"): False,
            ("route_contract", "unauthenticated", "/api/n6/app/v3/strategy-center", "status"): 410,
            ("route_contract", "unauthenticated", "/api/n6/app/v1/status-monitor", "status"): 401,
            ("route_contract", "unauthenticated_curl_methods_allowed"): ["GET", "HEAD"],
            ("route_contract", "authenticated_session_or_browser_use_allowed"): False,
            ("postflight_contract", "authenticated_dom_acceptance", "mobile_viewports_required"): [320, 375, 390, 430],
        }
        for path, value in expected.items():
            with self.subTest(path=path):
                self.assertEqual(nested_value(phase, path), value)
        self.assertEqual(
            tuple(phase["canonical_target"]["exact_changed_files"]),
            L2_TRIGGER_STATUS_REVIEWED_FILES,
        )
        registration = self.registry["append_only_gate_registrations"][
            L2_TRIGGER_STATUS_WEB_PHASE_ID
        ]
        self.assertEqual(canonical_sha256(registration), L2_TRIGGER_STATUS_WEB_REGISTRY_SHA256)
        self.assertFalse(registration["deployment_authorized"])
        self.assertFalse(registration["runtime_refreshed_in_this_governance_gate"])
        self.assertEqual(registration["previous_release_gate"]["result"], "BLOCKED_POLICY")
        counts = registration["previous_release_gate"]
        self.assertFalse(any(value for key, value in counts.items() if key != "result"))

    def test_l2_trigger_status_web_machine_classifier_is_fail_closed(self) -> None:
        phase = self.contract["lanes"]["L2"]["deployment_phases"][
            L2_TRIGGER_STATUS_WEB_PHASE_ID
        ]
        self.assertEqual(
            static_l2_web_phase_decision(phase, l2_web_phase_request()),
            "ACCEPT",
        )
        rejected_requests = (
            ("old_named_policy", {"policy_id": "n6_user_web_immutable_release_bounded_rebind_v1"}),
            ("l1_policy", {"policy_id": "n6_btrack_delivery_l1_web_readonly_v1"}),
            ("l1_phase", {"phase_id": "post_decommission_web_readonly_rebind"}),
            ("operation", {"operation_class": "install_only"}),
            ("role", {"executor_role": "N6_user"}),
            ("expanded_scope", {"requested_service_labels": [
                "com.ashare-v3.n6.user-web",
                "com.ashare-v3.n6.virtual-executor-v1",
            ]}),
            ("strategy_write", {"strategy_write": 1}),
            ("evaluator_state", {"strategy_evaluator_baseline_frozen": False}),
            ("evaluator_operation", {"strategy_evaluator_operation_attempts": 1}),
            ("virtual_executor_state", {"virtual_executor_loaded": False}),
            ("virtual_executor_operation", {"virtual_executor_operation_attempts": 1}),
            ("release_reuse", {"target_release_path_preexisting": True}),
            ("second_execution", {"prior_successful_execution_count": 1}),
        )
        for name, overrides in rejected_requests:
            with self.subTest(name=name):
                self.assertEqual(
                    static_l2_web_phase_decision(
                        phase,
                        l2_web_phase_request(**overrides),
                    ),
                    "REJECT",
                )

    def test_l2_trigger_status_web_phase_drift_rejects(self) -> None:
        phase = self.contract["lanes"]["L2"]["deployment_phases"][
            L2_TRIGGER_STATUS_WEB_PHASE_ID
        ]
        mutations = (
            ("target", ("canonical_target", "commit"), "other"),
            ("lineage", ("canonical_target", "exact_changed_file_count"), 28),
            ("migration", ("completed_prerequisite_evidence", "schema_089", "status"), "BLOCKED"),
            ("consumer", ("completed_prerequisite_evidence", "trigger_status_consumer", "processed_input_count"), 2295),
            ("source", ("active_source_and_rollback_target", "plist_sha256"), "other"),
            ("strategy", ("business_state_contract", "strategy_write", "live_before"), 1),
            ("executor", ("business_state_contract", "virtual_executor", "loaded"), False),
            ("release", ("fresh_immutable_release_contract", "fresh_release_count"), 2),
            ("plist", ("service_rebind_contract", "allowed_plist_semantic_deltas"), []),
            ("second_bootout", ("service_rebind_contract", "bootout_attempts"), 2),
            ("curl", ("route_contract", "unauthenticated_curl_methods_allowed"), ["GET", "HEAD", "POST"]),
            ("postflight", ("postflight_contract", "required_exact_evidence"), []),
            ("database", ("forbidden_effect_counts", "database_connections"), 1),
        )
        for name, path, replacement in mutations:
            with self.subTest(name=name):
                candidate = mutated_fixture(phase, path, replacement)
                self.assertEqual(
                    static_l2_web_phase_decision(candidate, l2_web_phase_request()),
                    "REJECT",
                )
        for key in phase:
            with self.subTest(missing=key):
                candidate = copy.deepcopy(phase)
                del candidate[key]
                self.assertEqual(
                    static_l2_web_phase_decision(candidate, l2_web_phase_request()),
                    "REJECT",
                )

    def test_l2_trigger_status_web_recovery_is_exact_and_registered(self) -> None:
        phase = self.contract["lanes"]["L2"]["deployment_phases"][
            L2_TRIGGER_STATUS_WEB_RECOVERY_PHASE_ID
        ]
        self.assertEqual(
            canonical_sha256(phase),
            L2_TRIGGER_STATUS_WEB_RECOVERY_PHASE_SHA256,
        )
        expected = {
            ("policy_id",): "n6_btrack_delivery_l2_n6_business_v1",
            ("operation_class",): "single_web_immutable_release_rebind_eacces_recovery",
            ("executor_role",): "runtime_control",
            ("default_decision",): "REJECT",
            ("separate_current_request_authorization_required",): True,
            ("governance_session_cannot_execute",): True,
            ("consumed_phase_contract", "phase_id"): L2_TRIGGER_STATUS_WEB_PHASE_ID,
            ("consumed_phase_contract", "canonical_sha256"): L2_TRIGGER_STATUS_WEB_PHASE_SHA256,
            ("consumed_phase_contract", "primary_execution_count"): 1,
            ("consumed_phase_contract", "consumed"): True,
            ("failed_execution_attestation", "sha256"): "71964ef2a231e3307f566f64845c6141d771d7da55e9dc344caf7ac1480934b9",
            ("failed_execution_attestation", "normalized_result"): "BLOCKED_PRE_SERVICE",
            ("failed_execution_attestation", "failed_target_absent"): True,
            ("invalid_staging_evidence", "manifest_sha256"): "f427d169c29c0c83b270d59bff8f6bfb0a3fd72511472b13e03d2fe9a1f10c91",
            ("invalid_staging_evidence", "object_count"): 6316,
            ("invalid_staging_evidence", "file_count"): 6271,
            ("invalid_staging_evidence", "directory_count"): 45,
            ("invalid_staging_evidence", "root_mode"): "0555",
            ("invalid_staging_evidence", "disposition"): "evidence_only_preserve_in_place",
            ("root_cause_contract", "cause"): "staging_root_sealed_0555_before_renameatx_np",
            ("fresh_release_contract", "staging_root_mode_through_pre_rename_verification"): "0700",
            ("fresh_release_contract", "target_root_mode_immediately_after_rename"): "0555",
            ("fresh_release_contract", "git_mode_100755_child_mode"): "0555",
            ("fresh_release_contract", "git_mode_100644_child_mode"): "0444",
            ("service_rebind_contract", "exact_label"): "com.ashare-v3.n6.user-web",
            ("service_rebind_contract", "plist_swap_attempts"): 1,
            ("service_rebind_contract", "bootout_attempts"): 1,
            ("service_rebind_contract", "bootstrap_attempts"): 1,
            ("business_and_acceptance_contract", "strategy_write"): 0,
            ("business_and_acceptance_contract", "trigger_pct_allowed_anywhere"): False,
        }
        for path, value in expected.items():
            with self.subTest(path=path):
                self.assertEqual(nested_value(phase, path), value)

        operations = phase["failed_execution_attestation"]["operation_counts"]
        self.assertEqual(operations["release_build"], 1)
        self.assertEqual(operations["exclusive_release_rename"], 1)
        self.assertFalse(
            any(
                count
                for name, count in operations.items()
                if name not in {"release_build", "exclusive_release_rename"}
            )
        )
        registry = self.registry["append_only_gate_registrations"][
            L2_TRIGGER_STATUS_WEB_RECOVERY_PHASE_ID
        ]
        self.assertEqual(
            canonical_sha256(registry),
            L2_TRIGGER_STATUS_WEB_RECOVERY_REGISTRY_SHA256,
        )
        self.assertEqual(
            registry["phase_canonical_sha256"],
            L2_TRIGGER_STATUS_WEB_RECOVERY_PHASE_SHA256,
        )
        self.assertFalse(registry["deployment_authorized"])
        self.assertFalse(registry["governance_session_execution_allowed"])

    def test_l2_trigger_status_web_recovery_preserves_failed_staging(self) -> None:
        phase = self.contract["lanes"]["L2"]["deployment_phases"][
            L2_TRIGGER_STATUS_WEB_RECOVERY_PHASE_ID
        ]
        staging = phase["invalid_staging_evidence"]
        for key in (
            "delete_allowed",
            "quarantine_allowed",
            "cleanup_allowed",
            "rename_allowed",
            "modify_allowed",
            "repair_allowed",
            "reuse_allowed",
            "promote_allowed",
        ):
            with self.subTest(key=key):
                self.assertFalse(staging[key])
        self.assertEqual(
            phase["root_cause_contract"]["rename_flags"],
            ["RENAME_EXCL", "RENAME_NOFOLLOW_ANY", "RENAME_RESOLVE_BENEATH"],
        )
        self.assertEqual(
            phase["fresh_release_contract"]["ordered_steps"],
            [
                "materialize_payload_metadata",
                "write_release_specific_manifest",
                "seal_child_directories_and_files_preserving_git_modes",
                "verify_full_payload_and_manifest_with_staging_root_0700",
                "renameatx_np_exclusive_no_follow_beneath",
                "chmod_target_root_0555",
                "fsync_target_root",
                "full_target_post_verify",
            ],
        )
        self.assertFalse(
            phase["fresh_release_contract"]["failed_fresh_staging_cleanup_allowed"]
        )
        self.assertFalse(phase["fresh_release_contract"]["second_recovery_allowed"])

    def test_l2_trigger_status_web_recovery_classifier_is_fail_closed(self) -> None:
        phase = self.contract["lanes"]["L2"]["deployment_phases"][
            L2_TRIGGER_STATUS_WEB_RECOVERY_PHASE_ID
        ]
        self.assertEqual(
            static_l2_web_recovery_phase_decision(
                phase,
                l2_web_recovery_request(),
            ),
            "ACCEPT",
        )
        rejected_requests = (
            ("missing_authorization", {"current_request_authorized": False}),
            ("governance_execute", {"governance_session": True}),
            ("prior_not_consumed", {"prior_phase_consumed": False}),
            ("failed_evidence_drift", {"failed_evidence_matches": False}),
            ("live_state_drift", {"current_state_matches": False}),
            ("old_staging_mutation", {"invalid_staging_preserved_in_place": False}),
            ("release_collision", {"fresh_release_id_and_path": False}),
            ("second_execution", {"prior_recovery_execution_count": 1}),
        )
        for name, overrides in rejected_requests:
            with self.subTest(name=name):
                self.assertEqual(
                    static_l2_web_recovery_phase_decision(
                        phase,
                        l2_web_recovery_request(**overrides),
                    ),
                    "REJECT",
                )
        mutations = (
            ("attestation", ("failed_execution_attestation", "sha256"), "other"),
            ("staging", ("invalid_staging_evidence", "manifest_sha256"), "other"),
            ("cleanup", ("invalid_staging_evidence", "cleanup_allowed"), True),
            ("root_mode", ("fresh_release_contract", "staging_root_mode_through_pre_rename_verification"), "0555"),
            ("executable_mode", ("fresh_release_contract", "git_mode_100755_child_mode"), "0444"),
            ("second_recovery", ("fresh_release_contract", "second_recovery_allowed"), True),
            ("second_bootout", ("service_rebind_contract", "bootout_attempts"), 2),
            ("strategy_write", ("business_and_acceptance_contract", "strategy_write"), 1),
            ("trigger_pct", ("business_and_acceptance_contract", "trigger_pct_allowed_anywhere"), True),
        )
        for name, path, replacement in mutations:
            with self.subTest(name=name):
                candidate = mutated_fixture(phase, path, replacement)
                self.assertEqual(
                    static_l2_web_recovery_phase_decision(
                        candidate,
                        l2_web_recovery_request(),
                    ),
                    "REJECT",
                )
        for key in phase:
            with self.subTest(missing=key):
                candidate = copy.deepcopy(phase)
                del candidate[key]
                self.assertEqual(
                    static_l2_web_recovery_phase_decision(
                        candidate,
                        l2_web_recovery_request(),
                    ),
                    "REJECT",
                )

    def test_l2_trigger_status_web_contract_is_synchronized(self) -> None:
        paths = (
            ROOT / "docs/N6_B_TRACK_DELIVERY_GOVERNANCE_V1.json",
            ROOT / "docs/N6_B_TRACK_BASELINE_REGISTRY_V1.json",
            ROOT / "docs/EXECUTION_KERNEL.md",
            ROOT / "docs/EXECUTION_COMPILER.md",
            ROOT / "docs/EXECUTION_RUNTIME_GATE.md",
            ROOT / "docs/Tasks.md",
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertIn(
                    L2_TRIGGER_STATUS_WEB_PHASE_ID,
                    path.read_text(encoding="utf-8"),
                )


if __name__ == "__main__":
    unittest.main()
