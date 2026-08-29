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

    @property
    def database_write_count(self) -> int:
        return self.outbox_insert_count


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
    outbox_count = sum(
        _insert_outbox_once(
            cursor,
            event=event,
            json_adapter=adapt_json,
        )
        for event in plan.output_events
    )
    return WindowsN4PersistenceResult(outbox_insert_count=outbox_count)


def _insert_outbox_once(
    cursor: Any,
    *,
    event: EventEnvelope,
    json_adapter: JsonAdapter,
) -> int:
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
        RETURNING event_id
        """,
        tuple(
            json_adapter(record[column])
            if column == "payload_json"
            else record[column]
            for column in OUTBOX_COLUMNS
        ),
    )
    return int(cursor.fetchone() is not None)


def _default_json_adapter() -> JsonAdapter:
    from psycopg.types.json import Jsonb

    return Jsonb
