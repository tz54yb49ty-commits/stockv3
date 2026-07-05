# N6 Phase 3 038B Virtual Cash Static Tests

Status: STATIC_TESTS_PASS

Layer role: N6_user

Date: 2026-06-05

Static validation targets for the 038B migration draft. These tests do not
execute DDL or write the database.

## 1. JSON Parse

Required JSON files:

```text
docs/N6_PHASE3_038B_VIRTUAL_CASH_MIGRATION_DRAFT.json
docs/N6_PHASE3_038B_VIRTUAL_CASH_STATIC_TESTS.json
docs/N6_PHASE3_038B_VIRTUAL_CASH_TRACEABILITY.json
```

## 2. Migration Static Scan

Expected:

```text
CREATE TABLE IF NOT EXISTS count = 2
created tables = n6_virtual_cash_ledger, n6_virtual_cash_snapshot
CREATE INDEX IF NOT EXISTS only
no INSERT / UPDATE / DELETE / TRUNCATE / COPY
no ALTER old table
no DROP
no GRANT
no CASCADE
no 038C-E table creation
no N1-N6 fact/outbox references
no broker / real trade fields
```

## 3. Cash Ledger Proof

Expected SQL evidence:

```text
n6_virtual_cash_ledger has virtual_account_id FK to n6_virtual_account
ledger_type allows initial_deposit/order_freeze/order_unfreeze/virtual_buy/virtual_sell/fee/tax/adjustment
amount has no nonnegative CHECK, so positive and negative ledger rows are possible
source_virtual_order_id and source_virtual_trade_id are nullable columns without future table FK
no updated_at column on ledger
```

## 4. Cash Snapshot Proof

Expected SQL evidence:

```text
n6_virtual_cash_snapshot has virtual_account_id FK to n6_virtual_account
available_cash >= 0
frozen_cash >= 0
total_cash >= 0
total_cash = available_cash + frozen_cash
source_ledger_max_id references n6_virtual_cash_ledger
snapshot_status allows draft/active/superseded/failed
one active snapshot per virtual_account_id + trade_date
```

## 5. Deferred Policy Proof

Expected:

```text
no fee_rate / tax_rate / stamp_duty / commission fields
no T+1 / t_plus_one field
no broker fields
no real trade fields
fee/tax are only ledger_type reserved values
```

## 6. Rollback Static Scan

Expected:

```text
RAISE EXCEPTION before first DROP
checks n6_virtual_cash_snapshot row_count
checks n6_virtual_cash_ledger row_count
checks future 038C-E table row_count using to_regclass
no CASCADE
drops only n6_virtual_cash_snapshot and n6_virtual_cash_ledger
does not drop n6_virtual_account
does not drop 036/037 objects
does not touch N1-N6 facts/outbox
```
