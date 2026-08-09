"""N1 official daily 20260526 execute runner support.

The functions here wire the execute path behind explicit final-gate flags. Unit
tests use injected source adapters and recording connections. Real source fetch
and PostgreSQL commit only happen when the run-once script is called with all
four final-gate flags in a separately authorized execute gate.
"""

from __future__ import annotations

from collections import Counter
import importlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.ingestion.tushare_env import load_tushare_token
from ashare_v3.ingestion.official_daily_20260526_contract import (
    ACTIVE_DATA_TYPES,
    ALLOWED_FUTURE_WRITE_TABLES,
    BATCH_ID,
    CONTRACT_SOURCE_VERSION,
    DEFAULT_PATHS,
    EXPECTED_SCOPE,
    FIXED_9_INDEX_IDENTITIES,
    SOURCE_VERSIONS,
    TRADE_DATE,
    add_total,
    build_blockers,
    build_execute_contract,
    build_execute_preflight,
    build_snapshot_from_db,
    no_side_effects,
    normalize_jsonable,
    now_iso,
)


BOARD_881_RE = re.compile(r"^881\d{3}$")
FORBIDDEN_WRITE_TABLES = (
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_event_delivery_attempt",
    "stock_realtime_daily_snapshot",
    "index_realtime_daily_snapshot",
    "board_realtime_daily_snapshot",
    "stock_minute_bar_1m",
    "index_minute_bar_1m",
    "board_minute_bar_1m",
    "condition tables",
    "trigger/action/user/voice/mobile/sim/position tables",
    "Parquet",
    "worker",
    "old system",
    "real trading",
)
SOURCE_FETCH_ROUTES = {
    "stock": {"primary": "Tushare daily + adj_factor proof", "fallback": None},
    "index": {"primary": "TDX/Mootdx", "fallback": "Tushare index_daily"},
    "board": {"primary": "TDX/Mootdx board daily", "fallback": None},
}


class OfficialDaily20260526ExecuteBlocked(RuntimeError):
    """Raised when the 20260526 official daily execute gate is blocked."""


def validate_execute_request(
    *,
    execute_requested: bool,
    user_confirmed: bool,
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> None:
    if not execute_requested:
        raise OfficialDaily20260526ExecuteBlocked("missing --execute")
    if not user_confirmed:
        raise OfficialDaily20260526ExecuteBlocked("missing --user-confirmed")
    if not source_fetch_enabled:
        raise OfficialDaily20260526ExecuteBlocked("missing --source-fetch-enabled")
    if not postgres_commit_enabled:
        raise OfficialDaily20260526ExecuteBlocked("missing --postgres-commit-enabled")


class DefaultOfficialDaily20260526SourceAdapter:
    """Lazy real source adapter used only after explicit final execute flags."""

    def __init__(
        self,
        *,
        tushare_token: str | None = None,
        mootdx_offset: int = 800,
        mootdx_source: Any | None = None,
    ) -> None:
        self.tushare_token = tushare_token or load_tushare_token()
        self.mootdx_offset = mootdx_offset
        self._tushare_client: Any | None = None
        self._mootdx_source = mootdx_source

    def fetch_stock_daily(self, *, trade_date: str, expected_scope: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pro = self._pro()
        daily_rows = frame_to_records(
            pro.daily(
                trade_date=trade_date,
                fields="ts_code,trade_date,open,high,low,close,vol,amount",
            )
        )
        adj_rows = frame_to_records(
            pro.adj_factor(
                trade_date=trade_date,
                fields="ts_code,trade_date,adj_factor",
            )
        )
        daily_by_ts = {str(row.get("ts_code") or ""): row for row in daily_rows}
        adj_by_ts = {str(row.get("ts_code") or ""): row for row in adj_rows}
        rows: list[dict[str, Any]] = []
        for scope_row in expected_scope:
            ts_code = ts_code_from_scope(scope_row)
            raw = daily_by_ts.get(ts_code)
            adj = adj_by_ts.get(ts_code)
            if not raw or not adj:
                continue
            rows.append(
                {
                    "asset_kind": "stock",
                    "identity_key": scope_row["identity_key"],
                    "trade_date": trade_date,
                    "ts_code": ts_code,
                    "code": str(scope_row.get("code") or ""),
                    "exchange": str(scope_row.get("exchange") or ""),
                    "name": scope_row.get("name"),
                    "open": to_optional_float(raw.get("open")),
                    "high": to_optional_float(raw.get("high")),
                    "low": to_optional_float(raw.get("low")),
                    "close": to_optional_float(raw.get("close")),
                    "volume": to_optional_float(raw.get("vol")),
                    "amount": to_optional_float(raw.get("amount")),
                    "adj_factor": to_optional_float(adj.get("adj_factor")),
                    "official_daily_proof": True,
                    "source": "tushare.daily+adj_factor.official_daily",
                    "source_batch_id": BATCH_ID,
                    "source_version": SOURCE_VERSIONS["stock"],
                    "raw_payload": json_safe({"daily": raw, "adj_factor": adj}),
                }
            )
        return rows

    def fetch_index_daily(self, *, trade_date: str, expected_scope: list[dict[str, Any]]) -> list[dict[str, Any]]:
        daily_bars = importlib.import_module("ashare_v3.ingestion.daily_bars")
        symbols = [
            daily_bars.IndexDailySymbol(
                code=str(row.get("code") or ""),
                exchange=str(row.get("exchange") or ""),
                name=row.get("name"),
            )
            for row in expected_scope
        ]
        raw_rows = frame_to_records(
            self._mootdx().fetch_index_daily_bars(indexes=symbols, start_date=trade_date, end_date=trade_date)
        )
        raw_by_key = {f"index:{row.get('exchange')}:{row.get('code')}": row for row in raw_rows}
        rows = [
            self._index_row(scope_row, raw_by_key[str(scope_row["identity_key"])], source="mootdx.index")
            for scope_row in expected_scope
            if str(scope_row.get("identity_key")) in raw_by_key
        ]
        missing = [row for row in expected_scope if str(row.get("identity_key")) not in raw_by_key]
        if missing:
            rows.extend(self._fetch_index_fallback(trade_date=trade_date, missing_scope=missing))
        return rows

    def fetch_board_daily(self, *, trade_date: str, expected_scope: list[dict[str, Any]]) -> list[dict[str, Any]]:
        daily_bars = importlib.import_module("ashare_v3.ingestion.daily_bars")
        symbols = [
            daily_bars.BoardDailySymbol(
                board_code=str(row.get("code") or ""),
                board_name=row.get("name"),
                board_type=str(row.get("board_type") or "tdx_other"),
            )
            for row in expected_scope
        ]
        raw_rows = frame_to_records(
            self._mootdx().fetch_board_daily_bars(boards=symbols, start_date=trade_date, end_date=trade_date)
        )
        raw_by_key = {f"board:TDX:{row.get('board_code')}": row for row in raw_rows}
        return [
            self._board_row(scope_row, raw_by_key[str(scope_row["identity_key"])])
            for scope_row in expected_scope
            if str(scope_row.get("identity_key")) in raw_by_key
        ]

    def _fetch_index_fallback(self, *, trade_date: str, missing_scope: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pro = self._pro()
        rows: list[dict[str, Any]] = []
        for scope_row in missing_scope:
            raw_rows = frame_to_records(
                pro.index_daily(
                    ts_code=ts_code_from_scope(scope_row),
                    start_date=trade_date,
                    end_date=trade_date,
                    fields="ts_code,trade_date,open,high,low,close,vol,amount",
                )
            )
            if raw_rows:
                rows.append(self._index_row(scope_row, raw_rows[0], source="tushare.index_daily.fallback"))
        return rows

    def _index_row(self, scope_row: Mapping[str, Any], raw: Mapping[str, Any], *, source: str) -> dict[str, Any]:
        return {
            "asset_kind": "index",
            "identity_key": scope_row["identity_key"],
            "trade_date": TRADE_DATE,
            "code": str(scope_row.get("code") or raw.get("code") or ""),
            "exchange": str(scope_row.get("exchange") or raw.get("exchange") or ""),
            "name": scope_row.get("name"),
            "open": to_optional_float(raw.get("open")),
            "high": to_optional_float(raw.get("high")),
            "low": to_optional_float(raw.get("low")),
            "close": to_optional_float(raw.get("close")),
            "volume": to_optional_float(raw.get("vol")) or to_optional_float(raw.get("volume")),
            "amount": to_optional_float(raw.get("amount")),
            "source": source,
            "source_batch_id": BATCH_ID,
            "source_version": SOURCE_VERSIONS["index"],
            "raw_payload": json_safe(raw),
        }

    def _board_row(self, scope_row: Mapping[str, Any], raw: Mapping[str, Any]) -> dict[str, Any]:
        board_code = str(scope_row.get("code") or raw.get("board_code") or "")
        return {
            "asset_kind": "board",
            "identity_key": scope_row["identity_key"],
            "trade_date": TRADE_DATE,
            "code": board_code,
            "exchange": "TDX",
            "name": scope_row.get("name"),
            "board_code": board_code,
            "board_name": scope_row.get("name") or raw.get("board_name"),
            "board_type": str(scope_row.get("board_type") or raw.get("board_type") or "tdx_other"),
            "open": to_optional_float(raw.get("open")),
            "high": to_optional_float(raw.get("high")),
            "low": to_optional_float(raw.get("low")),
            "close": to_optional_float(raw.get("close")),
            "volume": to_optional_float(raw.get("vol")) or to_optional_float(raw.get("volume")),
            "amount": to_optional_float(raw.get("amount")),
            "source": "mootdx.index",
            "source_batch_id": BATCH_ID,
            "source_version": SOURCE_VERSIONS["board"],
            "raw_payload": json_safe(raw),
        }

    def _pro(self) -> Any:
        if self._tushare_client is None:
            if not self.tushare_token:
                raise OfficialDaily20260526ExecuteBlocked("TUSHARE_TOKEN is required for stock official daily fetch")
            tushare = importlib.import_module("tushare")
            self._tushare_client = tushare.pro_api(self.tushare_token)
        return self._tushare_client

    def _mootdx(self) -> Any:
        if self._mootdx_source is None:
            module = importlib.import_module("ashare_v3.ingestion.mootdx_daily_source")
            self._mootdx_source = module.MootdxDailyBarSource(offset=self.mootdx_offset)
        return self._mootdx_source


def fetch_official_daily_sources(
    *,
    adapter: Any,
    trade_date: str,
    expected_scope: Mapping[str, Any],
    source_fetch_enabled: bool,
) -> dict[str, Any]:
    if not source_fetch_enabled:
        raise OfficialDaily20260526ExecuteBlocked("missing --source-fetch-enabled")
    scope = normalize_expected_scope(expected_scope)
    rows = {
        "stock": list(adapter.fetch_stock_daily(trade_date=trade_date, expected_scope=scope["stock"])),
        "index": list(adapter.fetch_index_daily(trade_date=trade_date, expected_scope=scope["index"])),
        "board": list(adapter.fetch_board_daily(trade_date=trade_date, expected_scope=scope["board"])),
    }
    return normalize_jsonable(
        {
            "trade_date": trade_date,
            "routes": SOURCE_FETCH_ROUTES,
            "row_counts": add_total({asset: len(rows[asset]) for asset in ("stock", "index", "board")}),
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
            blockers.append(f"missing_expected_{asset}")
        quality_items.append(
            quality_item(
                f"{asset}_expected_coverage",
                passed=not missing,
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
                passed=not duplicate_ids,
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
                passed=not contract_errors,
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
                passed=not sanity_errors,
                expected=0,
                actual=len(sanity_errors),
                details={"failed_sample": sanity_errors[:10]},
            )
        )

    stock_proof_errors = [
        row_identity(row)
        for row in rows_by_asset["stock"]
        if row.get("official_daily_proof") is not True or row.get("adj_factor") is None
    ]
    if stock_proof_errors:
        add_once(blockers, "stock_adj_factor_proof_missing")
    quality_items.append(
        quality_item(
            "stock_adj_factor_proof",
            passed=not stock_proof_errors,
            expected=len(scope["stock"]),
            actual=len(scope["stock"]) - len(stock_proof_errors),
            details={"failed_sample": stock_proof_errors[:10]},
        )
    )

    contamination = detect_same_code_contamination(rows_by_asset)
    if contamination:
        add_once(blockers, "same_code_contamination")
    quality_items.append(
        quality_item(
            "same_code_contamination",
            passed=not contamination,
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
            passed=not missing_fixed_9,
            expected=len(FIXED_9_INDEX_IDENTITIES),
            actual=len(FIXED_9_INDEX_IDENTITIES) - len(missing_fixed_9),
            details={"missing": missing_fixed_9},
        )
    )

    expected_881 = {str(row.get("identity_key")) for row in scope["board"] if BOARD_881_RE.match(str(row.get("code") or ""))}
    actual_881 = {row_identity(row) for row in rows_by_asset["board"] if BOARD_881_RE.match(str(row.get("board_code") or row.get("code") or ""))}
    missing_881 = sorted(expected_881 - actual_881)
    if missing_881:
        add_once(blockers, "board_881_coverage_missing")
    quality_items.append(
        quality_item(
            "board_881_required_coverage",
            passed=not missing_881,
            expected=len(expected_881),
            actual=len(expected_881) - len(missing_881),
            details={"missing_sample": missing_881[:10]},
        )
    )

    p0_count = sum(1 for item in quality_items if item["status"] != "passed" and item["severity"] == "P0")
    return normalize_jsonable(
        {
            "result": "VALIDATION_PASS" if p0_count == 0 else "VALIDATION_BLOCKED",
            "p0_count": p0_count,
            "blockers": sorted(dict.fromkeys(blockers)),
            "row_counts": add_total({asset: len(rows_by_asset[asset]) for asset in ("stock", "index", "board")}),
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
        raise OfficialDaily20260526ExecuteBlocked(", ".join(sorted(dict.fromkeys(blockers))))


def build_commit_plan(
    *,
    bundle: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    baseline: Mapping[str, Any],
    trade_date: str,
) -> dict[str, Any]:
    if int(validation_report.get("p0_count") or 0) != 0:
        raise OfficialDaily20260526ExecuteBlocked("source validation P0 must be zero before commit plan")
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
    active_rows = [
        {
            "data_domain": asset,
            "data_type": ACTIVE_DATA_TYPES[asset],
            "scope_key": trade_date,
            "source_version": SOURCE_VERSIONS[asset],
            "source_batch_id": BATCH_ID,
            "previous_source_version": previous_active_source_version(baseline, asset),
            "activated_by": "n1_official_daily_20260526_execute_runner",
        }
        for asset in ("stock", "index", "board")
    ]
    row_counts = add_total({asset: len(rows_by_asset[asset]) for asset in ("stock", "index", "board")})
    return normalize_jsonable(
        {
            "trade_date": trade_date,
            "batch_id": BATCH_ID,
            "contract_source_version": CONTRACT_SOURCE_VERSION,
            "source_versions": dict(SOURCE_VERSIONS),
            "allowed_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
            "row_counts": row_counts,
            "rows": rows_by_asset,
            "quality_rows": quality_rows,
            "active_source_version_rows": active_rows,
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
        raise OfficialDaily20260526ExecuteBlocked(f"unexpected write tables: {unexpected_tables}")

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
    report = build_execute_preflight(snapshot)
    blockers = list(report.get("blockers") or [])
    if execute_requested and not user_confirmed:
        blockers.append("missing_user_confirmed")
    if execute_requested and user_confirmed and not source_fetch_enabled:
        blockers.append("source_fetch_disabled")
    if execute_requested and user_confirmed and not postgres_commit_enabled:
        blockers.append("postgres_commit_disabled")
    blockers = sorted(dict.fromkeys(blockers))
    report.update(
        {
            "result": "PREFLIGHT_BLOCKED" if blockers else "PREFLIGHT_PASS",
            "blocked": bool(blockers),
            "blockers": blockers,
            "runner_readiness": "blocked" if blockers else "ready_for_final_gate",
            "source_fetch_implemented": True,
            "postgres_commit_implemented": True,
            "final_execute_gate_allowed": not bool(blockers),
            "execute_authorized": False,
            "execute_flags_seen": {
                "execute": bool(execute_requested),
                "user_confirmed": bool(user_confirmed),
                "source_fetch_enabled": bool(source_fetch_enabled),
                "postgres_commit_enabled": bool(postgres_commit_enabled),
            },
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
                    "source_fetch",
                    "validate_source_bundle",
                    "validate_commit_preconditions",
                    "build_commit_plan",
                    "execute_commit_transaction",
                ],
                "tests_use_mock_source": True,
            },
            "execute_command_template": (
                "PYTHONPATH=src python3 scripts/run_official_daily_ingestion_20260526_once.py "
                "--trade-date 20260526 --execute --user-confirmed --source-fetch-enabled --postgres-commit-enabled"
            ),
            "side_effects": no_side_effects(),
        }
    )
    return normalize_jsonable(report)


def build_expected_scope_from_db(*, dsn: str, trade_date: str = TRADE_DATE) -> dict[str, list[dict[str, Any]]]:
    if trade_date != TRADE_DATE:
        raise ValueError("This runner is fixed to trade_date=20260526")
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT stock_identity_key AS identity_key, exchange, code, name, ts_code
                FROM stock_identity
                WHERE status = 'active'
                ORDER BY stock_identity_key
                """
            )
            stock_scope = [dict(row) for row in cur.fetchall()]
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
        raise OfficialDaily20260526ExecuteBlocked("execute_contract_not_design_pass")
    if contract.get("contract_batch_id") != BATCH_ID:
        raise OfficialDaily20260526ExecuteBlocked("execute_contract_batch_id_mismatch")
    if dict(contract.get("source_versions") or {}) != dict(SOURCE_VERSIONS):
        raise OfficialDaily20260526ExecuteBlocked("execute_contract_source_versions_mismatch")


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
            "# N1 Official Daily 20260526 Ingestion Execute Preflight",
            "",
            "日期：2026-05-27  ",
            "layer_role：`N1_ingestion`  ",
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
            "## Execute Pipeline",
            "",
            "```json",
            json.dumps(report.get("execute_pipeline") or {}, ensure_ascii=False, indent=2),
            "```",
            "",
            "## Future Write Scope",
            "",
            "Only the N1 official daily tables are in scope; no Parquet, outbox, inbox, checkpoint, worker, old system, or N2-N6 writes.",
            "",
        ]
    )


def render_contract_markdown(contract: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# N1 Official Daily 20260526 Ingestion Execute Contract",
            "",
            "日期：2026-05-27  ",
            "layer_role：`N1_ingestion`  ",
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
            "## Implementation Status",
            "",
            "```json",
            json.dumps(contract.get("implementation_status") or {}, ensure_ascii=False, indent=2),
            "```",
            "",
            "## Execute Command Candidate",
            "",
            "```bash",
            "PYTHONPATH=src python3 scripts/run_official_daily_ingestion_20260526_once.py \\",
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
          'n1.official_daily.20260526.source_fetch', %(source_version)s,
          %(source_params)s, %(row_count)s, 0, %(quality_gate_summary)s,
          %(rollback_strategy)s, 'running', now()
        )
        """,
        {
            "batch_id": commit_plan["batch_id"],
            "trade_date": commit_plan["trade_date"],
            "source_version": commit_plan["contract_source_version"],
            "source_params": Jsonb({"source_versions": commit_plan.get("source_versions"), "postgres_only": True}),
            "row_count": int((commit_plan.get("row_counts") or {}).get("total", 0)),
            "quality_gate_summary": Jsonb({"p0_count": 0, "validation": "passed"}),
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


def quality_item(gate_name: str, *, passed: bool, expected: Any, actual: Any, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "gate_name": gate_name,
        "severity": "P0",
        "status": "passed" if passed else "failed",
        "expected": expected,
        "actual": actual,
        "details": dict(details or {}),
    }


def add_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def row_identity(row: Mapping[str, Any]) -> str:
    return str(row.get("identity_key") or "")


def has_valid_ohlc_amount(row: Mapping[str, Any]) -> bool:
    try:
        open_value = float(row.get("open"))
        high_value = float(row.get("high"))
        low_value = float(row.get("low"))
        close_value = float(row.get("close"))
        volume = float(row.get("volume") or 0)
        amount = float(row.get("amount") or 0)
    except (TypeError, ValueError):
        return False
    if min(open_value, high_value, low_value, close_value) <= 0:
        return False
    if high_value < max(open_value, low_value, close_value):
        return False
    if low_value > min(open_value, high_value, close_value):
        return False
    return volume >= 0 and amount >= 0


def ts_code_from_scope(scope_row: Mapping[str, Any]) -> str:
    if scope_row.get("ts_code"):
        return str(scope_row["ts_code"])
    return f"{scope_row.get('code')}.{scope_row.get('exchange')}"


def to_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


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
    if isinstance(frame, list):
        return [dict(row) for row in frame]
    return [dict(row) for row in list(frame)]


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))
