"""Pure same-process orchestration for Windows N3, N4, and N5 memory state.

The orchestrator consumes one immutable N3 cycle through the existing N4
memory runtime, plans N4 lifecycle events, delivers them directly to the N5
episode planners, and requests closed-minute confirmation metrics only for
currently eligible identities. It owns no database, outbox, scheduler, or
market client construction.
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

from ashare_v3.action.windows_n5_episode import (
    EpisodeKey,
    N5EpisodeSnapshot,
    WindowsN5EpisodePlanner,
)
from ashare_v3.events.models import EventEnvelope
from ashare_v3.market.windows_n3_action_metric import (
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


SHANGHAI_TIMEZONE = ZoneInfo("Asia/Shanghai")
ASSET_KINDS = ("stock", "index", "board")


class N4CycleRuntime(Protocol):
    def consume_cycle(self, cycle: object) -> N4MemoryCycleResult: ...


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
        trigger_batch = self.n4.consume(snapshot)
        action_events: list[EventEnvelope] = []
        for event in trigger_batch.events:
            self.trigger_event_counts[event.event_type] += 1
            planned = self.n5.consume_trigger_event(event)
            action_events.extend(planned.events)

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
                    planned = self.n5.consume_metric(metric)
                    action_events.extend(planned.events)
                    if metric.metric_ready:
                        ready_count += 1
                        for key in needed_by_identity[request.identity_key]:
                            self.metric_watermarks[key] = completed_minute_index
                    else:
                        pending_count += 1

        if completed_minute_index >= MINUTES_PER_DAY:
            expired = self.n5.expire(snapshot.generated_at)
            action_events.extend(expired.events)

        for event in action_events:
            self.action_event_counts[event.event_type] += 1
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
