"""Bounded N4 worker smoke planning helpers.

The implementation in this module is deliberately side-effect free.  A later
final gate can wire these plans to database writes after review.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timezone
from decimal import Decimal
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from ashare_v3.events.ids import build_stable_event_id
from ashare_v3.trigger.worker_state_transition import build_transition_event_plans, source_event_consume_key

try:  # psycopg is only needed when a future execute gate opens the DB write path.
    from psycopg.types.json import Jsonb
except Exception:  # pragma: no cover - import fallback for static/unit contexts
    Jsonb = None  # type: ignore[assignment]


DEFAULT_CONSUMER_NAME = "n4_trigger_worker_v1"
DEFAULT_SMOKE_RUN_ID = "n4_worker_bounded_smoke"
DEFAULT_DSN = "host=127.0.0.1 port=5432 dbname=ashare_v3 user=ashare_v3_user"

ALLOWED_SMOKE_WRITE_TABLES = {
    "common_trigger_run",
    "common_trigger_quality_item",
    "common_trigger_state",
    "common_trigger_match",
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
}

CONSUMER_BOUNDARY = {
    "n4_must_not_update_n3_outbox_status": True,
    "n4_may_write_inbox_checkpoint": True,
    "n5_n6_entered": False,
    "worker_started": False,
}


class N4WorkerSmokeBlocked(RuntimeError):
    """Raised when bounded smoke execution is not explicitly authorized."""


def assert_bounded_smoke_confirmed(*, execute: bool, user_confirmed: bool) -> None:
    if not execute:
        raise N4WorkerSmokeBlocked("N4 worker bounded smoke blocked before DB write: missing --execute")
    if not user_confirmed:
        raise N4WorkerSmokeBlocked("N4 worker bounded smoke blocked before DB write: missing --user-confirmed")


def assert_explicit_smoke_run_id_for_execute(*, execute: bool, smoke_run_id: str | None) -> None:
    if execute and not (smoke_run_id or "").strip():
        raise N4WorkerSmokeBlocked("N4 worker bounded smoke blocked before DB write: missing --smoke-run-id")


def require_semantic_inputs(
    *,
    semantic_smoke: bool,
    semantic_fixture_path: str | None,
    semantic_oracle_run_id: str | None,
) -> None:
    has_fixture_or_oracle = bool((semantic_fixture_path or "").strip() or (semantic_oracle_run_id or "").strip())
    if has_fixture_or_oracle and not semantic_smoke:
        raise N4WorkerSmokeBlocked("N4 worker bounded smoke blocked before DB write: missing --semantic-smoke")
    if semantic_smoke and not has_fixture_or_oracle:
        raise N4WorkerSmokeBlocked("N4 worker bounded smoke blocked before DB write: missing semantic fixture/oracle")


def load_idempotency_scenario(path: str, *, consumer_name: str) -> dict[str, Any]:
    """Load a bounded smoke duplicate/retry scenario without side effects."""

    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise N4WorkerSmokeBlocked(f"N4 worker bounded smoke idempotency scenario not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise N4WorkerSmokeBlocked(f"N4 worker bounded smoke idempotency scenario JSON invalid: {path}") from exc
    if not isinstance(payload, Mapping):
        raise N4WorkerSmokeBlocked("N4 worker bounded smoke idempotency scenario must be a JSON object")

    scenario_payload = payload.get("idempotency_scenario") or payload.get("scenario") or payload
    if not isinstance(scenario_payload, Mapping):
        raise N4WorkerSmokeBlocked("N4 worker bounded smoke idempotency scenario payload must be a JSON object")

    duplicate_counts = _scenario_duplicate_source_event_counts(payload, scenario_payload)
    existing_consume_keys = _scenario_existing_consume_keys(payload, scenario_payload, consumer_name=consumer_name)
    failure_injection = _scenario_failure_injection(scenario_payload)
    return {
        "scenario_enabled": True,
        "scenario_path": path,
        "duplicate_source_event_counts": duplicate_counts,
        "existing_consume_keys": sorted(existing_consume_keys),
        "failure_injection": failure_injection,
        "raw_json": make_json_safe(payload),
    }


def apply_idempotency_scenario(
    source_events: Sequence[Mapping[str, Any]],
    *,
    existing_consume_keys: set[str] | frozenset[str],
    scenario: Mapping[str, Any] | None,
) -> tuple[list[dict[str, Any]], set[str], dict[str, Any]]:
    """Apply duplicate-row and existing-consume-key modeling in memory only."""

    source_event_rows = [dict(row) for row in source_events]
    combined_existing_keys = set(existing_consume_keys)
    if not scenario:
        return source_event_rows, combined_existing_keys, {
            "scenario_enabled": False,
            "injected_duplicate_source_event_count": 0,
            "injected_existing_consume_key_count": 0,
            "retry_failure_injection_enabled": False,
            "failure_injection_point": None,
        }

    rows_by_event_id = {str(row.get("event_id")): dict(row) for row in source_event_rows}
    injected_duplicate_count = 0
    duplicate_counts = scenario.get("duplicate_source_event_counts") or {}
    if not isinstance(duplicate_counts, Mapping):
        raise N4WorkerSmokeBlocked("N4 worker bounded smoke scenario duplicate_source_event_counts must be an object")
    for event_id, repeat_count in duplicate_counts.items():
        event_key = str(event_id)
        if event_key not in rows_by_event_id:
            raise N4WorkerSmokeBlocked(
                f"N4 worker bounded smoke scenario duplicate source event not selected: {event_key}"
            )
        try:
            count = int(repeat_count)
        except (TypeError, ValueError) as exc:
            raise N4WorkerSmokeBlocked(
                f"N4 worker bounded smoke scenario duplicate count invalid for {event_key}: {repeat_count}"
            ) from exc
        if count < 0:
            raise N4WorkerSmokeBlocked(
                f"N4 worker bounded smoke scenario duplicate count must be non-negative for {event_key}: {count}"
            )
        for index in range(count):
            duplicate_row = dict(rows_by_event_id[event_key])
            duplicate_row["scenario_duplicate_source_row"] = True
            duplicate_row["scenario_duplicate_index"] = index + 1
            source_event_rows.append(duplicate_row)
            injected_duplicate_count += 1

    scenario_existing_keys = {str(key) for key in scenario.get("existing_consume_keys") or [] if str(key)}
    combined_existing_keys.update(scenario_existing_keys)
    failure_injection = scenario.get("failure_injection") if isinstance(scenario.get("failure_injection"), Mapping) else {}
    return source_event_rows, combined_existing_keys, {
        "scenario_enabled": True,
        "scenario_path": scenario.get("scenario_path"),
        "injected_duplicate_source_event_count": injected_duplicate_count,
        "injected_existing_consume_key_count": len(scenario_existing_keys),
        "retry_failure_injection_enabled": bool(failure_injection.get("enabled")),
        "failure_injection_point": failure_injection.get("point"),
    }


def assert_smoke_baseline_clean(baseline_counts: Mapping[str, int]) -> None:
    dirty = {name: count for name, count in baseline_counts.items() if int(count) != 0}
    if dirty:
        raise N4WorkerSmokeBlocked(f"N4 worker bounded smoke target scoped rows already exist: {dirty}")


def validate_source_events_for_execute(
    source_events: Sequence[Mapping[str, Any]],
    *,
    source_event_type: str,
    max_events: int,
) -> None:
    if len(source_events) > max_events:
        raise N4WorkerSmokeBlocked(
            f"N4 worker bounded smoke selected source events exceed max_events: {len(source_events)} > {max_events}"
        )
    for row in source_events:
        if row.get("event_type") != source_event_type or row.get("source_layer") != "N3_market_data":
            raise N4WorkerSmokeBlocked(
                f"N4 worker bounded smoke unsupported source event type: {row.get('source_layer')}/{row.get('event_type')}"
            )
        if row.get("status") != "pending":
            raise N4WorkerSmokeBlocked(
                f"N4 worker bounded smoke non-pending source event blocked: {row.get('event_id')} status={row.get('status')}"
            )


def build_bounded_controls(
    *,
    max_events: int,
    max_runtime_seconds: int,
    stop_file: str,
    status_json: str,
    heartbeat_interval_seconds: int,
) -> dict[str, Any]:
    return {
        "max_events": int(max_events),
        "max_runtime_seconds": int(max_runtime_seconds),
        "stop_file": stop_file,
        "stop_requested": bool(stop_file and Path(stop_file).exists()),
        "status_json": status_json,
        "heartbeat_interval_seconds": int(heartbeat_interval_seconds),
        "bounded": True,
        "long_running_worker_allowed": False,
    }


def write_status_json(path: str, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(make_json_safe(dict(payload)), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def make_json_safe(value: Any) -> Any:
    """Return a recursively JSON-safe value for jsonb/raw_json binding."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [make_json_safe(item) for item in value]
    return str(value)


def load_semantic_fixture(path: str) -> dict[str, Any]:
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise N4WorkerSmokeBlocked(f"N4 worker bounded smoke semantic fixture not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise N4WorkerSmokeBlocked(f"N4 worker bounded smoke semantic fixture JSON invalid: {path}") from exc
    if not isinstance(payload, Mapping):
        raise N4WorkerSmokeBlocked("N4 worker bounded smoke semantic fixture must be a JSON object")
    evaluations = payload.get("evaluations")
    if not isinstance(evaluations, Sequence) or isinstance(evaluations, (str, bytes, bytearray)) or not evaluations:
        raise N4WorkerSmokeBlocked("N4 worker bounded smoke semantic fixture must contain non-empty evaluations")
    source_oracle_run_id = str(payload.get("source_oracle_run_id") or "fixture")
    fixture_trace = {
        "fixture_only": bool(payload.get("fixture_only", True)),
        "source_oracle_run_id": source_oracle_run_id,
        "not_new_market_decision": bool(payload.get("not_new_market_decision", True)),
    }
    normalized_evaluations = []
    for row in evaluations:
        if not isinstance(row, Mapping):
            raise N4WorkerSmokeBlocked("N4 worker bounded smoke semantic fixture evaluations must be JSON objects")
        normalized_evaluations.append({**fixture_trace, **dict(row)})
    return {
        **fixture_trace,
        "evaluations": normalized_evaluations,
        "previous_states": _normalize_fixture_previous_states(payload.get("previous_states") or {}),
    }


def load_semantic_oracle_evaluations(
    conn: Any,
    *,
    semantic_oracle_run_id: str,
    max_events: int,
) -> dict[str, Any]:
    """Build smoke evaluations from an existing N4 oracle run without mutation."""

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT event_id, event_type, trade_date, asset_kind, identity_key, event_time, payload_json
            FROM common_event_outbox
            WHERE source_layer='N4_trigger'
              AND source_run_id=%s
              AND event_type IN ('TriggerMatched', 'TriggerPendingMarketData', 'TriggerStateChanged')
            ORDER BY outbox_id ASC
            LIMIT %s
            """,
            (semantic_oracle_run_id, max_events),
        )
        rows = _dict_rows(cur)
    evaluations: list[dict[str, Any]] = []
    previous_states: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        payload = dict(row.get("payload_json") or {})
        event_type = str(row.get("event_type") or payload.get("output_event_type") or "")
        source_event_id = (
            payload.get("source_event_id")
            or payload.get("source_market_event_or_projection_id")
            or payload.get("source_trigger_event_id")
            or row.get("event_id")
        )
        evaluation = {
            **payload,
            "fixture_only": True,
            "source_oracle_run_id": semantic_oracle_run_id,
            "not_new_market_decision": True,
            "source_event_id": source_event_id,
            "trade_date": payload.get("trade_date") or row.get("trade_date"),
            "asset_kind": payload.get("asset_kind") or row.get("asset_kind"),
            "identity_key": payload.get("identity_key") or row.get("identity_key"),
            "event_time": payload.get("event_time") or row.get("event_time"),
            "output_event_type": event_type,
            "new_trigger_fact": event_type == "TriggerMatched",
        }
        evaluations.append(evaluation)
        if event_type == "TriggerMatched":
            previous_states[_state_lookup_key(evaluation)] = {
                **evaluation,
                "current_status": "matched",
                "trigger_live": True,
            }
    if not evaluations:
        raise N4WorkerSmokeBlocked(
            f"N4 worker bounded smoke semantic oracle produced no evaluations: {semantic_oracle_run_id}"
        )
    return {
        "fixture_only": True,
        "source_oracle_run_id": semantic_oracle_run_id,
        "not_new_market_decision": True,
        "evaluations": evaluations,
        "previous_states": previous_states,
    }


def semantic_source_event_ids(
    evaluations: Sequence[Mapping[str, Any]],
    *,
    max_events: int,
) -> list[str]:
    """Return ordered unique N3 source event ids referenced by semantic evaluations."""

    source_event_ids: list[str] = []
    seen: set[str] = set()
    for row in evaluations:
        source_event_id = str(row.get("source_event_id") or "").strip()
        if not source_event_id or source_event_id in seen:
            continue
        seen.add(source_event_id)
        source_event_ids.append(source_event_id)
        if len(source_event_ids) >= max_events:
            break
    return source_event_ids


def build_worker_smoke_plan(
    *,
    smoke_run_id: str,
    consumer_name: str,
    source_events: Sequence[Mapping[str, Any]],
    evaluations: Sequence[Mapping[str, Any]],
    previous_states: Mapping[str, Mapping[str, Any]],
    existing_consume_keys: set[str] | frozenset[str],
    max_events: int,
) -> dict[str, Any]:
    seen_consume_keys: set[str] = set()
    accepted_source_events: list[dict[str, Any]] = []
    skipped_source_events: list[dict[str, Any]] = []
    for row in sorted(source_events, key=lambda item: int(item.get("outbox_id") or 0)):
        if len(accepted_source_events) >= max_events:
            skipped_source_events.append({"event_id": row.get("event_id"), "skip_reason": "max_events_reached"})
            continue
        if row.get("event_type") != "MarketSnapshotUpdated" or row.get("source_layer") != "N3_market_data":
            skipped_source_events.append({"event_id": row.get("event_id"), "skip_reason": "unsupported_source_event"})
            continue
        consume_key = source_event_consume_key(consumer_name, str(row.get("event_id") or ""))
        if consume_key in existing_consume_keys or consume_key in seen_consume_keys:
            skipped_source_events.append({"event_id": row.get("event_id"), "skip_reason": "duplicate_source_event"})
            continue
        seen_consume_keys.add(consume_key)
        accepted_source_events.append({**dict(row), "consume_key": consume_key})

    accepted_ids = {str(row.get("event_id")) for row in accepted_source_events}
    transition_plans: list[dict[str, Any]] = []
    for evaluation in evaluations:
        source_event_id = str(evaluation.get("source_event_id") or "")
        if source_event_id not in accepted_ids:
            continue
        state_key = _state_lookup_key(evaluation)
        transition_plans.extend(
            build_transition_event_plans(
                previous_state=previous_states.get(state_key),
                current_evaluation=evaluation,
                source_event_id=source_event_id,
                trade_date=str(evaluation.get("trade_date") or ""),
            )
        )

    return {
        "result": "DRY_VALIDATION_PASS",
        "smoke_run_id": smoke_run_id,
        "consumer_name": consumer_name,
        "accepted_source_events": accepted_source_events,
        "skipped_source_events": skipped_source_events,
        "transition_event_plans": transition_plans,
        "summary": {
            "accepted_source_event_count": len(accepted_source_events),
            "skipped_duplicate_source_event_count": sum(
                1 for row in skipped_source_events if row.get("skip_reason") == "duplicate_source_event"
            ),
            "transition_event_plan_count": len(transition_plans),
            "TriggerMatched": sum(1 for row in transition_plans if row.get("output_event_type") == "TriggerMatched"),
            "TriggerPendingMarketData": sum(
                1 for row in transition_plans if row.get("output_event_type") == "TriggerPendingMarketData"
            ),
            "TriggerStateChanged": sum(
                1 for row in transition_plans if row.get("output_event_type") == "TriggerStateChanged"
            ),
        },
        "side_effects": {
            "database_written": False,
            "worker_started": False,
            "n3_outbox_status_updated": False,
            "n5_n6_entered": False,
            "delivery_push_voice_mobile": False,
            "sim_position_order_trade_real_trade": False,
        },
    }


def build_smoke_write_plan(
    *,
    smoke_run_id: str,
    consumer_name: str,
    source_condition_run_id: str,
    source_market_data_run_id: str,
    for_trade_date: str,
    source_trade_date: str,
    prev_trade_date: str,
    dry_run_plan: Mapping[str, Any],
) -> dict[str, Any]:
    accepted_source_events = [dict(row) for row in dry_run_plan.get("accepted_source_events", [])]
    transition_event_plans = [dict(row) for row in dry_run_plan.get("transition_event_plans", [])]
    run_row = {
        "run_id": smoke_run_id,
        "source_condition_run_id": source_condition_run_id,
        "source_market_data_run_id": source_market_data_run_id,
        "for_trade_date": for_trade_date,
        "source_trade_date": source_trade_date,
        "prev_trade_date": prev_trade_date,
        "mode": "execute",
        "status": "passed",
        "p0_count": 0,
        "p1_count": 0,
        "p2_count": 0,
        "trigger_state_row_count": 0,
        "trigger_match_row_count": sum(1 for row in transition_event_plans if row.get("output_event_type") == "TriggerMatched"),
        "trigger_event_outbox_count": len(transition_event_plans),
        "worker_started": False,
        "raw_json": {
            "bounded_smoke_run_id": smoke_run_id,
            "consumer_name": consumer_name,
            "source_event_count": len(accepted_source_events),
            "n3_outbox_status_updated": False,
            "long_running_worker_started": False,
        },
    }
    quality_rows = [
        {
            "run_id": smoke_run_id,
            "source_condition_run_id": source_condition_run_id,
            "for_trade_date": for_trade_date,
            "source_trade_date": source_trade_date,
            "data_domain": "common",
            "layer_scope": "trigger_run",
            "table_name": "common_event_inbox",
            "gate_code": "n4_worker_bounded_smoke_source_events_selected",
            "gate_name": "N4 worker bounded smoke source events selected",
            "severity": "P0",
            "status": "passed",
            "expected_value": "<=max_events",
            "actual_value": str(len(accepted_source_events)),
            "details": {"consumer_name": consumer_name, "bounded_smoke_run_id": smoke_run_id},
        },
        {
            "run_id": smoke_run_id,
            "source_condition_run_id": source_condition_run_id,
            "for_trade_date": for_trade_date,
            "source_trade_date": source_trade_date,
            "data_domain": "common",
            "layer_scope": "event_contract",
            "table_name": "common_event_outbox",
            "gate_code": "n4_worker_bounded_smoke_n3_outbox_not_updated",
            "gate_name": "N4 worker bounded smoke does not update N3 outbox",
            "severity": "P0",
            "status": "passed",
            "expected_value": "false",
            "actual_value": "false",
            "details": {"n3_outbox_status_updated": False},
        },
    ]
    inbox_rows = [_build_inbox_row(row, consumer_name=consumer_name, smoke_run_id=smoke_run_id) for row in accepted_source_events]
    checkpoint_rows = _build_checkpoint_rows(inbox_rows, consumer_name=consumer_name, smoke_run_id=smoke_run_id)
    state_rows_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    match_rows: list[dict[str, Any]] = []
    outbox_rows: list[dict[str, Any]] = []
    for plan in transition_event_plans:
        state_row = _build_state_row(
            plan,
            smoke_run_id=smoke_run_id,
            source_condition_run_id=source_condition_run_id,
            for_trade_date=for_trade_date,
        )
        state_key = _state_unique_key(state_row)
        state_row["state_unique_key"] = state_key
        state_rows_by_key[state_key] = _merge_state_row(state_rows_by_key.get(state_key), state_row)
        outbox_row = _build_outbox_row(plan, smoke_run_id=smoke_run_id)
        outbox_rows.append(outbox_row)
        if plan.get("output_event_type") == "TriggerMatched":
            match_rows.append(
                _build_match_row(
                    plan,
                    smoke_run_id=smoke_run_id,
                    source_condition_run_id=source_condition_run_id,
                    for_trade_date=for_trade_date,
                    output_event_id=outbox_row["event_id"],
                    state_unique_key=state_key,
                )
            )
    state_rows = list(state_rows_by_key.values())
    run_row["trigger_state_row_count"] = len(state_rows)
    event_distribution = {
        event_type: sum(1 for row in outbox_rows if row.get("event_type") == event_type)
        for event_type in ("TriggerMatched", "TriggerPendingMarketData", "TriggerStateChanged")
    }
    return {
        "allowed_write_tables": sorted(ALLOWED_SMOKE_WRITE_TABLES),
        "forbidden_write_tables": {
            "N3_common_event_outbox_status_update": False,
            "N5_N6": False,
            "delivery_push_voice_mobile": False,
            "sim_position_order_trade_real_trade": False,
        },
        "run_row": run_row,
        "quality_rows": quality_rows,
        "inbox_rows": inbox_rows,
        "checkpoint_rows": checkpoint_rows,
        "state_rows": state_rows,
        "match_rows": match_rows,
        "outbox_rows": outbox_rows,
        "event_distribution": event_distribution,
        "write_counts": {
            "common_trigger_run": 1,
            "common_trigger_quality_item": len(quality_rows),
            "common_event_inbox": len(inbox_rows),
            "common_event_consumer_checkpoint": len(checkpoint_rows),
            "common_trigger_state": len(state_rows),
            "common_trigger_match": len(match_rows),
            "common_event_outbox": len(outbox_rows),
        },
    }


def fetch_source_events_for_smoke(
    conn: Any,
    *,
    source_run_id: str,
    source_event_type: str,
    source_trade_date: str,
    max_events: int,
    consumer_name: str | None = None,
) -> list[dict[str, Any]]:
    consumer_filter = ""
    params: list[Any] = [source_event_type, source_trade_date, source_run_id]
    if consumer_name:
        consumer_filter = """
              AND NOT EXISTS (
                SELECT 1
                FROM common_event_inbox i
                WHERE i.consumer_name=%s
                  AND i.event_id=o.event_id
                  AND i.source_layer='N3_market_data'
                  AND i.event_type=o.event_type
                  AND i.source_run_id=o.source_run_id
              )
              AND NOT EXISTS (
                SELECT 1
                FROM common_event_consumer_checkpoint c
                WHERE c.consumer_name=%s
                  AND c.source_layer='N3_market_data'
                  AND (
                    c.last_event_id=o.event_id
                    OR c.checkpoint_payload ->> 'source_event_id' = o.event_id
                    OR c.checkpoint_payload ->> 'source_event_consume_key' = %s || '|' || o.event_id
                  )
              )
        """
        params.extend([consumer_name, consumer_name, consumer_name])
    params.append(max_events)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT outbox_id, event_id, event_type, event_schema_version, trade_date, asset_kind, identity_key,
                   event_time, source_layer, source_run_id, dedup_key, partition_key, payload_json, status, created_at
            FROM common_event_outbox o
            WHERE o.source_layer='N3_market_data'
              AND event_type=%s
              AND trade_date=%s
              AND source_run_id=%s
              AND status='pending'
              {consumer_filter}
            ORDER BY outbox_id ASC
            LIMIT %s
            """,
            tuple(params),
        )
        return _dict_rows(cur)


def fetch_source_events_by_event_ids_for_smoke(
    conn: Any,
    *,
    source_run_id: str,
    source_event_type: str,
    source_trade_date: str,
    source_event_ids: Sequence[str],
) -> list[dict[str, Any]]:
    """Fetch pending N3 source events by deterministic semantic oracle event ids."""

    ordered_ids = [str(event_id) for event_id in source_event_ids if str(event_id)]
    if not ordered_ids:
        raise N4WorkerSmokeBlocked("N4 worker bounded smoke semantic oracle has no source_event_id values")
    placeholders = ", ".join(["%s"] * len(ordered_ids))
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT outbox_id, event_id, event_type, event_schema_version, trade_date, asset_kind, identity_key,
                   event_time, source_layer, source_run_id, dedup_key, partition_key, payload_json, status, created_at
            FROM common_event_outbox
            WHERE source_layer='N3_market_data'
              AND event_type=%s
              AND trade_date=%s
              AND source_run_id=%s
              AND status='pending'
              AND event_id IN ({placeholders})
            """,
            (source_event_type, source_trade_date, source_run_id, *ordered_ids),
        )
        rows_by_event_id = {str(row["event_id"]): row for row in _dict_rows(cur)}
    missing = [event_id for event_id in ordered_ids if event_id not in rows_by_event_id]
    if missing:
        raise N4WorkerSmokeBlocked(
            "N4 worker bounded smoke semantic oracle referenced source events that are not pending N3 inputs: "
            + ", ".join(missing[:10])
        )
    return [rows_by_event_id[event_id] for event_id in ordered_ids]


def fetch_existing_consume_keys(
    conn: Any,
    *,
    consumer_name: str,
    source_run_id: str,
    source_event_type: str,
) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT consume_key
            FROM (
              SELECT COALESCE(NULLIF(raw_json ->> 'source_event_consume_key', ''), %s || '|' || event_id) AS consume_key
              FROM common_event_inbox
              WHERE consumer_name=%s
                AND source_layer='N3_market_data'
                AND event_type=%s
                AND source_run_id=%s
              UNION
              SELECT COALESCE(
                       NULLIF(checkpoint_payload ->> 'source_event_consume_key', ''),
                       CASE WHEN last_event_id IS NOT NULL AND last_event_id <> '' THEN %s || '|' || last_event_id END
                     ) AS consume_key
              FROM common_event_consumer_checkpoint
              WHERE consumer_name=%s
                AND source_layer='N3_market_data'
            ) existing
            WHERE consume_key IS NOT NULL
            """,
            (consumer_name, consumer_name, source_event_type, source_run_id, consumer_name, consumer_name),
        )
        return {str(row[0]) for row in cur.fetchall()}


def fetch_smoke_run_metadata(conn: Any, *, source_run_id: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT source_condition_run_id, run_id AS source_market_data_run_id, for_trade_date, source_trade_date
            FROM common_market_data_run
            WHERE run_id=%s
            """,
            (source_run_id,),
        )
        row = cur.fetchone()
    if not row:
        raise N4WorkerSmokeBlocked(f"N4 worker bounded smoke source market data run not found: {source_run_id}")
    return {
        "source_condition_run_id": row[0],
        "source_market_data_run_id": row[1],
        "for_trade_date": row[2],
        "source_trade_date": row[3],
        "prev_trade_date": row[3],
    }


def fetch_smoke_baseline_counts(conn: Any, *, smoke_run_id: str, consumer_name: str) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              (SELECT count(*) FROM common_trigger_run WHERE run_id=%s)::int AS common_trigger_run,
              (SELECT count(*) FROM common_trigger_quality_item WHERE run_id=%s)::int AS common_trigger_quality_item,
              (SELECT count(*) FROM common_trigger_state WHERE run_id=%s)::int AS common_trigger_state,
              (SELECT count(*) FROM common_trigger_match WHERE run_id=%s)::int AS common_trigger_match,
              (SELECT count(*) FROM common_event_outbox WHERE source_layer='N4_trigger' AND source_run_id=%s)::int AS common_event_outbox,
              (SELECT count(*) FROM common_event_inbox WHERE consumer_name=%s AND raw_json ->> 'bounded_smoke_run_id' = %s)::int AS common_event_inbox,
              (SELECT count(*) FROM common_event_consumer_checkpoint WHERE consumer_name=%s AND checkpoint_payload ->> 'bounded_smoke_run_id' = %s)::int AS common_event_consumer_checkpoint
            """,
            (
                smoke_run_id,
                smoke_run_id,
                smoke_run_id,
                smoke_run_id,
                smoke_run_id,
                consumer_name,
                smoke_run_id,
                consumer_name,
                smoke_run_id,
            ),
        )
        row = cur.fetchone()
        names = [desc.name for desc in cur.description]
    return {name: int(value) for name, value in zip(names, row)}


def persist_worker_smoke_write_plan(conn: Any, write_plan: Mapping[str, Any]) -> dict[str, int]:
    """Persist a prebuilt scoped smoke plan.

    This function intentionally contains no path that updates N3 outbox status.
    """

    with conn.cursor() as cur:
        _insert_trigger_run(cur, write_plan["run_row"])
        for row in write_plan["quality_rows"]:
            _insert_quality_item(cur, row)
        for row in write_plan["inbox_rows"]:
            _insert_inbox_row(cur, row)
        for row in write_plan["checkpoint_rows"]:
            _insert_checkpoint_row(cur, row)
        state_ids_by_key: dict[tuple[Any, ...], int] = {}
        for row in write_plan["state_rows"]:
            state_key = row.get("state_unique_key") or _state_unique_key(row)
            state_ids_by_key[state_key] = _insert_state_row(cur, row)
        for source_match_row in write_plan["match_rows"]:
            match_row = dict(source_match_row)
            state_key = match_row.pop("state_unique_key", None)
            if state_key not in state_ids_by_key:
                raise N4WorkerSmokeBlocked(f"N4 worker smoke matched row has no coalesced state row: {state_key}")
            match_row["trigger_state_id"] = state_ids_by_key[state_key]
            _insert_match_row(cur, match_row)
        for row in write_plan["outbox_rows"]:
            _insert_outbox_row(cur, row)
    return dict(write_plan["write_counts"])


def build_worker_rollback_sql(*, smoke_run_id: str, consumer_name: str = DEFAULT_CONSUMER_NAME) -> str:
    return f"""-- N4 worker bounded smoke rollback.
-- Target smoke run_id: {smoke_run_id}
-- Consumer: {consumer_name}
-- This draft is intentionally guarded; review downstream refs before enabling row removal.

DO $$
BEGIN
  RAISE EXCEPTION 'N4 worker bounded smoke rollback is guarded. Review delivered/delivering N4 outbox, active worker heartbeat, N5 refs, N6 refs, user/sim/order/trade/position refs before enabling scoped row removal for {smoke_run_id}.';
END $$;

-- Guard checklist before row removal:
-- 1. N4 common_event_outbox delivered/delivering rows for {smoke_run_id} must be 0.
-- 2. N5 common_action_run/common_action_event refs for {smoke_run_id} must be 0.
-- 3. N6/user_signal_projection/user_signal_card/user_notification_queue refs must be 0.
-- 4. user_sim/order/trade/position/real_trade refs must be 0.
-- 5. worker heartbeat/running status for {smoke_run_id} must be stopped.
-- 6. N3 facts and N3 common_event_outbox status must not be touched.

DELETE FROM common_event_inbox
WHERE consumer_name = '{consumer_name}'
  AND raw_json ->> 'bounded_smoke_run_id' = '{smoke_run_id}';

DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = '{consumer_name}'
  AND checkpoint_payload ->> 'bounded_smoke_run_id' = '{smoke_run_id}';

DELETE FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = '{smoke_run_id}';

DELETE FROM common_trigger_match
WHERE run_id = '{smoke_run_id}';

DELETE FROM common_trigger_state
WHERE run_id = '{smoke_run_id}';

DELETE FROM common_trigger_quality_item
WHERE run_id = '{smoke_run_id}';

DELETE FROM common_trigger_run
WHERE run_id = '{smoke_run_id}';
"""


def build_implementation_report() -> dict[str, Any]:
    return {
        "result": "IMPLEMENTATION_PASS",
        "gate": "N4_WORKER_BOUNDED_SMOKE_IMPLEMENTATION_GATE",
        "layer_role": "N4_trigger",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "worker_started": False,
        "database_written": False,
        "n4_executed": False,
        "n3_outbox_updated": False,
        "n5_n6_entered": False,
        "state_transition_helpers": [
            "inactive -> pending_market_data",
            "pending_market_data -> matched",
            "inactive -> matched",
            "matched -> inactive",
            "pending_market_data -> inactive",
            "matched -> matched material change",
        ],
        "idempotency_helpers": [
            "source_event_consume_key",
            "trigger_state_key",
            "trigger_match_dedup_key",
            "trigger_pending_dedup_key",
            "trigger_state_changed_dedup_key",
        ],
        "consumer_boundary": CONSUMER_BOUNDARY,
        "forbidden_scope": {
            "n3_outbox_status_update": False,
            "n5_n6": False,
            "delivery_push_voice_mobile": False,
            "proposal_order_trade": False,
            "sim_position_pnl_real_trade": False,
            "old_system": False,
        },
    }


def format_implementation_report(report: Mapping[str, Any]) -> str:
    side_effects = report.get("side_effects") if isinstance(report.get("side_effects"), Mapping) else {}
    database_written = bool(report.get("database_written") or side_effects.get("database_written"))
    scoped_n4_database_writes = bool(
        report.get("scoped_n4_database_writes") or side_effects.get("scoped_n4_database_writes")
    )
    worker_started = bool(report.get("worker_started") or side_effects.get("worker_started"))
    n3_outbox_updated = bool(report.get("n3_outbox_updated") or side_effects.get("n3_outbox_updated"))
    n5_n6_entered = bool(report.get("n5_n6_entered") or side_effects.get("n5_n6_entered"))
    return "\n".join(
        [
            "# N4 Worker Bounded Smoke Implementation",
            "",
            f"Result: `{report['result']}`",
            "",
            "This implementation adds side-effect-free bounded worker smoke planning, state transition helpers, CLI guards, and rollback draft artifacts.",
            "",
            "## Boundary",
            "",
            f"- scoped_n4_database_writes={str(scoped_n4_database_writes).lower()}",
            f"- database_written={str(database_written).lower()}",
            f"- worker_started={str(worker_started).lower()}",
            f"- n3_outbox_updated={str(n3_outbox_updated).lower()}",
            f"- n5_n6_entered={str(n5_n6_entered).lower()}",
            "- real_trade=false",
            "",
            "## Next Gate",
            "",
            "`N4_WORKER_BOUNDED_SMOKE_IMPLEMENTATION_POST_REVIEW_GATE`",
            "",
        ]
    )


def _state_lookup_key(row: Mapping[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("trade_date") or ""),
            str(row.get("asset_kind") or ""),
            str(row.get("identity_key") or ""),
            str(row.get("direction") or ""),
            str(row.get("signal_type") or ""),
            str(row.get("condition_key") or ""),
        ]
    )


def _state_unique_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("run_id"),
        row.get("for_trade_date"),
        row.get("asset_kind"),
        row.get("identity_key"),
        row.get("direction"),
        row.get("signal_type"),
        row.get("condition_key"),
        row.get("trigger_period"),
        row.get("trigger_bucket"),
    )


def _merge_state_row(existing: Mapping[str, Any] | None, candidate: Mapping[str, Any]) -> dict[str, Any]:
    if existing is None:
        merged = dict(candidate)
    elif _state_row_priority(candidate) > _state_row_priority(existing):
        merged = dict(candidate)
    else:
        merged = dict(existing)

    output_event_types: list[str] = []
    for row in (existing, candidate):
        if not row:
            continue
        raw_json = row.get("raw_json") if isinstance(row.get("raw_json"), Mapping) else {}
        for event_type in raw_json.get("coalesced_output_event_types", []):
            if event_type not in output_event_types:
                output_event_types.append(str(event_type))
        event_type = row.get("output_event_type")
        if event_type and str(event_type) not in output_event_types:
            output_event_types.append(str(event_type))
    raw_json = dict(merged.get("raw_json") or {})
    raw_json["coalesced_output_event_types"] = output_event_types
    raw_json["coalesced_state_event_count"] = len(output_event_types)
    merged["raw_json"] = make_json_safe(raw_json)
    return merged


def _state_row_priority(row: Mapping[str, Any]) -> int:
    event_type = row.get("output_event_type")
    if event_type == "TriggerMatched":
        return 30
    if event_type == "TriggerPendingMarketData":
        return 20
    if event_type == "TriggerStateChanged":
        return 10
    return 0


def _normalize_fixture_previous_states(value: Any) -> dict[str, Mapping[str, Any]]:
    if isinstance(value, Mapping):
        normalized: dict[str, Mapping[str, Any]] = {}
        for key, item in value.items():
            if isinstance(item, Mapping):
                normalized[str(key)] = dict(item)
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        normalized = {}
        for item in value:
            if isinstance(item, Mapping):
                normalized[_state_lookup_key(item)] = dict(item)
        return normalized
    return {}


def _scenario_duplicate_source_event_counts(
    full_payload: Mapping[str, Any],
    scenario_payload: Mapping[str, Any],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    raw_counts = scenario_payload.get("duplicate_source_event_counts")
    if isinstance(raw_counts, Mapping):
        for event_id, count in raw_counts.items():
            try:
                normalized_count = int(count)
            except (TypeError, ValueError) as exc:
                raise N4WorkerSmokeBlocked(
                    f"N4 worker bounded smoke scenario duplicate count invalid for {event_id}: {count}"
                ) from exc
            counts[str(event_id)] = counts.get(str(event_id), 0) + normalized_count

    raw_ids = scenario_payload.get("duplicate_source_event_ids") or scenario_payload.get("duplicate_event_ids") or []
    if isinstance(raw_ids, Sequence) and not isinstance(raw_ids, (str, bytes, bytearray)):
        for event_id in raw_ids:
            counts[str(event_id)] = counts.get(str(event_id), 0) + 1

    raw_rows = scenario_payload.get("duplicate_source_rows") or []
    if isinstance(raw_rows, Sequence) and not isinstance(raw_rows, (str, bytes, bytearray)):
        for row in raw_rows:
            if isinstance(row, Mapping):
                event_id = str(row.get("event_id") or "")
                if event_id:
                    try:
                        repeat_count = int(row.get("repeat_count") or 1)
                    except (TypeError, ValueError) as exc:
                        raise N4WorkerSmokeBlocked(
                            f"N4 worker bounded smoke scenario repeat_count invalid for {event_id}: {row.get('repeat_count')}"
                        ) from exc
                    counts[event_id] = counts.get(event_id, 0) + repeat_count

    helper_model = _scenario_helper_model(full_payload)
    if helper_model:
        existing_event_ids = _event_ids_from_consume_keys(helper_model.get("modeled_existing_consume_keys") or [])
        skipped_ids = helper_model.get("skipped_duplicate_event_ids") or []
        if isinstance(skipped_ids, Sequence) and not isinstance(skipped_ids, (str, bytes, bytearray)):
            selected_count = len(full_payload.get("selected_source_events", {}).get("event_ids", []) or [])
            modeled_count = int(helper_model.get("modeled_source_event_rows") or selected_count)
            inferred_duplicate_slots = max(modeled_count - selected_count, 0)
            for event_id in skipped_ids:
                event_key = str(event_id)
                if event_key in existing_event_ids:
                    continue
                if inferred_duplicate_slots <= 0:
                    continue
                counts[event_key] = counts.get(event_key, 0) + 1
                inferred_duplicate_slots -= 1

    return counts


def _scenario_existing_consume_keys(
    full_payload: Mapping[str, Any],
    scenario_payload: Mapping[str, Any],
    *,
    consumer_name: str,
) -> set[str]:
    existing_keys: set[str] = set()
    for source in (
        scenario_payload.get("existing_consume_keys"),
        scenario_payload.get("modeled_existing_consume_keys"),
    ):
        if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
            existing_keys.update(str(key) for key in source if str(key))

    for source in (
        scenario_payload.get("existing_consume_event_ids"),
        scenario_payload.get("modeled_existing_consume_event_ids"),
    ):
        if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
            existing_keys.update(source_event_consume_key(consumer_name, str(event_id)) for event_id in source if str(event_id))

    helper_model = _scenario_helper_model(full_payload)
    if helper_model:
        helper_keys = helper_model.get("modeled_existing_consume_keys") or []
        if isinstance(helper_keys, Sequence) and not isinstance(helper_keys, (str, bytes, bytearray)):
            existing_keys.update(str(key) for key in helper_keys if str(key))
    return existing_keys


def _scenario_failure_injection(scenario_payload: Mapping[str, Any]) -> dict[str, Any]:
    raw = scenario_payload.get("failure_injection") or scenario_payload.get("retry_failure_injection") or {}
    if raw in (None, False):
        return {"enabled": False, "point": None}
    if raw is True:
        return {"enabled": True, "point": "before_write"}
    if not isinstance(raw, Mapping):
        raise N4WorkerSmokeBlocked("N4 worker bounded smoke failure_injection must be a JSON object")
    enabled = bool(raw.get("enabled", False))
    point = raw.get("point") or raw.get("failure_injection_point") or ("before_write" if enabled else None)
    allowed_points = {None, "before_write", "after_persist_before_commit"}
    if point not in allowed_points:
        raise N4WorkerSmokeBlocked(f"N4 worker bounded smoke unsupported failure injection point: {point}")
    return {
        "enabled": enabled,
        "point": point,
        "reason": raw.get("reason") or raw.get("blocked_reason") or "idempotency_retry_failure_injection",
    }


def _scenario_helper_model(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    scenario_cases = payload.get("scenario_cases")
    if not isinstance(scenario_cases, Mapping):
        return None
    helper_model = scenario_cases.get("duplicate_source_event_helper_model")
    return helper_model if isinstance(helper_model, Mapping) else None


def _event_ids_from_consume_keys(keys: Any) -> set[str]:
    if not isinstance(keys, Sequence) or isinstance(keys, (str, bytes, bytearray)):
        return set()
    event_ids = set()
    for key in keys:
        text = str(key)
        if "|" in text:
            event_ids.add(text.rsplit("|", 1)[-1])
        elif text:
            event_ids.add(text)
    return event_ids


def _build_inbox_row(row: Mapping[str, Any], *, consumer_name: str, smoke_run_id: str) -> dict[str, Any]:
    dedup_key = row.get("dedup_key") or row.get("consume_key") or source_event_consume_key(consumer_name, str(row["event_id"]))
    return {
        "consumer_name": consumer_name,
        "event_id": row["event_id"],
        "event_type": row["event_type"],
        "event_schema_version": row.get("event_schema_version") or "v1",
        "source_layer": row["source_layer"],
        "source_run_id": row.get("source_run_id") or "",
        "dedup_key": dedup_key,
        "partition_key": row.get("partition_key") or row.get("identity_key") or row["event_id"],
        "payload_json": make_json_safe(row.get("payload_json") or {}),
        "status": "processed",
        "raw_json": {
            "bounded_smoke_run_id": smoke_run_id,
            "source_outbox_id": row.get("outbox_id"),
            "source_event_consume_key": row.get("consume_key"),
            "source_event_time": make_json_safe(row.get("event_time")),
            "n3_outbox_status_updated": False,
        },
    }


def _build_checkpoint_rows(
    inbox_rows: Sequence[Mapping[str, Any]],
    *,
    consumer_name: str,
    smoke_run_id: str,
) -> list[dict[str, Any]]:
    latest_by_partition: dict[str, Mapping[str, Any]] = {}
    for row in inbox_rows:
        latest_by_partition[str(row["partition_key"])] = row
    return [
        {
            "consumer_name": consumer_name,
            "partition_key": partition_key,
            "source_layer": "N3_market_data",
            "last_event_id": row["event_id"],
            "last_event_time": row.get("payload_json", {}).get("event_time"),
            "last_outbox_id": row.get("raw_json", {}).get("source_outbox_id"),
        "checkpoint_payload": make_json_safe({
            "bounded_smoke_run_id": smoke_run_id,
            "source_event_id": row["event_id"],
            "source_event_consume_key": row.get("raw_json", {}).get("source_event_consume_key"),
        }),
        }
        for partition_key, row in latest_by_partition.items()
    ]


def _build_state_row(
    plan: Mapping[str, Any],
    *,
    smoke_run_id: str,
    source_condition_run_id: str,
    for_trade_date: str,
) -> dict[str, Any]:
    trigger_period = _trigger_period(plan)
    current_status = str(plan.get("current_status") or "inactive")
    return {
        "run_id": smoke_run_id,
        "source_condition_run_id": source_condition_run_id,
        "for_trade_date": for_trade_date,
        "asset_kind": plan.get("asset_kind"),
        "identity_key": plan.get("identity_key"),
        "direction": plan.get("direction"),
        "signal_type": plan.get("signal_type"),
        "condition_key": plan.get("condition_key"),
        "trigger_period": trigger_period,
        "trigger_bucket": str(plan.get("trigger_bucket") or trigger_period),
        "current_status": current_status,
        "last_source_event_id": plan.get("source_event_id"),
        "data_quality_status": str(plan.get("data_quality_status") or ("passed" if current_status == "matched" else "pending")),
        "context_hash": plan.get("context_hash"),
        "match_count": 1 if plan.get("output_event_type") == "TriggerMatched" else 0,
        "first_matched_at": plan.get("trigger_time") if plan.get("output_event_type") == "TriggerMatched" else None,
        "last_matched_at": plan.get("trigger_time") if plan.get("output_event_type") == "TriggerMatched" else None,
        "cleared_at": plan.get("trigger_time") if current_status == "inactive" else None,
        "raw_json": make_json_safe({**dict(plan), "bounded_smoke_run_id": smoke_run_id}),
        "trigger_live": bool(plan.get("trigger_live")),
        "trigger_mark_candidate": plan.get("trigger_mark_candidate") or "normal",
        "primary_trigger_period": plan.get("primary_trigger_period"),
        "all_trigger_periods": make_json_safe(plan.get("all_trigger_periods") or []),
        "projection_30m_flag": bool(plan.get("projection_30m_flag")),
        "projection_30m_type": plan.get("projection_30m_type") or "none",
        "output_event_type": plan.get("output_event_type"),
    }


def _build_match_row(
    plan: Mapping[str, Any],
    *,
    smoke_run_id: str,
    source_condition_run_id: str,
    for_trade_date: str,
    output_event_id: str,
    state_unique_key: tuple[Any, ...],
) -> dict[str, Any]:
    trigger_period = _trigger_period(plan)
    return {
        "run_id": smoke_run_id,
        "source_event_id": plan.get("source_event_id"),
        "source_event_type": plan.get("source_event_type") or "MarketSnapshotUpdated",
        "source_condition_run_id": source_condition_run_id,
        "source_market_subscription_id": plan.get("source_market_subscription_id"),
        "for_trade_date": for_trade_date,
        "asset_kind": plan.get("asset_kind"),
        "identity_key": plan.get("identity_key"),
        "direction": plan.get("direction"),
        "signal_type": plan.get("signal_type"),
        "condition_key": plan.get("condition_key"),
        "trigger_price": plan.get("trigger_price"),
        "trigger_time": plan.get("trigger_time") or plan.get("event_time"),
        "trigger_period": trigger_period,
        "trigger_bucket": str(plan.get("trigger_bucket") or trigger_period),
        "data_quality_status": plan.get("data_quality_status") or "passed",
        "output_event_type": "TriggerMatched",
        "output_event_id": output_event_id,
        "dedup_key": plan.get("dedup_key"),
        "context_hash": plan.get("context_hash"),
        "raw_json": make_json_safe({**dict(plan), "bounded_smoke_run_id": smoke_run_id}),
        "trigger_mark_candidate": plan.get("trigger_mark_candidate") or "normal",
        "state_unique_key": state_unique_key,
    }


def _build_outbox_row(plan: Mapping[str, Any], *, smoke_run_id: str) -> dict[str, Any]:
    event_type = str(plan["output_event_type"])
    dedup_key = str(plan["dedup_key"])
    event_schema_version = str(plan.get("event_schema_version") or "v1")
    event_id = build_stable_event_id(
        source_layer="N4_trigger",
        event_type=event_type,
        source_run_id=smoke_run_id,
        dedup_key=dedup_key,
        event_schema_version=event_schema_version,
    )
    payload_json = make_json_safe({
        **dict(plan),
        "event_id": event_id,
        "bounded_smoke_run_id": smoke_run_id,
        "n5_entry_allowed": bool(plan.get("n5_entry_allowed")) if event_type == "TriggerMatched" else False,
    })
    return {
        "event_id": event_id,
        "event_type": event_type,
        "event_schema_version": event_schema_version,
        "trade_date": plan.get("trade_date") or "",
        "asset_kind": plan.get("asset_kind"),
        "identity_key": plan.get("identity_key"),
        "event_time": plan.get("event_time") or plan.get("trigger_time"),
        "source_layer": "N4_trigger",
        "source_run_id": smoke_run_id,
        "dedup_key": dedup_key,
        "partition_key": plan.get("partition_key") or plan.get("identity_key"),
        "payload_json": payload_json,
        "status": "pending",
    }


def _trigger_period(plan: Mapping[str, Any]) -> str:
    if plan.get("trigger_period"):
        return str(plan["trigger_period"])
    if plan.get("primary_trigger_period"):
        return str(plan["primary_trigger_period"])
    periods = plan.get("all_trigger_periods") or []
    if isinstance(periods, Sequence) and not isinstance(periods, str) and periods:
        return str(periods[0])
    if plan.get("projection_30m_flag"):
        return "30m"
    return "D"


def _dict_rows(cur: Any) -> list[dict[str, Any]]:
    names = [desc.name for desc in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def _insert_trigger_run(cur: Any, row: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO common_trigger_run (
          run_id, source_condition_run_id, source_market_data_run_id, for_trade_date, source_trade_date, prev_trade_date,
          layer_role, mode, status, p0_count, p1_count, p2_count, trigger_state_row_count,
          trigger_match_row_count, trigger_event_outbox_count, generated_by, market_data_pulled,
          action_layer_touched, user_layer_touched, voice_touched, sim_touched, real_trade_touched,
          worker_started, raw_json, finished_at
        ) VALUES (
          %(run_id)s, %(source_condition_run_id)s, %(source_market_data_run_id)s, %(for_trade_date)s,
          %(source_trade_date)s, %(prev_trade_date)s, 'N4_trigger', %(mode)s, %(status)s, %(p0_count)s,
          %(p1_count)s, %(p2_count)s, %(trigger_state_row_count)s, %(trigger_match_row_count)s,
          %(trigger_event_outbox_count)s, 'n4_worker_bounded_smoke', false, false, false, false, false,
          false, %(worker_started)s, %(raw_json)s, now()
        )
        """,
        _pg_params(row),
    )


def _insert_quality_item(cur: Any, row: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO common_trigger_quality_item (
          run_id, source_condition_run_id, for_trade_date, source_trade_date, data_domain, layer_scope,
          table_name, gate_code, gate_name, severity, status, expected_value, actual_value, identity_key, details
        ) VALUES (
          %(run_id)s, %(source_condition_run_id)s, %(for_trade_date)s, %(source_trade_date)s, %(data_domain)s,
          %(layer_scope)s, %(table_name)s, %(gate_code)s, %(gate_name)s, %(severity)s, %(status)s,
          %(expected_value)s, %(actual_value)s, %(identity_key)s, %(details)s
        )
        """,
        _pg_params({**dict(row), "identity_key": row.get("identity_key")}),
    )


def _insert_inbox_row(cur: Any, row: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO common_event_inbox (
          consumer_name, event_id, event_type, event_schema_version, source_layer, source_run_id,
          dedup_key, partition_key, payload_json, status, processed_at, raw_json
        ) VALUES (
          %(consumer_name)s, %(event_id)s, %(event_type)s, %(event_schema_version)s, %(source_layer)s,
          %(source_run_id)s, %(dedup_key)s, %(partition_key)s, %(payload_json)s, %(status)s, now(), %(raw_json)s
        )
        """,
        _pg_params(row),
    )


def _insert_checkpoint_row(cur: Any, row: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO common_event_consumer_checkpoint (
          consumer_name, partition_key, source_layer, last_event_id, last_event_time, last_outbox_id, checkpoint_payload
        ) VALUES (
          %(consumer_name)s, %(partition_key)s, %(source_layer)s, %(last_event_id)s,
          %(last_event_time)s, %(last_outbox_id)s, %(checkpoint_payload)s
        )
        """,
        _pg_params(row),
    )


def _insert_state_row(cur: Any, row: Mapping[str, Any]) -> int:
    cur.execute(
        """
        INSERT INTO common_trigger_state (
          run_id, source_condition_run_id, for_trade_date, asset_kind, identity_key, direction, signal_type,
          condition_key, trigger_period, trigger_bucket, current_status, last_source_event_id,
          data_quality_status, context_hash, match_count, first_matched_at, last_matched_at, cleared_at,
          raw_json, trigger_live, trigger_mark_candidate, primary_trigger_period, all_trigger_periods,
          projection_30m_flag, projection_30m_type
        ) VALUES (
          %(run_id)s, %(source_condition_run_id)s, %(for_trade_date)s, %(asset_kind)s, %(identity_key)s,
          %(direction)s, %(signal_type)s, %(condition_key)s, %(trigger_period)s, %(trigger_bucket)s,
          %(current_status)s, %(last_source_event_id)s, %(data_quality_status)s, %(context_hash)s,
          %(match_count)s, %(first_matched_at)s, %(last_matched_at)s, %(cleared_at)s, %(raw_json)s,
          %(trigger_live)s, %(trigger_mark_candidate)s, %(primary_trigger_period)s, %(all_trigger_periods)s,
          %(projection_30m_flag)s, %(projection_30m_type)s
        )
        RETURNING trigger_state_id
        """,
        _pg_params(row),
    )
    return int(cur.fetchone()[0])


def _insert_match_row(cur: Any, row: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO common_trigger_match (
          run_id, trigger_state_id, source_event_id, source_event_type, source_condition_run_id,
          source_market_subscription_id, for_trade_date, asset_kind, identity_key, direction, signal_type,
          condition_key, trigger_price, trigger_time, trigger_period, trigger_bucket, data_quality_status,
          output_event_type, output_event_id, dedup_key, context_hash, raw_json, trigger_mark_candidate
        ) VALUES (
          %(run_id)s, %(trigger_state_id)s, %(source_event_id)s, %(source_event_type)s,
          %(source_condition_run_id)s, %(source_market_subscription_id)s, %(for_trade_date)s,
          %(asset_kind)s, %(identity_key)s, %(direction)s, %(signal_type)s, %(condition_key)s,
          %(trigger_price)s, %(trigger_time)s, %(trigger_period)s, %(trigger_bucket)s,
          %(data_quality_status)s, %(output_event_type)s, %(output_event_id)s, %(dedup_key)s,
          %(context_hash)s, %(raw_json)s, %(trigger_mark_candidate)s
        )
        """,
        _pg_params(row),
    )


def _insert_outbox_row(cur: Any, row: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO common_event_outbox (
          event_id, event_type, event_schema_version, trade_date, asset_kind, identity_key, event_time,
          source_layer, source_run_id, dedup_key, partition_key, payload_json, status
        ) VALUES (
          %(event_id)s, %(event_type)s, %(event_schema_version)s, %(trade_date)s, %(asset_kind)s,
          %(identity_key)s, %(event_time)s, %(source_layer)s, %(source_run_id)s, %(dedup_key)s,
          %(partition_key)s, %(payload_json)s, %(status)s
        )
        """,
        _pg_params(row),
    )


def _pg_params(row: Mapping[str, Any]) -> dict[str, Any]:
    params = dict(row)
    if Jsonb is None:
        return {key: make_json_safe(value) for key, value in params.items()}
    for key, value in list(params.items()):
        if isinstance(value, (dict, list)):
            params[key] = Jsonb(make_json_safe(value))
        else:
            params[key] = make_json_safe(value)
    return params
