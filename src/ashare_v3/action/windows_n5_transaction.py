"""Caller-owned transaction coordinator for Windows N5 delivery.

The coordinator accepts an existing connection, plans against an isolated
candidate, persists N5 inbox/outbox/checkpoint rows in one transaction, and
returns that candidate only after the transaction commits successfully.  It
never opens a connection and never mutates the caller's live planner.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ashare_v3.action.windows_n5_delivery import (
    JsonAdapter,
    N4OutboxDelivery,
    WindowsN5CommittedOutboxRow,
    WindowsN5DeliveryPlan,
    WindowsN5PersistenceResult,
    persist_windows_n5_delivery,
    plan_expiry_delivery,
    plan_metric_delivery,
    plan_n4_deliveries,
)
from ashare_v3.action.windows_n5_episode import (
    N5EpisodeSnapshot,
    WindowsN5EpisodePlanner,
)
from ashare_v3.events.models import EventEnvelope
from ashare_v3.market.windows_n3_action_metric import (
    ActionConfirmationMetric,
)


@dataclass(frozen=True, slots=True)
class WindowsN5CommittedDelivery:
    """Planner state and writes made visible by one successful transaction."""

    planner: WindowsN5EpisodePlanner
    snapshot: N5EpisodeSnapshot
    output_events: tuple[EventEnvelope, ...]
    outbox_rows: tuple[WindowsN5CommittedOutboxRow, ...]
    persistence: WindowsN5PersistenceResult

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_events", tuple(self.output_events))
        object.__setattr__(self, "outbox_rows", tuple(self.outbox_rows))
        if self.planner.read() != self.snapshot:
            raise ValueError("committed planner does not match snapshot")
        if self.persistence.outbox_rows != self.outbox_rows:
            raise ValueError(
                "committed N5 rows do not match persistence result"
            )
        if tuple(
            row.event for row in self.outbox_rows if row.inserted
        ) != self.output_events:
            raise ValueError(
                "new committed N5 rows do not match output events"
            )


class WindowsN5TransactionCoordinator:
    """Commit one N5 candidate using a caller-provided database connection."""

    def __init__(
        self,
        *,
        consumer_name: str,
        json_adapter: JsonAdapter | None = None,
    ) -> None:
        if not consumer_name.strip():
            raise ValueError("consumer_name is required")
        self.consumer_name = consumer_name
        self.json_adapter = json_adapter

    def deliver_n4(
        self,
        connection: Any,
        *,
        planner: WindowsN5EpisodePlanner,
        deliveries: Sequence[N4OutboxDelivery],
    ) -> WindowsN5CommittedDelivery:
        """Consume ordered N4 lifecycle events in one N5 transaction."""

        return self._commit(
            connection,
            plan_n4_deliveries(planner, deliveries),
        )

    def deliver_metric(
        self,
        connection: Any,
        *,
        planner: WindowsN5EpisodePlanner,
        metric: ActionConfirmationMetric,
    ) -> WindowsN5CommittedDelivery:
        """Persist one closed-minute N5 outcome transactionally."""

        return self._commit(
            connection,
            plan_metric_delivery(planner, metric),
        )

    def deliver_expiry(
        self,
        connection: Any,
        *,
        planner: WindowsN5EpisodePlanner,
        observed_at: datetime,
    ) -> WindowsN5CommittedDelivery:
        """Persist the end-of-window ActionSkipped outcomes transactionally."""

        return self._commit(
            connection,
            plan_expiry_delivery(planner, observed_at),
        )

    def _commit(
        self,
        connection: Any,
        plan: WindowsN5DeliveryPlan,
    ) -> WindowsN5CommittedDelivery:
        with connection.transaction():
            with connection.cursor() as cursor:
                persistence = persist_windows_n5_delivery(
                    cursor,
                    plan=plan,
                    consumer_name=self.consumer_name,
                    json_adapter=self.json_adapter,
                )
        return WindowsN5CommittedDelivery(
            planner=plan.candidate_planner,
            snapshot=plan.snapshot,
            output_events=tuple(
                row.event
                for row in persistence.outbox_rows
                if row.inserted
            ),
            outbox_rows=persistence.outbox_rows,
            persistence=persistence,
        )
