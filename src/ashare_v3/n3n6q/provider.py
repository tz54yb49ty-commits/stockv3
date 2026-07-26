from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Protocol
from uuid import UUID, uuid4

from .contract import (
    CONTRACT_VERSION,
    SOURCE_ADAPTER,
    SOURCE_TIME_SEMANTICS,
    QuoteBatch,
    QuoteIdentity,
    QuoteItem,
)


_IDENTITY_FIELDS = frozenset({"identity_key", "exchange", "stock_code"})
_PROVEN_MARKETS = {"SH": 1, "SZ": 0}
_SOURCE_TIME_PATTERN = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9](?:\.[0-9]+)?)?$")


class StockQuoteAdapter(Protocol):
    source_adapter: str
    source_version: str

    def fetch_stock_quotes(
        self, identities: Sequence[QuoteIdentity]
    ) -> Sequence[Mapping[str, Any]]: ...


class QuoteProvider:
    def __init__(
        self,
        adapter: StockQuoteAdapter,
        *,
        clock: Callable[[], datetime] | None = None,
        uuid_factory: Callable[[], UUID] | None = None,
    ) -> None:
        if adapter.source_adapter != SOURCE_ADAPTER:
            raise ValueError(f"source_adapter must be {SOURCE_ADAPTER}")
        self._adapter = adapter
        self._clock = clock or (lambda: datetime.now().astimezone())
        self._uuid_factory = uuid_factory or uuid4

    def fetch_quotes(
        self, identities: Sequence[QuoteIdentity | Mapping[str, object]]
    ) -> QuoteBatch:
        request = self._validate_request(identities)
        requested_at = self._now_iso()
        batch_id = str(self._uuid_factory())
        supported = tuple(item for item in request if item.exchange in _PROVEN_MARKETS)

        rows: list[Mapping[str, Any]] = []
        provider_failed = False
        if supported:
            try:
                fetched = self._adapter.fetch_stock_quotes(supported)
                rows = list(fetched)
                if any(not isinstance(row, Mapping) for row in rows):
                    provider_failed = True
            except Exception:
                provider_failed = True

        fetched_at = self._now_iso()
        if provider_failed:
            items = tuple(
                self._not_ready(
                    item,
                    fetched_at,
                    "provider_error" if item.exchange in _PROVEN_MARKETS else "unsupported_exchange",
                )
                for item in request
            )
        else:
            items = self._normalize_items(request, supported, rows, fetched_at)

        passed_count = sum(item.quality_status == "passed" for item in items)
        if passed_count == len(items):
            batch_status = "passed"
        elif passed_count == 0:
            batch_status = "failed"
        else:
            batch_status = "partial"

        return QuoteBatch(
            contract_version=CONTRACT_VERSION,
            batch_id=batch_id,
            source_adapter=SOURCE_ADAPTER,
            source_version=str(self._adapter.source_version),
            source_time_semantics=SOURCE_TIME_SEMANTICS,
            requested_at=requested_at,
            completed_at=self._now_iso(),
            batch_status=batch_status,
            item_count=len(request),
            items=items,
        )

    def _validate_request(
        self, identities: Sequence[QuoteIdentity | Mapping[str, object]]
    ) -> tuple[QuoteIdentity, ...]:
        if isinstance(identities, (str, bytes)):
            raise ValueError("QuoteIdentity batch must be a sequence")
        try:
            raw_items = list(identities)
        except TypeError as exc:
            raise ValueError("QuoteIdentity batch must be a sequence") from exc
        if not 1 <= len(raw_items) <= 80:
            raise ValueError("QuoteIdentity batch size must be 1..80")

        request: list[QuoteIdentity] = []
        for raw_item in raw_items:
            if isinstance(raw_item, QuoteIdentity):
                item = raw_item
            elif isinstance(raw_item, Mapping):
                if set(raw_item) != _IDENTITY_FIELDS:
                    raise ValueError("QuoteIdentity v1 has unexpected fields")
                try:
                    item = QuoteIdentity(
                        identity_key=raw_item["identity_key"],  # type: ignore[arg-type]
                        exchange=raw_item["exchange"],  # type: ignore[arg-type]
                        stock_code=raw_item["stock_code"],  # type: ignore[arg-type]
                    )
                except (TypeError, ValueError) as exc:
                    raise ValueError("invalid QuoteIdentity v1") from exc
            else:
                raise ValueError("invalid QuoteIdentity v1")
            request.append(item)

        identity_keys = [item.identity_key for item in request]
        if len(set(identity_keys)) != len(identity_keys):
            raise ValueError("duplicate identity_key")
        return tuple(request)

    def _normalize_items(
        self,
        request: tuple[QuoteIdentity, ...],
        supported: tuple[QuoteIdentity, ...],
        rows: list[Mapping[str, Any]],
        fetched_at: str,
    ) -> tuple[QuoteItem, ...]:
        rows_by_code: dict[str, list[Mapping[str, Any]]] = {}
        for row in rows:
            rows_by_code.setdefault(str(row.get("code") or ""), []).append(row)
        code_counts = Counter(str(row.get("code") or "") for row in rows)
        requested_codes = {item.stock_code for item in supported}
        unexpected_response = any(code not in requested_codes for code in rows_by_code)

        items: list[QuoteItem] = []
        for item in request:
            if item.exchange not in _PROVEN_MARKETS:
                items.append(self._not_ready(item, fetched_at, "unsupported_exchange"))
                continue
            if unexpected_response:
                items.append(self._not_ready(item, fetched_at, "identity_mismatch"))
                continue
            matches = rows_by_code.get(item.stock_code, [])
            if code_counts[item.stock_code] > 1:
                items.append(self._not_ready(item, fetched_at, "identity_mismatch"))
                continue
            if not matches:
                items.append(self._not_ready(item, fetched_at, "missing"))
                continue
            items.append(self._normalize_item(item, matches[0], fetched_at))
        return tuple(items)

    def _normalize_item(
        self,
        identity: QuoteIdentity,
        row: Mapping[str, Any],
        fetched_at: str,
    ) -> QuoteItem:
        market = self._market_or_none(row.get("market"))
        if market != _PROVEN_MARKETS[identity.exchange]:
            return self._not_ready(identity, fetched_at, "identity_mismatch", market=market)

        source_time = row.get("servertime")
        if not isinstance(source_time, str) or _SOURCE_TIME_PATTERN.fullmatch(source_time) is None:
            return self._not_ready(identity, fetched_at, "invalid_source_time", market=market)

        try:
            current_price = self._decimal_string(row.get("price"), required=True)
            last_close = self._decimal_string(row.get("last_close"), required=False)
            day_open = self._decimal_string(row.get("open"), required=False)
            day_high = self._decimal_string(row.get("high"), required=False)
            day_low = self._decimal_string(row.get("low"), required=True)
            if Decimal(current_price) <= 0 or Decimal(day_low) <= 0:
                raise ValueError("non-positive required price")
        except (InvalidOperation, TypeError, ValueError):
            return self._not_ready(identity, fetched_at, "invalid_price", market=market)

        return QuoteItem(
            identity_key=identity.identity_key,
            exchange=identity.exchange,
            market=market,
            stock_code=identity.stock_code,
            current_price=current_price,
            last_close=last_close,
            day_open=day_open,
            day_high=day_high,
            day_low=day_low,
            source_time_text=source_time,
            fetched_at=fetched_at,
            quality_status="passed",
            quality_reason="ok",
        )

    @staticmethod
    def _decimal_string(value: object, *, required: bool) -> str | None:
        if value is None or value == "":
            if required:
                raise ValueError("required price missing")
            return None
        if isinstance(value, bool):
            raise ValueError("boolean is not a price")
        decimal_value = Decimal(str(value))
        if not decimal_value.is_finite():
            raise ValueError("price must be finite")
        return format(decimal_value, "f")

    @staticmethod
    def _market_or_none(value: object) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            market = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return market if value == market or str(value) == str(market) else None

    @staticmethod
    def _not_ready(
        identity: QuoteIdentity,
        fetched_at: str,
        reason: str,
        *,
        market: int | None = None,
    ) -> QuoteItem:
        return QuoteItem(
            identity_key=identity.identity_key,
            exchange=identity.exchange,
            market=market,
            stock_code=identity.stock_code,
            current_price=None,
            last_close=None,
            day_open=None,
            day_high=None,
            day_low=None,
            source_time_text=None,
            fetched_at=fetched_at,
            quality_status="not_ready",
            quality_reason=reason,  # type: ignore[arg-type]
        )

    def _now_iso(self) -> str:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value.isoformat()
