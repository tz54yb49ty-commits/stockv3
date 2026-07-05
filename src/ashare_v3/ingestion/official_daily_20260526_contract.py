"""N1 official daily 20260526 dry-run and execute contract artifacts.

This module is intentionally contract/preflight only. It performs read-only
PostgreSQL checks, builds JSON/Markdown artifacts, and drafts rollback SQL. It
does not fetch market data, write PostgreSQL facts, write Parquet, update active
source versions, enter downstream layers, or start workers.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
TRADE_DATE = "20260526"
EXPECTED_PREV_TRADE_DATE = "20260525"
EXPECTED_NEXT_TRADE_DATE = "20260527"
BATCH_ID = "official_daily_ingest_20260526_v1"
CONTRACT_SOURCE_VERSION = BATCH_ID
SOURCE_VERSIONS = {
    "stock": "stock_daily_20260526_v1",
    "index": "index_daily_20260526_v1",
    "board": "board_daily_20260526_v1",
}
EXPECTED_SCOPE = {
    "stock_active_universe": 5523,
    "fixed_9_index": 9,
    "board_total": 428,
    "board_881_required": 127,
    "total_daily_fact_rows": 5523 + 9 + 428,
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
ACTIVE_DATA_TYPES = {
    "stock": "stock_daily",
    "index": "index_daily",
    "board": "board_daily",
}
ALLOWED_FUTURE_WRITE_TABLES = (
    "common_ingest_batch",
    "common_quality_gate_result",
    "common_active_source_version",
    "stock_daily_bar_fact",
    "index_daily_bar_fact",
    "board_daily_bar_fact",
)
FORBIDDEN_SCOPE = (
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "stock_daily_basic",
    "stock_financial_metrics_fact",
    "N2_condition_tables",
    "N3_market_data_tables",
    "N4_trigger_tables",
    "N5_action_tables",
    "N6_user_tables",
    "Parquet",
    "worker",
    "old_system",
    "real_trading",
)
DEFAULT_PATHS = {
    "dry_run_json": Path("docs/N1_official_daily_20260526_ingestion_dry_run_plan.json"),
    "dry_run_md": Path("docs/N1_OFFICIAL_DAILY_20260526_INGESTION_DRY_RUN_PLAN.md"),
    "contract_json": Path("docs/N1_official_daily_20260526_ingestion_execute_contract.json"),
    "contract_md": Path("docs/N1_OFFICIAL_DAILY_20260526_INGESTION_EXECUTE_CONTRACT.md"),
    "preflight_json": Path("docs/N1_official_daily_20260526_ingestion_execute_preflight.json"),
    "preflight_md": Path("docs/N1_OFFICIAL_DAILY_20260526_INGESTION_EXECUTE_PREFLIGHT.md"),
    "rollback_sql": Path("sql/N1_official_daily_20260526_ingestion_rollback.sql"),
}


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
        "stock_active_universe": 5523,
        "fixed_9_index_present": 9,
        "fixed_9_index_missing": [],
        "board_total": 428,
        "board_881": 127,
        "event_counts": {"outbox": 74176, "inbox": 2952, "checkpoint": 2803},
        "read_only_database_checks": True,
    }


def build_snapshot_from_db(*, dsn: str, trade_date: str = TRADE_DATE) -> dict[str, Any]:
    if trade_date != TRADE_DATE:
        raise ValueError("This generator is fixed to trade_date=20260526")

    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            calendar = fetch_calendar(cur)
            snapshot = {
                "trade_date": TRADE_DATE,
                "calendar": calendar,
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
                "contract_batch_exists": scalar_count(
                    cur,
                    "SELECT count(*) FROM common_ingest_batch WHERE batch_id = %s",
                    (BATCH_ID,),
                )
                > 0,
                "target_source_version_conflicts": fetch_target_source_version_conflicts(cur),
                "stock_active_universe": scalar_count(
                    cur,
                    "SELECT count(*) FROM stock_identity WHERE status = 'active'",
                ),
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
    return {
        asset: scalar_count(cur, sql, (TRADE_DATE, SOURCE_VERSIONS[asset]))
        for asset, sql in queries.items()
    }


def fetch_fixed_9_index_present(cur: Any) -> int:
    cur.execute(
        "SELECT count(*) FROM index_identity WHERE index_identity_key = ANY(%s)",
        (list(FIXED_9_INDEX_IDENTITIES),),
    )
    row = cur.fetchone()
    if isinstance(row, dict):
        return int(next(iter(row.values())))
    return int(row[0])


def fetch_fixed_9_index_missing(cur: Any) -> list[str]:
    cur.execute(
        "SELECT index_identity_key FROM index_identity WHERE index_identity_key = ANY(%s)",
        (list(FIXED_9_INDEX_IDENTITIES),),
    )
    present = {
        str(row["index_identity_key"] if isinstance(row, dict) else row[0])
        for row in cur.fetchall()
    }
    return sorted(set(FIXED_9_INDEX_IDENTITIES) - present)


def build_dry_run_plan(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    current_rows = add_total(snapshot.get("current_daily_fact_rows") or {})
    missing = {
        "stock": max(EXPECTED_SCOPE["stock_active_universe"] - current_rows["stock"], 0),
        "index": max(EXPECTED_SCOPE["fixed_9_index"] - current_rows["index"], 0),
        "board": max(EXPECTED_SCOPE["board_total"] - current_rows["board"], 0),
    }
    missing["total"] = missing["stock"] + missing["index"] + missing["board"]
    quality = build_quality(snapshot)
    return normalize_jsonable(
        {
            "stage": "N1 official daily 20260526 ingestion dry-run plan",
            "layer_role": "N1_ingestion",
            "result": "DRY_RUN_BLOCKED" if quality["p0_count"] else "DRY_RUN_PASS",
            "blocked": bool(quality["p0_count"]),
            "trade_date": TRADE_DATE,
            "source_batch_id": BATCH_ID,
            "contract_source_version": CONTRACT_SOURCE_VERSION,
            "source_versions": dict(SOURCE_VERSIONS),
            "expected_scope": dict(EXPECTED_SCOPE),
            "current_n1_fact": {
                "stock_daily_bar_fact": current_rows["stock"],
                "index_daily_bar_fact": current_rows["index"],
                "board_daily_bar_fact": current_rows["board"],
                "total": current_rows["total"],
            },
            "missing_official_daily": missing,
            "source_fetch_plan": {
                "actual_fetch_in_this_stage": False,
                "stock": {
                    "source": "Tushare daily + adj_factor proof",
                    "expected_rows": EXPECTED_SCOPE["stock_active_universe"],
                },
                "index": {
                    "source": "TDX/Mootdx preferred; Tushare index_daily fallback",
                    "expected_rows": EXPECTED_SCOPE["fixed_9_index"],
                    "required_fixed_9": list(FIXED_9_INDEX_IDENTITIES),
                },
                "board": {
                    "source": "TDX/Mootdx board daily",
                    "expected_rows": EXPECTED_SCOPE["board_total"],
                    "required_881_coverage": EXPECTED_SCOPE["board_881_required"],
                },
            },
            "quality": quality,
            "contract_alignment": build_contract_alignment(),
            "side_effects": no_side_effects(),
            "generated_at": now_iso(),
        }
    )


def build_execute_contract(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    quality = build_quality(snapshot)
    return normalize_jsonable(
        {
            "stage": "N1 official daily 20260526 ingestion execute contract",
            "layer_role": "N1_ingestion",
            "result": "DESIGN_PASS" if not quality["p0_count"] else "DESIGN_BLOCKED",
            "trade_date": TRADE_DATE,
            "contract_batch_id": BATCH_ID,
            "contract_source_version": CONTRACT_SOURCE_VERSION,
            "source_versions": dict(SOURCE_VERSIONS),
            "expected_scope": dict(EXPECTED_SCOPE),
            "execute_flags": ["--execute", "--user-confirmed", "--source-fetch-enabled", "--postgres-commit-enabled"],
            "source_contract": {
                "stock": "Tushare daily + adj_factor proof",
                "index": "TDX/Mootdx preferred; Tushare index_daily fallback",
                "board": "TDX/Mootdx board daily; board_total=428 and board_881_required=127",
                "forbidden_sources": ["N3 snapshot", "C2/C2B summary", "C3 outbox", "old system", "manual data"],
            },
            "idempotency": {
                "block_existing_batch_id": True,
                "block_existing_source_version": True,
                "block_existing_active_source_version": True,
                "overwrite_active_source_version": False,
            },
            "quality_gate": {
                "p0_must_equal_zero": True,
                "required_checks": [
                    "calendar_ready",
                    "stock_active_universe=5523",
                    "fixed_9_index=9",
                    "board_total=428",
                    "board_881_required=127",
                    "duplicate_identity_key=0",
                    "same_code_contamination=0",
                    "stock_adj_factor_proof=100%",
                    "OHLC/volume/amount sanity",
                ],
                "current_contract_quality": quality,
            },
            "future_write_scope": {
                "allowed_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
                "single_transaction": True,
                "postgres_only": True,
            },
            "transaction_boundary": [
                "common_ingest_batch",
                "stock_daily_bar_fact",
                "index_daily_bar_fact",
                "board_daily_bar_fact",
                "common_quality_gate_result",
                "common_active_source_version",
                "common_ingest_batch status update",
            ],
            "parquet_policy": {
                "writes_parquet": False,
                "reason": "initial gate is PostgreSQL only to keep rollback scope narrow",
            },
            "rollback": {
                "path": str(DEFAULT_PATHS["rollback_sql"]),
                "strategy": "delete by trade_date/source_batch_id/source_version and remove this active source_version",
                "do_not_touch_calendar_patch": True,
            },
            "eod_handoff": {
                "read_active_source_version_first": True,
                "read_by_trade_date_source_version_identity_key": True,
                "forbid_max_trade_date": True,
                "forbid_runtime_snapshot_substitution": True,
            },
            "forbidden_scope": list(FORBIDDEN_SCOPE),
            "side_effects": no_side_effects(),
            "generated_at": now_iso(),
        }
    )


def build_execute_preflight(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    quality = build_quality(snapshot)
    blockers = build_blockers(snapshot)
    result = "PREFLIGHT_BLOCKED" if blockers else "PREFLIGHT_PASS"
    return normalize_jsonable(
        {
            "stage": "N1 official daily 20260526 ingestion execute preflight",
            "layer_role": "N1_ingestion",
            "result": result,
            "blocked": bool(blockers),
            "blockers": blockers,
            "trade_date": TRADE_DATE,
            "source_batch_id": BATCH_ID,
            "source_versions": dict(SOURCE_VERSIONS),
            "execute_authorized": False,
            "final_gate_required": True,
            "final_execute_gate_allowed": False,
            "runner_readiness": "dry_run_contract_ready_execute_runner_not_implemented",
            "source_fetch_implemented": False,
            "postgres_commit_implemented": False,
            "baseline": {
                "calendar": snapshot.get("calendar") or {},
                "active_trade_calendar_count": int(snapshot.get("active_trade_calendar_count") or 0),
                "current_daily_fact_rows": add_total(snapshot.get("current_daily_fact_rows") or {}),
                "active_daily_source_versions": list(snapshot.get("active_daily_source_versions") or []),
                "contract_batch_exists": bool(snapshot.get("contract_batch_exists")),
                "target_source_version_conflicts": add_total(snapshot.get("target_source_version_conflicts") or {}),
                "event_counts": snapshot.get("event_counts") or {},
            },
            "expected_scope": dict(EXPECTED_SCOPE),
            "expected_future_writes": {
                "allowed_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
                "writes_postgres": True,
                "writes_parquet": False,
                "updates_active_source_version": True,
                "writes_outbox": False,
                "enters_n2_n3_n4_n5_n6": False,
            },
            "quality": quality,
            "rollback": {
                "path": str(DEFAULT_PATHS["rollback_sql"]),
                "source_batch_id": BATCH_ID,
                "source_versions": dict(SOURCE_VERSIONS),
                "rollback_safe": True,
            },
            "side_effects": no_side_effects(),
            "generated_at": now_iso(),
        }
    )


def build_quality(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    items = [
        quality_item(
            "calendar_ready",
            passed=calendar_ready(snapshot),
            expected="row=1,is_open=true,prev=20260525,next=20260527",
            actual=snapshot.get("calendar") or {},
        ),
        quality_item(
            "active_trade_calendar_ready",
            passed=int(snapshot.get("active_trade_calendar_count") or 0) == 1,
            expected=1,
            actual=int(snapshot.get("active_trade_calendar_count") or 0),
        ),
        quality_item(
            "daily_fact_absent_before_execute",
            passed=add_total(snapshot.get("current_daily_fact_rows") or {})["total"] == 0,
            expected=0,
            actual=add_total(snapshot.get("current_daily_fact_rows") or {})["total"],
        ),
        quality_item(
            "daily_active_source_version_absent",
            passed=len(snapshot.get("active_daily_source_versions") or []) == 0,
            expected=0,
            actual=len(snapshot.get("active_daily_source_versions") or []),
        ),
        quality_item(
            "contract_batch_absent",
            passed=not bool(snapshot.get("contract_batch_exists")),
            expected=False,
            actual=bool(snapshot.get("contract_batch_exists")),
        ),
        quality_item(
            "source_version_conflicts_absent",
            passed=add_total(snapshot.get("target_source_version_conflicts") or {})["total"] == 0,
            expected=0,
            actual=add_total(snapshot.get("target_source_version_conflicts") or {})["total"],
        ),
        quality_item(
            "stock_active_universe_count",
            passed=int(snapshot.get("stock_active_universe") or 0) == EXPECTED_SCOPE["stock_active_universe"],
            expected=EXPECTED_SCOPE["stock_active_universe"],
            actual=int(snapshot.get("stock_active_universe") or 0),
        ),
        quality_item(
            "fixed_9_index_identity_coverage",
            passed=int(snapshot.get("fixed_9_index_present") or 0) == EXPECTED_SCOPE["fixed_9_index"],
            expected=EXPECTED_SCOPE["fixed_9_index"],
            actual=int(snapshot.get("fixed_9_index_present") or 0),
            details={"missing": list(snapshot.get("fixed_9_index_missing") or [])},
        ),
        quality_item(
            "board_total_scope_count",
            passed=int(snapshot.get("board_total") or 0) == EXPECTED_SCOPE["board_total"],
            expected=EXPECTED_SCOPE["board_total"],
            actual=int(snapshot.get("board_total") or 0),
        ),
        quality_item(
            "board_881_required_coverage",
            passed=int(snapshot.get("board_881") or 0) == EXPECTED_SCOPE["board_881_required"],
            expected=EXPECTED_SCOPE["board_881_required"],
            actual=int(snapshot.get("board_881") or 0),
        ),
    ]
    return normalize_jsonable(
        {
            "p0_count": sum(1 for item in items if item["severity"] == "P0" and item["status"] != "passed"),
            "p1_count": 0,
            "p2_count": 0,
            "items": items,
        }
    )


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
    if int(snapshot.get("stock_active_universe") or 0) != EXPECTED_SCOPE["stock_active_universe"]:
        blockers.append("stock_universe_count_mismatch")
    if int(snapshot.get("fixed_9_index_present") or 0) != EXPECTED_SCOPE["fixed_9_index"]:
        blockers.append("fixed_9_index_missing")
    if int(snapshot.get("board_total") or 0) != EXPECTED_SCOPE["board_total"]:
        blockers.append("board_total_mismatch")
    if int(snapshot.get("board_881") or 0) != EXPECTED_SCOPE["board_881_required"]:
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


def quality_item(
    gate_name: str,
    *,
    passed: bool,
    expected: Any,
    actual: Any,
    severity: str = "P0",
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "gate_name": gate_name,
        "severity": severity,
        "status": "passed" if passed else "failed",
        "expected": expected,
        "actual": actual,
        "details": dict(details or {}),
    }


def build_contract_alignment() -> dict[str, Any]:
    return {
        "batch_id": BATCH_ID,
        "source_versions": dict(SOURCE_VERSIONS),
        "writes_postgres_in_this_stage": False,
        "writes_parquet_in_this_stage": False,
        "updates_active_source_version_in_this_stage": False,
        "enters_n2_n3_n4_n5_n6": False,
    }


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


def build_rollback_sql() -> str:
    stock_version = SOURCE_VERSIONS["stock"]
    index_version = SOURCE_VERSIONS["index"]
    board_version = SOURCE_VERSIONS["board"]
    return f"""-- N1 official daily 20260526 rollback draft.
-- Scope: official daily fact ingestion batch {BATCH_ID}.
-- Review execute report before use, especially previous_source_version restoration.

BEGIN;

DELETE FROM common_active_source_version
WHERE scope_key = '{TRADE_DATE}'
  AND source_batch_id = '{BATCH_ID}'
  AND (
    (data_domain = 'stock' AND data_type = 'stock_daily' AND source_version = '{stock_version}')
    OR (data_domain = 'index' AND data_type = 'index_daily' AND source_version = '{index_version}')
    OR (data_domain = 'board' AND data_type = 'board_daily' AND source_version = '{board_version}')
  );

DELETE FROM common_quality_gate_result
WHERE source_batch_id = '{BATCH_ID}'
   OR source_version IN ('{BATCH_ID}', '{stock_version}', '{index_version}', '{board_version}');

DELETE FROM stock_daily_bar_fact
WHERE trade_date = '{TRADE_DATE}'
  AND source_batch_id = '{BATCH_ID}'
  AND source_version = '{stock_version}';

DELETE FROM index_daily_bar_fact
WHERE trade_date = '{TRADE_DATE}'
  AND source_batch_id = '{BATCH_ID}'
  AND source_version = '{index_version}';

DELETE FROM board_daily_bar_fact
WHERE trade_date = '{TRADE_DATE}'
  AND source_batch_id = '{BATCH_ID}'
  AND source_version = '{board_version}';

DELETE FROM common_ingest_batch
WHERE batch_id = '{BATCH_ID}';

COMMIT;
"""


def write_artifacts(snapshot: Mapping[str, Any], *, paths: Mapping[str, Path] | None = None) -> dict[str, str]:
    resolved = {key: Path(value) for key, value in (paths or DEFAULT_PATHS).items()}
    dry_run = build_dry_run_plan(snapshot)
    contract = build_execute_contract(snapshot)
    preflight = build_execute_preflight(snapshot)
    rollback_sql = build_rollback_sql()

    write_json(resolved["dry_run_json"], dry_run)
    write_text(resolved["dry_run_md"], render_dry_run_markdown(dry_run))
    write_json(resolved["contract_json"], contract)
    write_text(resolved["contract_md"], render_contract_markdown(contract))
    write_json(resolved["preflight_json"], preflight)
    write_text(resolved["preflight_md"], render_preflight_markdown(preflight))
    write_text(resolved["rollback_sql"], rollback_sql)
    return {key: str(path) for key, path in resolved.items()}


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def render_dry_run_markdown(plan: Mapping[str, Any]) -> str:
    quality = plan["quality"]
    return f"""# N1 Official Daily 20260526 Ingestion Dry-Run Plan

日期：2026-05-27
layer_role：`N1_ingestion`
状态：`{plan['result']}`

## Scope

- trade_date: `{TRADE_DATE}`
- source_batch_id: `{BATCH_ID}`
- stock source_version: `{SOURCE_VERSIONS['stock']}`
- index source_version: `{SOURCE_VERSIONS['index']}`
- board source_version: `{SOURCE_VERSIONS['board']}`

## Expected Rows

```text
stock active universe = {EXPECTED_SCOPE['stock_active_universe']}
fixed 9 index = {EXPECTED_SCOPE['fixed_9_index']}
board total = {EXPECTED_SCOPE['board_total']}
board 881 required coverage = {EXPECTED_SCOPE['board_881_required']}
total daily fact rows = {EXPECTED_SCOPE['total_daily_fact_rows']}
```

## Current N1 Fact

```json
{json.dumps(plan['current_n1_fact'], ensure_ascii=False, indent=2)}
```

## Missing Official Daily

```json
{json.dumps(plan['missing_official_daily'], ensure_ascii=False, indent=2)}
```

## Source Fetch Plan

本计划不执行外部拉取。未来 execute 才允许在 final gate 下使用：

- stock: Tushare daily + adj_factor proof
- index: TDX/Mootdx preferred; Tushare index_daily fallback
- board: TDX/Mootdx board daily

## Quality

```text
P0/P1/P2 = {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}
```

## Boundary

不写 PostgreSQL、不写 Parquet、不改 active_source_version、不进入 N2-N6、不启动 worker。
"""


def render_contract_markdown(contract: Mapping[str, Any]) -> str:
    return f"""# N1 Official Daily 20260526 Ingestion Execute Contract

日期：2026-05-27
layer_role：`N1_ingestion`
状态：`{contract['result']}`

## Identity

```text
source_batch_id = {BATCH_ID}
stock source_version = {SOURCE_VERSIONS['stock']}
index source_version = {SOURCE_VERSIONS['index']}
board source_version = {SOURCE_VERSIONS['board']}
```

## Future Execute Flags

```bash
--execute --user-confirmed --source-fetch-enabled --postgres-commit-enabled
```

## Data Source Contract

- stock: Tushare daily + adj_factor proof
- index: TDX/Mootdx preferred; Tushare index_daily fallback
- board: TDX/Mootdx board daily
- initial execute: PostgreSQL only

禁止用 N3 snapshot、C2/C2B summary、C3 outbox、旧系统或手工数据替代 official daily。

## Future Write Scope

```json
{json.dumps(contract['future_write_scope']['allowed_tables'], ensure_ascii=False, indent=2)}
```

## Rollback

Rollback SQL: `{DEFAULT_PATHS['rollback_sql']}`

按 trade_date/source_batch_id/source_version 精确清理；不碰 calendar patch，不碰 N2-N6，不碰事件队列，不碰归档文件。
"""


def render_preflight_markdown(preflight: Mapping[str, Any]) -> str:
    quality = preflight["quality"]
    return f"""# N1 Official Daily 20260526 Ingestion Execute Preflight

日期：2026-05-27
layer_role：`N1_ingestion`
状态：`{preflight['result']}`

## Summary

```text
trade_date = {TRADE_DATE}
source_batch_id = {BATCH_ID}
blocked = {preflight['blocked']}
blockers = {', '.join(preflight['blockers']) if preflight['blockers'] else 'none'}
P0/P1/P2 = {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}
runner_readiness = {preflight['runner_readiness']}
execute_authorized = false
```

## Baseline

```json
{json.dumps(preflight['baseline'], ensure_ascii=False, indent=2)}
```

## Next Gate

本 preflight 不授权 execute。下一步如继续，需要另开 20260526 official daily execute runner/source fetch/commit gate。
"""


def normalize_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): normalize_jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value
