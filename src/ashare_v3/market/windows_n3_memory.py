"""Pure in-memory Windows N3 snapshot and virtual-amount runtime.

This module owns no database connection, SQL, HTTP server, scheduler, or N4
classification.  One cycle fetches three independent quote channels, replaces
their bounded in-memory views atomically, and publishes immutable views for a
future N4 consumer.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from queue import Queue
from threading import Lock, RLock
from types import MappingProxyType
from typing import Generic, TypeVar

from ashare_v3.market.windows_n3_snapshot import (
    BoardSnapshotBatch,
    BoardSnapshotProvider,
    BoardSnapshotRequest,
    IndexSnapshotBatch,
    IndexSnapshotProvider,
    IndexSnapshotRequest,
    RealtimeQuote,
    StockSnapshotBatch,
    StockSnapshotProvider,
    StockSnapshotRequest,
)


VIRTUAL_AMOUNT_PERIODS = ("30m", "D", "W", "M", "Q", "Y")
DEFAULT_STALE_AFTER_SECONDS = 15.0
DEFAULT_MIN_CYCLE_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class RatioAmountBaseline:
    previous_same_elapsed_amount: Decimal | None
    previous_full_amount: Decimal | None


@dataclass(frozen=True, slots=True)
class AverageAmountBaseline:
    completed_amount_sum: Decimal
    completed_unit_count: int

    def __post_init__(self) -> None:
        if self.completed_unit_count < 0:
            raise ValueError("completed_unit_count must not be negative")


@dataclass(frozen=True, slots=True)
class VirtualAmountContext:
    window_30m: RatioAmountBaseline | None = None
    day: RatioAmountBaseline | None = None
    higher_periods: Mapping[str, AverageAmountBaseline] | None = None

    def __post_init__(self) -> None:
        values = dict(self.higher_periods or {})
        invalid = set(values).difference({"W", "M", "Q", "Y"})
        if invalid:
            raise ValueError(f"unsupported higher virtual amount periods: {sorted(invalid)}")
        object.__setattr__(self, "higher_periods", MappingProxyType(values))


@dataclass(frozen=True, slots=True)
class RealtimeMetric:
    asset_kind: str
    identity_key: str
    exchange: str
    code: str
    name: str
    quote: RealtimeQuote | None
    virtual_amounts: Mapping[str, Decimal | None]
    live_status: str
    fresh: bool
    last_success_at: datetime | None
    last_error: str | None = None

    def __post_init__(self) -> None:
        if self.live_status not in {"available", "unavailable", "stale"}:
            raise ValueError(f"unsupported live_status: {self.live_status}")
        values = {period: self.virtual_amounts.get(period) for period in VIRTUAL_AMOUNT_PERIODS}
        object.__setattr__(self, "virtual_amounts", MappingProxyType(values))


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ChannelStateView(Generic[T]):
    for_trade_date: str
    source_condition_run_id: str
    version: int
    generated_at: datetime
    channel_status: str
    states: Mapping[str, T]
    error_summary: str | None = None


class AtomicSnapshotStore(Generic[T]):
    """Copy-on-replace store; readers never observe a partially updated cycle."""

    def __init__(
        self,
        *,
        for_trade_date: str,
        source_condition_run_id: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if len(for_trade_date) != 8 or not for_trade_date.isdigit():
            raise ValueError("for_trade_date must be YYYYMMDD")
        if not source_condition_run_id:
            raise ValueError("source_condition_run_id is required")
        self._clock = clock or _utc_now
        self._lock = RLock()
        self._view = ChannelStateView(
            for_trade_date=for_trade_date,
            source_condition_run_id=source_condition_run_id,
            version=0,
            generated_at=self._clock(),
            channel_status="warming",
            states=MappingProxyType({}),
        )

    def read(self) -> ChannelStateView[T]:
        with self._lock:
            return self._view

    def replace(
        self,
        states: Mapping[str, T],
        *,
        generated_at: datetime,
        channel_status: str,
        error_summary: str | None = None,
    ) -> ChannelStateView[T]:
        if channel_status not in {"warming", "ready", "degraded"}:
            raise ValueError(f"unsupported channel_status: {channel_status}")
        immutable_states = MappingProxyType(dict(states))
        with self._lock:
            self._view = ChannelStateView(
                for_trade_date=self._view.for_trade_date,
                source_condition_run_id=self._view.source_condition_run_id,
                version=self._view.version + 1,
                generated_at=generated_at,
                channel_status=channel_status,
                states=immutable_states,
                error_summary=error_summary,
            )
            return self._view


class ChannelCycleInProgress(RuntimeError):
    """Raised when a second cycle is attempted for the same channel."""


RequestT = TypeVar("RequestT", StockSnapshotRequest, IndexSnapshotRequest, BoardSnapshotRequest)
BatchT = TypeVar("BatchT", StockSnapshotBatch, IndexSnapshotBatch, BoardSnapshotBatch)


class _SnapshotChannel(Generic[RequestT, BatchT]):
    def __init__(
        self,
        *,
        asset_kind: str,
        provider: object,
        for_trade_date: str,
        source_condition_run_id: str,
        stale_after_seconds: float,
        min_cycle_seconds: float,
        clock: Callable[[], datetime] | None,
    ) -> None:
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")
        if min_cycle_seconds < 5:
            raise ValueError("min_cycle_seconds must be at least 5")
        self.asset_kind = asset_kind
        self.provider = provider
        self.stale_after = timedelta(seconds=stale_after_seconds)
        self.min_cycle = timedelta(seconds=min_cycle_seconds)
        self.clock = clock or _utc_now
        self.store: AtomicSnapshotStore[RealtimeMetric] = AtomicSnapshotStore(
            for_trade_date=for_trade_date,
            source_condition_run_id=source_condition_run_id,
            clock=self.clock,
        )
        self.events: Queue[ChannelStateView[RealtimeMetric]] = Queue()
        self._cycle_lock = Lock()
        self._last_cycle_started_at: datetime | None = None

    @property
    def next_due_at(self) -> datetime | None:
        if self._last_cycle_started_at is None:
            return None
        return self._last_cycle_started_at + self.min_cycle

    def _run_cycle(
        self,
        requests: Sequence[RequestT],
        *,
        contexts: Mapping[str, VirtualAmountContext] | None,
        current_30m_elapsed_amounts: Mapping[str, Decimal] | None,
    ) -> ChannelStateView[RealtimeMetric]:
        if not self._cycle_lock.acquire(blocking=False):
            raise ChannelCycleInProgress(f"{self.asset_kind} snapshot cycle already running")
        now = self.clock()
        self._last_cycle_started_at = now
        requested = tuple(requests)
        try:
            try:
                batch = self.provider.fetch_many(requested)
            except Exception as error:
                view = self._replace_after_channel_failure(requested, now, error)
            else:
                view = self._replace_from_batch(
                    requested,
                    batch,
                    now,
                    contexts or {},
                    current_30m_elapsed_amounts or {},
                )
            self.events.put(view)
            return view
        finally:
            self._cycle_lock.release()

    def _replace_from_batch(
        self,
        requests: Sequence[RequestT],
        batch: BatchT,
        now: datetime,
        contexts: Mapping[str, VirtualAmountContext],
        current_30m_elapsed_amounts: Mapping[str, Decimal],
    ) -> ChannelStateView[RealtimeMetric]:
        previous = self.store.read().states
        quotes = {row.identity_key: row for row in batch.rows}
        states: dict[str, RealtimeMetric] = {}
        for request in requests:
            quote = quotes.get(request.identity_key)
            if quote is not None:
                states[request.identity_key] = RealtimeMetric(
                    asset_kind=self.asset_kind,
                    identity_key=request.identity_key,
                    exchange=request.exchange,
                    code=request.code,
                    name=request.name,
                    quote=quote,
                    virtual_amounts=calculate_virtual_amounts(
                        quote,
                        contexts.get(request.identity_key),
                        current_30m_elapsed_amount=current_30m_elapsed_amounts.get(request.identity_key),
                    ),
                    live_status="available",
                    fresh=True,
                    last_success_at=quote.observed_at,
                )
                continue
            states[request.identity_key] = _missing_metric(
                self.asset_kind,
                request,
                previous.get(request.identity_key),
                now,
                self.stale_after,
            )
        error_summary = "; ".join(batch.errors) if batch.errors else None
        status = "degraded" if batch.errors else "ready"
        return self.store.replace(
            states,
            generated_at=now,
            channel_status=status,
            error_summary=error_summary,
        )

    def _replace_after_channel_failure(
        self,
        requests: Sequence[RequestT],
        now: datetime,
        error: Exception,
    ) -> ChannelStateView[RealtimeMetric]:
        previous = self.store.read().states
        error_summary = f"{type(error).__name__}:{error}"
        states = {
            request.identity_key: _missing_metric(
                self.asset_kind,
                request,
                previous.get(request.identity_key),
                now,
                self.stale_after,
                error_summary,
            )
            for request in requests
        }
        return self.store.replace(
            states,
            generated_at=now,
            channel_status="degraded",
            error_summary=error_summary,
        )


class StockSnapshotChannel(_SnapshotChannel[StockSnapshotRequest, StockSnapshotBatch]):
    def __init__(
        self,
        provider: StockSnapshotProvider,
        *,
        for_trade_date: str,
        source_condition_run_id: str,
        stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
        min_cycle_seconds: float = DEFAULT_MIN_CYCLE_SECONDS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(
            asset_kind="stock",
            provider=provider,
            for_trade_date=for_trade_date,
            source_condition_run_id=source_condition_run_id,
            stale_after_seconds=stale_after_seconds,
            min_cycle_seconds=min_cycle_seconds,
            clock=clock,
        )

    def run_cycle(
        self,
        requests: Sequence[StockSnapshotRequest],
        *,
        contexts: Mapping[str, VirtualAmountContext] | None = None,
        current_30m_elapsed_amounts: Mapping[str, Decimal] | None = None,
    ) -> ChannelStateView[RealtimeMetric]:
        return self._run_cycle(
            requests,
            contexts=contexts,
            current_30m_elapsed_amounts=current_30m_elapsed_amounts,
        )


class IndexSnapshotChannel(_SnapshotChannel[IndexSnapshotRequest, IndexSnapshotBatch]):
    def __init__(
        self,
        provider: IndexSnapshotProvider,
        *,
        for_trade_date: str,
        source_condition_run_id: str,
        stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
        min_cycle_seconds: float = DEFAULT_MIN_CYCLE_SECONDS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(
            asset_kind="index",
            provider=provider,
            for_trade_date=for_trade_date,
            source_condition_run_id=source_condition_run_id,
            stale_after_seconds=stale_after_seconds,
            min_cycle_seconds=min_cycle_seconds,
            clock=clock,
        )

    def run_cycle(
        self,
        requests: Sequence[IndexSnapshotRequest],
        *,
        contexts: Mapping[str, VirtualAmountContext] | None = None,
        current_30m_elapsed_amounts: Mapping[str, Decimal] | None = None,
    ) -> ChannelStateView[RealtimeMetric]:
        return self._run_cycle(
            requests,
            contexts=contexts,
            current_30m_elapsed_amounts=current_30m_elapsed_amounts,
        )


class BoardSnapshotChannel(_SnapshotChannel[BoardSnapshotRequest, BoardSnapshotBatch]):
    def __init__(
        self,
        provider: BoardSnapshotProvider,
        *,
        for_trade_date: str,
        source_condition_run_id: str,
        stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
        min_cycle_seconds: float = DEFAULT_MIN_CYCLE_SECONDS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(
            asset_kind="board",
            provider=provider,
            for_trade_date=for_trade_date,
            source_condition_run_id=source_condition_run_id,
            stale_after_seconds=stale_after_seconds,
            min_cycle_seconds=min_cycle_seconds,
            clock=clock,
        )

    def run_cycle(
        self,
        requests: Sequence[BoardSnapshotRequest],
        *,
        contexts: Mapping[str, VirtualAmountContext] | None = None,
        current_30m_elapsed_amounts: Mapping[str, Decimal] | None = None,
    ) -> ChannelStateView[RealtimeMetric]:
        return self._run_cycle(
            requests,
            contexts=contexts,
            current_30m_elapsed_amounts=current_30m_elapsed_amounts,
        )


@dataclass(frozen=True, slots=True)
class N3MemoryCycleResult:
    stock: ChannelStateView[RealtimeMetric]
    index: ChannelStateView[RealtimeMetric]
    board: ChannelStateView[RealtimeMetric]


class WindowsN3MemoryRuntime:
    """Coordinator only; provider calls remain isolated by channel."""

    def __init__(
        self,
        stock_channel: StockSnapshotChannel,
        index_channel: IndexSnapshotChannel,
        board_channel: BoardSnapshotChannel,
    ) -> None:
        self.stock_channel = stock_channel
        self.index_channel = index_channel
        self.board_channel = board_channel

    def run_cycle(
        self,
        *,
        stock_requests: Sequence[StockSnapshotRequest],
        index_requests: Sequence[IndexSnapshotRequest],
        board_requests: Sequence[BoardSnapshotRequest],
        stock_contexts: Mapping[str, VirtualAmountContext] | None = None,
        index_contexts: Mapping[str, VirtualAmountContext] | None = None,
        board_contexts: Mapping[str, VirtualAmountContext] | None = None,
        stock_30m_elapsed: Mapping[str, Decimal] | None = None,
        index_30m_elapsed: Mapping[str, Decimal] | None = None,
        board_30m_elapsed: Mapping[str, Decimal] | None = None,
    ) -> N3MemoryCycleResult:
        with ThreadPoolExecutor(max_workers=3) as pool:
            stock_future = pool.submit(
                self.stock_channel.run_cycle,
                stock_requests,
                contexts=stock_contexts,
                current_30m_elapsed_amounts=stock_30m_elapsed,
            )
            index_future = pool.submit(
                self.index_channel.run_cycle,
                index_requests,
                contexts=index_contexts,
                current_30m_elapsed_amounts=index_30m_elapsed,
            )
            board_future = pool.submit(
                self.board_channel.run_cycle,
                board_requests,
                contexts=board_contexts,
                current_30m_elapsed_amounts=board_30m_elapsed,
            )
            return N3MemoryCycleResult(
                stock=stock_future.result(),
                index=index_future.result(),
                board=board_future.result(),
            )

    def get_stock_metrics(self) -> ChannelStateView[RealtimeMetric]:
        return self.stock_channel.store.read()

    def get_index_metrics(self) -> ChannelStateView[RealtimeMetric]:
        return self.index_channel.store.read()

    def get_board_metrics(self) -> ChannelStateView[RealtimeMetric]:
        return self.board_channel.store.read()


def calculate_virtual_amounts(
    quote: RealtimeQuote,
    context: VirtualAmountContext | None,
    *,
    current_30m_elapsed_amount: Decimal | None,
) -> Mapping[str, Decimal | None]:
    values: dict[str, Decimal | None] = {period: None for period in VIRTUAL_AMOUNT_PERIODS}
    if context is None:
        return MappingProxyType(values)
    values["30m"] = _ratio_projection(current_30m_elapsed_amount, context.window_30m)
    values["D"] = _ratio_projection(quote.amount, context.day)
    for period in ("W", "M", "Q", "Y"):
        basis = context.higher_periods.get(period) if context.higher_periods else None
        values[period] = _average_with_projected_day(values["D"], basis)
    return MappingProxyType(values)


def _ratio_projection(
    current_elapsed_amount: Decimal | None,
    basis: RatioAmountBaseline | None,
) -> Decimal | None:
    if current_elapsed_amount is None or basis is None:
        return None
    previous_elapsed = basis.previous_same_elapsed_amount
    previous_full = basis.previous_full_amount
    if previous_elapsed is None or previous_full is None or previous_elapsed <= 0:
        return None
    return current_elapsed_amount / previous_elapsed * previous_full


def _average_with_projected_day(
    projected_day_amount: Decimal | None,
    basis: AverageAmountBaseline | None,
) -> Decimal | None:
    if projected_day_amount is None or basis is None:
        return None
    return (basis.completed_amount_sum + projected_day_amount) / Decimal(basis.completed_unit_count + 1)


def _missing_metric(
    asset_kind: str,
    request: RequestT,
    previous: RealtimeMetric | None,
    now: datetime,
    stale_after: timedelta,
    error_summary: str | None = None,
) -> RealtimeMetric:
    if previous is None or previous.last_success_at is None:
        return RealtimeMetric(
            asset_kind=asset_kind,
            identity_key=request.identity_key,
            exchange=request.exchange,
            code=request.code,
            name=request.name,
            quote=None,
            virtual_amounts={},
            live_status="unavailable",
            fresh=False,
            last_success_at=None,
            last_error=error_summary,
        )
    age = now - previous.last_success_at
    return replace(
        previous,
        live_status="stale" if age >= stale_after else "available",
        fresh=False,
        last_error=error_summary,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
