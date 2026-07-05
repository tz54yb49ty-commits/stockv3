"""Environment probe execution application package dry-run.

This module prepares an operator-facing application package for a future
environment probe. It does not read environment variables, inspect the
filesystem, read local TDX files, connect PostgreSQL, execute SQL, call
external APIs, write files, start workers, or authorize real execution.
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
    REQUIRED_PROBE_CATEGORIES,
    REQUIRED_PROBE_ITEM_IDS,
    EnvironmentProbeItem,
    build_environment_probe_plan_report,
)
from ashare_v3.ingestion.environment_probe_review import (
    EnvironmentProbeReviewReport,
    build_environment_probe_review_report,
)
from ashare_v3.ingestion.ingestion_acceptance import quality_gate_to_dict
from ashare_v3.ingestion.parquet_archive import DEFAULT_DATA_ROOT
from ashare_v3.ingestion.real_execution_config import DEFAULT_REAL_EXECUTION_CONFIG
from ashare_v3.ingestion.schema_readiness import DEFAULT_SCHEMA_PATH


REQUIRED_PROBE_OPERATOR_APPROVALS = (
    "probe.security_env_metadata",
    "probe.database_readonly",
    "probe.archive_filesystem_metadata",
    "probe.tdx_local_file_metadata",
    "probe.source_connectivity",
    "probe.runtime_import_checks",
    "probe.safety_boundary",
    "probe.no_writes_or_workers",
)


@dataclass(frozen=True)
class EnvironmentProbeExecutionRequest:
    item_id: str
    category: str
    target_kind: str
    target: str
    planned_probe: str
    required_permission: str
    redaction_policy: str
    evidence_policy: str
    expected_result_status_values: tuple[str, ...]
    approval_status: str = "pending_user_confirmation"
    will_run: bool = False

    @property
    def approved(self) -> bool:
        return self.approval_status == "confirmed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "category": self.category,
            "target_kind": self.target_kind,
            "target": self.target,
            "planned_probe": self.planned_probe,
            "required_permission": self.required_permission,
            "redaction_policy": self.redaction_policy,
            "evidence_policy": self.evidence_policy,
            "expected_result_status_values": list(self.expected_result_status_values),
            "approval_status": self.approval_status,
            "approved": self.approved,
            "will_run": self.will_run,
        }


@dataclass(frozen=True)
class ProbeOperatorApprovalItem:
    item_id: str
    category: str
    required_confirmation: str
    evidence: Mapping[str, Any]
    status: str = "pending_user_confirmation"

    @property
    def confirmed(self) -> bool:
        return self.status == "confirmed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "category": self.category,
            "required_confirmation": self.required_confirmation,
            "status": self.status,
            "confirmed": self.confirmed,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class EnvironmentProbeApplicationPackage:
    package_id: str
    probe_plan_id: str
    review_id: str
    result_report_id: str
    data_root: str
    tdx_root: str
    required_env_vars: tuple[str, ...]
    probe_requests: tuple[EnvironmentProbeExecutionRequest, ...]
    operator_approval_items: tuple[ProbeOperatorApprovalItem, ...]
    inherited_blocking_finding_ids: tuple[str, ...]
    inherited_blocking_result_item_ids: tuple[str, ...]
    input_review_passed: bool
    input_review_ready_for_execution_review: bool
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
    def ready_to_probe(self) -> bool:
        return False

    @property
    def pending_probe_request_ids(self) -> tuple[str, ...]:
        return tuple(request.item_id for request in self.probe_requests if not request.approved)

    @property
    def pending_approval_item_ids(self) -> tuple[str, ...]:
        return tuple(item.item_id for item in self.operator_approval_items if not item.confirmed)

    @property
    def probe_request_item_ids(self) -> tuple[str, ...]:
        return tuple(request.item_id for request in self.probe_requests)

    @property
    def category_counts(self) -> dict[str, int]:
        return dict(Counter(request.category for request in self.probe_requests))

    @property
    def required_permission_counts(self) -> dict[str, int]:
        return dict(Counter(request.required_permission for request in self.probe_requests))

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "probe_plan_id": self.probe_plan_id,
            "review_id": self.review_id,
            "result_report_id": self.result_report_id,
            "data_root": self.data_root,
            "tdx_root": self.tdx_root,
            "required_env_vars": list(self.required_env_vars),
            "passed": self.passed,
            "ready_to_probe": self.ready_to_probe,
            "input_review_passed": self.input_review_passed,
            "input_review_ready_for_execution_review": self.input_review_ready_for_execution_review,
            "probe_request_count": len(self.probe_requests),
            "category_counts": self.category_counts,
            "required_permission_counts": self.required_permission_counts,
            "pending_probe_request_ids": list(self.pending_probe_request_ids),
            "pending_approval_item_ids": list(self.pending_approval_item_ids),
            "inherited_blocking_finding_ids": list(self.inherited_blocking_finding_ids),
            "inherited_blocking_result_item_ids": list(self.inherited_blocking_result_item_ids),
            "probe_requests": [request.to_dict() for request in self.probe_requests],
            "operator_approval_items": [item.to_dict() for item in self.operator_approval_items],
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


def build_environment_probe_application_package(
    *,
    initial_config_path: str | Path = DEFAULT_INITIAL_BACKFILL_CONFIG,
    daily_config_path: str | Path = DEFAULT_DAILY_INCREMENTAL_CONFIG,
    real_config_path: str | Path = DEFAULT_REAL_EXECUTION_CONFIG,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
    data_root: str | None = None,
) -> EnvironmentProbeApplicationPackage:
    plan = build_environment_probe_plan_report(
        initial_config_path=initial_config_path,
        daily_config_path=daily_config_path,
        real_config_path=real_config_path,
        schema_path=schema_path,
        data_root=data_root or DEFAULT_DATA_ROOT,
    )
    review = build_environment_probe_review_report(
        initial_config_path=initial_config_path,
        daily_config_path=daily_config_path,
        real_config_path=real_config_path,
        schema_path=schema_path,
        data_root=data_root or DEFAULT_DATA_ROOT,
    )
    probe_requests = tuple(build_probe_execution_request(item) for item in plan.probe_items)
    package = EnvironmentProbeApplicationPackage(
        package_id="environment_probe_application_n3_9",
        probe_plan_id=plan.plan_id,
        review_id=review.review_id,
        result_report_id=review.result_report_id,
        data_root=plan.data_root,
        tdx_root=plan.tdx_root,
        required_env_vars=plan.required_env_vars,
        probe_requests=probe_requests,
        operator_approval_items=tuple(build_probe_operator_approval_items()),
        inherited_blocking_finding_ids=review.blocking_finding_ids,
        inherited_blocking_result_item_ids=review.blocking_result_item_ids,
        input_review_passed=review.passed,
        input_review_ready_for_execution_review=review.ready_for_execution_review,
        quality_gates=(),
    )
    return EnvironmentProbeApplicationPackage(
        package_id=package.package_id,
        probe_plan_id=package.probe_plan_id,
        review_id=package.review_id,
        result_report_id=package.result_report_id,
        data_root=package.data_root,
        tdx_root=package.tdx_root,
        required_env_vars=package.required_env_vars,
        probe_requests=package.probe_requests,
        operator_approval_items=package.operator_approval_items,
        inherited_blocking_finding_ids=package.inherited_blocking_finding_ids,
        inherited_blocking_result_item_ids=package.inherited_blocking_result_item_ids,
        input_review_passed=package.input_review_passed,
        input_review_ready_for_execution_review=package.input_review_ready_for_execution_review,
        quality_gates=tuple(build_probe_application_quality_gates(package)),
    )


def build_probe_execution_request(item: EnvironmentProbeItem) -> EnvironmentProbeExecutionRequest:
    return EnvironmentProbeExecutionRequest(
        item_id=item.item_id,
        category=item.category,
        target_kind=item.target_kind,
        target=item.target,
        planned_probe=item.planned_probe,
        required_permission=item.required_permission,
        redaction_policy=redaction_policy_for_target(item),
        evidence_policy=evidence_policy_for_category(item.category),
        expected_result_status_values=("passed", "failed", "skipped"),
    )


def redaction_policy_for_target(item: EnvironmentProbeItem) -> str:
    if item.target_kind == "environment_variable_name":
        return "env_var_name_only_secret_value_never_logged"
    if item.target_kind == "postgres_dsn_env_name":
        return "dsn_env_name_only_dsn_value_never_logged"
    if item.category == "source":
        return "connectivity_status_only_no_market_payload"
    if item.category == "tdx":
        return "path_status_only_no_file_content"
    if item.category == "archive":
        return "path_status_only_no_directory_listing"
    if item.category == "runtime":
        return "module_name_and_import_status_only"
    if item.category == "safety":
        return "project_rule_status_only"
    return "metadata_only"


def evidence_policy_for_category(category: str) -> str:
    policies = {
        "security": "boolean_presence_only",
        "database": "connectivity_or_catalog_status_without_dsn",
        "archive": "path_capability_status_without_file_creation",
        "tdx": "readability_status_without_content_capture",
        "source": "connectivity_status_without_response_payload",
        "runtime": "import_status_without_package_dump",
        "safety": "boundary_status_from_v3_rules_only",
    }
    return policies.get(category, "metadata_status_only")


def build_probe_operator_approval_items() -> list[ProbeOperatorApprovalItem]:
    return [
        ProbeOperatorApprovalItem(
            item_id="probe.security_env_metadata",
            category="security",
            required_confirmation="Allow future probe to check whether required environment variable names are bound without logging values.",
            evidence={"required_env_vars": ["TUSHARE_TOKEN", "ASHARE_V3_POSTGRES_DSN"]},
        ),
        ProbeOperatorApprovalItem(
            item_id="probe.database_readonly",
            category="database",
            required_confirmation="Allow future short PostgreSQL connectivity and catalog probes without writes.",
            evidence={"writes_allowed": False, "sql_execution_allowed": False},
        ),
        ProbeOperatorApprovalItem(
            item_id="probe.archive_filesystem_metadata",
            category="archive",
            required_confirmation="Allow future filesystem metadata checks under /Volumes/MacRaid/database without creating files.",
            evidence={"data_root": "/Volumes/MacRaid/database", "writes_allowed": False},
        ),
        ProbeOperatorApprovalItem(
            item_id="probe.tdx_local_file_metadata",
            category="tdx",
            required_confirmation="Allow future readability checks for local TDX txt files without capturing file contents.",
            evidence={"tdx_root": "/Volumes/MacRaid/tdxdata/tdx", "content_capture_allowed": False},
        ),
        ProbeOperatorApprovalItem(
            item_id="probe.source_connectivity",
            category="source",
            required_confirmation="Allow future Tushare and Mootdx connectivity checks without storing market payloads.",
            evidence={"payload_capture_allowed": False},
        ),
        ProbeOperatorApprovalItem(
            item_id="probe.runtime_import_checks",
            category="runtime",
            required_confirmation="Allow future Python dependency import checks for ingestion runtime packages.",
            evidence={"package_dump_allowed": False},
        ),
        ProbeOperatorApprovalItem(
            item_id="probe.safety_boundary",
            category="safety",
            required_confirmation="Confirm future probe still excludes old system access, workers, services, and non-ingestion layers.",
            evidence={"old_system_access_allowed": False, "worker_start_allowed": False},
        ),
        ProbeOperatorApprovalItem(
            item_id="probe.no_writes_or_workers",
            category="safety",
            required_confirmation="Confirm future probe remains read-only and does not authorize real ingestion execution.",
            evidence={"data_writes_allowed": False, "real_execution_authorized": False},
        ),
    ]


def build_probe_application_quality_gates(package: EnvironmentProbeApplicationPackage) -> list[QualityGateResult]:
    request_ids = set(package.probe_request_item_ids)
    missing_requests = sorted(set(REQUIRED_PROBE_ITEM_IDS) - request_ids)
    extra_requests = sorted(request_ids - set(REQUIRED_PROBE_ITEM_IDS))
    missing_categories = sorted(set(REQUIRED_PROBE_CATEGORIES) - set(package.category_counts))
    unpending_requests = [
        request.item_id
        for request in package.probe_requests
        if request.approval_status != "pending_user_confirmation" or request.will_run
    ]
    approval_ids = {item.item_id for item in package.operator_approval_items}
    missing_approvals = sorted(set(REQUIRED_PROBE_OPERATOR_APPROVALS) - approval_ids)
    extra_approvals = sorted(approval_ids - set(REQUIRED_PROBE_OPERATOR_APPROVALS))
    confirmed_approvals = [item.item_id for item in package.operator_approval_items if item.confirmed]
    missing_redaction = [
        request.item_id
        for request in package.probe_requests
        if not request.redaction_policy or not request.evidence_policy
    ]
    side_effect_flags = {
        "will_read_environment": package.will_read_environment,
        "will_check_filesystem": package.will_check_filesystem,
        "will_call_external_sources": package.will_call_external_sources,
        "will_read_tdx_files": package.will_read_tdx_files,
        "will_connect_database": package.will_connect_database,
        "will_execute_sql": package.will_execute_sql,
        "will_create_directories": package.will_create_directories,
        "will_write_data_files": package.will_write_data_files,
        "will_start_worker": package.will_start_worker,
        "will_authorize_real_execution": package.will_authorize_real_execution,
    }
    enabled_side_effects = sorted(name for name, enabled in side_effect_flags.items() if enabled)

    return [
        QualityGateResult(
            gate_name="probe_application_review_passed_but_not_ready",
            status="passed" if package.input_review_passed and not package.input_review_ready_for_execution_review else "failed",
            expected_value="N3.8 review passed but is not ready for execution review",
            actual_value=f"{package.input_review_passed}/{package.input_review_ready_for_execution_review}",
        ),
        QualityGateResult(
            gate_name="probe_application_requests_cover_required_items",
            status="passed" if not missing_requests and not extra_requests else "failed",
            expected_value=str(len(REQUIRED_PROBE_ITEM_IDS)),
            actual_value=str(len(package.probe_requests)),
            details={"missing_requests": missing_requests, "extra_requests": extra_requests},
        ),
        QualityGateResult(
            gate_name="probe_application_categories_cover_required",
            status="passed" if not missing_categories else "failed",
            expected_value="/".join(REQUIRED_PROBE_CATEGORIES),
            actual_value="/".join(sorted(package.category_counts)),
            details={"missing_categories": missing_categories},
        ),
        QualityGateResult(
            gate_name="probe_application_requests_pending_and_disabled",
            status="passed" if not unpending_requests else "failed",
            expected_value="all probe requests pending and will_run=false",
            actual_value=str(len(unpending_requests)),
            details={"unpending_requests": unpending_requests},
        ),
        QualityGateResult(
            gate_name="probe_application_operator_approvals_pending",
            status="passed" if not missing_approvals and not extra_approvals and not confirmed_approvals else "failed",
            expected_value=str(len(REQUIRED_PROBE_OPERATOR_APPROVALS)),
            actual_value=str(len(package.operator_approval_items)),
            details={
                "missing_approvals": missing_approvals,
                "extra_approvals": extra_approvals,
                "confirmed_approvals": confirmed_approvals,
            },
        ),
        QualityGateResult(
            gate_name="probe_application_inherits_review_blockers",
            status="passed" if "probe_plan_not_ready" in package.inherited_blocking_finding_ids else "failed",
            expected_value="N3.8 blocking findings are carried forward",
            actual_value=str(len(package.inherited_blocking_finding_ids)),
            details={"inherited_blocking_finding_ids": list(package.inherited_blocking_finding_ids)},
        ),
        QualityGateResult(
            gate_name="probe_application_redaction_policy_present",
            status="passed" if not missing_redaction else "failed",
            expected_value="all probe requests define redaction and evidence policies",
            actual_value=str(len(missing_redaction)),
            details={"missing_redaction": missing_redaction},
        ),
        QualityGateResult(
            gate_name="probe_application_not_ready_to_probe",
            status="passed" if not package.ready_to_probe else "failed",
            expected_value="application package does not authorize probe execution",
            actual_value=str(package.ready_to_probe).lower(),
        ),
        QualityGateResult(
            gate_name="probe_application_no_side_effects",
            status="passed" if not enabled_side_effects else "failed",
            expected_value="no env read, no filesystem check, no source calls, no TDX reads, no DB, no SQL, no writes, no worker",
            actual_value=str(len(enabled_side_effects)),
            details={"enabled_side_effects": enabled_side_effects},
        ),
    ]
