from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "n6_user_web_immutable_release_bounded_rebind_v1"
POLICY_BEGIN = f"<!-- policy:{POLICY_ID}:begin -->"
POLICY_END = f"<!-- policy:{POLICY_ID}:end -->"
STRATEGY_POLICY_ID = "n6_strategy_center_display_only_bounded_run_once_v1"


def load_policy() -> dict[str, Any]:
    text = (ROOT / "docs" / "EXECUTION_KERNEL.md").read_text(encoding="utf-8")
    start = text.index(POLICY_BEGIN) + len(POLICY_BEGIN)
    end = text.index(POLICY_END, start)
    fenced = text[start:end].strip()
    match = re.fullmatch(r"```json\s*(\{.*\})\s*```", fenced, re.DOTALL)
    if match is None:
        raise AssertionError("Web bounded-rebind policy must contain exactly one valid JSON fence")
    return json.loads(match.group(1))


def canonical_request(policy: dict[str, Any]) -> dict[str, Any]:
    source_release = (
        f"{policy['release_root']}/"
        "20260722_151503__85132bdb2cb431abf24f81cb3a100c4c16b1bd41"
    )
    target_release = (
        f"{policy['release_root']}/"
        "20260722_150819__1de9508fe5e64843296844f231d57e51b5521f9c"
    )
    request: dict[str, Any] = {
        "policy_id": policy["policy_id"],
        "layer_role": policy["layer_role"],
        "scope_mode": policy["scope_mode"],
        "launch_agent_label": policy["launch_agent_label"],
        "launch_agent_plist_path": policy["launch_agent_plist_path"],
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
        "strategy_write_flag_value": policy["required_strategy_write_flag_value"],
        "login_redirect_path": policy["required_login_redirect_path"],
        "route_expectations": copy.deepcopy(policy["required_route_expectations"]),
    }
    request.update(policy["required_singleton_counts"])
    request.update({field: True for field in policy["required_true_fields"]})
    request.update({field: False for field in policy["required_false_fields"]})
    return request


def strict_non_negative_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def evaluate(policy: dict[str, Any], request: dict[str, Any]) -> str:
    reject = policy["default_runtime_execution_decision"]
    if request.get("policy_id") != policy["policy_id"]:
        return reject
    for field in (
        "layer_role",
        "scope_mode",
        "launch_agent_label",
        "launch_agent_plist_path",
        "service_port",
    ):
        if request.get(field) != policy[field]:
            return reject
    release_paths: list[str] = []
    for field in policy["required_resource_fields"]:
        value = request.get(field)
        if not isinstance(value, str) or not value.startswith("/") or value.endswith("/"):
            return reject
        path = Path(value)
        if str(path.parent) != policy["release_root"]:
            return reject
        if re.fullmatch(policy["release_name_pattern"], path.name) is None:
            return reject
        release_paths.append(value)
    if len(set(release_paths)) != len(release_paths):
        return reject
    for field, expected in policy["required_singleton_counts"].items():
        value = request.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value != expected:
            return reject
    if any(request.get(field) is not True for field in policy["required_true_fields"]):
        return reject
    if any(request.get(field) is not False for field in policy["required_false_fields"]):
        return reject
    if request.get("declared_mutation_resources") != policy["allowed_mutation_resources"]:
        return reject
    if request.get("declared_runtime_operations") != policy["allowed_runtime_operations"]:
        return reject
    if request.get("primary_bootout_attempts") != policy["primary_bootout_attempts"]:
        return reject
    if request.get("primary_bootstrap_attempts") != policy["primary_bootstrap_attempts"]:
        return reject
    if request.get("primary_retries") != policy["maximum_primary_retries"]:
        return reject
    rollback_attempts = request.get("rollback_attempts")
    if not strict_non_negative_int(rollback_attempts):
        return reject
    if rollback_attempts > policy["maximum_rollback_attempts"]:
        return reject
    if rollback_attempts:
        if policy["rollback_requires_primary_failure"] and request.get("primary_health_failed") is not True:
            return reject
        if policy["rollback_requires_frozen_source"]:
            if request.get("rollback_source_path") != request.get("source_release_path"):
                return reject
        if request.get("rollback_launch_agent_label") != policy["launch_agent_label"]:
            return reject
        if request.get("rollback_bootout_attempts") != 1:
            return reject
        if request.get("rollback_bootstrap_attempts") != 1:
            return reject
    else:
        if request.get("rollback_bootout_attempts") != 0:
            return reject
        if request.get("rollback_bootstrap_attempts") != 0:
            return reject
    for field in (
        "teardown_timeout_seconds",
        "readiness_timeout_seconds",
        "stability_window_seconds",
    ):
        if request.get(field) != policy[field]:
            return reject
    if request.get("strategy_write_flag_value") != policy["required_strategy_write_flag_value"]:
        return reject
    if request.get("login_redirect_path") != policy["required_login_redirect_path"]:
        return reject
    if request.get("route_expectations") != policy["required_route_expectations"]:
        return reject
    return policy["accept_decision"]


class N6UserWebBoundedRebindPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()
        cls.request = canonical_request(cls.policy)

    def decision(self, **changes: Any) -> str:
        request = copy.deepcopy(self.request)
        request.update(changes)
        return evaluate(self.policy, request)

    def test_canonical_single_service_rebind_accepts(self) -> None:
        self.assertEqual(self.decision(), "ACCEPT")
        self.assertEqual(self.policy["runtime_gate_decision"], "ACCEPT")

    def test_default_and_unknown_runtime_execution_reject(self) -> None:
        self.assertEqual(self.policy["default_runtime_execution_decision"], "REJECT")
        self.assertEqual(self.decision(policy_id="general_runtime_control_execute"), "REJECT")

    def test_exact_layer_label_plist_port_and_scope_are_required(self) -> None:
        cases = {
            "layer_role": "N6_user",
            "scope_mode": "all_services",
            "launch_agent_label": "com.ashare-v3.n6.other",
            "launch_agent_plist_path": "/tmp/other.plist",
            "service_port": 8787,
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: value}), "REJECT")

    def test_explicit_current_request_authorization_is_mandatory(self) -> None:
        self.assertEqual(self.decision(explicit_user_authorization_current_request=False), "REJECT")

    def test_source_and_target_must_be_distinct_absolute_release_paths(self) -> None:
        self.assertEqual(self.decision(source_release_path=None), "REJECT")
        self.assertEqual(self.decision(target_release_path="relative/release"), "REJECT")
        self.assertEqual(
            self.decision(
                target_release_path=(
                    "/tmp/20260722_150819__1de9508fe5e64843296844f231d57e51b5521f9c"
                )
            ),
            "REJECT",
        )
        self.assertEqual(
            self.decision(target_release_path=f"{self.policy['release_root']}/target_release"),
            "REJECT",
        )
        self.assertEqual(
            self.decision(target_release_path=self.request["source_release_path"]),
            "REJECT",
        )

    def test_every_singleton_count_is_exactly_one(self) -> None:
        for field in self.policy["required_singleton_counts"]:
            for value in (0, 2, True, "1"):
                with self.subTest(field=field, value=value):
                    self.assertEqual(self.decision(**{field: value}), "REJECT")

    def test_every_required_true_field_is_fail_closed(self) -> None:
        for field in self.policy["required_true_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")

    def test_every_required_false_field_is_fail_closed(self) -> None:
        for field in self.policy["required_false_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_ownership_ambiguity_and_concurrent_drift_reject(self) -> None:
        self.assertEqual(self.decision(runtime_ownership_ambiguous=True), "REJECT")
        self.assertEqual(self.decision(launchd_ownership_verified=False), "REJECT")
        self.assertEqual(self.decision(concurrent_runtime_change=True), "REJECT")

    def test_release_proof_and_lineage_regression_reject(self) -> None:
        for field in (
            "source_release_commit_verified",
            "source_release_tree_verified",
            "source_release_archive_hash_verified",
            "source_release_manifest_hash_verified",
            "target_release_commit_verified",
            "target_release_tree_verified",
            "target_release_archive_hash_verified",
            "target_release_manifest_hash_verified",
            "target_no_lineage_regression_verified",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        self.assertEqual(self.decision(lineage_regression_detected=True), "REJECT")

    def test_release_plist_and_environment_drift_reject(self) -> None:
        for field in (
            "release_drift_detected",
            "plist_drift_detected",
            "environment_drift_detected",
            "extra_environment_change_requested",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_mutation_resources_and_operations_are_exact(self) -> None:
        self.assertEqual(
            self.decision(
                declared_mutation_resources=self.policy["allowed_mutation_resources"]
                + ["gui/current-user/com.ashare-v3.other"]
            ),
            "REJECT",
        )
        self.assertEqual(
            self.decision(
                declared_runtime_operations=self.policy["allowed_runtime_operations"]
                + ["launchctl_kickstart"]
            ),
            "REJECT",
        )

    def test_primary_bootout_bootstrap_and_retry_limits_are_exact(self) -> None:
        self.assertEqual(self.decision(primary_bootout_attempts=0), "REJECT")
        self.assertEqual(self.decision(primary_bootout_attempts=2), "REJECT")
        self.assertEqual(self.decision(primary_bootstrap_attempts=0), "REJECT")
        self.assertEqual(self.decision(primary_bootstrap_attempts=2), "REJECT")
        self.assertEqual(self.decision(primary_retries=1), "REJECT")
        self.assertEqual(self.decision(primary_retry_requested=True), "REJECT")

    def test_one_rollback_pair_accepts_only_after_primary_health_failure(self) -> None:
        self.assertEqual(
            self.decision(
                rollback_attempts=1,
                rollback_bootout_attempts=1,
                rollback_bootstrap_attempts=1,
                primary_health_failed=True,
            ),
            "ACCEPT",
        )
        self.assertEqual(
            self.decision(
                rollback_attempts=1,
                rollback_bootout_attempts=1,
                rollback_bootstrap_attempts=1,
                primary_health_failed=False,
            ),
            "REJECT",
        )

    def test_rollback_must_restore_only_frozen_source_and_exact_label(self) -> None:
        base = {
            "rollback_attempts": 1,
            "rollback_bootout_attempts": 1,
            "rollback_bootstrap_attempts": 1,
            "primary_health_failed": True,
        }
        self.assertEqual(
            self.decision(**base, rollback_source_path="/tmp/other-release"),
            "REJECT",
        )
        self.assertEqual(
            self.decision(**base, rollback_launch_agent_label="com.ashare-v3.other"),
            "REJECT",
        )
        self.assertEqual(self.decision(rollback_attempts=2), "REJECT")

    def test_state_driven_teardown_and_immutable_content_guards_reject(self) -> None:
        self.assertEqual(self.decision(state_driven_teardown_defined=False), "REJECT")
        self.assertEqual(self.decision(old_pid_exit_required_before_bootstrap=False), "REJECT")
        self.assertEqual(self.decision(job_absence_required_before_bootstrap=False), "REJECT")
        self.assertEqual(self.decision(fixed_sleep_bootstrap_requested=True), "REJECT")
        self.assertEqual(self.decision(signal_or_kill_requested=True), "REJECT")
        self.assertEqual(
            self.decision(immutable_release_content_modification_requested=True),
            "REJECT",
        )

    def test_readiness_routes_stability_and_write_flag_are_exact(self) -> None:
        self.assertEqual(self.decision(teardown_timeout_seconds=31), "REJECT")
        self.assertEqual(self.decision(readiness_timeout_seconds=61), "REJECT")
        self.assertEqual(self.decision(stability_window_seconds=31), "REJECT")
        self.assertEqual(self.decision(strategy_write_flag_value="0"), "REJECT")
        self.assertEqual(self.decision(login_redirect_path="/login"), "REJECT")
        routes = copy.deepcopy(self.policy["required_route_expectations"])
        routes["/n6/app/strategy-center"] = 200
        self.assertEqual(self.decision(route_expectations=routes), "REJECT")

    def test_evaluator_worker_database_and_migration_paths_reject(self) -> None:
        for field in (
            "long_running_worker_requested",
            "strategy_evaluator_execute_requested",
            "strategy_evaluator_start_requested",
            "virtual_executor_start_requested",
            "database_connection_requested",
            "database_write_requested",
            "migration_requested",
            "selection_projection_change_touched",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_queue_business_and_trading_paths_reject(self) -> None:
        for field in (
            "outbox_inbox_checkpoint_mutation_requested",
            "proposal_touched",
            "order_touched",
            "trade_touched",
            "position_touched",
            "cash_touched",
            "real_broker_connected",
            "n1_n6_business_mutation_requested",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_control_documents_reference_both_policies_and_default_reject(self) -> None:
        paths = (
            "AGENTS.md",
            "docs/EXECUTION_COMPILER.md",
            "docs/EXECUTION_KERNEL.md",
            "docs/EXECUTION_RUNTIME_GATE.md",
            "docs/EXECUTION_SANDBOX.md",
            "docs/EXECUTION_TEST_SUITE.md",
            "docs/EXECUTION_TRACE_SYSTEM.md",
        )
        for path in paths:
            with self.subTest(path=path):
                text = (ROOT / path).read_text(encoding="utf-8")
                self.assertIn(POLICY_ID, text)
                self.assertIn(STRATEGY_POLICY_ID, text)
        self.assertEqual(self.policy["default_runtime_execution_decision"], "REJECT")


if __name__ == "__main__":
    unittest.main()
