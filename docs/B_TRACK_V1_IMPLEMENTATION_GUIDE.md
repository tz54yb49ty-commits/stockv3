# B Track V1 Implementation Guide

Status: IMPLEMENTATION_GUIDE_PASS / IMPLEMENTATION_BLOCKED

Layer role: N6_user

Date: 2026-06-07

This guide gives implementation-gate acceptance criteria for B Track V1. It is
not an implementation artifact and does not change code or data.

## Global Requirements

All B Track V1 pages and APIs must remain:

```text
GET-only
readonly
principal scoped
not investment advice
no order / no trade
no position update / no real trade
no outbox consumption
no worker
no delivery / push / voice / mobile
```

All pages must use the B Track-owned source policy:

```text
N6 reviewed projection/card outputs
N2 display_basis readonly views
N1 membership_fact readonly views
```

## Page Gate Matrix

| Gate | Current status | Required result after implementation |
|---|---|---|
| B_TRACK_DASHBOARD_IMPLEMENTATION | BLOCKED | Dashboard DTO reads B Track allowlist only |
| B_TRACK_SIGNALS_IMPLEMENTATION | BLOCKED | Signals adapter no longer calls A Track fetch_ui_v1_signals |
| B_TRACK_WATCHLIST_IMPLEMENTATION | BLOCKED | Watchlist uses display_basis/membership views, no writes |
| B_TRACK_ACCOUNT_IMPLEMENTATION | PARTIAL_PASS | Add complete safety labels and keep principal-scoped account read |
| B_TRACK_STATUS_MONITOR_IMPLEMENTATION | BLOCKED | Use reviewed status monitor adapter/artifact, no projection/card writes |
| B_TRACK_AI_USERS_IMPLEMENTATION | BLOCKED | AI shadow observers only, no generated signal/advice |
| B_TRACK_LOCKED_FUTURE_MODULES_IMPLEMENTATION | BLOCKED | Future modules render locked/planned and avoid virtual position/PnL reads |

## Dashboard

Required:

```text
safety banner
trade date
latest N6 projection run
ActionExecuted / ActionBlocked counts
blocked_reason distribution
account summary
signal inbox summary
watchlist summary
AI users summary
future modules locked
```

Must not:

```text
read raw K
read direct live market
read N4/N5 raw facts
show trade action buttons
```

## Signals

Required:

```text
principal-scoped N6 projection/card rows
display_basis explanation
membership explanation
N4/N5 -> N6 evidence chain
ActionExecuted wording = market action confirmation established
ActionBlocked wording = market action not confirmed
```

Must not:

```text
call fetch_ui_v1_signals
join unreviewed common_event_outbox directly
show buy/sell/advice buttons
```

## Watchlist

Required:

```text
stock/index/board context
condition display context
index/board membership context
latest signal/status summary
```

Must not:

```text
add/delete/reorder/persist rows
create scope
infer conditions from membership
```

## Account

Required:

```text
principal identity
virtual account summary
cash snapshot
quality/status/run/policy fields
```

Must not:

```text
cash mutation
real account binding
order/trade/position changes
```

## Status Monitor

Required:

```text
TriggerMatched / TriggerPendingMarketData / TriggerStateChanged counts
ActionExecuted / ActionBlocked relationship
active / pending_market_data / inactive status tabs
proof status-only events do not enter action confirmation
```

Must not:

```text
write projection/card
consume outbox
read raw trigger/action facts as a B Track bypass
```

## AI Users

Required:

```text
AI principal identity
strategy/policy label
shadow observer status
allowed/forbidden sources
latest observation summary
```

Must not:

```text
generate real signals
generate orders
auto-trade
provide advice without evidence chain
```

## Locked Future Modules

Required:

```text
Proposals = locked/planned
Portfolio = locked/empty
PnL = locked/empty with non-real return disclaimer
Leaderboard = locked/planned
Future Automation = locked readiness checklist only
```

Must not:

```text
materialize proposals/orders/trades/positions/PnL
rank users by returns
start automation
```

## Required Implementation Validation

```text
static route scan: GET-only for /api/n6/app/v1 and /n6/app
static source scan: no fetch_ui_v1_signals in B Track adapters
static source scan: display_basis and membership views present in allowlist
static source scan: forbidden sources present in policy
unit tests: safety labels include NOT INVESTMENT ADVICE
unit tests: principal_id/principal_type are enforced by B Track adapters
unit tests: locked modules do not read virtual position/PnL unless allowed
compile/test command for changed web/tests files
```
