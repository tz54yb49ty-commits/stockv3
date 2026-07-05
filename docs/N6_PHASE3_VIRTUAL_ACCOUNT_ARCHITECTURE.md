# N6 Phase 3 Virtual Account Architecture

Status: ARCHITECTURE_DRAFT_PASS

Layer role: N6_user

Date: 2026-06-05

This document drafts the Phase 3 Track B virtual-account architecture. It does
not create schema, run migrations, write database rows, consume or update
outbox rows, start workers, modify N6_UI_v1, modify existing APIs, modify
existing projection/shadow pipelines, deliver notifications, push to
voice/mobile, run live sim, create real positions, or place real trades.

## 1. Goal

Phase 3 defines a future N6-only virtual-account system that can represent
human/admin and AI-owned virtual portfolios without touching broker accounts or
N1-N5 facts. The architecture provides stable ownership, run lineage, policy
versioning, rollback scope, quality gates, and event/fact separation for future
schema and runner gates.

Phase 3 does not turn current `user_sim_*` shadow tables into the canonical
virtual-account system. Those tables remain existing shadow evidence only.

## 2. Source Basis

Required upstream artifacts:

```text
docs/N6_MULTI_USER_AND_AI_ARCHITECTURE_v1.md
docs/N6_MULTI_USER_AND_AI_ARCHITECTURE_TRACEABILITY_v1.md
docs/N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_EXECUTE_CONTRACT.md
docs/N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_execute_contract.json
sql/036_n6_multi_user_ai_owner_principal_schema.sql
```

Current Phase 2 owner roots:

```text
admin principal: principal_type=admin, principal_status=active
system principal: principal_type=system, principal_status=system_reserved
```

Future AI virtual account compatibility requires a separate AI principal/profile
gate before active AI ownership can be enabled.

## 3. Ownership Boundary

All Phase 3 virtual-account objects are owned by a Track B principal:

```text
principal_id
principal_type
account_id
virtual_account_id
```

Allowed ownership modes:

| Principal type | Virtual account mode | Status |
|---|---|---|
| `admin` | `admin_shadow_virtual` | planned |
| `human_user` | `human_virtual` | future gate |
| `ai_user` | `ai_virtual` | future gate, inactive until AI profile gate |
| `system` | none by default | reserved only |

Hard boundaries:

```text
virtual_account is not a real broker account
virtual_cash is not real cash
virtual_position is not a real holding
virtual_order is not a broker order
virtual_trade is not an exchange execution
virtual_pnl is not real return
```

## 4. Virtual Account

Logical object:

```text
n6_virtual_account
```

Purpose:

```text
canonical N6-only account container for virtual cash, positions, orders,
trades, and PnL
```

Required fields:

```text
virtual_account_id
account_id
principal_id
principal_type
account_mode
account_status
initial_cash
currency
run_id
policy_version
policy_hash
rollback_scope
source_lineage_json
quality_status
created_at
updated_at
```

Rules:

```text
initial_cash defaults may be configured only by policy
account_status lifecycle: draft, active, paused, closed, deleted
no broker credentials
no real account number
no real cash balance
account_id must bridge to n6_principal_account in a future schema gate
```

## 5. Virtual Cash

Logical object:

```text
n6_virtual_cash
```

Purpose:

```text
cash ledger and cash snapshot for an N6 virtual account
```

Required fields:

```text
virtual_cash_id
virtual_account_id
cash_event_type
amount_delta
cash_balance_after
currency
trade_date
event_time
source_virtual_order_id
source_virtual_trade_id
run_id
policy_version
policy_hash
rollback_scope
quality_status
created_at
```

Rules:

```text
cash_balance_after must never be negative unless policy explicitly allows margin
margin is disabled by default
cash event is immutable after commit
corrections require adjustment events
```

## 6. Virtual Position

Logical object:

```text
n6_virtual_position
```

Purpose:

```text
position state and immutable position adjustment lineage for virtual accounts
```

Required fields:

```text
virtual_position_id
virtual_account_id
asset_kind
identity_key
code
name
quantity
available_quantity
locked_quantity
avg_cost
mark_price
market_value
unrealized_pnl
t_plus_one_locked_until_trade_date
position_status
run_id
policy_version
policy_hash
rollback_scope
source_virtual_trade_id
source_lineage_json
quality_status
created_at
updated_at
```

Rules:

```text
quantity >= 0
available_quantity + locked_quantity <= quantity
sell cannot exceed available_quantity
T+1 lock is policy-driven and virtual-only
position rows do not modify common_position_state or real holdings
```

## 7. Virtual Order

Logical object:

```text
n6_virtual_order
```

Purpose:

```text
virtual intent/order lifecycle derived from accepted user or AI intent
```

Required fields:

```text
virtual_order_id
virtual_account_id
principal_id
source_signal_projection_id
source_signal_card_id
source_decision_id
source_ai_decision_id
asset_kind
identity_key
side
order_type
quantity
limit_price
order_status
submitted_at
filled_quantity
avg_fill_price
cancelled_at
run_id
policy_version
policy_hash
rollback_scope
quality_status
created_at
updated_at
```

Rules:

```text
virtual_order is not a broker order
order_status lifecycle: draft, submitted_virtual, partially_filled_virtual,
filled_virtual, cancelled_virtual, rejected_virtual, expired_virtual
no exchange/broker adapter call
no N5 outbox consumption or status update
```

## 8. Virtual Trade

Logical object:

```text
n6_virtual_trade
```

Purpose:

```text
immutable virtual fill event generated from virtual order policy
```

Required fields:

```text
virtual_trade_id
virtual_order_id
virtual_account_id
principal_id
asset_kind
identity_key
side
quantity
price
gross_amount
fee_amount
tax_amount
net_amount
trade_date
trade_time
fill_policy_version
fill_policy_hash
run_id
rollback_scope
quality_status
created_at
```

Rules:

```text
virtual_trade is immutable
corrections require reversal/adjustment events
virtual fill policy must be deterministic for replay
virtual_trade never means real成交
```

## 9. Virtual PnL

Logical object:

```text
n6_virtual_pnl
```

Purpose:

```text
daily and run-scoped virtual performance snapshot
```

Required fields:

```text
virtual_pnl_id
virtual_account_id
principal_id
trade_date
cash_balance
market_value
total_equity
realized_pnl
unrealized_pnl
daily_return_pct
max_drawdown_pct
benchmark_identity_key
run_id
policy_version
policy_hash
rollback_scope
source_lineage_json
quality_status
created_at
```

Rules:

```text
PnL is virtual only
PnL is not investment advice
PnL is not real return
Leaderboard may only read approved PnL snapshots after a separate gate
```

## 10. Run / Policy / Rollback Model

Every Phase 3 materialization must carry:

```text
run_id
policy_version
policy_hash
rollback_scope
source_lineage_json
quality_status
```

Run classes:

| Run class | Scope |
|---|---|
| `virtual_account_run_id` | account initialization |
| `virtual_order_run_id` | order creation / state transition |
| `virtual_trade_run_id` | deterministic virtual fills |
| `virtual_position_run_id` | position state update |
| `virtual_pnl_run_id` | PnL snapshot |

Rollback scopes:

```text
by run_id
by virtual_account_id and run_id
by principal_id and run_id
```

Rollback hard-fail conditions:

```text
downstream virtual_trade exists for an order rollback
downstream virtual_position exists for a trade rollback
downstream virtual_pnl exists for position/trade rollback
AI evaluation or leaderboard refs exist
delivery/push/voice/mobile refs exist
real trade refs exist
```

Rollback must not:

```text
drop schema
modify N1-N5 facts
consume/update outbox
delete Track A N6 projection rows
delete real/sim legacy rows outside explicit future adapter gates
```

## 11. Quality Gate

Minimum quality checks:

```text
owner principal exists and status allows virtual account use
account policy hash matches artifact
cash balance is internally consistent
position quantities are nonnegative
T+1 available/locked quantities are consistent
order quantity and price are valid
trade gross/net amount math is consistent
PnL total_equity = cash_balance + market_value
source lineage is present
forbidden real/broker fields absent
```

P0 blockers:

```text
missing principal
principal disabled/deleted
active AI account without approved AI profile
negative cash without margin policy
negative position quantity
sell exceeds available virtual quantity
missing policy_hash
missing rollback_scope
broker credential or real account field present
N5 outbox status update planned
real trade call planned
```

P1 warnings:

```text
display price missing
benchmark missing
industry/board context missing
non-critical PnL display field missing
```

P2 notes:

```text
reserved policy extension
future leaderboard eligibility pending
future AI evaluation pending
```

## 12. AI Account Compatibility

AI virtual accounts are supported only after separate AI principal/profile gates:

```text
n6_principal.principal_type = ai_user
n6_ai_user profile exists
n6_ai_user.status is approved for virtual workflow
AI readable boundary passed
AI proposal lifecycle reached virtual_intent
```

AI virtual account limits:

```text
AI can create virtual_intent only through approved lifecycle
AI virtual_intent can enter only virtual_order
AI cannot access real account/funds/position
AI cannot call broker or real trade API
AI cannot consume/update N5 outbox
AI virtual performance can feed leaderboard only after evaluation gate
```

## 13. Data Source Boundary

Allowed sources:

```text
N6 shadow projection rows
accepted user decision rows from a future decision gate
accepted AI virtual_intent rows from a future AI gate
approved N2 display summaries
reviewed N4/N5 artifacts
future virtual account events/facts
```

Forbidden sources:

```text
raw K
live行情直连
N1 raw facts
N3 raw facts
N4 raw facts
N5 raw facts
broker sessions
real accounts
real funds
real positions
real trade API
```

## 14. Independent Future Gates

This architecture draft requires separate gates for:

```text
virtual account schema
virtual cash schema
virtual order schema
virtual trade schema
virtual position schema
virtual pnl schema
virtual account initialization runner
virtual order runner
virtual fill policy runner
virtual position materializer
virtual pnl materializer
AI virtual account adapter
leaderboard reader
rollback SQL per module
```

## 15. Current Gaps

```text
no Phase 3 SQL schema
no Phase 3 migration
no Phase 3 runner
no virtual account rows
no virtual cash/position/order/trade/pnl rows
no AI principal/profile active gate
no AI decision virtual_intent implementation
no leaderboard integration
no UI/API adapter
```

## 16. Next Gate

Allowed next step:

```text
runtime_control N6 Phase 3 virtual account architecture review gate
```

Still forbidden:

```text
database write
migration
execute
outbox consumption/update
worker
delivery/push/voice/mobile/sim/position/real trade
```
