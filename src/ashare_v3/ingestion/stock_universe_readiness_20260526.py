"""N1 stock universe readiness dry-run for 20260526.

This module is read-only by design. It checks the stock universe gap that
blocked the 20260526 official daily ingestion v1 run, classifies stale identity
and source gaps, and writes only report artifacts through the CLI wrapper.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
import importlib
import json
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row

from ashare_v3.ingestion.tushare_env import load_tushare_token


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
TRADE_DATE = "20260526"
RAW_ACTIVE_UNIVERSE = 5523
TUSHARE_DAILY_MATCHED = 5504
STALE_IDENTITY_KEY = "stock:SZ:300114"
SUPERSEDED_BY_IDENTITY_KEY = "stock:SZ:302132"
DAILY_MISSING_ACTIVE_IDENTITIES = (
    "stock:BJ:920058",
    "stock:BJ:920305",
    "stock:SH:600193",
    "stock:SH:600421",
    "stock:SH:600599",
    "stock:SH:600608",
    "stock:SH:600636",
    "stock:SH:600696",
    "stock:SH:605081",
    "stock:SH:688121",
    "stock:SZ:000004",
    "stock:SZ:000638",
    "stock:SZ:002731",
    "stock:SZ:002808",
    "stock:SZ:002898",
    "stock:SZ:300029",
    "stock:SZ:300550",
    "stock:SZ:301096",
)
KNOWN_MISSING_IDENTITIES = tuple(sorted((STALE_IDENTITY_KEY, *DAILY_MISSING_ACTIVE_IDENTITIES)))
DEFAULT_JSON_PATH = Path("docs/N1_stock_universe_readiness_20260526_report.json")
DEFAULT_MD_PATH = Path("docs/N1_STOCK_UNIVERSE_READINESS_20260526_REPORT.md")


class StockUniverseReadinessBlocked(RuntimeError):
    """Raised when a caller attempts a forbidden readiness action."""


def now_iso() -> str:
    return datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat()


def identity_to_ts_code(identity_key: str) -> str:
    _, exchange, code = identity_key.split(":")
    return f"{code}.{exchange}"


def normalize_identity_row(row: Mapping[str, Any]) -> dict[str, Any]:
    identity_key = str(row.get("stock_identity_key") or row.get("identity_key") or "")
    if not identity_key:
        ts_code = str(row.get("ts_code") or "")
        code, exchange = ts_code.split(".")
        identity_key = f"stock:{exchange}:{code}"
    _, exchange, code = identity_key.split(":")
    return {
        "stock_identity_key": identity_key,
        "identity_key": identity_key,
        "ts_code": str(row.get("ts_code") or f"{code}.{exchange}"),
        "code": str(row.get("code") or code),
        "exchange": str(row.get("exchange") or exchange),
        "name": row.get("name"),
        "listed_date": row.get("listed_date"),
        "delisted_date": row.get("delisted_date"),
        "is_st": bool(row.get("is_st") or False),
        "status": str(row.get("status") or "unknown"),
        "source": row.get("source"),
        "source_version": row.get("source_version"),
    }


def build_readiness_report(
    *,
    db_snapshot: Mapping[str, Any],
    tushare_snapshot: Mapping[str, Any],
    tdx_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    candidate_rows = [normalize_identity_row(row) for row in db_snapshot.get("candidate_rows") or []]
    active_rows = [normalize_identity_row(row) for row in db_snapshot.get("active_stock_rows") or []]
    if not active_rows:
        active_rows = candidate_rows
    active_by_identity = {row["identity_key"]: row for row in active_rows}
    candidate_by_identity = {row["identity_key"]: row for row in candidate_rows}
    raw_active_universe = int(db_snapshot.get("raw_active_universe") or len(active_rows) or RAW_ACTIVE_UNIVERSE)

    daily_present = set(map(str, tushare_snapshot.get("daily_present_ts_codes") or []))
    adj_present = set(map(str, tushare_snapshot.get("adj_factor_present_ts_codes") or []))
    stock_basic_by_ts = {
        str(key): dict(value)
        for key, value in (tushare_snapshot.get("stock_basic_by_ts_code") or {}).items()
    }
    active_ts_codes = {row["ts_code"] for row in active_rows}
    missing_from_daily = sorted(active_ts_codes - daily_present) if active_ts_codes and daily_present else list(map(identity_to_ts_code, KNOWN_MISSING_IDENTITIES))
    missing_identity_keys = sorted(
        {
            ts_code_to_identity(ts_code)
            for ts_code in missing_from_daily
            if ts_code_to_identity(ts_code) in set(KNOWN_MISSING_IDENTITIES) or ts_code_to_identity(ts_code) in active_by_identity
        }
    )
    if not missing_identity_keys:
        missing_identity_keys = list(KNOWN_MISSING_IDENTITIES)

    stale_candidates = build_stale_identity_candidates(candidate_by_identity, active_by_identity, daily_present, adj_present, stock_basic_by_ts)
    stale_keys = {row["identity_key"] for row in stale_candidates}
    effective_active_universe = raw_active_universe - len(stale_keys)

    tdx_presence = {
        str(key): dict(value)
        for key, value in (tdx_snapshot.get("presence_by_identity_key") or {}).items()
    }
    source_available = bool(tdx_snapshot.get("source_available", True))

    gap_rows: list[dict[str, Any]] = []
    for identity_key in DAILY_MISSING_ACTIVE_IDENTITIES:
        identity = candidate_by_identity.get(identity_key) or active_by_identity.get(identity_key) or identity_from_key(identity_key)
        ts_code = identity["ts_code"]
        tdx_info = tdx_presence.get(identity_key) or {}
        tdx_present = bool(tdx_info.get("present"))
        in_daily = ts_code in daily_present
        in_adj = ts_code in adj_present
        stock_basic = stock_basic_by_ts.get(ts_code)
        if tdx_present:
            disposition = "supplemental_source_bar"
            severity = "P1"
            reason = "Tushare daily missing but TDX/Mootdx daily is available for supplemental official bar."
            recommended_action = "Generate official_daily_ingest_20260526_v2 with TDX/Mootdx supplemental stock bar source."
        else:
            disposition = "no_trade_candidate_without_official_proof" if in_adj and stock_basic else "unresolved_source_gap"
            severity = "P0"
            reason = (
                "Tushare daily missing; adj_factor/listed evidence exists but no official no-trade proof or supplemental bar is available."
                if disposition == "no_trade_candidate_without_official_proof"
                else "Tushare daily missing and no supplemental official bar evidence is available."
            )
            recommended_action = "Do not commit daily fact; obtain TDX/Mootdx bar or official no-trade/suspend proof."
        gap_rows.append(
            {
                "identity_key": identity_key,
                "code": identity["code"],
                "exchange": identity["exchange"],
                "ts_code": ts_code,
                "name": identity.get("name"),
                "is_st": identity.get("is_st"),
                "stock_identity_status": identity.get("status"),
                "tushare_daily_present": in_daily,
                "tushare_adj_factor_present": in_adj,
                "tushare_stock_basic": summarize_stock_basic(stock_basic),
                "tdx_mootdx_daily_present": tdx_present,
                "tdx_mootdx_evidence": tdx_info.get("evidence") or {},
                "recommended_disposition": disposition,
                "severity": severity,
                "reason": reason,
                "recommended_action": recommended_action,
            }
        )

    unresolved_rows = [row for row in gap_rows if row["recommended_disposition"] != "supplemental_source_bar"]
    supplemental_rows = [row for row in gap_rows if row["recommended_disposition"] == "supplemental_source_bar"]
    blockers = []
    if unresolved_rows:
        blockers.append("unresolved_source_gap")
    if not source_available:
        blockers.append("tdx_mootdx_unavailable")

    quality_items = []
    for row in stale_candidates:
        quality_items.append(
            quality_item(
                "stale_identity_candidate",
                "P1",
                "warning",
                "0 stale active identities",
                row["identity_key"],
                {"superseded_by": row["superseded_by_identity_key"]},
            )
        )
    for row in gap_rows:
        status = "warning" if row["severity"] == "P1" else "failed"
        quality_items.append(
            quality_item(
                row["recommended_disposition"],
                row["severity"],
                status,
                "supplemental source bar or official no-trade proof",
                row["identity_key"],
                {
                    "tushare_daily_present": row["tushare_daily_present"],
                    "tushare_adj_factor_present": row["tushare_adj_factor_present"],
                    "tdx_mootdx_daily_present": row["tdx_mootdx_daily_present"],
                },
            )
        )
    if not source_available:
        quality_items.append(
            quality_item(
                "tdx_mootdx_unavailable",
                "P0",
                "failed",
                "TDX/Mootdx stock daily probe available",
                str(tdx_snapshot.get("source_unavailable_reason") or "unavailable"),
                {},
            )
        )

    quality = summarize_quality(quality_items)
    result = "READINESS_PASS" if quality["p0_count"] == 0 else "READINESS_BLOCKED"
    tushare_daily_matched = int(tushare_snapshot.get("daily_row_count") or (raw_active_universe - len(missing_identity_keys)) or TUSHARE_DAILY_MATCHED)
    expected_scope = {
        "stock": effective_active_universe if result == "READINESS_PASS" else None,
        "candidate_stock_if_all_gaps_resolved": effective_active_universe,
        "requires_supplemental_source_rows": len(supplemental_rows),
        "blocked_unresolved_rows": len(unresolved_rows),
    }

    return normalize_jsonable(
        {
            "stage": "N1 stock universe readiness 20260526 source gap dry-run",
            "layer_role": "N1_ingestion",
            "result": result,
            "blocked": result != "READINESS_PASS",
            "blockers": blockers,
            "trade_date": TRADE_DATE,
            "raw_active_universe": raw_active_universe,
            "stale_identity_candidates": stale_candidates,
            "effective_active_universe": effective_active_universe,
            "tushare_daily_matched": tushare_daily_matched,
            "unresolved_daily_missing_active": len(unresolved_rows),
            "supplemental_source_available": len(supplemental_rows),
            "expected_daily_bar_scope": expected_scope,
            "missing_stock_manifest": [*stale_candidates, *gap_rows],
            "daily_missing_active_disposition": gap_rows,
            "tdx_mootdx": {
                "source_available": source_available,
                "source": tdx_snapshot.get("source"),
                "source_unavailable_reason": tdx_snapshot.get("source_unavailable_reason"),
                "supplemental_present_count": len(supplemental_rows),
            },
            "quality": quality,
            "quality_items": quality_items,
            "official_daily_ingest_v2_allowed": result == "READINESS_PASS",
            "recommended_next_step": (
                "Generate official_daily_ingest_20260526_v2 contract/final gate."
                if result == "READINESS_PASS"
                else "Resolve stock identity correction and source gaps before official_daily_ingest_20260526_v2."
            ),
            "side_effects": no_side_effects(),
            "generated_at": now_iso(),
        }
    )


def build_stale_identity_candidates(
    candidate_by_identity: Mapping[str, Mapping[str, Any]],
    active_by_identity: Mapping[str, Mapping[str, Any]],
    daily_present: set[str],
    adj_present: set[str],
    stock_basic_by_ts: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    stale = candidate_by_identity.get(STALE_IDENTITY_KEY) or active_by_identity.get(STALE_IDENTITY_KEY)
    replacement = candidate_by_identity.get(SUPERSEDED_BY_IDENTITY_KEY) or active_by_identity.get(SUPERSEDED_BY_IDENTITY_KEY)
    if not stale:
        return []
    stale_ts = identity_to_ts_code(STALE_IDENTITY_KEY)
    replacement_ts = identity_to_ts_code(SUPERSEDED_BY_IDENTITY_KEY)
    replacement_evidence = stock_basic_by_ts.get(replacement_ts) or {}
    return [
        {
            "identity_key": STALE_IDENTITY_KEY,
            "code": stale.get("code", "300114"),
            "exchange": stale.get("exchange", "SZ"),
            "ts_code": stale.get("ts_code", stale_ts),
            "name": stale.get("name"),
            "reason": "stale_identity_candidate",
            "evidence": {
                "local_source": stale.get("source"),
                "local_source_version": stale.get("source_version"),
                "tushare_daily_present": stale_ts in daily_present,
                "tushare_adj_factor_present": stale_ts in adj_present,
                "replacement_identity_exists": bool(replacement),
                "replacement_tushare_stock_basic": summarize_stock_basic(replacement_evidence),
            },
            "recommended_action": "Exclude from 20260526 expected universe and open stock_identity correction gate.",
            "recommended_disposition": "exclude_from_expected_universe",
            "severity": "P1",
            "superseded_by_identity_key": SUPERSEDED_BY_IDENTITY_KEY,
        }
    ]


def identity_from_key(identity_key: str) -> dict[str, Any]:
    _, exchange, code = identity_key.split(":")
    return {
        "identity_key": identity_key,
        "stock_identity_key": identity_key,
        "ts_code": f"{code}.{exchange}",
        "code": code,
        "exchange": exchange,
        "name": None,
        "is_st": False,
        "status": "active",
    }


def ts_code_to_identity(ts_code: str) -> str:
    code, exchange = str(ts_code).split(".")
    return f"stock:{exchange}:{code}"


def summarize_stock_basic(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    keys = ("ts_code", "symbol", "name", "list_status", "list_date", "delist_date", "market")
    return {key: row.get(key) for key in keys if key in row}


def quality_item(
    gate_name: str,
    severity: str,
    status: str,
    expected: Any,
    actual: Any,
    details: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "gate_name": gate_name,
        "severity": severity,
        "status": status,
        "expected": expected,
        "actual": actual,
        "details": dict(details),
    }


def summarize_quality(items: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "p0_count": sum(1 for item in items if item.get("severity") == "P0" and item.get("status") != "passed"),
        "p1_count": sum(1 for item in items if item.get("severity") == "P1" and item.get("status") != "passed"),
        "p2_count": sum(1 for item in items if item.get("severity") == "P2" and item.get("status") != "passed"),
        "items": len(items),
    }


def build_db_snapshot_from_db(*, dsn: str, trade_date: str = TRADE_DATE) -> dict[str, Any]:
    if trade_date != TRADE_DATE:
        raise StockUniverseReadinessBlocked(f"this runner is fixed to trade_date={TRADE_DATE}")
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT stock_identity_key, ts_code, code, exchange, name, listed_date,
                       delisted_date, is_st, status, source, source_version
                FROM stock_identity
                WHERE status = 'active'
                ORDER BY exchange, code
                """
            )
            active_rows = [dict(row) for row in cur.fetchall()]
    active_by_key = {row["stock_identity_key"]: row for row in active_rows}
    candidate_keys = sorted(set(KNOWN_MISSING_IDENTITIES) | {SUPERSEDED_BY_IDENTITY_KEY})
    return normalize_jsonable(
        {
            "trade_date": trade_date,
            "raw_active_universe": len(active_rows),
            "active_stock_rows": active_rows,
            "candidate_rows": [active_by_key[key] for key in candidate_keys if key in active_by_key],
            "read_only_database_checks": True,
        }
    )


class DefaultTushareStockUniverseProbe:
    def __init__(self, *, token: str | None = None) -> None:
        self.token = token or load_tushare_token()
        self._pro: Any | None = None

    def fetch_snapshot(self, *, trade_date: str = TRADE_DATE) -> dict[str, Any]:
        if not self.token:
            raise StockUniverseReadinessBlocked("TUSHARE_TOKEN is required for stock universe readiness dry-run")
        pro = self._client()
        daily_rows = frame_to_records(
            pro.daily(trade_date=trade_date, fields="ts_code,trade_date,open,high,low,close,vol,amount")
        )
        adj_rows = frame_to_records(pro.adj_factor(trade_date=trade_date, fields="ts_code,trade_date,adj_factor"))
        stock_basic_rows: list[dict[str, Any]] = []
        for status in ("L", "D", "P"):
            stock_basic_rows.extend(
                frame_to_records(
                    pro.stock_basic(
                        exchange="",
                        list_status=status,
                        fields="ts_code,symbol,name,area,industry,market,list_date,delist_date,list_status",
                    )
                )
            )
        return normalize_jsonable(
            {
                "trade_date": trade_date,
                "source": "tushare.daily+adj_factor+stock_basic.readonly",
                "daily_row_count": len(daily_rows),
                "daily_present_ts_codes": sorted({str(row.get("ts_code")) for row in daily_rows if row.get("ts_code")}),
                "adj_factor_row_count": len(adj_rows),
                "adj_factor_present_ts_codes": sorted({str(row.get("ts_code")) for row in adj_rows if row.get("ts_code")}),
                "stock_basic_by_ts_code": {
                    str(row.get("ts_code")): row
                    for row in stock_basic_rows
                    if row.get("ts_code")
                },
            }
        )

    def _client(self) -> Any:
        if self._pro is None:
            tushare = importlib.import_module("tushare")
            self._pro = tushare.pro_api(self.token)
        return self._pro


class DefaultMootdxStockDailyProbe:
    def __init__(self, *, offset: int = 20, client: Any | None = None) -> None:
        self.offset = offset
        self._client = client

    def fetch_snapshot(self, *, candidates: Sequence[Mapping[str, Any]], trade_date: str = TRADE_DATE) -> dict[str, Any]:
        try:
            client = self._get_client()
        except Exception as exc:  # pragma: no cover - environment dependent
            return {
                "trade_date": trade_date,
                "source": "mootdx.stock_daily.readonly",
                "source_available": False,
                "source_unavailable_reason": f"{type(exc).__name__}: {exc}",
                "presence_by_identity_key": {},
            }
        presence: dict[str, Any] = {}
        for row in candidates:
            identity = normalize_identity_row(row)
            try:
                records = frame_to_records(client.bars(symbol=identity["code"], frequency=9, start=0, offset=self.offset))
                matched = [record for record in records if parse_record_trade_date(record) == trade_date]
                if matched:
                    presence[identity["identity_key"]] = {
                        "present": True,
                        "source": "mootdx.stock_daily",
                        "evidence": select_bar_evidence(matched[-1]),
                    }
                else:
                    presence[identity["identity_key"]] = {
                        "present": False,
                        "source": "mootdx.stock_daily",
                        "evidence": {"checked": True, "reason": "no row for trade_date"},
                    }
            except Exception as exc:  # pragma: no cover - environment dependent
                presence[identity["identity_key"]] = {
                    "present": False,
                    "source": "mootdx.stock_daily",
                    "evidence": {"error": f"{type(exc).__name__}: {exc}"},
                }
        return {
            "trade_date": trade_date,
            "source": "mootdx.stock_daily.readonly",
            "source_available": True,
            "presence_by_identity_key": normalize_jsonable(presence),
        }

    def _get_client(self) -> Any:
        if self._client is None:
            quotes_module = importlib.import_module("mootdx.quotes")
            self._client = quotes_module.Quotes.factory(market="std")
        return self._client


def run_readiness_planner(
    *,
    dsn: str,
    tushare_token: str | None = None,
    trade_date: str = TRADE_DATE,
    db_snapshot: Mapping[str, Any] | None = None,
    tushare_snapshot: Mapping[str, Any] | None = None,
    tdx_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    db = dict(db_snapshot) if db_snapshot is not None else build_db_snapshot_from_db(dsn=dsn, trade_date=trade_date)
    tushare = (
        dict(tushare_snapshot)
        if tushare_snapshot is not None
        else DefaultTushareStockUniverseProbe(token=tushare_token).fetch_snapshot(trade_date=trade_date)
    )
    candidate_rows = [
        row
        for row in (db.get("candidate_rows") or [])
        if str(row.get("stock_identity_key") or row.get("identity_key")) in set(DAILY_MISSING_ACTIVE_IDENTITIES)
    ]
    tdx = (
        dict(tdx_snapshot)
        if tdx_snapshot is not None
        else DefaultMootdxStockDailyProbe().fetch_snapshot(candidates=candidate_rows, trade_date=trade_date)
    )
    return build_readiness_report(db_snapshot=db, tushare_snapshot=tushare, tdx_snapshot=tdx)


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# N1 Stock Universe Readiness 20260526 Report",
        "",
        "日期：2026-05-27",
        "layer_role：`N1_ingestion`",
        f"状态：`{report['result']}`",
        "",
        "## Summary",
        "",
        "```text",
        f"raw_active_universe = {report['raw_active_universe']}",
        f"effective_active_universe = {report['effective_active_universe']}",
        f"tushare_daily_matched = {report['tushare_daily_matched']}",
        f"unresolved_daily_missing_active = {report['unresolved_daily_missing_active']}",
        f"supplemental_source_available = {report['supplemental_source_available']}",
        f"P0/P1/P2 = {report['quality']['p0_count']}/{report['quality']['p1_count']}/{report['quality']['p2_count']}",
        "```",
        "",
        "## 19 Stock Disposition",
        "",
        "| identity_key | name | Tushare daily | adj_factor | TDX/Mootdx daily | disposition | severity |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for row in report.get("missing_stock_manifest") or []:
        lines.append(
            "| {identity_key} | {name} | {daily} | {adj} | {tdx} | {disp} | {sev} |".format(
                identity_key=row.get("identity_key"),
                name=row.get("name") or "",
                daily=row.get("tushare_daily_present", row.get("evidence", {}).get("tushare_daily_present")),
                adj=row.get("tushare_adj_factor_present", row.get("evidence", {}).get("tushare_adj_factor_present")),
                tdx=row.get("tdx_mootdx_daily_present", ""),
                disp=row.get("recommended_disposition"),
                sev=row.get("severity"),
            )
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "不写 PostgreSQL、不写 Parquet、不改 active_source_version、不进入 N2-N6、不启动 worker。",
        ]
    )
    return "\n".join(lines) + "\n"


def write_report_artifacts(report: Mapping[str, Any], *, json_path: Path = DEFAULT_JSON_PATH, md_path: Path = DEFAULT_MD_PATH) -> dict[str, str]:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(normalize_jsonable(report), ensure_ascii=False, indent=2) + "\n")
    md_path.write_text(render_markdown(report))
    return {"json": str(json_path), "markdown": str(md_path)}


def no_side_effects() -> dict[str, bool]:
    return {
        "writes_postgres": False,
        "writes_parquet": False,
        "updates_active_source_version": False,
        "enters_n2_n3_n4_n5_n6": False,
        "worker_started": False,
        "old_system_touched": False,
        "real_trading": False,
    }


def frame_to_records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        try:
            return [dict(row) for row in frame.to_dict(orient="records")]
        except TypeError:
            return [dict(row) for row in frame.to_dict("records")]
    if isinstance(frame, Mapping):
        return [dict(frame)]
    if isinstance(frame, Iterable) and not isinstance(frame, (str, bytes)):
        return [dict(row) for row in frame]
    return []


def parse_record_trade_date(record: Mapping[str, Any]) -> str | None:
    value = record.get("trade_date") or record.get("datetime") or record.get("date")
    if value is None and all(key in record for key in ("year", "month", "day")):
        return f"{int(record['year']):04d}{int(record['month']):02d}{int(record['day']):02d}"
    text = str(value)
    digits = "".join(ch for ch in text[:10] if ch.isdigit())
    if len(digits) >= 8:
        return digits[:8]
    return None


def select_bar_evidence(record: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("open", "high", "low", "close", "vol", "volume", "amount", "datetime")
    return {key: json_safe_value(record.get(key)) for key in keys if key in record}


def normalize_jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): normalize_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [normalize_jsonable(item) for item in value]
    return json_safe_value(value)


def json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    try:
        import math

        if isinstance(value, float) and math.isnan(value):
            return None
    except Exception:
        pass
    return str(value)
