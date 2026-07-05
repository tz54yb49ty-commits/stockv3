# N2-R3 Static Reference Period Full Chain Migration Review

Date: 2026-05-24T20:28:46
Layer: N2_condition
Migration: `sql/012_condition_static_reference_period_full_chain_migration.sql`
Status: safe_to_apply_after_confirmation

## Summary

```text
migration_safe_to_apply = true
additive_only = true
nullable_only = true
no_drop = true
no_backfill = true
no_not_null = true
no_check_or_fk = true
user_confirmation_required = true
will_execute_sql = false
migration_performed = false
```

## Current Schema Gap

```text
missing_tables = []
missing_column_count = 15
type_mismatch_count = 0
not_null_risk_count = 10
constraint_deferred_count = 15
```

Missing columns by table:

- `board_condition_pool`: up_sell_reference_period, down_buy_reference_period, clear_sell_ref_period
- `board_minute_target_scope`: up_sell_reference_period, down_buy_reference_period, clear_sell_ref_period
- `index_condition_pool`: up_sell_reference_period, down_buy_reference_period, clear_sell_ref_period
- `index_minute_target_scope`: up_sell_reference_period, down_buy_reference_period, clear_sell_ref_period
- `stock_minute_target_scope`: up_sell_reference_period, down_buy_reference_period, clear_sell_ref_period


## SQL Review

```text
statement_count = 11
add_column_count = 27
disallowed_hits = []
```

The 012 draft only uses `ADD COLUMN IF NOT EXISTS` nullable `TEXT` columns. It does not update, insert, delete, overwrite, add constraints, or backfill existing rows.

## Rollback Note

Because this migration is additive and nullable, rollback is manual-only. If rollback is explicitly required before downstream consumption, drop the added columns from:

```text
stock/index/board_condition_basis
stock/index/board_condition_pool
stock/index/board_minute_target_scope
```

Do not run rollback automatically; wait for explicit user confirmation.

## Boundary

```text
old_system_touched: no
external_market_api_called: no
minute_k_pulled: no
worker_started: no
entered_N3_N4_N5_N6: no
common_event_outbox_written: no
n1_fact_modified: no
migration_executed: no
overwrite_executed: no
```

## Next Step

Stop here. Execute 012 only after explicit user confirmation.
