"""Whole-batch raw ingestion orchestration dry-run planning.

This module composes existing dry-run plans. It never calls external data
sources, reads local TDX files, connects PostgreSQL, executes SQL, or writes
Parquet files/manifests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ashare_v3.ingestion.active_source_version import ActiveSourceVersionPlan, build_active_source_version_plan
from ashare_v3.ingestion.common import BatchSpec, IngestionValidationError, QualityGateResult, make_source_batch_id, require_yyyymmdd, utc_now_iso
from ashare_v3.ingestion.parquet_archive import DATASET_PARTITION_KEYS, DEFAULT_DATA_ROOT, ParquetArchivePlan, build_parquet_archive_plan
from ashare_v3.ingestion.postgres_write_plan import PostgresWritePlan, build_postgres_write_plan


@dataclass(frozen=True)
class IngestionTaskSpec:
    task_id: str
    table_name: str
    data_domain: str
    data_type: str
    source: str
    dependencies: tuple[str, ...]
    source_path: str | None = None
    source_params: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class IngestionOrchestrationTaskPlan:
    spec: IngestionTaskSpec
    batch_spec: BatchSpec
    target_write_plan: PostgresWritePlan
    batch_audit_write_plan: PostgresWritePlan
    quality_gate_write_plan: PostgresWritePlan
    active_source_version_plan: ActiveSourceVersionPlan
    archive_plan: ParquetArchivePlan | None
    orchestration_quality_gates: tuple[QualityGateResult, ...]
    will_call_external_source: bool = False
    will_read_tdx_files: bool = False
    will_connect_database: bool = False
    will_execute_sql: bool = False
    will_write_data_files: bool = False

    @property
    def passed(self) -> bool:
        plan_results = [
            self.target_write_plan.passed,
            self.batch_audit_write_plan.passed,
            self.quality_gate_write_plan.passed,
            self.active_source_version_plan.activation_allowed,
            all(gate.passed for gate in self.orchestration_quality_gates),
        ]
        if self.archive_plan is not None:
            plan_results.append(self.archive_plan.passed)
        return all(plan_results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.spec.task_id,
            "target_table": self.spec.table_name,
            "data_domain": self.spec.data_domain,
            "data_type": self.spec.data_type,
            "source": self.spec.source,
            "dependencies": list(self.spec.dependencies),
            "source_batch_id": self.batch_spec.batch_id,
            "source_version": self.batch_spec.source_version,
            "passed": self.passed,
            "target_write_plan": self.target_write_plan.to_dict(),
            "batch_audit_write_plan": self.batch_audit_write_plan.to_dict(),
            "quality_gate_write_plan": self.quality_gate_write_plan.to_dict(),
            "archive_plan": self.archive_plan.to_manifest_dict() if self.archive_plan else None,
            "active_source_version_plan": self.active_source_version_plan.to_dict(),
            "orchestration_quality_gates": [quality_gate_to_dict(gate) for gate in self.orchestration_quality_gates],
            "side_effects": {
                "will_call_external_source": self.will_call_external_source,
                "will_read_tdx_files": self.will_read_tdx_files,
                "will_connect_database": self.will_connect_database,
                "will_execute_sql": self.will_execute_sql,
                "will_write_data_files": self.will_write_data_files,
            },
            "rollback": {
                "postgres_target": self.target_write_plan.rollback_sql_template,
                "postgres_batch_audit": self.batch_audit_write_plan.rollback_sql_template,
                "postgres_quality_gate": self.quality_gate_write_plan.rollback_sql_template,
                "active_source_version": self.active_source_version_plan.rollback_sql_template,
                "archive_paths": self.archive_plan.rollback_paths if self.archive_plan else [],
            },
        }


@dataclass(frozen=True)
class DailyIngestionOrchestrationPlan:
    trade_date: str
    version: str
    data_root: str
    tasks: tuple[IngestionOrchestrationTaskPlan, ...]
    quality_gates: tuple[QualityGateResult, ...]
    will_call_external_sources: bool = False
    will_read_tdx_files: bool = False
    will_connect_database: bool = False
    will_execute_sql: bool = False
    will_write_data_files: bool = False

    @property
    def passed(self) -> bool:
        return all(task.passed for task in self.tasks) and all(gate.passed for gate in self.quality_gates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "version": self.version,
            "data_root": self.data_root,
            "task_count": len(self.tasks),
            "passed": self.passed,
            "tasks": [task.to_dict() for task in self.tasks],
            "quality_gates": [quality_gate_to_dict(gate) for gate in self.quality_gates],
            "side_effects": {
                "will_call_external_sources": self.will_call_external_sources,
                "will_read_tdx_files": self.will_read_tdx_files,
                "will_connect_database": self.will_connect_database,
                "will_execute_sql": self.will_execute_sql,
                "will_write_data_files": self.will_write_data_files,
            },
            "rollback": {
                "strategy": "delete_by_source_batch_id_then_restore_previous_active_source_version; archive_manifest_paths_are_planned_only",
                "source_batch_ids": [task.batch_spec.batch_id for task in self.tasks],
            },
        }


CORE_DAILY_TASK_SPECS: tuple[IngestionTaskSpec, ...] = (
    IngestionTaskSpec(
        task_id="common_trade_calendar",
        table_name="common_trade_calendar",
        data_domain="common",
        data_type="trade_calendar",
        source="tushare.trade_cal",
        dependencies=(),
        source_params={"exchange": "SSE"},
    ),
    IngestionTaskSpec(
        task_id="stock_identity",
        table_name="stock_identity",
        data_domain="stock",
        data_type="stock_identity",
        source="tushare.stock_basic",
        dependencies=("common_trade_calendar",),
        source_params={"exchange": "", "list_status": "L,D,P"},
    ),
    IngestionTaskSpec(
        task_id="index_identity",
        table_name="index_identity",
        data_domain="index",
        data_type="index_identity",
        source="tushare.index_basic",
        dependencies=("common_trade_calendar",),
    ),
    IngestionTaskSpec(
        task_id="board_identity",
        table_name="board_identity",
        data_domain="board",
        data_type="board_identity",
        source="tdx.local_txt",
        dependencies=("common_trade_calendar",),
        source_path="/Volumes/MacRaid/tdxdata/tdx",
    ),
    IngestionTaskSpec(
        task_id="index_membership",
        table_name="index_membership_fact",
        data_domain="index",
        data_type="index_membership",
        source="tdx.local_txt.index_board",
        dependencies=("stock_identity", "index_identity"),
        source_path="/Volumes/MacRaid/tdxdata/tdx/指数板块.txt",
    ),
    IngestionTaskSpec(
        task_id="board_membership",
        table_name="board_membership_fact",
        data_domain="board",
        data_type="board_membership",
        source="tdx.local_txt.board",
        dependencies=("stock_identity", "board_identity"),
        source_path="/Volumes/MacRaid/tdxdata/tdx",
    ),
    IngestionTaskSpec(
        task_id="stock_daily",
        table_name="stock_daily_bar_fact",
        data_domain="stock",
        data_type="stock_daily",
        source="tushare.pro_bar.qfq",
        dependencies=("common_trade_calendar", "stock_identity"),
        source_params={"asset": "E", "freq": "D", "adj": "qfq"},
    ),
    IngestionTaskSpec(
        task_id="stock_daily_basic",
        table_name="stock_daily_basic",
        data_domain="stock",
        data_type="stock_daily_basic",
        source="tushare.daily_basic",
        dependencies=("common_trade_calendar", "stock_identity"),
    ),
    IngestionTaskSpec(
        task_id="index_daily",
        table_name="index_daily_bar_fact",
        data_domain="index",
        data_type="index_daily",
        source="mootdx.index",
        dependencies=("common_trade_calendar", "index_identity"),
    ),
    IngestionTaskSpec(
        task_id="board_daily",
        table_name="board_daily_bar_fact",
        data_domain="board",
        data_type="board_daily",
        source="mootdx.index",
        dependencies=("common_trade_calendar", "board_identity"),
    ),
    IngestionTaskSpec(
        task_id="stock_financial",
        table_name="stock_financial_metrics_fact",
        data_domain="stock",
        data_type="stock_financial",
        source="mootdx.finance",
        dependencies=("common_trade_calendar", "stock_identity"),
    ),
)


def build_daily_ingestion_orchestration_plan(
    *,
    trade_date: str,
    version: str = "v1",
    data_root: str = DEFAULT_DATA_ROOT,
) -> DailyIngestionOrchestrationPlan:
    normalized_trade_date = require_yyyymmdd(trade_date, "trade_date")
    normalized_version = validate_version(version)
    seen_task_ids: set[str] = set()
    tasks: list[IngestionOrchestrationTaskPlan] = []

    for spec in CORE_DAILY_TASK_SPECS:
        task_plan = build_task_plan(
            spec=spec,
            trade_date=normalized_trade_date,
            version=normalized_version,
            seen_task_ids=seen_task_ids,
            data_root=data_root,
        )
        tasks.append(task_plan)
        seen_task_ids.add(spec.task_id)

    plan_quality_gates = tuple(build_plan_quality_gates(tasks))
    return DailyIngestionOrchestrationPlan(
        trade_date=normalized_trade_date,
        version=normalized_version,
        data_root=data_root,
        tasks=tuple(tasks),
        quality_gates=plan_quality_gates,
    )


def build_task_plan(
    *,
    spec: IngestionTaskSpec,
    trade_date: str,
    version: str,
    seen_task_ids: set[str],
    data_root: str,
) -> IngestionOrchestrationTaskPlan:
    source_batch_id = make_source_batch_id(spec.data_type, trade_date, version)
    source_version = source_batch_id
    batch_spec = BatchSpec(
        batch_id=source_batch_id,
        trade_date=trade_date,
        data_domain=spec.data_domain,
        data_type=spec.data_type,
        source=spec.source,
        source_path=spec.source_path,
        source_params=spec.source_params,
        source_version=source_version,
    )
    target_rows = sample_target_rows(spec, batch_spec)
    target_write_plan = build_postgres_write_plan(table_name=spec.table_name, rows=target_rows)
    archive_plan = (
        build_parquet_archive_plan(
            dataset=spec.table_name,
            rows=target_rows,
            source_batch_id=source_batch_id,
            source_version=source_version,
            data_root=data_root,
        )
        if spec.table_name in DATASET_PARTITION_KEYS
        else None
    )
    batch_audit_write_plan = build_postgres_write_plan(
        table_name="common_ingest_batch",
        rows=[sample_batch_audit_row(spec, batch_spec, target_write_plan, archive_plan)],
    )
    orchestration_quality_gates = tuple(build_task_orchestration_quality_gates(spec, seen_task_ids, archive_plan))
    activation_input_gates = (
        *batch_audit_write_plan.quality_gates,
        *target_write_plan.quality_gates,
        *(archive_plan.quality_gates if archive_plan else ()),
        *orchestration_quality_gates,
    )
    active_source_version_plan = build_active_source_version_plan(
        data_domain=spec.data_domain,
        data_type=spec.data_type,
        scope_key="global",
        source_version=source_version,
        source_batch_id=source_batch_id,
        quality_gates=activation_input_gates,
    )
    quality_gate_rows = sample_quality_gate_rows(
        spec=spec,
        source_batch_id=source_batch_id,
        source_version=source_version,
        gates=(*activation_input_gates, *active_source_version_plan.quality_gates),
    )
    quality_gate_write_plan = build_postgres_write_plan(
        table_name="common_quality_gate_result",
        rows=quality_gate_rows,
    )

    return IngestionOrchestrationTaskPlan(
        spec=spec,
        batch_spec=batch_spec,
        target_write_plan=target_write_plan,
        batch_audit_write_plan=batch_audit_write_plan,
        quality_gate_write_plan=quality_gate_write_plan,
        active_source_version_plan=active_source_version_plan,
        archive_plan=archive_plan,
        orchestration_quality_gates=orchestration_quality_gates,
    )


def build_task_orchestration_quality_gates(
    spec: IngestionTaskSpec,
    seen_task_ids: set[str],
    archive_plan: ParquetArchivePlan | None,
) -> list[QualityGateResult]:
    missing_dependencies = [dependency for dependency in spec.dependencies if dependency not in seen_task_ids]
    expected_prefix = f"{spec.data_domain}_"
    return [
        QualityGateResult(
            gate_name="orchestration_dependencies_precede_task",
            status="passed" if not missing_dependencies else "failed",
            expected_value="all dependencies already planned",
            actual_value=str(len(missing_dependencies)),
            details={"missing_dependencies": missing_dependencies},
        ),
        QualityGateResult(
            gate_name="orchestration_physical_table_prefix",
            status="passed" if spec.table_name.startswith(expected_prefix) else "failed",
            expected_value=expected_prefix,
            actual_value=spec.table_name,
            details={"data_domain": spec.data_domain},
        ),
        QualityGateResult(
            gate_name="orchestration_archive_plan_present_when_required",
            status="passed" if (spec.table_name not in DATASET_PARTITION_KEYS or archive_plan is not None) else "failed",
            expected_value="archive manifest plan for archive dataset",
            actual_value="present" if archive_plan else "not_required",
            details={"dataset": spec.table_name},
        ),
        QualityGateResult(
            gate_name="orchestration_dry_run_only",
            status="passed",
            expected_value="no source calls, no database execution, no data file writes",
            actual_value="dry_run",
            details={},
        ),
    ]


def build_plan_quality_gates(tasks: Sequence[IngestionOrchestrationTaskPlan]) -> list[QualityGateResult]:
    task_ids = [task.spec.task_id for task in tasks]
    batch_ids = [task.batch_spec.batch_id for task in tasks]
    covered_tables = [task.spec.table_name for task in tasks]
    expected_tables = [spec.table_name for spec in CORE_DAILY_TASK_SPECS]
    side_effect_violations = [
        task.spec.task_id
        for task in tasks
        if any(
            (
                task.will_call_external_source,
                task.will_read_tdx_files,
                task.will_connect_database,
                task.will_execute_sql,
                task.will_write_data_files,
            )
        )
    ]
    return [
        QualityGateResult(
            gate_name="orchestration_core_table_coverage",
            status="passed" if covered_tables == expected_tables else "failed",
            expected_value="canonical core ingestion table order",
            actual_value=str(len(covered_tables)),
            details={"covered_tables": covered_tables, "expected_tables": expected_tables},
        ),
        QualityGateResult(
            gate_name="orchestration_task_ids_unique",
            status="passed" if len(task_ids) == len(set(task_ids)) else "failed",
            expected_value=str(len(task_ids)),
            actual_value=str(len(set(task_ids))),
            details={"task_ids": task_ids},
        ),
        QualityGateResult(
            gate_name="orchestration_source_batch_ids_unique",
            status="passed" if len(batch_ids) == len(set(batch_ids)) else "failed",
            expected_value=str(len(batch_ids)),
            actual_value=str(len(set(batch_ids))),
            details={"source_batch_ids": batch_ids},
        ),
        QualityGateResult(
            gate_name="orchestration_no_side_effects",
            status="passed" if not side_effect_violations else "failed",
            expected_value="0",
            actual_value=str(len(side_effect_violations)),
            details={"violations": side_effect_violations},
        ),
        QualityGateResult(
            gate_name="orchestration_all_tasks_passed",
            status="passed" if all(task.passed for task in tasks) else "failed",
            expected_value="all task plans pass",
            actual_value=str(sum(1 for task in tasks if task.passed)),
            details={"failed_task_ids": [task.spec.task_id for task in tasks if not task.passed]},
        ),
    ]


def sample_target_rows(spec: IngestionTaskSpec, batch_spec: BatchSpec) -> list[dict[str, Any]]:
    source = {
        "source": batch_spec.source,
        "source_batch_id": batch_spec.batch_id,
        "source_version": batch_spec.source_version,
    }
    trade_date = batch_spec.trade_date
    if spec.table_name == "common_trade_calendar":
        return [{**source, "trade_date": trade_date, "exchange": "SSE", "is_open": True}]
    if spec.table_name == "stock_identity":
        return [{**source, "stock_identity_key": "stock:SZ:000001", "ts_code": "000001.SZ", "code": "000001", "exchange": "SZ", "name": "平安银行"}]
    if spec.table_name == "index_identity":
        return [{**source, "index_identity_key": "index:SH:000001", "ts_code": "000001.SH", "code": "000001", "exchange": "SH", "name": "上证指数"}]
    if spec.table_name == "board_identity":
        return [{**source, "board_identity_key": "board:TDX:881002", "board_code": "881002", "board_name": "煤炭开采", "board_type": "tdx_industry", "source_namespace": "TDX"}]
    if spec.table_name == "index_membership_fact":
        return [{**source, "trade_date": trade_date, "index_identity_key": "index:SH:000300", "stock_identity_key": "stock:SZ:000001", "index_code": "000300", "stock_code": "000001"}]
    if spec.table_name == "board_membership_fact":
        return [{**source, "trade_date": trade_date, "board_identity_key": "board:TDX:881002", "stock_identity_key": "stock:SZ:000001", "board_code": "881002", "board_type": "tdx_industry", "stock_code": "000001"}]
    if spec.table_name == "stock_daily_bar_fact":
        return [{**source, "stock_identity_key": "stock:SZ:000001", "trade_date": trade_date, "ts_code": "000001.SZ", "code": "000001", "exchange": "SZ", "open": "1", "high": "2", "low": "1", "close": "2", "official_daily_proof": True, "adjust_type": "qfq"}]
    if spec.table_name == "stock_daily_basic":
        return [{**source, "stock_identity_key": "stock:SZ:000001", "trade_date": trade_date, "ts_code": "000001.SZ", "code": "000001", "exchange": "SZ", "pe": "6.5", "pb": "0.7", "total_mv": "1000000"}]
    if spec.table_name == "index_daily_bar_fact":
        return [{**source, "index_identity_key": "index:SH:000001", "trade_date": trade_date, "code": "000001", "exchange": "SH", "open": "1", "high": "2", "low": "1", "close": "2"}]
    if spec.table_name == "board_daily_bar_fact":
        return [{**source, "board_identity_key": "board:TDX:881002", "trade_date": trade_date, "board_code": "881002", "board_type": "tdx_industry", "open": "1", "high": "2", "low": "1", "close": "2"}]
    if spec.table_name == "stock_financial_metrics_fact":
        return [{**source, "stock_identity_key": "stock:SZ:000001", "asof_date": trade_date, "report_period": "20260331", "ts_code": "000001.SZ", "code": "000001", "exchange": "SZ", "roe": "10.5"}]
    raise IngestionValidationError(f"unsupported orchestration target table: {spec.table_name!r}")


def sample_batch_audit_row(
    spec: IngestionTaskSpec,
    batch_spec: BatchSpec,
    target_write_plan: PostgresWritePlan,
    archive_plan: ParquetArchivePlan | None,
) -> dict[str, Any]:
    return {
        "batch_id": batch_spec.batch_id,
        "trade_date": batch_spec.trade_date,
        "data_domain": spec.data_domain,
        "data_type": spec.data_type,
        "source": spec.source,
        "source_version": batch_spec.source_version,
        "source_path": spec.source_path,
        "source_params": dict(spec.source_params or {}),
        "raw_hash": target_write_plan.raw_hash,
        "row_count": target_write_plan.row_count,
        "error_count": 0,
        "quality_gate_summary": {"mode": "dry_run_plan", "archive_planned": archive_plan is not None},
        "rollback_strategy": "delete_by_source_batch_id_then_restore_previous_active_source_version",
        "status": "planned",
        "started_at": utc_now_iso(),
    }


def sample_quality_gate_rows(
    *,
    spec: IngestionTaskSpec,
    source_batch_id: str,
    source_version: str,
    gates: Sequence[QualityGateResult],
) -> list[dict[str, Any]]:
    return [
        {
            "source_batch_id": source_batch_id,
            "source_version": source_version,
            "data_domain": spec.data_domain,
            "data_type": spec.data_type,
            "gate_name": gate.gate_name,
            "severity": gate.severity,
            "status": gate.status,
            "expected_value": gate.expected_value,
            "actual_value": gate.actual_value,
            "details": dict(gate.details or {}),
        }
        for gate in gates
    ]


def validate_version(version: str) -> str:
    text = str(version).strip()
    if not text.startswith("v") or len(text) < 2 or not text[1:].isdigit():
        raise IngestionValidationError(f"version must look like vN: {version!r}")
    return text


def quality_gate_to_dict(gate: QualityGateResult) -> dict[str, Any]:
    return {
        "gate_name": gate.gate_name,
        "status": gate.status,
        "severity": gate.severity,
        "expected_value": gate.expected_value,
        "actual_value": gate.actual_value,
        "details": dict(gate.details or {}),
    }
