#!/usr/bin/env python3
"""Run one fail-closed current-day N6 trigger-status projection tick."""

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
from ashare_v3.user.trigger_status_projection import (
    CONSUMER_NAME,
    TriggerStatusProjectionError,
)
from scripts.run_n6_trigger_status_projection_once import run as run_projection_once


POLICY_ID = "n5_n6_trigger_status_scheduled_convergence_30s_v1"
DEFAULT_DSN = os.environ.get(
    "ASHARE_V3_POSTGRES_DSN",
    "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3",
)
MAX_LIMIT = 5000
READ_ONLY_TIMEOUT_SECONDS = 5
HISTORY_MAX_LINES = 500
COUNT_FIELDS = (
    "selected",
    "inserted",
    "updated",
    "invalidated",
    "ignored_action_outcomes",
    "replay_skipped",
)
FORBIDDEN_FIELD = "trigger" + "_pct"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lineage-config", required=True)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--singleton-lock-path", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json-report-path", required=True)
    parser.add_argument("--history-path", required=True)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    return parser


def run_n6_trigger_status_projection_current_once(
    argv: Sequence[str] | None = None,
    *,
    now_provider: Callable[[], datetime] | None = None,
    lineage_loader: Callable[[str | Path], Mapping[str, Any]] = load_intraday_worker_lineage_config,
    calendar_reader: Callable[[str, str], Mapping[str, Any]] | None = None,
    core_runner: Callable[[argparse.Namespace], Mapping[str, Any]] = run_projection_once,
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
                calendar = dict(
                    (calendar_reader or _read_open_date)(args.dsn, local_trade_date)
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

            calendar_rows = int(calendar.get("calendar_rows") or 0)
            is_open = bool(calendar.get("is_open"))
            report["date_authority"] = {
                "calendar_rows": calendar_rows,
                "is_open": is_open,
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

            projection_run_id = (
                f"n6_trigger_status_projection_current_{local_trade_date}_v1"
            )
            partition_key = f"trigger-status:{local_trade_date}"
            report["projection_run_id"] = projection_run_id
            report["partition_key"] = partition_key
            core_args = argparse.Namespace(
                dsn=args.dsn,
                for_trade_date=local_trade_date,
                projection_run_id=projection_run_id,
                limit=args.limit,
                execute=bool(args.execute),
                user_confirmed=bool(args.user_confirmed),
            )
            report["core_args"] = {
                "dsn": "<redacted>",
                "for_trade_date": local_trade_date,
                "projection_run_id": projection_run_id,
                "limit": int(args.limit),
                "execute": bool(args.execute),
                "user_confirmed": bool(args.user_confirmed),
            }

            try:
                core_result = dict(core_runner(core_args))
            except TriggerStatusProjectionError as exc:
                return _finalize(
                    report,
                    result="BLOCKED",
                    verdict="BLOCKED_CORE_PROJECTION_INPUT",
                    reason=f"{type(exc).__name__}:{exc}",
                    args=args,
                    report_writer=report_writer,
                    failure_phase="projection_rolled_back",
                )
            except Exception as exc:
                if args.execute:
                    try:
                        incident = _write_commit_unknown_incident(
                            Path(args.json_report_path),
                            report,
                            reason=f"{type(exc).__name__}:{exc}",
                        )
                    except Exception as incident_exc:
                        fallback_id = (
                            "n6_trigger_status_write_ambiguity_fallback_"
                            f"{local_trade_date}_{projection_run_id}"
                        )
                        return _finalize(
                            report,
                            result="COMMIT_UNKNOWN",
                            verdict="BLOCKED_COMMIT_UNKNOWN",
                            reason=(
                                f"{type(exc).__name__}:{exc};"
                                "incident_persistence_failed:"
                                f"{type(incident_exc).__name__}:{incident_exc}"
                            ),
                            args=args,
                            report_writer=report_writer,
                            failure_phase="write",
                            requires_post_check=True,
                            incident_id=fallback_id,
                            incident_path=str(args.json_report_path),
                        )
                    return _finalize(
                        report,
                        result="COMMIT_UNKNOWN",
                        verdict="BLOCKED_COMMIT_UNKNOWN",
                        reason=f"{type(exc).__name__}:{exc}",
                        args=args,
                        report_writer=report_writer,
                        failure_phase="write",
                        requires_post_check=True,
                        incident_id=str(incident["incident_id"]),
                        incident_path=str(incident["incident_path"]),
                    )
                return _finalize(
                    report,
                    result="BLOCKED",
                    verdict="BLOCKED_CORE_RUNNER_ERROR",
                    reason=f"{type(exc).__name__}:{exc}",
                    args=args,
                    report_writer=report_writer,
                    failure_phase="plan",
                )

            core_error = _validate_core_result(
                core_result,
                execute=bool(args.execute),
                trade_date=local_trade_date,
                projection_run_id=projection_run_id,
                limit=int(args.limit),
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
                return _finalize(
                    report,
                    result="BLOCKED",
                    verdict="BLOCKED_CORE_RUNNER",
                    reason=str(core_result.get("blocked_reason") or "core_runner_blocked"),
                    args=args,
                    report_writer=report_writer,
                )

            counts = {
                field: int(core_result.get(field) or 0) for field in COUNT_FIELDS
            }
            return _finalize(
                report,
                result="PASS",
                verdict=(
                    "N6_TRIGGER_STATUS_PROJECTION_CURRENT_EXECUTE_PASS"
                    if args.execute
                    else "N6_TRIGGER_STATUS_PROJECTION_CURRENT_PLAN_ONLY_PASS"
                ),
                reason="bounded_tick_complete",
                args=args,
                report_writer=report_writer,
                counts=counts,
                last_outbox_id=core_result.get("last_outbox_id"),
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
    if not 0 < int(args.limit) <= MAX_LIMIT:
        return "limit_out_of_bounds"
    if args.execute and not args.user_confirmed:
        return "execute_requires_user_confirmed"
    if not str(args.dsn or "").strip():
        return "dsn_required"
    if Path(args.json_report_path) == Path(args.history_path):
        return "report_and_history_paths_must_differ"
    return ""


def _read_open_date(dsn: str, trade_date: str) -> dict[str, Any]:
    timeout_ms = READ_ONLY_TIMEOUT_SECONDS * 1000
    options = f"-c default_transaction_read_only=on -c statement_timeout={timeout_ms}"
    with psycopg.connect(
        dsn,
        row_factory=dict_row,
        options=options,
        connect_timeout=READ_ONLY_TIMEOUT_SECONDS,
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
    return {
        "calendar_rows": int(calendar.get("calendar_rows") or 0),
        "is_open": bool(calendar.get("is_open")),
    }


def _validate_core_result(
    result: Mapping[str, Any],
    *,
    execute: bool,
    trade_date: str,
    projection_run_id: str,
    limit: int,
) -> str:
    if FORBIDDEN_FIELD in json.dumps(result, ensure_ascii=False, default=str):
        return "forbidden_field_present"
    if str(result.get("verdict") or "").startswith("BLOCKED"):
        return ""
    expected_verdict = (
        "N6_TRIGGER_STATUS_PROJECTION_EXECUTE_PASS"
        if execute
        else "N6_TRIGGER_STATUS_PROJECTION_PLAN_ONLY"
    )
    if result.get("verdict") != expected_verdict:
        return "unexpected_core_verdict"
    if result.get("consumer_name") != CONSUMER_NAME:
        return "core_consumer_name_mismatch"
    if bool(result.get("writes_database")) is not execute:
        return "core_writes_database_mismatch"
    if int(result.get("outbox_status_updates") or 0) != 0:
        return "core_outbox_status_updates_must_be_zero"
    if not execute:
        return ""
    if result.get("trade_date") != trade_date:
        return "core_trade_date_mismatch"
    if result.get("projection_run_id") != projection_run_id:
        return "core_projection_run_id_mismatch"
    for field in COUNT_FIELDS:
        try:
            count = int(result.get(field))
        except (TypeError, ValueError):
            return f"core_{field}_invalid"
        if count < 0:
            return f"core_{field}_negative"
    if int(result["selected"]) > limit:
        return "core_selected_exceeds_limit"
    last_outbox_id = result.get("last_outbox_id")
    if last_outbox_id is not None:
        try:
            if int(last_outbox_id) < 0:
                return "core_last_outbox_id_invalid"
        except (TypeError, ValueError):
            return "core_last_outbox_id_invalid"
    return ""


def _incident_directory(report_path: Path) -> Path:
    return report_path.with_name(f"{report_path.stem}.incidents")


def _unresolved_incident(report_path: Path) -> dict[str, str] | None:
    incident_directory = _incident_directory(report_path)
    if incident_directory.exists():
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
    try:
        rolling_report = json.loads(report_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return None
    if bool(rolling_report.get("requires_post_check")) or str(
        rolling_report.get("verdict") or ""
    ) == "BLOCKED_COMMIT_UNKNOWN":
        return {
            "incident_id": str(
                rolling_report.get("incident_id") or "rolling_report_write_fallback"
            ),
            "incident_path": str(
                rolling_report.get("incident_path") or report_path
            ),
            "reason": "unresolved_write_fallback_report",
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
        "n6_trigger_status_write_ambiguity_"
        f"{created_at.strftime('%Y%m%dT%H%M%S%f%z')}_{uuid.uuid4().hex}"
    )
    incident_directory = _incident_directory(report_path)
    incident_directory.mkdir(parents=True, exist_ok=True)
    os.chmod(incident_directory, 0o700)
    incident_path = incident_directory / f"{incident_id}.json"
    incident = {
        "incident_version": "n6-trigger-status-write-ambiguity-v1",
        "incident_id": incident_id,
        "incident_path": str(incident_path),
        "rolling_report_path": str(report_path),
        "policy_id": POLICY_ID,
        "layer_role": "N6_user",
        "created_at": created_at.isoformat(),
        "failure_phase": "write",
        "requires_post_check": True,
        "reason": reason,
        "local_trade_date": str(report.get("local_trade_date") or ""),
        "projection_run_id": str(report.get("projection_run_id") or ""),
        "partition_key": str(report.get("partition_key") or ""),
        "core_args": dict(report.get("core_args") or {}),
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


def _base_report(
    args: argparse.Namespace, now: datetime, trade_date: str
) -> dict[str, Any]:
    return {
        "policy_id": POLICY_ID,
        "layer_role": "N6_user",
        "started_at": now.isoformat(),
        "local_trade_date": trade_date,
        "execute_requested": bool(args.execute),
        "user_confirmed": bool(args.user_confirmed),
        "consumer_name": CONSUMER_NAME,
        "bounded": {"limit": int(args.limit)},
        "failure_phase": None,
        "requires_post_check": False,
        "incident_id": None,
        "incident_path": None,
        "write_boundary": {
            "allowed_tables": [
                "n6_trigger_status_current",
                "common_event_inbox",
                "common_event_consumer_checkpoint",
            ],
            "common_event_outbox_status_updates": 0,
            "signal_message_card_projection_writes": 0,
            "other_consumer_checkpoint_writes": 0,
            "n1_n5_writes": 0,
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
    counts: Mapping[str, int] | None = None,
    last_outbox_id: Any = None,
    incident_id: str | None = None,
    incident_path: str | None = None,
) -> dict[str, Any]:
    final_counts = {field: int((counts or {}).get(field, 0)) for field in COUNT_FIELDS}
    report.update(
        {
            "result": result,
            "verdict": verdict,
            "reason": reason,
            "failure_phase": failure_phase,
            "requires_post_check": bool(requires_post_check),
            "incident_id": incident_id,
            "incident_path": incident_path,
            "counts": final_counts,
            "last_outbox_id": last_outbox_id,
            "finished_at": datetime.now(ASIA_SHANGHAI).isoformat(),
        }
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


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def main(argv: Sequence[str] | None = None) -> int:
    result = run_n6_trigger_status_projection_current_once(argv)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    if result["result"] == "COMMIT_UNKNOWN":
        return 3
    if result["result"] == "BLOCKED":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
