#!/usr/bin/env python3
"""Run one N5 live-tracking bounded poller invocation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.action.execute import coerce_metric_run_ids
from ashare_v3.action.dry_run import build_action_tracking_state_key
from ashare_v3.action.live_tracking_poller import (
    build_active_set_a_rebuild_from_n4_day_events,
    build_live_tracking_plan,
)
from ashare_v3.market.minute_label_normalization import canonical_ashare_1m_labels
from ashare_v3.runtime.bounded_worker_control import atomic_write_json
from ashare_v3.runtime_control.n5_n3t_fastlane import (
    FASTLANE_LANE_ID,
    POST_CLOSE_FINAL_A_PASS_DONE_ARTIFACT_TYPE,
    build_fastlane_source_run_namespace,
    classify_fastlane_session_phase,
    default_post_close_final_a_pass_done_marker_path,
    load_fastlane_activation_config,
    resolve_fastlane_runtime_session_context,
    resolve_fastlane_active_worker_decision,
    validate_fastlane_write_enabled_activation_authorization,
)


DEFAULT_DSN = os.environ.get("ASHARE_V3_POSTGRES_DSN", "")
DEFAULT_EVENT_LIMIT = 1000
DEFAULT_FASTLANE_MAX_RUNTIME_SECONDS = 10.0
DEFAULT_FASTLANE_CONSUMER_NAME = "n5_live_tracking_poller_v2_fastlane"
TRACKING_WRITE_DEADLOCK_RETRY_LIMIT = 3
TRACKING_WRITE_DEADLOCK_RETRY_DELAYS_SECONDS = (0.05, 0.15)
# Keep the executed poller bounded, but large enough to reach exact-ready refs
# behind a backlog of active refs that do not yet have N3T proof.
FASTLANE_EXECUTED_DISCOVERY_CANDIDATE_LIMIT = 256
FASTLANE_EXECUTED_CONTINUOUS_METRIC_RUN_LIMIT = 64
FASTLANE_EXECUTED_BATCH_STATE_KEY = "__fastlane_executed_batch__"
N5_OUTPUT_EVENT_TYPES = ("ActionEligible", "ActionExecuted")
N4_INPUT_EVENT_TYPES = ("TriggerMatched", "TriggerStateChanged")
N5_LIVE_TRACKING_SCHEMA_VERSION = "v2"
N5_LIVE_TRACKING_TRIGGER_TYPE = "N5_live_tracking_v2"
SCHEMA_ALLOWED_TRACKING_TRIGGER_TYPES = ("BUY", "BUY:FULL", "SELL", "SELL:FULL", "BUY_HINT", "SELL_HINT")
TRACKING_MONITOR_WINDOW_ID_PREFIX = "N5_live_tracking_monitor_window_v1"
FASTLANE_ACTION_RUN_ID_REGEX = r"^n5_live_tracking_.*__fastlane_v1$"
ACTIVE_SET_A_INTAKE_EVENT_KINDS = {
    "active_set_a",
    "post_close_final_a_scope_snapshot",
}
STALE_METRIC_STATUS_REEVALUATION_REASONS = {
    "missing_previous_session_reference",
}
N3T_ACTION_CONFIRMATION_METRIC_TABLES_BY_ASSET_KIND = {
    "stock": "stock_n3t_action_confirmation_metric",
    "index": "index_n3t_action_confirmation_metric",
    "board": "board_n3t_action_confirmation_metric",
}


class N5LiveTrackingBlocked(RuntimeError):
    """Raised when the bounded poller is blocked before mutation."""


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _jsonb(value: Any) -> Jsonb:
    return Jsonb(_json_safe_value(value))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one N5 live-tracking bounded poller invocation.")
    parser.add_argument("--for-trade-date", default="")
    parser.add_argument("--source-trigger-run-id", default="")
    parser.add_argument("--source-metric-run-id", default="")
    parser.add_argument("--fastlane-ref-state-key", default="")
    parser.add_argument("--fastlane-target-minute-label", default="")
    parser.add_argument("--fastlane-executed-batch-candidates-json", default="")
    parser.add_argument("--action-run-id", default="")
    parser.add_argument("--consumer-name", default="")
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument("--max-runtime-seconds", type=float, default=0.0)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--activation-config", default="")
    parser.add_argument("--fastlane-lane-id", default="")
    parser.add_argument("--fastlane-phase", choices=("intake", "executed", ""), default="")
    parser.add_argument("--n5-intake-event-kind", default="")
    parser.add_argument("--active-scope-artifact-path", default="")
    parser.add_argument("--output-artifact-path", default="")
    parser.add_argument("--current-exchange-time", default="")
    parser.add_argument("--post-close-final-a-rebuild-from-n4-day-events", action="store_true")
    parser.add_argument("--post-close-final-a-pass-done-marker-path", default="")
    parser.add_argument("--write-active-scope-artifact", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--scheduler-quiet", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def run_n5_live_tracking_poller_once(
    argv: Sequence[str] | None = None,
    *,
    activation_discovery_provider: Callable[[argparse.Namespace, Mapping[str, Any]], Mapping[str, Any]] | None = None,
    plan_provider: Callable[[argparse.Namespace], Mapping[str, Any]] | None = None,
    writer: Callable[[argparse.Namespace, Mapping[str, Any]], Mapping[str, Any]] | None = None,
    now_monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    invocation_id = f"n5_live_tracking_invocation_{uuid.uuid4().hex}"
    started = now_monotonic()
    try:
        if bool(getattr(args, "post_close_final_a_rebuild_from_n4_day_events", False)):
            return _run_post_close_final_a_rebuild_from_n4_day_events(args, invocation_id, started, now_monotonic)
        _apply_activation_config(args, activation_discovery_provider=activation_discovery_provider)
        _validate_args(args)
        if args.execute and not args.user_confirmed:
            raise N5LiveTrackingBlocked("execute_requires_user_confirmed")
        if args.write_active_scope_artifact and not args.user_confirmed:
            raise N5LiveTrackingBlocked("write_active_scope_artifact_requires_user_confirmed")
        provider = plan_provider or _default_plan_provider
        plan = dict(provider(args))
        _validate_plan_boundary(plan)
        _validate_fastlane_phase_plan_boundary(args, plan)
        manifest = _build_manifest(args, invocation_id, plan, started, now_monotonic)
        if not args.execute:
            manifest["verdict"] = "N5_LIVE_TRACKING_PLAN_ONLY"
            manifest["write_result"] = {"executed": False}
            manifest["active_scope_artifact_write_result"] = _write_active_scope_artifact(args, plan)
            manifest["post_close_final_a_pass_done_marker_write_result"] = (
                _maybe_write_post_close_final_a_pass_done_marker(args, plan, manifest)
            )
            return manifest
        write_result = dict((writer or _default_execute_writer)(args, plan))
        manifest["verdict"] = _execute_verdict(args, plan)
        manifest["write_result"] = write_result
        manifest["active_scope_artifact_write_result"] = _write_active_scope_artifact(args, plan)
        manifest["post_close_final_a_pass_done_marker_write_result"] = (
            _maybe_write_post_close_final_a_pass_done_marker(args, plan, manifest)
        )
        return manifest
    except N5LiveTrackingBlocked as exc:
        reason = str(exc)
        if _is_fastlane_readiness_waiting_reason(reason):
            return {
                "verdict": "N5_LIVE_TRACKING_READINESS_WAITING",
                "reason": reason.removeprefix("fastlane_worker_"),
                "invocation_id": invocation_id,
                "action_run_id": args.action_run_id,
                "execute_requested": bool(args.execute),
                "writes_enabled": False,
                "artifact_writes_enabled": False,
                "fastlane": {
                    "phase": getattr(args, "fastlane_phase", ""),
                    "session_phase": getattr(args, "fastlane_session_phase", ""),
                    "active_worker_decision": getattr(args, "fastlane_active_worker_decision", {}),
                },
            }
        return {
            "verdict": "BLOCKED_N5_LIVE_TRACKING_POLLER",
            "blocked_reason": reason,
            "invocation_id": invocation_id,
            "action_run_id": args.action_run_id,
            "execute_requested": bool(args.execute),
            "writes_enabled": False,
            "artifact_writes_enabled": False,
            "fastlane": {
                "phase": getattr(args, "fastlane_phase", ""),
                "session_phase": getattr(args, "fastlane_session_phase", ""),
                "active_worker_decision": getattr(args, "fastlane_active_worker_decision", {}),
            },
        }


def _run_post_close_final_a_rebuild_from_n4_day_events(
    args: argparse.Namespace,
    invocation_id: str,
    started: float,
    now_monotonic: Callable[[], float],
) -> dict[str, Any]:
    _validate_post_close_final_a_rebuild_args(args)
    action_run_id = str(args.action_run_id or _fastlane_active_set_a_action_run_id(for_trade_date=str(args.for_trade_date)))
    consumer_name = str(args.consumer_name or DEFAULT_FASTLANE_CONSUMER_NAME)
    with psycopg.connect(
        args.dsn,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
        connect_timeout=10,
    ) as conn, conn.cursor() as cur:
        n4_rows = _fetch_n4_day_event_rows_for_active_set_rebuild(cur, args)
        action_executed_rows = _fetch_n5_action_executed_rows_for_active_set_rebuild(cur, args)
    plan = build_active_set_a_rebuild_from_n4_day_events(
        n4_event_rows=n4_rows,
        action_executed_event_rows=action_executed_rows,
        for_trade_date=str(args.for_trade_date),
        action_run_id=action_run_id,
        consumer_name=consumer_name,
        current_exchange_time=str(getattr(args, "current_exchange_time", "") or ""),
    )
    write_result = _write_post_close_final_a_rebuild_artifact(args, plan)
    return {
        "verdict": "N5_ACTIVE_SET_A_REBUILD_FROM_N4_DAY_EVENTS_PASS",
        "invocation_id": invocation_id,
        "for_trade_date": str(args.for_trade_date),
        "action_run_id": action_run_id,
        "consumer_name": consumer_name,
        "execute_requested": False,
        "writes_enabled": False,
        "artifact_writes_enabled": True,
        "bounded": {
            "max_events": int(getattr(args, "max_events", 0) or 0),
            "max_runtime_seconds": float(getattr(args, "max_runtime_seconds", 0.0) or 0.0),
            "elapsed_seconds": round(now_monotonic() - started, 6),
        },
        "boundary": {
            "n4_outbox_updated": False,
            "n5_outbox_updated": False,
            "common_event_inbox_written": False,
            "common_event_consumer_checkpoint_written": False,
            "db_written": False,
            "n6_touched": False,
            "launchd_touched": False,
        },
        "write_result": write_result,
        "plan": plan,
    }


def _validate_post_close_final_a_rebuild_args(args: argparse.Namespace) -> None:
    if not str(args.for_trade_date).isdigit() or len(str(args.for_trade_date)) != 8:
        raise N5LiveTrackingBlocked("for_trade_date_must_be_yyyymmdd")
    if not str(args.dsn or "").strip():
        raise N5LiveTrackingBlocked("dsn_required_for_active_set_a_rebuild")
    if not str(getattr(args, "output_artifact_path", "") or "").strip():
        raise N5LiveTrackingBlocked("output_artifact_path_required")
    if not bool(getattr(args, "user_confirmed", False)):
        raise N5LiveTrackingBlocked("active_set_a_rebuild_local_artifact_write_requires_user_confirmed")


def _fetch_n4_day_event_rows_for_active_set_rebuild(cur: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT o.*
        FROM common_event_outbox o
        WHERE o.source_layer = 'N4_trigger'
          AND o.trade_date = %s
          AND o.event_type IN ('TriggerMatched', 'TriggerStateChanged')
        ORDER BY o.event_time, o.source_run_id, o.event_id
        """,
        (args.for_trade_date,),
    )
    return [dict(row) for row in cur.fetchall()]


def _fetch_n5_action_executed_rows_for_active_set_rebuild(cur: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT o.*
        FROM common_event_outbox o
        WHERE o.source_layer = 'N5_action'
          AND o.trade_date = %s
          AND o.event_type = 'ActionExecuted'
        ORDER BY o.event_time, o.source_run_id, o.event_id
        """,
        (args.for_trade_date,),
    )
    return [dict(row) for row in cur.fetchall()]


def _write_post_close_final_a_rebuild_artifact(args: argparse.Namespace, plan: Mapping[str, Any]) -> dict[str, Any]:
    artifact = plan.get("active_scope_snapshot_artifact")
    if not isinstance(artifact, Mapping):
        raise N5LiveTrackingBlocked("active_scope_snapshot_artifact_missing")
    path = Path(str(getattr(args, "output_artifact_path", "") or ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe_value(artifact), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "executed": True,
        "path": str(path),
        "artifact_type": artifact.get("artifact_type"),
        "scope_count": artifact.get("scope_count"),
        "active_tracking_ref_count": artifact.get("active_tracking_ref_count"),
        "n4_outbox_updated": False,
        "db_written": False,
        "n6_touched": False,
    }


def _is_fastlane_readiness_waiting_reason(reason: str) -> bool:
    return reason in {
        "fastlane_worker_waiting_for_n4_triggermatched",
        "fastlane_worker_waiting_for_n3t_c1_closed_metric",
        "fastlane_worker_waiting_for_actionexecuted_candidate",
        "fastlane_worker_post_close_final_a_pass_done",
    }


def _execute_verdict(args: argparse.Namespace, plan: Mapping[str, Any]) -> str:
    if (
        _is_fastlane_executed_phase(args)
        and _plan_action_executed_count(plan) == 0
        and _plan_tracking_update_count(plan) > 0
    ):
        return "N5_LIVE_TRACKING_EVALUATION_PASS_NO_ACTIONEXECUTED"
    return "N5_LIVE_TRACKING_EXECUTE_PASS"


def _validate_args(args: argparse.Namespace) -> None:
    if not str(args.for_trade_date).isdigit() or len(str(args.for_trade_date)) != 8:
        raise N5LiveTrackingBlocked("for_trade_date_must_be_yyyymmdd")
    required_names = ["action_run_id", "consumer_name"]
    ref_scoped_executed = _is_fastlane_executed_phase(args) and bool(
        str(getattr(args, "fastlane_ref_state_key", "") or "").strip()
    )
    if not _is_active_set_a_intake(args) and not ref_scoped_executed:
        required_names.insert(0, "source_trigger_run_id")
    if str(getattr(args, "fastlane_phase", "") or "") != "intake":
        required_names.append("source_metric_run_id")
    for name in required_names:
        if not str(getattr(args, name) or "").strip():
            raise N5LiveTrackingBlocked(f"{name}_required")
    if int(args.max_events) < 1:
        raise N5LiveTrackingBlocked("max_events_must_be_positive")
    if float(args.max_runtime_seconds) <= 0:
        raise N5LiveTrackingBlocked("max_runtime_seconds_must_be_positive")


def _apply_activation_config(
    args: argparse.Namespace,
    *,
    activation_discovery_provider: Callable[[argparse.Namespace, Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> None:
    config_path = str(getattr(args, "activation_config", "") or "").strip()
    if not config_path:
        return
    config = load_fastlane_activation_config(config_path)
    if bool(getattr(args, "execute", False)) or bool(getattr(args, "write_active_scope_artifact", False)):
        try:
            validate_fastlane_write_enabled_activation_authorization(config)
        except ValueError as exc:
            raise N5LiveTrackingBlocked(str(exc)) from exc
    phase = str(getattr(args, "fastlane_phase", "") or "").strip()
    lane_key = {
        "intake": "n5_action_intake",
        "executed": "n5_action_executed",
    }.get(phase)
    if not lane_key:
        raise N5LiveTrackingBlocked("activation_config_requires_fastlane_phase")
    runtime_inputs = (config.get("runtime_inputs") or {}).get(lane_key) or {}
    if not isinstance(runtime_inputs, Mapping):
        raise N5LiveTrackingBlocked("activation_config_runtime_inputs_must_be_object")

    args.fastlane_lane_id = args.fastlane_lane_id or FASTLANE_LANE_ID
    args.for_trade_date = args.for_trade_date or str(config.get("for_trade_date") or "")
    args.fastlane_trigger_time = str(
        getattr(args, "fastlane_trigger_time", "") or runtime_inputs.get("trigger_time") or ""
    )
    for name in ("source_trigger_run_id", "source_metric_run_id", "action_run_id", "consumer_name", "n5_intake_event_kind"):
        if not str(getattr(args, name, "") or "").strip():
            setattr(args, name, str(runtime_inputs.get(name) or ""))
    if not str(getattr(args, "fastlane_ref_state_key", "") or "").strip():
        args.fastlane_ref_state_key = str(runtime_inputs.get("fastlane_ref_state_key") or runtime_inputs.get("state_key") or "")
    if _activation_config_needs_discovery(args, phase):
        if activation_discovery_provider is not None or _activation_config_allows_runtime_env_discovery(config):
            provider = activation_discovery_provider or _default_activation_discovery_provider
            discovered = dict(provider(args, config) or {})
            for name in (
                "source_trigger_run_id",
                "source_metric_run_id",
                "action_run_id",
                "consumer_name",
                "n5_intake_event_kind",
                "fastlane_target_minute_label",
            ):
                if not str(getattr(args, name, "") or "").strip():
                    setattr(args, name, str(discovered.get(name) or ""))
            if not str(getattr(args, "fastlane_trigger_time", "") or "").strip():
                args.fastlane_trigger_time = str(discovered.get("trigger_time") or "")
            if not str(getattr(args, "fastlane_ref_state_key", "") or "").strip():
                args.fastlane_ref_state_key = str(
                    discovered.get("fastlane_ref_state_key") or discovered.get("state_key") or ""
                )
            batch_candidates = discovered.get("fastlane_executed_batch_candidates")
            if batch_candidates:
                args.fastlane_executed_batch_candidates = batch_candidates
                if not str(getattr(args, "fastlane_executed_batch_candidates_json", "") or "").strip():
                    args.fastlane_executed_batch_candidates_json = json.dumps(
                        _json_safe_value(batch_candidates),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
    if not str(args.consumer_name or "").strip():
        args.consumer_name = str(runtime_inputs.get("consumer_name") or config.get("n5_consumer_name") or DEFAULT_FASTLANE_CONSUMER_NAME)
    if not str(args.action_run_id or "").strip() and str(args.source_trigger_run_id or "").strip():
        args.action_run_id = _fastlane_action_run_id(
            for_trade_date=str(args.for_trade_date or ""),
            source_trigger_run_id=str(args.source_trigger_run_id),
        )
    if int(args.max_events or 0) <= 0:
        args.max_events = int(runtime_inputs.get("max_events") or config.get("n5_intake_max_events") or DEFAULT_EVENT_LIMIT)
    if float(args.max_runtime_seconds or 0.0) <= 0:
        args.max_runtime_seconds = float(
            runtime_inputs.get("max_runtime_seconds")
            or (config.get("max_runtime_seconds_by_lane") or {}).get(lane_key)
            or DEFAULT_FASTLANE_MAX_RUNTIME_SECONDS
        )
    if not str(getattr(args, "post_close_final_a_pass_done_marker_path", "") or "").strip():
        args.post_close_final_a_pass_done_marker_path = str(
            config.get("post_close_final_a_pass_done_marker_path")
            or (config.get("session_context_policy") or {}).get("post_close_final_a_pass_done_marker_path")
            or default_post_close_final_a_pass_done_marker_path(
                for_trade_date=str(args.for_trade_date or config.get("for_trade_date") or "")
            )
        )
    if phase == "intake" and not str(args.active_scope_artifact_path or "").strip():
        artifact_dir = str(config.get("n5_active_scope_artifact_dir") or "").strip()
        if artifact_dir and str(args.action_run_id or "").strip():
            args.active_scope_artifact_path = str(
                Path(artifact_dir)
                / _fastlane_active_scope_artifact_filename(
                    for_trade_date=str(args.for_trade_date or ""),
                    source_trigger_run_id=str(args.source_trigger_run_id or ""),
                    action_run_id=str(args.action_run_id or ""),
                )
            )
    _apply_fastlane_worker_phase_gate(args, config, lane_key=lane_key)


def _apply_fastlane_worker_phase_gate(
    args: argparse.Namespace,
    config: Mapping[str, Any],
    *,
    lane_key: str,
) -> None:
    session_context = config.get("session_context") or {}
    try:
        n5_intake_event_kind = str(getattr(args, "n5_intake_event_kind", "") or "")
        active_set_a_available = n5_intake_event_kind in ACTIVE_SET_A_INTAKE_EVENT_KINDS
        formal_trigger_matched_available = active_set_a_available or (
            n5_intake_event_kind in {"", "formal_TriggerMatched"}
            and bool(str(args.source_trigger_run_id or "").strip())
        )
        inactive_trigger_state_changed_available = n5_intake_event_kind == "inactive_TriggerStateChanged_false"
        active_trigger_state_changed_available = (
            active_set_a_available or n5_intake_event_kind == "active_TriggerStateChanged_true"
        )
        session_context = resolve_fastlane_runtime_session_context(
            config,
            trigger_time=str(getattr(args, "fastlane_trigger_time", "") or ""),
            formal_trigger_matched_available=formal_trigger_matched_available,
            inactive_trigger_state_changed_available=inactive_trigger_state_changed_available,
            active_trigger_state_changed_available=active_trigger_state_changed_available,
            matching_n3t_metric_available=lane_key == "n5_action_executed"
            and bool(str(args.source_metric_run_id or "").strip()),
        )
    except ValueError as exc:
        raise N5LiveTrackingBlocked(str(exc)) from exc
    if not isinstance(session_context, Mapping) or not session_context:
        return
    classification = classify_fastlane_session_phase(
        for_trade_date=str(args.for_trade_date or config.get("for_trade_date") or ""),
        trigger_time=str(session_context.get("trigger_time") or session_context.get("current_exchange_time") or ""),
        current_exchange_time=str(session_context.get("current_exchange_time") or ""),
        trade_calendar_is_open=bool(session_context.get("trade_calendar_is_open")),
    )
    decision = resolve_fastlane_active_worker_decision(
        lane_key=lane_key,
        session_phase=str(classification["phase"]),
        formal_trigger_matched_available=bool(session_context.get("formal_trigger_matched_available"))
        or formal_trigger_matched_available,
        inactive_trigger_state_changed_available=bool(session_context.get("inactive_trigger_state_changed_available"))
        or inactive_trigger_state_changed_available,
        active_trigger_state_changed_available=bool(session_context.get("active_trigger_state_changed_available"))
        or active_trigger_state_changed_available,
        closed_minute_available=bool(session_context.get("closed_minute_available")),
        matching_n3t_metric_available=bool(session_context.get("matching_n3t_metric_available"))
        or (lane_key == "n5_action_executed" and bool(str(args.source_metric_run_id or "").strip())),
        for_trade_date_is_current_date=bool(
            session_context.get("for_trade_date_is_current_date", classification.get("current_date_matches_for_trade_date"))
        ),
        trade_calendar_is_open=bool(session_context.get("trade_calendar_is_open")),
        post_close_final_a_pass_available=bool(
            session_context.get("post_close_final_a_pass_available", classification["phase"] == "post_close")
        ),
        post_close_final_a_pass_done=bool(session_context.get("post_close_final_a_pass_done")),
    )
    args.fastlane_session_phase = classification["phase"]
    args.fastlane_active_worker_decision = decision
    if decision["worker_mode"] == "fail_closed":
        raise N5LiveTrackingBlocked(f"fastlane_worker_{decision.get('blocked_reason') or 'fail_closed'}")
    if args.execute and not decision["writes_enabled_allowed"]:
        raise N5LiveTrackingBlocked(f"fastlane_worker_{decision.get('blocked_reason') or 'write_not_allowed'}")
    if args.write_active_scope_artifact and not decision["artifact_writes_enabled_allowed"]:
        raise N5LiveTrackingBlocked(f"fastlane_worker_{decision.get('blocked_reason') or 'artifact_write_not_allowed'}")


def _activation_config_needs_discovery(args: argparse.Namespace, phase: str) -> bool:
    if not str(args.source_trigger_run_id or "").strip():
        return True
    if phase == "executed" and not str(args.source_metric_run_id or "").strip():
        return True
    return not str(args.action_run_id or "").strip() or not str(args.consumer_name or "").strip()


def _activation_config_allows_runtime_env_discovery(config: Mapping[str, Any]) -> bool:
    allowed_policy = "runtime_env_required_no_secret_in_artifact"
    if str(config.get("dsn_env_policy") or "") == allowed_policy:
        return True
    activation_policy = config.get("activation_config_policy") or {}
    return isinstance(activation_policy, Mapping) and str(activation_policy.get("dsn_env_policy") or "") == allowed_policy


def _fastlane_action_run_id(*, for_trade_date: str, source_trigger_run_id: str) -> str:
    safe_trade_date = "".join(ch for ch in str(for_trade_date) if ch.isdigit()) or "unknown_trade_date"
    safe_source_run_id = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(source_trigger_run_id).strip()
    )
    return f"n5_live_tracking_{safe_trade_date}__{safe_source_run_id}__fastlane_v1"


def _fastlane_active_set_a_action_run_id(*, for_trade_date: str) -> str:
    safe_trade_date = "".join(ch for ch in str(for_trade_date) if ch.isdigit()) or "unknown_trade_date"
    return f"n5_live_tracking_{safe_trade_date}__active_set_a__fastlane_v1"


def _default_activation_discovery_provider(
    args: argparse.Namespace,
    _config: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not str(args.dsn or "").strip():
        return {}
    try:
        with psycopg.connect(
            args.dsn,
            row_factory=dict_row,
            options="-c default_transaction_read_only=on",
            connect_timeout=10,
        ) as conn, conn.cursor() as cur:
            if str(args.fastlane_phase or "") == "intake":
                return _discover_intake_runtime_inputs(cur, args)
            if str(args.fastlane_phase or "") == "executed":
                return _discover_executed_runtime_inputs(cur, args)
    except N5LiveTrackingBlocked:
        raise
    except Exception as exc:
        raise N5LiveTrackingBlocked(f"activation_discovery_failed:{type(exc).__name__}") from exc
    return {}


def _discover_intake_runtime_inputs(cur: Any, args: argparse.Namespace) -> dict[str, str]:
    cur.execute(
        """
        SELECT
          min(o.event_time)::text AS first_trigger_time,
          max(o.event_time)::text AS latest_trigger_time,
          bool_or(o.event_type = 'TriggerMatched') AS has_trigger_matched,
	          bool_or(
	            o.event_type = 'TriggerStateChanged'
	            AND lower(coalesce(o.payload_json->>'trigger_live', 'true')) IN ('false', 'f', '0', 'no', 'n')
	          ) AS has_inactive_state_changed,
	          bool_or(
	            o.event_type = 'TriggerStateChanged'
	            AND lower(coalesce(o.payload_json->>'trigger_live', 'true')) NOT IN ('false', 'f', '0', 'no', 'n')
	          ) AS has_active_state_changed
	        FROM common_event_outbox o
        WHERE o.source_layer = 'N4_trigger'
          AND o.trade_date = %s
          AND o.status = 'pending'
	          AND (
	            o.event_type = 'TriggerMatched'
	            OR o.event_type = 'TriggerStateChanged'
	          )
          AND NOT EXISTS (
            SELECT 1
            FROM common_event_inbox i
            WHERE i.consumer_name = %s
              AND i.event_id = o.event_id
          )
        """,
        (args.for_trade_date, DEFAULT_FASTLANE_CONSUMER_NAME),
    )
    row = cur.fetchone()
    if not row or not any(
        bool((row or {}).get(name))
        for name in ("has_trigger_matched", "has_inactive_state_changed", "has_active_state_changed")
    ):
        return _discover_processed_tsc_true_repair_inputs(cur, args)
    return {
        "trigger_time": str((row or {}).get("latest_trigger_time") or (row or {}).get("first_trigger_time") or ""),
        "n5_intake_event_kind": "active_set_a",
        "action_run_id": _fastlane_active_set_a_action_run_id(for_trade_date=str(args.for_trade_date)),
        "consumer_name": DEFAULT_FASTLANE_CONSUMER_NAME,
    }


def _discover_processed_tsc_true_repair_inputs(cur: Any, args: argparse.Namespace) -> dict[str, str]:
    consumer_name = str(getattr(args, "consumer_name", "") or DEFAULT_FASTLANE_CONSUMER_NAME)
    cur.execute(
        """
        SELECT
          min(o.event_time)::text AS first_trigger_time,
          max(o.event_time)::text AS latest_trigger_time,
          bool_or(true) AS has_active_state_changed
        FROM common_event_outbox o
        JOIN common_event_inbox i
          ON i.event_id = o.event_id
         AND i.consumer_name = %s
         AND i.status = 'processed'
        WHERE o.source_layer = 'N4_trigger'
          AND o.trade_date = %s
          AND o.event_type = 'TriggerStateChanged'
          AND lower(coalesce(o.payload_json->>'trigger_live', 'true')) NOT IN ('false', 'f', '0', 'no', 'n')
          AND coalesce(o.payload_json->>'current_status', 'matched') = 'matched'
          AND NOT EXISTS (
            SELECT 1
            FROM common_action_tracking_state t
            WHERE t.trade_date = o.trade_date
              AND t.source_trigger_event_id = o.event_id
              AND t.source_trigger_event_type = 'TriggerStateChanged'
              AND t.action_state = 'eligible'
              AND t.tracking_status = 'tracking'
          )
          AND NOT EXISTS (
            SELECT 1
            FROM common_event_outbox inactive
            WHERE inactive.source_layer = 'N4_trigger'
              AND inactive.trade_date = o.trade_date
              AND inactive.event_type = 'TriggerStateChanged'
              AND inactive.event_time >= o.event_time
              AND inactive.asset_kind = o.asset_kind
              AND inactive.identity_key = o.identity_key
              AND coalesce(inactive.payload_json->>'condition_key', '') = coalesce(o.payload_json->>'condition_key', '')
              AND lower(coalesce(inactive.payload_json->>'trigger_live', 'true')) IN ('false', 'f', '0', 'no', 'n')
          )
        """,
        (consumer_name, args.for_trade_date),
    )
    row = cur.fetchone()
    if not row or not bool((row or {}).get("has_active_state_changed")):
        return {}
    return {
        "trigger_time": str((row or {}).get("latest_trigger_time") or (row or {}).get("first_trigger_time") or ""),
        "n5_intake_event_kind": "active_set_a",
        "action_run_id": _fastlane_active_set_a_action_run_id(for_trade_date=str(args.for_trade_date)),
        "consumer_name": consumer_name,
    }


def _discover_stale_metric_status_reevaluation_runtime_inputs(
    cur: Any, args: argparse.Namespace
) -> dict[str, str]:
    for asset_kind, table_name in N3T_ACTION_CONFIRMATION_METRIC_TABLES_BY_ASSET_KIND.items():
        cur.execute(
            f"""
            WITH stale_tracking AS (
              SELECT
                s.*,
                CASE
                  WHEN coalesce(s.raw_json->'latest_metric_status'->>'source_action_confirmation_metric_id', '') ~ '^[0-9]+$'
                    THEN (s.raw_json->'latest_metric_status'->>'source_action_confirmation_metric_id')::bigint
                  ELSE NULL::bigint
                END AS stale_metric_id
              FROM common_action_tracking_state s
              WHERE s.trade_date = %s
                AND s.run_id ~ %s
                AND s.asset_kind = %s
                AND s.action_state = 'eligible'
                AND s.tracking_status = 'tracking'
                AND coalesce(s.raw_json->'latest_metric_status'->>'reason', '') = ANY(%s)
            )
            SELECT
              s.run_id,
              coalesce(s.asset_kind, '') AS asset_kind,
              coalesce(s.identity_key, '') AS identity_key,
              coalesce(s.direction, '') AS direction,
              coalesce(s.signal_type, '') AS signal_type,
              coalesce(s.condition_key, '') AS condition_key,
              coalesce(s.source_trigger_run_id, '') AS source_trigger_run_id,
              coalesce(s.source_trigger_event_id, '') AS source_trigger_event_id,
              coalesce(s.state_key, '') AS state_key,
              s.latest_n4_event_time::text AS trigger_time,
              s.latest_n4_event_time::text AS latest_n4_event_time,
              coalesce(s.last_checked_minute_label, '')::text AS last_checked_minute_label,
              coalesce(s.raw_json->>'next_unchecked_minute_label', '') AS next_unchecked_minute_label,
              s.raw_json,
              coalesce(s.raw_json->>'source_run_hash', '') AS source_run_hash,
              1 AS active_tracking_count,
              coalesce(m.metric_minute_label, '') AS target_minute_label,
              coalesce(m.projection_run_id, '') AS source_metric_run_id
            FROM stale_tracking s
            JOIN {table_name} m
              ON m.n3t_action_confirmation_metric_id = s.stale_metric_id
            WHERE coalesce(m.source_basis, '') = 'N3T_C1_CLOSED'
              AND coalesce(m.metric_role, '') = 'action_confirmation'
              AND coalesce(m.proof_consumer, '') = 'N5'
              AND coalesce(m.not_n5_final_proof, false) = false
              AND coalesce(m.metric_ready, false) = true
              AND coalesce(m.metric_quality_status, '') = 'passed'
              AND coalesce(m.raw_json->'previous_period_sources'->>'120m', '') <> ''
              AND coalesce(m.raw_json->'previous_period_sources'->>'120m', '') <> 'not_available'
            ORDER BY s.latest_n4_event_time NULLS LAST, s.run_id, s.state_key
            LIMIT %s
            """,
            (
                args.for_trade_date,
                FASTLANE_ACTION_RUN_ID_REGEX,
                asset_kind,
                sorted(STALE_METRIC_STATUS_REEVALUATION_REASONS),
                FASTLANE_EXECUTED_DISCOVERY_CANDIDATE_LIMIT,
            ),
        )
        for candidate in [dict(row) for row in cur.fetchall()]:
            source_metric_run_id = str(candidate.get("source_metric_run_id") or "")
            target_minute_label = _minute_label_text(candidate.get("target_minute_label")).replace(":", "")
            if not source_metric_run_id or not target_minute_label:
                continue
            candidate["target_minute_label"] = target_minute_label
            plan = _build_executed_candidate_plan(cur, args, candidate, source_metric_run_id)
            if _plan_action_executed_count(plan) > 0 or _plan_tracking_update_count(plan) > 0:
                return _executed_runtime_input_output(candidate, source_metric_run_id)
    return {}


def _discover_executed_runtime_inputs(cur: Any, args: argparse.Namespace) -> dict[str, str]:
    explicit_candidates = _explicit_active_scope_executed_candidates(args)
    if explicit_candidates:
        current_candidates = _rehydrate_active_scope_executed_candidates(cur, args, explicit_candidates)
        if not current_candidates:
            raise N5LiveTrackingBlocked("fastlane_worker_waiting_for_actionexecuted_candidate")
        return _discover_executed_runtime_input_from_candidates(cur, args, current_candidates)
    latest_active_scope_candidates = _latest_active_scope_executed_candidates(args)
    missing_metric_exc: N5LiveTrackingBlocked | None = None
    if latest_active_scope_candidates:
        latest_active_scope_candidates = _rehydrate_active_scope_executed_candidates(
            cur,
            args,
            latest_active_scope_candidates,
        )
    if latest_active_scope_candidates:
        try:
            return _discover_executed_runtime_input_from_candidates(cur, args, latest_active_scope_candidates)
        except N5LiveTrackingBlocked as exc:
            if str(exc) != "fastlane_worker_waiting_for_n3t_c1_closed_metric":
                raise
            missing_metric_exc = exc
    try:
        active_tracking_candidate = _discover_active_tracking_executed_runtime_inputs(cur, args)
    except N5LiveTrackingBlocked as exc:
        if str(exc) != "fastlane_worker_waiting_for_n3t_c1_closed_metric":
            raise
        missing_metric_exc = exc
        active_tracking_candidate = {}
    if active_tracking_candidate:
        return active_tracking_candidate
    stale_metric_status_candidate = _discover_stale_metric_status_reevaluation_runtime_inputs(cur, args)
    if stale_metric_status_candidate:
        return stale_metric_status_candidate
    final_no_action_candidate = _discover_post_close_no_action_terminalization_runtime_inputs(cur, args)
    if final_no_action_candidate:
        return final_no_action_candidate
    if missing_metric_exc is not None:
        raise missing_metric_exc
    raise N5LiveTrackingBlocked("fastlane_worker_waiting_for_actionexecuted_candidate")


def _discover_active_tracking_executed_runtime_inputs(cur: Any, args: argparse.Namespace) -> dict[str, Any]:
    cur.execute(
        """
        WITH active_tracking AS (
          SELECT *
          FROM common_action_tracking_state
          WHERE trade_date = %s
            AND run_id ~ %s
            AND action_state = 'eligible'
            AND tracking_status = 'tracking'
        ),
        active_source_run_group AS (
          SELECT
            run_id,
            ''::text AS asset_kind,
            ''::text AS identity_key,
            ''::text AS direction,
            ''::text AS signal_type,
            ''::text AS condition_key,
            source_trigger_run_id,
            ''::text AS source_trigger_event_id,
            ''::text AS state_key,
            min(latest_n4_event_time)::text AS trigger_time,
            min(latest_n4_event_time)::text AS latest_n4_event_time,
            ''::text AS last_checked_minute_label,
            ''::text AS next_unchecked_minute_label,
            NULL::jsonb AS raw_json,
            ''::text AS source_run_hash,
            count(*) AS active_tracking_count
          FROM active_tracking
          WHERE coalesce(source_trigger_run_id, '') <> ''
          GROUP BY run_id, source_trigger_run_id
        ),
        ref_scoped AS (
          SELECT
            run_id,
            coalesce(asset_kind, '') AS asset_kind,
            coalesce(identity_key, '') AS identity_key,
            coalesce(direction, '') AS direction,
            coalesce(signal_type, '') AS signal_type,
            coalesce(condition_key, '') AS condition_key,
            coalesce(source_trigger_run_id, '') AS source_trigger_run_id,
            coalesce(source_trigger_event_id, '') AS source_trigger_event_id,
            coalesce(state_key, '') AS state_key,
            latest_n4_event_time::text AS trigger_time,
            latest_n4_event_time::text AS latest_n4_event_time,
            coalesce(last_checked_minute_label, '')::text AS last_checked_minute_label,
            coalesce(raw_json->>'next_unchecked_minute_label', '') AS next_unchecked_minute_label,
            raw_json,
            coalesce(raw_json->>'source_run_hash', '') AS source_run_hash,
            1 AS active_tracking_count
          FROM active_tracking
          WHERE coalesce(source_trigger_run_id, '') = ''
        )
        SELECT *
        FROM (
          SELECT * FROM active_source_run_group
          UNION ALL
          SELECT * FROM ref_scoped
        ) candidates
        ORDER BY trigger_time DESC NULLS LAST, run_id, source_trigger_run_id, state_key
        LIMIT %s
        """,
        (args.for_trade_date, FASTLANE_ACTION_RUN_ID_REGEX, FASTLANE_EXECUTED_DISCOVERY_CANDIDATE_LIMIT),
    )
    try:
        return _discover_executed_runtime_input_from_candidates(cur, args, [dict(row) for row in cur.fetchall()])
    except N5LiveTrackingBlocked as exc:
        if str(exc) == "fastlane_worker_waiting_for_actionexecuted_candidate":
            return {}
        raise


def _discover_executed_runtime_input_from_candidates(
    cur: Any,
    args: argparse.Namespace,
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    evidence_candidate: dict[str, str] | None = None
    batch_candidates: list[dict[str, Any]] = []
    matched_metric_seen = False
    exact_ready_metric_run_ids = _discover_exact_ready_n3t_metric_run_ids(
        cur,
        str(args.for_trade_date),
        candidates=candidates,
    )
    ordered_candidates = sorted(
        enumerate(candidates),
        key=lambda item: (
            0 if item[0] in exact_ready_metric_run_ids else 1,
            -_candidate_trigger_time_sort_value(item[1]),
            str(item[1].get("target_minute_label") or ""),
            str(item[1].get("state_key") or ""),
        ),
    )
    batch_limit = min(
        FASTLANE_EXECUTED_CONTINUOUS_METRIC_RUN_LIMIT,
        max(1, int(getattr(args, "max_events", 0) or FASTLANE_EXECUTED_CONTINUOUS_METRIC_RUN_LIMIT)),
    )
    for candidate_index, candidate_source in ordered_candidates:
        candidate = dict(candidate_source)
        action_run_id = str(candidate.get("run_id") or "")
        source_trigger_run_id = str(candidate.get("source_trigger_run_id") or "")
        target_minute_label = _candidate_target_minute_label(candidate, for_trade_date=str(args.for_trade_date))
        if not action_run_id or not target_minute_label:
            continue
        source_run_hash = _candidate_source_run_hash(
            candidate,
            for_trade_date=str(args.for_trade_date),
            action_run_id=action_run_id,
            source_trigger_run_id=source_trigger_run_id,
            target_minute_label=target_minute_label,
        )
        if not source_run_hash:
            continue
        candidate["target_minute_label"] = target_minute_label
        candidate["source_run_hash"] = source_run_hash
        source_metric_run_id = exact_ready_metric_run_ids.get(candidate_index, "")
        if not source_metric_run_id:
            source_metric_run_id = _discover_latest_ready_n3t_metric_run_id(
                cur,
                str(args.for_trade_date),
                target_minute_label=target_minute_label,
                source_run_hash=source_run_hash,
            )
        if not source_metric_run_id:
            source_metric_run_id = _discover_ready_object_minute_n3t_metric_run_id(
                cur,
                str(args.for_trade_date),
                candidate=candidate,
                target_minute_label=target_minute_label,
            )
        if not source_metric_run_id:
            continue
        matched_metric_seen = True
        source_metric_run_id_text = source_metric_run_id
        plan = _build_executed_candidate_plan(cur, args, candidate, source_metric_run_id_text)
        if _plan_action_executed_count(plan) > 0:
            candidate["source_metric_run_id"] = source_metric_run_id_text
            batch_candidates.append(candidate)
            if len(batch_candidates) >= batch_limit:
                return _executed_runtime_batch_or_single_input_output(batch_candidates)
            continue
        if _plan_tracking_update_count(plan) > 0:
            candidate["source_metric_run_id"] = source_metric_run_id_text
            if evidence_candidate is None:
                evidence_candidate = _executed_runtime_input_output(candidate, source_metric_run_id_text)
            batch_candidates.append(candidate)
            if len(batch_candidates) >= batch_limit:
                return _executed_runtime_batch_or_single_input_output(batch_candidates)
    if batch_candidates:
        return _executed_runtime_batch_or_single_input_output(batch_candidates)
    if evidence_candidate is not None:
        return evidence_candidate
    if not matched_metric_seen:
        raise N5LiveTrackingBlocked("fastlane_worker_waiting_for_n3t_c1_closed_metric")
    raise N5LiveTrackingBlocked("fastlane_worker_waiting_for_actionexecuted_candidate")


def _discover_exact_ready_n3t_metric_run_ids(
    cur: Any,
    for_trade_date: str,
    *,
    candidates: Sequence[Mapping[str, Any]],
) -> dict[int, str]:
    """Batch-discover exact target-minute N3T proofs before generic scans."""
    grouped: dict[str, list[tuple[int, str, str]]] = {}
    for index, candidate in enumerate(candidates):
        asset_kind = str(candidate.get("asset_kind") or "")
        identity_key = str(candidate.get("identity_key") or "")
        target_label = _minute_label_text(candidate.get("target_minute_label"))
        table_name = N3T_ACTION_CONFIRMATION_METRIC_TABLES_BY_ASSET_KIND.get(asset_kind)
        if not table_name or not identity_key or not target_label:
            continue
        grouped.setdefault(table_name, []).append((index, identity_key, target_label))

    output: dict[int, str] = {}
    for table_name, values in grouped.items():
        placeholders = ", ".join(["(%s, %s, %s)"] * len(values))
        params: list[Any] = []
        for index, identity_key, target_label in values:
            params.extend((index, identity_key, target_label))
        params.append(for_trade_date)
        cur.execute(
            f"""
            WITH candidate_targets(candidate_index, identity_key, target_minute_label) AS (
              VALUES {placeholders}
            ), ready_proofs AS (
              SELECT
                c.candidate_index,
                m.projection_run_id,
                row_number() OVER (
                  PARTITION BY c.candidate_index
                  ORDER BY m.created_at DESC, m.projection_run_id DESC
                ) AS proof_rank
              FROM candidate_targets c
              JOIN {table_name} m
                ON m.identity_key = c.identity_key
               AND coalesce(nullif(m.metric_minute_label, ''),
                   to_char(m.metric_time AT TIME ZONE 'Asia/Shanghai', 'HH24:MI')) = c.target_minute_label
              WHERE m.for_trade_date = %s
                AND m.source_basis = 'N3T_C1_CLOSED'
                AND m.metric_role = 'action_confirmation'
                AND m.proof_consumer = 'N5'
                AND m.not_n5_final_proof = false
                AND m.metric_ready = true
                AND m.metric_quality_status = 'passed'
            )
            SELECT candidate_index, projection_run_id
            FROM ready_proofs
            WHERE proof_rank = 1
            """,
            params,
        )
        for row in cur.fetchall():
            index = int(row.get("candidate_index"))
            run_id = str(row.get("projection_run_id") or "")
            if run_id:
                output[index] = run_id
    return output


def _explicit_active_scope_executed_candidates(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = _load_explicit_active_scope_tracking_rows(args)
    if not rows:
        return []
    return _active_scope_rows_to_executed_candidates(args, rows)


def _latest_active_scope_executed_candidates(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = _load_latest_active_scope_tracking_rows(args)
    if not rows:
        return []
    return _active_scope_rows_to_executed_candidates(args, rows)


def _active_scope_rows_to_executed_candidates(
    args: argparse.Namespace,
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("action_state") or "") != "eligible" or str(row.get("tracking_status") or "") != "tracking":
            continue
        candidate = {
            "run_id": str(row.get("run_id") or getattr(args, "action_run_id", "") or ""),
            "asset_kind": str(row.get("asset_kind") or ""),
            "identity_key": str(row.get("identity_key") or ""),
            "direction": str(row.get("direction") or ""),
            "signal_type": str(row.get("signal_type") or ""),
            "condition_key": str(row.get("condition_key") or ""),
            "source_trigger_run_id": str(row.get("source_trigger_run_id") or ""),
            "source_trigger_event_id": str(row.get("source_trigger_event_id") or row.get("latest_n4_event_id") or ""),
            "state_key": str(row.get("state_key") or ""),
            "trigger_time": str(row.get("trigger_time") or row.get("latest_n4_event_time") or ""),
            "latest_n4_event_time": str(row.get("latest_n4_event_time") or row.get("trigger_time") or ""),
            "last_checked_minute_label": str(row.get("last_checked_minute_label") or ""),
            "next_unchecked_minute_label": str(
                row.get("next_unchecked_minute_label")
                or (row.get("raw_json") or {}).get("next_unchecked_minute_label")
                or ""
            ),
            "object_minute_source_run_hash": str(
                row.get("object_minute_source_run_hash")
                or (row.get("raw_json") or {}).get("object_minute_source_run_hash")
                or ""
            ),
            "raw_json": dict(row.get("raw_json") or {}),
            "active_tracking_count": 1,
            "active_tracking_row": dict(row),
        }
        target_minute_label = _candidate_target_minute_label(candidate, for_trade_date=str(args.for_trade_date))
        if not target_minute_label:
            continue
        source_run_hash = _candidate_source_run_hash(
            candidate,
            for_trade_date=str(args.for_trade_date),
            action_run_id=str(candidate.get("run_id") or ""),
            source_trigger_run_id=str(candidate.get("source_trigger_run_id") or ""),
            target_minute_label=target_minute_label,
        )
        if not source_run_hash:
            continue
        candidate["target_minute_label"] = target_minute_label
        candidate["source_run_hash"] = source_run_hash
        candidate["active_tracking_row"] = _tracking_row_with_candidate_target_cursor(
            candidate["active_tracking_row"],
            target_minute_label,
            for_trade_date=str(args.for_trade_date),
        )
        candidates.append(candidate)
    candidates.sort(
        key=lambda item: (
            -_candidate_trigger_time_sort_value(item),
            str(item.get("target_minute_label") or ""),
            str(item.get("state_key") or ""),
        )
    )
    return candidates[:FASTLANE_EXECUTED_DISCOVERY_CANDIDATE_LIMIT]


def _rehydrate_active_scope_executed_candidates(
    cur: Any,
    args: argparse.Namespace,
    candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Treat the A artifact as a state-key allowlist and reload mutable DB state."""
    grouped_state_keys: dict[str, list[str]] = {}
    for candidate in candidates:
        action_run_id = str(candidate.get("run_id") or getattr(args, "action_run_id", "") or "").strip()
        state_key = str(candidate.get("state_key") or "").strip()
        if not action_run_id or not state_key:
            continue
        run_keys = grouped_state_keys.setdefault(action_run_id, [])
        if state_key not in run_keys:
            run_keys.append(state_key)

    current_rows: list[dict[str, Any]] = []
    for action_run_id, state_keys in grouped_state_keys.items():
        allowed_keys = set(state_keys)
        rows = _fetch_active_tracking_rows_by_state_keys(
            cur,
            args,
            action_run_id=action_run_id,
            state_keys=state_keys,
        )
        current_rows.extend(
            dict(row)
            for row in rows
            if str(row.get("state_key") or "") in allowed_keys
        )

    rehydrated = _active_scope_rows_to_executed_candidates(args, current_rows)
    for candidate in rehydrated:
        candidate["db_rehydrated_active_tracking_row"] = True
    return rehydrated


def _tracking_row_with_candidate_target_cursor(
    row: Mapping[str, Any],
    target_minute_label: str,
    *,
    for_trade_date: str = "",
) -> dict[str, Any]:
    aligned = dict(row)
    target_label = _minute_label_text(target_minute_label)
    if not target_label:
        return aligned
    if _candidate_target_precedes_tracking_cursor(
        aligned,
        target_label,
        for_trade_date=for_trade_date,
    ):
        return aligned
    raw_json = dict(aligned.get("raw_json") or {})
    raw_json["next_unchecked_minute_label"] = target_label
    aligned["raw_json"] = raw_json
    return aligned


def _candidate_target_precedes_tracking_cursor(
    row: Mapping[str, Any],
    target_minute_label: str,
    *,
    for_trade_date: str,
) -> bool:
    target_label = _minute_label_text(target_minute_label)
    raw_json = row.get("raw_json") or {}
    current_label = _minute_label_text(
        row.get("next_unchecked_minute_label")
        or (raw_json.get("next_unchecked_minute_label") if isinstance(raw_json, Mapping) else "")
    )
    if not target_label:
        return False
    if current_label:
        return _compare_candidate_minute_labels(
            target_label,
            current_label,
            for_trade_date=for_trade_date,
        ) < 0
    last_checked_label = _minute_label_text(
        row.get("last_checked_minute_label")
        or (raw_json.get("last_checked_minute_label") if isinstance(raw_json, Mapping) else "")
    )
    if not last_checked_label:
        return False
    return _compare_candidate_minute_labels(
        target_label,
        last_checked_label,
        for_trade_date=for_trade_date,
    ) <= 0


def _compare_candidate_minute_labels(
    left: str,
    right: str,
    *,
    for_trade_date: str,
) -> int:
    left_label = _minute_label_text(left)
    right_label = _minute_label_text(right)
    if not left_label or not right_label:
        return 0
    labels = canonical_ashare_1m_labels(for_trade_date) if re.fullmatch(r"\d{8}", str(for_trade_date or "")) else []
    if left_label in labels and right_label in labels:
        left_index = labels.index(left_label)
        right_index = labels.index(right_label)
        return (left_index > right_index) - (left_index < right_index)
    return (left_label > right_label) - (left_label < right_label)


def _candidate_trigger_time_sort_value(candidate: Mapping[str, Any]) -> float:
    values = (
        candidate.get("latest_n4_event_time"),
        candidate.get("trigger_time"),
    )
    timestamps: list[float] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        timestamps.append(parsed.timestamp())
    return max(timestamps, default=0.0)


def _discover_post_close_no_action_terminalization_runtime_inputs(
    cur: Any, args: argparse.Namespace
) -> dict[str, str]:
    labels = canonical_ashare_1m_labels(str(args.for_trade_date or ""))
    final_label = labels[-1] if labels else ""
    if not final_label:
        return {}
    cur.execute(
        """
        WITH post_close_no_action_candidates AS (
          SELECT
            run_id,
            coalesce(asset_kind, '') AS asset_kind,
            coalesce(identity_key, '') AS identity_key,
            coalesce(direction, '') AS direction,
            coalesce(signal_type, '') AS signal_type,
            coalesce(condition_key, '') AS condition_key,
            coalesce(source_trigger_run_id, '') AS source_trigger_run_id,
            coalesce(source_trigger_event_id, '') AS source_trigger_event_id,
            coalesce(state_key, '') AS state_key,
            latest_n4_event_time::text AS trigger_time,
            latest_n4_event_time::text AS latest_n4_event_time,
            coalesce(last_checked_minute_label, '')::text AS last_checked_minute_label,
            coalesce(raw_json->>'next_unchecked_minute_label', '') AS next_unchecked_minute_label,
            coalesce(raw_json->'latest_metric_status'->>'projection_run_id', '') AS source_metric_run_id,
            coalesce(raw_json->'latest_metric_status'->>'metric_minute_label', '') AS target_minute_label,
            coalesce(raw_json->'latest_metric_status'->>'reason', '') AS latest_metric_reason,
            raw_json,
            coalesce(raw_json->>'source_run_hash', '') AS source_run_hash,
            1 AS active_tracking_count
          FROM common_action_tracking_state
          WHERE trade_date = %s
            AND run_id ~ %s
            AND action_state = 'eligible'
            AND confirmation_status = 'pending'
            AND tracking_status = 'tracking'
            AND coalesce(last_checked_minute_label, '') = %s
        )
        SELECT *
        FROM post_close_no_action_candidates
        ORDER BY latest_n4_event_time NULLS LAST, run_id, state_key
        LIMIT %s
        """,
        (args.for_trade_date, FASTLANE_ACTION_RUN_ID_REGEX, final_label, FASTLANE_EXECUTED_DISCOVERY_CANDIDATE_LIMIT),
    )
    for candidate in [dict(row) for row in cur.fetchall()]:
        target_label = _minute_label_text(candidate.get("target_minute_label")) or _minute_label_text(
            candidate.get("last_checked_minute_label")
        )
        if target_label != final_label:
            continue
        source_metric_run_id = str(candidate.get("source_metric_run_id") or "").strip()
        if not source_metric_run_id:
            state_key = str(candidate.get("state_key") or "").strip()
            if not state_key:
                continue
            source_metric_run_id = f"n5_post_close_no_action_terminalization_{args.for_trade_date}_{_short_scope_hash(state_key)}"
        plan = _build_executed_candidate_plan(cur, args, candidate, source_metric_run_id)
        if _plan_action_executed_count(plan) > 0 or _plan_tracking_update_count(plan) > 0:
            return _executed_runtime_input_output(candidate, source_metric_run_id)
    return {}


def _plan_action_executed_count(plan: Mapping[str, Any]) -> int:
    summary = plan.get("summary") or {}
    try:
        return int(summary.get("action_executed_count") or 0)
    except (TypeError, ValueError):
        return sum(1 for event in plan.get("action_events") or [] if event.get("event_type") == "ActionExecuted")


def _plan_tracking_update_count(plan: Mapping[str, Any]) -> int:
    summary = plan.get("summary") or {}
    try:
        count = int(summary.get("tracking_upsert_count") or 0)
    except (TypeError, ValueError):
        count = 0
    if count > 0:
        return count
    return len(plan.get("tracking_updates") or [])


def _metric_minute_label_from_source_trigger_run_id(source_trigger_run_id: str) -> str:
    match = re.search(r"(?:^|_)until_([0-9]{4})(?:_|$)", str(source_trigger_run_id or ""))
    return match.group(1) if match else ""


def _candidate_target_minute_label(candidate: Mapping[str, Any], *, for_trade_date: str = "") -> str:
    explicit_label = str(candidate.get("target_minute_label") or "")
    if re.fullmatch(r"[0-2][0-9][0-5][0-9]", explicit_label):
        return _candidate_minute_label_at_or_after_trigger(
            candidate,
            explicit_label,
            for_trade_date=for_trade_date,
        )
    cursor_label = _candidate_next_unchecked_minute_label(candidate, for_trade_date=for_trade_date)
    if cursor_label:
        return _candidate_minute_label_at_or_after_trigger(
            candidate,
            cursor_label,
            for_trade_date=for_trade_date,
        )
    if _minute_label_text(candidate.get("last_checked_minute_label")):
        return ""
    for key in ("trigger_time", "latest_n4_event_time"):
        label = _metric_minute_label_from_time_text(candidate.get(key))
        if label:
            return label
    source_trigger_run_id = str(candidate.get("source_trigger_run_id") or "")
    label = _metric_minute_label_from_source_trigger_run_id(source_trigger_run_id)
    if label:
        return label
    return ""


def _candidate_minute_label_at_or_after_trigger(
    candidate: Mapping[str, Any],
    minute_label: str,
    *,
    for_trade_date: str,
) -> str:
    target_label = _minute_label_text(minute_label)
    trigger_label = _minute_label_text(candidate.get("trigger_time") or candidate.get("latest_n4_event_time"))
    if not target_label or not trigger_label:
        return target_label.replace(":", "")
    labels = canonical_ashare_1m_labels(for_trade_date) if re.fullmatch(r"\d{8}", str(for_trade_date or "")) else []
    if (
        target_label in labels
        and trigger_label in labels
        and labels.index(target_label) < labels.index(trigger_label)
    ):
        return trigger_label.replace(":", "")
    return target_label.replace(":", "")


def _candidate_next_unchecked_minute_label(candidate: Mapping[str, Any], *, for_trade_date: str) -> str:
    explicit_label = _minute_label_text(candidate.get("next_unchecked_minute_label"))
    first_label = _minute_label_text(candidate.get("trigger_time") or candidate.get("latest_n4_event_time"))
    last_label = _minute_label_text(candidate.get("last_checked_minute_label"))
    if explicit_label and not last_label:
        return explicit_label.replace(":", "")
    if explicit_label and last_label:
        labels = canonical_ashare_1m_labels(for_trade_date) if re.fullmatch(r"\d{8}", str(for_trade_date or "")) else []
        if explicit_label in labels and last_label in labels:
            if labels.index(explicit_label) > labels.index(last_label):
                return explicit_label.replace(":", "")
        elif explicit_label > last_label:
            return explicit_label.replace(":", "")
    if not first_label:
        return ""
    labels = canonical_ashare_1m_labels(for_trade_date) if re.fullmatch(r"\d{8}", str(for_trade_date or "")) else []
    if first_label not in labels:
        return first_label.replace(":", "")
    if not last_label or last_label not in labels:
        return first_label.replace(":", "")
    first_index = labels.index(first_label)
    last_index = labels.index(last_label)
    if last_index < first_index:
        return first_label.replace(":", "")
    next_index = last_index + 1
    if next_index >= len(labels):
        return ""
    return labels[next_index].replace(":", "")


def _minute_label_text(value: Any) -> str:
    text = str(value or "").strip()
    match = re.search(r"([0-2][0-9]):([0-5][0-9])", text)
    if match:
        return f"{match.group(1)}:{match.group(2)}"
    if re.fullmatch(r"[0-2][0-9][0-5][0-9]", text):
        return f"{text[:2]}:{text[2:]}"
    return ""


def _metric_minute_label_from_time_text(value: Any) -> str:
    match = re.search(r"(?:T|\s)([0-2][0-9]):([0-5][0-9])(?::[0-5][0-9])?", str(value or ""))
    if not match:
        return ""
    return f"{match.group(1)}{match.group(2)}"


def _candidate_source_run_hash(
    candidate: Mapping[str, Any],
    *,
    for_trade_date: str,
    action_run_id: str,
    source_trigger_run_id: str,
    target_minute_label: str,
) -> str:
    object_minute_hash = str(candidate.get("object_minute_source_run_hash") or "")
    if object_minute_hash:
        return object_minute_hash
    raw_json = candidate.get("raw_json") or {}
    if isinstance(raw_json, Mapping):
        object_minute_hash = str(raw_json.get("object_minute_source_run_hash") or "")
        if object_minute_hash:
            return object_minute_hash
    existing = str(candidate.get("source_run_hash") or "")
    if existing:
        return existing
    if isinstance(raw_json, Mapping):
        existing = str(raw_json.get("source_run_hash") or "")
        if existing:
            return existing
    if source_trigger_run_id:
        namespace = build_fastlane_source_run_namespace(
            for_trade_date=for_trade_date,
            source_trigger_run_id=source_trigger_run_id,
            action_run_id=action_run_id,
            target_hhmm=target_minute_label,
        )
        return str(namespace.get("source_run_hash") or "")
    for key in ("source_run_hash", "source_trigger_event_id", "state_key"):
        value = str(candidate.get(key) or "")
        if value:
            return _short_scope_hash(value)
    return ""


def _short_scope_hash(*parts: str) -> str:
    text = "|".join(str(part).strip() for part in parts if str(part).strip())
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _executed_runtime_input_output(candidate: Mapping[str, Any], source_metric_run_id: str) -> dict[str, str]:
    output: dict[str, str] = {
        "action_run_id": str(candidate.get("run_id") or ""),
        "source_trigger_run_id": str(candidate.get("source_trigger_run_id") or ""),
        "source_metric_run_id": str(source_metric_run_id),
        "consumer_name": DEFAULT_FASTLANE_CONSUMER_NAME,
    }
    if candidate.get("trigger_time"):
        output["trigger_time"] = str(candidate.get("trigger_time") or "")
    if candidate.get("state_key"):
        output["state_key"] = str(candidate.get("state_key") or "")
    if candidate.get("target_minute_label"):
        output["fastlane_target_minute_label"] = str(candidate.get("target_minute_label") or "")
    return {key: value for key, value in output.items() if value}


def _executed_runtime_batch_input_output(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not candidates:
        return {}
    first = candidates[0]
    metric_run_ids: list[str] = []
    for candidate in candidates:
        for run_id in coerce_metric_run_ids(str(candidate.get("source_metric_run_id") or "")):
            if run_id and run_id not in metric_run_ids:
                metric_run_ids.append(run_id)
    output: dict[str, Any] = {
        "action_run_id": str(first.get("run_id") or ""),
        "source_trigger_run_id": str(first.get("source_trigger_run_id") or ""),
        "source_metric_run_id": ",".join(metric_run_ids),
        "consumer_name": DEFAULT_FASTLANE_CONSUMER_NAME,
        "fastlane_ref_state_key": FASTLANE_EXECUTED_BATCH_STATE_KEY,
        "state_key": FASTLANE_EXECUTED_BATCH_STATE_KEY,
        "fastlane_executed_batch_candidates": [dict(candidate) for candidate in candidates],
    }
    if first.get("trigger_time"):
        output["trigger_time"] = str(first.get("trigger_time") or "")
    return {key: value for key, value in output.items() if value}


def _executed_runtime_batch_or_single_input_output(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len(candidates) == 1:
        candidate = candidates[0]
        return _executed_runtime_input_output(candidate, str(candidate.get("source_metric_run_id") or ""))
    return _executed_runtime_batch_input_output(candidates)


def _coerce_fastlane_executed_batch_candidates(args: argparse.Namespace) -> list[dict[str, Any]]:
    candidates = getattr(args, "fastlane_executed_batch_candidates", None)
    if isinstance(candidates, Sequence) and not isinstance(candidates, (str, bytes, bytearray)):
        return [dict(candidate) for candidate in candidates if isinstance(candidate, Mapping)]
    text = str(getattr(args, "fastlane_executed_batch_candidates_json", "") or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        raise N5LiveTrackingBlocked("fastlane_executed_batch_candidates_json_invalid")
    if not isinstance(parsed, list):
        raise N5LiveTrackingBlocked("fastlane_executed_batch_candidates_json_must_be_list")
    return [dict(candidate) for candidate in parsed if isinstance(candidate, Mapping)]


def _build_executed_candidate_plan(
    cur: Any,
    args: argparse.Namespace,
    candidate: Mapping[str, Any],
    source_metric_run_id: str,
) -> dict[str, Any]:
    candidate_args = argparse.Namespace(**vars(args))
    candidate_args.action_run_id = str(candidate.get("run_id") or "")
    candidate_args.source_trigger_run_id = str(candidate.get("source_trigger_run_id") or "")
    candidate_args.source_metric_run_id = str(source_metric_run_id)
    candidate_args.fastlane_ref_state_key = str(candidate.get("state_key") or "")
    candidate_args.consumer_name = str(getattr(args, "consumer_name", "") or DEFAULT_FASTLANE_CONSUMER_NAME)
    candidate_args.max_events = int(getattr(args, "max_events", 0) or DEFAULT_EVENT_LIMIT)
    explicit_tracking_row = candidate.get("active_tracking_row") if isinstance(candidate.get("active_tracking_row"), Mapping) else None
    if explicit_tracking_row is not None:
        active_tracking = [dict(explicit_tracking_row)]
        if candidate.get("db_rehydrated_active_tracking_row"):
            active_scope_tracking = [dict(explicit_tracking_row)]
        else:
            active_scope_tracking = _load_explicit_active_scope_tracking_rows(args) or [dict(explicit_tracking_row)]
    else:
        active_tracking = _fetch_active_tracking_rows(cur, candidate_args, n4_event_rows=[])
        active_scope_tracking = _fetch_active_scope_tracking_rows(cur, args)
    metric_rows = _fetch_metric_rows(cur, candidate_args)
    existing_event_keys = _fetch_existing_action_event_keys(cur, candidate_args)
    return build_live_tracking_plan(
        n4_event_rows=[],
        active_tracking_rows=active_tracking,
        metric_rows=metric_rows,
        action_run_id=candidate_args.action_run_id,
        source_trigger_run_id=candidate_args.source_trigger_run_id,
        source_metric_run_id=candidate_args.source_metric_run_id,
        consumer_name=candidate_args.consumer_name,
        existing_action_event_keys=existing_event_keys,
        active_scope_tracking_rows=active_scope_tracking,
        for_trade_date=str(args.for_trade_date),
    )


def _build_executed_batch_candidate_plan(
    cur: Any,
    args: argparse.Namespace,
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not candidates:
        raise N5LiveTrackingBlocked("fastlane_executed_batch_candidates_required")
    action_run_id = str(candidates[0].get("run_id") or getattr(args, "action_run_id", "") or "")
    if not action_run_id:
        raise N5LiveTrackingBlocked("action_run_id_required_for_executed_batch")
    source_metric_run_ids: list[str] = []
    for candidate in candidates:
        for run_id in coerce_metric_run_ids(str(candidate.get("source_metric_run_id") or "")):
            if run_id and run_id not in source_metric_run_ids:
                source_metric_run_ids.append(run_id)
    if not source_metric_run_ids:
        raise N5LiveTrackingBlocked("source_metric_run_id_required_for_executed_batch")
    state_keys = [
        str(candidate.get("state_key") or "").strip()
        for candidate in candidates
        if str(candidate.get("state_key") or "").strip()
        and str(candidate.get("state_key") or "").strip() != FASTLANE_EXECUTED_BATCH_STATE_KEY
    ]
    active_tracking = _fetch_active_tracking_rows_by_state_keys(
        cur,
        args,
        action_run_id=action_run_id,
        state_keys=state_keys,
    )
    if not active_tracking:
        raise N5LiveTrackingBlocked("active_tracking_rows_required_for_executed_batch")
    target_by_state_key = {
        str(candidate.get("state_key") or ""): str(candidate.get("target_minute_label") or "")
        for candidate in candidates
        if str(candidate.get("state_key") or "").strip()
    }
    aligned_active_tracking: list[dict[str, Any]] = []
    for row in active_tracking:
        target_minute_label = target_by_state_key.get(str(row.get("state_key") or ""), "")
        if _candidate_target_precedes_tracking_cursor(
            row,
            target_minute_label,
            for_trade_date=str(args.for_trade_date),
        ):
            continue
        aligned_active_tracking.append(
            _tracking_row_with_candidate_target_cursor(
                row,
                target_minute_label,
                for_trade_date=str(args.for_trade_date),
            )
        )
    active_tracking = aligned_active_tracking
    candidate_args = argparse.Namespace(**vars(args))
    candidate_args.action_run_id = action_run_id
    candidate_args.source_trigger_run_id = str(candidates[0].get("source_trigger_run_id") or "")
    candidate_args.source_metric_run_id = ",".join(source_metric_run_ids)
    candidate_args.fastlane_ref_state_key = ""
    candidate_args.consumer_name = str(getattr(args, "consumer_name", "") or DEFAULT_FASTLANE_CONSUMER_NAME)
    metric_rows = _fetch_metric_rows(cur, candidate_args)
    existing_event_keys = _fetch_existing_action_event_keys(cur, candidate_args)
    active_scope_tracking = _fetch_active_scope_tracking_rows(cur, args)
    return build_live_tracking_plan(
        n4_event_rows=[],
        active_tracking_rows=active_tracking,
        metric_rows=metric_rows,
        action_run_id=candidate_args.action_run_id,
        source_trigger_run_id=candidate_args.source_trigger_run_id,
        source_metric_run_id=candidate_args.source_metric_run_id,
        consumer_name=candidate_args.consumer_name,
        existing_action_event_keys=existing_event_keys,
        active_scope_tracking_rows=active_scope_tracking,
        for_trade_date=str(args.for_trade_date),
    )


def _fastlane_n3t_metric_run_id_regex(for_trade_date: str, target_minute_label: str, source_run_hash: str) -> str:
    safe_trade_date = re.escape(str(for_trade_date or ""))
    safe_minute_label = re.escape(str(target_minute_label or ""))
    safe_source_run_hash = re.escape(str(source_run_hash or ""))
    if not safe_source_run_hash:
        return r"a^"
    return (
        rf"^n3t_action_confirmation_metric_{safe_trade_date}_until_{safe_minute_label}"
        rf"__fastlane_sr_{safe_source_run_hash}_raw_prevday_c1_amount_v1$"
    )


def _fastlane_active_scope_artifact_filename(
    *,
    for_trade_date: str,
    source_trigger_run_id: str,
    action_run_id: str,
) -> str:
    namespace = build_fastlane_source_run_namespace(
        for_trade_date=for_trade_date,
        source_trigger_run_id=source_trigger_run_id,
        action_run_id=action_run_id,
    )
    return f"n5_active_scope_snapshot_v1_{namespace['token']}.json"


def _discover_latest_ready_n3t_metric_run_id(
    cur: Any,
    for_trade_date: str,
    *,
    target_minute_label: str,
    source_run_hash: str,
) -> str:
    if not str(source_run_hash or "").strip():
        return ""
    candidates: list[tuple[str, str]] = []
    metric_run_id_regex = _fastlane_n3t_metric_run_id_regex(for_trade_date, target_minute_label, source_run_hash)
    for table_name in (
        "stock_n3t_action_confirmation_metric",
        "index_n3t_action_confirmation_metric",
        "board_n3t_action_confirmation_metric",
    ):
        cur.execute(
            f"""
            SELECT projection_run_id, max(metric_time)::text AS latest_metric_time
            FROM {table_name}
            WHERE for_trade_date = %s
              AND source_basis = 'N3T_C1_CLOSED'
              AND metric_role = 'action_confirmation'
              AND proof_consumer = 'N5'
              AND not_n5_final_proof = false
              AND metric_ready = true
              AND metric_quality_status = 'passed'
              AND projection_run_id LIKE %s
              AND projection_run_id ~ %s
            GROUP BY projection_run_id
            ORDER BY max(metric_time) DESC, projection_run_id DESC
            LIMIT 1
            """,
            (for_trade_date, f"%until_{target_minute_label}__fastlane_sr_{source_run_hash}%", metric_run_id_regex),
        )
        row = cur.fetchone()
        if row and row.get("projection_run_id"):
            candidates.append((str(row.get("latest_metric_time") or ""), str(row["projection_run_id"])))
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return candidates[0][1]


def _discover_ready_object_minute_n3t_metric_run_id(
    cur: Any,
    for_trade_date: str,
    *,
    candidate: Mapping[str, Any],
    target_minute_label: str,
) -> str:
    run_ids = _discover_ready_object_minute_n3t_metric_run_ids(
        cur,
        for_trade_date,
        candidate=candidate,
        target_minute_label=target_minute_label,
        limit=1,
    )
    return run_ids[0] if run_ids else ""


def _discover_ready_object_minute_n3t_metric_run_ids(
    cur: Any,
    for_trade_date: str,
    *,
    candidate: Mapping[str, Any],
    target_minute_label: str,
    limit: int = FASTLANE_EXECUTED_CONTINUOUS_METRIC_RUN_LIMIT,
) -> list[str]:
    asset_kind = str(candidate.get("asset_kind") or "")
    identity_key = str(candidate.get("identity_key") or "")
    if asset_kind not in {"stock", "index", "board"} or not identity_key:
        return []
    table_name = {
        "stock": "stock_n3t_action_confirmation_metric",
        "index": "index_n3t_action_confirmation_metric",
        "board": "board_n3t_action_confirmation_metric",
    }[asset_kind]
    cur.execute(
        f"""
        SELECT metric_minute_label, metric_time, metric_evaluation_minute_label, projection_run_id
        FROM (
          SELECT DISTINCT ON (
                 COALESCE(NULLIF(metric_minute_label, ''), to_char(metric_time AT TIME ZONE 'Asia/Shanghai', 'HH24:MI'))
          )
                 projection_run_id,
                 metric_minute_label,
                 metric_time,
                 COALESCE(NULLIF(metric_minute_label, ''), to_char(metric_time AT TIME ZONE 'Asia/Shanghai', 'HH24:MI')) AS metric_evaluation_minute_label,
                 created_at
          FROM {table_name}
          WHERE for_trade_date = %s
            AND identity_key = %s
            AND COALESCE(NULLIF(metric_minute_label, ''), to_char(metric_time AT TIME ZONE 'Asia/Shanghai', 'HH24:MI')) >= %s
            AND source_basis = 'N3T_C1_CLOSED'
            AND metric_role = 'action_confirmation'
            AND proof_consumer = 'N5'
            AND not_n5_final_proof = false
            AND metric_ready = true
            AND metric_quality_status = 'passed'
          ORDER BY COALESCE(NULLIF(metric_minute_label, ''), to_char(metric_time AT TIME ZONE 'Asia/Shanghai', 'HH24:MI')) ASC,
                   created_at DESC,
                   projection_run_id DESC
        ) chosen
        ORDER BY metric_evaluation_minute_label ASC
        LIMIT %s
        """,
        (
            for_trade_date,
            identity_key,
            _minute_label_text(target_minute_label) or target_minute_label,
            max(1, int(limit or 1)),
        ),
    )
    output: list[str] = []
    expected_label = _minute_label_text(target_minute_label) or str(target_minute_label or "")
    canonical_labels = canonical_ashare_1m_labels(for_trade_date) if re.fullmatch(r"\d{8}", str(for_trade_date or "")) else []
    expected_index = canonical_labels.index(expected_label) if expected_label in canonical_labels else -1
    for row in cur.fetchall():
        metric_label = (
            _minute_label_text(_metric_minute_label_from_source_trigger_run_id(row.get("projection_run_id")))
            or _minute_label_text(row.get("metric_minute_label"))
            or _minute_label_text(row.get("metric_evaluation_minute_label"))
            or _minute_label_text(row.get("metric_time"))
        )
        if expected_index >= 0:
            if expected_index >= len(canonical_labels) or metric_label != canonical_labels[expected_index]:
                break
            expected_index += 1
        elif expected_label and metric_label != expected_label:
            break
        run_id = str(row.get("projection_run_id") or "")
        if run_id and run_id not in output:
            output.append(run_id)
    return output


def _validate_plan_boundary(plan: Mapping[str, Any]) -> None:
    for event in plan.get("action_events") or []:
        if str(event.get("event_type") or "") not in N5_OUTPUT_EVENT_TYPES:
            raise N5LiveTrackingBlocked("plan_contains_non_n6_output_event")
    if (plan.get("inbox_checkpoint_intent") or {}).get("updates_n4_outbox") is not False:
        raise N5LiveTrackingBlocked("plan_may_update_n4_outbox")


def _validate_fastlane_phase_plan_boundary(args: argparse.Namespace, plan: Mapping[str, Any]) -> None:
    if not _is_fastlane_executed_phase(args):
        return
    inbox_intent = plan.get("inbox_checkpoint_intent") or {}
    if plan.get("consumed_n4_events") or plan.get("consumed_n4_event_ids") or inbox_intent.get("source_event_ids"):
        raise N5LiveTrackingBlocked("executed_phase_must_not_consume_n4_events")


def _is_fastlane_executed_phase(args: argparse.Namespace) -> bool:
    return str(getattr(args, "fastlane_phase", "") or "") == "executed"


def _is_active_set_a_intake(args: argparse.Namespace) -> bool:
    return (
        str(getattr(args, "fastlane_phase", "") or "") == "intake"
        and str(getattr(args, "n5_intake_event_kind", "") or "") in ACTIVE_SET_A_INTAKE_EVENT_KINDS
    )


def _write_active_scope_artifact(args: argparse.Namespace, plan: Mapping[str, Any]) -> dict[str, Any]:
    if not _active_scope_artifact_writes_enabled(args):
        return {
            "executed": False,
            "reason": "artifact_write_disabled",
            "artifact_writes_enabled": False,
        }
    path_text = str(getattr(args, "active_scope_artifact_path", "") or "").strip()
    if not path_text:
        return {
            "executed": False,
            "reason": "active_scope_artifact_path_missing",
            "artifact_writes_enabled": True,
        }
    artifact = plan.get("active_scope_snapshot_artifact")
    if not isinstance(artifact, Mapping):
        raise N5LiveTrackingBlocked("active_scope_snapshot_artifact_missing")
    namespace = build_fastlane_source_run_namespace(
        for_trade_date=str(getattr(args, "for_trade_date", "") or ""),
        source_trigger_run_id=str(getattr(args, "source_trigger_run_id", "") or ""),
        action_run_id=str(getattr(args, "action_run_id", "") or ""),
    )
    artifact = dict(artifact)
    artifact["source_run_hash"] = namespace["source_run_hash"]
    artifact["source_run_namespace"] = namespace["token"]
    path = Path(path_text)
    if len(path.name.encode("utf-8")) > 240:
        raise N5LiveTrackingBlocked("active_scope_artifact_filename_too_long")
    atomic_write_json(path, _json_safe_value(artifact))
    return {
        "executed": True,
        "artifact_writes_enabled": True,
        "path": str(path),
        "artifact_type": artifact.get("artifact_type"),
        "scope_count": artifact.get("scope_count"),
    }


def _active_scope_artifact_writes_enabled(args: argparse.Namespace) -> bool:
    if bool(getattr(args, "write_active_scope_artifact", False)) and bool(getattr(args, "user_confirmed", False)):
        return True
    return False


def _maybe_write_post_close_final_a_pass_done_marker(
    args: argparse.Namespace,
    plan: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    decision = getattr(args, "fastlane_active_worker_decision", {}) or {}
    if str(getattr(args, "fastlane_session_phase", "") or "") != "post_close":
        return {"executed": False, "reason": "not_post_close"}
    if not bool(decision.get("post_close_final_a_pass_allowed")):
        return {"executed": False, "reason": str(decision.get("blocked_reason") or "post_close_final_a_pass_not_allowed")}

    phase = str(getattr(args, "fastlane_phase", "") or "")
    if phase == "intake" and decision.get("worker_mode") == "post_close_final_a_scope_snapshot":
        active_scope_result = manifest.get("active_scope_artifact_write_result") or {}
        artifact = plan.get("active_scope_snapshot_artifact") or {}
        if not active_scope_result.get("executed"):
            return {"executed": False, "reason": "active_scope_artifact_not_written"}
        if int(artifact.get("scope_count") or 0) != 0:
            return {"executed": False, "reason": "active_scope_not_empty"}
        return _write_post_close_final_a_pass_done_marker(
            args,
            completion_mode="empty_a_noop",
            active_scope_artifact_path=str(active_scope_result.get("path") or ""),
            evaluated_ref_count=0,
            action_executed_count=0,
            evaluation_only_count=0,
            unprocessed_ref_count=0,
        )

    if phase == "executed" and decision.get("worker_mode") == "post_close_final_a_execute":
        summary = _post_close_final_a_executed_completion_summary(plan)
        if summary["unprocessed_ref_count"] != 0:
            return {
                "executed": False,
                "reason": "active_refs_not_all_evaluated",
                **summary,
            }
        if summary["evaluated_ref_count"] == 0:
            return {"executed": False, "reason": "active_refs_empty_for_executed_marker", **summary}
        return _write_post_close_final_a_pass_done_marker(
            args,
            completion_mode="n5_executed_all_refs_evaluated",
            active_scope_artifact_path=str(getattr(args, "active_scope_artifact_path", "") or ""),
            evaluated_ref_count=summary["evaluated_ref_count"],
            action_executed_count=summary["action_executed_count"],
            evaluation_only_count=summary["evaluation_only_count"],
            unprocessed_ref_count=summary["unprocessed_ref_count"],
        )

    return {"executed": False, "reason": "lane_not_marker_writer"}


def _post_close_final_a_executed_completion_summary(plan: Mapping[str, Any]) -> dict[str, int]:
    active_keys = _post_close_final_a_active_scope_ref_state_keys(plan)
    completed_keys: set[str] = set()
    action_executed_keys: set[str] = set()
    for event in plan.get("action_events") or []:
        if str(event.get("event_type") or "") != "ActionExecuted":
            continue
        state_key = _action_event_state_key(event)
        if state_key:
            action_executed_keys.add(state_key)
            completed_keys.add(state_key)
    for update in plan.get("tracking_updates") or []:
        state_key = str(update.get("state_key") or "")
        if state_key and _tracking_update_has_terminal_or_evaluation_evidence(update):
            completed_keys.add(state_key)
    if not active_keys:
        active_keys = set(completed_keys)
    evaluated_keys = active_keys & completed_keys
    action_keys = active_keys & action_executed_keys
    return {
        "evaluated_ref_count": len(evaluated_keys),
        "action_executed_count": len(action_keys),
        "evaluation_only_count": max(0, len(evaluated_keys) - len(action_keys)),
        "unprocessed_ref_count": len(active_keys - completed_keys),
    }


def _post_close_final_a_active_scope_ref_state_keys(plan: Mapping[str, Any]) -> set[str]:
    artifact = plan.get("active_scope_snapshot_artifact") or {}
    artifact_keys: set[str] = set()
    if isinstance(artifact, Mapping):
        for row in artifact.get("scope_rows") or []:
            if not isinstance(row, Mapping):
                continue
            for ref in row.get("active_tracking_refs") or []:
                if not isinstance(ref, Mapping):
                    continue
                state_key = str(ref.get("state_key") or "").strip()
                if state_key:
                    artifact_keys.add(state_key)
    if artifact_keys:
        return artifact_keys
    return {
        str(row.get("state_key") or "").strip()
        for row in plan.get("active_tracking_rows") or []
        if str(row.get("state_key") or "").strip()
    }


def _action_event_state_key(event: Mapping[str, Any]) -> str:
    payload = event.get("payload_json") or {}
    if isinstance(payload, Mapping):
        trace = payload.get("trace_json") or {}
        if isinstance(trace, Mapping) and str(trace.get("tracking_state_key") or "").strip():
            return str(trace.get("tracking_state_key") or "")
        if str(payload.get("action_key") or "").strip():
            return str(payload.get("action_key") or "")
    return str(event.get("state_key") or "")


def _tracking_update_has_terminal_or_evaluation_evidence(update: Mapping[str, Any]) -> bool:
    if str(update.get("action_state") or "") in {"blocked", "executed", "skipped", "expired"}:
        return True
    if str(update.get("confirmation_status") or "") in {"passed", "failed", "expired"}:
        return True
    raw_json = update.get("raw_json") or {}
    if isinstance(raw_json, Mapping):
        latest_metric_status = raw_json.get("latest_metric_status") or {}
        if isinstance(latest_metric_status, Mapping) and str(latest_metric_status.get("reason") or "") in {
            "metric_before_next_unchecked_minute_label",
            "metric_after_next_unchecked_minute_label",
        }:
            return False
        for key in (
            "latest_metric_status",
            "metric_evaluation_key",
            "last_seen_metric_key",
            "source_action_confirmation_metric_id",
        ):
            if str(raw_json.get(key) or "").strip():
                return True
    for key in ("latest_metric_status", "metric_evaluation_key", "last_seen_metric_key"):
        if str(update.get(key) or "").strip():
            return True
    return False


def _write_post_close_final_a_pass_done_marker(
    args: argparse.Namespace,
    *,
    completion_mode: str,
    active_scope_artifact_path: str,
    evaluated_ref_count: int,
    action_executed_count: int,
    evaluation_only_count: int,
    unprocessed_ref_count: int,
) -> dict[str, Any]:
    path_text = str(getattr(args, "post_close_final_a_pass_done_marker_path", "") or "").strip()
    if not path_text:
        path_text = default_post_close_final_a_pass_done_marker_path(
            for_trade_date=str(getattr(args, "for_trade_date", "") or "")
        )
    path = Path(path_text)
    active_scope_hash = _sha256_file(active_scope_artifact_path) if active_scope_artifact_path else ""
    marker = {
        "artifact_type": POST_CLOSE_FINAL_A_PASS_DONE_ARTIFACT_TYPE,
        "for_trade_date": str(getattr(args, "for_trade_date", "") or ""),
        "status": "done",
        "completion_mode": completion_mode,
        "active_scope_artifact_path": active_scope_artifact_path,
        "active_scope_artifact_sha256": active_scope_hash,
        "evaluated_ref_count": int(evaluated_ref_count),
        "action_executed_count": int(action_executed_count),
        "evaluation_only_count": int(evaluation_only_count),
        "unprocessed_ref_count": int(unprocessed_ref_count),
        "created_at": datetime.now().astimezone().isoformat(),
        "boundary": {
            "n4_outbox_updated": False,
            "n6_touched": False,
            "canonical_minute_bar_1m_written": False,
            "db_marker_table_written": False,
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe_value(marker), ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {
        "executed": True,
        "path": str(path),
        "artifact_type": POST_CLOSE_FINAL_A_PASS_DONE_ARTIFACT_TYPE,
        "completion_mode": completion_mode,
        "evaluated_ref_count": int(evaluated_ref_count),
        "action_executed_count": int(action_executed_count),
        "evaluation_only_count": int(evaluation_only_count),
        "unprocessed_ref_count": int(unprocessed_ref_count),
    }


def _sha256_file(path_text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_manifest(
    args: argparse.Namespace,
    invocation_id: str,
    plan: Mapping[str, Any],
    started: float,
    now_monotonic: Callable[[], float],
) -> dict[str, Any]:
    return {
        "verdict": "N5_LIVE_TRACKING_PLANNED",
        "invocation_id": invocation_id,
        "action_run_id": args.action_run_id,
        "source_trigger_run_id": args.source_trigger_run_id,
        "source_metric_run_id": args.source_metric_run_id,
        "for_trade_date": args.for_trade_date,
        "consumer_name": args.consumer_name,
        "fastlane": {
            "lane_id": args.fastlane_lane_id,
            "phase": args.fastlane_phase,
            "session_phase": getattr(args, "fastlane_session_phase", ""),
            "active_worker_decision": getattr(args, "fastlane_active_worker_decision", {}),
            "trace_only": True,
        },
        "execute_requested": bool(args.execute),
        "writes_enabled": bool(args.execute and args.user_confirmed),
        "artifact_writes_enabled": _active_scope_artifact_writes_enabled(args),
        "bounded": {
            "max_events": int(args.max_events),
            "max_runtime_seconds": float(args.max_runtime_seconds),
            "elapsed_seconds": round(now_monotonic() - started, 6),
        },
        "boundary": {
            "n4_outbox_updated": False,
            "n3_or_n4_fact_modified": False,
            "n6_written_directly": False,
            "market_data_pulled": False,
            "launchd_touched": False,
            "long_running_worker_started": False,
            "output_event_types": list(N5_OUTPUT_EVENT_TYPES),
        },
        "rollback_contract": build_rollback_contract(args.action_run_id, args.consumer_name, plan=plan),
        "plan": plan,
    }


def _default_plan_provider(args: argparse.Namespace) -> dict[str, Any]:
    if not args.dsn:
        raise N5LiveTrackingBlocked("dsn_required_for_default_plan_provider")
    with psycopg.connect(
        args.dsn,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
        connect_timeout=10,
    ) as conn, conn.cursor() as cur:
        executed_batch_candidates = (
            _coerce_fastlane_executed_batch_candidates(args) if _is_fastlane_executed_phase(args) else []
        )
        if executed_batch_candidates:
            return _build_executed_batch_candidate_plan(cur, args, executed_batch_candidates)
        n4_rows = [] if _is_fastlane_executed_phase(args) else _fetch_pending_n4_rows(cur, args)
        repair_n4_rows = (
            []
            if _is_fastlane_executed_phase(args) or not _is_active_set_a_intake(args)
            else _fetch_processed_tsc_true_repair_rows(cur, args)
        )
        explicit_active_scope_tracking = _load_explicit_active_scope_tracking_rows(args)
        if explicit_active_scope_tracking is not None:
            explicit_candidates = _active_scope_rows_to_executed_candidates(args, explicit_active_scope_tracking)
            current_candidates = _rehydrate_active_scope_executed_candidates(cur, args, explicit_candidates)
            active_tracking = [
                dict(candidate["active_tracking_row"])
                for candidate in current_candidates
                if isinstance(candidate.get("active_tracking_row"), Mapping)
            ]
            active_scope_tracking = list(active_tracking)
        else:
            active_tracking = _fetch_active_tracking_rows(cur, args, n4_event_rows=[*n4_rows, *repair_n4_rows])
            active_tracking = _align_fastlane_state_key_target_cursor(args, active_tracking)
            active_scope_tracking = _fetch_active_scope_tracking_rows(cur, args)
        metric_rows = _fetch_metric_rows(cur, args)
        existing_event_keys = _fetch_existing_action_event_keys(cur, args)
    return build_live_tracking_plan(
        n4_event_rows=n4_rows,
        repair_n4_event_rows=repair_n4_rows,
        active_tracking_rows=active_tracking,
        metric_rows=metric_rows,
        action_run_id=args.action_run_id,
        source_trigger_run_id=args.source_trigger_run_id,
        source_metric_run_id=args.source_metric_run_id,
        consumer_name=args.consumer_name,
        existing_action_event_keys=existing_event_keys,
        active_scope_tracking_rows=active_scope_tracking,
        for_trade_date=args.for_trade_date,
    )


def _align_fastlane_state_key_target_cursor(
    args: argparse.Namespace,
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    state_key = str(getattr(args, "fastlane_ref_state_key", "") or "").strip()
    target_minute_label = str(getattr(args, "fastlane_target_minute_label", "") or "").strip()
    if not _is_fastlane_executed_phase(args) or not state_key or not target_minute_label:
        return [dict(row) for row in rows]
    aligned_rows: list[dict[str, Any]] = []
    for row in rows:
        row_dict = dict(row)
        if str(row_dict.get("state_key") or "") == state_key:
            aligned_target = _candidate_minute_label_at_or_after_trigger(
                row_dict,
                target_minute_label,
                for_trade_date=str(getattr(args, "for_trade_date", "") or ""),
            )
            if _candidate_target_precedes_tracking_cursor(
                row_dict,
                aligned_target,
                for_trade_date=str(getattr(args, "for_trade_date", "") or ""),
            ):
                continue
            row_dict = _tracking_row_with_candidate_target_cursor(
                row_dict,
                aligned_target,
                for_trade_date=str(getattr(args, "for_trade_date", "") or ""),
            )
        aligned_rows.append(row_dict)
    return aligned_rows


def _load_explicit_active_scope_tracking_rows(args: argparse.Namespace) -> list[dict[str, Any]] | None:
    if not _is_fastlane_executed_phase(args):
        return None
    path_text = str(getattr(args, "active_scope_artifact_path", "") or "").strip()
    if not path_text:
        return None
    return _load_active_scope_tracking_rows_from_path(Path(path_text), missing_reason="active_scope_artifact_path_missing")


def _load_latest_active_scope_tracking_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    if not _is_fastlane_executed_phase(args):
        return []
    path = _latest_active_scope_artifact_path(args)
    if path is None:
        return []
    return _load_active_scope_tracking_rows_from_path(path, missing_reason="latest_active_scope_artifact_missing")


def _latest_active_scope_artifact_path(args: argparse.Namespace) -> Path | None:
    dirs: list[Path] = []
    configured_dir = str(getattr(args, "active_scope_artifact_dir", "") or "").strip()
    if configured_dir:
        dirs.append(Path(configured_dir))
    trade_date = str(getattr(args, "for_trade_date", "") or "").strip()
    if trade_date:
        dirs.append(Path("docs") / "runtime" / trade_date / "n5_fastlane_active_scope")
    seen: set[str] = set()
    candidates: list[Path] = []
    for directory in dirs:
        directory_key = str(directory)
        if directory_key in seen:
            continue
        seen.add(directory_key)
        if not directory.exists() or not directory.is_dir():
            continue
        candidates.extend(directory.glob("n5_active_scope_snapshot_v1_*.json"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _load_active_scope_tracking_rows_from_path(
    path: Path,
    *,
    missing_reason: str,
) -> list[dict[str, Any]]:
    if not path.exists():
        raise N5LiveTrackingBlocked(missing_reason)
    artifact = json.loads(path.read_text(encoding="utf-8"))
    if str(artifact.get("artifact_type") or "") != "n5_active_scope_snapshot_v1":
        raise N5LiveTrackingBlocked("active_scope_artifact_contract_mismatch")
    rows: list[dict[str, Any]] = []
    grouped_rows: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = {}
    for scope_row in artifact.get("scope_rows") or []:
        if not isinstance(scope_row, Mapping):
            continue
        for ref in scope_row.get("active_tracking_refs") or []:
            if not isinstance(ref, Mapping):
                continue
            row = _tracking_row_from_active_scope_ref(ref, scope_row=scope_row, artifact=artifact)
            if row:
                rows.append(row)
                target_label = _candidate_target_minute_label(row, for_trade_date=str(artifact.get("for_trade_date") or row.get("trade_date") or ""))
                target_hhmm = target_label.replace(":", "")
                if target_hhmm:
                    key = (
                        str(row.get("trade_date") or artifact.get("for_trade_date") or ""),
                        str(row.get("asset_kind") or ""),
                        str(row.get("identity_key") or ""),
                        str(row.get("direction") or ""),
                        target_hhmm,
                    )
                    grouped_rows.setdefault(key, []).append(row)
    for (trade_date, asset_kind, identity_key, direction, target_hhmm), group in grouped_rows.items():
        object_hash = _active_scope_object_minute_source_run_hash(
            trade_date=trade_date,
            asset_kind=asset_kind,
            identity_key=identity_key,
            direction=direction,
            target_hhmm=target_hhmm,
            rows=group,
        )
        if not object_hash:
            continue
        for row in group:
            row["object_minute_source_run_hash"] = object_hash
            raw_json = dict(row.get("raw_json") or {})
            raw_json["object_minute_source_run_hash"] = object_hash
            row["raw_json"] = raw_json
    return rows


def _active_scope_object_minute_source_run_hash(
    *,
    trade_date: str,
    asset_kind: str,
    identity_key: str,
    direction: str,
    target_hhmm: str,
    rows: Sequence[Mapping[str, Any]],
) -> str:
    ref_parts = [
        "|".join(
            str(row.get(key) or (row.get("raw_json") or {}).get(key) or "")
            for key in (
                "source_run_hash",
                "state_key",
                "condition_key",
                "source_trigger_event_id",
                "source_trigger_event_time",
                "latest_n4_event_time",
                "next_unchecked_minute_label",
            )
        )
        for row in rows
        if isinstance(row, Mapping)
    ]
    return _short_scope_hash(
        trade_date,
        asset_kind,
        identity_key,
        direction,
        target_hhmm,
        *sorted(ref_parts),
    )


def _tracking_row_from_active_scope_ref(
    ref: Mapping[str, Any],
    *,
    scope_row: Mapping[str, Any],
    artifact: Mapping[str, Any],
) -> dict[str, Any]:
    row = dict(ref)
    for key in ("trade_date", "asset_kind", "identity_key", "direction", "signal_type"):
        if not str(row.get(key) or "").strip():
            row[key] = scope_row.get(key) or artifact.get(key)
    if not str(row.get("trade_date") or "").strip():
        row["trade_date"] = scope_row.get("for_trade_date") or artifact.get("for_trade_date")
    if not str(row.get("condition_key") or "").strip():
        row["condition_key"] = ref.get("condition_key") or scope_row.get("condition_key") or ""
    if not str(row.get("latest_n4_event_time") or "").strip():
        row["latest_n4_event_time"] = (
            ref.get("source_trigger_event_time")
            or ref.get("trigger_time")
            or ref.get("latest_n4_event_time")
        )
    if not str(row.get("latest_n4_event_id") or "").strip():
        row["latest_n4_event_id"] = ref.get("source_trigger_event_id") or ref.get("latest_n4_event_id")
    if not str(row.get("latest_n4_event_type") or "").strip():
        row["latest_n4_event_type"] = ref.get("source_trigger_event_type") or ref.get("latest_n4_event_type")
    if not str(row.get("run_id") or "").strip():
        row["run_id"] = artifact.get("action_run_id") or artifact.get("run_id") or ""
    row.setdefault("trigger_live", True)
    row.setdefault("current_status", "matched")
    row.setdefault("action_state", "eligible")
    row.setdefault("confirmation_status", "pending")
    row.setdefault("tracking_status", "tracking")
    raw_json = dict(row.get("raw_json") or {})
    if ref.get("source_n4_payload") is not None:
        raw_json.setdefault("source_n4_payload", ref.get("source_n4_payload"))
    if ref.get("next_unchecked_minute_label") is not None:
        raw_json["next_unchecked_minute_label"] = ref.get("next_unchecked_minute_label")
    if ref.get("latest_metric_status") is not None:
        raw_json.setdefault("latest_metric_status", ref.get("latest_metric_status"))
    if ref.get("source_run_hash") is not None:
        raw_json.setdefault("source_run_hash", ref.get("source_run_hash"))
    row["raw_json"] = raw_json
    if not str(row.get("state_key") or "").strip():
        grain = {
            "trade_date": str(row.get("trade_date") or ""),
            "asset_kind": str(row.get("asset_kind") or ""),
            "identity_key": str(row.get("identity_key") or ""),
            "direction": str(row.get("direction") or ""),
            "signal_type": str(row.get("signal_type") or ""),
            "condition_key": str(row.get("condition_key") or ""),
        }
        if not all(grain.values()):
            return {}
        row["state_key"] = build_action_tracking_state_key(**grain)
    return row


def _fetch_pending_n4_rows(cur: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
    if _is_active_set_a_intake(args):
        cur.execute(
            """
            SELECT o.*
            FROM common_event_outbox o
            WHERE o.source_layer = 'N4_trigger'
              AND o.trade_date = %s
              AND o.status = 'pending'
              AND o.event_type = ANY(%s)
              AND NOT EXISTS (
                SELECT 1
                FROM common_event_inbox i
                WHERE i.consumer_name = %s
                  AND i.event_id = o.event_id
              )
            ORDER BY o.event_time, o.source_run_id, o.outbox_id
            LIMIT %s
            """,
            (
                args.for_trade_date,
                list(N4_INPUT_EVENT_TYPES),
                args.consumer_name,
                int(args.max_events),
            ),
        )
        return [dict(row) for row in cur.fetchall()]
    cur.execute(
        """
        SELECT o.*
        FROM common_event_outbox o
        WHERE o.source_layer = 'N4_trigger'
          AND o.source_run_id = %s
          AND o.trade_date = %s
          AND o.status = 'pending'
          AND o.event_type = ANY(%s)
          AND NOT EXISTS (
            SELECT 1
            FROM common_event_inbox i
            WHERE i.consumer_name = %s
              AND i.event_id = o.event_id
          )
        ORDER BY o.event_time, o.outbox_id
        LIMIT %s
        """,
        (
            args.source_trigger_run_id,
            args.for_trade_date,
            list(N4_INPUT_EVENT_TYPES),
            args.consumer_name,
            int(args.max_events),
        ),
    )
    return [dict(row) for row in cur.fetchall()]


def _fetch_processed_tsc_true_repair_rows(cur: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT o.*
        FROM common_event_outbox o
        JOIN common_event_inbox i
          ON i.event_id = o.event_id
         AND i.consumer_name = %s
         AND i.status = 'processed'
        WHERE o.source_layer = 'N4_trigger'
          AND o.trade_date = %s
          AND o.event_type = 'TriggerStateChanged'
          AND lower(coalesce(o.payload_json->>'trigger_live', 'true')) NOT IN ('false', 'f', '0', 'no', 'n')
          AND coalesce(o.payload_json->>'current_status', 'matched') = 'matched'
          AND NOT EXISTS (
            SELECT 1
            FROM common_action_tracking_state t
            WHERE t.trade_date = o.trade_date
              AND t.source_trigger_event_id = o.event_id
              AND t.source_trigger_event_type = 'TriggerStateChanged'
              AND t.action_state = 'eligible'
              AND t.tracking_status = 'tracking'
          )
          AND NOT EXISTS (
            SELECT 1
            FROM common_event_outbox inactive
            WHERE inactive.source_layer = 'N4_trigger'
              AND inactive.trade_date = o.trade_date
              AND inactive.event_type = 'TriggerStateChanged'
              AND inactive.event_time >= o.event_time
              AND inactive.asset_kind = o.asset_kind
              AND inactive.identity_key = o.identity_key
              AND coalesce(inactive.payload_json->>'condition_key', '') = coalesce(o.payload_json->>'condition_key', '')
              AND lower(coalesce(inactive.payload_json->>'trigger_live', 'true')) IN ('false', 'f', '0', 'no', 'n')
          )
        ORDER BY o.event_time, o.source_run_id, o.outbox_id
        LIMIT %s
        """,
        (args.consumer_name, args.for_trade_date, int(args.max_events)),
    )
    return [dict(row) for row in cur.fetchall()]


def _fetch_active_tracking_rows(
    cur: Any,
    args: argparse.Namespace,
    *,
    n4_event_rows: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    ref_state_key = str(getattr(args, "fastlane_ref_state_key", "") or "")
    if _is_fastlane_executed_phase(args) and ref_state_key:
        cur.execute(
            """
            SELECT *
            FROM common_action_tracking_state
            WHERE trade_date = %s
              AND run_id = %s
              AND state_key = %s
              AND action_state = 'eligible'
              AND tracking_status = 'tracking'
            ORDER BY latest_n4_event_time NULLS LAST, run_id, state_key
            """,
            (args.for_trade_date, args.action_run_id, ref_state_key),
        )
        return [dict(row) for row in cur.fetchall()]
    if _is_active_set_a_intake(args):
        state_keys = _n4_event_state_keys(n4_event_rows or [])
        if not state_keys:
            return []
        cur.execute(
            """
            SELECT *
            FROM common_action_tracking_state
            WHERE trade_date = %s
              AND state_key = ANY(%s)
            ORDER BY latest_n4_event_time DESC NULLS LAST, run_id, state_key
            """,
            (args.for_trade_date, state_keys),
        )
        return [dict(row) for row in cur.fetchall()]
    cur.execute(
        """
        SELECT *
        FROM common_action_tracking_state
        WHERE run_id = %s
          AND source_trigger_run_id = %s
          AND trade_date = %s
          AND action_state = 'eligible'
          AND tracking_status = 'tracking'
        ORDER BY latest_n4_event_time NULLS LAST, state_key
        """,
        (args.action_run_id, args.source_trigger_run_id, args.for_trade_date),
    )
    rows = [dict(row) for row in cur.fetchall()]
    inactive_state_keys = _inactive_state_change_keys(n4_event_rows or [])
    existing_keys = {str(row.get("state_key") or "") for row in rows}
    missing_keys = [key for key in inactive_state_keys if key and key not in existing_keys]
    if missing_keys:
        cur.execute(
            """
            SELECT *
            FROM common_action_tracking_state
            WHERE trade_date = %s
              AND state_key = ANY(%s)
              AND action_state = 'eligible'
              AND tracking_status = 'tracking'
            ORDER BY latest_n4_event_time NULLS LAST, run_id, state_key
            """,
            (args.for_trade_date, missing_keys),
        )
        for row in cur.fetchall():
            row_dict = dict(row)
            key = str(row_dict.get("state_key") or "")
            if key and key not in existing_keys:
                rows.append(row_dict)
                existing_keys.add(key)
    return rows


def _fetch_active_tracking_rows_by_state_keys(
    cur: Any,
    args: argparse.Namespace,
    *,
    action_run_id: str,
    state_keys: Sequence[str],
) -> list[dict[str, Any]]:
    keys = [str(key).strip() for key in state_keys if str(key).strip()]
    if not keys:
        return []
    cur.execute(
        """
        SELECT *
        FROM common_action_tracking_state
        WHERE trade_date = %s
          AND run_id = %s
          AND state_key = ANY(%s)
          AND action_state = 'eligible'
          AND tracking_status = 'tracking'
          AND coalesce(trigger_live, false) = true
          AND current_status = 'matched'
        ORDER BY latest_n4_event_time NULLS LAST, run_id, state_key
        """,
        (args.for_trade_date, action_run_id, keys),
    )
    return [dict(row) for row in cur.fetchall()]


def _n4_event_state_keys(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    keys: set[str] = set()
    for row in rows:
        event_type = str(row.get("event_type") or "")
        if event_type not in N4_INPUT_EVENT_TYPES:
            continue
        payload = _event_payload(row)
        signal_type = str(_event_value(row, payload, "signal_type") or "")
        direction = str(_event_value(row, payload, "direction") or "")
        if not direction:
            direction = "buy" if signal_type == "B_BUY" else "sell" if signal_type == "S_SELL" else ""
        grain = {
            "trade_date": str(_event_value(row, payload, "trade_date", "for_trade_date") or ""),
            "asset_kind": str(_event_value(row, payload, "asset_kind") or ""),
            "identity_key": str(_event_value(row, payload, "identity_key") or ""),
            "direction": direction,
            "signal_type": signal_type,
            "condition_key": str(_event_value(row, payload, "condition_key", "original_condition_key") or ""),
        }
        if all(grain.values()):
            keys.add(build_action_tracking_state_key(**grain))
    return sorted(keys)


def _fetch_active_scope_tracking_rows(cur: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT *
        FROM common_action_tracking_state
        WHERE trade_date = %s
          AND action_state = 'eligible'
          AND tracking_status = 'tracking'
          AND coalesce(trigger_live, false) = true
          AND current_status = 'matched'
        ORDER BY latest_n4_event_time NULLS LAST, run_id, state_key
        """,
        (args.for_trade_date,),
    )
    return [dict(row) for row in cur.fetchall()]


def _inactive_state_change_keys(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    keys: set[str] = set()
    for row in rows:
        if str(row.get("event_type") or "") != "TriggerStateChanged":
            continue
        payload = _event_payload(row)
        if _bool_value(_event_value(row, payload, "trigger_live"), default=True):
            continue
        signal_type = str(_event_value(row, payload, "signal_type") or "")
        direction = str(_event_value(row, payload, "direction") or "")
        if not direction:
            direction = "buy" if signal_type == "B_BUY" else "sell" if signal_type == "S_SELL" else ""
        grain = {
            "trade_date": str(_event_value(row, payload, "trade_date", "for_trade_date") or ""),
            "asset_kind": str(_event_value(row, payload, "asset_kind") or ""),
            "identity_key": str(_event_value(row, payload, "identity_key") or ""),
            "direction": direction,
            "signal_type": signal_type,
            "condition_key": str(_event_value(row, payload, "condition_key", "original_condition_key") or ""),
        }
        if all(grain.values()):
            keys.add(build_action_tracking_state_key(**grain))
    return sorted(keys)


def _event_payload(row: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = row.get("payload_json") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    return payload if isinstance(payload, Mapping) else {}


def _event_value(row: Mapping[str, Any], payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is not None and value != "":
            return value
        value = row.get(key)
        if value is not None and value != "":
            return value
    return None


def _bool_value(value: Any, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "t", "1", "yes", "y"}:
        return True
    if text in {"false", "f", "0", "no", "n"}:
        return False
    return default


def _fetch_metric_rows(cur: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
    from ashare_v3.action.execute import fetch_action_confirmation_metric_rows_by_run_id

    return fetch_action_confirmation_metric_rows_by_run_id(cur, args.source_metric_run_id)


def _fetch_existing_action_event_keys(cur: Any, args: argparse.Namespace) -> set[str]:
    cur.execute(
        """
        SELECT dedup_key
        FROM common_event_outbox
        WHERE source_layer = 'N5_action'
          AND source_run_id = %s
          AND event_type = ANY(%s)
        """,
        (args.action_run_id, list(N5_OUTPUT_EVENT_TYPES)),
    )
    return {str(row["dedup_key"]) for row in cur.fetchall() if row.get("dedup_key")}


def _default_execute_writer(args: argparse.Namespace, plan: Mapping[str, Any]) -> dict[str, Any]:
    if not args.dsn:
        raise N5LiveTrackingBlocked("dsn_required_for_execute")
    for attempt in range(TRACKING_WRITE_DEADLOCK_RETRY_LIMIT):
        try:
            with psycopg.connect(args.dsn, row_factory=dict_row, connect_timeout=10) as conn:
                with conn.cursor() as cur:
                    tracking_count = _upsert_tracking_states(cur, plan.get("tracking_updates") or [])
                    action_events = list(plan.get("action_events") or [])
                    outbox_count = _insert_action_outbox_events(cur, action_events)
                    proof_to_action_ms = _proof_to_action_latency_ms(cur, action_events)
                    consumed_n4_events = [] if _is_fastlane_executed_phase(args) else list(plan.get("consumed_n4_events") or [])
                    inbox_count = _insert_inbox_rows(cur, consumed_n4_events, args) if consumed_n4_events else 0
                    checkpoint_count = _upsert_checkpoints(cur, consumed_n4_events, args) if consumed_n4_events else 0
                conn.commit()
            return {
                "executed": True,
                "common_action_tracking_state": tracking_count,
                "common_event_outbox": outbox_count,
                "common_event_inbox": inbox_count,
                "common_event_consumer_checkpoint": checkpoint_count,
                "n4_outbox_status_updated": False,
                "proof_to_action_ms": proof_to_action_ms,
            }
        except psycopg.errors.DeadlockDetected:
            if attempt + 1 >= TRACKING_WRITE_DEADLOCK_RETRY_LIMIT:
                raise
            time.sleep(TRACKING_WRITE_DEADLOCK_RETRY_DELAYS_SECONDS[attempt])
    raise AssertionError("unreachable")


def _proof_to_action_latency_ms(cur: Any, events: Sequence[Mapping[str, Any]]) -> int | None:
    observed_at = datetime.now().astimezone()
    references_by_table: dict[str, set[tuple[str, str]]] = {}
    for event in events:
        if str(event.get("event_type") or "") != "ActionExecuted":
            continue
        payload = event.get("payload_json") if isinstance(event.get("payload_json"), Mapping) else {}
        source_metric_run_id = str(payload.get("source_metric_run_id") or "").strip()
        asset_kind = str(event.get("asset_kind") or payload.get("asset_kind") or "").strip()
        identity_key = str(event.get("identity_key") or payload.get("identity_key") or "").strip()
        table_name = N3T_ACTION_CONFIRMATION_METRIC_TABLES_BY_ASSET_KIND.get(asset_kind)
        if source_metric_run_id and identity_key and table_name:
            references_by_table.setdefault(table_name, set()).add((source_metric_run_id, identity_key))

    values: list[int] = []
    for table_name, references in references_by_table.items():
        run_ids = sorted({run_id for run_id, _identity_key in references})
        identity_keys = sorted({identity_key for _run_id, identity_key in references})
        cur.execute(
            f"""
            SELECT projection_run_id, identity_key, max(created_at) AS proof_created_at
            FROM {table_name}
            WHERE projection_run_id = ANY(%s)
              AND identity_key = ANY(%s)
              AND source_basis = 'N3T_C1_CLOSED'
            GROUP BY projection_run_id, identity_key
            """,
            (run_ids, identity_keys),
        )
        for row in cur.fetchall():
            reference = (str(row.get("projection_run_id") or ""), str(row.get("identity_key") or ""))
            proof_created_at = row.get("proof_created_at")
            if reference not in references or proof_created_at is None:
                continue
            values.append(max(0, int(round((observed_at - proof_created_at).total_seconds() * 1000))))
    return max(values) if values else None


def _upsert_tracking_states(cur: Any, rows: Sequence[Mapping[str, Any]]) -> int:
    if not rows:
        return 0
    ordered_rows = sorted(
        rows,
        key=lambda row: (str(row.get("run_id") or ""), str(row.get("state_key") or "")),
    )
    values = [_tracking_values(row) for row in ordered_rows]
    cur.executemany(
        """
        INSERT INTO common_action_tracking_state (
          run_id, source_trigger_run_id, source_trigger_state_id,
          source_trigger_event_id, source_trigger_event_type, source_trigger_match_id,
          trade_date, state_key, asset_kind, identity_key, direction, signal_type,
          condition_key, trigger_live, current_status, primary_trigger_period,
          all_trigger_periods, trigger_mark_candidate, latest_n4_event_id,
          latest_n4_event_type, latest_n4_event_time, action_state,
          confirmation_status, tracking_status, planned_output_event_type,
          expired_reason, expired_at, tracking_until, last_checked_minute_label,
          monitor_window_id, trigger_type, triggered_periods, trigger_context_version,
          raw_json, updated_at
        )
        VALUES (
          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
          %s, %s, now()
        )
        ON CONFLICT (run_id, state_key)
        DO UPDATE SET
          source_trigger_event_id = CASE
            WHEN EXCLUDED.latest_n4_event_time IS NULL THEN common_action_tracking_state.source_trigger_event_id
            WHEN common_action_tracking_state.latest_n4_event_time IS NULL
              OR EXCLUDED.latest_n4_event_time >= common_action_tracking_state.latest_n4_event_time
              THEN EXCLUDED.source_trigger_event_id
            ELSE common_action_tracking_state.source_trigger_event_id
          END,
          source_trigger_event_type = CASE
            WHEN EXCLUDED.latest_n4_event_time IS NULL THEN common_action_tracking_state.source_trigger_event_type
            WHEN common_action_tracking_state.latest_n4_event_time IS NULL
              OR EXCLUDED.latest_n4_event_time >= common_action_tracking_state.latest_n4_event_time
              THEN EXCLUDED.source_trigger_event_type
            ELSE common_action_tracking_state.source_trigger_event_type
          END,
          source_trigger_match_id = CASE
            WHEN EXCLUDED.latest_n4_event_time IS NULL THEN common_action_tracking_state.source_trigger_match_id
            WHEN common_action_tracking_state.latest_n4_event_time IS NULL
              OR EXCLUDED.latest_n4_event_time >= common_action_tracking_state.latest_n4_event_time
              THEN COALESCE(EXCLUDED.source_trigger_match_id, common_action_tracking_state.source_trigger_match_id)
            ELSE common_action_tracking_state.source_trigger_match_id
          END,
          trigger_live = CASE
            WHEN EXCLUDED.latest_n4_event_time IS NULL THEN common_action_tracking_state.trigger_live
            WHEN common_action_tracking_state.latest_n4_event_time IS NULL
              OR EXCLUDED.latest_n4_event_time >= common_action_tracking_state.latest_n4_event_time
              THEN EXCLUDED.trigger_live
            ELSE common_action_tracking_state.trigger_live
          END,
          current_status = CASE
            WHEN EXCLUDED.latest_n4_event_time IS NULL THEN common_action_tracking_state.current_status
            WHEN common_action_tracking_state.latest_n4_event_time IS NULL
              OR EXCLUDED.latest_n4_event_time >= common_action_tracking_state.latest_n4_event_time
              THEN EXCLUDED.current_status
            ELSE common_action_tracking_state.current_status
          END,
          primary_trigger_period = CASE
            WHEN EXCLUDED.latest_n4_event_time IS NULL THEN common_action_tracking_state.primary_trigger_period
            WHEN common_action_tracking_state.latest_n4_event_time IS NULL
              OR EXCLUDED.latest_n4_event_time >= common_action_tracking_state.latest_n4_event_time
              THEN EXCLUDED.primary_trigger_period
            ELSE common_action_tracking_state.primary_trigger_period
          END,
          all_trigger_periods = CASE
            WHEN EXCLUDED.latest_n4_event_time IS NULL THEN common_action_tracking_state.all_trigger_periods
            WHEN common_action_tracking_state.latest_n4_event_time IS NULL
              OR EXCLUDED.latest_n4_event_time >= common_action_tracking_state.latest_n4_event_time
              THEN EXCLUDED.all_trigger_periods
            ELSE common_action_tracking_state.all_trigger_periods
          END,
          trigger_mark_candidate = CASE
            WHEN EXCLUDED.latest_n4_event_time IS NULL THEN common_action_tracking_state.trigger_mark_candidate
            WHEN common_action_tracking_state.latest_n4_event_time IS NULL
              OR EXCLUDED.latest_n4_event_time >= common_action_tracking_state.latest_n4_event_time
              THEN EXCLUDED.trigger_mark_candidate
            ELSE common_action_tracking_state.trigger_mark_candidate
          END,
          latest_n4_event_id = CASE
            WHEN EXCLUDED.latest_n4_event_time IS NULL THEN common_action_tracking_state.latest_n4_event_id
            WHEN common_action_tracking_state.latest_n4_event_time IS NULL
              OR EXCLUDED.latest_n4_event_time >= common_action_tracking_state.latest_n4_event_time
              THEN EXCLUDED.latest_n4_event_id
            ELSE common_action_tracking_state.latest_n4_event_id
          END,
          latest_n4_event_type = CASE
            WHEN EXCLUDED.latest_n4_event_time IS NULL THEN common_action_tracking_state.latest_n4_event_type
            WHEN common_action_tracking_state.latest_n4_event_time IS NULL
              OR EXCLUDED.latest_n4_event_time >= common_action_tracking_state.latest_n4_event_time
              THEN EXCLUDED.latest_n4_event_type
            ELSE common_action_tracking_state.latest_n4_event_type
          END,
          latest_n4_event_time = CASE
            WHEN EXCLUDED.latest_n4_event_time IS NULL THEN common_action_tracking_state.latest_n4_event_time
            WHEN common_action_tracking_state.latest_n4_event_time IS NULL
              OR EXCLUDED.latest_n4_event_time >= common_action_tracking_state.latest_n4_event_time
              THEN EXCLUDED.latest_n4_event_time
            ELSE common_action_tracking_state.latest_n4_event_time
          END,
          action_state = CASE
            WHEN EXCLUDED.action_state = 'executed' THEN EXCLUDED.action_state
            WHEN common_action_tracking_state.action_state IN ('expired', 'executed')
              AND EXCLUDED.action_state = 'eligible'
              AND COALESCE(EXCLUDED.raw_json->>'terminal_ref_reopen_allowed', 'false') = 'true'
              AND EXCLUDED.source_trigger_event_type = 'TriggerMatched'
              AND EXCLUDED.source_trigger_event_id IS DISTINCT FROM common_action_tracking_state.source_trigger_event_id
              AND (
                common_action_tracking_state.action_state = 'expired'
                OR (
                  common_action_tracking_state.action_state = 'executed'
                  AND COALESCE(
                    EXCLUDED.raw_json->'terminal_episode_inactive_boundary'->>'source_trigger_event_type',
                    ''
                  ) = 'TriggerStateChanged'
                  AND lower(COALESCE(
                    EXCLUDED.raw_json->'terminal_episode_inactive_boundary'->>'trigger_live',
                    'true'
                  )) IN ('false', 'f', '0', 'no', 'n')
                  AND COALESCE(
                    EXCLUDED.raw_json->'terminal_episode_inactive_boundary'->>'source_trigger_event_id',
                    ''
                  ) <> ''
                  AND COALESCE(
                    EXCLUDED.raw_json->'terminal_episode_inactive_boundary'->>'closed_source_trigger_event_id',
                    ''
                  ) = common_action_tracking_state.source_trigger_event_id
                )
              )
              AND (
                common_action_tracking_state.latest_n4_event_time IS NULL
                OR EXCLUDED.latest_n4_event_time >= common_action_tracking_state.latest_n4_event_time
              )
              THEN EXCLUDED.action_state
            WHEN common_action_tracking_state.action_state = 'executed' THEN common_action_tracking_state.action_state
            WHEN common_action_tracking_state.action_state IN ('blocked', 'skipped', 'expired') THEN common_action_tracking_state.action_state
            ELSE EXCLUDED.action_state
          END,
          confirmation_status = CASE
            WHEN EXCLUDED.action_state = 'executed' THEN EXCLUDED.confirmation_status
            WHEN common_action_tracking_state.action_state IN ('expired', 'executed')
              AND EXCLUDED.action_state = 'eligible'
              AND COALESCE(EXCLUDED.raw_json->>'terminal_ref_reopen_allowed', 'false') = 'true'
              AND EXCLUDED.source_trigger_event_type = 'TriggerMatched'
              AND EXCLUDED.source_trigger_event_id IS DISTINCT FROM common_action_tracking_state.source_trigger_event_id
              AND (
                common_action_tracking_state.action_state = 'expired'
                OR (
                  common_action_tracking_state.action_state = 'executed'
                  AND COALESCE(
                    EXCLUDED.raw_json->'terminal_episode_inactive_boundary'->>'source_trigger_event_type',
                    ''
                  ) = 'TriggerStateChanged'
                  AND lower(COALESCE(
                    EXCLUDED.raw_json->'terminal_episode_inactive_boundary'->>'trigger_live',
                    'true'
                  )) IN ('false', 'f', '0', 'no', 'n')
                  AND COALESCE(
                    EXCLUDED.raw_json->'terminal_episode_inactive_boundary'->>'source_trigger_event_id',
                    ''
                  ) <> ''
                  AND COALESCE(
                    EXCLUDED.raw_json->'terminal_episode_inactive_boundary'->>'closed_source_trigger_event_id',
                    ''
                  ) = common_action_tracking_state.source_trigger_event_id
                )
              )
              AND (
                common_action_tracking_state.latest_n4_event_time IS NULL
                OR EXCLUDED.latest_n4_event_time >= common_action_tracking_state.latest_n4_event_time
              )
              THEN EXCLUDED.confirmation_status
            WHEN common_action_tracking_state.action_state = 'executed' THEN common_action_tracking_state.confirmation_status
            WHEN common_action_tracking_state.action_state IN ('blocked', 'skipped', 'expired') THEN common_action_tracking_state.confirmation_status
            ELSE EXCLUDED.confirmation_status
          END,
          tracking_status = CASE
            WHEN EXCLUDED.action_state = 'executed' THEN EXCLUDED.tracking_status
            WHEN common_action_tracking_state.action_state IN ('expired', 'executed')
              AND EXCLUDED.action_state = 'eligible'
              AND COALESCE(EXCLUDED.raw_json->>'terminal_ref_reopen_allowed', 'false') = 'true'
              AND EXCLUDED.source_trigger_event_type = 'TriggerMatched'
              AND EXCLUDED.source_trigger_event_id IS DISTINCT FROM common_action_tracking_state.source_trigger_event_id
              AND (
                common_action_tracking_state.action_state = 'expired'
                OR (
                  common_action_tracking_state.action_state = 'executed'
                  AND COALESCE(
                    EXCLUDED.raw_json->'terminal_episode_inactive_boundary'->>'source_trigger_event_type',
                    ''
                  ) = 'TriggerStateChanged'
                  AND lower(COALESCE(
                    EXCLUDED.raw_json->'terminal_episode_inactive_boundary'->>'trigger_live',
                    'true'
                  )) IN ('false', 'f', '0', 'no', 'n')
                  AND COALESCE(
                    EXCLUDED.raw_json->'terminal_episode_inactive_boundary'->>'source_trigger_event_id',
                    ''
                  ) <> ''
                  AND COALESCE(
                    EXCLUDED.raw_json->'terminal_episode_inactive_boundary'->>'closed_source_trigger_event_id',
                    ''
                  ) = common_action_tracking_state.source_trigger_event_id
                )
              )
              AND (
                common_action_tracking_state.latest_n4_event_time IS NULL
                OR EXCLUDED.latest_n4_event_time >= common_action_tracking_state.latest_n4_event_time
              )
              THEN EXCLUDED.tracking_status
            WHEN common_action_tracking_state.action_state = 'executed' THEN common_action_tracking_state.tracking_status
            WHEN common_action_tracking_state.action_state IN ('blocked', 'skipped', 'expired') THEN common_action_tracking_state.tracking_status
            ELSE EXCLUDED.tracking_status
          END,
          planned_output_event_type = EXCLUDED.planned_output_event_type,
          expired_reason = EXCLUDED.expired_reason,
          expired_at = EXCLUDED.expired_at,
          tracking_until = EXCLUDED.tracking_until,
          last_checked_minute_label = CASE
            WHEN EXCLUDED.action_state = 'executed' THEN EXCLUDED.last_checked_minute_label
            WHEN common_action_tracking_state.action_state IN ('expired', 'executed')
              AND EXCLUDED.action_state = 'eligible'
              AND COALESCE(EXCLUDED.raw_json->>'terminal_ref_reopen_allowed', 'false') = 'true'
              AND EXCLUDED.source_trigger_event_type = 'TriggerMatched'
              AND EXCLUDED.source_trigger_event_id IS DISTINCT FROM common_action_tracking_state.source_trigger_event_id
              AND (
                common_action_tracking_state.action_state = 'expired'
                OR (
                  common_action_tracking_state.action_state = 'executed'
                  AND COALESCE(
                    EXCLUDED.raw_json->'terminal_episode_inactive_boundary'->>'source_trigger_event_type',
                    ''
                  ) = 'TriggerStateChanged'
                  AND lower(COALESCE(
                    EXCLUDED.raw_json->'terminal_episode_inactive_boundary'->>'trigger_live',
                    'true'
                  )) IN ('false', 'f', '0', 'no', 'n')
                  AND COALESCE(
                    EXCLUDED.raw_json->'terminal_episode_inactive_boundary'->>'source_trigger_event_id',
                    ''
                  ) <> ''
                  AND COALESCE(
                    EXCLUDED.raw_json->'terminal_episode_inactive_boundary'->>'closed_source_trigger_event_id',
                    ''
                  ) = common_action_tracking_state.source_trigger_event_id
                )
              )
              AND (
                common_action_tracking_state.latest_n4_event_time IS NULL
                OR EXCLUDED.latest_n4_event_time >= common_action_tracking_state.latest_n4_event_time
              )
              THEN EXCLUDED.last_checked_minute_label
            WHEN common_action_tracking_state.action_state IN ('executed', 'blocked', 'skipped', 'expired')
              THEN common_action_tracking_state.last_checked_minute_label
            WHEN EXCLUDED.latest_n4_event_time IS NOT NULL
              AND (
                common_action_tracking_state.latest_n4_event_time IS NULL
                OR EXCLUDED.latest_n4_event_time > common_action_tracking_state.latest_n4_event_time
              )
              THEN EXCLUDED.last_checked_minute_label
            WHEN COALESCE(EXCLUDED.last_checked_minute_label, '') = ''
              THEN common_action_tracking_state.last_checked_minute_label
            WHEN COALESCE(common_action_tracking_state.last_checked_minute_label, '') = ''
              THEN EXCLUDED.last_checked_minute_label
            WHEN EXCLUDED.last_checked_minute_label >= common_action_tracking_state.last_checked_minute_label
              THEN EXCLUDED.last_checked_minute_label
            ELSE common_action_tracking_state.last_checked_minute_label
          END,
          monitor_window_id = EXCLUDED.monitor_window_id,
          trigger_type = EXCLUDED.trigger_type,
          triggered_periods = EXCLUDED.triggered_periods,
          trigger_context_version = EXCLUDED.trigger_context_version,
          raw_json = CASE
            WHEN EXCLUDED.action_state = 'executed' THEN EXCLUDED.raw_json
            WHEN common_action_tracking_state.action_state IN ('expired', 'executed')
              AND EXCLUDED.action_state = 'eligible'
              AND COALESCE(EXCLUDED.raw_json->>'terminal_ref_reopen_allowed', 'false') = 'true'
              AND EXCLUDED.source_trigger_event_type = 'TriggerMatched'
              AND EXCLUDED.source_trigger_event_id IS DISTINCT FROM common_action_tracking_state.source_trigger_event_id
              AND (
                common_action_tracking_state.action_state = 'expired'
                OR (
                  common_action_tracking_state.action_state = 'executed'
                  AND COALESCE(
                    EXCLUDED.raw_json->'terminal_episode_inactive_boundary'->>'source_trigger_event_type',
                    ''
                  ) = 'TriggerStateChanged'
                  AND lower(COALESCE(
                    EXCLUDED.raw_json->'terminal_episode_inactive_boundary'->>'trigger_live',
                    'true'
                  )) IN ('false', 'f', '0', 'no', 'n')
                  AND COALESCE(
                    EXCLUDED.raw_json->'terminal_episode_inactive_boundary'->>'source_trigger_event_id',
                    ''
                  ) <> ''
                  AND COALESCE(
                    EXCLUDED.raw_json->'terminal_episode_inactive_boundary'->>'closed_source_trigger_event_id',
                    ''
                  ) = common_action_tracking_state.source_trigger_event_id
                )
              )
              AND (
                common_action_tracking_state.latest_n4_event_time IS NULL
                OR EXCLUDED.latest_n4_event_time >= common_action_tracking_state.latest_n4_event_time
              )
              THEN EXCLUDED.raw_json
            WHEN common_action_tracking_state.action_state IN ('executed', 'blocked', 'skipped', 'expired')
              THEN common_action_tracking_state.raw_json
            WHEN EXCLUDED.latest_n4_event_time IS NOT NULL
              AND (
                common_action_tracking_state.latest_n4_event_time IS NULL
                OR EXCLUDED.latest_n4_event_time > common_action_tracking_state.latest_n4_event_time
              )
              THEN EXCLUDED.raw_json
            WHEN COALESCE(EXCLUDED.last_checked_minute_label, '') = ''
              THEN common_action_tracking_state.raw_json
            WHEN COALESCE(common_action_tracking_state.last_checked_minute_label, '') = ''
              THEN EXCLUDED.raw_json
            WHEN EXCLUDED.last_checked_minute_label >= common_action_tracking_state.last_checked_minute_label
              THEN EXCLUDED.raw_json
            ELSE common_action_tracking_state.raw_json
          END,
          updated_at = now()
        """,
        values,
    )
    return len({(row.get("run_id"), row.get("state_key")) for row in rows})


def _tracking_values(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("run_id"),
        row.get("source_trigger_run_id"),
        _int_or_none(row.get("source_trigger_state_id")),
        row.get("source_trigger_event_id"),
        row.get("source_trigger_event_type"),
        _int_or_none(row.get("source_trigger_match_id")),
        row.get("trade_date"),
        row.get("state_key"),
        row.get("asset_kind"),
        row.get("identity_key"),
        row.get("direction"),
        row.get("signal_type"),
        row.get("condition_key"),
        bool(row.get("trigger_live")),
        row.get("current_status"),
        row.get("primary_trigger_period") or "D",
        _jsonb(list(row.get("all_trigger_periods") or [])),
        row.get("trigger_mark_candidate"),
        row.get("latest_n4_event_id"),
        row.get("latest_n4_event_type"),
        row.get("latest_n4_event_time"),
        row.get("action_state"),
        row.get("confirmation_status"),
        row.get("tracking_status"),
        row.get("planned_output_event_type"),
        row.get("expired_reason"),
        row.get("expired_at"),
        row.get("tracking_until"),
        row.get("last_checked_minute_label"),
        _monitor_window_id(row),
        _trigger_type(row),
        _jsonb(_triggered_periods(row)),
        _trigger_context_version(row),
        _jsonb(dict(row.get("raw_json") or {})),
    )


def _monitor_window_id(row: Mapping[str, Any]) -> str:
    existing = str(row.get("monitor_window_id") or "").strip()
    if existing:
        return existing
    run_id = str(row.get("run_id") or "").strip()
    state_key = str(row.get("state_key") or "").strip()
    if not run_id or not state_key:
        raise N5LiveTrackingBlocked("tracking_monitor_window_id_source_missing")
    return f"{TRACKING_MONITOR_WINDOW_ID_PREFIX}|action_run_id|{run_id}|state_key|{state_key}"


def _trigger_type(row: Mapping[str, Any]) -> str:
    existing = str(row.get("trigger_type") or "").strip()
    if existing in SCHEMA_ALLOWED_TRACKING_TRIGGER_TYPES:
        return existing
    condition_key = str(row.get("condition_key") or "").strip().upper()
    signal_type = str(row.get("signal_type") or "").strip().upper()
    if condition_key.startswith("BUY_HINT"):
        return "BUY_HINT"
    if condition_key.startswith("SELL_HINT"):
        return "SELL_HINT"
    if condition_key.startswith("BUY:FULL") or condition_key.startswith("BUY_FULL"):
        return "BUY:FULL"
    if condition_key.startswith("SELL:FULL") or condition_key.startswith("SELL_FULL"):
        return "SELL:FULL"
    if condition_key.startswith("BUY") or signal_type == "B_BUY":
        return "BUY"
    if condition_key.startswith("SELL") or signal_type == "S_SELL":
        return "SELL"
    raise N5LiveTrackingBlocked("tracking_trigger_type_required")


def _trigger_context_version(row: Mapping[str, Any]) -> str:
    return str(row.get("trigger_context_version") or N5_LIVE_TRACKING_SCHEMA_VERSION)


def _triggered_periods(row: Mapping[str, Any]) -> list[str]:
    periods = _period_list(row.get("triggered_periods")) or _period_list(row.get("all_trigger_periods"))
    if not periods:
        periods = _period_list(row.get("primary_trigger_period"))
    if not periods:
        raise N5LiveTrackingBlocked("tracking_triggered_periods_required")
    return periods


def _period_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                return _period_list(json.loads(stripped))
            except json.JSONDecodeError:
                return [stripped]
        return [stripped]
    if isinstance(value, Mapping):
        return []
    if isinstance(value, Sequence):
        return [str(item) for item in value if item is not None and str(item) != ""]
    return [str(value)]


def _insert_action_outbox_events(cur: Any, events: Sequence[Mapping[str, Any]]) -> int:
    if not events:
        return 0
    cur.executemany(
        """
        INSERT INTO common_event_outbox (
          event_id, event_type, event_schema_version, trade_date,
          asset_kind, identity_key, event_time, source_layer, source_run_id,
          dedup_key, partition_key, payload_json, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (event_id) DO UPDATE SET
          payload_json = EXCLUDED.payload_json,
          event_time = EXCLUDED.event_time,
          partition_key = EXCLUDED.partition_key,
          updated_at = now()
        """,
        [
            (
                event.get("event_id"),
                event.get("event_type"),
                event.get("event_schema_version"),
                event.get("trade_date"),
                event.get("asset_kind"),
                event.get("identity_key"),
                event.get("event_time"),
                event.get("source_layer"),
                event.get("source_run_id"),
                event.get("dedup_key"),
                event.get("partition_key"),
                _jsonb(dict(event.get("payload_json") or {})),
            )
            for event in events
        ],
    )
    return len(events)


def _insert_inbox_rows(cur: Any, rows: Sequence[Mapping[str, Any]], args: argparse.Namespace) -> int:
    if not rows:
        return 0
    cur.executemany(
        """
        INSERT INTO common_event_inbox (
          consumer_name, event_id, event_type, event_schema_version,
          source_layer, source_run_id, dedup_key, partition_key,
          payload_json, status, attempt_count, processed_at, raw_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'processed', 0, now(), %s)
        ON CONFLICT (consumer_name, event_id) DO NOTHING
        """,
        [
            (
                args.consumer_name,
                row.get("event_id"),
                row.get("event_type"),
                row.get("event_schema_version"),
                row.get("source_layer"),
                row.get("source_run_id"),
                row.get("dedup_key"),
                row.get("partition_key") or row.get("identity_key"),
                _jsonb(dict(row.get("payload_json") or {})),
                _jsonb({"action_run_id": args.action_run_id, "source_metric_run_id": args.source_metric_run_id}),
            )
            for row in rows
        ],
    )
    return len(rows)


def _upsert_checkpoints(cur: Any, rows: Sequence[Mapping[str, Any]], args: argparse.Namespace) -> int:
    checkpoint_rows = _checkpoint_rows(rows, args)
    if not checkpoint_rows:
        return 0
    cur.executemany(
        """
        INSERT INTO common_event_consumer_checkpoint (
          consumer_name, partition_key, source_layer, last_event_id,
          last_event_time, last_outbox_id, checkpoint_payload, updated_at
        )
        VALUES (%s, %s, 'N4_trigger', %s, %s, %s, %s, now())
        ON CONFLICT (consumer_name, partition_key, source_layer)
        DO UPDATE SET
          last_event_id = EXCLUDED.last_event_id,
          last_event_time = EXCLUDED.last_event_time,
          last_outbox_id = EXCLUDED.last_outbox_id,
          checkpoint_payload = EXCLUDED.checkpoint_payload,
          updated_at = now()
        WHERE common_event_consumer_checkpoint.last_outbox_id IS NULL
           OR EXCLUDED.last_outbox_id > common_event_consumer_checkpoint.last_outbox_id
        """,
        checkpoint_rows,
    )
    return len(checkpoint_rows)


def _checkpoint_rows(rows: Sequence[Mapping[str, Any]], args: argparse.Namespace) -> list[tuple[Any, ...]]:
    latest: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        partition_key = str(row.get("partition_key") or row.get("identity_key") or "")
        if not partition_key:
            continue
        prior = latest.get(partition_key)
        if prior is None or int(row.get("outbox_id") or 0) >= int(prior.get("outbox_id") or 0):
            latest[partition_key] = row
    return [
        (
            args.consumer_name,
            partition_key,
            row.get("event_id"),
            row.get("event_time"),
            row.get("outbox_id"),
            _jsonb(
                {
                    "action_run_id": args.action_run_id,
                    "source_trigger_run_id": args.source_trigger_run_id,
                    "source_metric_run_id": args.source_metric_run_id,
                }
            ),
        )
        for partition_key, row in sorted(latest.items())
    ]


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def build_rollback_contract(
    action_run_id: str,
    consumer_name: str,
    *,
    plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    affected_tracking_run_ids = _affected_tracking_run_ids(action_run_id, plan or {})
    requires_tracking_restore = any(run_id != action_run_id for run_id in affected_tracking_run_ids)
    return {
        "scope": "N5 only",
        "action_run_id": action_run_id,
        "affected_tracking_run_ids": affected_tracking_run_ids,
        "requires_tracking_restore": requires_tracking_restore,
        "tracking_restore_source": "tracking_updates.raw_json.rollback_before_tracking_state"
        if requires_tracking_restore
        else "",
        "consumer_name": consumer_name,
        "deletes_only": [
            "common_event_consumer_checkpoint by consumer_name and checkpoint_payload.action_run_id",
            "common_event_inbox by consumer_name and raw_json.action_run_id",
            "common_event_outbox by source_layer=N5_action and source_run_id=action_run_id",
        ],
        "tracking_rollback": [
            "common_action_tracking_state by affected_tracking_run_ids",
            "restore pre-existing tracking rows from tracking_updates.raw_json.rollback_before_tracking_state when requires_tracking_restore=true",
        ],
        "forbidden": [
            "common_event_outbox rows from N4_trigger",
            "N3/N4 facts",
            "N6 user projection",
            "launchd",
        ],
    }


def _affected_tracking_run_ids(action_run_id: str, plan: Mapping[str, Any]) -> list[str]:
    run_ids = {str(action_run_id or "").strip()}
    for row in plan.get("tracking_updates") or []:
        if isinstance(row, Mapping):
            run_id = str(row.get("run_id") or "").strip()
            if run_id:
                run_ids.add(run_id)
    return sorted(run_id for run_id in run_ids if run_id)


def main(argv: Sequence[str] | None = None) -> int:
    scheduler_quiet = _scheduler_quiet_requested(argv)
    manifest = run_n5_live_tracking_poller_once(argv)
    if scheduler_quiet and _is_scheduler_phase_noop(manifest):
        return 0
    if scheduler_quiet:
        print(json.dumps(_scheduler_compact_manifest(manifest), ensure_ascii=False, sort_keys=True, default=str))
    else:
        print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, default=str, indent=2))
    return 2 if str(manifest.get("verdict") or "").startswith("BLOCKED") else 0


def _scheduler_quiet_requested(argv: Sequence[str] | None) -> bool:
    values = list(sys.argv[1:] if argv is None else argv)
    return "--scheduler-quiet" in values


def _scheduler_compact_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    fastlane = manifest.get("fastlane") if isinstance(manifest.get("fastlane"), Mapping) else {}
    compact: dict[str, Any] = {
        "verdict": str(manifest.get("verdict") or ""),
        "scheduler_quiet": True,
    }
    for key in ("blocked_reason", "reason", "for_trade_date", "writes_enabled", "artifact_writes_enabled"):
        if key in manifest:
            compact[key] = _compact_scalar(manifest.get(key))
    for key in ("phase", "session_phase"):
        if key in fastlane:
            compact[key] = _compact_scalar(fastlane.get(key))
    write_result = _compact_mapping_scalars(
        manifest.get("write_result"),
        {
            "executed",
            "common_action_tracking_state",
            "common_event_consumer_checkpoint",
            "common_event_inbox",
            "common_event_outbox",
            "n4_outbox_status_updated",
            "proof_to_action_ms",
            "rows_written",
        },
    )
    if write_result:
        compact["write_result"] = write_result
    counts = _scheduler_compact_counts(manifest)
    if counts:
        compact["counts"] = counts
    artifact_paths = _scheduler_compact_artifact_paths(manifest)
    if artifact_paths:
        compact["artifact_paths"] = artifact_paths
    boundary = _compact_mapping_scalars(
        manifest.get("boundary"),
        {
            "n4_outbox_updated",
            "n3_or_n4_fact_modified",
            "n6_written_directly",
            "market_data_pulled",
            "launchd_touched",
            "long_running_worker_started",
        },
    )
    if boundary:
        compact["boundary"] = boundary
    return compact


def _scheduler_compact_counts(manifest: Mapping[str, Any]) -> dict[str, Any]:
    counts = _compact_mapping_scalars(
        manifest,
        {"scope_count", "active_tracking_ref_count", "active_scope_artifact_count"},
    )
    plan = manifest.get("plan") if isinstance(manifest.get("plan"), Mapping) else {}
    artifact = plan.get("active_scope_artifact") if isinstance(plan.get("active_scope_artifact"), Mapping) else {}
    counts.update(
        _compact_mapping_scalars(
            artifact,
            {"scope_count", "active_tracking_ref_count"},
        )
    )
    list_count_keys = {
        "tracking_updates": "tracking_update_count",
        "action_events": "action_event_count",
        "consumed_n4_events": "consumed_n4_event_count",
        "active_tracking_refs": "active_tracking_ref_row_count",
        "attention_event_refs": "attention_event_ref_count",
        "metric_rows": "metric_row_count",
    }
    for key, output_key in list_count_keys.items():
        value = plan.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            counts[output_key] = len(value)
    return counts


def _scheduler_compact_artifact_paths(manifest: Mapping[str, Any]) -> dict[str, Any]:
    paths = _compact_mapping_scalars(
        manifest,
        {
            "active_scope_artifact_path",
            "output_artifact_path",
            "post_close_final_a_pass_done_marker_path",
        },
    )
    active_scope_result = (
        manifest.get("active_scope_artifact_write_result")
        if isinstance(manifest.get("active_scope_artifact_write_result"), Mapping)
        else {}
    )
    paths.update(
        _compact_mapping_scalars(
            active_scope_result,
            {"path", "artifact_path", "active_scope_artifact_path"},
        )
    )
    return paths


def _compact_mapping_scalars(value: Any, allowed_keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key in sorted(allowed_keys):
        if key in value:
            result[key] = _compact_scalar(value.get(key))
    return result


def _compact_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date, Decimal)):
        return _json_safe_value(value)
    return str(value)


def _is_scheduler_phase_noop(manifest: Mapping[str, Any]) -> bool:
    if manifest.get("verdict") == "N5_LIVE_TRACKING_READINESS_WAITING":
        return manifest.get("writes_enabled") is False and manifest.get("artifact_writes_enabled") is False
    if not str(manifest.get("verdict") or "").startswith("BLOCKED"):
        return False
    if manifest.get("writes_enabled") is not False:
        return False
    if manifest.get("artifact_writes_enabled") is True:
        return False
    reason = str(manifest.get("blocked_reason") or "")
    return (
        reason.startswith("fastlane_worker_")
        or reason.startswith("fastlane active_worker_policy_review_ref_not_ready:")
        or reason in {
            "fastlane write-enabled active plan requires session_context or session_context_policy",
            "fastlane write-enabled active plan requires session_context_policy.trade_calendar_is_open",
            "fastlane write-enabled active plan requires active_worker_policy_review_ref",
            "fastlane active_worker_policy_review_ref not ready",
            "fastlane active_worker_policy_review_ref for_trade_date mismatch",
            "active worker policy review not ready",
            "active worker policy review not ready: manual_gate_required",
            "active worker policy review not ready: blockers_or_waiting_reasons",
            "active worker policy review chain_backlog mismatch",
            "fastlane active_worker_policy_review_path not readable",
        }
    )


def _scheduler_noop_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    fastlane = manifest.get("fastlane") if isinstance(manifest.get("fastlane"), Mapping) else {}
    return {
        "verdict": "FASTLANE_SCHEDULER_NOOP",
        "blocked_reason": str(manifest.get("blocked_reason") or ""),
        "phase": str(fastlane.get("phase") or ""),
        "session_phase": str(fastlane.get("session_phase") or ""),
        "scheduler_quiet": True,
        "writes_enabled": False,
    }


if __name__ == "__main__":
    raise SystemExit(main())
