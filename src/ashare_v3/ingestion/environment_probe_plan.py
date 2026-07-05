"""Environment probe plan dry-run.

This module builds the list of environment checks that should be reviewed before
any later real probe is allowed. It never reads environment variable values,
checks filesystem paths, reads local TDX files, connects PostgreSQL, calls
external APIs, writes files, creates directories, starts workers, or authorizes
real execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ashare_v3.ingestion.backfill_config import DEFAULT_INITIAL_BACKFILL_CONFIG
from ashare_v3.ingestion.common import QualityGateResult
from ashare_v3.ingestion.daily_incremental_config import DEFAULT_DAILY_INCREMENTAL_CONFIG
from ashare_v3.ingestion.ingestion_acceptance import quality_gate_to_dict
from ashare_v3.ingestion.parquet_archive import DEFAULT_DATA_ROOT
from ashare_v3.ingestion.real_execution_application import RealExecutionApplicationPackage, build_real_execution_application_package
from ashare_v3.ingestion.real_execution_config import DEFAULT_REAL_EXECUTION_CONFIG
from ashare_v3.ingestion.schema_readiness import DEFAULT_SCHEMA_PATH


REQUIRED_PROBE_ITEM_IDS = (
    "security.env_tushare_token_present",
    "security.env_postgres_dsn_present",
    "database.postgresql_connectivity",
    "database.schema_applied",
    "archive.data_root_present",
    "archive.data_root_writable",
    "archive.manifest_root_writable",
    "tdx.root_readable",
    "tdx.board_txt_files_readable",
    "source.tushare_reachable",
    "source.mootdx_reachable",
    "runtime.python_dependencies_available",
    "safety.old_system_boundary",
    "safety.no_worker_or_service_start",
)
REQUIRED_PROBE_CATEGORIES = ("security", "database", "archive", "tdx", "source", "runtime", "safety")
RUNTIME_DEPENDENCIES = ("pandas", "pyarrow", "psycopg", "tushare", "mootdx")
TDX_REQUIRED_TXT_FILES = ("地区板块.txt", "指数板块.txt", "概念板块.txt", "行业板块.txt")


@dataclass(frozen=True)
class EnvironmentProbeItem:
    item_id: str
    category: str
    target_kind: str
    target: str
    planned_probe: str
    required_permission: str
    evidence: Mapping[str, Any]
    approval_status: str = "pending_user_confirmation"
    will_run: bool = False
    actual_status: str = "not_checked"

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "category": self.category,
            "target_kind": self.target_kind,
            "target": self.target,
            "planned_probe": self.planned_probe,
            "required_permission": self.required_permission,
            "approval_status": self.approval_status,
            "will_run": self.will_run,
            "actual_status": self.actual_status,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class EnvironmentProbePlanReport:
    plan_id: str
    initial_config_path: str
    daily_config_path: str
    real_config_path: str
    schema_path: str
    data_root: str
    tdx_root: str
    required_env_vars: tuple[str, ...]
    application_passed: bool
    application_ready_to_execute: bool
    execution_blockers: tuple[str, ...]
    probe_items: tuple[EnvironmentProbeItem, ...]
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
    def probe_item_ids(self) -> tuple[str, ...]:
        return tuple(item.item_id for item in self.probe_items)

    @property
    def pending_probe_item_ids(self) -> tuple[str, ...]:
        return tuple(item.item_id for item in self.probe_items if item.approval_status != "confirmed")

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "initial_config_path": self.initial_config_path,
            "daily_config_path": self.daily_config_path,
            "real_config_path": self.real_config_path,
            "schema_path": self.schema_path,
            "data_root": self.data_root,
            "tdx_root": self.tdx_root,
            "required_env_vars": list(self.required_env_vars),
            "application_passed": self.application_passed,
            "application_ready_to_execute": self.application_ready_to_execute,
            "execution_blockers": list(self.execution_blockers),
            "passed": self.passed,
            "ready_to_probe": self.ready_to_probe,
            "pending_probe_item_ids": list(self.pending_probe_item_ids),
            "probe_items": [item.to_dict() for item in self.probe_items],
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


def build_environment_probe_plan_report(
    *,
    initial_config_path: str | Path = DEFAULT_INITIAL_BACKFILL_CONFIG,
    daily_config_path: str | Path = DEFAULT_DAILY_INCREMENTAL_CONFIG,
    real_config_path: str | Path = DEFAULT_REAL_EXECUTION_CONFIG,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
    data_root: str | None = None,
) -> EnvironmentProbePlanReport:
    application = build_real_execution_application_package(
        initial_config_path=initial_config_path,
        daily_config_path=daily_config_path,
        real_config_path=real_config_path,
        schema_path=schema_path,
        data_root=data_root or DEFAULT_DATA_ROOT,
    )
    probe_items = tuple(build_probe_items(application))
    report = EnvironmentProbePlanReport(
        plan_id="environment_probe_plan_n3_6",
        initial_config_path=str(initial_config_path),
        daily_config_path=str(daily_config_path),
        real_config_path=str(real_config_path),
        schema_path=str(schema_path),
        data_root=application.data_root,
        tdx_root=application.tdx_root,
        required_env_vars=application.required_env_vars,
        application_passed=application.passed,
        application_ready_to_execute=application.ready_to_execute,
        execution_blockers=application.execution_blockers,
        probe_items=probe_items,
        quality_gates=(),
    )
    return EnvironmentProbePlanReport(
        plan_id=report.plan_id,
        initial_config_path=report.initial_config_path,
        daily_config_path=report.daily_config_path,
        real_config_path=report.real_config_path,
        schema_path=report.schema_path,
        data_root=report.data_root,
        tdx_root=report.tdx_root,
        required_env_vars=report.required_env_vars,
        application_passed=report.application_passed,
        application_ready_to_execute=report.application_ready_to_execute,
        execution_blockers=report.execution_blockers,
        probe_items=report.probe_items,
        quality_gates=tuple(build_probe_quality_gates(report)),
    )


def build_probe_items(application: RealExecutionApplicationPackage) -> list[EnvironmentProbeItem]:
    data_lake_root = str(PurePosixPath(application.data_root) / "data_lake")
    manifest_root = str(PurePosixPath(application.data_root) / "data_lake" / "_manifests")
    tdx_files = [str(PurePosixPath(application.tdx_root) / file_name) for file_name in TDX_REQUIRED_TXT_FILES]
    network_sources = sorted(
        {
            request.source.split(".", 1)[0]
            for stage in application.stages
            for request in stage.source_requests
            if request.requires_network
        }
    )
    fallback_sources = sorted(
        {
            request.fallback_source.split(".", 1)[0]
            for stage in application.stages
            for request in stage.source_requests
            if request.fallback_source and request.requires_network
        }
    )

    return [
        EnvironmentProbeItem(
            item_id="security.env_tushare_token_present",
            category="security",
            target_kind="environment_variable_name",
            target="TUSHARE_TOKEN",
            planned_probe="future_check_env_var_name_is_bound_without_logging_value",
            required_permission="read_environment_variable_metadata",
            evidence={"secret_value_must_not_be_logged": True},
        ),
        EnvironmentProbeItem(
            item_id="security.env_postgres_dsn_present",
            category="security",
            target_kind="environment_variable_name",
            target="ASHARE_V3_POSTGRES_DSN",
            planned_probe="future_check_env_var_name_is_bound_without_logging_value",
            required_permission="read_environment_variable_metadata",
            evidence={"secret_value_must_not_be_logged": True},
        ),
        EnvironmentProbeItem(
            item_id="database.postgresql_connectivity",
            category="database",
            target_kind="postgres_dsn_env_name",
            target="ASHARE_V3_POSTGRES_DSN",
            planned_probe="future_open_short_postgresql_probe_then_close_without_writes",
            required_permission="postgresql_readonly_connection_probe",
            evidence={"schema_path": application.schema_path, "writes_allowed": False},
        ),
        EnvironmentProbeItem(
            item_id="database.schema_applied",
            category="database",
            target_kind="postgres_schema",
            target="sql/001_raw_ingestion_schema.sql",
            planned_probe="future_compare_required_table_names_against_postgresql_catalog",
            required_permission="postgresql_readonly_catalog_probe",
            evidence={"expected_table_count": 14, "writes_allowed": False},
        ),
        EnvironmentProbeItem(
            item_id="archive.data_root_present",
            category="archive",
            target_kind="filesystem_path",
            target=application.data_root,
            planned_probe="future_check_path_exists_without_creating_it",
            required_permission="filesystem_metadata_probe",
            evidence={"data_root": application.data_root},
        ),
        EnvironmentProbeItem(
            item_id="archive.data_root_writable",
            category="archive",
            target_kind="filesystem_path",
            target=application.data_root,
            planned_probe="future_check_write_permission_using_non_destructive_temp_probe_after_approval",
            required_permission="filesystem_write_probe",
            evidence={"writes_allowed_now": False},
        ),
        EnvironmentProbeItem(
            item_id="archive.manifest_root_writable",
            category="archive",
            target_kind="filesystem_path",
            target=manifest_root,
            planned_probe="future_check_manifest_parent_write_permission_after_approval",
            required_permission="filesystem_write_probe",
            evidence={"data_lake_root": data_lake_root, "writes_allowed_now": False},
        ),
        EnvironmentProbeItem(
            item_id="tdx.root_readable",
            category="tdx",
            target_kind="filesystem_path",
            target=application.tdx_root,
            planned_probe="future_check_tdx_root_metadata_without_reading_files",
            required_permission="tdx_root_metadata_probe",
            evidence={"tdx_root": application.tdx_root},
        ),
        EnvironmentProbeItem(
            item_id="tdx.board_txt_files_readable",
            category="tdx",
            target_kind="filesystem_paths",
            target=",".join(tdx_files),
            planned_probe="future_check_required_tdx_txt_files_are_readable_after_approval",
            required_permission="tdx_txt_read_probe",
            evidence={"required_files": tdx_files, "encoding": "GBK", "separator": "tab"},
        ),
        EnvironmentProbeItem(
            item_id="source.tushare_reachable",
            category="source",
            target_kind="external_api",
            target="tushare",
            planned_probe="future_call_minimal_tushare_metadata_endpoint_after_approval",
            required_permission="network_probe",
            evidence={"env_var": "TUSHARE_TOKEN", "source_names": sorted(set(network_sources + fallback_sources))},
        ),
        EnvironmentProbeItem(
            item_id="source.mootdx_reachable",
            category="source",
            target_kind="external_api",
            target="mootdx",
            planned_probe="future_call_minimal_mootdx_quote_or_finance_probe_after_approval",
            required_permission="network_or_tdx_client_probe",
            evidence={"source_names": sorted(set(network_sources + fallback_sources))},
        ),
        EnvironmentProbeItem(
            item_id="runtime.python_dependencies_available",
            category="runtime",
            target_kind="python_packages",
            target=",".join(RUNTIME_DEPENDENCIES),
            planned_probe="future_import_check_without_running_ingestion",
            required_permission="python_import_probe",
            evidence={"packages": list(RUNTIME_DEPENDENCIES)},
        ),
        EnvironmentProbeItem(
            item_id="safety.old_system_boundary",
            category="safety",
            target_kind="project_boundary",
            target="old_system_paths_declared_in_AGENTS",
            planned_probe="future_assert_probe_plan_excludes_old_system_paths",
            required_permission="none",
            evidence={"project_rule_source": "AGENTS.md", "old_system_access_allowed": False},
        ),
        EnvironmentProbeItem(
            item_id="safety.no_worker_or_service_start",
            category="safety",
            target_kind="process_boundary",
            target="worker_or_service_start",
            planned_probe="future_assert_no_worker_or_long_running_service_is_started",
            required_permission="none",
            evidence={"worker_start_allowed": False},
        ),
    ]


def build_probe_quality_gates(report: EnvironmentProbePlanReport) -> list[QualityGateResult]:
    item_ids = set(report.probe_item_ids)
    missing_items = sorted(set(REQUIRED_PROBE_ITEM_IDS) - item_ids)
    extra_items = sorted(item_ids - set(REQUIRED_PROBE_ITEM_IDS))
    categories = {item.category for item in report.probe_items}
    missing_categories = sorted(set(REQUIRED_PROBE_CATEGORIES) - categories)
    running_items = [item.item_id for item in report.probe_items if item.will_run or item.actual_status != "not_checked"]
    non_pending_items = [item.item_id for item in report.probe_items if item.approval_status != "pending_user_confirmation"]
    env_var_targets = {item.target for item in report.probe_items if item.category == "security"}
    required_env_vars = set(report.required_env_vars)
    expected_paths = {report.data_root, report.tdx_root}
    actual_paths = {item.target for item in report.probe_items if item.target_kind == "filesystem_path"}
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
            gate_name="environment_probe_application_package_passed",
            status="passed" if report.application_passed and not report.application_ready_to_execute else "failed",
            expected_value="application package passed but not executable",
            actual_value=f"{report.application_passed}/{report.application_ready_to_execute}",
            details={"execution_blockers": list(report.execution_blockers)},
        ),
        QualityGateResult(
            gate_name="environment_probe_items_present",
            status="passed" if not missing_items and not extra_items else "failed",
            expected_value=str(len(REQUIRED_PROBE_ITEM_IDS)),
            actual_value=str(len(report.probe_items)),
            details={"missing_items": missing_items, "extra_items": extra_items},
        ),
        QualityGateResult(
            gate_name="environment_probe_categories_present",
            status="passed" if not missing_categories else "failed",
            expected_value="/".join(REQUIRED_PROBE_CATEGORIES),
            actual_value=",".join(sorted(categories)),
            details={"missing_categories": missing_categories},
        ),
        QualityGateResult(
            gate_name="environment_probe_required_targets_planned",
            status="passed" if required_env_vars.issubset(env_var_targets) and expected_paths.issubset(actual_paths) else "failed",
            expected_value="env vars plus data_root and tdx_root",
            actual_value=f"env={sorted(env_var_targets)};paths={sorted(actual_paths)}",
            details={"required_env_vars": sorted(required_env_vars), "expected_paths": sorted(expected_paths)},
        ),
        QualityGateResult(
            gate_name="environment_probe_not_executed",
            status="passed" if not running_items else "failed",
            expected_value="all probe items are planned only",
            actual_value=str(len(running_items)),
            details={"running_items": running_items},
        ),
        QualityGateResult(
            gate_name="environment_probe_approvals_pending",
            status="passed" if not non_pending_items else "failed",
            expected_value="all probe approvals pending",
            actual_value=str(len(non_pending_items)),
            details={"non_pending_items": non_pending_items},
        ),
        QualityGateResult(
            gate_name="environment_probe_no_real_authorization",
            status="passed" if not report.ready_to_probe and not report.will_authorize_real_execution else "failed",
            expected_value="probe plan does not authorize real probe execution",
            actual_value=str(report.ready_to_probe).lower(),
            details={"pending_probe_item_ids": list(report.pending_probe_item_ids)},
        ),
        QualityGateResult(
            gate_name="environment_probe_no_side_effects",
            status="passed" if not enabled_side_effects else "failed",
            expected_value="no env read, no filesystem check, no source calls, no TDX reads, no DB, no SQL, no writes, no worker",
            actual_value=str(len(enabled_side_effects)),
            details={"enabled_side_effects": enabled_side_effects},
        ),
    ]
