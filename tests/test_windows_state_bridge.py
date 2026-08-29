from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import socket
from types import MappingProxyType, SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import pytest

from ashare_v3.runtime_control.windows_n3_n4_n5_memory import (
    WindowsStateBridgeSnapshot,
)
from ashare_v3.runtime_control.windows_state_bridge import WindowsStateBridge


@dataclass(frozen=True)
class _Direction:
    direction: str
    trigger_live: bool
    current_status: str
    source_n4_version: int


@dataclass(frozen=True)
class _EpisodeKey:
    identity_key: str


@dataclass(frozen=True)
class _Episode:
    direction: str
    code: str
    trigger_live: bool
    live_status: str
    action_state: str = "eligible"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _snapshot(version: int = 7) -> WindowsStateBridgeSnapshot:
    identities = {
        "stock": "stock:SZ:000001",
        "index": "index:SH:000001",
        "board": "board:SH:881333",
    }
    n4_memory = {}
    n4_states = {}
    n5_episodes = {}
    for kind, identity in identities.items():
        code = identity.rsplit(":", 1)[-1]
        n4_memory[kind] = SimpleNamespace(
            states={identity: SimpleNamespace(live_status="available")}
        )
        n4_states[kind] = SimpleNamespace(
            source_n4_version=version,
            states={
                identity: SimpleNamespace(
                    exchange=identity.split(":")[1],
                    code=code,
                    name=f"{kind}-fixture",
                    buy=_Direction("buy", True, "matched", version),
                    sell=_Direction("sell", False, "inactive", version),
                )
            },
        )
        key = _EpisodeKey(identity)
        runtime = _Episode("buy", code, True, "available")
        n5_episodes[kind] = SimpleNamespace(
            version=version,
            active=MappingProxyType({key: object()}),
            runtime_states=MappingProxyType({key: runtime}),
        )
    return WindowsStateBridgeSnapshot(
        generated_at=datetime.now(timezone.utc),
        n4_memory=n4_memory,
        n4_states=n4_states,
        n5_episodes=n5_episodes,
    )


def _get(port: int, path: str):
    with urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as response:
        return response, json.load(response)


def test_health_three_channels_filters_pagination_and_read_only() -> None:
    holder = {"snapshot": _snapshot()}
    before = holder["snapshot"]
    port = _free_port()
    with WindowsStateBridge(lambda: holder["snapshot"], port=port):
        response, health = _get(port, "/internal/v1/health")
        assert response.headers["Cache-Control"] == "no-store"
        assert health == {"read_only": True, "status": "ok"}

        _, first = _get(port, "/internal/v1/n4/states?limit=2")
        assert first["count"] == 2
        assert first["snapshot_version"] == "n4:7:7:7"
        assert first["next_cursor"]
        _, second = _get(
            port,
            "/internal/v1/n4/states?limit=2&cursor=" + first["next_cursor"],
        )
        assert second["snapshot_version"] == first["snapshot_version"]

        _, live = _get(
            port,
            "/internal/v1/n4/states?asset_kind=board&code=881333"
            "&direction=buy&live_status=available&trigger_live=true",
        )
        assert [(row["asset_kind"], row["direction"]) for row in live["items"]] == [
            ("board", "buy")
        ]

        _, episodes = _get(port, "/internal/v1/n5/episodes")
        assert {row["asset_kind"] for row in episodes["items"]} == {
            "stock",
            "index",
            "board",
        }
        assert all(row["action_state"] == "eligible" for row in episodes["items"])
        assert holder["snapshot"] is before


def test_cursor_rejects_a_new_snapshot_version() -> None:
    holder = {"snapshot": _snapshot()}
    port = _free_port()
    with WindowsStateBridge(lambda: holder["snapshot"], port=port):
        _, first = _get(port, "/internal/v1/n4/states?limit=1")
        holder["snapshot"] = _snapshot(version=8)
        with pytest.raises(HTTPError) as error:
            _get(
                port,
                "/internal/v1/n4/states?limit=1&cursor=" + first["next_cursor"],
            )
        assert error.value.code == 400


def test_loopback_only_startup_failure_and_shutdown() -> None:
    with pytest.raises(ValueError, match="127.0.0.1"):
        WindowsStateBridge(_snapshot, host="0.0.0.0", port=_free_port())

    port = _free_port()
    bridge = WindowsStateBridge(_snapshot, port=port).start()
    assert bridge.server_address == ("127.0.0.1", port)
    bridge.shutdown()
    with pytest.raises(URLError):
        _get(port, "/internal/v1/health")

    blocker = socket.socket()
    blocker.bind(("127.0.0.1", port))
    blocker.listen()
    try:
        with pytest.raises(OSError):
            WindowsStateBridge(_snapshot, port=port)
    finally:
        blocker.close()
