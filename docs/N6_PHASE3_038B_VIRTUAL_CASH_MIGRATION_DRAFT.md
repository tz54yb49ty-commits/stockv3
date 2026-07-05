# N6 Phase 3 038B Virtual Cash Migration Draft

Status: DRAFT_PASS

Layer role: N6_user

Date: 2026-06-05

This gate drafts the split 038B migration for virtual cash ledger and cash
snapshot only. It does not execute DDL, write database rows, run a migration,
consume or update outbox rows, start workers, modify N6_UI_v1, modify existing
APIs, modify projection/shadow pipelines, deliver notifications, push to
voice/mobile, run sim, create positions, or place real trades.

## 1. Basis

Source artifacts:

```text
docs/N6_PHASE3_VIRTUAL_ACCOUNT_SCHEMA_DRAFT.md
docs/N6_PHASE3_VIRTUAL_ACCOUNT_SCHEMA_DRAFT.json
docs/N6_PHASE3_VIRTUAL_ACCOUNT_SCHEMA_TRACEABILITY.md
docs/N6_PHASE3_VIRTUAL_ACCOUNT_SCHEMA_TRACEABILITY.json
docs/N6_PHASE3_VIRTUAL_ACCOUNT_SCHEMA_STATIC_TESTS.md
docs/N6_PHASE3_VIRTUAL_ACCOUNT_SCHEMA_STATIC_TESTS.json
sql/038_n6_virtual_account_schema_draft.sql
sql/038_n6_virtual_account_schema_rollback_draft.sql
runtime_control Phase 3 schema split route
```

038B files:

```text
sql/038B_n6_virtual_cash_schema.sql
sql/038B_n6_virtual_cash_schema_rollback.sql
```

## 2. Scope

038B creates only:

```text
n6_virtual_cash_ledger
n6_virtual_cash_snapshot
```

038B does not create:

```text
n6_virtual_position
n6_virtual_position_event
n6_virtual_order
n6_virtual_trade
n6_virtual_pnl_snapshot
```

038B does not create account linkage, AI, strategy, watchlist, position,
delivery, push, voice, mobile, sim, or real-trade objects.

## 3. Cash Ledger Model

`n6_virtual_cash_ledger` is the immutable cash ledger. It is append-only by
contract: later balance changes must append ledger rows and may create new
snapshots, but must not replace ledger lineage.

Fields:

```text
cash_ledger_id
virtual_account_id
ledger_type
amount
currency
trade_date
event_time
source_event_type
source_event_id
source_virtual_order_id
source_virtual_trade_id
run_id
policy_version
policy_hash
rollback_scope
source_lineage_json
quality_status
created_at
```

`ledger_type` values:

```text
initial_deposit
order_freeze
order_unfreeze
virtual_buy
virtual_sell
fee
tax
adjustment
```

`amount` may be positive or negative. Fee and tax are only reserved ledger
types; 038B does not encode fee rates, tax rates, stamp duty, commission, T+1,
or fill policy.

## 4. Cash Snapshot Model

`n6_virtual_cash_snapshot` is the balance snapshot table. It summarizes ledger
state for display and replay checkpoints, but does not replace ledger lineage.

Fields:

```text
cash_snapshot_id
virtual_account_id
snapshot_time
trade_date
available_cash
frozen_cash
total_cash
currency
source_ledger_max_id
snapshot_status
run_id
policy_version
policy_hash
rollback_scope
source_lineage_json
quality_status
created_at
```

`snapshot_status` values:

```text
draft
active
superseded
failed
```

Snapshot constraints:

```text
available_cash >= 0
frozen_cash >= 0
total_cash >= 0
total_cash = available_cash + frozen_cash
source_ledger_max_id references n6_virtual_cash_ledger
one active snapshot per virtual_account_id + trade_date
```

No overdraft policy is enabled in 038B.

## 5. Shared Checks

Both tables use:

```text
virtual_account_id FK -> n6_virtual_account
currency = CNY
quality_status in passed / warning / failed
run_id <> ''
policy_version <> ''
policy_hash <> ''
rollback_scope <> ''
source_lineage_json is JSON object
```

## 6. Split Dependency

038B rollback must account for future 038C-E dependent tables:

```text
n6_virtual_position
n6_virtual_position_event
n6_virtual_order
n6_virtual_trade
n6_virtual_pnl_snapshot
```

If any of those tables exist and have rows, rollback must block.

## 7. Rollback

Rollback file:

```text
sql/038B_n6_virtual_cash_schema_rollback.sql
```

Rollback properties:

```text
RAISE EXCEPTION before first DROP
blocks if n6_virtual_cash_snapshot has rows
blocks if n6_virtual_cash_ledger has rows
blocks if future 038C-E tables exist with rows
does not use CASCADE
drops only n6_virtual_cash_snapshot and n6_virtual_cash_ledger
does not drop n6_virtual_account
does not drop 036/037 objects
does not touch N1-N6 facts/outbox
does not touch N6_UI_v1
```

## 8. Final Gate Baseline

Future final gate must provide fresh DB proof:

```text
n6_virtual_cash_ledger does not exist
n6_virtual_cash_snapshot does not exist
n6_virtual_account exists
n6_virtual_account row_count=0
038C-E future tables do not exist or row_count=0
```

## 9. Remaining Gaps

```text
no DDL executed
no live DB proof in this gate
no cash rows
no virtual account rows
no order/trade/position/pnl tables
no fee/tax/T+1 policy
no runner
```

## 10. Next Gate

Allowed next step:

```text
runtime_control 038B migration draft review
```

Still forbidden:

```text
DDL execute
database write
outbox consumption/update
worker start
N6_UI_v1/API/projection/shadow pipeline modification
delivery/push/voice/mobile/sim/position/real trade
```
