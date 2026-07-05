"""Tushare raw source adapters for v3 stock ingestion.

The adapter is intentionally limited to raw retrieval. It does not connect to
PostgreSQL, write files, or make source versions active.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import importlib
from typing import Any

from ashare_v3.ingestion.common import IngestionValidationError, normalize_exchange_from_ts_code
from ashare_v3.ingestion.tushare_env import load_tushare_token


STOCK_BASIC_FIELDS = ",".join(
    [
        "ts_code",
        "symbol",
        "name",
        "area",
        "industry",
        "market",
        "list_date",
        "delist_date",
        "list_status",
    ]
)

DAILY_BASIC_FIELDS = ",".join(
    [
        "ts_code",
        "trade_date",
        "close",
        "turnover_rate",
        "turnover_rate_f",
        "volume_ratio",
        "pe",
        "pe_ttm",
        "pb",
        "ps",
        "ps_ttm",
        "dv_ratio",
        "dv_ttm",
        "total_share",
        "float_share",
        "free_share",
        "total_mv",
        "circ_mv",
    ]
)

OFFICIAL_DAILY_PROOF_FIELDS = "ts_code,trade_date"


class TushareSourceError(IngestionValidationError):
    """Raised when a Tushare source cannot be configured safely."""


class TushareStockSource:
    """Raw Tushare source implementing the StockRawSource protocol."""

    def __init__(
        self,
        *,
        token: str,
        symbols: Sequence[str],
        pro_client: Any | None = None,
        tushare_module: Any | None = None,
    ) -> None:
        cleaned_token = token.strip()
        if not cleaned_token:
            raise TushareSourceError("Tushare token is required")

        self._symbols = tuple(_normalize_symbols(symbols))
        if not self._symbols:
            raise TushareSourceError("symbols are required to prevent accidental full-market pulls")

        self._tushare_module = tushare_module
        self._pro_client = pro_client
        if self._pro_client is None:
            module = self._require_tushare_module()
            if hasattr(module, "set_token"):
                module.set_token(cleaned_token)
            self._pro_client = module.pro_api(cleaned_token)

    @classmethod
    def from_env(
        cls,
        *,
        token_env: str = "TUSHARE_TOKEN",
        symbols: Sequence[str],
        pro_client: Any | None = None,
        tushare_module: Any | None = None,
    ) -> "TushareStockSource":
        token = (load_tushare_token(token_env=token_env) or "").strip()
        if not token:
            raise TushareSourceError(f"{token_env} environment variable is required")
        return cls(token=token, symbols=symbols, pro_client=pro_client, tushare_module=tushare_module)

    @property
    def symbols(self) -> tuple[str, ...]:
        return self._symbols

    def fetch_stock_basic(self, *, asof_date: str) -> Sequence[Mapping[str, Any]]:
        rows: list[dict[str, Any]] = []
        for list_status in ("L", "D", "P"):
            frame = self._pro_client.stock_basic(
                exchange="",
                list_status=list_status,
                fields=STOCK_BASIC_FIELDS,
            )
            rows.extend(_frame_to_records(frame))
        return [row for row in rows if str(row.get("ts_code") or "").strip() in self._symbols]

    def fetch_stock_daily_qfq(self, *, start_date: str, end_date: str) -> Sequence[Mapping[str, Any]]:
        module = self._require_tushare_module()
        rows: list[dict[str, Any]] = []
        for ts_code in self._symbols:
            frame = module.pro_bar(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                asset="E",
                freq="D",
                adj="qfq",
            )
            rows.extend(_frame_to_records(frame))
        return rows

    def fetch_stock_daily_basic(self, *, start_date: str, end_date: str) -> Sequence[Mapping[str, Any]]:
        rows: list[dict[str, Any]] = []
        for ts_code in self._symbols:
            frame = self._pro_client.daily_basic(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields=DAILY_BASIC_FIELDS,
            )
            rows.extend(_frame_to_records(frame))
        return rows

    def fetch_stock_official_daily_proof_keys(self, *, start_date: str, end_date: str) -> set[tuple[str, str]]:
        keys: set[tuple[str, str]] = set()
        for ts_code in self._symbols:
            frame = self._pro_client.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields=OFFICIAL_DAILY_PROOF_FIELDS,
            )
            for row in _frame_to_records(frame):
                raw_ts_code = row.get("ts_code")
                raw_trade_date = row.get("trade_date")
                if raw_ts_code and raw_trade_date:
                    keys.add((str(raw_ts_code).strip(), str(raw_trade_date).strip()))
        return keys

    def _require_tushare_module(self) -> Any:
        if self._tushare_module is None:
            self._tushare_module = importlib.import_module("tushare")
        return self._tushare_module


def _normalize_symbols(symbols: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_symbol in symbols:
        symbol = str(raw_symbol).strip().upper()
        if not symbol:
            continue
        normalize_exchange_from_ts_code(symbol)
        if symbol not in seen:
            normalized.append(symbol)
            seen.add(symbol)
    return normalized


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
    raise TushareSourceError(f"unsupported Tushare frame type: {type(frame).__name__}")
