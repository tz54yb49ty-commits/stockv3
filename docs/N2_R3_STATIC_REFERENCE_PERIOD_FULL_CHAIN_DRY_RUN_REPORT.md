# N2-R3 Static Reference Period Full Chain Dry-Run Report

Date: 2026-05-24T20:28:26
Layer: N2_condition
Mode: migration_review_and_full_chain_dry_run
Status: passed

## Date Context

```text
source_trade_date = 20260522
for_trade_date = 20260525
prev_trade_date = 20260522
active index_daily = index_daily_20260522_v4
```

## Migration Review

```text
migration_sql = sql/012_condition_static_reference_period_full_chain_migration.sql
migration_safe_to_apply = true
missing_column_count = 15
add_column_count = 27
additive_only = true
nullable_only = true
disallowed_hits = []
will_execute_sql = false
migration_performed = false
```

Missing columns by current DB schema:

- `board_condition_pool`: up_sell_reference_period, down_buy_reference_period, clear_sell_ref_period
- `board_minute_target_scope`: up_sell_reference_period, down_buy_reference_period, clear_sell_ref_period
- `index_condition_pool`: up_sell_reference_period, down_buy_reference_period, clear_sell_ref_period
- `index_minute_target_scope`: up_sell_reference_period, down_buy_reference_period, clear_sell_ref_period
- `stock_minute_target_scope`: up_sell_reference_period, down_buy_reference_period, clear_sell_ref_period


## Row Counts

| stage | stock | index | board |
|---|---:|---:|---:|
| condition_basis | 5504 | 81 | 428 |
| condition_pool | 4236 | 18 | 258 |
| minute_target_scope | 4236 | 18 | 258 |

## Reference Period Validation

Combined:

```text
up_sell_reference_period missing = 0
down_buy_reference_period missing = 0
clear_sell_ref_period missing = 0
clear_sell_ref_period != up_sell_reference_period = 0
invalid_reference_period = 0
```

| table | rows | up missing | down missing | clear missing | alias mismatch | invalid |
|---|---:|---:|---:|---:|---:|---:|
| `stock_condition_basis` | 5504 | 0 | 0 | 0 | 0 | 0 |
| `index_condition_basis` | 81 | 0 | 0 | 0 | 0 | 0 |
| `board_condition_basis` | 428 | 0 | 0 | 0 | 0 | 0 |
| `stock_condition_pool` | 4236 | 0 | 0 | 0 | 0 | 0 |
| `index_condition_pool` | 18 | 0 | 0 | 0 | 0 | 0 |
| `board_condition_pool` | 258 | 0 | 0 | 0 | 0 | 0 |
| `stock_minute_target_scope` | 4236 | 0 | 0 | 0 | 0 | 0 |
| `index_minute_target_scope` | 18 | 0 | 0 | 0 | 0 | 0 |
| `board_minute_target_scope` | 258 | 0 | 0 | 0 | 0 | 0 |


## Quality

```text
basis P0/P1/P2 = 0/3/1
pool P0/P1/P2 = 0/1/1
scope P0/P1/P2 = 0/1/1
combined P0/P1/P2 = 0/5/3
```

The remaining P1/P2 warnings are inherited dry-run warnings. N2-R3 reference-period chain validation has no P0 blocker.

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

Stop here. Execute `sql/012_condition_static_reference_period_full_chain_migration.sql` only after explicit user confirmation.
