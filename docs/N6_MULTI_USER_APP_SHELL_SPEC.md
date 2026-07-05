# N6 Multi User App Shell Spec

Status: SPEC_PASS

Layer role: N6_user

Date: 2026-06-05

This gate freezes the Track B `N6_MULTI_USER_AND_AI_APP` app shell
specification. It is a documentation artifact only. It does not modify
`N6_UI_v1`, does not reuse `/api/n6/ui/v1` as a user-app API, does not write
database rows, does not execute runners, does not consume or update outbox
rows, does not start workers, and does not perform delivery, push, voice,
mobile, sim, position, or real trade side effects.

## 1. Basis

Authoritative inputs:

```text
docs/N6_UI_V1_ADMIN_CONSOLE_FREEZE.md
docs/N6_A_B_TRACK_BOUNDARY_CLARIFICATION.md
docs/N6_MULTI_USER_AND_AI_ARCHITECTURE_v1.md
docs/N6_PHASE3_ORDER_PROPOSAL_SPEC.md
```

Current boundary:

```text
Track A = N6_UI_v1_ADMIN_CONSOLE
Track B = N6_MULTI_USER_AND_AI_APP
```

Track A is frozen as administrator read-only console. Track B is the future
multi-user front office and must use independent page and API namespaces.

## 2. Product Identity

Canonical Track B identity:

```text
N6_MULTI_USER_AND_AI_APP
```

Canonical page namespace:

```text
/n6/app/...
```

Canonical API namespace:

```text
/api/n6/app/v1/...
```

Track B must not use the Track A admin-console API namespace:

```text
/api/n6/ui/v1/...
```

## 3. App Shell Goal

The first Track B app shell is a user-front-office frame. It defines navigation,
page slots, API boundaries, and permission isolation for future multi-user and
AI-user workflows.

The shell does not create business objects. In this spec gate it must not:

```text
generate proposal rows
generate virtual order rows
generate virtual trade rows
update virtual position rows
update virtual pnl rows
create AI decision / evaluation rows
materialize leaderboard rows
consume or update N4/N5 outbox
trigger delivery / push / voice / mobile
enter sim / position / real trade
```

## 4. Routes

All Track B pages must live under `/n6/app`.

| Route | Page | First purpose | Status |
|---|---|---|---|
| `/n6/app` | App Home | Redirect or render user front-office shell landing | planned |
| `/n6/app/dashboard` | Dashboard | Principal-scoped overview of account, signals, proposals, portfolio, PnL | planned |
| `/n6/app/account` | Account | Principal-scoped virtual account summary | planned |
| `/n6/app/watchlist` | Watchlist | Principal-owned watchlist frame | planned |
| `/n6/app/signals` | Signals | Principal-scoped signal list from approved N6 projection | planned |
| `/n6/app/proposals` | Proposals | Proposal list and review frame, display only until later gates | planned |
| `/n6/app/portfolio` | Portfolio | Principal-scoped virtual portfolio display | planned |
| `/n6/app/pnl` | PnL | Principal-scoped virtual PnL display | planned |
| `/n6/app/ai-users` | AI Users | AI user profile and policy frame | planned |
| `/n6/app/leaderboard` | Leaderboard | Approved virtual performance display frame | planned |

Route implementation is out of scope for this gate. The table above is a
contract for future implementation gates, not evidence that the routes already
exist.

## 5. API Prefix

All Track B user-front-office APIs must live under `/api/n6/app/v1`.

| API | Purpose | Allowed read/write posture in first app shell | Status |
|---|---|---|---|
| `GET /api/n6/app/v1/me` | Current principal/session summary | read-only | planned |
| `GET /api/n6/app/v1/account` | Current principal virtual account summary | read-only | planned |
| `GET /api/n6/app/v1/watchlist` | Current principal watchlists | read-only first; write gates later | planned |
| `GET /api/n6/app/v1/signals` | Current principal signals | read-only | planned |
| `GET /api/n6/app/v1/proposals` | Current principal proposals | read-only first; review/accept gates later | planned |
| `GET /api/n6/app/v1/portfolio` | Current principal portfolio | read-only | planned |
| `GET /api/n6/app/v1/pnl` | Current principal virtual PnL | read-only | planned |
| `GET /api/n6/app/v1/ai-users` | Current principal AI users | read-only first; AI gates later | planned |
| `GET /api/n6/app/v1/leaderboard` | Approved virtual leaderboard | read-only | planned |

Future non-GET APIs must be introduced by separate contract, preflight,
rollback, and execute gates. This shell spec does not authorize write routes.

## 6. Permission Model

First supported user:

```text
admin as first user
```

Future principal types:

```text
human_user
ai_user
admin
system
```

Access rules:

| Rule | Requirement |
|---|---|
| Principal scope | Each principal can only view its own virtual account, watchlist, proposals, portfolio, and PnL. |
| Admin first user | Admin may use the first Track B shell while multi-user lifecycle is still gated. |
| Admin audit | Admin may access system audit through explicit audit surfaces, but the user front office must not silently mix Track A admin console pages. |
| AI user | AI user pages are frames only until AI decision/evaluation gates pass. |
| System principal | System principal is not a normal user and must not receive a default front-office account page without a separate gate. |
| Principal ownership | Account, watchlist, strategy, proposal, portfolio, and PnL reads must be constrained by `principal_id` and `principal_type`. |

## 7. Page Boundaries

### Dashboard

The dashboard is the front-office overview for the current principal. It may
show principal-scoped summaries, but it must not execute proposal, order,
trade, position, PnL, delivery, AI, or leaderboard materialization.

### Account

The account page displays the current principal's virtual account and cash
summary. It is not a broker account page and must not show real-account,
broker-session, real-funds, or real-position semantics.

### Watchlist

The watchlist page is a future principal-owned watchlist frame. Creation,
update, deletion, sharing, or marketplace integration requires later gates.

### Signals

The signals page reads approved N6 user projection / signal card data through
Track B APIs. It must not directly consume N5 outbox and must not scan N4/N5
raw facts as a substitute for reviewed projections or artifacts.

### Proposals

The proposals page may display proposal candidates after a proposal schema or
runner gate exists. A proposal is a candidate intent, not an order. This shell
does not generate proposals and does not accept proposals.

### Portfolio

The portfolio page displays virtual portfolio state after position
materialization gates exist. It must not write position rows and must not imply
real holdings.

### PnL

The PnL page displays virtual PnL after valuation gates exist. It must include
virtual-only disclaimers in future UI implementation. It must not imply real
returns or investment advice.

### AI Users

The AI Users page is a future AI profile and policy surface. It must not create
AI decisions, AI evaluations, virtual intents, orders, trades, or real-trade
instructions.

### Leaderboard

The leaderboard page is a future read-only display for approved virtual
performance. It must not create leaderboard materialization in this shell and
must not present results as real returns, investment advice, or future
performance guarantees.

## 8. Data Boundary

Allowed future read sources:

```text
principal-scoped Track B API responses
N6 shadow projection / signal card / notification queue through reviewed adapters
approved virtual account / cash / position / pnl rows scoped to principal
reviewed N4/N5/N6 artifacts exposed through safe summary APIs
approved N2 display_basis summaries through read-only views or adapters
```

Forbidden sources:

```text
raw K
live market data direct connection
N1 raw facts
N3 raw facts used as direct user-app source
N4 raw facts used to bypass reviewed events/artifacts
N5 raw facts used to bypass reviewed events/artifacts
broker account
broker funds
broker position
broker order/trade APIs
Track A /api/n6/ui/v1 APIs as user-app API
```

Shared data or display logic between Track A and Track B requires a dedicated
shared component or adapter gate.

## 9. Track A Isolation

This spec must not modify these Track A pages:

```text
/n6/action-events
/n6/admin/account
/n6/admin/users
```

This spec must not modify or reuse this Track A API namespace:

```text
/api/n6/ui/v1/...
```

If Track B needs to reuse a display pattern from Track A, the next gate must be
explicitly named, for example:

```text
N6_SHARED_COMPONENT_ADAPTER_GATE
```

Track A admin-console evidence remains admin-only audit evidence. It must not
be interpreted as B-track multi-user front-office completion.

## 10. Safety And Forbidden Scope

This shell spec keeps the following disabled:

```text
delivery
push
voice
mobile
sim
position execution
real trade
proposal acceptance
virtual order runner
virtual trade runner
position materialization runner
pnl valuation runner
AI decision engine
AI evaluation
leaderboard materialization
strategy marketplace
```

Forbidden user-facing wording for future shell pages unless a later reviewed
spec explicitly scopes it safely:

```text
已下单
已成交
真实交易
投资建议
```

## 11. Implementation Readiness Requirements

A future implementation gate must provide:

```text
route registration proof under /n6/app/...
API registration proof under /api/n6/app/v1/...
authentication and current-principal resolution
principal-scope access tests
Track A route/API non-regression tests
no write-route proof for first shell
no outbox consumption/update proof
no worker/delivery/push/voice/mobile/sim/position/real-trade proof
forbidden wording tests
```

The first implementation should prefer read-only GET routes. Any mutation,
including watchlist creation, proposal review, proposal acceptance, order
creation, trade materialization, position update, PnL valuation, AI decision,
or leaderboard materialization, must open a separate gate.

## 12. Boundary Flags

```text
database_written = false
code_modified = false
executed = false
outbox_consumed = false
outbox_status_updated = false
worker_started = false
delivery_triggered = false
push_triggered = false
voice_triggered = false
mobile_triggered = false
sim_triggered = false
position_written = false
real_trade_triggered = false
n6_ui_v1_modified = false
n6_ui_v1_api_reused = false
```

## 13. Next Recommended Gate

Recommended sequence:

```text
1. runtime_control N6_MULTI_USER_APP_SHELL_SPEC_REVIEW_GATE
2. N6_user N6_MULTI_USER_APP_SHELL_API_CONTRACT_GATE
3. N6_user N6_MULTI_USER_APP_SHELL_IMPLEMENTATION_READINESS_GATE
4. N6_user N6_MULTI_USER_APP_SHELL_READONLY_IMPLEMENTATION_GATE
```

If shared UI components are desired before implementation, insert:

```text
N6_SHARED_COMPONENT_ADAPTER_GATE
```

