"""Caller-owned transaction boundary for Windows N4 delivery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ashare_v3.events.models import EventEnvelope
from ashare_v3.trigger.windows_n4_delivery import (
    JsonAdapter,
    WindowsN4CommittedOutboxRow,
    WindowsN4PersistenceResult,
    persist_windows_n4_delivery,
    plan_windows_n4_delivery,
)
from ashare_v3.trigger.windows_n4_memory import RuntimeStateSnapshot
from ashare_v3.trigger.windows_n4_state_transition import (
    TriggerStateSnapshot,
    WindowsN4StateTransitionPlanner,
)


@dataclass(frozen=True, slots=True)
class WindowsN4CommittedDelivery:
    """Candidate and authoritative rows exposed only after commit succeeds."""

    planner: WindowsN4StateTransitionPlanner
    snapshot: TriggerStateSnapshot
    output_events: tuple[EventEnvelope, ...]
    outbox_rows: tuple[WindowsN4CommittedOutboxRow, ...]
    persistence: WindowsN4PersistenceResult

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_events", tuple(self.output_events))
        object.__setattr__(self, "outbox_rows", tuple(self.outbox_rows))
        if self.planner.read() != self.snapshot:
            raise ValueError("committed N4 planner does not match snapshot")
        if self.persistence.outbox_rows != self.outbox_rows:
            raise ValueError(
                "committed N4 rows do not match persistence result"
            )
        if tuple(row.event for row in self.outbox_rows) != self.output_events:
            raise ValueError(
                "committed N4 rows do not match output events"
            )


class WindowsN4TransactionCoordinator:
    """Persist one N4 candidate using a caller-provided transaction."""

    def __init__(self, *, json_adapter: JsonAdapter | None = None) -> None:
        self.json_adapter = json_adapter

    def deliver(
        self,
        connection: Any,
        *,
        planner: WindowsN4StateTransitionPlanner,
        runtime_snapshot: RuntimeStateSnapshot[Any],
    ) -> WindowsN4CommittedDelivery:
        plan = plan_windows_n4_delivery(planner, runtime_snapshot)
        with connection.transaction():
            with connection.cursor() as cursor:
                persistence = persist_windows_n4_delivery(
                    cursor,
                    plan=plan,
                    json_adapter=self.json_adapter,
                )
        return WindowsN4CommittedDelivery(
            planner=plan.candidate_planner,
            snapshot=plan.snapshot,
            output_events=plan.output_events,
            outbox_rows=persistence.outbox_rows,
            persistence=persistence,
        )
