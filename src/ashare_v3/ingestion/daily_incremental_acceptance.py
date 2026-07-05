"""Daily incremental raw-ingestion acceptance checklist dry-run planning.

This module turns the daily incremental execution checklist into explicit
acceptance items. It never calls external APIs, reads local TDX files, connects
PostgreSQL, executes SQL, writes Parquet, or creates files under the data root.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Sequence

from ashare_v3.ingestion.common import QualityGateResult
from ashare_v3.ingestion.daily_incremental_summary import DAILY_TDX_REFRESH_TASK_IDS, EXPECTED_DAILY_DOMAIN_COUNTS, DailyIncrementalExecutionChecklist
from ashare_v3.ingestion.ingestion_acceptance import AcceptanceItem, quality_gate_to_dict


@dataclass(frozen=True)
class DailyIncrementalAcceptanceChecklist:
    trade_date: str
    version: str
    task_count: int
    acceptance_items: tuple[AcceptanceItem, ...]
    quality_gates: tuple[QualityGateResult, ...]
    will_call_external_sources: bool = False
    will_read_tdx_files: bool = False
    will_connect_database: bool = False
    will_execute_sql: bool = False
    will_write_data_files: bool = False

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.acceptance_items) and all(gate.passed for gate in self.quality_gates)

    @property
    def category_counts(self) -> dict[str, int]:
        return dict(Counter(item.category for item in self.acceptance_items))

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "version": self.version,
            "task_count": self.task_count,
            "passed": self.passed,
            "category_counts": self.category_counts,
            "acceptance_items": [item.to_dict() for item in self.acceptance_items],
            "quality_gates": [quality_gate_to_dict(gate) for gate in self.quality_gates],
            "side_effects": {
                "will_call_external_sources": self.will_call_external_sources,
                "will_read_tdx_files": self.will_read_tdx_files,
                "will_connect_database": self.will_connect_database,
                "will_execute_sql": self.will_execute_sql,
                "will_write_data_files": self.will_write_data_files,
            },
        }


def build_daily_incremental_acceptance_checklist(
    summary: DailyIncrementalExecutionChecklist,
) -> DailyIncrementalAcceptanceChecklist:
    items = tuple(build_daily_acceptance_items(summary))
    gates = tuple(build_daily_acceptance_quality_gates(summary, items))
    return DailyIncrementalAcceptanceChecklist(
        trade_date=summary.trade_date,
        version=summary.version,
        task_count=summary.task_count,
        acceptance_items=items,
        quality_gates=gates,
    )


def build_daily_acceptance_items(summary: DailyIncrementalExecutionChecklist) -> list[AcceptanceItem]:
    tables = {table.target_table: table for table in summary.table_summaries}
    activation_groups = {group.source_version: group for group in summary.activation_groups}
    rollback_groups = {group.source_version: group for group in summary.rollback_groups}
    data_domains = set(summary.domain_counts)
    source_batch_total = sum(group.source_batch_count for group in summary.rollback_groups)
    expected_daily_versions = {table.source_version for table in summary.table_summaries}
    tdx_refresh_task_ids = tuple(task.task_id for task in summary.tdx_refresh_tasks)
    tdx_refresh_tables = tuple(task.target_table for task in summary.tdx_refresh_tasks)
    archive_datasets = [table.archive_dataset for table in summary.table_summaries if table.archive_dataset]
    item_specs = [
        (
            "structure.physical_split",
            "structure",
            "Daily stock/index/board/common target tables are physically separated.",
            "No mixed daily_bar_fact table; all target tables use domain prefix.",
            "passed" if "daily_bar_fact" not in tables and all(table.target_table.startswith(f"{table.data_domain}_") for table in summary.table_summaries) else "failed",
            {"target_tables": sorted(tables)},
        ),
        (
            "structure.core_task_coverage",
            "structure",
            "All approved daily raw-ingestion tasks are represented.",
            "11 daily target tasks",
            "passed" if summary.task_count == 11 and len(tables) == 11 else "failed",
            {"task_count": summary.task_count, "target_tables": list(tables)},
        ),
        (
            "structure.daily_basic_separate",
            "structure",
            "stock_daily_basic is planned as its own stock table for daily ingestion.",
            "stock_daily_basic exists and is not merged into stock_daily_bar_fact",
            "passed" if "stock_daily_basic" in tables and tables["stock_daily_basic"].data_domain == "stock" else "failed",
            {"stock_daily_basic": tables.get("stock_daily_basic").to_dict() if "stock_daily_basic" in tables else None},
        ),
        (
            "source_trace.batch_count",
            "source_trace",
            "Daily incremental batch count is explicit and auditable.",
            "11 source_batch_id values",
            "passed" if summary.task_count == 11 else "failed",
            {"task_count": summary.task_count, "execution_order": list(summary.execution_order)},
        ),
        (
            "source_trace.domain_counts",
            "source_trace",
            "Domain counts match the approved daily physical split plan.",
            "common=1, stock=4, index=3, board=3",
            "passed" if summary.domain_counts == EXPECTED_DAILY_DOMAIN_COUNTS else "failed",
            {"domain_counts": summary.domain_counts},
        ),
        (
            "source_trace.single_day_source_versions",
            "source_trace",
            "Every daily source_version is scoped to the requested trade_date.",
            f"all source_version values end with _{summary.trade_date}_{summary.version}",
            "passed" if all(version.endswith(f"_{summary.trade_date}_{summary.version}") for version in expected_daily_versions) else "failed",
            {"source_versions": sorted(expected_daily_versions)},
        ),
        (
            "source_trace.tdx_refresh_tasks",
            "source_trace",
            "Daily ingestion identifies local TDX txt refresh tasks.",
            "board_identity, index_membership, board_membership",
            "passed" if tdx_refresh_task_ids == DAILY_TDX_REFRESH_TASK_IDS else "failed",
            {"tdx_refresh_task_ids": list(tdx_refresh_task_ids), "tdx_refresh_tables": list(tdx_refresh_tables)},
        ),
        (
            "quality_gate.identity_key_required",
            "quality_gate",
            "Identity-key coverage gates are required for identity and fact tables before daily activation.",
            "All stock/index/board domains appear in the daily plan.",
            "passed" if all(domain in data_domains for domain in ("stock", "index", "board")) else "failed",
            {"domains": sorted(data_domains)},
        ),
        (
            "quality_gate.membership_daily_refresh_required",
            "quality_gate",
            "Index and board membership are refreshed from local TDX txt for the daily source_version.",
            "index_membership_fact and board_membership_fact appear in TDX refresh tables",
            "passed" if {"index_membership_fact", "board_membership_fact"}.issubset(tdx_refresh_tables) else "failed",
            {"tdx_refresh_tables": list(tdx_refresh_tables)},
        ),
        (
            "quality_gate.official_daily_proof_required",
            "quality_gate",
            "Stock daily activation must require official daily and qfq proof gates.",
            "stock_daily_bar_fact is present as stock qfq daily plan",
            "passed" if tables.get("stock_daily_bar_fact") and tables["stock_daily_bar_fact"].source == "tushare.pro_bar.qfq" else "failed",
            {"stock_daily_source": tables.get("stock_daily_bar_fact").source if "stock_daily_bar_fact" in tables else None},
        ),
        (
            "quality_gate.stock_daily_basic_universe_required",
            "quality_gate",
            "stock_daily_basic must align to stock universe before daily activation.",
            "stock_daily_basic daily source_version exists",
            "passed" if "stock_daily_basic" in tables and tables["stock_daily_basic"].source_version == f"stock_daily_basic_{summary.trade_date}_{summary.version}" else "failed",
            {"source_version": tables.get("stock_daily_basic").source_version if "stock_daily_basic" in tables else None},
        ),
        (
            "quality_gate.no_code_pollution_required",
            "quality_gate",
            "Same-code and 88xxxx pollution checks are required before daily activation.",
            "stock/index/board daily table summaries exist separately",
            "passed" if all(name in tables for name in ("stock_daily_bar_fact", "index_daily_bar_fact", "board_daily_bar_fact")) else "failed",
            {"daily_tables": [name for name in ("stock_daily_bar_fact", "index_daily_bar_fact", "board_daily_bar_fact") if name in tables]},
        ),
        (
            "archive.parquet_manifest_planned",
            "archive",
            "Parquet archive manifests are planned for daily fact and membership tables.",
            "7 archive datasets",
            "passed" if len(archive_datasets) == 7 else "failed",
            {"archive_datasets": archive_datasets},
        ),
        (
            "rollback.rollback_groups_complete",
            "rollback",
            "Every daily source_version has a rollback group.",
            "rollback groups cover every source_batch_id",
            "passed" if len(rollback_groups) == len(activation_groups) and source_batch_total == summary.task_count else "failed",
            {"rollback_group_count": len(rollback_groups), "covered_batch_count": source_batch_total},
        ),
        (
            "rollback.delete_by_source_batch_id",
            "rollback",
            "Daily rollback strategy deletes by source_batch_id before restoring active source_version.",
            "All rollback groups use delete_source_batch_id_then_restore_previous_active_source_version",
            "passed" if all(group.rollback_strategy == "delete_source_batch_id_then_restore_previous_active_source_version" for group in summary.rollback_groups) else "failed",
            {"rollback_strategies": sorted({group.rollback_strategy for group in summary.rollback_groups})},
        ),
        (
            "safety.no_side_effects",
            "safety",
            "Daily acceptance checklist generation has no side effects.",
            "no source calls, no TDX reads, no DB, no SQL, no data file writes",
            "passed" if not any((summary.will_call_external_sources, summary.will_read_tdx_files, summary.will_connect_database, summary.will_execute_sql, summary.will_write_data_files)) else "failed",
            {
                "will_call_external_sources": summary.will_call_external_sources,
                "will_read_tdx_files": summary.will_read_tdx_files,
                "will_connect_database": summary.will_connect_database,
                "will_execute_sql": summary.will_execute_sql,
                "will_write_data_files": summary.will_write_data_files,
            },
        ),
        (
            "safety.forbidden_layers_absent",
            "safety",
            "Daily acceptance scope excludes condition, trigger, action, voice, sim, frontend, and real trading.",
            "only raw-ingestion target tables appear",
            "passed" if all(table.data_domain in {"common", "stock", "index", "board"} for table in summary.table_summaries) else "failed",
            {"data_domains": sorted(data_domains)},
        ),
    ]
    return [
        AcceptanceItem(
            item_id=item_id,
            category=category,
            description=description,
            expected=expected,
            actual=status,
            status=status,
            evidence=evidence,
        )
        for item_id, category, description, expected, status, evidence in item_specs
    ]


def build_daily_acceptance_quality_gates(
    summary: DailyIncrementalExecutionChecklist,
    items: Sequence[AcceptanceItem],
) -> list[QualityGateResult]:
    failed_items = [item for item in items if not item.passed]
    categories = Counter(item.category for item in items)
    return [
        QualityGateResult(
            gate_name="daily_acceptance_summary_passed",
            status="passed" if summary.passed else "failed",
            expected_value="summary.passed=true",
            actual_value=str(summary.passed).lower(),
            details={},
        ),
        QualityGateResult(
            gate_name="daily_acceptance_items_non_empty",
            status="passed" if items else "failed",
            expected_value=">0",
            actual_value=str(len(items)),
            details={},
        ),
        QualityGateResult(
            gate_name="daily_acceptance_all_items_passed",
            status="passed" if not failed_items else "failed",
            expected_value="0 failed items",
            actual_value=str(len(failed_items)),
            details={"failed_item_ids": [item.item_id for item in failed_items]},
        ),
        QualityGateResult(
            gate_name="daily_acceptance_required_categories_present",
            status="passed" if all(category in categories for category in ("structure", "source_trace", "quality_gate", "archive", "rollback", "safety")) else "failed",
            expected_value="structure/source_trace/quality_gate/archive/rollback/safety",
            actual_value=",".join(sorted(categories)),
            details={"category_counts": dict(categories)},
        ),
        QualityGateResult(
            gate_name="daily_acceptance_no_side_effects",
            status="passed" if not any((summary.will_call_external_sources, summary.will_read_tdx_files, summary.will_connect_database, summary.will_execute_sql, summary.will_write_data_files)) else "failed",
            expected_value="no runtime side effects",
            actual_value="dry_run",
            details={},
        ),
    ]
