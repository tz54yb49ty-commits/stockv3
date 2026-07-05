"""PostgreSQL schema readiness checks for raw ingestion.

This module only reads SQL text and performs static checks. It never connects
PostgreSQL, executes SQL, runs migrations, reads source data, or writes files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Mapping

from ashare_v3.ingestion.common import IngestionValidationError, QualityGateResult
from ashare_v3.ingestion.ingestion_acceptance import quality_gate_to_dict


DEFAULT_SCHEMA_PATH = "sql/001_raw_ingestion_schema.sql"
REQUIRED_SCHEMA_TABLES = (
    "common_ingest_batch",
    "common_quality_gate_result",
    "common_active_source_version",
    "common_trade_calendar",
    "stock_identity",
    "index_identity",
    "board_identity",
    "stock_daily_bar_fact",
    "stock_daily_basic",
    "index_daily_bar_fact",
    "board_daily_bar_fact",
    "stock_financial_metrics_fact",
    "index_membership_fact",
    "board_membership_fact",
)
CORE_TARGET_TABLES = (
    "common_trade_calendar",
    "stock_identity",
    "index_identity",
    "board_identity",
    "index_membership_fact",
    "board_membership_fact",
    "stock_daily_bar_fact",
    "stock_daily_basic",
    "index_daily_bar_fact",
    "board_daily_bar_fact",
    "stock_financial_metrics_fact",
)
SOURCE_METADATA_TABLES = CORE_TARGET_TABLES
IDENTITY_KEY_REQUIREMENTS = {
    "stock_identity": ("stock_identity_key",),
    "index_identity": ("index_identity_key",),
    "board_identity": ("board_identity_key",),
    "stock_daily_bar_fact": ("stock_identity_key",),
    "stock_daily_basic": ("stock_identity_key",),
    "stock_financial_metrics_fact": ("stock_identity_key",),
    "index_daily_bar_fact": ("index_identity_key",),
    "index_membership_fact": ("index_identity_key", "stock_identity_key"),
    "board_daily_bar_fact": ("board_identity_key",),
    "board_membership_fact": ("board_identity_key", "stock_identity_key"),
}
FORBIDDEN_EXACT_TABLES = ("daily_bar_fact", "sim_position", "candidate_list", "filter_fact_cache")
FORBIDDEN_SQL_PATTERNS = (
    r"\bCREATE\s+TRIGGER\b",
    r"\bCREATE\s+TABLE\s+.*voice",
    r"\bCREATE\s+TABLE\s+.*action",
    r"\bCREATE\s+TABLE\s+.*sim_trade",
)


@dataclass(frozen=True)
class SchemaTableSummary:
    table_name: str
    column_names: tuple[str, ...]
    has_source_batch_id: bool
    has_source_version: bool
    identity_key_columns: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "column_count": len(self.column_names),
            "column_names": list(self.column_names),
            "has_source_batch_id": self.has_source_batch_id,
            "has_source_version": self.has_source_version,
            "identity_key_columns": list(self.identity_key_columns),
        }


@dataclass(frozen=True)
class SchemaReadinessReport:
    schema_path: str
    table_count: int
    required_table_count: int
    table_summaries: tuple[SchemaTableSummary, ...]
    quality_gates: tuple[QualityGateResult, ...]
    will_connect_database: bool = False
    will_execute_sql: bool = False
    will_write_data_files: bool = False
    will_call_external_sources: bool = False
    will_read_tdx_files: bool = False

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.quality_gates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_path": self.schema_path,
            "table_count": self.table_count,
            "required_table_count": self.required_table_count,
            "passed": self.passed,
            "table_summaries": [summary.to_dict() for summary in self.table_summaries],
            "quality_gates": [quality_gate_to_dict(gate) for gate in self.quality_gates],
            "side_effects": {
                "will_connect_database": self.will_connect_database,
                "will_execute_sql": self.will_execute_sql,
                "will_write_data_files": self.will_write_data_files,
                "will_call_external_sources": self.will_call_external_sources,
                "will_read_tdx_files": self.will_read_tdx_files,
            },
        }


def build_schema_readiness_report(path: str | Path = DEFAULT_SCHEMA_PATH) -> SchemaReadinessReport:
    schema_path = Path(path)
    sql_text = schema_path.read_text(encoding="utf-8")
    return build_schema_readiness_report_from_sql(sql_text, schema_path=str(path))


def build_schema_readiness_report_from_sql(
    sql_text: str,
    *,
    schema_path: str = "<memory>",
) -> SchemaReadinessReport:
    tables = parse_create_tables(sql_text)
    summaries = tuple(build_table_summaries(tables))
    gates = tuple(build_schema_quality_gates(sql_text, tables, summaries))
    return SchemaReadinessReport(
        schema_path=schema_path,
        table_count=len(tables),
        required_table_count=len(REQUIRED_SCHEMA_TABLES),
        table_summaries=summaries,
        quality_gates=gates,
    )


def parse_create_tables(sql_text: str) -> dict[str, tuple[str, ...]]:
    table_blocks = re.finditer(
        r"CREATE\s+TABLE\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\);\s*",
        sql_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    tables: dict[str, tuple[str, ...]] = {}
    for match in table_blocks:
        table_name = match.group(1)
        table_body = match.group(2)
        tables[table_name] = extract_column_names(table_body)
    return tables


def extract_column_names(table_body: str) -> tuple[str, ...]:
    columns: list[str] = []
    for raw_line in table_body.splitlines():
        line = raw_line.strip().rstrip(",")
        if not line or line.startswith("--"):
            continue
        first_token = line.split(None, 1)[0].strip('"').lower()
        if first_token in {"primary", "unique", "check", "foreign", "constraint"}:
            continue
        columns.append(first_token)
    return tuple(columns)


def build_table_summaries(tables: Mapping[str, tuple[str, ...]]) -> list[SchemaTableSummary]:
    summaries: list[SchemaTableSummary] = []
    for table_name in REQUIRED_SCHEMA_TABLES:
        column_names = tables.get(table_name, ())
        summaries.append(
            SchemaTableSummary(
                table_name=table_name,
                column_names=column_names,
                has_source_batch_id="source_batch_id" in column_names,
                has_source_version="source_version" in column_names,
                identity_key_columns=tuple(column for column in column_names if column.endswith("_identity_key")),
            )
        )
    return summaries


def build_schema_quality_gates(
    sql_text: str,
    tables: Mapping[str, tuple[str, ...]],
    summaries: tuple[SchemaTableSummary, ...],
) -> list[QualityGateResult]:
    table_names = set(tables)
    missing_tables = sorted(set(REQUIRED_SCHEMA_TABLES) - table_names)
    forbidden_exact_tables = sorted(table for table in FORBIDDEN_EXACT_TABLES if table in table_names)
    forbidden_pattern_hits = [
        pattern
        for pattern in FORBIDDEN_SQL_PATTERNS
        if re.search(pattern, sql_text, flags=re.IGNORECASE)
    ]
    source_metadata_failures = [
        table_name
        for table_name in SOURCE_METADATA_TABLES
        if not {"source_batch_id", "source_version"}.issubset(tables.get(table_name, ()))
    ]
    identity_key_failures = [
        table_name
        for table_name, required_columns in IDENTITY_KEY_REQUIREMENTS.items()
        if not set(required_columns).issubset(tables.get(table_name, ()))
    ]
    physical_prefix_failures = [
        table_name
        for table_name in CORE_TARGET_TABLES
        if table_name != "common_trade_calendar" and not table_name.startswith(("stock_", "index_", "board_"))
    ]
    audit_columns = set(tables.get("common_ingest_batch", ()))
    quality_columns = set(tables.get("common_quality_gate_result", ()))
    active_columns = set(tables.get("common_active_source_version", ()))
    rollback_columns = {"rollback_strategy", "status", "error_summary", "quality_gate_summary"}
    active_required_columns = {"source_batch_id", "source_version", "previous_source_version", "activated_at"}
    quality_required_columns = {"source_batch_id", "source_version", "gate_name", "severity", "status", "details"}
    table_summary_map = {summary.table_name: summary for summary in summaries}

    return [
        QualityGateResult(
            gate_name="schema_required_tables_present",
            status="passed" if not missing_tables else "failed",
            expected_value=str(len(REQUIRED_SCHEMA_TABLES)),
            actual_value=str(len(REQUIRED_SCHEMA_TABLES) - len(missing_tables)),
            details={"missing_tables": missing_tables},
        ),
        QualityGateResult(
            gate_name="schema_no_mixed_daily_bar_fact",
            status="passed" if not forbidden_exact_tables else "failed",
            expected_value="no mixed daily_bar_fact or legacy runtime tables",
            actual_value=str(len(forbidden_exact_tables)),
            details={"forbidden_tables": forbidden_exact_tables},
        ),
        QualityGateResult(
            gate_name="schema_no_forbidden_layers",
            status="passed" if not forbidden_pattern_hits else "failed",
            expected_value="no trigger/action/voice/sim SQL objects",
            actual_value=str(len(forbidden_pattern_hits)),
            details={"forbidden_pattern_hits": forbidden_pattern_hits},
        ),
        QualityGateResult(
            gate_name="schema_physical_table_prefixes",
            status="passed" if not physical_prefix_failures else "failed",
            expected_value="stock/index/board/common physical tables",
            actual_value=str(len(physical_prefix_failures)),
            details={"physical_prefix_failures": physical_prefix_failures},
        ),
        QualityGateResult(
            gate_name="schema_source_metadata_columns",
            status="passed" if not source_metadata_failures else "failed",
            expected_value="source_batch_id and source_version on all target tables",
            actual_value=str(len(source_metadata_failures)),
            details={"source_metadata_failures": source_metadata_failures},
        ),
        QualityGateResult(
            gate_name="schema_identity_key_columns",
            status="passed" if not identity_key_failures else "failed",
            expected_value="identity_key columns on identity and fact tables",
            actual_value=str(len(identity_key_failures)),
            details={
                "identity_key_failures": identity_key_failures,
                "identity_key_columns": {
                    table_name: list(table_summary_map[table_name].identity_key_columns)
                    for table_name in IDENTITY_KEY_REQUIREMENTS
                    if table_name in table_summary_map
                },
            },
        ),
        QualityGateResult(
            gate_name="schema_ingest_batch_audit_columns",
            status="passed" if rollback_columns.issubset(audit_columns) else "failed",
            expected_value="rollback/status/error/quality columns",
            actual_value=str(len(rollback_columns & audit_columns)),
            details={"missing_columns": sorted(rollback_columns - audit_columns)},
        ),
        QualityGateResult(
            gate_name="schema_quality_gate_columns",
            status="passed" if quality_required_columns.issubset(quality_columns) else "failed",
            expected_value="quality gate result trace columns",
            actual_value=str(len(quality_required_columns & quality_columns)),
            details={"missing_columns": sorted(quality_required_columns - quality_columns)},
        ),
        QualityGateResult(
            gate_name="schema_active_source_version_columns",
            status="passed" if active_required_columns.issubset(active_columns) else "failed",
            expected_value="active source version rollback columns",
            actual_value=str(len(active_required_columns & active_columns)),
            details={"missing_columns": sorted(active_required_columns - active_columns)},
        ),
        QualityGateResult(
            gate_name="schema_static_check_only",
            status="passed",
            expected_value="no PostgreSQL connection and no SQL execution",
            actual_value="static_readiness_only",
            details={},
        ),
    ]


def require_schema_ready(path: str | Path = DEFAULT_SCHEMA_PATH) -> SchemaReadinessReport:
    report = build_schema_readiness_report(path)
    if not report.passed:
        failed = [gate.gate_name for gate in report.quality_gates if not gate.passed]
        raise IngestionValidationError(f"schema readiness failed: {failed}")
    return report
