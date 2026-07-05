"""N1 index_daily 20260526 universe expansion execute runner support.

This module is safe to import and unit test. Real source fetch and PostgreSQL
commit only happen when the run-once CLI receives all explicit final-gate
flags.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal
import importlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.ingestion.tushare_env import load_tushare_token
from ashare_v3.ingestion.common import stable_raw_hash
from ashare_v3.ingestion.daily_bars import IndexDailySymbol
from ashare_v3.ingestion.mootdx_daily_source import MootdxDailyBarSource


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
TRADE_DATE = "20260526"
BATCH_ID = "official_daily_ingest_20260526_index_expansion_v1"
SOURCE_VERSION = "index_daily_20260526_v3"
PREVIOUS_SOURCE_VERSION = "index_daily_20260526_v2"
EXPECTED_ROWS = 83
MOOTDX_EXPECTED_ROWS = 81
TUSHARE_FALLBACK_EXPECTED_ROWS = 2
FIXED_9_INDEX_IDENTITIES = (
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
CANONICAL_IDENTITY_MAPPING = {
    "index:UNKNOWN:899050": "index:BJ:899050",
    "index:UNKNOWN:899601": "index:BJ:899601",
}
ALLOWED_FUTURE_WRITE_TABLES = (
    "common_ingest_batch",
    "common_quality_gate_result",
    "common_active_source_version",
    "index_daily_bar_fact",
)
FORBIDDEN_WRITE_TABLES = (
    "stock_daily_bar_fact",
    "board_daily_bar_fact",
    "stock_daily_basic",
    "stock_financial_metrics_fact",
    "index_membership_fact",
    "board_membership_fact",
    "condition source",
    "condition_* tables",
    "N2/N3/N4/N5/N6",
    "Parquet",
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "worker",
    "old system",
    "real trading",
)
DEFAULT_PATHS = {
    "contract_json": Path("docs/N1_index_daily_20260526_expansion_execute_contract.json"),
    "contract_md": Path("docs/N1_INDEX_DAILY_20260526_EXPANSION_EXECUTE_CONTRACT.md"),
    "preflight_json": Path("docs/N1_index_daily_20260526_expansion_execute_preflight.json"),
    "preflight_md": Path("docs/N1_INDEX_DAILY_20260526_EXPANSION_EXECUTE_PREFLIGHT.md"),
    "rollback_sql": Path("sql/N1_index_daily_20260526_expansion_rollback.sql"),
}


class IndexDaily20260526ExpansionBlocked(RuntimeError):
    """Raised when the 20260526 index_daily expansion gate is blocked."""


def now_iso() -> str:
    return datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat()


def validate_execute_request(*, execute_requested: bool, user_confirmed: bool, postgres_commit_enabled: bool) -> None:
    if not execute_requested:
        raise IndexDaily20260526ExpansionBlocked("missing --execute")
    if not user_confirmed:
        raise IndexDaily20260526ExpansionBlocked("missing --user-confirmed")
    if not postgres_commit_enabled:
        raise IndexDaily20260526ExpansionBlocked("missing --postgres-commit-enabled")


def sample_pass_snapshot() -> dict[str, Any]:
    return {
        "trade_date": TRADE_DATE,
        "active_source_version": PREVIOUS_SOURCE_VERSION,
        "active_source_batch_id": "official_daily_ingest_20260526_v2",
        "active_source_rows": 9,
        "existing_v3_rows": 0,
        "existing_v3_batch": 0,
        "existing_v3_quality_rows": 0,
        "event_counts": {"outbox": 74176, "inbox": 2952, "checkpoint": 2803},
        "read_only_database_checks": True,
    }


def build_snapshot_from_db(*, dsn: str, trade_date: str) -> dict[str, Any]:
    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=10) as conn:
        conn.execute("BEGIN TRANSACTION READ ONLY")
        active = conn.execute(
            """
            SELECT source_version, source_batch_id
            FROM common_active_source_version
            WHERE data_domain='index' AND data_type='index_daily' AND scope_key=%s
            """,
            (trade_date,),
        ).fetchone()
        active_version = active["source_version"] if active else None
        active_batch = active["source_batch_id"] if active else None
        snapshot = {
            "trade_date": trade_date,
            "active_source_version": active_version,
            "active_source_batch_id": active_batch,
            "active_source_rows": conn.execute(
                "SELECT count(*)::int AS c FROM index_daily_bar_fact WHERE trade_date=%s AND source_version=%s",
                (trade_date, active_version),
            ).fetchone()["c"]
            if active_version
            else 0,
            "existing_v3_rows": conn.execute(
                "SELECT count(*)::int AS c FROM index_daily_bar_fact WHERE trade_date=%s AND source_version=%s",
                (trade_date, SOURCE_VERSION),
            ).fetchone()["c"],
            "existing_v3_batch": conn.execute(
                "SELECT count(*)::int AS c FROM common_ingest_batch WHERE batch_id=%s",
                (BATCH_ID,),
            ).fetchone()["c"],
            "existing_v3_quality_rows": conn.execute(
                "SELECT count(*)::int AS c FROM common_quality_gate_result WHERE source_batch_id=%s OR source_version=%s",
                (BATCH_ID, SOURCE_VERSION),
            ).fetchone()["c"],
            "event_counts": {
                "outbox": conn.execute("SELECT count(*)::int AS c FROM common_event_outbox").fetchone()["c"],
                "inbox": conn.execute("SELECT count(*)::int AS c FROM common_event_inbox").fetchone()["c"],
                "checkpoint": conn.execute("SELECT count(*)::int AS c FROM common_event_consumer_checkpoint").fetchone()["c"],
            },
            "read_only_database_checks": True,
        }
        conn.execute("ROLLBACK")
        return snapshot


def build_expected_scope_from_db(*, dsn: str, trade_date: str) -> list[dict[str, Any]]:
    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=10) as conn:
        conn.execute("BEGIN TRANSACTION READ ONLY")
        membership_rows = conn.execute(
            """
            SELECT im.index_identity_key AS source_membership_identity_key,
                   ii.index_identity_key,
                   ii.ts_code,
                   ii.code,
                   ii.exchange,
                   ii.name,
                   ii.status,
                   count(*)::int AS members
            FROM index_membership_fact im
            LEFT JOIN index_identity ii ON ii.index_identity_key = im.index_identity_key
            WHERE im.trade_date = %s
            GROUP BY im.index_identity_key, ii.index_identity_key, ii.ts_code, ii.code, ii.exchange, ii.name, ii.status
            """,
            (trade_date,),
        ).fetchall()
        fixed_rows = conn.execute(
            """
            SELECT index_identity_key, index_identity_key AS source_membership_identity_key,
                   ts_code, code, exchange, name, status, 0::int AS members
            FROM index_identity
            WHERE index_identity_key = ANY(%s)
            """,
            (list(FIXED_9_INDEX_IDENTITIES),),
        ).fetchall()
        canonical_rows = conn.execute(
            """
            SELECT index_identity_key, index_identity_key AS source_membership_identity_key,
                   ts_code, code, exchange, name, status, 0::int AS members
            FROM index_identity
            WHERE index_identity_key = ANY(%s)
            """,
            (list(CANONICAL_IDENTITY_MAPPING.values()),),
        ).fetchall()
        conn.execute("ROLLBACK")

    rows_by_key: dict[str, dict[str, Any]] = {}
    for row in membership_rows + fixed_rows:
        item = dict(row)
        key = str(item.get("index_identity_key") or item.get("source_membership_identity_key"))
        rows_by_key[key] = item
    for source_key, canonical_key in CANONICAL_IDENTITY_MAPPING.items():
        if source_key in rows_by_key:
            source_item = rows_by_key.pop(source_key)
            canonical = next((dict(row) for row in canonical_rows if row["index_identity_key"] == canonical_key), None)
            if not canonical:
                raise IndexDaily20260526ExpansionBlocked(f"missing canonical identity for {source_key} -> {canonical_key}")
            canonical["source_membership_identity_key"] = source_key
            canonical["members"] = source_item.get("members", 0)
            rows_by_key[canonical_key] = canonical
    return [rows_by_key[key] for key in sorted(rows_by_key)]


class DefaultIndexDaily20260526ExpansionSourceAdapter:
    """Lazy real source adapter used only after explicit final execute flags."""

    def __init__(self, *, tushare_token: str | None = None, mootdx_offset: int = 800) -> None:
        self.tushare_token = tushare_token or load_tushare_token()
        self.mootdx_offset = mootdx_offset
        self._mootdx: MootdxDailyBarSource | None = None
        self._tushare_client: Any | None = None

    def fetch_mootdx_index_daily(self, *, trade_date: str, expected_scope: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for scope_row in expected_scope:
            symbol = IndexDailySymbol(
                code=str(scope_row["code"]),
                exchange=str(scope_row["exchange"]),
                name=scope_row.get("name"),
            )
            raw_rows = self._get_mootdx().fetch_index_daily_bars(indexes=[symbol], start_date=trade_date, end_date=trade_date)
            for raw in raw_rows:
                rows.append(normalize_source_row(raw, scope_row=scope_row, source_type="mootdx", source="mootdx.index"))
        return rows

    def fetch_tushare_index_daily_fallback(self, *, trade_date: str, missing_scope: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        pro = self._get_tushare()
        fields = "ts_code,trade_date,open,high,low,close,vol,amount"
        for scope_row in missing_scope:
            candidates = [value for value in (scope_row.get("ts_code"), f"{scope_row['code']}.{scope_row['exchange']}") if value]
            raw_rows: list[dict[str, Any]] = []
            for ts_code in dict.fromkeys(map(str, candidates)):
                frame = pro.index_daily(ts_code=ts_code, start_date=trade_date, end_date=trade_date, fields=fields)
                raw_rows = frame_to_records(frame)
                if raw_rows:
                    break
            for raw in raw_rows:
                rows.append(normalize_source_row(raw, scope_row=scope_row, source_type="tushare", source="tushare.index_daily.fallback"))
        return rows

    def _get_mootdx(self) -> MootdxDailyBarSource:
        if self._mootdx is None:
            self._mootdx = MootdxDailyBarSource(offset=self.mootdx_offset)
        return self._mootdx

    def _get_tushare(self) -> Any:
        if not self.tushare_token:
            raise IndexDaily20260526ExpansionBlocked("TUSHARE_TOKEN is required for BJ index fallback")
        if self._tushare_client is None:
            ts = importlib.import_module("tushare")
            ts.set_token(self.tushare_token)
            self._tushare_client = ts.pro_api(self.tushare_token)
        return self._tushare_client


def frame_to_records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        try:
            return [dict(record) for record in frame.to_dict(orient="records")]
        except TypeError:
            return [dict(record) for record in frame.to_dict("records")]
    if isinstance(frame, Mapping):
        return [dict(frame)]
    return [dict(record) for record in frame]


def normalize_source_row(raw: Mapping[str, Any], *, scope_row: Mapping[str, Any], source_type: str, source: str) -> dict[str, Any]:
    return {
        "index_identity_key": str(scope_row["index_identity_key"]),
        "trade_date": TRADE_DATE,
        "code": str(scope_row["code"]),
        "exchange": str(scope_row["exchange"]),
        "name": scope_row.get("name"),
        "open": decimal_from(raw.get("open")),
        "high": decimal_from(raw.get("high")),
        "low": decimal_from(raw.get("low")),
        "close": decimal_from(raw.get("close")),
        "volume": decimal_from(raw.get("vol", raw.get("volume"))),
        "amount": decimal_from(raw.get("amount")),
        "source": source,
        "source_type": source_type,
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSION,
        "raw_payload": json_safe(
            {
                **dict(raw),
                "source_type": source_type,
                "source_membership_identity_key": scope_row.get("source_membership_identity_key"),
            }
        ),
    }


def decimal_from(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(_sanitize_json(value), ensure_ascii=False, allow_nan=False))


def _sanitize_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_json(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Decimal):
        return float(value) if value.is_finite() else None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if hasattr(value, "item"):
        try:
            return _sanitize_json(value.item())
        except Exception:
            pass
    return str(value)


def build_source_bundle(
    *,
    adapter: Any,
    trade_date: str,
    expected_scope: list[dict[str, Any]],
    source_fetch_enabled: bool,
) -> dict[str, Any]:
    if not source_fetch_enabled:
        raise IndexDaily20260526ExpansionBlocked("source fetch disabled")
    mootdx_rows = list(adapter.fetch_mootdx_index_daily(trade_date=trade_date, expected_scope=expected_scope))
    mootdx_keys = {str(row["index_identity_key"]) for row in mootdx_rows}
    missing_scope = [row for row in expected_scope if str(row["index_identity_key"]) not in mootdx_keys]
    tushare_rows = list(adapter.fetch_tushare_index_daily_fallback(trade_date=trade_date, missing_scope=missing_scope))
    return {
        "rows": mootdx_rows + tushare_rows,
        "mootdx_rows": mootdx_rows,
        "tushare_fallback_rows": tushare_rows,
        "expected_scope": expected_scope,
    }


def validate_source_bundle(*, bundle: Mapping[str, Any], expected_scope: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [dict(row) for row in bundle.get("rows", [])]
    keys = [str(row.get("index_identity_key")) for row in rows]
    expected_keys = {str(row["index_identity_key"]) for row in expected_scope}
    row_key_set = set(keys)
    fixed_present = sorted(set(FIXED_9_INDEX_IDENTITIES) & row_key_set)
    missing_fixed = sorted(set(FIXED_9_INDEX_IDENTITIES) - row_key_set)
    unknown_writes = sorted(key for key in row_key_set if ":UNKNOWN:" in key)
    duplicate_count = len(keys) - len(row_key_set)
    missing = sorted(expected_keys - row_key_set)
    extra = sorted(row_key_set - expected_keys)
    mootdx_rows = [row for row in rows if str(row.get("source_type")) == "mootdx" or str(row.get("source")) == "mootdx.index"]
    tushare_rows = [row for row in rows if str(row.get("source_type")) == "tushare" or str(row.get("source")) == "tushare.index_daily.fallback"]
    p0: list[str] = []
    if len(rows) != EXPECTED_ROWS:
        p0.append(f"expected 83 rows, got {len(rows)}")
    if missing_fixed:
        p0.append(f"missing fixed 9 index rows: {missing_fixed}")
    if unknown_writes:
        p0.append(f"UNKNOWN identity writes are forbidden: {unknown_writes}")
    if duplicate_count:
        p0.append(f"duplicate identity_key rows: {duplicate_count}")
    if missing:
        p0.append(f"missing expected identities: {missing[:10]}")
    if extra:
        p0.append(f"unexpected identities: {extra[:10]}")
    if len(mootdx_rows) != MOOTDX_EXPECTED_ROWS:
        p0.append(f"expected {MOOTDX_EXPECTED_ROWS} Mootdx rows, got {len(mootdx_rows)}")
    if len(tushare_rows) != TUSHARE_FALLBACK_EXPECTED_ROWS:
        p0.append(f"expected {TUSHARE_FALLBACK_EXPECTED_ROWS} Tushare fallback rows, got {len(tushare_rows)}")
    if p0:
        raise IndexDaily20260526ExpansionBlocked("; ".join(p0))
    return {
        "p0_count": 0,
        "p1_count": 1,
        "p2_count": 0,
        "p1_items": [{"gate_name": "canonical_bj_mapping_from_tdx_unknown_membership", "rows": 2}],
        "row_count": len(rows),
        "mootdx_rows": len(mootdx_rows),
        "tushare_fallback_rows": len(tushare_rows),
        "tushare_fallback_identities": sorted(row["index_identity_key"] for row in tushare_rows),
        "fixed_9_present": fixed_present,
        "fixed_9_missing": missing_fixed,
        "unknown_writes": len(unknown_writes),
        "duplicate_identity_key": duplicate_count,
        "missing": missing,
        "canonical_mapping": dict(CANONICAL_IDENTITY_MAPPING),
    }


def validate_commit_preconditions(*, snapshot: Mapping[str, Any], validation_report: Mapping[str, Any], postgres_commit_enabled: bool) -> None:
    if not postgres_commit_enabled:
        raise IndexDaily20260526ExpansionBlocked("missing --postgres-commit-enabled")
    if snapshot.get("active_source_version") != PREVIOUS_SOURCE_VERSION:
        raise IndexDaily20260526ExpansionBlocked(f"active index_daily must be {PREVIOUS_SOURCE_VERSION}")
    if int(snapshot.get("existing_v3_rows") or 0) != 0:
        raise IndexDaily20260526ExpansionBlocked("existing index_daily_20260526_v3 rows")
    if int(snapshot.get("existing_v3_batch") or 0) != 0:
        raise IndexDaily20260526ExpansionBlocked("existing expansion batch")
    if int(snapshot.get("existing_v3_quality_rows") or 0) != 0:
        raise IndexDaily20260526ExpansionBlocked("existing expansion quality rows")
    if int(validation_report.get("p0_count") or 0) != 0:
        raise IndexDaily20260526ExpansionBlocked("source validation P0 > 0")


def build_commit_plan(*, bundle: Mapping[str, Any], validation_report: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    rows = [dict(row) for row in bundle["rows"]]
    quality_items = build_quality_items(validation_report)
    return {
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSION,
        "previous_source_version": PREVIOUS_SOURCE_VERSION,
        "trade_date": TRADE_DATE,
        "rows": rows,
        "quality_items": quality_items,
        "allowed_write_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
        "row_counts": {"index_daily_bar_fact": len(rows)},
        "active_source_version": {
            "data_domain": "index",
            "data_type": "index_daily",
            "scope_key": TRADE_DATE,
            "source_version": SOURCE_VERSION,
            "source_batch_id": BATCH_ID,
            "previous_source_version": PREVIOUS_SOURCE_VERSION,
            "activated_by": "n1_index_daily_20260526_expansion_execute_runner",
        },
        "batch": {
            "batch_id": BATCH_ID,
            "trade_date": TRADE_DATE,
            "data_domain": "index",
            "data_type": "index_daily",
            "source": "mootdx.index+tushare.index_daily.fallback",
            "source_version": SOURCE_VERSION,
            "source_params": {
                "trade_date": TRADE_DATE,
                "expected_rows": EXPECTED_ROWS,
                "previous_source_version": PREVIOUS_SOURCE_VERSION,
                "canonical_identity_mapping": dict(CANONICAL_IDENTITY_MAPPING),
            },
            "raw_hash": stable_raw_hash(rows),
            "row_count": len(rows),
            "error_count": 0,
            "quality_gate_summary": {
                "p0_count": validation_report["p0_count"],
                "p1_count": validation_report["p1_count"],
                "p2_count": validation_report["p2_count"],
            },
            "rollback_strategy": "sql/N1_index_daily_20260526_expansion_rollback.sql",
            "status": "passed",
        },
        "baseline": dict(baseline),
    }


def build_quality_items(validation_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    items = [
        ("index_daily_expansion_expected_rows", "P0", "passed", "83", str(validation_report["row_count"]), {}),
        ("index_daily_expansion_fixed_9_included", "P0", "passed", "9/9", f"{len(validation_report['fixed_9_present'])}/9", {}),
        ("index_daily_expansion_mootdx_rows", "P0", "passed", "81", str(validation_report["mootdx_rows"]), {}),
        ("index_daily_expansion_tushare_bj_fallback_rows", "P0", "passed", "2", str(validation_report["tushare_fallback_rows"]), {}),
        ("index_daily_expansion_unknown_writes", "P0", "passed", "0", str(validation_report["unknown_writes"]), {}),
        ("index_daily_expansion_duplicate_identity_key", "P0", "passed", "0", str(validation_report["duplicate_identity_key"]), {}),
        (
            "canonical_bj_mapping_from_tdx_unknown_membership",
            "P1",
            "warning",
            "2 canonical mappings",
            "2",
            {"mapping": dict(CANONICAL_IDENTITY_MAPPING)},
        ),
    ]
    return [
        {
            "data_domain": "index",
            "data_type": "index_daily",
            "source_batch_id": BATCH_ID,
            "source_version": SOURCE_VERSION,
            "gate_name": gate_name,
            "severity": severity,
            "status": status,
            "expected_value": expected,
            "actual_value": actual,
            "details": details,
        }
        for gate_name, severity, status, expected, actual, details in items
    ]


def execute_commit_transaction(
    conn: Any,
    *,
    commit_plan: Mapping[str, Any],
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    validate_execute_request(
        execute_requested=execute_requested,
        user_confirmed=user_confirmed,
        postgres_commit_enabled=postgres_commit_enabled,
    )
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN")
        batch = commit_plan["batch"]
        cursor.execute(
            """
            INSERT INTO common_ingest_batch
              (batch_id, trade_date, data_domain, data_type, source, source_version, source_path,
               source_params, raw_hash, row_count, error_count, quality_gate_summary,
               error_summary, rollback_strategy, status, started_at, finished_at)
            VALUES (%s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, %s, %s, NULL, %s, %s, now(), now())
            """,
            (
                batch["batch_id"],
                batch["trade_date"],
                batch["data_domain"],
                batch["data_type"],
                batch["source"],
                batch["source_version"],
                Jsonb(batch["source_params"]),
                batch["raw_hash"],
                batch["row_count"],
                batch["error_count"],
                Jsonb(batch["quality_gate_summary"]),
                batch["rollback_strategy"],
                batch["status"],
            ),
        )
        cursor.executemany(
            """
            INSERT INTO index_daily_bar_fact
              (index_identity_key, trade_date, code, exchange, name, open, high, low, close,
               volume, amount, source, source_batch_id, source_version, raw_payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
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
                    BATCH_ID,
                    SOURCE_VERSION,
                    Jsonb(json_safe(row.get("raw_payload") or {})),
                )
                for row in commit_plan["rows"]
            ),
        )
        cursor.executemany(
            """
            INSERT INTO common_quality_gate_result
              (data_domain, data_type, source_batch_id, source_version, gate_name,
               severity, status, expected_value, actual_value, details)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                (
                    item["data_domain"],
                    item["data_type"],
                    item["source_batch_id"],
                    item["source_version"],
                    item["gate_name"],
                    item["severity"],
                    item["status"],
                    item["expected_value"],
                    item["actual_value"],
                    Jsonb(json_safe(item.get("details") or {})),
                )
                for item in commit_plan["quality_items"]
            ),
        )
        active = commit_plan["active_source_version"]
        cursor.execute(
            """
            UPDATE common_active_source_version
            SET source_version=%s,
                source_batch_id=%s,
                previous_source_version=%s,
                activated_at=now(),
                activated_by=%s
            WHERE data_domain=%s AND data_type=%s AND scope_key=%s
            """,
            (
                active["source_version"],
                active["source_batch_id"],
                active["previous_source_version"],
                active["activated_by"],
                active["data_domain"],
                active["data_type"],
                active["scope_key"],
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "result": "COMMIT_PASS",
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSION,
        "row_counts": dict(commit_plan["row_counts"]),
        "active_source_version": dict(commit_plan["active_source_version"]),
        "allowed_write_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
    }


def build_execute_contract(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stage": "N1 index_daily 20260526 universe expansion execute contract",
        "layer_role": "N1_ingestion",
        "result": "DESIGN_PASS",
        "runner_readiness": "ready_for_final_gate",
        "execute_authorized": False,
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSION,
        "previous_source_version": PREVIOUS_SOURCE_VERSION,
        "expected_rows": {"index_daily_bar_fact": EXPECTED_ROWS},
        "current_active_source_version": snapshot.get("active_source_version"),
        "future_write_scope": {"allowed_tables": list(ALLOWED_FUTURE_WRITE_TABLES), "forbidden_tables": list(FORBIDDEN_WRITE_TABLES)},
        "rollback_sql_path": str(DEFAULT_PATHS["rollback_sql"]),
    }


def build_execute_preflight_report(
    snapshot: Mapping[str, Any],
    *,
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    blockers: list[str] = []
    if snapshot.get("active_source_version") != PREVIOUS_SOURCE_VERSION:
        blockers.append("active_source_version_not_v2")
    if int(snapshot.get("existing_v3_rows") or 0) != 0:
        blockers.append("existing_v3_rows")
    if int(snapshot.get("existing_v3_batch") or 0) != 0:
        blockers.append("existing_v3_batch")
    if int(snapshot.get("existing_v3_quality_rows") or 0) != 0:
        blockers.append("existing_v3_quality_rows")
    return {
        "stage": "N1 index_daily 20260526 universe expansion execute preflight",
        "layer_role": "N1_ingestion",
        "result": "PREFLIGHT_PASS" if not blockers else "PREFLIGHT_BLOCKED",
        "blocked": bool(blockers),
        "blockers": blockers,
        "runner_readiness": "ready_for_final_gate" if not blockers else "blocked",
        "final_execute_gate_allowed": not blockers,
        "execute_authorized": bool(execute_requested and user_confirmed and postgres_commit_enabled and not blockers),
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSION,
        "previous_source_version": PREVIOUS_SOURCE_VERSION,
        "baseline": dict(snapshot),
        "expected": {
            "index_daily_bar_fact_rows": EXPECTED_ROWS,
            "mootdx_rows": MOOTDX_EXPECTED_ROWS,
            "tushare_fallback_bj_rows": TUSHARE_FALLBACK_EXPECTED_ROWS,
            "unknown_writes": 0,
            "duplicate_identity_key": 0,
        },
        "quality": {"p0_count": 0 if not blockers else len(blockers), "p1_count": 1, "p2_count": 0},
        "future_write_scope": {"allowed_tables": list(ALLOWED_FUTURE_WRITE_TABLES), "forbidden_tables": list(FORBIDDEN_WRITE_TABLES)},
        "side_effects": {
            "writes_postgres": False,
            "updates_active_source_version": False,
            "writes_parquet": False,
            "writes_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "enters_n2_n3_n4_n5_n6": False,
            "worker_started": False,
            "old_system_touched": False,
            "real_trading": False,
        },
        "rollback_sql_path": str(DEFAULT_PATHS["rollback_sql"]),
    }


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_contract_files(contract: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    write_json(json_path, contract)
    Path(markdown_path).write_text(
        "\n".join(
            [
                "# N1 Index Daily 20260526 Expansion Execute Contract",
                "",
                "状态：`DESIGN_PASS`",
                "",
                "```text",
                f"source_batch_id = {BATCH_ID}",
                f"source_version = {SOURCE_VERSION}",
                f"previous_source_version = {PREVIOUS_SOURCE_VERSION}",
                f"expected_rows = {EXPECTED_ROWS}",
                "runner_readiness = ready_for_final_gate",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_preflight_files(preflight: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    write_json(json_path, preflight)
    Path(markdown_path).write_text(
        "\n".join(
            [
                "# N1 Index Daily 20260526 Expansion Execute Preflight",
                "",
                f"状态：`{preflight['result']}`",
                "",
                "```text",
                f"runner_readiness = {preflight['runner_readiness']}",
                f"final_execute_gate_allowed = {str(preflight['final_execute_gate_allowed']).lower()}",
                f"expected_rows = {EXPECTED_ROWS}",
                "P0/P1/P2 = 0/1/0",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
