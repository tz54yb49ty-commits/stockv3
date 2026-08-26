from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "docs" / "EXECUTION_KERNEL.md"
LIFECYCLE_ID = "n6_strategy_center_30_day_isolation_decommission_v1"
WEB_POLICY_ID = "n6_strategy_center_decommission_web_runtime_v1"
SCHEMA_POLICY_ID = "n6_strategy_center_decommission_schema_archive_v1"


def load_json_block(begin: str, end: str) -> dict[str, Any]:
    text = KERNEL.read_text(encoding="utf-8")
    start = text.index(begin) + len(begin)
    stop = text.index(end, start)
    match = re.fullmatch(
        r"```json\s*(\{.*\})\s*```",
        text[start:stop].strip(),
        re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"{begin} must contain one valid JSON fence")
    return json.loads(match.group(1))


def load_policy(policy_id: str) -> dict[str, Any]:
    return load_json_block(
        f"<!-- policy:{policy_id}:begin -->",
        f"<!-- policy:{policy_id}:end -->",
    )


def load_lifecycle() -> dict[str, Any]:
    return load_json_block(
        f"<!-- policy-lifecycle:{LIFECYCLE_ID}:begin -->",
        f"<!-- policy-lifecycle:{LIFECYCLE_ID}:end -->",
    )


def exact_non_negative_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def lifecycle_decision(lifecycle: dict[str, Any], policy_id: str) -> str | None:
    if policy_id in lifecycle["retired_policy_ids"]:
        return lifecycle["retired_policy_decision"]
    return None


def canonical_web_request(policy: dict[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {
        field: policy[field]
        for field in (
            "policy_id",
            "layer_role",
            "scope_mode",
            "web_launch_agent_label",
            "evaluator_launch_agent_label",
            "virtual_executor_launch_agent_label",
            "web_strategy_write_flag",
            "web_strategy_write_flag_before",
            "web_strategy_write_flag_after",
            "web_strategy_write_flag_rollback",
            "required_target_release_delta",
            "web_teardown_timeout_seconds",
            "web_readiness_timeout_seconds",
            "web_stability_window_seconds",
        )
    }
    request["target_release_name"] = "20260727_120000__" + "a" * 40
    request["declared_runtime_operations"] = list(policy["allowed_runtime_operations"])
    request.update(policy["required_operation_counts"])
    request.update(
        {
            "web_rollback_bootout_attempts": 0,
            "web_rollback_bootstrap_attempts": 0,
            "primary_failed": False,
            "archive_requested": False,
            "web_stability_passed": True,
            "archive_root_new": True,
            "archive_root_read_only": True,
            "archive_manifest_hashes_complete": True,
        }
    )
    for field in policy["required_hash_fields"]:
        request[field] = "b" * (40 if field.endswith(("commit_sha", "tree_sha")) else 64)
    request.update({field: True for field in policy["required_true_fields"]})
    request.update({field: False for field in policy["required_false_fields"]})
    return request


def evaluate_web(
    lifecycle: dict[str, Any],
    policy: dict[str, Any],
    request: dict[str, Any],
) -> str:
    retired = lifecycle_decision(lifecycle, str(request.get("policy_id")))
    if retired is not None:
        return retired
    reject = policy["default_runtime_execution_decision"]
    exact_fields = (
        "policy_id",
        "layer_role",
        "scope_mode",
        "web_launch_agent_label",
        "evaluator_launch_agent_label",
        "virtual_executor_launch_agent_label",
        "web_strategy_write_flag",
        "web_strategy_write_flag_before",
        "web_strategy_write_flag_after",
        "web_strategy_write_flag_rollback",
        "required_target_release_delta",
        "web_teardown_timeout_seconds",
        "web_readiness_timeout_seconds",
        "web_stability_window_seconds",
    )
    if any(request.get(field) != policy[field] for field in exact_fields):
        return reject
    if re.fullmatch(
        policy["target_release_name_pattern"],
        str(request.get("target_release_name", "")),
    ) is None:
        return reject
    if request.get("declared_runtime_operations") != policy["allowed_runtime_operations"]:
        return reject
    for field, expected in policy["required_operation_counts"].items():
        if not exact_non_negative_int(request.get(field)) or request[field] != expected:
            return reject
    for field, maximum in policy["maximum_conditional_rollback_counts"].items():
        if not exact_non_negative_int(request.get(field)) or request[field] > maximum:
            return reject
    rollback_counts = (
        request.get("web_rollback_bootout_attempts"),
        request.get("web_rollback_bootstrap_attempts"),
    )
    if rollback_counts not in ((0, 0), (1, 1)):
        return reject
    if rollback_counts == (1, 1) and request.get("primary_failed") is not True:
        return reject
    for field in policy["required_hash_fields"]:
        size = 40 if field.endswith(("commit_sha", "tree_sha")) else 64
        if re.fullmatch(rf"[0-9a-f]{{{size}}}", str(request.get(field, ""))) is None:
            return reject
    if any(request.get(field) is not True for field in policy["required_true_fields"]):
        return reject
    if any(request.get(field) is not False for field in policy["required_false_fields"]):
        return reject
    if request.get("archive_requested") is True:
        archive_checks = (
            "web_stability_passed",
            "archive_root_new",
            "archive_root_read_only",
            "archive_manifest_hashes_complete",
        )
        if any(request.get(field) is not True for field in archive_checks):
            return reject
    return policy["accept_decision"]


def canonical_schema_request(policy: dict[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {
        field: copy.deepcopy(policy[field])
        for field in (
            "policy_id",
            "layer_role",
            "scope_mode",
            "archive_schema",
            "retention_days",
            "core_tables",
            "owned_dependent_object_types",
            "archive_schema_usage_revoked_from",
            "protected_objects",
            "allowed_ddl_operations",
            "required_evidence_per_table",
        )
    }
    request.update(policy["required_operation_counts"])
    request.update({field: True for field in policy["required_true_fields"]})
    request.update({field: False for field in policy["required_false_fields"]})
    request["per_table_evidence"] = {
        table: list(policy["required_evidence_per_table"])
        for table in policy["core_tables"]
    }
    request["rollback_sql_sha256"] = "c" * 64
    return request


def evaluate_schema(
    lifecycle: dict[str, Any],
    policy: dict[str, Any],
    request: dict[str, Any],
) -> str:
    retired = lifecycle_decision(lifecycle, str(request.get("policy_id")))
    if retired is not None:
        return retired
    reject = policy["default_runtime_execution_decision"]
    exact_fields = (
        "policy_id",
        "layer_role",
        "scope_mode",
        "archive_schema",
        "retention_days",
        "core_tables",
        "owned_dependent_object_types",
        "archive_schema_usage_revoked_from",
        "protected_objects",
        "allowed_ddl_operations",
        "required_evidence_per_table",
    )
    if any(request.get(field) != policy[field] for field in exact_fields):
        return reject
    for field, expected in policy["required_operation_counts"].items():
        if not exact_non_negative_int(request.get(field)) or request[field] != expected:
            return reject
    if any(request.get(field) is not True for field in policy["required_true_fields"]):
        return reject
    if any(request.get(field) is not False for field in policy["required_false_fields"]):
        return reject
    if re.fullmatch(r"[0-9a-f]{64}", str(request.get("rollback_sql_sha256", ""))) is None:
        return reject
    evidence = request.get("per_table_evidence")
    if not isinstance(evidence, dict) or set(evidence) != set(policy["core_tables"]):
        return reject
    if any(
        evidence[table] != policy["required_evidence_per_table"]
        for table in policy["core_tables"]
    ):
        return reject
    return policy["accept_decision"]


class StrategyCenterDecommissionPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lifecycle = load_lifecycle()
        cls.web_policy = load_policy(WEB_POLICY_ID)
        cls.schema_policy = load_policy(SCHEMA_POLICY_ID)
        cls.web_request = canonical_web_request(cls.web_policy)
        cls.schema_request = canonical_schema_request(cls.schema_policy)

    def web_decision(self, **changes: Any) -> str:
        request = copy.deepcopy(self.web_request)
        request.update(changes)
        return evaluate_web(self.lifecycle, self.web_policy, request)

    def schema_decision(self, **changes: Any) -> str:
        request = copy.deepcopy(self.schema_request)
        request.update(changes)
        return evaluate_schema(self.lifecycle, self.schema_policy, request)

    def test_lifecycle_retires_every_historical_strategy_center_policy(self) -> None:
        self.assertEqual(len(self.lifecycle["retired_policy_ids"]), 13)
        self.assertEqual(self.lifecycle["retired_status"], "RETIRED")
        for policy_id in self.lifecycle["retired_policy_ids"]:
            with self.subTest(policy_id=policy_id):
                self.assertEqual(lifecycle_decision(self.lifecycle, policy_id), "REJECT")
                self.assertIn(
                    f"<!-- policy:{policy_id}:begin -->",
                    KERNEL.read_text(encoding="utf-8"),
                )

    def test_only_two_decommission_policies_are_active(self) -> None:
        self.assertEqual(
            self.lifecycle["active_decommission_policy_ids"],
            [WEB_POLICY_ID, SCHEMA_POLICY_ID],
        )
        self.assertTrue(
            set(self.lifecycle["active_decommission_policy_ids"]).isdisjoint(
                self.lifecycle["retired_policy_ids"]
            )
        )

    def test_web_exact_contract_accepts(self) -> None:
        self.assertEqual(self.web_decision(), "ACCEPT")
        self.assertEqual(self.web_policy["runtime_gate_decision"], "ACCEPT")

    def test_web_default_unknown_and_retired_policy_reject(self) -> None:
        self.assertEqual(self.web_policy["default_runtime_execution_decision"], "REJECT")
        self.assertEqual(self.web_decision(policy_id="general_runtime_execute"), "REJECT")
        retired = self.lifecycle["retired_policy_ids"][0]
        self.assertEqual(self.web_decision(policy_id=retired), "REJECT")

    def test_web_write_evaluator_and_single_attempt_guards_reject(self) -> None:
        cases = {
            "web_strategy_write_flag_before": "1",
            "web_strategy_write_flag_after": "1",
            "evaluator_restore_attempts": 1,
            "virtual_executor_operation_attempts": 1,
            "database_connection_attempts": 1,
            "other_service_operation_attempts": 1,
            "web_primary_bootout_attempts": 2,
            "canary_heartbeat_operation_requested": True,
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                self.assertEqual(self.web_decision(**{field: value}), "REJECT")

    def test_web_rollback_and_archive_are_fail_closed(self) -> None:
        self.assertEqual(
            self.web_decision(
                web_rollback_bootout_attempts=1,
                web_rollback_bootstrap_attempts=1,
                primary_failed=True,
            ),
            "ACCEPT",
        )
        self.assertEqual(
            self.web_decision(
                web_rollback_bootout_attempts=1,
                web_rollback_bootstrap_attempts=1,
            ),
            "REJECT",
        )
        self.assertEqual(
            self.web_decision(archive_requested=True, archive_root_read_only=False),
            "REJECT",
        )

    def test_schema_exact_contract_accepts(self) -> None:
        self.assertEqual(self.schema_decision(), "ACCEPT")
        self.assertEqual(len(self.schema_policy["core_tables"]), 6)
        self.assertEqual(self.schema_policy["retention_days"], 30)

    def test_schema_drop_role_acl_executor_and_retry_guards_reject(self) -> None:
        cases = {
            "data_drop_requested": True,
            "core_table_drop_requested": True,
            "truncate_requested": True,
            "row_update_delete_insert_requested": True,
            "n6_strategy_worker_role_change_requested": True,
            "reviewed_view_079_acl_change_requested": True,
            "base_n6_strategy_table_touched": True,
            "n6_ai_strategy_table_family_touched": True,
            "virtual_executor_operation_requested": True,
            "second_transaction_or_retry_requested": True,
            "automatic_physical_deletion_requested": True,
            "canary_heartbeat_operation_requested": True,
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                self.assertEqual(self.schema_decision(**{field: value}), "REJECT")

    def test_schema_exact_scope_evidence_and_rollback_are_required(self) -> None:
        self.assertEqual(
            self.schema_decision(core_tables=self.schema_policy["core_tables"][:-1]),
            "REJECT",
        )
        self.assertEqual(self.schema_decision(per_table_evidence={}), "REJECT")
        self.assertEqual(self.schema_decision(rollback_sql_sha256="bad"), "REJECT")
        self.assertEqual(
            self.schema_decision(
                archive_schema_usage_revoked_from=["n6_strategy_worker", "PUBLIC"]
            ),
            "REJECT",
        )

    def test_governance_session_and_physical_deletion_remain_rejected(self) -> None:
        self.assertTrue(self.web_policy["governance_session_cannot_execute"])
        self.assertTrue(self.schema_policy["governance_session_cannot_execute"])
        self.assertFalse(self.lifecycle["governance_session_runtime_execution_authorized"])
        self.assertFalse(self.lifecycle["physical_deletion_automatically_scheduled"])
        self.assertTrue(
            self.lifecycle[
                "physical_deletion_requires_new_independent_explicit_authorization_after_retention"
            ]
        )


if __name__ == "__main__":
    unittest.main()
