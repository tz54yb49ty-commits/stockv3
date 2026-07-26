from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "n6_strategy_center_post_081_v2_web_bounded_rebind_v1"
ORIGINAL_WEB_POLICY_ID = "n6_user_web_immutable_release_bounded_rebind_v1"


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


def canonical_request(policy: dict[str, Any]) -> dict[str, Any]:
    source_release = (
        f"{policy['release_root']}/"
        "20260722_234251__658ebb3995a7c539ac211258c378af6499635df4"
    )
    target_release = (
        f"{policy['release_root']}/"
        "20260723_124546__168f375aa089d8bd384971c94730d233f1327826"
    )
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
        "target_release_path": target_release,
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
        request[field] = "c" * (40 if "{40}" in pattern else 64)
    request.update({field: True for field in policy["required_true_fields"]})
    request.update({field: False for field in policy["required_false_fields"]})
    return request


def strict_non_negative_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


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

    release_paths: list[str] = []
    for field in policy["required_resource_fields"]:
        value = request.get(field)
        if not isinstance(value, str):
            return reject
        path = Path(value)
        if str(path.parent) != policy["release_root"]:
            return reject
        if re.fullmatch(policy["release_name_pattern"], path.name) is None:
            return reject
        release_paths.append(value)
    if len(set(release_paths)) != len(release_paths):
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

    rollback_attempts = request.get("rollback_attempts")
    if not strict_non_negative_int(rollback_attempts):
        return reject
    if rollback_attempts > policy["maximum_rollback_attempts"]:
        return reject
    if rollback_attempts:
        if policy["rollback_requires_primary_failure"]:
            if request.get("primary_health_failed") is not True:
                return reject
        if policy["rollback_requires_frozen_source"]:
            if request.get("rollback_source_path") != request.get(
                "source_release_path"
            ):
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


class N6StrategyCenterPost081V2WebBoundedRebindPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()
        cls.request = canonical_request(cls.policy)

    def decision(self, **changes: Any) -> str:
        request = copy.deepcopy(self.request)
        request.update(changes)
        return evaluate(self.policy, request)

    def test_complete_post_081_contract_accepts(self) -> None:
        self.assertEqual(self.decision(), "ACCEPT")
        self.assertEqual(self.policy["runtime_gate_decision"], "ACCEPT")

    def test_default_and_unknown_runtime_execution_reject(self) -> None:
        self.assertEqual(self.policy["default_runtime_execution_decision"], "REJECT")
        self.assertEqual(self.decision(policy_id="general_runtime_execute"), "REJECT")

    def test_explicit_current_request_authorization_is_required(self) -> None:
        self.assertEqual(
            self.decision(explicit_user_authorization_current_request=False),
            "REJECT",
        )

    def test_exact_runtime_control_scope_labels_plist_and_port_are_required(self) -> None:
        cases = {
            "layer_role": "N6_user",
            "scope_mode": "all_services",
            "phase_mode": "normal_rebind",
            "launch_agent_label": "com.ashare-v3.n6.other",
            "launch_agent_plist_path": "/tmp/other.plist",
            "evaluator_launch_agent_label": "com.ashare-v3.n6.other",
            "virtual_executor_launch_agent_label": "com.ashare-v3.n6.other",
            "service_port": 8787,
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: value}), "REJECT")

    def test_one_distinct_source_and_target_release_are_required(self) -> None:
        self.assertEqual(self.decision(source_release_path="/tmp/release"), "REJECT")
        self.assertEqual(self.decision(target_release_path="relative"), "REJECT")
        self.assertEqual(
            self.decision(target_release_path=self.request["source_release_path"]),
            "REJECT",
        )
        for field in self.policy["required_singleton_counts"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: 2}), "REJECT")

    def test_all_hash_fields_are_strict_and_fail_closed(self) -> None:
        for field in self.policy["required_hash_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: "bad"}), "REJECT")

    def test_every_required_true_field_is_fail_closed(self) -> None:
        for field in self.policy["required_true_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")

    def test_every_required_false_field_is_fail_closed(self) -> None:
        for field in self.policy["required_false_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_081_commit_and_082_083_absence_are_required(self) -> None:
        self.assertEqual(self.decision(migration_081_committed_verified=False), "REJECT")
        self.assertEqual(
            self.decision(migration_082_not_executed_verified=False), "REJECT"
        )
        self.assertEqual(
            self.decision(migration_083_not_executed_verified=False), "REJECT"
        )
        self.assertEqual(self.decision(migration_082_requested=True), "REJECT")
        self.assertEqual(self.decision(migration_083_requested=True), "REJECT")

    def test_write_flag_must_remain_zero_at_every_phase(self) -> None:
        for field in (
            "strategy_write_flag_before",
            "strategy_write_flag_target",
            "strategy_write_flag_after",
            "strategy_write_flag_rollback",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: "1"}), "REJECT")
        self.assertEqual(self.decision(strategy_write_enable_requested=True), "REJECT")

    def test_evaluator_must_be_absent_and_cannot_be_operated(self) -> None:
        self.assertEqual(self.decision(evaluator_job_absent_verified=False), "REJECT")
        self.assertEqual(self.decision(evaluator_pid_absent_verified=False), "REJECT")
        for field in (
            "strategy_evaluator_execute_requested",
            "strategy_evaluator_start_requested",
            "strategy_evaluator_restore_requested",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_virtual_executor_is_frozen_disjoint_and_never_operated(self) -> None:
        for field in (
            "virtual_executor_configuration_frozen",
            "virtual_executor_role_acl_frozen",
            "virtual_executor_object_boundary_frozen",
            "virtual_executor_strategy_center_write_disjoint_verified",
            "virtual_executor_not_operated_verified",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        for field in (
            "virtual_executor_operation_requested",
            "virtual_executor_stop_requested",
            "virtual_executor_start_requested",
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

    def test_v2_081_and_non_regression_evidence_is_required(self) -> None:
        fields = (
            "post_081_schema_evidence_verified",
            "target_no_lineage_regression_verified",
            "target_v2_web_api_ui_sse_verified",
            "target_observation_surface_verified",
            "target_direction_and_trading_minute_freshness_verified",
            "target_081_schema_compatible_verified",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")

    def test_ownership_release_plist_environment_and_schema_drift_reject(self) -> None:
        fields = (
            "runtime_ownership_ambiguous",
            "release_drift_detected",
            "plist_drift_detected",
            "environment_drift_detected",
            "lineage_regression_detected",
            "post_081_schema_drift_detected",
            "concurrent_runtime_change",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_only_exact_web_resources_and_operations_are_allowed(self) -> None:
        self.assertEqual(self.decision(declared_mutation_resources=[]), "REJECT")
        self.assertEqual(self.decision(declared_runtime_operations=[]), "REJECT")
        self.assertNotIn(
            "com.ashare-v3.n6.strategy-center-evaluator-v1",
            self.policy["allowed_mutation_resources"],
        )
        self.assertNotIn(
            "com.ashare-v3.n6.virtual-executor-v1",
            self.policy["allowed_mutation_resources"],
        )

    def test_primary_attempts_and_retries_are_exact(self) -> None:
        self.assertEqual(self.decision(primary_bootout_attempts=0), "REJECT")
        self.assertEqual(self.decision(primary_bootout_attempts=2), "REJECT")
        self.assertEqual(self.decision(primary_bootstrap_attempts=0), "REJECT")
        self.assertEqual(self.decision(primary_bootstrap_attempts=2), "REJECT")
        self.assertEqual(self.decision(primary_retries=1), "REJECT")
        self.assertEqual(self.decision(primary_retry_requested=True), "REJECT")

    def test_one_rollback_pair_requires_primary_failure_and_frozen_source(self) -> None:
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

    def test_state_driven_teardown_and_immutable_guards_are_required(self) -> None:
        self.assertEqual(self.decision(state_driven_teardown_defined=False), "REJECT")
        self.assertEqual(
            self.decision(old_pid_exit_required_before_bootstrap=False), "REJECT"
        )
        self.assertEqual(
            self.decision(job_absence_required_before_bootstrap=False), "REJECT"
        )
        self.assertEqual(self.decision(fixed_sleep_bootstrap_requested=True), "REJECT")
        self.assertEqual(self.decision(signal_or_kill_requested=True), "REJECT")
        self.assertEqual(
            self.decision(immutable_release_content_modification_requested=True),
            "REJECT",
        )

    def test_readiness_routes_and_stability_are_exact(self) -> None:
        self.assertEqual(self.decision(teardown_timeout_seconds=31), "REJECT")
        self.assertEqual(self.decision(readiness_timeout_seconds=61), "REJECT")
        self.assertEqual(self.decision(stability_window_seconds=31), "REJECT")
        self.assertEqual(self.decision(login_redirect_path="/login"), "REJECT")
        routes = copy.deepcopy(self.policy["required_route_expectations"])
        routes["/n6/app/strategy-center"] = 200
        self.assertEqual(self.decision(route_expectations=routes), "REJECT")

    def test_database_migration_selection_queue_and_worker_paths_reject(self) -> None:
        fields = (
            "database_connection_requested",
            "database_write_requested",
            "migration_requested",
            "selection_projection_change_touched",
            "outbox_inbox_checkpoint_mutation_requested",
            "long_running_worker_requested",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_business_trading_and_n1_n5_paths_reject(self) -> None:
        fields = (
            "proposal_touched",
            "order_touched",
            "trade_touched",
            "position_touched",
            "cash_touched",
            "real_broker_connected",
            "n1_n5_write_requested",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_original_web_policy_remains_unchanged(self) -> None:
        original = load_policy(ORIGINAL_WEB_POLICY_ID)
        self.assertEqual(original["required_strategy_write_flag_value"], "1")
        self.assertIn(
            "virtual_executor_unloaded_verified",
            original["required_true_fields"],
        )
        self.assertNotEqual(original["policy_id"], self.policy["policy_id"])

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
