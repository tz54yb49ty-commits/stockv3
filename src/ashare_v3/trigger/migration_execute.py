"""N4-2 executor for the reviewed 010 trigger-layer schema migration.

This module performs a bounded schema migration only. It does not write trigger
business rows, consume N3 events, pull quotes, start workers, or enter N5/N6.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.trigger.query_audit_phase1 import audited_n4_schema_review_connect
from ashare_v3.trigger.schema_review import (
    DEFAULT_TRIGGER_SCHEMA_PATH,
    DEFAULT_TRIGGER_SCHEMA_ROLLBACK_SQL_PATH,
    REQUIRED_DEPENDENCY_TABLES,
    REQUIRED_TRIGGER_TABLES,
    build_trigger_schema_migration_review,
)


DEFAULT_N4_2_PRE_BACKUP_PATH = "docs/N4_2_schema_backup_before_010.json"
DEFAULT_N4_2_POST_BACKUP_PATH = "docs/N4_2_schema_backup_after_010.json"
DEFAULT_N4_2_JSON_REPORT_PATH = "docs/N4_2_trigger_schema_migration_report.json"
DEFAULT_N4_2_MD_REPORT_PATH = "docs/N4_2_TRIGGER_SCHEMA_MIGRATION_REPORT.md"

N4_BUSINESS_TABLES = (
    "common_trigger_run",
    "common_trigger_quality_item",
    "stock_trigger_context_snapshot",
    "index_trigger_context_snapshot",
    "board_trigger_context_snapshot",
    "common_trigger_state",
    "common_trigger_match",
)
ROW_COUNT_GUARD_TABLES = REQUIRED_TRIGGER_TABLES + ("common_event_outbox",)


def run_trigger_schema_010_migration(
    *,
    dsn: str,
    sql_path: str = DEFAULT_TRIGGER_SCHEMA_PATH,
    rollback_sql_path: str = DEFAULT_TRIGGER_SCHEMA_ROLLBACK_SQL_PATH,
    pre_backup_path: str = DEFAULT_N4_2_PRE_BACKUP_PATH,
    post_backup_path: str = DEFAULT_N4_2_POST_BACKUP_PATH,
    json_report_path: str = DEFAULT_N4_2_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N4_2_MD_REPORT_PATH,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    pre_review = build_trigger_schema_migration_review(
        dsn=dsn,
        schema_path=sql_path,
        rollback_sql_path=rollback_sql_path,
    )
    if int(pre_review["quality"]["p0_count"]) > 0:
        raise RuntimeError("N4-2 blocked: schema review has P0 findings")
    if not bool(pre_review["ready_for_n4_2_user_confirmation"]):
        raise RuntimeError("N4-2 blocked: ready_for_n4_2_user_confirmation is false")
    if not bool(pre_review["migration_safe_to_apply_after_user_confirmation"]):
        raise RuntimeError("N4-2 blocked: 010 migration is not safe to apply")
    if not Path(rollback_sql_path).exists():
        raise RuntimeError(f"N4-2 blocked: rollback preview does not exist: {rollback_sql_path}")

    pre_backup = capture_trigger_schema_backup(dsn, phase="before_010")
    write_json(pre_backup_path, pre_backup)

    execute_sql_file(dsn, sql_path)

    post_backup = capture_trigger_schema_backup(dsn, phase="after_010")
    write_json(post_backup_path, post_backup)

    post_review = build_trigger_schema_migration_review(
        dsn=dsn,
        schema_path=sql_path,
        rollback_sql_path=rollback_sql_path,
    )
    post_checks = build_post_migration_checks(
        pre_backup=pre_backup,
        post_backup=post_backup,
        post_review=post_review,
    )
    quality_items = build_quality_items(post_checks)
    severity_counts = count_quality_severities(quality_items)
    report = {
        "stage": "N4-2",
        "layer_role": "N4_trigger",
        "execution_mode": "execute_010_trigger_schema_migration",
        "sql_path": sql_path,
        "rollback_sql_path": rollback_sql_path,
        "pre_backup_path": pre_backup_path,
        "post_backup_path": post_backup_path,
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "migration_executed": True,
        "preconditions": {
            "review_p0_count": pre_review["quality"]["p0_count"],
            "review_p1_count": pre_review["quality"]["p1_count"],
            "review_p2_count": pre_review["quality"]["p2_count"],
            "review_passed": pre_review["passed"],
            "ready_for_n4_2_user_confirmation": pre_review["ready_for_n4_2_user_confirmation"],
            "migration_safe_to_apply_after_user_confirmation": pre_review[
                "migration_safe_to_apply_after_user_confirmation"
            ],
            "rollback_preview_exists": Path(rollback_sql_path).exists(),
            "additive_create_only": pre_review["static_review"]["additive_create_only"],
            "static_ready": pre_review["static_review"]["static_ready"],
        },
        "pre_migration": {
            "review_summary": summarize_review(pre_review),
            "target_row_counts": pre_backup["target_row_counts"],
            "guard_row_counts": pre_backup["guard_row_counts"],
            "active_snapshot_hash": stable_json_hash(pre_backup["active_snapshot"]),
        },
        "post_migration": {
            "review_summary": summarize_review(post_review),
            "target_row_counts": post_backup["target_row_counts"],
            "guard_row_counts": post_backup["guard_row_counts"],
            "active_snapshot_hash": stable_json_hash(post_backup["active_snapshot"]),
        },
        "post_checks": post_checks,
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "side_effects": {
            "will_execute_sql": True,
            "migration_executed": True,
            "writes_performed": False,
            "market_data_pulled": False,
            "n3_event_consumed": False,
            "trigger_context_snapshot_written": False,
            "trigger_state_written": False,
            "trigger_match_written": False,
            "event_outbox_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_trigger_schema_010_migration_report(report))
    return report


def capture_trigger_schema_backup(dsn: str, *, phase: str) -> dict[str, Any]:
    with audited_n4_schema_review_connect(
        dsn,
        stage_id=f"n4_trigger_schema_backup_{phase}",
        source_run_id=f"trigger_schema_backup_{phase}",
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
            "active_snapshot": fetch_active_snapshot(cur),
            "target_row_counts": fetch_row_counts(cur, REQUIRED_TRIGGER_TABLES),
            "dependency_row_counts": fetch_row_counts(cur, REQUIRED_DEPENDENCY_TABLES),
            "guard_row_counts": fetch_row_counts(cur, ROW_COUNT_GUARD_TABLES),
        }


def execute_sql_file(dsn: str, sql_path: str) -> None:
    sql_text = Path(sql_path).read_text(encoding="utf-8")
    with audited_n4_schema_review_connect(
        dsn,
        stage_id="n4_trigger_schema_execute_sql_file",
        source_run_id=Path(sql_path).stem,
        readonly_expected=False,
        connect_timeout=10,
        autocommit=True,
    ) as conn:
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


def fetch_active_snapshot(cur: Any) -> dict[str, Any]:
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


def fetch_row_counts(cur: Any, table_names: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for table_name in table_names:
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
    post_review: Mapping[str, Any],
) -> dict[str, bool]:
    pre_guard_counts = pre_backup["guard_row_counts"]
    post_guard_counts = post_backup["guard_row_counts"]
    post_target_counts = post_backup["target_row_counts"]
    all_targets_exist = all(post_target_counts[table]["exists"] for table in REQUIRED_TRIGGER_TABLES)
    all_targets_empty = all(post_target_counts[table]["row_count"] == 0 for table in REQUIRED_TRIGGER_TABLES)
    outbox_unchanged = pre_guard_counts["common_event_outbox"] == post_guard_counts["common_event_outbox"]
    active_unchanged = pre_backup["active_snapshot"] == post_backup["active_snapshot"]
    dependencies_present = not post_review["missing_dependency_tables"]
    return {
        "missing_n4_tables_zero": len(post_review["target_tables_missing"]) == 0,
        "missing_dependency_tables_zero": dependencies_present,
        "missing_columns_zero": len(post_review["missing_columns"]) == 0,
        "type_mismatch_zero": len(post_review["type_mismatch"]) == 0,
        "missing_unique_constraints_zero": len(post_review["missing_unique_constraints"]) == 0,
        "n4_target_tables_exist": all_targets_exist,
        "n4_target_tables_row_count_zero": all_targets_empty,
        "trigger_business_rows_zero": all_targets_empty,
        "common_event_outbox_unchanged": outbox_unchanged,
        "n1_n2_active_run_unchanged": active_unchanged,
        "post_review_p0_zero": int(post_review["quality"]["p0_count"]) == 0,
        "post_review_static_ready": bool(post_review["static_review"]["static_ready"]),
    }


def build_quality_items(post_checks: Mapping[str, bool]) -> list[dict[str, Any]]:
    items = [
        quality_item(
            "P0",
            "passed" if passed else "failed",
            f"n4_2_{check_name}",
            f"N4-2 post migration check: {check_name}",
            expected="true",
            actual=str(passed).lower(),
        )
        for check_name, passed in post_checks.items()
    ]
    items.extend(
        [
            quality_item("P0", "passed", "n4_2_no_market_data_pull", "N4-2 does not pull market data"),
            quality_item("P0", "passed", "n4_2_no_n3_event_consumption", "N4-2 does not consume N3 events"),
            quality_item("P0", "passed", "n4_2_no_worker_or_downstream", "N4-2 does not start workers or enter N5/N6"),
            quality_item("P0", "passed", "n4_2_no_old_system_touch", "N4-2 does not touch old system"),
        ]
    )
    return items


def summarize_review(review_report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "migration_required": review_report["migration_required"],
        "ready_for_n4_2_user_confirmation": review_report["ready_for_n4_2_user_confirmation"],
        "migration_safe_to_apply_after_user_confirmation": review_report[
            "migration_safe_to_apply_after_user_confirmation"
        ],
        "manual_review_required": review_report["manual_review_required"],
        "target_tables_existing": review_report["target_tables_existing"],
        "target_tables_missing": review_report["target_tables_missing"],
        "missing_dependency_tables": review_report["missing_dependency_tables"],
        "missing_columns_count": len(review_report["missing_columns"]),
        "type_mismatch_count": len(review_report["type_mismatch"]),
        "missing_unique_constraints_count": len(review_report["missing_unique_constraints"]),
        "p0_count": review_report["quality"]["p0_count"],
        "p1_count": review_report["quality"]["p1_count"],
        "p2_count": review_report["quality"]["p2_count"],
        "static_ready": review_report["static_review"]["static_ready"],
        "additive_create_only": review_report["static_review"]["additive_create_only"],
    }


def format_trigger_schema_010_migration_report(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    pre_review = report["pre_migration"]["review_summary"]
    post_review = report["post_migration"]["review_summary"]
    lines = [
        "# N4-2 Trigger Schema Migration Report",
        "",
        "## Summary",
        "",
        f"- stage: {report['stage']}",
        f"- layer_role: {report['layer_role']}",
        f"- sql_path: {report['sql_path']}",
        f"- rollback_sql_path: {report['rollback_sql_path']}",
        f"- migration_executed: {str(report['migration_executed']).lower()}",
        f"- pre_backup_path: {report['pre_backup_path']}",
        f"- post_backup_path: {report['post_backup_path']}",
        f"- started_at: {report['started_at']}",
        f"- finished_at: {report['finished_at']}",
        f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
        "",
        "## Preconditions",
        "",
        f"- ready_for_n4_2_user_confirmation: {str(report['preconditions']['ready_for_n4_2_user_confirmation']).lower()}",
        f"- migration_safe_to_apply_after_user_confirmation: {str(report['preconditions']['migration_safe_to_apply_after_user_confirmation']).lower()}",
        f"- rollback_preview_exists: {str(report['preconditions']['rollback_preview_exists']).lower()}",
        f"- additive_create_only: {str(report['preconditions']['additive_create_only']).lower()}",
        f"- pre_review P0/P1/P2: {report['preconditions']['review_p0_count']}/{report['preconditions']['review_p1_count']}/{report['preconditions']['review_p2_count']}",
        "",
        "## Schema Gap",
        "",
        f"- before missing_tables: {pre_review['target_tables_missing']}",
        f"- before missing_dependency_tables: {pre_review['missing_dependency_tables']}",
        f"- after missing_tables: {post_review['target_tables_missing']}",
        f"- after missing_dependency_tables: {post_review['missing_dependency_tables']}",
        f"- after missing_columns_count: {post_review['missing_columns_count']}",
        f"- after type_mismatch_count: {post_review['type_mismatch_count']}",
        f"- after missing_unique_constraints_count: {post_review['missing_unique_constraints_count']}",
        "",
        "## Post Checks",
        "",
    ]
    for check_name, passed in report["post_checks"].items():
        lines.append(f"- {check_name}: {str(passed).lower()}")
    lines.extend(
        [
            "",
            "## N4 Target Row Counts",
            "",
        ]
    )
    for table_name, row_status in report["post_migration"]["target_row_counts"].items():
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
            f"- will_execute_sql: {str(side_effects['will_execute_sql']).lower()}",
            f"- migration_executed: {str(side_effects['migration_executed']).lower()}",
            f"- writes_performed: {str(side_effects['writes_performed']).lower()}",
            f"- market_data_pulled: {str(side_effects['market_data_pulled']).lower()}",
            f"- n3_event_consumed: {str(side_effects['n3_event_consumed']).lower()}",
            f"- trigger_context_snapshot_written: {str(side_effects['trigger_context_snapshot_written']).lower()}",
            f"- trigger_state_written: {str(side_effects['trigger_state_written']).lower()}",
            f"- trigger_match_written: {str(side_effects['trigger_match_written']).lower()}",
            f"- event_outbox_written: {str(side_effects['event_outbox_written']).lower()}",
            f"- downstream_layers_touched: {str(side_effects['downstream_layers_touched']).lower()}",
            f"- worker_started: {str(side_effects['worker_started']).lower()}",
            f"- old_system_touched: {str(side_effects['old_system_touched']).lower()}",
            "",
            "## Rollback",
            "",
            "010 created additive N4 schema objects only. If rollback is required before any N4 business rows are written, "
            "execute sql/N4_2_trigger_schema_rollback.sql after confirming all N4 trigger tables still have row_count=0. "
            "The rollback preview drops only N4 trigger-layer schema objects and does not touch N1/N2/N3 facts or common_event_outbox.",
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
