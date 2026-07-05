"""Top-level raw-ingestion dry-run control report.

This module composes the initial backfill and daily incremental dry-run plans,
execution checklists, and acceptance checklists. It never calls external APIs,
reads local TDX files, connects PostgreSQL, executes SQL, writes Parquet, or
creates files under the data root.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ashare_v3.ingestion.backfill_config import DEFAULT_INITIAL_BACKFILL_CONFIG, load_initial_backfill_config
from ashare_v3.ingestion.backfill_summary import BackfillExecutionChecklist, build_backfill_execution_checklist
from ashare_v3.ingestion.common import QualityGateResult
from ashare_v3.ingestion.daily_incremental_acceptance import DailyIncrementalAcceptanceChecklist, build_daily_incremental_acceptance_checklist
from ashare_v3.ingestion.daily_incremental_config import DEFAULT_DAILY_INCREMENTAL_CONFIG, load_daily_incremental_config
from ashare_v3.ingestion.daily_incremental_summary import DailyIncrementalExecutionChecklist, build_daily_incremental_execution_checklist
from ashare_v3.ingestion.ingestion_acceptance import IngestionAcceptanceChecklist, build_ingestion_acceptance_checklist, quality_gate_to_dict


REQUIRED_ACCEPTANCE_CATEGORIES = ("structure", "source_trace", "quality_gate", "archive", "rollback", "safety")


@dataclass(frozen=True)
class DryRunStageReport:
    stage_id: str
    stage_kind: str
    start_date: str | None
    end_date: str | None
    trade_date: str | None
    version: str
    batch_count: int
    task_count: int
    table_count: int
    acceptance_item_count: int
    category_counts: Mapping[str, int]
    domain_counts: Mapping[str, int]
    archive_dataset_count: int
    rollback_group_count: int
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "stage_kind": self.stage_kind,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "trade_date": self.trade_date,
            "version": self.version,
            "batch_count": self.batch_count,
            "task_count": self.task_count,
            "table_count": self.table_count,
            "acceptance_item_count": self.acceptance_item_count,
            "category_counts": dict(self.category_counts),
            "domain_counts": dict(self.domain_counts),
            "archive_dataset_count": self.archive_dataset_count,
            "rollback_group_count": self.rollback_group_count,
            "passed": self.passed,
        }


@dataclass(frozen=True)
class IngestionDryRunControlReport:
    initial_config_path: str
    daily_config_path: str
    initial_backfill: DryRunStageReport
    daily_incremental: DryRunStageReport
    quality_gates: tuple[QualityGateResult, ...]
    will_call_external_sources: bool = False
    will_read_tdx_files: bool = False
    will_connect_database: bool = False
    will_execute_sql: bool = False
    will_write_data_files: bool = False

    @property
    def passed(self) -> bool:
        return self.initial_backfill.passed and self.daily_incremental.passed and all(gate.passed for gate in self.quality_gates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_config_path": self.initial_config_path,
            "daily_config_path": self.daily_config_path,
            "passed": self.passed,
            "initial_backfill": self.initial_backfill.to_dict(),
            "daily_incremental": self.daily_incremental.to_dict(),
            "quality_gates": [quality_gate_to_dict(gate) for gate in self.quality_gates],
            "side_effects": {
                "will_call_external_sources": self.will_call_external_sources,
                "will_read_tdx_files": self.will_read_tdx_files,
                "will_connect_database": self.will_connect_database,
                "will_execute_sql": self.will_execute_sql,
                "will_write_data_files": self.will_write_data_files,
            },
        }


def build_ingestion_dry_run_control_report(
    *,
    initial_config_path: str | Path = DEFAULT_INITIAL_BACKFILL_CONFIG,
    daily_config_path: str | Path = DEFAULT_DAILY_INCREMENTAL_CONFIG,
) -> IngestionDryRunControlReport:
    initial_config = load_initial_backfill_config(initial_config_path)
    initial_summary = build_backfill_execution_checklist(initial_config.to_plan())
    initial_acceptance = build_ingestion_acceptance_checklist(initial_summary)

    daily_config = load_daily_incremental_config(daily_config_path)
    daily_summary = build_daily_incremental_execution_checklist(daily_config.to_plan(), source_configs=daily_config.sources)
    daily_acceptance = build_daily_incremental_acceptance_checklist(daily_summary)

    initial_stage = build_initial_stage_report(initial_summary, initial_acceptance)
    daily_stage = build_daily_stage_report(daily_summary, daily_acceptance)
    gates = tuple(build_control_quality_gates(initial_summary, initial_acceptance, daily_summary, daily_acceptance))

    return IngestionDryRunControlReport(
        initial_config_path=str(initial_config_path),
        daily_config_path=str(daily_config_path),
        initial_backfill=initial_stage,
        daily_incremental=daily_stage,
        quality_gates=gates,
    )


def build_initial_stage_report(
    summary: BackfillExecutionChecklist,
    acceptance: IngestionAcceptanceChecklist,
) -> DryRunStageReport:
    return DryRunStageReport(
        stage_id="initial_backfill",
        stage_kind="initial_backfill",
        start_date=summary.start_date,
        end_date=summary.end_date,
        trade_date=None,
        version=summary.version,
        batch_count=summary.batch_count,
        task_count=summary.batch_count,
        table_count=len(summary.table_summaries),
        acceptance_item_count=len(acceptance.acceptance_items),
        category_counts=acceptance.category_counts,
        domain_counts=summary.domain_counts,
        archive_dataset_count=sum(1 for table in summary.table_summaries if table.archive_dataset),
        rollback_group_count=len(summary.rollback_groups),
        passed=summary.passed and acceptance.passed,
    )


def build_daily_stage_report(
    summary: DailyIncrementalExecutionChecklist,
    acceptance: DailyIncrementalAcceptanceChecklist,
) -> DryRunStageReport:
    return DryRunStageReport(
        stage_id="daily_incremental",
        stage_kind="daily_incremental",
        start_date=None,
        end_date=None,
        trade_date=summary.trade_date,
        version=summary.version,
        batch_count=summary.task_count,
        task_count=summary.task_count,
        table_count=len(summary.table_summaries),
        acceptance_item_count=len(acceptance.acceptance_items),
        category_counts=acceptance.category_counts,
        domain_counts=summary.domain_counts,
        archive_dataset_count=sum(1 for table in summary.table_summaries if table.archive_dataset),
        rollback_group_count=len(summary.rollback_groups),
        passed=summary.passed and acceptance.passed,
    )


def build_control_quality_gates(
    initial_summary: BackfillExecutionChecklist,
    initial_acceptance: IngestionAcceptanceChecklist,
    daily_summary: DailyIncrementalExecutionChecklist,
    daily_acceptance: DailyIncrementalAcceptanceChecklist,
) -> list[QualityGateResult]:
    side_effect_violations = collect_side_effect_violations(initial_summary, initial_acceptance, daily_summary, daily_acceptance)
    combined_tables = [table.target_table for table in initial_summary.table_summaries] + [table.target_table for table in daily_summary.table_summaries]
    category_counts = Counter(initial_acceptance.category_counts) + Counter(daily_acceptance.category_counts)
    return [
        QualityGateResult(
            gate_name="control_initial_backfill_passed",
            status="passed" if initial_summary.passed and initial_acceptance.passed else "failed",
            expected_value="initial summary and acceptance passed",
            actual_value=f"{initial_summary.passed}/{initial_acceptance.passed}",
            details={"batch_count": initial_summary.batch_count},
        ),
        QualityGateResult(
            gate_name="control_daily_incremental_passed",
            status="passed" if daily_summary.passed and daily_acceptance.passed else "failed",
            expected_value="daily summary and acceptance passed",
            actual_value=f"{daily_summary.passed}/{daily_acceptance.passed}",
            details={"task_count": daily_summary.task_count},
        ),
        QualityGateResult(
            gate_name="control_daily_after_backfill",
            status="passed" if daily_summary.trade_date > initial_summary.end_date else "failed",
            expected_value=f"daily trade_date > {initial_summary.end_date}",
            actual_value=daily_summary.trade_date,
            details={"backfill_end_date": initial_summary.end_date},
        ),
        QualityGateResult(
            gate_name="control_source_trace_coverage",
            status="passed" if initial_summary.batch_count == 211 and daily_summary.task_count == 11 else "failed",
            expected_value="211 initial batches and 11 daily tasks",
            actual_value=f"{initial_summary.batch_count}/{daily_summary.task_count}",
            details={"initial_domain_counts": initial_summary.domain_counts, "daily_domain_counts": daily_summary.domain_counts},
        ),
        QualityGateResult(
            gate_name="control_physical_tables_split",
            status="passed" if "daily_bar_fact" not in combined_tables and all(table.startswith(("common_", "stock_", "index_", "board_")) for table in combined_tables) else "failed",
            expected_value="stock/index/board/common physical tables only",
            actual_value=str(len(combined_tables)),
            details={"target_tables": combined_tables},
        ),
        QualityGateResult(
            gate_name="control_acceptance_categories_present",
            status="passed" if all(category in initial_acceptance.category_counts and category in daily_acceptance.category_counts for category in REQUIRED_ACCEPTANCE_CATEGORIES) else "failed",
            expected_value="/".join(REQUIRED_ACCEPTANCE_CATEGORIES),
            actual_value=",".join(sorted(category_counts)),
            details={"combined_category_counts": dict(category_counts)},
        ),
        QualityGateResult(
            gate_name="control_no_side_effects",
            status="passed" if not side_effect_violations else "failed",
            expected_value="no source calls, no TDX reads, no DB, no SQL, no data file writes",
            actual_value=str(len(side_effect_violations)),
            details={"violations": side_effect_violations},
        ),
    ]


def collect_side_effect_violations(*objects: Any) -> list[str]:
    flag_names = (
        "will_call_external_sources",
        "will_read_tdx_files",
        "will_connect_database",
        "will_execute_sql",
        "will_write_data_files",
    )
    violations: list[str] = []
    for obj in objects:
        for flag_name in flag_names:
            if getattr(obj, flag_name, False):
                violations.append(f"{obj.__class__.__name__}.{flag_name}")
    return violations
