"""Windows N3 closed-minute metrics for active N5 identities.

Only closed 1m bars are fetched.  The 5m, 30m, and 120m values are derived
from that single immutable sequence.  This module owns no database or event
side effects.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from threading import RLock
from types import MappingProxyType
from typing import Any, Generic, Protocol, TypeVar

from ashare_v3.market.windows_n3_minute_context import (
    MINUTES_PER_DAY,
    NormalizedMinuteBar,
    PreviousDayMinuteContext,
    normalize_minute_bars,
)
from ashare_v3.market.windows_n3_snapshot import (
    BoardSnapshotRequest,
    IndexSnapshotRequest,
    StockSnapshotRequest,
)


ACTION_INITIAL_BAR_COUNT = 600
ACTION_INCREMENTAL_BAR_COUNT = 3
ACTION_MAX_WORKERS = 16
ACTION_METRIC_POLICY_VERSION = "windows_n3_action_metric_v1"
BOUNDARY_POLICY_VERSION = "n3.action_confirmation_boundary.v1"
VIRTUAL_AMOUNT_POLICY_VERSION = "previous_day_same_window_elapsed_ratio_v1"

PREVIOUS_DAY_SOURCE = "previous_trade_date_last_period"
SAME_DAY_SOURCE = "same_trade_date_previous_period"
UNAVAILABLE_SOURCE = "not_available"

RequestT = TypeVar(
    "RequestT",
    StockSnapshotRequest,
    IndexSnapshotRequest,
    BoardSnapshotRequest,
)


@dataclass(frozen=True, slots=True)
class ActionConfirmationMetric:
    asset_kind: str
    identity_key: str
    trade_date: str
    provider: str
    metric_time: datetime | None
    metric_minute_label: str | None
    current_price: Decimal | None
    previous_120m_body_high: Decimal | None
    previous_120m_body_low: Decimal | None
    previous_30m_body_high: Decimal | None
    previous_30m_body_low: Decimal | None
    previous_5m_body_high: Decimal | None
    previous_5m_body_low: Decimal | None
    previous_1m_body_high: Decimal | None
    previous_1m_body_low: Decimal | None
    current_5m_virtual_amount: Decimal | None
    previous_5m_full_amount: Decimal | None
    current_1m_amount: Decimal | None
    previous_1m_amount: Decimal | None
    current_30m_virtual_amount: Decimal | None
    previous_day_same_window_amount: Decimal | None
    previous_30m_full_amount: Decimal | None
    is_first_1m_of_day: bool
    is_first_5m_of_day: bool
    first_1m_amount_default_pass: bool
    first_5m_amount_default_pass: bool
    previous_1m_period_source: str
    previous_5m_period_source: str
    previous_30m_period_source: str
    previous_120m_period_source: str
    amount_unit: str
    boundary_policy_version: str
    virtual_amount_policy_version: str
    metric_policy_version: str
    metric_ready: bool
    metric_quality_status: str
    error_summary: str | None
    expected_minute_index: int
    observed_minute_index: int | None


@dataclass(frozen=True, slots=True)
class ActionMetricBatch(Generic[RequestT]):
    metrics: Mapping[str, ActionConfirmationMetric]
    missing_identity_keys: tuple[str, ...]
    provider: str
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))


class StockActionMetricProvider(Protocol):
    def fetch_many(
        self,
        requests: Sequence[StockSnapshotRequest],
        trade_date: str,
        previous_contexts: Mapping[str, PreviousDayMinuteContext],
        expected_minute_index: int,
    ) -> ActionMetricBatch[StockSnapshotRequest]: ...


class IndexActionMetricProvider(Protocol):
    def fetch_many(
        self,
        requests: Sequence[IndexSnapshotRequest],
        trade_date: str,
        previous_contexts: Mapping[str, PreviousDayMinuteContext],
        expected_minute_index: int,
    ) -> ActionMetricBatch[IndexSnapshotRequest]: ...


class BoardActionMetricProvider(Protocol):
    def fetch_many(
        self,
        requests: Sequence[BoardSnapshotRequest],
        trade_date: str,
        previous_contexts: Mapping[str, PreviousDayMinuteContext],
        expected_minute_index: int,
    ) -> ActionMetricBatch[BoardSnapshotRequest]: ...


class EltdxStockActionMetricProvider:
    provider_name = "eltdx.stock.closed_1m"

    def __init__(self, client: Any, *, max_workers: int = ACTION_MAX_WORKERS) -> None:
        self._fetcher = _EltdxActionMetricFetcher(client, "stock", max_workers)

    def fetch_many(self, requests, trade_date, previous_contexts, expected_minute_index):
        return self._fetcher.fetch_many(
            requests,
            trade_date,
            previous_contexts,
            expected_minute_index,
            self.provider_name,
        )


class EltdxIndexActionMetricProvider:
    provider_name = "eltdx.index.closed_1m"

    def __init__(self, client: Any, *, max_workers: int = ACTION_MAX_WORKERS) -> None:
        self._fetcher = _EltdxActionMetricFetcher(client, "index", max_workers)

    def fetch_many(self, requests, trade_date, previous_contexts, expected_minute_index):
        return self._fetcher.fetch_many(
            requests,
            trade_date,
            previous_contexts,
            expected_minute_index,
            self.provider_name,
        )


class EltdxBoardActionMetricProvider:
    provider_name = "eltdx.board.closed_1m"

    def __init__(self, client: Any, *, max_workers: int = ACTION_MAX_WORKERS) -> None:
        self._fetcher = _EltdxActionMetricFetcher(client, "board", max_workers)

    def fetch_many(self, requests, trade_date, previous_contexts, expected_minute_index):
        return self._fetcher.fetch_many(
            requests,
            trade_date,
            previous_contexts,
            expected_minute_index,
            self.provider_name,
        )


class _EltdxActionMetricFetcher:
    def __init__(self, client: Any, asset_kind: str, max_workers: int) -> None:
        if max_workers <= 0:
            raise ValueError("max_workers must be positive")
        self.client = client
        self.asset_kind = asset_kind
        self.max_workers = max_workers
        self._cache: dict[tuple[str, str], tuple[NormalizedMinuteBar, ...]] = {}
        self._consume_lock = RLock()

    def fetch_many(
        self,
        requests: Sequence[RequestT],
        trade_date: str,
        previous_contexts: Mapping[str, PreviousDayMinuteContext],
        expected_minute_index: int,
        provider: str,
    ) -> ActionMetricBatch[RequestT]:
        if not 1 <= expected_minute_index <= MINUTES_PER_DAY:
            raise ValueError("expected_minute_index must be between 1 and 240")
        requested = _dedupe_requests(requests)
        active_keys = {(trade_date, row.identity_key) for row in requested}
        with self._consume_lock:
            self._cache = {
                key: bars for key, bars in self._cache.items() if key in active_keys
            }
            fetched: dict[str, tuple[NormalizedMinuteBar, ...]] = {}
            errors: list[str] = []
            with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                futures = {
                    pool.submit(
                        self._fetch_one,
                        request,
                        trade_date,
                        expected_minute_index,
                    ): request
                    for request in requested
                }
                for future in as_completed(futures):
                    request = futures[future]
                    try:
                        fetched[request.identity_key] = future.result()
                    except Exception as error:
                        errors.append(
                            f"{request.identity_key}:{type(error).__name__}:{error}"
                        )
            metrics: dict[str, ActionConfirmationMetric] = {}
            missing: list[str] = []
            for request in requested:
                bars = fetched.get(request.identity_key, ())
                metric = build_action_confirmation_metric(
                    asset_kind=self.asset_kind,
                    identity_key=request.identity_key,
                    trade_date=trade_date,
                    provider=provider,
                    current_bars=bars,
                    previous_context=previous_contexts.get(request.identity_key),
                    expected_minute_index=expected_minute_index,
                )
                metrics[request.identity_key] = metric
                if not metric.metric_ready:
                    missing.append(request.identity_key)
            return ActionMetricBatch(
                metrics=metrics,
                missing_identity_keys=tuple(missing),
                provider=provider,
                errors=tuple(sorted(errors)),
            )

    def _fetch_one(
        self,
        request: RequestT,
        trade_date: str,
        expected_minute_index: int,
    ) -> tuple[NormalizedMinuteBar, ...]:
        cache_key = (trade_date, request.identity_key)
        cached = self._cache.get(cache_key, ())
        count = (
            ACTION_INCREMENTAL_BAR_COUNT
            if cached
            else ACTION_INITIAL_BAR_COUNT
        )
        response = self.client.bars.get(
            _eltdx_code(request),
            period="1m",
            start=0,
            count=count,
            adjust=None,
            kind="stock" if self.asset_kind == "stock" else "index",
        )
        rows = getattr(response, "bars", response)
        normalized = normalize_minute_bars(
            request.identity_key,
            trade_date,
            _close_labelled_eltdx_rows(rows or ()),
        )
        merged = _merge_bars(cached, normalized, expected_minute_index)
        self._cache[cache_key] = merged
        return merged


def build_action_confirmation_metric(
    *,
    asset_kind: str,
    identity_key: str,
    trade_date: str,
    provider: str,
    current_bars: Sequence[NormalizedMinuteBar],
    previous_context: PreviousDayMinuteContext | None,
    expected_minute_index: int,
) -> ActionConfirmationMetric:
    ordered = tuple(sorted(current_bars, key=lambda row: row.minute_index))
    observed = ordered[-1].minute_index if ordered else None
    if previous_context is None:
        return _pending_metric(
            asset_kind, identity_key, trade_date, provider,
            expected_minute_index, observed, "previous_day_context_missing",
        )
    if (
        len(previous_context.bars) != MINUTES_PER_DAY
        or len(previous_context.windows) != 8
    ):
        return _pending_metric(
            asset_kind, identity_key, trade_date, provider,
            expected_minute_index, observed, "previous_day_context_incomplete",
        )
    if tuple(row.minute_index for row in ordered) != tuple(
        range(1, expected_minute_index + 1)
    ):
        return _pending_metric(
            asset_kind, identity_key, trade_date, provider,
            expected_minute_index, observed, "expected_closed_minute_missing",
        )

    latest = ordered[-1]
    previous_rows: dict[int, tuple[NormalizedMinuteBar, ...]] = {}
    previous_sources: dict[int, str] = {}
    for size in (1, 5, 30, 120):
        rows, source = _previous_period_rows(
            ordered, previous_context.bars, expected_minute_index, size
        )
        previous_rows[size] = rows
        previous_sources[size] = source

    current_5m, previous_same_5m = _current_and_previous_same_window(
        ordered, previous_context.bars, expected_minute_index, 5
    )
    current_30m, previous_same_30m = _current_and_previous_same_window(
        ordered, previous_context.bars, expected_minute_index, 30
    )
    virtual_5m = _same_window_virtual_amount(current_5m, previous_same_5m)
    virtual_30m = _same_window_virtual_amount(current_30m, previous_same_30m)

    first_1m = previous_sources[1] == PREVIOUS_DAY_SOURCE
    first_5m = previous_sources[5] == PREVIOUS_DAY_SOURCE
    previous_1m_amount = None if first_1m else _amount(previous_rows[1])
    previous_5m_amount = None if first_5m else _amount(previous_rows[5])
    previous_30m_amount = (
        None
        if previous_sources[30] == PREVIOUS_DAY_SOURCE
        else _amount(previous_rows[30])
    )
    bounds = {
        size: _body_bounds(rows)
        for size, rows in previous_rows.items()
    }
    required = (
        latest.close,
        bounds[120][0], bounds[120][1],
        bounds[30][0], bounds[30][1],
        bounds[5][0], bounds[5][1],
        bounds[1][0], bounds[1][1],
        virtual_5m,
        latest.amount,
        virtual_30m,
        _amount(previous_same_30m),
    )
    ready = all(value is not None for value in required)
    if not first_1m:
        ready = ready and previous_1m_amount is not None
    if not first_5m:
        ready = ready and previous_5m_amount is not None

    return ActionConfirmationMetric(
        asset_kind=asset_kind,
        identity_key=identity_key,
        trade_date=trade_date,
        provider=provider,
        metric_time=_metric_time(trade_date, latest.time_label),
        metric_minute_label=latest.time_label,
        current_price=latest.close,
        previous_120m_body_high=bounds[120][0],
        previous_120m_body_low=bounds[120][1],
        previous_30m_body_high=bounds[30][0],
        previous_30m_body_low=bounds[30][1],
        previous_5m_body_high=bounds[5][0],
        previous_5m_body_low=bounds[5][1],
        previous_1m_body_high=bounds[1][0],
        previous_1m_body_low=bounds[1][1],
        current_5m_virtual_amount=virtual_5m,
        previous_5m_full_amount=previous_5m_amount,
        current_1m_amount=latest.amount,
        previous_1m_amount=previous_1m_amount,
        current_30m_virtual_amount=virtual_30m,
        previous_day_same_window_amount=_amount(previous_same_30m),
        previous_30m_full_amount=previous_30m_amount,
        is_first_1m_of_day=first_1m,
        is_first_5m_of_day=first_5m,
        first_1m_amount_default_pass=first_1m,
        first_5m_amount_default_pass=first_5m,
        previous_1m_period_source=previous_sources[1],
        previous_5m_period_source=previous_sources[5],
        previous_30m_period_source=previous_sources[30],
        previous_120m_period_source=previous_sources[120],
        amount_unit="yuan",
        boundary_policy_version=BOUNDARY_POLICY_VERSION,
        virtual_amount_policy_version=VIRTUAL_AMOUNT_POLICY_VERSION,
        metric_policy_version=ACTION_METRIC_POLICY_VERSION,
        metric_ready=ready,
        metric_quality_status="passed" if ready else "pending",
        error_summary=None if ready else "virtual_amount_reference_unavailable",
        expected_minute_index=expected_minute_index,
        observed_minute_index=observed,
    )


def _pending_metric(
    asset_kind: str,
    identity_key: str,
    trade_date: str,
    provider: str,
    expected_minute_index: int,
    observed_minute_index: int | None,
    error: str,
) -> ActionConfirmationMetric:
    return ActionConfirmationMetric(
        asset_kind=asset_kind,
        identity_key=identity_key,
        trade_date=trade_date,
        provider=provider,
        metric_time=None,
        metric_minute_label=None,
        current_price=None,
        previous_120m_body_high=None,
        previous_120m_body_low=None,
        previous_30m_body_high=None,
        previous_30m_body_low=None,
        previous_5m_body_high=None,
        previous_5m_body_low=None,
        previous_1m_body_high=None,
        previous_1m_body_low=None,
        current_5m_virtual_amount=None,
        previous_5m_full_amount=None,
        current_1m_amount=None,
        previous_1m_amount=None,
        current_30m_virtual_amount=None,
        previous_day_same_window_amount=None,
        previous_30m_full_amount=None,
        is_first_1m_of_day=False,
        is_first_5m_of_day=False,
        first_1m_amount_default_pass=False,
        first_5m_amount_default_pass=False,
        previous_1m_period_source=UNAVAILABLE_SOURCE,
        previous_5m_period_source=UNAVAILABLE_SOURCE,
        previous_30m_period_source=UNAVAILABLE_SOURCE,
        previous_120m_period_source=UNAVAILABLE_SOURCE,
        amount_unit="yuan",
        boundary_policy_version=BOUNDARY_POLICY_VERSION,
        virtual_amount_policy_version=VIRTUAL_AMOUNT_POLICY_VERSION,
        metric_policy_version=ACTION_METRIC_POLICY_VERSION,
        metric_ready=False,
        metric_quality_status="pending",
        error_summary=error,
        expected_minute_index=expected_minute_index,
        observed_minute_index=observed_minute_index,
    )


def _previous_period_rows(
    current: Sequence[NormalizedMinuteBar],
    previous: Sequence[NormalizedMinuteBar],
    position: int,
    size: int,
) -> tuple[tuple[NormalizedMinuteBar, ...], str]:
    current_start = ((position - 1) // size) * size + 1
    if current_start == 1:
        return tuple(previous[-size:]), PREVIOUS_DAY_SOURCE
    first = current_start - size
    last = current_start - 1
    rows = tuple(row for row in current if first <= row.minute_index <= last)
    if len(rows) != size:
        return (), UNAVAILABLE_SOURCE
    return rows, SAME_DAY_SOURCE

def _current_and_previous_same_window(
    current: Sequence[NormalizedMinuteBar],
    previous: Sequence[NormalizedMinuteBar],
    position: int,
    size: int,
) -> tuple[tuple[NormalizedMinuteBar, ...], tuple[NormalizedMinuteBar, ...]]:
    start = ((position - 1) // size) * size + 1
    current_rows = tuple(row for row in current if start <= row.minute_index <= position)
    previous_rows = tuple(
        row for row in previous if start <= row.minute_index < start + size
    )
    return current_rows, previous_rows


def _same_window_virtual_amount(
    current: Sequence[NormalizedMinuteBar],
    previous_full: Sequence[NormalizedMinuteBar],
) -> Decimal | None:
    if not current or len(previous_full) < len(current):
        return None
    current_elapsed = _amount(current)
    previous_elapsed = _amount(previous_full[: len(current)])
    previous_amount = _amount(previous_full)
    if (
        current_elapsed is None
        or previous_elapsed is None
        or previous_amount is None
        or previous_elapsed <= 0
        or previous_amount <= 0
    ):
        return None
    return current_elapsed / previous_elapsed * previous_amount


def _body_bounds(
    rows: Sequence[NormalizedMinuteBar],
) -> tuple[Decimal | None, Decimal | None]:
    if not rows:
        return None, None
    return max(rows[0].open, rows[-1].close), min(rows[0].open, rows[-1].close)


def _amount(rows: Sequence[NormalizedMinuteBar]) -> Decimal | None:
    if not rows:
        return None
    return sum((row.amount for row in rows), start=Decimal(0))


def _merge_bars(
    cached: Sequence[NormalizedMinuteBar],
    fetched: Sequence[NormalizedMinuteBar],
    expected_minute_index: int,
) -> tuple[NormalizedMinuteBar, ...]:
    merged = {row.minute_index: row for row in cached}
    merged.update({row.minute_index: row for row in fetched})
    return tuple(
        merged[index]
        for index in sorted(merged)
        if index <= expected_minute_index
    )


def _dedupe_requests(requests: Sequence[RequestT]) -> tuple[RequestT, ...]:
    by_identity: dict[str, RequestT] = {}
    for request in requests:
        by_identity.setdefault(request.identity_key, request)
    return tuple(by_identity.values())


def _eltdx_code(request: RequestT) -> str:
    if request.identity_key.startswith("board:"):
        return f"sh{request.code}"
    prefix = request.exchange.lower()
    if prefix not in {"sh", "sz", "bj"}:
        prefix = "sh" if request.code.startswith(("0", "8")) else "sz"
    return f"{prefix}{request.code}"


def _close_labelled_eltdx_rows(rows: Sequence[Any]) -> tuple[dict[str, Any], ...]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        timestamp = _coerce_datetime(_field(row, "time"))
        if timestamp is None:
            continue
        normalized.append(
            {
                "time": timestamp + timedelta(minutes=1),
                "open": _field(row, "open"),
                "high": _field(row, "high"),
                "low": _field(row, "low"),
                "close": _field(row, "close"),
                "amount": _field(row, "amount"),
            }
        )
    return tuple(normalized)


def _field(row: Any, name: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(name)
    return getattr(row, name, None)


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, str):
        normalized = value.strip().replace("T", " ")
        for pattern in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y%m%d%H%M%S",
            "%Y%m%d%H%M",
        ):
            try:
                return datetime.strptime(normalized, pattern)
            except ValueError:
                continue
    return None


def _metric_time(trade_date: str, time_label: str) -> datetime:
    return datetime.strptime(f"{trade_date} {time_label}", "%Y%m%d %H:%M")
