#!/usr/bin/env python3
"""Run one v3 raw-ingestion daily increment into PostgreSQL.

Scope: raw ingestion only. This script writes only the approved common/stock/
index/board physical tables, quality gates, active source versions, and
Parquet archives. It does not read or modify the old system.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Iterable, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for path in (str(PROJECT_ROOT), str(SRC_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

import psycopg
from psycopg.types.json import Jsonb

from ashare_v3.ingestion.common import (
    infer_index_exchange_from_code,
    make_index_identity_key,
    require_yyyymmdd,
)
from ashare_v3.ingestion.common_index import normalize_trade_calendar_rows
from ashare_v3.ingestion.daily_bars import (
    BoardDailySymbol,
    IndexDailySymbol,
    normalize_board_daily_bar_row,
)
from ashare_v3.ingestion.mootdx_daily_source import MootdxDailyBarSource
from ashare_v3.mootdx_client import MootdxEndpointManager
from scripts.run_real_initial_ingestion import (
    ADJ_FACTOR_FIELDS,
    BOARD_FILE_TYPES,
    DAILY_BASIC_FIELDS,
    DEFAULT_DATA_ROOT,
    DEFAULT_DSN,
    DEFAULT_TDX_ROOT,
    FINA_INDICATOR_FIELDS,
    INDEX_DAILY_FIELDS,
    INDEX_MEMBERSHIP_FILE,
    STOCK_DAILY_FIELDS,
    BatchResult,
    Gate,
    activate_source_version,
    archive_rows,
    build_board_identity_rows,
    clean_record,
    copy_rows,
    decimal_required,
    fail_on_gates,
    finish_batch,
    frame_to_records,
    get_board_identity_rows,
    get_index_identity_map,
    get_stock_identity_map,
    insert_batch,
    insert_gates,
    is_b_share_ts_code,
    normalize_board_membership_row,
    normalize_exchange_from_ts_code,
    normalize_index_identity_row,
    normalize_index_membership_row,
    normalize_ts_code,
    read_tdx_board_rows,
    read_tdx_index_rows,
    stable_hash,
    to_decimal,
    tushare_client,
    tushare_query,
)
from ashare_v3.ingestion.stock import normalize_stock_identity_row


ACTIVATED_BY = "codex_daily_incremental"
FIXED_CORE_INDEX_IDENTITIES = (
    "index:SH:000905",
    "index:SZ:399303",
    "index:SH:000001",
    "index:SH:000852",
    "index:SZ:399001",
    "index:SZ:399006",
    "index:SH:000300",
    "index:SH:000016",
    "index:SH:000688",
)


def batch_id(prefix: str, trade_date: str, version: str) -> str:
    require_yyyymmdd(trade_date, "trade_date")
    if not version.startswith("v"):
        raise ValueError(f"version must look like vN: {version!r}")
    return f"{prefix}_{trade_date}_{version}"


def p0_failures(gates: Sequence[Gate]) -> list[Gate]:
    return [gate for gate in gates if not gate.passed and gate.severity == "P0"]


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def ensure_batch_absent_or_failed(cur: psycopg.Cursor[Any], source_batch_id: str) -> None:
    cur.execute("SELECT status FROM common_ingest_batch WHERE batch_id = %s", (source_batch_id,))
    row = cur.fetchone()
    if row is not None:
        raise RuntimeError(f"batch already exists: {source_batch_id} status={row[0]}")


def insert_failed_audit(
    conn: psycopg.Connection[Any],
    *,
    source_batch_id: str,
    trade_date: str,
    data_domain: str,
    data_type: str,
    source: str,
    source_version: str,
    source_path: str | None,
    source_params: Mapping[str, Any] | None,
    raw_hash: str,
    row_count: int,
    gates: Sequence[Gate],
) -> None:
    failed = p0_failures(gates)
    with conn.transaction():
        with conn.cursor() as cur:
            ensure_batch_absent_or_failed(cur, source_batch_id)
            insert_batch(
                cur,
                batch_id=source_batch_id,
                trade_date=trade_date,
                data_domain=data_domain,
                data_type=data_type,
                source=source,
                source_version=source_version,
                source_path=source_path,
                source_params=source_params,
                raw_hash=raw_hash,
                row_count=row_count,
            )
            insert_gates(
                cur,
                source_batch_id=source_batch_id,
                source_version=source_version,
                data_domain=data_domain,
                data_type=data_type,
                gates=gates,
            )
            cur.execute(
                """
                UPDATE common_ingest_batch
                SET status = 'failed',
                    finished_at = now(),
                    error_count = %s,
                    error_summary = %s,
                    quality_gate_summary = %s
                WHERE batch_id = %s
                """,
                (
                    len(failed),
                    json.dumps(
                        [
                            {
                                "gate": gate.name,
                                "expected": gate.expected,
                                "actual": gate.actual,
                                "details": dict(gate.details or {}),
                            }
                            for gate in failed
                        ],
                        ensure_ascii=False,
                        default=str,
                    )[:4000],
                    Jsonb(
                        {
                            "passed": False,
                            "gate_count": len(gates),
                            "failed_gate_count": sum(1 for gate in gates if not gate.passed),
                            "gate_names": [gate.name for gate in gates],
                        }
                    ),
                    source_batch_id,
                ),
            )


def run_persisted_batch(
    conn: psycopg.Connection[Any],
    *,
    source_batch_id: str,
    trade_date: str,
    data_domain: str,
    data_type: str,
    source: str,
    source_version: str,
    source_path: str | None,
    source_params: Mapping[str, Any] | None,
    raw_hash: str,
    row_count: int,
    gates: Sequence[Gate],
    writer: Callable[[psycopg.Cursor[Any]], None],
    activation_scope_key: str,
    archive_manifest_path: str | None = None,
) -> BatchResult:
    if p0_failures(gates):
        insert_failed_audit(
            conn,
            source_batch_id=source_batch_id,
            trade_date=trade_date,
            data_domain=data_domain,
            data_type=data_type,
            source=source,
            source_version=source_version,
            source_path=source_path,
            source_params=source_params,
            raw_hash=raw_hash,
            row_count=row_count,
            gates=gates,
        )
        fail_on_gates(gates, source_batch_id)

    with conn.transaction():
        with conn.cursor() as cur:
            ensure_batch_absent_or_failed(cur, source_batch_id)
            insert_batch(
                cur,
                batch_id=source_batch_id,
                trade_date=trade_date,
                data_domain=data_domain,
                data_type=data_type,
                source=source,
                source_version=source_version,
                source_path=source_path,
                source_params=source_params,
                raw_hash=raw_hash,
                row_count=row_count,
            )
            writer(cur)
            insert_gates(
                cur,
                source_batch_id=source_batch_id,
                source_version=source_version,
                data_domain=data_domain,
                data_type=data_type,
                gates=gates,
            )
            activate_source_version(
                cur,
                data_domain=data_domain,
                data_type=data_type,
                scope_key=activation_scope_key,
                source_version=source_version,
                source_batch_id=source_batch_id,
                activated_by=ACTIVATED_BY,
            )
            finish_batch(
                cur,
                batch_id=source_batch_id,
                gates=gates,
                archive_manifest_path=archive_manifest_path,
            )
    return BatchResult(batch_id=source_batch_id, table_name=data_type, row_count=row_count)


def insert_identity_rows(
    cur: psycopg.Cursor[Any],
    table_name: str,
    columns: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
) -> int:
    column_list = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    conflict_clause = "ON CONFLICT DO NOTHING"
    sql = f"INSERT INTO {table_name} ({column_list}) VALUES ({placeholders}) {conflict_clause} RETURNING 1"
    inserted = 0
    for row in rows:
        values = [Jsonb(clean_record(row.get(column) or {})) if column == "raw_payload" else row.get(column) for column in columns]
        cur.execute(sql, values)
        if cur.fetchone() is not None:
            inserted += 1
    return inserted


def load_trade_calendar_day(conn: psycopg.Connection[Any], pro: Any, *, trade_date: str, version: str) -> tuple[BatchResult, bool]:
    source_batch_id = batch_id("trade_calendar", trade_date, version)
    source_version = source_batch_id
    center = datetime.strptime(trade_date, "%Y%m%d").date()
    start = (center - timedelta(days=20)).strftime("%Y%m%d")
    end = (center + timedelta(days=20)).strftime("%Y%m%d")
    raw_rows = frame_to_records(
        tushare_query(
            pro.trade_cal,
            exchange="SSE",
            start_date=start,
            end_date=end,
            fields="exchange,cal_date,is_open,pretrade_date",
        )
    )
    normalized = normalize_trade_calendar_rows(
        raw_rows,
        source="tushare.trade_cal",
        source_batch_id=source_batch_id,
        source_version=source_version,
    )
    rows = [row for row in normalized if row["trade_date"] == trade_date]
    gates = [
        Gate("trade_calendar_target_date_present", len(rows) == 1, "1", str(len(rows))),
        Gate("trade_calendar_unique_trade_date", len(rows) == len({row["trade_date"] for row in rows}), "0 duplicates", str(len(rows) - len({row["trade_date"] for row in rows}))),
        Gate("trade_calendar_required_fields", all(row.get("trade_date") and row.get("source_batch_id") and row.get("source_version") for row in rows), "100%", f"{len(rows)}/{len(rows)}"),
    ]

    def writer(cur: psycopg.Cursor[Any]) -> None:
        for row in rows:
            cur.execute(
                """
                INSERT INTO common_trade_calendar (
                  trade_date, exchange, is_open, prev_trade_date, next_trade_date,
                  source, source_batch_id, source_version, raw_payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (trade_date) DO UPDATE SET
                  exchange = EXCLUDED.exchange,
                  is_open = EXCLUDED.is_open,
                  prev_trade_date = EXCLUDED.prev_trade_date,
                  next_trade_date = EXCLUDED.next_trade_date,
                  source = EXCLUDED.source,
                  source_batch_id = EXCLUDED.source_batch_id,
                  source_version = EXCLUDED.source_version,
                  raw_payload = EXCLUDED.raw_payload,
                  updated_at = now()
                """,
                (
                    row["trade_date"],
                    row["exchange"],
                    row["is_open"],
                    row.get("prev_trade_date"),
                    row.get("next_trade_date"),
                    row["source"],
                    row["source_batch_id"],
                    row["source_version"],
                    Jsonb(clean_record(row.get("raw_payload") or {})),
                ),
            )

    result = run_persisted_batch(
        conn,
        source_batch_id=source_batch_id,
        trade_date=trade_date,
        data_domain="common",
        data_type="trade_calendar",
        source="tushare.trade_cal",
        source_version=source_version,
        source_path=None,
        source_params={"exchange": "SSE", "target_trade_date": trade_date, "window_start": start, "window_end": end},
        raw_hash=stable_hash(raw_rows),
        row_count=len(rows),
        gates=gates,
        writer=writer,
        activation_scope_key=f"SSE:{trade_date}",
    )
    return result, bool(rows and rows[0]["is_open"])


def load_stock_identity_day(conn: psycopg.Connection[Any], pro: Any, *, trade_date: str, version: str) -> BatchResult:
    source_batch_id = batch_id("stock_identity", trade_date, version)
    source_version = source_batch_id
    raw_rows: list[dict[str, Any]] = []
    for list_status in ("L", "D", "P"):
        raw_rows.extend(
            frame_to_records(
                pro.stock_basic(
                    exchange="",
                    list_status=list_status,
                    fields="ts_code,symbol,name,area,industry,market,list_date,delist_date,list_status",
                )
            )
        )
    rows_by_key: dict[str, dict[str, Any]] = {}
    skipped: list[str] = []
    for raw in raw_rows:
        try:
            row = normalize_stock_identity_row(
                raw,
                source="tushare.stock_basic",
                source_batch_id=source_batch_id,
                source_version=source_version,
            )
        except Exception:
            skipped.append(str(raw.get("ts_code") or ""))
            continue
        rows_by_key[row["stock_identity_key"]] = row
    rows = list(rows_by_key.values())
    gates = [
        Gate("stock_identity_non_empty", bool(rows), ">0", str(len(rows))),
        Gate("stock_identity_key_coverage", all(row.get("stock_identity_key") for row in rows), "100%", f"{len(rows)}/{len(rows)}"),
        Gate("stock_identity_unique_key", len(rows) == len({row["stock_identity_key"] for row in rows}), "0 duplicates", str(len(rows) - len({row["stock_identity_key"] for row in rows}))),
        Gate("stock_identity_no_88xxxx", not any(str(row["code"]).startswith("88") for row in rows), "0", str(sum(1 for row in rows if str(row["code"]).startswith("88")))),
        Gate("stock_identity_non_a_share_rows_filtered", True, "non-A-share source rows are filtered before stock_identity", str(len(skipped)), {"sample": skipped[:50]}, severity="P2"),
    ]

    def writer(cur: psycopg.Cursor[Any]) -> None:
        insert_identity_rows(
            cur,
            "stock_identity",
            (
                "stock_identity_key",
                "ts_code",
                "code",
                "exchange",
                "name",
                "display_code",
                "area",
                "industry",
                "market",
                "listed_date",
                "delisted_date",
                "is_st",
                "status",
                "source",
                "source_batch_id",
                "source_version",
                "raw_payload",
            ),
            rows,
        )

    return run_persisted_batch(
        conn,
        source_batch_id=source_batch_id,
        trade_date=trade_date,
        data_domain="stock",
        data_type="stock_identity",
        source="tushare.stock_basic",
        source_version=source_version,
        source_path=None,
        source_params={"list_status": ["L", "D", "P"], "identity_write_mode": "insert_missing_only"},
        raw_hash=stable_hash(raw_rows),
        row_count=len(rows),
        gates=gates,
        writer=writer,
        activation_scope_key=f"A_STOCK:{trade_date}",
    )


def load_index_identity_day(conn: psycopg.Connection[Any], pro: Any, tdx_root: Path, *, trade_date: str, version: str) -> BatchResult:
    source_batch_id = batch_id("index_identity", trade_date, version)
    source_version = source_batch_id
    raw_rows: list[dict[str, Any]] = []
    for market in ("SSE", "SZSE", "CSI", "SW", "OTH", "MSCI", "CICC", "CNI"):
        try:
            raw_rows.extend(
                frame_to_records(
                    pro.index_basic(
                        market=market,
                        fields="ts_code,name,fullname,market,publisher,index_type,category,base_date,base_point,list_date,weight_rule,desc,exp_date",
                    )
                )
            )
        except Exception:
            continue
    rows_by_key: dict[str, dict[str, Any]] = {}
    skipped: list[str] = []
    for raw in raw_rows:
        try:
            row = normalize_index_identity_row(
                raw,
                source="tushare.index_basic",
                source_batch_id=source_batch_id,
                source_version=source_version,
            )
        except Exception:
            skipped.append(str(raw.get("ts_code") or ""))
            continue
        if str(row["code"]).startswith("88"):
            skipped.append(str(row.get("ts_code") or row["code"]))
            continue
        rows_by_key[row["index_identity_key"]] = row

    tdx_index_rows = read_tdx_index_rows(tdx_root)
    for raw in tdx_index_rows:
        code = str(raw["index_code"])
        exchange = infer_index_exchange_from_code(code)
        key = make_index_identity_key(exchange, code)
        if key not in rows_by_key:
            rows_by_key[key] = {
                "index_identity_key": key,
                "ts_code": f"{code}.{exchange}" if exchange in {"SH", "SZ"} else None,
                "code": code,
                "exchange": exchange,
                "name": raw["index_name"],
                "source_namespace": "TDX",
                "publisher": None,
                "index_category": "tdx_local_membership",
                "base_date": None,
                "listed_date": None,
                "status": "active",
                "source": "tdx.local_txt.index_board",
                "source_batch_id": source_batch_id,
                "source_version": source_version,
                "raw_payload": clean_record(raw),
            }
    rows = list(rows_by_key.values())
    gates = [
        Gate("index_identity_non_empty", bool(rows), ">0", str(len(rows))),
        Gate("index_identity_key_coverage", all(row.get("index_identity_key") for row in rows), "100%", f"{len(rows)}/{len(rows)}"),
        Gate("index_identity_unique_key", len(rows) == len({row["index_identity_key"] for row in rows}), "0 duplicates", str(len(rows) - len({row["index_identity_key"] for row in rows}))),
        Gate("index_identity_no_88xxxx_board", not any(str(row["code"]).startswith("88") for row in rows), "0", str(sum(1 for row in rows if str(row["code"]).startswith("88")))),
        Gate("index_identity_non_index_rows_filtered", True, "non-index/88xxxx source rows are filtered before index_identity", str(len(skipped)), {"sample": skipped[:50]}, severity="P2"),
    ]

    def writer(cur: psycopg.Cursor[Any]) -> None:
        insert_identity_rows(
            cur,
            "index_identity",
            (
                "index_identity_key",
                "ts_code",
                "code",
                "exchange",
                "name",
                "source_namespace",
                "publisher",
                "index_category",
                "base_date",
                "listed_date",
                "status",
                "source",
                "source_batch_id",
                "source_version",
                "raw_payload",
            ),
            rows,
        )

    return run_persisted_batch(
        conn,
        source_batch_id=source_batch_id,
        trade_date=trade_date,
        data_domain="index",
        data_type="index_identity",
        source="tushare.index_basic+tdx.local_txt.index_board",
        source_version=source_version,
        source_path=str(tdx_root / INDEX_MEMBERSHIP_FILE),
        source_params={"markets": ["SSE", "SZSE", "CSI", "SW", "OTH", "MSCI", "CICC", "CNI"], "identity_write_mode": "insert_missing_only"},
        raw_hash=stable_hash(raw_rows + tdx_index_rows),
        row_count=len(rows),
        gates=gates,
        writer=writer,
        activation_scope_key=f"INDEX:{trade_date}",
    )


def load_board_identity_day(conn: psycopg.Connection[Any], tdx_root: Path, *, trade_date: str, version: str) -> BatchResult:
    source_batch_id = batch_id("board_identity", trade_date, version)
    source_version = source_batch_id
    raw_rows = read_tdx_board_rows(tdx_root)
    rows = build_board_identity_rows(raw_rows, source_batch_id=source_batch_id, source_version=source_version)
    gates = [
        Gate("board_identity_non_empty", bool(rows), ">0", str(len(rows))),
        Gate("board_identity_key_coverage", all(row.get("board_identity_key") for row in rows), "100%", f"{len(rows)}/{len(rows)}"),
        Gate("board_identity_unique_key", len(rows) == len({row["board_identity_key"] for row in rows}), "0 duplicates", str(len(rows) - len({row["board_identity_key"] for row in rows}))),
        Gate("board_identity_code_shape", all(str(row["board_code"]).startswith("88") for row in rows), "all board_code starts with 88", str(sum(1 for row in rows if not str(row["board_code"]).startswith("88")))),
    ]

    def writer(cur: psycopg.Cursor[Any]) -> None:
        insert_identity_rows(
            cur,
            "board_identity",
            (
                "board_identity_key",
                "board_code",
                "board_name",
                "board_type",
                "source_namespace",
                "source_file",
                "status",
                "source",
                "source_batch_id",
                "source_version",
                "raw_payload",
            ),
            rows,
        )

    return run_persisted_batch(
        conn,
        source_batch_id=source_batch_id,
        trade_date=trade_date,
        data_domain="board",
        data_type="board_identity",
        source="tdx.local_txt.board",
        source_version=source_version,
        source_path=str(tdx_root),
        source_params={"files": sorted(BOARD_FILE_TYPES), "identity_write_mode": "insert_missing_only"},
        raw_hash=stable_hash(raw_rows),
        row_count=len(rows),
        gates=gates,
        writer=writer,
        activation_scope_key=f"TDX:{trade_date}",
    )


def load_memberships_day(conn: psycopg.Connection[Any], tdx_root: Path, data_root: Path, *, trade_date: str, version: str) -> list[BatchResult]:
    raw_board_rows = read_tdx_board_rows(tdx_root)
    raw_index_rows = read_tdx_index_rows(tdx_root)
    board_batch = batch_id("board_membership", trade_date, version)
    index_batch = batch_id("index_membership", trade_date, version)
    board_rows = [
        normalize_board_membership_row(row, trade_date=trade_date, source_batch_id=board_batch, source_version=board_batch)
        for row in raw_board_rows
    ]
    index_rows = [
        normalize_index_membership_row(row, trade_date=trade_date, source_batch_id=index_batch, source_version=index_batch)
        for row in raw_index_rows
    ]
    with conn.cursor() as cur:
        cur.execute("SELECT stock_identity_key FROM stock_identity")
        stock_keys = {str(row[0]) for row in cur.fetchall()}
        cur.execute("SELECT index_identity_key FROM index_identity")
        index_keys = {str(row[0]) for row in cur.fetchall()}
        cur.execute("SELECT board_identity_key FROM board_identity")
        board_keys = {str(row[0]) for row in cur.fetchall()}

    board_missing_stock = sorted({row["stock_identity_key"] for row in board_rows} - stock_keys)
    board_missing_board = sorted({row["board_identity_key"] for row in board_rows} - board_keys)
    index_missing_stock = sorted({row["stock_identity_key"] for row in index_rows} - stock_keys)
    index_missing_index = sorted({row["index_identity_key"] for row in index_rows} - index_keys)
    board_rows = [
        row
        for row in board_rows
        if row["stock_identity_key"] in stock_keys and row["board_identity_key"] in board_keys
    ]
    index_rows = [
        row
        for row in index_rows
        if row["stock_identity_key"] in stock_keys and row["index_identity_key"] in index_keys
    ]
    board_unique = {(row["trade_date"], row["board_identity_key"], row["stock_identity_key"]) for row in board_rows}
    index_unique = {(row["trade_date"], row["index_identity_key"], row["stock_identity_key"]) for row in index_rows}
    board_gates = [
        Gate("board_membership_non_empty", bool(board_rows), ">0", str(len(board_rows))),
        Gate("board_membership_board_identity_coverage", True, "100% for inserted rows", "0"),
        Gate("board_membership_stock_identity_coverage", True, "100% for inserted rows", "0"),
        Gate("board_membership_unresolved_source_rows_filtered", True, "unresolved source rows filtered before activation", str(len(board_missing_stock) + len(board_missing_board)), {"missing_stock_identity_keys": board_missing_stock[:50], "missing_board_identity_keys": board_missing_board[:50]}, severity="P2"),
        Gate("board_membership_unique_key", len(board_unique) == len(board_rows), "0 duplicates", str(len(board_rows) - len(board_unique))),
        Gate("board_membership_no_88_stock", not any(str(row["stock_code"]).startswith("88") for row in board_rows), "0", str(sum(1 for row in board_rows if str(row["stock_code"]).startswith("88")))),
    ]
    index_gates = [
        Gate("index_membership_non_empty", bool(index_rows), ">0", str(len(index_rows))),
        Gate("index_membership_index_identity_coverage", True, "100% for inserted rows", "0"),
        Gate("index_membership_stock_identity_coverage", True, "100% for inserted rows", "0"),
        Gate("index_membership_unresolved_source_rows_filtered", True, "unresolved source rows filtered before activation", str(len(index_missing_stock) + len(index_missing_index)), {"missing_stock_identity_keys": index_missing_stock[:50], "missing_index_identity_keys": index_missing_index[:50]}, severity="P2"),
        Gate("index_membership_unique_key", len(index_unique) == len(index_rows), "0 duplicates", str(len(index_rows) - len(index_unique))),
        Gate("index_membership_no_88_stock", not any(str(row["stock_code"]).startswith("88") for row in index_rows), "0", str(sum(1 for row in index_rows if str(row["stock_code"]).startswith("88")))),
    ]
    index_manifest = archive_rows(dataset="index_membership_fact", rows=index_rows, source_batch_id=index_batch, source_version=index_batch, data_root=data_root, partition_key="trade_date")
    board_manifest = archive_rows(dataset="board_membership_fact", rows=board_rows, source_batch_id=board_batch, source_version=board_batch, data_root=data_root, partition_key="trade_date")

    def write_index(cur: psycopg.Cursor[Any]) -> None:
        copy_rows(
            cur,
            "index_membership_fact",
            ("trade_date", "index_identity_key", "stock_identity_key", "index_code", "index_name", "stock_code", "stock_name", "source", "source_file", "source_batch_id", "source_version", "raw_payload"),
            (
                (row["trade_date"], row["index_identity_key"], row["stock_identity_key"], row["index_code"], row.get("index_name"), row["stock_code"], row.get("stock_name"), row["source"], row.get("source_file"), row["source_batch_id"], row["source_version"], Jsonb(clean_record(row.get("raw_payload") or {})))
                for row in index_rows
            ),
        )

    def write_board(cur: psycopg.Cursor[Any]) -> None:
        copy_rows(
            cur,
            "board_membership_fact",
            ("trade_date", "board_identity_key", "stock_identity_key", "board_code", "board_name", "board_type", "stock_code", "stock_name", "source", "source_file", "source_batch_id", "source_version", "raw_payload"),
            (
                (row["trade_date"], row["board_identity_key"], row["stock_identity_key"], row["board_code"], row.get("board_name"), row["board_type"], row["stock_code"], row.get("stock_name"), row["source"], row.get("source_file"), row["source_batch_id"], row["source_version"], Jsonb(clean_record(row.get("raw_payload") or {})))
                for row in board_rows
            ),
        )

    return [
        run_persisted_batch(
            conn,
            source_batch_id=index_batch,
            trade_date=trade_date,
            data_domain="index",
            data_type="index_membership",
            source="tdx.local_txt.index_board",
            source_version=index_batch,
            source_path=str(tdx_root / INDEX_MEMBERSHIP_FILE),
            source_params={"file": INDEX_MEMBERSHIP_FILE},
            raw_hash=stable_hash(raw_index_rows),
            row_count=len(index_rows),
            gates=index_gates,
            writer=write_index,
            activation_scope_key=f"TDX:{trade_date}",
            archive_manifest_path=index_manifest,
        ),
        run_persisted_batch(
            conn,
            source_batch_id=board_batch,
            trade_date=trade_date,
            data_domain="board",
            data_type="board_membership",
            source="tdx.local_txt.board",
            source_version=board_batch,
            source_path=str(tdx_root),
            source_params={"files": sorted(BOARD_FILE_TYPES)},
            raw_hash=stable_hash(raw_board_rows),
            row_count=len(board_rows),
            gates=board_gates,
            writer=write_board,
            activation_scope_key=f"TDX:{trade_date}",
            archive_manifest_path=board_manifest,
        ),
    ]


def load_stock_daily_day(conn: psycopg.Connection[Any], pro: Any, data_root: Path, *, trade_date: str, version: str) -> BatchResult:
    source_batch_id = batch_id("stock_daily", trade_date, version)
    source_version = source_batch_id
    raw_rows = frame_to_records(pro.daily(trade_date=trade_date, fields=STOCK_DAILY_FIELDS))
    adj_rows = frame_to_records(pro.adj_factor(trade_date=trade_date, fields=ADJ_FACTOR_FIELDS))
    with conn.cursor() as cur:
        stock_map = get_stock_identity_map(cur)
    adj_by_key = {
        (normalize_ts_code(row.get("ts_code")), str(row.get("trade_date"))): to_decimal(row.get("adj_factor"))
        for row in adj_rows
    }
    rows: list[dict[str, Any]] = []
    missing_identity: set[str] = set()
    missing_adj: set[tuple[str, str]] = set()
    for raw in raw_rows:
        ts_code = normalize_ts_code(raw.get("ts_code"))
        if not ts_code or ts_code not in stock_map:
            if ts_code and not is_b_share_ts_code(ts_code):
                missing_identity.add(ts_code)
            continue
        adj = adj_by_key.get((ts_code, trade_date))
        if adj is None:
            missing_adj.add((ts_code, trade_date))
            continue
        identity = stock_map[ts_code]
        rows.append(
            {
                "stock_identity_key": identity["stock_identity_key"],
                "trade_date": trade_date,
                "ts_code": ts_code,
                "code": identity["code"],
                "exchange": identity["exchange"],
                "name": identity["name"],
                "open": decimal_required(raw.get("open"), "open"),
                "high": decimal_required(raw.get("high"), "high"),
                "low": decimal_required(raw.get("low"), "low"),
                "close": decimal_required(raw.get("close"), "close"),
                "volume": to_decimal(raw.get("vol")),
                "amount": to_decimal(raw.get("amount")),
                "adj_factor": adj,
                "adjust_type": "qfq",
                "source": "tushare.daily+adj_factor.qfq_daily",
                "source_batch_id": source_batch_id,
                "source_version": source_version,
                "official_daily_proof": True,
                "raw_payload": clean_record({**raw, "adj_factor": str(adj), "qfq_factor": "1"}),
            }
        )
    unique_keys = {(row["stock_identity_key"], row["trade_date"]) for row in rows}
    gates = [
        Gate("stock_daily_non_empty", bool(rows), ">0", str(len(rows))),
        Gate("stock_daily_identity_coverage", not missing_identity, "0 unresolved non-B-share", str(len(missing_identity)), {"missing_ts_codes": sorted(missing_identity)[:50]}),
        Gate("stock_daily_adj_factor_coverage", not missing_adj, "100%", str(len(missing_adj)), {"missing": [{"ts_code": a, "trade_date": b} for a, b in sorted(missing_adj)[:50]]}),
        Gate("stock_daily_unique_key", len(unique_keys) == len(rows), "0 duplicates", str(len(rows) - len(unique_keys))),
        Gate("stock_daily_no_88xxxx", not any(str(row["code"]).startswith("88") for row in rows), "0", str(sum(1 for row in rows if str(row["code"]).startswith("88")))),
        Gate("stock_daily_official_proof", all(row["official_daily_proof"] for row in rows), "100%", f"{sum(1 for row in rows if row['official_daily_proof'])}/{len(rows)}"),
    ]
    manifest_path = archive_rows(dataset="stock_daily_bar_fact", rows=rows, source_batch_id=source_batch_id, source_version=source_version, data_root=data_root, partition_key="trade_date") if rows else None

    def writer(cur: psycopg.Cursor[Any]) -> None:
        copy_rows(
            cur,
            "stock_daily_bar_fact",
            ("stock_identity_key", "trade_date", "ts_code", "code", "exchange", "name", "open", "high", "low", "close", "volume", "amount", "adj_factor", "adjust_type", "source", "source_batch_id", "source_version", "official_daily_proof", "raw_payload"),
            ((row["stock_identity_key"], row["trade_date"], row["ts_code"], row["code"], row["exchange"], row.get("name"), row["open"], row["high"], row["low"], row["close"], row.get("volume"), row.get("amount"), row.get("adj_factor"), row["adjust_type"], row["source"], row["source_batch_id"], row["source_version"], row["official_daily_proof"], Jsonb(clean_record(row.get("raw_payload") or {}))) for row in rows),
        )

    return run_persisted_batch(
        conn,
        source_batch_id=source_batch_id,
        trade_date=trade_date,
        data_domain="stock",
        data_type="stock_daily",
        source="tushare.daily+adj_factor.qfq_daily",
        source_version=source_version,
        source_path=None,
        source_params={"trade_date": trade_date},
        raw_hash=stable_hash(raw_rows + adj_rows),
        row_count=len(rows),
        gates=gates,
        writer=writer,
        activation_scope_key=trade_date,
        archive_manifest_path=manifest_path,
    )


def load_stock_daily_basic_day(conn: psycopg.Connection[Any], pro: Any, data_root: Path, *, trade_date: str, version: str) -> BatchResult:
    source_batch_id = batch_id("stock_daily_basic", trade_date, version)
    source_version = source_batch_id
    raw_rows = frame_to_records(pro.daily_basic(trade_date=trade_date, fields=DAILY_BASIC_FIELDS))
    with conn.cursor() as cur:
        stock_map = get_stock_identity_map(cur)
    rows: list[dict[str, Any]] = []
    missing_identity: set[str] = set()
    for raw in raw_rows:
        ts_code = normalize_ts_code(raw.get("ts_code"))
        if not ts_code or ts_code not in stock_map:
            if ts_code and not is_b_share_ts_code(ts_code):
                missing_identity.add(ts_code)
            continue
        identity = stock_map[ts_code]
        rows.append(
            {
                "stock_identity_key": identity["stock_identity_key"],
                "trade_date": trade_date,
                "ts_code": ts_code,
                "code": identity["code"],
                "exchange": identity["exchange"],
                "close": to_decimal(raw.get("close")),
                "turnover_rate": to_decimal(raw.get("turnover_rate")),
                "turnover_rate_f": to_decimal(raw.get("turnover_rate_f")),
                "volume_ratio": to_decimal(raw.get("volume_ratio")),
                "pe": to_decimal(raw.get("pe")),
                "pe_ttm": to_decimal(raw.get("pe_ttm")),
                "pb": to_decimal(raw.get("pb")),
                "ps": to_decimal(raw.get("ps")),
                "ps_ttm": to_decimal(raw.get("ps_ttm")),
                "dv_ratio": to_decimal(raw.get("dv_ratio")),
                "dv_ttm": to_decimal(raw.get("dv_ttm")),
                "total_share": to_decimal(raw.get("total_share")),
                "float_share": to_decimal(raw.get("float_share")),
                "free_share": to_decimal(raw.get("free_share")),
                "total_mv": to_decimal(raw.get("total_mv")),
                "circ_mv": to_decimal(raw.get("circ_mv")),
                "source": "tushare.daily_basic",
                "source_batch_id": source_batch_id,
                "source_version": source_version,
                "raw_payload": clean_record(raw),
            }
        )
    unique_keys = {(row["stock_identity_key"], row["trade_date"]) for row in rows}
    gates = [
        Gate("stock_daily_basic_non_empty", bool(rows), ">0", str(len(rows))),
        Gate("stock_daily_basic_identity_coverage", not missing_identity, "0 unresolved non-B-share", str(len(missing_identity)), {"missing_ts_codes": sorted(missing_identity)[:50]}),
        Gate("stock_daily_basic_unique_key", len(unique_keys) == len(rows), "0 duplicates", str(len(rows) - len(unique_keys))),
        Gate("stock_daily_basic_no_88xxxx", not any(str(row["code"]).startswith("88") for row in rows), "0", str(sum(1 for row in rows if str(row["code"]).startswith("88")))),
    ]
    manifest_path = archive_rows(dataset="stock_daily_basic", rows=rows, source_batch_id=source_batch_id, source_version=source_version, data_root=data_root, partition_key="trade_date") if rows else None

    def writer(cur: psycopg.Cursor[Any]) -> None:
        copy_rows(
            cur,
            "stock_daily_basic",
            ("stock_identity_key", "trade_date", "ts_code", "code", "exchange", "close", "turnover_rate", "turnover_rate_f", "volume_ratio", "pe", "pe_ttm", "pb", "ps", "ps_ttm", "dv_ratio", "dv_ttm", "total_share", "float_share", "free_share", "total_mv", "circ_mv", "source", "source_batch_id", "source_version", "raw_payload"),
            ((row["stock_identity_key"], row["trade_date"], row["ts_code"], row["code"], row["exchange"], row.get("close"), row.get("turnover_rate"), row.get("turnover_rate_f"), row.get("volume_ratio"), row.get("pe"), row.get("pe_ttm"), row.get("pb"), row.get("ps"), row.get("ps_ttm"), row.get("dv_ratio"), row.get("dv_ttm"), row.get("total_share"), row.get("float_share"), row.get("free_share"), row.get("total_mv"), row.get("circ_mv"), row["source"], row["source_batch_id"], row["source_version"], Jsonb(clean_record(row.get("raw_payload") or {}))) for row in rows),
        )

    return run_persisted_batch(
        conn,
        source_batch_id=source_batch_id,
        trade_date=trade_date,
        data_domain="stock",
        data_type="stock_daily_basic",
        source="tushare.daily_basic",
        source_version=source_version,
        source_path=None,
        source_params={"trade_date": trade_date},
        raw_hash=stable_hash(raw_rows),
        row_count=len(rows),
        gates=gates,
        writer=writer,
        activation_scope_key=trade_date,
        archive_manifest_path=manifest_path,
    )


def load_index_daily_day(
    conn: psycopg.Connection[Any],
    pro: Any,
    data_root: Path,
    *,
    trade_date: str,
    version: str,
    mootdx_offset: int,
    prefetched_raw_rows: Sequence[Mapping[str, Any]] | None = None,
    endpoint_provenance: Mapping[str, Any] | None = None,
) -> BatchResult:
    source_batch_id = batch_id("index_daily", trade_date, version)
    source_version = source_batch_id
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ii.index_identity_key, ii.ts_code, ii.code, ii.exchange, ii.name
            FROM index_membership_fact im
            JOIN index_identity ii ON ii.index_identity_key = im.index_identity_key
            WHERE im.trade_date = %s
            ORDER BY ii.code
            """,
            (trade_date,),
        )
        indexes = [dict(index_identity_key=k, ts_code=ts_code, code=code, exchange=exchange, name=name) for k, ts_code, code, exchange, name in cur.fetchall()]
        cur.execute(
            """
            SELECT index_identity_key, ts_code, code, exchange, name
            FROM index_identity
            WHERE index_identity_key = ANY(%s)
            ORDER BY index_identity_key
            """,
            (list(FIXED_CORE_INDEX_IDENTITIES),),
        )
        fixed_indexes = [
            dict(index_identity_key=k, ts_code=ts_code, code=code, exchange=exchange, name=name)
            for k, ts_code, code, exchange, name in cur.fetchall()
        ]
    indexes_by_key = {str(index["index_identity_key"]): index for index in indexes}
    for index in fixed_indexes:
        indexes_by_key.setdefault(str(index["index_identity_key"]), index)
    missing_fixed_identity_keys = sorted(set(FIXED_CORE_INDEX_IDENTITIES) - set(indexes_by_key))
    indexes = sorted(indexes_by_key.values(), key=lambda item: (str(item["code"]), str(item["exchange"])))
    symbols = [IndexDailySymbol(code=index["code"], exchange=index["exchange"], name=index["name"]) for index in indexes]
    if prefetched_raw_rows is None:
        source = MootdxDailyBarSource(offset=mootdx_offset)
        raw_rows, endpoint_provenance = _fetch_and_close_mootdx_phase(
            source,
            lambda: source.fetch_index_daily_bars(
                indexes=symbols,
                start_date=trade_date,
                end_date=trade_date,
            ),
        )
    else:
        raw_rows = [dict(row) for row in prefetched_raw_rows]
    mootdx_raw_rows = list(raw_rows)
    rows: list[dict[str, Any]] = []
    for item in raw_rows:
        key = f"index:{item.get('exchange')}:{item.get('code')}"
        index = next((idx for idx in indexes if idx["index_identity_key"] == key), None)
        if not index:
            continue
        rows.append(
            {
                "index_identity_key": index["index_identity_key"],
                "trade_date": trade_date,
                "code": index["code"],
                "exchange": index["exchange"],
                "name": index["name"],
                "open": decimal_required(item.get("open"), "open"),
                "high": decimal_required(item.get("high"), "high"),
                "low": decimal_required(item.get("low"), "low"),
                "close": decimal_required(item.get("close"), "close"),
                "volume": to_decimal(item.get("vol")) or to_decimal(item.get("volume")),
                "amount": to_decimal(item.get("amount")),
                "source": "mootdx.index",
                "source_batch_id": source_batch_id,
                "source_version": source_version,
                "raw_payload": clean_record(item),
            }
        )
    actual_keys = {row["index_identity_key"] for row in rows}
    missing_indexes = [index for index in indexes if index["index_identity_key"] not in actual_keys]
    unresolved: list[str] = []
    for index in missing_indexes:
        candidates = [str(value) for value in (index.get("ts_code"), f"{index['code']}.{index['exchange']}") if value]
        fallback_raw: list[dict[str, Any]] = []
        for ts_code in dict.fromkeys(candidates):
            try:
                fallback_raw = frame_to_records(tushare_query(pro.index_daily, ts_code=ts_code, start_date=trade_date, end_date=trade_date, fields=INDEX_DAILY_FIELDS, retries=3))
            except Exception:
                fallback_raw = []
            if fallback_raw:
                break
        if not fallback_raw:
            unresolved.append(str(index["index_identity_key"]))
            continue
        raw_rows.extend(fallback_raw)
        for item in fallback_raw:
            rows.append(
                {
                    "index_identity_key": index["index_identity_key"],
                    "trade_date": trade_date,
                    "code": index["code"],
                    "exchange": index["exchange"],
                    "name": index["name"],
                    "open": decimal_required(item.get("open"), "open"),
                    "high": decimal_required(item.get("high"), "high"),
                    "low": decimal_required(item.get("low"), "low"),
                    "close": decimal_required(item.get("close"), "close"),
                    "volume": to_decimal(item.get("vol")),
                    "amount": to_decimal(item.get("amount")),
                    "source": "tushare.index_daily.fallback",
                    "source_batch_id": source_batch_id,
                    "source_version": source_version,
                    "raw_payload": clean_record(item),
                }
            )
    unique_keys = {(row["index_identity_key"], row["trade_date"]) for row in rows}
    fixed_present = sorted(set(FIXED_CORE_INDEX_IDENTITIES) & {str(row["index_identity_key"]) for row in rows})
    missing_fixed_daily_keys = sorted(set(FIXED_CORE_INDEX_IDENTITIES) - set(fixed_present))
    gates = [
        Gate("index_daily_non_empty", bool(rows), ">0", str(len(rows))),
        Gate("index_daily_identity_coverage", True, "100% for inserted rows", "0"),
        Gate("index_daily_fixed_core_identity_coverage", not missing_fixed_identity_keys, "all fixed core index identities exist", str(len(missing_fixed_identity_keys)), {"missing": missing_fixed_identity_keys}),
        Gate("index_daily_fixed_core_daily_coverage", not missing_fixed_daily_keys, "all fixed core indexes have daily rows", str(len(missing_fixed_daily_keys)), {"missing": missing_fixed_daily_keys}),
        Gate("index_daily_unresolved_source_rows_filtered", True, "indexes without daily rows filtered before activation", str(len(unresolved)), {"missing": unresolved[:50]}, severity="P2"),
        Gate("index_daily_unique_key", len(unique_keys) == len(rows), "0 duplicates", str(len(rows) - len(unique_keys))),
        Gate("index_daily_no_88xxxx", not any(str(row["code"]).startswith("88") for row in rows), "0", str(sum(1 for row in rows if str(row["code"]).startswith("88")))),
        Gate(
            "index_daily_mootdx_single_winning_endpoint",
            _rows_match_endpoint_provenance(mootdx_raw_rows, endpoint_provenance),
            "one winning endpoint/attempt",
            str((endpoint_provenance or {}).get("endpoint_id") or ""),
            dict(endpoint_provenance or {}),
        ),
    ]
    manifest_path = archive_rows(dataset="index_daily_bar_fact", rows=rows, source_batch_id=source_batch_id, source_version=source_version, data_root=data_root, partition_key="trade_date") if rows else None

    def writer(cur: psycopg.Cursor[Any]) -> None:
        copy_rows(
            cur,
            "index_daily_bar_fact",
            ("index_identity_key", "trade_date", "code", "exchange", "name", "open", "high", "low", "close", "volume", "amount", "source", "source_batch_id", "source_version", "raw_payload"),
            ((row["index_identity_key"], row["trade_date"], row["code"], row["exchange"], row.get("name"), row["open"], row["high"], row["low"], row["close"], row.get("volume"), row.get("amount"), row["source"], row["source_batch_id"], row["source_version"], Jsonb(clean_record(row.get("raw_payload") or {}))) for row in rows),
        )

    return run_persisted_batch(
        conn,
        source_batch_id=source_batch_id,
        trade_date=trade_date,
        data_domain="index",
        data_type="index_daily",
        source="mootdx.index+tushare.index_daily.fallback",
        source_version=source_version,
        source_path=None,
        source_params={"trade_date": trade_date, "requested_index_count": len(indexes), "mootdx_offset": mootdx_offset, "fixed_core_index_identities": list(FIXED_CORE_INDEX_IDENTITIES), "mootdx_endpoint_provenance": dict(endpoint_provenance or {})},
        raw_hash=stable_hash(raw_rows),
        row_count=len(rows),
        gates=gates,
        writer=writer,
        activation_scope_key=trade_date,
        archive_manifest_path=manifest_path,
    )


def load_board_daily_day(
    conn: psycopg.Connection[Any],
    data_root: Path,
    *,
    trade_date: str,
    version: str,
    mootdx_offset: int,
    prefetched_raw_rows: Sequence[Mapping[str, Any]] | None = None,
    endpoint_provenance: Mapping[str, Any] | None = None,
) -> BatchResult:
    source_batch_id = batch_id("board_daily", trade_date, version)
    source_version = source_batch_id
    with conn.cursor() as cur:
        board_rows = get_board_identity_rows(cur)
    boards = [BoardDailySymbol(board_code=row["board_code"], board_name=row["board_name"], board_type=row["board_type"]) for row in board_rows]
    if prefetched_raw_rows is None:
        source = MootdxDailyBarSource(offset=mootdx_offset)
        raw_rows, endpoint_provenance = _fetch_and_close_mootdx_phase(
            source,
            lambda: source.fetch_board_daily_bars(
                boards=boards,
                start_date=trade_date,
                end_date=trade_date,
            ),
        )
    else:
        raw_rows = [dict(row) for row in prefetched_raw_rows]
    rows = [normalize_board_daily_bar_row(row, source="mootdx.index", source_batch_id=source_batch_id, source_version=source_version) for row in raw_rows]
    requested_keys = {board.board_identity_key for board in boards}
    actual_keys = {str(row["board_identity_key"]) for row in rows}
    missing = sorted(requested_keys - actual_keys)
    unique_keys = {(row["board_identity_key"], row["trade_date"]) for row in rows}
    gates = [
        Gate("board_daily_non_empty", bool(rows), ">0", str(len(rows))),
        Gate("board_daily_identity_coverage", not missing, "all requested boards have rows", str(len(missing)), {"missing": missing[:50]}),
        Gate("board_daily_unique_key", len(unique_keys) == len(rows), "0 duplicates", str(len(rows) - len(unique_keys))),
        Gate("board_daily_code_shape", all(str(row["board_code"]).startswith("88") for row in rows), "all board_code starts with 88", str(sum(1 for row in rows if not str(row["board_code"]).startswith("88")))),
        Gate(
            "board_daily_mootdx_single_winning_endpoint",
            _rows_match_endpoint_provenance(raw_rows, endpoint_provenance),
            "one winning endpoint/attempt",
            str((endpoint_provenance or {}).get("endpoint_id") or ""),
            dict(endpoint_provenance or {}),
        ),
    ]
    manifest_path = archive_rows(dataset="board_daily_bar_fact", rows=rows, source_batch_id=source_batch_id, source_version=source_version, data_root=data_root, partition_key="trade_date") if rows else None

    def writer(cur: psycopg.Cursor[Any]) -> None:
        copy_rows(
            cur,
            "board_daily_bar_fact",
            ("board_identity_key", "trade_date", "board_code", "board_name", "board_type", "open", "high", "low", "close", "volume", "amount", "source", "source_batch_id", "source_version", "raw_payload"),
            ((row["board_identity_key"], row["trade_date"], row["board_code"], row.get("board_name"), row["board_type"], row["open"], row["high"], row["low"], row["close"], row.get("volume"), row.get("amount"), row["source"], row["source_batch_id"], row["source_version"], Jsonb(clean_record(row.get("raw_payload") or {}))) for row in rows),
        )

    return run_persisted_batch(
        conn,
        source_batch_id=source_batch_id,
        trade_date=trade_date,
        data_domain="board",
        data_type="board_daily",
        source="mootdx.index",
        source_version=source_version,
        source_path=None,
        source_params={"trade_date": trade_date, "requested_board_count": len(boards), "mootdx_offset": mootdx_offset, "mootdx_endpoint_provenance": dict(endpoint_provenance or {})},
        raw_hash=stable_hash(raw_rows),
        row_count=len(rows),
        gates=gates,
        writer=writer,
        activation_scope_key=trade_date,
        archive_manifest_path=manifest_path,
    )


def _fetch_and_close_mootdx_phase(
    source: Any,
    fetch: Callable[[], Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        rows = frame_to_records(fetch())
    finally:
        try:
            source.close()
        except Exception as exc:
            setattr(
                exc,
                "mootdx_endpoint_provenance",
                dict(source.endpoint_provenance or {}),
            )
            raise
    return rows, dict(source.endpoint_provenance or {})


def prepare_mootdx_daily_bundle(
    *,
    indexes: Sequence[IndexDailySymbol],
    boards: Sequence[BoardDailySymbol],
    trade_date: str,
    mootdx_offset: int,
    endpoint_manager: MootdxEndpointManager | None = None,
    source_factory: Callable[..., Any] = MootdxDailyBarSource,
    attempt_id: str | None = None,
) -> dict[str, Any]:
    """Prepare only the index+board Mootdx sub-bundle before either fact commit."""

    manager = endpoint_manager or MootdxEndpointManager.from_toml()
    base_attempt_id = attempt_id or f"n1_real_daily_bundle__{trade_date}"
    previous_endpoint: str | None = None
    retry_reason: str | None = None
    attempts: list[dict[str, Any]] = []
    for replay_count in range(2):
        current_attempt_id = (
            base_attempt_id if replay_count == 0 else f"{base_attempt_id}__retry_1"
        )
        source = source_factory(
            endpoint_manager=manager,
            attempt_id=current_attempt_id,
            offset=mootdx_offset,
            failover_from=previous_endpoint,
            failover_reason=retry_reason,
        )
        try:
            board_rows = frame_to_records(
                source.fetch_board_daily_bars(
                    boards=boards,
                    start_date=trade_date,
                    end_date=trade_date,
                )
            ) if boards else []
            index_rows = frame_to_records(
                source.fetch_index_daily_bars(
                    indexes=indexes,
                    start_date=trade_date,
                    end_date=trade_date,
                )
            ) if indexes else []
        except Exception as exc:
            provenance = dict(source.endpoint_provenance or {})
            source.close()
            attempts.append(
                {
                    **provenance,
                    "status": "failed",
                    "failure_kind": provenance.get("retry_reason")
                    or type(exc).__name__,
                }
            )
            if (
                replay_count == 0
                and manager.n1_failover_mode == "active"
                and provenance.get("would_retry") is True
            ):
                previous_endpoint = str(provenance.get("endpoint_id") or "") or None
                retry_reason = str(provenance.get("retry_reason") or "runtime_failure")
                continue
            setattr(
                exc,
                "mootdx_endpoint_provenance",
                {
                    **provenance,
                    "attempts": [dict(row) for row in attempts],
                    "winning_attempt_id": None,
                },
            )
            raise
        provenance = {
            **dict(source.endpoint_provenance or {}),
            "replay_count": replay_count,
        }
        if not _rows_match_endpoint_provenance(
            [*board_rows, *index_rows],
            provenance,
        ):
            raise RuntimeError(
                "Mootdx bundle contains mixed endpoint or attempt provenance"
            )
        attempts.append(
            {
                **provenance,
                "status": "winning",
                "failure_kind": None,
            }
        )
        provenance = {
            **provenance,
            "attempts": [dict(row) for row in attempts],
            "winning_attempt_id": provenance.get("attempt_id"),
        }
        source.close()
        return {
            "board": board_rows,
            "index": index_rows,
            "mootdx_endpoint_provenance": provenance,
        }
    raise RuntimeError("Mootdx active bundle replay exhausted")


def _rows_match_endpoint_provenance(
    rows: Sequence[Mapping[str, Any]],
    provenance: Mapping[str, Any] | None,
) -> bool:
    expected_endpoint = str((provenance or {}).get("endpoint_id") or "")
    expected_attempt = str((provenance or {}).get("attempt_id") or "")
    expected_transport = str((provenance or {}).get("transport") or "")
    if not expected_endpoint or not expected_attempt or not expected_transport:
        return False
    for row in rows:
        row_provenance = row.get("mootdx_endpoint_provenance")
        if not isinstance(row_provenance, Mapping):
            return False
        if (
            str(row_provenance.get("endpoint_id") or "") != expected_endpoint
            or str(row_provenance.get("attempt_id") or "") != expected_attempt
            or str(row_provenance.get("transport") or "") != expected_transport
        ):
            return False
    return True


def load_financial_day(
    conn: psycopg.Connection[Any],
    pro: Any,
    data_root: Path,
    *,
    trade_date: str,
    version: str,
    sleep_seconds: float,
) -> BatchResult:
    source_batch_id = batch_id("stock_financial", trade_date, version)
    source_version = source_batch_id
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT source_version
            FROM common_active_source_version
            WHERE data_domain = 'stock'
              AND data_type = 'stock_daily'
              AND scope_key = %s
            """,
            (trade_date,),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(f"stock_daily active source version is required before stock_financial: {trade_date}")
        stock_daily_source_version = str(row[0])
        cur.execute(
            """
            SELECT source_version
            FROM common_active_source_version
            WHERE data_domain = 'stock'
              AND data_type = 'stock_daily_basic'
              AND scope_key = %s
            """,
            (trade_date,),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(f"stock_daily_basic active source version is required before stock_financial: {trade_date}")
        daily_basic_source_version = str(row[0])
        cur.execute(
            """
            SELECT
              d.stock_identity_key,
              d.ts_code,
              d.code,
              d.exchange,
              d.name,
              b.pe_ttm,
              b.pe,
              b.total_mv,
              b.circ_mv,
              b.raw_payload
            FROM stock_daily_bar_fact d
            LEFT JOIN stock_daily_basic b
              ON b.stock_identity_key = d.stock_identity_key
             AND b.trade_date = d.trade_date
             AND b.source_version = %s
            WHERE d.trade_date = %s
              AND d.source_version = %s
            ORDER BY d.stock_identity_key
            """,
            (daily_basic_source_version, trade_date, stock_daily_source_version),
        )
        stock_universe = [
            {
                "stock_identity_key": r[0],
                "ts_code": r[1],
                "code": r[2],
                "exchange": r[3],
                "name": r[4],
                "pe_ttm": r[5],
                "pe": r[6],
                "total_mv": r[7],
                "circ_mv": r[8],
                "daily_basic_raw_payload": r[9],
            }
            for r in cur.fetchall()
        ]
        cur.execute(
            """
            SELECT DISTINCT ON (stock_identity_key)
              stock_identity_key,
              asof_date,
              source_trade_date,
              announcement_date,
              report_period,
              ts_code,
              code,
              exchange,
              roe,
              revenue_yoy,
              profit_yoy,
              total_revenue,
              net_profit,
              net_assets,
              eps,
              bps,
              pe_core,
              total_mv,
              circ_mv,
              source,
              source_version,
              raw_payload,
              quality_status
            FROM stock_financial_metrics_fact
            WHERE source_version <> %s
              AND COALESCE(announcement_date, asof_date) <= %s
            ORDER BY
              stock_identity_key,
              CASE
                WHEN lower(source) LIKE '%%mootdx%%' OR lower(source) LIKE '%%tdx%%' THEN 0
                ELSE 1
              END,
              CASE WHEN quality_status = 'warning' THEN 1 ELSE 0 END,
              COALESCE(announcement_date, asof_date) DESC,
              report_period DESC NULLS LAST
            """,
            (source_version, trade_date),
        )
        latest_financial = {
            str(r[0]): {
                "stock_identity_key": r[0],
                "asof_date": r[1],
                "source_trade_date": r[2],
                "announcement_date": r[3],
                "report_period": r[4],
                "ts_code": r[5],
                "code": r[6],
                "exchange": r[7],
                "roe": r[8],
                "revenue_yoy": r[9],
                "profit_yoy": r[10],
                "total_revenue": r[11],
                "net_profit": r[12],
                "net_assets": r[13],
                "eps": r[14],
                "bps": r[15],
                "pe_core": r[16],
                "total_mv": r[17],
                "circ_mv": r[18],
                "source": r[19],
                "source_version": r[20],
                "raw_payload": r[21],
                "quality_status": r[22],
            }
            for r in cur.fetchall()
        }
    rows: list[dict[str, Any]] = []
    placeholder_count = 0
    for stock in stock_universe:
        candidate = latest_financial.get(str(stock["stock_identity_key"]))
        pe_core = to_decimal(stock.get("pe_ttm")) or to_decimal(stock.get("pe"))
        total_mv = to_decimal(stock.get("total_mv"))
        circ_mv = to_decimal(stock.get("circ_mv"))
        if candidate is None or candidate.get("quality_status") == "warning":
            placeholder_count += 1
            warning = "未找到可用财报"
            quality_status = "warning"
            score = 0
            report_period = None
            announcement_date = None
            metrics = {
                "roe": None,
                "revenue_yoy": None,
                "profit_yoy": None,
                "total_revenue": None,
                "net_profit": None,
                "net_assets": None,
                "eps": None,
                "bps": None,
                "pe_core": None,
                "total_mv": total_mv,
                "circ_mv": circ_mv,
            }
        else:
            warning = None
            quality_status = "passed"
            score = 1
            report_period = candidate.get("report_period")
            announcement_date = candidate.get("announcement_date") or candidate.get("asof_date")
            metrics = {
                "roe": candidate.get("roe"),
                "revenue_yoy": candidate.get("revenue_yoy"),
                "profit_yoy": candidate.get("profit_yoy"),
                "total_revenue": candidate.get("total_revenue"),
                "net_profit": candidate.get("net_profit"),
                "net_assets": candidate.get("net_assets"),
                "eps": candidate.get("eps"),
                "bps": candidate.get("bps"),
                "pe_core": pe_core or candidate.get("pe_core"),
                "total_mv": total_mv or candidate.get("total_mv"),
                "circ_mv": circ_mv or candidate.get("circ_mv"),
            }
        rows.append(
            {
                "stock_identity_key": stock["stock_identity_key"],
                "asof_date": trade_date,
                "source_trade_date": trade_date,
                "announcement_date": announcement_date,
                "report_period": report_period,
                "ts_code": stock["ts_code"],
                "code": stock["code"],
                "exchange": stock["exchange"],
                **metrics,
                "score": score,
                "warning": warning,
                "quality_status": quality_status,
                "source": "financial_asof_snapshot.tdx_mootdx_first_existing+tushare_fallback+daily_basic",
                "source_batch_id": source_batch_id,
                "source_version": source_version,
                "raw_payload": clean_record(
                    json_safe(
                        {
                        "snapshot_rule": "latest announcement_date <= source_trade_date; TDX/Mootdx source rows preferred when available; placeholder when no usable financial report exists",
                        "source_trade_date": trade_date,
                        "selected_financial": candidate,
                        "daily_basic": stock.get("daily_basic_raw_payload"),
                        }
                    )
                ),
            }
        )
    unique_keys = {(row["stock_identity_key"], row["source_trade_date"]) for row in rows}
    gates = [
        Gate("stock_financial_non_empty", bool(rows), ">0", str(len(rows))),
        Gate("stock_financial_universe_alignment", len(rows) == len(stock_universe), f"{len(stock_universe)} stock universe rows", str(len(rows))),
        Gate("stock_financial_identity_coverage", all(row.get("stock_identity_key") for row in rows), "100%", f"{len(rows)}/{len(rows)}"),
        Gate("stock_financial_source_trade_date_coverage", all(row.get("source_trade_date") == trade_date for row in rows), f"all {trade_date}", str(sum(1 for row in rows if row.get("source_trade_date") != trade_date))),
        Gate("stock_financial_unique_key", len(unique_keys) == len(rows), "0 duplicates", str(len(rows) - len(unique_keys))),
        Gate("stock_financial_no_88xxxx", not any(str(row["code"]).startswith("88") for row in rows), "0", str(sum(1 for row in rows if str(row["code"]).startswith("88")))),
        Gate("stock_financial_placeholders", True, "placeholders are allowed with quality_status=warning", str(placeholder_count), severity="P2"),
    ]
    manifest_path = archive_rows(dataset="stock_financial_metrics_fact", rows=rows, source_batch_id=source_batch_id, source_version=source_version, data_root=data_root, partition_key="source_trade_date") if rows else None

    def writer(cur: psycopg.Cursor[Any]) -> None:
        copy_rows(
            cur,
            "stock_financial_metrics_fact",
            ("stock_identity_key", "asof_date", "source_trade_date", "announcement_date", "report_period", "ts_code", "code", "exchange", "roe", "revenue_yoy", "profit_yoy", "total_revenue", "net_profit", "net_assets", "eps", "bps", "pe_core", "total_mv", "circ_mv", "score", "warning", "quality_status", "source", "source_batch_id", "source_version", "raw_payload"),
            ((row["stock_identity_key"], row["asof_date"], row["source_trade_date"], row.get("announcement_date"), row.get("report_period"), row["ts_code"], row["code"], row["exchange"], row.get("roe"), row.get("revenue_yoy"), row.get("profit_yoy"), row.get("total_revenue"), row.get("net_profit"), row.get("net_assets"), row.get("eps"), row.get("bps"), row.get("pe_core"), row.get("total_mv"), row.get("circ_mv"), row.get("score"), row.get("warning"), row.get("quality_status"), row["source"], row["source_batch_id"], row["source_version"], Jsonb(clean_record(row.get("raw_payload") or {}))) for row in rows),
        )

    return run_persisted_batch(
        conn,
        source_batch_id=source_batch_id,
        trade_date=trade_date,
        data_domain="stock",
        data_type="stock_financial",
        source="financial_asof_snapshot.tdx_mootdx_first_existing+tushare_fallback+daily_basic",
        source_version=source_version,
        source_path=None,
        source_params={
            "source_trade_date": trade_date,
            "stock_daily_source_version": stock_daily_source_version,
            "stock_daily_basic_source_version": daily_basic_source_version,
            "selection": "latest announcement_date <= source_trade_date; prefer TDX/Mootdx source rows when present; otherwise Tushare fallback; placeholder if no usable report",
            "placeholder_count": placeholder_count,
        },
        raw_hash=stable_hash(rows),
        row_count=len(rows),
        gates=gates,
        writer=writer,
        activation_scope_key=trade_date,
        archive_manifest_path=manifest_path,
    )


def selected(phase: str, names: Iterable[str]) -> bool:
    return phase == "all" or phase in set(names)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--version", default="v1")
    parser.add_argument("--phase", choices=["common", "identity", "membership", "stock_daily", "stock_daily_basic", "index_daily", "board_daily", "financial", "all"], default="all")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    parser.add_argument("--tdx-root", default=DEFAULT_TDX_ROOT)
    parser.add_argument("--mootdx-offset", type=int, default=200)
    parser.add_argument("--financial-sleep-seconds", type=float, default=0.0)
    parser.add_argument("--allow-closed-day", action="store_true")
    args = parser.parse_args()

    trade_date = require_yyyymmdd(args.trade_date, "trade_date")
    data_root = Path(args.data_root)
    tdx_root = Path(args.tdx_root)
    pro = tushare_client()
    results: list[BatchResult] = []
    with psycopg.connect(args.dsn, connect_timeout=10) as conn:
        conn.autocommit = True
        is_open = True
        if selected(args.phase, {"common"}):
            result, is_open = load_trade_calendar_day(conn, pro, trade_date=trade_date, version=args.version)
            results.append(result)
            print(json.dumps({"completed": result.__dict__, "is_open": is_open}, ensure_ascii=False), flush=True)
        if not is_open and not args.allow_closed_day:
            print(json.dumps({"passed": True, "skipped_market_facts": True, "reason": "trade_date is closed", "results": [result.__dict__ for result in results]}, ensure_ascii=False, indent=2))
            return 0
        if selected(args.phase, {"identity"}):
            for result in (
                load_stock_identity_day(conn, pro, trade_date=trade_date, version=args.version),
                load_index_identity_day(conn, pro, tdx_root, trade_date=trade_date, version=args.version),
                load_board_identity_day(conn, tdx_root, trade_date=trade_date, version=args.version),
            ):
                results.append(result)
                print(json.dumps({"completed": result.__dict__}, ensure_ascii=False), flush=True)
        if selected(args.phase, {"membership"}):
            for result in load_memberships_day(conn, tdx_root, data_root, trade_date=trade_date, version=args.version):
                results.append(result)
                print(json.dumps({"completed": result.__dict__}, ensure_ascii=False), flush=True)
        prepared_mootdx_sub_bundle: dict[str, Any] | None = None
        if args.phase == "all":
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ii.code, ii.exchange, ii.name
                    FROM index_membership_fact im
                    JOIN index_identity ii ON ii.index_identity_key = im.index_identity_key
                    WHERE im.trade_date = %s
                    ORDER BY ii.code
                    """,
                    (trade_date,),
                )
                bundle_indexes = [
                    IndexDailySymbol(code=code, exchange=exchange, name=name)
                    for code, exchange, name in cur.fetchall()
                ]
                cur.execute(
                    """
                    SELECT code, exchange, name
                    FROM index_identity
                    WHERE index_identity_key = ANY(%s)
                    ORDER BY index_identity_key
                    """,
                    (list(FIXED_CORE_INDEX_IDENTITIES),),
                )
                bundle_index_by_key = {
                    (symbol.exchange, symbol.code): symbol
                    for symbol in bundle_indexes
                }
                for code, exchange, name in cur.fetchall():
                    bundle_index_by_key.setdefault(
                        (exchange, code),
                        IndexDailySymbol(code=code, exchange=exchange, name=name),
                    )
                bundle_indexes = sorted(
                    bundle_index_by_key.values(),
                    key=lambda symbol: (symbol.code, symbol.exchange),
                )
                bundle_boards = [
                    BoardDailySymbol(
                        board_code=row["board_code"],
                        board_name=row["board_name"],
                        board_type=row["board_type"],
                    )
                    for row in get_board_identity_rows(cur)
                ]
            prepared_mootdx_sub_bundle = prepare_mootdx_daily_bundle(
                indexes=bundle_indexes,
                boards=bundle_boards,
                trade_date=trade_date,
                mootdx_offset=args.mootdx_offset,
            )
        if selected(args.phase, {"stock_daily"}):
            result = load_stock_daily_day(conn, pro, data_root, trade_date=trade_date, version=args.version)
            results.append(result)
            print(json.dumps({"completed": result.__dict__}, ensure_ascii=False), flush=True)
        if selected(args.phase, {"stock_daily_basic"}):
            result = load_stock_daily_basic_day(conn, pro, data_root, trade_date=trade_date, version=args.version)
            results.append(result)
            print(json.dumps({"completed": result.__dict__}, ensure_ascii=False), flush=True)
        if selected(args.phase, {"index_daily"}):
            result = load_index_daily_day(conn, pro, data_root, trade_date=trade_date, version=args.version, mootdx_offset=args.mootdx_offset, prefetched_raw_rows=(prepared_mootdx_sub_bundle or {}).get("index"), endpoint_provenance=(prepared_mootdx_sub_bundle or {}).get("mootdx_endpoint_provenance"))
            results.append(result)
            print(json.dumps({"completed": result.__dict__}, ensure_ascii=False), flush=True)
        if selected(args.phase, {"board_daily"}):
            result = load_board_daily_day(conn, data_root, trade_date=trade_date, version=args.version, mootdx_offset=args.mootdx_offset, prefetched_raw_rows=(prepared_mootdx_sub_bundle or {}).get("board"), endpoint_provenance=(prepared_mootdx_sub_bundle or {}).get("mootdx_endpoint_provenance"))
            results.append(result)
            print(json.dumps({"completed": result.__dict__}, ensure_ascii=False), flush=True)
        if selected(args.phase, {"financial"}):
            result = load_financial_day(conn, pro, data_root, trade_date=trade_date, version=args.version, sleep_seconds=args.financial_sleep_seconds)
            results.append(result)
            print(json.dumps({"completed": result.__dict__}, ensure_ascii=False), flush=True)

    print(json.dumps({"passed": True, "trade_date": trade_date, "results": [result.__dict__ for result in results]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
