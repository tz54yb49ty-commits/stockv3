"""N1 official daily 20260526 v2 execute runner support.

The v2 runner keeps the v1 final-gate shape, but changes the stock contract:
5504 Tushare daily rows, 16 TDX/Mootdx supplemental bars, 2 official no-trade
manifest rows, and 1 stale identity exclusion. This module is safe to import
and unit test; real source fetch and PostgreSQL commit only happen when the
run-once CLI receives all four explicit final-gate flags.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import importlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.ingestion.tushare_env import load_tushare_token
from ashare_v3.ingestion.official_daily_20260526_execute import (
    DefaultOfficialDaily20260526SourceAdapter as V1SourceAdapter,
    frame_to_records,
    has_valid_ohlc_amount,
    json_safe,
    to_optional_float,
    ts_code_from_scope,
)


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
TRADE_DATE = "20260526"
EXPECTED_PREV_TRADE_DATE = "20260525"
EXPECTED_NEXT_TRADE_DATE = "20260527"
BATCH_ID = "official_daily_ingest_20260526_v2"
CONTRACT_SOURCE_VERSION = BATCH_ID
SOURCE_VERSIONS = {
    "stock": "stock_daily_20260526_v2",
    "index": "index_daily_20260526_v2",
    "board": "board_daily_20260526_v2",
}
ACTIVE_DATA_TYPES = {
    "stock": "stock_daily",
    "index": "index_daily",
    "board": "board_daily",
}
EXPECTED_ROWS = {
    "stock_daily_bar_fact": 5520,
    "index_daily_bar_fact": 9,
    "board_daily_bar_fact": 428,
    "total_daily_fact": 5957,
}
STOCK_SCOPE_BREAKDOWN = {
    "raw_active_universe": 5523,
    "stale_identity_excluded": 1,
    "effective_active_universe": 5522,
    "tushare_daily_rows": 5504,
    "tdx_mootdx_supplemental_source_bar_rows": 16,
    "official_no_trade_manifest_rows": 2,
    "expected_stock_daily_bar_rows": 5520,
    "unresolved_source_gap": 0,
}
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
STALE_IDENTITY_KEY = "stock:SZ:300114"
STALE_IDENTITY_MANIFEST = (
    {
        "identity_key": STALE_IDENTITY_KEY,
        "ts_code": "300114.SZ",
        "name": "中航成飞",
        "disposition": "exclude_from_expected_universe",
        "severity": "P1",
        "superseded_by_identity_key": "stock:SZ:302132",
    },
)
OFFICIAL_NO_TRADE_IDENTITIES = ("stock:BJ:920058", "stock:BJ:920305")
OFFICIAL_NO_TRADE_MANIFEST_TEMPLATE = (
    {
        "identity_key": "stock:BJ:920058",
        "ts_code": "920058.BJ",
        "name": "华洋赛车",
        "disposition": "official_no_trade",
        "severity": "P1",
        "writes_stock_daily_bar_fact": False,
        "source_proof_json": {
            "suspend_d": {"trade_date": TRADE_DATE, "suspend_type": "S"},
            "bak_daily": {"trade_date": TRADE_DATE, "vol": 0.0, "amount": 0.0},
        },
    },
    {
        "identity_key": "stock:BJ:920305",
        "ts_code": "920305.BJ",
        "name": "*ST云创",
        "disposition": "official_no_trade",
        "severity": "P1",
        "writes_stock_daily_bar_fact": False,
        "source_proof_json": {
            "suspend_d": {"trade_date": TRADE_DATE, "suspend_type": "S"},
            "bak_daily": {"trade_date": TRADE_DATE, "vol": 0.0, "amount": 0.0},
        },
    },
)
SUPPLEMENTAL_IDENTITIES = (
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
ALLOWED_FUTURE_WRITE_TABLES = (
    "common_ingest_batch",
    "common_quality_gate_result",
    "common_active_source_version",
    "stock_daily_bar_fact",
    "index_daily_bar_fact",
    "board_daily_bar_fact",
)
FORBIDDEN_WRITE_TABLES = (
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "stock_daily_basic",
    "stock_financial_metrics_fact",
    "condition tables",
    "trigger/action/user/voice/mobile/sim/position tables",
    "Parquet",
    "worker",
    "old system",
    "real trading",
)
DEFAULT_PATHS = {
    "contract_json": Path("docs/N1_official_daily_20260526_v2_ingestion_execute_contract.json"),
    "contract_md": Path("docs/N1_OFFICIAL_DAILY_20260526_V2_INGESTION_EXECUTE_CONTRACT.md"),
    "preflight_json": Path("docs/N1_official_daily_20260526_v2_ingestion_execute_preflight.json"),
    "preflight_md": Path("docs/N1_OFFICIAL_DAILY_20260526_V2_INGESTION_EXECUTE_PREFLIGHT.md"),
    "rollback_sql": Path("sql/N1_official_daily_20260526_v2_ingestion_rollback.sql"),
}
BOARD_881_RE = re.compile(r"^881\d{3}$")
SOURCE_FETCH_ROUTES = {
    "stock_main": "Tushare daily + adj_factor proof",
    "stock_supplemental": "TDX/Mootdx stock daily for the 16 supplemental_source_bar identities",
    "stock_no_trade": "Tushare suspend_d + bak_daily manifest only",
    "index": "TDX/Mootdx preferred, Tushare index_daily fallback",
    "board": "TDX/Mootdx board daily",
}


class OfficialDaily20260526V2ExecuteBlocked(RuntimeError):
    """Raised when the 20260526 v2 official daily execute gate is blocked."""


def now_iso() -> str:
    return datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat()


def add_total(counts: Mapping[str, Any]) -> dict[str, int]:
    normalized = {
        "stock": int(counts.get("stock") or 0),
        "index": int(counts.get("index") or 0),
        "board": int(counts.get("board") or 0),
    }
    normalized["total"] = normalized["stock"] + normalized["index"] + normalized["board"]
    return normalized


def normalize_jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def no_side_effects() -> dict[str, bool]:
    return {
        "calls_external_market_sources": False,
        "writes_postgres": False,
        "writes_parquet": False,
        "updates_active_source_version": False,
        "writes_outbox": False,
        "writes_inbox_or_checkpoint": False,
        "enters_n2_n3_n4_n5_n6": False,
        "worker_started": False,
        "old_system_touched": False,
        "real_trading": False,
    }


def sample_pass_snapshot() -> dict[str, Any]:
    return {
        "trade_date": TRADE_DATE,
        "calendar": {
            "row_count": 1,
            "is_open": True,
            "prev_trade_date": EXPECTED_PREV_TRADE_DATE,
            "next_trade_date": EXPECTED_NEXT_TRADE_DATE,
            "source": "tushare.trade_cal.patch",
            "source_version": "trade_calendar_20260526_patch_v1",
        },
        "active_trade_calendar_count": 1,
        "current_daily_fact_rows": {"stock": 0, "index": 0, "board": 0},
        "active_daily_source_versions": [],
        "contract_batch_exists": False,
        "target_source_version_conflicts": {"stock": 0, "index": 0, "board": 0},
        "quality_rows_for_v2": 0,
        "stock_active_universe": STOCK_SCOPE_BREAKDOWN["raw_active_universe"],
        "fixed_9_index_present": 9,
        "fixed_9_index_missing": [],
        "board_total": 428,
        "board_881": 127,
        "event_counts": {"outbox": 74176, "inbox": 2952, "checkpoint": 2803},
        "read_only_database_checks": True,
    }


def validate_execute_request(
    *,
    execute_requested: bool,
    user_confirmed: bool,
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> None:
    if not execute_requested:
        raise OfficialDaily20260526V2ExecuteBlocked("missing --execute")
    if not user_confirmed:
        raise OfficialDaily20260526V2ExecuteBlocked("missing --user-confirmed")
    if not source_fetch_enabled:
        raise OfficialDaily20260526V2ExecuteBlocked("missing --source-fetch-enabled")
    if not postgres_commit_enabled:
        raise OfficialDaily20260526V2ExecuteBlocked("missing --postgres-commit-enabled")


class DefaultOfficialDaily20260526V2SourceAdapter:
    """Lazy real source adapter used only after explicit final execute flags."""

    def __init__(self, *, tushare_token: str | None = None, mootdx_offset: int = 800) -> None:
        self.tushare_token = tushare_token or load_tushare_token()
        self.mootdx_offset = mootdx_offset
        self._v1 = V1SourceAdapter(tushare_token=self.tushare_token, mootdx_offset=mootdx_offset)
        self._mootdx_client: Any | None = None
        self._tushare_client: Any | None = None

    def fetch_stock_daily(self, *, trade_date: str, expected_scope: list[dict[str, Any]]) -> list[dict[str, Any]]:
        main_scope = [row for row in expected_scope if str(row.get("identity_key")) not in set(SUPPLEMENTAL_IDENTITIES)]
        rows = self._v1.fetch_stock_daily(trade_date=trade_date, expected_scope=main_scope)
        return [self._retag_stock_row(row, source_type="tushare_daily") for row in rows]

    def fetch_supplemental_stock_daily(self, *, trade_date: str, expected_scope: list[dict[str, Any]]) -> list[dict[str, Any]]:
        client = self._get_mootdx_client()
        rows: list[dict[str, Any]] = []
        for scope_row in expected_scope:
            identity_key = str(scope_row.get("identity_key") or "")
            if identity_key not in set(SUPPLEMENTAL_IDENTITIES):
                continue
            records = frame_to_records(client.bars(symbol=str(scope_row.get("code") or ""), frequency=9, start=0, offset=self.mootdx_offset))
            matched = [record for record in records if parse_record_trade_date(record) == trade_date]
            if not matched:
                continue
            raw = matched[-1]
            proof = {
                "source": "mootdx.stock_daily",
                "trade_date": trade_date,
                "identity_key": identity_key,
                "raw_payload": json_safe(raw),
            }
            rows.append(
                {
                    "asset_kind": "stock",
                    "identity_key": identity_key,
                    "trade_date": trade_date,
                    "ts_code": ts_code_from_scope(scope_row),
                    "code": str(scope_row.get("code") or ""),
                    "exchange": str(scope_row.get("exchange") or ""),
                    "name": scope_row.get("name"),
                    "open": to_optional_float(raw.get("open")),
                    "high": to_optional_float(raw.get("high")),
                    "low": to_optional_float(raw.get("low")),
                    "close": to_optional_float(raw.get("close")),
                    "volume": to_optional_float(raw.get("vol")) or to_optional_float(raw.get("volume")),
                    "amount": to_optional_float(raw.get("amount")),
                    "adj_factor": to_optional_float(raw.get("adj_factor")),
                    "official_daily_proof": True,
                    "source_type": "supplemental_source_bar",
                    "source": "mootdx.stock_daily.supplemental",
                    "source_batch_id": BATCH_ID,
                    "source_version": SOURCE_VERSIONS["stock"],
                    "source_proof_json": proof,
                    "raw_payload": proof,
                }
            )
        return rows

    def fetch_official_no_trade_manifest(self, *, trade_date: str, identities: tuple[str, ...]) -> list[dict[str, Any]]:
        pro = self._pro()
        rows: list[dict[str, Any]] = []
        for identity_key in identities:
            _, exchange, code = identity_key.split(":")
            ts_code = f"{code}.{exchange}"
            suspend_rows = frame_to_records(pro.suspend_d(ts_code=ts_code, trade_date=trade_date))
            bak_rows = frame_to_records(pro.bak_daily(ts_code=ts_code, trade_date=trade_date))
            if not suspend_rows or not bak_rows:
                continue
            suspend = suspend_rows[0]
            bak = bak_rows[0]
            if str(suspend.get("suspend_type") or "") != "S":
                continue
            rows.append(
                {
                    "identity_key": identity_key,
                    "ts_code": ts_code,
                    "disposition": "official_no_trade",
                    "writes_stock_daily_bar_fact": False,
                    "source_proof_json": {
                        "suspend_d": json_safe(suspend),
                        "bak_daily": json_safe(bak),
                    },
                }
            )
        return rows

    def fetch_index_daily(self, *, trade_date: str, expected_scope: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = self._v1.fetch_index_daily(trade_date=trade_date, expected_scope=expected_scope)
        return [self._retag_asset_row(row, asset="index") for row in rows]

    def fetch_board_daily(self, *, trade_date: str, expected_scope: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = self._v1.fetch_board_daily(trade_date=trade_date, expected_scope=expected_scope)
        return [self._retag_asset_row(row, asset="board") for row in rows]

    def _retag_stock_row(self, row: Mapping[str, Any], *, source_type: str) -> dict[str, Any]:
        retagged = dict(row)
        retagged["source_batch_id"] = BATCH_ID
        retagged["source_version"] = SOURCE_VERSIONS["stock"]
        retagged["source_type"] = source_type
        return retagged

    def _retag_asset_row(self, row: Mapping[str, Any], *, asset: str) -> dict[str, Any]:
        retagged = dict(row)
        retagged["source_batch_id"] = BATCH_ID
        retagged["source_version"] = SOURCE_VERSIONS[asset]
        return retagged

    def _get_mootdx_client(self) -> Any:
        if self._mootdx_client is None:
            quotes_module = importlib.import_module("mootdx.quotes")
            self._mootdx_client = quotes_module.Quotes.factory(market="std")
        return self._mootdx_client

    def _pro(self) -> Any:
        if self._tushare_client is None:
            if not self.tushare_token:
                raise OfficialDaily20260526V2ExecuteBlocked("TUSHARE_TOKEN is required for official no-trade proof")
            tushare = importlib.import_module("tushare")
            self._tushare_client = tushare.pro_api(self.tushare_token)
        return self._tushare_client


def fetch_official_daily_sources(
    *,
    adapter: Any,
    trade_date: str,
    expected_scope: Mapping[str, Any],
    source_fetch_enabled: bool,
) -> dict[str, Any]:
    if not source_fetch_enabled:
        raise OfficialDaily20260526V2ExecuteBlocked("missing --source-fetch-enabled")
    scope = normalize_expected_scope(expected_scope)
    stock_main = list(adapter.fetch_stock_daily(trade_date=trade_date, expected_scope=scope["stock"]))
    stock_supplemental = list(adapter.fetch_supplemental_stock_daily(trade_date=trade_date, expected_scope=scope["stock"]))
    no_trade_manifest = list(adapter.fetch_official_no_trade_manifest(trade_date=trade_date, identities=OFFICIAL_NO_TRADE_IDENTITIES))
    rows = {
        "stock": [*stock_main, *stock_supplemental],
        "index": list(adapter.fetch_index_daily(trade_date=trade_date, expected_scope=scope["index"])),
        "board": list(adapter.fetch_board_daily(trade_date=trade_date, expected_scope=scope["board"])),
    }
    return normalize_jsonable(
        {
            "trade_date": trade_date,
            "routes": SOURCE_FETCH_ROUTES,
            "source_breakdown": {
                "stock_tushare_daily": len(stock_main),
                "stock_supplemental_source_bar": len(stock_supplemental),
                "official_no_trade": len(no_trade_manifest),
                "stale_identity_excluded": len(STALE_IDENTITY_MANIFEST),
                "unresolved_source_gap": 0,
            },
            "row_counts": add_total({asset: len(rows[asset]) for asset in ("stock", "index", "board")}),
            "official_no_trade_manifest": no_trade_manifest,
            "stale_identity_manifest": list(STALE_IDENTITY_MANIFEST),
            "unresolved_source_gap": [],
            **rows,
        }
    )


def validate_source_bundle(*, bundle: Mapping[str, Any], expected_scope: Mapping[str, Any], trade_date: str) -> dict[str, Any]:
    rows_by_asset = normalize_bundle_rows(bundle)
    scope = normalize_expected_scope(expected_scope)
    blockers: list[str] = []
    quality_items: list[dict[str, Any]] = []

    for asset in ("stock", "index", "board"):
        expected_ids = {str(row.get("identity_key")) for row in scope[asset] if row.get("identity_key")}
        actual_ids = [str(row.get("identity_key") or "") for row in rows_by_asset[asset]]
        actual_set = set(actual_ids)
        missing = sorted(expected_ids - actual_set)
        if missing:
            add_once(blockers, f"{asset}_expected_coverage")
        quality_items.append(
            quality_item(
                f"{asset}_expected_coverage",
                severity="P0",
                status="passed" if not missing else "failed",
                expected=len(expected_ids),
                actual=len(expected_ids) - len(missing),
                details={"missing_sample": missing[:10]},
            )
        )

        duplicate_ids = sorted(identity for identity, count in Counter(actual_ids).items() if identity and count > 1)
        if duplicate_ids:
            add_once(blockers, "duplicate_identity_key")
        quality_items.append(
            quality_item(
                f"{asset}_duplicate_identity_key",
                severity="P0",
                status="passed" if not duplicate_ids else "failed",
                expected=0,
                actual=len(duplicate_ids),
                details={"duplicate_sample": duplicate_ids[:10]},
            )
        )

        contract_errors = [
            row_identity(row)
            for row in rows_by_asset[asset]
            if row.get("source_batch_id") != BATCH_ID
            or row.get("source_version") != SOURCE_VERSIONS[asset]
            or str(row.get("trade_date")) != trade_date
        ]
        if contract_errors:
            add_once(blockers, "source_contract_mismatch")
        quality_items.append(
            quality_item(
                f"{asset}_source_contract",
                severity="P0",
                status="passed" if not contract_errors else "failed",
                expected=f"{trade_date}/{BATCH_ID}/{SOURCE_VERSIONS[asset]}",
                actual=len(contract_errors),
                details={"failed_sample": contract_errors[:10]},
            )
        )

        sanity_errors = [row_identity(row) for row in rows_by_asset[asset] if not has_valid_ohlc_amount(row)]
        if sanity_errors:
            add_once(blockers, "ohlc_volume_amount_sanity")
        quality_items.append(
            quality_item(
                f"{asset}_ohlc_volume_amount_sanity",
                severity="P0",
                status="passed" if not sanity_errors else "failed",
                expected=0,
                actual=len(sanity_errors),
                details={"failed_sample": sanity_errors[:10]},
            )
        )

    expected_counts = {
        "stock": EXPECTED_ROWS["stock_daily_bar_fact"],
        "index": EXPECTED_ROWS["index_daily_bar_fact"],
        "board": EXPECTED_ROWS["board_daily_bar_fact"],
    }
    for asset, expected_count in expected_counts.items():
        actual_count = len(rows_by_asset[asset])
        if actual_count != expected_count:
            add_once(blockers, f"{asset}_row_count_mismatch")
        quality_items.append(
            quality_item(
                f"{asset}_row_count",
                severity="P0",
                status="passed" if actual_count == expected_count else "failed",
                expected=expected_count,
                actual=actual_count,
            )
        )

    stock_rows = rows_by_asset["stock"]
    tushare_rows = [row for row in stock_rows if row.get("source_type") == "tushare_daily"]
    supplemental_rows = [row for row in stock_rows if row.get("source_type") == "supplemental_source_bar"]
    if len(tushare_rows) != STOCK_SCOPE_BREAKDOWN["tushare_daily_rows"]:
        add_once(blockers, "tushare_daily_count_mismatch")
    quality_items.append(
        quality_item(
            "stock_tushare_daily_count",
            severity="P0",
            status="passed" if len(tushare_rows) == STOCK_SCOPE_BREAKDOWN["tushare_daily_rows"] else "failed",
            expected=STOCK_SCOPE_BREAKDOWN["tushare_daily_rows"],
            actual=len(tushare_rows),
        )
    )
    if len(supplemental_rows) != STOCK_SCOPE_BREAKDOWN["tdx_mootdx_supplemental_source_bar_rows"]:
        add_once(blockers, "supplemental_source_bar_count_mismatch")
    quality_items.append(
        quality_item(
            "supplemental_source_bar_manifest",
            severity="P1",
            status="warning",
            expected=STOCK_SCOPE_BREAKDOWN["tdx_mootdx_supplemental_source_bar_rows"],
            actual=len(supplemental_rows),
            details={"requires_source_proof_json": True},
        )
    )
    supplemental_without_proof = [
        row_identity(row)
        for row in supplemental_rows
        if not (row.get("source_proof_json") or (row.get("raw_payload") or {}).get("source_proof_json"))
    ]
    if supplemental_without_proof:
        add_once(blockers, "supplemental_source_proof_missing")
    quality_items.append(
        quality_item(
            "supplemental_source_proof",
            severity="P0",
            status="passed" if not supplemental_without_proof else "failed",
            expected=0,
            actual=len(supplemental_without_proof),
            details={"failed_sample": supplemental_without_proof[:10]},
        )
    )

    no_trade_manifest = [dict(row) for row in bundle.get("official_no_trade_manifest") or []]
    no_trade_ids = {str(row.get("identity_key") or "") for row in no_trade_manifest}
    no_trade_inserted = sorted({row_identity(row) for row in stock_rows if row_identity(row) in set(OFFICIAL_NO_TRADE_IDENTITIES)})
    if no_trade_inserted:
        add_once(blockers, "official_no_trade_inserted_as_bar")
    no_trade_ok = no_trade_ids == set(OFFICIAL_NO_TRADE_IDENTITIES) and all(row.get("writes_stock_daily_bar_fact") is False for row in no_trade_manifest)
    if not no_trade_ok:
        add_once(blockers, "official_no_trade_manifest_mismatch")
    quality_items.append(
        quality_item(
            "official_no_trade_manifest",
            severity="P1",
            status="warning" if no_trade_ok and not no_trade_inserted else "failed",
            expected=len(OFFICIAL_NO_TRADE_IDENTITIES),
            actual=len(no_trade_manifest),
            details={"identity_keys": sorted(no_trade_ids), "inserted_as_bar": no_trade_inserted},
        )
    )
    quality_items.append(
        quality_item(
            "official_no_trade_guard",
            severity="P0",
            status="passed" if no_trade_ok and not no_trade_inserted else "failed",
            expected={"manifest_rows": 2, "inserted_bar_rows": 0},
            actual={"manifest_rows": len(no_trade_manifest), "inserted_bar_rows": len(no_trade_inserted)},
            details={"identity_keys": sorted(no_trade_ids), "inserted_as_bar": no_trade_inserted},
        )
    )

    stale_manifest = [dict(row) for row in bundle.get("stale_identity_manifest") or []]
    stale_inserted = sorted({row_identity(row) for row in stock_rows if row_identity(row) == STALE_IDENTITY_KEY})
    stale_ok = len(stale_manifest) == 1 and str(stale_manifest[0].get("identity_key") or "") == STALE_IDENTITY_KEY
    if stale_inserted:
        add_once(blockers, "stale_identity_inserted_as_bar")
    if not stale_ok:
        add_once(blockers, "stale_identity_manifest_mismatch")
    quality_items.append(
        quality_item(
            "stale_identity_excluded",
            severity="P1",
            status="warning" if stale_ok and not stale_inserted else "failed",
            expected=1,
            actual=len(stale_manifest),
            details={"inserted_as_bar": stale_inserted, "identity_key": STALE_IDENTITY_KEY},
        )
    )
    quality_items.append(
        quality_item(
            "stale_identity_guard",
            severity="P0",
            status="passed" if stale_ok and not stale_inserted else "failed",
            expected={"manifest_rows": 1, "inserted_bar_rows": 0},
            actual={"manifest_rows": len(stale_manifest), "inserted_bar_rows": len(stale_inserted)},
            details={"inserted_as_bar": stale_inserted, "identity_key": STALE_IDENTITY_KEY},
        )
    )

    unresolved = [dict(row) for row in bundle.get("unresolved_source_gap") or []]
    if unresolved:
        add_once(blockers, "unresolved_source_gap")
    quality_items.append(
        quality_item(
            "unresolved_source_gap",
            severity="P0",
            status="passed" if not unresolved else "failed",
            expected=0,
            actual=len(unresolved),
            details={"sample": unresolved[:10]},
        )
    )

    stock_proof_errors = [
        row_identity(row)
        for row in tushare_rows
        if row.get("official_daily_proof") is not True or row.get("adj_factor") is None
    ]
    if stock_proof_errors:
        add_once(blockers, "stock_adj_factor_proof_missing")
    quality_items.append(
        quality_item(
            "stock_adj_factor_proof",
            severity="P0",
            status="passed" if not stock_proof_errors else "failed",
            expected=len(tushare_rows),
            actual=len(tushare_rows) - len(stock_proof_errors),
            details={"failed_sample": stock_proof_errors[:10]},
        )
    )

    contamination = detect_same_code_contamination(rows_by_asset)
    if contamination:
        add_once(blockers, "same_code_contamination")
    quality_items.append(
        quality_item(
            "same_code_contamination",
            severity="P0",
            status="passed" if not contamination else "failed",
            expected=0,
            actual=len(contamination),
            details={"sample": contamination[:10]},
        )
    )

    index_ids = {row_identity(row) for row in rows_by_asset["index"]}
    missing_fixed_9 = sorted(set(FIXED_9_INDEX_IDENTITIES) - index_ids)
    if missing_fixed_9:
        add_once(blockers, "fixed_9_index_missing")
    quality_items.append(
        quality_item(
            "fixed_9_index_coverage",
            severity="P0",
            status="passed" if not missing_fixed_9 else "failed",
            expected=len(FIXED_9_INDEX_IDENTITIES),
            actual=len(FIXED_9_INDEX_IDENTITIES) - len(missing_fixed_9),
            details={"missing": missing_fixed_9},
        )
    )

    actual_881 = {row_identity(row) for row in rows_by_asset["board"] if BOARD_881_RE.match(str(row.get("board_code") or row.get("code") or ""))}
    if len(actual_881) != 127:
        add_once(blockers, "board_881_coverage_missing")
    quality_items.append(
        quality_item(
            "board_881_required_coverage",
            severity="P0",
            status="passed" if len(actual_881) == 127 else "failed",
            expected=127,
            actual=len(actual_881),
        )
    )

    quality = summarize_quality(quality_items)
    return normalize_jsonable(
        {
            "result": "VALIDATION_PASS" if quality["p0_count"] == 0 else "VALIDATION_BLOCKED",
            "p0_count": quality["p0_count"],
            "blockers": sorted(dict.fromkeys(blockers)),
            "row_counts": add_total({asset: len(rows_by_asset[asset]) for asset in ("stock", "index", "board")}),
            "stock_breakdown": {
                "tushare_daily_rows": len(tushare_rows),
                "supplemental_source_bar_rows": len(supplemental_rows),
                "official_no_trade_manifest_rows": len(no_trade_manifest),
                "stale_identity_manifest_rows": len(stale_manifest),
                "unresolved_source_gap": len(unresolved),
            },
            "quality": quality,
            "quality_items": quality_items,
        }
    )


def validate_commit_preconditions(
    *,
    snapshot: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> None:
    blockers = build_blockers(snapshot)
    if not source_fetch_enabled:
        blockers.append("source_fetch_disabled")
    if not postgres_commit_enabled:
        blockers.append("postgres_commit_disabled")
    if int(validation_report.get("p0_count") or 0) != 0:
        blockers.extend(str(blocker) for blocker in validation_report.get("blockers") or ["source_validation_p0"])
    if blockers:
        raise OfficialDaily20260526V2ExecuteBlocked(", ".join(sorted(dict.fromkeys(blockers))))


def build_commit_plan(
    *,
    bundle: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    baseline: Mapping[str, Any],
    trade_date: str,
) -> dict[str, Any]:
    if int(validation_report.get("p0_count") or 0) != 0:
        raise OfficialDaily20260526V2ExecuteBlocked("source validation P0 must be zero before commit plan")
    rows_by_asset = normalize_bundle_rows(bundle)
    quality_rows = [
        {
            "source_batch_id": BATCH_ID,
            "source_version": CONTRACT_SOURCE_VERSION,
            "data_domain": "common",
            "data_type": "official_daily",
            "gate_name": item["gate_name"],
            "severity": item["severity"],
            "status": item["status"],
            "expected_value": str(item.get("expected")),
            "actual_value": str(item.get("actual")),
            "details": item.get("details") or {},
        }
        for item in validation_report.get("quality_items") or []
    ]
    quality_rows.append(
        {
            "source_batch_id": BATCH_ID,
            "source_version": CONTRACT_SOURCE_VERSION,
            "data_domain": "common",
            "data_type": "official_daily",
            "gate_name": "v2_manifest_details",
            "severity": "P1",
            "status": "warning",
            "expected_value": "stale=1,no_trade=2,supplemental=16",
            "actual_value": json.dumps(validation_report.get("stock_breakdown") or {}, ensure_ascii=False),
            "details": {
                "official_no_trade_manifest": bundle.get("official_no_trade_manifest") or [],
                "stale_identity_manifest": bundle.get("stale_identity_manifest") or [],
                "supplemental_identities": list(SUPPLEMENTAL_IDENTITIES),
            },
        }
    )
    active_rows = [
        {
            "data_domain": asset,
            "data_type": ACTIVE_DATA_TYPES[asset],
            "scope_key": trade_date,
            "source_version": SOURCE_VERSIONS[asset],
            "source_batch_id": BATCH_ID,
            "previous_source_version": previous_active_source_version(baseline, asset),
            "activated_by": "n1_official_daily_20260526_v2_execute_runner",
        }
        for asset in ("stock", "index", "board")
    ]
    return normalize_jsonable(
        {
            "trade_date": trade_date,
            "batch_id": BATCH_ID,
            "contract_source_version": CONTRACT_SOURCE_VERSION,
            "source_versions": dict(SOURCE_VERSIONS),
            "allowed_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
            "row_counts": add_total({asset: len(rows_by_asset[asset]) for asset in ("stock", "index", "board")}),
            "rows": rows_by_asset,
            "quality_rows": quality_rows,
            "active_source_version_rows": active_rows,
            "manifest": {
                "official_no_trade": bundle.get("official_no_trade_manifest") or [],
                "stale_identity": bundle.get("stale_identity_manifest") or [],
                "supplemental_identities": list(SUPPLEMENTAL_IDENTITIES),
            },
            "side_effects": {
                "writes_parquet": False,
                "writes_outbox": False,
                "writes_inbox_or_checkpoint": False,
                "enters_n2_n3_n4_n5_n6": False,
            },
        }
    )


def execute_commit_transaction(
    conn: Any,
    *,
    commit_plan: Mapping[str, Any],
    execute_requested: bool,
    user_confirmed: bool,
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    validate_execute_request(
        execute_requested=execute_requested,
        user_confirmed=user_confirmed,
        source_fetch_enabled=source_fetch_enabled,
        postgres_commit_enabled=postgres_commit_enabled,
    )
    unexpected_tables = sorted(set(commit_plan.get("allowed_tables") or []) - set(ALLOWED_FUTURE_WRITE_TABLES))
    if unexpected_tables:
        raise OfficialDaily20260526V2ExecuteBlocked(f"unexpected write tables: {unexpected_tables}")

    cur = conn.cursor()
    try:
        insert_ingest_batch(cur, commit_plan)
        for row in (commit_plan.get("rows") or {}).get("stock", []):
            insert_stock_daily_bar_fact(cur, row)
        for row in (commit_plan.get("rows") or {}).get("index", []):
            insert_index_daily_bar_fact(cur, row)
        for row in (commit_plan.get("rows") or {}).get("board", []):
            insert_board_daily_bar_fact(cur, row)
        for row in commit_plan.get("quality_rows") or []:
            insert_quality_gate_result(cur, row)
        for row in commit_plan.get("active_source_version_rows") or []:
            insert_active_source_version(cur, row)
        update_ingest_batch_passed(cur, commit_plan)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return normalize_jsonable(
        {
            "committed": True,
            "batch_id": commit_plan.get("batch_id"),
            "written_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
            "row_counts": commit_plan.get("row_counts") or {},
            "rollback_safe": True,
            "rollback_sql_path": str(DEFAULT_PATHS["rollback_sql"]),
        }
    )


def build_execute_preflight_report(
    snapshot: Mapping[str, Any],
    *,
    execute_requested: bool,
    user_confirmed: bool,
    source_fetch_enabled: bool = False,
    postgres_commit_enabled: bool = False,
) -> dict[str, Any]:
    blockers = build_blockers(snapshot)
    if execute_requested and not user_confirmed:
        blockers.append("missing_user_confirmed")
    if execute_requested and user_confirmed and not source_fetch_enabled:
        blockers.append("source_fetch_disabled")
    if execute_requested and user_confirmed and not postgres_commit_enabled:
        blockers.append("postgres_commit_disabled")
    blockers = sorted(dict.fromkeys(blockers))
    quality = build_preflight_quality(snapshot)
    return normalize_jsonable(
        {
            "stage": "N1 official daily 20260526 v2 ingestion execute preflight",
            "layer_role": "N1_ingestion",
            "result": "PREFLIGHT_BLOCKED" if blockers else "PREFLIGHT_PASS",
            "blocked": bool(blockers),
            "blockers": blockers,
            "trade_date": TRADE_DATE,
            "source_batch_id": BATCH_ID,
            "source_versions": dict(SOURCE_VERSIONS),
            "execute_authorized": False,
            "final_gate_required": True,
            "final_execute_gate_allowed": not bool(blockers),
            "runner_readiness": "blocked" if blockers else "ready_for_final_gate",
            "execute_runner_implemented": True,
            "source_fetch_implemented": True,
            "postgres_commit_implemented": True,
            "execute_flags_seen": {
                "execute": bool(execute_requested),
                "user_confirmed": bool(user_confirmed),
                "source_fetch_enabled": bool(source_fetch_enabled),
                "postgres_commit_enabled": bool(postgres_commit_enabled),
            },
            "baseline": {
                "calendar": snapshot.get("calendar") or {},
                "active_trade_calendar_count": int(snapshot.get("active_trade_calendar_count") or 0),
                "current_daily_fact_rows": add_total(snapshot.get("current_daily_fact_rows") or {}),
                "active_daily_source_versions": list(snapshot.get("active_daily_source_versions") or []),
                "contract_batch_exists": bool(snapshot.get("contract_batch_exists")),
                "target_source_version_conflicts": add_total(snapshot.get("target_source_version_conflicts") or {}),
                "quality_rows_for_v2": int(snapshot.get("quality_rows_for_v2") or 0),
                "event_counts": snapshot.get("event_counts") or {},
            },
            "expected_rows": dict(EXPECTED_ROWS),
            "stock_scope_breakdown": dict(STOCK_SCOPE_BREAKDOWN),
            "source_fetch": {
                "implemented": True,
                "routes": SOURCE_FETCH_ROUTES,
                "enabled_for_this_run": bool(source_fetch_enabled),
                "will_call_external_sources_this_preflight": False,
            },
            "postgres_commit": {
                "implemented": True,
                "single_transaction": True,
                "enabled_for_this_run": bool(postgres_commit_enabled),
                "allowed_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
                "will_write_postgres_this_preflight": False,
            },
            "execute_pipeline": {
                "wired": True,
                "enabled_for_this_run": bool(execute_requested and user_confirmed and source_fetch_enabled and postgres_commit_enabled),
                "sequence": [
                    "load_contract",
                    "refresh_db_baseline",
                    "fetch_tushare_stock_daily_and_adj_factor",
                    "fetch_tdx_mootdx_supplemental_stock_daily",
                    "fetch_official_no_trade_manifest",
                    "fetch_index_daily",
                    "fetch_board_daily",
                    "validate_source_bundle",
                    "validate_commit_preconditions",
                    "build_commit_plan",
                    "execute_commit_transaction",
                ],
                "tests_use_mock_source": True,
            },
            "quality": quality,
            "expected_future_writes": {
                "allowed_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
                "writes_postgres": True,
                "writes_parquet": False,
                "updates_active_source_version": True,
                "writes_outbox": False,
                "enters_n2_n3_n4_n5_n6": False,
            },
            "rollback": {
                "path": str(DEFAULT_PATHS["rollback_sql"]),
                "source_batch_id": BATCH_ID,
                "source_versions": dict(SOURCE_VERSIONS),
                "rollback_safe": True,
            },
            "execute_command_template": (
                "PYTHONPATH=src python3 scripts/run_official_daily_ingestion_20260526_v2_once.py "
                "--trade-date 20260526 --execute --user-confirmed --source-fetch-enabled --postgres-commit-enabled"
            ),
            "side_effects": no_side_effects(),
            "generated_at": now_iso(),
        }
    )


def build_execute_contract(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    quality = build_preflight_quality(snapshot)
    return normalize_jsonable(
        {
            "stage": "N1 official daily 20260526 v2 ingestion execute contract",
            "layer_role": "N1_ingestion",
            "result": "DESIGN_PASS" if quality["p0_count"] == 0 else "DESIGN_BLOCKED",
            "trade_date": TRADE_DATE,
            "contract_batch_id": BATCH_ID,
            "contract_source_version": CONTRACT_SOURCE_VERSION,
            "source_versions": dict(SOURCE_VERSIONS),
            "expected_rows": dict(EXPECTED_ROWS),
            "stock_scope_breakdown": dict(STOCK_SCOPE_BREAKDOWN),
            "execute_flags": ["--execute", "--user-confirmed", "--source-fetch-enabled", "--postgres-commit-enabled"],
            "source_contract": {
                "stock_main": SOURCE_FETCH_ROUTES["stock_main"],
                "stock_supplemental": SOURCE_FETCH_ROUTES["stock_supplemental"],
                "stock_no_trade": SOURCE_FETCH_ROUTES["stock_no_trade"],
                "index": SOURCE_FETCH_ROUTES["index"],
                "board": SOURCE_FETCH_ROUTES["board"],
                "forbidden_sources": ["N3 snapshot", "C2/C2B summary", "C3 outbox", "old system", "manual OHLC"],
            },
            "manifests": {
                "stale_identity": list(STALE_IDENTITY_MANIFEST),
                "official_no_trade": list(OFFICIAL_NO_TRADE_MANIFEST_TEMPLATE),
                "supplemental_source_bar_count": len(SUPPLEMENTAL_IDENTITIES),
            },
            "quality_gate": {
                "p0_must_equal_zero": True,
                "expected_p0_p1_p2": {"p0": 0, "p1": 19, "p2": 0},
                "current_contract_quality": quality,
            },
            "future_write_scope": {
                "allowed_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
                "single_transaction": True,
                "postgres_only": True,
                "writes_parquet": False,
            },
            "idempotency": {
                "block_existing_batch_id": True,
                "block_existing_source_version": True,
                "block_existing_active_source_version": True,
                "block_existing_v1_active_source_version": True,
                "overwrite_active_source_version": False,
            },
            "implementation_status": {
                "execute_runner_implemented": True,
                "source_fetch_adapter_routing": True,
                "source_bundle_validation": True,
                "postgres_commit_transaction": True,
                "cli_execute_pipeline_wired": True,
                "execute_authorized": False,
                "final_execute_gate_allowed": quality["p0_count"] == 0 and not build_blockers(snapshot),
            },
            "rollback": {
                "path": str(DEFAULT_PATHS["rollback_sql"]),
                "strategy": "delete by trade_date/source_batch_id/source_version and remove this active source_version",
                "do_not_touch_v1": True,
                "do_not_touch_calendar_patch": True,
                "do_not_touch_parquet_or_outbox_or_n2_n6": True,
            },
            "forbidden_scope": list(FORBIDDEN_WRITE_TABLES),
            "side_effects": no_side_effects(),
            "generated_at": now_iso(),
        }
    )


def build_snapshot_from_db(*, dsn: str, trade_date: str = TRADE_DATE) -> dict[str, Any]:
    if trade_date != TRADE_DATE:
        raise ValueError("This runner is fixed to trade_date=20260526")
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            snapshot = {
                "trade_date": TRADE_DATE,
                "calendar": fetch_calendar(cur),
                "active_trade_calendar_count": scalar_count(
                    cur,
                    """
                    SELECT count(*)
                    FROM common_active_source_version
                    WHERE data_domain = 'common'
                      AND data_type = 'trade_calendar'
                      AND scope_key = 'SSE:20260526'
                    """,
                ),
                "current_daily_fact_rows": fetch_current_daily_fact_rows(cur),
                "active_daily_source_versions": fetch_active_daily_source_versions(cur),
                "contract_batch_exists": scalar_count(cur, "SELECT count(*) FROM common_ingest_batch WHERE batch_id = %s", (BATCH_ID,)) > 0,
                "target_source_version_conflicts": fetch_target_source_version_conflicts(cur),
                "quality_rows_for_v2": scalar_count(cur, "SELECT count(*) FROM common_quality_gate_result WHERE source_batch_id = %s", (BATCH_ID,)),
                "stock_active_universe": scalar_count(cur, "SELECT count(*) FROM stock_identity WHERE status = 'active'"),
                "fixed_9_index_present": fetch_fixed_9_index_present(cur),
                "fixed_9_index_missing": fetch_fixed_9_index_missing(cur),
                "board_total": scalar_count(cur, "SELECT count(*) FROM board_identity"),
                "board_881": scalar_count(cur, "SELECT count(*) FROM board_identity WHERE board_code LIKE '881%%'"),
                "event_counts": {
                    "outbox": scalar_count(cur, "SELECT count(*) FROM common_event_outbox"),
                    "inbox": scalar_count(cur, "SELECT count(*) FROM common_event_inbox"),
                    "checkpoint": scalar_count(cur, "SELECT count(*) FROM common_event_consumer_checkpoint"),
                },
                "read_only_database_checks": True,
            }
    return normalize_jsonable(snapshot)


def build_expected_scope_from_db(*, dsn: str, trade_date: str = TRADE_DATE) -> dict[str, list[dict[str, Any]]]:
    if trade_date != TRADE_DATE:
        raise ValueError("This runner is fixed to trade_date=20260526")
    excluded_stock = [STALE_IDENTITY_KEY, *OFFICIAL_NO_TRADE_IDENTITIES]
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT stock_identity_key AS identity_key, exchange, code, name, ts_code
                FROM stock_identity
                WHERE status = 'active'
                  AND stock_identity_key <> ALL(%s)
                ORDER BY stock_identity_key
                """,
                (excluded_stock,),
            )
            stock_scope = [tag_stock_scope_row(dict(row)) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT index_identity_key AS identity_key, exchange, code, name, ts_code
                FROM index_identity
                WHERE index_identity_key = ANY(%s)
                """,
                (list(FIXED_9_INDEX_IDENTITIES),),
            )
            index_rows = [dict(row) for row in cur.fetchall()]
            order = {identity_key: index for index, identity_key in enumerate(FIXED_9_INDEX_IDENTITIES)}
            index_scope = sorted(index_rows, key=lambda row: order.get(str(row["identity_key"]), 999))
            cur.execute(
                """
                SELECT board_identity_key AS identity_key, 'TDX' AS exchange,
                       board_code AS code, board_name AS name, board_type
                FROM board_identity
                ORDER BY board_identity_key
                """
            )
            board_scope = [dict(row) for row in cur.fetchall()]
    return normalize_jsonable({"stock": stock_scope, "index": index_scope, "board": board_scope})


def load_execute_contract(path: str | Path = DEFAULT_PATHS["contract_json"]) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def validate_execute_contract(contract: Mapping[str, Any]) -> None:
    if contract.get("result") != "DESIGN_PASS":
        raise OfficialDaily20260526V2ExecuteBlocked("execute_contract_not_design_pass")
    if contract.get("contract_batch_id") != BATCH_ID:
        raise OfficialDaily20260526V2ExecuteBlocked("execute_contract_batch_id_mismatch")
    if dict(contract.get("source_versions") or {}) != dict(SOURCE_VERSIONS):
        raise OfficialDaily20260526V2ExecuteBlocked("execute_contract_source_versions_mismatch")


def write_preflight_files(report: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    json_target = Path(json_path)
    markdown_target = Path(markdown_path)
    json_target.parent.mkdir(parents=True, exist_ok=True)
    markdown_target.parent.mkdir(parents=True, exist_ok=True)
    json_target.write_text(json.dumps(normalize_jsonable(report), ensure_ascii=False, indent=2) + "\n")
    markdown_target.write_text(render_preflight_markdown(report))


def write_contract_files(contract: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    json_target = Path(json_path)
    markdown_target = Path(markdown_path)
    json_target.parent.mkdir(parents=True, exist_ok=True)
    markdown_target.parent.mkdir(parents=True, exist_ok=True)
    json_target.write_text(json.dumps(normalize_jsonable(contract), ensure_ascii=False, indent=2) + "\n")
    markdown_target.write_text(render_contract_markdown(contract))


def render_preflight_markdown(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    return "\n".join(
        [
            "# N1 Official Daily 20260526 V2 Ingestion Execute Preflight",
            "",
            "日期：2026-05-27",
            "layer_role：`N1_ingestion`",
            f"状态：`{report.get('result')}`",
            "",
            "## Summary",
            "",
            "```text",
            f"trade_date = {TRADE_DATE}",
            f"source_batch_id = {BATCH_ID}",
            f"blocked = {report.get('blocked')}",
            f"blockers = {', '.join(report.get('blockers') or []) or 'none'}",
            f"P0/P1/P2 = {quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}",
            f"runner_readiness = {report.get('runner_readiness')}",
            f"source_fetch_implemented = {report.get('source_fetch_implemented')}",
            f"postgres_commit_implemented = {report.get('postgres_commit_implemented')}",
            "execute_authorized = false",
            "```",
            "",
            "## V2 Expected Rows",
            "",
            "```json",
            json.dumps(report.get("expected_rows") or {}, ensure_ascii=False, indent=2),
            "```",
            "",
            "## Execute Pipeline",
            "",
            "```json",
            json.dumps(report.get("execute_pipeline") or {}, ensure_ascii=False, indent=2),
            "```",
            "",
            "No `official_no_trade` rows are written to `stock_daily_bar_fact`; they remain manifest/quality details only.",
            "",
        ]
    )


def render_contract_markdown(contract: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# N1 Official Daily 20260526 V2 Ingestion Execute Contract",
            "",
            "日期：2026-05-27",
            "layer_role：`N1_ingestion`",
            f"状态：`{contract.get('result')}`",
            "",
            "## Identity",
            "",
            "```text",
            f"source_batch_id = {BATCH_ID}",
            f"stock source_version = {SOURCE_VERSIONS['stock']}",
            f"index source_version = {SOURCE_VERSIONS['index']}",
            f"board source_version = {SOURCE_VERSIONS['board']}",
            "```",
            "",
            "## V2 Expected",
            "",
            "```json",
            json.dumps(contract.get("expected_rows") or {}, ensure_ascii=False, indent=2),
            "```",
            "",
            "## Implementation Status",
            "",
            "```json",
            json.dumps(contract.get("implementation_status") or {}, ensure_ascii=False, indent=2),
            "```",
            "",
            "## Execute Command Candidate",
            "",
            "```bash",
            "PYTHONPATH=src python3 scripts/run_official_daily_ingestion_20260526_v2_once.py \\",
            "  --trade-date 20260526 \\",
            "  --execute \\",
            "  --user-confirmed \\",
            "  --source-fetch-enabled \\",
            "  --postgres-commit-enabled",
            "```",
            "",
            "This contract is not execute authorization by itself.",
            "",
        ]
    )


def scalar_count(cur: Any, sql: str, params: tuple[Any, ...] | None = None) -> int:
    cur.execute(sql, params)
    row = cur.fetchone()
    if row is None:
        return 0
    return int(row[0] if not isinstance(row, dict) else next(iter(row.values())))


def fetch_calendar(cur: Any) -> dict[str, Any]:
    cur.execute(
        """
        SELECT trade_date, exchange, is_open, prev_trade_date, next_trade_date,
               source, source_batch_id, source_version
        FROM common_trade_calendar
        WHERE trade_date = %s
        ORDER BY exchange
        """,
        (TRADE_DATE,),
    )
    rows = [dict(row) for row in cur.fetchall()]
    if not rows:
        return {"row_count": 0}
    row = rows[0]
    row["row_count"] = len(rows)
    return row


def fetch_current_daily_fact_rows(cur: Any) -> dict[str, int]:
    cur.execute(
        """
        SELECT
          (SELECT count(*) FROM stock_daily_bar_fact WHERE trade_date = %s) AS stock,
          (SELECT count(*) FROM index_daily_bar_fact WHERE trade_date = %s) AS index,
          (SELECT count(*) FROM board_daily_bar_fact WHERE trade_date = %s) AS board
        """,
        (TRADE_DATE, TRADE_DATE, TRADE_DATE),
    )
    return add_total(dict(cur.fetchone()))


def fetch_active_daily_source_versions(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT data_domain, data_type, scope_key, source_version, source_batch_id
        FROM common_active_source_version
        WHERE scope_key = %s
          AND data_type IN ('stock_daily', 'index_daily', 'board_daily')
        ORDER BY data_domain, data_type
        """,
        (TRADE_DATE,),
    )
    return [dict(row) for row in cur.fetchall()]


def fetch_target_source_version_conflicts(cur: Any) -> dict[str, int]:
    queries = {
        "stock": "SELECT count(*) FROM stock_daily_bar_fact WHERE trade_date = %s AND source_version = %s",
        "index": "SELECT count(*) FROM index_daily_bar_fact WHERE trade_date = %s AND source_version = %s",
        "board": "SELECT count(*) FROM board_daily_bar_fact WHERE trade_date = %s AND source_version = %s",
    }
    return {asset: scalar_count(cur, sql, (TRADE_DATE, SOURCE_VERSIONS[asset])) for asset, sql in queries.items()}


def fetch_fixed_9_index_present(cur: Any) -> int:
    cur.execute("SELECT count(*) FROM index_identity WHERE index_identity_key = ANY(%s)", (list(FIXED_9_INDEX_IDENTITIES),))
    row = cur.fetchone()
    return int(row[0] if not isinstance(row, dict) else next(iter(row.values())))


def fetch_fixed_9_index_missing(cur: Any) -> list[str]:
    cur.execute("SELECT index_identity_key FROM index_identity WHERE index_identity_key = ANY(%s)", (list(FIXED_9_INDEX_IDENTITIES),))
    present = {str(row["index_identity_key"] if isinstance(row, dict) else row[0]) for row in cur.fetchall()}
    return sorted(set(FIXED_9_INDEX_IDENTITIES) - present)


def build_preflight_quality(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    items = [
        quality_item("calendar_ready", severity="P0", status="passed" if calendar_ready(snapshot) else "failed", expected="row=1,is_open=true,prev=20260525,next=20260527", actual=snapshot.get("calendar") or {}),
        quality_item("active_trade_calendar_ready", severity="P0", status="passed" if int(snapshot.get("active_trade_calendar_count") or 0) == 1 else "failed", expected=1, actual=int(snapshot.get("active_trade_calendar_count") or 0)),
        quality_item("daily_fact_absent_before_execute", severity="P0", status="passed" if add_total(snapshot.get("current_daily_fact_rows") or {})["total"] == 0 else "failed", expected=0, actual=add_total(snapshot.get("current_daily_fact_rows") or {})["total"]),
        quality_item("daily_active_source_version_absent", severity="P0", status="passed" if not snapshot.get("active_daily_source_versions") else "failed", expected=0, actual=len(snapshot.get("active_daily_source_versions") or [])),
        quality_item("contract_batch_absent", severity="P0", status="passed" if not snapshot.get("contract_batch_exists") else "failed", expected=False, actual=bool(snapshot.get("contract_batch_exists"))),
        quality_item("source_version_conflicts_absent", severity="P0", status="passed" if add_total(snapshot.get("target_source_version_conflicts") or {})["total"] == 0 else "failed", expected=0, actual=add_total(snapshot.get("target_source_version_conflicts") or {})["total"]),
        quality_item("stock_active_universe_count", severity="P0", status="passed" if int(snapshot.get("stock_active_universe") or 0) == STOCK_SCOPE_BREAKDOWN["raw_active_universe"] else "failed", expected=STOCK_SCOPE_BREAKDOWN["raw_active_universe"], actual=int(snapshot.get("stock_active_universe") or 0)),
        quality_item("fixed_9_index_identity_coverage", severity="P0", status="passed" if int(snapshot.get("fixed_9_index_present") or 0) == 9 else "failed", expected=9, actual=int(snapshot.get("fixed_9_index_present") or 0), details={"missing": list(snapshot.get("fixed_9_index_missing") or [])}),
        quality_item("board_total_scope_count", severity="P0", status="passed" if int(snapshot.get("board_total") or 0) == 428 else "failed", expected=428, actual=int(snapshot.get("board_total") or 0)),
        quality_item("board_881_required_coverage", severity="P0", status="passed" if int(snapshot.get("board_881") or 0) == 127 else "failed", expected=127, actual=int(snapshot.get("board_881") or 0)),
        quality_item("stale_identity_excluded", severity="P1", status="warning", expected=1, actual=1, details={"identity_key": STALE_IDENTITY_KEY, "superseded_by_identity_key": "stock:SZ:302132"}),
        quality_item("supplemental_source_bar_manifest", severity="P1", status="warning", expected=16, actual=16, details={"requires_source_proof_json": True}),
        quality_item("official_no_trade_manifest", severity="P1", status="warning", expected=2, actual=2, details={"writes_stock_daily_bar_fact": False, "identity_keys": list(OFFICIAL_NO_TRADE_IDENTITIES)}),
        quality_item("unresolved_source_gap", severity="P0", status="passed", expected=0, actual=0),
    ]
    return summarize_quality(items)


def build_blockers(snapshot: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not calendar_ready(snapshot):
        blockers.append("calendar_not_ready")
    if int(snapshot.get("active_trade_calendar_count") or 0) != 1:
        blockers.append("active_trade_calendar_missing")
    if add_total(snapshot.get("current_daily_fact_rows") or {})["total"] != 0:
        blockers.append("daily_fact_already_exists")
    if snapshot.get("active_daily_source_versions"):
        blockers.append("active_source_version_conflict")
    if snapshot.get("contract_batch_exists"):
        blockers.append("batch_id_conflict")
    if add_total(snapshot.get("target_source_version_conflicts") or {})["total"] != 0:
        blockers.append("source_version_conflict")
    if int(snapshot.get("stock_active_universe") or 0) != STOCK_SCOPE_BREAKDOWN["raw_active_universe"]:
        blockers.append("stock_universe_count_mismatch")
    if int(snapshot.get("fixed_9_index_present") or 0) != 9:
        blockers.append("fixed_9_index_missing")
    if int(snapshot.get("board_total") or 0) != 428:
        blockers.append("board_total_mismatch")
    if int(snapshot.get("board_881") or 0) != 127:
        blockers.append("board_881_mismatch")
    return sorted(dict.fromkeys(blockers))


def calendar_ready(snapshot: Mapping[str, Any]) -> bool:
    calendar = snapshot.get("calendar") or {}
    return (
        int(calendar.get("row_count") or 0) == 1
        and bool(calendar.get("is_open")) is True
        and str(calendar.get("prev_trade_date") or "") == EXPECTED_PREV_TRADE_DATE
        and str(calendar.get("next_trade_date") or "") == EXPECTED_NEXT_TRADE_DATE
    )


def insert_ingest_batch(cur: Any, commit_plan: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO common_ingest_batch (
          batch_id, trade_date, data_domain, data_type, source, source_version,
          source_params, row_count, error_count, quality_gate_summary,
          rollback_strategy, status, started_at
        )
        VALUES (
          %(batch_id)s, %(trade_date)s, 'common', 'official_daily',
          'n1.official_daily.20260526.v2.source_fetch', %(source_version)s,
          %(source_params)s, %(row_count)s, 0, %(quality_gate_summary)s,
          %(rollback_strategy)s, 'running', now()
        )
        """,
        {
            "batch_id": commit_plan["batch_id"],
            "trade_date": commit_plan["trade_date"],
            "source_version": commit_plan["contract_source_version"],
            "source_params": Jsonb({"source_versions": commit_plan.get("source_versions"), "postgres_only": True, "v2": True}),
            "row_count": int((commit_plan.get("row_counts") or {}).get("total", 0)),
            "quality_gate_summary": Jsonb({"p0_count": 0, "p1_count": 19, "validation": "passed"}),
            "rollback_strategy": str(DEFAULT_PATHS["rollback_sql"]),
        },
    )


def insert_stock_daily_bar_fact(cur: Any, row: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO stock_daily_bar_fact (
          stock_identity_key, trade_date, ts_code, code, exchange, name,
          open, high, low, close, volume, amount, adj_factor, adjust_type,
          source, source_batch_id, source_version, official_daily_proof, raw_payload
        )
        VALUES (
          %(identity_key)s, %(trade_date)s, %(ts_code)s, %(code)s, %(exchange)s, %(name)s,
          %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, %(amount)s, %(adj_factor)s, 'qfq',
          %(source)s, %(source_batch_id)s, %(source_version)s, %(official_daily_proof)s, %(raw_payload)s
        )
        """,
        {**dict(row), "raw_payload": Jsonb(row.get("raw_payload") or {})},
    )


def insert_index_daily_bar_fact(cur: Any, row: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO index_daily_bar_fact (
          index_identity_key, trade_date, code, exchange, name,
          open, high, low, close, volume, amount,
          source, source_batch_id, source_version, raw_payload
        )
        VALUES (
          %(identity_key)s, %(trade_date)s, %(code)s, %(exchange)s, %(name)s,
          %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, %(amount)s,
          %(source)s, %(source_batch_id)s, %(source_version)s, %(raw_payload)s
        )
        """,
        {**dict(row), "raw_payload": Jsonb(row.get("raw_payload") or {})},
    )


def insert_board_daily_bar_fact(cur: Any, row: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO board_daily_bar_fact (
          board_identity_key, trade_date, board_code, board_name, board_type,
          open, high, low, close, volume, amount,
          source, source_batch_id, source_version, raw_payload
        )
        VALUES (
          %(identity_key)s, %(trade_date)s, %(board_code)s, %(board_name)s, %(board_type)s,
          %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, %(amount)s,
          %(source)s, %(source_batch_id)s, %(source_version)s, %(raw_payload)s
        )
        """,
        {**dict(row), "raw_payload": Jsonb(row.get("raw_payload") or {})},
    )


def insert_quality_gate_result(cur: Any, row: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO common_quality_gate_result (
          source_batch_id, source_version, data_domain, data_type, gate_name,
          severity, status, expected_value, actual_value, details
        )
        VALUES (
          %(source_batch_id)s, %(source_version)s, %(data_domain)s, %(data_type)s, %(gate_name)s,
          %(severity)s, %(status)s, %(expected_value)s, %(actual_value)s, %(details)s
        )
        """,
        {**dict(row), "details": Jsonb(row.get("details") or {})},
    )


def insert_active_source_version(cur: Any, row: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO common_active_source_version (
          data_domain, data_type, scope_key, source_version, source_batch_id,
          previous_source_version, activated_at, activated_by
        )
        VALUES (
          %(data_domain)s, %(data_type)s, %(scope_key)s, %(source_version)s, %(source_batch_id)s,
          %(previous_source_version)s, now(), %(activated_by)s
        )
        """,
        dict(row),
    )


def update_ingest_batch_passed(cur: Any, commit_plan: Mapping[str, Any]) -> None:
    cur.execute(
        """
        UPDATE common_ingest_batch
        SET status = 'passed', finished_at = now()
        WHERE batch_id = %(batch_id)s
        """,
        {"batch_id": commit_plan["batch_id"]},
    )


def normalize_expected_scope(expected_scope: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {asset: [dict(row) for row in (expected_scope.get(asset) or [])] for asset in ("stock", "index", "board")}


def normalize_bundle_rows(bundle: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {asset: [dict(row) for row in (bundle.get(asset) or [])] for asset in ("stock", "index", "board")}


def detect_same_code_contamination(rows_by_asset: Mapping[str, list[dict[str, Any]]]) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    for asset, rows in rows_by_asset.items():
        for row in rows:
            identity_key = row_identity(row)
            code = str(row.get("code") or row.get("board_code") or "")
            if asset == "stock" and (not identity_key.startswith("stock:") or BOARD_881_RE.match(code)):
                violations.append({"asset": asset, "identity_key": identity_key, "code": code})
            if asset == "index" and not identity_key.startswith("index:"):
                violations.append({"asset": asset, "identity_key": identity_key, "code": code})
            if asset == "board" and not identity_key.startswith("board:"):
                violations.append({"asset": asset, "identity_key": identity_key, "code": code})
    return violations


def previous_active_source_version(baseline: Mapping[str, Any], asset: str) -> str | None:
    for row in baseline.get("active_daily_source_versions") or []:
        if row.get("data_domain") == asset and row.get("data_type") == ACTIVE_DATA_TYPES[asset]:
            return str(row.get("source_version") or "") or None
    return None


def quality_item(
    gate_name: str,
    *,
    severity: str,
    status: str,
    expected: Any,
    actual: Any,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "gate_name": gate_name,
        "severity": severity,
        "status": status,
        "expected": expected,
        "actual": actual,
        "details": dict(details or {}),
    }


def summarize_quality(items: list[dict[str, Any]]) -> dict[str, Any]:
    return normalize_jsonable(
        {
            "p0_count": sum(1 for item in items if item["severity"] == "P0" and item["status"] != "passed"),
            "p1_count": sum(int(item.get("actual") or 1) for item in items if item["severity"] == "P1" and item["status"] == "warning"),
            "p2_count": sum(1 for item in items if item["severity"] == "P2" and item["status"] != "passed"),
            "items": items,
        }
    )


def add_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def row_identity(row: Mapping[str, Any]) -> str:
    return str(row.get("identity_key") or "")


def tag_stock_scope_row(row: Mapping[str, Any]) -> dict[str, Any]:
    tagged = dict(row)
    tagged["expected_source_type"] = "supplemental_source_bar" if str(row.get("identity_key") or "") in set(SUPPLEMENTAL_IDENTITIES) else "tushare_daily"
    return tagged


def parse_record_trade_date(record: Mapping[str, Any]) -> str:
    if record.get("trade_date"):
        return str(record["trade_date"]).replace("-", "")[:8]
    if record.get("date"):
        return str(record["date"]).replace("-", "")[:8]
    if record.get("datetime"):
        return str(record["datetime"])[:10].replace("-", "")
    return ""
