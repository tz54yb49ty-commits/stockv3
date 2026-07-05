# N6 Phase 3 038C Order/Trade Static Tests

Status: STATIC_TESTS_PASS

Layer role: N6_user

Date: 2026-06-05

Static validation targets for the 038C migration draft. These tests do not
execute DDL or write the database.

## 1. JSON Parse

Required JSON files:

```text
docs/N6_PHASE3_038C_ORDER_TRADE_MIGRATION_DRAFT.json
docs/N6_PHASE3_038C_ORDER_TRADE_STATIC_TESTS.json
docs/N6_PHASE3_038C_ORDER_TRADE_TRACEABILITY.json
```

## 2. Migration Static Scan

Expected:

```text
CREATE TABLE IF NOT EXISTS count = 2
created tables = n6_virtual_order, n6_virtual_trade
CREATE INDEX IF NOT EXISTS only
no INSERT / UPDATE / DELETE / TRUNCATE / COPY
no ALTER old table
no DROP
no GRANT
no CASCADE
no 038D-E table creation
no N1-N6 fact/outbox references
no broker_order_id / real_trade_id / real_execution_id fields
```

## 3. Order Proof

Expected SQL evidence:

```text
n6_virtual_order has virtual_account_id FK to n6_virtual_account
n6_virtual_order has principal composite FK to n6_principal
order_side allows buy/sell
order_status values are virtual-only lifecycle values
requested_quantity > 0
requested_price nullable and nonnegative when present
estimated_fee_amount and estimated_tax_amount are nonnegative fields only
source_action_event_id and source_signal_projection_id are nullable lineage ids
```

## 4. Trade Proof

Expected SQL evidence:

```text
n6_virtual_trade has virtual_order_id FK to n6_virtual_order
n6_virtual_trade has virtual_account_id FK to n6_virtual_account
n6_virtual_trade has principal composite FK to n6_principal
trade_side allows buy/sell
filled_quantity > 0
filled_price / gross_amount / commission_amount / stamp_tax_amount / transfer_fee_amount / total_fee_amount / net_amount are nonnegative
total_fee_amount = commission_amount + stamp_tax_amount + transfer_fee_amount
fill_policy_version / fill_policy_hash / replay_deterministic_seed are required
```

## 5. Deferred Policy Proof

Expected:

```text
no fee_rate / tax_rate / stamp_duty_rate / commission_rate / transfer_fee_rate fields
no T+1 / t_plus_one field
no broker fields
no real trade fields
no common_position references
no user_sim references
fee/tax/commission/transfer amounts are value fields only
```

## 6. Rollback Static Scan

Expected:

```text
RAISE EXCEPTION before first DROP
checks n6_virtual_trade row_count
checks n6_virtual_order row_count
checks future 038D-E table row_count using to_regclass
no CASCADE
drops only n6_virtual_trade and n6_virtual_order
does not drop 038A/038B/036/037 objects
does not touch N1-N6 facts/outbox
```
