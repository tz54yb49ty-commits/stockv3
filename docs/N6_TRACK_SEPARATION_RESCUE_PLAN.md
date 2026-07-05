# N6 Track Separation Rescue Plan

Result: `RESCUE_PLAN_PASS`

Layer role: `runtime_control`

Generated at: `2026-06-05T14:30:40+08:00`

This artifact separates the current N6 admin console track from the future
multi-user and AI app track. It is a documentation rescue plan only. It does
not change code, write database rows, execute runners, consume or update outbox
rows, start workers, deliver notifications, push to voice or mobile, run sim,
create positions, create virtual orders/trades/PnL, or place real trades.

## 1. Rescue Goal

The immediate goal is to stop treating `N6_UI_v1` as both an administrator
console and the future user-facing multi-user app. The two tracks must have
separate product names, route prefixes, API prefixes, documents, and gates.

Canonical track names:

```text
Track A = N6_UI_v1_ADMIN_CONSOLE
Track B = N6_MULTI_USER_AND_AI_APP
```

## 2. Track A: N6_UI_v1_ADMIN_CONSOLE

Positioning:

```text
administrator read-only console
runtime action-message dashboard
system audit surface
not a multi-user front office
not a user portfolio product
not an AI/strategy product
```

Allowed purpose:

```text
view N4/N5/N6 action messages
view ActionBlocked / ActionExecuted
view N6 shadow projection / queue
view system audit status
view admin virtual account seed status only as system account status
view artifact and rollback links
```

Allowed pages:

```text
/n6/action-events
/n6/admin/account
/n6/admin/users
```

Required page naming:

```text
/n6/admin/account page name = 系统账户状态
```

Required A-track labels:

```text
管理员审计用途
不是多用户前台
只读
不下单
不交易
不更新持仓
不真实交易
```

Allowed APIs remain A-track admin-console APIs only:

```text
/api/n6/ui/v1/...
```

The `/api/n6/ui/v1/...` namespace must not be reused as the B-track user app
API namespace.

Track A frozen scope:

```text
Dashboard
Signal List
Signal Detail
ActionBlocked Card
ActionExecuted Card
Notification Preview
Audit Panel
Shared Status Label
Admin system account status display
Admin user-management utility
```

Track A forbidden scope:

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
mobile
voice
push
delivery execution
sim execution
real trade
```

## 3. Track B: N6_MULTI_USER_AND_AI_APP

Positioning:

```text
true user-facing N6 app
human user / AI user product
principal-isolated virtual accounts
watchlist and strategy workflow
proposal and virtual operation workflow
AI decision / evaluation / leaderboard workflow
```

Required route namespace:

```text
/n6/app/...
```

Required API namespace:

```text
/api/n6/app/v1/...
```

Track B target scope:

```text
human user
AI user
each principal owns an independent virtual account
watchlist
strategy
proposal
virtual order
virtual trade
virtual position
virtual PnL
AI decision
AI evaluation
leaderboard
```

Track B implementation boundary:

```text
do not reuse /api/n6/ui/v1 as user app API
do not directly modify N6_UI_v1 old pages
do not silently add B-track writes into A-track components
do not treat admin virtual account display as user portfolio completion
do not treat schema foundation as operation readiness
```

If Track B needs visual pieces from Track A, it must open a separate shared
component adapter gate before reuse.

## 4. Current Mixed Items

The current risk is not a database or runner failure. It is a product and
governance naming failure: some admin-console surfaces can be misread as
multi-user front-office readiness.

Current mixed or easy-to-misread items:

| Item | Current risk | Rescue decision |
|---|---|---|
| `/n6/admin/account` | May be mistaken for user portfolio or virtual-account product | Keep route, rename page to `系统账户状态` |
| Admin virtual account display | May be mistaken for per-user account rollout | Label as system/admin audit status only |
| Admin user management | May be mistaken for B-track lifecycle | Keep as administrator tool only |
| Proposal eligibility display | May be mistaken for proposal generation | Keep display-only; no proposal row or accept action |
| Virtual order/trade schema | May be mistaken for operation readiness | Keep schema-foundation-only until operation gates |
| Existing `/api/n6/ui/v1/...` | May be extended into user app API | Freeze as A-track API only |
| Notification preview | May be mistaken for delivery/push | Keep preview/queued-only; no provider delivery |
| Hidden monitor/filter/position/mobile features | May be reopened inside A-track | Keep hidden until independent gates |

## 5. Must-Fix Items

Required correction actions:

1. Rename the A-track account page display title from `账户` to `系统账户状态`.
2. Add visible copy or metadata that marks the page as `管理员审计用途，不是多用户前台`.
3. Keep these A-track entries hidden or disabled:
   - 监控筛选
   - 持仓
   - 手机播报
4. Stop adding these modules to `N6_UI_v1`:
   - watchlist
   - strategy
   - AI user
   - proposal
   - leaderboard
   - virtual order/trade operation
   - position/PnL user pages
5. Open B-track user app work under a new gate:
   - `N6_MULTI_USER_APP_SHELL_SPEC_GATE`
6. Reserve B-track routes and APIs:
   - `/n6/app/...`
   - `/api/n6/app/v1/...`
7. Require a shared component adapter gate before B-track reuses A-track UI
   components or data models.

## 6. Gate Separation Rules

A-track gates may modify only A-track admin-console artifacts unless explicitly
approved otherwise:

```text
N6_UI_v1_ADMIN_CONSOLE
/n6/action-events
/n6/admin/account
/n6/admin/users
/api/n6/ui/v1/...
```

B-track gates must use independent route/API namespaces:

```text
N6_MULTI_USER_AND_AI_APP
/n6/app/...
/api/n6/app/v1/...
```

Shared reuse requires:

```text
N6_SHARED_COMPONENT_ADAPTER_GATE
```

No gate may silently promote an A-track admin page into a B-track user-facing
page.

## 7. Forbidden Scope

This rescue plan does not authorize:

```text
code changes
database writes
runner execute
outbox consumption or update
worker startup
delivery
push
voice
mobile
sim
position mutation
virtual order/trade execution
PnL valuation
leaderboard generation
real trade
```

## 8. Next Recommended Gate

Recommended next gate:

```text
N6_MULTI_USER_APP_SHELL_SPEC_GATE
```

Purpose:

```text
define B-track /n6/app shell
define /api/n6/app/v1 API ownership
define app navigation without touching N6_UI_v1
define principal/session boundary
define placeholder pages for watchlist, strategy, proposal, virtual account,
virtual order/trade/position/PnL, AI decision/evaluation, leaderboard
```

This next gate must remain design/spec only unless separately authorized.
