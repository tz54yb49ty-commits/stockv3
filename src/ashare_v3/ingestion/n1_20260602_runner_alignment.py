"""N1 20260602 runner/source readiness alignment support.

This module is intentionally read-only. It creates the date-specific N1
official daily and condition source preflight artifacts for 20260602, but it
does not implement or run production ingestion commits.
"""

from __future__ import annotations

from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row

from ashare_v3.ingestion.tushare_env import tushare_token_status


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
TRADE_DATE = "20260602"
FOR_TRADE_DATE = "20260603"
EXPECTED_PREV_TRADE_DATE = "20260601"
EXPECTED_NEXT_TRADE_DATE = "20260603"

OFFICIAL_DAILY_BATCH_ID = "official_daily_ingest_20260602_v1"
OFFICIAL_DAILY_SOURCE_VERSIONS = {
    "stock": "stock_daily_20260602_v1",
    "index": "index_daily_20260602_v1",
    "board": "board_daily_20260602_v1",
}
CONDITION_SOURCE_BATCH_ID = "condition_source_activation_20260602_v1"
CONDITION_SOURCE_VERSIONS = {
    "stock_daily_basic": "stock_daily_basic_20260602_v1",
    "stock_financial": "stock_financial_20260602_v1",
    "index_membership": "index_membership_20260602_v1",
    "board_membership": "board_membership_20260602_v1",
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
ALLOWED_OFFICIAL_DAILY_TABLES = (
    "common_ingest_batch",
    "common_quality_gate_result",
    "common_active_source_version",
    "stock_daily_bar_fact",
    "index_daily_bar_fact",
    "board_daily_bar_fact",
)
ALLOWED_CONDITION_SOURCE_TABLES = (
    "common_ingest_batch",
    "common_quality_gate_result",
    "common_active_source_version",
    "stock_daily_basic",
    "stock_financial_metrics_fact",
    "index_membership_fact",
    "board_membership_fact",
)
DEFAULT_TDX_ROOT = Path("/Volumes/MacRaid/tdxdata/tdx")
DEFAULT_PATHS = {
    "alignment_json": Path("docs/N1_20260602_runner_source_readiness_alignment.json"),
    "alignment_md": Path("docs/N1_20260602_RUNNER_SOURCE_READINESS_ALIGNMENT.md"),
    "official_dry_run_json": Path("docs/N1_official_daily_20260602_ingestion_dry_run_report.json"),
    "official_dry_run_md": Path("docs/N1_INGESTION_20260602_DRY_RUN_PREFLIGHT_REPORT.md"),
    "official_preflight_json": Path("docs/N1_official_daily_20260602_ingestion_execute_preflight.json"),
    "official_preflight_md": Path("docs/N1_OFFICIAL_DAILY_20260602_INGESTION_EXECUTE_PREFLIGHT.md"),
    "condition_preflight_json": Path("docs/N1_condition_source_20260602_activation_execute_preflight.json"),
    "condition_preflight_md": Path("docs/N1_CONDITION_SOURCE_20260602_ACTIVATION_EXECUTE_PREFLIGHT.md"),
    "condition_dry_run_json": Path("docs/N1_condition_source_20260602_activation_dry_run_report.json"),
    "condition_dry_run_md": Path("docs/N1_CONDITION_SOURCE_20260602_ACTIVATION_DRY_RUN_REPORT.md"),
    "official_rollback_sql": Path("sql/N1_official_daily_20260602_ingestion_rollback.sql"),
    "condition_rollback_sql": Path("sql/N1_condition_source_20260602_activation_rollback.sql"),
}


class AlignmentBlocked(RuntimeError):
    """Raised when a guarded 20260602 alignment gate refuses execute."""


def now_iso() -> str:
    return datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat()


def validate_execute_flags(
    *,
    execute_requested: bool,
    user_confirmed: bool,
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> None:
    missing: list[str] = []
    if not execute_requested:
        missing.append("--execute")
    if not user_confirmed:
        missing.append("--user-confirmed")
    if not source_fetch_enabled:
        missing.append("--source-fetch-enabled")
    if not postgres_commit_enabled:
        missing.append("--postgres-commit-enabled")
    if missing:
        raise AlignmentBlocked("missing required final execute flags: " + ", ".join(missing))


def no_side_effects() -> dict[str, bool]:
    return {
        "writes_database": False,
        "postgres_fact_written": False,
        "parquet_written": False,
        "condition_source_written": False,
        "executes_n1_n6": False,
        "enters_n2_n3_a1": False,
        "enters_n2_n3_n4_n5_n6": False,
        "consumes_outbox": False,
        "starts_worker": False,
        "delivery_or_notification": False,
        "old_system_touched": False,
        "real_trading": False,
    }


def collect_source_readiness(*, tdx_root: str | Path = DEFAULT_TDX_ROOT) -> dict[str, Any]:
    root = Path(tdx_root)
    token_status = tushare_token_status()
    token_present = bool(token_status["token_present"])
    tdx_exists = root.exists()
    tdx_readable = os.access(root, os.R_OK)
    mootdx_present = importlib.util.find_spec("mootdx") is not None
    p0_blockers: list[str] = []
    if not token_present:
        p0_blockers.append("tushare_token_absent")
    if not (tdx_exists and tdx_readable):
        p0_blockers.append("tdx_root_unavailable")
    return {
        "tushare_token_present": token_present,
        "tushare_token_length": token_status["token_length"],
        "tushare_fallback_approved": False,
        "tdx_root": str(root),
        "tdx_root_exists": tdx_exists,
        "tdx_root_readable": tdx_readable,
        "mootdx_import_present": mootdx_present,
        "tdx_mootdx_local_source_available": bool(tdx_exists and tdx_readable),
        "source_fetch_boundary": {
            "live_fetch_performed": False,
            "external_tushare_fetch_performed": False,
            "external_mootdx_fetch_performed": False,
        },
        "p0_blockers": p0_blockers,
    }


def sample_baseline() -> dict[str, Any]:
    return {
        "source_trade_date": TRADE_DATE,
        "for_trade_date": FOR_TRADE_DATE,
        "calendar": {
            "row_count": 1,
            "trade_date": TRADE_DATE,
            "is_open": True,
            "prev_trade_date": EXPECTED_PREV_TRADE_DATE,
            "next_trade_date": EXPECTED_NEXT_TRADE_DATE,
        },
        "next_calendar": {"trade_date": FOR_TRADE_DATE, "row_count": 0},
        "official_daily_rows": {"stock": 0, "index": 0, "board": 0, "total": 0},
        "condition_source_rows": {
            "stock_daily_basic": 0,
            "stock_financial": 0,
            "index_membership": 0,
            "board_membership": 0,
            "total": 0,
        },
        "official_batch_conflict": 0,
        "official_quality_conflict": 0,
        "official_active_conflict": 0,
        "condition_batch_conflict": 0,
        "condition_quality_conflict": 0,
        "condition_active_conflict": 0,
        "active_daily_source_versions": [],
        "active_condition_source_versions": [],
        "scope_basis": {
            "stock_identity_active_universe": 5526,
            "fixed_9_index_present": 9,
            "fixed_9_index_missing": [],
            "index_identity_active": None,
            "board_identity_total": 428,
            "board_881": 127,
        },
        "event_counts": {"outbox": None, "inbox": None, "checkpoint": None},
        "read_only_database_checks": True,
    }


def _count_one(cur: Any, sql: str, params: Sequence[Any] = ()) -> int:
    cur.execute(sql, params)
    row = cur.fetchone()
    return int(row["count"] if isinstance(row, Mapping) else row[0])


def build_baseline_from_db(*, dsn: str, tdx_root: str | Path = DEFAULT_TDX_ROOT) -> dict[str, Any]:
    del tdx_root
    source_versions = list(OFFICIAL_DAILY_SOURCE_VERSIONS.values())
    condition_versions = list(CONDITION_SOURCE_VERSIONS.values())
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT trade_date::text, is_open, prev_trade_date::text,
                       next_trade_date::text, source_version
                FROM common_trade_calendar
                WHERE trade_date = %s
                """,
                (TRADE_DATE,),
            )
            calendar_rows = [dict(row) for row in cur.fetchall()]
            calendar = calendar_rows[0] if calendar_rows else {"trade_date": TRADE_DATE}
            calendar["row_count"] = len(calendar_rows)
            cur.execute(
                "SELECT trade_date::text, is_open, prev_trade_date::text, next_trade_date::text FROM common_trade_calendar WHERE trade_date = %s",
                (FOR_TRADE_DATE,),
            )
            next_rows = [dict(row) for row in cur.fetchall()]
            next_calendar = next_rows[0] if next_rows else {"trade_date": FOR_TRADE_DATE}
            next_calendar["row_count"] = len(next_rows)
            official_rows: dict[str, int] = {}
            for asset, table in (
                ("stock", "stock_daily_bar_fact"),
                ("index", "index_daily_bar_fact"),
                ("board", "board_daily_bar_fact"),
            ):
                official_rows[asset] = _count_one(cur, f"SELECT count(*) AS count FROM {table} WHERE trade_date = %s", (TRADE_DATE,))
            official_rows["total"] = sum(official_rows.values())
            condition_rows = {
                "stock_daily_basic": _count_one(cur, "SELECT count(*) AS count FROM stock_daily_basic WHERE trade_date = %s", (TRADE_DATE,)),
                "stock_financial": _count_one(cur, "SELECT count(*) AS count FROM stock_financial_metrics_fact WHERE source_trade_date = %s", (TRADE_DATE,)),
                "index_membership": _count_one(cur, "SELECT count(*) AS count FROM index_membership_fact WHERE trade_date = %s", (TRADE_DATE,)),
                "board_membership": _count_one(cur, "SELECT count(*) AS count FROM board_membership_fact WHERE trade_date = %s", (TRADE_DATE,)),
            }
            condition_rows["total"] = sum(condition_rows.values())
            official_batch_conflict = _count_one(
                cur,
                "SELECT count(*) AS count FROM common_ingest_batch WHERE batch_id = %s OR source_version = ANY(%s)",
                (OFFICIAL_DAILY_BATCH_ID, source_versions),
            )
            official_quality_conflict = _count_one(
                cur,
                "SELECT count(*) AS count FROM common_quality_gate_result WHERE source_batch_id = %s OR source_version = ANY(%s)",
                (OFFICIAL_DAILY_BATCH_ID, source_versions),
            )
            official_active_conflict = _count_one(
                cur,
                "SELECT count(*) AS count FROM common_active_source_version WHERE source_version = ANY(%s)",
                (source_versions,),
            )
            condition_batch_conflict = _count_one(
                cur,
                "SELECT count(*) AS count FROM common_ingest_batch WHERE batch_id = %s OR source_version = ANY(%s)",
                (CONDITION_SOURCE_BATCH_ID, condition_versions),
            )
            condition_quality_conflict = _count_one(
                cur,
                "SELECT count(*) AS count FROM common_quality_gate_result WHERE source_batch_id = %s OR source_version = ANY(%s)",
                (CONDITION_SOURCE_BATCH_ID, condition_versions),
            )
            condition_active_conflict = _count_one(
                cur,
                "SELECT count(*) AS count FROM common_active_source_version WHERE source_version = ANY(%s)",
                (condition_versions,),
            )
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
            active_daily = [dict(row) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT data_domain, data_type, scope_key, source_version, source_batch_id
                FROM common_active_source_version
                WHERE source_version = ANY(%s)
                ORDER BY data_domain, data_type
                """,
                (condition_versions,),
            )
            active_condition = [dict(row) for row in cur.fetchall()]
            stock_active_universe = _count_one(cur, "SELECT count(*) AS count FROM stock_identity WHERE status = 'active'")
            fixed9_present = _count_one(
                cur,
                "SELECT count(*) AS count FROM index_identity WHERE index_identity_key = ANY(%s)",
                (list(FIXED_9_INDEX_IDENTITIES),),
            )
            cur.execute(
                "SELECT index_identity_key FROM index_identity WHERE index_identity_key = ANY(%s)",
                (list(FIXED_9_INDEX_IDENTITIES),),
            )
            fixed9_keys = {str(row["index_identity_key"]) for row in cur.fetchall()}
            board_total = _count_one(cur, "SELECT count(*) AS count FROM board_identity")
            board_881 = _count_one(cur, "SELECT count(*) AS count FROM board_identity WHERE board_code LIKE '881%%'")
            event_counts = {
                "outbox": _count_one(cur, "SELECT count(*) AS count FROM common_event_outbox"),
                "inbox": _count_one(cur, "SELECT count(*) AS count FROM common_event_inbox"),
                "checkpoint": _count_one(cur, "SELECT count(*) AS count FROM common_event_consumer_checkpoint"),
            }
    return {
        "source_trade_date": TRADE_DATE,
        "for_trade_date": FOR_TRADE_DATE,
        "calendar": calendar,
        "next_calendar": next_calendar,
        "official_daily_rows": official_rows,
        "condition_source_rows": condition_rows,
        "official_batch_conflict": official_batch_conflict,
        "official_quality_conflict": official_quality_conflict,
        "official_active_conflict": official_active_conflict,
        "condition_batch_conflict": condition_batch_conflict,
        "condition_quality_conflict": condition_quality_conflict,
        "condition_active_conflict": condition_active_conflict,
        "active_daily_source_versions": active_daily,
        "active_condition_source_versions": active_condition,
        "scope_basis": {
            "stock_identity_active_universe": stock_active_universe,
            "fixed_9_index_present": fixed9_present,
            "fixed_9_index_missing": sorted(set(FIXED_9_INDEX_IDENTITIES) - fixed9_keys),
            "index_identity_active": None,
            "board_identity_total": board_total,
            "board_881": board_881,
        },
        "event_counts": event_counts,
        "read_only_database_checks": True,
    }


def _calendar_ok(baseline: Mapping[str, Any]) -> bool:
    calendar = baseline.get("calendar") or {}
    return (
        int(calendar.get("row_count") or 0) == 1
        and calendar.get("is_open") is True
        and str(calendar.get("prev_trade_date") or "") == EXPECTED_PREV_TRADE_DATE
        and str(calendar.get("next_trade_date") or "") == EXPECTED_NEXT_TRADE_DATE
    )


def _official_baseline_clean(baseline: Mapping[str, Any]) -> bool:
    rows = baseline.get("official_daily_rows") or {}
    return (
        int(rows.get("total") or 0) == 0
        and int(baseline.get("official_batch_conflict") or 0) == 0
        and int(baseline.get("official_quality_conflict") or 0) == 0
        and int(baseline.get("official_active_conflict") or 0) == 0
    )


def _condition_baseline_clean(baseline: Mapping[str, Any]) -> bool:
    rows = baseline.get("condition_source_rows") or {}
    return (
        int(rows.get("total") or 0) == 0
        and int(baseline.get("condition_batch_conflict") or 0) == 0
        and int(baseline.get("condition_quality_conflict") or 0) == 0
        and int(baseline.get("condition_active_conflict") or 0) == 0
    )


def _quality_item(name: str, severity: str, status: str, expected: Any, actual: Any) -> dict[str, Any]:
    return {"gate_name": name, "severity": severity, "status": status, "expected": expected, "actual": actual}


def _summarize_quality(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    p0 = sum(1 for item in items if item.get("severity") == "P0" and item.get("status") != "passed")
    p1 = sum(1 for item in items if item.get("severity") == "P1")
    p2 = sum(1 for item in items if item.get("severity") == "P2")
    return {"p0_count": p0, "p1_count": p1, "p2_count": p2, "items": [dict(item) for item in items]}


def _expected_scope_summary(baseline: Mapping[str, Any]) -> dict[str, Any]:
    scope = baseline.get("scope_basis") or {}
    return {
        "official_daily": {
            "stock_scope_basis": {
                "active_stock_identity": scope.get("stock_identity_active_universe"),
                "daily_bar_rows": "TBD_after_Tushare_daily_adj_factor_source_probe",
            },
            "index_scope_basis": {
                "fixed_9_present": scope.get("fixed_9_index_present"),
                "fixed_9_missing": scope.get("fixed_9_index_missing") or [],
                "daily_bar_rows": "TBD_after_Mootdx_Tushare_BJ_source_probe",
            },
            "board_scope_basis": {
                "board_identity_total": scope.get("board_identity_total"),
                "industry_881": scope.get("board_881"),
                "daily_bar_rows": "TBD_after_TDX_Mootdx_source_probe",
            },
        },
        "condition_source": {
            "stock_daily_basic": "blocked_until_official_daily_20260602_passed",
            "stock_financial": "blocked_until_official_daily_20260602_passed",
            "index_membership": "TBD_after_TDX_membership_validation",
            "board_membership": "TBD_after_TDX_membership_validation",
        },
    }


def build_official_daily_preflight(
    *,
    baseline: Mapping[str, Any],
    source_readiness: Mapping[str, Any],
    execute_requested: bool,
    user_confirmed: bool,
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    if execute_requested:
        validate_execute_flags(
            execute_requested=execute_requested,
            user_confirmed=user_confirmed,
            source_fetch_enabled=source_fetch_enabled,
            postgres_commit_enabled=postgres_commit_enabled,
        )
    items = [
        _quality_item(
            "calendar_ready",
            "P0",
            "passed" if _calendar_ok(baseline) else "failed",
            f"row=1,is_open=true,prev={EXPECTED_PREV_TRADE_DATE},next={EXPECTED_NEXT_TRADE_DATE}",
            baseline.get("calendar"),
        ),
        _quality_item("official_daily_baseline_clean", "P0", "passed" if _official_baseline_clean(baseline) else "failed", "daily/batch/quality/active conflicts=0", {
            "daily_rows": baseline.get("official_daily_rows"),
            "batch": baseline.get("official_batch_conflict"),
            "quality": baseline.get("official_quality_conflict"),
            "active": baseline.get("official_active_conflict"),
        }),
        _quality_item(
            "tushare_source_ready",
            "P0",
            "passed" if source_readiness.get("tushare_token_present") else "failed",
            "TUSHARE_TOKEN_PRESENT=true or approved fallback",
            {"TUSHARE_TOKEN_PRESENT": bool(source_readiness.get("tushare_token_present")), "fallback_approved": False},
        ),
        _quality_item(
            "tdx_mootdx_source_ready",
            "P0",
            "passed" if source_readiness.get("tdx_mootdx_local_source_available") else "failed",
            "TDX/Mootdx local source readable",
            source_readiness,
        ),
        _quality_item(
            "next_calendar_detail_ready",
            "P1",
            "passed" if int((baseline.get("next_calendar") or {}).get("row_count") or 0) == 1 else "warning",
            f"common_trade_calendar({FOR_TRADE_DATE})=1",
            baseline.get("next_calendar"),
        ),
    ]
    quality = _summarize_quality(items)
    final_allowed = quality["p0_count"] == 0
    return {
        "stage": "N1 official daily 20260602 ingestion execute preflight",
        "layer_role": "N1_ingestion",
        "result": "PREFLIGHT_PASS" if final_allowed else "PREFLIGHT_BLOCKED",
        "trade_date": TRADE_DATE,
        "for_trade_date": FOR_TRADE_DATE,
        "source_batch_id": OFFICIAL_DAILY_BATCH_ID,
        "source_versions": dict(OFFICIAL_DAILY_SOURCE_VERSIONS),
        "runner": {
            "exists": True,
            "default_execute": False,
            "runner_readiness": "ready_for_dry_run_preflight_gate",
            "production_commit_path": "not_entered_in_alignment_gate",
        },
        "execute_flags_required": ["--execute", "--user-confirmed", "--source-fetch-enabled", "--postgres-commit-enabled"],
        "execute_flags_seen": {
            "execute": execute_requested,
            "user_confirmed": user_confirmed,
            "source_fetch_enabled": source_fetch_enabled,
            "postgres_commit_enabled": postgres_commit_enabled,
        },
        "execute_authorized": False,
        "final_execute_gate_allowed": False,
        "baseline": {
            "calendar": baseline.get("calendar"),
            "next_calendar": baseline.get("next_calendar"),
            "official_daily_rows": baseline.get("official_daily_rows"),
            "batch_conflict": baseline.get("official_batch_conflict"),
            "quality_conflict": baseline.get("official_quality_conflict"),
            "active_conflict": baseline.get("official_active_conflict"),
        },
        "source_readiness": dict(source_readiness),
        "expected_scope": _expected_scope_summary(baseline)["official_daily"],
        "future_write_scope": {"allowed_tables": list(ALLOWED_OFFICIAL_DAILY_TABLES)},
        "rollback": {"path": str(DEFAULT_PATHS["official_rollback_sql"]), "hard_fail_before_delete_required": True},
        "quality": quality,
        "side_effects": no_side_effects(),
        "execute_command_candidate": (
            "PYTHONPATH=src python3 scripts/run_official_daily_ingestion_20260602_once.py "
            "--trade-date 20260602 --execute --user-confirmed --source-fetch-enabled --postgres-commit-enabled"
        ),
        "generated_at": now_iso(),
    }


def build_condition_source_preflight(
    *,
    baseline: Mapping[str, Any],
    source_readiness: Mapping[str, Any],
    execute_requested: bool,
    user_confirmed: bool,
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    if execute_requested:
        validate_execute_flags(
            execute_requested=execute_requested,
            user_confirmed=user_confirmed,
            source_fetch_enabled=source_fetch_enabled,
            postgres_commit_enabled=postgres_commit_enabled,
        )
    official_passed = len(baseline.get("active_daily_source_versions") or []) == 3 and int((baseline.get("official_daily_rows") or {}).get("total") or 0) > 0
    items = [
        _quality_item("condition_source_baseline_clean", "P0", "passed" if _condition_baseline_clean(baseline) else "failed", "target rows/batch/quality/active conflicts=0", {
            "target_rows": baseline.get("condition_source_rows"),
            "batch": baseline.get("condition_batch_conflict"),
            "quality": baseline.get("condition_quality_conflict"),
            "active": baseline.get("condition_active_conflict"),
        }),
        _quality_item(
            "condition_source_requires_official_daily_20260602_passed",
            "P0",
            "passed" if official_passed else "failed",
            "active stock/index/board daily source_version for 20260602",
            {"active_daily_source_versions": baseline.get("active_daily_source_versions"), "official_daily_rows": baseline.get("official_daily_rows")},
        ),
        _quality_item(
            "tushare_source_ready",
            "P0",
            "passed" if source_readiness.get("tushare_token_present") else "failed",
            "TUSHARE_TOKEN_PRESENT=true or approved fallback",
            {"TUSHARE_TOKEN_PRESENT": bool(source_readiness.get("tushare_token_present")), "fallback_approved": False},
        ),
        _quality_item(
            "tdx_mootdx_source_ready",
            "P0",
            "passed" if source_readiness.get("tdx_mootdx_local_source_available") else "failed",
            "TDX/Mootdx local source readable",
            source_readiness,
        ),
    ]
    quality = _summarize_quality(items)
    return {
        "stage": "N1 condition source activation 20260602 execute preflight",
        "layer_role": "N1_ingestion",
        "result": "PREFLIGHT_PASS" if quality["p0_count"] == 0 else "PREFLIGHT_BLOCKED",
        "trade_date": TRADE_DATE,
        "source_batch_id": CONDITION_SOURCE_BATCH_ID,
        "source_versions": dict(CONDITION_SOURCE_VERSIONS),
        "runner": {
            "exists": True,
            "default_execute": False,
            "runner_readiness": "ready_for_dry_run_preflight_gate",
            "production_commit_path": "blocked_until_official_daily_20260602_passed",
        },
        "execute_flags_required": ["--execute", "--user-confirmed", "--source-fetch-enabled", "--postgres-commit-enabled"],
        "execute_flags_seen": {
            "execute": execute_requested,
            "user_confirmed": user_confirmed,
            "source_fetch_enabled": source_fetch_enabled,
            "postgres_commit_enabled": postgres_commit_enabled,
        },
        "execute_authorized": False,
        "final_execute_gate_allowed": False,
        "baseline": {
            "condition_source_rows": baseline.get("condition_source_rows"),
            "batch_conflict": baseline.get("condition_batch_conflict"),
            "quality_conflict": baseline.get("condition_quality_conflict"),
            "active_conflict": baseline.get("condition_active_conflict"),
            "upstream_official_daily": {
                "daily_rows": baseline.get("official_daily_rows"),
                "active_daily_source_versions": baseline.get("active_daily_source_versions"),
            },
        },
        "source_readiness": dict(source_readiness),
        "expected_scope": _expected_scope_summary(baseline)["condition_source"],
        "future_write_scope": {"allowed_tables": list(ALLOWED_CONDITION_SOURCE_TABLES)},
        "rollback": {"path": str(DEFAULT_PATHS["condition_rollback_sql"]), "hard_fail_before_delete_required": True},
        "quality": quality,
        "side_effects": no_side_effects(),
        "execute_command_candidate": (
            "PYTHONPATH=src python3 scripts/run_condition_source_activation_20260602_once.py "
            "--trade-date 20260602 --execute --user-confirmed --source-fetch-enabled --postgres-commit-enabled"
        ),
        "generated_at": now_iso(),
    }


def build_alignment_report(*, baseline: Mapping[str, Any], source_readiness: Mapping[str, Any]) -> dict[str, Any]:
    official = build_official_daily_preflight(
        baseline=baseline,
        source_readiness=source_readiness,
        execute_requested=False,
        user_confirmed=False,
        source_fetch_enabled=False,
        postgres_commit_enabled=False,
    )
    condition = build_condition_source_preflight(
        baseline=baseline,
        source_readiness=source_readiness,
        execute_requested=False,
        user_confirmed=False,
        source_fetch_enabled=False,
        postgres_commit_enabled=False,
    )
    p0_names: list[str] = []
    for report in (official, condition):
        for item in report["quality"]["items"]:
            if item.get("severity") == "P0" and item.get("status") != "passed":
                p0_names.append(str(item.get("gate_name")))
    if "tushare_source_ready" in p0_names:
        p0_names = ["tushare_token_absent" if name == "tushare_source_ready" else name for name in p0_names]
    unique_blockers = sorted(set(p0_names))
    quality = {
        "p0_count": len(unique_blockers),
        "p1_count": official["quality"]["p1_count"] + condition["quality"]["p1_count"],
        "p2_count": official["quality"]["p2_count"] + condition["quality"]["p2_count"],
        "p0_items": unique_blockers,
    }
    result = "ALIGNMENT_PASS" if not unique_blockers else "BLOCKED"
    return {
        "stage": "N1_20260602 runner/source readiness alignment gate",
        "layer_role": "N1_ingestion",
        "result": result,
        "source_trade_date": TRADE_DATE,
        "for_trade_date": FOR_TRADE_DATE,
        "runners": {
            "official_daily": {
                "exists": True,
                "default_execute": False,
                "script": "scripts/run_official_daily_ingestion_20260602_once.py",
                "module": "ashare_v3.ingestion.n1_20260602_runner_alignment",
            },
            "condition_source": {
                "exists": True,
                "default_execute": False,
                "script": "scripts/run_condition_source_activation_20260602_once.py",
                "module": "ashare_v3.ingestion.n1_20260602_runner_alignment",
            },
        },
        "blockers": unique_blockers,
        "source_readiness": dict(source_readiness),
        "expected_scope": _expected_scope_summary(baseline),
        "planned_ids": {
            "official_daily": {
                "source_batch_id": OFFICIAL_DAILY_BATCH_ID,
                "source_versions": dict(OFFICIAL_DAILY_SOURCE_VERSIONS),
            },
            "condition_source": {
                "source_batch_id": CONDITION_SOURCE_BATCH_ID,
                "source_versions": dict(CONDITION_SOURCE_VERSIONS),
            },
        },
        "baseline": baseline,
        "rollback": {
            "official_daily": check_rollback_sql_scope(DEFAULT_PATHS["official_rollback_sql"], required_tokens=[OFFICIAL_DAILY_BATCH_ID, *OFFICIAL_DAILY_SOURCE_VERSIONS.values()]),
            "condition_source": check_rollback_sql_scope(DEFAULT_PATHS["condition_rollback_sql"], required_tokens=[CONDITION_SOURCE_BATCH_ID, *CONDITION_SOURCE_VERSIONS.values()]),
        },
        "quality": quality,
        "side_effects": no_side_effects(),
        "return_to_dry_run_preflight_gate": True,
        "generated_at": now_iso(),
    }


def check_rollback_sql_scope(path: str | Path, *, required_tokens: Sequence[str]) -> dict[str, Any]:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    upper = text.upper()
    first_delete = upper.find("DELETE")
    hard_fail_before_delete = first_delete > -1 and upper.find("RAISE EXCEPTION") != -1 and upper.find("RAISE EXCEPTION") < first_delete
    required_present = {token: token in text for token in required_tokens}
    forbidden_write_patterns = (
        "DELETE FROM COMMON_EVENT_OUTBOX",
        "DELETE FROM COMMON_EVENT_INBOX",
        "DELETE FROM COMMON_EVENT_CONSUMER_CHECKPOINT",
        "UPDATE COMMON_EVENT_OUTBOX",
        "UPDATE COMMON_EVENT_INBOX",
        "UPDATE COMMON_EVENT_CONSUMER_CHECKPOINT",
        "INSERT INTO COMMON_EVENT_OUTBOX",
        "INSERT INTO COMMON_EVENT_INBOX",
        "INSERT INTO COMMON_EVENT_CONSUMER_CHECKPOINT",
        "DELETE FROM STOCK_CONDITION_",
        "DELETE FROM INDEX_CONDITION_",
        "DELETE FROM BOARD_CONDITION_",
        "DELETE FROM COMMON_CONDITION_",
        "INSERT INTO STOCK_CONDITION_",
        "UPDATE STOCK_CONDITION_",
    )
    forbidden_scope_touched = any(pattern in upper for pattern in forbidden_write_patterns)
    result = "ROLLBACK_SCOPE_PASS" if hard_fail_before_delete and all(required_present.values()) and not forbidden_scope_touched else "ROLLBACK_SCOPE_BLOCKED"
    return {
        "path": str(target),
        "result": result,
        "hard_fail_before_delete": hard_fail_before_delete,
        "required_tokens_present": required_present,
        "forbidden_scope_touched": forbidden_scope_touched,
    }


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_markdown(path: str | Path, title: str, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join([f"# {title}", "", "```json", json.dumps(payload, ensure_ascii=False, indent=2, default=str), "```", ""]),
        encoding="utf-8",
    )


def write_alignment_artifacts(*, alignment: Mapping[str, Any], official_preflight: Mapping[str, Any], condition_preflight: Mapping[str, Any]) -> None:
    write_json(DEFAULT_PATHS["alignment_json"], alignment)
    write_markdown(DEFAULT_PATHS["alignment_md"], "N1 20260602 Runner Source Readiness Alignment", alignment)
    write_json(DEFAULT_PATHS["official_preflight_json"], official_preflight)
    write_markdown(DEFAULT_PATHS["official_preflight_md"], "N1 Official Daily 20260602 Ingestion Execute Preflight", official_preflight)
    write_json(DEFAULT_PATHS["condition_preflight_json"], condition_preflight)
    write_markdown(DEFAULT_PATHS["condition_preflight_md"], "N1 Condition Source 20260602 Activation Execute Preflight", condition_preflight)
    official_dry_run = {
        "stage": "N1 official daily 20260602 ingestion dry-run",
        "layer_role": "N1_ingestion",
        "result": "DRY_RUN_BLOCKED" if official_preflight["quality"]["p0_count"] else "DRY_RUN_PASS",
        "trade_date": TRADE_DATE,
        "for_trade_date": FOR_TRADE_DATE,
        "source_batch_id": OFFICIAL_DAILY_BATCH_ID,
        "source_versions": dict(OFFICIAL_DAILY_SOURCE_VERSIONS),
        "read_only_baseline": official_preflight.get("baseline"),
        "expected_scope": official_preflight.get("expected_scope"),
        "quality": official_preflight.get("quality"),
        "blockers": [
            item.get("gate_name")
            for item in official_preflight.get("quality", {}).get("items", [])
            if item.get("severity") == "P0" and item.get("status") != "passed"
        ],
        "rollback_sql_path": str(DEFAULT_PATHS["official_rollback_sql"]),
        "side_effects": no_side_effects(),
        "generated_at": now_iso(),
    }
    write_json(DEFAULT_PATHS["official_dry_run_json"], official_dry_run)
    write_markdown(DEFAULT_PATHS["official_dry_run_md"], "N1 Ingestion 20260602 Dry-Run / Preflight Report", official_dry_run)
    condition_dry_run = {
        "stage": "N1 condition source activation 20260602 dry-run",
        "layer_role": "N1_ingestion",
        "result": "DRY_RUN_BLOCKED" if condition_preflight["quality"]["p0_count"] else "DRY_RUN_PASS",
        "trade_date": TRADE_DATE,
        "source_batch_id": CONDITION_SOURCE_BATCH_ID,
        "source_versions": dict(CONDITION_SOURCE_VERSIONS),
        "read_only_baseline": condition_preflight.get("baseline"),
        "expected_scope": condition_preflight.get("expected_scope"),
        "quality": condition_preflight.get("quality"),
        "blockers": [
            item.get("gate_name")
            for item in condition_preflight.get("quality", {}).get("items", [])
            if item.get("severity") == "P0" and item.get("status") != "passed"
        ],
        "rollback_sql_path": str(DEFAULT_PATHS["condition_rollback_sql"]),
        "side_effects": no_side_effects(),
        "generated_at": now_iso(),
    }
    write_json(DEFAULT_PATHS["condition_dry_run_json"], condition_dry_run)
    write_markdown(DEFAULT_PATHS["condition_dry_run_md"], "N1 Condition Source 20260602 Activation Dry-Run Report", condition_dry_run)
