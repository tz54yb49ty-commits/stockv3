#!/usr/bin/env python3
"""Run one N5 live-tracking bounded poller invocation."""

from __future__ import annotations

import argparse
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

from ashare_v3.action.dry_run import build_action_tracking_state_key
from ashare_v3.action.live_tracking_poller import build_live_tracking_plan
from ashare_v3.runtime_control.n5_n3t_fastlane import (
    FASTLANE_LANE_ID,
    build_fastlane_source_run_namespace,
    classify_fastlane_session_phase,
    load_fastlane_activation_config,
    resolve_fastlane_runtime_session_context,
    resolve_fastlane_active_worker_decision,
    validate_fastlane_write_enabled_activation_authorization,
)


DEFAULT_DSN = os.environ.get("ASHARE_V3_POSTGRES_DSN", "")
DEFAULT_EVENT_LIMIT = 1000
DEFAULT_FASTLANE_MAX_RUNTIME_SECONDS = 10.0
DEFAULT_FASTLANE_CONSUMER_NAME = "n5_live_tracking_poller_v2_fastlane"
N5_OUTPUT_EVENT_TYPES = ("ActionEligible", "ActionExecuted")
N4_INPUT_EVENT_TYPES = ("TriggerMatched", "TriggerStateChanged")
N5_LIVE_TRACKING_SCHEMA_VERSION = "v2"
N5_LIVE_TRACKING_TRIGGER_TYPE = "N5_live_tracking_v2"
SCHEMA_ALLOWED_TRACKING_TRIGGER_TYPES = ("BUY", "BUY:FULL", "SELL", "SELL:FULL", "BUY_HINT", "SELL_HINT")
TRACKING_MONITOR_WINDOW_ID_PREFIX = "N5_live_tracking_monitor_window_v1"
FASTLANE_ACTION_RUN_ID_REGEX = r"^n5_live_tracking_.*__fastlane_v1$"
FASTLANE_N3T_METRIC_RUN_ID_SUFFIX_REGEX = r"__fastlane.*$"


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
            return manifest
        write_result = dict((writer or _default_execute_writer)(args, plan))
        manifest["verdict"] = "N5_LIVE_TRACKING_EXECUTE_PASS"
        manifest["write_result"] = write_result
        manifest["active_scope_artifact_write_result"] = _write_active_scope_artifact(args, plan)
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


def _is_fastlane_readiness_waiting_reason(reason: str) -> bool:
    return reason == "fastlane_worker_waiting_for_n4_triggermatched"


def _validate_args(args: argparse.Namespace) -> None:
    if not str(args.for_trade_date).isdigit() or len(str(args.for_trade_date)) != 8:
        raise N5LiveTrackingBlocked("for_trade_date_must_be_yyyymmdd")
    required_names = ["source_trigger_run_id", "action_run_id", "consumer_name"]
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
            ):
                if not str(getattr(args, name, "") or "").strip():
                    setattr(args, name, str(discovered.get(name) or ""))
            if not str(getattr(args, "fastlane_trigger_time", "") or "").strip():
                args.fastlane_trigger_time = str(discovered.get("trigger_time") or "")
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
        formal_trigger_matched_available = (
            n5_intake_event_kind != "inactive_TriggerStateChanged_false"
            and bool(str(args.source_trigger_run_id or "").strip())
        )
        inactive_trigger_state_changed_available = n5_intake_event_kind == "inactive_TriggerStateChanged_false"
        session_context = resolve_fastlane_runtime_session_context(
            config,
            trigger_time=str(getattr(args, "fastlane_trigger_time", "") or ""),
            formal_trigger_matched_available=formal_trigger_matched_available,
            inactive_trigger_state_changed_available=inactive_trigger_state_changed_available,
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
        closed_minute_available=bool(session_context.get("closed_minute_available")),
        matching_n3t_metric_available=bool(session_context.get("matching_n3t_metric_available"))
        or (lane_key == "n5_action_executed" and bool(str(args.source_metric_run_id or "").strip())),
    )
    args.fastlane_session_phase = classification["phase"]
    args.fastlane_active_worker_decision = decision
    if decision["worker_mode"] == "fail_closed":
        raise N5LiveTrackingBlocked(f"fastlane_worker_{decision.get('blocked_reason') or 'fail_closed'}")
    if (args.execute or args.write_active_scope_artifact) and not decision["writes_enabled_allowed"]:
        raise N5LiveTrackingBlocked(f"fastlane_worker_{decision.get('blocked_reason') or 'write_not_allowed'}")


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
          o.source_run_id,
          min(o.event_time)::text AS trigger_time,
          bool_or(o.event_type = 'TriggerMatched') AS has_trigger_matched,
          bool_or(
            o.event_type = 'TriggerStateChanged'
            AND lower(coalesce(o.payload_json->>'trigger_live', 'true')) IN ('false', 'f', '0', 'no', 'n')
          ) AS has_inactive_state_changed
        FROM common_event_outbox o
        WHERE o.source_layer = 'N4_trigger'
          AND o.trade_date = %s
          AND o.status = 'pending'
          AND (
            o.event_type = 'TriggerMatched'
            OR (
              o.event_type = 'TriggerStateChanged'
              AND lower(coalesce(o.payload_json->>'trigger_live', 'true')) IN ('false', 'f', '0', 'no', 'n')
            )
          )
          AND NOT EXISTS (
            SELECT 1
            FROM common_event_inbox i
            WHERE i.consumer_name = %s
              AND i.event_id = o.event_id
          )
        GROUP BY o.source_run_id
        ORDER BY min(o.event_time), o.source_run_id
        LIMIT 1
        """,
        (args.for_trade_date, DEFAULT_FASTLANE_CONSUMER_NAME),
    )
    row = cur.fetchone()
    source_trigger_run_id = str((row or {}).get("source_run_id") or "")
    if not source_trigger_run_id:
        return {}
    has_trigger_matched = bool((row or {}).get("has_trigger_matched"))
    return {
        "source_trigger_run_id": source_trigger_run_id,
        "trigger_time": str((row or {}).get("trigger_time") or ""),
        "n5_intake_event_kind": (
            "formal_TriggerMatched" if has_trigger_matched else "inactive_TriggerStateChanged_false"
        ),
        "action_run_id": _fastlane_action_run_id(
            for_trade_date=str(args.for_trade_date),
            source_trigger_run_id=source_trigger_run_id,
        ),
        "consumer_name": DEFAULT_FASTLANE_CONSUMER_NAME,
    }


def _discover_executed_runtime_inputs(cur: Any, args: argparse.Namespace) -> dict[str, str]:
    cur.execute(
        """
        SELECT run_id, source_trigger_run_id, latest_n4_event_time::text AS trigger_time
        FROM common_action_tracking_state
        WHERE trade_date = %s
          AND run_id ~ %s
          AND action_state = 'eligible'
          AND tracking_status = 'tracking'
        ORDER BY latest_n4_event_time NULLS LAST, run_id, source_trigger_run_id
        LIMIT 1
        """,
        (args.for_trade_date, FASTLANE_ACTION_RUN_ID_REGEX),
    )
    row = cur.fetchone()
    action_run_id = str((row or {}).get("run_id") or "")
    source_trigger_run_id = str((row or {}).get("source_trigger_run_id") or "")
    target_minute_label = _metric_minute_label_from_source_trigger_run_id(source_trigger_run_id)
    source_metric_run_id = ""
    if target_minute_label:
        source_metric_run_id = _discover_latest_ready_n3t_metric_run_id(
            cur,
            str(args.for_trade_date),
            target_minute_label=target_minute_label,
        )
    output: dict[str, str] = {}
    if action_run_id:
        output["action_run_id"] = action_run_id
    if source_trigger_run_id:
        output["source_trigger_run_id"] = source_trigger_run_id
    if row and row.get("trigger_time"):
        output["trigger_time"] = str(row.get("trigger_time") or "")
    if source_metric_run_id:
        output["source_metric_run_id"] = source_metric_run_id
    if action_run_id or source_trigger_run_id or source_metric_run_id:
        output["consumer_name"] = DEFAULT_FASTLANE_CONSUMER_NAME
    return output


def _metric_minute_label_from_source_trigger_run_id(source_trigger_run_id: str) -> str:
    match = re.search(r"(?:^|_)until_([0-9]{4})(?:_|$)", str(source_trigger_run_id or ""))
    return match.group(1) if match else ""


def _fastlane_n3t_metric_run_id_regex(for_trade_date: str, target_minute_label: str) -> str:
    safe_trade_date = re.escape(str(for_trade_date or ""))
    safe_minute_label = re.escape(str(target_minute_label or ""))
    return (
        rf"^n3t_action_confirmation_metric_{safe_trade_date}_until_{safe_minute_label}"
        + FASTLANE_N3T_METRIC_RUN_ID_SUFFIX_REGEX
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


def _discover_latest_ready_n3t_metric_run_id(cur: Any, for_trade_date: str, *, target_minute_label: str) -> str:
    candidates: list[tuple[str, str]] = []
    metric_run_id_regex = _fastlane_n3t_metric_run_id_regex(for_trade_date, target_minute_label)
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
            (for_trade_date, f"%until_{target_minute_label}%", metric_run_id_regex),
        )
        row = cur.fetchone()
        if row and row.get("projection_run_id"):
            candidates.append((str(row.get("latest_metric_time") or ""), str(row["projection_run_id"])))
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return candidates[0][1]


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe_value(artifact), ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
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
        n4_rows = [] if _is_fastlane_executed_phase(args) else _fetch_pending_n4_rows(cur, args)
        active_tracking = _fetch_active_tracking_rows(cur, args, n4_event_rows=n4_rows)
        metric_rows = _fetch_metric_rows(cur, args)
        existing_event_keys = _fetch_existing_action_event_keys(cur, args)
    return build_live_tracking_plan(
        n4_event_rows=n4_rows,
        active_tracking_rows=active_tracking,
        metric_rows=metric_rows,
        action_run_id=args.action_run_id,
        source_trigger_run_id=args.source_trigger_run_id,
        source_metric_run_id=args.source_metric_run_id,
        consumer_name=args.consumer_name,
        existing_action_event_keys=existing_event_keys,
        for_trade_date=args.for_trade_date,
    )


def _fetch_pending_n4_rows(cur: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
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


def _fetch_active_tracking_rows(
    cur: Any,
    args: argparse.Namespace,
    *,
    n4_event_rows: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
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
    with psycopg.connect(args.dsn, row_factory=dict_row, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            tracking_count = _upsert_tracking_states(cur, plan.get("tracking_updates") or [])
            outbox_count = _insert_action_outbox_events(cur, plan.get("action_events") or [])
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
    }


def _upsert_tracking_states(cur: Any, rows: Sequence[Mapping[str, Any]]) -> int:
    if not rows:
        return 0
    values = [_tracking_values(row) for row in rows]
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
          source_trigger_event_id = EXCLUDED.source_trigger_event_id,
          source_trigger_event_type = EXCLUDED.source_trigger_event_type,
          source_trigger_match_id = COALESCE(EXCLUDED.source_trigger_match_id, common_action_tracking_state.source_trigger_match_id),
          trigger_live = EXCLUDED.trigger_live,
          current_status = EXCLUDED.current_status,
          primary_trigger_period = EXCLUDED.primary_trigger_period,
          all_trigger_periods = EXCLUDED.all_trigger_periods,
          trigger_mark_candidate = EXCLUDED.trigger_mark_candidate,
          latest_n4_event_id = EXCLUDED.latest_n4_event_id,
          latest_n4_event_type = EXCLUDED.latest_n4_event_type,
          latest_n4_event_time = EXCLUDED.latest_n4_event_time,
          action_state = CASE
            WHEN EXCLUDED.action_state = 'executed' THEN EXCLUDED.action_state
            WHEN common_action_tracking_state.action_state = 'executed' THEN common_action_tracking_state.action_state
            WHEN common_action_tracking_state.action_state IN ('blocked', 'skipped', 'expired') THEN common_action_tracking_state.action_state
            ELSE EXCLUDED.action_state
          END,
          confirmation_status = CASE
            WHEN EXCLUDED.action_state = 'executed' THEN EXCLUDED.confirmation_status
            WHEN common_action_tracking_state.action_state = 'executed' THEN common_action_tracking_state.confirmation_status
            WHEN common_action_tracking_state.action_state IN ('blocked', 'skipped', 'expired') THEN common_action_tracking_state.confirmation_status
            ELSE EXCLUDED.confirmation_status
          END,
          tracking_status = CASE
            WHEN EXCLUDED.action_state = 'executed' THEN EXCLUDED.tracking_status
            WHEN common_action_tracking_state.action_state = 'executed' THEN common_action_tracking_state.tracking_status
            WHEN common_action_tracking_state.action_state IN ('blocked', 'skipped', 'expired') THEN common_action_tracking_state.tracking_status
            ELSE EXCLUDED.tracking_status
          END,
          planned_output_event_type = EXCLUDED.planned_output_event_type,
          expired_reason = EXCLUDED.expired_reason,
          expired_at = EXCLUDED.expired_at,
          tracking_until = EXCLUDED.tracking_until,
          last_checked_minute_label = EXCLUDED.last_checked_minute_label,
          monitor_window_id = EXCLUDED.monitor_window_id,
          trigger_type = EXCLUDED.trigger_type,
          triggered_periods = EXCLUDED.triggered_periods,
          trigger_context_version = EXCLUDED.trigger_context_version,
          raw_json = EXCLUDED.raw_json,
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
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, default=str, indent=2))
    return 2 if str(manifest.get("verdict") or "").startswith("BLOCKED") else 0


def _scheduler_quiet_requested(argv: Sequence[str] | None) -> bool:
    values = list(sys.argv[1:] if argv is None else argv)
    return "--scheduler-quiet" in values


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
    return reason.startswith("fastlane_worker_") or reason in {
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
