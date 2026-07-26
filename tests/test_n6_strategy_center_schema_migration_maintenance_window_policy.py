from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "n6_strategy_center_schema_migration_maintenance_window_v1"
POLICY_BEGIN = f"<!-- policy:{POLICY_ID}:begin -->"
POLICY_END = f"<!-- policy:{POLICY_ID}:end -->"


def load_policy() -> dict[str, Any]:
    text = (ROOT / "docs" / "EXECUTION_KERNEL.md").read_text(encoding="utf-8")
    start = text.index(POLICY_BEGIN) + len(POLICY_BEGIN)
    end = text.index(POLICY_END, start)
    fenced = text[start:end].strip()
    match = re.fullmatch(r"```json\s*(\{.*\})\s*```", fenced, re.DOTALL)
    if match is None:
        raise AssertionError("maintenance-window policy must contain one valid JSON fence")
    return json.loads(match.group(1))


def canonical_request(policy: dict[str, Any]) -> dict[str, Any]:
    release_path = (
        f"{policy['release_root']}/"
        "20260723_124546__168f375aa089d8bd384971c94730d233f1327826"
    )
    token_hash = "a" * 64
    request: dict[str, Any] = {
        "policy_id": policy["policy_id"],
        "layer_role": policy["layer_role"],
        "scope_mode": policy["scope_mode"],
        "phase_mode": policy["phase_mode"],
        "migration_id": policy["migration_id"],
        "migration_forward_basename": policy["migration_forward_basename"],
        "migration_rollback_basename": policy["migration_rollback_basename"],
        "requested_migration_ids": [policy["migration_id"]],
        "web_launch_agent_label": policy["web_launch_agent_label"],
        "web_launch_agent_plist_path": policy["web_launch_agent_plist_path"],
        "evaluator_launch_agent_label": policy["evaluator_launch_agent_label"],
        "evaluator_launch_agent_plist_path": policy[
            "evaluator_launch_agent_plist_path"
        ],
        "virtual_executor_launch_agent_label": policy[
            "virtual_executor_launch_agent_label"
        ],
        "release_path": release_path,
        "maintenance_token_path": (
            f"{policy['maintenance_token_root']}/"
            f"081-maintenance-20260723T131500+0800__{token_hash}.json"
        ),
        "web_strategy_write_flag": policy["web_strategy_write_flag"],
        "web_strategy_write_flag_before": policy[
            "web_strategy_write_flag_before"
        ],
        "web_strategy_write_flag_during": policy[
            "web_strategy_write_flag_during"
        ],
        "web_teardown_timeout_seconds": policy["web_teardown_timeout_seconds"],
        "web_readiness_timeout_seconds": policy["web_readiness_timeout_seconds"],
        "web_stability_window_seconds": policy["web_stability_window_seconds"],
        "evaluator_teardown_timeout_seconds": policy[
            "evaluator_teardown_timeout_seconds"
        ],
        "maintenance_token_max_age_seconds": policy[
            "maintenance_token_max_age_seconds"
        ],
        "route_expectations": copy.deepcopy(policy["required_route_expectations"]),
        "readonly_watermark_tables": list(policy["allowed_readonly_watermark_tables"]),
        "declared_mutation_resources": list(policy["allowed_mutation_resources"]),
        "declared_runtime_operations": list(policy["allowed_runtime_operations"]),
        "pre_migration_web_restore_attempts": 0,
        "quiesce_failed": False,
        "migration_started": False,
        "normal_periodic_pid_runs_change_is_configuration_drift": False,
        "migration_transaction_authorized": False,
        "post_081_keep_web_strategy_writes_disabled": True,
        "post_081_keep_old_evaluator_quiesced": True,
    }
    request.update(policy["required_singleton_counts"])
    request.update(policy["required_operation_counts"])
    request.update({field: "b" * 64 for field in policy["required_hash_fields"]})
    request["release_commit_sha"] = "c" * 40
    request["release_tree_sha"] = "d" * 40
    request["maintenance_token_file_sha256"] = token_hash
    request.update({field: True for field in policy["required_true_fields"]})
    request.update({field: False for field in policy["required_false_fields"]})
    return request


def exact_non_negative_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def evaluate(policy: dict[str, Any], request: dict[str, Any]) -> str:
    reject = policy["default_runtime_execution_decision"]
    exact_fields = (
        "policy_id",
        "layer_role",
        "scope_mode",
        "phase_mode",
        "migration_id",
        "migration_forward_basename",
        "migration_rollback_basename",
        "web_launch_agent_label",
        "web_launch_agent_plist_path",
        "evaluator_launch_agent_label",
        "evaluator_launch_agent_plist_path",
        "virtual_executor_launch_agent_label",
        "web_strategy_write_flag",
        "web_strategy_write_flag_before",
        "web_strategy_write_flag_during",
        "web_teardown_timeout_seconds",
        "web_readiness_timeout_seconds",
        "web_stability_window_seconds",
        "evaluator_teardown_timeout_seconds",
        "maintenance_token_max_age_seconds",
    )
    if any(request.get(field) != policy[field] for field in exact_fields):
        return reject
    if request.get("requested_migration_ids") != [policy["migration_id"]]:
        return reject

    release_path = request.get("release_path")
    if not isinstance(release_path, str):
        return reject
    release = Path(release_path)
    if str(release.parent) != policy["release_root"]:
        return reject
    if re.fullmatch(r"[0-9]{8}_[0-9]{6}__[0-9a-f]{40}", release.name) is None:
        return reject

    token_path = request.get("maintenance_token_path")
    if not isinstance(token_path, str):
        return reject
    token = Path(token_path)
    if str(token.parent) != policy["maintenance_token_root"]:
        return reject
    if re.fullmatch(policy["maintenance_token_name_pattern"], token.name) is None:
        return reject

    for field, pattern in policy["required_hash_fields"].items():
        value = request.get(field)
        if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
            return reject
    token_name_hash = token.name.removesuffix(".json").rsplit("__", 1)[-1]
    if token_name_hash != request.get("maintenance_token_file_sha256"):
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
    if request.get("declared_mutation_resources") != policy["allowed_mutation_resources"]:
        return reject
    if request.get("declared_runtime_operations") != policy["allowed_runtime_operations"]:
        return reject
    if request.get("readonly_watermark_tables") != policy[
        "allowed_readonly_watermark_tables"
    ]:
        return reject
    if request.get("route_expectations") != policy["required_route_expectations"]:
        return reject

    restore_attempts = request.get("pre_migration_web_restore_attempts")
    if not exact_non_negative_int(restore_attempts):
        return reject
    if restore_attempts > policy["maximum_pre_migration_web_restore_attempts"]:
        return reject
    if restore_attempts:
        if request.get("quiesce_failed") is not True:
            return reject
        if request.get("migration_started") is not False:
            return reject

    fixed_values = {
        "normal_periodic_pid_runs_change_is_configuration_drift": policy[
            "normal_periodic_pid_runs_change_is_configuration_drift"
        ],
        "migration_transaction_authorized": policy[
            "migration_transaction_authorized"
        ],
        "post_081_keep_web_strategy_writes_disabled": policy[
            "post_081_keep_web_strategy_writes_disabled"
        ],
        "post_081_keep_old_evaluator_quiesced": policy[
            "post_081_keep_old_evaluator_quiesced"
        ],
    }
    if any(request.get(field) != value for field, value in fixed_values.items()):
        return reject
    return policy["accept_decision"]


class N6StrategyCenterMaintenanceWindowPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()
        cls.request = canonical_request(cls.policy)

    def decision(self, **changes: Any) -> str:
        request = copy.deepcopy(self.request)
        request.update(changes)
        return evaluate(self.policy, request)

    def test_exact_prepare_only_contract_accepts(self) -> None:
        self.assertEqual(self.decision(), "ACCEPT")
        self.assertEqual(self.policy["runtime_gate_decision"], "ACCEPT")

    def test_default_and_unknown_runtime_execution_reject(self) -> None:
        self.assertEqual(self.policy["default_runtime_execution_decision"], "REJECT")
        self.assertEqual(self.decision(policy_id="general_runtime_execute"), "REJECT")

    def test_current_user_authorization_is_required(self) -> None:
        self.assertEqual(
            self.decision(explicit_user_authorization_current_request=False),
            "REJECT",
        )

    def test_exact_runtime_control_scope_and_labels_are_required(self) -> None:
        cases = {
            "layer_role": "N6_user",
            "scope_mode": "all_migrations",
            "phase_mode": "execute_081",
            "web_launch_agent_label": "com.ashare-v3.n6.other",
            "evaluator_launch_agent_label": "com.ashare-v3.n6.other",
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: value}), "REJECT")

    def test_only_exact_081_is_allowed(self) -> None:
        self.assertEqual(self.decision(migration_id="082"), "REJECT")
        self.assertEqual(self.decision(requested_migration_ids=["081", "082"]), "REJECT")
        self.assertEqual(self.decision(migration_082_requested=True), "REJECT")
        self.assertEqual(self.decision(migration_083_requested=True), "REJECT")

    def test_migration_execution_and_database_write_or_lock_reject(self) -> None:
        self.assertEqual(self.decision(migration_execution_requested=True), "REJECT")
        self.assertEqual(self.decision(migration_execution_attempts=1), "REJECT")
        self.assertEqual(self.decision(database_write_requested=True), "REJECT")
        self.assertEqual(self.decision(database_write_attempts=1), "REJECT")
        self.assertEqual(self.decision(database_lock_requested=True), "REJECT")

    def test_web_selection_write_quiescence_is_required(self) -> None:
        self.assertEqual(self.decision(web_strategy_write_flag_during="1"), "REJECT")
        self.assertEqual(self.decision(selection_writes_quiesced=False), "REJECT")
        self.assertEqual(self.decision(web_only_strategy_write_flag_changed=False), "REJECT")
        self.assertEqual(self.decision(web_other_environment_byte_equivalent=False), "REJECT")

    def test_evaluator_must_be_absent_and_cannot_bootstrap(self) -> None:
        self.assertEqual(self.decision(evaluator_pid_absent=False), "REJECT")
        self.assertEqual(self.decision(evaluator_job_absent=False), "REJECT")
        self.assertEqual(self.decision(evaluator_bootstrap_attempts=1), "REJECT")
        self.assertEqual(self.decision(evaluator_bootstrap_requested=True), "REJECT")

    def test_virtual_executor_is_frozen_but_not_operated(self) -> None:
        self.assertEqual(self.decision(virtual_executor_object_disjoint_verified=False), "REJECT")
        self.assertEqual(self.decision(virtual_executor_operation_attempts=1), "REJECT")
        self.assertEqual(self.decision(virtual_executor_operation_requested=True), "REJECT")

    def test_normal_periodic_pid_runs_change_is_not_drift(self) -> None:
        self.assertEqual(self.decision(), "ACCEPT")
        self.assertFalse(
            self.request["normal_periodic_pid_runs_change_is_configuration_drift"]
        )
        self.assertEqual(
            self.decision(normal_periodic_pid_runs_change_is_configuration_drift=True),
            "REJECT",
        )

    def test_release_migration_plist_acl_and_ownership_drift_reject(self) -> None:
        fields = (
            "release_drift_detected",
            "migration_hash_drift_detected",
            "plist_or_runner_drift_detected",
            "acl_or_role_drift_detected",
            "ownership_ambiguous",
            "concurrent_runtime_change",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_token_path_hash_mode_expiry_and_watermark_are_required(self) -> None:
        self.assertEqual(self.decision(maintenance_token_fields_complete=False), "REJECT")
        self.assertEqual(self.decision(maintenance_token_hash_verified=False), "REJECT")
        self.assertEqual(self.decision(maintenance_token_mode_0444_verified=False), "REJECT")
        self.assertEqual(
            self.decision(maintenance_token_missing_expired_or_drifted=True),
            "REJECT",
        )
        self.assertEqual(self.decision(strategy_watermarks_frozen=False), "REJECT")
        self.assertEqual(
            self.decision(maintenance_token_file_sha256="e" * 64),
            "REJECT",
        )

    def test_release_and_token_must_be_direct_children_with_exact_names(self) -> None:
        self.assertEqual(self.decision(release_path="/tmp/release"), "REJECT")
        self.assertEqual(self.decision(maintenance_token_path="/tmp/token.json"), "REJECT")

    def test_hash_fields_fail_closed(self) -> None:
        for field in self.policy["required_hash_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: "bad"}), "REJECT")

    def test_exact_resources_operations_and_watermark_scope_are_required(self) -> None:
        self.assertEqual(self.decision(declared_mutation_resources=[]), "REJECT")
        self.assertEqual(self.decision(declared_runtime_operations=[]), "REJECT")
        self.assertEqual(self.decision(readonly_watermark_tables=[]), "REJECT")
        self.assertNotIn(
            "n6_user_strategy_selection_item",
            self.policy["allowed_readonly_watermark_tables"],
        )

    def test_singleton_and_operation_counts_fail_closed(self) -> None:
        fields = {
            **self.policy["required_singleton_counts"],
            **self.policy["required_operation_counts"],
        }
        for field, expected in fields.items():
            for value in (True, -1, expected + 1):
                with self.subTest(field=field, value=value):
                    self.assertEqual(self.decision(**{field: value}), "REJECT")

    def test_no_fixed_sleep_kill_kickstart_retry_or_extra_service(self) -> None:
        fields = (
            "fixed_sleep_substituted_for_state_wait",
            "kill_or_kickstart_requested",
            "primary_retry_requested",
            "other_launch_agent_touched",
            "multiple_services_requested",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_general_business_and_trading_paths_remain_rejected(self) -> None:
        fields = (
            "proposal_touched",
            "order_touched",
            "trade_touched",
            "position_touched",
            "cash_touched",
            "real_broker_connected",
            "n1_n5_write_requested",
            "outbox_inbox_checkpoint_mutation_requested",
            "long_term_worker_install_requested",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_old_v1_evaluator_restore_after_081_rejects(self) -> None:
        self.assertEqual(
            self.decision(old_v1_evaluator_restore_after_081_requested=True),
            "REJECT",
        )
        self.assertEqual(
            self.decision(post_081_keep_old_evaluator_quiesced=False),
            "REJECT",
        )
        self.assertEqual(
            self.decision(post_081_keep_web_strategy_writes_disabled=False),
            "REJECT",
        )

    def test_pre_migration_web_restore_is_bounded_and_conditional(self) -> None:
        self.assertEqual(
            self.decision(
                pre_migration_web_restore_attempts=1,
                quiesce_failed=True,
                migration_started=False,
            ),
            "ACCEPT",
        )
        self.assertEqual(
            self.decision(pre_migration_web_restore_attempts=1),
            "REJECT",
        )
        self.assertEqual(
            self.decision(
                pre_migration_web_restore_attempts=1,
                quiesce_failed=True,
                migration_started=True,
            ),
            "REJECT",
        )
        self.assertEqual(
            self.decision(
                pre_migration_web_restore_attempts=2,
                quiesce_failed=True,
            ),
            "REJECT",
        )

    def test_all_control_documents_name_the_policy(self) -> None:
        for relative in (
            "AGENTS.md",
            "docs/EXECUTION_COMPILER.md",
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

    def test_policy_does_not_authorize_migration_transaction(self) -> None:
        self.assertFalse(self.policy["migration_transaction_authorized"])
        self.assertEqual(
            self.decision(migration_transaction_authorized=True),
            "REJECT",
        )


if __name__ == "__main__":
    unittest.main()
