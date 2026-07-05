"""Real read-only environment probe authorization request dry-run.

This module prepares the last authorization request before a future real
read-only environment probe. It does not read environment variables, inspect
the filesystem, read local TDX files, connect PostgreSQL, execute SQL, call
external APIs, create directories, write files, start workers, or authorize
real execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ashare_v3.ingestion.backfill_config import DEFAULT_INITIAL_BACKFILL_CONFIG
from ashare_v3.ingestion.common import QualityGateResult
from ashare_v3.ingestion.daily_incremental_config import DEFAULT_DAILY_INCREMENTAL_CONFIG
from ashare_v3.ingestion.environment_probe_application import REQUIRED_PROBE_OPERATOR_APPROVALS
from ashare_v3.ingestion.environment_probe_authorization_summary import (
    AUTHORIZATION_BLOCKERS,
    SENSITIVE_REAL_PROBE_ACTIONS,
    EnvironmentProbeAuthorizationSummary,
    SensitiveProbeAction,
    build_environment_probe_authorization_summary,
)
from ashare_v3.ingestion.ingestion_acceptance import quality_gate_to_dict
from ashare_v3.ingestion.parquet_archive import DEFAULT_DATA_ROOT
from ashare_v3.ingestion.real_execution_config import DEFAULT_REAL_EXECUTION_CONFIG
from ashare_v3.ingestion.schema_readiness import DEFAULT_SCHEMA_PATH


REQUIRED_READONLY_AUTHORIZATION_PHRASE = "允许执行真实只读环境探测"
READONLY_AUTHORIZATION_OUTPUT_FIELDS = (
    "action_id",
    "result_status",
    "error_summary",
    "redacted_evidence",
)
READONLY_AUTHORIZATION_FORBIDDEN_OUTPUTS = (
    "tushare_token_value",
    "postgres_dsn_value",
    "tdx_file_content",
    "external_api_payload",
    "market_data_payload",
    "postgres_result_rows",
    "directory_listing",
)


@dataclass(frozen=True)
class ReadOnlyProbeAuthorizationRequest:
    action_id: str
    category: str
    description: str
    required_approval_item: str
    requested_scope: str
    allowed_outputs: tuple[str, ...]
    forbidden_outputs: tuple[str, ...]
    redaction_policy: str
    approval_status: str = "pending_user_confirmation"
    will_execute: bool = False

    @property
    def approved(self) -> bool:
        return self.approval_status == "confirmed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "category": self.category,
            "description": self.description,
            "required_approval_item": self.required_approval_item,
            "requested_scope": self.requested_scope,
            "allowed_outputs": list(self.allowed_outputs),
            "forbidden_outputs": list(self.forbidden_outputs),
            "redaction_policy": self.redaction_policy,
            "approval_status": self.approval_status,
            "approved": self.approved,
            "will_execute": self.will_execute,
        }


@dataclass(frozen=True)
class EnvironmentProbeReadOnlyAuthorizationRequest:
    request_id: str
    authorization_summary_id: str
    data_root: str
    audit_root: str
    required_authorization_phrase: str
    authorization_phrase_present: bool
    sensitive_action_requests: tuple[ReadOnlyProbeAuthorizationRequest, ...]
    pending_approval_item_ids: tuple[str, ...]
    inherited_blocking_finding_ids: tuple[str, ...]
    inherited_blocking_result_item_ids: tuple[str, ...]
    inherited_authorization_blockers: tuple[str, ...]
    input_summary_passed: bool
    input_summary_ready_for_real_probe: bool
    quality_gates: tuple[QualityGateResult, ...]
    will_read_environment: bool = False
    will_check_filesystem: bool = False
    will_call_external_sources: bool = False
    will_read_tdx_files: bool = False
    will_connect_database: bool = False
    will_execute_sql: bool = False
    will_create_directories: bool = False
    will_write_data_files: bool = False
    will_start_worker: bool = False
    will_authorize_real_probe: bool = False
    will_authorize_real_execution: bool = False

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.quality_gates)

    @property
    def ready_for_real_probe(self) -> bool:
        return False

    @property
    def action_ids(self) -> tuple[str, ...]:
        return tuple(request.action_id for request in self.sensitive_action_requests)

    @property
    def pending_action_ids(self) -> tuple[str, ...]:
        return tuple(
            request.action_id
            for request in self.sensitive_action_requests
            if request.approval_status != "confirmed" or not request.will_execute
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "authorization_summary_id": self.authorization_summary_id,
            "data_root": self.data_root,
            "audit_root": self.audit_root,
            "required_authorization_phrase": self.required_authorization_phrase,
            "authorization_phrase_present": self.authorization_phrase_present,
            "passed": self.passed,
            "ready_for_real_probe": self.ready_for_real_probe,
            "sensitive_action_count": len(self.sensitive_action_requests),
            "pending_action_ids": list(self.pending_action_ids),
            "pending_approval_item_ids": list(self.pending_approval_item_ids),
            "inherited_blocking_finding_ids": list(self.inherited_blocking_finding_ids),
            "inherited_blocking_result_item_ids": list(self.inherited_blocking_result_item_ids),
            "inherited_authorization_blockers": list(self.inherited_authorization_blockers),
            "input_summary_passed": self.input_summary_passed,
            "input_summary_ready_for_real_probe": self.input_summary_ready_for_real_probe,
            "sensitive_action_requests": [request.to_dict() for request in self.sensitive_action_requests],
            "quality_gates": [quality_gate_to_dict(gate) for gate in self.quality_gates],
            "side_effects": {
                "will_read_environment": self.will_read_environment,
                "will_check_filesystem": self.will_check_filesystem,
                "will_call_external_sources": self.will_call_external_sources,
                "will_read_tdx_files": self.will_read_tdx_files,
                "will_connect_database": self.will_connect_database,
                "will_execute_sql": self.will_execute_sql,
                "will_create_directories": self.will_create_directories,
                "will_write_data_files": self.will_write_data_files,
                "will_start_worker": self.will_start_worker,
                "will_authorize_real_probe": self.will_authorize_real_probe,
                "will_authorize_real_execution": self.will_authorize_real_execution,
            },
        }


def build_environment_probe_readonly_authorization_request(
    *,
    initial_config_path: str | Path = DEFAULT_INITIAL_BACKFILL_CONFIG,
    daily_config_path: str | Path = DEFAULT_DAILY_INCREMENTAL_CONFIG,
    real_config_path: str | Path = DEFAULT_REAL_EXECUTION_CONFIG,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
    data_root: str | None = None,
) -> EnvironmentProbeReadOnlyAuthorizationRequest:
    summary = build_environment_probe_authorization_summary(
        initial_config_path=initial_config_path,
        daily_config_path=daily_config_path,
        real_config_path=real_config_path,
        schema_path=schema_path,
        data_root=data_root or DEFAULT_DATA_ROOT,
    )
    return build_environment_probe_readonly_authorization_request_from_summary(summary)


def build_environment_probe_readonly_authorization_request_from_summary(
    summary: EnvironmentProbeAuthorizationSummary,
) -> EnvironmentProbeReadOnlyAuthorizationRequest:
    action_requests = tuple(build_readonly_action_request(action) for action in summary.sensitive_actions)
    request = EnvironmentProbeReadOnlyAuthorizationRequest(
        request_id="environment_probe_readonly_authorization_n3_13",
        authorization_summary_id=summary.summary_id,
        data_root=summary.data_root,
        audit_root=summary.audit_root,
        required_authorization_phrase=REQUIRED_READONLY_AUTHORIZATION_PHRASE,
        authorization_phrase_present=False,
        sensitive_action_requests=action_requests,
        pending_approval_item_ids=summary.pending_approval_item_ids,
        inherited_blocking_finding_ids=summary.inherited_blocking_finding_ids,
        inherited_blocking_result_item_ids=summary.inherited_blocking_result_item_ids,
        inherited_authorization_blockers=summary.authorization_blockers,
        input_summary_passed=summary.passed,
        input_summary_ready_for_real_probe=summary.ready_for_real_probe,
        quality_gates=(),
    )
    return EnvironmentProbeReadOnlyAuthorizationRequest(
        request_id=request.request_id,
        authorization_summary_id=request.authorization_summary_id,
        data_root=request.data_root,
        audit_root=request.audit_root,
        required_authorization_phrase=request.required_authorization_phrase,
        authorization_phrase_present=request.authorization_phrase_present,
        sensitive_action_requests=request.sensitive_action_requests,
        pending_approval_item_ids=request.pending_approval_item_ids,
        inherited_blocking_finding_ids=request.inherited_blocking_finding_ids,
        inherited_blocking_result_item_ids=request.inherited_blocking_result_item_ids,
        inherited_authorization_blockers=request.inherited_authorization_blockers,
        input_summary_passed=request.input_summary_passed,
        input_summary_ready_for_real_probe=request.input_summary_ready_for_real_probe,
        quality_gates=tuple(build_readonly_authorization_quality_gates(request)),
    )


def build_readonly_action_request(action: SensitiveProbeAction) -> ReadOnlyProbeAuthorizationRequest:
    return ReadOnlyProbeAuthorizationRequest(
        action_id=action.action_id,
        category=action.category,
        description=action.description,
        required_approval_item=action.required_approval_item,
        requested_scope=requested_scope_for_action(action.action_id),
        allowed_outputs=READONLY_AUTHORIZATION_OUTPUT_FIELDS,
        forbidden_outputs=READONLY_AUTHORIZATION_FORBIDDEN_OUTPUTS,
        redaction_policy=redaction_policy_for_action(action.action_id),
    )


def requested_scope_for_action(action_id: str) -> str:
    scopes = {
        "read_environment_variable_metadata": "Check whether required environment variable names exist; never read or log their values.",
        "check_data_root_filesystem_metadata": "Check data root and planned audit path metadata; do not create files or list unrelated directories.",
        "check_tdx_root_and_txt_file_metadata": "Check TDX root and required txt file metadata; do not read file contents.",
        "open_short_postgresql_readonly_connection": "Open one short readonly PostgreSQL connection and inspect catalog metadata only.",
        "call_tushare_connectivity_probe": "Call minimum Tushare connectivity probe and discard response payload.",
        "call_mootdx_connectivity_probe": "Call minimum Mootdx connectivity probe and discard response payload.",
        "import_runtime_dependencies": "Import ingestion runtime dependency modules and report import status only.",
    }
    return scopes[action_id]


def redaction_policy_for_action(action_id: str) -> str:
    policies = {
        "read_environment_variable_metadata": "env_name_and_boolean_only",
        "check_data_root_filesystem_metadata": "path_capability_status_only_no_directory_listing",
        "check_tdx_root_and_txt_file_metadata": "path_readability_status_only_no_file_content",
        "open_short_postgresql_readonly_connection": "dsn_env_name_and_catalog_status_only_no_rows",
        "call_tushare_connectivity_probe": "connectivity_status_only_no_api_payload",
        "call_mootdx_connectivity_probe": "connectivity_status_only_no_api_payload",
        "import_runtime_dependencies": "module_name_and_import_status_only",
    }
    return policies[action_id]


def build_readonly_authorization_quality_gates(
    request: EnvironmentProbeReadOnlyAuthorizationRequest,
) -> list[QualityGateResult]:
    missing_actions = sorted(set(SENSITIVE_REAL_PROBE_ACTIONS) - set(request.action_ids))
    extra_actions = sorted(set(request.action_ids) - set(SENSITIVE_REAL_PROBE_ACTIONS))
    unpending_actions = [
        action_request.action_id
        for action_request in request.sensitive_action_requests
        if action_request.approval_status != "pending_user_confirmation" or action_request.will_execute
    ]
    invalid_approval_refs = [
        action_request.action_id
        for action_request in request.sensitive_action_requests
        if action_request.required_approval_item not in REQUIRED_PROBE_OPERATOR_APPROVALS
    ]
    missing_output_policies = [
        action_request.action_id
        for action_request in request.sensitive_action_requests
        if not action_request.allowed_outputs
        or not action_request.forbidden_outputs
        or not action_request.redaction_policy
    ]
    missing_forbidden_outputs = [
        action_request.action_id
        for action_request in request.sensitive_action_requests
        if set(READONLY_AUTHORIZATION_FORBIDDEN_OUTPUTS) - set(action_request.forbidden_outputs)
    ]
    missing_authorization_blockers = sorted(
        set(AUTHORIZATION_BLOCKERS) - set(request.inherited_authorization_blockers)
    )
    side_effect_flags = {
        "will_read_environment": request.will_read_environment,
        "will_check_filesystem": request.will_check_filesystem,
        "will_call_external_sources": request.will_call_external_sources,
        "will_read_tdx_files": request.will_read_tdx_files,
        "will_connect_database": request.will_connect_database,
        "will_execute_sql": request.will_execute_sql,
        "will_create_directories": request.will_create_directories,
        "will_write_data_files": request.will_write_data_files,
        "will_start_worker": request.will_start_worker,
        "will_authorize_real_probe": request.will_authorize_real_probe,
        "will_authorize_real_execution": request.will_authorize_real_execution,
    }
    enabled_side_effects = sorted(name for name, enabled in side_effect_flags.items() if enabled)

    return [
        QualityGateResult(
            gate_name="readonly_authorization_summary_passed_but_not_ready",
            status="passed" if request.input_summary_passed and not request.input_summary_ready_for_real_probe else "failed",
            expected_value="N3.12 authorization summary passed but is not ready_for_real_probe",
            actual_value=f"{request.input_summary_passed}/{request.input_summary_ready_for_real_probe}",
        ),
        QualityGateResult(
            gate_name="readonly_authorization_actions_cover_sensitive_scope",
            status="passed" if not missing_actions and not extra_actions else "failed",
            expected_value="/".join(SENSITIVE_REAL_PROBE_ACTIONS),
            actual_value="/".join(request.action_ids),
            details={"missing_actions": missing_actions, "extra_actions": extra_actions},
        ),
        QualityGateResult(
            gate_name="readonly_authorization_actions_pending_and_disabled",
            status="passed" if not unpending_actions else "failed",
            expected_value="all action requests pending and will_execute=false",
            actual_value=str(len(unpending_actions)),
            details={"unpending_actions": unpending_actions},
        ),
        QualityGateResult(
            gate_name="readonly_authorization_exact_phrase_required",
            status="passed" if request.required_authorization_phrase == REQUIRED_READONLY_AUTHORIZATION_PHRASE and not request.authorization_phrase_present else "failed",
            expected_value=REQUIRED_READONLY_AUTHORIZATION_PHRASE,
            actual_value=str(request.authorization_phrase_present).lower(),
        ),
        QualityGateResult(
            gate_name="readonly_authorization_approval_refs_valid",
            status="passed" if not invalid_approval_refs and len(request.pending_approval_item_ids) == 8 else "failed",
            expected_value="all action requests reference N3.9 approval items",
            actual_value=str(len(invalid_approval_refs)),
            details={"invalid_approval_refs": invalid_approval_refs},
        ),
        QualityGateResult(
            gate_name="readonly_authorization_output_policies_explicit",
            status="passed" if not missing_output_policies and not missing_forbidden_outputs else "failed",
            expected_value="allowed outputs, forbidden outputs, and redaction policy are explicit",
            actual_value=f"{len(missing_output_policies)}/{len(missing_forbidden_outputs)}",
            details={
                "missing_output_policies": missing_output_policies,
                "missing_forbidden_outputs": missing_forbidden_outputs,
            },
        ),
        QualityGateResult(
            gate_name="readonly_authorization_blockers_carried_forward",
            status="passed"
            if len(request.inherited_blocking_finding_ids) == 15 and not missing_authorization_blockers
            else "failed",
            expected_value="15 inherited blockers and N3.12 authorization blockers",
            actual_value=f"{len(request.inherited_blocking_finding_ids)}/{len(missing_authorization_blockers)}",
            details={"missing_authorization_blockers": missing_authorization_blockers},
        ),
        QualityGateResult(
            gate_name="readonly_authorization_not_ready_for_real_probe",
            status="passed" if not request.ready_for_real_probe else "failed",
            expected_value="N3.13 request does not authorize real probe",
            actual_value=str(request.ready_for_real_probe).lower(),
        ),
        QualityGateResult(
            gate_name="readonly_authorization_no_side_effects",
            status="passed" if not enabled_side_effects else "failed",
            expected_value="no env read, no filesystem check, no source calls, no TDX reads, no DB, no SQL, no mkdir, no writes, no worker, no authorization",
            actual_value=str(len(enabled_side_effects)),
            details={"enabled_side_effects": enabled_side_effects},
        ),
    ]
