"""Transactional Outbox boundary for Windows N4 lifecycle events.

Planning always happens on a forked candidate. This module never connects or
commits a database transaction. The caller persists inside its transaction
and replaces the live planner with the candidate only after commit.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ashare_v3.events.models import (
    EventEnvelope,
    N4_SOURCE_LAYER,
    validate_event_envelope,
)
from ashare_v3.trigger.windows_n4_memory import RuntimeStateSnapshot
from ashare_v3.trigger.windows_n4_state_transition import (
    TriggerStateSnapshot,
    WindowsN4StateTransitionPlanner,
)


JsonAdapter = Callable[[Any], Any]
N4_DELIVERY_EVENT_TYPES = {"TriggerMatched", "TriggerStateChanged"}
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
class WindowsN4DeliveryPlan:
    snapshot: TriggerStateSnapshot
    candidate_planner: WindowsN4StateTransitionPlanner
    output_events: tuple[EventEnvelope, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_events", tuple(self.output_events))
        if self.candidate_planner.read() != self.snapshot:
            raise ValueError(
                "candidate planner does not match delivery snapshot"
            )
        for event in self.output_events:
            validate_event_envelope(event)
            if event.source_layer != N4_SOURCE_LAYER:
                raise ValueError(
                    "N4 delivery output must use source_layer=N4_trigger"
                )
            if event.event_type not in N4_DELIVERY_EVENT_TYPES:
                raise ValueError(
                    f"unsupported N4 delivery event_type: {event.event_type}"
                )


@dataclass(frozen=True, slots=True)
class WindowsN4PersistenceResult:
    outbox_insert_count: int
    outbox_rows: tuple[WindowsN4CommittedOutboxRow, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "outbox_rows", tuple(self.outbox_rows))
        if not 0 <= self.outbox_insert_count <= len(self.outbox_rows):
            raise ValueError("invalid N4 outbox insert count")

    @property
    def database_write_count(self) -> int:
        return self.outbox_insert_count


@dataclass(frozen=True, slots=True)
class WindowsN4CommittedOutboxRow:
    """One authoritative N4 row resolved from common_event_outbox."""

    outbox_id: int
    event: EventEnvelope

    def __post_init__(self) -> None:
        if self.outbox_id <= 0:
            raise ValueError("outbox_id must be positive")
        validate_event_envelope(self.event)
        if self.event.source_layer != N4_SOURCE_LAYER:
            raise ValueError(
                "committed N4 row must use source_layer=N4_trigger"
            )
        if self.event.event_type not in N4_DELIVERY_EVENT_TYPES:
            raise ValueError(
                "committed N4 row has unsupported event_type: "
                f"{self.event.event_type}"
            )


def plan_windows_n4_delivery(
    planner: WindowsN4StateTransitionPlanner,
    runtime_snapshot: RuntimeStateSnapshot[Any],
) -> WindowsN4DeliveryPlan:
    """Plan one immutable N4 snapshot without advancing the live planner."""

    candidate = planner.fork()
    batch = candidate.consume(runtime_snapshot)
    return WindowsN4DeliveryPlan(
        snapshot=batch.snapshot,
        candidate_planner=candidate,
        output_events=batch.events,
    )


def persist_windows_n4_delivery(
    cursor: Any,
    *,
    plan: WindowsN4DeliveryPlan,
    json_adapter: JsonAdapter | None = None,
) -> WindowsN4PersistenceResult:
    """Insert N4 events idempotently without committing the transaction."""

    adapt_json = json_adapter or _default_json_adapter()
    outbox_rows: list[WindowsN4CommittedOutboxRow] = []
    outbox_count = 0
    for event in plan.output_events:
        outbox_row, inserted = _persist_outbox_once(
            cursor,
            event=event,
            json_adapter=adapt_json,
        )
        outbox_rows.append(outbox_row)
        outbox_count += int(inserted)
    return WindowsN4PersistenceResult(
        outbox_insert_count=outbox_count,
        outbox_rows=tuple(outbox_rows),
    )


def _persist_outbox_once(
    cursor: Any,
    *,
    event: EventEnvelope,
    json_adapter: JsonAdapter,
) -> tuple[WindowsN4CommittedOutboxRow, bool]:
    validate_event_envelope(event)
    if event.source_layer != N4_SOURCE_LAYER:
        raise ValueError("N4 persistence accepts only N4 source events")
    if event.event_type not in N4_DELIVERY_EVENT_TYPES:
        raise ValueError(
            f"unsupported N4 persistence event_type: {event.event_type}"
        )
    record: Mapping[str, Any] = event.as_record()
    placeholders = ", ".join(["%s"] * len(OUTBOX_COLUMNS))
    cursor.execute(
        f"""
        INSERT INTO common_event_outbox ({", ".join(OUTBOX_COLUMNS)})
        VALUES ({placeholders})
        ON CONFLICT DO NOTHING
        RETURNING outbox_id, {", ".join(OUTBOX_COLUMNS)}
        """,
        tuple(
            json_adapter(record[column])
            if column == "payload_json"
            else record[column]
            for column in OUTBOX_COLUMNS
        ),
    )
    inserted_row = cursor.fetchone()
    if inserted_row is not None:
        return _authoritative_outbox_row(inserted_row, event=event), True

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
            "N4 idempotent conflict did not resolve exactly one "
            "authoritative outbox row"
        )
    return _authoritative_outbox_row(resolved_rows[0], event=event), False


def _authoritative_outbox_row(
    row: Any,
    *,
    event: EventEnvelope,
) -> WindowsN4CommittedOutboxRow:
    values = tuple(row)
    if len(values) != len(OUTBOX_COLUMNS) + 1:
        raise RuntimeError("invalid authoritative N4 outbox row shape")
    outbox_id = int(values[0])
    record = dict(zip(OUTBOX_COLUMNS, values[1:]))
    authoritative_event = EventEnvelope(**record)
    validate_event_envelope(authoritative_event)
    if authoritative_event != event:
        raise RuntimeError(
            "authoritative N4 outbox row does not match planned event"
        )
    return WindowsN4CommittedOutboxRow(
        outbox_id=outbox_id,
        event=authoritative_event,
    )


def _default_json_adapter() -> JsonAdapter:
    from psycopg.types.json import Jsonb

    return Jsonb
