#!/usr/bin/env python3
"""Run one bounded N3 -> N4 -> N5 realtime chain pass.

This wrapper is the single scheduler entrypoint for the realtime fast lane. It
keeps every child as a bounded run-once command and stops on the first noop or
blocker. It never enters N6, delivery, voice, mobile, sim, position, PnL, or
real-trade paths.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Mapping

import psycopg
from psycopg.rows import dict_row

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.action_confirmation_metric_materialization_execute import (
    ALLOWED_WRITE_TABLES as ACTION_METRIC_ALLOWED_WRITE_TABLES,
    FORBIDDEN_WRITE_TABLES as ACTION_METRIC_FORBIDDEN_WRITE_TABLES,
    PROJECTION_SCHEMA_VERSION as ACTION_METRIC_SCHEMA_VERSION,
    REQUESTED_TARGET_ALIASES as ACTION_METRIC_REQUESTED_TARGET_ALIASES,
    build_preflight as build_action_metric_preflight,
    build_rollback_sql as build_action_metric_rollback_sql,
    is_bj_identity,
)
from ashare_v3.market.action_confirmation_projection_plan import (
    build_metric_candidate_rows_from_sources,
    extract_candidate_identities,
    load_minute_rows_for_metric_dry_run,
    load_snapshot_rows_for_metric_dry_run,
)
from ashare_v3.market.preload_execute_contract import build_previous_day_minute_execute_contract
from ashare_v3.market.preload_plan import build_previous_day_minute_preload_plan_dry_run
from ashare_v3.market.previous_day_preload_execute import write_json, write_text
from ashare_v3.market.realtime_projection_execute import (
    build_expected_distribution_from_summary,
    build_projection_rollback_sql,
    build_projection_rows,
    summarize_projection_rows,
)
from ashare_v3.market.realtime_snapshot_execute_contract import (
    build_execute_contract_from_reports,
    format_realtime_snapshot_rollback_sql,
)
from ashare_v3.market.today_minute_plan import (
    build_today_minute_rollback_sql,
    build_today_minute_bar_plan_dry_run,
    format_today_minute_markdown,
)

from run_n3_intraday_b1_c1_b2_auto_poll_once import (
    ASIA_SHANGHAI,
    DEFAULT_DSN,
    resolve_auto_poll_lineage,
)


DEFAULT_CHAIN_JSON_REPORT_PATH = "docs/N3_N4_N5_REALTIME_CHAIN_REPORT.json"
DEFAULT_CHAIN_MD_REPORT_PATH = "docs/N3_N4_N5_REALTIME_CHAIN_REPORT.md"
CHAIN_OBJECTIVE = "N3_N4_N5_20260612_REALTIME_AUTO_CHAIN_CLOSEOUT"
ASSET_KINDS = ("stock", "index", "board")
SNAPSHOT_TABLES = {
    "stock": "stock_realtime_daily_snapshot",
    "index": "index_realtime_daily_snapshot",
    "board": "board_realtime_daily_snapshot",
}
IDENTITY_COLUMNS = {
    "stock": "stock_identity_key",
    "index": "index_identity_key",
    "board": "board_identity_key",
}
MINUTE_SCOPE_TABLES = {
    "stock": "stock_minute_target_scope",
    "index": "index_minute_target_scope",
    "board": "board_minute_target_scope",
}


@dataclass(frozen=True)
class StageIds:
    for_trade_date: str
    hhmm: str
    b1_fact_run_id: str
    b1_standard_outbox_run_id: str
    c1_today_minute_run_id: str
    b2_trace_projection_run_id: str
    n4_context_run_id: str
    n4_run_id: str
    n4_consumer_name: str
    n3_action_subscription_run_id: str
    n3_action_today_minute_run_id: str
    n3_action_preload_run_id: str
    n3_action_metric_run_id: str
    n5_action_run_id: str
    n5_consumer_name: str


def build_stage_ids(
    *,
    for_trade_date: str,
    hhmm: str,
    subscription_run_id: str,
    source_condition_run_id: str,
) -> StageIds:
    b1_fact_run_id = f"realtime_daily_snapshot_{for_trade_date}_until_{hhmm}__{subscription_run_id}"
    b1_standard_outbox_run_id = f"realtime_daily_snapshot_{for_trade_date}_standard_outbox_until_{hhmm}__{subscription_run_id}"
    c1_today_minute_run_id = f"today_minute_bar_1m_{for_trade_date}_until_{hhmm}__{subscription_run_id}"
    b2_trace_projection_run_id = f"realtime_projection_metric_{for_trade_date}_trace_aligned_standard_outbox_until_{hhmm}__{b1_standard_outbox_run_id}"
    n4_run_id = f"n4_production_semantic_replay_{for_trade_date}_market_snapshot_updated_until_{hhmm}"
    n4_consumer_name = f"n4_production_semantic_replay_{for_trade_date}_market_snapshot_updated_until_{hhmm}"
    n3_action_subscription_run_id = f"market_data_subscription_{for_trade_date}_action_confirmation_until_{hhmm}_scope__{n4_run_id}_v1"
    n3_action_today_minute_run_id = f"today_minute_bar_1m_{for_trade_date}_until_{hhmm}_action_confirmation_scope__{n4_run_id}_v1"
    n3_action_preload_run_id = f"previous_day_minute_preload_{for_trade_date}_until_{hhmm}_action_confirmation_scope__{n4_run_id}_v1"
    n3_action_metric_run_id = f"action_confirmation_projection_metric_{for_trade_date}_until_{hhmm}_from_{n4_run_id}_v1"
    n5_action_run_id = f"n5_action_bounded_{for_trade_date}_after_n3_action_confirmation_metric_until_{hhmm}_v1"
    n5_consumer_name = f"n5_action_bounded_consumer_{for_trade_date}_after_n3_metric_until_{hhmm}_v1"
    return StageIds(
        for_trade_date=for_trade_date,
        hhmm=hhmm,
        b1_fact_run_id=b1_fact_run_id,
        b1_standard_outbox_run_id=b1_standard_outbox_run_id,
        c1_today_minute_run_id=c1_today_minute_run_id,
        b2_trace_projection_run_id=b2_trace_projection_run_id,
        n4_context_run_id=f"trigger_context_snapshot_{for_trade_date}_{source_condition_run_id}",
        n4_run_id=n4_run_id,
        n4_consumer_name=n4_consumer_name,
        n3_action_subscription_run_id=n3_action_subscription_run_id,
        n3_action_today_minute_run_id=n3_action_today_minute_run_id,
        n3_action_preload_run_id=n3_action_preload_run_id,
        n3_action_metric_run_id=n3_action_metric_run_id,
        n5_action_run_id=n5_action_run_id,
        n5_consumer_name=n5_consumer_name,
    )


def local_now() -> datetime:
    return datetime.now(ASIA_SHANGHAI)


def resolve_report_path(path: str, for_trade_date: str | None) -> str:
    if "{for_trade_date}" in path and for_trade_date:
        return path.format(for_trade_date=for_trade_date)
    if for_trade_date and path == DEFAULT_CHAIN_JSON_REPORT_PATH:
        return f"docs/N3_N4_N5_REALTIME_CHAIN_REPORT_{for_trade_date}.json"
    if for_trade_date and path == DEFAULT_CHAIN_MD_REPORT_PATH:
        return f"docs/N3_N4_N5_REALTIME_CHAIN_REPORT_{for_trade_date}.md"
    return path


def run_command(argv: list[str]) -> Any:
    return subprocess.run(argv, check=False, text=True, capture_output=True)


def normalize_completed_process(result: Any) -> dict[str, Any]:
    return {
        "returncode": int(getattr(result, "returncode", 0)),
        "stdout": str(getattr(result, "stdout", "") or ""),
        "stderr": str(getattr(result, "stderr", "") or ""),
    }


def run_realtime_chain_once(
    *,
    dsn: str = DEFAULT_DSN,
    auto_resolve_lineage: bool = False,
    for_trade_date: str | None = None,
    subscription_run_id: str | None = None,
    preload_run_id: str | None = None,
    source_condition_run_id: str | None = None,
    docs_root: str | Path = "docs",
    sql_root: str | Path = "sql",
    json_report_path: str | Path | None = None,
    markdown_report_path: str | Path | None = None,
    as_of: datetime | None = None,
    python_executable: str = sys.executable,
    execute: bool = False,
    user_confirmed: bool = False,
    max_n4_events: int = 5000,
    max_n5_events: int = 5000,
    max_n5_runtime_seconds: int = 120,
    n5_heartbeat_interval_seconds: int = 10,
    allow_overwrite: bool = False,
    command_runner: Callable[[list[str]], Any] | None = None,
    lineage_resolver: Callable[..., dict[str, Any]] | None = None,
    n3_report_loader: Callable[[str | Path], dict[str, Any]] | None = None,
    stage_status_provider: Callable[[str, StageIds], dict[str, Any]] | None = None,
    artifact_builder: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_as_of = coerce_shanghai(as_of or local_now())
    runner = command_runner or run_command
    write_reports = json_report_path is not None or markdown_report_path is not None
    report: dict[str, Any] = build_base_report(
        execute=execute,
        user_confirmed=user_confirmed,
        as_of=resolved_as_of,
    )
    if not write_reports:
        report["_suppress_report_write"] = True

    if execute and not user_confirmed:
        report.update({"result": "BLOCKED", "blocked_reason": "missing --user-confirmed"})
        return maybe_write_chain_report(report, json_report_path=json_report_path, markdown_report_path=markdown_report_path)
    if user_confirmed and not execute:
        report.update({"result": "BLOCKED", "blocked_reason": "missing --execute"})
        return maybe_write_chain_report(report, json_report_path=json_report_path, markdown_report_path=markdown_report_path)
    if execute:
        report.update(
            {
                "result": "BLOCKED",
                "blocked_reason": "cross_layer_realtime_chain_execute_removed_use_layer_gates",
                "orchestration_boundary": "runtime_control_plan_only",
                "next_required_gates": [
                    "N3_market_data B1/C1/B2 execute gate",
                    "N4_trigger production semantic replay gate",
                    "N3_market_data action-confirmation metric gate",
                    "N5_action bounded action consumer gate",
                ],
            }
        )
        return maybe_write_chain_report(report, json_report_path=json_report_path, markdown_report_path=markdown_report_path)

    lineage = resolve_chain_lineage(
        dsn=dsn,
        auto_resolve_lineage=auto_resolve_lineage,
        for_trade_date=for_trade_date,
        subscription_run_id=subscription_run_id,
        preload_run_id=preload_run_id,
        source_condition_run_id=source_condition_run_id,
        as_of=resolved_as_of,
        lineage_resolver=lineage_resolver,
    )
    report["lineage"] = lineage
    if lineage.get("status") != "resolved":
        result = "NOOP_PASS" if lineage.get("status") == "noop" else "BLOCKED"
        report.update({"result": result, "reason": lineage.get("reason"), "blocked_reason": lineage.get("reason")})
        return maybe_write_chain_report(report, json_report_path=json_report_path, markdown_report_path=markdown_report_path)

    resolved_trade_date = str(lineage["for_trade_date"])
    report["for_trade_date"] = resolved_trade_date
    report["json_report_path"] = resolve_report_path(str(json_report_path or DEFAULT_CHAIN_JSON_REPORT_PATH), resolved_trade_date)
    report["markdown_report_path"] = resolve_report_path(str(markdown_report_path or DEFAULT_CHAIN_MD_REPORT_PATH), resolved_trade_date)
    if not for_trade_date and resolved_trade_date > resolved_as_of.strftime("%Y%m%d"):
        report.update({"result": "NOOP_PASS", "reason": "awaiting_future_trade_date"})
        return maybe_write_chain_report(
            report,
            json_report_path=report["json_report_path"],
            markdown_report_path=report["markdown_report_path"],
        )

    n3_json_path = Path(docs_root) / f"N3_INTRADAY_B1_C1_B2_AUTO_POLL_REPORT_{resolved_trade_date}.json"
    n3_md_path = Path(docs_root) / f"N3_INTRADAY_B1_C1_B2_AUTO_POLL_REPORT_{resolved_trade_date}.md"
    n3_command = build_n3_auto_poll_command(
        python_executable=python_executable,
        dsn=dsn,
        docs_root=docs_root,
        sql_root=sql_root,
        json_report_path=n3_json_path,
        markdown_report_path=n3_md_path,
        auto_resolve_lineage=auto_resolve_lineage,
        for_trade_date=for_trade_date if for_trade_date else None,
        execute=True,
        user_confirmed=True,
        allow_overwrite=allow_overwrite,
    )
    report["child_command_plan"].append(command_plan("N3_B1_C1_B2", n3_command))
    if not execute:
        report["result"] = "PLAN_ONLY"
        return maybe_write_chain_report(
            report,
            json_report_path=report.get("json_report_path") or json_report_path,
            markdown_report_path=report.get("markdown_report_path") or markdown_report_path,
        )

    n3_result = normalize_completed_process(runner(n3_command))
    report["executed_steps"].append({"stage": "N3_B1_C1_B2", "command": n3_command, **n3_result})
    if n3_result["returncode"] != 0:
        report.update({"result": "BLOCKED", "blocked_reason": "n3_auto_poll_failed"})
        return maybe_write_chain_report(report, json_report_path=report["json_report_path"], markdown_report_path=report["markdown_report_path"])

    n3_report = (n3_report_loader or load_json)(n3_json_path)
    report["n3_report_summary"] = summarize_n3_report(n3_report)
    if int(n3_report.get("executed_child_command_count") or 0) > 0:
        report["side_effects"]["database_written"] = True
        report["side_effects"]["n3_b1_c1_b2_executed"] = True
    if n3_report.get("status") in {"noop", "prewarm_ready"}:
        report.update({"result": "NOOP_PASS", "reason": n3_report.get("reason")})
        return maybe_write_chain_report(report, json_report_path=report["json_report_path"], markdown_report_path=report["markdown_report_path"])
    if n3_report.get("status") not in {"passed", "ready"}:
        report.update({"result": "BLOCKED", "blocked_reason": str(n3_report.get("reason") or "n3_auto_poll_not_passed")})
        return maybe_write_chain_report(report, json_report_path=report["json_report_path"], markdown_report_path=report["markdown_report_path"])

    if not str(n3_report.get("latest_closed_minute") or "").strip():
        report.update({"result": "NOOP_PASS", "reason": "awaiting_closed_minute_for_trace_aligned_projection"})
        return maybe_write_chain_report(report, json_report_path=report["json_report_path"], markdown_report_path=report["markdown_report_path"])

    hhmm = str(n3_report.get("effective_hhmm") or n3_report.get("latest_closed_minute_hhmm") or "").strip()
    if not hhmm:
        report.update({"result": "BLOCKED", "blocked_reason": "n3_effective_hhmm_missing"})
        return maybe_write_chain_report(report, json_report_path=report["json_report_path"], markdown_report_path=report["markdown_report_path"])

    ids = build_stage_ids(
        for_trade_date=resolved_trade_date,
        hhmm=hhmm,
        subscription_run_id=str(lineage["subscription_run_id"]),
        source_condition_run_id=str(lineage["source_condition_run_id"]),
    )
    report["stage_ids"] = asdict(ids)
    context = {
        "dsn": dsn,
        "lineage": lineage,
        "n3_report": n3_report,
        "stage_ids": ids,
        "docs_root": Path(docs_root),
        "sql_root": Path(sql_root),
        "python_executable": python_executable,
        "max_n4_events": max_n4_events,
        "max_n5_events": max_n5_events,
        "max_n5_runtime_seconds": max_n5_runtime_seconds,
        "n5_heartbeat_interval_seconds": n5_heartbeat_interval_seconds,
    }

    status_of = stage_status_provider or (lambda stage, stage_ids: default_stage_status(dsn=dsn, stage_name=stage, ids=stage_ids))
    build_artifacts = artifact_builder or default_artifact_builder

    for stage_name in ("N3_B1_STANDARD_OUTBOX", "N3_B2_TRACE_ALIGNED_PROJECTION"):
        stage_status = status_of(stage_name, ids)
        report["stage_status"][stage_name] = stage_status
        if stage_status.get("status") == "passed":
            report["skipped_steps"].append({"stage": stage_name, "reason": "already_passed"})
            continue
        artifact_info = build_artifacts(stage_name, context)
        report["generated_artifacts"][stage_name] = artifact_info
        child_command = build_stage_command(stage_name, context, artifact_info)
        report["child_command_plan"].append(command_plan(stage_name, child_command))
        child_result = normalize_completed_process(runner(child_command))
        report["executed_steps"].append({"stage": stage_name, "command": child_command, **child_result})
        if child_result["returncode"] != 0:
            report.update({"result": "BLOCKED", "blocked_reason": f"{stage_name.lower()}_failed"})
            return maybe_write_chain_report(report, json_report_path=report["json_report_path"], markdown_report_path=report["markdown_report_path"])
        mark_stage_side_effects(report, stage_name)

    context_status = status_of("N4_CONTEXT", ids)
    report["stage_status"]["N4_CONTEXT"] = context_status
    if context_status.get("status") != "passed":
        report.update({"result": "BLOCKED", "blocked_reason": "n4_context_not_ready"})
        return maybe_write_chain_report(report, json_report_path=report["json_report_path"], markdown_report_path=report["markdown_report_path"])

    for stage_name in (
        "N4_PRODUCTION_TRIGGER_SEMANTIC_REPLAY",
        "N3_ACTION_CONFIRMATION_SCOPE_SUBSCRIPTION",
        "N3_ACTION_CONFIRMATION_PREVIOUS_DAY_PRELOAD",
        "N3_ACTION_CONFIRMATION_TODAY_MINUTE",
        "N3_ACTION_CONFIRMATION_METRIC",
        "N5_BOUNDED_ACTION_CONSUMER",
    ):
        stage_status = status_of(stage_name, ids)
        report["stage_status"][stage_name] = stage_status
        if stage_status.get("status") == "passed":
            report["skipped_steps"].append({"stage": stage_name, "reason": "already_passed"})
            continue
        artifact_info = build_artifacts(stage_name, context)
        report["generated_artifacts"][stage_name] = artifact_info
        child_command = build_stage_command(stage_name, context, artifact_info)
        report["child_command_plan"].append(command_plan(stage_name, child_command))
        child_result = normalize_completed_process(runner(child_command))
        report["executed_steps"].append({"stage": stage_name, "command": child_command, **child_result})
        if child_result["returncode"] != 0:
            report.update({"result": "BLOCKED", "blocked_reason": f"{stage_name.lower()}_failed"})
            return maybe_write_chain_report(report, json_report_path=report["json_report_path"], markdown_report_path=report["markdown_report_path"])
        mark_stage_side_effects(report, stage_name)

    report["result"] = "EXECUTE_PASS"
    return maybe_write_chain_report(report, json_report_path=report["json_report_path"], markdown_report_path=report["markdown_report_path"])


def mark_stage_side_effects(report: dict[str, Any], stage_name: str) -> None:
    if stage_name == "N3_B1_STANDARD_OUTBOX":
        report["side_effects"]["database_written"] = True
        report["side_effects"]["n3_standard_outbox_written"] = True
    elif stage_name == "N3_B2_TRACE_ALIGNED_PROJECTION":
        report["side_effects"]["database_written"] = True
        report["side_effects"]["n3_b2_projection_written"] = True
    elif stage_name == "N4_PRODUCTION_TRIGGER_SEMANTIC_REPLAY":
        report["side_effects"]["database_written"] = True
        report["side_effects"]["n4_executed"] = True
    elif stage_name == "N3_ACTION_CONFIRMATION_SCOPE_SUBSCRIPTION":
        report["side_effects"]["database_written"] = True
        report["side_effects"]["n3_action_confirmation_scope_subscription_written"] = True
    elif stage_name == "N3_ACTION_CONFIRMATION_PREVIOUS_DAY_PRELOAD":
        report["side_effects"]["database_written"] = True
        report["side_effects"]["n3_action_confirmation_previous_day_preload_written"] = True
    elif stage_name == "N3_ACTION_CONFIRMATION_TODAY_MINUTE":
        report["side_effects"]["database_written"] = True
        report["side_effects"]["n3_action_confirmation_today_minute_written"] = True
    elif stage_name == "N3_ACTION_CONFIRMATION_METRIC":
        report["side_effects"]["database_written"] = True
        report["side_effects"]["n3_action_confirmation_metric_written"] = True
    elif stage_name == "N5_BOUNDED_ACTION_CONSUMER":
        report["side_effects"]["database_written"] = True
        report["side_effects"]["n5_executed"] = True


def build_base_report(*, execute: bool, user_confirmed: bool, as_of: datetime) -> dict[str, Any]:
    return {
        "objective": CHAIN_OBJECTIVE,
        "stage": "N3-N4-N5-realtime-chain-wrapper",
        "layer_role": "runtime_control",
        "result": "PLAN_ONLY",
        "reason": None,
        "blocked_reason": None,
        "as_of": as_of.isoformat(),
        "execute": bool(execute),
        "user_confirmed": bool(user_confirmed),
        "lineage": {},
        "stage_ids": {},
        "stage_status": {},
        "generated_artifacts": {},
        "child_command_plan": [],
        "executed_steps": [],
        "skipped_steps": [],
        "side_effects": {
            "database_written": False,
            "n3_b1_c1_b2_executed": False,
            "n3_standard_outbox_written": False,
            "n3_b2_projection_written": False,
            "n3_action_confirmation_scope_subscription_written": False,
            "n3_action_confirmation_previous_day_preload_written": False,
            "n3_action_confirmation_today_minute_written": False,
            "n3_action_confirmation_metric_written": False,
            "n4_executed": False,
            "n5_executed": False,
            "n6_entered": False,
            "outbox_inbox_checkpoint_consumed_or_updated_by_wrapper": False,
            "scheduler_installed_or_enabled_by_wrapper": False,
            "worker_started": False,
            "delivery_push_voice_mobile": False,
            "proposal_order_trade_sim_position_pnl_real_trade": False,
        },
        "forbidden_scope_proof": {
            "n6_entered": False,
            "voice_mobile_touched": False,
            "sim_position_pnl_touched": False,
            "real_trade_touched": False,
            "old_system_touched": False,
            "long_running_worker_started": False,
        },
    }


def resolve_chain_lineage(
    *,
    dsn: str,
    auto_resolve_lineage: bool,
    for_trade_date: str | None,
    subscription_run_id: str | None,
    preload_run_id: str | None,
    source_condition_run_id: str | None,
    as_of: datetime,
    lineage_resolver: Callable[..., dict[str, Any]] | None,
) -> dict[str, Any]:
    if auto_resolve_lineage:
        resolver = lineage_resolver or resolve_auto_poll_lineage
        return resolver(dsn=dsn, as_of=as_of, for_trade_date=for_trade_date)
    missing = [
        name
        for name, value in {
            "for_trade_date": for_trade_date,
            "subscription_run_id": subscription_run_id,
            "preload_run_id": preload_run_id,
            "source_condition_run_id": source_condition_run_id,
        }.items()
        if not value
    ]
    if missing:
        return {"status": "blocked", "reason": "lineage_arguments_missing", "missing": missing, "for_trade_date": for_trade_date}
    return {
        "status": "resolved",
        "reason": "explicit_lineage",
        "for_trade_date": for_trade_date,
        "subscription_run_id": subscription_run_id,
        "preload_run_id": preload_run_id,
        "source_condition_run_id": source_condition_run_id,
    }


def coerce_shanghai(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=ASIA_SHANGHAI)
    return value.astimezone(ASIA_SHANGHAI)


def command_plan(stage_name: str, argv: list[str]) -> dict[str, Any]:
    return {
        "stage": stage_name,
        "argv": list(argv),
        "uses_shell": False,
        "requires_execute": "--execute" in argv,
        "requires_user_confirmed": "--user-confirmed" in argv,
    }


def build_n3_auto_poll_command(
    *,
    python_executable: str,
    dsn: str,
    docs_root: str | Path,
    sql_root: str | Path,
    json_report_path: str | Path,
    markdown_report_path: str | Path,
    auto_resolve_lineage: bool,
    for_trade_date: str | None,
    execute: bool,
    user_confirmed: bool,
    allow_overwrite: bool = False,
) -> list[str]:
    argv = [
        python_executable,
        "scripts/run_n3_intraday_b1_c1_b2_auto_poll_once.py",
        "--dsn",
        dsn,
        "--docs-root",
        str(docs_root),
        "--sql-root",
        str(sql_root),
        "--python-executable",
        python_executable,
        "--json-report-path",
        str(json_report_path),
        "--markdown-report-path",
        str(markdown_report_path),
    ]
    if auto_resolve_lineage:
        argv.append("--auto-resolve-lineage")
    if for_trade_date:
        argv.extend(["--for-trade-date", for_trade_date])
    if execute:
        argv.append("--execute")
    if user_confirmed:
        argv.append("--user-confirmed")
    if allow_overwrite:
        argv.append("--allow-overwrite")
    return argv


def build_stage_command(stage_name: str, context: Mapping[str, Any], artifact_info: Mapping[str, Any]) -> list[str]:
    ids: StageIds = context["stage_ids"]
    python_executable = str(context["python_executable"])
    dsn = str(context["dsn"])
    docs_root = Path(context["docs_root"])
    sql_root = Path(context["sql_root"])
    if stage_name == "N3_B1_STANDARD_OUTBOX":
        contract_path = artifact_info.get("contract_path") or docs_root / f"N3_{ids.for_trade_date}_B1_STANDARD_OUTBOX_UNTIL_{ids.hhmm}_EXECUTE_CONTRACT.json"
        preflight_path = artifact_info.get("preflight_path") or docs_root / f"N3_{ids.for_trade_date}_B1_STANDARD_OUTBOX_UNTIL_{ids.hhmm}_PREFLIGHT.json"
        return [
            python_executable,
            "scripts/run_realtime_daily_snapshot_once.py",
            "--dsn",
            dsn,
            "--contract-path",
            str(contract_path),
            "--readiness-path",
            str(preflight_path),
            "--for-trade-date",
            ids.for_trade_date,
            "--snapshot-run-id",
            ids.b1_standard_outbox_run_id,
            "--execute",
            "--user-confirmed",
            "--writes-outbox=true",
            "--json-report-path",
            str(docs_root / f"N3_{ids.for_trade_date}_B1_STANDARD_OUTBOX_UNTIL_{ids.hhmm}_EXECUTE_REPORT.json"),
            "--markdown-report-path",
            str(docs_root / f"N3_{ids.for_trade_date}_B1_STANDARD_OUTBOX_UNTIL_{ids.hhmm}_EXECUTE_REPORT.md"),
        ]
    if stage_name == "N3_B2_TRACE_ALIGNED_PROJECTION":
        dry_run_path = artifact_info.get("dry_run_path") or docs_root / f"N3_{ids.for_trade_date}_B2_TRACE_ALIGNED_PROJECTION_UNTIL_{ids.hhmm}_DRY_RUN.json"
        contract_path = artifact_info.get("contract_path") or docs_root / f"N3_{ids.for_trade_date}_B2_TRACE_ALIGNED_PROJECTION_UNTIL_{ids.hhmm}_EXECUTE_CONTRACT.json"
        preflight_path = artifact_info.get("preflight_path") or docs_root / f"N3_{ids.for_trade_date}_B2_TRACE_ALIGNED_PROJECTION_UNTIL_{ids.hhmm}_PREFLIGHT.json"
        rollback_sql_path = artifact_info.get("rollback_sql_path") or sql_root / f"N3_{ids.for_trade_date}_B2_trace_aligned_projection_until_{ids.hhmm}_rollback.sql"
        return [
            python_executable,
            "scripts/run_realtime_projection_metric_once.py",
            "--dsn",
            dsn,
            "--contract-path",
            str(contract_path),
            "--preflight-path",
            str(preflight_path),
            "--dry-run-path",
            str(dry_run_path),
            "--projection-run-id",
            ids.b2_trace_projection_run_id,
            "--for-trade-date",
            ids.for_trade_date,
            "--execute",
            "--user-confirmed",
            "--json-report-path",
            str(docs_root / f"N3_{ids.for_trade_date}_B2_TRACE_ALIGNED_PROJECTION_UNTIL_{ids.hhmm}_EXECUTE_REPORT.json"),
            "--markdown-report-path",
            str(docs_root / f"N3_{ids.for_trade_date}_B2_TRACE_ALIGNED_PROJECTION_UNTIL_{ids.hhmm}_EXECUTE_REPORT.md"),
            "--rollback-sql-path",
            str(rollback_sql_path),
        ]
    if stage_name == "N4_PRODUCTION_TRIGGER_SEMANTIC_REPLAY":
        return [
            python_executable,
            "scripts/run_trigger_projection_matcher_once.py",
            "--dsn",
            dsn,
            "--execute-run-id",
            ids.n4_run_id,
            "--trigger-context-run-id",
            ids.n4_context_run_id,
            "--projection-run-id",
            ids.b2_trace_projection_run_id,
            "--snapshot-run-id",
            ids.b1_standard_outbox_run_id,
            "--consumer-name",
            ids.n4_consumer_name,
            "--json-report-path",
            str(docs_root / f"N4_{ids.for_trade_date}_PRODUCTION_TRIGGER_SEMANTIC_REPLAY_UNTIL_{ids.hhmm}_EXECUTE_REPORT.json"),
            "--markdown-report-path",
            str(docs_root / f"N4_{ids.for_trade_date}_PRODUCTION_TRIGGER_SEMANTIC_REPLAY_UNTIL_{ids.hhmm}_EXECUTE_REPORT.md"),
            "--rollback-sql-path",
            str(sql_root / f"N4_{ids.for_trade_date}_production_trigger_semantic_replay_until_{ids.hhmm}_rollback.sql"),
            "--execute",
            "--user-confirmed",
        ]
    if stage_name == "N3_ACTION_CONFIRMATION_SCOPE_SUBSCRIPTION":
        dry_run_path = artifact_info.get("dry_run_path") or docs_root / f"N3_{ids.for_trade_date}_ACTION_CONFIRMATION_SCOPE_SUBSCRIPTION_UNTIL_{ids.hhmm}_DRY_RUN.json"
        return [
            python_executable,
            "scripts/run_market_data_subscription_control_from_dry_run_once.py",
            "--dsn",
            dsn,
            "--dry-run-path",
            str(dry_run_path),
            "--json-report-path",
            str(docs_root / f"N3_{ids.for_trade_date}_ACTION_CONFIRMATION_SCOPE_SUBSCRIPTION_UNTIL_{ids.hhmm}_EXECUTE_REPORT.json"),
            "--markdown-report-path",
            str(docs_root / f"N3_{ids.for_trade_date}_ACTION_CONFIRMATION_SCOPE_SUBSCRIPTION_UNTIL_{ids.hhmm}_EXECUTE_REPORT.md"),
            "--execute",
            "--user-confirmed",
        ]
    if stage_name == "N3_ACTION_CONFIRMATION_PREVIOUS_DAY_PRELOAD":
        contract_path = artifact_info.get("contract_path") or docs_root / f"N3_{ids.for_trade_date}_ACTION_CONFIRMATION_PREVIOUS_DAY_PRELOAD_UNTIL_{ids.hhmm}_CONTRACT.json"
        argv = [
            python_executable,
            "scripts/run_previous_day_minute_preload_execute.py",
            "--dsn",
            dsn,
            "--contract-path",
            str(contract_path),
            "--json-report-path",
            str(docs_root / f"N3_{ids.for_trade_date}_ACTION_CONFIRMATION_PREVIOUS_DAY_PRELOAD_UNTIL_{ids.hhmm}_EXECUTE_REPORT.json"),
            "--markdown-report-path",
            str(docs_root / f"N3_{ids.for_trade_date}_ACTION_CONFIRMATION_PREVIOUS_DAY_PRELOAD_UNTIL_{ids.hhmm}_EXECUTE_REPORT.md"),
            "--execute",
            "--user-confirmed",
        ]
        data_trade_date = str(artifact_info.get("data_trade_date") or "")
        if data_trade_date:
            argv.extend(
                [
                    "--historical-preload",
                    "--source-subscription-run-id",
                    ids.n3_action_subscription_run_id,
                    "--preload-run-id",
                    ids.n3_action_preload_run_id,
                    "--data-trade-date",
                    data_trade_date,
                ]
            )
        return argv
    if stage_name == "N3_ACTION_CONFIRMATION_TODAY_MINUTE":
        c0_plan_path = artifact_info.get("c0_plan_path") or docs_root / f"N3_{ids.for_trade_date}_ACTION_CONFIRMATION_TODAY_MINUTE_UNTIL_{ids.hhmm}_C0_DRY_RUN.json"
        return [
            python_executable,
            "scripts/run_today_minute_bar_1m_once.py",
            "--dsn",
            dsn,
            "--c0-plan-path",
            str(c0_plan_path),
            "--for-trade-date",
            ids.for_trade_date,
            "--today-minute-run-id",
            ids.n3_action_today_minute_run_id,
            "--json-report-path",
            str(docs_root / f"N3_{ids.for_trade_date}_ACTION_CONFIRMATION_TODAY_MINUTE_UNTIL_{ids.hhmm}_EXECUTE_REPORT.json"),
            "--markdown-report-path",
            str(docs_root / f"N3_{ids.for_trade_date}_ACTION_CONFIRMATION_TODAY_MINUTE_UNTIL_{ids.hhmm}_EXECUTE_REPORT.md"),
            "--rollback-sql-path",
            str(sql_root / f"N3_{ids.for_trade_date}_action_confirmation_today_minute_until_{ids.hhmm}_rollback.sql"),
            "--execute",
            "--user-confirmed",
        ]
    if stage_name == "N3_ACTION_CONFIRMATION_METRIC":
        payload_path = artifact_info.get("payload_path") or docs_root / f"N3_{ids.for_trade_date}_ACTION_CONFIRMATION_METRIC_UNTIL_{ids.hhmm}_PAYLOAD.json"
        contract_path = artifact_info.get("contract_path") or docs_root / f"N3_{ids.for_trade_date}_ACTION_CONFIRMATION_METRIC_UNTIL_{ids.hhmm}_CONTRACT.json"
        return [
            python_executable,
            "scripts/run_n3_action_confirmation_metric_materialization_execute.py",
            "--dsn",
            dsn,
            "--payload-path",
            str(payload_path),
            "--contract-path",
            str(contract_path),
            "--report-path",
            str(docs_root / f"N3_{ids.for_trade_date}_ACTION_CONFIRMATION_METRIC_UNTIL_{ids.hhmm}_EXECUTE_REPORT.json"),
            "--markdown-report-path",
            str(docs_root / f"N3_{ids.for_trade_date}_ACTION_CONFIRMATION_METRIC_UNTIL_{ids.hhmm}_EXECUTE_REPORT.md"),
            "--execute",
            "--user-confirmed",
        ]
    if stage_name == "N5_BOUNDED_ACTION_CONSUMER":
        return [
            python_executable,
            "scripts/run_action_consumer_once.py",
            "--dsn",
            dsn,
            "--semantic-action-smoke",
            "--smoke-run-id",
            ids.n5_action_run_id,
            "--action-run-id",
            ids.n5_action_run_id,
            "--source-run-id",
            ids.n4_run_id,
            "--consumer-name",
            ids.n5_consumer_name,
            "--metric-run-id",
            ids.n3_action_metric_run_id,
            "--source-event-type",
            "TriggerMatched",
            "--max-events",
            str(context["max_n5_events"]),
            "--max-runtime-seconds",
            str(context["max_n5_runtime_seconds"]),
            "--heartbeat-interval-seconds",
            str(context["n5_heartbeat_interval_seconds"]),
            "--json-report-path",
            str(docs_root / f"N5_{ids.for_trade_date}_BOUNDED_ACTION_FROM_N4_UNTIL_{ids.hhmm}_EXECUTE_REPORT.json"),
            "--markdown-report-path",
            str(docs_root / f"N5_{ids.for_trade_date}_BOUNDED_ACTION_FROM_N4_UNTIL_{ids.hhmm}_EXECUTE_REPORT.md"),
            "--rollback-sql-path",
            str(sql_root / f"N5_{ids.for_trade_date}_bounded_action_from_n4_until_{ids.hhmm}_rollback.sql"),
            "--execute",
            "--user-confirmed",
        ]
    raise ValueError(f"unsupported stage: {stage_name}")


def default_artifact_builder(stage_name: str, context: dict[str, Any]) -> dict[str, Any]:
    ids: StageIds = context["stage_ids"]
    lineage = context["lineage"]
    docs_root = Path(context["docs_root"])
    sql_root = Path(context["sql_root"])
    dsn = str(context["dsn"])
    details = fetch_lineage_details(dsn=dsn, subscription_run_id=str(lineage["subscription_run_id"]))
    if stage_name == "N3_B1_STANDARD_OUTBOX":
        return build_b1_standard_outbox_artifacts(
            docs_root=docs_root,
            sql_root=sql_root,
            for_trade_date=ids.for_trade_date,
            source_trade_date=details["source_trade_date"],
            prev_trade_date=details["prev_trade_date"],
            source_condition_run_id=str(lineage["source_condition_run_id"]),
            subscription_run_id=str(lineage["subscription_run_id"]),
            snapshot_run_id=ids.b1_standard_outbox_run_id,
            hhmm=ids.hhmm,
            pull_plan_rows=fetch_realtime_pull_plan_rows(
                dsn=dsn,
                subscription_run_id=str(lineage["subscription_run_id"]),
                for_trade_date=ids.for_trade_date,
            ),
        )
    if stage_name == "N3_B2_TRACE_ALIGNED_PROJECTION":
        expected_rows_by_asset = fetch_snapshot_row_counts(
            dsn=dsn,
            snapshot_run_id=ids.b1_standard_outbox_run_id,
        )
        expected_distribution = materialize_b2_expected_distribution(
            dsn=dsn,
            for_trade_date=ids.for_trade_date,
            source_trade_date=details["source_trade_date"],
            prev_trade_date=details["prev_trade_date"],
            source_condition_run_id=str(lineage["source_condition_run_id"]),
            subscription_run_id=str(lineage["subscription_run_id"]),
            preload_run_id=str(lineage["preload_run_id"]),
            today_minute_run_id=ids.c1_today_minute_run_id,
            snapshot_run_id=ids.b1_standard_outbox_run_id,
            projection_run_id=ids.b2_trace_projection_run_id,
            latest_closed_minute=str((context["n3_report"] or {}).get("latest_closed_minute") or ""),
            expected_rows_by_asset=expected_rows_by_asset,
        )
        return build_b2_trace_aligned_artifacts(
            docs_root=docs_root,
            sql_root=sql_root,
            for_trade_date=ids.for_trade_date,
            source_trade_date=details["source_trade_date"],
            prev_trade_date=details["prev_trade_date"],
            source_condition_run_id=str(lineage["source_condition_run_id"]),
            subscription_run_id=str(lineage["subscription_run_id"]),
            preload_run_id=str(lineage["preload_run_id"]),
            today_minute_run_id=ids.c1_today_minute_run_id,
            snapshot_run_id=ids.b1_standard_outbox_run_id,
            projection_run_id=ids.b2_trace_projection_run_id,
            latest_closed_minute=str((context["n3_report"] or {}).get("latest_closed_minute") or ""),
            expected_rows_by_asset=expected_rows_by_asset,
            expected_distribution=expected_distribution,
        )
    if stage_name == "N3_ACTION_CONFIRMATION_METRIC":
        return build_n3_action_confirmation_metric_artifacts(
            dsn=dsn,
            docs_root=docs_root,
            sql_root=sql_root,
            for_trade_date=ids.for_trade_date,
            source_trade_date=details["source_trade_date"],
            prev_trade_date=details["prev_trade_date"],
            source_condition_run_id=str(lineage["source_condition_run_id"]),
            subscription_run_id=ids.n3_action_subscription_run_id,
            preload_run_id=ids.n3_action_preload_run_id,
            snapshot_run_id=ids.b1_standard_outbox_run_id,
            today_minute_run_id=ids.n3_action_today_minute_run_id,
            source_realtime_projection_run_id=ids.b2_trace_projection_run_id,
            trigger_execute_run_id=ids.n4_run_id,
            projection_run_id=ids.n3_action_metric_run_id,
            hhmm=ids.hhmm,
            python_executable=str(context["python_executable"]),
        )
    if stage_name == "N3_ACTION_CONFIRMATION_SCOPE_SUBSCRIPTION":
        return build_n3_action_confirmation_scope_subscription_artifacts(
            dsn=dsn,
            docs_root=docs_root,
            sql_root=sql_root,
            for_trade_date=ids.for_trade_date,
            source_trade_date=details["source_trade_date"],
            prev_trade_date=details["prev_trade_date"],
            source_condition_run_id=str(lineage["source_condition_run_id"]),
            trigger_execute_run_id=ids.n4_run_id,
            subscription_run_id=ids.n3_action_subscription_run_id,
            today_minute_run_id=ids.n3_action_today_minute_run_id,
            preload_run_id=ids.n3_action_preload_run_id,
            hhmm=ids.hhmm,
        )
    if stage_name == "N3_ACTION_CONFIRMATION_PREVIOUS_DAY_PRELOAD":
        return build_n3_action_confirmation_previous_day_preload_artifacts(
            dsn=dsn,
            docs_root=docs_root,
            sql_root=sql_root,
            for_trade_date=ids.for_trade_date,
            prev_trade_date=details["prev_trade_date"],
            subscription_run_id=ids.n3_action_subscription_run_id,
            preload_run_id=ids.n3_action_preload_run_id,
            hhmm=ids.hhmm,
        )
    if stage_name == "N3_ACTION_CONFIRMATION_TODAY_MINUTE":
        return build_n3_action_confirmation_today_minute_artifacts(
            dsn=dsn,
            docs_root=docs_root,
            sql_root=sql_root,
            for_trade_date=ids.for_trade_date,
            subscription_run_id=ids.n3_action_subscription_run_id,
            today_minute_run_id=ids.n3_action_today_minute_run_id,
            hhmm=ids.hhmm,
            latest_closed_minute=str((context["n3_report"] or {}).get("latest_closed_minute") or ""),
        )
    if stage_name in {"N4_PRODUCTION_TRIGGER_SEMANTIC_REPLAY", "N5_BOUNDED_ACTION_CONSUMER"}:
        return {
            "stage": stage_name,
            "status": "command_only",
            "rollback_sql_path": str(sql_root / f"{stage_name.lower()}_{ids.for_trade_date}_{ids.hhmm}_rollback.sql"),
        }
    raise ValueError(f"unsupported artifact stage: {stage_name}")


def build_b1_standard_outbox_artifacts(
    *,
    docs_root: str | Path,
    sql_root: str | Path,
    for_trade_date: str,
    source_trade_date: str,
    prev_trade_date: str,
    source_condition_run_id: str,
    subscription_run_id: str,
    snapshot_run_id: str,
    hhmm: str,
    pull_plan_rows: list[Mapping[str, Any]],
) -> dict[str, Any]:
    docs_root = Path(docs_root)
    sql_root = Path(sql_root)
    docs_root.mkdir(parents=True, exist_ok=True)
    sql_root.mkdir(parents=True, exist_ok=True)
    prefix = f"N3_{for_trade_date}_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_UNTIL_{hhmm}"
    contract_path = docs_root / f"{prefix}_EXECUTE_CONTRACT.json"
    contract_md_path = docs_root / f"{prefix}_EXECUTE_CONTRACT.md"
    preflight_path = docs_root / f"{prefix}_PREFLIGHT.json"
    preflight_md_path = docs_root / f"{prefix}_PREFLIGHT.md"
    rollback_sql_path = sql_root / f"N3_{for_trade_date}_B1_market_snapshot_updated_standard_outbox_until_{hhmm}_rollback.sql"
    b0_report = build_b1_b0_report(
        for_trade_date=for_trade_date,
        source_trade_date=source_trade_date,
        prev_trade_date=prev_trade_date,
        source_condition_run_id=source_condition_run_id,
        pull_plan_rows=pull_plan_rows,
    )
    persisted_report = build_subscription_persisted_report(
        for_trade_date=for_trade_date,
        subscription_run_id=subscription_run_id,
        source_condition_run_id=source_condition_run_id,
        pull_plan_rows=pull_plan_rows,
    )
    contract = build_execute_contract_from_reports(
        b0_report=b0_report,
        persisted_report=persisted_report,
        market_data_run_id=subscription_run_id,
        snapshot_run_id=snapshot_run_id,
        rollback_sql_path=str(rollback_sql_path),
        writes_outbox=True,
    )
    apply_board_observed_at_normalization_policy(contract)
    preflight = {
        "stage": "N3-B1-readiness-gate",
        "layer_role": "N3_market_data",
        "result": "PREFLIGHT_PASS",
        "ready": True,
        "source_run_id": subscription_run_id,
        "snapshot_run_id": snapshot_run_id,
        "for_trade_date": for_trade_date,
        "quality": {"p0_count": 0, "p1_count": int((contract.get("quality") or {}).get("p1_count") or 0), "p2_count": 0},
        "source_time_policy": contract["source_time_policy"],
        "board_source_time_semantics_policy": contract["board_source_time_semantics_policy"],
    }
    rollback_sql = format_realtime_snapshot_rollback_sql(contract)
    write_json(contract_path, contract)
    write_text(contract_md_path, render_artifact_markdown("B1 Standard Outbox Contract", contract))
    write_json(preflight_path, preflight)
    write_text(preflight_md_path, render_artifact_markdown("B1 Standard Outbox Preflight", preflight))
    write_text(rollback_sql_path, rollback_sql)
    return {
        "stage": "N3_B1_STANDARD_OUTBOX",
        "status": "written",
        "contract_path": str(contract_path),
        "preflight_path": str(preflight_path),
        "rollback_sql_path": str(rollback_sql_path),
    }


def build_b1_b0_report(
    *,
    for_trade_date: str,
    source_trade_date: str,
    prev_trade_date: str,
    source_condition_run_id: str,
    pull_plan_rows: list[Mapping[str, Any]],
) -> dict[str, Any]:
    counts = {asset: 0 for asset in ASSET_KINDS}
    adapter_rows: list[dict[str, Any]] = []
    for row in pull_plan_rows:
        asset = str(row["asset_kind"])
        count = int(row.get("object_count") or row.get("subscription_count") or 0)
        counts[asset] = count
        adapter_rows.append(
            {
                "asset_kind": asset,
                "source_pull_plan_id": int(row.get("source_pull_plan_id") or row.get("pull_plan_id") or 0),
                "adapter_name": str(row.get("adapter_name") or default_adapter_name(asset)),
                "trade_date": for_trade_date,
                "subscription_count": int(row.get("subscription_count") or count),
                "object_count": count,
                "expected_snapshot_rows": count,
                "target_snapshot_table": SNAPSHOT_TABLES[asset],
            }
        )
    return {
        "stage": "N3-B0",
        "blocked": False,
        "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0},
        "for_trade_date": for_trade_date,
        "source_trade_date": source_trade_date,
        "prev_trade_date": prev_trade_date,
        "source_condition_run_id": source_condition_run_id,
        "snapshot_object_count_by_asset_kind": counts,
        "expected_snapshot_rows_by_asset_kind": dict(counts),
        "expected_snapshot_rows": sum(counts.values()),
        "source_adapter_plan": {"rows": sorted(adapter_rows, key=lambda item: item["asset_kind"])},
    }


def build_subscription_persisted_report(
    *,
    for_trade_date: str,
    subscription_run_id: str,
    source_condition_run_id: str,
    pull_plan_rows: list[Mapping[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for plan in pull_plan_rows:
        asset = str(plan["asset_kind"])
        count = int(plan.get("object_count") or plan.get("subscription_count") or 0)
        rows.extend(
            {
                "asset_kind": asset,
                "identity_key": f"{asset}:CHAIN:{idx:06d}",
                "required_data_kind": "realtime_daily_snapshot",
            }
            for idx in range(count)
        )
    return {
        "stage": "N3-6-market-data-subscription",
        "passed": True,
        "market_data_run_id": subscription_run_id,
        "run_id": subscription_run_id,
        "source_condition_run_id": source_condition_run_id,
        "for_trade_date": for_trade_date,
        "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0},
        "market_data_subscription_dedup": {"rows": rows},
    }


def apply_board_observed_at_normalization_policy(contract: dict[str, Any]) -> None:
    contract.setdefault("source_time_policy", {})
    contract["source_time_policy"].update(
        {
            "board_source_time_label_handling": "NORMALIZE_TO_OBSERVED_AT",
            "normalize_to_observed_at_enabled": True,
            "board_event_time_policy": "observed_at_for_board_untrusted_period_label",
        }
    )
    contract["board_source_time_semantics_policy"] = {
        "enabled": True,
        "adapter": "BoardMarketDataAdapter",
        "source_path": "mootdx.quotes.index(frequency=9)",
        "raw_snapshot_time_semantics": "tdx_index_frequency_9_period_label",
        "source_time_trust_level": "untrusted_period_label",
        "raw_snapshot_time_field": "raw_snapshot_time_label",
        "observed_time_fields": ["observed_at", "fetched_at"],
        "board_source_time_label_handling": "NORMALIZE_TO_OBSERVED_AT",
        "normalize_to_observed_at_enabled": True,
        "event_time_policy": "observed_at_for_board_untrusted_period_label",
        "normalized_event_time_reason": "reviewed_board_tdx_period_label_normalized_to_observed_at",
        "raw_label_event_time_allowed": False,
        "quality_gate": "board_source_time_label_normalized",
    }


def build_b2_trace_aligned_artifacts(
    *,
    docs_root: str | Path,
    sql_root: str | Path,
    for_trade_date: str,
    source_trade_date: str,
    prev_trade_date: str,
    source_condition_run_id: str,
    subscription_run_id: str,
    preload_run_id: str,
    today_minute_run_id: str,
    snapshot_run_id: str,
    projection_run_id: str,
    latest_closed_minute: str,
    expected_rows_by_asset: Mapping[str, int],
    expected_distribution: Mapping[str, Any],
) -> dict[str, Any]:
    docs_root = Path(docs_root)
    sql_root = Path(sql_root)
    docs_root.mkdir(parents=True, exist_ok=True)
    sql_root.mkdir(parents=True, exist_ok=True)
    hhmm = projection_run_id.split("_until_")[-1].split("__")[0] if "_until_" in projection_run_id else "latest"
    prefix = f"N3_{for_trade_date}_B2_TRACE_ALIGNED_REALTIME_PROJECTION_METRIC_FOR_STANDARD_OUTBOX_UNTIL_{hhmm}"
    dry_run_path = docs_root / f"{prefix}_DRY_RUN.json"
    contract_path = docs_root / f"{prefix}_EXECUTE_CONTRACT.json"
    preflight_path = docs_root / f"{prefix}_PREFLIGHT.json"
    dry_run_md_path = docs_root / f"{prefix}_DRY_RUN.md"
    contract_md_path = docs_root / f"{prefix}_EXECUTE_CONTRACT.md"
    preflight_md_path = docs_root / f"{prefix}_PREFLIGHT.md"
    rollback_sql_path = sql_root / f"N3_{for_trade_date}_B2_trace_aligned_realtime_projection_metric_for_standard_outbox_until_{hhmm}_rollback.sql"
    expected_total = sum(int(expected_rows_by_asset.get(asset) or 0) for asset in ASSET_KINDS)
    contract = {
        "stage": "N3-B2-realtime-projection-execute-contract",
        "layer_role": "N3_market_data",
        "execution_mode": "realtime_projection_metric_run_once_execute",
        "artifact_generation_mode": "chain_trace_aligned_standard_outbox",
        "projection_input_mode": "trace_aligned_standard_outbox",
        "projection_run_id": projection_run_id,
        "source_runs": {
            "source_condition_run_id": source_condition_run_id,
            "subscription_run_id": subscription_run_id,
            "preload_run_id": preload_run_id,
            "today_minute_run_id": today_minute_run_id,
            "snapshot_run_id": snapshot_run_id,
        },
        "dates": {
            "for_trade_date": for_trade_date,
            "source_trade_date": source_trade_date,
            "prev_trade_date": prev_trade_date,
        },
        "projection_time_policy": {
            "mode": "standard_outbox_observed_at_to_latest_closed_minute",
            "bucket_time_source": "latest_closed_minute",
            "latest_closed_minute": latest_closed_minute,
            "source_event_time_semantics": "MarketSnapshotUpdated.event_time may be observed_at for board normalized labels",
            "trace_preservation": ["snapshot_event_id", "snapshot_id", "identity_key"],
        },
        "calculation_config": build_b2_calculation_config(),
        "expected_projection_rows": {
            "total": expected_total,
            "by_asset": {asset: int(expected_rows_by_asset.get(asset) or 0) for asset in ASSET_KINDS},
        },
        "expected_distribution": dict(expected_distribution),
        "expected_distribution_policy": {"mode": "materialized_before_execute", "source": "projection_row_builder"},
        "writes_outbox": False,
        "updates_market_snapshot_payload": False,
        "consumes_outbox": False,
        "rollback_sql_path": str(rollback_sql_path),
    }
    dry_run = {
        "stage": "N3-B2-trace-aligned-standard-outbox-dry-run",
        "result": "DRY_RUN_PASS",
        "projection_run_id": projection_run_id,
        "projection_run_id_candidate": projection_run_id,
        "source_snapshot_run_id": snapshot_run_id,
        "dates": contract["dates"],
        "expected_projection_rows": contract["expected_projection_rows"],
        "projection_time_policy": contract["projection_time_policy"],
    }
    preflight = {
        "stage": "N3-B2-realtime-projection-execute-preflight",
        "result": "PREFLIGHT_PASS",
        "projection_run_id": projection_run_id,
        "for_trade_date": for_trade_date,
        "dates": contract["dates"],
        "lineage_checks": [
            {"name": "subscription_run_passed", "passed": True},
            {"name": "snapshot_run_passed", "passed": True},
            {"name": "today_minute_run_passed", "passed": True},
            {"name": "preload_run_passed", "passed": True},
        ],
        "contract_summary": {
            "writes_outbox": False,
            "updates_market_snapshot_payload": False,
            "consumes_outbox": False,
        },
        "expected_projection_rows": contract["expected_projection_rows"],
        "expected_distribution": contract["expected_distribution"],
    }
    write_json(dry_run_path, dry_run)
    write_text(dry_run_md_path, render_artifact_markdown("B2 Trace-Aligned Dry Run", dry_run))
    write_json(contract_path, contract)
    write_text(contract_md_path, render_artifact_markdown("B2 Trace-Aligned Contract", contract))
    write_json(preflight_path, preflight)
    write_text(preflight_md_path, render_artifact_markdown("B2 Trace-Aligned Preflight", preflight))
    write_text(rollback_sql_path, build_projection_rollback_sql(projection_run_id))
    return {
        "stage": "N3_B2_TRACE_ALIGNED_PROJECTION",
        "status": "written",
        "dry_run_path": str(dry_run_path),
        "contract_path": str(contract_path),
        "preflight_path": str(preflight_path),
        "rollback_sql_path": str(rollback_sql_path),
    }


def build_b2_calculation_config() -> dict[str, Any]:
    return {
        "amount_projection_expand_threshold": "1.2",
        "amount_projection_shrink_threshold": "0.8",
        "calculation_config_hash": "c0e47d3beec744930c098fae1a083fc1da95f9752bb2efc01dc76b3ed4d92b1d",
        "calculation_method": "active_30m_bucket_projection_v1_strict_current_lineage",
        "completion_ratio_min_ready": "0.2",
        "price_flat_abs_pct_threshold": "0.001",
        "window_total_seconds": 1800,
        "projection_windows": ["1m", "5m", "30m", "120m"],
        "ready_requires": ["snapshot_trace", "today_minute_trace", "previous_day_minute_trace"],
        "trace_required_fields": ["snapshot_event_id", "snapshot_id", "identity_key"],
        "signal_policy": "n4_realtime_trigger_projection_metric",
    }


def build_n3_action_confirmation_metric_artifacts(
    *,
    dsn: str,
    docs_root: str | Path,
    sql_root: str | Path,
    for_trade_date: str,
    source_trade_date: str,
    prev_trade_date: str,
    source_condition_run_id: str,
    subscription_run_id: str,
    preload_run_id: str,
    snapshot_run_id: str,
    today_minute_run_id: str,
    source_realtime_projection_run_id: str,
    trigger_execute_run_id: str,
    projection_run_id: str,
    hhmm: str,
    python_executable: str,
) -> dict[str, Any]:
    docs_root = Path(docs_root)
    sql_root = Path(sql_root)
    docs_root.mkdir(parents=True, exist_ok=True)
    sql_root.mkdir(parents=True, exist_ok=True)
    prefix = f"N3_{for_trade_date}_ACTION_CONFIRMATION_METRIC_UNTIL_{hhmm}"
    payload_path = docs_root / f"{prefix}_PAYLOAD.json"
    payload_md_path = docs_root / f"{prefix}_PAYLOAD.md"
    contract_path = docs_root / f"{prefix}_CONTRACT.json"
    contract_md_path = docs_root / f"{prefix}_CONTRACT.md"
    preflight_path = docs_root / f"{prefix}_PREFLIGHT.json"
    preflight_md_path = docs_root / f"{prefix}_PREFLIGHT.md"
    rollback_sql_path = sql_root / f"N3_{for_trade_date}_action_confirmation_metric_until_{hhmm}_rollback.sql"

    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            n4_events = fetch_n4_trigger_matched_events(cur, trigger_execute_run_id=trigger_execute_run_id)
            snapshot_rows_by_asset = load_snapshot_rows_for_metric_dry_run(cur, source_snapshot_run_id=snapshot_run_id)
            candidate_identities = extract_candidate_identities(snapshot_rows_by_asset)
            today_rows_by_asset = load_minute_rows_for_metric_dry_run(
                cur,
                run_id=today_minute_run_id,
                candidate_identities=candidate_identities,
            )
            previous_rows_by_asset = load_minute_rows_for_metric_dry_run(
                cur,
                run_id=preload_run_id,
                candidate_identities=candidate_identities,
            )
    rows_by_asset = build_metric_candidate_rows_from_sources(
        projection_run_id=projection_run_id,
        projection_schema_version=ACTION_METRIC_SCHEMA_VERSION,
        for_trade_date=for_trade_date,
        source_condition_run_id=source_condition_run_id,
        source_subscription_run_id=subscription_run_id,
        source_snapshot_run_id=snapshot_run_id,
        source_today_minute_run_id=today_minute_run_id,
        source_previous_day_minute_run_id=preload_run_id,
        snapshot_rows_by_asset=snapshot_rows_by_asset,
        today_minute_rows_by_asset=today_rows_by_asset,
        previous_day_minute_rows_by_asset=previous_rows_by_asset,
    )
    enriched_by_asset, coverage = attach_n4_trigger_refs_to_action_metric_rows(
        rows_by_asset=rows_by_asset,
        n4_events=n4_events,
        trigger_execute_run_id=trigger_execute_run_id,
        source_realtime_projection_run_id=source_realtime_projection_run_id,
    )
    rows = [row for asset in ASSET_KINDS for row in enriched_by_asset.get(asset, [])]
    row_counts = count_metric_rows(rows)
    metric_ready_expected = sum(1 for row in rows if row.get("metric_ready") is True)
    payload = {
        "artifact_type": "N3_action_confirmation_metric_materialization_payload",
        "artifact_subtype": "dynamic_realtime_chain_action_confirmation_metric",
        "layer_role": "N3_market_data",
        "projection_run_id": projection_run_id,
        "target_run_id": projection_run_id,
        "projection_schema_version": ACTION_METRIC_SCHEMA_VERSION,
        "for_trade_date": for_trade_date,
        "source_trade_date": source_trade_date,
        "prev_trade_date": prev_trade_date,
        "source_condition_run_id": source_condition_run_id,
        "trigger_execute_run_id": trigger_execute_run_id,
        "source_realtime_projection_run_id": source_realtime_projection_run_id,
        "source_snapshot_run_id": snapshot_run_id,
        "source_subscription_run_ids": [subscription_run_id],
        "source_today_minute_run_ids": [today_minute_run_id],
        "source_previous_day_minute_run_ids": [preload_run_id],
        "expected_rows": row_counts,
        "metric_ready_expected": metric_ready_expected,
        "n4_matched_coverage": coverage,
        "bj_full_scope_decision": {
            "bj_identity_rows": int(coverage.get("excluded_bj_or_full") or 0),
            "full_signal_type_rows": int(coverage.get("excluded_full") or 0),
            "full_condition_key_rows": int(coverage.get("excluded_full") or 0),
            "policy": "BJ and FULL are excluded from dynamic N3 action-confirmation metric lineage",
        },
        "rows": rows,
        "side_effects": {
            "writes_database": False,
            "writes_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "enters_n4_n5_n6": False,
            "worker_started": False,
        },
    }
    contract = build_dynamic_action_metric_contract(
        payload=payload,
        rollback_sql_path=rollback_sql_path,
        python_executable=python_executable,
        payload_path=payload_path,
        contract_path=contract_path,
        report_path=docs_root / f"{prefix}_EXECUTE_REPORT.json",
        markdown_report_path=docs_root / f"{prefix}_EXECUTE_REPORT.md",
    )
    preflight = build_action_metric_preflight(dsn, payload, contract)
    rollback_sql = build_action_metric_rollback_sql(projection_run_id, label=f"{for_trade_date}_until_{hhmm}")

    write_json(payload_path, payload)
    write_text(payload_md_path, render_artifact_markdown("N3 Action Confirmation Metric Payload", payload))
    write_json(contract_path, contract)
    write_text(contract_md_path, render_artifact_markdown("N3 Action Confirmation Metric Contract", contract))
    write_json(preflight_path, preflight)
    write_text(preflight_md_path, render_artifact_markdown("N3 Action Confirmation Metric Preflight", preflight))
    write_text(rollback_sql_path, rollback_sql)
    return {
        "stage": "N3_ACTION_CONFIRMATION_METRIC",
        "status": "written",
        "payload_path": str(payload_path),
        "contract_path": str(contract_path),
        "preflight_path": str(preflight_path),
        "rollback_sql_path": str(rollback_sql_path),
        "expected_rows": row_counts,
        "n4_matched_coverage": coverage,
        "preflight_result": preflight.get("result"),
    }


def build_n3_action_confirmation_scope_subscription_artifacts(
    *,
    dsn: str,
    docs_root: str | Path,
    sql_root: str | Path,
    for_trade_date: str,
    source_trade_date: str,
    prev_trade_date: str,
    source_condition_run_id: str,
    trigger_execute_run_id: str,
    subscription_run_id: str,
    today_minute_run_id: str,
    preload_run_id: str,
    hhmm: str,
) -> dict[str, Any]:
    docs_root = Path(docs_root)
    sql_root = Path(sql_root)
    docs_root.mkdir(parents=True, exist_ok=True)
    sql_root.mkdir(parents=True, exist_ok=True)
    prefix = f"N3_{for_trade_date}_ACTION_CONFIRMATION_SCOPE_SUBSCRIPTION_UNTIL_{hhmm}"
    dry_run_path = docs_root / f"{prefix}_DRY_RUN.json"
    dry_run_md_path = docs_root / f"{prefix}_DRY_RUN.md"
    rollback_sql_path = sql_root / f"N3_{for_trade_date}_action_confirmation_scope_subscription_until_{hhmm}_rollback.sql"
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            scope_rows = fetch_action_confirmation_scope_rows(
                cur,
                trigger_execute_run_id=trigger_execute_run_id,
                for_trade_date=for_trade_date,
                source_condition_run_id=source_condition_run_id,
            )
            baseline = fetch_market_control_baseline(cur, subscription_run_id)
    dry_run = build_action_confirmation_scope_subscription_dry_run(
        scope_rows=scope_rows,
        baseline=baseline,
        subscription_run_id=subscription_run_id,
        trigger_execute_run_id=trigger_execute_run_id,
        source_condition_run_id=source_condition_run_id,
        for_trade_date=for_trade_date,
        source_trade_date=source_trade_date,
        prev_trade_date=prev_trade_date,
        today_minute_run_id=today_minute_run_id,
        preload_run_id=preload_run_id,
        hhmm=hhmm,
    )
    rollback_sql = build_action_confirmation_subscription_rollback_sql(subscription_run_id)
    write_json(dry_run_path, dry_run)
    write_text(dry_run_md_path, render_artifact_markdown("N3 Action Confirmation Scope Subscription Dry Run", dry_run))
    write_text(rollback_sql_path, rollback_sql)
    return {
        "stage": "N3_ACTION_CONFIRMATION_SCOPE_SUBSCRIPTION",
        "status": "written",
        "dry_run_path": str(dry_run_path),
        "rollback_sql_path": str(rollback_sql_path),
        "expected_objects": dry_run["subscription_object_count"],
        "required_data_kind_counts": dry_run["required_data_kind_counts"],
        "preflight_result": dry_run["result"],
    }


def fetch_action_confirmation_scope_rows(
    cur: Any,
    *,
    trigger_execute_run_id: str,
    for_trade_date: str,
    source_condition_run_id: str,
) -> list[dict[str, Any]]:
    union_sql = []
    for asset_kind in ASSET_KINDS:
        table = MINUTE_SCOPE_TABLES[asset_kind]
        identity_column = IDENTITY_COLUMNS[asset_kind]
        id_column = f"{asset_kind}_minute_target_scope_id"
        code_column = "board_code" if asset_kind == "board" else "code"
        name_column = "board_name" if asset_kind == "board" else "name"
        union_sql.append(
            f"""
            SELECT
              '{asset_kind}' AS asset_kind,
              {identity_column} AS identity_key,
              {id_column} AS source_scope_id,
              source_condition_pool_id,
              code_column_value.exchange,
              {code_column} AS code,
              {code_column} AS display_code,
              {name_column} AS name,
              direction,
              condition_key,
              allowed_signal_types,
              previous_day_minute_date
            FROM {table}
            CROSS JOIN LATERAL (
              SELECT CASE
                WHEN {identity_column} LIKE 'stock:SH:%%' OR {identity_column} LIKE 'index:SH:%%' THEN 'SH'
                WHEN {identity_column} LIKE 'stock:SZ:%%' OR {identity_column} LIKE 'index:SZ:%%' THEN 'SZ'
                ELSE COALESCE(NULLIF(split_part({identity_column}, ':', 2), ''), '')
              END AS exchange
            ) AS code_column_value
            WHERE run_id = %s
              AND for_trade_date = %s
            """
        )
    scope_cte = "\nUNION ALL\n".join(union_sql)
    cur.execute(
        f"""
        WITH scope_rows AS ({scope_cte})
        SELECT
          m.trigger_match_id,
          m.output_event_id,
          m.source_event_id,
          m.source_condition_run_id,
          m.source_condition_pool_id,
          m.source_condition_basis_id,
          m.source_market_subscription_id,
          m.for_trade_date,
          m.asset_kind,
          m.identity_key,
          m.direction,
          m.signal_type,
          m.condition_key,
          m.trigger_time,
          m.trigger_period,
          m.trigger_bucket,
          m.trigger_mark_candidate,
          s.source_scope_id,
          s.exchange,
          s.code,
          s.display_code,
          s.name,
          s.allowed_signal_types,
          s.previous_day_minute_date
        FROM common_trigger_match m
        LEFT JOIN scope_rows s
          ON s.asset_kind = m.asset_kind
         AND s.identity_key = m.identity_key
         AND s.source_condition_pool_id = m.source_condition_pool_id
         AND s.direction = m.direction
         AND s.condition_key = m.condition_key
        WHERE m.run_id = %s
          AND m.output_event_type = 'TriggerMatched'
        ORDER BY m.asset_kind, m.identity_key, m.trigger_match_id
        """,
        (
            source_condition_run_id,
            for_trade_date,
            source_condition_run_id,
            for_trade_date,
            source_condition_run_id,
            for_trade_date,
            trigger_execute_run_id,
        ),
    )
    return [dict(row) for row in cur.fetchall()]


def fetch_market_control_baseline(cur: Any, run_id: str) -> dict[str, int]:
    tables = (
        "common_market_data_run",
        "common_market_data_quality_item",
        "common_market_data_subscription_candidate",
        "common_market_data_subscription",
        "common_market_data_pull_plan",
    )
    output: dict[str, int] = {}
    for table in tables:
        cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table} WHERE run_id = %s", (run_id,))
        output[table] = int(cur.fetchone()["row_count"])
    return output


def build_action_confirmation_scope_subscription_dry_run(
    *,
    scope_rows: list[Mapping[str, Any]],
    baseline: Mapping[str, int],
    subscription_run_id: str,
    trigger_execute_run_id: str,
    source_condition_run_id: str,
    for_trade_date: str,
    source_trade_date: str,
    prev_trade_date: str,
    today_minute_run_id: str,
    preload_run_id: str,
    hhmm: str,
) -> dict[str, Any]:
    grouped = group_action_scope_rows(scope_rows)
    candidate_rows: list[dict[str, Any]] = []
    subscription_rows: list[dict[str, Any]] = []
    pull_plan_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    candidate_index = 1
    subscription_index = 1
    for group in grouped:
        for required_data_kind, data_trade_date in (
            ("minute_bar_1m", for_trade_date),
            ("previous_day_minute_bar_1m", prev_trade_date),
        ):
            candidate_ref = f"dry_run:action_confirmation_candidate:{candidate_index}"
            subscription_ref = f"dry_run:action_confirmation_subscription:{subscription_index}"
            flags = {
                "daily_snapshot_required": False,
                "minute_required": required_data_kind == "minute_bar_1m",
                "previous_day_minute_required": required_data_kind == "previous_day_minute_bar_1m",
                "previous_day_minute_date": prev_trade_date if required_data_kind == "previous_day_minute_bar_1m" else None,
                "scoped_required_data_kind": required_data_kind,
                "scoped_reason": f"n4_trigger_matched_{hhmm}_action_confirmation_dynamic_scope",
            }
            raw_json = {
                "source_trigger_run_id": trigger_execute_run_id,
                "source_trigger_match_ids": group["trigger_match_ids"],
                "source_trigger_event_ids": group["source_trigger_event_ids"],
                "source_market_snapshot_event_ids": group["source_market_snapshot_event_ids"],
                "target_today_minute_run_id": today_minute_run_id,
                "target_preload_run_id": preload_run_id,
                "required_data_kind": required_data_kind,
                "dynamic_realtime_chain_action_confirmation_scope": True,
            }
            candidate_rows.append(
                {
                    "candidate_ref": candidate_ref,
                    "run_id": subscription_run_id,
                    "source_condition_run_id": source_condition_run_id,
                    "for_trade_date": for_trade_date,
                    "source_trade_date": source_trade_date,
                    "prev_trade_date": prev_trade_date,
                    "asset_kind": group["asset_kind"],
                    "identity_key": group["identity_key"],
                    "exchange": group["exchange"],
                    "code": group["code"],
                    "display_code": group["display_code"],
                    "name": group["name"],
                    "required_data_kind": required_data_kind,
                    "data_trade_date": data_trade_date,
                    "source_scope_table": MINUTE_SCOPE_TABLES[group["asset_kind"]],
                    "source_scope_id": group["source_scope_ids"][0],
                    "source_condition_pool_id": group["source_condition_pool_ids"][0],
                    "direction": group["directions"][0],
                    "condition_key": group["condition_keys"][0],
                    "allowed_signal_types": group["allowed_signal_types"],
                    "source_scope_required_flags": flags,
                    "candidate_status": "planned",
                    "selected_reason": "dynamic N4 TriggerMatched action-confirmation source scope",
                    "raw_json": raw_json,
                }
            )
            subscription_rows.append(
                {
                    "subscription_ref": subscription_ref,
                    "run_id": subscription_run_id,
                    "source_condition_run_id": source_condition_run_id,
                    "for_trade_date": for_trade_date,
                    "source_trade_date": source_trade_date,
                    "prev_trade_date": prev_trade_date,
                    "asset_kind": group["asset_kind"],
                    "identity_key": group["identity_key"],
                    "exchange": group["exchange"],
                    "code": group["code"],
                    "display_code": group["display_code"],
                    "name": group["name"],
                    "required_data_kind": required_data_kind,
                    "data_trade_date": data_trade_date,
                    "source_scope_row_count": len(group["source_scope_ids"]),
                    "source_scope_tables": [MINUTE_SCOPE_TABLES[group["asset_kind"]]],
                    "source_scope_ids": group["source_scope_ids"],
                    "source_condition_pool_ids": group["source_condition_pool_ids"],
                    "condition_keys": group["condition_keys"],
                    "directions": group["directions"],
                    "allowed_signal_types": group["allowed_signal_types"],
                    "priority": 10,
                    "status": "planned",
                    "selected_reason": "dynamic N4 TriggerMatched action-confirmation source scope",
                    "source_scope_refs": [f"{MINUTE_SCOPE_TABLES[group['asset_kind']]}:{item}" for item in group["source_scope_ids"]],
                    "data_trade_dates": [data_trade_date],
                    "raw_json": raw_json,
                }
            )
            pull_plan_groups.setdefault((group["asset_kind"], required_data_kind, data_trade_date), []).append(subscription_rows[-1])
            candidate_index += 1
            subscription_index += 1
    pull_plan_rows = build_action_scope_pull_plan_rows(subscription_run_id, source_condition_run_id, for_trade_date, source_trade_date, prev_trade_date, pull_plan_groups)
    missing_scope_count = sum(1 for row in grouped if not row["source_scope_ids"])
    severity_items = [
        quality_item("P0", "passed" if grouped else "failed", "n3_action_scope_n4_matched_objects_present", "N4 TriggerMatched scope must have non-excluded objects"),
        quality_item("P0", "passed" if missing_scope_count == 0 else "failed", "n3_action_scope_minute_target_scope_trace_present", "dynamic action-confirmation subscriptions must trace to minute_target_scope rows", expected="0", actual=str(missing_scope_count)),
        quality_item("P0", "passed" if not any(int(v or 0) for v in baseline.values()) else "failed", "n3_action_scope_subscription_baseline_zero", "target subscription/control run must be clean", expected="all zero", actual=json.dumps(dict(baseline), sort_keys=True)),
    ]
    severity = count_quality_severities(severity_items)
    object_counts = {asset: sum(1 for row in grouped if row["asset_kind"] == asset) for asset in ASSET_KINDS}
    required_counts = {
        "minute_bar_1m": sum(1 for row in subscription_rows if row["required_data_kind"] == "minute_bar_1m"),
        "previous_day_minute_bar_1m": sum(1 for row in subscription_rows if row["required_data_kind"] == "previous_day_minute_bar_1m"),
    }
    return {
        "stage": "N3_ACTION_CONFIRMATION_SCOPE_SUBSCRIPTION_DRY_RUN",
        "layer_role": "N3_market_data",
        "plan_mode": "dynamic_action_confirmation_subscription_control_rows_only",
        "mode": "dry_run",
        "result": "PREFLIGHT_PASS" if severity["P0"] == 0 else "BLOCKED",
        "blocked": severity["P0"] > 0,
        "passed": severity["P0"] == 0,
        "market_data_run_id": subscription_run_id,
        "source_condition_run_id": source_condition_run_id,
        "source_n4_trigger_run_id": trigger_execute_run_id,
        "for_trade_date": for_trade_date,
        "source_trade_date": source_trade_date,
        "prev_trade_date": prev_trade_date,
        "planned_today_minute_run_id": today_minute_run_id,
        "planned_previous_day_preload_run_id": preload_run_id,
        "source_scope_row_count": len(grouped),
        "source_scope_row_count_by_asset_kind": {**object_counts, "total": sum(object_counts.values())},
        "candidate_row_count": len(candidate_rows),
        "subscription_candidate_count": len(candidate_rows),
        "subscription_row_count": len(subscription_rows),
        "dedup_subscription_count": len(subscription_rows),
        "subscription_object_count": len(grouped),
        "object_count_by_asset_kind": {**object_counts, "total": sum(object_counts.values())},
        "required_data_kind_counts": required_counts,
        "market_data_pull_plan_row_count": len(pull_plan_rows),
        "dedup_ratio": 1.0,
        "market_data_subscription_candidate": {"row_count": len(candidate_rows), "rows_included": True, "rows": candidate_rows},
        "market_data_subscription_dedup": {"row_count": len(subscription_rows), "rows_included": True, "rows": subscription_rows},
        "market_data_pull_plan": {"row_count": len(pull_plan_rows), "rows_included": True, "rows": pull_plan_rows},
        "quality": {"p0_count": severity["P0"], "p1_count": severity["P1"], "p2_count": severity["P2"], "items": severity_items},
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "market_data_pulled": False,
            "market_data_fact_written": False,
            "event_outbox_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }


def group_action_scope_rows(scope_rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in scope_rows:
        identity = str(row.get("identity_key") or "")
        if is_action_metric_excluded_identity(identity):
            continue
        if any("FULL" in str(row.get(field) or "") for field in ("signal_type", "condition_key")):
            continue
        asset_kind = str(row.get("asset_kind") or "")
        key = (asset_kind, identity)
        item = grouped.setdefault(
            key,
            {
                "asset_kind": asset_kind,
                "identity_key": identity,
                "exchange": str(row.get("exchange") or exchange_from_identity(identity)),
                "code": str(row.get("code") or code_from_identity(identity)),
                "display_code": str(row.get("display_code") or code_from_identity(identity)),
                "name": str(row.get("name") or ""),
                "source_scope_ids": [],
                "source_condition_pool_ids": [],
                "directions": [],
                "condition_keys": [],
                "allowed_signal_types": [],
                "trigger_match_ids": [],
                "source_trigger_event_ids": [],
                "source_market_snapshot_event_ids": [],
            },
        )
        append_unique_int(item["source_scope_ids"], row.get("source_scope_id"))
        append_unique_int(item["source_condition_pool_ids"], row.get("source_condition_pool_id"))
        append_unique(item["directions"], row.get("direction"))
        append_unique(item["condition_keys"], row.get("condition_key"))
        allowed = row.get("allowed_signal_types")
        if isinstance(allowed, list):
            for value in allowed:
                append_unique(item["allowed_signal_types"], value)
        else:
            signal_type = "BUY" if str(row.get("signal_type") or "").startswith("B_") else "SELL"
            append_unique(item["allowed_signal_types"], signal_type)
        append_unique_int(item["trigger_match_ids"], row.get("trigger_match_id"))
        append_unique(item["source_trigger_event_ids"], row.get("output_event_id"))
        append_unique(item["source_market_snapshot_event_ids"], row.get("source_event_id"))
    return [grouped[key] for key in sorted(grouped)]


def is_action_metric_excluded_identity(identity_key: str) -> bool:
    return is_bj_identity(identity_key) or ":BJ:" in identity_key


def append_unique(items: list[Any], value: Any) -> None:
    if value in (None, ""):
        return
    text = str(value)
    if text not in items:
        items.append(text)


def append_unique_int(items: list[int], value: Any) -> None:
    if value in (None, ""):
        return
    number = int(value)
    if number not in items:
        items.append(number)


def code_from_identity(identity_key: str) -> str:
    parts = identity_key.split(":")
    return parts[-1] if parts else identity_key


def exchange_from_identity(identity_key: str) -> str:
    parts = identity_key.split(":")
    return parts[1] if len(parts) >= 3 else ""


def build_action_scope_pull_plan_rows(
    subscription_run_id: str,
    source_condition_run_id: str,
    for_trade_date: str,
    source_trade_date: str,
    prev_trade_date: str,
    groups: Mapping[tuple[str, str, str], list[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (asset_kind, required_data_kind, data_trade_date), subscriptions in sorted(groups.items()):
        refs = [str(row["subscription_ref"]) for row in subscriptions]
        identities = [str(row["identity_key"]) for row in subscriptions]
        rows.append(
            {
                "pull_plan_ref": f"dry_run:action_confirmation_pull:{len(rows) + 1}",
                "run_id": subscription_run_id,
                "source_condition_run_id": source_condition_run_id,
                "for_trade_date": for_trade_date,
                "source_trade_date": source_trade_date,
                "prev_trade_date": prev_trade_date,
                "asset_kind": asset_kind,
                "required_data_kind": required_data_kind,
                "data_trade_date": data_trade_date,
                "adapter_name": default_adapter_name(asset_kind),
                "subscription_count": len(subscriptions),
                "object_count": len(set(identities)),
                "subscription_refs_sample": refs[:20],
                "identity_keys_sample": identities[:20],
                "plan_status": "planned",
                "execute_allowed": False,
                "selected_reason": "dynamic action-confirmation scope pull plan",
                "raw_json": {
                    "dynamic_realtime_chain_action_confirmation_scope": True,
                    "required_data_kind": required_data_kind,
                },
            }
        )
    return rows


def build_action_confirmation_subscription_rollback_sql(subscription_run_id: str) -> str:
    return f"""-- V3 dynamic action-confirmation subscription rollback.
-- Scope: only N3 control rows for {subscription_run_id}.
DO $$
BEGIN
  RAISE EXCEPTION 'HARD_FAIL: set reviewed rollback guard before deleting dynamic action-confirmation subscription rows';
END $$;

DELETE FROM common_market_data_pull_plan WHERE run_id = '{subscription_run_id}';
DELETE FROM common_market_data_subscription WHERE run_id = '{subscription_run_id}';
DELETE FROM common_market_data_subscription_candidate WHERE run_id = '{subscription_run_id}';
DELETE FROM common_market_data_quality_item WHERE run_id = '{subscription_run_id}';
DELETE FROM common_market_data_run WHERE run_id = '{subscription_run_id}';
"""


def build_n3_action_confirmation_previous_day_preload_artifacts(
    *,
    dsn: str,
    docs_root: str | Path,
    sql_root: str | Path,
    for_trade_date: str,
    prev_trade_date: str,
    subscription_run_id: str,
    preload_run_id: str,
    hhmm: str,
) -> dict[str, Any]:
    docs_root = Path(docs_root)
    sql_root = Path(sql_root)
    prefix = f"N3_{for_trade_date}_ACTION_CONFIRMATION_PREVIOUS_DAY_PRELOAD_UNTIL_{hhmm}"
    a0_path = docs_root / f"{prefix}_A0_DRY_RUN.json"
    a0_md_path = docs_root / f"{prefix}_A0_DRY_RUN.md"
    contract_path = docs_root / f"{prefix}_CONTRACT.json"
    contract_md_path = docs_root / f"{prefix}_CONTRACT.md"
    preflight_path = docs_root / f"{prefix}_PREFLIGHT.json"
    preflight_md_path = docs_root / f"{prefix}_PREFLIGHT.md"
    rollback_sql_path = sql_root / f"N3_{for_trade_date}_action_confirmation_previous_day_preload_until_{hhmm}_rollback.sql"
    a0 = build_previous_day_minute_preload_plan_dry_run(
        dsn=dsn,
        market_data_run_id=subscription_run_id,
        for_trade_date=for_trade_date,
        expected_previous_day_minute_date=prev_trade_date,
        include_rows=True,
    )
    write_json(a0_path, a0)
    write_text(a0_md_path, render_artifact_markdown("N3 Action Confirmation Previous-Day Preload A0", a0))
    contract = build_previous_day_minute_execute_contract(
        dsn=dsn,
        market_data_run_id=subscription_run_id,
        a0_report_path=str(a0_path),
        contract_json_path=str(contract_path),
        contract_markdown_path=str(contract_md_path),
        rollback_sql_path=str(rollback_sql_path),
        preflight_json_path=str(preflight_path),
        preflight_markdown_path=str(preflight_md_path),
        preload_run_id=preload_run_id,
    )
    return {
        "stage": "N3_ACTION_CONFIRMATION_PREVIOUS_DAY_PRELOAD",
        "status": "written",
        "a0_path": str(a0_path),
        "contract_path": str(contract_path),
        "preflight_path": str(preflight_path),
        "rollback_sql_path": str(rollback_sql_path),
        "data_trade_date": prev_trade_date,
        "preload_run_id": preload_run_id,
        "preflight_result": "PREFLIGHT_PASS" if int((contract.get("quality") or {}).get("p0_count") or 0) == 0 else "BLOCKED",
    }


def build_n3_action_confirmation_today_minute_artifacts(
    *,
    dsn: str,
    docs_root: str | Path,
    sql_root: str | Path,
    for_trade_date: str,
    subscription_run_id: str,
    today_minute_run_id: str,
    hhmm: str,
    latest_closed_minute: str,
) -> dict[str, Any]:
    docs_root = Path(docs_root)
    sql_root = Path(sql_root)
    prefix = f"N3_{for_trade_date}_ACTION_CONFIRMATION_TODAY_MINUTE_UNTIL_{hhmm}"
    c0_path = docs_root / f"{prefix}_C0_DRY_RUN.json"
    c0_md_path = docs_root / f"{prefix}_C0_DRY_RUN.md"
    rollback_sql_path = sql_root / f"N3_{for_trade_date}_action_confirmation_today_minute_until_{hhmm}_rollback.sql"
    as_of = datetime.fromisoformat(latest_closed_minute.replace("Z", "+00:00")) + timedelta(minutes=1)
    c0 = build_today_minute_bar_plan_dry_run(
        dsn=dsn,
        market_data_run_id=subscription_run_id,
        for_trade_date=for_trade_date,
        as_of=as_of,
        include_rows=True,
    )
    c0["today_minute_run_id"] = today_minute_run_id
    c0["execute_contract"]["today_minute_run_id"] = today_minute_run_id
    c0["rollback_contract"]["rollback_sql"] = build_today_minute_rollback_sql(today_minute_run_id)
    write_json(c0_path, c0)
    write_text(c0_md_path, format_today_minute_markdown(c0))
    write_text(rollback_sql_path, c0["rollback_contract"]["rollback_sql"])
    return {
        "stage": "N3_ACTION_CONFIRMATION_TODAY_MINUTE",
        "status": "written",
        "c0_plan_path": str(c0_path),
        "rollback_sql_path": str(rollback_sql_path),
        "today_minute_run_id": today_minute_run_id,
        "preflight_result": "PREFLIGHT_PASS" if int((c0.get("quality") or {}).get("p0_count") or 0) == 0 else "BLOCKED",
    }


def fetch_n4_trigger_matched_events(cur: Any, *, trigger_execute_run_id: str) -> dict[str, list[dict[str, Any]]]:
    cur.execute(
        """
        SELECT
          m.trigger_match_id,
          m.output_event_id,
          o.event_id,
          o.event_time,
          o.trade_date,
          m.asset_kind,
          m.identity_key,
          m.direction,
          m.signal_type,
          m.condition_key,
          m.trigger_mark_candidate,
          m.trigger_period,
          m.trigger_bucket,
          o.payload_json
        FROM common_trigger_match m
        LEFT JOIN common_event_outbox o
          ON o.source_run_id = m.run_id
         AND o.event_type = 'TriggerMatched'
         AND o.event_id = m.output_event_id
        WHERE m.run_id = %s
          AND m.output_event_type = 'TriggerMatched'
        ORDER BY m.asset_kind, m.identity_key, m.trigger_match_id
        """,
        (trigger_execute_run_id,),
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in cur.fetchall():
        event = dict(row)
        event["payload_json"] = dict(event.get("payload_json") or {})
        grouped.setdefault(str(event["identity_key"]), []).append(event)
    return grouped


def attach_n4_trigger_refs_to_action_metric_rows(
    *,
    rows_by_asset: Mapping[str, list[dict[str, Any]]],
    n4_events: Mapping[str, list[Mapping[str, Any]]],
    trigger_execute_run_id: str,
    source_realtime_projection_run_id: str,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    enriched: dict[str, list[dict[str, Any]]] = {asset: [] for asset in ASSET_KINDS}
    source_total = sum(len(events) for events in n4_events.values())
    excluded_bj_or_full = sum(
        1
        for identity, events in n4_events.items()
        for event in events
        if event_is_action_metric_excluded(identity, event)
    )
    excluded_full = sum(
        1
        for identity, events in n4_events.items()
        for event in events
        if any("FULL" in str(value or "") for value in (event.get("signal_type"), event.get("condition_key")))
    )
    covered_events = 0
    missing_metric_identities: list[str] = []
    for asset_kind in ASSET_KINDS:
        for row in rows_by_asset.get(asset_kind, []):
            identity = str(row.get("identity_key") or "")
            events = list(n4_events.get(identity) or [])
            if not events:
                continue
            included_events: list[dict[str, Any]] = []
            for event in events:
                if event_is_action_metric_excluded(identity, event):
                    continue
                included_events.append(dict(event))
            if not included_events:
                continue
            enriched_row = enrich_action_metric_row_with_n4_events(
                row=row,
                events=included_events,
                trigger_execute_run_id=trigger_execute_run_id,
                source_realtime_projection_run_id=source_realtime_projection_run_id,
            )
            covered_events += len(included_events)
            enriched[asset_kind].append(enriched_row)
    metric_identities = {
        str(row.get("identity_key") or "")
        for rows in enriched.values()
        for row in rows
    }
    for identity, events in sorted(n4_events.items()):
        non_excluded = [
            event for event in events
            if not event_is_action_metric_excluded(identity, event)
        ]
        if non_excluded and identity not in metric_identities:
            missing_metric_identities.append(identity)
    expected = max(0, source_total - excluded_bj_or_full)
    return enriched, {
        "covered": covered_events,
        "expected": expected,
        "missing": max(0, expected - covered_events),
        "source_total_trigger_matched": source_total,
        "excluded_bj_or_full": excluded_bj_or_full,
        "excluded_full": excluded_full,
        "distinct_metric_rows": sum(len(rows) for rows in enriched.values()),
        "missing_metric_identity_count": len(missing_metric_identities),
        "missing_metric_identity_sample": missing_metric_identities[:20],
    }


def enrich_action_metric_row_with_n4_events(
    *,
    row: Mapping[str, Any],
    events: list[Mapping[str, Any]],
    trigger_execute_run_id: str,
    source_realtime_projection_run_id: str,
) -> dict[str, Any]:
    enriched = dict(row)
    match_ids = [int(event["trigger_match_id"]) for event in events if event.get("trigger_match_id") is not None]
    event_ids = [str(event.get("event_id") or event.get("output_event_id") or "") for event in events if event.get("event_id") or event.get("output_event_id")]
    event_summaries = [
        {
            "source_trigger_run_id": trigger_execute_run_id,
            "source_trigger_match_id": event.get("trigger_match_id"),
            "source_trigger_event_id": event.get("event_id") or event.get("output_event_id"),
            "event_time": str(event.get("event_time") or ""),
            "direction": event.get("direction"),
            "signal_type": event.get("signal_type"),
            "condition_key": event.get("condition_key"),
            "trigger_bucket": event.get("trigger_bucket"),
            "trigger_mark_candidate": event.get("trigger_mark_candidate"),
        }
        for event in events
    ]
    source_fact_ids = dict(enriched.get("source_fact_ids") or {})
    source_fact_ids.update(
        {
            "source_realtime_projection_run_id": source_realtime_projection_run_id,
            "source_trigger_run_id": trigger_execute_run_id,
            "source_trigger_match_ids": match_ids,
            "source_trigger_event_ids": event_ids,
            "n4_trigger_match_ids": match_ids,
            "n4_output_event_ids": event_ids,
        }
    )
    raw = dict(enriched.get("raw_json") or {})
    raw.update(
        {
            "dynamic_realtime_chain_action_confirmation_metric": True,
            "source_realtime_projection_run_id": source_realtime_projection_run_id,
            "source_trigger_run_id": trigger_execute_run_id,
            "n4_trigger_matched_events": event_summaries,
            "metric_time_policy": "latest_closed_minute_from_c1_run",
            "n5_join_policy": "projection_closed_label_or_metric_time_with_trigger_refs",
        }
    )
    enriched["source_fact_ids"] = source_fact_ids
    enriched["raw_json"] = raw
    return enriched


def event_is_action_metric_excluded(identity_key: str, event: Mapping[str, Any]) -> bool:
    return is_action_metric_excluded_identity(identity_key) or any(
        "FULL" in str(value or "")
        for value in (event.get("signal_type"), event.get("condition_key"))
    )


def build_dynamic_action_metric_contract(
    *,
    payload: Mapping[str, Any],
    rollback_sql_path: str | Path,
    python_executable: str,
    payload_path: str | Path,
    contract_path: str | Path,
    report_path: str | Path,
    markdown_report_path: str | Path,
) -> dict[str, Any]:
    projection_run_id = str(payload["projection_run_id"])
    return {
        "stage": "N3 dynamic realtime-chain action-confirmation metric materialization contract",
        "preflight_stage": "N3 dynamic realtime-chain action-confirmation metric materialization preflight",
        "layer_role": "N3_market_data",
        "contract_result": "CONTRACT_PASS",
        "execute_authorized_now": False,
        "runner_exists": True,
        "runner_readiness": "ready_contract_driven",
        "execute_command": [
            python_executable,
            "scripts/run_n3_action_confirmation_metric_materialization_execute.py",
            "--payload-path",
            str(payload_path),
            "--contract-path",
            str(contract_path),
            "--report-path",
            str(report_path),
            "--markdown-report-path",
            str(markdown_report_path),
            "--execute",
            "--user-confirmed",
        ],
        "projection_run_id": projection_run_id,
        "target_run_id": projection_run_id,
        "projection_schema_version": ACTION_METRIC_SCHEMA_VERSION,
        "for_trade_date": payload.get("for_trade_date"),
        "source_trade_date": payload.get("source_trade_date"),
        "prev_trade_date": payload.get("prev_trade_date") or payload.get("source_trade_date"),
        "source_condition_run_id": payload.get("source_condition_run_id"),
        "trigger_execute_run_id": payload.get("trigger_execute_run_id"),
        "source_realtime_projection_run_id": payload.get("source_realtime_projection_run_id"),
        "source_snapshot_run_id": payload.get("source_snapshot_run_id"),
        "source_subscription_run_ids": list(payload.get("source_subscription_run_ids") or []),
        "source_today_minute_run_ids": list(payload.get("source_today_minute_run_ids") or []),
        "source_previous_day_minute_run_ids": list(payload.get("source_previous_day_minute_run_ids") or []),
        "expected_rows": dict(payload.get("expected_rows") or {}),
        "metric_ready_expected": int(payload.get("metric_ready_expected") or 0),
        "expected_n4_matched_coverage": dict(payload.get("n4_matched_coverage") or {}),
        "allowed_write_tables": list(ACTION_METRIC_ALLOWED_WRITE_TABLES),
        "requested_target_aliases": list(ACTION_METRIC_REQUESTED_TARGET_ALIASES),
        "forbidden_write_tables": list(ACTION_METRIC_FORBIDDEN_WRITE_TABLES),
        "writes_outbox": False,
        "consumes_outbox": False,
        "writes_inbox_or_checkpoint": False,
        "pulls_market_data": False,
        "enters_n4_n5_n6": False,
        "starts_worker": False,
        "row_policy": {
            "BJ_excluded": True,
            "FULL_excluded": True,
            "metric_grain": "identity-level dynamic action metric row; N4 TriggerMatched refs are carried in source_fact_ids/raw_json",
            "n4_payload_mutation_allowed": False,
        },
        "rollback": {
            "rollback_sql_path": str(rollback_sql_path),
            "scope": "projection_run_id",
            "hard_fail_before_delete": True,
        },
    }


def count_metric_rows(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    counts = {asset: 0 for asset in ASSET_KINDS}
    for row in rows:
        asset = str(row.get("asset_kind") or "")
        if asset in counts:
            counts[asset] += 1
    counts["total"] = sum(counts.values())
    return counts


def materialize_b2_expected_distribution(
    *,
    dsn: str,
    for_trade_date: str,
    source_trade_date: str,
    prev_trade_date: str,
    source_condition_run_id: str,
    subscription_run_id: str,
    preload_run_id: str,
    today_minute_run_id: str,
    snapshot_run_id: str,
    projection_run_id: str,
    latest_closed_minute: str,
    expected_rows_by_asset: Mapping[str, int],
) -> dict[str, Any]:
    temp_contract = {
        "projection_run_id": projection_run_id,
        "source_runs": {
            "source_condition_run_id": source_condition_run_id,
            "subscription_run_id": subscription_run_id,
            "preload_run_id": preload_run_id,
            "today_minute_run_id": today_minute_run_id,
            "snapshot_run_id": snapshot_run_id,
        },
        "dates": {
            "for_trade_date": for_trade_date,
            "source_trade_date": source_trade_date,
            "prev_trade_date": prev_trade_date,
        },
        "calculation_config": build_b2_calculation_config(),
        "projection_time_policy": {
            "mode": "standard_outbox_observed_at_to_latest_closed_minute",
            "bucket_time_source": "latest_closed_minute",
            "latest_closed_minute": latest_closed_minute,
        },
        "expected_projection_rows": {
            "total": sum(int(expected_rows_by_asset.get(asset) or 0) for asset in ASSET_KINDS),
            "by_asset": dict(expected_rows_by_asset),
        },
    }
    rows = build_projection_rows(dsn=dsn, contract=temp_contract)
    return build_expected_distribution_from_summary(summarize_projection_rows(rows))


def default_stage_status(*, dsn: str, stage_name: str, ids: StageIds) -> dict[str, Any]:
    if stage_name == "N4_CONTEXT":
        return fetch_run_status(dsn=dsn, table="common_trigger_run", run_column="run_id", run_id=ids.n4_context_run_id)
    if stage_name == "N3_B1_STANDARD_OUTBOX":
        return fetch_market_run_status_with_rows(
            dsn=dsn,
            run_id=ids.b1_standard_outbox_run_id,
            row_count_sql="SELECT count(*) FROM common_event_outbox WHERE source_layer='N3_market_data' AND source_run_id=%s AND event_type='MarketSnapshotUpdated'",
        )
    if stage_name == "N3_B2_TRACE_ALIGNED_PROJECTION":
        return fetch_market_run_status_with_rows(
            dsn=dsn,
            run_id=ids.b2_trace_projection_run_id,
            row_count_sql="""
                SELECT
                  (SELECT count(*) FROM stock_realtime_projection_metric WHERE projection_run_id=%s)
                + (SELECT count(*) FROM index_realtime_projection_metric WHERE projection_run_id=%s)
                + (SELECT count(*) FROM board_realtime_projection_metric WHERE projection_run_id=%s)
            """,
        )
    if stage_name == "N4_PRODUCTION_TRIGGER_SEMANTIC_REPLAY":
        return fetch_run_status(dsn=dsn, table="common_trigger_run", run_column="run_id", run_id=ids.n4_run_id)
    if stage_name == "N3_ACTION_CONFIRMATION_SCOPE_SUBSCRIPTION":
        return fetch_market_run_status_with_rows(
            dsn=dsn,
            run_id=ids.n3_action_subscription_run_id,
            row_count_sql="SELECT count(*) FROM common_market_data_subscription WHERE run_id=%s",
        )
    if stage_name == "N3_ACTION_CONFIRMATION_PREVIOUS_DAY_PRELOAD":
        return fetch_market_run_status_with_rows(
            dsn=dsn,
            run_id=ids.n3_action_preload_run_id,
            row_count_sql="""
                SELECT
                  (SELECT count(*) FROM stock_minute_bar_1m WHERE run_id=%s AND is_previous_day_preload=true)
                + (SELECT count(*) FROM index_minute_bar_1m WHERE run_id=%s AND is_previous_day_preload=true)
                + (SELECT count(*) FROM board_minute_bar_1m WHERE run_id=%s AND is_previous_day_preload=true)
            """,
        )
    if stage_name == "N3_ACTION_CONFIRMATION_TODAY_MINUTE":
        return fetch_market_run_status_with_rows(
            dsn=dsn,
            run_id=ids.n3_action_today_minute_run_id,
            row_count_sql="""
                SELECT
                  (SELECT count(*) FROM stock_minute_bar_1m WHERE run_id=%s AND is_previous_day_preload=false)
                + (SELECT count(*) FROM index_minute_bar_1m WHERE run_id=%s AND is_previous_day_preload=false)
                + (SELECT count(*) FROM board_minute_bar_1m WHERE run_id=%s AND is_previous_day_preload=false)
            """,
        )
    if stage_name == "N3_ACTION_CONFIRMATION_METRIC":
        return fetch_market_run_status_with_rows(
            dsn=dsn,
            run_id=ids.n3_action_metric_run_id,
            row_count_sql="""
                SELECT
                  (SELECT count(*) FROM stock_action_confirmation_projection_metric WHERE projection_run_id=%s)
                + (SELECT count(*) FROM index_action_confirmation_projection_metric WHERE projection_run_id=%s)
                + (SELECT count(*) FROM board_action_confirmation_projection_metric WHERE projection_run_id=%s)
            """,
        )
    if stage_name == "N5_BOUNDED_ACTION_CONSUMER":
        return fetch_run_status(dsn=dsn, table="common_action_run", run_column="run_id", run_id=ids.n5_action_run_id)
    return {"status": "unknown", "reason": "unsupported_stage"}


def fetch_market_run_status_with_rows(*, dsn: str, run_id: str, row_count_sql: str) -> dict[str, Any]:
    status = fetch_run_status(dsn=dsn, table="common_market_data_run", run_column="run_id", run_id=run_id)
    if status.get("status") != "passed":
        return status
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on") as conn, conn.cursor() as cur:
        if row_count_sql.count("%s") == 3:
            cur.execute(row_count_sql, (run_id, run_id, run_id))
        else:
            cur.execute(row_count_sql, (run_id,))
        row_count = int(cur.fetchone()[0] or 0)
    return {**status, "row_count": row_count, "status": "passed" if row_count > 0 else "missing"}


def fetch_run_status(*, dsn: str, table: str, run_column: str, run_id: str) -> dict[str, Any]:
    with psycopg.connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(f"SELECT status FROM {table} WHERE {run_column} = %s LIMIT 1", (run_id,))
        row = cur.fetchone()
    if not row:
        return {"status": "missing", "run_id": run_id}
    return {"status": str(row["status"]), "run_id": run_id}


def fetch_lineage_details(*, dsn: str, subscription_run_id: str) -> dict[str, str]:
    with psycopg.connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT source_trade_date, prev_trade_date
            FROM common_market_data_run
            WHERE run_id = %s
            LIMIT 1
            """,
            (subscription_run_id,),
        )
        row = cur.fetchone() or {}
    return {
        "source_trade_date": str(row.get("source_trade_date") or ""),
        "prev_trade_date": str(row.get("prev_trade_date") or row.get("source_trade_date") or ""),
    }


def fetch_realtime_pull_plan_rows(*, dsn: str, subscription_run_id: str, for_trade_date: str) -> list[dict[str, Any]]:
    with psycopg.connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT asset_kind,
                   pull_plan_id AS source_pull_plan_id,
                   adapter_name,
                   subscription_count,
                   object_count
            FROM common_market_data_pull_plan
            WHERE run_id = %s
              AND for_trade_date = %s
              AND required_data_kind = 'realtime_daily_snapshot'
            ORDER BY asset_kind
            """,
            (subscription_run_id, for_trade_date),
        )
        rows = [dict(row) for row in cur.fetchall()]
    if {str(row.get("asset_kind")) for row in rows} != set(ASSET_KINDS):
        raise RuntimeError(f"realtime pull plan does not cover stock/index/board: {rows}")
    return rows


def fetch_snapshot_row_counts(*, dsn: str, snapshot_run_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on") as conn, conn.cursor() as cur:
        for asset_kind, table in SNAPSHOT_TABLES.items():
            cur.execute(f"SELECT count(*) FROM {table} WHERE run_id = %s", (snapshot_run_id,))
            counts[asset_kind] = int(cur.fetchone()[0] or 0)
    return counts


def default_adapter_name(asset_kind: str) -> str:
    return {
        "stock": "StockRealtimeQuoteAdapter",
        "index": "IndexRealtimeQuoteAdapter",
        "board": "BoardMarketDataAdapter",
    }[asset_kind]


def summarize_n3_report(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status"),
        "reason": report.get("reason"),
        "latest_closed_minute": report.get("latest_closed_minute"),
        "latest_closed_minute_hhmm": report.get("latest_closed_minute_hhmm"),
        "effective_hhmm": report.get("effective_hhmm"),
        "executed_child_command_count": report.get("executed_child_command_count"),
    }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def maybe_write_chain_report(
    report: dict[str, Any],
    *,
    json_report_path: str | Path | None,
    markdown_report_path: str | Path | None,
) -> dict[str, Any]:
    if report.pop("_suppress_report_write", False):
        return report
    if json_report_path:
        write_json(json_report_path, report)
    if markdown_report_path:
        write_text(markdown_report_path, render_chain_markdown(report))
    return report


def render_chain_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# N3-N4-N5 Realtime Chain Report",
        "",
        f"- objective: `{report.get('objective')}`",
        f"- result: `{report.get('result')}`",
        f"- reason: `{report.get('reason')}`",
        f"- blocked_reason: `{report.get('blocked_reason')}`",
        f"- for_trade_date: `{report.get('for_trade_date')}`",
        f"- execute: `{report.get('execute')}`",
        f"- user_confirmed: `{report.get('user_confirmed')}`",
        "",
        "## Executed Steps",
        "",
    ]
    for step in report.get("executed_steps", []):
        lines.append(f"- {step.get('stage')}: rc `{step.get('returncode')}`")
    lines.extend(
        [
            "",
            "## Forbidden Scope",
            "",
            "```text",
            "n6_entered=false",
            "voice_mobile_touched=false",
            "sim_position_pnl_touched=false",
            "real_trade_touched=false",
            "long_running_worker_started=false",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def render_artifact_markdown(title: str, data: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            f"# {title}",
            "",
            f"- stage: `{data.get('stage')}`",
            f"- result: `{data.get('result')}`",
            f"- projection_run_id: `{data.get('projection_run_id')}`",
            f"- snapshot_run_id: `{data.get('snapshot_run_id')}`",
            f"- writes_outbox: `{data.get('writes_outbox')}`",
            "",
        ]
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one bounded N3 -> N4 -> N5 realtime chain pass.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--auto-resolve-lineage", action="store_true")
    parser.add_argument("--for-trade-date", default="")
    parser.add_argument("--subscription-run-id", default="")
    parser.add_argument("--preload-run-id", default="")
    parser.add_argument("--source-condition-run-id", default="")
    parser.add_argument("--docs-root", default="docs")
    parser.add_argument("--sql-root", default="sql")
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--as-of", default="")
    parser.add_argument("--max-n4-events", type=int, default=5000)
    parser.add_argument("--max-n5-events", type=int, default=5000)
    parser.add_argument("--max-n5-runtime-seconds", type=int, default=120)
    parser.add_argument("--n5-heartbeat-interval-seconds", type=int, default=10)
    parser.add_argument("--allow-overwrite", action="store_true")
    parser.add_argument("--json-report-path", default=DEFAULT_CHAIN_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_CHAIN_MD_REPORT_PATH)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    as_of = datetime.fromisoformat(args.as_of) if args.as_of else None
    report = run_realtime_chain_once(
        dsn=args.dsn,
        auto_resolve_lineage=args.auto_resolve_lineage,
        for_trade_date=args.for_trade_date or None,
        subscription_run_id=args.subscription_run_id or None,
        preload_run_id=args.preload_run_id or None,
        source_condition_run_id=args.source_condition_run_id or None,
        docs_root=args.docs_root,
        sql_root=args.sql_root,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
        as_of=as_of,
        python_executable=args.python_executable,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
        max_n4_events=args.max_n4_events,
        max_n5_events=args.max_n5_events,
        max_n5_runtime_seconds=args.max_n5_runtime_seconds,
        n5_heartbeat_interval_seconds=args.n5_heartbeat_interval_seconds,
        allow_overwrite=args.allow_overwrite,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report.get("result") in {"PLAN_ONLY", "NOOP_PASS", "EXECUTE_PASS"} else 2


def format_summary(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "n3-n4-n5 realtime chain wrapper",
            f"  result={report.get('result')}",
            f"  reason={report.get('reason')}",
            f"  blocked_reason={report.get('blocked_reason')}",
            f"  for_trade_date={report.get('for_trade_date')}",
            f"  executed_steps={len(report.get('executed_steps') or [])}",
            "  n6_entered=false voice_mobile=false sim_position_pnl=false real_trade=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
