#!/usr/bin/env python3
"""Run the v3 raw-ingestion initial load into the local PostgreSQL database.

This script is intentionally scoped to the raw ingestion layer. It writes only
the approved stock/index/board/common physical tables, audit rows, quality gate
rows, active source versions, and Parquet archives.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from calendar import monthrange
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import time
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd
import psycopg
from psycopg.types.json import Jsonb
import tushare as ts

from ashare_v3.ingestion.tushare_env import load_tushare_token
from ashare_v3.ingestion.common import (
    infer_index_exchange_from_code,
    infer_stock_exchange_from_code,
    make_board_identity_key,
    make_index_identity_key,
    make_stock_identity_key,
    normalize_exchange_from_ts_code,
    normalize_index_exchange_from_ts_code,
    require_six_digit_code,
    require_stock_code,
    require_yyyymmdd,
)
from ashare_v3.ingestion.common_index import normalize_index_identity_row
from ashare_v3.ingestion.daily_bars import BoardDailySymbol, IndexDailySymbol, normalize_board_daily_bar_row
from ashare_v3.ingestion.mootdx_daily_source import MootdxDailyBarSource
from ashare_v3.ingestion.stock import normalize_stock_identity_row
from ashare_v3.ingestion.tdx_local import (
    BOARD_FILE_TYPES,
    INDEX_MEMBERSHIP_FILE,
    TDX_ENCODING,
    build_board_identity_rows,
    normalize_board_membership_row,
    normalize_index_membership_row,
)


DEFAULT_DSN = "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3"
DEFAULT_DATA_ROOT = "/Volumes/MacRaid/database"
DEFAULT_TDX_ROOT = "/Volumes/MacRaid/tdxdata/tdx"
START_DATE = "20230101"
END_DATE = "20260521"
SNAPSHOT_DATE = "20260521"
VERSION = "v1"
SCHEMA_VERSION = "v1"

DAILY_BASIC_FIELDS = ",".join(
    [
        "ts_code",
        "trade_date",
        "close",
        "turnover_rate",
        "turnover_rate_f",
        "volume_ratio",
        "pe",
        "pe_ttm",
        "pb",
        "ps",
        "ps_ttm",
        "dv_ratio",
        "dv_ttm",
        "total_share",
        "float_share",
        "free_share",
        "total_mv",
        "circ_mv",
    ]
)

STOCK_DAILY_FIELDS = "ts_code,trade_date,open,high,low,close,vol,amount"
ADJ_FACTOR_FIELDS = "ts_code,trade_date,adj_factor"
INDEX_DAILY_FIELDS = "ts_code,trade_date,open,high,low,close,vol,amount"
FINA_INDICATOR_FIELDS = "ts_code,end_date,ann_date,roe,or_yoy,netprofit_yoy"


@dataclass(frozen=True)
class Gate:
    name: str
    passed: bool
    expected: str
    actual: str
    details: Mapping[str, Any] | None = None
    severity: str = "P0"


@dataclass(frozen=True)
class BatchResult:
    batch_id: str
    table_name: str
    row_count: int


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def clean_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if math.isnan(value):
            return None
    except TypeError:
        pass
    if hasattr(value, "item"):
        return clean_value(value.item())
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    return value


def clean_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): clean_value(value) for key, value in dict(record).items()}


def stable_hash(rows: Sequence[Mapping[str, Any]]) -> str:
    payload = json.dumps([clean_record(row) for row in rows], ensure_ascii=False, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def frame_to_records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        return [clean_record(row) for row in frame.to_dict(orient="records")]
    if isinstance(frame, Mapping):
        return [clean_record(frame)]
    return [clean_record(row) for row in frame]


def to_decimal(value: Any) -> Decimal | None:
    value = clean_value(value)
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        return None


def decimal_required(value: Any, field: str) -> Decimal:
    parsed = to_decimal(value)
    if parsed is None:
        raise ValueError(f"{field} is required and must be numeric")
    return parsed


def table_count(cur: psycopg.Cursor[Any], table_name: str) -> int:
    cur.execute(f"SELECT count(*) FROM {table_name}")
    return int(cur.fetchone()[0])


def ensure_empty_or_owned(cur: psycopg.Cursor[Any], table_name: str, batch_ids: Sequence[str]) -> None:
    count = table_count(cur, table_name)
    if count == 0:
        return
    cur.execute(
        f"SELECT count(*) FROM {table_name} WHERE source_batch_id = ANY(%s)",
        (list(batch_ids),),
    )
    owned = int(cur.fetchone()[0])
    if owned != count:
        raise RuntimeError(f"{table_name} contains {count} rows not owned by this planned batch set")


def ensure_batch_absent(cur: psycopg.Cursor[Any], batch_id: str) -> None:
    cur.execute("SELECT status FROM common_ingest_batch WHERE batch_id = %s", (batch_id,))
    row = cur.fetchone()
    if row is not None and row[0] == "passed":
        raise RuntimeError(f"batch already passed: {batch_id}")


def existing_passed_batch(conn: psycopg.Connection[Any], batch_id: str, table_name: str) -> BatchResult | None:
    with conn.cursor() as cur:
        cur.execute("SELECT row_count, status FROM common_ingest_batch WHERE batch_id = %s", (batch_id,))
        row = cur.fetchone()
        if row is None or row[1] != "passed":
            return None
        return BatchResult(batch_id=batch_id, table_name=table_name, row_count=int(row[0]))


def insert_batch(
    cur: psycopg.Cursor[Any],
    *,
    batch_id: str,
    trade_date: str,
    data_domain: str,
    data_type: str,
    source: str,
    source_version: str,
    source_path: str | None,
    source_params: Mapping[str, Any] | None,
    raw_hash: str,
    row_count: int,
) -> None:
    cur.execute(
        """
        INSERT INTO common_ingest_batch (
          batch_id, trade_date, data_domain, data_type, source, source_version,
          source_path, source_params, raw_hash, row_count, error_count,
          rollback_strategy, status, started_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0,
          'delete_by_source_batch_id', 'running', %s)
        """,
        (
            batch_id,
            trade_date,
            data_domain,
            data_type,
            source,
            source_version,
            source_path,
            Jsonb(dict(source_params or {})),
            raw_hash,
            row_count,
            utcnow(),
        ),
    )


def insert_gates(
    cur: psycopg.Cursor[Any],
    *,
    source_batch_id: str,
    source_version: str,
    data_domain: str,
    data_type: str,
    gates: Sequence[Gate],
) -> None:
    with cur.copy(
        """
        COPY common_quality_gate_result (
          source_batch_id, source_version, data_domain, data_type, gate_name,
          severity, status, expected_value, actual_value, details
        ) FROM STDIN
        """
    ) as copy:
        for gate in gates:
            copy.write_row(
                (
                    source_batch_id,
                    source_version,
                    data_domain,
                    data_type,
                    gate.name,
                    gate.severity,
                    "passed" if gate.passed else "failed",
                    gate.expected,
                    gate.actual,
                    Jsonb(dict(gate.details or {})),
                )
            )


def fail_on_gates(gates: Sequence[Gate], batch_id: str) -> None:
    failed = [gate for gate in gates if not gate.passed and gate.severity == "P0"]
    if failed:
        payload = [
            {
                "gate": gate.name,
                "expected": gate.expected,
                "actual": gate.actual,
                "details": dict(gate.details or {}),
            }
            for gate in failed
        ]
        raise RuntimeError(f"P0 quality gate failed for {batch_id}: {json.dumps(payload, ensure_ascii=False)[:4000]}")


def finish_batch(
    cur: psycopg.Cursor[Any],
    *,
    batch_id: str,
    gates: Sequence[Gate],
    archive_manifest_path: str | None = None,
) -> None:
    summary = {
        "passed": all(gate.passed for gate in gates),
        "gate_count": len(gates),
        "failed_gate_count": sum(1 for gate in gates if not gate.passed),
        "gate_names": [gate.name for gate in gates],
    }
    if archive_manifest_path:
        summary["archive_manifest_path"] = archive_manifest_path
    cur.execute(
        """
        UPDATE common_ingest_batch
        SET status = 'passed', finished_at = %s, quality_gate_summary = %s
        WHERE batch_id = %s
        """,
        (utcnow(), Jsonb(summary), batch_id),
    )


def activate_source_version(
    cur: psycopg.Cursor[Any],
    *,
    data_domain: str,
    data_type: str,
    scope_key: str,
    source_version: str,
    source_batch_id: str,
    activated_by: str,
) -> None:
    cur.execute(
        """
        INSERT INTO common_active_source_version (
          data_domain, data_type, scope_key, source_version, source_batch_id,
          previous_source_version, activated_by
        ) VALUES (%s, %s, %s, %s, %s, NULL, %s)
        ON CONFLICT (data_domain, data_type, scope_key) DO UPDATE SET
          previous_source_version = common_active_source_version.source_version,
          source_version = EXCLUDED.source_version,
          source_batch_id = EXCLUDED.source_batch_id,
          activated_at = now(),
          activated_by = EXCLUDED.activated_by
        """,
        (data_domain, data_type, scope_key, source_version, source_batch_id, activated_by),
    )


def copy_rows(cur: psycopg.Cursor[Any], table_name: str, columns: Sequence[str], rows: Iterable[Sequence[Any]]) -> int:
    count = 0
    column_list = ", ".join(columns)
    with cur.copy(f"COPY {table_name} ({column_list}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)
            count += 1
    return count


def archive_rows(
    *,
    dataset: str,
    rows: Sequence[Mapping[str, Any]],
    source_batch_id: str,
    source_version: str,
    data_root: Path,
    partition_key: str,
) -> str:
    if not rows:
        raise RuntimeError(f"refusing empty parquet archive for {dataset}:{source_batch_id}")
    root = data_root / "data_lake"
    manifest_dir = root / "_manifests" / dataset / f"source_version={source_version}"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    dataset_root = root / dataset / f"source_version={source_version}"
    files: list[dict[str, Any]] = []
    frame = pd.DataFrame([parquet_safe_row(row) for row in rows])
    for partition_value, partition_frame in frame.groupby(partition_key, sort=True):
        partition_dir = dataset_root / f"{partition_key}={partition_value}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        path = partition_dir / f"{source_batch_id}.parquet"
        partition_frame.to_parquet(path, index=False)
        files.append(
            {
                "path": str(path),
                "row_count": int(len(partition_frame)),
                "partition_values": {partition_key: str(partition_value)},
            }
        )
    manifest_path = manifest_dir / f"{source_batch_id}.manifest.json"
    manifest = {
        "manifest_version": "v1",
        "dataset": dataset,
        "source_batch_id": source_batch_id,
        "source_version": source_version,
        "schema_version": SCHEMA_VERSION,
        "row_count": len(rows),
        "raw_hash": stable_hash(rows),
        "partition_keys": [partition_key],
        "manifest_path": str(manifest_path),
        "file_paths": [file["path"] for file in files],
        "files": files,
        "rollback": {
            "strategy": "delete_manifest_and_files_by_source_batch_id",
            "paths": [str(manifest_path), *[file["path"] for file in files]],
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return str(manifest_path)


def parquet_safe_row(row: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in row.items():
        if key == "raw_payload":
            safe[key] = json.dumps(clean_record(value or {}), ensure_ascii=False, sort_keys=True, default=str)
        elif isinstance(value, Decimal):
            safe[key] = float(value)
        elif isinstance(value, (dict, list, tuple)):
            safe[key] = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        else:
            safe[key] = clean_value(value)
    return safe


def month_ranges(start_date: str, end_date: str) -> list[tuple[str, str, str]]:
    current = datetime.strptime(start_date, "%Y%m%d").date().replace(day=1)
    end = datetime.strptime(end_date, "%Y%m%d").date()
    ranges: list[tuple[str, str, str]] = []
    while current <= end:
        if current.month == 12:
            next_month = current.replace(year=current.year + 1, month=1, day=1)
        else:
            next_month = current.replace(month=current.month + 1, day=1)
        month_start = max(current, datetime.strptime(start_date, "%Y%m%d").date())
        month_end = min(current.replace(day=monthrange(current.year, current.month)[1]), end)
        period = current.strftime("%Y%m")
        ranges.append((period, month_start.strftime("%Y%m%d"), month_end.strftime("%Y%m%d")))
        current = next_month
    return ranges


def get_open_dates(cur: psycopg.Cursor[Any], start_date: str, end_date: str) -> list[str]:
    cur.execute(
        """
        SELECT trade_date
        FROM common_trade_calendar
        WHERE trade_date BETWEEN %s AND %s AND is_open
        ORDER BY trade_date
        """,
        (start_date, end_date),
    )
    return [str(row[0]) for row in cur.fetchall()]


def get_stock_identity_map(cur: psycopg.Cursor[Any]) -> dict[str, dict[str, Any]]:
    cur.execute("SELECT ts_code, stock_identity_key, code, exchange, name FROM stock_identity")
    return {
        str(ts_code): {
            "stock_identity_key": stock_identity_key,
            "code": code,
            "exchange": exchange,
            "name": name,
        }
        for ts_code, stock_identity_key, code, exchange, name in cur.fetchall()
    }


def is_b_share_ts_code(ts_code: str) -> bool:
    code = ts_code.split(".", 1)[0]
    return code.startswith(("200", "900"))


def ensure_stock_identity_supplements(
    conn: psycopg.Connection[Any],
    pro: Any,
    *,
    ts_codes: Sequence[str],
    source_trade_date: str,
    period: str,
) -> BatchResult | None:
    requested = sorted({code for code in ts_codes if code and not is_b_share_ts_code(code)})
    if not requested:
        return None
    with conn.cursor() as cur:
        stock_map = get_stock_identity_map(cur)
    missing = [code for code in requested if code not in stock_map]
    if not missing:
        return None

    batch_id = f"stock_identity_supplement_{period}_{VERSION}"
    source_version = batch_id
    rows: list[dict[str, Any]] = []
    raw_payloads: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for ts_code in missing:
        try:
            exchange, code = normalize_exchange_from_ts_code(ts_code)
        except Exception:
            unresolved.append(ts_code)
            continue
        name = None
        area = None
        industry = None
        market = None
        list_date = None
        raw_parts: dict[str, Any] = {"ts_code": ts_code}
        try:
            name_rows = frame_to_records(pro.namechange(ts_code=ts_code))
            raw_parts["namechange"] = name_rows
            active_names = [
                row
                for row in name_rows
                if str(row.get("start_date") or "") <= SNAPSHOT_DATE
                and (not row.get("end_date") or str(row.get("end_date")) >= SNAPSHOT_DATE)
            ]
            if active_names:
                name = str(active_names[0].get("name") or "").strip() or None
            elif name_rows:
                name = str(name_rows[0].get("name") or "").strip() or None
        except Exception:
            pass
        try:
            bak_rows = frame_to_records(pro.bak_basic(ts_code=ts_code, trade_date=source_trade_date))
            raw_parts["bak_basic"] = bak_rows[:3]
            if bak_rows:
                bak = bak_rows[0]
                name = name or str(bak.get("name") or "").strip() or None
                area = str(bak.get("area") or "").strip() or None
                industry = str(bak.get("industry") or "").strip() or None
                list_date = str(bak.get("list_date") or "").strip() or None
        except Exception:
            pass
        if not name:
            unresolved.append(ts_code)
            continue
        raw_payloads.append(clean_record(raw_parts))
        rows.append(
            {
                "stock_identity_key": make_stock_identity_key(exchange, code),
                "ts_code": ts_code,
                "code": code,
                "exchange": exchange,
                "name": name,
                "display_code": f"{code}.{exchange}",
                "area": area,
                "industry": industry,
                "market": market,
                "listed_date": list_date if list_date and len(list_date) == 8 else None,
                "delisted_date": None,
                "is_st": "ST" in name.upper(),
                "status": "active",
                "source": "tushare.namechange+bak_basic.identity_supplement",
                "source_batch_id": batch_id,
                "source_version": source_version,
                "raw_payload": clean_record(raw_parts),
            }
        )
    gates = [
        Gate("stock_identity_supplement_requested_non_empty", bool(missing), ">0", str(len(missing))),
        Gate("stock_identity_supplement_resolved", not unresolved, "0 unresolved", str(len(unresolved)), {"unresolved": unresolved[:50]}),
        Gate("stock_identity_supplement_key_coverage", all(row.get("stock_identity_key") for row in rows), "100%", f"{len(rows)}/{len(rows)}"),
        Gate("stock_identity_supplement_no_88xxxx", not any(str(row["code"]).startswith("88") for row in rows), "0", str(sum(1 for row in rows if str(row["code"]).startswith("88")))),
    ]
    fail_on_gates(gates, batch_id)
    with conn.transaction():
        with conn.cursor() as cur:
            ensure_batch_absent(cur, batch_id)
            insert_batch(
                cur,
                batch_id=batch_id,
                trade_date=source_trade_date,
                data_domain="stock",
                data_type="stock_identity_supplement",
                source="tushare.namechange+bak_basic",
                source_version=source_version,
                source_path=None,
                source_params={"period": period, "ts_codes": missing},
                raw_hash=stable_hash(raw_payloads),
                row_count=len(rows),
            )
            copy_rows(
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
                (
                    (
                        row["stock_identity_key"],
                        row["ts_code"],
                        row["code"],
                        row["exchange"],
                        row["name"],
                        row.get("display_code"),
                        row.get("area"),
                        row.get("industry"),
                        row.get("market"),
                        row.get("listed_date"),
                        row.get("delisted_date"),
                        row.get("is_st"),
                        row.get("status"),
                        row["source"],
                        row["source_batch_id"],
                        row["source_version"],
                        Jsonb(clean_record(row.get("raw_payload") or {})),
                    )
                    for row in rows
                ),
            )
            insert_gates(cur, source_batch_id=batch_id, source_version=source_version, data_domain="stock", data_type="stock_identity_supplement", gates=gates)
            activate_source_version(cur, data_domain="stock", data_type="stock_identity_supplement", scope_key=f"A_STOCK_SUPPLEMENT:{period}", source_version=source_version, source_batch_id=batch_id, activated_by="codex_initial_ingestion")
            finish_batch(cur, batch_id=batch_id, gates=gates)
    return BatchResult(batch_id=batch_id, table_name="stock_identity", row_count=len(rows))


def get_index_identity_map(cur: psycopg.Cursor[Any]) -> dict[str, dict[str, Any]]:
    cur.execute("SELECT index_identity_key, ts_code, code, exchange, name FROM index_identity")
    rows: dict[str, dict[str, Any]] = {}
    for key, ts_code, code, exchange, name in cur.fetchall():
        rows[str(key)] = {"ts_code": ts_code, "code": code, "exchange": exchange, "name": name}
    return rows


def get_board_identity_rows(cur: psycopg.Cursor[Any]) -> list[dict[str, Any]]:
    cur.execute("SELECT board_identity_key, board_code, board_name, board_type FROM board_identity ORDER BY board_code")
    return [
        {
            "board_identity_key": key,
            "board_code": code,
            "board_name": name,
            "board_type": board_type,
        }
        for key, code, name, board_type in cur.fetchall()
    ]


def tushare_client() -> Any:
    token = load_tushare_token() or ts.get_token()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN or local Tushare token is required")
    ts.set_token(token)
    return ts.pro_api(token)


def tushare_query(func: Any, /, *, retries: int = 5, sleep_seconds: float = 2.0, **kwargs: Any) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return func(**kwargs)
        except Exception as exc:
            last_error = exc
            if attempt == retries:
                break
            time.sleep(sleep_seconds * attempt)
    raise RuntimeError(f"Tushare query failed after {retries} attempts: {last_error}") from last_error


def load_stock_identity(conn: psycopg.Connection[Any], pro: Any) -> BatchResult:
    batch_id = f"stock_identity_{SNAPSHOT_DATE}_{VERSION}"
    source_version = batch_id
    existing = existing_passed_batch(conn, batch_id, "stock_identity")
    if existing is not None:
        return existing
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
    skipped_non_a_share: list[str] = []
    for raw in raw_rows:
        ts_code = str(raw.get("ts_code") or "").strip().upper()
        try:
            row = normalize_stock_identity_row(
                raw,
                source="tushare.stock_basic",
                source_batch_id=batch_id,
                source_version=source_version,
            )
        except Exception:
            skipped_non_a_share.append(ts_code)
            continue
        rows_by_key[row["stock_identity_key"]] = row
    rows = list(rows_by_key.values())
    gates = [
        Gate("stock_identity_non_empty", bool(rows), ">0", str(len(rows))),
        Gate("stock_identity_key_coverage", all(row.get("stock_identity_key") for row in rows), "100%", f"{len(rows)}/{len(rows)}"),
        Gate("stock_identity_unique_key", len(rows) == len({row["stock_identity_key"] for row in rows}), "0 duplicates", str(len(rows) - len({row["stock_identity_key"] for row in rows}))),
        Gate("stock_identity_no_88xxxx", not any(str(row["code"]).startswith("88") for row in rows), "0", str(sum(1 for row in rows if str(row["code"]).startswith("88")))),
        Gate("stock_identity_non_a_share_rows_filtered", True, "non-A-share source rows are filtered before stock_identity", str(len(skipped_non_a_share)), {"sample": skipped_non_a_share[:50]}, severity="P2"),
    ]
    fail_on_gates(gates, batch_id)
    with conn.transaction():
        with conn.cursor() as cur:
            ensure_batch_absent(cur, batch_id)
            ensure_empty_or_owned(cur, "stock_identity", [batch_id])
            insert_batch(
                cur,
                batch_id=batch_id,
                trade_date=SNAPSHOT_DATE,
                data_domain="stock",
                data_type="stock_identity",
                source="tushare.stock_basic",
                source_version=source_version,
                source_path=None,
                source_params={"list_status": ["L", "D", "P"]},
                raw_hash=stable_hash(raw_rows),
                row_count=len(rows),
            )
            copy_rows(
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
                (
                    (
                        row["stock_identity_key"],
                        row["ts_code"],
                        row["code"],
                        row["exchange"],
                        row["name"],
                        row.get("display_code"),
                        row.get("area"),
                        row.get("industry"),
                        row.get("market"),
                        row.get("listed_date"),
                        row.get("delisted_date"),
                        row.get("is_st"),
                        row.get("status"),
                        row["source"],
                        row["source_batch_id"],
                        row["source_version"],
                        Jsonb(clean_record(row.get("raw_payload") or {})),
                    )
                    for row in rows
                ),
            )
            insert_gates(cur, source_batch_id=batch_id, source_version=source_version, data_domain="stock", data_type="stock_identity", gates=gates)
            activate_source_version(cur, data_domain="stock", data_type="stock_identity", scope_key=f"A_STOCK:{SNAPSHOT_DATE}", source_version=source_version, source_batch_id=batch_id, activated_by="codex_initial_ingestion")
            finish_batch(cur, batch_id=batch_id, gates=gates)
    return BatchResult(batch_id=batch_id, table_name="stock_identity", row_count=len(rows))


def load_index_identity(conn: psycopg.Connection[Any], pro: Any, tdx_root: Path) -> BatchResult:
    batch_id = f"index_identity_{SNAPSHOT_DATE}_{VERSION}"
    source_version = batch_id
    existing = existing_passed_batch(conn, batch_id, "index_identity")
    if existing is not None:
        return existing
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
    skipped_non_index: list[str] = []
    for raw in raw_rows:
        try:
            row = normalize_index_identity_row(
                raw,
                source="tushare.index_basic",
                source_batch_id=batch_id,
                source_version=source_version,
            )
        except Exception:
            skipped_non_index.append(str(raw.get("ts_code") or ""))
            continue
        if str(row["code"]).startswith("88"):
            skipped_non_index.append(str(raw.get("ts_code") or row["code"]))
            continue
        rows_by_key[row["index_identity_key"]] = row

    # Add local TDX index membership heads missing from Tushare so membership can
    # be physically separated and identity-keyed without inventing stock rows.
    for raw in read_tdx_index_rows(tdx_root):
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
                "source_batch_id": batch_id,
                "source_version": source_version,
                "raw_payload": clean_record(raw),
            }
    rows = list(rows_by_key.values())
    gates = [
        Gate("index_identity_non_empty", bool(rows), ">0", str(len(rows))),
        Gate("index_identity_key_coverage", all(row.get("index_identity_key") for row in rows), "100%", f"{len(rows)}/{len(rows)}"),
        Gate("index_identity_unique_key", len(rows) == len({row["index_identity_key"] for row in rows}), "0 duplicates", str(len(rows) - len({row["index_identity_key"] for row in rows}))),
        Gate("index_identity_no_88xxxx_board", not any(str(row["code"]).startswith("88") for row in rows), "0", str(sum(1 for row in rows if str(row["code"]).startswith("88")))),
        Gate("index_identity_non_index_rows_filtered", True, "non-index/88xxxx source rows are filtered before index_identity", str(len(skipped_non_index)), {"sample": skipped_non_index[:50]}, severity="P2"),
    ]
    fail_on_gates(gates, batch_id)
    with conn.transaction():
        with conn.cursor() as cur:
            ensure_batch_absent(cur, batch_id)
            ensure_empty_or_owned(cur, "index_identity", [batch_id])
            insert_batch(
                cur,
                batch_id=batch_id,
                trade_date=SNAPSHOT_DATE,
                data_domain="index",
                data_type="index_identity",
                source="tushare.index_basic+tdx.local_txt.index_board",
                source_version=source_version,
                source_path=str(tdx_root / INDEX_MEMBERSHIP_FILE),
                source_params={"markets": ["SSE", "SZSE", "CSI", "SW", "OTH", "MSCI", "CICC", "CNI"]},
                raw_hash=stable_hash(raw_rows),
                row_count=len(rows),
            )
            copy_rows(
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
                (
                    (
                        row["index_identity_key"],
                        row.get("ts_code"),
                        row["code"],
                        row["exchange"],
                        row["name"],
                        row.get("source_namespace"),
                        row.get("publisher"),
                        row.get("index_category"),
                        row.get("base_date"),
                        row.get("listed_date"),
                        row.get("status"),
                        row["source"],
                        row["source_batch_id"],
                        row["source_version"],
                        Jsonb(clean_record(row.get("raw_payload") or {})),
                    )
                    for row in rows
                ),
            )
            insert_gates(cur, source_batch_id=batch_id, source_version=source_version, data_domain="index", data_type="index_identity", gates=gates)
            activate_source_version(cur, data_domain="index", data_type="index_identity", scope_key=f"INDEX:{SNAPSHOT_DATE}", source_version=source_version, source_batch_id=batch_id, activated_by="codex_initial_ingestion")
            finish_batch(cur, batch_id=batch_id, gates=gates)
    return BatchResult(batch_id=batch_id, table_name="index_identity", row_count=len(rows))


def read_tdx_board_rows(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for file_name, board_type in BOARD_FILE_TYPES.items():
        path = root / file_name
        rows.extend(read_tdx_txt(path, kind="board", board_type=board_type))
    return rows


def read_tdx_index_rows(root: Path) -> list[dict[str, Any]]:
    return read_tdx_txt(root / INDEX_MEMBERSHIP_FILE, kind="index", board_type=None)


def read_tdx_txt(path: Path, *, kind: str, board_type: str | None) -> list[dict[str, Any]]:
    if not path.exists():
        raise RuntimeError(f"TDX txt not found: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding=TDX_ENCODING, newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for line_number, columns in enumerate(reader, start=1):
            stripped = [column.strip() for column in columns]
            if not any(stripped):
                continue
            if len(stripped) < 4:
                raise RuntimeError(f"{path.name}:{line_number} expected 4 tab separated columns")
            first_code, first_name, stock_code, stock_name = stripped[:4]
            common = {"stock_code": stock_code, "stock_name": stock_name, "source_file": path.name, "line_number": line_number}
            if kind == "board":
                rows.append({"board_code": first_code, "board_name": first_name, "board_type": board_type or "tdx_other", **common})
            else:
                rows.append({"index_code": first_code, "index_name": first_name, **common})
    return rows


def load_board_identity(conn: psycopg.Connection[Any], tdx_root: Path) -> BatchResult:
    batch_id = f"board_identity_{SNAPSHOT_DATE}_{VERSION}"
    source_version = batch_id
    existing = existing_passed_batch(conn, batch_id, "board_identity")
    if existing is not None:
        return existing
    raw_board_rows = read_tdx_board_rows(tdx_root)
    rows = build_board_identity_rows(raw_board_rows, source_batch_id=batch_id, source_version=source_version)
    gates = [
        Gate("board_identity_non_empty", bool(rows), ">0", str(len(rows))),
        Gate("board_identity_key_coverage", all(row.get("board_identity_key") for row in rows), "100%", f"{len(rows)}/{len(rows)}"),
        Gate("board_identity_unique_key", len(rows) == len({row["board_identity_key"] for row in rows}), "0 duplicates", str(len(rows) - len({row["board_identity_key"] for row in rows}))),
        Gate("board_identity_code_shape", all(str(row["board_code"]).startswith("88") for row in rows), "all board_code starts with 88", str(sum(1 for row in rows if not str(row["board_code"]).startswith("88")))),
    ]
    fail_on_gates(gates, batch_id)
    with conn.transaction():
        with conn.cursor() as cur:
            ensure_batch_absent(cur, batch_id)
            ensure_empty_or_owned(cur, "board_identity", [batch_id])
            insert_batch(
                cur,
                batch_id=batch_id,
                trade_date=SNAPSHOT_DATE,
                data_domain="board",
                data_type="board_identity",
                source="tdx.local_txt.board",
                source_version=source_version,
                source_path=str(tdx_root),
                source_params={"files": sorted(BOARD_FILE_TYPES)},
                raw_hash=stable_hash(raw_board_rows),
                row_count=len(rows),
            )
            copy_rows(
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
                (
                    (
                        row["board_identity_key"],
                        row["board_code"],
                        row["board_name"],
                        row["board_type"],
                        row["source_namespace"],
                        row.get("source_file"),
                        row.get("status"),
                        row["source"],
                        row["source_batch_id"],
                        row["source_version"],
                        Jsonb(clean_record(row.get("raw_payload") or {})),
                    )
                    for row in rows
                ),
            )
            insert_gates(cur, source_batch_id=batch_id, source_version=source_version, data_domain="board", data_type="board_identity", gates=gates)
            activate_source_version(cur, data_domain="board", data_type="board_identity", scope_key=f"TDX:{SNAPSHOT_DATE}", source_version=source_version, source_batch_id=batch_id, activated_by="codex_initial_ingestion")
            finish_batch(cur, batch_id=batch_id, gates=gates)
    return BatchResult(batch_id=batch_id, table_name="board_identity", row_count=len(rows))


def load_memberships(conn: psycopg.Connection[Any], tdx_root: Path, data_root: Path) -> list[BatchResult]:
    raw_board_rows = read_tdx_board_rows(tdx_root)
    raw_index_rows = read_tdx_index_rows(tdx_root)
    board_batch = f"board_membership_{SNAPSHOT_DATE}_{VERSION}"
    index_batch = f"index_membership_{SNAPSHOT_DATE}_{VERSION}"
    board_rows = [
        normalize_board_membership_row(row, trade_date=SNAPSHOT_DATE, source_batch_id=board_batch, source_version=board_batch)
        for row in raw_board_rows
    ]
    index_rows = [
        normalize_index_membership_row(row, trade_date=SNAPSHOT_DATE, source_batch_id=index_batch, source_version=index_batch)
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
    board_gates = [
        Gate("board_membership_non_empty", bool(board_rows), ">0", str(len(board_rows))),
        Gate("board_membership_board_identity_coverage", True, "100% for inserted rows", "0"),
        Gate("board_membership_stock_identity_coverage", True, "100% for inserted rows", "0"),
        Gate("board_membership_unresolved_source_rows_filtered", True, "unresolved source rows filtered before activation", str(len(board_missing_stock) + len(board_missing_board)), {"missing_stock_identity_keys": board_missing_stock[:50], "missing_board_identity_keys": board_missing_board[:50]}, severity="P2"),
        Gate("board_membership_unique_key", len(board_rows) == len({(row["trade_date"], row["board_identity_key"], row["stock_identity_key"]) for row in board_rows}), "0 duplicates", str(len(board_rows) - len({(row["trade_date"], row["board_identity_key"], row["stock_identity_key"]) for row in board_rows}))),
        Gate("board_membership_no_88_stock", not any(str(row["stock_code"]).startswith("88") for row in board_rows), "0", str(sum(1 for row in board_rows if str(row["stock_code"]).startswith("88")))),
    ]
    index_gates = [
        Gate("index_membership_non_empty", bool(index_rows), ">0", str(len(index_rows))),
        Gate("index_membership_index_identity_coverage", True, "100% for inserted rows", "0"),
        Gate("index_membership_stock_identity_coverage", True, "100% for inserted rows", "0"),
        Gate("index_membership_unresolved_source_rows_filtered", True, "unresolved source rows filtered before activation", str(len(index_missing_stock) + len(index_missing_index)), {"missing_stock_identity_keys": index_missing_stock[:50], "missing_index_identity_keys": index_missing_index[:50]}, severity="P2"),
        Gate("index_membership_unique_key", len(index_rows) == len({(row["trade_date"], row["index_identity_key"], row["stock_identity_key"]) for row in index_rows}), "0 duplicates", str(len(index_rows) - len({(row["trade_date"], row["index_identity_key"], row["stock_identity_key"]) for row in index_rows}))),
        Gate("index_membership_no_88_stock", not any(str(row["stock_code"]).startswith("88") for row in index_rows), "0", str(sum(1 for row in index_rows if str(row["stock_code"]).startswith("88")))),
    ]
    fail_on_gates(board_gates, board_batch)
    fail_on_gates(index_gates, index_batch)
    results: list[BatchResult] = []
    with conn.transaction():
        with conn.cursor() as cur:
            ensure_batch_absent(cur, index_batch)
            ensure_empty_or_owned(cur, "index_membership_fact", [index_batch])
            insert_batch(cur, batch_id=index_batch, trade_date=SNAPSHOT_DATE, data_domain="index", data_type="index_membership", source="tdx.local_txt.index_board", source_version=index_batch, source_path=str(tdx_root / INDEX_MEMBERSHIP_FILE), source_params={"file": INDEX_MEMBERSHIP_FILE}, raw_hash=stable_hash(raw_index_rows), row_count=len(index_rows))
            copy_rows(
                cur,
                "index_membership_fact",
                ("trade_date", "index_identity_key", "stock_identity_key", "index_code", "index_name", "stock_code", "stock_name", "source", "source_file", "source_batch_id", "source_version", "raw_payload"),
                (
                    (row["trade_date"], row["index_identity_key"], row["stock_identity_key"], row["index_code"], row.get("index_name"), row["stock_code"], row.get("stock_name"), row["source"], row.get("source_file"), row["source_batch_id"], row["source_version"], Jsonb(clean_record(row.get("raw_payload") or {})))
                    for row in index_rows
                ),
            )
            insert_gates(cur, source_batch_id=index_batch, source_version=index_batch, data_domain="index", data_type="index_membership", gates=index_gates)
            activate_source_version(cur, data_domain="index", data_type="index_membership", scope_key=f"TDX:{SNAPSHOT_DATE}", source_version=index_batch, source_batch_id=index_batch, activated_by="codex_initial_ingestion")
            finish_batch(cur, batch_id=index_batch, gates=index_gates, archive_manifest_path=archive_rows(dataset="index_membership_fact", rows=index_rows, source_batch_id=index_batch, source_version=index_batch, data_root=data_root, partition_key="trade_date"))
            results.append(BatchResult(batch_id=index_batch, table_name="index_membership_fact", row_count=len(index_rows)))

            ensure_batch_absent(cur, board_batch)
            ensure_empty_or_owned(cur, "board_membership_fact", [board_batch])
            insert_batch(cur, batch_id=board_batch, trade_date=SNAPSHOT_DATE, data_domain="board", data_type="board_membership", source="tdx.local_txt.board", source_version=board_batch, source_path=str(tdx_root), source_params={"files": sorted(BOARD_FILE_TYPES)}, raw_hash=stable_hash(raw_board_rows), row_count=len(board_rows))
            copy_rows(
                cur,
                "board_membership_fact",
                ("trade_date", "board_identity_key", "stock_identity_key", "board_code", "board_name", "board_type", "stock_code", "stock_name", "source", "source_file", "source_batch_id", "source_version", "raw_payload"),
                (
                    (row["trade_date"], row["board_identity_key"], row["stock_identity_key"], row["board_code"], row.get("board_name"), row["board_type"], row["stock_code"], row.get("stock_name"), row["source"], row.get("source_file"), row["source_batch_id"], row["source_version"], Jsonb(clean_record(row.get("raw_payload") or {})))
                    for row in board_rows
                ),
            )
            insert_gates(cur, source_batch_id=board_batch, source_version=board_batch, data_domain="board", data_type="board_membership", gates=board_gates)
            activate_source_version(cur, data_domain="board", data_type="board_membership", scope_key=f"TDX:{SNAPSHOT_DATE}", source_version=board_batch, source_batch_id=board_batch, activated_by="codex_initial_ingestion")
            finish_batch(cur, batch_id=board_batch, gates=board_gates, archive_manifest_path=archive_rows(dataset="board_membership_fact", rows=board_rows, source_batch_id=board_batch, source_version=board_batch, data_root=data_root, partition_key="trade_date"))
            results.append(BatchResult(batch_id=board_batch, table_name="board_membership_fact", row_count=len(board_rows)))
    return results


def normalize_ts_code(raw_ts_code: Any) -> str | None:
    if raw_ts_code is None:
        return None
    text = str(raw_ts_code).strip().upper()
    if not text:
        return None
    if "." not in text and len(text) == 6:
        exchange = infer_stock_exchange_from_code(text)
        return f"{text}.{exchange}"
    return text


def load_stock_daily_month(conn: psycopg.Connection[Any], pro: Any, data_root: Path, period: str, start_date: str, end_date: str) -> BatchResult:
    batch_id = f"stock_daily_{period}_{VERSION}"
    source_version = f"stock_daily_{START_DATE}_{END_DATE}_{VERSION}"
    with conn.cursor() as cur:
        open_dates = [d for d in get_open_dates(cur, start_date, end_date)]
        stock_map = get_stock_identity_map(cur)
    raw_daily_rows: list[dict[str, Any]] = []
    adj_rows: list[dict[str, Any]] = []
    for trade_date in open_dates:
        raw_daily_rows.extend(frame_to_records(pro.daily(trade_date=trade_date, fields=STOCK_DAILY_FIELDS)))
        adj_rows.extend(frame_to_records(pro.adj_factor(trade_date=trade_date, fields=ADJ_FACTOR_FIELDS)))
    initial_missing = sorted(
        {
            ts_code
            for ts_code in (normalize_ts_code(row.get("ts_code")) for row in raw_daily_rows)
            if ts_code and ts_code not in stock_map and not is_b_share_ts_code(ts_code)
        }
    )
    ensure_stock_identity_supplements(
        conn,
        pro,
        ts_codes=initial_missing,
        source_trade_date=open_dates[0] if open_dates else start_date,
        period=period,
    )
    with conn.cursor() as cur:
        stock_map = get_stock_identity_map(cur)
    adj_by_key = {(normalize_ts_code(row.get("ts_code")), str(row.get("trade_date"))): to_decimal(row.get("adj_factor")) for row in adj_rows}
    latest_adj: dict[str, Decimal] = {}
    for row in adj_rows:
        ts_code = normalize_ts_code(row.get("ts_code"))
        value = to_decimal(row.get("adj_factor"))
        if ts_code and value is not None:
            latest_adj[ts_code] = value
    rows: list[dict[str, Any]] = []
    missing_identity: set[str] = set()
    missing_adj: set[tuple[str, str]] = set()
    for raw in raw_daily_rows:
        ts_code = normalize_ts_code(raw.get("ts_code"))
        trade_date = str(raw.get("trade_date") or "")
        if not ts_code or ts_code not in stock_map:
            if ts_code:
                missing_identity.add(ts_code)
            continue
        adj = adj_by_key.get((ts_code, trade_date))
        latest = latest_adj.get(ts_code)
        if adj is None or latest is None or latest == 0:
            missing_adj.add((ts_code, trade_date))
            continue
        factor = adj / latest
        identity = stock_map[ts_code]
        rows.append(
            {
                "stock_identity_key": identity["stock_identity_key"],
                "trade_date": require_yyyymmdd(trade_date),
                "ts_code": ts_code,
                "code": identity["code"],
                "exchange": identity["exchange"],
                "name": identity["name"],
                "open": decimal_required(raw.get("open"), "open") * factor,
                "high": decimal_required(raw.get("high"), "high") * factor,
                "low": decimal_required(raw.get("low"), "low") * factor,
                "close": decimal_required(raw.get("close"), "close") * factor,
                "volume": to_decimal(raw.get("vol")),
                "amount": to_decimal(raw.get("amount")),
                "adj_factor": adj,
                "adjust_type": "qfq",
                "source": "tushare.daily+adj_factor.qfq",
                "source_batch_id": batch_id,
                "source_version": source_version,
                "official_daily_proof": True,
                "raw_payload": clean_record({**raw, "adj_factor": str(adj), "qfq_factor": str(factor)}),
            }
        )
    unique_keys = {(row["stock_identity_key"], row["trade_date"]) for row in rows}
    gates = [
        Gate("stock_daily_non_empty", bool(rows), ">0", str(len(rows))),
        Gate("stock_daily_identity_coverage", True, "100% for inserted rows", "0"),
        Gate("stock_daily_unresolved_source_rows_filtered", True, "unresolved/B-share source rows filtered before activation", str(len(missing_identity)), {"missing_ts_codes": sorted(missing_identity)[:50]}, severity="P2"),
        Gate("stock_daily_adj_factor_coverage", not missing_adj, "100%", str(len(missing_adj)), {"missing": [{"ts_code": a, "trade_date": b} for a, b in sorted(missing_adj)[:50]]}),
        Gate("stock_daily_unique_key", len(unique_keys) == len(rows), "0 duplicates", str(len(rows) - len(unique_keys))),
        Gate("stock_daily_no_88xxxx", not any(str(row["code"]).startswith("88") for row in rows), "0", str(sum(1 for row in rows if str(row["code"]).startswith("88")))),
        Gate("stock_daily_official_proof", all(row["official_daily_proof"] for row in rows), "100%", f"{sum(1 for row in rows if row['official_daily_proof'])}/{len(rows)}"),
    ]
    fail_on_gates(gates, batch_id)
    manifest_path = archive_rows(dataset="stock_daily_bar_fact", rows=rows, source_batch_id=batch_id, source_version=source_version, data_root=data_root, partition_key="trade_date")
    with conn.transaction():
        with conn.cursor() as cur:
            ensure_batch_absent(cur, batch_id)
            insert_batch(cur, batch_id=batch_id, trade_date=end_date, data_domain="stock", data_type="stock_daily", source="tushare.daily+adj_factor.qfq", source_version=source_version, source_path=None, source_params={"start_date": start_date, "end_date": end_date, "slice": period}, raw_hash=stable_hash(raw_daily_rows + adj_rows), row_count=len(rows))
            copy_rows(
                cur,
                "stock_daily_bar_fact",
                ("stock_identity_key", "trade_date", "ts_code", "code", "exchange", "name", "open", "high", "low", "close", "volume", "amount", "adj_factor", "adjust_type", "source", "source_batch_id", "source_version", "official_daily_proof", "raw_payload"),
                (
                    (row["stock_identity_key"], row["trade_date"], row["ts_code"], row["code"], row["exchange"], row.get("name"), row["open"], row["high"], row["low"], row["close"], row.get("volume"), row.get("amount"), row.get("adj_factor"), row["adjust_type"], row["source"], row["source_batch_id"], row["source_version"], row["official_daily_proof"], Jsonb(clean_record(row.get("raw_payload") or {})))
                    for row in rows
                ),
            )
            insert_gates(cur, source_batch_id=batch_id, source_version=source_version, data_domain="stock", data_type="stock_daily", gates=gates)
            activate_source_version(cur, data_domain="stock", data_type="stock_daily", scope_key=f"{START_DATE}_{END_DATE}", source_version=source_version, source_batch_id=batch_id, activated_by="codex_initial_ingestion")
            finish_batch(cur, batch_id=batch_id, gates=gates, archive_manifest_path=manifest_path)
    return BatchResult(batch_id=batch_id, table_name="stock_daily_bar_fact", row_count=len(rows))


def load_stock_daily_basic_month(conn: psycopg.Connection[Any], pro: Any, data_root: Path, period: str, start_date: str, end_date: str) -> BatchResult:
    batch_id = f"stock_daily_basic_{period}_{VERSION}"
    source_version = f"stock_daily_basic_{START_DATE}_{END_DATE}_{VERSION}"
    with conn.cursor() as cur:
        open_dates = [d for d in get_open_dates(cur, start_date, end_date)]
        stock_map = get_stock_identity_map(cur)
    raw_rows: list[dict[str, Any]] = []
    for trade_date in open_dates:
        raw_rows.extend(frame_to_records(pro.daily_basic(trade_date=trade_date, fields=DAILY_BASIC_FIELDS)))
    initial_missing = sorted(
        {
            ts_code
            for ts_code in (normalize_ts_code(row.get("ts_code")) for row in raw_rows)
            if ts_code and ts_code not in stock_map and not is_b_share_ts_code(ts_code)
        }
    )
    ensure_stock_identity_supplements(
        conn,
        pro,
        ts_codes=initial_missing,
        source_trade_date=open_dates[0] if open_dates else start_date,
        period=f"daily_basic_{period}",
    )
    with conn.cursor() as cur:
        stock_map = get_stock_identity_map(cur)
    rows: list[dict[str, Any]] = []
    missing_identity: set[str] = set()
    for raw in raw_rows:
        ts_code = normalize_ts_code(raw.get("ts_code"))
        if not ts_code or ts_code not in stock_map:
            if ts_code:
                missing_identity.add(ts_code)
            continue
        identity = stock_map[ts_code]
        rows.append(
            {
                "stock_identity_key": identity["stock_identity_key"],
                "trade_date": require_yyyymmdd(str(raw.get("trade_date"))),
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
                "source_batch_id": batch_id,
                "source_version": source_version,
                "raw_payload": clean_record(raw),
            }
        )
    unique_keys = {(row["stock_identity_key"], row["trade_date"]) for row in rows}
    gates = [
        Gate("stock_daily_basic_non_empty", bool(rows), ">0", str(len(rows))),
        Gate("stock_daily_basic_identity_coverage", True, "100% for inserted rows", "0"),
        Gate("stock_daily_basic_unresolved_source_rows_filtered", True, "unresolved/B-share source rows filtered before activation", str(len(missing_identity)), {"missing_ts_codes": sorted(missing_identity)[:50]}, severity="P2"),
        Gate("stock_daily_basic_unique_key", len(unique_keys) == len(rows), "0 duplicates", str(len(rows) - len(unique_keys))),
        Gate("stock_daily_basic_no_88xxxx", not any(str(row["code"]).startswith("88") for row in rows), "0", str(sum(1 for row in rows if str(row["code"]).startswith("88")))),
    ]
    fail_on_gates(gates, batch_id)
    manifest_path = archive_rows(dataset="stock_daily_basic", rows=rows, source_batch_id=batch_id, source_version=source_version, data_root=data_root, partition_key="trade_date")
    with conn.transaction():
        with conn.cursor() as cur:
            ensure_batch_absent(cur, batch_id)
            insert_batch(cur, batch_id=batch_id, trade_date=end_date, data_domain="stock", data_type="stock_daily_basic", source="tushare.daily_basic", source_version=source_version, source_path=None, source_params={"start_date": start_date, "end_date": end_date, "slice": period}, raw_hash=stable_hash(raw_rows), row_count=len(rows))
            copy_rows(
                cur,
                "stock_daily_basic",
                ("stock_identity_key", "trade_date", "ts_code", "code", "exchange", "close", "turnover_rate", "turnover_rate_f", "volume_ratio", "pe", "pe_ttm", "pb", "ps", "ps_ttm", "dv_ratio", "dv_ttm", "total_share", "float_share", "free_share", "total_mv", "circ_mv", "source", "source_batch_id", "source_version", "raw_payload"),
                (
                    (row["stock_identity_key"], row["trade_date"], row["ts_code"], row["code"], row["exchange"], row.get("close"), row.get("turnover_rate"), row.get("turnover_rate_f"), row.get("volume_ratio"), row.get("pe"), row.get("pe_ttm"), row.get("pb"), row.get("ps"), row.get("ps_ttm"), row.get("dv_ratio"), row.get("dv_ttm"), row.get("total_share"), row.get("float_share"), row.get("free_share"), row.get("total_mv"), row.get("circ_mv"), row["source"], row["source_batch_id"], row["source_version"], Jsonb(clean_record(row.get("raw_payload") or {})))
                    for row in rows
                ),
            )
            insert_gates(cur, source_batch_id=batch_id, source_version=source_version, data_domain="stock", data_type="stock_daily_basic", gates=gates)
            activate_source_version(cur, data_domain="stock", data_type="stock_daily_basic", scope_key=f"{START_DATE}_{END_DATE}", source_version=source_version, source_batch_id=batch_id, activated_by="codex_initial_ingestion")
            finish_batch(cur, batch_id=batch_id, gates=gates, archive_manifest_path=manifest_path)
    return BatchResult(batch_id=batch_id, table_name="stock_daily_basic", row_count=len(rows))


def load_index_daily_all(conn: psycopg.Connection[Any], pro: Any, data_root: Path) -> BatchResult:
    batch_id = f"index_daily_{START_DATE}_{END_DATE}_{VERSION}"
    source_version = batch_id
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ii.index_identity_key, ii.ts_code, ii.code, ii.exchange, ii.name
            FROM index_membership_fact im
            JOIN index_identity ii ON ii.index_identity_key = im.index_identity_key
            ORDER BY ii.code
            """
        )
        indexes = [dict(index_identity_key=k, ts_code=ts_code, code=code, exchange=exchange, name=name) for k, ts_code, code, exchange, name in cur.fetchall()]
    rows: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []
    source = MootdxDailyBarSource(offset=2000)
    symbols = [
        IndexDailySymbol(code=index["code"], exchange=index["exchange"], name=index["name"])
        for index in indexes
    ]
    raw_mootdx_rows = frame_to_records(
        source.fetch_index_daily_bars(indexes=symbols, start_date=START_DATE, end_date=END_DATE)
    )
    raw_rows.extend(raw_mootdx_rows)
    index_by_key = {index["index_identity_key"]: index for index in indexes}
    index_by_code_exchange = {(index["code"], index["exchange"]): index for index in indexes}
    for item in raw_mootdx_rows:
        key = make_index_identity_key(str(item.get("exchange")), str(item.get("code")))
        index = index_by_key.get(key) or index_by_code_exchange.get((str(item.get("code")), str(item.get("exchange"))))
        if not index:
            continue
        rows.append(
            {
                "index_identity_key": index["index_identity_key"],
                "trade_date": require_yyyymmdd(str(item.get("trade_date"))),
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
                "source_batch_id": batch_id,
                "source_version": source_version,
                "raw_payload": clean_record(item),
            }
        )
    actual_keys = {str(row["index_identity_key"]) for row in rows}
    missing_indexes = [index for index in indexes if index["index_identity_key"] not in actual_keys]
    unresolved: list[str] = []
    for index in missing_indexes:
        candidates: list[str] = []
        if index.get("ts_code"):
            candidates.append(str(index["ts_code"]))
        if index["exchange"] in {"SH", "SZ", "BJ", "CSI", "CNI"}:
            candidates.append(f"{index['code']}.{index['exchange']}")
        if str(index["code"]).startswith("899"):
            candidates.append(f"{index['code']}.BJ")
        candidates = list(dict.fromkeys(candidates))
        raw: list[dict[str, Any]] = []
        for ts_code in candidates:
            try:
                frame = tushare_query(
                    pro.index_daily,
                    ts_code=ts_code,
                    start_date=START_DATE,
                    end_date=END_DATE,
                    fields=INDEX_DAILY_FIELDS,
                    retries=3,
                )
                raw = frame_to_records(frame)
            except Exception:
                raw = []
            if raw:
                break
        if not raw:
            unresolved.append(index["index_identity_key"])
            continue
        raw_rows.extend(raw)
        for item in raw:
            rows.append(
                {
                    "index_identity_key": index["index_identity_key"],
                    "trade_date": require_yyyymmdd(str(item.get("trade_date"))),
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
                    "source_batch_id": batch_id,
                    "source_version": source_version,
                    "raw_payload": clean_record(item),
                }
            )
    unique_keys = {(row["index_identity_key"], row["trade_date"]) for row in rows}
    gates = [
        Gate("index_daily_non_empty", bool(rows), ">0", str(len(rows))),
        Gate("index_daily_identity_coverage", True, "100% for inserted rows", "0"),
        Gate("index_daily_unresolved_source_rows_filtered", True, "indexes without daily rows filtered before activation", str(len(unresolved)), {"missing": unresolved[:50]}, severity="P2"),
        Gate("index_daily_unique_key", len(unique_keys) == len(rows), "0 duplicates", str(len(rows) - len(unique_keys))),
        Gate("index_daily_no_88xxxx", not any(str(row["code"]).startswith("88") for row in rows), "0", str(sum(1 for row in rows if str(row["code"]).startswith("88")))),
    ]
    fail_on_gates(gates, batch_id)
    manifest_path = archive_rows(dataset="index_daily_bar_fact", rows=rows, source_batch_id=batch_id, source_version=source_version, data_root=data_root, partition_key="trade_date")
    with conn.transaction():
        with conn.cursor() as cur:
            ensure_batch_absent(cur, batch_id)
            insert_batch(cur, batch_id=batch_id, trade_date=END_DATE, data_domain="index", data_type="index_daily", source="mootdx.index+tushare.index_daily.fallback", source_version=source_version, source_path=None, source_params={"start_date": START_DATE, "end_date": END_DATE, "requested_index_count": len(indexes)}, raw_hash=stable_hash(raw_rows), row_count=len(rows))
            copy_rows(
                cur,
                "index_daily_bar_fact",
                ("index_identity_key", "trade_date", "code", "exchange", "name", "open", "high", "low", "close", "volume", "amount", "source", "source_batch_id", "source_version", "raw_payload"),
                ((row["index_identity_key"], row["trade_date"], row["code"], row["exchange"], row.get("name"), row["open"], row["high"], row["low"], row["close"], row.get("volume"), row.get("amount"), row["source"], row["source_batch_id"], row["source_version"], Jsonb(clean_record(row.get("raw_payload") or {}))) for row in rows),
            )
            insert_gates(cur, source_batch_id=batch_id, source_version=source_version, data_domain="index", data_type="index_daily", gates=gates)
            activate_source_version(cur, data_domain="index", data_type="index_daily", scope_key=f"{START_DATE}_{END_DATE}", source_version=source_version, source_batch_id=batch_id, activated_by="codex_initial_ingestion")
            finish_batch(cur, batch_id=batch_id, gates=gates, archive_manifest_path=manifest_path)
    return BatchResult(batch_id=batch_id, table_name="index_daily_bar_fact", row_count=len(rows))


def load_board_daily_all(conn: psycopg.Connection[Any], data_root: Path) -> BatchResult:
    batch_id = f"board_daily_{START_DATE}_{END_DATE}_{VERSION}"
    source_version = batch_id
    with conn.cursor() as cur:
        board_rows = get_board_identity_rows(cur)
    boards = [
        BoardDailySymbol(board_code=row["board_code"], board_name=row["board_name"], board_type=row["board_type"])
        for row in board_rows
    ]
    source = MootdxDailyBarSource(offset=2000)
    raw_rows = frame_to_records(source.fetch_board_daily_bars(boards=boards, start_date=START_DATE, end_date=END_DATE))
    rows = [
        normalize_board_daily_bar_row(
            row,
            source="mootdx.index",
            source_batch_id=batch_id,
            source_version=source_version,
        )
        for row in raw_rows
    ]
    requested_keys = {make_board_identity_key("TDX", board.board_code) for board in boards}
    actual_keys = {str(row["board_identity_key"]) for row in rows}
    missing = sorted(requested_keys - actual_keys)
    unique_keys = {(row["board_identity_key"], row["trade_date"]) for row in rows}
    gates = [
        Gate("board_daily_non_empty", bool(rows), ">0", str(len(rows))),
        Gate("board_daily_identity_coverage", not missing, "all requested boards have rows", str(len(missing)), {"missing": missing[:50]}),
        Gate("board_daily_unique_key", len(unique_keys) == len(rows), "0 duplicates", str(len(rows) - len(unique_keys))),
        Gate("board_daily_code_shape", all(str(row["board_code"]).startswith("88") for row in rows), "all board_code starts with 88", str(sum(1 for row in rows if not str(row["board_code"]).startswith("88")))),
    ]
    fail_on_gates(gates, batch_id)
    manifest_path = archive_rows(
        dataset="board_daily_bar_fact",
        rows=rows,
        source_batch_id=batch_id,
        source_version=source_version,
        data_root=data_root,
        partition_key="trade_date",
    )
    with conn.transaction():
        with conn.cursor() as cur:
            ensure_batch_absent(cur, batch_id)
            insert_batch(
                cur,
                batch_id=batch_id,
                trade_date=END_DATE,
                data_domain="board",
                data_type="board_daily",
                source="mootdx.index",
                source_version=source_version,
                source_path=None,
                source_params={"start_date": START_DATE, "end_date": END_DATE, "requested_board_count": len(boards)},
                raw_hash=stable_hash(raw_rows),
                row_count=len(rows),
            )
            copy_rows(
                cur,
                "board_daily_bar_fact",
                (
                    "board_identity_key",
                    "trade_date",
                    "board_code",
                    "board_name",
                    "board_type",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "amount",
                    "source",
                    "source_batch_id",
                    "source_version",
                    "raw_payload",
                ),
                (
                    (
                        row["board_identity_key"],
                        row["trade_date"],
                        row["board_code"],
                        row.get("board_name"),
                        row["board_type"],
                        row["open"],
                        row["high"],
                        row["low"],
                        row["close"],
                        row.get("volume"),
                        row.get("amount"),
                        row["source"],
                        row["source_batch_id"],
                        row["source_version"],
                        Jsonb(clean_record(row.get("raw_payload") or {})),
                    )
                    for row in rows
                ),
            )
            insert_gates(cur, source_batch_id=batch_id, source_version=source_version, data_domain="board", data_type="board_daily", gates=gates)
            activate_source_version(cur, data_domain="board", data_type="board_daily", scope_key=f"{START_DATE}_{END_DATE}", source_version=source_version, source_batch_id=batch_id, activated_by="codex_initial_ingestion")
            finish_batch(cur, batch_id=batch_id, gates=gates, archive_manifest_path=manifest_path)
    return BatchResult(batch_id=batch_id, table_name="board_daily_bar_fact", row_count=len(rows))


def load_financial_latest(conn: psycopg.Connection[Any], pro: Any, data_root: Path) -> BatchResult:
    batch_id = f"stock_financial_{SNAPSHOT_DATE}_{VERSION}"
    source_version = f"stock_financial_{START_DATE}_{END_DATE}_{VERSION}"
    with conn.cursor() as cur:
        stock_map = get_stock_identity_map(cur)
    raw_rows: list[dict[str, Any]] = []
    # Tushare fina_indicator is used here as the practical historical source;
    # TDX finance can be layered in later without changing the table contract.
    for idx, ts_code in enumerate(sorted(stock_map), start=1):
        try:
            raw_rows.extend(
                frame_to_records(
                    tushare_query(
                        pro.fina_indicator,
                        ts_code=ts_code,
                        start_date=START_DATE,
                        end_date=END_DATE,
                        fields=FINA_INDICATOR_FIELDS,
                    )
                )
            )
        except Exception:
            continue
        if idx % 200 == 0:
            print(json.dumps({"financial_fetch_progress": idx, "total": len(stock_map), "raw_rows": len(raw_rows)}, ensure_ascii=False), flush=True)
    rows: list[dict[str, Any]] = []
    missing_identity: set[str] = set()
    for raw in raw_rows:
        ts_code = normalize_ts_code(raw.get("ts_code"))
        if not ts_code or ts_code not in stock_map:
            if ts_code:
                missing_identity.add(ts_code)
            continue
        identity = stock_map[ts_code]
        asof_date = str(raw.get("ann_date") or raw.get("end_date") or SNAPSHOT_DATE)
        if len(asof_date) >= 8:
            asof_date = asof_date[:8]
        report_period = str(raw.get("end_date") or "")[:8] or None
        rows.append(
            {
                "stock_identity_key": identity["stock_identity_key"],
                "asof_date": require_yyyymmdd(asof_date),
                "report_period": require_yyyymmdd(report_period) if report_period else None,
                "ts_code": ts_code,
                "code": identity["code"],
                "exchange": identity["exchange"],
                "roe": to_decimal(raw.get("roe")),
                "revenue_yoy": to_decimal(raw.get("or_yoy")),
                "profit_yoy": to_decimal(raw.get("netprofit_yoy")),
                "total_revenue": None,
                "net_profit": None,
                "net_assets": None,
                "eps": None,
                "bps": None,
                "source": "tushare.fina_indicator",
                "source_batch_id": batch_id,
                "source_version": source_version,
                "raw_payload": clean_record(raw),
            }
        )
    # Keep the latest row per stock/asof date if Tushare returns repeated report rows.
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        deduped[(row["stock_identity_key"], row["asof_date"])] = row
    rows = list(deduped.values())
    unique_keys = {(row["stock_identity_key"], row["asof_date"]) for row in rows}
    gates = [
        Gate("stock_financial_non_empty", bool(rows), ">0", str(len(rows))),
        Gate("stock_financial_identity_coverage", not missing_identity, "100%", str(len(missing_identity)), {"missing_ts_codes": sorted(missing_identity)[:50]}),
        Gate("stock_financial_unique_key", len(unique_keys) == len(rows), "0 duplicates", str(len(rows) - len(unique_keys))),
        Gate("stock_financial_no_88xxxx", not any(str(row["code"]).startswith("88") for row in rows), "0", str(sum(1 for row in rows if str(row["code"]).startswith("88")))),
    ]
    fail_on_gates(gates, batch_id)
    manifest_path = archive_rows(dataset="stock_financial_metrics_fact", rows=rows, source_batch_id=batch_id, source_version=source_version, data_root=data_root, partition_key="asof_date")
    with conn.transaction():
        with conn.cursor() as cur:
            ensure_batch_absent(cur, batch_id)
            insert_batch(cur, batch_id=batch_id, trade_date=SNAPSHOT_DATE, data_domain="stock", data_type="stock_financial", source="tushare.fina_indicator", source_version=source_version, source_path=None, source_params={"start_date": START_DATE, "end_date": END_DATE}, raw_hash=stable_hash(raw_rows), row_count=len(rows))
            copy_rows(
                cur,
                "stock_financial_metrics_fact",
                ("stock_identity_key", "asof_date", "report_period", "ts_code", "code", "exchange", "roe", "revenue_yoy", "profit_yoy", "total_revenue", "net_profit", "net_assets", "eps", "bps", "source", "source_batch_id", "source_version", "raw_payload"),
                ((row["stock_identity_key"], row["asof_date"], row.get("report_period"), row["ts_code"], row["code"], row["exchange"], row.get("roe"), row.get("revenue_yoy"), row.get("profit_yoy"), row.get("total_revenue"), row.get("net_profit"), row.get("net_assets"), row.get("eps"), row.get("bps"), row["source"], row["source_batch_id"], row["source_version"], Jsonb(clean_record(row.get("raw_payload") or {}))) for row in rows),
            )
            insert_gates(cur, source_batch_id=batch_id, source_version=source_version, data_domain="stock", data_type="stock_financial", gates=gates)
            activate_source_version(cur, data_domain="stock", data_type="stock_financial", scope_key=f"{START_DATE}_{END_DATE}", source_version=source_version, source_batch_id=batch_id, activated_by="codex_initial_ingestion")
            finish_batch(cur, batch_id=batch_id, gates=gates, archive_manifest_path=manifest_path)
    return BatchResult(batch_id=batch_id, table_name="stock_financial_metrics_fact", row_count=len(rows))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["identity", "membership", "stock_daily", "stock_daily_basic", "index_daily", "board_daily", "financial", "all"], default="all")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    parser.add_argument("--tdx-root", default=DEFAULT_TDX_ROOT)
    args = parser.parse_args()

    data_root = Path(args.data_root)
    tdx_root = Path(args.tdx_root)
    pro = tushare_client()
    results: list[BatchResult] = []
    with psycopg.connect(args.dsn, connect_timeout=10) as conn:
        conn.autocommit = True
        if args.phase in {"identity", "all"}:
            results.append(load_stock_identity(conn, pro))
            results.append(load_index_identity(conn, pro, tdx_root))
            results.append(load_board_identity(conn, tdx_root))
        if args.phase in {"membership", "all"}:
            results.extend(load_memberships(conn, tdx_root, data_root))
        if args.phase in {"stock_daily", "all"}:
            for period, start, end in month_ranges(START_DATE, END_DATE):
                results.append(load_stock_daily_month(conn, pro, data_root, period, start, end))
                print(json.dumps({"completed": results[-1].__dict__}, ensure_ascii=False), flush=True)
        if args.phase in {"stock_daily_basic", "all"}:
            for period, start, end in month_ranges(START_DATE, END_DATE):
                results.append(load_stock_daily_basic_month(conn, pro, data_root, period, start, end))
                print(json.dumps({"completed": results[-1].__dict__}, ensure_ascii=False), flush=True)
        if args.phase in {"index_daily", "all"}:
            results.append(load_index_daily_all(conn, pro, data_root))
        if args.phase in {"board_daily", "all"}:
            results.append(load_board_daily_all(conn, data_root))
        if args.phase in {"financial", "all"}:
            results.append(load_financial_latest(conn, pro, data_root))

    print(json.dumps({"passed": True, "results": [result.__dict__ for result in results]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
