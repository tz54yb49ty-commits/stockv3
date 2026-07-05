#!/usr/bin/env python3
"""Run one PR-4 N5 bounded action worker invocation.

This wrapper is orchestration only. Its active child path is the existing
scripts/run_action_consumer_once.py semantic action smoke path. It does not
consume N5 outbox, enter N6, write user/voice/mobile/sim/position/order state,
or mutate N3/N4 facts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ashare_v3.runtime.bounded_worker_control import (
    BoundedResult,
    BoundedWorkerStatus,
    SingletonLockHeld,
    acquire_global_chain_lock,
    atomic_write_json,
    build_invocation_id,
    build_phase1_realtime_chain_lock_path,
    build_run_id,
    check_stop_file,
    deadline_from_now,
    remaining_deadline_seconds,
    result_to_exit_code,
    run_child_with_timeout,
)


WORKER_NAME = "n5_bounded_action_worker"
ACTIVE_PATH = "scripts/run_action_consumer_once.py --semantic-action-smoke"
ACTIVE_CHILD_SCRIPT = "scripts/run_action_consumer_once.py"
ACCEPTED_EVENT_TYPE = "TriggerMatched"
DEFAULT_MAX_EVENTS = 10_000
DEFAULT_MAX_RUNTIME_SECONDS = 120.0
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 10
IMPLICIT_LINEAGE_VALUES = {"latest", "active", "fallback", "auto", "auto-resolve", "auto_resolve"}
ACTION_EVENT_TYPES = ("ActionExecuted", "ActionBlocked", "ActionSkipped", "ActionEligible")
TRADE_DATE_RE = re.compile(r"^\d{8}$")


class N5BoundedBlocked(RuntimeError):
    """Raised when wrapper preconditions fail before the child starts."""


class PlanningDeadlineExceeded(RuntimeError):
    """Raised when preflight planning has exhausted the bounded runtime."""

    def __init__(self, stage: str):
        super().__init__(stage)
        self.stage = stage


@dataclass(frozen=True)
class ExplicitLineage:
    for_trade_date: str
    source_trigger_run_id: str
    source_metric_run_id: str
    projection_run_id: str
    action_run_id: str
    consumer_name: str
    source_event_type: str

    def to_dict(self) -> dict[str, str]:
        return {
            "for_trade_date": self.for_trade_date,
            "source_trigger_run_id": self.source_trigger_run_id,
            "source_metric_run_id": self.source_metric_run_id,
            "projection_run_id": self.projection_run_id,
            "action_run_id": self.action_run_id,
            "consumer_name": self.consumer_name,
            "source_event_type": self.source_event_type,
        }


@dataclass(frozen=True)
class N5BoundedContext:
    repo_root: Path
    lineage: ExplicitLineage
    invocation_id: str
    wrapper_run_id: str
    lock_path: Path
    deadline: datetime | None
    dsn: str
    status_json: Path
    manifest_json: Path
    rollback_sql_path: Path
    child_rollback_sql_path: Path
    child_report_json_path: Path
    child_report_markdown_path: Path
    child_status_json_path: Path
    docs_root: Path
    sql_root: Path
    python_executable: str
    current_only_trigger_matched: bool = False

    @property
    def input_run_ids(self) -> dict[str, str]:
        return {
            "source_trigger_run_id": self.lineage.source_trigger_run_id,
            "source_metric_run_id": self.lineage.source_metric_run_id,
            "projection_run_id": self.lineage.projection_run_id,
        }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one PR-4 N5 bounded action worker invocation.")
    parser.add_argument("--for-trade-date")
    parser.add_argument("--source-trigger-run-id")
    parser.add_argument("--source-metric-run-id")
    parser.add_argument("--projection-run-id")
    parser.add_argument("--action-run-id")
    parser.add_argument("--consumer-name")
    parser.add_argument("--source-event-type")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", ""))
    parser.add_argument("--status-json")
    parser.add_argument("--manifest-json")
    parser.add_argument("--rollback-sql-path")
    parser.add_argument("--stop-file", default="")
    parser.add_argument("--max-runtime-seconds", type=float, default=DEFAULT_MAX_RUNTIME_SECONDS)
    parser.add_argument("--heartbeat-interval-seconds", type=int, default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS)
    parser.add_argument("--max-events", type=int, default=DEFAULT_MAX_EVENTS)
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--docs-root", default="docs")
    parser.add_argument("--sql-root", default="sql")
    parser.add_argument(
        "--current-only-trigger-matched",
        action="store_true",
        help="Consume only pending TriggerMatched rows whose trigger state is still current matched.",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def build_explicit_lineage(args: argparse.Namespace) -> ExplicitLineage:
    lineage = ExplicitLineage(
        for_trade_date=_validate_trade_date(_required_arg(args, "for_trade_date")),
        source_trigger_run_id=_validate_explicit_value("source_trigger_run_id", _required_arg(args, "source_trigger_run_id")),
        source_metric_run_id=_validate_explicit_value("source_metric_run_id", _required_arg(args, "source_metric_run_id")),
        projection_run_id=_validate_explicit_value("projection_run_id", _required_arg(args, "projection_run_id")),
        action_run_id=_validate_explicit_value("action_run_id", _required_arg(args, "action_run_id")),
        consumer_name=_validate_explicit_value("consumer_name", _required_arg(args, "consumer_name")),
        source_event_type=_required_arg(args, "source_event_type"),
    )
    if lineage.source_event_type != ACCEPTED_EVENT_TYPE:
        raise N5BoundedBlocked("source_event_type must be TriggerMatched")
    if lineage.source_metric_run_id != lineage.projection_run_id:
        raise N5BoundedBlocked("source_metric_run_id must equal projection_run_id")
    return lineage


def build_n5_bounded_context(
    lineage: ExplicitLineage,
    args: argparse.Namespace,
    *,
    repo_root: str | Path | None = None,
    now: datetime | None = None,
) -> N5BoundedContext:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    docs_root = _resolve_repo_path(root, _required_arg(args, "docs_root"))
    sql_root = _resolve_repo_path(root, _required_arg(args, "sql_root"))
    invocation_id = build_invocation_id()
    wrapper_run_id = build_run_id(WORKER_NAME, lineage.for_trade_date, invocation_id=invocation_id, now=now)
    artifact_stem = f"N5_BOUNDED_ACTION_WORKER_{_safe_artifact_name(lineage.action_run_id)}"
    return N5BoundedContext(
        repo_root=root,
        lineage=lineage,
        invocation_id=invocation_id,
        wrapper_run_id=wrapper_run_id,
        lock_path=build_phase1_realtime_chain_lock_path(root, lineage.for_trade_date),
        deadline=deadline_from_now(args.max_runtime_seconds, now=now),
        dsn=str(args.dsn or ""),
        status_json=_resolve_repo_path(root, _required_arg(args, "status_json")),
        manifest_json=_resolve_repo_path(root, _required_arg(args, "manifest_json")),
        rollback_sql_path=_resolve_repo_path(root, _required_arg(args, "rollback_sql_path")),
        child_rollback_sql_path=sql_root / f"{artifact_stem}_child_rollback.sql",
        child_report_json_path=docs_root / f"{artifact_stem}_child_report.json",
        child_report_markdown_path=docs_root / f"{artifact_stem}_child_report.md",
        child_status_json_path=docs_root / f"{artifact_stem}_child_status.json",
        docs_root=docs_root,
        sql_root=sql_root,
        python_executable=str(args.python_executable or sys.executable),
        current_only_trigger_matched=bool(getattr(args, "current_only_trigger_matched", False)),
    )


def build_source_query_filter(context: N5BoundedContext) -> dict[str, Any]:
    return {
        "source_layer": "N4_trigger",
        "source_trigger_run_id": context.lineage.source_trigger_run_id,
        "event_type": ACCEPTED_EVENT_TYPE,
        "status": "pending",
        "consumer_name": context.lineage.consumer_name,
        "for_trade_date": context.lineage.for_trade_date,
        "uses_limit": False,
        "current_only_trigger_matched": context.current_only_trigger_matched,
    }


def run_n5_bounded_action_worker_once(
    argv: Sequence[str] | None = None,
    *,
    repo_root: str | Path | None = None,
    preflight_provider: Callable[[N5BoundedContext], Mapping[str, Any]] | None = None,
    command_runner: Callable[[Sequence[str], float | None], Mapping[str, Any] | Any] | None = None,
    post_check_provider: Callable[[N5BoundedContext, Mapping[str, Any]], Mapping[str, Any]] | None = None,
    lock_acquirer: Callable[[str | Path], Any] = acquire_global_chain_lock,
    now: datetime | None = None,
) -> dict[str, Any]:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        lineage = build_explicit_lineage(args)
        context = build_n5_bounded_context(lineage, args, repo_root=repo_root, now=now)
    except (N5BoundedBlocked, ValueError) as exc:
        return _early_blocked_manifest(args, str(exc), repo_root=repo_root, now=now)

    if not args.execute:
        manifest = build_n5_manifest(
            context,
            result=BoundedResult.NOOP,
            stop_reason="plan_only",
            args=args,
            child_result={"child_invoked": False},
            classification={"requires_post_check": False, "action_event_counts": zero_action_event_counts()},
        )
        write_final_status(context, manifest)
        return manifest

    try:
        with lock_acquirer(context.lock_path):
            manifest = _run_with_lock(
                context,
                args,
                preflight_provider=preflight_provider,
                command_runner=command_runner,
                post_check_provider=post_check_provider,
            )
            write_final_status(context, manifest)
            return manifest
    except SingletonLockHeld:
        manifest = build_n5_manifest(
            context,
            result=BoundedResult.NOOP,
            stop_reason="singleton_lock_held",
            args=args,
            child_result={"child_invoked": False},
            classification={"requires_post_check": False, "action_event_counts": zero_action_event_counts()},
        )
        write_final_status(context, manifest)
        return manifest


def _run_with_lock(
    context: N5BoundedContext,
    args: argparse.Namespace,
    *,
    preflight_provider: Callable[[N5BoundedContext], Mapping[str, Any]] | None,
    command_runner: Callable[[Sequence[str], float | None], Mapping[str, Any] | Any] | None,
    post_check_provider: Callable[[N5BoundedContext, Mapping[str, Any]], Mapping[str, Any]] | None,
) -> dict[str, Any]:
    if not args.execute:
        return build_n5_manifest(
            context,
            result=BoundedResult.NOOP,
            stop_reason="plan_only",
            args=args,
            child_result={"child_invoked": False},
            classification={"requires_post_check": False, "action_event_counts": zero_action_event_counts()},
        )
    if not args.user_confirmed:
        return build_n5_manifest(
            context,
            result=BoundedResult.BLOCKED,
            stop_reason="execute_requires_user_confirmed",
            args=args,
            child_result={"child_invoked": False},
            classification={"requires_post_check": False, "action_event_counts": zero_action_event_counts()},
        )

    stopped, stop_reason = check_stop_file(args.stop_file or None)
    if stopped:
        return build_n5_manifest(
            context,
            result=BoundedResult.NOOP,
            stop_reason=stop_reason,
            args=args,
            child_result={"child_invoked": False},
            classification={"requires_post_check": False, "action_event_counts": zero_action_event_counts()},
        )

    remaining = remaining_deadline_seconds(context.deadline)
    if remaining is not None and remaining <= 0:
        return build_n5_manifest(
            context,
            result=BoundedResult.BLOCKED,
            stop_reason="deadline_before_child",
            args=args,
            child_result={"child_invoked": False},
            classification={"requires_post_check": False, "action_event_counts": zero_action_event_counts()},
        )

    preflight = run_preflight(context, args, preflight_provider=preflight_provider)
    block_reason = preflight_block_reason(preflight, max_events=int(args.max_events))
    if block_reason is not None:
        return build_n5_manifest(
            context,
            result=BoundedResult.BLOCKED,
            stop_reason=block_reason,
            args=args,
            preflight=preflight,
            child_result={"child_invoked": False},
            classification={"requires_post_check": False, "action_event_counts": preflight_action_event_counts(preflight)},
        )

    write_wrapper_rollback_sql(context, preflight)
    child_result = execute_child(context, args, command_runner=command_runner)
    classification = classify_child_result(
        child_result,
        context,
        preflight,
        post_check_provider=post_check_provider,
    )
    return build_n5_manifest(
        context,
        result=str(classification["result"]),
        stop_reason=classification.get("stop_reason"),
        args=args,
        preflight=preflight,
        child_result=child_result,
        classification=classification,
    )


def run_preflight(
    context: N5BoundedContext,
    args: argparse.Namespace,
    *,
    preflight_provider: Callable[[N5BoundedContext], Mapping[str, Any]] | None,
) -> dict[str, Any]:
    raw = dict(preflight_provider(context)) if preflight_provider is not None else _default_preflight(context)
    return normalize_preflight(raw, context)


def normalize_preflight(raw: Mapping[str, Any], context: N5BoundedContext) -> dict[str, Any]:
    output = dict(raw)
    rows = [dict(row) for row in output.get("candidate_rows") or []]
    output["candidate_rows"] = rows
    output["candidate_total"] = int(output.get("candidate_total") if output.get("candidate_total") is not None else len(rows))
    output.setdefault("candidate_event_ids", [str(row.get("event_id") or "") for row in rows if row.get("event_id")])
    output.setdefault("candidate_partitions", sorted({str(row.get("partition_key") or row.get("identity_key") or "") for row in rows}))
    output["source_query_filter"] = build_source_query_filter(context)
    output.setdefault("consumer_scope", {"fresh": False, "reason": "consumer_scope_missing"})
    output.setdefault("trade_date_proof", {"passed": False, "reason": "trade_date_proof_missing"})
    output.setdefault("planning_deadline", {"passed": True})
    output.setdefault("current_only_trigger_matched_filter", {"enabled": context.current_only_trigger_matched})
    output["trade_date_proof"] = normalize_trade_date_proof(
        output["trade_date_proof"],
        candidate_total=int(output["candidate_total"]),
        for_trade_date=context.lineage.for_trade_date,
    )
    output.setdefault("metric_preflight", {"passed": False, "reason": "metric_preflight_missing"})
    output.setdefault("stale_trigger_preflight", {"passed": False, "reason": "stale_trigger_preflight_missing"})
    counts = zero_action_event_counts()
    counts.update({key: int(value or 0) for key, value in dict(output.get("action_event_counts") or {}).items() if key in counts})
    output["action_event_counts"] = counts
    output.setdefault("live_window_action_summary", build_live_window_action_summary_from_counts(counts))
    output.setdefault("action_eligible_allowed", {"passed": True, "count": counts["ActionEligible"]})
    return output


def normalize_trade_date_proof(proof: Mapping[str, Any], *, candidate_total: int, for_trade_date: str) -> dict[str, Any]:
    output = dict(proof or {})
    if output.get("passed") is True and candidate_total > 0:
        errors: list[str] = []
        if int(output.get("joined_proof_count") or 0) != candidate_total:
            errors.append("joined_proof_count")
        if str(output.get("trigger_match_for_trade_date") or "") != for_trade_date:
            errors.append("trigger_match_for_trade_date")
        if str(output.get("trigger_state_for_trade_date") or "") != for_trade_date:
            errors.append("trigger_state_for_trade_date")
        if errors:
            output["passed"] = False
            output["reason"] = "joined_trade_date_proof_incomplete"
            output["proof_errors"] = errors
    return output


def preflight_block_reason(preflight: Mapping[str, Any], *, max_events: int) -> str | None:
    if max_events < 1:
        return "max_events_invalid"
    candidate_total = preflight.get("candidate_total")
    if candidate_total is None:
        return "candidate_total_unavailable"
    if int(candidate_total) > max_events:
        return "candidate_total_exceeds_max_events"
    current_only_filter = preflight.get("current_only_trigger_matched_filter") or {}
    if current_only_filter.get("enabled") and current_only_filter.get("passed") is not True:
        return str(current_only_filter.get("reason") or "current_only_trigger_matched_filter_failed")
    if (preflight.get("consumer_scope") or {}).get("fresh") is not True:
        return "consumer_scope_not_fresh"
    if (preflight.get("trade_date_proof") or {}).get("passed") is not True:
        return "trade_date_proof_failed"
    if (preflight.get("planning_deadline") or {}).get("passed") is not True:
        return str((preflight.get("planning_deadline") or {}).get("reason") or "planning_deadline_exceeded")
    if (preflight.get("metric_preflight") or {}).get("passed") is not True:
        return "metric_preflight_failed"
    if (preflight.get("stale_trigger_preflight") or {}).get("passed") is not True:
        return "stale_trigger_preflight_failed"
    return None


def execute_child(
    context: N5BoundedContext,
    args: argparse.Namespace,
    *,
    command_runner: Callable[[Sequence[str], float | None], Mapping[str, Any] | Any] | None,
) -> dict[str, Any]:
    remaining = remaining_deadline_seconds(context.deadline)
    if remaining is not None and remaining <= 0:
        return {
            "result": BoundedResult.BLOCKED,
            "stop_reason": "deadline_before_child",
            "child_invoked": False,
            "requires_post_check": False,
        }
    command = build_child_command(context, args)
    runner = command_runner or _run_child_command
    result = _normalize_child_result(runner(command, remaining))
    result["argv"] = command
    result["child_invoked"] = True
    return result


def build_child_command(context: N5BoundedContext, args: argparse.Namespace) -> list[str]:
    command = [
        context.python_executable,
        str(context.repo_root / ACTIVE_CHILD_SCRIPT),
        "--semantic-action-smoke",
        "--dsn",
        context.dsn,
        "--source-trigger-run-id",
        context.lineage.source_trigger_run_id,
        "--consumer-name",
        context.lineage.consumer_name,
        "--smoke-run-id",
        context.lineage.action_run_id,
        "--metric-run-id",
        context.lineage.source_metric_run_id,
        "--source-event-type",
        ACCEPTED_EVENT_TYPE,
        "--max-events",
        str(int(args.max_events)),
        "--max-runtime-seconds",
        str(int(float(args.max_runtime_seconds))),
        "--heartbeat-interval-seconds",
        str(int(args.heartbeat_interval_seconds)),
        "--json-report-path",
        str(context.child_report_json_path),
        "--markdown-report-path",
        str(context.child_report_markdown_path),
        "--status-json",
        str(context.child_status_json_path),
        "--rollback-sql-path",
        str(context.child_rollback_sql_path),
        "--execute",
        "--user-confirmed",
        "--json",
    ]
    if args.stop_file:
        command.extend(["--stop-file", str(args.stop_file)])
    if context.current_only_trigger_matched:
        command.append("--current-only-trigger-matched")
    return command


def classify_child_result(
    child_result: Mapping[str, Any],
    context: N5BoundedContext,
    preflight: Mapping[str, Any],
    *,
    post_check_provider: Callable[[N5BoundedContext, Mapping[str, Any]], Mapping[str, Any]] | None,
) -> dict[str, Any]:
    if child_result.get("timed_out") or child_result.get("result") == BoundedResult.UNKNOWN_AFTER_TIMEOUT:
        post_check = post_check_action_run(context, preflight, post_check_provider=post_check_provider)
        return {
            "result": BoundedResult.UNKNOWN_AFTER_TIMEOUT,
            "stop_reason": "child_timeout",
            "requires_post_check": True,
            "post_check": post_check,
            "action_event_counts": _merge_action_counts(preflight_action_event_counts(preflight), post_check.get("action_event_counts")),
            "rollback_artifacts": {},
        }

    if child_result.get("returncode") not in (0, None):
        post_check = post_check_action_run(context, preflight, post_check_provider=post_check_provider)
        return _classify_failed_or_ambiguous_child("child_exit_nonzero", post_check, preflight)

    report_result = _load_child_report(context.child_report_json_path, context.lineage.action_run_id)
    if report_result["error"]:
        post_check = post_check_action_run(context, preflight, post_check_provider=post_check_provider)
        return _classify_failed_or_ambiguous_child(str(report_result["error"]), post_check, preflight)

    rollback_result = validate_wrapper_rollback_sql(context.rollback_sql_path)
    post_check = post_check_action_run(context, preflight, post_check_provider=post_check_provider)
    report_counts = _event_counts_from_child_report(report_result["report"])
    counts = _merge_action_counts(report_counts, post_check.get("action_event_counts"))

    if rollback_result["error"]:
        return _classify_failed_or_ambiguous_child(str(rollback_result["error"]), post_check, preflight, counts=counts)

    if str(post_check.get("state") or "") != "committed":
        return _classify_failed_or_ambiguous_child("post_check_not_committed", post_check, preflight, counts=counts)

    return {
        "result": BoundedResult.PASS,
        "stop_reason": None,
        "requires_post_check": False,
        "post_check": post_check,
        "action_event_counts": counts,
        "rollback_artifacts": rollback_result["rollback_artifacts"],
        "child_report_json_path": str(context.child_report_json_path),
    }


def post_check_action_run(
    context: N5BoundedContext,
    preflight: Mapping[str, Any],
    *,
    post_check_provider: Callable[[N5BoundedContext, Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if post_check_provider is not None:
        return dict(post_check_provider(context, preflight))
    return _default_post_check_action_run(context, preflight)


def build_n5_manifest(
    context: N5BoundedContext,
    *,
    result: str,
    stop_reason: str | None,
    args: argparse.Namespace,
    preflight: Mapping[str, Any] | None = None,
    child_result: Mapping[str, Any] | None = None,
    classification: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    preflight = dict(preflight or {})
    classification = dict(classification or {})
    action_event_counts = _merge_action_counts(preflight_action_event_counts(preflight), classification.get("action_event_counts"))
    child_invoked = bool((child_result or {}).get("child_invoked"))
    requires_post_check = bool(
        classification.get("requires_post_check", result in {BoundedResult.UNKNOWN_AFTER_TIMEOUT, BoundedResult.COMMIT_UNKNOWN})
    )
    side_effects = _no_external_side_effects()
    bounded_status = BoundedWorkerStatus(
        result=result,
        stop_reason=stop_reason,
        requires_post_check=requires_post_check,
        invocation_id=context.invocation_id,
        run_id=context.wrapper_run_id,
        trade_date=context.lineage.for_trade_date,
        worker_name=WORKER_NAME,
        input_run_ids=context.input_run_ids,
        output_run_id=context.lineage.action_run_id if child_invoked else None,
        rollback_artifacts=classification.get("rollback_artifacts") or {},
        downstream_consumption_allowed=False,
        processed_count=int(preflight.get("candidate_total") or 0),
        written_count=sum(action_event_counts.values()) if result == BoundedResult.PASS else 0,
        external_side_effects=side_effects,
    ).to_dict()
    manifest = {
        "worker_name": WORKER_NAME,
        "json": bool(args.json),
        "result": result,
        "stop_reason": stop_reason,
        "exit_code": result_to_exit_code(result),
        "requires_post_check": requires_post_check,
        "invocation_id": context.invocation_id,
        "wrapper_run_id": context.wrapper_run_id,
        "action_run_id": context.lineage.action_run_id,
        "source_trigger_run_id": context.lineage.source_trigger_run_id,
        "source_metric_run_id": context.lineage.source_metric_run_id,
        "projection_run_id": context.lineage.projection_run_id,
        "input_run_ids": context.input_run_ids,
        "explicit_lineage": context.lineage.to_dict(),
        "lineage_policy": {
            "all_lineage_explicit": True,
            "source_metric_run_id_equals_projection_run_id": context.lineage.source_metric_run_id == context.lineage.projection_run_id,
            "accepted_event_type": ACCEPTED_EVENT_TYPE,
            "implicit_selectors_rejected": sorted(IMPLICIT_LINEAGE_VALUES),
        },
        "active_path": ACTIVE_PATH,
        "active_child_script": ACTIVE_CHILD_SCRIPT,
        "source_query_filter": build_source_query_filter(context),
        "candidate_total": preflight.get("candidate_total"),
        "source_candidate_total": preflight.get("source_candidate_total"),
        "max_events": int(args.max_events),
        "current_only_trigger_matched_filter": dict(preflight.get("current_only_trigger_matched_filter") or {}),
        "consumer_scope": dict(preflight.get("consumer_scope") or {}),
        "trade_date_proof": dict(preflight.get("trade_date_proof") or {}),
        "planning_deadline": dict(preflight.get("planning_deadline") or {}),
        "metric_preflight": dict(preflight.get("metric_preflight") or {}),
        "stale_trigger_preflight": dict(preflight.get("stale_trigger_preflight") or {}),
        "action_event_counts": action_event_counts,
        "live_window_action_summary": dict(
            preflight.get("live_window_action_summary")
            or build_live_window_action_summary_from_counts(action_event_counts)
        ),
        "action_eligible_allowed": {
            "passed": True,
            "count": action_event_counts["ActionEligible"],
        },
        "child_invoked": child_invoked,
        "child_result": dict(child_result or {}),
        "post_check": dict(classification.get("post_check") or {}),
        "rollback_artifacts": dict(classification.get("rollback_artifacts") or {}),
        "rollback_sql_path": str(context.rollback_sql_path),
        "rollback_sql_sha256": (classification.get("rollback_artifacts") or {}).get("rollback_sql_sha256"),
        "tracking_state_rollback_coverage": tracking_state_rollback_coverage(context.rollback_sql_path),
        "status_json": str(context.status_json),
        "manifest_json": str(context.manifest_json),
        "lock_path": str(context.lock_path),
        "external_side_effects": side_effects,
        "side_effects": side_effects,
        "downstream_consumption_allowed": False,
        "n6_consumption_allowed": False,
        "n5_outbox_consumed": False,
        "no_partial_contract": True,
        "bounded_status": bounded_status,
    }
    return manifest


def write_final_status(context: N5BoundedContext, manifest: Mapping[str, Any]) -> None:
    atomic_write_json(context.manifest_json, manifest)
    status_keys = (
        "worker_name",
        "result",
        "stop_reason",
        "exit_code",
        "requires_post_check",
        "invocation_id",
        "wrapper_run_id",
        "action_run_id",
        "source_trigger_run_id",
        "source_metric_run_id",
        "projection_run_id",
        "candidate_total",
        "max_events",
        "child_invoked",
        "action_event_counts",
        "downstream_consumption_allowed",
        "external_side_effects",
    )
    atomic_write_json(context.status_json, {key: manifest[key] for key in status_keys if key in manifest})


def write_wrapper_rollback_sql(context: N5BoundedContext, preflight: Mapping[str, Any]) -> dict[str, Any]:
    sql = build_wrapper_rollback_sql(
        action_run_id=context.lineage.action_run_id,
        source_trigger_run_id=context.lineage.source_trigger_run_id,
        consumer_name=context.lineage.consumer_name,
        candidate_event_ids=[str(item) for item in preflight.get("candidate_event_ids") or []],
    )
    context.rollback_sql_path.parent.mkdir(parents=True, exist_ok=True)
    context.rollback_sql_path.write_text(sql, encoding="utf-8")
    digest = hashlib.sha256(context.rollback_sql_path.read_bytes()).hexdigest()
    return {"rollback_sql_path": str(context.rollback_sql_path), "rollback_sql_sha256": digest}


def build_wrapper_rollback_sql(
    *,
    action_run_id: str,
    source_trigger_run_id: str,
    consumer_name: str,
    candidate_event_ids: Sequence[str],
) -> str:
    event_id_array = _sql_text_array(candidate_event_ids)
    return f"""-- PR-4 N5 bounded action worker rollback.
-- Scope:
--   action_run_id: {action_run_id}
--   source_trigger_run_id: {source_trigger_run_id}
--   consumer_name: {consumer_name}
-- Boundary:
--   Deletes only scoped N5 action rows, scoped N5 outbox/ledger/delivery attempts,
--   this action run's N5 tracking state, and this consumer's exact N4 inbox/checkpoint
--   rows. It does not delete N3 facts, N4 trigger facts/outbox, N6/user projection,
--   voice, sim, mobile, position, order, or real-trade rows.

BEGIN;

\\set action_run_id '{action_run_id}'
\\set source_trigger_run_id '{source_trigger_run_id}'
\\set consumer_name '{consumer_name}'

SET LOCAL n5.rollback_action_run_id = :'action_run_id';
SET LOCAL n5.rollback_source_trigger_run_id = :'source_trigger_run_id';
SET LOCAL n5.rollback_consumer_name = :'consumer_name';

DO $$
DECLARE
  v_action_run_id text := current_setting('n5.rollback_action_run_id');
  v_source_trigger_run_id text := current_setting('n5.rollback_source_trigger_run_id');
  v_count bigint := 0;
  v_table_name text;
  v_table_regclass regclass;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = v_action_run_id
    AND status IN ('delivering', 'delivered');
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: scoped N5 outbox has delivered/delivering rows (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = v_action_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: scoped N5 outbox has downstream inbox refs (%)', v_count;
  END IF;

  WITH scoped_n5_partitions AS (
    SELECT DISTINCT partition_key
    FROM common_event_outbox
    WHERE source_layer = 'N5_action'
      AND source_run_id = v_action_run_id
    UNION
    SELECT DISTINCT partition_key
    FROM common_event_ledger
    WHERE source_layer = 'N5_action'
      AND source_run_id = v_action_run_id
  )
  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer = 'N5_action'
    AND partition_key IN (SELECT partition_key FROM scoped_n5_partitions);
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: scoped N5 outbox has downstream checkpoint refs (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_action_tracking_state
  -- Required PR-4 guard marker: source_trigger_run_id <> :'source_trigger_run_id'
  WHERE run_id = v_action_run_id
    AND source_trigger_run_id <> v_source_trigger_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: tracking_state source_trigger_run_id mismatch (%)', v_count;
  END IF;

  FOREACH v_table_name IN ARRAY ARRAY[
    'user_projection_run',
    'user_card_projection',
    'user_signal_projection',
    'user_signal_decision',
    'user_notification_queue',
    'user_notification_projection',
    'user_voice_delivery',
    'user_device_ack',
    'user_market_projection',
    'voice_delivery_queue',
    'mobile_projection',
    'mobile_notification_queue',
    'sim_projection',
    'sim_order',
    'sim_trade',
    'user_sim_order',
    'user_sim_trade',
    'user_sim_position',
    'common_position_state',
    'common_position_event',
    'common_order',
    'common_order_event',
    'order_event',
    'real_order',
    'user_order'
  ]
  LOOP
    v_table_regclass := to_regclass('public.' || v_table_name);
    IF v_table_regclass IS NOT NULL THEN
      EXECUTE format(
        'SELECT count(*) FROM %s t WHERE to_jsonb(t)::text LIKE $1 OR to_jsonb(t)::text LIKE $2',
        v_table_regclass
      )
      INTO v_count
      USING '%' || v_action_run_id || '%', '%' || v_source_trigger_run_id || '%';
      IF v_count > 0 THEN
        RAISE EXCEPTION 'N5 rollback blocked: downstream table % has scoped refs (%)', v_table_name, v_count;
      END IF;
    END IF;
  END LOOP;
END $$;

SELECT 'common_action_tracking_state' AS table_name, count(*) AS row_count
FROM common_action_tracking_state
WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'stock_action_fact', count(*) FROM stock_action_fact WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'index_action_fact', count(*) FROM index_action_fact WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'board_action_fact', count(*) FROM board_action_fact WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'common_action_event', count(*) FROM common_action_event WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'common_event_outbox_n5', count(*) FROM common_event_outbox WHERE source_layer = 'N5_action' AND source_run_id = :'action_run_id'
UNION ALL
SELECT 'common_event_inbox_n4_exact_candidates', count(*) FROM common_event_inbox
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND source_run_id = :'source_trigger_run_id'
  AND event_id = ANY({event_id_array});

WITH scoped_n5_event_ids AS (
  SELECT event_id
  FROM common_event_outbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = :'action_run_id'
  UNION
  SELECT event_id
  FROM common_event_ledger
  WHERE source_layer = 'N5_action'
    AND source_run_id = :'action_run_id'
)
DELETE FROM common_event_delivery_attempt
WHERE event_id IN (SELECT event_id FROM scoped_n5_event_ids);

DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND checkpoint_payload->>'action_run_id' = :'action_run_id';

DELETE FROM common_event_inbox
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND source_run_id = :'source_trigger_run_id'
  AND event_id = ANY({event_id_array});

DELETE FROM common_event_outbox
WHERE source_layer = 'N5_action'
  AND source_run_id = :'action_run_id';

DELETE FROM common_event_ledger
WHERE source_layer = 'N5_action'
  AND source_run_id = :'action_run_id';

DELETE FROM common_action_event
WHERE run_id = :'action_run_id';

DELETE FROM common_action_tracking_state
WHERE run_id = :'action_run_id';

DELETE FROM board_action_fact
WHERE run_id = :'action_run_id';

DELETE FROM index_action_fact
WHERE run_id = :'action_run_id';

DELETE FROM stock_action_fact
WHERE run_id = :'action_run_id';

DELETE FROM common_action_quality_item
WHERE run_id = :'action_run_id';

DELETE FROM common_action_run
WHERE run_id = :'action_run_id';

COMMIT;
"""


def validate_wrapper_rollback_sql(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"rollback_artifacts": {}, "error": "rollback_sql_missing"}
    text = path.read_text(encoding="utf-8")
    required = (
        "common_action_tracking_state",
        "source_trigger_run_id <> :'source_trigger_run_id'",
        "DELETE FROM common_action_tracking_state",
        "scoped N5 outbox has downstream inbox refs",
        "scoped N5 outbox has downstream checkpoint refs",
    )
    missing = [item for item in required if item not in text]
    forbidden = ("DELETE FROM common_trigger_state", "DELETE FROM common_trigger_match", "DELETE FROM user_")
    found_forbidden = [item for item in forbidden if item in text]
    if missing or found_forbidden:
        return {
            "rollback_artifacts": {},
            "error": "rollback_sql_incomplete",
            "missing": missing,
            "forbidden": found_forbidden,
        }
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "rollback_artifacts": {
            "rollback_sql_path": str(path),
            "rollback_sql_sha256": digest,
            "tracking_state_rollback_coverage": tracking_state_rollback_coverage(path),
        },
        "error": None,
    }


def tracking_state_rollback_coverage(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"included": False, "reason": "rollback_sql_missing"}
    text = path.read_text(encoding="utf-8")
    included = (
        "common_action_tracking_state" in text
        and "source_trigger_run_id <> :'source_trigger_run_id'" in text
        and "DELETE FROM common_action_tracking_state" in text
    )
    return {
        "included": included,
        "delete_scope": "run_id",
        "source_trigger_run_id_guard": "source_trigger_run_id <> :'source_trigger_run_id'" in text,
    }


def zero_action_event_counts() -> dict[str, int]:
    return {event_type: 0 for event_type in ACTION_EVENT_TYPES}


def build_live_window_action_summary_from_counts(counts: Mapping[str, Any]) -> dict[str, int]:
    return {
        "opened_tracking": int(counts.get("ActionEligible") or 0),
        "executed_from_window": 0,
        "still_pending": int(counts.get("ActionEligible") or 0),
        "expired": int(counts.get("ActionSkipped") or 0),
        "one_shot_blocked": int(counts.get("ActionBlocked") or 0),
        "executed_metric_count": 0,
        "multi_action_trigger_count": 0,
        "max_actions_per_trigger": 0,
    }


def preflight_action_event_counts(preflight: Mapping[str, Any] | None) -> dict[str, int]:
    counts = zero_action_event_counts()
    if preflight:
        counts.update({key: int(value or 0) for key, value in dict(preflight.get("action_event_counts") or {}).items() if key in counts})
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    result = run_n5_bounded_action_worker_once(argv)
    if result.get("json") is True:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "\n".join(
                [
                    "N5 bounded action worker",
                    f"  result={result.get('result')}",
                    f"  stop_reason={result.get('stop_reason')}",
                    f"  action_run_id={result.get('action_run_id')}",
                    f"  child_invoked={result.get('child_invoked')}",
                    f"  downstream_consumption_allowed={result.get('downstream_consumption_allowed')}",
                ]
            )
        )
    return int(result.get("exit_code", result_to_exit_code(str(result.get("result") or BoundedResult.BLOCKED))))


def _default_preflight(context: N5BoundedContext) -> dict[str, Any]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as exc:  # pragma: no cover - environment guard.
        return {
            "candidate_total": None,
            "candidate_rows": [],
            "consumer_scope": {"fresh": False, "reason": f"psycopg_unavailable:{exc.__class__.__name__}"},
        }

    try:
        with psycopg.connect(
            context.dsn,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            _ensure_planning_deadline(context, "before_fetch_candidates")
            source_rows = _fetch_candidate_rows(cur, context)
            _ensure_planning_deadline(context, "after_fetch_candidates")
            rows = source_rows
            current_only_filter = {"enabled": False}
            if context.current_only_trigger_matched:
                rows, current_only_filter = _filter_current_trigger_matched_rows(cur, context, source_rows)
                _ensure_planning_deadline(context, "after_current_only_filter")
                if not rows:
                    action_event_counts = zero_action_event_counts()
                    return {
                        "candidate_rows": [],
                        "candidate_total": 0,
                        "source_candidate_total": len(source_rows),
                        "candidate_event_ids": [],
                        "candidate_partitions": [],
                        "current_only_trigger_matched_filter": current_only_filter,
                        "consumer_scope": {
                            "fresh": True,
                            "existing_inbox_count": 0,
                            "existing_checkpoint_count": 0,
                            "candidate_event_count": 0,
                            "candidate_partition_count": 0,
                        },
                        "trade_date_proof": {
                            "passed": True,
                            "joined_proof_count": 0,
                            "trigger_match_for_trade_date": context.lineage.for_trade_date,
                            "trigger_state_for_trade_date": context.lineage.for_trade_date,
                        },
                        "planning_deadline": {"passed": True},
                        "metric_preflight": {
                            "passed": True,
                            "reason": "current_only_no_current_trigger_matched",
                            "metric_run_id": context.lineage.source_metric_run_id,
                            "n4_trigger_matched_rows": 0,
                            "joined_n4_rows": 0,
                            "missing_n4_rows": 0,
                        },
                        "stale_trigger_preflight": {"passed": True, "checked_count": 0, "stale_count": 0, "failures_sample": []},
                        "action_event_counts": action_event_counts,
                        "live_window_action_summary": build_live_window_action_summary_from_counts(action_event_counts),
                        "action_eligible_allowed": {"passed": True, "count": 0},
                    }
            consumer_scope = _verify_consumer_scope(cur, context, rows)
            _ensure_planning_deadline(context, "after_consumer_scope")
            trade_date_proof = _verify_trade_date_proof(cur, context, rows)
            _ensure_planning_deadline(context, "after_trade_date_proof")
            stale_trigger_preflight = _verify_stale_trigger_preflight(cur, context, rows)
            _ensure_planning_deadline(context, "after_stale_trigger_preflight")
            metric_preflight, enriched_rows, metric_facts, metric_facts_by_identity = _verify_metric_preflight(cur, context, rows)
            _ensure_planning_deadline(context, "after_metric_preflight")
            action_event_counts, live_window_action_summary = _build_action_plan_summaries(
                context,
                enriched_rows,
                metric_facts,
                metric_facts_by_identity,
            )
            _ensure_planning_deadline(context, "after_action_plan_summary")
    except PlanningDeadlineExceeded as exc:
        return _planning_deadline_blocked_preflight(context, stage=exc.stage)
    except Exception as exc:  # pragma: no cover - live DB only.
        return {
            "candidate_total": None,
            "candidate_rows": [],
            "consumer_scope": {"fresh": False, "reason": f"preflight_query_failed:{exc.__class__.__name__}"},
            "trade_date_proof": {"passed": False, "reason": f"preflight_query_failed:{exc.__class__.__name__}"},
            "metric_preflight": {"passed": False, "reason": f"preflight_query_failed:{exc.__class__.__name__}"},
            "stale_trigger_preflight": {"passed": False, "reason": f"preflight_query_failed:{exc.__class__.__name__}"},
        }

    return {
        "candidate_rows": rows,
        "candidate_total": len(rows),
        "source_candidate_total": len(source_rows),
        "candidate_event_ids": [str(row.get("event_id") or "") for row in rows],
        "candidate_partitions": sorted({str(row.get("partition_key") or row.get("identity_key") or "") for row in rows}),
        "current_only_trigger_matched_filter": current_only_filter,
        "consumer_scope": consumer_scope,
        "trade_date_proof": trade_date_proof,
        "planning_deadline": {"passed": True},
        "metric_preflight": metric_preflight,
        "stale_trigger_preflight": stale_trigger_preflight,
        "action_event_counts": action_event_counts,
        "live_window_action_summary": live_window_action_summary,
        "action_eligible_allowed": {"passed": True, "count": action_event_counts["ActionEligible"]},
    }


def _ensure_planning_deadline(context: N5BoundedContext, stage: str) -> None:
    remaining = remaining_deadline_seconds(context.deadline)
    if remaining is not None and remaining <= 0:
        raise PlanningDeadlineExceeded(stage)


def _planning_deadline_blocked_preflight(context: N5BoundedContext, *, stage: str) -> dict[str, Any]:
    counts = zero_action_event_counts()
    return {
        "candidate_rows": [],
        "candidate_total": 0,
        "source_candidate_total": 0,
        "candidate_event_ids": [],
        "candidate_partitions": [],
        "current_only_trigger_matched_filter": {
            "enabled": context.current_only_trigger_matched,
            "passed": True,
            "reason": "not_checked_after_planning_deadline",
        },
        "consumer_scope": {"fresh": True, "reason": "not_checked_after_planning_deadline"},
        "trade_date_proof": {"passed": True, "reason": "not_checked_after_planning_deadline"},
        "planning_deadline": {
            "passed": False,
            "reason": "planning_deadline_exceeded",
            "stage": stage,
        },
        "metric_preflight": {"passed": False, "reason": "planning_deadline_exceeded", "stage": stage},
        "stale_trigger_preflight": {"passed": True, "reason": "not_checked_after_planning_deadline"},
        "action_event_counts": counts,
        "live_window_action_summary": build_live_window_action_summary_from_counts(counts),
        "action_eligible_allowed": {"passed": True, "count": 0},
    }


def _fetch_candidate_rows(cur: Any, context: N5BoundedContext) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT outbox_id, event_id, event_type, event_schema_version, trade_date,
               asset_kind, identity_key, event_time, source_layer, source_run_id,
               dedup_key, partition_key, payload_json, status, created_at
        FROM common_event_outbox
        WHERE source_layer = 'N4_trigger'
          AND source_run_id = %s
          AND status = 'pending'
          AND event_type = 'TriggerMatched'
        ORDER BY partition_key, event_time, outbox_id, event_id
        """,
        (context.lineage.source_trigger_run_id,),
    )
    return [_normalize_row(row) for row in cur.fetchall()]


def _verify_consumer_scope(cur: Any, context: N5BoundedContext, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    event_ids = [str(row.get("event_id") or "") for row in rows if row.get("event_id")]
    partitions = sorted({str(row.get("partition_key") or row.get("identity_key") or "") for row in rows if row.get("partition_key") or row.get("identity_key")})
    inbox_count = 0
    checkpoint_count = 0
    if event_ids:
        cur.execute(
            """
            SELECT count(*)::bigint AS row_count
            FROM common_event_inbox
            WHERE consumer_name = %s
              AND event_id = ANY(%s)
            """,
            (context.lineage.consumer_name, event_ids),
        )
        inbox_count = int(cur.fetchone()["row_count"])
    if partitions:
        cur.execute(
            """
            SELECT count(*)::bigint AS row_count
            FROM common_event_consumer_checkpoint
            WHERE consumer_name = %s
              AND source_layer = 'N4_trigger'
              AND partition_key = ANY(%s)
            """,
            (context.lineage.consumer_name, partitions),
        )
        checkpoint_count = int(cur.fetchone()["row_count"])
    return {
        "fresh": inbox_count == 0 and checkpoint_count == 0,
        "existing_inbox_count": inbox_count,
        "existing_checkpoint_count": checkpoint_count,
        "candidate_event_count": len(event_ids),
        "candidate_partition_count": len(partitions),
    }


def _verify_trade_date_proof(cur: Any, context: N5BoundedContext, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    mismatches: list[dict[str, Any]] = []
    missing_proof: list[dict[str, Any]] = []
    joined_proof: list[dict[str, Any]] = []
    for row in rows:
        payload = row.get("payload_json") if isinstance(row.get("payload_json"), Mapping) else {}
        event_id = str(row.get("event_id") or "")
        outbox_trade_date = str(row.get("trade_date") or "")
        payload_trade_date = str(payload.get("trade_date") or "")
        if not outbox_trade_date:
            missing_proof.append({"event_id": event_id, "source": "outbox.trade_date"})
        elif outbox_trade_date != context.lineage.for_trade_date:
            mismatches.append({"event_id": row.get("event_id"), "source": "outbox", "trade_date": outbox_trade_date})
        if payload_trade_date and payload_trade_date != context.lineage.for_trade_date:
            mismatches.append({"event_id": row.get("event_id"), "source": "payload", "trade_date": payload_trade_date})
        trigger_state_id = payload.get("trigger_state_id")
        trigger_match_id = payload.get("source_trigger_match_id") or payload.get("trigger_match_id")
        if not trigger_state_id or not trigger_match_id:
            missing_proof.append({"event_id": event_id, "source": "joined_trigger_rows", "reason": "missing_trigger_state_or_match_id"})
            continue
        trigger_match, trigger_state = _fetch_joined_trigger_proof(cur, trigger_state_id, trigger_match_id)
        if not trigger_match:
            missing_proof.append({"event_id": event_id, "source": "common_trigger_match", "trigger_match_id": str(trigger_match_id)})
        if not trigger_state:
            missing_proof.append({"event_id": event_id, "source": "common_trigger_state", "trigger_state_id": str(trigger_state_id)})
        trigger_match_trade_date = str((trigger_match or {}).get("for_trade_date") or "")
        trigger_state_trade_date = str((trigger_state or {}).get("for_trade_date") or "")
        if trigger_match and trigger_match_trade_date != context.lineage.for_trade_date:
            mismatches.append({"event_id": event_id, "source": "trigger_match", "trade_date": trigger_match_trade_date})
        if trigger_state and trigger_state_trade_date != context.lineage.for_trade_date:
            mismatches.append({"event_id": event_id, "source": "trigger_state", "trade_date": trigger_state_trade_date})
        if trigger_match and trigger_state:
            joined_proof.append(
                {
                    "event_id": event_id,
                    "trigger_match_id": str(trigger_match_id),
                    "trigger_state_id": str(trigger_state_id),
                    "trigger_match_for_trade_date": trigger_match_trade_date,
                    "trigger_state_for_trade_date": trigger_state_trade_date,
                }
            )
    trigger_match_dates = sorted({proof["trigger_match_for_trade_date"] for proof in joined_proof if proof.get("trigger_match_for_trade_date")})
    trigger_state_dates = sorted({proof["trigger_state_for_trade_date"] for proof in joined_proof if proof.get("trigger_state_for_trade_date")})
    return {
        "passed": not mismatches and not missing_proof,
        "mismatch_count": len(mismatches),
        "missing_proof_count": len(missing_proof),
        "mismatches_sample": mismatches[:20],
        "missing_proof_sample": missing_proof[:20],
        "missing_proof_event_ids": [item["event_id"] for item in missing_proof[:20]],
        "joined_proof_count": len(joined_proof),
        "joined_proof_sample": joined_proof[:20],
        "trigger_match_for_trade_date": trigger_match_dates[0] if len(trigger_match_dates) == 1 else "mixed" if trigger_match_dates else None,
        "trigger_state_for_trade_date": trigger_state_dates[0] if len(trigger_state_dates) == 1 else "mixed" if trigger_state_dates else None,
    }


def _fetch_joined_trigger_proof(cur: Any, trigger_state_id: Any, trigger_match_id: Any) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
    cur.execute(
        """
        SELECT trigger_match_id, trigger_state_id, run_id, for_trade_date
        FROM common_trigger_match
        WHERE trigger_match_id = %s
        """,
        (trigger_match_id,),
    )
    trigger_match = cur.fetchone()
    cur.execute(
        """
        SELECT trigger_state_id, run_id, for_trade_date, current_status, last_trigger_match_id
        FROM common_trigger_state
        WHERE trigger_state_id = %s
        """,
        (trigger_state_id,),
    )
    trigger_state = cur.fetchone()
    return trigger_match, trigger_state


def _trigger_state_and_match_ids(row: Mapping[str, Any]) -> tuple[Any, Any]:
    payload = row.get("payload_json") if isinstance(row.get("payload_json"), Mapping) else {}
    return payload.get("trigger_state_id"), payload.get("source_trigger_match_id") or payload.get("trigger_match_id")


def _fetch_trigger_state(cur: Any, trigger_state_id: Any) -> Mapping[str, Any] | None:
    cur.execute(
        """
        SELECT trigger_state_id, run_id, for_trade_date, current_status, last_trigger_match_id
        FROM common_trigger_state
        WHERE trigger_state_id = %s
        """,
        (trigger_state_id,),
    )
    return cur.fetchone()


def _current_trigger_failure(
    context: N5BoundedContext,
    row: Mapping[str, Any],
    state: Mapping[str, Any] | None,
    *,
    trigger_state_id: Any,
    trigger_match_id: Any,
) -> dict[str, Any] | None:
    event_id = row.get("event_id")
    if not trigger_state_id or not trigger_match_id:
        return {"event_id": event_id, "reason": "missing_trigger_state_or_match_id"}
    if not state:
        return {"event_id": event_id, "reason": "trigger_state_missing", "trigger_state_id": str(trigger_state_id)}
    if str(state.get("run_id") or "") != context.lineage.source_trigger_run_id:
        return {"event_id": event_id, "reason": "source_trigger_run_id_mismatch", "state": dict(state)}
    if str(state.get("for_trade_date") or "") != context.lineage.for_trade_date:
        return {"event_id": event_id, "reason": "for_trade_date_mismatch", "state": dict(state)}
    if str(state.get("current_status") or "") != "matched":
        return {"event_id": event_id, "reason": "current_status_not_matched", "state": dict(state)}
    if str(state.get("last_trigger_match_id") or "") != str(trigger_match_id):
        return {"event_id": event_id, "reason": "last_trigger_match_id_mismatch", "state": dict(state)}
    return None


def _filter_current_trigger_matched_rows(
    cur: Any,
    context: N5BoundedContext,
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    current_rows: list[dict[str, Any]] = []
    stale_failures: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    for row in rows:
        trigger_state_id, trigger_match_id = _trigger_state_and_match_ids(row)
        state = _fetch_trigger_state(cur, trigger_state_id) if trigger_state_id else None
        failure = _current_trigger_failure(
            context,
            row,
            state,
            trigger_state_id=trigger_state_id,
            trigger_match_id=trigger_match_id,
        )
        if failure:
            stale_failures.append(failure)
            reason_counts[str(failure.get("reason") or "unknown")] += 1
            continue
        current_rows.append(dict(row))

    passed = bool(current_rows)
    return current_rows, {
        "enabled": True,
        "passed": passed,
        "reason": None if passed else "current_only_no_current_trigger_matched",
        "criteria": {
            "current_status": "matched",
            "last_trigger_match_id": "payload.source_trigger_match_id_or_trigger_match_id",
            "source_trigger_run_id": context.lineage.source_trigger_run_id,
            "for_trade_date": context.lineage.for_trade_date,
        },
        "source_candidate_count": len(rows),
        "selected_current_count": len(current_rows),
        "excluded_stale_count": len(stale_failures),
        "excluded_stale_sample": stale_failures[:20],
        "stale_reason_counts": dict(sorted(reason_counts.items())),
        "filter_applied_before_action_plan": True,
    }


def _verify_stale_trigger_preflight(cur: Any, context: N5BoundedContext, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for row in rows:
        trigger_state_id, trigger_match_id = _trigger_state_and_match_ids(row)
        state = _fetch_trigger_state(cur, trigger_state_id) if trigger_state_id else None
        failure = _current_trigger_failure(
            context,
            row,
            state,
            trigger_state_id=trigger_state_id,
            trigger_match_id=trigger_match_id,
        )
        if failure:
            failures.append(failure)
    return {
        "passed": not failures,
        "checked_count": len(rows),
        "stale_count": len(failures),
        "failures_sample": failures[:20],
    }


def _verify_metric_preflight(
    cur: Any,
    context: N5BoundedContext,
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], Mapping[Any, Mapping[str, Any]], Mapping[Any, Sequence[Mapping[str, Any]]]]:
    from ashare_v3.action.execute import resolve_action_confirmation_metrics_for_execute

    join = resolve_action_confirmation_metrics_for_execute(
        cur,
        rows,
        baseline_report={"metric_run_id": context.lineage.source_metric_run_id},
    )
    summary = dict(join.get("summary") or {})
    n4_trigger_matched_rows = int(summary.get("n4_trigger_matched_rows", summary.get("matched_rows") or 0) or 0)
    joined_n4_rows = int(summary.get("joined_n4_rows", summary.get("joined_rows") or 0) or 0)
    missing_n4_rows = int(summary.get("missing_n4_rows", summary.get("missing_rows") or 0) or 0)
    duplicate_join_key_count = int(summary.get("duplicate_join_key_count") or 0)
    duplicate_join_key_rows = int(summary.get("duplicate_join_key_rows") or 0)
    passed = (
        n4_trigger_matched_rows == len(rows)
        and joined_n4_rows == len(rows)
        and missing_n4_rows == 0
        and duplicate_join_key_count == 0
        and duplicate_join_key_rows == 0
    )
    return (
        {
            "passed": passed,
            **summary,
            "metric_run_id": context.lineage.source_metric_run_id,
            "n4_trigger_matched_rows": n4_trigger_matched_rows,
            "joined_n4_rows": joined_n4_rows,
            "missing_n4_rows": missing_n4_rows,
            "duplicate_join_key_count": duplicate_join_key_count,
            "duplicate_join_key_rows": duplicate_join_key_rows,
        },
        list(join.get("outbox_rows") or []),
        join.get("action_confirmation_metric_facts") or {},
        join.get("action_confirmation_metric_facts_by_identity") or {},
    )


def _build_action_event_counts_from_plan(
    context: N5BoundedContext,
    rows: Sequence[Mapping[str, Any]],
    metric_facts: Mapping[Any, Mapping[str, Any]],
) -> dict[str, int]:
    counts, _summary = _build_action_plan_summaries(context, rows, metric_facts, {})
    return counts


def _build_action_plan_summaries(
    context: N5BoundedContext,
    rows: Sequence[Mapping[str, Any]],
    metric_facts: Mapping[Any, Mapping[str, Any]],
    metric_facts_by_identity: Mapping[Any, Sequence[Mapping[str, Any]]],
) -> tuple[dict[str, int], dict[str, int]]:
    from ashare_v3.action.consumer_dry_run import empty_inbox_keys
    from ashare_v3.action.execute import build_executable_plan_from_rows

    plan = build_executable_plan_from_rows(
        outbox_rows=rows,
        action_run_id=context.lineage.action_run_id,
        consumer_name=context.lineage.consumer_name,
        existing_inbox_keys=empty_inbox_keys(),
        existing_checkpoints={},
        action_confirmation_metric_facts=metric_facts,
        action_confirmation_metric_facts_by_identity=metric_facts_by_identity,
    )
    counts = zero_action_event_counts()
    live_summary = {
        "opened_tracking": 0,
        "executed_from_window": 0,
        "still_pending": 0,
        "expired": 0,
        "one_shot_blocked": 0,
        "executed_metric_count": 0,
        "multi_action_trigger_count": 0,
        "max_actions_per_trigger": 0,
    }
    actions_by_trigger: Counter[str] = Counter()
    for row in plan.get("action_write_plan") or []:
        trace = row.get("trace_json") if isinstance(row.get("trace_json"), Mapping) else {}
        window = trace.get("live_window_confirmation") if isinstance(trace.get("live_window_confirmation"), Mapping) else {}
        event_type = str(row.get("planned_output_event_type") or "")
        if window and event_type == "ActionExecuted" and window.get("executed_from_window") is True:
            live_summary["executed_from_window"] += 1
            live_summary["executed_metric_count"] += 1
            trigger_id = str(row.get("source_trigger_event_id") or "")
            if trigger_id:
                actions_by_trigger[trigger_id] += 1
        elif window and event_type == "ActionEligible":
            live_summary["opened_tracking"] += 1
            live_summary["still_pending"] += 1
        elif event_type == "ActionSkipped" and str(row.get("action_state") or "") == "expired":
            live_summary["expired"] += 1
        elif event_type == "ActionBlocked" and not window:
            live_summary["one_shot_blocked"] += 1
    live_summary["multi_action_trigger_count"] = sum(1 for count in actions_by_trigger.values() if count > 1)
    live_summary["max_actions_per_trigger"] = max(actions_by_trigger.values(), default=0)
    for row in plan.get("output_event_plan") or []:
        event_type = str(row.get("event_type") or "")
        if event_type in counts:
            counts[event_type] = int(row.get("planned_event_count") or 0)
    return counts, live_summary


def _default_post_check_action_run(context: N5BoundedContext, preflight: Mapping[str, Any]) -> dict[str, Any]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as exc:  # pragma: no cover - environment guard.
        return {"state": "unresolved", "reason": f"psycopg_unavailable:{exc.__class__.__name__}"}

    try:
        with psycopg.connect(
            context.dsn,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            action_run_exists = _count_where(cur, "common_action_run", "run_id = %s", (context.lineage.action_run_id,))
            fact_count = sum(
                _count_where(cur, table, "run_id = %s", (context.lineage.action_run_id,))
                for table in ("stock_action_fact", "index_action_fact", "board_action_fact")
            )
            tracking_count = _count_where(cur, "common_action_tracking_state", "run_id = %s", (context.lineage.action_run_id,))
            action_event_counts = _count_action_events(cur, context.lineage.action_run_id)
            n5_outbox_count = _count_where(
                cur,
                "common_event_outbox",
                "source_layer = 'N5_action' AND source_run_id = %s",
                (context.lineage.action_run_id,),
            )
            inbox_count = _count_candidate_inbox(cur, context, preflight)
            checkpoint_count = _count_where(
                cur,
                "common_event_consumer_checkpoint",
                "consumer_name = %s AND source_layer = 'N4_trigger' AND checkpoint_payload->>'action_run_id' = %s",
                (context.lineage.consumer_name, context.lineage.action_run_id),
            )
            downstream_refs = _downstream_refs(cur, context)
    except Exception as exc:  # pragma: no cover - live DB only.
        return {"state": "unresolved", "reason": f"post_check_query_failed:{exc.__class__.__name__}"}

    scoped_counts = {
        "common_action_run": action_run_exists,
        "action_fact": fact_count,
        "common_action_tracking_state": tracking_count,
        "common_event_outbox_n5": n5_outbox_count,
        "common_event_inbox_n4_candidates": inbox_count,
        "common_event_consumer_checkpoint": checkpoint_count,
    }
    any_scoped = any(scoped_counts.values()) or any(action_event_counts.values())
    if action_run_exists and not downstream_refs:
        state = "committed"
    elif not any_scoped and not downstream_refs:
        state = "rolled_back"
    else:
        state = "unresolved"
    return {
        "state": state,
        "scoped_counts": scoped_counts,
        "action_event_counts": action_event_counts,
        "downstream_refs": downstream_refs,
    }


def _early_blocked_manifest(
    args: argparse.Namespace,
    stop_reason: str,
    *,
    repo_root: str | Path | None,
    now: datetime | None,
) -> dict[str, Any]:
    safe_args = argparse.Namespace(**vars(args))
    safe_args.for_trade_date = _maybe_trade_date(safe_args.for_trade_date)
    safe_args.source_trigger_run_id = str(safe_args.source_trigger_run_id or "")
    safe_args.source_metric_run_id = str(safe_args.source_metric_run_id or "")
    safe_args.projection_run_id = str(safe_args.projection_run_id or "")
    safe_args.action_run_id = str(safe_args.action_run_id or "")
    safe_args.consumer_name = str(safe_args.consumer_name or "")
    safe_args.source_event_type = str(safe_args.source_event_type or "")
    safe_args.status_json = safe_args.status_json or "docs/N5_BOUNDED_ACTION_WORKER_status.json"
    safe_args.manifest_json = safe_args.manifest_json or "docs/N5_BOUNDED_ACTION_WORKER_manifest.json"
    safe_args.rollback_sql_path = safe_args.rollback_sql_path or "sql/N5_BOUNDED_ACTION_WORKER_rollback.sql"
    lineage = ExplicitLineage(
        for_trade_date=safe_args.for_trade_date,
        source_trigger_run_id=safe_args.source_trigger_run_id,
        source_metric_run_id=safe_args.source_metric_run_id,
        projection_run_id=safe_args.projection_run_id,
        action_run_id=safe_args.action_run_id,
        consumer_name=safe_args.consumer_name,
        source_event_type=safe_args.source_event_type,
    )
    context = build_n5_bounded_context(lineage, safe_args, repo_root=repo_root, now=now)
    manifest = build_n5_manifest(
        context,
        result=BoundedResult.BLOCKED,
        stop_reason=stop_reason,
        args=safe_args,
        child_result={"child_invoked": False},
        classification={"requires_post_check": False, "action_event_counts": zero_action_event_counts()},
    )
    write_final_status(context, manifest)
    return manifest


def _classify_failed_or_ambiguous_child(
    stop_reason: str,
    post_check: Mapping[str, Any],
    preflight: Mapping[str, Any],
    *,
    counts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    state = str(post_check.get("state") or "unresolved")
    if state == "rolled_back":
        result = BoundedResult.CRASHED
        requires_post_check = False
    else:
        result = BoundedResult.COMMIT_UNKNOWN
        requires_post_check = True
    return {
        "result": result,
        "stop_reason": stop_reason,
        "requires_post_check": requires_post_check,
        "post_check": dict(post_check),
        "action_event_counts": _merge_action_counts(counts or preflight_action_event_counts(preflight), post_check.get("action_event_counts")),
        "rollback_artifacts": {},
    }


def _load_child_report(path: Path, expected_action_run_id: str) -> dict[str, Any]:
    if not path.exists():
        return {"report": {}, "error": "child_report_missing"}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"report": {}, "error": "child_report_invalid_json"}
    report_run_id = str(report.get("action_run_id") or report.get("smoke_run_id") or "")
    if report_run_id != expected_action_run_id:
        return {"report": report, "error": "child_report_action_run_id_mismatch"}
    return {"report": report, "error": None}


def _event_counts_from_child_report(report: Mapping[str, Any]) -> dict[str, int]:
    counts = zero_action_event_counts()
    candidates = [
        report.get("action_event_counts"),
        (report.get("output_event_plan_summary") or {}).get("by_event_type") if isinstance(report.get("output_event_plan_summary"), Mapping) else None,
        (report.get("output_event_plan") or {}).get("by_event_type") if isinstance(report.get("output_event_plan"), Mapping) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            counts.update({key: int(value or 0) for key, value in candidate.items() if key in counts})
            break
    return counts


def _merge_action_counts(primary: Mapping[str, Any] | None, secondary: Mapping[str, Any] | None) -> dict[str, int]:
    counts = zero_action_event_counts()
    for source in (primary, secondary):
        if not isinstance(source, Mapping):
            continue
        for key in counts:
            counts[key] = max(counts[key], int(source.get(key) or 0))
    return counts


def _normalize_child_result(result: Mapping[str, Any] | Any) -> dict[str, Any]:
    if isinstance(result, Mapping):
        output = dict(result)
    else:
        output = {
            "result": getattr(result, "result", None),
            "returncode": getattr(result, "returncode", None),
            "timed_out": getattr(result, "timed_out", False),
            "stdout_tail": getattr(result, "stdout_tail", ""),
            "stderr_tail": getattr(result, "stderr_tail", ""),
        }
    if not output.get("result"):
        output["result"] = BoundedResult.PASS if output.get("returncode") == 0 else BoundedResult.CRASHED
    output.setdefault("timed_out", False)
    output.setdefault("requires_post_check", output["result"] in {BoundedResult.UNKNOWN_AFTER_TIMEOUT, BoundedResult.COMMIT_UNKNOWN})
    return output


def _run_child_command(command: Sequence[str], timeout_seconds: float | None) -> dict[str, Any]:
    return run_child_with_timeout(command, timeout_seconds)


def _no_external_side_effects() -> dict[str, Any]:
    return {
        "db_write": False,
        "worker_started": False,
        "n6_writes": 0,
        "real_trade_api_calls": 0,
        "sim_writes": 0,
        "voice_writes": 0,
        "mobile_writes": 0,
        "position_writes": 0,
        "order_writes": 0,
    }


def _normalize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output = dict(row)
    payload = output.get("payload_json")
    if isinstance(payload, str):
        try:
            output["payload_json"] = json.loads(payload)
        except json.JSONDecodeError:
            output["payload_json"] = {}
    elif payload is None:
        output["payload_json"] = {}
    return output


def _count_where(cur: Any, table: str, where_sql: str, params: Sequence[Any]) -> int:
    cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table} WHERE {where_sql}", tuple(params))
    return int(cur.fetchone()["row_count"])


def _count_candidate_inbox(cur: Any, context: N5BoundedContext, preflight: Mapping[str, Any]) -> int:
    event_ids = [str(item) for item in preflight.get("candidate_event_ids") or [] if str(item)]
    if not event_ids:
        return 0
    cur.execute(
        """
        SELECT count(*)::bigint AS row_count
        FROM common_event_inbox
        WHERE consumer_name = %s
          AND source_layer = 'N4_trigger'
          AND source_run_id = %s
          AND event_id = ANY(%s)
        """,
        (context.lineage.consumer_name, context.lineage.source_trigger_run_id, event_ids),
    )
    return int(cur.fetchone()["row_count"])


def _count_action_events(cur: Any, action_run_id: str) -> dict[str, int]:
    counts = zero_action_event_counts()
    cur.execute(
        """
        SELECT event_type, count(*)::bigint AS row_count
        FROM common_action_event
        WHERE run_id = %s
        GROUP BY event_type
        """,
        (action_run_id,),
    )
    for row in cur.fetchall():
        event_type = str(row.get("event_type") or "")
        if event_type in counts:
            counts[event_type] = int(row.get("row_count") or 0)
    return counts


def _downstream_refs(cur: Any, context: N5BoundedContext) -> dict[str, int]:
    refs: dict[str, int] = {}
    tables = (
        "user_projection_run",
        "user_card_projection",
        "user_signal_projection",
        "user_notification_queue",
        "user_voice_delivery",
        "mobile_projection",
        "mobile_notification_queue",
        "sim_projection",
        "sim_order",
        "sim_trade",
        "common_position_state",
        "common_position_event",
        "common_order",
        "common_order_event",
        "order_event",
        "real_order",
        "user_order",
    )
    for table in tables:
        cur.execute("SELECT to_regclass(%s) AS table_regclass", (f"public.{table}",))
        if not cur.fetchone()["table_regclass"]:
            continue
        cur.execute(
            f"SELECT count(*)::bigint AS row_count FROM {table} WHERE to_jsonb({table})::text LIKE %s OR to_jsonb({table})::text LIKE %s",
            (f"%{context.lineage.action_run_id}%", f"%{context.lineage.source_trigger_run_id}%"),
        )
        count = int(cur.fetchone()["row_count"])
        if count:
            refs[table] = count
    return refs


def _required_arg(args: argparse.Namespace, name: str) -> str:
    value = getattr(args, name, None)
    if value is None or str(value).strip() == "":
        raise N5BoundedBlocked(f"{name} is required")
    return str(value)


def _validate_trade_date(value: str) -> str:
    if not TRADE_DATE_RE.fullmatch(value):
        raise N5BoundedBlocked("for_trade_date must be YYYYMMDD")
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError as exc:
        raise N5BoundedBlocked("for_trade_date must be a real date") from exc
    return value


def _validate_explicit_value(name: str, value: str) -> str:
    if value in IMPLICIT_LINEAGE_VALUES:
        raise N5BoundedBlocked(f"{name} cannot use implicit lineage selector")
    if not value.strip():
        raise N5BoundedBlocked(f"{name} is required")
    return value


def _maybe_trade_date(value: Any) -> str:
    text = str(value or "")
    if TRADE_DATE_RE.fullmatch(text):
        return text
    return "19700101"


def _resolve_repo_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def _safe_artifact_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "unknown"))
    return safe[:120] or "unknown"


def _sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _sql_text_array(values: Sequence[str]) -> str:
    literals = ", ".join(_sql_literal(str(value)) for value in values if str(value))
    if not literals:
        return "ARRAY[]::text[]"
    return f"ARRAY[{literals}]::text[]"


if __name__ == "__main__":
    raise SystemExit(main())
