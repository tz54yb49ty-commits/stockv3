from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from .contract import SOURCE_ADAPTER, QuoteIdentity


class MootdxStockQuoteAdapter:
    """Narrow, lazy Mootdx adapter; construction has no network side effects."""

    source_adapter = SOURCE_ADAPTER

    def __init__(self, client_factory: Callable[[], Any] | None = None) -> None:
        self._client_factory = client_factory or self._default_client_factory
        try:
            self.source_version = version("mootdx")
        except PackageNotFoundError:
            self.source_version = "unavailable"

    def fetch_stock_quotes(
        self, identities: Sequence[QuoteIdentity]
    ) -> Sequence[Mapping[str, Any]]:
        if any(identity.exchange == "BJ" for identity in identities):
            raise ValueError("BJ exchange mapping is not proven")
        client = self._client_factory()
        result = client.quotes(symbol=[identity.stock_code for identity in identities])
        if result is None:
            return []
        if hasattr(result, "to_dict"):
            return result.to_dict(orient="records")
        if isinstance(result, Sequence) and not isinstance(result, (str, bytes)):
            return list(result)
        raise TypeError("unexpected Mootdx quote response")

    @staticmethod
    def _default_client_factory() -> Any:
        from mootdx.quotes import Quotes

        return Quotes.factory(market="std")
