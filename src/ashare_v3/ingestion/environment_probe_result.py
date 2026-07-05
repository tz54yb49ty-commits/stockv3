"""Environment probe result report template dry-run.

This module defines the report shape for future environment probe results. It
does not execute probes, read environment variables, inspect the filesystem,
read local TDX files, connect PostgreSQL, execute SQL, call external APIs, write
files, start workers, or authorize real execution.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ashare_v3.ingestion.backfill_config import DEFAULT_INITIAL_BACKFILL_CONFIG
from ashare_v3.ingestion.common import QualityGateResult
from ashare_v3.ingestion.daily_incremental_config import DEFAULT_DAILY_INCREMENTAL_CONFIG
from ashare_v3.ingestion.environment_probe_plan import (
    REQUIRED_PROBE_ITEM_IDS,
    EnvironmentProbeItem,
    EnvironmentProbePlanReport,
    build_environment_probe_plan_report,
)
from ashare_v3.ingestion.ingestion_acceptance import quality_gate_to_dict
from ashare_v3.ingestion.parquet_archive import DEFAULT_DATA_ROOT
from ashare_v3.ingestion.real_execution_config import DEFAULT_REAL_EXECUTION_CONFIG
from ashare_v3.ingestion.schema_readiness import DEFAULT_SCHEMA_PATH


RESULT_STATUS_VALUES = ("passed", "failed", "skipped")
DEFAULT_SKIPPED_ERROR_SUMMARY = "probe_not_executed_in_n3_7_dry_run"


@dataclass(frozen=True)
class EnvironmentProbeResultRecord:
    item_id: str
    category: str
    target_kind: str
    target: str
    planned_probe: str
    result_status: str
    severity: str
    blocking: bool
    probe_executed: bool
    error_summary: str | None
    evidence: Mapping[str, Any]

    @property
    def passed(self) -> bool:
        return self.result_status == "passed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "category": self.category,
            "target_kind": self.target_kind,
            "target": self.target,
            "planned_probe": self.planned_probe,
            "result_status": self.result_status,
            "severity": self.severity,
            "blocking": self.blocking,
            "probe_executed": self.probe_executed,
            "error_summary": self.error_summary,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class EnvironmentProbeResultTemplate:
    report_id: str
    probe_plan_id: str
    data_root: str
    tdx_root: str
    required_env_vars: tuple[str, ...]
    probe_plan_passed: bool
    probe_plan_ready_to_probe: bool
    execution_blockers: tuple[str, ...]
    result_records: tuple[EnvironmentProbeResultRecord, ...]
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
    def ready_for_execution_review(self) -> bool:
        return False

    @property
    def result_status_counts(self) -> dict[str, int]:
        return dict(Counter(record.result_status for record in self.result_records))

    @property
    def result_item_ids(self) -> tuple[str, ...]:
        return tuple(record.item_id for record in self.result_records)

    @property
    def blocking_result_item_ids(self) -> tuple[str, ...]:
        return tuple(record.item_id for record in self.result_records if record.blocking)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "probe_plan_id": self.probe_plan_id,
            "data_root": self.data_root,
            "tdx_root": self.tdx_root,
            "required_env_vars": list(self.required_env_vars),
            "probe_plan_passed": self.probe_plan_passed,
            "probe_plan_ready_to_probe": self.probe_plan_ready_to_probe,
            "passed": self.passed,
            "ready_for_execution_review": self.ready_for_execution_review,
            "execution_blockers": list(self.execution_blockers),
            "result_status_values": list(RESULT_STATUS_VALUES),
            "result_status_counts": self.result_status_counts,
            "blocking_result_item_ids": list(self.blocking_result_item_ids),
            "result_records": [record.to_dict() for record in self.result_records],
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


def build_environment_probe_result_template(
    *,
    initial_config_path: str | Path = DEFAULT_INITIAL_BACKFILL_CONFIG,
    daily_config_path: str | Path = DEFAULT_DAILY_INCREMENTAL_CONFIG,
    real_config_path: str | Path = DEFAULT_REAL_EXECUTION_CONFIG,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
    data_root: str | None = None,
) -> EnvironmentProbeResultTemplate:
    probe_plan = build_environment_probe_plan_report(
        initial_config_path=initial_config_path,
        daily_config_path=daily_config_path,
        real_config_path=real_config_path,
        schema_path=schema_path,
        data_root=data_root or DEFAULT_DATA_ROOT,
    )
    result_records = tuple(build_skipped_result_record(item) for item in probe_plan.probe_items)
    template = EnvironmentProbeResultTemplate(
        report_id="environment_probe_result_template_n3_7",
        probe_plan_id=probe_plan.plan_id,
        data_root=probe_plan.data_root,
        tdx_root=probe_plan.tdx_root,
        required_env_vars=probe_plan.required_env_vars,
        probe_plan_passed=probe_plan.passed,
        probe_plan_ready_to_probe=probe_plan.ready_to_probe,
        execution_blockers=probe_plan.execution_blockers,
        result_records=result_records,
        quality_gates=(),
    )
    return EnvironmentProbeResultTemplate(
        report_id=template.report_id,
        probe_plan_id=template.probe_plan_id,
        data_root=template.data_root,
        tdx_root=template.tdx_root,
        required_env_vars=template.required_env_vars,
        probe_plan_passed=template.probe_plan_passed,
        probe_plan_ready_to_probe=template.probe_plan_ready_to_probe,
        execution_blockers=template.execution_blockers,
        result_records=template.result_records,
        quality_gates=tuple(build_result_template_quality_gates(template)),
    )


def build_skipped_result_record(item: EnvironmentProbeItem) -> EnvironmentProbeResultRecord:
    return EnvironmentProbeResultRecord(
        item_id=item.item_id,
        category=item.category,
        target_kind=item.target_kind,
        target=item.target,
        planned_probe=item.planned_probe,
        result_status="skipped",
        severity=severity_for_probe_category(item.category),
        blocking=True,
        probe_executed=False,
        error_summary=DEFAULT_SKIPPED_ERROR_SUMMARY,
        evidence={
            "source_probe_item_status": item.actual_status,
            "source_probe_item_approval_status": item.approval_status,
            "result_template_only": True,
        },
    )


def severity_for_probe_category(category: str) -> str:
    if category == "runtime":
        return "P1"
    return "P0"


def build_result_template_quality_gates(template: EnvironmentProbeResultTemplate) -> list[QualityGateResult]:
    item_ids = set(template.result_item_ids)
    missing_items = sorted(set(REQUIRED_PROBE_ITEM_IDS) - item_ids)
    extra_items = sorted(item_ids - set(REQUIRED_PROBE_ITEM_IDS))
    invalid_status_items = [
        record.item_id
        for record in template.result_records
        if record.result_status not in RESULT_STATUS_VALUES
    ]
    executed_items = [record.item_id for record in template.result_records if record.probe_executed]
    non_skipped_items = [
        record.item_id
        for record in template.result_records
        if record.result_status != "skipped"
    ]
    missing_error_summary_items = [
        record.item_id
        for record in template.result_records
        if record.result_status in {"failed", "skipped"} and not record.error_summary
    ]
    non_blocking_skipped_items = [
        record.item_id
        for record in template.result_records
        if record.result_status == "skipped" and not record.blocking
    ]
    side_effect_flags = {
        "will_read_environment": template.will_read_environment,
        "will_check_filesystem": template.will_check_filesystem,
        "will_call_external_sources": template.will_call_external_sources,
        "will_read_tdx_files": template.will_read_tdx_files,
        "will_connect_database": template.will_connect_database,
        "will_execute_sql": template.will_execute_sql,
        "will_create_directories": template.will_create_directories,
        "will_write_data_files": template.will_write_data_files,
        "will_start_worker": template.will_start_worker,
        "will_authorize_real_execution": template.will_authorize_real_execution,
    }
    enabled_side_effects = sorted(name for name, enabled in side_effect_flags.items() if enabled)

    return [
        QualityGateResult(
            gate_name="probe_result_plan_passed_but_not_ready",
            status="passed" if template.probe_plan_passed and not template.probe_plan_ready_to_probe else "failed",
            expected_value="probe plan passed but is not ready_to_probe",
            actual_value=f"{template.probe_plan_passed}/{template.probe_plan_ready_to_probe}",
            details={"execution_blockers": list(template.execution_blockers)},
        ),
        QualityGateResult(
            gate_name="probe_result_records_cover_plan_items",
            status="passed" if not missing_items and not extra_items else "failed",
            expected_value=str(len(REQUIRED_PROBE_ITEM_IDS)),
            actual_value=str(len(template.result_records)),
            details={"missing_items": missing_items, "extra_items": extra_items},
        ),
        QualityGateResult(
            gate_name="probe_result_status_domain_valid",
            status="passed" if not invalid_status_items else "failed",
            expected_value="/".join(RESULT_STATUS_VALUES),
            actual_value=str(len(invalid_status_items)),
            details={"invalid_status_items": invalid_status_items},
        ),
        QualityGateResult(
            gate_name="probe_result_template_all_skipped",
            status="passed" if not executed_items and not non_skipped_items else "failed",
            expected_value="all records skipped and not executed in N3.7",
            actual_value=f"executed={len(executed_items)};non_skipped={len(non_skipped_items)}",
            details={"executed_items": executed_items, "non_skipped_items": non_skipped_items},
        ),
        QualityGateResult(
            gate_name="probe_result_blockers_explicit",
            status="passed" if not non_blocking_skipped_items else "failed",
            expected_value="skipped results block execution review",
            actual_value=str(len(non_blocking_skipped_items)),
            details={"non_blocking_skipped_items": non_blocking_skipped_items},
        ),
        QualityGateResult(
            gate_name="probe_result_error_summary_present",
            status="passed" if not missing_error_summary_items else "failed",
            expected_value="failed/skipped records include error_summary",
            actual_value=str(len(missing_error_summary_items)),
            details={"missing_error_summary_items": missing_error_summary_items},
        ),
        QualityGateResult(
            gate_name="probe_result_no_real_authorization",
            status="passed" if not template.ready_for_execution_review and not template.will_authorize_real_execution else "failed",
            expected_value="result template does not authorize execution review",
            actual_value=str(template.ready_for_execution_review).lower(),
            details={"blocking_result_item_ids": list(template.blocking_result_item_ids)},
        ),
        QualityGateResult(
            gate_name="probe_result_no_side_effects",
            status="passed" if not enabled_side_effects else "failed",
            expected_value="no env read, no filesystem check, no source calls, no TDX reads, no DB, no SQL, no writes, no worker",
            actual_value=str(len(enabled_side_effects)),
            details={"enabled_side_effects": enabled_side_effects},
        ),
    ]
