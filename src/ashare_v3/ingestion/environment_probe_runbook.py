"""Environment probe execution runbook dry-run.

This module turns the N3.9 environment probe application package into an
ordered runbook for a future probe. It does not read environment variables,
inspect the filesystem, read local TDX files, connect PostgreSQL, execute SQL,
call external APIs, write files, start workers, or authorize real execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ashare_v3.ingestion.backfill_config import DEFAULT_INITIAL_BACKFILL_CONFIG
from ashare_v3.ingestion.common import QualityGateResult
from ashare_v3.ingestion.daily_incremental_config import DEFAULT_DAILY_INCREMENTAL_CONFIG
from ashare_v3.ingestion.environment_probe_application import (
    REQUIRED_PROBE_OPERATOR_APPROVALS,
    EnvironmentProbeApplicationPackage,
    EnvironmentProbeExecutionRequest,
    build_environment_probe_application_package,
)
from ashare_v3.ingestion.environment_probe_plan import REQUIRED_PROBE_CATEGORIES, REQUIRED_PROBE_ITEM_IDS
from ashare_v3.ingestion.ingestion_acceptance import quality_gate_to_dict
from ashare_v3.ingestion.parquet_archive import DEFAULT_DATA_ROOT
from ashare_v3.ingestion.real_execution_config import DEFAULT_REAL_EXECUTION_CONFIG
from ashare_v3.ingestion.schema_readiness import DEFAULT_SCHEMA_PATH


RUNBOOK_CATEGORY_ORDER = ("security", "database", "archive", "tdx", "source", "runtime", "safety")
APPROVAL_DEPENDENCY_BY_CATEGORY = {
    "security": "probe.security_env_metadata",
    "database": "probe.database_readonly",
    "archive": "probe.archive_filesystem_metadata",
    "tdx": "probe.tdx_local_file_metadata",
    "source": "probe.source_connectivity",
    "runtime": "probe.runtime_import_checks",
    "safety": "probe.safety_boundary",
}


@dataclass(frozen=True)
class EnvironmentProbeRunbookStep:
    step_id: str
    step_order: int
    item_id: str
    category: str
    target_kind: str
    target: str
    planned_probe: str
    required_permission: str
    approval_dependency: str
    redaction_policy: str
    evidence_policy: str
    abort_on_failure: bool
    cleanup_policy: str
    approval_status: str
    will_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_order": self.step_order,
            "item_id": self.item_id,
            "category": self.category,
            "target_kind": self.target_kind,
            "target": self.target,
            "planned_probe": self.planned_probe,
            "required_permission": self.required_permission,
            "approval_dependency": self.approval_dependency,
            "redaction_policy": self.redaction_policy,
            "evidence_policy": self.evidence_policy,
            "abort_on_failure": self.abort_on_failure,
            "cleanup_policy": self.cleanup_policy,
            "approval_status": self.approval_status,
            "will_run": self.will_run,
        }


@dataclass(frozen=True)
class EnvironmentProbeRunbook:
    runbook_id: str
    application_package_id: str
    probe_plan_id: str
    review_id: str
    data_root: str
    tdx_root: str
    required_env_vars: tuple[str, ...]
    steps: tuple[EnvironmentProbeRunbookStep, ...]
    inherited_pending_approval_item_ids: tuple[str, ...]
    inherited_blocking_finding_ids: tuple[str, ...]
    inherited_blocking_result_item_ids: tuple[str, ...]
    input_application_passed: bool
    input_application_ready_to_probe: bool
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
    will_authorize_real_execution: bool = False

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.quality_gates)

    @property
    def ready_to_run(self) -> bool:
        return False

    @property
    def step_ids(self) -> tuple[str, ...]:
        return tuple(step.step_id for step in self.steps)

    @property
    def step_item_ids(self) -> tuple[str, ...]:
        return tuple(step.item_id for step in self.steps)

    @property
    def pending_step_ids(self) -> tuple[str, ...]:
        return tuple(step.step_id for step in self.steps if step.approval_status != "confirmed" or not step.will_run)

    @property
    def category_order(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(step.category for step in self.steps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "runbook_id": self.runbook_id,
            "application_package_id": self.application_package_id,
            "probe_plan_id": self.probe_plan_id,
            "review_id": self.review_id,
            "data_root": self.data_root,
            "tdx_root": self.tdx_root,
            "required_env_vars": list(self.required_env_vars),
            "passed": self.passed,
            "ready_to_run": self.ready_to_run,
            "input_application_passed": self.input_application_passed,
            "input_application_ready_to_probe": self.input_application_ready_to_probe,
            "step_count": len(self.steps),
            "category_order": list(self.category_order),
            "pending_step_ids": list(self.pending_step_ids),
            "inherited_pending_approval_item_ids": list(self.inherited_pending_approval_item_ids),
            "inherited_blocking_finding_ids": list(self.inherited_blocking_finding_ids),
            "inherited_blocking_result_item_ids": list(self.inherited_blocking_result_item_ids),
            "steps": [step.to_dict() for step in self.steps],
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
                "will_authorize_real_execution": self.will_authorize_real_execution,
            },
        }


def build_environment_probe_runbook(
    *,
    initial_config_path: str | Path = DEFAULT_INITIAL_BACKFILL_CONFIG,
    daily_config_path: str | Path = DEFAULT_DAILY_INCREMENTAL_CONFIG,
    real_config_path: str | Path = DEFAULT_REAL_EXECUTION_CONFIG,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
    data_root: str | None = None,
) -> EnvironmentProbeRunbook:
    application = build_environment_probe_application_package(
        initial_config_path=initial_config_path,
        daily_config_path=daily_config_path,
        real_config_path=real_config_path,
        schema_path=schema_path,
        data_root=data_root or DEFAULT_DATA_ROOT,
    )
    return build_environment_probe_runbook_from_application(application)


def build_environment_probe_runbook_from_application(
    application: EnvironmentProbeApplicationPackage,
) -> EnvironmentProbeRunbook:
    steps = tuple(build_runbook_steps(application.probe_requests))
    runbook = EnvironmentProbeRunbook(
        runbook_id="environment_probe_runbook_n3_10",
        application_package_id=application.package_id,
        probe_plan_id=application.probe_plan_id,
        review_id=application.review_id,
        data_root=application.data_root,
        tdx_root=application.tdx_root,
        required_env_vars=application.required_env_vars,
        steps=steps,
        inherited_pending_approval_item_ids=application.pending_approval_item_ids,
        inherited_blocking_finding_ids=application.inherited_blocking_finding_ids,
        inherited_blocking_result_item_ids=application.inherited_blocking_result_item_ids,
        input_application_passed=application.passed,
        input_application_ready_to_probe=application.ready_to_probe,
        quality_gates=(),
    )
    return EnvironmentProbeRunbook(
        runbook_id=runbook.runbook_id,
        application_package_id=runbook.application_package_id,
        probe_plan_id=runbook.probe_plan_id,
        review_id=runbook.review_id,
        data_root=runbook.data_root,
        tdx_root=runbook.tdx_root,
        required_env_vars=runbook.required_env_vars,
        steps=runbook.steps,
        inherited_pending_approval_item_ids=runbook.inherited_pending_approval_item_ids,
        inherited_blocking_finding_ids=runbook.inherited_blocking_finding_ids,
        inherited_blocking_result_item_ids=runbook.inherited_blocking_result_item_ids,
        input_application_passed=runbook.input_application_passed,
        input_application_ready_to_probe=runbook.input_application_ready_to_probe,
        quality_gates=tuple(build_runbook_quality_gates(runbook)),
    )


def build_runbook_steps(
    probe_requests: tuple[EnvironmentProbeExecutionRequest, ...],
) -> list[EnvironmentProbeRunbookStep]:
    sorted_requests = sorted(
        probe_requests,
        key=lambda request: (
            RUNBOOK_CATEGORY_ORDER.index(request.category),
            list(REQUIRED_PROBE_ITEM_IDS).index(request.item_id),
        ),
    )
    return [
        EnvironmentProbeRunbookStep(
            step_id=f"probe_step_{step_order:02d}_{request.item_id}",
            step_order=step_order,
            item_id=request.item_id,
            category=request.category,
            target_kind=request.target_kind,
            target=request.target,
            planned_probe=request.planned_probe,
            required_permission=request.required_permission,
            approval_dependency=approval_dependency_for_request(request),
            redaction_policy=request.redaction_policy,
            evidence_policy=request.evidence_policy,
            abort_on_failure=True,
            cleanup_policy=cleanup_policy_for_category(request.category),
            approval_status=request.approval_status,
            will_run=False,
        )
        for step_order, request in enumerate(sorted_requests, start=1)
    ]


def approval_dependency_for_request(request: EnvironmentProbeExecutionRequest) -> str:
    if request.item_id == "safety.no_worker_or_service_start":
        return "probe.no_writes_or_workers"
    return APPROVAL_DEPENDENCY_BY_CATEGORY[request.category]


def cleanup_policy_for_category(category: str) -> str:
    policies = {
        "security": "no_secret_values_captured",
        "database": "close_probe_connection_without_writes",
        "archive": "no_files_or_directories_created",
        "tdx": "no_file_content_captured",
        "source": "discard_connectivity_response_payload",
        "runtime": "no_runtime_state_persisted",
        "safety": "no_services_or_workers_started",
    }
    return policies[category]


def build_runbook_quality_gates(runbook: EnvironmentProbeRunbook) -> list[QualityGateResult]:
    step_item_ids = set(runbook.step_item_ids)
    missing_steps = sorted(set(REQUIRED_PROBE_ITEM_IDS) - step_item_ids)
    extra_steps = sorted(step_item_ids - set(REQUIRED_PROBE_ITEM_IDS))
    invalid_category_order = runbook.category_order != RUNBOOK_CATEGORY_ORDER
    unpending_steps = [
        step.step_id
        for step in runbook.steps
        if step.approval_status != "pending_user_confirmation" or step.will_run
    ]
    invalid_approval_dependencies = [
        step.step_id
        for step in runbook.steps
        if step.approval_dependency not in REQUIRED_PROBE_OPERATOR_APPROVALS
    ]
    missing_abort_or_cleanup = [
        step.step_id
        for step in runbook.steps
        if not step.abort_on_failure or not step.cleanup_policy
    ]
    side_effect_flags = {
        "will_read_environment": runbook.will_read_environment,
        "will_check_filesystem": runbook.will_check_filesystem,
        "will_call_external_sources": runbook.will_call_external_sources,
        "will_read_tdx_files": runbook.will_read_tdx_files,
        "will_connect_database": runbook.will_connect_database,
        "will_execute_sql": runbook.will_execute_sql,
        "will_create_directories": runbook.will_create_directories,
        "will_write_data_files": runbook.will_write_data_files,
        "will_start_worker": runbook.will_start_worker,
        "will_authorize_real_execution": runbook.will_authorize_real_execution,
    }
    enabled_side_effects = sorted(name for name, enabled in side_effect_flags.items() if enabled)

    return [
        QualityGateResult(
            gate_name="probe_runbook_application_passed_but_not_ready",
            status="passed" if runbook.input_application_passed and not runbook.input_application_ready_to_probe else "failed",
            expected_value="N3.9 application passed but is not ready_to_probe",
            actual_value=f"{runbook.input_application_passed}/{runbook.input_application_ready_to_probe}",
        ),
        QualityGateResult(
            gate_name="probe_runbook_steps_cover_required_items",
            status="passed" if not missing_steps and not extra_steps else "failed",
            expected_value=str(len(REQUIRED_PROBE_ITEM_IDS)),
            actual_value=str(len(runbook.steps)),
            details={"missing_steps": missing_steps, "extra_steps": extra_steps},
        ),
        QualityGateResult(
            gate_name="probe_runbook_category_order_valid",
            status="passed" if not invalid_category_order else "failed",
            expected_value="/".join(RUNBOOK_CATEGORY_ORDER),
            actual_value="/".join(runbook.category_order),
        ),
        QualityGateResult(
            gate_name="probe_runbook_steps_pending_and_disabled",
            status="passed" if not unpending_steps else "failed",
            expected_value="all runbook steps pending and will_run=false",
            actual_value=str(len(unpending_steps)),
            details={"unpending_steps": unpending_steps},
        ),
        QualityGateResult(
            gate_name="probe_runbook_approval_dependencies_valid",
            status="passed" if not invalid_approval_dependencies else "failed",
            expected_value="step approval dependencies are N3.9 operator approval ids",
            actual_value=str(len(invalid_approval_dependencies)),
            details={"invalid_approval_dependencies": invalid_approval_dependencies},
        ),
        QualityGateResult(
            gate_name="probe_runbook_abort_and_cleanup_explicit",
            status="passed" if not missing_abort_or_cleanup else "failed",
            expected_value="each step aborts on failure and has cleanup policy",
            actual_value=str(len(missing_abort_or_cleanup)),
            details={"missing_abort_or_cleanup": missing_abort_or_cleanup},
        ),
        QualityGateResult(
            gate_name="probe_runbook_inherits_application_blockers",
            status="passed" if len(runbook.inherited_blocking_finding_ids) == 15 else "failed",
            expected_value="15 inherited N3.8 blockers",
            actual_value=str(len(runbook.inherited_blocking_finding_ids)),
        ),
        QualityGateResult(
            gate_name="probe_runbook_not_ready_to_run",
            status="passed" if not runbook.ready_to_run else "failed",
            expected_value="runbook does not authorize probe execution",
            actual_value=str(runbook.ready_to_run).lower(),
        ),
        QualityGateResult(
            gate_name="probe_runbook_no_side_effects",
            status="passed" if not enabled_side_effects else "failed",
            expected_value="no env read, no filesystem check, no source calls, no TDX reads, no DB, no SQL, no writes, no worker",
            actual_value=str(len(enabled_side_effects)),
            details={"enabled_side_effects": enabled_side_effects},
        ),
    ]
