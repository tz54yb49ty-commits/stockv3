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
POLICY_ID = "n4_lifecycle_deactivation_state_columns_controlled_promotion_v1"
BASE_COMMIT = "8229124a7c770e10793d65f937f79dc9ab6ca42c"
SOURCE_ENDPOINT = "6d1b7a24f2f6d6fa6ef5a4d675995c943703101e"
SOURCE_ROLLBACK = "a1ff8b0e0dbda579dd2cece1c5b84a10879293bc"
COMBINED_PATCH_SHA256 = (
    "7de6b1a94b08f4fa2ebc84443dd528e1a9d6f5a9c28d1ab0f7af89a938aedefe"
)
ROLLBACK_PATCH_SHA256 = (
    "fbffe7733183d0c3234b7d6c050781c43524f551d9728fcbcb9febc87ebed777"
)


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
        raise AssertionError("policy must contain one JSON fence")
    return json.loads(match.group(1), object_pairs_hook=reject_duplicate_json_keys)


def literal_hash(pattern: str) -> str | None:
    value = pattern.removeprefix("^").removesuffix("$")
    if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value):
        return value
    return None


def canonical_request(policy: dict[str, Any]) -> dict[str, Any]:
    dynamic_hashes = {
        "policy_definition_commit": "1" * 40,
        "policy_definition_tree": "2" * 40,
        "active_head_commit": "1" * 40,
        "final_promotion_commit_1": "3" * 40,
        "final_promotion_commit_1_parent": "1" * 40,
        "final_promotion_tip": "4" * 40,
        "final_promotion_tip_parent": "3" * 40,
        "final_promotion_tip_tree": "6" * 40,
        "final_rollback_commit": "5" * 40,
        "final_rollback_parent": "4" * 40,
        "final_rollback_tree": "2" * 40,
        "merge_target_commit": "4" * 40,
        "reported_rollback_target": "5" * 40,
    }
    request: dict[str, Any] = {
        "policy_id": POLICY_ID,
        "layer_role": "runtime_control",
        "scope_mode": policy["scope_mode"],
        "phase_mode": policy["phase_mode"],
        "declared_mutation_resources": list(policy["allowed_mutation_resources"]),
        "declared_operations": list(policy["allowed_operations"]),
    }
    for field, pattern in policy["required_hash_fields"].items():
        request[field] = literal_hash(pattern) or dynamic_hashes[field]
    request.update(copy.deepcopy(policy["required_exact_values"]))
    request.update(policy["required_singleton_counts"])
    request.update({field: True for field in policy["required_true_fields"]})
    request.update({field: False for field in policy["required_false_fields"]})
    return request


def evaluate(policy: dict[str, Any], request: dict[str, Any]) -> str:
    reject = policy["default_runtime_execution_decision"]
    allowed_fields = {
        "policy_id",
        "layer_role",
        "scope_mode",
        "phase_mode",
        "declared_mutation_resources",
        "declared_operations",
    }
    allowed_fields.update(policy["required_hash_fields"])
    allowed_fields.update(policy["required_exact_values"])
    allowed_fields.update(policy["required_singleton_counts"])
    allowed_fields.update(policy["required_true_fields"])
    allowed_fields.update(policy["required_false_fields"])
    if policy["reject_unknown_request_fields"] and set(request) != allowed_fields:
        return reject
    for field in ("policy_id", "layer_role", "scope_mode", "phase_mode"):
        if request.get(field) != policy[field]:
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
    for left, right in policy["required_equal_field_pairs"]:
        if request.get(left) != request.get(right):
            return reject
    if request.get("declared_mutation_resources") != policy["allowed_mutation_resources"]:
        return reject
    if request.get("declared_operations") != policy["allowed_operations"]:
        return reject
    commit_fields = (
        "policy_definition_commit",
        "final_promotion_commit_1",
        "final_promotion_tip",
        "final_rollback_commit",
    )
    commits = [request[field] for field in commit_fields]
    if len(set(commits)) != len(commits):
        return reject
    source_commits = {
        request["source_base_commit"],
        request["source_endpoint_commit"],
        request["source_rollback_commit"],
    }
    if any(commit in source_commits for commit in commits):
        return reject
    return policy["accept_decision"]


def git_bytes(*args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


class N4LifecycleControlledPromotionPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()
        cls.request = canonical_request(cls.policy)

    def decide(self, **changes: Any) -> str:
        request = copy.deepcopy(self.request)
        request.update(changes)
        return evaluate(self.policy, request)

    def test_machine_contract_accepts_only_independent_execution(self) -> None:
        self.assertEqual(self.decide(), "ACCEPT")
        self.assertEqual(self.policy["runtime_gate_decision"], "ACCEPT")
        self.assertEqual(self.policy["default_runtime_execution_decision"], "REJECT")
        self.assertFalse(self.policy["governance_definition_session_can_execute_policy"])
        self.assertEqual(
            self.decide(current_request_is_policy_definition_gate=True),
            "REJECT",
        )

    def test_source_commits_patches_paths_and_blobs_are_real_and_fixed(self) -> None:
        hashes = self.policy["required_hash_fields"]
        exact = self.policy["required_exact_values"]
        self.assertEqual(literal_hash(hashes["source_base_commit"]), BASE_COMMIT)
        self.assertEqual(literal_hash(hashes["source_endpoint_commit"]), SOURCE_ENDPOINT)
        self.assertEqual(literal_hash(hashes["source_rollback_commit"]), SOURCE_ROLLBACK)
        self.assertEqual(
            literal_hash(hashes["source_base_tree"]),
            git_bytes("rev-parse", f"{BASE_COMMIT}^{{tree}}").decode().strip(),
        )
        self.assertEqual(
            literal_hash(hashes["source_endpoint_tree"]),
            git_bytes("rev-parse", f"{SOURCE_ENDPOINT}^{{tree}}").decode().strip(),
        )
        self.assertEqual(
            literal_hash(hashes["source_rollback_tree"]),
            git_bytes("rev-parse", f"{SOURCE_ROLLBACK}^{{tree}}").decode().strip(),
        )
        combined = git_bytes(
            "diff", BASE_COMMIT, SOURCE_ENDPOINT, "--full-index", "--binary"
        )
        rollback = git_bytes(
            "diff", SOURCE_ENDPOINT, SOURCE_ROLLBACK, "--full-index", "--binary"
        )
        self.assertEqual(hashlib.sha256(combined).hexdigest(), COMBINED_PATCH_SHA256)
        self.assertEqual(hashlib.sha256(rollback).hexdigest(), ROLLBACK_PATCH_SHA256)
        self.assertEqual(
            git_bytes("rev-list", "--count", f"{BASE_COMMIT}..{SOURCE_ENDPOINT}").strip(),
            b"2",
        )
        changed_paths = git_bytes(
            "diff", "--name-only", BASE_COMMIT, SOURCE_ENDPOINT
        ).decode().splitlines()
        self.assertEqual(sorted(changed_paths), exact["n4_file_allowlist"])
        self.assertEqual(
            git_bytes("rev-parse", f"{BASE_COMMIT}^{{tree}}").strip(),
            git_bytes("rev-parse", f"{SOURCE_ROLLBACK}^{{tree}}").strip(),
        )
        blobs: dict[str, str] = {}
        for path in exact["n4_file_allowlist"]:
            row = git_bytes("ls-tree", SOURCE_ENDPOINT, "--", path).decode().strip()
            blobs[path] = row.split()[2]
        self.assertEqual(blobs, exact["source_endpoint_blob_sha1_by_path"])

    def test_final_shas_are_dynamic_but_ancestry_is_exact(self) -> None:
        hashes = self.policy["required_hash_fields"]
        for field in (
            "policy_definition_commit",
            "final_promotion_commit_1",
            "final_promotion_tip",
            "final_rollback_commit",
        ):
            self.assertEqual(hashes[field], "^[0-9a-f]{40}$")
        self.assertFalse(self.policy["final_commit_shas_fixed_in_policy"])
        self.assertTrue(self.policy["execution_time_exact_final_commit_freeze_required"])
        for field in (
            "active_head_commit",
            "final_promotion_commit_1_parent",
            "final_promotion_tip_parent",
            "final_rollback_parent",
            "final_rollback_tree",
        ):
            changed = "9" * 40
            self.assertEqual(self.decide(**{field: changed}), "REJECT", field)

    def test_source_commits_cannot_be_substituted_as_final_targets(self) -> None:
        self.assertFalse(self.policy["source_evidence_commits_executable"])
        for field, commit in (
            ("final_promotion_commit_1", SOURCE_ENDPOINT),
            ("final_promotion_tip", SOURCE_ENDPOINT),
            ("final_rollback_commit", SOURCE_ROLLBACK),
        ):
            self.assertEqual(self.decide(**{field: commit}), "REJECT", field)
        self.assertEqual(
            self.decide(source_endpoint_used_as_execution_target=True),
            "REJECT",
        )

    def test_file_patch_blob_scope_cannot_widen(self) -> None:
        exact = self.policy["required_exact_values"]
        widened = list(exact["final_changed_paths"]) + ["src/extra.py"]
        self.assertEqual(self.decide(final_changed_paths=widened), "REJECT")
        drifted_blobs = dict(exact["final_blob_sha1_by_path"])
        first_path = exact["n4_file_allowlist"][0]
        drifted_blobs[first_path] = "f" * 40
        self.assertEqual(self.decide(final_blob_sha1_by_path=drifted_blobs), "REJECT")
        self.assertEqual(
            self.decide(final_combined_patch_sha256="f" * 64),
            "REJECT",
        )
        self.assertEqual(
            self.decide(dynamic_file_allowlist_requested=True),
            "REJECT",
        )

    def test_only_two_exact_labels_and_original_plists_are_allowed(self) -> None:
        exact = self.policy["required_exact_values"]
        self.assertEqual(
            exact["launchd_labels"],
            [
                "com.ashare-v3.n4.proof-discovery-poller",
                "com.ashare-v3.n4.proof-discovery-poller.hint",
            ],
        )
        labels = list(exact["launchd_labels"]) + ["com.ashare-v3.n4.other"]
        self.assertEqual(self.decide(launchd_labels=labels), "REJECT")
        self.assertEqual(self.decide(ordinary_plist_sha256="f" * 64), "REJECT")
        paths = dict(exact["plist_path_by_label"])
        paths[exact["launchd_labels"][0]] = "/tmp/other.plist"
        self.assertEqual(self.decide(plist_path_by_label=paths), "REJECT")
        for label, hash_field in (
            (exact["launchd_labels"][0], "ordinary_plist_sha256"),
            (exact["launchd_labels"][1], "hint_plist_sha256"),
        ):
            plist_path = Path(exact["plist_path_by_label"][label])
            self.assertEqual(
                hashlib.sha256(plist_path.read_bytes()).hexdigest(),
                literal_hash(self.policy["required_hash_fields"][hash_field]),
            )

    def test_execution_budget_and_forbidden_operations_fail_closed(self) -> None:
        counts = self.policy["required_singleton_counts"]
        self.assertEqual(counts["source_promotion_commit_count"], 2)
        self.assertEqual(counts["final_promotion_commit_count"], 2)
        self.assertEqual(counts["ff_only_merge_attempt_count"], 1)
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
            "fixed_sleep_requested",
            "kickstart_requested",
            "manual_execute_requested",
            "retry_requested",
            "automatic_rollback_requested",
            "rollback_execution_requested",
            "push_requested",
            "checkout_rebase_or_cherry_pick_requested",
            "plist_write_requested",
            "other_launchagent_requested",
            "n2_operation_requested",
            "n3_operation_requested",
            "n5_operation_requested",
            "n6_operation_requested",
            "database_dml_requested",
            "message_or_queue_operation_requested",
            "historical_event_mutation_requested",
            "trade_operation_requested",
        ):
            self.assertEqual(self.decide(**{field: True}), "REJECT", field)

    def test_all_governance_documents_name_the_policy(self) -> None:
        for relative in (
            "AGENTS.md",
            "docs/EXECUTION_KERNEL.md",
            "docs/EXECUTION_COMPILER.md",
            "docs/EXECUTION_RUNTIME_GATE.md",
            "docs/EXECUTION_SANDBOX.md",
            "docs/EXECUTION_TRACE_SYSTEM.md",
            "docs/EXECUTION_TEST_SUITE.md",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(POLICY_ID, text, relative)


if __name__ == "__main__":
    unittest.main()
