"""Restore verified V3 runtime archive parquet files back into hot PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4

import pandas as pd
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from ashare_v3.ingestion.common import require_yyyymmdd
from ashare_v3.ingestion.runtime_archive import DEFAULT_RUNTIME_ARCHIVE_ROOT, make_runtime_archive_manifest_path
from ashare_v3.ingestion.runtime_archive_execute import DEFAULT_DSN, build_runtime_archive_query_specs


RESTORE_ORDER_BASE = {
    "n3": 1000,
    "n4": 2000,
    "n5": 3000,
    "n6": 4000,
}

TABLE_RESTORE_PRIORITY = {
    "common_market_data_run": 10,
    "common_market_data_subscription_candidate": 20,
    "common_market_data_subscription": 30,
    "common_market_data_pull_plan": 40,
    "common_market_data_quality_item": 50,
    "stock_previous_day_minute_preload_status": 60,
    "index_previous_day_minute_preload_status": 60,
    "board_previous_day_minute_preload_status": 60,
    "stock_realtime_daily_snapshot": 70,
    "index_realtime_daily_snapshot": 70,
    "board_realtime_daily_snapshot": 70,
    "stock_minute_bar_1m": 80,
    "index_minute_bar_1m": 80,
    "board_minute_bar_1m": 80,
    "stock_realtime_projection_metric": 90,
    "index_realtime_projection_metric": 90,
    "board_realtime_projection_metric": 90,
    "stock_action_confirmation_projection_metric": 100,
    "index_action_confirmation_projection_metric": 100,
    "board_action_confirmation_projection_metric": 100,
    "common_trigger_run": 10,
    "common_trigger_quality_item": 20,
    "stock_trigger_context_snapshot": 30,
    "index_trigger_context_snapshot": 30,
    "board_trigger_context_snapshot": 30,
    "common_trigger_state": 40,
    "common_trigger_match": 50,
    "common_action_run": 10,
    "common_action_quality_item": 20,
    "stock_action_fact": 30,
    "index_action_fact": 30,
    "board_action_fact": 30,
    "common_action_event": 40,
    "user_projection_run": 10,
    "user_signal_projection": 20,
    "user_signal_card": 30,
    "user_notification_queue": 40,
    "common_event_outbox": 800,
    "common_event_ledger": 810,
    "common_event_inbox": 820,
    "common_event_delivery_attempt": 830,
    "common_event_consumer_checkpoint": 840,
}


@dataclass(frozen=True)
class TableColumn:
    name: str
    udt_name: str
    has_default: bool
    is_nullable: bool


def manifest_path_for_trade_date(
    *,
    trade_date: str,
    archive_root: str | Path = DEFAULT_RUNTIME_ARCHIVE_ROOT,
) -> Path:
    return Path(make_runtime_archive_manifest_path(archive_root=str(archive_root), trade_date=trade_date))


def validate_restore_manifest(path: str | Path, *, trade_date: str) -> dict[str, Any]:
    normalized_trade_date = require_yyyymmdd(str(trade_date), "trade_date")
    manifest_path = Path(path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("result") != "ARCHIVED_VERIFIED":
        raise ValueError(f"archive manifest is not verified: {manifest.get('result')}")
    if str(manifest.get("trade_date")) != normalized_trade_date:
        raise ValueError(f"archive manifest trade_date mismatch: {manifest.get('trade_date')}")
    if not manifest.get("row_count_match"):
        raise ValueError("archive manifest row_count_match is false")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("archive manifest has no files")
    for item in files:
        file_path = Path(str(item.get("path") or ""))
        if not file_path.exists():
            raise FileNotFoundError(file_path)
        checksum = str(item.get("checksum") or "")
        if checksum.startswith("sha256:"):
            actual = f"sha256:{sha256(file_path.read_bytes()).hexdigest()}"
            if actual != checksum:
                raise ValueError(f"checksum mismatch for {file_path}")
    return manifest


def ordered_restore_files(files: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (dict(item) for item in files),
        key=lambda item: (
            RESTORE_ORDER_BASE.get(str(item.get("layer")), 9000),
            TABLE_RESTORE_PRIORITY.get(str(item.get("table")), 700),
            str(item.get("table")),
            str(item.get("path")),
        ),
    )


def table_columns(conn: psycopg.Connection[Any], table: str) -> list[TableColumn]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select column_name, udt_name, column_default is not null, is_nullable = 'YES'
            from information_schema.columns
            where table_schema = 'public' and table_name = %s
            order by ordinal_position
            """,
            (table,),
        )
        rows = cur.fetchall()
    if not rows:
        raise ValueError(f"table not found: {table}")
    return [TableColumn(str(name), str(udt_name), bool(has_default), bool(is_nullable)) for name, udt_name, has_default, is_nullable in rows]


def primary_key_columns(conn: psycopg.Connection[Any], table: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select a.attname
            from pg_index i
            join pg_attribute a on a.attrelid = i.indrelid and a.attnum = any(i.indkey)
            where i.indrelid = %s::regclass and i.indisprimary
            order by array_position(i.indkey, a.attnum)
            """,
            (table,),
        )
        rows = cur.fetchall()
    columns = [str(row[0]) for row in rows]
    if not columns:
        raise ValueError(f"table has no primary key: {table}")
    return columns


def convert_archive_value(value: Any, *, udt_name: str) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.to_pydatetime()
    if hasattr(value, "item") and not isinstance(value, (str, bytes, bytearray)):
        try:
            value = value.item()
        except (AttributeError, ValueError):
            pass
    if udt_name == "jsonb" or udt_name == "json":
        return Jsonb(parse_jsonish(value))
    if udt_name.startswith("_"):
        return parse_arrayish(value)
    if udt_name in {"int2", "int4", "int8"}:
        return int(value)
    if isinstance(value, (datetime, date)):
        return value
    return value


def parse_jsonish(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return value
    return value


def parse_arrayish(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return None
        parsed = json.loads(text)
        return list(parsed) if isinstance(parsed, list) else [parsed]
    if isinstance(value, (list, tuple)):
        return list(value)
    if hasattr(value, "tolist"):
        converted = value.tolist()
        return list(converted) if isinstance(converted, list) else [converted]
    return [value]


def restore_dataframe_to_table(
    *,
    conn: psycopg.Connection[Any],
    table: str,
    frame: pd.DataFrame,
) -> dict[str, Any]:
    columns = table_columns(conn, table)
    column_by_name = {column.name: column for column in columns}
    restore_columns = [column for column in frame.columns if column in column_by_name]
    if not restore_columns:
        return {"table": table, "archived_rows": int(len(frame)), "inserted_rows": 0, "skipped_existing_rows": 0}
    missing_required = [
        column.name
        for column in columns
        if column.name not in restore_columns and not column.is_nullable and not column.has_default
    ]
    if missing_required:
        raise ValueError(f"{table} archive missing required columns: {missing_required}")

    pk_columns = primary_key_columns(conn, table)
    temp_table = f"tmp_restore_{table}_{uuid4().hex[:12]}"
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("create temp table {} (like {} including defaults) on commit drop").format(
                sql.Identifier(temp_table),
                sql.Identifier(table),
            )
        )
        copy_sql = sql.SQL("copy {} ({}) from stdin").format(
            sql.Identifier(temp_table),
            sql.SQL(", ").join(sql.Identifier(column) for column in restore_columns),
        )
        udt_names = [column_by_name[column].udt_name for column in restore_columns]
        with cur.copy(copy_sql) as copy:
            for row in frame[restore_columns].itertuples(index=False, name=None):
                copy.write_row(
                    [
                        convert_archive_value(value, udt_name=udt_name)
                        for value, udt_name in zip(row, udt_names)
                    ]
                )
        insert_sql = sql.SQL(
            "insert into {} ({}) overriding system value select {} from {} on conflict ({}) do nothing"
        ).format(
            sql.Identifier(table),
            sql.SQL(", ").join(sql.Identifier(column) for column in restore_columns),
            sql.SQL(", ").join(sql.Identifier(column) for column in restore_columns),
            sql.Identifier(temp_table),
            sql.SQL(", ").join(sql.Identifier(column) for column in pk_columns),
        )
        cur.execute(insert_sql)
        inserted = int(cur.rowcount or 0)
        archived_rows = int(len(frame))
        return {
            "table": table,
            "archived_rows": archived_rows,
            "inserted_rows": inserted,
            "skipped_existing_rows": archived_rows - inserted,
            "primary_key_columns": pk_columns,
        }


def refresh_table_sequences(conn: psycopg.Connection[Any], table: str) -> list[dict[str, Any]]:
    refreshed: list[dict[str, Any]] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            select column_name
            from information_schema.columns
            where table_schema = 'public'
              and table_name = %s
              and column_default like 'nextval%%'
            order by ordinal_position
            """,
            (table,),
        )
        for (column_name,) in cur.fetchall():
            cur.execute("select pg_get_serial_sequence(%s, %s)", (table, column_name))
            sequence = cur.fetchone()[0]
            if not sequence:
                continue
            cur.execute(
                sql.SQL("select setval(%s, coalesce((select max({}) from {}), 1), true)").format(
                    sql.Identifier(str(column_name)),
                    sql.Identifier(table),
                ),
                (sequence,),
            )
            refreshed.append({"table": table, "column": str(column_name), "sequence": str(sequence)})
    return refreshed


def archived_scope_live_count(*, dsn: str = DEFAULT_DSN, trade_date: str) -> tuple[int, list[dict[str, Any]]]:
    specs = build_runtime_archive_query_specs(trade_date)
    total = 0
    nonzero: list[dict[str, Any]] = []
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            for spec in specs:
                cur.execute(count_sql_for_archive_spec(spec.sql), spec.params)
                count = int(cur.fetchone()[0])
                total += count
                if count:
                    nonzero.append({"layer": spec.layer, "table": spec.table, "rows": count})
    return total, nonzero


def count_sql_for_archive_spec(query_sql: str) -> str:
    lower_sql = query_sql.lower()
    order_index = lower_sql.rfind(" order by ")
    count_source = query_sql[:order_index] if order_index >= 0 else query_sql
    return "select count(*) from (" + count_source + ") s"


def restore_runtime_archive(
    *,
    trade_date: str,
    dsn: str = DEFAULT_DSN,
    archive_root: str | Path = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    normalized_trade_date = require_yyyymmdd(str(trade_date), "trade_date")
    manifest = validate_restore_manifest(
        manifest_path or manifest_path_for_trade_date(trade_date=normalized_trade_date, archive_root=archive_root),
        trade_date=normalized_trade_date,
    )
    before_total, before_nonzero = archived_scope_live_count(dsn=dsn, trade_date=normalized_trade_date)
    per_file: list[dict[str, Any]] = []
    touched_tables: set[str] = set()

    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            for item in ordered_restore_files(manifest["files"]):
                frame = pd.read_parquet(str(item["path"]))
                result = restore_dataframe_to_table(conn=conn, table=str(item["table"]), frame=frame)
                result.update({"layer": item.get("layer"), "path": item.get("path")})
                per_file.append(result)
                touched_tables.add(str(item["table"]))
            refreshed_sequences = []
            for table in sorted(touched_tables):
                refreshed_sequences.extend(refresh_table_sequences(conn, table))

    after_total, after_nonzero = archived_scope_live_count(dsn=dsn, trade_date=normalized_trade_date)
    inserted_rows = sum(int(item["inserted_rows"]) for item in per_file)
    skipped_rows = sum(int(item["skipped_existing_rows"]) for item in per_file)
    return {
        "result": "RESTORE_PASS" if after_total == int(manifest["total_rows"]) else "BLOCKED",
        "trade_date": normalized_trade_date,
        "manifest_path": str(manifest.get("manifest_path") or ""),
        "file_count": int(manifest["file_count"]),
        "manifest_total_rows": int(manifest["total_rows"]),
        "before_live_total": before_total,
        "before_nonzero_tables": before_nonzero,
        "after_live_total": after_total,
        "after_nonzero_tables": after_nonzero,
        "inserted_rows": inserted_rows,
        "skipped_existing_rows": skipped_rows,
        "per_file": per_file,
        "refreshed_sequence_count": len(refreshed_sequences),
        "refreshed_sequences_sample": refreshed_sequences[:20],
        "side_effects": {
            "writes_database": True,
            "restores_hot_runtime": True,
            "writes_archive_files": False,
            "cleanup_local_runtime": False,
            "outbox_inbox_checkpoint_consumed_or_updated": False,
            "worker_or_scheduler_started": False,
            "n6_voice_mobile_sim_position_trade_touched": False,
            "old_system_touched": False,
        },
    }
