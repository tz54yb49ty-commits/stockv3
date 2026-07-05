"""Read-only N3 market-data schema gap planner.

N3-3 compares the 006/007/008 schema drafts with the current v3 PostgreSQL
development database metadata. It never executes migration SQL, writes
business rows, pulls market data, starts workers, or enters downstream layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_schema_review_connect

from ashare_v3.condition.basis import count_quality_severities, quality_item


DEFAULT_MARKET_SCHEMA_PATHS = (
    "sql/006_market_data_layer_schema.sql",
    "sql/007_market_data_fact_schema.sql",
    "sql/008_common_event_infra_schema.sql",
)
DEFAULT_MARKET_SCHEMA_GAP_SQL_PATH = "sql/009_market_data_schema_migration.sql"
DEFAULT_MARKET_SCHEMA_GAP_JSON_PATH = "docs/N3_3_market_data_schema_gap_plan.json"
DEFAULT_MARKET_SCHEMA_GAP_MD_PATH = "docs/N3_3_MARKET_DATA_SCHEMA_GAP_PLAN.md"
REQUIRED_N2_DEPENDENCY_TABLES = (
    "common_condition_run",
    "stock_minute_target_scope",
    "index_minute_target_scope",
    "board_minute_target_scope",
)
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
SKIP_TABLE_BODY_TOKENS = {"primary", "unique", "check", "foreign", "constraint", "exclude"}
FORBIDDEN_DML_OR_DESTRUCTIVE_SQL = (
    r"(^|;)\s*DROP\b",
    r"(^|;)\s*INSERT\b",
    r"(^|;)\s*UPDATE\b",
    r"(^|;)\s*DELETE\b",
    r"(^|;)\s*TRUNCATE\b",
    r"(^|;)\s*COPY\b",
)
FORBIDDEN_RUNTIME_TABLE_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*_runtime\b", re.IGNORECASE)
FORBIDDEN_N3_USER_EVENT_PATTERN = re.compile(r"['\"]User[A-Za-z0-9_]+['\"]")


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
class TargetUniqueConstraint:
    table_name: str
    constraint_name: str
    columns: tuple[str, ...]
    kind: str
    raw_definition: str

    @property
    def can_use_unique_index(self) -> bool:
        return self.kind in {"unique_constraint", "unique_index"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "constraint_name": self.constraint_name,
            "columns": list(self.columns),
            "kind": self.kind,
            "raw_definition": self.raw_definition,
        }


@dataclass(frozen=True)
class TargetIndex:
    index_name: str
    table_name: str
    columns: tuple[str, ...]
    unique: bool
    raw_definition: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "index_name": self.index_name,
            "table_name": self.table_name,
            "columns": list(self.columns),
            "unique": self.unique,
            "raw_definition": self.raw_definition,
        }


@dataclass(frozen=True)
class TargetTable:
    table_name: str
    source_schema_path: str
    create_table_sql: str
    columns: Mapping[str, TargetColumn]
    unique_constraints: tuple[TargetUniqueConstraint, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "source_schema_path": self.source_schema_path,
            "column_count": len(self.columns),
            "columns": [column.to_dict() for column in self.columns.values()],
            "unique_constraints": [item.to_dict() for item in self.unique_constraints],
        }


@dataclass(frozen=True)
class TargetSchema:
    schema_paths: tuple[str, ...]
    tables: Mapping[str, TargetTable]
    indexes: tuple[TargetIndex, ...]
    unsafe_sql_hits: tuple[str, ...]
    forbidden_runtime_table_hits: tuple[str, ...]
    forbidden_user_event_hits: tuple[str, ...]

    @property
    def table_names(self) -> tuple[str, ...]:
        return tuple(self.tables)

    def indexes_for_missing_tables(self, missing_tables: Sequence[str]) -> tuple[TargetIndex, ...]:
        missing = set(missing_tables)
        return tuple(index for index in self.indexes if index.table_name in missing)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_paths": list(self.schema_paths),
            "table_names": list(self.table_names),
            "table_count": len(self.tables),
            "index_count": len(self.indexes),
            "unique_constraint_count": sum(len(table.unique_constraints) for table in self.tables.values()),
            "unsafe_sql_hits": list(self.unsafe_sql_hits),
            "forbidden_runtime_table_hits": list(self.forbidden_runtime_table_hits),
            "forbidden_user_event_hits": list(self.forbidden_user_event_hits),
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
class CurrentUniqueConstraint:
    table_name: str
    constraint_name: str
    columns: tuple[str, ...]
    kind: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "constraint_name": self.constraint_name,
            "columns": list(self.columns),
            "kind": self.kind,
        }


@dataclass(frozen=True)
class CurrentSchemaMetadata:
    checked_readonly: bool
    existing_tables: tuple[str, ...]
    missing_dependency_tables: tuple[str, ...]
    columns_by_table: Mapping[str, Mapping[str, CurrentColumn]]
    unique_constraints_by_table: Mapping[str, tuple[CurrentUniqueConstraint, ...]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked_readonly": self.checked_readonly,
            "existing_tables": list(self.existing_tables),
            "missing_dependency_tables": list(self.missing_dependency_tables),
            "columns_by_table": {
                table: [column.to_dict() for column in columns.values()]
                for table, columns in self.columns_by_table.items()
            },
            "unique_constraints_by_table": {
                table: [item.to_dict() for item in constraints]
                for table, constraints in self.unique_constraints_by_table.items()
            },
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
class MissingUniqueConstraint:
    table_name: str
    constraint_name: str
    columns: tuple[str, ...]
    kind: str
    raw_definition: str

    @classmethod
    def from_target(cls, target: TargetUniqueConstraint) -> "MissingUniqueConstraint":
        return cls(
            table_name=target.table_name,
            constraint_name=target.constraint_name,
            columns=target.columns,
            kind=target.kind,
            raw_definition=target.raw_definition,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "constraint_name": self.constraint_name,
            "columns": list(self.columns),
            "kind": self.kind,
            "raw_definition": self.raw_definition,
        }


@dataclass(frozen=True)
class N3SchemaGapReport:
    stage: str
    layer_role: str
    schema_paths: tuple[str, ...]
    migration_sql_path: str
    checked_readonly: bool
    will_execute_sql: bool
    writes_performed: bool
    market_data_pulled: bool
    market_data_fact_written: bool
    downstream_layers_touched: bool
    worker_started: bool
    old_system_touched: bool
    missing_tables: tuple[str, ...]
    missing_columns: tuple[MissingColumn, ...]
    type_mismatches: tuple[TypeMismatch, ...]
    missing_unique_constraints: tuple[MissingUniqueConstraint, ...]
    missing_dependency_tables: tuple[str, ...]
    manual_review_required: bool
    migration_safe_to_apply: bool
    target_schema: TargetSchema
    quality_items: tuple[dict[str, Any], ...]

    @property
    def migration_required(self) -> bool:
        return bool(self.missing_tables or self.missing_columns or self.missing_unique_constraints)

    @property
    def p0_count(self) -> int:
        return count_quality_severities(self.quality_items)["P0"]

    @property
    def passed(self) -> bool:
        return self.p0_count == 0

    def to_dict(self) -> dict[str, Any]:
        severity_counts = count_quality_severities(self.quality_items)
        return {
            "stage": self.stage,
            "layer_role": self.layer_role,
            "schema_paths": list(self.schema_paths),
            "migration_sql_path": self.migration_sql_path,
            "checked_readonly": self.checked_readonly,
            "will_execute_sql": self.will_execute_sql,
            "writes_performed": self.writes_performed,
            "market_data_pulled": self.market_data_pulled,
            "market_data_fact_written": self.market_data_fact_written,
            "downstream_layers_touched": self.downstream_layers_touched,
            "worker_started": self.worker_started,
            "old_system_touched": self.old_system_touched,
            "migration_required": self.migration_required,
            "manual_review_required": self.manual_review_required,
            "migration_safe_to_apply": self.migration_safe_to_apply,
            "passed": self.passed,
            "missing_tables": list(self.missing_tables),
            "missing_columns": [item.to_dict() for item in self.missing_columns],
            "type_mismatch": [item.to_dict() for item in self.type_mismatches],
            "type_mismatches": [item.to_dict() for item in self.type_mismatches],
            "missing_unique_constraints": [item.to_dict() for item in self.missing_unique_constraints],
            "missing_dependency_tables": list(self.missing_dependency_tables),
            "target_schema": self.target_schema.to_dict(),
            "quality": {
                "p0_count": severity_counts["P0"],
                "p1_count": severity_counts["P1"],
                "p2_count": severity_counts["P2"],
                "items": list(self.quality_items),
            },
            "side_effects": {
                "read_only_database_checks": self.checked_readonly,
                "will_execute_sql": self.will_execute_sql,
                "migration_executed": False,
                "writes_performed": self.writes_performed,
                "market_data_pulled": self.market_data_pulled,
                "market_data_fact_written": self.market_data_fact_written,
                "downstream_layers_touched": self.downstream_layers_touched,
                "worker_started": self.worker_started,
                "old_system_touched": self.old_system_touched,
            },
        }


def build_market_data_schema_gap_report(
    *,
    dsn: str,
    schema_paths: Sequence[str | Path] = DEFAULT_MARKET_SCHEMA_PATHS,
    migration_sql_path: str | Path = DEFAULT_MARKET_SCHEMA_GAP_SQL_PATH,
) -> N3SchemaGapReport:
    target_schema = parse_target_schema(schema_paths)
    current_metadata = fetch_current_schema_metadata(
        dsn,
        target_table_names=target_schema.table_names,
        dependency_table_names=REQUIRED_N2_DEPENDENCY_TABLES,
    )
    return build_market_data_schema_gap_report_from_metadata(
        target_schema=target_schema,
        current_metadata=current_metadata,
        migration_sql_path=str(migration_sql_path),
    )


def build_market_data_schema_gap_report_from_metadata(
    *,
    target_schema: TargetSchema,
    current_metadata: CurrentSchemaMetadata,
    migration_sql_path: str = DEFAULT_MARKET_SCHEMA_GAP_SQL_PATH,
) -> N3SchemaGapReport:
    current_tables = set(current_metadata.existing_tables)
    missing_tables = tuple(table for table in target_schema.table_names if table not in current_tables)
    missing_columns: list[MissingColumn] = []
    type_mismatches: list[TypeMismatch] = []
    missing_unique_constraints: list[MissingUniqueConstraint] = []

    for table_name, target_table in target_schema.tables.items():
        if table_name not in current_tables:
            continue
        current_columns = current_metadata.columns_by_table.get(table_name, {})
        for column_name, target_column in target_table.columns.items():
            current_column = current_columns.get(column_name)
            if current_column is None:
                missing_columns.append(
                    MissingColumn(
                        table_name=table_name,
                        column_name=column_name,
                        migration_type=target_column.migration_type,
                        target_nullable=target_column.nullable,
                        target_has_default=target_column.has_default,
                        target_has_check=target_column.has_check,
                        target_has_references=target_column.has_references,
                        additive_safe=target_column.additive_safe,
                    )
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
        current_uniques = current_metadata.unique_constraints_by_table.get(table_name, ())
        for target_unique in target_table.unique_constraints:
            if not unique_constraint_satisfied(target_unique, current_uniques):
                missing_unique_constraints.append(MissingUniqueConstraint.from_target(target_unique))

    manual_review_required = bool(
        type_mismatches
        or missing_columns
        or missing_unique_constraints
        or current_metadata.missing_dependency_tables
        or target_schema.unsafe_sql_hits
        or target_schema.forbidden_runtime_table_hits
        or target_schema.forbidden_user_event_hits
    )
    migration_safe_to_apply = bool(
        not type_mismatches
        and not current_metadata.missing_dependency_tables
        and not target_schema.unsafe_sql_hits
        and not target_schema.forbidden_runtime_table_hits
        and not target_schema.forbidden_user_event_hits
        and all(item.additive_safe for item in missing_columns)
        and not missing_columns
        and not missing_unique_constraints
    )
    quality_items = tuple(
        build_quality_items(
            target_schema=target_schema,
            current_metadata=current_metadata,
            missing_tables=missing_tables,
            missing_columns=tuple(missing_columns),
            type_mismatches=tuple(type_mismatches),
            missing_unique_constraints=tuple(missing_unique_constraints),
            migration_safe_to_apply=migration_safe_to_apply,
            manual_review_required=manual_review_required,
        )
    )
    return N3SchemaGapReport(
        stage="N3-3",
        layer_role="N3_market_data",
        schema_paths=target_schema.schema_paths,
        migration_sql_path=str(migration_sql_path),
        checked_readonly=current_metadata.checked_readonly,
        will_execute_sql=False,
        writes_performed=False,
        market_data_pulled=False,
        market_data_fact_written=False,
        downstream_layers_touched=False,
        worker_started=False,
        old_system_touched=False,
        missing_tables=missing_tables,
        missing_columns=tuple(missing_columns),
        type_mismatches=tuple(type_mismatches),
        missing_unique_constraints=tuple(missing_unique_constraints),
        missing_dependency_tables=current_metadata.missing_dependency_tables,
        manual_review_required=manual_review_required,
        migration_safe_to_apply=migration_safe_to_apply,
        target_schema=target_schema,
        quality_items=quality_items,
    )


def parse_target_schema(schema_paths: Sequence[str | Path]) -> TargetSchema:
    tables: dict[str, TargetTable] = {}
    indexes: list[TargetIndex] = []
    unsafe_sql_hits: list[str] = []
    forbidden_runtime_table_hits: list[str] = []
    forbidden_user_event_hits: list[str] = []
    schema_path_strings = tuple(str(path) for path in schema_paths)

    for schema_path in schema_paths:
        path = Path(schema_path)
        sql_text = path.read_text(encoding="utf-8")
        executable_sql = strip_line_comments(sql_text)
        unsafe_sql_hits.extend(
            f"{path}:{pattern}"
            for pattern in FORBIDDEN_DML_OR_DESTRUCTIVE_SQL
            if re.search(pattern, executable_sql, flags=re.IGNORECASE)
        )
        forbidden_runtime_table_hits.extend(
            f"{path}:{match.group(0)}"
            for match in FORBIDDEN_RUNTIME_TABLE_PATTERN.finditer(executable_sql)
        )
        forbidden_user_event_hits.extend(
            f"{path}:{match.group(0)}"
            for match in FORBIDDEN_N3_USER_EVENT_PATTERN.finditer(executable_sql)
        )
        for table_name, body, create_sql in iter_create_table_blocks(executable_sql):
            table_columns: dict[str, TargetColumn] = {}
            table_uniques: list[TargetUniqueConstraint] = []
            for part in split_top_level_commas(body):
                parsed_column = parse_column_definition(table_name, part)
                if parsed_column is not None:
                    table_columns[parsed_column.column_name] = parsed_column
                    table_uniques.extend(parse_column_unique_constraints(table_name, parsed_column))
                    continue
                parsed_unique = parse_table_unique_constraint(table_name, part)
                if parsed_unique is not None:
                    table_uniques.append(parsed_unique)
            tables[table_name] = TargetTable(
                table_name=table_name,
                source_schema_path=str(path),
                create_table_sql=create_sql.strip(),
                columns=table_columns,
                unique_constraints=tuple(table_uniques),
            )
        indexes.extend(parse_index_definitions(executable_sql))

    for index in indexes:
        if index.unique and index.table_name in tables:
            existing = tables[index.table_name]
            tables[index.table_name] = TargetTable(
                table_name=existing.table_name,
                source_schema_path=existing.source_schema_path,
                create_table_sql=existing.create_table_sql,
                columns=existing.columns,
                unique_constraints=existing.unique_constraints
                + (
                    TargetUniqueConstraint(
                        table_name=index.table_name,
                        constraint_name=index.index_name,
                        columns=index.columns,
                        kind="unique_index",
                        raw_definition=index.raw_definition,
                    ),
                ),
            )

    return TargetSchema(
        schema_paths=schema_path_strings,
        tables=tables,
        indexes=tuple(indexes),
        unsafe_sql_hits=tuple(unsafe_sql_hits),
        forbidden_runtime_table_hits=tuple(forbidden_runtime_table_hits),
        forbidden_user_event_hits=tuple(forbidden_user_event_hits),
    )


def iter_create_table_blocks(sql_text: str) -> list[tuple[str, str, str]]:
    pattern = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<table>[A-Za-z_][A-Za-z0-9_]*)\s*\(",
        re.IGNORECASE,
    )
    blocks: list[tuple[str, str, str]] = []
    for match in pattern.finditer(sql_text):
        table_name = match.group("table")
        open_paren_index = match.end() - 1
        close_paren_index = find_matching_paren(sql_text, open_paren_index)
        if close_paren_index < 0:
            continue
        semicolon_index = sql_text.find(";", close_paren_index)
        if semicolon_index < 0:
            continue
        body = sql_text[open_paren_index + 1 : close_paren_index]
        create_sql = sql_text[match.start() : semicolon_index + 1]
        blocks.append((table_name, body, create_sql))
    return blocks


def find_matching_paren(text: str, open_index: int) -> int:
    depth = 0
    in_single_quote = False
    index = open_index
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if char == "'" and next_char == "'":
            index += 2
            continue
        if char == "'":
            in_single_quote = not in_single_quote
        elif not in_single_quote:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index
        index += 1
    return -1


def split_top_level_commas(body: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    in_single_quote = False
    index = 0
    while index < len(body):
        char = body[index]
        next_char = body[index + 1] if index + 1 < len(body) else ""
        if char == "'" and next_char == "'":
            index += 2
            continue
        if char == "'":
            in_single_quote = not in_single_quote
        elif not in_single_quote:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                parts.append(body[start:index].strip())
                start = index + 1
        index += 1
    tail = body[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def parse_column_definition(table_name: str, raw_part: str) -> TargetColumn | None:
    line = compact_sql_fragment(raw_part)
    if not line:
        return None
    match = re.match(r'"?(?P<column>[A-Za-z_][A-Za-z0-9_]*)"?\s+(?P<definition>.+)$', line)
    if match is None:
        return None
    column_name = match.group("column").lower()
    if column_name in SKIP_TABLE_BODY_TOKENS:
        return None
    definition = match.group("definition").strip()
    if not definition or definition.startswith(("<", ">", "=", "!", ")")):
        return None
    definition_lower = definition.lower()
    target_type = definition[: first_constraint_index(definition)].strip()
    if not target_type:
        return None
    return TargetColumn(
        table_name=table_name,
        column_name=column_name,
        target_type=target_type,
        nullable="not null" not in definition_lower and "primary key" not in definition_lower,
        has_default=bool(re.search(r"\bdefault\b", definition_lower)),
        has_check=bool(re.search(r"\bcheck\b", definition_lower)),
        has_references=bool(re.search(r"\breferences\b", definition_lower)),
        has_generated=bool(re.search(r"\bgenerated\b", definition_lower)),
        raw_definition=line,
    )


def parse_column_unique_constraints(table_name: str, column: TargetColumn) -> list[TargetUniqueConstraint]:
    definition_lower = column.raw_definition.lower()
    output: list[TargetUniqueConstraint] = []
    if re.search(r"\bprimary\s+key\b", definition_lower):
        output.append(
            TargetUniqueConstraint(
                table_name=table_name,
                constraint_name=f"{table_name}_pkey",
                columns=(column.column_name,),
                kind="primary_key",
                raw_definition=column.raw_definition,
            )
        )
    elif re.search(r"\bunique\b", definition_lower):
        output.append(
            TargetUniqueConstraint(
                table_name=table_name,
                constraint_name=stable_unique_name(table_name, (column.column_name,)),
                columns=(column.column_name,),
                kind="unique_constraint",
                raw_definition=column.raw_definition,
            )
        )
    return output


def parse_table_unique_constraint(table_name: str, raw_part: str) -> TargetUniqueConstraint | None:
    line = compact_sql_fragment(raw_part)
    if not line:
        return None
    named_match = re.match(
        r"CONSTRAINT\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s+(?P<kind>PRIMARY\s+KEY|UNIQUE)\s*\((?P<cols>[^)]+)\)",
        line,
        flags=re.IGNORECASE,
    )
    if named_match is not None:
        kind_text = named_match.group("kind").lower()
        columns = parse_column_list(named_match.group("cols"))
        return TargetUniqueConstraint(
            table_name=table_name,
            constraint_name=named_match.group("name"),
            columns=columns,
            kind="primary_key" if "primary" in kind_text else "unique_constraint",
            raw_definition=line,
        )
    unnamed_match = re.match(
        r"(?P<kind>PRIMARY\s+KEY|UNIQUE)\s*\((?P<cols>[^)]+)\)",
        line,
        flags=re.IGNORECASE,
    )
    if unnamed_match is None:
        return None
    kind_text = unnamed_match.group("kind").lower()
    columns = parse_column_list(unnamed_match.group("cols"))
    constraint_name = f"{table_name}_pkey" if "primary" in kind_text else stable_unique_name(table_name, columns)
    return TargetUniqueConstraint(
        table_name=table_name,
        constraint_name=constraint_name,
        columns=columns,
        kind="primary_key" if "primary" in kind_text else "unique_constraint",
        raw_definition=line,
    )


def parse_index_definitions(sql_text: str) -> list[TargetIndex]:
    pattern = re.compile(
        r"CREATE\s+(?P<unique>UNIQUE\s+)?INDEX\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s+"
        r"ON\s+(?P<table>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<cols>[^)]+)\)\s*;",
        flags=re.IGNORECASE | re.DOTALL,
    )
    indexes: list[TargetIndex] = []
    for match in pattern.finditer(sql_text):
        indexes.append(
            TargetIndex(
                index_name=match.group("name"),
                table_name=match.group("table"),
                columns=parse_column_list(match.group("cols")),
                unique=bool(match.group("unique")),
                raw_definition=compact_sql_fragment(match.group(0)),
            )
        )
    return indexes


def parse_column_list(text: str) -> tuple[str, ...]:
    columns: list[str] = []
    for part in split_top_level_commas(text):
        clean = part.strip().strip('"').lower()
        clean = re.sub(r"\s+(asc|desc)\b.*$", "", clean, flags=re.IGNORECASE)
        if clean:
            columns.append(clean)
    return tuple(columns)


def fetch_current_schema_metadata(
    dsn: str,
    *,
    target_table_names: Sequence[str],
    dependency_table_names: Sequence[str],
) -> CurrentSchemaMetadata:
    table_names = tuple(target_table_names)
    dependency_names = tuple(dependency_table_names)
    with audited_n3_market_schema_review_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        existing_tables = fetch_existing_tables(cur, tuple(dict.fromkeys(table_names + dependency_names)))
        columns_by_table = fetch_current_columns(cur, table_names)
        unique_constraints_by_table = fetch_current_unique_constraints(cur, table_names)
    missing_dependency_tables = tuple(table for table in dependency_names if table not in existing_tables)
    return CurrentSchemaMetadata(
        checked_readonly=True,
        existing_tables=tuple(table for table in table_names if table in existing_tables),
        missing_dependency_tables=missing_dependency_tables,
        columns_by_table=columns_by_table,
        unique_constraints_by_table=unique_constraints_by_table,
    )


def fetch_existing_tables(cur: Any, table_names: Sequence[str]) -> set[str]:
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = ANY(%s)
        """,
        (list(table_names),),
    )
    return {str(row["table_name"]) for row in cur.fetchall()}


def fetch_current_columns(cur: Any, table_names: Sequence[str]) -> dict[str, dict[str, CurrentColumn]]:
    cur.execute(
        """
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
        """,
        (list(table_names),),
    )
    output: dict[str, dict[str, CurrentColumn]] = {}
    for row in cur.fetchall():
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


def fetch_current_unique_constraints(cur: Any, table_names: Sequence[str]) -> dict[str, tuple[CurrentUniqueConstraint, ...]]:
    cur.execute(
        """
        SELECT c.relname AS table_name,
               con.conname AS constraint_name,
               CASE con.contype WHEN 'p' THEN 'primary_key' ELSE 'unique_constraint' END AS kind,
               array_agg(a.attname ORDER BY key_order.ordinality) AS columns
        FROM pg_constraint con
        JOIN pg_class c ON c.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN unnest(con.conkey) WITH ORDINALITY AS key_order(attnum, ordinality)
          ON true
        JOIN pg_attribute a
          ON a.attrelid = c.oid
         AND a.attnum = key_order.attnum
        WHERE n.nspname = 'public'
          AND c.relname = ANY(%s)
          AND con.contype IN ('p', 'u')
        GROUP BY c.relname, con.conname, con.contype
        ORDER BY c.relname, con.conname
        """,
        (list(table_names),),
    )
    constraints: dict[str, list[CurrentUniqueConstraint]] = {}
    for row in cur.fetchall():
        table_name = str(row["table_name"])
        constraints.setdefault(table_name, []).append(
            CurrentUniqueConstraint(
                table_name=table_name,
                constraint_name=str(row["constraint_name"]),
                columns=tuple(str(column) for column in row["columns"]),
                kind=str(row["kind"]),
            )
        )
    cur.execute(
        """
        SELECT tbl.relname AS table_name,
               idx.relname AS constraint_name,
               'unique_index' AS kind,
               array_agg(att.attname ORDER BY key_order.ordinality) AS columns
        FROM pg_index i
        JOIN pg_class idx ON idx.oid = i.indexrelid
        JOIN pg_class tbl ON tbl.oid = i.indrelid
        JOIN pg_namespace n ON n.oid = tbl.relnamespace
        JOIN unnest(i.indkey) WITH ORDINALITY AS key_order(attnum, ordinality)
          ON true
        JOIN pg_attribute att
          ON att.attrelid = tbl.oid
         AND att.attnum = key_order.attnum
        LEFT JOIN pg_constraint con
          ON con.conindid = i.indexrelid
        WHERE n.nspname = 'public'
          AND tbl.relname = ANY(%s)
          AND i.indisunique
          AND con.oid IS NULL
          AND key_order.attnum > 0
        GROUP BY tbl.relname, idx.relname
        ORDER BY tbl.relname, idx.relname
        """,
        (list(table_names),),
    )
    for row in cur.fetchall():
        table_name = str(row["table_name"])
        constraints.setdefault(table_name, []).append(
            CurrentUniqueConstraint(
                table_name=table_name,
                constraint_name=str(row["constraint_name"]),
                columns=tuple(str(column) for column in row["columns"]),
                kind=str(row["kind"]),
            )
        )
    return {table: tuple(items) for table, items in constraints.items()}


def unique_constraint_satisfied(
    target: TargetUniqueConstraint,
    current_constraints: Sequence[CurrentUniqueConstraint],
) -> bool:
    for current in current_constraints:
        if tuple(current.columns) != tuple(target.columns):
            continue
        if target.kind == "primary_key":
            if current.kind == "primary_key":
                return True
        elif current.kind in {"primary_key", "unique_constraint", "unique_index"}:
            return True
    return False


def build_quality_items(
    *,
    target_schema: TargetSchema,
    current_metadata: CurrentSchemaMetadata,
    missing_tables: tuple[str, ...],
    missing_columns: tuple[MissingColumn, ...],
    type_mismatches: tuple[TypeMismatch, ...],
    missing_unique_constraints: tuple[MissingUniqueConstraint, ...],
    migration_safe_to_apply: bool,
    manual_review_required: bool,
) -> list[dict[str, Any]]:
    return [
        quality_item(
            "P0",
            "passed" if current_metadata.checked_readonly else "failed",
            "n3_3_readonly_metadata_checked",
            "N3-3 must use a read-only PostgreSQL metadata check",
            expected="checked_readonly=true",
            actual=str(current_metadata.checked_readonly).lower(),
        ),
        quality_item(
            "P0",
            "passed" if not target_schema.unsafe_sql_hits else "failed",
            "n3_schema_no_dml_or_destructive_sql",
            "006/007/008 schema drafts must not contain DML or destructive SQL",
            expected="no DROP/INSERT/UPDATE/DELETE/TRUNCATE/COPY",
            actual="none" if not target_schema.unsafe_sql_hits else ",".join(target_schema.unsafe_sql_hits),
        ),
        quality_item(
            "P0",
            "passed" if not target_schema.forbidden_runtime_table_hits else "failed",
            "n3_schema_no_runtime_table_names",
            "N3 schema must not use *_runtime table names",
            expected="no *_runtime identifiers",
            actual=(
                "none"
                if not target_schema.forbidden_runtime_table_hits
                else ",".join(target_schema.forbidden_runtime_table_hits)
            ),
        ),
        quality_item(
            "P0",
            "passed" if not target_schema.forbidden_user_event_hits else "failed",
            "n3_schema_no_user_event_names",
            "N3 event names must not use User*",
            expected="no quoted User* event names",
            actual=(
                "none"
                if not target_schema.forbidden_user_event_hits
                else ",".join(target_schema.forbidden_user_event_hits)
            ),
        ),
        quality_item(
            "P0",
            "passed" if not current_metadata.missing_dependency_tables else "failed",
            "n3_dependency_tables_exist",
            "N3 schema readiness requires N2 condition run and minute target scope tables to exist",
            expected=",".join(REQUIRED_N2_DEPENDENCY_TABLES),
            actual=(
                "present"
                if not current_metadata.missing_dependency_tables
                else ",".join(current_metadata.missing_dependency_tables)
            ),
        ),
        quality_item(
            "P0",
            "passed" if not type_mismatches else "failed",
            "n3_schema_no_type_mismatch",
            "Existing N3 tables must not disagree with 006/007/008 column types",
            expected="no type mismatch",
            actual="none" if not type_mismatches else str([item.to_dict() for item in type_mismatches]),
        ),
        quality_item(
            "P1",
            "warning" if missing_tables else "passed",
            "n3_schema_missing_tables",
            "Missing N3 tables require additive CREATE TABLE migration draft",
            expected="all target tables exist, or additive draft generated",
            actual="none" if not missing_tables else ",".join(missing_tables),
        ),
        quality_item(
            "P1",
            "warning" if missing_columns else "passed",
            "n3_schema_missing_columns",
            "Existing N3 tables with column gaps require additive column migration review",
            expected="no missing columns on existing tables",
            actual="none" if not missing_columns else str([item.to_dict() for item in missing_columns]),
        ),
        quality_item(
            "P1",
            "warning" if missing_unique_constraints else "passed",
            "n3_schema_missing_unique_constraints",
            "Existing N3 tables with unique constraint gaps require manual duplicate-risk review",
            expected="all target unique constraints exist",
            actual=(
                "none"
                if not missing_unique_constraints
                else str([item.to_dict() for item in missing_unique_constraints])
            ),
        ),
        quality_item(
            "P1",
            "warning" if manual_review_required else "passed",
            "n3_schema_manual_review_required",
            "Manual review is required when gaps are not missing-table-only additive creates",
            expected="manual_review_required=false for clean first-apply/additive table create",
            actual=str(manual_review_required).lower(),
        ),
        quality_item(
            "P1",
            "passed" if migration_safe_to_apply else "warning",
            "n3_schema_migration_safe_to_apply",
            "Migration can be considered safe only when metadata gaps are missing-table-only additive creates",
            expected="migration_safe_to_apply=true",
            actual=str(migration_safe_to_apply).lower(),
        ),
        quality_item("P0", "passed", "n3_3_no_migration_execute", "N3-3 does not execute migration SQL"),
        quality_item("P0", "passed", "n3_3_no_business_writes", "N3-3 does not write business data"),
        quality_item("P0", "passed", "n3_3_no_market_data_pull", "N3-3 does not pull market data"),
        quality_item("P0", "passed", "n3_3_no_worker_or_downstream", "N3-3 does not start workers or enter N4/N5/N6"),
    ]


def generate_additive_migration_sql(report: N3SchemaGapReport) -> str:
    lines = [
        "-- A-share monitor v3 N3 market-data schema migration gap draft.",
        "-- Stage N3-3 only: generated for review; do not execute without explicit user confirmation.",
        "-- This file is additive only: CREATE TABLE IF NOT EXISTS, ADD COLUMN IF NOT EXISTS,",
        "-- CREATE INDEX IF NOT EXISTS, and guarded ADD CONSTRAINT blocks.",
        "-- N3-3 itself did not execute this SQL.",
        "",
        "BEGIN;",
        "",
    ]
    if not report.migration_required:
        lines.append("-- No N3 schema gaps detected.")
    for table_name in report.missing_tables:
        target_table = report.target_schema.tables[table_name]
        lines.append(rewrite_create_table_if_not_exists(target_table.create_table_sql))
        lines.append("")
    for index in report.target_schema.indexes_for_missing_tables(report.missing_tables):
        lines.append(rewrite_create_index_if_not_exists(index.raw_definition))
        lines.append("")

    missing_columns_by_table: dict[str, list[MissingColumn]] = {}
    for item in report.missing_columns:
        if item.additive_safe:
            missing_columns_by_table.setdefault(item.table_name, []).append(item)
    for table_name in report.target_schema.table_names:
        columns = missing_columns_by_table.get(table_name, [])
        if not columns:
            continue
        lines.append(f"ALTER TABLE {table_name}")
        for index, column in enumerate(columns):
            suffix = "," if index < len(columns) - 1 else ";"
            lines.append(f"  ADD COLUMN IF NOT EXISTS {column.column_name} {column.migration_type}{suffix}")
        lines.append("")

    if report.missing_unique_constraints:
        lines.extend(
            [
                "-- Unique constraints on existing tables need manual duplicate-risk review before execution.",
                "-- These guarded blocks are a draft only.",
                "",
            ]
        )
    for item in report.missing_unique_constraints:
        lines.extend(render_unique_constraint_sql(item))
        lines.append("")

    lines.extend(
        [
            "COMMIT;",
            "",
            "-- Rollback note:",
            "-- N3-3 did not execute this SQL. If a later confirmed migration applies it,",
            "-- rollback must be planned per object and only before dependent business rows exist.",
            "-- This draft intentionally does not include rollback SQL statements.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_unique_constraint_sql(item: MissingUniqueConstraint) -> list[str]:
    columns = ", ".join(item.columns)
    if item.kind == "unique_index":
        return [f"CREATE UNIQUE INDEX IF NOT EXISTS {item.constraint_name}", f"ON {item.table_name}({columns});"]
    constraint_type = "PRIMARY KEY" if item.kind == "primary_key" else "UNIQUE"
    return [
        "DO $$",
        "BEGIN",
        "  IF NOT EXISTS (",
        "    SELECT 1",
        "    FROM pg_constraint con",
        "    JOIN pg_class rel ON rel.oid = con.conrelid",
        "    JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace",
        f"    WHERE nsp.nspname = 'public' AND rel.relname = '{item.table_name}' AND con.conname = '{item.constraint_name}'",
        "  ) THEN",
        f"    ALTER TABLE {item.table_name} ADD CONSTRAINT {item.constraint_name} {constraint_type} ({columns});",
        "  END IF;",
        "END $$;",
    ]


def format_market_data_schema_gap_markdown(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    side_effects = report["side_effects"]
    lines = [
        "# N3-3 Market Data Schema Gap Plan",
        "",
        "## Summary",
        "",
        f"- stage: {report['stage']}",
        f"- layer_role: {report['layer_role']}",
        f"- schema_paths: {report['schema_paths']}",
        f"- migration_sql_path: {report['migration_sql_path']}",
        f"- checked_readonly: {str(report['checked_readonly']).lower()}",
        f"- migration_required: {str(report['migration_required']).lower()}",
        f"- manual_review_required: {str(report['manual_review_required']).lower()}",
        f"- migration_safe_to_apply: {str(report['migration_safe_to_apply']).lower()}",
        f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
        "",
        "## Gap Plan",
        "",
        f"- missing_tables: {report['missing_tables']}",
        f"- missing_columns: {report['missing_columns']}",
        f"- type_mismatch: {report['type_mismatch']}",
        f"- missing_unique_constraints: {report['missing_unique_constraints']}",
        f"- missing_dependency_tables: {report['missing_dependency_tables']}",
        "",
        "## Quality",
        "",
    ]
    for item in quality["items"]:
        lines.append(
            f"- {item['severity']} {item['status']} {item['gate_code']}: "
            f"expected={item.get('expected_value')} actual={item.get('actual_value')}"
        )
    lines.extend(
        [
            "",
            "## Boundary Confirmation",
            "",
            f"- read_only_database_checks: {str(side_effects['read_only_database_checks']).lower()}",
            f"- will_execute_sql: {str(side_effects['will_execute_sql']).lower()}",
            f"- migration_executed: {str(side_effects['migration_executed']).lower()}",
            f"- writes_performed: {str(side_effects['writes_performed']).lower()}",
            f"- market_data_pulled: {str(side_effects['market_data_pulled']).lower()}",
            f"- market_data_fact_written: {str(side_effects['market_data_fact_written']).lower()}",
            f"- downstream_layers_touched: {str(side_effects['downstream_layers_touched']).lower()}",
            f"- worker_started: {str(side_effects['worker_started']).lower()}",
            f"- old_system_touched: {str(side_effects['old_system_touched']).lower()}",
            "",
            "## Rollback",
            "",
            "N3-3 did not execute migration SQL and did not write database rows. "
            "Rollback for this stage is deleting the generated report and 009 SQL draft if needed.",
            "",
        ]
    )
    return "\n".join(lines)


def rewrite_create_table_if_not_exists(create_sql: str) -> str:
    return re.sub(
        r"\bCREATE\s+TABLE\s+(?!IF\s+NOT\s+EXISTS)",
        "CREATE TABLE IF NOT EXISTS ",
        create_sql.strip(),
        count=1,
        flags=re.IGNORECASE,
    )


def rewrite_create_index_if_not_exists(index_sql: str) -> str:
    rewritten = re.sub(
        r"\bCREATE\s+(UNIQUE\s+)?INDEX\s+(?!IF\s+NOT\s+EXISTS)",
        lambda match: f"CREATE {match.group(1) or ''}INDEX IF NOT EXISTS ",
        index_sql.strip(),
        count=1,
        flags=re.IGNORECASE,
    )
    return rewritten if rewritten.endswith(";") else f"{rewritten};"


def strip_line_comments(sql_text: str) -> str:
    return "\n".join(line.split("--", 1)[0] for line in sql_text.splitlines())


def compact_sql_fragment(text: str) -> str:
    return " ".join(text.strip().rstrip(";").split())


def first_constraint_index(definition: str) -> int:
    lower = definition.lower()
    indexes = [
        match.start()
        for keyword in CONSTRAINT_KEYWORDS
        for match in [re.search(rf"\b{re.escape(keyword)}\b", lower)]
        if match is not None
    ]
    return min(indexes) if indexes else len(definition)


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
        "bigint": "bigint",
        "integer": "integer",
        "boolean": "boolean",
        "numeric": "numeric",
        "jsonb": "jsonb",
        "timestamp with time zone": "timestamptz",
        "timestamptz": "timestamptz",
    }
    return aliases.get(normalized, normalized)


def stable_unique_name(table_name: str, columns: Sequence[str]) -> str:
    base = f"uq_{table_name}_{'_'.join(columns)}"
    if len(base) <= 60:
        return base
    digest = sha1(base.encode("utf-8")).hexdigest()[:8]
    return f"uq_{table_name}_{digest}"
