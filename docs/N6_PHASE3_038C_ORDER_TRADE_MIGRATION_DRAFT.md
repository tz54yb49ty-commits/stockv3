# N6 Phase 3 038C Order/Trade Migration Draft

Status: DRAFT_PASS

Layer role: N6_user

Date: 2026-06-05

This gate drafts the split 038C migration for virtual order and virtual trade
only. It does not execute DDL, write database rows, run a migration, consume or
update outbox rows, start workers, modify N6_UI_v1, modify existing APIs,
modify projection/shadow pipelines, deliver notifications, push to voice/mobile,
run sim, create positions, or place real trades.

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

038C files:

```text
sql/038C_n6_virtual_order_trade_schema.sql
sql/038C_n6_virtual_order_trade_schema_rollback.sql
```

## 2. Scope

038C creates only:

```text
n6_virtual_order
n6_virtual_trade
```

038C does not create:

```text
n6_virtual_position
n6_virtual_position_event
n6_virtual_pnl_snapshot
```

038C does not create AI, strategy, watchlist, account linkage, delivery, push,
voice, mobile, sim, position, PnL, or real-trade objects.

## 3. Virtual Order Model

`n6_virtual_order` records a virtual order lifecycle request. It is not a
broker order and does not authorize real execution.

Fields:

```text
virtual_order_id
virtual_account_id
principal_id
principal_type
asset_kind
identity_key
signal_type
order_side
order_type
order_status
requested_quantity
requested_price
estimated_fee_amount
estimated_tax_amount
fee_policy_version
tax_policy_version
execution_policy_version
execution_policy_hash
market_rule_set
source_action_event_id
source_signal_projection_id
run_id
policy_version
policy_hash
rollback_scope
source_lineage_json
quality_status
created_at
updated_at
```

`order_status` values:

```text
draft
staged_virtual
accepted_virtual
partially_filled_virtual
filled_virtual
cancelled_virtual
rejected_virtual
expired_virtual
```

`source_signal_projection_id` and `source_action_event_id` are nullable lineage
identifiers only. 038C does not add FK dependencies to projection rows or N5
outbox rows.

## 4. Virtual Trade Model

`n6_virtual_trade` records deterministic virtual fill results only. It does not
mean a broker fill, placed order, or real成交.

Fields:

```text
virtual_trade_id
virtual_order_id
virtual_account_id
principal_id
principal_type
asset_kind
identity_key
trade_side
filled_quantity
filled_price
gross_amount
commission_amount
stamp_tax_amount
transfer_fee_amount
total_fee_amount
net_amount
fill_policy_version
fill_policy_hash
replay_deterministic_seed
trade_status
trade_time
source_lineage_json
run_id
policy_version
policy_hash
rollback_scope
quality_status
created_at
```

`trade_status` values:

```text
filled_virtual
reversed_virtual
cancelled_virtual
failed_virtual
```

Determinism fields:

```text
fill_policy_version
fill_policy_hash
replay_deterministic_seed
```

## 5. FK / Dependency

038C dependencies:

```text
n6_virtual_order.virtual_account_id -> n6_virtual_account
n6_virtual_order(principal_id, principal_type) -> n6_principal
n6_virtual_trade.virtual_order_id -> n6_virtual_order
n6_virtual_trade.virtual_account_id -> n6_virtual_account
n6_virtual_trade(principal_id, principal_type) -> n6_principal
```

038C does not depend on:

```text
n6_virtual_position
n6_virtual_position_event
n6_virtual_pnl_snapshot
```

## 6. Fee / Tax / T+1 Boundary

038C stores amount and policy fields only:

```text
estimated_fee_amount
estimated_tax_amount
commission_amount
stamp_tax_amount
transfer_fee_amount
total_fee_amount
fee_policy_version
tax_policy_version
execution_policy_version
execution_policy_hash
fill_policy_version
fill_policy_hash
market_rule_set
```

038C does not encode fee rates, tax rates, stamp duty rules, commission rules,
transfer-fee rules, T+1 rules, or fill matching rules. Those rules require a
future execution policy / fee policy gate.

## 7. Safety Boundary

Forbidden in 038C:

```text
broker_order_id
real_trade_id
real_execution_id
broker session
broker API
common_position writes
user_sim table writes
N5 outbox status updates
```

## 8. Rollback

Rollback file:

```text
sql/038C_n6_virtual_order_trade_schema_rollback.sql
```

Rollback properties:

```text
RAISE EXCEPTION before first DROP
blocks if n6_virtual_trade has rows
blocks if n6_virtual_order has rows
blocks if future 038D-E tables exist with rows
does not use CASCADE
drops only n6_virtual_trade and n6_virtual_order
does not drop 038A/038B/036/037 objects
does not touch N1-N6 facts/outbox
does not touch N6_UI_v1
```

## 9. Final Gate Baseline

Future final gate must provide fresh DB proof:

```text
n6_virtual_order does not exist
n6_virtual_trade does not exist
n6_virtual_account exists and row_count=0
n6_virtual_cash_ledger exists and row_count=0
n6_virtual_cash_snapshot exists and row_count=0
038D-E future tables do not exist or row_count=0
```

## 10. Remaining Gaps

```text
no DDL executed
no live DB proof in this gate
no order rows
no trade rows
no position/PnL tables
no fee/tax/T+1 policy
no execution runner
```

## 11. Next Gate

Allowed next step:

```text
runtime_control 038C migration draft review
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
