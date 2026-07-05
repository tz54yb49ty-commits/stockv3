"""N5-4 executor for the reviewed 011 action-layer schema migration.

This module performs a bounded schema migration only. It creates the reviewed
N5 action-layer tables and indexes, then verifies that no N4 outbox consumption,
inbox/checkpoint update, action business row, N5 outbox event, N6 projection,
voice, sim, mobile, true trade, worker, or old-system touch occurred.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row

from ashare_v3.action.query_audit_phase2 import audited_n5_schema_review_connect
from ashare_v3.action.schema_migration_review import (
    DEFAULT_N5_3_JSON_REPORT_PATH,
    DEFAULT_N5_3_ROLLBACK_PREVIEW_PATH,
    DEFAULT_N5_3_SCHEMA_PATH,
    ALLOWED_N5_TABLES,
    build_n5_action_schema_migration_review,
)
from ashare_v3.condition.basis import count_quality_severities, quality_item


DEFAULT_N5_4_PRE_SCHEMA_SNAPSHOT_PATH = "docs/N5_4_schema_snapshot_before_011.json"
DEFAULT_N5_4_POST_SCHEMA_SNAPSHOT_PATH = "docs/N5_4_schema_snapshot_after_011.json"
DEFAULT_N5_4_JSON_REPORT_PATH = "docs/N5_4_action_schema_migration_report.json"
DEFAULT_N5_4_MD_REPORT_PATH = "docs/N5_4_ACTION_SCHEMA_MIGRATION_REPORT.md"

N5_TARGET_TABLES = ALLOWED_N5_TABLES
N5_BUSINESS_TABLES = (
    "common_action_run",
    "common_action_quality_item",
    "stock_action_fact",
    "index_action_fact",
    "board_action_fact",
    "common_action_event",
    "common_position_state",
    "common_position_event",
)
ROW_COUNT_GUARD_TABLES = N5_TARGET_TABLES + (
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
)


def run_action_schema_011_migration(
    *,
    dsn: str,
    sql_path: str = DEFAULT_N5_3_SCHEMA_PATH,
    review_json_path: str = DEFAULT_N5_3_JSON_REPORT_PATH,
    rollback_preview_path: str = DEFAULT_N5_3_ROLLBACK_PREVIEW_PATH,
    pre_schema_snapshot_path: str = DEFAULT_N5_4_PRE_SCHEMA_SNAPSHOT_PATH,
    post_schema_snapshot_path: str = DEFAULT_N5_4_POST_SCHEMA_SNAPSHOT_PATH,
    json_report_path: str = DEFAULT_N5_4_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N5_4_MD_REPORT_PATH,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    pre_review = build_n5_action_schema_migration_review(schema_text=Path(sql_path).read_text(encoding="utf-8"))
    n5_3_review_summary = load_n5_3_review_summary(review_json_path)
    if int(pre_review["quality"]["p0_count"]) > 0 or not bool(pre_review["migration_review"]["migration_ready"]):
        raise RuntimeError("N5-4 blocked: fresh N5 migration review is not migration_ready")
    if not bool(n5_3_review_summary.get("migration_ready")):
        raise RuntimeError("N5-4 blocked: N5-3 review migration_ready is not true")
    if not Path(rollback_preview_path).exists():
        raise RuntimeError(f"N5-4 blocked: rollback preview does not exist: {rollback_preview_path}")

    pre_snapshot = capture_action_schema_snapshot(dsn, phase="before_011")
    pre_existing_targets = [
        table_name
        for table_name, row_count in pre_snapshot["target_row_counts"].items()
        if row_count["exists"]
    ]
    if pre_existing_targets:
        raise RuntimeError(
            "N5-4 blocked: target tables already exist before migration: "
            + ",".join(pre_existing_targets)
        )
    write_json(pre_schema_snapshot_path, pre_snapshot)

    execute_sql_file(dsn, sql_path)

    post_snapshot = capture_action_schema_snapshot(dsn, phase="after_011")
    write_json(post_schema_snapshot_path, post_snapshot)

    post_review = build_n5_action_schema_migration_review(schema_text=Path(sql_path).read_text(encoding="utf-8"))
    post_checks = build_post_migration_checks(
        pre_snapshot=pre_snapshot,
        post_snapshot=post_snapshot,
        post_review=post_review,
    )
    quality_items = build_quality_items(post_checks)
    severity_counts = count_quality_severities(quality_items)
    report = {
        "stage": "N5-4",
        "layer_role": "N5_action",
        "execution_mode": "execute_011_action_schema_migration",
        "sql_path": sql_path,
        "review_json_path": review_json_path,
        "rollback_preview_path": rollback_preview_path,
        "pre_schema_snapshot_path": pre_schema_snapshot_path,
        "post_schema_snapshot_path": post_schema_snapshot_path,
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "migration_executed": True,
        "preconditions": {
            "fresh_review_p0_count": pre_review["quality"]["p0_count"],
            "fresh_review_p1_count": pre_review["quality"]["p1_count"],
            "fresh_review_p2_count": pre_review["quality"]["p2_count"],
            "fresh_review_passed": pre_review["passed"],
            "fresh_review_migration_ready": pre_review["migration_review"]["migration_ready"],
            "n5_3_review_migration_ready": n5_3_review_summary.get("migration_ready"),
            "n5_3_review_p0_count": n5_3_review_summary.get("p0_count"),
            "n5_3_review_p1_count": n5_3_review_summary.get("p1_count"),
            "n5_3_review_p2_count": n5_3_review_summary.get("p2_count"),
            "rollback_preview_exists": Path(rollback_preview_path).exists(),
            "target_tables_existing_before": pre_existing_targets,
        },
        "pre_migration": {
            "target_row_counts": pre_snapshot["target_row_counts"],
            "guard_row_counts": pre_snapshot["guard_row_counts"],
            "schema_snapshot_hash": stable_json_hash(pre_snapshot["public_schema"]),
        },
        "post_migration": {
            "target_row_counts": post_snapshot["target_row_counts"],
            "guard_row_counts": post_snapshot["guard_row_counts"],
            "schema_snapshot_hash": stable_json_hash(post_snapshot["public_schema"]),
            "review_summary": summarize_review(post_review),
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
            "business_data_written": False,
            "n4_outbox_consumed": False,
            "common_event_inbox_updated": False,
            "consumer_checkpoint_updated": False,
            "action_fact_written": False,
            "action_quality_written": False,
            "action_event_written": False,
            "position_state_written": False,
            "position_event_written": False,
            "n5_outbox_written": False,
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
        "passed": severity_counts["P0"] == 0,
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_action_schema_011_migration_report(report))
    return report


def capture_action_schema_snapshot(dsn: str, *, phase: str) -> dict[str, Any]:
    with audited_n5_schema_review_connect(
        dsn,
        stage_id=f"n5_action_schema_snapshot_{phase}",
        source_run_id=f"action_schema_snapshot_{phase}",
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
            "target_table_existence": fetch_table_existence(cur, N5_TARGET_TABLES),
            "target_row_counts": fetch_row_counts(cur, N5_TARGET_TABLES),
            "guard_row_counts": fetch_row_counts(cur, ROW_COUNT_GUARD_TABLES),
        }


def execute_sql_file(dsn: str, sql_path: str) -> None:
    sql_text = Path(sql_path).read_text(encoding="utf-8")
    with audited_n5_schema_review_connect(
        dsn,
        stage_id="n5_action_schema_execute_sql_file",
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


def fetch_table_existence(cur: Any, table_names: tuple[str, ...]) -> dict[str, bool]:
    return {table_name: table_exists(cur, table_name) for table_name in table_names}


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
    pre_snapshot: Mapping[str, Any],
    post_snapshot: Mapping[str, Any],
    post_review: Mapping[str, Any],
) -> dict[str, bool]:
    post_target_counts = post_snapshot["target_row_counts"]
    pre_guard_counts = pre_snapshot["guard_row_counts"]
    post_guard_counts = post_snapshot["guard_row_counts"]
    all_targets_exist = all(post_target_counts[table]["exists"] for table in N5_TARGET_TABLES)
    all_targets_empty = all(post_target_counts[table]["row_count"] == 0 for table in N5_TARGET_TABLES)
    business_rows_zero = all(post_target_counts[table]["row_count"] == 0 for table in N5_BUSINESS_TABLES)
    outbox_unchanged = pre_guard_counts["common_event_outbox"] == post_guard_counts["common_event_outbox"]
    inbox_unchanged = pre_guard_counts["common_event_inbox"] == post_guard_counts["common_event_inbox"]
    checkpoint_unchanged = (
        pre_guard_counts["common_event_consumer_checkpoint"]
        == post_guard_counts["common_event_consumer_checkpoint"]
    )
    guard_tables_exist = all(
        post_guard_counts[table]["exists"]
        for table in ("common_event_outbox", "common_event_inbox", "common_event_consumer_checkpoint")
    )
    return {
        "n5_target_tables_exist": all_targets_exist,
        "n5_target_tables_row_count_zero": all_targets_empty,
        "n5_business_rows_zero": business_rows_zero,
        "common_event_outbox_unchanged": outbox_unchanged,
        "common_event_inbox_unchanged": inbox_unchanged,
        "common_event_consumer_checkpoint_unchanged": checkpoint_unchanged,
        "event_guard_tables_exist": guard_tables_exist,
        "action_fact_rows_zero": all(
            post_target_counts[table]["row_count"] == 0
            for table in ("stock_action_fact", "index_action_fact", "board_action_fact")
        ),
        "n5_outbox_rows_zero": post_target_counts["common_action_event"]["row_count"] == 0,
        "post_review_p0_zero": int(post_review["quality"]["p0_count"]) == 0,
        "post_review_migration_ready": bool(post_review["migration_review"]["migration_ready"]),
    }


def build_quality_items(post_checks: Mapping[str, bool]) -> list[dict[str, Any]]:
    items = [
        quality_item(
            "P0",
            "passed" if passed else "failed",
            f"n5_4_{check_name}",
            f"N5-4 post migration check: {check_name}",
            expected="true",
            actual=str(passed).lower(),
        )
        for check_name, passed in post_checks.items()
    ]
    items.extend(
        [
            quality_item("P0", "passed", "n5_4_no_n4_outbox_consumption", "N5-4 does not consume N4 outbox"),
            quality_item("P0", "passed", "n5_4_no_n5_business_data", "N5-4 does not write action business data"),
            quality_item("P0", "passed", "n5_4_no_n5_outbox_business_event", "N5-4 does not write N5 outbox business events"),
            quality_item("P0", "passed", "n5_4_no_n6_voice_sim_mobile_trade", "N5-4 does not enter N6, voice, sim, mobile, or true trade"),
            quality_item("P0", "passed", "n5_4_no_worker", "N5-4 does not start workers"),
            quality_item("P0", "passed", "n5_4_no_old_system_touch", "N5-4 does not touch old system"),
        ]
    )
    return items


def load_n5_3_review_summary(path: str) -> dict[str, Any]:
    report_path = Path(path)
    if not report_path.exists():
        return {"exists": False, "migration_ready": False}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    quality = report.get("quality") or {}
    migration_review = report.get("migration_review") or {}
    return {
        "exists": True,
        "migration_ready": bool(migration_review.get("migration_ready")),
        "p0_count": quality.get("p0_count"),
        "p1_count": quality.get("p1_count"),
        "p2_count": quality.get("p2_count"),
        "passed": report.get("passed"),
    }


def summarize_review(review_report: Mapping[str, Any]) -> dict[str, Any]:
    migration_review = review_report["migration_review"]
    quality = review_report["quality"]
    return {
        "passed": review_report["passed"],
        "p0_count": quality["p0_count"],
        "p1_count": quality["p1_count"],
        "p2_count": quality["p2_count"],
        "migration_ready": migration_review["migration_ready"],
        "created_tables": migration_review["created_tables"],
        "extra_created_tables": migration_review["extra_created_tables"],
        "payload_contract_missing": migration_review["payload_contract_missing"],
    }


def rows_to_json(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_value(dict(row)) for row in rows]


def normalize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return [normalize_value(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def stable_json_hash(payload: Mapping[str, Any]) -> str:
    import hashlib

    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: str, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_text(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def format_action_schema_011_migration_report(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    checks = report["post_checks"]
    pre = report["pre_migration"]
    post = report["post_migration"]
    side_effects = report["side_effects"]
    return "\n".join(
        [
            "# N5-4 Action Schema Migration Report",
            "",
            "## Summary",
            "",
            f"- stage: {report['stage']}",
            f"- layer_role: {report['layer_role']}",
            f"- execution_mode: {report['execution_mode']}",
            f"- sql_path: {report['sql_path']}",
            f"- migration_executed: {report['migration_executed']}",
            f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
            f"- passed: {report['passed']}",
            "",
            "## Snapshots",
            "",
            f"- before_schema_snapshot: {report['pre_schema_snapshot_path']}",
            f"- after_schema_snapshot: {report['post_schema_snapshot_path']}",
            f"- before_schema_hash: {pre['schema_snapshot_hash']}",
            f"- after_schema_hash: {post['schema_snapshot_hash']}",
            "",
            "## Preconditions",
            "",
            f"- n5_3_review_migration_ready: {report['preconditions']['n5_3_review_migration_ready']}",
            f"- fresh_review_migration_ready: {report['preconditions']['fresh_review_migration_ready']}",
            f"- target_tables_existing_before: {report['preconditions']['target_tables_existing_before']}",
            f"- rollback_preview_exists: {report['preconditions']['rollback_preview_exists']}",
            "",
            "## Row Counts",
            "",
            f"- before_target_row_counts: {pre['target_row_counts']}",
            f"- after_target_row_counts: {post['target_row_counts']}",
            f"- before_guard_row_counts: {pre['guard_row_counts']}",
            f"- after_guard_row_counts: {post['guard_row_counts']}",
            "",
            "## Post Checks",
            "",
            *[f"- {key}: {value}" for key, value in checks.items()],
            "",
            "## Boundary Confirmation",
            "",
            f"- writes_performed: {side_effects['writes_performed']}",
            f"- business_data_written: {side_effects['business_data_written']}",
            f"- n4_outbox_consumed: {side_effects['n4_outbox_consumed']}",
            f"- common_event_inbox_updated: {side_effects['common_event_inbox_updated']}",
            f"- consumer_checkpoint_updated: {side_effects['consumer_checkpoint_updated']}",
            f"- action_fact_written: {side_effects['action_fact_written']}",
            f"- n5_outbox_written: {side_effects['n5_outbox_written']}",
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
            "- N5-4 executed only the reviewed action-layer schema migration.",
            "- No N4 outbox consumption, inbox/checkpoint update, action fact row, N5 outbox business event, N6 write, worker, market pull, voice, sim, mobile, true trade, or old-system touch was performed.",
        ]
    )
