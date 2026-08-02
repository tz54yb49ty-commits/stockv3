"""Read-only B-track N6 multi-user app shell models."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Any
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

from ashare_v3.web.n6_ui_v1 import (
    cash_summary_item,
    display_datetime,
    number_or_none,
    proposal_eligibility_model,
    signal_list_item,
    virtual_account_item,
)


APP_SCOPE = "n6_multi_user_app"
APP_SAFETY_LABELS = (
    "投影只读 · 虚拟交易不连接真实券商 · 不执行真实下单 · 不构成投资建议",
    "本页仅展示已审核的系统投影和证据链，不代表交易建议",
)
APP_FUTURE_MODULE_NOTICE = "该入口为未来功能预留，当前不会生成方案、订单、交易或持仓变化"
APP_DISCLAIMER = ["非实际业绩", "非投资建议", "不代表未来结果"]
AI_AGENT_PUBLIC_DISCLAIMER = [
    "仅为模拟账户和实验性 AI 决策展示",
    "不连接真实券商，不执行真实下单",
    "非投资建议，不代表未来结果",
]
APP_ALLOWED_SIGNAL_SOURCES = [
    "reviewed N6 projections",
    "reviewed signal cards",
    "principal-scoped N6 monitor preferences",
]
APP_FORBIDDEN_SIGNAL_SOURCES = [
    "raw K",
    "N1 raw facts",
    "direct live market",
    "N4 raw facts bypass",
    "N5 raw facts bypass",
    "condition_basis",
    "condition_pool",
    "minute_target_scope",
    "unreviewed outbox / raw facts",
]
SIGNAL_SSE_CONTRACT_VERSION = "n6-b-track-signal-sse-v1"
SIGNAL_SSE_ALLOWED_SOURCES = (
    "user_projection_run",
    "user_signal_projection",
    "user_signal_card",
)
POSTGRES_SIGNED_BIGINT_MAX = 9223372036854775807
APP_SIGNAL_BIGINT_ID_FIELDS = (
    "monitor_id",
    "principal_id",
    "user_id",
    "realtime_scope_id",
    "source_display_basis_id",
    "user_signal_projection_id",
    "user_signal_card_id",
    "source_condition_display_basis_id",
    "proposal_id",
    "source_signal_projection_id",
    "source_virtual_position_id",
    "virtual_account_id",
    "virtual_position_id",
    "virtual_position_lot_id",
    "virtual_order_id",
    "virtual_trade_id",
    "source_virtual_trade_id",
    "virtual_cash_snapshot_id",
    "virtual_cash_ledger_id",
    "virtual_quote_snapshot_id",
    "fill_quote_snapshot_id",
    "stop_loss_source_quote_snapshot_id",
    "ai_user_id",
    "ai_context_snapshot_id",
    "ai_decision_run_id",
    "ai_decision_id",
    "ai_daily_summary_id",
    "ai_strategy_evaluation_id",
    "source_virtual_trade_proposal_id",
    "strategy_id",
    "selection_revision_id",
    "strategy_match_projection_id",
    "strategy_observation_projection_id",
    "strategy_match_change_id",
)
PORTFOLIO_TIMEZONE = ZoneInfo("Asia/Shanghai")
PORTFOLIO_FRESH_SECONDS = Decimal("120")
SIGNAL_DISPLAY_TIMEZONE = ZoneInfo("Asia/Shanghai")
PORTFOLIO_ALLOWED_SOURCES = [
    "common_trade_calendar",
    "n6_principal",
    "n6_virtual_account",
    "n6_virtual_position",
    "n6_virtual_position_lot",
    "v_n6_virtual_quote_latest",
    "v_n6_stock_condition_display_basis",
    "v_n6_board_membership_fact",
]
PORTFOLIO_FORBIDDEN_SOURCES = [
    "N1-N5 raw facts",
    "existing N3 facts",
    "external market data",
    "Mootdx from web request",
]


def canonical_bigint_id(
    value: Any,
    *,
    field_name: str,
    required: bool = False,
) -> str | None:
    if field_name not in APP_SIGNAL_BIGINT_ID_FIELDS:
        raise ValueError("unsupported_bigint_id_field")
    if value is None:
        if required:
            raise ValueError(f"missing_{field_name}")
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f"invalid_{field_name}")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise ValueError(f"invalid_{field_name}")
        parsed = int(value)
    elif isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value):
        parsed = int(value)
    else:
        raise ValueError(f"invalid_{field_name}")
    if parsed < 1 or parsed > POSTGRES_SIGNED_BIGINT_MAX:
        raise ValueError(f"invalid_{field_name}")
    return str(parsed)


APP_SIGNAL_FROZEN_PROJECTION_FIELDS = (
    "condition_projection_context",
    "condition_projection_context_status",
    "condition_projection_context_trace",
    "projection_message_contract_version",
    "projection_message_contract_hash",
    "projection_message_status",
    "projection_message_not_ready_reasons",
    "trigger_price",
    "trigger_pct",
    "trigger_pct_status",
    "action_price",
    "action_pct",
    "action_pct_status",
    "target_price",
    "buy_expected_return_pct",
    "up_secondary_expected_return_pct",
    "sell_expected_return_pct",
    "up_reference_period",
    "down_reference_period",
    "primary_trigger_period",
    "all_trigger_periods",
    "score",
    "pe_core",
    "industry_status",
    "industry_provenance",
)
RETIRED_STRATEGY_CENTER_PRIVATE_FIELDS = frozenset(
    {
        "strategy_center_temporal_confluence",
        "strategy_match_projection_id",
        "strategy_observation_projection_id",
        "strategy_match_change_id",
        "selection_revision_id",
        "selected_package_keys",
        "selected_packages",
        "matched_packages",
        "observed_packages",
        "package_evidence",
        "confluence",
        "coherence_episode_key",
        "coherence_level",
        "coherence_span_trading_minutes",
        "evaluator_policy_hash",
        "freshness_status",
        "market_heat_evidence",
        "market_heat_state",
        "observation_reason",
        "strategy_version",
        "surface_kind",
    }
)
APP_V2_SAFETY_LABELS = (
    "投影只读 · 不连接真实券商 · 不执行真实下单 · 不构成投资建议 · principal scoped",
)
APP_V2_MESSAGE_DASHBOARD_SAFETY_LABELS = (
    "投影只读 · 不连接真实券商 · 不执行真实下单 · 不构成投资建议 · principal scoped",
)
APP_V2_BUY_MESSAGES_SAFETY_LABELS = (
    "投影只读 · 不连接真实券商 · 不执行真实下单 · 不构成投资建议 · principal scoped",
)
APP_V2_MESSAGE_EMPTY_STATES = {
    "no_effective_monitor": "当前没有有效监控对象，请先从筛选中心加入监控",
    "no_n6_user_messages": "当前有效监控对象暂无 N6 用户消息",
    "no_messages_for_trade_date": "该交易日没有 N6 历史消息",
    "waiting_projection": "等待 N6 projection 生成用户消息",
    "message_trade_date_missing": "存在消息缺少 trade_date，已从有效监控消息中排除",
    "current_filter_batch_not_ready": "当前筛选批次尚未准备完成",
}
APP_V2_ALLOWED_SOURCES = [
    "reviewed N6 projections",
    "reviewed signal cards",
    "v_n6_stock_condition_display_basis",
    "v_n6_index_condition_display_basis",
    "v_n6_board_condition_display_basis",
    "v_n6_index_membership_fact",
    "v_n6_board_membership_fact",
]
APP_V2_FORBIDDEN_SOURCES = [
    "raw K",
    "N1 raw facts",
    "N4 raw bypass",
    "N5 raw bypass",
    "condition_basis",
    "condition_pool",
    "minute_target_scope",
    "direct live market",
    "unreviewed outbox",
    "n6_stock_display_cache",
    "n6_index_display_cache",
    "n6_board_display_cache",
    "n6_display_stock_condition_cache",
    "n6_display_index_condition_cache",
    "n6_display_board_condition_cache",
    "n6_display_index_membership_cache",
    "n6_display_board_membership_cache",
    "stock_condition_display_basis",
    "index_condition_display_basis",
    "board_condition_display_basis",
]
APP_SIDE_EFFECTS = {
    "writes_database": False,
    "database_written": False,
    "outbox_consumed": False,
    "outbox_status_updates": 0,
    "outbox_status_updated": False,
    "proposal_generated": False,
    "order_generated": False,
    "trade_generated": False,
    "position_updated": False,
    "pnl_generated": False,
    "leaderboard_materialized": False,
    "delivery_triggered": False,
    "push_triggered": False,
    "voice_triggered": False,
    "mobile_triggered": False,
    "sim_written": False,
    "position_written": False,
    "real_trade_submitted": False,
}

APP_PAGE_LABELS = {
    "home": "B轨首页",
    "dashboard": "日常工作台",
    "guide": "新用户说明书",
    "account": "我的账户",
    "realtime-scope": "实时监控范围",
    "strategy-center": "策略中心",
    "trade-log": "买卖日志",
    "watchlist": "关注池",
    "signals": "我的监控消息列表",
    "messages": "我的监控消息总览",
    "buy-messages": "买入消息",
    "filter-center": "筛选中心",
    "my-monitor": "我的监控对象",
    "status-monitor": "触发状态",
    "proposals": "方案",
    "portfolio": "组合",
    "pnl": "收益",
    "ai-agent": "AI模拟投资员",
    "ai-users": "AI助手",
    "leaderboard": "排行榜",
}
APP_NAV_LABELS = {
    "dashboard": "首页",
    "account": "虚拟账户",
    "realtime-scope": "实时监控范围",
    "strategy-center": "策略中心",
    "trade-log": "买卖日志",
    "watchlist": "关注池",
    "signals": "消息列表",
    "messages": "卡片消息",
    "buy-messages": "买入消息",
    "filter-center": "筛选中心",
    "my-monitor": "监控对象",
    "status-monitor": "触发状态",
    "proposals": "方案",
    "portfolio": "组合",
    "pnl": "收益",
    "ai-agent": "AI投资员",
    "ai-users": "AI助手",
    "leaderboard": "排行榜",
}
APP_COMPONENT_LABELS = {
    "B Track Me": "我的身份",
    "B Track Dashboard": "B轨首页",
    "B Track Account": "我的账户",
    "B Track Signals": "我的监控消息列表",
    "B Track V2 Monitor Message Dashboard": "我的监控消息总览",
    "B Track V2 Monitor Message Groups": "消息分组",
    "B Track V2 Monitor Projection Status": "projection 状态",
    "B Track V2 Buy Messages": "买入消息",
    "B Track Signal Detail": "消息详情",
    "B Track Watchlist": "关注池",
    "B Track Realtime Scope": "实时监控范围",
    "B Track Strategy Center": "策略中心",
    "B Track V2 Filter Center": "筛选中心",
    "B Track V2 Stock Filter": "个股筛选",
    "B Track V2 Board Filter": "板块筛选",
    "B Track V2 Index Filter": "指数筛选",
    "B Track V2 Board Members": "板块成分股",
    "B Track V2 Index Members": "指数成分股",
    "B Track V2 Board Linked Stocks": "板块关联个股",
    "B Track V2 Index Linked Stocks": "指数关联个股",
    "B Track V2 My Monitor": "我的监控对象",
    "B Track Status Monitor": "触发状态",
    "B Track AI Agent": "AI模拟投资员",
    "B Track AI Users": "AI助手",
    "B Track Proposals": "方案",
    "B Track Portfolio": "组合",
    "B Track PnL": "收益",
    "B Track Leaderboard": "排行榜",
}
APP_SIGNAL_TAGS = (
    "市场动作确认成立 (ActionExecuted)",
    "市场动作未确认 (ActionBlocked)",
    "等待行情证据 (TriggerPendingMarketData)",
    "状态变化 (TriggerStateChanged)",
)
APP_MESSAGE_ASSET_KIND_ORDER = ("index", "board", "stock")
APP_DEFAULT_MESSAGE_ASSET_KIND = "stock"
APP_SIGNAL_ASSET_TAB_LABELS = {
    "index": "指数消息",
    "board": "板块消息",
    "stock": "个股消息",
}
APP_CARD_ASSET_TAB_LABELS = {
    "index": "指数卡片",
    "board": "板块卡片",
    "stock": "个股卡片",
}
DEFAULT_REALTIME_SCOPE_INDEXES = (
    {"asset_kind": "index", "identity_key": "index:SH:000001", "display_name": "上证指数"},
    {"asset_kind": "index", "identity_key": "index:SH:000016", "display_name": "上证50"},
    {"asset_kind": "index", "identity_key": "index:SH:000300", "display_name": "沪深300"},
    {"asset_kind": "index", "identity_key": "index:SH:000688", "display_name": "科创50"},
    {"asset_kind": "index", "identity_key": "index:SH:000852", "display_name": "中证1000"},
    {"asset_kind": "index", "identity_key": "index:SH:000905", "display_name": "中证500"},
    {"asset_kind": "index", "identity_key": "index:SZ:399001", "display_name": "深证成指"},
    {"asset_kind": "index", "identity_key": "index:SZ:399006", "display_name": "创业板指"},
    {"asset_kind": "index", "identity_key": "index:SZ:399303", "display_name": "国证2000"},
)
APP_EVENT_LABELS = {
    "ActionExecuted": "市场动作确认成立 (ActionExecuted)",
    "ActionBlocked": "市场动作未确认 (ActionBlocked)",
    "TriggerMatched": "触发成立 (TriggerMatched)",
    "TriggerPendingMarketData": "等待行情证据 (TriggerPendingMarketData)",
    "TriggerStateChanged": "状态变化 (TriggerStateChanged)",
    "ActionEligible": "动作待确认 (ActionEligible)",
    "ActionSkipped": "动作已跳过 (ActionSkipped)",
}
APP_STATE_LABELS = {
    "executed": "已确认",
    "blocked": "未确认",
    "eligible": "待确认",
    "skipped": "已跳过",
    "expired": "已过期",
    "active": "有效",
    "pending_market_data": "等待行情证据",
    "inactive": "已失效",
    "data_not_ready": "数据未准备",
    "ready": "已准备",
    "locked_planned": "未开放",
    "locked_empty": "未开放",
    "locked_readiness_only": "未开放",
    "readonly_shell": "只读壳",
    "readonly": "只读",
}
APP_DIRECTION_LABELS = {
    "buy": "买向观察",
    "sell": "卖向观察",
}
APP_BLOCKED_REASON_LABELS = {
    "price_confirmation_failed": "价格确认未通过",
    "amount_confirmation_failed": "成交额确认未通过",
    "metric_missing": "指标缺失",
    "unknown": "未知原因",
}
APP_ASSET_KIND_LABELS = {
    "stock": "个股",
    "index": "指数",
    "board": "板块",
}
APP_WATCHLIST_STATUS_LABELS = {
    "market_action_confirmed": "市场动作确认成立",
    "market_action_not_confirmed": "市场动作未确认",
    "pending_market_data": "等待行情证据",
    "state_changed": "状态变化",
}
CONDITION_CACHE_SOURCE_BY_ASSET = {
    "stock": "v_n6_stock_condition_display_basis",
    "index": "v_n6_index_condition_display_basis",
    "board": "v_n6_board_condition_display_basis",
}
V2_FILTER_SOURCE_BY_ASSET = {
    "stock": "v_n6_stock_condition_display_basis",
    "index": "v_n6_index_condition_display_basis",
    "board": "v_n6_board_condition_display_basis",
}
V2_FILTER_READ_SOURCE_BY_ASSET = {
    "stock": "v_n6_stock_condition_display_basis",
    "index": "v_n6_index_condition_display_basis",
    "board": "v_n6_board_condition_display_basis",
}
V2_MEMBERSHIP_SOURCE_BY_KIND = {
    "index": "v_n6_index_membership_fact",
    "board": "v_n6_board_membership_fact",
}
V2_MEMBERSHIP_READ_SOURCE_BY_KIND = {
    "index": "v_n6_index_membership_fact",
    "board": "v_n6_board_membership_fact",
}
V2_LINKED_STOCK_COMPONENT_BY_KIND = {
    "index": "B Track V2 Index Linked Stocks",
    "board": "B Track V2 Board Linked Stocks",
}
V2_LINKED_STOCK_ROUTE_BY_KIND = {
    "index": "/api/n6/app/v2/membership/index",
    "board": "/api/n6/app/v2/membership/board",
}
V2_LINKED_STOCK_PARAM_BY_KIND = {
    "index": "index_identity_key",
    "board": "board_identity_key",
}
V2_FILTER_COMPONENT_BY_ASSET = {
    "stock": "B Track V2 Stock Filter",
    "board": "B Track V2 Board Filter",
    "index": "B Track V2 Index Filter",
}
V2_FILTER_LABEL_BY_ASSET = {
    "stock": "个股筛选",
    "board": "板块筛选",
    "index": "指数筛选",
}
V2_FILTER_ANCHOR_BY_ASSET = {
    "stock": "stock-filter",
    "board": "board-filter",
    "index": "index-filter",
}
V2_FILTER_ASSET_ORDER = ("index", "board", "stock")
V2_FILTER_DEFAULT_LIMIT_BY_ASSET = {
    "index": 200,
    "board": 200,
    "stock": 200,
}
V2_FILTER_COMMON_QUERY_FIELDS = (
    "for_trade_date",
    "q",
    "direction",
    "year_overheat_level",
    "quarter_overheat_level",
    "month_overheat_level",
    "week_overheat_level",
    "day_overheat_level",
    "buy_expected_return_pct_min",
    "condition_key",
    "quality_status",
    "source_run_id",
)
V2_FILTER_PERCENT_FIELDS = frozenset(
    {
        "cash_realization_rate",
    }
)
V2_EXPECTED_RETURN_FILTER_KEY = "buy_expected_return_pct_min"
V2_EXPECTED_RETURN_FILTER_FIELD = "buy_expected_return_pct"
V2_EXPECTED_RETURN_FILTER_LABEL = "预期收益率"
V2_LEVEL_UP_RECOMMENDATION_FILTER_KEY = "level_up_score_recommendation"
V2_LEVEL_UP_RECOMMENDATION_INDEX_MAX = "index_max"
V2_LEVEL_UP_RECOMMENDATION_FIELD = "level_up_score"
V2_FILTER_VISIBLE_FIELDS_BY_ASSET = {
    "stock": (
        "for_trade_date",
        "identity_key",
        "display_name",
        "industry_code",
        "industry_name",
        "buy_expected_return_pct",
        "buy_target_price",
        "up_secondary_target_price",
        "up_sell_reference_period",
        "score",
        "pe_core",
        "prev_up_str",
        "prev_dn_str",
        "level_up_score",
        "level_down_score",
        "period_transition_y",
        "period_transition_q",
        "period_transition_m",
        "period_transition_w",
        "period_transition_d",
        "cash_realization_rate",
        "revenue_yoy_pct",
        "core_profit_yoy_pct",
        "report_core_revenue",
        "report_core_profit",
        "core_profit_ttm",
        "core_gt_revenue_yoy",
        "revenue_growth_streak_q",
        "core_growth_streak_q",
        "core_gt_revenue_streak_q",
        "forecast_type",
        "forecast_score",
    ),
    "index": (
        "for_trade_date",
        "identity_key",
        "display_name",
        "buy_expected_return_pct",
        "buy_target_price",
        "up_secondary_target_price",
        "up_sell_reference_period",
        "prev_up_str",
        "prev_dn_str",
        "level_up_score",
        "level_down_score",
        "period_transition_y",
        "period_transition_q",
        "period_transition_m",
        "period_transition_w",
        "period_transition_d",
    ),
    "board": (
        "for_trade_date",
        "identity_key",
        "display_name",
        "buy_expected_return_pct",
        "buy_target_price",
        "up_secondary_target_price",
        "up_sell_reference_period",
        "prev_up_str",
        "prev_dn_str",
        "level_up_score",
        "level_down_score",
        "period_transition_y",
        "period_transition_q",
        "period_transition_m",
        "period_transition_w",
        "period_transition_d",
    ),
}
V2_FILTER_TABLE_HIDDEN_FIELDS_BY_ASSET = {
    "stock": frozenset({"forecast_type", "forecast_score"}),
}
V2_FILTER_FIELD_LABELS = {
    "for_trade_date": "生效交易日",
    "source_trade_date": "来源交易日",
    "asset_kind": "资产类型",
    "identity_key": "对象标识",
    "exchange": "交易所",
    "display_code": "代码",
    "display_name": "名称",
    "industry_code": "行业代码",
    "industry_name": "行业名称",
    "buy_expected_return_pct": "买入预期收益率",
    "up_secondary_expected_return_pct": "买入次级预期收益率",
    "buy_target_price": "买入目标价",
    "up_secondary_target_price": "买入次级目标价",
    "up_sell_reference_period": "参考周期",
    "down_buy_reference_period": "下行参考周期",
    "score": "综合评分",
    "pe_core": "核心市盈率",
    "prev_up_str": "前次上涨说明",
    "prev_dn_str": "前次下跌说明",
    "level_up_score": "上行评分",
    "level_down_score": "下行评分",
    "period_transition_y": "年周期状态",
    "period_transition_q": "季周期状态",
    "period_transition_m": "月周期状态",
    "period_transition_w": "周周期状态",
    "period_transition_d": "日周期状态",
    "cash_realization_rate": "现金实现率",
    "revenue_yoy_pct": "营收同比",
    "core_profit_yoy_pct": "核心利润同比",
    "report_core_revenue": "报告核心营收",
    "report_core_profit": "报告核心利润",
    "core_profit_ttm": "核心利润TTM",
    "core_gt_revenue_yoy": "核心利润增速高于营收",
    "revenue_growth_streak_q": "营收连续增长季度数",
    "core_growth_streak_q": "核心利润连续增长季度数",
    "core_gt_revenue_streak_q": "核心利润增速高于营收连续季度数",
    "forecast_type": "业绩预告类型",
    "forecast_score": "业绩预告评分",
}
V2_FILTER_MOBILE_FIELDS = (
    ("buy_expected_return_pct", "买入预期收益率"),
    ("buy_target_price", "买入目标价"),
    ("up_sell_reference_period", "参考周期"),
)
V2_FILTER_PERIOD_TRANSITION_FIELDS = (
    ("年", "period_transition_y"),
    ("季", "period_transition_q"),
    ("月", "period_transition_m"),
    ("周", "period_transition_w"),
    ("日", "period_transition_d"),
)
V2_FILTER_PERIOD_TRANSITION_LABELS = {
    "volume_up": "放量上涨",
    "volume_down": "放量下跌",
    "low_volume_up": "缩量上涨",
    "low_volume_down": "缩量下跌",
    "flat": "震荡",
    "unknown": "未知",
}
V2_FILTER_PAGE_BY_ASSET = {
    "index": "indexes",
    "board": "boards",
    "stock": "stocks",
}
V2_ADD_MONITOR_LABEL_BY_ASSET = {
    "stock": "加入个股监控",
    "board": "加入板块监控",
    "index": "加入指数监控",
}
V2_ADD_MONITOR_SHORT_LABEL_BY_ASSET = {
    "stock": "监控",
    "board": "监控",
    "index": "监控",
}
V2_ADD_SELECTED_LABEL_BY_ASSET = {
    "stock": "加入已选到个股监控",
    "board": "加入已选到板块监控",
    "index": "加入到指数监控",
}
V2_BULK_ADD_LABEL_BY_ASSET = {
    "stock": "将当前筛选结果加入到个股监控",
    "board": "将当前筛选结果加入到板块监控",
    "index": "当前筛选结果到指数监控",
}
V2_MONITOR_TITLE_BY_ASSET = {
    "stock": "我的个股监控",
    "board": "我的板块监控",
    "index": "我的指数监控",
}
V2_MONITOR_PAGE_BY_ASSET = {
    "index": "indexes",
    "board": "boards",
    "stock": "stocks",
}
V2_MONITOR_ASSET_BY_PAGE = {
    "indexes": "index",
    "boards": "board",
    "stocks": "stock",
}
V2_MONITOR_STATUS_FILTERS = {
    "active": "有效",
    "expired": "已失效",
    "all": "全部",
}
V2_MONITOR_SOURCE_TYPE_BY_RAW = {
    "single_row": "direct",
    "direct": "direct",
    "index_linked_stock": "index_linked_stock",
    "board_linked_stock": "board_linked_stock",
}
V2_MONITOR_SOURCE_LABEL_BY_TYPE = {
    "direct": "直接加入",
    "index_linked_stock": "来源指数",
    "board_linked_stock": "来源板块",
}
V2_MONITOR_SOURCE_OBJECT_KIND_BY_TYPE = {
    "direct": "none",
    "index_linked_stock": "index",
    "board_linked_stock": "board",
}
V2_OVERHEAT_FILTER_LABELS = {
    "year_overheat_level": "年过渡状态",
    "quarter_overheat_level": "季过渡状态",
    "month_overheat_level": "月过渡状态",
    "week_overheat_level": "周过渡状态",
    "day_overheat_level": "日过渡状态",
}
V2_PERIOD_GRADE_FILTERS = (
    ("year_overheat_level", "年过渡状态"),
    ("quarter_overheat_level", "季过渡状态"),
    ("month_overheat_level", "月过渡状态"),
    ("week_overheat_level", "周过渡状态"),
    ("day_overheat_level", "日过渡状态"),
)
V2_PERIOD_GRADE_OPTIONS = (
    {"value": "volume_up", "label": "放量上涨"},
    {"value": "volume_down", "label": "放量下跌"},
    {"value": "low_volume_up", "label": "缩量上涨"},
    {"value": "low_volume_down", "label": "缩量下跌"},
    {"value": "flat", "label": "震荡"},
)
MEMBERSHIP_CACHE_SOURCE_BY_ASSET = {
    "stock": "v_n6_board_membership_fact",
    "index": "v_n6_index_membership_fact",
    "board": "v_n6_board_membership_fact",
}


def app_nav_context(active: str) -> dict[str, Any]:
    links = [
        {"key": "dashboard", "label": APP_NAV_LABELS["dashboard"], "href": "/n6/app/dashboard"},
        {"key": "filter-center", "label": APP_NAV_LABELS["filter-center"], "href": "/n6/app/filter-center"},
        {"key": "my-monitor", "label": APP_NAV_LABELS["my-monitor"], "href": "/n6/app/my-monitor"},
        {"key": "realtime-scope", "label": APP_NAV_LABELS["realtime-scope"], "href": "/n6/app/realtime-scope"},
        {"key": "status-monitor", "label": APP_NAV_LABELS["status-monitor"], "href": "/n6/app/status-monitor"},
        {"key": "signals", "label": APP_NAV_LABELS["signals"], "href": "/n6/app/signals"},
        {"key": "messages", "label": APP_NAV_LABELS["messages"], "href": "/n6/app/messages"},
        {"key": "account", "label": APP_NAV_LABELS["account"], "href": "/n6/app/account"},
        {"key": "trade-log", "label": APP_NAV_LABELS["trade-log"], "href": "/n6/app/trade-log"},
        {"key": "ai-agent", "label": APP_NAV_LABELS["ai-agent"], "href": "/n6/app/ai-agent"},
    ]
    return {"active": "dashboard" if active == "home" else active, "links": links}


def _component_label(component: str) -> str:
    return APP_COMPONENT_LABELS.get(component, component)


def _event_label(event_type: Any) -> str:
    value = str(event_type or "").strip()
    return APP_EVENT_LABELS.get(value, value or "状态变化 (TriggerStateChanged)")


def _state_label(value: Any) -> str:
    text = str(value or "").strip()
    return APP_STATE_LABELS.get(text, text or "—")


def _direction_label(value: Any) -> str:
    text = str(value or "").strip()
    return APP_DIRECTION_LABELS.get(text, text or "—")


def _blocked_reason_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text == "—":
        return "—"
    return APP_BLOCKED_REASON_LABELS.get(text, text)


def _asset_kind_label(value: Any) -> str:
    text = str(value or "").strip()
    return APP_ASSET_KIND_LABELS.get(text, text or "—")


def _period_label(value: Any) -> str:
    text = str(value or "").strip()
    return {
        "Y": "年",
        "Q": "季",
        "M": "月",
        "W": "周",
        "D": "日",
        "120m": "120分钟",
        "30m": "30分钟",
        "5m": "5分钟",
        "1m": "1分钟",
    }.get(text, text or "—")


def _periods_label(values: Any) -> str:
    if isinstance(values, (list, tuple)):
        return "、".join(_period_label(value) for value in values) or "—"
    return _period_label(values)


def app_message_asset_kind(value: Any) -> str:
    text = str(value or "").strip()
    if text in APP_MESSAGE_ASSET_KIND_ORDER:
        return text
    return APP_DEFAULT_MESSAGE_ASSET_KIND


def app_message_asset_kinds(values: Any = None) -> list[str]:
    if isinstance(values, str) or values is None:
        candidates = [values]
    else:
        try:
            candidates = list(values)
        except TypeError:
            candidates = [values]
    selected = {
        str(value or "").strip()
        for value in candidates
        if str(value or "").strip() in APP_MESSAGE_ASSET_KIND_ORDER
    }
    return [
        asset_kind
        for asset_kind in APP_MESSAGE_ASSET_KIND_ORDER
        if asset_kind in selected
    ] or list(APP_MESSAGE_ASSET_KIND_ORDER)


def _asset_kind_options(selected_asset_kinds: list[str]) -> list[dict[str, Any]]:
    selected = set(selected_asset_kinds)
    return [
        {
            "asset_kind": asset_kind,
            "label": APP_CARD_ASSET_TAB_LABELS[asset_kind],
            "asset_kind_label": _asset_kind_label(asset_kind),
            "selected": asset_kind in selected,
        }
        for asset_kind in APP_MESSAGE_ASSET_KIND_ORDER
    ]


def _asset_kind_tabs(
    *,
    base_href: str,
    selected_trade_date: str,
    selected_asset_kind: str,
    labels: dict[str, str],
) -> list[dict[str, Any]]:
    tabs: list[dict[str, Any]] = []
    for asset_kind in APP_MESSAGE_ASSET_KIND_ORDER:
        pairs = [
            ("trade_date", selected_trade_date),
            ("asset_kind", asset_kind),
        ]
        tabs.append(
            {
                "asset_kind": asset_kind,
                "label": labels[asset_kind],
                "asset_kind_label": _asset_kind_label(asset_kind),
                "active": asset_kind == selected_asset_kind,
                "href": _filter_href(base_href, pairs),
            }
        )
    return tabs


def _message_api_href(
    base_href: str,
    *,
    selected_trade_date: str,
    selected_asset_kind: str | None = None,
    selected_asset_kinds: list[str] | None = None,
) -> str:
    asset_kinds = (
        app_message_asset_kinds(selected_asset_kinds)
        if selected_asset_kinds is not None
        else [app_message_asset_kind(selected_asset_kind)]
    )
    return _filter_href(
        base_href,
        [
            ("trade_date", selected_trade_date),
            *((("asset_kind", asset_kind) for asset_kind in asset_kinds)),
        ],
    )


def _watchlist_status_label(value: Any) -> str:
    text = str(value or "").strip()
    return APP_WATCHLIST_STATUS_LABELS.get(text, _state_label(text))


def app_principal_model(principal: dict[str, Any], *, user: dict[str, Any]) -> dict[str, Any]:
    principal_type = str(principal.get("principal_type") or "")
    permissions = [
        "read:own_virtual_account",
        "read:own_watchlist",
        "read:own_signals",
        "read:own_proposals",
        "read:own_portfolio",
        "read:own_pnl",
    ]
    if principal_type == "admin":
        permissions.append("read:system_audit_link")
    return {
        "principal_id": canonical_bigint_id(
            principal.get("principal_id"),
            field_name="principal_id",
            required=True,
        ),
        "principal_type": principal_type,
        "display_name": principal.get("display_name")
        or principal.get("principal_label")
        or user.get("display_name")
        or user.get("login_name"),
        "role": user.get("role"),
        "app_scope": APP_SCOPE,
        "permissions": permissions,
        "principal_status": principal.get("principal_status") or "active",
    }


def app_me_model(principal: dict[str, Any], *, user: dict[str, Any]) -> dict[str, Any]:
    component = "B Track Me"
    return {
        "ok": True,
        "component": component,
        "component_label": _component_label(component),
        "principal": app_principal_model(principal, user=user),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def app_dashboard_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    account: dict[str, Any] | None,
    cash_snapshot: dict[str, Any] | None,
    signal_rows: list[dict[str, Any]],
    current_trade_date: str = "",
    trading_session_active: bool = False,
    monitor_result: dict[str, Any] | None = None,
    realtime_scope_result: dict[str, Any] | None = None,
    positions: list[dict[str, Any]] | None = None,
    proposal_result: dict[str, Any] | None = None,
    trade_result: dict[str, Any] | None = None,
    scope_write_enabled: bool = False,
    scope_bulk_write_enabled: bool = False,
    proposal_write_enabled: bool = False,
) -> dict[str, Any]:
    signal_items = [app_signal_item(row) for row in signal_rows]
    account_payload = app_account_model(
        principal,
        user=user,
        account=account,
        cash_snapshot=cash_snapshot,
        current_trade_date=current_trade_date,
    )
    guide = app_dashboard_user_operation_guide()
    scope_summary = app_dashboard_scope_summary(
        monitor_result or {},
        realtime_scope_result or {},
    )
    message_summary = app_dashboard_message_summary(
        signal_items,
        current_trade_date=current_trade_date,
    )
    virtual_summary = app_dashboard_virtual_summary(
        account_payload,
        positions=positions or [],
        proposal_result=proposal_result or {},
        trade_result=trade_result or {},
    )
    next_action = app_dashboard_next_action(
        scope_summary=scope_summary,
        message_summary=message_summary,
        virtual_summary=virtual_summary,
        scope_write_enabled=scope_write_enabled,
        proposal_write_enabled=proposal_write_enabled,
    )
    component = "B Track Dashboard"
    return {
        "ok": True,
        "component": component,
        "component_label": _component_label(component),
        "principal": app_principal_model(principal, user=user),
        "today_overview": app_dashboard_today_overview(signal_items, cash_snapshot=cash_snapshot),
        "account_summary": app_dashboard_account_summary(account_payload),
        "signals_summary": app_dashboard_signals_summary(signal_items),
        "user_operation_guide": guide,
        "guide_summary": {
            "title": guide["title"],
            "summary": guide["summary"],
            "href": "/n6/app/guide",
            "cta_label": "打开六步新用户说明书",
        },
        "watchlist_summary": app_dashboard_watchlist_summary(monitor_result or {}),
        "ai_users_summary": app_dashboard_ai_users_summary(),
        "status_monitor_snapshot": app_dashboard_status_snapshot(signal_items),
        "future_modules_locked": app_dashboard_future_modules_locked(),
        "dashboard_status": app_dashboard_status(
            current_trade_date=current_trade_date,
            trading_session_active=trading_session_active,
            scope_write_enabled=scope_write_enabled,
            scope_bulk_write_enabled=scope_bulk_write_enabled,
            proposal_write_enabled=proposal_write_enabled,
        ),
        "scope_summary": scope_summary,
        "message_summary": message_summary,
        "virtual_summary": virtual_summary,
        "next_action": next_action,
        "readonly": True,
        "safety_banner": list(APP_SAFETY_LABELS),
        "source_policy": app_signal_source_policy(),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def app_dashboard_user_operation_guide() -> dict[str, Any]:
    steps = [
        {
            "number": "01",
            "title": "筛选三类资产",
            "summary": "先在筛选中心查看指数、板块和个股。",
            "description": "个股只提供买向观察；指数和板块同时提供买向、卖向观察。筛选结果是只读候选，不构成投资建议。",
            "href": "/n6/app/filter-center",
        },
        {
            "number": "02",
            "title": "加入监控对象",
            "summary": "把想持续观察的对象加入本人监控。",
            "description": "监控对象按当前用户隔离，用于决定哪些对象的 N6 消息对你可见；不同用户互不影响。",
            "href": "/n6/app/my-monitor",
        },
        {
            "number": "03",
            "title": "按需加入实时范围",
            "summary": "实时范围只决定当前交易日的增量消息可见性。",
            "description": "监控对象可保留历史查询；实时范围面向当前交易日，两者不是同一概念，也不会触发下单。",
            "href": "/n6/app/realtime-scope",
        },
        {
            "number": "04",
            "title": "查看消息与移动卡片",
            "summary": "消息列表与卡片消息使用同一用户可见性边界。",
            "description": "当前业务日可用 SSE 接收新增消息；历史查询不走实时 SSE。语音只播本页新收到的 SSE，浏览器本地处理，不写服务器。",
            "href": "/n6/app/messages",
        },
        {
            "number": "05",
            "title": "合格个股两阶段虚拟申请",
            "summary": "先准备申请，再由本人第二次确认。",
            "description": "proposal 只是虚拟交易申请，不等于订单或成交；是否可用取决于页面能力状态，且全程不连接真实券商。",
            "href": "/n6/app/signals",
        },
        {
            "number": "06",
            "title": "核对账户、组合与日志",
            "summary": "最后核对资金、持仓、T+1、申请与虚拟成交。",
            "description": "账户、持仓和买卖日志只展示当前 principal 的虚拟数据；空消息不等于上游故障，应结合业务日、监控与实时范围判断。",
            "href": "/n6/app/account",
        },
    ]
    return {
        "title": "B轨新用户操作说明书",
        "summary": "六步完成筛选、个人监控、实时范围、消息、虚拟申请和账户核对。",
        "subtitle": "B轨是多用户、全虚拟的只读观察与受控申请界面，不连接真实券商。",
        "steps": steps,
        "concepts": [
            {
                "title": "监控对象与实时范围",
                "description": "监控对象决定本人可见对象及历史查询范围；实时范围只补充当前交易日的增量消息范围。",
            },
            {
                "title": "资产方向",
                "description": "个股只按买向观察；指数、板块按买向和卖向双向观察。",
            },
            {
                "title": "历史查询与 SSE",
                "description": "交易时段历史查询受限；历史快照不接收实时 SSE。当前业务日 SSE 只传新增 N6 投影。",
            },
            {
                "title": "语音边界",
                "description": "语音只播当前页面新收到的 SSE，由浏览器本地完成，不写服务器，也不代表通知已送达。",
            },
        ],
        "safety_boundaries": [
            "proposal 不等于订单或成交，必须由真人执行两阶段确认。",
            "proposal/确认不等于成交；成交由独立 N6 executor 处理；executor 状态本页不验证。",
            "全部账户、资金、持仓和成交均为虚拟数据；全虚拟、不连接真实券商；不执行真实下单。",
            "空消息可能来自当前无匹配监控、无实时范围或当前没有新投影，不等于上游故障。",
        ],
        "advanced_notes": [
            "页面只读取现有 principal-scoped N6 repository，不回查 N1-N5 裸表。",
            "executor 运行状态不由本页验证；工作台固定显示“本页未验证”。",
        ],
        "ai_agent": {
            "title": "AI投资员",
            "description": "独立共享的只读学习入口，不替用户创建申请，不连接真实券商。",
            "href": "/n6/app/ai-agent",
        },
        "readonly": True,
    }


def app_user_guide_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
) -> dict[str, Any]:
    guide = app_dashboard_user_operation_guide()
    return {
        "ok": True,
        "component": "B Track User Guide",
        "component_label": "新用户说明书",
        "principal": app_principal_model(principal, user=user),
        "guide": guide,
        "readonly": True,
        "safety_banner": list(APP_SAFETY_LABELS),
        "source_policy": app_signal_source_policy(),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def app_dashboard_status(
    *,
    current_trade_date: str,
    trading_session_active: bool,
    scope_write_enabled: bool,
    scope_bulk_write_enabled: bool,
    proposal_write_enabled: bool,
) -> dict[str, Any]:
    business_date_ready = bool(str(current_trade_date or "").strip())
    historical_allowed = bool(business_date_ready and not trading_session_active)
    return {
        "business_date": current_trade_date or None,
        "business_date_display": current_trade_date or "暂不可确认",
        "trading_session": "trading" if trading_session_active else "off_session" if business_date_ready else "unknown",
        "trading_session_display": "交易时段" if trading_session_active else "非交易时段" if business_date_ready else "暂不可确认",
        "historical_query_allowed": historical_allowed if business_date_ready else None,
        "historical_query_display": "可查询只读历史快照" if historical_allowed else "交易时段仅限当前业务日" if trading_session_active else "暂不可确认",
        "capabilities": {
            "monitor_management": "已启用" if scope_write_enabled else "只读查看",
            "bulk_add": "已启用" if scope_bulk_write_enabled else "未启用",
            "proposal": "已启用" if proposal_write_enabled else "未启用",
            "sse": "当前业务日新增消息" if business_date_ready else "暂不可确认",
            "executor": "本页未验证",
        },
    }


def _dashboard_asset_counts(
    rows: list[dict[str, Any]],
    *,
    status_field: str = "",
    status_value: str = "",
) -> dict[str, int]:
    identities = {
        (str(row.get("asset_kind") or ""), str(row.get("identity_key") or ""))
        for row in rows
        if str(row.get("asset_kind") or "") in APP_ASSET_KIND_LABELS
        and str(row.get("identity_key") or "")
        and (not status_field or str(row.get(status_field) or "") == status_value)
    }
    return {
        asset_kind: sum(1 for kind, _ in identities if kind == asset_kind)
        for asset_kind in ("stock", "index", "board")
    }


def app_dashboard_scope_summary(
    monitor_result: dict[str, Any],
    realtime_scope_result: dict[str, Any],
) -> dict[str, Any]:
    monitor_ready = bool(monitor_result.get("tables_ready"))
    realtime_ready = bool(realtime_scope_result.get("tables_ready"))
    monitor_rows = list(monitor_result.get("items") or [])
    active_rows = [
        row
        for row in monitor_rows
        if str(row.get("effective_status") or row.get("status") or "") == "active"
    ]
    realtime_rows = [
        row
        for row in realtime_scope_result.get("items") or []
        if str(row.get("status") or "active") == "active"
    ]
    monitor_counts = _dashboard_asset_counts(active_rows) if monitor_ready else {}
    realtime_counts = _dashboard_asset_counts(realtime_rows) if realtime_ready else {}
    monitor_count = sum(monitor_counts.values()) if monitor_ready else None
    realtime_count = sum(realtime_counts.values()) if realtime_ready else None
    return {
        "monitor_ready": monitor_ready,
        "monitor_count": monitor_count,
        "monitor_count_display": str(monitor_count) if monitor_count is not None else "暂不可确认",
        "monitor_by_asset_kind": monitor_counts if monitor_ready else None,
        "realtime_ready": realtime_ready,
        "realtime_count": realtime_count,
        "realtime_count_display": str(realtime_count) if realtime_count is not None else "暂不可确认",
        "realtime_by_asset_kind": realtime_counts if realtime_ready else None,
        "readonly": True,
    }


def app_dashboard_message_summary(
    signal_items: list[dict[str, Any]],
    *,
    current_trade_date: str,
) -> dict[str, Any]:
    ready = bool(str(current_trade_date or "").strip())
    event_times = [
        str(item.get("event_time") or "").strip()
        for item in signal_items
        if str(item.get("event_time") or "").strip()
    ]
    latest_event_time = max(event_times, default="") if ready else ""
    by_event = {
        event_type: _count_action(signal_items, state, event_type)
        for event_type, state in (
            ("ActionEligible", "eligible"),
            ("ActionExecuted", "executed"),
            ("ActionBlocked", "blocked"),
            ("ActionSkipped", "skipped"),
        )
    }
    total_count = len(signal_items) if ready else None
    return {
        "ready": ready,
        "total_count": total_count,
        "total_count_display": str(total_count) if total_count is not None else "暂不可确认",
        "latest_event_time": latest_event_time or None,
        "latest_event_time_display": latest_event_time or ("暂无消息" if ready else "暂不可确认"),
        "by_event_type": by_event if ready else None,
        "by_asset_kind": _count_by(signal_items, "asset_kind") if ready else None,
        "empty_is_upstream_failure": False,
        "empty_explanation": "空消息不等于上游故障，请核对业务日、监控对象与实时范围。",
        "readonly": True,
    }


def _dashboard_number(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def app_dashboard_virtual_summary(
    account_payload: dict[str, Any],
    *,
    positions: list[dict[str, Any]],
    proposal_result: dict[str, Any],
    trade_result: dict[str, Any],
) -> dict[str, Any]:
    account_ready = bool(account_payload.get("virtual_account"))
    cash = account_payload.get("cash_summary") or {}
    proposal_ready = bool(proposal_result.get("tables_ready"))
    trade_ready = bool(trade_result.get("tables_ready"))
    proposals = list(proposal_result.get("items") or [])
    trades = list(trade_result.get("items") or [])
    position_count = len(positions) if account_ready else None
    sellable = sum(
        (_dashboard_number(row.get("sellable_quantity")) or Decimal("0"))
        for row in positions
    ) if account_ready else None
    t1_locked = sum(
        (_dashboard_number(row.get("t1_locked_quantity")) or Decimal("0"))
        for row in positions
    ) if account_ready else None
    pending_proposal_count = (
        sum(1 for row in proposals if str(row.get("proposal_status") or "") == "pending")
        if proposal_ready
        else None
    )
    trade_count = len(trades) if trade_ready else None
    return {
        "account_ready": account_ready,
        "account_status_display": "已初始化" if account_ready else "未初始化",
        "cash_ready": bool(cash),
        "available_cash_display": cash.get("available_cash_display") if cash else "暂不可确认",
        "total_cash_display": cash.get("total_cash_display") if cash else "暂不可确认",
        "freshness_display": cash.get("freshness_display") if cash else "暂不可确认",
        "position_count": position_count,
        "position_count_display": str(position_count) if position_count is not None else "暂不可确认",
        "sellable_quantity_display": _portfolio_decimal_text(sellable) if sellable is not None else "暂不可确认",
        "t1_locked_quantity_display": _portfolio_decimal_text(t1_locked) if t1_locked is not None else "暂不可确认",
        "proposal_ready": proposal_ready,
        "pending_proposal_count": pending_proposal_count,
        "pending_proposal_count_display": str(pending_proposal_count) if pending_proposal_count is not None else "暂不可确认",
        "trade_ready": trade_ready,
        "trade_count": trade_count,
        "trade_count_display": str(trade_count) if trade_count is not None else "暂不可确认",
        "executor_status": "本页未验证",
        "real_broker_connected": False,
        "readonly": True,
    }


def app_dashboard_next_action(
    *,
    scope_summary: dict[str, Any],
    message_summary: dict[str, Any],
    virtual_summary: dict[str, Any],
    scope_write_enabled: bool,
    proposal_write_enabled: bool,
) -> dict[str, str]:
    pending = virtual_summary.get("pending_proposal_count")
    eligible = (message_summary.get("by_event_type") or {}).get("ActionEligible")
    positions = virtual_summary.get("position_count")
    monitor_count = scope_summary.get("monitor_count")
    realtime_count = scope_summary.get("realtime_count")
    message_count = message_summary.get("total_count")
    if proposal_write_enabled and isinstance(pending, int) and pending > 0:
        return {"key": "pending_proposal", "label": "继续待确认虚拟申请", "href": "/n6/app/proposals"}
    if isinstance(eligible, int) and eligible > 0:
        return {"key": "action_eligible_stock_message", "label": "查看待确认个股消息", "href": "/n6/app/signals?asset_kind=stock&action_state=eligible"}
    if isinstance(positions, int) and positions > 0:
        return {"key": "portfolio", "label": "核对虚拟持仓与 T+1", "href": "/n6/app/portfolio"}
    if scope_write_enabled and monitor_count == 0:
        return {"key": "filter_center", "label": "去筛选中心选择监控对象", "href": "/n6/app/filter-center"}
    if not virtual_summary.get("account_ready"):
        return {"key": "account_initialization", "label": "查看虚拟账户初始化状态", "href": "/n6/app/account"}
    if scope_write_enabled and realtime_count == 0:
        return {"key": "realtime_scope", "label": "按需设置实时监控范围", "href": "/n6/app/realtime-scope"}
    if isinstance(monitor_count, int) and monitor_count > 0 and message_count == 0:
        return {"key": "monitor_without_message", "label": "查看监控对象与消息边界", "href": "/n6/app/my-monitor"}
    return {"key": "card_messages", "label": "查看卡片消息", "href": "/n6/app/messages"}


def app_dashboard_today_overview(
    signal_items: list[dict[str, Any]],
    *,
    cash_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    latest = signal_items[0] if signal_items else {}
    action_counts = {
        "ActionExecuted": _count_action(signal_items, "executed", "ActionExecuted"),
        "ActionBlocked": _count_action(signal_items, "blocked", "ActionBlocked"),
        "ActionEligible": _count_action(signal_items, "eligible", "ActionEligible"),
        "ActionSkipped": _count_action(signal_items, "skipped", "ActionSkipped"),
        "ActionExpired": _count_action(signal_items, "expired", "ActionSkipped"),
    }
    blocked_reason_distribution: dict[str, int] = {}
    for item in signal_items:
        reason = str(item.get("blocked_reason") or "").strip()
        if reason and reason != "—":
            blocked_reason_distribution[reason] = blocked_reason_distribution.get(reason, 0) + 1
    blocked_reason_labels = {reason: _blocked_reason_label(reason) for reason in blocked_reason_distribution}
    trade_date = _first_text(latest, "trade_date", default=str((cash_snapshot or {}).get("trade_date") or "—"))
    return {
        "trade_date": trade_date,
        "latest_projection_run_id": _first_text(latest, "projection_run_id", "user_projection_run_id"),
        "latest_event_time": _first_text(latest, "event_time"),
        "action_counts": action_counts,
        "blocked_reason_distribution": blocked_reason_distribution,
        "blocked_reason_labels": blocked_reason_labels,
        "wording": {
            "ActionExecuted": APP_EVENT_LABELS["ActionExecuted"],
            "ActionBlocked": APP_EVENT_LABELS["ActionBlocked"],
            "ActionEligible": APP_EVENT_LABELS["ActionEligible"],
            "ActionSkipped": APP_EVENT_LABELS["ActionSkipped"],
        },
    }


def app_dashboard_account_summary(account_payload: dict[str, Any]) -> dict[str, Any]:
    virtual_account = account_payload.get("virtual_account") or {}
    cash = account_payload.get("cash_summary") or {}
    return {
        "account_name": _first_text(virtual_account, "account_name"),
        "status": _first_text(virtual_account, "account_status", "status", "virtual_account_status"),
        "quality_status": _first_text(virtual_account, "quality_status"),
        "base_currency": _first_text(
            virtual_account,
            "currency",
            "base_currency",
            default=_first_text(cash, "currency"),
        ),
        "initial_cash": _money_text(virtual_account.get("initial_cash")),
        "available_cash": _money_text(cash.get("available_cash")),
        "frozen_cash": _money_text(cash.get("frozen_cash")),
        "total_cash": _money_text(cash.get("total_cash")),
        "snapshot_status": _first_text(cash, "snapshot_status"),
        "updated_at": _first_text(virtual_account, "updated_at"),
    }


def app_dashboard_signals_summary(signal_items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_count": len(signal_items),
        "latest_items": signal_items[:5],
        "by_asset_kind": _count_by(signal_items, "asset_kind"),
        "by_direction": _count_by(signal_items, "direction"),
        "inbox_label": "我的监控消息",
        "overview_entry_label": "查看消息总览",
        "overview_entry_href": "/n6/app/messages",
        "list_entry_label": "查看消息列表",
        "list_entry_href": "/n6/app/signals",
        "readonly": True,
    }


def app_dashboard_watchlist_summary(monitor_result: dict[str, Any]) -> dict[str, Any]:
    ready = bool(monitor_result.get("tables_ready"))
    rows = list(monitor_result.get("items") or [])
    active_rows = [
        row
        for row in rows
        if str(row.get("effective_status") or row.get("status") or "") == "active"
    ]
    counts = _dashboard_asset_counts(active_rows) if ready else {}
    return {
        "status": "ready" if ready else "data_not_ready",
        "status_label": _state_label("ready" if ready else "data_not_ready"),
        "tracked_count": sum(counts.values()) if ready else None,
        "tracked_count_display": str(sum(counts.values())) if ready else "暂不可确认",
        "by_asset_kind": counts if ready else None,
        "source": "当前用户监控对象",
        "mutation_enabled": False,
        "add_enabled": False,
        "delete_enabled": False,
        "sort_persist_enabled": False,
    }


def app_dashboard_ai_users_summary() -> dict[str, Any]:
    return {
        "status": "readonly_shell",
        "status_label": _state_label("readonly_shell"),
        "mode": "shadow_observer",
        "mode_label": "只读观察员",
        "observer_count": 0,
        "generated_signal_enabled": False,
        "auto_trade_enabled": False,
        "advice_enabled": False,
    }


def app_dashboard_status_snapshot(signal_items: list[dict[str, Any]]) -> dict[str, Any]:
    tags = [tag for item in signal_items for tag in item.get("tags", [])]
    return {
        "active_signal_count": len(signal_items),
        "market_action_confirmed": sum(1 for tag in tags if "市场动作确认成立" in str(tag)),
        "market_action_not_confirmed": sum(1 for tag in tags if "市场动作未确认" in str(tag)),
        "pending_market_data": sum(1 for tag in tags if "等待行情证据" in str(tag)),
        "state_changed": sum(1 for tag in tags if "状态变化" in str(tag)),
        "source": "reviewed N6 projection/card tags",
    }


def app_dashboard_future_modules_locked() -> list[dict[str, Any]]:
    return [
        {
            "key": "pnl",
            "label": "收益",
            "status": "locked_empty",
            "status_label": _state_label("locked_empty"),
            "locked": True,
            "reason": APP_FUTURE_MODULE_NOTICE,
            "entry_enabled": False,
        },
        {
            "key": "leaderboard",
            "label": "排行榜",
            "status": "locked_planned",
            "status_label": _state_label("locked_planned"),
            "locked": True,
            "reason": APP_FUTURE_MODULE_NOTICE,
            "entry_enabled": False,
        },
        {
            "key": "future_automation",
            "label": "未来自动交易入口",
            "status": "locked_readiness_only",
            "status_label": _state_label("locked_readiness_only"),
            "locked": True,
            "reason": APP_FUTURE_MODULE_NOTICE,
            "entry_enabled": False,
        },
    ]


def app_account_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    account: dict[str, Any] | None,
    cash_snapshot: dict[str, Any] | None,
    current_trade_date: Any = None,
) -> dict[str, Any]:
    component = "B Track Account"
    account_ready = bool(account)
    virtual_account = None
    if account:
        virtual_account = {
            "virtual_account_id": str(account.get("virtual_account_id") or ""),
            "account_name": _first_text(account, "account_name", default="虚拟账户"),
            "account_status": _first_text(account, "account_status", default="active"),
            "account_type": _first_text(account, "account_type", default="virtual_t1"),
            "settlement_rule": _first_text(account, "settlement_rule", default="T+1"),
            "currency": _first_text(account, "currency", default="CNY"),
            "initial_cash": number_or_none(account.get("initial_cash")),
            "quality_status": _first_text(account, "quality_status"),
            "updated_at": display_datetime(account.get("updated_at")),
        }
    cash_summary = None
    if cash_snapshot:
        snapshot_trade_date = _app_account_trade_date(cash_snapshot.get("trade_date"))
        current_date = _app_account_trade_date(current_trade_date)
        freshness = (
            "current"
            if snapshot_trade_date is not None and snapshot_trade_date == current_date
            else "stale"
            if snapshot_trade_date is not None and current_date is not None and snapshot_trade_date < current_date
            else "unknown"
        )
        freshness_display = {
            "current": "当前交易日数据",
            "stale": "数据时间较早",
            "unknown": "暂不可确认",
        }[freshness]
        cash_summary = {
            "available_cash": number_or_none(cash_snapshot.get("available_cash")),
            "frozen_cash": number_or_none(cash_snapshot.get("frozen_cash")),
            "total_cash": number_or_none(cash_snapshot.get("total_cash")),
            "available_cash_display": _money_text(cash_snapshot.get("available_cash")),
            "frozen_cash_display": _money_text(cash_snapshot.get("frozen_cash")),
            "total_cash_display": _money_text(cash_snapshot.get("total_cash")),
            "snapshot_time": display_datetime(cash_snapshot.get("snapshot_time") or cash_snapshot.get("updated_at")),
            "trade_date": snapshot_trade_date.isoformat() if snapshot_trade_date is not None else None,
            "freshness": freshness,
            "freshness_display": freshness_display,
            "freshness_warning": freshness != "current",
        }
    return {
        "ok": True,
        "component": component,
        "component_label": _component_label(component),
        "principal": app_principal_model(principal, user=user),
        "status": "ready" if account_ready else "not_ready",
        "status_label": _state_label("ready" if account_ready else "not_ready"),
        "locked": not account_ready,
        "reason": "" if account_ready else "当前 principal 尚未创建虚拟账户",
        "virtual_account": virtual_account,
        "cash_summary": cash_summary,
        "readonly": True,
        "safety_banner": list(APP_SAFETY_LABELS),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def _app_account_trade_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if re.fullmatch(r"[0-9]{8}", text):
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def app_trade_proposals_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    result: dict[str, Any],
    write_enabled: bool = False,
) -> dict[str, Any]:
    items = []
    for row in result.get("items") or []:
        items.append(
            {
                "proposal_id": canonical_bigint_id(row.get("proposal_id"), field_name="proposal_id", required=True),
                "source_type": _first_text(row, "source_type"),
                "source_id": _first_text(row, "source_id"),
                "asset_kind": _first_text(row, "asset_kind"),
                "identity_key": _first_text(row, "identity_key"),
                "proposal_side": _first_text(row, "proposal_side"),
                "signal_reference_kind": _first_text(row, "signal_reference_kind"),
                "signal_reference_price": number_or_none(row.get("signal_reference_price")),
                "proposal_status": _first_text(row, "proposal_status"),
                "confirmation_generation_token": _first_text(
                    row, "confirmation_generation_token"
                ),
                "expires_at": display_datetime(row.get("expires_at")),
                "confirmed_at": display_datetime(row.get("confirmed_at")),
                "created_at": display_datetime(row.get("created_at")),
                "failure_reason": _first_text(row, "failure_reason"),
            }
        )
    return {
        "ok": True,
        "component": "B Track Virtual Trade Proposals V3",
        "principal": app_principal_model(principal, user=user),
        "tables_ready": bool(result.get("tables_ready")),
        "items": items,
        "controls": {
            "create_route_registered": True,
            "confirm_route_registered": True,
            "write_route_enabled": bool(write_enabled),
            "client_price_allowed": False,
            "client_quantity_allowed": False,
            "client_account_allowed": False,
        },
        "readonly": not bool(write_enabled),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def app_virtual_trades_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    items = []
    for row in result.get("items") or []:
        items.append(
            {
                "virtual_trade_id": canonical_bigint_id(
                    row.get("virtual_trade_id"), field_name="virtual_trade_id", required=True
                ),
                "virtual_order_id": canonical_bigint_id(
                    row.get("virtual_order_id"), field_name="virtual_order_id", required=True
                ),
                "virtual_account_id": canonical_bigint_id(
                    row.get("virtual_account_id"), field_name="virtual_account_id", required=True
                ),
                "identity_key": _first_text(row, "identity_key"),
                "stock_code": _first_text(row, "stock_code"),
                "stock_name": _first_text(row, "stock_name"),
                "industry_code": _first_text(row, "industry_code"),
                "industry_name": _first_text(row, "industry_name"),
                "trade_side": _first_text(row, "trade_side"),
                "filled_quantity": number_or_none(row.get("filled_quantity")),
                "filled_price": number_or_none(row.get("filled_price")),
                "gross_amount": number_or_none(row.get("gross_amount")),
                "total_fee_amount": number_or_none(row.get("total_fee_amount")),
                "net_amount": number_or_none(row.get("net_amount")),
                "trade_status": _first_text(row, "trade_status"),
                "trade_time": display_datetime(row.get("trade_time")),
                "signal_reference_kind": _first_text(row, "signal_reference_kind"),
                "signal_reference_price": number_or_none(row.get("signal_reference_price")),
                "fill_quote_snapshot_id": canonical_bigint_id(
                    row.get("fill_quote_snapshot_id"), field_name="fill_quote_snapshot_id"
                ),
            }
        )
    return {
        "ok": True,
        "component": "B Track Virtual Trade Log V3",
        "principal": app_principal_model(principal, user=user),
        "tables_ready": bool(result.get("tables_ready")),
        "items": items,
        "readonly": True,
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def app_signals_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    rows: list[dict[str, Any]],
    filters: dict[str, Any],
    scope_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected_asset_kind = app_message_asset_kind(filters.get("asset_kind"))
    items = []
    for row in rows:
        item = app_signal_item(row)
        if item.get("asset_kind") == "stock":
            item["industry_code"] = _first_available_text(
                row.get("signal_industry_code")
            ) or "—"
            item["industry_name"] = _first_available_text(
                row.get("signal_industry_name")
            ) or "—"
        items.append(item)
    metadata = dict(scope_metadata or {})
    excluded_reason_counts = {
        "message_trade_date_missing": 0,
        "message_trade_date_mismatch": 0,
        "monitor_expired": 0,
    }
    excluded_reason_counts.update(metadata.get("excluded_reason_counts") or {})
    effective_monitor_count = int(metadata.get("effective_monitor_count") or 0)
    matched_signal_count = len(items)
    scope_mode = metadata.get("scope_mode") or "effective_monitor"
    if scope_mode == "historical_projection" and matched_signal_count <= 0:
        empty_state = {
            "reason": "no_messages_for_trade_date",
            "message": "该交易日没有 N6 历史消息",
        }
    elif scope_mode == "historical_projection" and matched_signal_count > 0:
        empty_state = {"reason": "", "message": ""}
    elif effective_monitor_count <= 0:
        empty_state = {
            "reason": "no_effective_monitor",
            "message": "当前没有有效监控对象，请先从筛选中心加入监控",
        }
    elif matched_signal_count <= 0:
        empty_state = {
            "reason": "waiting_projection",
            "message": "等待 N6 projection 生成用户消息",
        }
    elif excluded_reason_counts.get("message_trade_date_missing", 0):
        empty_state = {
            "reason": "message_trade_date_missing",
            "message": "存在消息缺少 trade_date，已从有效监控消息中排除",
        }
    else:
        empty_state = {"reason": "", "message": ""}
    component = "B Track Signals"
    return {
        "ok": True,
        "component": component,
        "component_label": _component_label(component),
        "principal": app_principal_model(principal, user=user),
        "filters": {
            key: value
            for key, value in filters.items()
            if value and key not in {"historical_projection_mode", "date_policy_blocker", "date_policy_message"}
        },
        "items": items,
        "scope_mode": scope_mode,
        "selected_trade_date": str(filters.get("trade_date") or ""),
        "selected_asset_kind": selected_asset_kind,
        "selected_asset_kind_label": _asset_kind_label(selected_asset_kind),
        "asset_kind_tabs": _asset_kind_tabs(
            base_href="/n6/app/signals",
            selected_trade_date=str(filters.get("trade_date") or ""),
            selected_asset_kind=selected_asset_kind,
            labels=APP_SIGNAL_ASSET_TAB_LABELS,
        ),
        "api_refresh_href": _message_api_href(
            "/api/n6/app/v1/signals",
            selected_trade_date=str(filters.get("trade_date") or ""),
            selected_asset_kind=selected_asset_kind,
        ),
        "api_stream_href": _message_api_href(
            "/api/n6/app/v1/signals/stream",
            selected_trade_date=str(filters.get("trade_date") or ""),
            selected_asset_kind=selected_asset_kind,
        ),
        "available_trade_dates": list(metadata.get("available_trade_dates") or []),
        "date_policy_blocker": str(metadata.get("date_policy_blocker") or ""),
        "date_policy_message": str(metadata.get("date_policy_message") or ""),
        "current_filter_batch": metadata.get("current_filter_batch") or {},
        "effective_monitor_count": effective_monitor_count,
        "expired_monitor_count": int(metadata.get("expired_monitor_count") or 0),
        "matched_signal_count": matched_signal_count,
        "excluded_reason_counts": excluded_reason_counts,
        "empty_state": empty_state,
        "available_tags": list(APP_SIGNAL_TAGS),
        "source_policy": app_signal_source_policy(),
        "readonly": True,
        "safety_banner": list(APP_SAFETY_LABELS),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def app_v2_message_dashboard_source_policy() -> dict[str, Any]:
    return {
        "allowed_sources": [
            "user_monitor_stock",
            "user_monitor_index",
            "user_monitor_board",
            "user_signal_projection",
            "user_signal_card",
            "user_projection_run",
            "v_n6_stock_condition_display_basis",
            "v_n6_index_condition_display_basis",
            "v_n6_board_condition_display_basis",
        ],
        "forbidden_sources": [
            "A-track message dashboard API",
            "common_event_outbox",
            "condition_basis",
            "condition_pool",
            "minute_target_scope",
            "raw K",
            "direct live market",
            "N4/N5 raw fact bypass",
            "user_notification_queue",
        ],
        "principal_scoped": True,
        "effective_monitor_scope": True,
        "monitor_effective_active_required": True,
        "asset_kind_match_required": True,
        "identity_key_match_required": True,
        "direction_match_required": True,
        "trade_date_match_required": True,
        "current_batch_reads_only_views": True,
        "n6_projection_only": True,
        "a_track_api_reused": False,
        "common_event_outbox_read": False,
        "condition_basis_read": False,
        "condition_pool_read": False,
        "minute_target_scope_read": False,
        "raw_k_read": False,
        "direct_live_market_read": False,
        "n4_raw_fact_bypass": False,
        "n5_raw_fact_bypass": False,
        "user_notification_queue_read": False,
    }


def app_v2_message_dashboard_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    rows: list[dict[str, Any]],
    filters: dict[str, Any] | None = None,
    scope_metadata: dict[str, Any] | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    items = [app_signal_item(row) for row in rows]
    card_items = [app_v2_message_card_item(row) for row in rows if row.get("user_signal_card_id")]
    metadata = _app_v2_message_scope_metadata(scope_metadata)
    normalized_filters = {
        key: value
        for key, value in dict(filters or {}).items()
        if key not in {"historical_projection_mode", "date_policy_blocker", "date_policy_message"} and value not in (None, "")
    }
    selected_trade_date = str(normalized_filters.get("trade_date") or metadata.get("selected_trade_date") or "")
    selected_asset_kinds = app_message_asset_kinds(
        normalized_filters.get("asset_kinds")
        or normalized_filters.get("asset_kind")
    )
    selected_asset_kind = selected_asset_kinds[0] if len(selected_asset_kinds) == 1 else None
    normalized_filters["asset_kinds"] = selected_asset_kinds
    if selected_asset_kind:
        normalized_filters["asset_kind"] = selected_asset_kind
    else:
        normalized_filters.pop("asset_kind", None)
    groups_payload = app_v2_message_groups_model(
        principal,
        user=user,
        rows=rows,
        scope_metadata=metadata,
        include_side_effects=False,
    )
    projection_status = app_v2_message_projection_status_model(
        principal,
        user=user,
        rows=rows,
        scope_metadata=metadata,
        include_side_effects=False,
    )
    summary = _app_v2_message_summary(items, metadata)
    empty_state = _app_v2_message_empty_state(
        summary=summary,
        current_filter_batch=metadata["current_filter_batch"],
        projection_status=projection_status,
        excluded_reason_counts=metadata["excluded_reason_counts"],
        scope_mode=str(metadata.get("scope_mode") or "effective_monitor"),
    )
    component = "B Track V2 Monitor Message Dashboard"
    return {
        "ok": True,
        "component": "b_track_monitor_message_dashboard_v2",
        "component_label": _component_label(component),
        "principal": app_principal_model(principal, user=user),
        "scope_mode": metadata["scope_mode"],
        "selected_trade_date": selected_trade_date,
        "selected_asset_kind": selected_asset_kind,
        "selected_asset_kinds": selected_asset_kinds,
        "selected_asset_kind_label": (
            _asset_kind_label(selected_asset_kind)
            if selected_asset_kind
            else "三类资产"
        ),
        "asset_kind_options": _asset_kind_options(selected_asset_kinds),
        "asset_kind_tabs": _asset_kind_tabs(
            base_href="/n6/app/messages",
            selected_trade_date=selected_trade_date,
            selected_asset_kind=selected_asset_kind or "",
            labels=APP_CARD_ASSET_TAB_LABELS,
        ),
        "api_refresh_href": _message_api_href(
            "/api/n6/app/v2/message-dashboard",
            selected_trade_date=selected_trade_date,
            selected_asset_kinds=selected_asset_kinds,
        ),
        "api_stream_href": _message_api_href(
            "/api/n6/app/v1/signals/stream",
            selected_trade_date=selected_trade_date,
            selected_asset_kinds=selected_asset_kinds,
        ),
        "available_trade_dates": list(metadata["available_trade_dates"]),
        "date_policy_blocker": str(metadata.get("date_policy_blocker") or ""),
        "date_policy_message": str(metadata.get("date_policy_message") or ""),
        "filters": normalized_filters,
        "current_filter_batch": metadata["current_filter_batch"],
        "summary": summary,
        "projection_status": projection_status,
        "groups": groups_payload["groups"],
        "card_items": card_items[: max(1, min(int(limit or 100), 500))],
        "items_preview": items[: max(1, min(int(limit or 100), 500))],
        "detail_entry": {
            "enabled": True,
            "label": "查看详情",
            "api_template": "/api/n6/app/v1/signals/{user_signal_projection_id}",
        },
        "empty_state": empty_state,
        "empty_states_supported": dict(APP_V2_MESSAGE_EMPTY_STATES),
        "source_policy": app_v2_message_dashboard_source_policy(),
        "readonly": True,
        "safety_banner": list(APP_V2_MESSAGE_DASHBOARD_SAFETY_LABELS),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def app_v2_message_card_item(row: dict[str, Any]) -> dict[str, Any]:
    item = app_signal_item(row)
    title = _first_text(row, "title", default=item.get("event_label") or "N6 消息卡片")
    summary = _first_text(
        row,
        "message",
        default=f"{item.get('display_name') or item.get('identity_key')} · {item.get('condition_key') or '—'}",
    )
    projection_id = item.get("user_signal_projection_id")
    return {
        "user_signal_card_id": item.get("user_signal_card_id"),
        "user_signal_projection_id": projection_id,
        "card_source": "user_signal_card",
        "authority_source": "user_signal_projection",
        "title": title,
        "summary": summary,
        "event_label": item.get("event_label"),
        "event_time": item.get("event_time"),
        "trade_date": item.get("trade_date"),
        "asset_kind": item.get("asset_kind"),
        "asset_kind_label": item.get("asset_kind_label"),
        "identity_key": item.get("identity_key"),
        "display_code": item.get("display_code"),
        "display_name": item.get("display_name"),
        "direction": item.get("direction"),
        "direction_label": item.get("direction_label"),
        "condition_key": item.get("condition_key"),
        "triggered_periods": item.get("trigger_periods"),
        "triggered_periods_label": _periods_label(item.get("trigger_periods")),
        "primary_trigger_period": item.get("primary_trigger_period"),
        "primary_trigger_period_label": _period_label(item.get("primary_trigger_period")),
        "target_price": item.get("target_price"),
        "buy_target_price": item.get("buy_target_price"),
        "sell_target_price": item.get("sell_target_price"),
        "display_values": item.get("display_values"),
        "current_price": item.get("current_price"),
        "expected_return_pct": item.get("expected_return_pct"),
        "buy_return": item.get("buy_return"),
        "secondary_return": item.get("secondary_return"),
        "sell_return": item.get("sell_return"),
        "trigger_price": item.get("trigger_price"),
        "trigger_pct": item.get("trigger_pct"),
        "action_price": item.get("action_price"),
        "action_pct": item.get("action_pct"),
        "industry_code": item.get("industry_code"),
        "industry_name": item.get("industry_name"),
        "industry_status": item.get("industry_status"),
        "score": item.get("score"),
        "pe_core": item.get("pe_core"),
        "up_ref": item.get("up_ref"),
        "up_ref_label": _period_label(item.get("up_ref")),
        "down_ref": item.get("down_ref"),
        "down_ref_label": _period_label(item.get("down_ref")),
        "projection_message_status": item.get("projection_message_status"),
        "action_state_label": item.get("action_state_label"),
        "action_mark": item.get("action_mark"),
        "action_mark_label": {
            "normal": "普通确认",
            "30m_volume": "30分钟放量确认",
            "30m_shrink": "30分钟缩量确认",
        }.get(str(item.get("action_mark") or ""), "—"),
        "blocked_reason_label": item.get("blocked_reason_label"),
        "quality_status": item.get("quality_status"),
        "source_run_id": item.get("source_run_id"),
        "projection_run_id": item.get("projection_run_id"),
        "detail_href": f"/api/n6/app/v1/signals/{projection_id}" if projection_id else "",
    }


def app_v2_buy_messages_source_policy() -> dict[str, Any]:
    return {
        "allowed_sources": [
            "user_monitor_stock",
            "user_monitor_index",
            "user_monitor_board",
            "user_projection_run",
            "effective_monitor_scope",
        ],
        "forbidden_sources": [
            "common_event_outbox",
            "condition_basis",
            "condition_pool",
            "minute_target_scope",
            "raw K",
            "direct live market",
            "N4/N5 raw fact bypass",
            "notification queue",
        ],
        "principal_scoped": True,
        "effective_monitor_scope": True,
        "monitor_effective_active_required": True,
        "n6_projection_only": True,
        "common_event_outbox_read": False,
        "condition_basis_read": False,
        "condition_pool_read": False,
        "minute_target_scope_read": False,
        "raw_k_read": False,
        "direct_live_market_read": False,
        "n4_raw_fact_bypass": False,
        "n5_raw_fact_bypass": False,
        "notification_queue_read": False,
    }


def app_v2_buy_messages_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    rows: list[dict[str, Any]],
    scope_metadata: dict[str, Any] | None = None,
    selected_asset_kind: str | None = None,
) -> dict[str, Any]:
    candidates = [
        item
        for item in (app_v2_buy_message_item(row) for row in rows)
        if item is not None
    ]
    source_signal_keys = {
        (
            str(item.get("asset_kind") or ""),
            str(item.get("identity_key") or ""),
        )
        for item in candidates
        if item.get("asset_kind") in {"index", "board"}
    }
    sections = {
        "index": {
            "asset_kind": "index",
            "title": "指数买入信号",
            "readonly_observation_only": True,
            "items": [],
        },
        "board": {
            "asset_kind": "board",
            "title": "板块买入信号",
            "readonly_observation_only": True,
            "items": [],
        },
        "stock": {
            "asset_kind": "stock",
            "title": "个股买入信号",
            "readonly_observation_only": True,
            "items": [],
        },
    }
    for item in candidates:
        asset_kind = str(item.get("asset_kind") or "")
        if selected_asset_kind and asset_kind != selected_asset_kind:
            continue
        if asset_kind in {"index", "board"}:
            sections[asset_kind]["items"].append(item)
            continue
        if asset_kind != "stock":
            continue
        source_type = str(item.get("source_type") or "")
        if source_type == "direct":
            sections["stock"]["items"].append(item)
            continue
        if source_type in {"index_linked_stock", "board_linked_stock"}:
            source_key = (
                str(item.get("source_object_kind") or ""),
                str(item.get("source_object_identity_key") or ""),
            )
            if source_key in source_signal_keys:
                sections["stock"]["items"].append(item)
    if selected_asset_kind:
        for asset_kind, section in sections.items():
            if asset_kind != selected_asset_kind:
                section["items"] = []
    for section in sections.values():
        section["count"] = len(section["items"])
    metadata = _app_v2_message_scope_metadata(scope_metadata)
    component = "B Track V2 Buy Messages"
    return {
        "ok": True,
        "component": "b_track_v2_buy_messages_readonly",
        "component_label": _component_label(component),
        "principal": app_principal_model(principal, user=user),
        "scope_mode": "effective_monitor",
        "current_filter_batch": metadata["current_filter_batch"],
        "filters": {"asset_kind": selected_asset_kind} if selected_asset_kind else {},
        "summary": {
            "index_count": len(sections["index"]["items"]),
            "board_count": len(sections["board"]["items"]),
            "stock_count": len(sections["stock"]["items"]),
            "total_count": sum(len(section["items"]) for section in sections.values()),
        },
        "sections": sections,
        "source_policy": app_v2_buy_messages_source_policy(),
        "readonly": True,
        "safety_banner": list(APP_V2_BUY_MESSAGES_SAFETY_LABELS),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def app_v2_buy_message_item(row: dict[str, Any]) -> dict[str, Any] | None:
    item = app_signal_item(row)
    direction = str(item.get("direction") or "").strip().lower()
    signal_type = str(item.get("signal_type") or "").strip().upper()
    if direction not in {"buy", "b_buy"} and not signal_type.startswith("B_BUY"):
        return None
    action_state = str(item.get("action_state") or "").strip()
    blocked_reason = str(item.get("blocked_reason") or "").strip()
    if action_state == "executed":
        status = "executable_readonly"
        status_label = "可进入虚拟买入确认"
    elif action_state == "blocked" and blocked_reason == "amount_confirmation_failed":
        status = "preparation_hint"
        status_label = "买入准备提示"
    else:
        return None
    source_type_raw = _first_available_text(row.get("source_type_raw"), row.get("source_type")) or "single_row"
    source_type = V2_MONITOR_SOURCE_TYPE_BY_RAW.get(source_type_raw, source_type_raw)
    source_type_label = V2_MONITOR_SOURCE_LABEL_BY_TYPE.get(source_type, source_type or "—")
    source_object_kind = _first_available_text(row.get("source_object_kind"))
    if not source_object_kind:
        source_object_kind = V2_MONITOR_SOURCE_OBJECT_KIND_BY_TYPE.get(source_type, "none")
    if source_type == "direct":
        source_object_kind = "none"
    asset_kind = str(item.get("asset_kind") or "")
    readonly_label = (
        "虚拟买入确认入口：后续 gate 开启"
        if asset_kind == "stock" and status == "executable_readonly"
        else "只读观察信号"
    )
    return {
        "asset": item.get("identity_key"),
        "asset_kind": asset_kind,
        "asset_kind_label": item.get("asset_kind_label"),
        "identity_key": item.get("identity_key"),
        "code": item.get("display_code") or item.get("code"),
        "name": item.get("display_name") or item.get("name"),
        "signal_type": item.get("signal_type"),
        "event_time": item.get("event_time"),
        "trigger_price": _first_text(row, "trigger_price"),
        "trigger_period": _first_text(row, "trigger_period", "primary_trigger_period"),
        "triggered_periods": _first_text(row, "triggered_periods"),
        "condition_key": item.get("condition_key"),
        "action_state": action_state,
        "action_state_label": item.get("action_state_label"),
        "blocked_reason": blocked_reason if blocked_reason != "—" else "",
        "blocked_reason_label": item.get("blocked_reason_label"),
        "buy_message_status": status,
        "buy_message_status_label": status_label,
        "source_type_raw": source_type_raw,
        "source_type": source_type,
        "source_type_label": source_type_label,
        "source_object_kind": source_object_kind,
        "source_object_identity_key": row.get("source_object_identity_key"),
        "source_object_name": row.get("source_object_name"),
        "membership_relation_date": row.get("membership_relation_date"),
        "industry_code": _first_text(row, "industry_code", "board_code", default=""),
        "industry_name": _first_text(row, "industry_name", "board_name", default=""),
        "readonly_entry": {
            "enabled": False,
            "label": readonly_label,
        },
        "projection_run_id": item.get("projection_run_id"),
        "source_run_id": item.get("source_run_id"),
    }


def app_v2_message_groups_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    rows: list[dict[str, Any]],
    scope_metadata: dict[str, Any] | None = None,
    include_side_effects: bool = True,
) -> dict[str, Any]:
    items = [app_signal_item(row) for row in rows]
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in items:
        key = (
            str(item.get("asset_kind") or ""),
            str(item.get("direction") or ""),
            str(item.get("event_type") or item.get("source_action_event_type") or ""),
        )
        group = groups.setdefault(
            key,
            {
                "group_key": "|".join(key),
                "asset_kind": key[0],
                "asset_kind_label": _asset_kind_label(key[0]),
                "direction": key[1],
                "direction_label": _direction_label(key[1]),
                "event_type": key[2],
                "event_label": _event_label(key[2]),
                "message_count": 0,
                "items_preview": [],
            },
        )
        group["message_count"] += 1
        if len(group["items_preview"]) < 5:
            group["items_preview"].append(item)
    ordered_groups = sorted(
        groups.values(),
        key=lambda group: (
            str(group.get("asset_kind") or ""),
            str(group.get("direction") or ""),
            str(group.get("event_type") or ""),
        ),
    )
    component = "B Track V2 Monitor Message Groups"
    payload = {
        "ok": True,
        "component": "b_track_monitor_message_groups_v2",
        "component_label": _component_label(component),
        "principal": app_principal_model(principal, user=user),
        "scope_mode": "effective_monitor",
        "group_by": ["asset_kind", "direction", "event_type"],
        "group_count": len(ordered_groups),
        "groups": ordered_groups,
        "current_filter_batch": _app_v2_message_scope_metadata(scope_metadata)["current_filter_batch"],
        "source_policy": app_v2_message_dashboard_source_policy(),
        "readonly": True,
        "safety_banner": list(APP_V2_MESSAGE_DASHBOARD_SAFETY_LABELS),
    }
    if include_side_effects:
        payload["side_effects"] = dict(APP_SIDE_EFFECTS)
    return payload


def app_v2_message_projection_status_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    rows: list[dict[str, Any]],
    scope_metadata: dict[str, Any] | None = None,
    include_side_effects: bool = True,
) -> dict[str, Any]:
    items = [app_signal_item(row) for row in rows]
    metadata = _app_v2_message_scope_metadata(scope_metadata)
    current_batch = metadata["current_filter_batch"]
    expected_for_trade_date = str(current_batch.get("for_trade_date") or "")
    run_ids = [str(item.get("projection_run_id") or "") for item in items if item.get("projection_run_id")]
    latest_run_id = run_ids[0] if run_ids else ""
    card_count = sum(1 for row in rows if row.get("user_signal_card_id"))
    if metadata.get("scope_mode") == "historical_projection":
        status_reason = "historical_projection_covers_trade_date" if items else "no_messages_for_trade_date"
        latest_status = "passed" if items else "empty"
    elif str(current_batch.get("status")) != "ready":
        status_reason = "current_filter_batch_not_ready"
        latest_status = "not_ready"
    elif not items and int(metadata.get("effective_monitor_count") or 0) > 0:
        status_reason = "waiting_projection"
        latest_status = "waiting_projection"
    elif not items:
        status_reason = "no_effective_monitor"
        latest_status = "empty"
    else:
        status_reason = "projection_covers_for_trade_date"
        latest_status = "passed"
    component = "B Track V2 Monitor Projection Status"
    payload = {
        "ok": True,
        "component": "b_track_monitor_projection_status_v2",
        "component_label": _component_label(component),
        "principal": app_principal_model(principal, user=user),
        "scope_mode": metadata["scope_mode"],
        "latest_projection_run_id": latest_run_id,
        "latest_status": latest_status,
        "status_reason": status_reason,
        "expected_for_trade_date": expected_for_trade_date,
        "source_trade_date": current_batch.get("source_trade_date") or "",
        "source_run_id": current_batch.get("source_run_id") or "",
        "projection_count": len(items),
        "card_count": card_count,
        "notification_queue_count": 0,
        "notification_queue_read": False,
        "writes_database": False,
        "source_policy": app_v2_message_dashboard_source_policy(),
        "readonly": True,
        "safety_banner": list(APP_V2_MESSAGE_DASHBOARD_SAFETY_LABELS),
    }
    if include_side_effects:
        payload["side_effects"] = dict(APP_SIDE_EFFECTS)
    return payload


def _app_v2_message_scope_metadata(scope_metadata: dict[str, Any] | None) -> dict[str, Any]:
    metadata = dict(scope_metadata or {})
    excluded_reason_counts = {
        "message_trade_date_missing": 0,
        "message_trade_date_mismatch": 0,
        "monitor_expired": 0,
    }
    excluded_reason_counts.update(metadata.get("excluded_reason_counts") or {})
    return {
        "scope_mode": metadata.get("scope_mode") or "effective_monitor",
        "current_filter_batch": _app_v2_message_current_batch(metadata.get("current_filter_batch") or {}),
        "effective_monitor_count": int(metadata.get("effective_monitor_count") or 0),
        "expired_monitor_count": int(metadata.get("expired_monitor_count") or 0),
        "matched_signal_count": int(metadata.get("matched_signal_count") or 0),
        "selected_trade_date": str(metadata.get("selected_trade_date") or ""),
        "available_trade_dates": [
            str(value)
            for value in metadata.get("available_trade_dates") or []
            if str(value or "").strip()
        ],
        "date_policy_blocker": str(metadata.get("date_policy_blocker") or ""),
        "date_policy_message": str(metadata.get("date_policy_message") or ""),
        "excluded_reason_counts": {
            key: int(value or 0)
            for key, value in excluded_reason_counts.items()
        },
    }


def _app_v2_message_current_batch(raw_batch: dict[str, Any]) -> dict[str, Any]:
    batch_by_asset: dict[str, dict[str, str]] = {}
    for asset_kind in ("stock", "index", "board"):
        row = raw_batch.get(asset_kind) if isinstance(raw_batch, dict) else {}
        row = row if isinstance(row, dict) else {}
        batch_by_asset[asset_kind] = {
            "source_trade_date": str(row.get("source_trade_date") or ""),
            "for_trade_date": str(row.get("for_trade_date") or ""),
            "source_run_id": str(row.get("source_run_id") or ""),
        }
    values = [row for row in batch_by_asset.values() if row.get("for_trade_date")]
    source_dates = {row["source_trade_date"] for row in values if row.get("source_trade_date")}
    for_dates = {row["for_trade_date"] for row in values if row.get("for_trade_date")}
    source_run_ids = {row["source_run_id"] for row in values if row.get("source_run_id")}
    first = values[0] if values else {"source_trade_date": "", "for_trade_date": "", "source_run_id": ""}
    status = "ready" if values and len(for_dates) == 1 else "not_ready"
    if status == "ready" and (len(source_dates) > 1 or len(source_run_ids) > 1):
        status = "mixed"
    return {
        "status": status,
        "source_trade_date": first.get("source_trade_date") or "",
        "for_trade_date": first.get("for_trade_date") or "",
        "source_run_id": first.get("source_run_id") or "",
        "by_asset": batch_by_asset,
    }


def _app_v2_message_summary(items: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    event_counts = {
        "ActionExecuted": 0,
        "ActionBlocked": 0,
        "ActionEligible": 0,
        "ActionSkipped": 0,
        "TriggerMatched": 0,
        "TriggerPendingMarketData": 0,
        "TriggerStateChanged": 0,
    }
    asset_kind_counts = {"stock": 0, "index": 0, "board": 0}
    direction_counts = {"buy": 0, "sell": 0}
    for item in items:
        event_type = str(item.get("event_type") or item.get("source_action_event_type") or "")
        if event_type in event_counts:
            event_counts[event_type] += 1
        else:
            event_counts[event_type] = event_counts.get(event_type, 0) + 1
        asset_kind = str(item.get("asset_kind") or "")
        direction = str(item.get("direction") or "")
        if asset_kind:
            asset_kind_counts[asset_kind] = asset_kind_counts.get(asset_kind, 0) + 1
        if direction:
            direction_counts[direction] = direction_counts.get(direction, 0) + 1
    excluded = metadata["excluded_reason_counts"]
    excluded_message_count = int(excluded.get("message_trade_date_missing") or 0) + int(
        excluded.get("message_trade_date_mismatch") or 0
    )
    return {
        "effective_monitor_count": int(metadata.get("effective_monitor_count") or 0),
        "expired_monitor_count": int(metadata.get("expired_monitor_count") or 0),
        "matched_signal_count": len(items),
        "today_message_count": len(items),
        "action_executed_count": int(event_counts.get("ActionExecuted") or 0),
        "action_blocked_count": int(event_counts.get("ActionBlocked") or 0),
        "action_eligible_count": int(event_counts.get("ActionEligible") or 0),
        "action_skipped_count": int(event_counts.get("ActionSkipped") or 0),
        "trigger_matched_count": int(event_counts.get("TriggerMatched") or 0),
        "pending_market_data_count": int(event_counts.get("TriggerPendingMarketData") or 0),
        "state_changed_count": int(event_counts.get("TriggerStateChanged") or 0),
        "excluded_message_count": excluded_message_count,
        "event_counts": event_counts,
        "asset_kind_counts": asset_kind_counts,
        "direction_counts": direction_counts,
        "excluded_reason_counts": excluded,
    }


def _app_v2_message_empty_state(
    *,
    summary: dict[str, Any],
    current_filter_batch: dict[str, Any],
    projection_status: dict[str, Any],
    excluded_reason_counts: dict[str, int],
    scope_mode: str = "effective_monitor",
) -> dict[str, str]:
    if scope_mode == "historical_projection":
        if int(summary.get("matched_signal_count") or 0) > 0:
            return {"reason": "", "message": ""}
        reason = "no_messages_for_trade_date"
    elif str(current_filter_batch.get("status")) == "not_ready":
        reason = "current_filter_batch_not_ready"
    elif int(summary.get("effective_monitor_count") or 0) <= 0:
        reason = "no_effective_monitor"
    elif int(excluded_reason_counts.get("message_trade_date_missing") or 0) > 0:
        reason = "message_trade_date_missing"
    elif int(summary.get("matched_signal_count") or 0) <= 0 and projection_status.get("status_reason") == "waiting_projection":
        reason = "waiting_projection"
    elif int(summary.get("matched_signal_count") or 0) <= 0:
        reason = "no_n6_user_messages"
    else:
        return {"reason": "", "message": ""}
    return {"reason": reason, "message": APP_V2_MESSAGE_EMPTY_STATES[reason]}


def app_signal_detail_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    component = "B Track Signal Detail"
    return {
        "ok": True,
        "component": component,
        "component_label": _component_label(component),
        "principal": app_principal_model(principal, user=user),
        "signal": app_signal_item(row),
        "source_policy": app_signal_source_policy(),
        "readonly": True,
        "safety_banner": list(APP_SAFETY_LABELS),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def app_watchlist_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    signal_items = [app_signal_item(row) for row in rows]
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for signal in signal_items:
        identity_key = str(signal.get("identity_key") or "").strip()
        if not identity_key or identity_key in seen:
            continue
        seen.add(identity_key)
        items.append(app_watchlist_item(signal))
    component = "B Track Watchlist"
    return {
        "ok": True,
        "component": component,
        "component_label": _component_label(component),
        "principal": app_principal_model(principal, user=user),
        "items": items,
        "controls": {
            "add_enabled": False,
            "delete_enabled": False,
            "sort_enabled": False,
            "sort_persist_enabled": False,
            "source": "reviewed_n6_projection_only",
        },
        "readonly": True,
        "safety_banner": list(APP_SAFETY_LABELS),
        "source_policy": app_signal_source_policy(),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def app_realtime_scope_item(row: dict[str, Any]) -> dict[str, Any]:
    status = _first_text(row, "status", default="active")
    return {
        "realtime_scope_id": row.get("realtime_scope_id"),
        "asset_kind": _first_text(row, "asset_kind", default="index"),
        "asset_kind_label": _asset_kind_label(_first_text(row, "asset_kind", default="index")),
        "identity_key": _first_text(row, "identity_key"),
        "display_name": _first_text(row, "display_name", "name", default=_first_text(row, "identity_key")),
        "status": status,
        "status_label": _state_label(status),
        "is_default_seed": bool(row.get("is_default_seed")),
        "source_type": _first_text(row, "source_type", default="manual"),
        "controls": {
            "delete_enabled": bool(row.get("realtime_scope_id")) and status == "active",
        },
    }


def app_realtime_scope_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    result: dict[str, Any],
    write_enabled: bool = False,
) -> dict[str, Any]:
    items = [app_realtime_scope_item(row) for row in result.get("items") or []]
    component = "B Track Realtime Scope"
    return {
        "ok": True,
        "component": component,
        "component_label": _component_label(component),
        "principal": app_principal_model(principal, user=user),
        "items": items,
        "summary": {
            "count": len(items),
            "default_seed_count": sum(1 for item in items if item.get("is_default_seed")),
        },
        "controls": {
            "write_route_registered": True,
            "write_route_enabled": bool(write_enabled),
            "add_enabled": bool(write_enabled),
            "delete_enabled": bool(write_enabled),
            "source": "user_realtime_monitor_scope",
            "scope_notice": "仅影响当前交易日实时消息可见性，不代表交易意图",
        },
        "readonly": not bool(write_enabled),
        "safety_banner": list(APP_SAFETY_LABELS),
        "source_policy": app_signal_source_policy(),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def app_status_monitor_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    rows: list[dict[str, Any]],
    filters: dict[str, Any],
) -> dict[str, Any]:
    effective_filters = {
        key: str(filters.get(key) or "").strip()
        for key in ("asset_kind", "trade_date")
        if str(filters.get(key) or "").strip()
    }
    refresh_query = urlencode(effective_filters)
    items = []
    for row in rows:
        trigger_pct = number_or_none(row.get("trigger_pct"))
        trigger_price = number_or_none(row.get("trigger_price"))
        items.append(
            {
                "trigger_time": _first_text(row, "trigger_time"),
                "asset_kind": _first_text(row, "asset_kind"),
                "asset_kind_label": _asset_kind_label(_first_text(row, "asset_kind")),
                "identity_key": _first_text(row, "identity_key"),
                "asset_code": _first_text(row, "asset_code"),
                "asset_name": _first_text(row, "asset_name"),
                "direction": _first_text(row, "direction"),
                "direction_label": _direction_label(_first_text(row, "direction")),
                "trigger_pct": f"{trigger_pct:.6f}" if trigger_pct is not None else None,
                "trigger_pct_display": f"{trigger_pct:.2f}%" if trigger_pct is not None else "—",
                "trigger_price": f"{trigger_price:.6f}" if trigger_price is not None else None,
                "trigger_period": _first_text(row, "trigger_period"),
                "triggered_periods": [str(value) for value in (row.get("triggered_periods") or [])],
                "episode_count": int(row.get("episode_count") or 0),
            }
        )
    status_summary = {"active": len(items), "pending_market_data": 0, "inactive": 0}
    component = "B Track Status Monitor"
    return {
        "ok": True,
        "component": component,
        "component_label": _component_label(component),
        "principal": app_principal_model(principal, user=user),
        "filters": effective_filters,
        "refresh_href": "/n6/app/status-monitor" + (f"?{refresh_query}" if refresh_query else ""),
        "status_summary": status_summary,
        "items": items,
        "write_controls": {
            "projection_write_enabled": False,
            "card_write_enabled": False,
            "outbox_consume_enabled": False,
            "outbox_status_update_enabled": False,
            "worker_enabled": False,
        },
        "readonly": True,
        "safety_banner": list(APP_SAFETY_LABELS),
        "source_policy": {
            "allowed_sources": [
                "n6_trigger_status_current",
                "principal monitor objects",
                "realtime monitor scope",
                "current holdings",
            ],
            "forbidden_sources": list(APP_FORBIDDEN_SIGNAL_SOURCES),
        },
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


AI_AGENT_PUBLIC_PRIVATE_KEYS = frozenset(
    {
        "chain_of_thought",
        "credential",
        "credentials",
        "dsn",
        "owner_user_id",
        "password",
        "pgpass",
        "principal_id",
        "prompt",
        "raw_prompt",
        "reasoning",
        "session",
        "session_hash",
        "session_token",
        "system_prompt",
        "token",
        "user_id",
    }
)


def _ai_agent_public_bigint(value: Any, field_name: str) -> str | None:
    try:
        return canonical_bigint_id(value, field_name=field_name)
    except ValueError:
        return None


def _ai_agent_public_json(value: Any, *, depth: int = 0) -> Any:
    """Return bounded public evidence without operational or identity secrets."""
    if depth > 4:
        return None
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, (float, Decimal)):
        return number_or_none(value)
    if isinstance(value, str):
        return value[:2000]
    if isinstance(value, (list, tuple)):
        return [
            item
            for item in (
                _ai_agent_public_json(entry, depth=depth + 1)
                for entry in list(value)[:50]
            )
            if item is not None
        ]
    if isinstance(value, dict):
        public: dict[str, Any] = {}
        for raw_key, entry in list(value.items())[:100]:
            key = str(raw_key or "").strip()
            normalized_key = key.lower()
            if (
                not key
                or normalized_key in AI_AGENT_PUBLIC_PRIVATE_KEYS
                or any(
                    fragment in normalized_key
                    for fragment in (
                        "api_key",
                        "chain_of_thought",
                        "credential",
                        "dsn",
                        "password",
                        "private_key",
                        "prompt",
                        "reasoning",
                        "secret",
                        "session",
                        "token",
                    )
                )
            ):
                continue
            cleaned = _ai_agent_public_json(entry, depth=depth + 1)
            if cleaned is not None:
                public[key] = cleaned
        return public
    return str(value)[:2000]


def _ai_agent_public_position(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "virtual_position_id": _ai_agent_public_bigint(
            row.get("virtual_position_id"), "virtual_position_id"
        ),
        "identity_key": _first_text(row, "identity_key"),
        "stock_code": _first_text(row, "stock_code", "display_code"),
        "display_name": _first_text(row, "display_name", "stock_name"),
        "quantity": number_or_none(row.get("quantity")),
        "sellable_quantity": number_or_none(
            row.get("sellable_quantity")
            if row.get("sellable_quantity") is not None
            else row.get("available_quantity")
        ),
        "t1_locked_quantity": number_or_none(
            row.get("t1_locked_quantity")
            if row.get("t1_locked_quantity") is not None
            else row.get("locked_quantity")
        ),
        "average_cost": number_or_none(row.get("average_cost")),
        "current_price": number_or_none(row.get("current_price")),
        "market_value": number_or_none(row.get("market_value")),
        "unrealized_pnl": number_or_none(row.get("unrealized_pnl")),
        "unrealized_return_pct": number_or_none(row.get("unrealized_return_pct")),
        "quote_status": _first_text(row, "quote_status", "quality_status"),
        "target_price": number_or_none(
            row.get("target_price")
            if row.get("target_price") is not None
            else row.get("locked_target_price")
        ),
        "target_price_status": _first_text(row, "target_price_status"),
        "stop_loss_price": number_or_none(row.get("stop_loss_price")),
        "stop_loss_status": _first_text(row, "stop_loss_status"),
        "holding_episode_no": row.get("holding_episode_no"),
        "first_open_trade_date": _first_text(row, "first_open_trade_date"),
        "updated_at": display_datetime(row.get("updated_at") or row.get("quote_minute")),
    }


def _ai_agent_public_trade(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "virtual_trade_id": _ai_agent_public_bigint(
            row.get("virtual_trade_id"), "virtual_trade_id"
        ),
        "ai_decision_id": _ai_agent_public_bigint(
            row.get("ai_decision_id") or row.get("source_ai_decision_id"),
            "ai_decision_id",
        ),
        "trade_time": display_datetime(row.get("trade_time") or row.get("created_at")),
        "identity_key": _first_text(row, "identity_key"),
        "display_name": _first_text(row, "display_name", "stock_name"),
        "trade_side": _first_text(row, "trade_side", "proposal_side"),
        "filled_quantity": number_or_none(row.get("filled_quantity")),
        "filled_price": number_or_none(row.get("filled_price")),
        "gross_amount": number_or_none(row.get("gross_amount")),
        "total_fee_amount": number_or_none(row.get("total_fee_amount")),
        "net_amount": number_or_none(
            row.get("net_amount")
            if row.get("net_amount") is not None
            else row.get("gross_amount")
        ),
        "trade_status": _first_text(row, "trade_status"),
        "reason_summary": _first_text(row, "reason_summary"),
    }


def app_ai_agent_public_decision_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "ai_decision_id": _ai_agent_public_bigint(
            row.get("ai_decision_id") or row.get("decision_id"), "ai_decision_id"
        ),
        "trade_date": _first_text(row, "trade_date", "for_trade_date"),
        "event_time": display_datetime(
            row.get("event_time") or row.get("decided_at") or row.get("created_at")
        ),
        "decision_type": _first_text(row, "decision_type"),
        "identity_key": _first_text(row, "identity_key"),
        "display_name": _first_text(row, "display_name", "stock_name"),
        "confidence": number_or_none(row.get("confidence")),
        "reason_summary": _first_text(row, "reason_summary"),
        "evidence": _ai_agent_public_json(row.get("evidence") or []),
        "counter_evidence": _ai_agent_public_json(row.get("counter_evidence") or []),
        "risk_status": _first_text(row, "risk_status"),
        "risk_reason": _first_text(row, "risk_reason"),
        "risk_assessment": _ai_agent_public_json(row.get("risk_assessment") or {}),
        "proposal_status": _first_text(
            row, "proposal_status", default="—"
        ),
        "execution_status": _first_text(
            row, "execution_status", "decision_status"
        ),
        "source_signal_projection_id": _ai_agent_public_bigint(
            row.get("source_signal_projection_id"), "source_signal_projection_id"
        ),
        "source_virtual_position_id": _ai_agent_public_bigint(
            row.get("source_virtual_position_id"), "source_virtual_position_id"
        ),
        "source_virtual_trade_proposal_id": _ai_agent_public_bigint(
            row.get("source_virtual_trade_proposal_id"),
            "source_virtual_trade_proposal_id",
        ),
        "ai_decision_run_id": _ai_agent_public_bigint(
            row.get("ai_decision_run_id") or row.get("decision_run_id"),
            "ai_decision_run_id",
        ),
        "ai_context_snapshot_id": _ai_agent_public_bigint(
            row.get("ai_context_snapshot_id") or row.get("context_snapshot_id"),
            "ai_context_snapshot_id",
        ),
        "strategy_version": _first_text(row, "strategy_version"),
    }


def _ai_agent_public_daily_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "ai_daily_summary_id": _ai_agent_public_bigint(
            row.get("ai_daily_summary_id") or row.get("daily_summary_id"),
            "ai_daily_summary_id",
        ),
        "trade_date": _first_text(row, "trade_date", "summary_date"),
        "summary_text": _first_text(row, "summary_text", "daily_summary"),
        "decision_count": int(row.get("decision_count") or 0),
        "trade_count": int(row.get("trade_count") or 0),
        "net_return_pct": number_or_none(row.get("net_return_pct")),
        "max_drawdown_pct": number_or_none(row.get("max_drawdown_pct")),
        "turnover_pct": number_or_none(row.get("turnover_pct")),
        "risk_adjusted_score": number_or_none(row.get("risk_adjusted_score")),
        "total_asset_value": number_or_none(row.get("total_asset_value")),
        "current_cash": number_or_none(row.get("current_cash")),
        "position_market_value": number_or_none(row.get("position_market_value")),
        "daily_net_pnl": number_or_none(row.get("daily_net_pnl")),
        "success_reasons": _ai_agent_public_json(
            row.get("success_reasons") or []
        ),
        "lessons": _ai_agent_public_json(
            row.get("lessons") or row.get("trade_review") or []
        ),
        "next_day_watch_plan": _ai_agent_public_json(
            row.get("next_day_watch_plan") or row.get("next_trade_focus") or []
        ),
        "strategy_version": _first_text(row, "strategy_version"),
        "strategy_hash": _first_text(row, "strategy_hash"),
        "knowledge_bundle_version": _first_text(
            row, "knowledge_bundle_version"
        ),
        "knowledge_bundle_hash": _first_text(
            row, "knowledge_bundle_hash"
        ),
        "generated_at": display_datetime(row.get("generated_at") or row.get("created_at")),
    }


def app_ai_agent_public_model(result: dict[str, Any] | None) -> dict[str, Any]:
    source = result if isinstance(result, dict) else {}
    profile_source = source.get("profile") if isinstance(source.get("profile"), dict) else {}
    account_source = source.get("account") if isinstance(source.get("account"), dict) else {}
    strategy_source = (
        source.get("strategy") if isinstance(source.get("strategy"), dict) else {}
    )
    runtime_source = (
        source.get("runtime") if isinstance(source.get("runtime"), dict) else {}
    )
    performance_source = (
        source.get("performance") if isinstance(source.get("performance"), dict) else {}
    )
    ai_user_id = _ai_agent_public_bigint(
        profile_source.get("ai_user_id"), "ai_user_id"
    )
    profile_status = _first_text(
        profile_source,
        "ai_status",
        "status",
        default="not_registered" if ai_user_id is None else "disabled",
    )
    profile_mode = _first_text(
        profile_source,
        "agent_mode",
        "mode",
        default=_first_text(runtime_source, "run_mode"),
    )
    runtime_run_status = _first_text(runtime_source, "run_status")
    pause_reason = _first_text(
        profile_source,
        "pause_reason",
        default=(
            runtime_run_status
            if runtime_run_status not in {"—", "passed", "recorded"}
            else "—"
        ),
    )
    if profile_status == "sandbox_only":
        if profile_mode == "disabled":
            profile_mode = "shadow"
        if pause_reason == "ai_user_inactive":
            pause_reason = {
                "started": "agent_run_in_progress",
                "rejected": "agent_run_rejected",
                "failed": "agent_run_failed",
            }.get(
                runtime_run_status,
                (
                    "—"
                    if runtime_run_status in {"—", "passed", "recorded"}
                    else "agent_run_unavailable"
                ),
            )
    last_success_at = (
        display_datetime(
            profile_source.get("last_success_at")
            or runtime_source.get("last_finished_at")
        )
        if runtime_run_status in {"passed", "recorded"}
        else "—"
    )
    profile = {
        "ai_user_id": ai_user_id,
        "display_name": _first_text(
            profile_source,
            "ai_name",
            "display_name",
            "principal_label",
            default="AI模拟投资员",
        ),
        "status": profile_status,
        "mode": profile_mode,
        "model_label": _first_text(
            profile_source,
            "model_label",
            "model_adapter",
            default=_first_text(runtime_source, "model_adapter"),
        ),
        "model_version": _first_text(
            profile_source,
            "model_version",
            default=_first_text(runtime_source, "model_version"),
        ),
        "strategy_version": _first_text(
            profile_source,
            "strategy_version",
            default=_first_text(strategy_source, "policy_version"),
        ),
        "last_success_at": last_success_at,
        "pause_reason": pause_reason,
    }
    account = {
        "virtual_account_id": _ai_agent_public_bigint(
            account_source.get("virtual_account_id"), "virtual_account_id"
        ),
        "account_name": _first_text(
            account_source, "account_name", default="AI独立模拟账户"
        ),
        "account_status": _first_text(account_source, "account_status", "status"),
        "currency": _first_text(
            account_source, "currency", "base_currency", default="CNY"
        ),
        "initial_cash": number_or_none(account_source.get("initial_cash")),
        "cash_balance": number_or_none(
            account_source.get("cash_balance")
            if account_source.get("cash_balance") is not None
            else account_source.get("total_cash")
            if account_source.get("total_cash") is not None
            else account_source.get("available_cash")
        ),
        "available_cash": number_or_none(account_source.get("available_cash")),
        "frozen_cash": number_or_none(account_source.get("frozen_cash")),
        "market_value": number_or_none(
            account_source.get("market_value")
            if account_source.get("market_value") is not None
            else account_source.get("position_market_value")
        ),
        "total_equity": number_or_none(
            account_source.get("total_equity")
            if account_source.get("total_equity") is not None
            else account_source.get("total_asset_value")
        ),
        "net_pnl": number_or_none(account_source.get("net_pnl")),
        "total_return_pct": number_or_none(
            account_source.get("total_return_pct")
            if account_source.get("total_return_pct") is not None
            else performance_source.get("net_return_pct")
        ),
        "max_drawdown_pct": number_or_none(
            account_source.get("max_drawdown_pct")
            if account_source.get("max_drawdown_pct") is not None
            else performance_source.get("max_drawdown_pct")
        ),
        "valuation_status": _first_text(
            account_source, "valuation_status", default="not_ready"
        ),
        "not_ready_position_count": int(
            account_source.get("not_ready_position_count") or 0
        ),
        "as_of": display_datetime(
            account_source.get("as_of")
            or account_source.get("snapshot_time")
            or account_source.get("updated_at")
        ),
    }
    performance = {
        "trade_date": _first_text(performance_source, "trade_date", "summary_date"),
        "total_asset_value": number_or_none(
            performance_source.get("total_asset_value")
        ),
        "current_cash": number_or_none(performance_source.get("current_cash")),
        "position_market_value": number_or_none(
            performance_source.get("position_market_value")
        ),
        "daily_net_pnl": number_or_none(performance_source.get("daily_net_pnl")),
        "net_return_pct": number_or_none(performance_source.get("net_return_pct")),
        "max_drawdown_pct": number_or_none(
            performance_source.get("max_drawdown_pct")
        ),
        "turnover_pct": number_or_none(performance_source.get("turnover_pct")),
        "risk_adjusted_score": number_or_none(
            performance_source.get("risk_adjusted_score")
        ),
        "total_trade_count": int(performance_source.get("total_trade_count") or 0),
        "winning_trade_count": int(
            performance_source.get("winning_trade_count") or 0
        ),
        "as_of": display_datetime(
            performance_source.get("as_of")
            or performance_source.get("calculated_at")
        ),
    }
    strategy = {
        "strategy_id": _ai_agent_public_bigint(
            strategy_source.get("strategy_id"), "strategy_id"
        ),
        "strategy_name": _first_text(strategy_source, "strategy_name"),
        "policy_version": _first_text(strategy_source, "policy_version"),
        "policy_hash": _first_text(strategy_source, "policy_hash"),
        "status": _first_text(strategy_source, "status"),
        "risk_labels": _ai_agent_public_json(
            strategy_source.get("risk_labels") or []
        ),
    }
    runtime = {
        "latest_run_id": _ai_agent_public_bigint(
            runtime_source.get("latest_run_id"), "ai_decision_run_id"
        ),
        "run_mode": _first_text(runtime_source, "run_mode"),
        "run_status": _first_text(runtime_source, "run_status"),
        "model_adapter": _first_text(runtime_source, "model_adapter"),
        "model_version": _first_text(runtime_source, "model_version"),
        "last_started_at": display_datetime(runtime_source.get("last_started_at")),
        "last_finished_at": display_datetime(runtime_source.get("last_finished_at")),
    }
    positions = [
        _ai_agent_public_position(row)
        for row in (source.get("positions") or [])
        if isinstance(row, dict)
    ]
    trades = [
        _ai_agent_public_trade(row)
        for row in (source.get("trades") or [])
        if isinstance(row, dict)
    ]
    decisions = [
        app_ai_agent_public_decision_item(row)
        for row in (source.get("decisions") or [])
        if isinstance(row, dict)
    ]
    daily_summaries = [
        _ai_agent_public_daily_summary(row)
        for row in (source.get("daily_summaries") or [])
        if isinstance(row, dict)
    ]
    return {
        "ok": bool(source.get("ok", True)),
        "component": "B Track AI Agent",
        "component_label": _component_label("B Track AI Agent"),
        "contract_version": _first_text(
            source, "contract_version", default="n6-ai-agent-public-v1"
        ),
        "status": profile["status"],
        "profile": profile,
        "account": account,
        "positions": positions,
        "trades": trades,
        "decisions": decisions,
        "daily_summaries": daily_summaries,
        "performance": performance,
        "strategy": strategy,
        "runtime": runtime,
        "public_scope": "shared_ai_virtual_account",
        "readonly": True,
        "empty_state": (
            ""
            if ai_user_id is not None
            else "AI身份和独立模拟账户尚未初始化，当前没有可展示记录。"
        ),
        "controls": {
            "proposal_enabled": False,
            "confirm_enabled": False,
            "pause_enabled": False,
            "strategy_edit_enabled": False,
            "account_edit_enabled": False,
            "real_trade_enabled": False,
        },
        "disclaimer": list(AI_AGENT_PUBLIC_DISCLAIMER),
        "safety_banner": list(APP_SAFETY_LABELS),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def app_ai_agent_public_section_model(
    payload: dict[str, Any],
    section: str,
) -> dict[str, Any]:
    section_key = "daily_summaries" if section == "daily-summaries" else section
    allowed = {
        "overview",
        "positions",
        "trades",
        "decisions",
        "daily_summaries",
        "performance",
    }
    if section_key not in allowed:
        raise ValueError("invalid_ai_agent_section")
    common = {
        "ok": payload["ok"],
        "component": payload["component"],
        "component_label": payload["component_label"],
        "contract_version": payload["contract_version"],
        "public_scope": payload["public_scope"],
        "readonly": True,
        "disclaimer": list(payload["disclaimer"]),
    }
    if section_key == "overview":
        return {
            **common,
            "section": "overview",
            "profile": payload["profile"],
            "account": payload["account"],
            "strategy": payload["strategy"],
            "runtime": payload["runtime"],
            "empty_state": payload["empty_state"],
            "controls": payload["controls"],
        }
    return {
        **common,
        "section": section,
        section_key: payload[section_key],
    }


def app_ai_agent_public_decision_detail_model(
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    source = result if isinstance(result, dict) else {}
    row = source.get("decision") or source.get("item")
    decision = (
        app_ai_agent_public_decision_item(row)
        if isinstance(row, dict)
        else None
    )
    return {
        "ok": decision is not None,
        "component": "B Track AI Agent Decision Detail",
        "contract_version": _first_text(
            source, "contract_version", default="n6-ai-agent-public-v1"
        ),
        "public_scope": "shared_ai_virtual_account",
        "readonly": True,
        "decision": decision,
        "disclaimer": list(AI_AGENT_PUBLIC_DISCLAIMER),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def app_ai_users_model(principal: dict[str, Any], *, user: dict[str, Any]) -> dict[str, Any]:
    component = "B Track AI Users"
    return {
        "ok": True,
        "component": component,
        "component_label": _component_label(component),
        "principal": app_principal_model(principal, user=user),
        "status": "readonly_shell",
        "status_label": _state_label("readonly_shell"),
        "mode": "shadow_observer",
        "mode_label": "只读观察员",
        "items": [
            {
                "ai_user_id": "b_track_shadow_observer",
                "display_name": "B轨只读观察员",
                "role": "shadow_observer",
                "role_label": "只读观察员",
                "status": "readonly",
                "status_label": _state_label("readonly"),
                "scope": "principal",
                "source": "reviewed_n6_projection_only",
                "can_generate_signal": False,
                "can_generate_advice": False,
                "can_trade": False,
                "can_update_position": False,
            }
        ],
        "observer_policy": {
            "source": "reviewed_n6_projection_only",
            "generated_signal_enabled": False,
            "investment_advice_enabled": False,
            "auto_trade_enabled": False,
            "order_enabled": False,
            "trade_enabled": False,
            "position_update_enabled": False,
            "real_trade_enabled": False,
        },
        "readonly": True,
        "safety_banner": list(APP_SAFETY_LABELS),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def app_status_monitor_item(signal: dict[str, Any]) -> dict[str, Any]:
    evidence = signal.get("evidence_chain") or {}
    n4 = evidence.get("N4_trigger") or {}
    n5 = evidence.get("N5_action") or {}
    current_status = _status_monitor_current_status(signal)
    n5_event_type = _first_text(n5, "event_type")
    n5_action_state = _first_text(n5, "action_state")
    n5_blocked_reason = _first_text(n5, "blocked_reason")
    return {
        "asset_kind": _first_text(signal, "asset_kind"),
        "asset_kind_label": _asset_kind_label(_first_text(signal, "asset_kind")),
        "identity_key": _first_text(signal, "identity_key"),
        "display_name": _first_text(signal, "display_name", "name"),
        "display_code": _first_text(signal, "display_code", "code"),
        "current_status": current_status,
        "current_status_label": _state_label(current_status),
        "trigger_live": current_status == "active",
        "n4_event": {
            "source": _first_text(n4, "source"),
            "source_run_id": _first_text(n4, "source_run_id"),
            "event_id": _first_text(n4, "event_id"),
            "raw_fact_bypass": bool(n4.get("raw_fact_bypass")),
        },
        "n5_relationship": {
            "source": _first_text(n5, "source"),
            "source_run_id": _first_text(n5, "source_run_id"),
            "event_id": _first_text(n5, "event_id"),
            "event_type": n5_event_type,
            "event_label": _event_label(n5_event_type),
            "action_state": n5_action_state,
            "action_state_label": _state_label(n5_action_state),
            "action_mark": _first_text(n5, "action_mark"),
            "blocked_reason": n5_blocked_reason,
            "blocked_reason_label": _blocked_reason_label(n5_blocked_reason),
            "raw_fact_bypass": bool(n5.get("raw_fact_bypass")),
        },
        "evidence_chain": evidence,
        "quality_status": _first_text(signal, "quality_status"),
        "source_run_id": _first_text(signal, "source_run_id"),
        "projection_run_id": _first_text(signal, "projection_run_id"),
        "event_time": _first_text(signal, "event_time"),
        "readonly": True,
    }


def app_watchlist_item(signal: dict[str, Any]) -> dict[str, Any]:
    evidence = signal.get("evidence_chain") or {}
    n2_source = evidence.get("N2_display_basis") or {}
    condition_trace = signal.get("condition_trace") or {}
    status = _watchlist_status(signal)
    action_state = _first_text(signal, "action_state")
    blocked_reason = _first_text(signal, "blocked_reason")
    recent_event_type = _first_text(signal, "event_type", "source_action_event_type")
    return {
        "asset_kind": _first_text(signal, "asset_kind"),
        "asset_kind_label": _asset_kind_label(_first_text(signal, "asset_kind")),
        "identity_key": _first_text(signal, "identity_key"),
        "display_name": _first_text(signal, "display_name", "name"),
        "display_code": _first_text(signal, "display_code", "code"),
        "status": status,
        "status_label": _watchlist_status_label(status),
        "action": {
            "action_state": action_state,
            "action_state_label": _state_label(action_state),
            "action_mark": _first_text(signal, "action_mark"),
            "blocked_reason": blocked_reason,
            "blocked_reason_label": _blocked_reason_label(blocked_reason),
            "label": _watchlist_status_label(status),
        },
        "condition_source": {
            "display_cache_source": _first_text(n2_source, "source"),
            "membership_cache_source": _first_text(n2_source, "membership_source"),
            "condition_key": _first_text(condition_trace, "condition_key"),
            "condition_family": _first_text(condition_trace, "condition_family"),
            "rendering_policy": _first_text(condition_trace, "rendering_policy"),
        },
        "recent_signal": {
            "user_signal_projection_id": signal.get("user_signal_projection_id"),
            "source_action_event_type": recent_event_type,
            "event_label": _event_label(recent_event_type),
            "event_time": _first_text(signal, "event_time"),
            "source_run_id": _first_text(signal, "source_run_id"),
            "projection_run_id": _first_text(signal, "projection_run_id"),
            "tags": list(signal.get("tags") or []),
        },
        "advice_enabled": False,
        "order_enabled": False,
        "position_update_enabled": False,
        "readonly": True,
    }


def _watchlist_status(signal: dict[str, Any]) -> str:
    action_state = str(signal.get("action_state") or "").strip()
    blocked_reason = str(signal.get("blocked_reason") or "").strip()
    tags = set(signal.get("tags") or [])
    if action_state == "executed" or any("市场动作确认成立" in str(tag) for tag in tags):
        return "market_action_confirmed"
    if blocked_reason == "metric_missing" or any("等待行情证据" in str(tag) for tag in tags):
        return "pending_market_data"
    if action_state == "blocked" or any("市场动作未确认" in str(tag) for tag in tags):
        return "market_action_not_confirmed"
    return "state_changed"


def _status_monitor_current_status(signal: dict[str, Any]) -> str:
    action_state = str(signal.get("action_state") or "").strip()
    event_type = str(signal.get("event_type") or signal.get("source_action_event_type") or "").strip()
    blocked_reason = str(signal.get("blocked_reason") or "").strip()
    tags = set(signal.get("tags") or [])
    if (
        blocked_reason == "metric_missing"
        or event_type == "TriggerPendingMarketData"
        or any("等待行情证据" in str(tag) for tag in tags)
    ):
        return "pending_market_data"
    if action_state in {"skipped", "expired"}:
        return "inactive"
    if event_type == "TriggerStateChanged" and action_state not in {"eligible", "blocked", "executed"}:
        return "inactive"
    return "active"


def app_signal_item(row: dict[str, Any]) -> dict[str, Any]:
    row = scrub_retired_strategy_center_private_fields(row)
    item = signal_list_item(row)
    item["user_signal_projection_id"] = canonical_bigint_id(
        row.get("user_signal_projection_id"),
        field_name="user_signal_projection_id",
        required=True,
    )
    card_payload = _json_object(row.get("card_payload_json"))
    display_payload = _json_object(row.get("display_payload_json"))
    for field in APP_SIGNAL_FROZEN_PROJECTION_FIELDS:
        value = card_payload.get(field)
        if value is None:
            value = display_payload.get(field)
        if value is None:
            value = item.get(field)
        if value is None:
            value = row.get(field)
        item[field] = value
    item["user_signal_card_id"] = canonical_bigint_id(
        row.get("user_signal_card_id"),
        field_name="user_signal_card_id",
    )
    item["user_projection_run_id"] = _first_text(row, "user_projection_run_id", "projection_run_id")
    item["proposal_eligibility"] = proposal_eligibility_model(row)
    item["display_code"] = _first_text(row, "display_code", "code")
    item["display_name"] = _first_text(row, "display_name", "name")
    industry_provenance = _json_object(item.get("industry_provenance"))
    item["industry_code"] = _first_available_text(
        row.get("board_code"),
        row.get("industry_code"),
        industry_provenance.get("board_code"),
    ) or "—"
    item["industry_name"] = _first_available_text(
        row.get("board_name"),
        row.get("industry_name"),
        industry_provenance.get("board_name"),
    ) or "—"
    item["source_run_id"] = _first_text(row, "source_run_id", "source_action_run_id")
    item["projection_run_id"] = _first_text(row, "projection_run_id", "user_projection_run_id")
    item["quality_status"] = _first_text(row, "quality_status", default="reviewed")
    item["buy_return"] = number_or_none(item.get("buy_expected_return_pct"))
    item["secondary_return"] = number_or_none(item.get("up_secondary_expected_return_pct"))
    item["sell_return"] = number_or_none(item.get("sell_expected_return_pct"))
    item["up_ref"] = _first_text(item, "up_reference_period")
    item["down_ref"] = _first_text(item, "down_reference_period")
    item["trigger_periods"] = (
        item.get("all_trigger_periods")
        if item.get("all_trigger_periods") is not None
        else row.get("triggered_periods")
    )
    item["buy_target"] = number_or_none(item.get("target_price"))
    buy_target_price, sell_target_price = _signal_target_prices(
        item,
        fallback_target_price=row.get("target_price"),
    )
    item["buy_target_price"] = buy_target_price
    item["sell_target_price"] = sell_target_price
    item["reference_price"] = (
        number_or_none(item.get("action_price"))
        if item.get("action_state") == "executed"
        else number_or_none(item.get("trigger_price"))
    )
    item["event_time"] = display_datetime(row.get("event_time") or row.get("trigger_time"))
    item["display_values"] = _signal_display_values(
        item,
        event_time=row.get("event_time") or row.get("trigger_time"),
    )
    item["asset_kind_label"] = _asset_kind_label(item.get("asset_kind"))
    item["direction_label"] = _direction_label(item.get("direction"))
    item["action_state_label"] = _state_label(item.get("action_state"))
    item["blocked_reason_label"] = _blocked_reason_label(item.get("blocked_reason"))
    item["event_label"] = _event_label(item.get("event_type") or row.get("source_action_event_type"))
    item["condition_trace"] = app_condition_trace(row)
    item["evidence_chain"] = app_evidence_chain(row)
    item["tags"] = app_signal_tags(item, row)
    item["detail_page"] = app_signal_detail_policy(row)
    return item


def scrub_retired_strategy_center_private_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: scrub_retired_strategy_center_private_fields(item)
            for key, item in value.items()
            if key not in RETIRED_STRATEGY_CENTER_PRIVATE_FIELDS
        }
    if isinstance(value, list):
        return [
            scrub_retired_strategy_center_private_fields(item) for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            scrub_retired_strategy_center_private_fields(item) for item in value
        )
    return value


def app_signal_sse_data_model(row: dict[str, Any]) -> dict[str, Any]:
    normalized = app_signal_item(row)
    projection_id = canonical_bigint_id(
        row.get("user_signal_projection_id"),
        field_name="user_signal_projection_id",
        required=True,
    )
    card_id = canonical_bigint_id(
        row.get("user_signal_card_id"),
        field_name="user_signal_card_id",
    )
    event_type = _first_text(row, "event_type", "source_action_event_type")
    action_state = _first_text(row, "action_state")
    blocked_reason = _first_text(row, "blocked_reason")
    signal_industry_code = normalized["industry_code"]
    signal_industry_name = normalized["industry_name"]
    if normalized.get("asset_kind") == "stock":
        signal_industry_code = _first_available_text(
            row.get("signal_industry_code")
        ) or "—"
        signal_industry_name = _first_available_text(
            row.get("signal_industry_name")
        ) or "—"
    signal = {
        "user_signal_projection_id": projection_id,
        "user_signal_card_id": card_id,
        "user_projection_run_id": _first_text(row, "user_projection_run_id", "projection_run_id"),
        "trade_date": _first_text(row, "trade_date"),
        "event_time": display_datetime(row.get("event_time") or row.get("created_at")),
        "event_type": event_type,
        "event_label": _event_label(event_type),
        "asset_kind": _first_text(row, "asset_kind"),
        "asset_kind_label": _asset_kind_label(row.get("asset_kind")),
        "identity_key": _first_text(row, "identity_key"),
        "display_code": _first_text(row, "display_code", "code"),
        "display_name": _first_text(row, "display_name", "name"),
        "industry_code": signal_industry_code,
        "industry_name": signal_industry_name,
        "direction": _first_text(row, "direction"),
        "direction_label": _direction_label(row.get("direction")),
        "condition_key": _first_text(row, "condition_key"),
        "condition_rendering_policy": "reviewed_n6_projection_only",
        "triggered_periods": row.get("triggered_periods"),
        "primary_trigger_period": _first_text(row, "primary_trigger_period"),
        "target_price": number_or_none(row.get("target_price")),
        "buy_target": number_or_none(row.get("target_price")),
        "buy_target_price": normalized["buy_target_price"],
        "sell_target_price": normalized["sell_target_price"],
        "display_values": normalized["display_values"],
        "current_price": number_or_none(row.get("current_price")),
        "trigger_price": number_or_none(row.get("trigger_price")),
        "action_price": number_or_none(row.get("action_price")),
        "expected_return_pct": number_or_none(row.get("expected_return_pct")),
        "buy_return": number_or_none(row.get("buy_expected_return_pct")),
        "secondary_return": number_or_none(row.get("up_secondary_expected_return_pct")),
        "sell_return": number_or_none(row.get("sell_expected_return_pct")),
        "up_ref": _first_text(row, "up_reference_period"),
        "down_ref": _first_text(row, "down_reference_period"),
        "score": number_or_none(row.get("score")),
        "pe_core": number_or_none(row.get("pe_core")),
        "trigger_pct": number_or_none(row.get("trigger_pct")),
        "action_pct": number_or_none(row.get("action_pct")),
        "projection_message_status": _first_text(row, "projection_message_status", default="not_ready"),
        "action_state": action_state,
        "action_state_label": _state_label(action_state),
        "action_mark": _first_text(row, "action_mark"),
        "blocked_reason": blocked_reason,
        "blocked_reason_label": _blocked_reason_label(blocked_reason),
        "quality_status": _first_text(row, "quality_status", default="reviewed"),
        "source_run_id": _first_text(row, "source_run_id", "source_action_run_id"),
        "projection_run_id": _first_text(row, "projection_run_id", "user_projection_run_id"),
    }
    card = app_v2_message_card_item(row) if card_id is not None else None
    return {
        "contract_version": SIGNAL_SSE_CONTRACT_VERSION,
        "signal": signal,
        "card": card,
    }


def _signal_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value or value == "—":
            return None
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return decimal_value if decimal_value.is_finite() else None


def _signal_raw_decimal(value: Any) -> Any:
    decimal_value = _signal_decimal(value)
    if decimal_value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _signal_display_decimal(value: Any) -> str:
    decimal_value = _signal_decimal(value)
    if decimal_value is None:
        return "—"
    rounded = decimal_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if rounded == 0:
        return "0"
    return format(rounded, "f").rstrip("0").rstrip(".")


def _signal_display_time(value: Any) -> str:
    if value is None:
        return "—"
    parsed = value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return "—"
        normalized = f"{text[:-1]}+00:00" if text.endswith("Z") else text
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return "—"
    if not isinstance(parsed, datetime):
        return "—"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
    return parsed.astimezone(SIGNAL_DISPLAY_TIMEZONE).strftime("%H:%M:%S")


def _signal_target_prices(
    item: dict[str, Any],
    *,
    fallback_target_price: Any,
) -> tuple[Any, Any]:
    context = _json_object(item.get("condition_projection_context"))
    fields = _json_object(context.get("fields"))
    buy_target_price = _signal_raw_decimal(fields.get("buy_target_price"))
    sell_target_price = _signal_raw_decimal(fields.get("sell_target_price"))
    direction = str(item.get("direction") or "").strip().lower()
    if buy_target_price is None and direction == "buy":
        buy_target_price = _signal_raw_decimal(fallback_target_price)
    if sell_target_price is None and direction == "sell":
        sell_target_price = _signal_raw_decimal(fallback_target_price)
    return buy_target_price, sell_target_price


def _signal_display_values(item: dict[str, Any], *, event_time: Any) -> dict[str, str]:
    return {
        "event_time": _signal_display_time(event_time),
        "buy_target_price": _signal_display_decimal(item.get("buy_target_price")),
        "sell_target_price": _signal_display_decimal(item.get("sell_target_price")),
        "trigger_price": _signal_display_decimal(item.get("trigger_price")),
        "action_price": _signal_display_decimal(item.get("action_price")),
        "buy_expected_return_pct": _signal_display_decimal(item.get("buy_expected_return_pct")),
        "up_secondary_expected_return_pct": _signal_display_decimal(
            item.get("up_secondary_expected_return_pct")
        ),
        "sell_expected_return_pct": _signal_display_decimal(item.get("sell_expected_return_pct")),
        "trigger_pct": _signal_display_decimal(item.get("trigger_pct")),
        "action_pct": _signal_display_decimal(item.get("action_pct")),
        "score": _signal_display_decimal(item.get("score")),
        "pe_core": _signal_display_decimal(item.get("pe_core")),
    }


def app_signal_source_policy() -> dict[str, Any]:
    return {
        "allowed_sources": list(APP_ALLOWED_SIGNAL_SOURCES),
        "forbidden_sources": list(APP_FORBIDDEN_SIGNAL_SOURCES),
        "raw_k_read": False,
        "n1_raw_facts_read": False,
        "direct_live_market_read": False,
        "n4_raw_facts_bypass": False,
        "n5_raw_facts_bypass": False,
        "condition_basis_read": False,
        "condition_pool_read": False,
        "minute_target_scope_read": False,
        "unreviewed_outbox_or_raw_facts_read": False,
    }


def app_v2_source_policy() -> dict[str, Any]:
    return {
        "allowed_sources": list(APP_V2_ALLOWED_SOURCES),
        "forbidden_sources": list(APP_V2_FORBIDDEN_SOURCES),
        "raw_k_read": False,
        "n1_raw_facts_read": False,
        "n4_raw_bypass_read": False,
        "n5_raw_bypass_read": False,
        "condition_basis_read": False,
        "condition_pool_read": False,
        "minute_target_scope_read": False,
        "direct_live_market_read": False,
        "unreviewed_outbox_read": False,
    }


def app_v2_filter_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    asset_kind: str,
    result: dict[str, Any],
    filters: dict[str, Any],
    base_href: str,
    include_linked_stock_actions: bool = False,
    show_all: bool = False,
    default_limit: int = 200,
    write_enabled: bool = False,
    bulk_write_enabled: bool = False,
) -> dict[str, Any]:
    cache_ready = bool(result.get("cache_ready"))
    source_items = result.get("items") or []
    visible_fields = V2_FILTER_VISIBLE_FIELDS_BY_ASSET.get(asset_kind, ())
    rows = [
        {
            field: _app_v2_filter_json_value(row.get(field))
            for field in visible_fields
            if field in row
        }
        for row in source_items
    ]
    schema = _app_v2_filter_schema(rows)
    rows = _app_v2_filter_schema_rows(rows, schema)
    columns = _app_v2_filter_columns(
        rows,
        asset_kind=asset_kind,
        schema=schema,
        base_href=base_href,
        filters=filters,
        show_all=show_all,
    )
    sort_key, sort_dir = _app_v2_filter_sort(filters, schema=schema)
    rows = _app_v2_sort_filter_rows(rows, columns=columns, sort_key=sort_key, sort_dir=sort_dir)
    columns = _app_v2_filter_columns(
        rows,
        asset_kind=asset_kind,
        schema=schema,
        base_href=base_href,
        filters=filters,
        current_sort=sort_key,
        current_dir=sort_dir,
        show_all=show_all,
    )
    api_items = _app_v2_sort_filter_rows(
        [app_v2_filter_item(row, asset_kind=asset_kind) for row in source_items],
        columns=columns,
        sort_key=sort_key,
        sort_dir=sort_dir,
    )
    grid_rows = [
        _app_v2_filter_grid_row(
            row,
            asset_kind=asset_kind,
            columns=columns,
            include_linked_stock_actions=include_linked_stock_actions,
        )
        for row in rows
    ]
    total_count = int(result.get("total_count") or 0) if "total_count" in result else (len(source_items) if cache_ready else 0)
    filtered_count = (
        int(result.get("filtered_count") or 0)
        if "filtered_count" in result
        else (len(source_items) if cache_ready else 0)
    )
    returned_count = (
        int(result.get("returned_count") or 0)
        if "returned_count" in result
        else (len(grid_rows) if cache_ready else 0)
    )
    filter_pairs = _filter_query_pairs(filters)
    available_for_trade_dates = [
        str(item).strip()
        for item in result.get("available_for_trade_dates") or []
        if str(item).strip()
    ]
    selected_for_trade_date = str(result.get("selected_for_trade_date") or "").strip()
    if not selected_for_trade_date and available_for_trade_dates:
        selected_for_trade_date = available_for_trade_dates[0]
    date_filter_pairs = _filter_query_pairs(filters, exclude_field="for_trade_date")
    date_hidden_fields = [
        {"name": key, "value": value}
        for key, value in date_filter_pairs
    ]
    if show_all:
        date_hidden_fields.append({"name": "show_all", "value": "1"})
    search_hidden_fields = [
        {"name": key, "value": value}
        for key, value in _filter_query_pairs(filters, exclude_field="q")
    ]
    if show_all:
        search_hidden_fields.append({"name": "show_all", "value": "1"})
    has_more_rows = cache_ready and not show_all and returned_count < filtered_count
    component = V2_FILTER_COMPONENT_BY_ASSET.get(asset_kind, "B Track V2 Stock Filter")
    status = "data_not_ready" if not cache_ready else "ready"
    monitor_direction = _monitor_direction_from_filters(filters)
    clean_filters = {
        key: value
        for key, value in filters.items()
        if value and key not in {"sort", "sort_dir", "date_policy_blocker", "date_policy_message"}
    }
    source_context = _app_v2_filter_source_context_model(
        asset_kind=asset_kind,
        raw_context=result.get("source_context"),
        filters=filters,
        base_href=base_href,
        selected_for_trade_date=selected_for_trade_date,
    )
    empty_state = "筛选数据尚未准备完成" if not cache_ready else "暂无符合条件的对象"
    if source_context and source_context.get("empty_state"):
        empty_state = str(source_context["empty_state"])
    linked_stock_filter = _app_v2_filter_linked_stock_filter_context(
        asset_kind=asset_kind,
        rows=rows,
        source_identity_keys=result.get("linked_stock_filter_source_identity_keys"),
        filters=filters,
        selected_for_trade_date=selected_for_trade_date,
    )
    grade_filter_rows = app_v2_period_grade_filter_rows(filters, base_href=base_href)
    return {
        "ok": True,
        "component": component,
        "component_label": _component_label(component),
        "asset_kind": asset_kind,
        "anchor_id": V2_FILTER_ANCHOR_BY_ASSET.get(asset_kind, f"{asset_kind}-filter"),
        "source_table": V2_FILTER_SOURCE_BY_ASSET.get(asset_kind, "v_n6_stock_condition_display_basis"),
        "read_source_table": V2_FILTER_READ_SOURCE_BY_ASSET.get(
            asset_kind,
            "v_n6_stock_condition_display_basis",
        ),
        "membership_source_table": V2_MEMBERSHIP_SOURCE_BY_KIND.get(asset_kind),
        "membership_read_source_table": V2_MEMBERSHIP_READ_SOURCE_BY_KIND.get(asset_kind),
        "date_policy_blocker": str(result.get("date_policy_blocker") or ""),
        "date_policy_message": str(result.get("date_policy_message") or ""),
        "principal": app_principal_model(principal, user=user),
        "status": status,
        "status_label": _state_label(status),
        "empty_state": empty_state,
        "total_count": total_count,
        "filtered_count": filtered_count,
        "returned_count": returned_count,
        "selected_for_trade_date": selected_for_trade_date,
        "available_for_trade_dates": available_for_trade_dates,
        "date_selector": {
            "enabled": bool(available_for_trade_dates),
            "label": "当前生效日期",
            "selected": selected_for_trade_date,
            "base_href": base_href,
            "hidden_fields": date_hidden_fields,
            "options": [
                {
                    "value": trade_date,
                    "label": trade_date,
                    "selected": trade_date == selected_for_trade_date,
                    "href": _filter_href(
                        base_href,
                        [
                            *date_filter_pairs,
                            ("for_trade_date", trade_date),
                            *(((("show_all", "1"),) if show_all else ())),
                        ],
                    ),
                }
                for trade_date in available_for_trade_dates
            ],
        },
        "default_limit": default_limit,
        "show_all": show_all,
        "has_more_rows": has_more_rows,
        "show_all_href": _filter_href(base_href, [*filter_pairs, ("show_all", "1")]),
        "default_rows_href": _filter_href(base_href, filter_pairs),
        "expected_return_filter": _app_v2_expected_return_filter_model(
            filters=filters,
            base_href=base_href,
            show_all=show_all,
        ),
        "level_up_recommendation_filter": _app_v2_level_up_recommendation_filter_model(
            asset_kind=asset_kind,
            filters=filters,
            base_href=base_href,
            show_all=show_all,
            recommendation=result.get("level_up_recommendation"),
        ),
        "search_filter": {
            "base_href": base_href,
            "value": str(filters.get("q") or "").strip(),
            "hidden_fields": search_hidden_fields,
            "clear_href": _filter_href(
                base_href,
                [
                    *_filter_query_pairs(filters, exclude_field="q"),
                    *(((("show_all", "1"),) if show_all else ())),
                ],
            ),
        },
        "score_comparison": _app_v2_score_comparison_model(result.get("score_comparison")),
        "filters": clean_filters,
        "filters_json": json.dumps(clean_filters, ensure_ascii=False, sort_keys=True),
        "default_monitor_direction": monitor_direction,
        "default_monitor_direction_label": _direction_label(monitor_direction),
        "grade_filter_rows": grade_filter_rows,
        "selected_grade_filter_count": sum(
            len(row.get("selected_values") or []) for row in grade_filter_rows
        ),
        "schema": schema,
        "columns": columns,
        "sort": {
            "field": sort_key,
            "direction": sort_dir,
            "enabled": True,
            "persist_enabled": False,
        },
        "rows": rows,
        "grid_rows": grid_rows,
        "items": grid_rows,
        "_api_items": api_items,
        "source_context": source_context,
        "linked_stock_filter": linked_stock_filter,
        "controls": app_v2_filter_controls(
            asset_kind,
            write_enabled=write_enabled,
            bulk_write_enabled=bulk_write_enabled,
        ),
        "readonly": True,
        "safety_banner": list(APP_V2_SAFETY_LABELS),
        "source_policy": app_v2_source_policy(),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def app_v2_filter_api_model(model: dict[str, Any], *, asset_kind: str) -> dict[str, Any]:
    visible_rows = [dict(row) for row in model.get("rows") or []]
    visible_items = [dict(row) for row in model.get("_api_items") or []]
    if not visible_items:
        visible_items = [app_v2_filter_item(row, asset_kind=asset_kind) for row in visible_rows]
    return {
        "ok": bool(model.get("ok")),
        "component": model.get("component"),
        "component_label": model.get("component_label"),
        "principal": model.get("principal"),
        "status": model.get("status"),
        "status_label": model.get("status_label"),
        "empty_state": model.get("empty_state"),
        "filters": model.get("filters") or {},
        "available_for_trade_dates": model.get("available_for_trade_dates") or [],
        "selected_for_trade_date": model.get("selected_for_trade_date") or "",
        "source_context": model.get("source_context") or {},
        "expected_return_filter": model.get("expected_return_filter") or {},
        "level_up_recommendation_filter": model.get("level_up_recommendation_filter") or {},
        "score_comparison": model.get("score_comparison") or _app_v2_score_comparison_model(None),
        "default_monitor_direction": model.get("default_monitor_direction") or "buy",
        "default_monitor_direction_label": model.get("default_monitor_direction_label") or "",
        "read_source_table": model.get("read_source_table") or "",
        "source_table": model.get("source_table") or "",
        "membership_read_source_table": model.get("membership_read_source_table") or "",
        "total_count": int(model.get("total_count") or 0),
        "filtered_count": int(model.get("filtered_count") or 0),
        "returned_count": len(visible_rows),
        "schema": model.get("schema") or [],
        "columns": model.get("columns") or [],
        "rows": visible_rows,
        "grid_rows": model.get("grid_rows") or [],
        "items": visible_items,
        "controls": model.get("controls") or {},
        "readonly": True,
        "safety_banner": model.get("safety_banner") or [],
        "source_policy": model.get("source_policy") or {},
        "side_effects": model.get("side_effects") or dict(APP_SIDE_EFFECTS),
    }


def _filter_value_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _monitor_direction_from_filters(filters: dict[str, Any]) -> str:
    values = _filter_value_list(filters.get("direction"))
    if len(values) == 1 and values[0] in APP_DIRECTION_LABELS:
        return values[0]
    return "buy"


def _filter_query_pairs(filters: dict[str, Any], *, exclude_field: str | None = None) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for key, value in filters.items():
        if key == exclude_field or key in {"date_policy_blocker", "date_policy_message"}:
            continue
        for item in _filter_value_list(value):
            pairs.append((key, item))
    return pairs


def _filter_href(base_href: str, pairs: list[tuple[str, str]]) -> str:
    query = urlencode(pairs)
    return f"{base_href}?{query}" if query else base_href


def _filter_query_pairs_without(filters: dict[str, Any], excluded_fields: set[str]) -> list[tuple[str, str]]:
    return [
        (key, value)
        for key, value in _filter_query_pairs(filters)
        if key not in excluded_fields
    ]


def _app_v2_filter_common_query_pairs(filters: dict[str, Any]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    valid_grade_values = {
        str(option["value"])
        for option in V2_PERIOD_GRADE_OPTIONS
    }
    grade_fields = {field for field, _ in V2_PERIOD_GRADE_FILTERS}
    for field in V2_FILTER_COMMON_QUERY_FIELDS:
        values = _filter_value_list(filters.get(field))
        if field == "direction":
            values = [value for value in values if value in APP_DIRECTION_LABELS]
        elif field in grade_fields:
            values = [value for value in values if value in valid_grade_values]
        elif field == V2_EXPECTED_RETURN_FILTER_KEY:
            value = app_v2_expected_return_value_text(filters.get(field))
            values = [value] if value else []
        pairs.extend((field, value) for value in values)
    return pairs


def app_v2_expected_return_threshold(value: Any) -> Decimal | None:
    decimal_value = _decimal_or_none(value)
    if decimal_value is None or decimal_value < 0 or decimal_value > 100:
        return None
    return decimal_value


def app_v2_expected_return_value_text(value: Any) -> str:
    decimal_value = app_v2_expected_return_threshold(value)
    if decimal_value is None:
        return ""
    text = format(decimal_value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def app_v2_level_up_recommendation_value(value: Any) -> str:
    text = str(value or "").strip()
    if text == V2_LEVEL_UP_RECOMMENDATION_INDEX_MAX:
        return V2_LEVEL_UP_RECOMMENDATION_INDEX_MAX
    return ""


def _app_v2_expected_return_filter_model(
    *,
    filters: dict[str, Any],
    base_href: str,
    show_all: bool,
) -> dict[str, Any]:
    value = app_v2_expected_return_value_text(filters.get(V2_EXPECTED_RETURN_FILTER_KEY))
    hidden_pairs = _filter_query_pairs(filters, exclude_field=V2_EXPECTED_RETURN_FILTER_KEY)
    hidden_fields = [{"name": key, "value": item} for key, item in hidden_pairs]
    if show_all:
        hidden_fields.append({"name": "show_all", "value": "1"})
    clear_pairs = _filter_query_pairs_without(filters, {V2_EXPECTED_RETURN_FILTER_KEY})
    if show_all:
        clear_pairs.append(("show_all", "1"))
    return {
        "enabled": True,
        "label": V2_EXPECTED_RETURN_FILTER_LABEL,
        "field": V2_EXPECTED_RETURN_FILTER_FIELD,
        "param": V2_EXPECTED_RETURN_FILTER_KEY,
        "value": value,
        "slider_value": value or "0",
        "min": "0",
        "max": "100",
        "step": "1",
        "active": bool(value),
        "active_label": f"{V2_EXPECTED_RETURN_FILTER_LABEL} >= {value}%" if value else "",
        "base_href": base_href,
        "hidden_fields": hidden_fields,
        "clear_href": _filter_href(base_href, clear_pairs),
    }


def _app_v2_level_up_recommendation_filter_model(
    *,
    asset_kind: str,
    filters: dict[str, Any],
    base_href: str,
    show_all: bool,
    recommendation: Any,
) -> dict[str, Any]:
    enabled = asset_kind in {"board", "stock"}
    label = "推荐板块" if asset_kind == "board" else "推荐个股" if asset_kind == "stock" else ""
    value = app_v2_level_up_recommendation_value(filters.get(V2_LEVEL_UP_RECOMMENDATION_FILTER_KEY))
    active = enabled and value == V2_LEVEL_UP_RECOMMENDATION_INDEX_MAX
    context = dict(recommendation) if isinstance(recommendation, dict) else {}
    threshold = _app_v2_filter_display_numeric_value(context.get("threshold"))
    threshold = "" if threshold == "—" else threshold
    available = bool(context.get("available")) if active else True
    blocker = str(context.get("blocker") or "")
    href_pairs = _filter_query_pairs_without(filters, {V2_LEVEL_UP_RECOMMENDATION_FILTER_KEY})
    href_pairs.append((V2_LEVEL_UP_RECOMMENDATION_FILTER_KEY, V2_LEVEL_UP_RECOMMENDATION_INDEX_MAX))
    clear_pairs = _filter_query_pairs_without(filters, {V2_LEVEL_UP_RECOMMENDATION_FILTER_KEY})
    if show_all:
        href_pairs.append(("show_all", "1"))
        clear_pairs.append(("show_all", "1"))
    if active and threshold:
        active_label = f"{label}：{V2_LEVEL_UP_RECOMMENDATION_FIELD} >= {threshold}"
    elif active:
        active_label = f"{label}：指数 level_up_score 不可用"
    else:
        active_label = ""
    return {
        "enabled": enabled,
        "label": label,
        "param": V2_LEVEL_UP_RECOMMENDATION_FILTER_KEY,
        "value": value,
        "active": active,
        "available": available,
        "threshold": threshold,
        "field": V2_LEVEL_UP_RECOMMENDATION_FIELD,
        "blocker": blocker,
        "active_label": active_label,
        "href": _filter_href(base_href, href_pairs),
        "clear_href": _filter_href(base_href, clear_pairs),
    }


def _app_v2_filter_source_context_model(
    *,
    asset_kind: str,
    raw_context: Any,
    filters: dict[str, Any],
    base_href: str,
    selected_for_trade_date: str,
) -> dict[str, Any] | None:
    if asset_kind != "stock":
        return None
    context = dict(raw_context) if isinstance(raw_context, dict) else {}
    context = {str(key): value for key, value in context.items() if not str(key).startswith("_")}
    source_asset_type = str(context.get("source_asset_type") or "").strip()
    source_identity_keys = [
        str(item).strip()
        for item in context.get("source_identity_keys") or []
        if str(item).strip()
    ]
    source_display_names = [
        str(item).strip()
        for item in context.get("source_display_names") or []
        if str(item).strip()
    ]
    source_label_by_type = {
        "index": "指数",
        "board": "板块",
    }
    if not source_asset_type:
        label = "全部个股"
        active = False
    elif source_asset_type == "board" and source_identity_keys:
        label = f"来源板块筛选结果：{len(source_identity_keys)} 个板块"
        active = True
    elif source_asset_type not in source_label_by_type:
        label = "来源参数无效"
        active = True
    elif len(source_identity_keys) == 1:
        display_name = source_display_names[0] if source_display_names else source_identity_keys[0]
        label = f"来自{source_label_by_type[source_asset_type]}：{display_name}"
        active = True
    else:
        label = f"来自多个{source_label_by_type[source_asset_type]}：{len(source_identity_keys)} 个来源"
        active = True
    clear_pairs = _filter_query_pairs_without(
        filters,
        {"source_asset_type", "source_identity_key", "source_identity_keys"},
    )
    context.update(
        {
            "source_asset_type": source_asset_type or None,
            "source_identity_keys": source_identity_keys,
            "source_display_names": source_display_names,
            "for_trade_date": context.get("for_trade_date") or selected_for_trade_date,
            "label": label,
            "active": active,
            "clear_href": _filter_href(base_href, clear_pairs),
        }
    )
    return context


def _app_v2_filter_linked_stock_filter_context(
    *,
    asset_kind: str,
    rows: list[dict[str, Any]],
    source_identity_keys: Any,
    filters: dict[str, Any],
    selected_for_trade_date: str,
) -> dict[str, Any] | None:
    if asset_kind != "board":
        return None
    normalized_source_identity_keys = [
        str(item).strip()
        for item in (source_identity_keys or [])
        if str(item).strip()
    ]
    if not normalized_source_identity_keys:
        for row in rows:
            identity_key = _first_text(row, "identity_key", f"{asset_kind}_identity_key")
            if identity_key and identity_key not in normalized_source_identity_keys:
                normalized_source_identity_keys.append(identity_key)
    if not normalized_source_identity_keys:
        return None
    pairs = _app_v2_filter_common_query_pairs(filters)
    if selected_for_trade_date and not any(key == "for_trade_date" for key, _ in pairs):
        pairs.insert(0, ("for_trade_date", selected_for_trade_date))
    pairs.append(("source_asset_type", asset_kind))
    pairs.append(("source_identity_keys", ",".join(normalized_source_identity_keys)))
    return {
        "enabled": True,
        "source_asset_type": asset_kind,
        "source_identity_keys": normalized_source_identity_keys,
        "source_count": len(normalized_source_identity_keys),
        "label": "按当前板块筛选结果查看个股",
        "source_label": f"来源板块筛选结果：{len(normalized_source_identity_keys)} 个板块",
        "href": _filter_href("/n6/app/filter-center/stocks", pairs),
    }


def _app_v2_filter_json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _app_v2_filter_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_app_v2_filter_json_value(item) for item in value]
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return value


def _app_v2_filter_passthrough_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): _app_v2_filter_json_value(value)
        for key, value in row.items()
        if not str(key).startswith("_")
    }


def _app_v2_filter_schema(rows: list[dict[str, Any]]) -> list[str]:
    schema: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                schema.append(key)
                seen.add(key)
    return schema


def _app_v2_filter_schema_rows(rows: list[dict[str, Any]], schema: list[str]) -> list[dict[str, Any]]:
    return [{field: row.get(field) for field in schema} for row in rows]


def _app_v2_filter_date_digits(value: Any) -> str:
    text = str(value or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) < 8:
        return ""
    year = int(digits[:4])
    month = int(digits[4:6])
    day = int(digits[6:8])
    if 1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
        return digits
    return ""


def _app_v2_filter_infer_sort_type(values: list[Any]) -> str:
    present = [value for value in values if not _app_v2_filter_missing(value)]
    if not present:
        return "text"
    if all(_app_v2_filter_date_digits(value) for value in present):
        return "date"
    if all(_decimal_or_none(value) is not None for value in present):
        return "number"
    return "text"


def _app_v2_filter_sort(filters: dict[str, Any], *, schema: list[str]) -> tuple[str, str]:
    fields = set(schema)
    sort_key = str(filters.get("sort") or "").strip()
    if sort_key not in fields:
        sort_key = ""
    sort_dir = str(filters.get("sort_dir") or "asc").strip().lower()
    if sort_dir not in {"asc", "desc"}:
        sort_dir = "asc"
    return sort_key, sort_dir


def _app_v2_filter_sort_href(
    *,
    base_href: str,
    filters: dict[str, Any],
    field: str,
    current_sort: str,
    current_dir: str,
    show_all: bool,
) -> str:
    next_dir = "desc" if current_sort == field and current_dir == "asc" else "asc"
    pairs = [
        (key, value)
        for key, value in _filter_query_pairs(filters)
        if key not in {"sort", "sort_dir"}
    ]
    pairs.append(("sort", field))
    pairs.append(("sort_dir", next_dir))
    if show_all:
        pairs.append(("show_all", "1"))
    return _filter_href(base_href, pairs)


def _app_v2_filter_columns(
    rows: list[dict[str, Any]],
    *,
    asset_kind: str,
    schema: list[str],
    base_href: str,
    filters: dict[str, Any],
    current_sort: str = "",
    current_dir: str = "asc",
    show_all: bool,
) -> list[dict[str, Any]]:
    columns: list[dict[str, Any]] = []
    schema_set = set(schema)
    hidden_fields = V2_FILTER_TABLE_HIDDEN_FIELDS_BY_ASSET.get(asset_kind, frozenset())
    visible_fields = [
        field
        for field in V2_FILTER_VISIBLE_FIELDS_BY_ASSET.get(asset_kind, ())
        if field in schema_set and field not in hidden_fields
    ]
    fields = visible_fields or list(schema)
    for field in fields:
        sort_type = _app_v2_filter_infer_sort_type([row.get(field) for row in rows])
        columns.append(
            {
                "key": field,
                "label": V2_FILTER_FIELD_LABELS.get(field, field),
                "sort_type": sort_type,
                "sortable": True,
                "sort_active": field == current_sort,
                "sort_direction": current_dir if field == current_sort else "",
                "sort_href": _app_v2_filter_sort_href(
                    base_href=base_href,
                    filters=filters,
                    field=field,
                    current_sort=current_sort,
                    current_dir=current_dir,
                    show_all=show_all,
                ),
                "align": "numeric" if sort_type == "number" else "text",
            }
        )
    return columns


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text or text == "—":
            return None
        value = text.replace(",", "")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _app_v2_filter_is_percent_field(field: str) -> bool:
    return field.endswith("_pct") or field in V2_FILTER_PERCENT_FIELDS


def _app_v2_filter_display_percent_value(value: Any) -> str:
    decimal_value = _decimal_or_none(value)
    if decimal_value is None:
        return "—"
    return format(decimal_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def _app_v2_filter_display_numeric_value(value: Any) -> str:
    decimal_value = _decimal_or_none(value)
    if decimal_value is None:
        return "—"
    text = format(decimal_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _app_v2_filter_display_value(value: Any, *, field: str = "", sort_type: str = "text") -> str:
    if _app_v2_filter_is_percent_field(field):
        return _app_v2_filter_display_percent_value(value)
    if sort_type == "number":
        return _app_v2_filter_display_numeric_value(value)
    if value is None:
        return "—"
    if isinstance(value, str):
        text = value.strip()
        if not text or text == "—":
            return "—"
        return text
    return _field_value_text(value)


def _app_v2_filter_display_cells(row: dict[str, Any], columns: list[dict[str, Any]]) -> list[dict[str, str]]:
    cells: list[dict[str, str]] = []
    for column in columns:
        field = str(column["key"])
        cells.append(
            {
                "key": field,
                "label": str(column.get("label") or field),
                "value": _app_v2_filter_display_value(
                    row.get(field),
                    field=field,
                    sort_type=str(column.get("sort_type") or "text"),
                ),
                "align": str(column.get("align") or "text"),
                "sort_type": str(column.get("sort_type") or "text"),
            }
        )
    return cells


def _app_v2_filter_mobile_code(row: dict[str, Any], *, identity_key: str) -> str:
    display_code = _first_text(row, "display_code")
    if display_code and display_code != "—":
        return display_code
    identity_part = identity_key.rsplit(":", 1)[-1].strip() if identity_key else ""
    return identity_part or "—"


def _app_v2_filter_period_transition_summary(row: dict[str, Any]) -> str:
    values = [
        (period_label, _first_text(row, field))
        for period_label, field in V2_FILTER_PERIOD_TRANSITION_FIELDS
    ]
    if all(not value or value == "—" for _, value in values):
        return "—"
    return " / ".join(
        f"{period_label}：{V2_FILTER_PERIOD_TRANSITION_LABELS.get(value, value or '—')}"
        for period_label, value in values
    )


def _app_v2_filter_mobile_fields(row: dict[str, Any], columns: list[dict[str, Any]]) -> list[dict[str, str]]:
    columns_by_key = {str(column["key"]): column for column in columns}
    fields: list[dict[str, str]] = []
    for field, label in V2_FILTER_MOBILE_FIELDS:
        column = columns_by_key.get(field) or {}
        fields.append(
            {
                "key": field,
                "label": label,
                "value": _app_v2_filter_display_value(
                    row.get(field),
                    field=field,
                    sort_type=str(column.get("sort_type") or "text"),
                ),
            }
        )
    fields.append(
        {
            "key": "period_transition_summary",
            "label": "周期状态",
            "value": _app_v2_filter_period_transition_summary(row),
        }
    )
    return fields


def _app_v2_filter_missing(value: Any) -> bool:
    return value is None or str(value).strip() in {"", "—"}


def _app_v2_filter_date_sort_value(value: Any) -> str:
    return _app_v2_filter_date_digits(value) or str(value or "").strip()


def _app_v2_filter_sort_value(item: dict[str, Any], field: str, sort_type: str) -> Any:
    value = item.get(field)
    if sort_type == "number":
        return _decimal_or_none(value) or Decimal("0")
    if sort_type == "date":
        return _app_v2_filter_date_sort_value(value)
    return str(value or "")


def _app_v2_sort_filter_rows(
    rows: list[dict[str, Any]],
    *,
    columns: list[dict[str, Any]],
    sort_key: str,
    sort_dir: str,
) -> list[dict[str, Any]]:
    sort_type_by_key = {str(column["key"]): str(column.get("sort_type") or "text") for column in columns}
    if not sort_key:
        return rows
    if sort_key not in sort_type_by_key and all(sort_key not in row for row in rows):
        return rows
    sort_type = sort_type_by_key.get(sort_key) or _app_v2_filter_infer_sort_type([row.get(sort_key) for row in rows])
    present = [row for row in rows if not _app_v2_filter_missing(row.get(sort_key))]
    missing = [row for row in rows if _app_v2_filter_missing(row.get(sort_key))]
    present.sort(
        key=lambda row: _app_v2_filter_sort_value(row, sort_key, sort_type),
        reverse=sort_dir == "desc",
    )
    return [*present, *missing]


def _period_grade_filter_href(
    *,
    base_href: str,
    filters: dict[str, Any],
    field: str,
    value: str,
    selected_values: list[str],
) -> str:
    next_values = list(selected_values)
    if value in next_values:
        next_values = [item for item in next_values if item != value]
    else:
        next_values.append(value)

    pairs = _filter_query_pairs(filters, exclude_field=field)
    pairs.extend((field, item) for item in next_values)
    return _filter_href(base_href, pairs)


def app_v2_period_grade_filter_rows(
    filters: dict[str, Any],
    *,
    base_href: str,
) -> list[dict[str, Any]]:
    option_values = [str(option["value"]) for option in V2_PERIOD_GRADE_OPTIONS]
    rows: list[dict[str, Any]] = []
    for field, label in V2_PERIOD_GRADE_FILTERS:
        raw_values = _filter_value_list(filters.get(field))
        selected_values = [value for value in raw_values if value in option_values]
        rows.append(
            {
                "field": field,
                "label": label,
                "selected_values": selected_values,
                "all_selected": bool(selected_values) and len(selected_values) == len(option_values),
                "unlimited": not selected_values,
                "reset_href": _filter_href(
                    base_href,
                    _filter_query_pairs(filters, exclude_field=field),
                ),
                "options": [
                    {
                        "value": str(option["value"]),
                        "label": str(option["label"]),
                        "selected": str(option["value"]) in selected_values,
                        "href": _period_grade_filter_href(
                            base_href=base_href,
                            filters=filters,
                            field=field,
                            value=str(option["value"]),
                            selected_values=selected_values,
                        ),
                    }
                    for option in V2_PERIOD_GRADE_OPTIONS
                ],
            }
        )
    return rows


def _app_v2_score_comparison_model(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    sample_count = int(raw.get("sample_count") or 0)
    if sample_count <= 0:
        return {
            "level_up_score_avg": None,
            "level_down_score_avg": None,
            "sample_count": 0,
            "regime": "unavailable",
            "label": "暂无数据",
        }
    avg_up = _app_v2_filter_json_value(raw.get("level_up_score_avg"))
    avg_down = _app_v2_filter_json_value(raw.get("level_down_score_avg"))
    regime = str(raw.get("regime") or "").strip()
    if regime not in {"bull", "bear"}:
        up_value = _decimal_or_none(avg_up)
        down_value = _decimal_or_none(avg_down)
        regime = "bull" if up_value is not None and down_value is not None and up_value > down_value else "bear"
    return {
        "level_up_score_avg": avg_up,
        "level_down_score_avg": avg_down,
        "sample_count": sample_count,
        "regime": regime,
        "label": "牛市" if regime == "bull" else "熊市",
    }


def _app_v2_filter_grid_row(
    row: dict[str, Any],
    *,
    asset_kind: str,
    columns: list[dict[str, Any]],
    include_linked_stock_actions: bool,
) -> dict[str, Any]:
    identity_key = _first_text(row, "identity_key", f"{asset_kind}_identity_key")
    display_code = _first_text(row, "display_code", "code", f"{asset_kind}_code")
    display_name = _first_text(row, "display_name", "name", f"{asset_kind}_name", default=identity_key)
    item = {
        "asset_kind": _first_text(row, "asset_kind", default=asset_kind),
        "asset_kind_label": _asset_kind_label(asset_kind),
        "identity_key": identity_key,
        "for_trade_date": _first_text(row, "for_trade_date"),
        "display_code": display_code,
        "mobile_display_code": _app_v2_filter_mobile_code(row, identity_key=identity_key),
        "display_name": display_name,
        "source_table": V2_FILTER_SOURCE_BY_ASSET.get(asset_kind, "v_n6_stock_condition_display_basis"),
        "readonly": True,
        "add_monitor_enabled": False,
        "monitor_direction_policy": "buy_only" if asset_kind == "stock" else "buy_sell",
        "realtime_current_filter_only": True,
        "single_item_actions_only": True,
        "add_monitor_label": "只读查看",
        "add_monitor_short_label": "只读",
        "investment_advice": False,
        "cells": _app_v2_filter_display_cells(row, columns),
        "mobile_fields": _app_v2_filter_mobile_fields(row, columns),
    }
    if include_linked_stock_actions and asset_kind in V2_LINKED_STOCK_ROUTE_BY_KIND:
        parent_key = _first_text(
            row,
            f"{asset_kind}_identity_key",
            default=identity_key,
        )
        item.update(
            {
                "linked_stocks_enabled": True,
                "linked_stocks_label": "查看成分股",
                "linked_stocks_href": f"{V2_LINKED_STOCK_ROUTE_BY_KIND[asset_kind]}/{quote(parent_key, safe='')}",
                "linked_stocks_default_view_label": "只读成分股",
                "linked_stocks_all_members_label": "全部成分股",
            }
        )
    return item


def app_v2_filter_item(row: dict[str, Any], *, asset_kind: str) -> dict[str, Any]:
    return _app_v2_filter_item(row, asset_kind=asset_kind, include_linked_stock_actions=False)


def _app_v2_filter_item(
    row: dict[str, Any],
    *,
    asset_kind: str,
    include_linked_stock_actions: bool,
) -> dict[str, Any]:
    selected_directions = _list_text(row, "selected_directions")
    selected_condition_keys = _list_text(row, "selected_condition_keys")
    selected_signal_types = _list_text(row, "selected_signal_types")
    selected_lanes = _list_text(row, "selected_lanes")
    selected_monitor_types = _list_text(row, "selected_monitor_types")
    direction = _first_text(
        row,
        "direction",
        default=selected_directions[0] if len(selected_directions) == 1 else "—",
    )
    condition_key = _first_text(
        row,
        "condition_key",
        default="、".join(selected_condition_keys) if selected_condition_keys else "—",
    )
    last_signal_state = _first_text(row, "last_signal_state", default="—")
    common_item = {
        "asset_kind": asset_kind,
        "asset_kind_label": _asset_kind_label(asset_kind),
        "source_display_basis_id": canonical_bigint_id(
            row.get("source_display_basis_id"),
            field_name="source_display_basis_id",
        ),
        "run_id": _first_text(row, "run_id", "source_run_id"),
        "source_run_id": _first_text(row, "source_run_id", "run_id"),
        "for_trade_date": _first_text(row, "for_trade_date"),
        "source_trade_date": _first_text(row, "source_trade_date"),
        "identity_key": _first_text(row, "identity_key"),
        "display_code": _first_text(row, "display_code", "code"),
        "display_name": _first_text(row, "display_name", "name"),
        "display_title": _first_text(row, "display_title"),
        "display_summary": _first_text(row, "display_summary"),
        "direction": direction,
        "direction_label": _direction_list_label(selected_directions) if selected_directions else _direction_label(direction),
        "condition_key": condition_key,
        "selected_directions": selected_directions,
        "selected_condition_keys": selected_condition_keys,
        "selected_signal_types": selected_signal_types,
        "selected_lanes": selected_lanes,
        "selected_monitor_types": selected_monitor_types,
        "year_overheat_level": _first_text(row, "year_overheat_level", "period_grade_y"),
        "quarter_overheat_level": _first_text(row, "quarter_overheat_level", "period_grade_q"),
        "month_overheat_level": _first_text(row, "month_overheat_level", "period_grade_m"),
        "week_overheat_level": _first_text(row, "week_overheat_level", "period_grade_w"),
        "day_overheat_level": _first_text(row, "day_overheat_level", "period_grade_d"),
        "period_grade_y": _first_text(row, "period_grade_y", "year_overheat_level"),
        "period_grade_q": _first_text(row, "period_grade_q", "quarter_overheat_level"),
        "period_grade_m": _first_text(row, "period_grade_m", "month_overheat_level"),
        "period_grade_w": _first_text(row, "period_grade_w", "week_overheat_level"),
        "period_grade_d": _first_text(row, "period_grade_d", "day_overheat_level"),
        "period_transition_y": _first_text(row, "period_transition_y"),
        "period_transition_q": _first_text(row, "period_transition_q"),
        "period_transition_m": _first_text(row, "period_transition_m"),
        "period_transition_w": _first_text(row, "period_transition_w"),
        "period_transition_d": _first_text(row, "period_transition_d"),
        "buy_target_price": _first_text(row, "buy_target_price"),
        "sell_target_price": _first_text(row, "sell_target_price"),
        "up_sell_reference_period": _first_text(row, "up_sell_reference_period"),
        "down_buy_reference_period": _first_text(row, "down_buy_reference_period"),
        "quality_status": _first_text(row, "quality_status", default="reviewed"),
        "quality_reason": _first_text(row, "quality_reason"),
        "display_status": _first_text(row, "display_status"),
        "last_signal_state": last_signal_state,
        "last_signal_state_label": _state_label(last_signal_state),
        "projection_run_id": _first_text(row, "projection_run_id"),
        "cache_run_id": _first_text(row, "cache_run_id"),
        "source_table": V2_FILTER_SOURCE_BY_ASSET.get(asset_kind, "v_n6_stock_condition_display_basis"),
        "readonly": True,
        "add_monitor_enabled": False,
        "add_monitor_label": "只读查看",
        "add_monitor_short_label": "只读",
        "investment_advice": False,
    }
    if include_linked_stock_actions and asset_kind in V2_LINKED_STOCK_ROUTE_BY_KIND:
        parent_key = _first_text(
            row,
            f"{asset_kind}_identity_key",
            default=_first_text(row, "identity_key"),
        )
        common_item.update(
            {
                "linked_stocks_enabled": True,
                "linked_stocks_label": "查看成分股",
                "linked_stocks_href": f"{V2_LINKED_STOCK_ROUTE_BY_KIND[asset_kind]}/{quote(parent_key, safe='')}",
                "linked_stocks_default_view_label": "只读成分股",
                "linked_stocks_all_members_label": "全部成分股",
            }
        )
    if asset_kind == "stock":
        return {
            **common_item,
            "stock_identity_key": _first_text(row, "stock_identity_key", default=_first_text(row, "identity_key")),
            "code": _first_text(row, "code"),
            "exchange": _first_text(row, "exchange"),
            "name": _first_text(row, "name"),
            "industry_code": row.get("industry_code"),
            "industry_name": row.get("industry_name"),
            "total_mv": _first_text(row, "total_mv"),
            "circ_mv": _first_text(row, "circ_mv"),
            "score": _first_text(row, "score"),
            "recommendation_level": _first_text(row, "recommendation_level"),
            "main_index_code": _first_text(row, "main_index_code"),
            "main_index_name": _first_text(row, "main_index_name"),
            "preferred_board_code": _first_text(row, "preferred_board_code"),
            "preferred_board_name": _first_text(row, "preferred_board_name"),
            "is_st": _first_text(row, "is_st"),
            "stock_status": _first_text(row, "stock_status"),
        }
    if asset_kind == "index":
        return {
            **common_item,
            "index_identity_key": _first_text(row, "index_identity_key", default=_first_text(row, "identity_key")),
            "code": _first_text(row, "code"),
            "exchange": _first_text(row, "exchange"),
            "name": _first_text(row, "name"),
            "fixed_index_member": _first_text(row, "fixed_index_member"),
        }
    return {
        **common_item,
        "board_identity_key": _first_text(row, "board_identity_key", default=_first_text(row, "identity_key")),
        "board_code": _first_text(row, "board_code", "code"),
        "board_name": _first_text(row, "board_name", "name"),
        "board_type": _first_text(row, "board_type", default="—"),
        "is_industry_board": _first_text(row, "is_industry_board"),
    }


def app_v2_filter_controls(
    asset_kind: str,
    *,
    write_enabled: bool = False,
    bulk_write_enabled: bool = False,
) -> dict[str, Any]:
    bulk_active = bool(write_enabled and bulk_write_enabled)
    return {
        "add_monitor_enabled": bool(write_enabled),
        "add_monitor_label": "加入监控对象" if write_enabled else "写入功能未启用",
        "add_realtime_scope_enabled": bool(write_enabled),
        "add_realtime_scope_label": "加入实时监控范围" if write_enabled else "写入功能未启用",
        "write_route_registered": True,
        "write_route_enabled": bool(write_enabled),
        "single_item_actions_only": not bulk_active,
        "bulk_add_enabled": bulk_active,
        "bulk_preview_required": True,
        "bulk_max_identity_count": 10000,
        "monitor_direction_policy": "buy_only" if asset_kind == "stock" else "buy_sell",
        "realtime_current_filter_only": True,
        "pause_monitor_enabled": False,
        "remove_monitor_enabled": False,
        "members_lookup_enabled": asset_kind in {"board", "index"},
        "members_lookup_label": "查看成分股",
        "write_scope_notice": "筛选数据只读；仅获授权时可保存本人监控范围",
    }


def app_v2_filter_members_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    membership_kind: str,
    parent_identity_key: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    cache_ready = bool(result.get("cache_ready"))
    component = "B Track V2 Board Members" if membership_kind == "board" else "B Track V2 Index Members"
    status = "data_not_ready" if not cache_ready else "ready"
    source_table = V2_MEMBERSHIP_SOURCE_BY_KIND.get(membership_kind, "v_n6_board_membership_fact")
    return {
        "ok": True,
        "component": component,
        "component_label": _component_label(component),
        "principal": app_principal_model(principal, user=user),
        "membership_kind": membership_kind,
        "parent_identity_key": parent_identity_key,
        "source_table": source_table,
        "status": status,
        "status_label": _state_label(status),
        "empty_state": "筛选数据尚未准备完成" if not cache_ready else "暂无成分股记录",
        "items": [app_v2_membership_item(row, membership_kind=membership_kind) for row in result.get("items") or []],
        "readonly": True,
        "safety_banner": list(APP_V2_SAFETY_LABELS),
        "source_policy": app_v2_source_policy(),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def app_v2_membership_drilldown_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    entity_type: str,
    identity_key: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    source_table = V2_MEMBERSHIP_READ_SOURCE_BY_KIND.get(entity_type)
    return {
        "ok": True,
        "component": "B Track V1 Membership Drilldown",
        "component_label": "成分股展开",
        "principal": app_principal_model(principal, user=user),
        "entity_type": entity_type,
        "identity_key": identity_key,
        "source_table": source_table,
        "members": list(result.get("members") or []),
        "member_count": int(result.get("member_count") or 0),
        "readonly": True,
        "safety_banner": list(APP_V2_SAFETY_LABELS),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def app_v2_filter_linked_stocks_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    membership_kind: str,
    parent_identity_key: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    cache_ready = bool(result.get("cache_ready"))
    component = V2_LINKED_STOCK_COMPONENT_BY_KIND.get(membership_kind, "B Track V2 Board Linked Stocks")
    status = "data_not_ready" if not cache_ready else "ready"
    membership_count = int(result.get("membership_count") or 0)
    linked_count = int(result.get("linked_count") or 0)
    missing_count = int(result.get("missing_count") or 0)
    view = _first_text(result, "view", default="matched")
    current_view_count = int(result.get("current_view_count") or len(result.get("items") or []))
    items = [
        app_v2_linked_stock_item(row, membership_kind=membership_kind)
        for row in result.get("items") or []
    ]
    return {
        "ok": True,
        "component": component,
        "component_label": _component_label(component),
        "principal": app_principal_model(principal, user=user),
        "membership_kind": membership_kind,
        "parent_identity_key": parent_identity_key,
        "source_table": V2_FILTER_SOURCE_BY_ASSET["stock"],
        "read_source_table": V2_FILTER_READ_SOURCE_BY_ASSET["stock"],
        "membership_source_table": V2_MEMBERSHIP_SOURCE_BY_KIND.get(
            membership_kind,
            "v_n6_board_membership_fact",
        ),
        "membership_read_source_table": V2_MEMBERSHIP_READ_SOURCE_BY_KIND.get(
            membership_kind,
            "v_n6_board_membership_fact",
        ),
        "status": status,
        "status_label": _state_label(status),
        "empty_state": "筛选数据尚未准备完成" if not cache_ready else "暂无关联个股",
        "membership_count": membership_count,
        "linked_count": linked_count,
        "missing_count": missing_count,
        "view": view,
        "current_view_count": current_view_count,
        "items": items,
        "controls": {
            "default_view_label": "符合个股筛选",
            "all_members_label": "全部成分股",
            "selected_add_label": "加入已选个股监控",
            "matched_add_label": "将符合个股筛选加入个股监控",
            "all_members_view_label": "查看全部成分股",
            "all_members_write_label": "全部成分股加入监控（暂未开放）",
            "all_members_write_enabled": False,
            "write_route_registered": False,
            "write_route_enabled": False,
            "write_scope_notice": "当前页面仅展示已批准的 N6 只读数据",
        },
        "readonly": True,
        "safety_banner": list(APP_V2_SAFETY_LABELS),
        "source_policy": app_v2_source_policy(),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def app_v2_linked_stock_item(row: dict[str, Any], *, membership_kind: str) -> dict[str, Any]:
    stock_identity_key = _first_text(row, "stock_identity_key", "identity_key")
    materialized = dict(row)
    materialized.setdefault("asset_kind", "stock")
    materialized["identity_key"] = _first_text(row, "identity_key", default=stock_identity_key)
    materialized["stock_identity_key"] = stock_identity_key
    materialized["code"] = _first_text(row, "code", "stock_code")
    materialized["name"] = _first_text(row, "name", "stock_name")
    materialized["display_code"] = _first_text(row, "display_code", "stock_code", "code")
    materialized["display_name"] = _first_text(row, "display_name", "stock_name", "name")
    item = app_v2_filter_item(materialized, asset_kind="stock")
    in_stock_filter = str(row.get("in_stock_filter", True)).lower() not in {"false", "0", "no"}
    stock_filter_status = "in_filter" if in_stock_filter else "not_in_filter"
    return {
        **item,
        "membership_kind": _first_text(row, "membership_kind", default=membership_kind),
        "membership_trade_date": _first_text(row, "membership_trade_date", "trade_date"),
        "parent_identity_key": _first_text(row, "parent_identity_key"),
        "parent_code": _first_text(row, "parent_code"),
        "parent_name": _first_text(row, "parent_name"),
        "stock_identity_key": stock_identity_key,
        "stock_code": _first_text(row, "stock_code", "code", default=item["display_code"]),
        "stock_name": _first_text(row, "stock_name", "name", default=item["display_name"]),
        "in_stock_filter": in_stock_filter,
        "stock_filter_status": stock_filter_status,
        "stock_filter_status_label": "符合个股筛选" if in_stock_filter else "未进入个股筛选",
        "membership_source_table": V2_MEMBERSHIP_SOURCE_BY_KIND.get(
            membership_kind,
            "v_n6_board_membership_fact",
        ),
        "membership_read_source_table": V2_MEMBERSHIP_READ_SOURCE_BY_KIND.get(
            membership_kind,
            "v_n6_board_membership_fact",
        ),
        "membership_source_version": _first_text(row, "membership_source_version", "source_version"),
        "membership_source_batch_id": _first_text(row, "membership_source_batch_id", "source_batch_id"),
        "linked_view_label": "符合个股筛选" if in_stock_filter else "全部成分股",
    }


def app_v2_membership_item(row: dict[str, Any], *, membership_kind: str) -> dict[str, Any]:
    common_item = {
        "membership_kind": _first_text(row, "membership_kind", default=membership_kind),
        "trade_date": _first_text(row, "trade_date"),
        "parent_identity_key": _first_text(row, "parent_identity_key"),
        "parent_code": _first_text(row, "parent_code"),
        "parent_name": _first_text(row, "parent_name"),
        "stock_identity_key": _first_text(row, "stock_identity_key"),
        "stock_code": _first_text(row, "stock_code"),
        "stock_name": _first_text(row, "stock_name"),
        "source_version": _first_text(row, "source_version"),
        "source_batch_id": _first_text(row, "source_batch_id"),
        "source_table": V2_MEMBERSHIP_SOURCE_BY_KIND.get(membership_kind, "v_n6_board_membership_fact"),
        "readonly": True,
    }
    if membership_kind == "board":
        return {
            **common_item,
            "board_identity_key": _first_text(row, "board_identity_key", "parent_identity_key"),
            "board_code": _first_text(row, "board_code", "parent_code"),
            "board_name": _first_text(row, "board_name", "parent_name"),
            "board_type": _first_text(row, "board_type", default="—"),
        }
    return {
        **common_item,
        "index_identity_key": _first_text(row, "index_identity_key", "parent_identity_key"),
        "index_code": _first_text(row, "index_code", "parent_code"),
        "index_name": _first_text(row, "index_name", "parent_name"),
    }


def app_v2_filter_center_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    stock_result: dict[str, Any],
    board_result: dict[str, Any],
    index_result: dict[str, Any],
    selected_asset_kind: str = "index",
    filters: dict[str, Any] | None = None,
    show_all: bool = False,
    write_enabled: bool = False,
    bulk_write_enabled: bool = False,
) -> dict[str, Any]:
    component = "B Track V2 Filter Center"
    filters = filters or {}
    selected_asset_kind = selected_asset_kind if selected_asset_kind in V2_FILTER_ASSET_ORDER else "index"
    all_sections = {
        "indexes": app_v2_filter_model(
            principal,
            user=user,
            asset_kind="index",
            result=index_result,
            filters=filters if selected_asset_kind == "index" else {},
            base_href="/n6/app/filter-center/indexes",
            include_linked_stock_actions=True,
            show_all=show_all if selected_asset_kind == "index" else False,
            default_limit=V2_FILTER_DEFAULT_LIMIT_BY_ASSET["index"],
            write_enabled=write_enabled,
            bulk_write_enabled=bulk_write_enabled,
        ),
        "boards": app_v2_filter_model(
            principal,
            user=user,
            asset_kind="board",
            result=board_result,
            filters=filters if selected_asset_kind == "board" else {},
            base_href="/n6/app/filter-center/boards",
            include_linked_stock_actions=True,
            show_all=show_all if selected_asset_kind == "board" else False,
            default_limit=V2_FILTER_DEFAULT_LIMIT_BY_ASSET["board"],
            write_enabled=write_enabled,
            bulk_write_enabled=bulk_write_enabled,
        ),
        "stocks": app_v2_filter_model(
            principal,
            user=user,
            asset_kind="stock",
            result=stock_result,
            filters=filters if selected_asset_kind == "stock" else {},
            base_href="/n6/app/filter-center/stocks",
            include_linked_stock_actions=True,
            show_all=show_all if selected_asset_kind == "stock" else False,
            default_limit=V2_FILTER_DEFAULT_LIMIT_BY_ASSET["stock"],
            write_enabled=write_enabled,
            bulk_write_enabled=bulk_write_enabled,
        ),
    }
    for section in all_sections.values():
        section.pop("_api_items", None)
    selected_section_key = V2_FILTER_PAGE_BY_ASSET[selected_asset_kind]
    sections = {selected_section_key: all_sections[selected_section_key]}
    subinterface_pairs = _app_v2_filter_common_query_pairs(filters)
    subinterfaces = [
        {
            "key": key,
            "label": section["component_label"],
            "anchor_id": section["anchor_id"],
            "href": _filter_href(f"/n6/app/filter-center/{key}", subinterface_pairs),
            "active": key == selected_section_key,
            "read_source_table": section["read_source_table"],
            "membership_read_source_table": section.get("membership_read_source_table"),
        }
        for key, section in all_sections.items()
    ]
    selected_base_href = f"/n6/app/filter-center/{selected_section_key}"
    filter_reset = {
        "label": "清除全部筛选",
        "href": selected_base_href,
        "active": bool(_filter_query_pairs(filters) or show_all),
        "readonly": True,
    }
    return {
        "ok": True,
        "component": component,
        "component_label": _component_label(component),
        "principal": app_principal_model(principal, user=user),
        "selected_asset_kind": selected_asset_kind,
        "selected_section_key": selected_section_key,
        "sections": sections,
        "date_selector": sections[selected_section_key]["date_selector"],
        "subinterfaces": subinterfaces,
        "common_filter_fields": list(V2_FILTER_COMMON_QUERY_FIELDS),
        "common_filter_pairs": [
            {"name": key, "value": value}
            for key, value in subinterface_pairs
        ],
        "filter_reset": filter_reset,
        "filter_labels": dict(V2_OVERHEAT_FILTER_LABELS),
        "direction_options": [
            {"value": "buy", "label": APP_DIRECTION_LABELS["buy"]},
            {"value": "sell", "label": APP_DIRECTION_LABELS["sell"]},
        ],
        "asset_kind_options": [
            {"value": "stock", "label": APP_ASSET_KIND_LABELS["stock"]},
            {"value": "board", "label": APP_ASSET_KIND_LABELS["board"]},
            {"value": "index", "label": APP_ASSET_KIND_LABELS["index"]},
        ],
        "board_type_options": ["tdx_industry", "tdx_concept", "tdx_region"],
        "readonly": True,
        "safety_banner": list(APP_V2_SAFETY_LABELS),
        "source_policy": app_v2_source_policy(),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def app_v2_monitor_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    result: dict[str, Any],
    selected_asset_kind: str | None = None,
    write_enabled: bool = False,
) -> dict[str, Any]:
    component = "B Track V2 My Monitor"
    selected_asset_kind = selected_asset_kind if selected_asset_kind in V2_MONITOR_TITLE_BY_ASSET else None
    monitor_status_filter = _monitor_status_filter(result.get("monitor_status_filter"))
    current_filter_batch = app_v2_monitor_current_filter_batch(result.get("current_filter_batch"))
    selected_for_trade_date = _first_text(result, "selected_for_trade_date")
    available_for_trade_dates = [
        str(item).strip()
        for item in result.get("available_for_trade_dates") or []
        if str(item).strip()
    ]
    if selected_for_trade_date and selected_for_trade_date not in available_for_trade_dates:
        available_for_trade_dates.insert(0, selected_for_trade_date)
    items = [app_v2_monitor_item(row) for row in result.get("items") or []]
    grouped = {asset_kind: [] for asset_kind in V2_MONITOR_TITLE_BY_ASSET}
    for item in items:
        grouped.setdefault(item["asset_kind"], []).append(item)
    status_counts = result.get("status_counts") if isinstance(result.get("status_counts"), dict) else {}
    sections = {
        "stocks": app_v2_monitor_section(
            "stock",
            grouped.get("stock") or [],
            tables_ready=bool(result.get("tables_ready")),
            status_counts=status_counts.get("stock"),
        ),
        "boards": app_v2_monitor_section(
            "board",
            grouped.get("board") or [],
            tables_ready=bool(result.get("tables_ready")),
            status_counts=status_counts.get("board"),
        ),
        "indexes": app_v2_monitor_section(
            "index",
            grouped.get("index") or [],
            tables_ready=bool(result.get("tables_ready")),
            status_counts=status_counts.get("index"),
        ),
    }
    selected_section_key = V2_MONITOR_PAGE_BY_ASSET.get(selected_asset_kind or "stock")
    subinterfaces = [
        {
            "key": page_key,
            "label": V2_MONITOR_TITLE_BY_ASSET[asset_kind],
            "href": app_v2_monitor_href(
                f"/n6/app/my-monitor/{page_key}",
                monitor_status=monitor_status_filter,
                for_trade_date=selected_for_trade_date,
            ),
            "active": selected_asset_kind == asset_kind,
        }
        for asset_kind, page_key in V2_MONITOR_PAGE_BY_ASSET.items()
    ]
    selected_batch_asset = selected_asset_kind or "stock"
    selected_batch = current_filter_batch.get(selected_batch_asset, app_v2_empty_monitor_batch())
    status_filter_links = [
        {
            "key": key,
            "label": label,
            "href": app_v2_monitor_href(
                f"/n6/app/my-monitor/{selected_section_key}",
                monitor_status=key,
                for_trade_date=selected_for_trade_date,
            ),
            "active": monitor_status_filter == key,
        }
        for key, label in V2_MONITOR_STATUS_FILTERS.items()
    ]
    tables_ready = bool(result.get("tables_ready"))
    status = "ready" if tables_ready else "data_not_ready"
    return {
        "ok": True,
        "component": component,
        "component_label": _component_label(component),
        "principal": app_principal_model(principal, user=user),
        "status": status,
        "status_label": _state_label(status),
        "tables_ready": tables_ready,
        "empty_state": "暂无监控对象",
        "locked_reason": "" if tables_ready else "监控对象表尚未准备完成",
        "selected_asset_kind": selected_asset_kind,
        "selected_section_key": selected_section_key,
        "monitor_status_filter": monitor_status_filter,
        "selected_for_trade_date": selected_for_trade_date,
        "available_for_trade_dates": available_for_trade_dates,
        "date_selector": app_v2_monitor_date_selector(
            selected_section_key=selected_section_key,
            selected_for_trade_date=selected_for_trade_date,
            available_for_trade_dates=available_for_trade_dates,
            monitor_status_filter=monitor_status_filter,
        ),
        "status_filter_links": status_filter_links,
        "current_filter_batch": current_filter_batch,
        "selected_current_batch": selected_batch,
        "current_batch_label": app_v2_monitor_batch_label(selected_batch),
        "signal_scope_notice": "已失效对象不会参与交易时间信号监控",
        "subinterfaces": subinterfaces,
        "sections": sections,
        "items": items,
        "notice": "当前仅保存监控范围，不代表交易建议",
        "controls": {
            "write_route_registered": True,
            "write_route_enabled": bool(write_enabled),
            "add_monitor_enabled": bool(write_enabled),
            "single_item_actions_only": True,
            "bulk_add_enabled": False,
            "pause_monitor_enabled": False,
            "pause_monitor_label": "暂停监控（暂未开放）",
            "remove_monitor_enabled": bool(write_enabled),
            "remove_monitor_label": "移除" if write_enabled else "写入功能未启用",
        },
        "readonly": not bool(write_enabled),
        "safety_banner": list(APP_V2_SAFETY_LABELS),
        "source_policy": app_v2_source_policy(),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }


def app_v2_monitor_href(base_href: str, *, monitor_status: str, for_trade_date: str = "") -> str:
    pairs = [("monitor_status", monitor_status)]
    if for_trade_date:
        pairs.append(("for_trade_date", for_trade_date))
    return _filter_href(base_href, pairs)

def app_v2_monitor_date_selector(
    *,
    selected_section_key: str,
    selected_for_trade_date: str,
    available_for_trade_dates: list[str],
    monitor_status_filter: str,
) -> dict[str, Any]:
    return {
        "base_href": f"/n6/app/my-monitor/{selected_section_key}",
        "selected_for_trade_date": selected_for_trade_date,
        "available_for_trade_dates": available_for_trade_dates,
        "monitor_status_filter": monitor_status_filter,
        "options": [
            {
                "value": trade_date,
                "label": trade_date,
                "selected": trade_date == selected_for_trade_date,
            }
            for trade_date in available_for_trade_dates
        ],
    }

def _monitor_status_filter(value: Any) -> str:
    text = str(value or "active").strip().lower()
    return text if text in V2_MONITOR_STATUS_FILTERS else "active"


def app_v2_empty_monitor_batch() -> dict[str, str]:
    return {"source_trade_date": "—", "for_trade_date": "—", "source_run_id": "—"}


def app_v2_monitor_current_filter_batch(raw: Any) -> dict[str, dict[str, str]]:
    source = raw if isinstance(raw, dict) else {}
    return {
        asset_kind: {
            "source_trade_date": _first_text(source.get(asset_kind) or {}, "source_trade_date"),
            "for_trade_date": _first_text(source.get(asset_kind) or {}, "for_trade_date"),
            "source_run_id": _first_text(source.get(asset_kind) or {}, "source_run_id", "run_id"),
        }
        for asset_kind in V2_MONITOR_TITLE_BY_ASSET
    }


def app_v2_monitor_batch_label(batch: dict[str, Any]) -> str:
    source_trade_date = _first_text(batch, "source_trade_date")
    for_trade_date = _first_text(batch, "for_trade_date")
    if not source_trade_date or not for_trade_date:
        return "当前有效批次：暂无"
    return f"当前有效批次：source_trade_date={source_trade_date} · for_trade_date={for_trade_date}"


def _monitor_status_counts(raw: Any) -> dict[str, int]:
    source = raw if isinstance(raw, dict) else {}
    return {
        "active": int(source.get("active") or 0),
        "expired": int(source.get("expired") or 0),
        "removed": int(source.get("removed") or 0),
        "all": int(source.get("all") or source.get("total") or 0),
    }


def app_v2_monitor_section(
    asset_kind: str,
    items: list[dict[str, Any]],
    *,
    tables_ready: bool,
    status_counts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = "ready" if tables_ready else "data_not_ready"
    counts = _monitor_status_counts(status_counts)
    columns = app_v2_monitor_columns(asset_kind, items)
    display_columns = [column for column in columns if column["key"] != "is_invalid"]
    for item in items:
        item["cells"] = [
            {
                "key": "is_invalid",
                "value": item.get("is_invalid_label") or "是",
                "align": "text",
                "sort_type": "text",
            },
            *_app_v2_filter_display_cells(item.get("display_row") or {}, display_columns),
        ]
    return {
        "asset_kind": asset_kind,
        "title": V2_MONITOR_TITLE_BY_ASSET[asset_kind],
        "status": status,
        "status_label": _state_label(status),
        "columns": columns,
        "items": items,
        "count": len(items),
        "status_counts": counts,
        "empty_state": "暂无监控对象" if tables_ready else "监控对象表尚未准备完成",
        "readonly": True,
    }


def app_v2_monitor_columns(asset_kind: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    schema_set: set[str] = set()
    rows: list[dict[str, Any]] = []
    for item in items:
        row = item.get("display_row") if isinstance(item.get("display_row"), dict) else {}
        rows.append(row)
        schema_set.update(str(key) for key in row.keys())
    visible_fields = list(V2_FILTER_VISIBLE_FIELDS_BY_ASSET.get(asset_kind, ()))
    if not visible_fields:
        visible_fields = sorted(schema_set)
    columns = [
        {
            "key": "is_invalid",
            "label": "是否失效",
            "sort_type": "text",
            "sortable": False,
            "sort_active": False,
            "sort_direction": "",
            "sort_href": "",
            "align": "text",
        }
    ]
    for field in visible_fields:
        sort_type = _app_v2_filter_infer_sort_type([row.get(field) for row in rows])
        columns.append(
            {
                "key": field,
                "label": field,
                "sort_type": sort_type,
                "sortable": False,
                "sort_active": False,
                "sort_direction": "",
                "sort_href": "",
                "align": "numeric" if sort_type == "number" else "text",
            }
        )
    return columns


def app_v2_monitor_display_row(row: dict[str, Any], *, asset_kind: str) -> dict[str, Any]:
    snapshot = _json_object(row.get("source_snapshot_json"))
    display_row = _json_object(row.get("current_display_row_json"))
    merged = {**snapshot, **display_row}
    merged.setdefault("for_trade_date", _first_text(row, "valid_for_trade_date"))
    merged.setdefault("source_trade_date", _first_text(row, "valid_source_trade_date"))
    merged.setdefault("source_run_id", _first_text(row, "valid_source_run_id", "source_run_id"))
    merged.setdefault("asset_kind", asset_kind)
    merged.setdefault("identity_key", _first_text(row, "identity_key"))
    merged.setdefault("display_name", _first_text(row, "display_name", "name"))
    merged.setdefault("display_code", _first_text(row, "display_code", "code"))
    return merged


def app_v2_monitor_source_context(row: dict[str, Any]) -> dict[str, Any]:
    snapshot = _json_object(row.get("source_snapshot_json"))
    source_type_raw = _first_available_text(row.get("source_type"), row.get("source")) or "single_row"
    source_type = V2_MONITOR_SOURCE_TYPE_BY_RAW.get(source_type_raw, source_type_raw)
    source_type_label = V2_MONITOR_SOURCE_LABEL_BY_TYPE.get(source_type, source_type or "—")
    fallback_object_kind = V2_MONITOR_SOURCE_OBJECT_KIND_BY_TYPE.get(source_type, "")
    source_object_kind = _first_available_text(
        row.get("source_parent_asset_kind"),
        snapshot.get("parent_asset_kind"),
    ) or fallback_object_kind
    source_object_identity_key = _first_available_text(
        row.get("source_parent_identity_key"),
        snapshot.get("parent_identity_key"),
    )
    source_object_code = _first_available_text(row.get("source_parent_code"), snapshot.get("parent_code"))
    source_object_name = _first_available_text(row.get("source_parent_name"), snapshot.get("parent_name"))
    row_relation_date_key = "source_parent_" + "tra" + "de_date"
    snapshot_relation_date_key = "membership_" + "tra" + "de_date"
    membership_relation_date = _first_available_text(
        row.get(row_relation_date_key),
        snapshot.get(snapshot_relation_date_key),
    )
    if source_type == "direct":
        source_object_kind = "none"
        source_object_identity_key = ""
        source_object_code = ""
        source_object_name = ""
        membership_relation_date = ""
    return {
        "source_type_raw": source_type_raw,
        "source_type": source_type,
        "source_type_label": source_type_label,
        "source_object_kind": source_object_kind or "none",
        "source_object_identity_key": source_object_identity_key or None,
        "source_object_code": source_object_code or None,
        "source_object_name": source_object_name or None,
        "membership_relation_date": membership_relation_date or None,
    }


def app_v2_monitor_source_parent(row: dict[str, Any]) -> dict[str, Any]:
    source_context = app_v2_monitor_source_context(row)
    snapshot = _json_object(row.get("source_snapshot_json"))
    parent_asset_kind = source_context["source_object_kind"]
    parent_identity_key = source_context["source_object_identity_key"] or ""
    parent_code = source_context["source_object_code"] or ""
    parent_name = source_context["source_object_name"] or ""
    trade_date = source_context["membership_relation_date"] or ""
    source_version = _first_available_text(
        row.get("source_parent_source_version"),
        snapshot.get("membership_source_version"),
    )
    source_batch_id = _first_available_text(
        row.get("source_parent_source_batch_id"),
        snapshot.get("membership_source_batch_id"),
    )
    linked_mode = _first_available_text(row.get("source_linked_mode"), snapshot.get("linked_mode"))
    available = bool(parent_identity_key)
    return {
        "available": available,
        "asset_kind": parent_asset_kind or "—",
        "asset_kind_label": _asset_kind_label(parent_asset_kind),
        "title_label": source_context["source_type_label"],
        "identity_key": parent_identity_key or "—",
        "display_code": parent_code or "—",
        "display_name": parent_name or "—",
        "trade_date": trade_date or "—",
        "source_version": source_version or "—",
        "source_batch_id": source_batch_id or "—",
        "linked_mode": linked_mode or "—",
    }


def app_v2_monitor_invalid_reason(
    row: dict[str, Any],
    *,
    original_batch: dict[str, Any],
    current_batch: dict[str, Any],
    is_valid: bool,
) -> str:
    if is_valid:
        return ""
    effective_status = _first_text(row, "effective_status", default="")
    if effective_status == "removed":
        return _first_text(row, "expired_reason", default="removed")

    original_for_trade_date = _first_text(original_batch, "for_trade_date", default="")
    current_for_trade_date = _first_text(current_batch, "for_trade_date", default="")
    if original_for_trade_date and current_for_trade_date and original_for_trade_date != current_for_trade_date:
        return "for_trade_date_mismatch"

    original_source_trade_date = _first_text(original_batch, "source_trade_date", default="")
    current_source_trade_date = _first_text(current_batch, "source_trade_date", default="")
    if (
        original_source_trade_date
        and current_source_trade_date
        and original_source_trade_date != current_source_trade_date
    ):
        return "source_trade_date_mismatch"

    original_source_run_id = _first_text(original_batch, "source_run_id", default="")
    current_source_run_id = _first_text(current_batch, "source_run_id", default="")
    if original_source_run_id and current_source_run_id and original_source_run_id != current_source_run_id:
        return "source_run_id_mismatch"

    return _first_text(row, "expired_reason", default="filter_batch_changed")


def app_v2_monitor_memberships(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("current_memberships")
    current = raw if isinstance(raw, dict) else {}
    indexes = [
        app_v2_monitor_membership_item(item, asset_kind="index")
        for item in current.get("indexes", [])
        if isinstance(item, dict)
    ]
    boards = [
        app_v2_monitor_membership_item(item, asset_kind="board")
        for item in current.get("boards", [])
        if isinstance(item, dict)
    ]
    return {
        "indexes": indexes,
        "boards": boards,
        "index_count": len(indexes),
        "board_count": len(boards),
        "summary_label": f"所属指数 {len(indexes)} 个 / 所属板块 {len(boards)} 个",
    }


def app_v2_monitor_membership_item(row: dict[str, Any], *, asset_kind: str) -> dict[str, Any]:
    return {
        "asset_kind": asset_kind,
        "asset_kind_label": _asset_kind_label(asset_kind),
        "identity_key": _first_text(row, "identity_key"),
        "display_code": _first_text(row, "display_code", "code"),
        "display_name": _first_text(row, "display_name", "name"),
        "board_type": _first_text(row, "board_type"),
        "trade_date": _first_text(row, "trade_date"),
        "source_version": _first_text(row, "source_version"),
        "source_batch_id": _first_text(row, "source_batch_id"),
    }


def app_v2_monitor_item(row: dict[str, Any]) -> dict[str, Any]:
    asset_kind = _first_text(row, "asset_kind")
    direction = _first_text(row, "direction", default="buy")
    status = _first_text(row, "status", default="active")
    effective_status = _first_text(row, "effective_status", default=status)
    original_batch = row.get("validity", {}).get("original_batch") if isinstance(row.get("validity"), dict) else {}
    current_batch = row.get("validity", {}).get("current_batch") if isinstance(row.get("validity"), dict) else {}
    original_batch = original_batch if isinstance(original_batch, dict) else {}
    current_batch = current_batch if isinstance(current_batch, dict) else {}
    source_context = app_v2_monitor_source_context(row)
    is_valid = bool(row.get("effective_active"))
    display_row = app_v2_monitor_display_row(row, asset_kind=asset_kind)
    invalid_reason = app_v2_monitor_invalid_reason(
        row,
        original_batch=original_batch,
        current_batch=current_batch,
        is_valid=is_valid,
    )
    return {
        "monitor_id": canonical_bigint_id(
            row.get("monitor_id"),
            field_name="monitor_id",
            required=True,
        ),
        "principal_id": canonical_bigint_id(
            row.get("principal_id"),
            field_name="principal_id",
            required=True,
        ),
        "principal_type": _first_text(row, "principal_type"),
        "asset_kind": asset_kind,
        "asset_kind_label": _asset_kind_label(asset_kind),
        "identity_key": _first_text(row, "identity_key"),
        "display_name": _first_text(row, "display_name", "name"),
        "display_code": _first_text(row, "display_code", "code"),
        "direction": direction,
        "direction_label": _direction_label(direction),
        "source": source_context["source_type"],
        "source_type_raw": source_context["source_type_raw"],
        "source_type": source_context["source_type"],
        "source_type_label": source_context["source_type_label"],
        "source_object_kind": source_context["source_object_kind"],
        "source_object_identity_key": source_context["source_object_identity_key"],
        "source_object_code": source_context["source_object_code"],
        "source_object_name": source_context["source_object_name"],
        "membership_relation_date": source_context["membership_relation_date"],
        "condition_key": _first_text(row, "condition_key"),
        "source_run_id": _first_text(row, "source_run_id"),
        "projection_run_id": _first_text(row, "projection_run_id"),
        "last_signal_state": _first_text(row, "last_signal_state"),
        "last_signal_state_label": _state_label(_first_text(row, "last_signal_state")),
        "quality_status": _first_text(row, "quality_status", default="reviewed"),
        "status": status,
        "status_label": _state_label(status),
        "effective_status": effective_status,
        "effective_status_label": _first_text(row, "effective_status_label", default="有效" if effective_status == "active" else "已失效"),
        "effective_active": is_valid,
        "is_valid": is_valid,
        "is_invalid_label": "否" if is_valid else "是",
        "invalid_reason": invalid_reason,
        "expired_at": _first_text(row, "expired_at"),
        "expired_reason": _first_text(row, "expired_reason"),
        "expired_reason_label": _first_text(row, "expired_reason_label"),
        "valid_for_trade_date": _first_text(row, "valid_for_trade_date"),
        "valid_source_trade_date": _first_text(row, "valid_source_trade_date"),
        "valid_source_run_id": _first_text(row, "valid_source_run_id"),
        "validity": {
            "original_batch": {
                "source_trade_date": _first_text(original_batch, "source_trade_date"),
                "for_trade_date": _first_text(original_batch, "for_trade_date"),
                "source_run_id": _first_text(original_batch, "source_run_id"),
            },
            "current_batch": {
                "source_trade_date": _first_text(current_batch, "source_trade_date"),
                "for_trade_date": _first_text(current_batch, "for_trade_date"),
                "source_run_id": _first_text(current_batch, "source_run_id"),
            },
        },
        "created_at": _first_text(row, "created_at"),
        "updated_at": _first_text(row, "updated_at"),
        "removed_at": _first_text(row, "removed_at"),
        "source_parent": app_v2_monitor_source_parent(row),
        "current_memberships": app_v2_monitor_memberships(row),
        "display_row": display_row,
    }


def app_condition_trace(row: dict[str, Any]) -> dict[str, Any]:
    condition_key = _first_text(row, "condition_key", "original_condition_key")
    return {
        "condition_key": condition_key,
        "original_condition_key": _first_text(row, "original_condition_key", default=condition_key),
        "condition_family": _condition_family(condition_key),
        "signal_type": _first_text(row, "signal_type"),
        "direction": _first_text(row, "direction"),
        "rendering_policy": "source_trace_only_not_advice",
        "buy_hint_sell_hint_policy": "condition_source_only_not_tip_stock_or_advice",
    }


def app_evidence_chain(row: dict[str, Any]) -> dict[str, Any]:
    asset_kind = str(row.get("asset_kind") or "").strip()
    condition_cache = str(row.get("condition_display_cache_source") or "").strip()
    if not condition_cache:
        condition_cache = CONDITION_CACHE_SOURCE_BY_ASSET.get(asset_kind, "reviewed N6 projections")
    membership_cache = str(row.get("membership_cache_source") or "").strip()
    if not membership_cache:
        membership_cache = MEMBERSHIP_CACHE_SOURCE_BY_ASSET.get(asset_kind, "reviewed N6 projections")
    return {
        "N2_display_basis": {
            "source": condition_cache,
            "membership_source": membership_cache,
            "display_basis_id": canonical_bigint_id(
                row.get("source_condition_display_basis_id"),
                field_name="source_condition_display_basis_id",
            ),
            "display_run_id": _first_text(row, "source_condition_display_run_id", default="—"),
            "condition_key": _first_text(row, "condition_key", "original_condition_key"),
            "readonly_explanation_only": True,
        },
        "N3_market_data": {
            "source": "reviewed N6 projection trace",
            "source_run_id": _first_text(
                row,
                "n3_source_run_id",
                "source_market_run_id",
                "market_data_run_id",
                "projection_metric_run_id",
                default="—",
            ),
            "direct_live_market_read": False,
            "raw_k_read": False,
        },
        "N4_trigger": {
            "source": "reviewed N6 projection trace",
            "source_run_id": _first_text(row, "source_n4_run_id", "n4_source_run_id", default="—"),
            "event_id": _first_text(row, "n4_trigger_event_id", default="—"),
            "raw_fact_bypass": False,
        },
        "N5_action": {
            "source": "reviewed N6 projection trace",
            "source_run_id": _first_text(row, "source_action_run_id"),
            "event_id": _first_text(row, "source_action_event_id", "source_event_id"),
            "event_type": _first_text(row, "source_action_event_type", "event_type"),
            "action_state": _first_text(row, "action_state"),
            "action_mark": _first_text(row, "action_mark"),
            "blocked_reason": _first_text(row, "blocked_reason"),
            "raw_fact_bypass": False,
        },
        "N6_projection": {
            "source": "reviewed N6 projections",
            "projection_run_id": _first_text(row, "user_projection_run_id", "projection_run_id"),
            "user_signal_projection_id": canonical_bigint_id(
                row.get("user_signal_projection_id"),
                field_name="user_signal_projection_id",
                required=True,
            ),
            "user_signal_card_id": canonical_bigint_id(
                row.get("user_signal_card_id"),
                field_name="user_signal_card_id",
            ),
            "quality_status": _first_text(row, "quality_status", default="reviewed"),
        },
    }


def app_signal_tags(item: dict[str, Any], row: dict[str, Any]) -> list[str]:
    action_state = str(item.get("action_state") or row.get("action_state") or "").strip()
    event_type = _first_text(row, "event_type", "source_action_event_type")
    blocked_reason = str(item.get("blocked_reason") or row.get("blocked_reason") or "").strip()
    tags: list[str] = []
    if action_state == "executed" or event_type == "ActionExecuted":
        tags.append(APP_EVENT_LABELS["ActionExecuted"])
    if action_state == "blocked" or event_type == "ActionBlocked":
        tags.append(APP_EVENT_LABELS["ActionBlocked"])
    if blocked_reason == "metric_missing" or event_type == "TriggerPendingMarketData":
        tags.append(APP_EVENT_LABELS["TriggerPendingMarketData"])
    if event_type == "TriggerStateChanged":
        tags.append(APP_EVENT_LABELS["TriggerStateChanged"])
    return tags or [APP_EVENT_LABELS["TriggerStateChanged"]]


def app_signal_detail_policy(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "readonly": True,
        "buy_button_visible": False,
        "sell_button_visible": False,
        "one_click_order_visible": False,
        "auto_trade_toggle_visible": False,
        "investment_advice": False,
        "hint_rendering_policy": "BUY_HINT/SELL_HINT are condition traces only, not tip stocks or investment advice",
        "proposal_generated": False,
        "order_generated": False,
        "trade_generated": False,
        "position_updated": False,
        "pnl_generated": False,
        "real_trade_submitted": False,
        "condition_trace": app_condition_trace(row),
    }


def _first_text(row: dict[str, Any], *keys: str, default: Any = "—") -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return str(value)
    return str(default)


def _first_available_text(*values: Any) -> str:
    for value in values:
        if value is not None and str(value).strip() != "":
            return str(value)
    return ""


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _field_value_text(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        text = value.strip()
        return text if text else "—"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return str(value)


def _list_text(row: dict[str, Any], key: str) -> list[str]:
    value = row.get(key)
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item or "").strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("{") and text.endswith("}"):
        return [part.strip().strip('"') for part in text[1:-1].split(",") if part.strip()]
    return [text]


def _direction_list_label(values: list[str]) -> str:
    labels = [_direction_label(value) for value in values if str(value or "").strip()]
    return "、".join(labels) if labels else "—"


def _condition_family(condition_key: str) -> str:
    value = str(condition_key or "").strip()
    for family in ("BUY_HINT", "SELL_HINT", "BUY", "SELL"):
        if value == family or value.startswith(f"{family}:"):
            return family
    return "—"


def _count_action(signal_items: list[dict[str, Any]], action_state: str, event_type: str) -> int:
    return sum(
        1
        for item in signal_items
        if str(item.get("action_state") or "") == action_state
        or str(item.get("event_type") or "") == event_type
    )


def _count_by(signal_items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in signal_items:
        value = str(item.get(key) or "—").strip() or "—"
        counts[value] = counts.get(value, 0) + 1
    return counts


def _money_text(value: Any) -> str:
    number = number_or_none(value)
    if number is None:
        return "—"
    return f"{number:,.2f}"


def app_empty_planned_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    component: str,
    status: str = "planned",
    items: list[dict[str, Any]] | None = None,
    disclaimer: list[str] | None = None,
) -> dict[str, Any]:
    payload = {
        "ok": True,
        "component": component,
        "component_label": _component_label(component),
        "principal": app_principal_model(principal, user=user),
        "status": status,
        "status_label": _state_label(status),
        "items": list(items or []),
        "readonly": True,
        "safety_banner": list(APP_SAFETY_LABELS),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }
    if disclaimer is not None:
        payload["disclaimer"] = list(disclaimer)
    return payload


def app_locked_future_module_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    module_key: str,
    component: str,
) -> dict[str, Any]:
    config_by_key = {
        "proposals": {
            "status": "locked_planned",
            "reason": APP_FUTURE_MODULE_NOTICE,
            "next_gate": "B_TRACK_PROPOSALS_V2_CONTRACT_GATE",
        },
        "portfolio": {
            "status": "locked_empty",
            "reason": APP_FUTURE_MODULE_NOTICE,
            "next_gate": "B_TRACK_PORTFOLIO_V2_CONTRACT_GATE",
        },
        "pnl": {
            "status": "locked_empty",
            "reason": APP_FUTURE_MODULE_NOTICE,
            "next_gate": "B_TRACK_PNL_V2_CONTRACT_GATE",
        },
        "leaderboard": {
            "status": "locked_planned",
            "reason": APP_FUTURE_MODULE_NOTICE,
            "next_gate": "B_TRACK_LEADERBOARD_V2_CONTRACT_GATE",
        },
        "future_automation": {
            "status": "locked_readiness_only",
            "reason": APP_FUTURE_MODULE_NOTICE,
            "next_gate": "B_TRACK_AUTOMATION_V3_CONTRACT_GATE",
        },
    }
    config = config_by_key.get(
        module_key,
        {
            "status": "locked_planned",
            "reason": APP_FUTURE_MODULE_NOTICE,
            "next_gate": "B_TRACK_FUTURE_MODULE_CONTRACT_GATE",
        },
    )
    payload = app_empty_planned_model(
        principal,
        user=user,
        component=component,
        status=str(config["status"]),
        items=[],
        disclaimer=APP_DISCLAIMER if module_key in {"pnl", "leaderboard"} else None,
    )
    payload.update(
        {
            "module_key": module_key,
            "locked": True,
            "planned": True,
            "status_label": _state_label(str(config["status"])),
            "reason": str(config["reason"]),
            "next_gate": str(config["next_gate"]),
            "controls": {
                "entry_enabled": False,
                "proposal_enabled": False,
                "order_enabled": False,
                "trade_enabled": False,
                "position_update_enabled": False,
                "pnl_generation_enabled": False,
                "leaderboard_materialization_enabled": False,
                "auto_trade_enabled": False,
                "real_trade_enabled": False,
            },
            "source_policy": app_signal_source_policy(),
        }
    )
    return payload


def app_portfolio_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    positions: list[dict[str, Any]],
    now: datetime | None = None,
    proposal_write_enabled: bool = False,
) -> dict[str, Any]:
    current_time = _portfolio_aware_datetime(now) or datetime.now(PORTFOLIO_TIMEZONE)
    items = [
        app_position_item(
            row,
            now=current_time,
            proposal_write_enabled=proposal_write_enabled,
        )
        for row in positions
    ]
    payload = app_empty_planned_model(
        principal,
        user=user,
        component="B Track Portfolio",
        status="readonly" if items else "empty",
        items=items,
    )
    payload.update(
        {
            "locked": False,
            "planned": False,
            "empty_state": "当前没有持仓",
            "proposal_write_enabled": proposal_write_enabled,
            "source_policy": portfolio_source_policy(),
        }
    )
    return payload


def app_pnl_model(
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    return app_empty_planned_model(
        principal,
        user=user,
        component="B Track PnL",
        status="empty" if not snapshots else "readonly",
        items=[app_pnl_item(row) for row in snapshots],
        disclaimer=APP_DISCLAIMER,
    )


def app_leaderboard_model(principal: dict[str, Any], *, user: dict[str, Any]) -> dict[str, Any]:
    payload = app_locked_future_module_model(
        principal, user=user, module_key="leaderboard", component="B Track Leaderboard"
    )
    payload["leaderboard_materialized"] = False
    return payload


def portfolio_source_policy() -> dict[str, Any]:
    return {
        "allowed_sources": list(PORTFOLIO_ALLOWED_SOURCES),
        "forbidden_sources": list(PORTFOLIO_FORBIDDEN_SOURCES),
        "n2_n5_raw_facts_read": False,
        "n3_facts_read": False,
        "external_market_read": False,
        "mootdx_called": False,
    }


def _portfolio_aware_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    candidate = value
    if not isinstance(candidate, datetime):
        text = str(candidate).strip()
        if not text:
            return None
        try:
            candidate = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if candidate.tzinfo is None or candidate.utcoffset() is None:
        return None
    return candidate.astimezone(PORTFOLIO_TIMEZONE)


def _portfolio_datetime_text(value: Any) -> str | None:
    candidate = _portfolio_aware_datetime(value)
    return candidate.isoformat() if candidate is not None else None


def _portfolio_is_trading_session(value: datetime) -> bool:
    local = value.astimezone(PORTFOLIO_TIMEZONE)
    current = (local.hour, local.minute)
    return local.weekday() < 5 and ((9, 30) <= current <= (11, 30) or (13, 0) <= current <= (15, 0))


def _portfolio_position_exchange(row: dict[str, Any]) -> str:
    explicit = str(row.get("position_exchange") or "").strip().upper()
    if explicit:
        return explicit
    identity_parts = str(row.get("identity_key") or "").split(":")
    return identity_parts[1].upper() if len(identity_parts) == 3 else ""


def _portfolio_quote_quality_passed(row: dict[str, Any]) -> bool:
    position_exchange = _portfolio_position_exchange(row)
    quote_exchange = str(row.get("quote_exchange") or "").strip().upper()
    quality_status = str(row.get("quality_status") or "").strip().lower()
    current_price = _decimal_or_none(row.get("current_price"))
    return (
        position_exchange in {"SH", "SZ"}
        and quote_exchange == position_exchange
        and quality_status == "passed"
        and current_price is not None
        and current_price.is_finite()
        and current_price > Decimal("0")
    )


def _portfolio_quote_status(row: dict[str, Any], *, now: datetime) -> str:
    if not _portfolio_quote_quality_passed(row):
        return "not_ready"
    if _portfolio_aware_datetime(row.get("quote_minute")) is None:
        return "not_ready"
    if not _portfolio_is_trading_session(now):
        return "market_closed"
    fetched_at = _portfolio_aware_datetime(row.get("fetched_at"))
    if fetched_at is None:
        return "stale"
    age_seconds = Decimal(str((now - fetched_at).total_seconds()))
    return "fresh" if Decimal("0") <= age_seconds <= PORTFOLIO_FRESH_SECONDS else "stale"


def _portfolio_decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _portfolio_nonnegative_decimal(value: Any) -> Decimal | None:
    candidate = _decimal_or_none(value)
    return candidate if candidate is not None and candidate.is_finite() and candidate >= 0 else None


def _portfolio_positive_price(value: Any) -> Decimal | None:
    candidate = _decimal_or_none(value)
    return candidate if candidate is not None and candidate.is_finite() and candidate > 0 else None


def _portfolio_date_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    text = str(value).strip()
    return text if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text) else None


def _portfolio_positive_episode(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 and str(value).strip() == str(parsed) else None


def app_position_item(
    row: dict[str, Any],
    *,
    now: datetime,
    proposal_write_enabled: bool = False,
) -> dict[str, Any]:
    quote_status = _portfolio_quote_status(row, now=now)
    quantity = _portfolio_nonnegative_decimal(row.get("quantity"))
    sellable_quantity = _portfolio_nonnegative_decimal(row.get("sellable_quantity"))
    t1_locked_quantity = _portfolio_nonnegative_decimal(row.get("t1_locked_quantity"))
    lot_quantity_total = _portfolio_nonnegative_decimal(row.get("lot_quantity_total"))
    average_cost = _portfolio_positive_price(row.get("average_cost"))
    source_price = _decimal_or_none(row.get("current_price"))
    usable_price = source_price if quote_status in {"fresh", "market_closed"} else None
    market_value = quantity * usable_price if quantity is not None and usable_price is not None else None
    unrealized_pnl = (
        (usable_price - average_cost) * quantity
        if usable_price is not None and average_cost is not None and quantity is not None
        else None
    )
    unrealized_return_pct = (
        ((usable_price - average_cost) / average_cost * Decimal("100")).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        if usable_price is not None and average_cost is not None and average_cost > 0
        else None
    )
    identity_key = str(row.get("identity_key") or "")
    identity_parts = identity_key.split(":")
    virtual_position_id = canonical_bigint_id(
        row.get("virtual_position_id"),
        field_name="virtual_position_id",
    )
    holding_episode_no = _portfolio_positive_episode(row.get("holding_episode_no"))
    lot_scope_ready = bool(
        quantity is not None
        and quantity > 0
        and lot_quantity_total == quantity
        and sellable_quantity is not None
        and t1_locked_quantity is not None
        and sellable_quantity + t1_locked_quantity == lot_quantity_total
        and holding_episode_no is not None
        and _portfolio_date_text(row.get("current_trade_date")) is not None
    )
    position_open = str(row.get("position_status") or "") == "open_virtual"
    manual_sell_available = bool(
        proposal_write_enabled
        and virtual_position_id
        and position_open
        and lot_scope_ready
        and sellable_quantity is not None
        and sellable_quantity > 0
    )
    if not proposal_write_enabled:
        manual_sell_disabled_reason = "交易申请未启用"
    elif not position_open:
        manual_sell_disabled_reason = "持仓状态不可卖"
    elif not lot_scope_ready:
        manual_sell_disabled_reason = "交易日或持仓批次数量未就绪"
    elif sellable_quantity == 0 and t1_locked_quantity and t1_locked_quantity > 0:
        manual_sell_disabled_reason = "T+1 锁定，当前无可卖数量"
    elif sellable_quantity == 0:
        manual_sell_disabled_reason = "当前无可卖数量"
    else:
        manual_sell_disabled_reason = None

    target_price = _portfolio_positive_price(row.get("target_price"))
    target_price_status = str(row.get("target_price_status") or "not_ready")
    if target_price_status not in {"not_ready", "frozen"} or (
        target_price_status == "frozen" and target_price is None
    ):
        target_price_status = "not_ready"
        target_price = None
    elif target_price_status == "not_ready":
        target_price = None

    stop_loss_price = _portfolio_positive_price(row.get("stop_loss_price"))
    stop_loss_status = str(row.get("stop_loss_status") or "not_ready")
    stop_loss_effective_trade_date = _portfolio_date_text(row.get("stop_loss_effective_trade_date"))
    stop_loss_source_quote_snapshot_id = canonical_bigint_id(
        row.get("stop_loss_source_quote_snapshot_id"),
        field_name="stop_loss_source_quote_snapshot_id",
    )
    stop_loss_frozen_at = _portfolio_datetime_text(row.get("stop_loss_frozen_at"))
    if stop_loss_status not in {"not_ready", "provisional_first_day", "frozen", "disabled"}:
        stop_loss_status = "not_ready"
        stop_loss_price = None
    elif stop_loss_status in {"not_ready", "disabled"}:
        stop_loss_price = None
    elif stop_loss_price is None:
        stop_loss_status = "not_ready"
    elif stop_loss_status == "frozen" and (
        stop_loss_effective_trade_date is None
        or stop_loss_source_quote_snapshot_id is None
        or stop_loss_frozen_at is None
    ):
        stop_loss_status = "not_ready"
        stop_loss_price = None
    return {
        "virtual_position_id": virtual_position_id,
        "identity_key": identity_key,
        "stock_code": str(row.get("stock_code") or (identity_parts[2] if len(identity_parts) == 3 else "")),
        "stock_name": str(row.get("stock_name") or "").strip(),
        "industry_code": str(row.get("industry_code") or "").strip(),
        "industry_name": str(row.get("industry_name") or "").strip(),
        "quantity": _portfolio_decimal_text(quantity),
        "sellable_quantity": _portfolio_decimal_text(sellable_quantity),
        "t1_locked_quantity": _portfolio_decimal_text(t1_locked_quantity),
        "lot_quantity_total": _portfolio_decimal_text(lot_quantity_total),
        "average_cost": _portfolio_decimal_text(average_cost),
        "current_price": _portfolio_decimal_text(usable_price),
        "quote_minute": _portfolio_datetime_text(row.get("quote_minute")),
        "fetched_at": _portfolio_datetime_text(row.get("fetched_at")),
        "quote_status": quote_status,
        "quality_reason": str(row.get("quality_reason") or "").strip() or None,
        "market_value": _portfolio_decimal_text(market_value),
        "unrealized_pnl": _portfolio_decimal_text(unrealized_pnl),
        "unrealized_return_pct": _portfolio_decimal_text(unrealized_return_pct),
        "position_status": str(row.get("position_status") or "not_ready"),
        "holding_episode_no": holding_episode_no,
        "first_open_trade_date": _portfolio_date_text(row.get("first_open_trade_date")),
        "current_trade_date": _portfolio_date_text(row.get("current_trade_date")),
        "target_price": _portfolio_decimal_text(target_price),
        "target_price_status": target_price_status,
        "stop_loss_price": _portfolio_decimal_text(stop_loss_price),
        "stop_loss_status": stop_loss_status,
        "stop_loss_effective_trade_date": stop_loss_effective_trade_date,
        "stop_loss_source_quote_snapshot_id": stop_loss_source_quote_snapshot_id,
        "stop_loss_frozen_at": stop_loss_frozen_at,
        "stop_loss_policy_version": str(row.get("stop_loss_policy_version") or "").strip() or None,
        "stop_loss_policy_hash": str(row.get("stop_loss_policy_hash") or "").strip() or None,
        "lot_scope_ready": lot_scope_ready,
        "manual_sell_available": manual_sell_available,
        "manual_sell_disabled_reason": manual_sell_disabled_reason,
    }


def app_pnl_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "pnl_snapshot_id": row.get("pnl_snapshot_id"),
        "virtual_account_id": row.get("virtual_account_id"),
        "trade_date": row.get("trade_date") or "—",
        "gross_pnl": number_or_none(row.get("gross_pnl")),
        "realized_pnl": number_or_none(row.get("realized_pnl")),
        "unrealized_pnl": number_or_none(row.get("unrealized_pnl")),
        "net_pnl": number_or_none(row.get("net_pnl")),
        "total_asset_value": number_or_none(row.get("total_asset_value")),
        "pnl_status": row.get("pnl_status") or "—",
        "snapshot_time": display_datetime(row.get("snapshot_time")),
    }


def app_page_model(
    page_key: str,
    principal: dict[str, Any],
    *,
    user: dict[str, Any],
    data: dict[str, Any],
) -> dict[str, Any]:
    return {
        "page_key": page_key,
        "page_title": APP_PAGE_LABELS.get(page_key, page_key),
        "app_title": "N6 多用户前台",
        "principal": app_principal_model(principal, user=user),
        "safety": list(data.get("safety_banner") or APP_SAFETY_LABELS),
        "nav": app_nav_context(page_key),
        "data": data,
        "source_policy": data.get("source_policy") or app_signal_source_policy(),
        "disclaimer": (
            []
            if data.get("locked")
            else AI_AGENT_PUBLIC_DISCLAIMER
            if page_key == "ai-agent"
            else APP_DISCLAIMER
            if page_key in {"pnl", "leaderboard"}
            else []
        ),
        "side_effects": dict(APP_SIDE_EFFECTS),
    }
