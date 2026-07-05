"""N1 trade calendar patch preflight and guarded execute helpers."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row

from ashare_v3.ingestion.tushare_env import load_tushare_token
from psycopg.types.json import Jsonb


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
TRADE_DATE = "20260526"
EXCHANGE = "SSE"
PATCH_BATCH_ID = "trade_calendar_20260526_patch_v1"
PATCH_SOURCE_VERSION = PATCH_BATCH_ID
PATCH_SCOPE_KEY = f"{EXCHANGE}:{TRADE_DATE}"
EXPECTED_PREV_TRADE_DATE = "20260525"
DEFAULT_FALLBACK_NEXT_TRADE_DATE = "20260527"
DEFAULT_DSN = "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3"
DEFAULT_PREFLIGHT_JSON_PATH = "docs/N1_trade_calendar_20260526_patch_preflight.json"
DEFAULT_PREFLIGHT_MARKDOWN_PATH = "docs/N1_TRADE_CALENDAR_20260526_PATCH_PREFLIGHT.md"
DEFAULT_ROLLBACK_SQL_PATH = "sql/N1_trade_calendar_20260526_patch_rollback.sql"

ALLOWED_WRITE_TABLES = (
    "common_ingest_batch",
    "common_trade_calendar",
    "common_active_source_version",
    "common_quality_gate_result",
)
FORBIDDEN_WRITE_TABLES = (
    "stock_daily_bar_fact",
    "index_daily_bar_fact",
    "board_daily_bar_fact",
    "stock_daily_basic",
    "stock_financial_metrics_fact",
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_event_delivery_attempt",
    "Parquet",
    "N2/N3/N4/N5/N6",
    "worker",
    "old system",
    "real trading",
)


class CalendarPatchBlocked(RuntimeError):
    """Raised when the calendar patch safety gate is not open."""


def now_iso() -> str:
    return datetime.now(ASIA_SHANGHAI).isoformat()


def normalize_jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def quality_item(
    gate_name: str,
    *,
    severity: str,
    status: str,
    expected_value: str,
    actual_value: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "gate_name": gate_name,
        "severity": severity,
        "status": status,
        "expected_value": expected_value,
        "actual_value": actual_value,
        "details": dict(details or {}),
    }


def count_quality(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"P0": 0, "P1": 0, "P2": 0}
    for item in items:
        if item.get("status") == "passed":
            continue
        severity = str(item.get("severity") or "")
        if severity in counts:
            counts[severity] += 1
    return counts


def build_calendar_patch_preflight(
    *,
    snapshot: Mapping[str, Any],
    source_result: Mapping[str, Any],
    allow_minimal_fallback: bool,
    execute_requested: bool = False,
    user_confirmed: bool = False,
    postgres_commit_enabled: bool = False,
    rollback_sql_path: str = DEFAULT_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    blockers: list[str] = []
    quality: list[dict[str, Any]] = []

    target_rows = list(snapshot.get("target_calendar_rows") or [])
    active_rows = list(snapshot.get("target_active_rows") or [])
    batch_conflicts = list(snapshot.get("patch_batch_conflict") or [])
    active_conflicts = list(snapshot.get("patch_active_conflict") or [])
    quality_conflicts = int(snapshot.get("patch_quality_conflict_rows") or 0)

    add_gate(
        quality,
        blockers,
        "target_calendar_missing_before_patch",
        passed=not target_rows,
        severity="P0",
        expected="0 rows",
        actual=f"{len(target_rows)} rows",
        blocker="target_calendar_already_exists",
    )
    add_gate(
        quality,
        blockers,
        "active_trade_calendar_missing_before_patch",
        passed=not active_rows,
        severity="P0",
        expected="0 active rows",
        actual=f"{len(active_rows)} active rows",
        blocker="active_trade_calendar_conflict",
    )
    add_gate(
        quality,
        blockers,
        "patch_batch_absent",
        passed=not batch_conflicts,
        severity="P0",
        expected="0 batch conflicts",
        actual=f"{len(batch_conflicts)} batch conflicts",
        blocker="patch_batch_conflict",
    )
    add_gate(
        quality,
        blockers,
        "patch_active_conflict_absent",
        passed=not active_conflicts,
        severity="P0",
        expected="0 active conflicts",
        actual=f"{len(active_conflicts)} active conflicts",
        blocker="patch_active_conflict",
    )
    add_gate(
        quality,
        blockers,
        "patch_quality_conflict_absent",
        passed=quality_conflicts == 0,
        severity="P0",
        expected="0 quality rows",
        actual=str(quality_conflicts),
        blocker="patch_quality_conflict",
    )

    patch_row = select_tushare_patch_row(source_result)
    fallback_used = False
    if patch_row is None:
        if not allow_minimal_fallback:
            blockers.append("tushare_calendar_unavailable")
            quality.append(
                quality_item(
                    "tushare_trade_cal_available",
                    severity="P0",
                    status="failed",
                    expected_value="available target row",
                    actual_value=str(source_result.get("error") or "no target row"),
                    details={"allow_minimal_fallback": False},
                )
            )
        else:
            patch_row = build_minimal_fallback_row(snapshot)
            fallback_used = True
            quality.append(
                quality_item(
                    "manual_calendar_patch_used",
                    severity="P2",
                    status="warning",
                    expected_value="Tushare authoritative row",
                    actual_value="manual fallback from 20260525 next_trade_date",
                    details={
                        "patch_source": "previous_calendar_next_trade_date",
                        "evidence": "20260525.next_trade_date=20260526",
                    },
                )
            )
    else:
        quality.append(
            quality_item(
                "tushare_trade_cal_available",
                severity="P0",
                status="passed",
                expected_value="available target row",
                actual_value="available",
                details={"source": source_result.get("source") or "tushare.trade_cal"},
            )
        )

    if patch_row is not None:
        add_gate(
            quality,
            blockers,
            "calendar_target_open",
            passed=bool(patch_row.get("is_open")),
            severity="P0",
            expected="is_open=true",
            actual=f"is_open={patch_row.get('is_open')}",
            blocker="target_calendar_not_open",
        )
        add_gate(
            quality,
            blockers,
            "calendar_prev_trade_date",
            passed=str(patch_row.get("prev_trade_date") or "") == EXPECTED_PREV_TRADE_DATE,
            severity="P0",
            expected=EXPECTED_PREV_TRADE_DATE,
            actual=str(patch_row.get("prev_trade_date") or ""),
            blocker="prev_trade_date_mismatch",
        )
        add_gate(
            quality,
            blockers,
            "calendar_next_trade_date_present",
            passed=bool(patch_row.get("next_trade_date")),
            severity="P0",
            expected="non-empty next_trade_date",
            actual=str(patch_row.get("next_trade_date") or ""),
            blocker="next_trade_date_missing",
        )

    quality.append(
        quality_item(
            "calendar_patch_scope_limited",
            severity="P0",
            status="passed",
            expected_value=", ".join(ALLOWED_WRITE_TABLES),
            actual_value=", ".join(ALLOWED_WRITE_TABLES),
            details={"forbidden_tables": list(FORBIDDEN_WRITE_TABLES)},
        )
    )

    quality_counts = count_quality(quality)
    if quality_counts["P0"] > 0:
        blockers = sorted(set(blockers))
    result = "PREFLIGHT_BLOCKED" if blockers or quality_counts["P0"] else "PREFLIGHT_PASS"

    report = {
        "stage": "N1 trade calendar 20260526 patch preflight",
        "layer_role": "N1_ingestion",
        "result": result,
        "blocked": result != "PREFLIGHT_PASS",
        "blockers": blockers,
        "trade_date": TRADE_DATE,
        "exchange": EXCHANGE,
        "scope_key": PATCH_SCOPE_KEY,
        "patch": {
            "source_batch_id": PATCH_BATCH_ID,
            "source_version": PATCH_SOURCE_VERSION,
            "calendar_row": patch_row,
        },
        "tushare": {
            "available": bool(source_result.get("available") and select_tushare_patch_row(source_result)),
            "source": source_result.get("source") or "tushare.trade_cal",
            "error": source_result.get("error"),
            "row_count": len(source_result.get("rows") or []),
        },
        "fallback": {
            "allowed": bool(allow_minimal_fallback),
            "used": fallback_used,
            "requires_flag": "--allow-minimal-fallback",
        },
        "baseline": normalize_jsonable(snapshot),
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality,
        },
        "future_write_scope": {
            "allowed_tables": list(ALLOWED_WRITE_TABLES),
            "forbidden_tables": list(FORBIDDEN_WRITE_TABLES),
            "writes_postgres": True,
            "writes_parquet": False,
            "writes_daily_fact": False,
            "writes_outbox": False,
            "enters_n2_n3_n4_n5_n6": False,
            "worker_started": False,
        },
        "execute_contract": {
            "execute_requires": ["--execute", "--user-confirmed", "--postgres-commit-enabled"],
            "block_on_existing_calendar_row": True,
            "block_on_existing_active_source_version": True,
            "block_on_existing_batch_id": True,
            "single_transaction": True,
            "rollback_sql_path": rollback_sql_path,
        },
        "side_effects": {
            "read_only_database_checks": True,
            "tushare_trade_cal_checked": bool(source_result.get("checked", True)),
            "writes_postgres": False,
            "writes_parquet": False,
            "writes_daily_fact": False,
            "updates_active_source_version": False,
            "writes_outbox": False,
            "enters_n2_n3_n4_n5_n6": False,
            "worker_started": False,
            "old_system_touched": False,
            "real_trading": False,
        },
        "generated_at": now_iso(),
    }
    report["execute_authorized"] = bool(execute_requested and user_confirmed and postgres_commit_enabled)
    return normalize_jsonable(report)


def add_gate(
    items: list[dict[str, Any]],
    blockers: list[str],
    gate_name: str,
    *,
    passed: bool,
    severity: str,
    expected: str,
    actual: str,
    blocker: str,
) -> None:
    items.append(
        quality_item(
            gate_name,
            severity=severity,
            status="passed" if passed else "failed",
            expected_value=expected,
            actual_value=actual,
        )
    )
    if not passed and severity == "P0":
        blockers.append(blocker)


def select_tushare_patch_row(source_result: Mapping[str, Any]) -> dict[str, Any] | None:
    if not source_result.get("available"):
        return None
    for row in source_result.get("rows") or []:
        if str(row.get("trade_date") or "") == TRADE_DATE and str(row.get("exchange") or "") == EXCHANGE:
            return normalize_patch_row(row, source="tushare.trade_cal.patch")
    return None


def normalize_patch_row(row: Mapping[str, Any], *, source: str) -> dict[str, Any]:
    return {
        "trade_date": TRADE_DATE,
        "exchange": EXCHANGE,
        "is_open": bool(row.get("is_open")),
        "prev_trade_date": str(row.get("prev_trade_date") or ""),
        "next_trade_date": str(row.get("next_trade_date") or ""),
        "source": source,
        "source_batch_id": PATCH_BATCH_ID,
        "source_version": PATCH_SOURCE_VERSION,
        "raw_payload": normalize_jsonable(row.get("raw_payload") or row),
    }


def build_minimal_fallback_row(snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
    previous = None
    for row in snapshot.get("calendar_window") or []:
        if str(row.get("trade_date") or "") == EXPECTED_PREV_TRADE_DATE and row.get("next_trade_date") == TRADE_DATE:
            previous = row
            break
    if previous is None:
        return None
    return {
        "trade_date": TRADE_DATE,
        "exchange": EXCHANGE,
        "is_open": True,
        "prev_trade_date": EXPECTED_PREV_TRADE_DATE,
        "next_trade_date": DEFAULT_FALLBACK_NEXT_TRADE_DATE,
        "source": "manual.calendar_patch",
        "source_batch_id": PATCH_BATCH_ID,
        "source_version": PATCH_SOURCE_VERSION,
        "raw_payload": {
            "patch_source": "previous_calendar_next_trade_date",
            "evidence": previous,
            "quality_risk": "manual fallback used because Tushare trade_cal was unavailable",
        },
    }


def validate_execute_request(
    *,
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> None:
    if not execute_requested:
        raise CalendarPatchBlocked("calendar patch execute requires explicit --execute")
    if not user_confirmed:
        raise CalendarPatchBlocked("calendar patch execute requires explicit --user-confirmed")
    if not postgres_commit_enabled:
        raise CalendarPatchBlocked("calendar patch execute requires explicit --postgres-commit-enabled")


def execute_patch_transaction(
    conn: Any,
    *,
    report: Mapping[str, Any],
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    validate_execute_request(
        execute_requested=execute_requested,
        user_confirmed=user_confirmed,
        postgres_commit_enabled=postgres_commit_enabled,
    )
    if report.get("result") != "PREFLIGHT_PASS":
        raise CalendarPatchBlocked("calendar patch execute requires PREFLIGHT_PASS")
    calendar_row = (report.get("patch") or {}).get("calendar_row")
    if not calendar_row:
        raise CalendarPatchBlocked("calendar patch execute requires a calendar_row")

    quality_rows = [
        {
            "source_batch_id": PATCH_BATCH_ID,
            "source_version": PATCH_SOURCE_VERSION,
            "data_domain": "common",
            "data_type": "trade_calendar",
            "gate_name": item["gate_name"],
            "severity": item["severity"],
            "status": item["status"],
            "expected_value": item.get("expected_value"),
            "actual_value": item.get("actual_value"),
            "details": item.get("details") or {},
        }
        for item in (report.get("quality") or {}).get("items", [])
    ]
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO common_ingest_batch (
              batch_id, trade_date, data_domain, data_type, source, source_version,
              source_path, source_params, raw_hash, row_count, error_count,
              quality_gate_summary, rollback_strategy, status, started_at
            )
            VALUES (
              %(batch_id)s, %(trade_date)s, 'common', 'trade_calendar',
              %(source)s, %(source_version)s, NULL, %(source_params)s, %(raw_hash)s,
              1, 0, %(quality_gate_summary)s,
              'delete_by_source_batch_id_then_restore_previous_active_source_version',
              'running', now()
            )
            """,
            {
                "batch_id": PATCH_BATCH_ID,
                "trade_date": TRADE_DATE,
                "source": calendar_row["source"],
                "source_version": PATCH_SOURCE_VERSION,
                "source_params": jsonb({"trade_date": TRADE_DATE, "exchange": EXCHANGE}),
                "raw_hash": stable_hash(calendar_row.get("raw_payload") or {}),
                "quality_gate_summary": jsonb(report.get("quality") or {}),
            },
        )
        cur.execute(
            """
            INSERT INTO common_trade_calendar (
              trade_date, exchange, is_open, prev_trade_date, next_trade_date,
              source, source_batch_id, source_version, raw_payload
            )
            VALUES (
              %(trade_date)s, %(exchange)s, %(is_open)s, %(prev_trade_date)s, %(next_trade_date)s,
              %(source)s, %(source_batch_id)s, %(source_version)s, %(raw_payload)s
            )
            """,
            {
                **calendar_row,
                "raw_payload": jsonb(calendar_row.get("raw_payload") or {}),
            },
        )
        for item in quality_rows:
            cur.execute(
                """
                INSERT INTO common_quality_gate_result (
                  source_batch_id, source_version, data_domain, data_type, gate_name,
                  severity, status, expected_value, actual_value, details
                )
                VALUES (
                  %(source_batch_id)s, %(source_version)s, %(data_domain)s, %(data_type)s,
                  %(gate_name)s, %(severity)s, %(status)s, %(expected_value)s, %(actual_value)s,
                  %(details)s
                )
                """,
                {**item, "details": jsonb(item.get("details") or {})},
            )
        cur.execute(
            """
            INSERT INTO common_active_source_version (
              data_domain, data_type, scope_key, source_version, source_batch_id,
              previous_source_version, activated_at, activated_by
            )
            VALUES (
              'common', 'trade_calendar', %(scope_key)s, %(source_version)s, %(source_batch_id)s,
              NULL, now(), 'n1_calendar_patch'
            )
            """,
            {
                "scope_key": PATCH_SCOPE_KEY,
                "source_version": PATCH_SOURCE_VERSION,
                "source_batch_id": PATCH_BATCH_ID,
            },
        )
        cur.execute(
            """
            UPDATE common_ingest_batch
            SET status = 'passed', finished_at = now()
            WHERE batch_id = %(batch_id)s
            """,
            {"batch_id": PATCH_BATCH_ID},
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "result": "EXECUTE_PASS",
        "batch_id": PATCH_BATCH_ID,
        "source_version": PATCH_SOURCE_VERSION,
        "trade_date": TRADE_DATE,
        "allowed_write_tables": list(ALLOWED_WRITE_TABLES),
        "writes_postgres": True,
        "writes_parquet": False,
        "writes_daily_fact": False,
    }


def jsonb(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return Jsonb(value)
    return Jsonb(normalize_jsonable(value))


def stable_hash(value: Any) -> str:
    import hashlib

    payload = json.dumps(normalize_jsonable(value), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fetch_tushare_trade_calendar_source(*, trade_date: str = TRADE_DATE, token: str | None = None) -> dict[str, Any]:
    token = token or load_tushare_token()
    if not token:
        return {"available": False, "checked": True, "source": "tushare.trade_cal", "error": "TUSHARE_TOKEN missing", "rows": []}
    try:
        import tushare  # type: ignore

        center = datetime.strptime(trade_date, "%Y%m%d").date()
        start = (center - timedelta(days=20)).strftime("%Y%m%d")
        end = (center + timedelta(days=20)).strftime("%Y%m%d")
        pro = tushare.pro_api(token)
        frame = pro.trade_cal(
            exchange=EXCHANGE,
            start_date=start,
            end_date=end,
            fields="exchange,cal_date,is_open,pretrade_date",
        )
        records = frame.to_dict("records") if hasattr(frame, "to_dict") else []
        open_dates = sorted(str(row.get("cal_date") or "") for row in records if int(row.get("is_open") or 0) == 1)
        rows: list[dict[str, Any]] = []
        for raw in records:
            cal_date = str(raw.get("cal_date") or "")
            if cal_date != trade_date:
                continue
            next_trade_date = next((date for date in open_dates if date > trade_date), "")
            rows.append(
                {
                    "trade_date": cal_date,
                    "exchange": str(raw.get("exchange") or EXCHANGE),
                    "is_open": int(raw.get("is_open") or 0) == 1,
                    "prev_trade_date": str(raw.get("pretrade_date") or ""),
                    "next_trade_date": next_trade_date,
                    "raw_payload": normalize_jsonable(raw),
                }
            )
        return {
            "available": bool(rows),
            "checked": True,
            "source": "tushare.trade_cal",
            "error": None if rows else "target trade calendar row missing",
            "rows": rows,
        }
    except Exception as exc:
        return {"available": False, "checked": True, "source": "tushare.trade_cal", "error": exc.__class__.__name__, "rows": []}


def build_snapshot_from_db(*, dsn: str, trade_date: str = TRADE_DATE, batch_id: str = PATCH_BATCH_ID) -> dict[str, Any]:
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT trade_date, exchange, is_open, prev_trade_date, next_trade_date,
                       source, source_batch_id, source_version, raw_payload, updated_at
                FROM common_trade_calendar
                WHERE trade_date = %s
                ORDER BY exchange
                """,
                (trade_date,),
            )
            target_rows = cur.fetchall()
            cur.execute(
                """
                SELECT trade_date, exchange, is_open, prev_trade_date, next_trade_date,
                       source, source_batch_id, source_version, updated_at
                FROM common_trade_calendar
                WHERE trade_date BETWEEN '20260522' AND '20260527'
                ORDER BY trade_date, exchange
                """,
            )
            calendar_window = cur.fetchall()
            cur.execute(
                """
                SELECT data_domain, data_type, scope_key, source_version, source_batch_id,
                       previous_source_version, activated_at, activated_by
                FROM common_active_source_version
                WHERE data_domain = 'common'
                  AND data_type = 'trade_calendar'
                  AND scope_key = %s
                ORDER BY scope_key
                """,
                (PATCH_SCOPE_KEY,),
            )
            target_active_rows = cur.fetchall()
            cur.execute(
                """
                SELECT batch_id, trade_date, data_domain, data_type, source_version, row_count, status
                FROM common_ingest_batch
                WHERE batch_id = %s OR source_version = %s
                """,
                (batch_id, PATCH_SOURCE_VERSION),
            )
            patch_batch_conflict = cur.fetchall()
            cur.execute(
                """
                SELECT data_domain, data_type, scope_key, source_version, source_batch_id, previous_source_version
                FROM common_active_source_version
                WHERE source_batch_id = %s OR source_version = %s
                """,
                (batch_id, PATCH_SOURCE_VERSION),
            )
            patch_active_conflict = cur.fetchall()
            cur.execute(
                """
                SELECT count(*) AS rows
                FROM common_quality_gate_result
                WHERE source_batch_id = %s OR source_version = %s
                """,
                (batch_id, PATCH_SOURCE_VERSION),
            )
            quality_row = cur.fetchone()
            cur.execute("SELECT count(*) AS rows FROM common_event_outbox")
            outbox_row = cur.fetchone()
    return normalize_jsonable(
        {
            "target_calendar_rows": target_rows,
            "target_active_rows": target_active_rows,
            "patch_batch_conflict": patch_batch_conflict,
            "patch_active_conflict": patch_active_conflict,
            "patch_quality_conflict_rows": int((quality_row or {}).get("rows") or 0),
            "calendar_window": calendar_window,
            "outbox_rows_before": int((outbox_row or {}).get("rows") or 0),
        }
    )


def write_preflight_files(report: Mapping[str, Any], *, json_path: str, markdown_path: str) -> None:
    Path(json_path).write_text(json.dumps(normalize_jsonable(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(markdown_path).write_text(render_preflight_markdown(report), encoding="utf-8")


def render_preflight_markdown(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    patch = report.get("patch") or {}
    row = patch.get("calendar_row") or {}
    return "\n".join(
        [
            "# N1 Trade Calendar 20260526 Patch Preflight",
            "",
            f"result: `{report.get('result')}`",
            f"layer_role: `{report.get('layer_role')}`",
            f"trade_date: `{report.get('trade_date')}`",
            f"source_batch_id: `{patch.get('source_batch_id')}`",
            f"source_version: `{patch.get('source_version')}`",
            "",
            "## Calendar Row",
            "",
            "```json",
            json.dumps(row, ensure_ascii=False, indent=2, default=str),
            "```",
            "",
            "## Source",
            "",
            f"Tushare available: `{(report.get('tushare') or {}).get('available')}`",
            f"fallback used: `{(report.get('fallback') or {}).get('used')}`",
            "",
            "## Quality",
            "",
            f"P0/P1/P2: `{quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}`",
            "",
            "## Boundary",
            "",
            f"allowed write tables: `{', '.join((report.get('future_write_scope') or {}).get('allowed_tables') or [])}`",
            "daily fact writes: `false`",
            "Parquet writes: `false`",
            "outbox writes: `false`",
            "downstream layers touched: `false`",
            "",
        ]
    )
