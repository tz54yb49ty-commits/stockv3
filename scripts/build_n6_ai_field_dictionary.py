#!/usr/bin/env python3
"""Build the reviewable N6 AI field inventory from a read-only catalog snapshot.

The builder never connects to PostgreSQL.  A runtime-control or N6_user
preflight must supply a JSON catalog snapshot captured in a read-only
transaction.  Planned 055 relations are parsed from the committed migration.
Fields without a reviewed semantic rule remain forbidden to the Agent.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


DICTIONARY_VERSION = "n6_ai_field_dictionary_v1"
SOURCE_COMMIT = "82f9a3401f4dfc813eb46e3adbfbaa5958895ecc"
HIGHEST_ACTIVE_MIGRATION = "054"
PLANNED_MIGRATION = "055"

RELATION_POLICY = {
    "v_n6_stock_condition_display_basis": ("filter_view", "context_only"),
    "v_n6_index_condition_display_basis": ("filter_view", "context_only"),
    "v_n6_board_condition_display_basis": ("filter_view", "context_only"),
    "v_n6_index_membership_fact": ("membership_view", "context_only"),
    "v_n6_board_membership_fact": ("membership_view", "context_only"),
    "user_projection_run": ("human_projection", "forbidden"),
    "user_signal_projection": ("human_projection", "forbidden"),
    "user_signal_card": ("human_projection", "forbidden"),
    "user_monitor_stock": ("human_private_scope", "forbidden"),
    "user_monitor_index": ("human_private_scope", "forbidden"),
    "user_monitor_board": ("human_private_scope", "forbidden"),
    "user_realtime_monitor_scope": ("human_private_scope", "forbidden"),
    "n6_principal": ("identity_authority", "audit_only"),
    "n6_ai_user": ("ai_identity", "audit_only"),
    "n6_strategy": ("ai_strategy", "audit_only"),
    "n6_virtual_account": ("ai_own_account", "decision"),
    "n6_virtual_cash_ledger": ("ai_own_account", "audit_only"),
    "n6_virtual_cash_snapshot": ("ai_own_account", "decision"),
    "n6_virtual_trade_proposal": ("ai_own_execution", "audit_only"),
    "n6_virtual_order": ("ai_own_execution", "audit_only"),
    "n6_virtual_trade": ("ai_own_execution", "audit_only"),
    "n6_virtual_position": ("ai_own_position", "decision"),
    "n6_virtual_position_event": ("ai_own_position", "audit_only"),
    "n6_virtual_position_lot": ("ai_own_position", "decision"),
    "n6_virtual_pnl_snapshot": ("ai_own_account", "audit_only"),
    "n6_virtual_quote_run": ("quote_audit", "audit_only"),
    "n6_virtual_quote_snapshot": ("quote", "decision"),
    "n6_virtual_quote_run_identity": ("quote_audit", "audit_only"),
    "v_n6_virtual_quote_latest": ("quote", "decision"),
    "n6_ai_shared_signal_projection": ("ai_shared_signal", "decision"),
    "n6_ai_context_snapshot": ("ai_context", "audit_only"),
    "n6_ai_decision_run": ("ai_decision", "audit_only"),
    "n6_ai_decision": ("ai_decision", "audit_only"),
    "n6_ai_daily_summary": ("ai_summary", "display_only"),
    "n6_ai_strategy_evaluation": ("ai_strategy", "audit_only"),
}

RELATION_GRAIN = {
    "filter_view": "one display-safe condition row per source display-basis grain",
    "membership_view": "one approved index/board membership fact",
    "human_projection": "human-principal projection grain; semantic documentation only",
    "human_private_scope": "one human-principal private scope row",
    "identity_authority": "one N6 principal",
    "ai_identity": "one AI actor",
    "ai_strategy": "one strategy or candidate evaluation",
    "ai_own_account": "one AI-owned account fact or account snapshot",
    "ai_own_execution": "one AI-owned proposal/order/trade fact",
    "ai_own_position": "one AI-owned position, lot, or position event",
    "quote": "one approved N3N6Q-derived virtual quote fact",
    "quote_audit": "one quote collection run or run identity audit fact",
    "ai_shared_signal": "one sanitized N6 shared signal projection",
    "ai_context": "one immutable Agent context snapshot",
    "ai_decision": "one Agent run or structured decision fact",
    "ai_summary": "one AI daily summary per trade date",
}

EXACT_SEMANTICS = {
    "for_trade_date": (
        "生效交易日",
        "The open trade date for which the row is valid.",
        "date",
        "decision",
        "Must equal the current approved open trade date for live decisions.",
        "Do not treat as source_trade_date or prev_trade_date.",
    ),
    "source_trade_date": (
        "来源交易日",
        "Trade date carried by the frozen upstream source lineage.",
        "date",
        "audit_only",
        "May differ from the current effective date by contract.",
        "Never substitute for for_trade_date.",
    ),
    "prev_trade_date": (
        "前一交易日",
        "Previous open trade date used by the frozen calculation.",
        "date",
        "context_only",
        "Historical reference only.",
        "Never authorize a live or historical trade.",
    ),
    "identity_key": (
        "规范标的键",
        "Exchange-qualified canonical asset identity.",
        None,
        "decision",
        "Must match the frozen row and approved asset-kind contract.",
        "A code without exchange qualification is not equivalent.",
    ),
    "stock_identity_key": (
        "股票规范标的键",
        "Exchange-qualified canonical stock identity used in an approved membership or display relation.",
        None,
        "context_only",
        "Must match the corresponding stock code and approved relation row.",
        "It does not by itself authorize a trade.",
    ),
    "index_identity_key": (
        "指数规范标的键",
        "Exchange-qualified canonical index identity used as market context.",
        None,
        "context_only",
        "Must match the corresponding index code.",
        "Indexes are context only and are not tradable by the AI Agent.",
    ),
    "board_identity_key": (
        "板块规范标的键",
        "Canonical board identity used as market or membership context.",
        None,
        "context_only",
        "Must match board code, board type, and approved membership lineage.",
        "Boards are context only and are not tradable by the AI Agent.",
    ),
    "stock_name": (
        "股票名称",
        "Display-safe stock name from the approved N6 relation.",
        None,
        "context_only",
        "Must remain paired with the canonical stock identity.",
        "A name is not an authority identity.",
    ),
    "index_code": (
        "指数代码",
        "Display code of an approved index context identity.",
        None,
        "context_only",
        "Must remain paired with index_identity_key.",
        "A bare index code is not tradable.",
    ),
    "index_name": (
        "指数名称",
        "Display-safe name of an approved index context identity.",
        None,
        "context_only",
        "Must remain paired with index_identity_key.",
        "A display name is not an authority identity.",
    ),
    "board_code": (
        "板块代码",
        "Display code of an approved board context identity.",
        None,
        "context_only",
        "Must remain paired with board_identity_key and board_type.",
        "A board code is not tradable.",
    ),
    "board_name": (
        "板块名称",
        "Display-safe name of an approved board context identity.",
        None,
        "context_only",
        "Must remain paired with board_identity_key.",
        "A board name is not a tradable identity.",
    ),
    "board_type": (
        "板块类型",
        "Approved board namespace such as the reviewed industry-board channel.",
        None,
        "context_only",
        "Only allowlisted board types may enter context.",
        "Concept or region boards must not be silently treated as industry boards.",
    ),
    "display_code": (
        "展示代码",
        "Display-safe code exposed by the approved N6 filter view.",
        None,
        "context_only",
        "Must remain paired with identity_key.",
        "It is presentation data, not trade authority.",
    ),
    "display_name": (
        "展示名称",
        "Display-safe asset name exposed by the approved N6 filter view.",
        None,
        "context_only",
        "Must remain paired with identity_key.",
        "It is presentation data, not trade authority.",
    ),
    "display_title": (
        "展示标题",
        "Frozen display title from the approved filter adapter.",
        None,
        "display_only",
        "Presentation only.",
        "Do not extract a trading signal from display prose.",
    ),
    "display_summary": (
        "展示摘要",
        "Frozen display summary from the approved filter adapter.",
        None,
        "display_only",
        "Presentation only.",
        "Do not extract a trading signal from display prose.",
    ),
    "selected_directions": (
        "筛选方向集合",
        "Directions selected by the approved display/filter policy.",
        None,
        "context_only",
        "Must match the frozen policy lineage.",
        "A selected direction is not a shared trading signal.",
    ),
    "selected_condition_keys": (
        "筛选条件键集合",
        "Condition trace keys selected by the approved display policy.",
        None,
        "context_only",
        "Trace context only.",
        "Condition keys are not execution instructions.",
    ),
    "selected_signal_types": (
        "筛选信号类型集合",
        "Canonical condition signal types selected by the approved filter policy.",
        None,
        "context_only",
        "Must retain asset-kind and policy lineage.",
        "Filter selection cannot fabricate n6_ai_shared_signal_projection.",
    ),
    "asset_kind": (
        "资产类型",
        "Physical N6 channel: stock, index, or board.",
        None,
        "decision",
        "Stock, index, and board remain separate channels.",
        "Index and board are context-only and are not tradable identities.",
    ),
    "direction": (
        "方向",
        "Canonical buy or sell direction of the frozen N6 signal.",
        None,
        "decision",
        "Buy requires a current shared stock buy signal; sell also requires an AI-owned position.",
        "Direction alone is not execution authority.",
    ),
    "level_up_score": (
        "结构上行排序分",
        "N2-frozen structural ranking score for upward structure.",
        "score",
        "context_only",
        "Use only as comparative context within the same frozen lineage.",
        "It is not a buy signal, probability, confidence, or expected return.",
    ),
    "score": (
        "财务综合分",
        "Frozen stock financial composite score passed through by N6.",
        "score",
        "context_only",
        "Requires the source financial-quality contract to be satisfied.",
        "It is not a buy signal or model confidence.",
    ),
    "pe_core": (
        "核心市盈率",
        "Frozen core-profit valuation ratio from the approved display source.",
        "ratio",
        "context_only",
        "Meaningful only when the financial-quality fields permit it.",
        "Negative, null, or extreme values must not be silently normalized.",
    ),
    "industry_code": (
        "行业代码",
        "Frozen industry-board code attached to the stock display row.",
        None,
        "context_only",
        "Requires the approved stock display-basis lineage.",
        "It is context, not a tradable board identity or buy authority.",
    ),
    "industry_name": (
        "行业名称",
        "Frozen industry-board display name attached to the stock row.",
        None,
        "context_only",
        "Requires the approved stock display-basis lineage.",
        "It must not be enriched from an unapproved membership source.",
    ),
    "cash_realization_rate": (
        "现金实现率",
        "Frozen cash-realization percentage from the canonical stock financial metrics.",
        "percent",
        "context_only",
        "Requires passed financial-quality lineage.",
        "It is not cash balance, free cash flow, or a buy signal.",
    ),
    "revenue_yoy_pct": (
        "营业收入同比",
        "Year-over-year percentage change of canonical report revenue.",
        "percent",
        "context_only",
        "Uses the canonical financial snapshot or its approved fallback calculation.",
        "It is not a forward forecast.",
    ),
    "core_profit_yoy_pct": (
        "核心利润同比",
        "Year-over-year percentage change of canonical core profit.",
        "percent",
        "context_only",
        "Uses the canonical financial snapshot or its approved fallback calculation.",
        "It is not total net-profit growth unless the source contract says so.",
    ),
    "report_core_revenue": (
        "报告期核心收入",
        "Canonical revenue value for the frozen report period.",
        "CNY",
        "context_only",
        "Requires the approved report-period financial snapshot.",
        "Do not combine different report periods.",
    ),
    "report_core_profit": (
        "报告期核心利润",
        "Canonical core-profit value for the frozen report period.",
        "CNY",
        "context_only",
        "Requires the approved report-period financial snapshot.",
        "Do not reinterpret it as operating cash flow or total profit.",
    ),
    "core_profit_ttm": (
        "核心利润TTM",
        "Trailing-twelve-month canonical core profit.",
        "CNY",
        "context_only",
        "Requires sufficient approved quarterly financial lineage.",
        "Do not mix it with a single report-period profit.",
    ),
    "core_gt_revenue_yoy": (
        "核心利润增速高于收入增速",
        "Boolean comparison: core-profit YoY exceeds revenue YoY.",
        "boolean",
        "context_only",
        "Both YoY inputs must be available and comparable.",
        "False and NULL are not interchangeable.",
    ),
    "revenue_growth_streak_q": (
        "收入连续增长季度数",
        "Count of consecutive approved quarters with positive revenue growth.",
        "quarters",
        "context_only",
        "Requires contiguous approved quarterly observations.",
        "It is not the magnitude of growth.",
    ),
    "core_growth_streak_q": (
        "核心利润连续增长季度数",
        "Count of consecutive approved quarters with positive core-profit growth.",
        "quarters",
        "context_only",
        "Requires contiguous approved quarterly observations.",
        "It is not the magnitude of growth.",
    ),
    "core_gt_revenue_streak_q": (
        "核心利润增速领先季度数",
        "Count of consecutive quarters where core-profit growth exceeds revenue growth.",
        "quarters",
        "context_only",
        "Requires comparable approved YoY inputs for every quarter.",
        "It is not a forecast horizon.",
    ),
    "forecast_type": (
        "业绩预告类型",
        "Canonical forecast classification from the frozen financial source.",
        None,
        "context_only",
        "Requires an approved forecast source row.",
        "It is not a model-generated recommendation.",
    ),
    "forecast_score": (
        "业绩预告评分",
        "Frozen score derived by the canonical financial forecast policy.",
        "score",
        "context_only",
        "Requires its forecast policy version and quality lineage.",
        "It is not a probability, return estimate, or buy signal.",
    ),
    "prev_up_str": (
        "前序上行周期串",
        "Frozen compact trace of prior upward-period structure.",
        None,
        "context_only",
        "Interpret only with the N2 period encoding contract.",
        "Characters must not be reinterpreted as orders or confidence.",
    ),
    "prev_dn_str": (
        "前序下行周期串",
        "Frozen compact trace of prior downward-period structure.",
        None,
        "context_only",
        "Interpret only with the N2 period encoding contract.",
        "Characters must not be reinterpreted as orders or confidence.",
    ),
    "up_sell_reference_period": (
        "上行卖出参考周期",
        "N2-frozen reference period for upward-structure sell context.",
        None,
        "context_only",
        "Preserve the frozen period label.",
        "It does not itself authorize a sell.",
    ),
    "down_buy_reference_period": (
        "下行买入参考周期",
        "N2-frozen reference period for downward-structure buy context.",
        None,
        "context_only",
        "Preserve the frozen period label.",
        "It does not itself authorize a buy.",
    ),
    "clear_sell_ref_period": (
        "清仓卖出参考周期兼容字段",
        "Legacy alias that must equal up_sell_reference_period.",
        None,
        "audit_only",
        "Equality with up_sell_reference_period is required.",
        "It is not an independent calculation.",
    ),
    "period_trigger_baseline_json": (
        "周期触发基线",
        "N2-frozen Y/Q/M/W/D trigger baseline object.",
        "json",
        "context_only",
        "Must satisfy the reviewed nested-field schema and source lineage.",
        "N6 must not query raw historical K data or recompute the baseline.",
    ),
    "target_price_trace_json": (
        "目标价追踪",
        "Frozen target-price calculation trace from the symmetry policy.",
        "json",
        "context_only",
        "Must retain policy and source-period lineage.",
        "It is evidence, not an execution-price instruction.",
    ),
    "financial_quality_status": (
        "财务质量状态",
        "Quality classification of the frozen canonical stock financial metrics.",
        None,
        "context_only",
        "Only statuses explicitly approved by policy permit financial-field use.",
        "Missing or failed quality must not be treated as passed.",
    ),
    "official_daily_proof": (
        "官方日线证明",
        "Frozen proof that the approved official daily source exists for the stock.",
        None,
        "context_only",
        "Must match the display-basis trade-date lineage.",
        "It is not a live quote or execution proof.",
    ),
    "is_st": (
        "ST风险标记",
        "Frozen boolean indicating ST/risk-name classification.",
        "boolean",
        "context_only",
        "Requires the approved identity/status source.",
        "False and unavailable are not interchangeable.",
    ),
    "stock_status": (
        "股票状态",
        "Frozen stock eligibility/status classification.",
        None,
        "context_only",
        "Must satisfy the policy allowlist before use.",
        "It does not override quote, suspension, or exchange checks.",
    ),
    "total_mv": (
        "总市值",
        "Frozen total market capitalization used by the approved stock filter.",
        "CNY",
        "context_only",
        "Requires the source trade-date and market-cap quality contract.",
        "It is not account exposure or executable liquidity.",
    ),
    "circ_mv": (
        "流通市值",
        "Frozen circulating market capitalization.",
        "CNY",
        "context_only",
        "Requires the source trade-date and market-cap quality contract.",
        "It is not turnover or executable liquidity.",
    ),
    "buy_target_price": (
        "买向目标价",
        "N2-frozen buy-direction reference target price.",
        "CNY/share",
        "context_only",
        "Evidence only; preserve source lineage and quality state.",
        "Not a fill price, quote, guarantee, or order instruction.",
    ),
    "sell_target_price": (
        "卖向目标价",
        "N2-frozen sell-direction reference target price.",
        "CNY/share",
        "context_only",
        "Evidence only; preserve source lineage and quality state.",
        "Not a fill price, quote, guarantee, or order instruction.",
    ),
    "target_price": (
        "投影目标价",
        "Target price copied into a sanitized N6 signal or frozen position fact.",
        "CNY/share",
        "context_only",
        "Must retain its source projection or position episode.",
        "Not the virtual execution price.",
    ),
    "trigger_price": (
        "触发参考价",
        "Price evidence at the trigger boundary.",
        "CNY/share",
        "context_only",
        "Trace evidence only.",
        "Not a fill price and never supplied by the model.",
    ),
    "action_price": (
        "动作确认参考价",
        "Price evidence carried by the N5 action projection.",
        "CNY/share",
        "context_only",
        "Trace evidence only.",
        "Not a fill price; virtual execution requires a fresh passed N3N6Q quote and the model may not override it.",
    ),
    "current_price": (
        "当前参考价",
        "Price value frozen in the source row.",
        "CNY/share",
        "context_only",
        "May be used only when its own source-quality contract permits.",
        "Must not replace a fresh passed N3N6Q quote for execution.",
    ),
    "filled_price": (
        "模拟成交价",
        "Virtual fill price written by the N6 executor from a fresh passed quote.",
        "CNY/share",
        "audit_only",
        "Authoritative only for the referenced simulated trade.",
        "Does not represent a real broker fill.",
    ),
    "expected_return_pct": (
        "投影预期收益率",
        "Frozen projection percentage derived upstream and copied into N6.",
        "percent",
        "context_only",
        "Compare only under the same projection contract.",
        "Not a promised return or realized performance.",
    ),
    "buy_expected_return_pct": (
        "买向预期收益率",
        "N2-frozen buy-direction projected return percentage.",
        "percent",
        "context_only",
        "Context only.",
        "Not a promised or realized return.",
    ),
    "up_secondary_expected_return_pct": (
        "次级上行预期收益率",
        "N2-frozen secondary upward projected return percentage.",
        "percent",
        "context_only",
        "Context only.",
        "Not a promised or realized return.",
    ),
    "action_state": (
        "动作状态",
        "Canonical N5 action projection state.",
        None,
        "decision",
        "Use only with the matching source event and action lineage.",
        "Does not mean that any virtual or real trade occurred.",
    ),
    "action_mark": (
        "动作标记",
        "N5 final action mark: normal, 30m_volume, or 30m_shrink.",
        None,
        "context_only",
        "Valid only after the N5 confirmation contract.",
        "It is not a model strategy label.",
    ),
    "condition_key": (
        "条件追踪键",
        "Condition trace identifier preserved from the approved projection.",
        None,
        "context_only",
        "Trace and audit only.",
        "It is not the runtime signal type or execution authority.",
    ),
    "signal_type": (
        "信号类型",
        "Canonical projected signal type under the N6 contract.",
        None,
        "decision",
        "Must agree with direction, asset kind, date, and shared projection status.",
        "A filter-center row alone cannot fabricate a signal.",
    ),
    "quality_status": (
        "质量状态",
        "Quality classification defined by the owning N6 relation.",
        None,
        "decision",
        "For quotes, only passed, finite, positive, fresh SH/SZ rows are usable; other relations keep their own quality contract.",
        "A passed label from one relation must not be transplanted to another relation.",
    ),
    "price": (
        "行情价格",
        "N3N6Q-derived virtual quote price stored by the N6 quote writer.",
        "CNY/share",
        "decision",
        "Must be finite, positive, passed, fresh, and identity matched.",
        "The model may not submit or override it.",
    ),
    "exchange": (
        "交易所",
        "Exchange component of the canonical stock quote identity.",
        None,
        "decision",
        "Must agree with identity_key and stock_code.",
        "An exchange value may not be guessed from a bare code.",
    ),
    "stock_code": (
        "股票代码",
        "Six-digit stock code carried by the canonical quote identity.",
        None,
        "decision",
        "Must agree with exchange and identity_key.",
        "A bare code is not an authority identity.",
    ),
    "quote_minute": (
        "行情分钟",
        "Minute bucket associated with the frozen N3N6Q quote.",
        "timestamp",
        "decision",
        "Must satisfy the active-session or closing-window freshness policy.",
        "A quote from another minute or trade date must not be reused.",
    ),
    "fetched_at": (
        "行情获取时间",
        "Server-recorded completion time for the N3N6Q quote fetch.",
        "timestamp",
        "decision",
        "Used with quote_minute and quality status for freshness checks.",
        "Fetch time is not exchange event time or trade time.",
    ),
    "available_cash": (
        "可用模拟现金",
        "Server-owned available cash of the AI virtual account.",
        "CNY",
        "decision",
        "Must be re-read transactionally before execution.",
        "A context snapshot cannot reserve or spend cash.",
    ),
    "quantity": (
        "数量",
        "Share quantity of a virtual position or execution fact.",
        "shares",
        "decision",
        "T+1 and 100-share rules remain authoritative.",
        "The model may not submit quantity.",
    ),
    "sellable_quantity": (
        "可卖数量",
        "AI-owned position quantity currently sellable under T+1.",
        "shares",
        "decision",
        "Must be revalidated inside the executor transaction.",
        "Total quantity is not automatically sellable quantity.",
    ),
    "available_quantity": (
        "可用持仓数量",
        "AI-owned position quantity currently available for a virtual sell under T+1.",
        "shares",
        "decision",
        "Must be revalidated inside the executor transaction.",
        "Total or locked quantity must not be treated as available quantity.",
    ),
    "reason_summary": (
        "公开简短理由",
        "Concise auditable reason; hidden reasoning is not stored.",
        None,
        "display_only",
        "Must cite approved frozen evidence.",
        "Must not contain chain-of-thought, prompts, secrets, or private human data.",
    ),
}

ENUMS = {
    "asset_kind": ["stock", "index", "board"],
    "direction": ["buy", "sell"],
    "decision_type": ["buy", "sell", "hold"],
    "principal_type": ["admin", "human_user", "ai_user", "system_reserved"],
    "action_state": ["eligible", "blocked", "executed", "skipped", "expired"],
    "action_mark": ["normal", "30m_volume", "30m_shrink"],
    "run_mode": ["shadow", "autonomous_canary"],
}

PERIOD_FIELD_RE = re.compile(
    r"^period_(grade|transition)_(y|q|m|w|d)$"
)


def boundary_semantics(
    name: str,
    category: str,
    data_type: str,
) -> tuple[str, str, str | None, str, str, str] | None:
    period = PERIOD_FIELD_RE.fullmatch(name)
    if period:
        kind, period_code = period.groups()
        return (
            f"{period_code.upper()}周期{'等级' if kind == 'grade' else '过渡状态'}",
            f"N2-frozen {period_code.upper()}-period {kind} classification.",
            None,
            "context_only",
            "Requires the matching frozen display-basis row.",
            "It is structural context, not a standalone signal.",
        )
    if name.endswith("_id") or name.endswith("_ids_json"):
        return (
            "审计标识符",
            f"Identifier or identifier collection used to reference {name[:-3] or name}.",
            None,
            "audit_only",
            "Must resolve inside the same approved principal and lineage boundary.",
            "An identifier never grants authority or proves semantic equivalence.",
        )
    if name.endswith("_hash"):
        return (
            "不可变哈希",
            f"Integrity or policy hash recorded in {name}.",
            None,
            "audit_only",
            "Must match the named canonical serialization and algorithm contract.",
            "A hash is not a business metric.",
        )
    if name.endswith("_version"):
        return (
            "版本标识",
            f"Version label for the contract or policy named by {name}.",
            None,
            "audit_only",
            "Must be paired with the matching hash when the relation provides one.",
            "Different versions must not be silently combined.",
        )
    if name.endswith("_at") or name.endswith("_time"):
        return (
            "时间戳",
            f"Timestamp recorded for the lifecycle event named by {name}.",
            "timestamp",
            "audit_only",
            "Timezone and lifecycle meaning inherit the relation contract.",
            "Insert time, source event time, quote time, and trade time are not interchangeable.",
        )
    if name.endswith("_date") or name == "trade_date":
        return (
            "日期",
            f"Date associated with the lifecycle or source concept named by {name}.",
            "date",
            "audit_only",
            "Open-trade-date use requires common_trade_calendar validation.",
            "It must not replace for_trade_date unless the contract explicitly says so.",
        )
    if name.endswith("_count"):
        return (
            "计数",
            f"Non-negative count of the items named by {name}.",
            "count",
            "audit_only",
            "Count grain inherits the owning relation.",
            "A count is not a score or probability.",
        )
    if name.endswith("_json") or name in {"raw_json", "raw_payload"}:
        return (
            "冻结JSON审计载荷",
            f"Opaque JSON audit payload stored in {name}.",
            "json",
            "forbidden",
            "Every nested field needs a separate reviewed schema before model use.",
            "Do not expose or infer nested semantics from an opaque payload.",
        )
    if name.endswith("_status") or name == "status":
        return (
            "状态",
            f"Lifecycle or quality state defined by {name} in its owning relation.",
            None,
            "audit_only",
            "Only documented enum values under the same relation are comparable.",
            "A status label does not grant execution authority.",
        )
    if name.endswith("_reason") or name.endswith("_reason_text"):
        return (
            "原因",
            f"Auditable reason associated with {name}.",
            None,
            "audit_only",
            "Must not contain secrets, hidden reasoning, or private human data.",
            "A reason is explanatory text, not an authority decision.",
        )
    if name in {
        "principal_id",
        "principal_type",
        "user_id",
        "owner_user_id",
        "created_by_user_id",
        "created_by_principal_id",
        "ai_user_id",
    }:
        return (
            "主体归属",
            f"N6 authority identity component {name}.",
            None,
            "audit_only",
            "Must be server-resolved and exactly match the authorized actor.",
            "The model or browser may not submit or override authority identity.",
        )
    if category in {"human_projection", "human_private_scope"}:
        return (
            "真人私有字段",
            f"Field {name} belongs to a human-principal private N6 relation.",
            inferred_unit(name, data_type),
            "forbidden",
            "Semantic documentation does not authorize row access.",
            "The AI Agent must never read or infer this human-private value.",
        )
    return None


def canonical_hash(value: Any) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def split_sql_columns(body: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    in_single = False
    index = 0
    while index < len(body):
        char = body[index]
        if char == "'" and (
            index == 0 or body[index - 1] != "\\"
        ):
            if in_single and index + 1 < len(body) and body[index + 1] == "'":
                index += 2
                continue
            in_single = not in_single
        elif not in_single:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                parts.append(body[start:index].strip())
                start = index + 1
        index += 1
    tail = body[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def sql_type(definition: str) -> str:
    match = re.match(
        r"^[a-z_][a-z0-9_]*\s+(.+?)(?=\s+(?:NOT\s+NULL|NULL|DEFAULT|"
        r"PRIMARY\s+KEY|REFERENCES|CHECK|UNIQUE|GENERATED)\b|$)",
        " ".join(definition.split()),
        re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"column_definition_unparsed:{definition[:80]}")
    return match.group(1)


def planned_relations(schema_text: str) -> list[dict[str, Any]]:
    relations: list[dict[str, Any]] = []
    pattern = re.compile(
        r"CREATE TABLE public\.(n6_ai_[a-z0-9_]+)\s*\((.*?)\n\);",
        re.DOTALL,
    )
    for relation_name, body in pattern.findall(schema_text):
        columns: list[dict[str, Any]] = []
        for definition in split_sql_columns(body):
            normalized = " ".join(definition.split())
            if re.match(
                r"^(?:FOREIGN\s+KEY|CHECK|UNIQUE|PRIMARY\s+KEY|CONSTRAINT)\b",
                normalized,
                re.IGNORECASE,
            ):
                continue
            name_match = re.match(r"^([a-z_][a-z0-9_]*)\s+", normalized)
            if not name_match:
                raise ValueError(
                    f"planned_column_name_unparsed:{normalized[:80]}"
                )
            columns.append(
                {
                    "ordinal": len(columns) + 1,
                    "name": name_match.group(1),
                    "data_type": sql_type(normalized),
                    "not_null": bool(
                        re.search(r"\bNOT\s+NULL\b", normalized, re.I)
                    ),
                    "default_expression": (
                        "defined"
                        if re.search(r"\bDEFAULT\b", normalized, re.I)
                        else None
                    ),
                }
            )
        relations.append(
            {
                "relation_name": relation_name,
                "relation_kind": "planned_table",
                "columns": columns,
            }
        )
    expected = {
        "n6_ai_shared_signal_projection",
        "n6_ai_context_snapshot",
        "n6_ai_decision_run",
        "n6_ai_decision",
        "n6_ai_daily_summary",
        "n6_ai_strategy_evaluation",
    }
    if {item["relation_name"] for item in relations} != expected:
        raise ValueError("planned_relation_set_mismatch")
    return relations


def inferred_unit(name: str, data_type: str) -> str | None:
    if name.endswith("_pct") or name.endswith("_rate"):
        return "percent"
    if "quantity" in name:
        return "shares"
    if any(
        token in name
        for token in (
            "price",
            "cash",
            "amount",
            "market_value",
            "total_asset",
            "pnl",
            "cost",
        )
    ):
        return "CNY_or_CNY_per_share_as_defined_by_source"
    if data_type.startswith("date"):
        return "date"
    if "timestamp" in data_type:
        return "timestamp"
    if name.endswith("_count"):
        return "count"
    return None


def lineage_for(relation: str, category: str) -> str:
    if category == "filter_view":
        return (
            f"approved N6 readonly view {relation}; upstream calculation is "
            "owned by the corresponding N2 display-basis source"
        )
    if category == "membership_view":
        return (
            f"approved N6 readonly membership view {relation}; relational "
            "membership context only"
        )
    if category.startswith("human_"):
        return f"N6 human-private relation {relation}; row access forbidden"
    if category == "quote":
        return f"N3N6Q -> N6 quote writer -> {relation}"
    if category == "quote_audit":
        return f"N3N6Q -> N6 quote-writer audit relation {relation}"
    if category == "ai_shared_signal":
        return (
            "approved passed N5_action projection -> sanitized N6 shared "
            f"projection {relation}"
        )
    return f"N6-owned relation {relation}"


def field_record(
    relation: str,
    category: str,
    default_usage: str,
    column: dict[str, Any],
    *,
    schema_state: str,
) -> dict[str, Any]:
    name = column["name"]
    exact = EXACT_SEMANTICS.get(name)
    if exact:
        (
            chinese_name,
            meaning,
            unit,
            usage,
            quality,
            forbidden,
        ) = exact
        semantic_status = "reviewed"
    else:
        boundary = boundary_semantics(
            name, category, column["data_type"]
        )
        if boundary:
            (
                chinese_name,
                meaning,
                unit,
                usage,
                quality,
                forbidden,
            ) = boundary
            semantic_status = "reviewed_boundary_only"
        else:
            chinese_name = name
            meaning = (
                f"Canonical field {name} stored or exposed by {relation}; "
                "exact calculation semantics are not yet promoted into the "
                "reviewed AI knowledge dictionary."
            )
            unit = inferred_unit(name, column["data_type"])
            usage = "forbidden"
            quality = (
                "Unavailable to the Agent until a human-reviewed semantic "
                "rule and source citation are added."
            )
            forbidden = (
                "Do not infer business meaning from the column name or use "
                "it for a decision."
            )
            semantic_status = "needs_human_review"
    if default_usage == "forbidden":
        usage = "forbidden"
    elif default_usage == "context_only" and usage == "decision":
        usage = "context_only"
    elif default_usage == "audit_only":
        usage = "audit_only"
    elif default_usage == "display_only":
        usage = "display_only"
    if category == "quote" and name in {
        "identity_key",
        "current_price",
        "quality_status",
        "quality_reason",
        "quote_minute",
        "fetched_at",
    }:
        usage = "decision"
    if category == "membership_view" and name == "trade_date":
        usage = "context_only"
    if semantic_status == "needs_human_review":
        usage = "forbidden"
    if name.endswith("_json") and semantic_status != "reviewed":
        usage = "forbidden"
        forbidden = (
            "Opaque JSON is not model context until every nested field has "
            "a separate reviewed contract."
        )
    return {
        "canonical_name": name,
        "chinese_name": chinese_name,
        "source_relation": relation,
        "data_type": column["data_type"],
        "not_null": bool(column["not_null"]),
        "default_expression": column.get("default_expression"),
        "unit": unit,
        "enums": ENUMS.get(name, []),
        "null_meaning": (
            "not_applicable_or_source_not_available; never silently zero"
            if not column["not_null"]
            else "not_allowed"
        ),
        "business_meaning": meaning,
        "data_grain": RELATION_GRAIN[category],
        "date_freshness_semantics": (
            EXACT_SEMANTICS["for_trade_date"][4]
            if name == "for_trade_date"
            else "Inherits the relation and frozen-source freshness contract."
        ),
        "owner_layer": (
            "N6_user_readonly_adapter"
            if category in {"filter_view", "membership_view"}
            else "N6_user"
        ),
        "formula_or_passthrough_source": lineage_for(
            relation, category
        ),
        "quality_prerequisites": quality,
        "allowed_consumers": (
            ["N6_AI_investor_research_room_semantic_only"]
            if default_usage == "forbidden"
            else [
                "N6_AI_investor_research_room",
                "N6_AI_context_builder_via_hardened_function",
            ]
        ),
        "ai_usage": usage,
        "forbidden_interpretation": forbidden,
        "lineage": lineage_for(relation, category),
        "schema_state": schema_state,
        "source_commit": SOURCE_COMMIT,
        "dictionary_version": DICTIONARY_VERSION,
        "semantic_status": semantic_status,
    }


def build_dictionary(
    catalog: dict[str, Any], schema_text: str
) -> dict[str, Any]:
    if catalog.get("database") != "ashare_v3":
        raise ValueError("catalog_database_mismatch")
    current = catalog.get("relations")
    if not isinstance(current, list):
        raise ValueError("catalog_relations_invalid")
    current_names = {item.get("relation_name") for item in current}
    expected_current = {
        name
        for name in RELATION_POLICY
        if not name.startswith("n6_ai_")
        or name in {"n6_ai_user"}
    }
    expected_current |= {"n6_strategy"}
    missing = expected_current - current_names
    if missing:
        raise ValueError(
            "catalog_relations_missing:" + ",".join(sorted(missing))
        )
    planned = planned_relations(schema_text)
    relations: list[dict[str, Any]] = []
    for source, schema_state in (
        (current, "active_catalog_054"),
        (planned, "planned_055_not_migrated"),
    ):
        for item in source:
            name = item["relation_name"]
            if name not in RELATION_POLICY:
                continue
            category, default_usage = RELATION_POLICY[name]
            fields = [
                field_record(
                    name,
                    category,
                    default_usage,
                    column,
                    schema_state=schema_state,
                )
                for column in item["columns"]
            ]
            relations.append(
                {
                    "relation_name": name,
                    "relation_kind": item["relation_kind"],
                    "schema_state": schema_state,
                    "category": category,
                    "data_grain": RELATION_GRAIN[category],
                    "default_ai_usage": default_usage,
                    "direct_ai_role_access": False,
                    "field_count": len(fields),
                    "fields": fields,
                }
            )
    proposal = next(
        relation
        for relation in relations
        if relation["relation_name"] == "n6_virtual_trade_proposal"
    )
    proposal_user_id = next(
        field
        for field in proposal["fields"]
        if field["canonical_name"] == "user_id"
    )
    proposal_user_id["not_null"] = False
    proposal_user_id["null_meaning"] = (
        "not_applicable_for_ai_actor; never silently substitute a human user"
    )
    proposal_user_id["schema_state"] = "planned_055_not_migrated"
    for name, data_type in (
        ("actor_ai_user_id", "bigint"),
        ("source_ai_decision_id", "bigint"),
    ):
        column = {
            "name": name,
            "data_type": data_type,
            "not_null": False,
            "default_expression": None,
        }
        proposal["fields"].append(
            field_record(
                "n6_virtual_trade_proposal",
                "ai_own_execution",
                "audit_only",
                column,
                schema_state="planned_055_not_migrated",
            )
        )
    proposal["field_count"] = len(proposal["fields"])
    relations.sort(key=lambda item: item["relation_name"])
    fields = [
        field
        for relation in relations
        for field in relation["fields"]
    ]
    unresolved = [
        f"{field['source_relation']}.{field['canonical_name']}"
        for field in fields
        if field["semantic_status"] == "needs_human_review"
    ]
    approved_fields = [
        field
        for field in fields
        if field["ai_usage"] in {"decision", "context_only", "display_only"}
    ]
    unresolved_approved = [
        f"{field['source_relation']}.{field['canonical_name']}"
        for field in approved_fields
        if field["semantic_status"] == "needs_human_review"
    ]
    source_catalog_snapshot = sorted(
        (
            {
                "relation_name": item["relation_name"],
                "relation_kind": item["relation_kind"],
                "columns": item["columns"],
            }
            for item in current
            if item["relation_name"] in RELATION_POLICY
        ),
        key=lambda item: item["relation_name"],
    )
    catalog_signature = canonical_hash(source_catalog_snapshot)
    payload: dict[str, Any] = {
        "dictionary_version": DICTIONARY_VERSION,
        "layer_role": "N6_user",
        "source_commit": SOURCE_COMMIT,
        "highest_active_migration": HIGHEST_ACTIVE_MIGRATION,
        "planned_migration": PLANNED_MIGRATION,
        "database": "ashare_v3",
        "catalog_signature_sha256": catalog_signature,
        "source_catalog_snapshot": source_catalog_snapshot,
        "status": "inventory_complete_semantic_review_incomplete",
        "production_agent_usable": False,
        "relation_count": len(relations),
        "field_count": len(fields),
        "reviewed_field_count": len(fields) - len(unresolved),
        "unresolved_field_count": len(unresolved),
        "unresolved_fields": unresolved,
        "approved_ai_field_count": len(approved_fields),
        "unresolved_approved_ai_field_count": len(
            unresolved_approved
        ),
        "unresolved_approved_ai_fields": unresolved_approved,
        "approved_ai_field_semantics_complete": not unresolved_approved,
        "allowed_sources": [
            "approved N6 readonly filter and membership views",
            "sanitized n6_ai_shared_signal_projection",
            "AI-own N6 account, cash, proposal, order, trade, position, lot, PnL and quote facts via hardened functions",
            "versioned N6 system and policy documents",
        ],
        "forbidden_sources": [
            "human user sessions and session hashes",
            "human-private monitor and realtime scope rows",
            "human-private account, proposal, order, trade and position rows",
            "user_signal_projection and user_signal_card rows as Agent input",
            "N1-N5 raw or internal relations",
            "common_event_outbox, inbox and checkpoint",
            "raw K data and direct live-market provider access",
            "arbitrary SQL, repository paths, model credentials and hidden reasoning",
        ],
        "hard_semantic_distinctions": {
            "trade_dates": "for_trade_date, source_trade_date and prev_trade_date are not interchangeable",
            "level_up_score": "structural ranking only; not a buy signal",
            "score": "financial composite context; not a buy signal",
            "target_and_return": "frozen projections; not execution promises",
            "price": "trigger/action values are evidence; fills require fresh passed N3N6Q quote",
            "filter_center": "filter matches are analysis context and never authorize a buy",
        },
        "relations": relations,
    }
    payload["dictionary_payload_sha256"] = canonical_hash(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-json", type=Path, required=True)
    parser.add_argument(
        "--schema-sql",
        type=Path,
        default=Path("sql/055_n6_ai_agent_v1_schema.sql"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    catalog = json.loads(args.catalog_json.read_text(encoding="utf-8"))
    schema_text = args.schema_sql.read_text(encoding="utf-8")
    payload = build_dictionary(catalog, schema_text)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
