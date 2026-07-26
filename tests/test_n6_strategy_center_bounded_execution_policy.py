from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "n6_strategy_center_display_only_bounded_run_once_v1"
POLICY_BEGIN = f"<!-- policy:{POLICY_ID}:begin -->"
POLICY_END = f"<!-- policy:{POLICY_ID}:end -->"


def load_policy() -> dict[str, Any]:
    text = (ROOT / "docs" / "EXECUTION_KERNEL.md").read_text(encoding="utf-8")
    start = text.index(POLICY_BEGIN) + len(POLICY_BEGIN)
    end = text.index(POLICY_END, start)
    fenced = text[start:end].strip()
    match = re.fullmatch(r"```json\s*(\{.*\})\s*```", fenced, re.DOTALL)
    if match is None:
        raise AssertionError("bounded policy must contain exactly one valid JSON fence")
    return json.loads(match.group(1))


def canonical_request(policy: dict[str, Any]) -> dict[str, Any]:
    coexistence = policy["virtual_executor_coexistence_contract"]
    request: dict[str, Any] = {
        "policy_id": policy["policy_id"],
        "layer_role": policy["layer_role"],
        "runner_basename": policy["runner_basename"],
        "scope_mode": policy["scope_mode"],
        "database_role": policy["database_role"],
        "principal_id": 11,
        "user_id": 22,
        "selection_revision_id": coexistence["required_selection_revision_id"],
        "trade_date": coexistence["required_trade_date"],
        "current_trade_date": coexistence["required_trade_date"],
        "declared_write_tables": list(policy["allowed_write_tables"]),
        "observation_dml_contract": copy.deepcopy(
            policy["observation_dml_contract"]
        ),
        "rollback_contract": copy.deepcopy(policy["rollback_contract"]),
        "primary_execute_attempts": policy["primary_execute_attempts"],
        "idempotence_replay_attempts": 1,
        "idempotence_replay_same_scope": True,
        "idempotence_replay_same_input": True,
        "idempotence_replay_same_run_id": True,
        "virtual_executor_loaded_or_running": True,
        "virtual_executor_phase_mode": coexistence["phase_mode"],
        "virtual_executor_launch_agent_label": coexistence["launch_agent_label"],
        "virtual_executor_launch_agent_plist_path": coexistence[
            "launch_agent_plist_path"
        ],
        "virtual_executor_database_role": coexistence["database_role"],
        "virtual_executor_pgservice": coexistence["pgservice"],
        "virtual_executor_start_interval_seconds": coexistence[
            "start_interval_seconds"
        ],
        "gate2_attempt_order": list(coexistence["required_attempt_order"]),
        "virtual_executor_forbidden_strategy_center_write_tables": list(
            coexistence["forbidden_strategy_center_write_tables"]
        ),
        "virtual_executor_forbidden_strategy_center_execute_scope": coexistence[
            "forbidden_strategy_center_execute_scope"
        ],
        "virtual_executor_operation_attempts": coexistence[
            "required_operation_attempts"
        ],
        "normal_start_interval_pid_runs_change_is_configuration_drift": (
            coexistence[
                "normal_start_interval_pid_runs_change_is_configuration_drift"
            ]
        ),
    }
    request.update(policy["required_singleton_counts"])
    request.update({field: True for field in policy["required_true_fields"]})
    request.update({field: False for field in policy["required_false_fields"]})
    request.update(coexistence["required_pre_gate_attempt_counts"])
    for field, pattern in coexistence["required_hash_fields"].items():
        request[field] = "a" * (40 if "{40}" in pattern else 64)
    request.update({field: True for field in coexistence["required_true_fields"]})
    request.update({field: False for field in coexistence["required_false_fields"]})
    return request


def evaluate(policy: dict[str, Any], request: dict[str, Any]) -> str:
    reject = policy["default_runtime_execution_decision"]
    if request.get("policy_id") != policy["policy_id"]:
        return reject
    for field in ("layer_role", "runner_basename", "scope_mode", "database_role"):
        if request.get(field) != policy[field]:
            return reject
    for field in policy["required_scope_fields"]:
        value = request.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return reject
    for field, expected in policy["required_singleton_counts"].items():
        if request.get(field) != expected:
            return reject
    trade_date = request.get(policy["trade_date_field"])
    current_trade_date = request.get(policy["current_trade_date_field"])
    if not isinstance(trade_date, str) or re.fullmatch(r"\d{8}", trade_date) is None:
        return reject
    if trade_date != current_trade_date:
        return reject
    if any(request.get(field) is not True for field in policy["required_true_fields"]):
        return reject
    if any(request.get(field) is not False for field in policy["required_false_fields"]):
        return reject
    if request.get("virtual_executor_loaded_or_running") is True:
        coexistence = policy["virtual_executor_coexistence_contract"]
        exact_fields = {
            "virtual_executor_phase_mode": coexistence["phase_mode"],
            "selection_revision_id": coexistence["required_selection_revision_id"],
            "trade_date": coexistence["required_trade_date"],
            "current_trade_date": coexistence["required_trade_date"],
            "virtual_executor_launch_agent_label": coexistence[
                "launch_agent_label"
            ],
            "virtual_executor_launch_agent_plist_path": coexistence[
                "launch_agent_plist_path"
            ],
            "virtual_executor_database_role": coexistence["database_role"],
            "virtual_executor_pgservice": coexistence["pgservice"],
            "virtual_executor_start_interval_seconds": coexistence[
                "start_interval_seconds"
            ],
            "gate2_attempt_order": coexistence["required_attempt_order"],
            "virtual_executor_forbidden_strategy_center_write_tables": coexistence[
                "forbidden_strategy_center_write_tables"
            ],
            "virtual_executor_forbidden_strategy_center_execute_scope": coexistence[
                "forbidden_strategy_center_execute_scope"
            ],
            "virtual_executor_operation_attempts": coexistence[
                "required_operation_attempts"
            ],
            "normal_start_interval_pid_runs_change_is_configuration_drift": (
                coexistence[
                    "normal_start_interval_pid_runs_change_is_configuration_drift"
                ]
            ),
        }
        if any(request.get(field) != expected for field, expected in exact_fields.items()):
            return reject
        if any(
            request.get(field) != expected
            for field, expected in coexistence[
                "required_pre_gate_attempt_counts"
            ].items()
        ):
            return reject
        for field, pattern in coexistence["required_hash_fields"].items():
            value = request.get(field)
            if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
                return reject
        if any(
            request.get(field) is not True
            for field in coexistence["required_true_fields"]
        ):
            return reject
        if any(
            request.get(field) is not False
            for field in coexistence["required_false_fields"]
        ):
            return reject
    elif request.get("virtual_executor_loaded_or_running") is not False:
        return reject
    if request.get("declared_write_tables") != policy["allowed_write_tables"]:
        return reject
    if request.get("observation_dml_contract") != policy["observation_dml_contract"]:
        return reject
    if request.get("rollback_contract") != policy["rollback_contract"]:
        return reject
    if request.get("primary_execute_attempts") != policy["primary_execute_attempts"]:
        return reject
    replay_attempts = request.get("idempotence_replay_attempts")
    if isinstance(replay_attempts, bool) or not isinstance(replay_attempts, int):
        return reject
    if replay_attempts < 0 or replay_attempts > policy["maximum_idempotence_replay_attempts"]:
        return reject
    if replay_attempts:
        replay_requirements = (
            ("idempotence_replay_same_scope", "idempotence_replay_requires_same_scope"),
            ("idempotence_replay_same_input", "idempotence_replay_requires_same_input"),
            ("idempotence_replay_same_run_id", "idempotence_replay_requires_same_run_id"),
        )
        if any(policy[required] and request.get(actual) is not True for actual, required in replay_requirements):
            return reject
    return policy["accept_decision"]


class N6StrategyCenterBoundedExecutionPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()
        cls.request = canonical_request(cls.policy)

    def decision(self, **changes: Any) -> str:
        request = copy.deepcopy(self.request)
        request.update(changes)
        return evaluate(self.policy, request)

    def test_canonical_single_user_revision_contract_accepts(self) -> None:
        self.assertEqual(self.decision(), "ACCEPT")
        self.assertEqual(self.policy["runtime_gate_decision"], "ACCEPT")

    def test_unloaded_virtual_executor_path_remains_accepted(self) -> None:
        self.assertEqual(
            self.decision(virtual_executor_loaded_or_running=False),
            "ACCEPT",
        )

    def test_missing_or_invalid_scope_parameter_rejects(self) -> None:
        for field in self.policy["required_scope_fields"]:
            for value in (None, 0, -1, True, "11"):
                with self.subTest(field=field, value=value):
                    self.assertEqual(self.decision(**{field: value}), "REJECT")

    def test_all_users_or_multiple_scope_rejects(self) -> None:
        self.assertEqual(self.decision(all_users_mode=True), "REJECT")
        for field in self.policy["required_singleton_counts"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: 2}), "REJECT")

    def test_non_current_or_invalid_trade_date_rejects(self) -> None:
        self.assertEqual(self.decision(trade_date="20260721"), "REJECT")
        self.assertEqual(self.decision(trade_date="2026-07-22"), "REJECT")

    def test_release_or_input_authority_drift_rejects(self) -> None:
        fields = (
            "active_immutable_release_verified",
            "release_commit_verified",
            "release_tree_verified",
            "release_hash_verified",
            "bounded_runner_present_in_active_release",
            "same_scope_dry_run_passed",
            "input_watermark_frozen",
            "plan_hash_frozen",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        for field in (
            "release_drift_detected",
            "selection_revision_drift_detected",
            "input_watermark_drift_detected",
            "concurrent_runtime_change",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_acl_role_and_write_allowlist_are_exact(self) -> None:
        self.assertEqual(
            self.policy["allowed_write_tables"],
            [
                "n6_user_strategy_selection_revision",
                "n6_strategy_match_projection",
                "n6_strategy_observation_projection",
                "n6_strategy_match_change",
            ],
        )
        self.assertEqual(self.decision(database_role="n6_btrack_web"), "REJECT")
        self.assertEqual(self.decision(strategy_worker_acl_verified=False), "REJECT")
        self.assertEqual(self.decision(acl_drift_detected=True), "REJECT")
        self.assertEqual(
            self.decision(declared_write_tables=self.policy["allowed_write_tables"] + ["n6_virtual_trade"]),
            "REJECT",
        )
        self.assertEqual(self.decision(fifth_write_table_requested=True), "REJECT")

    def test_observation_dml_scope_grain_surface_and_replay_are_exact(self) -> None:
        contract = self.policy["observation_dml_contract"]
        self.assertEqual(
            contract["operations"],
            ["select_for_update", "insert", "update", "delete"],
        )
        expected_scope = [
            "selection_revision_id",
            "principal_id",
            "principal_type",
            "user_id",
            "trade_date",
        ]
        self.assertEqual(contract["scope_predicate_fields"], expected_scope)
        self.assertEqual(contract["insert_scope_columns"], expected_scope)
        self.assertEqual(
            contract["unique_grain_081"],
            [
                "principal_id",
                "principal_type",
                "user_id",
                "trade_date",
                "stock_identity_key",
                "action_episode_key",
                "coherence_episode_key",
                "observation_kind",
                "selection_revision_id",
            ],
        )
        self.assertEqual(contract["same_hash_replay_behavior"], "unchanged")
        self.assertEqual(contract["qualified_surface_kind"], "qualified_match")
        self.assertEqual(contract["observation_surface_kind"], "observation")
        self.assertEqual(
            contract["same_episode_surface_mode"], "mutually_exclusive"
        )
        self.assertTrue(contract["change_dedup_required"])
        drifted = copy.deepcopy(contract)
        drifted["scope_predicate_fields"].remove("trade_date")
        self.assertEqual(
            self.decision(observation_dml_contract=drifted),
            "REJECT",
        )

    def test_observation_authority_and_rollback_fail_closed(self) -> None:
        self.assertEqual(
            self.policy["rollback_contract"],
            {
                "allowed_mutation_resources": [],
                "database_mutation_allowed": False,
                "observation_delete_allowed": False,
                "schema_081_rollback_reject_if_v2_dependencies": [
                    "selection_revision",
                    "match_projection",
                    "observation_projection",
                    "match_change",
                ],
            },
        )
        drifted_rollback = copy.deepcopy(self.policy["rollback_contract"])
        drifted_rollback["observation_delete_allowed"] = True
        self.assertEqual(
            self.decision(rollback_contract=drifted_rollback),
            "REJECT",
        )
        for field in (
            "web_observation_function_only_verified",
            "virtual_executor_observation_write_disjoint_verified",
            "virtual_executor_observation_code_reference_disjoint_verified",
            "observation_rows_preserved_by_rollback",
            "v2_dependency_blocks_081_schema_rollback_verified",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        for field in (
            "cross_scope_observation_write_detected",
            "cross_trade_date_observation_write_detected",
            "observation_scope_predicate_missing",
            "same_episode_dual_surface_detected",
            "duplicate_observation_change_detected",
            "web_observation_table_write_privilege_detected",
            "virtual_executor_observation_table_write_privilege_detected",
            "virtual_executor_observation_code_reference_detected",
            "observation_delete_rollback_requested",
            "schema_081_rollback_with_v2_dependency_requested",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_trade_account_cash_and_position_paths_reject(self) -> None:
        for field in (
            "proposal_touched",
            "order_touched",
            "trade_touched",
            "position_touched",
            "cash_touched",
            "real_broker_connected",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_worker_and_launchagent_changes_reject(self) -> None:
        for field in (
            "long_running_worker_requested",
            "launch_agent_install_or_start_requested",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_post_083_virtual_executor_coexistence_is_exact(self) -> None:
        coexistence = self.policy["virtual_executor_coexistence_contract"]
        self.assertEqual(self.decision(), "ACCEPT")
        cases = {
            "virtual_executor_phase_mode": "general_bounded_canary",
            "selection_revision_id": 19,
            "current_trade_date": "20260724",
            "virtual_executor_launch_agent_label": "com.ashare-v3.n6.other",
            "virtual_executor_launch_agent_plist_path": "/tmp/other.plist",
            "virtual_executor_database_role": "n6_strategy_worker",
            "virtual_executor_pgservice": "n6_strategy_worker",
            "virtual_executor_start_interval_seconds": 6,
            "gate2_attempt_order": [
                "primary_execute",
                "same_scope_dry_run",
                "same_input_replay",
            ],
            "virtual_executor_forbidden_strategy_center_write_tables": [],
            "virtual_executor_forbidden_strategy_center_execute_scope": "some",
            "virtual_executor_operation_attempts": 1,
            "pre_gate_dry_run_attempts": 1,
            "pre_gate_primary_execute_attempts": 1,
            "pre_gate_same_input_replay_attempts": 1,
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: value}), "REJECT")
        self.assertEqual(
            coexistence["required_attempt_order"],
            ["same_scope_dry_run", "primary_execute", "same_input_replay"],
        )

    def test_virtual_executor_hashes_are_required_and_frozen(self) -> None:
        coexistence = self.policy["virtual_executor_coexistence_contract"]
        for field in coexistence["required_hash_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: "bad"}), "REJECT")
        for field in coexistence["required_true_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")

    def test_virtual_executor_operation_privilege_reference_and_drift_reject(self) -> None:
        coexistence = self.policy["virtual_executor_coexistence_contract"]
        for field in coexistence["required_false_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_normal_start_interval_pid_runs_change_is_not_drift(self) -> None:
        coexistence = self.policy["virtual_executor_coexistence_contract"]
        self.assertFalse(
            coexistence[
                "normal_start_interval_pid_runs_change_is_configuration_drift"
            ]
        )
        self.assertEqual(
            self.decision(
                normal_start_interval_pid_runs_change_is_configuration_drift=True
            ),
            "REJECT",
        )

    def test_upstream_and_queue_mutation_rejects(self) -> None:
        self.assertEqual(self.decision(n1_n5_write_requested=True), "REJECT")
        self.assertEqual(self.decision(outbox_inbox_checkpoint_mutation_requested=True), "REJECT")

    def test_current_request_authorization_is_mandatory(self) -> None:
        self.assertEqual(self.decision(explicit_user_authorization_current_request=False), "REJECT")

    def test_every_required_true_field_is_fail_closed(self) -> None:
        for field in self.policy["required_true_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")

    def test_every_required_false_field_is_fail_closed(self) -> None:
        for field in self.policy["required_false_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_general_runtime_or_wrong_policy_rejects(self) -> None:
        self.assertEqual(self.decision(policy_id="general_n6_execute"), "REJECT")
        self.assertEqual(self.decision(layer_role="runtime_control"), "REJECT")
        self.assertEqual(self.decision(runner_basename="other_runner.py"), "REJECT")
        self.assertEqual(self.decision(scope_mode="all_users"), "REJECT")

    def test_execute_and_replay_attempts_are_bounded(self) -> None:
        self.assertEqual(self.decision(primary_execute_attempts=0), "REJECT")
        self.assertEqual(self.decision(primary_execute_attempts=2), "REJECT")
        self.assertEqual(self.decision(idempotence_replay_attempts=2), "REJECT")
        for field in (
            "idempotence_replay_same_scope",
            "idempotence_replay_same_input",
            "idempotence_replay_same_run_id",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")

    def test_control_documents_reference_the_same_policy_and_default_reject(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        compiler = (ROOT / "docs" / "EXECUTION_COMPILER.md").read_text(encoding="utf-8")
        kernel = (ROOT / "docs" / "EXECUTION_KERNEL.md").read_text(encoding="utf-8")
        runtime_gate = (ROOT / "docs" / "EXECUTION_RUNTIME_GATE.md").read_text(encoding="utf-8")
        sandbox = (ROOT / "docs" / "EXECUTION_SANDBOX.md").read_text(encoding="utf-8")
        test_suite = (ROOT / "docs" / "EXECUTION_TEST_SUITE.md").read_text(encoding="utf-8")
        trace = (ROOT / "docs" / "EXECUTION_TRACE_SYSTEM.md").read_text(encoding="utf-8")
        for text in (agents, compiler, kernel, runtime_gate, sandbox, test_suite, trace):
            self.assertIn(POLICY_ID, text)
        self.assertEqual(self.policy["default_runtime_execution_decision"], "REJECT")
        self.assertIn("Compiler success alone never changes", compiler)
        self.assertIn("named_policy_passed", runtime_gate)
        self.assertIn("must not infer or fabricate", sandbox)
        self.assertIn("general N6 execute requests", test_suite)
        self.assertIn("affected_resources", trace)
        self.assertIn("一般性 N6 execute", agents)


if __name__ == "__main__":
    unittest.main()
