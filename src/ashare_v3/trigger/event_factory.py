"""N4 trigger event factory.

The factory is pure: it does not read N3 facts, write trigger facts, enqueue
events, start workers, or decide downstream actions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from ashare_v3.events.ids import build_n4_trigger_dedup_key, build_n4_trigger_state_changed_dedup_key, build_stable_event_id
from ashare_v3.events.models import (
    DEFAULT_EVENT_SCHEMA_VERSION,
    EventEnvelope,
    N4_SOURCE_LAYER,
    utc_now,
    validate_event_envelope,
    validate_n4_event_type,
)


def build_n4_trigger_event(
    *,
    event_type: str,
    asset_kind: str,
    identity_key: str,
    trade_date: str,
    event_time: datetime,
    trigger_run_id: str,
    source_event_id: str,
    direction: str,
    signal_type: str,
    condition_key: str,
    trigger_mark_candidate: str,
    trigger_period: str,
    trigger_bucket: str,
    match_basis: str,
    data_quality_status: str,
    payload: Mapping[str, Any] | None = None,
    event_schema_version: str = DEFAULT_EVENT_SCHEMA_VERSION,
    created_at: datetime | None = None,
) -> EventEnvelope:
    """Build and validate an N4 trigger event envelope."""

    validate_n4_event_type(event_type)
    payload_map = dict(payload or {})
    if event_type == "TriggerStateChanged":
        dedup_key = build_n4_trigger_state_changed_dedup_key(
            asset_kind=asset_kind,
            identity_key=identity_key,
            trade_date=trade_date,
            direction=direction,
            signal_type=signal_type,
            condition_key=condition_key,
            trigger_bucket=trigger_bucket,
            trigger_mark_candidate=trigger_mark_candidate,
            previous_status=payload_map.get("previous_status"),
            current_status=str(payload_map.get("current_status")),
            previous_trigger_live=bool(payload_map.get("previous_trigger_live")),
            trigger_live=bool(payload_map.get("trigger_live")),
            previous_primary_trigger_period=payload_map.get("previous_primary_trigger_period"),
            primary_trigger_period=payload_map.get("primary_trigger_period"),
            previous_all_trigger_periods=payload_map.get("previous_all_trigger_periods"),
            all_trigger_periods=payload_map.get("all_trigger_periods"),
            state_change_reason=str(payload_map.get("state_change_reason")),
            source_outcome_event_id=payload_map.get("source_outcome_event_id"),
        )
    else:
        dedup_key = build_n4_trigger_dedup_key(
            event_type=event_type,
            asset_kind=asset_kind,
            identity_key=identity_key,
            trade_date=trade_date,
            direction=direction,
            signal_type=signal_type,
            condition_key=condition_key,
            trigger_bucket=trigger_bucket,
        )
    event_id = build_stable_event_id(
        source_layer=N4_SOURCE_LAYER,
        event_type=event_type,
        source_run_id=trigger_run_id,
        dedup_key=dedup_key,
        event_schema_version=event_schema_version,
    )
    enriched_payload = {
        **payload_map,
        "run_id": trigger_run_id,
        "source_event_id": source_event_id,
        "identity_key": identity_key,
        "asset_kind": asset_kind,
        "direction": direction,
        "signal_type": signal_type,
        "condition_key": condition_key,
        "trigger_mark_candidate": trigger_mark_candidate,
        "trigger_period": trigger_period,
        "trigger_bucket": trigger_bucket,
        "match_basis": match_basis,
        "data_quality_status": data_quality_status,
    }
    envelope = EventEnvelope(
        event_id=event_id,
        event_type=event_type,
        event_schema_version=event_schema_version,
        trade_date=trade_date,
        asset_kind=asset_kind,
        identity_key=identity_key,
        event_time=event_time,
        source_layer=N4_SOURCE_LAYER,
        source_run_id=trigger_run_id,
        dedup_key=dedup_key,
        partition_key=identity_key,
        payload_json=enriched_payload,
        created_at=created_at or utc_now(),
    )
    validate_event_envelope(envelope)
    return envelope
