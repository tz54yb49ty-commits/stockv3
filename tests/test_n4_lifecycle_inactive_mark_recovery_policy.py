from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "n4_lifecycle_inactive_mark_recovery_v1"
FAILED_ACTIVE = "49fd0a6576d3f3f04c28c0ce65da95d6472931d7"
STABLE_N4 = "ae05d7f8c365d3d0ed807235ab124e0d4cdae28e"
FROZEN_ROLLBACK = "cadbe91c1d400a803dd678710a2733ac0e0d9f92"
PRIOR_POLICY = "3786528a96f2a0489c8021fdffb528dbf88335c6"
PRIOR_RESTORE = "195ac3f30cbb30bfaaf971b0dc8b4bb22d279920"
PRIOR_LIFECYCLE = "5bd53e75412540c173dc47e8c9bd58d4725d89fd"
PRIOR_TYPED = "14786f73ac672608aeecbff2d0fff28002ced622"
PRIOR_CODE_ROLLBACK = "0f62f592e0af21a1d5b20a38d84ba668fc5b7850"


def reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AssertionError(f"duplicate policy JSON key: {key}")
        result[key] = value
    return result


def load_policy() -> dict[str, Any]:
    text = (ROOT / "docs" / "EXECUTION_KERNEL.md").read_text(encoding="utf-8")
    begin = f"<!-- policy:{POLICY_ID}:begin -->"
    end = f"<!-- policy:{POLICY_ID}:end -->"
    if text.count(begin) != 1 or text.count(end) != 1:
        raise AssertionError("policy must contain exactly one begin/end marker pair")
    start = text.index(begin) + len(begin)
    stop = text.index(end, start)
    block = text[start:stop].strip()
    match = re.fullmatch(r"```json\s*(\{.*\})\s*```", block, re.DOTALL)
    if match is None:
        raise AssertionError("policy must contain exactly one JSON fence")
    return json.loads(match.group(1), object_pairs_hook=reject_duplicate_json_keys)


def literal_hash(pattern: str) -> str | None:
    value = pattern.removeprefix("^").removesuffix("$")
    if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value):
        return value
    return None


def git_bytes(*args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


DYNAMIC_HASHES = {
    "policy_definition_commit": "1" * 40,
    "policy_definition_tree": "2" * 40,
    "rollback_restore_commit": "3" * 40,
    "rollback_restore_parent": "1" * 40,
    "rollback_restore_tree": "4" * 40,
    "fixed_lifecycle_commit": "5" * 40,
    "fixed_lifecycle_parent": "3" * 40,
    "typed_columns_commit": "6" * 40,
    "typed_columns_parent": "5" * 40,
    "typed_columns_tree": "7" * 40,
    "fixed_code_rollback_commit": "8" * 40,
    "fixed_code_rollback_parent": "6" * 40,
    "fixed_code_rollback_tree": "4" * 40,
    "active_head_commit": "1" * 40,
    "phase_merge_target_commit": "3" * 40,
    "reported_rollback_target": "8" * 40,
}


def canonical_request(policy: dict[str, Any], phase: str) -> dict[str, Any]:
    hashes: dict[str, str] = {}
    for field, pattern in policy["required_hash_fields"].items():
        hashes[field] = literal_hash(pattern) or DYNAMIC_HASHES[field]
    phase_binding = policy["phase_head_and_target_fields"][phase]
    hashes["active_head_commit"] = hashes[phase_binding["active_head_field"]]
    hashes["phase_merge_target_commit"] = hashes[
        phase_binding["merge_target_field"]
    ]
    request: dict[str, Any] = {
        "policy_id": POLICY_ID,
        "layer_role": policy["layer_role"],
        "scope_mode": policy["scope_mode"],
        "phase_mode": policy["phase_mode"],
        "selected_phase": phase,
        "declared_mutation_resources": copy.deepcopy(
            policy["allowed_mutation_resources"]
        ),
        "declared_operations": copy.deepcopy(
            policy["allowed_operations_by_phase"][phase]
        ),
    }
    request.update(hashes)
    request.update(copy.deepcopy(policy["required_exact_values"]))
    request.update(policy["required_singleton_counts"])
    request.update({field: True for field in policy["required_true_fields"]})
    request.update({field: False for field in policy["required_false_fields"]})
    request.update(policy["phase_required_flags"][phase])
    return request


def evaluate(policy: dict[str, Any], request: dict[str, Any]) -> str:
    reject = policy["default_runtime_execution_decision"]
    allowed_fields = {
        "policy_id",
        "layer_role",
        "scope_mode",
        "phase_mode",
        "selected_phase",
        "declared_mutation_resources",
        "declared_operations",
    }
    allowed_fields.update(policy["required_hash_fields"])
    allowed_fields.update(policy["required_exact_values"])
    allowed_fields.update(policy["required_singleton_counts"])
    allowed_fields.update(policy["required_true_fields"])
    allowed_fields.update(policy["required_false_fields"])
    for flags in policy["phase_required_flags"].values():
        allowed_fields.update(flags)
    if policy["reject_unknown_request_fields"] and set(request) != allowed_fields:
        return reject
    for field in ("policy_id", "layer_role", "scope_mode", "phase_mode"):
        if request.get(field) != policy[field]:
            return reject
    phase = request.get("selected_phase")
    if phase not in policy["allowed_execution_phases"]:
        return reject
    for field, pattern in policy["required_hash_fields"].items():
        if re.fullmatch(pattern, str(request.get(field, ""))) is None:
            return reject
    for field, value in policy["required_exact_values"].items():
        if request.get(field) != value:
            return reject
    for field, value in policy["required_singleton_counts"].items():
        if request.get(field) != value:
            return reject
    for field in policy["required_true_fields"]:
        if request.get(field) is not True:
            return reject
    for field in policy["required_false_fields"]:
        if request.get(field) is not False:
            return reject
    for field, value in policy["phase_required_flags"][phase].items():
        if request.get(field) is not value:
            return reject
    for left, right in policy["required_equal_field_pairs"]:
        if request.get(left) != request.get(right):
            return reject
    phase_binding = policy["phase_head_and_target_fields"][phase]
    if request["active_head_commit"] != request[phase_binding["active_head_field"]]:
        return reject
    if request["phase_merge_target_commit"] != request[
        phase_binding["merge_target_field"]
    ]:
        return reject
    if request["declared_mutation_resources"] != policy["allowed_mutation_resources"]:
        return reject
    if request["declared_operations"] != policy["allowed_operations_by_phase"][phase]:
        return reject
    execution_commits = [
        request["policy_definition_commit"],
        request["rollback_restore_commit"],
        request["fixed_lifecycle_commit"],
        request["typed_columns_commit"],
        request["fixed_code_rollback_commit"],
    ]
    if len(set(execution_commits)) != len(execution_commits):
        return reject
    if request["frozen_content_rollback_commit"] in execution_commits:
        return reject
    return policy["accept_decision"]


class N4LifecycleInactiveMarkRecoveryPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()

    def decide(self, phase: str = "rollback_restore", **changes: Any) -> str:
        request = canonical_request(self.policy, phase)
        request.update(changes)
        return evaluate(self.policy, request)

    def test_all_three_phases_accept_independently(self) -> None:
        self.assertEqual(
            self.policy["policy_revision"], "git_permission_failure_recovery_v2"
        )
        for phase in self.policy["allowed_execution_phases"]:
            self.assertEqual(self.decide(phase), "ACCEPT", phase)
        self.assertEqual(self.policy["default_runtime_execution_decision"], "REJECT")
        self.assertFalse(self.policy["governance_definition_session_can_execute_policy"])
        self.assertEqual(
            self.decide(current_request_is_policy_definition_gate=True), "REJECT"
        )

    def test_frozen_git_evidence_and_stable_blobs_are_real(self) -> None:
        hashes = self.policy["required_hash_fields"]
        exact = self.policy["required_exact_values"]
        self.assertEqual(literal_hash(hashes["failed_active_commit"]), FAILED_ACTIVE)
        self.assertEqual(literal_hash(hashes["stable_n4_commit"]), STABLE_N4)
        self.assertEqual(
            literal_hash(hashes["frozen_content_rollback_commit"]), FROZEN_ROLLBACK
        )
        self.assertEqual(
            git_bytes("rev-parse", f"{FAILED_ACTIVE}^{{tree}}").decode().strip(),
            literal_hash(hashes["failed_active_tree"]),
        )
        stable_tree = git_bytes("rev-parse", f"{STABLE_N4}^{{tree}}").decode().strip()
        self.assertEqual(stable_tree, literal_hash(hashes["stable_n4_tree"]))
        self.assertEqual(
            stable_tree,
            git_bytes("rev-parse", f"{FROZEN_ROLLBACK}^{{tree}}").decode().strip(),
        )
        rollback = git_bytes(
            "diff", "--binary", "--full-index", FAILED_ACTIVE, FROZEN_ROLLBACK
        )
        self.assertEqual(
            hashlib.sha256(rollback).hexdigest(),
            literal_hash(hashes["frozen_content_rollback_patch_sha256"]),
        )
        self.assertEqual(
            sorted(git_bytes("diff", "--name-only", FAILED_ACTIVE, FROZEN_ROLLBACK).decode().splitlines()),
            exact["n4_file_allowlist"],
        )
        blobs: dict[str, str] = {}
        for path in exact["n4_file_allowlist"]:
            blobs[path] = git_bytes("rev-parse", f"{STABLE_N4}:{path}").decode().strip()
        self.assertEqual(blobs, exact["stable_blob_sha1_by_path"])

    def test_corrected_contract_matches_database_domain(self) -> None:
        exact = self.policy["required_exact_values"]
        contract = exact["corrected_inactive_contract"]
        self.assertEqual(contract["trigger_mark_candidate"], "normal")
        self.assertNotIn("none", exact["allowed_trigger_mark_candidate_values"])
        self.assertNotIn(None, exact["allowed_trigger_mark_candidate_values"])
        self.assertEqual(
            contract["previous_trigger_mark_candidate_field"],
            "previous_trigger_mark_candidate",
        )
        self.assertIs(contract["projection_30m_flag"], False)
        self.assertEqual(contract["projection_30m_type"], "none")
        drift = copy.deepcopy(contract)
        drift["trigger_mark_candidate"] = "none"
        self.assertEqual(self.decide(corrected_inactive_contract=drift), "REJECT")

    def test_phase_lineage_and_phase_separation_fail_closed(self) -> None:
        self.assertEqual(self.decide(rollback_restore_parent="9" * 40), "REJECT")
        self.assertEqual(self.decide(fixed_lifecycle_parent="9" * 40), "REJECT")
        self.assertEqual(self.decide(typed_columns_parent="9" * 40), "REJECT")
        self.assertEqual(self.decide(fixed_code_rollback_tree="9" * 40), "REJECT")
        self.assertEqual(self.decide(selected_phase_count=2), "REJECT")
        self.assertEqual(self.decide(multiple_phases_requested=True), "REJECT")
        self.assertEqual(self.decide(automatic_phase_progression_requested=True), "REJECT")
        self.assertEqual(
            self.decide("corrected_promotion", natural_stability_after_restore_verified=False),
            "REJECT",
        )
        self.assertEqual(
            self.decide(
                "corrected_code_only_rollback",
                severe_corrected_contract_failure_verified=False,
            ),
            "REJECT",
        )

    def test_frozen_rollback_is_content_only(self) -> None:
        self.assertFalse(self.policy["frozen_content_rollback_commit_executable"])
        self.assertEqual(
            self.decide(phase_merge_target_commit=FROZEN_ROLLBACK), "REJECT"
        )
        self.assertEqual(
            self.decide(rollback_restore_commit=FROZEN_ROLLBACK), "REJECT"
        )

    def test_file_label_plist_and_operation_scope_cannot_widen(self) -> None:
        exact = self.policy["required_exact_values"]
        widened = list(exact["n4_file_allowlist"]) + ["src/extra.py"]
        self.assertEqual(self.decide(n4_file_allowlist=widened), "REJECT")
        labels = list(exact["launchd_labels"]) + ["com.ashare-v3.n4.other"]
        self.assertEqual(self.decide(launchd_labels=labels), "REJECT")
        for label, hash_field in (
            (exact["launchd_labels"][0], "ordinary_plist_sha256"),
            (exact["launchd_labels"][1], "hint_plist_sha256"),
        ):
            path = Path(exact["plist_path_by_label"][label])
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                literal_hash(self.policy["required_hash_fields"][hash_field]),
            )
        for field in (
            "ff_only_merge_attempt_count",
            "ordinary_bootout_attempt_count",
            "hint_bootout_attempt_count",
            "ordinary_bootstrap_attempt_count",
            "hint_bootstrap_attempt_count",
        ):
            self.assertEqual(self.decide(**{field: 2}), "REJECT", field)
        for field in (
            "non_ff_merge_requested",
            "kickstart_requested",
            "manual_execute_requested",
            "retry_requested",
            "automatic_rollback_requested",
            "schema_or_constraint_change_requested",
            "event_structure_change_requested",
            "database_dml_requested",
            "message_or_queue_operation_requested",
            "historical_target_mutation_requested",
            "n2_operation_requested",
            "n3_operation_requested",
            "n5_operation_requested",
            "n6_operation_requested",
            "trade_operation_requested",
        ):
            self.assertEqual(self.decide(**{field: True}), "REJECT", field)

    def test_failed_target_is_frozen_as_zero_write_evidence(self) -> None:
        exact = self.policy["required_exact_values"]
        self.assertEqual(exact["failed_identity"], "stock:SH:600292")
        self.assertEqual(
            exact["failed_target_zero_write_counts"],
            {"run": 0, "state": 0, "match": 0, "outbox": 0, "inbox": 0},
        )

    def test_prior_git_permission_failure_is_frozen_and_non_executable(self) -> None:
        hashes = self.policy["required_hash_fields"]
        exact = self.policy["required_exact_values"]
        self.assertEqual(
            literal_hash(hashes["prior_policy_definition_commit"]), PRIOR_POLICY
        )
        self.assertEqual(
            literal_hash(hashes["prior_rollback_restore_commit"]), PRIOR_RESTORE
        )
        self.assertEqual(
            literal_hash(hashes["prior_fixed_lifecycle_commit"]), PRIOR_LIFECYCLE
        )
        self.assertEqual(
            literal_hash(hashes["prior_typed_columns_commit"]), PRIOR_TYPED
        )
        self.assertEqual(
            literal_hash(hashes["prior_fixed_code_rollback_commit"]),
            PRIOR_CODE_ROLLBACK,
        )
        self.assertEqual(
            git_bytes("rev-parse", f"{PRIOR_POLICY}^{{tree}}").decode().strip(),
            literal_hash(hashes["prior_policy_definition_tree"]),
        )
        self.assertEqual(
            git_bytes("rev-parse", f"{PRIOR_RESTORE}^").decode().strip(),
            PRIOR_POLICY,
        )
        failure_output = (
            "fatal: update_ref failed for ref 'ORIG_HEAD': cannot lock ref "
            "'ORIG_HEAD': Unable to create '/Users/chuanfuchen/Documents/"
            "A股监控系统v3/.git/ORIG_HEAD.lock': Operation not permitted\n"
        ).encode()
        self.assertEqual(
            hashlib.sha256(failure_output).hexdigest(),
            literal_hash(hashes["prior_merge_failure_output_sha256"]),
        )
        failure = exact["prior_permission_failure"]
        self.assertEqual(
            failure["failure_class"],
            "git_metadata_write_permission_denied_before_ref_or_tree_change",
        )
        self.assertEqual(failure["active_head_before_and_after"], PRIOR_POLICY)
        self.assertTrue(
            all(value == 0 for value in failure["zero_mutation_counts"].values())
        )
        self.assertFalse(self.policy["prior_failed_merge_target_commit_executable"])
        self.assertEqual(
            self.decide(phase_merge_target_commit=PRIOR_RESTORE), "REJECT"
        )
        self.assertEqual(self.decide(prior_policy_execution_reused=True), "REJECT")
        self.assertEqual(
            self.decide(non_escalated_git_merge_probe_requested=True), "REJECT"
        )

    def test_regenerated_patch_hashes_are_frozen_from_prior_chain(self) -> None:
        expected = self.policy["required_exact_values"][
            "required_regenerated_patch_sha256_by_phase"
        ]
        pairs = {
            "rollback_restore": (PRIOR_POLICY, PRIOR_RESTORE),
            "fixed_lifecycle": (PRIOR_RESTORE, PRIOR_LIFECYCLE),
            "typed_columns": (PRIOR_LIFECYCLE, PRIOR_TYPED),
            "fixed_code_rollback": (PRIOR_TYPED, PRIOR_CODE_ROLLBACK),
        }
        for phase, (parent, commit) in pairs.items():
            patch = git_bytes("diff", "--binary", "--full-index", parent, commit)
            self.assertEqual(hashlib.sha256(patch).hexdigest(), expected[phase], phase)

    def test_all_governance_documents_name_policy(self) -> None:
        for relative in (
            "AGENTS.md",
            "docs/EXECUTION_KERNEL.md",
            "docs/EXECUTION_COMPILER.md",
            "docs/EXECUTION_RUNTIME_GATE.md",
            "docs/EXECUTION_SANDBOX.md",
            "docs/EXECUTION_TRACE_SYSTEM.md",
            "docs/EXECUTION_TEST_SUITE.md",
        ):
            self.assertIn(POLICY_ID, (ROOT / relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
