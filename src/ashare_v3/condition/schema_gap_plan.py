"""Read-only schema gap planner for existing condition-layer tables.

N2-E6 compares the current development database metadata with the condition
schema draft and builds an additive migration plan. It never executes SQL or
writes business data.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row

from ashare_v3.condition.execute_preflight import REQUIRED_SCHEMA_TABLES
from ashare_v3.condition.schema_migration_readiness import DEFAULT_CONDITION_SCHEMA_PATH


DEFAULT_SCHEMA_GAP_SQL_PATH = "sql/005_condition_layer_policy_columns_migration.sql"
CONSTRAINT_KEYWORDS = (
    "generated",
    "not null",
    "default",
    "check",
    "references",
    "primary key",
    "unique",
    "collate",
)
SKIP_TABLE_BODY_TOKENS = {"primary", "unique", "check", "foreign", "constraint", "or", "and"}


@dataclass(frozen=True)
class TargetColumn:
    table_name: str
    column_name: str
    target_type: str
    nullable: bool
    has_default: bool
    has_check: bool
    has_references: bool
    has_generated: bool
    raw_definition: str

    @property
    def migration_type(self) -> str:
        return simplify_migration_type(self.target_type)

    @property
    def additive_safe(self) -> bool:
        return not self.has_generated

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "column_name": self.column_name,
            "target_type": self.target_type,
            "migration_type": self.migration_type,
            "nullable": self.nullable,
            "has_default": self.has_default,
            "has_check": self.has_check,
            "has_references": self.has_references,
            "has_generated": self.has_generated,
            "raw_definition": self.raw_definition,
        }


@dataclass(frozen=True)
class CurrentColumn:
    table_name: str
    column_name: str
    formatted_type: str
    not_null: bool
    default_expr: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "column_name": self.column_name,
            "formatted_type": self.formatted_type,
            "not_null": self.not_null,
            "default_expr": self.default_expr,
        }


@dataclass(frozen=True)
class MissingColumn:
    table_name: str
    column_name: str
    migration_type: str
    target_nullable: bool
    target_has_default: bool
    target_has_check: bool
    target_has_references: bool
    additive_safe: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "column_name": self.column_name,
            "migration_type": self.migration_type,
            "target_nullable": self.target_nullable,
            "target_has_default": self.target_has_default,
            "target_has_check": self.target_has_check,
            "target_has_references": self.target_has_references,
            "additive_safe": self.additive_safe,
        }


@dataclass(frozen=True)
class TypeMismatch:
    table_name: str
    column_name: str
    target_type: str
    current_type: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "column_name": self.column_name,
            "target_type": self.target_type,
            "current_type": self.current_type,
        }


@dataclass(frozen=True)
class SchemaGapReport:
    stage: str
    schema_path: str
    migration_sql_path: str
    checked_readonly: bool
    will_execute_sql: bool
    writes_performed: bool
    missing_tables: tuple[str, ...]
    missing_columns: tuple[MissingColumn, ...]
    type_mismatches: tuple[TypeMismatch, ...]
    not_null_risks: tuple[dict[str, Any], ...]
    constraint_deferred: tuple[dict[str, Any], ...]
    index_gap_notes: tuple[str, ...]
    rollback_notes: tuple[str, ...]

    @property
    def migration_required(self) -> bool:
        return bool(self.missing_columns)

    @property
    def passed(self) -> bool:
        return not self.missing_tables and not self.type_mismatches

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "schema_path": self.schema_path,
            "migration_sql_path": self.migration_sql_path,
            "checked_readonly": self.checked_readonly,
            "will_execute_sql": self.will_execute_sql,
            "writes_performed": self.writes_performed,
            "migration_required": self.migration_required,
            "passed": self.passed,
            "missing_tables": list(self.missing_tables),
            "missing_columns": [item.to_dict() for item in self.missing_columns],
            "type_mismatches": [item.to_dict() for item in self.type_mismatches],
            "not_null_risks": list(self.not_null_risks),
            "constraint_deferred": list(self.constraint_deferred),
            "index_gap_notes": list(self.index_gap_notes),
            "rollback_notes": list(self.rollback_notes),
        }


def build_condition_schema_gap_report(
    *,
    dsn: str,
    schema_path: str | Path = DEFAULT_CONDITION_SCHEMA_PATH,
    migration_sql_path: str | Path = DEFAULT_SCHEMA_GAP_SQL_PATH,
) -> SchemaGapReport:
    sql_text = Path(schema_path).read_text(encoding="utf-8")
    target_columns = parse_target_columns(sql_text)
    current_columns = fetch_current_columns(dsn, REQUIRED_SCHEMA_TABLES)
    return build_condition_schema_gap_report_from_columns(
        target_columns=target_columns,
        current_columns=current_columns,
        schema_path=str(schema_path),
        migration_sql_path=str(migration_sql_path),
    )


def build_condition_schema_gap_report_from_columns(
    *,
    target_columns: Mapping[str, Mapping[str, TargetColumn]],
    current_columns: Mapping[str, Mapping[str, CurrentColumn]],
    schema_path: str = DEFAULT_CONDITION_SCHEMA_PATH,
    migration_sql_path: str = DEFAULT_SCHEMA_GAP_SQL_PATH,
) -> SchemaGapReport:
    missing_tables = tuple(table for table in REQUIRED_SCHEMA_TABLES if table not in current_columns)
    missing_columns: list[MissingColumn] = []
    type_mismatches: list[TypeMismatch] = []
    not_null_risks: list[dict[str, Any]] = []
    constraint_deferred: list[dict[str, Any]] = []

    for table_name in REQUIRED_SCHEMA_TABLES:
        target_table = target_columns.get(table_name, {})
        current_table = current_columns.get(table_name, {})
        if not current_table:
            continue
        for column_name, target_column in target_table.items():
            current_column = current_table.get(column_name)
            if current_column is None:
                missing = MissingColumn(
                    table_name=table_name,
                    column_name=column_name,
                    migration_type=target_column.migration_type,
                    target_nullable=target_column.nullable,
                    target_has_default=target_column.has_default,
                    target_has_check=target_column.has_check,
                    target_has_references=target_column.has_references,
                    additive_safe=target_column.additive_safe,
                )
                missing_columns.append(missing)
                if not target_column.nullable:
                    not_null_risks.append(
                        {
                            "table_name": table_name,
                            "column_name": column_name,
                            "risk": "target_schema_not_null_but_gap_migration_adds_nullable_column",
                        }
                    )
                if target_column.has_default or target_column.has_check or target_column.has_references:
                    constraint_deferred.append(
                        {
                            "table_name": table_name,
                            "column_name": column_name,
                            "target_has_default": target_column.has_default,
                            "target_has_check": target_column.has_check,
                            "target_has_references": target_column.has_references,
                            "migration_policy": "defer_default_check_fk_to_later_backfill_review",
                        }
                    )
            elif normalize_type(target_column.target_type) != normalize_type(current_column.formatted_type):
                type_mismatches.append(
                    TypeMismatch(
                        table_name=table_name,
                        column_name=column_name,
                        target_type=target_column.target_type,
                        current_type=current_column.formatted_type,
                    )
                )

    return SchemaGapReport(
        stage="N2-E6",
        schema_path=str(schema_path),
        migration_sql_path=str(migration_sql_path),
        checked_readonly=True,
        will_execute_sql=False,
        writes_performed=False,
        missing_tables=missing_tables,
        missing_columns=tuple(missing_columns),
        type_mismatches=tuple(type_mismatches),
        not_null_risks=tuple(not_null_risks),
        constraint_deferred=tuple(constraint_deferred),
        index_gap_notes=tuple(build_index_gap_notes(missing_columns)),
        rollback_notes=tuple(build_rollback_notes(missing_columns)),
    )


def parse_target_columns(sql_text: str) -> dict[str, dict[str, TargetColumn]]:
    output: dict[str, dict[str, TargetColumn]] = {}
    for match in re.finditer(
        r"CREATE\s+TABLE\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\);\s*",
        sql_text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        table_name = match.group(1)
        body = match.group(2)
        table_columns: dict[str, TargetColumn] = {}
        for raw_line in body.splitlines():
            parsed = parse_column_definition(table_name, raw_line)
            if parsed is not None:
                table_columns[parsed.column_name] = parsed
        output[table_name] = table_columns
    return output


def parse_column_definition(table_name: str, raw_line: str) -> TargetColumn | None:
    line = raw_line.strip().rstrip(",")
    if not line or line.startswith("--"):
        return None
    match = re.match(r'"?(?P<column>[A-Za-z_][A-Za-z0-9_]*)"?\s+(?P<definition>.+)$', line)
    if match is None:
        return None
    column_name = match.group("column").lower()
    if column_name in SKIP_TABLE_BODY_TOKENS:
        return None
    definition = match.group("definition").strip()
    if definition.startswith(("<", ">", "=", "!", ")")):
        return None
    definition_lower = definition.lower()
    target_type = definition[: first_constraint_index(definition)].strip()
    return TargetColumn(
        table_name=table_name,
        column_name=column_name,
        target_type=target_type,
        nullable="not null" not in definition_lower,
        has_default=bool(re.search(r"\bdefault\b", definition_lower)),
        has_check=bool(re.search(r"\bcheck\b", definition_lower)),
        has_references=bool(re.search(r"\breferences\b", definition_lower)),
        has_generated=bool(re.search(r"\bgenerated\b", definition_lower)),
        raw_definition=line,
    )


def first_constraint_index(definition: str) -> int:
    lower = definition.lower()
    indexes = [
        match.start()
        for keyword in CONSTRAINT_KEYWORDS
        for match in [re.search(rf"\b{re.escape(keyword)}\b", lower)]
        if match is not None
    ]
    return min(indexes) if indexes else len(definition)


def fetch_current_columns(dsn: str, table_names: tuple[str, ...]) -> dict[str, dict[str, CurrentColumn]]:
    query = """
        SELECT c.relname AS table_name,
               a.attname AS column_name,
               pg_catalog.format_type(a.atttypid, a.atttypmod) AS formatted_type,
               a.attnotnull AS not_null,
               pg_get_expr(ad.adbin, ad.adrelid) AS default_expr
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_attrdef ad
          ON ad.adrelid = a.attrelid
         AND ad.adnum = a.attnum
        WHERE n.nspname = 'public'
          AND c.relname = ANY(%s)
          AND a.attnum > 0
          AND NOT a.attisdropped
        ORDER BY c.relname, a.attnum
    """
    with psycopg.connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(query, (list(table_names),))
        rows = cur.fetchall()
    output: dict[str, dict[str, CurrentColumn]] = {}
    for row in rows:
        table_name = str(row["table_name"])
        column_name = str(row["column_name"])
        output.setdefault(table_name, {})[column_name] = CurrentColumn(
            table_name=table_name,
            column_name=column_name,
            formatted_type=str(row["formatted_type"]),
            not_null=bool(row["not_null"]),
            default_expr=None if row["default_expr"] is None else str(row["default_expr"]),
        )
    return output


def generate_additive_migration_sql(report: SchemaGapReport) -> str:
    lines = [
        "-- A-share monitor v3 condition-layer schema gap migration plan.",
        "-- Stage N2-E6 only: review before running in any PostgreSQL database.",
        "-- This plan is additive: ADD COLUMN IF NOT EXISTS only.",
        "-- It intentionally does not add NOT NULL, DEFAULT, CHECK, FK, DROP, or data backfill.",
        "",
        "BEGIN;",
        "",
    ]
    missing_by_table: dict[str, list[MissingColumn]] = {}
    for item in report.missing_columns:
        if item.additive_safe:
            missing_by_table.setdefault(item.table_name, []).append(item)
    if not missing_by_table:
        lines.append("-- No additive column gaps detected.")
    for table_name in REQUIRED_SCHEMA_TABLES:
        columns = missing_by_table.get(table_name, [])
        if not columns:
            continue
        lines.append(f"ALTER TABLE {table_name}")
        for index, column in enumerate(columns):
            suffix = "," if index < len(columns) - 1 else ";"
            lines.append(f"  ADD COLUMN IF NOT EXISTS {column.column_name} {column.migration_type}{suffix}")
        lines.append("")
    lines.extend(
        [
            "COMMIT;",
            "",
            "-- Rollback note:",
            "-- Additive columns are not automatically dropped. If manual rollback is required,",
            "-- review downstream compatibility first, then run DROP COLUMN commands explicitly.",
        ]
    )
    for item in report.missing_columns:
        if item.additive_safe:
            lines.append(f"-- ALTER TABLE {item.table_name} DROP COLUMN IF EXISTS {item.column_name};")
    return "\n".join(lines) + "\n"


def build_index_gap_notes(missing_columns: list[MissingColumn]) -> list[str]:
    if not missing_columns:
        return ["no_missing_columns_no_index_gap_plan_needed"]
    return [
        "sql/002_condition_layer_schema.sql does not define new indexes for the missing N2-E5 policy/basis columns",
        "N2-E6 migration plan intentionally skips index creation",
    ]


def build_rollback_notes(missing_columns: list[MissingColumn]) -> list[str]:
    if not missing_columns:
        return ["no_additive_columns_to_rollback"]
    return [
        "additive columns should normally remain in place",
        "manual rollback may DROP the added columns only after confirming no code path reads them",
        "N2-E6 does not execute rollback SQL",
    ]


def simplify_migration_type(target_type: str) -> str:
    normalized = " ".join(target_type.strip().split())
    if normalized.lower().startswith("bigint generated"):
        return "BIGINT"
    return normalized.upper()


def normalize_type(type_text: str) -> str:
    normalized = " ".join(type_text.strip().lower().split())
    aliases = {
        "text": "text",
        "text[]": "text[]",
        "character varying": "text",
        "bigint": "bigint",
        "integer": "integer",
        "boolean": "boolean",
        "numeric": "numeric",
        "jsonb": "jsonb",
        "timestamp with time zone": "timestamptz",
        "timestamptz": "timestamptz",
    }
    return aliases.get(normalized, normalized)
