"""N1 trade-calendar patch helpers scoped to 20260528."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from typing import Any, Iterator, Mapping

from ashare_v3.ingestion import trade_calendar_patch as base


TRADE_DATE = "20260528"
EXCHANGE = "SSE"
PATCH_BATCH_ID = "trade_calendar_20260528_patch_v1"
PATCH_SOURCE_VERSION = PATCH_BATCH_ID
PATCH_SCOPE_KEY = f"{EXCHANGE}:{TRADE_DATE}"
EXPECTED_PREV_TRADE_DATE = "20260527"
DEFAULT_FALLBACK_NEXT_TRADE_DATE = "20260529"
DEFAULT_DSN = base.DEFAULT_DSN
DEFAULT_PREFLIGHT_JSON_PATH = "docs/N1_trade_calendar_20260528_patch_preflight.json"
DEFAULT_PREFLIGHT_MARKDOWN_PATH = "docs/N1_TRADE_CALENDAR_20260528_PATCH_PREFLIGHT.md"
DEFAULT_ROLLBACK_SQL_PATH = "sql/N1_trade_calendar_20260528_patch_rollback.sql"

ALLOWED_WRITE_TABLES = base.ALLOWED_WRITE_TABLES
FORBIDDEN_WRITE_TABLES = base.FORBIDDEN_WRITE_TABLES


class CalendarPatch20260528Blocked(RuntimeError):
    """Raised when the 20260528 calendar patch safety gate is not open."""


@contextmanager
def _patched_base_context() -> Iterator[None]:
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
        base.TRADE_DATE = TRADE_DATE
        base.EXCHANGE = EXCHANGE
        base.PATCH_BATCH_ID = PATCH_BATCH_ID
        base.PATCH_SOURCE_VERSION = PATCH_SOURCE_VERSION
        base.PATCH_SCOPE_KEY = PATCH_SCOPE_KEY
        base.EXPECTED_PREV_TRADE_DATE = EXPECTED_PREV_TRADE_DATE
        base.DEFAULT_FALLBACK_NEXT_TRADE_DATE = DEFAULT_FALLBACK_NEXT_TRADE_DATE
        base.DEFAULT_PREFLIGHT_JSON_PATH = DEFAULT_PREFLIGHT_JSON_PATH
        base.DEFAULT_PREFLIGHT_MARKDOWN_PATH = DEFAULT_PREFLIGHT_MARKDOWN_PATH
        base.DEFAULT_ROLLBACK_SQL_PATH = DEFAULT_ROLLBACK_SQL_PATH
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


def _previous_calendar_chain_status(snapshot: Mapping[str, Any]) -> tuple[bool, str]:
    for row in snapshot.get("calendar_window") or []:
        if str(row.get("trade_date") or "") != EXPECTED_PREV_TRADE_DATE:
            continue
        if str(row.get("exchange") or EXCHANGE) != EXCHANGE:
            continue
        actual = str(row.get("next_trade_date") or "")
        return bool(row.get("is_open")) and actual == TRADE_DATE, actual
    return False, ""


def _normalize_report(report: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_jsonable(report)
    normalized["stage"] = "N1 trade calendar 20260528 patch preflight"
    normalized["trade_date"] = TRADE_DATE
    normalized["scope_key"] = PATCH_SCOPE_KEY
    normalized["rollback_sql_path"] = DEFAULT_ROLLBACK_SQL_PATH

    patch = normalized.get("patch") or {}
    patch["source_batch_id"] = PATCH_BATCH_ID
    patch["source_version"] = PATCH_SOURCE_VERSION
    normalized["patch"] = patch

    fallback = normalized.get("fallback") or {}
    if fallback.get("used"):
        for item in (normalized.get("quality") or {}).get("items") or []:
            if item.get("gate_name") == "manual_calendar_patch_used":
                item["details"] = {
                    "patch_source": "previous_calendar_next_trade_date",
                    "evidence": f"{EXPECTED_PREV_TRADE_DATE}.next_trade_date={TRADE_DATE}",
                }

    passed, actual_next = _previous_calendar_chain_status(snapshot)
    quality = normalized.setdefault("quality", {})
    items = list(quality.get("items") or [])
    items.append(
        quality_item(
            "previous_calendar_next_trade_date",
            severity="P0",
            status="passed" if passed else "failed",
            expected_value=f"{EXPECTED_PREV_TRADE_DATE}.next_trade_date={TRADE_DATE}",
            actual_value=actual_next or "missing previous calendar row",
            details={"previous_trade_date": EXPECTED_PREV_TRADE_DATE, "trade_date": TRADE_DATE},
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
    snapshot: Mapping[str, Any],
    source_result: Mapping[str, Any],
    allow_minimal_fallback: bool,
    execute_requested: bool = False,
    user_confirmed: bool = False,
    postgres_commit_enabled: bool = False,
    rollback_sql_path: str = DEFAULT_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    with _patched_base_context():
        report = base.build_calendar_patch_preflight(
            snapshot=snapshot,
            source_result=source_result,
            allow_minimal_fallback=allow_minimal_fallback,
            execute_requested=execute_requested,
            user_confirmed=user_confirmed,
            postgres_commit_enabled=postgres_commit_enabled,
            rollback_sql_path=rollback_sql_path,
        )
    return _normalize_report(report, snapshot)


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
        raise CalendarPatch20260528Blocked(str(exc)) from exc


def execute_patch_transaction(
    conn: Any,
    *,
    report: Mapping[str, Any],
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    try:
        with _patched_base_context():
            result = base.execute_patch_transaction(
                conn,
                report=report,
                execute_requested=execute_requested,
                user_confirmed=user_confirmed,
                postgres_commit_enabled=postgres_commit_enabled,
            )
    except base.CalendarPatchBlocked as exc:
        raise CalendarPatch20260528Blocked(str(exc)) from exc
    return normalize_jsonable(result)


def fetch_tushare_trade_calendar_source(*, trade_date: str = TRADE_DATE, token: str | None = None) -> dict[str, Any]:
    with _patched_base_context():
        return base.fetch_tushare_trade_calendar_source(trade_date=trade_date, token=token)


def build_snapshot_from_db(*, dsn: str, trade_date: str = TRADE_DATE, batch_id: str = PATCH_BATCH_ID) -> dict[str, Any]:
    with _patched_base_context():
        return base.build_snapshot_from_db(dsn=dsn, trade_date=trade_date, batch_id=batch_id)


def write_preflight_files(report: Mapping[str, Any], *, json_path: str, markdown_path: str) -> None:
    Path(json_path).write_text(json.dumps(normalize_jsonable(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(markdown_path).write_text(render_preflight_markdown(report), encoding="utf-8")


def render_preflight_markdown(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    patch = report.get("patch") or {}
    row = patch.get("calendar_row") or {}
    return "\n".join(
        [
            "# N1 Trade Calendar 20260528 Patch Preflight",
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
