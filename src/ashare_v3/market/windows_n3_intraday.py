"""Trading-day lifecycle for the Windows N3 in-memory runtime.

The runner reads one active N2 run, preloads previous-day minute context, then
publishes immutable N3 cycles through an injected callback.  It owns no N4
logic, database writes, event generation, service registration, or scheduler.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, time
from types import MappingProxyType
from typing import Any
from zoneinfo import ZoneInfo

from ashare_v3.market.windows_n3_memory import (
    N3MemoryCycleResult,
    RealtimeMetric,
    WindowsN3MemoryRuntime,
)
from ashare_v3.market.windows_n3_minute_context import (
    BoardMinuteContextProvider,
    IndexMinuteContextProvider,
    MinuteContextBatch,
    PreviousDayMinuteContext,
    StockMinuteContextProvider,
    ThirtyMinuteRuntimeReference,
    build_cycle_inputs,
    trading_bucket_position,
)
from ashare_v3.market.windows_n3_previous_day_context import (
    PreviousDayContextLoader,
)
from ashare_v3.market.windows_n3_read_model import (
    N3ActiveReadModel,
    WindowsN3ReadOnlyRepository,
)


SHANGHAI_TIMEZONE = ZoneInfo("Asia/Shanghai")
DEFAULT_CYCLE_SECONDS = 5.0


@dataclass(slots=True)
class PreparedN3Session:
    model: N3ActiveReadModel
    runtime: WindowsN3MemoryRuntime
    previous_stock: Mapping[str, PreviousDayMinuteContext]
    previous_index: Mapping[str, PreviousDayMinuteContext]
    previous_board: Mapping[str, PreviousDayMinuteContext]
    current_stock: Mapping[str, PreviousDayMinuteContext] = field(default_factory=dict)
    current_index: Mapping[str, PreviousDayMinuteContext] = field(default_factory=dict)
    current_board: Mapping[str, PreviousDayMinuteContext] = field(default_factory=dict)
    current_completed_windows: int = 0
    preload_errors: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    stock_price_tracker: "_EntityPriceTracker" = field(default_factory=lambda: _EntityPriceTracker())
    index_price_tracker: "_EntityPriceTracker" = field(default_factory=lambda: _EntityPriceTracker())
    board_price_tracker: "_EntityPriceTracker" = field(default_factory=lambda: _EntityPriceTracker())


@dataclass(frozen=True, slots=True)
class N3IntradayCycle:
    generated_at: datetime
    metrics: N3MemoryCycleResult
    stock_30m_references: Mapping[str, ThirtyMinuteRuntimeReference]
    index_30m_references: Mapping[str, ThirtyMinuteRuntimeReference]
    board_30m_references: Mapping[str, ThirtyMinuteRuntimeReference]

    def __post_init__(self) -> None:
        object.__setattr__(self, "stock_30m_references", MappingProxyType(dict(self.stock_30m_references)))
        object.__setattr__(self, "index_30m_references", MappingProxyType(dict(self.index_30m_references)))
        object.__setattr__(self, "board_30m_references", MappingProxyType(dict(self.board_30m_references)))


@dataclass(frozen=True, slots=True)
class N3IntradayRunSummary:
    result: str
    for_trade_date: str
    source_condition_run_id: str | None
    cycles: int
    started_at: datetime
    finished_at: datetime


class WindowsN3IntradayRunner:
    def __init__(
        self,
        *,
        repository: WindowsN3ReadOnlyRepository,
        context_loader: PreviousDayContextLoader,
        current_stock_minute_provider: StockMinuteContextProvider | None = None,
        current_index_minute_provider: IndexMinuteContextProvider | None = None,
        current_board_minute_provider: BoardMinuteContextProvider | None = None,
        runtime_factory: Callable[[N3ActiveReadModel], WindowsN3MemoryRuntime],
        publish: Callable[[N3IntradayCycle], None] | None = None,
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] | None = None,
        cycle_seconds: float = DEFAULT_CYCLE_SECONDS,
    ) -> None:
        if cycle_seconds < 5:
            raise ValueError("cycle_seconds must be at least 5")
        self.repository = repository
        self.context_loader = context_loader
        self.current_stock_minute_provider = current_stock_minute_provider
        self.current_index_minute_provider = current_index_minute_provider
        self.current_board_minute_provider = current_board_minute_provider
        self.runtime_factory = runtime_factory
        self.publish = publish or (lambda _cycle: None)
        self.clock = clock or _shanghai_now
        if sleep is None:
            from time import sleep as system_sleep
            self.sleep = system_sleep
        else:
            self.sleep = sleep
        self.cycle_seconds = cycle_seconds

    def prepare(self, for_trade_date: str) -> PreparedN3Session | None:
        if not self.repository.is_open_trade_date(for_trade_date):
            return None
        model = self.repository.load_active(for_trade_date)
        loaded = self.context_loader.load(model)
        session = PreparedN3Session(
            model=model,
            runtime=self.runtime_factory(model),
            previous_stock=loaded.stock,
            previous_index=loaded.index,
            previous_board=loaded.board,
            preload_errors={},
        )
        now = _as_shanghai(self.clock())
        if now.strftime("%Y%m%d") == for_trade_date and now.time() >= time(9, 31):
            self._rebuild_current_day_once(session)
        return session

    def _rebuild_current_day_once(self, session: PreparedN3Session) -> None:
        providers = (
            self.current_stock_minute_provider,
            self.current_index_minute_provider,
            self.current_board_minute_provider,
        )
        if any(provider is None for provider in providers):
            return
        model = session.model
        # TQ terminal RPC is single-channel. Keep the three asset contracts
        # independent, but execute the one-time late-start rebuild serially.
        stock_batch = _safe_current_batch(
            self.current_stock_minute_provider,
            model.stock_requests(),
            model.for_trade_date,
            "stock",
        )
        index_batch = _safe_current_batch(
            self.current_index_minute_provider,
            model.index_requests(),
            model.for_trade_date,
            "index",
        )
        board_batch = _safe_current_batch(
            self.current_board_minute_provider,
            model.board_requests(),
            model.for_trade_date,
            "board",
        )
        session.current_stock = stock_batch.contexts
        session.current_index = index_batch.contexts
        session.current_board = board_batch.contexts
        session.current_completed_windows = completed_window_count(_as_shanghai(self.clock()).time())
        session.stock_price_tracker.seed(session.current_stock)
        session.index_price_tracker.seed(session.current_index)
        session.board_price_tracker.seed(session.current_board)

    def run_one_cycle(
        self,
        session: PreparedN3Session,
        observed_at: datetime | None = None,
    ) -> N3IntradayCycle:
        now = _as_shanghai(observed_at or self.clock())
        model = session.model
        stock_contexts, stock_elapsed, stock_references = build_cycle_inputs(
            session.previous_stock,
            session.current_stock,
            model.higher_amount_baselines("stock"),
            now,
        )
        index_contexts, index_elapsed, index_references = build_cycle_inputs(
            session.previous_index,
            session.current_index,
            model.higher_amount_baselines("index"),
            now,
        )
        board_contexts, board_elapsed, board_references = build_cycle_inputs(
            session.previous_board,
            session.current_board,
            model.higher_amount_baselines("board"),
            now,
        )
        metrics = session.runtime.run_cycle(
            stock_requests=model.stock_requests(),
            index_requests=model.index_requests(),
            board_requests=model.board_requests(),
            stock_contexts=stock_contexts,
            index_contexts=index_contexts,
            board_contexts=board_contexts,
            stock_30m_elapsed=stock_elapsed,
            index_30m_elapsed=index_elapsed,
            board_30m_elapsed=board_elapsed,
        )
        stock_references = _update_runtime_references(
            session.previous_stock,
            stock_references,
            metrics.stock.states,
            session.stock_price_tracker,
            now,
        )
        index_references = _update_runtime_references(
            session.previous_index,
            index_references,
            metrics.index.states,
            session.index_price_tracker,
            now,
        )
        board_references = _update_runtime_references(
            session.previous_board,
            board_references,
            metrics.board.states,
            session.board_price_tracker,
            now,
        )
        cycle = N3IntradayCycle(
            generated_at=now,
            metrics=metrics,
            stock_30m_references=stock_references,
            index_30m_references=index_references,
            board_30m_references=board_references,
        )
        self.publish(cycle)
        return cycle

    def execute(self, for_trade_date: str) -> N3IntradayRunSummary:
        started_at = _as_shanghai(self.clock())
        if (
            started_at.strftime("%Y%m%d") != for_trade_date
            or started_at.time() > time(15, 0)
        ):
            return N3IntradayRunSummary(
                result="OUTSIDE_SESSION_SKIPPED",
                for_trade_date=for_trade_date,
                source_condition_run_id=None,
                cycles=0,
                started_at=started_at,
                finished_at=_as_shanghai(self.clock()),
            )
        session = self.prepare(for_trade_date)
        if session is None:
            return N3IntradayRunSummary(
                result="NON_TRADING_DAY_SKIPPED",
                for_trade_date=for_trade_date,
                source_condition_run_id=None,
                cycles=0,
                started_at=started_at,
                finished_at=_as_shanghai(self.clock()),
            )
        cycles = 0
        while True:
            now = _as_shanghai(self.clock())
            if now.strftime("%Y%m%d") != for_trade_date or now.time() > time(15, 0):
                break
            if is_live_session(now.time()):
                self.run_one_cycle(session, now)
                cycles += 1
            self.sleep(self.cycle_seconds)
        return N3IntradayRunSummary(
            result="N3_MEMORY_SESSION_COMPLETE",
            for_trade_date=for_trade_date,
            source_condition_run_id=session.model.run_id,
            cycles=cycles,
            started_at=started_at,
            finished_at=_as_shanghai(self.clock()),
        )


def is_live_session(wall_time: time) -> bool:
    return (
        time(9, 30) <= wall_time <= time(11, 30)
        or time(13, 0) <= wall_time <= time(15, 0)
    )


def completed_window_count(wall_time: time) -> int:
    boundaries = (
        time(10, 0), time(10, 30), time(11, 0), time(11, 30),
        time(13, 30), time(14, 0), time(14, 30), time(15, 0),
    )
    return sum(1 for boundary in boundaries if wall_time >= boundary)


def _safe_current_batch(
    provider: Any,
    requests: Any,
    trade_date: str,
    asset_kind: str,
) -> MinuteContextBatch[Any]:
    try:
        return provider.fetch_many(
            requests,
            trade_date,
            require_complete=False,
        )
    except Exception as error:
        return MinuteContextBatch(
            {},
            (),
            (f"{asset_kind}:{type(error).__name__}:{error}",),
            f"{asset_kind}.unavailable",
        )


@dataclass(frozen=True, slots=True)
class _EntityBucketPrice:
    bucket_index: int
    open: Any
    close: Any


class _EntityPriceTracker:
    """Bounded in-memory 30m entity boundary tracker."""

    def __init__(self) -> None:
        self.current: dict[str, _EntityBucketPrice] = {}
        self.completed: dict[tuple[str, int], tuple[Any, Any]] = {}

    def seed(self, contexts: Mapping[str, PreviousDayMinuteContext]) -> None:
        for identity_key, context in contexts.items():
            for window in context.windows:
                self.completed[(identity_key, window.bucket_index)] = (
                    window.entity_high,
                    window.entity_low,
                )
            if context.bars:
                last = context.bars[-1]
                bucket_index = (last.minute_index - 1) // 30
                bucket_bars = tuple(
                    row
                    for row in context.bars
                    if (row.minute_index - 1) // 30 == bucket_index
                )
                if bucket_bars:
                    self.current[identity_key] = _EntityBucketPrice(
                        bucket_index,
                        bucket_bars[0].open,
                        bucket_bars[-1].close,
                    )

    def observe(self, metric: RealtimeMetric, bucket_index: int) -> None:
        quote = metric.quote
        if quote is None or quote.current_price is None or not metric.fresh:
            return
        previous = self.current.get(metric.identity_key)
        if previous is None:
            self.current[metric.identity_key] = _EntityBucketPrice(
                bucket_index,
                quote.current_price,
                quote.current_price,
            )
            return
        if previous.bucket_index == bucket_index:
            self.current[metric.identity_key] = _EntityBucketPrice(
                bucket_index,
                previous.open,
                quote.current_price,
            )
            return
        self.completed[(metric.identity_key, previous.bucket_index)] = (
            max(previous.open, previous.close),
            min(previous.open, previous.close),
        )
        self.current[metric.identity_key] = _EntityBucketPrice(
            bucket_index,
            quote.current_price,
            quote.current_price,
        )

    def adjacent(self, identity_key: str, bucket_index: int) -> tuple[Any, Any] | None:
        return self.completed.get((identity_key, bucket_index - 1))


def _update_runtime_references(
    previous_contexts: Mapping[str, PreviousDayMinuteContext],
    existing: Mapping[str, ThirtyMinuteRuntimeReference],
    states: Mapping[str, RealtimeMetric],
    tracker: _EntityPriceTracker,
    observed_at: datetime,
) -> Mapping[str, ThirtyMinuteRuntimeReference]:
    position = trading_bucket_position(observed_at.time().replace(tzinfo=None))
    if position is None:
        return MappingProxyType(dict(existing))
    bucket_index, _elapsed = position
    for metric in states.values():
        tracker.observe(metric, bucket_index)
    merged = dict(existing)
    if bucket_index == 0:
        return MappingProxyType(merged)
    for identity_key, previous in previous_contexts.items():
        if identity_key in merged:
            continue
        window = next(
            (row for row in previous.windows if row.bucket_index == bucket_index),
            None,
        )
        adjacent = tracker.adjacent(identity_key, bucket_index)
        if window is None or adjacent is None:
            continue
        merged[identity_key] = ThirtyMinuteRuntimeReference(
            bucket_index=bucket_index,
            previous_day_same_window_amount=window.full_amount,
            adjacent_completed_entity_high=adjacent[0],
            adjacent_completed_entity_low=adjacent[1],
        )
    return MappingProxyType(merged)


def _as_shanghai(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=SHANGHAI_TIMEZONE)
    return value.astimezone(SHANGHAI_TIMEZONE)


def _shanghai_now() -> datetime:
    return datetime.now(SHANGHAI_TIMEZONE)
