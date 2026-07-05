"""Execute runner support for N1 stock_identity refresh on 20260527.

This module is safe to import and unit test. Real Tushare fetch and
PostgreSQL writes only happen when the run-once CLI receives all explicit
final-gate flags.
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
from ashare_v3.ingestion.common import normalize_exchange_from_ts_code, stable_raw_hash
from ashare_v3.ingestion.tushare_source import TushareStockSource


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
TRADE_DATE = "20260527"
BATCH_ID = "stock_identity_refresh_20260527_v1"
SOURCE_VERSION = "stock_identity_20260527_v1"
PREVIOUS_SOURCE_VERSION = "stock_identity_20260522_v1"
ACTIVE_SCOPE_KEY = "A_STOCK:20260527"
EXPECTED_TS_CODES = ("688635.SH", "920161.BJ")
EXPECTED_IDENTITIES = {
    "stock:SH:688635": {
        "ts_code": "688635.SH",
        "code": "688635",
        "exchange": "SH",
        "name": "长进光子",
        "area": "湖北",
        "industry": "通信设备",
        "market": "科创板",
        "listed_date": TRADE_DATE,
    },
    "stock:BJ:920161": {
        "ts_code": "920161.BJ",
        "code": "920161",
        "exchange": "BJ",
        "name": "龙辰科技",
        "area": "湖北",
        "industry": "元器件",
        "market": "北交所",
        "listed_date": TRADE_DATE,
    },
}
STALE_IDENTITY_MANIFEST = {
    "identity_key": "stock:SZ:300114",
    "superseded_by": "stock:SZ:302132",
    "decision": "not_modified_in_this_gate",
    "severity": "P1",
}
ALLOWED_FUTURE_WRITE_TABLES = (
    "stock_identity",
    "common_ingest_batch",
    "common_quality_gate_result",
    "common_active_source_version",
)
FORBIDDEN_WRITE_TABLES = (
    "stock_daily_bar_fact",
    "index_daily_bar_fact",
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
    "contract_json": Path("docs/N1_stock_identity_20260527_refresh_execute_contract.json"),
    "contract_md": Path("docs/N1_STOCK_IDENTITY_20260527_REFRESH_EXECUTE_CONTRACT.md"),
    "preflight_json": Path("docs/N1_stock_identity_20260527_refresh_execute_preflight.json"),
    "preflight_md": Path("docs/N1_STOCK_IDENTITY_20260527_REFRESH_EXECUTE_PREFLIGHT.md"),
    "rollback_sql": Path("sql/N1_stock_identity_20260527_refresh_rollback.sql"),
}


class StockIdentity20260527RefreshBlocked(RuntimeError):
    """Raised when the 20260527 stock_identity refresh gate is blocked."""


def now_iso() -> str:
    return datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat()


def validate_execute_request(
    *,
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> None:
    if not execute_requested:
        raise StockIdentity20260527RefreshBlocked("missing --execute")
    if not user_confirmed:
        raise StockIdentity20260527RefreshBlocked("missing --user-confirmed")
    if not postgres_commit_enabled:
        raise StockIdentity20260527RefreshBlocked("missing --postgres-commit-enabled")


def sample_pass_snapshot() -> dict[str, Any]:
    return {
        "trade_date": TRADE_DATE,
        "target_stock_identity_rows": 0,
        "target_ts_code_rows": 0,
        "source_version_identity_rows": 0,
        "batch_conflict_count": 0,
        "quality_conflict_count": 0,
        "existing_active_scope_key_count": 0,
        "latest_previous_active_source_version": PREVIOUS_SOURCE_VERSION,
        "daily_fact_rows": {"stock": 0, "index": 0, "board": 0},
        "event_counts": {"outbox": 74176, "inbox": 2952, "checkpoint": 2803},
        "read_only_database_checks": True,
    }


def build_snapshot_from_db(*, dsn: str, trade_date: str = TRADE_DATE) -> dict[str, Any]:
    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=10) as conn:
        conn.execute("BEGIN TRANSACTION READ ONLY")
        target_keys = list(EXPECTED_IDENTITIES)
        target_ts_codes = list(EXPECTED_TS_CODES)
        previous_active = conn.execute(
            """
            SELECT source_version
            FROM common_active_source_version
            WHERE data_domain='stock' AND data_type='stock_identity'
            ORDER BY activated_at DESC NULLS LAST, created_at DESC NULLS LAST
            LIMIT 1
            """
        ).fetchone()
        snapshot = {
            "trade_date": trade_date,
            "target_stock_identity_rows": conn.execute(
                "SELECT count(*)::int AS c FROM stock_identity WHERE stock_identity_key = ANY(%s)",
                (target_keys,),
            ).fetchone()["c"],
            "target_ts_code_rows": conn.execute(
                "SELECT count(*)::int AS c FROM stock_identity WHERE ts_code = ANY(%s)",
                (target_ts_codes,),
            ).fetchone()["c"],
            "source_version_identity_rows": conn.execute(
                "SELECT count(*)::int AS c FROM stock_identity WHERE source_batch_id=%s OR source_version=%s",
                (BATCH_ID, SOURCE_VERSION),
            ).fetchone()["c"],
            "batch_conflict_count": conn.execute(
                "SELECT count(*)::int AS c FROM common_ingest_batch WHERE batch_id=%s OR source_version=%s",
                (BATCH_ID, SOURCE_VERSION),
            ).fetchone()["c"],
            "quality_conflict_count": conn.execute(
                "SELECT count(*)::int AS c FROM common_quality_gate_result WHERE source_batch_id=%s OR source_version=%s",
                (BATCH_ID, SOURCE_VERSION),
            ).fetchone()["c"],
            "existing_active_scope_key_count": conn.execute(
                """
                SELECT count(*)::int AS c
                FROM common_active_source_version
                WHERE data_domain='stock' AND data_type='stock_identity' AND scope_key=%s
                """,
                (ACTIVE_SCOPE_KEY,),
            ).fetchone()["c"],
            "latest_previous_active_source_version": previous_active["source_version"] if previous_active else PREVIOUS_SOURCE_VERSION,
            "daily_fact_rows": {
                "stock": conn.execute(
                    "SELECT count(*)::int AS c FROM stock_daily_bar_fact WHERE trade_date=%s AND source_batch_id=%s",
                    (trade_date, BATCH_ID),
                ).fetchone()["c"],
                "index": conn.execute(
                    "SELECT count(*)::int AS c FROM index_daily_bar_fact WHERE trade_date=%s AND source_batch_id=%s",
                    (trade_date, BATCH_ID),
                ).fetchone()["c"],
                "board": conn.execute(
                    "SELECT count(*)::int AS c FROM board_daily_bar_fact WHERE trade_date=%s AND source_batch_id=%s",
                    (trade_date, BATCH_ID),
                ).fetchone()["c"],
            },
            "event_counts": {
                "outbox": conn.execute("SELECT count(*)::int AS c FROM common_event_outbox").fetchone()["c"],
                "inbox": conn.execute("SELECT count(*)::int AS c FROM common_event_inbox").fetchone()["c"],
                "checkpoint": conn.execute("SELECT count(*)::int AS c FROM common_event_consumer_checkpoint").fetchone()["c"],
            },
            "read_only_database_checks": True,
        }
        conn.execute("ROLLBACK")
        return snapshot


class DefaultStockIdentity20260527RefreshSourceAdapter:
    """Lazy Tushare adapter used only after explicit final execute flags."""

    def __init__(self, *, token: str | None = None) -> None:
        self.token = token or load_tushare_token() or ""
        self._source: TushareStockSource | None = None

    def fetch_stock_basic(self, *, trade_date: str, ts_codes: tuple[str, ...] = EXPECTED_TS_CODES) -> list[dict[str, Any]]:
        if not self.token:
            raise StockIdentity20260527RefreshBlocked("TUSHARE_TOKEN is required")
        if self._source is None:
            self._source = TushareStockSource(token=self.token, symbols=ts_codes)
        return [dict(row) for row in self._source.fetch_stock_basic(asof_date=trade_date)]


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


def identity_key_from_ts_code(ts_code: str) -> tuple[str, str, str]:
    exchange, code = normalize_exchange_from_ts_code(str(ts_code).strip().upper())
    return f"stock:{exchange}:{code}", exchange, code


def build_target_identity_rows(stock_basic_rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows_by_ts_code: dict[str, dict[str, Any]] = {}
    duplicate_ts_codes = [ts_code for ts_code, count in Counter(str(row.get("ts_code") or "").strip().upper() for row in stock_basic_rows).items() if ts_code and count > 1]
    if duplicate_ts_codes:
        raise StockIdentity20260527RefreshBlocked(f"duplicate stock_basic ts_code rows: {duplicate_ts_codes}")

    for raw in stock_basic_rows:
        ts_code = str(raw.get("ts_code") or "").strip().upper()
        if ts_code in EXPECTED_TS_CODES:
            rows_by_ts_code[ts_code] = dict(raw)

    missing = sorted(set(EXPECTED_TS_CODES) - set(rows_by_ts_code))
    if missing:
        raise StockIdentity20260527RefreshBlocked(f"missing target stock_basic rows: {missing}")

    identity_rows: list[dict[str, Any]] = []
    for ts_code in EXPECTED_TS_CODES:
        raw = rows_by_ts_code[ts_code]
        list_date = str(raw.get("list_date") or "").strip()
        if list_date != TRADE_DATE:
            raise StockIdentity20260527RefreshBlocked(f"{ts_code} list_date must be {TRADE_DATE}, got {list_date}")
        identity_key, exchange, code = identity_key_from_ts_code(ts_code)
        expected = EXPECTED_IDENTITIES[identity_key]
        name = str(raw.get("name") or expected["name"]).strip()
        row = {
            "stock_identity_key": identity_key,
            "ts_code": ts_code,
            "code": str(raw.get("symbol") or code).strip(),
            "exchange": exchange,
            "name": name,
            "display_code": code,
            "area": _none_if_empty(raw.get("area")),
            "industry": _none_if_empty(raw.get("industry")),
            "market": _none_if_empty(raw.get("market")),
            "listed_date": list_date,
            "delisted_date": _none_if_empty(raw.get("delist_date")),
            "is_st": is_st_name(name),
            "status": "active" if str(raw.get("list_status") or "L").strip().upper() == "L" else "inactive",
            "source": "tushare.stock_basic.refresh",
            "source_batch_id": BATCH_ID,
            "source_version": SOURCE_VERSION,
            "raw_payload": json_safe(
                {
                    **dict(raw),
                    "identity_refresh_gate": BATCH_ID,
                    "canonical_identity_key": identity_key,
                }
            ),
        }
        if row["code"] != code:
            raise StockIdentity20260527RefreshBlocked(f"{ts_code} symbol/code mismatch: {row['code']} != {code}")
        if row["status"] != "active":
            raise StockIdentity20260527RefreshBlocked(f"{ts_code} list_status must be L/active")
        identity_rows.append(row)

    keys = [row["stock_identity_key"] for row in identity_rows]
    if len(keys) != len(set(keys)):
        raise StockIdentity20260527RefreshBlocked("duplicate identity_key in target rows")
    return identity_rows


def _none_if_empty(value: Any) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def is_st_name(name: str) -> bool:
    text = name.strip().upper()
    return text.startswith("ST") or text.startswith("*ST")


def validate_source_rows(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    identity_keys = [str(row.get("stock_identity_key") or "") for row in rows]
    ts_codes = [str(row.get("ts_code") or "") for row in rows]
    p0: list[str] = []
    if len(rows) != 2:
        p0.append(f"expected 2 stock_identity rows, got {len(rows)}")
    missing_identity = sorted(set(EXPECTED_IDENTITIES) - set(identity_keys))
    if missing_identity:
        p0.append(f"missing expected identity_key rows: {missing_identity}")
    duplicate_identity = len(identity_keys) - len(set(identity_keys))
    duplicate_ts_code = len(ts_codes) - len(set(ts_codes))
    if duplicate_identity:
        p0.append(f"duplicate identity_key rows: {duplicate_identity}")
    if duplicate_ts_code:
        p0.append(f"duplicate ts_code rows: {duplicate_ts_code}")
    if any(key == STALE_IDENTITY_MANIFEST["identity_key"] for key in identity_keys):
        p0.append("stale stock:SZ:300114 must not be modified in this gate")
    wrong_list_dates = [row["ts_code"] for row in rows if str(row.get("listed_date") or "") != TRADE_DATE]
    if wrong_list_dates:
        p0.append(f"wrong list_date rows: {wrong_list_dates}")
    if p0:
        raise StockIdentity20260527RefreshBlocked("; ".join(p0))
    return {
        "p0_count": 0,
        "p1_count": 1,
        "p2_count": 0,
        "row_count": len(rows),
        "duplicate_identity_key": duplicate_identity,
        "duplicate_ts_code": duplicate_ts_code,
        "new_identity_keys": sorted(identity_keys),
        "new_ts_codes": sorted(ts_codes),
        "stale_identity_handling": dict(STALE_IDENTITY_MANIFEST),
        "p1_items": [{"gate_name": "stale_identity_not_modified", **dict(STALE_IDENTITY_MANIFEST)}],
    }


def validate_commit_preconditions(
    *,
    snapshot: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    postgres_commit_enabled: bool,
) -> None:
    if not postgres_commit_enabled:
        raise StockIdentity20260527RefreshBlocked("missing --postgres-commit-enabled")
    if int(snapshot.get("target_stock_identity_rows") or 0) != 0:
        raise StockIdentity20260527RefreshBlocked("existing target stock_identity rows")
    if int(snapshot.get("target_ts_code_rows") or 0) != 0:
        raise StockIdentity20260527RefreshBlocked("existing target ts_code rows")
    if int(snapshot.get("source_version_identity_rows") or 0) != 0:
        raise StockIdentity20260527RefreshBlocked("existing stock_identity rows for this source_version")
    if int(snapshot.get("batch_conflict_count") or 0) != 0:
        raise StockIdentity20260527RefreshBlocked("existing batch/source_version conflict")
    if int(snapshot.get("quality_conflict_count") or 0) != 0:
        raise StockIdentity20260527RefreshBlocked("existing quality rows")
    if int(snapshot.get("existing_active_scope_key_count") or 0) != 0:
        raise StockIdentity20260527RefreshBlocked("existing active source_version for A_STOCK:20260527")
    daily_fact_rows = snapshot.get("daily_fact_rows") or {}
    if any(int(value or 0) != 0 for value in daily_fact_rows.values()):
        raise StockIdentity20260527RefreshBlocked("this identity refresh gate must not own daily fact rows")
    if int(validation_report.get("p0_count") or 0) != 0:
        raise StockIdentity20260527RefreshBlocked("source validation P0 > 0")


def build_commit_plan(*, rows: list[Mapping[str, Any]], validation_report: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    identity_rows = [dict(row) for row in rows]
    previous_source_version = str(baseline.get("latest_previous_active_source_version") or PREVIOUS_SOURCE_VERSION)
    quality_items = build_quality_items(validation_report)
    return {
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSION,
        "previous_source_version": previous_source_version,
        "trade_date": TRADE_DATE,
        "rows": identity_rows,
        "quality_items": quality_items,
        "allowed_write_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
        "row_counts": {
            "stock_identity": len(identity_rows),
            "common_ingest_batch": 1,
            "common_active_source_version": 1,
            "common_quality_gate_result": len(quality_items),
        },
        "active_source_version": {
            "data_domain": "stock",
            "data_type": "stock_identity",
            "scope_key": ACTIVE_SCOPE_KEY,
            "source_version": SOURCE_VERSION,
            "source_batch_id": BATCH_ID,
            "previous_source_version": previous_source_version,
            "activated_by": "n1_stock_identity_20260527_refresh_execute_runner",
        },
        "batch": {
            "batch_id": BATCH_ID,
            "trade_date": TRADE_DATE,
            "data_domain": "stock",
            "data_type": "stock_identity",
            "source": "tushare.stock_basic.refresh",
            "source_version": SOURCE_VERSION,
            "source_params": {
                "trade_date": TRADE_DATE,
                "target_ts_codes": list(EXPECTED_TS_CODES),
                "stale_identity_modified": False,
                "stale_identity_manifest": dict(STALE_IDENTITY_MANIFEST),
            },
            "raw_hash": stable_raw_hash(identity_rows),
            "row_count": len(identity_rows),
            "error_count": 0,
            "quality_gate_summary": {
                "p0_count": validation_report["p0_count"],
                "p1_count": validation_report["p1_count"],
                "p2_count": validation_report["p2_count"],
                "stale_identity_not_modified": True,
            },
            "rollback_strategy": str(DEFAULT_PATHS["rollback_sql"]),
            "status": "passed",
        },
        "baseline": dict(baseline),
    }


def build_quality_items(validation_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    items = [
        ("target_stock_basic_rows_present", "P0", "passed", "2", str(validation_report["row_count"]), {"target_ts_codes": list(EXPECTED_TS_CODES)}),
        ("target_list_date_20260527", "P0", "passed", "2", "2", {"trade_date": TRADE_DATE}),
        ("duplicate_identity_key", "P0", "passed", "0", str(validation_report["duplicate_identity_key"]), {}),
        ("duplicate_ts_code", "P0", "passed", "0", str(validation_report["duplicate_ts_code"]), {}),
        (
            "stale_identity_not_modified",
            "P1",
            "warning",
            "record manifest only",
            "not_modified",
            {"manifest": dict(STALE_IDENTITY_MANIFEST)},
        ),
        ("daily_fact_write_guard", "P0", "passed", "0 daily fact writes", "0", {}),
    ]
    return [
        {
            "data_domain": "stock",
            "data_type": "stock_identity",
            "source_batch_id": BATCH_ID,
            "source_version": SOURCE_VERSION,
            "gate_name": gate_name,
            "severity": severity,
            "status": status,
            "expected_value": expected,
            "actual_value": actual,
            "details": json_safe(details),
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
                Jsonb(json_safe(batch["source_params"])),
                batch["raw_hash"],
                batch["row_count"],
                batch["error_count"],
                Jsonb(json_safe(batch["quality_gate_summary"])),
                batch["rollback_strategy"],
                batch["status"],
            ),
        )
        cursor.executemany(
            """
            INSERT INTO stock_identity
              (stock_identity_key, ts_code, code, exchange, name, display_code, area, industry,
               market, listed_date, delisted_date, is_st, status, source, source_batch_id,
               source_version, raw_payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
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
                    row["is_st"],
                    row["status"],
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
            INSERT INTO common_active_source_version
              (data_domain, data_type, scope_key, source_version, source_batch_id,
               previous_source_version, activated_at, activated_by)
            VALUES (%s, %s, %s, %s, %s, %s, now(), %s)
            """,
            (
                active["data_domain"],
                active["data_type"],
                active["scope_key"],
                active["source_version"],
                active["source_batch_id"],
                active["previous_source_version"],
                active["activated_by"],
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
        "rollback_safe": True,
        "rollback_sql_path": str(DEFAULT_PATHS["rollback_sql"]),
    }


def build_execute_contract(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    blockers = build_preflight_blockers(snapshot)
    return {
        "stage": "N1 stock_identity 20260527 refresh execute contract",
        "layer_role": "N1_ingestion",
        "result": "DESIGN_PASS",
        "trade_date": TRADE_DATE,
        "runner_readiness": "ready_for_final_gate" if not blockers else "blocked",
        "execute_authorized": False,
        "final_execute_gate_allowed": not blockers,
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSION,
        "previous_source_version": str(snapshot.get("latest_previous_active_source_version") or PREVIOUS_SOURCE_VERSION),
        "active_scope_key": ACTIVE_SCOPE_KEY,
        "expected_rows": {
            "stock_identity_insert_rows": 2,
            "common_ingest_batch_rows": 1,
            "common_active_source_version_rows": 1,
        },
        "new_identity_rows": [public_identity_row(EXPECTED_IDENTITIES[key]) for key in sorted(EXPECTED_IDENTITIES)],
        "stale_identity_decision": {STALE_IDENTITY_MANIFEST["identity_key"]: STALE_IDENTITY_MANIFEST["decision"]},
        "execute_flags": ["--execute", "--user-confirmed", "--postgres-commit-enabled"],
        "future_write_scope": {
            "allowed_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
            "forbidden_tables": list(FORBIDDEN_WRITE_TABLES),
            "single_transaction": True,
            "postgres_only": True,
            "writes_parquet": False,
        },
        "idempotency": {
            "block_existing_batch_id": True,
            "block_existing_source_version": True,
            "block_existing_target_identity_key": True,
            "block_existing_target_ts_code": True,
            "block_existing_active_scope_key": True,
        },
        "quality_gate": {
            "p0_must_equal_zero": True,
            "expected_p0_p1_p2": {"p0": 0, "p1": 1, "p2": 0},
        },
        "rollback": {
            "path": str(DEFAULT_PATHS["rollback_sql"]),
            "strategy": "delete this batch's stock_identity rows and this batch/quality/active metadata only",
            "do_not_touch_historical_identity_rows": True,
            "do_not_touch_daily_fact": True,
            "do_not_touch_stale_300114": True,
            "do_not_touch_outbox_or_n2_n6": True,
        },
        "implementation_status": {
            "execute_runner_implemented": True,
            "execute_authorized": False,
            "final_execute_gate_allowed": not blockers,
            "next_gate": "final_execute_gate" if not blockers else "resolve_preflight_blockers",
        },
    }


def public_identity_row(expected: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stock_identity_key": f"stock:{expected['exchange']}:{expected['code']}",
        "ts_code": expected["ts_code"],
        "code": expected["code"],
        "exchange": expected["exchange"],
        "name": expected["name"],
        "area": expected["area"],
        "industry": expected["industry"],
        "market": expected["market"],
        "listed_date": expected["listed_date"],
        "delisted_date": None,
        "is_st": False,
        "status": "active",
    }


def build_execute_preflight_report(
    snapshot: Mapping[str, Any],
    *,
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    blockers = build_preflight_blockers(snapshot)
    result = "PREFLIGHT_PASS" if not blockers else "PREFLIGHT_BLOCKED"
    return {
        "stage": "N1 stock_identity 20260527 refresh execute preflight",
        "layer_role": "N1_ingestion",
        "result": result,
        "blocked": bool(blockers),
        "blockers": blockers,
        "trade_date": TRADE_DATE,
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSION,
        "previous_source_version": str(snapshot.get("latest_previous_active_source_version") or PREVIOUS_SOURCE_VERSION),
        "active_scope_key": ACTIVE_SCOPE_KEY,
        "runner_readiness": "ready_for_final_gate" if not blockers else "blocked",
        "final_execute_gate_allowed": not blockers,
        "execute_authorized": bool(execute_requested and user_confirmed and postgres_commit_enabled and not blockers),
        "baseline": dict(snapshot),
        "expected_rows": {
            "stock_identity_insert_rows": 2,
            "common_ingest_batch_rows": 1,
            "common_active_source_version_rows": 1,
        },
        "quality": {
            "p0_count": 0 if not blockers else len(blockers),
            "p1_count": 1,
            "p2_count": 0,
            "p1_items": [{"gate_name": "stale_identity_not_modified", **dict(STALE_IDENTITY_MANIFEST)}],
        },
        "execute_runner": {
            "implemented": True,
            "runner_readiness": "ready_for_final_gate" if not blockers else "blocked",
            "final_execute_gate_allowed": not blockers,
            "execute_authorized": bool(execute_requested and user_confirmed and postgres_commit_enabled and not blockers),
        },
        "future_write_scope": {
            "allowed_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
            "forbidden_tables": list(FORBIDDEN_WRITE_TABLES),
        },
        "rollback": {"path": str(DEFAULT_PATHS["rollback_sql"]), "rollback_safe": True},
        "side_effects": {
            "writes_postgres": False,
            "updates_active_source_version": False,
            "writes_daily_fact": False,
            "writes_parquet": False,
            "writes_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "enters_n2_n3_n4_n5_n6": False,
            "worker_started": False,
            "old_system_touched": False,
            "real_trading": False,
        },
    }


def build_preflight_blockers(snapshot: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if int(snapshot.get("target_stock_identity_rows") or 0) != 0:
        blockers.append("target_stock_identity_exists")
    if int(snapshot.get("target_ts_code_rows") or 0) != 0:
        blockers.append("target_ts_code_exists")
    if int(snapshot.get("source_version_identity_rows") or 0) != 0:
        blockers.append("source_version_identity_rows_exist")
    if int(snapshot.get("batch_conflict_count") or 0) != 0:
        blockers.append("batch_source_version_conflict")
    if int(snapshot.get("quality_conflict_count") or 0) != 0:
        blockers.append("quality_conflict")
    if int(snapshot.get("existing_active_scope_key_count") or 0) != 0:
        blockers.append("active_scope_key_conflict")
    daily_fact_rows = snapshot.get("daily_fact_rows") or {}
    if any(int(value or 0) != 0 for value in daily_fact_rows.values()):
        blockers.append("unexpected_daily_fact_rows_for_identity_batch")
    return blockers


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(_sanitize_json(value), ensure_ascii=False, allow_nan=False))


def _sanitize_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_json(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Decimal):
        return float(value) if value.is_finite() else None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item"):
        try:
            return _sanitize_json(value.item())
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    Path(path).write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_contract_files(contract: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    write_json(json_path, contract)
    Path(markdown_path).write_text(
        "\n".join(
            [
                "# N1 Stock Identity 20260527 Refresh Execute Contract",
                "",
                "状态：`DESIGN_PASS`",
                "",
                "```text",
                f"source_batch_id = {BATCH_ID}",
                f"source_version = {SOURCE_VERSION}",
                f"active_scope_key = {ACTIVE_SCOPE_KEY}",
                "runner_readiness = ready_for_final_gate",
                "expected_stock_identity_insert_rows = 2",
                "P0/P1/P2 = 0/1/0",
                "```",
                "",
                "本 runner 只允许写 stock_identity、common_ingest_batch、common_quality_gate_result、common_active_source_version。",
                "stale identity stock:SZ:300114 仅记录 manifest，本 gate 不修改。",
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
                "# N1 Stock Identity 20260527 Refresh Execute Preflight",
                "",
                f"状态：`{preflight['result']}`",
                "",
                "```text",
                f"runner_readiness = {preflight['runner_readiness']}",
                f"final_execute_gate_allowed = {str(preflight['final_execute_gate_allowed']).lower()}",
                f"source_batch_id = {BATCH_ID}",
                f"source_version = {SOURCE_VERSION}",
                "expected_stock_identity_insert_rows = 2",
                "P0/P1/P2 = 0/1/0",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
