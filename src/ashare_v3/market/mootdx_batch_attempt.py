"""N3 composition for one atomic Mootdx batch with bounded failover."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, TypeVar
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from ashare_v3.mootdx_client import (
    DEFAULT_REQUIRED_PROBE_CHECKS,
    EndpointSelection,
    MootdxEndpointManager,
    Probe,
)
from ashare_v3.quote_transport import (
    QuoteTransportError,
    create_quote_transport,
    resolve_quote_transport_name,
)


BatchResult = TypeVar("BatchResult")
ObjectValue = TypeVar("ObjectValue")
ClientFactory = Callable[[EndpointSelection], Any]
SelectionClientFactory = Callable[[EndpointSelection, str], Any]
TransportFactory = Callable[..., Any]
BatchFetch = Callable[[Any, EndpointSelection], BatchResult]
ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class MootdxBatchAttemptOutcome(Generic[BatchResult]):
    batch_id: str
    status: str
    result: BatchResult | None
    winning_attempt_id: str | None
    attempts: tuple[Mapping[str, Any], ...]

    def to_provenance(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "batch_status": self.status,
            "winning_attempt_id": self.winning_attempt_id,
            "attempts": [dict(row) for row in self.attempts],
        }


class MootdxEndpointAttemptFailure(RuntimeError):
    """Base class for endpoint-scoped failures that permit bounded failover."""


class MootdxEndpointSemanticValidationError(MootdxEndpointAttemptFailure):
    """Raised when endpoint data violates the current batch semantic contract."""


class MootdxEndpointTransportError(MootdxEndpointAttemptFailure):
    """Wrap a transport failure after a family adapter converted it to a result."""


class MootdxEndpointWideRequiredObjectsEmpty(MootdxEndpointAttemptFailure):
    """Raised only after the configured distinct required-object empty threshold."""


_ENDPOINT_TRANSPORT_EXCEPTION_NAMES = frozenset(
    {
        "TdxConnectionError",
        "TdxTimeoutError",
        "ResponseRecvFailed",
        "SendRequestError",
    }
)


def is_endpoint_transport_exception(exc: BaseException) -> bool:
    """Return true only for explicit endpoint transport failure types."""

    return isinstance(
        exc,
        (
            MootdxEndpointTransportError,
            QuoteTransportError,
            TimeoutError,
            ConnectionError,
            OSError,
        ),
    ) or type(exc).__name__ in _ENDPOINT_TRANSPORT_EXCEPTION_NAMES


@dataclass(frozen=True)
class MootdxRequiredObjectResult(Generic[ObjectValue]):
    identity_key: str
    status: str
    value: ObjectValue


class MootdxBatchObjectTracker:
    """Classify required-object empties without turning one missing object into failover."""

    def __init__(self, manager: MootdxEndpointManager, selection: EndpointSelection) -> None:
        self.manager = manager
        self.selection = selection
        self._consecutive_empty_identity_keys: list[str] = []

    def record(
        self,
        *,
        identity_key: str,
        value: ObjectValue,
        empty: bool,
    ) -> MootdxRequiredObjectResult[ObjectValue]:
        if not empty:
            self._consecutive_empty_identity_keys.clear()
            self.manager.record_required_object_result(
                self.selection.endpoint_id,
                transport=self.selection.transport,
                empty=False,
                object_identity=identity_key,
            )
            return MootdxRequiredObjectResult(identity_key=identity_key, status="passed", value=value)

        if identity_key not in self._consecutive_empty_identity_keys:
            self._consecutive_empty_identity_keys.append(identity_key)
        threshold_reached = (
            len(self._consecutive_empty_identity_keys)
            >= self.manager.required_empty_object_threshold
        )
        if threshold_reached:
            self.manager.record_transport_failure(
                self.selection.endpoint_id,
                transport=self.selection.transport,
                failure_kind="consecutive_required_objects_empty",
                detail=str(len(self._consecutive_empty_identity_keys)),
            )
            raise MootdxEndpointWideRequiredObjectsEmpty(
                f"endpoint-wide required-object empty threshold reached at {identity_key}"
            )
        return MootdxRequiredObjectResult(
            identity_key=identity_key,
            status="empty_required_object",
            value=value,
        )


def run_mootdx_batch_attempt(
    *,
    manager: MootdxEndpointManager,
    batch_id: str,
    probe: Probe,
    fetch_batch: BatchFetch[BatchResult],
    client_factory: ClientFactory | None = None,
    transport: str | None = None,
    transport_factory: TransportFactory = create_quote_transport,
    required_checks: Sequence[str] = DEFAULT_REQUIRED_PROBE_CHECKS,
) -> MootdxBatchAttemptOutcome[BatchResult]:
    """Return only a complete winning attempt; failed attempt data is discarded."""

    resolved_transport = resolve_quote_transport_name(transport)
    if client_factory is None:
        def selection_client_factory(
            selection: EndpointSelection,
            profile: str,
        ) -> Any:
            return transport_factory(
                selection,
                profile,
                transport=resolved_transport,
            )

        business_client_factory = lambda selection: selection_client_factory(selection, "std")
    else:
        def selection_client_factory(
            selection: EndpointSelection,
            profile: str,
        ) -> Any:
            del profile
            return client_factory(selection)

        business_client_factory = client_factory

    first = manager.select_for_batch(
        batch_id=batch_id,
        probe=probe,
        attempt_id=f"{batch_id}__attempt_1",
        required_checks=required_checks,
        transport=resolved_transport,
        client_factory=selection_client_factory,
    )
    if not first.selectable:
        return _failed_outcome(
            batch_id,
            [_selection_trace(first, status="selection_blocked")],
        )

    first_result, first_trace = _execute_attempt(
        selection=first,
        client_factory=business_client_factory,
        fetch_batch=fetch_batch,
    )
    if first_trace["status"] == "passed":
        return _passed_outcome(batch_id, first, first_result, [first_trace])

    if not first_trace.get("retry_allowed"):
        return _failed_outcome(batch_id, [first_trace])
    _record_attempt_failure(manager, first, first_trace)
    if first.failover_performed:
        return _failed_outcome(batch_id, [first_trace])

    second = manager.select_for_batch(
        batch_id=batch_id,
        probe=probe,
        attempt_id=f"{batch_id}__attempt_2",
        required_checks=required_checks,
        failover_from=first.endpoint_id,
        failover_reason=str(first_trace["failure_kind"]),
        transport=resolved_transport,
        client_factory=selection_client_factory,
    )
    if not second.selectable:
        return _failed_outcome(
            batch_id,
            [first_trace, _selection_trace(second, status="selection_blocked")],
        )
    if second.endpoint_id == first.endpoint_id or not second.failover_performed:
        return _failed_outcome(
            batch_id,
            [first_trace, _selection_trace(second, status="unsafe_retry_blocked")],
        )

    second_result, second_trace = _execute_attempt(
        selection=second,
        client_factory=business_client_factory,
        fetch_batch=fetch_batch,
    )
    if second_trace["status"] == "passed":
        return _passed_outcome(batch_id, second, second_result, [first_trace, second_trace])

    _record_attempt_failure(manager, second, second_trace)
    return _failed_outcome(batch_id, [first_trace, second_trace])


def with_batch_attempt_provenance(
    record: Mapping[str, Any],
    outcome: MootdxBatchAttemptOutcome[Any],
) -> dict[str, Any]:
    """Copy winning endpoint trace into an N3 fact/quality raw_json mapping."""

    raw_value = record.get("raw_json")
    raw_mapping = raw_value if isinstance(raw_value, Mapping) else getattr(raw_value, "obj", {})
    raw_json = dict(raw_mapping) if isinstance(raw_mapping, Mapping) else {}
    provenance = outcome.to_provenance()
    winning = next(
        (
            dict(row)
            for row in outcome.attempts
            if row.get("attempt_id") == outcome.winning_attempt_id
        ),
        None,
    )
    raw_json["mootdx_batch_attempt"] = provenance
    if winning is not None:
        for key in (
            "attempt_id",
            "endpoint_pool_version",
            "endpoint_id",
            "endpoint_host",
            "endpoint_port",
            "transport",
            "source_transport",
            "failover_mode",
            "failover_from",
            "failover_reason",
            "failover_performed",
        ):
            raw_json[key] = winning.get(key)
    copied = dict(record)
    copied["raw_json"] = Jsonb(raw_json) if isinstance(raw_value, Jsonb) else raw_json
    return copied


def build_mootdx_minute_semantic_probe(
    *,
    subscriptions: Sequence[Mapping[str, Any]],
    trade_date: str,
    adapter_factory: Callable[[Any], Any],
    fetch_rows: Callable[[Any, Mapping[str, Any], str], Sequence[Mapping[str, Any]]] | None = None,
) -> Probe:
    """Build a target-date minute probe over one deterministic sentinel per active asset kind."""

    sentinels = [
        sorted(
            (row for row in subscriptions if str(row.get("asset_kind") or "") == asset_kind),
            key=lambda row: str(row.get("identity_key") or ""),
        )[0]
        for asset_kind in ("stock", "index", "board")
        if any(str(row.get("asset_kind") or "") == asset_kind for row in subscriptions)
    ]

    def probe(endpoint: Any, make_client: Callable[[str], Any]) -> Mapping[str, Any]:
        del endpoint
        adapter = adapter_factory(make_client("std"))
        fetch = fetch_rows or (lambda value, subscription, date: value.fetch_minute_bars(subscription, date))
        sentinel_results = [
            _minute_sentinel_valid(
                fetch(adapter, subscription, trade_date),
                trade_date=trade_date,
            )
            for subscription in sentinels
        ]
        return {
            "checks": {
                "minute_scope_sentinels": bool(sentinels) and all(sentinel_results),
            },
            "sentinel_identity_keys": [str(row.get("identity_key") or "") for row in sentinels],
        }

    return probe


def _minute_sentinel_valid(
    rows: Sequence[Mapping[str, Any]],
    *,
    trade_date: str,
) -> bool:
    if not rows:
        return False
    labels: list[datetime] = []
    minute_labels: list[str] = []
    for row in rows:
        value = row.get("bar_time")
        if not isinstance(value, datetime):
            return False
        normalized = value.replace(tzinfo=ASIA_SHANGHAI) if value.tzinfo is None else value.astimezone(ASIA_SHANGHAI)
        if normalized.strftime("%Y%m%d") != trade_date:
            return False
        try:
            if float(row.get("close")) <= 0:
                return False
        except (TypeError, ValueError):
            return False
        labels.append(normalized)
        minute_labels.append(normalized.strftime("%H:%M"))
    if labels != sorted(labels) or len(set(labels)) != len(labels):
        return False
    canonical_interval_start = all(
        "09:30" <= label <= "11:29" or "13:00" <= label <= "14:59"
        for label in minute_labels
    )
    provider_close_label = all(
        "09:31" <= label <= "11:30" or "13:01" <= label <= "15:00"
        for label in minute_labels
    )
    return canonical_interval_start or provider_close_label


def _execute_attempt(
    *,
    selection: EndpointSelection,
    client_factory: ClientFactory,
    fetch_batch: BatchFetch[BatchResult],
) -> tuple[BatchResult | None, dict[str, Any]]:
    client: Any | None = None
    result: BatchResult | None = None
    trace: dict[str, Any] | None = None
    try:
        client = client_factory(selection)
        result = fetch_batch(client, selection)
    except MootdxEndpointWideRequiredObjectsEmpty as exc:
        trace = {
            **selection.to_provenance(),
            "status": "failed",
            "failure_kind": "consecutive_required_objects_empty",
            "error_type": type(exc).__name__,
            "manager_recorded_failure": True,
            "retry_allowed": True,
        }
    except (MootdxEndpointTransportError, QuoteTransportError) as exc:
        trace = {
            **selection.to_provenance(),
            "status": "failed",
            "failure_kind": "batch_transport_failure",
            "error_type": type(exc).__name__,
            "retry_allowed": True,
        }
    except MootdxEndpointSemanticValidationError as exc:
        trace = {
            **selection.to_provenance(),
            "status": "failed",
            "failure_kind": "endpoint_semantic_validation_failure",
            "error_type": type(exc).__name__,
            "retry_allowed": True,
        }
    except (TimeoutError, ConnectionError, OSError) as exc:
        trace = {
            **selection.to_provenance(),
            "status": "failed",
            "failure_kind": "batch_transport_failure",
            "error_type": type(exc).__name__,
            "retry_allowed": True,
        }
    except Exception as exc:  # noqa: BLE001 - unexpected bugs fail closed without circuit mutation.
        trace = {
            **selection.to_provenance(),
            "status": "failed_closed",
            "failure_kind": "unclassified_program_failure",
            "error_type": type(exc).__name__,
            "retry_allowed": False,
        }
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            try:
                close()
            except Exception as exc:  # noqa: BLE001 - a leaked/unclean client invalidates the attempt.
                if trace is None:
                    trace = {
                        **selection.to_provenance(),
                        "status": "failed",
                        "failure_kind": "client_close_failure",
                        "error_type": type(exc).__name__,
                        "retry_allowed": True,
                    }
                    result = None
                else:
                    trace["client_close_error_type"] = type(exc).__name__
                    trace["client_close_failed"] = True
    if trace is not None:
        return None, trace
    return result, _selection_trace(selection, status="passed")


def _record_attempt_failure(
    manager: MootdxEndpointManager,
    selection: EndpointSelection,
    trace: Mapping[str, Any],
) -> None:
    if trace.get("manager_recorded_failure"):
        return
    manager.record_transport_failure(
        selection.endpoint_id,
        transport=selection.transport,
        failure_kind=str(trace["failure_kind"]),
        detail=str(trace.get("error_type") or ""),
    )


def _selection_trace(selection: EndpointSelection, *, status: str) -> dict[str, Any]:
    return {**selection.to_provenance(), "status": status}


def _passed_outcome(
    batch_id: str,
    selection: EndpointSelection,
    result: BatchResult | None,
    attempts: Sequence[Mapping[str, Any]],
) -> MootdxBatchAttemptOutcome[BatchResult]:
    return MootdxBatchAttemptOutcome(
        batch_id=batch_id,
        status="passed",
        result=result,
        winning_attempt_id=selection.attempt_id,
        attempts=tuple(dict(row) for row in attempts),
    )


def _failed_outcome(
    batch_id: str,
    attempts: Sequence[Mapping[str, Any]],
) -> MootdxBatchAttemptOutcome[Any]:
    return MootdxBatchAttemptOutcome(
        batch_id=batch_id,
        status="failed",
        result=None,
        winning_attempt_id=None,
        attempts=tuple(dict(row) for row in attempts),
    )
