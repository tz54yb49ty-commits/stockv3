from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "runtime_hot_cleanup_archive_gated_disk_governance_v1"
POLICY_BEGIN = f"<!-- policy:{POLICY_ID}:begin -->"
POLICY_END = f"<!-- policy:{POLICY_ID}:end -->"
SHA256 = "a" * 64


def load_policy() -> dict:
    kernel = (REPO_ROOT / "docs" / "EXECUTION_KERNEL.md").read_text(
        encoding="utf-8"
    )
    block = kernel.split(POLICY_BEGIN, 1)[1].split(POLICY_END, 1)[0]
    matches = re.findall(r"```json\s*(\{.*?\})\s*```", block, re.DOTALL)
    if len(matches) != 1:
        raise AssertionError("policy must contain exactly one JSON block")
    return json.loads(matches[0])


def canonical_request(policy: dict, phase_mode: str) -> dict:
    request = {
        "policy_id": POLICY_ID,
        "layer_role": "runtime_control",
        "phase_mode": phase_mode,
        "cleanup_launch_agent_label": policy["cleanup_launch_agent_label"],
        "cleanup_launch_agent_plist_path": policy[
            "cleanup_launch_agent_plist_path"
        ],
        "local_artifact_archive_root": policy["local_artifact_archive_root"],
        "database_archive_root": policy["database_archive_root"],
        "data_volume_free_target_bytes": policy[
            "data_volume_free_target_bytes"
        ],
        "retention_policy": policy["retention_policy"],
        "trade_calendar_authority": policy["trade_calendar_authority"],
        "bootout_count": 0,
        "bootstrap_count": 0,
        "kickstart_count": 0,
        "database_delete_count": 0,
        "snapshot_delete_count": 0,
        "local_artifact_delete_count": 0,
        "cleanup_job_and_pid_absent_after_wait": False,
        "archive_manifest_sha256": None,
        "batch_summary_sha256": None,
        "manifest_entry_count": 0,
        "allowlist_entry_count": 0,
        "manifest_allocated_bytes": 0,
        "allowlist_allocated_bytes": 0,
        "archive_evidence_verified": False,
        "restore_proofs_complete": False,
        "allowlist_revalidated": False,
        "delete_scope": None,
        "stop_at_free_target": False,
        "local_reclaim_completed": False,
        "data_volume_free_before_bytes": 0,
        "snapshot_candidates": [],
        "archive_required_configuration_verified": False,
        "exact_cleanup_job_loaded_without_kickstart": False,
    }
    request.update({field: True for field in policy["required_true_fields"]})
    request.update({field: False for field in policy["required_false_fields"]})

    if phase_mode == "cleanup_scheduler_quiesce":
        request["bootout_count"] = 1
        request["cleanup_job_and_pid_absent_after_wait"] = True
    elif phase_mode == "archive_verified_local_reclaim":
        request.update(
            {
                "archive_manifest_sha256": SHA256,
                "batch_summary_sha256": SHA256,
                "manifest_entry_count": 3,
                "allowlist_entry_count": 3,
                "manifest_allocated_bytes": 4096,
                "allowlist_allocated_bytes": 4096,
                "archive_evidence_verified": True,
                "restore_proofs_complete": True,
                "allowlist_revalidated": True,
                "delete_scope": "exact_manifest_entries_only",
                "stop_at_free_target": True,
                "local_artifact_delete_count": 3,
            }
        )
    elif phase_mode == "time_machine_snapshot_fallback":
        request.update(
            {
                "snapshot_delete_count": 1,
                "local_reclaim_completed": True,
                "data_volume_free_before_bytes": (
                    policy["data_volume_free_target_bytes"] - 1
                ),
                "snapshot_candidates": [
                    {
                        "name": "com.apple.TimeMachine.2026-08-21-010101.local",
                        "purgeable": True,
                    }
                ],
            }
        )
    elif phase_mode == "cleanup_scheduler_archive_gated_restore":
        request.update(
            {
                "bootstrap_count": 1,
                "archive_required_configuration_verified": True,
                "exact_cleanup_job_loaded_without_kickstart": True,
            }
        )
    return request


def evaluate(policy: dict, request: dict) -> str:
    canonical_fields = set(
        canonical_request(policy, "cleanup_scheduler_quiesce")
    )
    if set(request) != canonical_fields:
        return "REJECT"
    if request["policy_id"] != policy["policy_id"]:
        return "REJECT"
    if request["layer_role"] != policy["layer_role"]:
        return "REJECT"
    if request["phase_mode"] not in policy["allowed_phase_modes"]:
        return "REJECT"
    for field in (
        "cleanup_launch_agent_label",
        "cleanup_launch_agent_plist_path",
        "local_artifact_archive_root",
        "database_archive_root",
        "data_volume_free_target_bytes",
        "retention_policy",
        "trade_calendar_authority",
    ):
        if request[field] != policy[field]:
            return "REJECT"
    if any(not request[field] for field in policy["required_true_fields"]):
        return "REJECT"
    if any(request[field] for field in policy["required_false_fields"]):
        return "REJECT"
    if request["kickstart_count"] != 0 or request["database_delete_count"] != 0:
        return "REJECT"

    phase_mode = request["phase_mode"]
    if phase_mode == "cleanup_scheduler_quiesce":
        valid = (
            request["bootout_count"] == 1
            and request["bootstrap_count"] == 0
            and request["cleanup_job_and_pid_absent_after_wait"]
            and request["snapshot_delete_count"] == 0
            and request["local_artifact_delete_count"] == 0
        )
    elif phase_mode == "archive_verified_local_reclaim":
        sha_pattern = policy["archive_evidence_requirements"][
            "manifest_sha256_pattern"
        ]
        valid = (
            request["bootout_count"] == 0
            and request["bootstrap_count"] == 0
            and request["snapshot_delete_count"] == 0
            and request["local_artifact_delete_count"] > 0
            and request["archive_evidence_verified"]
            and request["restore_proofs_complete"]
            and request["allowlist_revalidated"]
            and re.fullmatch(sha_pattern, request["archive_manifest_sha256"] or "")
            and re.fullmatch(sha_pattern, request["batch_summary_sha256"] or "")
            and request["manifest_entry_count"]
            == request["allowlist_entry_count"]
            == request["local_artifact_delete_count"]
            and request["manifest_allocated_bytes"]
            == request["allowlist_allocated_bytes"]
            and request["delete_scope"] == "exact_manifest_entries_only"
            and request["stop_at_free_target"]
        )
    elif phase_mode == "time_machine_snapshot_fallback":
        candidates = request["snapshot_candidates"]
        valid = (
            request["bootout_count"] == 0
            and request["bootstrap_count"] == 0
            and request["local_artifact_delete_count"] == 0
            and request["local_reclaim_completed"]
            and request["data_volume_free_before_bytes"]
            < policy["data_volume_free_target_bytes"]
            and request["snapshot_delete_count"] == len(candidates)
            and bool(candidates)
            and all(
                item["purgeable"]
                and item["name"].startswith("com.apple.TimeMachine.")
                and item["name"].endswith(".local")
                and not item["name"].startswith("com.apple.os.update")
                for item in candidates
            )
        )
    else:
        valid = (
            request["bootout_count"] == 0
            and request["bootstrap_count"] == 1
            and request["kickstart_count"] == 0
            and request["snapshot_delete_count"] == 0
            and request["local_artifact_delete_count"] == 0
            and request["archive_required_configuration_verified"]
            and request["exact_cleanup_job_loaded_without_kickstart"]
        )
    return "ACCEPT" if valid else "REJECT"


class RuntimeHotCleanupArchiveGatedDiskGovernancePolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy()

    def test_contract_has_exact_scope_and_manifest_fields(self) -> None:
        policy = self.policy
        self.assertEqual(policy["policy_id"], POLICY_ID)
        self.assertEqual(policy["layer_role"], "runtime_control")
        self.assertEqual(policy["phase_cardinality"], 1)
        self.assertEqual(
            policy["allowed_phase_modes"],
            [
                "cleanup_scheduler_quiesce",
                "archive_verified_local_reclaim",
                "time_machine_snapshot_fallback",
                "cleanup_scheduler_archive_gated_restore",
            ],
        )
        self.assertEqual(
            policy["retention_policy"],
            "current_trade_date_plus_previous_5_completed_trade_dates_v1",
        )
        self.assertEqual(policy["trade_calendar_authority"], "common_trade_calendar")
        self.assertEqual(policy["data_volume_free_target_bytes"], 250 * 1024**3)
        manifest = policy["local_artifact_archive_manifest_contract"]
        self.assertEqual(manifest["schema"], "LocalArtifactArchiveManifest.v1")
        self.assertEqual(manifest["archive_writer_layer_role"], "N1_ingestion")
        self.assertFalse(manifest["glob_or_directory_inference_allowed"])
        self.assertEqual(manifest["required_restore_proof_result"], "RESTORE_PROOF_PASS")
        for field in (
            "source_device",
            "source_inode",
            "source_allocated_bytes",
            "source_sha256",
            "archive_sha256",
            "reference_classification",
            "restore_proof_id",
        ):
            self.assertIn(field, manifest["required_entry_fields"])

    def test_each_exact_phase_is_accepted(self) -> None:
        for phase_mode in self.policy["allowed_phase_modes"]:
            with self.subTest(phase_mode=phase_mode):
                self.assertEqual(
                    evaluate(
                        self.policy,
                        canonical_request(self.policy, phase_mode),
                    ),
                    "ACCEPT",
                )

    def test_common_fail_closed_mutations_are_rejected(self) -> None:
        base = canonical_request(self.policy, "archive_verified_local_reclaim")
        mutations = {
            "definition_session": {"policy_definition_session": True},
            "no_authorization": {"explicit_user_authorization_current_request": False},
            "direct_delete": {"direct_delete_no_archive_requested": True},
            "glob_delete": {"glob_delete_requested": True},
            "retained_overlap": {"retained_date_overlap": True},
            "active_lineage": {"active_lineage_overlap": True},
            "writer_active": {"active_writer_present": True},
            "database_write": {"database_write_requested": True},
            "business_service": {"n3p_launch_agent_touched": True},
            "automatic_retry": {"automatic_retry_requested": True},
            "wrong_label": {"cleanup_launch_agent_label": "com.example.cleanup"},
            "wrong_retention": {"retention_policy": "latest_hot_trade_dates"},
            "unknown_field": {"unexpected": True},
        }
        for name, changes in mutations.items():
            with self.subTest(name=name):
                request = copy.deepcopy(base)
                request.update(changes)
                self.assertEqual(evaluate(self.policy, request), "REJECT")

    def test_reclaim_requires_exact_archive_evidence(self) -> None:
        base = canonical_request(self.policy, "archive_verified_local_reclaim")
        mutations = {
            "bad_manifest_hash": {"archive_manifest_sha256": "bad"},
            "count_mismatch": {"allowlist_entry_count": 2},
            "allocated_mismatch": {"allowlist_allocated_bytes": 1},
            "restore_missing": {"restore_proofs_complete": False},
            "not_revalidated": {"allowlist_revalidated": False},
            "broad_scope": {"delete_scope": "directory"},
            "snapshot_mixed": {"snapshot_delete_count": 1},
        }
        for name, changes in mutations.items():
            with self.subTest(name=name):
                request = copy.deepcopy(base)
                request.update(changes)
                self.assertEqual(evaluate(self.policy, request), "REJECT")

    def test_snapshot_fallback_is_time_machine_only_and_last_resort(self) -> None:
        base = canonical_request(self.policy, "time_machine_snapshot_fallback")
        mutations = {
            "reclaim_not_complete": {"local_reclaim_completed": False},
            "target_already_met": {
                "data_volume_free_before_bytes": self.policy[
                    "data_volume_free_target_bytes"
                ]
            },
            "not_purgeable": {
                "snapshot_candidates": [
                    {
                        "name": "com.apple.TimeMachine.2026-08-21-010101.local",
                        "purgeable": False,
                    }
                ]
            },
            "os_update": {
                "snapshot_candidates": [
                    {"name": "com.apple.os.update-ABC.local", "purgeable": True}
                ]
            },
        }
        for name, changes in mutations.items():
            with self.subTest(name=name):
                request = copy.deepcopy(base)
                request.update(changes)
                self.assertEqual(evaluate(self.policy, request), "REJECT")

    def test_restore_requires_archive_mode_and_no_kickstart(self) -> None:
        base = canonical_request(
            self.policy, "cleanup_scheduler_archive_gated_restore"
        )
        for changes in (
            {"archive_required_configuration_verified": False},
            {"direct_delete_confirmation_token_present": True},
            {"kickstart_count": 1},
            {"bootstrap_count": 2},
        ):
            request = copy.deepcopy(base)
            request.update(changes)
            self.assertEqual(evaluate(self.policy, request), "REJECT")

    def test_authoritative_docs_bind_policy_and_revoke_direct_mode(self) -> None:
        agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        runtime = (REPO_ROOT / "docs" / "RUNTIME_PIPELINE_CONTROL_V0.md").read_text(
            encoding="utf-8"
        )
        compiler = (REPO_ROOT / "docs" / "EXECUTION_COMPILER.md").read_text(
            encoding="utf-8"
        )
        runtime_gate = (REPO_ROOT / "docs" / "EXECUTION_RUNTIME_GATE.md").read_text(
            encoding="utf-8"
        )
        sandbox = (REPO_ROOT / "docs" / "EXECUTION_SANDBOX.md").read_text(
            encoding="utf-8"
        )
        trace = (REPO_ROOT / "docs" / "EXECUTION_TRACE_SYSTEM.md").read_text(
            encoding="utf-8"
        )
        roadmap = (REPO_ROOT / "docs" / "Roadmap.md").read_text(encoding="utf-8")
        tasks = (REPO_ROOT / "docs" / "Tasks.md").read_text(encoding="utf-8")
        for document in (
            agents,
            runtime,
            compiler,
            runtime_gate,
            sandbox,
            trace,
            roadmap,
            tasks,
        ):
            self.assertIn(POLICY_ID, document)
        self.assertIn("direct-delete-no-archive=REJECT", runtime)
        self.assertIn("定义或修改该 policy 的治理会话不得执行它", agents)
        self.assertIn("policy defined / execution pending", roadmap)
        self.assertIn("policy defined / execution pending", tasks)


if __name__ == "__main__":
    unittest.main()
