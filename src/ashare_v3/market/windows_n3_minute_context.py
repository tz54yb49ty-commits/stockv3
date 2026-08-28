"""Windows N3 previous-day minute context kept entirely in memory.

The three provider contracts are intentionally separate so stock, index, and
board minute transports can be replaced independently.  This module performs
no database or filesystem writes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Generic, Protocol, TypeVar

from ashare_v3.market.windows_n3_memory import (
    AverageAmountBaseline,
    RatioAmountBaseline,
    VirtualAmountContext,
)
from ashare_v3.market.windows_n3_snapshot import (
    BoardSnapshotRequest,
    IndexSnapshotRequest,
    StockSnapshotRequest,
)


MINUTES_PER_DAY = 240
MINUTES_PER_WINDOW = 30
WINDOWS_PER_DAY = 8
ELTDX_MINUTE_MAX_WORKERS = 16


@dataclass(frozen=True, slots=True)
class NormalizedMinuteBar:
    identity_key: str
    trade_date: str
    minute_index: int
    time_label: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    amount: Decimal


@dataclass(frozen=True, slots=True)
class ThirtyMinuteWindow:
    bucket_index: int
    bars: tuple[NormalizedMinuteBar, ...]
    cumulative_amounts: tuple[Decimal, ...]
    full_amount: Decimal
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    @property
    def entity_high(self) -> Decimal:
        return max(self.open, self.close)

    @property
    def entity_low(self) -> Decimal:
        return min(self.open, self.close)


@dataclass(frozen=True, slots=True)
class PreviousDayMinuteContext:
    identity_key: str
    source_trade_date: str
    bars: tuple[NormalizedMinuteBar, ...]
    cumulative_day_amounts: tuple[Decimal, ...]
    windows: tuple[ThirtyMinuteWindow, ...]

    @property
    def full_day_amount(self) -> Decimal:
        return self.cumulative_day_amounts[-1]


@dataclass(frozen=True, slots=True)
class ThirtyMinuteRuntimeReference:
    bucket_index: int
    previous_day_same_window_amount: Decimal
    adjacent_completed_entity_high: Decimal
    adjacent_completed_entity_low: Decimal


RequestT = TypeVar("RequestT", StockSnapshotRequest, IndexSnapshotRequest, BoardSnapshotRequest)


@dataclass(frozen=True, slots=True)
class MinuteContextBatch(Generic[RequestT]):
    contexts: Mapping[str, PreviousDayMinuteContext]
    missing_identity_keys: tuple[str, ...]
    errors: tuple[str, ...]
    provider: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "contexts", MappingProxyType(dict(self.contexts)))


class StockMinuteContextProvider(Protocol):
    def fetch_many(
        self,
        requests: Sequence[StockSnapshotRequest],
        trade_date: str,
        *,
        require_complete: bool = True,
    ) -> MinuteContextBatch[StockSnapshotRequest]: ...


class IndexMinuteContextProvider(Protocol):
    def fetch_many(
        self,
        requests: Sequence[IndexSnapshotRequest],
        trade_date: str,
        *,
        require_complete: bool = True,
    ) -> MinuteContextBatch[IndexSnapshotRequest]: ...


class BoardMinuteContextProvider(Protocol):
    def fetch_many(
        self,
        requests: Sequence[BoardSnapshotRequest],
        trade_date: str,
        *,
        require_complete: bool = True,
    ) -> MinuteContextBatch[BoardSnapshotRequest]: ...


class EltdxStockMinuteContextProvider:
    provider_name = "eltdx.stock.bars.1m"

    def __init__(self, client: Any, *, max_workers: int = ELTDX_MINUTE_MAX_WORKERS) -> None:
        self._fetcher = _EltdxMinuteFetcher(client, "stock", max_workers)

    def fetch_many(self, requests, trade_date, *, require_complete=True):
        return self._fetcher.fetch_many(
            requests,
            trade_date,
            require_complete=require_complete,
            provider=self.provider_name,
        )


class EltdxIndexMinuteContextProvider:
    provider_name = "eltdx.index.bars.1m"

    def __init__(self, client: Any, *, max_workers: int = ELTDX_MINUTE_MAX_WORKERS) -> None:
        self._fetcher = _EltdxMinuteFetcher(client, "index", max_workers)

    def fetch_many(self, requests, trade_date, *, require_complete=True):
        return self._fetcher.fetch_many(
            requests,
            trade_date,
            require_complete=require_complete,
            provider=self.provider_name,
        )


class EltdxBoardMinuteContextProvider:
    provider_name = "eltdx.board.bars.1m"

    def __init__(self, client: Any, *, max_workers: int = ELTDX_MINUTE_MAX_WORKERS) -> None:
        self._fetcher = _EltdxMinuteFetcher(client, "board", max_workers)

    def fetch_many(self, requests, trade_date, *, require_complete=True):
        return self._fetcher.fetch_many(
            requests,
            trade_date,
            require_complete=require_complete,
            provider=self.provider_name,
        )


class _EltdxMinuteFetcher:
    def __init__(self, client: Any, asset_kind: str, max_workers: int) -> None:
        if max_workers <= 0:
            raise ValueError("max_workers must be positive")
        self.client = client
        self.asset_kind = asset_kind
        self.max_workers = max_workers

    def fetch_many(
        self,
        requests: Sequence[RequestT],
        trade_date: str,
        *,
        require_complete: bool,
        provider: str,
    ) -> MinuteContextBatch[RequestT]:
        requested = tuple(requests)
        contexts: dict[str, PreviousDayMinuteContext] = {}
        errors: list[str] = []
        if not requested:
            return MinuteContextBatch({}, (), (), provider)
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(self._fetch_one, request, trade_date, require_complete): request
                for request in requested
            }
            for future in as_completed(futures):
                request = futures[future]
                try:
                    context = future.result()
                except Exception as error:
                    errors.append(f"{request.identity_key}:{type(error).__name__}:{error}")
                    continue
                if context is not None:
                    contexts[request.identity_key] = context
        missing = tuple(
            request.identity_key
            for request in requested
            if request.identity_key not in contexts
        )
        return MinuteContextBatch(
            contexts,
            missing,
            tuple(sorted(errors)),
            provider,
        )

    def _fetch_one(
        self,
        request: RequestT,
        trade_date: str,
        require_complete: bool,
    ) -> PreviousDayMinuteContext | None:
        rows = self.client.bars.get(
            _eltdx_code(request),
            period="1m",
            start=0,
            count=800,
            adjust=None,
            kind="stock" if self.asset_kind == "stock" else "index",
        )
        bars = normalize_minute_bars(
            request.identity_key,
            trade_date,
            rows or (),
        )
        if require_complete and len(bars) != MINUTES_PER_DAY:
            return None
        if not bars:
            return None
        return build_minute_context(request.identity_key, trade_date, bars)


def normalize_minute_bars(
    identity_key: str,
    trade_date: str,
    rows: Sequence[Any],
) -> tuple[NormalizedMinuteBar, ...]:
    """Normalize either start-labelled or close-labelled CN A-share minutes."""

    target = _parse_trade_date(trade_date)
    candidates: list[tuple[datetime, Any]] = []
    for row in rows:
        timestamp = _coerce_datetime(_field(row, "time"))
        if timestamp is None or timestamp.date() != target:
            continue
        candidates.append((timestamp, row))
    start_labelled = any(timestamp.time() in {time(9, 30), time(13, 0)} for timestamp, _ in candidates)
    normalized: dict[int, NormalizedMinuteBar] = {}
    for timestamp, row in candidates:
        label_time = timestamp.time().replace(tzinfo=None)
        if start_labelled:
            label_time = (datetime.combine(target, label_time) + timedelta(minutes=1)).time()
        minute_index = minute_index_for_label(label_time)
        if minute_index is None:
            continue
        amount = _decimal(_field(row, "amount"))
        open_price = _decimal(_field(row, "open"))
        high_price = _decimal(_field(row, "high"))
        low_price = _decimal(_field(row, "low"))
        close_price = _decimal(_field(row, "close"))
        if None in {amount, open_price, high_price, low_price, close_price} or amount < 0:
            continue
        normalized[minute_index] = NormalizedMinuteBar(
            identity_key=identity_key,
            trade_date=trade_date,
            minute_index=minute_index,
            time_label=label_time.strftime("%H:%M"),
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            amount=amount,
        )
    return tuple(normalized[index] for index in sorted(normalized))


def build_minute_context(
    identity_key: str,
    trade_date: str,
    bars: Sequence[NormalizedMinuteBar],
) -> PreviousDayMinuteContext:
    ordered = tuple(sorted(bars, key=lambda row: row.minute_index))
    if not ordered:
        raise ValueError("minute bars are required")
    day_cumulative: list[Decimal] = []
    total = Decimal(0)
    for row in ordered:
        total += row.amount
        day_cumulative.append(total)
    windows: list[ThirtyMinuteWindow] = []
    for bucket_index in range(WINDOWS_PER_DAY):
        first_index = bucket_index * MINUTES_PER_WINDOW + 1
        last_index = first_index + MINUTES_PER_WINDOW - 1
        window_bars = tuple(
            row for row in ordered if first_index <= row.minute_index <= last_index
        )
        if len(window_bars) != MINUTES_PER_WINDOW:
            continue
        cumulative: list[Decimal] = []
        window_total = Decimal(0)
        for row in window_bars:
            window_total += row.amount
            cumulative.append(window_total)
        windows.append(
            ThirtyMinuteWindow(
                bucket_index=bucket_index,
                bars=window_bars,
                cumulative_amounts=tuple(cumulative),
                full_amount=window_total,
                open=window_bars[0].open,
                high=max(row.high for row in window_bars),
                low=min(row.low for row in window_bars),
                close=window_bars[-1].close,
            )
        )
    return PreviousDayMinuteContext(
        identity_key=identity_key,
        source_trade_date=trade_date,
        bars=ordered,
        cumulative_day_amounts=tuple(day_cumulative),
        windows=tuple(windows),
    )


def build_cycle_inputs(
    previous_contexts: Mapping[str, PreviousDayMinuteContext],
    current_contexts: Mapping[str, PreviousDayMinuteContext],
    higher_periods: Mapping[str, Mapping[str, AverageAmountBaseline]],
    observed_at: datetime,
) -> tuple[
    Mapping[str, VirtualAmountContext],
    Mapping[str, Decimal],
    Mapping[str, ThirtyMinuteRuntimeReference],
]:
    """Build time-positioned N3 inputs without fabricating missing context."""

    elapsed_day = trading_elapsed_minutes(observed_at.time().replace(tzinfo=None))
    bucket_position = trading_bucket_position(observed_at.time().replace(tzinfo=None))
    contexts: dict[str, VirtualAmountContext] = {}
    current_elapsed: dict[str, Decimal] = {}
    references: dict[str, ThirtyMinuteRuntimeReference] = {}
    for identity_key, previous in previous_contexts.items():
        if elapsed_day <= 0 or elapsed_day > len(previous.cumulative_day_amounts):
            continue
        day_basis = RatioAmountBaseline(
            previous.cumulative_day_amounts[elapsed_day - 1],
            previous.full_day_amount,
        )
        window_basis = None
        if bucket_position is not None:
            bucket_index, bucket_elapsed = bucket_position
            previous_window = _window(previous, bucket_index)
            if previous_window is not None and bucket_elapsed > 0:
                window_basis = RatioAmountBaseline(
                    previous_window.cumulative_amounts[bucket_elapsed - 1],
                    previous_window.full_amount,
                )
            adjacent = _adjacent_window(previous, current_contexts.get(identity_key), bucket_index)
            if previous_window is not None and adjacent is not None:
                references[identity_key] = ThirtyMinuteRuntimeReference(
                    bucket_index=bucket_index,
                    previous_day_same_window_amount=previous_window.full_amount,
                    adjacent_completed_entity_high=adjacent.entity_high,
                    adjacent_completed_entity_low=adjacent.entity_low,
                )
            current_amount = _partial_window_amount(
                current_contexts.get(identity_key),
                bucket_index,
            )
            if current_amount is not None:
                current_elapsed[identity_key] = current_amount
            elif bucket_elapsed == 0:
                current_elapsed[identity_key] = Decimal(0)
        contexts[identity_key] = VirtualAmountContext(
            window_30m=window_basis,
            day=day_basis,
            higher_periods=higher_periods.get(identity_key, {}),
        )
    return (
        MappingProxyType(contexts),
        MappingProxyType(current_elapsed),
        MappingProxyType(references),
    )


def minute_index_for_label(label: time) -> int | None:
    if time(9, 31) <= label <= time(11, 30):
        return int((datetime.combine(date.min, label) - datetime.combine(date.min, time(9, 30))).total_seconds() // 60)
    if time(13, 1) <= label <= time(15, 0):
        return 120 + int((datetime.combine(date.min, label) - datetime.combine(date.min, time(13, 0))).total_seconds() // 60)
    return None


def trading_elapsed_minutes(wall_time: time) -> int:
    if wall_time <= time(9, 30):
        return 0
    if wall_time <= time(11, 30):
        return min(120, int((datetime.combine(date.min, wall_time) - datetime.combine(date.min, time(9, 30))).total_seconds() // 60))
    if wall_time < time(13, 0):
        return 120
    if wall_time <= time(15, 0):
        return 120 + min(120, int((datetime.combine(date.min, wall_time) - datetime.combine(date.min, time(13, 0))).total_seconds() // 60))
    return 240


def trading_bucket_position(wall_time: time) -> tuple[int, int] | None:
    starts = (
        time(9, 30), time(10, 0), time(10, 30), time(11, 0),
        time(13, 0), time(13, 30), time(14, 0), time(14, 30),
    )
    ends = (
        time(10, 0), time(10, 30), time(11, 0), time(11, 30),
        time(13, 30), time(14, 0), time(14, 30), time(15, 0),
    )
    for index, (start, end) in enumerate(zip(starts, ends, strict=True)):
        if start <= wall_time < end or (index == 7 and wall_time == end):
            elapsed = int((datetime.combine(date.min, wall_time) - datetime.combine(date.min, start)).total_seconds() // 60)
            return index, min(MINUTES_PER_WINDOW, max(0, elapsed))
    return None


def _adjacent_window(
    previous: PreviousDayMinuteContext,
    current: PreviousDayMinuteContext | None,
    bucket_index: int,
) -> ThirtyMinuteWindow | None:
    if bucket_index == 0:
        return _window(previous, WINDOWS_PER_DAY - 1)
    return _window(current, bucket_index - 1)


def _window(context: PreviousDayMinuteContext | None, index: int) -> ThirtyMinuteWindow | None:
    if context is None:
        return None
    return next((window for window in context.windows if window.bucket_index == index), None)


def _partial_window_amount(
    context: PreviousDayMinuteContext | None,
    bucket_index: int,
) -> Decimal | None:
    if context is None:
        return None
    first_index = bucket_index * MINUTES_PER_WINDOW + 1
    last_index = first_index + MINUTES_PER_WINDOW - 1
    bars = tuple(
        row for row in context.bars if first_index <= row.minute_index <= last_index
    )
    if not bars:
        return None
    return sum((row.amount for row in bars), start=Decimal(0))


def _eltdx_code(request: RequestT) -> str:
    if request.identity_key.startswith("board:"):
        return f"sh{request.code}"
    prefix = request.exchange.lower()
    if prefix not in {"sh", "sz", "bj"}:
        prefix = "sh" if request.code.startswith(("0", "8")) else "sz"
    return f"{prefix}{request.code}"


def _field(row: Any, name: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(name)
    return getattr(row, name, None)


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, str):
        normalized = value.strip().replace("T", " ")
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d %H:%M"):
            try:
                return datetime.strptime(normalized, pattern)
            except ValueError:
                continue
    return None


def _parse_trade_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as error:
        raise ValueError("trade_date must be YYYYMMDD") from error
