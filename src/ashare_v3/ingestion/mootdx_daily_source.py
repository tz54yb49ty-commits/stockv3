"""Mootdx raw source adapter for index and board daily bars."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import importlib
from typing import Any

from ashare_v3.ingestion.common import IngestionValidationError, require_yyyymmdd
from ashare_v3.ingestion.daily_bars import BoardDailySymbol, IndexDailySymbol, parse_trade_date


class MootdxDailyBarSourceError(IngestionValidationError):
    """Raised when Mootdx daily bar source configuration is invalid."""


class MootdxDailyBarSource:
    """Fetch raw daily bars using Mootdx `index` endpoint.

    The source only returns raw rows enriched with v3 metadata. It does not
    connect to PostgreSQL, write files, or activate source versions.
    """

    def __init__(
        self,
        *,
        client: Any | None = None,
        market: str = "std",
        frequency: int = 9,
        start: int = 0,
        offset: int = 800,
    ) -> None:
        self.market = market
        self.frequency = frequency
        self.start = start
        self.offset = offset
        self._client = client
        if self._client is None:
            quotes_module = importlib.import_module("mootdx.quotes")
            self._client = quotes_module.Quotes.factory(market=market)

    def fetch_index_daily_bars(
        self,
        *,
        indexes: Sequence[IndexDailySymbol],
        start_date: str,
        end_date: str,
    ) -> Sequence[Mapping[str, Any]]:
        require_yyyymmdd(start_date, "start_date")
        require_yyyymmdd(end_date, "end_date")
        rows: list[dict[str, Any]] = []
        for symbol in indexes:
            frame = self._client.index(
                symbol=symbol.code,
                frequency=self.frequency,
                start=self.start,
                offset=self.offset,
            )
            rows.extend(
                _enrich_and_filter_records(
                    frame,
                    start_date=start_date,
                    end_date=end_date,
                    extra={
                        "code": symbol.code,
                        "exchange": symbol.exchange,
                        "name": symbol.name,
                        "source_symbol": symbol.code,
                    },
                )
            )
        return rows

    def fetch_board_daily_bars(
        self,
        *,
        boards: Sequence[BoardDailySymbol],
        start_date: str,
        end_date: str,
    ) -> Sequence[Mapping[str, Any]]:
        require_yyyymmdd(start_date, "start_date")
        require_yyyymmdd(end_date, "end_date")
        rows: list[dict[str, Any]] = []
        for symbol in boards:
            frame = self._client.index(
                symbol=symbol.board_code,
                frequency=self.frequency,
                start=self.start,
                offset=self.offset,
            )
            rows.extend(
                _enrich_and_filter_records(
                    frame,
                    start_date=start_date,
                    end_date=end_date,
                    extra={
                        "board_code": symbol.board_code,
                        "board_name": symbol.board_name,
                        "board_type": symbol.board_type,
                        "source_symbol": symbol.board_code,
                    },
                )
            )
        return rows


def _enrich_and_filter_records(
    frame: Any,
    *,
    start_date: str,
    end_date: str,
    extra: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in _frame_to_records(frame):
        trade_date = parse_trade_date(record)
        if start_date <= trade_date <= end_date:
            enriched = dict(record)
            enriched.update({key: value for key, value in extra.items() if value is not None})
            enriched["trade_date"] = trade_date
            rows.append(enriched)
    return rows


def _frame_to_records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        try:
            records = frame.to_dict(orient="records")
        except TypeError:
            records = frame.to_dict("records")
        return [dict(record) for record in records]
    if isinstance(frame, Mapping):
        return [dict(frame)]
    if isinstance(frame, Iterable) and not isinstance(frame, (str, bytes)):
        return [dict(record) for record in frame]
    raise MootdxDailyBarSourceError(f"unsupported Mootdx frame type: {type(frame).__name__}")
