"""Windows N3 post-close compressed previous-day minute context.

The post-close writer persists one bounded context row per N2 object.  TQ is
the batch primary and every incomplete TQ identity is eligible for targeted
eltdx fallback.  Intraday code reads the completed context with a read-only
connection; raw 1m bars and realtime N3/N4 state are never stored.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
import hashlib
import importlib
import json
import os
import sys
from types import MappingProxyType
from typing import Any, Generic, Protocol, TypeVar

from ashare_v3.market.windows_n3_minute_context import (
    MINUTES_PER_DAY,
    MinuteContextBatch,
    PreviousDayMinuteContext,
    ThirtyMinuteWindow,
    build_minute_context,
    normalize_minute_bars,
)
from ashare_v3.market.windows_n3_read_model import (
    N2ObjectRuntimeInput,
    N3ActiveReadModel,
)
from ashare_v3.market.windows_n3_snapshot import (
    BoardSnapshotRequest,
    IndexSnapshotRequest,
    StockSnapshotRequest,
)


TQ_MINUTE_BATCH_SIZE = 500
TQ_MINUTE_ATTEMPTS = 3
TQ_RETRY_DELAYS_SECONDS = (30.0, 120.0)
TERMINAL_CONTEXT_STATUSES = frozenset({"ready", "partial", "unavailable", "failed"})
ASSET_KINDS = ("stock", "index", "board")


RequestT = TypeVar(
    "RequestT",
    StockSnapshotRequest,
    IndexSnapshotRequest,
    BoardSnapshotRequest,
)


@dataclass(frozen=True, slots=True)
class MinuteContextFetchBatch(Generic[RequestT]):
    contexts: Mapping[str, PreviousDayMinuteContext]
    provider_by_identity: Mapping[str, str]
    missing_identity_keys: tuple[str, ...]
    failed_batch_identity_keys: tuple[str, ...]
    errors: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "contexts", MappingProxyType(dict(self.contexts)))
        object.__setattr__(
            self,
            "provider_by_identity",
            MappingProxyType(dict(self.provider_by_identity)),
        )


class PreviousDayContextProvider(Protocol[RequestT]):
    def fetch_many(
        self,
        requests: Sequence[RequestT],
        trade_date: str,
        *,
        require_complete: bool = True,
    ) -> MinuteContextFetchBatch[RequestT]: ...


class TQStockMinuteContextProvider:
    provider_name = "tq.stock.get_market_data.1m"

    def __init__(self, client: Any, **kwargs: Any) -> None:
        self._fetcher = _TQMinuteFetcher(client, "stock", self.provider_name, **kwargs)

    def fetch_many(self, requests, trade_date, *, require_complete=True):
        return self._fetcher.fetch_many(
            requests, trade_date, require_complete=require_complete
        )


class TQIndexMinuteContextProvider:
    provider_name = "tq.index.get_market_data.1m"

    def __init__(self, client: Any, **kwargs: Any) -> None:
        self._fetcher = _TQMinuteFetcher(client, "index", self.provider_name, **kwargs)

    def fetch_many(self, requests, trade_date, *, require_complete=True):
        return self._fetcher.fetch_many(
            requests, trade_date, require_complete=require_complete
        )


class TQBoardMinuteContextProvider:
    provider_name = "tq.board.get_market_data.1m"

    def __init__(self, client: Any, **kwargs: Any) -> None:
        self._fetcher = _TQMinuteFetcher(client, "board", self.provider_name, **kwargs)

    def fetch_many(self, requests, trade_date, *, require_complete=True):
        return self._fetcher.fetch_many(
            requests, trade_date, require_complete=require_complete
        )


class UnavailableTQMinuteContextProvider(Generic[RequestT]):
    """Represent an unavailable TQ bridge so eltdx can take every request."""

    provider_name = "tq.unavailable"

    def __init__(self, error: BaseException | str) -> None:
        self.error = (
            error
            if isinstance(error, str)
            else f"{type(error).__name__}:{error}"
        )

    def fetch_many(
        self,
        requests: Sequence[RequestT],
        trade_date: str,
        *,
        require_complete: bool = True,
    ) -> MinuteContextFetchBatch[RequestT]:
        del trade_date, require_complete
        identity_keys = tuple(row.identity_key for row in requests)
        return MinuteContextFetchBatch(
            contexts={},
            provider_by_identity={},
            missing_identity_keys=identity_keys,
            failed_batch_identity_keys=identity_keys,
            errors=(f"tq_unavailable:{self.error}",),
        )


class TQWithEltdxMinuteContextProvider(Generic[RequestT]):
    """One-shot TQ primary with targeted eltdx fallback."""

    def __init__(self, tq: PreviousDayContextProvider[RequestT], eltdx: Any) -> None:
        self.tq = tq
        self.eltdx = eltdx

    def fetch_many(
        self,
        requests: Sequence[RequestT],
        trade_date: str,
        *,
        require_complete: bool = False,
    ) -> MinuteContextBatch[RequestT]:
        requested = tuple(requests)
        primary = self.tq.fetch_many(
            requested,
            trade_date,
            require_complete=require_complete,
        )
        primary_contexts = dict(primary.contexts)
        fallback_requests = tuple(
            request
            for request in requested
            if request.identity_key in primary.missing_identity_keys
        )
        errors = list(primary.errors)
        provider = "tq"
        fallback_contexts: dict[str, PreviousDayMinuteContext] = {}
        if fallback_requests:
            fallback = self.eltdx.fetch_many(
                fallback_requests,
                trade_date,
                require_complete=False,
            )
            fallback_contexts.update(fallback.contexts)
            errors.extend(fallback.errors)
            provider = "tq+eltdx"
        contexts: dict[str, PreviousDayMinuteContext] = {}
        for request in requested:
            selected, _selected_provider = _select_minute_context(
                primary_contexts.get(request.identity_key),
                fallback_contexts.get(request.identity_key),
                tq_provider="tq",
                eltdx_provider=fallback.provider if fallback_requests else "eltdx",
            )
            if selected is not None:
                contexts[request.identity_key] = selected
        missing = tuple(
            request.identity_key
            for request in requested
            if request.identity_key not in contexts
            or (
                require_complete
                and len(contexts[request.identity_key].bars) != MINUTES_PER_DAY
            )
        )
        return MinuteContextBatch(
            contexts=contexts,
            missing_identity_keys=missing,
            errors=tuple(errors),
            provider=provider,
        )


def _select_minute_context(
    tq_context: PreviousDayMinuteContext | None,
    eltdx_context: PreviousDayMinuteContext | None,
    *,
    tq_provider: str,
    eltdx_provider: str,
) -> tuple[PreviousDayMinuteContext | None, str]:
    """Choose one source without merging bars; equal partial lengths prefer TQ."""

    tq_count = len(tq_context.bars) if tq_context is not None else 0
    eltdx_count = len(eltdx_context.bars) if eltdx_context is not None else 0
    if tq_count == MINUTES_PER_DAY:
        return tq_context, tq_provider
    if eltdx_count == MINUTES_PER_DAY:
        return eltdx_context, eltdx_provider
    if eltdx_count > tq_count:
        return eltdx_context, eltdx_provider
    if tq_context is not None:
        return tq_context, tq_provider
    if eltdx_context is not None:
        return eltdx_context, eltdx_provider
    return None, "tq+eltdx.missing"


def _context_error_summary(
    identity_key: str,
    *,
    tq_minute_count: int,
    eltdx_minute_count: int,
    tq_batch_failed: bool,
    eltdx_requested: bool,
    eltdx_errors: Sequence[str],
) -> str | None:
    parts: list[str] = []
    if tq_batch_failed:
        parts.append("tq=[batch_failed]")
    elif tq_minute_count < MINUTES_PER_DAY:
        parts.append(f"tq=[incomplete:{tq_minute_count}]")
    matching_eltdx_errors = tuple(
        error for error in eltdx_errors if error.startswith(f"{identity_key}:")
    )
    if matching_eltdx_errors:
        parts.append("eltdx=[" + " | ".join(matching_eltdx_errors) + "]")
    elif eltdx_requested and eltdx_minute_count == 0:
        parts.append("eltdx=[missing]")
    return "; ".join(parts) or None


class _TQMinuteFetcher:
    def __init__(
        self,
        client: Any,
        asset_kind: str,
        provider_name: str,
        *,
        batch_size: int = TQ_MINUTE_BATCH_SIZE,
        sleep: Callable[[float], None] | None = None,
        retry_delays: Sequence[float] = TQ_RETRY_DELAYS_SECONDS,
    ) -> None:
        if batch_size <= 0 or batch_size > TQ_MINUTE_BATCH_SIZE:
            raise ValueError("TQ minute batch_size must be between 1 and 500")
        if len(tuple(retry_delays)) != TQ_MINUTE_ATTEMPTS - 1:
            raise ValueError("TQ retry_delays must contain exactly two delays")
        self.client = client
        self.asset_kind = asset_kind
        self.provider_name = provider_name
        self.batch_size = batch_size
        if sleep is None:
            from time import sleep as system_sleep

            self.sleep = system_sleep
        else:
            self.sleep = sleep
        self.retry_delays = tuple(float(value) for value in retry_delays)

    def fetch_many(
        self,
        requests: Sequence[RequestT],
        trade_date: str,
        *,
        require_complete: bool = True,
    ) -> MinuteContextFetchBatch[RequestT]:
        requested = tuple(requests)
        contexts: dict[str, PreviousDayMinuteContext] = {}
        providers: dict[str, str] = {}
        failed_batch_keys: list[str] = []
        errors: list[str] = []
        for offset in range(0, len(requested), self.batch_size):
            batch = requested[offset : offset + self.batch_size]
            outcome = self._fetch_batch(
                batch,
                trade_date,
                require_complete=require_complete,
            )
            if outcome is None:
                failed_batch_keys.extend(row.identity_key for row in batch)
                errors.append(
                    f"{self.asset_kind}:tq_batch_failed:offset={offset}:count={len(batch)}"
                )
                continue
            rows_by_code, batch_errors = outcome
            errors.extend(batch_errors)
            for request in batch:
                rows = rows_by_code.get(_tq_vendor_code(request), ())
                bars = normalize_minute_bars(request.identity_key, trade_date, rows)
                if not bars:
                    continue
                contexts[request.identity_key] = build_minute_context(
                    request.identity_key,
                    trade_date,
                    bars,
                )
                providers[request.identity_key] = self.provider_name
        missing = tuple(
            row.identity_key
            for row in requested
            if row.identity_key not in contexts
            or (require_complete and len(contexts[row.identity_key].bars) != MINUTES_PER_DAY)
        )
        return MinuteContextFetchBatch(
            contexts=contexts,
            provider_by_identity=providers,
            missing_identity_keys=missing,
            failed_batch_identity_keys=tuple(failed_batch_keys),
            errors=tuple(errors),
        )

    def _fetch_batch(
        self,
        requests: Sequence[RequestT],
        trade_date: str,
        *,
        require_complete: bool,
    ) -> tuple[Mapping[str, Sequence[Any]], tuple[str, ...]] | None:
        vendor_codes = tuple(_tq_vendor_code(row) for row in requests)
        errors: list[str] = []
        last_rows_by_code: Mapping[str, Sequence[Any]] | None = None
        for attempt in range(TQ_MINUTE_ATTEMPTS):
            try:
                raw = self.client.get_market_data(
                    field_list=[],
                    stock_list=list(vendor_codes),
                    period="1m",
                    start_time=f"{trade_date}093000",
                    end_time=f"{trade_date}150000",
                    count=-1,
                    dividend_type="none",
                    fill_data=False,
                )
                rows_by_code = _tq_rows_by_code(raw, vendor_codes)
                if not rows_by_code:
                    raise RuntimeError("empty TQ minute batch")
                last_rows_by_code = rows_by_code
                incomplete = tuple(
                    request.identity_key
                    for request in requests
                    if len(
                        normalize_minute_bars(
                            request.identity_key,
                            trade_date,
                            rows_by_code.get(_tq_vendor_code(request), ()),
                        )
                    )
                    != MINUTES_PER_DAY
                )
                if (
                    not require_complete
                    or not incomplete
                    or attempt == TQ_MINUTE_ATTEMPTS - 1
                ):
                    return rows_by_code, tuple(errors)
                errors.append(
                    f"attempt={attempt + 1}:incomplete_count={len(incomplete)}"
                )
            except Exception as error:  # TQ exception types vary by terminal build
                errors.append(
                    f"attempt={attempt + 1}:{type(error).__name__}:{error}"
                )
                if attempt < TQ_MINUTE_ATTEMPTS - 1:
                    self.sleep(self.retry_delays[attempt])
                    continue
            if attempt < TQ_MINUTE_ATTEMPTS - 1:
                self.sleep(self.retry_delays[attempt])
        return None if last_rows_by_code is None else (last_rows_by_code, tuple(errors))


@dataclass(frozen=True, slots=True)
class ContextRecord:
    asset_kind: str
    identity_key: str
    exchange: str
    code: str
    name: str
    basis_trade_date: str | None
    provider: str
    status: str
    minute_count: int
    tq_minute_count: int
    eltdx_minute_count: int
    cumulative_amounts: tuple[Decimal, ...]
    windows: tuple[Mapping[str, Any], ...]
    content_sha256: str
    error_summary: str | None = None

    def __post_init__(self) -> None:
        if self.asset_kind not in ASSET_KINDS:
            raise ValueError(f"unsupported asset_kind: {self.asset_kind}")
        if self.status not in TERMINAL_CONTEXT_STATUSES:
            raise ValueError(f"unsupported context status: {self.status}")
        if not self.identity_key.startswith(f"{self.asset_kind}:"):
            raise ValueError("identity_key does not match asset_kind")
        if not 0 <= self.tq_minute_count <= MINUTES_PER_DAY:
            raise ValueError("tq_minute_count must be between 0 and 240")
        if not 0 <= self.eltdx_minute_count <= MINUTES_PER_DAY:
            raise ValueError("eltdx_minute_count must be between 0 and 240")
        if self.status == "ready":
            if self.minute_count != 240 or len(self.cumulative_amounts) != 240 or len(self.windows) != 8:
                raise ValueError("ready context requires 240 points and 8 windows")
        elif self.status == "partial":
            if not 1 <= self.minute_count <= 239:
                raise ValueError("partial context requires 1..239 minute points")
            if len(self.cumulative_amounts) != self.minute_count:
                raise ValueError("partial cumulative points must match minute_count")
        elif self.minute_count != 0 or self.cumulative_amounts or self.windows:
            raise ValueError("unavailable/failed contexts must not contain minute data")
        object.__setattr__(self, "windows", tuple(MappingProxyType(dict(row)) for row in self.windows))


@dataclass(frozen=True, slots=True)
class PreviousDayContextLoad:
    context_run_id: str
    source_condition_run_id: str
    source_trade_date: str
    for_trade_date: str
    stock: Mapping[str, PreviousDayMinuteContext]
    index: Mapping[str, PreviousDayMinuteContext]
    board: Mapping[str, PreviousDayMinuteContext]
    status_counts: Mapping[str, Mapping[str, int]]

    def __post_init__(self) -> None:
        for name in ASSET_KINDS:
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))
        object.__setattr__(
            self,
            "status_counts",
            MappingProxyType(
                {key: MappingProxyType(dict(value)) for key, value in self.status_counts.items()}
            ),
        )


@dataclass(frozen=True, slots=True)
class PreviousDayContextPreloadSummary:
    result: str
    context_run_id: str
    source_condition_run_id: str
    source_trade_date: str
    for_trade_date: str
    expected_counts: Mapping[str, int]
    terminal_counts: Mapping[str, int]
    status_counts: Mapping[str, Mapping[str, int]]
    inserted_count: int


class PreviousDayContextWriteRepository(Protocol):
    def begin_run(self, model: N3ActiveReadModel) -> tuple[str, bool]: ...

    def terminal_identity_keys(self, context_run_id: str, asset_kind: str) -> set[str]: ...

    def save_records(
        self,
        context_run_id: str,
        model: N3ActiveReadModel,
        records: Sequence[ContextRecord],
    ) -> int: ...

    def complete_run(
        self,
        context_run_id: str,
        model: N3ActiveReadModel,
    ) -> PreviousDayContextPreloadSummary: ...


class PreviousDayContextLoader(Protocol):
    def load(self, model: N3ActiveReadModel) -> PreviousDayContextLoad: ...


class WindowsN3PreviousDayContextPreloader:
    def __init__(
        self,
        *,
        repository: PreviousDayContextWriteRepository,
        tq_stock: PreviousDayContextProvider[StockSnapshotRequest],
        tq_index: PreviousDayContextProvider[IndexSnapshotRequest],
        tq_board: PreviousDayContextProvider[BoardSnapshotRequest],
        eltdx_stock: Any,
        eltdx_index: Any,
        eltdx_board: Any,
    ) -> None:
        self.repository = repository
        self.primary = {"stock": tq_stock, "index": tq_index, "board": tq_board}
        self.fallback = {
            "stock": eltdx_stock,
            "index": eltdx_index,
            "board": eltdx_board,
        }

    def execute(self, model: N3ActiveReadModel) -> PreviousDayContextPreloadSummary:
        context_run_id, already_complete = self.repository.begin_run(model)
        if already_complete:
            summary = self.repository.complete_run(context_run_id, model)
            return PreviousDayContextPreloadSummary(
                result="N3_PREVIOUS_DAY_CONTEXT_SKIPPED_COMPLETE",
                context_run_id=summary.context_run_id,
                source_condition_run_id=summary.source_condition_run_id,
                source_trade_date=summary.source_trade_date,
                for_trade_date=summary.for_trade_date,
                expected_counts=summary.expected_counts,
                terminal_counts=summary.terminal_counts,
                status_counts=summary.status_counts,
                inserted_count=0,
            )

        inserted = 0
        for asset_kind in ASSET_KINDS:
            rows = tuple(getattr(model, asset_kind))
            requests = _requests(model, asset_kind)
            by_identity = {row.identity_key: row for row in rows}
            terminal = self.repository.terminal_identity_keys(context_run_id, asset_kind)
            pending_requests = tuple(
                request for request in requests if request.identity_key not in terminal
            )
            records: list[ContextRecord] = []
            eligible: list[RequestT] = []
            for request in pending_requests:
                row = by_identity[request.identity_key]
                if row.basis_trade_date and row.basis_trade_date > model.source_trade_date:
                    raise ValueError(
                        f"N2 basis_trade_date is in the future: {request.identity_key}"
                    )
                if row.basis_trade_date and row.basis_trade_date < model.source_trade_date:
                    records.append(
                        make_context_record(
                            row,
                            provider="n2.stale_basis",
                            status="unavailable",
                            context=None,
                            error_summary=None,
                        )
                    )
                else:
                    eligible.append(request)

            primary = self.primary[asset_kind].fetch_many(
                eligible,
                model.source_trade_date,
            )
            primary_contexts = dict(primary.contexts)
            failed_batches = set(primary.failed_batch_identity_keys)
            fallback_requests = tuple(
                request
                for request in eligible
                if request.identity_key in primary.missing_identity_keys
            )
            fallback_errors: tuple[str, ...] = ()
            fallback_identity_keys = {
                request.identity_key for request in fallback_requests
            }
            fallback_contexts: dict[str, PreviousDayMinuteContext] = {}
            fallback_provider = "eltdx"
            if fallback_requests:
                fallback_batch = self.fallback[asset_kind].fetch_many(
                    fallback_requests,
                    model.source_trade_date,
                    require_complete=False,
                )
                fallback_contexts.update(fallback_batch.contexts)
                fallback_provider = fallback_batch.provider
                fallback_errors = fallback_batch.errors

            for request in eligible:
                row = by_identity[request.identity_key]
                tq_context = primary_contexts.get(request.identity_key)
                eltdx_context = fallback_contexts.get(request.identity_key)
                context, provider = _select_minute_context(
                    tq_context,
                    eltdx_context,
                    tq_provider=primary.provider_by_identity.get(
                        request.identity_key,
                        "tq",
                    ),
                    eltdx_provider=fallback_provider,
                )
                tq_minute_count = len(tq_context.bars) if tq_context is not None else 0
                eltdx_minute_count = (
                    len(eltdx_context.bars) if eltdx_context is not None else 0
                )
                error_text = _context_error_summary(
                    request.identity_key,
                    tq_minute_count=tq_minute_count,
                    eltdx_minute_count=eltdx_minute_count,
                    tq_batch_failed=request.identity_key in failed_batches,
                    eltdx_requested=request.identity_key in fallback_identity_keys,
                    eltdx_errors=fallback_errors,
                )
                if context is None:
                    records.append(
                        make_context_record(
                            row,
                            provider="tq+eltdx.missing",
                            status="failed",
                            context=None,
                            error_summary=error_text,
                            tq_minute_count=tq_minute_count,
                            eltdx_minute_count=eltdx_minute_count,
                        )
                    )
                    continue
                records.append(
                    make_context_record(
                        row,
                        provider=provider,
                        status=("ready" if len(context.bars) == MINUTES_PER_DAY else "partial"),
                        context=context,
                        error_summary=error_text,
                        tq_minute_count=tq_minute_count,
                        eltdx_minute_count=eltdx_minute_count,
                    )
                )
            inserted += self.repository.save_records(
                context_run_id,
                model,
                records,
            )
        summary = self.repository.complete_run(context_run_id, model)
        return PreviousDayContextPreloadSummary(
            result="N3_PREVIOUS_DAY_CONTEXT_COMPLETE",
            context_run_id=summary.context_run_id,
            source_condition_run_id=summary.source_condition_run_id,
            source_trade_date=summary.source_trade_date,
            for_trade_date=summary.for_trade_date,
            expected_counts=summary.expected_counts,
            terminal_counts=summary.terminal_counts,
            status_counts=summary.status_counts,
            inserted_count=inserted,
        )


class PostgresPreviousDayContextRepository:
    def __init__(self, dsn: str, *, connect: Callable[[str], Any] | None = None) -> None:
        self.dsn = dsn
        self._connect = connect or _connect_write

    def begin_run(self, model: N3ActiveReadModel) -> tuple[str, bool]:
        context_run_id = context_run_id_for(model.run_id)
        expected = _expected_counts(model)
        with self._connect(self.dsn) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT context_run_id, source_condition_run_id,
                       source_trade_date, for_trade_date,
                       status, expected_stock_count, expected_index_count,
                       expected_board_count
                FROM common_n3_previous_day_context_run
                WHERE source_condition_run_id = %s
                FOR UPDATE
                """,
                (model.run_id,),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    """
                    INSERT INTO common_n3_previous_day_context_run (
                      context_run_id, source_condition_run_id,
                      source_trade_date, for_trade_date,
                      expected_stock_count, expected_index_count, expected_board_count
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        context_run_id,
                        model.run_id,
                        model.source_trade_date,
                        model.for_trade_date,
                        expected["stock"],
                        expected["index"],
                        expected["board"],
                    ),
                )
                return context_run_id, False
            values = _row_values(row)
            actual_context_run_id = str(values[0])
            actual = (
                str(values[1]),
                str(values[2]),
                str(values[3]),
                int(values[5]),
                int(values[6]),
                int(values[7]),
            )
            required = (
                model.run_id,
                model.source_trade_date,
                model.for_trade_date,
                expected["stock"],
                expected["index"],
                expected["board"],
            )
            if actual_context_run_id != context_run_id or actual != required:
                raise RuntimeError("existing N3 context run lineage/count mismatch")
            if str(values[4]) != "completed":
                return context_run_id, False
            cursor.execute(
                """
                SELECT EXISTS (
                  SELECT 1 FROM stock_n3_previous_day_context
                  WHERE context_run_id = %s AND status = 'failed'
                  UNION ALL
                  SELECT 1 FROM index_n3_previous_day_context
                  WHERE context_run_id = %s AND status = 'failed'
                  UNION ALL
                  SELECT 1 FROM board_n3_previous_day_context
                  WHERE context_run_id = %s AND status = 'failed'
                )
                """,
                (context_run_id, context_run_id, context_run_id),
            )
            has_failed = bool(_row_values(cursor.fetchone())[0])
            if not has_failed:
                return context_run_id, True
            cursor.execute(
                """
                UPDATE common_n3_previous_day_context_run
                SET status='running',
                    terminal_stock_count=0,
                    terminal_index_count=0,
                    terminal_board_count=0,
                    result_summary='{}'::JSONB,
                    finished_at=NULL,
                    updated_at=now()
                WHERE context_run_id=%s
                """,
                (context_run_id,),
            )
            return context_run_id, False

    def terminal_identity_keys(self, context_run_id: str, asset_kind: str) -> set[str]:
        table, identity_column = _asset_table(asset_kind)
        with self._connect(self.dsn) as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {identity_column} FROM {table} "
                "WHERE context_run_id = %s AND status <> 'failed'",
                (context_run_id,),
            )
            return {str(_row_values(row)[0]) for row in cursor.fetchall()}

    def save_records(
        self,
        context_run_id: str,
        model: N3ActiveReadModel,
        records: Sequence[ContextRecord],
    ) -> int:
        values = tuple(records)
        if not values:
            return 0
        asset_kind = values[0].asset_kind
        if any(row.asset_kind != asset_kind for row in values):
            raise ValueError("save_records accepts one asset kind per call")
        table, identity_column = _asset_table(asset_kind)
        query = f"""
            INSERT INTO {table} (
              context_run_id, source_condition_run_id,
              source_trade_date, for_trade_date,
              {identity_column}, exchange, code, name, basis_trade_date,
              provider, status, minute_count, tq_minute_count,
              eltdx_minute_count, cumulative_amounts,
              windows_json, content_sha256, error_summary
            ) VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s, %s, %s::JSONB, %s, %s
            )
            ON CONFLICT (context_run_id, {identity_column}) DO UPDATE SET
              exchange=EXCLUDED.exchange,
              code=EXCLUDED.code,
              name=EXCLUDED.name,
              basis_trade_date=EXCLUDED.basis_trade_date,
              provider=EXCLUDED.provider,
              status=EXCLUDED.status,
              minute_count=EXCLUDED.minute_count,
              tq_minute_count=EXCLUDED.tq_minute_count,
              eltdx_minute_count=EXCLUDED.eltdx_minute_count,
              cumulative_amounts=EXCLUDED.cumulative_amounts,
              windows_json=EXCLUDED.windows_json,
              content_sha256=EXCLUDED.content_sha256,
              error_summary=EXCLUDED.error_summary,
              updated_at=now()
            WHERE {table}.status = 'failed'
        """
        params = [
            (
                context_run_id,
                model.run_id,
                model.source_trade_date,
                model.for_trade_date,
                row.identity_key,
                row.exchange,
                row.code,
                row.name,
                row.basis_trade_date,
                row.provider,
                row.status,
                row.minute_count,
                row.tq_minute_count,
                row.eltdx_minute_count,
                list(row.cumulative_amounts),
                json.dumps(
                    [dict(value) for value in row.windows],
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                row.content_sha256,
                row.error_summary,
            )
            for row in values
        ]
        with self._connect(self.dsn) as connection, connection.cursor() as cursor:
            cursor.executemany(query, params)
            inserted_count = max(int(cursor.rowcount), 0)
        return inserted_count

    def complete_run(
        self,
        context_run_id: str,
        model: N3ActiveReadModel,
    ) -> PreviousDayContextPreloadSummary:
        expected = _expected_counts(model)
        terminal: dict[str, int] = {}
        status_counts: dict[str, dict[str, int]] = {}
        with self._connect(self.dsn) as connection, connection.cursor() as cursor:
            for asset_kind in ASSET_KINDS:
                table, _identity_column = _asset_table(asset_kind)
                cursor.execute(
                    f"SELECT status, count(*) FROM {table} "
                    "WHERE context_run_id = %s GROUP BY status",
                    (context_run_id,),
                )
                counts = {
                    str(_row_values(row)[0]): int(_row_values(row)[1])
                    for row in cursor.fetchall()
                }
                status_counts[asset_kind] = counts
                terminal[asset_kind] = sum(counts.values())
                if terminal[asset_kind] != expected[asset_kind]:
                    raise RuntimeError(
                        f"N3 context terminal count mismatch for {asset_kind}: "
                        f"{terminal[asset_kind]} != {expected[asset_kind]}"
                    )
                usable_count = counts.get("ready", 0) + counts.get("partial", 0)
                if expected[asset_kind] > 0 and usable_count == 0:
                    raise RuntimeError(
                        f"N3 context has no usable rows for {asset_kind}"
                    )
            summary_json = json.dumps(status_counts, ensure_ascii=False, sort_keys=True)
            cursor.execute(
                """
                UPDATE common_n3_previous_day_context_run
                SET status='completed',
                    terminal_stock_count=%s,
                    terminal_index_count=%s,
                    terminal_board_count=%s,
                    result_summary=%s::JSONB,
                    finished_at=COALESCE(finished_at, now()),
                    updated_at=now()
                WHERE context_run_id=%s
                  AND source_condition_run_id=%s
                  AND source_trade_date=%s
                  AND for_trade_date=%s
                """,
                (
                    terminal["stock"],
                    terminal["index"],
                    terminal["board"],
                    summary_json,
                    context_run_id,
                    model.run_id,
                    model.source_trade_date,
                    model.for_trade_date,
                ),
            )
        return PreviousDayContextPreloadSummary(
            result="N3_PREVIOUS_DAY_CONTEXT_COMPLETE",
            context_run_id=context_run_id,
            source_condition_run_id=model.run_id,
            source_trade_date=model.source_trade_date,
            for_trade_date=model.for_trade_date,
            expected_counts=MappingProxyType(expected),
            terminal_counts=MappingProxyType(terminal),
            status_counts=MappingProxyType(
                {key: MappingProxyType(value) for key, value in status_counts.items()}
            ),
            inserted_count=0,
        )


class PostgresPreviousDayContextLoader:
    def __init__(self, dsn: str, *, connect: Callable[[str], Any] | None = None) -> None:
        self.dsn = dsn
        self._connect = connect or _connect_read_only

    def load(self, model: N3ActiveReadModel) -> PreviousDayContextLoad:
        with self._connect(self.dsn) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT context_run_id, source_condition_run_id,
                       source_trade_date, for_trade_date
                FROM common_n3_previous_day_context_run
                WHERE source_condition_run_id=%s
                  AND source_trade_date=%s
                  AND for_trade_date=%s
                  AND status='completed'
                """,
                (model.run_id, model.source_trade_date, model.for_trade_date),
            )
            run = cursor.fetchone()
            if run is None:
                raise RuntimeError("completed N3 previous-day context is unavailable")
            run_values = _row_values(run)
            context_run_id = str(run_values[0])
            if (
                str(run_values[1]),
                str(run_values[2]),
                str(run_values[3]),
            ) != (model.run_id, model.source_trade_date, model.for_trade_date):
                raise RuntimeError("completed N3 context lineage mismatch")
            contexts: dict[str, dict[str, PreviousDayMinuteContext]] = {}
            status_counts: dict[str, dict[str, int]] = {}
            for asset_kind in ASSET_KINDS:
                table, identity_column = _asset_table(asset_kind)
                cursor.execute(
                    f"""
                    SELECT {identity_column}, exchange, code, name,
                           basis_trade_date, provider, status, minute_count,
                           tq_minute_count, eltdx_minute_count,
                           cumulative_amounts, windows_json,
                           content_sha256, error_summary
                    FROM {table}
                    WHERE context_run_id=%s
                      AND source_condition_run_id=%s
                      AND source_trade_date=%s
                      AND for_trade_date=%s
                    ORDER BY {identity_column}
                    """,
                    (
                        context_run_id,
                        model.run_id,
                        model.source_trade_date,
                        model.for_trade_date,
                    ),
                )
                rows = cursor.fetchall()
                expected_keys = {row.identity_key for row in getattr(model, asset_kind)}
                actual_keys = {str(_row_values(row)[0]) for row in rows}
                if actual_keys != expected_keys:
                    raise RuntimeError(
                        f"N3 context identity mismatch for {asset_kind}: "
                        f"expected={len(expected_keys)} actual={len(actual_keys)}"
                    )
                ready: dict[str, PreviousDayMinuteContext] = {}
                counts: dict[str, int] = {}
                for row in rows:
                    values = _row_values(row)
                    record = ContextRecord(
                        asset_kind=asset_kind,
                        identity_key=str(values[0]),
                        exchange=str(values[1]),
                        code=str(values[2]),
                        name=str(values[3]),
                        basis_trade_date=None if values[4] is None else str(values[4]),
                        provider=str(values[5]),
                        status=str(values[6]),
                        minute_count=int(values[7]),
                        tq_minute_count=int(values[8]),
                        eltdx_minute_count=int(values[9]),
                        cumulative_amounts=tuple(Decimal(str(value)) for value in (values[10] or ())),
                        windows=tuple(_json_array(values[11])),
                        content_sha256=str(values[12]),
                        error_summary=None if values[13] is None else str(values[13]),
                    )
                    if record.content_sha256 != context_record_sha256(record):
                        raise RuntimeError(f"N3 context SHA mismatch: {record.identity_key}")
                    counts[record.status] = counts.get(record.status, 0) + 1
                    if record.status == "ready":
                        ready[record.identity_key] = context_from_record(
                            record,
                            model.source_trade_date,
                        )
                contexts[asset_kind] = ready
                status_counts[asset_kind] = counts
        return PreviousDayContextLoad(
            context_run_id=context_run_id,
            source_condition_run_id=model.run_id,
            source_trade_date=model.source_trade_date,
            for_trade_date=model.for_trade_date,
            stock=contexts["stock"],
            index=contexts["index"],
            board=contexts["board"],
            status_counts=status_counts,
        )


def make_context_record(
    row: N2ObjectRuntimeInput,
    *,
    provider: str,
    status: str,
    context: PreviousDayMinuteContext | None,
    error_summary: str | None,
    tq_minute_count: int = 0,
    eltdx_minute_count: int = 0,
) -> ContextRecord:
    cumulative = tuple(context.cumulative_day_amounts) if context is not None else ()
    windows = tuple(_window_payload(window) for window in (context.windows if context is not None else ()))
    draft = ContextRecord(
        asset_kind=row.asset_kind,
        identity_key=row.identity_key,
        exchange=row.exchange,
        code=row.code,
        name=row.name,
        basis_trade_date=row.basis_trade_date,
        provider=provider,
        status=status,
        minute_count=len(context.bars) if context is not None else 0,
        tq_minute_count=tq_minute_count,
        eltdx_minute_count=eltdx_minute_count,
        cumulative_amounts=cumulative,
        windows=windows,
        content_sha256="0" * 64,
        error_summary=error_summary,
    )
    return ContextRecord(
        asset_kind=draft.asset_kind,
        identity_key=draft.identity_key,
        exchange=draft.exchange,
        code=draft.code,
        name=draft.name,
        basis_trade_date=draft.basis_trade_date,
        provider=draft.provider,
        status=draft.status,
        minute_count=draft.minute_count,
        tq_minute_count=draft.tq_minute_count,
        eltdx_minute_count=draft.eltdx_minute_count,
        cumulative_amounts=draft.cumulative_amounts,
        windows=draft.windows,
        content_sha256=context_record_sha256(draft),
        error_summary=draft.error_summary,
    )


def context_record_sha256(record: ContextRecord) -> str:
    payload = {
        "asset_kind": record.asset_kind,
        "identity_key": record.identity_key,
        "exchange": record.exchange,
        "code": record.code,
        "name": record.name,
        "basis_trade_date": record.basis_trade_date,
        "provider": record.provider,
        "status": record.status,
        "minute_count": record.minute_count,
        "tq_minute_count": record.tq_minute_count,
        "eltdx_minute_count": record.eltdx_minute_count,
        "cumulative_amounts": [str(value) for value in record.cumulative_amounts],
        "windows": [dict(value) for value in record.windows],
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def context_from_record(
    record: ContextRecord,
    source_trade_date: str,
) -> PreviousDayMinuteContext:
    windows = tuple(
        ThirtyMinuteWindow(
            bucket_index=int(row["bucket_index"]),
            bars=(),
            cumulative_amounts=tuple(Decimal(str(value)) for value in row["cumulative_amounts"]),
            full_amount=Decimal(str(row["full_amount"])),
            open=Decimal(str(row["open"])),
            high=Decimal(str(row["high"])),
            low=Decimal(str(row["low"])),
            close=Decimal(str(row["close"])),
        )
        for row in record.windows
    )
    return PreviousDayMinuteContext(
        identity_key=record.identity_key,
        source_trade_date=source_trade_date,
        bars=(),
        cumulative_day_amounts=record.cumulative_amounts,
        windows=windows,
    )


def context_run_id_for(source_condition_run_id: str) -> str:
    digest = hashlib.sha256(source_condition_run_id.encode("utf-8")).hexdigest()[:24]
    return f"windows_n3_previous_day_context_{digest}"


def load_windows_tq_client(module_path: str | None = None) -> Any:
    """Load the already-installed TQ terminal bridge without reading secrets."""

    resolved_path = module_path or os.environ.get(
        "ASHARE_V3_TQCENTER_PATH",
        r"C:\new_tdx64\PYPlugins\sys",
    )
    if resolved_path and resolved_path not in sys.path:
        sys.path.insert(0, resolved_path)
    module = importlib.import_module("tqcenter")
    candidates = (
        module,
        getattr(module, "tq", None),
        getattr(module, "client", None),
    )
    for candidate in candidates:
        if candidate is not None and callable(getattr(candidate, "get_market_data", None)):
            return candidate
    raise RuntimeError("tqcenter does not expose get_market_data")


def _window_payload(window: ThirtyMinuteWindow) -> Mapping[str, Any]:
    return {
        "bucket_index": window.bucket_index,
        "cumulative_amounts": [str(value) for value in window.cumulative_amounts],
        "full_amount": str(window.full_amount),
        "open": str(window.open),
        "high": str(window.high),
        "low": str(window.low),
        "close": str(window.close),
        "entity_high": str(window.entity_high),
        "entity_low": str(window.entity_low),
    }


def _expected_counts(model: N3ActiveReadModel) -> dict[str, int]:
    return {asset_kind: len(getattr(model, asset_kind)) for asset_kind in ASSET_KINDS}


def _requests(model: N3ActiveReadModel, asset_kind: str) -> tuple[Any, ...]:
    return getattr(model, f"{asset_kind}_requests")()


def _asset_table(asset_kind: str) -> tuple[str, str]:
    if asset_kind not in ASSET_KINDS:
        raise ValueError(f"unsupported asset_kind: {asset_kind}")
    return (
        f"{asset_kind}_n3_previous_day_context",
        f"{asset_kind}_identity_key",
    )


def _tq_vendor_code(request: RequestT) -> str:
    exchange = "SH" if request.identity_key.startswith("board:") and request.code.startswith("88") else request.exchange.upper()
    return f"{request.code}.{exchange}"


def _tq_rows_by_code(
    raw: Any,
    vendor_codes: Sequence[str],
) -> Mapping[str, Sequence[Any]]:
    normalized = {code.upper(): code for code in vendor_codes}
    if isinstance(raw, Mapping):
        direct: dict[str, Sequence[Any]] = {}
        for key, value in raw.items():
            code = _match_vendor_code(str(key), normalized)
            if code is not None:
                direct[code] = _table_records(value)
        if direct:
            return MappingProxyType(direct)
        matrix = _field_matrix_records(raw, vendor_codes)
        if matrix:
            return MappingProxyType(matrix)
    records = _table_records(raw)
    by_code: dict[str, list[Any]] = {}
    for row in records:
        code_value = _first(row, "stock_code", "full_code", "code", "symbol")
        code = _match_vendor_code(str(code_value or ""), normalized)
        if code is not None:
            by_code.setdefault(code, []).append(row)
    return MappingProxyType(by_code)


def _field_matrix_records(
    fields: Mapping[Any, Any],
    vendor_codes: Sequence[str],
) -> dict[str, Sequence[Any]]:
    result: dict[str, Sequence[Any]] = {}
    for vendor_code in vendor_codes:
        rows_by_time: dict[str, dict[str, Any]] = {}
        for field_name, matrix in fields.items():
            series = _matrix_series(matrix, vendor_code)
            for label, value in series:
                key = str(label)
                row = rows_by_time.setdefault(key, {"time": label})
                row[str(field_name)] = value
        if rows_by_time:
            result[vendor_code] = tuple(rows_by_time[key] for key in sorted(rows_by_time))
    return result


def _matrix_series(matrix: Any, vendor_code: str) -> tuple[tuple[Any, Any], ...]:
    candidate: Any = None
    keys = (vendor_code, vendor_code.upper(), vendor_code.lower(), vendor_code.split(".", 1)[0])
    if isinstance(matrix, Mapping):
        for key in keys:
            if key in matrix:
                candidate = matrix[key]
                break
    if candidate is None and hasattr(matrix, "columns"):
        columns = set(str(value) for value in matrix.columns)
        for key in keys:
            if key in columns:
                candidate = matrix[key]
                break
    if candidate is None and hasattr(matrix, "loc"):
        for key in keys:
            try:
                candidate = matrix.loc[key]
                break
            except Exception:
                continue
    if candidate is None:
        return ()
    if isinstance(candidate, Mapping):
        return tuple(candidate.items())
    if hasattr(candidate, "items"):
        return tuple(candidate.items())
    if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes)):
        return tuple(enumerate(candidate))
    return ()


def _table_records(value: Any) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        if value and all(isinstance(item, Mapping) for item in value.values()):
            return tuple(dict(item, time=key) for key, item in value.items())
        return (dict(value),)
    if hasattr(value, "iterrows"):
        return tuple(
            dict(dict(row), time=index)
            for index, row in value.iterrows()
        )
    if hasattr(value, "to_dict"):
        try:
            records = value.to_dict("records")
        except TypeError:
            records = value.to_dict()
        return _table_records(records)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        rows: list[Mapping[str, Any]] = []
        for row in value:
            if isinstance(row, Mapping):
                rows.append(dict(row))
            elif hasattr(row, "__dict__"):
                rows.append(
                    {key: item for key, item in vars(row).items() if not key.startswith("_")}
                )
        return tuple(rows)
    return ()


def _match_vendor_code(value: str, normalized: Mapping[str, str]) -> str | None:
    text = value.strip().upper()
    if text in normalized:
        return normalized[text]
    if len(text) == 8 and text[:2] in {"SH", "SZ", "BJ"}:
        text = f"{text[2:]}.{text[:2]}"
    for key, original in normalized.items():
        if text == key or text == key.split(".", 1)[0]:
            return original
    return None


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if row.get(key) not in (None, ""):
            return row[key]
    return None


def _json_array(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list):
        raise ValueError("windows_json must be an array")
    return [dict(row) for row in value]


def _row_values(row: Any) -> tuple[Any, ...]:
    if isinstance(row, Mapping):
        return tuple(row.values())
    return tuple(row)


def _connect_write(dsn: str) -> Any:
    import psycopg

    return psycopg.connect(dsn)


def _connect_read_only(dsn: str) -> Any:
    import psycopg

    return psycopg.connect(
        dsn,
        options="-c default_transaction_read_only=on",
    )
