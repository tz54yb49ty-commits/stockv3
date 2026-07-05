"""Generic N1 trade-calendar patch wrapper.

The core patch implementation lives in :mod:`trade_calendar_patch`. This module
only parameterizes the date-specific constants so a new trade-date patch can use
the same guarded preflight/execute path without copying a dedicated module.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterator, Mapping

import psycopg
from psycopg.rows import dict_row

from ashare_v3.ingestion import trade_calendar_patch as base


ALLOWED_WRITE_TABLES = base.ALLOWED_WRITE_TABLES
FORBIDDEN_WRITE_TABLES = base.FORBIDDEN_WRITE_TABLES
DEFAULT_DSN = base.DEFAULT_DSN


class CalendarPatchGenericBlocked(RuntimeError):
    """Raised when a generic calendar patch safety gate is not open."""


@dataclass(frozen=True)
class TradeCalendarPatchConfig:
    trade_date: str
    expected_prev_trade_date: str
    fallback_next_trade_date: str
    exchange: str = "SSE"
    source_batch_id: str | None = None
    source_version: str | None = None
    preflight_json_path: str | None = None
    preflight_markdown_path: str | None = None
    rollback_sql_path: str | None = None

    @property
    def resolved_source_batch_id(self) -> str:
        return self.source_batch_id or f"trade_calendar_{self.trade_date}_patch_v1"

    @property
    def resolved_source_version(self) -> str:
        return self.source_version or self.resolved_source_batch_id

    @property
    def scope_key(self) -> str:
        return f"{self.exchange}:{self.trade_date}"

    @property
    def resolved_preflight_json_path(self) -> str:
        return self.preflight_json_path or f"docs/N1_trade_calendar_{self.trade_date}_patch_preflight.json"

    @property
    def resolved_preflight_markdown_path(self) -> str:
        return self.preflight_markdown_path or f"docs/N1_TRADE_CALENDAR_{self.trade_date}_PATCH_PREFLIGHT.md"

    @property
    def resolved_rollback_sql_path(self) -> str:
        return self.rollback_sql_path or f"sql/N1_trade_calendar_{self.trade_date}_patch_rollback.sql"


@contextmanager
def patched_base_context(config: TradeCalendarPatchConfig) -> Iterator[None]:
    names = (
        "TRADE_DATE",
        "EXCHANGE",
        "PATCH_BATCH_ID",
        "PATCH_SOURCE_VERSION",
        "PATCH_SCOPE_KEY",
        "EXPECTED_PREV_TRADE_DATE",
        "DEFAULT_FALLBACK_NEXT_TRADE_DATE",
        "DEFAULT_PREFLIGHT_JSON_PATH",
        "DEFAULT_PREFLIGHT_MARKDOWN_PATH",
        "DEFAULT_ROLLBACK_SQL_PATH",
    )
    old_values = {name: getattr(base, name) for name in names}
    try:
        base.TRADE_DATE = config.trade_date
        base.EXCHANGE = config.exchange
        base.PATCH_BATCH_ID = config.resolved_source_batch_id
        base.PATCH_SOURCE_VERSION = config.resolved_source_version
        base.PATCH_SCOPE_KEY = config.scope_key
        base.EXPECTED_PREV_TRADE_DATE = config.expected_prev_trade_date
        base.DEFAULT_FALLBACK_NEXT_TRADE_DATE = config.fallback_next_trade_date
        base.DEFAULT_PREFLIGHT_JSON_PATH = config.resolved_preflight_json_path
        base.DEFAULT_PREFLIGHT_MARKDOWN_PATH = config.resolved_preflight_markdown_path
        base.DEFAULT_ROLLBACK_SQL_PATH = config.resolved_rollback_sql_path
        yield
    finally:
        for name, value in old_values.items():
            setattr(base, name, value)


def normalize_jsonable(value: Any) -> Any:
    return base.normalize_jsonable(value)


def quality_item(
    gate_name: str,
    *,
    severity: str,
    status: str,
    expected_value: str,
    actual_value: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return base.quality_item(
        gate_name,
        severity=severity,
        status=status,
        expected_value=expected_value,
        actual_value=actual_value,
        details=details,
    )


def count_quality(items: list[dict[str, Any]]) -> dict[str, int]:
    return base.count_quality(items)


def previous_calendar_chain_status(config: TradeCalendarPatchConfig, snapshot: Mapping[str, Any]) -> tuple[bool, str]:
    for row in snapshot.get("calendar_window") or []:
        if str(row.get("trade_date") or "") != config.expected_prev_trade_date:
            continue
        if str(row.get("exchange") or config.exchange) != config.exchange:
            continue
        actual = str(row.get("next_trade_date") or "")
        return bool(row.get("is_open")) and actual == config.trade_date, actual
    return False, ""


def normalize_report(
    *,
    config: TradeCalendarPatchConfig,
    report: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = normalize_jsonable(report)
    normalized["stage"] = f"N1 trade calendar {config.trade_date} patch preflight"
    normalized["trade_date"] = config.trade_date
    normalized["exchange"] = config.exchange
    normalized["scope_key"] = config.scope_key
    normalized["rollback_sql_path"] = config.resolved_rollback_sql_path

    patch = normalized.get("patch") or {}
    patch["source_batch_id"] = config.resolved_source_batch_id
    patch["source_version"] = config.resolved_source_version
    normalized["patch"] = patch

    if (normalized.get("fallback") or {}).get("used"):
        for item in (normalized.get("quality") or {}).get("items") or []:
            if item.get("gate_name") == "manual_calendar_patch_used":
                item["actual_value"] = f"manual fallback from {config.expected_prev_trade_date} next_trade_date"
                item["details"] = {
                    "patch_source": "previous_calendar_next_trade_date",
                    "evidence": f"{config.expected_prev_trade_date}.next_trade_date={config.trade_date}",
                }

    passed, actual_next = previous_calendar_chain_status(config, snapshot)
    quality = normalized.setdefault("quality", {})
    items = list(quality.get("items") or [])
    items.append(
        quality_item(
            "previous_calendar_next_trade_date",
            severity="P0",
            status="passed" if passed else "failed",
            expected_value=f"{config.expected_prev_trade_date}.next_trade_date={config.trade_date}",
            actual_value=actual_next or "missing previous calendar row",
            details={
                "previous_trade_date": config.expected_prev_trade_date,
                "trade_date": config.trade_date,
            },
        )
    )

    quality_counts = count_quality(items)
    blockers = sorted(set(normalized.get("blockers") or []))
    if not passed:
        blockers.append("previous_next_trade_date_mismatch")
        blockers = sorted(set(blockers))
    result = "PREFLIGHT_BLOCKED" if blockers or quality_counts["P0"] else "PREFLIGHT_PASS"

    quality["items"] = items
    quality["p0_count"] = quality_counts["P0"]
    quality["p1_count"] = quality_counts["P1"]
    quality["p2_count"] = quality_counts["P2"]
    normalized["quality"] = quality
    normalized["blockers"] = blockers
    normalized["result"] = result
    normalized["blocked"] = result != "PREFLIGHT_PASS"
    return normalize_jsonable(normalized)


def build_calendar_patch_preflight(
    *,
    config: TradeCalendarPatchConfig,
    snapshot: Mapping[str, Any],
    source_result: Mapping[str, Any],
    allow_minimal_fallback: bool,
    execute_requested: bool = False,
    user_confirmed: bool = False,
    postgres_commit_enabled: bool = False,
) -> dict[str, Any]:
    with patched_base_context(config):
        report = base.build_calendar_patch_preflight(
            snapshot=snapshot,
            source_result=source_result,
            allow_minimal_fallback=allow_minimal_fallback,
            execute_requested=execute_requested,
            user_confirmed=user_confirmed,
            postgres_commit_enabled=postgres_commit_enabled,
            rollback_sql_path=config.resolved_rollback_sql_path,
        )
    return normalize_report(config=config, report=report, snapshot=snapshot)


def validate_execute_request(
    *,
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> None:
    try:
        base.validate_execute_request(
            execute_requested=execute_requested,
            user_confirmed=user_confirmed,
            postgres_commit_enabled=postgres_commit_enabled,
        )
    except base.CalendarPatchBlocked as exc:
        raise CalendarPatchGenericBlocked(str(exc)) from exc


def execute_patch_transaction(
    *,
    config: TradeCalendarPatchConfig,
    conn: Any,
    report: Mapping[str, Any],
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    try:
        with patched_base_context(config):
            result = base.execute_patch_transaction(
                conn,
                report=report,
                execute_requested=execute_requested,
                user_confirmed=user_confirmed,
                postgres_commit_enabled=postgres_commit_enabled,
            )
    except base.CalendarPatchBlocked as exc:
        raise CalendarPatchGenericBlocked(str(exc)) from exc
    return normalize_jsonable(result)


def fetch_tushare_trade_calendar_source(
    *,
    config: TradeCalendarPatchConfig,
    token: str | None = None,
) -> dict[str, Any]:
    with patched_base_context(config):
        return base.fetch_tushare_trade_calendar_source(trade_date=config.trade_date, token=token)


def build_snapshot_from_db(*, config: TradeCalendarPatchConfig, dsn: str) -> dict[str, Any]:
    with patched_base_context(config):
        snapshot = base.build_snapshot_from_db(
            dsn=dsn,
            trade_date=config.trade_date,
            batch_id=config.resolved_source_batch_id,
        )

    existing_dates = {str(row.get("trade_date") or "") for row in snapshot.get("calendar_window") or []}
    if config.expected_prev_trade_date not in existing_dates:
        with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT trade_date, exchange, is_open, prev_trade_date, next_trade_date,
                           source, source_batch_id, source_version, updated_at
                    FROM common_trade_calendar
                    WHERE trade_date = %s
                    ORDER BY exchange
                    """,
                    (config.expected_prev_trade_date,),
                )
                snapshot.setdefault("calendar_window", []).extend(cur.fetchall())
    snapshot["calendar_window"] = sorted(
        normalize_jsonable(snapshot.get("calendar_window") or []),
        key=lambda row: (str(row.get("trade_date") or ""), str(row.get("exchange") or "")),
    )
    return normalize_jsonable(snapshot)


def write_preflight_files(report: Mapping[str, Any], *, json_path: str, markdown_path: str) -> None:
    Path(json_path).parent.mkdir(parents=True, exist_ok=True)
    Path(markdown_path).parent.mkdir(parents=True, exist_ok=True)
    Path(json_path).write_text(json.dumps(normalize_jsonable(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(markdown_path).write_text(render_preflight_markdown(report), encoding="utf-8")


def render_preflight_markdown(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    patch = report.get("patch") or {}
    row = patch.get("calendar_row") or {}
    return "\n".join(
        [
            f"# N1 Trade Calendar {report.get('trade_date')} Patch Preflight",
            "",
            f"result: `{report.get('result')}`",
            f"layer_role: `{report.get('layer_role')}`",
            f"trade_date: `{report.get('trade_date')}`",
            f"source_batch_id: `{patch.get('source_batch_id')}`",
            f"source_version: `{patch.get('source_version')}`",
            f"rollback_sql_path: `{report.get('rollback_sql_path')}`",
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
