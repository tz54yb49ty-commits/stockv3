"""N1 official daily 20260525 execute preflight.

This module implements the final gate scaffolding for official daily fact
ingestion. It is intentionally read-only for this stage: no market data fetch,
no PostgreSQL writes, no Parquet writes, no active source version update, and
no downstream layer entry.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import json
import re
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.ingestion.tushare_env import load_tushare_token
from ashare_v3.ingestion.official_daily_ingestion_plan import (
    ASSET_KINDS,
    ACTIVE_DATA_TYPES,
    CONTRACT_BATCH_ID,
    CONTRACT_SOURCE_VERSION,
    DEFAULT_EOD_REPORT_JSON,
    FIXED_9_INDEX_IDENTITIES,
    SOURCE_VERSIONS,
    build_snapshot_from_db,
    fetch_active_source_versions_for_trade_date,
    fetch_contract_batch_exists,
    fetch_current_fact_state,
    fetch_target_source_version_conflicts,
    load_json,
    normalize_counts,
    normalize_jsonable,
    now_iso,
)


FOR_TRADE_DATE = "20260525"
EXPECTED_C3_PENDING = 17432
EXPECTED_TRADE_DATE = "20260525"
DEFAULT_DRY_RUN_REPORT_PATH = "docs/N1_official_daily_20260525_ingestion_dry_run_report.json"
DEFAULT_PREFLIGHT_JSON_PATH = "docs/N1_official_daily_20260525_ingestion_execute_preflight.json"
DEFAULT_PREFLIGHT_MARKDOWN_PATH = "docs/N1_OFFICIAL_DAILY_20260525_INGESTION_EXECUTE_PREFLIGHT.md"
DEFAULT_ROLLBACK_SQL_PATH = "sql/N1_official_daily_20260525_ingestion_rollback.sql"
DEFAULT_EXECUTE_CONTRACT_JSON_PATH = "docs/N1_official_daily_20260525_ingestion_execute_contract.json"
BOARD_881_RE = re.compile(r"^881\d{3}$")

ALLOWED_EXECUTE_WRITE_TABLES = (
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
    "common_event_delivery_attempt",
    "stock_eod_snapshot",
    "index_eod_snapshot",
    "board_eod_snapshot",
    "stock_eod_reconciliation_item",
    "index_eod_reconciliation_item",
    "board_eod_reconciliation_item",
    "stock_realtime_daily_snapshot",
    "index_realtime_daily_snapshot",
    "board_realtime_daily_snapshot",
    "stock_realtime_projection_metric",
    "index_realtime_projection_metric",
    "board_realtime_projection_metric",
    "stock_closed_30m_summary",
    "index_closed_30m_summary",
    "board_closed_30m_summary",
    "stock_closed_30m_signal_enrichment",
    "index_closed_30m_signal_enrichment",
    "board_closed_30m_signal_enrichment",
    "stock_minute_bar_1m",
    "index_minute_bar_1m",
    "board_minute_bar_1m",
    "stock_daily_basic",
    "stock_financial_metrics_fact",
    "condition tables",
    "trigger/action/user/voice/mobile/sim/position tables",
    "N4/N5/N6",
    "Parquet",
    "worker",
    "old system",
    "real trading",
)

EOD_SNAPSHOT_TABLES = {
    "stock": "stock_eod_snapshot",
    "index": "index_eod_snapshot",
    "board": "board_eod_snapshot",
}


class OfficialDailyExecuteBlocked(RuntimeError):
    """Raised when a caller attempts to cross the execute safety gate."""


SOURCE_FETCH_ROUTES = {
    "stock": {
        "primary": "Tushare daily + adj_factor proof",
        "fallback": None,
        "external_call_enabled_by_default": False,
    },
    "index": {
        "primary": "TDX/Mootdx",
        "fallback": "Tushare index_daily",
        "external_call_enabled_by_default": False,
    },
    "board": {
        "primary": "TDX/Mootdx industry board daily",
        "fallback": None,
        "external_call_enabled_by_default": False,
    },
}


def validate_execute_request(*, execute_requested: bool, user_confirmed: bool) -> None:
    if not execute_requested:
        raise OfficialDailyExecuteBlocked("N1 official daily execute requires explicit --execute")
    if not user_confirmed:
        raise OfficialDailyExecuteBlocked("N1 official daily execute requires explicit --user-confirmed")


class DefaultOfficialDailySourceAdapter:
    """Lazy real source adapter for future explicitly authorized final execute."""

    def __init__(self, *, tushare_token: str | None = None, mootdx_offset: int = 800) -> None:
        self.tushare_token = tushare_token or load_tushare_token()
        self.mootdx_offset = mootdx_offset
        self._tushare_client: Any | None = None
        self._mootdx_source: Any | None = None

    def fetch_stock_daily(self, *, for_trade_date: str, expected_scope: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pro = self._pro()
        daily_rows = _frame_to_records(
            pro.daily(
                trade_date=for_trade_date,
                fields="ts_code,trade_date,open,high,low,close,vol,amount",
            )
        )
        adj_rows = _frame_to_records(
            pro.adj_factor(
                trade_date=for_trade_date,
                fields="ts_code,trade_date,adj_factor",
            )
        )
        daily_by_ts_code = {str(row.get("ts_code") or ""): row for row in daily_rows}
        adj_by_ts_code = {str(row.get("ts_code") or ""): row for row in adj_rows}
        rows: list[dict[str, Any]] = []
        for scope_row in expected_scope:
            ts_code = ts_code_from_scope(scope_row)
            raw = daily_by_ts_code.get(ts_code)
            adj = adj_by_ts_code.get(ts_code)
            if not raw or not adj:
                continue
            rows.append(
                {
                    "asset_kind": "stock",
                    "identity_key": scope_row["identity_key"],
                    "trade_date": for_trade_date,
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
                    "source": "tushare.daily+adj_factor.official_daily",
                    "source_batch_id": CONTRACT_BATCH_ID,
                    "source_version": SOURCE_VERSIONS["stock"],
                    "official_daily_proof": True,
                    "raw_payload": json_safe({"daily": raw, "adj_factor": adj}),
                }
            )
        return rows

    def fetch_index_daily(self, *, for_trade_date: str, expected_scope: list[dict[str, Any]]) -> list[dict[str, Any]]:
        daily_bars = importlib.import_module("ashare_v3.ingestion.daily_bars")
        symbols = [
            daily_bars.IndexDailySymbol(
                code=str(row.get("code") or ""),
                exchange=str(row.get("exchange") or ""),
                name=row.get("name"),
            )
            for row in expected_scope
        ]
        raw_rows = _frame_to_records(
            self._mootdx().fetch_index_daily_bars(
                indexes=symbols,
                start_date=for_trade_date,
                end_date=for_trade_date,
            )
        )
        rows_by_key = {f"index:{row.get('exchange')}:{row.get('code')}": row for row in raw_rows}
        rows = [
            self._index_row(scope_row, rows_by_key[str(scope_row["identity_key"])], source="mootdx.index")
            for scope_row in expected_scope
            if str(scope_row.get("identity_key")) in rows_by_key
        ]
        missing_scope = [row for row in expected_scope if str(row.get("identity_key")) not in rows_by_key]
        if missing_scope:
            rows.extend(self._fetch_index_fallback(for_trade_date=for_trade_date, missing_scope=missing_scope))
        return rows

    def fetch_board_daily(self, *, for_trade_date: str, expected_scope: list[dict[str, Any]]) -> list[dict[str, Any]]:
        daily_bars = importlib.import_module("ashare_v3.ingestion.daily_bars")
        symbols = [
            daily_bars.BoardDailySymbol(
                board_code=str(row.get("code") or ""),
                board_name=row.get("name"),
                board_type="tdx_industry",
            )
            for row in expected_scope
        ]
        raw_rows = _frame_to_records(
            self._mootdx().fetch_board_daily_bars(
                boards=symbols,
                start_date=for_trade_date,
                end_date=for_trade_date,
            )
        )
        rows_by_key = {f"board:TDX:{row.get('board_code')}": row for row in raw_rows}
        return [
            self._board_row(scope_row, rows_by_key[str(scope_row["identity_key"])])
            for scope_row in expected_scope
            if str(scope_row.get("identity_key")) in rows_by_key
        ]

    def _fetch_index_fallback(self, *, for_trade_date: str, missing_scope: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pro = self._pro()
        rows: list[dict[str, Any]] = []
        for scope_row in missing_scope:
            raw_rows = _frame_to_records(
                pro.index_daily(
                    ts_code=ts_code_from_scope(scope_row),
                    start_date=for_trade_date,
                    end_date=for_trade_date,
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
            "trade_date": EXPECTED_TRADE_DATE,
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
            "source_batch_id": CONTRACT_BATCH_ID,
            "source_version": SOURCE_VERSIONS["index"],
            "raw_payload": json_safe(raw),
        }

    def _board_row(self, scope_row: Mapping[str, Any], raw: Mapping[str, Any]) -> dict[str, Any]:
        board_code = str(scope_row.get("code") or raw.get("board_code") or "")
        return {
            "asset_kind": "board",
            "identity_key": scope_row["identity_key"],
            "trade_date": EXPECTED_TRADE_DATE,
            "code": board_code,
            "exchange": "TDX",
            "name": scope_row.get("name"),
            "board_code": board_code,
            "board_name": scope_row.get("name") or raw.get("board_name"),
            "board_type": str(raw.get("board_type") or "tdx_industry"),
            "open": to_optional_float(raw.get("open")),
            "high": to_optional_float(raw.get("high")),
            "low": to_optional_float(raw.get("low")),
            "close": to_optional_float(raw.get("close")),
            "volume": to_optional_float(raw.get("vol")) or to_optional_float(raw.get("volume")),
            "amount": to_optional_float(raw.get("amount")),
            "source": "mootdx.index",
            "source_batch_id": CONTRACT_BATCH_ID,
            "source_version": SOURCE_VERSIONS["board"],
            "raw_payload": json_safe(raw),
        }

    def _pro(self) -> Any:
        if self._tushare_client is None:
            if not self.tushare_token:
                raise OfficialDailyExecuteBlocked("TUSHARE_TOKEN is required for real official daily source fetch")
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
    for_trade_date: str,
    expected_scope: Mapping[str, Any],
    source_fetch_enabled: bool,
) -> dict[str, Any]:
    """Route source fetch through an injected adapter.

    The production runner keeps this disabled unless a later final gate passes
    an explicit source_fetch_enabled flag and a real adapter. Tests can inject a
    mock adapter without touching external services.
    """
    if not source_fetch_enabled:
        raise OfficialDailyExecuteBlocked("source_fetch_enabled=true is required before official daily source fetch")

    scope = normalize_expected_scope(expected_scope)
    rows = {
        "stock": list(adapter.fetch_stock_daily(for_trade_date=for_trade_date, expected_scope=scope["stock"])),
        "index": list(adapter.fetch_index_daily(for_trade_date=for_trade_date, expected_scope=scope["index"])),
        "board": list(adapter.fetch_board_daily(for_trade_date=for_trade_date, expected_scope=scope["board"])),
    }
    row_counts = add_total({asset: len(rows[asset]) for asset in ASSET_KINDS})
    return normalize_jsonable(
        {
            "for_trade_date": for_trade_date,
            "routes": SOURCE_FETCH_ROUTES,
            "row_counts": row_counts,
            **rows,
        }
    )


def load_execute_contract(path: str | Path = DEFAULT_EXECUTE_CONTRACT_JSON_PATH) -> dict[str, Any]:
    return load_json(path)


def validate_execute_contract(contract: Mapping[str, Any]) -> None:
    if contract.get("result") != "DESIGN_PASS":
        raise OfficialDailyExecuteBlocked("execute_contract_not_design_pass")
    if contract.get("contract_batch_id") != CONTRACT_BATCH_ID:
        raise OfficialDailyExecuteBlocked("execute_contract_batch_id_mismatch")
    if dict(contract.get("source_versions") or {}) != dict(SOURCE_VERSIONS):
        raise OfficialDailyExecuteBlocked("execute_contract_source_versions_mismatch")


def build_expected_scope_from_db(
    *,
    dsn: str,
    for_trade_date: str = FOR_TRADE_DATE,
    eod_report_path: str | Path = DEFAULT_EOD_REPORT_JSON,
) -> dict[str, list[dict[str, Any]]]:
    snapshot = build_snapshot_from_db(dsn=dsn, for_trade_date=for_trade_date, eod_report_path=eod_report_path)
    return normalize_expected_scope(snapshot.get("expected_scope") or {})


def validate_source_bundle(
    *,
    bundle: Mapping[str, Any],
    expected_scope: Mapping[str, Any],
    for_trade_date: str = EXPECTED_TRADE_DATE,
) -> dict[str, Any]:
    rows_by_asset = normalize_bundle_rows(bundle)
    scope = normalize_expected_scope(expected_scope)
    blockers: list[str] = []
    quality_items: list[dict[str, Any]] = []

    for asset in ASSET_KINDS:
        expected_identities = {str(row.get("identity_key")) for row in scope[asset] if row.get("identity_key")}
        actual_identities = [str(row.get("identity_key") or "") for row in rows_by_asset[asset]]
        actual_identity_set = set(actual_identities)
        missing = sorted(expected_identities - actual_identity_set)
        if missing:
            blockers.append(f"missing_expected_{asset}")
        quality_items.append(
            quality_item(
                gate_name=f"{asset}_expected_coverage",
                status="passed" if not missing else "failed",
                severity="P0",
                expected_value=len(expected_identities),
                actual_value=len(expected_identities) - len(missing),
                details={"missing_sample": missing[:10]},
            )
        )

        duplicates = sorted({identity for identity in actual_identities if actual_identities.count(identity) > 1 and identity})
        if duplicates:
            add_once(blockers, "duplicate_identity_key")
        quality_items.append(
            quality_item(
                gate_name=f"{asset}_duplicate_identity_key",
                status="passed" if not duplicates else "failed",
                severity="P0",
                expected_value=0,
                actual_value=len(duplicates),
                details={"duplicate_sample": duplicates[:10]},
            )
        )

        source_errors = [row for row in rows_by_asset[asset] if row.get("source_version") != SOURCE_VERSIONS[asset]]
        batch_errors = [row for row in rows_by_asset[asset] if row.get("source_batch_id") != CONTRACT_BATCH_ID]
        trade_date_errors = [row for row in rows_by_asset[asset] if str(row.get("trade_date")) != for_trade_date]
        if source_errors or batch_errors or trade_date_errors:
            add_once(blockers, "source_contract_mismatch")
        quality_items.append(
            quality_item(
                gate_name=f"{asset}_source_contract",
                status="passed" if not (source_errors or batch_errors or trade_date_errors) else "failed",
                severity="P0",
                expected_value=f"{for_trade_date}/{CONTRACT_BATCH_ID}/{SOURCE_VERSIONS[asset]}",
                actual_value="passed" if not (source_errors or batch_errors or trade_date_errors) else "failed",
                details={
                    "source_version_errors": len(source_errors),
                    "source_batch_errors": len(batch_errors),
                    "trade_date_errors": len(trade_date_errors),
                },
            )
        )

        sanity_errors = [row_identity(row) for row in rows_by_asset[asset] if not has_valid_ohlc_amount(row)]
        if sanity_errors:
            add_once(blockers, "ohlc_volume_amount_sanity")
        quality_items.append(
            quality_item(
                gate_name=f"{asset}_ohlc_volume_amount_sanity",
                status="passed" if not sanity_errors else "failed",
                severity="P0",
                expected_value=0,
                actual_value=len(sanity_errors),
                details={"failed_sample": sanity_errors[:10]},
            )
        )

        if asset == "stock":
            proof_errors = [
                row_identity(row)
                for row in rows_by_asset["stock"]
                if row.get("official_daily_proof") is not True or row.get("adj_factor") is None
            ]
            if proof_errors:
                add_once(blockers, "stock_official_daily_proof_missing")
            quality_items.append(
                quality_item(
                    gate_name="stock_official_daily_adj_factor_proof",
                    status="passed" if not proof_errors else "failed",
                    severity="P0",
                    expected_value=0,
                    actual_value=len(proof_errors),
                    details={"failed_sample": proof_errors[:10]},
                )
            )

    contamination = detect_same_code_contamination(rows_by_asset)
    if contamination:
        blockers.append("same_code_contamination")
    quality_items.append(
        quality_item(
            gate_name="same_code_contamination",
            status="passed" if not contamination else "failed",
            severity="P0",
            expected_value=0,
            actual_value=len(contamination),
            details={"sample": contamination[:10]},
        )
    )

    index_identities = {row_identity(row) for row in rows_by_asset["index"]}
    missing_fixed_9 = sorted(set(FIXED_9_INDEX_IDENTITIES) - index_identities)
    if missing_fixed_9:
        blockers.append("fixed_9_index_missing")
    quality_items.append(
        quality_item(
            gate_name="fixed_9_index_coverage",
            status="passed" if not missing_fixed_9 else "failed",
            severity="P0",
            expected_value=len(FIXED_9_INDEX_IDENTITIES),
            actual_value=len(FIXED_9_INDEX_IDENTITIES) - len(missing_fixed_9),
            details={"missing": missing_fixed_9},
        )
    )

    board_violations = [
        row_identity(row)
        for row in rows_by_asset["board"]
        if not BOARD_881_RE.match(str(row.get("board_code") or row.get("code") or ""))
    ]
    if board_violations:
        blockers.append("board_881_coverage_failed")
    quality_items.append(
        quality_item(
            gate_name="board_881_coverage",
            status="passed" if not board_violations else "failed",
            severity="P0",
            expected_value=0,
            actual_value=len(board_violations),
            details={"violation_sample": board_violations[:10]},
        )
    )

    blockers = sorted(dict.fromkeys(blockers))
    p0_count = sum(1 for item in quality_items if item["severity"] == "P0" and item["status"] != "passed")
    return normalize_jsonable(
        {
            "result": "VALIDATION_PASS" if p0_count == 0 else "VALIDATION_BLOCKED",
            "p0_count": p0_count,
            "blockers": blockers,
            "row_counts": add_total({asset: len(rows_by_asset[asset]) for asset in ASSET_KINDS}),
            "quality_items": quality_items,
        }
    )


def validate_commit_preconditions(
    *,
    dry_run_report: Mapping[str, Any],
    baseline: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> None:
    blockers = build_blockers(dry_run_report=dry_run_report, baseline=baseline, rollback_sql_path=DEFAULT_ROLLBACK_SQL_PATH)
    if not source_fetch_enabled:
        blockers.append("source_fetch_disabled")
    if not postgres_commit_enabled:
        blockers.append("postgres_commit_disabled")
    if int(validation_report.get("p0_count") or 0) != 0:
        blockers.extend([str(blocker) for blocker in validation_report.get("blockers") or ["source_validation_p0"]])
    if blockers:
        raise OfficialDailyExecuteBlocked(", ".join(sorted(dict.fromkeys(blockers))))


def build_commit_plan(
    *,
    bundle: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    baseline: Mapping[str, Any],
    for_trade_date: str = EXPECTED_TRADE_DATE,
) -> dict[str, Any]:
    rows_by_asset = normalize_bundle_rows(bundle)
    if int(validation_report.get("p0_count") or 0) != 0:
        raise OfficialDailyExecuteBlocked("source validation P0 must be zero before commit plan")
    quality_rows = [
        {
            "source_batch_id": CONTRACT_BATCH_ID,
            "source_version": CONTRACT_SOURCE_VERSION,
            "data_domain": "common",
            "data_type": "official_daily",
            "gate_name": item["gate_name"],
            "severity": item["severity"],
            "status": item["status"],
            "expected_value": str(item.get("expected_value")),
            "actual_value": str(item.get("actual_value")),
            "details": item.get("details") or {},
        }
        for item in validation_report.get("quality_items", [])
    ]
    active_rows = [
        {
            "data_domain": asset,
            "data_type": ACTIVE_DATA_TYPES[asset],
            "scope_key": for_trade_date,
            "source_version": SOURCE_VERSIONS[asset],
            "source_batch_id": CONTRACT_BATCH_ID,
            "previous_source_version": previous_active_source_version(baseline, asset),
            "activated_by": "n1_official_daily_execute_runner",
        }
        for asset in ASSET_KINDS
    ]
    row_counts = add_total({asset: len(rows_by_asset[asset]) for asset in ASSET_KINDS})
    return normalize_jsonable(
        {
            "for_trade_date": for_trade_date,
            "batch_id": CONTRACT_BATCH_ID,
            "contract_source_version": CONTRACT_SOURCE_VERSION,
            "source_versions": dict(SOURCE_VERSIONS),
            "allowed_tables": list(ALLOWED_EXECUTE_WRITE_TABLES),
            "write_sequence": [
                "common_ingest_batch",
                "stock_daily_bar_fact",
                "index_daily_bar_fact",
                "board_daily_bar_fact",
                "common_quality_gate_result",
                "common_active_source_version",
                "common_ingest_batch status update",
            ],
            "row_counts": row_counts,
            "rows": rows_by_asset,
            "quality_rows": quality_rows,
            "active_source_version_rows": active_rows,
            "side_effects": {
                "writes_parquet": False,
                "writes_outbox": False,
                "writes_inbox_or_checkpoint": False,
                "enters_n3_n4_n5_n6": False,
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
    validate_execute_request(execute_requested=execute_requested, user_confirmed=user_confirmed)
    if not source_fetch_enabled:
        raise OfficialDailyExecuteBlocked("source_fetch_enabled=true is required before commit")
    if not postgres_commit_enabled:
        raise OfficialDailyExecuteBlocked("postgres_commit_enabled=true is required before commit")

    unexpected_tables = sorted(set(commit_plan.get("allowed_tables") or []) - set(ALLOWED_EXECUTE_WRITE_TABLES))
    if unexpected_tables:
        raise OfficialDailyExecuteBlocked(f"unexpected write tables: {unexpected_tables}")

    cur = conn.cursor()
    written_tables: set[str] = set()
    try:
        insert_ingest_batch(cur, commit_plan)
        written_tables.add("common_ingest_batch")
        for row in (commit_plan.get("rows") or {}).get("stock", []):
            insert_stock_daily_bar_fact(cur, row)
        if (commit_plan.get("rows") or {}).get("stock"):
            written_tables.add("stock_daily_bar_fact")
        for row in (commit_plan.get("rows") or {}).get("index", []):
            insert_index_daily_bar_fact(cur, row)
        if (commit_plan.get("rows") or {}).get("index"):
            written_tables.add("index_daily_bar_fact")
        for row in (commit_plan.get("rows") or {}).get("board", []):
            insert_board_daily_bar_fact(cur, row)
        if (commit_plan.get("rows") or {}).get("board"):
            written_tables.add("board_daily_bar_fact")
        for row in commit_plan.get("quality_rows") or []:
            insert_quality_gate_result(cur, row)
        if commit_plan.get("quality_rows"):
            written_tables.add("common_quality_gate_result")
        for row in commit_plan.get("active_source_version_rows") or []:
            insert_active_source_version(cur, row)
        if commit_plan.get("active_source_version_rows"):
            written_tables.add("common_active_source_version")
        update_ingest_batch_passed(cur, commit_plan)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return normalize_jsonable(
        {
            "committed": True,
            "batch_id": commit_plan.get("batch_id"),
            "written_tables": sorted(written_tables),
            "row_counts": commit_plan.get("row_counts") or {},
        }
    )


def normalize_expected_scope(expected_scope: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        asset: [dict(row) for row in (expected_scope.get(asset) or [])]
        for asset in ASSET_KINDS
    }


def normalize_bundle_rows(bundle: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        asset: [dict(row) for row in (bundle.get(asset) or [])]
        for asset in ASSET_KINDS
    }


def ts_code_from_scope(scope_row: Mapping[str, Any]) -> str:
    code = str(scope_row.get("code") or "")
    exchange = str(scope_row.get("exchange") or "")
    return f"{code}.{exchange}"


def _frame_to_records(frame: Any) -> list[dict[str, Any]]:
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


def to_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def quality_item(
    *,
    gate_name: str,
    status: str,
    severity: str,
    expected_value: Any,
    actual_value: Any,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "gate_name": gate_name,
        "status": status,
        "severity": severity,
        "expected_value": expected_value,
        "actual_value": actual_value,
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
            if asset == "board" and (not identity_key.startswith("board:") or not BOARD_881_RE.match(code)):
                violations.append({"asset": asset, "identity_key": identity_key, "code": code})
    return violations


def previous_active_source_version(baseline: Mapping[str, Any], asset: str) -> str | None:
    for row in baseline.get("active_source_versions_for_trade_date") or []:
        if row.get("data_domain") == asset and row.get("data_type") == ACTIVE_DATA_TYPES[asset]:
            return str(row.get("source_version") or "") or None
    return None


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
          'n1.official_daily.source_fetch', %(source_version)s,
          %(source_params)s, %(row_count)s, 0, %(quality_gate_summary)s,
          %(rollback_strategy)s, 'running', now()
        )
        """,
        {
            "batch_id": commit_plan["batch_id"],
            "trade_date": commit_plan["for_trade_date"],
            "source_version": commit_plan["contract_source_version"],
            "source_params": Jsonb(
                {
                    "source_versions": commit_plan.get("source_versions"),
                    "postgres_only": True,
                    "parquet_write": False,
                }
            ),
            "row_count": int((commit_plan.get("row_counts") or {}).get("total", 0)),
            "quality_gate_summary": Jsonb({"p0_count": 0, "validation": "passed"}),
            "rollback_strategy": DEFAULT_ROLLBACK_SQL_PATH,
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
        {
            **dict(row),
            "raw_payload": Jsonb(row.get("raw_payload") or {}),
        },
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
        {
            **dict(row),
            "raw_payload": Jsonb(row.get("raw_payload") or {}),
        },
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
        {
            **dict(row),
            "raw_payload": Jsonb(row.get("raw_payload") or {}),
        },
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
        {
            **dict(row),
            "details": Jsonb(row.get("details") or {}),
        },
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


def build_execute_preflight_report(
    *,
    dry_run_report: Mapping[str, Any],
    baseline: Mapping[str, Any],
    execute_requested: bool,
    user_confirmed: bool,
    source_fetch_enabled: bool = False,
    postgres_commit_enabled: bool = False,
    rollback_sql_path: str | Path = DEFAULT_ROLLBACK_SQL_PATH,
    generated_at: str | None = None,
) -> dict[str, Any]:
    blockers = build_blockers(dry_run_report=dry_run_report, baseline=baseline, rollback_sql_path=rollback_sql_path)
    if execute_requested and not user_confirmed:
        blockers.append("missing_user_confirmed")
    if execute_requested and user_confirmed and not source_fetch_enabled:
        blockers.append("source_fetch_disabled")
    if execute_requested and user_confirmed and not postgres_commit_enabled:
        blockers.append("postgres_commit_disabled")

    result = "PREFLIGHT_BLOCKED" if blockers else "PREFLIGHT_PASS"
    missing = (dry_run_report.get("missing_official_daily") or {}).get("missing_by_asset") or {}
    baseline_rows = {
        "current_official_daily_rows": normalize_counts(baseline.get("current_official_daily_rows") or {}),
        "eod_snapshot_rows": normalize_counts(baseline.get("eod_snapshot_rows") or {}),
        "c3_outbox_status": normalize_outbox_status(baseline.get("c3_outbox_status") or {}),
        "target_source_version_conflicts": normalize_counts(baseline.get("target_source_version_conflicts") or {}),
        "active_source_version_count": len(baseline.get("active_source_versions_for_trade_date") or []),
        "common_ingest_batch_exists": bool(baseline.get("common_ingest_batch_exists")),
    }
    rollback_path = str(rollback_sql_path)
    report = {
        "stage": "N1 official daily fact ingestion execute preflight",
        "layer_role": "N1_ingestion",
        "result": result,
        "blocked": bool(blockers),
        "blockers": blockers,
        "runner_readiness": "blocked" if blockers else "ready_for_final_gate",
        "execute_authorized": False,
        "for_trade_date": str(dry_run_report.get("for_trade_date") or FOR_TRADE_DATE),
        "contract_batch_id": CONTRACT_BATCH_ID,
        "contract_source_version": CONTRACT_SOURCE_VERSION,
        "source_versions": dict(SOURCE_VERSIONS),
        "execute_flags_required": ["--execute", "--user-confirmed"],
        "final_gate_required": True,
        "final_gate_flags_required": ["--source-fetch-enabled", "--postgres-commit-enabled"],
        "execute_flags_seen": {
            "execute": bool(execute_requested),
            "user_confirmed": bool(user_confirmed),
            "source_fetch_enabled": bool(source_fetch_enabled),
            "postgres_commit_enabled": bool(postgres_commit_enabled),
        },
        "missing_official_daily": normalize_counts(missing),
        "baseline_rows": baseline_rows,
        "baseline_guard": {
            "common_ingest_batch_absent": not bool(baseline.get("common_ingest_batch_exists")),
            "target_source_versions_absent": sum(baseline_rows["target_source_version_conflicts"].values()) == 0,
            "active_source_version_absent": baseline_rows["active_source_version_count"] == 0,
            "eod_snapshot_rows_zero": baseline_rows["eod_snapshot_rows"].get("total", 0) == 0,
            "c3_outbox_pending_expected": baseline_rows["c3_outbox_status"].get("pending") == EXPECTED_C3_PENDING,
        },
        "expected_future_writes": {
            "allowed_tables": list(ALLOWED_EXECUTE_WRITE_TABLES),
            "writes_postgres": True,
            "writes_parquet": False,
            "updates_active_source_version": True,
            "writes_outbox": False,
            "consumes_c3_outbox": False,
            "enters_n3_n4_n5_n6": False,
        },
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "rollback": {
            "path": rollback_path,
            "exists": Path(rollback_path).exists(),
            "batch_id": CONTRACT_BATCH_ID,
            "source_versions": dict(SOURCE_VERSIONS),
            "strategy": "delete_by_source_batch_id_then_restore_previous_active_source_version",
        },
        "source_fetch": {
            "implemented": True,
            "routes": SOURCE_FETCH_ROUTES,
            "enabled_for_this_run": bool(source_fetch_enabled),
            "will_call_external_sources_this_turn": False,
            "final_execute_requires_source_fetch_gate": True,
        },
        "postgres_commit": {
            "implemented": True,
            "enabled_for_this_run": bool(postgres_commit_enabled),
            "single_transaction": True,
            "allowed_tables": list(ALLOWED_EXECUTE_WRITE_TABLES),
            "will_write_postgres_this_turn": False,
        },
        "execute_pipeline": {
            "wired": True,
            "enabled_for_this_run": bool(execute_requested and user_confirmed and source_fetch_enabled and postgres_commit_enabled),
            "sequence": [
                "load_execute_contract",
                "refresh_final_preflight_baseline_guard",
                "source_fetch_adapter_routing",
                "source_bundle_validation",
                "commit_preconditions",
                "build_commit_plan",
                "execute_commit_transaction",
            ],
            "uses_mock_only_in_tests": True,
        },
        "side_effects": {
            "read_only_database_checks": bool(baseline.get("read_only_database_checks", False)),
            "will_call_external_sources": False,
            "writes_postgres": False,
            "writes_parquet": False,
            "updates_active_source_version": False,
            "writes_outbox": False,
            "consumes_c3_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "enters_n3_n4_n5_n6": False,
            "worker_started": False,
            "old_system_touched": False,
            "real_trading": False,
        },
        "handoff": {
            "next_step": "N1 official daily ingestion execute final gate",
            "next_step_is_not_executed_by_this_preflight": True,
            "execute_command_template": (
                "PYTHONPATH=src python3 scripts/run_official_daily_ingestion_20260525_once.py "
                "--trade-date 20260525 --execute --user-confirmed --source-fetch-enabled --postgres-commit-enabled"
            ),
        },
        "generated_at": generated_at or now_iso(),
    }
    return normalize_jsonable(report)


def build_blockers(*, dry_run_report: Mapping[str, Any], baseline: Mapping[str, Any], rollback_sql_path: str | Path) -> list[str]:
    blockers: list[str] = []
    if dry_run_report.get("result") != "DRY_RUN_PASS":
        blockers.append("dry_run_not_passed")
    if int((dry_run_report.get("quality") or {}).get("p0_count") or 0) != 0:
        blockers.append("dry_run_p0_not_zero")
    if dry_run_report.get("contract_batch_id") != CONTRACT_BATCH_ID:
        blockers.append("contract_batch_id_mismatch")
    if dict(dry_run_report.get("source_versions") or {}) != dict(SOURCE_VERSIONS):
        blockers.append("source_version_mismatch")
    if bool(baseline.get("common_ingest_batch_exists")):
        blockers.append("existing_batch_id")
    source_conflicts = normalize_counts(baseline.get("target_source_version_conflicts") or {})
    if sum(source_conflicts.values()) != 0:
        blockers.append("existing_source_version")
    if len(baseline.get("active_source_versions_for_trade_date") or []) != 0:
        blockers.append("existing_active_source_version")
    eod_rows = normalize_counts(baseline.get("eod_snapshot_rows") or {})
    if eod_rows.get("total", 0) != 0:
        blockers.append("eod_snapshot_rows_not_zero")
    c3_status = normalize_outbox_status(baseline.get("c3_outbox_status") or {})
    if c3_status.get("pending", 0) != EXPECTED_C3_PENDING or c3_status.get("total", 0) != EXPECTED_C3_PENDING:
        blockers.append("c3_outbox_pending_drift")
    if c3_status.get("delivered", 0) != 0 or c3_status.get("delivering", 0) != 0:
        blockers.append("c3_outbox_consumed_or_delivering")
    if not Path(rollback_sql_path).exists():
        blockers.append("rollback_sql_missing")
    return blockers


def build_baseline_snapshot_from_db(
    *,
    dsn: str,
    for_trade_date: str = FOR_TRADE_DATE,
    eod_report_path: str | Path = DEFAULT_EOD_REPORT_JSON,
) -> dict[str, Any]:
    eod_report = load_json(eod_report_path)
    lineage = eod_report.get("lineage_allowlist") or {}
    eod_run_id = str(eod_report.get("eod_run_id") or "")
    c3_run_id = str(lineage.get("source_c3_run_id") or "")
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            current_rows, _, _, _ = fetch_current_fact_state(cur, for_trade_date=for_trade_date)
            baseline = {
                "common_ingest_batch_exists": fetch_contract_batch_exists(cur),
                "target_source_version_conflicts": fetch_target_source_version_conflicts(cur, for_trade_date=for_trade_date),
                "active_source_versions_for_trade_date": fetch_active_source_versions_for_trade_date(cur, for_trade_date=for_trade_date),
                "current_official_daily_rows": add_total(current_rows),
                "eod_snapshot_rows": fetch_eod_snapshot_rows(cur, eod_run_id=eod_run_id),
                "c3_outbox_status": fetch_c3_outbox_status(cur, c3_run_id=c3_run_id),
                "eod_run_id": eod_run_id,
                "c3_run_id": c3_run_id,
                "read_only_database_checks": True,
            }
    return normalize_jsonable(baseline)


def fetch_eod_snapshot_rows(cur: Any, *, eod_run_id: str) -> dict[str, int]:
    rows: dict[str, int] = {}
    for asset, table in EOD_SNAPSHOT_TABLES.items():
        cur.execute(f"SELECT COUNT(*)::int AS row_count FROM {table} WHERE eod_run_id = %s", (eod_run_id,))
        rows[asset] = int(cur.fetchone()["row_count"])
    return add_total(rows)


def fetch_c3_outbox_status(cur: Any, *, c3_run_id: str) -> dict[str, int]:
    status = {"pending": 0, "delivered": 0, "delivering": 0, "total": 0}
    cur.execute(
        """
        SELECT status, COUNT(*)::int AS row_count
        FROM common_event_outbox
        WHERE source_run_id = %s
          AND event_type = 'MinuteBarClosed'
        GROUP BY status
        """,
        (c3_run_id,),
    )
    for row in cur.fetchall():
        key = str(row["status"])
        count = int(row["row_count"])
        status[key] = count
        status["total"] += count
    return status


def add_total(counts: Mapping[str, Any]) -> dict[str, int]:
    result = {asset: int(counts.get(asset, 0) or 0) for asset in ASSET_KINDS}
    result["total"] = sum(result.values())
    return result


def normalize_outbox_status(value: Mapping[str, Any]) -> dict[str, int]:
    return {
        "pending": int(value.get("pending", 0) or 0),
        "delivered": int(value.get("delivered", 0) or 0),
        "delivering": int(value.get("delivering", 0) or 0),
        "total": int(value.get("total", 0) or 0),
    }


def load_dry_run_report(path: str | Path = DEFAULT_DRY_RUN_REPORT_PATH) -> dict[str, Any]:
    return load_json(path)


def render_preflight_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# N1 Official Daily 20260525 Ingestion Execute Preflight",
            "",
            "## Summary",
            "",
            f"- result: `{report.get('result')}`",
            f"- blocked: `{report.get('blocked')}`",
            f"- blockers: `{report.get('blockers')}`",
            f"- runner_readiness: `{report.get('runner_readiness')}`",
            f"- execute_authorized: `{report.get('execute_authorized')}`",
            f"- contract_batch_id: `{report.get('contract_batch_id')}`",
            f"- source_versions: `{report.get('source_versions')}`",
            f"- missing_official_daily: `{report.get('missing_official_daily')}`",
            "",
            "## Baseline",
            "",
            f"- current_official_daily_rows: `{(report.get('baseline_rows') or {}).get('current_official_daily_rows')}`",
            f"- eod_snapshot_rows: `{(report.get('baseline_rows') or {}).get('eod_snapshot_rows')}`",
            f"- c3_outbox_status: `{(report.get('baseline_rows') or {}).get('c3_outbox_status')}`",
            "",
            "## Implementation Gate",
            "",
            f"- source_fetch_implemented: `{((report.get('source_fetch') or {}).get('implemented'))}`",
            f"- source_fetch_enabled_for_this_run: `{((report.get('source_fetch') or {}).get('enabled_for_this_run'))}`",
            f"- postgres_commit_implemented: `{((report.get('postgres_commit') or {}).get('implemented'))}`",
            f"- postgres_commit_enabled_for_this_run: `{((report.get('postgres_commit') or {}).get('enabled_for_this_run'))}`",
            f"- execute_pipeline_wired: `{((report.get('execute_pipeline') or {}).get('wired'))}`",
            f"- execute_pipeline_enabled_for_this_run: `{((report.get('execute_pipeline') or {}).get('enabled_for_this_run'))}`",
            f"- final_gate_required: `{report.get('final_gate_required')}`",
            "",
            "## Future Write Scope",
            "",
            f"- allowed_tables: `{(report.get('expected_future_writes') or {}).get('allowed_tables')}`",
            f"- writes_parquet: `{(report.get('expected_future_writes') or {}).get('writes_parquet')}`",
            f"- writes_outbox: `{(report.get('expected_future_writes') or {}).get('writes_outbox')}`",
            f"- enters_n3_n4_n5_n6: `{(report.get('expected_future_writes') or {}).get('enters_n3_n4_n5_n6')}`",
            "",
            "## Rollback",
            "",
            f"- rollback_path: `{(report.get('rollback') or {}).get('path')}`",
            f"- rollback_exists: `{(report.get('rollback') or {}).get('exists')}`",
            "",
            "## Decision",
            "",
            "This preflight does not execute ingestion. Source fetch and PostgreSQL commit are implemented but remain disabled behind a future explicit final gate.",
            "",
        ]
    )


def write_preflight_files(report: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    json_target = Path(json_path)
    markdown_target = Path(markdown_path)
    json_target.parent.mkdir(parents=True, exist_ok=True)
    markdown_target.parent.mkdir(parents=True, exist_ok=True)
    json_target.write_text(json.dumps(normalize_jsonable(report), ensure_ascii=False, indent=2) + "\n")
    markdown_target.write_text(render_preflight_markdown(report))
