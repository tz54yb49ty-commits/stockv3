"""Environment probe authorization boundary summary dry-run.

This module summarizes the authorization boundary before any future real
environment probe. It does not read environment variables, inspect the
filesystem, read local TDX files, connect PostgreSQL, execute SQL, call
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
from ashare_v3.ingestion.environment_probe_artifact_plan import (
    REQUIRED_ARTIFACT_KINDS,
    EnvironmentProbeArtifactPlan,
    build_environment_probe_artifact_plan,
)
from ashare_v3.ingestion.environment_probe_plan import REQUIRED_PROBE_ITEM_IDS
from ashare_v3.ingestion.ingestion_acceptance import quality_gate_to_dict
from ashare_v3.ingestion.parquet_archive import DEFAULT_DATA_ROOT
from ashare_v3.ingestion.real_execution_config import DEFAULT_REAL_EXECUTION_CONFIG
from ashare_v3.ingestion.schema_readiness import DEFAULT_SCHEMA_PATH


SENSITIVE_REAL_PROBE_ACTIONS = (
    "read_environment_variable_metadata",
    "check_data_root_filesystem_metadata",
    "check_tdx_root_and_txt_file_metadata",
    "open_short_postgresql_readonly_connection",
    "call_tushare_connectivity_probe",
    "call_mootdx_connectivity_probe",
    "import_runtime_dependencies",
)
AUTHORIZATION_BLOCKERS = (
    "pending_probe_operator_approvals",
    "inherited_probe_plan_not_ready",
    "artifact_plan_not_ready_to_write",
    "real_probe_not_authorized",
)


@dataclass(frozen=True)
class SensitiveProbeAction:
    action_id: str
    category: str
    description: str
    required_approval_item: str
    allowed_in_n3_12: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "category": self.category,
            "description": self.description,
            "required_approval_item": self.required_approval_item,
            "allowed_in_n3_12": self.allowed_in_n3_12,
        }


@dataclass(frozen=True)
class EnvironmentProbeAuthorizationSummary:
    summary_id: str
    artifact_plan_id: str
    runbook_id: str
    application_package_id: str
    probe_plan_id: str
    review_id: str
    data_root: str
    audit_root: str
    probe_item_ids: tuple[str, ...]
    runbook_step_ids: tuple[str, ...]
    artifact_kinds: tuple[str, ...]
    pending_approval_item_ids: tuple[str, ...]
    inherited_blocking_finding_ids: tuple[str, ...]
    inherited_blocking_result_item_ids: tuple[str, ...]
    sensitive_actions: tuple[SensitiveProbeAction, ...]
    authorization_blockers: tuple[str, ...]
    input_artifact_plan_passed: bool
    input_artifact_plan_ready_to_write: bool
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
    def sensitive_action_ids(self) -> tuple[str, ...]:
        return tuple(action.action_id for action in self.sensitive_actions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary_id": self.summary_id,
            "artifact_plan_id": self.artifact_plan_id,
            "runbook_id": self.runbook_id,
            "application_package_id": self.application_package_id,
            "probe_plan_id": self.probe_plan_id,
            "review_id": self.review_id,
            "data_root": self.data_root,
            "audit_root": self.audit_root,
            "passed": self.passed,
            "ready_for_real_probe": self.ready_for_real_probe,
            "probe_item_count": len(self.probe_item_ids),
            "runbook_step_count": len(self.runbook_step_ids),
            "artifact_count": len(self.artifact_kinds),
            "pending_approval_count": len(self.pending_approval_item_ids),
            "inherited_blocking_finding_count": len(self.inherited_blocking_finding_ids),
            "probe_item_ids": list(self.probe_item_ids),
            "runbook_step_ids": list(self.runbook_step_ids),
            "artifact_kinds": list(self.artifact_kinds),
            "pending_approval_item_ids": list(self.pending_approval_item_ids),
            "inherited_blocking_finding_ids": list(self.inherited_blocking_finding_ids),
            "inherited_blocking_result_item_ids": list(self.inherited_blocking_result_item_ids),
            "sensitive_action_ids": list(self.sensitive_action_ids),
            "sensitive_actions": [action.to_dict() for action in self.sensitive_actions],
            "authorization_blockers": list(self.authorization_blockers),
            "input_artifact_plan_passed": self.input_artifact_plan_passed,
            "input_artifact_plan_ready_to_write": self.input_artifact_plan_ready_to_write,
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


def build_environment_probe_authorization_summary(
    *,
    initial_config_path: str | Path = DEFAULT_INITIAL_BACKFILL_CONFIG,
    daily_config_path: str | Path = DEFAULT_DAILY_INCREMENTAL_CONFIG,
    real_config_path: str | Path = DEFAULT_REAL_EXECUTION_CONFIG,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
    data_root: str | None = None,
) -> EnvironmentProbeAuthorizationSummary:
    artifact_plan = build_environment_probe_artifact_plan(
        initial_config_path=initial_config_path,
        daily_config_path=daily_config_path,
        real_config_path=real_config_path,
        schema_path=schema_path,
        data_root=data_root or DEFAULT_DATA_ROOT,
    )
    return build_environment_probe_authorization_summary_from_artifact_plan(artifact_plan)


def build_environment_probe_authorization_summary_from_artifact_plan(
    artifact_plan: EnvironmentProbeArtifactPlan,
) -> EnvironmentProbeAuthorizationSummary:
    summary = EnvironmentProbeAuthorizationSummary(
        summary_id="environment_probe_authorization_summary_n3_12",
        artifact_plan_id=artifact_plan.plan_id,
        runbook_id=artifact_plan.runbook_id,
        application_package_id=artifact_plan.application_package_id,
        probe_plan_id=artifact_plan.probe_plan_id,
        review_id=artifact_plan.review_id,
        data_root=artifact_plan.data_root,
        audit_root=artifact_plan.audit_root,
        probe_item_ids=REQUIRED_PROBE_ITEM_IDS,
        runbook_step_ids=artifact_plan.inherited_step_ids,
        artifact_kinds=artifact_plan.artifact_kinds,
        pending_approval_item_ids=REQUIRED_PROBE_OPERATOR_APPROVALS,
        inherited_blocking_finding_ids=artifact_plan.inherited_blocking_finding_ids,
        inherited_blocking_result_item_ids=artifact_plan.inherited_blocking_result_item_ids,
        sensitive_actions=tuple(build_sensitive_probe_actions()),
        authorization_blockers=AUTHORIZATION_BLOCKERS,
        input_artifact_plan_passed=artifact_plan.passed,
        input_artifact_plan_ready_to_write=artifact_plan.ready_to_write,
        quality_gates=(),
    )
    return EnvironmentProbeAuthorizationSummary(
        summary_id=summary.summary_id,
        artifact_plan_id=summary.artifact_plan_id,
        runbook_id=summary.runbook_id,
        application_package_id=summary.application_package_id,
        probe_plan_id=summary.probe_plan_id,
        review_id=summary.review_id,
        data_root=summary.data_root,
        audit_root=summary.audit_root,
        probe_item_ids=summary.probe_item_ids,
        runbook_step_ids=summary.runbook_step_ids,
        artifact_kinds=summary.artifact_kinds,
        pending_approval_item_ids=summary.pending_approval_item_ids,
        inherited_blocking_finding_ids=summary.inherited_blocking_finding_ids,
        inherited_blocking_result_item_ids=summary.inherited_blocking_result_item_ids,
        sensitive_actions=summary.sensitive_actions,
        authorization_blockers=summary.authorization_blockers,
        input_artifact_plan_passed=summary.input_artifact_plan_passed,
        input_artifact_plan_ready_to_write=summary.input_artifact_plan_ready_to_write,
        quality_gates=tuple(build_authorization_summary_quality_gates(summary)),
    )


def build_sensitive_probe_actions() -> list[SensitiveProbeAction]:
    return [
        SensitiveProbeAction(
            action_id="read_environment_variable_metadata",
            category="security",
            description="Check whether TUSHARE_TOKEN and ASHARE_V3_POSTGRES_DSN variable names are bound without logging values.",
            required_approval_item="probe.security_env_metadata",
        ),
        SensitiveProbeAction(
            action_id="check_data_root_filesystem_metadata",
            category="archive",
            description="Check /Volumes/MacRaid/database and planned audit roots for existence and writability metadata.",
            required_approval_item="probe.archive_filesystem_metadata",
        ),
        SensitiveProbeAction(
            action_id="check_tdx_root_and_txt_file_metadata",
            category="tdx",
            description="Check /Volumes/MacRaid/tdxdata/tdx and required txt file readability metadata without reading contents.",
            required_approval_item="probe.tdx_local_file_metadata",
        ),
        SensitiveProbeAction(
            action_id="open_short_postgresql_readonly_connection",
            category="database",
            description="Open a short PostgreSQL readonly connectivity and catalog probe, then close it without writes.",
            required_approval_item="probe.database_readonly",
        ),
        SensitiveProbeAction(
            action_id="call_tushare_connectivity_probe",
            category="source",
            description="Call a Tushare connectivity probe without storing market payloads.",
            required_approval_item="probe.source_connectivity",
        ),
        SensitiveProbeAction(
            action_id="call_mootdx_connectivity_probe",
            category="source",
            description="Call a Mootdx connectivity probe without storing market payloads.",
            required_approval_item="probe.source_connectivity",
        ),
        SensitiveProbeAction(
            action_id="import_runtime_dependencies",
            category="runtime",
            description="Import pandas, pyarrow, psycopg, tushare, and mootdx to verify runtime availability.",
            required_approval_item="probe.runtime_import_checks",
        ),
    ]


def build_authorization_summary_quality_gates(
    summary: EnvironmentProbeAuthorizationSummary,
) -> list[QualityGateResult]:
    missing_probe_items = sorted(set(REQUIRED_PROBE_ITEM_IDS) - set(summary.probe_item_ids))
    missing_runbook_steps = len(summary.runbook_step_ids) != len(REQUIRED_PROBE_ITEM_IDS)
    missing_artifacts = sorted(set(REQUIRED_ARTIFACT_KINDS) - set(summary.artifact_kinds))
    extra_artifacts = sorted(set(summary.artifact_kinds) - set(REQUIRED_ARTIFACT_KINDS))
    missing_approvals = sorted(set(REQUIRED_PROBE_OPERATOR_APPROVALS) - set(summary.pending_approval_item_ids))
    missing_sensitive_actions = sorted(set(SENSITIVE_REAL_PROBE_ACTIONS) - set(summary.sensitive_action_ids))
    unblocked_sensitive_actions = [
        action.action_id for action in summary.sensitive_actions if action.allowed_in_n3_12
    ]
    missing_authorization_blockers = sorted(set(AUTHORIZATION_BLOCKERS) - set(summary.authorization_blockers))
    side_effect_flags = {
        "will_read_environment": summary.will_read_environment,
        "will_check_filesystem": summary.will_check_filesystem,
        "will_call_external_sources": summary.will_call_external_sources,
        "will_read_tdx_files": summary.will_read_tdx_files,
        "will_connect_database": summary.will_connect_database,
        "will_execute_sql": summary.will_execute_sql,
        "will_create_directories": summary.will_create_directories,
        "will_write_data_files": summary.will_write_data_files,
        "will_start_worker": summary.will_start_worker,
        "will_authorize_real_probe": summary.will_authorize_real_probe,
        "will_authorize_real_execution": summary.will_authorize_real_execution,
    }
    enabled_side_effects = sorted(name for name, enabled in side_effect_flags.items() if enabled)

    return [
        QualityGateResult(
            gate_name="probe_authorization_artifact_plan_passed_but_not_ready",
            status="passed" if summary.input_artifact_plan_passed and not summary.input_artifact_plan_ready_to_write else "failed",
            expected_value="N3.11 artifact plan passed but is not ready_to_write",
            actual_value=f"{summary.input_artifact_plan_passed}/{summary.input_artifact_plan_ready_to_write}",
        ),
        QualityGateResult(
            gate_name="probe_authorization_probe_scope_complete",
            status="passed" if not missing_probe_items and not missing_runbook_steps else "failed",
            expected_value="14 probe items and 14 runbook steps",
            actual_value=f"{len(summary.probe_item_ids)}/{len(summary.runbook_step_ids)}",
            details={"missing_probe_items": missing_probe_items, "missing_runbook_steps": missing_runbook_steps},
        ),
        QualityGateResult(
            gate_name="probe_authorization_artifacts_complete",
            status="passed" if not missing_artifacts and not extra_artifacts else "failed",
            expected_value="/".join(REQUIRED_ARTIFACT_KINDS),
            actual_value="/".join(summary.artifact_kinds),
            details={"missing_artifacts": missing_artifacts, "extra_artifacts": extra_artifacts},
        ),
        QualityGateResult(
            gate_name="probe_authorization_approvals_still_pending",
            status="passed" if not missing_approvals and len(summary.pending_approval_item_ids) == 8 else "failed",
            expected_value="8 pending probe operator approvals",
            actual_value=str(len(summary.pending_approval_item_ids)),
            details={"missing_approvals": missing_approvals},
        ),
        QualityGateResult(
            gate_name="probe_authorization_blockers_carried_forward",
            status="passed" if len(summary.inherited_blocking_finding_ids) == 15 else "failed",
            expected_value="15 inherited blockers",
            actual_value=str(len(summary.inherited_blocking_finding_ids)),
        ),
        QualityGateResult(
            gate_name="probe_authorization_sensitive_actions_declared",
            status="passed" if not missing_sensitive_actions and not unblocked_sensitive_actions else "failed",
            expected_value="all sensitive real-probe actions declared and disabled",
            actual_value=f"{len(summary.sensitive_actions)}/{len(unblocked_sensitive_actions)}",
            details={
                "missing_sensitive_actions": missing_sensitive_actions,
                "unblocked_sensitive_actions": unblocked_sensitive_actions,
            },
        ),
        QualityGateResult(
            gate_name="probe_authorization_blockers_explicit",
            status="passed" if not missing_authorization_blockers else "failed",
            expected_value="/".join(AUTHORIZATION_BLOCKERS),
            actual_value="/".join(summary.authorization_blockers),
            details={"missing_authorization_blockers": missing_authorization_blockers},
        ),
        QualityGateResult(
            gate_name="probe_authorization_not_ready_for_real_probe",
            status="passed" if not summary.ready_for_real_probe else "failed",
            expected_value="summary does not authorize real environment probe",
            actual_value=str(summary.ready_for_real_probe).lower(),
        ),
        QualityGateResult(
            gate_name="probe_authorization_no_side_effects",
            status="passed" if not enabled_side_effects else "failed",
            expected_value="no env read, no filesystem check, no source calls, no TDX reads, no DB, no SQL, no mkdir, no writes, no worker, no authorization",
            actual_value=str(len(enabled_side_effects)),
            details={"enabled_side_effects": enabled_side_effects},
        ),
    ]
