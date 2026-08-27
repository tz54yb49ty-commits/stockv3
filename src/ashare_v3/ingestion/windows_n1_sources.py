"""Windows-only N1 source adapters for TQ and eltdx.

The module deliberately has no Tushare/Mootdx import or fallback path.  Vendor
modules are imported lazily so unit tests and WSL static checks remain usable.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import asdict, is_dataclass
from datetime import date
import importlib
import json
from typing import Any, Iterable, Mapping, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TQ_MARKETS = ("5", "9", "11", "12", "14")
FORBIDDEN_SOURCE_MODULES = ("tushare", "mootdx")
ELTDX_FINANCE_BATCH_SIZE = 100
LOCAL_TRADE_CALENDAR_SOURCE = "local_trade_calendar.rest.v1"


def three_year_start(today: date) -> str:
    return f"{today.year - 3:04d}0101"


def _records(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if hasattr(value, "to_dict"):
        try:
            value = value.to_dict("records")
        except TypeError:
            value = value.to_dict()
    elif hasattr(value, "records"):
        value = value.records
    elif hasattr(value, "rows"):
        value = value.rows
    if isinstance(value, Mapping):
        value = [value]
    rows = []
    for row in value:
        if isinstance(row, Mapping):
            rows.append(dict(row))
        elif is_dataclass(row):
            rows.append(asdict(row))
        elif hasattr(row, "to_dict"):
            rows.append(dict(row.to_dict()))
        elif hasattr(row, "__dict__"):
            rows.append({key: item for key, item in vars(row).items() if not key.startswith("_")})
        else:
            raise TypeError(f"unsupported vendor record type: {type(row).__name__}")
    return rows


def load_vendor_module(module_name: str) -> Any:
    root = module_name.partition(".")[0].lower()
    if root in FORBIDDEN_SOURCE_MODULES:
        raise RuntimeError(f"forbidden Windows N1 source module: {root}")
    return importlib.import_module(module_name)


class TQClient(Protocol):
    def get_stock_list(self, market: str) -> Any: ...
    def get_stock_list_in_sector(self, market: str) -> Any: ...
    def get_daily_bars(
        self, symbol: str, *, start_date: str, end_date: str,
        adjust: str | None, fill_data: bool,
    ) -> Any: ...
    def get_daily_bars_batch(
        self, symbols: Sequence[str], *, start_date: str, end_date: str,
        adjust: str | None, fill_data: bool,
    ) -> Any: ...


@dataclass(frozen=True)
class LocalTradeCalendarProvider:
    """GET-only client for the local trade-calendar REST service."""

    base_url: str = "http://127.0.0.1:8000"
    timeout_seconds: float = 5.0

    def _get(self, path: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        query = "" if not params else "?" + urlencode(params)
        request = Request(self.base_url.rstrip("/") + path + query, method="GET")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise RuntimeError(f"local trade-calendar request failed: {path}: {error}") from error
        if not isinstance(payload, Mapping):
            raise RuntimeError(f"local trade-calendar returned non-object JSON: {path}")
        return dict(payload)

    def health(self) -> dict[str, Any]:
        payload = self._get("/health")
        if payload.get("status") != "ok" or payload.get("database") != "up":
            raise RuntimeError(f"local trade-calendar is not healthy: {payload}")
        return payload

    def range(self, exchange: str = "SSE") -> dict[str, str]:
        payload = self._get("/api/range", {"exchange": exchange})
        if payload.get("exchange") != exchange:
            raise RuntimeError(f"local trade-calendar exchange mismatch: {payload}")
        minimum = str(payload.get("min") or "")
        maximum = str(payload.get("max") or "")
        if len(minimum) != 8 or len(maximum) != 8 or not minimum.isdigit() or not maximum.isdigit():
            raise RuntimeError(f"local trade-calendar invalid range: {payload}")
        if minimum > maximum:
            raise RuntimeError(f"local trade-calendar reversed range: {payload}")
        return {"exchange": exchange, "min": minimum, "max": maximum}

    def fetch(self, start_date: str, end_date: str, exchange: str = "SSE") -> list[dict[str, Any]]:
        payload = self._get(
            "/api/trade_cal",
            {"exchange": exchange, "start_date": start_date, "end_date": end_date},
        )
        items = payload.get("items")
        if not isinstance(items, list) or int(payload.get("total", -1)) != len(items):
            raise RuntimeError(f"local trade-calendar total/items mismatch: {payload.get('total')}")
        rows = _records(items)
        dates = [str(row.get("cal_date") or "") for row in rows]
        if not rows or dates[0] != start_date or dates[-1] != end_date:
            raise RuntimeError("local trade-calendar response does not cover the requested range")
        if len(dates) != len(set(dates)) or dates != sorted(dates):
            raise RuntimeError("local trade-calendar returned duplicate or unsorted dates")
        if any(row.get("exchange") != exchange for row in rows):
            raise RuntimeError("local trade-calendar returned an unexpected exchange")
        return rows


@dataclass
class TQHttpClient:
    """Minimal JSON-RPC client for the native TdxW HTTP service."""

    base_url: str = "http://127.0.0.1:17709"
    timeout_seconds: float = 30.0
    _request_id: int = 0

    def call(self, method: str, params: Mapping[str, Any]) -> Any:
        self._request_id += 1
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": dict(params)},
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(self.base_url, data=payload, headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=self.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
        if body.get("error"):
            raise RuntimeError(f"TQ HTTP error: {body['error']}")
        result = body.get("result")
        if isinstance(result, Mapping) and str(result.get("ErrorId", "0")) != "0":
            raise RuntimeError(f"TQ method error: {result.get('Error')}")
        return result.get("Value", result) if isinstance(result, Mapping) else result

    def get_stock_list_in_sector(self, market: str) -> Any:
        return self.call("get_stock_list_in_sector", {"block_code": market, "list_type": 1})

    def get_stock_list(self, market: str) -> Any:
        return self.call("get_stock_list", {"market": market, "list_type": 1})

    @staticmethod
    def _columnar_rows(result: Mapping[str, Any]) -> list[dict[str, Any]]:
        columns = {key: value for key, value in result.items() if isinstance(value, list)}
        row_count = max((len(value) for value in columns.values()), default=0)
        return [
            {key: values[index] if index < len(values) else None for key, values in columns.items()}
            for index in range(row_count)
        ]

    def get_daily_bars_batch(
        self, symbols: Sequence[str], *, start_date: str, end_date: str,
        adjust: str | None, fill_data: bool,
    ) -> dict[str, list[dict[str, Any]]]:
        requested = tuple(symbols)
        if not requested:
            return {}
        if len(requested) > 100:
            raise ValueError("TQ daily batch exceeds 100 symbols")
        result = self.call(
            "get_market_data",
            {
                "period": "1d",
                "stock_list": list(requested),
                "start_time": start_date,
                "end_time": end_date,
                "dividend_type": "front" if adjust == "qfq" else "none",
                "fill_data": fill_data,
            },
        )
        if not isinstance(result, Mapping):
            raise RuntimeError("TQ daily batch returned a non-object result")
        if len(requested) == 1 and requested[0] not in result:
            return {requested[0]: self._columnar_rows(result)}
        return {
            symbol: self._columnar_rows(payload)
            if isinstance((payload := result.get(symbol)), Mapping)
            else []
            for symbol in requested
        }

    def get_daily_bars(
        self, symbol: str, *, start_date: str, end_date: str,
        adjust: str | None, fill_data: bool,
    ) -> Any:
        return self.get_daily_bars_batch(
            (symbol,), start_date=start_date, end_date=end_date,
            adjust=adjust, fill_data=fill_data,
        )[symbol]


@dataclass(frozen=True)
class TQWindowsSource:
    client: TQClient

    def fetch_market_members(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for market in TQ_MARKETS:
            for row in _records(self.client.get_stock_list(market)):
                rows.append({**row, "market": market})
        return rows

    def fetch_sector_members(self, block_code: str) -> list[dict[str, Any]]:
        return _records(self.client.get_stock_list_in_sector(block_code))

    def fetch_daily(
        self,
        symbol: str,
        *,
        asset_kind: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        if asset_kind not in {"stock", "index", "board"}:
            raise ValueError(f"unsupported asset_kind: {asset_kind}")
        adjust = "qfq" if asset_kind == "stock" else None
        return _records(
            self.client.get_daily_bars(
                symbol,
                start_date=start_date,
                end_date=end_date,
                adjust=adjust,
                fill_data=False,
            )
        )

    def fetch_daily_batch(
        self,
        symbols: Sequence[str],
        *,
        asset_kind: str,
        start_date: str,
        end_date: str,
    ) -> dict[str, list[dict[str, Any]]]:
        if asset_kind not in {"stock", "index", "board"}:
            raise ValueError(f"unsupported asset_kind: {asset_kind}")
        requested = tuple(symbols)
        if len(requested) > 100:
            raise ValueError("TQ daily batch exceeds 100 symbols")
        adjust = "qfq" if asset_kind == "stock" else None
        return {
            symbol: _records(rows)
            for symbol, rows in self.client.get_daily_bars_batch(
                requested,
                start_date=start_date,
                end_date=end_date,
                adjust=adjust,
                fill_data=False,
            ).items()
        }


@dataclass(frozen=True)
class EltdxWindowsSource:
    client: Any

    def fetch_finance_batch(self, codes: Sequence[str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for offset in range(0, len(codes), ELTDX_FINANCE_BATCH_SIZE):
            batch = tuple(codes[offset : offset + ELTDX_FINANCE_BATCH_SIZE])
            rows.extend(_records(self.client.corporate.finance_batch(batch)))
        return rows

    def fetch_three_reports(self, code: str) -> dict[str, list[dict[str, Any]]]:
        return {
            name: _records(self.client.f10.finance_report(code, report_type=report_type))
            for name, report_type in (
                ("balance", "zcfzb"),
                ("income", "lrb"),
                ("cashflow", "xjllb"),
            )
        }


def calculate_market_values(
    *, close: Any, total_share: Any, float_share: Any
) -> tuple[float | None, float | None]:
    def product(shares: Any) -> float | None:
        if close is None or shares is None:
            return None
        return float(close) * float(shares)

    return product(total_share), product(float_share)


def validate_ohlc_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    valid: list[dict[str, Any]] = []
    for row in rows:
        if not all(row.get(field) is not None for field in ("trade_date", "open", "high", "low", "close")):
            continue
        if min(float(row[field]) for field in ("open", "high", "low", "close")) <= 0:
            continue
        if float(row["high"]) < float(row["low"]):
            continue
        valid.append(dict(row))
    return valid


def normalize_tq_daily_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for raw in rows:
        row = {str(key).lower(): value for key, value in raw.items()}
        trade_date = str(row.get("date") or "").split(".", 1)[0]
        candidate = {
            "trade_date": trade_date,
            "open": row.get("open"),
            "high": row.get("high"),
            "low": row.get("low"),
            "close": row.get("close"),
            "volume": row.get("volume"),
            "amount": row.get("amount"),
            "adj_factor": row.get("forwardfactor"),
            "raw_payload": dict(raw),
        }
        normalized.extend(validate_ohlc_rows([candidate]))
    return normalized
