from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "n6_strategy_center_post_081_v2_catalog_migration_window_v1"
POLICY_BEGIN = f"<!-- policy:{POLICY_ID}:begin -->"
POLICY_END = f"<!-- policy:{POLICY_ID}:end -->"


def load_policy() -> dict[str, Any]:
    text = (ROOT / "docs" / "EXECUTION_KERNEL.md").read_text(encoding="utf-8")
    start = text.index(POLICY_BEGIN) + len(POLICY_BEGIN)
    end = text.index(POLICY_END, start)
    fenced = text[start:end].strip()
    match = re.fullmatch(r"```json\s*(\{.*\})\s*```", fenced, re.DOTALL)
    if match is None:
        raise AssertionError("catalog migration policy must contain one JSON fence")
    return json.loads(match.group(1))


def canonical_request(policy: dict[str, Any], phase_mode: str) -> dict[str, Any]:
    phase = policy["allowed_phase_modes"][phase_mode]
    request: dict[str, Any] = {
        "policy_id": policy["policy_id"],
        "layer_role": policy["layer_role"],
        "scope_mode": policy["scope_mode"],
        "phase_mode": phase_mode,
        "migration_id": phase["migration_id"],
        "migration_forward_basename": phase["forward_basename"],
        "migration_rollback_basename": phase["rollback_basename"],
        "requested_migration_ids": [phase["migration_id"]],
        "release_path": (
            f"{policy['release_root']}/"
            "20260723_160843__c021cc46cd5c64c29cff2429584edda0d29bacf9"
        ),
        "web_launch_agent_label": policy["web_launch_agent_label"],
        "evaluator_launch_agent_label": policy["evaluator_launch_agent_label"],
        "virtual_executor_launch_agent_label": policy[
            "virtual_executor_launch_agent_label"
        ],
        "strategy_write_flag": policy["required_strategy_write_flag_value"],
        "database_authority_mode": policy["required_database_authority_mode"],
        "declared_schema_objects": list(phase["allowed_schema_objects"]),
        "declared_data_mutations": list(phase["allowed_data_mutations"]),
        "normal_virtual_executor_pid_runs_change_is_configuration_drift": policy[
            "normal_virtual_executor_pid_runs_change_is_configuration_drift"
        ],
        "transaction_not_committed_skips_sql_rollback": policy[
            "transaction_not_committed_skips_sql_rollback"
        ],
        "post_082_keep_maintenance_window_open": policy[
            "post_082_keep_maintenance_window_open"
        ],
        "post_083_failure_keeps_strategy_write_zero_and_evaluator_quiesced": policy[
            "post_083_failure_keeps_strategy_write_zero_and_evaluator_quiesced"
        ],
    }
    request.update(policy["required_singleton_counts"])
    request.update(policy["required_operation_counts"])
    for field, pattern in policy["required_hash_fields"].items():
        request[field] = "c" * (40 if "{40}" in pattern else 64)
    request.update({field: True for field in policy["required_true_fields"]})
    request.update({field: False for field in policy["required_false_fields"]})
    request.update({field: True for field in phase["required_true_fields"]})
    request.update({field: False for field in phase["required_false_fields"]})
    return request


def exact_non_negative_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def evaluate(policy: dict[str, Any], request: dict[str, Any]) -> str:
    reject = policy["default_runtime_execution_decision"]
    exact_fields = (
        "policy_id",
        "layer_role",
        "scope_mode",
        "web_launch_agent_label",
        "evaluator_launch_agent_label",
        "virtual_executor_launch_agent_label",
    )
    if any(request.get(field) != policy[field] for field in exact_fields):
        return reject
    if request.get("strategy_write_flag") != policy[
        "required_strategy_write_flag_value"
    ]:
        return reject
    if request.get("database_authority_mode") != policy[
        "required_database_authority_mode"
    ]:
        return reject

    phase_mode = request.get("phase_mode")
    phase = policy["allowed_phase_modes"].get(phase_mode)
    if phase is None:
        return reject
    if request.get("migration_id") != phase["migration_id"]:
        return reject
    if request.get("migration_forward_basename") != phase["forward_basename"]:
        return reject
    if request.get("migration_rollback_basename") != phase["rollback_basename"]:
        return reject
    if request.get("requested_migration_ids") != [phase["migration_id"]]:
        return reject
    if request.get("declared_schema_objects") != phase["allowed_schema_objects"]:
        return reject
    if request.get("declared_data_mutations") != phase["allowed_data_mutations"]:
        return reject

    release_path = request.get("release_path")
    if not isinstance(release_path, str):
        return reject
    release = Path(release_path)
    if str(release.parent) != policy["release_root"]:
        return reject
    if re.fullmatch(r"[0-9]{8}_[0-9]{6}__[0-9a-f]{40}", release.name) is None:
        return reject

    for field, pattern in policy["required_hash_fields"].items():
        value = request.get(field)
        if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
            return reject
    for field, expected in policy["required_singleton_counts"].items():
        value = request.get(field)
        if not exact_non_negative_int(value) or value != expected:
            return reject
    for field, expected in policy["required_operation_counts"].items():
        value = request.get(field)
        if not exact_non_negative_int(value) or value != expected:
            return reject
    if any(request.get(field) is not True for field in policy["required_true_fields"]):
        return reject
    if any(request.get(field) is not False for field in policy["required_false_fields"]):
        return reject
    if any(request.get(field) is not True for field in phase["required_true_fields"]):
        return reject
    if any(request.get(field) is not False for field in phase["required_false_fields"]):
        return reject

    fixed_values = {
        "normal_virtual_executor_pid_runs_change_is_configuration_drift": policy[
            "normal_virtual_executor_pid_runs_change_is_configuration_drift"
        ],
        "transaction_not_committed_skips_sql_rollback": policy[
            "transaction_not_committed_skips_sql_rollback"
        ],
        "post_082_keep_maintenance_window_open": policy[
            "post_082_keep_maintenance_window_open"
        ],
        "post_083_failure_keeps_strategy_write_zero_and_evaluator_quiesced": policy[
            "post_083_failure_keeps_strategy_write_zero_and_evaluator_quiesced"
        ],
    }
    if any(request.get(field) != value for field, value in fixed_values.items()):
        return reject
    return policy["accept_decision"]


class N6StrategyCenterPost081V2CatalogMigrationPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()
        cls.request_082 = canonical_request(cls.policy, "execute_082_tooling_once")
        cls.request_083 = canonical_request(
            cls.policy, "execute_083_catalog_activation_once"
        )

    def decision(self, phase: str = "082", **changes: Any) -> str:
        source = self.request_082 if phase == "082" else self.request_083
        request = copy.deepcopy(source)
        request.update(changes)
        return evaluate(self.policy, request)

    def test_exact_082_contract_accepts(self) -> None:
        self.assertEqual(self.decision(), "ACCEPT")
        self.assertEqual(self.policy["runtime_gate_decision"], "ACCEPT")

    def test_exact_083_contract_accepts(self) -> None:
        self.assertEqual(self.decision("083"), "ACCEPT")

    def test_default_and_unknown_runtime_execution_reject(self) -> None:
        self.assertEqual(self.policy["default_runtime_execution_decision"], "REJECT")
        self.assertEqual(self.decision(policy_id="general_runtime_execute"), "REJECT")
        self.assertEqual(self.decision(phase_mode="all_migrations"), "REJECT")

    def test_current_request_authorization_is_required(self) -> None:
        self.assertEqual(
            self.decision(explicit_user_authorization_current_request=False),
            "REJECT",
        )

    def test_every_common_true_field_is_fail_closed(self) -> None:
        for field in self.policy["required_true_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")

    def test_every_common_false_field_is_fail_closed(self) -> None:
        for field in self.policy["required_false_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_every_082_phase_field_is_fail_closed(self) -> None:
        phase = self.policy["allowed_phase_modes"]["execute_082_tooling_once"]
        for field in phase["required_true_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        for field in phase["required_false_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_every_083_phase_field_is_fail_closed(self) -> None:
        phase = self.policy["allowed_phase_modes"][
            "execute_083_catalog_activation_once"
        ]
        for field in phase["required_true_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision("083", **{field: False}), "REJECT")
        for field in phase["required_false_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision("083", **{field: True}), "REJECT")

    def test_exact_n6_user_scope_and_labels_are_required(self) -> None:
        cases = {
            "layer_role": "runtime_control",
            "scope_mode": "all_users",
            "web_launch_agent_label": "other",
            "evaluator_launch_agent_label": "other",
            "virtual_executor_launch_agent_label": "other",
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: value}), "REJECT")

    def test_one_phase_one_migration_one_transaction_are_required(self) -> None:
        self.assertEqual(
            self.decision(requested_migration_ids=["082", "083"]), "REJECT"
        )
        self.assertEqual(self.decision(combined_082_083_requested=True), "REJECT")
        for field in (
            "migration_phase_count",
            "migration_count",
            "database_transaction_count",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: 2}), "REJECT")

    def test_082_requires_committed_081_and_absent_082_083(self) -> None:
        for field in (
            "migration_081_committed_verified",
            "migration_082_not_executed_verified",
            "migration_083_not_executed_verified",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")

    def test_082_requires_zero_pending_and_install_only_scope(self) -> None:
        self.assertEqual(
            self.decision(pending_revision_count_zero_verified=False), "REJECT"
        )
        self.assertEqual(
            self.decision(migration_082_compensation_function_call_requested=True),
            "REJECT",
        )
        self.assertEqual(self.decision(selection_revision_write_requested=True), "REJECT")
        self.assertEqual(self.decision(catalog_write_requested=True), "REJECT")
        self.assertEqual(self.decision(projection_change_write_requested=True), "REJECT")
        self.assertEqual(self.decision(declared_schema_objects=[]), "REJECT")
        self.assertEqual(self.decision(declared_data_mutations=["revision"]), "REJECT")

    def test_083_requires_082_postflight_and_open_day(self) -> None:
        fields = (
            "migration_081_committed_verified",
            "migration_082_committed_verified",
            "migration_083_not_executed_verified",
            "migration_082_postflight_and_acl_passed",
            "current_open_trade_date_verified",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision("083", **{field: False}), "REJECT")

    def test_083_requires_selection_quiescence_and_active_v1_coverage(self) -> None:
        fields = (
            "pending_revision_count_zero_verified",
            "unique_active_v1_per_active_principal_verified",
            "v2_selection_item_count_zero_verified",
            "catalog_transition_exact_verified",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision("083", **{field: False}), "REJECT")

    def test_083_allows_only_exact_catalog_mutations(self) -> None:
        self.assertEqual(
            self.decision("083", declared_data_mutations=["all_catalog"]), "REJECT"
        )
        self.assertEqual(self.decision("083", declared_schema_objects=["table"]), "REJECT")
        self.assertEqual(
            self.decision("083", selection_revision_write_requested=True), "REJECT"
        )
        self.assertEqual(
            self.decision("083", selection_item_write_requested=True), "REJECT"
        )
        self.assertEqual(
            self.decision("083", projection_change_write_requested=True), "REJECT"
        )

    def test_strategy_write_and_evaluator_must_remain_quiesced(self) -> None:
        self.assertEqual(self.decision(strategy_write_flag="1"), "REJECT")
        self.assertEqual(self.decision(strategy_write_zero_verified=False), "REJECT")
        self.assertEqual(self.decision(evaluator_job_absent_verified=False), "REJECT")
        self.assertEqual(self.decision(evaluator_pid_absent_verified=False), "REJECT")
        for field in (
            "strategy_evaluator_execute_requested",
            "strategy_evaluator_start_requested",
            "strategy_evaluator_restore_requested",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_virtual_executor_is_frozen_disjoint_and_not_operated(self) -> None:
        fields = (
            "virtual_executor_configuration_frozen",
            "virtual_executor_role_acl_frozen",
            "virtual_executor_object_boundary_frozen",
            "virtual_executor_strategy_center_write_disjoint_verified",
            "virtual_executor_not_operated_verified",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        self.assertEqual(self.decision(virtual_executor_operation_requested=True), "REJECT")
        self.assertEqual(
            self.decision(virtual_executor_configuration_drift_detected=True), "REJECT"
        )

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

    def test_release_migration_and_maintenance_hashes_fail_closed(self) -> None:
        for field in self.policy["required_hash_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: "bad"}), "REJECT")
        self.assertEqual(self.decision(release_path="/tmp/release"), "REJECT")

    def test_owner_transaction_lock_and_postflight_are_required(self) -> None:
        fields = (
            "database_owner_authority_verified",
            "on_error_stop_enabled",
            "explicit_begin_commit_defined",
            "advisory_transaction_lock_defined",
            "before_after_watermarks_frozen",
            "postflight_defined",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        self.assertEqual(self.decision(database_authority_mode="worker"), "REJECT")

    def test_attempts_retries_and_rollback_are_exact(self) -> None:
        self.assertEqual(self.decision(forward_attempts=0), "REJECT")
        self.assertEqual(self.decision(forward_attempts=2), "REJECT")
        self.assertEqual(self.decision(primary_retries=1), "REJECT")
        self.assertEqual(self.decision(rollback_attempts=1), "REJECT")
        self.assertEqual(self.decision(transaction_not_committed_skips_sql_rollback=False), "REJECT")
        self.assertEqual(self.decision(rollback_requires_separate_authorization=False), "REJECT")

    def test_web_other_migration_and_long_worker_paths_reject(self) -> None:
        fields = (
            "web_rebind_requested",
            "other_migration_requested",
            "other_launch_agent_touched",
            "long_term_worker_install_requested",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_business_queue_trading_and_n1_n5_paths_reject(self) -> None:
        fields = (
            "business_dml_requested",
            "outbox_inbox_checkpoint_mutation_requested",
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

    def test_drift_and_concurrency_reject(self) -> None:
        fields = (
            "release_drift_detected",
            "migration_hash_drift_detected",
            "plist_runner_acl_or_ownership_drift_detected",
            "maintenance_evidence_drift_detected",
            "concurrent_runtime_change",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_phase_basenames_are_exact(self) -> None:
        self.assertEqual(
            self.request_082["migration_forward_basename"],
            "082_n6_strategy_center_v2_user_compensation.sql",
        )
        self.assertEqual(
            self.request_083["migration_forward_basename"],
            "083_n6_strategy_center_v2_catalog_activation.sql",
        )
        self.assertEqual(self.decision(migration_forward_basename="082.sql"), "REJECT")

    def test_decision_enumeration_remains_standard(self) -> None:
        self.assertIn(self.policy["accept_decision"], {"ACCEPT", "REJECT", "BLOCK", "ESCALATE"})
        self.assertIn(
            self.policy["default_runtime_execution_decision"],
            {"ACCEPT", "REJECT", "BLOCK", "ESCALATE"},
        )

    def test_all_control_documents_name_the_policy(self) -> None:
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
                    POLICY_ID, (ROOT / relative).read_text(encoding="utf-8")
                )

    def test_existing_named_policies_remain_present(self) -> None:
        kernel = (ROOT / "docs" / "EXECUTION_KERNEL.md").read_text(encoding="utf-8")
        for policy_id in (
            "n6_strategy_center_schema_migration_maintenance_window_v1",
            "n6_strategy_center_post_081_v2_web_bounded_rebind_v1",
            "n6_user_web_immutable_release_bounded_rebind_v1",
        ):
            with self.subTest(policy_id=policy_id):
                self.assertIn(f"<!-- policy:{policy_id}:begin -->", kernel)


if __name__ == "__main__":
    unittest.main()
