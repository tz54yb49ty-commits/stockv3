"""N1 condition source activation contract/dry-run for 20260526.

This module is intentionally dry-run only. It performs read-only PostgreSQL
checks, reads local TDX txt membership files for planning, and writes contract
artifacts through the CLI wrapper. It does not execute ingestion, write
PostgreSQL, write Parquet, update active source versions, enter downstream
layers, or start workers.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row

from ashare_v3.ingestion.common import stable_raw_hash
from ashare_v3.ingestion.tdx_local import (
    TDXLocalTxtSource,
    normalize_board_membership_row,
    normalize_index_membership_row,
)


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
TRADE_DATE = "20260526"
BATCH_ID = "condition_source_activation_20260526_v1"
TDX_ROOT = Path("/Volumes/MacRaid/tdxdata/tdx")
SOURCE_VERSIONS = {
    "stock_daily_basic": "stock_daily_basic_20260526_v1",
    "stock_financial": "stock_financial_20260526_v1",
    "index_membership": "index_membership_20260526_v1",
    "board_membership": "board_membership_20260526_v1",
}
ACTIVE_SCOPES = {
    "stock_daily_basic": "20260526",
    "stock_financial": "20260526",
    "index_membership": "TDX:20260526",
    "board_membership": "TDX:20260526",
}
DATA_DOMAINS = {
    "stock_daily_basic": "stock",
    "stock_financial": "stock",
    "index_membership": "index",
    "board_membership": "board",
}
EXPECTED_REFERENCE_ROWS = {
    "stock_daily_basic": 5520,
    "stock_financial": 5520,
    "index_membership": 12841,
    "board_membership": 56872,
}
STALE_IDENTITY_EXCLUDED = ("stock:SZ:300114",)
OFFICIAL_NO_TRADE_EXCLUDED = ("stock:BJ:920058", "stock:BJ:920305")
ALLOWED_FUTURE_WRITE_TABLES = (
    "common_ingest_batch",
    "common_quality_gate_result",
    "common_active_source_version",
    "stock_daily_basic",
    "stock_financial_metrics_fact",
    "index_membership_fact",
    "board_membership_fact",
)
FORBIDDEN_SCOPE = (
    "stock_daily_bar_fact",
    "index_daily_bar_fact",
    "board_daily_bar_fact",
    "Parquet",
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "N2_condition_tables",
    "N3_market_data_tables",
    "N4_trigger_tables",
    "N5_action_tables",
    "N6_user_tables",
    "worker",
    "old_system",
    "real_trading",
)
DEFAULT_PATHS = {
    "contract_json": Path("docs/N1_condition_source_20260526_activation_contract.json"),
    "contract_md": Path("docs/N1_CONDITION_SOURCE_20260526_ACTIVATION_CONTRACT.md"),
    "dry_run_json": Path("docs/N1_condition_source_20260526_activation_dry_run_report.json"),
    "dry_run_md": Path("docs/N1_CONDITION_SOURCE_20260526_ACTIVATION_DRY_RUN_REPORT.md"),
    "preflight_json": Path("docs/N1_condition_source_20260526_activation_preflight.json"),
    "preflight_md": Path("docs/N1_CONDITION_SOURCE_20260526_ACTIVATION_PREFLIGHT.md"),
    "rollback_sql": Path("sql/N1_condition_source_20260526_activation_rollback.sql"),
}


def now_iso() -> str:
    return datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat()


def sample_pass_snapshot() -> dict[str, Any]:
    return {
        "trade_date": TRADE_DATE,
        "source_batch_id": BATCH_ID,
        "upstream_daily": {
            "stock_daily": {"active_source_version": "stock_daily_20260526_v2", "row_count": 5520},
            "index_daily": {"active_source_version": "index_daily_20260526_v2", "row_count": 9},
            "board_daily": {"active_source_version": "board_daily_20260526_v2", "row_count": 428},
        },
        "stock_scope": {
            "active_stock_identity_rows": 5523,
            "official_daily_stock_rows": 5520,
            "stale_identity_inserted_rows": 0,
            "official_no_trade_inserted_rows": 0,
            "stale_identity_excluded": list(STALE_IDENTITY_EXCLUDED),
            "official_no_trade_excluded": list(OFFICIAL_NO_TRADE_EXCLUDED),
        },
        "current_target_fact_rows": {
            "stock_daily_basic": 0,
            "stock_financial": 0,
            "index_membership": 0,
            "board_membership": 0,
        },
        "target_source_version_conflicts": {
            "stock_daily_basic": 0,
            "stock_financial": 0,
            "index_membership": 0,
            "board_membership": 0,
        },
        "active_target_source_versions": [],
        "contract_batch_exists": False,
        "membership_tdx": {
            "source_available": True,
            "tdx_root": str(TDX_ROOT),
            "index_membership": {
                "raw_rows": 12841,
                "filtered_rows": 12841,
                "missing_index_identity": 0,
                "missing_stock_identity": 0,
                "duplicate_rows": 0,
                "raw_hash": "sample-index",
            },
            "board_membership": {
                "raw_rows": 56872,
                "filtered_rows": 56872,
                "missing_board_identity": 0,
                "missing_stock_identity": 0,
                "duplicate_rows": 0,
                "raw_hash": "sample-board",
            },
        },
        "event_counts": {
            "common_event_outbox": 74176,
            "common_event_inbox": 2952,
            "common_event_consumer_checkpoint": 2803,
        },
        "read_only_database_checks": True,
        "source_fetches": {
            "tushare_daily_basic": False,
            "financial_external_refresh": False,
            "tdx_local_txt_read": True,
        },
    }


def build_snapshot_from_db(
    *,
    dsn: str,
    trade_date: str = TRADE_DATE,
    tdx_root: str | Path = TDX_ROOT,
) -> dict[str, Any]:
    if trade_date != TRADE_DATE:
        raise ValueError(f"this dry-run is fixed to trade_date={TRADE_DATE}")
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            stock_daily_version = fetch_active_source_version(cur, "stock", "stock_daily", TRADE_DATE)
            index_daily_version = fetch_active_source_version(cur, "index", "index_daily", TRADE_DATE)
            board_daily_version = fetch_active_source_version(cur, "board", "board_daily", TRADE_DATE)
            stock_daily_rows = count_fact_rows(
                cur,
                "stock_daily_bar_fact",
                "trade_date",
                TRADE_DATE,
                stock_daily_version,
            )
            membership = build_membership_tdx_snapshot(cur, tdx_root=Path(tdx_root))
            snapshot = {
                "trade_date": TRADE_DATE,
                "source_batch_id": BATCH_ID,
                "upstream_daily": {
                    "stock_daily": {"active_source_version": stock_daily_version, "row_count": stock_daily_rows},
                    "index_daily": {
                        "active_source_version": index_daily_version,
                        "row_count": count_fact_rows(cur, "index_daily_bar_fact", "trade_date", TRADE_DATE, index_daily_version),
                    },
                    "board_daily": {
                        "active_source_version": board_daily_version,
                        "row_count": count_fact_rows(cur, "board_daily_bar_fact", "trade_date", TRADE_DATE, board_daily_version),
                    },
                },
                "stock_scope": build_stock_scope(cur, stock_daily_version=stock_daily_version),
                "current_target_fact_rows": fetch_current_target_fact_rows(cur),
                "target_source_version_conflicts": fetch_target_source_version_conflicts(cur),
                "active_target_source_versions": fetch_active_target_source_versions(cur),
                "contract_batch_exists": scalar_count(
                    cur,
                    "SELECT count(*) FROM common_ingest_batch WHERE batch_id = %s",
                    (BATCH_ID,),
                )
                > 0,
                "membership_tdx": membership,
                "event_counts": {
                    "common_event_outbox": scalar_count(cur, "SELECT count(*) FROM common_event_outbox"),
                    "common_event_inbox": scalar_count(cur, "SELECT count(*) FROM common_event_inbox"),
                    "common_event_consumer_checkpoint": scalar_count(cur, "SELECT count(*) FROM common_event_consumer_checkpoint"),
                },
                "read_only_database_checks": True,
                "source_fetches": {
                    "tushare_daily_basic": False,
                    "financial_external_refresh": False,
                    "tdx_local_txt_read": True,
                },
            }
    return normalize_jsonable(snapshot)


def scalar_count(cur: Any, sql: str, params: tuple[Any, ...] | None = None) -> int:
    cur.execute(sql, params)
    row = cur.fetchone()
    if row is None:
        return 0
    if isinstance(row, dict):
        return int(next(iter(row.values())))
    return int(row[0])


def fetch_active_source_version(cur: Any, data_domain: str, data_type: str, scope_key: str) -> str | None:
    cur.execute(
        """
        SELECT source_version
        FROM common_active_source_version
        WHERE data_domain = %s
          AND data_type = %s
          AND scope_key = %s
        """,
        (data_domain, data_type, scope_key),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return str(row["source_version"] if isinstance(row, dict) else row[0])


def count_fact_rows(cur: Any, table_name: str, date_column: str, trade_date: str, source_version: str | None) -> int:
    if not source_version:
        return 0
    cur.execute(
        f"SELECT count(*) FROM {table_name} WHERE {date_column} = %s AND source_version = %s",
        (trade_date, source_version),
    )
    row = cur.fetchone()
    return int(next(iter(row.values())) if isinstance(row, dict) else row[0])


def fetch_current_target_fact_rows(cur: Any) -> dict[str, int]:
    cur.execute(
        """
        SELECT
          (SELECT count(*) FROM stock_daily_basic WHERE trade_date = %s) AS stock_daily_basic,
          (SELECT count(*) FROM stock_financial_metrics_fact WHERE source_trade_date = %s) AS stock_financial,
          (SELECT count(*) FROM index_membership_fact WHERE trade_date = %s) AS index_membership,
          (SELECT count(*) FROM board_membership_fact WHERE trade_date = %s) AS board_membership
        """,
        (TRADE_DATE, TRADE_DATE, TRADE_DATE, TRADE_DATE),
    )
    return {key: int(value or 0) for key, value in dict(cur.fetchone()).items()}


def fetch_target_source_version_conflicts(cur: Any) -> dict[str, int]:
    specs = {
        "stock_daily_basic": ("stock_daily_basic", "trade_date"),
        "stock_financial": ("stock_financial_metrics_fact", "source_trade_date"),
        "index_membership": ("index_membership_fact", "trade_date"),
        "board_membership": ("board_membership_fact", "trade_date"),
    }
    conflicts: dict[str, int] = {}
    for data_type, (table_name, date_column) in specs.items():
        conflicts[data_type] = scalar_count(
            cur,
            f"SELECT count(*) FROM {table_name} WHERE {date_column} = %s AND source_version = %s",
            (TRADE_DATE, SOURCE_VERSIONS[data_type]),
        )
    return conflicts


def fetch_active_target_source_versions(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT data_domain, data_type, scope_key, source_version, source_batch_id, previous_source_version
        FROM common_active_source_version
        WHERE (
            data_domain = 'stock'
            AND data_type IN ('stock_daily_basic', 'stock_financial')
            AND scope_key = %s
          )
          OR (
            data_domain IN ('index', 'board')
            AND data_type IN ('index_membership', 'board_membership')
            AND scope_key = %s
          )
        ORDER BY data_domain, data_type
        """,
        (TRADE_DATE, f"TDX:{TRADE_DATE}"),
    )
    return [dict(row) for row in cur.fetchall()]


def build_stock_scope(cur: Any, *, stock_daily_version: str | None) -> dict[str, Any]:
    active_stock_identity_rows = scalar_count(cur, "SELECT count(*) FROM stock_identity WHERE status = 'active'")
    if not stock_daily_version:
        official_daily_stock_rows = 0
        stale_inserted = 0
        no_trade_inserted = 0
    else:
        official_daily_stock_rows = scalar_count(
            cur,
            """
            SELECT count(*)
            FROM stock_daily_bar_fact
            WHERE trade_date = %s
              AND source_version = %s
            """,
            (TRADE_DATE, stock_daily_version),
        )
        stale_inserted = scalar_count(
            cur,
            """
            SELECT count(*)
            FROM stock_daily_bar_fact
            WHERE trade_date = %s
              AND source_version = %s
              AND stock_identity_key = ANY(%s)
            """,
            (TRADE_DATE, stock_daily_version, list(STALE_IDENTITY_EXCLUDED)),
        )
        no_trade_inserted = scalar_count(
            cur,
            """
            SELECT count(*)
            FROM stock_daily_bar_fact
            WHERE trade_date = %s
              AND source_version = %s
              AND stock_identity_key = ANY(%s)
            """,
            (TRADE_DATE, stock_daily_version, list(OFFICIAL_NO_TRADE_EXCLUDED)),
        )
    return {
        "active_stock_identity_rows": active_stock_identity_rows,
        "official_daily_stock_rows": official_daily_stock_rows,
        "stale_identity_inserted_rows": stale_inserted,
        "official_no_trade_inserted_rows": no_trade_inserted,
        "stale_identity_excluded": list(STALE_IDENTITY_EXCLUDED),
        "official_no_trade_excluded": list(OFFICIAL_NO_TRADE_EXCLUDED),
    }


def build_membership_tdx_snapshot(cur: Any, *, tdx_root: Path) -> dict[str, Any]:
    try:
        source = TDXLocalTxtSource(tdx_root)
        raw_index_rows = list(source.fetch_index_membership_rows())
        raw_board_rows = list(source.fetch_board_membership_rows())
    except Exception as exc:  # pragma: no cover - exercised by integration environment
        return {
            "source_available": False,
            "tdx_root": str(tdx_root),
            "error": str(exc),
            "index_membership": empty_membership_summary(),
            "board_membership": empty_membership_summary(),
        }

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
    return {
        "source_available": True,
        "tdx_root": str(tdx_root),
        "index_membership": summarize_index_membership(raw_index_rows, index_rows, filtered_index, stock_keys, index_keys),
        "board_membership": summarize_board_membership(raw_board_rows, board_rows, filtered_board, stock_keys, board_keys),
    }


def fetch_key_set(cur: Any, sql: str) -> set[str]:
    cur.execute(sql)
    return {str(next(iter(dict(row).values()))) if isinstance(row, dict) else str(row[0]) for row in cur.fetchall()}


def empty_membership_summary() -> dict[str, Any]:
    return {
        "raw_rows": 0,
        "filtered_rows": 0,
        "missing_stock_identity": 0,
        "duplicate_rows": 0,
        "raw_hash": None,
    }


def summarize_index_membership(
    raw_rows: list[Mapping[str, Any]],
    normalized_rows: list[Mapping[str, Any]],
    filtered_rows: list[Mapping[str, Any]],
    stock_keys: set[str],
    index_keys: set[str],
) -> dict[str, Any]:
    unique_keys = {(row["trade_date"], row["index_identity_key"], row["stock_identity_key"]) for row in filtered_rows}
    return {
        "raw_rows": len(raw_rows),
        "filtered_rows": len(filtered_rows),
        "missing_index_identity": len({row["index_identity_key"] for row in normalized_rows} - index_keys),
        "missing_stock_identity": len({row["stock_identity_key"] for row in normalized_rows} - stock_keys),
        "duplicate_rows": len(filtered_rows) - len(unique_keys),
        "raw_hash": stable_raw_hash(raw_rows),
    }


def summarize_board_membership(
    raw_rows: list[Mapping[str, Any]],
    normalized_rows: list[Mapping[str, Any]],
    filtered_rows: list[Mapping[str, Any]],
    stock_keys: set[str],
    board_keys: set[str],
) -> dict[str, Any]:
    unique_keys = {(row["trade_date"], row["board_identity_key"], row["stock_identity_key"]) for row in filtered_rows}
    return {
        "raw_rows": len(raw_rows),
        "filtered_rows": len(filtered_rows),
        "missing_board_identity": len({row["board_identity_key"] for row in normalized_rows} - board_keys),
        "missing_stock_identity": len({row["stock_identity_key"] for row in normalized_rows} - stock_keys),
        "duplicate_rows": len(filtered_rows) - len(unique_keys),
        "raw_hash": stable_raw_hash(raw_rows),
    }


def build_expected_rows(snapshot: Mapping[str, Any]) -> dict[str, int]:
    stock_scope = snapshot.get("stock_scope") or {}
    membership = snapshot.get("membership_tdx") or {}
    index_membership = membership.get("index_membership") or {}
    board_membership = membership.get("board_membership") or {}
    stock_rows = int(stock_scope.get("official_daily_stock_rows") or 0)
    expected = {
        "stock_daily_basic": stock_rows,
        "stock_financial": stock_rows,
        "index_membership": int(index_membership.get("filtered_rows") or 0),
        "board_membership": int(board_membership.get("filtered_rows") or 0),
    }
    expected["total"] = sum(expected.values())
    return expected


def build_quality_items(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    expected = build_expected_rows(snapshot)
    stock_scope = snapshot.get("stock_scope") or {}
    current_rows = snapshot.get("current_target_fact_rows") or {}
    conflicts = snapshot.get("target_source_version_conflicts") or {}
    membership = snapshot.get("membership_tdx") or {}
    index_membership = membership.get("index_membership") or {}
    board_membership = membership.get("board_membership") or {}
    quality = [
        quality_item("upstream_stock_daily_active", "P0", passed=expected["stock_daily_basic"] > 0, expected="active stock_daily rows > 0", actual=expected["stock_daily_basic"]),
        quality_item("stock_daily_basic_expected_scope", "P0", passed=expected["stock_daily_basic"] == expected["stock_financial"] and expected["stock_daily_basic"] > 0, expected="stock_daily_basic aligns to N2 stock universe", actual=expected["stock_daily_basic"]),
        quality_item("stale_identity_not_required", "P0", passed=int(stock_scope.get("stale_identity_inserted_rows") or 0) == 0, expected="stock:SZ:300114 absent from expected fact scope", actual=stock_scope.get("stale_identity_inserted_rows")),
        quality_item("official_no_trade_not_required_as_bar", "P0", passed=int(stock_scope.get("official_no_trade_inserted_rows") or 0) == 0, expected="BJ no-trade identities excluded from expected fact rows", actual=stock_scope.get("official_no_trade_inserted_rows")),
        quality_item("index_membership_local_tdx_available", "P0", passed=bool(membership.get("source_available")) and expected["index_membership"] > 0, expected="local TDX index membership rows > 0", actual=expected["index_membership"]),
        quality_item("board_membership_local_tdx_available", "P0", passed=bool(membership.get("source_available")) and expected["board_membership"] > 0, expected="local TDX board membership rows > 0", actual=expected["board_membership"]),
        quality_item("index_membership_unique_key", "P0", passed=int(index_membership.get("duplicate_rows") or 0) == 0, expected="0 duplicates", actual=index_membership.get("duplicate_rows")),
        quality_item("board_membership_unique_key", "P0", passed=int(board_membership.get("duplicate_rows") or 0) == 0, expected="0 duplicates", actual=board_membership.get("duplicate_rows")),
        quality_item("target_fact_already_exists", "P0", passed=sum(int(value or 0) for value in current_rows.values()) == 0, expected="0 existing 20260526 target fact rows", actual=current_rows),
        quality_item("target_source_version_conflict", "P0", passed=sum(int(value or 0) for value in conflicts.values()) == 0, expected="0 target source_version conflicts", actual=conflicts),
        quality_item("active_source_version_conflict", "P0", passed=not snapshot.get("active_target_source_versions"), expected="0 target active source rows", actual=len(snapshot.get("active_target_source_versions") or [])),
        quality_item("condition_source_batch_conflict", "P0", passed=not bool(snapshot.get("contract_batch_exists")), expected="batch absent", actual=bool(snapshot.get("contract_batch_exists"))),
        quality_item("rollback_sql_scope_available", "P0", passed=True, expected="delete by batch/source_version/trade_date and restore/delete active", actual="available"),
        quality_item("forbidden_scope_excluded", "P0", passed=True, expected="no daily bar, no Parquet, no outbox, no N2-N6", actual="excluded"),
    ]
    if expected["index_membership"] != EXPECTED_REFERENCE_ROWS["index_membership"]:
        quality.append(
            quality_item(
                "index_membership_row_count_changed_from_recent_active",
                "P1",
                passed=False,
                expected=EXPECTED_REFERENCE_ROWS["index_membership"],
                actual=expected["index_membership"],
            )
        )
    if expected["board_membership"] != EXPECTED_REFERENCE_ROWS["board_membership"]:
        quality.append(
            quality_item(
                "board_membership_row_count_changed_from_recent_active",
                "P1",
                passed=False,
                expected=EXPECTED_REFERENCE_ROWS["board_membership"],
                actual=expected["board_membership"],
            )
        )
    filtered_identity_issues = {
        "index_missing_index_identity": int(index_membership.get("missing_index_identity") or 0),
        "index_missing_stock_identity": int(index_membership.get("missing_stock_identity") or 0),
        "board_missing_board_identity": int(board_membership.get("missing_board_identity") or 0),
        "board_missing_stock_identity": int(board_membership.get("missing_stock_identity") or 0),
    }
    filtered_count = sum(filtered_identity_issues.values())
    if filtered_count:
        quality.append(
            quality_item(
                "membership_unresolved_source_rows_filtered",
                "P2",
                passed=False,
                expected="0 unresolved raw membership identities",
                actual=filtered_count,
                details=filtered_identity_issues,
            )
        )
    return quality


def quality_item(
    gate_name: str,
    severity: str,
    *,
    passed: bool,
    expected: Any,
    actual: Any,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "gate_name": gate_name,
        "severity": severity,
        "status": "passed" if passed else ("failed" if severity == "P0" else "warning"),
        "expected_value": str(expected),
        "actual_value": str(actual),
        "details": normalize_jsonable(dict(details or {})),
    }


def summarize_quality(items: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "p0_count": sum(1 for item in items if item["severity"] == "P0" and item["status"] != "passed"),
        "p1_count": sum(1 for item in items if item["severity"] == "P1" and item["status"] != "passed"),
        "p2_count": sum(1 for item in items if item["severity"] == "P2" and item["status"] != "passed"),
    }


def build_blockers(quality_items: list[Mapping[str, Any]]) -> list[str]:
    return [str(item["gate_name"]) for item in quality_items if item["severity"] == "P0" and item["status"] != "passed"]


def build_dry_run_report(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    quality_items = build_quality_items(snapshot)
    quality = summarize_quality(quality_items)
    expected = build_expected_rows(snapshot)
    blockers = build_blockers(quality_items)
    return normalize_jsonable(
        {
            "stage": "N1 condition source activation 20260526 dry-run",
            "layer_role": "N1_ingestion",
            "result": "DRY_RUN_BLOCKED" if blockers else "DRY_RUN_PASS",
            "blocked": bool(blockers),
            "blockers": blockers,
            "trade_date": TRADE_DATE,
            "source_batch_id": BATCH_ID,
            "source_versions": dict(SOURCE_VERSIONS),
            "active_scopes": dict(ACTIVE_SCOPES),
            "expected_rows": expected,
            "current_target_fact_rows": snapshot.get("current_target_fact_rows") or {},
            "active_target_source_versions": snapshot.get("active_target_source_versions") or [],
            "source_plan": build_source_plan(),
            "stock_scope_policy": build_stock_scope_policy(snapshot),
            "membership_tdx": snapshot.get("membership_tdx") or {},
            "quality": quality,
            "quality_items": quality_items,
            "side_effects": no_side_effects(),
            "rollback_sql_path": str(DEFAULT_PATHS["rollback_sql"]),
            "generated_at": now_iso(),
        }
    )


def build_stock_scope_policy(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    stock_scope = snapshot.get("stock_scope") or {}
    return {
        "expected_stock_rows": int(stock_scope.get("official_daily_stock_rows") or 0),
        "active_stock_identity_rows": int(stock_scope.get("active_stock_identity_rows") or 0),
        "basis": "active stock_daily official v2 fact scope for 20260526",
        "stale_identity_excluded": list(stock_scope.get("stale_identity_excluded") or STALE_IDENTITY_EXCLUDED),
        "official_no_trade_excluded": list(stock_scope.get("official_no_trade_excluded") or OFFICIAL_NO_TRADE_EXCLUDED),
        "requires_no_trade_bj_daily_basic_rows": False,
        "requires_stale_300114_rows": False,
    }


def build_source_plan() -> dict[str, Any]:
    return {
        "stock_daily_basic": {
            "strategy": "refresh",
            "source": "Tushare daily_basic",
            "execute_fetch_required": True,
            "dry_run_fetch_performed": False,
            "expected_scope": "20260526 active official stock_daily fact rows; excludes stale 300114 and official no-trade BJ rows",
        },
        "stock_financial": {
            "strategy": "refresh_asof_snapshot",
            "source": "latest available financial report announcement_date <= 20260526; TDX/Mootdx preferred; Tushare fallback; stock_daily_basic for market cap/PE",
            "execute_fetch_required": True,
            "dry_run_fetch_performed": False,
            "expected_scope": "same stock universe as stock_daily_basic and active official stock_daily fact rows",
        },
        "index_membership": {
            "strategy": "refresh_materialized_snapshot",
            "source": "/Volumes/MacRaid/tdxdata/tdx/指数板块.txt",
            "execute_fetch_required": False,
            "dry_run_fetch_performed": True,
            "active_scope": ACTIVE_SCOPES["index_membership"],
        },
        "board_membership": {
            "strategy": "refresh_materialized_snapshot",
            "source": "/Volumes/MacRaid/tdxdata/tdx/地区板块.txt + 概念板块.txt + 行业板块.txt",
            "execute_fetch_required": False,
            "dry_run_fetch_performed": True,
            "active_scope": ACTIVE_SCOPES["board_membership"],
        },
    }


def build_contract(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    quality_items = build_quality_items(snapshot)
    quality = summarize_quality(quality_items)
    return normalize_jsonable(
        {
            "stage": "N1 condition source activation 20260526 execute contract",
            "layer_role": "N1_ingestion",
            "result": "BLOCKED" if quality["p0_count"] else "DESIGN_PASS",
            "trade_date": TRADE_DATE,
            "source_batch_id": BATCH_ID,
            "source_versions": dict(SOURCE_VERSIONS),
            "active_scopes": dict(ACTIVE_SCOPES),
            "expected_rows": build_expected_rows(snapshot),
            "source_strategy": build_source_plan(),
            "future_write_scope": {
                "allowed_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
                "forbidden_scope": list(FORBIDDEN_SCOPE),
                "writes_postgres": True,
                "writes_parquet": False,
                "writes_outbox": False,
                "enters_n2_n3_n4_n5_n6": False,
                "worker_started": False,
            },
            "execute_requirements": {
                "double_confirmation": ["--execute", "--user-confirmed"],
                "postgres_commit_gate": "--postgres-commit-enabled",
                "single_transaction": True,
                "p0_must_equal_zero": True,
                "block_on_existing_fact_or_active": True,
                "parquet_write": False,
            },
            "quality_policy": {
                "stock_daily_basic": "P0 if expected scope mismatches active official stock_daily rows or stale/no-trade exclusions leak into required rows.",
                "stock_financial": "P0 if as-of snapshot row_count does not equal active official stock_daily rows.",
                "index_membership": "P0 if local TDX snapshot cannot produce non-empty mapped rows; row-count drift from 20260522 is P1 review.",
                "board_membership": "P0 if local TDX snapshot cannot produce non-empty mapped rows; row-count drift from 20260522 is P1 review.",
            },
            "rollback": {
                "rollback_safe": True,
                "rollback_sql_path": str(DEFAULT_PATHS["rollback_sql"]),
                "strategy": "delete by source_batch_id/source_version/trade_date and restore or delete active source rows scoped to 20260526.",
            },
            "implementation_status": {
                "execute_runner_implemented": True,
                "source_row_builder": True,
                "source_bundle_validation": True,
                "postgres_commit_transaction": True,
                "cli_execute_pipeline_wired": True,
                "execute_authorized": False,
                "final_execute_gate_allowed": quality["p0_count"] == 0,
            },
            "quality": quality,
            "quality_items": quality_items,
            "generated_at": now_iso(),
        }
    )


def build_preflight(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    quality_items = build_quality_items(snapshot)
    quality = summarize_quality(quality_items)
    blockers = build_blockers(quality_items)
    return normalize_jsonable(
        {
            "stage": "N1 condition source activation 20260526 preflight",
            "layer_role": "N1_ingestion",
            "result": "PREFLIGHT_BLOCKED" if blockers else "PREFLIGHT_PASS",
            "blockers": blockers,
            "trade_date": TRADE_DATE,
            "source_batch_id": BATCH_ID,
            "source_versions": dict(SOURCE_VERSIONS),
            "expected_rows": build_expected_rows(snapshot),
            "baseline": {
                "current_target_fact_rows": snapshot.get("current_target_fact_rows") or {},
                "active_target_source_versions": snapshot.get("active_target_source_versions") or [],
                "target_source_version_conflicts": snapshot.get("target_source_version_conflicts") or {},
                "contract_batch_exists": bool(snapshot.get("contract_batch_exists")),
                "event_counts": snapshot.get("event_counts") or {},
            },
            "quality": quality,
            "quality_items": quality_items,
            "runner_readiness": "ready_for_final_gate" if not blockers else "blocked",
            "execute_authorized": False,
            "final_execute_gate_allowed": not bool(blockers),
            "execute_runner_implementation_allowed": False,
            "execute_runner_implemented": True,
            "postgres_commit_implemented": True,
            "side_effects": no_side_effects(),
            "rollback_sql_path": str(DEFAULT_PATHS["rollback_sql"]),
            "generated_at": now_iso(),
        }
    )


def no_side_effects() -> dict[str, bool]:
    return {
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


def build_rollback_sql() -> str:
    return f"""-- N1 condition source activation 20260526 rollback draft.
-- Scope: condition source activation batch {BATCH_ID}.
-- This rollback does not touch official daily bar facts, calendar patch,
-- Parquet, outbox/inbox/checkpoint, old system, or any N2-N6 table.

BEGIN;

DO $$
DECLARE
  missing_previous_batch_count integer;
BEGIN
  SELECT COUNT(*)
  INTO missing_previous_batch_count
  FROM common_active_source_version a
  WHERE a.source_batch_id = '{BATCH_ID}'
    AND (
      (a.data_domain = 'stock' AND a.data_type IN ('stock_daily_basic', 'stock_financial') AND a.scope_key = '20260526')
      OR (a.data_domain = 'index' AND a.data_type = 'index_membership' AND a.scope_key = 'TDX:20260526')
      OR (a.data_domain = 'board' AND a.data_type = 'board_membership' AND a.scope_key = 'TDX:20260526')
    )
    AND a.previous_source_version IS NOT NULL
    AND NOT EXISTS (
      SELECT 1
      FROM common_ingest_batch b
      WHERE b.data_domain = a.data_domain
        AND b.data_type = a.data_type
        AND b.source_version = a.previous_source_version
        AND b.status = 'passed'
    );

  IF missing_previous_batch_count > 0 THEN
    RAISE EXCEPTION 'Refusing condition source 20260526 rollback: previous_source_version cannot be resolved';
  END IF;
END $$;

UPDATE common_active_source_version a
SET source_version = a.previous_source_version,
    source_batch_id = (
      SELECT b.batch_id
      FROM common_ingest_batch b
      WHERE b.data_domain = a.data_domain
        AND b.data_type = a.data_type
        AND b.source_version = a.previous_source_version
        AND b.status = 'passed'
      ORDER BY b.finished_at DESC NULLS LAST, b.started_at DESC, b.batch_id DESC
      LIMIT 1
    ),
    previous_source_version = NULL,
    activated_at = now(),
    activated_by = 'rollback:n1_condition_source_activation_20260526'
WHERE a.source_batch_id = '{BATCH_ID}'
  AND a.previous_source_version IS NOT NULL
  AND (
    (a.data_domain = 'stock' AND a.data_type IN ('stock_daily_basic', 'stock_financial') AND a.scope_key = '20260526')
    OR (a.data_domain = 'index' AND a.data_type = 'index_membership' AND a.scope_key = 'TDX:20260526')
    OR (a.data_domain = 'board' AND a.data_type = 'board_membership' AND a.scope_key = 'TDX:20260526')
  );

DELETE FROM common_active_source_version
WHERE source_batch_id = '{BATCH_ID}'
  AND previous_source_version IS NULL
  AND (
    (data_domain = 'stock' AND data_type IN ('stock_daily_basic', 'stock_financial') AND scope_key = '20260526')
    OR (data_domain = 'index' AND data_type = 'index_membership' AND scope_key = 'TDX:20260526')
    OR (data_domain = 'board' AND data_type = 'board_membership' AND scope_key = 'TDX:20260526')
  );

DELETE FROM stock_daily_basic
WHERE trade_date = '20260526'
  AND source_batch_id = '{BATCH_ID}'
  AND source_version = '{SOURCE_VERSIONS["stock_daily_basic"]}';

DELETE FROM stock_financial_metrics_fact
WHERE source_trade_date = '20260526'
  AND source_batch_id = '{BATCH_ID}'
  AND source_version = '{SOURCE_VERSIONS["stock_financial"]}';

DELETE FROM index_membership_fact
WHERE trade_date = '20260526'
  AND source_batch_id = '{BATCH_ID}'
  AND source_version = '{SOURCE_VERSIONS["index_membership"]}';

DELETE FROM board_membership_fact
WHERE trade_date = '20260526'
  AND source_batch_id = '{BATCH_ID}'
  AND source_version = '{SOURCE_VERSIONS["board_membership"]}';

DELETE FROM common_quality_gate_result
WHERE source_batch_id = '{BATCH_ID}'
   OR source_version IN (
     '{BATCH_ID}',
     '{SOURCE_VERSIONS["stock_daily_basic"]}',
     '{SOURCE_VERSIONS["stock_financial"]}',
     '{SOURCE_VERSIONS["index_membership"]}',
     '{SOURCE_VERSIONS["board_membership"]}'
   );

DELETE FROM common_ingest_batch
WHERE batch_id = '{BATCH_ID}'
   OR source_version = '{BATCH_ID}';

COMMIT;
"""


def write_artifacts(snapshot: Mapping[str, Any], *, paths: Mapping[str, Path] | None = None) -> dict[str, str]:
    paths = dict(paths or DEFAULT_PATHS)
    contract = build_contract(snapshot)
    dry_run = build_dry_run_report(snapshot)
    preflight = build_preflight(snapshot)
    rollback_sql = build_rollback_sql()
    payloads = {
        "contract_json": json.dumps(contract, ensure_ascii=False, indent=2) + "\n",
        "dry_run_json": json.dumps(dry_run, ensure_ascii=False, indent=2) + "\n",
        "preflight_json": json.dumps(preflight, ensure_ascii=False, indent=2) + "\n",
        "contract_md": render_contract_md(contract),
        "dry_run_md": render_dry_run_md(dry_run),
        "preflight_md": render_preflight_md(preflight),
        "rollback_sql": rollback_sql,
    }
    written: dict[str, str] = {}
    for key, text in payloads.items():
        path = paths[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written[key] = str(path)
    return written


def render_contract_md(contract: Mapping[str, Any]) -> str:
    return f"""# N1 Condition Source 20260526 Activation Contract

Result: `{contract["result"]}`

- layer_role: `N1_ingestion`
- trade_date: `{TRADE_DATE}`
- source_batch_id: `{BATCH_ID}`
- source_versions: `{json.dumps(SOURCE_VERSIONS, ensure_ascii=False)}`
- active_scopes: `{json.dumps(ACTIVE_SCOPES, ensure_ascii=False)}`
- future write scope: `{", ".join(ALLOWED_FUTURE_WRITE_TABLES)}`
- forbidden: daily bar fact, Parquet, outbox/inbox/checkpoint, N2-N6, worker, old system, real trading

Expected rows:

```json
{json.dumps(contract["expected_rows"], ensure_ascii=False, indent=2)}
```

Rollback SQL: `{DEFAULT_PATHS["rollback_sql"]}`
"""


def render_dry_run_md(report: Mapping[str, Any]) -> str:
    return f"""# N1 Condition Source 20260526 Activation Dry-Run Report

Result: `{report["result"]}`

- blocked: `{report["blocked"]}`
- blockers: `{json.dumps(report["blockers"], ensure_ascii=False)}`
- source_batch_id: `{BATCH_ID}`
- P0/P1/P2: `{report["quality"]["p0_count"]}/{report["quality"]["p1_count"]}/{report["quality"]["p2_count"]}`

Expected rows:

```json
{json.dumps(report["expected_rows"], ensure_ascii=False, indent=2)}
```

Stock scope policy:

```json
{json.dumps(report["stock_scope_policy"], ensure_ascii=False, indent=2)}
```

Side effects:

```json
{json.dumps(report["side_effects"], ensure_ascii=False, indent=2)}
```
"""


def render_preflight_md(preflight: Mapping[str, Any]) -> str:
    return f"""# N1 Condition Source 20260526 Activation Preflight

Result: `{preflight["result"]}`

- runner_readiness: `{preflight["runner_readiness"]}`
- execute_runner_implemented: `{preflight["execute_runner_implemented"]}`
- postgres_commit_implemented: `{preflight["postgres_commit_implemented"]}`
- execute_authorized: `{preflight["execute_authorized"]}`
- final_execute_gate_allowed: `{preflight["final_execute_gate_allowed"]}`
- execute_runner_implementation_allowed: `{preflight["execute_runner_implementation_allowed"]}`
- P0/P1/P2: `{preflight["quality"]["p0_count"]}/{preflight["quality"]["p1_count"]}/{preflight["quality"]["p2_count"]}`

Rollback SQL: `{DEFAULT_PATHS["rollback_sql"]}`
"""


def normalize_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): normalize_jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [normalize_jsonable(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
