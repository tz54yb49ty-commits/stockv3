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
from urllib.request import Request, urlopen


TQ_MARKETS = ("5", "9", "11", "12", "14")
FORBIDDEN_SOURCE_MODULES = ("tushare", "mootdx")
ELTDX_FINANCE_BATCH_SIZE = 100


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

    def get_daily_bars(
        self, symbol: str, *, start_date: str, end_date: str,
        adjust: str | None, fill_data: bool,
    ) -> Any:
        result = self.call(
            "get_market_data",
            {
                "period": "1d",
                "stock_list": [symbol],
                "start_time": start_date,
                "end_time": end_date,
                "dividend_type": "front" if adjust == "qfq" else "none",
                "fill_data": fill_data,
            },
        )
        if not isinstance(result, Mapping):
            return result
        if symbol in result and isinstance(result[symbol], Mapping):
            result = result[symbol]
        columns = {key: value for key, value in result.items() if isinstance(value, list)}
        row_count = max((len(value) for value in columns.values()), default=0)
        return [
            {key: values[index] if index < len(values) else None for key, values in columns.items()}
            for index in range(row_count)
        ]


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
