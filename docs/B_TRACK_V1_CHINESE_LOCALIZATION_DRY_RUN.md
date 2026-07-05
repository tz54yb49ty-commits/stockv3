# B Track V1 Chinese Localization Dry Run

Gate: B_TRACK_V1_CHINESE_LOCALIZATION_CONTRACT_GATE

Result: CONTRACT_PASS

Layer role: N6_user

Date: 2026-06-07

## 1. Dry-Run Summary

This dry-run previews B Track V1 UI wording replacements. It does not change
code, APIs, database fields, internal enums, or data.

Primary implementation targets:

```text
src/ashare_v3/web/n6_app_v1.py
src/ashare_v3/web/templates/n6_app_shell.html
tests/test_n6_user_app.py
```

## 2. P0 Replacement Plan

| File | Current | Replacement | Notes |
|---|---|---|---|
| `n6_app_v1.py` | `APP_PAGE_LABELS` English values | Chinese page titles | Keep route keys unchanged |
| `n6_app_v1.py` | `app_nav_context` labels | Chinese nav labels | Keep nav keys and hrefs unchanged |
| `n6_app_v1.py` | `APP_SAFETY_LABELS` English chips | `只读模式 · 不下单 · 不更新持仓 · 不构成投资建议` | Can be one banner label or split Chinese chips |
| `n6_app_v1.py` | `APP_DISCLAIMER = ["非真实收益", ...]` | `["非实际业绩", "非投资建议", "不代表未来结果"]` | Removes forbidden substring `真实收益` |
| `n6_app_v1.py` | `wording.ActionExecuted` English explanation | `市场动作确认成立 (ActionExecuted)` | Internal event key unchanged |
| `n6_app_v1.py` | `wording.ActionBlocked` English explanation | `市场动作未确认 (ActionBlocked)` | Internal event key unchanged |
| `n6_app_shell.html` | `Logout` | `退出登录` | Button behavior unchanged |
| `n6_app_shell.html` | `GET ONLY` / `principal scoped` | `GET-only` / `按账号范围展示` | GET-only can remain mixed technical label |
| `n6_app_shell.html` | empty state English strings | Chinese empty states | User-facing only |

## 3. P1 Replacement Plan

| Surface | Current | Replacement |
|---|---|---|
| Dashboard title | `B Track Dashboard` | `B轨首页` |
| Dashboard metric | `trade_date` | `交易日` |
| Dashboard metric | `latest_projection_run` | `最新投影批次` |
| Dashboard module | `blocked_reason` | `未确认原因` |
| Dashboard module | `Future Modules Locked` | `未来功能` |
| Watchlist title | `B Track Watchlist` | `关注池` |
| Watchlist table | `asset_kind` | `标的类型` |
| Watchlist table | `Action` | `市场动作` |
| Watchlist table | `condition source` | `条件来源` |
| Watchlist table | `recent signal` | `最近信号` |
| Signals table | `condition trace` | `条件来源` |
| Signals table | `action_state` | `动作状态` |
| Signals table | `action_mark` | `动作标记` |
| Signals table | `blocked_reason` | `未确认原因` |
| Status Monitor title | `B Track Status Monitor` | `状态监控` |
| Status Monitor metric | `active` | `有效` |
| Status Monitor metric | `pending_market_data` | `等待行情证据` |
| Status Monitor metric | `inactive` | `已失效` |
| AI Users title | `B Track AI Users` | `AI助手` |
| AI Users module | `generated_signal_enabled` | `生成信号` |
| AI Users module | `auto_trade_enabled` | `自动交易` |

## 4. P2 Replacement Plan

| Surface | Current | Replacement |
|---|---|---|
| Data Boundary | `Data Boundary` | `数据边界` |
| Source policy | `Allowed sources` | `允许来源` |
| Source policy | `Forbidden sources` | `禁止来源` |
| Detail/evidence fields | English field names | Keep English, move/label as detail evidence fields |
| Locked placeholder | `This page is a read-only B-track placeholder...` | `该入口为未来功能预留，当前不会生成方案、订单、交易或持仓变化。` |

## 5. Runtime Display Value Plan

Display mappings must be applied at render/display-label level only:

```text
event_type: keep raw API value, display bilingual label
action_state: keep raw API value, display Chinese label
direction: keep raw API value, display Chinese label
blocked_reason: keep raw API value, display Chinese label
asset_kind: keep raw API value, display Chinese label
```

Example dry-run row:

```text
API value:
event_type=ActionBlocked
action_state=blocked
direction=sell
blocked_reason=price_confirmation_failed
asset_kind=stock

Display:
市场动作未确认 (ActionBlocked)
未确认
卖向观察
价格确认未通过
个股
```

## 6. Current Scan Evidence

English user-facing terms currently present in B Track source include:

```text
Dashboard
Account
Watchlist
Signals
Status Monitor
Proposals
Portfolio
PnL
AI Users
Leaderboard
Logout
B Track Dashboard
B Track Watchlist
B Track Status Monitor
B Track AI Users
Future Modules Locked
No scoped watchlist items.
No scoped signals.
No scoped status items.
Data Boundary
Allowed sources
Forbidden sources
READ ONLY
NO ORDER
NO TRADE
NO POSITION UPDATE
NO REAL TRADE
NOT INVESTMENT ADVICE
```

Forbidden wording scan:

```text
Finding:
src/ashare_v3/web/n6_app_v1.py line 27 contains 非真实收益

Disposition:
P0 replace with 非实际业绩.
```

## 7. Route Boundary

Route scan remains:

```text
GET /api/n6/app/v1/me
GET /api/n6/app/v1/account
GET /api/n6/app/v1/dashboard
GET /api/n6/app/v1/watchlist
GET /api/n6/app/v1/signals
GET /api/n6/app/v1/signals/{user_signal_projection_id}
GET /api/n6/app/v1/status-monitor
GET /api/n6/app/v1/proposals
GET /api/n6/app/v1/portfolio
GET /api/n6/app/v1/pnl
GET /api/n6/app/v1/ai-users
GET /api/n6/app/v1/leaderboard
GET /n6/app
GET /n6/app/{page_key}
```

No non-GET B Track page/API route is required for localization.

## 8. Implementation Gate Recommendation

Allowed:

```text
B_TRACK_V1_CHINESE_LOCALIZATION_IMPLEMENTATION_GATE
```

Implementation gate must verify:

```text
JSON parse
template render
test_n6_user_app.py
compileall
UI wording scan
forbidden wording scan
GET-only route scan
git diff --check
```
