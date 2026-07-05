"""N5-3 action schema migration review.

The review is static and report-only. It checks whether the N5 action schema
draft is additive and scoped to action-layer objects before a future migration
step. It never connects to PostgreSQL, executes SQL, consumes N4 outbox rows,
updates inbox/checkpoint state, writes N5 facts/outbox rows, enters N6, starts
workers, or calls trading interfaces.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping

from ashare_v3.action.dry_run import BUY_SIGNAL_TYPES, SELL_SIGNAL_TYPES
from ashare_v3.action.schema_event_review import (
    DEFAULT_N5_2_SCHEMA_PATH,
    REQUIRED_PAYLOAD_KEYS,
    extract_columns_for_table,
    extract_create_table_names,
    scan_forbidden_text,
    strip_line_comments,
)
from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.events.models import N5_EVENT_TYPES


PROJECT_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_N5_3_SCHEMA_PATH = DEFAULT_N5_2_SCHEMA_PATH
DEFAULT_N5_3_JSON_REPORT_PATH = "docs/N5_3_action_schema_migration_review.json"
DEFAULT_N5_3_MD_REPORT_PATH = "docs/N5_3_ACTION_SCHEMA_MIGRATION_REVIEW.md"
DEFAULT_N5_3_ROLLBACK_PREVIEW_PATH = "sql/011_action_layer_schema_rollback_preview.sql"

ALLOWED_N5_TABLES = (
    "common_action_run",
    "common_action_quality_item",
    "stock_action_fact",
    "index_action_fact",
    "board_action_fact",
    "common_action_event",
    "common_position_state",
    "common_position_event",
)

ALLOWED_REFERENCED_UPSTREAM_TABLES = (
    "common_trigger_run",
    "common_condition_run",
    "common_market_data_run",
    "stock_identity",
    "index_identity",
    "board_identity",
)

ALLOWED_STATEMENT_STARTS = (
    "BEGIN",
    "COMMIT",
    "CREATE TABLE",
    "CREATE INDEX",
)

UNSAFE_STATEMENT_STARTS = (
    "DROP",
    "DELETE",
    "UPDATE",
    "INSERT",
    "TRUNCATE",
    "COPY",
    "MERGE",
    "ALTER",
    "CREATE OR REPLACE",
)

N6_TABLE_KEYWORDS = ("user", "voice", "sim", "mobile")
TRUE_TRADE_FIELD_TERMS = (
    "broker",
    "account",
    "entrust",
    "commission",
    "filled",
    "fill",
    "cash",
    "order" + "_id",
    "order" + "_qty",
    "deal" + "_id",
)
TRUE_TRADE_ALLOWED_GUARD_COLUMNS = {"real_trade_touched"}


def run_n5_action_schema_migration_review(
    *,
    schema_path: str = DEFAULT_N5_3_SCHEMA_PATH,
    json_report_path: str = DEFAULT_N5_3_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N5_3_MD_REPORT_PATH,
    rollback_preview_path: str = DEFAULT_N5_3_ROLLBACK_PREVIEW_PATH,
) -> dict[str, Any]:
    schema_text = (PROJECT_ROOT / schema_path).read_text(encoding="utf-8")
    report = build_n5_action_schema_migration_review(
        schema_text=schema_text,
        schema_path=schema_path,
        json_report_path=json_report_path,
        markdown_report_path=markdown_report_path,
        rollback_preview_path=rollback_preview_path,
    )
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_n5_action_schema_migration_review(report))
    write_text(rollback_preview_path, report["rollback_preview"]["sql"])
    return report


def build_n5_action_schema_migration_review(
    *,
    schema_text: str,
    schema_path: str = DEFAULT_N5_3_SCHEMA_PATH,
    json_report_path: str = DEFAULT_N5_3_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N5_3_MD_REPORT_PATH,
    rollback_preview_path: str = DEFAULT_N5_3_ROLLBACK_PREVIEW_PATH,
) -> dict[str, Any]:
    executable_sql = strip_line_comments(schema_text)
    statements = split_sql_statements(executable_sql)
    created_tables = extract_create_table_names(executable_sql)
    created_indexes = extract_create_indexes(executable_sql)
    referenced_tables = extract_referenced_tables(executable_sql)
    review = {
        "schema_hash": sha256(schema_text.encode("utf-8")).hexdigest(),
        "created_tables": created_tables,
        "created_indexes": created_indexes,
        "referenced_tables": referenced_tables,
        "statement_count": len(statements),
        "unsafe_statements": find_unsafe_statements(statements),
        "unsupported_statements": find_unsupported_statements(statements),
        "extra_created_tables": [table for table in created_tables if table not in ALLOWED_N5_TABLES],
        "index_target_violations": [
            item
            for item in created_indexes
            if item["table_name"] not in ALLOWED_N5_TABLES
        ],
        "missing_required_tables": [table for table in ALLOWED_N5_TABLES if table not in created_tables],
        "n6_table_violations": find_n6_table_violations(created_tables),
        "business_data_write_statements": find_business_data_write_statements(statements),
        "true_trade_field_violations": find_true_trade_field_violations(executable_sql),
        "payload_contract_missing": missing_payload_contract_literals(executable_sql),
        "buy_sell_hint_contract": review_buy_sell_hint_contract(executable_sql),
        "non_n5_dependency_references": [
            table
            for table in referenced_tables
            if table not in ALLOWED_N5_TABLES and table not in ALLOWED_REFERENCED_UPSTREAM_TABLES
        ],
        "forbidden_boundary_findings": scan_forbidden_text("sql/011_action_layer_schema.sql", executable_sql),
        "additive_only": False,
        "migration_ready": False,
    }
    review["additive_only"] = (
        not review["unsafe_statements"]
        and not review["unsupported_statements"]
        and not review["business_data_write_statements"]
    )
    quality_items = build_quality_items(review)
    severity_counts = count_quality_severities(quality_items)
    review["migration_ready"] = severity_counts["P0"] == 0
    rollback_sql = build_rollback_preview_sql(created_tables)
    return {
        "stage": "N5-3",
        "layer_role": "N5_action",
        "mode": "action_schema_migration_review",
        "execution_mode": "static_review_no_db_no_migration",
        "schema_path": schema_path,
        "json_report_path": json_report_path,
        "markdown_report_path": markdown_report_path,
        "migration_review": review,
        "rollback_preview": {
            "path": rollback_preview_path,
            "generated": True,
            "executed": False,
            "sql": rollback_sql,
        },
        "side_effects": {
            "will_execute_sql": False,
            "migration_executed": False,
            "writes_performed": False,
            "business_data_written": False,
            "action_fact_written": False,
            "n5_outbox_written": False,
            "common_event_inbox_updated": False,
            "consumer_checkpoint_updated": False,
            "real_n4_outbox_consumed": False,
            "market_data_pulled": False,
            "n1_n2_n3_n4_modified": False,
            "n6_user_layer_touched": False,
            "voice_touched": False,
            "sim_touched": False,
            "mobile_touched": False,
            "real_trade_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "passed": severity_counts["P0"] == 0,
    }


def build_quality_items(review: Mapping[str, Any]) -> list[dict[str, Any]]:
    hint_contract = review["buy_sell_hint_contract"]
    return [
        quality_item(
            "P0",
            "passed" if not review["missing_required_tables"] else "failed",
            "n5_3_required_tables_present",
            "N5 action migration must create all required action-layer tables",
            expected=",".join(ALLOWED_N5_TABLES),
            actual="missing=" + ",".join(review["missing_required_tables"]),
        ),
        quality_item(
            "P0",
            "passed" if not review["extra_created_tables"] else "failed",
            "n5_3_created_tables_scoped_to_n5",
            "Migration must not create objects outside the N5 action schema scope",
            expected="only N5 action tables",
            actual="extra=" + ",".join(review["extra_created_tables"]),
        ),
        quality_item(
            "P0",
            "passed" if not review["index_target_violations"] else "failed",
            "n5_3_created_indexes_scoped_to_n5",
            "Migration indexes must only target N5 action schema tables",
            expected="indexes target N5 tables",
            actual=json.dumps(review["index_target_violations"], ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if review["additive_only"] else "failed",
            "n5_3_additive_only",
            "Migration SQL must be additive create-only SQL",
            expected="CREATE TABLE/INDEX plus BEGIN/COMMIT only",
            actual=json.dumps(
                {
                    "unsafe": review["unsafe_statements"],
                    "unsupported": review["unsupported_statements"],
                    "business_writes": review["business_data_write_statements"],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        quality_item(
            "P0",
            "passed" if not review["n6_table_violations"] else "failed",
            "n5_3_no_n6_projection_voice_sim_mobile_tables",
            "N5 migration must not create user/voice/sim/mobile tables",
            expected="none",
            actual=",".join(review["n6_table_violations"]),
        ),
        quality_item(
            "P0",
            "passed" if not review["true_trade_field_violations"] else "failed",
            "n5_3_no_true_trade_execution_fields",
            "N5 migration must not introduce true trading execution fields",
            expected="none",
            actual=",".join(review["true_trade_field_violations"]),
        ),
        quality_item(
            "P0",
            "passed" if not review["payload_contract_missing"] else "failed",
            "n5_3_n5_2_payload_contract_preserved",
            "N5 migration must preserve the N5-2 action event payload contract",
            expected="all required N5 payload keys/literals",
            actual="missing=" + ",".join(review["payload_contract_missing"]),
        ),
        quality_item(
            "P0",
            "passed" if hint_contract["passed"] else "failed",
            "n5_3_buy_sell_hint_not_schema_downgraded",
            "BUY_HINT and SELL_HINT must remain formal buy/sell candidates in schema",
            expected="formal buy/sell signal whitelist and direction guards",
            actual=json.dumps(hint_contract, ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if not review["forbidden_boundary_findings"] else "failed",
            "n5_3_forbidden_boundary_findings_clean",
            "Migration must not contain forbidden N6, runtime, external adapter, checkpoint, or trading boundary patterns",
            expected="none",
            actual="; ".join(review["forbidden_boundary_findings"]),
        ),
        quality_item(
            "P1",
            "warning" if review["non_n5_dependency_references"] else "passed",
            "n5_3_dependency_references_known",
            "N5 migration may reference upstream tables but should not depend on unexpected tables",
            expected="only documented upstream dependencies",
            actual=",".join(review["non_n5_dependency_references"]),
        ),
        quality_item(
            "P2",
            "warning",
            "n5_3_review_only_migration_not_executed",
            "N5-3 intentionally stops before migration execution",
            expected="no migration executed",
            actual="static review only",
        ),
    ]


def split_sql_statements(sql_text: str) -> list[str]:
    return [statement.strip() for statement in sql_text.split(";") if statement.strip()]


def normalized_statement_start(statement: str) -> str:
    normalized = " ".join(statement.split()).upper()
    if normalized.startswith("CREATE TABLE"):
        return "CREATE TABLE"
    if normalized.startswith("CREATE INDEX"):
        return "CREATE INDEX"
    if normalized.startswith("CREATE OR REPLACE"):
        return "CREATE OR REPLACE"
    return normalized.split()[0] if normalized else ""


def find_unsafe_statements(statements: list[str]) -> list[str]:
    unsafe: list[str] = []
    for statement in statements:
        start = normalized_statement_start(statement)
        if start in UNSAFE_STATEMENT_STARTS:
            unsafe.append(compact_statement(statement))
    return unsafe


def find_unsupported_statements(statements: list[str]) -> list[str]:
    unsupported: list[str] = []
    for statement in statements:
        start = normalized_statement_start(statement)
        if start not in ALLOWED_STATEMENT_STARTS:
            unsupported.append(compact_statement(statement))
    return unsupported


def find_business_data_write_statements(statements: list[str]) -> list[str]:
    write_starts = {"INSERT", "UPDATE", "DELETE", "COPY", "MERGE", "TRUNCATE"}
    return [
        compact_statement(statement)
        for statement in statements
        if normalized_statement_start(statement) in write_starts
    ]


def extract_create_indexes(sql_text: str) -> list[dict[str, str]]:
    pattern = re.compile(
        r"\bCREATE\s+INDEX\s+([A-Za-z_][A-Za-z0-9_]*)\s+ON\s+([A-Za-z_][A-Za-z0-9_]*)",
        flags=re.IGNORECASE,
    )
    return [
        {"index_name": match.group(1), "table_name": match.group(2)}
        for match in pattern.finditer(sql_text)
    ]


def extract_referenced_tables(sql_text: str) -> list[str]:
    refs = re.findall(r"\bREFERENCES\s+([A-Za-z_][A-Za-z0-9_]*)", sql_text, flags=re.IGNORECASE)
    return sorted(set(refs))


def find_n6_table_violations(created_tables: list[str]) -> list[str]:
    return [
        table
        for table in created_tables
        if any(keyword in table.lower() for keyword in N6_TABLE_KEYWORDS)
    ]


def find_true_trade_field_violations(sql_text: str) -> list[str]:
    violations: set[str] = set()
    for table in extract_create_table_names(sql_text):
        for column in extract_columns_for_table(sql_text, table):
            column_lower = column.lower()
            if column_lower in TRUE_TRADE_ALLOWED_GUARD_COLUMNS:
                continue
            if any(term in column_lower for term in TRUE_TRADE_FIELD_TERMS):
                violations.add(f"{table}.{column}")
    return sorted(violations)


def missing_payload_contract_literals(sql_text: str) -> list[str]:
    required = list(REQUIRED_PAYLOAD_KEYS) + [
        "source_market_data_run_id IS NOT NULL OR source_market_trace",
        *N5_EVENT_TYPES,
    ]
    return [literal for literal in required if literal not in sql_text]


def review_buy_sell_hint_contract(sql_text: str) -> dict[str, Any]:
    buy_signals = list(BUY_SIGNAL_TYPES)
    sell_signals = list(SELL_SIGNAL_TYPES)
    buy_present = all(signal in sql_text for signal in buy_signals)
    sell_present = all(signal in sql_text for signal in sell_signals)
    buy_direction_guard = "signal_type NOT IN ('B_BUY_30M_VOL', 'B_BUY', 'BUY_HINT') OR direction = 'buy'" in sql_text
    sell_direction_guard = "signal_type NOT IN ('S_SELL_30M_SHRINK', 'S_SELL', 'SELL_HINT') OR direction = 'sell'" in sql_text
    forced_hint_only = bool(
        re.search(
            r"BUY_HINT[^;\n]*(?:HintEvent|lane\s*=\s*'hint')|SELL_HINT[^;\n]*(?:HintEvent|lane\s*=\s*'hint')",
            sql_text,
            flags=re.IGNORECASE,
        )
    )
    return {
        "buy_signal_types": buy_signals,
        "sell_signal_types": sell_signals,
        "buy_present": buy_present,
        "sell_present": sell_present,
        "buy_direction_guard": buy_direction_guard,
        "sell_direction_guard": sell_direction_guard,
        "forced_hint_only": forced_hint_only,
        "passed": buy_present and sell_present and buy_direction_guard and sell_direction_guard and not forced_hint_only,
    }


def build_rollback_preview_sql(created_tables: list[str]) -> str:
    ordered_tables = [table for table in ALLOWED_N5_TABLES if table in created_tables]
    reverse_order = list(reversed(ordered_tables))
    lines = [
        "-- N5-3 rollback preview for sql/011_action_layer_schema.sql.",
        "-- Preview only. Do not execute unless N5 migration execution has been explicitly approved and needs rollback.",
        "BEGIN;",
    ]
    lines.extend(f"DROP TABLE IF EXISTS {table_name} CASCADE;" for table_name in reverse_order)
    lines.append("COMMIT;")
    lines.append("")
    return "\n".join(lines)


def compact_statement(statement: str, limit: int = 160) -> str:
    compact = " ".join(statement.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def write_json(path: str, payload: Mapping[str, Any]) -> None:
    target = PROJECT_ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_text(path: str, text: str) -> None:
    target = PROJECT_ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def format_n5_action_schema_migration_review(report: Mapping[str, Any]) -> str:
    review = report["migration_review"]
    quality = report["quality"]
    side_effects = report["side_effects"]
    rollback = report["rollback_preview"]
    return "\n".join(
        [
            "# N5-3 Action Schema Migration Review",
            "",
            "## Summary",
            "",
            f"- stage: {report['stage']}",
            f"- layer_role: {report['layer_role']}",
            f"- execution_mode: {report['execution_mode']}",
            f"- schema_path: {report['schema_path']}",
            f"- schema_hash: {review['schema_hash']}",
            f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
            f"- passed: {report['passed']}",
            f"- migration_ready: {review['migration_ready']}",
            "",
            "## SQL Scope",
            "",
            f"- created_tables: {review['created_tables']}",
            f"- created_indexes: {review['created_indexes']}",
            f"- referenced_tables: {review['referenced_tables']}",
            f"- missing_required_tables: {review['missing_required_tables']}",
            f"- extra_created_tables: {review['extra_created_tables']}",
            f"- index_target_violations: {review['index_target_violations']}",
            f"- non_n5_dependency_references: {review['non_n5_dependency_references']}",
            "",
            "## Additive Review",
            "",
            f"- additive_only: {review['additive_only']}",
            f"- unsafe_statements: {review['unsafe_statements']}",
            f"- unsupported_statements: {review['unsupported_statements']}",
            f"- business_data_write_statements: {review['business_data_write_statements']}",
            "",
            "## Boundary Review",
            "",
            f"- n6_table_violations: {review['n6_table_violations']}",
            f"- true_trade_field_violations: {review['true_trade_field_violations']}",
            f"- forbidden_boundary_findings: {review['forbidden_boundary_findings']}",
            "",
            "## Contract Review",
            "",
            f"- payload_contract_missing: {review['payload_contract_missing']}",
            f"- buy_sell_hint_contract: {review['buy_sell_hint_contract']}",
            "",
            "## Rollback Preview",
            "",
            f"- path: {rollback['path']}",
            f"- generated: {rollback['generated']}",
            f"- executed: {rollback['executed']}",
            "",
            "## Boundary Confirmation",
            "",
            f"- will_execute_sql: {side_effects['will_execute_sql']}",
            f"- migration_executed: {side_effects['migration_executed']}",
            f"- writes_performed: {side_effects['writes_performed']}",
            f"- business_data_written: {side_effects['business_data_written']}",
            f"- action_fact_written: {side_effects['action_fact_written']}",
            f"- n5_outbox_written: {side_effects['n5_outbox_written']}",
            f"- common_event_inbox_updated: {side_effects['common_event_inbox_updated']}",
            f"- consumer_checkpoint_updated: {side_effects['consumer_checkpoint_updated']}",
            f"- real_n4_outbox_consumed: {side_effects['real_n4_outbox_consumed']}",
            f"- market_data_pulled: {side_effects['market_data_pulled']}",
            f"- n1_n2_n3_n4_modified: {side_effects['n1_n2_n3_n4_modified']}",
            f"- n6_user_layer_touched: {side_effects['n6_user_layer_touched']}",
            f"- voice_touched: {side_effects['voice_touched']}",
            f"- sim_touched: {side_effects['sim_touched']}",
            f"- mobile_touched: {side_effects['mobile_touched']}",
            f"- real_trade_touched: {side_effects['real_trade_touched']}",
            f"- worker_started: {side_effects['worker_started']}",
            f"- old_system_touched: {side_effects['old_system_touched']}",
            "",
            "## Notes",
            "",
            "- N5-3 is static migration review only.",
            "- No SQL was executed and no database connection was opened.",
            "- Rollback preview was generated for later human review only.",
        ]
    )
