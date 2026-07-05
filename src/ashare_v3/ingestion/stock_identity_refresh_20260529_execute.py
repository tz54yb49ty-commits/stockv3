"""Execute runner support for N1 stock_identity refresh on 20260529.

This module is safe to import and unit test. PostgreSQL writes only happen
when the run-once CLI receives both explicit final-gate flags.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
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


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
TRADE_DATE = "20260529"
BATCH_ID = "stock_identity_refresh_20260529_v1"
SOURCE_VERSION = "stock_identity_20260529_v1"
PREVIOUS_SOURCE_VERSION = "stock_identity_20260527_v1"
PREVIOUS_SOURCE_BATCH_ID = "stock_identity_refresh_20260527_v1"
ACTIVE_SCOPE_KEY = "A_STOCK:20260529"
EXPECTED_TS_CODE = "920218.BJ"
EXPECTED_IDENTITY_KEY = "stock:BJ:920218"
EXPECTED_IDENTITY = {
    "stock_identity_key": EXPECTED_IDENTITY_KEY,
    "ts_code": EXPECTED_TS_CODE,
    "code": "920218",
    "exchange": "BJ",
    "name": "新天力",
    "area": "浙江",
    "industry": "塑料",
    "market": "北交所",
    "listed_date": TRADE_DATE,
    "status": "active",
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
    "contract_json": Path("docs/N1_stock_identity_refresh_20260529_execute_contract.json"),
    "contract_md": Path("docs/N1_STOCK_IDENTITY_REFRESH_20260529_EXECUTE_CONTRACT.md"),
    "preflight_json": Path("docs/N1_stock_identity_refresh_20260529_execute_preflight.json"),
    "preflight_md": Path("docs/N1_STOCK_IDENTITY_REFRESH_20260529_EXECUTE_PREFLIGHT.md"),
    "rollback_sql": Path("sql/N1_stock_identity_refresh_20260529_rollback.sql"),
}


class StockIdentityRefresh20260529Blocked(RuntimeError):
    """Raised when the 20260529 stock_identity refresh gate is blocked."""


def now_iso() -> str:
    return datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat()


def validate_execute_request(*, execute_requested: bool, user_confirmed: bool) -> None:
    if not execute_requested:
        raise StockIdentityRefresh20260529Blocked("missing --execute")
    if not user_confirmed:
        raise StockIdentityRefresh20260529Blocked("missing --user-confirmed")


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
        "latest_previous_active_source_batch_id": PREVIOUS_SOURCE_BATCH_ID,
        "daily_fact_rows": {"stock": 0, "index": 0, "board": 0},
        "condition_source_rows": {"stock_daily_basic": 0, "stock_financial": 0, "index_membership": 0, "board_membership": 0},
        "event_counts": {"outbox": 0, "inbox": 0, "checkpoint": 0},
        "read_only_database_checks": True,
    }


def build_snapshot_from_db(*, dsn: str, trade_date: str = TRADE_DATE) -> dict[str, Any]:
    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=10) as conn:
        conn.execute("BEGIN TRANSACTION READ ONLY")
        previous_active = conn.execute(
            """
            SELECT source_version, source_batch_id
            FROM common_active_source_version
            WHERE data_domain='stock' AND data_type='stock_identity'
            ORDER BY activated_at DESC NULLS LAST, created_at DESC NULLS LAST
            LIMIT 1
            """
        ).fetchone()
        snapshot = {
            "trade_date": trade_date,
            "target_stock_identity_rows": conn.execute(
                "SELECT count(*)::int AS c FROM stock_identity WHERE stock_identity_key=%s",
                (EXPECTED_IDENTITY_KEY,),
            ).fetchone()["c"],
            "target_ts_code_rows": conn.execute(
                "SELECT count(*)::int AS c FROM stock_identity WHERE ts_code=%s",
                (EXPECTED_TS_CODE,),
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
            "latest_previous_active_source_batch_id": previous_active["source_batch_id"] if previous_active else PREVIOUS_SOURCE_BATCH_ID,
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
            "condition_source_rows": {
                "stock_daily_basic": conn.execute(
                    "SELECT count(*)::int AS c FROM stock_daily_basic WHERE trade_date=%s AND source_batch_id=%s",
                    (trade_date, BATCH_ID),
                ).fetchone()["c"],
                "stock_financial": conn.execute(
                    "SELECT count(*)::int AS c FROM stock_financial_metrics_fact WHERE source_trade_date=%s AND source_batch_id=%s",
                    (trade_date, BATCH_ID),
                ).fetchone()["c"],
                "index_membership": conn.execute(
                    "SELECT count(*)::int AS c FROM index_membership_fact WHERE trade_date=%s AND source_batch_id=%s",
                    (trade_date, BATCH_ID),
                ).fetchone()["c"],
                "board_membership": conn.execute(
                    "SELECT count(*)::int AS c FROM board_membership_fact WHERE trade_date=%s AND source_batch_id=%s",
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


class DefaultStockIdentityRefresh20260529SourceAdapter:
    """Tushare proof adapter used by preflight and explicit final execute."""

    def __init__(self, *, token: str | None = None) -> None:
        self.token = token or load_tushare_token() or ""
        self._pro_client: Any | None = None

    def fetch_source_evidence(self, *, trade_date: str, ts_code: str = EXPECTED_TS_CODE) -> dict[str, list[dict[str, Any]]]:
        if not self.token:
            raise StockIdentityRefresh20260529Blocked("TUSHARE_TOKEN is required")
        pro = self._pro()
        stock_basic_rows: list[dict[str, Any]] = []
        for list_status in ("L", "D", "P"):
            stock_basic_rows.extend(
                row
                for row in frame_to_records(
                    pro.stock_basic(
                        exchange="",
                        list_status=list_status,
                        fields="ts_code,symbol,name,area,industry,market,list_date,delist_date,list_status,exchange",
                    )
                )
                if str(row.get("ts_code") or "").strip().upper() == ts_code
            )
        return {
            "stock_basic": stock_basic_rows,
            "daily": frame_to_records(
                pro.daily(
                    ts_code=ts_code,
                    trade_date=trade_date,
                    fields="ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
                )
            ),
            "adj_factor": frame_to_records(
                pro.adj_factor(ts_code=ts_code, trade_date=trade_date, fields="ts_code,trade_date,adj_factor")
            ),
            "suspend_d": frame_to_records(
                pro.suspend_d(ts_code=ts_code, trade_date=trade_date, fields="ts_code,trade_date,suspend_type,suspend_timing")
            ),
            "bak_daily": frame_to_records(
                pro.bak_daily(
                    ts_code=ts_code,
                    trade_date=trade_date,
                    fields="ts_code,trade_date,name,close,open,high,low,pre_close,vol,amount",
                )
            ),
        }

    def _pro(self) -> Any:
        if self._pro_client is None:
            module = importlib.import_module("tushare")
            if hasattr(module, "set_token"):
                module.set_token(self.token)
            self._pro_client = module.pro_api(self.token)
        return self._pro_client


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
    if isinstance(frame, Iterable) and not isinstance(frame, (str, bytes)):
        return [dict(record) for record in frame]
    return []


def validate_source_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    stock_basic_rows = target_rows(evidence, "stock_basic")
    daily_rows = target_rows(evidence, "daily")
    adj_factor_rows = target_rows(evidence, "adj_factor")
    suspend_rows = target_rows(evidence, "suspend_d")
    bak_daily_rows = target_rows(evidence, "bak_daily")
    p0: list[str] = []

    if len(stock_basic_rows) != 1:
        p0.append(f"stock_basic expected 1 row for {EXPECTED_TS_CODE}, got {len(stock_basic_rows)}")
    if len(daily_rows) != 1:
        p0.append(f"daily expected 1 row for {EXPECTED_TS_CODE}/{TRADE_DATE}, got {len(daily_rows)}")
    if len(adj_factor_rows) != 1:
        p0.append(f"adj_factor expected 1 row for {EXPECTED_TS_CODE}/{TRADE_DATE}, got {len(adj_factor_rows)}")
    if len(bak_daily_rows) != 1:
        p0.append(f"bak_daily expected 1 row for {EXPECTED_TS_CODE}/{TRADE_DATE}, got {len(bak_daily_rows)}")

    if stock_basic_rows:
        stock_basic = stock_basic_rows[0]
        list_date = str(stock_basic.get("list_date") or "").strip()
        if list_date != TRADE_DATE:
            p0.append(f"stock_basic list_date must be {TRADE_DATE}, got {list_date}")
        list_status = str(stock_basic.get("list_status") or "").strip().upper()
        if list_status != "L":
            p0.append(f"stock_basic list_status must be L, got {list_status}")
        for field in ("name", "area", "industry", "market"):
            expected = str(EXPECTED_IDENTITY[field] or "")
            actual = str(stock_basic.get(field) or "").strip()
            if expected and actual != expected:
                p0.append(f"stock_basic {field} mismatch: {actual} != {expected}")

    if daily_rows:
        daily = daily_rows[0]
        for field in ("open", "high", "low", "close"):
            if daily.get(field) is None:
                p0.append(f"daily {field} is missing")
        if _as_float(daily.get("vol")) is None or _as_float(daily.get("vol")) <= 0:
            p0.append("daily vol must be positive")
        if _as_float(daily.get("amount")) is None or _as_float(daily.get("amount")) <= 0:
            p0.append("daily amount must be positive")

    if adj_factor_rows and _as_float(adj_factor_rows[0].get("adj_factor")) is None:
        p0.append("adj_factor is missing")

    if p0:
        raise StockIdentityRefresh20260529Blocked("; ".join(p0))

    return {
        "p0_count": 0,
        "p1_count": 0,
        "p2_count": 0,
        "stock_basic_present": bool(stock_basic_rows),
        "daily_present": bool(daily_rows),
        "adj_factor_present": bool(adj_factor_rows),
        "suspend_d_present": bool(suspend_rows),
        "bak_daily_present": bool(bak_daily_rows),
        "stock_basic_rows": len(stock_basic_rows),
        "daily_rows": len(daily_rows),
        "adj_factor_rows": len(adj_factor_rows),
        "suspend_d_rows": len(suspend_rows),
        "bak_daily_rows": len(bak_daily_rows),
        "source_evidence_summary": {
            "ts_code": EXPECTED_TS_CODE,
            "trade_date": TRADE_DATE,
            "stock_basic": public_source_rows(stock_basic_rows),
            "daily": public_source_rows(daily_rows),
            "adj_factor": public_source_rows(adj_factor_rows),
            "suspend_d": public_source_rows(suspend_rows),
            "bak_daily": public_source_rows(bak_daily_rows),
        },
    }


def target_rows(evidence: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    rows = frame_to_records(evidence.get(key))
    return [
        row
        for row in rows
        if str(row.get("ts_code") or "").strip().upper() == EXPECTED_TS_CODE
        and (not row.get("trade_date") or str(row.get("trade_date")).strip() == TRADE_DATE)
    ]


def public_source_rows(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [json_safe(row) for row in rows]


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def identity_key_from_ts_code(ts_code: str) -> tuple[str, str, str]:
    exchange, code = normalize_exchange_from_ts_code(str(ts_code).strip().upper())
    return f"stock:{exchange}:{code}", exchange, code


def build_target_identity_rows(evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    validate_source_evidence(evidence)
    stock_basic_rows = target_rows(evidence, "stock_basic")
    duplicate_ts_codes = [
        ts_code
        for ts_code, count in Counter(str(row.get("ts_code") or "").strip().upper() for row in stock_basic_rows).items()
        if ts_code and count > 1
    ]
    if duplicate_ts_codes:
        raise StockIdentityRefresh20260529Blocked(f"duplicate stock_basic ts_code rows: {duplicate_ts_codes}")
    raw = dict(stock_basic_rows[0])
    ts_code = str(raw.get("ts_code") or "").strip().upper()
    identity_key, exchange, code = identity_key_from_ts_code(ts_code)
    if identity_key != EXPECTED_IDENTITY_KEY:
        raise StockIdentityRefresh20260529Blocked(f"identity_key mismatch: {identity_key} != {EXPECTED_IDENTITY_KEY}")
    list_date = str(raw.get("list_date") or "").strip()
    name = str(raw.get("name") or EXPECTED_IDENTITY["name"]).strip()
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
                "source_evidence": evidence,
            }
        ),
    }
    if row["code"] != code:
        raise StockIdentityRefresh20260529Blocked(f"{ts_code} symbol/code mismatch: {row['code']} != {code}")
    if row["status"] != "active":
        raise StockIdentityRefresh20260529Blocked(f"{ts_code} list_status must be L/active")
    return [row]


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
    if len(rows) != 1:
        p0.append(f"expected 1 stock_identity row, got {len(rows)}")
    if EXPECTED_IDENTITY_KEY not in identity_keys:
        p0.append(f"missing expected identity_key row: {EXPECTED_IDENTITY_KEY}")
    if EXPECTED_TS_CODE not in ts_codes:
        p0.append(f"missing expected ts_code row: {EXPECTED_TS_CODE}")
    duplicate_identity = len(identity_keys) - len(set(identity_keys))
    duplicate_ts_code = len(ts_codes) - len(set(ts_codes))
    if duplicate_identity:
        p0.append(f"duplicate identity_key rows: {duplicate_identity}")
    if duplicate_ts_code:
        p0.append(f"duplicate ts_code rows: {duplicate_ts_code}")
    wrong_list_dates = [row["ts_code"] for row in rows if str(row.get("listed_date") or "") != TRADE_DATE]
    if wrong_list_dates:
        p0.append(f"wrong list_date rows: {wrong_list_dates}")
    if p0:
        raise StockIdentityRefresh20260529Blocked("; ".join(p0))
    return {
        "p0_count": 0,
        "p1_count": 0,
        "p2_count": 0,
        "row_count": len(rows),
        "duplicate_identity_key": duplicate_identity,
        "duplicate_ts_code": duplicate_ts_code,
        "new_identity_keys": sorted(identity_keys),
        "new_ts_codes": sorted(ts_codes),
    }


def validate_commit_preconditions(*, snapshot: Mapping[str, Any], validation_report: Mapping[str, Any]) -> None:
    if int(snapshot.get("target_stock_identity_rows") or 0) != 0:
        raise StockIdentityRefresh20260529Blocked("existing target stock_identity rows")
    if int(snapshot.get("target_ts_code_rows") or 0) != 0:
        raise StockIdentityRefresh20260529Blocked("existing target ts_code rows")
    if int(snapshot.get("source_version_identity_rows") or 0) != 0:
        raise StockIdentityRefresh20260529Blocked("existing stock_identity rows for this source_version")
    if int(snapshot.get("batch_conflict_count") or 0) != 0:
        raise StockIdentityRefresh20260529Blocked("existing batch/source_version conflict")
    if int(snapshot.get("quality_conflict_count") or 0) != 0:
        raise StockIdentityRefresh20260529Blocked("existing quality rows")
    if int(snapshot.get("existing_active_scope_key_count") or 0) != 0:
        raise StockIdentityRefresh20260529Blocked("existing active source_version for A_STOCK:20260529")
    daily_fact_rows = snapshot.get("daily_fact_rows") or {}
    if any(int(value or 0) != 0 for value in daily_fact_rows.values()):
        raise StockIdentityRefresh20260529Blocked("this identity refresh gate must not own daily fact rows")
    condition_source_rows = snapshot.get("condition_source_rows") or {}
    if any(int(value or 0) != 0 for value in condition_source_rows.values()):
        raise StockIdentityRefresh20260529Blocked("this identity refresh gate must not own condition source rows")
    if int(validation_report.get("p0_count") or 0) != 0:
        raise StockIdentityRefresh20260529Blocked("source validation P0 > 0")


def build_commit_plan(*, rows: list[Mapping[str, Any]], validation_report: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    identity_rows = [dict(row) for row in rows]
    previous_source_version = str(baseline.get("latest_previous_active_source_version") or PREVIOUS_SOURCE_VERSION)
    previous_source_batch_id = str(baseline.get("latest_previous_active_source_batch_id") or PREVIOUS_SOURCE_BATCH_ID)
    quality_items = build_quality_items(validation_report)
    return {
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSION,
        "previous_source_version": previous_source_version,
        "previous_source_batch_id": previous_source_batch_id,
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
            "activated_by": "n1_stock_identity_refresh_20260529_execute_runner",
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
                "target_ts_code": EXPECTED_TS_CODE,
                "target_identity_key": EXPECTED_IDENTITY_KEY,
                "previous_source_version": previous_source_version,
                "evidence_sources": ["stock_basic", "daily", "adj_factor", "suspend_d", "bak_daily"],
            },
            "raw_hash": stable_raw_hash(identity_rows),
            "row_count": len(identity_rows),
            "error_count": 0,
            "quality_gate_summary": {
                "p0_count": validation_report["p0_count"],
                "p1_count": validation_report["p1_count"],
                "p2_count": validation_report["p2_count"],
                "source_evidence_validated": True,
            },
            "rollback_strategy": str(DEFAULT_PATHS["rollback_sql"]),
            "status": "passed",
        },
        "baseline": dict(baseline),
    }


def build_quality_items(validation_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    items = [
        ("target_stock_basic_rows_present", "P0", "passed", "1", "1", {"target_ts_code": EXPECTED_TS_CODE}),
        ("target_list_date_20260529", "P0", "passed", "1", "1", {"trade_date": TRADE_DATE}),
        ("daily_proof_present", "P0", "passed", "1", "1", {"source": "tushare.daily"}),
        ("adj_factor_proof_present", "P0", "passed", "1", "1", {"source": "tushare.adj_factor"}),
        ("bak_daily_proof_present", "P0", "passed", "1", "1", {"source": "tushare.bak_daily"}),
        ("duplicate_identity_key", "P0", "passed", "0", str(validation_report["duplicate_identity_key"]), {}),
        ("duplicate_ts_code", "P0", "passed", "0", str(validation_report["duplicate_ts_code"]), {}),
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
) -> dict[str, Any]:
    validate_execute_request(execute_requested=execute_requested, user_confirmed=user_confirmed)
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


def build_execute_contract(snapshot: Mapping[str, Any], *, source_report: Mapping[str, Any]) -> dict[str, Any]:
    blockers = build_preflight_blockers(snapshot)
    source_p0 = int(source_report.get("p0_count") or 0)
    final_allowed = not blockers and source_p0 == 0
    return {
        "stage": "N1 stock_identity refresh 20260529 execute contract",
        "layer_role": "N1_ingestion",
        "result": "DESIGN_PASS" if final_allowed else "DESIGN_BLOCKED",
        "trade_date": TRADE_DATE,
        "runner_readiness": "ready_for_final_gate" if final_allowed else "blocked",
        "execute_authorized": False,
        "final_execute_gate_allowed": final_allowed,
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSION,
        "previous_source_version": str(snapshot.get("latest_previous_active_source_version") or PREVIOUS_SOURCE_VERSION),
        "active_scope_key": ACTIVE_SCOPE_KEY,
        "expected_rows": {
            "stock_identity_insert_rows": 1,
            "common_ingest_batch_rows": 1,
            "common_active_source_version_rows": 1,
        },
        "new_identity_rows": [public_identity_row(EXPECTED_IDENTITY)],
        "source_evidence": source_report.get("source_evidence_summary", {}),
        "execute_flags": ["--execute", "--user-confirmed"],
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
            "expected_p0_p1_p2": {"p0": 0, "p1": 0, "p2": 0},
        },
        "rollback": {
            "path": str(DEFAULT_PATHS["rollback_sql"]),
            "strategy": "delete this batch's stock_identity row and quality/batch metadata, then restore active scope to previous_source_version when resolvable",
            "do_not_touch_historical_identity_rows": True,
            "do_not_touch_daily_fact": True,
            "do_not_touch_outbox_or_n2_n6": True,
        },
        "implementation_status": {
            "execute_runner_implemented": True,
            "execute_authorized": False,
            "final_execute_gate_allowed": final_allowed,
            "next_gate": "final_execute_gate" if final_allowed else "resolve_preflight_blockers",
        },
    }


def public_identity_row(expected: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stock_identity_key": expected["stock_identity_key"],
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
    source_report: Mapping[str, Any],
    execute_requested: bool,
    user_confirmed: bool,
) -> dict[str, Any]:
    blockers = build_preflight_blockers(snapshot)
    source_p0 = int(source_report.get("p0_count") or 0)
    if source_p0:
        blockers.append("source_evidence_p0")
    result = "PREFLIGHT_PASS" if not blockers else "PREFLIGHT_BLOCKED"
    return {
        "stage": "N1 stock_identity refresh 20260529 execute preflight",
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
        "execute_authorized": bool(execute_requested and user_confirmed and not blockers),
        "baseline": dict(snapshot),
        "expected_rows": {
            "stock_identity_insert_rows": 1,
            "common_ingest_batch_rows": 1,
            "common_active_source_version_rows": 1,
        },
        "source_evidence": source_report.get("source_evidence_summary", {}),
        "quality": {
            "p0_count": 0 if not blockers else len(blockers),
            "p1_count": 0,
            "p2_count": 0,
            "source_evidence": {
                "stock_basic_present": bool(source_report.get("stock_basic_present")),
                "daily_present": bool(source_report.get("daily_present")),
                "adj_factor_present": bool(source_report.get("adj_factor_present")),
                "suspend_d_present": bool(source_report.get("suspend_d_present")),
                "bak_daily_present": bool(source_report.get("bak_daily_present")),
            },
        },
        "execute_runner": {
            "implemented": True,
            "runner_readiness": "ready_for_final_gate" if not blockers else "blocked",
            "final_execute_gate_allowed": not blockers,
            "execute_authorized": bool(execute_requested and user_confirmed and not blockers),
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
            "writes_condition_source": False,
            "writes_parquet": False,
            "writes_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "enters_n2_n3_n4_n5_n6": False,
            "worker_started": False,
            "old_system_touched": False,
            "real_trading": False,
        },
        "execute_command_candidate": (
            "PYTHONPATH=src python3 scripts/run_stock_identity_refresh_20260529_once.py "
            "--trade-date 20260529 --execute --user-confirmed"
        ),
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
    condition_source_rows = snapshot.get("condition_source_rows") or {}
    if any(int(value or 0) != 0 for value in condition_source_rows.values()):
        blockers.append("unexpected_condition_source_rows_for_identity_batch")
    return blockers


def blocked_source_report(message: str) -> dict[str, Any]:
    return {
        "p0_count": 1,
        "p1_count": 0,
        "p2_count": 0,
        "source_evidence_error": message,
        "stock_basic_present": False,
        "daily_present": False,
        "adj_factor_present": False,
        "suspend_d_present": False,
        "bak_daily_present": False,
        "source_evidence_summary": {"error": message},
    }


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
                "# N1 Stock Identity Refresh 20260529 Execute Contract",
                "",
                f"状态：`{contract['result']}`",
                "",
                "```text",
                f"source_batch_id = {BATCH_ID}",
                f"source_version = {SOURCE_VERSION}",
                f"active_scope_key = {ACTIVE_SCOPE_KEY}",
                f"previous_source_version = {contract['previous_source_version']}",
                f"runner_readiness = {contract['runner_readiness']}",
                "expected_stock_identity_insert_rows = 1",
                "P0/P1/P2 = 0/0/0",
                "```",
                "",
                "本 runner 只允许写 stock_identity、common_ingest_batch、common_quality_gate_result、common_active_source_version。",
                "禁止写 daily fact、condition source、Parquet、outbox/inbox/checkpoint、N2-N6、worker、旧系统或真实交易。",
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
                "# N1 Stock Identity Refresh 20260529 Execute Preflight",
                "",
                f"状态：`{preflight['result']}`",
                "",
                "```text",
                f"runner_readiness = {preflight['runner_readiness']}",
                f"final_execute_gate_allowed = {str(preflight['final_execute_gate_allowed']).lower()}",
                f"source_batch_id = {BATCH_ID}",
                f"source_version = {SOURCE_VERSION}",
                "expected_stock_identity_insert_rows = 1",
                "P0/P1/P2 = 0/0/0",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
