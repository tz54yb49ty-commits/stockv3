"""Environment probe result review dry-run.

This module reviews the N3.7 probe result template in memory. It does not read
environment variables, inspect the filesystem, read local TDX files, connect
PostgreSQL, execute SQL, call external APIs, write files, start workers, or
authorize real execution.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ashare_v3.ingestion.backfill_config import DEFAULT_INITIAL_BACKFILL_CONFIG
from ashare_v3.ingestion.common import QualityGateResult
from ashare_v3.ingestion.daily_incremental_config import DEFAULT_DAILY_INCREMENTAL_CONFIG
from ashare_v3.ingestion.environment_probe_plan import REQUIRED_PROBE_ITEM_IDS
from ashare_v3.ingestion.environment_probe_result import (
    RESULT_STATUS_VALUES,
    EnvironmentProbeResultRecord,
    EnvironmentProbeResultTemplate,
    build_environment_probe_result_template,
)
from ashare_v3.ingestion.ingestion_acceptance import quality_gate_to_dict
from ashare_v3.ingestion.parquet_archive import DEFAULT_DATA_ROOT
from ashare_v3.ingestion.real_execution_config import DEFAULT_REAL_EXECUTION_CONFIG
from ashare_v3.ingestion.schema_readiness import DEFAULT_SCHEMA_PATH


REVIEW_REASON_VALUES = (
    "probe_plan_failed",
    "probe_plan_not_ready",
    "invalid_probe_status",
    "probe_status_failed",
    "probe_status_skipped",
    "probe_not_executed",
    "missing_error_summary",
)


@dataclass(frozen=True)
class EnvironmentProbeReviewFinding:
    finding_id: str
    item_id: str
    category: str
    reason: str
    result_status: str
    probe_executed: bool
    severity: str
    blocking: bool
    error_summary: str | None
    evidence: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "item_id": self.item_id,
            "category": self.category,
            "reason": self.reason,
            "result_status": self.result_status,
            "probe_executed": self.probe_executed,
            "severity": self.severity,
            "blocking": self.blocking,
            "error_summary": self.error_summary,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class EnvironmentProbeReviewReport:
    review_id: str
    result_report_id: str
    probe_plan_id: str
    data_root: str
    tdx_root: str
    input_result_report_passed: bool
    input_probe_plan_passed: bool
    input_probe_plan_ready_to_probe: bool
    result_records: tuple[EnvironmentProbeResultRecord, ...]
    findings: tuple[EnvironmentProbeReviewFinding, ...]
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
    def result_status_counts(self) -> dict[str, int]:
        return dict(Counter(record.result_status for record in self.result_records))

    @property
    def blocking_finding_ids(self) -> tuple[str, ...]:
        return tuple(finding.finding_id for finding in self.findings if finding.blocking)

    @property
    def blocking_result_item_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(finding.item_id for finding in self.findings if finding.blocking))

    @property
    def ready_for_execution_review(self) -> bool:
        return (
            self.input_result_report_passed
            and self.input_probe_plan_passed
            and self.input_probe_plan_ready_to_probe
            and not self.blocking_finding_ids
            and self.result_status_counts == {"passed": len(REQUIRED_PROBE_ITEM_IDS)}
            and all(record.probe_executed for record in self.result_records)
            and not self.will_authorize_real_execution
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "result_report_id": self.result_report_id,
            "probe_plan_id": self.probe_plan_id,
            "data_root": self.data_root,
            "tdx_root": self.tdx_root,
            "input_result_report_passed": self.input_result_report_passed,
            "input_probe_plan_passed": self.input_probe_plan_passed,
            "input_probe_plan_ready_to_probe": self.input_probe_plan_ready_to_probe,
            "passed": self.passed,
            "ready_for_execution_review": self.ready_for_execution_review,
            "result_status_values": list(RESULT_STATUS_VALUES),
            "review_reason_values": list(REVIEW_REASON_VALUES),
            "result_status_counts": self.result_status_counts,
            "blocking_finding_ids": list(self.blocking_finding_ids),
            "blocking_result_item_ids": list(self.blocking_result_item_ids),
            "findings": [finding.to_dict() for finding in self.findings],
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


def build_environment_probe_review_report(
    *,
    initial_config_path: str | Path = DEFAULT_INITIAL_BACKFILL_CONFIG,
    daily_config_path: str | Path = DEFAULT_DAILY_INCREMENTAL_CONFIG,
    real_config_path: str | Path = DEFAULT_REAL_EXECUTION_CONFIG,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
    data_root: str | None = None,
) -> EnvironmentProbeReviewReport:
    result_template = build_environment_probe_result_template(
        initial_config_path=initial_config_path,
        daily_config_path=daily_config_path,
        real_config_path=real_config_path,
        schema_path=schema_path,
        data_root=data_root or DEFAULT_DATA_ROOT,
    )
    return review_environment_probe_result_template(result_template)


def review_environment_probe_result_template(
    result_template: EnvironmentProbeResultTemplate,
) -> EnvironmentProbeReviewReport:
    findings = tuple(build_review_findings(result_template))
    report = EnvironmentProbeReviewReport(
        review_id="environment_probe_review_n3_8",
        result_report_id=result_template.report_id,
        probe_plan_id=result_template.probe_plan_id,
        data_root=result_template.data_root,
        tdx_root=result_template.tdx_root,
        input_result_report_passed=result_template.passed,
        input_probe_plan_passed=result_template.probe_plan_passed,
        input_probe_plan_ready_to_probe=result_template.probe_plan_ready_to_probe,
        result_records=result_template.result_records,
        findings=findings,
        quality_gates=(),
    )
    return EnvironmentProbeReviewReport(
        review_id=report.review_id,
        result_report_id=report.result_report_id,
        probe_plan_id=report.probe_plan_id,
        data_root=report.data_root,
        tdx_root=report.tdx_root,
        input_result_report_passed=report.input_result_report_passed,
        input_probe_plan_passed=report.input_probe_plan_passed,
        input_probe_plan_ready_to_probe=report.input_probe_plan_ready_to_probe,
        result_records=report.result_records,
        findings=report.findings,
        quality_gates=tuple(build_review_quality_gates(report)),
    )


def build_review_findings(result_template: EnvironmentProbeResultTemplate) -> list[EnvironmentProbeReviewFinding]:
    findings: list[EnvironmentProbeReviewFinding] = []
    if not result_template.probe_plan_passed:
        findings.append(
            build_report_finding(
                finding_id="probe_plan_failed",
                reason="probe_plan_failed",
                result_status="failed",
                error_summary="probe_plan_quality_gates_failed",
            )
        )
    if not result_template.probe_plan_ready_to_probe:
        findings.append(
            build_report_finding(
                finding_id="probe_plan_not_ready",
                reason="probe_plan_not_ready",
                result_status="skipped",
                error_summary="probe_plan_not_ready_to_probe",
            )
        )
    for record in result_template.result_records:
        findings.extend(build_record_findings(record))
    return findings


def build_report_finding(
    *,
    finding_id: str,
    reason: str,
    result_status: str,
    error_summary: str,
) -> EnvironmentProbeReviewFinding:
    return EnvironmentProbeReviewFinding(
        finding_id=finding_id,
        item_id="__probe_plan__",
        category="review",
        reason=reason,
        result_status=result_status,
        probe_executed=False,
        severity="P0",
        blocking=True,
        error_summary=error_summary,
        evidence={"review_level": "probe_plan"},
    )


def build_record_findings(record: EnvironmentProbeResultRecord) -> list[EnvironmentProbeReviewFinding]:
    findings: list[EnvironmentProbeReviewFinding] = []
    if record.result_status not in RESULT_STATUS_VALUES:
        findings.append(build_record_finding(record, "invalid_probe_status", blocking=True))
        return findings
    if record.result_status == "skipped":
        findings.append(build_record_finding(record, "probe_status_skipped", blocking=True))
    elif record.result_status == "failed":
        findings.append(build_record_finding(record, "probe_status_failed", blocking=True))
    elif not record.probe_executed:
        findings.append(build_record_finding(record, "probe_not_executed", blocking=True))
    if record.result_status in {"failed", "skipped"} and not record.error_summary:
        findings.append(build_record_finding(record, "missing_error_summary", blocking=True))
    return findings


def build_record_finding(
    record: EnvironmentProbeResultRecord,
    reason: str,
    *,
    blocking: bool,
) -> EnvironmentProbeReviewFinding:
    return EnvironmentProbeReviewFinding(
        finding_id=f"{reason}:{record.item_id}",
        item_id=record.item_id,
        category=record.category,
        reason=reason,
        result_status=record.result_status,
        probe_executed=record.probe_executed,
        severity=record.severity,
        blocking=blocking,
        error_summary=record.error_summary,
        evidence={
            "target_kind": record.target_kind,
            "target": record.target,
            "planned_probe": record.planned_probe,
            "record_blocking": record.blocking,
        },
    )


def build_review_quality_gates(report: EnvironmentProbeReviewReport) -> list[QualityGateResult]:
    result_item_ids = {record.item_id for record in report.result_records}
    missing_items = sorted(set(REQUIRED_PROBE_ITEM_IDS) - result_item_ids)
    extra_items = sorted(result_item_ids - set(REQUIRED_PROBE_ITEM_IDS))
    invalid_status_items = [
        record.item_id
        for record in report.result_records
        if record.result_status not in RESULT_STATUS_VALUES
    ]
    missing_error_summary_items = [
        record.item_id
        for record in report.result_records
        if record.result_status in {"failed", "skipped"} and not record.error_summary
    ]
    bad_unblocked_items = [
        record.item_id
        for record in report.result_records
        if (record.result_status != "passed" or not record.probe_executed)
        and record.item_id not in report.blocking_result_item_ids
    ]
    side_effect_flags = {
        "will_read_environment": report.will_read_environment,
        "will_check_filesystem": report.will_check_filesystem,
        "will_call_external_sources": report.will_call_external_sources,
        "will_read_tdx_files": report.will_read_tdx_files,
        "will_connect_database": report.will_connect_database,
        "will_execute_sql": report.will_execute_sql,
        "will_create_directories": report.will_create_directories,
        "will_write_data_files": report.will_write_data_files,
        "will_start_worker": report.will_start_worker,
        "will_authorize_real_execution": report.will_authorize_real_execution,
    }
    enabled_side_effects = sorted(name for name, enabled in side_effect_flags.items() if enabled)

    return [
        QualityGateResult(
            gate_name="probe_review_input_result_template_passed",
            status="passed" if report.input_result_report_passed else "failed",
            expected_value="N3.7 result template quality gates passed",
            actual_value=str(report.input_result_report_passed).lower(),
        ),
        QualityGateResult(
            gate_name="probe_review_required_items_present",
            status="passed" if not missing_items and not extra_items else "failed",
            expected_value=str(len(REQUIRED_PROBE_ITEM_IDS)),
            actual_value=str(len(report.result_records)),
            details={"missing_items": missing_items, "extra_items": extra_items},
        ),
        QualityGateResult(
            gate_name="probe_review_status_domain_valid",
            status="passed" if not invalid_status_items else "failed",
            expected_value="/".join(RESULT_STATUS_VALUES),
            actual_value=str(len(invalid_status_items)),
            details={"invalid_status_items": invalid_status_items},
        ),
        QualityGateResult(
            gate_name="probe_review_failed_skipped_have_error_summary",
            status="passed" if not missing_error_summary_items else "failed",
            expected_value="failed/skipped results include error_summary",
            actual_value=str(len(missing_error_summary_items)),
            details={"missing_error_summary_items": missing_error_summary_items},
        ),
        QualityGateResult(
            gate_name="probe_review_unready_results_are_blocking",
            status="passed" if not bad_unblocked_items else "failed",
            expected_value="skipped/failed/unexecuted results produce blocking findings",
            actual_value=str(len(bad_unblocked_items)),
            details={"bad_unblocked_items": bad_unblocked_items},
        ),
        QualityGateResult(
            gate_name="probe_review_default_template_not_ready",
            status="passed" if not report.ready_for_execution_review else "failed",
            expected_value="N3.8 default review is not ready for execution review",
            actual_value=str(report.ready_for_execution_review).lower(),
            details={"blocking_finding_ids": list(report.blocking_finding_ids)},
        ),
        QualityGateResult(
            gate_name="probe_review_no_real_authorization",
            status="passed" if not report.will_authorize_real_execution else "failed",
            expected_value="review report does not authorize real execution",
            actual_value=str(report.will_authorize_real_execution).lower(),
        ),
        QualityGateResult(
            gate_name="probe_review_no_side_effects",
            status="passed" if not enabled_side_effects else "failed",
            expected_value="no env read, no filesystem check, no source calls, no TDX reads, no DB, no SQL, no writes, no worker",
            actual_value=str(len(enabled_side_effects)),
            details={"enabled_side_effects": enabled_side_effects},
        ),
    ]
