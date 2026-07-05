#!/usr/bin/env python3
"""Run one N3 intraday auto-poll activation pass.

The wrapper is intentionally bounded. It prepares child artifacts for the
latest closed minute, validates them, then invokes the existing supervisor only
when explicitly authorized. It does not install schedulers, consume event infra,
or enter downstream layers.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from datetime import datetime, time
import json
import os
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
    DEFAULT_SUPERVISOR_JSON_REPORT_PATH,
    DEFAULT_SUPERVISOR_MD_REPORT_PATH,
    ASIA_SHANGHAI,
    build_intraday_supervisor_plan,
    fetch_passed_market_data_run_ids,
    run_intraday_supervisor_plan,
)
from ashare_v3.market.previous_day_preload_execute import write_json, write_text

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:
    DEFAULT_DSN = "postgresql://ashare_v3_user:ashare_v3_password@127.0.0.1:5432/ashare_v3"


DEFAULT_AUTO_POLL_JSON_REPORT_PATH = "docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_REPORT.json"
DEFAULT_AUTO_POLL_MD_REPORT_PATH = "docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_REPORT.md"
PREOPEN_PREWARM_START = time(9, 25)
FIRST_CLOSED_MINUTE_AVAILABLE_AT = time(9, 32)
FIRST_CLOSED_MINUTE_HHMM = "0931"
AUTO_RESOLVE_TODAY_CUTOFF = time(15, 30)


def run_auto_poll_once(
    *,
    for_trade_date: str,
    subscription_run_id: str,
    preload_run_id: str,
    source_condition_run_id: str,
    passed_run_ids: Iterable[str],
    as_of: datetime | None = None,
    docs_root: str | Path = "docs",
    sql_root: str | Path = "sql",
    python_executable: str = "python3",
    execute: bool = False,
    user_confirmed: bool = False,
    allow_overwrite: bool = False,
    subscription_summary: dict[str, Any] | None = None,
    command_runner: Callable[[list[str]], Any] | None = None,
) -> dict[str, Any]:
    """Build and optionally execute one bounded auto-poll pass."""

    plan = build_intraday_supervisor_plan(
        for_trade_date=for_trade_date,
        subscription_run_id=subscription_run_id,
        preload_run_id=preload_run_id,
        passed_run_ids=passed_run_ids,
        as_of=as_of,
        python_executable=python_executable,
        docs_root=docs_root,
        sql_root=sql_root,
    )
    report = build_base_wrapper_report(
        plan=plan,
        source_condition_run_id=source_condition_run_id,
        execute=execute,
        user_confirmed=user_confirmed,
    )

    if execute != user_confirmed:
        report["status"] = "blocked"
        report["reason"] = "auto_poll_execute_requires_user_confirmed"
        return report

    if plan.get("status") != "ready":
        if should_prewarm_auction_snapshot(plan):
            return run_auction_snapshot_prewarm(
                report=report,
                for_trade_date=for_trade_date,
                subscription_run_id=subscription_run_id,
                preload_run_id=preload_run_id,
                source_condition_run_id=source_condition_run_id,
                docs_root=docs_root,
                sql_root=sql_root,
                execute=execute,
                allow_overwrite=allow_overwrite,
                subscription_summary=subscription_summary,
            )
        if should_prewarm_first_closed_minute(plan):
            return run_preopen_first_closed_minute_prewarm(
                report=report,
                for_trade_date=for_trade_date,
                subscription_run_id=subscription_run_id,
                preload_run_id=preload_run_id,
                source_condition_run_id=source_condition_run_id,
                docs_root=docs_root,
                sql_root=sql_root,
                execute=execute,
                allow_overwrite=allow_overwrite,
                subscription_summary=subscription_summary,
            )
        return report

    if b2_noop_report_already_processed(plan):
        report["status"] = "noop"
        report["reason"] = "latest_closed_minute_b2_noop_already_processed"
        report["skipped_child_steps"] = list(report.get("skipped_child_steps", [])) + [
            {
                "stage": "B2",
                "reason": "existing_b2_noop_pass_report",
                "run_id": b2_noop_child_step(plan).get("run_id"),
                "json_report_path": b2_noop_child_step(plan).get("json_report_path"),
            }
        ]
        report["child_steps"] = []
        return report

    child_plan = build_child_artifact_plan_for_minute(
        for_trade_date=for_trade_date,
        latest_closed_minute=str(plan.get("latest_closed_minute") or ""),
        latest_closed_minute_hhmm=str(plan.get("effective_hhmm") or plan.get("latest_closed_minute_hhmm") or ""),
        subscription_run_id=subscription_run_id,
        preload_run_id=preload_run_id,
        source_condition_run_id=source_condition_run_id,
        docs_root=docs_root,
        sql_root=sql_root,
        projection_input_mode=str(plan.get("projection_input_mode") or "closed_minute"),
        subscription_summary=subscription_summary,
    )
    report["stage_run_ids"] = child_plan["stage_run_ids"]
    report["generated_artifacts"] = child_plan["generated_artifacts"]

    if not execute:
        report["execution_mode"] = "plan_only"
        return report

    try:
        write_result = write_intraday_child_artifacts(child_plan, allow_overwrite=allow_overwrite)
    except IntradayChildArtifactConflictError as exc:
        report["status"] = "blocked"
        report["reason"] = "child_artifact_generation_failed"
        report["artifact_generation"] = {
            "status": "blocked",
            "reason": str(exc),
        }
        return report

    report["artifact_generation"] = write_result
    validation = validate_generated_child_artifacts(child_plan)
    report["artifact_validation"] = validation
    if validation["status"] != "passed":
        report["status"] = "blocked"
        report["reason"] = "child_artifact_validation_failed"
        return report

    supervisor_report = run_intraday_supervisor_plan(plan, command_runner=command_runner)
    report.update(
        {
            "status": supervisor_report.get("status"),
            "reason": supervisor_report.get("reason"),
            "failed_stage": supervisor_report.get("failed_stage"),
            "failed_step_id": supervisor_report.get("failed_step_id"),
            "child_step_results": supervisor_report.get("child_step_results", []),
            "executed_child_command_count": supervisor_report.get("executed_child_command_count", 0),
            "supervisor_report": supervisor_report,
            "execution_mode": "execute",
        }
    )
    report["side_effects"]["supervisor_executed"] = True
    report["side_effects"]["b1_c1_b2_executed"] = bool(int(report.get("executed_child_command_count") or 0))
    return report


def b2_noop_child_step(plan: dict[str, Any]) -> dict[str, Any]:
    child_steps = [step for step in plan.get("child_steps", []) if str(step.get("stage")) == "B2"]
    return dict(child_steps[0]) if len(child_steps) == 1 and len(plan.get("child_steps", [])) == 1 else {}


def b2_noop_report_already_processed(plan: dict[str, Any]) -> bool:
    """Treat a reviewed no-write B2 NOOP report as a processed watermark."""

    step = b2_noop_child_step(plan)
    if not step:
        return False
    report_path = Path(str(step.get("json_report_path") or ""))
    if not report_path.exists():
        return False
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if report.get("result") != "NOOP_PASS":
        return False
    if str(report.get("projection_run_id") or "") != str(step.get("run_id") or ""):
        return False
    side_effects = report.get("side_effects") or {}
    if side_effects.get("writes_performed") is not False:
        return False
    return True


def should_prewarm_first_closed_minute(plan: dict[str, Any]) -> bool:
    """Return true for the 09:25-09:31 pre-open artifact prewarm window."""

    if plan.get("status") != "noop" or plan.get("reason") != "no_closed_minute_available":
        return False
    as_of_text = str(plan.get("as_of") or "")
    if not as_of_text:
        return False
    as_of = datetime.fromisoformat(as_of_text)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=ASIA_SHANGHAI)
    else:
        as_of = as_of.astimezone(ASIA_SHANGHAI)
    if as_of.strftime("%Y%m%d") != str(plan.get("for_trade_date")):
        return False
    return PREOPEN_PREWARM_START <= as_of.time().replace(second=0, microsecond=0) < FIRST_CLOSED_MINUTE_AVAILABLE_AT


def should_prewarm_auction_snapshot(plan: dict[str, Any]) -> bool:
    return plan.get("status") == "noop" and plan.get("reason") == "auction_preopen_plan_only"


def run_auction_snapshot_prewarm(
    *,
    report: dict[str, Any],
    for_trade_date: str,
    subscription_run_id: str,
    preload_run_id: str,
    source_condition_run_id: str,
    docs_root: str | Path,
    sql_root: str | Path,
    execute: bool,
    allow_overwrite: bool,
    subscription_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    prepared_hhmm = str(report.get("prewarm_hhmm") or "0920")
    child_plan = build_child_artifact_plan_for_minute(
        for_trade_date=for_trade_date,
        latest_closed_minute="",
        latest_closed_minute_hhmm=prepared_hhmm,
        subscription_run_id=subscription_run_id,
        preload_run_id=preload_run_id,
        source_condition_run_id=source_condition_run_id,
        docs_root=docs_root,
        sql_root=sql_root,
        projection_input_mode="auction_or_snapshot_only",
        subscription_summary=subscription_summary,
    )
    report.update(
        {
            "status": "prewarm_ready",
            "reason": "auction_preopen_artifacts_ready",
            "stage_run_ids": child_plan["stage_run_ids"],
            "generated_artifacts": child_plan["generated_artifacts"],
            "prewarm": {
                "enabled": True,
                "prepared_hhmm": prepared_hhmm,
                "projection_input_mode": "auction_or_snapshot_only",
                "supervisor_execute_allowed": False,
                "child_execute_allowed": False,
                "closed_minute_fact_write_allowed": False,
            },
        }
    )
    if not execute:
        report["execution_mode"] = "plan_only"
        return report

    try:
        report["artifact_generation"] = write_intraday_child_artifacts(child_plan, allow_overwrite=allow_overwrite)
    except IntradayChildArtifactConflictError as exc:
        report["status"] = "prewarm_blocked"
        report["reason"] = "auction_preopen_artifact_generation_failed"
        report["artifact_generation"] = {
            "status": "blocked",
            "reason": str(exc),
        }
        return report

    validation = validate_generated_child_artifacts(child_plan)
    report["artifact_validation"] = validation
    if validation["status"] != "passed":
        report["status"] = "prewarm_blocked"
        report["reason"] = "auction_preopen_artifact_validation_failed"
    return report


def run_preopen_first_closed_minute_prewarm(
    *,
    report: dict[str, Any],
    for_trade_date: str,
    subscription_run_id: str,
    preload_run_id: str,
    source_condition_run_id: str,
    docs_root: str | Path,
    sql_root: str | Path,
    execute: bool,
    allow_overwrite: bool,
    subscription_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Generate and validate first-closed-minute child artifacts without running supervisor."""

    prepared_minute = datetime.strptime(for_trade_date + FIRST_CLOSED_MINUTE_HHMM, "%Y%m%d%H%M").replace(tzinfo=ASIA_SHANGHAI)
    child_plan = build_child_artifact_plan_for_minute(
        for_trade_date=for_trade_date,
        latest_closed_minute=prepared_minute.isoformat(),
        latest_closed_minute_hhmm=FIRST_CLOSED_MINUTE_HHMM,
        subscription_run_id=subscription_run_id,
        preload_run_id=preload_run_id,
        source_condition_run_id=source_condition_run_id,
        docs_root=docs_root,
        sql_root=sql_root,
        projection_input_mode="closed_minute",
        subscription_summary=subscription_summary,
    )
    report.update(
        {
            "status": "prewarm_ready",
            "reason": "preopen_first_closed_minute_artifacts_ready",
            "latest_closed_minute": None,
            "latest_closed_minute_hhmm": None,
            "stage_run_ids": child_plan["stage_run_ids"],
            "generated_artifacts": child_plan["generated_artifacts"],
            "prewarm": {
                "enabled": True,
                "prepared_hhmm": FIRST_CLOSED_MINUTE_HHMM,
                "prepared_latest_closed_minute": prepared_minute.isoformat(),
                "supervisor_execute_allowed": False,
                "child_execute_allowed": False,
                "closed_minute_fact_write_allowed": False,
            },
        }
    )
    if not execute:
        report["execution_mode"] = "plan_only"
        return report

    try:
        report["artifact_generation"] = write_intraday_child_artifacts(child_plan, allow_overwrite=allow_overwrite)
    except IntradayChildArtifactConflictError as exc:
        report["status"] = "prewarm_blocked"
        report["reason"] = "prewarm_child_artifact_generation_failed"
        report["artifact_generation"] = {
            "status": "blocked",
            "reason": str(exc),
        }
        return report

    validation = validate_generated_child_artifacts(child_plan)
    report["artifact_validation"] = validation
    if validation["status"] != "passed":
        report["status"] = "prewarm_blocked"
        report["reason"] = "prewarm_child_artifact_validation_failed"
    return report


def build_child_artifact_plan_for_minute(
    *,
    for_trade_date: str,
    latest_closed_minute: str,
    latest_closed_minute_hhmm: str,
    subscription_run_id: str,
    preload_run_id: str,
    source_condition_run_id: str,
    docs_root: str | Path,
    sql_root: str | Path,
    projection_input_mode: str = "closed_minute",
    subscription_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_intraday_child_artifact_plan(
        IntradayChildArtifactRequest(
            for_trade_date=for_trade_date,
            latest_closed_minute=latest_closed_minute,
            latest_closed_minute_hhmm=latest_closed_minute_hhmm,
            subscription_run_id=subscription_run_id,
            preload_run_id=preload_run_id,
            source_condition_run_id=source_condition_run_id,
            docs_root=docs_root,
            sql_root=sql_root,
            projection_input_mode=projection_input_mode,
            subscription_summary=subscription_summary,
        )
    )


def build_base_wrapper_report(
    *,
    plan: dict[str, Any],
    source_condition_run_id: str,
    execute: bool,
    user_confirmed: bool,
) -> dict[str, Any]:
    return {
        "stage": "N3-intraday-B1-C1-B2-auto-poll-wrapper",
        "layer_role": "N3_market_data",
        "status": plan.get("status"),
        "reason": plan.get("reason"),
        "execution_mode": "execute" if execute and user_confirmed else "plan_only",
        "for_trade_date": plan.get("for_trade_date"),
        "latest_closed_minute": plan.get("latest_closed_minute"),
        "latest_closed_minute_hhmm": plan.get("latest_closed_minute_hhmm"),
        "effective_hhmm": plan.get("effective_hhmm"),
        "prewarm_hhmm": plan.get("prewarm_hhmm"),
        "stage_order_policy": plan.get("stage_order_policy"),
        "projection_input_mode": plan.get("projection_input_mode"),
        "subscription_run_id": plan.get("subscription_run_id"),
        "preload_run_id": plan.get("preload_run_id"),
        "source_condition_run_id": source_condition_run_id,
        "child_steps": plan.get("child_steps", []),
        "skipped_child_steps": plan.get("skipped_child_steps", []),
        "child_step_results": [],
        "executed_child_command_count": 0,
        "stage_run_ids": extract_stage_run_ids(plan),
        "generated_artifacts": {},
        "artifact_generation": {
            "status": "not_written",
            "reason": "plan_only_or_noop_before_generation",
        },
        "artifact_validation": {
            "status": "not_run",
        },
        "confirmation": {
            "execute": execute,
            "user_confirmed": user_confirmed,
        },
        "side_effects": {
            "database_written": False,
            "scheduler_installed_or_enabled": False,
            "supervisor_executed": False,
            "b1_c1_b2_executed": False,
            "outbox_inbox_checkpoint_consumed_or_updated": False,
            "n4_n5_n6_entered": False,
            "worker_started": False,
            "delivery_push_voice_mobile": False,
            "proposal_order_trade": False,
            "sim_position_pnl_real_trade": False,
            "old_system_touched": False,
        },
    }


def extract_stage_run_ids(plan: dict[str, Any]) -> dict[str, str]:
    return {str(step.get("stage")): str(step.get("run_id")) for step in plan.get("child_steps", [])}


def validate_generated_child_artifacts(child_plan: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for path in iter_required_json_paths(child_plan):
        checks.append({"path": path, "kind": "json", "passed": validate_json_path(path)})
    for path in iter_rollback_paths(child_plan):
        checks.append({"path": path, "kind": "rollback_sql", "passed": validate_rollback_sql_path(path)})
    failed = [check for check in checks if not check["passed"]]
    return {
        "status": "passed" if not failed else "blocked",
        "checks": checks,
        "failed_checks": failed,
    }


def iter_required_json_paths(child_plan: dict[str, Any]) -> list[str]:
    artifacts = child_plan["generated_artifacts"]
    return [
        artifacts["B1"]["execute_contract_json"],
        artifacts["B1"]["execute_readiness_json"],
        artifacts["C1"]["c0_dry_run_json"],
        artifacts["B2"]["dry_run_json"],
        artifacts["B2"]["execute_contract_json"],
        artifacts["B2"]["execute_preflight_json"],
    ]


def iter_rollback_paths(child_plan: dict[str, Any]) -> list[str]:
    artifacts = child_plan["generated_artifacts"]
    return [
        artifacts["B1"]["rollback_sql"],
        artifacts["C1"]["rollback_sql"],
        artifacts["B2"]["rollback_sql"],
    ]


def validate_json_path(path_text: str) -> bool:
    path = Path(path_text)
    if not path.exists():
        return False
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return True


def validate_rollback_sql_path(path_text: str) -> bool:
    path = Path(path_text)
    if not path.exists():
        return False
    sql = path.read_text(encoding="utf-8")
    upper = sql.upper()
    if "RAISE EXCEPTION" not in sql or "DELETE FROM" not in sql:
        return False
    if sql.index("RAISE EXCEPTION") > sql.index("DELETE FROM"):
        return False
    if "DROP " in upper or "TRUNCATE" in upper or "CASCADE" in upper:
        return False
    required_markers = (
        "common_event_outbox",
        "common_event_inbox",
        "common_event_consumer_checkpoint",
        "common_trigger_state",
    )
    return all(marker in sql for marker in required_markers)


def fetch_wrapper_passed_run_ids(*, dsn: str, for_trade_date: str) -> set[str]:
    prefixes = (
        f"realtime_daily_snapshot_{for_trade_date}_until_",
        f"realtime_daily_snapshot_{for_trade_date}_auction_",
        f"today_minute_bar_1m_{for_trade_date}_until_",
        f"today_minute_bar_1m_{for_trade_date}_auction_",
        f"realtime_projection_metric_{for_trade_date}_until_",
        f"realtime_projection_metric_{for_trade_date}_auction_",
    )
    return fetch_passed_market_data_run_ids(dsn=dsn, for_trade_date=for_trade_date, run_id_prefixes=prefixes)


def fetch_live_subscription_summary(*, dsn: str, subscription_run_id: str) -> dict[str, Any]:
    """Read persisted subscription counts for dynamic child artifact generation."""

    counts = {
        "realtime_daily_snapshot": {"stock": 0, "index": 0, "board": 0},
        "minute_bar_1m": {"stock": 0, "index": 0, "board": 0},
    }
    with psycopg.connect(
        dsn,
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
            (subscription_run_id, list(counts)),
        )
        for row in cur.fetchall():
            data_kind = str(row["required_data_kind"])
            asset_kind = str(row["asset_kind"])
            if data_kind in counts and asset_kind in counts[data_kind]:
                counts[data_kind][asset_kind] = int(row["object_count"] or 0)
    return {
        "source": "live_subscription_counts",
        "source_run_id": subscription_run_id,
        "snapshot_object_count_by_asset_kind": counts["realtime_daily_snapshot"],
        "today_minute_object_count_by_asset_kind": counts["minute_bar_1m"],
    }


def write_auto_poll_report(
    report: dict[str, Any],
    *,
    json_report_path: str | Path,
    markdown_report_path: str | Path,
) -> None:
    write_json(json_report_path, report)
    write_text(markdown_report_path, render_auto_poll_markdown(report))


def render_auto_poll_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# N3 Intraday B1/C1/B2 Auto-Poll Wrapper Report",
        "",
        f"- status: `{report.get('status')}`",
        f"- reason: `{report.get('reason')}`",
        f"- execution_mode: `{report.get('execution_mode')}`",
        f"- for_trade_date: `{report.get('for_trade_date')}`",
        f"- latest_closed_minute_hhmm: `{report.get('latest_closed_minute_hhmm')}`",
        f"- effective_hhmm: `{report.get('effective_hhmm')}`",
        f"- stage_order_policy: `{report.get('stage_order_policy')}`",
        f"- projection_input_mode: `{report.get('projection_input_mode')}`",
        f"- artifact_generation: `{(report.get('artifact_generation') or {}).get('status')}`",
        f"- artifact_validation: `{(report.get('artifact_validation') or {}).get('status')}`",
        f"- executed_child_command_count: `{report.get('executed_child_command_count', 0)}`",
        "",
        "## Forbidden Scope",
        "",
        "```text",
        "database_written=false",
        "scheduler_installed_or_enabled=false",
        "outbox_inbox_checkpoint_consumed_or_updated=false",
        "n4_n5_n6_entered=false",
        "worker_started=false",
        "delivery_push_voice_mobile=false",
        "proposal_order_trade=false",
        "sim_position_pnl_real_trade=false",
        "old_system_touched=false",
        "```",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    as_of = datetime.fromisoformat(args.as_of) if args.as_of else None
    lineage_resolution: dict[str, Any] | None = None
    explicit_for_trade_date = args.for_trade_date or None
    if args.auto_resolve_lineage:
        lineage_resolution = resolve_auto_poll_lineage(dsn=args.dsn, as_of=as_of, for_trade_date=explicit_for_trade_date)
        if lineage_resolution["status"] != "resolved":
            report = build_auto_lineage_blocked_report(lineage_resolution=lineage_resolution, execute=args.execute, user_confirmed=args.user_confirmed)
            json_report_path = resolve_report_path(args.json_report_path, lineage_resolution.get("for_trade_date"))
            markdown_report_path = resolve_report_path(args.markdown_report_path, lineage_resolution.get("for_trade_date"))
            write_auto_poll_report(report, json_report_path=json_report_path, markdown_report_path=markdown_report_path)
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str) if args.json else format_summary(report))
            return 0 if report.get("status") == "noop" else 2
        local_as_of = (as_of or datetime.now(ASIA_SHANGHAI)).astimezone(ASIA_SHANGHAI) if (as_of or datetime.now(ASIA_SHANGHAI)).tzinfo else (as_of or datetime.now(ASIA_SHANGHAI)).replace(tzinfo=ASIA_SHANGHAI)
        if not explicit_for_trade_date and str(lineage_resolution["for_trade_date"]) > local_as_of.strftime("%Y%m%d"):
            future_resolution = dict(lineage_resolution)
            future_resolution["status"] = "noop"
            future_resolution["reason"] = "awaiting_future_trade_date"
            report = build_auto_lineage_blocked_report(lineage_resolution=future_resolution, execute=args.execute, user_confirmed=args.user_confirmed)
            json_report_path = resolve_report_path(args.json_report_path, lineage_resolution.get("for_trade_date"))
            markdown_report_path = resolve_report_path(args.markdown_report_path, lineage_resolution.get("for_trade_date"))
            write_auto_poll_report(report, json_report_path=json_report_path, markdown_report_path=markdown_report_path)
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str) if args.json else format_summary(report))
            return 0
        args.for_trade_date = lineage_resolution["for_trade_date"]
        args.subscription_run_id = lineage_resolution["subscription_run_id"]
        args.preload_run_id = lineage_resolution["preload_run_id"]
        args.source_condition_run_id = lineage_resolution["source_condition_run_id"]
    missing = [
        name
        for name, value in (
            ("--for-trade-date", args.for_trade_date),
            ("--subscription-run-id", args.subscription_run_id),
            ("--preload-run-id", args.preload_run_id),
            ("--source-condition-run-id", args.source_condition_run_id),
        )
        if not value
    ]
    if missing:
        parser.error("missing required arguments unless --auto-resolve-lineage is used: " + ", ".join(missing))
    passed_run_ids = set(args.passed_run_id)
    if not args.skip_db_watermark:
        passed_run_ids.update(fetch_wrapper_passed_run_ids(dsn=args.dsn, for_trade_date=args.for_trade_date))
    subscription_summary = fetch_live_subscription_summary(
        dsn=args.dsn,
        subscription_run_id=args.subscription_run_id,
    )
    report = run_auto_poll_once(
        for_trade_date=args.for_trade_date,
        subscription_run_id=args.subscription_run_id,
        preload_run_id=args.preload_run_id,
        source_condition_run_id=args.source_condition_run_id,
        passed_run_ids=passed_run_ids,
        as_of=as_of,
        docs_root=args.docs_root,
        sql_root=args.sql_root,
        python_executable=args.python_executable,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
        allow_overwrite=args.allow_overwrite,
        subscription_summary=subscription_summary,
    )
    if lineage_resolution is not None:
        report["lineage_resolution"] = lineage_resolution
    write_auto_poll_report(
        report,
        json_report_path=resolve_report_path(args.json_report_path, args.for_trade_date),
        markdown_report_path=resolve_report_path(args.markdown_report_path, args.for_trade_date),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report.get("status") in {"ready", "passed", "noop", "prewarm_ready"} else 2


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one N3 intraday B1/C1/B2 auto-poll wrapper pass.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--auto-resolve-lineage", action="store_true")
    parser.add_argument("--for-trade-date", default="")
    parser.add_argument("--subscription-run-id", default="")
    parser.add_argument("--preload-run-id", default="")
    parser.add_argument("--source-condition-run-id", default="")
    parser.add_argument("--as-of", default="")
    parser.add_argument("--python-executable", default="python3")
    parser.add_argument("--docs-root", default="docs")
    parser.add_argument("--sql-root", default="sql")
    parser.add_argument("--passed-run-id", action="append", default=[])
    parser.add_argument("--skip-db-watermark", action="store_true")
    parser.add_argument("--json-report-path", default=DEFAULT_AUTO_POLL_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_AUTO_POLL_MD_REPORT_PATH)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--allow-overwrite", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def resolve_report_path(path: str, for_trade_date: str | None) -> str:
    if "{for_trade_date}" in path and for_trade_date:
        return path.format(for_trade_date=for_trade_date)
    if for_trade_date and path == DEFAULT_AUTO_POLL_JSON_REPORT_PATH:
        return f"docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_REPORT_{for_trade_date}.json"
    if for_trade_date and path == DEFAULT_AUTO_POLL_MD_REPORT_PATH:
        return f"docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_REPORT_{for_trade_date}.md"
    return path


def production_subscription_pattern(for_trade_date: str) -> str:
    return f"market_data_subscription_{for_trade_date}_condition_layer_%"


def production_preload_suffix_pattern(subscription_run_id: str) -> str:
    return f"%__{subscription_run_id}"


def resolve_auto_poll_lineage(*, dsn: str, as_of: datetime | None = None, for_trade_date: str | None = None) -> dict[str, Any]:
    resolved_as_of = as_of or datetime.now(ASIA_SHANGHAI)
    if resolved_as_of.tzinfo is None:
        resolved_as_of = resolved_as_of.replace(tzinfo=ASIA_SHANGHAI)
    local_as_of = resolved_as_of.astimezone(ASIA_SHANGHAI)
    with psycopg.connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT trade_date, is_open
            FROM common_trade_calendar
            WHERE trade_date >= %s
            ORDER BY trade_date
            LIMIT 10
            """,
            (local_as_of.strftime("%Y%m%d"),),
        )
        calendar_rows = [dict(row) for row in cur.fetchall()]
        trade_date_resolution = resolve_auto_trade_date(
            calendar_rows=calendar_rows,
            as_of=local_as_of,
            explicit_for_trade_date=for_trade_date,
        )
        if trade_date_resolution["status"] != "resolved":
            return {
                "status": trade_date_resolution["status"],
                "reason": trade_date_resolution["reason"],
                "as_of": local_as_of.isoformat(),
                "for_trade_date": trade_date_resolution.get("for_trade_date"),
                "calendar": trade_date_resolution,
            }
        resolved_trade_date = str(trade_date_resolution["for_trade_date"])
        cur.execute(
            """
            SELECT run_id, source_condition_run_id, created_at
            FROM common_market_data_run
            WHERE for_trade_date = %s
              AND status = 'passed'
              AND run_id LIKE %s
              AND run_id NOT LIKE '%%action_confirmation%%'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (resolved_trade_date, production_subscription_pattern(resolved_trade_date)),
        )
        subscription = cur.fetchone()
        if not subscription:
            return {
                "status": "blocked",
                "reason": "subscription_run_not_ready",
                "as_of": local_as_of.isoformat(),
                "for_trade_date": resolved_trade_date,
                "calendar": trade_date_resolution,
            }
        subscription_run_id = str(subscription["run_id"])
        source_condition_run_id = str(subscription["source_condition_run_id"] or "")
        cur.execute(
            """
            SELECT run_id, created_at
            FROM common_market_data_run
            WHERE for_trade_date = %s
              AND status = 'passed'
              AND run_id LIKE %s
              AND run_id LIKE %s
              AND run_id NOT LIKE '%%action_confirmation%%'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (resolved_trade_date, "previous_day_minute_preload_%", production_preload_suffix_pattern(subscription_run_id)),
        )
        preload = cur.fetchone()
        if not preload:
            return {
                "status": "blocked",
                "reason": "preload_run_not_ready",
                "as_of": local_as_of.isoformat(),
                "for_trade_date": resolved_trade_date,
                "subscription_run_id": subscription_run_id,
                "source_condition_run_id": source_condition_run_id,
                "calendar": trade_date_resolution,
            }
        return {
            "status": "resolved",
            "reason": "auto_lineage_resolved",
            "as_of": local_as_of.isoformat(),
            "for_trade_date": resolved_trade_date,
            "subscription_run_id": subscription_run_id,
            "preload_run_id": str(preload["run_id"]),
            "source_condition_run_id": source_condition_run_id,
            "calendar": trade_date_resolution,
        }


def resolve_auto_trade_date(
    *,
    calendar_rows: list[dict[str, Any]],
    as_of: datetime,
    explicit_for_trade_date: str | None = None,
) -> dict[str, Any]:
    if explicit_for_trade_date:
        matching = [row for row in calendar_rows if str(row.get("trade_date")) == explicit_for_trade_date]
        is_open = bool(matching[0].get("is_open")) if matching else False
        return {
            "status": "resolved" if is_open else "blocked",
            "reason": "explicit_trade_date" if is_open else "explicit_trade_date_not_open",
            "for_trade_date": explicit_for_trade_date,
            "is_open": is_open,
        }
    today = as_of.strftime("%Y%m%d")
    today_row = next((row for row in calendar_rows if str(row.get("trade_date")) == today), None)
    if today_row and bool(today_row.get("is_open")) and as_of.timetz().replace(tzinfo=None) <= AUTO_RESOLVE_TODAY_CUTOFF:
        return {
            "status": "resolved",
            "reason": "today_open_before_cutoff",
            "for_trade_date": today,
            "is_open": True,
            "cutoff": AUTO_RESOLVE_TODAY_CUTOFF.strftime("%H:%M"),
        }
    for row in calendar_rows:
        trade_date = str(row.get("trade_date") or "")
        if trade_date > today and bool(row.get("is_open")):
            return {
                "status": "resolved",
                "reason": "next_open_trade_date_after_cutoff_or_non_trading_day",
                "for_trade_date": trade_date,
                "is_open": True,
                "cutoff": AUTO_RESOLVE_TODAY_CUTOFF.strftime("%H:%M"),
            }
    return {
        "status": "noop",
        "reason": "no_open_trade_date_available",
        "for_trade_date": None,
        "is_open": False,
    }


def build_auto_lineage_blocked_report(*, lineage_resolution: dict[str, Any], execute: bool, user_confirmed: bool) -> dict[str, Any]:
    status = "noop" if lineage_resolution.get("status") == "noop" else "blocked"
    return {
        "stage": "N3-intraday-B1-C1-B2-auto-poll-wrapper",
        "layer_role": "N3_market_data",
        "status": status,
        "reason": lineage_resolution.get("reason"),
        "execution_mode": "auto_lineage_resolution",
        "for_trade_date": lineage_resolution.get("for_trade_date"),
        "latest_closed_minute": None,
        "latest_closed_minute_hhmm": None,
        "effective_hhmm": None,
        "lineage_resolution": lineage_resolution,
        "execute": execute,
        "user_confirmed": user_confirmed,
        "artifact_generation": {"status": "not_written"},
        "artifact_validation": {"status": "not_run"},
        "executed_child_command_count": 0,
        "side_effects": {
            "database_written": False,
            "scheduler_installed_or_enabled": False,
            "supervisor_executed": False,
            "b1_c1_b2_executed": False,
            "outbox_inbox_checkpoint_consumed_or_updated": False,
            "n4_n5_n6_entered": False,
            "worker_started": False,
            "delivery_push_voice_mobile": False,
            "proposal_order_trade_sim_position_pnl_real_trade": False,
            "old_system_touched": False,
        },
    }


def format_summary(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "n3 intraday b1/c1/b2 auto-poll wrapper",
            f"  status={report.get('status')}",
            f"  reason={report.get('reason')}",
            f"  execution_mode={report.get('execution_mode')}",
            f"  for_trade_date={report.get('for_trade_date')}",
            f"  latest_closed_minute_hhmm={report.get('latest_closed_minute_hhmm')}",
            f"  effective_hhmm={report.get('effective_hhmm')}",
            f"  stage_order_policy={report.get('stage_order_policy')}",
            f"  projection_input_mode={report.get('projection_input_mode')}",
            f"  artifact_generation={(report.get('artifact_generation') or {}).get('status')}",
            f"  artifact_validation={(report.get('artifact_validation') or {}).get('status')}",
            f"  executed_child_command_count={report.get('executed_child_command_count', 0)}",
            "  scheduler_installed=false outbox_consumed_or_updated=false n4_n5_n6_entered=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
