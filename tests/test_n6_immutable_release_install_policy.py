from __future__ import annotations

import copy
import hashlib
import json
import re
import struct
import unittest
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "n6_immutable_release_install_bounded_v1"
VALIDATOR_RECOVERY_POLICY_ID = (
    "n6_immutable_release_install_pre_rename_validator_recovery_v1"
)
PREFLIGHT_GIT_VIOLATION_RECOVERY_POLICY_ID = (
    "n6_immutable_release_install_preflight_git_violation_recovery_v1"
)
RETRY_POLICY_ID = "n6_immutable_release_install_eacces_retry_v1"
HOST_REMEDIATION_POLICY_ID = "n6_immutable_release_install_host_eacces_remediation_v1"
PRIVILEGED_INSTALL_POLICY_ID = "n6_immutable_release_privileged_atomic_install_v1"
MATERIALIZE_INSTALL_POLICY_ID = "n6_immutable_release_privileged_materialize_and_install_v1"
F67_MATERIALIZE_INSTALL_POLICY_ID = (
    "n6_immutable_release_privileged_materialize_and_install_f67_v1"
)

FROZEN_AA6_COMMIT = "aa6d19c169df3837b3115d975587686cc726b87b"
FROZEN_AA6_PARENT = "081bd74ae07c327452b2a1fc67bf7df3d73a4b6c"
FROZEN_AA6_TREE = "e8c5b1b883304f5499c1ff399165cb1c122a38c4"
FROZEN_AA6_PATCH_SHA = "1c20e1ca674bdf4576c82c3f2f4a39a8103f61d556f69b260f7e2a0f0c1cf708"
FROZEN_AA6_ARCHIVE_SHA = "40e3756f37f64a8b4e31ff259814b0240fe77bff8b379e4f9428aac307ebd841"
FROZEN_AA6_MANIFEST_SHA = "8acb70c772a3472819bd78304808e23658e954a3ae000020ba41cd9b33d7c341"
FROZEN_AA6_FILESYSTEM_SHA = "4beb0a988a2798473641d260ef09dc6bcd6e1aa8ac8fefe15599464508be11b3"
FROZEN_AA6_RELEASE_CONTENT_SHA = (
    "ee7df8ca7ead0633679f9d8b6c3046788f27f99b1a5c3929db9dc4105f1b4881"
)
FROZEN_AA6_RELEASE_ATTESTATION_SHA = (
    "efdeb2e4ba8244041005d402bd153b7df4de5d0803f5f026aa3e1c2f797fbdee"
)
FROZEN_BLOCKED_ATTESTATION_SHA = (
    "9594308305ff68a217d51f6071ded07e4c01892a3ed91227abea9f1586b2edf1"
)
FROZEN_BLOCKED_SIDECAR_SHA = (
    "a5529027670687327180be5384f13aea6cd26c20a433950562f8767693cd6945"
)
FROZEN_PRESERVED_STAGING_METADATA_SHA = (
    "72c6f1cae5394888bb883f78177c4bd848d9f18adb56ab155228397d958950c5"
)
FROZEN_PRESERVED_STAGING_XATTR_SHA = (
    "d712c33be3c78b7b80b82428a9ce6a3b6d880b1ec4bd1aed71b951b3536ab7fa"
)
FROZEN_VALIDATOR_EXECUTABLE_SHA = (
    "a4891287e560225be676dc3eb9e32f058ab55a705fc6ff0d388b6e75802d63cc"
)
FROZEN_VALIDATOR_PROTOCOL_SHA = (
    "d46af344eab78629252d1dc35b3a16d0c5cf129aff35d8ce0d724626293709b4"
)
FROZEN_XATTR_RAW_VALUE_SHA = (
    "29056cd65452fb0f6214e35e97e773d512c87f3bdd3577f2cc445b082ae19487"
)
FROZEN_XATTR_CANONICAL_FINGERPRINT_SHA = (
    "92d525c921324d35d82bc503142c5fe3bfab37fd09b199788053903013baa7ee"
)
FROZEN_RELEASE_CONTENT_PATH_SET_SHA = (
    "ed3e7016cc2e41ed8fee7363be4b89ea8f14ab959987447cf7cc3b3dd8741cdb"
)
FROZEN_RELEASE_CLOSURE_PATH_SET_SHA = (
    "b77ce626022f2ade199fb1f46fc62a6a600bb81b91d8843692d69d18cb279ea6"
)
FROZEN_AA6_TARGET_NAME = f"20260728_002901__{FROZEN_AA6_COMMIT}"
FROZEN_AA6_STAGING_V1_NAME = (
    f".20260728_002901__{FROZEN_AA6_COMMIT}.install-staging-v1"
)
FROZEN_AA6_STAGING_V2_NAME = (
    f".20260728_002901__{FROZEN_AA6_COMMIT}.install-staging-v2"
)

FROZEN_D85_ARCHIVE_PATH = "/tmp/n6_release_d85_20260726/source.tar"
FROZEN_D85_MANIFEST_PATH = "/tmp/n6_release_d85_20260726/release-manifest.json"
FROZEN_D85_COMMIT = "d85df6328bde223e912dabc3bd65e16df984aa45"
FROZEN_D85_TREE = "d6d5ae1d68a1255ea9f05d8e7ce40a837a572ea1"
FROZEN_D85_ARCHIVE_SHA = "49fb8729e6648f2b15e20d699d5f0f10a97bc1cbd5935cc31f5bb90a9de859ac"
FROZEN_D85_MANIFEST_SHA = "df698d8208977cd5a1d24c144260eb6ef0604f39be1f33f0b08af387027b6106"
FROZEN_D85_FILESYSTEM_SHA = "5f600a1e1fbb7905968312387c0fc17acee09968a6dfb7d238a22d8d49152ad4"
FROZEN_D85_ARCHIVE_FIXTURE = {
    "pax_global_headers": 1,
    "pax_extended_headers": 108,
    "pax_global_key": "comment",
    "pax_extended_key": "path",
    "input_file_modes": {"0644": 0, "0664": 6236, "0755": 0, "0775": 4},
    "input_directory_modes": {"0755": 0, "0775": 45},
    "sealed_file_modes": {"0444": 6236, "0555": 4},
    "sealed_directory_modes": {"0555": 45},
}

FROZEN_F67_ARCHIVE_PATH = "/tmp/n6_release_f67_20260727/source.tar"
FROZEN_F67_MANIFEST_PATH = "/tmp/n6_release_f67_20260727/release-manifest.json"
FROZEN_F67_HELPER_PATH = (
    "/usr/local/libexec/ashare-v3/n6-immutable-release-materializer-f67"
)
FROZEN_F67_COMMIT = "f67be0f538f7fdc0fe413ac98bbdc5b32a29661a"
FROZEN_F67_TREE = "997e12766f806cedf046484463d19318fb9e4a69"
FROZEN_F67_ARCHIVE_SHA = "88ea81e1fda5b1f4b6864c959e91de798bf95272184877c36b32cfd77d12fcd5"
FROZEN_F67_GIT_LS_TREE_SHA = "e49924357270ac612e6c50da510f10a4bdd069bc983adca6928e5948342745e1"
FROZEN_F67_MANIFEST_SHA = "4976e9510da6792274e63ce168acecb3ef4e16b893547b2b5fb813953f97c494"
FROZEN_F67_FILESYSTEM_SHA = "ae6aed7d6fd3fa17ecb8362b3b28c1ed95c0113c05ac7841842797aeb4488004"
FROZEN_F67_BUNDLE_PAYLOAD_SHA = (
    "36d1a1e874583316d63be36d0135ea07fd88dbfa5902baf63d3001f29736a9cd"
)
FROZEN_F67_BUNDLE_FILE_SHA = (
    "e9b8fa599a6af3d90cc7f8ba38c3299a0fa25c18ae0539a95b8ca9f218842789"
)
FROZEN_F67_ARCHIVE_FIXTURE = {
    "pax_global_headers": 1,
    "pax_extended_headers": 108,
    "pax_global_key": "comment",
    "pax_extended_key": "path",
    "input_file_modes": {"0644": 0, "0664": 6236, "0755": 0, "0775": 4},
    "input_directory_modes": {"0755": 0, "0775": 45},
    "sealed_file_modes": {"0444": 6236, "0555": 4},
    "sealed_directory_modes": {"0555": 45},
}


def reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AssertionError(f"duplicate policy JSON key: {key}")
        result[key] = value
    return result


def load_policy(policy_id: str = POLICY_ID) -> dict[str, Any]:
    text = (ROOT / "docs" / "EXECUTION_KERNEL.md").read_text(encoding="utf-8")
    begin = f"<!-- policy:{policy_id}:begin -->"
    end = f"<!-- policy:{policy_id}:end -->"
    if text.count(begin) != 1 or text.count(end) != 1:
        raise AssertionError("policy must contain exactly one begin/end marker pair")
    start = text.index(begin) + len(begin)
    stop = text.index(end, start)
    block = text[start:stop].strip()
    match = re.fullmatch(r"```json\s*(\{.*\})\s*```", block, re.DOTALL)
    if match is None:
        raise AssertionError("policy must contain one JSON fence")
    return json.loads(
        match.group(1),
        object_pairs_hook=reject_duplicate_json_keys,
    )


def canonical(policy: dict[str, Any], policy_id: str = POLICY_ID) -> dict[str, Any]:
    root = policy["release_root"]
    req: dict[str, Any] = {
        "policy_id": policy_id,
        "layer_role": "runtime_control",
        "scope_mode": policy["scope_mode"],
        "phase_mode": policy["phase_mode"],
        "target_release_path": f"{root}/20260724_120000__" + "a" * 40,
        "staging_release_path": f"{root}/.staging-20260724-120000-" + "a" * 12,
        "declared_mutation_resources": list(policy["allowed_mutation_resources"]),
        "declared_operations": list(policy["allowed_operations"]),
    }
    if "prior_failed_staging_path" in policy["required_resource_fields"]:
        req["prior_failed_staging_path"] = f"{root}/.staging-prior-" + "b" * 12
    if "orphaned_staging_path" in policy["required_resource_fields"]:
        req["orphaned_staging_path"] = f"{root}/.staging-orphaned-" + "c" * 12
        req["host_eacces_trace_path"] = "/Users/chuanfuchen/.codex/sessions/host-eacces.jsonl"
    if "helper_path" in policy["required_resource_fields"]:
        req["helper_path"] = "/usr/local/libexec/ashare-v3/n6-immutable-release-installer"
    if "materializer_helper_path" in policy["required_resource_fields"]:
        req["archive_path"] = policy["frozen_archive_path"]
        req["manifest_path"] = policy["frozen_manifest_path"]
        req["materializer_helper_path"] = policy.get(
            "frozen_helper_path",
            "/usr/local/libexec/ashare-v3/n6-immutable-release-materializer",
        )
    req.update(policy["required_singleton_counts"])
    req.update(policy.get("required_exact_values", {}))
    req.update({name: True for name in policy["required_true_fields"]})
    req.update({name: False for name in policy["required_false_fields"]})
    for name, pattern in policy["required_hash_fields"].items():
        literal = pattern.removeprefix("^").removesuffix("$")
        if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", literal):
            req[name] = literal
        else:
            req[name] = "a" * (40 if "{40}" in pattern else 64)
    for left, right in policy.get("required_equal_field_pairs", []):
        req[right] = req[left]
    if "materializer_helper_path" in policy["required_resource_fields"]:
        source_commit = req["source_commit"]
        req["target_release_path"] = f"{root}/20260726_120000__{source_commit}"
        req["staging_release_path"] = f"{root}/.staging__20260726_120000__{source_commit}"
    return req


def evaluate(policy: dict[str, Any], request: dict[str, Any]) -> str:
    reject = policy["default_runtime_execution_decision"]
    if policy.get("reject_unknown_request_fields"):
        allowed_fields = {
            "policy_id",
            "layer_role",
            "scope_mode",
            "phase_mode",
            "target_release_path",
            "staging_release_path",
            "declared_mutation_resources",
            "declared_operations",
        }
        allowed_fields.update(policy["required_resource_fields"])
        allowed_fields.update(policy["required_hash_fields"])
        allowed_fields.update(policy["required_singleton_counts"])
        allowed_fields.update(policy.get("required_exact_values", {}))
        allowed_fields.update(policy["required_true_fields"])
        allowed_fields.update(policy["required_false_fields"])
        if set(request) != allowed_fields:
            return reject
    for field in ("policy_id", "layer_role", "scope_mode", "phase_mode"):
        if request.get(field) != policy[field]:
            return reject
    root = Path(policy["release_root"])
    target = Path(request.get("target_release_path", ""))
    staging = Path(request.get("staging_release_path", ""))
    if target.parent != root or staging.parent != root:
        return reject
    if target == staging or target.name.startswith(".staging"):
        return reject
    if not re.fullmatch(r"[0-9]{8}_[0-9]{6}__[0-9a-f]{40}", target.name):
        return reject
    if "prior_failed_staging_path" in policy["required_resource_fields"]:
        prior = Path(request.get("prior_failed_staging_path", ""))
        if prior.parent != root or prior == staging or prior == target:
            return reject
    if "preserved_failed_staging_path" in policy["required_resource_fields"]:
        for field in policy["required_resource_fields"]:
            if not isinstance(request.get(field), str) or not request[field]:
                return reject
        preserved = Path(request["preserved_failed_staging_path"])
        capability = Path(request["validator_capability_attestation_path"])
        validator = Path(request["validator_executable_path"])
        if preserved.parent != root or preserved == staging or preserved == target:
            return reject
        if not capability.is_absolute() or capability.suffix != ".json":
            return reject
        if not validator.is_absolute():
            return reject
    if "orphaned_staging_path" in policy["required_resource_fields"]:
        orphaned = Path(request.get("orphaned_staging_path", ""))
        if orphaned.parent != root or orphaned == staging or orphaned == target:
            return reject
        if not str(request.get("host_eacces_trace_path", "")).endswith(".jsonl"):
            return reject
    if "helper_path" in policy["required_resource_fields"]:
        helper = str(request.get("helper_path", ""))
        if helper != "/usr/local/libexec/ashare-v3/n6-immutable-release-installer":
            return reject
    if "materializer_helper_path" in policy["required_resource_fields"]:
        if request.get("archive_path") != policy["frozen_archive_path"]:
            return reject
        if request.get("manifest_path") != policy["frozen_manifest_path"]:
            return reject
        expected_helper = policy.get(
            "frozen_helper_path",
            "/usr/local/libexec/ashare-v3/n6-immutable-release-materializer",
        )
        if request.get("materializer_helper_path") != expected_helper:
            return reject
        if not staging.name.startswith(".staging__"):
            return reject
        if not target.name.endswith(f"__{request.get('source_commit', '')}"):
            return reject
    for name, pattern in policy["required_hash_fields"].items():
        if not isinstance(request.get(name), str) or not re.fullmatch(pattern, request[name]):
            return reject
    for left, right in policy.get("required_equal_field_pairs", []):
        if request.get(left) != request.get(right):
            return reject
    for name, expected in policy["required_singleton_counts"].items():
        if request.get(name) != expected:
            return reject
    for name, expected in policy.get("required_exact_values", {}).items():
        if request.get(name) != expected:
            return reject
    if any(request.get(name) is not True for name in policy["required_true_fields"]):
        return reject
    if any(request.get(name) is not False for name in policy["required_false_fields"]):
        return reject
    if request.get("declared_mutation_resources") != policy["allowed_mutation_resources"]:
        return reject
    if request.get("declared_operations") != policy["allowed_operations"]:
        return reject
    return policy["accept_decision"]


def normalize_xattr_hex_stdout(stdout: str) -> bytes:
    if re.search(r"[^0-9A-Fa-f \t\r\n\f\v]", stdout):
        raise ValueError("xattr hex stdout contains a non-hex token")
    compact = re.sub(r"[ \t\r\n\f\v]", "", stdout)
    if len(compact) % 2:
        raise ValueError("xattr hex stdout contains an odd nibble count")
    return bytes.fromhex(compact)


def parse_xattr_names_stdout(stdout: str) -> list[bytes]:
    if not stdout.endswith("\n") or "\r" in stdout or "\x00" in stdout:
        raise ValueError("xattr name stdout framing is invalid")
    names = stdout[:-1].split("\n")
    if not names or any(not name for name in names):
        raise ValueError("xattr name stdout contains an empty record")
    return [name.encode("utf-8") for name in names]


def canonical_xattr_fingerprint(
    records: list[tuple[bytes, bytes, bytes]],
) -> str:
    digest = hashlib.sha256()
    for path, name, raw_value in sorted(records, key=lambda record: record[:2]):
        for value in (path, name, raw_value):
            digest.update(struct.pack(">Q", len(value)))
            digest.update(value)
    return digest.hexdigest()


def canonical_path_set_fingerprint(paths: set[bytes]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(struct.pack(">Q", len(path)))
        digest.update(path)
    return digest.hexdigest()


class ImmutableReleaseInstallPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()
        cls.request = canonical(cls.policy)

    def decide(self, **changes: Any) -> str:
        req = copy.deepcopy(self.request)
        req.update(changes)
        return evaluate(self.policy, req)

    def test_complete_artifact_install_accepts(self) -> None:
        self.assertEqual(self.decide(), "ACCEPT")
        self.assertEqual(self.policy["runtime_gate_decision"], "ACCEPT")

    def test_default_runtime_and_missing_authorization_reject(self) -> None:
        self.assertEqual(self.policy["default_runtime_execution_decision"], "REJECT")
        self.assertEqual(self.decide(explicit_user_authorization_current_request=False), "REJECT")

    def test_target_must_be_new_single_direct_child(self) -> None:
        for value in (True,):
            self.assertEqual(self.decide(target_release_exists_before_install=value), "REJECT")
        self.assertEqual(self.decide(target_release_count=2), "REJECT")
        self.assertEqual(self.decide(target_release_path="/tmp/target"), "REJECT")

    def test_hash_and_attestation_drift_reject(self) -> None:
        self.assertEqual(self.decide(target_hash_drift=True), "REJECT")
        self.assertEqual(self.decide(attestation_sha256="b" * 64), "ACCEPT")
        self.assertEqual(self.decide(archive_sha256="bad"), "REJECT")

    def test_staging_atomicity_and_retry_reject(self) -> None:
        self.assertEqual(self.decide(staging_path_is_unique=False), "REJECT")
        self.assertEqual(self.decide(staging_outside_release_root=True), "REJECT")
        self.assertEqual(self.decide(non_atomic_copy_into_final_path=True), "REJECT")
        self.assertEqual(self.decide(retry_count=1), "REJECT")

    def test_release_root_owner_write_window_is_exact_and_fail_closed(self) -> None:
        self.assertEqual(self.policy["release_root_mode"], "0555")
        self.assertEqual(self.policy["temporary_release_root_mode"], "0755")
        self.assertEqual(self.decide(release_root_before_mode_0555_verified=False), "REJECT")
        self.assertEqual(self.decide(release_root_owner_group_acl_xattr_frozen=False), "REJECT")
        self.assertEqual(self.decide(temporary_release_root_mode_0755_owner_only_verified=False), "REJECT")
        self.assertEqual(self.decide(release_root_after_mode_0555_verified=False), "REJECT")
        self.assertEqual(self.decide(failure_restores_release_root_mode_defined=False), "REJECT")
        self.assertEqual(self.decide(release_root_owner_write_enable_count=2), "REJECT")
        self.assertEqual(self.decide(release_root_mode_restore_count=0), "REJECT")
        self.assertEqual(self.decide(release_root_left_writable=True), "REJECT")
        self.assertEqual(self.decide(release_root_owner_group_acl_xattr_changed=True), "REJECT")
        self.assertEqual(self.decide(release_root_group_or_other_write_enabled=True), "REJECT")
        self.assertEqual(self.decide(multiple_release_root_mode_changes=True), "REJECT")

    def test_existing_release_and_cleanup_are_fail_closed(self) -> None:
        self.assertEqual(self.decide(existing_release_modified=True), "REJECT")
        self.assertEqual(self.decide(existing_release_delete_requested=True), "REJECT")
        self.assertEqual(self.decide(failure_cleanup_new_paths_only_defined=False), "REJECT")

    def test_service_database_evaluator_and_business_paths_reject(self) -> None:
        for field in (
            "launch_agent_touched", "service_restarted", "launchctl_bootout_requested",
            "database_connection_requested", "database_write_requested",
            "evaluator_requested", "virtual_executor_requested", "migration_requested",
            "selection_projection_change_touched", "proposal_touched", "order_touched",
            "trade_touched", "position_touched", "cash_touched",
            "n1_n6_business_mutation_requested",
        ):
            self.assertEqual(self.decide(**{field: True}), "REJECT", field)

    def test_concurrent_drift_and_multiple_targets_reject(self) -> None:
        self.assertEqual(self.decide(concurrent_runtime_change=True), "REJECT")
        self.assertEqual(self.decide(multiple_targets_requested=True), "REJECT")


class ImmutableReleasePreRenameValidatorRecoveryPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy(VALIDATOR_RECOVERY_POLICY_ID)
        cls.request = canonical(cls.policy, VALIDATOR_RECOVERY_POLICY_ID)

    def decide(self, **changes: Any) -> str:
        req = copy.deepcopy(self.request)
        req.update(changes)
        return evaluate(self.policy, req)

    def test_exact_frozen_recovery_contract_accepts(self) -> None:
        self.assertEqual(self.decide(), "ACCEPT")
        self.assertEqual(self.policy["runtime_gate_decision"], "ACCEPT")
        self.assertEqual(self.policy["default_runtime_execution_decision"], "REJECT")
        self.assertEqual(
            self.policy["scope_mode"],
            "single_frozen_aa6d19c_pre_rename_validator_recovery",
        )
        self.assertEqual(self.request["source_commit"], FROZEN_AA6_COMMIT)
        self.assertEqual(self.request["source_parent"], FROZEN_AA6_PARENT)
        self.assertEqual(self.request["source_tree"], FROZEN_AA6_TREE)

    def test_blocked_attestation_and_failure_shape_are_exact(self) -> None:
        exact = self.policy["required_exact_values"]
        self.assertEqual(
            self.request["blocked_install_attestation_sha256"],
            FROZEN_BLOCKED_ATTESTATION_SHA,
        )
        self.assertEqual(
            self.request["blocked_install_attestation_sidecar_sha256"],
            FROZEN_BLOCKED_SIDECAR_SHA,
        )
        self.assertEqual(
            self.decide(blocked_install_attestation_sha256="b" * 64),
            "REJECT",
        )
        self.assertEqual(
            self.decide(blocked_install_attestation_sidecar_sha256="b" * 64),
            "REJECT",
        )
        for field, value in (
            ("blocked_install_attestation_path", "/tmp/blocked.json"),
            ("blocked_install_attestation_sidecar_path", "/tmp/blocked.sha256"),
            ("prior_failure_status", "BLOCKED_OTHER"),
            ("prior_failure_stage", "atomic_rename"),
            ("prior_failure_type", "eacces"),
            ("prior_failure_exception", "OSError"),
            ("prior_failure_message", "other"),
            ("prior_target_absent", False),
            ("prior_release_root_mode_after", "0755"),
        ):
            self.assertIn(field, exact)
            self.assertEqual(self.decide(**{field: value}), "REJECT", field)
        self.assertEqual(self.decide(prior_atomic_rename_attempt_count=1), "REJECT")
        self.assertEqual(self.decide(prior_fallback_attempt_count=1), "REJECT")
        self.assertEqual(self.decide(prior_retry_attempt_count=1), "REJECT")
        self.assertEqual(self.decide(prior_cleanup_attempt_count=1), "REJECT")

    def test_source_identity_and_artifact_hashes_are_exact(self) -> None:
        expected = {
            "source_commit": FROZEN_AA6_COMMIT,
            "source_parent": FROZEN_AA6_PARENT,
            "source_tree": FROZEN_AA6_TREE,
            "source_patch_sha256": FROZEN_AA6_PATCH_SHA,
            "archive_sha256": FROZEN_AA6_ARCHIVE_SHA,
            "manifest_sha256": FROZEN_AA6_MANIFEST_SHA,
            "filesystem_validation_sha256": FROZEN_AA6_FILESYSTEM_SHA,
            "release_content_manifest_sha256": FROZEN_AA6_RELEASE_CONTENT_SHA,
            "attestation_sha256": FROZEN_AA6_RELEASE_ATTESTATION_SHA,
        }
        for field, value in expected.items():
            self.assertEqual(self.request[field], value, field)
            replacement = ("b" if value[0] != "b" else "c") + value[1:]
            self.assertEqual(self.decide(**{field: replacement}), "REJECT", field)
        for field in (
            "source_archive_path",
            "source_manifest_path",
            "source_filesystem_validation_path",
            "source_release_content_manifest_path",
            "source_release_attestation_path",
        ):
            self.assertEqual(self.decide(**{field: f"/tmp/{field}"}), "REJECT", field)

    def test_preserved_staging_v1_is_exact_evidence_only(self) -> None:
        root = self.policy["release_root"]
        self.assertEqual(
            self.request["preserved_failed_staging_path"],
            f"{root}/{FROZEN_AA6_STAGING_V1_NAME}",
        )
        self.assertEqual(
            self.request["preserved_staging_metadata_contract_sha256"],
            FROZEN_PRESERVED_STAGING_METADATA_SHA,
        )
        self.assertEqual(
            self.request["preserved_staging_xattr_fingerprint_sha256"],
            FROZEN_PRESERVED_STAGING_XATTR_SHA,
        )
        self.assertEqual(
            self.decide(preserved_staging_metadata_contract_sha256="b" * 64),
            "REJECT",
        )
        self.assertEqual(
            self.decide(preserved_staging_xattr_fingerprint_sha256="b" * 64),
            "REJECT",
        )
        for field, value in (
            ("preserved_staging_device", 1),
            ("preserved_staging_inode", 1),
            ("preserved_staging_uid", 0),
            ("preserved_staging_gid", 0),
            ("preserved_staging_mode", "0755"),
            ("preserved_staging_file_count", 6242),
            ("preserved_staging_directory_count_including_root", 44),
            ("preserved_staging_file_mode_counts", "0444:6243"),
            ("preserved_staging_directory_mode_counts", "0555:44"),
            ("preserved_staging_provenance_xattr_entry_count", 6287),
            ("preserved_staging_other_xattr_entry_count", 1),
            ("preserved_staging_full_content_validation_completed", True),
        ):
            self.assertEqual(self.decide(**{field: value}), "REJECT", field)
        self.assertEqual(
            self.decide(
                preserved_failed_staging_path=self.request["staging_release_path"]
            ),
            "REJECT",
        )
        self.assertTrue(self.policy["preserved_staging_evidence_only"])
        self.assertFalse(self.policy["preserved_staging_cleanup_allowed"])

    def test_validator_capability_attestation_is_mandatory_and_hash_bound(self) -> None:
        self.assertEqual(
            self.request["validator_executable_path"],
            "/usr/bin/xattr",
        )
        self.assertEqual(
            self.request["validator_executable_sha256"],
            FROZEN_VALIDATOR_EXECUTABLE_SHA,
        )
        self.assertEqual(
            self.request["validator_protocol_sha256"],
            FROZEN_VALIDATOR_PROTOCOL_SHA,
        )
        self.assertEqual(self.request["validator_executable_device"], 16777232)
        self.assertEqual(
            self.request["validator_executable_inode"],
            1152921500312569043,
        )
        self.assertEqual(self.request["validator_executable_mode"], "0755")
        protocol_bytes = json.dumps(
            self.policy["validator_protocol_contract"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        self.assertEqual(
            hashlib.sha256(protocol_bytes).hexdigest(),
            FROZEN_VALIDATOR_PROTOCOL_SHA,
        )
        self.assertEqual(
            self.request["validator_protocol_canonicalization"],
            "json_sort_keys_compact_utf8_v1",
        )
        self.assertTrue(
            self.request["validator_capability_attestation_path"].endswith(
                "/validator-capability-attestation.json"
            )
        )
        self.assertTrue(
            self.request["validator_capability_attestation_sidecar_path"].endswith(
                "/validator-capability-attestation.sha256"
            )
        )
        self.assertEqual(
            self.request["validator_capability_artifact_file_mode"],
            "0444",
        )
        self.assertEqual(
            self.request["validator_capability_artifact_directory_mode"],
            "0555",
        )
        for field in (
            "validator_capability_artifact_paths_absent_before_recovery_verified",
            "validator_capability_artifact_exact_new_directories_verified",
            "validator_capability_attestation_path_absent_before_recovery_verified",
            "validator_capability_attestation_sidecar_path_absent_before_recovery_verified",
            "validator_capability_attestation_created_in_current_recovery_verified",
            "validator_capability_attestation_sidecar_created_in_current_recovery_verified",
            "validator_capability_probe_completed_before_attestation_write_verified",
            "validator_capability_attestation_sha_bound_verified",
            "validator_capability_attestation_hash_verified",
            "validator_capability_attestation_sidecar_binding_verified",
            "validator_capability_attestation_no_duplicate_keys_verified",
            "validator_capability_attestation_and_sidecar_frozen_before_root_write_verified",
            "validator_capability_attestation_and_sidecar_unchanged_after_recovery_verified",
            "validator_capability_artifacts_sealed_0444_directories_0555_before_root_write_verified",
            "validator_capability_failure_preserves_sealed_artifacts_before_stop_defined",
            "validator_executable_hash_verified",
            "validator_executable_identity_verified",
            "validator_protocol_hash_verified",
            "validator_lists_xattr_names_and_values_verified",
            "validator_fails_closed_on_unsupported_capability_verified",
            "validator_does_not_mutate_xattr_acl_mode_verified",
            "validator_capability_phase_completed_before_release_root_write_verified",
            "validator_capability_phase_completed_before_new_staging_creation_verified",
            "validator_capability_failure_stops_before_release_root_write_or_staging_creation_defined",
            "validator_capability_failure_finalizes_sealed_recovery_output_before_stop_defined",
        ):
            self.assertEqual(self.decide(**{field: False}), "REJECT", field)
        for field in (
            "validator_capability_attestation_sha256",
            "validator_capability_attestation_sidecar_recorded_sha256",
            "validator_executable_sha256",
            "validator_capability_attestation_embedded_executable_sha256",
            "validator_protocol_sha256",
            "validator_capability_attestation_embedded_protocol_sha256",
        ):
            self.assertEqual(self.decide(**{field: "bad"}), "REJECT", field)
        self.assertEqual(
            self.decide(validator_capability_attestation_sha256="b" * 64),
            "REJECT",
        )
        self.assertEqual(
            self.decide(
                validator_capability_attestation_sidecar_recorded_sha256="b" * 64
            ),
            "REJECT",
        )
        self.assertEqual(
            self.decide(
                validator_capability_attestation_embedded_executable_sha256="b" * 64
            ),
            "REJECT",
        )
        self.assertEqual(
            self.decide(
                validator_capability_attestation_embedded_protocol_sha256="b" * 64
            ),
            "REJECT",
        )
        self.assertEqual(
            self.decide(validator_executable_sha256="b" * 64),
            "REJECT",
        )
        self.assertEqual(
            self.decide(validator_protocol_sha256="b" * 64),
            "REJECT",
        )
        self.assertEqual(
            self.decide(validator_capability_attestation_path="/tmp/capability.json"),
            "REJECT",
        )
        self.assertEqual(
            self.decide(
                validator_capability_attestation_sidecar_path="/tmp/capability.sha256"
            ),
            "REJECT",
        )
        self.assertEqual(
            self.decide(validator_uses_missing_os_listxattr_api=True),
            "REJECT",
        )
        self.assertEqual(
            self.decide(validator_capability_artifact_directory_create_count=0),
            "REJECT",
        )
        self.assertEqual(
            self.decide(validator_capability_artifact_directory_create_count=3),
            "REJECT",
        )
        for field in (
            "validator_capability_generation_count",
            "validator_capability_probe_count",
            "validator_capability_attestation_write_count",
            "validator_capability_attestation_sidecar_write_count",
        ):
            self.assertEqual(self.decide(**{field: 0}), "REJECT", field)
            self.assertEqual(self.decide(**{field: 2}), "REJECT", field)

    def test_every_required_resource_is_present_and_exact(self) -> None:
        for field in self.policy["required_resource_fields"]:
            self.assertEqual(self.decide(**{field: ""}), "REJECT", field)

    def test_unknown_request_fields_are_rejected(self) -> None:
        self.assertTrue(self.policy["reject_unknown_request_fields"])
        for field in (
            "helper_shell_execution_requested",
            "arbitrary_external_write_requested",
            "delete_existing_release_via_unmodelled_path",
        ):
            self.assertEqual(self.decide(**{field: True}), "REJECT", field)

    def test_recovery_output_paths_and_hashes_are_exact_and_non_overwriting(
        self,
    ) -> None:
        output_directory = self.request["recovery_output_artifact_directory"]
        self.assertTrue(
            output_directory.endswith(
                f"/20260728_002901__{FROZEN_AA6_COMMIT}"
            )
        )
        for field, filename in (
            ("recovery_validation_artifact_path", "recovery-validation.json"),
            (
                "recovery_install_attestation_path",
                "recovery-install-attestation.json",
            ),
            (
                "recovery_install_attestation_sidecar_path",
                "recovery-install-attestation.sha256",
            ),
        ):
            self.assertEqual(
                self.request[field],
                f"{output_directory}/{filename}",
                field,
            )
            self.assertEqual(
                self.decide(**{field: f"/tmp/{filename}"}),
                "REJECT",
                field,
            )
        self.assertEqual(
            self.request["recovery_output_artifact_file_mode"],
            "0444",
        )
        self.assertEqual(
            self.request["recovery_output_artifact_directory_mode"],
            "0555",
        )
        self.assertEqual(
            self.request["recovery_output_artifact_temporary_directory_mode"],
            "0700",
        )
        self.assertEqual(
            self.request["recovery_output_file_create_flags"],
            "O_CREAT|O_EXCL|O_WRONLY|O_NOFOLLOW",
        )
        self.assertEqual(
            self.request["recovery_output_artifact_creation_stage"],
            "finalize_after_release_root_confirmed_0555_and_selected_recovery_outcome_branch_finalized",
        )
        self.assertEqual(
            self.request["recovery_output_failure_points_covered"],
            [
                "artifact_root_create",
                "artifact_directory_create",
                "recovery_validation_write",
                "recovery_install_attestation_write",
                "recovery_install_attestation_sidecar_write",
                "recovery_output_final_seal",
            ],
        )
        self.assertEqual(
            self.request["recovery_install_attestation_sha256"],
            self.request[
                "recovery_install_attestation_sidecar_recorded_sha256"
            ],
        )
        self.assertEqual(
            self.decide(recovery_install_attestation_sha256="b" * 64),
            "REJECT",
        )
        self.assertEqual(
            self.decide(
                recovery_install_attestation_sidecar_recorded_sha256="b" * 64
            ),
            "REJECT",
        )
        self.assertEqual(
            self.decide(recovery_validation_artifact_sha256="bad"),
            "REJECT",
        )
        for field in (
            "recovery_output_artifact_path_preexisted",
            "recovery_output_artifact_overwrite_requested",
            "recovery_output_artifact_or_sidecar_drift",
            "recovery_output_artifact_created_before_release_root_confirmed_0555_or_selected_recovery_outcome_branch_finalized",
            "nonexclusive_recovery_output_file_create_requested",
            "recovery_output_failure_cleanup_requested",
            "failure_returns_with_writable_or_unattested_recovery_output_artifact",
        ):
            self.assertEqual(self.decide(**{field: True}), "REJECT", field)

    def test_exclusive_rename_and_owner_group_contract_are_exact(self) -> None:
        exact = self.policy["required_exact_values"]
        self.assertEqual(exact["new_staging_expected_uid"], 501)
        self.assertEqual(exact["new_staging_expected_gid"], 20)
        self.assertEqual(exact["new_target_expected_uid"], 501)
        self.assertEqual(exact["new_target_expected_gid"], 20)
        self.assertEqual(exact["atomic_rename_primitive"], "renameatx_np")
        self.assertEqual(
            exact["atomic_rename_flags"],
            "RENAME_EXCL|RENAME_NOFOLLOW_ANY|RENAME_RESOLVE_BENEATH",
        )
        self.assertEqual(exact["atomic_rename_flag_mask_decimal"], 0x34)
        self.assertEqual(
            exact["atomic_rename_path_form"],
            "direct_child_basenames_only",
        )
        for field in (
            "ordinary_rename_requested",
            "rename_replace_or_overwrite_semantics_requested",
            "renameatx_np_missing_flag_or_fallback_requested",
            "renameatx_np_absolute_or_parent_traversal_path_requested",
            "new_staging_or_target_owner_group_drift",
        ):
            self.assertEqual(self.decide(**{field: True}), "REJECT", field)
        self.assertEqual(self.decide(renameatx_np_attempt_count=2), "REJECT")
        self.assertEqual(self.decide(ordinary_rename_attempt_count=1), "REJECT")
        self.assertEqual(self.decide(rename_fallback_count=1), "REJECT")
        operations = self.policy["allowed_operations"]
        self.assertNotIn(
            "atomic_rename_new_staging_v2_to_new_target",
            operations,
        )
        self.assertIn(
            "atomic_renameatx_np_excl_nofollow_beneath_new_staging_v2_to_new_target",
            operations,
        )

    def test_xattr_path_authority_reconciles_to_release_content_manifest(self) -> None:
        git_tree_manifest = Path(self.request["source_manifest_path"]).read_bytes()
        self.assertEqual(
            hashlib.sha256(git_tree_manifest).hexdigest(),
            FROZEN_AA6_MANIFEST_SHA,
        )
        self.assertEqual(git_tree_manifest.count(b"\x00"), 6254)

        manifest_path = Path(
            self.request["source_release_content_manifest_path"]
        )
        manifest_bytes = manifest_path.read_bytes()
        self.assertEqual(
            hashlib.sha256(manifest_bytes).hexdigest(),
            FROZEN_AA6_RELEASE_CONTENT_SHA,
        )
        self.assertNotIn(b"\r", manifest_bytes)
        self.assertNotIn(b"\x00", manifest_bytes)
        lines = manifest_bytes.split(b"\n")
        if lines and lines[-1] == b"":
            lines.pop()

        file_paths: set[bytes] = set()
        for line in lines:
            fields = line.split(b"\t")
            self.assertEqual(len(fields), 4)
            content_sha, mode, git_oid, path = fields
            self.assertRegex(content_sha, rb"^[0-9a-f]{64}$")
            self.assertIn(mode, {b"100644", b"100755"})
            self.assertRegex(git_oid, rb"^[0-9a-f]{40}$")
            self.assertTrue(path)
            path_text = path.decode("utf-8", "strict")
            posix_path = PurePosixPath(path_text)
            self.assertFalse(posix_path.is_absolute())
            self.assertNotIn("..", posix_path.parts)
            self.assertNotIn(".", posix_path.parts)
            self.assertEqual(posix_path.as_posix(), path_text)
            self.assertNotIn(path, file_paths)
            file_paths.add(path)

        self.assertEqual(len(file_paths), 6243)
        self.assertEqual(6254 - len(file_paths), 11)
        self.assertEqual(
            canonical_path_set_fingerprint(file_paths),
            FROZEN_RELEASE_CONTENT_PATH_SET_SHA,
        )

        directories = {b""}
        for path in file_paths:
            parent = PurePosixPath(path.decode("utf-8")).parent
            while str(parent) != ".":
                directories.add(str(parent).encode("utf-8"))
                parent = parent.parent
        closure = file_paths | directories
        self.assertEqual(len(directories), 45)
        self.assertEqual(len(closure), 6288)
        self.assertEqual(
            canonical_path_set_fingerprint(closure),
            FROZEN_RELEASE_CLOSURE_PATH_SET_SHA,
        )
        self.assertEqual(
            self.request["new_staging_xattr_path_source_file_count"],
            len(file_paths),
        )
        self.assertEqual(
            self.request["new_staging_xattr_path_source_file_set_sha256"],
            FROZEN_RELEASE_CONTENT_PATH_SET_SHA,
        )
        self.assertEqual(
            self.request[
                "new_staging_xattr_derived_directory_count_including_root"
            ],
            len(directories),
        )
        self.assertEqual(
            self.request["new_staging_xattr_closure_path_count"],
            len(closure),
        )
        self.assertEqual(
            self.request["new_staging_xattr_closure_path_set_sha256"],
            FROZEN_RELEASE_CLOSURE_PATH_SET_SHA,
        )

    def test_xattr_value_authority_and_canonical_fingerprint_are_exact(self) -> None:
        self.assertEqual(
            self.request["new_staging_expected_xattr_record_count"],
            6243 + 45,
        )
        self.assertEqual(
            self.request["new_staging_expected_xattr_name"],
            "com.apple.provenance",
        )
        self.assertEqual(
            self.request["new_staging_expected_other_xattr_record_count"],
            0,
        )
        self.assertEqual(
            self.request["new_staging_expected_xattr_raw_value_length"],
            11,
        )
        self.assertEqual(
            self.request["new_staging_expected_xattr_raw_value_sha256"],
            FROZEN_XATTR_RAW_VALUE_SHA,
        )
        self.assertEqual(
            hashlib.sha256(
                bytes.fromhex("0100006457bbc065b81880")
            ).hexdigest(),
            FROZEN_XATTR_RAW_VALUE_SHA,
        )
        self.assertEqual(
            self.request[
                "new_staging_expected_xattr_canonical_fingerprint_sha256"
            ],
            FROZEN_XATTR_CANONICAL_FINGERPRINT_SHA,
        )
        self.assertEqual(
            normalize_xattr_hex_stdout("01 00 00 64 57 BB C0 65 B8 18 80\n"),
            bytes.fromhex("0100006457bbc065b81880"),
        )
        self.assertEqual(
            normalize_xattr_hex_stdout("0100006457bbc065b81880"),
            bytes.fromhex("0100006457bbc065b81880"),
        )
        self.assertEqual(normalize_xattr_hex_stdout(" \n\t"), b"")
        for invalid in ("0", "0g", "00\u00a000"):
            with self.assertRaises(ValueError, msg=invalid):
                normalize_xattr_hex_stdout(invalid)
        self.assertEqual(
            parse_xattr_names_stdout("com.apple.provenance\n"),
            [b"com.apple.provenance"],
        )
        self.assertEqual(
            parse_xattr_names_stdout("name.one\nname.two\n"),
            [b"name.one", b"name.two"],
        )
        for invalid in ("", "name", "name\r\n", "name\n\n", "name\x00\n"):
            with self.assertRaises(ValueError, msg=repr(invalid)):
                parse_xattr_names_stdout(invalid)

        records = [
            (
                b"",
                b"com.apple.provenance",
                bytes.fromhex("0100006457bbc065b81880"),
            ),
            (b"a path", b"empty", b""),
            ("\u76ee\u5f55/\u503c".encode("utf-8"), b"binary", b"\x00\xff\n"),
        ]
        expected_fixture_sha = (
            "5ffb904b09f40beb0c6981bf624817ba68a7a6a209c3d24ce3eff725f93e6436"
        )
        self.assertEqual(
            canonical_xattr_fingerprint(records),
            expected_fixture_sha,
        )
        self.assertEqual(
            canonical_xattr_fingerprint(list(reversed(records))),
            expected_fixture_sha,
        )
        drifted = list(records)
        path, name, raw_value = drifted[2]
        drifted[2] = (path, name, raw_value + b"\x00")
        self.assertNotEqual(
            canonical_xattr_fingerprint(drifted),
            expected_fixture_sha,
        )
        self.assertEqual(
            self.decide(
                new_staging_expected_xattr_canonical_fingerprint_sha256=(
                    "b" * 64
                )
            ),
            "REJECT",
        )
        self.assertEqual(
            self.decide(new_staging_xattr_name_count_or_value_drift=True),
            "REJECT",
        )
        self.assertEqual(
            self.decide(new_staging_xattr_parser_ambiguity_or_loss=True),
            "REJECT",
        )

    def test_every_required_exact_value_is_fail_closed(self) -> None:
        for field, expected in self.policy["required_exact_values"].items():
            if isinstance(expected, bool):
                replacement = not expected
            elif isinstance(expected, int):
                replacement = expected + 1
            else:
                replacement = f"{expected}.drift"
            self.assertEqual(
                self.decide(**{field: replacement}),
                "REJECT",
                field,
            )

    def test_every_required_singleton_count_is_fail_closed(self) -> None:
        for field, expected in self.policy["required_singleton_counts"].items():
            self.assertEqual(
                self.decide(**{field: expected + 1}),
                "REJECT",
                field,
            )

    def test_policy_field_lists_are_unique_and_boolean_sets_are_disjoint(self) -> None:
        for field in (
            "required_resource_fields",
            "required_true_fields",
            "required_false_fields",
            "allowed_mutation_resources",
            "allowed_operations",
        ):
            values = self.policy[field]
            self.assertEqual(len(values), len(set(values)), field)
        self.assertFalse(
            set(self.policy["required_true_fields"])
            & set(self.policy["required_false_fields"])
        )

    def test_new_staging_v2_is_exact_fresh_unique_and_same_parent(self) -> None:
        root = self.policy["release_root"]
        self.assertEqual(
            self.request["target_release_path"],
            f"{root}/{FROZEN_AA6_TARGET_NAME}",
        )
        self.assertEqual(
            self.request["staging_release_path"],
            f"{root}/{FROZEN_AA6_STAGING_V2_NAME}",
        )
        for value in (
            f"{root}/{FROZEN_AA6_STAGING_V1_NAME}",
            f"{root}/.{FROZEN_AA6_TARGET_NAME}.install-staging-v3",
            "/tmp/staging-v2",
            self.request["target_release_path"],
        ):
            self.assertEqual(
                self.decide(staging_release_path=value),
                "REJECT",
                value,
            )
        self.assertEqual(self.decide(staging_path_is_new=False), "REJECT")
        self.assertEqual(self.decide(staging_preexisted=True), "REJECT")
        self.assertEqual(self.decide(target_release_exists_before_recovery=True), "REJECT")

    def test_exactly_one_recovery_window_and_atomic_promotion(self) -> None:
        for field, value in (
            ("recovery_attempt_count", 2),
            ("second_recovery_count", 1),
            ("rename_count", 2),
            ("release_root_owner_write_enable_count", 2),
            ("release_root_mode_restore_count", 0),
            ("retry_count", 1),
            ("policy_fallback_count", 1),
            ("preserved_staging_cleanup_count", 1),
        ):
            self.assertEqual(self.decide(**{field: value}), "REJECT", field)
        self.assertEqual(self.decide(second_recovery_requested=True), "REJECT")
        self.assertEqual(self.decide(automatic_retry_requested=True), "REJECT")
        self.assertEqual(self.decide(multiple_release_root_mode_changes=True), "REJECT")

    def test_capability_happens_before_and_failure_sealing_are_fail_closed(self) -> None:
        for field in (
            "release_root_write_before_validator_capability_pass",
            "staging_creation_before_validator_capability_pass",
            "target_postflight_or_attestation_before_release_root_restore",
            "failure_returns_with_writable_new_staging",
            "post_rename_failure_target_modified_or_deleted",
        ):
            self.assertEqual(self.decide(**{field: True}), "REJECT", field)
        for field in (
            "new_staging_failure_path_recursive_seal_0444_0555_defined",
            "new_staging_failure_path_identity_metadata_attestation_defined",
            "post_rename_failure_preserves_immutable_target_evidence_defined",
            "new_staging_contents_verified_before_rename",
            "target_contents_verified_after_rename",
        ):
            self.assertEqual(self.decide(**{field: False}), "REJECT", field)
        self.assertNotIn(
            "target_contents_verified_before_rename",
            self.policy["required_true_fields"],
        )

    def test_preserved_staging_cannot_be_mutated_or_cleaned(self) -> None:
        for field in (
            "preserved_staging_reused",
            "preserved_staging_modified",
            "preserved_staging_renamed",
            "preserved_staging_deleted",
            "preserved_staging_cleanup_requested",
            "preserved_staging_metadata_touched",
        ):
            self.assertEqual(self.decide(**{field: True}), "REJECT", field)

    def test_policy_fallback_is_forbidden(self) -> None:
        for field in (
            "policy_fallback_requested",
            "eacces_retry_policy_requested",
            "host_remediation_policy_requested",
            "privileged_helper_requested",
            "new_staging_cleanup_requested",
        ):
            self.assertEqual(self.decide(**{field: True}), "REJECT", field)
        self.assertFalse(self.policy["policy_fallback_allowed"])
        self.assertFalse(self.policy["second_recovery_allowed"])
        self.assertFalse(self.policy["new_staging_cleanup_allowed"])

    def test_runtime_database_and_business_paths_are_forbidden(self) -> None:
        for field in (
            "launch_agent_touched",
            "service_restarted",
            "launchctl_bootout_requested",
            "launchctl_bootstrap_requested",
            "port_operation_requested",
            "git_operation_requested",
            "test_execution_requested",
            "evaluator_requested",
            "virtual_executor_requested",
            "database_connection_requested",
            "database_write_requested",
            "migration_requested",
            "selection_projection_change_touched",
            "proposal_touched",
            "order_touched",
            "trade_touched",
            "position_touched",
            "cash_touched",
            "n1_n6_business_mutation_requested",
        ):
            self.assertEqual(self.decide(**{field: True}), "REJECT", field)

    def test_every_required_boolean_is_fail_closed(self) -> None:
        for field in self.policy["required_true_fields"]:
            self.assertEqual(self.decide(**{field: False}), "REJECT", field)
        for field in self.policy["required_false_fields"]:
            self.assertEqual(self.decide(**{field: True}), "REJECT", field)

    def test_allowed_scope_excludes_old_staging_cleanup_and_execution_now(self) -> None:
        self.assertFalse(
            self.policy["governance_definition_session_can_execute_policy"]
        )
        self.assertEqual(
            self.decide(current_request_is_policy_definition_gate=True),
            "REJECT",
        )
        self.assertTrue(
            self.request[
                "governance_definition_gate_separate_from_recovery_execution_verified"
            ]
        )
        declared = self.policy["allowed_mutation_resources"] + self.policy["allowed_operations"]
        self.assertFalse(any("preserved_staging" in item for item in declared))
        self.assertFalse(any("cleanup" in item for item in declared))
        self.assertFalse(any("fallback" in item for item in declared))
        self.assertIn(
            "validator_capability_artifact_root",
            self.policy["allowed_mutation_resources"],
        )
        self.assertIn(
            "validator_capability_artifact_directory",
            self.policy["allowed_mutation_resources"],
        )
        self.assertIn(
            "validator_capability_attestation_path",
            self.policy["allowed_mutation_resources"],
        )
        self.assertIn(
            "validator_capability_attestation_sidecar_path",
            self.policy["allowed_mutation_resources"],
        )
        for resource in (
            "recovery_output_artifact_root",
            "recovery_output_artifact_directory",
            "recovery_validation_artifact_path",
            "recovery_install_attestation_path",
            "recovery_install_attestation_sidecar_path",
        ):
            self.assertIn(
                resource,
                self.policy["allowed_mutation_resources"],
            )
        operations = self.policy["allowed_operations"]
        self.assertLess(
            operations.index("probe_readonly_xattr_name_and_value_capability"),
            operations.index(
                "generate_macos_xattr_validator_capability_attestation"
            ),
        )
        self.assertLess(
            operations.index(
                "generate_macos_xattr_validator_capability_attestation"
            ),
            operations.index(
                "hash_and_write_validator_capability_attestation_sidecar"
            ),
        )
        self.assertLess(
            operations.index(
                "hash_and_write_validator_capability_attestation_sidecar"
            ),
            operations.index(
                "seal_validator_capability_artifacts_0444_0555"
            ),
        )
        self.assertLess(
            operations.index(
                "seal_validator_capability_artifacts_0444_0555"
            ),
            operations.index(
                "verify_validator_capability_before_release_root_write"
            ),
        )
        self.assertLess(
            operations.index(
                "verify_validator_capability_before_release_root_write"
            ),
            operations.index("temporarily_enable_owner_write_on_release_root"),
        )
        self.assertLess(
            operations.index(
                "atomic_renameatx_np_excl_nofollow_beneath_new_staging_v2_to_new_target"
            ),
            operations.index("restore_release_root_mode_0555"),
        )
        self.assertLess(
            operations.index("restore_release_root_mode_0555"),
            operations.index("verify_new_target_after_atomic_rename"),
        )
        self.assertLess(
            operations.index("verify_new_target_after_atomic_rename"),
            operations.index(
                "create_exact_recovery_output_artifact_directories"
            ),
        )
        self.assertLess(
            operations.index(
                "attest_immutable_target_on_post_rename_failure"
            ),
            operations.index(
                "create_exact_recovery_output_artifact_directories"
            ),
        )
        self.assertLess(
            operations.index(
                "create_exact_recovery_output_artifact_directories"
            ),
            operations.index("write_exact_recovery_validation_artifact"),
        )
        self.assertLess(
            operations.index("write_exact_recovery_validation_artifact"),
            operations.index("write_exact_recovery_install_attestation"),
        )
        self.assertLess(
            operations.index("write_exact_recovery_install_attestation"),
            operations.index(
                "hash_and_write_recovery_install_attestation_sidecar"
            ),
        )
        self.assertLess(
            operations.index(
                "hash_and_write_recovery_install_attestation_sidecar"
            ),
            operations.index("seal_recovery_output_artifacts_0444_0555"),
        )
        self.assertIn(
            "seal_and_attest_incomplete_new_staging_v2_on_failure",
            operations,
        )
        self.assertIn(
            "seal_and_attest_partial_recovery_output_artifacts_on_failure",
            operations,
        )
        self.assertEqual(
            self.policy["allowed_mutation_resources"],
            self.request["declared_mutation_resources"],
        )
        self.assertEqual(
            self.policy["allowed_operations"],
            self.request["declared_operations"],
        )

    def test_governance_documents_name_the_policy(self) -> None:
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
            self.assertIn(VALIDATOR_RECOVERY_POLICY_ID, text, relative)


class ImmutableReleasePreflightGitViolationRecoveryPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy(PREFLIGHT_GIT_VIOLATION_RECOVERY_POLICY_ID)
        cls.request = canonical(
            cls.policy,
            PREFLIGHT_GIT_VIOLATION_RECOVERY_POLICY_ID,
        )

    def decide(self, **changes: Any) -> str:
        req = copy.deepcopy(self.request)
        req.update(changes)
        return evaluate(self.policy, req)

    def test_exact_frozen_procedural_recovery_contract_accepts(self) -> None:
        self.assertEqual(self.decide(), "ACCEPT")
        self.assertEqual(self.policy["runtime_gate_decision"], "ACCEPT")
        self.assertEqual(self.policy["default_runtime_execution_decision"], "REJECT")
        self.assertFalse(
            self.policy["governance_definition_session_can_execute_policy"]
        )

    def test_unique_raw_session_evidence_is_literal_bound(self) -> None:
        exact = self.policy["required_exact_values"]
        hashes = self.policy["required_hash_fields"]
        self.assertEqual(
            exact["session_trace_path"],
            "/Users/chuanfuchen/.codex/sessions/2026/07/27/"
            "rollout-2026-07-27T22-32-51-"
            "019fa3fe-2bec-72b1-92cb-2b9bcc29a0ba.jsonl",
        )
        self.assertEqual(exact["session_turn_start_line"], 3672)
        self.assertEqual(exact["session_turn_end_line_inclusive"], 3833)
        self.assertEqual(exact["session_turn_start_byte"], 21636363)
        self.assertEqual(exact["session_turn_end_byte_exclusive"], 21989026)
        self.assertEqual(exact["session_turn_segment_size_bytes"], 352663)
        self.assertEqual(
            hashes["session_turn_segment_sha256"],
            "^844c5ab3d98d8aa75fa1e9cb4931be9bfa709672efa4ca7661c768eace709877$",
        )
        self.assertEqual(
            hashes["session_prefix_through_turn_sha256"],
            "^f49976d6a867b7608f9621798c0306666e018d184b101f7080323188ac6d4149$",
        )
        self.assertEqual(
            exact["session_whole_file_sha_authority"],
            "forbidden_append_drifting",
        )

    def test_historical_git_was_read_only_and_every_mutation_was_zero(self) -> None:
        exact = self.policy["required_exact_values"]
        counts = self.policy["required_singleton_counts"]
        self.assertEqual(exact["historical_git_subcommands"], ["rev-parse", "diff", "show"])
        self.assertTrue(exact["historical_git_operations_read_only"])
        self.assertEqual(counts["historical_git_tool_call_count"], 1)
        self.assertEqual(counts["historical_git_subcommand_count"], 3)
        for field in (
            "historical_apply_patch_call_count",
            "prior_capability_artifact_create_attempt_count",
            "prior_recovery_artifact_create_attempt_count",
            "prior_release_root_mode_change_attempt_count",
            "prior_staging_v2_create_attempt_count",
            "prior_atomic_rename_attempt_count",
            "prior_target_create_attempt_count",
            "prior_cleanup_attempt_count",
            "prior_fallback_attempt_count",
            "prior_runtime_operation_attempt_count",
            "prior_database_operation_attempt_count",
            "prior_service_operation_attempt_count",
            "execution_git_operation_count",
            "execution_test_execution_count",
        ):
            self.assertEqual(counts[field], 0, field)

    def test_later_execution_rejects_git_tests_and_unbound_governance(self) -> None:
        self.assertFalse(self.policy["git_operations_allowed"])
        self.assertFalse(self.policy["test_execution_allowed"])
        self.assertEqual(self.decide(git_operation_requested=True), "REJECT")
        self.assertEqual(self.decide(test_execution_requested=True), "REJECT")
        self.assertEqual(
            self.decide(authorized_governance_agents_raw_sha256="b" * 64),
            "REJECT",
        )
        self.assertEqual(
            self.decide(
                authorized_governance_policy_block_raw_sha256="b" * 64
            ),
            "REJECT",
        )

    def test_pre_mutation_failure_and_filesystem_identity_are_exact(self) -> None:
        exact = self.policy["required_exact_values"]
        self.assertEqual(
            exact["prior_policy_id"],
            "n6_immutable_release_install_pre_rename_validator_recovery_v1",
        )
        self.assertEqual(exact["prior_failure_status"], "BLOCKED_PRE_MUTATION")
        self.assertEqual(
            exact["prior_failure_type"],
            "forbidden_read_only_git_preflight_operation",
        )
        self.assertEqual(
            (
                exact["release_root_device"],
                exact["release_root_inode"],
                exact["release_root_uid"],
                exact["release_root_gid"],
                exact["release_root_mode_before_recovery"],
            ),
            (16777232, 307341897, 501, 20, "0555"),
        )
        self.assertEqual(
            (
                exact["preserved_staging_device"],
                exact["preserved_staging_inode"],
                exact["preserved_staging_file_count"],
                exact["preserved_staging_directory_count_including_root"],
            ),
            (16777232, 322967321, 6243, 45),
        )

    def test_capability_first_fresh_staging_and_single_rename_are_mandatory(self) -> None:
        true_fields = set(self.policy["required_true_fields"])
        counts = self.policy["required_singleton_counts"]
        self.assertIn(
            "validator_capability_completed_before_root_write_or_staging_creation_verified",
            true_fields,
        )
        self.assertIn(
            "full_blob_path_mode_owner_acl_xattr_value_validation_verified",
            true_fields,
        )
        self.assertEqual(counts["new_staging_release_count"], 1)
        self.assertEqual(counts["release_root_owner_write_enable_count"], 1)
        self.assertEqual(counts["release_root_mode_restore_count"], 1)
        self.assertEqual(counts["renameatx_np_attempt_count"], 1)
        self.assertEqual(counts["ordinary_rename_attempt_count"], 0)
        self.assertEqual(
            self.policy["required_exact_values"]["atomic_rename_flags"],
            "RENAME_EXCL|RENAME_NOFOLLOW_ANY|RENAME_RESOLVE_BENEATH",
        )

    def test_staging_v1_is_evidence_only_and_fallbacks_reject(self) -> None:
        resources = set(self.policy["allowed_mutation_resources"])
        operations = set(self.policy["allowed_operations"])
        self.assertTrue(self.policy["preserved_staging_evidence_only"])
        self.assertFalse(self.policy["preserved_staging_cleanup_allowed"])
        self.assertNotIn("preserved_failed_staging_path", resources)
        self.assertFalse(any("preserved" in operation for operation in operations))
        for field in (
            "prior_policy_reuse_requested",
            "preserved_staging_reused",
            "preserved_staging_modified",
            "preserved_staging_renamed",
            "preserved_staging_deleted",
            "automatic_retry_requested",
            "second_recovery_requested",
            "policy_fallback_requested",
            "cleanup_requested",
            "runtime_operation_requested",
            "database_connection_requested",
            "migration_requested",
            "evaluator_requested",
            "virtual_executor_requested",
            "n1_n6_business_mutation_requested",
            "trade_touched",
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
            self.assertIn(
                PREFLIGHT_GIT_VIOLATION_RECOVERY_POLICY_ID,
                text,
                relative,
            )


class ImmutableReleaseInstallEaccesRetryPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy(RETRY_POLICY_ID)
        cls.request = canonical(cls.policy, RETRY_POLICY_ID)

    def decide(self, **changes: Any) -> str:
        req = copy.deepcopy(self.request)
        req.update(changes)
        return evaluate(self.policy, req)

    def test_exact_eacces_retry_accepts(self) -> None:
        self.assertEqual(self.decide(), "ACCEPT")
        self.assertEqual(self.policy["runtime_gate_decision"], "ACCEPT")
        self.assertEqual(self.policy["default_runtime_execution_decision"], "REJECT")

    def test_non_eacces_or_missing_failure_evidence_rejects(self) -> None:
        for field in (
            "prior_failure_errno_eacces_verified",
            "prior_failure_target_absent_verified",
            "prior_failure_no_attestation_verified",
            "prior_failure_release_root_restored_0555_verified",
            "prior_failed_staging_exists_and_is_immutable_verified",
            "prior_failed_staging_unmodified_verified",
        ):
            self.assertEqual(self.decide(**{field: False}), "REJECT", field)
        self.assertEqual(self.decide(prior_eacces_rename_failure_count=0), "REJECT")

    def test_every_required_boolean_is_fail_closed(self) -> None:
        for field in self.policy["required_true_fields"]:
            self.assertEqual(self.decide(**{field: False}), "REJECT", field)
        for field in self.policy["required_false_fields"]:
            self.assertEqual(self.decide(**{field: True}), "REJECT", field)

    def test_prior_staging_is_evidence_only(self) -> None:
        self.assertEqual(self.decide(prior_failed_staging_reused=True), "REJECT")
        self.assertEqual(self.decide(prior_failed_staging_modified=True), "REJECT")
        self.assertEqual(
            self.decide(prior_failed_staging_path=self.request["staging_release_path"]),
            "REJECT",
        )

    def test_both_owner_write_windows_are_exact(self) -> None:
        for field in (
            "temporary_release_root_mode_0755_owner_only_verified",
            "release_root_after_mode_0555_verified",
            "staging_root_before_mode_0555_verified",
            "temporary_staging_root_mode_0755_owner_only_verified",
            "staging_root_after_mode_0555_verified",
            "failure_restores_all_modes_defined",
        ):
            self.assertEqual(self.decide(**{field: False}), "REJECT", field)
        self.assertEqual(self.decide(staging_root_owner_write_enable_count=2), "REJECT")
        self.assertEqual(self.decide(staging_root_mode_restore_count=0), "REJECT")
        self.assertEqual(self.decide(staging_root_left_writable=True), "REJECT")

    def test_second_retry_and_forbidden_operations_reject(self) -> None:
        self.assertEqual(self.decide(retry_count=2), "REJECT")
        self.assertEqual(self.decide(second_retry_requested=True), "REJECT")
        for field in (
            "database_connection_requested", "evaluator_requested",
            "virtual_executor_requested", "migration_requested", "service_restarted",
            "proposal_touched", "order_touched", "trade_touched", "position_touched",
            "cash_touched", "n1_n6_business_mutation_requested",
        ):
            self.assertEqual(self.decide(**{field: True}), "REJECT", field)


class ImmutableReleaseInstallHostEaccesRemediationPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy(HOST_REMEDIATION_POLICY_ID)
        cls.request = canonical(cls.policy, HOST_REMEDIATION_POLICY_ID)

    def decide(self, **changes: Any) -> str:
        req = copy.deepcopy(self.request)
        req.update(changes)
        return evaluate(self.policy, req)

    def test_exact_host_remediation_accepts(self) -> None:
        self.assertEqual(self.decide(), "ACCEPT")
        self.assertEqual(self.policy["runtime_gate_decision"], "ACCEPT")
        self.assertEqual(self.policy["default_runtime_execution_decision"], "REJECT")

    def test_host_trace_and_orphaned_staging_are_mandatory(self) -> None:
        for field in (
            "host_eacces_trace_readable_verified", "host_eacces_errno_verified",
            "host_eacces_same_root_verified", "host_eacces_same_parent_and_tmp_failure_verified",
            "orphaned_staging_exists_verified", "orphaned_staging_unmodified_verified",
            "orphaned_target_absent_verified",
        ):
            self.assertEqual(self.decide(**{field: False}), "REJECT", field)
        self.assertEqual(self.decide(orphaned_staging_path=self.request["staging_release_path"]), "REJECT")

    def test_every_boolean_and_forbidden_runtime_path_is_fail_closed(self) -> None:
        for field in self.policy["required_true_fields"]:
            self.assertEqual(self.decide(**{field: False}), "REJECT", field)
        for field in self.policy["required_false_fields"]:
            self.assertEqual(self.decide(**{field: True}), "REJECT", field)
        self.assertEqual(self.decide(remediation_attempt_count=2), "REJECT")
        self.assertEqual(self.decide(staging_root_owner_write_enable_count=2), "REJECT")


class ImmutableReleasePrivilegedAtomicInstallPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy(PRIVILEGED_INSTALL_POLICY_ID)
        cls.request = canonical(cls.policy, PRIVILEGED_INSTALL_POLICY_ID)
        cls.source = (ROOT / "scripts" / "n6_privileged_atomic_release_installer.c").read_text(
            encoding="utf-8"
        )

    def decide(self, **changes: Any) -> str:
        req = copy.deepcopy(self.request)
        req.update(changes)
        return evaluate(self.policy, req)

    def test_exact_privileged_install_accepts(self) -> None:
        self.assertEqual(self.decide(), "ACCEPT")
        self.assertEqual(self.policy["runtime_gate_decision"], "ACCEPT")
        self.assertEqual(self.policy["default_runtime_execution_decision"], "REJECT")

    def test_required_attestation_and_one_call_are_fail_closed(self) -> None:
        for field in self.policy["required_true_fields"]:
            self.assertEqual(self.decide(**{field: False}), "REJECT", field)
        for field in self.policy["required_false_fields"]:
            self.assertEqual(self.decide(**{field: True}), "REJECT", field)
        self.assertEqual(self.decide(privileged_helper_invocation_count=2), "REJECT")
        self.assertEqual(self.decide(renameatx_np_count=0), "REJECT")
        self.assertEqual(self.decide(retry_count=1), "REJECT")

    def test_paths_and_target_are_fail_closed(self) -> None:
        self.assertEqual(self.decide(helper_path="/tmp/helper"), "REJECT")
        self.assertEqual(self.decide(target_release_path="/tmp/escape"), "REJECT")
        self.assertEqual(self.decide(target_release_exists_before_install=True), "REJECT")
        self.assertEqual(self.decide(staging_target_direct_children_verified=False), "REJECT")

    def test_helper_uses_only_parent_dirfd_atomic_promotion(self) -> None:
        for token in (
            "static const char kReleaseRoot[]", "geteuid() != 0",
            "open(kReleaseRoot, O_RDONLY | O_DIRECTORY | O_NOFOLLOW)",
            "fstatat(root_fd, argv[1]", "AT_SYMLINK_NOFOLLOW",
            "renameatx_np(root_fd, argv[1], root_fd, argv[2], flags)",
            "RENAME_EXCL | RENAME_NOFOLLOW_ANY | RENAME_RESOLVE_BENEATH",
        ):
            self.assertIn(token, self.source)

    def test_helper_rejects_shell_copy_delete_and_metadata_mutation(self) -> None:
        for token in (
            "system(", "popen(", "execl", "execv", "copyfile(", "unlink(",
            "remove(", "rename(", "chmod(", "chown(", "setxattr(",
            "removexattr(", "acl_",
        ):
            self.assertNotIn(token, self.source, token)


class ImmutableReleasePrivilegedMaterializeInstallPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy(MATERIALIZE_INSTALL_POLICY_ID)
        cls.request = canonical(cls.policy, MATERIALIZE_INSTALL_POLICY_ID)
        cls.source = (ROOT / "scripts" / "n6_privileged_materialize_and_install.c").read_text(
            encoding="utf-8"
        )

    def decide(self, **changes: Any) -> str:
        req = copy.deepcopy(self.request)
        req.update(changes)
        return evaluate(self.policy, req)

    def test_exact_materialize_install_accepts(self) -> None:
        self.assertEqual(self.decide(), "ACCEPT")
        self.assertEqual(self.policy["runtime_gate_decision"], "ACCEPT")
        self.assertEqual(
            self.policy["scope_mode"],
            "single_frozen_d85df632_privileged_materialize_install",
        )
        self.assertEqual(self.request["source_commit"], FROZEN_D85_COMMIT)
        self.assertEqual(self.request["source_tree"], FROZEN_D85_TREE)
        self.assertEqual(self.request["archive_sha256"], FROZEN_D85_ARCHIVE_SHA)
        self.assertEqual(self.request["manifest_sha256"], FROZEN_D85_MANIFEST_SHA)
        self.assertEqual(
            self.request["filesystem_validation_sha256"],
            FROZEN_D85_FILESYSTEM_SHA,
        )
        self.assertEqual(self.request["archive_expected_file_count"], 6240)
        self.assertEqual(self.request["archive_expected_directory_count"], 45)
        self.assertEqual(self.request["archive_pax_global_header_count"], 1)
        self.assertEqual(self.request["archive_pax_extended_header_count"], 108)
        self.assertEqual(
            self.request["attestation_filename_suffix"],
            "__d85df632-materialize-install.json",
        )

    def test_archive_manifest_paths_and_one_call_are_fail_closed(self) -> None:
        self.assertEqual(self.request["archive_path"], FROZEN_D85_ARCHIVE_PATH)
        self.assertEqual(self.request["manifest_path"], FROZEN_D85_MANIFEST_PATH)
        self.assertEqual(self.decide(archive_path="/tmp/other.tar"), "REJECT")
        self.assertEqual(self.decide(manifest_path="/tmp/other.json"), "REJECT")
        self.assertEqual(self.decide(materializer_helper_path="/tmp/helper"), "REJECT")
        self.assertEqual(self.decide(materializer_helper_invocation_count=2), "REJECT")
        self.assertEqual(self.decide(retry_count=1), "REJECT")
        self.assertEqual(self.decide(target_release_exists_before_install=True), "REJECT")

    def test_only_frozen_d85_hashes_counts_and_commit_bound_target_accept(self) -> None:
        for field, value in (
            ("source_commit", "f2b1ef323ad74be58fe9344815865350130dc012"),
            ("source_tree", "15210c96232c2faa1a095313e0c894e241692644"),
            ("archive_sha256", "b4d413b5e93c96585f19abc29b713f84b1fb2ac1a2fb148732c66e864fd495d1"),
            ("manifest_sha256", "5ecf06997ef83e8e9542735402375f2ad495007ebec0ea6d465d9bd0e77ca894"),
            ("filesystem_validation_sha256", "71aae1850504bd0e37f161df481d083695b6f2a0c4b22d1131ae1232cf420c62"),
            ("archive_expected_file_count", 6239),
            ("archive_expected_directory_count", 44),
            ("archive_pax_global_header_count", 0),
            ("archive_pax_extended_header_count", 107),
            ("attestation_filename_suffix", "__f2b1-materialize-install.json"),
        ):
            self.assertEqual(self.decide(**{field: value}), "REJECT", field)
        wrong_target = (
            self.policy["release_root"]
            + "/20260726_120000__"
            + "a" * 40
        )
        self.assertEqual(self.decide(target_release_path=wrong_target), "REJECT")

    def test_all_contract_booleans_and_forbidden_paths_fail_closed(self) -> None:
        for field in self.policy["required_true_fields"]:
            self.assertEqual(self.decide(**{field: False}), "REJECT", field)
        for field in self.policy["required_false_fields"]:
            self.assertEqual(self.decide(**{field: True}), "REJECT", field)

    def test_v2_is_fixed_archive_dirfd_safe_extract_and_single_promotion(self) -> None:
        for token in (
            "static const char kArchive[]", "static const char kManifest[]",
            "static const char kArchiveSha[]", "static const char kManifestSha[]",
            "geteuid() != 0", "mkdirat(rootfd, argv[3], 0755)",
            "struct tar_header", "safe_relative_path(out)",
            "static bool archive_mode_allowed(char typeflag, mode_t mode)",
            "mode == 0755 || mode == 0775",
            "mode == 0644 || mode == 0664 || mode == 0755 || mode == 0775",
            "!archive_mode_allowed(header.typeflag, mode)",
            "struct pax_override",
            "static bool pax_records(",
            "header.typeflag == 'g' || header.typeflag == 'x'",
            "pax_global_header",
            "override.has_path",
            "record_length < digits + 3",
            "header.linkname[0] != '\\0'", "header.typeflag == '5'",
            "header.typeflag == '\\0' || header.typeflag == '0'",
            "out[n - 1] == '/'",
            "mode_t sealed_mode = (mode == 0755 || mode == 0775) ? 0555 : 0444",
            "files == kExpectedFiles && dirs == kExpectedDirectories",
            "fchmodat(dirfd, entry->d_name, 0555, 0)",
            "fchmodat(rootfd, argv[3], 0555, 0)",
            "RENAME_EXCL | RENAME_NOFOLLOW_ANY | RENAME_RESOLVE_BENEATH",
            "renameatx_np(rootfd, argv[3], rootfd, argv[4], flags)",
            "write_attestation(argv[4])",
        ):
            self.assertIn(token, self.source)

    def test_v2_source_constants_are_exactly_d85_and_attestation_is_not_f2(self) -> None:
        for value in (
            FROZEN_D85_ARCHIVE_PATH,
            FROZEN_D85_MANIFEST_PATH,
            FROZEN_D85_COMMIT,
            FROZEN_D85_TREE,
            FROZEN_D85_ARCHIVE_SHA,
            FROZEN_D85_MANIFEST_SHA,
            FROZEN_D85_FILESYSTEM_SHA,
            "static const unsigned kExpectedFiles = 6240;",
            "static const unsigned kExpectedDirectories = 45;",
            "__d85df632-materialize-install.json",
        ):
            self.assertIn(value, self.source)
        self.assertNotIn("__f2b1-materialize-install.json", self.source)
        self.assertNotIn("/tmp/n6_release_attest.VVcfaF", self.source)

    def test_v2_accepts_git_archive_modes_only_and_seals_stricter(self) -> None:
        self.assertIn("if (typeflag == '5') return mode == 0755 || mode == 0775;", self.source)
        self.assertIn(
            "return mode == 0644 || mode == 0664 || mode == 0755 || mode == 0775;",
            self.source,
        )
        self.assertIn("mode == 0755 || mode == 0775) ? 0555 : 0444", self.source)
        self.assertNotIn("mode == 0777", self.source)
        self.assertNotIn("mode == 0666", self.source)

    def test_v2_seals_directories_from_verified_parent_dirfds(self) -> None:
        self.assertNotIn("fchmod(child, 0555)", self.source)
        self.assertNotIn("fchmod(stagefd, 0555)", self.source)

    def test_v2_rejects_hardlinked_files_without_rejecting_directory_link_counts(self) -> None:
        self.assertIn("if (S_ISLNK(st.st_mode))", self.source)
        self.assertIn("S_ISREG(st.st_mode) && st.st_nlink <= 1", self.source)
        self.assertNotIn("S_ISLNK(st.st_mode) || st.st_nlink > 1", self.source)

    def test_v2_accepts_exact_ustar_name_field_boundary(self) -> None:
        self.assertIn(
            "USTAR permits a path component to occupy the complete 100-byte name field",
            self.source,
        )
        self.assertNotIn(
            "if (name_n == sizeof(header->name) || prefix_n == sizeof(header->prefix)) return false;",
            self.source,
        )

    def test_frozen_d85_archive_mode_and_pax_fixture(self) -> None:
        fixture = FROZEN_D85_ARCHIVE_FIXTURE
        self.assertEqual(sum(fixture["input_file_modes"].values()), 6240)
        self.assertEqual(sum(fixture["input_directory_modes"].values()), 45)
        self.assertEqual(fixture["sealed_file_modes"], {"0444": 6236, "0555": 4})
        self.assertEqual(fixture["sealed_directory_modes"], {"0555": 45})
        self.assertEqual(fixture["pax_global_headers"], 1)
        self.assertEqual(fixture["pax_extended_headers"], 108)
        self.assertEqual(fixture["pax_global_key"], "comment")
        self.assertEqual(fixture["pax_extended_key"], "path")

    def test_v2_excludes_shell_copy_delete_xattr_acl_and_arbitrary_exec(self) -> None:
        for token in (
            "system(", "popen(", "execl", "execv", "copyfile(", "unlink(",
            "remove(", "rename(", "setxattr(", "removexattr(", "acl_",
        ):
            self.assertNotIn(token, self.source, token)


class ImmutableReleasePrivilegedF67MaterializeInstallPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy(F67_MATERIALIZE_INSTALL_POLICY_ID)
        cls.request = canonical(cls.policy, F67_MATERIALIZE_INSTALL_POLICY_ID)
        cls.source = (
            ROOT / "scripts" / "n6_privileged_materialize_and_install_f67.c"
        ).read_text(encoding="utf-8")

    def decide(self, **changes: Any) -> str:
        req = copy.deepcopy(self.request)
        req.update(changes)
        return evaluate(self.policy, req)

    def test_exact_f67_contract_accepts_without_changing_d85_policy(self) -> None:
        self.assertEqual(self.decide(), "ACCEPT")
        self.assertEqual(self.policy["runtime_gate_decision"], "ACCEPT")
        self.assertEqual(
            self.policy["scope_mode"],
            "single_frozen_f67be0f5_privileged_materialize_install",
        )
        self.assertEqual(self.request["source_commit"], FROZEN_F67_COMMIT)
        self.assertEqual(self.request["source_tree"], FROZEN_F67_TREE)
        d85 = load_policy(MATERIALIZE_INSTALL_POLICY_ID)
        self.assertEqual(d85["scope_mode"], "single_frozen_d85df632_privileged_materialize_install")
        self.assertEqual(d85["frozen_archive_path"], FROZEN_D85_ARCHIVE_PATH)

    def test_f67_paths_helper_hashes_counts_and_attestation_are_exact(self) -> None:
        expected = {
            "archive_path": FROZEN_F67_ARCHIVE_PATH,
            "manifest_path": FROZEN_F67_MANIFEST_PATH,
            "materializer_helper_path": FROZEN_F67_HELPER_PATH,
            "source_commit": FROZEN_F67_COMMIT,
            "source_tree": FROZEN_F67_TREE,
            "archive_sha256": FROZEN_F67_ARCHIVE_SHA,
            "git_ls_tree_sha256": FROZEN_F67_GIT_LS_TREE_SHA,
            "manifest_sha256": FROZEN_F67_MANIFEST_SHA,
            "filesystem_validation_sha256": FROZEN_F67_FILESYSTEM_SHA,
            "bundle_payload_sha256": FROZEN_F67_BUNDLE_PAYLOAD_SHA,
            "bundle_file_sha256": FROZEN_F67_BUNDLE_FILE_SHA,
            "archive_expected_file_count": 6240,
            "archive_expected_directory_count": 45,
            "archive_pax_global_header_count": 1,
            "archive_pax_extended_header_count": 108,
            "attestation_filename_suffix": "__f67be0f5-materialize-install.json",
        }
        for field, value in expected.items():
            self.assertEqual(self.request[field], value, field)
        self.assertTrue(self.request["target_release_path"].endswith(FROZEN_F67_COMMIT))
        self.assertTrue(self.request["staging_release_path"].endswith(FROZEN_F67_COMMIT))

    def test_non_f67_input_d85_helper_old_staging_and_target_are_rejected(self) -> None:
        for field, value in (
            ("source_commit", FROZEN_D85_COMMIT),
            ("archive_sha256", FROZEN_D85_ARCHIVE_SHA),
            ("git_ls_tree_sha256", "a" * 64),
            ("manifest_sha256", FROZEN_D85_MANIFEST_SHA),
            ("filesystem_validation_sha256", FROZEN_D85_FILESYSTEM_SHA),
            ("bundle_payload_sha256", "b" * 64),
            ("bundle_file_sha256", "c" * 64),
            ("archive_expected_file_count", 6239),
            ("archive_expected_directory_count", 44),
            ("archive_pax_global_header_count", 0),
            ("archive_pax_extended_header_count", 107),
            ("materializer_helper_path", "/usr/local/libexec/ashare-v3/n6-immutable-release-materializer"),
            ("target_release_exists_before_install", True),
            ("retry_count", 1),
        ):
            self.assertEqual(self.decide(**{field: value}), "REJECT", field)
        self.assertEqual(
            self.decide(orphaned_staging_path=self.request["staging_release_path"]),
            "REJECT",
        )

    def test_all_required_and_forbidden_fields_are_fail_closed(self) -> None:
        for field in self.policy["required_true_fields"]:
            self.assertEqual(self.decide(**{field: False}), "REJECT", field)
        for field in self.policy["required_false_fields"]:
            self.assertEqual(self.decide(**{field: True}), "REJECT", field)
        self.assertEqual(self.decide(materializer_helper_invocation_count=2), "REJECT")
        self.assertEqual(self.decide(renameatx_np_count=0), "REJECT")

    def test_f67_helper_binds_every_frozen_authority(self) -> None:
        for value in (
            FROZEN_F67_ARCHIVE_PATH,
            FROZEN_F67_MANIFEST_PATH,
            FROZEN_F67_COMMIT,
            FROZEN_F67_TREE,
            FROZEN_F67_ARCHIVE_SHA,
            FROZEN_F67_GIT_LS_TREE_SHA,
            FROZEN_F67_MANIFEST_SHA,
            FROZEN_F67_FILESYSTEM_SHA,
            FROZEN_F67_BUNDLE_PAYLOAD_SHA,
            FROZEN_F67_BUNDLE_FILE_SHA,
            "static const unsigned kExpectedFiles = 6240;",
            "static const unsigned kExpectedDirectories = 45;",
            "static const unsigned kExpectedPaxGlobalHeaders = 1;",
            "static const unsigned kExpectedPaxExtendedHeaders = 108;",
            "__f67be0f5-materialize-install.json",
        ):
            self.assertIn(value, self.source)
        self.assertNotIn(FROZEN_D85_ARCHIVE_PATH, self.source)
        self.assertNotIn("__d85df632-materialize-install.json", self.source)

    def test_f67_helper_is_root_only_fresh_staging_and_commit_bound(self) -> None:
        for token in (
            "geteuid() != 0",
            "strcmp(argv[1], kArchive) != 0",
            "strcmp(argv[2], kManifest) != 0",
            "!ends_with(argv[3], kCommit)",
            "!ends_with(argv[4], kCommit)",
            "fstatat(rootfd, argv[4], &target, AT_SYMLINK_NOFOLLOW)",
            "mkdirat(rootfd, argv[3], 0755)",
            "openat(rootfd, argv[3], O_RDONLY | O_DIRECTORY | O_NOFOLLOW)",
        ):
            self.assertIn(token, self.source)
        self.assertLess(
            self.source.index("fstatat(rootfd, argv[4], &target"),
            self.source.index("mkdirat(rootfd, argv[3], 0755)"),
        )

    def test_f67_helper_strictly_validates_archive_and_seals_output(self) -> None:
        for token in (
            "header.typeflag == 'g' || header.typeflag == 'x'",
            "pax_global_header",
            "record_length < digits + 3",
            "header.linkname[0] != '\\0'",
            "safe_relative_path(override->path)",
            "if (S_ISLNK(st.st_mode))",
            "S_ISREG(st.st_mode) && st.st_nlink <= 1",
            "mode == 0644 || mode == 0664 || mode == 0755 || mode == 0775",
            "mode_t sealed_mode = (mode == 0755 || mode == 0775) ? 0555 : 0444",
            "pax_global_headers == kExpectedPaxGlobalHeaders",
            "pax_extended_headers == kExpectedPaxExtendedHeaders",
            "fchmodat(rootfd, argv[3], 0555, 0)",
        ):
            self.assertIn(token, self.source)

    def test_f67_helper_promotes_once_and_verifies_target_0555(self) -> None:
        for token in (
            "RENAME_EXCL | RENAME_NOFOLLOW_ANY | RENAME_RESOLVE_BENEATH",
            "renameatx_np(rootfd, argv[3], rootfd, argv[4], flags)",
            "S_ISDIR(target_stat.st_mode)",
            "(target_stat.st_mode & 0777) == 0555",
            "write_attestation(argv[4])",
        ):
            self.assertIn(token, self.source)
        self.assertEqual(
            self.source.count("renameatx_np(rootfd, argv[3], rootfd, argv[4], flags)"),
            1,
        )

    def test_frozen_f67_archive_fixture_matches_exact_modes_and_pax(self) -> None:
        fixture = FROZEN_F67_ARCHIVE_FIXTURE
        self.assertEqual(sum(fixture["input_file_modes"].values()), 6240)
        self.assertEqual(sum(fixture["input_directory_modes"].values()), 45)
        self.assertEqual(fixture["sealed_file_modes"], {"0444": 6236, "0555": 4})
        self.assertEqual(fixture["sealed_directory_modes"], {"0555": 45})
        self.assertEqual(fixture["pax_global_headers"], 1)
        self.assertEqual(fixture["pax_extended_headers"], 108)
        self.assertEqual(fixture["pax_global_key"], "comment")
        self.assertEqual(fixture["pax_extended_key"], "path")

    def test_f67_helper_excludes_shell_delete_overwrite_xattr_acl_and_runtime(self) -> None:
        for token in (
            "system(", "popen(", "execl", "execv", "copyfile(", "unlink(",
            "remove(", "rename(", "setxattr(", "removexattr(", "acl_",
            "launchctl", "psql", "evaluator", "executor", "proposal", "order",
            "trade", "position", "cash",
        ):
            self.assertNotIn(token, self.source, token)


if __name__ == "__main__":
    unittest.main()
