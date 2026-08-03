"""Versioned Mootdx endpoint selection and client construction.

The health cache is only a short-lived circuit-breaker aid.  Callers must copy
``EndpointSelection.to_provenance()`` into their own authoritative run trace.
This module performs no network work until a caller supplies a probe or asks
``create_mootdx_client`` to construct a client.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import importlib
import ipaddress
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
import tomllib
from types import MappingProxyType
from typing import Any
from uuid import uuid4


DEFAULT_ENDPOINT_POOL_PATH = Path(__file__).resolve().parents[2] / "configs" / "mootdx_endpoint_pool.toml"
DEFAULT_HEALTH_CACHE_PATH = Path("~/.cache/ashare_v3/mootdx_endpoint_health_v1.json").expanduser()
DEFAULT_CLIENT_FACTORY_LOCK_PATH = Path(
    "~/.cache/ashare_v3/mootdx_client_factory_v1.lock"
).expanduser()
DEFAULT_REQUIRED_PROBE_CHECKS = (
    "stock_quote",
    "stock_daily_bars",
    "index_daily_bars",
    "scope_sentinels",
)
HEALTH_CACHE_SCHEMA_V1 = "mootdx_endpoint_health_v1"
HEALTH_CACHE_SCHEMA_V2 = "mootdx_endpoint_health_v2"
HEALTH_STATES = {"unknown", "healthy", "degraded", "open", "half_open"}
FAILOVER_MODES = {"observe", "active"}
_CLIENT_FACTORY_THREAD_LOCK = RLock()
_HEALTH_CACHE_THREAD_LOCK = RLock()


class MootdxEndpointError(RuntimeError):
    """Base class for endpoint policy failures."""


class MootdxEndpointConfigError(MootdxEndpointError):
    """Raised when the versioned endpoint pool is invalid or unavailable."""


class MootdxEndpointSelectionError(MootdxEndpointError):
    """Raised when a blocked selection is used to create a client."""


@dataclass(frozen=True)
class EndpointConfig:
    endpoint_id: str
    host: str
    port: int
    priority: int
    enabled: bool
    quarantined: bool
    provenance_url: str
    provenance_commit: str
    local_validation_status: str

    @property
    def server(self) -> tuple[str, int]:
        return self.host, self.port


@dataclass
class EndpointHealth:
    endpoint_id: str
    transport: str = "mootdx"
    state: str = "unknown"
    checked_at: str | None = None
    open_until: str | None = None
    consecutive_failures: int = 0
    consecutive_required_empty_objects: int = 0
    consecutive_required_empty_object_ids: list[str] = field(default_factory=list)
    probe_summary: dict[str, Any] = field(default_factory=dict)
    half_open_token: str | None = None
    half_open_until: str | None = None


@dataclass(frozen=True)
class EndpointSelection:
    endpoint_pool_version: str
    endpoint_id: str
    host: str
    port: int
    transport: str
    health_state: str
    health_checked_at: str | None
    probe_summary: Mapping[str, Any]
    attempt_id: str
    selection_reason: str
    failover_mode: str
    selectable: bool
    failover_from: str | None = None
    failover_reason: str | None = None
    would_switch_to: str | None = None
    failover_performed: bool = False
    endpoint_probe_results: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "probe_summary", _deep_freeze_json(self.probe_summary))
        object.__setattr__(
            self,
            "endpoint_probe_results",
            tuple(_deep_freeze_json(row) for row in self.endpoint_probe_results),
        )

    @property
    def server(self) -> tuple[str, int]:
        return self.host, self.port

    def to_provenance(self) -> dict[str, Any]:
        endpoint_probe_results = _deep_thaw_json(self.endpoint_probe_results)
        return {
            "endpoint_pool_version": self.endpoint_pool_version,
            "endpoint_id": self.endpoint_id,
            "endpoint_host": self.host,
            "endpoint_port": self.port,
            "transport": self.transport,
            "source_transport": self.transport,
            "health_state": self.health_state,
            "health_checked_at": self.health_checked_at,
            "probe_summary": _deep_thaw_json(self.probe_summary),
            "attempt_id": self.attempt_id,
            "selection_reason": self.selection_reason,
            "failover_mode": self.failover_mode,
            "selectable": self.selectable,
            "failover_from": self.failover_from,
            "failover_reason": self.failover_reason,
            "would_switch_to": self.would_switch_to,
            "failover_performed": self.failover_performed,
            "endpoint_probe_results": endpoint_probe_results,
            "pool_probe_summary": {
                "enabled_endpoint_count": sum(
                    row.get("enabled") is True for row in endpoint_probe_results
                ),
                "probed_endpoint_count": sum(
                    row.get("excluded_reason") is None for row in endpoint_probe_results
                ),
                "passed_endpoint_ids": [
                    str(row["endpoint_id"])
                    for row in endpoint_probe_results
                    if row.get("passed") is True
                ],
                "failed_endpoint_ids": [
                    str(row["endpoint_id"])
                    for row in endpoint_probe_results
                    if row.get("passed") is False and row.get("excluded_reason") is None
                ],
                "excluded_endpoint_ids": [
                    str(row["endpoint_id"])
                    for row in endpoint_probe_results
                    if row.get("excluded_reason") is not None
                ],
            },
        }


ProbeClientFactory = Callable[[str], Any]
SelectionClientFactory = Callable[[EndpointSelection, str], Any]
Probe = Callable[[EndpointConfig, ProbeClientFactory], Mapping[str, Any]]
Clock = Callable[[], datetime]


class MootdxEndpointManager:
    """Select a stable endpoint and maintain the short-lived circuit state."""

    def __init__(
        self,
        *,
        endpoint_pool_version: str,
        transport: str,
        endpoints: Sequence[EndpointConfig],
        n1_failover_mode: str,
        n3_failover_mode: str,
        circuit_open_seconds: int,
        required_empty_object_threshold: int,
        health_cache_path: Path | str = DEFAULT_HEALTH_CACHE_PATH,
        clock: Clock | None = None,
    ) -> None:
        self.endpoint_pool_version = _required_text(endpoint_pool_version, "endpoint_pool_version")
        self.transport = _required_text(transport, "transport")
        self.endpoints = tuple(endpoints)
        self.n1_failover_mode = _validate_mode(n1_failover_mode, "n1_failover_mode")
        self.n3_failover_mode = _validate_mode(n3_failover_mode, "n3_failover_mode")
        self.circuit_open_seconds = _positive_int(circuit_open_seconds, "circuit_open_seconds")
        self.required_empty_object_threshold = _positive_int(
            required_empty_object_threshold,
            "required_empty_object_threshold",
        )
        self.health_cache_path = Path(health_cache_path).expanduser()
        self.health_cache_lock_path = self.health_cache_path.with_name(
            f"{self.health_cache_path.name}.lock"
        )
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        _validate_endpoints(self.endpoints)
        with self._locked_health_cache():
            pass

    @classmethod
    def from_toml(
        cls,
        path: Path | str = DEFAULT_ENDPOINT_POOL_PATH,
        *,
        health_cache_path: Path | str = DEFAULT_HEALTH_CACHE_PATH,
        clock: Clock | None = None,
    ) -> "MootdxEndpointManager":
        config_path = Path(path)
        try:
            payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise MootdxEndpointConfigError(f"endpoint pool config missing: {config_path}") from exc
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise MootdxEndpointConfigError(f"endpoint pool config unreadable: {config_path}") from exc
        try:
            endpoint_rows = payload["endpoints"]
            endpoints = tuple(EndpointConfig(**dict(row)) for row in endpoint_rows)
            return cls(
                endpoint_pool_version=payload["endpoint_pool_version"],
                transport=payload["transport"],
                endpoints=endpoints,
                n1_failover_mode=payload["n1_failover_mode"],
                n3_failover_mode=payload["n3_failover_mode"],
                circuit_open_seconds=payload["circuit_open_seconds"],
                required_empty_object_threshold=payload["required_empty_object_threshold"],
                health_cache_path=health_cache_path,
                clock=clock,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MootdxEndpointConfigError(f"endpoint pool config invalid: {config_path}") from exc

    def select_for_run(
        self,
        *,
        run_id: str,
        probe: Probe,
        attempt_id: str | None = None,
        required_checks: Sequence[str] = DEFAULT_REQUIRED_PROBE_CHECKS,
        failover_from: str | None = None,
        failover_reason: str | None = None,
        transport: str | None = None,
        client_factory: SelectionClientFactory | None = None,
    ) -> EndpointSelection:
        _required_text(run_id, "run_id")
        return self._select(
            probe=probe,
            attempt_id=attempt_id or f"{run_id}__attempt_{uuid4().hex}",
            mode=self.n1_failover_mode,
            required_checks=required_checks,
            failover_from=failover_from,
            failover_reason=failover_reason,
            transport=self.transport if transport is None else transport,
            client_factory=client_factory,
        )

    def select_for_batch(
        self,
        *,
        batch_id: str,
        probe: Probe,
        attempt_id: str | None = None,
        required_checks: Sequence[str] = DEFAULT_REQUIRED_PROBE_CHECKS,
        failover_from: str | None = None,
        failover_reason: str | None = None,
        transport: str | None = None,
        client_factory: SelectionClientFactory | None = None,
        failover_mode: str | None = None,
    ) -> EndpointSelection:
        _required_text(batch_id, "batch_id")
        resolved_failover_mode = (
            self.n3_failover_mode
            if failover_mode is None
            else _validate_mode(failover_mode, "failover_mode")
        )
        return self._select(
            probe=probe,
            attempt_id=attempt_id or f"{batch_id}__attempt_{uuid4().hex}",
            mode=resolved_failover_mode,
            required_checks=required_checks,
            failover_from=failover_from,
            failover_reason=failover_reason,
            transport=self.transport if transport is None else transport,
            client_factory=client_factory,
        )

    def record_transport_failure(
        self,
        endpoint_id: str,
        *,
        transport: str | None = None,
        failure_kind: str,
        detail: str | None = None,
    ) -> EndpointHealth:
        resolved_transport = self.transport if transport is None else _required_text(
            transport,
            "transport",
        )
        with self._locked_health_cache():
            health = self._health_for(endpoint_id, transport=resolved_transport)
            now = self._now()
            health.state = "open"
            health.checked_at = _format_time(now)
            health.open_until = _format_time(now + timedelta(seconds=self.circuit_open_seconds))
            health.consecutive_failures += 1
            health.half_open_token = None
            health.half_open_until = None
            health.probe_summary = {
                "passed": False,
                "failure_kind": _required_text(failure_kind, "failure_kind"),
                "detail": str(detail or ""),
            }
            self._write_health_cache_unlocked()
            return health

    def record_required_object_result(
        self,
        endpoint_id: str,
        *,
        transport: str | None = None,
        empty: bool,
        object_identity: str,
    ) -> bool:
        resolved_transport = self.transport if transport is None else _required_text(
            transport,
            "transport",
        )
        normalized_identity = (
            _required_text(object_identity, "object_identity") if empty else str(object_identity)
        )
        with self._locked_health_cache():
            health = self._health_for(endpoint_id, transport=resolved_transport)
            if (
                health.state == "open"
                and health.probe_summary.get("failure_kind")
                == "consecutive_required_objects_empty"
            ):
                return bool(empty)
            if not empty:
                if (
                    health.consecutive_required_empty_objects == 0
                    and not health.consecutive_required_empty_object_ids
                ):
                    return False
                health.consecutive_required_empty_objects = 0
                health.consecutive_required_empty_object_ids = []
                self._write_health_cache_unlocked()
                return False
            if normalized_identity not in health.consecutive_required_empty_object_ids:
                health.consecutive_required_empty_object_ids.append(normalized_identity)
            health.consecutive_required_empty_objects = len(
                health.consecutive_required_empty_object_ids
            )
            endpoint_wide_failure = (
                health.consecutive_required_empty_objects >= self.required_empty_object_threshold
            )
            if endpoint_wide_failure:
                now = self._now()
                health.state = "open"
                health.checked_at = _format_time(now)
                health.open_until = _format_time(
                    now + timedelta(seconds=self.circuit_open_seconds)
                )
                health.consecutive_failures += 1
                health.half_open_token = None
                health.half_open_until = None
                health.probe_summary = {
                    "passed": False,
                    "failure_kind": "consecutive_required_objects_empty",
                    "detail": str(health.consecutive_required_empty_objects),
                }
            self._write_health_cache_unlocked()
            return endpoint_wide_failure

    def _select(
        self,
        *,
        probe: Probe,
        attempt_id: str,
        mode: str,
        required_checks: Sequence[str],
        failover_from: str | None,
        failover_reason: str | None,
        transport: str,
        client_factory: SelectionClientFactory | None,
    ) -> EndpointSelection:
        resolved_transport = _required_text(transport, "transport")
        pool_endpoints = sorted(
            self.endpoints,
            key=lambda row: (row.priority, row.endpoint_id),
        )
        candidates = [row for row in pool_endpoints if row.enabled and not row.quarantined]
        if not candidates:
            raise MootdxEndpointConfigError("endpoint pool has no enabled non-quarantined endpoint")
        results: dict[str, bool] = {}
        endpoint_probe_results: list[dict[str, Any]] = []
        required = tuple(
            _required_text(value, "required_probe_check") for value in required_checks
        )
        for endpoint in pool_endpoints:
            if endpoint.quarantined:
                endpoint_probe_results.append(
                    self._excluded_probe_result(
                        endpoint,
                        required_checks=required,
                        state="excluded",
                        failure_kind="quarantined",
                        excluded_reason="quarantined",
                    )
                )
                continue
            if not endpoint.enabled:
                endpoint_probe_results.append(
                    self._excluded_probe_result(
                        endpoint,
                        required_checks=required,
                        state="excluded",
                        failure_kind="disabled",
                        excluded_reason="disabled",
                    )
                )
                continue
            results[endpoint.endpoint_id] = self._probe_endpoint(
                endpoint,
                probe=probe,
                required_checks=required,
                transport=resolved_transport,
                client_factory=client_factory,
                result_sink=endpoint_probe_results,
            )
        with self._locked_health_cache():
            reconciled_results: list[dict[str, Any]] = []
            final_results: dict[str, bool] = {}
            for row in endpoint_probe_results:
                reconciled = dict(row)
                endpoint_id = str(row["endpoint_id"])
                if endpoint_id in results:
                    health = self._health_for(
                        endpoint_id,
                        transport=resolved_transport,
                    )
                    final_results[endpoint_id] = (
                        results[endpoint_id] and health.state == "healthy"
                    )
                    if results[endpoint_id] and not final_results[endpoint_id]:
                        reconciled.update(
                            {
                                "state": health.state,
                                "checked_at": health.checked_at,
                                "passed": False,
                                "failure_kind": "health_changed_after_probe",
                                "excluded_reason": None,
                            }
                        )
                reconciled_results.append(reconciled)
            frozen_probe_results = tuple(reconciled_results)
            primary = candidates[0]
            healthy = [row for row in candidates if final_results[row.endpoint_id]]
            if healthy and healthy[0].endpoint_id == primary.endpoint_id:
                return self._selection(
                    primary,
                    attempt_id=attempt_id,
                    mode=mode,
                    selectable=True,
                    selection_reason="stable_priority_primary_healthy",
                    failover_from=failover_from,
                    failover_reason=failover_reason,
                    transport=resolved_transport,
                    endpoint_probe_results=frozen_probe_results,
                )
            if healthy:
                alternative = healthy[0]
                reason = f"{primary.endpoint_id}_mandatory_probe_failed"
                if mode == "observe":
                    return self._selection(
                        primary,
                        attempt_id=attempt_id,
                        mode=mode,
                        selectable=False,
                        selection_reason="observe_primary_unavailable_fail_closed",
                        failover_from=failover_from,
                        failover_reason=reason,
                        would_switch_to=alternative.endpoint_id,
                        transport=resolved_transport,
                        endpoint_probe_results=frozen_probe_results,
                    )
                return self._selection(
                    alternative,
                    attempt_id=attempt_id,
                    mode=mode,
                    selectable=True,
                    selection_reason="active_failover_to_stable_secondary",
                    failover_from=primary.endpoint_id,
                    failover_reason=reason,
                    failover_performed=True,
                    transport=resolved_transport,
                    endpoint_probe_results=frozen_probe_results,
                )
            return self._selection(
                primary,
                attempt_id=attempt_id,
                mode=mode,
                selectable=False,
                selection_reason="all_enabled_endpoints_unhealthy",
                failover_from=failover_from,
                failover_reason=failover_reason or "mandatory_probe_failed",
                transport=resolved_transport,
                endpoint_probe_results=frozen_probe_results,
            )

    def _probe_endpoint(
        self,
        endpoint: EndpointConfig,
        *,
        probe: Probe,
        required_checks: Sequence[str],
        transport: str | None = None,
        client_factory: SelectionClientFactory | None = None,
        result_sink: list[dict[str, Any]] | None = None,
    ) -> bool:
        resolved_transport = self.transport if transport is None else _required_text(
            transport,
            "transport",
        )
        required = tuple(
            _required_text(value, "required_probe_check") for value in required_checks
        )
        half_open_token: str | None = None
        with self._locked_health_cache():
            health = self._health_for(endpoint.endpoint_id, transport=resolved_transport)
            now = self._now()
            if health.state == "open" and _parse_time(health.open_until) > now:
                self._append_probe_result(
                    result_sink,
                    endpoint=endpoint,
                    state="open",
                    checked_at=_format_time(now),
                    required_checks=required,
                    checks={},
                    passed=False,
                    failure_kind="circuit_open",
                    excluded_reason="circuit_open",
                )
                return False
            if (
                health.state == "half_open"
                and _parse_time(health.half_open_until) > now
            ):
                self._append_probe_result(
                    result_sink,
                    endpoint=endpoint,
                    state="half_open",
                    checked_at=_format_time(now),
                    required_checks=required,
                    checks={},
                    passed=False,
                    failure_kind="half_open_lease_held",
                    excluded_reason="half_open_lease_held",
                )
                return False
            if health.state in {"open", "half_open"}:
                half_open_token = uuid4().hex
                health.state = "half_open"
                health.half_open_token = half_open_token
                health.half_open_until = _format_time(
                    now + timedelta(seconds=self.circuit_open_seconds)
                )
                self._write_health_cache_unlocked()
        probe_clients: list[Any] = []
        probe_client_ids: set[int] = set()
        probe_close_errors: list[str] = []

        def make_probe_client(profile: str = "std") -> Any:
            make_selection_client = client_factory or create_mootdx_client
            client = make_selection_client(
                self._probe_selection(endpoint, transport=resolved_transport),
                profile,
            )
            if id(client) not in probe_client_ids:
                probe_client_ids.add(id(client))
                probe_clients.append(client)
            return client

        try:
            try:
                summary = dict(
                    probe(
                        endpoint,
                        make_probe_client,
                    )
                )
            except Exception as exc:
                summary = {
                    "checks": {},
                    "failure_kind": "probe_exception",
                    "error_type": type(exc).__name__,
                }
        finally:
            for client in reversed(probe_clients):
                close = getattr(client, "close", None)
                if not callable(close):
                    continue
                try:
                    close()
                except Exception as exc:
                    probe_close_errors.append(type(exc).__name__)
        if probe_close_errors:
            summary["probe_close_errors"] = probe_close_errors
        checks = summary.get("checks")
        passed = (
            isinstance(checks, Mapping)
            and bool(required)
            and all(checks.get(name) is True for name in required)
            and not probe_close_errors
        )
        if probe_close_errors:
            summary["failure_kind"] = "probe_client_close_failed"
        summary["required_checks"] = list(required)
        summary["passed"] = passed
        with self._locked_health_cache():
            health = self._health_for(endpoint.endpoint_id, transport=resolved_transport)
            if half_open_token is not None and health.half_open_token != half_open_token:
                self._append_probe_result(
                    result_sink,
                    endpoint=endpoint,
                    state=health.state,
                    checked_at=_format_time(self._now()),
                    required_checks=required,
                    checks={name: checks.get(name) for name in required}
                    if isinstance(checks, Mapping)
                    else {},
                    passed=False,
                    failure_kind="probe_result_superseded",
                    excluded_reason=None,
                )
                return False
            if half_open_token is None and health.state == "open":
                self._append_probe_result(
                    result_sink,
                    endpoint=endpoint,
                    state="open",
                    checked_at=_format_time(self._now()),
                    required_checks=required,
                    checks={name: checks.get(name) for name in required}
                    if isinstance(checks, Mapping)
                    else {},
                    passed=False,
                    failure_kind="concurrent_transport_failure",
                    excluded_reason=None,
                )
                return False
            health.checked_at = _format_time(now)
            health.probe_summary = summary
            health.half_open_token = None
            health.half_open_until = None
            if passed:
                health.state = "healthy"
                health.open_until = None
                health.consecutive_failures = 0
                health.consecutive_required_empty_objects = 0
                health.consecutive_required_empty_object_ids = []
            else:
                health.consecutive_failures += 1
                if half_open_token is not None or health.state == "degraded":
                    health.state = "open"
                    health.open_until = _format_time(
                        now + timedelta(seconds=self.circuit_open_seconds)
                    )
                else:
                    health.state = "degraded"
                    health.open_until = None
            self._write_health_cache_unlocked()
            result_state = health.state
            result_checked_at = health.checked_at
        self._append_probe_result(
            result_sink,
            endpoint=endpoint,
            state=result_state,
            checked_at=result_checked_at,
            required_checks=required,
            checks={name: checks.get(name) for name in required}
            if isinstance(checks, Mapping)
            else {},
            passed=passed,
            failure_kind=(
                None
                if passed
                else str(summary.get("failure_kind") or "mandatory_probe_failed")
            ),
            excluded_reason=None,
            probe_close_errors=probe_close_errors,
        )
        return passed

    def _append_probe_result(
        self,
        result_sink: list[dict[str, Any]] | None,
        *,
        endpoint: EndpointConfig,
        state: str,
        checked_at: str | None,
        required_checks: Sequence[str],
        checks: Mapping[str, Any],
        passed: bool,
        failure_kind: str | None,
        excluded_reason: str | None,
        probe_close_errors: Sequence[str] = (),
    ) -> None:
        if result_sink is None:
            return
        result_sink.append(
            {
                "endpoint_id": endpoint.endpoint_id,
                "enabled": endpoint.enabled,
                "quarantined": endpoint.quarantined,
                "state": state,
                "checked_at": checked_at,
                "required_checks": list(required_checks),
                "checks": {
                    name: checks.get(name)
                    for name in required_checks
                },
                "passed": passed,
                "failure_kind": failure_kind,
                "excluded_reason": excluded_reason,
                "probe_close_errors": list(probe_close_errors),
            }
        )

    def _excluded_probe_result(
        self,
        endpoint: EndpointConfig,
        *,
        required_checks: Sequence[str],
        state: str,
        failure_kind: str,
        excluded_reason: str,
    ) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        self._append_probe_result(
            rows,
            endpoint=endpoint,
            state=state,
            checked_at=_format_time(self._now()),
            required_checks=required_checks,
            checks={},
            passed=False,
            failure_kind=failure_kind,
            excluded_reason=excluded_reason,
        )
        return rows[0]

    def _probe_selection(
        self,
        endpoint: EndpointConfig,
        *,
        transport: str,
    ) -> EndpointSelection:
        health = self._health_for(endpoint.endpoint_id, transport=transport)
        return EndpointSelection(
            endpoint_pool_version=self.endpoint_pool_version,
            endpoint_id=endpoint.endpoint_id,
            host=endpoint.host,
            port=endpoint.port,
            transport=transport,
            health_state=health.state,
            health_checked_at=health.checked_at,
            probe_summary=dict(health.probe_summary),
            attempt_id=f"preflight_probe__{uuid4().hex}",
            selection_reason="mandatory_protocol_preflight_probe",
            failover_mode="observe",
            selectable=True,
        )

    def _selection(
        self,
        endpoint: EndpointConfig,
        *,
        attempt_id: str,
        mode: str,
        selectable: bool,
        selection_reason: str,
        failover_from: str | None,
        failover_reason: str | None,
        transport: str,
        would_switch_to: str | None = None,
        failover_performed: bool = False,
        endpoint_probe_results: tuple[Mapping[str, Any], ...] = (),
    ) -> EndpointSelection:
        health = self._health_for(endpoint.endpoint_id, transport=transport)
        return EndpointSelection(
            endpoint_pool_version=self.endpoint_pool_version,
            endpoint_id=endpoint.endpoint_id,
            host=endpoint.host,
            port=endpoint.port,
            transport=transport,
            health_state=health.state,
            health_checked_at=health.checked_at,
            probe_summary=dict(health.probe_summary),
            attempt_id=_required_text(attempt_id, "attempt_id"),
            selection_reason=selection_reason,
            failover_mode=mode,
            selectable=selectable,
            failover_from=failover_from,
            failover_reason=failover_reason,
            would_switch_to=would_switch_to,
            failover_performed=failover_performed,
            endpoint_probe_results=endpoint_probe_results,
        )

    def _health_for(self, endpoint_id: str, *, transport: str) -> EndpointHealth:
        if endpoint_id not in {row.endpoint_id for row in self.endpoints}:
            raise MootdxEndpointConfigError(f"unknown endpoint_id: {endpoint_id}")
        resolved_transport = _required_text(transport, "transport")
        key = (resolved_transport, endpoint_id)
        return self._health.setdefault(
            key,
            EndpointHealth(endpoint_id=endpoint_id, transport=resolved_transport),
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise MootdxEndpointConfigError("clock must return a timezone-aware datetime")
        return value.astimezone(timezone.utc)

    def _load_health_cache(self) -> dict[tuple[str, str], EndpointHealth]:
        try:
            raw = json.loads(self.health_cache_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError):
            return {}
        if raw.get("endpoint_pool_version") != self.endpoint_pool_version:
            return {}
        schema_version = raw.get("cache_schema_version")
        if schema_version == HEALTH_CACHE_SCHEMA_V1:
            partitions: Mapping[str, Any] = {"mootdx": raw.get("endpoints")}
        elif schema_version == HEALTH_CACHE_SCHEMA_V2:
            raw_partitions = raw.get("transports")
            if not isinstance(raw_partitions, Mapping):
                return {}
            partitions = raw_partitions
        else:
            return {}
        health: dict[tuple[str, str], EndpointHealth] = {}
        for transport, rows in partitions.items():
            if not isinstance(transport, str) or not transport.strip():
                continue
            if not isinstance(rows, Mapping):
                continue
            for endpoint_id, payload in rows.items():
                if not isinstance(endpoint_id, str) or not isinstance(payload, Mapping):
                    continue
                normalized_payload = dict(payload)
                if schema_version == HEALTH_CACHE_SCHEMA_V1:
                    normalized_payload["transport"] = "mootdx"
                try:
                    row = EndpointHealth(**normalized_payload)
                except TypeError:
                    continue
                if (
                    row.endpoint_id != endpoint_id
                    or row.transport != transport
                    or row.state not in HEALTH_STATES
                ):
                    continue
                health[(transport, endpoint_id)] = row
        return health

    @contextmanager
    def _locked_health_cache(self):
        with _HEALTH_CACHE_THREAD_LOCK, _exclusive_file_lock(self.health_cache_lock_path):
            self._health = self._load_health_cache()
            yield

    def _write_health_cache_unlocked(self) -> None:
        transports: dict[str, dict[str, Any]] = {}
        for (transport, endpoint_id), value in sorted(self._health.items()):
            transports.setdefault(transport, {})[endpoint_id] = asdict(value)
        payload = {
            "cache_schema_version": HEALTH_CACHE_SCHEMA_V2,
            "endpoint_pool_version": self.endpoint_pool_version,
            "written_at": _format_time(self._now()),
            "transports": transports,
        }
        self.health_cache_path.parent.mkdir(parents=True, exist_ok=True)
        fd, raw_path = tempfile.mkstemp(
            prefix=f".{self.health_cache_path.name}.",
            suffix=".tmp",
            dir=self.health_cache_path.parent,
        )
        temp_path = Path(raw_path)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.health_cache_path)
        finally:
            temp_path.unlink(missing_ok=True)


def create_mootdx_client(
    selection: EndpointSelection,
    profile: str = "std",
    *,
    quotes_factory: Callable[..., Any] | None = None,
    lock_path: Path | str = DEFAULT_CLIENT_FACTORY_LOCK_PATH,
) -> Any:
    """Create one explicitly pinned Mootdx client without implicit retries."""

    if not selection.selectable:
        raise MootdxEndpointSelectionError(
            f"endpoint selection is fail-closed: {selection.selection_reason}"
        )
    if selection.transport != "mootdx":
        raise MootdxEndpointSelectionError(f"unsupported transport: {selection.transport}")
    factory = quotes_factory
    if factory is None:
        quotes_module = importlib.import_module("mootdx.quotes")
        factory = quotes_module.Quotes.factory
    with _CLIENT_FACTORY_THREAD_LOCK, _exclusive_file_lock(Path(lock_path).expanduser()):
        client = factory(
            market=_required_text(profile, "profile"),
            server=selection.server,
            timeout=5,
            raise_exception=True,
            auto_retry=False,
            heartbeat=False,
        )
        actual_server = getattr(client, "server", None)
        if tuple(actual_server or ()) != selection.server:
            close = getattr(client, "close", None)
            if callable(close):
                close()
            raise MootdxEndpointSelectionError(
                "Mootdx client server mismatch after factory: "
                f"expected={selection.server!r}, actual={actual_server!r}"
            )
        return client


def build_n1_protocol_probe(
    *,
    scope_kind: str,
    symbols: Sequence[str],
    target_trade_date: str,
    frequency: int = 9,
    start: int = 0,
    offset: int = 800,
) -> Probe:
    """Build the N1 semantic quote/bars/index/scope-sentinel preflight."""

    normalized_scope_kind = _required_text(scope_kind, "scope_kind")
    if normalized_scope_kind not in {"stock", "index", "board"}:
        raise MootdxEndpointConfigError(f"unsupported N1 probe scope_kind: {normalized_scope_kind}")
    normalized_target_date = _normalize_trade_date(target_trade_date)
    if not normalized_target_date:
        raise MootdxEndpointConfigError("target_trade_date must be YYYYMMDD")
    sentinels = _deterministic_sentinels(symbols)

    def probe(endpoint: EndpointConfig, make_client: ProbeClientFactory) -> Mapping[str, Any]:
        del endpoint
        client = make_client("std")
        quote_rows = _frame_to_records(client.quotes(symbol="600000"))
        stock_bar_rows = _frame_to_records_with_requested_symbol(
            client.bars(symbol="600000", frequency=9, start=0, offset=3),
            requested_symbol="600000",
        )
        index_bar_rows = _frame_to_records_with_requested_symbol(
            client.index(symbol="000001", frequency=9, start=0, offset=3),
            requested_symbol="000001",
        )
        sentinel_results: dict[str, bool] = {}
        for symbol in sentinels:
            if normalized_scope_kind == "stock":
                raw = client.bars(
                    symbol=symbol,
                    frequency=frequency,
                    start=start,
                    offset=offset,
                )
            else:
                raw = client.index(
                    symbol=symbol,
                    frequency=frequency,
                    start=start,
                    offset=offset,
                )
            rows = _frame_to_records_with_requested_symbol(
                raw,
                requested_symbol=symbol,
            )
            sentinel_results[symbol] = any(
                _row_trade_date(row) == normalized_target_date for row in rows
            ) and _valid_daily_bars(
                rows,
                expected_code=symbol,
                exact_count=None,
            )
        checks = {
            "stock_quote": _valid_stock_quote(quote_rows, expected_code="600000"),
            "stock_daily_bars": _valid_daily_bars(
                stock_bar_rows,
                expected_code="600000",
                exact_count=3,
            ),
            "index_daily_bars": _valid_daily_bars(
                index_bar_rows,
                expected_code="000001",
                exact_count=None,
            ),
            "scope_sentinels": bool(sentinel_results) and all(sentinel_results.values()),
        }
        return {
            "checks": checks,
            "scope_kind": normalized_scope_kind,
            "target_trade_date": normalized_target_date,
            "quote_row_count": len(quote_rows),
            "stock_daily_row_count": len(stock_bar_rows),
            "index_daily_row_count": len(index_bar_rows),
            "sentinel_symbols": list(sentinels),
            "sentinel_results": sentinel_results,
        }

    return probe


def _validate_endpoints(endpoints: Sequence[EndpointConfig]) -> None:
    if not endpoints:
        raise MootdxEndpointConfigError("endpoint pool must not be empty")
    endpoint_ids: set[str] = set()
    servers: set[tuple[str, int]] = set()
    priorities: set[int] = set()
    for endpoint in endpoints:
        endpoint_id = _required_text(endpoint.endpoint_id, "endpoint_id")
        try:
            ipaddress.ip_address(endpoint.host)
        except ValueError as exc:
            raise MootdxEndpointConfigError(f"endpoint host must be an IP address: {endpoint.host}") from exc
        port = _positive_int(endpoint.port, f"{endpoint_id}.port")
        priority = _positive_int(endpoint.priority, f"{endpoint_id}.priority")
        if endpoint_id in endpoint_ids:
            raise MootdxEndpointConfigError(f"duplicate endpoint_id: {endpoint_id}")
        if (endpoint.host, port) in servers:
            raise MootdxEndpointConfigError(f"duplicate endpoint server: {endpoint.host}:{port}")
        if priority in priorities:
            raise MootdxEndpointConfigError(f"duplicate endpoint priority: {priority}")
        if endpoint.enabled and endpoint.quarantined:
            raise MootdxEndpointConfigError(f"quarantined endpoint cannot be enabled: {endpoint_id}")
        if endpoint.enabled and endpoint.local_validation_status != "protocol_passed":
            raise MootdxEndpointConfigError(
                f"enabled endpoint must have local_validation_status=protocol_passed: {endpoint_id}"
            )
        _required_text(endpoint.provenance_url, f"{endpoint_id}.provenance_url")
        _required_text(endpoint.provenance_commit, f"{endpoint_id}.provenance_commit")
        _required_text(endpoint.local_validation_status, f"{endpoint_id}.local_validation_status")
        endpoint_ids.add(endpoint_id)
        servers.add((endpoint.host, port))
        priorities.add(priority)


def _required_text(value: Any, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise MootdxEndpointConfigError(f"{field_name} is required")
    return normalized


def _positive_int(value: Any, field_name: str) -> int:
    normalized = int(value)
    if normalized <= 0:
        raise MootdxEndpointConfigError(f"{field_name} must be positive")
    return normalized


def _validate_mode(value: Any, field_name: str) -> str:
    normalized = _required_text(value, field_name)
    if normalized not in FAILOVER_MODES:
        raise MootdxEndpointConfigError(f"{field_name} must be one of {sorted(FAILOVER_MODES)}")
    return normalized


def _deep_freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): _deep_freeze_json(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze_json(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise MootdxEndpointConfigError(
        f"endpoint provenance must be JSON-safe, got {type(value).__name__}"
    )


def _deep_thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _deep_thaw_json(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_deep_thaw_json(item) for item in value]
    return value


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@contextmanager
def _exclusive_file_lock(path: Path):
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _frame_to_records(frame: Any) -> list[dict[str, Any]]:
    if frame is None or frame is False:
        return []
    if hasattr(frame, "to_dict"):
        try:
            rows = frame.to_dict(orient="records")
        except TypeError:
            rows = frame.to_dict("records")
        return [dict(row) for row in rows]
    if isinstance(frame, Mapping):
        return [dict(frame)]
    if isinstance(frame, Sequence) and not isinstance(frame, (str, bytes)):
        return [dict(row) for row in frame]
    return []


def _frame_to_records_with_requested_symbol(
    frame: Any,
    *,
    requested_symbol: str,
) -> list[dict[str, Any]]:
    """Copy records and attach explicit identity only when both fields are absent."""

    rows = _frame_to_records(frame)
    for row in rows:
        code = str(row.get("code") or "").strip()
        symbol = str(row.get("symbol") or "").strip()
        if not code and not symbol:
            row["code"] = requested_symbol
    return rows


def _deterministic_sentinels(symbols: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(str(symbol).strip() for symbol in symbols if str(symbol).strip()))
    if not normalized:
        return ()
    return tuple(dict.fromkeys((normalized[0], normalized[len(normalized) // 2], normalized[-1])))


def _valid_stock_quote(rows: Sequence[Mapping[str, Any]], *, expected_code: str) -> bool:
    for row in rows:
        code = str(row.get("code") or row.get("symbol") or "").strip()
        if code != expected_code:
            continue
        for field_name in ("price", "last_price", "close"):
            if _positive_decimal(row.get(field_name)):
                return True
    return False


def _valid_daily_bars(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_code: str,
    exact_count: int | None,
) -> bool:
    if not rows or (exact_count is not None and len(rows) != exact_count):
        return False
    dates: list[str] = []
    for row in rows:
        code = str(row.get("code") or "").strip()
        symbol = str(row.get("symbol") or "").strip()
        identities = [value for value in (code, symbol) if value]
        if not identities or any(value != expected_code for value in identities):
            return False
        trade_date = _row_trade_date(row)
        if not trade_date or not _valid_ohlc(row):
            return False
        dates.append(trade_date)
    return dates == sorted(dates) and len(dates) == len(set(dates))


def _valid_ohlc(row: Mapping[str, Any]) -> bool:
    try:
        open_price = Decimal(str(row.get("open")))
        high_price = Decimal(str(row.get("high")))
        low_price = Decimal(str(row.get("low")))
        close_price = Decimal(str(row.get("close")))
    except (InvalidOperation, TypeError, ValueError):
        return False
    if min(open_price, high_price, low_price, close_price) <= 0:
        return False
    if high_price < max(open_price, close_price, low_price):
        return False
    if low_price > min(open_price, close_price, high_price):
        return False
    for field_name in ("vol", "volume", "amount"):
        if field_name in row:
            try:
                if Decimal(str(row[field_name])) < 0:
                    return False
            except (InvalidOperation, TypeError, ValueError):
                return False
    return True


def _row_trade_date(row: Mapping[str, Any]) -> str:
    for field_name in ("trade_date", "datetime", "date"):
        normalized = _normalize_trade_date(row.get(field_name))
        if normalized:
            return normalized
    return ""


def _normalize_trade_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    text = str(value or "").strip()
    digits = "".join(character for character in text[:10] if character.isdigit())
    return digits if len(digits) == 8 else ""


def _positive_decimal(value: Any) -> bool:
    try:
        return Decimal(str(value)) > 0
    except (InvalidOperation, TypeError, ValueError):
        return False
