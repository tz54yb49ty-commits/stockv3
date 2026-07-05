"""Environment probe result artifact plan dry-run.

This module defines the future on-disk audit artifact shape for environment
probe results. It does not read environment variables, inspect the filesystem,
read local TDX files, connect PostgreSQL, execute SQL, call external APIs,
create directories, write files, start workers, or authorize real execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ashare_v3.ingestion.backfill_config import DEFAULT_INITIAL_BACKFILL_CONFIG
from ashare_v3.ingestion.common import QualityGateResult
from ashare_v3.ingestion.daily_incremental_config import DEFAULT_DAILY_INCREMENTAL_CONFIG
from ashare_v3.ingestion.environment_probe_plan import REQUIRED_PROBE_ITEM_IDS
from ashare_v3.ingestion.environment_probe_runbook import EnvironmentProbeRunbook, build_environment_probe_runbook
from ashare_v3.ingestion.ingestion_acceptance import quality_gate_to_dict
from ashare_v3.ingestion.parquet_archive import DEFAULT_DATA_ROOT
from ashare_v3.ingestion.real_execution_config import DEFAULT_REAL_EXECUTION_CONFIG
from ashare_v3.ingestion.schema_readiness import DEFAULT_SCHEMA_PATH


DEFAULT_PROBE_RUN_ID_PATTERN = "env_probe_YYYYMMDDThhmmssZ_vN"
REQUIRED_ARTIFACT_KINDS = (
    "probe_results",
    "probe_manifest",
    "probe_quality_gates",
    "probe_rollback_manifest",
)
FORBIDDEN_PERSISTED_FIELDS = (
    "tushare_token_value",
    "postgres_dsn_value",
    "ashare_v3_postgres_dsn_value",
    "tdx_file_content",
    "tdx_directory_listing",
    "external_api_payload",
    "market_data_payload",
    "postgres_result_rows",
    "secret_environment_values",
)
RESULT_ARTIFACT_REQUIRED_FIELDS = (
    "probe_run_id",
    "runbook_id",
    "started_at",
    "finished_at",
    "result_status_counts",
    "blocking_result_item_ids",
    "probe_results",
    "quality_gates",
    "side_effect_summary",
)
PROBE_RESULT_REQUIRED_FIELDS = (
    "item_id",
    "category",
    "target_kind",
    "target",
    "planned_probe",
    "result_status",
    "severity",
    "blocking",
    "probe_executed",
    "error_summary",
    "evidence",
)


@dataclass(frozen=True)
class EnvironmentProbeArtifactFilePlan:
    artifact_kind: str
    file_format: str
    planned_path: str
    required_fields: tuple[str, ...]
    forbidden_fields: tuple[str, ...]
    redaction_required: bool
    deletion_strategy: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_kind": self.artifact_kind,
            "file_format": self.file_format,
            "planned_path": self.planned_path,
            "required_fields": list(self.required_fields),
            "forbidden_fields": list(self.forbidden_fields),
            "redaction_required": self.redaction_required,
            "deletion_strategy": self.deletion_strategy,
        }


@dataclass(frozen=True)
class EnvironmentProbeArtifactPlan:
    plan_id: str
    runbook_id: str
    application_package_id: str
    probe_plan_id: str
    review_id: str
    data_root: str
    audit_root: str
    probe_run_id_pattern: str
    artifact_files: tuple[EnvironmentProbeArtifactFilePlan, ...]
    result_artifact_required_fields: tuple[str, ...]
    probe_result_required_fields: tuple[str, ...]
    forbidden_persisted_fields: tuple[str, ...]
    inherited_step_ids: tuple[str, ...]
    inherited_blocking_finding_ids: tuple[str, ...]
    inherited_blocking_result_item_ids: tuple[str, ...]
    input_runbook_passed: bool
    input_runbook_ready_to_run: bool
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
    def ready_to_write(self) -> bool:
        return False

    @property
    def artifact_kinds(self) -> tuple[str, ...]:
        return tuple(file_plan.artifact_kind for file_plan in self.artifact_files)

    @property
    def planned_paths(self) -> tuple[str, ...]:
        return tuple(file_plan.planned_path for file_plan in self.artifact_files)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "runbook_id": self.runbook_id,
            "application_package_id": self.application_package_id,
            "probe_plan_id": self.probe_plan_id,
            "review_id": self.review_id,
            "data_root": self.data_root,
            "audit_root": self.audit_root,
            "probe_run_id_pattern": self.probe_run_id_pattern,
            "passed": self.passed,
            "ready_to_write": self.ready_to_write,
            "artifact_count": len(self.artifact_files),
            "artifact_kinds": list(self.artifact_kinds),
            "planned_paths": list(self.planned_paths),
            "result_artifact_required_fields": list(self.result_artifact_required_fields),
            "probe_result_required_fields": list(self.probe_result_required_fields),
            "forbidden_persisted_fields": list(self.forbidden_persisted_fields),
            "inherited_step_ids": list(self.inherited_step_ids),
            "inherited_blocking_finding_ids": list(self.inherited_blocking_finding_ids),
            "inherited_blocking_result_item_ids": list(self.inherited_blocking_result_item_ids),
            "input_runbook_passed": self.input_runbook_passed,
            "input_runbook_ready_to_run": self.input_runbook_ready_to_run,
            "artifact_files": [file_plan.to_dict() for file_plan in self.artifact_files],
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


def build_environment_probe_artifact_plan(
    *,
    initial_config_path: str | Path = DEFAULT_INITIAL_BACKFILL_CONFIG,
    daily_config_path: str | Path = DEFAULT_DAILY_INCREMENTAL_CONFIG,
    real_config_path: str | Path = DEFAULT_REAL_EXECUTION_CONFIG,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
    data_root: str | None = None,
) -> EnvironmentProbeArtifactPlan:
    runbook = build_environment_probe_runbook(
        initial_config_path=initial_config_path,
        daily_config_path=daily_config_path,
        real_config_path=real_config_path,
        schema_path=schema_path,
        data_root=data_root or DEFAULT_DATA_ROOT,
    )
    return build_environment_probe_artifact_plan_from_runbook(runbook)


def build_environment_probe_artifact_plan_from_runbook(
    runbook: EnvironmentProbeRunbook,
) -> EnvironmentProbeArtifactPlan:
    audit_root = str(PurePosixPath(runbook.data_root) / "audit" / "environment_probe")
    artifact_files = tuple(build_artifact_file_plans(audit_root))
    plan = EnvironmentProbeArtifactPlan(
        plan_id="environment_probe_artifact_plan_n3_11",
        runbook_id=runbook.runbook_id,
        application_package_id=runbook.application_package_id,
        probe_plan_id=runbook.probe_plan_id,
        review_id=runbook.review_id,
        data_root=runbook.data_root,
        audit_root=audit_root,
        probe_run_id_pattern=DEFAULT_PROBE_RUN_ID_PATTERN,
        artifact_files=artifact_files,
        result_artifact_required_fields=RESULT_ARTIFACT_REQUIRED_FIELDS,
        probe_result_required_fields=PROBE_RESULT_REQUIRED_FIELDS,
        forbidden_persisted_fields=FORBIDDEN_PERSISTED_FIELDS,
        inherited_step_ids=runbook.step_ids,
        inherited_blocking_finding_ids=runbook.inherited_blocking_finding_ids,
        inherited_blocking_result_item_ids=runbook.inherited_blocking_result_item_ids,
        input_runbook_passed=runbook.passed,
        input_runbook_ready_to_run=runbook.ready_to_run,
        quality_gates=(),
    )
    return EnvironmentProbeArtifactPlan(
        plan_id=plan.plan_id,
        runbook_id=plan.runbook_id,
        application_package_id=plan.application_package_id,
        probe_plan_id=plan.probe_plan_id,
        review_id=plan.review_id,
        data_root=plan.data_root,
        audit_root=plan.audit_root,
        probe_run_id_pattern=plan.probe_run_id_pattern,
        artifact_files=plan.artifact_files,
        result_artifact_required_fields=plan.result_artifact_required_fields,
        probe_result_required_fields=plan.probe_result_required_fields,
        forbidden_persisted_fields=plan.forbidden_persisted_fields,
        inherited_step_ids=plan.inherited_step_ids,
        inherited_blocking_finding_ids=plan.inherited_blocking_finding_ids,
        inherited_blocking_result_item_ids=plan.inherited_blocking_result_item_ids,
        input_runbook_passed=plan.input_runbook_passed,
        input_runbook_ready_to_run=plan.input_runbook_ready_to_run,
        quality_gates=tuple(build_artifact_plan_quality_gates(plan)),
    )


def build_artifact_file_plans(audit_root: str) -> list[EnvironmentProbeArtifactFilePlan]:
    run_root = str(PurePosixPath(audit_root) / "probe_run_id=env_probe_YYYYMMDDThhmmssZ_vN")
    return [
        EnvironmentProbeArtifactFilePlan(
            artifact_kind="probe_results",
            file_format="json",
            planned_path=str(PurePosixPath(run_root) / "results.json"),
            required_fields=RESULT_ARTIFACT_REQUIRED_FIELDS,
            forbidden_fields=FORBIDDEN_PERSISTED_FIELDS,
            redaction_required=True,
            deletion_strategy="delete_probe_run_directory_by_probe_run_id",
        ),
        EnvironmentProbeArtifactFilePlan(
            artifact_kind="probe_manifest",
            file_format="json",
            planned_path=str(PurePosixPath(run_root) / "manifest.json"),
            required_fields=(
                "probe_run_id",
                "runbook_id",
                "artifact_paths",
                "forbidden_persisted_fields",
                "redaction_policy_summary",
            ),
            forbidden_fields=FORBIDDEN_PERSISTED_FIELDS,
            redaction_required=True,
            deletion_strategy="delete_probe_run_directory_by_probe_run_id",
        ),
        EnvironmentProbeArtifactFilePlan(
            artifact_kind="probe_quality_gates",
            file_format="json",
            planned_path=str(PurePosixPath(run_root) / "quality_gates.json"),
            required_fields=("probe_run_id", "quality_gates", "blocking_result_item_ids"),
            forbidden_fields=FORBIDDEN_PERSISTED_FIELDS,
            redaction_required=True,
            deletion_strategy="delete_probe_run_directory_by_probe_run_id",
        ),
        EnvironmentProbeArtifactFilePlan(
            artifact_kind="probe_rollback_manifest",
            file_format="json",
            planned_path=str(PurePosixPath(run_root) / "rollback_manifest.json"),
            required_fields=("probe_run_id", "rollback_paths", "deletion_strategy", "created_artifact_paths"),
            forbidden_fields=FORBIDDEN_PERSISTED_FIELDS,
            redaction_required=True,
            deletion_strategy="delete_probe_run_directory_by_probe_run_id",
        ),
    ]


def build_artifact_plan_quality_gates(plan: EnvironmentProbeArtifactPlan) -> list[QualityGateResult]:
    missing_artifact_kinds = sorted(set(REQUIRED_ARTIFACT_KINDS) - set(plan.artifact_kinds))
    extra_artifact_kinds = sorted(set(plan.artifact_kinds) - set(REQUIRED_ARTIFACT_KINDS))
    paths_outside_audit_root = [
        path for path in plan.planned_paths if not path.startswith(f"{plan.audit_root}/")
    ]
    missing_required_result_fields = sorted(
        set(RESULT_ARTIFACT_REQUIRED_FIELDS) - set(plan.result_artifact_required_fields)
    )
    missing_probe_result_fields = sorted(
        set(PROBE_RESULT_REQUIRED_FIELDS) - set(plan.probe_result_required_fields)
    )
    missing_forbidden_fields = sorted(set(FORBIDDEN_PERSISTED_FIELDS) - set(plan.forbidden_persisted_fields))
    non_redacted_artifacts = [
        file_plan.artifact_kind
        for file_plan in plan.artifact_files
        if not file_plan.redaction_required
    ]
    non_deletable_artifacts = [
        file_plan.artifact_kind
        for file_plan in plan.artifact_files
        if file_plan.deletion_strategy != "delete_probe_run_directory_by_probe_run_id"
    ]
    side_effect_flags = {
        "will_read_environment": plan.will_read_environment,
        "will_check_filesystem": plan.will_check_filesystem,
        "will_call_external_sources": plan.will_call_external_sources,
        "will_read_tdx_files": plan.will_read_tdx_files,
        "will_connect_database": plan.will_connect_database,
        "will_execute_sql": plan.will_execute_sql,
        "will_create_directories": plan.will_create_directories,
        "will_write_data_files": plan.will_write_data_files,
        "will_start_worker": plan.will_start_worker,
        "will_authorize_real_execution": plan.will_authorize_real_execution,
    }
    enabled_side_effects = sorted(name for name, enabled in side_effect_flags.items() if enabled)

    return [
        QualityGateResult(
            gate_name="probe_artifact_plan_runbook_passed_but_not_ready",
            status="passed" if plan.input_runbook_passed and not plan.input_runbook_ready_to_run else "failed",
            expected_value="N3.10 runbook passed but is not ready_to_run",
            actual_value=f"{plan.input_runbook_passed}/{plan.input_runbook_ready_to_run}",
        ),
        QualityGateResult(
            gate_name="probe_artifact_plan_kinds_complete",
            status="passed" if not missing_artifact_kinds and not extra_artifact_kinds else "failed",
            expected_value="/".join(REQUIRED_ARTIFACT_KINDS),
            actual_value="/".join(plan.artifact_kinds),
            details={"missing_artifact_kinds": missing_artifact_kinds, "extra_artifact_kinds": extra_artifact_kinds},
        ),
        QualityGateResult(
            gate_name="probe_artifact_plan_paths_under_audit_root",
            status="passed" if not paths_outside_audit_root else "failed",
            expected_value=f"{plan.audit_root}/...",
            actual_value=str(len(paths_outside_audit_root)),
            details={"paths_outside_audit_root": paths_outside_audit_root},
        ),
        QualityGateResult(
            gate_name="probe_artifact_plan_result_schema_complete",
            status="passed" if not missing_required_result_fields and not missing_probe_result_fields else "failed",
            expected_value="required result and per-item result fields present",
            actual_value=f"{len(missing_required_result_fields)}/{len(missing_probe_result_fields)}",
            details={
                "missing_required_result_fields": missing_required_result_fields,
                "missing_probe_result_fields": missing_probe_result_fields,
            },
        ),
        QualityGateResult(
            gate_name="probe_artifact_plan_forbidden_fields_explicit",
            status="passed" if not missing_forbidden_fields else "failed",
            expected_value="secret values, payloads, and file contents forbidden",
            actual_value=str(len(missing_forbidden_fields)),
            details={"missing_forbidden_fields": missing_forbidden_fields},
        ),
        QualityGateResult(
            gate_name="probe_artifact_plan_redaction_and_deletion_explicit",
            status="passed" if not non_redacted_artifacts and not non_deletable_artifacts else "failed",
            expected_value="all artifacts redacted and deletable by probe_run_id",
            actual_value=f"{len(non_redacted_artifacts)}/{len(non_deletable_artifacts)}",
            details={
                "non_redacted_artifacts": non_redacted_artifacts,
                "non_deletable_artifacts": non_deletable_artifacts,
            },
        ),
        QualityGateResult(
            gate_name="probe_artifact_plan_inherits_runbook_scope",
            status="passed"
            if len(plan.inherited_step_ids) == len(REQUIRED_PROBE_ITEM_IDS)
            and len(plan.inherited_blocking_finding_ids) == 15
            else "failed",
            expected_value="14 runbook steps and 15 inherited blockers",
            actual_value=f"{len(plan.inherited_step_ids)}/{len(plan.inherited_blocking_finding_ids)}",
        ),
        QualityGateResult(
            gate_name="probe_artifact_plan_not_ready_to_write",
            status="passed" if not plan.ready_to_write else "failed",
            expected_value="artifact plan does not authorize file writes",
            actual_value=str(plan.ready_to_write).lower(),
        ),
        QualityGateResult(
            gate_name="probe_artifact_plan_no_side_effects",
            status="passed" if not enabled_side_effects else "failed",
            expected_value="no env read, no filesystem check, no source calls, no TDX reads, no DB, no SQL, no mkdir, no writes, no worker",
            actual_value=str(len(enabled_side_effects)),
            details={"enabled_side_effects": enabled_side_effects},
        ),
    ]
