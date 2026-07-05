#!/usr/bin/env python3
"""Run one bounded N4 polling pass through the smoke runner.

This wrapper is deliberately small: it creates per-pass identifiers and
artifact paths, then invokes the existing bounded smoke runner once when
explicitly authorized. It does not install schedulers, loop, or enter N5/N6.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ASIA_SHANGHAI = timezone(timedelta(hours=8))
DEFAULT_CHILD_CONTRACT_PATH = "docs/N4_WORKER_BOUNDED_POLLING_SCHEDULER_CONTRACT.json"
DEFAULT_WRAPPER_JSON_REPORT_PATH = "docs/N4_WORKER_BOUNDED_POLLING_RUN_ONCE_WRAPPER_REPORT.json"
DEFAULT_WRAPPER_MD_REPORT_PATH = "docs/N4_WORKER_BOUNDED_POLLING_RUN_ONCE_WRAPPER_REPORT.md"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="N4 bounded polling run-once wrapper.")
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--source-event-type", default="MarketSnapshotUpdated")
    parser.add_argument("--source-trade-date", required=True)
    parser.add_argument("--consumer-name", required=True)
    parser.add_argument("--max-events", type=int, default=50)
    parser.add_argument("--max-runtime-seconds", type=int, default=120)
    parser.add_argument("--heartbeat-interval-seconds", type=int, default=10)
    parser.add_argument("--docs-root", default="docs")
    parser.add_argument("--sql-root", default="sql")
    parser.add_argument("--tmp-root", default="tmp")
    parser.add_argument("--python-executable", default=default_child_python_executable())
    parser.add_argument("--child-contract-path", default=DEFAULT_CHILD_CONTRACT_PATH)
    parser.add_argument("--wrapper-json-report-path", default=DEFAULT_WRAPPER_JSON_REPORT_PATH)
    parser.add_argument("--wrapper-markdown-report-path", default=DEFAULT_WRAPPER_MD_REPORT_PATH)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    return parser


def run_bounded_poll_once(
    *,
    for_trade_date: str,
    source_run_id: str,
    source_event_type: str,
    source_trade_date: str,
    consumer_name: str,
    max_events: int = 50,
    max_runtime_seconds: int = 120,
    heartbeat_interval_seconds: int = 10,
    docs_root: str | Path = "docs",
    sql_root: str | Path = "sql",
    tmp_root: str | Path = "tmp",
    python_executable: str | None = None,
    child_contract_path: str = DEFAULT_CHILD_CONTRACT_PATH,
    wrapper_json_report_path: str | Path | None = None,
    wrapper_markdown_report_path: str | Path | None = None,
    now: datetime | None = None,
    execute: bool = False,
    user_confirmed: bool = False,
    command_runner: Callable[[list[str]], Any] | None = None,
    source_event_probe: Callable[[dict[str, Any]], Sequence[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Build and optionally execute a single bounded polling pass."""

    timestamp = _normalize_now(now)
    generated = build_dynamic_artifacts(
        for_trade_date=for_trade_date,
        timestamp=timestamp,
        docs_root=docs_root,
        sql_root=sql_root,
        tmp_root=tmp_root,
    )
    child_argv = build_child_argv(
        python_executable=python_executable or default_child_python_executable(),
        child_contract_path=child_contract_path,
        smoke_run_id=generated["smoke_run_id"],
        consumer_name=consumer_name,
        source_run_id=source_run_id,
        source_event_type=source_event_type,
        source_trade_date=source_trade_date,
        max_events=max_events,
        max_runtime_seconds=max_runtime_seconds,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        stop_file=generated["stop_file"],
        status_json=generated["status_json"],
        json_report_path=generated["json_report_path"],
        markdown_report_path=generated["markdown_report_path"],
        rollback_sql_path=generated["rollback_sql_path"],
    )

    report: dict[str, Any] = {
        "gate": "N4_WORKER_BOUNDED_POLLING_RUN_ONCE_WRAPPER_IMPLEMENTATION_GATE",
        "layer_role": "N4_trigger",
        "generated_at": timestamp.isoformat(),
        "execution_mode": "plan_only" if not execute else "execute",
        "execute_requested": bool(execute),
        "user_confirmed": bool(user_confirmed),
        "for_trade_date": for_trade_date,
        "source_run_id": source_run_id,
        "source_event_type": source_event_type,
        "source_trade_date": source_trade_date,
        "consumer_name": consumer_name,
        "bounded_controls": {
            "max_events": int(max_events),
            "max_runtime_seconds": int(max_runtime_seconds),
            "heartbeat_interval_seconds": int(heartbeat_interval_seconds),
            "internal_retry_loop_allowed": False,
            "long_running_worker_allowed": False,
        },
        "generated": generated,
        "child_runner_script": "scripts/run_n4_worker_bounded_smoke_once.py",
        "child_argv_for_execute": child_argv,
        "child_invoked": False,
        "child_returncode": None,
        "child_stdout": "",
        "child_stderr": "",
        "source_probe": {
            "performed": False,
            "accepted_source_event_count": None,
            "has_unprocessed_source_events": None,
            "uses_consumer_inbox_checkpoint_exclusion": True,
        },
        "forbidden_scope_proof": _forbidden_scope_proof(),
        "side_effects": {
            "scheduler_installed_or_enabled": False,
            "launchd_modified": False,
            "cron_modified": False,
            "database_written": None,
            "scoped_n4_database_writes": None,
            "trigger_run_written": None,
            "worker_started": False,
            "long_running_worker_started": False,
            "n3_outbox_status_updated": False,
            "n5_n6_entered": False,
            "delivery_push_voice_mobile": False,
            "sim_position_pnl_real_trade": False,
            "proposal_order_trade": False,
            "old_system_touched": False,
        },
    }

    blocked_reason = _confirmation_blocker(execute=execute, user_confirmed=user_confirmed)
    if blocked_reason:
        report["result"] = "BLOCKED"
        report["blocked_reason"] = blocked_reason
    elif not execute:
        report["result"] = "PLAN_ONLY"
    else:
        source_probe_context = {
            "for_trade_date": for_trade_date,
            "source_run_id": source_run_id,
            "source_event_type": source_event_type,
            "source_trade_date": source_trade_date,
            "consumer_name": consumer_name,
            "max_events": int(max_events),
            "probe_limit": 1,
        }
        try:
            probe = source_event_probe or _default_source_event_probe
            unprocessed_events = list(probe(source_probe_context))
        except Exception as exc:  # pragma: no cover - exercised by integration failure reports
            report["result"] = "BLOCKED"
            report["blocked_reason"] = f"source_event_probe_failed: {exc}"
            report["source_probe"] = {
                **source_probe_context,
                "performed": True,
                "accepted_source_event_count": None,
                "has_unprocessed_source_events": None,
                "uses_consumer_inbox_checkpoint_exclusion": True,
                "error": str(exc),
            }
            report["side_effects"].update(
                {
                    "database_written": False,
                    "scoped_n4_database_writes": False,
                    "trigger_run_written": False,
                }
            )
        else:
            report["source_probe"] = {
                **source_probe_context,
                "performed": True,
                "accepted_source_event_count": len(unprocessed_events),
                "has_unprocessed_source_events": bool(unprocessed_events),
                "uses_consumer_inbox_checkpoint_exclusion": True,
            }
            if not unprocessed_events:
                report["result"] = "NOOP_PASS"
                report["reason"] = "no_unprocessed_source_events"
                report["side_effects"].update(
                    {
                        "database_written": False,
                        "scoped_n4_database_writes": False,
                        "trigger_run_written": False,
                    }
                )
            else:
                _invoke_child_runner(report, child_argv, command_runner=command_runner)

    if wrapper_json_report_path:
        _write_text(wrapper_json_report_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    if wrapper_markdown_report_path:
        _write_text(wrapper_markdown_report_path, format_report_markdown(report))
    return report


def _invoke_child_runner(
    report: dict[str, Any],
    child_argv: list[str],
    *,
    command_runner: Callable[[list[str]], Any] | None,
) -> None:
    runner = command_runner or _default_command_runner
    completed = runner(child_argv)
    report["child_invoked"] = True
    report["child_returncode"] = int(getattr(completed, "returncode", 0) or 0)
    report["child_stdout"] = str(getattr(completed, "stdout", "") or "")
    report["child_stderr"] = str(getattr(completed, "stderr", "") or "")
    if report["child_returncode"] == 0:
        report["result"] = "EXECUTE_PASS"
    else:
        report["result"] = "BLOCKED"
        report["blocked_reason"] = "child_bounded_smoke_runner_failed"


def build_dynamic_artifacts(
    *,
    for_trade_date: str,
    timestamp: datetime,
    docs_root: str | Path,
    sql_root: str | Path,
    tmp_root: str | Path,
) -> dict[str, str]:
    id_timestamp = timestamp.strftime("%Y%m%dT%H%M%S%z")
    hhmmss = timestamp.strftime("%H%M%S")
    docs_root = Path(docs_root)
    sql_root = Path(sql_root)
    tmp_root = Path(tmp_root)
    return {
        "smoke_run_id": f"n4_worker_bounded_poll_{for_trade_date}_{id_timestamp}",
        "status_json": str(docs_root / f"N4_WORKER_BOUNDED_POLLING_{for_trade_date}_{hhmmss}_STATUS.json"),
        "json_report_path": str(docs_root / f"N4_WORKER_BOUNDED_POLLING_{for_trade_date}_{hhmmss}_EXECUTE_REPORT.json"),
        "markdown_report_path": str(docs_root / f"N4_WORKER_BOUNDED_POLLING_{for_trade_date}_{hhmmss}_EXECUTE_REPORT.md"),
        "rollback_sql_path": str(sql_root / f"N4_worker_bounded_polling_{for_trade_date}_{hhmmss}_rollback.sql"),
        "stop_file": str(tmp_root / f"n4_worker_bounded_polling_{for_trade_date}_{hhmmss}.stop"),
    }


def build_child_argv(
    *,
    python_executable: str,
    child_contract_path: str,
    smoke_run_id: str,
    consumer_name: str,
    source_run_id: str,
    source_event_type: str,
    source_trade_date: str,
    max_events: int,
    max_runtime_seconds: int,
    heartbeat_interval_seconds: int,
    stop_file: str,
    status_json: str,
    json_report_path: str,
    markdown_report_path: str,
    rollback_sql_path: str,
) -> list[str]:
    return [
        python_executable,
        "scripts/run_n4_worker_bounded_smoke_once.py",
        "--contract-path",
        child_contract_path,
        "--smoke-run-id",
        smoke_run_id,
        "--consumer-name",
        consumer_name,
        "--source-run-id",
        source_run_id,
        "--source-event-type",
        source_event_type,
        "--source-trade-date",
        source_trade_date,
        "--max-events",
        str(max_events),
        "--max-runtime-seconds",
        str(max_runtime_seconds),
        "--heartbeat-interval-seconds",
        str(heartbeat_interval_seconds),
        "--stop-file",
        stop_file,
        "--status-json",
        status_json,
        "--json-report-path",
        json_report_path,
        "--markdown-report-path",
        markdown_report_path,
        "--rollback-sql-path",
        rollback_sql_path,
        "--execute",
        "--user-confirmed",
    ]


def default_child_python_executable() -> str:
    """Return the wrapper runtime Python for launchd-safe child execution."""

    return sys.executable


def format_report_markdown(report: dict[str, Any]) -> str:
    generated = report.get("generated") if isinstance(report.get("generated"), dict) else {}
    lines = [
        "# N4 Worker Bounded Polling Run Once Wrapper Report",
        "",
        f"Result: `{report.get('result')}`",
        "",
        f"- smoke_run_id: `{generated.get('smoke_run_id')}`",
        f"- child_invoked: `{bool(report.get('child_invoked'))}`",
        f"- worker_started: `{False}`",
        f"- long_running_worker_started: `{False}`",
        f"- n5_n6_entered: `{False}`",
        f"- status_json: `{generated.get('status_json')}`",
        f"- json_report_path: `{generated.get('json_report_path')}`",
        f"- rollback_sql_path: `{generated.get('rollback_sql_path')}`",
    ]
    if report.get("blocked_reason"):
        lines.append(f"- blocked_reason: `{report.get('blocked_reason')}`")
    if report.get("reason"):
        lines.append(f"- reason: `{report.get('reason')}`")
    source_probe = report.get("source_probe") if isinstance(report.get("source_probe"), dict) else {}
    if source_probe:
        lines.extend(
            [
                f"- source_probe_performed: `{bool(source_probe.get('performed'))}`",
                f"- accepted_source_event_count: `{source_probe.get('accepted_source_event_count')}`",
                f"- has_unprocessed_source_events: `{source_probe.get('has_unprocessed_source_events')}`",
            ]
        )
    side_effects = report.get("side_effects") if isinstance(report.get("side_effects"), dict) else {}
    if side_effects:
        lines.extend(
            [
                f"- database_written: `{side_effects.get('database_written')}`",
                f"- scoped_n4_database_writes: `{side_effects.get('scoped_n4_database_writes')}`",
                f"- trigger_run_written: `{side_effects.get('trigger_run_written')}`",
            ]
        )
    return "\n".join(lines) + "\n"


def main(
    argv: list[str] | None = None,
    *,
    command_runner: Callable[[list[str]], Any] | None = None,
    now: datetime | None = None,
) -> int:
    args = build_arg_parser().parse_args(argv)
    report = run_bounded_poll_once(
        for_trade_date=args.for_trade_date,
        source_run_id=args.source_run_id,
        source_event_type=args.source_event_type,
        source_trade_date=args.source_trade_date,
        consumer_name=args.consumer_name,
        max_events=args.max_events,
        max_runtime_seconds=args.max_runtime_seconds,
        heartbeat_interval_seconds=args.heartbeat_interval_seconds,
        docs_root=args.docs_root,
        sql_root=args.sql_root,
        tmp_root=args.tmp_root,
        python_executable=args.python_executable,
        child_contract_path=args.child_contract_path,
        wrapper_json_report_path=args.wrapper_json_report_path,
        wrapper_markdown_report_path=args.wrapper_markdown_report_path,
        now=now,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
        command_runner=command_runner,
    )
    if report["result"] == "BLOCKED":
        return 2
    return 0


def _confirmation_blocker(*, execute: bool, user_confirmed: bool) -> str | None:
    if user_confirmed and not execute:
        return "missing --execute"
    if execute and not user_confirmed:
        return "missing --user-confirmed"
    return None


def _normalize_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(ASIA_SHANGHAI)
    if now.tzinfo is None:
        return now.replace(tzinfo=ASIA_SHANGHAI)
    return now.astimezone(ASIA_SHANGHAI)


def _default_command_runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=False, text=True, capture_output=True)


def _default_source_event_probe(context: dict[str, Any]) -> Sequence[Mapping[str, Any]]:
    """Read-only probe for unprocessed N3 source events for this consumer."""

    try:
        import psycopg

        from ashare_v3.trigger.worker_consumer import DEFAULT_DSN, fetch_source_events_for_smoke
    except Exception as exc:  # pragma: no cover - import failure is surfaced in wrapper report
        raise RuntimeError(f"source event probe dependency unavailable: {exc}") from exc

    with psycopg.connect(DEFAULT_DSN) as conn:
        conn.execute("BEGIN READ ONLY")
        return fetch_source_events_for_smoke(
            conn,
            source_run_id=str(context["source_run_id"]),
            source_event_type=str(context["source_event_type"]),
            source_trade_date=str(context["source_trade_date"]),
            max_events=int(context.get("probe_limit") or 1),
            consumer_name=str(context["consumer_name"]),
        )


def _forbidden_scope_proof() -> dict[str, bool]:
    return {
        "scheduler_installed_or_enabled": False,
        "launchd_modified": False,
        "cron_modified": False,
        "long_running_worker_started": False,
        "n3_outbox_status_updated": False,
        "n5_entered": False,
        "n6_entered": False,
        "delivery_push_voice_mobile": False,
        "sim_position_pnl_real_trade": False,
        "proposal_order_trade": False,
        "old_system_touched": False,
    }


def _write_text(path: str | Path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
