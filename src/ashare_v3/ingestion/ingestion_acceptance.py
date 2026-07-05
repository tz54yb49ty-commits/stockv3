"""Raw-ingestion acceptance checklist dry-run planning.

This module turns the initial backfill execution checklist into explicit
acceptance items. It never calls external APIs, reads local TDX files, connects
PostgreSQL, executes SQL, writes Parquet, or creates files under the data root.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ashare_v3.ingestion.backfill_summary import BackfillExecutionChecklist
from ashare_v3.ingestion.common import QualityGateResult


@dataclass(frozen=True)
class AcceptanceItem:
    item_id: str
    category: str
    description: str
    expected: str
    actual: str
    status: str
    evidence: Mapping[str, Any]
    severity: str = "P0"

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "category": self.category,
            "description": self.description,
            "severity": self.severity,
            "status": self.status,
            "expected": self.expected,
            "actual": self.actual,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class IngestionAcceptanceChecklist:
    start_date: str
    end_date: str
    snapshot_date: str
    version: str
    batch_count: int
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
            "start_date": self.start_date,
            "end_date": self.end_date,
            "snapshot_date": self.snapshot_date,
            "version": self.version,
            "batch_count": self.batch_count,
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


def build_ingestion_acceptance_checklist(summary: BackfillExecutionChecklist) -> IngestionAcceptanceChecklist:
    items = tuple(build_acceptance_items(summary))
    gates = tuple(build_acceptance_quality_gates(summary, items))
    return IngestionAcceptanceChecklist(
        start_date=summary.start_date,
        end_date=summary.end_date,
        snapshot_date=summary.snapshot_date,
        version=summary.version,
        batch_count=summary.batch_count,
        acceptance_items=items,
        quality_gates=gates,
    )


def build_acceptance_items(summary: BackfillExecutionChecklist) -> list[AcceptanceItem]:
    tables = {table.target_table: table for table in summary.table_summaries}
    activation_groups = {group.source_version: group for group in summary.activation_groups}
    rollback_groups = {group.source_version: group for group in summary.rollback_groups}
    data_domains = set(summary.domain_counts)
    source_batch_total = sum(group.source_batch_count for group in summary.rollback_groups)
    monthly_fact_versions = {
        "stock_daily_20230101_20260521_v1",
        "stock_daily_basic_20230101_20260521_v1",
        "index_daily_20230101_20260521_v1",
        "board_daily_20230101_20260521_v1",
        "stock_financial_20230101_20260521_v1",
    }
    item_specs = [
        (
            "structure.physical_split",
            "structure",
            "stock/index/board/common target tables are physically separated.",
            "No mixed daily_bar_fact table; all target tables use domain prefix.",
            "passed" if "daily_bar_fact" not in tables and all(table.target_table.startswith(f"{table.data_domain}_") for table in summary.table_summaries) else "failed",
            {"target_tables": sorted(tables)},
        ),
        (
            "structure.core_table_coverage",
            "structure",
            "All approved core raw-ingestion tables are represented.",
            "11 target tables",
            "passed" if len(tables) == 11 else "failed",
            {"target_table_count": len(tables), "target_tables": list(tables)},
        ),
        (
            "structure.daily_basic_separate",
            "structure",
            "stock_daily_basic is planned as its own stock table.",
            "stock_daily_basic exists and is not merged into stock_daily_bar_fact",
            "passed" if "stock_daily_basic" in tables and tables["stock_daily_basic"].data_domain == "stock" else "failed",
            {"stock_daily_basic": tables.get("stock_daily_basic").to_dict() if "stock_daily_basic" in tables else None},
        ),
        (
            "source_trace.batch_count",
            "source_trace",
            "Initial backfill batch count is explicit and auditable.",
            "211 source_batch_id values",
            "passed" if summary.batch_count == 211 else "failed",
            {"batch_count": summary.batch_count},
        ),
        (
            "source_trace.domain_counts",
            "source_trace",
            "Domain counts match the approved physical split plan.",
            "common=1, stock=124, index=43, board=43",
            "passed" if summary.domain_counts == {"common": 1, "stock": 124, "index": 43, "board": 43} else "failed",
            {"domain_counts": summary.domain_counts},
        ),
        (
            "source_trace.source_version_groups",
            "source_trace",
            "Each target table has an activation source_version group.",
            "11 activation groups",
            "passed" if len(summary.activation_groups) == 11 else "failed",
            {"source_versions": [group.source_version for group in summary.activation_groups]},
        ),
        (
            "source_trace.monthly_fact_versions",
            "source_trace",
            "Monthly fact batches roll up to full-range source_versions.",
            "5 monthly fact full-range source_versions",
            "passed" if monthly_fact_versions.issubset(activation_groups) and all(activation_groups[source_version].batch_count == 41 for source_version in monthly_fact_versions) else "failed",
            {"monthly_fact_versions": sorted(monthly_fact_versions)},
        ),
        (
            "quality_gate.identity_key_required",
            "quality_gate",
            "Identity-key coverage gates are required for identity and fact tables before activation.",
            "All stock/index/board tables have identity-key-bearing target table plans.",
            "passed" if all(domain in data_domains for domain in ("stock", "index", "board")) else "failed",
            {"domains": sorted(data_domains)},
        ),
        (
            "quality_gate.membership_snapshot_only",
            "quality_gate",
            "Index and board membership are snapshot-only for initial backfill.",
            f"membership start/end date equals {summary.snapshot_date}",
            "passed" if all(tables[name].start_date == summary.snapshot_date and tables[name].end_date == summary.snapshot_date and tables[name].batch_count == 1 for name in ("index_membership_fact", "board_membership_fact")) else "failed",
            {
                "index_membership": tables["index_membership_fact"].to_dict() if "index_membership_fact" in tables else None,
                "board_membership": tables["board_membership_fact"].to_dict() if "board_membership_fact" in tables else None,
            },
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
            "stock_daily_basic must align to stock universe before activation.",
            "stock_daily_basic activation group has 41 monthly batches",
            "passed" if activation_groups.get("stock_daily_basic_20230101_20260521_v1") and activation_groups["stock_daily_basic_20230101_20260521_v1"].batch_count == 41 else "failed",
            {"source_version": "stock_daily_basic_20230101_20260521_v1"},
        ),
        (
            "quality_gate.no_code_pollution_required",
            "quality_gate",
            "Same-code and 88xxxx pollution checks are required before activation.",
            "stock/index/board physical table summaries exist separately",
            "passed" if all(name in tables for name in ("stock_daily_bar_fact", "index_daily_bar_fact", "board_daily_bar_fact")) else "failed",
            {"daily_tables": [name for name in ("stock_daily_bar_fact", "index_daily_bar_fact", "board_daily_bar_fact") if name in tables]},
        ),
        (
            "archive.parquet_manifest_planned",
            "archive",
            "Parquet archive datasets are planned for historical fact tables.",
            "7 archive datasets",
            "passed" if sum(1 for table in summary.table_summaries if table.archive_dataset) == 7 else "failed",
            {"archive_datasets": [table.archive_dataset for table in summary.table_summaries if table.archive_dataset]},
        ),
        (
            "rollback.rollback_groups_complete",
            "rollback",
            "Every source_version has a rollback group.",
            "rollback groups cover every source_batch_id",
            "passed" if len(rollback_groups) == len(activation_groups) and source_batch_total == summary.batch_count else "failed",
            {"rollback_group_count": len(rollback_groups), "covered_batch_count": source_batch_total},
        ),
        (
            "rollback.delete_by_source_batch_id",
            "rollback",
            "Rollback strategy deletes by source_batch_id before restoring active source_version.",
            "All rollback groups use delete_all_source_batch_ids_then_restore_previous_active_source_version",
            "passed" if all(group.rollback_strategy == "delete_all_source_batch_ids_then_restore_previous_active_source_version" for group in summary.rollback_groups) else "failed",
            {"rollback_strategies": sorted({group.rollback_strategy for group in summary.rollback_groups})},
        ),
        (
            "safety.no_side_effects",
            "safety",
            "Acceptance checklist generation has no side effects.",
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
            "Acceptance scope excludes condition, trigger, action, voice, sim, frontend, and real trading.",
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


def build_acceptance_quality_gates(
    summary: BackfillExecutionChecklist,
    items: Sequence[AcceptanceItem],
) -> list[QualityGateResult]:
    failed_items = [item for item in items if not item.passed]
    categories = Counter(item.category for item in items)
    return [
        QualityGateResult(
            gate_name="acceptance_summary_passed",
            status="passed" if summary.passed else "failed",
            expected_value="summary.passed=true",
            actual_value=str(summary.passed).lower(),
            details={},
        ),
        QualityGateResult(
            gate_name="acceptance_items_non_empty",
            status="passed" if items else "failed",
            expected_value=">0",
            actual_value=str(len(items)),
            details={},
        ),
        QualityGateResult(
            gate_name="acceptance_all_items_passed",
            status="passed" if not failed_items else "failed",
            expected_value="0 failed items",
            actual_value=str(len(failed_items)),
            details={"failed_item_ids": [item.item_id for item in failed_items]},
        ),
        QualityGateResult(
            gate_name="acceptance_required_categories_present",
            status="passed" if all(category in categories for category in ("structure", "source_trace", "quality_gate", "archive", "rollback", "safety")) else "failed",
            expected_value="structure/source_trace/quality_gate/archive/rollback/safety",
            actual_value=",".join(sorted(categories)),
            details={"category_counts": dict(categories)},
        ),
        QualityGateResult(
            gate_name="acceptance_no_side_effects",
            status="passed" if not any((summary.will_call_external_sources, summary.will_read_tdx_files, summary.will_connect_database, summary.will_execute_sql, summary.will_write_data_files)) else "failed",
            expected_value="no runtime side effects",
            actual_value="dry_run",
            details={},
        ),
    ]


def quality_gate_to_dict(gate: QualityGateResult) -> dict[str, Any]:
    return {
        "gate_name": gate.gate_name,
        "status": gate.status,
        "severity": gate.severity,
        "expected_value": gate.expected_value,
        "actual_value": gate.actual_value,
        "details": dict(gate.details or {}),
    }
