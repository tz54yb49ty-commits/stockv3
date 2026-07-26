"""Fail-closed control plane for the resumable N6 shadow activation grant.

The module only reads a frozen contract and appends local JSONL governance
events.  It never connects to a database or invokes runtime commands.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


POLICY_ID = "n6_strategy_center_shadow_activation_grant_v1"
APPROVAL_ID = "N6_AI_SIMULATED_INVESTOR_RESUMABLE_ACTIVATION"
ORIGINAL_PARENT_MANIFEST_SHA256 = (
    "507eea13e9d6e5bb7088c83632107c68e444453fa1badd3869bfda89678be625"
)
FIRST_SUPERSESSION_MANIFEST_SHA256 = (
    "84f867676c1523c72adb28732f3c7551ade9cf119f629928005b1f009eddf0b8"
)
CONTROL_PLANE_COMMIT = "72b1d50b6658d89e3aff6ed15619b875814f8e5e"
CONTROL_PLANE_TREE = "f7e835e53146e30b8ab4ed8096133b1e14b14a12"
TARGET_RELEASE_COMMIT = "f4641e9c4cd4dff1a817f779d28007fe7cdffe62"
TARGET_RELEASE_TREE = "c654cbc03c0341c9b3490a02a432b136984c43ce"
EXACT_REBIND_LABELS = (
    "com.ashare-v3.n6.user-web",
    "com.ashare-v3.n6.strategy-center-evaluator-v1",
)
STAGES = (
    ("GOVERNANCE", "runtime_control"),
    ("EVALUATOR_RESUME_FIX", "N6_user"),
    ("BOUNDED_REBIND", "runtime_control"),
    ("NATURAL_ACCEPTANCE", "N6_user"),
)
STAGE_NAMES = tuple(name for name, _ in STAGES)
STAGE_LAYER = dict(STAGES)
INTERNAL_TARGETS = (
    "BOUNDED_REBIND_WEB_TARGET",
    "BOUNDED_REBIND_EVALUATOR_TARGET",
)
INTERNAL_TARGET_LAYER = {target: "runtime_control" for target in INTERNAL_TARGETS}
STATUSES = {"planned", "running", "passed", "failed", "rolled_back"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
UTC = timezone.utc


class ContractError(ValueError):
    """The immutable contract or append-only state failed validation."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def load_contract(path: Path | str) -> dict[str, Any]:
    contract_path = Path(path)
    try:
        document = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"contract_unreadable:{exc}") from exc
    validate_contract(document)
    return document


def load_supersession_l2(path: Path | str) -> dict[str, Any]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"supersession_l2_unreadable:{exc}") from exc
    validate_supersession_l2(document)
    return document


def validate_supersession_l2(document: Mapping[str, Any]) -> None:
    _require(document.get("document_schema_version") == 1, "supersession_l2_schema_invalid")
    _require(
        document.get("document_type")
        == "immutable_second_level_supersession_attestation",
        "supersession_l2_type_invalid",
    )
    payload = document.get("supersession_payload")
    _require(isinstance(payload, Mapping), "supersession_l2_payload_missing")
    manifest_sha = document.get("supersession_manifest_sha256")
    _require(SHA64.fullmatch(str(manifest_sha or "")) is not None, "supersession_l2_sha_invalid")
    _require(canonical_sha256(payload) == manifest_sha, "supersession_l2_sha_drift")
    _require(
        document.get("manifest_sha256_chain")
        == [
            ORIGINAL_PARENT_MANIFEST_SHA256,
            FIRST_SUPERSESSION_MANIFEST_SHA256,
            manifest_sha,
        ],
        "supersession_l2_chain_invalid",
    )
    _require(payload.get("supersession_level") == 2, "supersession_l2_level_invalid")
    _require(payload.get("policy_id") == POLICY_ID, "supersession_l2_policy_invalid")
    _require(payload.get("parent_approval_id") == APPROVAL_ID, "supersession_l2_approval_invalid")
    control = payload.get("control_plane_authority")
    _require(isinstance(control, Mapping), "control_plane_authority_missing")
    _require(control.get("commit") == CONTROL_PLANE_COMMIT, "control_plane_commit_drift")
    _require(control.get("tree") == CONTROL_PLANE_TREE, "control_plane_tree_drift")
    anchors = payload.get("current_runtime_anchors")
    _require(isinstance(anchors, Mapping), "supersession_l2_anchors_missing")
    web = anchors.get("web")
    evaluator = anchors.get("evaluator")
    virtual = anchors.get("virtual_executor")
    _require(isinstance(web, Mapping), "supersession_l2_web_missing")
    _require(web.get("release_commit") == "d85df6328bde223e912dabc3bd65e16df984aa45", "source_web_commit_drift")
    _require(
        web.get("plist_sha256")
        == "ee2b1e451b5f0e85a74e5510233e5b4272af4daf9c525d1b736af360f4237bc7",
        "source_web_plist_drift",
    )
    _require(web.get("strategy_write") == "0", "source_web_write_not_zero")
    _require(isinstance(evaluator, Mapping), "supersession_l2_evaluator_missing")
    _require(evaluator.get("job_state") == "absent", "evaluator_not_absent")
    _require(evaluator.get("runner_process_count") == 0, "evaluator_runner_present")
    _require(
        evaluator.get("must_remain_absent_until_current_date_bounded_canary_pass") is True,
        "evaluator_pre_canary_absence_missing",
    )
    _require(isinstance(virtual, Mapping), "supersession_l2_virtual_missing")
    _require(virtual.get("operations") == 0, "virtual_executor_operation_allowed")
    target = payload.get("target")
    _require(isinstance(target, Mapping), "supersession_l2_target_missing")
    _require(target.get("commit") == TARGET_RELEASE_COMMIT, "supersession_l2_target_commit_drift")
    _require(target.get("tree") == TARGET_RELEASE_TREE, "supersession_l2_target_tree_drift")
    bundle = payload.get("bundle_supersession")
    _require(isinstance(bundle, Mapping), "bundle_supersession_missing")
    _require(
        bundle.get("target_f464_bundle_file_sha256")
        == "6efda6309d8e6ebb2d8e91d4a961a0855a76a239c8dd36c45534a50778a190d8",
        "target_bundle_file_drift",
    )
    _require(
        bundle.get("target_f464_bundle_internal_sha256")
        == "119296de69f27b840cf743f2d6aad04fe56bd7f1ca80991dbdf5be3f547ca1e0",
        "target_bundle_internal_drift",
    )
    _require(bundle.get("historical_anchor_is_execution_authority") is False, "historical_bundle_authority")
    _require(payload.get("visible_stage_dag") == list(STAGE_NAMES), "visible_stage_dag_changed")
    internal = payload.get("bounded_rebind_internal_checkpoints")
    _require(
        [row.get("name") for row in internal or []] == list(INTERNAL_TARGETS),
        "internal_checkpoint_dag_invalid",
    )
    web_authority = payload.get("web_target_authority")
    evaluator_authority = payload.get("evaluator_target_authority")
    _require(isinstance(web_authority, Mapping), "web_target_authority_missing")
    _require(isinstance(evaluator_authority, Mapping), "evaluator_target_authority_missing")
    _require(web_authority.get("strategy_write_before") == "0", "web_target_write_before_invalid")
    _require(web_authority.get("strategy_write_after") == "0", "web_target_write_after_invalid")
    _require(web_authority.get("evaluator_operations") == 0, "web_target_evaluator_operation")
    _require(web_authority.get("canary_operations") == 0, "web_target_canary_operation")
    _require(evaluator_authority.get("pre_canary_planning_allowed") is False, "evaluator_pre_canary_plan_allowed")
    _require(evaluator_authority.get("pre_canary_lease_allowed") is False, "evaluator_pre_canary_lease_allowed")
    _require(evaluator_authority.get("requires_web_target_passed") is True, "evaluator_web_dependency_missing")
    _require(
        evaluator_authority.get("requires_current_date_bounded_canary_pass") is True,
        "evaluator_canary_dependency_missing",
    )
    _require(
        evaluator_authority.get("target_must_equal_web_target") == TARGET_RELEASE_COMMIT,
        "evaluator_target_release_drift",
    )
    forbidden = payload.get("forbidden")
    _require(isinstance(forbidden, Mapping), "supersession_l2_forbidden_missing")
    _require(all(value is True for value in forbidden.values()), "supersession_l2_boundary_expanded")


def validate_contract(document: Mapping[str, Any]) -> None:
    schema_version = document.get("document_schema_version")
    _require(schema_version in {1, 2}, "schema_version_invalid")
    _require(isinstance(document.get("schema"), Mapping), "schema_missing")
    policy = document.get("policy")
    manifest = document.get("parent_manifest")
    template = document.get("child_request_template")
    _require(isinstance(policy, Mapping), "policy_missing")
    _require(isinstance(manifest, Mapping), "parent_manifest_missing")
    _require(isinstance(template, Mapping), "child_request_template_missing")

    _require(policy.get("policy_id") == POLICY_ID, "policy_id_invalid")
    _require(policy.get("default_decision") == "REJECT", "default_not_fail_closed")
    _require(policy.get("approval_survives_lease_expiry") is True, "approval_lease_coupled")
    _require(policy.get("lease_renewal_expands_authority") is False, "lease_can_expand")
    _require(
        policy.get("approval_termination_conditions")
        == ["successful_closeout", "explicit_user_revocation", "input_lineage_or_rule_drift"],
        "approval_termination_conditions_invalid",
    )
    _require(manifest.get("approval_id") == APPROVAL_ID, "approval_id_invalid")
    _require(manifest.get("approval_status") == "ONE_TIME_APPROVAL_ALREADY_ACCEPTED", "approval_not_accepted")
    _require(manifest.get("scope") == "N6_only", "scope_not_n6_only")

    dag = manifest.get("stage_dag")
    _require(isinstance(dag, list) and len(dag) == len(STAGES), "stage_dag_invalid")
    compiled = tuple(
        (row.get("stage"), row.get("layer_role"))
        for row in dag
        if isinstance(row, Mapping)
    )
    _require(compiled == STAGES, "stage_layer_compilation_invalid")
    for index, row in enumerate(dag):
        _require(row.get("order") == index + 1, "stage_order_invalid")
        expected_depends = [] if index == 0 else [STAGES[index - 1][0]]
        _require(row.get("depends_on") == expected_depends, "stage_dependency_invalid")

    forbidden = set(manifest.get("forbidden_boundaries") or [])
    required_forbidden = {
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
    _require(required_forbidden <= forbidden, "forbidden_boundary_missing")
    migrations = manifest.get("existing_migrations")
    _require(
        migrations == [
            {"migration": "081", "rerun_allowed": False},
            {"migration": "082", "rerun_allowed": False},
            {"migration": "083", "rerun_allowed": False},
        ],
        "existing_migration_contract_invalid",
    )

    lineage = manifest.get("lineage")
    _require(isinstance(lineage, Mapping), "lineage_missing")
    source = lineage.get("policy_source")
    binding = lineage.get("governance_binding")
    _require(isinstance(source, Mapping), "policy_source_lineage_missing")
    _require(isinstance(binding, Mapping), "governance_binding_missing")
    _require(SHA40.fullmatch(str(source.get("commit") or "")) is not None, "policy_source_commit_invalid")
    _require(SHA40.fullmatch(str(source.get("tree") or "")) is not None, "policy_source_tree_invalid")
    _require(binding.get("storage") == "external_post_commit_attestation", "governance_binding_not_external")
    _require(binding.get("commit_field") == "governance_commit", "governance_commit_field_invalid")
    _require(binding.get("tree_field") == "governance_tree", "governance_tree_field_invalid")
    _require(binding.get("must_differ_from_policy_source") is True, "self_reference_guard_missing")
    candidate = lineage.get("candidate")
    bundle = lineage.get("bundle")
    implementation = lineage.get("implementation")
    _require(isinstance(candidate, Mapping), "candidate_lineage_missing")
    _require(isinstance(bundle, Mapping), "bundle_lineage_missing")
    _require(isinstance(implementation, Mapping), "implementation_lineage_missing")
    for field in ("integration_commit", "integration_tree"):
        _require(SHA40.fullmatch(str(candidate.get(field) or "")) is not None, f"candidate_{field}_invalid")
    _require(SHA64.fullmatch(str(candidate.get("sha256") or "")) is not None, "candidate_sha_invalid")
    _require(SHA40.fullmatch(str(bundle.get("integration_commit") or "")) is not None, "bundle_commit_invalid")
    for field in ("file_sha256", "declared_bundle_sha256"):
        _require(SHA64.fullmatch(str(bundle.get(field) or "")) is not None, f"bundle_{field}_invalid")
    for field in ("commit", "tree"):
        _require(SHA40.fullmatch(str(implementation.get(field) or "")) is not None, f"implementation_{field}_invalid")
    _require(
        SHA64.fullmatch(str(implementation.get("policy_sha256") or "")) is not None,
        "implementation_policy_sha_invalid",
    )

    anchors = manifest.get("current_runtime_anchors")
    _require(isinstance(anchors, Mapping), "runtime_anchors_missing")
    for anchor_name in ("web", "evaluator"):
        anchor = anchors.get(anchor_name)
        _require(isinstance(anchor, Mapping), f"{anchor_name}_anchor_missing")
        _require(SHA64.fullmatch(str(anchor.get("plist_sha256") or "")) is not None, f"{anchor_name}_plist_sha_invalid")
        _require(SHA40.fullmatch(str(anchor.get("release_commit") or "")) is not None, f"{anchor_name}_release_commit_invalid")
        _require(SHA40.fullmatch(str(anchor.get("release_tree") or "")) is not None, f"{anchor_name}_release_tree_invalid")
        _require(SHA64.fullmatch(str(anchor.get("runner_sha256") or "")) is not None, f"{anchor_name}_runner_sha_invalid")
    virtual_anchor = anchors.get("virtual_executor_frozen_not_operable")
    _require(isinstance(virtual_anchor, Mapping), "virtual_executor_anchor_missing")
    _require(virtual_anchor.get("operation_allowed") is False, "virtual_executor_operation_allowed")
    _require(
        SHA64.fullmatch(str(virtual_anchor.get("plist_sha256") or "")) is not None,
        "virtual_executor_plist_sha_invalid",
    )

    children = manifest.get("child_requests")
    _require(isinstance(children, list) and len(children) == len(STAGES), "child_requests_invalid")
    child_compiled = tuple(
        (row.get("stage"), row.get("layer_role"))
        for row in children
        if isinstance(row, Mapping)
    )
    _require(child_compiled == STAGES, "child_request_layer_invalid")
    for row in children:
        _require(isinstance(row.get("frozen_inputs"), Mapping), "child_inputs_missing")
        _require(isinstance(row.get("allowed_side_effects"), list), "child_side_effects_missing")
        _require(isinstance(row.get("stop_conditions"), list), "child_stop_missing")
        _require(isinstance(row.get("rollback_conditions"), list), "child_rollback_missing")
        _require(isinstance(row.get("required_outputs"), list), "child_outputs_missing")
        allowed_text = " ".join(str(value).lower() for value in row["allowed_side_effects"])
        for token in (
            "n1 ",
            "n2 ",
            "n3 ",
            "n4 ",
            "n5 ",
            "deepseek",
            "virtual executor",
            "proposal",
            "order ",
            "trade ",
            "position ",
            "lot ",
            "cash ",
            "autonomous trading",
            "real trading",
        ):
            _require(token not in allowed_text, f"forbidden_allowed_side_effect:{token.strip()}")

    manifest_sha = document.get("parent_manifest_sha256")
    _require(SHA64.fullmatch(str(manifest_sha or "")) is not None, "manifest_sha_invalid")
    _require(canonical_sha256(manifest) == manifest_sha, "manifest_sha_drift")
    if schema_version == 2:
        _validate_supersession(document, manifest)


def _validate_supersession(
    document: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> None:
    supersession = document.get("supersession")
    _require(isinstance(supersession, Mapping), "supersession_missing")
    _require(
        supersession.get("previous_parent_manifest_sha256")
        == ORIGINAL_PARENT_MANIFEST_SHA256,
        "supersession_previous_manifest_invalid",
    )
    _require(
        supersession.get("superseding_parent_manifest_sha256")
        == document.get("parent_manifest_sha256"),
        "supersession_current_manifest_invalid",
    )
    chain = supersession.get("manifest_sha256_chain")
    _require(
        chain
        == [
            ORIGINAL_PARENT_MANIFEST_SHA256,
            document.get("parent_manifest_sha256"),
        ],
        "supersession_chain_invalid",
    )

    drift = supersession.get("drift_resolution")
    _require(isinstance(drift, Mapping), "drift_resolution_missing")
    _require(drift.get("classification") == "operational_drift", "drift_not_operational")
    _require(drift.get("approval_terminated") is False, "approval_terminated")
    _require(drift.get("user_reapproval_required") is False, "reapproval_required")
    _require(drift.get("candidate_semantic_drift") is False, "candidate_semantic_drift")
    _require(drift.get("strategy_rule_semantic_drift") is False, "strategy_rule_semantic_drift")
    _require(drift.get("bundle_semantic_drift") is False, "bundle_semantic_drift")
    _require(drift.get("implementation_semantic_drift") is False, "implementation_semantic_drift")
    _require(drift.get("target_artifact_semantic_drift") is False, "target_artifact_semantic_drift")
    _require(drift.get("web_source_operational_drift") is True, "web_operational_drift_missing")

    proof = supersession.get("compatibility_proof")
    _require(isinstance(proof, Mapping), "compatibility_proof_missing")
    for field in (
        "web_original_is_ancestor_of_current",
        "web_current_is_ancestor_of_target",
        "evaluator_live_is_ancestor_of_source",
        "evaluator_source_is_ancestor_of_target",
        "critical_web_runner_unchanged",
        "critical_web_api_unchanged",
        "virtual_executor_blob_unchanged",
        "n1_n5_boundary_unchanged",
        "trading_boundary_unchanged",
    ):
        _require(proof.get(field) is True, f"compatibility_proof_failed:{field}")

    lineage = manifest.get("lineage")
    _require(isinstance(lineage, Mapping), "lineage_missing")
    policy_source = lineage.get("policy_source")
    target = lineage.get("target_artifact")
    implementation = lineage.get("implementation")
    _require(isinstance(policy_source, Mapping), "policy_source_lineage_missing")
    _require(isinstance(target, Mapping), "target_artifact_lineage_missing")
    _require(isinstance(implementation, Mapping), "implementation_lineage_missing")
    _require(policy_source.get("commit") == TARGET_RELEASE_COMMIT, "policy_source_commit_drift")
    _require(policy_source.get("tree") == TARGET_RELEASE_TREE, "policy_source_tree_drift")
    _require(target.get("release_commit") == TARGET_RELEASE_COMMIT, "target_release_commit_drift")
    _require(target.get("release_tree") == TARGET_RELEASE_TREE, "target_release_tree_drift")
    _require(
        target.get("archive_sha256")
        == "a62e98c77e4b3391099ed5eb5939fe2b44a52ac918be3ec6e0a1c6266621d368",
        "target_archive_drift",
    )
    _require(
        target.get("manifest_sha256")
        == "0d29c5b4fa2c550e69806d847a68556a3a6b9b568fe06bfde8027cd4639ff78f",
        "target_manifest_drift",
    )
    _require(
        target.get("filesystem_sha256")
        == "4e46cb1fcd73a452f6a3e534d0bb9dc7ddc011fea4937510991cd9b8e51a79fa",
        "target_filesystem_drift",
    )
    _require(
        implementation.get("commit")
        == "5c2c38d184385a317afe69b6397f7d98393ff24f",
        "implementation_commit_drift",
    )
    _require(
        implementation.get("tree")
        == "0a02ac53513946ca530d3420b2bd06c60630388e",
        "implementation_tree_drift",
    )

    rebind = supersession.get("bounded_rebind_policy")
    _require(isinstance(rebind, Mapping), "bounded_rebind_policy_missing")
    _require(tuple(rebind.get("exact_labels") or ()) == EXACT_REBIND_LABELS, "rebind_labels_invalid")
    _require(rebind.get("max_bootout_per_label") == 1, "bootout_limit_invalid")
    _require(rebind.get("max_plist_replace_per_label") == 1, "plist_replace_limit_invalid")
    _require(rebind.get("max_bootstrap_per_label") == 1, "bootstrap_limit_invalid")
    _require(rebind.get("max_source_restore_attempts") == 1, "source_restore_limit_invalid")
    for field in (
        "kickstart_allowed",
        "runner_allowed",
        "canary_allowed",
        "empty_state_restore_allowed",
        "virtual_executor_operation_allowed",
        "n1_n5_write_allowed",
        "trading_write_allowed",
    ):
        _require(rebind.get(field) is False, f"rebind_authority_expanded:{field}")
    _require(
        rebind.get("requires_supersession_manifest") is True,
        "supersession_manifest_not_required",
    )
    _require(rebind.get("requires_hash_chain_checkpoint") is True, "checkpoint_not_required")
    _require(rebind.get("requires_active_lease") is True, "lease_not_required")


def _event_hash(event: Mapping[str, Any]) -> str:
    unsigned = {key: value for key, value in event.items() if key != "event_sha256"}
    return canonical_sha256(unsigned)


def _append_event(state_path: Path, event: dict[str, Any]) -> dict[str, Any]:
    events = read_state(state_path) if state_path.exists() and state_path.stat().st_size else []
    event = copy.deepcopy(event)
    event["sequence"] = len(events) + 1
    event["previous_event_sha256"] = events[-1]["event_sha256"] if events else None
    event["event_sha256"] = _event_hash(event)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return event


def read_state(state_path: Path | str) -> list[dict[str, Any]]:
    path = Path(state_path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ContractError(f"state_unreadable:{exc}") from exc
    _require(bool(lines), "state_empty")
    events: list[dict[str, Any]] = []
    previous: str | None = None
    for index, line in enumerate(lines, start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ContractError(f"state_json_invalid:{index}") from exc
        _require(event.get("sequence") == index, "state_sequence_drift")
        _require(event.get("previous_event_sha256") == previous, "state_chain_drift")
        _require(event.get("event_sha256") == _event_hash(event), "state_event_hash_drift")
        previous = event["event_sha256"]
        events.append(event)
    return events


def _contract_context(contract: Mapping[str, Any]) -> tuple[str, str, str]:
    manifest_sha = str(contract["parent_manifest_sha256"])
    source = contract["parent_manifest"]["lineage"]["policy_source"]
    return manifest_sha, str(source["commit"]), str(source["tree"])


def create_state(
    contract: Mapping[str, Any],
    state_path: Path | str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    validate_contract(contract)
    path = Path(state_path)
    _require(not path.exists() or path.stat().st_size == 0, "state_already_exists")
    manifest_sha, source_commit, source_tree = _contract_context(contract)
    return _append_event(
        path,
        {
            "event_type": "created",
            "created_at": _iso(now),
            "policy_id": POLICY_ID,
            "approval_id": APPROVAL_ID,
            "approval_status": "active",
            "parent_manifest_sha256": manifest_sha,
            "policy_source_commit": source_commit,
            "policy_source_tree": source_tree,
            "initial_stage_status": "planned",
        },
    )


def _load_bound_state(
    contract: Mapping[str, Any],
    state_path: Path | str,
) -> list[dict[str, Any]]:
    validate_contract(contract)
    events = read_state(state_path)
    first = events[0]
    manifest_sha, source_commit, source_tree = _contract_context(contract)
    _require(first.get("event_type") == "created", "state_create_event_missing")
    _require(first.get("parent_manifest_sha256") == manifest_sha, "state_manifest_drift")
    _require(first.get("policy_source_commit") == source_commit, "state_source_commit_drift")
    _require(first.get("policy_source_tree") == source_tree, "state_source_tree_drift")
    return events


def attest(
    contract: Mapping[str, Any],
    state_path: Path | str,
    *,
    governance_commit: str,
    governance_tree: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    events = _load_bound_state(contract, state_path)
    _require(SHA40.fullmatch(governance_commit) is not None, "governance_commit_invalid")
    _require(SHA40.fullmatch(governance_tree) is not None, "governance_tree_invalid")
    source = contract["parent_manifest"]["lineage"]["policy_source"]
    _require(governance_commit != source["commit"], "governance_commit_self_reference")
    _require(governance_tree != source["tree"], "governance_tree_self_reference")
    for event in events:
        if event.get("event_type") == "attested":
            _require(event.get("governance_commit") == governance_commit, "governance_commit_rebind")
            _require(event.get("governance_tree") == governance_tree, "governance_tree_rebind")
            return {**event, "idempotent": True}
    return _append_event(
        Path(state_path),
        {
            "event_type": "attested",
            "created_at": _iso(now),
            "parent_manifest_sha256": contract["parent_manifest_sha256"],
            "governance_commit": governance_commit,
            "governance_tree": governance_tree,
        },
    )


def import_evidence(
    contract: Mapping[str, Any],
    state_path: Path | str,
    *,
    evidence_kind: str,
    evidence_path: str,
    evidence_sha256: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    events = _load_bound_state(contract, state_path)
    _require(_approval_status(events) == "active", "approval_not_active")
    _require(_attestation(events) is not None, "governance_attestation_missing")
    _require(bool(evidence_kind.strip()), "evidence_kind_missing")
    _require(bool(evidence_path.strip()), "evidence_path_missing")
    _require(SHA64.fullmatch(evidence_sha256) is not None, "evidence_sha_invalid")
    for event in events:
        if (
            event.get("event_type") == "evidence_imported"
            and event.get("evidence_kind") == evidence_kind
            and event.get("evidence_path") == evidence_path
        ):
            _require(event.get("evidence_sha256") == evidence_sha256, "evidence_rebind")
            return {**event, "idempotent": True}
    return _append_event(
        Path(state_path),
        {
            "event_type": "evidence_imported",
            "created_at": _iso(now),
            "evidence_kind": evidence_kind,
            "evidence_path": evidence_path,
            "evidence_sha256": evidence_sha256,
        },
    )


def _statuses(events: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    statuses = {stage: "planned" for stage in STAGE_NAMES}
    for event in events:
        if event.get("event_type") == "checkpoint":
            statuses[str(event["stage"])] = str(event["status"])
        elif event.get("event_type") == "bounded_rebind_internal_resume":
            statuses["BOUNDED_REBIND"] = "running"
    return statuses


def _internal_statuses(events: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    statuses = {
        "BOUNDED_REBIND_WEB_TARGET": "unavailable",
        "BOUNDED_REBIND_EVALUATOR_TARGET": "unavailable",
    }
    for event in events:
        if event.get("event_type") == "bounded_rebind_internal_resume":
            statuses["BOUNDED_REBIND_WEB_TARGET"] = "not_planned"
            statuses["BOUNDED_REBIND_EVALUATOR_TARGET"] = "blocked_pending_canary"
        elif event.get("event_type") == "internal_checkpoint":
            statuses[str(event["target"])] = str(event["status"])
    return statuses


def _last_checkpoint_hash(events: Sequence[Mapping[str, Any]]) -> str | None:
    hashes = [
        str(event["event_sha256"])
        for event in events
        if event.get("event_type") == "checkpoint"
    ]
    return hashes[-1] if hashes else None


def checkpoint_sha256(
    manifest_sha256: str,
    events: Sequence[Mapping[str, Any]],
) -> str:
    value: dict[str, Any] = {
        "parent_manifest_sha256": manifest_sha256,
        "stage_status": _statuses(events),
        "last_checkpoint_event_sha256": _last_checkpoint_hash(events),
    }
    internal_events = [
        event
        for event in events
        if event.get("event_type")
        in {"bounded_rebind_internal_resume", "internal_checkpoint"}
    ]
    if internal_events:
        value["bounded_rebind_internal_status"] = _internal_statuses(events)
        value["last_internal_event_sha256"] = internal_events[-1]["event_sha256"]
        value["supersession_l2_sha256"] = next(
            event["supersession_l2_sha256"]
            for event in reversed(events)
            if event.get("event_type") == "bounded_rebind_internal_resume"
        )
    return canonical_sha256(value)


def _approval_status(events: Sequence[Mapping[str, Any]]) -> str:
    for event in reversed(events):
        if event.get("event_type") == "closeout":
            return "closed_success"
        if event.get("event_type") == "approval_revoked":
            return "revoked"
        if event.get("event_type") == "input_drift":
            return "drifted"
    return "active"


def _attestation(events: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    return next((event for event in reversed(events) if event.get("event_type") == "attested"), None)


def _next_stage(statuses: Mapping[str, str]) -> str | None:
    for stage in STAGE_NAMES:
        if statuses[stage] != "passed":
            return stage
    return None


def derive_status(
    contract: Mapping[str, Any],
    state_path: Path | str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    events = _load_bound_state(contract, state_path)
    statuses = _statuses(events)
    current_time = _utc(now)
    leases: list[dict[str, Any]] = []
    for event in events:
        if event.get("event_type") in {"lease_issued", "internal_lease_issued"}:
            row = dict(event)
            row["lease_status"] = (
                "active" if _parse_iso(str(event["expires_at"])) > current_time else "expired"
            )
            leases.append(row)
    return {
        "policy_id": POLICY_ID,
        "approval_id": APPROVAL_ID,
        "approval_status": _approval_status(events),
        "parent_manifest_sha256": contract["parent_manifest_sha256"],
        "attested": _attestation(events) is not None,
        "stage_status": statuses,
        "bounded_rebind_internal_status": _internal_statuses(events),
        "next_stage": _next_stage(statuses),
        "checkpoint_sha256": checkpoint_sha256(
            str(contract["parent_manifest_sha256"]),
            events,
        ),
        "leases": leases,
        "event_count": len(events),
        "last_event_sha256": events[-1]["event_sha256"],
    }


def issue_lease(
    contract: Mapping[str, Any],
    state_path: Path | str,
    *,
    stage: str,
    ttl_seconds: int,
    renew_lease_id: str | None = None,
    requested_permissions: Sequence[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    events = _load_bound_state(contract, state_path)
    _require(_approval_status(events) == "active", "approval_not_active")
    _require(_attestation(events) is not None, "governance_attestation_missing")
    _require(stage in STAGE_LAYER, "stage_invalid")
    _require(type(ttl_seconds) is int and 1 <= ttl_seconds <= 3600, "lease_ttl_invalid")
    statuses = _statuses(events)
    _require(_next_stage(statuses) == stage, "stage_not_resumable")
    child = next(
        row
        for row in contract["parent_manifest"]["child_requests"]
        if row["stage"] == stage
    )
    frozen_permissions = list(child["allowed_side_effects"])
    permissions = list(requested_permissions) if requested_permissions is not None else frozen_permissions
    _require(permissions == frozen_permissions, "lease_permission_expansion")
    if renew_lease_id is not None:
        previous = next(
            (
                event
                for event in reversed(events)
                if event.get("event_type") == "lease_issued"
                and event.get("lease_id") == renew_lease_id
            ),
            None,
        )
        _require(previous is not None, "renewed_lease_missing")
        _require(previous.get("stage") == stage, "renewed_lease_stage_drift")
        _require(previous.get("permissions") == permissions, "renewed_lease_permission_drift")
    current_time = _utc(now)
    return _append_event(
        Path(state_path),
        {
            "event_type": "lease_issued",
            "created_at": current_time.isoformat(),
            "lease_id": uuid.uuid4().hex,
            "renewed_from_lease_id": renew_lease_id,
            "stage": stage,
            "layer_role": STAGE_LAYER[stage],
            "parent_manifest_sha256": contract["parent_manifest_sha256"],
            "checkpoint_sha256": checkpoint_sha256(
                str(contract["parent_manifest_sha256"]),
                events,
            ),
            "permissions": permissions,
            "expires_at": (current_time + timedelta(seconds=ttl_seconds)).isoformat(),
        },
    )


def record_checkpoint(
    contract: Mapping[str, Any],
    state_path: Path | str,
    *,
    stage: str,
    status: str,
    lease_id: str,
    evidence_sha256: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    events = _load_bound_state(contract, state_path)
    _require(_approval_status(events) == "active", "approval_not_active")
    _require(stage in STAGE_LAYER, "stage_invalid")
    _require(status in STATUSES - {"planned"}, "checkpoint_status_invalid")
    if evidence_sha256 is not None:
        _require(SHA64.fullmatch(evidence_sha256) is not None, "evidence_sha_invalid")
    statuses = _statuses(events)
    current = statuses[stage]
    if current == "passed" and status == "passed":
        previous = next(
            event
            for event in reversed(events)
            if event.get("event_type") == "checkpoint" and event.get("stage") == stage
        )
        _require(previous.get("evidence_sha256") == evidence_sha256, "passed_evidence_drift")
        return {**previous, "idempotent": True}

    transitions = {
        "planned": {"running", "failed"},
        "running": {"passed", "failed", "rolled_back"},
        "failed": {"running", "rolled_back"},
        "rolled_back": {"running"},
        "passed": {"rolled_back"},
    }
    _require(status in transitions[current], "checkpoint_transition_invalid")
    stage_index = STAGE_NAMES.index(stage)
    _require(
        all(statuses[prior] == "passed" for prior in STAGE_NAMES[:stage_index]),
        "prior_stage_not_passed",
    )
    expected_checkpoint = checkpoint_sha256(
        str(contract["parent_manifest_sha256"]),
        events,
    )
    lease = next(
        (
            event
            for event in reversed(events)
            if event.get("event_type") == "lease_issued"
            and event.get("lease_id") == lease_id
        ),
        None,
    )
    _require(lease is not None, "lease_missing")
    _require(lease.get("stage") == stage, "lease_stage_drift")
    _require(lease.get("parent_manifest_sha256") == contract["parent_manifest_sha256"], "lease_manifest_drift")
    _require(lease.get("checkpoint_sha256") == expected_checkpoint, "lease_checkpoint_drift")
    _require(_parse_iso(str(lease["expires_at"])) > _utc(now), "lease_expired")
    return _append_event(
        Path(state_path),
        {
            "event_type": "checkpoint",
            "created_at": _iso(now),
            "stage": stage,
            "layer_role": STAGE_LAYER[stage],
            "status": status,
            "lease_id": lease_id,
            "evidence_sha256": evidence_sha256,
        },
    )


def record_planned_checkpoint(
    contract: Mapping[str, Any],
    state_path: Path | str,
    *,
    stage: str,
    evidence_sha256: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    events = _load_bound_state(contract, state_path)
    _require(_approval_status(events) == "active", "approval_not_active")
    _require(_attestation(events) is not None, "governance_attestation_missing")
    _require(stage in STAGE_LAYER, "stage_invalid")
    _require(SHA64.fullmatch(evidence_sha256) is not None, "evidence_sha_invalid")
    statuses = _statuses(events)
    _require(statuses[stage] == "planned", "stage_not_plannable")
    stage_index = STAGE_NAMES.index(stage)
    _require(
        all(statuses[prior] == "passed" for prior in STAGE_NAMES[:stage_index]),
        "prior_stage_not_passed",
    )
    previous = next(
        (
            event
            for event in reversed(events)
            if event.get("event_type") == "checkpoint"
            and event.get("stage") == stage
            and event.get("status") == "planned"
        ),
        None,
    )
    if previous is not None:
        _require(previous.get("evidence_sha256") == evidence_sha256, "planned_evidence_drift")
        return {**previous, "idempotent": True}
    return _append_event(
        Path(state_path),
        {
            "event_type": "checkpoint",
            "created_at": _iso(now),
            "stage": stage,
            "layer_role": STAGE_LAYER[stage],
            "status": "planned",
            "planned_only": True,
            "evidence_sha256": evidence_sha256,
        },
    )


def resume_bounded_rebind_internal(
    contract: Mapping[str, Any],
    state_path: Path | str,
    supersession_l2: Mapping[str, Any],
    *,
    previous_failure_evidence_sha256: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    validate_supersession_l2(supersession_l2)
    events = _load_bound_state(contract, state_path)
    _require(_approval_status(events) == "active", "approval_not_active")
    existing = next(
        (
            event
            for event in reversed(events)
            if event.get("event_type") == "bounded_rebind_internal_resume"
        ),
        None,
    )
    manifest_sha = str(supersession_l2["supersession_manifest_sha256"])
    if existing is not None:
        _require(existing.get("supersession_l2_sha256") == manifest_sha, "internal_resume_manifest_drift")
        _require(
            existing.get("previous_failure_evidence_sha256")
            == previous_failure_evidence_sha256,
            "internal_resume_failure_evidence_drift",
        )
        return {**existing, "idempotent": True}
    statuses = _statuses(events)
    _require(statuses["BOUNDED_REBIND"] == "failed", "bounded_rebind_not_failed")
    _require(SHA64.fullmatch(previous_failure_evidence_sha256) is not None, "failure_evidence_sha_invalid")
    payload = supersession_l2["supersession_payload"]
    failure = payload["failure_resume"]
    _require(
        failure["failure_evidence_sha256"] == previous_failure_evidence_sha256,
        "failure_evidence_not_manifest_bound",
    )
    failed_event = next(
        event
        for event in reversed(events)
        if event.get("event_type") == "checkpoint"
        and event.get("stage") == "BOUNDED_REBIND"
        and event.get("status") == "failed"
    )
    _require(
        failed_event.get("evidence_sha256") == previous_failure_evidence_sha256,
        "failed_checkpoint_evidence_mismatch",
    )
    _require(
        checkpoint_sha256(str(contract["parent_manifest_sha256"]), events)
        == failure["failed_checkpoint_sha256"],
        "failed_checkpoint_sha_drift",
    )
    return _append_event(
        Path(state_path),
        {
            "event_type": "bounded_rebind_internal_resume",
            "created_at": _iso(now),
            "stage": "BOUNDED_REBIND",
            "status": "running",
            "supersession_l2_sha256": manifest_sha,
            "previous_failure_event_sha256": failed_event["event_sha256"],
            "previous_failure_evidence_sha256": previous_failure_evidence_sha256,
            "web_target_initial_status": "not_planned",
            "evaluator_target_initial_status": "blocked_pending_canary",
        },
    )


def _canary_pass_imported(events: Sequence[Mapping[str, Any]]) -> bool:
    return any(
        event.get("event_type") == "evidence_imported"
        and event.get("evidence_kind") == "current_date_bounded_canary_pass"
        for event in events
    )


def record_internal_planned_checkpoint(
    contract: Mapping[str, Any],
    state_path: Path | str,
    supersession_l2: Mapping[str, Any],
    *,
    target: str,
    evidence_sha256: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    validate_supersession_l2(supersession_l2)
    events = _load_bound_state(contract, state_path)
    _require(target in INTERNAL_TARGETS, "internal_target_invalid")
    _require(SHA64.fullmatch(evidence_sha256) is not None, "evidence_sha_invalid")
    resume_event = next(
        (
            event
            for event in reversed(events)
            if event.get("event_type") == "bounded_rebind_internal_resume"
        ),
        None,
    )
    _require(resume_event is not None, "bounded_rebind_internal_resume_missing")
    _require(
        resume_event.get("supersession_l2_sha256")
        == supersession_l2["supersession_manifest_sha256"],
        "internal_plan_manifest_drift",
    )
    statuses = _internal_statuses(events)
    previous = next(
        (
            event
            for event in reversed(events)
            if event.get("event_type") == "internal_checkpoint"
            and event.get("target") == target
            and event.get("status") == "planned"
        ),
        None,
    )
    if previous is not None:
        if previous.get("evidence_sha256") == evidence_sha256:
            return {**previous, "idempotent": True}
    if target == "BOUNDED_REBIND_WEB_TARGET":
        _require(
            statuses[target] in {"not_planned", "planned"},
            "web_target_not_plannable",
        )
    else:
        _require(
            statuses["BOUNDED_REBIND_WEB_TARGET"] == "passed",
            "evaluator_target_web_not_passed",
        )
        _require(_canary_pass_imported(events), "evaluator_target_canary_pass_missing")
        _require(
            statuses[target] in {"blocked_pending_canary", "planned"},
            "evaluator_target_not_blocked",
        )
    event = {
        "event_type": "internal_checkpoint",
        "created_at": _iso(now),
        "stage": "BOUNDED_REBIND",
        "target": target,
        "layer_role": INTERNAL_TARGET_LAYER[target],
        "status": "planned",
        "planned_only": True,
        "supersession_l2_sha256": supersession_l2["supersession_manifest_sha256"],
        "evidence_sha256": evidence_sha256,
    }
    if previous is not None:
        event["supersedes_internal_plan_event_sha256"] = previous["event_sha256"]
    return _append_event(
        Path(state_path),
        event,
    )


def issue_internal_lease(
    contract: Mapping[str, Any],
    state_path: Path | str,
    supersession_l2: Mapping[str, Any],
    *,
    target: str,
    ttl_seconds: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    validate_supersession_l2(supersession_l2)
    events = _load_bound_state(contract, state_path)
    _require(target in INTERNAL_TARGETS, "internal_target_invalid")
    _require(type(ttl_seconds) is int and 1 <= ttl_seconds <= 3600, "lease_ttl_invalid")
    statuses = _internal_statuses(events)
    _require(
        statuses[target] in {"planned", "running"},
        "internal_target_not_planned_or_running",
    )
    if target == "BOUNDED_REBIND_EVALUATOR_TARGET":
        _require(
            statuses["BOUNDED_REBIND_WEB_TARGET"] == "passed",
            "evaluator_target_web_not_passed",
        )
        _require(_canary_pass_imported(events), "evaluator_target_canary_pass_missing")
    permissions = (
        [
            "install exact immutable f464 release",
            "rebind exact Web d85 to f464 with strategy write zero",
            "keep exact Evaluator absent",
        ]
        if target == "BOUNDED_REBIND_WEB_TARGET"
        else ["bootstrap exact Evaluator to the same f464 after current-date canary pass"]
    )
    current_time = _utc(now)
    return _append_event(
        Path(state_path),
        {
            "event_type": "internal_lease_issued",
            "created_at": current_time.isoformat(),
            "lease_id": uuid.uuid4().hex,
            "stage": "BOUNDED_REBIND",
            "target": target,
            "layer_role": INTERNAL_TARGET_LAYER[target],
            "supersession_l2_sha256": supersession_l2["supersession_manifest_sha256"],
            "parent_manifest_sha256": contract["parent_manifest_sha256"],
            "checkpoint_sha256": checkpoint_sha256(
                str(contract["parent_manifest_sha256"]),
                events,
            ),
            "permissions": permissions,
            "expires_at": (current_time + timedelta(seconds=ttl_seconds)).isoformat(),
        },
    )


def record_internal_checkpoint(
    contract: Mapping[str, Any],
    state_path: Path | str,
    supersession_l2: Mapping[str, Any],
    *,
    target: str,
    status: str,
    lease_id: str,
    evidence_sha256: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    validate_supersession_l2(supersession_l2)
    events = _load_bound_state(contract, state_path)
    _require(target in INTERNAL_TARGETS, "internal_target_invalid")
    _require(status in {"running", "passed", "failed"}, "internal_status_invalid")
    _require(SHA64.fullmatch(evidence_sha256) is not None, "evidence_sha_invalid")
    statuses = _internal_statuses(events)
    transitions = {
        "planned": {"running", "failed"},
        "running": {"passed", "failed"},
    }
    _require(status in transitions.get(statuses[target], set()), "internal_transition_invalid")
    if target == "BOUNDED_REBIND_EVALUATOR_TARGET":
        _require(
            statuses["BOUNDED_REBIND_WEB_TARGET"] == "passed",
            "evaluator_target_web_not_passed",
        )
        _require(_canary_pass_imported(events), "evaluator_target_canary_pass_missing")
    lease = next(
        (
            event
            for event in reversed(events)
            if event.get("event_type") == "internal_lease_issued"
            and event.get("lease_id") == lease_id
        ),
        None,
    )
    _require(lease is not None, "internal_lease_missing")
    _require(lease.get("target") == target, "internal_lease_target_drift")
    _require(
        lease.get("supersession_l2_sha256")
        == supersession_l2["supersession_manifest_sha256"],
        "internal_lease_manifest_drift",
    )
    _require(
        lease.get("checkpoint_sha256")
        == checkpoint_sha256(str(contract["parent_manifest_sha256"]), events),
        "internal_lease_checkpoint_drift",
    )
    _require(_parse_iso(str(lease["expires_at"])) > _utc(now), "internal_lease_expired")
    return _append_event(
        Path(state_path),
        {
            "event_type": "internal_checkpoint",
            "created_at": _iso(now),
            "stage": "BOUNDED_REBIND",
            "target": target,
            "layer_role": INTERNAL_TARGET_LAYER[target],
            "status": status,
            "lease_id": lease_id,
            "supersession_l2_sha256": supersession_l2["supersession_manifest_sha256"],
            "evidence_sha256": evidence_sha256,
        },
    )


def resume(
    contract: Mapping[str, Any],
    state_path: Path | str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    status = derive_status(contract, state_path, now=now)
    _require(status["approval_status"] == "active", "approval_not_active")
    stage = status["next_stage"]
    if stage is None:
        return {"resume_required": False, **status}
    child = next(
        copy.deepcopy(row)
        for row in contract["parent_manifest"]["child_requests"]
        if row["stage"] == stage
    )
    child.update(
        {
            "policy_id": POLICY_ID,
            "approval_id": APPROVAL_ID,
            "parent_manifest_sha256": contract["parent_manifest_sha256"],
            "checkpoint_sha256": status["checkpoint_sha256"],
            "approval_reconfirmation_required": False,
        }
    )
    return {"resume_required": True, "child_request": child, **status}


def closeout(
    contract: Mapping[str, Any],
    state_path: Path | str,
    *,
    evidence_sha256: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    events = _load_bound_state(contract, state_path)
    _require(_approval_status(events) == "active", "approval_not_active")
    _require(all(value == "passed" for value in _statuses(events).values()), "stages_not_all_passed")
    _require(SHA64.fullmatch(evidence_sha256) is not None, "evidence_sha_invalid")
    return _append_event(
        Path(state_path),
        {
            "event_type": "closeout",
            "created_at": _iso(now),
            "result": "passed",
            "evidence_sha256": evidence_sha256,
        },
    )


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


def _iso(value: datetime | None) -> str:
    return _utc(value).isoformat()


def _parse_iso(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ContractError("timestamp_invalid") from exc
    _require(parsed.tzinfo is not None, "timestamp_timezone_missing")
    return parsed.astimezone(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--supersession-l2", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("create")
    attest_parser = sub.add_parser("attest")
    attest_parser.add_argument("--governance-commit", required=True)
    attest_parser.add_argument("--governance-tree", required=True)
    lease_parser = sub.add_parser("lease")
    lease_parser.add_argument("--stage", required=True, choices=STAGE_NAMES)
    lease_parser.add_argument("--ttl-seconds", type=int, default=300)
    lease_parser.add_argument("--renew-lease-id")
    evidence_parser = sub.add_parser("evidence")
    evidence_parser.add_argument("--evidence-kind", required=True)
    evidence_parser.add_argument("--evidence-path", required=True)
    evidence_parser.add_argument("--evidence-sha256", required=True)
    plan_parser = sub.add_parser("plan")
    plan_parser.add_argument("--stage", required=True, choices=STAGE_NAMES)
    plan_parser.add_argument("--evidence-sha256", required=True)
    checkpoint_parser = sub.add_parser("checkpoint")
    checkpoint_parser.add_argument("--stage", required=True, choices=STAGE_NAMES)
    checkpoint_parser.add_argument("--status", required=True, choices=sorted(STATUSES - {"planned"}))
    checkpoint_parser.add_argument("--lease-id", required=True)
    checkpoint_parser.add_argument("--evidence-sha256")
    resume_rebind_parser = sub.add_parser("resume-rebind")
    resume_rebind_parser.add_argument("--previous-failure-evidence-sha256", required=True)
    plan_internal_parser = sub.add_parser("plan-internal")
    plan_internal_parser.add_argument("--target", required=True, choices=INTERNAL_TARGETS)
    plan_internal_parser.add_argument("--evidence-sha256", required=True)
    lease_internal_parser = sub.add_parser("lease-internal")
    lease_internal_parser.add_argument("--target", required=True, choices=INTERNAL_TARGETS)
    lease_internal_parser.add_argument("--ttl-seconds", type=int, default=300)
    checkpoint_internal_parser = sub.add_parser("checkpoint-internal")
    checkpoint_internal_parser.add_argument("--target", required=True, choices=INTERNAL_TARGETS)
    checkpoint_internal_parser.add_argument(
        "--status",
        required=True,
        choices=("running", "passed", "failed"),
    )
    checkpoint_internal_parser.add_argument("--lease-id", required=True)
    checkpoint_internal_parser.add_argument("--evidence-sha256", required=True)
    sub.add_parser("resume")
    sub.add_parser("status")
    closeout_parser = sub.add_parser("closeout")
    closeout_parser.add_argument("--evidence-sha256", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        contract = load_contract(args.contract)
        if args.command == "create":
            result = create_state(contract, args.state)
        elif args.command == "attest":
            result = attest(
                contract,
                args.state,
                governance_commit=args.governance_commit,
                governance_tree=args.governance_tree,
            )
        elif args.command == "lease":
            result = issue_lease(
                contract,
                args.state,
                stage=args.stage,
                ttl_seconds=args.ttl_seconds,
                renew_lease_id=args.renew_lease_id,
            )
        elif args.command == "evidence":
            result = import_evidence(
                contract,
                args.state,
                evidence_kind=args.evidence_kind,
                evidence_path=args.evidence_path,
                evidence_sha256=args.evidence_sha256,
            )
        elif args.command == "plan":
            result = record_planned_checkpoint(
                contract,
                args.state,
                stage=args.stage,
                evidence_sha256=args.evidence_sha256,
            )
        elif args.command == "checkpoint":
            result = record_checkpoint(
                contract,
                args.state,
                stage=args.stage,
                status=args.status,
                lease_id=args.lease_id,
                evidence_sha256=args.evidence_sha256,
            )
        elif args.command in {
            "resume-rebind",
            "plan-internal",
            "lease-internal",
            "checkpoint-internal",
        }:
            _require(args.supersession_l2 is not None, "supersession_l2_path_missing")
            supersession_l2 = load_supersession_l2(args.supersession_l2)
            if args.command == "resume-rebind":
                result = resume_bounded_rebind_internal(
                    contract,
                    args.state,
                    supersession_l2,
                    previous_failure_evidence_sha256=(
                        args.previous_failure_evidence_sha256
                    ),
                )
            elif args.command == "plan-internal":
                result = record_internal_planned_checkpoint(
                    contract,
                    args.state,
                    supersession_l2,
                    target=args.target,
                    evidence_sha256=args.evidence_sha256,
                )
            elif args.command == "lease-internal":
                result = issue_internal_lease(
                    contract,
                    args.state,
                    supersession_l2,
                    target=args.target,
                    ttl_seconds=args.ttl_seconds,
                )
            else:
                result = record_internal_checkpoint(
                    contract,
                    args.state,
                    supersession_l2,
                    target=args.target,
                    status=args.status,
                    lease_id=args.lease_id,
                    evidence_sha256=args.evidence_sha256,
                )
        elif args.command == "resume":
            result = resume(contract, args.state)
        elif args.command == "status":
            result = derive_status(contract, args.state)
        else:
            result = closeout(
                contract,
                args.state,
                evidence_sha256=args.evidence_sha256,
            )
    except ContractError as exc:
        print(json.dumps({"ok": False, "decision": "REJECT", "error": str(exc)}))
        return 2
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
