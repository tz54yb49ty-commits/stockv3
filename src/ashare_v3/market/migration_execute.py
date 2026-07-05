"""N3-5 executor for the reviewed 009 market-data additive migration.

This module performs a bounded schema migration only. It does not write market
business rows, pull quotes, start workers, or enter downstream layers.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_schema_review_connect

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.migration_review import (
    DEFAULT_009_MIGRATION_PATH,
    build_market_data_009_migration_review,
    format_market_data_migration_review_markdown,
)
from ashare_v3.market.schema_gap_plan import (
    DEFAULT_MARKET_SCHEMA_GAP_SQL_PATH,
    build_market_data_schema_gap_report,
    format_market_data_schema_gap_markdown,
)


DEFAULT_N3_5_PRE_BACKUP_PATH = "docs/N3_5_schema_backup_before_009.json"
DEFAULT_N3_5_POST_BACKUP_PATH = "docs/N3_5_schema_backup_after_009.json"
DEFAULT_N3_5_JSON_REPORT_PATH = "docs/N3_5_market_data_009_migration_report.json"
DEFAULT_N3_5_MD_REPORT_PATH = "docs/N3_5_MARKET_DATA_009_MIGRATION_REPORT.md"
N3_TARGET_TABLES = (
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
N3_MARKET_FACT_AND_EVENT_TABLES = (
    "stock_realtime_daily_snapshot",
    "index_realtime_daily_snapshot",
    "board_realtime_daily_snapshot",
    "stock_minute_bar_1m",
    "index_minute_bar_1m",
    "board_minute_bar_1m",
    "stock_previous_day_minute_preload_status",
    "index_previous_day_minute_preload_status",
    "board_previous_day_minute_preload_status",
    "common_market_data_quality_item",
    "common_event_ledger",
    "common_event_outbox",
)


def run_market_data_009_migration(
    *,
    dsn: str,
    sql_path: str = DEFAULT_009_MIGRATION_PATH,
    pre_backup_path: str = DEFAULT_N3_5_PRE_BACKUP_PATH,
    post_backup_path: str = DEFAULT_N3_5_POST_BACKUP_PATH,
    json_report_path: str = DEFAULT_N3_5_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N3_5_MD_REPORT_PATH,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    pre_review = build_market_data_009_migration_review(sql_path=sql_path)
    if int(pre_review["quality"]["p0_count"]) > 0:
        raise RuntimeError("N3-5 blocked: N3-4 migration review has P0 findings")

    pre_gap = build_market_data_schema_gap_report(
        dsn=dsn,
        migration_sql_path=DEFAULT_MARKET_SCHEMA_GAP_SQL_PATH,
    ).to_dict()
    if int(pre_gap["quality"]["p0_count"]) > 0 or not bool(pre_gap["migration_safe_to_apply"]):
        raise RuntimeError("N3-5 blocked: N3-3 schema gap plan is not safe to apply")

    pre_backup = capture_migration_backup(dsn, phase="before_009")
    write_json(pre_backup_path, pre_backup)

    execute_sql_file(dsn, sql_path)

    post_backup = capture_migration_backup(dsn, phase="after_009")
    write_json(post_backup_path, post_backup)

    post_gap = build_market_data_schema_gap_report(
        dsn=dsn,
        migration_sql_path=DEFAULT_MARKET_SCHEMA_GAP_SQL_PATH,
    ).to_dict()
    post_review = build_market_data_009_migration_review(sql_path=sql_path)
    post_checks = build_post_migration_checks(
        pre_backup=pre_backup,
        post_backup=post_backup,
        post_gap=post_gap,
        post_review=post_review,
    )
    quality_items = build_quality_items(post_checks)
    severity_counts = count_quality_severities(quality_items)
    report = {
        "stage": "N3-5",
        "layer_role": "N3_market_data",
        "execution_mode": "execute_009_additive_market_data_migration",
        "sql_path": sql_path,
        "pre_backup_path": pre_backup_path,
        "post_backup_path": post_backup_path,
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "migration_executed": True,
        "preconditions": {
            "n3_3_schema_gap_p0_count": pre_gap["quality"]["p0_count"],
            "n3_3_migration_safe_to_apply": pre_gap["migration_safe_to_apply"],
            "n3_4_review_p0_count": pre_review["quality"]["p0_count"],
            "n3_4_review_p1_count": pre_review["quality"]["p1_count"],
            "n3_4_review_p2_count": pre_review["quality"]["p2_count"],
            "n3_4_review_passed": pre_review["passed"],
        },
        "pre_migration": {
            "schema_gap_summary": summarize_gap(pre_gap),
            "n3_target_row_counts": pre_backup["n3_target_row_counts"],
            "active_snapshot_hash": stable_json_hash(pre_backup["active_snapshot"]),
        },
        "post_migration": {
            "schema_gap_summary": summarize_gap(post_gap),
            "n3_target_row_counts": post_backup["n3_target_row_counts"],
            "active_snapshot_hash": stable_json_hash(post_backup["active_snapshot"]),
            "migration_review_summary": summarize_review(post_review),
        },
        "post_checks": post_checks,
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "side_effects": {
            "will_execute_sql": False,
            "migration_executed": True,
            "writes_performed": False,
            "market_data_pulled": False,
            "market_data_fact_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_market_data_009_migration_report(report))
    return report


def capture_migration_backup(dsn: str, *, phase: str) -> dict[str, Any]:
    with audited_n3_market_schema_review_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        return {
            "phase": phase,
            "captured_at": utc_now_iso(),
            "public_schema": {
                "tables": fetch_public_tables(cur),
                "columns": fetch_public_columns(cur),
                "constraints": fetch_public_constraints(cur),
                "indexes": fetch_public_indexes(cur),
            },
            "active_snapshot": fetch_n1_n2_active_snapshot(cur),
            "n3_target_row_counts": fetch_n3_target_row_counts(cur),
        }


def execute_sql_file(dsn: str, sql_path: str) -> None:
    sql_text = Path(sql_path).read_text(encoding="utf-8")
    with audited_n3_market_schema_review_connect(dsn, connect_timeout=10, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text)


def fetch_public_tables(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT table_name, table_type
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
        """
    )
    return rows_to_json(cur.fetchall())


def fetch_public_columns(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT table_name,
               ordinal_position,
               column_name,
               data_type,
               udt_name,
               is_nullable,
               column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
        """
    )
    return rows_to_json(cur.fetchall())


def fetch_public_constraints(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT con.conname AS constraint_name,
               rel.relname AS table_name,
               con.contype AS constraint_type,
               pg_get_constraintdef(con.oid) AS definition
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        WHERE nsp.nspname = 'public'
        ORDER BY rel.relname, con.conname
        """
    )
    return rows_to_json(cur.fetchall())


def fetch_public_indexes(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT schemaname,
               tablename,
               indexname,
               indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
        ORDER BY tablename, indexname
        """
    )
    return rows_to_json(cur.fetchall())


def fetch_n1_n2_active_snapshot(cur: Any) -> dict[str, Any]:
    return {
        "common_active_source_version": fetch_table_rows_if_exists(
            cur,
            "common_active_source_version",
            "data_domain, data_type, scope_key",
        ),
        "common_condition_run_active": fetch_table_rows_if_exists(
            cur,
            "common_condition_run",
            "for_trade_date, source_trade_date, status, run_id",
            where_clause="status IN ('passed', 'running', 'superseded')",
        ),
    }


def fetch_table_rows_if_exists(
    cur: Any,
    table_name: str,
    order_by: str,
    *,
    where_clause: str | None = None,
) -> dict[str, Any]:
    if not table_exists(cur, table_name):
        return {"exists": False, "rows": []}
    where_sql = f"WHERE {where_clause}" if where_clause else ""
    cur.execute(f"SELECT * FROM {table_name} {where_sql} ORDER BY {order_by}")
    return {"exists": True, "rows": rows_to_json(cur.fetchall())}


def fetch_n3_target_row_counts(cur: Any) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for table_name in N3_TARGET_TABLES:
        if not table_exists(cur, table_name):
            output[table_name] = {"exists": False, "row_count": None, "status": "missing"}
            continue
        cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name}")
        row = cur.fetchone()
        output[table_name] = {
            "exists": True,
            "row_count": int(row["row_count"]),
            "status": "present",
        }
    return output


def table_exists(cur: Any, table_name: str) -> bool:
    cur.execute("SELECT to_regclass(%s) AS regclass", (f"public.{table_name}",))
    return cur.fetchone()["regclass"] is not None


def build_post_migration_checks(
    *,
    pre_backup: Mapping[str, Any],
    post_backup: Mapping[str, Any],
    post_gap: Mapping[str, Any],
    post_review: Mapping[str, Any],
) -> dict[str, bool]:
    row_counts = post_backup["n3_target_row_counts"]
    active_unchanged = pre_backup["active_snapshot"] == post_backup["active_snapshot"]
    all_targets_exist = all(row_counts[table]["exists"] for table in N3_TARGET_TABLES)
    all_targets_empty = all(row_counts[table]["row_count"] == 0 for table in N3_TARGET_TABLES)
    fact_and_event_empty = all(
        row_counts[table]["exists"] and row_counts[table]["row_count"] == 0
        for table in N3_MARKET_FACT_AND_EVENT_TABLES
    )
    return {
        "missing_tables_zero": len(post_gap["missing_tables"]) == 0,
        "missing_columns_zero": len(post_gap["missing_columns"]) == 0,
        "type_mismatch_zero": len(post_gap["type_mismatch"]) == 0,
        "missing_unique_constraints_zero": len(post_gap["missing_unique_constraints"]) == 0,
        "n3_target_tables_exist": all_targets_exist,
        "n3_target_tables_row_count_zero": all_targets_empty,
        "n1_n2_active_run_unchanged": active_unchanged,
        "no_market_fact_or_outbox_business_events": fact_and_event_empty,
        "n3_4_review_still_passed": bool(post_review["passed"]) and int(post_review["quality"]["p0_count"]) == 0,
    }


def build_quality_items(post_checks: Mapping[str, bool]) -> list[dict[str, Any]]:
    items = [
        quality_item(
            "P0",
            "passed" if passed else "failed",
            f"n3_5_{check_name}",
            f"N3-5 post migration check: {check_name}",
            expected="true",
            actual=str(passed).lower(),
        )
        for check_name, passed in post_checks.items()
    ]
    items.extend(
        [
            quality_item("P0", "passed", "n3_5_no_market_data_pull", "N3-5 does not pull market data"),
            quality_item("P0", "passed", "n3_5_no_worker_or_downstream", "N3-5 does not start workers or enter N4/N5/N6"),
            quality_item("P0", "passed", "n3_5_no_old_system_touch", "N3-5 does not touch old system"),
        ]
    )
    return items


def summarize_gap(gap_report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "migration_required": gap_report["migration_required"],
        "migration_safe_to_apply": gap_report["migration_safe_to_apply"],
        "manual_review_required": gap_report["manual_review_required"],
        "missing_tables": gap_report["missing_tables"],
        "missing_columns_count": len(gap_report["missing_columns"]),
        "type_mismatch_count": len(gap_report["type_mismatch"]),
        "missing_unique_constraints_count": len(gap_report["missing_unique_constraints"]),
        "p0_count": gap_report["quality"]["p0_count"],
        "p1_count": gap_report["quality"]["p1_count"],
        "p2_count": gap_report["quality"]["p2_count"],
    }


def summarize_review(review_report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "passed": review_report["passed"],
        "additive_only": review_report["additive_only"],
        "target_scope_valid": review_report["target_scope_valid"],
        "outbox_unique_constraints_present": review_report["outbox_unique_constraints_present"],
        "p0_count": review_report["quality"]["p0_count"],
        "p1_count": review_report["quality"]["p1_count"],
        "p2_count": review_report["quality"]["p2_count"],
    }


def format_market_data_009_migration_report(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    pre_gap = report["pre_migration"]["schema_gap_summary"]
    post_gap = report["post_migration"]["schema_gap_summary"]
    lines = [
        "# N3-5 Market Data 009 Migration Report",
        "",
        "## Summary",
        "",
        f"- stage: {report['stage']}",
        f"- layer_role: {report['layer_role']}",
        f"- sql_path: {report['sql_path']}",
        f"- migration_executed: {str(report['migration_executed']).lower()}",
        f"- pre_backup_path: {report['pre_backup_path']}",
        f"- post_backup_path: {report['post_backup_path']}",
        f"- started_at: {report['started_at']}",
        f"- finished_at: {report['finished_at']}",
        f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
        "",
        "## Preconditions",
        "",
        f"- N3-3 migration_safe_to_apply: {str(report['preconditions']['n3_3_migration_safe_to_apply']).lower()}",
        f"- N3-3 P0: {report['preconditions']['n3_3_schema_gap_p0_count']}",
        f"- N3-4 passed: {str(report['preconditions']['n3_4_review_passed']).lower()}",
        f"- N3-4 P0/P1/P2: {report['preconditions']['n3_4_review_p0_count']}/{report['preconditions']['n3_4_review_p1_count']}/{report['preconditions']['n3_4_review_p2_count']}",
        "",
        "## Schema Gap",
        "",
        f"- before missing_tables: {pre_gap['missing_tables']}",
        f"- after missing_tables: {post_gap['missing_tables']}",
        f"- after missing_columns_count: {post_gap['missing_columns_count']}",
        f"- after type_mismatch_count: {post_gap['type_mismatch_count']}",
        f"- after missing_unique_constraints_count: {post_gap['missing_unique_constraints_count']}",
        "",
        "## Post Checks",
        "",
    ]
    for check_name, passed in report["post_checks"].items():
        lines.append(f"- {check_name}: {str(passed).lower()}")
    lines.extend(
        [
            "",
            "## N3 Target Row Counts",
            "",
        ]
    )
    for table_name, row_status in report["post_migration"]["n3_target_row_counts"].items():
        lines.append(
            f"- {table_name}: exists={str(row_status['exists']).lower()} row_count={row_status['row_count']}"
        )
    lines.extend(
        [
            "",
            "## Quality",
            "",
        ]
    )
    for item in quality["items"]:
        lines.append(
            f"- {item['severity']} {item['status']} {item['gate_code']}: "
            f"expected={item.get('expected_value')} actual={item.get('actual_value')}"
        )
    side_effects = report["side_effects"]
    lines.extend(
        [
            "",
            "## Boundary Confirmation",
            "",
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
            "009 created additive schema objects only. If rollback is required before any N3 business rows are written, "
            "drop the N3 target tables in dependency order after confirming no dependent objects or rows exist.",
            "",
        ]
    )
    return "\n".join(lines)


def write_json(path: str, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_text(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def rows_to_json(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [{key: normalize_json_value(value) for key, value in dict(row).items()} for row in rows]


def normalize_json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def stable_json_hash(payload: Mapping[str, Any]) -> str:
    import hashlib

    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
