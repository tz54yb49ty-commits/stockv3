#!/usr/bin/env python3
"""Run one N3 Phase 1 B1/C1/B2 bounded worker invocation.

This wrapper owns orchestration only. It reuses the existing N3 supervisor
child-step plan, child artifact generation, command guard, and PR-1 bounded
runtime utilities. It does not call the legacy auto-poll wrapper opaquely, loop,
enter N4/N5/N6, install schedulers, consume outbox, or perform rollback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from ashare_v3.market.intraday_child_artifacts import (
    IntradayChildArtifactConflictError,
    IntradayChildArtifactRequest,
    build_intraday_child_artifact_plan,
    write_intraday_child_artifacts,
)
from ashare_v3.market.intraday_supervisor import (
    build_intraday_supervisor_plan,
    validate_child_command,
)
from ashare_v3.runtime.bounded_worker_control import (
    BoundedResult,
    BoundedWorkerConfig,
    BoundedWorkerStatus,
    SingletonLockHeld,
    acquire_global_chain_lock,
    atomic_write_json,
    build_phase1_realtime_chain_lock_path,
    check_stop_file,
    deadline_from_now,
    remaining_deadline_seconds,
    result_to_exit_code,
    run_child_with_timeout,
)

try:
    from check_condition_source_ready import DEFAULT_DSN
except ImportError:  # pragma: no cover - package import fallback
    from scripts.check_condition_source_ready import DEFAULT_DSN


ASIA_SHANGHAI = timezone(timedelta(hours=8))
STAGE_ORDER = ("B1", "C1", "B2")
WORKER_NAME = "n3_phase1_bounded_worker"
IMPLICIT_LINEAGE_VALUES = {"latest", "active", "fallback", "auto", "auto-resolve", "auto_resolve"}
RUN_ID_KEYS = {"B1": "snapshot_run_id", "C1": "today_minute_run_id", "B2": "projection_run_id"}
ASSET_KINDS = ("stock", "index", "board")
SUBSCRIPTION_COUNT_KINDS = ("realtime_daily_snapshot", "minute_bar_1m")
CHILD_DIAGNOSTIC_TAIL_CHARS = 4000


@dataclass(frozen=True)
class N3BoundedContext:
    repo_root: Path
    lineage: dict[str, str]
    config: BoundedWorkerConfig
    wrapper_run_id: str
    deadline: datetime | None
    dsn: str
    docs_root: Path
    sql_root: Path
    python_executable: str
    status_json: Path
    rollback_manifest_json: Path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one N3 Phase 1 bounded worker B1/C1/B2 plan.")
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--source-condition-run-id", required=True)
    parser.add_argument("--source-subscription-run-id", required=True)
    parser.add_argument("--previous-day-preload-run-id", required=True)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", ""))
    parser.add_argument("--status-json", required=True)
    parser.add_argument("--rollback-manifest-json", required=True)
    parser.add_argument("--stop-file", default="")
    parser.add_argument("--max-runtime-seconds", type=float, default=None)
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--docs-root", default="docs")
    parser.add_argument("--sql-root", default="sql")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def build_explicit_lineage(
    *,
    for_trade_date: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    previous_day_preload_run_id: str,
) -> dict[str, str]:
    trade_date = _validate_trade_date(for_trade_date)
    lineage = {
        "for_trade_date": trade_date,
        "source_condition_run_id": _validate_explicit_run_id("source_condition_run_id", source_condition_run_id),
        "source_subscription_run_id": _validate_explicit_run_id("source_subscription_run_id", source_subscription_run_id),
        "previous_day_preload_run_id": _validate_explicit_run_id("previous_day_preload_run_id", previous_day_preload_run_id),
    }
    match = re.search(r"_for_(\d{8})(?:__|$)", lineage["previous_day_preload_run_id"])
    if match and match.group(1) != trade_date:
        raise ValueError("previous_day_preload_run_id trade_date does not match for_trade_date")
    return lineage


def build_n3_bounded_context(
    *,
    repo_root: str | Path,
    for_trade_date: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    previous_day_preload_run_id: str,
    dsn: str,
    status_json: str | Path,
    rollback_manifest_json: str | Path,
    stop_file: str | Path | None = None,
    max_runtime_seconds: float | int | None = None,
    python_executable: str = sys.executable,
    docs_root: str | Path = "docs",
    sql_root: str | Path = "sql",
    now: datetime | None = None,
) -> N3BoundedContext:
    root = Path(repo_root)
    lineage = build_explicit_lineage(
        for_trade_date=for_trade_date,
        source_condition_run_id=source_condition_run_id,
        source_subscription_run_id=source_subscription_run_id,
        previous_day_preload_run_id=previous_day_preload_run_id,
    )
    config = BoundedWorkerConfig(
        worker_name=WORKER_NAME,
        trade_date=lineage["for_trade_date"],
        lock_path=build_phase1_realtime_chain_lock_path(root, lineage["for_trade_date"]),
        status_json=status_json,
        stop_file=stop_file or None,
        max_runtime_seconds=max_runtime_seconds,
        run_id_prefix=WORKER_NAME,
        input_run_ids={
            "source_condition_run_id": lineage["source_condition_run_id"],
            "source_subscription_run_id": lineage["source_subscription_run_id"],
            "previous_day_preload_run_id": lineage["previous_day_preload_run_id"],
        },
    )
    return N3BoundedContext(
        repo_root=root,
        lineage=lineage,
        config=config,
        wrapper_run_id=config.make_run_id(now=now),
        deadline=deadline_from_now(max_runtime_seconds, now=now),
        dsn=dsn,
        docs_root=Path(docs_root),
        sql_root=Path(sql_root),
        python_executable=python_executable,
        status_json=Path(status_json),
        rollback_manifest_json=Path(rollback_manifest_json),
    )


def execute_child_stage(
    *,
    step: Mapping[str, Any],
    context: N3BoundedContext,
    child_runner: Callable[..., Mapping[str, Any]],
    remaining_seconds: float | None,
) -> dict[str, Any]:
    command = list(step.get("command") or [])
    validate_child_command(command)
    result = dict(child_runner(command, timeout_seconds=remaining_seconds, cwd=context.repo_root))
    result.setdefault("returncode", 0)
    result.setdefault("timed_out", False)
    result.setdefault("result", BoundedResult.PASS if int(result.get("returncode") or 0) == 0 else BoundedResult.CRASHED)
    result.setdefault("requires_post_check", bool(result.get("timed_out")))
    result["stage"] = step.get("stage")
    result["run_id"] = step.get("run_id")
    return result


def fetch_db_subscription_summary(*, dsn: str, subscription_run_id: str) -> dict[str, Any]:
    """Read authoritative subscription counts for bounded child artifact contracts."""

    with psycopg.connect(
        _resolved_dsn(dsn),
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT asset_kind, required_data_kind, count(DISTINCT identity_key) AS object_count
            FROM common_market_data_subscription
            WHERE run_id = %s
              AND required_data_kind = ANY(%s)
            GROUP BY asset_kind, required_data_kind
            """,
            (subscription_run_id, list(SUBSCRIPTION_COUNT_KINDS)),
        )
        rows = cur.fetchall()
    return build_db_subscription_summary_from_count_rows(rows, subscription_run_id)


def build_db_subscription_summary_from_count_rows(
    rows: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    subscription_run_id: str,
) -> dict[str, Any]:
    counts = {kind: {asset: 0 for asset in ASSET_KINDS} for kind in SUBSCRIPTION_COUNT_KINDS}
    for row in rows:
        data_kind = str(row.get("required_data_kind") or "")
        asset_kind = str(row.get("asset_kind") or "")
        if data_kind in counts and asset_kind in counts[data_kind]:
            counts[data_kind][asset_kind] = int(row.get("object_count") or 0)

    if not any(counts["realtime_daily_snapshot"].values()):
        raise RuntimeError(
            f"subscription rows missing for {subscription_run_id}: "
            "realtime_daily_snapshot counts are zero"
        )

    return {
        "source": "db_subscription_rows",
        "source_run_id": subscription_run_id,
        "snapshot_object_count_by_asset_kind": counts["realtime_daily_snapshot"],
        "today_minute_object_count_by_asset_kind": counts["minute_bar_1m"],
    }


def classify_child_result(
    *,
    step: Mapping[str, Any],
    child_result: Mapping[str, Any],
    completed_stages: list[str],
    output_run_ids: Mapping[str, Any],
    rollback_artifacts: Mapping[str, Any],
    post_check: Mapping[str, Any],
    artifact_validation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    stage = str(step.get("stage"))
    current_committed = post_check.get("state") == "committed"
    current_rolled_back = post_check.get("state") == "rolled_back"
    returncode = int(child_result.get("returncode") or 0)
    timed_out = bool(child_result.get("timed_out")) or child_result.get("result") == BoundedResult.UNKNOWN_AFTER_TIMEOUT

    if timed_out:
        return _terminal(BoundedResult.UNKNOWN_AFTER_TIMEOUT, f"child_timeout_{stage}", True)

    if artifact_validation and not artifact_validation.get("valid"):
        reason = str(artifact_validation.get("reason") or "artifact_invalid")
        if reason == "rollback_missing" and current_committed:
            return _terminal(BoundedResult.CRASHED, f"artifact_contract_corruption_{stage}", False)
        if current_rolled_back:
            return _terminal(BoundedResult.CRASHED, f"child_report_{reason}_{stage}", False)
        return _terminal(BoundedResult.COMMIT_UNKNOWN, f"child_report_{reason}_{stage}", True)

    if returncode == 0:
        return {"result": BoundedResult.PASS, "stage_completed": True}

    if returncode == 2:
        if current_rolled_back:
            if completed_stages:
                return _terminal(BoundedResult.PARTIAL, f"child_controlled_blocked_{stage}", False)
            return _terminal(BoundedResult.BLOCKED, f"child_controlled_blocked_{stage}", False)
        return _terminal(BoundedResult.COMMIT_UNKNOWN, f"child_controlled_blocked_unresolved_{stage}", True)

    if returncode == 1:
        if current_rolled_back:
            return _terminal(BoundedResult.CRASHED, f"child_technical_failure_{stage}", False)
        return _terminal(BoundedResult.COMMIT_UNKNOWN, f"child_technical_failure_unresolved_{stage}", True)

    return _terminal(BoundedResult.COMMIT_UNKNOWN, f"child_commit_unknown_{stage}", True)


def post_check_stage(
    *,
    stage: str,
    run_id: str,
    context: N3BoundedContext,
    step: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        if stage == "B1":
            from ashare_v3.market.realtime_snapshot_execute import capture_snapshot_execute_backup

            evidence = capture_snapshot_execute_backup(
                context.dsn,
                phase="post_check",
                snapshot_run_id=run_id,
                source_run_id=context.lineage["source_subscription_run_id"],
                for_trade_date=context.lineage["for_trade_date"],
            )
            return {"state": _classify_b1_snapshot(evidence), "evidence": evidence}
        if stage == "C1":
            from ashare_v3.market.today_minute_execute import capture_today_minute_execute_backup

            evidence = capture_today_minute_execute_backup(
                context.dsn,
                phase="post_check",
                today_minute_run_id=run_id,
                source_run_id=context.lineage["source_subscription_run_id"],
                for_trade_date=context.lineage["for_trade_date"],
            )
            return {"state": _classify_c1_snapshot(evidence), "evidence": evidence}
        if stage == "B2":
            from ashare_v3.market.realtime_projection_execute import capture_projection_execute_snapshot

            source_runs = dict(step.get("source_runs") or {})
            source_runs.setdefault("subscription_run_id", context.lineage["source_subscription_run_id"])
            source_runs.setdefault("preload_run_id", context.lineage["previous_day_preload_run_id"])
            evidence = capture_projection_execute_snapshot(
                context.dsn,
                projection_run_id=run_id,
                source_runs=source_runs,
            )
            return {"state": _classify_b2_snapshot(evidence), "evidence": evidence}
    except Exception as exc:  # read-only evidence failed, so the result is unresolved
        return {"state": "unresolved", "evidence": {"error": str(exc)}}
    return {"state": "unresolved", "evidence": {"error": f"unsupported_stage:{stage}"}}


def build_rollback_manifest(
    *,
    context: N3BoundedContext,
    result: str,
    requires_post_check: bool,
    completed_stages: list[str],
    pending_stages: list[str],
    stage_run_ids: Mapping[str, str],
    output_run_ids: Mapping[str, Any],
    stage_reports: Mapping[str, Any],
    rollback_artifacts: Mapping[str, Any],
    partial_reason: str | None,
    child_invoked: bool,
    child_diagnostics: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "invocation_id": context.config.invocation_id,
        "wrapper_run_id": context.wrapper_run_id,
        "trade_date": context.lineage["for_trade_date"],
        "result": result,
        "requires_post_check": requires_post_check,
        "completed_stages": list(completed_stages),
        "pending_stages": list(pending_stages),
        "stage_count_total": len(STAGE_ORDER),
        "completed_stage_count": len(completed_stages),
        "processed_count_unit": "n3_plan",
        "stage_run_ids": dict(stage_run_ids),
        "output_run_ids": dict(output_run_ids),
        "stage_reports": dict(stage_reports),
        "stage_rollback_sql": dict(rollback_artifacts),
        "artifact_exists": all(item.get("exists") for item in rollback_artifacts.values()) if rollback_artifacts else False,
        "artifact_hash": {stage: item.get("sha256") for stage, item in rollback_artifacts.items()},
        "downstream_consumption_allowed": result == BoundedResult.PASS,
        "n4_consumption_allowed": result == BoundedResult.PASS,
        "partial_reason": partial_reason,
        "child_invoked": bool(child_invoked),
        "child_diagnostics": list(child_diagnostics or []),
        "input_lineage_ids": dict(context.lineage),
    }


def write_final_status(
    *,
    context: N3BoundedContext,
    result: str,
    stop_reason: str | None,
    requires_post_check: bool,
    completed_stages: list[str],
    pending_stages: list[str],
    output_run_ids: Mapping[str, Any],
    rollback_artifacts: Mapping[str, Any],
    partial_reason: str | None,
    child_invoked: bool,
    child_diagnostics: list[Mapping[str, Any]] | None = None,
    atomic_writer: Callable[[str | Path, Mapping[str, Any]], None] = atomic_write_json,
) -> dict[str, Any]:
    status = BoundedWorkerStatus(
        result=result,
        stop_reason=stop_reason,
        requires_post_check=requires_post_check,
        invocation_id=context.config.invocation_id,
        run_id=context.wrapper_run_id,
        trade_date=context.lineage["for_trade_date"],
        worker_name=WORKER_NAME,
        input_run_ids=context.config.input_run_ids,
        output_run_id=output_run_ids.get("source_metric_run_id"),
        completed_stages=completed_stages,
        pending_stages=pending_stages,
        partial_reason=partial_reason,
        output_run_ids=output_run_ids,
        rollback_artifacts=rollback_artifacts,
        downstream_consumption_allowed=result == BoundedResult.PASS,
        processed_count=1 if child_invoked or result == BoundedResult.PASS else 0,
        written_count=len(completed_stages),
        skipped_count=len(pending_stages),
        blocked_count=1 if result == BoundedResult.BLOCKED else 0,
        external_side_effects={
            "db_write": bool(completed_stages or result in {BoundedResult.UNKNOWN_AFTER_TIMEOUT, BoundedResult.COMMIT_UNKNOWN}),
            "worker_started": False,
            "n4_entered": False,
            "n5_entered": False,
            "n6_writes": 0,
            "real_trade_api_calls": 0,
            "sim_writes": 0,
            "voice_writes": 0,
            "mobile_writes": 0,
        },
    )
    payload = status.to_dict()
    payload.update(
        {
            "child_invoked": bool(child_invoked),
            "business_writes": len(completed_stages),
            "processed_count_unit": "n3_plan",
            "stage_count_total": len(STAGE_ORDER),
            "completed_stage_count": len(completed_stages),
            "downstream_consumption_allowed": result == BoundedResult.PASS,
            "n4_consumption_allowed": result == BoundedResult.PASS,
            "projection_run_id": output_run_ids.get("projection_run_id"),
            "source_metric_run_id": output_run_ids.get("source_metric_run_id"),
            "child_diagnostics": list(child_diagnostics or []),
        }
    )
    atomic_writer(context.status_json, payload)
    return payload


def run_n3_bounded_worker_once(
    *,
    for_trade_date: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    previous_day_preload_run_id: str,
    dsn: str = "",
    status_json: str | Path,
    rollback_manifest_json: str | Path,
    stop_file: str | Path | None = None,
    max_runtime_seconds: float | int | None = None,
    python_executable: str = sys.executable,
    docs_root: str | Path = "docs",
    sql_root: str | Path = "sql",
    repo_root: str | Path | None = None,
    execute: bool = False,
    user_confirmed: bool = False,
    now: datetime | None = None,
    plan_builder: Callable[..., Mapping[str, Any]] = build_intraday_supervisor_plan,
    artifact_plan_builder: Callable[..., Mapping[str, Any]] | None = None,
    artifact_writer: Callable[..., Mapping[str, Any]] = write_intraday_child_artifacts,
    artifact_validator: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    subscription_summary_fetcher: Callable[..., Mapping[str, Any]] = fetch_db_subscription_summary,
    child_runner: Callable[..., Mapping[str, Any]] = run_child_with_timeout,
    post_checker: Callable[..., Mapping[str, Any]] = post_check_stage,
    atomic_writer: Callable[[str | Path, Mapping[str, Any]], None] = atomic_write_json,
    remaining_deadline_seconds_fn: Callable[[datetime | None], float | None] = remaining_deadline_seconds,
) -> dict[str, Any]:
    try:
        context = build_n3_bounded_context(
            repo_root=repo_root or Path.cwd(),
            for_trade_date=for_trade_date,
            source_condition_run_id=source_condition_run_id,
            source_subscription_run_id=source_subscription_run_id,
            previous_day_preload_run_id=previous_day_preload_run_id,
            dsn=dsn,
            status_json=status_json,
            rollback_manifest_json=rollback_manifest_json,
            stop_file=stop_file,
            max_runtime_seconds=max_runtime_seconds,
            python_executable=python_executable,
            docs_root=docs_root,
            sql_root=sql_root,
            now=now,
        )
    except ValueError as exc:
        context = _fallback_context(
            repo_root=repo_root or Path.cwd(),
            for_trade_date=for_trade_date or "19700101",
            status_json=status_json,
            rollback_manifest_json=rollback_manifest_json,
        )
        return _finalize(
            context=context,
            result=BoundedResult.BLOCKED,
            stop_reason="lineage_invalid",
            requires_post_check=False,
            completed_stages=[],
            pending_stages=list(STAGE_ORDER),
            stage_run_ids={},
            output_run_ids={},
            stage_reports={},
            rollback_artifacts={},
            partial_reason=None,
            child_invoked=False,
            atomic_writer=atomic_writer,
            extra={"error": str(exc)},
        )

    if execute and not user_confirmed:
        return _finalize_blocked(context, "missing_user_confirmed", atomic_writer=atomic_writer)
    if user_confirmed and not execute:
        return _finalize_blocked(context, "missing_execute", atomic_writer=atomic_writer)
    if not execute:
        return _finalize(
            context=context,
            result=BoundedResult.NOOP,
            stop_reason="plan_only",
            requires_post_check=False,
            completed_stages=[],
            pending_stages=list(STAGE_ORDER),
            stage_run_ids={},
            output_run_ids={},
            stage_reports={},
            rollback_artifacts={},
            partial_reason=None,
            child_invoked=False,
            atomic_writer=atomic_writer,
        )

    lock_metadata = {
        "worker_name": WORKER_NAME,
        "invocation_id": context.config.invocation_id,
        "wrapper_run_id": context.wrapper_run_id,
        "trade_date": context.lineage["for_trade_date"],
    }
    try:
        with acquire_global_chain_lock(context.config.lock_path, metadata=lock_metadata):
            return _run_locked(
                context=context,
                plan_builder=plan_builder,
                artifact_plan_builder=artifact_plan_builder,
                artifact_writer=artifact_writer,
                artifact_validator=artifact_validator,
                subscription_summary_fetcher=subscription_summary_fetcher,
                child_runner=child_runner,
                post_checker=post_checker,
                atomic_writer=atomic_writer,
                remaining_deadline_seconds_fn=remaining_deadline_seconds_fn,
            )
    except SingletonLockHeld:
        return _finalize(
            context=context,
            result=BoundedResult.NOOP,
            stop_reason="singleton_lock_held",
            requires_post_check=False,
            completed_stages=[],
            pending_stages=list(STAGE_ORDER),
            stage_run_ids={},
            output_run_ids={},
            stage_reports={},
            rollback_artifacts={},
            partial_reason=None,
            child_invoked=False,
            atomic_writer=atomic_writer,
        )


def main(
    argv: list[str] | None = None,
    **test_overrides: Any,
) -> int:
    args = build_arg_parser().parse_args(argv)
    report = run_n3_bounded_worker_once(
        for_trade_date=args.for_trade_date,
        source_condition_run_id=args.source_condition_run_id,
        source_subscription_run_id=args.source_subscription_run_id,
        previous_day_preload_run_id=args.previous_day_preload_run_id,
        dsn=args.dsn,
        status_json=args.status_json,
        rollback_manifest_json=args.rollback_manifest_json,
        stop_file=args.stop_file or None,
        max_runtime_seconds=args.max_runtime_seconds,
        python_executable=args.python_executable,
        docs_root=args.docs_root,
        sql_root=args.sql_root,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
        **test_overrides,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return result_to_exit_code(report["result"])


def _run_locked(
    *,
    context: N3BoundedContext,
    plan_builder: Callable[..., Mapping[str, Any]],
    artifact_plan_builder: Callable[..., Mapping[str, Any]] | None,
    artifact_writer: Callable[..., Mapping[str, Any]],
    artifact_validator: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None,
    subscription_summary_fetcher: Callable[..., Mapping[str, Any]],
    child_runner: Callable[..., Mapping[str, Any]],
    post_checker: Callable[..., Mapping[str, Any]],
    atomic_writer: Callable[[str | Path, Mapping[str, Any]], None],
    remaining_deadline_seconds_fn: Callable[[datetime | None], float | None],
) -> dict[str, Any]:
    plan = dict(
        plan_builder(
            for_trade_date=context.lineage["for_trade_date"],
            subscription_run_id=context.lineage["source_subscription_run_id"],
            preload_run_id=context.lineage["previous_day_preload_run_id"],
            passed_run_ids=set(),
            python_executable=context.python_executable,
            docs_root=context.docs_root,
            sql_root=context.sql_root,
        )
    )
    stage_run_ids = _extract_stage_run_ids(plan)
    steps = list(plan.get("child_steps") or [])
    if plan.get("status") != "ready":
        return _finalize_blocked(context, f"plan_not_ready:{plan.get('reason')}", stage_run_ids=stage_run_ids, atomic_writer=atomic_writer)
    if tuple(step.get("stage") for step in steps) != STAGE_ORDER:
        return _finalize_blocked(context, "incomplete_n3_stage_plan", stage_run_ids=stage_run_ids, atomic_writer=atomic_writer)
    for step in steps:
        try:
            validate_child_command(list(step.get("command") or []))
        except ValueError as exc:
            return _finalize_blocked(context, f"forbidden_command:{exc}", stage_run_ids=stage_run_ids, atomic_writer=atomic_writer)

    stopped, reason = check_stop_file(context.config.stop_file)
    if stopped:
        return _finalize(
            context=context,
            result=BoundedResult.NOOP,
            stop_reason=reason,
            requires_post_check=False,
            completed_stages=[],
            pending_stages=list(STAGE_ORDER),
            stage_run_ids=stage_run_ids,
            output_run_ids={},
            stage_reports={},
            rollback_artifacts={},
            partial_reason=None,
            child_invoked=False,
            atomic_writer=atomic_writer,
        )
    if (remaining_deadline_seconds_fn(context.deadline) or 0.0) <= 0.0 and context.deadline is not None:
        return _finalize_blocked(context, "deadline_exhausted_before_B1", stage_run_ids=stage_run_ids, atomic_writer=atomic_writer)

    try:
        artifact_plan = _build_artifact_plan(
            context,
            plan,
            artifact_plan_builder,
            subscription_summary_fetcher,
        )
        artifact_writer(artifact_plan, allow_overwrite=False)
    except IntradayChildArtifactConflictError as exc:
        return _finalize_blocked(context, f"artifact_generation_blocked:{exc}", stage_run_ids=stage_run_ids, atomic_writer=atomic_writer)
    except Exception as exc:
        return _finalize_blocked(context, f"artifact_generation_failed:{exc}", stage_run_ids=stage_run_ids, atomic_writer=atomic_writer)
    if artifact_validator is not None:
        validation = dict(artifact_validator(artifact_plan))
        if validation.get("status") != "passed":
            return _finalize_blocked(context, "artifact_validation_failed", stage_run_ids=stage_run_ids, atomic_writer=atomic_writer)

    completed_stages: list[str] = []
    output_run_ids: dict[str, Any] = {}
    stage_reports: dict[str, Any] = {}
    rollback_artifacts: dict[str, Any] = {}
    child_invoked = False
    child_diagnostics: list[dict[str, Any]] = []

    for index, step in enumerate(steps):
        stage = str(step["stage"])
        stopped, reason = check_stop_file(context.config.stop_file)
        if stopped:
            return _finalize_partial_or_noop(
                context=context,
                stop_reason=reason,
                completed_stages=completed_stages,
                stage_run_ids=stage_run_ids,
                output_run_ids=output_run_ids,
                stage_reports=stage_reports,
                rollback_artifacts=rollback_artifacts,
                child_invoked=child_invoked,
                child_diagnostics=child_diagnostics,
                atomic_writer=atomic_writer,
            )
        remaining = remaining_deadline_seconds_fn(context.deadline)
        if remaining is not None and remaining <= 0.0:
            return _finalize_partial_or_blocked_deadline(
                context=context,
                before_stage=stage,
                completed_stages=completed_stages,
                stage_run_ids=stage_run_ids,
                output_run_ids=output_run_ids,
                stage_reports=stage_reports,
                rollback_artifacts=rollback_artifacts,
                child_invoked=child_invoked,
                child_diagnostics=child_diagnostics,
                atomic_writer=atomic_writer,
            )

        child_invoked = True
        child_result = execute_child_stage(
            step=step,
            context=context,
            child_runner=child_runner,
            remaining_seconds=remaining,
        )
        child_diagnostics.append(_child_diagnostic_entry(step, child_result))
        if bool(child_result.get("timed_out")) or child_result.get("result") == BoundedResult.UNKNOWN_AFTER_TIMEOUT:
            return _finalize_terminal(
                context=context,
                result=BoundedResult.UNKNOWN_AFTER_TIMEOUT,
                stop_reason=f"child_timeout_{stage}",
                requires_post_check=True,
                completed_stages=completed_stages,
                stage_run_ids=stage_run_ids,
                output_run_ids=output_run_ids,
                stage_reports=stage_reports,
                rollback_artifacts=rollback_artifacts,
                child_invoked=child_invoked,
                child_diagnostics=child_diagnostics,
                atomic_writer=atomic_writer,
            )

        artifact_validation = None
        if int(child_result.get("returncode") or 0) == 0:
            artifact_validation = _validate_completed_stage_artifacts(step)
        post_check = (
            post_checker(stage=stage, run_id=str(step["run_id"]), context=context, step=step)
            if int(child_result.get("returncode") or 0) != 0 or (artifact_validation and not artifact_validation.get("valid"))
            else {"state": "committed", "evidence": {"child_returncode": 0}}
        )
        classification = classify_child_result(
            step=step,
            child_result=child_result,
            completed_stages=completed_stages,
            output_run_ids=output_run_ids,
            rollback_artifacts=rollback_artifacts,
            post_check=post_check,
            artifact_validation=artifact_validation,
        )
        if classification.get("stage_completed"):
            completed_stages.append(stage)
            _record_completed_stage(
                step=step,
                output_run_ids=output_run_ids,
                stage_reports=stage_reports,
                rollback_artifacts=rollback_artifacts,
            )
            continue
        return _finalize_terminal(
            context=context,
            result=str(classification["result"]),
            stop_reason=str(classification["stop_reason"]),
            requires_post_check=bool(classification["requires_post_check"]),
            completed_stages=completed_stages,
            stage_run_ids=stage_run_ids,
            output_run_ids=output_run_ids,
            stage_reports=stage_reports,
            rollback_artifacts=rollback_artifacts,
            child_invoked=child_invoked,
            child_diagnostics=child_diagnostics,
            atomic_writer=atomic_writer,
        )

    if _source_metric_alias_invalid(output_run_ids):
        return _finalize_terminal(
            context=context,
            result=BoundedResult.CRASHED,
            stop_reason="source_metric_run_id_projection_run_id_mismatch",
            requires_post_check=False,
            completed_stages=completed_stages,
            stage_run_ids=stage_run_ids,
            output_run_ids=output_run_ids,
            stage_reports=stage_reports,
            rollback_artifacts=rollback_artifacts,
            child_invoked=child_invoked,
            child_diagnostics=child_diagnostics,
            atomic_writer=atomic_writer,
        )
    return _finalize(
        context=context,
        result=BoundedResult.PASS,
        stop_reason=None,
        requires_post_check=False,
        completed_stages=completed_stages,
        pending_stages=[],
        stage_run_ids=stage_run_ids,
        output_run_ids=output_run_ids,
        stage_reports=stage_reports,
        rollback_artifacts=rollback_artifacts,
        partial_reason=None,
        child_invoked=child_invoked,
        child_diagnostics=child_diagnostics,
        atomic_writer=atomic_writer,
    )


def _build_artifact_plan(
    context: N3BoundedContext,
    plan: Mapping[str, Any],
    artifact_plan_builder: Callable[..., Mapping[str, Any]] | None,
    subscription_summary_fetcher: Callable[..., Mapping[str, Any]],
) -> Mapping[str, Any]:
    builder = artifact_plan_builder
    subscription_summary: Mapping[str, Any] | None = None
    if builder is None:
        subscription_summary = subscription_summary_fetcher(
            dsn=context.dsn,
            subscription_run_id=context.lineage["source_subscription_run_id"],
        )

        def builder(**kwargs: Any) -> Mapping[str, Any]:
            return build_intraday_child_artifact_plan(IntradayChildArtifactRequest(**kwargs))

    return builder(
        for_trade_date=context.lineage["for_trade_date"],
        latest_closed_minute=plan.get("latest_closed_minute"),
        latest_closed_minute_hhmm=plan.get("latest_closed_minute_hhmm"),
        subscription_run_id=context.lineage["source_subscription_run_id"],
        preload_run_id=context.lineage["previous_day_preload_run_id"],
        source_condition_run_id=context.lineage["source_condition_run_id"],
        docs_root=context.docs_root,
        sql_root=context.sql_root,
        projection_input_mode=plan.get("projection_input_mode") or "closed_minute",
        subscription_summary=dict(subscription_summary) if subscription_summary is not None else None,
    )


def _validate_completed_stage_artifacts(step: Mapping[str, Any]) -> dict[str, Any]:
    report_path = Path(str(step.get("json_report_path") or ""))
    rollback_path = Path(str(step.get("rollback_sql_path") or ""))
    stage = str(step.get("stage"))
    expected_run_id = str(step.get("run_id"))
    if not report_path.exists():
        return {"valid": False, "reason": "missing", "path": str(report_path)}
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"valid": False, "reason": "illegal", "path": str(report_path)}
    report_run_id = str(report.get(RUN_ID_KEYS[stage]) or "")
    if report_run_id != expected_run_id:
        return {"valid": False, "reason": "mismatch", "path": str(report_path), "report_run_id": report_run_id}
    if not rollback_path.exists():
        return {"valid": False, "reason": "rollback_missing", "path": str(rollback_path)}
    return {"valid": True, "report": report}


def _child_diagnostic_entry(step: Mapping[str, Any], child_result: Mapping[str, Any]) -> dict[str, Any]:
    report_path_text = str(step.get("json_report_path") or "")
    report_exists = Path(report_path_text).exists() if report_path_text else False
    argv = child_result.get("argv") or step.get("command") or []
    return {
        "stage": str(step.get("stage") or child_result.get("stage") or ""),
        "run_id": str(step.get("run_id") or child_result.get("run_id") or ""),
        "argv": [str(item) for item in argv],
        "returncode": int(child_result.get("returncode") or 0),
        "timed_out": bool(child_result.get("timed_out")),
        "result": str(child_result.get("result") or ""),
        "stdout_tail": _tail_text(child_result.get("stdout")),
        "stderr_tail": _tail_text(child_result.get("stderr")),
        "report_path": report_path_text,
        "report_exists": report_exists,
    }


def _tail_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return text[-CHILD_DIAGNOSTIC_TAIL_CHARS:]


def _record_completed_stage(
    *,
    step: Mapping[str, Any],
    output_run_ids: dict[str, Any],
    stage_reports: dict[str, Any],
    rollback_artifacts: dict[str, Any],
) -> None:
    stage = str(step["stage"])
    run_id = str(step["run_id"])
    report_path = Path(str(step["json_report_path"]))
    rollback_path = Path(str(step["rollback_sql_path"]))
    if stage == "B1":
        output_run_ids["snapshot_run_id"] = run_id
    elif stage == "C1":
        output_run_ids["today_minute_run_id"] = run_id
    elif stage == "B2":
        output_run_ids["projection_run_id"] = run_id
        output_run_ids["source_metric_run_id"] = run_id
    stage_reports[stage] = _artifact_entry(report_path)
    rollback_artifacts[stage] = _artifact_entry(rollback_path)


def _artifact_entry(path: Path) -> dict[str, Any]:
    exists = path.exists()
    return {
        "path": str(path),
        "exists": exists,
        "sha256": _sha256(path) if exists else None,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _finalize_blocked(
    context: N3BoundedContext,
    reason: str,
    *,
    stage_run_ids: Mapping[str, str] | None = None,
    atomic_writer: Callable[[str | Path, Mapping[str, Any]], None],
) -> dict[str, Any]:
    return _finalize(
        context=context,
        result=BoundedResult.BLOCKED,
        stop_reason=reason,
        requires_post_check=False,
        completed_stages=[],
        pending_stages=list(STAGE_ORDER),
        stage_run_ids=stage_run_ids or {},
        output_run_ids={},
        stage_reports={},
        rollback_artifacts={},
        partial_reason=None,
        child_invoked=False,
        atomic_writer=atomic_writer,
    )


def _finalize_partial_or_noop(
    *,
    context: N3BoundedContext,
    stop_reason: str | None,
    completed_stages: list[str],
    stage_run_ids: Mapping[str, str],
    output_run_ids: Mapping[str, Any],
    stage_reports: Mapping[str, Any],
    rollback_artifacts: Mapping[str, Any],
    child_invoked: bool,
    atomic_writer: Callable[[str | Path, Mapping[str, Any]], None],
    child_diagnostics: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if not completed_stages:
        return _finalize(
            context=context,
            result=BoundedResult.NOOP,
            stop_reason=stop_reason,
            requires_post_check=False,
            completed_stages=[],
            pending_stages=list(STAGE_ORDER),
            stage_run_ids=stage_run_ids,
            output_run_ids={},
            stage_reports={},
            rollback_artifacts={},
            partial_reason=None,
            child_invoked=child_invoked,
            child_diagnostics=child_diagnostics,
            atomic_writer=atomic_writer,
        )
    return _finalize_terminal(
        context=context,
        result=BoundedResult.PARTIAL,
        stop_reason=stop_reason,
        requires_post_check=False,
        completed_stages=completed_stages,
        stage_run_ids=stage_run_ids,
        output_run_ids=output_run_ids,
        stage_reports=stage_reports,
        rollback_artifacts=rollback_artifacts,
        child_invoked=child_invoked,
        child_diagnostics=child_diagnostics,
        atomic_writer=atomic_writer,
    )


def _finalize_partial_or_blocked_deadline(
    *,
    context: N3BoundedContext,
    before_stage: str,
    completed_stages: list[str],
    stage_run_ids: Mapping[str, str],
    output_run_ids: Mapping[str, Any],
    stage_reports: Mapping[str, Any],
    rollback_artifacts: Mapping[str, Any],
    child_invoked: bool,
    atomic_writer: Callable[[str | Path, Mapping[str, Any]], None],
    child_diagnostics: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    reason = f"deadline_exhausted_before_{before_stage}"
    if not completed_stages:
        return _finalize_blocked(context, reason, stage_run_ids=stage_run_ids, atomic_writer=atomic_writer)
    return _finalize_terminal(
        context=context,
        result=BoundedResult.PARTIAL,
        stop_reason=reason,
        requires_post_check=False,
        completed_stages=completed_stages,
        stage_run_ids=stage_run_ids,
        output_run_ids=output_run_ids,
        stage_reports=stage_reports,
        rollback_artifacts=rollback_artifacts,
        child_invoked=child_invoked,
        child_diagnostics=child_diagnostics,
        atomic_writer=atomic_writer,
    )


def _finalize_terminal(
    *,
    context: N3BoundedContext,
    result: str,
    stop_reason: str,
    requires_post_check: bool,
    completed_stages: list[str],
    stage_run_ids: Mapping[str, str],
    output_run_ids: Mapping[str, Any],
    stage_reports: Mapping[str, Any],
    rollback_artifacts: Mapping[str, Any],
    child_invoked: bool,
    atomic_writer: Callable[[str | Path, Mapping[str, Any]], None],
    child_diagnostics: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    pending = _pending_stages(completed_stages)
    partial_reason = stop_reason if result == BoundedResult.PARTIAL else None
    return _finalize(
        context=context,
        result=result,
        stop_reason=stop_reason,
        requires_post_check=requires_post_check,
        completed_stages=completed_stages,
        pending_stages=pending,
        stage_run_ids=stage_run_ids,
        output_run_ids=output_run_ids,
        stage_reports=stage_reports,
        rollback_artifacts=rollback_artifacts,
        partial_reason=partial_reason,
        child_invoked=child_invoked,
        child_diagnostics=child_diagnostics,
        atomic_writer=atomic_writer,
    )


def _finalize(
    *,
    context: N3BoundedContext,
    result: str,
    stop_reason: str | None,
    requires_post_check: bool,
    completed_stages: list[str],
    pending_stages: list[str],
    stage_run_ids: Mapping[str, str],
    output_run_ids: Mapping[str, Any],
    stage_reports: Mapping[str, Any],
    rollback_artifacts: Mapping[str, Any],
    partial_reason: str | None,
    child_invoked: bool,
    atomic_writer: Callable[[str | Path, Mapping[str, Any]], None],
    child_diagnostics: list[Mapping[str, Any]] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    status_payload = write_final_status(
        context=context,
        result=result,
        stop_reason=stop_reason,
        requires_post_check=requires_post_check,
        completed_stages=completed_stages,
        pending_stages=pending_stages,
        output_run_ids=output_run_ids,
        rollback_artifacts=rollback_artifacts,
        partial_reason=partial_reason,
        child_invoked=child_invoked,
        child_diagnostics=child_diagnostics,
        atomic_writer=atomic_writer,
    )
    manifest = build_rollback_manifest(
        context=context,
        result=result,
        requires_post_check=requires_post_check,
        completed_stages=completed_stages,
        pending_stages=pending_stages,
        stage_run_ids=stage_run_ids,
        output_run_ids=output_run_ids,
        stage_reports=stage_reports,
        rollback_artifacts=rollback_artifacts,
        partial_reason=partial_reason,
        child_invoked=child_invoked,
        child_diagnostics=child_diagnostics,
    )
    if extra:
        status_payload.update(dict(extra))
        manifest.update(dict(extra))
    atomic_writer(context.rollback_manifest_json, manifest)
    return {**status_payload, "rollback_manifest": manifest}


def _terminal(result: str, stop_reason: str, requires_post_check: bool) -> dict[str, Any]:
    return {"result": result, "stop_reason": stop_reason, "requires_post_check": requires_post_check}


def _pending_stages(completed_stages: list[str]) -> list[str]:
    completed = set(completed_stages)
    return [stage for stage in STAGE_ORDER if stage not in completed]


def _extract_stage_run_ids(plan: Mapping[str, Any]) -> dict[str, str]:
    return {str(step.get("stage")): str(step.get("run_id")) for step in plan.get("child_steps") or []}


def _source_metric_alias_invalid(output_run_ids: Mapping[str, Any]) -> bool:
    projection = output_run_ids.get("projection_run_id")
    source_metric = output_run_ids.get("source_metric_run_id")
    return bool(projection and source_metric and projection != source_metric)


def _resolved_dsn(dsn: str) -> str:
    return dsn or os.environ.get("ASHARE_V3_POSTGRES_DSN") or DEFAULT_DSN


def _validate_trade_date(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{8}", value):
        raise ValueError("for_trade_date must be YYYYMMDD")
    datetime.strptime(value, "%Y%m%d")
    return value


def _validate_explicit_run_id(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    normalized = value.strip()
    if normalized.lower() in IMPLICIT_LINEAGE_VALUES:
        raise ValueError(f"{name} must be explicit, not {normalized}")
    return normalized


def _classify_b1_snapshot(evidence: Mapping[str, Any]) -> str:
    row = evidence.get("snapshot_run_row")
    counts = evidence.get("target_snapshot_run_row_counts") or {}
    downstream = int(evidence.get("downstream_inbox_row_count") or 0) + int(evidence.get("checkpoint_ref_count") or 0)
    if _run_passed(row) and _positive_fact_count(counts) and int(counts.get("common_market_data_quality_item") or 0) > 0 and downstream == 0:
        return "committed"
    if not row and not _positive_fact_count(counts) and downstream == 0:
        return "rolled_back"
    return "unresolved"


def _classify_c1_snapshot(evidence: Mapping[str, Any]) -> str:
    row = evidence.get("today_minute_run_row")
    counts = evidence.get("target_today_minute_run_row_counts") or {}
    downstream = int(evidence.get("outbox_rows_for_run") or 0) + int(evidence.get("inbox_rows_for_run") or 0)
    if _run_passed(row) and _positive_fact_count(counts) and int(counts.get("common_market_data_quality_item") or 0) > 0 and downstream == 0:
        return "committed"
    if not row and not _positive_fact_count(counts) and downstream == 0:
        return "rolled_back"
    return "unresolved"


def _classify_b2_snapshot(evidence: Mapping[str, Any]) -> str:
    rows = evidence.get("source_run_rows") or {}
    projection_rows = [row for run_id, row in rows.items() if str(run_id).startswith("realtime_projection_metric_")]
    counts = evidence.get("projection_run_table_counts") or {}
    downstream = (
        int(evidence.get("outbox_rows_for_projection_run") or 0)
        + int(evidence.get("inbox_rows_for_projection_run") or 0)
        + int(evidence.get("checkpoint_refs_for_projection_run") or 0)
    )
    if projection_rows and _run_passed(projection_rows[0]) and _positive_fact_count(counts) and int(evidence.get("quality_rows_for_projection_run") or 0) > 0 and downstream == 0:
        return "committed"
    if not projection_rows and not _positive_fact_count(counts) and int(evidence.get("quality_rows_for_projection_run") or 0) == 0 and downstream == 0:
        return "rolled_back"
    return "unresolved"


def _run_passed(row: Any) -> bool:
    return isinstance(row, Mapping) and row.get("status") == "passed" and bool(row.get("market_data_fact_written"))


def _positive_fact_count(counts: Mapping[str, Any]) -> bool:
    return any(int(value or 0) > 0 for key, value in counts.items() if key not in {"common_market_data_run", "common_market_data_quality_item"})


def _fallback_context(
    *,
    repo_root: str | Path,
    for_trade_date: str,
    status_json: str | Path,
    rollback_manifest_json: str | Path,
) -> N3BoundedContext:
    trade_date = for_trade_date if re.fullmatch(r"\d{8}", str(for_trade_date or "")) else "19700101"
    root = Path(repo_root)
    lineage = {
        "for_trade_date": trade_date,
        "source_condition_run_id": "",
        "source_subscription_run_id": "",
        "previous_day_preload_run_id": "",
    }
    config = BoundedWorkerConfig(
        worker_name=WORKER_NAME,
        trade_date=trade_date,
        lock_path=build_phase1_realtime_chain_lock_path(root, trade_date),
        status_json=status_json,
        run_id_prefix=WORKER_NAME,
        input_run_ids={},
    )
    return N3BoundedContext(
        repo_root=root,
        lineage=lineage,
        config=config,
        wrapper_run_id=config.make_run_id(),
        deadline=None,
        dsn="",
        docs_root=Path("docs"),
        sql_root=Path("sql"),
        python_executable=sys.executable,
        status_json=Path(status_json),
        rollback_manifest_json=Path(rollback_manifest_json),
    )


if __name__ == "__main__":
    raise SystemExit(main())
