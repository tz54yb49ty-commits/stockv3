"""Execute runner support for N1 condition source activation 20260526.

The module is safe to import and test. Real PostgreSQL writes only happen when
the run-once CLI receives all explicit final-gate flags.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import importlib
import json
import os
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.ingestion.tushare_env import load_tushare_token
from ashare_v3.ingestion.condition_source_activation_20260526 import (
    ACTIVE_SCOPES,
    ALLOWED_FUTURE_WRITE_TABLES,
    BATCH_ID,
    DATA_DOMAINS,
    DEFAULT_PATHS,
    EXPECTED_REFERENCE_ROWS,
    FORBIDDEN_SCOPE,
    OFFICIAL_NO_TRADE_EXCLUDED,
    SOURCE_VERSIONS,
    STALE_IDENTITY_EXCLUDED,
    TDX_ROOT,
    TRADE_DATE,
    build_blockers,
    build_contract,
    build_expected_rows,
    build_preflight,
    build_quality_items,
    build_rollback_sql,
    normalize_jsonable,
    sample_pass_snapshot,
    summarize_quality,
    write_artifacts,
)
from ashare_v3.ingestion.tdx_local import (
    TDXLocalTxtSource,
    normalize_board_membership_row,
    normalize_index_membership_row,
)


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
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


class ConditionSourceActivation20260526Blocked(RuntimeError):
    """Raised when the condition source activation execute gate is blocked."""


def now_iso() -> str:
    return datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat()


def validate_execute_request(
    *,
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> None:
    if not execute_requested:
        raise ConditionSourceActivation20260526Blocked("missing --execute")
    if not user_confirmed:
        raise ConditionSourceActivation20260526Blocked("missing --user-confirmed")
    if not postgres_commit_enabled:
        raise ConditionSourceActivation20260526Blocked("missing --postgres-commit-enabled")


class DefaultConditionSourceActivation20260526SourceBuilder:
    """Build source rows lazily, only after the final execute gate is open."""

    def __init__(self, *, tdx_root: str | Path = TDX_ROOT, tushare_token: str | None = None) -> None:
        self.tdx_root = Path(tdx_root)
        self.tushare_token = tushare_token or load_tushare_token()
        self._tushare_client: Any | None = None

    def build_source_bundle(self, *, dsn: str, trade_date: str, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        if trade_date != TRADE_DATE:
            raise ConditionSourceActivation20260526Blocked(f"trade_date must be {TRADE_DATE}")
        with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                stock_scope = fetch_active_stock_daily_scope(cur, snapshot=snapshot)
                stock_daily_basic_rows = self.fetch_stock_daily_basic_rows(stock_scope=stock_scope)
                stock_financial_rows = build_stock_financial_snapshot_rows(
                    cur,
                    stock_daily_basic_rows=stock_daily_basic_rows,
                )
                index_membership_rows, board_membership_rows, manifests = build_membership_rows_from_tdx(
                    cur,
                    tdx_root=self.tdx_root,
                )
        return normalize_jsonable(
            {
                "stock_daily_basic": stock_daily_basic_rows,
                "stock_financial": stock_financial_rows,
                "index_membership": index_membership_rows,
                "board_membership": board_membership_rows,
                "manifests": {
                    **manifests,
                    "stale_identity_excluded": list(STALE_IDENTITY_EXCLUDED),
                    "official_no_trade_excluded": list(OFFICIAL_NO_TRADE_EXCLUDED),
                },
            }
        )

    def fetch_stock_daily_basic_rows(self, *, stock_scope: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
        pro = self._pro()
        raw_rows = frame_to_records(pro.daily_basic(trade_date=TRADE_DATE, fields=DAILY_BASIC_FIELDS))
        raw_by_ts_code = {str(row.get("ts_code") or ""): dict(row) for row in raw_rows}
        rows: list[dict[str, Any]] = []
        for stock in stock_scope:
            ts_code = str(stock.get("ts_code") or "")
            raw = raw_by_ts_code.get(ts_code)
            if not raw:
                continue
            rows.append(
                {
                    "stock_identity_key": stock["stock_identity_key"],
                    "trade_date": TRADE_DATE,
                    "ts_code": ts_code,
                    "code": stock["code"],
                    "exchange": stock["exchange"],
                    "close": raw.get("close"),
                    "turnover_rate": raw.get("turnover_rate"),
                    "turnover_rate_f": raw.get("turnover_rate_f"),
                    "volume_ratio": raw.get("volume_ratio"),
                    "pe": raw.get("pe"),
                    "pe_ttm": raw.get("pe_ttm"),
                    "pb": raw.get("pb"),
                    "ps": raw.get("ps"),
                    "ps_ttm": raw.get("ps_ttm"),
                    "dv_ratio": raw.get("dv_ratio"),
                    "dv_ttm": raw.get("dv_ttm"),
                    "total_share": raw.get("total_share"),
                    "float_share": raw.get("float_share"),
                    "free_share": raw.get("free_share"),
                    "total_mv": raw.get("total_mv"),
                    "circ_mv": raw.get("circ_mv"),
                    "source": "tushare.daily_basic",
                    "source_batch_id": BATCH_ID,
                    "source_version": SOURCE_VERSIONS["stock_daily_basic"],
                    "raw_payload": raw,
                }
            )
        return rows

    def _pro(self) -> Any:
        if self._tushare_client is None:
            if not self.tushare_token:
                raise ConditionSourceActivation20260526Blocked("TUSHARE_TOKEN is required for stock_daily_basic")
            tushare = importlib.import_module("tushare")
            self._tushare_client = tushare.pro_api(self.tushare_token)
        return self._tushare_client


def frame_to_records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        return [dict(row) for row in frame.to_dict("records")]
    return [dict(row) for row in frame]


def fetch_active_stock_daily_scope(cur: Any, *, snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    stock_daily_version = ((snapshot.get("upstream_daily") or {}).get("stock_daily") or {}).get("active_source_version")
    if not stock_daily_version:
        raise ConditionSourceActivation20260526Blocked("stock_daily active source_version is required")
    cur.execute(
        """
        SELECT stock_identity_key, trade_date, ts_code, code, exchange, name
        FROM stock_daily_bar_fact
        WHERE trade_date = %s
          AND source_version = %s
        ORDER BY stock_identity_key
        """,
        (TRADE_DATE, stock_daily_version),
    )
    return [dict(row) for row in cur.fetchall()]


def build_stock_financial_snapshot_rows(
    cur: Any,
    *,
    stock_daily_basic_rows: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
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
        (SOURCE_VERSIONS["stock_financial"], TRADE_DATE),
    )
    latest = {str(row["stock_identity_key"]): dict(row) for row in cur.fetchall()}
    rows: list[dict[str, Any]] = []
    for stock in stock_daily_basic_rows:
        identity_key = str(stock["stock_identity_key"])
        candidate = latest.get(identity_key)
        pe_core = stock.get("pe_ttm") or stock.get("pe")
        if candidate is None or candidate.get("quality_status") == "warning":
            metrics = {
                "announcement_date": None,
                "report_period": None,
                "roe": None,
                "revenue_yoy": None,
                "profit_yoy": None,
                "total_revenue": None,
                "net_profit": None,
                "net_assets": None,
                "eps": None,
                "bps": None,
                "pe_core": None,
                "score": 0,
                "warning": "未找到可用财报",
                "quality_status": "warning",
            }
        else:
            metrics = {
                "announcement_date": candidate.get("announcement_date") or candidate.get("asof_date"),
                "report_period": candidate.get("report_period"),
                "roe": candidate.get("roe"),
                "revenue_yoy": candidate.get("revenue_yoy"),
                "profit_yoy": candidate.get("profit_yoy"),
                "total_revenue": candidate.get("total_revenue"),
                "net_profit": candidate.get("net_profit"),
                "net_assets": candidate.get("net_assets"),
                "eps": candidate.get("eps"),
                "bps": candidate.get("bps"),
                "pe_core": pe_core or candidate.get("pe_core"),
                "score": 1,
                "warning": None,
                "quality_status": "passed",
            }
        rows.append(
            {
                "stock_identity_key": identity_key,
                "asof_date": TRADE_DATE,
                "source_trade_date": TRADE_DATE,
                "ts_code": stock["ts_code"],
                "code": stock["code"],
                "exchange": stock["exchange"],
                "total_mv": stock.get("total_mv") or (candidate or {}).get("total_mv"),
                "circ_mv": stock.get("circ_mv") or (candidate or {}).get("circ_mv"),
                "source": "financial_asof_snapshot.tdx_mootdx_first_existing+tushare_fallback+daily_basic",
                "source_batch_id": BATCH_ID,
                "source_version": SOURCE_VERSIONS["stock_financial"],
                "raw_payload": {
                    "snapshot_rule": "latest announcement_date <= source_trade_date; TDX/Mootdx preferred; placeholder when unavailable",
                    "selected_financial": candidate,
                    "daily_basic": stock.get("raw_payload"),
                },
                **metrics,
            }
        )
    return rows


def build_membership_rows_from_tdx(cur: Any, *, tdx_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    source = TDXLocalTxtSource(tdx_root)
    raw_index_rows = list(source.fetch_index_membership_rows())
    raw_board_rows = list(source.fetch_board_membership_rows())
    stock_keys = fetch_key_set(cur, "SELECT stock_identity_key FROM stock_identity")
    index_keys = fetch_key_set(cur, "SELECT index_identity_key FROM index_identity")
    board_keys = fetch_key_set(cur, "SELECT board_identity_key FROM board_identity")
    index_rows = [
        normalize_index_membership_row(
            row,
            trade_date=TRADE_DATE,
            source_batch_id=BATCH_ID,
            source_version=SOURCE_VERSIONS["index_membership"],
        )
        for row in raw_index_rows
    ]
    board_rows = [
        normalize_board_membership_row(
            row,
            trade_date=TRADE_DATE,
            source_batch_id=BATCH_ID,
            source_version=SOURCE_VERSIONS["board_membership"],
        )
        for row in raw_board_rows
    ]
    filtered_index = [
        row for row in index_rows if row["index_identity_key"] in index_keys and row["stock_identity_key"] in stock_keys
    ]
    filtered_board = [
        row for row in board_rows if row["board_identity_key"] in board_keys and row["stock_identity_key"] in stock_keys
    ]
    manifests = {
        "index_raw_rows": len(raw_index_rows),
        "board_raw_rows": len(raw_board_rows),
        "index_unmapped_raw_count": len(index_rows) - len(filtered_index),
        "board_unmapped_raw_count": len(board_rows) - len(filtered_board),
    }
    return filtered_index, filtered_board, manifests


def fetch_key_set(cur: Any, sql: str) -> set[str]:
    cur.execute(sql)
    return {str(next(iter(dict(row).values()))) if isinstance(row, dict) else str(row[0]) for row in cur.fetchall()}


def row_counts(bundle: Mapping[str, Any]) -> dict[str, int]:
    counts = {
        "stock_daily_basic": len(bundle.get("stock_daily_basic") or []),
        "stock_financial": len(bundle.get("stock_financial") or []),
        "index_membership": len(bundle.get("index_membership") or []),
        "board_membership": len(bundle.get("board_membership") or []),
    }
    counts["total"] = sum(counts.values())
    return counts


def validate_source_bundle(*, bundle: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    expected = build_expected_rows(snapshot)
    counts = row_counts(bundle)
    quality_items: list[dict[str, Any]] = []
    blockers: list[str] = []
    for data_type in ("stock_daily_basic", "stock_financial", "index_membership", "board_membership"):
        passed = counts[data_type] == expected[data_type]
        if not passed:
            blockers.append(f"{data_type}_row_count_mismatch")
        quality_items.append(
            quality_item(
                f"{data_type}_row_count",
                "P0",
                "passed" if passed else "failed",
                expected[data_type],
                counts[data_type],
            )
        )
        contract_errors = [
            row_identity(row, data_type)
            for row in bundle.get(data_type) or []
            if row.get("source_batch_id") != BATCH_ID
            or row.get("source_version") != SOURCE_VERSIONS[data_type]
            or row_date(row, data_type) != TRADE_DATE
        ]
        if contract_errors:
            blockers.append(f"{data_type}_source_contract_mismatch")
        quality_items.append(
            quality_item(
                f"{data_type}_source_contract",
                "P0",
                "passed" if not contract_errors else "failed",
                f"{TRADE_DATE}/{BATCH_ID}/{SOURCE_VERSIONS[data_type]}",
                len(contract_errors),
                {"failed_sample": contract_errors[:10]},
            )
        )

    stock_daily_basic_ids = {str(row.get("stock_identity_key") or "") for row in bundle.get("stock_daily_basic") or []}
    stock_financial_ids = {str(row.get("stock_identity_key") or "") for row in bundle.get("stock_financial") or []}
    stale_leaks = sorted((stock_daily_basic_ids | stock_financial_ids) & set(STALE_IDENTITY_EXCLUDED))
    no_trade_leaks = sorted((stock_daily_basic_ids | stock_financial_ids) & set(OFFICIAL_NO_TRADE_EXCLUDED))
    if stale_leaks:
        blockers.append("stale_identity_leaked_into_stock_condition_source")
    if no_trade_leaks:
        blockers.append("official_no_trade_leaked_into_stock_condition_source")
    quality_items.append(
        quality_item(
            "stale_identity_excluded",
            "P0",
            "passed" if not stale_leaks else "failed",
            0,
            len(stale_leaks),
            {"identity_keys": stale_leaks},
        )
    )
    quality_items.append(
        quality_item(
            "official_no_trade_excluded",
            "P0",
            "passed" if not no_trade_leaks else "failed",
            0,
            len(no_trade_leaks),
            {"identity_keys": no_trade_leaks},
        )
    )

    duplicate_issues = {
        data_type: duplicate_count(bundle.get(data_type) or [], data_type)
        for data_type in ("stock_daily_basic", "stock_financial", "index_membership", "board_membership")
    }
    if any(duplicate_issues.values()):
        blockers.append("duplicate_identity_key")
    quality_items.append(
        quality_item(
            "duplicate_identity_key",
            "P0",
            "passed" if not any(duplicate_issues.values()) else "failed",
            0,
            sum(duplicate_issues.values()),
            duplicate_issues,
        )
    )

    board_unmapped = int(((bundle.get("manifests") or {}).get("board_unmapped_raw_count")) or 0)
    if board_unmapped:
        quality_items.append(
            quality_item(
                "board_unmapped_raw_count_filtered",
                "P2",
                "warning",
                0,
                board_unmapped,
                {"meaning": "raw board membership rows filtered before fact insert"},
            )
        )

    quality = summarize_quality(quality_items)
    return normalize_jsonable(
        {
            "result": "VALIDATION_PASS" if quality["p0_count"] == 0 else "VALIDATION_BLOCKED",
            "p0_count": quality["p0_count"],
            "blockers": sorted(dict.fromkeys(blockers)),
            "row_counts": counts,
            "quality": quality,
            "quality_items": quality_items,
        }
    )


def duplicate_count(rows: list[Mapping[str, Any]], data_type: str) -> int:
    if data_type in ("stock_daily_basic", "stock_financial"):
        values = [str(row.get("stock_identity_key") or "") for row in rows]
    elif data_type == "index_membership":
        values = [f"{row.get('index_identity_key')}|{row.get('stock_identity_key')}" for row in rows]
    else:
        values = [f"{row.get('board_identity_key')}|{row.get('stock_identity_key')}" for row in rows]
    return sum(1 for _, count in Counter(values).items() if count > 1)


def row_identity(row: Mapping[str, Any], data_type: str) -> str:
    if data_type == "index_membership":
        return f"{row.get('index_identity_key')}|{row.get('stock_identity_key')}"
    if data_type == "board_membership":
        return f"{row.get('board_identity_key')}|{row.get('stock_identity_key')}"
    return str(row.get("stock_identity_key") or "")


def row_date(row: Mapping[str, Any], data_type: str) -> str:
    if data_type == "stock_financial":
        return str(row.get("source_trade_date") or "")
    return str(row.get("trade_date") or "")


def quality_item(
    gate_name: str,
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
        "expected_value": str(expected),
        "actual_value": str(actual),
        "details": normalize_jsonable(dict(details or {})),
    }


def validate_commit_preconditions(
    *,
    snapshot: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    postgres_commit_enabled: bool,
) -> None:
    blockers = build_blockers(build_quality_items(snapshot))
    if not postgres_commit_enabled:
        blockers.append("postgres_commit_disabled")
    if int(validation_report.get("p0_count") or 0) != 0:
        blockers.extend(str(blocker) for blocker in validation_report.get("blockers") or ["source_validation_p0"])
    if blockers:
        raise ConditionSourceActivation20260526Blocked(", ".join(sorted(dict.fromkeys(blockers))))


def build_commit_plan(
    *,
    bundle: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    baseline: Mapping[str, Any],
) -> dict[str, Any]:
    if int(validation_report.get("p0_count") or 0) != 0:
        raise ConditionSourceActivation20260526Blocked("source validation P0 must be zero before commit plan")
    counts = row_counts(bundle)
    quality_rows = [
        {
            "source_batch_id": BATCH_ID,
            "source_version": BATCH_ID,
            "data_domain": "common",
            "data_type": "condition_source_activation",
            "gate_name": item["gate_name"],
            "severity": item["severity"],
            "status": item["status"],
            "expected_value": item.get("expected_value"),
            "actual_value": item.get("actual_value"),
            "details": item.get("details") or {},
        }
        for item in validation_report.get("quality_items") or []
    ]
    active_rows = [
        {
            "data_domain": DATA_DOMAINS[data_type],
            "data_type": data_type,
            "scope_key": ACTIVE_SCOPES[data_type],
            "source_version": SOURCE_VERSIONS[data_type],
            "source_batch_id": BATCH_ID,
            "previous_source_version": previous_active_source_version(baseline, data_type),
            "activated_by": "n1_condition_source_activation_20260526_execute_runner",
        }
        for data_type in ("stock_daily_basic", "stock_financial", "index_membership", "board_membership")
    ]
    return normalize_jsonable(
        {
            "trade_date": TRADE_DATE,
            "batch_id": BATCH_ID,
            "source_versions": dict(SOURCE_VERSIONS),
            "allowed_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
            "row_counts": counts,
            "rows": {
                "stock_daily_basic": list(bundle.get("stock_daily_basic") or []),
                "stock_financial": list(bundle.get("stock_financial") or []),
                "index_membership": list(bundle.get("index_membership") or []),
                "board_membership": list(bundle.get("board_membership") or []),
            },
            "quality_rows": quality_rows,
            "active_source_version_rows": active_rows,
            "manifests": bundle.get("manifests") or {},
            "side_effects": {
                "writes_parquet": False,
                "writes_outbox": False,
                "writes_inbox_or_checkpoint": False,
                "enters_n2_n3_n4_n5_n6": False,
            },
        }
    )


def previous_active_source_version(baseline: Mapping[str, Any], data_type: str) -> str | None:
    for row in baseline.get("active_target_source_versions") or []:
        if row.get("data_type") == data_type:
            return row.get("source_version")
    return None


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
    unexpected_tables = sorted(set(commit_plan.get("allowed_tables") or []) - set(ALLOWED_FUTURE_WRITE_TABLES))
    if unexpected_tables:
        raise ConditionSourceActivation20260526Blocked(f"unexpected write tables: {unexpected_tables}")
    cur = conn.cursor()
    try:
        insert_ingest_batch(cur, commit_plan)
        insert_stock_daily_basic_rows(cur, (commit_plan.get("rows") or {}).get("stock_daily_basic") or [])
        insert_stock_financial_rows(cur, (commit_plan.get("rows") or {}).get("stock_financial") or [])
        insert_index_membership_rows(cur, (commit_plan.get("rows") or {}).get("index_membership") or [])
        insert_board_membership_rows(cur, (commit_plan.get("rows") or {}).get("board_membership") or [])
        insert_quality_rows(cur, commit_plan.get("quality_rows") or [])
        insert_active_source_version_rows(cur, commit_plan.get("active_source_version_rows") or [])
        update_ingest_batch_passed(cur)
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


def insert_ingest_batch(cur: Any, commit_plan: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO common_ingest_batch (
          batch_id, trade_date, data_domain, data_type, source, source_version,
          source_path, source_params, raw_hash, row_count, error_count,
          quality_gate_summary, error_summary, rollback_strategy, status, started_at
        )
        VALUES (
          %(batch_id)s, %(trade_date)s, 'common', 'condition_source_activation',
          'n1.condition_source_activation.20260526', %(source_version)s,
          NULL, %(source_params)s, NULL, %(row_count)s, 0,
          %(quality_gate_summary)s, NULL, %(rollback_strategy)s, 'running', now()
        )
        """,
        {
            "batch_id": BATCH_ID,
            "trade_date": TRADE_DATE,
            "source_version": BATCH_ID,
            "source_params": Jsonb({"source_versions": SOURCE_VERSIONS, "active_scopes": ACTIVE_SCOPES}),
            "row_count": int((commit_plan.get("row_counts") or {}).get("total") or 0),
            "quality_gate_summary": Jsonb({"expected_rows": commit_plan.get("row_counts") or {}}),
            "rollback_strategy": str(DEFAULT_PATHS["rollback_sql"]),
        },
    )


def insert_stock_daily_basic_rows(cur: Any, rows: list[Mapping[str, Any]]) -> None:
    cur.executemany(
        """
        INSERT INTO stock_daily_basic (
          stock_identity_key, trade_date, ts_code, code, exchange, close,
          turnover_rate, turnover_rate_f, volume_ratio, pe, pe_ttm, pb, ps,
          ps_ttm, dv_ratio, dv_ttm, total_share, float_share, free_share,
          total_mv, circ_mv, source, source_batch_id, source_version, raw_payload
        )
        VALUES (
          %(stock_identity_key)s, %(trade_date)s, %(ts_code)s, %(code)s, %(exchange)s, %(close)s,
          %(turnover_rate)s, %(turnover_rate_f)s, %(volume_ratio)s, %(pe)s, %(pe_ttm)s, %(pb)s, %(ps)s,
          %(ps_ttm)s, %(dv_ratio)s, %(dv_ttm)s, %(total_share)s, %(float_share)s, %(free_share)s,
          %(total_mv)s, %(circ_mv)s, %(source)s, %(source_batch_id)s, %(source_version)s, %(raw_payload)s
        )
        """,
        [jsonb_row(row) for row in rows],
    )


def insert_stock_financial_rows(cur: Any, rows: list[Mapping[str, Any]]) -> None:
    cur.executemany(
        """
        INSERT INTO stock_financial_metrics_fact (
          stock_identity_key, asof_date, source_trade_date, announcement_date, report_period,
          ts_code, code, exchange, roe, revenue_yoy, profit_yoy, total_revenue,
          net_profit, net_assets, eps, bps, pe_core, total_mv, circ_mv,
          score, warning, quality_status, source, source_batch_id, source_version, raw_payload
        )
        VALUES (
          %(stock_identity_key)s, %(asof_date)s, %(source_trade_date)s, %(announcement_date)s, %(report_period)s,
          %(ts_code)s, %(code)s, %(exchange)s, %(roe)s, %(revenue_yoy)s, %(profit_yoy)s, %(total_revenue)s,
          %(net_profit)s, %(net_assets)s, %(eps)s, %(bps)s, %(pe_core)s, %(total_mv)s, %(circ_mv)s,
          %(score)s, %(warning)s, %(quality_status)s, %(source)s, %(source_batch_id)s, %(source_version)s, %(raw_payload)s
        )
        """,
        [jsonb_row(row) for row in rows],
    )


def insert_index_membership_rows(cur: Any, rows: list[Mapping[str, Any]]) -> None:
    cur.executemany(
        """
        INSERT INTO index_membership_fact (
          trade_date, index_identity_key, stock_identity_key, index_code, index_name,
          stock_code, stock_name, source, source_file, source_batch_id, source_version, raw_payload
        )
        VALUES (
          %(trade_date)s, %(index_identity_key)s, %(stock_identity_key)s, %(index_code)s, %(index_name)s,
          %(stock_code)s, %(stock_name)s, %(source)s, %(source_file)s, %(source_batch_id)s, %(source_version)s, %(raw_payload)s
        )
        """,
        [jsonb_row(row) for row in rows],
    )


def insert_board_membership_rows(cur: Any, rows: list[Mapping[str, Any]]) -> None:
    cur.executemany(
        """
        INSERT INTO board_membership_fact (
          trade_date, board_identity_key, stock_identity_key, board_code, board_name,
          board_type, stock_code, stock_name, source, source_file, source_batch_id, source_version, raw_payload
        )
        VALUES (
          %(trade_date)s, %(board_identity_key)s, %(stock_identity_key)s, %(board_code)s, %(board_name)s,
          %(board_type)s, %(stock_code)s, %(stock_name)s, %(source)s, %(source_file)s, %(source_batch_id)s, %(source_version)s, %(raw_payload)s
        )
        """,
        [jsonb_row(row) for row in rows],
    )


def insert_quality_rows(cur: Any, rows: list[Mapping[str, Any]]) -> None:
    cur.executemany(
        """
        INSERT INTO common_quality_gate_result (
          source_batch_id, source_version, data_domain, data_type, gate_name,
          severity, status, expected_value, actual_value, details
        )
        VALUES (
          %(source_batch_id)s, %(source_version)s, %(data_domain)s, %(data_type)s,
          %(gate_name)s, %(severity)s, %(status)s, %(expected_value)s, %(actual_value)s, %(details)s
        )
        """,
        [jsonb_row(row) for row in rows],
    )


def insert_active_source_version_rows(cur: Any, rows: list[Mapping[str, Any]]) -> None:
    cur.executemany(
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
        list(rows),
    )


def update_ingest_batch_passed(cur: Any) -> None:
    cur.execute(
        """
        UPDATE common_ingest_batch
        SET status = 'passed',
            finished_at = now()
        WHERE batch_id = %s
        """,
        (BATCH_ID,),
    )


def jsonb_row(row: Mapping[str, Any]) -> dict[str, Any]:
    converted = dict(row)
    for key in ("raw_payload", "details", "source_params", "quality_gate_summary"):
        if key in converted:
            converted[key] = Jsonb(normalize_jsonable(converted.get(key) or {}))
    return converted


def build_execute_preflight_report(
    snapshot: Mapping[str, Any],
    *,
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    base = build_preflight(snapshot)
    blockers = list(base.get("blockers") or [])
    if execute_requested and not user_confirmed:
        blockers.append("missing_user_confirmed")
    if execute_requested and user_confirmed and not postgres_commit_enabled:
        blockers.append("postgres_commit_disabled")
    blockers = sorted(dict.fromkeys(blockers))
    return normalize_jsonable(
        {
            **base,
            "stage": "N1 condition source activation 20260526 execute preflight",
            "result": "PREFLIGHT_BLOCKED" if blockers else "PREFLIGHT_PASS",
            "blocked": bool(blockers),
            "blockers": blockers,
            "execute_authorized": False,
            "final_gate_required": True,
            "final_execute_gate_allowed": not bool(blockers),
            "runner_readiness": "blocked" if blockers else "ready_for_final_gate",
            "execute_runner_implemented": True,
            "postgres_commit_implemented": True,
            "execute_flags_seen": {
                "execute": bool(execute_requested),
                "user_confirmed": bool(user_confirmed),
                "postgres_commit_enabled": bool(postgres_commit_enabled),
            },
            "expected_future_writes": {
                "allowed_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
                "writes_postgres": True,
                "writes_parquet": False,
                "updates_active_source_version": True,
                "writes_outbox": False,
                "enters_n2_n3_n4_n5_n6": False,
            },
            "execute_command_template": (
                "PYTHONPATH=src python3 scripts/run_condition_source_activation_20260526_once.py "
                "--execute --user-confirmed --postgres-commit-enabled"
            ),
            "generated_at": now_iso(),
        }
    )


def write_preflight_files(report: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    Path(json_path).write_text(json.dumps(normalize_jsonable(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(markdown_path).write_text(render_preflight_markdown(report), encoding="utf-8")


def write_contract_files(contract: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    Path(json_path).write_text(json.dumps(normalize_jsonable(contract), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(markdown_path).write_text(render_contract_markdown(contract), encoding="utf-8")


def render_preflight_markdown(report: Mapping[str, Any]) -> str:
    return f"""# N1 Condition Source 20260526 Activation Preflight

Result: `{report["result"]}`

- runner_readiness: `{report["runner_readiness"]}`
- execute_runner_implemented: `{report["execute_runner_implemented"]}`
- postgres_commit_implemented: `{report["postgres_commit_implemented"]}`
- execute_authorized: `{report["execute_authorized"]}`
- final_execute_gate_allowed: `{report["final_execute_gate_allowed"]}`
- P0/P1/P2: `{report["quality"]["p0_count"]}/{report["quality"]["p1_count"]}/{report["quality"]["p2_count"]}`

Expected rows:

```json
{json.dumps(report["expected_rows"], ensure_ascii=False, indent=2)}
```

Rollback SQL: `{DEFAULT_PATHS["rollback_sql"]}`
"""


def render_contract_markdown(contract: Mapping[str, Any]) -> str:
    return f"""# N1 Condition Source 20260526 Activation Contract

Result: `{contract["result"]}`

- layer_role: `N1_ingestion`
- trade_date: `{TRADE_DATE}`
- source_batch_id: `{BATCH_ID}`
- execute runner implemented: `true`
- final execute gate allowed: `{contract.get("implementation_status", {}).get("final_execute_gate_allowed")}`
- allowed tables: `{", ".join(ALLOWED_FUTURE_WRITE_TABLES)}`
- forbidden: `{", ".join(FORBIDDEN_SCOPE)}`

Expected rows:

```json
{json.dumps(contract["expected_rows"], ensure_ascii=False, indent=2)}
```

Rollback SQL: `{DEFAULT_PATHS["rollback_sql"]}`
"""


def build_execute_contract(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    contract = build_contract(snapshot)
    blockers = build_blockers(build_quality_items(snapshot))
    return normalize_jsonable(
        {
            **contract,
            "stage": "N1 condition source activation 20260526 execute contract",
            "execute_flags": ["--execute", "--user-confirmed", "--postgres-commit-enabled"],
            "implementation_status": {
                "execute_runner_implemented": True,
                "source_row_builder": True,
                "source_bundle_validation": True,
                "postgres_commit_transaction": True,
                "cli_execute_pipeline_wired": True,
                "execute_authorized": False,
                "final_execute_gate_allowed": not bool(blockers),
            },
        }
    )


def load_execute_contract(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
