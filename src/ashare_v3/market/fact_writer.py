"""N3 fact writer transaction contracts.

The functions in this module are draft service contracts for N3-B/C style
execute paths. They do not fetch market data and they do not start workers.
They only define the required order inside one caller-owned database
transaction: write the N3 fact, then write the matching common_event_outbox row.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ashare_v3.events.repository import EventRepository
from ashare_v3.market.event_factory import build_n3_market_event
from ashare_v3.market.repositories import MinuteBarRepository, QualityRepository, SnapshotRepository

SOURCE_TIME_TRACE_FIELDS = (
    "source_time_status",
    "raw_snapshot_time_label",
    "raw_snapshot_time_semantics",
    "source_time_trust_level",
    "observed_at",
    "fetched_at",
    "source_time_label_normalized",
    "snapshot_time_policy",
)


def write_market_snapshot_with_event(conn: Any, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Write realtime snapshot fact and MarketSnapshotUpdated outbox atomically."""

    with conn.transaction():
        with conn.cursor() as cursor:
            snapshot_id = SnapshotRepository(cursor).upsert_snapshot(snapshot)
            payload = build_trace_payload(snapshot, snapshot_id=snapshot_id)
            event = build_n3_market_event(
                event_type="MarketSnapshotUpdated",
                asset_kind=str(snapshot["asset_kind"]),
                identity_key=str(snapshot["identity_key"]),
                trade_date=str(snapshot["trade_date"]),
                snapshot_time=format_event_time(snapshot["snapshot_time"]),
                event_time=coerce_datetime(snapshot["snapshot_time"], "snapshot_time"),
                source_run_id=str(snapshot["run_id"]),
                source_adapter=str(snapshot["source_adapter"]),
                payload=payload,
            )
            outbox_event_id = EventRepository(cursor).insert_outbox(event)
            return {
                "snapshot_id": snapshot_id,
                "event_id": event.event_id,
                "outbox_event_id": outbox_event_id,
                "event": event,
            }


def write_minute_bar_closed_with_event(conn: Any, minute_bar: Mapping[str, Any]) -> dict[str, Any]:
    """Write closed 1 minute bar fact and MinuteBarClosed outbox atomically."""

    with conn.transaction():
        with conn.cursor() as cursor:
            minute_bar_id = MinuteBarRepository(cursor).upsert_minute_bar(minute_bar)
            payload = build_trace_payload(minute_bar, minute_bar_id=minute_bar_id)
            event = build_n3_market_event(
                event_type="MinuteBarClosed",
                asset_kind=str(minute_bar["asset_kind"]),
                identity_key=str(minute_bar["identity_key"]),
                trade_date=str(minute_bar["trade_date"]),
                minute_bar_time=format_event_time(minute_bar["bar_time"]),
                event_time=coerce_datetime(minute_bar["bar_time"], "bar_time"),
                source_run_id=str(minute_bar["run_id"]),
                source_adapter=str(minute_bar["source_adapter"]),
                payload=payload,
            )
            outbox_event_id = EventRepository(cursor).insert_outbox(event)
            return {
                "minute_bar_id": minute_bar_id,
                "event_id": event.event_id,
                "outbox_event_id": outbox_event_id,
                "event": event,
            }


def write_market_quality_with_event(
    conn: Any,
    quality_item: Mapping[str, Any],
    *,
    event_type: str,
) -> dict[str, Any]:
    """Write market quality/status fact and MarketDataDelayed/Missing event atomically."""

    if event_type not in {"MarketDataDelayed", "MarketDataMissing"}:
        raise ValueError("quality event_type must be MarketDataDelayed or MarketDataMissing")

    with conn.transaction():
        with conn.cursor() as cursor:
            quality_item_id = QualityRepository(cursor).insert_quality_item(quality_item)
            payload = build_trace_payload(quality_item, quality_item_id=quality_item_id)
            event_time_value = quality_item.get("event_time") or quality_item.get("created_at")
            event = build_n3_market_event(
                event_type=event_type,
                asset_kind=str(quality_item.get("asset_kind") or quality_item["data_domain"]),
                identity_key=str(quality_item.get("identity_key") or "common:N3:market_data_quality"),
                trade_date=str(quality_item["for_trade_date"]),
                required_data_kind=str(quality_item["required_data_kind"]),
                status_kind=str(quality_item.get("status_kind") or quality_item["gate_code"]),
                event_time=coerce_datetime(event_time_value, "event_time"),
                source_run_id=str(quality_item["run_id"]),
                source_adapter=str(quality_item["source_adapter"]),
                payload=payload,
            )
            outbox_event_id = EventRepository(cursor).insert_outbox(event)
            return {
                "quality_item_id": quality_item_id,
                "event_id": event.event_id,
                "outbox_event_id": outbox_event_id,
                "event": event,
            }


def build_trace_payload(
    record: Mapping[str, Any],
    *,
    snapshot_id: int | None = None,
    minute_bar_id: int | None = None,
    quality_item_id: int | None = None,
) -> dict[str, Any]:
    payload = {
        "subscription_id": record.get("subscription_id"),
        "pull_plan_id": record.get("pull_plan_id"),
        "run_id": record.get("run_id"),
        "source_adapter": record.get("source_adapter"),
        "data_quality_status": record.get("data_quality_status") or record.get("quality_status"),
    }
    if snapshot_id is not None:
        payload["snapshot_id"] = snapshot_id
    if minute_bar_id is not None:
        payload["minute_bar_id"] = minute_bar_id
    if quality_item_id is not None:
        payload["quality_item_id"] = quality_item_id
    source_trace = unwrap_jsonb_mapping(record.get("raw_json"))
    for field in SOURCE_TIME_TRACE_FIELDS:
        value = record.get(field)
        if value is None:
            value = source_trace.get(field)
        if value is not None:
            payload[field] = value
    if payload.get("source_time_label_normalized"):
        payload["normalized_event_time_reason"] = (
            source_trace.get("source_time_status_reason")
            or "raw snapshot time label normalized to observed_at by explicit reviewed policy"
        )
    return payload


def unwrap_jsonb_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    obj = getattr(value, "obj", None)
    if isinstance(obj, Mapping):
        return obj
    return {}


def coerce_datetime(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return value
    raise TypeError(f"{field_name} must be a datetime for N3 event_time")


def format_event_time(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
