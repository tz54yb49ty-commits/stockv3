"""Windows N3 realtime snapshot provider contracts.

The stock, index, and board contracts are deliberately distinct.  Providers
receive injected vendor clients, perform no database work, and return one
normalized in-memory batch.  Importing this module never connects to a quote
server.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from threading import RLock
from typing import Any, Protocol
from zoneinfo import ZoneInfo


ELTDX_SNAPSHOT_BATCH_SIZE = 80
ELTDX_SNAPSHOT_MAX_WORKERS = 16
TQ_SNAPSHOT_MAX_WORKERS = 1
SHANGHAI_TIMEZONE = ZoneInfo("Asia/Shanghai")
_TQ_RPC_LOCK = RLock()


@dataclass(frozen=True, slots=True)
class StockSnapshotRequest:
    identity_key: str
    exchange: str
    code: str
    name: str

    def __post_init__(self) -> None:
        _validate_request(self.identity_key, "stock", self.exchange, self.code)


@dataclass(frozen=True, slots=True)
class IndexSnapshotRequest:
    identity_key: str
    exchange: str
    code: str
    name: str

    def __post_init__(self) -> None:
        _validate_request(self.identity_key, "index", self.exchange, self.code)


@dataclass(frozen=True, slots=True)
class BoardSnapshotRequest:
    identity_key: str
    exchange: str
    code: str
    name: str

    def __post_init__(self) -> None:
        _validate_request(self.identity_key, "board", self.exchange, self.code)


SnapshotRequest = StockSnapshotRequest | IndexSnapshotRequest | BoardSnapshotRequest


@dataclass(frozen=True, slots=True)
class RealtimeQuote:
    asset_kind: str
    identity_key: str
    exchange: str
    code: str
    name: str
    current_price: Decimal | None
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    pre_close: Decimal | None
    volume: Decimal | None
    amount: Decimal | None
    source_time: datetime
    observed_at: datetime
    provider: str
    source_time_raw: Any = None


@dataclass(frozen=True, slots=True)
class StockSnapshotBatch:
    rows: tuple[RealtimeQuote, ...]
    missing_identity_keys: tuple[str, ...]
    provider: str
    observed_at: datetime
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IndexSnapshotBatch:
    rows: tuple[RealtimeQuote, ...]
    missing_identity_keys: tuple[str, ...]
    provider: str
    observed_at: datetime
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BoardSnapshotBatch:
    rows: tuple[RealtimeQuote, ...]
    missing_identity_keys: tuple[str, ...]
    provider: str
    observed_at: datetime
    errors: tuple[str, ...] = ()


class StockSnapshotProvider(Protocol):
    def fetch_many(self, requests: Sequence[StockSnapshotRequest]) -> StockSnapshotBatch: ...


class IndexSnapshotProvider(Protocol):
    def fetch_many(self, requests: Sequence[IndexSnapshotRequest]) -> IndexSnapshotBatch: ...


class BoardSnapshotProvider(Protocol):
    def fetch_many(self, requests: Sequence[BoardSnapshotRequest]) -> BoardSnapshotBatch: ...


class EltdxStockSnapshotProvider:
    provider_name = "eltdx.stock.get_snapshots"

    def __init__(
        self,
        client: Any,
        *,
        batch_size: int = ELTDX_SNAPSHOT_BATCH_SIZE,
        max_workers: int = ELTDX_SNAPSHOT_MAX_WORKERS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._fetcher = _EltdxBatchFetcher(client, batch_size, max_workers, clock)

    def fetch_many(self, requests: Sequence[StockSnapshotRequest]) -> StockSnapshotBatch:
        return self._fetcher.fetch(
            requests,
            asset_kind="stock",
            provider=self.provider_name,
            code_formatter=_eltdx_stock_code,
            batch_factory=StockSnapshotBatch,
        )


class EltdxIndexSnapshotProvider:
    provider_name = "eltdx.index.get_snapshots"

    def __init__(
        self,
        client: Any,
        *,
        batch_size: int = ELTDX_SNAPSHOT_BATCH_SIZE,
        max_workers: int = ELTDX_SNAPSHOT_MAX_WORKERS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._fetcher = _EltdxBatchFetcher(client, batch_size, max_workers, clock)

    def fetch_many(self, requests: Sequence[IndexSnapshotRequest]) -> IndexSnapshotBatch:
        return self._fetcher.fetch(
            requests,
            asset_kind="index",
            provider=self.provider_name,
            code_formatter=_eltdx_index_code,
            batch_factory=IndexSnapshotBatch,
        )


class EltdxBoardSnapshotProvider:
    provider_name = "eltdx.board.get_snapshots"

    def __init__(
        self,
        client: Any,
        *,
        batch_size: int = ELTDX_SNAPSHOT_BATCH_SIZE,
        max_workers: int = ELTDX_SNAPSHOT_MAX_WORKERS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._fetcher = _EltdxBatchFetcher(client, batch_size, max_workers, clock)

    def fetch_many(self, requests: Sequence[BoardSnapshotRequest]) -> BoardSnapshotBatch:
        return self._fetcher.fetch(
            requests,
            asset_kind="board",
            provider=self.provider_name,
            code_formatter=_eltdx_board_code,
            batch_factory=BoardSnapshotBatch,
        )


class TQStockSnapshotProvider:
    provider_name = "tq.stock.get_market_snapshot"

    def __init__(
        self,
        client: Any,
        *,
        max_workers: int = TQ_SNAPSHOT_MAX_WORKERS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._fetcher = _TQSnapshotFetcher(client, max_workers, clock)

    def fetch_many(self, requests: Sequence[StockSnapshotRequest]) -> StockSnapshotBatch:
        return self._fetcher.fetch(
            requests,
            asset_kind="stock",
            provider=self.provider_name,
            code_formatter=_tq_stock_code,
            batch_factory=StockSnapshotBatch,
        )


class TQIndexSnapshotProvider:
    provider_name = "tq.index.get_market_snapshot"

    def __init__(
        self,
        client: Any,
        *,
        max_workers: int = TQ_SNAPSHOT_MAX_WORKERS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._fetcher = _TQSnapshotFetcher(client, max_workers, clock)

    def fetch_many(self, requests: Sequence[IndexSnapshotRequest]) -> IndexSnapshotBatch:
        return self._fetcher.fetch(
            requests,
            asset_kind="index",
            provider=self.provider_name,
            code_formatter=_tq_index_code,
            batch_factory=IndexSnapshotBatch,
        )


class TQBoardSnapshotProvider:
    provider_name = "tq.board.get_market_snapshot"

    def __init__(
        self,
        client: Any,
        *,
        max_workers: int = TQ_SNAPSHOT_MAX_WORKERS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._fetcher = _TQSnapshotFetcher(client, max_workers, clock)

    def fetch_many(self, requests: Sequence[BoardSnapshotRequest]) -> BoardSnapshotBatch:
        return self._fetcher.fetch(
            requests,
            asset_kind="board",
            provider=self.provider_name,
            code_formatter=_tq_board_code,
            batch_factory=BoardSnapshotBatch,
        )


class StockSnapshotProviderChain:
    def __init__(self, primary: StockSnapshotProvider, fallback: StockSnapshotProvider) -> None:
        self._primary = primary
        self._fallback = fallback

    def fetch_many(self, requests: Sequence[StockSnapshotRequest]) -> StockSnapshotBatch:
        return _fetch_with_fallback(requests, self._primary, self._fallback, StockSnapshotBatch)


class IndexSnapshotProviderChain:
    def __init__(self, primary: IndexSnapshotProvider, fallback: IndexSnapshotProvider) -> None:
        self._primary = primary
        self._fallback = fallback

    def fetch_many(self, requests: Sequence[IndexSnapshotRequest]) -> IndexSnapshotBatch:
        return _fetch_with_fallback(requests, self._primary, self._fallback, IndexSnapshotBatch)


class BoardSnapshotProviderChain:
    def __init__(self, primary: BoardSnapshotProvider, fallback: BoardSnapshotProvider) -> None:
        self._primary = primary
        self._fallback = fallback

    def fetch_many(self, requests: Sequence[BoardSnapshotRequest]) -> BoardSnapshotBatch:
        return _fetch_with_fallback(requests, self._primary, self._fallback, BoardSnapshotBatch)


class _EltdxBatchFetcher:
    def __init__(
        self,
        client: Any,
        batch_size: int,
        max_workers: int,
        clock: Callable[[], datetime] | None,
    ) -> None:
        if batch_size <= 0 or batch_size > 80:
            raise ValueError("eltdx snapshot batch_size must be between 1 and 80")
        if max_workers <= 0:
            raise ValueError("max_workers must be positive")
        self._client = client
        self._batch_size = batch_size
        self._max_workers = max_workers
        self._clock = clock or _utc_now

    def fetch(
        self,
        requests: Sequence[SnapshotRequest],
        *,
        asset_kind: str,
        provider: str,
        code_formatter: Callable[[SnapshotRequest], str],
        batch_factory: type[StockSnapshotBatch] | type[IndexSnapshotBatch] | type[BoardSnapshotBatch],
    ) -> StockSnapshotBatch | IndexSnapshotBatch | BoardSnapshotBatch:
        requested = tuple(requests)
        if not requested:
            observed_at = self._clock()
            return batch_factory((), (), provider, observed_at)
        vendor_codes = [code_formatter(request) for request in requested]
        pages = [vendor_codes[index : index + self._batch_size] for index in range(0, len(vendor_codes), self._batch_size)]
        with ThreadPoolExecutor(max_workers=min(self._max_workers, len(pages))) as pool:
            raw_pages = tuple(pool.map(self._client.quotes.get_snapshots, pages))
        observed_at = self._clock()
        records = [record for page in raw_pages for record in _records(page)]
        return _normalize_batch(
            requested,
            vendor_codes,
            records,
            asset_kind=asset_kind,
            provider=provider,
            observed_at=observed_at,
            batch_factory=batch_factory,
        )


class _TQSnapshotFetcher:
    def __init__(
        self,
        client: Any,
        max_workers: int,
        clock: Callable[[], datetime] | None,
    ) -> None:
        if max_workers <= 0:
            raise ValueError("max_workers must be positive")
        self._client = client
        self._max_workers = max_workers
        self._clock = clock or _utc_now
        self._rpc_lock = _tq_rpc_lock(client)

    def fetch(
        self,
        requests: Sequence[SnapshotRequest],
        *,
        asset_kind: str,
        provider: str,
        code_formatter: Callable[[SnapshotRequest], str],
        batch_factory: type[StockSnapshotBatch] | type[IndexSnapshotBatch] | type[BoardSnapshotBatch],
    ) -> StockSnapshotBatch | IndexSnapshotBatch | BoardSnapshotBatch:
        requested = tuple(requests)
        if not requested:
            observed_at = self._clock()
            return batch_factory((), (), provider, observed_at)
        vendor_codes = [code_formatter(request) for request in requested]

        def fetch_one(vendor_code: str) -> tuple[dict[str, Any] | None, str | None]:
            try:
                with self._rpc_lock:
                    raw = self._client.get_market_snapshot(vendor_code)
                record = _single_record(raw, vendor_code)
                if record is not None:
                    record.setdefault("full_code", vendor_code)
                return record, None
            except Exception as error:  # vendor exceptions are not stable across TQ versions
                return None, f"{vendor_code}:{type(error).__name__}:{error}"

        with ThreadPoolExecutor(max_workers=min(self._max_workers, len(vendor_codes))) as pool:
            outcomes = tuple(pool.map(fetch_one, vendor_codes))
        observed_at = self._clock()
        records = [record for record, _error in outcomes if record is not None]
        errors = tuple(error for _record, error in outcomes if error is not None)
        batch = _normalize_batch(
            requested,
            vendor_codes,
            records,
            asset_kind=asset_kind,
            provider=provider,
            observed_at=observed_at,
            batch_factory=batch_factory,
        )
        return batch_factory(
            batch.rows,
            batch.missing_identity_keys,
            batch.provider,
            batch.observed_at,
            errors,
        )


def _fetch_with_fallback(
    requests: Sequence[Any],
    primary: Any,
    fallback: Any,
    batch_factory: Any,
) -> Any:
    requested = tuple(requests)
    try:
        first = primary.fetch_many(requested)
    except Exception as error:
        second = fallback.fetch_many(requested)
        return batch_factory(
            second.rows,
            second.missing_identity_keys,
            second.provider,
            second.observed_at,
            (f"primary:{type(error).__name__}:{error}", *second.errors),
        )
    if not first.missing_identity_keys:
        return first
    missing = set(first.missing_identity_keys)
    fallback_requests = tuple(request for request in requested if request.identity_key in missing)
    second = fallback.fetch_many(fallback_requests)
    by_identity = {row.identity_key: row for row in (*first.rows, *second.rows)}
    combined = tuple(by_identity[request.identity_key] for request in requested if request.identity_key in by_identity)
    still_missing = tuple(request.identity_key for request in requested if request.identity_key not in by_identity)
    return batch_factory(
        combined,
        still_missing,
        f"{first.provider}+{second.provider}",
        max(first.observed_at, second.observed_at),
        (*first.errors, *second.errors),
    )


def _tq_rpc_lock(_client: Any) -> RLock:
    """Serialize every call through TQ's process-global DLL/run_id state."""

    return _TQ_RPC_LOCK


def _normalize_batch(
    requests: Sequence[SnapshotRequest],
    vendor_codes: Sequence[str],
    records: Sequence[Mapping[str, Any]],
    *,
    asset_kind: str,
    provider: str,
    observed_at: datetime,
    batch_factory: Any,
) -> Any:
    normalized_vendor_codes = tuple(code.lower() for code in vendor_codes)
    by_vendor_code = {code: request for code, request in zip(normalized_vendor_codes, requests, strict=True)}
    bare_counts = Counter(request.code for request in requests)
    by_bare_code = {request.code: request for request in requests if bare_counts[request.code] == 1}
    rows: dict[str, RealtimeQuote] = {}
    for raw in records:
        full_code = str(_first(raw, "full_code", "symbol", "ts_code", "code") or "").lower()
        bare_code = _bare_code(full_code)
        request = by_vendor_code.get(full_code) or by_bare_code.get(bare_code)
        if request is None:
            continue
        rows[request.identity_key] = _normalize_quote(
            raw,
            request,
            asset_kind=asset_kind,
            provider=provider,
            observed_at=observed_at,
        )
    ordered_rows = tuple(rows[request.identity_key] for request in requests if request.identity_key in rows)
    missing = tuple(request.identity_key for request in requests if request.identity_key not in rows)
    return batch_factory(ordered_rows, missing, provider, observed_at)


def _normalize_quote(
    raw: Mapping[str, Any],
    request: SnapshotRequest,
    *,
    asset_kind: str,
    provider: str,
    observed_at: datetime,
) -> RealtimeQuote:
    source_time_raw = _first(raw, "source_time_raw", "time_raw", "source_time", "datetime", "time", "Time")
    source_time = (
        _datetime(
            _first(raw, "source_time", "datetime", "time", "Time", "time_raw"),
            reference=observed_at,
        )
        or observed_at
    )
    return RealtimeQuote(
        asset_kind=asset_kind,
        identity_key=request.identity_key,
        exchange=request.exchange.upper(),
        code=request.code,
        name=request.name,
        current_price=_decimal(_first(raw, "last_price", "current_price", "Now", "price", "close")),
        open=_decimal(_first(raw, "open_price", "open", "Open")),
        high=_decimal(_first(raw, "high_price", "high", "High", "Max")),
        low=_decimal(_first(raw, "low_price", "low", "Low", "Min")),
        pre_close=_decimal(_first(raw, "pre_close_price", "prev_close", "pre_close", "LastClose")),
        volume=_decimal(_first(raw, "total_hand", "volume", "Volume", "vol")),
        amount=_decimal(_first(raw, "amount", "Amount", "turnover")),
        source_time=source_time,
        observed_at=observed_at,
        provider=provider,
        source_time_raw=source_time_raw,
    )


def _validate_request(identity_key: str, asset_kind: str, exchange: str, code: str) -> None:
    if not identity_key.startswith(f"{asset_kind}:"):
        raise ValueError(f"{asset_kind} identity_key required")
    if exchange.upper() not in {"SH", "SZ", "BJ"}:
        raise ValueError(f"unsupported exchange: {exchange}")
    if len(code) != 6 or not code.isdigit():
        raise ValueError(f"six digit code required: {code}")


def _eltdx_market_code(request: SnapshotRequest) -> str:
    return f"{request.exchange.lower()}{request.code}"


def _eltdx_stock_code(request: SnapshotRequest) -> str:
    return _eltdx_market_code(request)


def _eltdx_index_code(request: SnapshotRequest) -> str:
    return _eltdx_market_code(request)


def _eltdx_board_code(request: SnapshotRequest) -> str:
    if request.code.startswith("88"):
        return f"sh{request.code}"
    return _eltdx_market_code(request)


def _tq_market_code(request: SnapshotRequest) -> str:
    return f"{request.code}.{request.exchange.upper()}"


def _tq_stock_code(request: SnapshotRequest) -> str:
    return _tq_market_code(request)


def _tq_index_code(request: SnapshotRequest) -> str:
    return _tq_market_code(request)


def _tq_board_code(request: SnapshotRequest) -> str:
    if request.code.startswith("88"):
        return f"{request.code}.SH"
    return _tq_market_code(request)


def _records(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if hasattr(value, "records"):
        value = value.records
    elif hasattr(value, "rows"):
        value = value.rows
    elif hasattr(value, "to_dict"):
        try:
            value = value.to_dict("records")
        except TypeError:
            value = value.to_dict()
    if isinstance(value, Mapping):
        value = [value]
    return [_mapping(item) for item in value]


def _single_record(value: Any, vendor_code: str) -> dict[str, Any] | None:
    if isinstance(value, Mapping) and vendor_code in value:
        value = value[vendor_code]
    rows = _records(value)
    return rows[0] if rows else None


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        result = dict(value)
    elif is_dataclass(value):
        result = asdict(value)
    elif hasattr(value, "to_dict"):
        result = dict(value.to_dict())
    elif hasattr(value, "__dict__"):
        result = {key: item for key, item in vars(value).items() if not key.startswith("_")}
    else:
        raise TypeError(f"unsupported snapshot row: {type(value).__name__}")
    return {key: (item[0] if isinstance(item, list) and item else item) for key, item in result.items()}


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _bare_code(value: str) -> str:
    text = value.lower()
    if len(text) == 8 and text[:2] in {"sh", "sz", "bj"}:
        return text[2:]
    if "." in text:
        return text.split(".", 1)[0]
    return text


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _datetime(value: Any, *, reference: datetime | None = None) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if value in (None, ""):
        return None
    text = str(value).strip().replace("Z", "+00:00")
    digits = text.removesuffix(".0") if text.endswith(".0") else text
    if digits.isdigit() and len(digits) in {5, 6} and reference is not None:
        hhmmss = digits.zfill(6)
        try:
            wall_time = datetime.strptime(hhmmss, "%H%M%S").time()
        except ValueError:
            return None
        normalized_reference = (
            reference if reference.tzinfo is not None else reference.replace(tzinfo=timezone.utc)
        )
        local_date = normalized_reference.astimezone(SHANGHAI_TIMEZONE).date()
        return datetime.combine(local_date, wall_time, tzinfo=SHANGHAI_TIMEZONE)
    if digits.isdigit() and len(digits) == 14:
        try:
            return datetime.strptime(digits, "%Y%m%d%H%M%S").replace(tzinfo=SHANGHAI_TIMEZONE)
        except ValueError:
            return None
    try:
        result = datetime.fromisoformat(text)
    except ValueError:
        return None
    return result if result.tzinfo is not None else result.replace(tzinfo=timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
