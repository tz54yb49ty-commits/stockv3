"""Real-execution application package dry-run.

This module turns the approved dry-run plans into an operator-facing application
package. It lists the stages, sources, target tables, archive paths, quality
gates, rollback groups, environment variables, and permission requests that
would need manual approval before real ingestion. It never calls external APIs,
reads local TDX files, connects PostgreSQL, executes SQL, writes data files,
creates directories, or authorizes real execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from ashare_v3.ingestion.backfill_config import DEFAULT_INITIAL_BACKFILL_CONFIG, InitialBackfillConfig, load_initial_backfill_config
from ashare_v3.ingestion.backfill_summary import BackfillExecutionChecklist, BackfillTableSummary, build_backfill_execution_checklist
from ashare_v3.ingestion.common import QualityGateResult
from ashare_v3.ingestion.daily_incremental_config import DEFAULT_DAILY_INCREMENTAL_CONFIG, DailyIncrementalConfig, load_daily_incremental_config
from ashare_v3.ingestion.daily_incremental_summary import DailyIncrementalExecutionChecklist, DailyIncrementalTableSummary, build_daily_incremental_execution_checklist
from ashare_v3.ingestion.ingestion_acceptance import quality_gate_to_dict
from ashare_v3.ingestion.parquet_archive import DEFAULT_DATA_ROOT
from ashare_v3.ingestion.parquet_readiness import ParquetReadinessReport, build_parquet_readiness_report
from ashare_v3.ingestion.real_execution_config import DEFAULT_REAL_EXECUTION_CONFIG, RealExecutionConfig, load_real_execution_config
from ashare_v3.ingestion.real_execution_readiness import RealExecutionReadinessReport, build_real_execution_readiness_report
from ashare_v3.ingestion.schema_readiness import DEFAULT_SCHEMA_PATH


REQUIRED_APPLICATION_STAGES = ("initial_backfill", "daily_incremental")
REQUIRED_OPERATOR_APPROVALS = (
    "stage.initial_backfill_scope",
    "stage.daily_incremental_scope",
    "security.env_vars_available",
    "source.allow_network_reads",
    "source.allow_tdx_local_txt_reads",
    "database.allow_postgresql_writes",
    "archive.allow_data_root_writes",
    "quality_gate.block_on_p0",
    "rollback.accept_delete_by_source_batch",
    "safety.keep_old_system_boundary",
    "safety.no_worker_or_service_start",
)
CORE_TARGET_TABLE_COUNT = 11
ARCHIVE_DATASET_COUNT = 7


@dataclass(frozen=True)
class ExecutionTargetTableRequest:
    target_table: str
    data_domain: str
    data_type: str
    batch_count: int
    source_versions: tuple[str, ...]
    archive_dataset: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_table": self.target_table,
            "data_domain": self.data_domain,
            "data_type": self.data_type,
            "batch_count": self.batch_count,
            "source_versions": list(self.source_versions),
            "archive_dataset": self.archive_dataset,
        }


@dataclass(frozen=True)
class ExecutionSourceRequest:
    task_id: str
    target_table: str
    data_domain: str
    data_type: str
    source: str
    fallback_source: str | None
    date_scope: str
    source_path: str | None
    source_file: str | None
    source_params: Mapping[str, Any]
    requires_network: bool
    requires_tdx_file_read: bool
    approval_status: str = "pending_user_confirmation"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "target_table": self.target_table,
            "data_domain": self.data_domain,
            "data_type": self.data_type,
            "source": self.source,
            "fallback_source": self.fallback_source,
            "date_scope": self.date_scope,
            "source_path": self.source_path,
            "source_file": self.source_file,
            "source_params": dict(self.source_params),
            "requires_network": self.requires_network,
            "requires_tdx_file_read": self.requires_tdx_file_read,
            "approval_status": self.approval_status,
        }


@dataclass(frozen=True)
class ExecutionArchiveRequest:
    dataset: str
    dataset_root: str
    manifest_root: str
    partition_keys: tuple[str, ...]
    sample_manifest_path: str
    sample_parquet_path: str
    rollback_paths: tuple[str, ...]
    source_versions: tuple[str, ...]
    approval_status: str = "pending_user_confirmation"

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "dataset_root": self.dataset_root,
            "manifest_root": self.manifest_root,
            "partition_keys": list(self.partition_keys),
            "sample_manifest_path": self.sample_manifest_path,
            "sample_parquet_path": self.sample_parquet_path,
            "rollback_paths": list(self.rollback_paths),
            "source_versions": list(self.source_versions),
            "approval_status": self.approval_status,
        }


@dataclass(frozen=True)
class ExecutionRollbackRequest:
    group_id: str
    target_table: str
    data_domain: str
    data_type: str
    source_version: str
    source_batch_count: int
    rollback_strategy: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "target_table": self.target_table,
            "data_domain": self.data_domain,
            "data_type": self.data_type,
            "source_version": self.source_version,
            "source_batch_count": self.source_batch_count,
            "rollback_strategy": self.rollback_strategy,
        }


@dataclass(frozen=True)
class ExecutionStageApplication:
    stage_id: str
    stage_kind: str
    date_scope: str
    batch_count: int
    target_tables: tuple[ExecutionTargetTableRequest, ...]
    source_requests: tuple[ExecutionSourceRequest, ...]
    archive_requests: tuple[ExecutionArchiveRequest, ...]
    rollback_requests: tuple[ExecutionRollbackRequest, ...]
    quality_gate_categories: tuple[str, ...]
    execution_order: tuple[str, ...]
    approval_status: str = "pending_user_confirmation"

    @property
    def target_table_count(self) -> int:
        return len(self.target_tables)

    @property
    def source_request_count(self) -> int:
        return len(self.source_requests)

    @property
    def archive_request_count(self) -> int:
        return len(self.archive_requests)

    @property
    def rollback_request_count(self) -> int:
        return len(self.rollback_requests)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "stage_kind": self.stage_kind,
            "date_scope": self.date_scope,
            "batch_count": self.batch_count,
            "target_table_count": self.target_table_count,
            "source_request_count": self.source_request_count,
            "archive_request_count": self.archive_request_count,
            "rollback_request_count": self.rollback_request_count,
            "quality_gate_categories": list(self.quality_gate_categories),
            "approval_status": self.approval_status,
            "target_tables": [table.to_dict() for table in self.target_tables],
            "source_requests": [request.to_dict() for request in self.source_requests],
            "archive_requests": [request.to_dict() for request in self.archive_requests],
            "rollback_requests": [request.to_dict() for request in self.rollback_requests],
            "execution_order": list(self.execution_order),
        }


@dataclass(frozen=True)
class OperatorApprovalItem:
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
class RealExecutionApplicationPackage:
    package_id: str
    initial_config_path: str
    daily_config_path: str
    real_config_path: str
    schema_path: str
    data_root: str
    tdx_root: str
    required_env_vars: tuple[str, ...]
    stages: tuple[ExecutionStageApplication, ...]
    operator_approval_items: tuple[OperatorApprovalItem, ...]
    readiness_passed: bool
    readiness_ready_to_execute: bool
    execution_blockers: tuple[str, ...]
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
        return False

    @property
    def pending_approval_item_ids(self) -> tuple[str, ...]:
        return tuple(item.item_id for item in self.operator_approval_items if not item.confirmed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "initial_config_path": self.initial_config_path,
            "daily_config_path": self.daily_config_path,
            "real_config_path": self.real_config_path,
            "schema_path": self.schema_path,
            "data_root": self.data_root,
            "tdx_root": self.tdx_root,
            "required_env_vars": list(self.required_env_vars),
            "passed": self.passed,
            "ready_to_execute": self.ready_to_execute,
            "readiness_passed": self.readiness_passed,
            "readiness_ready_to_execute": self.readiness_ready_to_execute,
            "execution_blockers": list(self.execution_blockers),
            "pending_approval_item_ids": list(self.pending_approval_item_ids),
            "stages": [stage.to_dict() for stage in self.stages],
            "operator_approval_items": [item.to_dict() for item in self.operator_approval_items],
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


def build_real_execution_application_package(
    *,
    initial_config_path: str | Path = DEFAULT_INITIAL_BACKFILL_CONFIG,
    daily_config_path: str | Path = DEFAULT_DAILY_INCREMENTAL_CONFIG,
    real_config_path: str | Path = DEFAULT_REAL_EXECUTION_CONFIG,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
    data_root: str | None = None,
) -> RealExecutionApplicationPackage:
    initial_config = load_initial_backfill_config(initial_config_path)
    daily_config = load_daily_incremental_config(daily_config_path)
    real_config = load_real_execution_config(real_config_path)
    archive_data_root = data_root or real_config.data_root or DEFAULT_DATA_ROOT
    readiness = build_real_execution_readiness_report(
        initial_config_path=initial_config_path,
        daily_config_path=daily_config_path,
        real_config_path=real_config_path,
        schema_path=schema_path,
        data_root=archive_data_root,
    )
    parquet = build_parquet_readiness_report(archive_data_root)
    initial_summary = build_backfill_execution_checklist(initial_config.to_plan())
    daily_summary = build_daily_incremental_execution_checklist(daily_config.to_plan(), source_configs=daily_config.sources)
    stages = (
        build_initial_stage_application(initial_config, initial_summary, parquet),
        build_daily_stage_application(daily_config, daily_summary, parquet),
    )
    approval_items = tuple(build_operator_approval_items(initial_config, daily_config, real_config, readiness))
    package = RealExecutionApplicationPackage(
        package_id="real_execution_application_n3_5",
        initial_config_path=str(initial_config_path),
        daily_config_path=str(daily_config_path),
        real_config_path=str(real_config_path),
        schema_path=str(schema_path),
        data_root=archive_data_root,
        tdx_root=real_config.tdx_root,
        required_env_vars=(real_config.tushare_token_env, real_config.postgres_dsn_env),
        stages=stages,
        operator_approval_items=approval_items,
        readiness_passed=readiness.passed,
        readiness_ready_to_execute=readiness.ready_to_execute,
        execution_blockers=readiness.execution_blockers,
        quality_gates=(),
    )
    return RealExecutionApplicationPackage(
        package_id=package.package_id,
        initial_config_path=package.initial_config_path,
        daily_config_path=package.daily_config_path,
        real_config_path=package.real_config_path,
        schema_path=package.schema_path,
        data_root=package.data_root,
        tdx_root=package.tdx_root,
        required_env_vars=package.required_env_vars,
        stages=package.stages,
        operator_approval_items=package.operator_approval_items,
        readiness_passed=package.readiness_passed,
        readiness_ready_to_execute=package.readiness_ready_to_execute,
        execution_blockers=package.execution_blockers,
        quality_gates=tuple(build_application_quality_gates(package)),
    )


def build_initial_stage_application(
    config: InitialBackfillConfig,
    summary: BackfillExecutionChecklist,
    parquet: ParquetReadinessReport,
) -> ExecutionStageApplication:
    source_versions_by_dataset = {
        table.archive_dataset: table.source_versions
        for table in summary.table_summaries
        if table.archive_dataset
    }
    return ExecutionStageApplication(
        stage_id="initial_backfill",
        stage_kind="initial_backfill",
        date_scope=f"{summary.start_date}-{summary.end_date}; snapshot={summary.snapshot_date}",
        batch_count=summary.batch_count,
        target_tables=tuple(build_initial_target_table_request(table) for table in summary.table_summaries),
        source_requests=tuple(build_source_requests_from_config(config.sources, config.tdx_root, f"{summary.start_date}-{summary.end_date}", "initial_backfill")),
        archive_requests=tuple(build_archive_requests(parquet, source_versions_by_dataset)),
        rollback_requests=tuple(
            ExecutionRollbackRequest(
                group_id=group.group_id,
                target_table=group.target_table,
                data_domain=group.data_domain,
                data_type=group.data_type,
                source_version=group.source_version,
                source_batch_count=group.source_batch_count,
                rollback_strategy=group.rollback_strategy,
            )
            for group in summary.rollback_groups
        ),
        quality_gate_categories=("structure", "source_trace", "quality_gate", "archive", "rollback", "safety"),
        execution_order=summary.execution_order,
    )


def build_daily_stage_application(
    config: DailyIncrementalConfig,
    summary: DailyIncrementalExecutionChecklist,
    parquet: ParquetReadinessReport,
) -> ExecutionStageApplication:
    source_versions_by_dataset = {
        table.archive_dataset: (table.source_version,)
        for table in summary.table_summaries
        if table.archive_dataset
    }
    return ExecutionStageApplication(
        stage_id="daily_incremental",
        stage_kind="daily_incremental",
        date_scope=summary.trade_date,
        batch_count=summary.task_count,
        target_tables=tuple(build_daily_target_table_request(table) for table in summary.table_summaries),
        source_requests=tuple(build_source_requests_from_config(config.sources, config.tdx_root, summary.trade_date, "daily_incremental")),
        archive_requests=tuple(build_archive_requests(parquet, source_versions_by_dataset)),
        rollback_requests=tuple(
            ExecutionRollbackRequest(
                group_id=group.group_id,
                target_table=group.target_table,
                data_domain=group.data_domain,
                data_type=group.data_type,
                source_version=group.source_version,
                source_batch_count=group.source_batch_count,
                rollback_strategy=group.rollback_strategy,
            )
            for group in summary.rollback_groups
        ),
        quality_gate_categories=("structure", "source_trace", "quality_gate", "archive", "rollback", "safety"),
        execution_order=summary.execution_order,
    )


def build_initial_target_table_request(summary: BackfillTableSummary) -> ExecutionTargetTableRequest:
    return ExecutionTargetTableRequest(
        target_table=summary.target_table,
        data_domain=summary.data_domain,
        data_type=summary.data_type,
        batch_count=summary.batch_count,
        source_versions=summary.source_versions,
        archive_dataset=summary.archive_dataset,
    )


def build_daily_target_table_request(summary: DailyIncrementalTableSummary) -> ExecutionTargetTableRequest:
    return ExecutionTargetTableRequest(
        target_table=summary.target_table,
        data_domain=summary.data_domain,
        data_type=summary.data_type,
        batch_count=1,
        source_versions=(summary.source_version,),
        archive_dataset=summary.archive_dataset,
    )


def build_source_requests_from_config(
    sources: Mapping[str, Mapping[str, Any]],
    tdx_root: str,
    default_date_scope: str,
    stage_kind: str,
) -> list[ExecutionSourceRequest]:
    requests: list[ExecutionSourceRequest] = []
    for task_id, source_config in sources.items():
        source = str(source_config["source"])
        source_path, source_file = resolve_source_path(source_config, tdx_root)
        requests.append(
            ExecutionSourceRequest(
                task_id=task_id,
                target_table=str(source_config["target_table"]),
                data_domain=str(source_config["data_domain"]),
                data_type=str(source_config["data_type"]),
                source=source,
                fallback_source=optional_string(source_config.get("fallback_source")),
                date_scope=source_date_scope(source_config, default_date_scope, stage_kind),
                source_path=source_path,
                source_file=source_file,
                source_params=dict(source_config.get("source_params") or {}),
                requires_network=source_requires_network(source, optional_string(source_config.get("fallback_source"))),
                requires_tdx_file_read=source_requires_tdx_file_read(source),
            )
        )
    return requests


def build_archive_requests(
    parquet: ParquetReadinessReport,
    source_versions_by_dataset: Mapping[str | None, tuple[str, ...]],
) -> list[ExecutionArchiveRequest]:
    requests: list[ExecutionArchiveRequest] = []
    for summary in parquet.dataset_summaries:
        requests.append(
            ExecutionArchiveRequest(
                dataset=summary.dataset,
                dataset_root=summary.dataset_root,
                manifest_root=summary.manifest_root,
                partition_keys=summary.partition_keys,
                sample_manifest_path=summary.sample_manifest_path,
                sample_parquet_path=summary.sample_parquet_path,
                rollback_paths=summary.sample_rollback_paths,
                source_versions=source_versions_by_dataset.get(summary.dataset, ()),
            )
        )
    return requests


def build_operator_approval_items(
    initial_config: InitialBackfillConfig,
    daily_config: DailyIncrementalConfig,
    real_config: RealExecutionConfig,
    readiness: RealExecutionReadinessReport,
) -> list[OperatorApprovalItem]:
    item_specs = [
        (
            "stage.initial_backfill_scope",
            "stage",
            "Confirm initial backfill scope is 20230101-20260521 with snapshot 20260521.",
            {
                "start_date": initial_config.start_date,
                "end_date": initial_config.end_date,
                "snapshot_date": initial_config.snapshot_date,
            },
        ),
        (
            "stage.daily_incremental_scope",
            "stage",
            "Confirm daily incremental scope is exactly one trade_date.",
            {"trade_date": daily_config.trade_date},
        ),
        (
            "security.env_vars_available",
            "security",
            "Confirm required environment variables are available outside repository files.",
            {"required_env_vars": [real_config.tushare_token_env, real_config.postgres_dsn_env]},
        ),
        (
            "source.allow_network_reads",
            "source",
            "Confirm Tushare and Mootdx network reads are allowed only for raw ingestion sources.",
            {"requested_sources": ["tushare", "mootdx"]},
        ),
        (
            "source.allow_tdx_local_txt_reads",
            "source",
            "Confirm local TDX txt reads are allowed for board identity and membership only.",
            {"tdx_root": real_config.tdx_root},
        ),
        (
            "database.allow_postgresql_writes",
            "database",
            "Confirm PostgreSQL writes are allowed only after schema and P0 quality gates pass.",
            {"dsn_env_var": real_config.postgres_dsn_env},
        ),
        (
            "archive.allow_data_root_writes",
            "archive",
            "Confirm Parquet data and manifest writes are allowed under the v3 data root.",
            {"data_root": real_config.data_root},
        ),
        (
            "quality_gate.block_on_p0",
            "quality_gate",
            "Confirm P0 quality gate failures block active source_version activation.",
            {"block_on_p0": real_config.quality_gate["block_on_p0"]},
        ),
        (
            "rollback.accept_delete_by_source_batch",
            "rollback",
            "Confirm rollback deletes by source_batch_id and restores previous active source_version.",
            {"rollback_strategy": real_config.rollback["strategy"]},
        ),
        (
            "safety.keep_old_system_boundary",
            "safety",
            "Confirm old system reads, writes, migrations, services, and LaunchAgents stay forbidden.",
            {"old_system_access": real_config.permissions["allow_old_system_access"]},
        ),
        (
            "safety.no_worker_or_service_start",
            "safety",
            "Confirm no worker or long-running service startup is authorized by this package.",
            {"worker_start": real_config.permissions["allow_worker_start"]},
        ),
    ]
    return [
        OperatorApprovalItem(
            item_id=item_id,
            category=category,
            required_confirmation=required_confirmation,
            evidence={**evidence, "readiness_blockers": list(readiness.execution_blockers)},
        )
        for item_id, category, required_confirmation, evidence in item_specs
    ]


def build_application_quality_gates(package: RealExecutionApplicationPackage) -> list[QualityGateResult]:
    stage_ids = tuple(stage.stage_id for stage in package.stages)
    missing_stages = sorted(set(REQUIRED_APPLICATION_STAGES) - set(stage_ids))
    target_count_failures = [stage.stage_id for stage in package.stages if stage.target_table_count != CORE_TARGET_TABLE_COUNT]
    source_count_failures = [stage.stage_id for stage in package.stages if stage.source_request_count != CORE_TARGET_TABLE_COUNT]
    archive_count_failures = [stage.stage_id for stage in package.stages if stage.archive_request_count != ARCHIVE_DATASET_COUNT]
    rollback_count_failures = [stage.stage_id for stage in package.stages if stage.rollback_request_count != CORE_TARGET_TABLE_COUNT]
    mixed_table_hits = [
        table.target_table
        for stage in package.stages
        for table in stage.target_tables
        if table.target_table == "daily_bar_fact" or not table.target_table.startswith(("common_", "stock_", "index_", "board_"))
    ]
    approval_ids = tuple(item.item_id for item in package.operator_approval_items)
    missing_approvals = sorted(set(REQUIRED_OPERATOR_APPROVALS) - set(approval_ids))
    confirmed_approvals = [item.item_id for item in package.operator_approval_items if item.confirmed]
    side_effect_flags = {
        "will_call_external_sources": package.will_call_external_sources,
        "will_read_tdx_files": package.will_read_tdx_files,
        "will_connect_database": package.will_connect_database,
        "will_execute_sql": package.will_execute_sql,
        "will_create_directories": package.will_create_directories,
        "will_write_data_files": package.will_write_data_files,
        "will_authorize_real_execution": package.will_authorize_real_execution,
    }
    enabled_side_effects = sorted(name for name, enabled in side_effect_flags.items() if enabled)

    return [
        QualityGateResult(
            gate_name="application_readiness_summary_passed",
            status="passed" if package.readiness_passed and not package.readiness_ready_to_execute else "failed",
            expected_value="readiness passed but not ready_to_execute",
            actual_value=f"{package.readiness_passed}/{package.readiness_ready_to_execute}",
            details={"execution_blockers": list(package.execution_blockers)},
        ),
        QualityGateResult(
            gate_name="application_stages_present",
            status="passed" if not missing_stages else "failed",
            expected_value="/".join(REQUIRED_APPLICATION_STAGES),
            actual_value=",".join(stage_ids),
            details={"missing_stages": missing_stages},
        ),
        QualityGateResult(
            gate_name="application_stage_counts_match",
            status="passed" if not target_count_failures and not source_count_failures else "failed",
            expected_value="11 target tables and 11 source requests per stage",
            actual_value=f"targets={target_count_failures};sources={source_count_failures}",
            details={"target_count_failures": target_count_failures, "source_count_failures": source_count_failures},
        ),
        QualityGateResult(
            gate_name="application_physical_tables_split",
            status="passed" if not mixed_table_hits else "failed",
            expected_value="stock/index/board/common physical tables only",
            actual_value=str(len(mixed_table_hits)),
            details={"mixed_table_hits": mixed_table_hits},
        ),
        QualityGateResult(
            gate_name="application_archive_and_rollback_coverage",
            status="passed" if not archive_count_failures and not rollback_count_failures else "failed",
            expected_value="7 archive datasets and 11 rollback groups per stage",
            actual_value=f"archives={archive_count_failures};rollbacks={rollback_count_failures}",
            details={"archive_count_failures": archive_count_failures, "rollback_count_failures": rollback_count_failures},
        ),
        QualityGateResult(
            gate_name="application_operator_approvals_pending",
            status="passed" if not missing_approvals and not confirmed_approvals else "failed",
            expected_value="all required approvals listed and pending",
            actual_value=f"missing={len(missing_approvals)};confirmed={len(confirmed_approvals)}",
            details={"missing_approvals": missing_approvals, "confirmed_approvals": confirmed_approvals},
        ),
        QualityGateResult(
            gate_name="application_no_real_authorization",
            status="passed" if not package.ready_to_execute and not package.will_authorize_real_execution else "failed",
            expected_value="application package does not authorize execution",
            actual_value=str(package.ready_to_execute).lower(),
            details={"pending_approval_item_ids": list(package.pending_approval_item_ids)},
        ),
        QualityGateResult(
            gate_name="application_no_side_effects",
            status="passed" if not enabled_side_effects else "failed",
            expected_value="no source calls, no TDX reads, no DB, no SQL, no directory creation, no data file writes",
            actual_value=str(len(enabled_side_effects)),
            details={"enabled_side_effects": enabled_side_effects},
        ),
    ]


def resolve_source_path(source_config: Mapping[str, Any], tdx_root: str) -> tuple[str | None, str | None]:
    source_path_key = optional_string(source_config.get("source_path_key"))
    source_file = optional_string(source_config.get("source_file"))
    if source_path_key == "tdx_root" and source_file:
        return str(PurePosixPath(tdx_root) / source_file), source_file
    if source_path_key == "tdx_root":
        return tdx_root, source_file
    if source_file:
        return str(PurePosixPath(tdx_root) / source_file), source_file
    return None, None


def source_date_scope(source_config: Mapping[str, Any], default_date_scope: str, stage_kind: str) -> str:
    slice_kind = optional_string(source_config.get("slice_kind"))
    if stage_kind == "initial_backfill" and slice_kind == "snapshot":
        return "snapshot_date"
    return default_date_scope


def source_requires_network(source: str, fallback_source: str | None) -> bool:
    source_names = [source, fallback_source or ""]
    return any(name.startswith(("tushare.", "mootdx.")) for name in source_names)


def source_requires_tdx_file_read(source: str) -> bool:
    return source.startswith("tdx.local_txt")


def optional_string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
