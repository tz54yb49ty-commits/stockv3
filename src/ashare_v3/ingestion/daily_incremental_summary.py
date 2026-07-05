"""Execution checklist summaries for daily incremental dry-run plans.

This module only summarizes an already-built daily ingestion plan. It never
calls external APIs, reads local TDX files, connects PostgreSQL, executes SQL,
writes Parquet, or creates files under the data root.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ashare_v3.ingestion.batch_orchestration import DailyIngestionOrchestrationPlan, IngestionOrchestrationTaskPlan, quality_gate_to_dict
from ashare_v3.ingestion.common import QualityGateResult


EXPECTED_DAILY_DOMAIN_COUNTS = {"common": 1, "stock": 4, "index": 3, "board": 3}
DAILY_TDX_REFRESH_TASK_IDS = ("board_identity", "index_membership", "board_membership")


@dataclass(frozen=True)
class DailyIncrementalTableSummary:
    task_id: str
    target_table: str
    data_domain: str
    data_type: str
    source: str
    dependencies: tuple[str, ...]
    source_batch_id: str
    source_version: str
    refresh_policy: str | None
    archive_dataset: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "target_table": self.target_table,
            "data_domain": self.data_domain,
            "data_type": self.data_type,
            "source": self.source,
            "dependencies": list(self.dependencies),
            "source_batch_id": self.source_batch_id,
            "source_version": self.source_version,
            "refresh_policy": self.refresh_policy,
            "archive_dataset": self.archive_dataset,
        }


@dataclass(frozen=True)
class DailyIncrementalSourceVersionGroup:
    source_version: str
    target_table: str
    data_domain: str
    data_type: str
    source_batch_count: int
    source_batch_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_version": self.source_version,
            "target_table": self.target_table,
            "data_domain": self.data_domain,
            "data_type": self.data_type,
            "source_batch_count": self.source_batch_count,
            "source_batch_ids": list(self.source_batch_ids),
        }


@dataclass(frozen=True)
class DailyIncrementalRollbackGroup:
    group_id: str
    source_version: str
    target_table: str
    data_domain: str
    data_type: str
    source_batch_count: int
    source_batch_ids: tuple[str, ...]
    rollback_strategy: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "source_version": self.source_version,
            "target_table": self.target_table,
            "data_domain": self.data_domain,
            "data_type": self.data_type,
            "source_batch_count": self.source_batch_count,
            "source_batch_ids": list(self.source_batch_ids),
            "rollback_strategy": self.rollback_strategy,
        }


@dataclass(frozen=True)
class DailyIncrementalTdxRefreshTask:
    task_id: str
    target_table: str
    source: str
    refresh_policy: str
    source_path: str | None
    source_file: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "target_table": self.target_table,
            "source": self.source,
            "refresh_policy": self.refresh_policy,
            "source_path": self.source_path,
            "source_file": self.source_file,
        }


@dataclass(frozen=True)
class DailyIncrementalExecutionChecklist:
    trade_date: str
    version: str
    data_root: str
    task_count: int
    domain_counts: dict[str, int]
    table_summaries: tuple[DailyIncrementalTableSummary, ...]
    activation_groups: tuple[DailyIncrementalSourceVersionGroup, ...]
    rollback_groups: tuple[DailyIncrementalRollbackGroup, ...]
    tdx_refresh_tasks: tuple[DailyIncrementalTdxRefreshTask, ...]
    execution_order: tuple[str, ...]
    quality_gates: tuple[QualityGateResult, ...]
    will_call_external_sources: bool = False
    will_read_tdx_files: bool = False
    will_connect_database: bool = False
    will_execute_sql: bool = False
    will_write_data_files: bool = False

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.quality_gates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "version": self.version,
            "data_root": self.data_root,
            "task_count": self.task_count,
            "passed": self.passed,
            "domain_counts": dict(self.domain_counts),
            "table_summaries": [summary.to_dict() for summary in self.table_summaries],
            "activation_groups": [group.to_dict() for group in self.activation_groups],
            "rollback_groups": [group.to_dict() for group in self.rollback_groups],
            "tdx_refresh_tasks": [task.to_dict() for task in self.tdx_refresh_tasks],
            "execution_order": list(self.execution_order),
            "quality_gates": [quality_gate_to_dict(gate) for gate in self.quality_gates],
            "side_effects": {
                "will_call_external_sources": self.will_call_external_sources,
                "will_read_tdx_files": self.will_read_tdx_files,
                "will_connect_database": self.will_connect_database,
                "will_execute_sql": self.will_execute_sql,
                "will_write_data_files": self.will_write_data_files,
            },
        }


def build_daily_incremental_execution_checklist(
    plan: DailyIngestionOrchestrationPlan,
    source_configs: Mapping[str, Mapping[str, Any]] | None = None,
) -> DailyIncrementalExecutionChecklist:
    normalized_source_configs = source_configs or {}
    table_summaries = tuple(build_table_summaries(plan.tasks, normalized_source_configs))
    activation_groups = tuple(build_activation_groups(plan.tasks))
    rollback_groups = tuple(build_rollback_groups(activation_groups))
    tdx_refresh_tasks = tuple(build_tdx_refresh_tasks(plan.tasks, normalized_source_configs))
    domain_counts = dict(Counter(task.spec.data_domain for task in plan.tasks))
    execution_order = tuple(task.spec.task_id for task in plan.tasks)
    quality_gates = tuple(
        build_summary_quality_gates(
            plan=plan,
            table_summaries=table_summaries,
            activation_groups=activation_groups,
            rollback_groups=rollback_groups,
            tdx_refresh_tasks=tdx_refresh_tasks,
            domain_counts=domain_counts,
        )
    )

    return DailyIncrementalExecutionChecklist(
        trade_date=plan.trade_date,
        version=plan.version,
        data_root=plan.data_root,
        task_count=len(plan.tasks),
        domain_counts=domain_counts,
        table_summaries=table_summaries,
        activation_groups=activation_groups,
        rollback_groups=rollback_groups,
        tdx_refresh_tasks=tdx_refresh_tasks,
        execution_order=execution_order,
        quality_gates=quality_gates,
    )


def build_table_summaries(
    tasks: Sequence[IngestionOrchestrationTaskPlan],
    source_configs: Mapping[str, Mapping[str, Any]],
) -> list[DailyIncrementalTableSummary]:
    summaries: list[DailyIncrementalTableSummary] = []
    for task in tasks:
        source_config = source_configs.get(task.spec.task_id, {})
        summaries.append(
            DailyIncrementalTableSummary(
                task_id=task.spec.task_id,
                target_table=task.spec.table_name,
                data_domain=task.spec.data_domain,
                data_type=task.spec.data_type,
                source=task.spec.source,
                dependencies=tuple(task.spec.dependencies),
                source_batch_id=task.batch_spec.batch_id,
                source_version=task.batch_spec.source_version,
                refresh_policy=optional_string(source_config.get("refresh_policy")),
                archive_dataset=task.archive_plan.dataset if task.archive_plan else None,
            )
        )
    return summaries


def build_activation_groups(
    tasks: Sequence[IngestionOrchestrationTaskPlan],
) -> list[DailyIncrementalSourceVersionGroup]:
    grouped = group_tasks_by(tasks, lambda task: task.batch_spec.source_version)
    groups: list[DailyIncrementalSourceVersionGroup] = []
    for version_tasks in grouped:
        first = version_tasks[0]
        groups.append(
            DailyIncrementalSourceVersionGroup(
                source_version=first.batch_spec.source_version,
                target_table=first.spec.table_name,
                data_domain=first.spec.data_domain,
                data_type=first.spec.data_type,
                source_batch_count=len(version_tasks),
                source_batch_ids=tuple(task.batch_spec.batch_id for task in version_tasks),
            )
        )
    return groups


def build_rollback_groups(
    activation_groups: Sequence[DailyIncrementalSourceVersionGroup],
) -> list[DailyIncrementalRollbackGroup]:
    return [
        DailyIncrementalRollbackGroup(
            group_id=f"{group.data_type}:{group.source_version}",
            source_version=group.source_version,
            target_table=group.target_table,
            data_domain=group.data_domain,
            data_type=group.data_type,
            source_batch_count=group.source_batch_count,
            source_batch_ids=group.source_batch_ids,
            rollback_strategy="delete_source_batch_id_then_restore_previous_active_source_version",
        )
        for group in activation_groups
    ]


def build_tdx_refresh_tasks(
    tasks: Sequence[IngestionOrchestrationTaskPlan],
    source_configs: Mapping[str, Mapping[str, Any]],
) -> list[DailyIncrementalTdxRefreshTask]:
    refresh_tasks: list[DailyIncrementalTdxRefreshTask] = []
    for task in tasks:
        source_config = source_configs.get(task.spec.task_id, {})
        refresh_policy = str(source_config.get("refresh_policy") or "")
        should_refresh_from_config = refresh_policy == "daily_read_local_txt"
        should_refresh_from_plan = not source_configs and task.spec.task_id in DAILY_TDX_REFRESH_TASK_IDS
        if not should_refresh_from_config and not should_refresh_from_plan:
            continue

        refresh_tasks.append(
            DailyIncrementalTdxRefreshTask(
                task_id=task.spec.task_id,
                target_table=task.spec.table_name,
                source=task.spec.source,
                refresh_policy=refresh_policy or "daily_read_local_txt",
                source_path=task.spec.source_path or optional_string(source_config.get("source_path_key")),
                source_file=optional_string(source_config.get("source_file")),
            )
        )
    return refresh_tasks


def build_summary_quality_gates(
    *,
    plan: DailyIngestionOrchestrationPlan,
    table_summaries: Sequence[DailyIncrementalTableSummary],
    activation_groups: Sequence[DailyIncrementalSourceVersionGroup],
    rollback_groups: Sequence[DailyIncrementalRollbackGroup],
    tdx_refresh_tasks: Sequence[DailyIncrementalTdxRefreshTask],
    domain_counts: dict[str, int],
) -> list[QualityGateResult]:
    tables = [summary.target_table for summary in table_summaries]
    source_batch_ids = [summary.source_batch_id for summary in table_summaries]
    expected_suffix = f"_{plan.trade_date}_{plan.version}"
    source_versions = [summary.source_version for summary in table_summaries]
    side_effect_violations = []
    if any(
        (
            plan.will_call_external_sources,
            plan.will_read_tdx_files,
            plan.will_connect_database,
            plan.will_execute_sql,
            plan.will_write_data_files,
        )
    ):
        side_effect_violations.append("plan")

    return [
        QualityGateResult(
            gate_name="daily_summary_plan_passed",
            status="passed" if plan.passed else "failed",
            expected_value="plan.passed=true",
            actual_value=str(plan.passed).lower(),
            details={},
        ),
        QualityGateResult(
            gate_name="daily_summary_task_count",
            status="passed" if len(table_summaries) == 11 else "failed",
            expected_value="11",
            actual_value=str(len(table_summaries)),
            details={"task_ids": [summary.task_id for summary in table_summaries]},
        ),
        QualityGateResult(
            gate_name="daily_summary_domain_counts",
            status="passed" if domain_counts == EXPECTED_DAILY_DOMAIN_COUNTS else "failed",
            expected_value=str(EXPECTED_DAILY_DOMAIN_COUNTS),
            actual_value=str(domain_counts),
            details={"domain_counts": domain_counts},
        ),
        QualityGateResult(
            gate_name="daily_summary_source_batch_ids_unique",
            status="passed" if len(source_batch_ids) == len(set(source_batch_ids)) else "failed",
            expected_value=str(len(source_batch_ids)),
            actual_value=str(len(set(source_batch_ids))),
            details={},
        ),
        QualityGateResult(
            gate_name="daily_summary_source_versions_single_day",
            status="passed" if all(version.endswith(expected_suffix) for version in source_versions) else "failed",
            expected_value=expected_suffix,
            actual_value=str(len([version for version in source_versions if version.endswith(expected_suffix)])),
            details={"source_versions": source_versions},
        ),
        QualityGateResult(
            gate_name="daily_summary_physical_tables_split",
            status="passed" if "daily_bar_fact" not in tables and all(summary.target_table.startswith(f"{summary.data_domain}_") for summary in table_summaries) else "failed",
            expected_value="stock/index/board/common physical tables only",
            actual_value=str(len(tables)),
            details={"tables": tables},
        ),
        QualityGateResult(
            gate_name="daily_summary_tdx_refresh_tasks_present",
            status="passed" if tuple(task.task_id for task in tdx_refresh_tasks) == DAILY_TDX_REFRESH_TASK_IDS else "failed",
            expected_value=str(DAILY_TDX_REFRESH_TASK_IDS),
            actual_value=str(tuple(task.task_id for task in tdx_refresh_tasks)),
            details={"target_tables": [task.target_table for task in tdx_refresh_tasks]},
        ),
        QualityGateResult(
            gate_name="daily_summary_activation_groups_complete",
            status="passed" if len(activation_groups) == len(table_summaries) else "failed",
            expected_value=str(len(table_summaries)),
            actual_value=str(len(activation_groups)),
            details={"source_versions": [group.source_version for group in activation_groups]},
        ),
        QualityGateResult(
            gate_name="daily_summary_rollback_groups_complete",
            status="passed" if len(rollback_groups) == len(activation_groups) and sum(group.source_batch_count for group in rollback_groups) == len(table_summaries) else "failed",
            expected_value=f"{len(activation_groups)} groups / {len(table_summaries)} batches",
            actual_value=f"{len(rollback_groups)} groups / {sum(group.source_batch_count for group in rollback_groups)} batches",
            details={},
        ),
        QualityGateResult(
            gate_name="daily_summary_no_side_effects",
            status="passed" if not side_effect_violations else "failed",
            expected_value="0",
            actual_value=str(len(side_effect_violations)),
            details={"violations": side_effect_violations},
        ),
    ]


def group_tasks_by(
    tasks: Sequence[IngestionOrchestrationTaskPlan],
    key_func,
) -> list[list[IngestionOrchestrationTaskPlan]]:
    grouped: dict[str, list[IngestionOrchestrationTaskPlan]] = {}
    order: list[str] = []
    for task in tasks:
        key = str(key_func(task))
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(task)
    return [grouped[key] for key in order]


def optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
