from __future__ import annotations

import copy
import hashlib
import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "n6_strategy_center_display_only_scheduled_evaluator_v1"
F464_POLICY_ID = "n6_strategy_center_display_only_scheduled_evaluator_f464_v1"
POLICY_BEGIN = f"<!-- policy:{POLICY_ID}:begin -->"
POLICY_END = f"<!-- policy:{POLICY_ID}:end -->"
BOUNDED_POLICY_ID = "n6_strategy_center_display_only_bounded_run_once_v1"
WEB_POLICY_ID = "n6_user_web_immutable_release_bounded_rebind_v1"


def load_policy(policy_id: str = POLICY_ID) -> dict[str, Any]:
    text = (ROOT / "docs" / "EXECUTION_KERNEL.md").read_text(encoding="utf-8")
    policy_begin = f"<!-- policy:{policy_id}:begin -->"
    policy_end = f"<!-- policy:{policy_id}:end -->"
    start = text.index(policy_begin) + len(policy_begin)
    end = text.index(policy_end, start)
    fenced = text[start:end].strip()
    match = re.fullmatch(r"```json\s*(\{.*\})\s*```", fenced, re.DOTALL)
    if match is None:
        raise AssertionError("scheduled policy must contain exactly one valid JSON fence")
    return json.loads(match.group(1))


def argv_sha256(argv: list[str]) -> str:
    payload = json.dumps(argv, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def expected_program_arguments(
    policy: dict[str, Any],
    *,
    release_path: str,
    runtime_env_path: str,
) -> list[str]:
    state_paths = policy["required_runtime_state_paths"]
    database = policy["required_database_service_arguments"]
    return [
        *policy["required_env_launcher"],
        f"PGPASSFILE={database['PGPASSFILE']}",
        f"PGSERVICE={database['PGSERVICE']}",
        f"PGSERVICEFILE={database['PGSERVICEFILE']}",
        "PYTHONDONTWRITEBYTECODE=1",
        "PYTHONNOUSERSITE=1",
        "PYTHONPATH=" + ":".join(
            (
                f"{release_path}/src",
                f"{release_path}/scripts",
                release_path,
            )
        ),
        f"{runtime_env_path}/{policy['runtime_python_relative_path']}",
        f"{release_path}/scripts/{policy['runner_basename']}",
        "--state-path",
        state_paths["state_path"],
        "--singleton-lock-path",
        state_paths["singleton_lock_path"],
        "--json-report-path",
        state_paths["json_report_path"],
        "--history-path",
        state_paths["history_path"],
        "--release-id",
        Path(release_path).name,
        "--signal-source-user-id",
        str(policy["required_signal_source_user_id"]),
        "--max-runtime-seconds",
        str(policy["required_max_runtime_seconds"]),
        *policy["required_runner_flags"],
    ]


def canonical_request(policy: dict[str, Any]) -> dict[str, Any]:
    current_trade_date = "20260723"
    release_commit = policy["required_integrated_implementation_commit"]
    release_path = f"{policy['release_root']}/20260722_170000__{release_commit}"
    runtime_env_path = (
        f"{policy['runtime_env_root']}/n6-strategy-center-auto-v1-20260722"
    )
    runner_path = f"{release_path}/scripts/{policy['runner_basename']}"
    planner_path = f"{release_path}/scripts/{policy['planner_basename']}"
    python_executable = f"{runtime_env_path}/{policy['runtime_python_relative_path']}"
    program_arguments = expected_program_arguments(
        policy,
        release_path=release_path,
        runtime_env_path=runtime_env_path,
    )
    request: dict[str, Any] = {
        "policy_id": policy["policy_id"],
        "layer_role": policy["layer_role"],
        "scope_mode": policy["scope_mode"],
        "scheduler_mode": policy["scheduler_mode"],
        "launch_agent_label": policy["launch_agent_label"],
        "launch_agent_plist_path": policy["launch_agent_plist_path"],
        "runner_basename": policy["runner_basename"],
        "planner_basename": policy["planner_basename"],
        "database_role": policy["database_role"],
        "pgservice_value": policy["pgservice_value"],
        "timezone": policy["timezone"],
        "start_interval_seconds": policy["start_interval_seconds"],
        "max_scopes_per_tick": policy["max_scopes_per_tick"],
        "transaction_scope": policy["transaction_scope"],
        "pending_scope_order": list(policy["pending_scope_order"]),
        "active_scope_order": list(policy["active_scope_order"]),
        "active_scope_cursor_mode": policy["active_scope_cursor_mode"],
        "failure_queue_behavior": policy["failure_queue_behavior"],
        "evaluation_budget_seconds": policy["evaluation_budget_seconds"],
        "evidence_grace_seconds": policy["evidence_grace_seconds"],
        "canary_policy_id": policy["required_canary_policy_id"],
        "canary_trade_date": current_trade_date,
        "trade_date": current_trade_date,
        "current_trade_date": current_trade_date,
        policy["onsite_current_date_field"]: current_trade_date,
        policy["trade_calendar_date_field"]: current_trade_date,
        policy["trade_calendar_open_field"]: True,
        "release_path": release_path,
        "runtime_env_path": runtime_env_path,
        "runner_path": runner_path,
        "planner_path": planner_path,
        "source_authority_commits": list(policy["required_source_authority_commits"]),
        "capability_ancestor_commit": policy[
            "required_capability_ancestor_commit"
        ],
        "dto_fix_ancestor_commit": policy["required_dto_fix_ancestor_commit"],
        "membership_asof_ancestor_commit": policy[
            "required_membership_asof_ancestor_commit"
        ],
        "stable_replay_ancestor_commit": policy[
            "required_stable_replay_ancestor_commit"
        ],
        "single_scope_parent_commit": policy[
            "required_single_scope_parent_commit"
        ],
        "integrated_implementation_commit": policy[
            "required_integrated_implementation_commit"
        ],
        "integrated_implementation_tree": policy[
            "required_integrated_implementation_tree"
        ],
        "release_git_blobs": copy.deepcopy(policy["required_release_git_blobs"]),
        "python_executable": python_executable,
        "program_arguments": program_arguments,
        "plist_values": copy.deepcopy(policy["required_plist_values"]),
        "database_service_arguments": copy.deepcopy(
            policy["required_database_service_arguments"]
        ),
        "env_launcher": list(policy["required_env_launcher"]),
        "runtime_state_paths": copy.deepcopy(policy["required_runtime_state_paths"]),
        "signal_source_user_id": policy["required_signal_source_user_id"],
        "max_runtime_seconds": policy["required_max_runtime_seconds"],
        "runner_flags": list(policy["required_runner_flags"]),
        "declared_write_tables": list(policy["allowed_write_tables"]),
        "observation_dml_contract": copy.deepcopy(
            policy["observation_dml_contract"]
        ),
        "rollback_contract": copy.deepcopy(policy["rollback_contract"]),
        "declared_mutation_resources": list(policy["allowed_mutation_resources"]),
        "declared_runtime_operations": list(policy["allowed_runtime_operations"]),
        "closed_day_behavior": policy["closed_day_behavior"],
        "primary_install_attempts": policy["primary_install_attempts"],
        "primary_bootstrap_attempts": policy["primary_bootstrap_attempts"],
        "primary_retries": policy["maximum_primary_retries"],
        "rollback_attempts": 0,
        "rollback_bootout_attempts": 0,
        "rollback_remove_plist_attempts": 0,
        "readiness_failed": False,
        "rollback_launch_agent_label": policy["launch_agent_label"],
        "rollback_plist_path": policy["launch_agent_plist_path"],
        "scheduled_tick_requires_fresh_gate": policy["scheduled_tick_requires_fresh_gate"],
    }
    request.update(policy["required_singleton_counts"])
    request.update({field: True for field in policy["required_true_fields"]})
    request.update({field: False for field in policy["required_false_fields"]})

    hash_values = {
        field: format((index % 15) + 1, "x") * (40 if "_sha" in field and "sha256" not in field else 64)
        for index, field in enumerate(policy["required_hash_fields"])
    }
    hash_values["release_commit_sha"] = release_commit
    hash_values["release_tree_sha"] = policy[
        "required_integrated_implementation_tree"
    ]
    hash_values["runner_argv_sha256"] = argv_sha256(program_arguments)
    request.update(hash_values)
    request.update(
        {
            "canary_release_commit_sha": release_commit,
            "canary_release_tree_sha": policy[
                "required_integrated_implementation_tree"
            ],
            "canary_release_archive_sha256": hash_values[
                "release_archive_sha256"
            ],
            "canary_release_manifest_sha256": hash_values[
                "release_manifest_sha256"
            ],
            "canary_release_filesystem_sha256": hash_values[
                "release_filesystem_sha256"
            ],
        }
    )
    return request


def strict_non_negative_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def evaluate(policy: dict[str, Any], request: dict[str, Any]) -> str:
    reject = policy["default_runtime_execution_decision"]
    fixed_fields = (
        "policy_id",
        "layer_role",
        "scope_mode",
        "scheduler_mode",
        "launch_agent_label",
        "launch_agent_plist_path",
        "runner_basename",
        "planner_basename",
        "database_role",
        "pgservice_value",
        "timezone",
        "start_interval_seconds",
        "max_scopes_per_tick",
        "transaction_scope",
        "pending_scope_order",
        "active_scope_order",
        "active_scope_cursor_mode",
        "failure_queue_behavior",
        "evaluation_budget_seconds",
        "evidence_grace_seconds",
    )
    if any(request.get(field) != policy[field] for field in fixed_fields):
        return reject
    if not strict_non_negative_int(request.get("max_scopes_per_tick")):
        return reject
    if request.get("canary_policy_id") != policy["required_canary_policy_id"]:
        return reject

    release_path_value = request.get("release_path")
    if not isinstance(release_path_value, str) or not release_path_value.startswith("/"):
        return reject
    release_path = Path(release_path_value)
    if str(release_path.parent) != policy["release_root"]:
        return reject
    if re.fullmatch(policy["release_name_pattern"], release_path.name) is None:
        return reject
    release_commit = release_path.name.rsplit("__", 1)[-1]
    if request.get("release_commit_sha") != release_commit:
        return reject
    if (
        request.get("integrated_implementation_commit")
        != policy["required_integrated_implementation_commit"]
        or request.get("integrated_implementation_tree")
        != policy["required_integrated_implementation_tree"]
    ):
        return reject
    if release_commit != policy["required_integrated_implementation_commit"]:
        return reject
    if (
        request.get("release_tree_sha")
        != policy["required_integrated_implementation_tree"]
    ):
        return reject
    if (
        request.get("canary_release_commit_sha")
        != policy["required_integrated_implementation_commit"]
        or request.get("canary_release_tree_sha")
        != policy["required_integrated_implementation_tree"]
        or request.get("canary_release_archive_sha256")
        != request.get("release_archive_sha256")
        or request.get("canary_release_manifest_sha256")
        != request.get("release_manifest_sha256")
        or request.get("canary_release_filesystem_sha256")
        != request.get("release_filesystem_sha256")
    ):
        return reject

    runtime_env_value = request.get("runtime_env_path")
    if not isinstance(runtime_env_value, str) or not runtime_env_value.startswith("/"):
        return reject
    runtime_env_path = Path(runtime_env_value)
    if str(runtime_env_path.parent) != policy["runtime_env_root"]:
        return reject

    for field, pattern in policy["required_hash_fields"].items():
        value = request.get(field)
        if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
            return reject
    if request.get("source_authority_commits") != policy["required_source_authority_commits"]:
        return reject
    if request.get("capability_ancestor_commit") != policy[
        "required_capability_ancestor_commit"
    ]:
        return reject
    if request.get("dto_fix_ancestor_commit") != policy[
        "required_dto_fix_ancestor_commit"
    ]:
        return reject
    if request.get("membership_asof_ancestor_commit") != policy[
        "required_membership_asof_ancestor_commit"
    ]:
        return reject
    if request.get("stable_replay_ancestor_commit") != policy[
        "required_stable_replay_ancestor_commit"
    ]:
        return reject
    if request.get("single_scope_parent_commit") != policy[
        "required_single_scope_parent_commit"
    ]:
        return reject
    if request.get("release_git_blobs") != policy["required_release_git_blobs"]:
        return reject

    expected_runner = f"{release_path_value}/scripts/{policy['runner_basename']}"
    if request.get("runner_path") != expected_runner:
        return reject
    expected_planner = f"{release_path_value}/scripts/{policy['planner_basename']}"
    if request.get("planner_path") != expected_planner:
        return reject
    python_executable = request.get("python_executable")
    expected_python = f"{runtime_env_value}/{policy['runtime_python_relative_path']}"
    if python_executable != expected_python:
        return reject
    expected_argv = expected_program_arguments(
        policy,
        release_path=release_path_value,
        runtime_env_path=runtime_env_value,
    )
    if request.get("program_arguments") != expected_argv:
        return reject
    if request.get("runner_argv_sha256") != argv_sha256(expected_argv):
        return reject
    joined_argv = " ".join(expected_argv).lower()
    if any(value.lower() in joined_argv for value in policy["forbidden_runner_arguments"]):
        return reject

    trade_date = request.get(policy["trade_date_field"])
    current_trade_date = request.get(policy["current_trade_date_field"])
    onsite_current_date = request.get(policy["onsite_current_date_field"])
    trade_calendar_date = request.get(policy["trade_calendar_date_field"])
    canary_trade_date = request.get("canary_trade_date")
    if any(
        not isinstance(value, str) or re.fullmatch(r"\d{8}", value) is None
        for value in (
            trade_date,
            current_trade_date,
            onsite_current_date,
            trade_calendar_date,
            canary_trade_date,
        )
    ):
        return reject
    if (
        trade_date != current_trade_date
        or current_trade_date != onsite_current_date
        or trade_calendar_date != current_trade_date
        or canary_trade_date != current_trade_date
        or request.get(policy["trade_calendar_open_field"]) is not True
    ):
        return reject

    for field, expected in policy["required_singleton_counts"].items():
        value = request.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value != expected:
            return reject
    if any(request.get(field) is not True for field in policy["required_true_fields"]):
        return reject
    if any(request.get(field) is not False for field in policy["required_false_fields"]):
        return reject
    if request.get("plist_values") != policy["required_plist_values"]:
        return reject
    if request.get("database_service_arguments") != policy["required_database_service_arguments"]:
        return reject
    if request.get("env_launcher") != policy["required_env_launcher"]:
        return reject
    if request.get("runtime_state_paths") != policy["required_runtime_state_paths"]:
        return reject
    if request.get("signal_source_user_id") != policy["required_signal_source_user_id"]:
        return reject
    if request.get("max_runtime_seconds") != policy["required_max_runtime_seconds"]:
        return reject
    if request.get("runner_flags") != policy["required_runner_flags"]:
        return reject
    if request.get("declared_write_tables") != policy["allowed_write_tables"]:
        return reject
    if request.get("observation_dml_contract") != policy["observation_dml_contract"]:
        return reject
    if request.get("rollback_contract") != policy["rollback_contract"]:
        return reject
    if request.get("declared_mutation_resources") != policy["allowed_mutation_resources"]:
        return reject
    if request.get("declared_runtime_operations") != policy["allowed_runtime_operations"]:
        return reject
    if request.get("closed_day_behavior") != policy["closed_day_behavior"]:
        return reject
    if request.get("scheduled_tick_requires_fresh_gate") is not policy["scheduled_tick_requires_fresh_gate"]:
        return reject

    if request.get("primary_install_attempts") != policy["primary_install_attempts"]:
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
        if policy["rollback_requires_readiness_failure"] and request.get("readiness_failed") is not True:
            return reject
        if request.get("rollback_launch_agent_label") != policy["launch_agent_label"]:
            return reject
        if request.get("rollback_plist_path") != policy["launch_agent_plist_path"]:
            return reject
        if request.get("rollback_bootout_attempts") != 1:
            return reject
        if request.get("rollback_remove_plist_attempts") != 1:
            return reject
    elif request.get("rollback_bootout_attempts") != 0 or request.get("rollback_remove_plist_attempts") != 0:
        return reject
    return policy["accept_decision"]


class N6StrategyCenterScheduledEvaluatorPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()
        cls.request = canonical_request(cls.policy)

    def decision(self, **changes: Any) -> str:
        request = copy.deepcopy(self.request)
        request.update(changes)
        return evaluate(self.policy, request)

    def decision_for_integrated_release(self, *, commit: str, tree: str) -> str:
        request = copy.deepcopy(self.request)
        release_path = (
            f"{self.policy['release_root']}/20260722_170000__{commit}"
        )
        runtime_env_path = request["runtime_env_path"]
        program_arguments = expected_program_arguments(
            self.policy,
            release_path=release_path,
            runtime_env_path=runtime_env_path,
        )
        request.update(
            {
                "release_path": release_path,
                "runner_path": (
                    f"{release_path}/scripts/{self.policy['runner_basename']}"
                ),
                "planner_path": (
                    f"{release_path}/scripts/{self.policy['planner_basename']}"
                ),
                "program_arguments": program_arguments,
                "runner_argv_sha256": argv_sha256(program_arguments),
                "release_commit_sha": commit,
                "release_tree_sha": tree,
                "integrated_implementation_commit": commit,
                "integrated_implementation_tree": tree,
            }
        )
        return evaluate(self.policy, request)

    def test_canonical_scheduled_evaluator_contract_accepts(self) -> None:
        self.assertEqual(self.decision(), "ACCEPT")
        self.assertEqual(self.policy["runtime_gate_decision"], "ACCEPT")
        self.assertEqual(self.policy["default_runtime_execution_decision"], "REJECT")

    def test_658_release_accepts_and_2d89_release_rejects(self) -> None:
        self.assertEqual(
            self.policy["required_integrated_implementation_commit"],
            "658ebb3995a7c539ac211258c378af6499635df4",
        )
        self.assertEqual(
            self.policy["required_integrated_implementation_tree"],
            "016f154e6716ce0c4f2c7dcee74808e9f95c6dc9",
        )
        self.assertEqual(
            self.policy["required_stable_replay_ancestor_commit"],
            "335cdd8eaf0aa17ba85e611f6c716af60368ffd8",
        )
        self.assertEqual(
            self.policy["required_single_scope_parent_commit"],
            "2d89c45b2afeb0960d514553d5cc10210452f91a",
        )
        self.assertEqual(self.decision(), "ACCEPT")
        self.assertEqual(
            self.decision_for_integrated_release(
                commit="2d89c45b2afeb0960d514553d5cc10210452f91a",
                tree="627bfdc2ce614866a741b152d70b1c24e0185a40",
            ),
            "REJECT",
        )

    def test_exact_policy_layer_label_runner_and_mode_are_required(self) -> None:
        cases = {
            "policy_id": "general_n6_scheduler",
            "layer_role": "runtime_control",
            "scope_mode": "all_users",
            "scheduler_mode": "historical_trade_date",
            "transaction_scope": "all_users",
            "pending_scope_order": ["principal_id", "user_id"],
            "active_scope_order": ["principal_id", "user_id"],
            "active_scope_cursor_mode": "restart_each_tick",
            "failure_queue_behavior": "advance_failed_scope",
            "launch_agent_label": "com.ashare-v3.n6.other",
            "launch_agent_plist_path": "/tmp/other.plist",
            "runner_basename": "run_n6_strategy_center_scheduled_once.py",
            "planner_basename": "plan_other_launchd.py",
            "database_role": "n6_btrack_web",
            "pgservice_value": "n6_btrack_web",
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: value}), "REJECT")

    def test_current_request_authorization_and_bounded_canary_are_mandatory(self) -> None:
        for field in (
            "explicit_user_authorization_current_request",
            "automatic_evaluator_authorized_current_request",
            "bounded_canary_dry_run_passed",
            "bounded_canary_primary_passed",
            "bounded_canary_same_input_replay_passed",
            "bounded_canary_same_scope_replay_passed",
            "bounded_canary_projection_acceptance_passed",
            "bounded_canary_sse_acceptance_passed",
            "bounded_canary_result_frozen",
            "bounded_canary_trade_date_matches_current_verified",
            "bounded_canary_current_open_trade_date_verified",
            "bounded_canary_exact_release_verified",
            "bounded_canary_fresh_evidence_verified",
            "onsite_asia_shanghai_current_date_verified",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        self.assertNotIn("required_canary_trade_date", self.policy)
        self.assertEqual(
            self.policy["canary_trade_date_contract"],
            "must_equal_current_trade_date",
        )
        self.assertEqual(
            self.policy["canary_freshness_contract"],
            "fresh_current_trade_date_exact_release_only",
        )
        self.assertEqual(
            self.policy["canary_release_contract"],
            "must_match_exact_required_release",
        )
        self.assertEqual(
            self.policy["historical_canary_authority"],
            "evidence_only_no_activation",
        )
        self.assertEqual(self.policy["historical_canary_trade_dates"], ["20260722"])
        self.assertEqual(
            self.policy["trade_calendar_open_field"],
            "common_trade_calendar_is_open",
        )
        self.assertEqual(
            self.policy["onsite_current_date_field"],
            "onsite_asia_shanghai_date",
        )
        self.assertEqual(
            self.policy["trade_calendar_date_field"],
            "common_trade_calendar_trade_date",
        )
        self.assertEqual(self.request["canary_trade_date"], "20260723")
        self.assertEqual(self.request["current_trade_date"], "20260723")
        self.assertEqual(self.decision(canary_policy_id=WEB_POLICY_ID), "REJECT")
        self.assertEqual(self.decision(canary_trade_date="20260722"), "REJECT")
        self.assertEqual(self.decision(canary_trade_date="20260724"), "REJECT")
        self.assertEqual(
            self.decision(canary_release_commit_sha="a" * 40),
            "REJECT",
        )
        self.assertEqual(
            self.decision(canary_release_tree_sha="b" * 40),
            "REJECT",
        )
        self.assertEqual(
            self.decision(canary_release_archive_sha256="c" * 64),
            "REJECT",
        )
        self.assertEqual(
            self.decision(canary_release_manifest_sha256="d" * 64),
            "REJECT",
        )
        self.assertEqual(
            self.decision(canary_release_filesystem_sha256="e" * 64),
            "REJECT",
        )
        self.assertEqual(
            self.decision(historical_canary_activation_requested=True),
            "REJECT",
        )
        self.assertEqual(
            self.decision(bounded_canary_fresh_evidence_verified=False),
            "REJECT",
        )
        self.assertEqual(self.decision(bounded_canary_missing_or_failed=True), "REJECT")

    def test_release_path_commit_hashes_and_runner_blob_are_exact(self) -> None:
        self.assertEqual(self.decision(release_path="relative/release"), "REJECT")
        self.assertEqual(self.decision(release_path="/tmp/20260722_170000__" + "a" * 40), "REJECT")
        self.assertEqual(self.decision(release_commit_sha="b" * 40), "REJECT")
        for field in self.policy["required_hash_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: "not-a-hash"}), "REJECT")
        self.assertEqual(self.decision(release_drift_detected=True), "REJECT")
        self.assertEqual(
            self.decision(commit_tree_archive_manifest_filesystem_drift_detected=True),
            "REJECT",
        )
        self.assertEqual(self.decision(runner_blob_or_argv_drift_detected=True), "REJECT")
        self.assertEqual(
            self.decision(source_authority_commits=["a" * 40]),
            "REJECT",
        )
        blobs = copy.deepcopy(self.policy["required_release_git_blobs"])
        blobs["scripts/run_n6_strategy_center_auto_once.py"] = "f" * 40
        self.assertEqual(self.decision(release_git_blobs=blobs), "REJECT")
        old_runner_blobs = copy.deepcopy(self.policy["required_release_git_blobs"])
        old_runner_blobs[
            "scripts/run_n6_strategy_center_auto_once.py"
        ] = "c943c9ec2fc23800a91cf8796e4bf2229d1bd6d7"
        self.assertEqual(
            self.decision(release_git_blobs=old_runner_blobs),
            "REJECT",
        )
        self.assertEqual(
            self.decision(integrated_implementation_commit="a" * 40),
            "REJECT",
        )
        self.assertEqual(
            self.decision(integrated_implementation_tree="b" * 40),
            "REJECT",
        )
        self.assertEqual(
            self.decision(capability_ancestor_commit="a" * 40),
            "REJECT",
        )
        self.assertEqual(
            self.decision(dto_fix_ancestor_commit="b" * 40),
            "REJECT",
        )
        self.assertEqual(
            self.decision(membership_asof_ancestor_commit="c" * 40),
            "REJECT",
        )
        self.assertEqual(
            self.decision(stable_replay_ancestor_commit="d" * 40),
            "REJECT",
        )
        self.assertEqual(
            self.decision(single_scope_parent_commit="e" * 40),
            "REJECT",
        )
        self.assertEqual(
            self.decision(source_authority_or_git_blob_drift_detected=True),
            "REJECT",
        )
        self.assertEqual(
            self.decision(integrated_implementation_commit_tree_drift_detected=True),
            "REJECT",
        )
        self.assertEqual(
            self.decision(capability_ancestor_missing_or_drifted=True),
            "REJECT",
        )
        self.assertEqual(
            self.decision(dto_fix_ancestor_missing_or_drifted=True),
            "REJECT",
        )
        self.assertEqual(
            self.decision(membership_asof_080_ancestor_missing_or_drifted=True),
            "REJECT",
        )
        self.assertEqual(
            self.decision(stable_replay_ancestor_missing_or_drifted=True),
            "REJECT",
        )
        self.assertEqual(
            self.decision(single_scope_parent_missing_or_drifted=True),
            "REJECT",
        )

    def test_runner_planner_worker_and_fixture_blob_drift_rejects(self) -> None:
        artifact_paths = (
            "scripts/run_n6_strategy_center_auto_once.py",
            "scripts/plan_n6_strategy_center_launchd.py",
            "src/ashare_v3/user/strategy_center_worker.py",
            "tests/test_n6_strategy_center_auto.py",
            "tests/test_n6_strategy_center_launchd_plan.py",
            "tests/test_n6_strategy_center_worker.py",
        )
        for artifact_path in artifact_paths:
            with self.subTest(artifact_path=artifact_path):
                blobs = copy.deepcopy(self.policy["required_release_git_blobs"])
                blobs[artifact_path] = "f" * 40
                self.assertEqual(self.decision(release_git_blobs=blobs), "REJECT")
        predecessor_blobs = {
            "scripts/run_n6_strategy_center_auto_once.py": (
                "c943c9ec2fc23800a91cf8796e4bf2229d1bd6d7"
            ),
            "scripts/plan_n6_strategy_center_launchd.py": (
                "d6fd35b899960326dfb53afec09eb4c16692a15c"
            ),
            "tests/test_n6_strategy_center_auto.py": (
                "85ad70eb1ed5b533ab7d9c2895d5bb1af3d2c031"
            ),
            "tests/test_n6_strategy_center_launchd_plan.py": (
                "85e940d8a13894b2785f9ff67f62f1ece5a0d1ef"
            ),
        }
        for artifact_path, predecessor_blob in predecessor_blobs.items():
            with self.subTest(predecessor_artifact_path=artifact_path):
                blobs = copy.deepcopy(self.policy["required_release_git_blobs"])
                blobs[artifact_path] = predecessor_blob
                self.assertEqual(self.decision(release_git_blobs=blobs), "REJECT")
        self.assertEqual(
            self.decision(strategy_center_worker_blob_verified=False),
            "REJECT",
        )
        self.assertEqual(
            self.decision(strategy_center_worker_blob_drift_detected=True),
            "REJECT",
        )
        self.assertEqual(
            self.decision(deadline_12s_runner_planner_blobs_verified=False),
            "REJECT",
        )
        self.assertEqual(
            self.decision(deadline_12s_runner_planner_blob_drift_detected=True),
            "REJECT",
        )

    def test_membership_asof_080_blob_drift_rejects(self) -> None:
        paths = (
            "sql/080_n6_strategy_membership_asof_constraint.sql",
            "sql/080_n6_strategy_membership_asof_constraint_rollback.sql",
            "tests/test_n6_strategy_membership_asof_constraint_080.py",
        )
        for path in paths:
            with self.subTest(path=path):
                blobs = copy.deepcopy(self.policy["required_release_git_blobs"])
                blobs[path] = "f" * 40
                self.assertEqual(self.decision(release_git_blobs=blobs), "REJECT")
        self.assertEqual(
            self.decision(membership_asof_080_blobs_verified=False),
            "REJECT",
        )
        self.assertEqual(
            self.decision(membership_asof_080_blob_drift_detected=True),
            "REJECT",
        )

    def test_exact_argv_has_no_external_trade_date_or_scope(self) -> None:
        extra_argv = list(self.request["program_arguments"]) + ["--trade-date", "20260721"]
        self.assertEqual(self.decision(program_arguments=extra_argv), "REJECT")
        self.assertEqual(self.decision(runner_flags=["--execute"]), "REJECT")
        self.assertEqual(self.decision(runner_path="/tmp/runner.py"), "REJECT")
        self.assertEqual(self.decision(planner_path="/tmp/planner.py"), "REJECT")
        self.assertEqual(self.decision(runtime_env_path="/tmp/runtime-env"), "REJECT")
        self.assertEqual(self.decision(python_executable="/usr/bin/python3"), "REJECT")
        self.assertEqual(self.decision(external_trade_date_argument_requested=True), "REJECT")
        self.assertEqual(self.decision(external_scope_argument_requested=True), "REJECT")
        self.assertEqual(self.decision(mutable_code_requested=True), "REJECT")

    def test_current_open_trade_date_and_closed_day_policy_fail_closed(self) -> None:
        self.assertEqual(self.decision(), "ACCEPT")
        self.assertEqual(
            self.decision(
                trade_date="20260722",
                current_trade_date="20260722",
                canary_trade_date="20260722",
                common_trade_calendar_trade_date="20260722",
            ),
            "REJECT",
        )
        self.assertEqual(
            self.decision(
                trade_date="20260724",
                current_trade_date="20260724",
                canary_trade_date="20260724",
                common_trade_calendar_trade_date="20260724",
            ),
            "REJECT",
        )
        self.assertEqual(self.decision(trade_date="20260722"), "REJECT")
        self.assertEqual(self.decision(trade_date="20260724"), "REJECT")
        self.assertEqual(self.decision(current_trade_date="20260722"), "REJECT")
        self.assertEqual(self.decision(current_trade_date="20260724"), "REJECT")
        self.assertEqual(self.decision(canary_trade_date="20260722"), "REJECT")
        self.assertEqual(self.decision(canary_trade_date="20260724"), "REJECT")
        self.assertEqual(self.decision(trade_date="2026-07-23"), "REJECT")
        self.assertEqual(self.decision(canary_trade_date="2026-07-23"), "REJECT")
        self.assertEqual(
            self.decision(onsite_asia_shanghai_date="20260722"),
            "REJECT",
        )
        self.assertEqual(
            self.decision(common_trade_calendar_trade_date="20260722"),
            "REJECT",
        )
        self.assertEqual(
            self.decision(common_trade_calendar_is_open=False),
            "REJECT",
        )
        self.assertEqual(self.decision(non_current_trade_date_requested=True), "REJECT")
        self.assertEqual(self.decision(non_open_trade_date_write_requested=True), "REJECT")
        self.assertEqual(self.decision(closed_day_behavior="execute"), "REJECT")
        self.assertEqual(self.policy["closed_day_behavior"], "fail_closed_noop_no_dml")

    def test_five_second_schedule_timezone_and_no_overlap_are_exact(self) -> None:
        self.assertEqual(self.policy["required_plist_values"]["StartInterval"], 5)
        self.assertEqual(self.policy["required_plist_values"]["ThrottleInterval"], 5)
        self.assertEqual(self.decision(timezone="UTC"), "REJECT")
        self.assertEqual(self.decision(start_interval_seconds=6), "REJECT")
        plist = copy.deepcopy(self.policy["required_plist_values"])
        plist["StartInterval"] = 6
        self.assertEqual(self.decision(plist_values=plist), "REJECT")
        plist = copy.deepcopy(self.policy["required_plist_values"])
        plist["ThrottleInterval"] = 6
        self.assertEqual(self.decision(plist_values=plist), "REJECT")
        for field in (
            "launchd_single_instance_verified",
            "advisory_lock_verified",
            "advisory_lock_fail_closed_verified",
            "runner_uses_source_fingerprint_attempt_run_id",
            "runner_binds_asia_shanghai_current_date",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        self.assertEqual(self.decision(overlap_detected=True), "REJECT")
        self.assertEqual(self.decision(advisory_lock_bypass_requested=True), "REJECT")

    def test_each_tick_is_one_ordered_scope_without_all_users_transaction(
        self,
    ) -> None:
        self.assertEqual(self.policy["max_scopes_per_tick"], 1)
        self.assertEqual(
            self.policy["transaction_scope"],
            "single_principal_user_revision",
        )
        expected_order = ["selection_revision_id", "principal_id", "user_id"]
        self.assertEqual(self.policy["pending_scope_order"], expected_order)
        self.assertEqual(self.policy["active_scope_order"], expected_order)
        self.assertEqual(
            self.policy["active_scope_cursor_mode"],
            "persistent_round_robin",
        )
        self.assertEqual(
            self.policy["failure_queue_behavior"],
            "retain_selected_and_remaining",
        )
        self.assertEqual(self.policy["required_max_runtime_seconds"], 12)
        self.assertEqual(self.policy["evaluation_budget_seconds"], 11.5)
        self.assertEqual(self.policy["evidence_grace_seconds"], 0.5)
        self.assertEqual(
            self.policy["evaluation_budget_seconds"]
            + self.policy["evidence_grace_seconds"],
            self.policy["required_max_runtime_seconds"],
        )
        reject_cases = {
            "max_scopes_per_tick": 2,
            "transaction_scope": "all_users",
            "pending_scope_order": ["principal_id", "user_id"],
            "active_scope_order": ["principal_id", "user_id"],
            "active_scope_cursor_mode": "restart_each_tick",
            "failure_queue_behavior": "advance_failed_scope",
            "evaluation_budget_seconds": 11.6,
            "evidence_grace_seconds": 0.4,
            "max_runtime_seconds": 13,
        }
        for field, value in reject_cases.items():
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: value}), "REJECT")
        legacy_argv = list(self.request["program_arguments"])
        runtime_index = legacy_argv.index("--max-runtime-seconds") + 1
        legacy_argv[runtime_index] = "10"
        self.assertEqual(
            self.decision(
                max_runtime_seconds=10,
                evaluation_budget_seconds=9.5,
                program_arguments=legacy_argv,
                runner_argv_sha256=argv_sha256(legacy_argv),
            ),
            "REJECT",
        )
        for field in (
            "single_scope_per_tick_verified",
            "single_scope_transaction_verified",
            "pending_scope_order_verified",
            "pending_precedes_active_verified",
            "active_round_robin_cursor_verified",
            "scope_cursor_restart_restore_verified",
            "failure_preserves_scope_queue_verified",
            "runtime_budget_split_verified",
            "all_users_transaction_absent_verified",
            "per_user_selection_activation_only",
            "per_user_projection_transaction_boundary_verified",
            "cross_user_leakage_guard_verified",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        for field in (
            "more_than_one_scope_per_tick_requested",
            "all_users_transaction_requested",
            "pending_scope_order_drift_detected",
            "active_scope_cursor_drift_detected",
            "scope_queue_advanced_on_failure",
            "runtime_budget_split_drift_detected",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")
        self.assertEqual(self.decision(cross_user_write_detected=True), "REJECT")

    def test_pgservice_acl_and_write_allowlist_are_exact(self) -> None:
        self.assertEqual(
            self.policy["allowed_write_tables"],
            [
                "n6_user_strategy_selection_revision",
                "n6_strategy_match_projection",
                "n6_strategy_observation_projection",
                "n6_strategy_match_change",
            ],
        )
        self.assertEqual(
            self.decision(
                database_service_arguments={
                    **self.policy["required_database_service_arguments"],
                    "PGSERVICE": "n6_btrack_web",
                }
            ),
            "REJECT",
        )
        self.assertEqual(
            self.decision(
                database_service_arguments={
                    **self.policy["required_database_service_arguments"],
                    "PGPASSWORD": "secret",
                }
            ),
            "REJECT",
        )
        self.assertEqual(self.decision(env_launcher=["/usr/bin/env"]), "REJECT")
        self.assertEqual(self.decision(strategy_worker_acl_verified=False), "REJECT")
        self.assertEqual(self.decision(acl_drift_detected=True), "REJECT")
        self.assertEqual(self.decision(pgservice_drift_detected=True), "REJECT")
        self.assertEqual(
            self.decision(declared_write_tables=self.policy["allowed_write_tables"] + ["n6_virtual_trade"]),
            "REJECT",
        )
        self.assertEqual(self.decision(write_allowlist_drift_detected=True), "REJECT")
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
                "allowed_mutation_resources": [
                    self.policy["launch_agent_plist_path"],
                    f"gui/current-user/{self.policy['launch_agent_label']}",
                ],
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
        drifted_rollback["allowed_mutation_resources"].append(
            "n6_strategy_observation_projection"
        )
        self.assertEqual(
            self.decision(rollback_contract=drifted_rollback),
            "REJECT",
        )
        for field in (
            "input_watermark_frozen",
            "plan_hash_frozen",
            "selection_cas_verified",
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

    def test_exact_singletons_resources_and_operations_are_required(self) -> None:
        for field in self.policy["required_singleton_counts"]:
            for value in (0, 2, True, "1"):
                with self.subTest(field=field, value=value):
                    self.assertEqual(self.decision(**{field: value}), "REJECT")
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
                + ["launchctl_kickstart_other_label"]
            ),
            "REJECT",
        )
        self.assertEqual(self.decision(other_launch_agent_touched=True), "REJECT")

    def test_primary_activation_and_conditional_rollback_are_bounded(self) -> None:
        self.assertEqual(self.decision(primary_install_attempts=2), "REJECT")
        self.assertEqual(self.decision(primary_bootstrap_attempts=2), "REJECT")
        self.assertEqual(self.decision(primary_retries=1), "REJECT")
        self.assertEqual(
            self.decision(
                rollback_attempts=1,
                rollback_bootout_attempts=1,
                rollback_remove_plist_attempts=1,
                readiness_failed=True,
            ),
            "ACCEPT",
        )
        self.assertEqual(
            self.decision(
                rollback_attempts=1,
                rollback_bootout_attempts=1,
                rollback_remove_plist_attempts=1,
                readiness_failed=False,
            ),
            "REJECT",
        )
        self.assertEqual(self.decision(rollback_attempts=2), "REJECT")
        self.assertEqual(self.decision(rollback_database_mutation_requested=True), "REJECT")

    def test_n1_n5_queue_account_trading_and_executor_paths_reject(self) -> None:
        fields = (
            "n1_n5_write_requested",
            "outbox_inbox_checkpoint_mutation_requested",
            "account_mutation_requested",
            "cash_mutation_requested",
            "position_mutation_requested",
            "proposal_touched",
            "order_touched",
            "trade_touched",
            "real_broker_connected",
            "voice_mobile_sim_requested",
            "virtual_executor_loaded_or_running",
            "migration_or_schema_requested",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_every_required_field_is_fail_closed(self) -> None:
        for field in self.policy["required_true_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        for field in self.policy["required_false_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")

    def test_control_documents_reference_all_named_policies(self) -> None:
        paths = (
            "AGENTS.md",
            "docs/EXECUTION_COMPILER.md",
            "docs/EXECUTION_KERNEL.md",
            "docs/EXECUTION_RUNTIME_GATE.md",
        )
        for path in paths:
            with self.subTest(path=path):
                text = (ROOT / path).read_text(encoding="utf-8")
                self.assertIn(F464_POLICY_ID, text)
                self.assertIn(BOUNDED_POLICY_ID, text)
                self.assertIn(WEB_POLICY_ID, text)


def canonical_f464_request(policy: dict[str, Any]) -> dict[str, Any]:
    exact_fields = (
        "required_release",
        "required_release_git_blobs",
        "temporal_confluence_v2_lineage",
        "required_runtime_file_sha256",
        "required_migration_live_predicate",
        "required_live_web",
        "required_evaluator_before_state",
        "required_evaluator_target",
        "required_activation_chain",
        "required_virtual_executor",
        "required_canary_scope",
        "required_canary_result",
        "scheduler_contract",
        "activation_operation_counts",
        "failure_compensation_contract",
        "required_transition_order",
        "required_zero_side_effect_counts",
    )
    request = {
        "policy_id": policy["policy_id"],
        "layer_role": policy["layer_role"],
        **{field: copy.deepcopy(policy[field]) for field in exact_fields},
    }
    request.update({field: True for field in policy["required_true_fields"]})
    request.update({field: False for field in policy["required_false_fields"]})
    return request


def evaluate_f464(policy: dict[str, Any], request: dict[str, Any]) -> str:
    reject = policy["default_runtime_execution_decision"]
    if request.get("policy_id") != policy["policy_id"]:
        return reject
    if request.get("layer_role") != policy["layer_role"]:
        return reject
    exact_fields = (
        "required_release",
        "required_release_git_blobs",
        "temporal_confluence_v2_lineage",
        "required_runtime_file_sha256",
        "required_migration_live_predicate",
        "required_live_web",
        "required_evaluator_before_state",
        "required_evaluator_target",
        "required_activation_chain",
        "required_virtual_executor",
        "required_canary_scope",
        "required_canary_result",
        "scheduler_contract",
        "activation_operation_counts",
        "failure_compensation_contract",
        "required_transition_order",
        "required_zero_side_effect_counts",
    )
    if any(request.get(field) != policy[field] for field in exact_fields):
        return reject
    if any(request.get(field) is not True for field in policy["required_true_fields"]):
        return reject
    if any(request.get(field) is not False for field in policy["required_false_fields"]):
        return reject
    if any(value != 0 for value in request["required_zero_side_effect_counts"].values()):
        return reject
    return policy["accept_decision"]


class N6StrategyCenterScheduledEvaluatorF464PolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy(F464_POLICY_ID)
        cls.request = canonical_f464_request(cls.policy)

    def decision(self, **changes: Any) -> str:
        request = copy.deepcopy(self.request)
        request.update(changes)
        return evaluate_f464(self.policy, request)

    def mutate(self, field: str, key: str, value: Any) -> str:
        changed = copy.deepcopy(self.request[field])
        changed[key] = value
        return self.decision(**{field: changed})

    def test_f464_is_the_only_runtime_gate_policy_and_legacy_rejects_f464(self) -> None:
        self.assertEqual(self.decision(), "ACCEPT")
        self.assertEqual(self.policy["supersedes_policy_id"], POLICY_ID)
        self.assertEqual(self.policy["legacy_policy_f464_decision"], "REJECT")
        legacy = load_policy(POLICY_ID)
        legacy_request = canonical_request(legacy)
        self.assertEqual(
            evaluate(
                legacy,
                {
                    **legacy_request,
                    "release_path": (
                        f"{legacy['release_root']}/20260726_000001__"
                        "f4641e9c4cd4dff1a817f779d28007fe7cdffe62"
                    ),
                    "release_commit_sha": (
                        "f4641e9c4cd4dff1a817f779d28007fe7cdffe62"
                    ),
                    "release_tree_sha": (
                        "c654cbc03c0341c9b3490a02a432b136984c43ce"
                    ),
                },
            ),
            "REJECT",
        )
        runtime_gate = (ROOT / "docs" / "EXECUTION_RUNTIME_GATE.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(F464_POLICY_ID, runtime_gate)
        self.assertNotIn(f"`{POLICY_ID}`, or", runtime_gate)

    def test_exact_f464_release_blobs_and_temporal_lineage_are_frozen(self) -> None:
        self.assertEqual(
            self.policy["required_release"],
            {
                "commit": "f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
                "tree": "c654cbc03c0341c9b3490a02a432b136984c43ce",
            },
        )
        for field in (
            "required_release_git_blobs",
            "temporal_confluence_v2_lineage",
            "required_runtime_file_sha256",
        ):
            changed = copy.deepcopy(self.policy[field])
            first = next(iter(changed))
            changed[first] = "f" * 40
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: changed}), "REJECT")

    def test_exact_live_migration_web_plist_package_and_chain_hashes(self) -> None:
        self.assertEqual(
            self.policy["required_live_web"]["plist_sha256"],
            "7532979992d8e73a02a6bf81c0a43fa89e49843589d348792abfd62e3b0e64b8",
        )
        self.assertEqual(
            self.policy["required_evaluator_before_state"]["source_plist_sha256"],
            "60e9446a89b5f84ff5dee874eab6d05974c4e2dd6fb63a30c2d77074bb0c501a",
        )
        self.assertEqual(
            self.policy["required_evaluator_target"]["target_plist_sha256"],
            "a0219e9585c8e67c905805c9d603d854aa2fb67e44857b240e4509cc7d4fe936",
        )
        self.assertEqual(
            self.policy["required_evaluator_target"][
                "offline_activation_manifest_sha256"
            ],
            "b80edef162d08b857c81677f20166987c7c03a32af6cabf0dd1632af04da2afa",
        )
        self.assertEqual(self.policy["required_activation_chain"]["event_count"], 78)
        for field in (
            "required_migration_live_predicate",
            "required_live_web",
            "required_evaluator_before_state",
            "required_evaluator_target",
            "required_activation_chain",
        ):
            changed = copy.deepcopy(self.policy[field])
            first = next(iter(changed))
            changed[first] = "drift"
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: changed}), "REJECT")

    def test_exact_20260727_single_scope_canary_and_cas_are_required(self) -> None:
        self.assertEqual(self.policy["required_trade_date"], "20260727")
        self.assertEqual(
            self.policy["required_canary_scope"],
            {
                "principal_id": 12,
                "principal_type": "human_user",
                "user_id": 11,
                "selection_revision_id": 22,
                "selection_revision_no": 1,
                "package_key": "package_1",
                "package_version": "v2",
            },
        )
        self.assertEqual(
            self.mutate("required_canary_scope", "user_id", 12),
            "REJECT",
        )
        for invalid_principal_type in ("user", "admin", "unknown"):
            with self.subTest(principal_type=invalid_principal_type):
                self.assertEqual(
                    self.mutate(
                        "required_canary_scope",
                        "principal_type",
                        invalid_principal_type,
                    ),
                    "REJECT",
                )
        self.assertEqual(
            self.mutate(
                "required_canary_result", "all_cas_predicates_match", False
            ),
            "REJECT",
        )
        self.assertEqual(
            self.mutate(
                "required_canary_result", "fresh_business_increment_count", 1
            ),
            "REJECT",
        )
        self.assertEqual(self.decision(cas_drift_detected=True), "REJECT")

    def test_scheduler_is_bounded_pending_first_display_shadow_only(self) -> None:
        expected = {
            "start_interval_seconds": 5,
            "run_at_load": False,
            "keep_alive": False,
            "max_runtime_seconds": 12,
            "max_scopes_per_tick": 1,
            "pending_precedes_active": True,
            "active_scope_cursor_mode": "persistent_round_robin",
            "transaction_scope": "single_principal_user_revision",
            "all_users_transaction": False,
            "display_only": True,
            "shadow_only": True,
        }
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertEqual(self.policy["scheduler_contract"][key], value)
        self.assertEqual(
            self.mutate("scheduler_contract", "all_users_transaction", True),
            "REJECT",
        )
        self.assertEqual(self.decision(all_users_transaction_requested=True), "REJECT")

    def test_source_target_source_order_and_absent_label_operations_are_exact(self) -> None:
        self.assertEqual(
            self.policy["required_transition_order"],
            [
                "frozen_source",
                "validated_f464_target",
                "frozen_source_on_failure_only",
            ],
        )
        operations = self.policy["activation_operation_counts"]
        self.assertEqual(operations["primary_atomic_plist_replace"], 1)
        self.assertEqual(operations["primary_bootstrap"], 1)
        self.assertEqual(operations["primary_bootout"], 0)
        self.assertEqual(operations["primary_kickstart"], 0)
        self.assertEqual(operations["primary_start"], 0)
        self.assertEqual(
            self.mutate("activation_operation_counts", "primary_bootout", 1),
            "REJECT",
        )
        self.assertEqual(
            self.mutate(
                "failure_compensation_contract",
                "bootstrap_superseded_658_source",
                True,
            ),
            "REJECT",
        )
        self.assertEqual(self.decision(wrong_order_requested=True), "REJECT")
        self.assertEqual(self.decision(empty_state_restore_requested=True), "REJECT")

    def test_hash_all_users_and_every_side_effect_path_reject(self) -> None:
        for field in (
            "hash_drift_detected",
            "all_users_transaction_requested",
            "side_effect_requested",
            "deepseek_requested",
            "autonomous_execution_requested",
            "trading_side_effect_requested",
            "n1_n5_touched",
            "database_or_release_mutation_requested_by_governance_session",
        ):
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")
        for effect in self.policy["required_zero_side_effect_counts"]:
            with self.subTest(effect=effect):
                counts = copy.deepcopy(
                    self.policy["required_zero_side_effect_counts"]
                )
                counts[effect] = 1
                self.assertEqual(
                    self.decision(required_zero_side_effect_counts=counts),
                    "REJECT",
                )

    def test_every_f464_required_boolean_is_fail_closed(self) -> None:
        for field in self.policy["required_true_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: False}), "REJECT")
        for field in self.policy["required_false_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: True}), "REJECT")


if __name__ == "__main__":
    unittest.main()
