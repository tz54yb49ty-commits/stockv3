"""Static review for the N3-4 market-data migration draft.

This review only inspects sql/009_market_data_schema_migration.sql. It does
not connect to PostgreSQL, execute migrations, write business data, pull
market data, start workers, or enter downstream layers.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Mapping

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.schema_gap_plan import (
    parse_column_list,
    parse_index_definitions,
    split_top_level_commas,
    strip_line_comments,
)


DEFAULT_009_MIGRATION_PATH = "sql/009_market_data_schema_migration.sql"
DEFAULT_N3_4_REVIEW_REPORT_PATH = "docs/N3_4_MARKET_DATA_MIGRATION_REVIEW.md"

ALLOWED_N3_MIGRATION_TABLES = (
    "common_market_data_run",
    "common_market_data_quality_item",
    "common_market_data_subscription_candidate",
    "common_market_data_subscription",
    "common_market_data_pull_plan",
    "stock_realtime_daily_snapshot",
    "index_realtime_daily_snapshot",
    "board_realtime_daily_snapshot",
    "stock_minute_bar_1m",
    "index_minute_bar_1m",
    "board_minute_bar_1m",
    "stock_previous_day_minute_preload_status",
    "index_previous_day_minute_preload_status",
    "board_previous_day_minute_preload_status",
    "common_event_ledger",
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_event_delivery_attempt",
)
REQUIRED_OUTBOX_UNIQUE_CONSTRAINTS = {
    "event_id": ("event_id",),
    "dedup": ("source_layer", "event_type", "source_run_id", "dedup_key", "event_schema_version"),
}
FORBIDDEN_EXECUTABLE_PATTERNS = {
    "drop_statement": r"(^|;)\s*DROP\b",
    "delete_statement": r"(^|;)\s*DELETE\b|\bDELETE\s+FROM\b",
    "update_statement": r"(^|;)\s*UPDATE\b",
    "truncate_statement": r"(^|;)\s*TRUNCATE\b",
    "alter_table_drop": r"\bALTER\s+TABLE\b[^;]*\bDROP\b",
    "insert_into": r"\bINSERT\s+INTO\b",
}
ALLOWED_STATEMENT_START_PATTERNS = (
    r"^BEGIN$",
    r"^COMMIT$",
    r"^CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\b",
    r"^CREATE\s+(UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\b",
    r"^ALTER\s+TABLE\s+[A-Za-z_][A-Za-z0-9_]*\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\b",
    r"^DO\s+\$\$",
)
FORBIDDEN_RUNTIME_IDENTIFIER = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*_runtime\b", re.IGNORECASE)
FORBIDDEN_USER_EVENT_LITERAL = re.compile(r"['\"]User[A-Za-z0-9_]+['\"]")


def review_market_data_009_migration(sql_text: str, *, sql_path: str = DEFAULT_009_MIGRATION_PATH) -> dict[str, Any]:
    executable_sql = strip_line_comments(sql_text)
    statements = split_sql_statements(executable_sql)
    created_tables = extract_create_table_names(executable_sql)
    index_tables = tuple(index.table_name for index in parse_index_definitions(executable_sql))
    alter_tables = extract_alter_table_names(executable_sql)
    target_tables = tuple(dict.fromkeys(created_tables + index_tables + alter_tables))
    out_of_scope_tables = tuple(table for table in target_tables if table not in ALLOWED_N3_MIGRATION_TABLES)
    forbidden_executable_hits = find_forbidden_executable_hits(executable_sql)
    unsupported_statements = tuple(statement for statement in statements if not statement_is_allowed(statement))
    runtime_identifier_hits = tuple(match.group(0) for match in FORBIDDEN_RUNTIME_IDENTIFIER.finditer(executable_sql))
    user_event_hits = tuple(match.group(0) for match in FORBIDDEN_USER_EVENT_LITERAL.finditer(executable_sql))
    outbox_uniques = extract_outbox_unique_constraints(executable_sql)
    outbox_event_id_unique_present = REQUIRED_OUTBOX_UNIQUE_CONSTRAINTS["event_id"] in outbox_uniques
    outbox_dedup_unique_present = REQUIRED_OUTBOX_UNIQUE_CONSTRAINTS["dedup"] in outbox_uniques
    fk_on_delete_count = len(re.findall(r"\bON\s+DELETE\b", executable_sql, flags=re.IGNORECASE))
    additive_only = not forbidden_executable_hits and not unsupported_statements
    target_scope_valid = not out_of_scope_tables and bool(target_tables)
    outbox_unique_constraints_present = outbox_event_id_unique_present and outbox_dedup_unique_present

    quality_items = build_quality_items(
        additive_only=additive_only,
        forbidden_executable_hits=forbidden_executable_hits,
        unsupported_statements=unsupported_statements,
        target_scope_valid=target_scope_valid,
        out_of_scope_tables=out_of_scope_tables,
        outbox_unique_constraints_present=outbox_unique_constraints_present,
        outbox_event_id_unique_present=outbox_event_id_unique_present,
        outbox_dedup_unique_present=outbox_dedup_unique_present,
        runtime_identifier_hits=runtime_identifier_hits,
        user_event_hits=user_event_hits,
    )
    severity_counts = count_quality_severities(quality_items)
    passed = severity_counts["P0"] == 0
    return {
        "stage": "N3-4",
        "layer_role": "N3_market_data",
        "review_mode": "market_data_migration_static_review",
        "sql_path": sql_path,
        "checked_sql_only": True,
        "additive_only": additive_only,
        "target_scope_valid": target_scope_valid,
        "target_tables": list(target_tables),
        "out_of_scope_tables": list(out_of_scope_tables),
        "forbidden_executable_hits": list(forbidden_executable_hits),
        "unsupported_statements": list(unsupported_statements),
        "foreign_key_on_delete_count": fk_on_delete_count,
        "foreign_key_on_delete_is_dml_delete": False,
        "common_event_outbox_unique_constraints": [list(columns) for columns in outbox_uniques],
        "common_event_outbox_event_id_unique_present": outbox_event_id_unique_present,
        "common_event_outbox_dedup_unique_present": outbox_dedup_unique_present,
        "outbox_unique_constraints_present": outbox_unique_constraints_present,
        "runtime_identifier_hits": list(runtime_identifier_hits),
        "user_event_hits": list(user_event_hits),
        "passed": passed,
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "side_effects": {
            "read_only_database_checks": False,
            "will_execute_sql": False,
            "migration_executed": False,
            "writes_performed": False,
            "market_data_pulled": False,
            "market_data_fact_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }


def build_market_data_009_migration_review(
    *,
    sql_path: str = DEFAULT_009_MIGRATION_PATH,
) -> dict[str, Any]:
    path = Path(sql_path)
    return review_market_data_009_migration(path.read_text(encoding="utf-8"), sql_path=str(path))


def split_sql_statements(sql_text: str) -> tuple[str, ...]:
    statements: list[str] = []
    start = 0
    index = 0
    in_single_quote = False
    in_dollar_quote = False
    while index < len(sql_text):
        if sql_text.startswith("$$", index):
            in_dollar_quote = not in_dollar_quote
            index += 2
            continue
        char = sql_text[index]
        next_char = sql_text[index + 1] if index + 1 < len(sql_text) else ""
        if char == "'" and next_char == "'":
            index += 2
            continue
        if char == "'" and not in_dollar_quote:
            in_single_quote = not in_single_quote
        elif char == ";" and not in_single_quote and not in_dollar_quote:
            statement = " ".join(sql_text[start:index].strip().split())
            if statement:
                statements.append(statement)
            start = index + 1
        index += 1
    tail = " ".join(sql_text[start:].strip().split())
    if tail:
        statements.append(tail)
    return tuple(statements)


def statement_is_allowed(statement: str) -> bool:
    return any(re.match(pattern, statement, flags=re.IGNORECASE | re.DOTALL) for pattern in ALLOWED_STATEMENT_START_PATTERNS)


def find_forbidden_executable_hits(executable_sql: str) -> tuple[str, ...]:
    hits: list[str] = []
    for label, pattern in FORBIDDEN_EXECUTABLE_PATTERNS.items():
        if re.search(pattern, executable_sql, flags=re.IGNORECASE | re.DOTALL):
            hits.append(label)
    return tuple(hits)


def extract_create_table_names(sql_text: str) -> tuple[str, ...]:
    return tuple(
        match.group("table")
        for match in re.finditer(
            r"\bCREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(?P<table>[A-Za-z_][A-Za-z0-9_]*)\b",
            sql_text,
            flags=re.IGNORECASE,
        )
    )


def extract_alter_table_names(sql_text: str) -> tuple[str, ...]:
    return tuple(
        match.group("table")
        for match in re.finditer(
            r"\bALTER\s+TABLE\s+(?P<table>[A-Za-z_][A-Za-z0-9_]*)\b",
            sql_text,
            flags=re.IGNORECASE,
        )
    )


def extract_outbox_unique_constraints(sql_text: str) -> tuple[tuple[str, ...], ...]:
    body = extract_create_table_body(sql_text, "common_event_outbox")
    if not body:
        return ()
    constraints: list[tuple[str, ...]] = []
    for part in split_top_level_commas(body):
        compact = " ".join(part.strip().split())
        match = re.match(
            r"(CONSTRAINT\s+[A-Za-z_][A-Za-z0-9_]*\s+)?UNIQUE\s*\((?P<cols>[^)]+)\)",
            compact,
            flags=re.IGNORECASE,
        )
        if match is not None:
            constraints.append(parse_column_list(match.group("cols")))
            continue
        if re.match(r"(CONSTRAINT|UNIQUE|PRIMARY\s+KEY)\b", compact, flags=re.IGNORECASE):
            continue
        column_match = re.match(
            r"(?P<column>[A-Za-z_][A-Za-z0-9_]*)\s+.+\bUNIQUE\b",
            compact,
            flags=re.IGNORECASE,
        )
        if column_match is not None:
            constraints.append((column_match.group("column").lower(),))
    return tuple(constraints)


def extract_create_table_body(sql_text: str, table_name: str) -> str:
    match = re.search(
        rf"\bCREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{re.escape(table_name)}\s*\(",
        sql_text,
        flags=re.IGNORECASE,
    )
    if match is None:
        return ""
    open_index = match.end() - 1
    close_index = find_matching_paren(sql_text, open_index)
    if close_index < 0:
        return ""
    return sql_text[open_index + 1 : close_index]


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


def build_quality_items(
    *,
    additive_only: bool,
    forbidden_executable_hits: tuple[str, ...],
    unsupported_statements: tuple[str, ...],
    target_scope_valid: bool,
    out_of_scope_tables: tuple[str, ...],
    outbox_unique_constraints_present: bool,
    outbox_event_id_unique_present: bool,
    outbox_dedup_unique_present: bool,
    runtime_identifier_hits: tuple[str, ...],
    user_event_hits: tuple[str, ...],
) -> list[dict[str, Any]]:
    return [
        quality_item(
            "P0",
            "passed" if additive_only else "failed",
            "n3_4_migration_additive_only",
            "009 migration must contain only additive schema statements",
            expected="CREATE TABLE/INDEX IF NOT EXISTS, ADD COLUMN IF NOT EXISTS, guarded ADD CONSTRAINT",
            actual=(
                "passed"
                if additive_only
                else f"forbidden={list(forbidden_executable_hits)} unsupported={list(unsupported_statements)}"
            ),
        ),
        quality_item(
            "P0",
            "passed" if not forbidden_executable_hits else "failed",
            "n3_4_no_destructive_or_dml_sql",
            "009 migration must not contain executable DROP/DELETE/UPDATE/TRUNCATE/INSERT INTO or ALTER TABLE DROP",
            expected="no destructive SQL or DML",
            actual="none" if not forbidden_executable_hits else ",".join(forbidden_executable_hits),
        ),
        quality_item(
            "P0",
            "passed" if target_scope_valid else "failed",
            "n3_4_target_tables_in_n3_scope",
            "009 migration targets must stay inside N3 market/event/control tables",
            expected="N3 market/event/control table set",
            actual="passed" if target_scope_valid else ",".join(out_of_scope_tables),
        ),
        quality_item(
            "P0",
            "passed" if outbox_unique_constraints_present else "failed",
            "n3_4_common_event_outbox_unique_constraints",
            "common_event_outbox must have stable unique constraints for event_id and N3 dedup",
            expected="event_id and source_layer,event_type,source_run_id,dedup_key,event_schema_version",
            actual=(
                "present"
                if outbox_unique_constraints_present
                else f"event_id={outbox_event_id_unique_present} dedup={outbox_dedup_unique_present}"
            ),
        ),
        quality_item(
            "P0",
            "passed" if not runtime_identifier_hits else "failed",
            "n3_4_no_runtime_table_names",
            "N3 formal table names must not use *_runtime",
            expected="no *_runtime identifiers",
            actual="none" if not runtime_identifier_hits else ",".join(runtime_identifier_hits),
        ),
        quality_item(
            "P0",
            "passed" if not user_event_hits else "failed",
            "n3_4_no_user_event_names",
            "N3 event contract must not use User* event names",
            expected="no quoted User* event names",
            actual="none" if not user_event_hits else ",".join(user_event_hits),
        ),
        quality_item("P0", "passed", "n3_4_no_migration_execute", "N3-4 does not execute migration SQL"),
        quality_item("P0", "passed", "n3_4_no_database_write", "N3-4 does not write database rows"),
        quality_item("P0", "passed", "n3_4_no_market_data_pull", "N3-4 does not pull market data"),
        quality_item("P0", "passed", "n3_4_no_worker_or_downstream", "N3-4 does not start workers or enter N4/N5/N6"),
    ]


def format_market_data_migration_review_markdown(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    side_effects = report["side_effects"]
    lines = [
        "# N3-4 Market Data Migration Review",
        "",
        "## Summary",
        "",
        f"- stage: {report['stage']}",
        f"- layer_role: {report['layer_role']}",
        f"- sql_path: {report['sql_path']}",
        f"- checked_sql_only: {str(report['checked_sql_only']).lower()}",
        f"- additive_only: {str(report['additive_only']).lower()}",
        f"- target_scope_valid: {str(report['target_scope_valid']).lower()}",
        f"- outbox_unique_constraints_present: {str(report['outbox_unique_constraints_present']).lower()}",
        f"- passed: {str(report['passed']).lower()}",
        f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
        "",
        "## SQL Findings",
        "",
        f"- target_tables: {report['target_tables']}",
        f"- out_of_scope_tables: {report['out_of_scope_tables']}",
        f"- forbidden_executable_hits: {report['forbidden_executable_hits']}",
        f"- unsupported_statements: {report['unsupported_statements']}",
        f"- foreign_key_on_delete_count: {report['foreign_key_on_delete_count']}",
        f"- foreign_key_on_delete_is_dml_delete: {str(report['foreign_key_on_delete_is_dml_delete']).lower()}",
        f"- runtime_identifier_hits: {report['runtime_identifier_hits']}",
        f"- user_event_hits: {report['user_event_hits']}",
        "",
        "## Outbox Contract",
        "",
        f"- common_event_outbox_unique_constraints: {report['common_event_outbox_unique_constraints']}",
        f"- event_id_unique_present: {str(report['common_event_outbox_event_id_unique_present']).lower()}",
        f"- dedup_unique_present: {str(report['common_event_outbox_dedup_unique_present']).lower()}",
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
            f"- will_execute_sql: {str(side_effects['will_execute_sql']).lower()}",
            f"- migration_executed: {str(side_effects['migration_executed']).lower()}",
            f"- writes_performed: {str(side_effects['writes_performed']).lower()}",
            f"- market_data_pulled: {str(side_effects['market_data_pulled']).lower()}",
            f"- market_data_fact_written: {str(side_effects['market_data_fact_written']).lower()}",
            f"- downstream_layers_touched: {str(side_effects['downstream_layers_touched']).lower()}",
            f"- worker_started: {str(side_effects['worker_started']).lower()}",
            f"- old_system_touched: {str(side_effects['old_system_touched']).lower()}",
            "",
            "## Review Conclusion",
            "",
            "The N3-4 review is a static migration review only. It does not authorize or execute 009.",
            "",
        ]
    )
    return "\n".join(lines)
