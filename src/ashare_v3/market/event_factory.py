"""N3 market data event factory."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from ashare_v3.events.ids import build_n3_dedup_key, build_stable_event_id
from ashare_v3.events.models import (
    DEFAULT_EVENT_SCHEMA_VERSION,
    EventEnvelope,
    N3_SOURCE_LAYER,
    utc_now,
    validate_event_envelope,
    validate_n3_event_type,
)


def build_n3_market_event(
    *,
    event_type: str,
    asset_kind: str,
    identity_key: str,
    trade_date: str,
    event_time: datetime,
    source_run_id: str,
    source_adapter: str,
    payload: Mapping[str, Any],
    event_schema_version: str = DEFAULT_EVENT_SCHEMA_VERSION,
    snapshot_time: str | None = None,
    minute_bar_time: str | None = None,
    required_data_kind: str | None = None,
    status_kind: str | None = None,
    display_time: str | None = None,
    c2_run_id: str | None = None,
    summary_id: str | int | None = None,
    bucket_id: str | None = None,
    created_at: datetime | None = None,
) -> EventEnvelope:
    """Build and validate an N3 event envelope.

    The function is pure: it does not read market data, write facts, or enqueue
    the event. Services must persist the returned envelope in the same
    transaction as the corresponding N3 fact or quality/status row.
    """

    validate_n3_event_type(event_type)
    dedup_key = build_n3_dedup_key(
        event_type=event_type,
        asset_kind=asset_kind,
        identity_key=identity_key,
        trade_date=trade_date,
        source_adapter=source_adapter,
        snapshot_time=snapshot_time,
        minute_bar_time=minute_bar_time,
        required_data_kind=required_data_kind,
        status_kind=status_kind,
        display_time=display_time,
        event_schema_version=event_schema_version,
        c2_run_id=c2_run_id,
        summary_id=summary_id,
        bucket_id=bucket_id,
    )
    event_id = build_stable_event_id(
        source_layer=N3_SOURCE_LAYER,
        event_type=event_type,
        source_run_id=source_run_id,
        dedup_key=dedup_key,
        event_schema_version=event_schema_version,
    )
    enriched_payload = {
        **dict(payload),
        "run_id": payload.get("run_id") or source_run_id,
        "source_adapter": payload.get("source_adapter") or source_adapter,
        "event_schema_version": payload.get("event_schema_version") or event_schema_version,
    }
    envelope = EventEnvelope(
        event_id=event_id,
        event_type=event_type,
        event_schema_version=event_schema_version,
        trade_date=trade_date,
        asset_kind=asset_kind,
        identity_key=identity_key,
        event_time=event_time,
        source_layer=N3_SOURCE_LAYER,
        source_run_id=source_run_id,
        dedup_key=dedup_key,
        partition_key=identity_key,
        payload_json=enriched_payload,
        created_at=created_at or utc_now(),
    )
    validate_event_envelope(envelope)
    return envelope


def market_snapshot_updated_event(
    *,
    asset_kind: str,
    identity_key: str,
    trade_date: str,
    snapshot_time: str,
    event_time: datetime,
    source_run_id: str,
    source_adapter: str,
    payload: Mapping[str, Any],
) -> EventEnvelope:
    return build_n3_market_event(
        event_type="MarketSnapshotUpdated",
        asset_kind=asset_kind,
        identity_key=identity_key,
        trade_date=trade_date,
        snapshot_time=snapshot_time,
        event_time=event_time,
        source_run_id=source_run_id,
        source_adapter=source_adapter,
        payload=payload,
    )


def minute_bar_closed_event(
    *,
    asset_kind: str,
    identity_key: str,
    trade_date: str,
    minute_bar_time: str,
    event_time: datetime,
    source_run_id: str,
    source_adapter: str,
    payload: Mapping[str, Any],
    event_schema_version: str = DEFAULT_EVENT_SCHEMA_VERSION,
    c2_run_id: str | None = None,
    summary_id: str | int | None = None,
    bucket_id: str | None = None,
) -> EventEnvelope:
    return build_n3_market_event(
        event_type="MinuteBarClosed",
        asset_kind=asset_kind,
        identity_key=identity_key,
        trade_date=trade_date,
        minute_bar_time=minute_bar_time,
        event_time=event_time,
        source_run_id=source_run_id,
        source_adapter=source_adapter,
        payload=payload,
        event_schema_version=event_schema_version,
        c2_run_id=c2_run_id,
        summary_id=summary_id,
        bucket_id=bucket_id,
    )
