# N6 UI v1 Admin Console Freeze

Status: FREEZE_PASS

Layer role: N6_user

Date: 2026-06-05

Source basis:

```text
docs/N6_TRACK_SEPARATION_RESCUE_PLAN.md
docs/N6_TRACK_SEPARATION_RESCUE_PLAN.json
N6_UI_v1 admin virtual account readonly adapter POST_REVIEW_PASS
```

This freeze artifact locks `N6_UI_v1` as Track A administrator read-only
console. It is not the future multi-user front office. This gate only updates
UI naming, navigation wording, tests, and freeze documentation. It does not
write database rows, execute runners, consume or update outbox rows, start
workers, create user-facing features, create watchlists, create strategies,
create AI users, accept proposals, create virtual orders/trades/positions/PnL,
generate leaderboards, modify B-track schema, modify N1-N5 facts, deliver
notifications, push to voice/mobile, run sim, or place real trades.

## 1. Frozen Product Identity

Canonical product identity:

```text
N6_UI_v1 = N6_UI_v1_ADMIN_CONSOLE
```

Meaning:

```text
administrator read-only console
runtime action-message dashboard
system audit surface
not a multi-user front office
not a user portfolio product
not an AI/strategy product
```

Allowed Track A pages:

```text
/n6/action-events
/n6/admin/account
/n6/admin/users
```

Allowed Track A API namespace:

```text
/api/n6/ui/v1/...
```

The `/api/n6/ui/v1/...` namespace is frozen as an admin-console namespace and
must not be reused as the future B-track user-app API namespace.

## 2. Navigation Freeze

Top navigation must show:

```text
动作消息
系统账户状态
用户管理
退出
```

Top navigation must not show:

```text
监控筛选
持仓
手机播报
```

The route `/n6/admin/account` is retained for compatibility, but the page and
navigation label must be `系统账户状态`, not `账户`.

## 3. System Account Status Page

Route:

```text
/n6/admin/account
```

Page title:

```text
系统账户状态
```

Required explanatory copy:

```text
本页仅用于管理员审计 admin virtual account 初始化状态，不是多用户前台账户页面。
```

Required safety banner:

```text
READ ONLY
NO ORDER
NO TRADE
NO POSITION UPDATE
NO REAL TRADE
```

Allowed data display:

```text
admin virtual account seed status
current cash snapshot
recent cash ledger rows
quality_status
seed_run_id
```

This display is administrator audit evidence only. It does not mean regular
users have a completed account page, portfolio page, proposal workflow, virtual
trading workflow, or per-principal front office.

## 4. Track B Boundary

Canonical B-track identity:

```text
N6_MULTI_USER_AND_AI_APP
```

Required future B-track route namespace:

```text
/n6/app/...
```

Required future B-track API namespace:

```text
/api/n6/app/v1/...
```

The following must only enter Track B gates, not Track A `N6_UI_v1` expansion:

```text
regular user homepage
watchlist
strategy
AI user
proposal review / accept
virtual order operation
virtual trade operation
virtual position page
virtual PnL page
leaderboard
strategy marketplace
```

If B-track needs to reuse a Track A display pattern or component, it must open
a dedicated shared adapter gate first.

## 5. Current A-Track Completed Scope

Frozen completed A-track scope:

```text
admin login/session for current N6 web app
/n6/action-events read-only action-message dashboard
/n6/admin/account system account status audit page
/n6/admin/users administrator user-management utility
ActionBlocked display wording
ActionExecuted display wording
Notification Preview display-only model
Audit Panel / artifact / rollback links
Shared Status Label
admin virtual account seed status display
```

The existing administrator user-management add/delete function remains:

```text
admin-console legacy/admin utility
```

It is not the B-track canonical user lifecycle.

## 6. Frozen Forbidden Scope

Track A must not add:

```text
multi-user homepage
user watchlist
user strategy
AI user
proposal accept
virtual order operation
virtual trade operation
position user page
PnL user page
leaderboard
delivery execution
push
voice
mobile
sim execution
real trade
```

Forbidden wording in Track A user-visible pages:

```text
已下单
已成交
真实交易
投资建议
```

## 7. Validation Evidence

Required validation commands:

```text
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_user_app.py' -k test_admin_account_page_displays_virtual_account_and_hidden_modules_stay_hidden
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_user_app.py'
python3 -m compileall scripts src tests
python3 -m json.tool docs/N6_UI_V1_ADMIN_CONSOLE_FREEZE.json
git diff --check
```

Static checks must confirm:

```text
系统账户状态 is present
<h1>账户</h1> is absent
>账户</a> is absent
监控筛选 / 持仓 / 手机播报 are absent from active A-track navigation
已下单 / 已成交 / 真实交易 / 投资建议 are absent from A-track production templates
```

## 8. Next Allowed Gates

Allowed next gates:

```text
runtime_control N6_UI_v1 admin console freeze post-review registration
N6_MULTI_USER_APP_SHELL_SPEC_GATE for B-track design only
N6_SHARED_COMPONENT_ADAPTER_GATE before any shared UI reuse
```

This freeze does not authorize implementation of B-track app features,
migration, execution, database writes, worker startup, outbox consumption,
delivery, push, voice, mobile, sim, virtual operation execution, PnL valuation,
leaderboard generation, or real trade.
