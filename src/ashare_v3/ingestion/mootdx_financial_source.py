"""Mootdx raw source adapter for stock financial metrics."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import importlib
from typing import Any

from ashare_v3.ingestion.common import IngestionValidationError, require_yyyymmdd
from ashare_v3.ingestion.stock_financial import StockFinancialSymbol


class MootdxFinancialSourceError(IngestionValidationError):
    """Raised when Mootdx financial source configuration is invalid."""


class MootdxFinancialSource:
    """Fetch raw financial metrics using Mootdx `finance` endpoint."""

    def __init__(self, *, client: Any | None = None, market: str = "std") -> None:
        self.market = market
        self._client = client
        if self._client is None:
            quotes_module = importlib.import_module("mootdx.quotes")
            self._client = quotes_module.Quotes.factory(market=market)

    def fetch_stock_financial_metrics(
        self,
        *,
        symbols: Sequence[StockFinancialSymbol],
        asof_date: str,
    ) -> Sequence[Mapping[str, Any]]:
        require_yyyymmdd(asof_date, "asof_date")
        rows: list[dict[str, Any]] = []
        for symbol in symbols:
            frame = self._client.finance(symbol=symbol.code)
            for record in _frame_to_records(frame):
                enriched = dict(record)
                enriched.setdefault("code", symbol.code)
                enriched.setdefault("exchange", symbol.exchange)
                enriched.setdefault("ts_code", symbol.ts_code)
                if symbol.name:
                    enriched.setdefault("name", symbol.name)
                enriched.setdefault("requested_asof_date", asof_date)
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
    raise MootdxFinancialSourceError(f"unsupported Mootdx frame type: {type(frame).__name__}")
