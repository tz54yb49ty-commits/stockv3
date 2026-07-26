from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "n6_strategy_center_post_083_single_user_pending_v2_revision_v1"
POLICY_BEGIN = f"<!-- policy:{POLICY_ID}:begin -->"
POLICY_END = f"<!-- policy:{POLICY_ID}:end -->"


def load_policy() -> dict[str, Any]:
    text = (ROOT / "docs" / "EXECUTION_KERNEL.md").read_text(encoding="utf-8")
    start = text.index(POLICY_BEGIN) + len(POLICY_BEGIN)
    end = text.index(POLICY_END, start)
    match = re.fullmatch(
        r"```json\s*(\{.*\})\s*```",
        text[start:end].strip(),
        re.DOTALL,
    )
    if match is None:
        raise AssertionError("pending V2 revision policy must contain one JSON fence")
    return json.loads(match.group(1))


def canonical_request(policy: dict[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {
        "policy_id": policy["policy_id"],
        "layer_role": policy["layer_role"],
        "scope_mode": policy["scope_mode"],
        "phase_mode": policy["phase_mode"],
        "recovery_contract_version": policy["recovery_contract_version"],
        "historical_pre_dml_harness_failures": copy.deepcopy(
            policy["required_historical_pre_dml_harness_failures"]
        ),
        "guard_repair_mode": policy["required_guard_repair_mode"],
        "preflight_mode": policy["required_preflight_mode"],
        "request_id_binding_mode": policy["required_request_id_binding_mode"],
        "mutation_statement_classes": list(
            policy["required_mutation_statement_classes"]
        ),
        "strategy_write_flag": policy["required_strategy_write_flag_value"],
        "database_authority_mode": policy["required_database_authority_mode"],
        "selection_creation_authority_mode": policy[
            "allowed_selection_creation_authority_modes"
        ][0],
        "request_id": "12345678-1234-4abc-8def-1234567890ab",
        "canary_scope": copy.deepcopy(policy["exact_canary_scope"]),
        "declared_write_tables": list(policy["allowed_write_tables"]),
        "declared_mutations": list(policy["allowed_mutations"]),
        "strategy_write_must_remain_zero": policy[
            "strategy_write_must_remain_zero"
        ],
        "web_write_path_used": policy["web_write_path_used"],
        "revision_activation_authorized": policy[
            "revision_activation_authorized"
        ],
        "transaction_not_committed_skips_sql_rollback": policy[
            "transaction_not_committed_skips_sql_rollback"
        ],
        "rollback_requires_separate_authorization": policy[
            "rollback_requires_separate_authorization"
        ],
    }
    request.update(policy["required_singleton_counts"])
    request.update(policy["required_operation_counts"])
    request.update({field: "a" * 64 for field in policy["required_hash_fields"]})
    request.update({field: True for field in policy["required_true_fields"]})
    request.update({field: False for field in policy["required_false_fields"]})
    return request


def exact_non_negative_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def evaluate(policy: dict[str, Any], request: dict[str, Any]) -> str:
    reject = policy["default_runtime_execution_decision"]
    for field in (
        "policy_id",
        "layer_role",
        "scope_mode",
        "phase_mode",
        "recovery_contract_version",
    ):
        if request.get(field) != policy[field]:
            return reject
    if request.get("historical_pre_dml_harness_failures") != policy[
        "required_historical_pre_dml_harness_failures"
    ]:
        return reject
    if request.get("guard_repair_mode") != policy["required_guard_repair_mode"]:
        return reject
    if request.get("preflight_mode") != policy["required_preflight_mode"]:
        return reject
    if request.get("request_id_binding_mode") != policy[
        "required_request_id_binding_mode"
    ]:
        return reject
    if request.get("mutation_statement_classes") != policy[
        "required_mutation_statement_classes"
    ]:
        return reject
    if request.get("strategy_write_flag") != policy[
        "required_strategy_write_flag_value"
    ]:
        return reject
    if request.get("database_authority_mode") != policy[
        "required_database_authority_mode"
    ]:
        return reject
    if request.get("selection_creation_authority_mode") not in policy[
        "allowed_selection_creation_authority_modes"
    ]:
        return reject
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or re.fullmatch(
        policy["required_request_id_pattern"], request_id
    ) is None:
        return reject
    if request.get("canary_scope") != policy["exact_canary_scope"]:
        return reject
    if request.get("declared_write_tables") != policy["allowed_write_tables"]:
        return reject
    if request.get("declared_mutations") != policy["allowed_mutations"]:
        return reject
    for field, expected in policy["required_singleton_counts"].items():
        value = request.get(field)
        if not exact_non_negative_int(value) or value != expected:
            return reject
    for field, expected in policy["required_operation_counts"].items():
        value = request.get(field)
        if not exact_non_negative_int(value) or value != expected:
            return reject
    for field, pattern in policy["required_hash_fields"].items():
        value = request.get(field)
        if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
            return reject
    for before_field, after_field in policy["required_equal_hash_pairs"]:
        if request.get(before_field) != request.get(after_field):
            return reject
    if any(request.get(field) is not True for field in policy["required_true_fields"]):
        return reject
    if any(request.get(field) is not False for field in policy["required_false_fields"]):
        return reject
    fixed = {
        "strategy_write_must_remain_zero": True,
        "web_write_path_used": False,
        "revision_activation_authorized": False,
        "transaction_not_committed_skips_sql_rollback": True,
        "rollback_requires_separate_authorization": True,
    }
    if any(request.get(field) is not expected for field, expected in fixed.items()):
        return reject
    return policy["accept_decision"]


class Post083SingleUserPendingV2RevisionPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()
        cls.request = canonical_request(cls.policy)

    def decision(self, **changes: Any) -> str:
        request = copy.deepcopy(self.request)
        request.update(changes)
        return evaluate(self.policy, request)

    def changed_scope(self, **changes: Any) -> dict[str, Any]:
        scope = copy.deepcopy(self.policy["exact_canary_scope"])
        scope.update(changes)
        return scope

    def test_exact_contract_accepts_and_outputs_policy_id(self) -> None:
        self.assertEqual(self.decision(), "ACCEPT")
        self.assertEqual(self.policy["runtime_gate_decision"], "ACCEPT")
        self.assertEqual(self.policy["policy_id"], POLICY_ID)
        self.assertEqual(
            self.policy["recovery_contract_version"],
            "pre_dml_guard_harness_recovery_v2",
        )

    def test_decision_enumeration_remains_exact(self) -> None:
        self.assertEqual(
            self.policy["decision_states"],
            ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"],
        )

    def test_general_runtime_and_database_execution_default_reject(self) -> None:
        self.assertEqual(self.policy["default_runtime_execution_decision"], "REJECT")
        self.assertEqual(self.decision(policy_id="general_runtime_execute"), "REJECT")
        self.assertEqual(self.decision(scope_mode="general_database_write"), "REJECT")
        self.assertEqual(self.decision(layer_role="runtime_control"), "REJECT")

    def test_authorization_and_exact_n6_user_scope_are_required(self) -> None:
        self.assertEqual(
            self.decision(explicit_user_authorization_current_request=False),
            "REJECT",
        )
        self.assertEqual(self.decision(all_users_requested=True), "REJECT")
        self.assertEqual(self.decision(multi_scope_requested=True), "REJECT")
        self.assertEqual(self.decision(scope_count=2), "REJECT")

    def test_exact_canary_identity_and_trade_date_are_frozen(self) -> None:
        cases = {
            "principal_id": 2,
            "user_id": 2,
            "for_trade_date": "20260722",
            "expected_active_revision_id": 16,
            "expected_active_revision_no": 6,
            "target_revision_no": 7,
            "target_previous_revision_id": 16,
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                self.assertEqual(
                    self.decision(canary_scope=self.changed_scope(**{field: value})),
                    "REJECT",
                )
        self.assertEqual(self.decision(non_current_trade_date_requested=True), "REJECT")
        self.assertEqual(self.decision(closed_trade_date_requested=True), "REJECT")

    def test_package_keys_are_unchanged_and_only_version_moves_to_v2(self) -> None:
        self.assertEqual(self.decision(package_key_set_change_requested=True), "REJECT")
        self.assertEqual(
            self.decision(
                canary_scope=self.changed_scope(
                    target_package_items=[
                        {"package_key": "package_2", "package_version": "v2"}
                    ]
                )
            ),
            "REJECT",
        )
        self.assertEqual(
            self.decision(package_version_v1_to_v2_only_verified=False),
            "REJECT",
        )

    def test_postflights_catalog_and_quiescence_are_required(self) -> None:
        fields = (
            "migration_081_committed_and_postflight_verified",
            "migration_082_committed_and_postflight_verified",
            "migration_083_committed_and_postflight_verified",
            "v2_catalog_active_verified",
            "v1_catalog_grandfathered_verified",
            "strategy_write_zero_verified",
            "evaluator_job_absent_verified",
            "evaluator_pid_absent_verified",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        self.assertEqual(self.decision(strategy_write_flag="1"), "REJECT")
        self.assertEqual(self.decision(strategy_write_enable_requested=True), "REJECT")
        self.assertEqual(self.decision(evaluator_operation_requested=True), "REJECT")
        self.assertEqual(self.decision(migration_083_missing_or_uncommitted=True), "REJECT")

    def test_pending_v2_and_predecessor_drift_reject(self) -> None:
        self.assertEqual(self.decision(existing_pending_revision_detected=True), "REJECT")
        self.assertEqual(self.decision(existing_v2_selection_item_detected=True), "REJECT")
        self.assertEqual(self.decision(active_predecessor_drift_detected=True), "REJECT")
        self.assertEqual(
            self.decision(target_scope_pending_count_zero_verified=False), "REJECT"
        )
        self.assertEqual(
            self.decision(target_scope_unique_active_v1_verified=False), "REJECT"
        )

    def test_only_owner_user_isolated_authority_modes_accept(self) -> None:
        for mode in self.policy["allowed_selection_creation_authority_modes"]:
            with self.subTest(mode=mode):
                self.assertEqual(
                    self.decision(selection_creation_authority_mode=mode), "ACCEPT"
                )
        self.assertEqual(
            self.decision(selection_creation_authority_mode="web_put"), "REJECT"
        )
        self.assertEqual(
            self.decision(selection_creation_authority_user_isolation_verified=False),
            "REJECT",
        )
        self.assertEqual(
            self.decision(selection_creation_path_equivalence_verified=False),
            "REJECT",
        )

    def test_request_id_idempotence_and_previous_revision_cas_are_required(self) -> None:
        self.assertEqual(self.decision(request_id="not-a-uuid"), "REJECT")
        self.assertEqual(self.decision(request_id_idempotence_defined=False), "REJECT")
        self.assertEqual(
            self.decision(
                same_request_id_returns_same_revision_without_extra_rows_verified=False
            ),
            "REJECT",
        )
        self.assertEqual(
            self.decision(previous_revision_compare_and_swap_defined=False), "REJECT"
        )

    def test_one_transaction_one_attempt_zero_retry(self) -> None:
        self.assertEqual(self.decision(new_mutation_transaction_count=2), "REJECT")
        self.assertEqual(self.decision(new_mutation_attempts=0), "REJECT")
        self.assertEqual(self.decision(new_mutation_attempts=2), "REJECT")
        self.assertEqual(self.decision(new_mutation_retries=1), "REJECT")
        self.assertEqual(self.decision(second_mutation_attempt_requested=True), "REJECT")
        self.assertEqual(self.decision(rollback_requested=True), "REJECT")
        for field, expected in {
            **self.policy["required_singleton_counts"],
            **self.policy["required_operation_counts"],
        }.items():
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: expected + 1}), "REJECT")

    def test_only_two_exact_ordered_pre_dml_harness_failures_are_recoverable(
        self,
    ) -> None:
        failures = self.policy["required_historical_pre_dml_harness_failures"]
        self.assertEqual([failure["sqlstate"] for failure in failures], ["42704", "42601"])
        self.assertEqual(
            failures[1]["root_cause"],
            "psql_request_id_variable_inside_dollar_quoted_do_not_expanded",
        )
        for field in (
            "historical_harness_42704_evidence_sha256",
            "historical_harness_42601_evidence_sha256",
            "historical_harness_sequence_sha256",
        ):
            with self.subTest(evidence_hash=field):
                self.assertIn(field, self.policy["required_hash_fields"])
        for index, field, value in (
            (0, "guard_id", "different_guard"),
            (0, "sqlstate", "42501"),
            (1, "failure_class", "selection_function_failure"),
            (1, "error_token", "different_token"),
        ):
            changed = copy.deepcopy(failures)
            changed[index][field] = value
            with self.subTest(index=index, field=field):
                self.assertEqual(
                    self.decision(historical_pre_dml_harness_failures=changed),
                    "REJECT",
                )
        self.assertEqual(
            self.decision(
                historical_pre_dml_harness_failures=list(reversed(failures))
            ),
            "REJECT",
        )
        self.assertEqual(
            self.decision(historical_harness_failure_reason_or_order_differs=True),
            "REJECT",
        )
        self.assertEqual(
            self.decision(historical_failures_exact_pre_dml_harness_verified=False),
            "REJECT",
        )

    def test_two_harness_transactions_must_have_zero_mutation_and_commit(self) -> None:
        self.assertEqual(
            self.decision(historical_pre_dml_harness_transaction_count=1), "REJECT"
        )
        self.assertEqual(
            self.decision(historical_pre_dml_harness_transaction_count=3), "REJECT"
        )
        self.assertEqual(
            self.decision(historical_pre_dml_harness_attempts=3), "REJECT"
        )
        self.assertEqual(
            self.decision(third_pre_dml_harness_transaction_requested=True), "REJECT"
        )
        self.assertEqual(
            self.decision(third_pre_dml_error_kind_detected=True), "REJECT"
        )
        nonzero_counts = (
            "prior_official_selection_function_calls",
            "prior_selection_revision_dml_count",
            "prior_selection_item_dml_count",
            "prior_commit_count",
            "prior_explicit_rollback_count",
            "prior_mutation_attempts",
        )
        for field in nonzero_counts:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: 1}), "REJECT")
        for field in (
            "prior_official_selection_function_called",
            "prior_revision_item_dml_detected",
            "prior_commit_detected",
            "prior_request_id_persisted",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")
        self.assertEqual(
            self.decision(
                historical_harness_transactions_automatically_aborted_verified=False
            ),
            "REJECT",
        )
        self.assertEqual(
            self.decision(prior_request_id_absent_verified=False),
            "REJECT",
        )

    def test_every_prior_before_after_hash_must_match(self) -> None:
        for before_field, after_field in self.policy["required_equal_hash_pairs"]:
            with self.subTest(before=before_field, after=after_field):
                self.assertEqual(
                    self.decision(**{after_field: "b" * 64}),
                    "REJECT",
                )
        self.assertEqual(
            self.decision(prior_before_after_hash_drift_detected=True),
            "REJECT",
        )

    def test_guard_fix_is_audit_only_and_official_function_is_unchanged(self) -> None:
        self.assertEqual(
            self.policy["required_guard_repair_mode"],
            "pg_catalog_aclexplode_coalesced_function_acl_public_grantee_zero",
        )
        self.assertEqual(
            self.decision(guard_repair_mode="has_function_privilege_public_role_name"),
            "REJECT",
        )
        self.assertEqual(
            self.decision(guard_repair_audit_only_verified=False),
            "REJECT",
        )
        self.assertEqual(
            self.decision(guard_repair_semantically_correct_verified=False),
            "REJECT",
        )
        self.assertEqual(
            self.decision(official_selection_function_unchanged_verified=False),
            "REJECT",
        )
        self.assertEqual(
            self.decision(official_selection_function_modification_requested=True),
            "REJECT",
        )
        self.assertEqual(
            self.decision(guard_repair_outside_audit_requested=True),
            "REJECT",
        )

    def test_recovery_requires_fresh_preflight_and_new_request_id(self) -> None:
        self.assertEqual(self.decision(fresh_live_preflight_passed=False), "REJECT")
        self.assertEqual(
            self.decision(new_request_id_distinct_from_prior_verified=False),
            "REJECT",
        )
        self.assertEqual(self.decision(same_request_id_requested=True), "REJECT")
        self.assertEqual(self.decision(recovery_is_not_retry_verified=False), "REJECT")
        self.assertEqual(
            self.decision(
                phase_mode="create_first_post_083_pending_v2_revision_once"
            ),
            "REJECT",
        )
        for field in (
            "recovery_contract_version",
            "historical_pre_dml_harness_failures",
            "guard_repair_mode",
            "preflight_mode",
            "request_id_binding_mode",
            "mutation_statement_classes",
        ):
            request = copy.deepcopy(self.request)
            request.pop(field)
            with self.subTest(missing=field):
                self.assertEqual(evaluate(self.policy, request), "REJECT")

    def test_complex_checks_are_in_independent_read_only_preflight(self) -> None:
        self.assertEqual(
            self.policy["required_preflight_mode"],
            "independent_read_only_transaction_all_complex_validation",
        )
        for field in (
            "preflight_independent_transaction_verified",
            "preflight_transaction_read_only_verified",
            "all_complex_validation_completed_in_preflight_verified",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        self.assertEqual(
            self.decision(preflight_mode="mutation_transaction_validation"), "REJECT"
        )
        self.assertEqual(
            self.decision(mutation_complex_validation_query_count=1), "REJECT"
        )
        self.assertEqual(
            self.decision(mutation_complex_validation_requested=True), "REJECT"
        )

    def test_mutation_transaction_has_exact_static_statement_shape(self) -> None:
        self.assertEqual(
            self.policy["required_mutation_statement_classes"],
            [
                "BEGIN",
                "SET",
                "SELECT_ADVISORY_XACT_LOCK",
                "SELECT_OFFICIAL_SELECTION_FUNCTION",
                "SELECT_READ_ONLY_POSTFLIGHT",
                "COMMIT",
            ],
        )
        self.assertEqual(self.decision(mutation_do_block_count=1), "REJECT")
        self.assertEqual(
            self.decision(mutation_psql_variable_interpolation_count=1), "REJECT"
        )
        self.assertEqual(self.decision(mutation_dynamic_sql_count=1), "REJECT")
        self.assertEqual(
            self.decision(mutation_official_selection_function_select_count=2),
            "REJECT",
        )
        for field in (
            "mutation_do_block_requested",
            "mutation_psql_variable_interpolation_requested",
            "mutation_dynamic_sql_requested",
            "request_id_embedded_in_do_requested",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")
        changed = list(self.policy["required_mutation_statement_classes"])
        changed.insert(3, "DO")
        self.assertEqual(
            self.decision(mutation_statement_classes=changed),
            "REJECT",
        )

    def test_request_id_is_driver_bound_hash_audited_and_secret_redacted(self) -> None:
        self.assertEqual(
            self.policy["required_request_id_binding_mode"],
            "shell_or_driver_parameter_binding",
        )
        self.assertEqual(
            self.decision(request_id_binding_mode="psql_variable_interpolation"),
            "REJECT",
        )
        for field in (
            "request_id_bound_by_shell_or_driver_verified",
            "request_id_hash_auditable_verified",
            "request_id_token_secret_redaction_verified",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        self.assertEqual(self.decision(new_request_id_sha256="not-a-hash"), "REJECT")
        self.assertEqual(
            self.decision(request_id_literal_or_secret_logged=True), "REJECT"
        )

    def test_governance_session_cannot_use_new_policy(self) -> None:
        self.assertEqual(
            self.decision(policy_governance_session_execution_requested=True),
            "REJECT",
        )

    def test_only_revision_and_item_pending_writes_accept(self) -> None:
        self.assertEqual(
            self.decision(declared_write_tables=["n6_user_strategy_selection_revision"]),
            "REJECT",
        )
        self.assertEqual(self.decision(extra_table_write_requested=True), "REJECT")
        self.assertEqual(self.decision(direct_activation_requested=True), "REJECT")
        self.assertEqual(self.decision(non_pending_selection_status_requested=True), "REJECT")
        self.assertEqual(self.decision(non_pending_replay_status_requested=True), "REJECT")
        self.assertEqual(
            self.decision(migration_082_compensation_function_call_requested=True),
            "REJECT",
        )
        for field in (
            "projection_write_requested",
            "change_write_requested",
            "catalog_write_requested",
            "schema_write_requested",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_web_evaluator_and_virtual_executor_operations_reject(self) -> None:
        self.assertEqual(self.decision(web_put_requested=True), "REJECT")
        self.assertEqual(self.decision(web_put_attempts=1), "REJECT")
        self.assertEqual(self.decision(evaluator_execution_attempts=1), "REJECT")
        self.assertEqual(self.decision(virtual_executor_operation_requested=True), "REJECT")
        self.assertEqual(
            self.decision(virtual_executor_operation_attempts=1), "REJECT"
        )

    def test_other_users_projection_change_and_trading_proofs_are_required(self) -> None:
        for field in (
            "other_users_unchanged_verified",
            "projection_change_unchanged_verified",
            "zero_trading_side_effects_verified",
            "before_after_scope_proof_defined",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        for field in (
            "n1_n5_write_requested",
            "outbox_inbox_checkpoint_mutation_requested",
            "proposal_touched",
            "order_touched",
            "trade_touched",
            "position_touched",
            "cash_touched",
            "real_broker_connected",
            "long_term_worker_requested",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_every_required_field_and_hash_is_fail_closed(self) -> None:
        for field in self.policy["required_true_fields"]:
            with self.subTest(kind="true", field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        for field in self.policy["required_false_fields"]:
            with self.subTest(kind="false", field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")
        for field in self.policy["required_hash_fields"]:
            with self.subTest(kind="hash", field=field):
                self.assertEqual(self.decision(**{field: "bad"}), "REJECT")

    def test_all_control_documents_name_policy(self) -> None:
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
                self.assertIn(POLICY_ID, (ROOT / relative).read_text(encoding="utf-8"))

    def test_all_control_documents_bind_the_recovery_guard(self) -> None:
        for relative in (
            "AGENTS.md",
            "docs/EXECUTION_COMPILER.md",
            "docs/EXECUTION_KERNEL.md",
            "docs/EXECUTION_RUNTIME_GATE.md",
            "docs/EXECUTION_SANDBOX.md",
            "docs/EXECUTION_TEST_SUITE.md",
            "docs/EXECUTION_TRACE_SYSTEM.md",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(path=relative):
                self.assertIn("42601", text)
                self.assertIn("READ ONLY", text)
                self.assertIn("dynamic SQL", text)
                self.assertIn("mutation attempt", text)
                self.assertTrue("third" in text or "第三" in text)

    def test_existing_named_policies_remain_present(self) -> None:
        kernel = (ROOT / "docs" / "EXECUTION_KERNEL.md").read_text(encoding="utf-8")
        for policy_id in (
            "n6_strategy_center_post_081_v2_catalog_migration_window_v1",
            "n6_strategy_center_post_081_v2_web_bounded_rebind_v1",
            "n6_strategy_center_schema_migration_maintenance_window_v1",
            "n6_strategy_center_display_only_bounded_run_once_v1",
        ):
            with self.subTest(policy_id=policy_id):
                self.assertIn(f"<!-- policy:{policy_id}:begin -->", kernel)


if __name__ == "__main__":
    unittest.main()
