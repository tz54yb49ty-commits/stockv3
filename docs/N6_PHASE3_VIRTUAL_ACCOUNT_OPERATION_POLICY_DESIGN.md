# N6 Phase 3 Virtual Account Operation Policy Design

Status: DESIGN_PASS

Layer role: N6_user

Date: 2026-06-05

This gate designs the virtual account operation policy path after the Phase 3
admin virtual account seed. It does not write database rows, execute runners,
run migrations, consume or update outbox rows, start workers, modify N6_UI_v1,
modify existing APIs, modify projection or shadow pipelines, deliver
notifications, push to voice or mobile, run sim, materialize positions, or
place real trades.

## 1. Current Baseline

Phase 3 admin virtual account seed has passed post-review:

```text
admin virtual account exists
virtual_account_id = 1
principal = admin
initial_cash = 1000000.0000 CNY
n6_virtual_account = 1
n6_virtual_cash_ledger = 1
n6_virtual_cash_snapshot = 1
n6_virtual_order = 0
n6_virtual_trade = 0
n6_virtual_position = 0
n6_virtual_position_event = 0
n6_virtual_pnl_snapshot = 0
outbox/inbox/checkpoint refs = 0
delivery/push/voice/mobile/sim/position/real_trade = false
```

Schema foundation exists for:

```text
n6_virtual_order
n6_virtual_trade
n6_virtual_position
n6_virtual_position_event
n6_virtual_pnl_snapshot
```

This design defines policy sequencing only. It does not authorize writing these
tables.

## 2. Policy Boundary

Virtual account operations are user-layer shadow operations. They never imply:

```text
real brokerage order
real account access
real funds
real position
real fill
real PnL
investment advice
N5 outbox consumption
N1-N5 fact mutation
```

All operation policies must be versioned and replayable:

```text
run_id
policy_version
policy_hash
rollback_scope
source_lineage_json
quality_status
```

Every gate must produce rollback scope before it writes rows. Any write runner
must require a separate final gate and explicit `--execute --user-confirmed`.

## 3. Order Proposal

### 3.1 Meaning

An order proposal is a user-reviewable virtual intent candidate. It is not a
virtual order and must not write `n6_virtual_order`.

Recommended lifecycle:

```text
draft
reviewed
accepted
rejected
expired
```

Only `accepted` proposals may enter a future virtual order runner.

### 3.2 Input Boundary

Preferred input:

```text
N6 user_signal_projection
N6 user_signal_card
reviewed N6/N5 source artifact links
admin virtual account current cash snapshot
```

N6 operation policy should not directly scan N4/N5 raw fact tables to bypass
projection. If a new N5 event has not been projected into N6, the correct next
step is an N6 projection gate, not a direct order proposal write.

Signal mapping:

| N5/N6 state | Proposal policy |
|---|---|
| `ActionBlocked` / `blocked` | No proposal by default; display only. |
| `ActionExecuted` / `action_confirmed` | May generate proposal candidate, but still not a real trade. |
| `ActionEligible` / `candidate` | May generate proposal candidate if user policy permits. |
| `ActionSkipped` / `skipped` | No proposal; informational only. |

### 3.3 Proposal Payload

Future proposal artifact/table should carry:

```text
proposal_id
proposal_run_id
virtual_account_id
principal_id
principal_type
source_user_signal_projection_id
source_user_signal_card_id
source_action_run_id
source_action_event_id
asset_kind
identity_key
signal_type
proposal_side
proposal_quantity_policy
proposal_price_policy
proposal_status
review_status
reviewed_by_user_id
reviewed_at
policy_version
policy_hash
rollback_scope
source_lineage_json
quality_status
```

This gate does not create a proposal table. A future order proposal spec must
decide whether proposal is an artifact-only dry-run, an N6 table, or a UI-only
review queue.

## 4. Execution Policy

Execution policy applies only after a proposal is accepted and before a virtual
trade is generated. It only affects virtual orders/trades.

Policy must cover:

```text
trading calendar
trading session / time window
T+1 availability
suspension / halt state
limit up / limit down
market rule set
round-lot / quantity normalization
cash availability
position availability for virtual sells
deterministic fill seed
```

Execution policy must not:

```text
call broker API
read broker session
touch real account
touch common_position_*
touch user_sim_*
update N5 outbox
reinterpret N5 action_state
```

Recommended first version:

```text
execution_policy_version = n6_virtual_execution_policy_v1
fill_policy_version = n6_virtual_fill_policy_v1
market_rule_set = cn_a_share_virtual_v1
```

The concrete T+1 and market-rule implementation must be a separate execution
policy spec. This design only requires that those rules be policy versioned and
not hard-coded into schema.

## 5. Fee / Tax Policy

Fee/tax policy is versioned and separate from order proposal and execution.

Policy families:

```text
fee_policy_version
fee_policy_hash
tax_policy_version
tax_policy_hash
transfer_fee_policy_version
transfer_fee_policy_hash
```

Amounts may be written into future virtual order/trade rows only after a
fee/tax policy gate:

```text
estimated_fee_amount
estimated_tax_amount
commission_amount
stamp_tax_amount
transfer_fee_amount
total_fee_amount
```

This design does not choose real brokerage rates and does not hard-code
commission, stamp tax, transfer fee, minimum fee, rounding, or exemption rules.

## 6. Position Materialization

Position materialization must follow this lineage:

```text
n6_virtual_trade
  -> n6_virtual_position_event
  -> n6_virtual_position
```

Position event is immutable lineage. Position is current state.

Materialization policy must:

```text
append n6_virtual_position_event first
create or update n6_virtual_position current state
set quantity = available_quantity + locked_quantity
use last_virtual_trade_id for trace
preserve source_virtual_order_id and source_virtual_trade_id
record run_id / policy_version / policy_hash / rollback_scope
```

T+1 is only represented through virtual state:

```text
locked_quantity
available_quantity
```

T+1 must not create real positions, real settlement, or broker-side locks.

## 7. PnL Valuation

PnL valuation produces virtual snapshots only:

```text
n6_virtual_pnl_snapshot
```

Allowed valuation inputs:

```text
approved N6 display snapshot
reviewed artifact
virtual mark policy
n6_virtual_cash_snapshot
n6_virtual_position
n6_virtual_trade fee/tax fields
```

Forbidden valuation inputs:

```text
raw K
live price direct connection
brokerage performance
real account value
real position value
investment-advice model output
```

The snapshot must state:

```text
source_price_policy
valuation_policy_version
valuation_policy_hash
```

PnL is not real return, not investment advice, and not a prediction of future
returns. A future leaderboard may only read approved virtual PnL snapshots and
must repeat this disclaimer.

## 8. Gate Roadmap

Required gate order:

| Order | Gate | Purpose | Future write scope |
|---:|---|---|---|
| 1 | Order proposal spec | Define proposal source, review lifecycle, accepted/rejected semantics | No writes unless separately approved |
| 2 | Execution policy spec | Define T+1, time, halt, limit, fill and market rules | Policy artifacts only |
| 3 | Fee/tax policy spec | Define fee/tax versions, hashes, rounding and amount semantics | Policy artifacts only |
| 4 | Virtual order runner | Materialize accepted proposal into `n6_virtual_order` | `n6_virtual_order` only |
| 5 | Virtual trade runner | Deterministically fill virtual order into `n6_virtual_trade` and cash ledger/snapshot deltas | `n6_virtual_trade`, `n6_virtual_cash_ledger`, `n6_virtual_cash_snapshot` |
| 6 | Position materialization runner | Materialize virtual trades into position events and current position | `n6_virtual_position_event`, `n6_virtual_position` |
| 7 | PnL valuation runner | Create approved virtual PnL snapshot | `n6_virtual_pnl_snapshot` |
| 8 | UI adapter | Read-only display of virtual account/order/trade/position/PnL | Read-only APIs/UI |

Each gate requires its own contract, preflight, rollback, tests, final review,
and explicit user confirmation before any write.

## 9. Rollback Model

Rollback must be downstream-first:

```text
PnL valuation rollback
Position materialization rollback
Virtual trade rollback
Virtual order rollback
Order proposal rollback, if proposal rows exist
Virtual account seed rollback
```

No rollback may touch:

```text
N5 outbox
N4/N5 facts
N1-N3 facts
N6 shadow projection/card/queue rows
Phase 2 principal rows
real account/position/trade tables
```

## 10. Forbidden Scope

This design gate forbids:

```text
database writes
execute
migration
N5 outbox consumption/update
worker
N6_UI_v1/API/projection/shadow mutation
delivery / push / voice / mobile
sim
position materialization
real trade
broker API
raw K / live price direct read for valuation
```

## 11. Next Recommended Gate

Recommended next gate:

```text
N6_PHASE3_ORDER_PROPOSAL_SPEC_GATE
```

Alternative allowed read-only gates:

```text
N6_PHASE3_EXECUTION_POLICY_SPEC_GATE
N6_PHASE3_FEE_TAX_POLICY_SPEC_GATE
runtime_control operation policy design review
```

This design does not authorize any operation execution.
