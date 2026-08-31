"""Loopback-only, read-only HTTP projection of Windows N4/N5 memory state."""

from __future__ import annotations

import base64
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from types import MappingProxyType
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from ashare_v3.runtime_control.windows_n3_n4_n5_memory import (
    ASSET_KINDS,
    WindowsStateBridgeSnapshot,
)


LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 8796
MAX_LIMIT = 1000


class WindowsStateBridge:
    """Own a loopback server whose lifetime is bounded by this process."""

    def __init__(
        self,
        snapshot_reader: Callable[[], WindowsStateBridgeSnapshot],
        *,
        host: str = LOOPBACK_HOST,
        port: int = DEFAULT_PORT,
    ) -> None:
        if host != LOOPBACK_HOST:
            raise ValueError("state bridge host must be 127.0.0.1")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("state bridge port must be between 1 and 65535")
        self._snapshot_reader = snapshot_reader
        handler = _handler_factory(snapshot_reader)
        self._server = ThreadingHTTPServer((host, port), handler)
        self._server.daemon_threads = True
        self._thread = Thread(
            target=self._server.serve_forever,
            name="windows-state-bridge",
            daemon=True,
        )
        self._started = False

    @property
    def server_address(self) -> tuple[str, int]:
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    def start(self) -> WindowsStateBridge:
        if not self._started:
            self._thread.start()
            self._started = True
        return self

    def shutdown(self) -> None:
        if self._started:
            self._server.shutdown()
            self._thread.join(timeout=5)
            self._started = False
        self._server.server_close()

    def __enter__(self) -> WindowsStateBridge:
        return self.start()

    def __exit__(self, *_args: object) -> None:
        self.shutdown()


def _handler_factory(snapshot_reader):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            try:
                path = urlsplit(self.path)
                if path.path == "/internal/v1/health":
                    self._send(HTTPStatus.OK, {"status": "ok", "read_only": True})
                    return
                if path.path not in {
                    "/internal/v1/n4/states",
                    "/internal/v1/n5/episodes",
                }:
                    self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                    return
                query = parse_qs(path.query, keep_blank_values=True)
                snapshot = snapshot_reader()
                if path.path.endswith("/states"):
                    rows, version = _n4_rows(snapshot)
                else:
                    rows, version = _n5_rows(snapshot)
                payload = _page(rows, version, query)
                self._send(HTTPStatus.OK, payload)
            except (ValueError, RuntimeError) as error:
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            except Exception:
                self._send(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": "state_bridge_internal_error"},
                )

        def do_HEAD(self) -> None:  # noqa: N802 - explicitly disallowed
            self._send(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"})

        def do_POST(self) -> None:  # noqa: N802 - explicitly disallowed
            self._send(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"})

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _send(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

    return Handler


def _n4_rows(snapshot: WindowsStateBridgeSnapshot):
    rows = []
    versions = {}
    for kind in ASSET_KINDS:
        lifecycle = snapshot.n4_states[kind]
        runtime_snapshot = snapshot.n4_memory[kind]
        versions[kind] = lifecycle.source_n4_version
        for identity_key, state in lifecycle.states.items():
            runtime_state = runtime_snapshot.states.get(identity_key)
            for direction in ("buy", "sell"):
                value = getattr(state, direction)
                row = _n4_runtime_projection(
                    runtime_state,
                    runtime_snapshot=runtime_snapshot,
                    identity_key=identity_key,
                )
                row.update(_json_value(value))
                row.update(
                    asset_kind=kind,
                    identity=identity_key,
                    identity_key=identity_key,
                    exchange=state.exchange,
                    code=state.code,
                    name=state.name,
                    direction=str(value.direction).upper(),
                    n4_state_version=value.source_n4_version,
                )
                rows.append(row)
    return rows, _version("n4", versions)


def _n4_runtime_projection(
    runtime_state: Any,
    *,
    runtime_snapshot: Any,
    identity_key: str,
) -> dict[str, Any]:
    field_names = (
        "source_transitions",
        "source_amounts",
        "comparison_amounts",
        "realtime_transitions",
        "realtime_virtual_amounts",
        "current_price",
        "cumulative_amount",
        "provider",
        "live_status",
        "fresh",
    )
    row = {
        name: _json_value(getattr(runtime_state, name, None))
        for name in field_names
    }
    row.update(
        identity=identity_key,
        identity_key=identity_key,
        n4_state_version=runtime_snapshot.version,
        updated_at=_json_value(getattr(runtime_state, "observed_at", None)),
    )
    return row


def _n5_rows(snapshot: WindowsStateBridgeSnapshot):
    rows = []
    versions = {}
    for kind in ASSET_KINDS:
        value = snapshot.n5_episodes[kind]
        versions[kind] = value.version
        for key in value.active:
            row = _json_value(value.runtime_states[key])
            row["asset_kind"] = kind
            row["identity_key"] = key.identity_key
            rows.append(row)
    return rows, _version("n5", versions)


def _version(prefix: str, versions: dict[str, int]) -> str:
    return prefix + ":" + ":".join(str(versions[kind]) for kind in ASSET_KINDS)


def _page(rows, version: str, query: dict[str, list[str]]):
    allowed = {"asset_kind", "code", "direction", "live_status", "trigger_live", "cursor", "limit"}
    unknown = set(query).difference(allowed)
    if unknown:
        raise ValueError(f"unsupported query parameter: {sorted(unknown)[0]}")
    filtered = sorted(rows, key=lambda row: (row["asset_kind"], row["identity_key"], row["direction"]))
    for name in ("asset_kind", "code", "direction", "live_status"):
        if name in query:
            expected = _one(query, name)
            filtered = [row for row in filtered if str(row.get(name)) == expected]
    if "trigger_live" in query:
        raw = _one(query, "trigger_live").lower()
        if raw not in {"true", "false"}:
            raise ValueError("trigger_live must be true or false")
        expected = raw == "true"
        filtered = [row for row in filtered if row.get("trigger_live") is expected]
    limit = int(_one(query, "limit")) if "limit" in query else 100
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    offset = 0
    if "cursor" in query:
        cursor_version, offset = _decode_cursor(_one(query, "cursor"))
        if cursor_version != version:
            raise ValueError("cursor snapshot version is stale")
    page = filtered[offset : offset + limit]
    next_offset = offset + len(page)
    return {
        "snapshot_version": version,
        "items": page,
        "count": len(page),
        "next_cursor": (
            _encode_cursor(version, next_offset)
            if next_offset < len(filtered)
            else None
        ),
    }


def _one(query: dict[str, list[str]], name: str) -> str:
    values = query[name]
    if len(values) != 1 or values[0] == "":
        raise ValueError(f"{name} must have exactly one non-empty value")
    return values[0]


def _encode_cursor(version: str, offset: int) -> str:
    raw = json.dumps([version, offset], separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[str, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        version, offset = json.loads(raw)
    except Exception as error:
        raise ValueError("invalid cursor") from error
    if not isinstance(version, str) or type(offset) is not int or offset < 0:
        raise ValueError("invalid cursor")
    return version, offset


def _json_value(value: Any) -> Any:
    if is_dataclass(value):
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, (MappingProxyType, dict)):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value
