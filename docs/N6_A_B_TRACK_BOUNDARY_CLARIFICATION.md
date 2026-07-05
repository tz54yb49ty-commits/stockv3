# N6 A/B Track Boundary Clarification

Status: CLARIFICATION_PASS

Layer role: runtime_control

Date: 2026-06-05

This document clarifies the boundary between Track A `N6_UI_v1_ADMIN_CONSOLE`
and Track B `N6_MULTI_USER_AND_AI`. It is a runtime-control documentation
artifact only. It does not change code, write database rows, execute runners,
consume or update outbox rows, start workers, deliver notifications, push to
voice or mobile, run sim, create virtual orders/trades/positions/PnL, or place
real trades.

## 1. Why This Clarification Exists

`N6_UI_v1 admin virtual account readonly adapter` has passed post-review and
can display the admin virtual account, cash snapshot, and cash ledger. That
achievement belongs to the administrator read-only console. It does not mean
the future multi-user front office, AI-user workflow, proposal lifecycle,
personal watchlist, leaderboard, or virtual trading operation flow is complete.

The risk is that an operator or later gate may see admin virtual-account fields
inside `N6_UI_v1` and treat them as proof that the B-track multi-user user
experience has shipped. That interpretation is invalid.

## 2. Track A: N6_UI_v1_ADMIN_CONSOLE

Track A is the administrator console and read-only runtime dashboard.

Allowed purpose:

```text
administrator read-only console
view N4 / N5 / N6 signal messages
view ActionBlocked / ActionExecuted
view N6 shadow projection
view admin virtual account and cash state
safety audit
rollback and artifact links
runtime message dashboard
```

Track A currently owns these completed or reviewed items:

```text
N6 login/session/auth for the current web app
/n6/action-events read-only message dashboard
/n6/admin/account admin virtual account read-only page
GET /api/n6/ui/v1/virtual-account
GET /api/n6/ui/v1/cash-snapshot
GET /api/n6/ui/v1/cash-ledger
ActionBlocked / ActionExecuted display wording boundary
read-only safety banner
admin user-management utility in the current console
```

Track A does not provide:

```text
regular-user front office
multi-user personal home page
per-principal watchlist management
AI user strategy execution
user proposal review / confirmation workflow
user virtual trading operation flow
leaderboard
strategy marketplace
real delivery / push / voice / mobile execution
real trade
```

The existing user-management add/delete function is classified as:

```text
admin-console legacy/admin utility
```

It is not the B-track canonical user lifecycle. It does not prove multi-user
front-office onboarding, per-principal permissions, watchlist isolation,
strategy ownership, or virtual-account operation lifecycle.

## 3. Track B: N6_MULTI_USER_AND_AI

Track B is the future multi-user, AI-user, virtual-account, and strategy
front-office track.

Target purpose:

```text
true multi-user front office
human user / AI user principal model
independent virtual account per principal
watchlist
strategy
proposal
virtual order / virtual trade / virtual position / virtual PnL
AI decision / AI evaluation
leaderboard
strategy marketplace
future real-trade boundary
```

Track B must be treated as independently gated. A Track B module is not
implemented merely because Track A has an admin-only read-only view.

Current B-track foundations that exist as schema or seed evidence:

```text
owner/principal schema foundation
readonly view permission foundation
admin/system principal seed
virtual_account schema
virtual_cash ledger/snapshot schema
virtual_order / virtual_trade schema
virtual_position / virtual_position_event schema
virtual_pnl_snapshot schema
admin virtual account seed with initial cash
```

Current B-track gaps:

```text
multi-user front-office UI
per-principal virtual-account UI
watchlist implementation
strategy center implementation
proposal schema / runner / review / acceptance
virtual order runner
virtual trade runner
position materialization runner
PnL valuation runner
AI decision engine
AI evaluation
leaderboard
strategy marketplace
real-trade adapter boundary
```

## 4. Boundary Rules

Canonical boundary rules:

```text
Track B may reuse Track A read-only component ideas.
Track B must not directly modify legacy N6_UI_v1 APIs.
Track B must not silently add write behavior to Track A pages.
If shared display is needed, it must go through an adapter gate.
N6_UI_v1 showing admin virtual account is administrator audit only.
N6_UI_v1 admin virtual account display does not complete the multi-user front office.
Admin user-management utility does not equal Track B user lifecycle.
Track B modules require their own contract, schema, migration, runner, execute, post-review, and rollback gates as applicable.
```

Forbidden inference:

```text
admin virtual account visible in Track A != all users have virtual accounts
admin cash snapshot visible in Track A != user portfolio page is complete
proposal_eligibility display in Track A != proposal workflow is implemented
virtual order/trade schema exists != virtual order/trade runner is implemented
user management utility exists != canonical multi-user lifecycle is complete
queued_only or preview rows visible != delivery/push/mobile/voice is enabled
```

## 5. Current Completed Items by Track

Track A completed / usable for admin read-only review:

```text
admin login/session for current N6 web app
read-only action-events dashboard
read-only admin virtual account summary
read-only cash snapshot and ledger display
ActionBlocked wording: 市场动作未确认
ActionExecuted wording: 市场动作确认成立
safety labels: READ ONLY / NO ORDER / NO TRADE / NO POSITION UPDATE / NO REAL TRADE
```

Track B completed as foundations only:

```text
principal/account ownership schema and seed foundation
virtual account schema foundation
virtual cash schema foundation
virtual order/trade schema foundation
virtual position schema foundation
virtual PnL schema foundation
admin virtual account seed foundation
order proposal spec
operation policy design
```

Track B not complete:

```text
multi-user user-facing product
AI user runtime
per-user watchlist product
proposal review product
virtual trading operation
leaderboard product
strategy marketplace
real-trade integration
```

## 6. Misunderstanding Risks

| Risk | Clarification |
|---|---|
| Admin account page is mistaken for user portfolio | It is an admin audit page only. |
| `proposal_candidate` is mistaken for a generated proposal | It is display-only eligibility text. No proposal row is generated. |
| Virtual account seed is mistaken for multi-user account rollout | Only admin virtual account seed is completed. |
| User management utility is mistaken for B-track lifecycle | It is a legacy/admin console utility until a B-track user lifecycle gate exists. |
| Existing virtual order/trade/position schema is mistaken for operation readiness | Schema foundation exists; runners and execution policy remain gated. |
| Notification preview is mistaken for delivery | Preview/queued-only does not trigger delivery, push, voice, or mobile. |

## 7. Recommended Route

Recommended next route:

```text
1. Keep Track A focused on admin read-only runtime monitoring.
2. Do not expand Track A into a multi-user product surface.
3. For B-track user-facing work, open a dedicated B-track front-office architecture/spec gate.
4. Define B-track adapters for any reused Track A display components.
5. Continue proposal schema / proposal runner dry-run / review acceptance gates before virtual order execution.
6. Keep real delivery, sim, position execution, and real trade behind separate gates.
```

Allowed next runtime-control registration:

```text
record this clarification as the boundary between N6_UI_v1_ADMIN_CONSOLE and N6_MULTI_USER_AND_AI
```

This clarification does not authorize any implementation, migration, execution,
database write, worker, outbox consumption, delivery, push, voice, mobile, sim,
position update, PnL generation, or real trade.
