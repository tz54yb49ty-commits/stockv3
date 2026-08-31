"""Transactional delivery boundary for the Windows N5 episode planner.

This module converts persisted N4 outbox rows into canonical envelopes, plans
them through a candidate in-memory planner, and persists only N5 events plus
consumer idempotency metadata.  It never opens or commits a database
connection; the caller owns the surrounding transaction and adopts the
candidate planner only after that transaction commits.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ashare_v3.action.event_factory import json_safe_value
from ashare_v3.action.windows_n5_episode import (
    N5EpisodeSnapshot,
    WindowsN5EpisodePlanner,
)
from ashare_v3.events.models import (
    EventEnvelope,
    N4_SOURCE_LAYER,
    N5_SOURCE_LAYER,
    validate_event_envelope,
)
from ashare_v3.market.windows_n3_action_metric import (
    ActionConfirmationMetric,
)


JsonAdapter = Callable[[Any], Any]
N4_DELIVERY_EVENT_TYPES = {"TriggerMatched", "TriggerStateChanged"}
N5_DELIVERY_EVENT_TYPES = {
    "ActionEligible",
    "ActionBlocked",
    "ActionExecuted",
    "ActionSkipped",
}
OUTBOX_COLUMNS = (
    "event_id",
    "event_type",
    "event_schema_version",
    "trade_date",
    "asset_kind",
    "identity_key",
    "event_time",
    "source_layer",
    "source_run_id",
    "dedup_key",
    "partition_key",
    "payload_json",
    "created_at",
)


@dataclass(frozen=True, slots=True)
class N4OutboxDelivery:
    outbox_id: int
    event: EventEnvelope

    def __post_init__(self) -> None:
        if self.outbox_id <= 0:
            raise ValueError("outbox_id must be positive")
        validate_event_envelope(self.event)
        if self.event.source_layer != N4_SOURCE_LAYER:
            raise ValueError("N5 delivery accepts only N4 source events")
        if self.event.event_type not in N4_DELIVERY_EVENT_TYPES:
            raise ValueError(
                f"unsupported N4 delivery event_type: {self.event.event_type}"
            )


@dataclass(frozen=True, slots=True)
class WindowsN5DeliveryPlan:
    snapshot: N5EpisodeSnapshot
    candidate_planner: WindowsN5EpisodePlanner
    source_events: tuple[N4OutboxDelivery, ...]
    output_events: tuple[EventEnvelope, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_events", tuple(self.source_events))
        object.__setattr__(self, "output_events", tuple(self.output_events))
        for event in self.output_events:
            validate_event_envelope(event)
            if event.source_layer != N5_SOURCE_LAYER:
                raise ValueError("N5 delivery output must use source_layer=N5_action")
            if event.event_type not in N5_DELIVERY_EVENT_TYPES:
                raise ValueError(
                    f"unsupported N5 delivery event_type: {event.event_type}"
                )
        if self.candidate_planner.read() != self.snapshot:
            raise ValueError(
                "candidate planner does not match delivery snapshot"
            )


@dataclass(frozen=True, slots=True)
class WindowsN5PersistenceResult:
    inbox_insert_count: int
    outbox_insert_count: int
    checkpoint_upsert_count: int
    outbox_rows: tuple[WindowsN5CommittedOutboxRow, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "outbox_rows", tuple(self.outbox_rows))
        if not 0 <= self.outbox_insert_count <= len(self.outbox_rows):
            raise ValueError("invalid N5 outbox insert count")

    @property
    def database_write_count(self) -> int:
        return (
            self.inbox_insert_count
            + self.outbox_insert_count
            + self.checkpoint_upsert_count
        )


@dataclass(frozen=True, slots=True)
class WindowsN5CommittedOutboxRow:
    """One authoritative N5 row resolved from common_event_outbox."""

    outbox_id: int
    event: EventEnvelope
    inserted: bool

    def __post_init__(self) -> None:
        if self.outbox_id <= 0:
            raise ValueError("outbox_id must be positive")
        validate_event_envelope(self.event)
        if self.event.source_layer != N5_SOURCE_LAYER:
            raise ValueError(
                "committed N5 row must use source_layer=N5_action"
            )
        if self.event.event_type not in N5_DELIVERY_EVENT_TYPES:
            raise ValueError(
                "committed N5 row has unsupported event_type: "
                f"{self.event.event_type}"
            )


def n4_outbox_delivery_from_row(row: Mapping[str, Any]) -> N4OutboxDelivery:
    """Convert one psycopg mapping row without reading any additional state."""

    payload = row.get("payload_json")
    if not isinstance(payload, Mapping):
        raise ValueError("N4 outbox payload_json must be a mapping")
    event_time = row.get("event_time")
    created_at = row.get("created_at")
    if not isinstance(event_time, datetime):
        raise ValueError("N4 outbox event_time must be datetime")
    if not isinstance(created_at, datetime):
        raise ValueError("N4 outbox created_at must be datetime")
    envelope = EventEnvelope(
        event_id=str(row.get("event_id") or ""),
        event_type=str(row.get("event_type") or ""),
        event_schema_version=str(row.get("event_schema_version") or ""),
        trade_date=str(row.get("trade_date") or ""),
        asset_kind=str(row.get("asset_kind") or ""),
        identity_key=str(row.get("identity_key") or ""),
        event_time=event_time,
        source_layer=str(row.get("source_layer") or ""),
        source_run_id=str(row.get("source_run_id") or ""),
        dedup_key=str(row.get("dedup_key") or ""),
        partition_key=str(row.get("partition_key") or ""),
        payload_json=dict(payload),
        created_at=created_at,
    )
    return N4OutboxDelivery(
        outbox_id=int(row.get("outbox_id") or 0),
        event=envelope,
    )


def plan_n4_deliveries(
    planner: WindowsN5EpisodePlanner,
    deliveries: Sequence[N4OutboxDelivery],
) -> WindowsN5DeliveryPlan:
    """Plan an ordered candidate snapshot; caller discards it on transaction failure."""

    identifiers = [delivery.outbox_id for delivery in deliveries]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("duplicate source outbox_id in one N5 delivery batch")
    ordered = tuple(
        sorted(
            deliveries,
            key=lambda item: (
                item.event.event_time,
                item.outbox_id,
                item.event.event_id,
            ),
        )
    )
    candidate = planner.fork()
    output: list[EventEnvelope] = []
    for delivery in ordered:
        batch = candidate.consume_trigger_event(delivery.event)
        output.extend(batch.events)
    return WindowsN5DeliveryPlan(
        snapshot=candidate.read(),
        candidate_planner=candidate,
        source_events=ordered,
        output_events=tuple(output),
    )


def plan_metric_delivery(
    planner: WindowsN5EpisodePlanner,
    metric: ActionConfirmationMetric,
) -> WindowsN5DeliveryPlan:
    """Plan one closed-minute update without advancing the live planner."""

    candidate = planner.fork()
    batch = candidate.consume_metric(metric)
    return WindowsN5DeliveryPlan(
        snapshot=batch.snapshot,
        candidate_planner=candidate,
        source_events=(),
        output_events=batch.events,
    )


def plan_expiry_delivery(
    planner: WindowsN5EpisodePlanner,
    observed_at: datetime,
) -> WindowsN5DeliveryPlan:
    """Plan end-of-window expiry without advancing the live planner."""

    candidate = planner.fork()
    batch = candidate.expire(observed_at)
    return WindowsN5DeliveryPlan(
        snapshot=batch.snapshot,
        candidate_planner=candidate,
        source_events=(),
        output_events=batch.events,
    )


def persist_windows_n5_delivery(
    cursor: Any,
    *,
    plan: WindowsN5DeliveryPlan,
    consumer_name: str,
    json_adapter: JsonAdapter | None = None,
) -> WindowsN5PersistenceResult:
    """Persist one atomic delivery plan without committing the transaction."""

    if not consumer_name.strip():
        raise ValueError("consumer_name is required")
    adapt_json = json_adapter or _default_json_adapter()
    inbox_count = sum(
        _insert_inbox_once(
            cursor,
            consumer_name=consumer_name,
            delivery=delivery,
            json_adapter=adapt_json,
        )
        for delivery in plan.source_events
    )
    outbox_rows: list[WindowsN5CommittedOutboxRow] = []
    outbox_count = 0
    for event in plan.output_events:
        outbox_row = _persist_outbox_once(
            cursor,
            event=event,
            json_adapter=adapt_json,
        )
        outbox_rows.append(outbox_row)
        outbox_count += int(outbox_row.inserted)
    checkpoint_count = sum(
        _upsert_checkpoint(
            cursor,
            consumer_name=consumer_name,
            action_run_id=plan.snapshot.action_run_id,
            delivery=delivery,
            snapshot_version=plan.snapshot.version,
            json_adapter=adapt_json,
        )
        for delivery in _latest_delivery_per_partition(plan.source_events)
    )
    return WindowsN5PersistenceResult(
        inbox_insert_count=inbox_count,
        outbox_insert_count=outbox_count,
        checkpoint_upsert_count=checkpoint_count,
        outbox_rows=tuple(outbox_rows),
    )


def _insert_inbox_once(
    cursor: Any,
    *,
    consumer_name: str,
    delivery: N4OutboxDelivery,
    json_adapter: JsonAdapter,
) -> int:
    event = delivery.event
    cursor.execute(
        """
        INSERT INTO common_event_inbox (
          consumer_name, event_id, event_type, event_schema_version,
          source_layer, source_run_id, dedup_key, partition_key,
          payload_json, status, attempt_count, processed_at, raw_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'processed', 1, now(), %s)
        ON CONFLICT (consumer_name, event_id) DO NOTHING
        RETURNING event_id
        """,
        (
            consumer_name,
            event.event_id,
            event.event_type,
            event.event_schema_version,
            event.source_layer,
            event.source_run_id,
            event.dedup_key,
            event.partition_key,
            json_adapter(
                json_safe_value(dict(event.payload_json))
            ),
            json_adapter(
                json_safe_value(
                    {
                        "source_outbox_id": delivery.outbox_id,
                        "source_event": event.as_record(),
                    }
                )
            ),
        ),
    )
    return int(cursor.fetchone() is not None)


def _persist_outbox_once(
    cursor: Any,
    *,
    event: EventEnvelope,
    json_adapter: JsonAdapter,
) -> WindowsN5CommittedOutboxRow:
    validate_event_envelope(event)
    record = event.as_record()
    placeholders = ", ".join(["%s"] * len(OUTBOX_COLUMNS))
    cursor.execute(
        f"""
        INSERT INTO common_event_outbox ({", ".join(OUTBOX_COLUMNS)})
        VALUES ({placeholders})
        ON CONFLICT DO NOTHING
        RETURNING outbox_id, {", ".join(OUTBOX_COLUMNS)}
        """,
        tuple(
            json_adapter(json_safe_value(record[column]))
            if column == "payload_json"
            else record[column]
            for column in OUTBOX_COLUMNS
        ),
    )
    inserted_row = cursor.fetchone()
    if inserted_row is not None:
        return _authoritative_outbox_row(
            inserted_row,
            event=event,
            inserted=True,
        )

    cursor.execute(
        f"""
        SELECT outbox_id, {", ".join(OUTBOX_COLUMNS)}
        FROM common_event_outbox
        WHERE event_id = %s
           OR (
                source_layer = %s
                AND event_type = %s
                AND source_run_id = %s
                AND dedup_key = %s
                AND event_schema_version = %s
           )
        ORDER BY outbox_id
        LIMIT 2
        """,
        (
            event.event_id,
            event.source_layer,
            event.event_type,
            event.source_run_id,
            event.dedup_key,
            event.event_schema_version,
        ),
    )
    resolved_rows = tuple(cursor.fetchall())
    if len(resolved_rows) != 1:
        raise RuntimeError(
            "N5 idempotent conflict did not resolve exactly one "
            "authoritative outbox row"
        )
    return _authoritative_outbox_row(
        resolved_rows[0],
        event=event,
        inserted=False,
    )


def _authoritative_outbox_row(
    row: Any,
    *,
    event: EventEnvelope,
    inserted: bool,
) -> WindowsN5CommittedOutboxRow:
    values = tuple(row)
    if len(values) != len(OUTBOX_COLUMNS) + 1:
        raise RuntimeError("invalid authoritative N5 outbox row shape")
    outbox_id = int(values[0])
    record = dict(zip(OUTBOX_COLUMNS, values[1:]))
    authoritative_event = EventEnvelope(**record)
    validate_event_envelope(authoritative_event)
    planned_payload = json_safe_value(dict(event.payload_json))
    authoritative_payload = json_safe_value(
        dict(authoritative_event.payload_json)
    )
    if (
        authoritative_event.event_id != event.event_id
        or authoritative_event.event_type != event.event_type
        or authoritative_event.event_schema_version != event.event_schema_version
        or authoritative_event.trade_date != event.trade_date
        or authoritative_event.asset_kind != event.asset_kind
        or authoritative_event.identity_key != event.identity_key
        or authoritative_event.event_time != event.event_time
        or authoritative_event.source_layer != event.source_layer
        or authoritative_event.source_run_id != event.source_run_id
        or authoritative_event.dedup_key != event.dedup_key
        or authoritative_event.partition_key != event.partition_key
        or authoritative_payload != planned_payload
        or authoritative_payload.get("episode_entry_event_id")
        != planned_payload.get("episode_entry_event_id")
    ):
        raise RuntimeError(
            "authoritative N5 outbox row does not match planned event"
        )
    return WindowsN5CommittedOutboxRow(
        outbox_id=outbox_id,
        event=authoritative_event,
        inserted=inserted,
    )


def _upsert_checkpoint(
    cursor: Any,
    *,
    consumer_name: str,
    action_run_id: str,
    delivery: N4OutboxDelivery,
    snapshot_version: int,
    json_adapter: JsonAdapter,
) -> int:
    event = delivery.event
    cursor.execute(
        """
        INSERT INTO common_event_consumer_checkpoint (
          consumer_name, partition_key, source_layer, last_event_id,
          last_event_time, last_outbox_id, checkpoint_payload, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (consumer_name, partition_key, source_layer)
        DO UPDATE SET
          last_event_id = EXCLUDED.last_event_id,
          last_event_time = EXCLUDED.last_event_time,
          last_outbox_id = EXCLUDED.last_outbox_id,
          checkpoint_payload = EXCLUDED.checkpoint_payload,
          updated_at = now()
        WHERE common_event_consumer_checkpoint.last_outbox_id IS NULL
           OR EXCLUDED.last_outbox_id > common_event_consumer_checkpoint.last_outbox_id
        RETURNING partition_key
        """,
        (
            consumer_name,
            event.partition_key,
            N4_SOURCE_LAYER,
            event.event_id,
            event.event_time,
            delivery.outbox_id,
            json_adapter(
                json_safe_value(
                    {
                        "action_run_id": action_run_id,
                        "n5_snapshot_version": snapshot_version,
                        "source_rule_policy_version": (
                            event.payload_json.get("rule_policy_version")
                        ),
                    }
                )
            ),
        ),
    )
    return int(cursor.fetchone() is not None)


def _latest_delivery_per_partition(
    deliveries: Sequence[N4OutboxDelivery],
) -> tuple[N4OutboxDelivery, ...]:
    latest: dict[str, N4OutboxDelivery] = {}
    for delivery in deliveries:
        partition_key = delivery.event.partition_key
        current = latest.get(partition_key)
        if current is None or delivery.outbox_id > current.outbox_id:
            latest[partition_key] = delivery
    return tuple(
        latest[key]
        for key in sorted(latest)
    )


def _default_json_adapter() -> JsonAdapter:
    from psycopg.types.json import Jsonb

    return Jsonb
