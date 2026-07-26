"""N6-owned construction of an explicitly endpoint-pinned Mootdx facade."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import logging
from pathlib import Path
import re
from time import monotonic
import tomllib
from typing import Any

from ashare_v3.n3n6q import MootdxStockQuoteAdapter, QuoteIdentity, QuoteProvider


DEFAULT_ENDPOINT_POOL_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "mootdx_endpoint_pool.toml"
)
_RAW_SOURCE_TIME_PATTERN = re.compile(
    r"^(?P<hour>[0-9]|[01][0-9]|2[0-3]):[0-5][0-9]"
    r"(?::[0-5][0-9](?:\.[0-9]+)?)?$"
)
_NUMERIC_SCALE = Decimal("0.00000001")
_NUMERIC_FIELDS = ("price", "last_close", "open", "high", "low")
_PROVEN_MARKETS = {"SH": 1, "SZ": 0}
LOGGER = logging.getLogger(__name__)


class N6MootdxEndpointError(RuntimeError):
    """No approved endpoint can provide a valid stock quote."""

    def __init__(self, message: str, *, failure_kind: str = "transport_error") -> None:
        super().__init__(message)
        self.failure_kind = failure_kind


@dataclass(frozen=True, slots=True)
class N6MootdxEndpointSelection:
    endpoint_pool_version: str
    endpoint_id: str
    host: str
    port: int

    @property
    def server(self) -> tuple[str, int]:
        return self.host, self.port


class N6MootdxStockQuoteAdapter(MootdxStockQuoteAdapter):
    """N6 persistence-safe wrapper around the frozen N3N6Q adapter."""

    def __init__(
        self,
        *,
        endpoint_pool_path: Path | str = DEFAULT_ENDPOINT_POOL_PATH,
        quotes_factory: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(client_factory=lambda: None)
        self._package_version = self.source_version
        self._endpoint_pool_path = Path(endpoint_pool_path)
        self._quotes_factory = quotes_factory

    def fetch_stock_quotes(
        self, identities: Sequence[QuoteIdentity]
    ) -> Sequence[Mapping[str, Any]]:
        if any(identity.exchange == "BJ" for identity in identities):
            raise ValueError("BJ exchange mapping is not proven")
        pool_version, endpoints = _load_endpoint_pool(self._endpoint_pool_path)
        factory = self._quotes_factory
        if factory is None:
            from mootdx.quotes import Quotes

            factory = Quotes.factory

        symbols = [identity.stock_code for identity in identities]
        failures: list[str] = []
        for ordinal, endpoint in enumerate(endpoints, start=1):
            client = None
            started = monotonic()
            try:
                client = _create_client(factory, endpoint)
                result = client.quotes(symbol=symbols)
                rows = _response_rows(result)
                normalized = [_normalize_business_row(raw) for raw in rows]
                matched_count, usable_count = _validate_business_batch(
                    identities, normalized
                )
                self.source_version = (
                    f"{self._package_version}|{pool_version}|{endpoint.endpoint_id}"
                )
                _log_endpoint_attempt(
                    endpoint_id=endpoint.endpoint_id,
                    attempt_ordinal=ordinal,
                    failure_kind=(
                        "selected_passed"
                        if usable_count == len(identities)
                        else "selected_partial"
                    ),
                    elapsed_ms=(monotonic() - started) * 1000,
                    selected=True,
                    requested_count=len(identities),
                    matched_count=matched_count,
                )
                return normalized
            except Exception as exc:
                failure_kind = (
                    exc.failure_kind
                    if isinstance(exc, N6MootdxEndpointError)
                    else "transport_error"
                )
                failures.append(f"{endpoint.endpoint_id}:{failure_kind}")
                _log_endpoint_attempt(
                    endpoint_id=endpoint.endpoint_id,
                    attempt_ordinal=ordinal,
                    failure_kind=failure_kind,
                    elapsed_ms=(monotonic() - started) * 1000,
                    selected=False,
                    requested_count=len(identities),
                    matched_count=0,
                )
            finally:
                close = getattr(client, "close", None)
                if callable(close):
                    close()
        raise N6MootdxEndpointError(
            "all configured Mootdx endpoints failed business batch: "
            + ",".join(failures),
            failure_kind="all_endpoints_failed",
        )


def build_n6_virtual_quote_provider(
    *,
    endpoint_pool_path: Path | str = DEFAULT_ENDPOINT_POOL_PATH,
    quotes_factory: Callable[..., Any] | None = None,
) -> QuoteProvider:
    """Build the N6 provider without using Mootdx's mutable best-IP cache."""

    return QuoteProvider(
        N6MootdxStockQuoteAdapter(
            endpoint_pool_path=endpoint_pool_path,
            quotes_factory=quotes_factory,
        )
    )


def create_n6_mootdx_client(
    *,
    endpoint_pool_path: Path | str = DEFAULT_ENDPOINT_POOL_PATH,
    quotes_factory: Callable[..., Any] | None = None,
) -> tuple[Any, N6MootdxEndpointSelection]:
    """Construct the first approved endpoint client without network probing."""

    pool_version, endpoints = _load_endpoint_pool(Path(endpoint_pool_path))
    factory = quotes_factory
    if factory is None:
        from mootdx.quotes import Quotes

        factory = Quotes.factory
    failures: list[str] = []
    for endpoint in endpoints:
        try:
            return _create_client(factory, endpoint), endpoint
        except Exception as exc:
            failures.append(f"{endpoint.endpoint_id}:{type(exc).__name__}")
    raise N6MootdxEndpointError(
        "all configured Mootdx endpoints failed client construction: "
        + ",".join(failures),
        failure_kind="all_endpoints_failed",
    )


def _create_client(
    factory: Callable[..., Any], endpoint: N6MootdxEndpointSelection
) -> Any:
    return factory(
        market="std",
        server=endpoint.server,
        timeout=5,
        raise_exception=True,
        auto_retry=False,
        heartbeat=False,
    )


def _load_endpoint_pool(
    path: Path,
) -> tuple[str, tuple[N6MootdxEndpointSelection, ...]]:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        pool_version = str(payload["endpoint_pool_version"]).strip()
        transport = str(payload["transport"]).strip()
        rows = payload["endpoints"]
    except (FileNotFoundError, OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        raise N6MootdxEndpointError("Mootdx endpoint pool is unavailable") from exc
    if not pool_version or transport != "mootdx":
        raise N6MootdxEndpointError("Mootdx endpoint pool metadata is invalid")
    endpoints: list[N6MootdxEndpointSelection] = []
    ordered_rows: list[tuple[int, str, Mapping[str, Any]]] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise N6MootdxEndpointError("Mootdx endpoint row is invalid")
        endpoint_id = str(raw.get("endpoint_id") or "")
        ordered_rows.append((int(raw.get("priority") or 0), endpoint_id, raw))
    for _, endpoint_id, row in sorted(ordered_rows):
        if not row.get("enabled") or row.get("quarantined"):
            continue
        if row.get("local_validation_status") != "protocol_passed":
            raise N6MootdxEndpointError(
                "enabled Mootdx endpoint lacks protocol validation"
            )
        endpoints.append(
            N6MootdxEndpointSelection(
                endpoint_pool_version=pool_version,
                endpoint_id=endpoint_id,
                host=str(row["host"]),
                port=int(row["port"]),
            )
        )
    if not endpoints:
        raise N6MootdxEndpointError("Mootdx endpoint pool has no usable endpoint")
    return pool_version, tuple(endpoints)


def _response_rows(result: Any) -> list[Mapping[str, Any]]:
    if result is None:
        raise N6MootdxEndpointError(
            "empty Mootdx response", failure_kind="empty_response"
        )
    if hasattr(result, "to_dict"):
        try:
            rows = result.to_dict(orient="records")
        except Exception as exc:
            raise N6MootdxEndpointError(
                "invalid Mootdx response shape",
                failure_kind="response_shape_invalid",
            ) from exc
    elif isinstance(result, Sequence) and not isinstance(result, (str, bytes)):
        rows = list(result)
    else:
        raise N6MootdxEndpointError(
            "invalid Mootdx response shape",
            failure_kind="response_shape_invalid",
        )
    if not rows:
        raise N6MootdxEndpointError(
            "empty Mootdx response", failure_kind="empty_response"
        )
    if any(not isinstance(row, Mapping) for row in rows):
        raise N6MootdxEndpointError(
            "invalid Mootdx response shape",
            failure_kind="response_shape_invalid",
        )
    return rows


def _normalize_business_row(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    row = dict(raw)
    canonical_time = canonicalize_mootdx_source_time(row.get("servertime"))
    if canonical_time is not None:
        row["servertime"] = canonical_time
    for field in _NUMERIC_FIELDS:
        value = row.get(field)
        if value is None or value == "":
            continue
        try:
            row[field] = _numeric_24_8(value)
        except ValueError:
            row[field] = None
    return row


def canonicalize_mootdx_source_time(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = _RAW_SOURCE_TIME_PATTERN.fullmatch(value)
    if match is None:
        return None
    hour = match.group("hour")
    return value if len(hour) == 2 else f"0{value}"


def _validate_business_batch(
    identities: Sequence[QuoteIdentity], rows: Sequence[Mapping[str, Any]]
) -> tuple[int, int]:
    expected = {identity.stock_code: identity for identity in identities}
    response_codes = [str(row.get("code") or "") for row in rows]
    if any(code not in expected for code in response_codes) or len(
        response_codes
    ) != len(set(response_codes)):
        raise N6MootdxEndpointError(
            "Mootdx batch identity is corrupt",
            failure_kind="batch_identity_corrupt",
        )
    matched = 0
    usable = 0
    for row in rows:
        identity = expected[str(row.get("code") or "")]
        if row.get("market") != _PROVEN_MARKETS[identity.exchange]:
            continue
        matched += 1
        try:
            price = Decimal(str(row.get("price")))
            day_low = Decimal(str(row.get("low")))
            if (
                canonicalize_mootdx_source_time(row.get("servertime")) is not None
                and price.is_finite()
                and day_low.is_finite()
                and price > 0
                and day_low > 0
            ):
                usable += 1
        except (InvalidOperation, TypeError, ValueError):
            pass
    if matched == 0:
        raise N6MootdxEndpointError(
            "Mootdx batch identity is corrupt",
            failure_kind="batch_identity_corrupt",
        )
    if usable == 0:
        raise N6MootdxEndpointError(
            "all Mootdx batch items are not ready",
            failure_kind="all_items_not_ready",
        )
    return matched, usable


def _log_endpoint_attempt(
    *,
    endpoint_id: str,
    attempt_ordinal: int,
    failure_kind: str,
    elapsed_ms: float,
    selected: bool,
    requested_count: int,
    matched_count: int,
) -> None:
    LOGGER.info(
        "n6_mootdx_endpoint_attempt %s",
        json.dumps(
            {
                "endpoint_id": endpoint_id,
                "attempt_ordinal": attempt_ordinal,
                "failure_kind": failure_kind,
                "elapsed_ms": round(elapsed_ms, 3),
                "selected": selected,
                "requested_count": requested_count,
                "matched_count": matched_count,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
    )


def _numeric_24_8(value: object) -> str:
    if isinstance(value, bool):
        raise ValueError("boolean is not a Mootdx numeric field")
    try:
        decimal_value = Decimal(str(value))
        if not decimal_value.is_finite():
            raise ValueError("Mootdx numeric field must be finite")
        normalized = decimal_value.quantize(_NUMERIC_SCALE, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invalid Mootdx numeric field") from exc
    if normalized != 0 and normalized.copy_abs().adjusted() > 15:
        raise ValueError("Mootdx numeric field exceeds numeric(24,8)")
    return format(normalized, ".8f")
