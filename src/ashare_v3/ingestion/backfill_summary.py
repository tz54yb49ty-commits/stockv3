"""Execution checklist summaries for initial backfill dry-run plans.

This module only summarizes an already-built backfill plan. It never calls
external APIs, reads local TDX files, connects PostgreSQL, executes SQL, writes
Parquet, or creates files under the data root.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Sequence

from ashare_v3.ingestion.backfill_plan import BackfillBatchPlan, InitialBackfillPlan, quality_gate_to_dict
from ashare_v3.ingestion.common import QualityGateResult


@dataclass(frozen=True)
class BackfillTableSummary:
    target_table: str
    data_domain: str
    data_type: str
    source: str
    slice_kinds: tuple[str, ...]
    batch_count: int
    start_date: str
    end_date: str
    first_source_batch_id: str
    last_source_batch_id: str
    source_versions: tuple[str, ...]
    archive_dataset: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_table": self.target_table,
            "data_domain": self.data_domain,
            "data_type": self.data_type,
            "source": self.source,
            "slice_kinds": list(self.slice_kinds),
            "batch_count": self.batch_count,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "first_source_batch_id": self.first_source_batch_id,
            "last_source_batch_id": self.last_source_batch_id,
            "source_versions": list(self.source_versions),
            "archive_dataset": self.archive_dataset,
        }


@dataclass(frozen=True)
class BackfillSourceVersionGroup:
    source_version: str
    target_table: str
    data_domain: str
    data_type: str
    slice_kind: str
    batch_count: int
    first_source_batch_id: str
    last_source_batch_id: str
    source_batch_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_version": self.source_version,
            "target_table": self.target_table,
            "data_domain": self.data_domain,
            "data_type": self.data_type,
            "slice_kind": self.slice_kind,
            "batch_count": self.batch_count,
            "first_source_batch_id": self.first_source_batch_id,
            "last_source_batch_id": self.last_source_batch_id,
            "source_batch_ids": list(self.source_batch_ids),
        }


@dataclass(frozen=True)
class BackfillRollbackGroup:
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
class BackfillExecutionChecklist:
    start_date: str
    end_date: str
    snapshot_date: str
    version: str
    data_root: str
    monthly_period_count: int
    batch_count: int
    domain_counts: dict[str, int]
    slice_kind_counts: dict[str, int]
    table_summaries: tuple[BackfillTableSummary, ...]
    activation_groups: tuple[BackfillSourceVersionGroup, ...]
    rollback_groups: tuple[BackfillRollbackGroup, ...]
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
            "start_date": self.start_date,
            "end_date": self.end_date,
            "snapshot_date": self.snapshot_date,
            "version": self.version,
            "data_root": self.data_root,
            "monthly_period_count": self.monthly_period_count,
            "batch_count": self.batch_count,
            "passed": self.passed,
            "domain_counts": dict(self.domain_counts),
            "slice_kind_counts": dict(self.slice_kind_counts),
            "table_summaries": [summary.to_dict() for summary in self.table_summaries],
            "activation_groups": [group.to_dict() for group in self.activation_groups],
            "rollback_groups": [group.to_dict() for group in self.rollback_groups],
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


def build_backfill_execution_checklist(plan: InitialBackfillPlan) -> BackfillExecutionChecklist:
    table_summaries = tuple(build_table_summaries(plan.batches))
    activation_groups = tuple(build_activation_groups(plan.batches))
    rollback_groups = tuple(build_rollback_groups(activation_groups))
    domain_counts = dict(Counter(batch.spec.data_domain for batch in plan.batches))
    slice_kind_counts = dict(Counter(batch.spec.slice_kind for batch in plan.batches))
    execution_order = tuple(batch.source_batch_id for batch in plan.batches)
    quality_gates = tuple(
        build_summary_quality_gates(
            plan=plan,
            table_summaries=table_summaries,
            activation_groups=activation_groups,
            rollback_groups=rollback_groups,
            domain_counts=domain_counts,
            slice_kind_counts=slice_kind_counts,
        )
    )

    return BackfillExecutionChecklist(
        start_date=plan.start_date,
        end_date=plan.end_date,
        snapshot_date=plan.snapshot_date,
        version=plan.version,
        data_root=plan.data_root,
        monthly_period_count=len(plan.monthly_periods),
        batch_count=plan.batch_count,
        domain_counts=domain_counts,
        slice_kind_counts=slice_kind_counts,
        table_summaries=table_summaries,
        activation_groups=activation_groups,
        rollback_groups=rollback_groups,
        execution_order=execution_order,
        quality_gates=quality_gates,
    )


def build_table_summaries(batches: Sequence[BackfillBatchPlan]) -> list[BackfillTableSummary]:
    grouped = group_batches_by(batches, lambda batch: batch.spec.table_name)
    summaries: list[BackfillTableSummary] = []
    for table_batches in grouped:
        first = table_batches[0]
        summaries.append(
            BackfillTableSummary(
                target_table=first.spec.table_name,
                data_domain=first.spec.data_domain,
                data_type=first.spec.data_type,
                source=first.spec.source,
                slice_kinds=unique_in_order(batch.spec.slice_kind for batch in table_batches),
                batch_count=len(table_batches),
                start_date=min(batch.start_date for batch in table_batches),
                end_date=max(batch.end_date for batch in table_batches),
                first_source_batch_id=table_batches[0].source_batch_id,
                last_source_batch_id=table_batches[-1].source_batch_id,
                source_versions=unique_in_order(batch.source_version for batch in table_batches),
                archive_dataset=first.archive_dataset,
            )
        )
    return summaries


def build_activation_groups(batches: Sequence[BackfillBatchPlan]) -> list[BackfillSourceVersionGroup]:
    grouped = group_batches_by(batches, lambda batch: batch.source_version)
    groups: list[BackfillSourceVersionGroup] = []
    for version_batches in grouped:
        first = version_batches[0]
        groups.append(
            BackfillSourceVersionGroup(
                source_version=first.source_version,
                target_table=first.spec.table_name,
                data_domain=first.spec.data_domain,
                data_type=first.spec.data_type,
                slice_kind=first.spec.slice_kind,
                batch_count=len(version_batches),
                first_source_batch_id=version_batches[0].source_batch_id,
                last_source_batch_id=version_batches[-1].source_batch_id,
                source_batch_ids=tuple(batch.source_batch_id for batch in version_batches),
            )
        )
    return groups


def build_rollback_groups(activation_groups: Sequence[BackfillSourceVersionGroup]) -> list[BackfillRollbackGroup]:
    return [
        BackfillRollbackGroup(
            group_id=f"{group.data_type}:{group.source_version}",
            source_version=group.source_version,
            target_table=group.target_table,
            data_domain=group.data_domain,
            data_type=group.data_type,
            source_batch_count=group.batch_count,
            source_batch_ids=group.source_batch_ids,
            rollback_strategy="delete_all_source_batch_ids_then_restore_previous_active_source_version",
        )
        for group in activation_groups
    ]


def build_summary_quality_gates(
    *,
    plan: InitialBackfillPlan,
    table_summaries: Sequence[BackfillTableSummary],
    activation_groups: Sequence[BackfillSourceVersionGroup],
    rollback_groups: Sequence[BackfillRollbackGroup],
    domain_counts: dict[str, int],
    slice_kind_counts: dict[str, int],
) -> list[QualityGateResult]:
    tables = [summary.target_table for summary in table_summaries]
    source_batch_ids = [batch.source_batch_id for batch in plan.batches]
    membership_summaries = [
        summary
        for summary in table_summaries
        if summary.data_type in {"index_membership", "board_membership"}
    ]
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
            gate_name="backfill_summary_plan_passed",
            status="passed" if plan.passed else "failed",
            expected_value="plan.passed=true",
            actual_value=str(plan.passed).lower(),
            details={},
        ),
        QualityGateResult(
            gate_name="backfill_summary_batch_count_matches",
            status="passed" if sum(domain_counts.values()) == plan.batch_count else "failed",
            expected_value=str(plan.batch_count),
            actual_value=str(sum(domain_counts.values())),
            details={"domain_counts": domain_counts},
        ),
        QualityGateResult(
            gate_name="backfill_summary_slice_count_matches",
            status="passed" if sum(slice_kind_counts.values()) == plan.batch_count else "failed",
            expected_value=str(plan.batch_count),
            actual_value=str(sum(slice_kind_counts.values())),
            details={"slice_kind_counts": slice_kind_counts},
        ),
        QualityGateResult(
            gate_name="backfill_summary_source_batch_ids_unique",
            status="passed" if len(source_batch_ids) == len(set(source_batch_ids)) else "failed",
            expected_value=str(len(source_batch_ids)),
            actual_value=str(len(set(source_batch_ids))),
            details={},
        ),
        QualityGateResult(
            gate_name="backfill_summary_physical_tables_split",
            status="passed" if "daily_bar_fact" not in tables and all(summary.target_table.startswith(f"{summary.data_domain}_") for summary in table_summaries) else "failed",
            expected_value="stock/index/board/common physical tables only",
            actual_value=str(len(tables)),
            details={"tables": tables},
        ),
        QualityGateResult(
            gate_name="backfill_summary_membership_snapshot_only",
            status="passed" if all(summary.start_date == plan.snapshot_date and summary.end_date == plan.snapshot_date and summary.batch_count == 1 for summary in membership_summaries) else "failed",
            expected_value="membership summaries are snapshot only",
            actual_value=str(len(membership_summaries)),
            details={"membership_tables": [summary.target_table for summary in membership_summaries]},
        ),
        QualityGateResult(
            gate_name="backfill_summary_activation_groups_complete",
            status="passed" if len(activation_groups) == len(table_summaries) else "failed",
            expected_value=str(len(table_summaries)),
            actual_value=str(len(activation_groups)),
            details={"source_versions": [group.source_version for group in activation_groups]},
        ),
        QualityGateResult(
            gate_name="backfill_summary_rollback_groups_complete",
            status="passed" if len(rollback_groups) == len(activation_groups) and sum(group.source_batch_count for group in rollback_groups) == plan.batch_count else "failed",
            expected_value=f"{len(activation_groups)} groups / {plan.batch_count} batches",
            actual_value=f"{len(rollback_groups)} groups / {sum(group.source_batch_count for group in rollback_groups)} batches",
            details={},
        ),
        QualityGateResult(
            gate_name="backfill_summary_no_side_effects",
            status="passed" if not side_effect_violations else "failed",
            expected_value="0",
            actual_value=str(len(side_effect_violations)),
            details={"violations": side_effect_violations},
        ),
    ]


def group_batches_by(
    batches: Sequence[BackfillBatchPlan],
    key_func,
) -> list[list[BackfillBatchPlan]]:
    grouped: dict[str, list[BackfillBatchPlan]] = {}
    order: list[str] = []
    for batch in batches:
        key = str(key_func(batch))
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(batch)
    return [grouped[key] for key in order]


def unique_in_order(values) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = str(value)
        if text not in seen:
            seen.add(text)
            ordered.append(text)
    return tuple(ordered)
