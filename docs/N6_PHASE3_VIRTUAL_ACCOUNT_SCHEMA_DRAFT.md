# N6 Phase 3 Virtual Account Schema Draft

Status: SCHEMA_DRAFT_PASS

Layer role: N6_user

Date: 2026-06-05

This gate produces a Phase 3 virtual-account schema draft only. It does not
execute DDL, run a migration, write database rows, consume or update outbox
rows, start workers, modify N6_UI_v1, modify existing APIs, modify existing
projection/shadow pipelines, deliver notifications, push to voice/mobile, run
sim, create real positions, or place real trades.

## 1. Basis

Source artifacts:

```text
docs/N6_PHASE3_VIRTUAL_ACCOUNT_ARCHITECTURE.md
docs/N6_PHASE3_VIRTUAL_ACCOUNT_ARCHITECTURE.json
docs/N6_PHASE3_VIRTUAL_ACCOUNT_TRACEABILITY.md
docs/N6_PHASE3_VIRTUAL_ACCOUNT_TRACEABILITY.json
runtime_control Phase 3 architecture review APPROVED_WITH_CHANGES
```

SQL draft:

```text
sql/038_n6_virtual_account_schema_draft.sql
```

Rollback draft:

```text
sql/038_n6_virtual_account_schema_rollback_draft.sql
```

## 2. Table List

The draft defines eight Phase 3 tables:

| Table | Purpose |
|---|---|
| `n6_virtual_account` | Principal-owned virtual account container |
| `n6_virtual_cash_ledger` | Immutable cash ledger |
| `n6_virtual_cash_snapshot` | Cash balance snapshot |
| `n6_virtual_position` | Current virtual position state |
| `n6_virtual_position_event` | Immutable position adjustment/event lineage |
| `n6_virtual_order` | Virtual order lifecycle |
| `n6_virtual_trade` | Immutable deterministic virtual fill |
| `n6_virtual_pnl_snapshot` | Virtual PnL valuation snapshot |

The design explicitly separates:

```text
cash ledger from cash snapshot
position current state from position event lineage
```

## 3. Position Model

`n6_virtual_position` is the current-state table.

Key state fields:

```text
virtual_account_id
principal_id
asset_kind
identity_key
quantity
available_quantity
locked_quantity
avg_cost
mark_price
market_value
unrealized_pnl
t_plus_one_locked_until_trade_date
position_status
```

`n6_virtual_position_event` is the immutable adjustment/event lineage table.

Event fields:

```text
position_event_type
quantity_delta
quantity_after
available_quantity_after
locked_quantity_after
avg_cost_after
source_virtual_trade_id
event_time
```

Rules:

```text
state and event lineage are not mixed in one table
quantity fields are nonnegative
available_quantity + locked_quantity <= quantity
position rows never update common_position_state/common_position_event
T+1 lock is virtual-only
```

## 4. Cash Model

`n6_virtual_cash_ledger` is the immutable cash ledger.

Ledger fields:

```text
cash_ledger_type
amount_delta
cash_balance_after
source_virtual_order_id
source_virtual_trade_id
event_time
```

`n6_virtual_cash_snapshot` is the balance snapshot.

Snapshot fields:

```text
snapshot_trade_date
cash_balance
available_cash
frozen_cash
cash_snapshot_status
```

Rules:

```text
cash_balance_after >= 0
available_cash + frozen_cash <= cash_balance
balance changes require ledger lineage
snapshot rows summarize ledger state and are not the only source of truth
```

## 5. Enumerations / CHECK Constraints

The SQL draft uses `TEXT CHECK` constraints rather than PostgreSQL enum types
so future additive alignment can be reviewed per table.

Defined values:

| Field | Values |
|---|---|
| `virtual_account_status` | `draft`, `active`, `paused`, `closed`, `deleted` |
| `cash_ledger_type` | `initial_deposit`, `buy_cash_out`, `sell_cash_in`, `fee`, `tax`, `pnl_adjustment`, `manual_adjustment`, `reversal`, `rollback_adjustment` |
| `cash_snapshot_status` | `draft`, `active`, `superseded`, `deleted` |
| `position_status` | `open`, `closed`, `locked`, `suspended`, `deleted` |
| `position_event_type` | `initial_open`, `buy_increase`, `sell_reduce`, `mark_to_market`, `t_plus_one_unlock`, `manual_adjustment`, `reversal`, `close`, `rollback_adjustment` |
| `order_status` | `draft`, `submitted_virtual`, `partially_filled_virtual`, `filled_virtual`, `cancelled_virtual`, `rejected_virtual`, `expired_virtual` |
| `trade_status` | `filled_virtual`, `reversed_virtual`, `cancelled_virtual` |
| `pnl_status` | `draft`, `passed`, `warning`, `superseded`, `deleted` |

Common quality values:

```text
draft
passed
warning
blocked
```

## 6. Deterministic / Policy Fields

Every Phase 3 table includes:

```text
run_id
policy_version
policy_hash
rollback_scope
source_lineage_json
quality_status
created_at
```

`source_lineage_json` must be a JSON object.

## 7. Virtual Trade Requirements

`n6_virtual_trade` includes deterministic replay fields:

```text
fill_policy_version
fill_policy_hash
replay_deterministic_seed
```

The table intentionally does not define:

```text
broker_order_id
real_trade_id
real_execution_id
```

Virtual trade semantics:

```text
virtual_trade is a deterministic virtual fill only
virtual_trade never means real成交
correction requires reversal or adjustment event
```

## 8. PnL Requirements

`n6_virtual_pnl_snapshot` includes:

```text
source_price_policy
valuation_policy_version
valuation_policy_hash
```

Allowed `source_price_policy` values:

```text
n6_display_snapshot
reviewed_artifact
virtual_mark_policy
```

Forbidden valuation sources:

```text
live price direct
raw K recompute
N1 raw facts
N3 raw facts
broker account/funds/position
```

PnL is virtual only and must not be displayed as real return.

## 9. Principal Ownership

Every account root is owned through 036:

```text
n6_virtual_account.principal_id -> n6_principal.principal_id
```

Derived rows also carry `principal_id`:

```text
n6_virtual_cash_ledger
n6_virtual_cash_snapshot
n6_virtual_position
n6_virtual_position_event
n6_virtual_order
n6_virtual_trade
n6_virtual_pnl_snapshot
```

System principal default:

```text
system principal does not create virtual account by default
system-owned virtual account requires a separate gate
```

AI account compatibility:

```text
ai_virtual requires n6_principal.principal_type='ai_user'
ai_virtual requires n6_ai_user profile and approved AI lifecycle gate
AI cannot access real account/funds/position or broker APIs
```

## 10. Migration Split Recommendation

This schema draft is intentionally full-scope for review. Future migration
execute should be allowed to split into smaller final gates:

| Batch | Tables |
|---|---|
| 038A | `n6_virtual_account` |
| 038B | `n6_virtual_cash_ledger`, `n6_virtual_cash_snapshot` |
| 038C | `n6_virtual_order`, `n6_virtual_trade` |
| 038D | `n6_virtual_position`, `n6_virtual_position_event` |
| 038E | `n6_virtual_pnl_snapshot` |

Each split gate must have its own preflight, rollback, post-review, and
static checks. This draft does not enter migration final gate.

## 11. Rollback Draft

Rollback file:

```text
sql/038_n6_virtual_account_schema_rollback_draft.sql
```

Rollback properties:

```text
hard-fail before first DROP
block if any Phase 3 table has rows
no CASCADE
drop only the 8 Phase 3 tables
do not drop 036/037 tables/views/permissions
do not touch N1-N6 facts/outbox
do not touch N6_UI_v1
```

## 12. Remaining Gaps

```text
no migration final gate
no live database proof
no runner
no virtual account rows
no AI principal/profile active gate
no virtual_intent implementation
no leaderboard integration
no UI/API adapter
```

## 13. Next Gate

Allowed next step:

```text
runtime_control Phase 3 schema draft review
```

Still forbidden:

```text
DDL execute
database write
outbox consumption/update
worker
delivery/push/voice/mobile/sim/position/real trade
```
