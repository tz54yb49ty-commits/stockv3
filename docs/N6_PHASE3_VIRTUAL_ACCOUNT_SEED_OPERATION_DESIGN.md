# N6 Phase 3 Virtual Account Seed / Operation Design

Status: DESIGN_PASS

Layer role: N6_user

Date: 2026-06-05

This gate designs the Phase 3 virtual account initialization and operation
strategy. It does not write database rows, execute runners, run migrations,
consume or update outbox rows, start workers, modify N6_UI_v1, modify existing
APIs, modify projection or shadow pipelines, deliver notifications, push to
voice or mobile, run sim, materialize positions, or place real trades.

## 1. Inputs

Authoritative inputs:

```text
docs/N6_PHASE3_VIRTUAL_ACCOUNT_SCHEMA_FOUNDATION_CLOSEOUT.md
docs/N6_PHASE3_VIRTUAL_ACCOUNT_SCHEMA_FOUNDATION_CLOSEOUT.json
sql/038A_n6_virtual_account_schema.sql
sql/038B_n6_virtual_cash_schema.sql
sql/038C_n6_virtual_order_trade_schema.sql
sql/038D_n6_virtual_position_schema.sql
sql/038E_n6_virtual_pnl_schema.sql
docs/N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_EXECUTE_CONTRACT.md
docs/N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_execute_contract.json
```

Current schema foundation:

```text
n6_virtual_account exists, row_count=0
n6_virtual_cash_ledger exists, row_count=0
n6_virtual_cash_snapshot exists, row_count=0
n6_virtual_order exists, row_count=0
n6_virtual_trade exists, row_count=0
n6_virtual_position exists, row_count=0
n6_virtual_position_event exists, row_count=0
n6_virtual_pnl_snapshot exists, row_count=0
```

Current principal foundation:

```text
admin principal exists from Phase 2
system principal exists from Phase 2
system principal is a reserved owner root, not an account actor
no AI principal is active for trading or virtual-account operation
```

## 2. Seed Recommendation

The first Phase 3 seed should create exactly one admin virtual account.

Recommended first seed scope:

| Object | Recommendation | Rationale |
|---|---|---|
| Admin virtual account | Create 1 | Admin principal is already seeded and can validate the account/cash foundation. |
| Human demo virtual account | Defer | No separate human demo principal is part of the approved Phase 2 seed. |
| AI virtual account | Defer | AI principal/profile, AI policy, and AI decision gates are not yet active. |
| System virtual account | Forbid | System principal is a reserved owner root and must not own a virtual account by default. |

Planned first seed row counts:

| Table | Planned rows |
|---|---:|
| `n6_virtual_account` | 1 |
| `n6_virtual_cash_ledger` | 1 |
| `n6_virtual_cash_snapshot` | 1 |
| `n6_virtual_order` | 0 |
| `n6_virtual_trade` | 0 |
| `n6_virtual_position` | 0 |
| `n6_virtual_position_event` | 0 |
| `n6_virtual_pnl_snapshot` | 0 |

This seed is virtual-only. It does not imply user session, watchlist, strategy
execution, notification delivery, simulated trade execution, real position, or
real trade.

## 3. Seed Run And Policy

Recommended executable seed identity for the future contract gate:

```text
seed_run_id = n6_phase3_virtual_account_seed_20260605_v1
policy_version = n6_phase3_virtual_account_seed_policy_v1
policy_hash = b85a7bc71353a5ccfe0479fa67f2b403e91eb3f2fa1a0ba89ebddfb6f5cd4377
rollback_scope = n6_phase3_virtual_account_seed_20260605_v1
created_by_gate = N6_PHASE3_VIRTUAL_ACCOUNT_SEED_OR_OPERATION_DESIGN_GATE
source_artifact = docs/N6_PHASE3_VIRTUAL_ACCOUNT_SEED_OPERATION_DESIGN.md
```

Policy canonical payload used for the hash:

```json
{"ai_virtual_account":"deferred","currency":"CNY","forbidden_writes":["n6_virtual_order","n6_virtual_trade","n6_virtual_position","n6_virtual_position_event","n6_virtual_pnl_snapshot"],"human_demo_virtual_account":"deferred","initial_cash":"1000000.0000","policy_version":"n6_phase3_virtual_account_seed_policy_v1","seed_scope":"admin_virtual_account_only","system_principal_virtual_account":"forbidden","writes":["n6_virtual_account","n6_virtual_cash_ledger","n6_virtual_cash_snapshot"]}
```

## 4. Initial Cash Policy

Recommended default:

```text
initial_cash = 1,000,000.0000
currency = CNY
```

The value is a policy default, not a schema default and not a market rule. It
must be supplied by the seed contract and persisted through:

```text
n6_virtual_account.initial_cash
n6_virtual_cash_ledger.amount
n6_virtual_cash_snapshot.available_cash
n6_virtual_cash_snapshot.total_cash
source_lineage_json.policy_version
source_lineage_json.policy_hash
```

The seed must not hard-code fee, tax, T+1, valuation, execution, or order
rules. Those belong to later operation gates.

## 5. Initialization Write Semantics

The future seed execute gate should use a single transaction.

### 5.1 Account Row

Target:

```text
n6_virtual_account
```

Recommended values:

| Field | Value |
|---|---|
| `principal_id` | Phase 2 admin principal id |
| `principal_type` | `admin` |
| `account_name` | `Admin Virtual Account` |
| `virtual_account_status` | `active` |
| `base_currency` | `CNY` |
| `initial_cash` | `1000000.0000` |
| `current_cash_snapshot_id` | Created snapshot id after snapshot insert |
| `run_id` | `n6_phase3_virtual_account_seed_20260605_v1` |
| `policy_version` | `n6_phase3_virtual_account_seed_policy_v1` |
| `policy_hash` | `b85a7bc71353a5ccfe0479fa67f2b403e91eb3f2fa1a0ba89ebddfb6f5cd4377` |
| `rollback_scope` | `n6_phase3_virtual_account_seed_20260605_v1` |
| `quality_status` | `passed` |

`current_cash_snapshot_id` is nullable in 038A. The seed runner may insert the
account first, insert the ledger, insert the snapshot, and then set the account
pointer to the created snapshot id in the same transaction. This does not
create another account row and does not change the cash ledger lineage.

### 5.2 Initial Cash Ledger Row

Target:

```text
n6_virtual_cash_ledger
```

Recommended values:

| Field | Value |
|---|---|
| `virtual_account_id` | Created admin virtual account id |
| `ledger_type` | `initial_deposit` |
| `amount` | `1000000.0000` |
| `currency` | `CNY` |
| `trade_date` | `20260605` |
| `source_event_type` | `phase3_virtual_account_seed` |
| `source_event_id` | `n6_phase3_virtual_account_seed_20260605_v1` |
| `source_virtual_order_id` | `NULL` |
| `source_virtual_trade_id` | `NULL` |
| `run_id` | `n6_phase3_virtual_account_seed_20260605_v1` |
| `policy_version` | `n6_phase3_virtual_account_seed_policy_v1` |
| `policy_hash` | `b85a7bc71353a5ccfe0479fa67f2b403e91eb3f2fa1a0ba89ebddfb6f5cd4377` |
| `rollback_scope` | `n6_phase3_virtual_account_seed_20260605_v1` |
| `quality_status` | `passed` |

This row is immutable lineage for the initial cash. Future balance changes must
append ledger rows instead of replacing this row.

### 5.3 Initial Cash Snapshot Row

Target:

```text
n6_virtual_cash_snapshot
```

Recommended values:

| Field | Value |
|---|---|
| `virtual_account_id` | Created admin virtual account id |
| `trade_date` | `20260605` |
| `available_cash` | `1000000.0000` |
| `frozen_cash` | `0.0000` |
| `total_cash` | `1000000.0000` |
| `currency` | `CNY` |
| `source_ledger_max_id` | Created initial cash ledger id |
| `snapshot_status` | `active` |
| `run_id` | `n6_phase3_virtual_account_seed_20260605_v1` |
| `policy_version` | `n6_phase3_virtual_account_seed_policy_v1` |
| `policy_hash` | `b85a7bc71353a5ccfe0479fa67f2b403e91eb3f2fa1a0ba89ebddfb6f5cd4377` |
| `rollback_scope` | `n6_phase3_virtual_account_seed_20260605_v1` |
| `quality_status` | `passed` |

The snapshot is a balance materialization over the ledger. It does not replace
ledger lineage.

## 6. Quality Gate

The future seed contract/preflight must hard-fail on any P0 item:

| Severity | Check | Result |
|---|---|---|
| P0 | 038A-E tables missing | BLOCKED |
| P0 | Phase 2 admin principal missing or not unique | BLOCKED |
| P0 | system principal selected for virtual account | BLOCKED |
| P0 | target seed rows already exist for `seed_run_id` | BLOCKED |
| P0 | admin principal already has an active virtual account from another seed | BLOCKED unless separate migration/rebuild gate approves |
| P0 | any planned order/trade/position/position_event/pnl rows | BLOCKED |
| P0 | cash snapshot formula mismatch | BLOCKED |
| P0 | ledger amount does not equal initial cash | BLOCKED |
| P0 | any N1-N6 outbox/inbox/checkpoint write plan | BLOCKED |
| P0 | worker, delivery, push, voice, mobile, sim, position, or real-trade side effect | BLOCKED |

Expected quality result for the first seed design:

```text
P0=0
P1=0
P2=0
```

## 7. Rollback Design

Rollback scope:

```text
rollback_scope = n6_phase3_virtual_account_seed_20260605_v1
```

Rollback may delete only rows created by this seed run and must delete in this
order:

```text
1. n6_virtual_cash_snapshot
2. n6_virtual_cash_ledger
3. n6_virtual_account
```

Rollback must hard-fail before the first `DELETE` if any linked operation rows
exist:

```text
n6_virtual_order
n6_virtual_trade
n6_virtual_position
n6_virtual_position_event
n6_virtual_pnl_snapshot
future AI decision / evaluation / leaderboard refs, if those tables exist
```

Rollback must not:

```text
drop 038A-E schema
drop 036/037 objects
delete Phase 2 principal rows
delete N6 projection/card/notification rows
consume or update N5 outbox
touch N1-N6 facts/outbox/inbox/checkpoint
start worker
deliver/push/voice/mobile
run sim/materialize position/place real trade
```

Rollback SQL is not generated by this design gate. It should be generated in
the next virtual account seed contract gate.

## 8. Operation Gates Roadmap

Each operation must be a separate gate and must retain virtual-only semantics.

| Gate | Purpose | Allowed future writes |
|---|---|---|
| Virtual account seed contract gate | Turn this design into executable contract, preflight, rollback, and runner plan | contract artifacts only until user confirms execute |
| Virtual account seed execute gate | Create the first admin virtual account with initial cash ledger/snapshot | `n6_virtual_account`, `n6_virtual_cash_ledger`, `n6_virtual_cash_snapshot` |
| Virtual order proposal gate | Convert selected N6 user signal into virtual order proposal | `n6_virtual_order` only after separate execute gate |
| Virtual execution policy gate | Define deterministic fill policy and action-state eligibility | policy artifacts; later `n6_virtual_trade` |
| Virtual fee/tax policy gate | Define fee/tax calculation policy versions and hashes | policy artifacts; later trade/cash rows |
| Virtual position materialization gate | Materialize virtual fills into position state and position events | `n6_virtual_position`, `n6_virtual_position_event` |
| Virtual pnl valuation gate | Value virtual account using approved price policy | `n6_virtual_pnl_snapshot` |

Out of scope until separate gates:

```text
AI account creation
AI decision runner
AI evaluation
leaderboard
strategy marketplace
N6 UI adapter for virtual account
delivery / push / voice / mobile
real brokerage integration
real trade
```

## 9. Remaining Blockers

This design is ready for runtime_control design review, but the following are
not yet complete:

```text
virtual account seed execute contract not generated
virtual account seed preflight artifact not generated
virtual account seed rollback SQL not generated
virtual account seed runner not implemented
no user confirmation for business writes
no operation policies for order/trade/position/pnl
```

## 10. Review Decision

Design decision:

```text
DESIGN_PASS
```

Allowed next step:

```text
runtime_control N6 Phase 3 virtual account seed/operation design review
```

This document does not authorize execution. Business rows require a future
contract, preflight, rollback SQL, runner, final gate review, and explicit user
confirmation.
