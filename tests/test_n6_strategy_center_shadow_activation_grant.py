from __future__ import annotations

import copy
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

from ashare_v3.runtime_control import resumable_activation as grant


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "N6_STRATEGY_CENTER_SHADOW_ACTIVATION_GRANT_V1.json"
SUPERSESSION_PATH = (
    ROOT
    / "docs"
    / "N6_STRATEGY_CENTER_SHADOW_ACTIVATION_GRANT_V1_SUPERSESSION_20260726.json"
)
SUPERSESSION_L2_PATH = (
    ROOT
    / "docs"
    / "N6_STRATEGY_CENTER_SHADOW_ACTIVATION_GRANT_V1_SUPERSESSION_L2_20260726.json"
)
NOW = datetime(2026, 7, 26, 1, 0, tzinfo=timezone.utc)
GOVERNANCE_COMMIT = "1" * 40
GOVERNANCE_TREE = "2" * 40
EVIDENCE = "a" * 64


class N6StrategyCenterShadowActivationGrantTest(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = grant.load_contract(CONTRACT_PATH)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state_path = Path(self.temporary.name) / "activation-state.jsonl"

    def create_and_attest(self) -> None:
        grant.create_state(self.contract, self.state_path, now=NOW)
        grant.attest(
            self.contract,
            self.state_path,
            governance_commit=GOVERNANCE_COMMIT,
            governance_tree=GOVERNANCE_TREE,
            now=NOW,
        )

    def lease(self, stage: str, *, now: datetime = NOW) -> dict[str, object]:
        return grant.issue_lease(
            self.contract,
            self.state_path,
            stage=stage,
            ttl_seconds=60,
            now=now,
        )

    def checkpoint(
        self,
        stage: str,
        status: str,
        *,
        now: datetime = NOW,
        evidence: str | None = EVIDENCE,
    ) -> dict[str, object]:
        lease = self.lease(stage, now=now)
        return grant.record_checkpoint(
            self.contract,
            self.state_path,
            stage=stage,
            status=status,
            lease_id=str(lease["lease_id"]),
            evidence_sha256=evidence,
            now=now,
        )

    def test_machine_document_and_manifest_sha_parse(self) -> None:
        self.assertEqual(
            grant.canonical_sha256(self.contract["parent_manifest"]),
            self.contract["parent_manifest_sha256"],
        )
        self.assertEqual(
            self.contract["policy"]["policy_id"],
            grant.POLICY_ID,
        )
        self.assertEqual(
            self.contract["schema"]["$id"],
            "ashare-v3://runtime-control/n6-strategy-center-shadow-activation-grant-v1",
        )

    def test_manifest_tamper_and_state_hash_drift_fail_closed(self) -> None:
        tampered = copy.deepcopy(self.contract)
        tampered["parent_manifest"]["scope"] = "N1-N6"
        with self.assertRaisesRegex(grant.ContractError, "scope_not_n6_only|manifest_sha_drift"):
            grant.validate_contract(tampered)

        self.create_and_attest()
        lines = self.state_path.read_text(encoding="utf-8").splitlines()
        event = json.loads(lines[-1])
        event["governance_tree"] = "3" * 40
        lines[-1] = json.dumps(event, sort_keys=True)
        self.state_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(grant.ContractError, "state_event_hash_drift"):
            grant.read_state(self.state_path)

    def test_policy_source_and_post_commit_governance_lineage_are_distinct(self) -> None:
        grant.create_state(self.contract, self.state_path, now=NOW)
        source = self.contract["parent_manifest"]["lineage"]["policy_source"]
        with self.assertRaisesRegex(grant.ContractError, "governance_commit_self_reference"):
            grant.attest(
                self.contract,
                self.state_path,
                governance_commit=source["commit"],
                governance_tree=GOVERNANCE_TREE,
                now=NOW,
            )
        attestation = grant.attest(
            self.contract,
            self.state_path,
            governance_commit=GOVERNANCE_COMMIT,
            governance_tree=GOVERNANCE_TREE,
            now=NOW,
        )
        self.assertNotEqual(attestation["governance_commit"], source["commit"])
        self.assertNotEqual(attestation["governance_tree"], source["tree"])

    def test_approval_survives_lease_expiry_and_renewal_cannot_expand(self) -> None:
        self.create_and_attest()
        lease = grant.issue_lease(
            self.contract,
            self.state_path,
            stage="GOVERNANCE",
            ttl_seconds=1,
            now=NOW,
        )
        later = NOW + timedelta(seconds=2)
        status = grant.derive_status(self.contract, self.state_path, now=later)
        self.assertEqual(status["approval_status"], "active")
        self.assertEqual(status["leases"][-1]["lease_status"], "expired")
        with self.assertRaisesRegex(grant.ContractError, "lease_permission_expansion"):
            grant.issue_lease(
                self.contract,
                self.state_path,
                stage="GOVERNANCE",
                ttl_seconds=60,
                renew_lease_id=str(lease["lease_id"]),
                requested_permissions=[
                    *lease["permissions"],
                    "trade mutation",
                ],
                now=later,
            )
        renewed = grant.issue_lease(
            self.contract,
            self.state_path,
            stage="GOVERNANCE",
            ttl_seconds=60,
            renew_lease_id=str(lease["lease_id"]),
            requested_permissions=lease["permissions"],
            now=later,
        )
        self.assertEqual(renewed["permissions"], lease["permissions"])
        self.assertEqual(renewed["checkpoint_sha256"], lease["checkpoint_sha256"])

    def test_checkpoint_idempotency_failure_resume_and_rollback_preserve_state(self) -> None:
        self.create_and_attest()
        self.checkpoint("GOVERNANCE", "running")
        passed = self.checkpoint("GOVERNANCE", "passed")
        duplicate = grant.record_checkpoint(
            self.contract,
            self.state_path,
            stage="GOVERNANCE",
            status="passed",
            lease_id="unused-for-idempotent-pass",
            evidence_sha256=EVIDENCE,
            now=NOW,
        )
        self.assertTrue(duplicate["idempotent"])
        self.assertEqual(duplicate["event_sha256"], passed["event_sha256"])

        self.checkpoint("EVALUATOR_RESUME_FIX", "failed")
        resume = grant.resume(self.contract, self.state_path, now=NOW)
        self.assertEqual(resume["next_stage"], "EVALUATOR_RESUME_FIX")
        self.assertEqual(resume["stage_status"]["GOVERNANCE"], "passed")
        self.assertFalse(resume["child_request"]["approval_reconfirmation_required"])
        self.checkpoint("EVALUATOR_RESUME_FIX", "rolled_back")
        after_rollback = grant.derive_status(self.contract, self.state_path, now=NOW)
        self.assertEqual(after_rollback["stage_status"]["GOVERNANCE"], "passed")
        self.assertEqual(
            after_rollback["stage_status"]["EVALUATOR_RESUME_FIX"],
            "rolled_back",
        )
        self.assertGreater(after_rollback["event_count"], 1)

    def test_four_stage_layer_compilation_and_successful_closeout(self) -> None:
        self.create_and_attest()
        for stage, layer_role in grant.STAGES:
            request = grant.resume(self.contract, self.state_path, now=NOW)
            self.assertEqual(request["child_request"]["stage"], stage)
            self.assertEqual(request["child_request"]["layer_role"], layer_role)
            self.checkpoint(stage, "running")
            self.checkpoint(stage, "passed")
        closeout = grant.closeout(
            self.contract,
            self.state_path,
            evidence_sha256="f" * 64,
            now=NOW,
        )
        self.assertEqual(closeout["result"], "passed")
        status = grant.derive_status(self.contract, self.state_path, now=NOW)
        self.assertEqual(status["approval_status"], "closed_success")
        self.assertIsNone(status["next_stage"])

    def test_n1_n5_trading_deepseek_and_virtual_executor_are_rejected(self) -> None:
        forbidden = set(self.contract["parent_manifest"]["forbidden_boundaries"])
        self.assertTrue(
            {
                "N1-N5 modification",
                "DeepSeek invocation",
                "Virtual Executor operation",
                "proposal mutation",
                "order mutation",
                "trade mutation",
                "position mutation",
                "lot mutation",
                "cash mutation",
                "autonomous trading",
                "real trading",
            }
            <= forbidden
        )
        polluted = copy.deepcopy(self.contract)
        polluted["parent_manifest"]["child_requests"][0]["allowed_side_effects"].append(
            "trade mutation"
        )
        polluted["parent_manifest_sha256"] = grant.canonical_sha256(
            polluted["parent_manifest"]
        )
        with self.assertRaisesRegex(grant.ContractError, "forbidden_allowed_side_effect"):
            grant.validate_contract(polluted)
        self.assertEqual(
            self.contract["parent_manifest"]["existing_migrations"],
            [
                {"migration": "081", "rerun_allowed": False},
                {"migration": "082", "rerun_allowed": False},
                {"migration": "083", "rerun_allowed": False},
            ],
        )

    def test_missing_authority_fails_closed(self) -> None:
        missing = copy.deepcopy(self.contract)
        del missing["parent_manifest"]["lineage"]["implementation"]
        missing["parent_manifest_sha256"] = grant.canonical_sha256(
            missing["parent_manifest"]
        )
        with self.assertRaisesRegex(grant.ContractError, "implementation_lineage_missing"):
            grant.validate_contract(missing)

    def test_cli_create_status_and_reject_output(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = grant.main(
                [
                    "--contract",
                    str(CONTRACT_PATH),
                    "--state",
                    str(self.state_path),
                    "create",
                ]
            )
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(stdout.getvalue())["ok"])

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = grant.main(
                [
                    "--contract",
                    str(CONTRACT_PATH),
                    "--state",
                    str(self.state_path),
                    "lease",
                    "--stage",
                    "GOVERNANCE",
                ]
            )
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout.getvalue())["decision"], "REJECT")

    def test_supersession_classifies_operational_and_semantic_drift(self) -> None:
        supersession = grant.load_contract(SUPERSESSION_PATH)
        chain = supersession["supersession"]["manifest_sha256_chain"]
        self.assertEqual(chain[0], grant.ORIGINAL_PARENT_MANIFEST_SHA256)
        self.assertEqual(chain[1], supersession["parent_manifest_sha256"])
        resolution = supersession["supersession"]["drift_resolution"]
        self.assertEqual(resolution["classification"], "operational_drift")
        self.assertTrue(resolution["web_source_operational_drift"])
        self.assertFalse(resolution["approval_terminated"])
        for field in (
            "candidate_semantic_drift",
            "strategy_rule_semantic_drift",
            "bundle_semantic_drift",
            "implementation_semantic_drift",
            "target_artifact_semantic_drift",
        ):
            polluted = copy.deepcopy(supersession)
            polluted["supersession"]["drift_resolution"][field] = True
            with self.assertRaisesRegex(grant.ContractError, field):
                grant.validate_contract(polluted)

    def test_supersession_exact_rebind_authority_cannot_expand(self) -> None:
        supersession = grant.load_contract(SUPERSESSION_PATH)
        rebind = supersession["supersession"]["bounded_rebind_policy"]
        self.assertEqual(tuple(rebind["exact_labels"]), grant.EXACT_REBIND_LABELS)
        self.assertEqual(rebind["max_bootout_per_label"], 1)
        self.assertEqual(rebind["max_plist_replace_per_label"], 1)
        self.assertEqual(rebind["max_bootstrap_per_label"], 1)
        self.assertEqual(rebind["max_source_restore_attempts"], 1)
        for field in (
            "kickstart_allowed",
            "runner_allowed",
            "canary_allowed",
            "empty_state_restore_allowed",
            "virtual_executor_operation_allowed",
            "n1_n5_write_allowed",
            "trading_write_allowed",
        ):
            self.assertFalse(rebind[field])
        polluted = copy.deepcopy(supersession)
        polluted["supersession"]["bounded_rebind_policy"]["exact_labels"].append(
            "com.ashare-v3.n6.virtual-executor-v1"
        )
        with self.assertRaisesRegex(grant.ContractError, "rebind_labels_invalid"):
            grant.validate_contract(polluted)

    def test_supersession_two_ancestry_paths_and_boundary_proof_are_frozen(self) -> None:
        supersession = grant.load_contract(SUPERSESSION_PATH)
        proof = supersession["supersession"]["compatibility_proof"]
        self.assertTrue(proof["web_original_is_ancestor_of_current"])
        self.assertTrue(proof["web_current_is_ancestor_of_target"])
        self.assertTrue(proof["evaluator_live_is_ancestor_of_source"])
        self.assertTrue(proof["evaluator_source_is_ancestor_of_target"])
        self.assertTrue(proof["critical_web_runner_unchanged"])
        self.assertTrue(proof["critical_web_api_unchanged"])
        self.assertTrue(proof["virtual_executor_blob_unchanged"])
        self.assertTrue(proof["n1_n5_boundary_unchanged"])
        self.assertTrue(proof["trading_boundary_unchanged"])
        polluted = copy.deepcopy(supersession)
        polluted["supersession"]["compatibility_proof"][
            "virtual_executor_blob_unchanged"
        ] = False
        with self.assertRaisesRegex(grant.ContractError, "virtual_executor_blob_unchanged"):
            grant.validate_contract(polluted)

    def test_legacy_checkpoint_is_evidence_then_real_chain_plans_rebind(self) -> None:
        supersession = grant.load_contract(SUPERSESSION_PATH)
        state_path = Path(self.temporary.name) / "supersession-state.jsonl"
        grant.create_state(supersession, state_path, now=NOW)
        grant.attest(
            supersession,
            state_path,
            governance_commit=GOVERNANCE_COMMIT,
            governance_tree=GOVERNANCE_TREE,
            now=NOW,
        )
        imported = grant.import_evidence(
            supersession,
            state_path,
            evidence_kind="stage2_plain_checkpoint_jsonl",
            evidence_path="candidate/checkpoint.jsonl",
            evidence_sha256="0" * 64,
            now=NOW,
        )
        self.assertEqual(imported["event_type"], "evidence_imported")

        for stage, evidence in (
            ("GOVERNANCE", "1" * 64),
            ("EVALUATOR_RESUME_FIX", "2" * 64),
        ):
            running_lease = grant.issue_lease(
                supersession,
                state_path,
                stage=stage,
                ttl_seconds=60,
                now=NOW,
            )
            grant.record_checkpoint(
                supersession,
                state_path,
                stage=stage,
                status="running",
                lease_id=str(running_lease["lease_id"]),
                evidence_sha256=evidence,
                now=NOW,
            )
            passed_lease = grant.issue_lease(
                supersession,
                state_path,
                stage=stage,
                ttl_seconds=60,
                now=NOW,
            )
            grant.record_checkpoint(
                supersession,
                state_path,
                stage=stage,
                status="passed",
                lease_id=str(passed_lease["lease_id"]),
                evidence_sha256=evidence,
                now=NOW,
            )

        planned = grant.record_planned_checkpoint(
            supersession,
            state_path,
            stage="BOUNDED_REBIND",
            evidence_sha256="3" * 64,
            now=NOW,
        )
        self.assertEqual(planned["status"], "planned")
        self.assertTrue(planned["planned_only"])
        lease = grant.issue_lease(
            supersession,
            state_path,
            stage="BOUNDED_REBIND",
            ttl_seconds=60,
            now=NOW,
        )
        status = grant.derive_status(supersession, state_path, now=NOW)
        self.assertEqual(status["stage_status"]["GOVERNANCE"], "passed")
        self.assertEqual(status["stage_status"]["EVALUATOR_RESUME_FIX"], "passed")
        self.assertEqual(status["stage_status"]["BOUNDED_REBIND"], "planned")

    def test_second_level_supersession_binds_control_plane_and_bundle_upgrade(self) -> None:
        supersession = grant.load_supersession_l2(SUPERSESSION_L2_PATH)
        self.assertEqual(
            supersession["manifest_sha256_chain"],
            [
                grant.ORIGINAL_PARENT_MANIFEST_SHA256,
                grant.FIRST_SUPERSESSION_MANIFEST_SHA256,
                supersession["supersession_manifest_sha256"],
            ],
        )
        payload = supersession["supersession_payload"]
        self.assertEqual(
            payload["control_plane_authority"]["commit"],
            grant.CONTROL_PLANE_COMMIT,
        )
        self.assertEqual(
            payload["current_runtime_anchors"]["web"]["plist_sha256"],
            "ee2b1e451b5f0e85a74e5510233e5b4272af4daf9c525d1b736af360f4237bc7",
        )
        self.assertEqual(
            payload["bundle_supersession"]["target_f464_bundle_file_sha256"],
            "6efda6309d8e6ebb2d8e91d4a961a0855a76a239c8dd36c45534a50778a190d8",
        )
        self.assertFalse(
            payload["bundle_supersession"]["historical_anchor_is_execution_authority"]
        )

    def test_failed_rebind_resumes_web_only_and_evaluator_stays_blocked(self) -> None:
        supersession = grant.load_supersession_l2(SUPERSESSION_L2_PATH)
        failure_evidence = supersession["supersession_payload"]["failure_resume"][
            "failure_evidence_sha256"
        ]
        self.create_and_attest()
        for stage in ("GOVERNANCE", "EVALUATOR_RESUME_FIX"):
            self.checkpoint(stage, "running")
            self.checkpoint(stage, "passed")
        self.checkpoint("BOUNDED_REBIND", "failed", evidence=failure_evidence)

        events = grant.read_state(self.state_path)
        test_checkpoint = grant.checkpoint_sha256(
            self.contract["parent_manifest_sha256"],
            events,
        )
        supersession = copy.deepcopy(supersession)
        supersession["supersession_payload"]["failure_resume"][
            "failed_checkpoint_sha256"
        ] = test_checkpoint
        manifest_sha = grant.canonical_sha256(supersession["supersession_payload"])
        supersession["supersession_manifest_sha256"] = manifest_sha
        supersession["manifest_sha256_chain"][-1] = manifest_sha

        grant.resume_bounded_rebind_internal(
            self.contract,
            self.state_path,
            supersession,
            previous_failure_evidence_sha256=failure_evidence,
            now=NOW,
        )
        grant.record_internal_planned_checkpoint(
            self.contract,
            self.state_path,
            supersession,
            target="BOUNDED_REBIND_WEB_TARGET",
            evidence_sha256=manifest_sha,
            now=NOW,
        )
        status = grant.derive_status(self.contract, self.state_path, now=NOW)
        self.assertEqual(status["stage_status"]["BOUNDED_REBIND"], "running")
        self.assertEqual(
            status["bounded_rebind_internal_status"],
            {
                "BOUNDED_REBIND_WEB_TARGET": "planned",
                "BOUNDED_REBIND_EVALUATOR_TARGET": "blocked_pending_canary",
            },
        )
        lease = grant.issue_internal_lease(
            self.contract,
            self.state_path,
            supersession,
            target="BOUNDED_REBIND_WEB_TARGET",
            ttl_seconds=60,
            now=NOW,
        )
        self.assertIn("keep exact Evaluator absent", lease["permissions"])
        self.assertNotIn("bootstrap", " ".join(lease["permissions"]).lower())
        with self.assertRaisesRegex(
            grant.ContractError,
            "evaluator_target_web_not_passed",
        ):
            grant.record_internal_planned_checkpoint(
                self.contract,
                self.state_path,
                supersession,
                target="BOUNDED_REBIND_EVALUATOR_TARGET",
                evidence_sha256=EVIDENCE,
                now=NOW,
            )
        with self.assertRaisesRegex(
            grant.ContractError,
            "internal_target_not_planned_or_running",
        ):
            grant.issue_internal_lease(
                self.contract,
                self.state_path,
                supersession,
                target="BOUNDED_REBIND_EVALUATOR_TARGET",
                ttl_seconds=60,
                now=NOW,
            )
        grant.record_internal_checkpoint(
            self.contract,
            self.state_path,
            supersession,
            target="BOUNDED_REBIND_WEB_TARGET",
            status="running",
            lease_id=str(lease["lease_id"]),
            evidence_sha256=EVIDENCE,
            now=NOW,
        )
        completion_lease = grant.issue_internal_lease(
            self.contract,
            self.state_path,
            supersession,
            target="BOUNDED_REBIND_WEB_TARGET",
            ttl_seconds=60,
            now=NOW,
        )
        grant.record_internal_checkpoint(
            self.contract,
            self.state_path,
            supersession,
            target="BOUNDED_REBIND_WEB_TARGET",
            status="passed",
            lease_id=str(completion_lease["lease_id"]),
            evidence_sha256="b" * 64,
            now=NOW,
        )
        with self.assertRaisesRegex(
            grant.ContractError,
            "evaluator_target_canary_pass_missing",
        ):
            grant.record_internal_planned_checkpoint(
                self.contract,
                self.state_path,
                supersession,
                target="BOUNDED_REBIND_EVALUATOR_TARGET",
                evidence_sha256=EVIDENCE,
                now=NOW,
            )
        self.assertEqual(status["next_stage"], "BOUNDED_REBIND")
        self.assertEqual(lease["checkpoint_sha256"], status["checkpoint_sha256"])


if __name__ == "__main__":
    unittest.main()
