# B Track Product Design V1

Status: DESIGN_PASS

Layer role: N6_user

Date: 2026-06-07

This artifact designs B Track V1 as a read-only multi-user front office for
N6. It does not implement UI, change code, write database rows, consume or
update outbox rows, start workers, deliver notifications, write sim/position
/ PnL rows, generate proposal/order/trade rows, or place real trades.

## 1. Product Position

B Track V1 is not a trading terminal. It is a principal-scoped user front
office that explains reviewed N6 signal projections, account state, watchlist
context, N4/N5 status relationships, and AI-user shadow observers.

Core promises:

```text
READ ONLY
GET-only API
NO ORDER / NO TRADE
NO POSITION UPDATE / NO REAL TRADE
NOT INVESTMENT ADVICE
principal scoped
no A-track /api/n6/ui/v1 reuse
no raw K / N1 raw / direct live market / N4-N5 raw fact bypass
no business database writes
no outbox consumption
no worker
no delivery / push / voice / mobile
```

## 2. Users And Goals

Primary user:

```text
solo system owner using B Track as a safer front-office view of N6 output
```

Future users:

```text
human_user: sees only own principal/account/watchlist/signals
ai_user: shadow observer with explicit strategy and permission boundaries
admin: may inspect B Track scope, but A Track remains the admin console
```

User goals:

```text
understand whether today's N6 projected signals are trustworthy
see why a signal was confirmed, blocked, pending, skipped, or expired
inspect N2 display context and N1 membership context without reading raw N2 internals
track own virtual account state without creating orders or positions
see AI-user observations without treating them as advice or automation
understand which future modules are locked behind gates
```

## 3. Page Tree

V1 active pages:

```text
/n6/app/dashboard
/n6/app/signals
/n6/app/signals/:id            future detail route, read-only
/n6/app/watchlist
/n6/app/account
/n6/app/status-monitor
/n6/app/ai-users
```

V1 locked pages:

```text
/n6/app/proposals
/n6/app/portfolio
/n6/app/pnl
/n6/app/leaderboard
/n6/app/automation
```

## 4. Navigation

Primary navigation:

```text
Dashboard
Signals
Watchlist
Account
Status
AI Users
```

Secondary locked navigation:

```text
Proposals
Portfolio
PnL
Leaderboard
Future Automation
```

Locked modules should render as planned gates, not primary workflows.

## 5. Dashboard

Dashboard is the first-screen operating view.

Required content:

```text
safety banner
trade date
latest N6 projection run
ActionExecuted / ActionBlocked counts
blocked_reason distribution
virtual account summary
latest signal inbox
watchlist summary
AI user summary
status monitor snapshot
future modules locked panel
```

The page must avoid trading language. `ActionExecuted` displays as "market
action confirmation established", not as bought/sold/filled.

## 6. Signals

Signals is the core V1 page.

Required columns:

```text
trade_date
asset_kind
identity_key
code / name
direction
runtime signal_type
source_action_event_type
action_state
action_mark
blocked_reason
queue_status
source_action_run_id
source_projection_run_id
source_condition_display_basis_id
display_basis source table
membership summary availability
```

Required read-only detail:

```text
N2 display_basis context
N1 membership context
N4/N5 -> N6 evidence chain
quality status
source run lineage
canonical wording for ActionExecuted / ActionBlocked
```

Forbidden:

```text
buy button
sell button
proposal generation
order/trade/position/PnL mutation
investment advice wording
raw N4/N5 fact reads
```

## 7. Watchlist

Watchlist V1 is read-only context, not an editable user object manager.

Required content:

```text
stock/index/board rows
condition source from N2 display_basis
membership source from N1 membership_fact
latest status/action summary
recent signal count
data quality status
```

Forbidden in V1:

```text
add/delete/reorder watchlist item
persist watchlist edits
generate new signal from watchlist
infer conditions from membership_fact
```

## 8. Account

Account V1 shows the principal-scoped virtual account and cash snapshot.

Required content:

```text
principal_id / principal_type
virtual_account_id
account_name
status
base_currency
initial_cash
available_cash
frozen_cash
total_cash
quality_status
policy_version / run_id
```

Forbidden:

```text
cash adjustment
deposit/withdraw action
order/trade/position update
real account binding
```

## 9. Status Monitor

Status Monitor shows the N4/N5 relationship without exposing raw fact tables.

Required content:

```text
N4 event counts: TriggerMatched / TriggerPendingMarketData / TriggerStateChanged
N5 relationship: ActionExecuted / ActionBlocked / ActionSkipped / ActionEligible
matched reconciliation
status tabs: active / pending_market_data / inactive
proof that TriggerPendingMarketData and TriggerStateChanged do not create action confirmation
```

## 10. AI Users

AI Users V1 is a shadow observer page.

Required content:

```text
AI principal identity
strategy label / policy version
status
allowed sources
forbidden sources
latest observations
shadow-only explanation
```

Forbidden:

```text
automatic trading
new signal generation
advice without evidence chain
principal-scope bypass
direct N4/N5 raw fact interpretation
```

## 11. Locked Future Modules

V1 render mode:

| Page | V1 behavior |
|---|---|
| Proposals | locked / planned; ActionExecuted may show future eligibility only |
| Portfolio | locked / empty; no virtual position rows in V1 primary surface |
| PnL | locked / empty; non-real return disclaimer |
| Leaderboard | locked / planned; no ranking before PnL and sample controls |
| Future Automation | locked readiness checklist only; no start button |

## 12. MVP, V2, V3

MVP/V1:

```text
Dashboard
Signals
Watchlist readonly
Account readonly
Status Monitor
AI Users shadow readonly
locked future modules
```

V2:

```text
proposal review
watchlist editing gate
virtual order/trade dry-run
virtual position materialization
virtual PnL
AI shadow evaluation
notification preview
```

V3:

```text
AI strategy marketplace
leaderboard with risk/sample controls
automation readiness
real delivery/push/mobile/voice only behind separate gates
real trading only behind explicit future contract
```

## 13. Page Priority

Implementation order:

```text
1. B-track read-only adapter/source policy remediation
2. Dashboard
3. Signals + signal detail
4. Watchlist readonly context
5. Account readonly
6. Status Monitor
7. AI Users
8. Locked future modules
9. Post-review
10. Closeout
```

## 14. Absolutely Not Now

```text
real trade
broker integration
automatic order generation
proposal generation
virtual order/trade/position/PnL materialization
leaderboard ranking
AI generated trade recommendations
push / voice / mobile delivery
direct outbox consumption
direct N4/N5 raw fact reads
condition_basis / condition_pool / minute_target_scope reads
raw K reads
direct live market reads
cross-principal reads
```
