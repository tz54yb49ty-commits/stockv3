#!/usr/bin/env python3
"""Repair active index_daily history for 000001.SH.

This is a narrow raw-ingestion repair tool. It creates a new index_daily
source_version for one source trade date by carrying forward the active
source-date rows and adding 000001.SH historical daily bars. It checks the
existing PostgreSQL fact table and Parquet archive first; external index daily
sources are used only when the ingestion warehouse itself lacks required
history.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for path in (str(PROJECT_ROOT), str(SRC_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.condition.basis import period_ranges
from ashare_v3.ingestion.common import require_yyyymmdd
from ashare_v3.ingestion.daily_bars import IndexDailySymbol
from ashare_v3.ingestion.mootdx_daily_source import MootdxDailyBarSource
from scripts.run_real_daily_incremental import (
    ACTIVATED_BY,
    FIXED_CORE_INDEX_IDENTITIES,
    batch_id,
    run_persisted_batch,
)
from scripts.run_real_initial_ingestion import (
    DEFAULT_DATA_ROOT,
    DEFAULT_DSN,
    Gate,
    INDEX_DAILY_FIELDS,
    archive_rows,
    clean_record,
    copy_rows,
    decimal_required,
    frame_to_records,
    stable_hash,
    to_decimal,
    tushare_client,
    tushare_query,
)


TARGET_IDENTITY_KEY = "index:SH:000001"
TARGET_TS_CODE = "000001.SH"
TARGET_CODE = "000001"
TARGET_EXCHANGE = "SH"
TARGET_NAME = "上证指数"
DEFAULT_HISTORY_START_DATE = "20230101"
REPAIR_ACTIVATED_BY = "codex_index_daily_000001_history_repair"


@dataclass(frozen=True)
class ActiveSource:
    source_version: str
    source_batch_id: str
    previous_source_version: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-trade-date", required=True)
    parser.add_argument("--version", default="v3")
    parser.add_argument("--history-start-date", default=DEFAULT_HISTORY_START_DATE)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    parser.add_argument("--mootdx-offset", type=int, default=900)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--run-ready-check", action="store_true")
    parser.add_argument(
        "--report-path",
        default=str(PROJECT_ROOT / "docs" / "N2_R_INDEX_DAILY_000001_HISTORY_REPAIR_REPORT.md"),
    )
    parser.add_argument(
        "--rollback-sql-path",
        default=str(PROJECT_ROOT / "sql" / "N2_R_index_daily_000001_history_repair_rollback.sql"),
    )
    return parser.parse_args()


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def get_active_index_daily(cur: psycopg.Cursor[Mapping[str, Any]], trade_date: str) -> ActiveSource:
    cur.execute(
        """
        SELECT source_version, source_batch_id, previous_source_version
        FROM common_active_source_version
        WHERE data_domain = 'index'
          AND data_type = 'index_daily'
          AND scope_key = %s
        """,
        (trade_date,),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"active index_daily source_version missing for {trade_date}")
    return ActiveSource(
        source_version=str(row["source_version"]),
        source_batch_id=str(row["source_batch_id"]),
        previous_source_version=str(row["previous_source_version"]) if row["previous_source_version"] else None,
    )


def get_target_identity(cur: psycopg.Cursor[Mapping[str, Any]]) -> dict[str, Any]:
    cur.execute(
        """
        SELECT index_identity_key, ts_code, code, exchange, name
        FROM index_identity
        WHERE index_identity_key = %s
        """,
        (TARGET_IDENTITY_KEY,),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"index identity missing: {TARGET_IDENTITY_KEY}")
    return dict(row)


def get_active_source_date_rows(
    cur: psycopg.Cursor[Mapping[str, Any]],
    *,
    source_version: str,
    trade_date: str,
) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT index_identity_key, trade_date, code, exchange, name,
               open, high, low, close, volume, amount,
               source, source_batch_id, source_version, raw_payload
        FROM index_daily_bar_fact
        WHERE source_version = %s
          AND trade_date = %s
        ORDER BY index_identity_key
        """,
        (source_version, trade_date),
    )
    return [dict(row) for row in cur.fetchall()]


def previous_trade_date(cur: psycopg.Cursor[Mapping[str, Any]], source_trade_date: str) -> str:
    cur.execute(
        """
        SELECT prev_trade_date
        FROM common_trade_calendar
        WHERE trade_date = %s
        """,
        (source_trade_date,),
    )
    row = cur.fetchone()
    if row and row["prev_trade_date"]:
        return require_yyyymmdd(str(row["prev_trade_date"]), "prev_trade_date")
    cur.execute(
        """
        SELECT max(trade_date)
        FROM common_trade_calendar
        WHERE trade_date < %s
          AND is_open
        """,
        (source_trade_date,),
    )
    fallback = cur.fetchone()
    if not fallback or not fallback["max"]:
        raise RuntimeError(f"cannot infer previous trade date for {source_trade_date}")
    return require_yyyymmdd(str(fallback["max"]), "prev_trade_date")


def required_windows(source_trade_date: str, prev_trade_date: str) -> list[dict[str, str]]:
    windows = period_ranges(source_trade_date, prev_trade_date)
    return sorted(windows, key=lambda item: (item["start_date"], item["end_date"], item["period"], item["slot"]))


def get_open_dates_by_range(
    cur: psycopg.Cursor[Mapping[str, Any]],
    windows: Sequence[Mapping[str, str]],
) -> dict[tuple[str, str], list[str]]:
    result: dict[tuple[str, str], list[str]] = {}
    for window in windows:
        start_date = str(window["start_date"])
        end_date = str(window["end_date"])
        cur.execute(
            """
            SELECT trade_date
            FROM common_trade_calendar
            WHERE trade_date BETWEEN %s AND %s
              AND is_open
            ORDER BY trade_date
            """,
            (start_date, end_date),
        )
        result[(start_date, end_date)] = [str(row["trade_date"]) for row in cur.fetchall()]
    return result


def get_open_dates_for_span(
    cur: psycopg.Cursor[Mapping[str, Any]],
    *,
    start_date: str,
    end_date: str,
) -> list[str]:
    cur.execute(
        """
        SELECT trade_date
        FROM common_trade_calendar
        WHERE trade_date BETWEEN %s AND %s
          AND is_open
        ORDER BY trade_date
        """,
        (start_date, end_date),
    )
    return [str(row["trade_date"]) for row in cur.fetchall()]


def raw_payload_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if value is None or value == "":
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"raw_payload": value}
        return dict(parsed) if isinstance(parsed, Mapping) else {"raw_payload": parsed}
    return {"raw_payload": clean_value(value)}


def normalize_warehouse_history_row(
    row: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
    source_batch_id: str,
    source_version: str,
    warehouse_source: str,
) -> dict[str, Any]:
    raw_payload = raw_payload_dict(row.get("raw_payload"))
    raw_payload["_warehouse_reuse"] = {
        "previous_source": row.get("source"),
        "previous_source_batch_id": row.get("source_batch_id"),
        "previous_source_version": row.get("source_version"),
        "warehouse_source": warehouse_source,
    }
    return {
        "index_identity_key": str(identity["index_identity_key"]),
        "trade_date": require_yyyymmdd(str(row.get("trade_date")), "trade_date"),
        "code": str(identity["code"]),
        "exchange": str(identity["exchange"]),
        "name": identity.get("name"),
        "open": decimal_required(row.get("open"), "open"),
        "high": decimal_required(row.get("high"), "high"),
        "low": decimal_required(row.get("low"), "low"),
        "close": decimal_required(row.get("close"), "close"),
        "volume": to_decimal(row.get("volume")) or to_decimal(row.get("vol")),
        "amount": to_decimal(row.get("amount")),
        "source": warehouse_source,
        "source_batch_id": source_batch_id,
        "source_version": source_version,
        "raw_payload": clean_record(raw_payload),
    }


def missing_dates(rows: Sequence[Mapping[str, Any]], required_trade_dates: Sequence[str]) -> list[str]:
    row_dates = {str(row["trade_date"]) for row in rows}
    return sorted(set(required_trade_dates) - row_dates)


def read_parquet_history_rows(
    *,
    identity: Mapping[str, Any],
    source_batch_id: str,
    source_version: str,
    data_root: Path,
    start_date: str,
    end_date: str,
    excluded_source_version: str,
) -> list[dict[str, Any]]:
    try:
        import pyarrow.parquet as pq
    except Exception:
        return []

    manifest_root = data_root / "data_lake" / "_manifests" / "index_daily_bar_fact"
    if not manifest_root.exists():
        return []

    rows_by_date: dict[str, dict[str, Any]] = {}
    columns = [
        "index_identity_key",
        "trade_date",
        "code",
        "exchange",
        "name",
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
    ]
    for manifest_path in sorted(manifest_root.glob("source_version=*/index_daily*.manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if str(manifest.get("source_version")) == excluded_source_version:
            continue
        for item in manifest.get("files") or []:
            partition_date = str((item.get("partition_values") or {}).get("trade_date") or "")
            if partition_date and not (start_date <= partition_date <= end_date):
                continue
            file_path = Path(str(item.get("path") or ""))
            if not file_path.exists():
                continue
            table = pq.ParquetFile(file_path).read(columns=columns)
            for raw in table.to_pylist():
                if str(raw.get("index_identity_key")) != TARGET_IDENTITY_KEY:
                    continue
                trade_date = require_yyyymmdd(str(raw.get("trade_date")), "trade_date")
                if not (start_date <= trade_date <= end_date):
                    continue
                rows_by_date.setdefault(
                    trade_date,
                    normalize_warehouse_history_row(
                        raw,
                        identity=identity,
                        source_batch_id=source_batch_id,
                        source_version=source_version,
                        warehouse_source="warehouse.parquet.index_daily_bar_fact",
                    ),
                )
    return [rows_by_date[trade_date] for trade_date in sorted(rows_by_date)]


def load_warehouse_000001_history(
    cur: psycopg.Cursor[Mapping[str, Any]],
    *,
    identity: Mapping[str, Any],
    source_batch_id: str,
    source_version: str,
    data_root: Path,
    start_date: str,
    end_date: str,
    required_trade_dates: Sequence[str],
    preferred_source_version: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows_by_date: dict[str, dict[str, Any]] = {}
    cur.execute(
        """
        SELECT index_identity_key, trade_date, code, exchange, name,
               open, high, low, close, volume, amount,
               source, source_batch_id, source_version, raw_payload
        FROM index_daily_bar_fact
        WHERE index_identity_key = %s
          AND trade_date BETWEEN %s AND %s
          AND source_version <> %s
        ORDER BY trade_date,
                 CASE WHEN source_version = %s THEN 0 ELSE 1 END,
                 source_version DESC
        """,
        (TARGET_IDENTITY_KEY, start_date, end_date, source_version, preferred_source_version),
    )
    db_raw_rows = [dict(row) for row in cur.fetchall()]
    for raw in db_raw_rows:
        trade_date = require_yyyymmdd(str(raw.get("trade_date")), "trade_date")
        rows_by_date.setdefault(
            trade_date,
            normalize_warehouse_history_row(
                raw,
                identity=identity,
                source_batch_id=source_batch_id,
                source_version=source_version,
                warehouse_source="warehouse.postgres.index_daily_bar_fact",
            ),
        )

    db_missing = missing_dates(list(rows_by_date.values()), required_trade_dates)
    parquet_rows: list[dict[str, Any]] = []
    if db_missing:
        parquet_rows = read_parquet_history_rows(
            identity=identity,
            source_batch_id=source_batch_id,
            source_version=source_version,
            data_root=data_root,
            start_date=start_date,
            end_date=end_date,
            excluded_source_version=source_version,
        )
        for row in parquet_rows:
            rows_by_date.setdefault(str(row["trade_date"]), row)

    rows = [rows_by_date[trade_date] for trade_date in sorted(rows_by_date)]
    final_missing = missing_dates(rows, required_trade_dates)
    summary = {
        "warehouse_checked": True,
        "warehouse_used": not final_missing,
        "history_start_date": start_date,
        "history_end_date": end_date,
        "required_trade_date_count": len(required_trade_dates),
        "postgres_raw_count": len(db_raw_rows),
        "postgres_unique_trade_days": len({str(row.get("trade_date")) for row in db_raw_rows}),
        "postgres_missing_required_count": len(db_missing),
        "postgres_missing_required_sample": db_missing[:20],
        "parquet_raw_count": len(parquet_rows),
        "combined_unique_trade_days": len({str(row["trade_date"]) for row in rows}),
        "missing_required_count": len(final_missing),
        "missing_required_sample": final_missing[:20],
        "external_pull_required": bool(final_missing),
    }
    return rows, summary


def normalize_source_row(
    raw: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
    source_batch_id: str,
    source_version: str,
    source: str,
) -> dict[str, Any]:
    return {
        "index_identity_key": str(identity["index_identity_key"]),
        "trade_date": require_yyyymmdd(str(raw.get("trade_date")), "trade_date"),
        "code": str(identity["code"]),
        "exchange": str(identity["exchange"]),
        "name": identity.get("name"),
        "open": decimal_required(raw.get("open"), "open"),
        "high": decimal_required(raw.get("high"), "high"),
        "low": decimal_required(raw.get("low"), "low"),
        "close": decimal_required(raw.get("close"), "close"),
        "volume": to_decimal(raw.get("vol")) or to_decimal(raw.get("volume")),
        "amount": to_decimal(raw.get("amount")),
        "source": source,
        "source_batch_id": source_batch_id,
        "source_version": source_version,
        "raw_payload": clean_record(raw),
    }


def fetch_000001_history(
    pro: Any | None,
    *,
    identity: Mapping[str, Any],
    source_batch_id: str,
    source_version: str,
    start_date: str,
    end_date: str,
    required_trade_dates: Sequence[str],
    mootdx_offset: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    raw_rows: list[dict[str, Any]] = []
    rows_by_date: dict[str, dict[str, Any]] = {}
    source_summary: dict[str, Any] = {
        "mootdx_raw_count": 0,
        "tushare_raw_count": 0,
        "tushare_fallback_used": False,
        "missing_required_after_mootdx": [],
    }

    mootdx = MootdxDailyBarSource(offset=mootdx_offset)
    symbol = IndexDailySymbol(code=str(identity["code"]), exchange=str(identity["exchange"]), name=identity.get("name"))
    mootdx_rows = frame_to_records(mootdx.fetch_index_daily_bars(indexes=[symbol], start_date=start_date, end_date=end_date))
    source_summary["mootdx_raw_count"] = len(mootdx_rows)
    raw_rows.extend(mootdx_rows)
    for raw in mootdx_rows:
        row = normalize_source_row(
            raw,
            identity=identity,
            source_batch_id=source_batch_id,
            source_version=source_version,
            source="mootdx.index",
        )
        rows_by_date[row["trade_date"]] = row

    missing_required = sorted(set(required_trade_dates) - set(rows_by_date))
    source_summary["missing_required_after_mootdx"] = missing_required[:50]
    if missing_required:
        if pro is None:
            pro = tushare_client()
        fallback_rows = frame_to_records(
            tushare_query(
                pro.index_daily,
                ts_code=TARGET_TS_CODE,
                start_date=start_date,
                end_date=end_date,
                fields=INDEX_DAILY_FIELDS,
                retries=3,
            )
        )
        source_summary["tushare_fallback_used"] = True
        source_summary["tushare_raw_count"] = len(fallback_rows)
        raw_rows.extend(fallback_rows)
        for raw in fallback_rows:
            row = normalize_source_row(
                raw,
                identity=identity,
                source_batch_id=source_batch_id,
                source_version=source_version,
                source="tushare.index_daily.fallback",
            )
            rows_by_date.setdefault(row["trade_date"], row)

    return sorted(rows_by_date.values(), key=lambda row: row["trade_date"]), raw_rows, source_summary


def carry_forward_row(row: Mapping[str, Any], *, source_batch_id: str, source_version: str) -> dict[str, Any]:
    raw_payload = dict(row.get("raw_payload") or {})
    raw_payload["_repair_carry_forward"] = {
        "previous_source_batch_id": row.get("source_batch_id"),
        "previous_source_version": row.get("source_version"),
    }
    carried = dict(row)
    carried["source_batch_id"] = source_batch_id
    carried["source_version"] = source_version
    carried["raw_payload"] = clean_record(raw_payload)
    return carried


def build_rows(
    *,
    active_rows: Sequence[Mapping[str, Any]],
    history_rows: Sequence[Mapping[str, Any]],
    source_batch_id: str,
    source_version: str,
) -> list[dict[str, Any]]:
    rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in active_rows:
        if str(row["index_identity_key"]) == TARGET_IDENTITY_KEY:
            continue
        carried = carry_forward_row(row, source_batch_id=source_batch_id, source_version=source_version)
        rows_by_key[(str(carried["index_identity_key"]), str(carried["trade_date"]))] = carried
    for row in history_rows:
        rows_by_key[(str(row["index_identity_key"]), str(row["trade_date"]))] = dict(row)
    return [rows_by_key[key] for key in sorted(rows_by_key)]


def coverage_details(
    *,
    row_dates: set[str],
    windows: Sequence[Mapping[str, str]],
    open_dates_by_range: Mapping[tuple[str, str], Sequence[str]],
) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for window in windows:
        key = (str(window["start_date"]), str(window["end_date"]))
        expected = list(open_dates_by_range.get(key) or [])
        if expected:
            missing = sorted(set(expected) - row_dates)
            passed = not missing
            actual = f"{len(expected) - len(missing)}/{len(expected)}"
        else:
            present = sorted(date for date in row_dates if key[0] <= date <= key[1])
            missing = []
            passed = bool(present)
            actual = f"{len(present)} rows; calendar_open_dates_unavailable"
        details.append(
            {
                "period": window["period"],
                "slot": window["slot"],
                "start_date": key[0],
                "end_date": key[1],
                "passed": passed,
                "actual": actual,
                "missing_sample": missing[:10],
            }
        )
    return details


def build_gates(
    *,
    rows: Sequence[Mapping[str, Any]],
    history_rows: Sequence[Mapping[str, Any]],
    active_rows_before: Sequence[Mapping[str, Any]],
    required_history_dates: Sequence[str],
    history_start_date: str,
    windows: Sequence[Mapping[str, str]],
    open_dates_by_range: Mapping[tuple[str, str], Sequence[str]],
    prev_trade_date: str,
    source_trade_date: str,
    source_summary: Mapping[str, Any],
) -> list[Gate]:
    target_rows = [row for row in rows if str(row["index_identity_key"]) == TARGET_IDENTITY_KEY]
    row_dates = {str(row["trade_date"]) for row in target_rows}
    current_rows = [row for row in rows if str(row["trade_date"]) == source_trade_date]
    fixed_present = sorted(set(FIXED_CORE_INDEX_IDENTITIES) & {str(row["index_identity_key"]) for row in current_rows})
    missing_fixed = sorted(set(FIXED_CORE_INDEX_IDENTITIES) - set(fixed_present))
    duplicate_count = len(rows) - len({(str(row["index_identity_key"]), str(row["trade_date"])) for row in rows})
    null_ohlc_amount = [
        str(row["trade_date"])
        for row in target_rows
        if row.get("open") is None or row.get("close") is None or row.get("amount") is None
    ]
    missing_history = sorted(set(required_history_dates) - row_dates)
    details = coverage_details(row_dates=row_dates, windows=windows, open_dates_by_range=open_dates_by_range)
    failed_windows = [item for item in details if not item["passed"]]
    return [
        Gate("index_daily_000001_history_non_empty", bool(history_rows), ">0", str(len(history_rows)), source_summary),
        Gate(
            "index_daily_000001_required_history_coverage",
            not missing_history,
            f"all open dates covered from {history_start_date} to {source_trade_date}",
            f"{len(required_history_dates) - len(missing_history)}/{len(required_history_dates)}",
            {"missing_sample": missing_history[:20], "source_summary": dict(source_summary)},
        ),
        Gate("index_daily_000001_previous_day_present", prev_trade_date in row_dates, prev_trade_date, str(prev_trade_date in row_dates)),
        Gate(
            "index_daily_000001_period_window_coverage",
            not failed_windows,
            "all N2-R current/previous/seed period windows covered",
            str(len(failed_windows)),
            {"windows": details},
        ),
        Gate(
            "index_daily_000001_ohlc_amount_non_null",
            not null_ohlc_amount,
            "open/close/amount non-null for 000001 rows",
            str(len(null_ohlc_amount)),
            {"missing_dates": null_ohlc_amount[:50]},
        ),
        Gate(
            "index_daily_fixed_core_daily_coverage",
            not missing_fixed,
            "all fixed core indexes have source_trade_date rows",
            str(len(missing_fixed)),
            {"missing": missing_fixed},
        ),
        Gate(
            "index_daily_current_trade_date_row_count_preserved",
            len(current_rows) == len(active_rows_before),
            str(len(active_rows_before)),
            str(len(current_rows)),
        ),
        Gate("index_daily_unique_key", duplicate_count == 0, "0 duplicates", str(duplicate_count)),
        Gate(
            "index_daily_no_88xxxx",
            not any(str(row["code"]).startswith("88") for row in rows),
            "0",
            str(sum(1 for row in rows if str(row["code"]).startswith("88"))),
        ),
    ]


def write_rollback_sql(
    path: Path,
    *,
    source_trade_date: str,
    new_source_version: str,
    previous_active: ActiveSource,
) -> None:
    previous_previous = previous_active.previous_source_version or "NULL"
    previous_previous_sql = "NULL" if previous_previous == "NULL" else f"'{previous_previous}'"
    sql = f"""-- Rollback for 000001.SH index_daily history repair.
-- Generated by scripts/repair_index_daily_000001_history.py
-- Scope: v3 development database only.
-- After this SQL succeeds, remove the repaired Parquet archive paths if a file rollback is also needed:
--   /Volumes/MacRaid/database/data_lake/index_daily_bar_fact/source_version={new_source_version}
--   /Volumes/MacRaid/database/data_lake/_manifests/index_daily_bar_fact/source_version={new_source_version}

BEGIN;

UPDATE common_active_source_version
SET source_version = '{previous_active.source_version}',
    source_batch_id = '{previous_active.source_batch_id}',
    previous_source_version = {previous_previous_sql},
    activated_at = now(),
    activated_by = 'rollback_{REPAIR_ACTIVATED_BY}'
WHERE data_domain = 'index'
  AND data_type = 'index_daily'
  AND scope_key = '{source_trade_date}'
  AND source_version = '{new_source_version}';

DELETE FROM index_daily_bar_fact
WHERE source_version = '{new_source_version}';

DELETE FROM common_quality_gate_result
WHERE source_batch_id = '{new_source_version}';

DELETE FROM common_ingest_batch
WHERE batch_id = '{new_source_version}';

COMMIT;
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sql, encoding="utf-8")


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    gates = report["quality_gates"]
    gate_lines = "\n".join(
        f"- {gate['name']}: {gate['status']} ({gate['actual']} / expected {gate['expected']})"
        for gate in gates
    )
    ready = report.get("condition_source_ready")
    ready_block = "未运行"
    if ready:
        ready_block = (
            f"exit_code={ready['exit_code']}\n\n"
            "```text\n"
            f"{ready['output'].strip()}\n"
            "```"
        )
    text = f"""# N2-R 000001.SH index_daily 历史修复报告

## 结论

- execute: `{report['execute']}`
- source_trade_date: `{report['source_trade_date']}`
- new_source_version: `{report['new_source_version']}`
- previous_active_source_version: `{report['previous_active_source_version']}`
- row_count_written: `{report['row_count_written']}`
- 000001_history_rows: `{report['target_history_rows']}`
- 000001_min_trade_date: `{report['target_min_trade_date']}`
- 000001_max_trade_date: `{report['target_max_trade_date']}`
- required_history_range: `{report['required_history_start_date']}` - `{report['source_trade_date']}`
- required_history_trade_days: `{report['required_history_trade_days']}`
- fixed_9_present_on_source_trade_date: `{report['fixed_9_present_count']}/9`
- rollback_sql: `{report['rollback_sql_path']}`

## 数据来源

```json
{json.dumps(report['source_summary'], ensure_ascii=False, indent=2, default=str)}
```

## 历史窗口

```json
{json.dumps(report['required_windows'], ensure_ascii=False, indent=2, default=str)}
```

## 质量闸

{gate_lines}

## condition source ready

{ready_block}

## 边界

- 未触碰旧系统写入。
- 未进入条件层 overwrite / execute。
- 未进入 N3。
- 未启动 worker。
- 未写 trigger/action/mobile/voice/sim。
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def maybe_run_ready_check(source_trade_date: str) -> dict[str, Any] | None:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "check_condition_source_ready.py"),
        "--source-trade-date",
        source_trade_date,
    ]
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env={**os.environ, "PYTHONPATH": str(SRC_ROOT)},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return {"exit_code": completed.returncode, "output": completed.stdout}


def main() -> int:
    args = parse_args()
    source_trade_date = require_yyyymmdd(args.source_trade_date, "source_trade_date")
    new_source_version = batch_id("index_daily", source_trade_date, args.version)
    new_source_batch_id = new_source_version
    report_path = Path(args.report_path)
    rollback_path = Path(args.rollback_sql_path)
    data_root = Path(args.data_root)
    history_start_date = require_yyyymmdd(args.history_start_date, "history_start_date")

    with psycopg.connect(args.dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            active = get_active_index_daily(cur, source_trade_date)
            identity = get_target_identity(cur)
            prev_trade_date = previous_trade_date(cur, source_trade_date)
            windows = required_windows(source_trade_date, prev_trade_date)
            window_min_start = min(str(window["start_date"]) for window in windows)
            min_start = min(history_start_date, window_min_start)
            open_dates = get_open_dates_by_range(cur, windows)
            required_trade_dates = get_open_dates_for_span(
                cur,
                start_date=min_start,
                end_date=source_trade_date,
            )
            active_rows = get_active_source_date_rows(
                cur,
                source_version=active.source_version,
                trade_date=source_trade_date,
            )
            if not active_rows:
                raise RuntimeError(f"active source-date rows missing for {active.source_version}:{source_trade_date}")
            cur.execute("SELECT status FROM common_ingest_batch WHERE batch_id = %s", (new_source_batch_id,))
            existing_batch = cur.fetchone()
            if existing_batch and args.execute:
                raise RuntimeError(f"target batch already exists: {new_source_batch_id} status={existing_batch['status']}")

            warehouse_rows, warehouse_summary = load_warehouse_000001_history(
                cur,
                identity=identity,
                source_batch_id=new_source_batch_id,
                source_version=new_source_version,
                data_root=data_root,
                start_date=min_start,
                end_date=source_trade_date,
                required_trade_dates=required_trade_dates,
                preferred_source_version=active.source_version,
            )

        if not warehouse_summary["external_pull_required"]:
            history_rows = warehouse_rows
            raw_rows = [warehouse_summary]
            source_summary = {
                **warehouse_summary,
                "external_fetch_used": False,
                "external_source_summary": None,
            }
            batch_source = "warehouse.index_daily_bar_fact+parquet_history+active_source_carry_forward"
        else:
            history_rows, raw_rows, external_summary = fetch_000001_history(
                None,
                identity=identity,
                source_batch_id=new_source_batch_id,
                source_version=new_source_version,
                start_date=min_start,
                end_date=source_trade_date,
                required_trade_dates=required_trade_dates,
                mootdx_offset=args.mootdx_offset,
            )
            source_summary = {
                **warehouse_summary,
                "external_fetch_used": True,
                "external_source_summary": external_summary,
            }
            batch_source = "mootdx.index+tushare.index_daily.fallback+active_source_carry_forward"

        rows = build_rows(
            active_rows=active_rows,
            history_rows=history_rows,
            source_batch_id=new_source_batch_id,
            source_version=new_source_version,
        )
        gates = build_gates(
            rows=rows,
            history_rows=history_rows,
            active_rows_before=active_rows,
            required_history_dates=required_trade_dates,
            history_start_date=min_start,
            windows=windows,
            open_dates_by_range=open_dates,
            prev_trade_date=prev_trade_date,
            source_trade_date=source_trade_date,
            source_summary=source_summary,
        )
        p0_failed = [gate for gate in gates if not gate.passed and gate.severity == "P0"]
        manifest_path: str | None = None
        if args.execute:
            if p0_failed:
                raise RuntimeError(
                    "P0 quality gate failed: "
                    + json.dumps(
                        [
                            {
                                "name": gate.name,
                                "expected": gate.expected,
                                "actual": gate.actual,
                                "details": dict(gate.details or {}),
                            }
                            for gate in p0_failed
                        ],
                        ensure_ascii=False,
                        default=str,
                    )[:4000]
                )
            manifest_path = archive_rows(
                dataset="index_daily_bar_fact",
                rows=rows,
                source_batch_id=new_source_batch_id,
                source_version=new_source_version,
                data_root=data_root,
                partition_key="trade_date",
            )

            def writer(cur: psycopg.Cursor[Any]) -> None:
                copy_rows(
                    cur,
                    "index_daily_bar_fact",
                    (
                        "index_identity_key",
                        "trade_date",
                        "code",
                        "exchange",
                        "name",
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
                            row["index_identity_key"],
                            row["trade_date"],
                            row["code"],
                            row["exchange"],
                            row.get("name"),
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

            run_persisted_batch(
                conn,
                source_batch_id=new_source_batch_id,
                trade_date=source_trade_date,
                data_domain="index",
                data_type="index_daily",
                source=batch_source,
                source_version=new_source_version,
                source_path=None,
                source_params={
                    "repair": "000001.SH historical index_daily window",
                    "target_identity_key": TARGET_IDENTITY_KEY,
                    "start_date": min_start,
                    "end_date": source_trade_date,
                    "warehouse_first": True,
                    "external_fetch_used": source_summary["external_fetch_used"],
                    "previous_active_source_version": active.source_version,
                    "mootdx_offset": args.mootdx_offset,
                    "fixed_core_index_identities": list(FIXED_CORE_INDEX_IDENTITIES),
                    "required_windows": json_safe(windows),
                    "required_trade_date_count": len(required_trade_dates),
                },
                raw_hash=stable_hash(raw_rows + [{"carry_forward_rows": len(active_rows) - 1}]),
                row_count=len(rows),
                gates=gates,
                writer=writer,
                activation_scope_key=source_trade_date,
                archive_manifest_path=manifest_path,
            )
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE common_active_source_version
                    SET activated_by = %s
                    WHERE data_domain = 'index'
                      AND data_type = 'index_daily'
                      AND scope_key = %s
                      AND source_version = %s
                    """,
                    (REPAIR_ACTIVATED_BY, source_trade_date, new_source_version),
                )
            write_rollback_sql(
                rollback_path,
                source_trade_date=source_trade_date,
                new_source_version=new_source_version,
                previous_active=active,
            )

    ready_result = maybe_run_ready_check(source_trade_date) if args.run_ready_check else None
    target_dates = sorted(row["trade_date"] for row in history_rows)
    fixed_9_present = sorted(
        {
            str(row["index_identity_key"])
            for row in rows
            if str(row["trade_date"]) == source_trade_date
            and str(row["index_identity_key"]) in set(FIXED_CORE_INDEX_IDENTITIES)
        }
    )
    report = {
        "execute": args.execute,
        "source_trade_date": source_trade_date,
        "new_source_version": new_source_version,
        "previous_active_source_version": active.source_version,
        "row_count_written": len(rows) if args.execute else 0,
        "row_count_planned": len(rows),
        "target_history_rows": len(history_rows),
        "target_min_trade_date": target_dates[0] if target_dates else None,
        "target_max_trade_date": target_dates[-1] if target_dates else None,
        "required_history_start_date": min_start,
        "required_history_trade_days": len(required_trade_dates),
        "fixed_9_present_count": len(fixed_9_present),
        "rollback_sql_path": str(rollback_path) if args.execute else None,
        "archive_manifest_path": manifest_path,
        "source_summary": source_summary,
        "required_windows": windows,
        "quality_gates": [
            {
                "name": gate.name,
                "status": "passed" if gate.passed else "failed",
                "expected": gate.expected,
                "actual": gate.actual,
                "severity": gate.severity,
                "details": json_safe(gate.details or {}),
            }
            for gate in gates
        ],
        "condition_source_ready": ready_result,
    }
    write_report(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if ready_result and ready_result["exit_code"] != 0:
        return int(ready_result["exit_code"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
