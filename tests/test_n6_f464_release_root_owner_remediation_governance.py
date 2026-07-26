from __future__ import annotations

import copy
import hashlib
import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "n6_f464_release_root_owner_remediation_v1"
POLICY_PATH = ROOT / "docs" / "EXECUTION_KERNEL.md"
SOURCE_PATH = ROOT / "scripts" / "n6_f464_release_root_owner_remediation_v1.c"
TEST_PATH = (
    ROOT
    / "tests"
    / "test_n6_f464_release_root_owner_remediation_governance.py"
)


def load_policy() -> dict[str, Any]:
    text = POLICY_PATH.read_text(encoding="utf-8")
    begin = f"<!-- policy:{POLICY_ID}:begin -->"
    end = f"<!-- policy:{POLICY_ID}:end -->"
    start = text.index(begin) + len(begin)
    stop = text.index(end, start)
    block = text[start:stop].strip()
    match = re.fullmatch(r"```json\s*(\{.*\})\s*```", block, re.DOTALL)
    if match is None:
        raise AssertionError("policy must contain exactly one JSON fence")
    return json.loads(match.group(1))


def canonical_sha256(policy: dict[str, Any]) -> str:
    encoded = json.dumps(
        policy, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_request(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy_id": policy["policy_id"],
        "parent_approval_id": policy["parent_approval_id"],
        "approval_status": policy["approval_status"],
        "approval_reconfirmation_required": policy[
            "approval_reconfirmation_required"
        ],
        "layer_role": policy["layer_role"],
        "mode": policy["mode"],
        "risk_level": policy["risk_level"],
        "scope_mode": policy["scope_mode"],
        "phase_mode": policy["phase_mode"],
        "activation_state_before_sha256": policy[
            "activation_state_before_sha256"
        ],
        "activation_state_before_event_count": policy[
            "activation_state_before_event_count"
        ],
        "activation_state_before_tail_event_sha256": policy[
            "activation_state_before_tail_event_sha256"
        ],
        "activation_checkpoint_sha256_corrected": policy[
            "activation_checkpoint_sha256_corrected"
        ],
        "release_root": policy["release_root"],
        "release_root_before": copy.deepcopy(policy["release_root_before"]),
        "release_root_after": copy.deepcopy(policy["release_root_after"]),
        "required_absent_before_and_after": list(
            policy["required_absent_before_and_after"]
        ),
        "remediation_helper_source_path": policy[
            "remediation_helper_source_path"
        ],
        "remediation_helper_install_path": policy[
            "remediation_helper_install_path"
        ],
        "compiled_helper_artifact_path": policy[
            "compiled_helper_artifact_path"
        ],
        "helper_attestation_path": policy["helper_attestation_path"],
        "required_helper_identity": copy.deepcopy(
            policy["required_helper_identity"]
        ),
        "live_freeze": copy.deepcopy(policy["live_freeze"]),
        "allowed_governance_files": list(policy["allowed_governance_files"]),
        "allowed_governance_operations": list(
            policy["allowed_governance_operations"]
        ),
        "allowed_later_execution_operations": list(
            policy["allowed_later_execution_operations"]
        ),
        "required_singleton_counts": copy.deepcopy(
            policy["required_singleton_counts"]
        ),
        **{field: True for field in policy["required_true_fields"]},
        **{field: False for field in policy["required_false_fields"]},
    }


def evaluate(policy: dict[str, Any], request: dict[str, Any]) -> str:
    reject = policy["default_execution_decision"]
    exact_fields = (
        "policy_id",
        "parent_approval_id",
        "approval_status",
        "approval_reconfirmation_required",
        "layer_role",
        "mode",
        "risk_level",
        "scope_mode",
        "phase_mode",
        "activation_state_before_sha256",
        "activation_state_before_event_count",
        "activation_state_before_tail_event_sha256",
        "activation_checkpoint_sha256_corrected",
        "release_root",
        "release_root_before",
        "release_root_after",
        "required_absent_before_and_after",
        "remediation_helper_source_path",
        "remediation_helper_install_path",
        "compiled_helper_artifact_path",
        "helper_attestation_path",
        "required_helper_identity",
        "live_freeze",
        "allowed_governance_files",
        "allowed_governance_operations",
        "allowed_later_execution_operations",
        "required_singleton_counts",
    )
    if any(request.get(field) != policy[field] for field in exact_fields):
        return reject
    if any(request.get(field) is not True for field in policy["required_true_fields"]):
        return reject
    if any(request.get(field) is not False for field in policy["required_false_fields"]):
        return reject
    return policy["accept_decision"]


class F464ReleaseRootOwnerRemediationGovernanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()
        cls.request = canonical_request(cls.policy)
        cls.source = SOURCE_PATH.read_text(encoding="utf-8")

    def decide(self, **changes: Any) -> str:
        request = copy.deepcopy(self.request)
        request.update(changes)
        return evaluate(self.policy, request)

    def drift_metadata(self, side: str, field: str, value: Any) -> str:
        request = copy.deepcopy(self.request)
        request[side][field] = value
        return evaluate(self.policy, request)

    def test_happy_path_contract_accepts(self) -> None:
        self.assertEqual(self.decide(), "ACCEPT")
        self.assertEqual(
            self.policy["runtime_gate_decision_for_governance"], "ACCEPT"
        )
        self.assertEqual(self.policy["default_execution_decision"], "REJECT")
        self.assertFalse(
            self.policy["approval_reconfirmation_required"]
        )
        self.assertRegex(canonical_sha256(self.policy), r"^[0-9a-f]{64}$")
        self.assertEqual(
            file_sha256(SOURCE_PATH),
            self.policy["required_helper_identity"]["source_sha256"],
        )

    def test_wrong_uid_gid_mode_inode_acl_xattr_fail_closed(self) -> None:
        cases = (
            ("release_root_before", "uid", 502),
            ("release_root_before", "gid", 0),
            ("release_root_before", "mode", "0755"),
            ("release_root_before", "inode", 307341898),
            ("release_root_before", "extended_acl_entry_count", 1),
            ("release_root_before", "xattr_names", []),
            ("release_root_before", "xattr_fingerprint_sha256", "0" * 64),
            ("release_root_after", "uid", 501),
            ("release_root_after", "gid", 0),
            ("release_root_after", "mode", "0500"),
            ("release_root_after", "inode", 307341898),
            ("release_root_after", "extended_acl_entry_count", 1),
            ("release_root_after", "xattr_fingerprint_sha256", "f" * 64),
        )
        for side, field, value in cases:
            with self.subTest(side=side, field=field):
                self.assertEqual(
                    self.drift_metadata(side, field, value), "REJECT"
                )

    def test_symlink_and_every_required_boolean_fail_closed(self) -> None:
        self.assertIn(
            "release_root_symlink_detected",
            self.policy["required_false_fields"],
        )
        for field in self.policy["required_true_fields"]:
            self.assertEqual(self.decide(**{field: False}), "REJECT", field)
        for field in self.policy["required_false_fields"]:
            self.assertEqual(self.decide(**{field: True}), "REJECT", field)

    def test_recursive_path_arg_shell_chmod_group_change_are_forbidden(self) -> None:
        forbidden = self.policy["forbidden_helper_functions"]
        for function in forbidden:
            self.assertIsNone(
                re.search(rf"\b{re.escape(function)}\s*\(", self.source),
                function,
            )
        self.assertIn("if (argc != 1) return EXIT_USAGE;", self.source)
        self.assertIn("(void)argv;", self.source)
        self.assertNotIn("argv[", self.source)
        self.assertNotIn("-R", self.source)
        self.assertEqual(self.source.count("fchown(root_fd, kAfterUid, (gid_t)-1)"), 1)
        self.assertNotRegex(self.source, r"\bfchmod\s*\(")
        self.assertNotRegex(self.source, r"\bchmod\s*\(")

    def test_dirfd_nofollow_inode_acl_xattr_postconditions_are_static(self) -> None:
        required_fragments = (
            "open(kReleaseParent, O_RDONLY | O_DIRECTORY | O_NOFOLLOW",
            "openat(",
            "AT_SYMLINK_NOFOLLOW",
            "F_GETPATH",
            "kExpectedDevice",
            "kExpectedInode",
            "no_extended_acl(root_fd)",
            "exact_xattr_fingerprint(root_fd, xattr_before)",
            "exact_xattr_fingerprint(root_fd, xattr_after)",
            "strcmp(xattr_after, xattr_before) == 0",
            "after.st_gid == before.st_gid",
            "(after.st_mode & 07777) == (before.st_mode & 07777)",
            "after.st_ino == before.st_ino",
        )
        for fragment in required_fragments:
            self.assertIn(fragment, self.source)

    def test_second_call_and_retry_are_forbidden(self) -> None:
        self.assertEqual(self.policy["release_root_before"]["uid"], 501)
        self.assertEqual(self.policy["release_root_after"]["uid"], 0)
        self.assertIn(
            "exact_metadata(&before, kBeforeUid)", self.source
        )
        self.assertEqual(
            self.policy["required_singleton_counts"][
                "later_execution_max_helper_invocation_count"
            ],
            1,
        )
        self.assertEqual(
            self.policy["required_singleton_counts"]["retry_count"], 0
        )
        self.assertTrue(
            self.policy["remediation_checkpoint_contract"]["forbids_retry"]
        )

    def test_services_db_web_business_and_f464_install_remain_forbidden(self) -> None:
        forbidden = set(self.policy["required_false_fields"])
        expected = {
            "service_requested",
            "plist_requested",
            "database_connection_requested",
            "database_write_requested",
            "runner_requested",
            "canary_requested",
            "n1_n5_requested",
            "proposal_requested",
            "order_requested",
            "trade_requested",
            "position_requested",
            "cash_requested",
            "web_mutation_requested",
            "evaluator_requested",
            "virtual_executor_mutation_requested",
            "release_install_requested",
        }
        self.assertTrue(expected.issubset(forbidden))
        for key in (
            "service_operations_allowed",
            "database_operations_allowed",
            "web_operations_allowed",
            "evaluator_operations_allowed",
            "virtual_executor_operations_allowed",
            "n1_n5_business_operations_allowed",
        ):
            self.assertFalse(self.policy[key], key)

    def test_exact_three_file_allowlist_and_no_helper_call_from_tests(self) -> None:
        self.assertEqual(
            self.policy["allowed_governance_files"],
            [
                "docs/EXECUTION_KERNEL.md",
                "scripts/n6_f464_release_root_owner_remediation_v1.c",
                "tests/test_n6_f464_release_root_owner_remediation_governance.py",
            ],
        )
        self.assertEqual(
            self.policy["required_singleton_counts"][
                "governance_modified_file_count"
            ],
            3,
        )
        test_source = TEST_PATH.read_text(encoding="utf-8")
        process_module = "sub" + "process"
        system_call = "os." + "system("
        self.assertNotRegex(
            test_source, rf"(?m)^(from|import)\s+{process_module}\b"
        )
        self.assertNotIn(system_call, test_source)


if __name__ == "__main__":
    unittest.main()
