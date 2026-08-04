#!/usr/bin/env python3
"""Plan or persist one bounded N5 trigger-status-forward-only invocation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.action.live_tracking_poller import build_trigger_status_forward_plan
from ashare_v3.events.models import (
    EventEnvelope,
    N5_TRIGGER_STATUS_MESSAGE_TYPES,
    validate_event_envelope,
)


DEFAULT_DSN = os.environ.get("ASHARE_V3_POSTGRES_DSN", "")
DEFAULT_MAX_EVENTS = 1000
DEFAULT_MAX_RUNTIME_SECONDS = 10.0
MAX_EVENTS_LIMIT = 50000
MAX_RUNTIME_SECONDS_LIMIT = 60.0
PLANNING_MODE = "status_forward_only_offline_bounded_v1"


class N5TriggerStatusForwardBlocked(RuntimeError):
    """Raised when the status-only runner must fail closed."""


class N5TriggerStatusForwardWriteAmbiguous(RuntimeError):
    """Raised only after the writer phase starts and commit state is unknown."""


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--source-trigger-run-id", default="")
    parser.add_argument("--source-eligible-action-run-id", default="")
    parser.add_argument("--action-run-id", required=True)
    parser.add_argument("--consumer-name", required=True)
    parser.add_argument("--max-events", type=int, default=DEFAULT_MAX_EVENTS)
    parser.add_argument("--max-runtime-seconds", type=float, default=DEFAULT_MAX_RUNTIME_SECONDS)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def run_n5_trigger_status_forward_once(
    argv: Sequence[str] | None = None,
    *,
    plan_provider: Callable[[argparse.Namespace], Mapping[str, Any]] | None = None,
    writer: Callable[[argparse.Namespace, Sequence[Mapping[str, Any]]], Mapping[str, Any]] | None = None,
    now_monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    args = build_arg_parser().parse_args(list(argv) if argv is not None else None)
    invocation_id = f"n5_trigger_status_forward_{uuid.uuid4().hex}"
    started = now_monotonic()
    try:
        dsn_required = plan_provider is None or (args.execute and writer is None)
        _validate_args(args, dsn_required=False)
        if args.execute and not args.user_confirmed:
            raise N5TriggerStatusForwardBlocked("execute_requires_user_confirmed")
        if dsn_required and not str(args.dsn or ""):
            raise N5TriggerStatusForwardBlocked("dsn_required")
        args.deadline_monotonic = started + args.max_runtime_seconds
        try:
            plan = dict((plan_provider or _default_plan_provider)(args))
        except Exception as exc:
            return _plan_failure_manifest(args, invocation_id, exc)
        _validate_plan(args, plan)
        _check_runtime(args, started, now_monotonic)
        manifest = _manifest(args, invocation_id, plan, started, now_monotonic)
        if not args.execute:
            manifest["verdict"] = "N5_TRIGGER_STATUS_FORWARD_PLAN_ONLY"
            manifest["write_result"] = _zero_write_result()
            return manifest

        status_events = list(plan.get("status_events") or [])
        args.remaining_runtime_seconds = max(
            0.001,
            args.max_runtime_seconds - (now_monotonic() - started),
        )
        try:
            write_result = dict((writer or _default_execute_writer)(args, status_events))
        except Exception as exc:
            raise N5TriggerStatusForwardWriteAmbiguous(
                f"{type(exc).__name__}:{exc}"
            ) from exc
        manifest["verdict"] = "N5_TRIGGER_STATUS_FORWARD_EXECUTE_PASS"
        manifest["write_result"] = write_result
        return manifest
    except N5TriggerStatusForwardBlocked as exc:
        return {
            "verdict": "BLOCKED_N5_TRIGGER_STATUS_FORWARD",
            "blocked_reason": str(exc),
            "failure_phase": "plan",
            "requires_post_check": False,
            "invocation_id": invocation_id,
            "execute_requested": bool(args.execute),
            "writes_enabled": False,
            "writer_called": False,
            "write_result": _zero_write_result(),
        }


def _plan_failure_manifest(
    args: argparse.Namespace,
    invocation_id: str,
    exc: Exception,
) -> dict[str, Any]:
    return {
        "verdict": "BLOCKED_N5_TRIGGER_STATUS_FORWARD_PLAN_READ",
        "blocked_reason": f"{type(exc).__name__}:{exc}",
        "failure_phase": "plan",
        "requires_post_check": False,
        "invocation_id": invocation_id,
        "execute_requested": bool(args.execute),
        "writes_enabled": False,
        "writer_called": False,
        "write_result": _zero_write_result(),
    }


def _validate_args(args: argparse.Namespace, *, dsn_required: bool) -> None:
    if len(str(args.for_trade_date)) != 8 or not str(args.for_trade_date).isdigit():
        raise N5TriggerStatusForwardBlocked("for_trade_date_must_be_yyyymmdd")
    source_trigger_run_id = str(args.source_trigger_run_id or "").strip()
    source_eligible_action_run_id = str(args.source_eligible_action_run_id or "").strip()
    if bool(source_trigger_run_id) == bool(source_eligible_action_run_id):
        raise N5TriggerStatusForwardBlocked("exactly_one_source_authority_required")
    args.source_trigger_run_id = source_trigger_run_id
    args.source_eligible_action_run_id = source_eligible_action_run_id
    for name in ("action_run_id", "consumer_name"):
        if not str(getattr(args, name) or "").strip():
            raise N5TriggerStatusForwardBlocked(f"{name}_required")
    if not 0 < int(args.max_events) <= MAX_EVENTS_LIMIT:
        raise N5TriggerStatusForwardBlocked("max_events_out_of_bounds")
    if not 0 < float(args.max_runtime_seconds) <= MAX_RUNTIME_SECONDS_LIMIT:
        raise N5TriggerStatusForwardBlocked("max_runtime_seconds_out_of_bounds")
    if dsn_required and not str(args.dsn or ""):
        raise N5TriggerStatusForwardBlocked("dsn_required")


def _validate_plan(args: argparse.Namespace, plan: Mapping[str, Any]) -> None:
    if str(plan.get("planning_mode") or "") != PLANNING_MODE:
        raise N5TriggerStatusForwardBlocked("status_forward_planning_mode_required")
    if str(plan.get("scope_mode") or "") != _scope_mode(args):
        raise N5TriggerStatusForwardBlocked("status_forward_scope_mode_mismatch")
    if str(plan.get("source_trigger_run_id") or "") != str(args.source_trigger_run_id or ""):
        raise N5TriggerStatusForwardBlocked("status_forward_source_trigger_run_mismatch")
    if str(plan.get("source_eligible_action_run_id") or "") != str(
        args.source_eligible_action_run_id or ""
    ):
        raise N5TriggerStatusForwardBlocked("status_forward_source_action_run_mismatch")
    source_trigger_run_ids = list(plan.get("source_trigger_run_ids") or [])
    if source_trigger_run_ids != sorted(set(source_trigger_run_ids)) or any(
        not str(run_id or "") for run_id in source_trigger_run_ids
    ):
        raise N5TriggerStatusForwardBlocked("status_forward_source_run_census_invalid")
    try:
        source_trigger_run_count = int(plan.get("source_trigger_run_count", -1))
        action_eligible_count = int((plan.get("summary") or {}).get("action_eligible_count", -1))
    except (TypeError, ValueError) as exc:
        raise N5TriggerStatusForwardBlocked("status_forward_scope_counts_invalid") from exc
    if source_trigger_run_count != len(source_trigger_run_ids):
        raise N5TriggerStatusForwardBlocked("status_forward_source_run_count_mismatch")
    expected_source_run_hash = hashlib.sha256(
        json.dumps(source_trigger_run_ids, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if str(plan.get("source_trigger_run_ids_hash") or "") != expected_source_run_hash:
        raise N5TriggerStatusForwardBlocked("status_forward_source_run_hash_mismatch")
    if _scope_mode(args) == "single_source_trigger_run" and any(
        run_id != args.source_trigger_run_id for run_id in source_trigger_run_ids
    ):
        raise N5TriggerStatusForwardBlocked("status_forward_single_source_census_mismatch")
    if _scope_mode(args) == "aggregate_day_action_run" and action_eligible_count <= 0:
        raise N5TriggerStatusForwardBlocked("source_eligible_action_run_has_no_action_eligible")
    if plan.get("action_events") or plan.get("tracking_updates") or plan.get("inbox_checkpoint_intent"):
        raise N5TriggerStatusForwardBlocked("status_forward_plan_contains_forbidden_effects")
    persistence = plan.get("persistence") or {}
    if list(persistence.get("allowed_targets") or []) != ["common_event_outbox"]:
        raise N5TriggerStatusForwardBlocked("status_forward_persistence_target_mismatch")
    if persistence.get("common_action_event_write_allowed") is not False:
        raise N5TriggerStatusForwardBlocked("status_forward_common_action_event_write_forbidden")
    if persistence.get("database_write_allowed") is not False:
        raise N5TriggerStatusForwardBlocked("status_forward_plan_must_be_offline")

    events = list(plan.get("status_events") or [])
    if len(events) > int(args.max_events):
        raise N5TriggerStatusForwardBlocked("status_event_count_exceeds_max_events")
    for event in events:
        if str(event.get("event_type") or "") not in N5_TRIGGER_STATUS_MESSAGE_TYPES:
            raise N5TriggerStatusForwardBlocked("non_status_event_in_status_forward_plan")
        try:
            validate_event_envelope(_event_envelope(event))
        except (TypeError, ValueError) as exc:
            raise N5TriggerStatusForwardBlocked(f"invalid_status_event:{exc}") from exc


def _event_envelope(event: Mapping[str, Any]) -> EventEnvelope:
    event_time = _datetime_value(event.get("event_time"))
    return EventEnvelope(
        event_id=str(event.get("event_id") or ""),
        event_type=str(event.get("event_type") or ""),
        event_schema_version=str(event.get("event_schema_version") or ""),
        trade_date=str(event.get("trade_date") or ""),
        asset_kind=str(event.get("asset_kind") or ""),
        identity_key=str(event.get("identity_key") or ""),
        event_time=event_time,
        source_layer=str(event.get("source_layer") or ""),
        source_run_id=str(event.get("source_run_id") or ""),
        dedup_key=str(event.get("dedup_key") or ""),
        partition_key=str(event.get("partition_key") or ""),
        payload_json=dict(event.get("payload_json") or {}),
        created_at=event_time,
    )


def _datetime_value(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("event_time must be timezone-aware")
    return parsed


def _check_runtime(
    args: argparse.Namespace,
    started: float,
    now_monotonic: Callable[[], float],
) -> None:
    if now_monotonic() - started > float(args.max_runtime_seconds):
        raise N5TriggerStatusForwardBlocked("max_runtime_seconds_exceeded")


def _manifest(
    args: argparse.Namespace,
    invocation_id: str,
    plan: Mapping[str, Any],
    started: float,
    now_monotonic: Callable[[], float],
) -> dict[str, Any]:
    return {
        "invocation_id": invocation_id,
        "planning_mode": PLANNING_MODE,
        "for_trade_date": args.for_trade_date,
        "action_run_id": args.action_run_id,
        "scope_mode": _scope_mode(args),
        "source_trigger_run_id": args.source_trigger_run_id,
        "source_eligible_action_run_id": args.source_eligible_action_run_id,
        "source_trigger_run_count": plan.get("source_trigger_run_count", 0),
        "source_trigger_run_ids": list(plan.get("source_trigger_run_ids") or []),
        "source_trigger_run_ids_hash": plan.get("source_trigger_run_ids_hash", ""),
        "action_eligible_count": (plan.get("summary") or {}).get("action_eligible_count", 0),
        "consumer_name": args.consumer_name,
        "execute_requested": bool(args.execute),
        "status_event_count": len(plan.get("status_events") or []),
        "bounded": {
            "max_events": args.max_events,
            "max_runtime_seconds": args.max_runtime_seconds,
            "elapsed_seconds": round(now_monotonic() - started, 6),
        },
        "boundary": {
            "common_event_outbox_only": True,
            "common_action_event_written": False,
            "tracking_written": False,
            "common_event_inbox_written": False,
            "common_event_consumer_checkpoint_written": False,
            "n4_inbox_checkpoint_written": False,
            "n4_outbox_status_updated": False,
        },
        "plan": plan,
    }


def _zero_write_result() -> dict[str, Any]:
    return {
        "executed": False,
        "common_event_outbox": 0,
        "common_action_event": 0,
        "common_action_tracking_state": 0,
        "common_event_inbox": 0,
        "common_event_consumer_checkpoint": 0,
        "n4_outbox_status_updated": False,
    }


def _scope_mode(args: argparse.Namespace) -> str:
    if str(args.source_eligible_action_run_id or "").strip():
        return "aggregate_day_action_run"
    return "single_source_trigger_run"


def _default_plan_provider(args: argparse.Namespace) -> dict[str, Any]:
    limit = int(args.max_events) + 1
    statement_timeout_ms = max(1, int(float(args.max_runtime_seconds) * 1000))
    options = f"-c default_transaction_read_only=on -c statement_timeout={statement_timeout_ms}"
    with psycopg.connect(
        args.dsn,
        row_factory=dict_row,
        options=options,
        connect_timeout=max(1, min(10, int(args.max_runtime_seconds))),
    ) as conn, conn.cursor() as cur:
        n4_rows = _fetch_n4_lifecycle_rows(cur, args, limit=limit)
        eligible_rows = _fetch_action_eligible_rows(cur, args, limit=limit)
        existing_keys = _fetch_existing_status_event_keys(cur, args, limit=limit)
    if max(len(n4_rows), len(eligible_rows), len(existing_keys)) >= limit:
        raise N5TriggerStatusForwardBlocked("status_forward_read_scope_exceeds_max_events")
    return build_trigger_status_forward_plan(
        n4_event_rows=n4_rows,
        action_eligible_event_rows=eligible_rows,
        action_run_id=args.action_run_id,
        source_trigger_run_id=args.source_trigger_run_id,
        source_eligible_action_run_id=args.source_eligible_action_run_id,
        scope_mode=_scope_mode(args),
        consumer_name=args.consumer_name,
        for_trade_date=args.for_trade_date,
        existing_status_event_keys=existing_keys,
        max_n4_event_rows=args.max_events,
        max_status_events=args.max_events,
    )


def _fetch_n4_lifecycle_rows(cur: Any, args: argparse.Namespace, *, limit: int) -> list[dict[str, Any]]:
    source_filter = "AND source_run_id = %s" if args.source_trigger_run_id else ""
    params: tuple[Any, ...] = (
        (args.source_trigger_run_id, args.for_trade_date, limit)
        if args.source_trigger_run_id
        else (args.for_trade_date, limit)
    )
    cur.execute(
        f"""
        SELECT outbox_id, event_id, event_type, event_schema_version, trade_date,
               asset_kind, identity_key, event_time, source_layer, source_run_id,
               dedup_key, partition_key, payload_json, status
        FROM common_event_outbox
        WHERE source_layer = 'N4_trigger'
          {source_filter}
          AND trade_date = %s
          AND event_type = 'TriggerStateChanged'
        ORDER BY event_time, source_run_id, outbox_id, event_id
        LIMIT %s
        """,
        params,
    )
    return [dict(row) for row in cur.fetchall()]


def _fetch_action_eligible_rows(cur: Any, args: argparse.Namespace, *, limit: int) -> list[dict[str, Any]]:
    if args.source_eligible_action_run_id:
        authority_filter = "AND source_run_id = %s"
        authority_value = args.source_eligible_action_run_id
    else:
        authority_filter = "AND payload_json ->> 'source_trigger_run_id' = %s"
        authority_value = args.source_trigger_run_id
    cur.execute(
        f"""
        SELECT event_id, event_type, event_schema_version, trade_date, asset_kind,
               identity_key, event_time, source_layer, source_run_id, dedup_key,
               partition_key, payload_json
        FROM common_event_outbox
        WHERE source_layer = 'N5_action'
          AND trade_date = %s
          AND event_type = 'ActionEligible'
          {authority_filter}
        ORDER BY event_time, event_id
        LIMIT %s
        """,
        (args.for_trade_date, authority_value, limit),
    )
    return [dict(row) for row in cur.fetchall()]


def _fetch_existing_status_event_keys(
    cur: Any,
    args: argparse.Namespace,
    *,
    limit: int,
) -> set[str]:
    source_filter = (
        "" if args.source_eligible_action_run_id else "AND payload_json ->> 'source_trigger_run_id' = %s"
    )
    params: tuple[Any, ...] = (
        (args.for_trade_date, list(N5_TRIGGER_STATUS_MESSAGE_TYPES), limit)
        if args.source_eligible_action_run_id
        else (
            args.for_trade_date,
            list(N5_TRIGGER_STATUS_MESSAGE_TYPES),
            args.source_trigger_run_id,
            limit,
        )
    )
    cur.execute(
        f"""
        SELECT DISTINCT dedup_key
        FROM common_event_outbox
        WHERE source_layer = 'N5_action'
          AND trade_date = %s
          AND event_type = ANY(%s)
          {source_filter}
        ORDER BY dedup_key
        LIMIT %s
        """,
        params,
    )
    return {str(row["dedup_key"]) for row in cur.fetchall() if row.get("dedup_key")}


def _default_execute_writer(
    args: argparse.Namespace,
    status_events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not args.dsn:
        raise N5TriggerStatusForwardBlocked("dsn_required_for_execute")
    timeout_ms = max(1, int(float(args.remaining_runtime_seconds) * 1000))
    with psycopg.connect(
        args.dsn,
        row_factory=dict_row,
        options=f"-c statement_timeout={timeout_ms}",
        connect_timeout=max(1, min(10, int(args.remaining_runtime_seconds))),
    ) as conn, conn.cursor() as cur:
        count = 0
        for event in status_events:
            cur.execute(
                """
                INSERT INTO common_event_outbox (
                  event_id, event_type, event_schema_version, trade_date,
                  asset_kind, identity_key, event_time, source_layer,
                  source_run_id, dedup_key, partition_key, payload_json, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                ON CONFLICT DO NOTHING
                """,
                (
                    event["event_id"],
                    event["event_type"],
                    event["event_schema_version"],
                    event["trade_date"],
                    event["asset_kind"],
                    event["identity_key"],
                    _datetime_value(event["event_time"]),
                    event["source_layer"],
                    event["source_run_id"],
                    event["dedup_key"],
                    event["partition_key"],
                    Jsonb(dict(event["payload_json"])),
                ),
            )
            count += cur.rowcount
        if time.monotonic() > float(args.deadline_monotonic):
            raise N5TriggerStatusForwardBlocked("max_runtime_seconds_exceeded_before_commit")
        conn.commit()
    return {**_zero_write_result(), "executed": True, "common_event_outbox": count}


def main(argv: Sequence[str] | None = None) -> int:
    result = run_n5_trigger_status_forward_once(argv)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 2 if str(result.get("verdict") or "").startswith("BLOCKED") else 0


if __name__ == "__main__":
    raise SystemExit(main())
