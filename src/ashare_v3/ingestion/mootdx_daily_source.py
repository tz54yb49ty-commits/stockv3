"""Mootdx raw source adapter for index and board daily bars."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any
from uuid import uuid4

from ashare_v3.ingestion.common import IngestionValidationError, require_yyyymmdd
from ashare_v3.ingestion.daily_bars import BoardDailySymbol, IndexDailySymbol, parse_trade_date
from ashare_v3.mootdx_client import (
    DEFAULT_REQUIRED_PROBE_CHECKS,
    EndpointSelection,
    MootdxEndpointManager,
    Probe,
    _deterministic_sentinels,
    build_n1_protocol_probe,
)
from ashare_v3.quote_transport import (
    create_quote_transport,
    resolve_quote_transport_name,
)


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
        endpoint_manager: MootdxEndpointManager | None = None,
        endpoint_probe: Probe | None = None,
        client_factory: Any | None = None,
        transport_factory: Any = create_quote_transport,
        quote_transport: str | None = None,
        transport_environ: Mapping[str, str] | None = None,
        attempt_id: str | None = None,
        selection: EndpointSelection | None = None,
        failover_from: str | None = None,
        failover_reason: str | None = None,
    ) -> None:
        self.market = market
        self.frequency = frequency
        self.start = start
        self.offset = offset
        self._client = client
        self._endpoint_manager = endpoint_manager
        self._endpoint_probe = endpoint_probe
        self._transport_name = resolve_quote_transport_name(
            quote_transport,
            environ=transport_environ,
        )
        if client_factory is not None:
            self._client_factory = client_factory
        else:
            self._client_factory = lambda selection, profile: transport_factory(
                selection,
                profile,
                transport=self._transport_name,
            )
        self._attempt_id = attempt_id or f"n1_mootdx_source_attempt__{uuid4().hex}"
        self._failover_from = failover_from
        self._failover_reason = failover_reason
        self._would_retry = False
        self._retry_reason: str | None = None
        self._business_client_close_error: str | None = None
        if selection is not None and client is None:
            raise MootdxDailyBarSourceError("pinned selection requires an injected client")
        if selection is not None and not selection.selectable:
            raise MootdxDailyBarSourceError("pinned selection must be selectable")
        self._selection = selection
        self._pinned_endpoint_id = selection.endpoint_id if selection is not None else None
        if self._client is None:
            self._endpoint_manager = self._endpoint_manager or MootdxEndpointManager.from_toml()

    @property
    def endpoint_provenance(self) -> dict[str, Any] | None:
        if self._selection is None:
            return None
        return {
            **self._selection.to_provenance(),
            "would_retry": self._would_retry,
            "retry_reason": self._retry_reason,
            "business_client_close_error": self._business_client_close_error,
        }

    def close(self) -> None:
        client = self._client
        if client is None:
            return
        self._client = None
        close = getattr(client, "close", None)
        if not callable(close):
            return
        try:
            close()
        except Exception as exc:
            self._business_client_close_error = type(exc).__name__
            raise MootdxDailyBarSourceError(
                "Mootdx business client close failed; source attempt remains fail-closed"
            ) from exc

    def fetch_index_daily_bars(
        self,
        *,
        indexes: Sequence[IndexDailySymbol],
        start_date: str,
        end_date: str,
    ) -> Sequence[Mapping[str, Any]]:
        require_yyyymmdd(start_date, "start_date")
        require_yyyymmdd(end_date, "end_date")
        client = self._client_for_scope(
            scope_kind="index",
            symbols=[symbol.code for symbol in indexes],
            target_trade_date=end_date,
            require_scope_sentinels=False,
        )
        rows: list[dict[str, Any]] = []
        for symbol in indexes:
            frame = self._call_index(
                client,
                symbol=symbol.code,
            )
            self._record_required_object_result(
                frame,
                object_identity=f"index:{symbol.exchange}:{symbol.code}",
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
                    endpoint_provenance=self.endpoint_provenance,
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
        client = self._client_for_scope(
            scope_kind="board",
            symbols=[symbol.board_code for symbol in boards],
            target_trade_date=end_date,
            require_scope_sentinels=True,
        )
        rows: list[dict[str, Any]] = []
        for symbol in boards:
            frame = self._call_index(
                client,
                symbol=symbol.board_code,
            )
            self._record_required_object_result(
                frame,
                object_identity=f"board:{symbol.board_type}:{symbol.board_code}",
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
                    endpoint_provenance=self.endpoint_provenance,
                )
            )
        return rows

    def _client_for_scope(
        self,
        *,
        scope_kind: str,
        symbols: Sequence[str],
        target_trade_date: str,
        require_scope_sentinels: bool,
    ) -> Any:
        if self._client is not None and self._selection is not None:
            return self._client
        if self._endpoint_manager is None:
            return self._client
        probe = self._endpoint_probe or self._protocol_probe(
            scope_kind=scope_kind,
            symbols=symbols,
            target_trade_date=target_trade_date,
        )
        required_checks = (
            DEFAULT_REQUIRED_PROBE_CHECKS
            if require_scope_sentinels
            else tuple(
                name for name in DEFAULT_REQUIRED_PROBE_CHECKS if name != "scope_sentinels"
            )
        )
        selection = self._endpoint_manager.select_for_run(
            run_id=self._attempt_id,
            attempt_id=self._attempt_id,
            probe=probe,
            required_checks=required_checks,
            failover_from=self._failover_from,
            failover_reason=self._failover_reason,
            transport=self._transport_name,
            client_factory=self._client_factory,
        )
        self._selection = selection
        if not selection.selectable:
            raise MootdxDailyBarSourceError(
                "Mootdx endpoint preflight failed closed: "
                f"{selection.selection_reason}; would_switch_to={selection.would_switch_to or ''}"
            )
        if self._pinned_endpoint_id is not None and selection.endpoint_id != self._pinned_endpoint_id:
            raise MootdxDailyBarSourceError(
                "Mootdx endpoint changed within source-fetch attempt; discard the complete attempt"
            )
        if self._client is None:
            self._client = self._client_factory(selection, self.market)
            self._pinned_endpoint_id = selection.endpoint_id
        return self._client

    def _protocol_probe(
        self,
        *,
        scope_kind: str,
        symbols: Sequence[str],
        target_trade_date: str,
    ) -> Probe:
        return build_n1_protocol_probe(
            scope_kind=scope_kind,
            symbols=symbols,
            target_trade_date=target_trade_date,
            frequency=self.frequency,
            start=self.start,
            offset=self.offset,
        )

    def _call_index(self, client: Any, *, symbol: str) -> Any:
        try:
            return client.index(
                symbol=symbol,
                frequency=self.frequency,
                start=self.start,
                offset=self.offset,
            )
        except Exception as exc:
            if (
                self._endpoint_manager is not None
                and self._pinned_endpoint_id is not None
                and self._selection is not None
            ):
                self._endpoint_manager.record_transport_failure(
                    self._pinned_endpoint_id,
                    transport=self._selection.transport,
                    failure_kind="source_fetch_transport_exception",
                    detail=type(exc).__name__,
                )
                self._would_retry = True
                self._retry_reason = "source_fetch_transport_exception"
            raise MootdxDailyBarSourceError(
                f"Mootdx source-fetch transport failure for {symbol}: {type(exc).__name__}"
            ) from exc

    def _record_required_object_result(self, frame: Any, *, object_identity: str) -> None:
        if (
            self._endpoint_manager is None
            or self._pinned_endpoint_id is None
            or self._selection is None
        ):
            return
        empty = not _frame_to_records(frame)
        if self._endpoint_manager.record_required_object_result(
            self._pinned_endpoint_id,
            transport=self._selection.transport,
            empty=empty,
            object_identity=object_identity,
        ):
            self._would_retry = True
            self._retry_reason = "consecutive_required_objects_empty"
            raise MootdxDailyBarSourceError(
                "Mootdx endpoint-wide failure: three consecutive required objects were empty; "
                "discard the complete source-fetch attempt"
            )


def _enrich_and_filter_records(
    frame: Any,
    *,
    start_date: str,
    end_date: str,
    extra: Mapping[str, Any],
    endpoint_provenance: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in _frame_to_records(frame):
        trade_date = parse_trade_date(record)
        if start_date <= trade_date <= end_date:
            enriched = dict(record)
            enriched.update({key: value for key, value in extra.items() if value is not None})
            enriched["trade_date"] = trade_date
            if endpoint_provenance is not None:
                enriched["mootdx_endpoint_provenance"] = dict(endpoint_provenance)
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
