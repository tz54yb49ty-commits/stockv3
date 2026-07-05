#!/usr/bin/env python3
"""Plan or run one source-run-scoped N5/N3T Fastlane post-close drain."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ashare_v3.runtime_control.n5_n3t_fastlane import (
    DEFAULT_PYTHON_EXECUTABLE,
    FASTLANE_SOURCE_RUN_SCOPED_DRAIN_PLAN_TYPE,
    build_fastlane_source_run_scoped_bounded_drain_plan,
)


DEFAULT_DSN = os.environ.get("ASHARE_V3_POSTGRES_DSN", "")
DEFAULT_CONSUMER_NAME = "n5_live_tracking_poller_v2_fastlane"


class FastlaneDrainBlocked(RuntimeError):
    """Raised when the bounded drain cannot proceed safely."""


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one source-run-scoped Fastlane bounded drain.")
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--consumer-name", default=DEFAULT_CONSUMER_NAME)
    parser.add_argument("--source-run-family", default="ordinary")
    parser.add_argument("--start-after", default="")
    parser.add_argument("--first-source-run", default="")
    parser.add_argument("--max-source-runs", type=int, required=True)
    parser.add_argument("--max-runtime-seconds", type=float, required=True)
    parser.add_argument("--working-directory", default=str(Path.cwd()))
    parser.add_argument("--n5-active-scope-artifact-dir", default="")
    parser.add_argument("--n3-c1-n3t-artifact-dir", default="")
    parser.add_argument("--python-executable", default=DEFAULT_PYTHON_EXECUTABLE)
    parser.add_argument("--plan-source-runs-json", default="")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--closeout-prestep-only", action="store_true")
    parser.add_argument("--source-trigger-run-id", default="")
    parser.add_argument("--action-run-id", default="")
    parser.add_argument("--source-metric-run-id", default="")
    parser.add_argument("--closeout-json-path", default="")
    parser.add_argument("--closeout-md-path", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        report = run_fastlane_source_run_scoped_bounded_drain_once(args)
    except FastlaneDrainBlocked as exc:
        report = {
            "artifact_type": FASTLANE_SOURCE_RUN_SCOPED_DRAIN_PLAN_TYPE,
            "result": "BLOCKED",
            "blocked_reason": str(exc),
            "writes_enabled": False,
            "database_written_by_orchestrator": False,
            "n4_outbox_updated": False,
            "n6_touched": False,
        }
        if args.json:
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        else:
            print(f"result=BLOCKED blocked_reason={report['blocked_reason']}")
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(
            f"result={report['result']} "
            f"selected_source_run_count={report.get('selected_source_run_count', 0)}"
        )
    return 0 if report.get("result") in {"PLAN_PASS", "EXECUTE_PASS"} else 2


def run_fastlane_source_run_scoped_bounded_drain_once(args: argparse.Namespace) -> dict[str, Any]:
    if args.execute and not args.user_confirmed:
        raise FastlaneDrainBlocked("execute_requires_user_confirmed")
    if args.closeout_prestep_only:
        return _run_closeout_prestep(args)
    candidate_source_runs = _load_candidate_source_runs(args)
    plan = build_fastlane_source_run_scoped_bounded_drain_plan(
        for_trade_date=args.for_trade_date,
        consumer_name=args.consumer_name,
        source_run_family=args.source_run_family,
        start_after=args.start_after,
        first_source_run=args.first_source_run,
        max_source_runs=args.max_source_runs,
        max_runtime_seconds=args.max_runtime_seconds,
        candidate_source_runs=candidate_source_runs,
        working_directory=args.working_directory,
        n5_active_scope_artifact_dir=args.n5_active_scope_artifact_dir,
        n3_c1_n3t_artifact_dir=args.n3_c1_n3t_artifact_dir,
        python_executable=args.python_executable,
    )
    if not args.execute:
        plan["writes_enabled"] = False
        plan["database_written_by_orchestrator"] = False
        return plan
    return _execute_drain_plan(plan, working_directory=Path(args.working_directory))


def _run_closeout_prestep(args: argparse.Namespace) -> dict[str, Any]:
    json_path = Path(str(args.closeout_json_path or ""))
    md_path = Path(str(args.closeout_md_path or ""))
    required = {
        "for_trade_date": args.for_trade_date,
        "consumer_name": args.consumer_name,
        "source_trigger_run_id": args.source_trigger_run_id,
        "action_run_id": args.action_run_id,
        "source_metric_run_id": args.source_metric_run_id,
        "closeout_json_path": str(json_path),
        "closeout_md_path": str(md_path),
    }
    missing = [key for key, value in required.items() if not str(value or "").strip()]
    if missing:
        raise FastlaneDrainBlocked(f"closeout_prestep_missing_required:{','.join(missing)}")

    target_hhmm = _extract_hhmm(args.source_metric_run_id, str(json_path)) or "unknown"
    report = _build_closeout_prestep_report(
        for_trade_date=str(args.for_trade_date),
        consumer_name=str(args.consumer_name),
        target_hhmm=target_hhmm,
        source_trigger_run_id=str(args.source_trigger_run_id),
        action_run_id=str(args.action_run_id),
        source_metric_run_id=str(args.source_metric_run_id),
        closeout_json_path=str(json_path),
        closeout_md_path=str(md_path),
    )
    if not args.execute:
        report["result"] = "PLAN_PASS"
        report["writes_enabled"] = False
        return report

    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_exists = json_path.exists()
    md_exists = md_path.exists()
    if not json_exists:
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not md_exists:
        md_path.write_text(_render_closeout_prestep_md(report), encoding="utf-8")
    report["result"] = "EXECUTE_PASS"
    report["writes_enabled"] = True
    report["closeout_write_result"] = {
        "json_path": str(json_path),
        "md_path": str(md_path),
        "json_status": "skipped_existing" if json_exists else "written",
        "md_status": "skipped_existing" if md_exists else "written",
    }
    return report


def _build_closeout_prestep_report(
    *,
    for_trade_date: str,
    consumer_name: str,
    target_hhmm: str,
    source_trigger_run_id: str,
    action_run_id: str,
    source_metric_run_id: str,
    closeout_json_path: str,
    closeout_md_path: str,
) -> dict[str, Any]:
    return {
        "artifact_type": f"n5_fastlane_{target_hhmm}_actionexecuted_closeout_registration_v1",
        "artifact_status": "registered",
        "registration_mode": "fastlane_bounded_drain_closeout_prestep",
        "result": "PLAN_PASS",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "layer_role": "runtime_control",
        "for_trade_date": for_trade_date,
        "target_hhmm": target_hhmm,
        "consumer_name": consumer_name,
        "source_trigger_run_id": source_trigger_run_id,
        "action_run_id": action_run_id,
        "source_metric_run_id": source_metric_run_id,
        "closeout_json_path": closeout_json_path,
        "closeout_md_path": closeout_md_path,
        "must_complete_before_selected_source_runs": True,
        "database_written_by_orchestrator": False,
        "n4_outbox_updated": False,
        "n5_outbox_status_updated": False,
        "n6_touched": False,
        "old_n3_n4_runtime_touched": False,
        "requires_read_only_review": True,
        "final_verdict": "RUNTIME_CONTROL_FASTLANE_BOUNDED_DRAIN_CLOSEOUT_PRESTEP_REGISTERED",
    }


def _render_closeout_prestep_md(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            f"# N5 Fastlane {report.get('target_hhmm')} Closeout Registration Pre-Step",
            "",
            f"- artifact_status: {report.get('artifact_status')}",
            f"- for_trade_date: {report.get('for_trade_date')}",
            f"- consumer_name: {report.get('consumer_name')}",
            f"- action_run_id: {report.get('action_run_id')}",
            f"- source_trigger_run_id: {report.get('source_trigger_run_id')}",
            f"- source_metric_run_id: {report.get('source_metric_run_id')}",
            "- database_written_by_orchestrator: false",
            "- n4_outbox_updated: false",
            "- n6_touched: false",
            "",
            "This artifact is generated as the required pre-drain closeout step before selected source_run drain commands.",
            "",
        ]
    )


def _extract_hhmm(*values: str) -> str:
    for value in values:
        text = str(value or "")
        match = re.search(r"until_([0-2][0-9][0-5][0-9])", text)
        if match:
            return match.group(1)
        match = re.search(r"[_-]([0-2][0-9][0-5][0-9])[_-]", text)
        if match:
            return match.group(1)
    return ""


def _load_candidate_source_runs(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.plan_source_runs_json:
        payload = json.loads(Path(args.plan_source_runs_json).read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise FastlaneDrainBlocked("plan_source_runs_json_must_be_array")
        return [dict(item) for item in payload if isinstance(item, Mapping)]
    if not str(args.dsn or "").strip():
        raise FastlaneDrainBlocked("dsn_required_for_source_run_discovery")
    return _discover_candidate_source_runs_from_db(
        dsn=str(args.dsn),
        for_trade_date=str(args.for_trade_date),
        consumer_name=str(args.consumer_name),
    )


def _discover_candidate_source_runs_from_db(
    *,
    dsn: str,
    for_trade_date: str,
    consumer_name: str,
) -> list[dict[str, Any]]:
    import psycopg
    from psycopg.rows import dict_row

    query = """
        SELECT
          o.source_run_id,
          min(o.event_time)::text AS event_time,
          o.event_type,
          o.status,
          count(*)::int AS row_count
        FROM common_event_outbox o
        WHERE o.source_layer = 'N4_trigger'
          AND o.trade_date = %s
          AND o.event_type = 'TriggerMatched'
          AND o.status = 'pending'
          AND o.source_run_id LIKE %s
          AND NOT EXISTS (
            SELECT 1
            FROM common_action_tracking_state t
            WHERE t.trade_date = o.trade_date
              AND t.source_trigger_run_id = o.source_run_id
              AND t.run_id LIKE 'n5_live_tracking_%__fastlane_v1'
          )
        GROUP BY o.source_run_id, o.event_type, o.status
        ORDER BY min(o.event_time), o.source_run_id
    """
    with psycopg.connect(
        dsn,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
        connect_timeout=10,
    ) as conn, conn.cursor() as cur:
        cur.execute(query, (for_trade_date, "%_ordinary_%"))
        return [dict(row) for row in cur.fetchall()]


def _execute_drain_plan(plan: Mapping[str, Any], *, working_directory: Path) -> dict[str, Any]:
    started = time.monotonic()
    invocation_id = f"fastlane_source_run_scoped_drain_{uuid.uuid4().hex}"
    command_results: list[dict[str, Any]] = []
    for step in plan.get("pre_drain_steps") or []:
        elapsed = time.monotonic() - started
        remaining = float(plan.get("max_runtime_seconds") or 0) - elapsed
        if remaining <= 0:
            raise FastlaneDrainBlocked("max_runtime_seconds_exceeded")
        command = list((step.get("command") if isinstance(step, Mapping) else []) or [])
        if not command:
            raise FastlaneDrainBlocked(f"missing_pre_drain_step_command:{step.get('step_id') if isinstance(step, Mapping) else 'unknown'}")
        result = subprocess.run(
            command,
            cwd=str(working_directory),
            capture_output=True,
            text=True,
            timeout=max(1, int(remaining)),
            check=False,
        )
        command_results.append(
            {
                "step_id": step.get("step_id"),
                "step_type": step.get("step_type"),
                "lane": "pre_drain",
                "returncode": result.returncode,
                "stdout": _parse_json_or_text(result.stdout),
                "stderr_tail": (result.stderr or "")[-2000:],
            }
        )
        if result.returncode != 0:
            raise FastlaneDrainBlocked(f"pre_drain_step_failed:{step.get('step_id')}:{result.returncode}")
    for source_run in plan.get("selected_source_runs") or []:
        for lane in ("n5_intake", "n3_c1_n3t", "n5_executed"):
            elapsed = time.monotonic() - started
            remaining = float(plan.get("max_runtime_seconds") or 0) - elapsed
            if remaining <= 0:
                raise FastlaneDrainBlocked("max_runtime_seconds_exceeded")
            command = list(((source_run.get("commands") or {}).get(lane)) or [])
            if not command:
                raise FastlaneDrainBlocked(f"missing_lane_command:{lane}")
            result = subprocess.run(
                command,
                cwd=str(working_directory),
                capture_output=True,
                text=True,
                timeout=max(1, int(remaining)),
                check=False,
            )
            command_results.append(
                {
                    "source_run_id": source_run.get("source_run_id"),
                    "lane": lane,
                    "returncode": result.returncode,
                    "stdout": _parse_json_or_text(result.stdout),
                    "stderr_tail": (result.stderr or "")[-2000:],
                }
            )
            if result.returncode != 0:
                raise FastlaneDrainBlocked(f"lane_command_failed:{lane}:{result.returncode}")
    output = dict(plan)
    output["result"] = "EXECUTE_PASS"
    output["invocation_id"] = invocation_id
    output["writes_enabled"] = True
    output["database_written_by_orchestrator"] = False
    output["pre_drain_step_count"] = len(plan.get("pre_drain_steps") or [])
    output["command_results"] = command_results
    return output


def _parse_json_or_text(value: str) -> Any:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text[-2000:]


if __name__ == "__main__":
    raise SystemExit(main())
