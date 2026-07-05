# B Track V1 Chinese Localization Contract

Gate: B_TRACK_V1_CHINESE_LOCALIZATION_CONTRACT_GATE

Result: CONTRACT_PASS

Layer role: N6_user

Date: 2026-06-07

## 1. Scope

This contract defines the B Track V1 Chinese localization boundary and dry-run
replacement plan.

This gate is documentation only:

```text
No UI implementation
No API field rename
No database field rename
No action_state / event_type enum change
No database write
No outbox consume/update
No worker startup
No proposal/order/trade/position/PnL/real trade path
```

Localized surfaces:

```text
/n6/app
/n6/app/account
/n6/app/watchlist
/n6/app/signals
/n6/app/status-monitor
/n6/app/ai-users
/n6/app/proposals
/n6/app/portfolio
/n6/app/pnl
/n6/app/leaderboard
```

## 2. Product Language Rules

User-facing B Track UI uses Chinese first.

System runtime events use Chinese + canonical English event names:

```text
市场动作确认成立 (ActionExecuted)
市场动作未确认 (ActionBlocked)
触发成立 (TriggerMatched)
等待行情证据 (TriggerPendingMarketData)
状态变化 (TriggerStateChanged)
动作待确认 (ActionEligible)
动作已跳过 (ActionSkipped)
```

Developer and audit fields remain English and should appear only in detail,
evidence, source, or audit areas:

```text
identity_key
condition_key
original_condition_key
projection_run_id
source_run_id
event_id
dedup_key
partition_key
quality_status
asset_kind
action_state
action_mark
blocked_reason
principal_id
principal_type
```

## 3. Navigation Dictionary

| Current | Chinese |
|---|---|
| Dashboard | 首页 |
| Account | 账户 |
| Watchlist | 关注池 |
| Signals | 信号 |
| Status Monitor | 状态监控 |
| Proposals | 方案 |
| Portfolio | 组合 |
| PnL | 收益 |
| AI Users | AI助手 |
| Leaderboard | 排行榜 |
| Logout | 退出登录 |

## 4. Page Title Dictionary

| Route | Chinese title |
|---|---|
| `/n6/app` | B轨首页 |
| `/n6/app/account` | 我的账户 |
| `/n6/app/watchlist` | 关注池 |
| `/n6/app/signals` | 信号中心 |
| `/n6/app/status-monitor` | 状态监控 |
| `/n6/app/ai-users` | AI助手 |
| `/n6/app/proposals` | 方案 |
| `/n6/app/portfolio` | 组合 |
| `/n6/app/pnl` | 收益 |
| `/n6/app/leaderboard` | 排行榜 |

## 5. Module Dictionaries

Dashboard:

| Current | Chinese |
|---|---|
| B Track Dashboard | B轨首页 |
| trade_date | 交易日 |
| latest_projection_run | 最新投影批次 |
| blocked_reason | 未确认原因 |
| Watchlist | 关注池 |
| AI Users | AI助手 |
| Future Modules Locked | 未来功能 |

Signals:

| Current | Chinese |
|---|---|
| B Track Signals | 信号中心 |
| trade_date | 交易日 |
| asset_kind | 标的类型 |
| name / code | 名称 / 代码 |
| identity_key | identity_key |
| direction | 方向 |
| condition trace | 条件来源 |
| action_state | 动作状态 |
| action_mark | 动作标记 |
| blocked_reason | 未确认原因 |
| tags | 标签 |
| quality | 质量 |
| runs | 运行批次 |

Watchlist:

| Current | Chinese |
|---|---|
| B Track Watchlist | 关注池 |
| Action | 市场动作 |
| condition source | 条件来源 |
| recent signal | 最近信号 |
| No scoped watchlist items. | 当前没有关注中的标的。 |

Account:

| Current | Chinese |
|---|---|
| account_name | 账户名称 |
| base_currency | 币种 |
| initial_cash | 初始资金 |
| available_cash | 可展示现金 |
| frozen_cash | 冻结金额 |
| total_cash | 总现金 |
| status | 状态 |
| quality_status | 质量状态 |

Status Monitor:

| Current | Chinese |
|---|---|
| B Track Status Monitor | 状态监控 |
| active | 有效 |
| pending_market_data | 等待行情证据 |
| inactive | 已失效 |
| current_status | 当前状态 |
| N4 event | N4 触发事件 |
| N5 relationship | N5 动作关系 |
| No scoped status items. | 当前没有状态监控记录。 |

AI Users:

| Current | Chinese |
|---|---|
| B Track AI Users | AI助手 |
| status | 状态 |
| mode | 模式 |
| source | 来源 |
| generated_signal_enabled | 生成信号 |
| auto_trade_enabled | 自动交易 |
| order_enabled | 下单能力 |
| real_trade_enabled | 真实交易 |
| can_generate_signal | 可生成信号 |
| can_trade | 可交易 |

Locked future modules:

| Current | Chinese |
|---|---|
| Proposals | 方案 |
| Portfolio | 组合 |
| PnL | 收益 |
| Leaderboard | 排行榜 |
| Future Automation | 自动交易 |
| This page is a read-only B-track placeholder. Mutating flows require separate gates. | 该入口为未来功能预留，当前不会生成方案、订单、交易或持仓变化。 |

## 6. Runtime Value Dictionaries

Event names:

| Internal value | Display |
|---|---|
| ActionExecuted | 市场动作确认成立 (ActionExecuted) |
| ActionBlocked | 市场动作未确认 (ActionBlocked) |
| TriggerMatched | 触发成立 (TriggerMatched) |
| TriggerPendingMarketData | 等待行情证据 (TriggerPendingMarketData) |
| TriggerStateChanged | 状态变化 (TriggerStateChanged) |
| ActionEligible | 动作待确认 (ActionEligible) |
| ActionSkipped | 动作已跳过 (ActionSkipped) |

State values:

| Internal value | Display |
|---|---|
| executed | 已确认 |
| blocked | 未确认 |
| eligible | 待确认 |
| skipped | 已跳过 |
| expired | 已过期 |
| active | 有效 |
| pending_market_data | 等待行情证据 |
| inactive | 已失效 |

Direction:

| Internal value | Display |
|---|---|
| buy | 买向观察 |
| sell | 卖向观察 |

Blocked reason:

| Internal value | Display |
|---|---|
| price_confirmation_failed | 价格确认未通过 |
| amount_confirmation_failed | 成交额确认未通过 |
| metric_missing | 指标缺失 |
| unknown | 未知原因 |

Asset kind:

| Internal value | Display |
|---|---|
| stock | 个股 |
| index | 指数 |
| board | 板块 |

## 7. Safety Wording

Global safety banner:

```text
只读模式 · 不下单 · 不更新持仓 · 不构成投资建议
```

Evidence/detail disclaimer:

```text
本页仅展示已审核的系统投影和证据链，不代表交易建议
```

Future module disclaimer:

```text
该入口为未来功能预留，当前不会生成方案、订单、交易或持仓变化
```

## 8. Error And Empty States

Empty states:

| Surface | Copy |
|---|---|
| Signals | 当前没有可展示的信号。 |
| Watchlist | 当前没有关注中的标的。 |
| Account | 当前账户信息尚未准备完成。 |
| Status Monitor | 当前没有状态监控记录。 |
| AI Users | 当前没有启用的 AI观察员。 |
| Locked Future Modules | 该功能仍在规划中，当前仅保留入口。 |

Errors:

| Error | Copy |
|---|---|
| unauthorized | 登录已失效，请重新登录。 |
| principal_scope_unavailable | 当前账号尚未开通 B轨访问范围。 |
| forbidden | 当前账号无权访问该页面。 |
| data_not_ready | 数据尚未准备完成。 |
| source_unavailable | 来源数据暂不可用。 |
| api_error | 页面加载失败，请稍后重试。 |

## 9. Forbidden Wording

These phrases must not appear as B Track user-facing UI copy:

```text
建议买入
建议卖出
买入机会
卖出提醒
一键下单
已买入
已卖出
已成交
实盘账户
可用下单资金
真实收益
稳赚
高胜率
低风险
高收益
```

Scan result for current B Track source:

```text
src/ashare_v3/web/n6_app_v1.py: APP_DISCLAIMER contains 非真实收益
```

Although the current phrase is negative, it contains the forbidden substring
`真实收益`. It must be replaced in P0 with:

```text
非实际业绩
```

## 10. Protected API/DB/Internal Boundary

Must not change:

```text
API JSON field names
database table names
database column names
action_state enum values
event_type enum values
source_run_id / projection_run_id values
identity_key format
condition_key / original_condition_key values
principal_id / principal_type values
GET-only route model
principal scoped read model
readonly source allowlist
```

## 11. Affected Files For Implementation

Expected implementation files:

```text
src/ashare_v3/web/n6_app_v1.py
src/ashare_v3/web/templates/n6_app_shell.html
tests/test_n6_user_app.py
```

Contract artifacts:

```text
docs/B_TRACK_V1_CHINESE_LOCALIZATION_CONTRACT.md
docs/B_TRACK_V1_CHINESE_LOCALIZATION_CONTRACT.json
docs/B_TRACK_V1_CHINESE_LOCALIZATION_DRY_RUN.md
docs/B_TRACK_V1_CHINESE_LOCALIZATION_DRY_RUN.json
```

## 12. Priority

P0:

```text
navigation
page titles
safety banner
event bilingual display names
state / direction / blocked_reason labels
empty states
forbidden phrase 非真实收益 -> 非实际业绩
```

P1:

```text
Dashboard module labels
Signals table headers
Watchlist table headers
Status Monitor labels
AI assistant labels
Locked Future Modules copy
```

P2:

```text
Evidence/detail section polish
Data Boundary labels
Allowed/Forbidden source section labels
test assertion localization cleanup
```

## 13. Next Gate

Allowed next gate:

```text
B_TRACK_V1_CHINESE_LOCALIZATION_IMPLEMENTATION_GATE
```
