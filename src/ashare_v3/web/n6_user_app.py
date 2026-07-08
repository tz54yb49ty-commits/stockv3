"""FastAPI app for the N6 user login and read-only projection MVP."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import secrets
from typing import Any, Callable, Protocol
from urllib.parse import parse_qs, quote, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from ashare_v3.user.admin_bootstrap import HashResult, hash_password, validate_password
from ashare_v3.user.membership_drilldown import (
    get_board_membership_stocks,
    get_index_membership_stocks,
)
from ashare_v3.user.stale_active_lineage import stale_source_action_run_ids
from ashare_v3.user.virtual_buy_execution import (
    VirtualBuyRejected,
    VirtualBuyRequest,
    execute_virtual_buy,
)
from ashare_v3.web.n6_app_v1 import (
    DEFAULT_REALTIME_SCOPE_INDEXES,
    app_account_model,
    app_ai_users_model,
    app_dashboard_model,
    app_empty_planned_model,
    app_leaderboard_model,
    app_locked_future_module_model,
    app_me_model,
    app_message_asset_kind,
    app_page_model,
    app_pnl_model,
    app_portfolio_model,
    app_realtime_scope_model,
    app_v2_filter_center_model,
    app_v2_expected_return_threshold,
    app_v2_expected_return_value_text,
    app_v2_filter_linked_stocks_model,
    app_v2_filter_members_model,
    app_v2_filter_model,
    app_v2_level_up_recommendation_value,
    app_v2_buy_messages_model,
    app_v2_membership_drilldown_model,
    app_v2_message_dashboard_model,
    app_v2_message_groups_model,
    app_v2_message_projection_status_model,
    app_v2_monitor_model,
    app_signal_detail_model,
    app_signals_model,
    app_status_monitor_model,
    app_watchlist_model,
)
from ashare_v3.web.n6_ui_v1 import (
    artifacts_model,
    cash_ledger_model,
    cash_snapshot_model,
    dashboard_metrics_model,
    lineage_stats_model,
    message_dashboard_model,
    n2_condition_basis_model,
    n2_condition_basis_item,
    n3_messages_model,
    n4_messages_model,
    n5_messages_model,
    post_close_fastlane_status_model,
    rag_search_model,
    READ_ONLY_SIDE_EFFECTS,
    runtime_archive_status_model,
    input_messages_model,
    rollback_summary_model,
    signal_detail_model,
    signal_list_model,
    status_monitor_model,
    virtual_account_summary_model,
)
from ashare_v3.web.post_close_fastlane_status import read_post_close_fastlane_status
from ashare_v3.web.rag_status import read_rag_status_answer
from ashare_v3.web.runtime_archive_status import read_runtime_archive_status


COOKIE_NAME = "ashare_v3_n6_session"
SESSION_HASH_ALGO = "sha256"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DSN = "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3"
DEFAULT_B_TRACK_ENTRY = "/n6/app"
DEFAULT_A_TRACK_ADMIN_ENTRY = "/n6/post-close-fastlane-status"
DEFAULT_POST_CLOSE_FASTLANE_DOCS_ROOT = str(PROJECT_ROOT / "docs/post_close_fastlane")
DEFAULT_RUNTIME_ARCHIVE_DOCS_ROOT = str(PROJECT_ROOT / "docs/runtime_archive")
DEFAULT_RUNTIME_ARCHIVE_ROOT = "/Volumes/MacRaid/stock_db_archive/v3_runtime"
DEFAULT_RAG_DOCS_ROOT = str(PROJECT_ROOT / "docs")
DEFAULT_RAG_SQL_ROOT = str(PROJECT_ROOT / "sql")
DEFAULT_REPLAY_DOCS_ROOT = str(PROJECT_ROOT / "docs/replay")
DEFAULT_PROFILE_NAME = "MVP default"
DEFAULT_SIM_ACCOUNT_NAME = "MVP T+1 shadow account"
DEFAULT_INITIAL_CASH = 1000000000
DISPLAY_TIMEZONE = ZoneInfo("Asia/Shanghai")
N6_UI_V1_LINEAGE_N4_RUN_ID = "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
N6_UI_V1_LINEAGE_N5_RUN_ID = (
    "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
)
N6_UI_V1_LINEAGE_N6_RUN_ID = (
    "user_projection_shadow_20260605__action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
)
N4_STANDARD_EVENT_TYPES = ("TriggerMatched", "TriggerPendingMarketData", "TriggerStateChanged")
N4_LEGACY_EVENT_TYPES = ("TriggerCleared", "TriggerLiveChanged")
N4_ALL_EVENT_TYPES = N4_STANDARD_EVENT_TYPES + N4_LEGACY_EVENT_TYPES
N4_MESSAGE_DEFAULT_LIMIT = 200
N3_MESSAGE_EVENT_TYPES = (
    "MarketSnapshotUpdated",
    "MinuteBarClosed",
    "MinuteBarCorrected",
    "MarketDataDelayed",
    "MarketDataMissing",
    "MarketDisplaySnapshotUpdated",
)
N3_MESSAGE_DEFAULT_LIMIT = 200
N5_STANDARD_EVENT_TYPES = ("ActionEligible", "ActionBlocked", "ActionExecuted", "ActionSkipped")
N5_LEGACY_EVENT_TYPES = ("ActionEvent", "HintEvent", "RiskEvent", "PositionEvent")
N5_ALL_EVENT_TYPES = N5_STANDARD_EVENT_TYPES + N5_LEGACY_EVENT_TYPES
N5_ACTION_DISPLAY_EVENT_TYPES = ("ActionExecuted", "ActionEligible")
N5_MESSAGE_DEFAULT_LIMIT = 200
B_TRACK_BUY_SIGNAL_ACTION_TYPES = ("buy", "sell", "all")
V3_20260612_ACTIVE_N4_SOURCE_RUN_ID = "v3_n4_trigger_replay_20260612_after_trigger_period_baseline_fix_v1"
V3_20260612_ACTIVE_N5_SOURCE_RUN_ID = "v3_n5_action_replay_20260612_after_n4_trigger_period_baseline_fix_v1"
V3_20260622_ACTIVE_N4_SOURCE_RUN_ID = (
    "trigger_replay_phase2d_20260622_formal_unitfix_dseed_periodguard_until_1500__"
    "condition_layer_20260618_source_20260618_for_20260622_v1"
)
ACTIVE_RAW_MESSAGE_SOURCE_RUN_BY_LAYER_DATE = {
    ("N4_trigger", "2026-06-12"): V3_20260612_ACTIVE_N4_SOURCE_RUN_ID,
    ("N5_action", "2026-06-12"): V3_20260612_ACTIVE_N5_SOURCE_RUN_ID,
    ("N4_trigger", "2026-06-22"): V3_20260622_ACTIVE_N4_SOURCE_RUN_ID,
}
N3_DISPLAY_INPUT_EVENT_TYPES = ("MarketDisplaySnapshotUpdated",)
N6_INPUT_MESSAGE_DEFAULT_LIMIT = 200
N2_CONDITION_BASIS_DEFAULT_LIMIT = 200
N2_CONDITION_BASIS_EXPORT_FILENAME_PREFIX = "N2条件基础表_最近日期"
N2_CONDITION_BASIS_EXPORT_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
N2_CONDITION_BASIS_ASSET_ORDER = ("index", "board", "stock")
N2_CONDITION_BASIS_ASSET_META = {
    "index": {
        "label": "指数",
        "source_table": "index_condition_basis",
        "id_column": "index_condition_basis_id",
        "identity_column": "index_identity_key",
        "code_column": "code",
        "name_column": "name",
        "exchange_expr": "t.exchange",
        "board_type_expr": "NULL::text",
    },
    "board": {
        "label": "板块",
        "source_table": "board_condition_basis",
        "id_column": "board_condition_basis_id",
        "identity_column": "board_identity_key",
        "code_column": "board_code",
        "name_column": "board_name",
        "exchange_expr": "NULL::text",
        "board_type_expr": "t.board_type",
    },
    "stock": {
        "label": "个股",
        "source_table": "stock_condition_basis",
        "id_column": "stock_condition_basis_id",
        "identity_column": "stock_identity_key",
        "code_column": "code",
        "name_column": "name",
        "exchange_expr": "t.exchange",
        "board_type_expr": "NULL::text",
    },
}
N2_CONDITION_BASIS_EXPORT_COLUMNS = (
    ("asset_label", "资产类型"),
    ("source_table", "来源表"),
    ("condition_basis_id", "条件基础ID"),
    ("run_id", "运行批次"),
    ("source_trade_date", "来源日期"),
    ("for_trade_date", "适用交易日"),
    ("identity_key", "标识"),
    ("code", "代码"),
    ("exchange", "交易所"),
    ("name", "名称"),
    ("board_type", "板块类型"),
    ("direction_scope_text", "方向范围"),
    ("condition_keys_text", "条件键"),
    ("buy_necessary_key", "买入必要条件"),
    ("sell_necessary_key", "卖出必要条件"),
    ("buy_full_necessary_key", "买入FULL条件"),
    ("sell_full_necessary_key", "卖出FULL条件"),
    ("oversold_hint_key", "超跌提示条件"),
    ("overbought_hint_key", "超涨提示条件"),
    ("period_keys.Y", "年周期"),
    ("period_keys.Q", "季周期"),
    ("period_keys.M", "月周期"),
    ("period_keys.W", "周周期"),
    ("period_keys.D", "日周期"),
    ("period_grades.Y", "年分级"),
    ("period_grades.Q", "季分级"),
    ("period_grades.M", "月分级"),
    ("period_grades.W", "周分级"),
    ("period_grades.D", "日分级"),
    ("amount_quality_status", "金额质量"),
    ("buy_target_price", "买入目标价"),
    ("buy_expected_return_pct", "买入预期收益率"),
    ("sell_target_price", "卖出目标价"),
    ("sell_expected_return_pct", "卖出预期收益率"),
    ("up_sell_reference_period", "上涨卖出参考周期"),
    ("down_buy_reference_period", "下跌买入参考周期"),
    ("quality_status", "质量状态"),
    ("quality_reason", "质量原因"),
    ("source_version", "来源版本"),
    ("source_batch_id", "来源批次"),
    ("created_at", "创建时间"),
    ("updated_at", "更新时间"),
    ("row_json_text", "原始行JSON"),
    ("raw_json_text", "原始JSON"),
    ("period_trigger_baseline_json_text", "周期触发基准JSON"),
    ("target_price_trace_json_text", "目标价追溯JSON"),
)


def raw_message_event_date_bounds(event_date: str) -> tuple[datetime, datetime]:
    start = datetime.strptime(event_date, "%Y-%m-%d").replace(tzinfo=DISPLAY_TIMEZONE)
    return start, start + timedelta(days=1)


def raw_message_identity_candidates(keyword: Any) -> list[str]:
    text = str(keyword or "").strip()
    if not text:
        return []
    candidates: list[str] = []

    def add(value: str) -> None:
        if value and value not in candidates:
            candidates.append(value)

    normalized = text.upper()
    if re.fullmatch(r"(STOCK|INDEX|BOARD):[A-Z]+:[0-9A-Z]+", normalized):
        asset, exchange, code = normalized.split(":")
        add(f"{asset.lower()}:{exchange}:{code}")
        return candidates

    if re.fullmatch(r"[0-9]{6}", text):
        add(f"stock:SH:{text}")
        add(f"stock:SZ:{text}")
        add(f"stock:BJ:{text}")
        add(f"index:SH:{text}")
        add(f"index:SZ:{text}")
        if text.startswith("88"):
            add(f"board:TDX:{text}")
    return candidates


def raw_message_keyword_predicate(keyword: Any) -> tuple[str, list[Any]]:
    text = str(keyword or "").strip()
    candidates = raw_message_identity_candidates(text)
    if candidates:
        return (
            """
            partition_key = ANY(%s)
            """,
            [candidates],
        )
    pattern = f"%{text}%"
    return (
        """
        (
            identity_key ILIKE %s
            OR event_id ILIKE %s
            OR source_run_id ILIKE %s
        )
        """,
        [pattern, pattern, pattern],
    )


def n5_actions_read_only_side_effects() -> dict[str, Any]:
    return {
        "writes_database": False,
        "outbox_status_updates": 0,
        "inbox_writes": 0,
        "checkpoint_writes": 0,
        "user_projection_writes": 0,
        "sim_written": False,
        "real_trade_submitted": False,
        "voice_triggered": False,
        "mobile_triggered": False,
    }


def n5_actions_empty_model(*, filters: dict[str, Any], limit: int) -> dict[str, Any]:
    return {
        "ok": True,
        "component": "N5 Actions",
        "title": "N5动作",
        "source_layer": "N5_action",
        "action_run_id": "",
        "source_run_id": "",
        "total_count": 0,
        "filtered_count": 0,
        "returned_count": 0,
        "default_limit": limit,
        "filters": {key: value for key, value in filters.items() if value},
        "filter_inputs": {
            "action_run_id": str(filters.get("action_run_id") or ""),
            "source_run_id": str(filters.get("source_run_id") or ""),
            "event_type": str(filters.get("event_type") or ""),
            "status": str(filters.get("status") or ""),
            "asset_kind": str(filters.get("asset_kind") or ""),
            "action_state": str(filters.get("action_state") or ""),
            "q": str(filters.get("q") or ""),
        },
        "event_types": list(N5_ACTION_DISPLAY_EVENT_TYPES),
        "action_states": ["executed", "eligible"],
        "summary": {"total": 0, "pending": 0, "ActionExecuted": 0, "ActionEligible": 0},
        "items": [],
        "side_effects": n5_actions_read_only_side_effects(),
    }


def n5_action_display_item(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload_json") or {}
    if not isinstance(payload, dict):
        payload = {}
    trace_json = payload.get("trace_json") or {}
    if not isinstance(trace_json, dict):
        trace_json = {}
    live_window = trace_json.get("live_window_confirmation") or {}
    if not isinstance(live_window, dict):
        live_window = {}
    selected_metric_id = live_window.get("selected_metric_id") or payload.get("selected_metric_id") or ""
    selected_metric_time = (
        live_window.get("executed_metric_time")
        or live_window.get("selected_metric_time")
        or payload.get("executed_metric_time")
        or payload.get("selected_metric_time")
        or ""
    )
    trigger_metric_time = live_window.get("trigger_metric_time") or payload.get("trigger_metric_time") or ""
    live_window_confirmation = live_window.get("live_window_confirmation")
    if live_window_confirmation is None:
        live_window_confirmation = payload.get("live_window_confirmation")
    multi_action_window = live_window.get("multi_action_window")
    if multi_action_window is None:
        multi_action_window = payload.get("multi_action_window")
    return {
        "outbox_id": row.get("outbox_id"),
        "event_id": str(row.get("event_id") or ""),
        "event_time": format_datetime(row.get("event_time")),
        "trade_date": str(row.get("trade_date") or ""),
        "asset_kind": str(row.get("asset_kind") or ""),
        "identity_key": str(row.get("identity_key") or ""),
        "event_type": str(row.get("event_type") or ""),
        "source_layer": str(row.get("source_layer") or ""),
        "source_run_id": str(row.get("source_run_id") or ""),
        "status": str(row.get("status") or ""),
        "action_state": str(payload.get("action_state") or ""),
        "action_type": str(payload.get("action_type") or ""),
        "condition_key": str(payload.get("condition_key") or ""),
        "selected_metric_id": str(selected_metric_id) if selected_metric_id else "",
        "selected_metric_time": str(selected_metric_time) if selected_metric_time else "",
        "trigger_metric_time": str(trigger_metric_time) if trigger_metric_time else "",
        "live_window_confirmation": bool(live_window_confirmation),
        "multi_action_window": bool(multi_action_window),
        "action_key": str(payload.get("action_key") or ""),
        "dedup_key": str(payload.get("dedup_key") or row.get("dedup_key") or ""),
        "payload_json": payload,
        "payload_json_text": json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
    }


def b_track_buy_signal_read_only_side_effects() -> dict[str, Any]:
    return {
        "writes_database": False,
        "outbox_status_updates": 0,
        "inbox_writes": 0,
        "checkpoint_writes": 0,
        "user_projection_writes": 0,
        "user_card_writes": 0,
        "virtual_account_writes": 0,
        "order_writes": 0,
        "position_writes": 0,
        "sim_written": False,
        "real_trade_submitted": False,
        "voice_triggered": False,
        "mobile_triggered": False,
    }


def b_track_buy_signal_empty_model(*, filters: dict[str, Any], limit: int) -> dict[str, Any]:
    action_type = normalize_b_track_buy_signal_action_type(filters.get("action_type"))
    return {
        "ok": True,
        "component": "B Track Buy Signals",
        "title": "B轨买入信号",
        "source_layer": "N5_action",
        "action_run_id": "",
        "total_count": 0,
        "filtered_count": 0,
        "returned_count": 0,
        "default_limit": limit,
        "filters": {
            key: value
            for key, value in {
                "action_run_id": str(filters.get("action_run_id") or ""),
                "action_type": action_type,
                "q": str(filters.get("q") or ""),
            }.items()
            if value
        },
        "filter_inputs": {
            "action_run_id": str(filters.get("action_run_id") or ""),
            "action_type": action_type,
            "q": str(filters.get("q") or ""),
        },
        "action_types": list(B_TRACK_BUY_SIGNAL_ACTION_TYPES),
        "summary": {
            "total": 0,
            "buy": 0,
            "sell": 0,
            "ActionEligible": 0,
            "ActionExecuted": 0,
            "ActionBlocked": 0,
            "ActionSkipped": 0,
        },
        "items": [],
        "side_effects": b_track_buy_signal_read_only_side_effects(),
    }


def b_track_buy_signal_item(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload_json") or {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "outbox_id": row.get("outbox_id"),
        "event_id": str(row.get("event_id") or ""),
        "event_time": format_datetime(row.get("event_time")),
        "trade_date": str(row.get("trade_date") or ""),
        "action_run_id": str(row.get("source_run_id") or ""),
        "source_run_id": str(row.get("source_run_id") or ""),
        "asset_kind": str(row.get("asset_kind") or ""),
        "identity_key": str(row.get("identity_key") or ""),
        "event_type": str(row.get("event_type") or ""),
        "status": str(row.get("status") or ""),
        "action_type": str(payload.get("action_type") or ""),
        "action_state": str(payload.get("action_state") or ""),
        "signal_type": str(payload.get("signal_type") or ""),
        "condition_key": str(payload.get("condition_key") or ""),
        "projection_30m_type": str(payload.get("projection_30m_type") or ""),
        "trigger_mark_candidate": str(payload.get("trigger_mark_candidate") or ""),
        "projection_run_id": str(payload.get("projection_run_id") or ""),
        "projection_id": str(payload.get("projection_id") or ""),
        "source_trigger_run_id": str(payload.get("source_trigger_run_id") or ""),
        "source_trigger_event_id": str(payload.get("source_trigger_event_id") or ""),
        "provisional": bool(payload.get("provisional")),
        "action_confirmation_mode": str(payload.get("action_confirmation_mode") or ""),
        "payload_json": payload,
        "payload_json_text": json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
    }


STRATEGY_FILTER_OPTIONS = (
    {"key": "chase", "label": "追涨", "profile_key": "enable_chase"},
    {"key": "ultra_short", "label": "超短", "profile_key": "enable_ultra_short"},
    {"key": "short", "label": "短线", "profile_key": "enable_short"},
    {"key": "mid", "label": "中线", "profile_key": "enable_mid"},
    {"key": "long", "label": "长线", "profile_key": "enable_long"},
)
VALID_STRATEGY_FILTER_KEYS = {str(option["key"]) for option in STRATEGY_FILTER_OPTIONS}
APP_FILTER_CENTER_ASSET_BY_PAGE_KEY = {
    "filter-center": "index",
    "filter-center:indexes": "index",
    "filter-center:boards": "board",
    "filter-center:stocks": "stock",
}
APP_FILTER_CENTER_PAGE_KEY_BY_SLUG = {
    "indexes": "filter-center:indexes",
    "boards": "filter-center:boards",
    "stocks": "filter-center:stocks",
}
APP_FILTER_CENTER_PAGE_BY_ASSET = {
    "index": "indexes",
    "board": "boards",
    "stock": "stocks",
}
APP_MONITOR_ASSET_BY_PAGE_KEY = {
    "my-monitor": "stock",
    "my-monitor:stocks": "stock",
    "my-monitor:boards": "board",
    "my-monitor:indexes": "index",
}
APP_MONITOR_PAGE_KEY_BY_SLUG = {
    "stocks": "my-monitor:stocks",
    "boards": "my-monitor:boards",
    "indexes": "my-monitor:indexes",
}
APP_MONITOR_PAGE_BY_ASSET = {
    "stock": "stocks",
    "board": "boards",
    "index": "indexes",
}
APP_V2_MONITOR_TABLE_BY_ASSET = {
    "stock": "user_monitor_stock",
    "board": "user_monitor_board",
    "index": "user_monitor_index",
}
APP_REALTIME_SCOPE_TABLE = "user_realtime_monitor_scope"
APP_V2_FILTER_DISPLAY_TABLE_BY_ASSET = {
    "stock": "v_n6_stock_condition_display_basis",
    "board": "v_n6_board_condition_display_basis",
    "index": "v_n6_index_condition_display_basis",
}
APP_V2_VALID_DIRECTIONS = {"buy", "sell"}
APP_V2_MONITOR_STATUS_FILTERS = {"active", "expired", "all"}
APP_V2_PERIOD_GRADE_FILTER_VALUES = {
    "volume_up",
    "volume_down",
    "low_volume_up",
    "low_volume_down",
    "flat",
}
APP_V2_FILTER_PAGE_MAX_ROWS = 10000
APP_V2_FILTER_DEFAULT_ROWS_BY_ASSET = {
    "index": 200,
    "board": 200,
    "stock": 100,
}
N6_TRADING_SESSION_HISTORY_BLOCKER = "historical_query_disabled_during_trading_session"
N6_TRADING_SESSION_HISTORY_MESSAGE = "交易时段仅显示当前交易日，历史查询收盘后可用"
N6_TRADING_SESSION_START = (9, 25)
N6_TRADING_SESSION_END = (15, 0)


def app_v2_filter_default_limit(asset_kind: str) -> int:
    return APP_V2_FILTER_DEFAULT_ROWS_BY_ASSET.get(asset_kind, 200)


@dataclass(frozen=True)
class N6UserWebConfig:
    dsn: str = DEFAULT_DSN
    cookie_secure: bool = False
    session_ttl_seconds: int = 8 * 60 * 60
    card_limit: int = 500
    notification_limit: int = 500
    action_event_limit: int = 500
    ui_signal_limit: int = 500
    signal_source_user_id: int = 1
    post_close_fastlane_docs_root: str = DEFAULT_POST_CLOSE_FASTLANE_DOCS_ROOT
    runtime_archive_docs_root: str = DEFAULT_RUNTIME_ARCHIVE_DOCS_ROOT
    runtime_archive_root: str = DEFAULT_RUNTIME_ARCHIVE_ROOT
    rag_docs_root: str = DEFAULT_RAG_DOCS_ROOT
    rag_sql_root: str = DEFAULT_RAG_SQL_ROOT
    replay_docs_root: str = DEFAULT_REPLAY_DOCS_ROOT


def build_app_v2_message_dashboard(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    rows: list[dict[str, Any]],
    filters: dict[str, Any] | None = None,
    scope_metadata: dict[str, Any],
    limit: int = 100,
) -> dict[str, Any]:
    return app_v2_message_dashboard_model(
        principal,
        user=user,
        rows=rows,
        filters=filters,
        scope_metadata=scope_metadata,
        limit=limit,
    )


def n6_trading_session_now() -> datetime:
    return datetime.now(DISPLAY_TIMEZONE)


def n6_is_trading_session_for_trade_date(current_trade_date: str | None, *, now: datetime | None = None) -> bool:
    trade_date = normalize_filter_value(current_trade_date)
    if not trade_date:
        return False
    current_time = now or n6_trading_session_now()
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=DISPLAY_TIMEZONE)
    current_time = current_time.astimezone(DISPLAY_TIMEZONE)
    if current_time.strftime("%Y%m%d") != trade_date:
        return False
    start_hour, start_minute = N6_TRADING_SESSION_START
    end_hour, end_minute = N6_TRADING_SESSION_END
    session_start = current_time.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    session_end = current_time.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
    return session_start <= current_time <= session_end


def n6_trade_date_access_policy(
    *,
    current_trade_date: str | None,
    requested_trade_date: str | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = normalize_filter_value(current_trade_date)
    requested = normalize_filter_value(requested_trade_date)
    effective = requested or current or ""
    blocked = bool(
        current
        and requested
        and requested != current
        and n6_is_trading_session_for_trade_date(current, now=now)
    )
    if blocked:
        effective = current
    return {
        "blocked": blocked,
        "blocker": N6_TRADING_SESSION_HISTORY_BLOCKER if blocked else "",
        "message": N6_TRADING_SESSION_HISTORY_MESSAGE if blocked else "",
        "current_trade_date": current or "",
        "requested_trade_date": requested or "",
        "effective_trade_date": effective,
        "historical_query_allowed": not blocked,
    }


def n6_trading_session_blocker_response(policy: dict[str, Any]) -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error": N6_TRADING_SESSION_HISTORY_BLOCKER,
            "blockers": [N6_TRADING_SESSION_HISTORY_BLOCKER],
            "message": N6_TRADING_SESSION_HISTORY_MESSAGE,
            "current_trade_date": policy.get("current_trade_date") or "",
            "requested_trade_date": policy.get("requested_trade_date") or "",
            "effective_trade_date": policy.get("effective_trade_date") or "",
        },
        status_code=409,
    )


def n6_json_response(content: Any, *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(jsonable_encoder(content), status_code=status_code)


def build_app_v2_message_groups(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    rows: list[dict[str, Any]],
    scope_metadata: dict[str, Any],
) -> dict[str, Any]:
    return app_v2_message_groups_model(
        principal,
        user=user,
        rows=rows,
        scope_metadata=scope_metadata,
    )


def build_app_v2_projection_status(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    rows: list[dict[str, Any]],
    scope_metadata: dict[str, Any],
) -> dict[str, Any]:
    return app_v2_message_projection_status_model(
        principal,
        user=user,
        rows=rows,
        scope_metadata=scope_metadata,
    )


@dataclass(frozen=True)
class UserAccount:
    user_id: int
    login_name: str
    display_name: str | None
    role: str
    status: str
    password_hash: str
    password_hash_algo: str


@dataclass(frozen=True)
class AuthSession:
    user_session_id: int
    user_id: int
    login_name: str
    display_name: str | None
    role: str
    status: str
    session_token_hash: str
    expires_at: datetime
    revoked_at: datetime | None


class N6UserRepository(Protocol):
    def fetch_user_for_login(self, login_name: str) -> UserAccount | None:
        ...

    def create_session(
        self,
        *,
        user_id: int,
        session_token_hash: str,
        session_token_hash_algo: str,
        expires_at: datetime,
        client_info: dict[str, Any],
    ) -> AuthSession:
        ...

    def fetch_session(self, session_token_hash: str) -> AuthSession | None:
        ...

    def revoke_session(self, session_token_hash: str, revoked_at: datetime) -> bool:
        ...

    def fetch_cards(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        ...

    def fetch_notifications(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        ...

    def fetch_n5_action_events(self, limit: int) -> list[dict[str, Any]]:
        ...

    def fetch_message_dashboard(self, limit: int) -> dict[str, Any]:
        ...

    def fetch_top_index_strategy(self) -> dict[str, Any] | None:
        ...

    def fetch_strong_boards(self, limit: int) -> list[dict[str, Any]]:
        ...

    def fetch_filter_profile(self, user_id: int) -> dict[str, Any] | None:
        ...

    def fetch_users_for_admin(self) -> list[dict[str, Any]]:
        ...

    def create_user_with_defaults(
        self,
        *,
        login_name: str,
        display_name: str | None,
        role: str,
        password_hash: str,
        password_hash_algo: str,
        created_by_user_id: int,
    ) -> dict[str, Any]:
        ...

    def delete_user(self, *, target_user_id: int, deleted_by_user_id: int) -> dict[str, Any]:
        ...

    def fetch_sim_account(self, user_id: int) -> dict[str, Any] | None:
        ...

    def fetch_sim_positions(self, user_id: int) -> list[dict[str, Any]]:
        ...

    def fetch_ui_v1_signals(
        self,
        user_id: int,
        filters: dict[str, Any],
        limit: int,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        ...

    def count_ui_v1_signals(self, user_id: int, filters: dict[str, Any]) -> int:
        ...

    def fetch_ui_v1_signal_statistics(self, user_id: int) -> dict[str, Any]:
        ...

    def fetch_ui_v1_lineage_stats(self, user_id: int) -> dict[str, Any]:
        ...

    def fetch_ui_v1_n3_messages(
        self,
        *,
        filters: dict[str, Any] | None = None,
        limit: int,
        include_all: bool = False,
    ) -> dict[str, Any]:
        ...

    def fetch_ui_v1_n4_messages(
        self,
        *,
        filters: dict[str, Any] | None = None,
        limit: int,
        include_all: bool = False,
    ) -> dict[str, Any]:
        ...

    def fetch_ui_v1_n5_messages(
        self,
        *,
        filters: dict[str, Any] | None = None,
        limit: int,
        include_all: bool = False,
    ) -> dict[str, Any]:
        ...

    def fetch_ui_v1_n5_actions(
        self,
        *,
        filters: dict[str, Any] | None = None,
        limit: int,
    ) -> dict[str, Any]:
        ...

    def fetch_b_track_buy_signals(
        self,
        *,
        filters: dict[str, Any] | None = None,
        limit: int,
    ) -> dict[str, Any]:
        ...

    def fetch_index_board_c1_minute_rows(self, trade_date: str) -> dict[str, list[dict[str, Any]]]:
        ...

    def fetch_ui_v1_input_messages(
        self,
        *,
        filters: dict[str, Any] | None = None,
        limit: int,
        include_all: bool = False,
    ) -> dict[str, Any]:
        ...

    def fetch_ui_v1_n2_condition_basis(
        self,
        *,
        asset_kind: str,
        filters: dict[str, Any] | None = None,
        limit: int,
        include_all: bool = False,
    ) -> dict[str, Any]:
        ...

    def fetch_ui_v1_n2_condition_basis_latest_export(self) -> dict[str, Any]:
        ...

    def fetch_ui_v1_status_monitor(
        self,
        user_id: int,
        filters: dict[str, Any],
        limit: int,
        offset: int = 0,
    ) -> dict[str, Any]:
        ...

    def fetch_ui_v1_signal_detail(self, user_id: int, user_signal_projection_id: int) -> dict[str, Any] | None:
        ...

    def fetch_ui_v1_dashboard_metrics(self, user_id: int) -> dict[str, Any]:
        ...

    def fetch_ui_v1_virtual_account(self, user_id: int) -> dict[str, Any] | None:
        ...

    def fetch_ui_v1_cash_snapshot(self, user_id: int) -> dict[str, Any] | None:
        ...

    def fetch_ui_v1_cash_ledger(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        ...

    def fetch_ui_v1_artifacts(self) -> dict[str, Any]:
        ...

    def fetch_ui_v1_rollback_summary(self) -> dict[str, Any]:
        ...

    def fetch_app_principals(self, user_id: int) -> list[dict[str, Any]]:
        ...

    def fetch_app_virtual_account(self, principal_id: int, principal_type: str) -> dict[str, Any] | None:
        ...

    def fetch_app_cash_snapshot(self, virtual_account_id: int) -> dict[str, Any] | None:
        ...

    def fetch_app_signals(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        filters: dict[str, Any],
        limit: int,
    ) -> list[dict[str, Any]]:
        ...

    def fetch_app_signal_detail(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        user_signal_projection_id: int,
    ) -> dict[str, Any] | None:
        ...

    def fetch_app_signal_scope_metadata(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
    ) -> dict[str, Any]:
        ...

    def fetch_app_realtime_scope(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
    ) -> dict[str, Any]:
        ...

    def fetch_app_positions(self, principal_id: int, principal_type: str) -> list[dict[str, Any]]:
        ...

    def fetch_app_pnl_snapshots(self, principal_id: int, principal_type: str, limit: int) -> list[dict[str, Any]]:
        ...

    def fetch_app_filter_items(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        asset_kind: str,
        filters: dict[str, Any],
        limit: int,
        include_all_fields: bool = False,
    ) -> dict[str, Any]:
        ...

    def fetch_app_filter_members(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        membership_kind: str,
        parent_identity_key: str,
        limit: int,
    ) -> dict[str, Any]:
        ...

    def fetch_app_filter_linked_stocks(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        membership_kind: str,
        parent_identity_key: str,
        limit: int,
        view: str = "matched",
    ) -> dict[str, Any]:
        ...

    def fetch_app_membership_stocks(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        entity_type: str,
        identity_key: str,
        limit: int,
    ) -> dict[str, Any]:
        ...

    def fetch_app_monitor_items(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        asset_kind: str | None = None,
        limit: int = 500,
        monitor_status: str = "active",
        for_trade_date: str = "",
    ) -> dict[str, Any]:
        ...

    def add_app_monitor_item(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        asset_kind: str,
        identity_key: str,
        direction: str,
        source: str = "single_row",
        for_trade_date: str = "",
    ) -> dict[str, Any]:
        ...

    def bulk_add_app_monitor_items(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        asset_kind: str,
        direction: str,
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        ...

    def selected_add_app_monitor_items(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        asset_kind: str,
        direction: str,
        identity_keys: list[str],
    ) -> dict[str, Any]:
        ...

    def add_app_linked_stock_monitor_items(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        parent_asset_kind: str,
        parent_identity_key: str,
        mode: str,
        stock_identity_keys: list[str],
        direction: str,
    ) -> dict[str, Any]:
        ...

    def remove_app_monitor_item(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        monitor_id: int,
    ) -> dict[str, Any]:
        ...

    def add_app_realtime_scope_item(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        asset_kind: str,
        identity_key: str,
        for_trade_date: str = "",
        source: str = "single_row",
    ) -> dict[str, Any]:
        ...

    def selected_add_app_realtime_scope_items(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        asset_kind: str,
        identity_keys: list[str],
        for_trade_date: str = "",
    ) -> dict[str, Any]:
        ...

    def bulk_add_app_realtime_scope_items(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        asset_kind: str,
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        ...

    def remove_app_realtime_scope_item(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        realtime_scope_id: int,
    ) -> dict[str, Any]:
        ...


PasswordVerifier = Callable[[str, str, str], bool]
PasswordHasher = Callable[[str], HashResult]


class UserManagementError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PostgresN6UserRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._app_v2_monitor_column_cache: dict[str, set[str]] = {}
        self._app_v2_filter_column_cache: dict[str, set[str]] = {}

    def fetch_user_for_login(self, login_name: str) -> UserAccount | None:
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, login_name, display_name, role, status,
                       password_hash, password_hash_algo
                FROM user_account
                WHERE login_name = %s
                """,
                (login_name,),
            )
            row = cur.fetchone()
        return UserAccount(**dict(row)) if row else None

    def create_session(
        self,
        *,
        user_id: int,
        session_token_hash: str,
        session_token_hash_algo: str,
        expires_at: datetime,
        client_info: dict[str, Any],
    ) -> AuthSession:
        with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_session (
                      user_id,
                      session_token_hash,
                      session_token_hash_algo,
                      expires_at,
                      client_info_json
                    )
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    RETURNING user_session_id, session_token_hash, expires_at, revoked_at
                    """,
                    (
                        user_id,
                        session_token_hash,
                        session_token_hash_algo,
                        expires_at,
                        json.dumps(client_info, ensure_ascii=True),
                    ),
                )
                session_row = dict(cur.fetchone())
                cur.execute(
                    """
                    SELECT user_id, login_name, display_name, role, status
                    FROM user_account
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                user_row = dict(cur.fetchone())
        return AuthSession(**user_row, **session_row)

    def fetch_session(self, session_token_hash: str) -> AuthSession | None:
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.user_session_id,
                       s.user_id,
                       u.login_name,
                       u.display_name,
                       u.role,
                       u.status,
                       s.session_token_hash,
                       s.expires_at,
                       s.revoked_at
                FROM user_session s
                JOIN user_account u ON u.user_id = s.user_id
                WHERE s.session_token_hash = %s
                """,
                (session_token_hash,),
            )
            row = cur.fetchone()
        return AuthSession(**dict(row)) if row else None

    def revoke_session(self, session_token_hash: str, revoked_at: datetime) -> bool:
        with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE user_session
                    SET revoked_at = %s,
                        updated_at = now()
                    WHERE session_token_hash = %s
                      AND revoked_at IS NULL
                    RETURNING user_session_id
                    """,
                    (revoked_at, session_token_hash),
                )
                return cur.fetchone() is not None

    def fetch_cards(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.user_signal_card_id,
                       c.card_type,
                       c.card_status,
                       c.display_priority,
                       c.title,
                       c.summary,
                       c.asset_kind,
                       c.identity_key,
                       c.code,
                       c.name,
                       c.direction,
                       c.signal_type,
                       c.target_price,
                       c.current_price,
                       c.expected_return_pct,
                       c.board_code,
                       c.board_name,
                       c.source_action_run_id,
                       c.source_event_id,
                       c.created_at,
                       s.period_transition_y,
                       s.period_transition_q,
                       s.period_transition_m,
                       s.period_transition_w,
                       s.period_transition_d
                FROM user_signal_card c
                LEFT JOIN user_signal_projection p
                  ON p.user_signal_projection_id = c.user_signal_projection_id
                 AND p.user_id = c.user_id
                LEFT JOIN stock_condition_display_basis s
                  ON c.asset_kind = 'stock'
                 AND p.source_display_table = 'stock_condition_display_basis'
                 AND p.source_condition_display_basis_id = s.stock_condition_display_basis_id
                WHERE c.user_id = %s
                ORDER BY c.display_priority ASC, c.created_at DESC, c.user_signal_card_id ASC
                LIMIT %s
                """,
                (user_id, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    def fetch_notifications(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_notification_queue_id,
                       user_projection_run_id,
                       notification_source,
                       queue_status,
                       channel,
                       title,
                       message,
                       priority,
                       source_event_id,
                       source_action_run_id,
                       asset_kind,
                       identity_key,
                       queued_at
                FROM user_notification_queue
                WHERE user_id = %s
                ORDER BY priority ASC, queued_at DESC, user_notification_queue_id ASC
                LIMIT %s
                """,
                (user_id, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    def fetch_n5_action_events(self, limit: int) -> list[dict[str, Any]]:
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT outbox_id,
                       event_id,
                       event_type,
                       event_schema_version,
                       trade_date,
                       asset_kind,
                       identity_key,
                       event_time,
                       source_run_id,
                       dedup_key,
                       partition_key,
                       payload_json,
                       payload_json->>'direction' AS direction,
                       payload_json->>'signal_type' AS signal_type,
                       payload_json->>'action_state' AS action_state,
                       payload_json->>'action_mark' AS action_mark,
                       payload_json->>'condition_key' AS condition_key,
                       payload_json->>'original_condition_key' AS original_condition_key,
                       status,
                       created_at
                FROM common_event_outbox
                WHERE source_layer = 'N5_action'
                  AND event_type IN (
                    'ActionEligible',
                    'ActionBlocked',
                    'ActionExecuted',
                    'ActionSkipped',
                    'ActionEvent',
                    'HintEvent'
                  )
                ORDER BY created_at DESC, outbox_id DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]

    def fetch_message_dashboard(self, limit: int) -> dict[str, Any]:
        event_types = (
            "TriggerMatched",
            "ActionBlocked",
            "ActionExecuted",
            "ActionEligible",
            "ActionSkipped",
        )
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  count(*) FILTER (
                    WHERE source_layer = 'N4_trigger'
                      AND event_type = 'TriggerMatched'
                      AND status = 'pending'
                      AND (created_at AT TIME ZONE 'Asia/Shanghai')::date =
                          (now() AT TIME ZONE 'Asia/Shanghai')::date
                  )::int AS today_n4_trigger_matched_pending,
                  count(*) FILTER (
                    WHERE source_layer = 'N5_action'
                      AND event_type = 'ActionBlocked'
                      AND (created_at AT TIME ZONE 'Asia/Shanghai')::date =
                          (now() AT TIME ZONE 'Asia/Shanghai')::date
                  )::int AS today_n5_action_blocked,
                  count(*) FILTER (
                    WHERE source_layer = 'N5_action'
                      AND event_type = 'ActionExecuted'
                      AND (created_at AT TIME ZONE 'Asia/Shanghai')::date =
                          (now() AT TIME ZONE 'Asia/Shanghai')::date
                  )::int AS today_n5_action_executed,
                  count(*) FILTER (
                    WHERE source_layer = 'N5_action'
                      AND status = 'pending'
                      AND event_type IN ('ActionBlocked', 'ActionExecuted', 'ActionEligible', 'ActionSkipped')
                  )::int AS n5_outbox_pending
                FROM common_event_outbox
                WHERE event_type = ANY(%s)
                """,
                (list(event_types),),
            )
            admin_dashboard = dict(cur.fetchone() or {})

            cur.execute(
                """
                SELECT event_type, status, count(*)::int AS count
                FROM common_event_outbox
                WHERE event_type = ANY(%s)
                GROUP BY event_type, status
                ORDER BY event_type, status
                """,
                (list(event_types),),
            )
            event_distribution = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT
                  count(DISTINCT p.user_projection_run_id)::int AS projection_run_count,
                  count(DISTINCT p.user_signal_projection_id)::int AS signal_projection_count,
                  count(DISTINCT c.user_signal_card_id)::int AS signal_card_count,
                  count(DISTINCT q.user_notification_queue_id)::int AS notification_queue_count,
                  count(DISTINCT q.user_notification_queue_id)
                    FILTER (WHERE q.queue_status = 'queued_only')::int AS queued_only,
                  count(DISTINCT q.user_notification_queue_id)
                    FILTER (WHERE q.queue_status = 'ready_for_future_push')::int AS ready_for_future_push,
                  (
                    SELECT r.user_projection_run_id
                    FROM user_projection_run r
                    ORDER BY r.created_at DESC NULLS LAST, r.finished_at DESC NULLS LAST
                    LIMIT 1
                  ) AS latest_projection_run_id
                FROM user_signal_projection p
                LEFT JOIN user_signal_card c
                  ON c.user_signal_projection_id = p.user_signal_projection_id
                 AND c.user_id = p.user_id
                LEFT JOIN user_notification_queue q
                  ON q.user_signal_projection_id = p.user_signal_projection_id
                 AND q.user_id = p.user_id
                """
            )
            n6_shadow = dict(cur.fetchone() or {})

            cur.execute(
                """
                SELECT COALESCE(
                         c.card_payload_json->>'blocked_reason',
                         p.display_payload_json->>'blocked_reason',
                         p.trace_json->>'blocked_reason',
                         p.source_payload_json->>'blocked_reason',
                         'unknown'
                       ) AS blocked_reason,
                       count(*)::int AS count
                FROM user_signal_projection p
                LEFT JOIN user_signal_card c
                  ON c.user_signal_projection_id = p.user_signal_projection_id
                 AND c.user_id = p.user_id
                WHERE COALESCE(
                        NULLIF(p.action_state, ''),
                        NULLIF(c.action_state, ''),
                        CASE
                          WHEN p.source_action_event_type = 'ActionBlocked' THEN 'blocked'
                          WHEN p.source_action_event_type = 'ActionExecuted' THEN 'executed'
                          WHEN p.source_action_event_type = 'ActionEligible' THEN 'eligible'
                          WHEN p.source_action_event_type = 'ActionSkipped' THEN 'skipped'
                          ELSE NULL
                        END,
                        p.projection_status,
                        c.card_status
                      ) = 'blocked'
                GROUP BY blocked_reason
                ORDER BY count DESC, blocked_reason ASC
                LIMIT 20
                """
            )
            blocked_reasons = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT layer, run_id, status, created_at, finished_at
                FROM (
                  SELECT 'N4' AS layer, run_id, status, created_at, finished_at
                  FROM common_trigger_run
                  UNION ALL
                  SELECT 'N5' AS layer, run_id, status, created_at, finished_at
                  FROM common_action_run
                  UNION ALL
                  SELECT 'N6' AS layer, user_projection_run_id AS run_id, status, created_at, finished_at
                  FROM user_projection_run
                ) runs
                ORDER BY created_at DESC NULLS LAST, finished_at DESC NULLS LAST
                LIMIT 10
                """
            )
            recent_runs = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT outbox_id,
                       event_id,
                       event_type,
                       event_schema_version,
                       trade_date,
                       asset_kind,
                       identity_key,
                       event_time,
                       source_layer,
                       source_run_id,
                       dedup_key,
                       partition_key,
                       payload_json,
                       payload_json->>'direction' AS direction,
                       payload_json->>'signal_type' AS signal_type,
                       payload_json->>'action_state' AS action_state,
                       payload_json->>'action_mark' AS action_mark,
                       payload_json->>'condition_key' AS condition_key,
                       payload_json->>'original_condition_key' AS original_condition_key,
                       status,
                       created_at
                FROM common_event_outbox
                WHERE event_type = ANY(%s)
                ORDER BY created_at DESC, outbox_id DESC
                LIMIT %s
                """,
                (list(event_types), max(1, min(int(limit), 1000))),
            )
            messages = [dict(row) for row in cur.fetchall()]

        return {
            "admin_dashboard": {
                **admin_dashboard,
                "n6_shadow_projection_count": int(n6_shadow.get("signal_projection_count") or 0),
                "n6_shadow_card_count": int(n6_shadow.get("signal_card_count") or 0),
                "n6_shadow_queue_count": int(n6_shadow.get("notification_queue_count") or 0),
                "n6_queued_only": int(n6_shadow.get("queued_only") or 0),
                "n6_ready_for_future_push": int(n6_shadow.get("ready_for_future_push") or 0),
                "latest_projection_run_id": n6_shadow.get("latest_projection_run_id") or "—",
            },
            "message_dashboard": {
                "event_distribution": event_distribution,
                "total_messages": sum(int(row.get("count") or 0) for row in event_distribution),
            },
            "blocked_reason_distribution": blocked_reasons,
            "recent_runs": recent_runs,
            "messages": messages,
        }

    def fetch_top_index_strategy(self) -> dict[str, Any] | None:
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT code,
                       name,
                       display_title,
                       display_summary,
                       selected_signal_types,
                       selected_condition_keys,
                       period_transition_y,
                       period_transition_q,
                       period_transition_m,
                       period_transition_w,
                       period_transition_d,
                       buy_target_price,
                       sell_target_price
                FROM v_n6_index_condition_display_basis
                WHERE display_status = 'visible'
                  AND quality_status IN ('passed', 'warning', 'pending')
                ORDER BY
                  CASE
                    WHEN period_transition_y = 'volume_up'
                     AND period_transition_q = 'volume_up'
                     AND period_transition_m = 'volume_up'
                     AND period_transition_w = 'volume_up'
                     AND period_transition_d = 'volume_up' THEN 60
                    WHEN period_transition_y = 'volume_up'
                     AND period_transition_q = 'volume_up'
                     AND period_transition_m = 'volume_up'
                     AND period_transition_w = 'volume_up'
                     AND COALESCE(period_transition_d, '') <> 'volume_up' THEN 50
                    WHEN period_transition_y = 'volume_up'
                     AND period_transition_q = 'volume_up'
                     AND period_transition_m = 'volume_up'
                     AND COALESCE(period_transition_w, '') <> 'volume_up'
                     AND COALESCE(period_transition_d, '') <> 'volume_up' THEN 40
                    WHEN period_transition_y = 'volume_up'
                     AND period_transition_q = 'volume_up'
                     AND COALESCE(period_transition_m, '') <> 'volume_up'
                     AND COALESCE(period_transition_w, '') <> 'volume_up'
                     AND COALESCE(period_transition_d, '') <> 'volume_up' THEN 30
                    WHEN period_transition_y = 'volume_up'
                     AND COALESCE(period_transition_q, '') <> 'volume_up'
                     AND COALESCE(period_transition_m, '') <> 'volume_up'
                     AND COALESCE(period_transition_w, '') <> 'volume_up'
                     AND COALESCE(period_transition_d, '') <> 'volume_up' THEN 20
                    WHEN COALESCE(period_transition_y, '') <> 'volume_up'
                     AND COALESCE(period_transition_q, '') <> 'volume_up'
                     AND COALESCE(period_transition_m, '') <> 'volume_up'
                     AND COALESCE(period_transition_w, '') <> 'volume_up'
                     AND COALESCE(period_transition_d, '') <> 'volume_up' THEN 10
                    ELSE 0
                  END DESC,
                  updated_at DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def fetch_strong_boards(self, limit: int) -> list[dict[str, Any]]:
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT board_code,
                       board_name,
                       display_title,
                       display_summary,
                       selected_signal_types,
                       period_transition_y,
                       period_transition_q,
                       period_transition_m,
                       period_transition_w,
                       period_transition_d,
                       buy_target_price,
                       sell_target_price
                FROM v_n6_board_condition_display_basis
                WHERE display_status = 'visible'
                  AND quality_status IN ('passed', 'warning', 'pending')
                  AND board_code LIKE '881%%'
                  AND period_transition_y = 'volume_up'
                  AND period_transition_q = 'volume_up'
                  AND period_transition_m = 'volume_up'
                ORDER BY updated_at DESC, board_code ASC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]

    def fetch_filter_profile(self, user_id: int) -> dict[str, Any] | None:
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT enable_chase,
                       enable_ultra_short,
                       enable_short,
                       enable_mid,
                       enable_long
                FROM user_filter_profile
                WHERE user_id = %s
                  AND is_default = true
                  AND status = 'active'
                ORDER BY user_filter_profile_id ASC
                LIMIT 1
                """,
                (user_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def fetch_users_for_admin(self) -> list[dict[str, Any]]:
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.user_id,
                       u.login_name,
                       u.display_name,
                       u.role,
                       u.status,
                       u.last_login_at,
                       u.created_at,
                       count(DISTINCT fp.user_filter_profile_id)::int AS filter_profile_count,
                       count(DISTINCT sa.user_sim_account_id)::int AS sim_account_count,
                       count(DISTINCT sp.user_sim_position_id)::int AS active_position_count
                FROM user_account u
                LEFT JOIN user_filter_profile fp
                  ON fp.user_id = u.user_id
                 AND fp.status = 'active'
                LEFT JOIN user_sim_account sa
                  ON sa.user_id = u.user_id
                 AND sa.account_status = 'active'
                LEFT JOIN user_sim_position sp
                  ON sp.user_id = u.user_id
                 AND sp.total_qty > 0
                GROUP BY u.user_id, u.login_name, u.display_name, u.role, u.status, u.last_login_at, u.created_at
                ORDER BY u.user_id ASC
                LIMIT 100
                """
            )
            return [dict(row) for row in cur.fetchall()]

    def create_user_with_defaults(
        self,
        *,
        login_name: str,
        display_name: str | None,
        role: str,
        password_hash: str,
        password_hash_algo: str,
        created_by_user_id: int,
    ) -> dict[str, Any]:
        try:
            with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
                with conn.transaction(), conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO user_account (
                          login_name,
                          display_name,
                          password_hash,
                          password_hash_algo,
                          role,
                          status,
                          created_by_user_id,
                          user_policy_json
                        )
                        VALUES (%s, %s, %s, %s, %s, 'active', %s, %s)
                        RETURNING user_id, login_name, display_name, role, status, created_at, last_login_at
                        """,
                        (
                            login_name,
                            display_name,
                            password_hash,
                            password_hash_algo,
                            role,
                            created_by_user_id,
                            Jsonb({"n6_web_created": True}),
                        ),
                    )
                    user_row = dict(cur.fetchone())
                    user_id = int(user_row["user_id"])
                    cur.execute(
                        """
                        INSERT INTO user_filter_profile (
                          user_id,
                          profile_name,
                          is_default,
                          enable_chase,
                          enable_ultra_short,
                          enable_short,
                          enable_mid,
                          enable_long,
                          permission_scope,
                          status
                        )
                        VALUES (%s, %s, true, true, true, true, true, true, 'self', 'active')
                        """,
                        (user_id, DEFAULT_PROFILE_NAME),
                    )
                    cur.execute(
                        """
                        INSERT INTO user_sim_account (
                          user_id,
                          account_name,
                          initial_cash,
                          cash_balance,
                          frozen_cash,
                          settlement_mode,
                          account_status,
                          sim_policy_json
                        )
                        VALUES (%s, %s, %s, %s, 0, 'T_PLUS_1', 'active', %s)
                        """,
                        (
                            user_id,
                            DEFAULT_SIM_ACCOUNT_NAME,
                            DEFAULT_INITIAL_CASH,
                            DEFAULT_INITIAL_CASH,
                            Jsonb({"shadow_only": True, "real_trade_submitted": False}),
                        ),
                    )
        except psycopg.errors.UniqueViolation as exc:
            raise UserManagementError("login_name_exists") from exc
        user_row["filter_profile_count"] = 1
        user_row["sim_account_count"] = 1
        user_row["active_position_count"] = 0
        return user_row

    def delete_user(self, *, target_user_id: int, deleted_by_user_id: int) -> dict[str, Any]:
        with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE user_account
                    SET status = 'deleted',
                        deleted_by_user_id = %s,
                        deleted_at = now(),
                        updated_at = now()
                    WHERE user_id = %s
                      AND status <> 'deleted'
                    RETURNING user_id, login_name, display_name, role, status, created_at, last_login_at
                    """,
                    (deleted_by_user_id, target_user_id),
                )
                row = cur.fetchone()
                if row is None:
                    raise UserManagementError("user_not_found")
                cur.execute(
                    """
                    UPDATE user_session
                    SET revoked_at = COALESCE(revoked_at, now()),
                        updated_at = now()
                    WHERE user_id = %s
                      AND revoked_at IS NULL
                    """,
                    (target_user_id,),
                )
                cur.execute(
                    """
                    UPDATE user_filter_profile
                    SET status = 'deleted',
                        updated_at = now()
                    WHERE user_id = %s
                      AND status <> 'deleted'
                    """,
                    (target_user_id,),
                )
                cur.execute(
                    """
                    UPDATE user_sim_account
                    SET account_status = 'deleted',
                        updated_at = now()
                    WHERE user_id = %s
                      AND account_status <> 'deleted'
                    """,
                    (target_user_id,),
                )
        result = dict(row)
        result["filter_profile_count"] = 0
        result["sim_account_count"] = 0
        result["active_position_count"] = 0
        return result

    def fetch_sim_account(self, user_id: int) -> dict[str, Any] | None:
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_sim_account_id,
                       account_name,
                       initial_cash,
                       cash_balance,
                       frozen_cash,
                       settlement_mode,
                       account_status
                FROM user_sim_account
                WHERE user_id = %s
                  AND account_status = 'active'
                ORDER BY user_sim_account_id ASC
                LIMIT 1
                """,
                (user_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def fetch_sim_positions(self, user_id: int) -> list[dict[str, Any]]:
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT code,
                       name,
                       total_qty,
                       available_qty,
                       t_plus_one_locked_qty,
                       avg_cost,
                       last_price,
                       market_value,
                       unrealized_pnl
                FROM user_sim_position
                WHERE user_id = %s
                  AND total_qty > 0
                ORDER BY updated_at DESC, user_sim_position_id ASC
                LIMIT 200
                """,
                (user_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def fetch_ui_v1_signals(
        self,
        user_id: int,
        filters: dict[str, Any],
        limit: int,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where_sql, params = self._ui_v1_signal_where(user_id, filters)
        params["limit"] = max(1, min(int(limit), 500))
        params["offset"] = max(0, int(offset))
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {self._ui_v1_signal_select_list()}
                {self._ui_v1_signal_from_sql()}
                WHERE {where_sql}
                ORDER BY p.created_at DESC, p.user_signal_projection_id DESC
                LIMIT %(limit)s
                OFFSET %(offset)s
                """,
                params,
            )
            return [dict(row) for row in cur.fetchall()]

    def count_ui_v1_signals(self, user_id: int, filters: dict[str, Any]) -> int:
        where_sql, params = self._ui_v1_signal_where(user_id, filters)
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT count(*)::int AS count
                {self._ui_v1_signal_from_sql()}
                WHERE {where_sql}
                """,
                params,
            )
            row = cur.fetchone() or {}
        return int(row.get("count") or 0)

    def fetch_ui_v1_signal_statistics(self, user_id: int) -> dict[str, Any]:
        where_sql, params = self._ui_v1_signal_where(user_id, {})
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT count(*)::int AS total_count,
                       count(*) FILTER (WHERE {self._ui_v1_event_type_expr()} = 'ActionExecuted')::int AS action_executed,
                       count(*) FILTER (WHERE {self._ui_v1_event_type_expr()} = 'ActionBlocked')::int AS action_blocked,
                       0::int AS trigger_matched
                {self._ui_v1_signal_from_sql()}
                WHERE {where_sql}
                """,
                params,
            )
            counts = dict(cur.fetchone() or {})

            cur.execute(
                f"""
                SELECT {self._ui_v1_blocked_reason_expr()} AS blocked_reason,
                       count(*)::int AS count
                {self._ui_v1_signal_from_sql()}
                WHERE {where_sql}
                  AND {self._ui_v1_blocked_reason_expr()} IS NOT NULL
                GROUP BY blocked_reason
                """,
                params,
            )
            reasons = {
                str(row["blocked_reason"]): int(row["count"])
                for row in cur.fetchall()
                if row.get("blocked_reason")
            }
        return {
            "total_count": int(counts.get("total_count") or 0),
            "ActionExecuted": int(counts.get("action_executed") or 0),
            "ActionBlocked": int(counts.get("action_blocked") or 0),
            "TriggerMatched": int(counts.get("trigger_matched") or 0),
            "blocked_reason_distribution": reasons,
        }

    def fetch_ui_v1_lineage_stats(self, user_id: int) -> dict[str, Any]:
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT event_type, status, count(*)::int AS count
                FROM common_event_outbox
                WHERE source_run_id = %s
                  AND event_type IN (
                      'TriggerMatched',
                      'TriggerPendingMarketData',
                      'TriggerStateChanged',
                      'TriggerCleared',
                      'TriggerLiveChanged'
                  )
                  AND status = 'pending'
                GROUP BY event_type, status
                """,
                (N6_UI_V1_LINEAGE_N4_RUN_ID,),
            )
            n4_counts = {
                (str(row["event_type"]), str(row["status"])): int(row["count"])
                for row in cur.fetchall()
            }
            cur.execute(
                """
                SELECT event_type, status, count(*)::int AS count
                FROM common_event_outbox
                WHERE source_run_id = %s
                  AND event_type IN ('ActionExecuted', 'ActionBlocked')
                  AND status = 'pending'
                GROUP BY event_type, status
                """,
                (N6_UI_V1_LINEAGE_N5_RUN_ID,),
            )
            n5_counts = {
                (str(row["event_type"]), str(row["status"])): int(row["count"])
                for row in cur.fetchall()
            }
            cur.execute(
                f"""
                SELECT {self._ui_v1_blocked_reason_expr()} AS blocked_reason,
                       count(*)::int AS count
                {self._ui_v1_signal_from_sql()}
                WHERE p.user_id = %s
                  AND p.user_projection_run_id = %s
                  AND p.source_action_run_id = %s
                  AND {self._ui_v1_event_type_expr()} = 'ActionBlocked'
                  AND {self._ui_v1_blocked_reason_expr()} IS NOT NULL
                GROUP BY blocked_reason
                """,
                (user_id, N6_UI_V1_LINEAGE_N6_RUN_ID, N6_UI_V1_LINEAGE_N5_RUN_ID),
            )
            blocked_reason = {
                str(row["blocked_reason"]): int(row["count"])
                for row in cur.fetchall()
                if row.get("blocked_reason")
            }
        return {
            "source_runs": {
                "N4": N6_UI_V1_LINEAGE_N4_RUN_ID,
                "N5": N6_UI_V1_LINEAGE_N5_RUN_ID,
                "N6": N6_UI_V1_LINEAGE_N6_RUN_ID,
            },
            "lineage_stats": {
                "N4": {
                    "TriggerMatched": {
                        "pending": n4_counts.get(("TriggerMatched", "pending"), 0)
                    },
                    "TriggerPendingMarketData": {
                        "pending": n4_counts.get(("TriggerPendingMarketData", "pending"), 0)
                    },
                    "TriggerStateChanged": {
                        "pending": n4_counts.get(("TriggerStateChanged", "pending"), 0)
                    },
                },
                "N5": {
                    "ActionExecuted": {
                        "pending": n5_counts.get(("ActionExecuted", "pending"), 0)
                    },
                    "ActionBlocked": {
                        "pending": n5_counts.get(("ActionBlocked", "pending"), 0)
                    },
                },
            },
            "legacy": {
                "N4": {
                    "TriggerCleared": {
                        "pending": n4_counts.get(("TriggerCleared", "pending"), 0),
                        "display": "hidden_by_default",
                    },
                    "TriggerLiveChanged": {
                        "pending": n4_counts.get(("TriggerLiveChanged", "pending"), 0),
                        "display": "hidden_by_default",
                    },
                }
            },
            "blocked_reason": blocked_reason,
        }

    def fetch_ui_v1_n3_messages(
        self,
        *,
        filters: dict[str, Any] | None = None,
        limit: int,
        include_all: bool = False,
    ) -> dict[str, Any]:
        effective_limit = max(1, min(int(limit or N3_MESSAGE_DEFAULT_LIMIT), 5000))
        filters = filters or {}
        with self._readonly_connection() as conn, conn.cursor() as cur:
            latest_event_date = self._raw_message_latest_event_date(
                cur, "N3_market_data", N3_MESSAGE_EVENT_TYPES, filters
            )
            effective_filters, date_filter_defaulted = self._raw_message_effective_filters(
                filters,
                include_all=include_all,
                latest_event_date=latest_event_date,
            )
            where, params = self._raw_message_where("N3_market_data", N3_MESSAGE_EVENT_TYPES, effective_filters)
            cur.execute(
                """
                SELECT count(*)::int AS count
                FROM common_event_outbox
                WHERE source_layer = 'N3_market_data'
                  AND event_type = ANY(%s)
                """,
                (list(N3_MESSAGE_EVENT_TYPES),),
            )
            total_count = int((cur.fetchone() or {}).get("count") or 0)
            filtered_count = self._raw_message_count(cur, where, params)
            summary = self._n3_message_summary(cur, where, params)

            where_sql = " AND ".join(where)
            if include_all:
                cur.execute(
                    f"""
                    SELECT outbox_id,
                           event_id,
                           event_type,
                           event_schema_version,
                           trade_date,
                           asset_kind,
                           identity_key,
                           event_time,
                           source_layer,
                           source_run_id,
                           dedup_key,
                           partition_key,
                           payload_json,
                           status,
                           attempt_count,
                           created_at,
                           updated_at
                    FROM common_event_outbox
                    WHERE {where_sql}
                    ORDER BY event_time DESC, created_at DESC, outbox_id DESC
                    LIMIT %s
                    """,
                    tuple(params + [effective_limit]),
                )
            else:
                cur.execute(
                    f"""
                    SELECT outbox_id,
                           event_id,
                           event_type,
                           event_schema_version,
                           trade_date,
                           asset_kind,
                           identity_key,
                           event_time,
                           source_layer,
                           source_run_id,
                           dedup_key,
                           partition_key,
                           payload_json,
                           status,
                           attempt_count,
                           created_at,
                           updated_at
                    FROM common_event_outbox
                    WHERE {where_sql}
                    ORDER BY event_time DESC, created_at DESC, outbox_id DESC
                    LIMIT %s
                    """,
                    tuple(params + [effective_limit]),
                )
            rows = [dict(row) for row in cur.fetchall()]
        return {
            "total_count": total_count,
            "filtered_count": filtered_count,
            "returned_count": len(rows),
            "default_limit": effective_limit,
            "include_all": include_all,
            "filters": {key: value for key, value in effective_filters.items() if value},
            "latest_event_date": latest_event_date,
            "date_filter_defaulted": date_filter_defaulted,
            "event_types": list(N3_MESSAGE_EVENT_TYPES),
            "summary": summary,
            "items": rows,
        }

    def fetch_ui_v1_n4_messages(
        self,
        *,
        filters: dict[str, Any] | None = None,
        limit: int,
        include_all: bool = False,
    ) -> dict[str, Any]:
        effective_limit = max(1, min(int(limit or N4_MESSAGE_DEFAULT_LIMIT), 5000))
        filters = filters or {}
        with self._readonly_connection() as conn, conn.cursor() as cur:
            latest_event_date = self._raw_message_latest_event_date(cur, "N4_trigger", N4_ALL_EVENT_TYPES, filters)
            effective_filters, date_filter_defaulted = self._raw_message_effective_filters(
                filters,
                include_all=include_all,
                latest_event_date=latest_event_date,
            )
            effective_filters = self._raw_message_active_lineage_filters(
                "N4_trigger",
                effective_filters,
                include_all=include_all,
            )
            where, params = self._raw_message_where("N4_trigger", N4_ALL_EVENT_TYPES, effective_filters)
            cur.execute(
                """
                SELECT count(*)::int AS count
                FROM common_event_outbox
                WHERE source_layer = 'N4_trigger'
                  AND event_type = ANY(%s)
                """,
                (list(N4_ALL_EVENT_TYPES),),
            )
            total_count = int((cur.fetchone() or {}).get("count") or 0)
            filtered_count = self._raw_message_count(cur, where, params)
            summary = self._raw_message_summary(cur, where, params, N5_LEGACY_EVENT_TYPES)

            where_sql = " AND ".join(where)
            if include_all:
                cur.execute(
                    f"""
                    SELECT outbox_id,
                           event_id,
                           event_type,
                           event_schema_version,
                           trade_date,
                           asset_kind,
                           identity_key,
                           event_time,
                           source_layer,
                           source_run_id,
                           dedup_key,
                           partition_key,
                           payload_json,
                           status,
                           attempt_count,
                           created_at,
                           updated_at
                    FROM common_event_outbox
                    WHERE {where_sql}
                    ORDER BY event_time DESC, created_at DESC, outbox_id DESC
                    LIMIT %s
                    """,
                    tuple(params + [effective_limit]),
                )
            else:
                cur.execute(
                    f"""
                    SELECT outbox_id,
                           event_id,
                           event_type,
                           event_schema_version,
                           trade_date,
                           asset_kind,
                           identity_key,
                           event_time,
                           source_layer,
                           source_run_id,
                           dedup_key,
                           partition_key,
                           payload_json,
                           status,
                           attempt_count,
                           created_at,
                           updated_at
                    FROM common_event_outbox
                    WHERE {where_sql}
                    ORDER BY event_time DESC, created_at DESC, outbox_id DESC
                    LIMIT %s
                    """,
                    tuple(params + [effective_limit]),
                )
            rows = [dict(row) for row in cur.fetchall()]
        return {
            "total_count": total_count,
            "filtered_count": filtered_count,
            "returned_count": len(rows),
            "default_limit": effective_limit,
            "include_all": include_all,
            "filters": {key: value for key, value in effective_filters.items() if value},
            "latest_event_date": latest_event_date,
            "date_filter_defaulted": date_filter_defaulted,
            "event_types": list(N4_ALL_EVENT_TYPES),
            "standard_event_types": list(N4_STANDARD_EVENT_TYPES),
            "legacy_event_types": list(N4_LEGACY_EVENT_TYPES),
            "items": rows,
        }

    def fetch_ui_v1_n5_messages(
        self,
        *,
        filters: dict[str, Any] | None = None,
        limit: int,
        include_all: bool = False,
    ) -> dict[str, Any]:
        effective_limit = max(1, min(int(limit or N5_MESSAGE_DEFAULT_LIMIT), 5000))
        filters = filters or {}
        with self._readonly_connection() as conn, conn.cursor() as cur:
            latest_event_date = self._raw_message_latest_event_date(cur, "N5_action", N5_ALL_EVENT_TYPES, filters)
            effective_filters, date_filter_defaulted = self._raw_message_effective_filters(
                filters,
                include_all=include_all,
                latest_event_date=latest_event_date,
            )
            effective_filters = self._raw_message_active_lineage_filters(
                "N5_action",
                effective_filters,
                include_all=include_all,
            )
            where, params = self._raw_message_where("N5_action", N5_ALL_EVENT_TYPES, effective_filters)
            cur.execute(
                """
                SELECT count(*)::int AS count
                FROM common_event_outbox
                WHERE source_layer = 'N5_action'
                  AND event_type = ANY(%s)
                """,
                (list(N5_ALL_EVENT_TYPES),),
            )
            total_count = int((cur.fetchone() or {}).get("count") or 0)
            filtered_count = self._raw_message_count(cur, where, params)
            summary = self._raw_message_summary(cur, where, params, N5_LEGACY_EVENT_TYPES)

            where_sql = " AND ".join(where)
            if include_all:
                cur.execute(
                    f"""
                    SELECT outbox_id,
                           event_id,
                           event_type,
                           event_schema_version,
                           trade_date,
                           asset_kind,
                           identity_key,
                           event_time,
                           source_layer,
                           source_run_id,
                           dedup_key,
                           partition_key,
                           payload_json,
                           status,
                           attempt_count,
                           created_at,
                           updated_at
                    FROM common_event_outbox
                    WHERE {where_sql}
                    ORDER BY event_time DESC, created_at DESC, outbox_id DESC
                    LIMIT %s
                    """,
                    tuple(params + [effective_limit]),
                )
            else:
                cur.execute(
                    f"""
                    SELECT outbox_id,
                           event_id,
                           event_type,
                           event_schema_version,
                           trade_date,
                           asset_kind,
                           identity_key,
                           event_time,
                           source_layer,
                           source_run_id,
                           dedup_key,
                           partition_key,
                           payload_json,
                           status,
                           attempt_count,
                           created_at,
                           updated_at
                    FROM common_event_outbox
                    WHERE {where_sql}
                    ORDER BY event_time DESC, created_at DESC, outbox_id DESC
                    LIMIT %s
                    """,
                    tuple(params + [effective_limit]),
                )
            rows = [dict(row) for row in cur.fetchall()]
        return {
            "total_count": total_count,
            "filtered_count": filtered_count,
            "returned_count": len(rows),
            "default_limit": effective_limit,
            "include_all": include_all,
            "filters": {key: value for key, value in effective_filters.items() if value},
            "latest_event_date": latest_event_date,
            "date_filter_defaulted": date_filter_defaulted,
            "event_types": list(N5_ALL_EVENT_TYPES),
            "standard_event_types": list(N5_STANDARD_EVENT_TYPES),
            "legacy_event_types": list(N5_LEGACY_EVENT_TYPES),
            "summary": summary,
            "items": rows,
        }

    def _latest_passed_n5_action_run_id(self, cur: Any) -> str | None:
        cur.execute(
            """
            SELECT run_id
            FROM common_action_run
            WHERE status = 'passed'
            ORDER BY finished_at DESC NULLS LAST,
                     updated_at DESC NULLS LAST,
                     started_at DESC NULLS LAST,
                     created_at DESC NULLS LAST,
                     run_id DESC
            LIMIT 1
            """
        )
        row = cur.fetchone() or {}
        return row.get("run_id")

    def _n5_action_display_where(
        self,
        *,
        target_run_id: str,
        filters: dict[str, Any],
    ) -> tuple[list[str], list[Any]]:
        where = [
            "source_layer = 'N5_action'",
            "event_type = ANY(%s)",
            "source_run_id = %s",
        ]
        params: list[Any] = [list(N5_ACTION_DISPLAY_EVENT_TYPES), target_run_id]
        event_type = filters.get("event_type")
        if event_type:
            where.append("event_type = %s")
            params.append(event_type)
        status = filters.get("status")
        if status:
            where.append("status = %s")
            params.append(status)
        asset_kind = filters.get("asset_kind")
        if asset_kind:
            where.append("asset_kind = %s")
            params.append(asset_kind)
        action_state = filters.get("action_state")
        if action_state:
            where.append("payload_json ->> 'action_state' = %s")
            params.append(action_state)
        keyword = str(filters.get("q") or "").strip()
        if keyword:
            like = f"%{keyword}%"
            where.append(
                """
                (
                  identity_key ILIKE %s
                  OR event_id ILIKE %s
                  OR source_run_id ILIKE %s
                  OR COALESCE(payload_json ->> 'action_key', '') ILIKE %s
                  OR COALESCE(payload_json ->> 'condition_key', '') ILIKE %s
                  OR COALESCE(payload_json #>> '{trace_json,live_window_confirmation,selected_metric_id}', '') ILIKE %s
                )
                """
            )
            params.extend([like, like, like, like, like, like])
        return where, params

    def fetch_ui_v1_n5_actions(
        self,
        *,
        filters: dict[str, Any] | None = None,
        limit: int,
    ) -> dict[str, Any]:
        effective_limit = max(1, min(int(limit or N5_MESSAGE_DEFAULT_LIMIT), 5000))
        filters = filters or {}
        with self._readonly_connection() as conn, conn.cursor() as cur:
            target_run_id = (
                filters.get("action_run_id")
                or filters.get("source_run_id")
                or self._latest_passed_n5_action_run_id(cur)
            )
            if not target_run_id:
                return n5_actions_empty_model(filters=filters, limit=effective_limit)
            base_where = [
                "source_layer = 'N5_action'",
                "event_type = ANY(%s)",
                "source_run_id = %s",
            ]
            base_params = [list(N5_ACTION_DISPLAY_EVENT_TYPES), target_run_id]
            cur.execute(
                f"""
                SELECT count(*)::int AS count
                FROM common_event_outbox
                WHERE {" AND ".join(base_where)}
                """,
                tuple(base_params),
            )
            total_count = int((cur.fetchone() or {}).get("count") or 0)
            where, params = self._n5_action_display_where(target_run_id=target_run_id, filters=filters)
            where_sql = " AND ".join(where)
            cur.execute(
                f"""
                SELECT count(*)::int AS total,
                       count(*) FILTER (WHERE status = 'pending')::int AS pending,
                       count(*) FILTER (WHERE event_type = 'ActionExecuted')::int AS action_executed,
                       count(*) FILTER (WHERE event_type = 'ActionEligible')::int AS action_eligible
                FROM common_event_outbox
                WHERE {where_sql}
                """,
                tuple(params),
            )
            summary_row = cur.fetchone() or {}
            filtered_count = int(summary_row.get("total") or 0)
            cur.execute(
                f"""
                SELECT outbox_id,
                       event_id,
                       event_type,
                       event_schema_version,
                       trade_date,
                       asset_kind,
                       identity_key,
                       event_time,
                       source_layer,
                       source_run_id,
                       dedup_key,
                       partition_key,
                       payload_json,
                       status,
                       attempt_count,
                       created_at,
                       updated_at
                FROM common_event_outbox
                WHERE {where_sql}
                ORDER BY event_time DESC, created_at DESC, outbox_id DESC
                LIMIT %s
                """,
                tuple(params + [effective_limit]),
            )
            rows = [dict(row) for row in cur.fetchall()]
        effective_filters = {
            key: value
            for key, value in dict(filters, action_run_id=target_run_id, source_run_id=target_run_id).items()
            if value
        }
        items = [n5_action_display_item(row) for row in rows]
        return {
            "ok": True,
            "component": "N5 Actions",
            "title": "N5动作",
            "source_layer": "N5_action",
            "action_run_id": target_run_id,
            "source_run_id": target_run_id,
            "total_count": total_count,
            "filtered_count": filtered_count,
            "returned_count": len(items),
            "default_limit": effective_limit,
            "filters": effective_filters,
            "filter_inputs": {
                "action_run_id": str(filters.get("action_run_id") or ""),
                "source_run_id": str(filters.get("source_run_id") or ""),
                "event_type": str(filters.get("event_type") or ""),
                "status": str(filters.get("status") or ""),
                "asset_kind": str(filters.get("asset_kind") or ""),
                "action_state": str(filters.get("action_state") or ""),
                "q": str(filters.get("q") or ""),
            },
            "event_types": list(N5_ACTION_DISPLAY_EVENT_TYPES),
            "action_states": ["executed", "eligible"],
            "summary": {
                "total": filtered_count,
                "pending": int(summary_row.get("pending") or 0),
                "ActionExecuted": int(summary_row.get("action_executed") or 0),
                "ActionEligible": int(summary_row.get("action_eligible") or 0),
            },
            "items": items,
            "side_effects": n5_actions_read_only_side_effects(),
        }

    def _latest_b_track_buy_signal_action_run_id(self, cur: Any) -> str | None:
        cur.execute(
            """
            SELECT r.run_id
            FROM common_action_run r
            WHERE r.status = 'passed'
              AND EXISTS (
                  SELECT 1
                  FROM common_event_outbox e
                  WHERE e.source_layer = 'N5_action'
                    AND e.source_run_id = r.run_id
                    AND e.event_type = 'ActionEligible'
                    AND e.payload_json ->> 'provisional' = 'true'
                    AND e.payload_json ->> 'action_confirmation_mode' = 'eligibility_only'
              )
            ORDER BY r.finished_at DESC NULLS LAST,
                     r.updated_at DESC NULLS LAST,
                     r.started_at DESC NULLS LAST,
                     r.created_at DESC NULLS LAST,
                     r.run_id DESC
            LIMIT 1
            """
        )
        row = cur.fetchone() or {}
        return row.get("run_id")

    def _b_track_buy_signal_where(
        self,
        *,
        target_run_id: str,
        filters: dict[str, Any],
        include_action_type: bool,
    ) -> tuple[list[str], list[Any]]:
        where = [
            "source_layer = 'N5_action'",
            "event_type = 'ActionEligible'",
            "source_run_id = %s",
            "payload_json ->> 'provisional' = 'true'",
            "payload_json ->> 'action_confirmation_mode' = 'eligibility_only'",
        ]
        params: list[Any] = [target_run_id]
        action_type = normalize_b_track_buy_signal_action_type(filters.get("action_type"))
        if include_action_type and action_type != "all":
            where.append("payload_json ->> 'action_type' = %s")
            params.append(action_type)
        keyword = str(filters.get("q") or "").strip()
        if keyword:
            like = f"%{keyword}%"
            where.append(
                """
                (
                  identity_key ILIKE %s
                  OR event_id ILIKE %s
                  OR source_run_id ILIKE %s
                  OR COALESCE(payload_json ->> 'projection_id', '') ILIKE %s
                  OR COALESCE(payload_json ->> 'projection_run_id', '') ILIKE %s
                  OR COALESCE(payload_json ->> 'source_trigger_event_id', '') ILIKE %s
                  OR COALESCE(payload_json ->> 'condition_key', '') ILIKE %s
                  OR COALESCE(payload_json ->> 'signal_type', '') ILIKE %s
                )
                """
            )
            params.extend([like, like, like, like, like, like, like, like])
        return where, params

    def fetch_b_track_buy_signals(
        self,
        *,
        filters: dict[str, Any] | None = None,
        limit: int,
    ) -> dict[str, Any]:
        effective_limit = max(1, min(int(limit or N5_MESSAGE_DEFAULT_LIMIT), 5000))
        filters = filters or {}
        filters = {
            "action_run_id": filters.get("action_run_id"),
            "action_type": normalize_b_track_buy_signal_action_type(filters.get("action_type")),
            "q": filters.get("q"),
        }
        with self._readonly_connection() as conn, conn.cursor() as cur:
            target_run_id = filters.get("action_run_id") or self._latest_b_track_buy_signal_action_run_id(cur)
            if not target_run_id:
                return b_track_buy_signal_empty_model(filters=filters, limit=effective_limit)
            base_where, base_params = self._b_track_buy_signal_where(
                target_run_id=target_run_id,
                filters={**filters, "q": None},
                include_action_type=False,
            )
            cur.execute(
                f"""
                SELECT count(*)::int AS count
                FROM common_event_outbox
                WHERE {" AND ".join(base_where)}
                """,
                tuple(base_params),
            )
            total_count = int((cur.fetchone() or {}).get("count") or 0)
            where, params = self._b_track_buy_signal_where(
                target_run_id=target_run_id,
                filters=filters,
                include_action_type=True,
            )
            where_sql = " AND ".join(where)
            cur.execute(
                f"""
                SELECT count(*)::int AS total,
                       count(*) FILTER (WHERE payload_json ->> 'action_type' = 'buy')::int AS buy,
                       count(*) FILTER (WHERE payload_json ->> 'action_type' = 'sell')::int AS sell
                FROM common_event_outbox
                WHERE {where_sql}
                """,
                tuple(params),
            )
            summary_row = cur.fetchone() or {}
            filtered_count = int(summary_row.get("total") or 0)
            cur.execute(
                f"""
                SELECT outbox_id,
                       event_id,
                       event_type,
                       event_schema_version,
                       trade_date,
                       asset_kind,
                       identity_key,
                       event_time,
                       source_layer,
                       source_run_id,
                       dedup_key,
                       partition_key,
                       payload_json,
                       status,
                       attempt_count,
                       created_at,
                       updated_at
                FROM common_event_outbox
                WHERE {where_sql}
                ORDER BY event_time DESC, created_at DESC, outbox_id DESC
                LIMIT %s
                """,
                tuple(params + [effective_limit]),
            )
            rows = [dict(row) for row in cur.fetchall()]
        items = [b_track_buy_signal_item(row) for row in rows]
        effective_filters = {
            key: value
            for key, value in {
                "action_run_id": target_run_id,
                "action_type": filters.get("action_type") or "buy",
                "q": filters.get("q"),
            }.items()
            if value
        }
        return {
            "ok": True,
            "component": "B Track Buy Signals",
            "title": "B轨买入信号",
            "source_layer": "N5_action",
            "action_run_id": target_run_id,
            "total_count": total_count,
            "filtered_count": filtered_count,
            "returned_count": len(items),
            "default_limit": effective_limit,
            "filters": effective_filters,
            "filter_inputs": {
                "action_run_id": str(filters.get("action_run_id") or ""),
                "action_type": str(filters.get("action_type") or "buy"),
                "q": str(filters.get("q") or ""),
            },
            "action_types": list(B_TRACK_BUY_SIGNAL_ACTION_TYPES),
            "summary": {
                "total": filtered_count,
                "buy": int(summary_row.get("buy") or 0),
                "sell": int(summary_row.get("sell") or 0),
                "ActionEligible": filtered_count,
                "ActionExecuted": 0,
                "ActionBlocked": 0,
                "ActionSkipped": 0,
            },
            "items": items,
            "side_effects": b_track_buy_signal_read_only_side_effects(),
        }

    def fetch_ui_v1_input_messages(
        self,
        *,
        filters: dict[str, Any] | None = None,
        limit: int,
        include_all: bool = False,
    ) -> dict[str, Any]:
        effective_limit = max(1, min(int(limit or N6_INPUT_MESSAGE_DEFAULT_LIMIT), 5000))
        filters = filters or {}
        with self._readonly_connection() as conn, conn.cursor() as cur:
            latest_event_date = self._input_message_latest_event_date(cur, filters)
            effective_filters, date_filter_defaulted = self._raw_message_effective_filters(
                filters,
                include_all=include_all,
                latest_event_date=latest_event_date,
            )
            where, params = self._input_message_where(effective_filters)
            total_where, total_params = self._input_message_where({})
            total_count = self._raw_message_count(cur, total_where, total_params)
            filtered_count = self._raw_message_count(cur, where, params)
            summary = self._input_message_summary(cur, where, params)
            where_sql = " AND ".join(where)
            if include_all:
                cur.execute(
                    f"""
                    SELECT outbox_id,
                           event_id,
                           event_type,
                           event_schema_version,
                           trade_date,
                           asset_kind,
                           identity_key,
                           event_time,
                           source_layer,
                           source_run_id,
                           dedup_key,
                           partition_key,
                           payload_json,
                           status,
                           attempt_count,
                           created_at,
                           updated_at
                    FROM common_event_outbox
                    WHERE {where_sql}
                    ORDER BY event_time DESC, created_at DESC, outbox_id DESC
                    LIMIT %s
                    """,
                    tuple(params + [effective_limit]),
                )
            else:
                cur.execute(
                    f"""
                    SELECT outbox_id,
                           event_id,
                           event_type,
                           event_schema_version,
                           trade_date,
                           asset_kind,
                           identity_key,
                           event_time,
                           source_layer,
                           source_run_id,
                           dedup_key,
                           partition_key,
                           payload_json,
                           status,
                           attempt_count,
                           created_at,
                           updated_at
                    FROM common_event_outbox
                    WHERE {where_sql}
                    ORDER BY event_time DESC, created_at DESC, outbox_id DESC
                    LIMIT %s
                    """,
                    tuple(params + [effective_limit]),
                )
            rows = [dict(row) for row in cur.fetchall()]
        return {
            "total_count": total_count,
            "filtered_count": filtered_count,
            "returned_count": len(rows),
            "default_limit": effective_limit,
            "include_all": include_all,
            "filters": {key: value for key, value in effective_filters.items() if value},
            "latest_event_date": latest_event_date,
            "date_filter_defaulted": date_filter_defaulted,
            "source_layers": ["N5_action", "N3_market_data"],
            "event_types": list(N5_ALL_EVENT_TYPES + N3_DISPLAY_INPUT_EVENT_TYPES),
            "n5_canonical_event_types": list(N5_STANDARD_EVENT_TYPES),
            "n5_legacy_event_types": list(N5_LEGACY_EVENT_TYPES),
            "n3_display_event_types": list(N3_DISPLAY_INPUT_EVENT_TYPES),
            "summary": summary,
            "items": rows,
        }

    def fetch_ui_v1_n2_condition_basis(
        self,
        *,
        asset_kind: str,
        filters: dict[str, Any] | None = None,
        limit: int,
        include_all: bool = False,
    ) -> dict[str, Any]:
        meta = n2_condition_basis_asset_meta(asset_kind)
        effective_limit = max(1, min(int(limit or N2_CONDITION_BASIS_DEFAULT_LIMIT), 5000))
        filters = filters or {}
        with self._readonly_connection() as conn, conn.cursor() as cur:
            latest_source_trade_date = self._n2_condition_basis_latest_source_trade_date(cur, meta, filters)
            effective_filters, date_filter_defaulted = self._n2_condition_basis_effective_filters(
                filters,
                include_all=include_all,
                latest_source_trade_date=latest_source_trade_date,
            )
            where, params = self._n2_condition_basis_where(meta, effective_filters)
            source_table = str(meta["source_table"])
            id_column = str(meta["id_column"])
            identity_column = str(meta["identity_column"])
            code_column = str(meta["code_column"])
            name_column = str(meta["name_column"])
            exchange_expr = str(meta["exchange_expr"])
            board_type_expr = str(meta["board_type_expr"])
            cur.execute(f"SELECT count(*)::int AS count FROM {source_table}")
            total_count = int((cur.fetchone() or {}).get("count") or 0)
            cur.execute(
                f"""
                SELECT count(*)::int AS count
                FROM {source_table} t
                WHERE {" AND ".join(where)}
                """,
                tuple(params),
            )
            filtered_count = int((cur.fetchone() or {}).get("count") or 0)

            where_sql = " AND ".join(where)
            select_sql = f"""
                SELECT '{asset_kind}' AS asset_kind,
                       '{meta["label"]}' AS asset_label,
                       '{source_table}' AS source_table,
                       t.{id_column} AS condition_basis_id,
                       t.run_id,
                       t.for_trade_date,
                       t.source_trade_date,
                       t.prev_trade_date,
                       t.{identity_column} AS identity_key,
                       t.{code_column} AS code,
                       {exchange_expr} AS exchange,
                       t.{name_column} AS name,
                       {board_type_expr} AS board_type,
                       t.lane,
                       t.monitor_type,
                       t.monitor_status,
                       t.direction_scope,
                       t.period_key_y,
                       t.period_key_q,
                       t.period_key_m,
                       t.period_key_w,
                       t.period_key_d,
                       t.period_grade_y,
                       t.period_grade_q,
                       t.period_grade_m,
                       t.period_grade_w,
                       t.period_grade_d,
                       t.amount_quality_status,
                       t.buy_target_price,
                       t.buy_expected_return_pct,
                       t.sell_target_price,
                       t.sell_expected_return_pct,
                       t.up_sell_reference_period,
                       t.down_buy_reference_period,
                       t.buy_necessary_key,
                       t.sell_necessary_key,
                       t.buy_full_necessary_key,
                       t.sell_full_necessary_key,
                       t.oversold_hint_key,
                       t.overbought_hint_key,
                       t.quality_status,
                       t.quality_reason,
                       t.source_version,
                       t.source_batch_id,
                       t.raw_json,
                       t.missing_fields_json,
                       t.period_trigger_baseline_json,
                       t.target_price_trace_json,
                       t.created_at,
                       t.updated_at,
                       to_jsonb(t) AS row_json
                FROM {source_table} t
                WHERE {where_sql}
                ORDER BY t.source_trade_date DESC, t.created_at DESC, t.{id_column} DESC
            """
            if include_all:
                cur.execute(select_sql, tuple(params))
            else:
                cur.execute(f"{select_sql} LIMIT %s", tuple(params + [effective_limit]))
            rows = [dict(row) for row in cur.fetchall()]
        return {
            "asset_kind": asset_kind,
            "asset_label": str(meta["label"]),
            "source_table": source_table,
            "total_count": total_count,
            "filtered_count": filtered_count,
            "returned_count": len(rows),
            "default_limit": effective_limit,
            "include_all": include_all,
            "filters": {key: value for key, value in effective_filters.items() if value},
            "latest_source_trade_date": latest_source_trade_date,
            "date_filter_defaulted": date_filter_defaulted,
            "asset_tabs": n2_condition_basis_asset_tabs(),
            "items": rows,
        }

    def fetch_ui_v1_n2_condition_basis_latest_export(self) -> dict[str, Any]:
        latest_dates: list[str] = []
        with self._readonly_connection() as conn, conn.cursor() as cur:
            for asset_kind in N2_CONDITION_BASIS_ASSET_ORDER:
                meta = n2_condition_basis_asset_meta(asset_kind)
                latest_source_trade_date = self._n2_condition_basis_latest_source_trade_date(cur, meta, {})
                if latest_source_trade_date:
                    latest_dates.append(str(latest_source_trade_date))
        latest_source_trade_date = max(latest_dates) if latest_dates else None
        assets: dict[str, Any] = {}
        for asset_kind in N2_CONDITION_BASIS_ASSET_ORDER:
            data = self.fetch_ui_v1_n2_condition_basis(
                asset_kind=asset_kind,
                filters={"source_trade_date": latest_source_trade_date} if latest_source_trade_date else {},
                limit=N2_CONDITION_BASIS_DEFAULT_LIMIT,
                include_all=True,
            )
            assets[asset_kind] = {
                "asset_kind": data.get("asset_kind"),
                "asset_label": data.get("asset_label"),
                "source_table": data.get("source_table"),
                "row_count": len(list(data.get("items") or [])),
                "items": list(data.get("items") or []),
            }
        return {
            "latest_source_trade_date": latest_source_trade_date,
            "assets": assets,
            "side_effects": dict(READ_ONLY_SIDE_EFFECTS),
        }

    def _n2_condition_basis_effective_filters(
        self,
        filters: dict[str, Any],
        *,
        include_all: bool,
        latest_source_trade_date: str | None,
    ) -> tuple[dict[str, Any], bool]:
        effective_filters = dict(filters)
        if include_all or effective_filters.get("source_trade_date") or not latest_source_trade_date:
            return effective_filters, False
        effective_filters["source_trade_date"] = latest_source_trade_date
        return effective_filters, True

    def _n2_condition_basis_latest_source_trade_date(
        self,
        cur: Any,
        meta: dict[str, str],
        filters: dict[str, Any],
    ) -> str | None:
        source_table = str(meta["source_table"])
        where, params = self._n2_condition_basis_where(
            meta,
            {key: value for key, value in filters.items() if key != "source_trade_date"},
        )
        cur.execute(
            f"""
            SELECT max(source_trade_date) AS latest_source_trade_date
            FROM {source_table} t
            WHERE {" AND ".join(where)}
            """,
            tuple(params),
        )
        row = cur.fetchone() or {}
        return row.get("latest_source_trade_date")

    def _n2_condition_basis_where(
        self,
        meta: dict[str, str],
        filters: dict[str, Any],
    ) -> tuple[list[str], list[Any]]:
        identity_column = str(meta["identity_column"])
        code_column = str(meta["code_column"])
        name_column = str(meta["name_column"])
        where = ["TRUE"]
        params: list[Any] = []
        source_trade_date = filters.get("source_trade_date")
        if source_trade_date:
            where.append("t.source_trade_date = %s")
            params.append(source_trade_date)
        condition_key = filters.get("condition_key")
        if condition_key:
            where.append(
                """
                %s IN (
                    t.buy_necessary_key,
                    t.sell_necessary_key,
                    t.buy_full_necessary_key,
                    t.sell_full_necessary_key,
                    t.oversold_hint_key,
                    t.overbought_hint_key
                )
                """
            )
            params.append(condition_key)
        quality_status = filters.get("quality_status")
        if quality_status:
            where.append("t.quality_status = %s")
            params.append(quality_status)
        keyword = filters.get("q")
        if keyword:
            where.append(
                f"""
                (
                    t.{identity_column} ILIKE %s OR
                    t.{code_column} ILIKE %s OR
                    t.{name_column} ILIKE %s OR
                    t.run_id ILIKE %s
                )
                """
            )
            pattern = f"%{keyword}%"
            params.extend([pattern, pattern, pattern, pattern])
        return where, params

    def _raw_message_effective_filters(
        self,
        filters: dict[str, Any],
        *,
        include_all: bool,
        latest_event_date: str | None,
    ) -> tuple[dict[str, Any], bool]:
        effective_filters = dict(filters)
        if include_all or effective_filters.get("event_date") or not latest_event_date:
            return effective_filters, False
        effective_filters["event_date"] = latest_event_date
        return effective_filters, True

    def _raw_message_active_lineage_filters(
        self,
        source_layer: str,
        filters: dict[str, Any],
        *,
        include_all: bool,
    ) -> dict[str, Any]:
        effective_filters = dict(filters)
        if include_all or effective_filters.get("source_run_id"):
            return effective_filters
        event_date = effective_filters.get("event_date")
        if not event_date:
            return effective_filters
        active_source_run_id = ACTIVE_RAW_MESSAGE_SOURCE_RUN_BY_LAYER_DATE.get((source_layer, str(event_date)))
        if active_source_run_id:
            effective_filters["source_run_id"] = active_source_run_id
        return effective_filters

    def _raw_message_latest_event_date(
        self,
        cur: Any,
        source_layer: str,
        event_types: tuple[str, ...],
        filters: dict[str, Any],
    ) -> str | None:
        where = ["source_layer = %s", "event_type = ANY(%s)"]
        params: list[Any] = [source_layer, list(event_types)]
        event_type = filters.get("event_type")
        if event_type:
            where.append("event_type = %s")
            params.append(event_type)
        status = filters.get("status")
        if status:
            where.append("status = %s")
            params.append(status)
        asset_kind = filters.get("asset_kind")
        if asset_kind:
            where.append("asset_kind = %s")
            params.append(asset_kind)
        source_run_id = filters.get("source_run_id")
        if source_run_id:
            where.append("source_run_id = %s")
            params.append(source_run_id)
        keyword = filters.get("q")
        if keyword:
            keyword_where, keyword_params = raw_message_keyword_predicate(keyword)
            where.append(keyword_where)
            params.extend(keyword_params)
        cur.execute(
            f"""
            SELECT max((event_time AT TIME ZONE 'Asia/Shanghai')::date)::text AS latest_event_date
            FROM common_event_outbox
            WHERE {" AND ".join(where)}
            """,
            tuple(params),
        )
        row = cur.fetchone() or {}
        return row.get("latest_event_date")

    def _raw_message_where(
        self,
        source_layer: str,
        event_types: tuple[str, ...],
        filters: dict[str, Any],
    ) -> tuple[list[str], list[Any]]:
        where = ["source_layer = %s", "event_type = ANY(%s)"]
        params: list[Any] = [source_layer, list(event_types)]
        event_type = filters.get("event_type")
        if event_type:
            where.append("event_type = %s")
            params.append(event_type)
        status = filters.get("status")
        if status:
            where.append("status = %s")
            params.append(status)
        asset_kind = filters.get("asset_kind")
        if asset_kind:
            where.append("asset_kind = %s")
            params.append(asset_kind)
        source_run_id = filters.get("source_run_id")
        if source_run_id:
            where.append("source_run_id = %s")
            params.append(source_run_id)
        keyword = filters.get("q")
        if keyword:
            keyword_where, keyword_params = raw_message_keyword_predicate(keyword)
            where.append(keyword_where)
            params.extend(keyword_params)
        event_date = filters.get("event_date")
        if event_date:
            start, end = raw_message_event_date_bounds(event_date)
            where.append("event_time >= %s AND event_time < %s")
            params.extend([start, end])
        return where, params

    def _raw_message_count(self, cur: Any, where: list[str], params: list[Any]) -> int:
        cur.execute(
            f"""
            SELECT count(*)::int AS count
            FROM common_event_outbox
            WHERE {" AND ".join(where)}
            """,
            tuple(params),
        )
        return int((cur.fetchone() or {}).get("count") or 0)

    def _raw_message_summary(
        self,
        cur: Any,
        where: list[str],
        params: list[Any],
        legacy_event_types: tuple[str, ...],
    ) -> dict[str, Any]:
        cur.execute(
            f"""
            SELECT count(*)::int AS total,
                   count(*) FILTER (WHERE status = 'pending')::int AS pending,
                   count(*) FILTER (WHERE event_type = 'ActionBlocked')::int AS action_blocked,
                   count(*) FILTER (WHERE event_type = 'ActionExecuted')::int AS action_executed,
                   count(*) FILTER (WHERE event_type = ANY(%s))::int AS legacy,
                   max(event_time) AS latest_event_time
            FROM common_event_outbox
            WHERE {" AND ".join(where)}
            """,
            tuple([list(legacy_event_types)] + list(params)),
        )
        row = cur.fetchone() or {}
        return {
            "total": int(row.get("total") or 0),
            "pending": int(row.get("pending") or 0),
            "ActionBlocked": int(row.get("action_blocked") or 0),
            "ActionExecuted": int(row.get("action_executed") or 0),
            "legacy": int(row.get("legacy") or 0),
            "latest_event_time": row.get("latest_event_time"),
        }

    def _n3_message_summary(self, cur: Any, where: list[str], params: list[Any]) -> dict[str, Any]:
        cur.execute(
            f"""
            SELECT count(*)::int AS total,
                   count(*) FILTER (WHERE status = 'pending')::int AS pending,
                   count(*) FILTER (WHERE event_type = 'MarketSnapshotUpdated')::int AS market_snapshot_updated,
                   count(*) FILTER (WHERE event_type = 'MinuteBarClosed')::int AS minute_bar_closed,
                   count(*) FILTER (WHERE event_type = 'MarketDisplaySnapshotUpdated')::int
                       AS market_display_snapshot_updated,
                   max(event_time) AS latest_event_time
            FROM common_event_outbox
            WHERE {" AND ".join(where)}
            """,
            tuple(params),
        )
        row = cur.fetchone() or {}
        return {
            "total": int(row.get("total") or 0),
            "pending": int(row.get("pending") or 0),
            "MarketSnapshotUpdated": int(row.get("market_snapshot_updated") or 0),
            "MinuteBarClosed": int(row.get("minute_bar_closed") or 0),
            "MarketDisplaySnapshotUpdated": int(row.get("market_display_snapshot_updated") or 0),
            "latest_event_time": row.get("latest_event_time"),
        }

    def _input_message_where(self, filters: dict[str, Any]) -> tuple[list[str], list[Any]]:
        where = [
            """(
                (source_layer = %s AND event_type = ANY(%s))
                OR (source_layer = %s AND event_type = ANY(%s))
            )"""
        ]
        params: list[Any] = [
            "N5_action",
            list(N5_ALL_EVENT_TYPES),
            "N3_market_data",
            list(N3_DISPLAY_INPUT_EVENT_TYPES),
        ]
        source_layer = filters.get("source_layer")
        if source_layer:
            where.append("source_layer = %s")
            params.append(source_layer)
        input_group = filters.get("input_group")
        if input_group == "n5_action":
            where.append("source_layer = %s")
            params.append("N5_action")
        elif input_group == "n3_display":
            where.append("(source_layer = %s AND event_type = ANY(%s))")
            params.extend(["N3_market_data", list(N3_DISPLAY_INPUT_EVENT_TYPES)])
        elif input_group == "legacy":
            where.append("(source_layer = %s AND event_type = ANY(%s))")
            params.extend(["N5_action", list(N5_LEGACY_EVENT_TYPES)])
        event_type = filters.get("event_type")
        if event_type:
            where.append("event_type = %s")
            params.append(event_type)
        status = filters.get("status")
        if status:
            where.append("status = %s")
            params.append(status)
        asset_kind = filters.get("asset_kind")
        if asset_kind:
            where.append("asset_kind = %s")
            params.append(asset_kind)
        keyword = filters.get("q")
        if keyword:
            keyword_where, keyword_params = raw_message_keyword_predicate(keyword)
            where.append(keyword_where)
            params.extend(keyword_params)
        event_date = filters.get("event_date")
        if event_date:
            start, end = raw_message_event_date_bounds(event_date)
            where.append("event_time >= %s AND event_time < %s")
            params.extend([start, end])
        return where, params

    def _input_message_latest_event_date(self, cur: Any, filters: dict[str, Any]) -> str | None:
        effective_filters = {key: value for key, value in dict(filters).items() if key != "event_date"}
        where, params = self._input_message_where(effective_filters)
        cur.execute(
            f"""
            SELECT max((event_time AT TIME ZONE 'Asia/Shanghai')::date)::text AS latest_event_date
            FROM common_event_outbox
            WHERE {" AND ".join(where)}
            """,
            tuple(params),
        )
        row = cur.fetchone() or {}
        return row.get("latest_event_date")

    def _input_message_summary(self, cur: Any, where: list[str], params: list[Any]) -> dict[str, Any]:
        cur.execute(
            f"""
            SELECT count(*)::int AS total,
                   count(*) FILTER (WHERE status = 'pending')::int AS pending,
                   count(*) FILTER (
                     WHERE source_layer = 'N5_action'
                       AND event_type = ANY(%s)
                   )::int AS n5_canonical,
                   count(*) FILTER (
                     WHERE source_layer = 'N5_action'
                       AND event_type = ANY(%s)
                   )::int AS n5_legacy,
                   count(*) FILTER (
                     WHERE source_layer = 'N3_market_data'
                       AND event_type = ANY(%s)
                   )::int AS n3_display_input,
                   max(event_time) AS latest_event_time
            FROM common_event_outbox
            WHERE {" AND ".join(where)}
            """,
            tuple(
                [
                    list(N5_STANDARD_EVENT_TYPES),
                    list(N5_LEGACY_EVENT_TYPES),
                    list(N3_DISPLAY_INPUT_EVENT_TYPES),
                ]
                + list(params)
            ),
        )
        row = cur.fetchone() or {}
        return {
            "total": int(row.get("total") or 0),
            "pending": int(row.get("pending") or 0),
            "n5_canonical": int(row.get("n5_canonical") or 0),
            "n5_legacy": int(row.get("n5_legacy") or 0),
            "n3_display_input": int(row.get("n3_display_input") or 0),
            "latest_event_time": row.get("latest_event_time"),
        }

    def fetch_ui_v1_status_monitor(
        self,
        user_id: int,
        filters: dict[str, Any],
        limit: int,
        offset: int = 0,
    ) -> dict[str, Any]:
        del user_id
        source_n4_run_id = str(filters.get("source_n4_run_id") or N6_UI_V1_LINEAGE_N4_RUN_ID)
        source_n5_run_id = str(filters.get("source_n5_run_id") or N6_UI_V1_LINEAGE_N5_RUN_ID)
        with self._readonly_connection() as conn, conn.cursor() as cur:
            n4_counts = self._status_monitor_counts(
                cur,
                source_run_id=source_n4_run_id,
                event_types=("TriggerMatched", "TriggerPendingMarketData", "TriggerStateChanged"),
            )
            n5_counts = self._status_monitor_counts(
                cur,
                source_run_id=source_n5_run_id,
                event_types=("ActionExecuted", "ActionBlocked"),
            )
            rows, filtered_count = self._status_monitor_rows(
                cur,
                filters=filters,
                source_n4_run_id=source_n4_run_id,
                source_n5_run_id=source_n5_run_id,
                limit=limit,
                offset=offset,
            )

        trigger_matched = n4_counts.get("TriggerMatched", 0)
        action_executed = n5_counts.get("ActionExecuted", 0)
        action_blocked = n5_counts.get("ActionBlocked", 0)
        pending_market_data = n4_counts.get("TriggerPendingMarketData", 0)
        trigger_state_changed = n4_counts.get("TriggerStateChanged", 0)
        unmatched = max(trigger_matched - action_executed - action_blocked, 0)
        return {
            "source_runs": {
                "N4": source_n4_run_id,
                "N5": source_n5_run_id,
            },
            "event_summary": {
                "N4": {
                    "TriggerMatched": {"pending": trigger_matched, "action_entry": True},
                    "TriggerPendingMarketData": {
                        "pending": pending_market_data,
                        "action_entry": False,
                    },
                    "TriggerStateChanged": {
                        "pending": trigger_state_changed,
                        "action_entry": False,
                    },
                },
                "N5": {
                    "ActionExecuted": {"pending": action_executed},
                    "ActionBlocked": {"pending": action_blocked},
                },
            },
            "relationship_summary": {
                "matched_to_action": {
                    "TriggerMatched": trigger_matched,
                    "ActionExecuted": action_executed,
                    "ActionBlocked": action_blocked,
                    "unmatched": unmatched,
                    "pass": unmatched == 0,
                },
                "status_only": {
                    "TriggerPendingMarketData_action_entries": 0,
                    "TriggerStateChanged_action_entries": 0,
                },
            },
            "status_summary": {
                "active": {"count": trigger_matched, "trigger_live": True},
                "pending_market_data": {"count": pending_market_data, "trigger_live": False},
                "inactive": {"count": 0, "trigger_live": False},
            },
            "items": rows,
            "pagination": {
                "total_count": trigger_matched + pending_market_data + trigger_state_changed,
                "filtered_count": filtered_count,
                "limit": limit,
                "offset": offset,
            },
        }

    def _status_monitor_counts(
        self,
        cur: Any,
        *,
        source_run_id: str,
        event_types: tuple[str, ...],
    ) -> dict[str, int]:
        cur.execute(
            """
            SELECT event_type, count(*)::int AS count
            FROM common_event_outbox
            WHERE source_run_id = %s
              AND event_type = ANY(%s)
              AND status = 'pending'
            GROUP BY event_type
            """,
            (source_run_id, list(event_types)),
        )
        return {str(row["event_type"]): int(row["count"]) for row in cur.fetchall()}

    def _status_monitor_rows(
        self,
        cur: Any,
        *,
        filters: dict[str, Any],
        source_n4_run_id: str,
        source_n5_run_id: str,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        n5_mode = (
            filters.get("source_layer") == "N5_action"
            or filters.get("action_event_type") in {"ActionExecuted", "ActionBlocked"}
            or filters.get("event_type") in {"ActionExecuted", "ActionBlocked"}
        )
        if n5_mode:
            return self._status_monitor_n5_rows(
                cur,
                filters=filters,
                source_run_id=source_n5_run_id,
                limit=limit,
                offset=offset,
            )
        return self._status_monitor_n4_rows(
            cur,
            filters=filters,
            source_run_id=source_n4_run_id,
            limit=limit,
            offset=offset,
        )

    def _status_monitor_n4_rows(
        self,
        cur: Any,
        *,
        filters: dict[str, Any],
        source_run_id: str,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        where = [
            "source_run_id = %s",
            "event_type IN ('TriggerMatched', 'TriggerPendingMarketData', 'TriggerStateChanged')",
            "status = 'pending'",
        ]
        params: list[Any] = [source_run_id]
        event_type = filters.get("event_type")
        status_filter = filters.get("status")
        if event_type in {"TriggerMatched", "TriggerPendingMarketData", "TriggerStateChanged"}:
            where.append("event_type = %s")
            params.append(event_type)
        elif status_filter == "active":
            where.append("event_type = 'TriggerMatched'")
        elif status_filter == "pending_market_data":
            where.append("event_type = 'TriggerPendingMarketData'")
        elif status_filter == "inactive":
            where.append("event_type = 'TriggerStateChanged'")
            where.append("payload_json->>'current_status' = 'inactive'")
        self._append_status_monitor_common_filters(where, params, filters)
        return self._execute_status_monitor_row_query(
            cur,
            where=where,
            params=params,
            limit=limit,
            offset=offset,
            source_layer_label="'N4_trigger'",
            select_extra="""
                CASE
                  WHEN event_type = 'TriggerMatched' THEN 'active'
                  WHEN event_type = 'TriggerPendingMarketData' THEN 'pending_market_data'
                  WHEN payload_json->>'current_status' = 'matched' THEN 'active'
                  WHEN payload_json->>'current_status' = 'pending_market_data' THEN 'pending_market_data'
                  WHEN payload_json->>'current_status' = 'inactive' THEN 'inactive'
                  ELSE 'inactive'
                END AS status_key,
                COALESCE(payload_json->>'current_status',
                  CASE WHEN event_type = 'TriggerMatched' THEN 'matched'
                       WHEN event_type = 'TriggerPendingMarketData' THEN 'pending_market_data'
                       ELSE NULL END
                ) AS current_status,
                COALESCE((payload_json->>'trigger_live')::boolean, event_type = 'TriggerMatched') AS trigger_live,
                NULL::text AS action_event_type,
                NULL::text AS action_state,
                NULL::text AS blocked_reason,
                NULL::text AS related_n4_event_id
            """,
        )

    def _status_monitor_n5_rows(
        self,
        cur: Any,
        *,
        filters: dict[str, Any],
        source_run_id: str,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        where = [
            "source_run_id = %s",
            "event_type IN ('ActionExecuted', 'ActionBlocked')",
            "status = 'pending'",
        ]
        params: list[Any] = [source_run_id]
        action_event_type = filters.get("action_event_type") or filters.get("event_type")
        if action_event_type in {"ActionExecuted", "ActionBlocked"}:
            where.append("event_type = %s")
            params.append(action_event_type)
        self._append_status_monitor_common_filters(where, params, filters)
        return self._execute_status_monitor_row_query(
            cur,
            where=where,
            params=params,
            limit=limit,
            offset=offset,
            source_layer_label="'N5_action'",
            select_extra="""
                'active'::text AS status_key,
                'matched'::text AS current_status,
                true AS trigger_live,
                event_type AS action_event_type,
                COALESCE(payload_json->>'action_state',
                  CASE WHEN event_type = 'ActionExecuted' THEN 'executed'
                       WHEN event_type = 'ActionBlocked' THEN 'blocked'
                       ELSE NULL END
                ) AS action_state,
                payload_json->>'blocked_reason' AS blocked_reason,
                COALESCE(payload_json->>'source_trigger_event_id',
                         payload_json->>'source_n4_event_id',
                         payload_json->>'source_event_id') AS related_n4_event_id
            """,
        )

    def _append_status_monitor_common_filters(
        self,
        where: list[str],
        params: list[Any],
        filters: dict[str, Any],
    ) -> None:
        for key, expression in (
            ("asset_kind", "asset_kind = %s"),
            ("direction", "payload_json->>'direction' = %s"),
            ("signal_type", "payload_json->>'signal_type' = %s"),
            ("trade_date", "trade_date::text = %s"),
        ):
            value = filters.get(key)
            if value:
                where.append(expression)
                params.append(value)
        keyword = filters.get("q")
        if keyword:
            where.append(
                """
                (
                  event_id ILIKE %s
                  OR identity_key ILIKE %s
                  OR payload_json->>'code' ILIKE %s
                  OR payload_json->>'condition_key' ILIKE %s
                )
                """
            )
            like = f"%{keyword}%"
            params.extend([like, like, like, like])

    def _execute_status_monitor_row_query(
        self,
        cur: Any,
        *,
        where: list[str],
        params: list[Any],
        limit: int,
        offset: int,
        source_layer_label: str,
        select_extra: str,
    ) -> tuple[list[dict[str, Any]], int]:
        where_sql = " AND ".join(where)
        cur.execute(
            f"""
            SELECT count(*)::int AS count
            FROM common_event_outbox
            WHERE {where_sql}
            """,
            tuple(params),
        )
        count_row = cur.fetchone() or {}
        filtered_count = int(count_row.get("count") or 0)
        cur.execute(
            f"""
            SELECT
                {source_layer_label} AS source_layer,
                event_type,
                event_id,
                status AS outbox_status,
                source_run_id,
                event_time,
                asset_kind,
                identity_key,
                payload_json->>'code' AS code,
                payload_json->>'name' AS name,
                payload_json->>'direction' AS direction,
                payload_json->>'signal_type' AS signal_type,
                COALESCE(payload_json->>'condition_key', payload_json->>'original_condition_key') AS condition_key,
                {select_extra}
            FROM common_event_outbox
            WHERE {where_sql}
            ORDER BY event_time DESC, event_id DESC
            LIMIT %s OFFSET %s
            """,
            tuple(params + [limit, offset]),
        )
        return [dict(row) for row in cur.fetchall()], filtered_count

    def fetch_ui_v1_signal_detail(self, user_id: int, user_signal_projection_id: int) -> dict[str, Any] | None:
        where_sql, params = self._ui_v1_signal_where(user_id, {})
        params["user_signal_projection_id"] = int(user_signal_projection_id)
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {self._ui_v1_signal_select_list()}
                {self._ui_v1_signal_from_sql()}
                WHERE {where_sql}
                  AND p.user_signal_projection_id = %(user_signal_projection_id)s
                LIMIT 1
                """,
                params,
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def fetch_ui_v1_dashboard_metrics(self, user_id: int) -> dict[str, Any]:
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                WITH scoped AS (
                  SELECT p.user_projection_run_id,
                         p.created_at,
                         {self._ui_v1_action_state_expr()} AS action_state,
                         q.queue_status,
                         r.status AS run_status
                  FROM user_signal_projection p
                  LEFT JOIN user_signal_card c
                    ON c.user_signal_projection_id = p.user_signal_projection_id
                   AND c.user_id = p.user_id
                  LEFT JOIN LATERAL (
                    SELECT q.queue_status,
                           q.action_state
                    FROM user_notification_queue q
                    WHERE q.user_signal_projection_id = p.user_signal_projection_id
                      AND q.user_id = p.user_id
                    ORDER BY
                      CASE WHEN q.queue_status = 'queued_only' THEN 0 ELSE 1 END,
                      q.created_at DESC,
                      q.user_notification_queue_id DESC
                    LIMIT 1
                  ) q ON true
                  LEFT JOIN user_projection_run r
                    ON r.user_projection_run_id = p.user_projection_run_id
                  WHERE p.user_id = %s
                )
                SELECT count(*)::int AS today_signal_count,
                       count(*) FILTER (WHERE action_state = 'blocked')::int AS action_blocked,
                       count(*) FILTER (WHERE action_state IN ('executed', 'action_confirmed'))::int AS action_executed,
                       count(*) FILTER (WHERE queue_status = 'queued_only')::int AS queued_only,
                       count(*) FILTER (WHERE queue_status = 'ready_for_future_push')::int AS pending_delivery,
                       COALESCE(bool_and(COALESCE(run_status, 'passed') IN ('passed', 'ready')), true) AS rollback_safe,
                       (array_agg(user_projection_run_id ORDER BY created_at DESC))[1] AS latest_run_id
                FROM scoped
                """,
                (user_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else {}

    def fetch_ui_v1_virtual_account(self, user_id: int) -> dict[str, Any] | None:
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT v.virtual_account_id,
                       v.principal_id,
                       v.principal_type,
                       v.account_name,
                       v.virtual_account_status,
                       v.base_currency,
                       v.initial_cash,
                       v.current_cash_snapshot_id,
                       v.run_id,
                       v.policy_version,
                       v.policy_hash,
                       v.rollback_scope,
                       v.quality_status,
                       v.created_at,
                       v.updated_at
                FROM n6_virtual_account v
                JOIN n6_principal p
                  ON p.principal_id = v.principal_id
                 AND p.principal_type = v.principal_type
                WHERE p.owner_user_id = %s
                  AND p.principal_status = 'active'
                  AND v.virtual_account_status = 'active'
                  AND v.principal_type IN ('admin', 'human_user')
                ORDER BY v.virtual_account_id ASC
                LIMIT 1
                """,
                (user_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def fetch_ui_v1_cash_snapshot(self, user_id: int) -> dict[str, Any] | None:
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                WITH active_account AS (
                  SELECT v.virtual_account_id,
                         v.current_cash_snapshot_id
                  FROM n6_virtual_account v
                  JOIN n6_principal p
                    ON p.principal_id = v.principal_id
                   AND p.principal_type = v.principal_type
                  WHERE p.owner_user_id = %s
                    AND p.principal_status = 'active'
                    AND v.virtual_account_status = 'active'
                    AND v.principal_type IN ('admin', 'human_user')
                  ORDER BY v.virtual_account_id ASC
                  LIMIT 1
                )
                SELECT s.cash_snapshot_id,
                       s.virtual_account_id,
                       s.snapshot_time,
                       s.trade_date,
                       s.available_cash,
                       s.frozen_cash,
                       s.total_cash,
                       s.currency,
                       s.source_ledger_max_id,
                       s.snapshot_status,
                       s.run_id,
                       s.policy_version,
                       s.policy_hash,
                       s.rollback_scope,
                       s.quality_status,
                       s.created_at,
                       (a.current_cash_snapshot_id IS NULL) AS pointer_missing_warning
                FROM active_account a
                JOIN n6_virtual_cash_snapshot s
                  ON s.virtual_account_id = a.virtual_account_id
                WHERE (
                    a.current_cash_snapshot_id IS NOT NULL
                    AND s.cash_snapshot_id = a.current_cash_snapshot_id
                  )
                   OR (
                    a.current_cash_snapshot_id IS NULL
                    AND s.snapshot_status = 'active'
                  )
                ORDER BY
                  CASE WHEN s.cash_snapshot_id = a.current_cash_snapshot_id THEN 0 ELSE 1 END,
                  s.snapshot_time DESC,
                  s.cash_snapshot_id DESC
                LIMIT 1
                """,
                (user_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def fetch_ui_v1_cash_ledger(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        clamped_limit = max(1, min(int(limit), 100))
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                WITH active_account AS (
                  SELECT v.virtual_account_id
                  FROM n6_virtual_account v
                  JOIN n6_principal p
                    ON p.principal_id = v.principal_id
                   AND p.principal_type = v.principal_type
                  WHERE p.owner_user_id = %s
                    AND p.principal_status = 'active'
                    AND v.virtual_account_status = 'active'
                    AND v.principal_type IN ('admin', 'human_user')
                  ORDER BY v.virtual_account_id ASC
                  LIMIT 1
                )
                SELECT l.cash_ledger_id,
                       l.virtual_account_id,
                       l.ledger_type,
                       l.amount,
                       l.currency,
                       l.trade_date,
                       l.event_time,
                       l.source_event_type,
                       l.source_event_id,
                       l.source_virtual_order_id,
                       l.source_virtual_trade_id,
                       l.run_id,
                       l.policy_version,
                       l.policy_hash,
                       l.rollback_scope,
                       l.quality_status,
                       l.created_at
                FROM n6_virtual_cash_ledger l
                JOIN active_account a
                  ON a.virtual_account_id = l.virtual_account_id
                ORDER BY l.event_time DESC, l.cash_ledger_id DESC
                LIMIT %s
                """,
                (user_id, clamped_limit),
            )
            return [dict(row) for row in cur.fetchall()]

    def fetch_ui_v1_artifacts(self) -> dict[str, Any]:
        paths = [
            "docs/N6_USER_INTERFACE_SPEC_v1.md",
            "docs/N6_USER_INTERFACE_SPEC_v1_TRACEABILITY.md",
            "docs/N6_USER_INTERFACE_SPEC_v1_POST_REVIEW.md",
            "docs/N6_USER_INTERFACE_SPEC_v1_DRY_RUN_PREVIEW.md",
            "docs/N6_USER_INTERFACE_SPEC_v1_DRY_RUN_PREVIEW.json",
        ]
        repo_root = Path(__file__).resolve().parents[3]
        return {
            "artifacts": paths,
            "stale_artifact": any(not (repo_root / path).exists() for path in paths),
        }

    def fetch_ui_v1_rollback_summary(self) -> dict[str, Any]:
        repo_root = Path(__file__).resolve().parents[3]
        rollback_path = "sql/N6_projection_business_rollback.sql"
        return {
            "rollback_sql_path": rollback_path,
            "rollback_safe": (repo_root / rollback_path).exists(),
            "delete_order": [
                "user_notification_queue",
                "user_signal_card",
                "user_signal_projection",
                "user_projection_run",
            ],
            "hard_fail_guards": ["decision", "sim", "voice", "mobile", "position"],
        }

    def fetch_app_principals(self, user_id: int) -> list[dict[str, Any]]:
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.principal_id,
                       p.principal_type,
                       p.owner_user_id,
                       p.principal_status,
                       COALESCE(p.principal_label, u.display_name, u.login_name) AS display_name
                FROM n6_principal p
                JOIN user_account u
                  ON u.user_id = p.owner_user_id
                WHERE p.owner_user_id = %s
                  AND p.principal_status = 'active'
                  AND p.principal_type IN ('admin', 'human_user')
                  AND u.status = 'active'
                ORDER BY
                  CASE WHEN p.principal_type = 'admin' THEN 0 ELSE 1 END,
                  p.principal_id ASC
                """,
                (user_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def fetch_app_virtual_account(self, principal_id: int, principal_type: str) -> dict[str, Any] | None:
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT virtual_account_id,
                       principal_id,
                       principal_type,
                       account_name,
                       virtual_account_status,
                       base_currency,
                       initial_cash,
                       current_cash_snapshot_id,
                       run_id,
                       policy_version,
                       policy_hash,
                       rollback_scope,
                       quality_status,
                       created_at,
                       updated_at
                FROM n6_virtual_account
                WHERE principal_id = %s
                  AND principal_type = %s
                  AND virtual_account_status = 'active'
                ORDER BY virtual_account_id ASC
                LIMIT 1
                """,
                (principal_id, principal_type),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def fetch_app_cash_snapshot(self, virtual_account_id: int) -> dict[str, Any] | None:
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                WITH account AS (
                  SELECT virtual_account_id,
                         current_cash_snapshot_id
                  FROM n6_virtual_account
                  WHERE virtual_account_id = %s
                )
                SELECT s.cash_snapshot_id,
                       s.virtual_account_id,
                       s.snapshot_time,
                       s.trade_date,
                       s.available_cash,
                       s.frozen_cash,
                       s.total_cash,
                       s.currency,
                       s.source_ledger_max_id,
                       s.snapshot_status,
                       s.run_id,
                       s.policy_version,
                       s.policy_hash,
                       s.rollback_scope,
                       s.quality_status,
                       s.created_at,
                       (a.current_cash_snapshot_id IS NULL) AS pointer_missing_warning
                FROM account a
                JOIN n6_virtual_cash_snapshot s
                  ON s.virtual_account_id = a.virtual_account_id
                WHERE (
                    a.current_cash_snapshot_id IS NOT NULL
                    AND s.cash_snapshot_id = a.current_cash_snapshot_id
                  )
                   OR (
                    a.current_cash_snapshot_id IS NULL
                    AND s.snapshot_status = 'active'
                  )
                ORDER BY
                  CASE WHEN s.cash_snapshot_id = a.current_cash_snapshot_id THEN 0 ELSE 1 END,
                  s.snapshot_time DESC,
                  s.cash_snapshot_id DESC
                LIMIT 1
                """,
                (virtual_account_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def fetch_app_signals(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        filters: dict[str, Any],
        limit: int,
    ) -> list[dict[str, Any]]:
        if not self._app_v1_signal_scope_relations_ready():
            return []
        where_sql, params = self._app_v1_signal_where(
            principal_id=principal_id,
            principal_type=principal_type,
            user_id=user_id,
            filters=filters,
        )
        params["limit"] = max(1, min(int(limit), 500))
        historical_projection_mode = bool(filters.get("historical_projection_mode"))
        scope_cte_sql = self._app_v1_effective_monitor_scope_cte(
            include_expired=historical_projection_mode,
            include_realtime_scope=not historical_projection_mode,
        )
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                WITH {scope_cte_sql}
                SELECT {self._app_v1_signal_select_list()}
                FROM user_signal_projection p
                JOIN user_projection_run r
                  ON r.user_projection_run_id = p.user_projection_run_id
                 AND r.status IN ('passed', 'ready')
                LEFT JOIN user_signal_card c
                  ON c.user_signal_projection_id = p.user_signal_projection_id
                 AND c.user_projection_run_id = p.user_projection_run_id
                 AND c.user_id = p.user_id
                {self._app_v1_signal_display_join()}
                WHERE {where_sql}
                ORDER BY p.created_at DESC, p.user_signal_projection_id DESC
                LIMIT %(limit)s
                """,
                params,
            )
            return [dict(row) for row in cur.fetchall()]

    def fetch_app_signal_detail(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        user_signal_projection_id: int,
    ) -> dict[str, Any] | None:
        if not self._app_v1_signal_scope_relations_ready():
            return None
        where_sql, params = self._app_v1_signal_where(
            principal_id=principal_id,
            principal_type=principal_type,
            user_id=user_id,
            filters={},
        )
        params["user_signal_projection_id"] = int(user_signal_projection_id)
        scope_cte_sql = self._app_v1_effective_monitor_scope_cte()
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                WITH {scope_cte_sql}
                SELECT {self._app_v1_signal_select_list()}
                FROM user_signal_projection p
                JOIN user_projection_run r
                  ON r.user_projection_run_id = p.user_projection_run_id
                 AND r.status IN ('passed', 'ready')
                LEFT JOIN user_signal_card c
                  ON c.user_signal_projection_id = p.user_signal_projection_id
                 AND c.user_projection_run_id = p.user_projection_run_id
                 AND c.user_id = p.user_id
                {self._app_v1_signal_display_join()}
                WHERE {where_sql}
                  AND p.user_signal_projection_id = %(user_signal_projection_id)s
                LIMIT 1
                """,
                params,
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def fetch_app_signal_scope_metadata(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
    ) -> dict[str, Any]:
        metadata = {
            "scope_mode": "effective_monitor",
            "current_filter_batch": self._app_v2_current_filter_batches(["stock", "index", "board"]),
            "available_trade_dates": [],
            "effective_monitor_count": 0,
            "expired_monitor_count": 0,
            "matched_signal_count": 0,
            "excluded_reason_counts": {
                "message_trade_date_missing": 0,
                "message_trade_date_mismatch": 0,
                "monitor_expired": 0,
            },
        }
        if not self._app_v1_signal_scope_relations_ready():
            return metadata
        where_sql, params = self._app_v1_signal_where(
            principal_id=principal_id,
            principal_type=principal_type,
            user_id=user_id,
            filters={},
            include_monitor_scope=False,
        )
        scope_cte_sql = self._app_v1_effective_monitor_scope_cte()
        all_monitor_cte_sql = self._app_v1_all_monitor_scope_cte()
        trade_date_expr = self._app_v1_trade_date_expr()
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                WITH {scope_cte_sql},
                {all_monitor_cte_sql},
                candidate_messages AS (
                  SELECT p.asset_kind,
                         p.identity_key,
                         p.direction,
                         {trade_date_expr} AS message_trade_date
                  FROM user_signal_projection p
                  JOIN user_projection_run r
                    ON r.user_projection_run_id = p.user_projection_run_id
                   AND r.status IN ('passed', 'ready')
                  LEFT JOIN user_signal_card c
                    ON c.user_signal_projection_id = p.user_signal_projection_id
                   AND c.user_projection_run_id = p.user_projection_run_id
                   AND c.user_id = p.user_id
                  WHERE {where_sql}
                )
                SELECT
                  (SELECT COUNT(*) FROM effective_monitor_scope) AS effective_monitor_count,
                  (
                    SELECT COUNT(*)
                    FROM all_monitor_scope expired_monitor_scope
                    WHERE expired_monitor_scope.status = 'active'
                      AND NOT EXISTS (
                        SELECT 1
                        FROM effective_monitor_scope
                        WHERE effective_monitor_scope.asset_kind = expired_monitor_scope.asset_kind
                          AND effective_monitor_scope.monitor_id = expired_monitor_scope.monitor_id
                      )
                  ) AS expired_monitor_count,
                  COUNT(*) FILTER (WHERE candidate_messages.message_trade_date IS NULL) AS message_trade_date_missing,
                  COUNT(*) FILTER (
                    WHERE candidate_messages.message_trade_date IS NOT NULL
                      AND candidate_messages.message_trade_date <> effective_monitor_scope.valid_for_trade_date
                  ) AS message_trade_date_mismatch
                FROM candidate_messages
                JOIN effective_monitor_scope
                  ON effective_monitor_scope.asset_kind = candidate_messages.asset_kind
                 AND effective_monitor_scope.identity_key = candidate_messages.identity_key
                """,
                params,
            )
            row = cur.fetchone()
            cur.execute(
                f"""
                SELECT DISTINCT {trade_date_expr} AS trade_date
                FROM user_signal_projection p
                JOIN user_projection_run r
                  ON r.user_projection_run_id = p.user_projection_run_id
                 AND r.status IN ('passed', 'ready')
                LEFT JOIN user_signal_card c
                  ON c.user_signal_projection_id = p.user_signal_projection_id
                 AND c.user_projection_run_id = p.user_projection_run_id
                 AND c.user_id = p.user_id
                WHERE (
                    p.source_action_run_id IS NULL
                    OR NOT (p.source_action_run_id = ANY(%(stale_source_action_run_ids)s))
                  )
                  AND p.projection_status IN ('visible', 'blocked')
                  AND {trade_date_expr} IS NOT NULL
                ORDER BY trade_date DESC
                """,
                {"stale_source_action_run_ids": list(stale_source_action_run_ids())},
            )
            metadata["available_trade_dates"] = [str(item["trade_date"]) for item in cur.fetchall() if item.get("trade_date")]
        if row:
            metadata["effective_monitor_count"] = int(row.get("effective_monitor_count") or 0)
            metadata["expired_monitor_count"] = int(row.get("expired_monitor_count") or 0)
            metadata["excluded_reason_counts"]["monitor_expired"] = int(row.get("expired_monitor_count") or 0)
            metadata["excluded_reason_counts"]["message_trade_date_missing"] = int(
                row.get("message_trade_date_missing") or 0
            )
            metadata["excluded_reason_counts"]["message_trade_date_mismatch"] = int(
                row.get("message_trade_date_mismatch") or 0
            )
        return metadata

    def fetch_app_realtime_scope(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
    ) -> dict[str, Any]:
        if not self._app_v2_relation_exists(APP_REALTIME_SCOPE_TABLE):
            return {
                "tables_ready": False,
                "items": self._app_v2_default_realtime_scope_items(
                    principal_id=principal_id,
                    principal_type=principal_type,
                    user_id=user_id,
                ),
            }
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT realtime_scope_id,
                       principal_id,
                       principal_type,
                       user_id,
                       asset_kind,
                       identity_key,
                       display_name,
                       source_type,
                       source_snapshot_json,
                       is_default_seed,
                       status,
                       deleted_at,
                       created_at,
                       updated_at
                FROM {APP_REALTIME_SCOPE_TABLE}
                WHERE principal_id = %(principal_id)s
                  AND principal_type = %(principal_type)s
                  AND user_id = %(user_id)s
                ORDER BY
                  CASE WHEN status = 'active' THEN 0 ELSE 1 END,
                  asset_kind ASC,
                  identity_key ASC
                """,
                {
                    "principal_id": principal_id,
                    "principal_type": principal_type,
                    "user_id": user_id,
                },
            )
            rows = [dict(row) for row in cur.fetchall()]
        return {
            "tables_ready": True,
            "items": self._app_v2_merge_realtime_scope_defaults(
                rows,
                principal_id=principal_id,
                principal_type=principal_type,
                user_id=user_id,
            ),
        }

    def _app_v1_stock_signal_display_join(self) -> str:
        return self._app_v1_signal_display_join()

    def _app_v1_signal_display_join(self) -> str:
        trade_date_expr = self._app_v1_trade_date_expr()
        stock_basis_join = (
            f"""
                LEFT JOIN v_n6_stock_condition_display_basis s
                  ON p.asset_kind = 'stock'
                 AND s.identity_key = p.identity_key
                 AND s.for_trade_date::text = ({trade_date_expr})::text
                """
            if self._app_v2_relation_exists("v_n6_stock_condition_display_basis")
            else """
                LEFT JOIN (
                  SELECT NULL::text AS display_code,
                         NULL::text AS display_name,
                         NULL::text AS industry_code,
                         NULL::text AS industry_name
                ) s ON FALSE
                """
        )
        membership_join = (
            f"""
                LEFT JOIN LATERAL (
                  SELECT bm.stock_code,
                         bm.stock_name,
                         bm.parent_code,
                         bm.parent_name
                  FROM n6_board_membership_display_cache bm
                  WHERE p.asset_kind = 'stock'
                    AND bm.stock_identity_key = p.identity_key
                    AND bm.board_type = 'tdx_industry'
                    AND bm.quality_status = 'passed'
                    AND bm.source_trade_date <= ({trade_date_expr})::text
                  ORDER BY bm.source_trade_date DESC, bm.parent_code ASC
                  LIMIT 1
                ) bm ON TRUE
                """
            if self._app_v2_relation_exists("n6_board_membership_display_cache")
            else """
                LEFT JOIN (
                  SELECT NULL::text AS stock_code,
                         NULL::text AS stock_name,
                         NULL::text AS parent_code,
                         NULL::text AS parent_name
                ) bm ON FALSE
                """
        )
        index_basis_join = (
            f"""
                LEFT JOIN v_n6_index_condition_display_basis i
                  ON p.asset_kind = 'index'
                 AND i.identity_key = p.identity_key
                 AND i.for_trade_date::text = ({trade_date_expr})::text
                """
            if self._app_v2_relation_exists("v_n6_index_condition_display_basis")
            else """
                LEFT JOIN (
                  SELECT NULL::text AS display_code,
                         NULL::text AS display_name
                ) i ON FALSE
                """
        )
        board_basis_join = (
            f"""
                LEFT JOIN v_n6_board_condition_display_basis b
                  ON p.asset_kind = 'board'
                 AND b.identity_key = p.identity_key
                 AND b.for_trade_date::text = ({trade_date_expr})::text
                """
            if self._app_v2_relation_exists("v_n6_board_condition_display_basis")
            else """
                LEFT JOIN (
                  SELECT NULL::text AS display_code,
                         NULL::text AS display_name
                ) b ON FALSE
                """
        )
        return f"{stock_basis_join}\n{membership_join}\n{index_basis_join}\n{board_basis_join}"

    def _app_v1_signal_select_list(self) -> str:
        actual_trigger_period_expr = self._app_v1_actual_trigger_period_expr()
        stock_filter_columns = (
            self._app_v2_filter_columns("v_n6_stock_condition_display_basis")
            if self._app_v2_relation_exists("v_n6_stock_condition_display_basis")
            else set()
        )
        stock_basis_industry_code_expr = (
            "NULLIF(s.industry_code::text, '')" if "industry_code" in stock_filter_columns else "NULL::text"
        )
        stock_basis_industry_name_expr = (
            "NULLIF(s.industry_name::text, '')" if "industry_name" in stock_filter_columns else "NULL::text"
        )
        return f"""
               p.user_signal_projection_id,
               c.user_signal_card_id,
               NULL::bigint AS user_notification_queue_id,
               p.user_projection_run_id,
               p.user_projection_run_id AS projection_run_id,
               {self._app_v1_event_type_expr()} AS event_type,
               {self._app_v1_trade_date_expr()} AS trade_date,
               {self._app_v1_event_time_expr()} AS event_time,
               p.asset_kind,
               p.identity_key,
               p.code,
               COALESCE(
                 NULLIF(bm.stock_code::text, ''),
                 CASE WHEN s.display_code::text LIKE 'stock:%%' THEN NULL ELSE NULLIF(s.display_code::text, '') END,
                 NULLIF(i.display_code::text, ''),
                 NULLIF(b.display_code::text, ''),
                 CASE
                   WHEN p.code::text LIKE 'stock:%%' OR p.code::text LIKE 'index:%%' OR p.code::text LIKE 'board:%%' THEN NULL
                   ELSE NULLIF(p.code::text, '')
                 END,
                 p.code
               ) AS display_code,
               p.name,
               COALESCE(
                 NULLIF(bm.stock_name::text, ''),
                 CASE WHEN s.display_name::text LIKE 'stock:%%' THEN NULL ELSE NULLIF(s.display_name::text, '') END,
                 NULLIF(i.display_name::text, ''),
                 NULLIF(b.display_name::text, ''),
                 CASE
                   WHEN p.name::text LIKE 'stock:%%' OR p.name::text LIKE 'index:%%' OR p.name::text LIKE 'board:%%' THEN NULL
                   ELSE NULLIF(p.name::text, '')
                 END,
                 p.name
               ) AS display_name,
               COALESCE(
                 {stock_basis_industry_code_expr},
                 NULLIF(bm.parent_code::text, ''),
                 NULLIF(p.display_payload_json->>'industry_code', ''),
                 NULLIF(p.trace_json->>'industry_code', '')
               ) AS industry_code,
               COALESCE(
                 {stock_basis_industry_name_expr},
                 NULLIF(bm.parent_name::text, ''),
                 NULLIF(p.display_payload_json->>'industry_name', ''),
                 NULLIF(p.trace_json->>'industry_name', '')
               ) AS industry_name,
               p.direction,
               p.signal_type,
               {self._app_v1_action_state_expr()} AS action_state,
               COALESCE(NULLIF(p.action_mark, ''), NULLIF(c.action_mark, ''), '—') AS action_mark,
               c.card_status,
               {self._app_v1_blocked_reason_expr()} AS blocked_reason,
               COALESCE(p.source_payload_json->'payload_json'->>'trigger_kind', c.card_payload_json->>'trigger_kind', p.display_payload_json->>'trigger_kind', p.trace_json->>'trigger_kind', p.source_payload_json->>'trigger_kind') AS trigger_kind,
               COALESCE(NULLIF(p.condition_key, ''), NULLIF(c.condition_key, ''), p.display_payload_json->>'condition_key', p.trace_json->>'condition_key') AS condition_key,
               COALESCE(NULLIF(p.original_condition_key, ''), NULLIF(c.original_condition_key, ''), p.display_payload_json->>'original_condition_key', p.trace_json->>'original_condition_key') AS original_condition_key,
               {actual_trigger_period_expr} AS primary_trigger_period,
               COALESCE(p.trace_json->>'trigger_time', p.source_payload_json->>'event_time', p.created_at::text) AS trigger_time,
               'readonly'::text AS queue_status,
               'not_delivered'::text AS delivery_status,
               'b_track_reviewed_projection'::text AS notification_source,
               NULL::text AS channel,
               c.title,
               c.summary AS message,
               NULL::jsonb AS notification_payload_json,
               p.source_action_run_id,
               p.source_action_run_id AS source_run_id,
               p.source_event_id,
               COALESCE(NULLIF(p.source_action_event_id, ''), NULLIF(c.source_action_event_id, ''), p.source_event_id) AS source_action_event_id,
               {self._app_v1_event_type_expr()} AS source_action_event_type,
               COALESCE(c.card_payload_json->>'source_n4_run_id', p.trace_json->>'source_n4_run_id', p.source_payload_json->>'source_n4_run_id', p.trace_json->>'source_trigger_run_id') AS source_n4_run_id,
               COALESCE(p.source_payload_json->'payload_json'->>'source_trigger_event_id', p.trace_json#>>'{{condition_provenance,source_trigger_event_ids,0}}') AS n4_trigger_event_id,
               COALESCE(p.source_payload_json->'payload_json'->>'confirmation_status', p.trace_json->>'confirmation_status', p.action_state, c.action_state) AS source_action_status,
               {self._app_v1_trigger_price_expr()} AS trigger_price,
               {self._app_v1_triggered_periods_expr(actual_trigger_period_expr)} AS triggered_periods,
               {self._app_v1_baseline_source_expr(actual_trigger_period_expr)} AS baseline_source,
               COALESCE(c.target_price, p.target_price) AS target_price,
               COALESCE(c.current_price, p.current_price) AS current_price,
               COALESCE(c.expected_return_pct, p.expected_return_pct) AS expected_return_pct,
               COALESCE(c.board_code, p.board_code) AS board_code,
               COALESCE(c.board_name, p.board_name) AS board_name,
               p.source_display_table,
               p.source_condition_display_basis_id,
               p.source_condition_display_run_id,
               {self._app_v1_effective_monitor_scope_lookup("source_type_raw")} AS source_type_raw,
               {self._app_v1_effective_monitor_scope_lookup("source_type")} AS source_type,
               {self._app_v1_effective_monitor_scope_lookup("source_type_label")} AS source_type_label,
               {self._app_v1_effective_monitor_scope_lookup("source_object_kind")} AS source_object_kind,
               {self._app_v1_effective_monitor_scope_lookup("source_object_identity_key")} AS source_object_identity_key,
               {self._app_v1_effective_monitor_scope_lookup("source_object_code")} AS source_object_code,
               {self._app_v1_effective_monitor_scope_lookup("source_object_name")} AS source_object_name,
               {self._app_v1_effective_monitor_scope_lookup("membership_relation_date")} AS membership_relation_date,
               CASE p.source_display_table
                 WHEN 'stock_condition_display_basis' THEN 'n6_display_stock_condition_cache'
                 WHEN 'index_condition_display_basis' THEN 'n6_display_index_condition_cache'
                 WHEN 'board_condition_display_basis' THEN 'n6_display_board_condition_cache'
                 WHEN NULL THEN NULL
                 ELSE NULL
               END AS condition_display_cache_source,
               CASE
                 WHEN p.asset_kind = 'index' THEN 'n6_display_index_membership_cache'
                 WHEN p.asset_kind IN ('stock', 'board') THEN 'n6_display_board_membership_cache'
                 ELSE NULL
               END AS membership_cache_source,
               COALESCE(c.card_payload_json->>'quality_status', p.display_payload_json->>'quality_status', 'reviewed') AS quality_status,
               c.card_payload_json,
               p.display_payload_json,
               true AS rollback_safe,
               p.created_at
        """

    def _app_v1_signal_where(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        filters: dict[str, Any],
        include_monitor_scope: bool = True,
    ) -> tuple[str, dict[str, Any]]:
        params: dict[str, Any] = {
            "principal_id": int(principal_id),
            "principal_type": str(principal_type),
            "user_id": int(user_id),
            "trade_date": normalize_filter_value(filters.get("trade_date")) or "",
            "stale_source_action_run_ids": list(stale_source_action_run_ids()),
        }
        where_clauses = [
            """
            (
              p.source_action_run_id IS NULL
              OR NOT (p.source_action_run_id = ANY(%(stale_source_action_run_ids)s))
            )
            """,
            """
            p.projection_status IN ('visible', 'blocked')
            """,
        ]
        if include_monitor_scope:
            where_clauses.append(self._app_v1_effective_monitor_scope_clause())
        filter_specs = (
            ("trade_date", self._app_v1_trade_date_expr()),
            ("event_type", self._app_v1_event_type_expr()),
            ("asset_kind", "p.asset_kind"),
            ("direction", "p.direction"),
            ("signal_type", "p.signal_type"),
            ("action_state", self._app_v1_action_state_expr()),
            ("blocked_reason", self._app_v1_blocked_reason_expr()),
        )
        for key, expression in filter_specs:
            value = normalize_filter_value(filters.get(key))
            if value:
                params[key] = value
                where_clauses.append(f"{expression} = %({key})s")

        time_field = normalize_time_field(filters.get("time_field"))
        time_expression = "p.created_at" if time_field == "created_at" else f"({self._app_v1_event_time_expr()})::timestamptz"
        date_from = normalize_filter_value(filters.get("date_from"))
        if date_from:
            params["date_from"] = date_from
            where_clauses.append(f"(({time_expression}) AT TIME ZONE 'Asia/Shanghai')::date >= %(date_from)s::date")
        date_to = normalize_filter_value(filters.get("date_to"))
        if date_to:
            params["date_to"] = date_to
            where_clauses.append(f"(({time_expression}) AT TIME ZONE 'Asia/Shanghai')::date <= %(date_to)s::date")

        keyword = normalize_filter_value(filters.get("q"))
        if keyword:
            params["q_like"] = f"%{keyword}%"
            condition_expr = "COALESCE(NULLIF(p.condition_key, ''), NULLIF(c.condition_key, ''), p.display_payload_json->>'condition_key', p.trace_json->>'condition_key')"
            where_clauses.append(
                f"""
                (
                  p.code ILIKE %(q_like)s
                  OR p.name ILIKE %(q_like)s
                  OR p.identity_key ILIKE %(q_like)s
                  OR p.source_event_id ILIKE %(q_like)s
                  OR p.source_action_event_id ILIKE %(q_like)s
                  OR {condition_expr} ILIKE %(q_like)s
                )
                """
            )
        return "\n                  AND ".join(where_clauses), params

    def _app_v1_signal_scope_relations_ready(self) -> bool:
        required_monitor_tables = (
            "user_monitor_stock",
            "user_monitor_index",
            "user_monitor_board",
        )
        required_display_views = (
            "v_n6_stock_condition_display_basis",
            "v_n6_index_condition_display_basis",
            "v_n6_board_condition_display_basis",
        )
        return all(self._app_v2_monitor_relation_exists(table_name) for table_name in required_monitor_tables) and all(
            self._app_v2_relation_exists(view_name) for view_name in required_display_views
        )

    def _app_v1_effective_monitor_scope_clause(self) -> str:
        message_trade_date_expr = self._app_v1_trade_date_expr()
        return f"""
            EXISTS (
              SELECT 1
              FROM effective_monitor_scope
              WHERE effective_monitor_scope.asset_kind = p.asset_kind
                AND effective_monitor_scope.identity_key = p.identity_key
                AND effective_monitor_scope.valid_for_trade_date = ({message_trade_date_expr})
            )
        """

    def _app_v1_effective_monitor_scope_lookup(self, column_name: str) -> str:
        message_trade_date_expr = self._app_v1_trade_date_expr()
        return f"""
            (
              SELECT effective_monitor_scope.{column_name}
              FROM effective_monitor_scope
              WHERE effective_monitor_scope.asset_kind = p.asset_kind
                AND effective_monitor_scope.identity_key = p.identity_key
                AND effective_monitor_scope.valid_for_trade_date = ({message_trade_date_expr})
              ORDER BY effective_monitor_scope.monitor_id DESC
              LIMIT 1
            )
        """

    def _app_v1_effective_monitor_scope_cte(
        self,
        *,
        include_expired: bool = False,
        include_realtime_scope: bool = True,
    ) -> str:
        realtime_scope_union = ""
        if include_realtime_scope and not include_expired and self._app_v2_relation_exists(APP_REALTIME_SCOPE_TABLE):
            realtime_scope_union = f"""
          UNION ALL
          {self._app_v1_realtime_scope_select()}
            """
        return f"""
        effective_monitor_scope AS (
          {self._app_v1_effective_monitor_scope_select(
              asset_kind="stock",
              table_name="user_monitor_stock",
              view_name="v_n6_stock_condition_display_basis",
              include_expired=include_expired,
          )}
          UNION ALL
          {self._app_v1_effective_monitor_scope_select(
              asset_kind="index",
              table_name="user_monitor_index",
              view_name="v_n6_index_condition_display_basis",
              include_expired=include_expired,
          )}
          UNION ALL
          {self._app_v1_effective_monitor_scope_select(
              asset_kind="board",
              table_name="user_monitor_board",
              view_name="v_n6_board_condition_display_basis",
              include_expired=include_expired,
          )}
          {realtime_scope_union}
        )
        """

    def _app_v1_all_monitor_scope_cte(self) -> str:
        return f"""
        all_monitor_scope AS (
          {self._app_v1_all_monitor_scope_select(
              asset_kind="stock",
              table_name="user_monitor_stock",
          )}
          UNION ALL
          {self._app_v1_all_monitor_scope_select(
              asset_kind="index",
              table_name="user_monitor_index",
          )}
          UNION ALL
          {self._app_v1_all_monitor_scope_select(
              asset_kind="board",
              table_name="user_monitor_board",
          )}
        )
        """

    def _app_v1_monitor_validity_sql_exprs(self, table_name: str, alias: str = "m") -> tuple[str, str, str]:
        columns = self._app_v2_monitor_columns(table_name)
        snapshot_expr = f"{alias}.source_snapshot_json"
        source_run_expr = f"{alias}.source_run_id"
        valid_source_trade_expr = (
            f"COALESCE({alias}.valid_source_trade_date, {snapshot_expr}->>'source_trade_date')"
            if "valid_source_trade_date" in columns
            else f"{snapshot_expr}->>'source_trade_date'"
        )
        valid_for_trade_expr = (
            f"COALESCE({alias}.valid_for_trade_date, {snapshot_expr}->>'for_trade_date')"
            if "valid_for_trade_date" in columns
            else f"{snapshot_expr}->>'for_trade_date'"
        )
        valid_run_expr = (
            f"COALESCE({alias}.valid_source_run_id, {snapshot_expr}->>'source_run_id', {source_run_expr})"
            if "valid_source_run_id" in columns
            else f"COALESCE({snapshot_expr}->>'source_run_id', {source_run_expr})"
        )
        return valid_source_trade_expr, valid_for_trade_expr, valid_run_expr

    def _app_v1_effective_monitor_scope_select(
        self,
        *,
        asset_kind: str,
        table_name: str,
        view_name: str,
        include_expired: bool = False,
    ) -> str:
        valid_source_trade_expr, valid_for_trade_expr, valid_run_expr = self._app_v1_monitor_validity_sql_exprs(table_name)
        user_id_clause = "AND m.user_id = %(user_id)s" if "user_id" in self._app_v2_monitor_columns(table_name) else ""
        status_clause = "m.status <> 'removed'" if include_expired else "m.status = 'active'"
        source_type_raw_expr = "COALESCE(NULLIF(m.source_type, ''), 'single_row')"
        source_type_expr = f"""
            CASE {source_type_raw_expr}
              WHEN 'single_row' THEN 'direct'
              WHEN 'direct' THEN 'direct'
              WHEN 'index_linked_stock' THEN 'index_linked_stock'
              WHEN 'board_linked_stock' THEN 'board_linked_stock'
              ELSE {source_type_raw_expr}
            END
        """
        return f"""
          SELECT m.monitor_id,
                 m.principal_id,
                 m.principal_type,
                 '{asset_kind}'::text AS asset_kind,
                 m.identity_key,
                 m.direction,
                 {valid_source_trade_expr} AS valid_source_trade_date,
                 {valid_for_trade_expr} AS valid_for_trade_date,
                 {valid_run_expr} AS valid_source_run_id,
                 {source_type_raw_expr} AS source_type_raw,
                 {source_type_expr} AS source_type,
                 CASE {source_type_expr}
                   WHEN 'direct' THEN '直接加入'
                   WHEN 'index_linked_stock' THEN '来源指数'
                   WHEN 'board_linked_stock' THEN '来源板块'
                   ELSE {source_type_expr}
                 END AS source_type_label,
                 CASE
                   WHEN {source_type_expr} = 'direct' THEN 'none'
                   ELSE COALESCE(
                     NULLIF(m.source_snapshot_json->>'parent_asset_kind', ''),
                     CASE {source_type_expr}
                       WHEN 'index_linked_stock' THEN 'index'
                       WHEN 'board_linked_stock' THEN 'board'
                       ELSE 'none'
                     END
                   )
                 END AS source_object_kind,
                 CASE WHEN {source_type_expr} = 'direct' THEN NULL ELSE NULLIF(m.source_snapshot_json->>'parent_identity_key', '') END AS source_object_identity_key,
                 CASE WHEN {source_type_expr} = 'direct' THEN NULL ELSE NULLIF(m.source_snapshot_json->>'parent_code', '') END AS source_object_code,
                 CASE WHEN {source_type_expr} = 'direct' THEN NULL ELSE NULLIF(m.source_snapshot_json->>'parent_name', '') END AS source_object_name,
                 CASE WHEN {source_type_expr} = 'direct' THEN NULL ELSE NULLIF(m.source_snapshot_json->>'membership_trade_date', '') END AS membership_relation_date
          FROM {table_name} m
          WHERE m.principal_id = %(principal_id)s
            AND m.principal_type = %(principal_type)s
            {user_id_clause}
            AND {status_clause}
            AND NULLIF({valid_for_trade_expr}, '') IS NOT NULL
        """

    def _app_v1_realtime_scope_select(self) -> str:
        return f"""
          SELECT s.realtime_scope_id AS monitor_id,
                 s.principal_id,
                 s.principal_type,
                 s.asset_kind,
                 s.identity_key,
                 NULL::text AS direction,
                 NULL::text AS valid_source_trade_date,
                 %(trade_date)s::text AS valid_for_trade_date,
                 NULL::text AS valid_source_run_id,
                 COALESCE(NULLIF(s.source_type, ''), 'realtime_scope') AS source_type_raw,
                 'realtime_scope'::text AS source_type,
                 '实时监控范围'::text AS source_type_label,
                 'none'::text AS source_object_kind,
                 NULL::text AS source_object_identity_key,
                 NULL::text AS source_object_code,
                 NULL::text AS source_object_name,
                 NULL::text AS membership_relation_date
          FROM {APP_REALTIME_SCOPE_TABLE} s
          WHERE s.principal_id = %(principal_id)s
            AND s.principal_type = %(principal_type)s
            AND s.user_id = %(user_id)s
            AND s.status = 'active'
            AND NULLIF(%(trade_date)s, '') IS NOT NULL
        """

    def _app_v1_all_monitor_scope_select(self, *, asset_kind: str, table_name: str) -> str:
        valid_source_trade_expr, valid_for_trade_expr, valid_run_expr = self._app_v1_monitor_validity_sql_exprs(table_name)
        user_id_clause = "AND m.user_id = %(user_id)s" if "user_id" in self._app_v2_monitor_columns(table_name) else ""
        return f"""
          SELECT m.monitor_id,
                 m.principal_id,
                 m.principal_type,
                 '{asset_kind}'::text AS asset_kind,
                 m.identity_key,
                 m.direction,
                 m.status,
                 {valid_source_trade_expr} AS valid_source_trade_date,
                 {valid_for_trade_expr} AS valid_for_trade_date,
                 {valid_run_expr} AS valid_source_run_id
          FROM {table_name} m
          WHERE m.principal_id = %(principal_id)s
            AND m.principal_type = %(principal_type)s
            {user_id_clause}
            AND m.status <> 'removed'
        """

    def _app_v1_trade_date_expr(self) -> str:
        return "COALESCE(p.display_payload_json->>'trade_date', p.source_payload_json->>'trade_date', c.card_payload_json->>'trade_date', p.trace_json->>'trade_date')"

    def _app_v1_event_type_expr(self) -> str:
        return "COALESCE(NULLIF(p.source_action_event_type, ''), NULLIF(c.source_action_event_type, ''), p.source_event_type)"

    def _app_v1_event_time_expr(self) -> str:
        return "COALESCE(p.source_payload_json->>'event_time', p.source_payload_json->'payload_json'->>'event_time', p.trace_json->>'event_time', p.display_payload_json->>'event_time', c.card_payload_json->>'event_time', p.created_at::text)"

    def _app_v1_action_state_expr(self) -> str:
        return """
            COALESCE(
              NULLIF(p.action_state, ''),
              NULLIF(c.action_state, ''),
              CASE
                WHEN p.source_action_event_type = 'ActionBlocked' THEN 'blocked'
                WHEN p.source_action_event_type = 'ActionExecuted' THEN 'executed'
                WHEN p.source_action_event_type = 'ActionEligible' THEN 'eligible'
                WHEN p.source_action_event_type = 'ActionSkipped' THEN 'skipped'
                ELSE NULL
              END,
              p.projection_status,
              c.card_status
            )
        """

    def _app_v1_blocked_reason_expr(self) -> str:
        return "COALESCE(c.card_payload_json->>'blocked_reason', p.display_payload_json->>'blocked_reason', p.source_payload_json->'payload_json'->>'blocked_reason', p.trace_json->>'blocked_reason', p.source_payload_json->>'blocked_reason')"

    def _app_v1_actual_trigger_period_expr(self) -> str:
        return """
            COALESCE(
              p.source_payload_json->'payload_json'->>'primary_trigger_period',
              p.source_payload_json->'payload_json'->>'trigger_period',
              c.card_payload_json->>'primary_trigger_period',
              c.card_payload_json->>'trigger_period',
              p.display_payload_json->>'primary_trigger_period'
            )
        """

    def _app_v1_trigger_price_expr(self) -> str:
        return """
            COALESCE(
              p.source_payload_json->'payload_json'->>'trigger_price',
              p.source_payload_json->'payload_json'->'trace_json'->>'trigger_price',
              p.trace_json->>'trigger_price',
              c.card_payload_json->>'trigger_price'
            )
        """

    def _app_v1_triggered_periods_expr(self, actual_trigger_period_expr: str) -> str:
        return f"""
            COALESCE(
              p.source_payload_json->'payload_json'->>'all_trigger_periods',
              p.source_payload_json->'payload_json'->'trace_json'->>'all_trigger_periods',
              p.trace_json->>'all_trigger_periods',
              c.card_payload_json->>'all_trigger_periods',
              p.source_payload_json->'payload_json'->>'triggered_periods',
              p.source_payload_json->'payload_json'->'trace_json'->>'triggered_periods',
              p.trace_json->>'triggered_periods',
              c.card_payload_json->>'triggered_periods',
              CASE
                WHEN {actual_trigger_period_expr} IS NOT NULL
                THEN jsonb_build_array({actual_trigger_period_expr})::text
                ELSE NULL
              END
            )
        """

    def _app_v1_baseline_source_expr(self, actual_trigger_period_expr: str) -> str:
        period_baseline_cases = "\n".join(
            f"""
              WHEN '{period}' THEN COALESCE(
                p.source_payload_json#>>'{{payload_json,period_trigger_baseline_trace,traced_periods,{period},baseline_source}}',
                p.source_payload_json#>>'{{payload_json,trace_json,period_trigger_baseline_trace,traced_periods,{period},baseline_source}}',
                p.source_payload_json#>>'{{payload_json,source_market_trace,period_trigger_baseline_trace,traced_periods,{period},baseline_source}}',
                p.trace_json#>>'{{period_trigger_baseline_trace,traced_periods,{period},baseline_source}}',
                c.card_payload_json#>>'{{period_trigger_baseline_trace,traced_periods,{period},baseline_source}}'
              )
            """
            for period in ("Y", "Q", "M", "W", "D", "30m", "120m", "5m", "1m")
        )
        return f"""
            COALESCE(
              p.source_payload_json->'payload_json'->>'baseline_source',
              p.source_payload_json->'payload_json'->'trace_json'->>'baseline_source',
              p.trace_json->>'baseline_source',
              c.card_payload_json->>'baseline_source',
              CASE {actual_trigger_period_expr}
                {period_baseline_cases}
                ELSE NULL
              END
            )
        """

    def fetch_app_positions(self, principal_id: int, principal_type: str) -> list[dict[str, Any]]:
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT virtual_position_id,
                       virtual_account_id,
                       principal_id,
                       principal_type,
                       asset_kind,
                       identity_key,
                       position_status,
                       quantity,
                       available_quantity,
                       locked_quantity,
                       average_cost,
                       market_value,
                       unrealized_pnl,
                       last_virtual_trade_id,
                       source_position_event_id,
                       run_id,
                       policy_version,
                       policy_hash,
                       rollback_scope,
                       quality_status,
                       created_at,
                       updated_at
                FROM n6_virtual_position
                WHERE principal_id = %s
                  AND principal_type = %s
                ORDER BY updated_at DESC, virtual_position_id DESC
                LIMIT 200
                """,
                (principal_id, principal_type),
            )
            return [dict(row) for row in cur.fetchall()]

    def fetch_app_pnl_snapshots(self, principal_id: int, principal_type: str, limit: int) -> list[dict[str, Any]]:
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT pnl_snapshot_id,
                       virtual_account_id,
                       principal_id,
                       principal_type,
                       snapshot_time,
                       trade_date,
                       gross_pnl,
                       realized_pnl,
                       unrealized_pnl,
                       total_fee,
                       total_tax,
                       net_pnl,
                       total_asset_value,
                       cash_value,
                       position_market_value,
                       source_price_policy,
                       pnl_status,
                       run_id,
                       policy_version,
                       policy_hash,
                       rollback_scope,
                       quality_status,
                       created_at
                FROM n6_virtual_pnl_snapshot
                WHERE principal_id = %s
                  AND principal_type = %s
                ORDER BY snapshot_time DESC, pnl_snapshot_id DESC
                LIMIT %s
                """,
                (principal_id, principal_type, max(1, min(int(limit), 100))),
            )
            return [dict(row) for row in cur.fetchall()]

    def _app_v2_filter_source_identity_keys(self, filters: dict[str, Any]) -> list[str]:
        return normalize_filter_identity_values(
            [
                *normalize_filter_values(filters.get("source_identity_keys")),
                *normalize_filter_values(filters.get("source_identity_key")),
            ]
        )

    def _app_v2_stock_source_context(
        self,
        cur: Any,
        *,
        filters: dict[str, Any],
        selected_for_trade_date: str,
    ) -> dict[str, Any] | None:
        source_asset_type = normalize_filter_value(filters.get("source_asset_type"))
        source_identity_keys = self._app_v2_filter_source_identity_keys(filters)
        if not source_asset_type and not source_identity_keys:
            return {
                "source_asset_type": None,
                "source_identity_keys": [],
                "source_display_names": [],
                "membership_source_table": None,
                "membership_trade_date": None,
                "membership_count": 0,
                "matched_stock_count": 0,
                "for_trade_date": selected_for_trade_date,
                "empty_state": "",
                "fallback_used": False,
                "source_filter_active": False,
            }
        membership_table_by_type = {
            "index": "v_n6_index_membership_fact",
            "board": "v_n6_board_membership_fact",
        }
        parent_table_by_type = {
            "index": "v_n6_index_condition_display_basis",
            "board": "v_n6_board_condition_display_basis",
        }
        parent_column_by_type = {
            "index": "index_identity_key",
            "board": "board_identity_key",
        }
        parent_name_column_by_type = {
            "index": "index_name",
            "board": "board_name",
        }
        source_table = membership_table_by_type.get(source_asset_type or "")
        parent_table = parent_table_by_type.get(source_asset_type or "")
        parent_column = parent_column_by_type.get(source_asset_type or "")
        parent_name_column = parent_name_column_by_type.get(source_asset_type or "")
        if (
            source_asset_type not in membership_table_by_type
            or not source_identity_keys
            or source_table is None
            or parent_table is None
            or parent_column is None
            or parent_name_column is None
        ):
            return {
                "source_asset_type": source_asset_type,
                "source_identity_keys": source_identity_keys,
                "source_display_names": [],
                "membership_source_table": source_table,
                "membership_trade_date": None,
                "membership_count": 0,
                "matched_stock_count": 0,
                "for_trade_date": selected_for_trade_date,
                "empty_state": "非法来源类型" if source_asset_type not in membership_table_by_type else "暂无来源对象",
                "fallback_used": False,
                "source_filter_active": True,
                "_stock_identity_keys": [],
            }
        if not self._app_v2_relation_exists(source_table) or not self._app_v2_relation_exists(parent_table):
            return {
                "source_asset_type": source_asset_type,
                "source_identity_keys": source_identity_keys,
                "source_display_names": [],
                "membership_source_table": source_table,
                "membership_trade_date": None,
                "membership_count": 0,
                "matched_stock_count": 0,
                "for_trade_date": selected_for_trade_date,
                "empty_state": "暂无成分股",
                "fallback_used": False,
                "source_filter_active": True,
                "_stock_identity_keys": [],
            }
        cur.execute(
            f"""
            SELECT identity_key,
                   COALESCE(NULLIF(display_name, ''), identity_key) AS display_name,
                   max(source_trade_date::text) AS source_trade_date
            FROM {parent_table}
            WHERE identity_key = ANY(%(source_identity_keys)s)
              AND for_trade_date = %(selected_for_trade_date)s
            GROUP BY identity_key, COALESCE(NULLIF(display_name, ''), identity_key)
            """,
            {
                "source_identity_keys": source_identity_keys,
                "selected_for_trade_date": selected_for_trade_date,
            },
        )
        parent_rows = [dict(row) for row in cur.fetchall()]
        parent_display_by_key = {
            str(row.get("identity_key") or "").strip(): str(row.get("display_name") or row.get("identity_key") or "").strip()
            for row in parent_rows
            if str(row.get("identity_key") or "").strip()
        }
        parent_source_dates = sorted(
            {
                str(row.get("source_trade_date") or "").strip()
                for row in parent_rows
                if str(row.get("source_trade_date") or "").strip()
            }
        )
        parent_source_trade_date = parent_source_dates[-1] if parent_source_dates else None
        fallback_used = parent_source_trade_date is None
        if parent_source_trade_date:
            cur.execute(
                f"""
                SELECT max(trade_date::text) AS membership_trade_date
                FROM {source_table}
                WHERE {parent_column} = ANY(%(source_identity_keys)s)
                  AND trade_date::text <= %(parent_source_trade_date)s
                """,
                {
                    "source_identity_keys": source_identity_keys,
                    "parent_source_trade_date": parent_source_trade_date,
                },
            )
        else:
            cur.execute(
                f"""
                SELECT max(trade_date::text) AS membership_trade_date
                FROM {source_table}
                WHERE {parent_column} = ANY(%(source_identity_keys)s)
                """,
                {"source_identity_keys": source_identity_keys},
            )
        membership_trade_date = normalize_filter_value((cur.fetchone() or {}).get("membership_trade_date"))
        if not membership_trade_date and parent_source_trade_date:
            fallback_used = True
            cur.execute(
                f"""
                SELECT max(trade_date::text) AS membership_trade_date
                FROM {source_table}
                WHERE {parent_column} = ANY(%(source_identity_keys)s)
                """,
                {"source_identity_keys": source_identity_keys},
            )
            membership_trade_date = normalize_filter_value((cur.fetchone() or {}).get("membership_trade_date"))
        if membership_trade_date:
            cur.execute(
                f"""
                SELECT {parent_column} AS parent_identity_key,
                       {parent_name_column} AS parent_name,
                       stock_identity_key
                FROM {source_table}
                WHERE {parent_column} = ANY(%(source_identity_keys)s)
                  AND trade_date::text = %(membership_trade_date)s
                ORDER BY {parent_column} ASC, stock_identity_key ASC
                """,
                {
                    "source_identity_keys": source_identity_keys,
                    "membership_trade_date": membership_trade_date,
                },
            )
            membership_rows = [dict(row) for row in cur.fetchall()]
        else:
            membership_rows = []
        for row in membership_rows:
            parent_key = str(row.get("parent_identity_key") or "").strip()
            if parent_key and parent_key not in parent_display_by_key:
                parent_display_by_key[parent_key] = str(row.get("parent_name") or parent_key).strip()
        stock_identity_keys = list(
            dict.fromkeys(
                str(row.get("stock_identity_key") or "").strip()
                for row in membership_rows
                if str(row.get("stock_identity_key") or "").strip()
            )
        )
        return {
            "source_asset_type": source_asset_type,
            "source_identity_keys": source_identity_keys,
            "source_display_names": [
                parent_display_by_key.get(identity_key, identity_key)
                for identity_key in source_identity_keys
            ],
            "membership_source_table": source_table,
            "membership_trade_date": membership_trade_date,
            "membership_count": len(stock_identity_keys),
            "matched_stock_count": 0,
            "for_trade_date": selected_for_trade_date,
            "empty_state": "暂无成分股" if not stock_identity_keys else "",
            "fallback_used": fallback_used,
            "source_filter_active": True,
            "_stock_identity_keys": stock_identity_keys,
        }

    def fetch_app_filter_items(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        asset_kind: str,
        filters: dict[str, Any],
        limit: int,
        include_all_fields: bool = False,
    ) -> dict[str, Any]:
        table_by_asset = {
            "stock": "v_n6_stock_condition_display_basis",
            "index": "v_n6_index_condition_display_basis",
            "board": "v_n6_board_condition_display_basis",
        }
        table_name = table_by_asset.get(asset_kind)
        if table_name is None or not self._app_v2_relation_exists(table_name):
            return {"cache_ready": False, "items": [], "total_count": 0, "filtered_count": 0, "returned_count": 0}
        where_sql, params = self._app_v2_filter_where(filters, asset_kind=asset_kind)
        limit_cap = APP_V2_FILTER_PAGE_MAX_ROWS
        params["limit"] = max(1, min(int(limit), limit_cap))
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT for_trade_date::text AS for_trade_date
                FROM {table_name}
                WHERE for_trade_date IS NOT NULL
                ORDER BY for_trade_date DESC
                LIMIT 120
                """
            )
            available_for_trade_dates = [
                str(row.get("for_trade_date") or "").strip()
                for row in cur.fetchall()
                if str(row.get("for_trade_date") or "").strip()
            ]
            selected_for_trade_date = normalize_filter_value(filters.get("for_trade_date"))
            if not selected_for_trade_date:
                selected_for_trade_date = available_for_trade_dates[0] if available_for_trade_dates else None
            if not selected_for_trade_date:
                return {
                    "cache_ready": True,
                    "items": [],
                    "total_count": 0,
                    "filtered_count": 0,
                    "returned_count": 0,
                    "available_for_trade_dates": available_for_trade_dates,
                    "selected_for_trade_date": "",
                }
            params["selected_for_trade_date"] = selected_for_trade_date
            source_context = (
                self._app_v2_stock_source_context(
                    cur,
                    filters=filters,
                    selected_for_trade_date=selected_for_trade_date,
                )
                if asset_kind == "stock"
                else None
            )
            source_where_sql = "TRUE"
            if source_context and source_context.get("source_filter_active"):
                source_stock_identity_keys = list(source_context.get("_stock_identity_keys") or [])
                if source_stock_identity_keys:
                    params["source_stock_identity_keys"] = source_stock_identity_keys
                    source_where_sql = "identity_key = ANY(%(source_stock_identity_keys)s)"
                else:
                    source_where_sql = "FALSE"
            level_up_recommendation = self._app_v2_filter_level_up_recommendation_context(
                cur,
                filters=filters,
                asset_kind=asset_kind,
                params=params,
                selected_for_trade_date=selected_for_trade_date,
            )
            recommendation_where_sql = str(level_up_recommendation.get("_where_sql") or "TRUE")
            level_up_recommendation.pop("_where_sql", None)
            cur.execute(
                f"""
                SELECT count(*) FILTER (WHERE {source_where_sql})::int AS total_count,
                       count(*) FILTER (WHERE {source_where_sql} AND {where_sql} AND {recommendation_where_sql})::int AS filtered_count
                FROM {table_name}
                WHERE for_trade_date = %(selected_for_trade_date)s
                """,
                params,
            )
            count_row = cur.fetchone() or {}
            total_count = int(count_row.get("total_count") or 0)
            filtered_count = int(count_row.get("filtered_count") or 0)
            order_sql = self._app_v2_filter_order_sql(table_name, filters)
            cur.execute(
                f"""
                SELECT t.*
                FROM {table_name} t
                WHERE {where_sql}
                  AND {source_where_sql}
                  AND {recommendation_where_sql}
                  AND for_trade_date = %(selected_for_trade_date)s
                ORDER BY {order_sql}
                LIMIT %(limit)s
                """,
                params,
            )
            rows = [dict(row) for row in cur.fetchall()]
            linked_stock_filter_source_identity_keys: list[str] = []
            if asset_kind in {"index", "board"}:
                cur.execute(
                    f"""
                    SELECT t.identity_key
                    FROM {table_name} t
                    WHERE {where_sql}
                      AND {source_where_sql}
                      AND {recommendation_where_sql}
                      AND for_trade_date = %(selected_for_trade_date)s
                    ORDER BY {order_sql}
                    """,
                    params,
                )
                linked_stock_filter_source_identity_keys = list(
                    dict.fromkeys(
                        str(row.get("identity_key") or "").strip()
                        for row in cur.fetchall()
                        if str(row.get("identity_key") or "").strip()
                    )
                )
            if asset_kind == "stock":
                self._app_v2_enrich_stock_membership_display_cache(cur, rows)
            if include_all_fields:
                for row in rows:
                    row["_include_all_fields"] = True
            if source_context is not None:
                source_context["matched_stock_count"] = filtered_count
                if (
                    source_context.get("source_filter_active")
                    and source_context.get("membership_count")
                    and not filtered_count
                    and not source_context.get("empty_state")
                ):
                    source_context["empty_state"] = "成分股中无符合当前筛选条件的个股"
                source_context.pop("_stock_identity_keys", None)
        return {
            "cache_ready": True,
            "items": rows,
            "total_count": total_count,
            "filtered_count": filtered_count,
            "returned_count": len(rows),
            "available_for_trade_dates": available_for_trade_dates,
            "selected_for_trade_date": selected_for_trade_date,
            "source_context": source_context,
            "level_up_recommendation": level_up_recommendation,
            "linked_stock_filter_source_identity_keys": linked_stock_filter_source_identity_keys,
        }

    def _app_v2_filter_level_up_recommendation_context(
        self,
        cur: Any,
        *,
        filters: dict[str, Any],
        asset_kind: str,
        params: dict[str, Any],
        selected_for_trade_date: str,
    ) -> dict[str, Any]:
        value = app_v2_level_up_recommendation_value(filters.get("level_up_score_recommendation"))
        if asset_kind not in {"board", "stock"} or value != "index_max":
            return {"active": False, "value": "", "available": True, "_where_sql": "TRUE"}
        context: dict[str, Any] = {
            "active": True,
            "value": "index_max",
            "source_asset_kind": "index",
            "source_field": "level_up_score",
            "available": False,
            "threshold": None,
            "blocker": "",
            "_where_sql": "FALSE",
        }
        if not self._app_v2_relation_exists("v_n6_index_condition_display_basis"):
            context["blocker"] = "index_level_up_score_max_unavailable"
            return context
        cur.execute(
            """
            SELECT max(level_up_score) AS threshold
            FROM v_n6_index_condition_display_basis
            WHERE for_trade_date = %(selected_for_trade_date)s
              AND level_up_score IS NOT NULL
            """,
            {"selected_for_trade_date": selected_for_trade_date},
        )
        row = cur.fetchone() or {}
        threshold = row.get("threshold")
        if threshold is None:
            context["blocker"] = "index_level_up_score_max_unavailable"
            return context
        params["level_up_score_recommendation_min"] = threshold
        context.update(
            {
                "available": True,
                "threshold": threshold,
                "blocker": "",
                "_where_sql": "level_up_score >= %(level_up_score_recommendation_min)s",
            }
        )
        return context

    def _app_v2_enrich_stock_membership_display_cache(self, cur: Any, rows: list[dict[str, Any]]) -> None:
        stock_identity_keys = sorted(
            {
                str(row.get("identity_key") or row.get("stock_identity_key") or "").strip()
                for row in rows
                if str(row.get("identity_key") or row.get("stock_identity_key") or "").strip()
            }
        )
        source_trade_dates = sorted(
            {
                str(row.get("source_trade_date") or "").strip()
                for row in rows
                if str(row.get("source_trade_date") or "").strip()
            }
        )
        if not stock_identity_keys or not source_trade_dates:
            return
        params = {
            "membership_source_trade_date": source_trade_dates[-1],
            "membership_stock_identity_keys": stock_identity_keys,
        }
        if self._app_v2_relation_exists("n6_index_membership_display_cache"):
            cur.execute(
                """
                SELECT stock_identity_key, parent_code, parent_name
                FROM n6_index_membership_display_cache
                WHERE source_trade_date = COALESCE(
                    (
                        SELECT max(source_trade_date)
                        FROM n6_index_membership_display_cache
                        WHERE source_trade_date <= %(membership_source_trade_date)s
                    ),
                    (
                        SELECT max(source_trade_date)
                        FROM n6_index_membership_display_cache
                    )
                  )
                  AND stock_identity_key = ANY(%(membership_stock_identity_keys)s)
                  AND quality_status = 'passed'
                ORDER BY stock_identity_key ASC, parent_code ASC
                """,
                params,
            )
            index_memberships_by_stock: dict[str, list[dict[str, Any]]] = {}
            for row in cur.fetchall():
                stock_key = str(row.get("stock_identity_key") or "").strip()
                if stock_key:
                    index_memberships_by_stock.setdefault(stock_key, []).append(dict(row))
        else:
            index_memberships_by_stock = {}
        if self._app_v2_relation_exists("n6_board_membership_display_cache"):
            cur.execute(
                """
                SELECT stock_identity_key, parent_identity_key, parent_code, parent_name
                FROM n6_board_membership_display_cache
                WHERE source_trade_date = COALESCE(
                    (
                        SELECT max(source_trade_date)
                        FROM n6_board_membership_display_cache
                        WHERE source_trade_date <= %(membership_source_trade_date)s
                    ),
                    (
                        SELECT max(source_trade_date)
                        FROM n6_board_membership_display_cache
                    )
                  )
                  AND stock_identity_key = ANY(%(membership_stock_identity_keys)s)
                  AND board_type = 'tdx_industry'
                  AND quality_status = 'passed'
                ORDER BY stock_identity_key ASC, parent_code ASC
                """,
                params,
            )
            industry_membership_by_stock: dict[str, dict[str, Any]] = {}
            for row in cur.fetchall():
                stock_key = str(row.get("stock_identity_key") or "").strip()
                if stock_key and stock_key not in industry_membership_by_stock:
                    industry_membership_by_stock[stock_key] = dict(row)
        else:
            industry_membership_by_stock = {}
        for row in rows:
            stock_key = str(row.get("identity_key") or row.get("stock_identity_key") or "").strip()
            industry = industry_membership_by_stock.get(stock_key)
            if industry:
                row["industry_code"] = industry.get("parent_code")
                row["industry_name"] = industry.get("parent_name")
            index_memberships = index_memberships_by_stock.get(stock_key) or []
            if index_memberships:
                row["index_codes"] = ",".join(
                    str(item.get("parent_code") or "").strip()
                    for item in index_memberships
                    if str(item.get("parent_code") or "").strip()
                )
                row["index_names"] = ",".join(
                    str(item.get("parent_name") or "").strip()
                    for item in index_memberships
                    if str(item.get("parent_name") or "").strip()
                )

    def fetch_app_filter_members(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        membership_kind: str,
        parent_identity_key: str,
        limit: int,
    ) -> dict[str, Any]:
        table_by_kind = {
            "index": "v_n6_index_membership_fact",
            "board": "v_n6_board_membership_fact",
        }
        table_name = table_by_kind.get(membership_kind)
        if table_name is None or not self._app_v2_relation_exists(table_name):
            return {"cache_ready": False, "items": []}
        membership_select_by_kind = {
            "index": """
                       'index'::text AS membership_kind,
                       trade_date,
                       index_identity_key,
                       index_identity_key AS parent_identity_key,
                       index_code,
                       index_code AS parent_code,
                       index_name,
                       index_name AS parent_name,
                       stock_identity_key,
                       stock_code,
                       stock_name,
                       NULL::text AS board_type,
                       source_version,
                       source_batch_id
            """,
            "board": """
                       'board'::text AS membership_kind,
                       trade_date,
                       board_identity_key,
                       board_identity_key AS parent_identity_key,
                       board_code,
                       board_code AS parent_code,
                       board_name,
                       board_name AS parent_name,
                       stock_identity_key,
                       stock_code,
                       stock_name,
                       board_type,
                       source_version,
                       source_batch_id
            """,
        }
        membership_select = membership_select_by_kind[membership_kind]
        parent_column = "index_identity_key" if membership_kind == "index" else "board_identity_key"
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {membership_select}
                FROM {table_name}
                WHERE {parent_column} = %(parent_identity_key)s
                  AND trade_date = (SELECT max(trade_date) FROM {table_name})
                ORDER BY stock_code ASC, stock_identity_key ASC
                LIMIT %(limit)s
                """,
                {
                    "parent_identity_key": parent_identity_key,
                    "limit": max(1, min(int(limit), 500)),
                },
            )
            rows = [dict(row) for row in cur.fetchall()]
        return {"cache_ready": True, "items": rows}

    def fetch_app_filter_linked_stocks(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        membership_kind: str,
        parent_identity_key: str,
        limit: int,
        view: str = "matched",
    ) -> dict[str, Any]:
        del principal_id, principal_type, user_id
        view = "all" if view == "all" else "matched"
        table_by_kind = {
            "index": "v_n6_index_membership_fact",
            "board": "v_n6_board_membership_fact",
        }
        membership_table = table_by_kind.get(membership_kind)
        stock_table = "v_n6_stock_condition_display_basis"
        if (
            membership_table is None
            or not self._app_v2_relation_exists(membership_table)
            or not self._app_v2_relation_exists(stock_table)
        ):
            return {
                "cache_ready": False,
                "items": [],
                "membership_count": 0,
                "linked_count": 0,
                "missing_count": 0,
                "view": view,
                "current_view_count": 0,
            }
        membership_select_by_kind = {
            "index": """
                       'index'::text AS membership_kind,
                       m.trade_date,
                       m.index_identity_key,
                       m.index_identity_key AS parent_identity_key,
                       m.index_code,
                       m.index_code AS parent_code,
                       m.index_name,
                       m.index_name AS parent_name,
                       m.stock_identity_key,
                       m.stock_code,
                       m.stock_name,
                       NULL::text AS board_type,
                       m.source_version,
                       m.source_batch_id
            """,
            "board": """
                       'board'::text AS membership_kind,
                       m.trade_date,
                       m.board_identity_key,
                       m.board_identity_key AS parent_identity_key,
                       m.board_code,
                       m.board_code AS parent_code,
                       m.board_name,
                       m.board_name AS parent_name,
                       m.stock_identity_key,
                       m.stock_code,
                       m.stock_name,
                       m.board_type,
                       m.source_version,
                       m.source_batch_id
            """,
        }
        membership_select = membership_select_by_kind[membership_kind]
        parent_column = "index_identity_key" if membership_kind == "index" else "board_identity_key"
        query_params = {
            "parent_identity_key": parent_identity_key,
            "limit": max(1, min(int(limit), APP_V2_FILTER_PAGE_MAX_ROWS)),
        }
        join_type = "LEFT JOIN" if view == "all" else "JOIN"
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                WITH latest_membership AS (
                  SELECT max(trade_date) AS trade_date
                  FROM {membership_table}
                ),
                latest_stock AS (
                  SELECT max(source_trade_date) AS source_trade_date
                  FROM v_n6_stock_condition_display_basis
                ),
                membership_rows AS (
                  SELECT {membership_select}
                  FROM {membership_table} m, latest_membership lm
                  WHERE m.{parent_column} = %(parent_identity_key)s
                    AND m.trade_date = lm.trade_date
                ),
                stock_rows AS (
                  SELECT identity_key
                  FROM v_n6_stock_condition_display_basis s, latest_stock ls
                  WHERE s.source_trade_date = ls.source_trade_date
                )
                SELECT (SELECT count(*) FROM membership_rows)::int AS membership_count,
                       (
                         SELECT count(*)
                         FROM membership_rows mr
                         JOIN stock_rows s ON s.identity_key = mr.stock_identity_key
                       )::int AS linked_count
                """,
                query_params,
            )
            count_row = cur.fetchone() or {}
            membership_count = int(count_row.get("membership_count") or 0)
            linked_count = int(count_row.get("linked_count") or 0)
            missing_count = max(0, membership_count - linked_count)
            cur.execute(
                f"""
                WITH latest_membership AS (
                  SELECT max(trade_date) AS trade_date
                  FROM {membership_table}
                ),
                latest_stock AS (
                  SELECT max(source_trade_date) AS source_trade_date
                  FROM v_n6_stock_condition_display_basis
                ),
                membership_rows AS (
                  SELECT {membership_select}
                  FROM {membership_table} m, latest_membership lm
                  WHERE m.{parent_column} = %(parent_identity_key)s
                    AND m.trade_date = lm.trade_date
                )
                SELECT NULL::text AS cache_run_id,
                       'stock'::text AS asset_kind,
                       COALESCE(s.identity_key, mr.stock_identity_key) AS identity_key,
                       s.source_display_basis_id,
                       s.run_id,
                       s.for_trade_date,
                       s.source_trade_date,
                       COALESCE(s.stock_identity_key, mr.stock_identity_key) AS stock_identity_key,
                       COALESCE(s.code, mr.stock_code) AS code,
                       s.exchange,
                       COALESCE(s.name, mr.stock_name) AS name,
                       COALESCE(s.display_title, CONCAT(mr.stock_code, ' ', mr.stock_name)) AS display_title,
                       COALESCE(s.display_summary, 'not_in_stock_filter') AS display_summary,
                       s.period_transition_y,
                       s.period_transition_q,
                       s.period_transition_m,
                       s.period_transition_w,
                       s.period_transition_d,
                       s.buy_target_price,
                       s.sell_target_price,
                       s.up_sell_reference_period,
                       s.down_buy_reference_period,
                       s.total_mv,
                       s.circ_mv,
                       s.score,
                       s.recommendation_level,
                       s.main_index_code,
                       s.main_index_name,
                       s.preferred_board_code,
                       s.preferred_board_name,
                       s.is_st,
                       s.stock_status,
                       s.display_status,
                       s.quality_reason,
                       COALESCE(s.display_code, mr.stock_code) AS display_code,
                       COALESCE(s.display_name, mr.stock_name) AS display_name,
                       NULL::text AS direction,
                       NULL::text AS condition_key,
                       s.selected_directions,
                       s.selected_condition_keys,
                       s.selected_signal_types,
                       s.selected_lanes,
                       s.selected_monitor_types,
                       s.period_grade_y,
                       s.period_grade_q,
                       s.period_grade_m,
                       s.period_grade_w,
                       s.period_grade_d,
                       s.period_grade_y AS year_overheat_level,
                       s.period_grade_q AS quarter_overheat_level,
                       s.period_grade_m AS month_overheat_level,
                       s.period_grade_w AS week_overheat_level,
                       s.period_grade_d AS day_overheat_level,
                       NULL::text AS last_signal_state,
                       s.quality_status,
                       s.run_id AS source_run_id,
                       NULL::text AS projection_run_id,
                       NULL::text AS board_type,
                       s.updated_at AS source_updated_at,
                       CASE WHEN s.identity_key IS NULL THEN FALSE ELSE TRUE END AS in_stock_filter,
                       CASE WHEN s.identity_key IS NULL THEN 'not_in_filter' ELSE 'in_filter' END AS stock_filter_status,
                       mr.membership_kind,
                       mr.trade_date AS membership_trade_date,
                       mr.parent_identity_key,
                       mr.parent_code,
                       mr.parent_name,
                       mr.stock_code,
                       mr.stock_name,
                       mr.board_type AS membership_board_type,
                       mr.source_version AS membership_source_version,
                       mr.source_batch_id AS membership_source_batch_id
                FROM membership_rows mr
                {join_type} v_n6_stock_condition_display_basis s
                  ON s.identity_key = mr.stock_identity_key
                 AND s.source_trade_date = (SELECT source_trade_date FROM latest_stock)
                ORDER BY s.score DESC NULLS LAST, COALESCE(s.identity_key, mr.stock_identity_key) ASC
                LIMIT %(limit)s
                """,
                query_params,
            )
            rows = [dict(row) for row in cur.fetchall()]
        return {
            "cache_ready": True,
            "items": rows,
            "membership_count": membership_count,
            "linked_count": linked_count,
            "missing_count": missing_count,
            "view": view,
            "current_view_count": len(rows),
        }

    def fetch_app_membership_stocks(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        entity_type: str,
        identity_key: str,
        limit: int,
    ) -> dict[str, Any]:
        del principal_id, principal_type, user_id
        table_by_type = {
            "index": "v_n6_index_membership_fact",
            "board": "v_n6_board_membership_fact",
        }
        table_name = table_by_type.get(entity_type)
        if table_name is None or not self._app_v2_relation_exists(table_name):
            return {"members": [], "member_count": 0}
        if entity_type == "index":
            parent_column = "index_identity_key"
            select_sql = """
                index_identity_key,
                stock_identity_key,
                stock_name,
                stock_code,
                trade_date,
                NULL::numeric AS weight
            """
        else:
            parent_column = "board_identity_key"
            select_sql = """
                board_identity_key,
                stock_identity_key,
                stock_name,
                stock_code,
                trade_date,
                NULL::numeric AS weight
            """
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {select_sql}
                FROM {table_name}
                WHERE {parent_column} = %(identity_key)s
                  AND trade_date = (SELECT max(trade_date) FROM {table_name})
                ORDER BY stock_code ASC, stock_identity_key ASC
                LIMIT %(limit)s
                """,
                {
                    "identity_key": identity_key,
                    "limit": max(1, min(int(limit), 500)),
                },
            )
            rows = [dict(row) for row in cur.fetchall()]
        members = (
            get_index_membership_stocks(identity_key, rows)
            if entity_type == "index"
            else get_board_membership_stocks(identity_key, rows)
        )
        return {"members": members, "member_count": len(members)}

    def fetch_app_monitor_items(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        asset_kind: str | None = None,
        limit: int = 500,
        monitor_status: str = "active",
        for_trade_date: str = "",
    ) -> dict[str, Any]:
        table_items = list(APP_V2_MONITOR_TABLE_BY_ASSET.items())
        if asset_kind is not None:
            table_name = APP_V2_MONITOR_TABLE_BY_ASSET.get(asset_kind)
            table_items = [(asset_kind, table_name)] if table_name else []
        if not table_items:
            return {"tables_ready": False, "items": []}
        monitor_status = app_v2_monitor_status_filter(monitor_status)
        existing_tables = [
            (kind, table_name)
            for kind, table_name in table_items
            if table_name and self._app_v2_monitor_relation_exists(table_name)
        ]
        if len(existing_tables) != len(table_items):
            return {"tables_ready": False, "items": []}
        requested_for_trade_date = self._batch_text(for_trade_date)
        selected_for_trade_date = requested_for_trade_date
        available_for_trade_dates = self._app_v2_monitor_available_for_trade_dates(
            [kind for kind, _ in existing_tables]
        )
        if not selected_for_trade_date and available_for_trade_dates:
            selected_for_trade_date = available_for_trade_dates[0]
        current_filter_batch = self._app_v2_current_filter_batches(
            [kind for kind, _ in existing_tables],
            for_trade_date=selected_for_trade_date,
        )
        query_parts = []
        params: dict[str, Any] = {
            "principal_id": principal_id,
            "principal_type": principal_type,
            "limit": max(1, min(max(int(limit) * 5, int(limit)), 5000)),
            "selected_for_trade_date": selected_for_trade_date,
        }
        for kind, table_name in existing_tables:
            columns = self._app_v2_monitor_columns(table_name)
            display_table = APP_V2_FILTER_DISPLAY_TABLE_BY_ASSET.get(kind, "")
            display_join = ""
            display_json_expr = "'{}'::jsonb"
            if (
                selected_for_trade_date
                and display_table
                and self._app_v2_relation_exists(display_table)
            ):
                display_join = f"""
                LEFT JOIN {display_table} display_row
                  ON display_row.identity_key = monitor_base.identity_key
                 AND display_row.for_trade_date::text = %(selected_for_trade_date)s
                """
                display_json_expr = "COALESCE(to_jsonb(display_row), '{}'::jsonb)"
            valid_source_trade_expr = (
                "COALESCE(monitor_base.valid_source_trade_date, monitor_base.source_snapshot_json->>'source_trade_date')"
                if "valid_source_trade_date" in columns
                else "monitor_base.source_snapshot_json->>'source_trade_date'"
            )
            valid_for_trade_expr = (
                "COALESCE(monitor_base.valid_for_trade_date, monitor_base.source_snapshot_json->>'for_trade_date')"
                if "valid_for_trade_date" in columns
                else "monitor_base.source_snapshot_json->>'for_trade_date'"
            )
            valid_run_expr = (
                "COALESCE(monitor_base.valid_source_run_id, monitor_base.source_snapshot_json->>'source_run_id')"
                if "valid_source_run_id" in columns
                else "monitor_base.source_snapshot_json->>'source_run_id'"
            )
            expired_at_expr = "monitor_base.expired_at" if "expired_at" in columns else "NULL::timestamptz"
            expired_reason_expr = "monitor_base.expired_reason" if "expired_reason" in columns else "NULL::text"
            user_id_expr = "monitor_base.user_id" if "user_id" in columns else "NULL::text"
            user_filter_clause = "AND monitor_base.user_id = %(user_id)s" if "user_id" in columns else ""
            params["user_id"] = str(user_id)
            query_parts.append(
                f"""
                SELECT monitor_base.monitor_id,
                       monitor_base.principal_id,
                       monitor_base.principal_type,
                       {user_id_expr} AS user_id,
                       '{kind}'::text AS asset_kind,
                       monitor_base.identity_key,
                       monitor_base.direction,
                       monitor_base.source_type AS source,
                       monitor_base.condition_key,
                       monitor_base.source_run_id,
                       monitor_base.projection_run_id,
                       monitor_base.status,
                       monitor_base.quality_status,
                       monitor_base.last_signal_state,
                       {valid_source_trade_expr} AS valid_source_trade_date,
                       {valid_for_trade_expr} AS valid_for_trade_date,
                       {valid_run_expr} AS valid_source_run_id,
                       {expired_at_expr} AS expired_at,
                       {expired_reason_expr} AS expired_reason,
                       monitor_base.source_snapshot_json,
                       monitor_base.source_snapshot_json->>'display_name' AS display_name,
                       monitor_base.source_snapshot_json->>'display_code' AS display_code,
                       monitor_base.source_snapshot_json->>'parent_asset_kind' AS source_parent_asset_kind,
                       monitor_base.source_snapshot_json->>'parent_identity_key' AS source_parent_identity_key,
                       monitor_base.source_snapshot_json->>'parent_code' AS source_parent_code,
                       monitor_base.source_snapshot_json->>'parent_name' AS source_parent_name,
                       monitor_base.source_snapshot_json->>'membership_trade_date' AS source_parent_trade_date,
                       monitor_base.source_snapshot_json->>'membership_source_version' AS source_parent_source_version,
                       monitor_base.source_snapshot_json->>'membership_source_batch_id' AS source_parent_source_batch_id,
                       monitor_base.source_snapshot_json->>'linked_mode' AS source_linked_mode,
                       {display_json_expr} AS current_display_row_json,
                       monitor_base.created_at,
                       monitor_base.updated_at,
                       monitor_base.removed_at
                FROM {table_name} monitor_base
                {display_join}
                WHERE monitor_base.principal_id = %(principal_id)s
                  AND monitor_base.principal_type = %(principal_type)s
                  {user_filter_clause}
                  AND monitor_base.status <> 'removed'
                """
            )
        union_sql = "\nUNION ALL\n".join(query_parts)
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM (
                  {union_sql}
                ) monitor_rows
                ORDER BY created_at DESC NULLS LAST, monitor_id DESC
                LIMIT %(limit)s
                """,
                params,
            )
            rows = [dict(row) for row in cur.fetchall()]
        self._app_v2_apply_monitor_validity(rows, current_filter_batch)
        if requested_for_trade_date:
            rows = [
                row
                for row in rows
                if self._batch_text(row.get("valid_for_trade_date")) == requested_for_trade_date
            ]
        status_counts = self._app_v2_monitor_status_counts(rows)
        if monitor_status != "all":
            rows = [row for row in rows if row.get("effective_status") == monitor_status]
        rows = rows[: max(1, min(int(limit), 1000))]
        self._app_v2_enrich_monitor_memberships(rows)
        return {
            "tables_ready": True,
            "items": rows,
            "monitor_status_filter": monitor_status,
            "current_filter_batch": current_filter_batch,
            "selected_for_trade_date": selected_for_trade_date,
            "available_for_trade_dates": available_for_trade_dates,
            "status_counts": status_counts,
        }

    def _app_v2_monitor_columns(self, table_name: str) -> set[str]:
        if table_name not in set(APP_V2_MONITOR_TABLE_BY_ASSET.values()):
            return set()
        cached = self._app_v2_monitor_column_cache.get(table_name)
        if cached is not None:
            return set(cached)
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = %s
                """,
                (table_name,),
            )
            columns = {str(row["column_name"]) for row in cur.fetchall()}
        self._app_v2_monitor_column_cache[table_name] = set(columns)
        return columns

    def _app_v2_monitor_available_for_trade_dates(self, asset_kinds: list[str]) -> list[str]:
        dates: set[str] = set()
        with self._readonly_connection() as conn, conn.cursor() as cur:
            for asset_kind in asset_kinds:
                table_name = APP_V2_FILTER_DISPLAY_TABLE_BY_ASSET.get(asset_kind)
                if table_name is None or not self._app_v2_relation_exists(table_name):
                    continue
                cur.execute(
                    f"""
                    SELECT DISTINCT for_trade_date::text AS for_trade_date
                    FROM {table_name}
                    WHERE for_trade_date IS NOT NULL
                    """
                )
                dates.update(str(row.get("for_trade_date") or "").strip() for row in cur.fetchall())
        return sorted((date for date in dates if date), reverse=True)

    def _app_v2_current_filter_batches(
        self,
        asset_kinds: list[str],
        *,
        for_trade_date: str = "",
    ) -> dict[str, dict[str, str]]:
        table_by_asset = {
            "stock": "v_n6_stock_condition_display_basis",
            "index": "v_n6_index_condition_display_basis",
            "board": "v_n6_board_condition_display_basis",
        }
        batches = {
            asset_kind: {
                "source_trade_date": "",
                "for_trade_date": "",
                "source_run_id": "",
            }
            for asset_kind in APP_V2_MONITOR_TABLE_BY_ASSET
        }
        with self._readonly_connection() as conn, conn.cursor() as cur:
            for asset_kind in asset_kinds:
                table_name = table_by_asset.get(asset_kind)
                if table_name is None or not self._app_v2_relation_exists(table_name):
                    continue
                params: dict[str, Any] = {}
                where_clause = "source_trade_date = (SELECT max(source_trade_date) FROM {table_name})"
                if for_trade_date:
                    where_clause = "for_trade_date::text = %(for_trade_date)s"
                    params["for_trade_date"] = for_trade_date
                cur.execute(
                    f"""
                    SELECT source_trade_date::text AS source_trade_date,
                           for_trade_date::text AS for_trade_date,
                           run_id::text AS source_run_id
                    FROM {table_name}
                    WHERE {where_clause.format(table_name=table_name)}
                    ORDER BY updated_at DESC NULLS LAST,
                             source_trade_date DESC NULLS LAST,
                             for_trade_date DESC NULLS LAST,
                             identity_key ASC
                    LIMIT 1
                    """,
                    params,
                )
                row = cur.fetchone()
                if row:
                    batches[asset_kind] = {
                        "source_trade_date": str(row.get("source_trade_date") or "").strip(),
                        "for_trade_date": str(row.get("for_trade_date") or "").strip(),
                        "source_run_id": str(row.get("source_run_id") or "").strip(),
                    }
        return batches

    def _app_v2_apply_monitor_validity(
        self,
        rows: list[dict[str, Any]],
        current_filter_batch: dict[str, dict[str, str]],
    ) -> None:
        for row in rows:
            asset_kind = str(row.get("asset_kind") or "").strip()
            current_batch = current_filter_batch.get(asset_kind) or {}
            self._app_v2_apply_monitor_validity_to_row(row, current_batch)

    def _app_v2_apply_monitor_validity_to_row(self, row: dict[str, Any], current_batch: dict[str, Any]) -> None:
        snapshot = row.get("source_snapshot_json")
        if isinstance(snapshot, str):
            try:
                snapshot = json.loads(snapshot)
            except json.JSONDecodeError:
                snapshot = {}
        snapshot = snapshot if isinstance(snapshot, dict) else {}

        original_batch = {
            "source_trade_date": self._batch_text(row.get("valid_source_trade_date") or snapshot.get("source_trade_date")),
            "for_trade_date": self._batch_text(row.get("valid_for_trade_date") or snapshot.get("for_trade_date")),
            "source_run_id": self._batch_text(
                row.get("valid_source_run_id")
                or snapshot.get("source_run_id")
                or row.get("source_run_id")
            ),
        }
        normalized_current = {
            "source_trade_date": self._batch_text(current_batch.get("source_trade_date")),
            "for_trade_date": self._batch_text(current_batch.get("for_trade_date")),
            "source_run_id": self._batch_text(current_batch.get("source_run_id")),
        }
        row["valid_source_trade_date"] = original_batch["source_trade_date"]
        row["valid_for_trade_date"] = original_batch["for_trade_date"]
        row["valid_source_run_id"] = original_batch["source_run_id"]

        status = str(row.get("status") or "active").strip().lower()
        effective_status = status
        effective_active = False
        expired_reason = self._batch_text(row.get("expired_reason"))
        if status == "removed":
            effective_status = "removed"
        elif status == "expired":
            effective_status = "expired"
        elif status == "active":
            source_trade_matches = (
                original_batch["source_trade_date"]
                and original_batch["source_trade_date"] == normalized_current["source_trade_date"]
            )
            for_trade_matches = (
                original_batch["for_trade_date"]
                and original_batch["for_trade_date"] == normalized_current["for_trade_date"]
            )
            run_matches = (
                original_batch["source_run_id"]
                and original_batch["source_run_id"] == normalized_current["source_run_id"]
            )
            effective_active = bool(source_trade_matches and for_trade_matches and run_matches)
            if not effective_active:
                effective_status = "expired"
                expired_reason = expired_reason or "filter_batch_changed"

        row["effective_status"] = effective_status
        row["effective_active"] = bool(effective_active)
        row["expired_reason"] = expired_reason
        row["expired_reason_label"] = {
            "filter_batch_changed": "筛选中心已更新",
            "current_filter_batch_missing": "当前筛选批次不可用",
            "source_batch_missing": "来源批次缺失",
        }.get(expired_reason, "筛选中心已更新" if effective_status == "expired" else "")
        row["effective_status_label"] = {
            "active": "有效",
            "expired": "已失效",
            "removed": "已删除",
        }.get(effective_status, effective_status)
        row["validity"] = {
            "original_batch": original_batch,
            "current_batch": normalized_current,
        }

    def _app_v2_monitor_status_counts(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
        counts = {
            asset_kind: {"active": 0, "expired": 0, "removed": 0, "all": 0}
            for asset_kind in APP_V2_MONITOR_TABLE_BY_ASSET
        }
        for row in rows:
            asset_kind = str(row.get("asset_kind") or "").strip()
            if asset_kind not in counts:
                continue
            effective_status = str(row.get("effective_status") or "expired").strip()
            counts[asset_kind]["all"] += 1
            if effective_status in counts[asset_kind]:
                counts[asset_kind][effective_status] += 1
        return counts

    @staticmethod
    def _batch_text(value: Any) -> str:
        text = str(value or "").strip()
        return text

    def _app_v2_enrich_monitor_memberships(self, rows: list[dict[str, Any]]) -> None:
        stock_identity_keys = sorted(
            {
                str(row.get("identity_key") or "").strip()
                for row in rows
                if row.get("asset_kind") == "stock" and str(row.get("identity_key") or "").strip()
            }
        )
        empty_memberships = {
            "indexes": [],
            "boards": [],
            "index_count": 0,
            "board_count": 0,
            "summary_label": "所属指数 0 个 / 所属板块 0 个",
        }
        for row in rows:
            row["current_memberships"] = dict(empty_memberships)
        if not stock_identity_keys:
            return

        memberships_by_stock = {
            identity_key: {"indexes": [], "boards": []}
            for identity_key in stock_identity_keys
        }
        for membership in self._app_v2_fetch_stock_membership_context("index", stock_identity_keys):
            stock_identity_key = str(membership.get("stock_identity_key") or "").strip()
            if stock_identity_key in memberships_by_stock:
                memberships_by_stock[stock_identity_key]["indexes"].append(membership)
        for membership in self._app_v2_fetch_stock_membership_context("board", stock_identity_keys):
            stock_identity_key = str(membership.get("stock_identity_key") or "").strip()
            if stock_identity_key in memberships_by_stock:
                memberships_by_stock[stock_identity_key]["boards"].append(membership)

        for row in rows:
            if row.get("asset_kind") != "stock":
                continue
            identity_key = str(row.get("identity_key") or "").strip()
            current = memberships_by_stock.get(identity_key, {"indexes": [], "boards": []})
            index_count = len(current["indexes"])
            board_count = len(current["boards"])
            display_row = row.get("current_display_row_json")
            display_row = display_row if isinstance(display_row, dict) else {}
            industry = next(
                (
                    membership
                    for membership in current["boards"]
                    if str(membership.get("board_type") or "").strip() == "tdx_industry"
                ),
                None,
            )
            if industry:
                display_row = dict(display_row)
                display_row.setdefault("industry_code", industry.get("display_code"))
                display_row.setdefault("industry_name", industry.get("display_name"))
                row["current_display_row_json"] = display_row
            row["current_memberships"] = {
                "indexes": current["indexes"],
                "boards": current["boards"],
                "index_count": index_count,
                "board_count": board_count,
                "summary_label": f"所属指数 {index_count} 个 / 所属板块 {board_count} 个",
            }

    def _app_v2_fetch_stock_membership_context(
        self,
        membership_kind: str,
        stock_identity_keys: list[str],
    ) -> list[dict[str, Any]]:
        table_name = {
            "index": "v_n6_index_membership_fact",
            "board": "v_n6_board_membership_fact",
        }.get(membership_kind)
        if table_name is None or not stock_identity_keys or not self._app_v2_relation_exists(table_name):
            return []
        select_sql = {
            "index": """
                m.stock_identity_key,
                'index'::text AS asset_kind,
                m.index_identity_key AS identity_key,
                m.index_code AS display_code,
                m.index_name AS display_name,
                NULL::text AS board_type,
                m.trade_date,
                m.source_version,
                m.source_batch_id
            """,
            "board": """
                m.stock_identity_key,
                'board'::text AS asset_kind,
                m.board_identity_key AS identity_key,
                m.board_code AS display_code,
                m.board_name AS display_name,
                m.board_type,
                m.trade_date,
                m.source_version,
                m.source_batch_id
            """,
        }[membership_kind]
        order_sql = (
            "m.index_code ASC NULLS LAST, m.index_identity_key ASC"
            if membership_kind == "index"
            else "m.board_type ASC NULLS LAST, m.board_code ASC NULLS LAST, m.board_identity_key ASC"
        )
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {select_sql}
                FROM {table_name} m
                WHERE m.stock_identity_key = ANY(%(stock_identity_keys)s)
                  AND m.trade_date = (SELECT max(trade_date) FROM {table_name})
                ORDER BY m.stock_identity_key ASC, {order_sql}
                """,
                {"stock_identity_keys": stock_identity_keys},
            )
            return [dict(row) for row in cur.fetchall()]

    def add_app_monitor_item(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        asset_kind: str,
        identity_key: str,
        direction: str,
        source: str = "single_row",
        for_trade_date: str = "",
    ) -> dict[str, Any]:
        table_name = APP_V2_MONITOR_TABLE_BY_ASSET.get(asset_kind)
        if table_name is None or direction not in APP_V2_VALID_DIRECTIONS:
            return {"ok": False, "status": "invalid_request", "error": "invalid_monitor_request"}
        if not self._app_v2_monitor_relation_exists(table_name):
            return {"ok": False, "status": "data_not_ready", "error": "monitor_table_not_ready"}
        source_row = self._app_v2_fetch_filter_source_row(
            asset_kind=asset_kind,
            identity_key=identity_key,
            for_trade_date=for_trade_date,
        )
        if source_row is None:
            return {"ok": False, "status": "not_found", "error": "source_not_found"}
        snapshot = self._app_v2_monitor_snapshot(source_row, asset_kind=asset_kind)
        condition_key = self._app_v2_monitor_condition_key(source_row)
        with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction(), conn.cursor() as cur:
                existing = self._app_v2_fetch_existing_monitor(
                    cur,
                    table_name=table_name,
                    principal_id=principal_id,
                    principal_type=principal_type,
                    user_id=user_id,
                    identity_key=identity_key,
                    direction=direction,
                    valid_source_trade_date=snapshot.get("source_trade_date"),
                    valid_for_trade_date=snapshot.get("for_trade_date"),
                    valid_source_run_id=snapshot.get("source_run_id"),
                    require_matching_batch=self._app_v2_monitor_batch_identity_enabled(table_name),
                )
                if existing:
                    return {
                        "ok": True,
                        "status": "already_exists",
                        "added_count": 0,
                        "skipped_count": 1,
                        "item": dict(existing),
                    }
                lifecycle_columns, lifecycle_values, lifecycle_params = self._app_v2_monitor_lifecycle_insert_parts(
                    table_name,
                    snapshot,
                )
                user_id_columns, user_id_values, user_id_params = self._app_v2_monitor_user_insert_parts(
                    table_name,
                    user_id,
                )
                insert_params = {
                    "principal_id": principal_id,
                    "principal_type": principal_type,
                    "asset_kind": asset_kind,
                    "identity_key": identity_key,
                    "direction": direction,
                    "source_type": source,
                    "source_run_id": snapshot.get("source_run_id"),
                    "projection_run_id": snapshot.get("projection_run_id"),
                    "condition_key": condition_key,
                    "quality_status": snapshot.get("quality_status") or "reviewed",
                    "last_signal_state": snapshot.get("last_signal_state"),
                    "source_snapshot_json": Jsonb(snapshot),
                }
                insert_params.update(lifecycle_params)
                insert_params.update(user_id_params)
                cur.execute(
                    f"""
                    INSERT INTO {table_name} (
                      principal_id,
                      principal_type,
                      asset_kind
                      {user_id_columns},
                      identity_key,
                      direction,
                      source_type,
                      source_run_id,
                      projection_run_id,
                      condition_key,
                      status,
                      quality_status,
                      last_signal_state,
                      source_snapshot_json
                      {lifecycle_columns}
                    )
                    VALUES (
                      %(principal_id)s,
                      %(principal_type)s,
                      %(asset_kind)s
                      {user_id_values},
                      %(identity_key)s,
                      %(direction)s,
                      %(source_type)s,
                      %(source_run_id)s,
                      %(projection_run_id)s,
                      %(condition_key)s,
                      'active',
                      %(quality_status)s,
                      %(last_signal_state)s,
                      %(source_snapshot_json)s
                      {lifecycle_values}
                    )
                    RETURNING monitor_id,
                              principal_id,
                              principal_type,
                              asset_kind,
                              identity_key,
                              direction,
                              source_type AS source,
                              condition_key,
                              source_run_id,
                              projection_run_id,
                              status,
                              quality_status,
                              last_signal_state,
                              created_at,
                              updated_at
                    """,
                    insert_params,
                )
                item = dict(cur.fetchone())
        return {"ok": True, "status": "added", "added_count": 1, "skipped_count": 0, "item": item}

    def bulk_add_app_monitor_items(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        asset_kind: str,
        direction: str,
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        table_name = APP_V2_MONITOR_TABLE_BY_ASSET.get(asset_kind)
        if table_name is None or direction not in APP_V2_VALID_DIRECTIONS:
            return {"ok": False, "status": "invalid_request", "error": "invalid_monitor_request"}
        if not self._app_v2_monitor_relation_exists(table_name):
            return {"ok": False, "status": "data_not_ready", "error": "monitor_table_not_ready"}
        result = self.fetch_app_filter_items(
            principal_id=principal_id,
            principal_type=principal_type,
            user_id=user_id,
            asset_kind=asset_kind,
            filters=filters,
            limit=APP_V2_FILTER_PAGE_MAX_ROWS,
        )
        if not result.get("cache_ready"):
            return {"ok": False, "status": "data_not_ready", "error": "filter_source_not_ready"}
        added = 0
        skipped = 0
        with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction(), conn.cursor() as cur:
                for source_row in result.get("items") or []:
                    identity_key = str(source_row.get("identity_key") or "").strip()
                    if not identity_key:
                        continue
                    snapshot = self._app_v2_monitor_snapshot(source_row, asset_kind=asset_kind)
                    existing = self._app_v2_fetch_existing_monitor(
                        cur,
                        table_name=table_name,
                        principal_id=principal_id,
                        principal_type=principal_type,
                        user_id=user_id,
                        identity_key=identity_key,
                        direction=direction,
                        valid_source_trade_date=snapshot.get("source_trade_date"),
                        valid_for_trade_date=snapshot.get("for_trade_date"),
                        valid_source_run_id=snapshot.get("source_run_id"),
                        require_matching_batch=self._app_v2_monitor_batch_identity_enabled(table_name),
                    )
                    if existing:
                        skipped += 1
                        continue
                    lifecycle_columns, lifecycle_values, lifecycle_params = self._app_v2_monitor_lifecycle_insert_parts(
                        table_name,
                        snapshot,
                    )
                    user_id_columns, user_id_values, user_id_params = self._app_v2_monitor_user_insert_parts(
                        table_name,
                        user_id,
                    )
                    insert_params = {
                        "principal_id": principal_id,
                        "principal_type": principal_type,
                        "asset_kind": asset_kind,
                        "identity_key": identity_key,
                        "direction": direction,
                        "source_run_id": snapshot.get("source_run_id"),
                        "projection_run_id": snapshot.get("projection_run_id"),
                        "condition_key": self._app_v2_monitor_condition_key(source_row),
                        "quality_status": snapshot.get("quality_status") or "reviewed",
                        "last_signal_state": snapshot.get("last_signal_state"),
                        "source_snapshot_json": Jsonb(snapshot),
                    }
                    insert_params.update(lifecycle_params)
                    insert_params.update(user_id_params)
                    cur.execute(
                        f"""
                        INSERT INTO {table_name} (
                          principal_id,
                          principal_type,
                          asset_kind
                          {user_id_columns},
                          identity_key,
                          direction,
                          source_type,
                          source_run_id,
                          projection_run_id,
                          condition_key,
                          status,
                          quality_status,
                          last_signal_state,
                          source_snapshot_json
                          {lifecycle_columns}
                        )
                        VALUES (
                          %(principal_id)s,
                          %(principal_type)s,
                          %(asset_kind)s
                          {user_id_values},
                          %(identity_key)s,
                          %(direction)s,
                          'filter_result',
                          %(source_run_id)s,
                          %(projection_run_id)s,
                          %(condition_key)s,
                          'active',
                          %(quality_status)s,
                          %(last_signal_state)s,
                          %(source_snapshot_json)s
                          {lifecycle_values}
                        )
                        """,
                        insert_params,
                    )
                    added += 1
        return {
            "ok": True,
            "status": "completed",
            "asset_kind": asset_kind,
            "direction": direction,
            "filtered_count": int(result.get("filtered_count") or 0),
            "added_count": added,
            "skipped_count": skipped,
            "failed_count": 0,
        }

    def selected_add_app_monitor_items(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        asset_kind: str,
        direction: str,
        identity_keys: list[str],
        for_trade_date: str = "",
    ) -> dict[str, Any]:
        table_name = APP_V2_MONITOR_TABLE_BY_ASSET.get(asset_kind)
        if table_name is None or direction not in APP_V2_VALID_DIRECTIONS:
            return {"ok": False, "status": "invalid_request", "error": "invalid_monitor_request"}
        if not self._app_v2_monitor_relation_exists(table_name):
            return {"ok": False, "status": "data_not_ready", "error": "monitor_table_not_ready"}
        clean_identity_keys = list(dict.fromkeys(str(key).strip() for key in identity_keys if str(key or "").strip()))
        if not clean_identity_keys:
            return {"ok": False, "status": "invalid_request", "error": "empty_identity_keys"}

        added = 0
        skipped = 0
        failed = 0
        details: list[dict[str, Any]] = []
        for identity_key in clean_identity_keys:
            try:
                result = self.add_app_monitor_item(
                    principal_id=principal_id,
                    principal_type=principal_type,
                    user_id=user_id,
                    asset_kind=asset_kind,
                    identity_key=identity_key,
                    direction=direction,
                    source="selected_rows",
                    for_trade_date=for_trade_date,
                )
            except Exception as exc:
                failed += 1
                details.append({"identity_key": identity_key, "status": "failed", "error": type(exc).__name__})
                continue
            status = str(result.get("status") or "")
            if status == "added":
                added += int(result.get("added_count") or 1)
            elif status == "already_exists":
                skipped += int(result.get("skipped_count") or 1)
            else:
                failed += 1
            details.append({"identity_key": identity_key, "status": status or "unknown", "error": result.get("error")})
        return {
            "ok": failed == 0,
            "status": "completed",
            "asset_kind": asset_kind,
            "direction": direction,
            "requested_count": len(clean_identity_keys),
            "added_count": added,
            "skipped_count": skipped,
            "failed_count": failed,
            "items": details,
        }

    def add_app_linked_stock_monitor_items(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        parent_asset_kind: str,
        parent_identity_key: str,
        mode: str,
        stock_identity_keys: list[str],
        direction: str,
    ) -> dict[str, Any]:
        table_name = APP_V2_MONITOR_TABLE_BY_ASSET["stock"]
        if (
            parent_asset_kind not in {"index", "board"}
            or mode not in {"selected", "matched_stock_filter"}
            or direction not in APP_V2_VALID_DIRECTIONS
            or not parent_identity_key
        ):
            return {"ok": False, "status": "invalid_request", "error": "invalid_monitor_request"}
        if not self._app_v2_monitor_relation_exists(table_name):
            return {"ok": False, "status": "data_not_ready", "error": "monitor_table_not_ready"}
        result = self.fetch_app_filter_linked_stocks(
            principal_id=principal_id,
            principal_type=principal_type,
            user_id=user_id,
            membership_kind=parent_asset_kind,
            parent_identity_key=parent_identity_key,
            limit=APP_V2_FILTER_PAGE_MAX_ROWS,
            view="matched",
        )
        if not result.get("cache_ready"):
            return {"ok": False, "status": "data_not_ready", "error": "linked_stock_source_not_ready"}

        linked_rows = list(result.get("items") or [])
        selected_keys = {str(key).strip() for key in stock_identity_keys if str(key or "").strip()}
        if mode == "selected":
            if not selected_keys:
                return {"ok": False, "status": "invalid_request", "error": "empty_stock_identity_keys"}
            linked_rows = [
                row
                for row in linked_rows
                if str(row.get("stock_identity_key") or row.get("identity_key") or "").strip() in selected_keys
            ]

        added = 0
        skipped = 0
        source_type = f"{parent_asset_kind}_linked_stock"
        with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction(), conn.cursor() as cur:
                for source_row in linked_rows:
                    identity_key = str(source_row.get("stock_identity_key") or source_row.get("identity_key") or "").strip()
                    if not identity_key:
                        continue
                    snapshot = self._app_v2_monitor_snapshot(source_row, asset_kind="stock")
                    snapshot.update(
                        {
                            "source": source_type,
                            "linked_mode": mode,
                            "parent_asset_kind": parent_asset_kind,
                            "parent_identity_key": parent_identity_key,
                            "parent_code": source_row.get("parent_code"),
                            "parent_name": source_row.get("parent_name"),
                            "membership_trade_date": source_row.get("membership_trade_date"),
                            "membership_source_version": source_row.get("membership_source_version"),
                            "membership_source_batch_id": source_row.get("membership_source_batch_id"),
                            "stock_filter_source_trade_date": source_row.get("source_trade_date"),
                            "stock_filter_run_id": source_row.get("run_id") or source_row.get("source_run_id"),
                            "in_stock_filter": True,
                        }
                    )
                    existing = self._app_v2_fetch_existing_monitor(
                        cur,
                        table_name=table_name,
                        principal_id=principal_id,
                        principal_type=principal_type,
                        user_id=user_id,
                        identity_key=identity_key,
                        direction=direction,
                        valid_source_trade_date=snapshot.get("source_trade_date"),
                        valid_for_trade_date=snapshot.get("for_trade_date"),
                        valid_source_run_id=snapshot.get("source_run_id"),
                        require_matching_batch=self._app_v2_monitor_batch_identity_enabled(table_name),
                    )
                    if existing:
                        skipped += 1
                        continue
                    lifecycle_columns, lifecycle_values, lifecycle_params = self._app_v2_monitor_lifecycle_insert_parts(
                        table_name,
                        snapshot,
                    )
                    user_id_columns, user_id_values, user_id_params = self._app_v2_monitor_user_insert_parts(
                        table_name,
                        user_id,
                    )
                    insert_params = {
                        "principal_id": principal_id,
                        "principal_type": principal_type,
                        "identity_key": identity_key,
                        "direction": direction,
                        "source_type": source_type,
                        "source_run_id": snapshot.get("source_run_id"),
                        "projection_run_id": snapshot.get("projection_run_id"),
                        "condition_key": self._app_v2_monitor_condition_key(source_row),
                        "quality_status": snapshot.get("quality_status") or "reviewed",
                        "last_signal_state": snapshot.get("last_signal_state"),
                        "source_snapshot_json": Jsonb(snapshot),
                    }
                    insert_params.update(lifecycle_params)
                    insert_params.update(user_id_params)
                    cur.execute(
                        f"""
                        INSERT INTO {table_name} (
                          principal_id,
                          principal_type,
                          asset_kind
                          {user_id_columns},
                          identity_key,
                          direction,
                          source_type,
                          source_run_id,
                          projection_run_id,
                          condition_key,
                          status,
                          quality_status,
                          last_signal_state,
                          source_snapshot_json
                          {lifecycle_columns}
                        )
                        VALUES (
                          %(principal_id)s,
                          %(principal_type)s,
                          'stock'
                          {user_id_values},
                          %(identity_key)s,
                          %(direction)s,
                          %(source_type)s,
                          %(source_run_id)s,
                          %(projection_run_id)s,
                          %(condition_key)s,
                          'active',
                          %(quality_status)s,
                          %(last_signal_state)s,
                          %(source_snapshot_json)s
                          {lifecycle_values}
                        )
                        """,
                        insert_params,
                    )
                    added += 1
        return {
            "ok": True,
            "status": "completed",
            "asset_kind": "stock",
            "direction": direction,
            "parent_asset_kind": parent_asset_kind,
            "parent_identity_key": parent_identity_key,
            "mode": mode,
            "membership_count": int(result.get("membership_count") or 0),
            "candidate_count": len(linked_rows),
            "added_count": added,
            "skipped_count": skipped,
            "failed_count": 0,
        }

    def remove_app_monitor_item(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        monitor_id: int,
    ) -> dict[str, Any]:
        with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction(), conn.cursor() as cur:
                for table_name in APP_V2_MONITOR_TABLE_BY_ASSET.values():
                    if not self._app_v2_monitor_relation_exists(table_name):
                        continue
                    user_id_clause = ""
                    params = {
                        "monitor_id": monitor_id,
                        "principal_id": principal_id,
                        "principal_type": principal_type,
                    }
                    if "user_id" in self._app_v2_monitor_columns(table_name):
                        user_id_clause = "AND user_id = %(user_id)s"
                        params["user_id"] = int(user_id)
                    cur.execute(
                        f"""
                        UPDATE {table_name}
                        SET status = 'removed',
                            removed_at = now(),
                            updated_at = now()
                        WHERE monitor_id = %(monitor_id)s
                          AND principal_id = %(principal_id)s
                          AND principal_type = %(principal_type)s
                          {user_id_clause}
                          AND status <> 'removed'
                        RETURNING monitor_id
                        """,
                        params,
                    )
                    row = cur.fetchone()
                    if row:
                        return {"ok": True, "status": "removed", "monitor_id": int(row["monitor_id"])}
        return {"ok": False, "status": "not_found", "error": "monitor_not_found"}

    def add_app_realtime_scope_item(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        asset_kind: str,
        identity_key: str,
        for_trade_date: str = "",
        source: str = "single_row",
    ) -> dict[str, Any]:
        if asset_kind not in APP_V2_MONITOR_TABLE_BY_ASSET or not identity_key:
            return {"ok": False, "status": "invalid_request", "error": "invalid_realtime_scope_request"}
        if not self._app_v2_relation_exists(APP_REALTIME_SCOPE_TABLE):
            return {"ok": False, "status": "data_not_ready", "error": "realtime_scope_table_not_ready"}
        source_row = self._app_v2_fetch_filter_source_row(
            asset_kind=asset_kind,
            identity_key=identity_key,
            for_trade_date=for_trade_date,
        )
        snapshot = (
            self._app_v2_monitor_snapshot(source_row, asset_kind=asset_kind)
            if source_row is not None
            else {
                "asset_kind": asset_kind,
                "identity_key": identity_key,
                "display_name": identity_key,
                "for_trade_date": self._batch_text(for_trade_date),
            }
        )
        with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction(), conn.cursor() as cur:
                item = self._app_v2_upsert_realtime_scope_item(
                    cur,
                    principal_id=principal_id,
                    principal_type=principal_type,
                    user_id=user_id,
                    asset_kind=asset_kind,
                    identity_key=identity_key,
                    display_name=str(snapshot.get("display_name") or identity_key),
                    source_type=source,
                    source_snapshot=snapshot,
                    is_default_seed=False,
                )
        return {"ok": True, "status": "added", "added_count": 1, "skipped_count": 0, "item": item}

    def selected_add_app_realtime_scope_items(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        asset_kind: str,
        identity_keys: list[str],
        for_trade_date: str = "",
    ) -> dict[str, Any]:
        if asset_kind not in APP_V2_MONITOR_TABLE_BY_ASSET or not identity_keys:
            return {"ok": False, "status": "invalid_request", "error": "invalid_realtime_scope_request"}
        if not self._app_v2_relation_exists(APP_REALTIME_SCOPE_TABLE):
            return {"ok": False, "status": "data_not_ready", "error": "realtime_scope_table_not_ready"}
        added = 0
        with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction(), conn.cursor() as cur:
                for identity_key in identity_keys:
                    identity_key = str(identity_key or "").strip()
                    if not identity_key:
                        continue
                    source_row = self._app_v2_fetch_filter_source_row(
                        asset_kind=asset_kind,
                        identity_key=identity_key,
                        for_trade_date=for_trade_date,
                    )
                    snapshot = (
                        self._app_v2_monitor_snapshot(source_row, asset_kind=asset_kind)
                        if source_row is not None
                        else {
                            "asset_kind": asset_kind,
                            "identity_key": identity_key,
                            "display_name": identity_key,
                            "for_trade_date": self._batch_text(for_trade_date),
                        }
                    )
                    self._app_v2_upsert_realtime_scope_item(
                        cur,
                        principal_id=principal_id,
                        principal_type=principal_type,
                        user_id=user_id,
                        asset_kind=asset_kind,
                        identity_key=identity_key,
                        display_name=str(snapshot.get("display_name") or identity_key),
                        source_type="selected_rows",
                        source_snapshot=snapshot,
                        is_default_seed=False,
                    )
                    added += 1
        return {
            "ok": True,
            "status": "completed",
            "asset_kind": asset_kind,
            "requested_count": len(identity_keys),
            "added_count": added,
            "skipped_count": 0,
            "failed_count": 0,
        }

    def bulk_add_app_realtime_scope_items(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        asset_kind: str,
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        if asset_kind not in APP_V2_MONITOR_TABLE_BY_ASSET:
            return {"ok": False, "status": "invalid_request", "error": "invalid_realtime_scope_request"}
        if not self._app_v2_relation_exists(APP_REALTIME_SCOPE_TABLE):
            return {"ok": False, "status": "data_not_ready", "error": "realtime_scope_table_not_ready"}
        result = self.fetch_app_filter_items(
            principal_id=principal_id,
            principal_type=principal_type,
            user_id=user_id,
            asset_kind=asset_kind,
            filters=filters,
            limit=APP_V2_FILTER_PAGE_MAX_ROWS,
        )
        if not result.get("cache_ready"):
            return {"ok": False, "status": "data_not_ready", "error": "filter_source_not_ready"}
        added = 0
        with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction(), conn.cursor() as cur:
                for source_row in result.get("items") or []:
                    identity_key = str(source_row.get("identity_key") or "").strip()
                    if not identity_key:
                        continue
                    snapshot = self._app_v2_monitor_snapshot(source_row, asset_kind=asset_kind)
                    self._app_v2_upsert_realtime_scope_item(
                        cur,
                        principal_id=principal_id,
                        principal_type=principal_type,
                        user_id=user_id,
                        asset_kind=asset_kind,
                        identity_key=identity_key,
                        display_name=str(snapshot.get("display_name") or identity_key),
                        source_type="filter_result",
                        source_snapshot=snapshot,
                        is_default_seed=False,
                    )
                    added += 1
        return {
            "ok": True,
            "status": "completed",
            "asset_kind": asset_kind,
            "filtered_count": int(result.get("filtered_count") or 0),
            "added_count": added,
            "skipped_count": 0,
            "failed_count": 0,
        }

    def remove_app_realtime_scope_item(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        realtime_scope_id: int,
    ) -> dict[str, Any]:
        if not self._app_v2_relation_exists(APP_REALTIME_SCOPE_TABLE):
            return {"ok": False, "status": "data_not_ready", "error": "realtime_scope_table_not_ready"}
        with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE {APP_REALTIME_SCOPE_TABLE}
                    SET status = 'deleted',
                        deleted_at = now(),
                        updated_at = now()
                    WHERE realtime_scope_id = %(realtime_scope_id)s
                      AND principal_id = %(principal_id)s
                      AND principal_type = %(principal_type)s
                      AND user_id = %(user_id)s
                      AND status = 'active'
                    RETURNING realtime_scope_id
                    """,
                    {
                        "realtime_scope_id": realtime_scope_id,
                        "principal_id": principal_id,
                        "principal_type": principal_type,
                        "user_id": user_id,
                    },
                )
                row = cur.fetchone()
        if not row:
            return {"ok": False, "status": "not_found", "error": "realtime_scope_not_found"}
        return {"ok": True, "status": "deleted", "realtime_scope_id": int(row["realtime_scope_id"])}

    def _app_v2_upsert_realtime_scope_item(
        self,
        cur: Any,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        asset_kind: str,
        identity_key: str,
        display_name: str,
        source_type: str,
        source_snapshot: dict[str, Any],
        is_default_seed: bool,
    ) -> dict[str, Any]:
        cur.execute(
            f"""
            INSERT INTO {APP_REALTIME_SCOPE_TABLE} (
              principal_id,
              principal_type,
              user_id,
              asset_kind,
              identity_key,
              display_name,
              source_type,
              source_snapshot_json,
              is_default_seed,
              status,
              deleted_at
            )
            VALUES (
              %(principal_id)s,
              %(principal_type)s,
              %(user_id)s,
              %(asset_kind)s,
              %(identity_key)s,
              %(display_name)s,
              %(source_type)s,
              %(source_snapshot_json)s,
              %(is_default_seed)s,
              'active',
              NULL
            )
            ON CONFLICT (principal_id, principal_type, user_id, asset_kind, identity_key)
            DO UPDATE SET
              display_name = EXCLUDED.display_name,
              source_type = EXCLUDED.source_type,
              source_snapshot_json = EXCLUDED.source_snapshot_json,
              is_default_seed = {APP_REALTIME_SCOPE_TABLE}.is_default_seed OR EXCLUDED.is_default_seed,
              status = 'active',
              deleted_at = NULL,
              updated_at = now()
            RETURNING realtime_scope_id,
                      principal_id,
                      principal_type,
                      user_id,
                      asset_kind,
                      identity_key,
                      display_name,
                      source_type,
                      source_snapshot_json,
                      is_default_seed,
                      status,
                      deleted_at,
                      created_at,
                      updated_at
            """,
            {
                "principal_id": principal_id,
                "principal_type": principal_type,
                "user_id": user_id,
                "asset_kind": asset_kind,
                "identity_key": identity_key,
                "display_name": display_name,
                "source_type": source_type,
                "source_snapshot_json": Jsonb(source_snapshot),
                "is_default_seed": is_default_seed,
            },
        )
        return dict(cur.fetchone())

    def _app_v2_relation_exists(self, relation_name: str) -> bool:
        allowed_relations = {
            "v_n6_stock_condition_display_basis",
            "v_n6_index_condition_display_basis",
            "v_n6_board_condition_display_basis",
            "n6_index_membership_display_cache",
            "n6_board_membership_display_cache",
            "v_n6_index_membership_fact",
            "v_n6_board_membership_fact",
            APP_REALTIME_SCOPE_TABLE,
        }
        if relation_name not in allowed_relations:
            return False
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s) AS relation_name", (relation_name,))
            row = cur.fetchone()
        return bool(row and row.get("relation_name"))

    def _app_v2_default_realtime_scope_items(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
    ) -> list[dict[str, Any]]:
        return [
            {
                "realtime_scope_id": None,
                "principal_id": principal_id,
                "principal_type": principal_type,
                "user_id": user_id,
                "asset_kind": str(item["asset_kind"]),
                "identity_key": str(item["identity_key"]),
                "display_name": str(item["display_name"]),
                "source_type": "default_seed",
                "source_snapshot_json": {
                    "asset_kind": str(item["asset_kind"]),
                    "identity_key": str(item["identity_key"]),
                    "display_name": str(item["display_name"]),
                    "seed_policy": "n6_default_realtime_monitor_scope_v1",
                },
                "is_default_seed": True,
                "status": "active",
                "deleted_at": None,
                "created_at": None,
                "updated_at": None,
            }
            for item in DEFAULT_REALTIME_SCOPE_INDEXES
        ]

    def _app_v2_merge_realtime_scope_defaults(
        self,
        rows: list[dict[str, Any]],
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
    ) -> list[dict[str, Any]]:
        deleted_keys = {
            (str(row.get("asset_kind") or ""), str(row.get("identity_key") or ""))
            for row in rows
            if str(row.get("status") or "") == "deleted"
        }
        active_rows: list[dict[str, Any]] = []
        active_keys: set[tuple[str, str]] = set()
        for row in rows:
            if str(row.get("status") or "") != "active":
                continue
            key = (str(row.get("asset_kind") or ""), str(row.get("identity_key") or ""))
            if key in active_keys:
                continue
            active_rows.append(dict(row))
            active_keys.add(key)
        defaults = []
        for row in self._app_v2_default_realtime_scope_items(
            principal_id=principal_id,
            principal_type=principal_type,
            user_id=user_id,
        ):
            key = (str(row.get("asset_kind") or ""), str(row.get("identity_key") or ""))
            if key in deleted_keys or key in active_keys:
                continue
            defaults.append(row)
        return active_rows + defaults

    def _app_v2_filter_columns(self, table_name: str) -> set[str]:
        allowed_relations = {
            "v_n6_stock_condition_display_basis",
            "v_n6_index_condition_display_basis",
            "v_n6_board_condition_display_basis",
        }
        if table_name not in allowed_relations:
            return set()
        cached = self._app_v2_filter_column_cache.get(table_name)
        if cached is not None:
            return set(cached)
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = %s
                """,
                (table_name,),
            )
            columns = {
                str(row.get("column_name") or "").strip()
                for row in cur.fetchall()
                if str(row.get("column_name") or "").strip()
            }
        self._app_v2_filter_column_cache[table_name] = set(columns)
        return columns

    def _app_v2_filter_order_sql(self, table_name: str, filters: dict[str, Any]) -> str:
        default_order = "t.updated_at DESC NULLS LAST, t.identity_key ASC"
        sort_key = normalize_filter_value(filters.get("sort"))
        if not sort_key or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", sort_key):
            return default_order
        if sort_key not in self._app_v2_filter_columns(table_name):
            return default_order
        sort_dir = str(filters.get("sort_dir") or "asc").strip().lower()
        direction = "DESC" if sort_dir == "desc" else "ASC"
        return f't."{sort_key}" {direction} NULLS LAST, t.identity_key ASC'

    def _app_v2_monitor_relation_exists(self, relation_name: str) -> bool:
        if relation_name not in set(APP_V2_MONITOR_TABLE_BY_ASSET.values()):
            return False
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s) AS relation_name", (relation_name,))
            row = cur.fetchone()
        return bool(row and row.get("relation_name"))

    def _app_v2_monitor_lifecycle_insert_parts(
        self,
        table_name: str,
        snapshot: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]]:
        columns = self._app_v2_monitor_columns(table_name)
        mapping = (
            ("valid_source_trade_date", "source_trade_date"),
            ("valid_for_trade_date", "for_trade_date"),
            ("valid_source_run_id", "source_run_id"),
        )
        insert_columns: list[str] = []
        value_placeholders: list[str] = []
        params: dict[str, Any] = {}
        for column_name, snapshot_key in mapping:
            if column_name not in columns:
                continue
            param_name = f"insert_{column_name}"
            insert_columns.append(f",\n                      {column_name}")
            value_placeholders.append(f",\n                      %({param_name})s")
            params[param_name] = snapshot.get(snapshot_key)
        return "".join(insert_columns), "".join(value_placeholders), params

    def _app_v2_monitor_batch_identity_enabled(self, table_name: str) -> bool:
        columns = self._app_v2_monitor_columns(table_name)
        return {
            "valid_source_trade_date",
            "valid_for_trade_date",
            "valid_source_run_id",
        }.issubset(columns)

    def _app_v2_monitor_user_insert_parts(self, table_name: str, user_id: int) -> tuple[str, str, dict[str, Any]]:
        if "user_id" not in self._app_v2_monitor_columns(table_name):
            return "", "", {}
        return ",\n                      user_id", ",\n                      %(insert_user_id)s", {"insert_user_id": int(user_id)}

    def _app_v2_fetch_filter_source_row(
        self,
        *,
        asset_kind: str,
        identity_key: str,
        for_trade_date: str = "",
    ) -> dict[str, Any] | None:
        table_name = {
            "stock": "v_n6_stock_condition_display_basis",
            "index": "v_n6_index_condition_display_basis",
            "board": "v_n6_board_condition_display_basis",
        }.get(asset_kind)
        if table_name is None or not self._app_v2_relation_exists(table_name):
            return None
        selected_for_trade_date = self._batch_text(for_trade_date)
        date_filter_sql = ""
        params: dict[str, Any] = {"identity_key": identity_key}
        if selected_for_trade_date:
            date_filter_sql = "AND t.for_trade_date::text = %(for_trade_date)s"
            params["for_trade_date"] = selected_for_trade_date
        with self._readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT t.*
                FROM {table_name} t
                WHERE t.identity_key = %(identity_key)s
                  {date_filter_sql}
                  AND t.source_trade_date = (
                    SELECT max(source_trade_date)
                    FROM {table_name}
                    WHERE identity_key = %(identity_key)s
                      {date_filter_sql.replace("t.", "")}
                  )
                ORDER BY t.updated_at DESC NULLS LAST, t.identity_key ASC
                LIMIT 1
                """,
                params,
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def _app_v2_fetch_existing_monitor(
        self,
        cur: Any,
        *,
        table_name: str,
        principal_id: int,
        principal_type: str,
        identity_key: str,
        direction: str,
        user_id: int = 0,
        valid_source_trade_date: Any = None,
        valid_for_trade_date: Any = None,
        valid_source_run_id: Any = None,
        require_matching_batch: bool = True,
    ) -> dict[str, Any] | None:
        columns = self._app_v2_monitor_columns(table_name)
        valid_source_trade_expr = (
            "COALESCE(valid_source_trade_date, source_snapshot_json->>'source_trade_date')"
            if "valid_source_trade_date" in columns
            else "source_snapshot_json->>'source_trade_date'"
        )
        valid_for_trade_expr = (
            "COALESCE(valid_for_trade_date, source_snapshot_json->>'for_trade_date')"
            if "valid_for_trade_date" in columns
            else "source_snapshot_json->>'for_trade_date'"
        )
        valid_run_expr = (
            "COALESCE(valid_source_run_id, source_snapshot_json->>'source_run_id')"
            if "valid_source_run_id" in columns
            else "source_snapshot_json->>'source_run_id'"
        )
        params: dict[str, Any] = {
            "principal_id": principal_id,
            "principal_type": principal_type,
            "identity_key": identity_key,
            "direction": direction,
        }
        user_filter_sql = ""
        if "user_id" in columns:
            user_filter_sql = "AND user_id = %(user_id)s"
            params["user_id"] = int(user_id)
        batch_filters: list[str] = []
        valid_source_trade_date_text = self._batch_text(valid_source_trade_date)
        valid_for_trade_date_text = self._batch_text(valid_for_trade_date)
        valid_source_run_id_text = self._batch_text(valid_source_run_id)
        if require_matching_batch and valid_source_trade_date_text:
            params["valid_source_trade_date"] = valid_source_trade_date_text
            batch_filters.append(f"{valid_source_trade_expr} = %(valid_source_trade_date)s")
        if require_matching_batch and valid_for_trade_date_text:
            params["valid_for_trade_date"] = valid_for_trade_date_text
            batch_filters.append(f"{valid_for_trade_expr} = %(valid_for_trade_date)s")
        if require_matching_batch and valid_source_run_id_text:
            params["valid_source_run_id"] = valid_source_run_id_text
            batch_filters.append(f"{valid_run_expr} = %(valid_source_run_id)s")
        batch_filter_sql = ""
        if batch_filters:
            batch_filter_sql = "\n              AND " + "\n              AND ".join(batch_filters)
        cur.execute(
            f"""
            SELECT monitor_id,
                   principal_id,
                   principal_type,
                   asset_kind,
                   identity_key,
                   direction,
                   source_type AS source,
                   status,
                   quality_status,
                   last_signal_state,
                   {valid_source_trade_expr} AS valid_source_trade_date,
                   {valid_for_trade_expr} AS valid_for_trade_date,
                   {valid_run_expr} AS valid_source_run_id,
                   source_snapshot_json->>'display_name' AS display_name,
                   source_snapshot_json->>'display_code' AS display_code,
                   created_at,
                   updated_at
            FROM {table_name}
            WHERE principal_id = %(principal_id)s
              AND principal_type = %(principal_type)s
              {user_filter_sql}
              AND identity_key = %(identity_key)s
              AND direction = %(direction)s
              AND status <> 'removed'
              {batch_filter_sql}
            LIMIT 1
            """,
            params,
        )
        row = cur.fetchone()
        if not row:
            return None
        existing = dict(row)
        requested_batch = {
            "source_trade_date": valid_source_trade_date_text,
            "for_trade_date": valid_for_trade_date_text,
            "source_run_id": valid_source_run_id_text,
        }
        if require_matching_batch and any(requested_batch.values()):
            existing_batch = {
                "source_trade_date": self._batch_text(existing.get("valid_source_trade_date")),
                "for_trade_date": self._batch_text(existing.get("valid_for_trade_date")),
                "source_run_id": self._batch_text(existing.get("valid_source_run_id")),
            }
            if existing_batch != requested_batch:
                return None
        return existing

    def _app_v2_monitor_condition_key(self, row: dict[str, Any]) -> str | None:
        value = row.get("condition_key")
        if value is not None and str(value).strip():
            return str(value)
        keys = row.get("selected_condition_keys")
        if isinstance(keys, (list, tuple)):
            return ",".join(str(item) for item in keys if str(item or "").strip()) or None
        if keys is not None and str(keys).strip():
            return str(keys)
        return None

    def _app_v2_monitor_snapshot(self, row: dict[str, Any], *, asset_kind: str) -> dict[str, Any]:
        return {
            "asset_kind": asset_kind,
            "identity_key": row.get("identity_key"),
            "display_name": row.get("display_name") or row.get("name") or row.get("board_name"),
            "display_code": row.get("display_code") or row.get("code") or row.get("board_code"),
            "display_title": row.get("display_title"),
            "condition_key": self._app_v2_monitor_condition_key(row),
            "source_run_id": row.get("source_run_id") or row.get("run_id"),
            "source_display_basis_id": (
                row.get("source_display_basis_id")
                or row.get("stock_condition_display_basis_id")
                or row.get("index_condition_display_basis_id")
                or row.get("board_condition_display_basis_id")
            ),
            "source_trade_date": row.get("source_trade_date"),
            "for_trade_date": row.get("for_trade_date"),
            "projection_run_id": row.get("projection_run_id"),
            "quality_status": row.get("quality_status"),
            "last_signal_state": row.get("last_signal_state"),
            "period_grade_y": row.get("period_grade_y") or row.get("year_overheat_level"),
            "period_grade_q": row.get("period_grade_q") or row.get("quarter_overheat_level"),
            "period_grade_m": row.get("period_grade_m") or row.get("month_overheat_level"),
            "period_grade_w": row.get("period_grade_w") or row.get("week_overheat_level"),
            "period_grade_d": row.get("period_grade_d") or row.get("day_overheat_level"),
        }

    def _app_v2_filter_where(self, filters: dict[str, Any], *, asset_kind: str) -> tuple[str, dict[str, Any]]:
        where_clauses = ["TRUE"]
        params: dict[str, Any] = {}
        direct_filters = {
            "asset_kind": "asset_kind",
            "quality_status": "quality_status",
            "source_run_id": "run_id",
        }
        if asset_kind == "board":
            direct_filters["board_type"] = "board_type"
        for key, column in direct_filters.items():
            value = normalize_filter_value(filters.get(key))
            if value:
                params[key] = value
                where_clauses.append(f"{column} = %({key})s")
        direction = normalize_filter_value(filters.get("direction"))
        if direction:
            params["direction"] = direction
            where_clauses.append("%(direction)s = ANY(selected_directions)")
        condition_key = normalize_filter_value(filters.get("condition_key"))
        if condition_key:
            params["condition_key"] = condition_key
            where_clauses.append("%(condition_key)s = ANY(selected_condition_keys)")
        period_filters = {
            "year_overheat_level": "period_grade_y",
            "quarter_overheat_level": "period_grade_q",
            "month_overheat_level": "period_grade_m",
            "week_overheat_level": "period_grade_w",
            "day_overheat_level": "period_grade_d",
        }
        for key, expression in period_filters.items():
            values = normalize_filter_values(filters.get(key))
            if len(values) == 1:
                params[key] = values[0]
                where_clauses.append(f"{expression} = %({key})s")
            elif values:
                params[key] = values
                where_clauses.append(f"{expression} = ANY(%({key})s)")
        keyword = normalize_filter_value(filters.get("q"))
        if keyword:
            params["q_like"] = f"%{keyword}%"
            where_clauses.append("(code ILIKE %(q_like)s OR name ILIKE %(q_like)s OR identity_key ILIKE %(q_like)s)")
        expected_return_min = app_v2_expected_return_threshold(filters.get("buy_expected_return_pct_min"))
        if expected_return_min is not None:
            params["buy_expected_return_pct_min"] = expected_return_min
            where_clauses.append("buy_expected_return_pct >= %(buy_expected_return_pct_min)s")
        return " AND ".join(where_clauses), params

    def _ui_v1_signal_select_list(self) -> str:
        actual_trigger_period_expr = self._ui_v1_actual_trigger_period_expr()
        return f"""
               p.user_signal_projection_id,
               c.user_signal_card_id,
               q.user_notification_queue_id,
               p.user_projection_run_id,
               {self._ui_v1_event_type_expr()} AS event_type,
               {self._ui_v1_trade_date_expr()} AS trade_date,
               {self._ui_v1_event_time_expr()} AS event_time,
               p.asset_kind,
               p.identity_key,
               p.code,
               p.name,
               p.direction,
               p.signal_type,
               {self._ui_v1_action_state_expr()} AS action_state,
               COALESCE(NULLIF(p.action_mark, ''), NULLIF(c.action_mark, ''), NULLIF(q.action_mark, ''), '—') AS action_mark,
               c.card_status,
               {self._ui_v1_blocked_reason_expr()} AS blocked_reason,
               COALESCE(e.payload_json->>'trigger_kind', p.source_payload_json->'payload_json'->>'trigger_kind', c.card_payload_json->>'trigger_kind', p.display_payload_json->>'trigger_kind', p.trace_json->>'trigger_kind', p.source_payload_json->>'trigger_kind') AS trigger_kind,
               COALESCE(NULLIF(p.condition_key, ''), NULLIF(c.condition_key, ''), NULLIF(q.condition_key, ''), p.display_payload_json->>'condition_key', p.trace_json->>'condition_key') AS condition_key,
               COALESCE(NULLIF(p.original_condition_key, ''), NULLIF(c.original_condition_key, ''), NULLIF(q.original_condition_key, ''), p.display_payload_json->>'original_condition_key', p.trace_json->>'original_condition_key') AS original_condition_key,
               {actual_trigger_period_expr} AS primary_trigger_period,
               COALESCE(p.trace_json->>'trigger_time', p.source_payload_json->>'event_time', p.created_at::text) AS trigger_time,
               q.queue_status,
               CASE
                 WHEN q.queue_status = 'ready_for_future_push' THEN 'preview'
                 WHEN q.queue_status = 'queued_only' THEN 'not_delivered'
                 ELSE COALESCE(q.queue_status, 'not_delivered')
               END AS delivery_status,
               q.notification_source,
               q.channel,
               q.title,
               q.message,
               q.notification_payload_json,
               p.source_action_run_id,
               p.source_event_id,
               COALESCE(NULLIF(p.source_action_event_id, ''), NULLIF(c.source_action_event_id, ''), NULLIF(q.source_action_event_id, ''), e.event_id) AS source_action_event_id,
               {self._ui_v1_event_type_expr()} AS source_action_event_type,
               COALESCE(e.payload_json->>'source_trigger_run_id', c.card_payload_json->>'source_n4_run_id', p.trace_json->>'source_n4_run_id', p.source_payload_json->>'source_n4_run_id', p.trace_json->>'source_trigger_run_id') AS source_n4_run_id,
               COALESCE(e.payload_json->>'source_trigger_event_id', p.source_payload_json->'payload_json'->>'source_trigger_event_id', p.trace_json#>>'{{condition_provenance,source_trigger_event_ids,0}}') AS n4_trigger_event_id,
               COALESCE(e.payload_json->>'confirmation_status', p.source_payload_json->'payload_json'->>'confirmation_status', p.trace_json->>'confirmation_status', p.action_state, c.action_state) AS source_action_status,
               {self._ui_v1_trigger_price_expr()} AS trigger_price,
               {self._ui_v1_triggered_periods_expr(actual_trigger_period_expr)} AS triggered_periods,
               {self._ui_v1_baseline_source_expr(actual_trigger_period_expr)} AS baseline_source,
               COALESCE(c.target_price, p.target_price) AS target_price,
               COALESCE(c.current_price, p.current_price) AS current_price,
               COALESCE(c.expected_return_pct, p.expected_return_pct) AS expected_return_pct,
               COALESCE(c.board_code, p.board_code) AS board_code,
               COALESCE(c.board_name, p.board_name) AS board_name,
               c.card_payload_json,
               p.display_payload_json,
               true AS rollback_safe,
               p.created_at
        """

    def _ui_v1_signal_from_sql(self) -> str:
        return """
                FROM user_signal_projection p
                LEFT JOIN common_event_outbox e
                  ON e.event_id = p.source_event_id
                LEFT JOIN user_signal_card c
                  ON c.user_signal_projection_id = p.user_signal_projection_id
                 AND c.user_id = p.user_id
                LEFT JOIN LATERAL (
                  SELECT q.user_notification_queue_id,
                         q.notification_source,
                         q.queue_status,
                         q.channel,
                         q.title,
                         q.message,
                         q.notification_payload_json,
                         q.source_action_event_id,
                         q.source_action_event_type,
                         q.action_state,
                         q.action_mark,
                         q.condition_key,
                         q.original_condition_key
                  FROM user_notification_queue q
                  WHERE q.user_signal_projection_id = p.user_signal_projection_id
                    AND q.user_id = p.user_id
                  ORDER BY
                    CASE WHEN q.queue_status = 'queued_only' THEN 0 ELSE 1 END,
                    q.created_at DESC,
                    q.user_notification_queue_id DESC
                  LIMIT 1
                ) q ON true
        """

    def _ui_v1_signal_where(self, user_id: int, filters: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        params: dict[str, Any] = {
            "user_id": user_id,
            "stale_source_action_run_ids": list(stale_source_action_run_ids()),
        }
        where_clauses = [
            "p.user_id = %(user_id)s",
            """
            (
              p.source_action_run_id IS NULL
              OR NOT (p.source_action_run_id = ANY(%(stale_source_action_run_ids)s))
            )
            """,
            """
            p.user_projection_run_id = (
              SELECT upr.user_projection_run_id
              FROM user_projection_run upr
              WHERE upr.status = 'passed'
              ORDER BY COALESCE(upr.finished_at, upr.updated_at, upr.created_at) DESC,
                       upr.user_projection_run_id DESC
              LIMIT 1
            )
            """,
        ]
        filter_specs = (
            ("trade_date", self._ui_v1_trade_date_expr()),
            ("event_type", self._ui_v1_event_type_expr()),
            ("asset_kind", "p.asset_kind"),
            ("direction", "p.direction"),
            ("signal_type", "p.signal_type"),
            ("action_state", self._ui_v1_action_state_expr()),
            ("blocked_reason", self._ui_v1_blocked_reason_expr()),
        )
        for key, expression in filter_specs:
            value = normalize_filter_value(filters.get(key))
            if value:
                params[key] = value
                where_clauses.append(f"{expression} = %({key})s")

        time_field = normalize_time_field(filters.get("time_field"))
        time_expression = "p.created_at" if time_field == "created_at" else f"({self._ui_v1_event_time_expr()})::timestamptz"
        date_from = normalize_filter_value(filters.get("date_from"))
        if date_from:
            params["date_from"] = date_from
            where_clauses.append(f"(({time_expression}) AT TIME ZONE 'Asia/Shanghai')::date >= %(date_from)s::date")
        date_to = normalize_filter_value(filters.get("date_to"))
        if date_to:
            params["date_to"] = date_to
            where_clauses.append(f"(({time_expression}) AT TIME ZONE 'Asia/Shanghai')::date <= %(date_to)s::date")

        keyword = normalize_filter_value(filters.get("q"))
        if keyword:
            params["q_like"] = f"%{keyword}%"
            condition_expr = "COALESCE(NULLIF(p.condition_key, ''), NULLIF(c.condition_key, ''), NULLIF(q.condition_key, ''), p.display_payload_json->>'condition_key', p.trace_json->>'condition_key')"
            where_clauses.append(
                f"""
                (
                  p.code ILIKE %(q_like)s
                  OR p.name ILIKE %(q_like)s
                  OR p.identity_key ILIKE %(q_like)s
                  OR p.source_event_id ILIKE %(q_like)s
                  OR p.source_action_event_id ILIKE %(q_like)s
                  OR {condition_expr} ILIKE %(q_like)s
                )
                """
            )
        return "\n                  AND ".join(where_clauses), params

    def _ui_v1_trade_date_expr(self) -> str:
        return "COALESCE(p.display_payload_json->>'trade_date', p.source_payload_json->>'trade_date', c.card_payload_json->>'trade_date', p.trace_json->>'trade_date')"

    def _ui_v1_event_type_expr(self) -> str:
        return "COALESCE(NULLIF(e.event_type, ''), NULLIF(p.source_action_event_type, ''), NULLIF(c.source_action_event_type, ''), NULLIF(q.source_action_event_type, ''), p.source_event_type)"

    def _ui_v1_event_time_expr(self) -> str:
        return "COALESCE(e.payload_json->>'event_time', p.source_payload_json->>'event_time', p.source_payload_json->'payload_json'->>'event_time', p.trace_json->>'event_time', p.display_payload_json->>'event_time', c.card_payload_json->>'event_time', p.created_at::text)"

    def _ui_v1_action_state_expr(self) -> str:
        return """
            COALESCE(
              NULLIF(p.action_state, ''),
              NULLIF(c.action_state, ''),
              NULLIF(q.action_state, ''),
              CASE
                WHEN p.source_action_event_type = 'ActionBlocked' THEN 'blocked'
                WHEN p.source_action_event_type = 'ActionExecuted' THEN 'executed'
                WHEN p.source_action_event_type = 'ActionEligible' THEN 'eligible'
                WHEN p.source_action_event_type = 'ActionSkipped' THEN 'skipped'
                ELSE NULL
              END,
              p.projection_status,
              c.card_status
            )
        """

    def _ui_v1_blocked_reason_expr(self) -> str:
        return "COALESCE(e.payload_json->>'blocked_reason', c.card_payload_json->>'blocked_reason', p.display_payload_json->>'blocked_reason', p.source_payload_json->'payload_json'->>'blocked_reason', p.trace_json->>'blocked_reason', p.source_payload_json->>'blocked_reason')"

    def _ui_v1_actual_trigger_period_expr(self) -> str:
        return """
            COALESCE(
              e.payload_json->>'primary_trigger_period',
              e.payload_json->>'trigger_period',
              p.source_payload_json->'payload_json'->>'primary_trigger_period',
              p.source_payload_json->'payload_json'->>'trigger_period',
              c.card_payload_json->>'primary_trigger_period',
              c.card_payload_json->>'trigger_period',
              p.display_payload_json->>'primary_trigger_period'
            )
        """

    def _ui_v1_trigger_price_expr(self) -> str:
        return """
            COALESCE(
              e.payload_json->>'trigger_price',
              p.source_payload_json->'payload_json'->>'trigger_price',
              p.source_payload_json->'payload_json'->'trace_json'->>'trigger_price',
              p.trace_json->>'trigger_price',
              c.card_payload_json->>'trigger_price'
            )
        """

    def _ui_v1_triggered_periods_expr(self, actual_trigger_period_expr: str) -> str:
        return f"""
            COALESCE(
              e.payload_json->>'all_trigger_periods',
              p.source_payload_json->'payload_json'->>'all_trigger_periods',
              p.source_payload_json->'payload_json'->'trace_json'->>'all_trigger_periods',
              p.trace_json->>'all_trigger_periods',
              c.card_payload_json->>'all_trigger_periods',
              e.payload_json->>'triggered_periods',
              p.source_payload_json->'payload_json'->>'triggered_periods',
              p.source_payload_json->'payload_json'->'trace_json'->>'triggered_periods',
              p.trace_json->>'triggered_periods',
              c.card_payload_json->>'triggered_periods',
              CASE
                WHEN {actual_trigger_period_expr} IS NOT NULL
                THEN jsonb_build_array({actual_trigger_period_expr})::text
                ELSE NULL
              END
            )
        """

    def _ui_v1_baseline_source_expr(self, actual_trigger_period_expr: str) -> str:
        period_baseline_cases = "\n".join(
            f"""
              WHEN '{period}' THEN COALESCE(
                e.payload_json#>>'{{period_trigger_baseline_trace,traced_periods,{period},baseline_source}}',
                e.payload_json#>>'{{trace_json,period_trigger_baseline_trace,traced_periods,{period},baseline_source}}',
                e.payload_json#>>'{{source_market_trace,period_trigger_baseline_trace,traced_periods,{period},baseline_source}}',
                p.source_payload_json#>>'{{payload_json,period_trigger_baseline_trace,traced_periods,{period},baseline_source}}',
                p.source_payload_json#>>'{{payload_json,trace_json,period_trigger_baseline_trace,traced_periods,{period},baseline_source}}',
                p.source_payload_json#>>'{{payload_json,source_market_trace,period_trigger_baseline_trace,traced_periods,{period},baseline_source}}',
                p.trace_json#>>'{{period_trigger_baseline_trace,traced_periods,{period},baseline_source}}',
                c.card_payload_json#>>'{{period_trigger_baseline_trace,traced_periods,{period},baseline_source}}'
              )
            """
            for period in ("Y", "Q", "M", "W", "D", "30m", "120m", "5m", "1m")
        )
        return f"""
            COALESCE(
              e.payload_json->>'baseline_source',
              p.source_payload_json->'payload_json'->>'baseline_source',
              p.source_payload_json->'payload_json'->'trace_json'->>'baseline_source',
              p.trace_json->>'baseline_source',
              c.card_payload_json->>'baseline_source',
              CASE {actual_trigger_period_expr}
                {period_baseline_cases}
                ELSE NULL
              END
            )
        """

    def fetch_index_board_c1_minute_rows(self, trade_date: str) -> dict[str, list[dict[str, Any]]]:
        normalized_trade_date = str(trade_date or "").replace("-", "")
        output: dict[str, list[dict[str, Any]]] = {"index": [], "board": []}
        with self._readonly_connection() as conn, conn.cursor() as cur:
            for asset_kind, table_name, identity_column in (
                ("index", "index_minute_bar_1m", "index_identity_key"),
                ("board", "board_minute_bar_1m", "board_identity_key"),
            ):
                cur.execute(
                    f"""
                    SELECT
                      %s AS asset_kind,
                      {identity_column} AS identity_key,
                      exchange,
                      code,
                      COALESCE(display_code, code) AS display_code,
                      bar_id,
                      bar_time,
                      open,
                      high,
                      low,
                      close,
                      volume,
                      amount,
                      quality_status,
                      trade_date
                    FROM {table_name}
                    WHERE trade_date = %s
                    ORDER BY identity_key, bar_time
                    """,
                    (asset_kind, normalized_trade_date),
                )
                output[asset_kind] = [dict(row) for row in cur.fetchall()]
        return output

    def _readonly_connection(self) -> psycopg.Connection[Any]:
        return psycopg.connect(
            self.dsn,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        )


class SignalBoundVirtualBuyExecutionRepository:
    def __init__(self, delegate: Any, signal: dict[str, Any]) -> None:
        self.delegate = delegate
        self.signal = signal

    def fetch_signal_for_buy(
        self,
        user_signal_projection_id: int,
        principal_id: int,
        principal_type: str,
    ) -> dict[str, Any] | None:
        if int(self.signal.get("user_signal_projection_id") or 0) != int(user_signal_projection_id):
            return None
        scoped_signal = dict(self.signal)
        scoped_signal["principal_id"] = int(principal_id)
        scoped_signal["principal_type"] = str(principal_type)
        return scoped_signal

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)


class PostgresVirtualBuyExecutionRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @contextmanager
    def transaction(self) -> Any:
        with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction(), conn.cursor() as cur:
                yield _PostgresVirtualBuyExecutionCursorRepository(cur)


class _PostgresVirtualBuyExecutionCursorRepository:
    def __init__(self, cur: Any) -> None:
        self.cur = cur
        self._active_account_scope_by_id: dict[int, tuple[int, str]] = {}

    def fetch_signal_for_buy(
        self,
        user_signal_projection_id: int,
        principal_id: int,
        principal_type: str,
    ) -> dict[str, Any] | None:
        return None

    def fetch_active_virtual_account(self, principal_id: int, principal_type: str) -> dict[str, Any] | None:
        self.cur.execute(
            """
            SELECT virtual_account_id, principal_id, principal_type, virtual_account_status
            FROM n6_virtual_account
            WHERE principal_id = %s
              AND principal_type = %s
              AND virtual_account_status = 'active'
            ORDER BY virtual_account_id DESC
            LIMIT 1
            """,
            (principal_id, principal_type),
        )
        row = self.cur.fetchone()
        if not row:
            return None
        result = dict(row)
        self._active_account_scope_by_id[int(result["virtual_account_id"])] = (
            int(result["principal_id"]),
            str(result["principal_type"]),
        )
        return result

    def fetch_current_cash_snapshot(self, virtual_account_id: int) -> dict[str, Any] | None:
        self.cur.execute(
            "SELECT pg_advisory_xact_lock(%s::bigint)",
            (int(virtual_account_id),),
        )
        self.cur.execute(
            """
            SELECT cash_snapshot_id,
                   virtual_account_id,
                   available_cash,
                   frozen_cash,
                   total_cash,
                   source_ledger_max_id
            FROM n6_virtual_cash_snapshot
            WHERE virtual_account_id = %s
              AND snapshot_status = 'active'
            ORDER BY snapshot_time DESC, cash_snapshot_id DESC
            LIMIT 1
            """,
            (virtual_account_id,),
        )
        row = self.cur.fetchone()
        return dict(row) if row else None

    def fetch_position_for_update(
        self,
        virtual_account_id: int,
        asset_kind: str,
        identity_key: str,
    ) -> dict[str, Any] | None:
        self.cur.execute(
            """
            SELECT virtual_position_id,
                   virtual_account_id,
                   principal_id,
                   principal_type,
                   asset_kind,
                   identity_key,
                   position_status,
                   quantity,
                   available_quantity,
                   locked_quantity,
                   average_cost,
                   market_value,
                   unrealized_pnl,
                   last_virtual_trade_id
            FROM n6_virtual_position
            WHERE virtual_account_id = %s
              AND asset_kind = %s
              AND identity_key = %s
              AND position_status = 'open_virtual'
            FOR UPDATE
            """,
            (virtual_account_id, asset_kind, identity_key),
        )
        row = self.cur.fetchone()
        return dict(row) if row else None

    def insert_virtual_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        existing = self._fetch_order_by_idempotency(payload)
        if existing:
            return {"duplicate": True, "existing": existing}
        params = dict(payload)
        params["source_lineage_json"] = Jsonb(payload.get("source_lineage_json") or {})
        params["source_json"] = Jsonb(payload.get("source_json") or {})
        self.cur.execute(
            """
            INSERT INTO n6_virtual_order (
              virtual_account_id,
              principal_id,
              principal_type,
              asset_kind,
              identity_key,
              signal_type,
              order_side,
              order_type,
              order_status,
              requested_quantity,
              requested_price,
              estimated_fee_amount,
              estimated_tax_amount,
              fee_policy_version,
              tax_policy_version,
              execution_policy_version,
              execution_policy_hash,
              market_rule_set,
              source_action_event_id,
              source_signal_projection_id,
              run_id,
              policy_version,
              policy_hash,
              rollback_scope,
              source_lineage_json,
              quality_status,
              idempotency_key,
              source_message_key,
              source_signal_identity_key,
              source_condition_key,
              source_event_time,
              source_for_trade_date,
              source_trade_date,
              source_monitor_id,
              source_strategy_id,
              source_action_state,
              source_blocked_reason,
              source_json
            )
            VALUES (
              %(virtual_account_id)s,
              %(principal_id)s,
              %(principal_type)s,
              %(asset_kind)s,
              %(identity_key)s,
              %(signal_type)s,
              %(order_side)s,
              %(order_type)s,
              %(order_status)s,
              %(requested_quantity)s,
              %(requested_price)s,
              %(estimated_fee_amount)s,
              %(estimated_tax_amount)s,
              %(fee_policy_version)s,
              %(tax_policy_version)s,
              %(execution_policy_version)s,
              %(execution_policy_hash)s,
              %(market_rule_set)s,
              %(source_action_event_id)s,
              %(source_signal_projection_id)s,
              %(run_id)s,
              %(policy_version)s,
              %(policy_hash)s,
              %(rollback_scope)s,
              %(source_lineage_json)s,
              %(quality_status)s,
              %(idempotency_key)s,
              %(source_message_key)s,
              %(source_signal_identity_key)s,
              %(source_condition_key)s,
              %(source_event_time)s,
              %(source_for_trade_date)s,
              %(source_trade_date)s,
              %(source_monitor_id)s,
              %(source_strategy_id)s,
              %(source_action_state)s,
              %(source_blocked_reason)s,
              %(source_json)s
            )
            ON CONFLICT DO NOTHING
            RETURNING virtual_order_id
            """,
            params,
        )
        row = self.cur.fetchone()
        if row:
            return {"virtual_order_id": int(row["virtual_order_id"])}
        existing = self._fetch_order_by_idempotency(payload)
        if existing:
            return {"duplicate": True, "existing": existing}
        raise RuntimeError("virtual_order_insert_failed")

    def insert_virtual_trade(self, payload: dict[str, Any]) -> dict[str, Any]:
        params = dict(payload)
        params["source_lineage_json"] = Jsonb(payload.get("source_lineage_json") or {})
        self.cur.execute(
            """
            INSERT INTO n6_virtual_trade (
              virtual_order_id,
              virtual_account_id,
              principal_id,
              principal_type,
              asset_kind,
              identity_key,
              trade_side,
              filled_quantity,
              filled_price,
              gross_amount,
              commission_amount,
              stamp_tax_amount,
              transfer_fee_amount,
              total_fee_amount,
              net_amount,
              fill_policy_version,
              fill_policy_hash,
              replay_deterministic_seed,
              trade_status,
              trade_time,
              source_lineage_json,
              run_id,
              policy_version,
              policy_hash,
              rollback_scope,
              quality_status
            )
            VALUES (
              %(virtual_order_id)s,
              %(virtual_account_id)s,
              %(principal_id)s,
              %(principal_type)s,
              %(asset_kind)s,
              %(identity_key)s,
              %(trade_side)s,
              %(filled_quantity)s,
              %(filled_price)s,
              %(gross_amount)s,
              %(commission_amount)s,
              %(stamp_tax_amount)s,
              %(transfer_fee_amount)s,
              %(total_fee_amount)s,
              %(net_amount)s,
              %(fill_policy_version)s,
              %(fill_policy_hash)s,
              %(replay_deterministic_seed)s,
              %(trade_status)s,
              %(trade_time)s,
              %(source_lineage_json)s,
              %(run_id)s,
              %(policy_version)s,
              %(policy_hash)s,
              %(rollback_scope)s,
              %(quality_status)s
            )
            RETURNING virtual_trade_id
            """,
            params,
        )
        row = self.cur.fetchone()
        return {"virtual_trade_id": int(row["virtual_trade_id"])}

    def insert_cash_ledger(self, payload: dict[str, Any]) -> dict[str, Any]:
        params = dict(payload)
        params["source_lineage_json"] = Jsonb(payload.get("source_lineage_json") or {})
        self.cur.execute(
            """
            INSERT INTO n6_virtual_cash_ledger (
              virtual_account_id,
              ledger_type,
              amount,
              currency,
              trade_date,
              event_time,
              source_event_type,
              source_event_id,
              source_virtual_order_id,
              source_virtual_trade_id,
              run_id,
              policy_version,
              policy_hash,
              rollback_scope,
              source_lineage_json,
              quality_status
            )
            VALUES (
              %(virtual_account_id)s,
              %(ledger_type)s,
              %(amount)s,
              %(currency)s,
              %(trade_date)s,
              %(event_time)s,
              %(source_event_type)s,
              %(source_event_id)s,
              %(source_virtual_order_id)s,
              %(source_virtual_trade_id)s,
              %(run_id)s,
              %(policy_version)s,
              %(policy_hash)s,
              %(rollback_scope)s,
              %(source_lineage_json)s,
              %(quality_status)s
            )
            RETURNING cash_ledger_id
            """,
            params,
        )
        row = self.cur.fetchone()
        return {"cash_ledger_id": int(row["cash_ledger_id"])}

    def insert_cash_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        params = dict(payload)
        params["source_lineage_json"] = Jsonb(payload.get("source_lineage_json") or {})
        self.cur.execute(
            """
            UPDATE n6_virtual_cash_snapshot
            SET snapshot_status = 'superseded'
            WHERE virtual_account_id = %(virtual_account_id)s
              AND trade_date = %(trade_date)s
              AND snapshot_status = 'active'
            """,
            params,
        )
        self.cur.execute(
            """
            INSERT INTO n6_virtual_cash_snapshot (
              virtual_account_id,
              trade_date,
              available_cash,
              frozen_cash,
              total_cash,
              currency,
              source_ledger_max_id,
              snapshot_status,
              run_id,
              policy_version,
              policy_hash,
              rollback_scope,
              source_lineage_json,
              quality_status
            )
            VALUES (
              %(virtual_account_id)s,
              %(trade_date)s,
              %(available_cash)s,
              %(frozen_cash)s,
              %(total_cash)s,
              %(currency)s,
              %(source_ledger_max_id)s,
              %(snapshot_status)s,
              %(run_id)s,
              %(policy_version)s,
              %(policy_hash)s,
              %(rollback_scope)s,
              %(source_lineage_json)s,
              %(quality_status)s
            )
            RETURNING cash_snapshot_id
            """,
            params,
        )
        row = self.cur.fetchone()
        cash_snapshot_id = int(row["cash_snapshot_id"])
        params["cash_snapshot_id"] = cash_snapshot_id
        account_scope = self._active_account_scope_by_id.get(int(params["virtual_account_id"]))
        if account_scope is not None:
            params["principal_id"], params["principal_type"] = account_scope
        if params.get("principal_id") is None or params.get("principal_type") is None:
            raise RuntimeError("virtual_account_scope_missing")
        self.cur.execute(
            """
            UPDATE n6_virtual_account
            SET current_cash_snapshot_id = %(cash_snapshot_id)s,
                updated_at = now()
            WHERE virtual_account_id = %(virtual_account_id)s
              AND principal_id = %(principal_id)s
              AND principal_type = %(principal_type)s
              AND virtual_account_status = 'active'
            """,
            params,
        )
        if getattr(self.cur, "rowcount", 1) != 1:
            raise RuntimeError("virtual_account_cash_pointer_update_failed")
        return {"cash_snapshot_id": cash_snapshot_id}

    def upsert_virtual_position(self, payload: dict[str, Any]) -> dict[str, Any]:
        params = dict(payload)
        params.setdefault("market_value", None)
        params.setdefault("unrealized_pnl", None)
        params["source_lineage_json"] = Jsonb(payload.get("source_lineage_json") or {})
        if params.get("virtual_position_id"):
            self.cur.execute(
                """
                UPDATE n6_virtual_position
                SET position_status = %(position_status)s,
                    quantity = %(quantity)s,
                    available_quantity = %(available_quantity)s,
                    locked_quantity = %(locked_quantity)s,
                    average_cost = %(average_cost)s,
                    market_value = COALESCE(%(market_value)s, market_value),
                    unrealized_pnl = COALESCE(%(unrealized_pnl)s, unrealized_pnl),
                    last_virtual_trade_id = %(last_virtual_trade_id)s,
                    run_id = %(run_id)s,
                    policy_version = %(policy_version)s,
                    policy_hash = %(policy_hash)s,
                    rollback_scope = %(rollback_scope)s,
                    source_lineage_json = %(source_lineage_json)s,
                    quality_status = %(quality_status)s,
                    updated_at = now()
                WHERE virtual_position_id = %(virtual_position_id)s
                  AND virtual_account_id = %(virtual_account_id)s
                RETURNING virtual_position_id
                """,
                params,
            )
            row = self.cur.fetchone()
            if row:
                return {"virtual_position_id": int(row["virtual_position_id"])}
            raise RuntimeError("virtual_position_update_failed")

        self.cur.execute(
            """
            INSERT INTO n6_virtual_position (
              virtual_account_id,
              principal_id,
              principal_type,
              asset_kind,
              identity_key,
              position_status,
              quantity,
              available_quantity,
              locked_quantity,
              average_cost,
              market_value,
              unrealized_pnl,
              last_virtual_trade_id,
              run_id,
              policy_version,
              policy_hash,
              rollback_scope,
              source_lineage_json,
              quality_status
            )
            VALUES (
              %(virtual_account_id)s,
              %(principal_id)s,
              %(principal_type)s,
              %(asset_kind)s,
              %(identity_key)s,
              %(position_status)s,
              %(quantity)s,
              %(available_quantity)s,
              %(locked_quantity)s,
              %(average_cost)s,
              %(market_value)s,
              %(unrealized_pnl)s,
              %(last_virtual_trade_id)s,
              %(run_id)s,
              %(policy_version)s,
              %(policy_hash)s,
              %(rollback_scope)s,
              %(source_lineage_json)s,
              %(quality_status)s
            )
            ON CONFLICT (virtual_account_id, asset_kind, identity_key)
            DO UPDATE SET
              position_status = EXCLUDED.position_status,
              quantity = n6_virtual_position.quantity + EXCLUDED.quantity,
              available_quantity = n6_virtual_position.available_quantity,
              locked_quantity = n6_virtual_position.locked_quantity + EXCLUDED.locked_quantity,
              average_cost = CASE
                WHEN (n6_virtual_position.quantity + EXCLUDED.quantity) > 0 THEN
                  (
                    (n6_virtual_position.quantity * n6_virtual_position.average_cost)
                    + (EXCLUDED.quantity * EXCLUDED.average_cost)
                  ) / (n6_virtual_position.quantity + EXCLUDED.quantity)
                ELSE EXCLUDED.average_cost
              END,
              market_value = n6_virtual_position.market_value,
              unrealized_pnl = n6_virtual_position.unrealized_pnl,
              last_virtual_trade_id = EXCLUDED.last_virtual_trade_id,
              run_id = EXCLUDED.run_id,
              policy_version = EXCLUDED.policy_version,
              policy_hash = EXCLUDED.policy_hash,
              rollback_scope = EXCLUDED.rollback_scope,
              source_lineage_json = EXCLUDED.source_lineage_json,
              quality_status = EXCLUDED.quality_status,
              updated_at = now()
            RETURNING virtual_position_id
            """,
            params,
        )
        row = self.cur.fetchone()
        return {"virtual_position_id": int(row["virtual_position_id"])}

    def insert_position_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        params = dict(payload)
        params["source_lineage_json"] = Jsonb(payload.get("source_lineage_json") or {})
        params["source_json"] = Jsonb(payload.get("source_json") or {})
        self.cur.execute(
            """
            INSERT INTO n6_virtual_position_event (
              virtual_position_id,
              virtual_account_id,
              principal_id,
              principal_type,
              asset_kind,
              identity_key,
              event_type,
              quantity_delta,
              available_quantity_delta,
              locked_quantity_delta,
              cost_delta,
              price,
              source_virtual_order_id,
              source_virtual_trade_id,
              event_time,
              trade_date,
              available_date,
              source_order_side,
              source_for_trade_date,
              source_trade_date,
              source_json,
              run_id,
              policy_version,
              policy_hash,
              rollback_scope,
              source_lineage_json,
              quality_status
            )
            VALUES (
              %(virtual_position_id)s,
              %(virtual_account_id)s,
              %(principal_id)s,
              %(principal_type)s,
              %(asset_kind)s,
              %(identity_key)s,
              %(event_type)s,
              %(quantity_delta)s,
              %(available_quantity_delta)s,
              %(locked_quantity_delta)s,
              %(cost_delta)s,
              %(price)s,
              %(source_virtual_order_id)s,
              %(source_virtual_trade_id)s,
              %(event_time)s,
              %(trade_date)s,
              %(available_date)s,
              %(source_order_side)s,
              %(source_for_trade_date)s,
              %(source_trade_date)s,
              %(source_json)s,
              %(run_id)s,
              %(policy_version)s,
              %(policy_hash)s,
              %(rollback_scope)s,
              %(source_lineage_json)s,
              %(quality_status)s
            )
            RETURNING position_event_id
            """,
            params,
        )
        row = self.cur.fetchone()
        return {"position_event_id": int(row["position_event_id"])}

    def _fetch_order_by_idempotency(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        idempotency_key = payload.get("idempotency_key")
        if not idempotency_key:
            return None
        self.cur.execute(
            """
            SELECT o.virtual_order_id,
                   t.virtual_trade_id,
                   o.idempotency_key
            FROM n6_virtual_order o
            LEFT JOIN n6_virtual_trade t
              ON t.virtual_order_id = o.virtual_order_id
            WHERE o.principal_id = %s
              AND o.virtual_account_id = %s
              AND o.idempotency_key = %s
            ORDER BY t.virtual_trade_id DESC NULLS LAST
            LIMIT 1
            """,
            (payload.get("principal_id"), payload.get("virtual_account_id"), idempotency_key),
        )
        row = self.cur.fetchone()
        return dict(row) if row else None


def config_from_env() -> N6UserWebConfig:
    return N6UserWebConfig(
        dsn=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN),
        cookie_secure=os.environ.get("ASHARE_V3_N6_COOKIE_SECURE", "0") == "1",
        session_ttl_seconds=int(os.environ.get("ASHARE_V3_N6_SESSION_TTL_SECONDS", str(8 * 60 * 60))),
        card_limit=int(os.environ.get("ASHARE_V3_N6_CARD_LIMIT", "500")),
        notification_limit=int(os.environ.get("ASHARE_V3_N6_NOTIFICATION_LIMIT", "500")),
        action_event_limit=int(os.environ.get("ASHARE_V3_N6_ACTION_EVENT_LIMIT", "500")),
        ui_signal_limit=int(os.environ.get("ASHARE_V3_N6_UI_SIGNAL_LIMIT", "500")),
        signal_source_user_id=int(os.environ.get("ASHARE_V3_N6_SIGNAL_SOURCE_USER_ID", "1")),
        post_close_fastlane_docs_root=os.environ.get(
            "ASHARE_V3_POST_CLOSE_FASTLANE_DOCS_ROOT",
            DEFAULT_POST_CLOSE_FASTLANE_DOCS_ROOT,
        ),
        runtime_archive_docs_root=os.environ.get(
            "ASHARE_V3_RUNTIME_ARCHIVE_DOCS_ROOT",
            DEFAULT_RUNTIME_ARCHIVE_DOCS_ROOT,
        ),
        runtime_archive_root=os.environ.get("ASHARE_V3_RUNTIME_ARCHIVE_ROOT", DEFAULT_RUNTIME_ARCHIVE_ROOT),
        rag_docs_root=os.environ.get("ASHARE_V3_RAG_DOCS_ROOT", DEFAULT_RAG_DOCS_ROOT),
        rag_sql_root=os.environ.get("ASHARE_V3_RAG_SQL_ROOT", DEFAULT_RAG_SQL_ROOT),
    )


def create_app(
    *,
    repository: N6UserRepository | None = None,
    buy_execution_repository: Any | None = None,
    config: N6UserWebConfig | None = None,
    password_verifier: PasswordVerifier | None = None,
    password_hasher: PasswordHasher | None = None,
) -> FastAPI:
    web_config = config or config_from_env()
    repo = repository or PostgresN6UserRepository(web_config.dsn)
    buy_repo = buy_execution_repository or PostgresVirtualBuyExecutionRepository(web_config.dsn)
    verifier = password_verifier or verify_password
    hasher = password_hasher or hash_password
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    app = FastAPI(
        title="Ashare v3 N6 User MVP",
        description="N6 login and read-only user projection pages.",
    )

    @app.get("/n6/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> HTMLResponse:
        next_target = safe_b_track_next(request.query_params.get("next"))
        return templates.TemplateResponse(request, "n6_login.html", {"request": request, "next": next_target or ""})

    @app.post("/api/n6/auth/login")
    async def login(request: Request) -> Response:
        payload = await read_login_payload(request)
        login_name = str(payload.get("login_name") or "").strip()
        password = str(payload.get("password") or "")
        requested_next = payload.get("next") or request.query_params.get("next")
        user = repo.fetch_user_for_login(login_name) if login_name else None
        if user is None or user.status != "active" or not verifier(password, user.password_hash, user.password_hash_algo):
            return JSONResponse({"ok": False, "error": "invalid_login"}, status_code=401)

        raw_token = generate_session_token()
        expires_at = utc_now() + timedelta(seconds=web_config.session_ttl_seconds)
        session = repo.create_session(
            user_id=user.user_id,
            session_token_hash=hash_session_token(raw_token),
            session_token_hash_algo=SESSION_HASH_ALGO,
            expires_at=expires_at,
            client_info=client_info_from_request(request),
        )
        next_target = login_success_location(user, requested_next)
        response = RedirectResponse(next_target, status_code=302)
        response.set_cookie(
            COOKIE_NAME,
            raw_token,
            httponly=True,
            secure=web_config.cookie_secure,
            samesite="lax",
            path="/",
            max_age=web_config.session_ttl_seconds,
        )
        return response

    @app.get("/api/n6/me")
    async def me(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        return JSONResponse({"ok": True, "user": session_user_payload(session)})

    @app.get("/api/n6/app/v1/me")
    async def app_v1_me(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        return JSONResponse(app_me_model(principal, user=session_user_payload(session)))

    @app.get("/api/n6/app/v1/account")
    async def app_v1_account(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        account, snapshot = app_account_sources(repo, principal)
        return JSONResponse(
            app_account_model(principal, user=session_user_payload(session), account=account, cash_snapshot=snapshot)
        )

    @app.get("/api/n6/app/v1/dashboard")
    async def app_v1_dashboard(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        return JSONResponse(build_app_dashboard_data(session, principal))

    @app.get("/api/n6/app/v1/watchlist")
    async def app_v1_watchlist(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        rows = repo.fetch_app_signals(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            filters={},
            limit=web_config.ui_signal_limit,
        )
        return JSONResponse(app_watchlist_model(principal, user=session_user_payload(session), rows=rows))

    @app.get("/api/n6/app/v1/signals")
    async def app_v1_signals(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        filters = ui_v1_filters_from_request(request)
        limit = ui_v1_limit_from_request(request, web_config.ui_signal_limit)
        scope_metadata = repo.fetch_app_signal_scope_metadata(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
        )
        date_policy = n6_trade_date_access_policy(
            current_trade_date=current_app_signal_trade_date(scope_metadata),
            requested_trade_date=filters.get("trade_date"),
        )
        if date_policy["blocked"]:
            return n6_trading_session_blocker_response(date_policy)
        filters = app_signal_filters_with_trade_date_defaults(filters, scope_metadata)
        scope_metadata = app_signal_scope_metadata_for_filters(scope_metadata, filters)
        rows = repo.fetch_app_signals(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            filters=filters,
            limit=limit,
        )
        return JSONResponse(
            app_signals_model(
                principal,
                user=session_user_payload(session),
                rows=rows,
                filters=filters,
                scope_metadata=scope_metadata,
            )
        )

    @app.get("/api/n6/app/v1/signals/{user_signal_projection_id}")
    async def app_v1_signal_detail(request: Request, user_signal_projection_id: int) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        row = repo.fetch_app_signal_detail(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            user_signal_projection_id=user_signal_projection_id,
        )
        if row is None:
            return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
        return JSONResponse(app_signal_detail_model(principal, user=session_user_payload(session), row=row))

    @app.get("/api/n6/app/v1/status-monitor")
    async def app_v1_status_monitor(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        filters = ui_v1_filters_from_request(request)
        rows = repo.fetch_app_signals(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            filters=filters,
            limit=web_config.ui_signal_limit,
        )
        return JSONResponse(
            app_status_monitor_model(principal, user=session_user_payload(session), rows=rows, filters=filters)
        )

    @app.get("/api/n6/app/v1/proposals")
    async def app_v1_proposals(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        return JSONResponse(
            app_locked_future_module_model(
                principal, user=session_user_payload(session), module_key="proposals", component="B Track Proposals"
            )
        )

    @app.get("/api/n6/app/v1/portfolio")
    async def app_v1_portfolio(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        return JSONResponse(
            app_locked_future_module_model(
                principal, user=session_user_payload(session), module_key="portfolio", component="B Track Portfolio"
            )
        )

    @app.get("/api/n6/app/v1/pnl")
    async def app_v1_pnl(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        return JSONResponse(
            app_locked_future_module_model(
                principal, user=session_user_payload(session), module_key="pnl", component="B Track PnL"
            )
        )

    @app.get("/api/n6/app/v1/ai-users")
    async def app_v1_ai_users(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        return JSONResponse(app_ai_users_model(principal, user=session_user_payload(session)))

    @app.get("/api/n6/app/v1/leaderboard")
    async def app_v1_leaderboard(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        return JSONResponse(app_leaderboard_model(principal, user=session_user_payload(session)))

    def app_v2_message_context(
        request: Request,
    ) -> tuple[AuthSession, dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]] | JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        filters = ui_v1_filters_from_request(request)
        scope_metadata = repo.fetch_app_signal_scope_metadata(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
        )
        date_policy = n6_trade_date_access_policy(
            current_trade_date=current_app_signal_trade_date(scope_metadata),
            requested_trade_date=filters.get("trade_date"),
        )
        if date_policy["blocked"]:
            return n6_trading_session_blocker_response(date_policy)
        filters = app_signal_filters_with_trade_date_defaults(filters, scope_metadata)
        scope_metadata = app_signal_scope_metadata_for_filters(scope_metadata, filters)
        rows = repo.fetch_app_signals(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            filters=filters,
            limit=web_config.ui_signal_limit,
        )
        return session, principal, rows, scope_metadata, filters

    def build_app_v2_buy_messages_data(
        session: AuthSession,
        principal: dict[str, Any],
        *,
        selected_asset_kind: str | None = None,
    ) -> dict[str, Any]:
        rows = repo.fetch_app_signals(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            filters={},
            limit=web_config.ui_signal_limit,
        )
        scope_metadata = repo.fetch_app_signal_scope_metadata(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
        )
        return app_v2_buy_messages_model(
            principal,
            user=session_user_payload(session),
            rows=rows,
            scope_metadata=scope_metadata,
            selected_asset_kind=selected_asset_kind,
        )

    @app.get("/api/n6/app/v2/message-dashboard")
    async def app_v2_message_dashboard(request: Request) -> JSONResponse:
        context = app_v2_message_context(request)
        if isinstance(context, JSONResponse):
            return context
        session, principal, rows, scope_metadata, filters = context
        return JSONResponse(
            build_app_v2_message_dashboard(
                principal,
                user=session_user_payload(session),
                rows=rows,
                filters=filters,
                scope_metadata=scope_metadata,
                limit=web_config.ui_signal_limit,
            )
        )

    @app.get("/api/n6/app/v2/message-dashboard/groups")
    async def app_v2_message_dashboard_groups(request: Request) -> JSONResponse:
        context = app_v2_message_context(request)
        if isinstance(context, JSONResponse):
            return context
        session, principal, rows, scope_metadata, _filters = context
        return JSONResponse(
            build_app_v2_message_groups(
                principal,
                user=session_user_payload(session),
                rows=rows,
                scope_metadata=scope_metadata,
            )
        )

    @app.get("/api/n6/app/v2/message-dashboard/projection-status")
    async def app_v2_message_dashboard_projection_status(request: Request) -> JSONResponse:
        context = app_v2_message_context(request)
        if isinstance(context, JSONResponse):
            return context
        session, principal, rows, scope_metadata, _filters = context
        return JSONResponse(
            build_app_v2_projection_status(
                principal,
                user=session_user_payload(session),
                rows=rows,
                scope_metadata=scope_metadata,
            )
        )

    @app.get("/api/n6/app/v2/buy-messages")
    async def app_v2_buy_messages(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        asset_kind = normalize_filter_value(request.query_params.get("asset_kind"))
        if asset_kind and asset_kind not in {"index", "board", "stock"}:
            return JSONResponse({"ok": False, "error": "invalid_asset_kind"}, status_code=400)
        return JSONResponse(
            build_app_v2_buy_messages_data(
                session,
                principal,
                selected_asset_kind=asset_kind or None,
            )
        )

    @app.post("/api/n6/app/v2/buy-messages/{user_signal_projection_id}/execute")
    async def app_v2_buy_message_execute(request: Request, user_signal_projection_id: int) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        signal = repo.fetch_app_signal_detail(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            user_signal_projection_id=user_signal_projection_id,
        )
        if signal is None:
            return JSONResponse(virtual_buy_rejected_response("signal_not_found"), status_code=404)
        price = first_virtual_buy_value(body, "price") or first_virtual_buy_value(signal, "trigger_price", "current_price")
        if price is None:
            return JSONResponse(virtual_buy_rejected_response("price_missing"), status_code=400)
        trade_date = normalize_virtual_buy_date(
            first_virtual_buy_value(body, "trade_date") or first_virtual_buy_value(signal, "trade_date")
        )
        if trade_date is None:
            return JSONResponse(virtual_buy_rejected_response("trade_date_missing"), status_code=400)
        available_date = normalize_virtual_buy_date(
            first_virtual_buy_value(body, "available_date") or first_virtual_buy_value(signal, "available_date")
        )
        if available_date is None:
            return JSONResponse(virtual_buy_rejected_response("available_date_missing"), status_code=400)
        buy_request = VirtualBuyRequest(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_signal_projection_id=int(user_signal_projection_id),
            quantity=body.get("quantity", 300),
            price=price,
            trade_date=trade_date,
            available_date=available_date,
        )
        try:
            transaction_factory = getattr(buy_repo, "transaction", None)
            scope = transaction_factory() if callable(transaction_factory) else nullcontext(buy_repo)
            with scope as scoped_buy_repo:
                result = execute_virtual_buy(
                    SignalBoundVirtualBuyExecutionRepository(scoped_buy_repo, signal),
                    buy_request,
                )
        except VirtualBuyRejected as exc:
            return JSONResponse(virtual_buy_rejected_response(exc.code), status_code=400)
        return JSONResponse(virtual_buy_result_response(result))

    @app.get("/api/n6/app/v2/filter/stocks")
    async def app_v2_filter_stocks(request: Request) -> JSONResponse:
        return app_v2_filter_response(request, "stock")

    @app.get("/api/n6/app/v2/filter/boards")
    async def app_v2_filter_boards(request: Request) -> JSONResponse:
        return app_v2_filter_response(request, "board")

    @app.get("/api/n6/app/v2/filter/indexes")
    async def app_v2_filter_indexes(request: Request) -> JSONResponse:
        return app_v2_filter_response(request, "index")

    @app.get("/api/n6/app/v2/filter/board-members")
    async def app_v2_filter_board_members(request: Request) -> JSONResponse:
        return app_v2_filter_members_response(request, "board")

    @app.get("/api/n6/app/v2/filter/index-members")
    async def app_v2_filter_index_members(request: Request) -> JSONResponse:
        return app_v2_filter_members_response(request, "index")

    @app.get("/api/n6/app/v2/filter/board-linked-stocks")
    async def app_v2_filter_board_linked_stocks(request: Request) -> JSONResponse:
        return app_v2_filter_linked_stocks_response(request, "board")

    @app.get("/api/n6/app/v2/filter/index-linked-stocks")
    async def app_v2_filter_index_linked_stocks(request: Request) -> JSONResponse:
        return app_v2_filter_linked_stocks_response(request, "index")

    @app.get("/api/n6/app/v2/membership/index/{index_identity_key:path}")
    async def app_v2_membership_index(request: Request, index_identity_key: str) -> JSONResponse:
        return app_v2_membership_response(request, "index", index_identity_key)

    @app.get("/api/n6/app/v2/membership/board/{board_identity_key:path}")
    async def app_v2_membership_board(request: Request, board_identity_key: str) -> JSONResponse:
        return app_v2_membership_response(request, "board", board_identity_key)

    @app.get("/api/n6/app/v2/monitor")
    async def app_v2_monitor(request: Request) -> JSONResponse:
        return app_v2_monitor_response(request, None)

    @app.get("/api/n6/app/v2/monitor/stocks")
    async def app_v2_monitor_stocks(request: Request) -> JSONResponse:
        return app_v2_monitor_response(request, "stock")

    @app.get("/api/n6/app/v2/monitor/boards")
    async def app_v2_monitor_boards(request: Request) -> JSONResponse:
        return app_v2_monitor_response(request, "board")

    @app.get("/api/n6/app/v2/monitor/indexes")
    async def app_v2_monitor_indexes(request: Request) -> JSONResponse:
        return app_v2_monitor_response(request, "index")

    @app.post("/api/n6/app/v2/monitor/items")
    async def app_v2_monitor_add_item(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        try:
            body = await request.json()
        except Exception:
            body = {}
        asset_kind = normalize_filter_value(body.get("asset_kind"))
        identity_key = normalize_filter_value(body.get("identity_key"))
        direction = normalize_filter_value(body.get("direction")) or "buy"
        for_trade_date = normalize_filter_value(body.get("for_trade_date"))
        if asset_kind not in APP_V2_MONITOR_TABLE_BY_ASSET or not identity_key or direction not in APP_V2_VALID_DIRECTIONS:
            return JSONResponse({"ok": False, "error": "invalid_monitor_request"}, status_code=400)
        result = repo.add_app_monitor_item(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            asset_kind=asset_kind,
            identity_key=identity_key,
            direction=direction,
            source="single_row",
            for_trade_date=for_trade_date,
        )
        if result.get("status") == "not_found":
            return n6_json_response(result, status_code=404)
        if result.get("status") == "data_not_ready":
            return n6_json_response(result, status_code=409)
        return n6_json_response(result)

    @app.post("/api/n6/app/v2/monitor/bulk-add")
    async def app_v2_monitor_bulk_add(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        try:
            body = await request.json()
        except Exception:
            body = {}
        asset_kind = normalize_filter_value(body.get("asset_kind"))
        direction = normalize_filter_value(body.get("direction")) or "buy"
        filters = body.get("filters") if isinstance(body.get("filters"), dict) else {}
        for_trade_date = normalize_filter_value(body.get("for_trade_date"))
        if asset_kind not in APP_V2_MONITOR_TABLE_BY_ASSET or direction not in APP_V2_VALID_DIRECTIONS:
            return JSONResponse({"ok": False, "error": "invalid_monitor_request"}, status_code=400)
        clean_filters = {key: value for key, value in filters.items() if value}
        if for_trade_date:
            clean_filters["for_trade_date"] = for_trade_date
        result = repo.bulk_add_app_monitor_items(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            asset_kind=asset_kind,
            direction=direction,
            filters=clean_filters,
        )
        if result.get("status") == "data_not_ready":
            return n6_json_response(result, status_code=409)
        return n6_json_response(result)

    @app.post("/api/n6/app/v2/monitor/selected-add")
    async def app_v2_monitor_selected_add(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        try:
            body = await request.json()
        except Exception:
            body = {}
        asset_kind = normalize_filter_value(body.get("asset_kind"))
        direction = normalize_filter_value(body.get("direction")) or "buy"
        for_trade_date = normalize_filter_value(body.get("for_trade_date"))
        raw_identity_keys = body.get("identity_keys")
        identity_keys = (
            [str(item).strip() for item in raw_identity_keys if str(item or "").strip()]
            if isinstance(raw_identity_keys, list)
            else []
        )
        if (
            asset_kind not in APP_V2_MONITOR_TABLE_BY_ASSET
            or direction not in APP_V2_VALID_DIRECTIONS
            or not identity_keys
        ):
            return JSONResponse({"ok": False, "error": "invalid_monitor_request"}, status_code=400)
        result = repo.selected_add_app_monitor_items(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            asset_kind=asset_kind,
            direction=direction,
            identity_keys=identity_keys,
            for_trade_date=for_trade_date,
        )
        if result.get("status") == "data_not_ready":
            return n6_json_response(result, status_code=409)
        return n6_json_response(result)

    @app.post("/api/n6/app/v2/monitor/linked-stocks")
    async def app_v2_monitor_add_linked_stocks(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        try:
            body = await request.json()
        except Exception:
            body = {}
        parent_asset_kind = normalize_filter_value(body.get("parent_asset_kind"))
        parent_identity_key = normalize_filter_value(body.get("parent_identity_key"))
        mode = normalize_filter_value(body.get("mode")) or "selected"
        direction = normalize_filter_value(body.get("direction")) or "buy"
        raw_stock_keys = body.get("stock_identity_keys")
        stock_identity_keys = (
            [str(item).strip() for item in raw_stock_keys if str(item or "").strip()]
            if isinstance(raw_stock_keys, list)
            else []
        )
        if (
            parent_asset_kind not in {"index", "board"}
            or not parent_identity_key
            or mode not in {"selected", "matched_stock_filter"}
            or direction not in APP_V2_VALID_DIRECTIONS
            or (mode == "selected" and not stock_identity_keys)
        ):
            return JSONResponse({"ok": False, "error": "invalid_monitor_request"}, status_code=400)
        result = repo.add_app_linked_stock_monitor_items(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            parent_asset_kind=parent_asset_kind,
            parent_identity_key=parent_identity_key,
            mode=mode,
            stock_identity_keys=stock_identity_keys,
            direction=direction,
        )
        if result.get("status") == "invalid_request":
            return n6_json_response(result, status_code=400)
        if result.get("status") == "data_not_ready":
            return n6_json_response(result, status_code=409)
        if result.get("status") == "not_found":
            return n6_json_response(result, status_code=404)
        return n6_json_response(result)

    @app.delete("/api/n6/app/v2/monitor/items/{monitor_id}")
    async def app_v2_monitor_delete_item(request: Request, monitor_id: int) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        result = repo.remove_app_monitor_item(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            monitor_id=monitor_id,
        )
        if result.get("status") == "not_found":
            return n6_json_response(result, status_code=404)
        return n6_json_response(result)

    @app.get("/api/n6/app/v2/realtime-scope")
    async def app_v2_realtime_scope(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        result = repo.fetch_app_realtime_scope(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
        )
        return n6_json_response({"ok": True, **result})

    @app.post("/api/n6/app/v2/realtime-scope/items")
    async def app_v2_realtime_scope_add_item(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        try:
            body = await request.json()
        except Exception:
            body = {}
        asset_kind = normalize_filter_value(body.get("asset_kind"))
        identity_key = normalize_filter_value(body.get("identity_key"))
        for_trade_date = normalize_filter_value(body.get("for_trade_date"))
        if asset_kind not in APP_V2_MONITOR_TABLE_BY_ASSET or not identity_key:
            return JSONResponse({"ok": False, "error": "invalid_realtime_scope_request"}, status_code=400)
        result = repo.add_app_realtime_scope_item(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            asset_kind=asset_kind,
            identity_key=identity_key,
            for_trade_date=for_trade_date,
            source="single_row",
        )
        if result.get("status") == "data_not_ready":
            return n6_json_response(result, status_code=409)
        return n6_json_response(result)

    @app.post("/api/n6/app/v2/realtime-scope/selected-add")
    async def app_v2_realtime_scope_selected_add(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        try:
            body = await request.json()
        except Exception:
            body = {}
        asset_kind = normalize_filter_value(body.get("asset_kind"))
        for_trade_date = normalize_filter_value(body.get("for_trade_date"))
        raw_identity_keys = body.get("identity_keys")
        identity_keys = (
            [str(item).strip() for item in raw_identity_keys if str(item or "").strip()]
            if isinstance(raw_identity_keys, list)
            else []
        )
        if asset_kind not in APP_V2_MONITOR_TABLE_BY_ASSET or not identity_keys:
            return JSONResponse({"ok": False, "error": "invalid_realtime_scope_request"}, status_code=400)
        result = repo.selected_add_app_realtime_scope_items(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            asset_kind=asset_kind,
            identity_keys=identity_keys,
            for_trade_date=for_trade_date,
        )
        if result.get("status") == "data_not_ready":
            return n6_json_response(result, status_code=409)
        return n6_json_response(result)

    @app.post("/api/n6/app/v2/realtime-scope/bulk-add")
    async def app_v2_realtime_scope_bulk_add(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        try:
            body = await request.json()
        except Exception:
            body = {}
        asset_kind = normalize_filter_value(body.get("asset_kind"))
        filters = body.get("filters") if isinstance(body.get("filters"), dict) else {}
        for_trade_date = normalize_filter_value(body.get("for_trade_date"))
        if asset_kind not in APP_V2_MONITOR_TABLE_BY_ASSET:
            return JSONResponse({"ok": False, "error": "invalid_realtime_scope_request"}, status_code=400)
        clean_filters = {key: value for key, value in filters.items() if value}
        if for_trade_date:
            clean_filters["for_trade_date"] = for_trade_date
        result = repo.bulk_add_app_realtime_scope_items(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            asset_kind=asset_kind,
            filters=clean_filters,
        )
        if result.get("status") == "data_not_ready":
            return n6_json_response(result, status_code=409)
        return n6_json_response(result)

    @app.delete("/api/n6/app/v2/realtime-scope/items/{realtime_scope_id}")
    async def app_v2_realtime_scope_delete_item(request: Request, realtime_scope_id: int) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        result = repo.remove_app_realtime_scope_item(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            realtime_scope_id=realtime_scope_id,
        )
        if result.get("status") == "not_found":
            return n6_json_response(result, status_code=404)
        if result.get("status") == "data_not_ready":
            return n6_json_response(result, status_code=409)
        return n6_json_response(result)

    @app.get("/api/n6/ui/v1/signals")
    async def ui_v1_signals(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        filters = ui_v1_filters_from_request(request)
        limit = ui_v1_limit_from_request(request, 100)
        offset = ui_v1_offset_from_request(request)
        source_user_id = signal_source_user_id(session, web_config)
        rows = repo.fetch_ui_v1_signals(source_user_id, filters, limit, offset)
        pagination = {
            "total_count": repo.count_ui_v1_signals(source_user_id, {}),
            "filtered_count": repo.count_ui_v1_signals(source_user_id, filters),
            "limit": limit,
            "offset": offset,
        }
        statistics = repo.fetch_ui_v1_signal_statistics(source_user_id)
        return JSONResponse(signal_list_model(rows, filters=filters, pagination=pagination, statistics=statistics))

    @app.get("/api/n6/ui/v1/signals/{user_signal_projection_id}")
    async def ui_v1_signal_detail(request: Request, user_signal_projection_id: int) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        row = repo.fetch_ui_v1_signal_detail(signal_source_user_id(session, web_config), user_signal_projection_id)
        if row is None:
            return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
        artifacts = repo.fetch_ui_v1_artifacts()
        rollback_summary = repo.fetch_ui_v1_rollback_summary()
        return JSONResponse(signal_detail_model(row, artifacts=artifacts, rollback_summary=rollback_summary))

    @app.get("/api/n6/ui/v1/dashboard/metrics")
    async def ui_v1_dashboard_metrics(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        metrics = repo.fetch_ui_v1_dashboard_metrics(signal_source_user_id(session, web_config))
        return JSONResponse(dashboard_metrics_model(metrics))

    @app.get("/api/n6/ui/v1/virtual-account")
    async def ui_v1_virtual_account(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        account = repo.fetch_ui_v1_virtual_account(session.user_id)
        snapshot = repo.fetch_ui_v1_cash_snapshot(session.user_id)
        return JSONResponse(virtual_account_summary_model(account, cash_snapshot=snapshot))

    @app.get("/api/n6/ui/v1/cash-snapshot")
    async def ui_v1_cash_snapshot(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        snapshot = repo.fetch_ui_v1_cash_snapshot(session.user_id)
        return JSONResponse(cash_snapshot_model(snapshot))

    @app.get("/api/n6/ui/v1/cash-ledger")
    async def ui_v1_cash_ledger(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        limit = cash_ledger_limit_from_request(request)
        rows = repo.fetch_ui_v1_cash_ledger(session.user_id, limit)
        return JSONResponse(cash_ledger_model(rows))

    @app.get("/api/n6/ui/v1/message-dashboard")
    async def ui_v1_message_dashboard(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        dashboard = repo.fetch_message_dashboard(web_config.action_event_limit)
        return JSONResponse(message_dashboard_model(dashboard))

    @app.get("/api/n6/ui/v1/lineage-stats")
    async def ui_v1_lineage_stats(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        stats = repo.fetch_ui_v1_lineage_stats(signal_source_user_id(session, web_config))
        return JSONResponse(lineage_stats_model(stats))

    @app.get("/api/n6/ui/v1/n3-messages")
    async def ui_v1_n3_messages(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        if session.role != "admin":
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
        include_all = query_param_enabled(request, "show_all")
        limit = ui_v1_limit_from_request(request, N3_MESSAGE_DEFAULT_LIMIT, max_limit=5000)
        data = repo.fetch_ui_v1_n3_messages(
            filters=raw_message_filters_from_request(request),
            limit=limit,
            include_all=include_all,
        )
        return JSONResponse(n3_messages_model(data))

    @app.get("/api/n6/ui/v1/n4-messages")
    async def ui_v1_n4_messages(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        if session.role != "admin":
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
        include_all = query_param_enabled(request, "show_all")
        limit = ui_v1_limit_from_request(request, N4_MESSAGE_DEFAULT_LIMIT, max_limit=5000)
        data = repo.fetch_ui_v1_n4_messages(
            filters=raw_message_filters_from_request(request),
            limit=limit,
            include_all=include_all,
        )
        return JSONResponse(n4_messages_model(data))

    @app.get("/api/n6/ui/v1/n5-messages")
    async def ui_v1_n5_messages(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        if session.role != "admin":
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
        include_all = query_param_enabled(request, "show_all")
        limit = ui_v1_limit_from_request(request, N5_MESSAGE_DEFAULT_LIMIT, max_limit=5000)
        data = repo.fetch_ui_v1_n5_messages(
            filters=raw_message_filters_from_request(request),
            limit=limit,
            include_all=include_all,
        )
        return JSONResponse(n5_messages_model(data))

    @app.get("/api/n6/ui/v1/n5-actions")
    async def ui_v1_n5_actions(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        if session.role != "admin":
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
        limit = ui_v1_limit_from_request(request, N5_MESSAGE_DEFAULT_LIMIT, max_limit=5000)
        data = repo.fetch_ui_v1_n5_actions(
            filters=n5_action_filters_from_request(request),
            limit=limit,
        )
        return JSONResponse(data)

    @app.get("/api/n6/b-track/v1/buy-signals")
    async def b_track_v1_buy_signals(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        if session.role != "admin":
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
        limit = ui_v1_limit_from_request(request, N5_MESSAGE_DEFAULT_LIMIT, max_limit=5000)
        data = repo.fetch_b_track_buy_signals(
            filters=b_track_buy_signal_filters_from_request(request),
            limit=limit,
        )
        return JSONResponse(data)

    @app.get("/api/n6/ui/v1/input-messages")
    async def ui_v1_input_messages(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        if session.role != "admin":
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
        include_all = query_param_enabled(request, "show_all")
        limit = ui_v1_limit_from_request(request, N6_INPUT_MESSAGE_DEFAULT_LIMIT, max_limit=5000)
        data = repo.fetch_ui_v1_input_messages(
            filters=raw_message_filters_from_request(request),
            limit=limit,
            include_all=include_all,
        )
        return JSONResponse(input_messages_model(data))

    @app.get("/api/n6/ui/v1/post-close-fastlane-status")
    async def ui_v1_post_close_fastlane_status(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        if session.role != "admin":
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
        data = read_post_close_fastlane_status(
            docs_root=web_config.post_close_fastlane_docs_root,
            for_trade_date=request.query_params.get("for_trade_date"),
        )
        return JSONResponse(post_close_fastlane_status_model(data))

    @app.get("/api/n6/ui/v1/rag-search")
    async def ui_v1_rag_search(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        if session.role != "admin":
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
        limit = ui_v1_limit_from_request(request, 8, max_limit=20)
        data = read_rag_status_answer(
            docs_root=web_config.rag_docs_root,
            sql_root=web_config.rag_sql_root,
            query=str(request.query_params.get("q") or ""),
            limit=limit,
            layer_role=request.query_params.get("layer_role"),
            trade_date=request.query_params.get("trade_date"),
            artifact_type=request.query_params.get("artifact_type"),
        )
        return JSONResponse(rag_search_model(data))

    @app.get("/api/n6/ui/v1/archive-status")
    async def ui_v1_archive_status(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        if session.role != "admin":
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
        data = read_runtime_archive_status(
            docs_root=web_config.runtime_archive_docs_root,
            archive_root=web_config.runtime_archive_root,
            trade_date=request.query_params.get("trade_date"),
        )
        return JSONResponse(runtime_archive_status_model(data))

    @app.get("/api/n6/ui/v1/n2-condition-basis")
    async def ui_v1_n2_condition_basis(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        if session.role != "admin":
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
        asset_kind = str(request.query_params.get("asset_kind") or "index").strip().lower()
        if asset_kind not in N2_CONDITION_BASIS_ASSET_META:
            return JSONResponse({"ok": False, "error": "invalid_asset_kind"}, status_code=400)
        include_all = query_param_enabled(request, "show_all")
        limit = ui_v1_limit_from_request(request, N2_CONDITION_BASIS_DEFAULT_LIMIT, max_limit=5000)
        data = repo.fetch_ui_v1_n2_condition_basis(
            asset_kind=asset_kind,
            filters=n2_condition_basis_filters_from_request(request),
            limit=limit,
            include_all=include_all,
        )
        return JSONResponse(n2_condition_basis_model(data))

    @app.get("/api/n6/ui/v1/status-monitor")
    async def ui_v1_status_monitor(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        if session.role != "admin":
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
        filters = status_monitor_filters_from_request(request)
        limit = ui_v1_limit_from_request(request, 100)
        offset = ui_v1_offset_from_request(request)
        data = repo.fetch_ui_v1_status_monitor(
            signal_source_user_id(session, web_config),
            filters,
            limit,
            offset,
        )
        return JSONResponse(status_monitor_model(data, filters=filters))

    @app.get("/api/n6/ui/v1/artifacts")
    async def ui_v1_artifacts(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        return JSONResponse(artifacts_model(repo.fetch_ui_v1_artifacts()))

    @app.get("/api/n6/ui/v1/rollback-summary")
    async def ui_v1_rollback_summary(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        return JSONResponse(rollback_summary_model(repo.fetch_ui_v1_rollback_summary()))

    @app.post("/api/n6/auth/logout")
    async def logout(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE_NAME, path="/")
        if session is None:
            return response
        repo.revoke_session(session.session_token_hash, utc_now())
        return response

    @app.post("/api/n6/admin/users")
    async def admin_create_user(request: Request) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        if session.role != "admin":
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
        payload = await read_login_payload(request)
        login_name = normalize_login_name(payload.get("login_name"))
        display_name = normalize_optional_text(payload.get("display_name"))
        role = str(payload.get("role") or "user").strip()
        password = str(payload.get("password") or "")
        blockers = validate_user_create_payload(login_name=login_name, role=role)
        blockers.extend(validate_password(password))
        if blockers:
            return JSONResponse({"ok": False, "error": "invalid_user_payload", "blockers": blockers}, status_code=400)
        try:
            hash_result = hasher(password)
            user_row = repo.create_user_with_defaults(
                login_name=login_name,
                display_name=display_name,
                role=role,
                password_hash=hash_result.password_hash,
                password_hash_algo=hash_result.password_hash_algo,
                created_by_user_id=session.user_id,
            )
        except UserManagementError as exc:
            return JSONResponse({"ok": False, "error": exc.code, "blockers": [exc.code]}, status_code=409)
        except ValueError as exc:
            code = str(exc) or "user_create_failed"
            status = 409 if code == "login_name_exists" else 400
            return JSONResponse({"ok": False, "error": code, "blockers": [code]}, status_code=status)
        except RuntimeError:
            return JSONResponse({"ok": False, "error": "password_hash_unavailable"}, status_code=500)
        return JSONResponse(
            {
                "ok": True,
                "user": user_view(user_row),
                "created": {"user_account": 1, "user_filter_profile": 1, "user_sim_account": 1},
                "password_value_logged": False,
                "password_hash_logged": False,
            }
        )

    @app.post("/api/n6/admin/users/{target_user_id}/delete")
    async def admin_delete_user(request: Request, target_user_id: int) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        if session.role != "admin":
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
        if target_user_id == session.user_id:
            return JSONResponse({"ok": False, "error": "cannot_delete_self"}, status_code=400)
        try:
            user_row = repo.delete_user(target_user_id=target_user_id, deleted_by_user_id=session.user_id)
        except UserManagementError as exc:
            return JSONResponse({"ok": False, "error": exc.code, "blockers": [exc.code]}, status_code=404)
        except ValueError as exc:
            code = str(exc) or "user_not_found"
            return JSONResponse({"ok": False, "error": code, "blockers": [code]}, status_code=404)
        return JSONResponse({"ok": True, "user": user_view(user_row), "soft_deleted": True, "sessions_revoked": True})

    def build_app_dashboard_data(session: AuthSession, principal: dict[str, Any]) -> dict[str, Any]:
        user = session_user_payload(session)
        account, snapshot = app_account_sources(repo, principal)
        signals = repo.fetch_app_signals(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            filters={},
            limit=web_config.ui_signal_limit,
        )
        return app_dashboard_model(
            principal,
            user=user,
            account=account,
            cash_snapshot=snapshot,
            signal_rows=signals,
        )

    def app_v2_filter_response(request: Request, asset_kind: str) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        filters = {key: value for key, value in app_v2_filter_filters_from_request(request).items() if value}
        date_policy = app_v2_filter_trade_date_policy(session, principal, asset_kind, filters)
        if date_policy["blocked"]:
            return n6_trading_session_blocker_response(date_policy)
        result = repo.fetch_app_filter_items(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            asset_kind=asset_kind,
            filters=filters,
            limit=ui_v1_limit_from_request(request, 100, max_limit=200),
            include_all_fields=True,
        )
        return JSONResponse(
            app_v2_filter_model(
                principal,
                user=session_user_payload(session),
                asset_kind=asset_kind,
                result=result,
                filters=filters,
                base_href=f"/n6/app/filter-center/{APP_FILTER_CENTER_PAGE_BY_ASSET[asset_kind]}",
            )
        )

    def app_v2_filter_trade_date_policy(
        session: AuthSession,
        principal: dict[str, Any],
        asset_kind: str,
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        requested_trade_date = normalize_filter_value(filters.get("for_trade_date"))
        if not requested_trade_date:
            return n6_trade_date_access_policy(current_trade_date=None, requested_trade_date=None)
        current_filters = {key: value for key, value in filters.items() if key != "for_trade_date" and value}
        current_result = repo.fetch_app_filter_items(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            asset_kind=asset_kind,
            filters=current_filters,
            limit=1,
            include_all_fields=False,
        )
        current_trade_date = ""
        for value in current_result.get("available_for_trade_dates") or []:
            text = normalize_filter_value(value)
            if text:
                current_trade_date = text
                break
        if not current_trade_date:
            current_trade_date = normalize_filter_value(current_result.get("selected_for_trade_date"))
        return n6_trade_date_access_policy(
            current_trade_date=current_trade_date,
            requested_trade_date=requested_trade_date,
        )

    def app_v2_filter_members_response(request: Request, membership_kind: str) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        parent_identity_key = normalize_filter_value(request.query_params.get("identity_key")) or ""
        result = repo.fetch_app_filter_members(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            membership_kind=membership_kind,
            parent_identity_key=parent_identity_key,
            limit=ui_v1_limit_from_request(request, 100, max_limit=500),
        )
        return JSONResponse(
            app_v2_filter_members_model(
                principal,
                user=session_user_payload(session),
                membership_kind=membership_kind,
                parent_identity_key=parent_identity_key,
                result=result,
            )
        )

    def app_v2_filter_linked_stocks_response(request: Request, membership_kind: str) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        identity_param = f"{membership_kind}_identity_key"
        parent_identity_key = (
            normalize_filter_value(request.query_params.get(identity_param))
            or normalize_filter_value(request.query_params.get("identity_key"))
            or ""
        )
        view = normalize_filter_value(request.query_params.get("view")) or "matched"
        if view not in {"matched", "all"}:
            view = "matched"
        result = repo.fetch_app_filter_linked_stocks(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            membership_kind=membership_kind,
            parent_identity_key=parent_identity_key,
            limit=ui_v1_limit_from_request(request, 100, max_limit=500),
            view=view,
        )
        return JSONResponse(
            app_v2_filter_linked_stocks_model(
                principal,
                user=session_user_payload(session),
                membership_kind=membership_kind,
                parent_identity_key=parent_identity_key,
                result=result,
            )
        )

    def app_v2_membership_response(request: Request, entity_type: str, identity_key: str) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        result = repo.fetch_app_membership_stocks(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            entity_type=entity_type,
            identity_key=identity_key,
            limit=ui_v1_limit_from_request(request, 500, max_limit=500),
        )
        return JSONResponse(
            app_v2_membership_drilldown_model(
                principal,
                user=session_user_payload(session),
                entity_type=entity_type,
                identity_key=identity_key,
                result=result,
            )
        )

    def app_v2_monitor_response(request: Request, asset_kind: str | None) -> JSONResponse:
        session = current_session(request, repo)
        if session is None:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return JSONResponse({"ok": False, "error": "principal_scope_unavailable"}, status_code=403)
        result = repo.fetch_app_monitor_items(
            principal_id=int(principal["principal_id"]),
            principal_type=str(principal["principal_type"]),
            user_id=session.user_id,
            asset_kind=asset_kind,
            limit=500,
            monitor_status=app_v2_monitor_status_from_request(request),
            for_trade_date=str(request.query_params.get("for_trade_date") or "").strip(),
        )
        return JSONResponse(
            app_v2_monitor_model(
                principal,
                user=session_user_payload(session),
                result=result,
                selected_asset_kind=asset_kind,
            )
        )

    def build_app_page_data(
        page_key: str,
        session: AuthSession,
        principal: dict[str, Any],
        *,
        app_filters: dict[str, Any] | None = None,
        app_show_all: bool = False,
    ) -> dict[str, Any]:
        user = session_user_payload(session)
        if page_key in {"home", "dashboard"}:
            return build_app_dashboard_data(session, principal)
        if page_key == "account":
            account, snapshot = app_account_sources(repo, principal)
            return app_account_model(principal, user=user, account=account, cash_snapshot=snapshot)
        if page_key == "signals":
            filters = app_signal_filters_with_trade_date_defaults(dict(app_filters or {}), repo.fetch_app_signal_scope_metadata(
                principal_id=int(principal["principal_id"]),
                principal_type=str(principal["principal_type"]),
                user_id=session.user_id,
            ), enforce_trading_session=True)
            scope_metadata = repo.fetch_app_signal_scope_metadata(
                principal_id=int(principal["principal_id"]),
                principal_type=str(principal["principal_type"]),
                user_id=session.user_id,
            )
            scope_metadata = app_signal_scope_metadata_for_filters(scope_metadata, filters)
            rows = repo.fetch_app_signals(
                principal_id=int(principal["principal_id"]),
                principal_type=str(principal["principal_type"]),
                user_id=session.user_id,
                filters=filters,
                limit=web_config.ui_signal_limit,
            )
            return app_signals_model(principal, user=user, rows=rows, filters=filters, scope_metadata=scope_metadata)
        if page_key == "messages":
            scope_metadata = repo.fetch_app_signal_scope_metadata(
                principal_id=int(principal["principal_id"]),
                principal_type=str(principal["principal_type"]),
                user_id=session.user_id,
            )
            filters = app_signal_filters_with_trade_date_defaults(dict(app_filters or {}), scope_metadata, enforce_trading_session=True)
            scope_metadata = app_signal_scope_metadata_for_filters(scope_metadata, filters)
            rows = repo.fetch_app_signals(
                principal_id=int(principal["principal_id"]),
                principal_type=str(principal["principal_type"]),
                user_id=session.user_id,
                filters=filters,
                limit=web_config.ui_signal_limit,
            )
            return build_app_v2_message_dashboard(
                principal,
                user=user,
                rows=rows,
                filters=filters,
                scope_metadata=scope_metadata,
                limit=web_config.ui_signal_limit,
            )
        if page_key == "buy-messages":
            return build_app_v2_buy_messages_data(session, principal)
        if page_key == "realtime-scope":
            result = repo.fetch_app_realtime_scope(
                principal_id=int(principal["principal_id"]),
                principal_type=str(principal["principal_type"]),
                user_id=session.user_id,
            )
            return app_realtime_scope_model(principal, user=user, result=result)
        if page_key in APP_FILTER_CENTER_ASSET_BY_PAGE_KEY:
            asset_kind = APP_FILTER_CENTER_ASSET_BY_PAGE_KEY[page_key]
            filters = {key: value for key, value in (app_filters or {}).items() if value}
            date_policy = app_v2_filter_trade_date_policy(session, principal, asset_kind, filters)
            if date_policy["blocked"]:
                filters["for_trade_date"] = date_policy["effective_trade_date"]
            selected_result = repo.fetch_app_filter_items(
                principal_id=int(principal["principal_id"]),
                principal_type=str(principal["principal_type"]),
                user_id=session.user_id,
                asset_kind=asset_kind,
                filters=filters,
                limit=(
                    APP_V2_FILTER_PAGE_MAX_ROWS
                    if app_show_all
                    else app_v2_filter_default_limit(asset_kind)
                ),
                include_all_fields=True,
            )
            if date_policy["blocked"]:
                selected_result["date_policy_blocker"] = date_policy["blocker"]
                selected_result["date_policy_message"] = date_policy["message"]
            empty_result = {"cache_ready": False, "items": []}
            filter_results = {
                "index": empty_result,
                "board": empty_result,
                "stock": empty_result,
                asset_kind: selected_result,
            }
            return app_v2_filter_center_model(
                principal,
                user=user,
                stock_result=filter_results["stock"],
                board_result=filter_results["board"],
                index_result=filter_results["index"],
                selected_asset_kind=asset_kind,
                filters=filters,
                show_all=app_show_all,
            )
        if page_key in APP_MONITOR_ASSET_BY_PAGE_KEY:
            asset_kind = APP_MONITOR_ASSET_BY_PAGE_KEY[page_key]
            monitor_status = app_v2_monitor_status_filter((app_filters or {}).get("monitor_status"))
            result = repo.fetch_app_monitor_items(
                principal_id=int(principal["principal_id"]),
                principal_type=str(principal["principal_type"]),
                user_id=session.user_id,
                asset_kind=asset_kind,
                limit=500,
                monitor_status=monitor_status,
                for_trade_date=str((app_filters or {}).get("for_trade_date") or "").strip(),
            )
            return app_v2_monitor_model(principal, user=user, result=result, selected_asset_kind=asset_kind)
        if page_key == "status-monitor":
            rows = repo.fetch_app_signals(
                principal_id=int(principal["principal_id"]),
                principal_type=str(principal["principal_type"]),
                user_id=session.user_id,
                filters={},
                limit=web_config.ui_signal_limit,
            )
            return app_status_monitor_model(principal, user=user, rows=rows, filters={})
        if page_key == "watchlist":
            rows = repo.fetch_app_signals(
                principal_id=int(principal["principal_id"]),
                principal_type=str(principal["principal_type"]),
                user_id=session.user_id,
                filters={},
                limit=web_config.ui_signal_limit,
            )
            return app_watchlist_model(principal, user=user, rows=rows)
        if page_key == "proposals":
            return app_locked_future_module_model(
                principal, user=user, module_key="proposals", component="B Track Proposals"
            )
        if page_key == "portfolio":
            return app_locked_future_module_model(
                principal, user=user, module_key="portfolio", component="B Track Portfolio"
            )
        if page_key == "pnl":
            return app_locked_future_module_model(principal, user=user, module_key="pnl", component="B Track PnL")
        if page_key == "leaderboard":
            return app_leaderboard_model(principal, user=user)
        if page_key == "ai-users":
            return app_ai_users_model(principal, user=user)
        component = {
            "watchlist": "B Track Watchlist",
            "proposals": "B Track Proposals",
        }.get(page_key, "B Track Dashboard")
        return app_empty_planned_model(principal, user=user, component=component)

    @app.get("/n6/app", response_class=HTMLResponse)
    async def app_shell_home(request: Request) -> Response:
        return await app_shell_page(request, "home")

    @app.get("/n6/app/filter-center/{filter_page}", response_class=HTMLResponse)
    async def app_filter_center_page(request: Request, filter_page: str) -> Response:
        page_key = APP_FILTER_CENTER_PAGE_KEY_BY_SLUG.get(filter_page)
        if page_key is None:
            return HTMLResponse("not found", status_code=404)
        return await app_shell_page(request, page_key)

    @app.get("/n6/app/my-monitor/{monitor_page}", response_class=HTMLResponse)
    async def app_my_monitor_page(request: Request, monitor_page: str) -> Response:
        page_key = APP_MONITOR_PAGE_KEY_BY_SLUG.get(monitor_page)
        if page_key is None:
            return HTMLResponse("not found", status_code=404)
        return await app_shell_page(request, page_key)

    @app.get("/n6/app/{page_key}", response_class=HTMLResponse)
    async def app_shell_page(request: Request, page_key: str) -> Response:
        if page_key not in {
            "dashboard",
            "account",
            "watchlist",
            "signals",
            "messages",
            "buy-messages",
            "realtime-scope",
            "filter-center",
            "filter-center:indexes",
            "filter-center:boards",
            "filter-center:stocks",
            "my-monitor",
            "my-monitor:stocks",
            "my-monitor:boards",
            "my-monitor:indexes",
            "status-monitor",
            "proposals",
            "portfolio",
            "pnl",
            "ai-users",
            "leaderboard",
            "home",
        }:
            return HTMLResponse("not found", status_code=404)
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse(b_track_login_location(request), status_code=302)
        principal = resolve_app_principal(session, repo)
        if principal is None:
            return HTMLResponse("principal_scope_unavailable", status_code=403)
        is_filter_center_page = page_key in APP_FILTER_CENTER_ASSET_BY_PAGE_KEY
        is_monitor_page = page_key in APP_MONITOR_ASSET_BY_PAGE_KEY
        data = build_app_page_data(
            page_key,
            session,
            principal,
            app_filters=app_v2_filter_filters_from_request(request)
            if is_filter_center_page
            else app_v2_monitor_filters_from_request(request)
            if is_monitor_page
            else ui_v1_filters_from_request(request)
            if page_key in {"signals", "messages"}
            else None,
            app_show_all=query_param_enabled(request, "show_all") if is_filter_center_page else False,
        )
        display_page_key = (
            "filter-center"
            if page_key.startswith("filter-center:")
            else "my-monitor"
            if is_monitor_page
            else page_key
        )
        return templates.TemplateResponse(
            request,
            "n6_app_shell.html",
            {
                "request": request,
                "user": session_user_payload(session),
                "page": app_page_model(display_page_key, principal, user=session_user_payload(session), data=data),
            },
        )

    @app.get("/n6/", response_class=HTMLResponse)
    async def home(request: Request) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        return RedirectResponse(a_track_default_location(session), status_code=303)

    @app.get("/n6/portfolio", response_class=HTMLResponse)
    async def portfolio(request: Request) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        return RedirectResponse(a_track_default_location(session), status_code=303)

    @app.get("/n6/notifications", response_class=HTMLResponse)
    async def notifications(request: Request) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        return RedirectResponse(a_track_default_location(session), status_code=303)

    @app.get("/n6/action-events", response_class=HTMLResponse)
    async def action_events(request: Request) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        dashboard = repo.fetch_message_dashboard(web_config.action_event_limit)
        rows = dashboard.get("messages") or []
        filters = ui_v1_filters_from_request(request)
        limit = ui_v1_limit_from_request(request, 100)
        offset = ui_v1_offset_from_request(request)
        source_user_id = signal_source_user_id(session, web_config)
        signal_rows = repo.fetch_ui_v1_signals(source_user_id, filters, limit, offset)
        signal_page = signal_list_model(
            signal_rows,
            filters=filters,
            pagination={
                "total_count": repo.count_ui_v1_signals(source_user_id, {}),
                "filtered_count": repo.count_ui_v1_signals(source_user_id, filters),
                "limit": limit,
                "offset": offset,
            },
            statistics=repo.fetch_ui_v1_signal_statistics(source_user_id),
        )
        lineage_stats = lineage_stats_model(repo.fetch_ui_v1_lineage_stats(source_user_id))
        virtual_account = repo.fetch_ui_v1_virtual_account(session.user_id)
        cash_snapshot = repo.fetch_ui_v1_cash_snapshot(session.user_id)
        return templates.TemplateResponse(
            request,
            "n6_action_events.html",
            {
                "request": request,
                "user": session_user_payload(session),
                "nav": nav_context(session, "action_events"),
                "events": [action_event_view(row) for row in rows],
                "summary": summarize_action_events(rows),
                "dashboard": message_dashboard_view(dashboard),
                "signal_page": signal_page,
                "lineage_stats": lineage_stats,
                "virtual_account_summary": virtual_account_summary_view(virtual_account, cash_snapshot),
            },
        )

    @app.get("/n6/status-monitor", response_class=HTMLResponse)
    async def status_monitor(request: Request) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        if session.role != "admin":
            return HTMLResponse("forbidden", status_code=403)
        filters = status_monitor_filters_from_request(request)
        limit = ui_v1_limit_from_request(request, 100)
        offset = ui_v1_offset_from_request(request)
        monitor = status_monitor_model(
            repo.fetch_ui_v1_status_monitor(
                signal_source_user_id(session, web_config),
                filters,
                limit,
                offset,
            ),
            filters=filters,
        )
        return templates.TemplateResponse(
            request,
            "n6_status_monitor.html",
            {
                "request": request,
                "user": session_user_payload(session),
                "nav": nav_context(session, "status_monitor"),
                "monitor": monitor,
            },
        )

    @app.get("/n6/n3-messages", response_class=HTMLResponse)
    async def n3_messages(request: Request) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        if session.role != "admin":
            return HTMLResponse("forbidden", status_code=403)
        include_all = query_param_enabled(request, "show_all")
        limit = ui_v1_limit_from_request(request, N3_MESSAGE_DEFAULT_LIMIT, max_limit=5000)
        n3_page = n3_messages_model(
            repo.fetch_ui_v1_n3_messages(
                filters=raw_message_filters_from_request(request),
                limit=limit,
                include_all=include_all,
            )
        )
        return templates.TemplateResponse(
            request,
            "n6_n3_messages.html",
            {
                "request": request,
                "user": session_user_payload(session),
                "nav": nav_context(session, "n3_messages"),
                "n3_page": n3_page,
            },
        )

    @app.get("/n6/n4-messages", response_class=HTMLResponse)
    async def n4_messages(request: Request) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        if session.role != "admin":
            return HTMLResponse("forbidden", status_code=403)
        include_all = query_param_enabled(request, "show_all")
        limit = ui_v1_limit_from_request(request, N4_MESSAGE_DEFAULT_LIMIT, max_limit=5000)
        n4_page = n4_messages_model(
            repo.fetch_ui_v1_n4_messages(
                filters=raw_message_filters_from_request(request),
                limit=limit,
                include_all=include_all,
            )
        )
        return templates.TemplateResponse(
            request,
            "n6_n4_messages.html",
            {
                "request": request,
                "user": session_user_payload(session),
                "nav": nav_context(session, "n4_messages"),
                "n4_page": n4_page,
            },
        )

    @app.get("/n6/n5-messages", response_class=HTMLResponse)
    async def n5_messages(request: Request) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        if session.role != "admin":
            return HTMLResponse("forbidden", status_code=403)
        include_all = query_param_enabled(request, "show_all")
        limit = ui_v1_limit_from_request(request, N5_MESSAGE_DEFAULT_LIMIT, max_limit=5000)
        n5_page = n5_messages_model(
            repo.fetch_ui_v1_n5_messages(
                filters=raw_message_filters_from_request(request),
                limit=limit,
                include_all=include_all,
            )
        )
        return templates.TemplateResponse(
            request,
            "n6_n5_messages.html",
            {
                "request": request,
                "user": session_user_payload(session),
                "nav": nav_context(session, "n5_messages"),
                "n5_page": n5_page,
            },
        )

    @app.get("/n6/n5-actions", response_class=HTMLResponse)
    async def n5_actions(request: Request) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        if session.role != "admin":
            return HTMLResponse("forbidden", status_code=403)
        limit = ui_v1_limit_from_request(request, N5_MESSAGE_DEFAULT_LIMIT, max_limit=5000)
        n5_actions_page = repo.fetch_ui_v1_n5_actions(
            filters=n5_action_filters_from_request(request),
            limit=limit,
        )
        return templates.TemplateResponse(
            request,
            "n6_n5_actions.html",
            {
                "request": request,
                "user": session_user_payload(session),
                "nav": nav_context(session, "n5_actions"),
                "n5_actions_page": n5_actions_page,
            },
        )

    @app.get("/n6/b-track/buy-signals", response_class=HTMLResponse)
    async def b_track_buy_signals_page(request: Request) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        if session.role != "admin":
            return HTMLResponse("forbidden", status_code=403)
        limit = ui_v1_limit_from_request(request, N5_MESSAGE_DEFAULT_LIMIT, max_limit=5000)
        buy_signals_page = repo.fetch_b_track_buy_signals(
            filters=b_track_buy_signal_filters_from_request(request),
            limit=limit,
        )
        return templates.TemplateResponse(
            request,
            "n6_b_track_buy_signals.html",
            {
                "request": request,
                "user": session_user_payload(session),
                "nav": nav_context(session, "b_track_buy_signals"),
                "buy_signals_page": buy_signals_page,
            },
        )

    @app.get("/n6/input-messages", response_class=HTMLResponse)
    async def input_messages(request: Request) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        if session.role != "admin":
            return HTMLResponse("forbidden", status_code=403)
        include_all = query_param_enabled(request, "show_all")
        limit = ui_v1_limit_from_request(request, N6_INPUT_MESSAGE_DEFAULT_LIMIT, max_limit=5000)
        input_page = input_messages_model(
            repo.fetch_ui_v1_input_messages(
                filters=raw_message_filters_from_request(request),
                limit=limit,
                include_all=include_all,
            )
        )
        return templates.TemplateResponse(
            request,
            "n6_input_messages.html",
            {
                "request": request,
                "user": session_user_payload(session),
                "nav": nav_context(session, "input_messages"),
                "input_page": input_page,
            },
        )

    @app.get("/n6/post-close-fastlane-status", response_class=HTMLResponse)
    async def post_close_fastlane_status(request: Request) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        if session.role != "admin":
            return HTMLResponse("forbidden", status_code=403)
        status_page = post_close_fastlane_status_model(
            read_post_close_fastlane_status(
                docs_root=web_config.post_close_fastlane_docs_root,
                for_trade_date=request.query_params.get("for_trade_date"),
            )
        )
        return templates.TemplateResponse(
            request,
            "n6_post_close_fastlane_status.html",
            {
                "request": request,
                "user": session_user_payload(session),
                "nav": nav_context(session, "post_close_fastlane_status"),
                "status_page": status_page,
            },
        )

    @app.get("/n6/rag", response_class=HTMLResponse)
    async def rag_search(request: Request) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        if session.role != "admin":
            return HTMLResponse("forbidden", status_code=403)
        limit = ui_v1_limit_from_request(request, 8, max_limit=20)
        rag_page = rag_search_model(
            read_rag_status_answer(
                docs_root=web_config.rag_docs_root,
                sql_root=web_config.rag_sql_root,
                query=str(request.query_params.get("q") or ""),
                limit=limit,
                layer_role=request.query_params.get("layer_role"),
                trade_date=request.query_params.get("trade_date"),
                artifact_type=request.query_params.get("artifact_type"),
            )
        )
        return templates.TemplateResponse(
            request,
            "n6_rag.html",
            {
                "request": request,
                "user": session_user_payload(session),
                "nav": nav_context(session, "rag"),
                "rag_page": rag_page,
            },
        )

    @app.get("/n6/archive-status", response_class=HTMLResponse)
    async def archive_status(request: Request) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        if session.role != "admin":
            return HTMLResponse("forbidden", status_code=403)
        archive_page = runtime_archive_status_model(
            read_runtime_archive_status(
                docs_root=web_config.runtime_archive_docs_root,
                archive_root=web_config.runtime_archive_root,
                trade_date=request.query_params.get("trade_date"),
            )
        )
        return templates.TemplateResponse(
            request,
            "n6_archive_status.html",
            {
                "request": request,
                "user": session_user_payload(session),
                "nav": nav_context(session, "archive_status"),
                "archive_page": archive_page,
            },
        )

    @app.get("/n6/fastlane-status", response_class=HTMLResponse)
    async def post_close_fastlane_status_alias(request: Request) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        if session.role != "admin":
            return HTMLResponse("forbidden", status_code=403)
        return RedirectResponse("/n6/post-close-fastlane-status", status_code=303)

    @app.get("/n6/admin/n5-messages", response_class=HTMLResponse)
    async def admin_n5_messages_alias(request: Request) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        if session.role != "admin":
            return HTMLResponse("forbidden", status_code=403)
        return RedirectResponse("/n6/n5-messages", status_code=303)

    @app.get("/n6/n2-condition-basis", response_class=HTMLResponse)
    async def n2_condition_basis_default(request: Request) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        return RedirectResponse("/n6/n2-condition-basis/index", status_code=303)

    @app.get("/n6/n2-condition-basis/export-latest.xlsx")
    async def n2_condition_basis_export_latest(request: Request) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        if session.role != "admin":
            return HTMLResponse("forbidden", status_code=403)
        data = repo.fetch_ui_v1_n2_condition_basis_latest_export()
        return n2_condition_basis_latest_export_response(data)

    @app.get("/n6/n2-condition-basis/{asset_kind}", response_class=HTMLResponse)
    async def n2_condition_basis(request: Request, asset_kind: str) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        if session.role != "admin":
            return HTMLResponse("forbidden", status_code=403)
        asset_kind = str(asset_kind or "").strip().lower()
        if asset_kind not in N2_CONDITION_BASIS_ASSET_META:
            return HTMLResponse("not found", status_code=404)
        include_all = query_param_enabled(request, "show_all")
        limit = ui_v1_limit_from_request(request, N2_CONDITION_BASIS_DEFAULT_LIMIT, max_limit=5000)
        n2_page = n2_condition_basis_model(
            repo.fetch_ui_v1_n2_condition_basis(
                asset_kind=asset_kind,
                filters=n2_condition_basis_filters_from_request(request),
                limit=limit,
                include_all=include_all,
            )
        )
        return templates.TemplateResponse(
            request,
            "n6_n2_condition_basis.html",
            {
                "request": request,
                "user": session_user_payload(session),
                "nav": nav_context(session, "n2_condition_basis"),
                "n2_page": n2_page,
            },
        )

    @app.get("/n6/admin/account", response_class=HTMLResponse)
    async def admin_account(request: Request) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        if session.role != "admin":
            return HTMLResponse("forbidden", status_code=403)
        account = repo.fetch_ui_v1_virtual_account(session.user_id)
        snapshot = repo.fetch_ui_v1_cash_snapshot(session.user_id)
        ledger = repo.fetch_ui_v1_cash_ledger(session.user_id, 20)
        return templates.TemplateResponse(
            request,
            "n6_admin_account.html",
            {
                "request": request,
                "user": session_user_payload(session),
                "nav": nav_context(session, "admin_account"),
                "account": virtual_account_view(account),
                "cash_snapshot": virtual_cash_snapshot_view(snapshot),
                "cash_ledger": [virtual_cash_ledger_view(row) for row in ledger],
                "safety": [
                    "READ ONLY",
                    "NO ORDER",
                    "NO TRADE",
                    "NO POSITION UPDATE",
                    "NO REAL TRADE",
                    "NOT INVESTMENT ADVICE",
                ],
            },
        )

    @app.get("/n6/admin/users", response_class=HTMLResponse)
    async def admin_users(request: Request) -> Response:
        session = current_session(request, repo)
        if session is None:
            return RedirectResponse("/n6/login", status_code=303)
        if session.role != "admin":
            return HTMLResponse("forbidden", status_code=403)
        return templates.TemplateResponse(
            request,
            "n6_admin_users.html",
            {
                "request": request,
                "user": session_user_payload(session),
                "nav": nav_context(session, "admin_users"),
                "users": [user_view(row) for row in repo.fetch_users_for_admin()],
            },
        )

    return app


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_session_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def safe_b_track_next(value: Any) -> str | None:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    parsed = urlsplit(raw_value)
    if parsed.scheme or parsed.netloc:
        return None
    path = parsed.path or ""
    if path != DEFAULT_B_TRACK_ENTRY and not path.startswith(f"{DEFAULT_B_TRACK_ENTRY}/"):
        return None
    return urlunsplit(("", "", path, parsed.query, ""))


def login_success_location(user: UserAccount, requested_next: Any) -> str:
    safe_next = safe_b_track_next(requested_next)
    if safe_next:
        return safe_next
    if user.role == "admin":
        return DEFAULT_A_TRACK_ADMIN_ENTRY
    return DEFAULT_B_TRACK_ENTRY


def a_track_default_location(session: AuthSession) -> str:
    if session.role == "admin":
        return DEFAULT_A_TRACK_ADMIN_ENTRY
    return DEFAULT_B_TRACK_ENTRY


def b_track_login_location(request: Request) -> str:
    target = request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"
    safe_next = safe_b_track_next(target) or DEFAULT_B_TRACK_ENTRY
    return f"/n6/login?next={quote(safe_next, safe='/')}"


async def read_login_payload(request: Request) -> dict[str, str]:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[0] if values else "" for key, values in parsed.items()}


def verify_password(password: str, password_hash: str, password_hash_algo: str) -> bool:
    if not password or not password_hash:
        return False
    if password_hash_algo == "argon2id":
        try:
            from argon2 import PasswordHasher
            from argon2.exceptions import InvalidHashError, VerifyMismatchError, VerificationError
            from argon2.low_level import Type
        except ImportError:
            return False
        try:
            return PasswordHasher(type=Type.ID).verify(password_hash, password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False
    if password_hash_algo == "bcrypt":
        try:
            import bcrypt
        except ImportError:
            return False
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except ValueError:
            return False
    return False


def current_session(request: Request, repository: N6UserRepository) -> AuthSession | None:
    raw_token = request.cookies.get(COOKIE_NAME)
    if not raw_token:
        return None
    session = repository.fetch_session(hash_session_token(raw_token))
    if session is None:
        return None
    now = utc_now()
    if session.status != "active" or session.revoked_at is not None or ensure_aware(session.expires_at) <= now:
        return None
    return session


def session_user_payload(session: AuthSession) -> dict[str, Any]:
    return {
        "user_id": session.user_id,
        "login_name": session.login_name,
        "display_name": session.display_name,
        "role": session.role,
        "status": session.status,
        "expires_at": ensure_aware(session.expires_at).isoformat(),
    }


def resolve_app_principal(session: AuthSession, repository: N6UserRepository) -> dict[str, Any] | None:
    principals = repository.fetch_app_principals(session.user_id)
    if not principals and session.role == "user":
        return session_scoped_human_principal(session)
    if len(principals) != 1:
        return None
    principal = principals[0]
    if str(principal.get("principal_status") or "") != "active":
        return None
    if str(principal.get("principal_type") or "") not in {"admin", "human_user", "ai_user"}:
        return None
    return principal


def session_scoped_human_principal(session: AuthSession) -> dict[str, Any]:
    return {
        "principal_id": session.user_id,
        "principal_type": "human_user",
        "owner_user_id": session.user_id,
        "principal_status": "active",
        "display_name": session.display_name or session.login_name,
        "principal_source": "session_scope",
    }


def app_account_sources(
    repository: N6UserRepository,
    principal: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    account = repository.fetch_app_virtual_account(
        int(principal["principal_id"]),
        str(principal["principal_type"]),
    )
    if not account:
        return None, None
    snapshot = repository.fetch_app_cash_snapshot(int(account["virtual_account_id"]))
    return account, snapshot


def normalize_login_name(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def normalize_filter_value(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def first_virtual_buy_value(source: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = source.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text != "—":
            return text
    return None


def normalize_virtual_buy_date(value: Any) -> str | None:
    text = normalize_filter_value(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def virtual_buy_rejected_response(reason: str, idempotency_key: str | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "rejected",
        "order_id": None,
        "trade_id": None,
        "position_id": None,
        "idempotency_key": idempotency_key,
        "rejected_reason": reason,
    }


def virtual_buy_result_response(result: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "status": result.status,
        "order_id": result.virtual_order_id,
        "trade_id": result.virtual_trade_id,
        "position_id": result.virtual_position_id,
        "idempotency_key": result.idempotency_key,
        "rejected_reason": None,
    }


def normalize_filter_values(values: Any) -> list[str]:
    if values is None:
        return []
    raw_values = values if isinstance(values, (list, tuple, set)) else [values]
    deduped: list[str] = []
    for raw_value in raw_values:
        value = normalize_filter_value(raw_value)
        if value and value not in deduped:
            deduped.append(value)
    return deduped


def normalize_filter_identity_values(values: Any) -> list[str]:
    if values is None:
        return []
    raw_values = values if isinstance(values, (list, tuple, set)) else [values]
    deduped: list[str] = []
    for raw_value in raw_values:
        for part in str(raw_value or "").split(","):
            value = normalize_filter_value(part)
            if value and value not in deduped:
                deduped.append(value)
    return deduped


def normalize_period_grade_filter_values(values: Any) -> list[str]:
    return [value for value in normalize_filter_values(values) if value in APP_V2_PERIOD_GRADE_FILTER_VALUES]


def normalize_time_field(value: Any) -> str:
    text = str(value or "").strip()
    return text if text in {"event_time", "created_at"} else "event_time"


def normalize_event_date(value: Any) -> str | None:
    text = normalize_filter_value(value)
    if not text:
        return None
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None
    return text


def ui_v1_filters_from_request(request: Request) -> dict[str, str | None]:
    return {
        "date_from": normalize_filter_value(request.query_params.get("date_from")),
        "date_to": normalize_filter_value(request.query_params.get("date_to")),
        "time_field": normalize_time_field(request.query_params.get("time_field")),
        "event_type": normalize_filter_value(request.query_params.get("event_type")),
        "trade_date": normalize_filter_value(request.query_params.get("trade_date")),
        "asset_kind": normalize_filter_value(request.query_params.get("asset_kind")),
        "direction": normalize_filter_value(request.query_params.get("direction")),
        "signal_type": normalize_filter_value(request.query_params.get("signal_type")),
        "action_state": normalize_filter_value(request.query_params.get("action_state")),
        "blocked_reason": normalize_filter_value(request.query_params.get("blocked_reason")),
        "q": normalize_filter_value(request.query_params.get("q")),
    }


def app_signal_filters_with_trade_date_defaults(
    filters: dict[str, Any],
    scope_metadata: dict[str, Any] | None,
    *,
    enforce_trading_session: bool = False,
) -> dict[str, Any]:
    output = dict(filters)
    output["asset_kind"] = app_message_asset_kind(output.get("asset_kind"))
    current_trade_date = current_app_signal_trade_date(scope_metadata)
    explicit_trade_date = normalize_filter_value(output.get("trade_date"))
    if explicit_trade_date:
        if enforce_trading_session:
            policy = n6_trade_date_access_policy(
                current_trade_date=current_trade_date,
                requested_trade_date=explicit_trade_date,
            )
            if policy["blocked"]:
                output["trade_date"] = policy["effective_trade_date"]
                output.pop("historical_projection_mode", None)
                output["date_policy_blocker"] = policy["blocker"]
                output["date_policy_message"] = policy["message"]
                return output
        output["trade_date"] = explicit_trade_date
        if current_trade_date and explicit_trade_date != current_trade_date:
            output["historical_projection_mode"] = True
        return output
    if current_trade_date:
        output["trade_date"] = current_trade_date
    return output


def app_signal_available_trade_dates(
    *,
    current_trade_date: str | None,
    projection_trade_dates: list[str] | tuple[str, ...] | None,
    selected_trade_date: str | None = None,
) -> list[str]:
    dates = {
        str(value)
        for value in list(projection_trade_dates or []) + [current_trade_date or "", selected_trade_date or ""]
        if str(value or "").isdigit() and len(str(value or "")) == 8
    }
    ordered = sorted(dates, reverse=True)
    if current_trade_date in ordered:
        ordered.remove(current_trade_date)
        ordered.insert(0, current_trade_date)
    return ordered


def app_signal_scope_metadata_for_filters(
    scope_metadata: dict[str, Any] | None,
    filters: dict[str, Any],
) -> dict[str, Any]:
    output = dict(scope_metadata or {})
    date_policy_message = normalize_filter_value(filters.get("date_policy_message"))
    date_policy_blocker = normalize_filter_value(filters.get("date_policy_blocker"))
    if filters.get("historical_projection_mode"):
        output["scope_mode"] = "historical_projection"
    if date_policy_blocker:
        output["date_policy_blocker"] = date_policy_blocker
    if date_policy_message:
        output["date_policy_message"] = date_policy_message
    output["available_trade_dates"] = app_signal_available_trade_dates(
        current_trade_date=current_app_signal_trade_date(output),
        projection_trade_dates=list(output.get("available_trade_dates") or []),
        selected_trade_date=normalize_filter_value(filters.get("trade_date")),
    )
    if date_policy_blocker:
        current_trade_date = current_app_signal_trade_date(output)
        output["available_trade_dates"] = [current_trade_date] if current_trade_date else []
    return output


def current_app_signal_trade_date(scope_metadata: dict[str, Any] | None) -> str | None:
    current_filter_batch = (scope_metadata or {}).get("current_filter_batch")
    if not isinstance(current_filter_batch, dict):
        return None
    for asset_kind in ("stock", "index", "board"):
        batch = current_filter_batch.get(asset_kind)
        if isinstance(batch, dict):
            trade_date = normalize_filter_value(batch.get("for_trade_date"))
            if trade_date:
                return trade_date
    return None


def raw_message_filters_from_request(request: Request) -> dict[str, str | None]:
    return {
        "event_date": normalize_event_date(request.query_params.get("event_date")),
        "source_layer": normalize_filter_value(request.query_params.get("source_layer")),
        "input_group": normalize_filter_value(request.query_params.get("input_group")),
        "event_type": normalize_filter_value(request.query_params.get("event_type")),
        "status": normalize_filter_value(request.query_params.get("status")),
        "asset_kind": normalize_filter_value(request.query_params.get("asset_kind")),
        "source_run_id": normalize_filter_value(request.query_params.get("source_run_id")),
        "q": normalize_filter_value(request.query_params.get("q")),
    }


def n5_action_filters_from_request(request: Request) -> dict[str, str | None]:
    return {
        "action_run_id": normalize_filter_value(request.query_params.get("action_run_id")),
        "source_run_id": normalize_filter_value(request.query_params.get("source_run_id")),
        "event_type": normalize_filter_value(request.query_params.get("event_type")),
        "status": normalize_filter_value(request.query_params.get("status")),
        "asset_kind": normalize_filter_value(request.query_params.get("asset_kind")),
        "action_state": normalize_filter_value(request.query_params.get("action_state")),
        "q": normalize_filter_value(request.query_params.get("q")),
    }


def normalize_b_track_buy_signal_action_type(value: Any) -> str:
    action_type = str(value or "buy").strip().lower()
    return action_type if action_type in B_TRACK_BUY_SIGNAL_ACTION_TYPES else "buy"


def b_track_buy_signal_filters_from_request(request: Request) -> dict[str, str | None]:
    return {
        "action_run_id": normalize_filter_value(request.query_params.get("action_run_id")),
        "action_type": normalize_b_track_buy_signal_action_type(request.query_params.get("action_type")),
        "q": normalize_filter_value(request.query_params.get("q")),
    }


def n2_source_trade_date_from_request(value: Any) -> str | None:
    text = normalize_filter_value(value)
    if not text:
        return None
    if len(text) == 8 and text.isdigit():
        return text
    try:
        return datetime.strptime(text, "%Y-%m-%d").strftime("%Y%m%d")
    except ValueError:
        return None


def n2_condition_basis_filters_from_request(request: Request) -> dict[str, str | None]:
    return {
        "source_trade_date": n2_source_trade_date_from_request(request.query_params.get("source_trade_date")),
        "condition_key": normalize_filter_value(request.query_params.get("condition_key")),
        "quality_status": normalize_filter_value(request.query_params.get("quality_status")),
        "q": normalize_filter_value(request.query_params.get("q")),
    }


def app_v2_filter_filters_from_request(request: Request) -> dict[str, Any]:
    period_filter_keys = (
        "year_overheat_level",
        "quarter_overheat_level",
        "month_overheat_level",
        "week_overheat_level",
        "day_overheat_level",
    )
    period_filters = {
        key: normalize_period_grade_filter_values(request.query_params.getlist(key))
        for key in period_filter_keys
    }
    source_identity_values = [
        *request.query_params.getlist("source_identity_keys"),
        *request.query_params.getlist("source_identity_key"),
    ]
    return {
        "asset_kind": normalize_filter_value(request.query_params.get("asset_kind")),
        "for_trade_date": normalize_filter_value(request.query_params.get("for_trade_date")),
        "source_asset_type": normalize_filter_value(request.query_params.get("source_asset_type")),
        "source_identity_keys": normalize_filter_identity_values(source_identity_values),
        "direction": normalize_filter_value(request.query_params.get("direction")),
        "board_type": normalize_filter_value(request.query_params.get("board_type")),
        "year_overheat_level": period_filters["year_overheat_level"],
        "quarter_overheat_level": period_filters["quarter_overheat_level"],
        "month_overheat_level": period_filters["month_overheat_level"],
        "week_overheat_level": period_filters["week_overheat_level"],
        "day_overheat_level": period_filters["day_overheat_level"],
        "condition_key": normalize_filter_value(request.query_params.get("condition_key")),
        "quality_status": normalize_filter_value(request.query_params.get("quality_status")),
        "last_signal_state": normalize_filter_value(request.query_params.get("last_signal_state")),
        "source_run_id": normalize_filter_value(request.query_params.get("source_run_id")),
        "projection_run_id": normalize_filter_value(request.query_params.get("projection_run_id")),
        "cache_run_id": normalize_filter_value(request.query_params.get("cache_run_id")),
        "q": normalize_filter_value(request.query_params.get("q")),
        "buy_expected_return_pct_min": app_v2_expected_return_value_text(
            request.query_params.get("buy_expected_return_pct_min")
        ),
        "level_up_score_recommendation": app_v2_level_up_recommendation_value(
            request.query_params.get("level_up_score_recommendation")
        ),
        "sort": normalize_filter_value(request.query_params.get("sort")),
        "sort_dir": normalize_filter_value(request.query_params.get("sort_dir")),
    }


def app_v2_monitor_status_filter(value: Any) -> str:
    text = str(value or "active").strip().lower()
    return text if text in APP_V2_MONITOR_STATUS_FILTERS else "active"


def app_v2_monitor_status_from_request(request: Request) -> str:
    return app_v2_monitor_status_filter(request.query_params.get("monitor_status"))


def app_v2_monitor_filters_from_request(request: Request) -> dict[str, Any]:
    return {
        "monitor_status": app_v2_monitor_status_from_request(request),
        "for_trade_date": str(request.query_params.get("for_trade_date") or "").strip(),
    }


def status_monitor_filters_from_request(request: Request) -> dict[str, str | None]:
    return {
        "trade_date": normalize_filter_value(request.query_params.get("trade_date")),
        "source_n4_run_id": normalize_filter_value(request.query_params.get("source_n4_run_id")),
        "source_n5_run_id": normalize_filter_value(request.query_params.get("source_n5_run_id")),
        "source_layer": normalize_filter_value(request.query_params.get("source_layer")),
        "status": normalize_filter_value(request.query_params.get("status")),
        "event_type": normalize_filter_value(request.query_params.get("event_type")),
        "action_event_type": normalize_filter_value(request.query_params.get("action_event_type")),
        "asset_kind": normalize_filter_value(request.query_params.get("asset_kind")),
        "direction": normalize_filter_value(request.query_params.get("direction")),
        "signal_type": normalize_filter_value(request.query_params.get("signal_type")),
        "outbox_status": normalize_filter_value(request.query_params.get("outbox_status")),
        "q": normalize_filter_value(request.query_params.get("q")),
    }


def ui_v1_limit_from_request(request: Request, default_limit: int, *, max_limit: int = 500) -> int:
    try:
        requested = int(request.query_params.get("limit") or default_limit)
    except ValueError:
        requested = default_limit
    return max(1, min(requested, max_limit))


def query_param_enabled(request: Request, key: str) -> bool:
    return str(request.query_params.get(key) or "").strip().lower() in {"1", "true", "yes", "all"}


def ui_v1_offset_from_request(request: Request) -> int:
    try:
        requested = int(request.query_params.get("offset") or 0)
    except ValueError:
        requested = 0
    return max(0, requested)


def cash_ledger_limit_from_request(request: Request) -> int:
    try:
        requested = int(request.query_params.get("limit") or 20)
    except ValueError:
        requested = 20
    return max(1, min(requested, 100))


def validate_user_create_payload(*, login_name: str, role: str) -> list[str]:
    blockers: list[str] = []
    if len(login_name) < 3:
        blockers.append("login_name_too_short")
    if not login_name.replace("_", "").replace("-", "").isalnum():
        blockers.append("login_name_invalid_chars")
    if role not in {"admin", "user"}:
        blockers.append("invalid_role")
    return blockers


def client_info_from_request(request: Request) -> dict[str, Any]:
    return {
        "user_agent": request.headers.get("user-agent", ""),
        "client_host": request.client.host if request.client else "",
        "n6_web_mvp": True,
    }


def ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def nav_context(session: AuthSession, active: str) -> dict[str, Any]:
    return {
        "active": active,
        "is_admin": session.role == "admin",
        "links": [
            {"key": "post_close_fastlane_status", "label": "收盘状态", "href": "/n6/post-close-fastlane-status"},
            {"key": "archive_status", "label": "归档状态", "href": "/n6/archive-status"},
            {"key": "n2_condition_basis", "label": "N2条件基础表", "href": "/n6/n2-condition-basis/index"},
            {"key": "n3_messages", "label": "N3消息", "href": "/n6/n3-messages"},
            {"key": "n4_messages", "label": "N4消息", "href": "/n6/n4-messages"},
            {"key": "input_messages", "label": "N6输入消息", "href": "/n6/input-messages"},
            {"key": "n5_messages", "label": "N5消息", "href": "/n6/n5-messages"},
            {"key": "n5_actions", "label": "N5动作", "href": "/n6/n5-actions"},
            {"key": "b_track_buy_signals", "label": "B轨买入信号", "href": "/n6/b-track/buy-signals"},
            {"key": "rag", "label": "RAG问答", "href": "/n6/rag"},
        ],
    }


def n2_condition_basis_asset_meta(asset_kind: str) -> dict[str, str]:
    key = str(asset_kind or "").strip().lower()
    meta = N2_CONDITION_BASIS_ASSET_META.get(key)
    if meta is None:
        raise ValueError("invalid_n2_condition_basis_asset_kind")
    return dict(meta)


def n2_condition_basis_asset_tabs() -> list[dict[str, str]]:
    return [
        {
            "asset_kind": asset_kind,
            "label": str(N2_CONDITION_BASIS_ASSET_META[asset_kind]["label"]),
            "href": f"/n6/n2-condition-basis/{asset_kind}",
            "source_table": str(N2_CONDITION_BASIS_ASSET_META[asset_kind]["source_table"]),
        }
        for asset_kind in N2_CONDITION_BASIS_ASSET_ORDER
    ]


def _n2_condition_basis_export_cell(item: dict[str, Any], path: str) -> Any:
    value: Any = item
    for part in path.split("."):
        if not isinstance(value, dict):
            return ""
        value = value.get(part)
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return value


def build_n2_condition_basis_latest_export(data: dict[str, Any]) -> bytes:
    workbook = Workbook()
    header_fill = PatternFill("solid", fgColor="E6F3F1")
    header_font = Font(bold=True, color="172124")
    latest_source_trade_date = str(data.get("latest_source_trade_date") or "unknown")
    assets = dict(data.get("assets") or {})
    for sheet_index, asset_kind in enumerate(N2_CONDITION_BASIS_ASSET_ORDER):
        meta = n2_condition_basis_asset_meta(asset_kind)
        worksheet = workbook.active if sheet_index == 0 else workbook.create_sheet()
        worksheet.title = str(meta["label"])
        headers = [label for _, label in N2_CONDITION_BASIS_EXPORT_COLUMNS]
        worksheet.append(headers)
        for cell in worksheet[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        asset_data = dict(assets.get(asset_kind) or {})
        for row in list(asset_data.get("items") or []):
            item = n2_condition_basis_item(row)
            worksheet.append([
                _n2_condition_basis_export_cell(item, key)
                for key, _ in N2_CONDITION_BASIS_EXPORT_COLUMNS
            ])
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        for column_number, (_, label) in enumerate(N2_CONDITION_BASIS_EXPORT_COLUMNS, start=1):
            width = 16
            if label in {"运行批次", "标识", "条件键", "原始行JSON", "原始JSON", "周期触发基准JSON", "目标价追溯JSON"}:
                width = 28
            if label in {"名称", "来源表", "质量原因"}:
                width = 20
            worksheet.column_dimensions[get_column_letter(column_number)].width = width
        worksheet.sheet_view.showGridLines = False
    properties = workbook.properties
    properties.title = f"{N2_CONDITION_BASIS_EXPORT_FILENAME_PREFIX}_{latest_source_trade_date}"
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def n2_condition_basis_latest_export_response(data: dict[str, Any]) -> Response:
    latest_source_trade_date = str(data.get("latest_source_trade_date") or "unknown")
    filename = f"{N2_CONDITION_BASIS_EXPORT_FILENAME_PREFIX}_{latest_source_trade_date}.xlsx"
    return Response(
        build_n2_condition_basis_latest_export(data),
        media_type=N2_CONDITION_BASIS_EXPORT_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
        },
    )


def signal_source_user_id(session: AuthSession, config: N6UserWebConfig) -> int:
    # The current MVP has one shadow projection owner; per-user projection execute is a later gate.
    return config.signal_source_user_id or session.user_id


def filter_profile_view(profile: dict[str, Any] | None) -> dict[str, bool]:
    source = profile or {}
    return {
        "enable_chase": bool(source.get("enable_chase", True)),
        "enable_ultra_short": bool(source.get("enable_ultra_short", True)),
        "enable_short": bool(source.get("enable_short", True)),
        "enable_mid": bool(source.get("enable_mid", True)),
        "enable_long": bool(source.get("enable_long", True)),
    }


def top_strategy_view(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {
            "code": "—",
            "name": "暂无指数策略",
            "display_title": "暂无推荐",
            "display_summary": "",
            "recommendation_key": "unclassified",
            "recommendation_label": "暂无推荐策略",
            "signal_types": "—",
            "transition_summary": "—",
            "buy_target_price": "—",
            "sell_target_price": "—",
        }
    strategy_type = strategy_type_from_transitions(row)
    return {
        "code": row.get("code") or "—",
        "name": row.get("name") or "—",
        "display_title": row.get("display_title") or "顶部推荐策略",
        "display_summary": row.get("display_summary") or "",
        "recommendation_key": strategy_type["key"],
        "recommendation_label": f"推荐{strategy_type['label']}",
        "signal_types": join_list(row.get("selected_signal_types")),
        "transition_summary": transition_summary(row),
        "buy_target_price": format_price(row.get("buy_target_price")),
        "sell_target_price": format_price(row.get("sell_target_price")),
    }


def board_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "board_code": row.get("board_code") or "—",
        "board_name": row.get("board_name") or "—",
        "display_title": row.get("display_title") or row.get("board_name") or "强势板块",
        "signal_types": join_list(row.get("selected_signal_types")),
        "transition_summary": transition_summary(row),
        "buy_target_price": format_price(row.get("buy_target_price")),
    }


def strong_board_views(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [board_view(row) for row in rows if is_strong_industry_board(row)]


def is_strong_industry_board(row: dict[str, Any]) -> bool:
    return (
        str(row.get("board_code") or "").startswith("881")
        and row.get("period_transition_y") == "volume_up"
        and row.get("period_transition_q") == "volume_up"
        and row.get("period_transition_m") == "volume_up"
    )


def card_view(row: dict[str, Any]) -> dict[str, Any]:
    strategy_type = strategy_type_from_transitions(row)
    return {
        "user_signal_card_id": row.get("user_signal_card_id"),
        "code": row.get("code") or "—",
        "name": row.get("name") or "—",
        "direction": row.get("direction") or "—",
        "direction_label": "买入" if row.get("direction") == "buy" else "卖出" if row.get("direction") == "sell" else "—",
        "signal_type": row.get("signal_type") or "—",
        "target_price": format_price(row.get("target_price")),
        "current_price": format_price(row.get("current_price")),
        "expected_return_pct": format_pct(row.get("expected_return_pct")),
        "board_code": row.get("board_code") or "—",
        "board_name": row.get("board_name") or "—",
        "title": row.get("title") or "",
        "strategy_key": strategy_type["key"],
        "strategy_label": strategy_type["label"],
    }


def resolve_selected_strategy_keys(
    request: Request,
    strategy: dict[str, Any],
    profile: dict[str, bool],
) -> set[str]:
    if request.query_params.get("filter_submitted") == "1":
        return {
            key
            for key in request.query_params.getlist("strategy")
            if key in VALID_STRATEGY_FILTER_KEYS
        }
    recommendation_key = str(strategy.get("recommendation_key") or "")
    if recommendation_key in VALID_STRATEGY_FILTER_KEYS:
        return {recommendation_key}
    return {
        str(option["key"])
        for option in STRATEGY_FILTER_OPTIONS
        if profile.get(str(option["profile_key"]), True)
    }


def strategy_filter_view(selected_keys: set[str]) -> list[dict[str, Any]]:
    return [
        {
            "key": option["key"],
            "label": option["label"],
            "checked": str(option["key"]) in selected_keys,
        }
        for option in STRATEGY_FILTER_OPTIONS
    ]


def filter_stock_card_views(cards: list[dict[str, Any]], selected_keys: set[str]) -> list[dict[str, Any]]:
    rows = []
    for row in cards:
        if row.get("asset_kind") != "stock":
            continue
        view = card_view(row)
        if view["strategy_key"] in selected_keys:
            rows.append(view)
    return rows


def notification_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets = [
        ("index", "指数信号", {"index_signal"}),
        ("board", "板块信号", {"board_signal"}),
        ("stock", "个股信号", {"stock_filter_signal"}),
        ("n5", "N5 action/hint 信号", {"n5_action_event", "n5_hint_event"}),
    ]
    grouped = []
    for key, label, sources in buckets:
        group_rows = [notification_view(row) for row in rows if row.get("notification_source") in sources]
        grouped.append({"key": key, "label": label, "rows": group_rows, "count": len(group_rows)})
    return grouped


def notification_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": row.get("title") or "—",
        "message": row.get("message") or "",
        "queue_status": row.get("queue_status") or "—",
        "channel": row.get("channel") or "—",
        "notification_source": row.get("notification_source") or "—",
        "identity": row.get("identity_key") or row.get("code") or "—",
        "name": row.get("name") or "",
        "queued_at": format_datetime(row.get("queued_at")),
    }


def action_event_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "outbox_id": row.get("outbox_id"),
        "event_id": row.get("event_id") or "—",
        "event_type": row.get("event_type") or "—",
        "source_layer": row.get("source_layer") or "—",
        "status": row.get("status") or "—",
        "trade_date": row.get("trade_date") or "—",
        "asset": f"{row.get('asset_kind') or '—'} / {row.get('identity_key') or '—'}",
        "direction": row.get("direction") or "—",
        "signal_type": row.get("signal_type") or "—",
        "action_state": row.get("action_state") or "—",
        "action_mark": row.get("action_mark") or "—",
        "condition_key": row.get("condition_key") or row.get("original_condition_key") or "—",
        "source_run_id": row.get("source_run_id") or "—",
        "event_time": format_datetime(row.get("event_time")),
        "created_at": format_datetime(row.get("created_at")),
    }


def summarize_action_events(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_event_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for row in rows:
        event_type = str(row.get("event_type") or "unknown")
        status = str(row.get("status") or "unknown")
        by_event_type[event_type] = by_event_type.get(event_type, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
    return {
        "total": len(rows),
        "by_event_type": [{"label": key, "count": value} for key, value in sorted(by_event_type.items())],
        "by_status": [{"label": key, "count": value} for key, value in sorted(by_status.items())],
    }


def message_dashboard_view(dashboard: dict[str, Any]) -> dict[str, Any]:
    admin = dashboard.get("admin_dashboard") or {}
    message = dashboard.get("message_dashboard") or {}
    return {
        "safety": [
            "只读预览",
            "不消费 outbox",
            "不触发真实通知/交易",
            "READ ONLY",
            "NO ORDER",
            "NO TRADE",
            "NO POSITION UPDATE",
            "NO REAL TRADE",
            "NOT INVESTMENT ADVICE",
        ],
        "metrics": [
            {
                "label": "今日 N4 TriggerMatched pending",
                "value": int(admin.get("today_n4_trigger_matched_pending") or 0),
            },
            {
                "label": "今日 N5 ActionBlocked",
                "value": int(admin.get("today_n5_action_blocked") or 0),
            },
            {
                "label": "今日 N5 ActionExecuted",
                "value": int(admin.get("today_n5_action_executed") or 0),
            },
            {
                "label": "N5 outbox pending",
                "value": int(admin.get("n5_outbox_pending") or 0),
            },
            {
                "label": "N6 queued_only",
                "value": int(admin.get("n6_queued_only") or 0),
            },
            {
                "label": "N6 ready preview",
                "value": int(admin.get("n6_ready_for_future_push") or 0),
            },
        ],
        "n6_shadow": [
            {"label": "projection", "value": int(admin.get("n6_shadow_projection_count") or 0)},
            {"label": "card", "value": int(admin.get("n6_shadow_card_count") or 0)},
            {"label": "queue", "value": int(admin.get("n6_shadow_queue_count") or 0)},
            {"label": "latest run", "value": admin.get("latest_projection_run_id") or "—"},
        ],
        "event_distribution": [
            {
                "label": f"{row.get('event_type') or '—'} / {row.get('status') or '—'}",
                "count": int(row.get("count") or 0),
            }
            for row in message.get("event_distribution", [])
        ],
        "blocked_reasons": [
            {
                "label": row.get("blocked_reason") or "unknown",
                "count": int(row.get("count") or 0),
            }
            for row in dashboard.get("blocked_reason_distribution", [])
        ],
        "recent_runs": [
            {
                "layer": row.get("layer") or "—",
                "run_id": row.get("run_id") or "—",
                "status": row.get("status") or "—",
                "created_at": format_datetime(row.get("created_at")),
                "finished_at": format_datetime(row.get("finished_at")),
            }
            for row in dashboard.get("recent_runs", [])
        ],
    }


def user_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": row.get("user_id"),
        "login_name": row.get("login_name") or "—",
        "display_name": row.get("display_name") or "—",
        "role": row.get("role") or "—",
        "status": row.get("status") or "—",
        "created_at": format_datetime(row.get("created_at")),
        "last_login_at": format_datetime(row.get("last_login_at")),
        "filter_profile_count": int(row.get("filter_profile_count") or 0),
        "sim_account_count": int(row.get("sim_account_count") or 0),
        "active_position_count": int(row.get("active_position_count") or 0),
    }


def virtual_account_summary_view(
    account: dict[str, Any] | None,
    cash_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    account_view = virtual_account_view(account)
    snapshot_view = virtual_cash_snapshot_view(cash_snapshot)
    return {
        "available": account is not None,
        "safety": [
            "READ ONLY",
            "NO ORDER",
            "NO TRADE",
            "NO POSITION UPDATE",
            "NO REAL TRADE",
            "NOT INVESTMENT ADVICE",
        ],
        "account_name": account_view["account_name"],
        "base_currency": account_view["base_currency"],
        "initial_cash": account_view["initial_cash"],
        "available_cash": snapshot_view["available_cash"],
        "frozen_cash": snapshot_view["frozen_cash"],
        "total_cash": snapshot_view["total_cash"],
        "quality_status": account_view["quality_status"],
        "seed_run_id": account_view["seed_run_id"],
    }


def virtual_account_view(row: dict[str, Any] | None) -> dict[str, Any]:
    source = row or {}
    return {
        "virtual_account_id": source.get("virtual_account_id") or "—",
        "principal_id": source.get("principal_id") or "—",
        "principal_type": source.get("principal_type") or "—",
        "account_name": source.get("account_name") or "—",
        "virtual_account_status": source.get("virtual_account_status") or "missing",
        "base_currency": source.get("base_currency") or "—",
        "initial_cash": format_money(source.get("initial_cash")),
        "current_cash_snapshot_id": source.get("current_cash_snapshot_id") or "—",
        "quality_status": source.get("quality_status") or "missing",
        "seed_run_id": source.get("run_id") or "—",
        "policy_version": source.get("policy_version") or "—",
        "policy_hash": source.get("policy_hash") or "—",
        "rollback_scope": source.get("rollback_scope") or "—",
        "created_at": format_datetime(source.get("created_at")),
        "updated_at": format_datetime(source.get("updated_at")),
    }


def virtual_cash_snapshot_view(row: dict[str, Any] | None) -> dict[str, Any]:
    source = row or {}
    return {
        "cash_snapshot_id": source.get("cash_snapshot_id") or "—",
        "virtual_account_id": source.get("virtual_account_id") or "—",
        "snapshot_time": format_datetime(source.get("snapshot_time")),
        "trade_date": source.get("trade_date") or "—",
        "available_cash": format_money(source.get("available_cash")),
        "frozen_cash": format_money(source.get("frozen_cash")),
        "total_cash": format_money(source.get("total_cash")),
        "currency": source.get("currency") or "—",
        "source_ledger_max_id": source.get("source_ledger_max_id") or "—",
        "snapshot_status": source.get("snapshot_status") or "missing",
        "quality_status": source.get("quality_status") or "missing",
        "run_id": source.get("run_id") or "—",
    }


def virtual_cash_ledger_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "cash_ledger_id": row.get("cash_ledger_id") or "—",
        "event_time": format_datetime(row.get("event_time")),
        "ledger_type": row.get("ledger_type") or "—",
        "amount": format_money(row.get("amount")),
        "currency": row.get("currency") or "—",
        "source_event_type": row.get("source_event_type") or "—",
        "source_event_id": row.get("source_event_id") or "—",
        "source_virtual_order_id": row.get("source_virtual_order_id") or "—",
        "source_virtual_trade_id": row.get("source_virtual_trade_id") or "—",
        "run_id": row.get("run_id") or "—",
        "quality_status": row.get("quality_status") or "—",
    }


def sim_account_view(row: dict[str, Any] | None) -> dict[str, Any]:
    source = row or {}
    return {
        "account_name": source.get("account_name") or DEFAULT_SIM_ACCOUNT_NAME,
        "initial_cash": format_decimal(source.get("initial_cash", DEFAULT_INITIAL_CASH), places=0),
        "cash_balance": format_decimal(source.get("cash_balance", DEFAULT_INITIAL_CASH), places=0),
        "frozen_cash": format_decimal(source.get("frozen_cash", 0), places=0),
        "settlement_mode": source.get("settlement_mode") or "T_PLUS_1",
        "account_status": source.get("account_status") or "shadow",
    }


def sim_position_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": row.get("code") or "—",
        "name": row.get("name") or "—",
        "total_qty": format_decimal(row.get("total_qty"), places=0),
        "available_qty": format_decimal(row.get("available_qty"), places=0),
        "t_plus_one_locked_qty": format_decimal(row.get("t_plus_one_locked_qty"), places=0),
        "avg_cost": format_price(row.get("avg_cost")),
        "last_price": format_price(row.get("last_price")),
        "market_value": format_decimal(row.get("market_value"), places=2),
        "unrealized_pnl": format_decimal(row.get("unrealized_pnl"), places=2),
    }


def summarize_card_counts(cards: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(cards),
        "stock": sum(1 for row in cards if row.get("asset_kind") == "stock"),
        "buy": sum(1 for row in cards if row.get("direction") == "buy"),
        "sell": sum(1 for row in cards if row.get("direction") == "sell"),
    }


def summarize_stock_row_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(rows),
        "stock": len(rows),
        "buy": sum(1 for row in rows if row.get("direction") == "buy"),
        "sell": sum(1 for row in rows if row.get("direction") == "sell"),
    }


def format_price(value: Any) -> str:
    return format_decimal(value, places=2)


def format_pct(value: Any) -> str:
    formatted = format_decimal(value, places=2)
    return "—" if formatted == "—" else f"{formatted}%"


def format_money(value: Any) -> str:
    if value is None:
        return "—"
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return "—"
    quantized = decimal_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{quantized:,.2f}"


def format_decimal(value: Any, *, places: int) -> str:
    if value is None:
        return "—"
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return "—"
    quantizer = Decimal("1").scaleb(-places)
    return f"{decimal_value.quantize(quantizer, rounding=ROUND_HALF_UP):f}"


def format_datetime(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return ensure_aware(value).astimezone(DISPLAY_TIMEZONE).strftime("%Y-%m-%d %H:%M")
    return str(value)


def join_list(value: Any) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        return value
    return " / ".join(str(item) for item in value)


def strategy_type_from_transitions(row: dict[str, Any]) -> dict[str, Any]:
    transitions = [
        row.get("period_transition_y"),
        row.get("period_transition_q"),
        row.get("period_transition_m"),
        row.get("period_transition_w"),
        row.get("period_transition_d"),
    ]
    volume_up = [value == "volume_up" for value in transitions]
    if volume_up == [True, True, True, True, True]:
        return {"key": "chase", "label": "追涨策略", "rank": 60}
    if volume_up == [True, True, True, True, False]:
        return {"key": "ultra_short", "label": "超短策略", "rank": 50}
    if volume_up == [True, True, True, False, False]:
        return {"key": "short", "label": "短线策略", "rank": 40}
    if volume_up == [True, True, False, False, False]:
        return {"key": "mid", "label": "中线策略", "rank": 30}
    if volume_up == [True, False, False, False, False] or volume_up == [False, False, False, False, False]:
        return {"key": "long", "label": "长线策略", "rank": 20}
    return {"key": "unclassified", "label": "未分级策略", "rank": 0}


def transition_summary(row: dict[str, Any]) -> str:
    values = [
        ("年", row.get("period_transition_y")),
        ("季", row.get("period_transition_q")),
        ("月", row.get("period_transition_m")),
        ("周", row.get("period_transition_w")),
        ("日", row.get("period_transition_d")),
    ]
    labels = {"volume_up": "放量上涨", "low_volume_up": "缩量上涨", "volume_down": "放量下跌", "low_volume_down": "缩量下跌", "flat": "平稳", "unknown": "未知"}
    return " / ".join(f"{name}:{labels.get(value, value or '—')}" for name, value in values)


app = create_app()


def main() -> None:
    import uvicorn

    host = os.environ.get("ASHARE_V3_N6_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("ASHARE_V3_N6_WEB_PORT", "8786"))
    uvicorn.run("ashare_v3.web.n6_user_app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
