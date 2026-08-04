#!/usr/bin/env python3
"""Run one fail-closed current-day N5 trigger-status forwarding tick."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from ashare_v3.events.models import N5_TRIGGER_STATUS_MESSAGE_TYPES
from ashare_v3.runtime.bounded_worker_control import (
    SingletonLockHeld,
    acquire_global_chain_lock,
    atomic_write_json,
)
from ashare_v3.runtime.intraday_worker_lineage import (
    ASIA_SHANGHAI,
    LineageConfigError,
    load_intraday_worker_lineage_config,
)
from scripts.run_n5_trigger_status_forward_once import (
    N5TriggerStatusForwardWriteAmbiguous,
    run_n5_trigger_status_forward_once,
)


POLICY_ID = "n5_n6_trigger_status_scheduled_convergence_30s_v1"
CONSUMER_NAME = "n5_trigger_status_forward_current_v1"
DEFAULT_DSN = os.environ.get(
    "ASHARE_V3_POSTGRES_DSN",
    "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3",
)
MAX_EVENTS_LIMIT = 5000
MAX_RUNTIME_SECONDS_LIMIT = 20.0
HISTORY_MAX_LINES = 500
ALLOWED_EVENT_TYPES = frozenset(N5_TRIGGER_STATUS_MESSAGE_TYPES)
FORBIDDEN_WRITE_RESULT_KEYS = (
    "common_action_event",
    "common_action_tracking_state",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lineage-config", required=True)
    parser.add_argument("--consumer-name", required=True)
    parser.add_argument("--max-events", type=int, required=True)
    parser.add_argument("--max-runtime-seconds", type=float, required=True)
    parser.add_argument("--singleton-lock-path", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json-report-path", required=True)
    parser.add_argument("--history-path", required=True)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    return parser


def run_n5_trigger_status_forward_current_once(
    argv: Sequence[str] | None = None,
    *,
    now_provider: Callable[[], datetime] | None = None,
    lineage_loader: Callable[[str | Path], Mapping[str, Any]] = load_intraday_worker_lineage_config,
    authority_reader: Callable[[str, str, float], Mapping[str, Any]] | None = None,
    core_runner: Callable[[Sequence[str]], Mapping[str, Any]] = run_n5_trigger_status_forward_once,
    lock_acquirer: Callable[..., Any] = acquire_global_chain_lock,
    report_writer: Callable[[str | Path, Mapping[str, Any]], None] = atomic_write_json,
) -> dict[str, Any]:
    args = build_arg_parser().parse_args(list(argv) if argv is not None else None)
    now = (now_provider or (lambda: datetime.now(ASIA_SHANGHAI)))()
    if now.tzinfo is None:
        now = now.replace(tzinfo=ASIA_SHANGHAI)
    now = now.astimezone(ASIA_SHANGHAI)
    local_trade_date = now.strftime("%Y%m%d")
    report = _base_report(args, now, local_trade_date)

    validation_error = _validate_args(args)
    if validation_error:
        return _finalize(
            report,
            result="BLOCKED",
            verdict="BLOCKED_INVALID_ARGUMENTS",
            reason=validation_error,
            args=args,
            report_writer=report_writer,
        )

    try:
        with lock_acquirer(
            args.singleton_lock_path,
            metadata={"policy_id": POLICY_ID, "consumer_name": CONSUMER_NAME},
        ):
            unresolved_incident = _unresolved_incident(Path(args.json_report_path))
            if unresolved_incident:
                return _finalize(
                    report,
                    result="BLOCKED",
                    verdict="BLOCKED_PRIOR_COMMIT_UNKNOWN",
                    reason=str(unresolved_incident["reason"]),
                    args=args,
                    report_writer=report_writer,
                    failure_phase="write",
                    requires_post_check=True,
                    incident_id=str(unresolved_incident["incident_id"]),
                    incident_path=str(unresolved_incident["incident_path"]),
                )

            try:
                lineage = dict(lineage_loader(args.lineage_config))
            except (LineageConfigError, OSError, ValueError, TypeError) as exc:
                return _finalize(
                    report,
                    result="BLOCKED",
                    verdict="BLOCKED_LINEAGE_INVALID",
                    reason=f"{type(exc).__name__}:{exc}",
                    args=args,
                    report_writer=report_writer,
                )
            report["lineage"] = {
                "path": str(args.lineage_config),
                "for_trade_date": str(lineage.get("for_trade_date") or ""),
                "source_trade_date": str(lineage.get("source_trade_date") or ""),
                "n4_context_run_id": str(lineage.get("n4_context_run_id") or ""),
            }

            try:
                authority = dict(
                    (authority_reader or _read_open_date_and_authority)(
                        args.dsn,
                        local_trade_date,
                        args.max_runtime_seconds,
                    )
                )
            except Exception as exc:
                return _finalize(
                    report,
                    result="BLOCKED",
                    verdict="BLOCKED_READ_ONLY_PREFLIGHT",
                    reason=f"{type(exc).__name__}:{exc}",
                    args=args,
                    report_writer=report_writer,
                )

            calendar_rows = int(authority.get("calendar_rows") or 0)
            is_open = bool(authority.get("is_open"))
            source_run_ids = sorted(
                {
                    str(run_id).strip()
                    for run_id in (authority.get("source_run_ids") or [])
                    if str(run_id).strip()
                }
            )
            report["date_authority"] = {
                "calendar_rows": calendar_rows,
                "is_open": is_open,
                "action_eligible_source_run_ids": source_run_ids,
                "action_eligible_authority_count": len(source_run_ids),
            }
            if calendar_rows == 0 or not is_open:
                return _finalize(
                    report,
                    result="NOOP",
                    verdict="NOOP_CLOSED_DATE",
                    reason="local_trade_date_not_open",
                    args=args,
                    report_writer=report_writer,
                )

            lineage_trade_date = str(lineage.get("for_trade_date") or "")
            if lineage_trade_date != local_trade_date:
                return _finalize(
                    report,
                    result="BLOCKED",
                    verdict="BLOCKED_DATE_DRIFT",
                    reason=f"lineage_for_trade_date={lineage_trade_date}",
                    args=args,
                    report_writer=report_writer,
                )
            if len(source_run_ids) != 1:
                return _finalize(
                    report,
                    result="BLOCKED",
                    verdict="BLOCKED_ACTION_ELIGIBLE_AUTHORITY",
                    reason=f"authority_count={len(source_run_ids)}",
                    args=args,
                    report_writer=report_writer,
                )

            source_run_id = source_run_ids[0]
            action_run_id = f"n5_trigger_status_forward_current_{local_trade_date}_v1"
            core_argv = [
                "--for-trade-date",
                local_trade_date,
                "--source-eligible-action-run-id",
                source_run_id,
                "--action-run-id",
                action_run_id,
                "--consumer-name",
                args.consumer_name,
                "--max-events",
                str(args.max_events),
                "--max-runtime-seconds",
                _number_text(args.max_runtime_seconds),
                "--dsn",
                args.dsn,
            ]
            if args.execute:
                core_argv.extend(("--execute", "--user-confirmed"))
            report["action_run_id"] = action_run_id
            report["source_eligible_action_run_id"] = source_run_id
            report["core_argv"] = _redact_dsn(core_argv)

            try:
                core_result = dict(core_runner(core_argv))
            except N5TriggerStatusForwardWriteAmbiguous as exc:
                incident = _write_commit_unknown_incident(
                    Path(args.json_report_path),
                    report,
                    reason=str(exc),
                )
                return _finalize(
                    report,
                    result="COMMIT_UNKNOWN",
                    verdict="BLOCKED_COMMIT_UNKNOWN",
                    reason=str(exc),
                    args=args,
                    report_writer=report_writer,
                    failure_phase="write",
                    requires_post_check=True,
                    incident_id=str(incident["incident_id"]),
                    incident_path=str(incident["incident_path"]),
                )
            except Exception as exc:
                return _finalize(
                    report,
                    result="BLOCKED",
                    verdict="BLOCKED_CORE_PLAN_READ",
                    reason=f"{type(exc).__name__}:{exc}",
                    args=args,
                    report_writer=report_writer,
                    failure_phase="plan",
                )

            core_error = _validate_core_result(
                core_result,
                execute=args.execute,
                trade_date=local_trade_date,
                action_run_id=action_run_id,
                source_run_id=source_run_id,
            )
            report["core_result"] = _json_safe(core_result)
            if core_error:
                return _finalize(
                    report,
                    result="BLOCKED",
                    verdict="BLOCKED_CORE_RESULT_INVALID",
                    reason=core_error,
                    args=args,
                    report_writer=report_writer,
                )
            if str(core_result.get("verdict") or "").startswith("BLOCKED"):
                failure_phase = str(core_result.get("failure_phase") or "plan")
                return _finalize(
                    report,
                    result="BLOCKED",
                    verdict=(
                        "BLOCKED_CORE_PLAN_READ"
                        if failure_phase == "plan"
                        else "BLOCKED_CORE_RUNNER"
                    ),
                    reason=str(core_result.get("blocked_reason") or "core_runner_blocked"),
                    args=args,
                    report_writer=report_writer,
                    failure_phase=failure_phase,
                )
            written = int((core_result.get("write_result") or {}).get("common_event_outbox") or 0)
            return _finalize(
                report,
                result="PASS",
                verdict=(
                    "N5_TRIGGER_STATUS_FORWARD_CURRENT_EXECUTE_PASS"
                    if args.execute
                    else "N5_TRIGGER_STATUS_FORWARD_CURRENT_PLAN_ONLY_PASS"
                ),
                reason="bounded_tick_complete",
                args=args,
                report_writer=report_writer,
                written_count=written,
            )
    except SingletonLockHeld:
        return _finalize(
            report,
            result="NOOP",
            verdict="NOOP_SINGLETON_LOCK_HELD",
            reason="singleton_lock_held",
            args=args,
            report_writer=report_writer,
        )


def _validate_args(args: argparse.Namespace) -> str:
    if args.consumer_name != CONSUMER_NAME:
        return "consumer_name_must_be_n5_trigger_status_forward_current_v1"
    if not 0 < int(args.max_events) <= MAX_EVENTS_LIMIT:
        return "max_events_out_of_bounds"
    if not 0 < float(args.max_runtime_seconds) <= MAX_RUNTIME_SECONDS_LIMIT:
        return "max_runtime_seconds_out_of_bounds"
    if args.execute and not args.user_confirmed:
        return "execute_requires_user_confirmed"
    if not str(args.dsn or "").strip():
        return "dsn_required"
    if Path(args.json_report_path) == Path(args.history_path):
        return "report_and_history_paths_must_differ"
    return ""


def _read_open_date_and_authority(
    dsn: str,
    trade_date: str,
    max_runtime_seconds: float,
) -> dict[str, Any]:
    timeout_ms = max(1, int(float(max_runtime_seconds) * 1000))
    options = f"-c default_transaction_read_only=on -c statement_timeout={timeout_ms}"
    with psycopg.connect(
        dsn,
        row_factory=dict_row,
        options=options,
        connect_timeout=max(1, min(10, int(max_runtime_seconds))),
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS calendar_rows,
                   COALESCE(bool_or(is_open), false) AS is_open
            FROM common_trade_calendar
            WHERE trade_date = %s
            """,
            (trade_date,),
        )
        calendar = dict(cur.fetchone() or {})
        cur.execute(
            """
            SELECT source_run_id
            FROM common_event_outbox
            WHERE source_layer = 'N5_action'
              AND event_type = 'ActionEligible'
              AND trade_date = %s
              AND NULLIF(BTRIM(source_run_id), '') IS NOT NULL
            GROUP BY source_run_id
            ORDER BY source_run_id
            LIMIT 3
            """,
            (trade_date,),
        )
        source_run_ids = [str(row["source_run_id"]) for row in cur.fetchall()]
    return {
        "calendar_rows": int(calendar.get("calendar_rows") or 0),
        "is_open": bool(calendar.get("is_open")),
        "source_run_ids": source_run_ids,
    }


def _validate_core_result(
    result: Mapping[str, Any],
    *,
    execute: bool,
    trade_date: str,
    action_run_id: str,
    source_run_id: str,
) -> str:
    if "trigger_pct" in json.dumps(result, ensure_ascii=False, default=str):
        return "trigger_pct_forbidden"
    if str(result.get("verdict") or "").startswith("BLOCKED"):
        return ""
    expected_verdict = (
        "N5_TRIGGER_STATUS_FORWARD_EXECUTE_PASS"
        if execute
        else "N5_TRIGGER_STATUS_FORWARD_PLAN_ONLY"
    )
    if result.get("verdict") != expected_verdict:
        return "unexpected_core_verdict"
    exact = {
        "for_trade_date": trade_date,
        "action_run_id": action_run_id,
        "source_eligible_action_run_id": source_run_id,
        "consumer_name": CONSUMER_NAME,
        "scope_mode": "aggregate_day_action_run",
    }
    for key, value in exact.items():
        if result.get(key) != value:
            return f"core_{key}_mismatch"
    plan = result.get("plan") or {}
    if plan.get("action_events") or plan.get("tracking_updates") or plan.get("inbox_checkpoint_intent"):
        return "core_plan_contains_forbidden_effects"
    for event in plan.get("status_events") or []:
        if str(event.get("event_type") or "") not in ALLOWED_EVENT_TYPES:
            return "core_plan_contains_forbidden_event_type"
    boundary = result.get("boundary") or {}
    for key in (
        "common_action_event_written",
        "tracking_written",
        "common_event_inbox_written",
        "common_event_consumer_checkpoint_written",
        "n4_inbox_checkpoint_written",
        "n4_outbox_status_updated",
    ):
        if boundary.get(key) is not False:
            return f"core_boundary_{key}_must_be_false"
    write_result = result.get("write_result") or {}
    outbox_writes = int(write_result.get("common_event_outbox") or 0)
    if outbox_writes < 0 or (not execute and outbox_writes != 0):
        return "core_write_result_common_event_outbox_invalid"
    for key in FORBIDDEN_WRITE_RESULT_KEYS:
        if int(write_result.get(key) or 0) != 0:
            return f"core_write_result_{key}_must_be_zero"
    if write_result.get("n4_outbox_status_updated") is not False:
        return "core_write_result_n4_outbox_status_updated_must_be_false"
    return ""


def _incident_directory(report_path: Path) -> Path:
    return report_path.with_name(f"{report_path.stem}.incidents")


def _unresolved_incident(report_path: Path) -> dict[str, str] | None:
    incident_directory = _incident_directory(report_path)
    if not incident_directory.exists():
        return None
    for incident_path in sorted(incident_directory.glob("*.json")):
        try:
            payload = json.loads(incident_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "incident_id": incident_path.stem,
                "incident_path": str(incident_path),
                "reason": f"incident_unreadable:{type(exc).__name__}",
            }
        if bool(payload.get("requires_post_check")):
            return {
                "incident_id": str(payload.get("incident_id") or incident_path.stem),
                "incident_path": str(incident_path),
                "reason": "unresolved_write_incident",
            }
    return None


def _write_commit_unknown_incident(
    report_path: Path,
    report: Mapping[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    created_at = datetime.now(ASIA_SHANGHAI)
    incident_id = (
        "n5_trigger_status_write_ambiguity_"
        f"{created_at.strftime('%Y%m%dT%H%M%S%f%z')}_{uuid.uuid4().hex}"
    )
    incident_directory = _incident_directory(report_path)
    incident_directory.mkdir(parents=True, exist_ok=True)
    incident_path = incident_directory / f"{incident_id}.json"
    incident = {
        "incident_version": "n5-trigger-status-write-ambiguity-v1",
        "incident_id": incident_id,
        "incident_path": str(incident_path),
        "rolling_report_path": str(report_path),
        "policy_id": POLICY_ID,
        "layer_role": "N5_action",
        "created_at": created_at.isoformat(),
        "failure_phase": "write",
        "requires_post_check": True,
        "reason": reason,
        "local_trade_date": str(report.get("local_trade_date") or ""),
        "action_run_id": str(report.get("action_run_id") or ""),
        "source_eligible_action_run_id": str(
            report.get("source_eligible_action_run_id") or ""
        ),
        "core_argv": list(report.get("core_argv") or []),
        "execute_requested": bool(report.get("execute_requested")),
    }
    encoded = (
        json.dumps(incident, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n"
    ).encode("utf-8")
    tmp_path = incident_directory / f".{incident_id}.tmp.{os.getpid()}"
    try:
        with tmp_path.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, 0o444)
        os.link(tmp_path, incident_path)
        directory_fd = os.open(incident_directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return incident


def _base_report(args: argparse.Namespace, now: datetime, trade_date: str) -> dict[str, Any]:
    return {
        "policy_id": POLICY_ID,
        "layer_role": "N5_action",
        "started_at": now.isoformat(),
        "local_trade_date": trade_date,
        "execute_requested": bool(args.execute),
        "user_confirmed": bool(args.user_confirmed),
        "consumer_name": str(args.consumer_name),
        "bounded": {
            "max_events": int(args.max_events),
            "max_runtime_seconds": float(args.max_runtime_seconds),
        },
        "allowed_event_types": sorted(ALLOWED_EVENT_TYPES),
        "failure_phase": None,
        "requires_post_check": False,
        "incident_id": None,
        "incident_path": None,
        "business_writes": {
            "common_event_outbox_status_messages_only": 0,
            "common_action_event": 0,
            "common_action_tracking_state": 0,
            "common_event_inbox": 0,
            "common_event_consumer_checkpoint": 0,
            "n4_outbox_status_updates": 0,
        },
    }


def _finalize(
    report: dict[str, Any],
    *,
    result: str,
    verdict: str,
    reason: str,
    args: argparse.Namespace,
    report_writer: Callable[[str | Path, Mapping[str, Any]], None],
    failure_phase: str | None = None,
    requires_post_check: bool = False,
    written_count: int = 0,
    incident_id: str | None = None,
    incident_path: str | None = None,
) -> dict[str, Any]:
    report.update(
        {
            "result": result,
            "verdict": verdict,
            "reason": reason,
            "failure_phase": failure_phase,
            "requires_post_check": bool(requires_post_check),
            "incident_id": incident_id,
            "incident_path": incident_path,
            "written_count": int(written_count),
            "finished_at": datetime.now(ASIA_SHANGHAI).isoformat(),
        }
    )
    report["business_writes"]["common_event_outbox_status_messages_only"] = int(
        written_count
    )
    report_writer(args.json_report_path, report)
    _append_history(Path(args.history_path), report)
    return report


def _append_history(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    line = json.dumps(report, ensure_ascii=False, sort_keys=True, default=str)
    lines = [*existing[-(HISTORY_MAX_LINES - 1) :], line]
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _redact_dsn(argv: Sequence[str]) -> list[str]:
    redacted = list(argv)
    if "--dsn" in redacted:
        redacted[redacted.index("--dsn") + 1] = "<redacted>"
    return redacted


def _number_text(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def main(argv: Sequence[str] | None = None) -> int:
    result = run_n5_trigger_status_forward_current_once(argv)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    if result["result"] == "COMMIT_UNKNOWN":
        return 3
    if result["result"] == "BLOCKED":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
