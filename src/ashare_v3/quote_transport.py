"""Endpoint-pinned quote transports with a Mootdx-default rollback flag.

The transport boundary performs no normalization owned by N1/N3.  It only
maps the established ``quotes/bars/index/index_bars/minute`` call surface to a
single explicitly selected endpoint.  Creating a transport may connect its
underlying client; callers remain responsible for deciding when network work
is authorized.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import importlib
import os
from typing import Any, Protocol, runtime_checkable

from ashare_v3.mootdx_client import (
    EndpointSelection,
    MootdxEndpointSelectionError,
    create_mootdx_client,
)


DEFAULT_QUOTE_TRANSPORT = "mootdx"
QUOTE_TRANSPORT_ENV = "ASHARE_V3_QUOTE_TRANSPORT"
SUPPORTED_QUOTE_TRANSPORTS = frozenset({"mootdx", "tdxpy"})
TDXPY_BJ_STOCK_QUOTE_BLOCKER = "BLOCKED_N3_TDXPY_BJ_STOCK_QUOTE_UNSUPPORTED"


class QuoteTransportError(RuntimeError):
    """Base class for transport construction and call failures."""


class QuoteTransportConfigError(QuoteTransportError):
    """Raised when the transport feature flag is invalid."""


class QuoteTransportConnectionError(QuoteTransportError):
    """Raised when an explicitly selected endpoint cannot be connected."""


class QuoteTransportUnsupportedCall(QuoteTransportError):
    """Raised when a transport cannot honor the requested call contract."""


@runtime_checkable
class QuoteTransport(Protocol):
    """Compatibility surface consumed by existing N1/N3 quote adapters."""

    transport_name: str
    endpoint_selection: EndpointSelection

    def quotes(self, symbol: str | Sequence[str] | None = None, **kwargs: Any) -> Any: ...

    def bars(
        self,
        symbol: str = "000001",
        frequency: int | str = 9,
        start: int = 0,
        offset: int = 800,
        **kwargs: Any,
    ) -> Any: ...

    def index(
        self,
        symbol: str = "000001",
        frequency: int | str = 9,
        start: int = 0,
        offset: int = 800,
        **kwargs: Any,
    ) -> Any: ...

    def index_bars(
        self,
        symbol: str = "000001",
        frequency: int | str = 9,
        start: int = 0,
        offset: int = 800,
        **kwargs: Any,
    ) -> Any: ...

    def minute(self, symbol: str | None = None, **kwargs: Any) -> Any: ...

    def close(self) -> None: ...


class MootdxQuoteTransport:
    """Thin compatibility wrapper around an explicitly pinned Mootdx client."""

    transport_name = "mootdx"

    def __init__(self, *, selection: EndpointSelection, client: Any) -> None:
        _require_selectable(selection)
        _require_transport(selection, self.transport_name)
        self.endpoint_selection = selection
        self._client = client
        self._closed = False

    def quotes(self, symbol: str | Sequence[str] | None = None, **kwargs: Any) -> Any:
        raw = self._call("quotes", symbol=symbol, **kwargs)
        return _attach_requested_symbol(raw, symbol if isinstance(symbol, str) else None)

    def bars(
        self,
        symbol: str = "000001",
        frequency: int | str = 9,
        start: int = 0,
        offset: int = 800,
        **kwargs: Any,
    ) -> Any:
        raw = self._call(
            "bars",
            symbol=symbol,
            frequency=frequency,
            start=start,
            offset=offset,
            **kwargs,
        )
        return _attach_requested_symbol(raw, symbol)

    def index(
        self,
        symbol: str = "000001",
        frequency: int | str = 9,
        start: int = 0,
        offset: int = 800,
        **kwargs: Any,
    ) -> Any:
        raw = self._call(
            "index",
            symbol=symbol,
            frequency=frequency,
            start=start,
            offset=offset,
            **kwargs,
        )
        return _attach_requested_symbol(raw, symbol)

    def index_bars(
        self,
        symbol: str = "000001",
        frequency: int | str = 9,
        start: int = 0,
        offset: int = 800,
        **kwargs: Any,
    ) -> Any:
        raw = self._call(
            "index_bars",
            symbol=symbol,
            frequency=frequency,
            start=start,
            offset=offset,
            **kwargs,
        )
        return _attach_requested_symbol(raw, symbol)

    def minute(self, symbol: str | None = None, **kwargs: Any) -> Any:
        raw = self._call("minute", symbol=symbol, **kwargs)
        return _attach_requested_symbol(raw, symbol)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        _close_underlying(self._client)

    def _call(self, method_name: str, **kwargs: Any) -> Any:
        method = getattr(self._client, method_name, None)
        if not callable(method):
            raise QuoteTransportUnsupportedCall(
                f"mootdx client does not support {method_name}"
            )
        return method(**kwargs)


class TdxpyQuoteTransport:
    """Direct tdxpy transport pinned to ``EndpointSelection.server``."""

    transport_name = "tdxpy"

    def __init__(
        self,
        *,
        selection: EndpointSelection,
        api_factory: Callable[..., Any] | None = None,
    ) -> None:
        _require_selectable(selection)
        _require_transport(selection, self.transport_name)
        self.endpoint_selection = selection
        if api_factory is None:
            api_factory = importlib.import_module("tdxpy.hq").TdxHq_API
        self._api = api_factory(
            auto_retry=False,
            heartbeat=False,
            raise_exception=True,
        )
        connected = self._api.connect(
            selection.host,
            selection.port,
            time_out=5,
        )
        if connected is None or connected is False:
            raise QuoteTransportConnectionError(
                f"tdxpy connect failed closed for endpoint_id={selection.endpoint_id}"
            )
        self._server = selection.server
        self._closed = False

    def quotes(self, symbol: str | Sequence[str] | None = None, **kwargs: Any) -> list[dict[str, Any]]:
        _reject_kwargs("quotes", kwargs)
        symbols = _symbols(symbol)
        if not symbols:
            return []
        routed = [(_stock_market(code), code) for code in symbols]
        beijing_symbols = [code for market, code in routed if market == 2]
        if beijing_symbols:
            raise QuoteTransportUnsupportedCall(
                "tdxpy Beijing stock quotes are unsupported by the approved "
                f"transport contract: {beijing_symbols}"
            )
        return _records(self._api.get_security_quotes(routed), symbols=symbols)

    def bars(
        self,
        symbol: str = "000001",
        frequency: int | str = 9,
        start: int = 0,
        offset: int = 800,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        _reject_kwargs("bars", kwargs)
        code = _code(symbol)
        raw = self._api.get_security_bars(
            _frequency(frequency),
            _stock_market(code),
            code,
            int(start),
            _offset(offset),
        )
        return _records(raw, symbols=[code])

    def index(
        self,
        symbol: str = "000001",
        frequency: int | str = 9,
        start: int = 0,
        offset: int = 800,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        return self.index_bars(
            symbol=symbol,
            frequency=frequency,
            start=start,
            offset=offset,
            **kwargs,
        )

    def index_bars(
        self,
        symbol: str = "000001",
        frequency: int | str = 9,
        start: int = 0,
        offset: int = 800,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        _reject_kwargs("index_bars", kwargs)
        code = _code(symbol)
        raw = self._api.get_index_bars(
            _frequency(frequency),
            _index_market(code),
            code,
            int(start),
            _offset(offset),
        )
        return _records(raw, symbols=[code])

    def minute(self, symbol: str | None = None, **kwargs: Any) -> list[dict[str, Any]]:
        allowed = {"date"}
        unknown = sorted(set(kwargs) - allowed)
        if unknown:
            raise QuoteTransportUnsupportedCall(
                f"tdxpy minute unsupported arguments: {unknown}"
            )
        code = _code(symbol)
        trade_date = kwargs.get("date")
        if trade_date is None:
            raw = self._api.get_minute_time_data(_stock_market(code), code)
        else:
            normalized_date = "".join(character for character in str(trade_date) if character.isdigit())
            if len(normalized_date) != 8:
                raise QuoteTransportUnsupportedCall(
                    "tdxpy minute date must normalize to YYYYMMDD"
                )
            raw = self._api.get_history_minute_time_data(
                _stock_market(code),
                code,
                int(normalized_date),
            )
        return _records(raw, symbols=[code])

    @property
    def server(self) -> tuple[str, int]:
        """The immutable endpoint pinned for this transport instance."""

        return self._server

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        _close_underlying(self._api)


def resolve_quote_transport_name(
    configured: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve the feature flag; the absent flag always rolls back to Mootdx."""

    source = os.environ if environ is None else environ
    value = configured if configured is not None else source.get(QUOTE_TRANSPORT_ENV)
    normalized = str(value or DEFAULT_QUOTE_TRANSPORT).strip().lower()
    if normalized not in SUPPORTED_QUOTE_TRANSPORTS:
        raise QuoteTransportConfigError(
            f"unsupported quote transport: {normalized or '<empty>'}"
        )
    return normalized


def quote_transport_scope_blocker(
    configured: str | None,
    objects: Sequence[Mapping[str, Any]],
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any] | None:
    """Return a fail-closed capability blocker before endpoint probing."""

    transport = resolve_quote_transport_name(configured, environ=environ)
    if transport != "tdxpy":
        return None
    unsupported = sorted(
        {
            str(row.get("identity_key") or "")
            for row in objects
            if str(row.get("asset_kind") or "") == "stock"
            and (
                str(row.get("exchange") or "").upper() == "BJ"
                or str(row.get("identity_key") or "").startswith("stock:BJ:")
            )
        }
        - {""}
    )
    if not unsupported:
        return None
    return {
        "blocker": TDXPY_BJ_STOCK_QUOTE_BLOCKER,
        "reason": "tdxpy transport does not support Beijing stock quotes",
        "transport": transport,
        "unsupported_identity_keys": unsupported,
    }


def create_quote_transport(
    selection: EndpointSelection,
    profile: str = "std",
    *,
    transport: str | None = None,
    environ: Mapping[str, str] | None = None,
    mootdx_client_factory: Callable[..., Any] = create_mootdx_client,
    tdxpy_api_factory: Callable[..., Any] | None = None,
) -> QuoteTransport:
    """Create the selected transport without changing the endpoint contract."""

    name = resolve_quote_transport_name(transport, environ=environ)
    if name == "mootdx":
        client = mootdx_client_factory(selection, profile)
        return MootdxQuoteTransport(selection=selection, client=client)
    if profile != "std":
        raise QuoteTransportUnsupportedCall(
            f"tdxpy only supports the std quote profile, got {profile!r}"
        )
    return TdxpyQuoteTransport(
        selection=selection,
        api_factory=tdxpy_api_factory,
    )


def transport_provenance(
    transport: QuoteTransport,
) -> dict[str, Any]:
    """Copy endpoint provenance while recording the actual selected transport."""

    payload = transport.endpoint_selection.to_provenance()
    payload["transport"] = transport.transport_name
    return payload


def _require_selectable(selection: EndpointSelection) -> None:
    if not selection.selectable:
        raise MootdxEndpointSelectionError(
            f"endpoint selection is fail-closed: {selection.selection_reason}"
        )


def _require_transport(selection: EndpointSelection, expected: str) -> None:
    if selection.transport != expected:
        raise QuoteTransportConfigError(
            "endpoint selection transport mismatch: "
            f"selection={selection.transport!r}, requested={expected!r}"
        )


def _symbols(value: str | Sequence[str] | None) -> list[str]:
    if value is None:
        return []
    raw = [value] if isinstance(value, str) else list(value)
    return [_code(item) for item in raw]


def _code(value: Any) -> str:
    code = str(value or "").strip()
    if code[:2].lower() in {"sh", "sz"}:
        code = code[2:]
    if len(code) != 6 or not code.isdigit():
        raise QuoteTransportUnsupportedCall(f"unsupported TDX symbol: {value!r}")
    return code


def _stock_market(code: str) -> int:
    if code.startswith(("4", "8", "920")):
        return 2
    if code.startswith(("50", "51", "60", "68", "90", "110", "113", "132", "204")):
        return 1
    if code.startswith(("00", "12", "13", "15", "16", "18", "20", "30", "39", "115", "1318")):
        return 0
    if code.startswith(("5", "6", "7", "9")):
        return 1
    return 1


def _index_market(code: str) -> int:
    if code.startswith("899"):
        return 2
    return 1 if code.startswith(("00", "88", "99")) else 0


def _frequency(value: int | str) -> int:
    aliases = {
        "5m": 0,
        "15m": 1,
        "30m": 2,
        "1h": 3,
        "day": 9,
        "week": 5,
        "mon": 6,
        "1m": 8,
        "3mon": 10,
        "year": 11,
    }
    if isinstance(value, str):
        if value not in aliases:
            raise QuoteTransportUnsupportedCall(f"unsupported TDX frequency: {value!r}")
        return aliases[value]
    normalized = int(value)
    if normalized not in range(12):
        raise QuoteTransportUnsupportedCall(f"unsupported TDX frequency: {value!r}")
    return normalized


def _offset(value: Any) -> int:
    normalized = int(value)
    if normalized <= 0:
        raise QuoteTransportUnsupportedCall("offset must be positive")
    return min(normalized, 800)


def _reject_kwargs(method_name: str, kwargs: Mapping[str, Any]) -> None:
    if kwargs:
        raise QuoteTransportUnsupportedCall(
            f"tdxpy {method_name} unsupported arguments: {sorted(kwargs)}"
        )


def _records(raw: Any, *, symbols: Sequence[str]) -> list[dict[str, Any]]:
    if raw is None or raw is False:
        return []
    if hasattr(raw, "to_dict"):
        try:
            values = raw.to_dict(orient="records")
        except TypeError:
            values = raw.to_dict("records")
    elif isinstance(raw, Mapping):
        values = [raw]
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        values = raw
    else:
        raise QuoteTransportError(
            f"unsupported tdxpy response type: {type(raw).__name__}"
        )
    rows = [dict(value) for value in values]
    if len(symbols) == 1:
        for row in rows:
            _attach_symbol_to_row(row, symbols[0])
    return rows


def _attach_requested_symbol(raw: Any, symbol: str | None) -> Any:
    """Attach explicit request identity only when the response has none."""

    if raw is None or raw is False or not symbol:
        return raw
    if isinstance(raw, Mapping):
        row = dict(raw)
        _attach_symbol_to_row(row, symbol)
        return row
    if isinstance(raw, list):
        rows = [dict(value) for value in raw]
        for row in rows:
            _attach_symbol_to_row(row, symbol)
        return rows
    if isinstance(raw, tuple):
        rows = [dict(value) for value in raw]
        for row in rows:
            _attach_symbol_to_row(row, symbol)
        return tuple(rows)
    if hasattr(raw, "columns") and hasattr(raw, "copy"):
        copied = raw.copy()
        columns = {str(value) for value in copied.columns}
        if "code" not in columns:
            copied["code"] = None
        missing_code = copied["code"].isna() | copied["code"].astype(str).str.strip().eq("")
        if "symbol" in columns:
            missing_symbol = (
                copied["symbol"].isna()
                | copied["symbol"].astype(str).str.strip().eq("")
            )
            missing_identity = missing_code & missing_symbol
        else:
            missing_identity = missing_code
        copied.loc[missing_identity, "code"] = symbol
        return copied
    return raw


def _attach_symbol_to_row(row: dict[str, Any], symbol: str) -> None:
    code = str(row.get("code") or "").strip()
    alternate = str(row.get("symbol") or "").strip()
    if not code and not alternate:
        row["code"] = symbol


def _close_underlying(client: Any) -> None:
    disconnect = getattr(client, "disconnect", None)
    if callable(disconnect):
        disconnect()
        return
    close = getattr(client, "close", None)
    if callable(close):
        close()
