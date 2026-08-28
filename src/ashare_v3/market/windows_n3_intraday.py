"""Trading-day lifecycle for the Windows N3 in-memory runtime.

The runner reads one active N2 run, preloads previous-day minute context, then
publishes immutable N3 cycles through an injected callback.  It owns no N4
logic, database writes, event generation, service registration, or scheduler.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, time
from types import MappingProxyType
from typing import Any
from zoneinfo import ZoneInfo

from ashare_v3.market.windows_n3_memory import (
    N3MemoryCycleResult,
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
        stock_minute_provider: StockMinuteContextProvider,
        index_minute_provider: IndexMinuteContextProvider,
        board_minute_provider: BoardMinuteContextProvider,
        runtime_factory: Callable[[N3ActiveReadModel], WindowsN3MemoryRuntime],
        publish: Callable[[N3IntradayCycle], None] | None = None,
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] | None = None,
        cycle_seconds: float = DEFAULT_CYCLE_SECONDS,
    ) -> None:
        if cycle_seconds < 5:
            raise ValueError("cycle_seconds must be at least 5")
        self.repository = repository
        self.stock_minute_provider = stock_minute_provider
        self.index_minute_provider = index_minute_provider
        self.board_minute_provider = board_minute_provider
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
        stock_requests = model.stock_requests()
        index_requests = model.index_requests()
        board_requests = model.board_requests()
        with ThreadPoolExecutor(max_workers=3) as pool:
            stock_future = pool.submit(
                self.stock_minute_provider.fetch_many,
                stock_requests,
                model.source_trade_date,
            )
            index_future = pool.submit(
                self.index_minute_provider.fetch_many,
                index_requests,
                model.source_trade_date,
            )
            board_future = pool.submit(
                self.board_minute_provider.fetch_many,
                board_requests,
                model.source_trade_date,
            )
            stock_batch = _safe_batch(stock_future, "stock")
            index_batch = _safe_batch(index_future, "index")
            board_batch = _safe_batch(board_future, "board")
        session = PreparedN3Session(
            model=model,
            runtime=self.runtime_factory(model),
            previous_stock=stock_batch.contexts,
            previous_index=index_batch.contexts,
            previous_board=board_batch.contexts,
            preload_errors={
                "stock": stock_batch.errors,
                "index": index_batch.errors,
                "board": board_batch.errors,
            },
        )
        now = _as_shanghai(self.clock())
        if now.strftime("%Y%m%d") == for_trade_date and now.time() >= time(9, 31):
            self.refresh_current_day(session)
        return session

    def refresh_current_day(self, session: PreparedN3Session) -> None:
        model = session.model
        with ThreadPoolExecutor(max_workers=3) as pool:
            stock_future = pool.submit(
                self.stock_minute_provider.fetch_many,
                model.stock_requests(),
                model.for_trade_date,
                require_complete=False,
            )
            index_future = pool.submit(
                self.index_minute_provider.fetch_many,
                model.index_requests(),
                model.for_trade_date,
                require_complete=False,
            )
            board_future = pool.submit(
                self.board_minute_provider.fetch_many,
                model.board_requests(),
                model.for_trade_date,
                require_complete=False,
            )
            stock_batch = _safe_batch(stock_future, "stock")
            index_batch = _safe_batch(index_future, "index")
            board_batch = _safe_batch(board_future, "board")
        session.current_stock = stock_batch.contexts
        session.current_index = index_batch.contexts
        session.current_board = board_batch.contexts
        session.current_completed_windows = completed_window_count(_as_shanghai(self.clock()).time())

    def run_one_cycle(
        self,
        session: PreparedN3Session,
        observed_at: datetime | None = None,
    ) -> N3IntradayCycle:
        now = _as_shanghai(observed_at or self.clock())
        # The 15:00 close completes the eighth window but there is no following
        # live bucket that needs its adjacent reference.  Avoid a full-market
        # minute refresh at shutdown so the process can exit before 15:05.
        completed = min(completed_window_count(now.time()), 7)
        if completed > session.current_completed_windows:
            self.refresh_current_day(session)
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


def _safe_batch(future: Any, asset_kind: str) -> MinuteContextBatch[Any]:
    try:
        return future.result()
    except Exception as error:
        return MinuteContextBatch(
            {},
            (),
            (f"{asset_kind}:{type(error).__name__}:{error}",),
            f"{asset_kind}.unavailable",
        )


def _as_shanghai(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=SHANGHAI_TIMEZONE)
    return value.astimezone(SHANGHAI_TIMEZONE)


def _shanghai_now() -> datetime:
    return datetime.now(SHANGHAI_TIMEZONE)
