"""Tushare source adapter for common calendar and index identity."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import importlib
from typing import Any

from ashare_v3.ingestion.common import IngestionValidationError, require_yyyymmdd
from ashare_v3.ingestion.tushare_env import load_tushare_token


TRADE_CAL_FIELDS = "exchange,cal_date,is_open,pretrade_date"
INDEX_BASIC_FIELDS = ",".join(
    [
        "ts_code",
        "name",
        "fullname",
        "market",
        "publisher",
        "index_type",
        "category",
        "base_date",
        "base_point",
        "list_date",
        "weight_rule",
        "desc",
        "exp_date",
    ]
)
DEFAULT_INDEX_MARKETS = ("SSE", "SZSE", "CSI", "SW", "OTH", "MSCI", "CICC")


class TushareCommonIndexSourceError(IngestionValidationError):
    """Raised when Tushare common/index source configuration is invalid."""


class TushareCommonIndexSource:
    """Raw Tushare source implementing the CommonIndexRawSource protocol."""

    def __init__(
        self,
        *,
        token: str,
        trade_calendar_exchange: str = "SSE",
        index_markets: Sequence[str] = DEFAULT_INDEX_MARKETS,
        pro_client: Any | None = None,
        tushare_module: Any | None = None,
    ) -> None:
        cleaned_token = token.strip()
        if not cleaned_token:
            raise TushareCommonIndexSourceError("Tushare token is required")

        self.trade_calendar_exchange = trade_calendar_exchange.strip().upper() or "SSE"
        self.index_markets = tuple(_normalize_markets(index_markets))
        if not self.index_markets:
            raise TushareCommonIndexSourceError("index_markets are required")

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
        trade_calendar_exchange: str = "SSE",
        index_markets: Sequence[str] = DEFAULT_INDEX_MARKETS,
        pro_client: Any | None = None,
        tushare_module: Any | None = None,
    ) -> "TushareCommonIndexSource":
        token = (load_tushare_token(token_env=token_env) or "").strip()
        if not token:
            raise TushareCommonIndexSourceError(f"{token_env} environment variable is required")
        return cls(
            token=token,
            trade_calendar_exchange=trade_calendar_exchange,
            index_markets=index_markets,
            pro_client=pro_client,
            tushare_module=tushare_module,
        )

    def fetch_trade_calendar(self, *, start_date: str, end_date: str) -> Sequence[Mapping[str, Any]]:
        require_yyyymmdd(start_date, "start_date")
        require_yyyymmdd(end_date, "end_date")
        frame = self._pro_client.trade_cal(
            exchange=self.trade_calendar_exchange,
            start_date=start_date,
            end_date=end_date,
            fields=TRADE_CAL_FIELDS,
        )
        return _frame_to_records(frame)

    def fetch_index_basic(self, *, asof_date: str) -> Sequence[Mapping[str, Any]]:
        require_yyyymmdd(asof_date, "asof_date")
        rows: list[dict[str, Any]] = []
        for market in self.index_markets:
            frame = self._pro_client.index_basic(market=market, fields=INDEX_BASIC_FIELDS)
            rows.extend(_frame_to_records(frame))
        return rows

    def _require_tushare_module(self) -> Any:
        if self._tushare_module is None:
            self._tushare_module = importlib.import_module("tushare")
        return self._tushare_module


def _normalize_markets(index_markets: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_market in index_markets:
        market = str(raw_market).strip().upper()
        if not market or market in seen:
            continue
        normalized.append(market)
        seen.add(market)
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
    raise TushareCommonIndexSourceError(f"unsupported Tushare frame type: {type(frame).__name__}")
