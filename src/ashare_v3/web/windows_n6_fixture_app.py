"""Database-free Windows N6 A/B browser acceptance fixture."""

from __future__ import annotations

from html import escape
import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ashare_v3.web.windows_n6_runtime import (
    InMemoryWindowsRuntimeFixture,
    SIMULATION_LABEL,
    read_runtime_page,
    windows_archive_status,
    windows_postclose_status,
)


A_NAV = (
    ("收盘状态", "/n6/post-close-fastlane-status"),
    ("归档状态", "/n6/archive-status"),
    ("N2条件基础表", "/n6/n2-condition-basis/index"),
    ("N4状态表", "/n6/n4-runtime-states"),
    ("N5状态表", "/n6/n5-runtime-states"),
)
B_NAV = (
    ("首页", "/n6/app/dashboard"),
    ("筛选中心", "/n6/app/filter-center"),
    ("监控对象", "/n6/app/my-monitor"),
    ("实时监控范围", "/n6/app/realtime-scope"),
    ("触发状态", "/n6/app/status-monitor"),
    ("消息列表", "/n6/app/signals"),
    ("卡片消息", "/n6/app/messages"),
    ("虚拟账户", "/n6/app/account"),
    ("买卖日志", "/n6/app/trade-log"),
)

FIXTURE_PROJECTIONS = [
    {"asset_kind": "stock", "identity": "stock:SZ:000001", "direction": "BUY", "event_type": "ActionEligible", "status": "待确认"},
    {"asset_kind": "index", "identity": "index:SH:000001", "direction": "SELL", "event_type": "ActionExecuted", "status": "已确认"},
    {"asset_kind": "board", "identity": "board:SH:881333", "direction": "BUY", "event_type": "ActionSkipped", "status": "已失活"},
]


def create_windows_n6_fixture_app() -> FastAPI:
    bridge = InMemoryWindowsRuntimeFixture()
    app = FastAPI(title="Windows N6 fixture", description=SIMULATION_LABEL)

    @app.get("/")
    async def root() -> RedirectResponse:
        return RedirectResponse("/n6/post-close-fastlane-status")

    @app.get("/api/fixture/side-effects")
    async def side_effects() -> JSONResponse:
        return JSONResponse({
            "simulation": True,
            "database_connection_count": bridge.database_connection_count,
            "database_write_count": bridge.database_write_count,
            "outbox_write_count": bridge.outbox_write_count,
            "market_request_count": 0,
        })

    @app.get("/internal/v1/health")
    async def health() -> JSONResponse:
        return JSONResponse(dict(bridge.health()))

    @app.get("/internal/v1/n4/states")
    async def n4_api(request: Request) -> JSONResponse:
        return JSONResponse(read_runtime_page(bridge, "n4", dict(request.query_params)))

    @app.get("/internal/v1/n5/episodes")
    async def n5_api(request: Request) -> JSONResponse:
        return JSONResponse(read_runtime_page(bridge, "n5", dict(request.query_params)))

    @app.get("/n6/post-close-fastlane-status", response_class=HTMLResponse)
    async def postclose() -> HTMLResponse:
        return HTMLResponse(_page("Windows收盘状态", A_NAV, windows_postclose_status(bridge)))

    @app.get("/n6/archive-status", response_class=HTMLResponse)
    async def archive() -> HTMLResponse:
        return HTMLResponse(_page("Windows归档状态", A_NAV, windows_archive_status(bridge)))

    @app.get("/n6/n4-runtime-states", response_class=HTMLResponse)
    async def n4_states(request: Request) -> HTMLResponse:
        return HTMLResponse(_page("N4实时内存状态", A_NAV, read_runtime_page(bridge, "n4", dict(request.query_params))))

    @app.get("/n6/n5-runtime-states", response_class=HTMLResponse)
    async def n5_states(request: Request) -> HTMLResponse:
        return HTMLResponse(_page("N5活动Episode", A_NAV, read_runtime_page(bridge, "n5", dict(request.query_params))))

    @app.get("/n6/n2-condition-basis/index", response_class=HTMLResponse)
    async def n2_fixture() -> HTMLResponse:
        return HTMLResponse(_page("N2条件基础表", A_NAV, {"notice": "Fixture不连接数据库；生产页面读取Windows N2。"}))

    @app.get("/n6/app/{page_key}", response_class=HTMLResponse)
    async def b_track(page_key: str) -> HTMLResponse:
        payload: dict[str, Any] = {
            "page_key": page_key,
            "virtual_executor": "未启用",
            "projections": FIXTURE_PROJECTIONS if page_key in {"dashboard", "status-monitor", "signals", "messages"} else [],
            "write_api": False,
        }
        if page_key in {"account", "trade-log"}:
            payload["empty_state"] = "未初始化" if page_key == "account" else "暂无记录"
        return HTMLResponse(_page(f"B轨 {page_key}", B_NAV, payload))

    return app


def _page(title: str, nav: tuple[tuple[str, str], ...], payload: Any) -> str:
    links = "".join(f'<a href="{escape(href)}">{escape(label)}</a>' for label, href in nav)
    data = escape(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return f"""<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\"><title>{escape(title)}</title>
<style>body{{font-family:system-ui;margin:0;background:#f4f6f7;color:#172124}}header,main{{padding:16px 24px}}header{{background:#fff;border-bottom:1px solid #d7e0e3}}nav{{display:flex;gap:8px;flex-wrap:wrap}}a{{padding:7px 10px;border:1px solid #d7e0e3;border-radius:6px;color:#172124;text-decoration:none}}.warning{{background:#fff3cd;border:1px solid #ffcf66;color:#7a4b00;padding:12px;font-weight:800}}pre{{background:#fff;border:1px solid #d7e0e3;border-radius:8px;padding:14px;white-space:pre-wrap}}</style>
<header><h1>{escape(title)}</h1><nav>{links}</nav></header><main><div class=\"warning\">{SIMULATION_LABEL} · 数据库连接=0 · 数据库写入=0 · Outbox写入=0</div><pre>{data}</pre></main></html>"""
