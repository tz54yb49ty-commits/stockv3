from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "n6_strategy_center_post_083_v2_web_bounded_rebind_v1"
NORMAL_WEB_POLICY_ID = "n6_user_web_immutable_release_bounded_rebind_v1"
POST_081_WEB_POLICY_ID = "n6_strategy_center_post_081_v2_web_bounded_rebind_v1"


def load_policy(policy_id: str = POLICY_ID) -> dict[str, Any]:
    text = (ROOT / "docs" / "EXECUTION_KERNEL.md").read_text(encoding="utf-8")
    begin = f"<!-- policy:{policy_id}:begin -->"
    end = f"<!-- policy:{policy_id}:end -->"
    start = text.index(begin) + len(begin)
    stop = text.index(end, start)
    fenced = text[start:stop].strip()
    match = re.fullmatch(r"```json\s*(\{.*\})\s*```", fenced, re.DOTALL)
    if match is None:
        raise AssertionError(f"{policy_id} must contain exactly one valid JSON fence")
    return json.loads(match.group(1))


def strict_non_negative_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def canonical_request(policy: dict[str, Any]) -> dict[str, Any]:
    source_release = (
        f"{policy['release_root']}/{policy['source_release_name_exact']}"
    )
    target_commit = "f2b1ef323ad74be58fe9344815865350130dc012"
    target_release = f"{policy['release_root']}/20260725_082300__{target_commit}"
    request: dict[str, Any] = {
        "policy_id": policy["policy_id"],
        "layer_role": policy["layer_role"],
        "scope_mode": policy["scope_mode"],
        "phase_mode": policy["phase_mode"],
        "launch_agent_label": policy["launch_agent_label"],
        "launch_agent_plist_path": policy["launch_agent_plist_path"],
        "evaluator_launch_agent_label": policy["evaluator_launch_agent_label"],
        "virtual_executor_launch_agent_label": policy[
            "virtual_executor_launch_agent_label"
        ],
        "service_port": policy["service_port"],
        "source_release_path": source_release,
        "source_release_full_commit_sha": policy[
            "source_release_full_commit_sha_exact"
        ],
        "source_release_short_commit_prefix": policy[
            "source_release_short_commit_prefix_exact"
        ],
        "target_release_path": target_release,
        "target_release_commit_sha": target_commit,
        "declared_mutation_resources": list(policy["allowed_mutation_resources"]),
        "declared_runtime_operations": list(policy["allowed_runtime_operations"]),
        "primary_bootout_attempts": policy["primary_bootout_attempts"],
        "primary_bootstrap_attempts": policy["primary_bootstrap_attempts"],
        "primary_retries": policy["maximum_primary_retries"],
        "rollback_attempts": 0,
        "rollback_bootout_attempts": 0,
        "rollback_bootstrap_attempts": 0,
        "primary_health_failed": False,
        "rollback_source_path": source_release,
        "rollback_launch_agent_label": policy["launch_agent_label"],
        "evaluator_operation_attempts": policy["evaluator_operation_attempts"],
        "virtual_executor_operation_attempts": policy[
            "virtual_executor_operation_attempts"
        ],
        "virtual_executor_start_interval_seconds": policy[
            "required_virtual_executor_start_interval_seconds"
        ],
        "teardown_timeout_seconds": policy["teardown_timeout_seconds"],
        "readiness_timeout_seconds": policy["readiness_timeout_seconds"],
        "stability_window_seconds": policy["stability_window_seconds"],
        "strategy_write_flag_before": policy["required_strategy_write_flag_value"],
        "strategy_write_flag_target": policy["required_strategy_write_flag_value"],
        "strategy_write_flag_after": policy["required_strategy_write_flag_value"],
        "strategy_write_flag_rollback": policy["required_strategy_write_flag_value"],
        "login_redirect_path": policy["required_login_redirect_path"],
        "route_expectations": copy.deepcopy(policy["required_route_expectations"]),
        "normal_virtual_executor_pid_runs_change_is_configuration_drift": policy[
            "normal_virtual_executor_pid_runs_change_is_configuration_drift"
        ],
    }
    request.update(policy["required_singleton_counts"])
    for field, pattern in policy["required_hash_fields"].items():
        if field in {"source_release_full_commit_sha", "target_release_commit_sha"}:
            continue
        request[field] = "c" * (40 if "{40}" in pattern else 64)
    request.update({field: True for field in policy["required_true_fields"]})
    request.update({field: False for field in policy["required_false_fields"]})
    return request


def evaluate(policy: dict[str, Any], request: dict[str, Any]) -> str:
    reject = policy["default_runtime_execution_decision"]
    exact_fields = (
        "policy_id",
        "layer_role",
        "scope_mode",
        "phase_mode",
        "launch_agent_label",
        "launch_agent_plist_path",
        "evaluator_launch_agent_label",
        "virtual_executor_launch_agent_label",
        "service_port",
    )
    if any(request.get(field) != policy[field] for field in exact_fields):
        return reject

    source = Path(str(request.get("source_release_path", "")))
    target = Path(str(request.get("target_release_path", "")))
    if str(source.parent) != policy["release_root"]:
        return reject
    if source.name != policy["source_release_name_exact"]:
        return reject
    if str(target.parent) != policy["release_root"]:
        return reject
    if re.fullmatch(policy["target_release_name_pattern"], target.name) is None:
        return reject
    if source == target:
        return reject
    if request.get("source_release_full_commit_sha") != policy[
        "source_release_full_commit_sha_exact"
    ]:
        return reject
    if request.get("source_release_short_commit_prefix") != policy[
        "source_release_short_commit_prefix_exact"
    ]:
        return reject
    if not policy["source_release_full_commit_sha_exact"].startswith(
        policy["source_release_short_commit_prefix_exact"]
    ):
        return reject
    target_commit = request.get("target_release_commit_sha")
    if not isinstance(target_commit, str):
        return reject
    if target.name.rsplit("__", 1)[-1] != target_commit:
        return reject

    for field, pattern in policy["required_hash_fields"].items():
        value = request.get(field)
        if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
            return reject
    for field, expected in policy["required_singleton_counts"].items():
        value = request.get(field)
        if not strict_non_negative_int(value) or value != expected:
            return reject
    if any(request.get(field) is not True for field in policy["required_true_fields"]):
        return reject
    if any(request.get(field) is not False for field in policy["required_false_fields"]):
        return reject

    if request.get("declared_mutation_resources") != policy[
        "allowed_mutation_resources"
    ]:
        return reject
    if request.get("declared_runtime_operations") != policy[
        "allowed_runtime_operations"
    ]:
        return reject
    if request.get("primary_bootout_attempts") != policy[
        "primary_bootout_attempts"
    ]:
        return reject
    if request.get("primary_bootstrap_attempts") != policy[
        "primary_bootstrap_attempts"
    ]:
        return reject
    if request.get("primary_retries") != policy["maximum_primary_retries"]:
        return reject
    if request.get("evaluator_operation_attempts") != policy[
        "evaluator_operation_attempts"
    ]:
        return reject
    if request.get("virtual_executor_operation_attempts") != policy[
        "virtual_executor_operation_attempts"
    ]:
        return reject
    if request.get("virtual_executor_start_interval_seconds") != policy[
        "required_virtual_executor_start_interval_seconds"
    ]:
        return reject

    rollback_attempts = request.get("rollback_attempts")
    if not strict_non_negative_int(rollback_attempts):
        return reject
    if rollback_attempts > policy["maximum_rollback_attempts"]:
        return reject
    if rollback_attempts:
        if request.get("primary_health_failed") is not True:
            return reject
        if request.get("rollback_source_path") != request.get("source_release_path"):
            return reject
        if request.get("rollback_launch_agent_label") != policy[
            "launch_agent_label"
        ]:
            return reject
        if request.get("rollback_bootout_attempts") != 1:
            return reject
        if request.get("rollback_bootstrap_attempts") != 1:
            return reject
    elif (
        request.get("rollback_bootout_attempts") != 0
        or request.get("rollback_bootstrap_attempts") != 0
    ):
        return reject

    for field in (
        "teardown_timeout_seconds",
        "readiness_timeout_seconds",
        "stability_window_seconds",
    ):
        if request.get(field) != policy[field]:
            return reject
    for field in (
        "strategy_write_flag_before",
        "strategy_write_flag_target",
        "strategy_write_flag_after",
        "strategy_write_flag_rollback",
    ):
        if request.get(field) != policy["required_strategy_write_flag_value"]:
            return reject
    if request.get("login_redirect_path") != policy["required_login_redirect_path"]:
        return reject
    if request.get("route_expectations") != policy["required_route_expectations"]:
        return reject
    if request.get(
        "normal_virtual_executor_pid_runs_change_is_configuration_drift"
    ) != policy["normal_virtual_executor_pid_runs_change_is_configuration_drift"]:
        return reject
    return policy["accept_decision"]


class N6StrategyCenterPost083V2WebBoundedRebindPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()
        cls.request = canonical_request(cls.policy)

    def decision(self, **changes: Any) -> str:
        request = copy.deepcopy(self.request)
        request.update(changes)
        return evaluate(self.policy, request)

    def test_complete_post_083_contract_accepts(self) -> None:
        self.assertEqual(self.decision(), "ACCEPT")
        self.assertEqual(self.policy["runtime_gate_decision"], "ACCEPT")

    def test_default_unknown_and_missing_authorization_reject(self) -> None:
        self.assertEqual(self.policy["default_runtime_execution_decision"], "REJECT")
        self.assertEqual(self.decision(policy_id="general_runtime_execute"), "REJECT")
        self.assertEqual(
            self.decision(explicit_user_authorization_current_request=False),
            "REJECT",
        )

    def test_exact_runtime_control_web_scope_is_required(self) -> None:
        cases = {
            "layer_role": "N6_user",
            "scope_mode": "all_services",
            "phase_mode": "post_081_v2_web_rebind_only",
            "launch_agent_label": "com.ashare-v3.n6.other",
            "launch_agent_plist_path": "/tmp/other.plist",
            "evaluator_launch_agent_label": "com.ashare-v3.n6.other",
            "virtual_executor_launch_agent_label": "com.ashare-v3.n6.other",
            "service_port": 8787,
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: value}), "REJECT")

    def test_only_exact_one_time_legacy_source_is_accepted(self) -> None:
        other = (
            f"{self.policy['release_root']}/"
            "20260724_042200__deadbeef"
        )
        self.assertEqual(self.decision(source_release_path=other), "REJECT")
        self.assertEqual(
            self.decision(source_release_full_commit_sha="d" * 40),
            "REJECT",
        )
        self.assertEqual(
            self.decision(source_release_short_commit_prefix="deadbeef"),
            "REJECT",
        )
        for field in (
            "legacy_source_reuse_requested",
            "legacy_source_target_requested",
            "non_exact_legacy_source_requested",
            "legacy_source_content_mutation_requested",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_legacy_source_requires_complete_blob_attestation(self) -> None:
        fields = (
            "legacy_source_full_commit_matches_short_prefix_verified",
            "legacy_source_full_commit_tree_archive_manifest_filesystem_closed",
            "legacy_source_git_blob_mode_path_closed",
            "legacy_source_no_missing_extra_symlink_or_file_hardlink_verified",
            "legacy_source_immutable_verified",
            "legacy_source_rollback_only",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        for field in (
            "source_release_archive_sha256",
            "source_release_git_ls_tree_sha256",
            "source_release_manifest_sha256",
            "source_release_filesystem_sha256",
            "source_release_attestation_sha256",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: "bad"}), "REJECT")

    def test_target_must_use_formal_name_matching_commit(self) -> None:
        self.assertEqual(
            self.decision(
                target_release_path=(
                    f"{self.policy['release_root']}/"
                    "20260725_082300__f2b1ef32"
                )
            ),
            "REJECT",
        )
        self.assertEqual(
            self.decision(target_release_commit_sha="d" * 40),
            "REJECT",
        )
        self.assertEqual(self.decision(target_short_name_requested=True), "REJECT")

    def test_target_immutable_non_regressing_n6_evidence_is_required(self) -> None:
        fields = (
            "target_release_immutable_verified",
            "target_release_formal_name_matches_commit_verified",
            "target_no_lineage_regression_verified",
            "target_preserves_source_effective_n6_deltas_verified",
            "target_v2_web_api_ui_sse_verified",
            "target_observation_surface_verified",
            "target_direction_and_trading_minute_freshness_verified",
            "target_post_083_084_schema_compatible_verified",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")

    def test_081_082_083_084_commits_are_required_without_migration_authority(self) -> None:
        for field in (
            "migration_081_committed_verified",
            "migration_082_committed_verified",
            "migration_083_committed_verified",
            "migration_084_committed_verified",
            "post_083_084_schema_catalog_evidence_verified",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        self.assertEqual(self.decision(migration_requested=True), "REJECT")

    def test_strategy_write_remains_one_at_every_phase(self) -> None:
        for field in (
            "strategy_write_flag_before",
            "strategy_write_flag_target",
            "strategy_write_flag_after",
            "strategy_write_flag_rollback",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: "0"}), "REJECT")
        self.assertEqual(self.decision(strategy_write_disable_requested=True), "REJECT")

    def test_evaluator_requires_independent_quiesce_and_zero_operations(self) -> None:
        for field in (
            "independent_evaluator_quiesce_gate_passed",
            "evaluator_job_absent_verified",
            "evaluator_pid_absent_verified",
            "evaluator_not_operated_by_this_policy_verified",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        self.assertEqual(self.decision(evaluator_operation_attempts=1), "REJECT")
        for field in (
            "strategy_evaluator_execute_requested",
            "strategy_evaluator_stop_requested",
            "strategy_evaluator_start_requested",
            "strategy_evaluator_restore_requested",
            "evaluator_operation_requested_by_this_policy",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_virtual_executor_five_second_schedule_is_frozen_and_untouched(self) -> None:
        for field in (
            "virtual_executor_loaded_start_interval_five_verified",
            "virtual_executor_configuration_frozen",
            "virtual_executor_role_acl_frozen",
            "virtual_executor_object_boundary_frozen",
            "virtual_executor_strategy_center_write_disjoint_verified",
            "virtual_executor_web_rebind_disjoint_verified",
            "virtual_executor_not_operated_verified",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        self.assertEqual(
            self.decision(virtual_executor_start_interval_seconds=10),
            "REJECT",
        )
        self.assertEqual(self.decision(virtual_executor_operation_attempts=1), "REJECT")

    def test_virtual_executor_operations_and_configuration_drift_reject(self) -> None:
        for field in (
            "virtual_executor_operation_requested",
            "virtual_executor_stop_requested",
            "virtual_executor_start_requested",
            "virtual_executor_restart_requested",
            "virtual_executor_configuration_drift_detected",
            "virtual_executor_acl_or_object_boundary_drift_detected",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_normal_virtual_executor_pid_runs_change_is_not_drift(self) -> None:
        self.assertEqual(self.decision(), "ACCEPT")
        self.assertFalse(
            self.policy[
                "normal_virtual_executor_pid_runs_change_is_configuration_drift"
            ]
        )
        self.assertEqual(
            self.decision(
                normal_virtual_executor_pid_runs_change_is_configuration_drift=True
            ),
            "REJECT",
        )

    def test_every_hash_and_boolean_guard_is_fail_closed(self) -> None:
        for field in self.policy["required_hash_fields"]:
            with self.subTest(hash_field=field):
                self.assertEqual(self.decision(**{field: "bad"}), "REJECT")
        for field in self.policy["required_true_fields"]:
            with self.subTest(true_field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        for field in self.policy["required_false_fields"]:
            with self.subTest(false_field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_only_exact_web_resources_and_operations_are_allowed(self) -> None:
        self.assertEqual(self.decision(declared_mutation_resources=[]), "REJECT")
        self.assertEqual(self.decision(declared_runtime_operations=[]), "REJECT")
        self.assertNotIn(
            self.policy["evaluator_launch_agent_label"],
            self.policy["allowed_mutation_resources"],
        )
        self.assertNotIn(
            self.policy["virtual_executor_launch_agent_label"],
            self.policy["allowed_mutation_resources"],
        )

    def test_primary_attempts_are_one_with_zero_retry(self) -> None:
        self.assertEqual(self.decision(primary_bootout_attempts=0), "REJECT")
        self.assertEqual(self.decision(primary_bootout_attempts=2), "REJECT")
        self.assertEqual(self.decision(primary_bootstrap_attempts=0), "REJECT")
        self.assertEqual(self.decision(primary_bootstrap_attempts=2), "REJECT")
        self.assertEqual(self.decision(primary_retries=1), "REJECT")
        self.assertEqual(self.decision(primary_retry_requested=True), "REJECT")

    def test_single_rollback_requires_health_failure_and_exact_legacy_source(self) -> None:
        rollback = {
            "rollback_attempts": 1,
            "rollback_bootout_attempts": 1,
            "rollback_bootstrap_attempts": 1,
            "primary_health_failed": True,
        }
        self.assertEqual(self.decision(**rollback), "ACCEPT")
        self.assertEqual(
            self.decision(**{**rollback, "primary_health_failed": False}),
            "REJECT",
        )
        self.assertEqual(
            self.decision(**{**rollback, "rollback_source_path": "/tmp/other"}),
            "REJECT",
        )
        self.assertEqual(self.decision(rollback_attempts=2), "REJECT")

    def test_state_driven_readiness_route_and_stability_contract_is_exact(self) -> None:
        self.assertEqual(self.decision(state_driven_teardown_defined=False), "REJECT")
        self.assertEqual(
            self.decision(old_pid_exit_required_before_bootstrap=False),
            "REJECT",
        )
        self.assertEqual(
            self.decision(job_absence_required_before_bootstrap=False),
            "REJECT",
        )
        self.assertEqual(self.decision(fixed_sleep_bootstrap_requested=True), "REJECT")
        self.assertEqual(self.decision(signal_or_kill_requested=True), "REJECT")
        self.assertEqual(self.decision(teardown_timeout_seconds=31), "REJECT")
        self.assertEqual(self.decision(readiness_timeout_seconds=61), "REJECT")
        self.assertEqual(self.decision(stability_window_seconds=31), "REJECT")
        routes = copy.deepcopy(self.policy["required_route_expectations"])
        routes["/n6/app/strategy-center"] = 200
        self.assertEqual(self.decision(route_expectations=routes), "REJECT")

    def test_ownership_release_plist_environment_and_schema_drift_reject(self) -> None:
        for field in (
            "runtime_ownership_ambiguous",
            "release_drift_detected",
            "plist_drift_detected",
            "environment_drift_detected",
            "lineage_regression_detected",
            "post_083_084_schema_catalog_drift_detected",
            "concurrent_runtime_change",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_database_business_trading_n1_n5_and_other_runtime_paths_reject(self) -> None:
        for field in (
            "database_connection_requested",
            "database_write_requested",
            "migration_requested",
            "selection_projection_change_touched",
            "outbox_inbox_checkpoint_mutation_requested",
            "proposal_touched",
            "order_touched",
            "trade_touched",
            "position_touched",
            "cash_touched",
            "real_broker_connected",
            "n1_n5_write_requested",
            "long_running_worker_requested",
            "other_launch_agent_touched",
            "immutable_release_content_modification_requested",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_existing_web_policies_remain_strict_and_unchanged(self) -> None:
        normal = load_policy(NORMAL_WEB_POLICY_ID)
        post_081 = load_policy(POST_081_WEB_POLICY_ID)
        self.assertEqual(normal["required_strategy_write_flag_value"], "1")
        self.assertIn("virtual_executor_unloaded_verified", normal["required_true_fields"])
        self.assertEqual(post_081["required_strategy_write_flag_value"], "0")
        self.assertIn("migration_083_not_executed_verified", post_081["required_true_fields"])
        self.assertNotEqual(normal["policy_id"], self.policy["policy_id"])
        self.assertNotEqual(post_081["policy_id"], self.policy["policy_id"])

    def test_all_control_documents_name_the_new_policy(self) -> None:
        for relative in (
            "AGENTS.md",
            "docs/EXECUTION_COMPILER.md",
            "docs/EXECUTION_KERNEL.md",
            "docs/EXECUTION_RUNTIME_GATE.md",
            "docs/EXECUTION_SANDBOX.md",
            "docs/EXECUTION_TEST_SUITE.md",
            "docs/EXECUTION_TRACE_SYSTEM.md",
        ):
            with self.subTest(path=relative):
                self.assertIn(
                    POLICY_ID,
                    (ROOT / relative).read_text(encoding="utf-8"),
                )


if __name__ == "__main__":
    unittest.main()
