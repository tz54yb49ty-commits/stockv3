from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import socket
from types import MappingProxyType, SimpleNamespace
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from jinja2 import Environment, FileSystemLoader, select_autoescape
import pytest

from ashare_v3.runtime_control.windows_n3_n4_n5_memory import (
    WindowsStateBridgeSnapshot,
)
from ashare_v3.runtime_control.windows_state_bridge import WindowsStateBridge
from ashare_v3.web.windows_n6_runtime import (
    HttpWindowsRuntimeBridge,
    read_runtime_page,
)


@dataclass(frozen=True)
class _Direction:
    direction: str
    trigger_live: bool
    current_status: str
    source_n4_version: int
    rule_flags: Mapping[str, bool | None]


@dataclass(frozen=True)
class _RuntimeState:
    source_transitions: Mapping[str, str]
    source_amounts: Mapping[str, Decimal | None]
    comparison_amounts: Mapping[str, Decimal | None]
    realtime_transitions: Mapping[str, str | None]
    realtime_virtual_amounts: Mapping[str, Decimal | None]
    current_price: Decimal | None
    cumulative_amount: Decimal | None
    observed_at: datetime | None
    provider: str | None
    live_status: str
    fresh: bool


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


def _snapshot(
    version: int = 7,
    quality_by_kind: Mapping[str, tuple[str, bool]] | None = None,
) -> WindowsStateBridgeSnapshot:
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
        live_status, fresh = (quality_by_kind or {}).get(
            kind,
            ("available", True),
        )
        n4_memory[kind] = SimpleNamespace(
            version=version,
            states={
                identity: _RuntimeState(
                    source_transitions={"D": "flat", "W": "volume_up"},
                    source_amounts={"D": Decimal("1000000")},
                    comparison_amounts={"W": Decimal("900000")},
                    realtime_transitions={"D": "volume_up", "30m": "none"},
                    realtime_virtual_amounts={"D": Decimal("1100000")},
                    current_price=Decimal("10.25"),
                    cumulative_amount=Decimal("800000"),
                    observed_at=datetime(
                        2026,
                        8,
                        31,
                        9,
                        35,
                        tzinfo=timezone.utc,
                    ),
                    provider=f"{kind}.fixture",
                    live_status=live_status,
                    fresh=fresh,
                )
            },
        )
        n4_states[kind] = SimpleNamespace(
            source_n4_version=version,
            states={
                identity: SimpleNamespace(
                    exchange=identity.split(":")[1],
                    code=code,
                    name=f"{kind}-fixture",
                    buy=_Direction(
                        "buy",
                        True,
                        "matched",
                        version,
                        {"A": True, "B": False},
                    ),
                    sell=_Direction(
                        "sell",
                        False,
                        "inactive",
                        version,
                        {"C": False, "D30": False},
                    ),
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
            "&direction=BUY&live_status=available&trigger_live=true",
        )
        assert [(row["asset_kind"], row["direction"]) for row in live["items"]] == [
            ("board", "BUY")
        ]
        row = live["items"][0]
        assert row["identity"] == row["identity_key"] == "board:SH:881333"
        assert row["source_transitions"] == {"D": "flat", "W": "volume_up"}
        assert row["source_amounts"] == {"D": "1000000"}
        assert row["comparison_amounts"] == {"W": "900000"}
        assert row["realtime_transitions"] == {
            "30m": "none",
            "D": "volume_up",
        }
        assert row["realtime_virtual_amounts"] == {"D": "1100000"}
        assert row["current_price"] == "10.25"
        assert row["cumulative_amount"] == "800000"
        assert row["provider"] == "board.fixture"
        assert row["fresh"] is True
        assert row["n4_state_version"] == 7
        assert row["updated_at"] == "2026-08-31T09:35:00+00:00"

        _, episodes = _get(port, "/internal/v1/n5/episodes")
        assert {row["asset_kind"] for row in episodes["items"]} == {
            "stock",
            "index",
            "board",
        }
        assert all(row["action_state"] == "eligible" for row in episodes["items"])
        for limit in (10, 100):
            _, n4_page = _get(port, f"/internal/v1/n4/states?limit={limit}")
            _, n5_page = _get(port, f"/internal/v1/n5/episodes?limit={limit}")
            assert n4_page["count"] == 6
            assert n5_page["count"] == 3
        assert holder["snapshot"] is before


def test_n4_three_channel_quality_and_real_bridge_template_render() -> None:
    holder = {
        "snapshot": _snapshot(
            quality_by_kind={
                "stock": ("available", True),
                "index": ("stale", False),
                "board": ("unavailable", False),
            }
        )
    }
    port = _free_port()
    with WindowsStateBridge(lambda: holder["snapshot"], port=port):
        page = read_runtime_page(
            HttpWindowsRuntimeBridge(
                base_url=f"http://127.0.0.1:{port}",
                timeout_seconds=2,
            ),
            "n4",
            {"limit": 6},
        )

    assert page["runtime_status"] == "online"
    assert page["item_count"] == 6
    assert {
        (row["asset_kind"], row["live_status"], row["fresh"])
        for row in page["items"]
    } == {
        ("stock", "available", True),
        ("index", "stale", False),
        ("board", "unavailable", False),
    }
    required = {
        "identity",
        "identity_key",
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
        "updated_at",
        "n4_state_version",
        "rule_flags",
    }
    assert all(required.issubset(row) for row in page["items"])

    root = Path(__file__).resolve().parents[1]
    environment = Environment(
        loader=FileSystemLoader(root / "src/ashare_v3/web/templates"),
        autoescape=select_autoescape(("html",)),
    )
    rendered = environment.get_template(
        "n6_windows_runtime_states.html"
    ).render(
        title="N4 runtime states",
        layer="n4",
        page=page,
        filters={},
        nav={"links": (), "active": "n4_runtime_states", "is_admin": True},
    )
    assert "stock:SZ:000001" in rendered
    assert "board:SH:881333" in rendered
    assert "runtime_offline" not in rendered


def test_n4_missing_runtime_state_emits_explicit_null_fields() -> None:
    snapshot = _snapshot()
    snapshot.n4_memory["board"].states.clear()
    port = _free_port()
    with WindowsStateBridge(lambda: snapshot, port=port):
        _, page = _get(
            port,
            "/internal/v1/n4/states?asset_kind=board&direction=BUY",
        )

    assert page["count"] == 1
    row = page["items"][0]
    for name in (
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
        "updated_at",
    ):
        assert name in row
        assert row[name] is None


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
