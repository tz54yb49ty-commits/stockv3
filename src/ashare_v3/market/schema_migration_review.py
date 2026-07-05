"""N3-0C market data schema migration review.

This module reviews the N3 market-data control-table schema draft and checks
the development database object state through a read-only connection. It never
executes migrations, writes market data facts, pulls quotes, or touches
downstream layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_schema_review_connect

from ashare_v3.condition.basis import count_quality_severities, quality_item


DEFAULT_MARKET_SCHEMA_PATH = "sql/006_market_data_layer_schema.sql"

REQUIRED_MARKET_CONTROL_TABLES = (
    "common_market_data_run",
    "common_market_data_quality_item",
    "common_market_data_subscription_candidate",
    "common_market_data_subscription",
    "common_market_data_pull_plan",
)

REQUIRED_DEPENDENCY_TABLES = (
    "common_condition_run",
    "stock_minute_target_scope",
    "index_minute_target_scope",
    "board_minute_target_scope",
)

REQUIRED_COLUMNS = {
    "common_market_data_run": (
        "run_id",
        "source_condition_run_id",
        "for_trade_date",
        "source_trade_date",
        "prev_trade_date",
        "mode",
        "status",
        "p0_count",
        "p1_count",
        "p2_count",
        "source_scope_row_count",
        "candidate_row_count",
        "subscription_row_count",
        "subscription_object_count",
        "dedup_ratio",
        "market_data_pulled",
        "market_data_fact_written",
        "downstream_layers_touched",
        "worker_started",
    ),
    "common_market_data_quality_item": (
        "run_id",
        "source_condition_run_id",
        "for_trade_date",
        "source_trade_date",
        "data_domain",
        "layer_scope",
        "gate_code",
        "severity",
        "status",
    ),
    "common_market_data_subscription_candidate": (
        "run_id",
        "source_condition_run_id",
        "for_trade_date",
        "source_trade_date",
        "prev_trade_date",
        "asset_kind",
        "identity_key",
        "required_data_kind",
        "data_trade_date",
        "source_scope_table",
        "source_scope_id",
        "source_condition_pool_id",
        "direction",
        "condition_key",
        "allowed_signal_types",
    ),
    "common_market_data_subscription": (
        "run_id",
        "source_condition_run_id",
        "for_trade_date",
        "source_trade_date",
        "prev_trade_date",
        "asset_kind",
        "identity_key",
        "required_data_kind",
        "data_trade_date",
        "source_scope_ids",
        "source_condition_pool_ids",
        "condition_keys",
        "directions",
        "allowed_signal_types",
    ),
    "common_market_data_pull_plan": (
        "run_id",
        "source_condition_run_id",
        "for_trade_date",
        "source_trade_date",
        "prev_trade_date",
        "asset_kind",
        "required_data_kind",
        "data_trade_date",
        "adapter_name",
        "subscription_count",
        "object_count",
        "execute_allowed",
    ),
}

REQUIRED_DATA_KIND_VALUES = (
    "realtime_daily_snapshot",
    "minute_bar_1m",
    "previous_day_minute_bar_1m",
)

DOWNSTREAM_KEYWORDS = (
    "trigger",
    "action",
    "mobile",
    "voice",
    "sim",
    "position",
    "worker",
)

FORBIDDEN_MARKET_FACT_TABLES = (
    "stock_realtime_daily_snapshot",
    "index_realtime_daily_snapshot",
    "board_realtime_daily_snapshot",
    "stock_minute_bar_1m",
    "index_minute_bar_1m",
    "board_minute_bar_1m",
    "stock_previous_day_minute_preload_status",
    "index_previous_day_minute_preload_status",
    "board_previous_day_minute_preload_status",
)

UNSAFE_SQL_PATTERNS = (
    r"(^|;)\s*DROP\b",
    r"(^|;)\s*INSERT\b",
    r"(^|;)\s*UPDATE\b",
    r"(^|;)\s*DELETE\b",
    r"(^|;)\s*TRUNCATE\b",
    r"(^|;)\s*COPY\b",
    r"\bCREATE\s+TRIGGER\b",
    r"(^|;)\s*ALTER\s+TABLE\b",
)


@dataclass(frozen=True)
class MarketSchemaSqlReview:
    schema_hash: str
    created_tables: tuple[str, ...]
    required_tables_missing: tuple[str, ...]
    extra_created_tables: tuple[str, ...]
    forbidden_created_tables: tuple[str, ...]
    forbidden_keyword_hits: tuple[str, ...]
    unsafe_sql_hits: tuple[str, ...]
    missing_columns_by_table: Mapping[str, tuple[str, ...]]
    required_data_kind_whitelist_present: bool
    trace_columns_present: bool
    dry_run_guard_columns_present: bool
    additive_create_only: bool
    static_ready: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_hash": self.schema_hash,
            "table_count": len(self.created_tables),
            "created_tables": list(self.created_tables),
            "required_tables": list(REQUIRED_MARKET_CONTROL_TABLES),
            "required_tables_missing": list(self.required_tables_missing),
            "extra_created_tables": list(self.extra_created_tables),
            "forbidden_created_tables": list(self.forbidden_created_tables),
            "forbidden_keyword_hits": list(self.forbidden_keyword_hits),
            "unsafe_sql_hits": list(self.unsafe_sql_hits),
            "missing_columns_by_table": {
                table: list(columns)
                for table, columns in self.missing_columns_by_table.items()
            },
            "required_data_kind_whitelist_present": self.required_data_kind_whitelist_present,
            "trace_columns_present": self.trace_columns_present,
            "dry_run_guard_columns_present": self.dry_run_guard_columns_present,
            "additive_create_only": self.additive_create_only,
            "static_ready": self.static_ready,
        }


def review_market_data_schema_sql(sql_text: str) -> MarketSchemaSqlReview:
    executable_sql = strip_line_comments(sql_text)
    created_tables = tuple(extract_create_table_names(executable_sql))
    created_table_set = set(created_tables)
    required_table_set = set(REQUIRED_MARKET_CONTROL_TABLES)
    required_tables_missing = tuple(table for table in REQUIRED_MARKET_CONTROL_TABLES if table not in created_table_set)
    extra_created_tables = tuple(table for table in created_tables if table not in required_table_set)
    forbidden_created_tables = tuple(
        table
        for table in created_tables
        if table in FORBIDDEN_MARKET_FACT_TABLES
        or table.startswith(("stock_", "index_", "board_"))
        or any(keyword in table for keyword in DOWNSTREAM_KEYWORDS)
    )
    forbidden_keyword_hits = tuple(
        keyword
        for keyword in DOWNSTREAM_KEYWORDS
        if re.search(rf"\b[A-Za-z_][A-Za-z0-9_]*{keyword}[A-Za-z0-9_]*\b", executable_sql, flags=re.IGNORECASE)
    )
    unsafe_sql_hits = tuple(
        pattern
        for pattern in UNSAFE_SQL_PATTERNS
        if re.search(pattern, executable_sql, flags=re.IGNORECASE)
    )
    missing_columns_by_table = missing_required_columns(executable_sql)
    required_data_kind_whitelist_present = all(value in executable_sql for value in REQUIRED_DATA_KIND_VALUES)
    subscription_columns = set(extract_columns_for_table(executable_sql, "common_market_data_subscription"))
    trace_columns_present = {
        "source_scope_ids",
        "source_condition_pool_ids",
        "condition_keys",
        "directions",
        "allowed_signal_types",
    }.issubset(subscription_columns)
    run_columns = set(extract_columns_for_table(executable_sql, "common_market_data_run"))
    dry_run_guard_columns_present = {
        "market_data_pulled",
        "market_data_fact_written",
        "downstream_layers_touched",
        "worker_started",
    }.issubset(run_columns)
    additive_create_only = (
        bool(created_tables)
        and not unsafe_sql_hits
        and not extra_created_tables
        and not forbidden_created_tables
    )
    static_ready = (
        additive_create_only
        and not required_tables_missing
        and not forbidden_keyword_hits
        and not missing_columns_by_table
        and required_data_kind_whitelist_present
        and trace_columns_present
        and dry_run_guard_columns_present
    )
    return MarketSchemaSqlReview(
        schema_hash=sha256(sql_text.encode("utf-8")).hexdigest(),
        created_tables=created_tables,
        required_tables_missing=required_tables_missing,
        extra_created_tables=extra_created_tables,
        forbidden_created_tables=forbidden_created_tables,
        forbidden_keyword_hits=forbidden_keyword_hits,
        unsafe_sql_hits=unsafe_sql_hits,
        missing_columns_by_table=missing_columns_by_table,
        required_data_kind_whitelist_present=required_data_kind_whitelist_present,
        trace_columns_present=trace_columns_present,
        dry_run_guard_columns_present=dry_run_guard_columns_present,
        additive_create_only=additive_create_only,
        static_ready=static_ready,
    )


def build_market_data_schema_migration_review(
    *,
    dsn: str,
    schema_path: str = DEFAULT_MARKET_SCHEMA_PATH,
) -> dict[str, Any]:
    sql_text = Path(schema_path).read_text(encoding="utf-8")
    sql_review = review_market_data_schema_sql(sql_text)
    database_status = fetch_market_schema_database_status(dsn)
    return build_market_data_schema_review_report(
        schema_path=schema_path,
        sql_review=sql_review,
        database_status=database_status,
    )


def fetch_market_schema_database_status(dsn: str) -> dict[str, Any]:
    objects = tuple(REQUIRED_MARKET_CONTROL_TABLES) + tuple(REQUIRED_DEPENDENCY_TABLES)
    with audited_n3_market_schema_review_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        object_status = {table: object_exists(cur, table) for table in objects}
        existing_market_tables = [
            table for table in REQUIRED_MARKET_CONTROL_TABLES if object_status.get(table)
        ]
        existing_columns_by_table = {
            table: fetch_table_columns(cur, table)
            for table in existing_market_tables
        }
    missing_market_tables = [
        table for table in REQUIRED_MARKET_CONTROL_TABLES if not object_status.get(table)
    ]
    dependency_missing = [
        table for table in REQUIRED_DEPENDENCY_TABLES if not object_status.get(table)
    ]
    missing_columns_existing_tables = {
        table: [
            column
            for column in REQUIRED_COLUMNS[table]
            if column not in existing_columns_by_table.get(table, set())
        ]
        for table in existing_market_tables
    }
    missing_columns_existing_tables = {
        table: columns
        for table, columns in missing_columns_existing_tables.items()
        if columns
    }
    return {
        "read_only_database_checks": True,
        "required_market_tables": list(REQUIRED_MARKET_CONTROL_TABLES),
        "market_tables_existing": existing_market_tables,
        "market_tables_missing": missing_market_tables,
        "market_table_existing_count": len(existing_market_tables),
        "market_table_missing_count": len(missing_market_tables),
        "dependency_tables": list(REQUIRED_DEPENDENCY_TABLES),
        "dependency_missing": dependency_missing,
        "missing_columns_existing_tables": missing_columns_existing_tables,
        "all_market_tables_missing": len(existing_market_tables) == 0,
        "all_market_tables_existing": len(missing_market_tables) == 0,
        "partial_market_tables_existing": bool(existing_market_tables) and bool(missing_market_tables),
    }


def build_market_data_schema_review_report(
    *,
    schema_path: str,
    sql_review: MarketSchemaSqlReview,
    database_status: Mapping[str, Any],
) -> dict[str, Any]:
    quality_items = build_schema_review_quality_items(sql_review, database_status)
    severity_counts = count_quality_severities(quality_items)
    ready_for_first_apply = (
        sql_review.static_ready
        and not database_status.get("dependency_missing")
        and bool(database_status.get("all_market_tables_missing"))
        and severity_counts["P0"] == 0
    )
    migration_required = bool(database_status.get("market_tables_missing"))
    manual_review_required = (
        bool(database_status.get("partial_market_tables_existing"))
        or bool(database_status.get("missing_columns_existing_tables"))
        or severity_counts["P0"] > 0
    )
    ready_for_user_migration_review = ready_for_first_apply and not manual_review_required
    return {
        "stage": "N3-0C",
        "plan_mode": "market_data_schema_migration_review",
        "schema_path": schema_path,
        "migration_required": migration_required,
        "migration_safe_to_apply_after_user_confirmation": ready_for_user_migration_review,
        "ready_for_first_apply": ready_for_first_apply,
        "manual_review_required": manual_review_required,
        "ready_for_user_migration_review": ready_for_user_migration_review,
        "user_confirmation_required": True,
        "static_sql_review": sql_review.to_dict(),
        "database_status": dict(database_status),
        "planned_migration": {
            "strategy": "first_apply_additive_create_tables",
            "schema_file": schema_path,
            "create_order": list(REQUIRED_MARKET_CONTROL_TABLES),
            "will_create_market_data_fact_tables": False,
            "will_write_business_rows": False,
            "will_pull_market_data": False,
            "will_execute_sql": False,
        },
        "rollback_plan": {
            "strategy": "manual_drop_new_control_tables_only_if_migration_is_later_applied",
            "drop_order": list(reversed(REQUIRED_MARKET_CONTROL_TABLES)),
            "business_data_rollback_required": False,
        },
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "side_effects": {
            "read_only_database_checks": True,
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


def build_schema_review_quality_items(
    sql_review: MarketSchemaSqlReview,
    database_status: Mapping[str, Any],
) -> list[dict[str, Any]]:
    items = [
        quality_item(
            "P0",
            "passed" if sql_review.static_ready else "failed",
            "market_schema_static_ready",
            "006 schema must be a static-ready N3 market-data control-table draft",
            expected="static_ready=true",
            actual=str(sql_review.static_ready).lower(),
            details=sql_review.to_dict(),
        ),
        quality_item(
            "P0",
            "passed" if not sql_review.required_tables_missing else "failed",
            "market_schema_required_tables_present",
            "006 schema must include all required common_market_data_* control tables",
            expected=",".join(REQUIRED_MARKET_CONTROL_TABLES),
            actual="present" if not sql_review.required_tables_missing else ",".join(sql_review.required_tables_missing),
        ),
        quality_item(
            "P0",
            "passed" if not sql_review.forbidden_created_tables else "failed",
            "market_schema_no_fact_or_downstream_tables",
            "N3-0C schema must not create market data facts or downstream tables",
            expected="common_market_data_* control tables only",
            actual="none" if not sql_review.forbidden_created_tables else ",".join(sql_review.forbidden_created_tables),
        ),
        quality_item(
            "P0",
            "passed" if not sql_review.unsafe_sql_hits else "failed",
            "market_schema_no_destructive_or_dml_sql",
            "006 schema review must not contain destructive SQL or DML",
            expected="no DROP/INSERT/UPDATE/DELETE/TRUNCATE/COPY/ALTER/trigger",
            actual="none" if not sql_review.unsafe_sql_hits else ",".join(sql_review.unsafe_sql_hits),
        ),
        quality_item(
            "P0",
            "passed" if not database_status.get("dependency_missing") else "failed",
            "market_schema_dependencies_exist",
            "N3 control-table migration requires N2 condition run and scope tables to exist first",
            expected=",".join(REQUIRED_DEPENDENCY_TABLES),
            actual="present" if not database_status.get("dependency_missing") else ",".join(database_status.get("dependency_missing") or []),
        ),
        quality_item(
            "P1",
            "warning" if database_status.get("partial_market_tables_existing") else "passed",
            "market_schema_partial_existing_tables",
            "Partial common_market_data_* tables require manual review before any migration",
            expected="all missing for first apply, or all existing",
            actual="partial" if database_status.get("partial_market_tables_existing") else "not_partial",
        ),
        quality_item(
            "P1",
            "warning" if database_status.get("missing_columns_existing_tables") else "passed",
            "market_schema_existing_table_column_gaps",
            "Existing common_market_data_* tables with column gaps require additive gap planning",
            expected="no existing table column gaps",
            actual="none" if not database_status.get("missing_columns_existing_tables") else str(database_status.get("missing_columns_existing_tables")),
        ),
        quality_item("P0", "passed", "market_schema_review_no_execute", "N3-0C review does not execute SQL or migration"),
        quality_item("P0", "passed", "market_schema_review_no_market_data_pull", "N3-0C review does not pull market data"),
        quality_item("P0", "passed", "market_schema_review_no_downstream_layers", "N3-0C review does not enter trigger/action/mobile/voice/sim"),
    ]
    return items


def format_market_schema_review_markdown(report: Mapping[str, Any]) -> str:
    static_review = report["static_sql_review"]
    database = report["database_status"]
    quality = report["quality"]
    side_effects = report["side_effects"]
    lines = [
        "# N3-0C Market Data Schema Migration Review",
        "",
        "## Summary",
        "",
        f"- schema_path: {report['schema_path']}",
        f"- migration_required: {str(report['migration_required']).lower()}",
        f"- ready_for_first_apply: {str(report['ready_for_first_apply']).lower()}",
        f"- ready_for_user_migration_review: {str(report['ready_for_user_migration_review']).lower()}",
        f"- migration_safe_to_apply_after_user_confirmation: {str(report['migration_safe_to_apply_after_user_confirmation']).lower()}",
        f"- manual_review_required: {str(report['manual_review_required']).lower()}",
        f"- user_confirmation_required: {str(report['user_confirmation_required']).lower()}",
        "",
        "## Static SQL Review",
        "",
        f"- schema_hash: {static_review['schema_hash']}",
        f"- static_ready: {str(static_review['static_ready']).lower()}",
        f"- additive_create_only: {str(static_review['additive_create_only']).lower()}",
        f"- created_tables: {static_review['created_tables']}",
        f"- required_tables_missing: {static_review['required_tables_missing']}",
        f"- extra_created_tables: {static_review['extra_created_tables']}",
        f"- forbidden_created_tables: {static_review['forbidden_created_tables']}",
        f"- unsafe_sql_hits: {static_review['unsafe_sql_hits']}",
        f"- required_data_kind_whitelist_present: {str(static_review['required_data_kind_whitelist_present']).lower()}",
        f"- trace_columns_present: {str(static_review['trace_columns_present']).lower()}",
        f"- dry_run_guard_columns_present: {str(static_review['dry_run_guard_columns_present']).lower()}",
        "",
        "## Database Status",
        "",
        f"- read_only_database_checks: {str(database['read_only_database_checks']).lower()}",
        f"- market_tables_existing: {database['market_tables_existing']}",
        f"- market_tables_missing: {database['market_tables_missing']}",
        f"- dependency_missing: {database['dependency_missing']}",
        f"- partial_market_tables_existing: {str(database['partial_market_tables_existing']).lower()}",
        f"- missing_columns_existing_tables: {database['missing_columns_existing_tables']}",
        "",
        "## Planned Migration",
        "",
        f"- strategy: {report['planned_migration']['strategy']}",
        f"- create_order: {report['planned_migration']['create_order']}",
        "- will_execute_sql: false",
        "- will_write_business_rows: false",
        "- will_pull_market_data: false",
        "",
        "## Quality",
        "",
        f"- P0: {quality['p0_count']}",
        f"- P1: {quality['p1_count']}",
        f"- P2: {quality['p2_count']}",
        "",
        "Quality items:",
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
            f"- old_system_touched: {str(side_effects['old_system_touched']).lower()}",
            f"- migration_executed: {str(side_effects['migration_executed']).lower()}",
            f"- will_execute_sql: {str(side_effects['will_execute_sql']).lower()}",
            f"- writes_performed: {str(side_effects['writes_performed']).lower()}",
            f"- market_data_pulled: {str(side_effects['market_data_pulled']).lower()}",
            f"- market_data_fact_written: {str(side_effects['market_data_fact_written']).lower()}",
            f"- downstream_layers_touched: {str(side_effects['downstream_layers_touched']).lower()}",
            f"- worker_started: {str(side_effects['worker_started']).lower()}",
            "",
            "## Rollback",
            "",
            "N3-0C did not execute a migration and did not write database rows. "
            "Rollback for this review stage is deleting this report and the review code if needed.",
            "",
            "If a later user-confirmed migration applies 006, rollback must be reviewed separately and limited to the new common_market_data_* control tables.",
            "",
        ]
    )
    return "\n".join(lines)


def strip_line_comments(sql_text: str) -> str:
    return "\n".join(line.split("--", 1)[0] for line in sql_text.splitlines())


def extract_create_table_names(sql_text: str) -> list[str]:
    return [
        match.group(1)
        for match in re.finditer(
            r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
            sql_text,
            flags=re.IGNORECASE,
        )
    ]


def extract_columns_for_table(sql_text: str, table_name: str) -> tuple[str, ...]:
    body = extract_create_table_body(sql_text, table_name)
    if body is None:
        return ()
    columns: list[str] = []
    for item in split_top_level_commas(body):
        item = item.strip()
        if not item:
            continue
        first = item.split(None, 1)[0].strip('"').lower()
        if first in {"primary", "foreign", "unique", "check", "constraint", "exclude"}:
            continue
        columns.append(first)
    return tuple(columns)


def extract_create_table_body(sql_text: str, table_name: str) -> str | None:
    match = re.search(
        rf"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{re.escape(table_name)}\s*\(",
        sql_text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    start = match.end()
    depth = 1
    index = start
    while index < len(sql_text):
        char = sql_text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return sql_text[start:index]
        index += 1
    return None


def split_top_level_commas(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    return parts


def missing_required_columns(sql_text: str) -> dict[str, tuple[str, ...]]:
    output: dict[str, tuple[str, ...]] = {}
    for table_name, required_columns in REQUIRED_COLUMNS.items():
        columns = set(extract_columns_for_table(sql_text, table_name))
        missing = tuple(column for column in required_columns if column not in columns)
        if missing:
            output[table_name] = missing
    return output


def object_exists(cur: psycopg.Cursor[dict[str, Any]], table_name: str) -> bool:
    cur.execute("SELECT to_regclass(%s) AS regclass", (f"public.{table_name}",))
    return cur.fetchone()["regclass"] is not None


def fetch_table_columns(cur: psycopg.Cursor[dict[str, Any]], table_name: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
        """,
        (table_name,),
    )
    return {str(row["column_name"]) for row in cur.fetchall()}
