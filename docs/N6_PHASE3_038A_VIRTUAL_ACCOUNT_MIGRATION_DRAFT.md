# N6 Phase 3 038A Virtual Account Migration Draft

Status: DRAFT_PASS

Layer role: N6_user

Date: 2026-06-05

This gate drafts the split 038A migration for `n6_virtual_account` only. It
does not execute DDL, write database rows, run a migration, consume or update
outbox rows, start workers, modify N6_UI_v1, modify existing APIs, modify
projection/shadow pipelines, deliver notifications, push to voice/mobile, run
sim, create positions, or place real trades.

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
runtime_control APPROVED_WITH_CHANGES review
```

038A files:

```text
sql/038A_n6_virtual_account_schema.sql
sql/038A_n6_virtual_account_schema_rollback.sql
```

## 2. Scope

038A creates only:

```text
n6_virtual_account
```

038A does not create:

```text
n6_virtual_cash_ledger
n6_virtual_cash_snapshot
n6_virtual_position
n6_virtual_position_event
n6_virtual_order
n6_virtual_trade
n6_virtual_pnl_snapshot
```

## 3. Table Summary

`n6_virtual_account` fields:

```text
virtual_account_id
principal_id
principal_type
account_name
virtual_account_status
base_currency
initial_cash
current_cash_snapshot_id
run_id
policy_version
policy_hash
rollback_scope
source_lineage_json
quality_status
created_at
updated_at
```

`account_id` is intentionally not included in 038A. Account linkage to
`n6_principal_account.account_id` is deferred to a later account linkage gate.

## 4. Principal Ownership

The table uses a composite FK:

```sql
FOREIGN KEY (principal_id, principal_type)
REFERENCES n6_principal(principal_id, principal_type)
```

Allowed `principal_type` values:

```text
admin
human_user
ai_user
```

Forbidden:

```text
system
```

This prevents a Phase 2 system principal from creating a virtual account unless
a future explicit gate changes policy and schema.

## 5. Checks

`virtual_account_status`:

```text
draft
active
suspended
closed
```

`base_currency`:

```text
CNY
```

`quality_status`:

```text
passed
warning
failed
```

Additional checks:

```text
account_name <> ''
initial_cash >= 0
run_id <> ''
policy_version <> ''
policy_hash <> ''
rollback_scope <> ''
source_lineage_json is JSON object
```

## 6. Split Dependency

038A rollback must account for future 038B-E dependent tables:

```text
n6_virtual_cash_ledger
n6_virtual_cash_snapshot
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
sql/038A_n6_virtual_account_schema_rollback.sql
```

Rollback properties:

```text
RAISE EXCEPTION before first DROP
blocks if n6_virtual_account has rows
blocks if future 038B-E tables exist with rows
does not use CASCADE
drops only n6_virtual_account
does not drop 036/037 objects
does not touch N1-N6 facts/outbox
does not touch N6_UI_v1
```

## 8. Final Gate Baseline

Future final gate must provide fresh DB proof:

```text
n6_virtual_account does not exist
038B-E future tables do not exist or row_count=0
036 n6_principal exists
Phase 2 admin/system principals exist
037 readonly permission still passed
```

## 9. Remaining Gaps

```text
no DDL executed
no live DB proof in this gate
no virtual_account rows
no account_id linkage
no cash/order/trade/position/pnl tables
no runner
```

## 10. Next Gate

Allowed next step:

```text
runtime_control 038A migration draft review
```

Still forbidden:

```text
DDL execute
database write
outbox consumption/update
worker
delivery/push/voice/mobile/sim/position/real trade
```
