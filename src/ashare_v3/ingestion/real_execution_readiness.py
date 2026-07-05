"""Real-execution readiness summary dry-run.

This module composes the existing dry-run control report, preflight checklist,
real-execution config template, PostgreSQL schema readiness, and Parquet
readiness reports. It never calls external APIs, reads local TDX files, connects
PostgreSQL, executes SQL, writes Parquet, creates directories, or authorizes
real execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from ashare_v3.ingestion.backfill_config import DEFAULT_INITIAL_BACKFILL_CONFIG
from ashare_v3.ingestion.common import QualityGateResult
from ashare_v3.ingestion.daily_incremental_config import DEFAULT_DAILY_INCREMENTAL_CONFIG
from ashare_v3.ingestion.execution_preflight import build_execution_preflight_checklist
from ashare_v3.ingestion.ingestion_acceptance import quality_gate_to_dict
from ashare_v3.ingestion.ingestion_dry_run_control import build_ingestion_dry_run_control_report
from ashare_v3.ingestion.parquet_archive import DEFAULT_DATA_ROOT
from ashare_v3.ingestion.parquet_readiness import build_parquet_readiness_report
from ashare_v3.ingestion.real_execution_config import DEFAULT_REAL_EXECUTION_CONFIG, RealExecutionConfig, load_real_execution_config
from ashare_v3.ingestion.schema_readiness import DEFAULT_SCHEMA_PATH, build_schema_readiness_report


REQUIRED_READINESS_COMPONENTS = (
    "dry_run_control",
    "execution_preflight",
    "real_execution_config",
    "schema_readiness",
    "parquet_readiness",
)


@dataclass(frozen=True)
class ReadinessComponentStatus:
    component_id: str
    passed: bool
    ready_to_execute: bool | None
    summary: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "passed": self.passed,
            "ready_to_execute": self.ready_to_execute,
            "summary": dict(self.summary),
        }


@dataclass(frozen=True)
class RealExecutionReadinessReport:
    initial_config_path: str
    daily_config_path: str
    real_config_path: str
    schema_path: str
    data_root: str
    component_statuses: tuple[ReadinessComponentStatus, ...]
    execution_blockers: tuple[str, ...]
    pending_preflight_item_ids: tuple[str, ...]
    quality_gates: tuple[QualityGateResult, ...]
    will_call_external_sources: bool = False
    will_read_tdx_files: bool = False
    will_connect_database: bool = False
    will_execute_sql: bool = False
    will_create_directories: bool = False
    will_write_data_files: bool = False
    will_authorize_real_execution: bool = False

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.quality_gates)

    @property
    def ready_to_execute(self) -> bool:
        return self.passed and not self.execution_blockers and self.will_authorize_real_execution

    @property
    def component_ids(self) -> tuple[str, ...]:
        return tuple(component.component_id for component in self.component_statuses)

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_config_path": self.initial_config_path,
            "daily_config_path": self.daily_config_path,
            "real_config_path": self.real_config_path,
            "schema_path": self.schema_path,
            "data_root": self.data_root,
            "passed": self.passed,
            "ready_to_execute": self.ready_to_execute,
            "execution_blockers": list(self.execution_blockers),
            "pending_preflight_item_ids": list(self.pending_preflight_item_ids),
            "component_statuses": [status.to_dict() for status in self.component_statuses],
            "quality_gates": [quality_gate_to_dict(gate) for gate in self.quality_gates],
            "side_effects": {
                "will_call_external_sources": self.will_call_external_sources,
                "will_read_tdx_files": self.will_read_tdx_files,
                "will_connect_database": self.will_connect_database,
                "will_execute_sql": self.will_execute_sql,
                "will_create_directories": self.will_create_directories,
                "will_write_data_files": self.will_write_data_files,
                "will_authorize_real_execution": self.will_authorize_real_execution,
            },
        }


def build_real_execution_readiness_report(
    *,
    initial_config_path: str | Path = DEFAULT_INITIAL_BACKFILL_CONFIG,
    daily_config_path: str | Path = DEFAULT_DAILY_INCREMENTAL_CONFIG,
    real_config_path: str | Path = DEFAULT_REAL_EXECUTION_CONFIG,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
    data_root: str | None = None,
    confirmed_item_ids: Iterable[str] | None = None,
) -> RealExecutionReadinessReport:
    real_config = load_real_execution_config(real_config_path)
    parquet_data_root = data_root or real_config.data_root or DEFAULT_DATA_ROOT
    control_report = build_ingestion_dry_run_control_report(
        initial_config_path=initial_config_path,
        daily_config_path=daily_config_path,
    )
    preflight = build_execution_preflight_checklist(control_report, confirmed_item_ids=confirmed_item_ids)
    schema = build_schema_readiness_report(schema_path)
    parquet = build_parquet_readiness_report(data_root=parquet_data_root)
    component_statuses = (
        build_control_component(control_report),
        ReadinessComponentStatus(
            component_id="execution_preflight",
            passed=preflight.passed,
            ready_to_execute=preflight.ready_to_execute,
            summary={
                "confirmation_item_count": len(preflight.confirmation_items),
                "pending_item_count": len(preflight.pending_item_ids),
                "category_counts": preflight.category_counts,
            },
        ),
        build_config_component(real_config),
        ReadinessComponentStatus(
            component_id="schema_readiness",
            passed=schema.passed,
            ready_to_execute=None,
            summary={
                "schema_path": schema.schema_path,
                "table_count": schema.table_count,
                "required_table_count": schema.required_table_count,
            },
        ),
        ReadinessComponentStatus(
            component_id="parquet_readiness",
            passed=parquet.passed,
            ready_to_execute=None,
            summary={
                "data_root": parquet.data_root,
                "data_lake_dir": parquet.data_lake_dir,
                "dataset_count": parquet.dataset_count,
            },
        ),
    )
    execution_blockers = tuple(build_execution_blockers(real_config=real_config, preflight_ready=preflight.ready_to_execute))
    report = RealExecutionReadinessReport(
        initial_config_path=str(initial_config_path),
        daily_config_path=str(daily_config_path),
        real_config_path=str(real_config_path),
        schema_path=str(schema_path),
        data_root=parquet_data_root,
        component_statuses=component_statuses,
        execution_blockers=execution_blockers,
        pending_preflight_item_ids=preflight.pending_item_ids,
        quality_gates=(),
    )
    return RealExecutionReadinessReport(
        initial_config_path=report.initial_config_path,
        daily_config_path=report.daily_config_path,
        real_config_path=report.real_config_path,
        schema_path=report.schema_path,
        data_root=report.data_root,
        component_statuses=report.component_statuses,
        execution_blockers=report.execution_blockers,
        pending_preflight_item_ids=report.pending_preflight_item_ids,
        quality_gates=tuple(build_readiness_quality_gates(report)),
    )


def build_control_component(control_report: Any) -> ReadinessComponentStatus:
    return ReadinessComponentStatus(
        component_id="dry_run_control",
        passed=control_report.passed,
        ready_to_execute=None,
        summary={
            "initial_batch_count": control_report.initial_backfill.batch_count,
            "daily_task_count": control_report.daily_incremental.task_count,
            "initial_archive_dataset_count": control_report.initial_backfill.archive_dataset_count,
            "daily_archive_dataset_count": control_report.daily_incremental.archive_dataset_count,
            "initial_rollback_group_count": control_report.initial_backfill.rollback_group_count,
            "daily_rollback_group_count": control_report.daily_incremental.rollback_group_count,
        },
    )


def build_config_component(real_config: RealExecutionConfig) -> ReadinessComponentStatus:
    return ReadinessComponentStatus(
        component_id="real_execution_config",
        passed=True,
        ready_to_execute=real_config.ready_to_execute,
        summary={
            "mode": real_config.mode,
            "approved_stage": real_config.approved_stage,
            "allow_real_execution": real_config.allow_real_execution,
            "permission_count": len(real_config.permissions),
            "enabled_permission_count": sum(1 for enabled in real_config.permissions.values() if enabled),
            "required_confirmation_count": len(real_config.required_confirmation_items),
        },
    )


def build_execution_blockers(
    *,
    real_config: RealExecutionConfig,
    preflight_ready: bool,
) -> list[str]:
    blockers: list[str] = []
    if not preflight_ready:
        blockers.append("pending_user_confirmation")
    if not real_config.ready_to_execute:
        blockers.append("real_execution_config_disabled")
    return blockers


def build_readiness_quality_gates(report: RealExecutionReadinessReport) -> list[QualityGateResult]:
    component_ids = set(report.component_ids)
    missing_components = sorted(set(REQUIRED_READINESS_COMPONENTS) - component_ids)
    component_failures = [status.component_id for status in report.component_statuses if not status.passed]
    config_component = next(status for status in report.component_statuses if status.component_id == "real_execution_config")
    enabled_permission_count = int(config_component.summary["enabled_permission_count"])
    side_effect_flags = {
        "will_call_external_sources": report.will_call_external_sources,
        "will_read_tdx_files": report.will_read_tdx_files,
        "will_connect_database": report.will_connect_database,
        "will_execute_sql": report.will_execute_sql,
        "will_create_directories": report.will_create_directories,
        "will_write_data_files": report.will_write_data_files,
        "will_authorize_real_execution": report.will_authorize_real_execution,
    }
    enabled_side_effects = sorted(name for name, enabled in side_effect_flags.items() if enabled)

    return [
        QualityGateResult(
            gate_name="readiness_components_present",
            status="passed" if not missing_components else "failed",
            expected_value="/".join(REQUIRED_READINESS_COMPONENTS),
            actual_value=",".join(report.component_ids),
            details={"missing_components": missing_components},
        ),
        QualityGateResult(
            gate_name="readiness_components_passed",
            status="passed" if not component_failures else "failed",
            expected_value="all readiness components passed",
            actual_value=str(len(component_failures)),
            details={"component_failures": component_failures},
        ),
        QualityGateResult(
            gate_name="readiness_preflight_state_explicit",
            status="passed",
            expected_value="pending confirmations listed when not ready",
            actual_value=str(len(report.pending_preflight_item_ids)),
            details={"pending_preflight_item_ids": list(report.pending_preflight_item_ids)},
        ),
        QualityGateResult(
            gate_name="readiness_real_config_template_safe",
            status="passed" if enabled_permission_count == 0 and "real_execution_config_disabled" in report.execution_blockers else "failed",
            expected_value="all permissions disabled and no real execution in template",
            actual_value=str(enabled_permission_count),
            details={"execution_blockers": list(report.execution_blockers)},
        ),
        QualityGateResult(
            gate_name="readiness_real_execution_not_authorized",
            status="passed" if not report.ready_to_execute and not report.will_authorize_real_execution else "failed",
            expected_value="N3.4 does not authorize real execution",
            actual_value=str(report.ready_to_execute).lower(),
            details={"execution_blockers": list(report.execution_blockers)},
        ),
        QualityGateResult(
            gate_name="readiness_no_side_effects",
            status="passed" if not enabled_side_effects else "failed",
            expected_value="no source calls, no TDX reads, no DB, no SQL, no mkdir, no data file writes",
            actual_value=str(len(enabled_side_effects)),
            details={"enabled_side_effects": enabled_side_effects},
        ),
    ]
