"""N5 action event factory.

The factory is pure: it does not consume N4 outbox rows, read or pull market
data, write action facts, update checkpoints, write user projections, play
voice, write sim state, or submit real trades.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

from ashare_v3.events.ids import build_stable_event_id, join_dedup_parts
from ashare_v3.events.models import (
    DEFAULT_EVENT_SCHEMA_VERSION,
    EventEnvelope,
    N5_SOURCE_LAYER,
    utc_now,
    validate_event_envelope,
    validate_n5_event_type,
)


def build_n5_action_dedup_key(
    *,
    event_type: str,
    asset_kind: str,
    identity_key: str,
    trade_date: str,
    source_trigger_event_id: str,
    direction: str,
    signal_type: str,
    condition_key: str,
    trigger_period: str,
    action_state: str,
    action_mark: str | None,
    action_key: str | None = None,
) -> str:
    """Build the documented N5 action event dedup key."""

    parts = [
        "N5_action",
        event_type,
        asset_kind,
        identity_key,
        trade_date,
        "source_trigger_event_id",
        source_trigger_event_id,
        "direction",
        direction,
        "signal_type",
        signal_type,
        "condition_key",
        condition_key,
        "trigger_period",
        trigger_period,
        "action_state",
        action_state,
        "action_mark",
        action_mark or "none",
    ]
    if action_key:
        parts.extend(["action_key", action_key])
    return join_dedup_parts(*parts)


def build_n5_action_event(
    *,
    event_type: str,
    asset_kind: str,
    identity_key: str,
    trade_date: str,
    event_time: datetime,
    action_run_id: str,
    source_trigger_event_id: str,
    source_condition_run_id: str,
    direction: str,
    signal_type: str,
    condition_key: str,
    trigger_period: str,
    data_quality_status: str,
    source_trigger_run_id: str | None = None,
    source_trigger_state_id: int | str | None = None,
    source_trigger_match_id: int | str | None = None,
    original_condition_key: str | None = None,
    action_mark: str | None = None,
    action_state: str = "eligible",
    confirmation_status: str = "pending",
    action_policy: str = "n5_confirmation_only",
    eligibility_reason: str | None = None,
    blocked_reason: str | None = None,
    skipped_reason: str | None = None,
    trace_json: Mapping[str, Any] | None = None,
    action_type: str | None = None,
    lane: str | None = None,
    source_market_data_run_id: str | None = None,
    source_market_trace: Mapping[str, Any] | None = None,
    payload: Mapping[str, Any] | None = None,
    event_schema_version: str = DEFAULT_EVENT_SCHEMA_VERSION,
    created_at: datetime | None = None,
) -> EventEnvelope:
    """Build and validate an N5 action-layer event envelope."""

    validate_n5_event_type(event_type)
    action_key = str((payload or {}).get("action_key") or "")
    dedup_key = build_n5_action_dedup_key(
        event_type=event_type,
        asset_kind=asset_kind,
        identity_key=identity_key,
        trade_date=trade_date,
        source_trigger_event_id=source_trigger_event_id,
        direction=direction,
        signal_type=signal_type,
        condition_key=condition_key,
        trigger_period=trigger_period,
        action_state=action_state,
        action_mark=action_mark,
        action_key=action_key or None,
    )
    event_id = build_stable_event_id(
        source_layer=N5_SOURCE_LAYER,
        event_type=event_type,
        source_run_id=action_run_id,
        dedup_key=dedup_key,
        event_schema_version=event_schema_version,
    )
    action_key = action_key or dedup_key
    market_trace = dict(source_market_trace or {})
    if not source_market_data_run_id and not market_trace:
        market_trace = {
            "source": "N4_trigger_payload",
            "availability": "not_provided_in_current_dry_run",
        }
    source_trigger_run_id = str(source_trigger_run_id or (payload or {}).get("source_trigger_run_id") or "")
    original_condition_key = str(original_condition_key or condition_key)
    enriched_payload = {
        **dict(payload or {}),
        "run_id": action_run_id,
        "n4_trigger_event_id": (payload or {}).get("n4_trigger_event_id") or source_trigger_event_id,
        "source_trigger_event_id": source_trigger_event_id,
        "source_trigger_run_id": source_trigger_run_id,
        "source_trigger_state_id": source_trigger_state_id,
        "source_trigger_match_id": source_trigger_match_id,
        "trigger_match_id": source_trigger_match_id,
        "source_condition_run_id": source_condition_run_id,
        "source_market_data_run_id": source_market_data_run_id,
        "source_market_trace": json_safe_value(market_trace),
        "action_key": action_key,
        "dedup_key": dedup_key,
        "identity_key": identity_key,
        "asset_kind": asset_kind,
        "direction": direction,
        "signal_type": signal_type,
        "condition_key": condition_key,
        "original_condition_key": original_condition_key,
        "trigger_period": trigger_period,
        "action_mark": action_mark,
        "action_state": action_state,
        "confirmation_status": confirmation_status,
        "action_policy": action_policy,
        "eligibility_reason": eligibility_reason,
        "blocked_reason": blocked_reason,
        "skipped_reason": skipped_reason,
        "trace_json": json_safe_value(dict(trace_json or {})),
        "data_quality_status": data_quality_status,
        "event_schema_version": event_schema_version,
    }
    if action_type is not None:
        enriched_payload["action_type"] = action_type
    if lane is not None:
        enriched_payload["lane"] = lane
    envelope = EventEnvelope(
        event_id=event_id,
        event_type=event_type,
        event_schema_version=event_schema_version,
        trade_date=trade_date,
        asset_kind=asset_kind,
        identity_key=identity_key,
        event_time=event_time,
        source_layer=N5_SOURCE_LAYER,
        source_run_id=action_run_id,
        dedup_key=dedup_key,
        partition_key=identity_key,
        payload_json=json_safe_value(enriched_payload),
        created_at=created_at or utc_now(),
    )
    validate_event_envelope(envelope)
    return envelope


def json_safe_value(value: Any) -> Any:
    """Convert N5 payload values to JSONB-safe primitives."""

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
