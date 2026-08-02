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


if __name__ == "__main__":
    unittest.main()
