from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "n6_f464_user_owned_immutable_release_install_v1"
RECOVERY_POLICY_ID = "n6_f464_no_extended_acl_enoent_fix_recovery_v1"
RECOVERY_POLICY_CANONICAL_SHA256 = (
    "e52feedbf069444561497e37913c6329a948d0d86f1848c9b2066fc5e9d4082d"
)
PROVENANCE_RECOVERY_POLICY_ID = (
    "n6_f464_inherited_provenance_staging_recovery_governance_v1"
)
PROVENANCE_RECOVERY_POLICY_CANONICAL_SHA256 = (
    "6a18c12d529df83cfe8cb15877c29c4b91d05bf10f7dc262ff0d5474585343c3"
)
FULL_WIDTH_RECOVERY_POLICY_ID = (
    "n6_f464_full_width_ustar_name_recovery_governance_v1"
)
FULL_WIDTH_RECOVERY_POLICY_CANONICAL_SHA256 = (
    "f56c6e00903b5acec4705db8c8a646330433d0439150971f00da85c7da7fcd1d"
)
PROMOTE_RECOVERY_POLICY_ID = (
    "n6_f464_recovery4_promote_and_postcondition_governance_v1"
)
PROMOTE_RECOVERY_POLICY_CANONICAL_SHA256 = (
    "fd787f0332a7d9e0edc2dee4dcd55e384cc2ed6ffa63fe80e2174122d7d2382c"
)
HISTORICAL_INSTALLER_POLICY_ID = (
    "n6_immutable_release_privileged_materialize_and_install_f464_v1"
)
HISTORICAL_REMEDIATION_POLICY_ID = "n6_f464_release_root_owner_remediation_v1"
BASE_GOVERNANCE_COMMIT = "d281744840d404830d06fbaef7088524ed98885d"
PROVENANCE_RECOVERY_BASE_COMMIT = "ea6c2c372bd25ab42bf841b05b1f3f65a21dfbbb"
FULL_WIDTH_RECOVERY_BASE_COMMIT = "47b9d2d959010e7c99ccca1ec713e6797d630ec7"
FULL_WIDTH_RECOVERY_BASE_TREE = "13f063924b72dbc153aec4df55e03e51276fc40d"
PROMOTE_RECOVERY_BASE_COMMIT = "d2e7d015f7180186d0f1c73d1843b5dad40c78a8"
PROMOTE_RECOVERY_BASE_TREE = "d82a0ea1b6825f6cd6eebb4953e2b722c69292ad"
OLD_HELPER_BINARY_SHA256 = (
    "3e935d03611c0a775a81f06160bc16af0e9d860f08836ef479d70a8cfbbe7c88"
)
STAGE3J_HELPER_BINARY_SHA256 = (
    "7d4a7f815e44d729558c79cbf47a0dc80b4f5be708fa4d87d49af43e3d31fe6d"
)
STAGE3L_HELPER_BINARY_SHA256 = (
    "4ecef31c10e99754a916beb7db1661e89cde5a3915323d5880be13ab8ddfddb0"
)
STAGE3N_HELPER_BINARY_SHA256 = (
    "63e126e369a8402dfc731a37ba4cf1abf19b73086fada647c2d8a397dca6974c"
)
PROVENANCE_NAME = "com.apple.provenance"
PROVENANCE_RAW = bytes.fromhex("0100006457BBC065B81880")
PROVENANCE_FINGERPRINT_SHA256 = (
    "9bd57bf16e9955726429cd301ee3dbf68c635f050f9317977592961193a494ea"
)
SOURCE = ROOT / "scripts" / "n6_f464_privileged_materialize_and_install_v2.c"
CANDIDATE_ROOT = Path(
    "/Users/chuanfuchen/.codex/artifacts/"
    "n6_strategy_center_evaluator_resume_fix_v1/"
    "20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62"
)
ARCHIVE = CANDIDATE_ROOT / (
    "20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62.tar"
)
MANIFEST = CANDIDATE_ROOT / (
    "20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62"
    ".git-ls-tree.nul"
)
RELEASE_ATTESTATION = CANDIDATE_ROOT / "release-attestation.json"
BUNDLE = (
    CANDIDATE_ROOT
    / "release"
    / "config"
    / "n6_strategy_center"
    / "N6_SC_TEMPORAL_CONFLUENCE_V2_SHADOW_BUNDLE_20260723.json"
)
RELEASE_ROOT = Path(
    "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def provenance_fingerprint(name: str, value: bytes) -> str:
    name_bytes = name.encode()
    digest = hashlib.sha256()
    digest.update(len(name_bytes).to_bytes(8, "big"))
    digest.update(name_bytes)
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)
    return digest.hexdigest()


def exact_provenance_gate(xattrs: dict[str, bytes]) -> bool:
    return (
        list(xattrs) == [PROVENANCE_NAME]
        and provenance_fingerprint(PROVENANCE_NAME, xattrs[PROVENANCE_NAME])
        == PROVENANCE_FINGERPRINT_SHA256
    )


def load_policy(policy_id: str = POLICY_ID) -> dict[str, Any]:
    text = (ROOT / "docs" / "EXECUTION_KERNEL.md").read_text(encoding="utf-8")
    begin = f"<!-- policy:{policy_id}:begin -->"
    end = f"<!-- policy:{policy_id}:end -->"
    start = text.index(begin) + len(begin)
    stop = text.index(end, start)
    block = text[start:stop].strip()
    match = re.fullmatch(r"```json\s*(\{.*\})\s*```", block, re.DOTALL)
    if match is None:
        raise AssertionError("policy must contain exactly one JSON fence")
    return json.loads(match.group(1))


def canonical_request(policy: dict[str, Any]) -> dict[str, Any]:
    exact_fields = (
        "policy_id",
        "canonical_status",
        "parent_approval_id",
        "approval_status",
        "approval_reconfirmation_required",
        "layer_role",
        "mode",
        "risk_level",
        "scope_mode",
        "phase_mode",
        "governance_ancestry",
        "activation_state_before_sha256",
        "activation_state_before_event_count",
        "activation_state_before_tail_event_sha256",
        "release_root",
        "release_root_exact",
        "candidate_root",
        "frozen_archive_path",
        "frozen_manifest_path",
        "frozen_release_attestation_path",
        "frozen_bundle_path",
        "target_release_name",
        "target_release_path",
        "staging_release_name",
        "staging_release_path",
        "historical_privileged_helper_target",
        "helper_source_path",
        "compiled_helper_artifact_path",
        "helper_attestation_path",
        "failure_staging_policy",
        "live_freeze",
        "new_install_checkpoint_contract",
        "allowed_governance_files",
        "allowed_governance_operations",
        "allowed_later_execution_operations",
    )
    request: dict[str, Any] = {
        field: copy.deepcopy(policy[field]) for field in exact_fields
    }
    request.update(policy["required_exact_values"])
    request.update(policy["required_singleton_counts"])
    request.update({field: True for field in policy["required_true_fields"]})
    request.update({field: False for field in policy["required_false_fields"]})
    return request


def evaluate(policy: dict[str, Any], request: dict[str, Any]) -> str:
    reject = policy["default_execution_decision"]
    canonical = canonical_request(policy)
    if any(request.get(field) != expected for field, expected in canonical.items()):
        return reject
    for field, expected in policy["required_exact_values"].items():
        if request.get(field) != expected:
            return reject
    for field, expected in policy["required_singleton_counts"].items():
        if request.get(field) != expected:
            return reject
    if any(request.get(field) is not True for field in policy["required_true_fields"]):
        return reject
    if any(request.get(field) is not False for field in policy["required_false_fields"]):
        return reject
    root = Path(policy["release_root"])
    target = Path(request["target_release_path"])
    staging = Path(request["staging_release_path"])
    if (
        target.parent != root
        or staging.parent != root
        or target.name != policy["target_release_name"]
        or staging.name != policy["staging_release_name"]
        or not target.name.endswith(f"__{request['release_commit']}")
    ):
        return reject
    if (
        request.get("allowed_governance_files") != policy["allowed_governance_files"]
        or request.get("allowed_governance_operations")
        != policy["allowed_governance_operations"]
    ):
        return reject
    return policy["accept_decision"]


def safe_relative_path(path: str) -> bool:
    if not path or path.startswith("/") or "//" in path:
        return False
    return all(part not in ("", ".", "..") for part in path.split("/"))


def bounded_ustar_path(name: bytes, prefix: bytes = b"") -> str | None:
    if (
        not name
        or len(name) > 100
        or len(prefix) >= 155
        or b"\0" in name
        or b"\0" in prefix
    ):
        return None
    try:
        path = (
            f"{prefix.decode('utf-8')}/{name.decode('utf-8')}"
            if prefix
            else name.decode("utf-8")
        )
    except UnicodeDecodeError:
        return None
    path = path.rstrip("/")
    return path if safe_relative_path(path) else None


def failed_staging_entry_records_sha256(root: Path) -> str:
    records: list[dict[str, Any]] = []
    for path in sorted(
        root.rglob("*"),
        key=lambda item: os.fsencode(str(item.relative_to(root))),
    ):
        metadata = path.lstat()
        relative = str(path.relative_to(root))
        if stat.S_ISDIR(metadata.st_mode):
            entry_type = "d"
            content_sha256 = None
        elif stat.S_ISREG(metadata.st_mode):
            entry_type = "f"
            content_sha256 = sha256(path)
        else:
            entry_type = "other"
            content_sha256 = None
        records.append(
            {
                "path": relative,
                "type": entry_type,
                "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
                "uid": metadata.st_uid,
                "gid": metadata.st_gid,
                "size": metadata.st_size,
                "content_sha256": content_sha256,
            }
        )
    canonical = b"".join(
        json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n"
        for record in records
    )
    return hashlib.sha256(canonical).hexdigest()


def full_manifest_verification_sha256(root: Path) -> str:
    verified: list[dict[str, Any]] = []
    records = [record for record in MANIFEST.read_bytes().split(b"\0") if record]
    for index, record in enumerate(records, 1):
        descriptor, path_bytes = record.split(b"\t", 1)
        mode, object_type, oid = descriptor.decode("ascii").split(" ")
        path = path_bytes.decode("utf-8")
        materialized = root / path
        content = materialized.read_bytes()
        materialized_mode = (
            "0555" if mode == "100755" else "0444"
        )
        if (
            object_type != "blob"
            or hashlib.sha1(
                f"blob {len(content)}\0".encode() + content
            ).hexdigest()
            != oid
            or f"{stat.S_IMODE(materialized.stat().st_mode):04o}"
            != materialized_mode
        ):
            raise AssertionError(f"manifest closure mismatch at index {index}")
        verified.append(
            {
                "index": index,
                "path": path,
                "oid": oid,
                "manifest_mode": mode,
                "materialized_mode": materialized_mode,
            }
        )
    canonical = b"".join(
        json.dumps(
            row,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n"
        for row in verified
    )
    return hashlib.sha256(canonical).hexdigest()


def parse_pax(payload: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    offset = 0
    while offset < len(payload):
        space = payload.find(b" ", offset)
        if space <= offset:
            raise ValueError("invalid PAX length")
        length_text = payload[offset:space]
        if not length_text.isdigit():
            raise ValueError("invalid PAX length digits")
        length = int(length_text)
        end = offset + length
        if end > len(payload) or payload[end - 1 : end] != b"\n":
            raise ValueError("invalid PAX record framing")
        key_value = payload[space + 1 : end - 1]
        key, separator, value = key_value.partition(b"=")
        if not separator or not key or key in result:
            raise ValueError("invalid PAX key/value")
        result[key.decode("ascii")] = value.decode("utf-8")
        offset = end
    if offset != len(payload):
        raise ValueError("PAX trailing bytes")
    return result


def parse_octal(field: bytes) -> int:
    stripped = field.strip(b"\0 ")
    if not stripped or any(byte not in b"01234567" for byte in stripped):
        raise ValueError("invalid octal")
    return int(stripped, 8)


def valid_checksum(header: bytes) -> bool:
    expected = parse_octal(header[148:156])
    actual = sum(header[:148]) + 8 * ord(" ") + sum(header[156:])
    return actual == expected


def manifest_entries() -> list[tuple[str, str, int]]:
    entries: list[tuple[str, str, int]] = []
    for record in MANIFEST.read_bytes().split(b"\0"):
        if not record:
            continue
        prefix, separator, path_bytes = record.partition(b"\t")
        if not separator:
            raise AssertionError("manifest record missing tab")
        mode, object_type, oid = prefix.decode("ascii").split(" ")
        path = path_bytes.decode("utf-8")
        if object_type != "blob" or mode not in ("100644", "100755"):
            raise AssertionError("manifest contains non-blob or unsupported mode")
        if not re.fullmatch(r"[0-9a-f]{40}", oid) or not safe_relative_path(path):
            raise AssertionError("manifest contains invalid oid or path")
        entries.append((path, oid, int(mode[-3:], 8)))
    return entries


class F464InstallerGovernancePolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()
        cls.request = canonical_request(cls.policy)

    def decide(self, **changes: Any) -> str:
        request = copy.deepcopy(self.request)
        request.update(changes)
        return evaluate(self.policy, request)

    def test_canonical_governance_fixture_accepts(self) -> None:
        self.assertEqual(self.decide(), "ACCEPT")
        self.assertEqual(self.policy["runtime_gate_decision_for_governance"], "ACCEPT")
        self.assertEqual(self.policy["default_execution_decision"], "REJECT")
        self.assertFalse(self.policy["approval_reconfirmation_required"])
        canonical = json.dumps(
            self.policy,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            "5f4922d7f7b377788f32ff22f1980d87a1b17a90880de584cb2396246f4676fe",
        )

    def test_every_required_boolean_is_fail_closed(self) -> None:
        for field in self.policy["required_true_fields"]:
            self.assertEqual(self.decide(**{field: False}), "REJECT", field)
        for field in self.policy["required_false_fields"]:
            self.assertEqual(self.decide(**{field: True}), "REJECT", field)

    def test_every_exact_value_and_count_is_fail_closed(self) -> None:
        for field, expected in self.policy["required_exact_values"].items():
            replacement: Any = "0" * len(expected) if isinstance(expected, str) else None
            self.assertEqual(self.decide(**{field: replacement}), "REJECT", field)
        for field, expected in self.policy["required_singleton_counts"].items():
            self.assertEqual(self.decide(**{field: expected + 1}), "REJECT", field)

    def test_paths_are_single_exact_same_parent_target(self) -> None:
        self.assertEqual(self.decide(target_release_path="/tmp/f464"), "REJECT")
        self.assertEqual(self.decide(staging_release_path="/tmp/staging"), "REJECT")
        self.assertEqual(
            self.decide(
                target_release_path=str(
                    Path(self.policy["release_root"]) / ("20260726_000001__" + "a" * 40)
                )
            ),
            "REJECT",
        )

    def test_wrong_uid_gid_mode_inode_acl_xattr_fail_closed(self) -> None:
        cases = (
            ("uid", 0),
            ("gid", 0),
            ("mode", "0755"),
            ("device", 1),
            ("inode", 307341898),
            ("extended_acl_entry_count", 1),
            ("xattr_names", []),
            ("xattr_fingerprint_sha256", "0" * 64),
        )
        for field, value in cases:
            with self.subTest(field=field):
                request = copy.deepcopy(self.request)
                request["release_root_exact"][field] = value
                self.assertEqual(evaluate(self.policy, request), "REJECT")

    def test_target_staging_second_call_and_retry_fail_closed(self) -> None:
        for field in (
            "official_target_absent",
            "official_staging_absent",
            "historical_privileged_helper_target_absent",
        ):
            self.assertEqual(self.decide(**{field: False}), "REJECT")
        for field in ("retry_requested", "second_call_requested"):
            self.assertEqual(self.decide(**{field: True}), "REJECT")
        checkpoint = self.policy["new_install_checkpoint_contract"]
        self.assertTrue(checkpoint["forbids_retry"])
        self.assertTrue(checkpoint["forbids_second_call"])

    def test_governance_session_has_zero_install_and_invocation(self) -> None:
        self.assertEqual(
            self.policy["required_singleton_counts"][
                "governance_helper_install_count"
            ],
            0,
        )
        self.assertEqual(
            self.policy["required_singleton_counts"][
                "governance_helper_invocation_count"
            ],
            0,
        )
        self.assertTrue(self.policy["governance_session_cannot_install_helper"])
        self.assertTrue(self.policy["governance_session_cannot_invoke_helper"])
        self.assertTrue(self.policy["governance_session_cannot_install_release"])

    def test_later_execution_is_no_helper_install_one_call_no_retry(self) -> None:
        counts = self.policy["required_singleton_counts"]
        self.assertEqual(counts["later_execution_helper_install_count"], 0)
        self.assertEqual(counts["later_execution_max_helper_invocation_count"], 1)
        self.assertEqual(counts["retry_count"], 0)
        self.assertIn(
            "stop_without_retry_on_any_nonzero",
            self.policy["allowed_later_execution_operations"],
        )
        self.assertEqual(
            self.policy["failure_staging_policy"],
            "preserve_exact_unique_new_staging_no_delete_no_retry",
        )

    def test_historical_policies_are_superseded_without_history_rewrite(self) -> None:
        for policy_id in (
            HISTORICAL_INSTALLER_POLICY_ID,
            HISTORICAL_REMEDIATION_POLICY_ID,
        ):
            historical = load_policy(policy_id)
            self.assertEqual(historical["canonical_status"], "superseded_noncanonical")
            self.assertEqual(historical["superseded_by_policy_id"], POLICY_ID)
            self.assertFalse(historical["future_install_or_invocation_allowed"])
            self.assertFalse(historical["future_retry_allowed"])
            self.assertFalse(historical["future_privilege_elevation_allowed"])
            self.assertTrue(
                historical["historical_failure_evidence_must_remain_append_only"]
            )
        remediation = load_policy(HISTORICAL_REMEDIATION_POLICY_ID)
        self.assertFalse(remediation["future_uid_501_to_0_change_allowed"])

    def test_exact_three_file_allowlist_and_new_checkpoint_lease(self) -> None:
        self.assertEqual(
            self.policy["allowed_governance_files"],
            [
                "docs/EXECUTION_KERNEL.md",
                "scripts/n6_f464_privileged_materialize_and_install_v2.c",
                "tests/test_n6_f464_immutable_release_installer_governance.py",
            ],
        )
        checkpoint = self.policy["new_install_checkpoint_contract"]
        self.assertEqual(checkpoint["stage"], "F464_USER_OWNED_IMMUTABLE_INSTALL")
        self.assertEqual(checkpoint["target"], "BOUNDED_REBIND_WEB_TARGET")
        self.assertEqual(checkpoint["status"], "ready")
        self.assertTrue(checkpoint["requires_append_only_chain_tail_match"])


class F464HelperStaticTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()
        cls.recovery = load_policy(RECOVERY_POLICY_ID)
        cls.provenance_recovery = load_policy(PROVENANCE_RECOVERY_POLICY_ID)
        cls.full_width_recovery = load_policy(FULL_WIDTH_RECOVERY_POLICY_ID)
        cls.promote_recovery = load_policy(PROMOTE_RECOVERY_POLICY_ID)
        cls.text = SOURCE.read_text(encoding="utf-8")

    def test_source_sha_and_all_frozen_identifiers_are_bound(self) -> None:
        exact = self.policy["required_exact_values"]
        self.assertEqual(
            sha256(SOURCE),
            self.promote_recovery["new_binary"]["source_sha256"],
        )
        self.assertNotEqual(sha256(SOURCE), exact["helper_source_sha256"])
        self.assertNotEqual(
            sha256(SOURCE),
            self.full_width_recovery["new_binary"]["source_sha256"],
        )
        flattened_source = re.sub(r'"\s*"', "", self.text)
        for value in (
            PROMOTE_RECOVERY_POLICY_ID,
            self.promote_recovery["candidate_root"],
            self.promote_recovery["frozen_archive_path"],
            self.promote_recovery["frozen_manifest_path"],
            self.promote_recovery["target_release_name"],
            self.promote_recovery["new_staging_name"],
            self.promote_recovery["historical_staging_exact"]["name"],
            self.promote_recovery["failed_recovery2_staging_exact"]["name"],
            self.promote_recovery["failed_recovery3_staging_exact"]["name"],
            STAGE3N_HELPER_BINARY_SHA256,
            exact["release_commit"],
            exact["release_tree"],
            exact["implementation_commit"],
            exact["implementation_tree"],
            exact["archive_sha256"],
            exact["manifest_sha256"],
            exact["filesystem_sha256"],
            exact["release_attestation_sha256"],
            exact["bundle_file_sha256"],
            exact["bundle_internal_sha256"],
        ):
            self.assertIn(value, flattened_source)

    def test_helper_is_current_user_zero_argument_and_fixed_target(self) -> None:
        self.assertRegex(self.text, r"argc\s*!=\s*1")
        self.assertIn("getuid() != kExpectedUid", self.text)
        self.assertIn("geteuid() != kExpectedUid", self.text)
        self.assertIn("getgid() != kExpectedGid", self.text)
        self.assertIn("getegid() != kExpectedGid", self.text)
        self.assertNotRegex(self.text, r"geteuid\(\)\s*!=\s*0")
        self.assertNotRegex(self.text, r"argv\s*\[\s*1\s*\]")
        self.assertEqual(self.text.count("renameatx_np("), 1)
        for flag in ("RENAME_EXCL", "RENAME_NOFOLLOW_ANY", "RENAME_RESOLVE_BENEATH"):
            self.assertIn(flag, self.text)

    def test_no_elevation_shell_delete_overwrite_or_service_api(self) -> None:
        forbidden_calls = (
            "system",
            "popen",
            "posix_spawn",
            "execve",
            "execl",
            "execvp",
            "unlink",
            "unlinkat",
            "remove",
            "rmdir",
            "rename",
            "renameat",
            "setxattr",
            "removexattr",
            "fchown",
            "chown",
            "lchown",
        )
        for name in forbidden_calls:
            self.assertNotRegex(self.text, rf"\b{name}\s*\(", name)
        for token in (
            "sudo",
            "osascript",
            "AuthorizationCreate",
            "AuthorizationExecuteWithPrivileges",
            "launchctl",
            "postgres",
            "psql",
            "Evaluator",
            "Virtual Executor",
        ):
            self.assertNotIn(token, self.text)

    def test_root_mode_window_is_exactly_once_and_restored_in_finish(self) -> None:
        self.assertEqual(
            self.text.count("fchmod(rootfd, kRootOwnerWriteMode)"),
            1,
        )
        self.assertEqual(
            self.text.count("fchmod(rootfd, kRootSealedMode)"),
            1,
        )
        self.assertIn("goto finish;", self.text)
        self.assertIn("owner_write_window_open", self.text)
        self.assertIn("(metadata.st_mode & 0077) == 0", self.text)

    def test_exclusive_rename_then_immediate_root_seal_has_no_content_copy(self) -> None:
        rename = self.text.index("if (renameatx_np(")
        suffix = self.text[rename:]
        for call in ("mkdirat(", "write("):
            self.assertNotIn(call, suffix)
        seal = suffix.index("fchmod(stagefd, 0555)")
        sync = suffix.index("fsync(stagefd)")
        target = suffix.index("exact_sealed_full_release_tree(targetfd)")
        self.assertLess(seal, sync)
        self.assertLess(sync, target)
        self.assertIn("fchmod(rootfd, kRootSealedMode)", suffix)
        self.assertIn(
            "return final_exit_code(primary_result, postcondition_result);",
            suffix,
        )

    def test_exact_root_acl_xattr_and_target_entry_postconditions_are_static(self) -> None:
        for fragment in (
            "kExpectedDevice",
            "kExpectedInode",
            "kExpectedUid",
            "kExpectedGid",
            "kExpectedXattrFingerprint",
            "no_extended_acl(rootfd)",
            "exact_provenance_xattr_fingerprint(rootfd, root_xattr_before)",
            "strcmp(root_xattr_after, root_xattr_before) == 0",
            "exact_release_entry(stagefd, 0555, true)",
            "exact_sealed_full_release_tree(targetfd)",
            "absent_at(rootfd, kStagingName)",
            "exact_historical_staging(historical_stagefd)",
            "kExpectedHistoricalStagingInode",
        ):
            self.assertIn(fragment, self.text)

    def test_no_extended_acl_has_exact_enoent_semantics(self) -> None:
        function = re.search(
            r"static bool no_extended_acl\(int fd\) \{.*?^\}",
            self.text,
            re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(function)
        self.assertEqual(
            function.group(0),
            """static bool no_extended_acl(int fd) {
    errno = 0;
    acl_t acl = acl_get_fd_np(fd, ACL_TYPE_EXTENDED);
    if (acl == NULL) return errno == ENOENT;
    ssize_t length = 0;
    char *text = acl_to_text(acl, &length);
    bool ok = text != NULL && length == 0 && text[0] == '\\0';
    if (text != NULL) acl_free(text);
    acl_free(acl);
    return ok;
}""",
        )
        self.assertIn("if (acl == NULL) return errno == ENOENT;", function.group(0))
        self.assertNotIn("errno != ENOENT", function.group(0))
        self.assertIn(
            "text != NULL && length == 0 && text[0] == '\\0'",
            function.group(0),
        )

    def test_provenance_recovery_keeps_stage3j_enoent_fix_and_frozen_inputs(self) -> None:
        baseline = subprocess.run(
            [
                "git",
                "show",
                f"{PROVENANCE_RECOVERY_BASE_COMMIT}:"
                "scripts/n6_f464_privileged_materialize_and_install_v2.c",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        enoent_fix = (
            "errno = 0;\n"
            "    acl_t acl = acl_get_fd_np(fd, ACL_TYPE_EXTENDED);\n"
            "    if (acl == NULL) return errno == ENOENT;"
        )
        self.assertIn(enoent_fix, baseline)
        self.assertIn(enoent_fix, self.text)
        for frozen in (
            "a62e98c77e4b3391099ed5eb5939fe2b44a52ac918be3ec6e0a1c6266621d368",
            "0d29c5b4fa2c550e69806d847a68556a3a6b9b568fe06bfde8027cd4639ff78f",
            "4e46cb1fcd73a452f6a3e534d0bb9dc7ddc011fea4937510991cd9b8e51a79fa",
            "0657aad01289cf3ce70635d3732e1408ddad97358ce40c4b570c7de6fed587c3",
            "6efda6309d8e6ebb2d8e91d4a961a0855a76a239c8dd36c45534a50778a190d8",
            "119296de69f27b840cf743f2d6aad04fe56bd7f1ca80991dbdf5be3f547ca1e0",
        ):
            self.assertIn(frozen, baseline)
            self.assertIn(frozen, self.text)

    def test_release_entry_gate_requires_exact_inherited_provenance(self) -> None:
        self.assertNotIn("static bool no_xattrs(", self.text)
        for function_name in ("exact_release_entry", "exact_staging_work_directory"):
            function = re.search(
                rf"static bool {function_name}\(.*?^\}}",
                self.text,
                re.DOTALL | re.MULTILINE,
            )
            self.assertIsNotNone(function)
            self.assertIn(
                "exact_provenance_xattr_fingerprint",
                function.group(0),
            )
            self.assertIn(
                "strcmp(xattr_fingerprint, kExpectedXattrFingerprint) == 0",
                function.group(0),
            )

    def test_historical_staging_is_preserved_and_new_staging_is_unique(self) -> None:
        historical = self.provenance_recovery["historical_staging_exact"]["name"]
        new = self.provenance_recovery["new_staging_name"]
        self.assertNotEqual(historical, new)
        self.assertIn(historical, re.sub(r'"\s*"', "", self.text))
        self.assertIn(new, re.sub(r'"\s*"', "", self.text))
        self.assertNotIn("mkdirat(rootfd, kHistoricalStagingName", self.text)
        self.assertNotIn(
            "renameatx_np(\n            rootfd,\n            kHistoricalStagingName",
            self.text,
        )
        self.assertEqual(self.text.count("mkdirat(rootfd, kStagingName, 0700)"), 1)
        self.assertIn("exact_historical_staging(historical_stagefd)", self.text)
        self.assertIn("historical_staging_unchanged", self.text)


class F464EnoentRecoveryGovernancePolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy(RECOVERY_POLICY_ID)

    def test_recovery_policy_is_canonical_json_and_exact_three_file_scope(self) -> None:
        canonical = json.dumps(
            self.policy,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            RECOVERY_POLICY_CANONICAL_SHA256,
        )
        self.assertEqual(self.policy["canonical_status"], "active_canonical_recovery")
        self.assertEqual(self.policy["base_governance_commit"], BASE_GOVERNANCE_COMMIT)
        self.assertEqual(
            self.policy["allowed_governance_files"],
            [
                "docs/EXECUTION_KERNEL.md",
                "scripts/n6_f464_privileged_materialize_and_install_v2.c",
                "tests/test_n6_f464_immutable_release_installer_governance.py",
            ],
        )

    def test_old_binary_replay_is_permanently_forbidden(self) -> None:
        old = self.policy["old_binary"]
        self.assertEqual(old["sha256"], OLD_HELPER_BINARY_SHA256)
        self.assertFalse(old["future_invocation_allowed"])
        self.assertFalse(old["future_replay_allowed"])
        self.assertFalse(old["future_retry_allowed"])
        self.assertIn(
            "old_binary_replay_requested",
            self.policy["required_false_fields"],
        )

    def test_recovery_is_only_for_exact_pre_mutation_exit_67(self) -> None:
        failure = self.policy["stage3h_failure_contract"]
        self.assertEqual(failure["prior_helper_invocation_count"], 1)
        self.assertEqual(failure["prior_helper_exit_code"], 67)
        self.assertEqual(failure["prior_helper_exit_name"], "EXIT_ROOT_PREFLIGHT")
        self.assertEqual(failure["failure_phase"], "pre_mutation")
        for field in (
            "root_owner_write_window_open_count",
            "root_mode_change_count",
            "staging_create_count",
            "target_create_count",
            "web_operation_count",
            "business_side_effect_count",
        ):
            self.assertEqual(failure[field], 0, field)

    def test_recovery_is_one_new_binary_call_and_fail_closed_afterward(self) -> None:
        recovery = self.policy["recovery_checkpoint_contract"]
        self.assertEqual(recovery["recovery_attempt_ordinal"], 1)
        self.assertEqual(recovery["required_prior_helper_invocation_count"], 1)
        self.assertEqual(recovery["required_prior_helper_exit_code"], 67)
        self.assertEqual(recovery["required_prior_failure_phase"], "pre_mutation")
        self.assertEqual(
            recovery["required_new_binary_sha256"],
            self.policy["new_binary"]["binary_sha256"],
        )
        self.assertEqual(recovery["new_binary_max_invocation_count"], 1)
        self.assertEqual(recovery["allowed_success_exit_code"], 0)
        self.assertEqual(
            recovery["any_other_exit_decision"],
            "REJECT_NO_RETRY_NO_WEB",
        )
        self.assertEqual(
            recovery["any_side_effect_drift_decision"],
            "REJECT_NO_RECOVERY",
        )
        self.assertEqual(recovery["second_recovery_decision"], "REJECT")
        self.assertTrue(recovery["forbids_retry"])

    def test_governance_stage_does_not_install_invoke_or_operate_runtime(self) -> None:
        new_binary = self.policy["new_binary"]
        self.assertFalse(new_binary["installed"])
        self.assertFalse(new_binary["invoked"])
        self.assertTrue(self.policy["governance_session_cannot_install_helper"])
        self.assertTrue(self.policy["governance_session_cannot_invoke_helper"])
        self.assertTrue(self.policy["governance_session_cannot_install_release"])
        self.assertFalse(self.policy["web_operations_allowed"])
        self.assertFalse(self.policy["database_operations_allowed"])


class F464InheritedProvenanceRecoveryGovernancePolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy(PROVENANCE_RECOVERY_POLICY_ID)

    def test_policy_is_canonical_and_exact_three_file_scope(self) -> None:
        canonical = json.dumps(
            self.policy,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            PROVENANCE_RECOVERY_POLICY_CANONICAL_SHA256,
        )
        self.assertEqual(self.policy["base_governance_commit"], PROVENANCE_RECOVERY_BASE_COMMIT)
        self.assertEqual(
            self.policy["allowed_governance_files"],
            [
                "docs/EXECUTION_KERNEL.md",
                "scripts/n6_f464_privileged_materialize_and_install_v2.c",
                "tests/test_n6_f464_immutable_release_installer_governance.py",
            ],
        )

    def test_provenance_gate_happy_missing_extra_and_different(self) -> None:
        self.assertEqual(
            provenance_fingerprint(PROVENANCE_NAME, PROVENANCE_RAW),
            PROVENANCE_FINGERPRINT_SHA256,
        )
        self.assertTrue(exact_provenance_gate({PROVENANCE_NAME: PROVENANCE_RAW}))
        self.assertFalse(exact_provenance_gate({}))
        self.assertFalse(
            exact_provenance_gate(
                {
                    PROVENANCE_NAME: PROVENANCE_RAW,
                    "user.extra": b"x",
                }
            )
        )
        self.assertFalse(
            exact_provenance_gate({PROVENANCE_NAME: PROVENANCE_RAW + b"\x00"})
        )
        gate = self.policy["provenance_gate"]
        self.assertEqual(gate["missing_decision"], "REJECT")
        self.assertEqual(gate["extra_decision"], "REJECT")
        self.assertEqual(gate["different_decision"], "REJECT")
        self.assertFalse(gate["setxattr_allowed"])
        self.assertFalse(gate["removexattr_allowed"])

    def test_historical_staging_is_exact_and_never_reused(self) -> None:
        staging = self.policy["historical_staging_exact"]
        self.assertEqual(staging["device"], 16777232)
        self.assertEqual(staging["inode"], 320375768)
        self.assertEqual(staging["uid"], 501)
        self.assertEqual(staging["gid"], 20)
        self.assertEqual(staging["mode"], "0700")
        self.assertEqual(staging["entry_count"], 0)
        self.assertEqual(staging["extended_acl_entry_count"], 0)
        self.assertEqual(staging["xattr_names"], [PROVENANCE_NAME])
        self.assertEqual(staging["provenance_raw_hex"], PROVENANCE_RAW.hex().upper())
        self.assertEqual(
            staging["xattr_fingerprint_sha256"],
            PROVENANCE_FINGERPRINT_SHA256,
        )
        for field in (
            "delete_allowed",
            "overwrite_allowed",
            "reuse_allowed",
            "rename_allowed",
            "population_allowed",
        ):
            self.assertFalse(staging[field], field)
        self.assertNotEqual(staging["name"], self.policy["new_staging_name"])
        self.assertEqual(
            Path(staging["path"]).parent,
            Path(self.policy["new_staging_path"]).parent,
        )

    def test_recovery_is_only_for_exact_stage3j_exit71(self) -> None:
        binding = self.policy["stage3j_recovery_binding"]
        self.assertEqual(
            binding["required_prior_binary_sha256"],
            STAGE3J_HELPER_BINARY_SHA256,
        )
        self.assertEqual(binding["required_prior_invocation_count"], 1)
        self.assertEqual(binding["required_prior_exit_code"], 71)
        self.assertEqual(binding["required_prior_exit_name"], "EXIT_STAGING_CREATE")
        self.assertEqual(
            binding["required_prior_failure_phase"],
            "post_staging_create_pre_materialize",
        )
        self.assertEqual(binding["any_prior_exit_other_than_71_decision"], "REJECT")
        self.assertEqual(binding["second_recovery_decision"], "REJECT")
        self.assertEqual(binding["old_binary_replay_decision"], "REJECT")

    def test_old_binary_replay_and_second_recovery_are_forbidden(self) -> None:
        old = self.policy["old_stage3j_binary"]
        self.assertEqual(old["sha256"], STAGE3J_HELPER_BINARY_SHA256)
        self.assertEqual(old["prior_invocation_count"], 1)
        self.assertEqual(old["prior_exit_code"], 71)
        self.assertFalse(old["future_invocation_allowed"])
        self.assertFalse(old["future_replay_allowed"])
        self.assertFalse(old["future_retry_allowed"])
        recovery = self.policy["recovery_checkpoint_contract"]
        self.assertEqual(recovery["new_binary_max_invocation_count"], 1)
        self.assertEqual(recovery["second_recovery_decision"], "REJECT")
        self.assertTrue(recovery["forbids_retry"])
        self.assertEqual(
            recovery["required_new_binary_sha256"],
            self.policy["new_binary"]["binary_sha256"],
        )

    def test_governance_has_zero_runtime_or_helper_operations(self) -> None:
        self.assertTrue(self.policy["governance_session_cannot_install_helper"])
        self.assertTrue(self.policy["governance_session_cannot_invoke_helper"])
        self.assertTrue(self.policy["governance_session_cannot_install_release"])
        self.assertFalse(self.policy["web_or_launchagent_operations_allowed"])
        self.assertFalse(self.policy["database_operations_allowed"])
        self.assertFalse(self.policy["evaluator_operations_allowed"])
        self.assertFalse(self.policy["virtual_executor_operations_allowed"])
        self.assertFalse(self.policy["runner_canary_deepseek_operations_allowed"])
        self.assertFalse(self.policy["n1_n5_business_operations_allowed"])


class F464FullWidthUstarRecoveryGovernancePolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy(FULL_WIDTH_RECOVERY_POLICY_ID)
        cls.text = SOURCE.read_text(encoding="utf-8")

    def test_policy_is_canonical_and_exact_three_file_scope(self) -> None:
        canonical = json.dumps(
            self.policy,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            FULL_WIDTH_RECOVERY_POLICY_CANONICAL_SHA256,
        )
        self.assertEqual(
            self.policy["base_governance_commit"],
            FULL_WIDTH_RECOVERY_BASE_COMMIT,
        )
        self.assertEqual(
            self.policy["base_governance_tree"],
            FULL_WIDTH_RECOVERY_BASE_TREE,
        )
        self.assertEqual(self.policy["activation_state_before_event_count"], 55)
        self.assertEqual(
            self.policy["activation_state_before_sha256"],
            "fe0099e86001cca164d2df5c59d0e6f8435a1c4f4034114c65594ff43b0bcd1f",
        )
        self.assertEqual(
            self.policy["activation_state_before_tail_event_sha256"],
            "b9ad5cc5d7395ce56a3e2ba1e2cb3eaaafd4fc2654e5e48c1d5c1c63740b6d5e",
        )
        self.assertEqual(
            self.policy["allowed_governance_files"],
            [
                "docs/EXECUTION_KERNEL.md",
                "scripts/n6_f464_privileged_materialize_and_install_v2.c",
                "tests/test_n6_f464_immutable_release_installer_governance.py",
            ],
        )

    def test_stage3l_binding_is_exactly_one_exit72_at_first_full_width_name(
        self,
    ) -> None:
        failure = self.policy["stage3l_failure_contract"]
        self.assertEqual(failure["prior_helper_binary_sha256"], STAGE3L_HELPER_BINARY_SHA256)
        self.assertEqual(failure["prior_helper_invocation_count"], 1)
        self.assertEqual(failure["prior_helper_exit_code"], 72)
        self.assertEqual(failure["prior_helper_exit_name"], "EXIT_MATERIALIZE")
        self.assertTrue(failure["prior_lease_consumed"])
        self.assertFalse(failure["prior_retry_allowed"])
        self.assertEqual(failure["failure_archive_physical_header_index"], 585)
        self.assertEqual(failure["failure_manifest_file_index"], 573)
        self.assertEqual(failure["materialized_manifest_file_count"], 572)
        self.assertEqual(failure["materialized_directory_count"], 8)
        self.assertEqual(failure["failed_path_utf8_length_bytes"], 100)
        self.assertEqual(failure["failed_ustar_name_field_length_bytes"], 100)
        self.assertFalse(failure["failed_ustar_name_has_nul"])
        self.assertFalse(failure["failed_path_has_pax_override"])
        self.assertFalse(failure["failed_file_created"])

    def test_tar_path_accepts_legal_full_width_name_only(self) -> None:
        function = re.search(
            r"static bool tar_path\(.*?^\}",
            self.text,
            re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(function)
        self.assertNotIn(
            "name_length == sizeof(header->name)",
            function.group(0),
        )
        self.assertIn(
            "prefix_length == sizeof(header->prefix)",
            function.group(0),
        )
        self.assertIn("safe_relative_path(result)", function.group(0))
        self.assertIn('"%.*s/%.*s"', function.group(0))
        failed_path = self.policy["stage3l_failure_contract"]["failed_path"].encode()
        self.assertEqual(len(failed_path), 100)
        self.assertEqual(
            bounded_ustar_path(failed_path),
            failed_path.decode(),
        )
        self.assertIsNone(bounded_ustar_path(b"a" * 101))
        for unsafe in (b"/absolute", b"../escape", b"a/../../escape", b"a//b"):
            self.assertIsNone(bounded_ustar_path(unsafe), unsafe)
        fix = self.policy["ustar_name_fix"]
        self.assertTrue(fix["legal_name_length_100_without_nul_allowed"])
        self.assertFalse(fix["new_pax_support_added"])
        self.assertFalse(fix["gnu_longname_support_added"])

    def test_two_failed_stagings_are_read_only_and_recovery3_is_unique(self) -> None:
        historical = self.policy["historical_staging_exact"]
        recovery2 = self.policy["failed_recovery2_staging_exact"]
        recovery3 = Path(self.policy["new_staging_path"])
        flattened = re.sub(r'"\s*"', "", self.text)
        for staging in (historical["name"], recovery2["name"], recovery3.name):
            self.assertIn(staging, flattened)
        self.assertNotEqual(historical["name"], recovery2["name"])
        self.assertNotEqual(historical["name"], recovery3.name)
        self.assertNotEqual(recovery2["name"], recovery3.name)
        self.assertNotIn("mkdirat(rootfd, kHistoricalStagingName", self.text)
        self.assertNotIn("mkdirat(rootfd, kFailedRecovery2StagingName", self.text)
        self.assertEqual(self.text.count("mkdirat(rootfd, kStagingName, 0700)"), 1)
        rename = re.search(
            r"if \(renameatx_np\(.*?\) != 0\)",
            self.text,
            re.DOTALL,
        )
        self.assertIsNotNone(rename)
        self.assertIn("kStagingName", rename.group(0))
        self.assertNotIn("kHistoricalStagingName", rename.group(0))
        self.assertNotIn("kFailedRecovery2StagingName", rename.group(0))
        self.assertGreaterEqual(
            self.text.count("exact_historical_staging(historical_stagefd)"),
            2,
        )
        self.assertGreaterEqual(
            self.text.count(
                "exact_failed_recovery2_staging(failed_recovery2_stagefd)"
            ),
            2,
        )

    def test_live_failed_stagings_match_frozen_metadata_and_prefix(self) -> None:
        historical = self.policy["historical_staging_exact"]
        historical_path = Path(historical["path"])
        historical_stat = historical_path.stat()
        self.assertEqual(historical_stat.st_dev, historical["device"])
        self.assertEqual(historical_stat.st_ino, historical["inode"])
        self.assertEqual(historical_stat.st_uid, historical["uid"])
        self.assertEqual(historical_stat.st_gid, historical["gid"])
        self.assertEqual(stat.S_IMODE(historical_stat.st_mode), 0o700)
        self.assertEqual(list(historical_path.iterdir()), [])

        recovery2 = self.policy["failed_recovery2_staging_exact"]
        recovery2_path = Path(recovery2["path"])
        recovery2_stat = recovery2_path.stat()
        self.assertEqual(recovery2_stat.st_dev, recovery2["device"])
        self.assertEqual(recovery2_stat.st_ino, recovery2["inode"])
        self.assertEqual(recovery2_stat.st_uid, recovery2["uid"])
        self.assertEqual(recovery2_stat.st_gid, recovery2["gid"])
        self.assertEqual(stat.S_IMODE(recovery2_stat.st_mode), 0o700)
        entries = list(recovery2_path.rglob("*"))
        files = [path for path in entries if path.is_file()]
        directories = [path for path in entries if path.is_dir()]
        self.assertEqual(len(files), recovery2["file_count"])
        self.assertEqual(len(directories), recovery2["directory_count"])
        self.assertEqual(
            [path for path in entries if path.is_symlink()],
            [],
        )
        self.assertEqual(
            {stat.S_IMODE(path.stat().st_mode) for path in files},
            {0o444},
        )
        self.assertEqual(
            {stat.S_IMODE(path.stat().st_mode) for path in directories},
            {0o755},
        )
        self.assertEqual(
            {(path.stat().st_uid, path.stat().st_gid) for path in entries},
            {(501, 20)},
        )
        self.assertEqual(
            failed_staging_entry_records_sha256(recovery2_path),
            recovery2["entry_records_sha256"],
        )
        ordered_paths = b"".join(
            (
                str(path.relative_to(recovery2_path)) + "\0"
            ).encode()
            for path in sorted(
                entries,
                key=lambda item: os.fsencode(str(item.relative_to(recovery2_path))),
            )
        )
        self.assertEqual(
            hashlib.sha256(ordered_paths).hexdigest(),
            recovery2["ordered_paths_nul_sha256"],
        )
        xattr = subprocess.run(
            ["xattr", "-lr", str(recovery2_path)],
            check=True,
            capture_output=True,
        ).stdout
        self.assertEqual(
            hashlib.sha256(xattr).hexdigest(),
            recovery2["recursive_xattr_listing_sha256"],
        )
        self.assertEqual(
            xattr.count(b"com.apple.provenance:"),
            recovery2["provenance_entry_count_root_and_children"],
        )
        acl_listing = subprocess.run(
            ["ls", "-lde", str(historical_path), str(recovery2_path), *map(str, entries)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertEqual(len(acl_listing), 2 + len(entries))
        self.assertFalse(any("+" in line.split()[0] for line in acl_listing))
        self.assertFalse(Path(self.policy["target_release_path"]).exists())
        self.assertTrue(Path(self.policy["new_staging_path"]).is_dir())
        promote = load_policy(PROMOTE_RECOVERY_POLICY_ID)
        self.assertFalse(Path(promote["new_staging_path"]).exists())

    def test_first_572_materialized_files_match_manifest_exactly(self) -> None:
        recovery2 = self.policy["failed_recovery2_staging_exact"]
        recovery2_path = Path(recovery2["path"])
        records = [record for record in MANIFEST.read_bytes().split(b"\0") if record]
        prefix = b"\0".join(records[:572]) + b"\0"
        self.assertEqual(
            hashlib.sha256(prefix).hexdigest(),
            recovery2["first_572_manifest_records_sha256"],
        )
        verified: list[dict[str, Any]] = []
        for index, record in enumerate(records[:572], 1):
            descriptor, path_bytes = record.split(b"\t", 1)
            mode, object_type, oid = descriptor.decode("ascii").split(" ")
            path = path_bytes.decode("utf-8")
            materialized = recovery2_path / path
            content = materialized.read_bytes()
            self.assertEqual(object_type, "blob")
            self.assertEqual(
                hashlib.sha1(
                    f"blob {len(content)}\0".encode() + content
                ).hexdigest(),
                oid,
            )
            sealed_mode = "0555" if mode == "100755" else "0444"
            self.assertEqual(
                f"{stat.S_IMODE(materialized.stat().st_mode):04o}",
                sealed_mode,
            )
            verified.append(
                {
                    "index": index,
                    "path": path,
                    "oid": oid,
                    "manifest_mode": mode,
                    "materialized_mode": sealed_mode,
                }
            )
        canonical = b"".join(
            json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            + b"\n"
            for row in verified
        )
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            recovery2["first_572_materialized_verification_sha256"],
        )

    def test_old_binaries_are_disabled_and_recovery3_is_single_use(self) -> None:
        old = self.policy["permanently_disabled_old_binaries"]
        self.assertEqual(len(old), 5)
        self.assertIn(STAGE3L_HELPER_BINARY_SHA256, {row["sha256"] for row in old})
        for row in old:
            self.assertFalse(row["future_invocation_allowed"])
            self.assertFalse(row["future_replay_allowed"])
            self.assertFalse(row["future_retry_allowed"])
        recovery = self.policy["recovery_checkpoint_contract"]
        self.assertEqual(recovery["required_prior_helper_invocation_count"], 1)
        self.assertEqual(recovery["required_prior_helper_exit_code"], 72)
        self.assertEqual(recovery["required_prior_failure_archive_physical_header_index"], 585)
        self.assertEqual(recovery["required_prior_failure_manifest_file_index"], 573)
        self.assertEqual(recovery["new_binary_max_invocation_count"], 1)
        self.assertEqual(recovery["second_recovery3_decision"], "REJECT")
        self.assertTrue(recovery["forbids_retry"])

    def test_new_binary_is_attested_but_not_installed_or_invoked(self) -> None:
        binary = self.policy["new_binary"]
        path = Path(self.policy["temporary_compiled_helper_path"])
        historical_source = subprocess.run(
            [
                "git",
                "show",
                f"{PROMOTE_RECOVERY_BASE_COMMIT}:"
                "scripts/n6_f464_privileged_materialize_and_install_v2.c",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        self.assertEqual(
            hashlib.sha256(historical_source).hexdigest(),
            binary["source_sha256"],
        )
        self.assertNotEqual(sha256(SOURCE), binary["source_sha256"])
        self.assertEqual(sha256(path), binary["binary_sha256"])
        metadata = path.stat()
        self.assertEqual(stat.S_IMODE(metadata.st_mode), 0o500)
        self.assertEqual(metadata.st_uid, 501)
        self.assertEqual(metadata.st_gid, 20)
        codesign = subprocess.run(
            ["codesign", "-dv", "--verbose=4", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn(f"CDHash={binary['codesign_cdhash']}", codesign.stderr)
        self.assertFalse(binary["installed"])
        self.assertFalse(binary["invoked"])
        self.assertTrue(self.policy["governance_session_cannot_invoke_helper"])
        self.assertFalse(
            self.policy[
                "web_evaluator_virtual_executor_or_launchagent_operations_allowed"
            ]
        )
        self.assertFalse(self.policy["database_operations_allowed"])


class F464Recovery4PromotePostconditionGovernancePolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy(PROMOTE_RECOVERY_POLICY_ID)
        cls.text = SOURCE.read_text(encoding="utf-8")
        cls.stage3n_text = subprocess.run(
            [
                "git",
                "show",
                f"{PROMOTE_RECOVERY_BASE_COMMIT}:"
                "scripts/n6_f464_privileged_materialize_and_install_v2.c",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def test_policy_is_canonical_exact_base_and_three_file_scope(self) -> None:
        canonical = json.dumps(
            self.policy,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            PROMOTE_RECOVERY_POLICY_CANONICAL_SHA256,
        )
        self.assertEqual(
            self.policy["base_governance_commit"],
            PROMOTE_RECOVERY_BASE_COMMIT,
        )
        self.assertEqual(
            self.policy["base_governance_tree"],
            PROMOTE_RECOVERY_BASE_TREE,
        )
        self.assertEqual(self.policy["activation_state_before_event_count"], 61)
        self.assertEqual(
            self.policy["activation_state_before_sha256"],
            "ffc034539d0dc752b67b7fed90f0a106e4122ae2eed29ab65a03a52e616647b9",
        )
        self.assertEqual(
            self.policy["activation_state_before_tail_event_sha256"],
            "f5b2e9c7c8d7f6dccb8feb399a18719c3e2edeaecd1ea95d149b1601931d4bae",
        )
        self.assertEqual(
            self.policy["allowed_governance_files"],
            [
                "docs/EXECUTION_KERNEL.md",
                "scripts/n6_f464_privileged_materialize_and_install_v2.c",
                "tests/test_n6_f464_immutable_release_installer_governance.py",
            ],
        )

    def test_stage3n_exact_failure_has_primary_73_and_secondary_false_negative(
        self,
    ) -> None:
        failure = self.policy["stage3n_failure_contract"]
        self.assertEqual(
            failure["prior_helper_binary_sha256"],
            STAGE3N_HELPER_BINARY_SHA256,
        )
        self.assertEqual(failure["prior_helper_invocation_count"], 1)
        self.assertEqual(failure["prior_helper_reported_exit_code"], 75)
        self.assertEqual(failure["primary_exit_code"], 73)
        self.assertEqual(failure["primary_exit_name"], "EXIT_PROMOTE")
        self.assertEqual(
            failure["primary_failure"],
            "renameatx_np_returned_minus_one_with_staging_root_mode_0555",
        )
        self.assertEqual(failure["secondary_exit_code"], 75)
        self.assertEqual(
            failure["secondary_failure"],
            "recovery2_shared_open_file_description_offset_false_negative",
        )
        self.assertTrue(failure["secondary_overwrote_primary_in_old_binary"])
        self.assertTrue(failure["prior_lease_consumed"])
        self.assertFalse(failure["prior_retry_allowed"])
        seal = self.stage3n_text.index("fchmod(stagefd, 0555)")
        rename = self.stage3n_text.index("if (renameatx_np(")
        overwrite = self.stage3n_text.index(
            "if (!failed_recovery2_staging_unchanged) "
            "result = EXIT_POSTCONDITION;"
        )
        self.assertLess(seal, rename)
        self.assertLess(rename, overwrite)
        self.assertIn(
            "DIR *directory = fdopendir(dup(dirfd));",
            self.stage3n_text,
        )

    def test_all_repeated_recursive_scans_have_independent_open_descriptions(
        self,
    ) -> None:
        self.assertNotIn("fdopendir(dup(dirfd))", self.text)
        for function_name in (
            "count_failed_recovery2_tree",
            "count_exact_release_tree",
            "seal_and_count",
        ):
            function = re.search(
                rf"static bool {function_name}\(.*?^\}}",
                self.text,
                re.DOTALL | re.MULTILINE,
            )
            self.assertIsNotNone(function)
            self.assertIn('openat(\n        dirfd,\n        "."', function.group(0))
            self.assertIn("fdopendir(scanfd)", function.group(0))

    def test_same_recovery2_fd_scans_572_8_twice_and_primary_wins(self) -> None:
        recovery2_path = self.policy["failed_recovery2_staging_exact"]["path"]
        source_path = str(SOURCE).replace("\\", "\\\\").replace('"', '\\"')
        recovery2_literal = recovery2_path.replace("\\", "\\\\").replace('"', '\\"')
        harness = f"""
#define main installer_main_not_called
#include "{source_path}"
#undef main
int main(void) {{
    int fd = open(
        "{recovery2_literal}",
        O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
    );
    unsigned files_first = 0;
    unsigned directories_first = 0;
    unsigned files_second = 0;
    unsigned directories_second = 0;
    bool first = fd >= 0 && count_failed_recovery2_tree(
        fd,
        &files_first,
        &directories_first
    );
    bool second = fd >= 0 && count_failed_recovery2_tree(
        fd,
        &files_second,
        &directories_second
    );
    int selected = final_exit_code(EXIT_PROMOTE, EXIT_POSTCONDITION);
    if (fd >= 0) close(fd);
    printf(
        "%d %u %u %d %u %u %d\\n",
        first,
        files_first,
        directories_first,
        second,
        files_second,
        directories_second,
        selected
    );
    return !(first && second &&
             files_first == 572 && directories_first == 8 &&
             files_second == 572 && directories_second == 8 &&
             selected == EXIT_PROMOTE);
}}
"""
        with tempfile.TemporaryDirectory(
            prefix="n6_f464_recovery4_scan_test."
        ) as directory:
            source = Path(directory) / "scan_harness.c"
            binary = Path(directory) / "scan_harness"
            source.write_text(harness, encoding="utf-8")
            subprocess.run(
                [
                    "xcrun",
                    "clang",
                    "-std=c11",
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    str(source),
                    "-o",
                    str(binary),
                ],
                check=True,
                cwd=ROOT,
            )
            result = subprocess.run(
                [str(binary)],
                check=True,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.stdout, "1 572 8 1 572 8 73\n")

    def test_rename_mode_order_failure_seal_and_errno_reporting(self) -> None:
        extract = self.text.index("if (!extract_and_verify(rootfd, stagefd))")
        work_mode = self.text.index("exact_staging_work_directory(stagefd)")
        rename = self.text.index("if (renameatx_np(", extract)
        sealed = self.text.index("fchmod(stagefd, 0555)", rename)
        synced = self.text.index("fsync(stagefd)", sealed)
        target = self.text.index("exact_sealed_full_release_tree(targetfd)")
        self.assertLess(work_mode, rename)
        self.assertLess(rename, sealed)
        self.assertLess(sealed, synced)
        self.assertLess(synced, target)
        finish = self.text.index("finish:")
        failure_seal = self.text.index(
            "if (staging_created && !promoted && stagefd >= 0 "
            "&& !stage_root_sealed)",
            finish,
        )
        self.assertLess(finish, failure_seal)
        self.assertIn("primary_errno = errno;", self.text)
        self.assertIn("postcondition_errno", self.text)
        self.assertIn(
            "return final_exit_code(primary_result, postcondition_result);",
            self.text,
        )
        self.assertIn(
            '"primary_exit=%d primary_errno=%d "',
            self.text,
        )
        self.assertIn(
            '"postcondition_exit=%d postcondition_errno=%d\\n"',
            self.text,
        )

    def test_three_failed_stagings_are_exact_and_recovery4_is_unique(self) -> None:
        historical = self.policy["historical_staging_exact"]
        recovery2 = self.policy["failed_recovery2_staging_exact"]
        recovery3 = self.policy["failed_recovery3_staging_exact"]
        recovery4 = Path(self.policy["new_staging_path"])
        paths = [Path(row["path"]) for row in (historical, recovery2, recovery3)]
        self.assertEqual(len({path.name for path in [*paths, recovery4]}), 4)
        self.assertEqual(paths[0].stat().st_ino, 320375768)
        self.assertEqual(list(paths[0].iterdir()), [])
        self.assertEqual(paths[1].stat().st_ino, 320422668)
        self.assertEqual(
            failed_staging_entry_records_sha256(paths[1]),
            "0d7c85da4be58289d4e08cb44daf6471dc9444bb81d83f989084a04e50809db7",
        )
        self.assertEqual(paths[2].stat().st_ino, 320439773)
        self.assertEqual(stat.S_IMODE(paths[2].stat().st_mode), 0o555)
        entries = list(paths[2].rglob("*"))
        self.assertEqual(len([path for path in entries if path.is_file()]), 6240)
        self.assertEqual(len([path for path in entries if path.is_dir()]), 45)
        self.assertEqual(
            sum(
                bool(stat.S_IMODE(path.stat().st_mode) & 0o222)
                for path in [paths[2], *entries]
            ),
            0,
        )
        self.assertEqual(
            failed_staging_entry_records_sha256(paths[2]),
            recovery3["entry_records_sha256"],
        )
        self.assertEqual(
            full_manifest_verification_sha256(paths[2]),
            recovery3["manifest_verification_sha256"],
        )
        self.assertEqual(
            {(path.stat().st_uid, path.stat().st_gid) for path in [paths[2], *entries]},
            {(501, 20)},
        )
        xattr_listing = subprocess.run(
            ["xattr", "-lr", str(paths[2])],
            check=True,
            capture_output=True,
        ).stdout
        self.assertEqual(
            hashlib.sha256(xattr_listing).hexdigest(),
            recovery3["recursive_xattr_listing_sha256"],
        )
        self.assertEqual(
            xattr_listing.count(b"com.apple.provenance:"),
            recovery3["provenance_entry_count_root_and_children"],
        )
        acl_listing = subprocess.run(
            ["find", str(paths[2]), "-exec", "ls", "-lde", "{}", "+"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertFalse(
            any(
                bool(line.split()) and "+" in line.split()[0]
                for line in acl_listing
            )
        )
        self.assertFalse(recovery4.exists())
        self.assertFalse(Path(self.policy["target_release_path"]).exists())
        flattened = re.sub(r'"\s*"', "", self.text)
        for path in [*paths, recovery4]:
            self.assertIn(path.name, flattened)
        for constant in (
            "kHistoricalStagingName",
            "kFailedRecovery2StagingName",
            "kFailedRecovery3StagingName",
        ):
            self.assertNotIn(f"mkdirat(rootfd, {constant}", self.text)
        self.assertEqual(self.text.count("mkdirat(rootfd, kStagingName, 0700)"), 1)

    def test_old_binary_replay_is_disabled_and_recovery4_is_single_use(self) -> None:
        old = self.policy["permanently_disabled_old_binaries"]
        self.assertEqual(len(old), 6)
        self.assertIn(STAGE3N_HELPER_BINARY_SHA256, {row["sha256"] for row in old})
        for row in old:
            self.assertFalse(row["future_invocation_allowed"])
            self.assertFalse(row["future_replay_allowed"])
            self.assertFalse(row["future_retry_allowed"])
        checkpoint = self.policy["recovery_checkpoint_contract"]
        self.assertEqual(checkpoint["required_prior_helper_invocation_count"], 1)
        self.assertEqual(checkpoint["required_prior_helper_reported_exit_code"], 75)
        self.assertEqual(checkpoint["required_prior_primary_exit_code"], 73)
        self.assertEqual(checkpoint["new_binary_max_invocation_count"], 1)
        self.assertEqual(checkpoint["second_recovery4_decision"], "REJECT")
        self.assertTrue(checkpoint["forbids_retry"])

    def test_filesystem_sha_is_lineage_only_and_full_closure_is_predicate(
        self,
    ) -> None:
        contract = self.policy["filesystem_acceptance_contract"]
        self.assertEqual(
            contract["attested_filesystem_sha256"],
            "4e46cb1fcd73a452f6a3e534d0bb9dc7ddc011fea4937510991cd9b8e51a79fa",
        )
        self.assertEqual(
            contract["attested_filesystem_sha256_role"],
            "lineage_only_not_recomputed_by_helper",
        )
        self.assertFalse(contract["claims_attested_filesystem_sha256_recomputed"])
        self.assertTrue(contract["content_acceptance_not_relaxed"])
        self.assertEqual(
            contract["actual_acceptance_predicate"],
            [
                "frozen_archive_sha256",
                "frozen_manifest_sha256",
                "full_archive_checksum_type_path_mode_traversal",
                "all_6240_manifest_paths_exact",
                "all_6240_git_blob_oids_recomputed",
                "all_file_modes_exact_0444_or_0555",
                "all_45_directories_exact_0555_after_promotion",
                "all_entries_uid501_gid20",
                "all_entries_exact_provenance_xattr",
                "all_entries_extended_acl_zero",
                "no_symlink_no_extra_file_or_directory",
            ],
        )
        for function in (
            "verify_full_manifest_tree",
            "count_exact_release_tree",
            "exact_sealed_full_release_tree",
        ):
            self.assertIn(f"static bool {function}", self.text)

    def test_new_binary_is_attested_only_and_not_invoked(self) -> None:
        binary = self.policy["new_binary"]
        path = Path(self.policy["temporary_compiled_helper_path"])
        self.assertEqual(sha256(SOURCE), binary["source_sha256"])
        self.assertEqual(sha256(path), binary["binary_sha256"])
        metadata = path.stat()
        self.assertEqual(stat.S_IMODE(metadata.st_mode), 0o500)
        self.assertEqual(metadata.st_uid, 501)
        self.assertEqual(metadata.st_gid, 20)
        codesign = subprocess.run(
            ["codesign", "-dv", "--verbose=4", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn(f"CDHash={binary['codesign_cdhash']}", codesign.stderr)
        attestation = json.loads(
            Path(self.policy["temporary_helper_attestation_path"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            attestation["policy_canonical_sha256"],
            PROMOTE_RECOVERY_POLICY_CANONICAL_SHA256,
        )
        self.assertEqual(attestation["helper_source_sha256"], binary["source_sha256"])
        self.assertEqual(attestation["helper_binary_sha256"], binary["binary_sha256"])
        self.assertEqual(attestation["helper_codesign_cdhash"], binary["codesign_cdhash"])
        self.assertFalse(attestation["installed"])
        self.assertFalse(attestation["invoked"])
        self.assertFalse(binary["installed"])
        self.assertFalse(binary["invoked"])
        self.assertEqual(binary["max_future_invocation_count"], 1)
        self.assertTrue(self.policy["governance_session_cannot_invoke_helper"])


class F464FrozenArchiveStaticFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()

    def test_frozen_artifact_hashes_and_attestation(self) -> None:
        exact = self.policy["required_exact_values"]
        self.assertEqual(sha256(ARCHIVE), exact["archive_sha256"])
        self.assertEqual(sha256(MANIFEST), exact["manifest_sha256"])
        self.assertEqual(
            sha256(RELEASE_ATTESTATION),
            exact["release_attestation_sha256"],
        )
        self.assertEqual(sha256(BUNDLE), exact["bundle_file_sha256"])
        attestation = json.loads(RELEASE_ATTESTATION.read_text(encoding="utf-8"))
        bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
        self.assertEqual(attestation["release_commit"], exact["release_commit"])
        self.assertEqual(attestation["release_tree"], exact["release_tree"])
        self.assertEqual(attestation["filesystem_sha256"], exact["filesystem_sha256"])
        self.assertEqual(attestation["bundle_file_sha256"], exact["bundle_file_sha256"])
        self.assertEqual(attestation["bundle_sha256"], exact["bundle_internal_sha256"])
        self.assertEqual(bundle["bundle_sha256"], exact["bundle_internal_sha256"])
        self.assertEqual(attestation["file_count"], 6240)
        self.assertEqual(attestation["directory_count"], 45)
        self.assertEqual(attestation["writable_entry_count"], 0)

    def test_archive_success_fixture_validates_every_blob(self) -> None:
        manifest = manifest_entries()
        self.assertEqual(len(manifest), 6240)
        manifest_index = 0
        type_counts: dict[str, int] = {}
        mode_counts: dict[tuple[str, int], int] = {}
        pax_global = 0
        pax_extended = 0
        override: str | None = None
        physical_header_index = 0
        full_width_entries: list[dict[str, Any]] = []
        with ARCHIVE.open("rb") as handle:
            while True:
                header = handle.read(512)
                physical_header_index += 1
                self.assertEqual(len(header), 512)
                if not any(header):
                    self.assertEqual(handle.read(512), bytes(512))
                    self.assertEqual(set(handle.read()), {0})
                    break
                self.assertEqual(header[257:265], b"ustar\0" + b"00")
                self.assertTrue(valid_checksum(header))
                entry_type = chr(header[156]) if header[156] else "0"
                size = parse_octal(header[124:136])
                mode = parse_octal(header[100:108])
                type_counts[entry_type] = type_counts.get(entry_type, 0) + 1
                mode_counts[(entry_type, mode)] = (
                    mode_counts.get((entry_type, mode), 0) + 1
                )
                payload = handle.read((size + 511) // 512 * 512)
                self.assertEqual(len(payload), (size + 511) // 512 * 512)
                if entry_type in ("g", "x"):
                    records = parse_pax(payload[:size])
                    if entry_type == "g":
                        self.assertEqual(records, {"comment": "f4641e9c4cd4dff1a817f779d28007fe7cdffe62"})
                        pax_global += 1
                    else:
                        self.assertEqual(set(records), {"path"})
                        self.assertTrue(safe_relative_path(records["path"]))
                        self.assertIsNone(override)
                        override = records["path"]
                        pax_extended += 1
                    continue
                self.assertIn(entry_type, ("0", "5"))
                self.assertEqual(header[157:257].rstrip(b"\0"), b"")
                prefix = header[345:500].rstrip(b"\0").decode("utf-8")
                name = header[0:100].rstrip(b"\0").decode("utf-8").rstrip("/")
                used_override = override is not None
                path = override or (f"{prefix}/{name}" if prefix else name)
                override = None
                self.assertTrue(safe_relative_path(path))
                if entry_type == "5":
                    self.assertEqual(size, 0)
                    self.assertIn(mode, (0o755, 0o775))
                    continue
                expected_path, expected_oid, expected_mode = manifest[manifest_index]
                manifest_index += 1
                if b"\0" not in header[0:100] and not used_override:
                    self.assertEqual(len(header[0:100]), 100)
                    full_width_entries.append(
                        {
                            "manifest_index": manifest_index,
                            "physical_header_index": physical_header_index,
                            "prefix_length": len(header[345:500].rstrip(b"\0")),
                            "path": path,
                        }
                    )
                self.assertEqual(path, expected_path)
                self.assertEqual(0o755 if mode & 0o111 else 0o644, expected_mode)
                content = payload[:size]
                blob_header = f"blob {size}\0".encode()
                self.assertEqual(
                    hashlib.sha1(blob_header + content).hexdigest(),
                    expected_oid,
                )
        self.assertEqual(manifest_index, 6240)
        self.assertEqual(
            type_counts,
            {"g": 1, "x": 108, "5": 45, "0": 6240},
        )
        self.assertEqual(pax_global, 1)
        self.assertEqual(pax_extended, 108)
        self.assertEqual(mode_counts[("0", 0o664)], 6236)
        self.assertEqual(mode_counts[("0", 0o775)], 4)
        self.assertEqual(mode_counts[("5", 0o775)], 45)
        recovery = load_policy(FULL_WIDTH_RECOVERY_POLICY_ID)
        traversal = recovery["archive_traversal_contract"]
        self.assertEqual(len(full_width_entries), 17)
        self.assertEqual(
            full_width_entries,
            traversal["full_width_ustar_entries"],
        )
        self.assertEqual(full_width_entries[0]["manifest_index"], 573)
        self.assertEqual(full_width_entries[0]["physical_header_index"], 585)
        self.assertEqual(
            full_width_entries[0]["path"],
            recovery["stage3l_failure_contract"]["failed_path"],
        )

    def test_failure_fixtures_reject_checksum_pax_and_paths(self) -> None:
        with ARCHIVE.open("rb") as handle:
            header = bytearray(handle.read(512))
        self.assertTrue(valid_checksum(bytes(header)))
        header[0] ^= 1
        self.assertFalse(valid_checksum(bytes(header)))
        with self.assertRaises(ValueError):
            parse_pax(b"12 path=../x\n")
        for path in ("", "/absolute", "../escape", "a/../../escape", "a//b"):
            self.assertFalse(safe_relative_path(path), path)

    def test_fixture_does_not_touch_official_release_root(self) -> None:
        recovery = load_policy(PROVENANCE_RECOVERY_POLICY_ID)
        full_width_recovery = load_policy(FULL_WIDTH_RECOVERY_POLICY_ID)
        promote_recovery = load_policy(PROMOTE_RECOVERY_POLICY_ID)
        target = Path(recovery["target_release_path"])
        historical = Path(recovery["historical_staging_exact"]["path"])
        staging = Path(recovery["new_staging_path"])
        recovery3 = Path(full_width_recovery["new_staging_path"])
        self.assertFalse(target.exists())
        self.assertTrue(historical.is_dir())
        historical_stat = historical.stat()
        self.assertEqual(historical_stat.st_dev, 16777232)
        self.assertEqual(historical_stat.st_ino, 320375768)
        self.assertEqual(stat.S_IMODE(historical_stat.st_mode), 0o700)
        self.assertEqual(list(historical.iterdir()), [])
        self.assertTrue(staging.is_dir())
        self.assertEqual(
            len([path for path in staging.rglob("*") if path.is_file()]),
            572,
        )
        self.assertTrue(recovery3.is_dir())
        self.assertFalse(Path(promote_recovery["new_staging_path"]).exists())
        self.assertEqual(
            stat.S_IMODE((CANDIDATE_ROOT / "release").stat().st_mode),
            0o555,
        )


if __name__ == "__main__":
    unittest.main()
