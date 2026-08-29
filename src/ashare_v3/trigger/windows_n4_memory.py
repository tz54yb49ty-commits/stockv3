"""Pure in-memory Windows N4 realtime state consumers.

N2 baselines are injected once at startup.  Each consumer accepts only the
latest immutable N3 channel view, computes realtime 30m/D/W/M/Q/Y transitions,
and atomically replaces a bounded state mapping.  This module owns no database,
SQL, event, scheduler, or downstream action integration.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal
from threading import RLock
from types import MappingProxyType
from typing import Generic, TypeVar

from ashare_v3.market.windows_n3_memory import (
    ChannelStateView,
    RealtimeMetric,
    WindowsN3MemoryRuntime,
)
from ashare_v3.market.windows_n3_minute_context import ThirtyMinuteRuntimeReference
from ashare_v3.market.windows_n3_read_model import N2ObjectRuntimeInput, N3ActiveReadModel


RUNTIME_PERIODS = ("30m", "D", "W", "M", "Q", "Y")
N2_RUNTIME_PERIODS = ("D", "W", "M", "Q", "Y")
VALID_TRANSITIONS = {
    "volume_up",
    "low_volume_up",
    "volume_down",
    "low_volume_down",
    "flat",
    "unknown",
}
TRANSITION_WINDOWS = {"W": 1, "M": 5, "Q": 22, "Y": 66}


@dataclass(frozen=True, slots=True)
class RuntimePeriodBaseline:
    """Normalized N2 input for one realtime classification period."""

    period: str
    source_transition: str
    source_amount: Decimal | None
    comparison_entity_high: Decimal | None
    comparison_entity_low: Decimal | None
    comparison_amount: Decimal | None
    current_trade_days: int = 1
    ready: bool = True

    def __post_init__(self) -> None:
        if self.period not in RUNTIME_PERIODS:
            raise ValueError(f"unsupported runtime period: {self.period}")
        if self.source_transition not in VALID_TRANSITIONS:
            raise ValueError(f"unsupported source transition: {self.source_transition}")
        if self.current_trade_days < 1:
            raise ValueError("current_trade_days must be positive")
        if self.ready:
            required = (
                self.comparison_entity_high,
                self.comparison_entity_low,
                self.comparison_amount,
            )
            if any(value is None for value in required):
                raise ValueError("ready period baseline requires price and amount comparisons")
            assert self.comparison_entity_high is not None
            assert self.comparison_entity_low is not None
            assert self.comparison_amount is not None
            if self.comparison_entity_high < self.comparison_entity_low:
                raise ValueError("comparison_entity_high must not be below comparison_entity_low")
            if self.comparison_amount < 0:
                raise ValueError("comparison_amount must not be negative")


@dataclass(frozen=True, slots=True)
class N2RuntimeBaseline:
    """Small startup contract; deliberately excludes N2 user-facing fields."""

    source_condition_run_id: str
    source_trade_date: str
    for_trade_date: str
    asset_kind: str
    identity_key: str
    exchange: str
    code: str
    name: str
    periods: Mapping[str, RuntimePeriodBaseline]

    def __post_init__(self) -> None:
        if not self.source_condition_run_id:
            raise ValueError("source_condition_run_id is required")
        _require_yyyymmdd(self.source_trade_date, "source_trade_date")
        _require_yyyymmdd(self.for_trade_date, "for_trade_date")
        if self.source_trade_date >= self.for_trade_date:
            raise ValueError("for_trade_date must be after source_trade_date")
        if self.asset_kind not in {"stock", "index", "board"}:
            raise ValueError(f"unsupported asset_kind: {self.asset_kind}")
        if not self.identity_key.startswith(f"{self.asset_kind}:"):
            raise ValueError("identity_key must match asset_kind")
        values = dict(self.periods)
        if set(values) != set(N2_RUNTIME_PERIODS):
            raise ValueError("N2 period baselines must contain exactly D/W/M/Q/Y")
        for period, baseline in values.items():
            if baseline.period != period:
                raise ValueError(f"period key mismatch: {period} != {baseline.period}")
        object.__setattr__(self, "periods", MappingProxyType(values))


@dataclass(frozen=True, slots=True)
class _RuntimeState:
    source_condition_run_id: str
    source_trade_date: str
    for_trade_date: str
    asset_kind: str
    identity_key: str
    exchange: str
    code: str
    name: str
    source_transitions: Mapping[str, str]
    source_amounts: Mapping[str, Decimal | None]
    realtime_transitions: Mapping[str, str | None]
    realtime_virtual_amounts: Mapping[str, Decimal | None]
    current_price: Decimal | None
    cumulative_amount: Decimal | None
    source_time: datetime | None
    observed_at: datetime | None
    provider: str | None
    live_status: str
    fresh: bool
    last_success_at: datetime | None
    last_error: str | None
    source_n3_version: int
    comparison_amounts: Mapping[str, Decimal | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.live_status not in {"available", "unavailable", "stale"}:
            raise ValueError(f"unsupported live_status: {self.live_status}")
        object.__setattr__(
            self,
            "source_transitions",
            MappingProxyType({period: self.source_transitions.get(period, "unknown") for period in RUNTIME_PERIODS}),
        )
        object.__setattr__(
            self,
            "source_amounts",
            MappingProxyType({period: self.source_amounts.get(period) for period in RUNTIME_PERIODS}),
        )
        object.__setattr__(
            self,
            "comparison_amounts",
            MappingProxyType({period: self.comparison_amounts.get(period) for period in RUNTIME_PERIODS}),
        )
        object.__setattr__(
            self,
            "realtime_transitions",
            MappingProxyType({period: self.realtime_transitions.get(period) for period in RUNTIME_PERIODS}),
        )
        object.__setattr__(
            self,
            "realtime_virtual_amounts",
            MappingProxyType({period: self.realtime_virtual_amounts.get(period) for period in RUNTIME_PERIODS}),
        )


@dataclass(frozen=True, slots=True)
class StockRuntimeState(_RuntimeState):
    pass


@dataclass(frozen=True, slots=True)
class IndexRuntimeState(_RuntimeState):
    pass


@dataclass(frozen=True, slots=True)
class BoardRuntimeState(_RuntimeState):
    pass


RuntimeStateT = TypeVar("RuntimeStateT", bound=_RuntimeState)


@dataclass(frozen=True, slots=True)
class RuntimeStateSnapshot(Generic[RuntimeStateT]):
    source_condition_run_id: str
    source_trade_date: str
    for_trade_date: str
    version: int
    source_n3_version: int
    generated_at: datetime
    channel_status: str
    states: Mapping[str, RuntimeStateT]
    error_summary: str | None = None


class OutOfOrderN3Snapshot(ValueError):
    """Raised when a consumer receives an older N3 channel version."""


class _AtomicRuntimeStateStore(Generic[RuntimeStateT]):
    def __init__(
        self,
        baselines: Mapping[str, N2RuntimeBaseline],
        state_type: type[RuntimeStateT],
    ) -> None:
        first = next(iter(baselines.values()))
        initial = {
            identity_key: _initial_state(baseline, state_type)
            for identity_key, baseline in baselines.items()
        }
        self._lock = RLock()
        self._snapshot = RuntimeStateSnapshot(
            source_condition_run_id=first.source_condition_run_id,
            source_trade_date=first.source_trade_date,
            for_trade_date=first.for_trade_date,
            version=0,
            source_n3_version=0,
            generated_at=datetime.now(timezone.utc),
            channel_status="warming",
            states=MappingProxyType(initial),
        )

    def read(self) -> RuntimeStateSnapshot[RuntimeStateT]:
        with self._lock:
            return self._snapshot

    def replace(
        self,
        states: Mapping[str, RuntimeStateT],
        *,
        source_n3_version: int,
        generated_at: datetime,
        channel_status: str,
        error_summary: str | None,
    ) -> RuntimeStateSnapshot[RuntimeStateT]:
        if channel_status not in {"warming", "ready", "degraded"}:
            raise ValueError(f"unsupported channel_status: {channel_status}")
        immutable_states = MappingProxyType(dict(states))
        with self._lock:
            previous = self._snapshot
            self._snapshot = RuntimeStateSnapshot(
                source_condition_run_id=previous.source_condition_run_id,
                source_trade_date=previous.source_trade_date,
                for_trade_date=previous.for_trade_date,
                version=previous.version + 1,
                source_n3_version=source_n3_version,
                generated_at=generated_at,
                channel_status=channel_status,
                states=immutable_states,
                error_summary=error_summary,
            )
            return self._snapshot


class _RuntimeStateConsumer(Generic[RuntimeStateT]):
    def __init__(
        self,
        baselines: Sequence[N2RuntimeBaseline],
        *,
        asset_kind: str,
        state_type: type[RuntimeStateT],
    ) -> None:
        values = tuple(baselines)
        if not values:
            raise ValueError(f"{asset_kind} baselines must not be empty")
        first = values[0]
        by_identity: dict[str, N2RuntimeBaseline] = {}
        for baseline in values:
            if baseline.asset_kind != asset_kind:
                raise ValueError(f"expected {asset_kind} baseline, got {baseline.asset_kind}")
            if (
                baseline.source_condition_run_id != first.source_condition_run_id
                or baseline.source_trade_date != first.source_trade_date
                or baseline.for_trade_date != first.for_trade_date
            ):
                raise ValueError("all channel baselines must share one N2 lineage and date pair")
            if baseline.identity_key in by_identity:
                raise ValueError(f"duplicate baseline identity: {baseline.identity_key}")
            by_identity[baseline.identity_key] = baseline
        self.asset_kind = asset_kind
        self._baselines = MappingProxyType(by_identity)
        self._state_type = state_type
        self._store = _AtomicRuntimeStateStore(self._baselines, state_type)
        self._consume_lock = RLock()

    @property
    def states(self) -> Mapping[str, RuntimeStateT]:
        return self._store.read().states

    def read(self) -> RuntimeStateSnapshot[RuntimeStateT]:
        return self._store.read()

    def consume(
        self,
        view: ChannelStateView[RealtimeMetric],
        *,
        thirty_minute_references: Mapping[str, ThirtyMinuteRuntimeReference] | None = None,
    ) -> RuntimeStateSnapshot[RuntimeStateT]:
        with self._consume_lock:
            return self._consume_locked(view, thirty_minute_references or {})

    def _consume_locked(
        self,
        view: ChannelStateView[RealtimeMetric],
        thirty_minute_references: Mapping[str, ThirtyMinuteRuntimeReference],
    ) -> RuntimeStateSnapshot[RuntimeStateT]:
        current = self._store.read()
        self._validate_view(view)
        if view.version < current.source_n3_version:
            raise OutOfOrderN3Snapshot(
                f"{self.asset_kind} N3 version moved backwards: "
                f"{view.version} < {current.source_n3_version}"
            )
        if view.version == current.source_n3_version:
            return current
        unknown_references = set(thirty_minute_references).difference(self._baselines)
        if unknown_references:
            raise ValueError(
                "30m references contain identities outside N2 universe: "
                f"{sorted(unknown_references)[:3]}"
            )

        next_states: dict[str, RuntimeStateT] = {}
        for identity_key, baseline in self._baselines.items():
            previous = current.states[identity_key]
            metric = view.states.get(identity_key)
            if metric is not None and metric.asset_kind != self.asset_kind:
                raise ValueError(f"N3 metric asset mismatch for {identity_key}")
            if metric is not None and metric.identity_key != identity_key:
                raise ValueError(f"N3 metric identity mismatch for {identity_key}")
            next_states[identity_key] = self._next_state(
                baseline,
                previous,
                metric,
                view.version,
                thirty_minute_references.get(identity_key),
            )
        return self._store.replace(
            next_states,
            source_n3_version=view.version,
            generated_at=view.generated_at,
            channel_status=view.channel_status,
            error_summary=view.error_summary,
        )

    def _validate_view(self, view: ChannelStateView[RealtimeMetric]) -> None:
        first = next(iter(self._baselines.values()))
        if view.for_trade_date != first.for_trade_date:
            raise ValueError("N3 for_trade_date does not match N2 baseline")
        if view.source_condition_run_id != first.source_condition_run_id:
            raise ValueError("N3 source_condition_run_id does not match N2 baseline")
        unknown = set(view.states).difference(self._baselines)
        if unknown:
            raise ValueError(f"N3 view contains identities outside N2 universe: {sorted(unknown)[:3]}")

    def prevalidate(
        self,
        view: ChannelStateView[RealtimeMetric],
        references: Mapping[str, ThirtyMinuteRuntimeReference],
    ) -> None:
        """Fail before a three-channel cycle mutates any channel generation."""

        self._validate_view(view)
        current = self._store.read()
        if view.version < current.source_n3_version:
            raise OutOfOrderN3Snapshot(
                f"{self.asset_kind} N3 version moved backwards: "
                f"{view.version} < {current.source_n3_version}"
            )
        unknown_references = set(references).difference(self._baselines)
        if unknown_references:
            raise ValueError(
                "30m references contain identities outside N2 universe: "
                f"{sorted(unknown_references)[:3]}"
            )
        for identity_key, metric in view.states.items():
            if metric.asset_kind != self.asset_kind or metric.identity_key != identity_key:
                raise ValueError(f"N3 metric identity mismatch for {identity_key}")
            if metric.quote is not None and (
                metric.quote.asset_kind != self.asset_kind
                or metric.quote.identity_key != identity_key
            ):
                raise ValueError(f"N3 quote identity mismatch for {identity_key}")

    def _next_state(
        self,
        baseline: N2RuntimeBaseline,
        previous: RuntimeStateT,
        metric: RealtimeMetric | None,
        source_n3_version: int,
        thirty_minute_reference: ThirtyMinuteRuntimeReference | None,
    ) -> RuntimeStateT:
        if (
            metric is None
            or not metric.fresh
            or metric.live_status != "available"
            or metric.quote is None
        ):
            return replace(
                previous,
                realtime_transitions={period: "unknown" for period in RUNTIME_PERIODS},
                realtime_virtual_amounts={period: None for period in RUNTIME_PERIODS},
                current_price=None,
                cumulative_amount=None,
                source_time=None,
                observed_at=None,
                provider=None,
                live_status=metric.live_status if metric is not None else "unavailable",
                fresh=False,
                last_success_at=metric.last_success_at if metric is not None else previous.last_success_at,
                last_error=metric.last_error if metric is not None else None,
                source_n3_version=source_n3_version,
            )

        quote = metric.quote
        if quote.asset_kind != self.asset_kind or quote.identity_key != baseline.identity_key:
            raise ValueError(f"N3 quote identity mismatch for {baseline.identity_key}")
        period_baselines = dict(baseline.periods)
        period_baselines["30m"] = _thirty_minute_baseline(thirty_minute_reference)
        transitions = {
            period: (
                thirty_minute_transition(
                    current_price=quote.current_price,
                    current_amount=metric.virtual_amounts.get(period),
                    baseline=period_baselines[period],
                )
                if period == "30m"
                else realtime_transition(
                    period=period,
                    current_price=quote.current_price,
                    current_amount=metric.virtual_amounts.get(period),
                    baseline=period_baselines[period],
                )
            )
            for period in RUNTIME_PERIODS
        }
        return self._state_type(
            source_condition_run_id=baseline.source_condition_run_id,
            source_trade_date=baseline.source_trade_date,
            for_trade_date=baseline.for_trade_date,
            asset_kind=baseline.asset_kind,
            identity_key=baseline.identity_key,
            exchange=baseline.exchange,
            code=baseline.code,
            name=baseline.name,
            source_transitions={
                period: period_baselines[period].source_transition
                for period in RUNTIME_PERIODS
            },
            source_amounts={
                period: period_baselines[period].source_amount
                for period in RUNTIME_PERIODS
            },
            comparison_amounts={
                period: period_baselines[period].comparison_amount
                for period in RUNTIME_PERIODS
            },
            realtime_transitions=transitions,
            realtime_virtual_amounts=metric.virtual_amounts,
            current_price=quote.current_price,
            cumulative_amount=quote.amount,
            source_time=quote.source_time,
            observed_at=quote.observed_at,
            provider=quote.provider,
            live_status="available",
            fresh=True,
            last_success_at=metric.last_success_at,
            last_error=metric.last_error,
            source_n3_version=source_n3_version,
        )


class StockStateConsumer(_RuntimeStateConsumer[StockRuntimeState]):
    def __init__(self, baselines: Sequence[N2RuntimeBaseline]) -> None:
        super().__init__(baselines, asset_kind="stock", state_type=StockRuntimeState)


class IndexStateConsumer(_RuntimeStateConsumer[IndexRuntimeState]):
    def __init__(self, baselines: Sequence[N2RuntimeBaseline]) -> None:
        super().__init__(baselines, asset_kind="index", state_type=IndexRuntimeState)


class BoardStateConsumer(_RuntimeStateConsumer[BoardRuntimeState]):
    def __init__(self, baselines: Sequence[N2RuntimeBaseline]) -> None:
        super().__init__(baselines, asset_kind="board", state_type=BoardRuntimeState)


@dataclass(frozen=True, slots=True)
class N4MemoryCycleResult:
    stock: RuntimeStateSnapshot[StockRuntimeState]
    index: RuntimeStateSnapshot[IndexRuntimeState]
    board: RuntimeStateSnapshot[BoardRuntimeState]


class WindowsN4MemoryRuntime:
    """Three independent in-memory consumers with no persistence side effects."""

    def __init__(
        self,
        stock_consumer: StockStateConsumer,
        index_consumer: IndexStateConsumer,
        board_consumer: BoardStateConsumer,
    ) -> None:
        lineage = {
            (
                consumer.read().source_condition_run_id,
                consumer.read().source_trade_date,
                consumer.read().for_trade_date,
            )
            for consumer in (stock_consumer, index_consumer, board_consumer)
        }
        if len(lineage) != 1:
            raise ValueError("all N4 channels must share one N2 lineage and date pair")
        self.stock_consumer = stock_consumer
        self.index_consumer = index_consumer
        self.board_consumer = board_consumer

    @property
    def stock_states(self) -> Mapping[str, StockRuntimeState]:
        return self.stock_consumer.states

    @property
    def index_states(self) -> Mapping[str, IndexRuntimeState]:
        return self.index_consumer.states

    @property
    def board_states(self) -> Mapping[str, BoardRuntimeState]:
        return self.board_consumer.states

    def get_stock_states(self) -> RuntimeStateSnapshot[StockRuntimeState]:
        return self.stock_consumer.read()

    def get_index_states(self) -> RuntimeStateSnapshot[IndexRuntimeState]:
        return self.index_consumer.read()

    def get_board_states(self) -> RuntimeStateSnapshot[BoardRuntimeState]:
        return self.board_consumer.read()

    def consume_views(
        self,
        *,
        stock: ChannelStateView[RealtimeMetric],
        index: ChannelStateView[RealtimeMetric],
        board: ChannelStateView[RealtimeMetric],
        stock_30m_references: Mapping[str, ThirtyMinuteRuntimeReference] | None = None,
        index_30m_references: Mapping[str, ThirtyMinuteRuntimeReference] | None = None,
        board_30m_references: Mapping[str, ThirtyMinuteRuntimeReference] | None = None,
    ) -> N4MemoryCycleResult:
        reference_maps = (
            stock_30m_references or {},
            index_30m_references or {},
            board_30m_references or {},
        )
        for consumer, view, references in zip(
            (self.stock_consumer, self.index_consumer, self.board_consumer),
            (stock, index, board),
            reference_maps,
            strict=True,
        ):
            consumer.prevalidate(view, references)
        with ThreadPoolExecutor(max_workers=3) as pool:
            stock_future = pool.submit(
                self.stock_consumer.consume,
                stock,
                thirty_minute_references=reference_maps[0],
            )
            index_future = pool.submit(
                self.index_consumer.consume,
                index,
                thirty_minute_references=reference_maps[1],
            )
            board_future = pool.submit(
                self.board_consumer.consume,
                board,
                thirty_minute_references=reference_maps[2],
            )
            return N4MemoryCycleResult(
                stock=stock_future.result(),
                index=index_future.result(),
                board=board_future.result(),
            )

    def consume_latest(self, runtime: WindowsN3MemoryRuntime) -> N4MemoryCycleResult:
        return self.consume_views(
            stock=runtime.get_stock_metrics(),
            index=runtime.get_index_metrics(),
            board=runtime.get_board_metrics(),
        )

    def consume_cycle(self, cycle: object) -> N4MemoryCycleResult:
        """Consume the N3 intraday handoff without coupling N3 back to N4."""

        return self.consume_views(
            stock=cycle.metrics.stock,
            index=cycle.metrics.index,
            board=cycle.metrics.board,
            stock_30m_references=cycle.stock_30m_references,
            index_30m_references=cycle.index_30m_references,
            board_30m_references=cycle.board_30m_references,
        )


def realtime_transition(
    *,
    period: str,
    current_price: Decimal | None,
    current_amount: Decimal | None,
    baseline: RuntimePeriodBaseline,
) -> str:
    """Apply existing N2 grade and carry semantics to one realtime metric."""

    if period != baseline.period:
        raise ValueError("period does not match baseline")
    if not baseline.ready or current_price is None or current_amount is None:
        return "unknown"
    high = baseline.comparison_entity_high
    low = baseline.comparison_entity_low
    previous_amount = baseline.comparison_amount
    if high is None or low is None or previous_amount is None:
        return "unknown"
    if previous_amount <= 0:
        grade = "flat"
    elif current_price > high and current_amount > previous_amount:
        grade = "volume_up"
    elif current_price > high and current_amount < previous_amount:
        grade = "low_volume_up"
    elif current_price < low and current_amount > previous_amount:
        grade = "volume_down"
    elif current_price < low and current_amount < previous_amount:
        grade = "low_volume_down"
    else:
        grade = "flat"

    window = TRANSITION_WINDOWS.get(period)
    if grade in {"unknown", "volume_up", "low_volume_down"} or window is None:
        return grade
    if baseline.current_trade_days <= window:
        if baseline.source_transition == "volume_up" and grade in {"low_volume_up", "flat"}:
            return "volume_up"
        if baseline.source_transition == "low_volume_down" and grade in {"volume_down", "flat"}:
            return "low_volume_down"
    return grade


def thirty_minute_transition(
    *,
    current_price: Decimal | None,
    current_amount: Decimal | None,
    baseline: RuntimePeriodBaseline,
) -> str:
    """Classify 30m independently from the D/W/M/Q/Y five-state model."""

    if baseline.period != "30m":
        raise ValueError("30m transition requires a 30m baseline")
    if not baseline.ready or current_price is None or current_amount is None:
        return "unknown"
    high = baseline.comparison_entity_high
    low = baseline.comparison_entity_low
    previous_amount = baseline.comparison_amount
    if high is None or low is None or previous_amount is None or previous_amount <= 0:
        return "unknown"
    if current_price > high and current_amount > previous_amount:
        return "volume_up"
    if current_price < low and current_amount < previous_amount:
        return "shrink_down"
    return "none"


def _initial_state(
    baseline: N2RuntimeBaseline,
    state_type: type[RuntimeStateT],
) -> RuntimeStateT:
    return state_type(
        source_condition_run_id=baseline.source_condition_run_id,
        source_trade_date=baseline.source_trade_date,
        for_trade_date=baseline.for_trade_date,
        asset_kind=baseline.asset_kind,
        identity_key=baseline.identity_key,
        exchange=baseline.exchange,
        code=baseline.code,
        name=baseline.name,
        source_transitions={
            period: (
                "unknown"
                if period == "30m"
                else baseline.periods[period].source_transition
            )
            for period in RUNTIME_PERIODS
        },
        source_amounts={
            period: (
                None
                if period == "30m"
                else baseline.periods[period].source_amount
            )
            for period in RUNTIME_PERIODS
        },
        comparison_amounts={
            period: (
                None
                if period == "30m"
                else baseline.periods[period].comparison_amount
            )
            for period in RUNTIME_PERIODS
        },
        realtime_transitions={},
        realtime_virtual_amounts={},
        current_price=None,
        cumulative_amount=None,
        source_time=None,
        observed_at=None,
        provider=None,
        live_status="unavailable",
        fresh=False,
        last_success_at=None,
        last_error=None,
        source_n3_version=0,
    )


def _require_yyyymmdd(value: str, field: str) -> None:
    if len(value) != 8 or not value.isdigit():
        raise ValueError(f"{field} must be YYYYMMDD")


def build_windows_n4_runtime(model: N3ActiveReadModel) -> WindowsN4MemoryRuntime:
    """Adapt the N2 startup read model without copying user-facing fields."""

    return WindowsN4MemoryRuntime(
        StockStateConsumer(_channel_baselines(model, "stock")),
        IndexStateConsumer(_channel_baselines(model, "index")),
        BoardStateConsumer(_channel_baselines(model, "board")),
    )


def _channel_baselines(
    model: N3ActiveReadModel,
    asset_kind: str,
) -> tuple[N2RuntimeBaseline, ...]:
    return tuple(
        _n2_runtime_baseline(model, row)
        for row in getattr(model, asset_kind)
    )


def _n2_runtime_baseline(
    model: N3ActiveReadModel,
    row: N2ObjectRuntimeInput,
) -> N2RuntimeBaseline:
    periods: dict[str, RuntimePeriodBaseline] = {}
    for period in N2_RUNTIME_PERIODS:
        source = row.periods[period]
        source_amount = _average_source_amount(
            source.completed_amount_sum,
            source.completed_trade_days,
        )
        ready = all(
            value is not None
            for value in (
                source.previous_entity_high,
                source.previous_entity_low,
                source.previous_amount_baseline,
            )
        )
        transition = _source_transition(source.transition)
        periods[period] = RuntimePeriodBaseline(
            period=period,
            source_transition=transition,
            source_amount=source_amount,
            comparison_entity_high=source.previous_entity_high,
            comparison_entity_low=source.previous_entity_low,
            comparison_amount=source.previous_amount_baseline,
            current_trade_days=max(source.completed_trade_days or 1, 1),
            ready=ready,
        )
    return N2RuntimeBaseline(
        source_condition_run_id=model.run_id,
        source_trade_date=model.source_trade_date,
        for_trade_date=model.for_trade_date,
        asset_kind=row.asset_kind,
        identity_key=row.identity_key,
        exchange=row.exchange,
        code=row.code,
        name=row.name,
        periods=periods,
    )


def _source_transition(value: str | None) -> str:
    """Read the N2 period_transition field, including its optional A->B trace form."""

    candidate = value.rsplit("->", 1)[-1].strip() if value else ""
    return candidate if candidate in VALID_TRANSITIONS else "unknown"


def _average_source_amount(
    amount_sum: Decimal | None,
    trade_days: int | None,
) -> Decimal | None:
    if amount_sum is None or trade_days is None or trade_days <= 0:
        return None
    return amount_sum / Decimal(trade_days)


def _thirty_minute_baseline(
    reference: ThirtyMinuteRuntimeReference | None,
) -> RuntimePeriodBaseline:
    if reference is None:
        return RuntimePeriodBaseline(
            period="30m",
            source_transition="unknown",
            source_amount=None,
            comparison_entity_high=None,
            comparison_entity_low=None,
            comparison_amount=None,
            ready=False,
        )
    return RuntimePeriodBaseline(
        period="30m",
        source_transition="unknown",
        source_amount=reference.previous_day_same_window_amount,
        comparison_entity_high=reference.adjacent_completed_entity_high,
        comparison_entity_low=reference.adjacent_completed_entity_low,
        comparison_amount=reference.previous_day_same_window_amount,
        ready=True,
    )
