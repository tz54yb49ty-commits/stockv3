"""Pure same-process orchestration for Windows N3, N4, and N5 memory state.

The orchestrator consumes one immutable N3 cycle through the existing N4
memory runtime, delivers N4 lifecycle events through optional caller-owned N5
transactions, and requests closed-minute confirmation metrics only for
currently eligible identities. It constructs no database connection, outbox,
scheduler, or market client.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from types import MappingProxyType
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from ashare_v3.action.windows_n5_delivery import N4OutboxDelivery
from ashare_v3.action.windows_n5_episode import (
    EpisodeKey,
    N5EpisodeSnapshot,
    WindowsN5EpisodePlanner,
)
from ashare_v3.action.windows_n5_transaction import (
    WindowsN5TransactionCoordinator,
)
from ashare_v3.events.models import EventEnvelope
from ashare_v3.market.windows_n3_action_metric import (
    ActionConfirmationMetric,
    ActionMetricBatch,
    BoardActionMetricProvider,
    IndexActionMetricProvider,
    StockActionMetricProvider,
)
from ashare_v3.market.windows_n3_minute_context import (
    MINUTES_PER_DAY,
    PreviousDayMinuteContext,
    trading_elapsed_minutes,
)
from ashare_v3.market.windows_n3_snapshot import (
    BoardSnapshotRequest,
    IndexSnapshotRequest,
    StockSnapshotRequest,
)
from ashare_v3.trigger.windows_n4_memory import (
    N4MemoryCycleResult,
    RuntimeStateSnapshot,
)
from ashare_v3.trigger.windows_n4_state_transition import (
    TriggerPlanBatch,
    WindowsN4StateTransitionPlanner,
)
from ashare_v3.trigger.windows_n4_transaction import (
    WindowsN4TransactionCoordinator,
)


SHANGHAI_TIMEZONE = ZoneInfo("Asia/Shanghai")
ASSET_KINDS = ("stock", "index", "board")


class N4CycleRuntime(Protocol):
    def consume_cycle(self, cycle: object) -> N4MemoryCycleResult: ...


@dataclass(frozen=True, slots=True)
class N5ChannelTransactionBoundary:
    n4_connection: Any
    n4_coordinator: WindowsN4TransactionCoordinator
    connection: Any
    coordinator: WindowsN5TransactionCoordinator


@dataclass(frozen=True, slots=True)
class ChannelCycleResult:
    trigger_batch: TriggerPlanBatch
    n5_snapshot: N5EpisodeSnapshot
    n5_events: tuple[EventEnvelope, ...]
    requested_identity_keys: tuple[str, ...]
    metric_ready_count: int
    metric_pending_count: int
    provider_errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WindowsN3N4N5CycleResult:
    generated_at: datetime
    completed_minute_index: int
    n4_memory: N4MemoryCycleResult
    stock: ChannelCycleResult
    index: ChannelCycleResult
    board: ChannelCycleResult


@dataclass(frozen=True, slots=True)
class WindowsN3N4N5RuntimeSummary:
    generated_at: datetime | None
    completed_minute_index: int
    n4_trigger_event_counts: Mapping[str, Mapping[str, int]]
    n4_restored_event_counts: Mapping[str, int]
    n4_restored_versions: Mapping[str, int]
    n5_restored_event_counts: Mapping[str, int]
    n5_restored_episode_counts: Mapping[str, int]
    n5_restored_versions: Mapping[str, int]
    n5_action_event_counts: Mapping[str, Mapping[str, int]]
    action_metric_identity_request_counts: Mapping[str, int]
    action_metric_ready_counts: Mapping[str, int]
    provider_error_counts: Mapping[str, int]
    n5_state_counts: Mapping[str, int]
    n5_versions: Mapping[str, int]

    def __post_init__(self) -> None:
        for field_name in (
            "n4_trigger_event_counts",
            "n5_action_event_counts",
        ):
            value = getattr(self, field_name)
            object.__setattr__(
                self,
                field_name,
                MappingProxyType(
                    {
                        kind: MappingProxyType(dict(counts))
                        for kind, counts in value.items()
                    }
                ),
            )
        for field_name in (
            "n4_restored_event_counts",
            "n4_restored_versions",
            "n5_restored_event_counts",
            "n5_restored_episode_counts",
            "n5_restored_versions",
            "action_metric_identity_request_counts",
            "action_metric_ready_counts",
            "provider_error_counts",
            "n5_state_counts",
            "n5_versions",
        ):
            object.__setattr__(
                self,
                field_name,
                MappingProxyType(dict(getattr(self, field_name))),
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "completed_minute_index": self.completed_minute_index,
            "n4_trigger_event_counts": {
                kind: dict(values)
                for kind, values in self.n4_trigger_event_counts.items()
            },
            "n4_restored_event_counts": dict(
                self.n4_restored_event_counts
            ),
            "n4_restored_versions": dict(self.n4_restored_versions),
            "n5_restored_event_counts": dict(
                self.n5_restored_event_counts
            ),
            "n5_restored_episode_counts": dict(
                self.n5_restored_episode_counts
            ),
            "n5_restored_versions": dict(self.n5_restored_versions),
            "n5_action_event_counts": {
                kind: dict(values)
                for kind, values in self.n5_action_event_counts.items()
            },
            "action_metric_identity_request_counts": dict(
                self.action_metric_identity_request_counts
            ),
            "action_metric_ready_counts": dict(
                self.action_metric_ready_counts
            ),
            "provider_error_counts": dict(self.provider_error_counts),
            "n5_state_counts": dict(self.n5_state_counts),
            "n5_versions": dict(self.n5_versions),
        }


class _ChannelRuntime:
    def __init__(
        self,
        *,
        asset_kind: str,
        requests: Sequence[Any],
        previous_contexts: Mapping[str, PreviousDayMinuteContext],
        metric_provider: Any,
        trigger_run_id: str,
        action_run_id: str,
        n4_restore_events: Sequence[EventEnvelope] = (),
        n5_restore_events: Sequence[EventEnvelope] = (),
        transaction_boundary: (
            N5ChannelTransactionBoundary | None
        ) = None,
    ) -> None:
        by_identity: dict[str, Any] = {}
        for request in requests:
            if request.identity_key in by_identity:
                raise ValueError(
                    f"duplicate {asset_kind} request: {request.identity_key}"
                )
            by_identity[request.identity_key] = request
        self.asset_kind = asset_kind
        self.requests = by_identity
        self.previous_contexts = previous_contexts
        self.metric_provider = metric_provider
        self.n4 = WindowsN4StateTransitionPlanner(
            asset_kind=asset_kind,
            trigger_run_id=trigger_run_id,
        )
        self.n4_restored_event_count = len(n4_restore_events)
        self.n4_restored_version = 0
        if n4_restore_events:
            restored = self.n4.restore_from_outbox(n4_restore_events)
            self.n4_restored_version = restored.source_n4_version
        self.n5 = WindowsN5EpisodePlanner(
            asset_kind=asset_kind,
            action_run_id=action_run_id,
        )
        self.n5_restored_event_count = len(n5_restore_events)
        self.n5_restored_episode_count = 0
        self.n5_restored_version = 0
        if n5_restore_events:
            restored = self.n5.restore_from_outbox(n5_restore_events)
            self.n5_restored_episode_count = len(restored.active)
            self.n5_restored_version = restored.version
        self.transaction_boundary = transaction_boundary
        self._pending_n4_deliveries: tuple[N4OutboxDelivery, ...] = ()
        self.metric_watermarks: dict[EpisodeKey, int] = {}
        self.trigger_event_counts: Counter[str] = Counter()
        self.action_event_counts: Counter[str] = Counter()
        self.metric_identity_request_count = 0
        self.metric_ready_count = 0
        self.provider_error_count = 0

    def consume(
        self,
        snapshot: RuntimeStateSnapshot[Any],
        completed_minute_index: int,
    ) -> ChannelCycleResult:
        boundary = self.transaction_boundary
        committed_deliveries: tuple[N4OutboxDelivery, ...] = ()
        if boundary is None:
            trigger_batch = self.n4.consume(snapshot)
        else:
            committed_n4 = boundary.n4_coordinator.deliver(
                boundary.n4_connection,
                planner=self.n4,
                runtime_snapshot=snapshot,
            )
            self.n4 = committed_n4.planner
            trigger_batch = TriggerPlanBatch(
                snapshot=committed_n4.snapshot,
                events=committed_n4.output_events,
            )
            committed_deliveries = tuple(
                N4OutboxDelivery(row.outbox_id, row.event)
                for row in committed_n4.outbox_rows
            )

        action_events: list[EventEnvelope] = []
        for event in trigger_batch.events:
            self.trigger_event_counts[event.event_type] += 1
        if boundary is None:
            action_events.extend(
                self._deliver_trigger_events(trigger_batch.events)
            )
        else:
            action_events.extend(
                self._deliver_committed_n4(committed_deliveries)
            )

        current = self.n5.read()
        self.metric_watermarks = {
            key: value
            for key, value in self.metric_watermarks.items()
            if key in current.active
        }
        pending = {
            key: episode
            for key, episode in current.active.items()
            if episode.trigger_live
            and episode.action_state == "eligible"
            and episode.confirmation_status == "pending"
        }
        needed_keys = tuple(
            key
            for key in pending
            if completed_minute_index > 0
            and self.metric_watermarks.get(key, 0) < completed_minute_index
            and key.identity_key in snapshot.states
            and snapshot.states[key.identity_key].fresh
            and (
                snapshot.states[key.identity_key].live_status
                == "available"
            )
        )
        needed_identities = tuple(
            sorted({key.identity_key for key in needed_keys})
        )
        requests = tuple(
            self.requests[identity_key]
            for identity_key in needed_identities
            if identity_key in self.requests
        )
        unknown = tuple(
            identity_key
            for identity_key in needed_identities
            if identity_key not in self.requests
        )
        provider_errors: list[str] = [
            f"active_identity_missing_from_n2:{identity_key}"
            for identity_key in unknown
        ]
        ready_count = 0
        pending_count = len(requests)
        if requests:
            self.metric_identity_request_count += len(requests)
            try:
                batch: ActionMetricBatch[Any] = self.metric_provider.fetch_many(
                    requests,
                    snapshot.for_trade_date,
                    self.previous_contexts,
                    completed_minute_index,
                )
            except Exception as error:
                provider_errors.append(f"{type(error).__name__}:{error}")
            else:
                provider_errors.extend(batch.errors)
                pending_count = 0
                needed_by_identity: dict[str, tuple[EpisodeKey, ...]] = {
                    identity_key: tuple(
                        key
                        for key in needed_keys
                        if key.identity_key == identity_key
                    )
                    for identity_key in needed_identities
                }
                for request in requests:
                    metric = batch.metrics.get(request.identity_key)
                    if metric is None:
                        pending_count += 1
                        provider_errors.append(
                            f"metric_missing_from_batch:{request.identity_key}"
                        )
                        continue
                    action_events.extend(self._deliver_metric(metric))
                    if metric.metric_ready:
                        ready_count += 1
                        for key in needed_by_identity[request.identity_key]:
                            self.metric_watermarks[key] = completed_minute_index
                    else:
                        pending_count += 1

        if completed_minute_index >= MINUTES_PER_DAY:
            action_events.extend(self._deliver_expiry(snapshot.generated_at))

        self.metric_ready_count += ready_count
        self.provider_error_count += len(provider_errors)
        return ChannelCycleResult(
            trigger_batch=trigger_batch,
            n5_snapshot=self.n5.read(),
            n5_events=tuple(action_events),
            requested_identity_keys=tuple(
                request.identity_key for request in requests
            ),
            metric_ready_count=ready_count,
            metric_pending_count=pending_count,
            provider_errors=tuple(provider_errors),
        )

    def _deliver_trigger_events(
        self,
        events: Sequence[EventEnvelope],
    ) -> tuple[EventEnvelope, ...]:
        if self.transaction_boundary is not None:
            raise RuntimeError(
                "transaction mode requires committed N4 outbox rows"
            )
        output: list[EventEnvelope] = []
        for event in events:
            batch = self.n5.consume_trigger_event(event)
            output.extend(batch.events)
        return self._record_action_events(output)

    def _deliver_committed_n4(
        self,
        deliveries: Sequence[N4OutboxDelivery],
    ) -> tuple[EventEnvelope, ...]:
        boundary = self.transaction_boundary
        if boundary is None:
            raise RuntimeError(
                "N4 committed delivery requires transaction mode"
            )

        pending_by_id = {
            delivery.event.event_id: delivery
            for delivery in self._pending_n4_deliveries
        }
        for delivery in deliveries:
            existing = pending_by_id.get(delivery.event.event_id)
            if existing is not None and existing != delivery:
                raise ValueError(
                    "conflicting committed N4 outbox delivery: "
                    f"{delivery.event.event_id}"
                )
            pending_by_id.setdefault(delivery.event.event_id, delivery)
        self._pending_n4_deliveries = tuple(pending_by_id.values())
        if not self._pending_n4_deliveries:
            return ()

        committed = boundary.coordinator.deliver_n4(
            boundary.connection,
            planner=self.n5,
            deliveries=self._pending_n4_deliveries,
        )
        self.n5 = committed.planner
        self._pending_n4_deliveries = ()
        return self._record_action_events(committed.output_events)

    def _deliver_metric(
        self,
        metric: ActionConfirmationMetric,
    ) -> tuple[EventEnvelope, ...]:
        if self.transaction_boundary is None:
            batch = self.n5.consume_metric(metric)
            return self._record_action_events(batch.events)
        boundary = self.transaction_boundary
        committed = boundary.coordinator.deliver_metric(
            boundary.connection,
            planner=self.n5,
            metric=metric,
        )
        self.n5 = committed.planner
        return self._record_action_events(committed.output_events)

    def _deliver_expiry(
        self,
        observed_at: datetime,
    ) -> tuple[EventEnvelope, ...]:
        if self.transaction_boundary is None:
            batch = self.n5.expire(observed_at)
            return self._record_action_events(batch.events)
        boundary = self.transaction_boundary
        committed = boundary.coordinator.deliver_expiry(
            boundary.connection,
            planner=self.n5,
            observed_at=observed_at,
        )
        self.n5 = committed.planner
        return self._record_action_events(committed.output_events)

    def _record_action_events(
        self,
        events: Sequence[EventEnvelope],
    ) -> tuple[EventEnvelope, ...]:
        result = tuple(events)
        for event in result:
            self.action_event_counts[event.event_type] += 1
        return result


class WindowsN3N4N5MemoryOrchestrator:
    """One-process, three-channel orchestration with bounded in-memory state."""

    def __init__(
        self,
        *,
        n4_runtime: N4CycleRuntime,
        stock_requests: Sequence[StockSnapshotRequest],
        index_requests: Sequence[IndexSnapshotRequest],
        board_requests: Sequence[BoardSnapshotRequest],
        previous_stock: Mapping[str, PreviousDayMinuteContext],
        previous_index: Mapping[str, PreviousDayMinuteContext],
        previous_board: Mapping[str, PreviousDayMinuteContext],
        stock_metric_provider: StockActionMetricProvider,
        index_metric_provider: IndexActionMetricProvider,
        board_metric_provider: BoardActionMetricProvider,
        trigger_run_ids: Mapping[str, str],
        action_run_ids: Mapping[str, str],
        n4_restore_events: (
            Mapping[str, Sequence[EventEnvelope]] | None
        ) = None,
        n5_restore_events: (
            Mapping[str, Sequence[EventEnvelope]] | None
        ) = None,
        n5_transaction_boundaries: (
            Mapping[str, N5ChannelTransactionBoundary] | None
        ) = None,
    ) -> None:
        if set(trigger_run_ids) != set(ASSET_KINDS):
            raise ValueError("trigger_run_ids must contain stock/index/board")
        if set(action_run_ids) != set(ASSET_KINDS):
            raise ValueError("action_run_ids must contain stock/index/board")
        restore_events = (
            {kind: () for kind in ASSET_KINDS}
            if n4_restore_events is None
            else dict(n4_restore_events)
        )
        if set(restore_events) != set(ASSET_KINDS):
            raise ValueError(
                "n4_restore_events must contain stock/index/board"
            )
        n5_events = (
            {kind: () for kind in ASSET_KINDS}
            if n5_restore_events is None
            else dict(n5_restore_events)
        )
        if set(n5_events) != set(ASSET_KINDS):
            raise ValueError(
                "n5_restore_events must contain stock/index/board"
            )
        transaction_boundaries = (
            {kind: None for kind in ASSET_KINDS}
            if n5_transaction_boundaries is None
            else dict(n5_transaction_boundaries)
        )
        if set(transaction_boundaries) != set(ASSET_KINDS):
            raise ValueError(
                "n5_transaction_boundaries must contain stock/index/board"
            )
        if (
            n5_transaction_boundaries is not None
            and any(value is None for value in transaction_boundaries.values())
        ):
            raise ValueError("all N5 transaction boundaries are required")
        n4_connections = [
            boundary.n4_connection
            for boundary in transaction_boundaries.values()
            if boundary is not None
        ]
        if len({id(connection) for connection in n4_connections}) != len(
            n4_connections
        ):
            raise ValueError(
                "N4 transaction connections must be channel-local"
            )
        n5_connections = [
            boundary.connection
            for boundary in transaction_boundaries.values()
            if boundary is not None
        ]
        if len({id(connection) for connection in n5_connections}) != len(
            n5_connections
        ):
            raise ValueError(
                "N5 transaction connections must be channel-local"
            )
        self.n4_runtime = n4_runtime
        self._lock = RLock()
        self._generated_at: datetime | None = None
        self._completed_minute_index = 0
        self._channels = {
            "stock": _ChannelRuntime(
                asset_kind="stock",
                requests=stock_requests,
                previous_contexts=previous_stock,
                metric_provider=stock_metric_provider,
                trigger_run_id=trigger_run_ids["stock"],
                action_run_id=action_run_ids["stock"],
                n4_restore_events=restore_events["stock"],
                n5_restore_events=n5_events["stock"],
                transaction_boundary=transaction_boundaries["stock"],
            ),
            "index": _ChannelRuntime(
                asset_kind="index",
                requests=index_requests,
                previous_contexts=previous_index,
                metric_provider=index_metric_provider,
                trigger_run_id=trigger_run_ids["index"],
                action_run_id=action_run_ids["index"],
                n4_restore_events=restore_events["index"],
                n5_restore_events=n5_events["index"],
                transaction_boundary=transaction_boundaries["index"],
            ),
            "board": _ChannelRuntime(
                asset_kind="board",
                requests=board_requests,
                previous_contexts=previous_board,
                metric_provider=board_metric_provider,
                trigger_run_id=trigger_run_ids["board"],
                action_run_id=action_run_ids["board"],
                n4_restore_events=restore_events["board"],
                n5_restore_events=n5_events["board"],
                transaction_boundary=transaction_boundaries["board"],
            ),
        }

    def consume_cycle(self, cycle: object) -> WindowsN3N4N5CycleResult:
        with self._lock:
            generated_at = cycle.generated_at
            completed_minute_index = trading_elapsed_minutes(
                _shanghai_wall_time(generated_at)
            )
            n4_memory = self.n4_runtime.consume_cycle(cycle)
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {
                    kind: pool.submit(
                        self._channels[kind].consume,
                        getattr(n4_memory, kind),
                        completed_minute_index,
                    )
                    for kind in ASSET_KINDS
                }
                channel_results = {
                    kind: future.result()
                    for kind, future in futures.items()
                }
            self._generated_at = generated_at
            self._completed_minute_index = completed_minute_index
            return WindowsN3N4N5CycleResult(
                generated_at=generated_at,
                completed_minute_index=completed_minute_index,
                n4_memory=n4_memory,
                stock=channel_results["stock"],
                index=channel_results["index"],
                board=channel_results["board"],
            )

    def read_summary(self) -> WindowsN3N4N5RuntimeSummary:
        with self._lock:
            n5_snapshots = {
                kind: channel.n5.read()
                for kind, channel in self._channels.items()
            }
            return WindowsN3N4N5RuntimeSummary(
                generated_at=self._generated_at,
                completed_minute_index=self._completed_minute_index,
                n4_trigger_event_counts={
                    kind: dict(channel.trigger_event_counts)
                    for kind, channel in self._channels.items()
                },
                n4_restored_event_counts={
                    kind: channel.n4_restored_event_count
                    for kind, channel in self._channels.items()
                },
                n4_restored_versions={
                    kind: channel.n4_restored_version
                    for kind, channel in self._channels.items()
                },
                n5_restored_event_counts={
                    kind: channel.n5_restored_event_count
                    for kind, channel in self._channels.items()
                },
                n5_restored_episode_counts={
                    kind: channel.n5_restored_episode_count
                    for kind, channel in self._channels.items()
                },
                n5_restored_versions={
                    kind: channel.n5_restored_version
                    for kind, channel in self._channels.items()
                },
                n5_action_event_counts={
                    kind: dict(channel.action_event_counts)
                    for kind, channel in self._channels.items()
                },
                action_metric_identity_request_counts={
                    kind: channel.metric_identity_request_count
                    for kind, channel in self._channels.items()
                },
                action_metric_ready_counts={
                    kind: channel.metric_ready_count
                    for kind, channel in self._channels.items()
                },
                provider_error_counts={
                    kind: channel.provider_error_count
                    for kind, channel in self._channels.items()
                },
                n5_state_counts={
                    kind: len(snapshot.runtime_states)
                    for kind, snapshot in n5_snapshots.items()
                },
                n5_versions={
                    kind: snapshot.version
                    for kind, snapshot in n5_snapshots.items()
                },
            )


def _shanghai_wall_time(value: datetime):
    if value.tzinfo is not None:
        value = value.astimezone(SHANGHAI_TIMEZONE)
    return value.time().replace(tzinfo=None)
