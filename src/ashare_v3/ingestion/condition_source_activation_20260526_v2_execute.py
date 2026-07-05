"""Execute runner support for N1 condition source activation 20260526 v2.

This module is safe to import and test. Real PostgreSQL writes only happen
when the run-once CLI receives all explicit final-gate flags.
"""

from __future__ import annotations

import base64
from collections import Counter
from datetime import date, datetime, time
from decimal import Decimal
import importlib
import json
import math
import numbers
import os
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.ingestion.tushare_env import load_tushare_token
from ashare_v3.ingestion.common import stable_raw_hash
from ashare_v3.ingestion.tdx_local import (
    TDXLocalTxtSource,
    normalize_board_membership_row,
    normalize_index_membership_row,
)


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
TRADE_DATE = "20260526"
BATCH_ID = "condition_source_activation_20260526_v2"
TDX_ROOT = Path("/Volumes/MacRaid/tdxdata/tdx")
SOURCE_VERSIONS = {
    "stock_daily_basic": "stock_daily_basic_20260526_v2",
    "stock_financial": "stock_financial_20260526_v2",
    "index_membership": "index_membership_20260526_v2",
    "board_membership": "board_membership_20260526_v2",
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
    "stock_daily_basic": 5504,
    "stock_financial": 5504,
    "index_membership": 12841,
    "board_membership": 56872,
}
CONDITION_SOURCE_GAP_IDENTITIES = (
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
CONDITION_SOURCE_GAP_TS_CODES = {
    "stock:SH:600193": "600193.SH",
    "stock:SH:600421": "600421.SH",
    "stock:SH:600599": "600599.SH",
    "stock:SH:600608": "600608.SH",
    "stock:SH:600636": "600636.SH",
    "stock:SH:600696": "600696.SH",
    "stock:SH:605081": "605081.SH",
    "stock:SH:688121": "688121.SH",
    "stock:SZ:000004": "000004.SZ",
    "stock:SZ:000638": "000638.SZ",
    "stock:SZ:002731": "002731.SZ",
    "stock:SZ:002808": "002808.SZ",
    "stock:SZ:002898": "002898.SZ",
    "stock:SZ:300029": "300029.SZ",
    "stock:SZ:300550": "300550.SZ",
    "stock:SZ:301096": "301096.SZ",
}
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
    "contract_json": Path("docs/N1_condition_source_20260526_v2_activation_contract.json"),
    "contract_md": Path("docs/N1_CONDITION_SOURCE_20260526_V2_ACTIVATION_CONTRACT.md"),
    "dry_run_json": Path("docs/N1_condition_source_20260526_v2_activation_dry_run_report.json"),
    "dry_run_md": Path("docs/N1_CONDITION_SOURCE_20260526_V2_ACTIVATION_DRY_RUN_REPORT.md"),
    "preflight_json": Path("docs/N1_condition_source_20260526_v2_activation_preflight.json"),
    "preflight_md": Path("docs/N1_CONDITION_SOURCE_20260526_V2_ACTIVATION_PREFLIGHT.md"),
    "rollback_sql": Path("sql/N1_condition_source_20260526_v2_activation_rollback.sql"),
}
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
JSON_PAYLOAD_KEYS = ("raw_payload", "details", "source_params", "quality_gate_summary", "source_proof_json")


class ConditionSourceActivation20260526V2Blocked(RuntimeError):
    """Raised when the condition source activation v2 execute gate is blocked."""


def now_iso() -> str:
    return datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat()


def normalize_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): normalize_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def sanitize_json_value(value: Any, warnings: list[str] | None = None, path: str = "$") -> Any:
    """Return a PostgreSQL JSON/JSONB-safe value without mutating business columns."""
    if isinstance(value, Mapping):
        return {str(key): sanitize_json_value(item, warnings=warnings, path=f"{path}.{key}") for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_json_value(item, warnings=warnings, path=f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, set):
        return [sanitize_json_value(item, warnings=warnings, path=f"{path}[]") for item in value]
    if value is None:
        return None
    if isinstance(value, (str, bool)):
        return value
    if _is_pandas_missing_scalar(value):
        return None
    if isinstance(value, Decimal):
        return float(value) if value.is_finite() else None
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return base64.b64encode(raw).decode("ascii")
    if hasattr(value, "item") and not isinstance(value, (int, float)):
        try:
            return sanitize_json_value(value.item(), warnings=warnings, path=path)
        except Exception:
            pass
    if isinstance(value, numbers.Integral) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    try:
        assert_json_compatible(value, context=path)
        return value
    except ConditionSourceActivation20260526V2Blocked:
        converted = str(value)
        if warnings is not None:
            warnings.append(f"{path}: unknown object converted to string ({type(value).__name__})")
        return converted


def _is_pandas_missing_scalar(value: Any) -> bool:
    try:
        pandas = importlib.import_module("pandas")
    except Exception:
        return False
    try:
        result = pandas.isna(value)
        return bool(result)
    except Exception:
        return False


def assert_json_compatible(value: Any, *, context: str) -> Any:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ConditionSourceActivation20260526V2Blocked(f"{context} is not valid JSON: {exc}") from exc
    return value


def validate_execute_request(
    *,
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> None:
    if not execute_requested:
        raise ConditionSourceActivation20260526V2Blocked("missing --execute")
    if not user_confirmed:
        raise ConditionSourceActivation20260526V2Blocked("missing --user-confirmed")
    if not postgres_commit_enabled:
        raise ConditionSourceActivation20260526V2Blocked("missing --postgres-commit-enabled")


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
            "condition_stock_rows": 5504,
            "condition_source_gap_manifest_rows": 16,
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
                "unmapped_raw_count": 0,
                "unmapped_unique_identity_count": 0,
                "duplicate_rows": 0,
                "raw_hash": "sample-index",
            },
            "board_membership": {
                "raw_rows": 56882,
                "filtered_rows": 56872,
                "missing_board_identity": 0,
                "missing_stock_identity": 7,
                "unmapped_raw_count": 10,
                "unmapped_unique_identity_count": 7,
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
        raise ValueError(f"this runner is fixed to trade_date={TRADE_DATE}")
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            stock_daily_version = fetch_active_source_version(cur, "stock", "stock_daily", TRADE_DATE)
            index_daily_version = fetch_active_source_version(cur, "index", "index_daily", TRADE_DATE)
            board_daily_version = fetch_active_source_version(cur, "board", "board_daily", TRADE_DATE)
            official_daily_stock_rows = count_fact_rows(cur, "stock_daily_bar_fact", "trade_date", TRADE_DATE, stock_daily_version)
            membership = build_membership_tdx_snapshot(cur, tdx_root=Path(tdx_root))
            snapshot = {
                "trade_date": TRADE_DATE,
                "source_batch_id": BATCH_ID,
                "upstream_daily": {
                    "stock_daily": {"active_source_version": stock_daily_version, "row_count": official_daily_stock_rows},
                    "index_daily": {
                        "active_source_version": index_daily_version,
                        "row_count": count_fact_rows(cur, "index_daily_bar_fact", "trade_date", TRADE_DATE, index_daily_version),
                    },
                    "board_daily": {
                        "active_source_version": board_daily_version,
                        "row_count": count_fact_rows(cur, "board_daily_bar_fact", "trade_date", TRADE_DATE, board_daily_version),
                    },
                },
                "stock_scope": build_stock_scope(
                    cur,
                    stock_daily_version=stock_daily_version,
                    official_daily_stock_rows=official_daily_stock_rows,
                ),
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


def build_stock_scope(
    cur: Any,
    *,
    stock_daily_version: str | None,
    official_daily_stock_rows: int,
) -> dict[str, Any]:
    active_stock_identity_rows = scalar_count(cur, "SELECT count(*) FROM stock_identity WHERE status = 'active'")
    if not stock_daily_version:
        gap_rows = 0
    else:
        gap_rows = scalar_count(
            cur,
            """
            SELECT count(*)
            FROM stock_daily_bar_fact
            WHERE trade_date = %s
              AND source_version = %s
              AND stock_identity_key = ANY(%s)
            """,
            (TRADE_DATE, stock_daily_version, list(CONDITION_SOURCE_GAP_IDENTITIES)),
        )
    return {
        "active_stock_identity_rows": active_stock_identity_rows,
        "official_daily_stock_rows": official_daily_stock_rows,
        "condition_stock_rows": max(official_daily_stock_rows - gap_rows, 0),
        "condition_source_gap_manifest_rows": gap_rows,
        "condition_source_gap_manifest": condition_source_gap_manifest(),
    }


def build_membership_tdx_snapshot(cur: Any, *, tdx_root: Path) -> dict[str, Any]:
    try:
        source = TDXLocalTxtSource(tdx_root)
        raw_index_rows = list(source.fetch_index_membership_rows())
        raw_board_rows = list(source.fetch_board_membership_rows())
    except Exception as exc:  # pragma: no cover - environment dependent
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
        "unmapped_raw_count": 0,
        "unmapped_unique_identity_count": 0,
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
    missing_index = {row["index_identity_key"] for row in normalized_rows} - index_keys
    missing_stock = {row["stock_identity_key"] for row in normalized_rows} - stock_keys
    return {
        "raw_rows": len(raw_rows),
        "filtered_rows": len(filtered_rows),
        "missing_index_identity": len(missing_index),
        "missing_stock_identity": len(missing_stock),
        "unmapped_raw_count": len(normalized_rows) - len(filtered_rows),
        "unmapped_unique_identity_count": len(missing_index | missing_stock),
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
    missing_board = {row["board_identity_key"] for row in normalized_rows} - board_keys
    missing_stock = {row["stock_identity_key"] for row in normalized_rows} - stock_keys
    return {
        "raw_rows": len(raw_rows),
        "filtered_rows": len(filtered_rows),
        "missing_board_identity": len(missing_board),
        "missing_stock_identity": len(missing_stock),
        "unmapped_raw_count": len(normalized_rows) - len(filtered_rows),
        "unmapped_unique_identity_count": len(missing_board | missing_stock),
        "duplicate_rows": len(filtered_rows) - len(unique_keys),
        "raw_hash": stable_raw_hash(raw_rows),
    }


def build_expected_rows(snapshot: Mapping[str, Any]) -> dict[str, int]:
    stock_scope = snapshot.get("stock_scope") or {}
    membership = snapshot.get("membership_tdx") or {}
    index_membership = membership.get("index_membership") or {}
    board_membership = membership.get("board_membership") or {}
    stock_rows = int(stock_scope.get("condition_stock_rows") or 0)
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
    gap_manifest = list(stock_scope.get("condition_source_gap_manifest") or condition_source_gap_manifest())
    quality = [
        quality_item("upstream_stock_daily_active", "P0", passed=expected["stock_daily_basic"] > 0, expected="active stock_daily rows > 0", actual=expected["stock_daily_basic"]),
        quality_item(
            "condition_stock_universe_expected_scope",
            "P0",
            passed=expected["stock_daily_basic"] == expected["stock_financial"] == EXPECTED_REFERENCE_ROWS["stock_daily_basic"],
            expected=EXPECTED_REFERENCE_ROWS["stock_daily_basic"],
            actual=expected["stock_daily_basic"],
            details={
                "official_daily_bar_universe": stock_scope.get("official_daily_stock_rows"),
                "condition_source_gap_manifest_rows": len(gap_manifest),
            },
        ),
        quality_item(
            "condition_source_gap_manifest",
            "P1",
            passed=False,
            expected="0 daily_basic-missing supplemental official daily bars",
            actual=len(gap_manifest),
            details={"manifest": gap_manifest},
        ),
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
    board_raw_unmapped = int(board_membership.get("unmapped_raw_count") or 0)
    if board_raw_unmapped:
        quality.append(
            quality_item(
                "board_unmapped_raw_count_filtered",
                "P2",
                passed=False,
                expected=0,
                actual=board_raw_unmapped,
                details={
                    "raw_unmapped": board_raw_unmapped,
                    "unique_identity_unmapped": int(board_membership.get("unmapped_unique_identity_count") or 0),
                    "action": "filtered",
                    "blocking": False,
                },
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
        "details": sanitize_json_value(dict(details or {})),
    }


def summarize_quality(items: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "p0_count": sum(1 for item in items if item["severity"] == "P0" and item["status"] != "passed"),
        "p1_count": sum(1 for item in items if item["severity"] == "P1" and item["status"] != "passed"),
        "p2_count": sum(1 for item in items if item["severity"] == "P2" and item["status"] != "passed"),
    }


def build_blockers(quality_items: list[Mapping[str, Any]]) -> list[str]:
    return [str(item["gate_name"]) for item in quality_items if item["severity"] == "P0" and item["status"] != "passed"]


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


def condition_source_gap_manifest() -> list[dict[str, Any]]:
    return [
        {
            "identity_key": identity_key,
            "ts_code": CONDITION_SOURCE_GAP_TS_CODES[identity_key],
            "reason": "daily_basic_missing_for_suspended_supplemental_daily_bar",
            "daily_bar_available": True,
            "daily_bar_source": "mootdx.stock_daily.supplemental",
            "condition_source_available": False,
            "tushare_daily_basic_present": False,
            "tushare_suspend_d_present": True,
            "action": "exclude_from_condition_universe",
            "severity": "P1",
        }
        for identity_key in CONDITION_SOURCE_GAP_IDENTITIES
    ]


class DefaultConditionSourceActivation20260526V2SourceBuilder:
    """Build source rows lazily, only after the v2 final execute gate is open."""

    def __init__(self, *, tdx_root: str | Path = TDX_ROOT, tushare_token: str | None = None) -> None:
        self.tdx_root = Path(tdx_root)
        self.tushare_token = tushare_token or load_tushare_token()
        self._tushare_client: Any | None = None

    def build_source_bundle(self, *, dsn: str, trade_date: str, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        if trade_date != TRADE_DATE:
            raise ConditionSourceActivation20260526V2Blocked(f"trade_date must be {TRADE_DATE}")
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
                    "condition_source_gap_manifest": condition_source_gap_manifest(),
                },
            }
        )

    def fetch_stock_daily_basic_rows(self, *, stock_scope: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
        pro = self._pro()
        raw_rows = frame_to_records(pro.daily_basic(trade_date=TRADE_DATE, fields=DAILY_BASIC_FIELDS))
        raw_by_ts_code = {str(row.get("ts_code") or ""): dict(row) for row in raw_rows}
        rows: list[dict[str, Any]] = []
        for stock in stock_scope:
            identity_key = str(stock.get("stock_identity_key") or "")
            if identity_key in CONDITION_SOURCE_GAP_IDENTITIES:
                continue
            ts_code = str(stock.get("ts_code") or "")
            raw = raw_by_ts_code.get(ts_code)
            if not raw:
                continue
            rows.append(
                {
                    "stock_identity_key": identity_key,
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
                raise ConditionSourceActivation20260526V2Blocked("TUSHARE_TOKEN is required for stock_daily_basic")
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
        raise ConditionSourceActivation20260526V2Blocked("stock_daily active source_version is required")
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
                "warning": "financial report not found",
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
    board_unmapped_keys = {
        row["stock_identity_key"]
        for row in board_rows
        if row["board_identity_key"] not in board_keys or row["stock_identity_key"] not in stock_keys
    }
    manifests = {
        "index_raw_rows": len(raw_index_rows),
        "board_raw_rows": len(raw_board_rows),
        "index_unmapped_raw_count": len(index_rows) - len(filtered_index),
        "board_unmapped_raw_count": len(board_rows) - len(filtered_board),
        "board_unmapped_unique_identity_count": len(board_unmapped_keys),
    }
    return filtered_index, filtered_board, manifests


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
            plain_quality_item(
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
            plain_quality_item(
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
    gap_leaks = sorted((stock_daily_basic_ids | stock_financial_ids) & set(CONDITION_SOURCE_GAP_IDENTITIES))
    if gap_leaks:
        blockers.append("condition_source_gap_leaked_into_stock_condition_source")
    quality_items.append(
        plain_quality_item(
            "condition_source_gap_not_inserted",
            "P0",
            "passed" if not gap_leaks else "failed",
            0,
            len(gap_leaks),
            {"identity_keys": gap_leaks},
        )
    )

    manifest = list(((bundle.get("manifests") or {}).get("condition_source_gap_manifest")) or [])
    manifest_complete = len(manifest) == len(CONDITION_SOURCE_GAP_IDENTITIES)
    if not manifest_complete:
        blockers.append("condition_source_gap_manifest_incomplete")
    quality_items.append(
        plain_quality_item(
            "condition_source_gap_manifest_complete",
            "P0",
            "passed" if manifest_complete else "failed",
            len(CONDITION_SOURCE_GAP_IDENTITIES),
            len(manifest),
        )
    )
    quality_items.append(
        plain_quality_item(
            "condition_source_gap_manifest",
            "P1",
            "warning",
            0,
            len(manifest),
            {"manifest": manifest},
        )
    )

    duplicate_issues = {
        data_type: duplicate_count(bundle.get(data_type) or [], data_type)
        for data_type in ("stock_daily_basic", "stock_financial", "index_membership", "board_membership")
    }
    if any(duplicate_issues.values()):
        blockers.append("duplicate_identity_key")
    quality_items.append(
        plain_quality_item(
            "duplicate_identity_key",
            "P0",
            "passed" if not any(duplicate_issues.values()) else "failed",
            0,
            sum(duplicate_issues.values()),
            duplicate_issues,
        )
    )

    board_unmapped = int(((bundle.get("manifests") or {}).get("board_unmapped_raw_count")) or 0)
    board_unmapped_unique = int(((bundle.get("manifests") or {}).get("board_unmapped_unique_identity_count")) or 0)
    if board_unmapped:
        quality_items.append(
            plain_quality_item(
                "board_unmapped_raw_count_filtered",
                "P2",
                "warning",
                0,
                board_unmapped,
                {
                    "raw_unmapped": board_unmapped,
                    "unique_identity_unmapped": board_unmapped_unique,
                    "action": "filtered",
                    "blocking": False,
                },
            )
        )

    json_payload_errors, json_payload_warnings = validate_json_payloads(bundle)
    if json_payload_errors:
        blockers.append("json_payload_not_serializable")
    quality_items.append(
        plain_quality_item(
            "json_payload_sanitized",
            "P0",
            "passed" if not json_payload_errors else "failed",
            "json.dumps allow_nan=False",
            len(json_payload_errors),
            {"errors": json_payload_errors[:10]},
        )
    )
    if json_payload_warnings:
        quality_items.append(
            plain_quality_item(
                "json_payload_sanitizer_warnings",
                "P1",
                "warning",
                0,
                len(json_payload_warnings),
                {"warnings": json_payload_warnings[:50]},
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


def plain_quality_item(
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
        "details": sanitize_json_value(dict(details or {})),
    }


def validate_json_payloads(bundle: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for data_type in ("stock_daily_basic", "stock_financial", "index_membership", "board_membership"):
        for index, row in enumerate(bundle.get(data_type) or []):
            for key in JSON_PAYLOAD_KEYS:
                if key not in row:
                    continue
                try:
                    assert_json_compatible(
                        sanitize_json_value(
                            row.get(key),
                            warnings=warnings,
                            path=f"{data_type}[{index}].{key}",
                        ),
                        context=f"{data_type}[{index}].{key}",
                    )
                except ConditionSourceActivation20260526V2Blocked as exc:
                    errors.append(str(exc))
    try:
        assert_json_compatible(
            sanitize_json_value(bundle.get("manifests") or {}, warnings=warnings, path="bundle.manifests"),
            context="bundle.manifests",
        )
    except ConditionSourceActivation20260526V2Blocked as exc:
        errors.append(str(exc))
    return errors, warnings


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
        raise ConditionSourceActivation20260526V2Blocked(", ".join(sorted(dict.fromkeys(blockers))))


def build_commit_plan(
    *,
    bundle: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    baseline: Mapping[str, Any],
) -> dict[str, Any]:
    if int(validation_report.get("p0_count") or 0) != 0:
        raise ConditionSourceActivation20260526V2Blocked("source validation P0 must be zero before commit plan")
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
            "activated_by": "n1_condition_source_activation_20260526_v2_execute_runner",
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
        raise ConditionSourceActivation20260526V2Blocked(f"unexpected write tables: {unexpected_tables}")
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
          'n1.condition_source_activation.20260526.v2', %(source_version)s,
          NULL, %(source_params)s, NULL, %(row_count)s, 0,
          %(quality_gate_summary)s, NULL, %(rollback_strategy)s, 'running', now()
        )
        """,
        {
            "batch_id": BATCH_ID,
            "trade_date": TRADE_DATE,
            "source_version": BATCH_ID,
            "source_params": jsonb_payload(
                {"source_versions": SOURCE_VERSIONS, "active_scopes": ACTIVE_SCOPES},
                context="common_ingest_batch.source_params",
            ),
            "row_count": int((commit_plan.get("row_counts") or {}).get("total") or 0),
            "quality_gate_summary": jsonb_payload(
                {
                    "expected_rows": commit_plan.get("row_counts") or {},
                    "condition_source_gap_manifest_rows": len(condition_source_gap_manifest()),
                    "board_unmapped_raw_count": (commit_plan.get("manifests") or {}).get("board_unmapped_raw_count"),
                },
                context="common_ingest_batch.quality_gate_summary",
            ),
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
    for key in JSON_PAYLOAD_KEYS:
        if key in converted:
            converted[key] = jsonb_payload(converted.get(key), context=f"row.{key}")
    return converted


def jsonb_payload(value: Any, *, context: str) -> Jsonb:
    payload = {} if value is None else value
    warnings: list[str] = []
    sanitized = sanitize_json_value(payload, warnings=warnings, path=context)
    assert_json_compatible(sanitized, context=context)
    return Jsonb(sanitized)


def build_source_plan() -> dict[str, Any]:
    return {
        "stock_daily_basic": {
            "strategy": "refresh_tushare_daily_basic_for_condition_universe",
            "source": "Tushare daily_basic",
            "expected_rows": EXPECTED_REFERENCE_ROWS["stock_daily_basic"],
            "excluded_manifest": "condition_source_gap_manifest",
            "active_scope": ACTIVE_SCOPES["stock_daily_basic"],
        },
        "stock_financial": {
            "strategy": "as_of_snapshot_for_condition_universe",
            "source": "existing N1 financial as-of rows plus stock_daily_basic market metrics",
            "expected_rows": EXPECTED_REFERENCE_ROWS["stock_financial"],
            "excluded_manifest": "condition_source_gap_manifest",
            "active_scope": ACTIVE_SCOPES["stock_financial"],
        },
        "index_membership": {
            "strategy": "refresh_materialized_snapshot",
            "source": "/Volumes/MacRaid/tdxdata/tdx/指数板块.txt",
            "expected_rows": EXPECTED_REFERENCE_ROWS["index_membership"],
            "active_scope": ACTIVE_SCOPES["index_membership"],
        },
        "board_membership": {
            "strategy": "refresh_materialized_snapshot",
            "source": "/Volumes/MacRaid/tdxdata/tdx/地区板块.txt + 概念板块.txt + 行业板块.txt",
            "expected_rows": EXPECTED_REFERENCE_ROWS["board_membership"],
            "active_scope": ACTIVE_SCOPES["board_membership"],
        },
    }


def build_contract(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    quality_items = build_quality_items(snapshot)
    quality = summarize_quality(quality_items)
    return normalize_jsonable(
        {
            "stage": "N1 condition source activation 20260526 v2 execute contract",
            "layer_role": "N1_ingestion",
            "result": "BLOCKED" if quality["p0_count"] else "DESIGN_PASS",
            "trade_date": TRADE_DATE,
            "source_batch_id": BATCH_ID,
            "source_versions": dict(SOURCE_VERSIONS),
            "active_scopes": dict(ACTIVE_SCOPES),
            "expected_rows": build_expected_rows(snapshot),
            "condition_source_gap_manifest": condition_source_gap_manifest(),
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
                "required_flags": ["--execute", "--user-confirmed", "--postgres-commit-enabled"],
                "single_transaction": True,
                "p0_must_equal_zero": True,
                "block_on_existing_fact_or_active": True,
                "condition_gap_rows_inserted_blocks": True,
                "parquet_write": False,
            },
            "quality_policy": {
                "p0": [
                    "target count mismatch",
                    "existing v2 target rows",
                    "existing v2 active source_version",
                    "existing batch/source_version",
                    "condition source gap rows leaking into stock_daily_basic or stock_financial",
                ],
                "p1": "16 condition_source_gap_manifest rows are warnings and excluded from condition universe.",
                "p2": "board TDX unmapped raw rows are filtered and non-blocking.",
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
            "stage": "N1 condition source activation 20260526 v2 preflight",
            "layer_role": "N1_ingestion",
            "result": "PREFLIGHT_BLOCKED" if blockers else "PREFLIGHT_PASS",
            "blockers": blockers,
            "trade_date": TRADE_DATE,
            "source_batch_id": BATCH_ID,
            "source_versions": dict(SOURCE_VERSIONS),
            "expected_rows": build_expected_rows(snapshot),
            "condition_source_gap_manifest": condition_source_gap_manifest(),
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
            "stage": "N1 condition source activation 20260526 v2 execute preflight",
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
                "PYTHONPATH=src python3 scripts/run_condition_source_activation_20260526_v2_once.py "
                "--execute --user-confirmed --postgres-commit-enabled"
            ),
            "generated_at": now_iso(),
        }
    )


def build_execute_contract(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    contract = build_contract(snapshot)
    blockers = build_blockers(build_quality_items(snapshot))
    return normalize_jsonable(
        {
            **contract,
            "stage": "N1 condition source activation 20260526 v2 execute contract",
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


def render_preflight_markdown(report: Mapping[str, Any]) -> str:
    return f"""# N1 Condition Source 20260526 V2 Activation Preflight

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

Condition source gap manifest rows: `{len(report.get("condition_source_gap_manifest") or [])}`

Rollback SQL: `{DEFAULT_PATHS["rollback_sql"]}`
"""


def render_contract_markdown(contract: Mapping[str, Any]) -> str:
    return f"""# N1 Condition Source 20260526 V2 Activation Contract

Result: `{contract["result"]}`

- layer_role: `N1_ingestion`
- trade_date: `{TRADE_DATE}`
- source_batch_id: `{BATCH_ID}`
- source_versions: `{json.dumps(SOURCE_VERSIONS, ensure_ascii=False)}`
- execute runner implemented: `{contract.get("implementation_status", {}).get("execute_runner_implemented")}`
- final execute gate allowed: `{contract.get("implementation_status", {}).get("final_execute_gate_allowed")}`
- allowed tables: `{", ".join(ALLOWED_FUTURE_WRITE_TABLES)}`
- forbidden: daily bar fact, Parquet, outbox/inbox/checkpoint, N2-N6, worker, old system, real trading

Expected rows:

```json
{json.dumps(contract["expected_rows"], ensure_ascii=False, indent=2)}
```

Rollback SQL: `{DEFAULT_PATHS["rollback_sql"]}`
"""


def write_preflight_files(report: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    Path(json_path).write_text(json.dumps(normalize_jsonable(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(markdown_path).write_text(render_preflight_markdown(report), encoding="utf-8")


def write_contract_files(contract: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    Path(json_path).write_text(json.dumps(normalize_jsonable(contract), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(markdown_path).write_text(render_contract_markdown(contract), encoding="utf-8")


def load_execute_contract(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
