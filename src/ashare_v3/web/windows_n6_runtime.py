"""Windows-only read boundary for N4/N5 in-memory runtime state.

The production implementation talks only to the loopback bridge exposed by the
N3/N4/N5 process.  It never falls back to database rows or cached state.  The
fixture implementation is intentionally process-local and explicitly marked as
simulated.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


RUNTIME_OFFLINE = "runtime_offline"
SIMULATION_LABEL = "SIMULATED / NOT PRODUCTION"


class WindowsRuntimeBridge(Protocol):
    def health(self) -> Mapping[str, Any]: ...

    def n4_states(self, query: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def n5_episodes(self, query: Mapping[str, Any]) -> Mapping[str, Any]: ...


class WindowsRuntimeBridgeError(RuntimeError):
    """The loopback runtime bridge did not return a usable immutable page."""


@dataclass(frozen=True)
class HttpWindowsRuntimeBridge:
    base_url: str = "http://127.0.0.1:8791"
    timeout_seconds: float = 1.0

    def health(self) -> Mapping[str, Any]:
        return self._get("/internal/v1/health", {})

    def n4_states(self, query: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._get("/internal/v1/n4/states", query)

    def n5_episodes(self, query: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._get("/internal/v1/n5/episodes", query)

    def _get(self, path: str, query: Mapping[str, Any]) -> Mapping[str, Any]:
        params = {key: value for key, value in query.items() if value not in (None, "")}
        suffix = f"?{urlencode(params)}" if params else ""
        request = Request(f"{self.base_url.rstrip('/')}{path}{suffix}", method="GET")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, HTTPError, URLError, ValueError, json.JSONDecodeError) as exc:
            raise WindowsRuntimeBridgeError(RUNTIME_OFFLINE) from exc
        if not isinstance(payload, dict):
            raise WindowsRuntimeBridgeError("invalid_runtime_bridge_payload")
        return payload


class OfflineWindowsRuntimeBridge:
    def health(self) -> Mapping[str, Any]:
        raise WindowsRuntimeBridgeError(RUNTIME_OFFLINE)

    def n4_states(self, query: Mapping[str, Any]) -> Mapping[str, Any]:
        raise WindowsRuntimeBridgeError(RUNTIME_OFFLINE)

    def n5_episodes(self, query: Mapping[str, Any]) -> Mapping[str, Any]:
        raise WindowsRuntimeBridgeError(RUNTIME_OFFLINE)


class InMemoryWindowsRuntimeFixture:
    """Small offline fixture for browser acceptance; it has no persistence."""

    def __init__(self) -> None:
        self.database_connection_count = 0
        self.database_write_count = 0
        self.outbox_write_count = 0
        self._n4 = _fixture_n4_states()
        self._n5 = _fixture_n5_episodes()

    def health(self) -> Mapping[str, Any]:
        return {
            "ok": True,
            "runtime_status": "online",
            "mode": "fixture",
            "simulation": True,
            "simulation_label": SIMULATION_LABEL,
            "for_trade_date": "20260831",
            "source_trade_date": "20260828",
            "source_condition_run_id": "fixture_condition_20260828_to_20260831",
            "context_version": "pretrade_c2f55d9_v1",
            "coverage": {"expected": 6082, "ready": 6076, "missing": 6, "ratio": 0.0009865},
            "n4_versions": {"stock": 12, "index": 12, "board": 12},
            "n5_versions": {"stock": 4, "index": 2, "board": 3},
            "tasks": [
                {"name": "AshareV3-N1-Fastlane-1630", "time": "16:30", "state": "Ready"},
                {"name": "AshareV3-N2-N3-PostClose-1635", "time": "16:35", "state": "Ready"},
                {"name": "AshareV3-N3-N4-Memory-0915", "time": "09:15", "state": "Ready"},
            ],
            "database_connection_count": self.database_connection_count,
            "database_write_count": self.database_write_count,
            "outbox_write_count": self.outbox_write_count,
        }

    def n4_states(self, query: Mapping[str, Any]) -> Mapping[str, Any]:
        return _fixture_page(self._n4, query, layer="n4", version=12)

    def n5_episodes(self, query: Mapping[str, Any]) -> Mapping[str, Any]:
        active = [row for row in self._n5 if row.get("trigger_live") is True]
        return _fixture_page(active, query, layer="n5", version=4)


def read_runtime_health(bridge: WindowsRuntimeBridge) -> dict[str, Any]:
    try:
        payload = dict(bridge.health())
    except WindowsRuntimeBridgeError:
        return _offline_health()
    if not bool(payload.get("ok", True)):
        return _offline_health()
    payload.setdefault("runtime_status", "online")
    payload.setdefault("simulation", False)
    return payload


def read_runtime_page(
    bridge: WindowsRuntimeBridge,
    layer: str,
    query: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        payload = dict(
            bridge.n4_states(query or {})
            if layer == "n4"
            else bridge.n5_episodes(query or {})
        )
    except WindowsRuntimeBridgeError:
        return _offline_page(layer)
    items = payload.get("items")
    if not isinstance(items, list):
        return _offline_page(layer, reason="invalid_runtime_bridge_payload")
    payload.setdefault("ok", True)
    payload.setdefault("layer", layer)
    payload.setdefault("runtime_status", "online")
    payload.setdefault("simulation", False)
    payload.setdefault("items", items)
    payload.setdefault("item_count", len(items))
    return payload


def windows_postclose_status(bridge: WindowsRuntimeBridge) -> dict[str, Any]:
    health = read_runtime_health(bridge)
    return {
        "title": "Windows N1–N4 收盘与盘前状态",
        "runtime_status": health.get("runtime_status", RUNTIME_OFFLINE),
        "simulation": bool(health.get("simulation")),
        "simulation_label": health.get("simulation_label", ""),
        "timeline": [
            {"time": "16:30", "stage": "N1", "description": "日增量与完成标记"},
            {"time": "16:35", "stage": "N2/N3", "description": "下一交易日N2与压缩分钟上下文"},
            {"time": "09:15", "stage": "N4", "description": "加载上下文并建立warming内存状态"},
        ],
        "tasks": list(health.get("tasks") or []),
        "source_trade_date": health.get("source_trade_date"),
        "for_trade_date": health.get("for_trade_date"),
        "source_condition_run_id": health.get("source_condition_run_id"),
        "context_version": health.get("context_version"),
        "coverage": dict(health.get("coverage") or {}),
        "n4_versions": dict(health.get("n4_versions") or {}),
        "notice": "N4实时分级只在交易时段产生；盘后完成的是下一交易日启动准备。",
    }


def windows_archive_status(bridge: WindowsRuntimeBridge) -> dict[str, Any]:
    health = read_runtime_health(bridge)
    return {
        "title": "Windows N3压缩上下文状态",
        "runtime_status": health.get("runtime_status", RUNTIME_OFFLINE),
        "simulation": bool(health.get("simulation")),
        "simulation_label": health.get("simulation_label", ""),
        "source_trade_date": health.get("source_trade_date"),
        "for_trade_date": health.get("for_trade_date"),
        "source_condition_run_id": health.get("source_condition_run_id"),
        "context_version": health.get("context_version"),
        "coverage": dict(health.get("coverage") or {}),
        "retention": "每对象一行压缩上下文：240点累计金额 + 8个30分钟窗口",
        "runtime_retention": "N4/N5盘中状态不持久化；进程重启后从N2/N3和当日Outbox恢复。",
        "actions_allowed": False,
    }


def _offline_health() -> dict[str, Any]:
    return {
        "ok": False,
        "runtime_status": RUNTIME_OFFLINE,
        "simulation": False,
        "reason": "loopback_runtime_unavailable",
    }


def _offline_page(layer: str, *, reason: str = "loopback_runtime_unavailable") -> dict[str, Any]:
    return {
        "ok": False,
        "layer": layer,
        "runtime_status": RUNTIME_OFFLINE,
        "simulation": False,
        "reason": reason,
        "version": None,
        "items": [],
        "item_count": 0,
        "next_cursor": None,
    }


def _fixture_page(rows: list[dict[str, Any]], query: Mapping[str, Any], *, layer: str, version: int) -> dict[str, Any]:
    selected = list(rows)
    for key in ("asset_kind", "direction", "live_status"):
        value = str(query.get(key) or "").strip()
        if value:
            selected = [row for row in selected if str(row.get(key) or "") == value]
    identity = str(query.get("identity") or "").strip().lower()
    if identity:
        selected = [
            row for row in selected
            if identity in str(row.get("identity") or "").lower()
            or identity in str(row.get("code") or "").lower()
        ]
    trigger_live = str(query.get("trigger_live") or "").strip().lower()
    if trigger_live in {"true", "false"}:
        expected = trigger_live == "true"
        selected = [row for row in selected if row.get("trigger_live") is expected]
    limit = max(1, min(int(query.get("limit") or 100), 500))
    offset = max(0, int(query.get("cursor") or 0))
    page = selected[offset : offset + limit]
    next_cursor = str(offset + limit) if offset + limit < len(selected) else None
    return {
        "ok": True,
        "layer": layer,
        "runtime_status": "online",
        "simulation": True,
        "simulation_label": SIMULATION_LABEL,
        "for_trade_date": "20260831",
        "source_trade_date": "20260828",
        "source_condition_run_id": "fixture_condition_20260828_to_20260831",
        "version": version,
        "generated_at": "2026-08-31T09:35:05+08:00",
        "total_count": len(selected),
        "item_count": len(page),
        "items": page,
        "next_cursor": next_cursor,
    }


def _fixture_n4_states() -> list[dict[str, Any]]:
    common = {
        "source_trade_date": "20260828",
        "for_trade_date": "20260831",
        "source_condition_run_id": "fixture_condition_20260828_to_20260831",
        "source_transitions": {"D": "low_volume_down", "W": "flat", "M": "flat", "Q": "flat", "Y": "flat"},
        "source_amounts": {"D": 8.2e8, "W": 9.5e8, "M": 8.9e8, "Q": 8.4e8, "Y": 7.8e8},
        "comparison_amounts": {"30m": 1.2e8, "D": 8.2e8, "W": 9.5e8, "M": 8.9e8, "Q": 8.4e8, "Y": 7.8e8},
        "realtime_virtual_amounts": {"30m": 1.5e8, "D": 9.1e8, "W": 1.02e9, "M": 9.6e8, "Q": 9.1e8, "Y": 8.5e8},
        "realtime_transitions": {"30m": "volume_up", "D": "volume_up", "W": "volume_up", "M": "flat", "Q": "flat", "Y": "flat"},
        "provider": "fixture",
        "updated_at": "2026-08-31T09:35:05+08:00",
        "n4_state_version": 12,
    }
    return [
        {**common, "asset_kind": "stock", "identity": "stock:SZ:000001", "code": "000001", "name": "平安银行", "direction": "BUY", "current_price": 12.35, "cumulative_amount": 2.3e8, "rule_flags": {"A": True, "B": False, "C": False, "D30": False}, "trigger_live": True, "live_status": "available", "fresh": True},
        {**common, "asset_kind": "index", "identity": "index:SH:000001", "code": "000001", "name": "上证指数", "direction": "SELL", "current_price": 3956.57, "cumulative_amount": 3.1e11, "rule_flags": {"A": False, "B": False, "C": True, "D30": False}, "trigger_live": True, "live_status": "stale", "fresh": False},
        {**common, "asset_kind": "board", "identity": "board:SH:881333", "code": "881333", "name": "元器件", "direction": None, "current_price": None, "cumulative_amount": None, "rule_flags": {"A": False, "B": False, "C": False, "D30": False}, "trigger_live": False, "live_status": "unavailable", "fresh": False},
    ]


def _fixture_n5_episodes() -> list[dict[str, Any]]:
    return [
        {"asset_kind": "stock", "identity": "stock:SZ:000001", "code": "000001", "name": "平安银行", "direction": "BUY", "signal_type": "B_BUY", "condition_key": "BUY:STATE_V1", "trigger_live": True, "action_state": "eligible", "confirmation_status": "pending", "primary_trigger_period": "W", "trigger_period": "W", "source_trigger_event_id": "fixture-trigger-buy-1", "episode_entry_event_id": "fixture-trigger-buy-1", "n5_state_version": 4, "updated_at": "2026-08-31T09:35:05+08:00"},
        {"asset_kind": "index", "identity": "index:SH:000001", "code": "000001", "name": "上证指数", "direction": "SELL", "signal_type": "S_SELL", "condition_key": "SELL:STATE_V1", "trigger_live": True, "action_state": "executed", "confirmation_status": "passed", "primary_trigger_period": "D", "trigger_period": "D", "source_trigger_event_id": "fixture-trigger-sell-1", "episode_entry_event_id": "fixture-trigger-sell-1", "n5_state_version": 2, "updated_at": "2026-08-31T10:01:05+08:00"},
        {"asset_kind": "board", "identity": "board:SH:881333", "code": "881333", "name": "元器件", "direction": "BUY", "signal_type": "B_BUY", "condition_key": "BUY:STATE_V1", "trigger_live": False, "action_state": "skipped", "confirmation_status": "expired", "primary_trigger_period": None, "trigger_period": "30m", "source_trigger_event_id": "fixture-trigger-board-1", "episode_entry_event_id": "fixture-trigger-board-1", "n5_state_version": 3, "updated_at": "2026-08-31T10:30:05+08:00"},
    ]
