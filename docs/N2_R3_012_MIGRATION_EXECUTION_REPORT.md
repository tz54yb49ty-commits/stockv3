# N2-R3 012 Migration Execution Report

Date: 2026-05-24T20:35:45
Layer: N2_condition
Mode: execute_012_additive_migration_only
Status: passed

## Summary

```text
sql_path = sql/012_condition_static_reference_period_full_chain_migration.sql
migration_executed = true
overwrite_executed = false
condition_business_rows_written = false
common_event_outbox_written = false
```

## Schema Gap

```text
before missing_column_count = 15
after missing_column_count = 0
after type_mismatch_count = 0
after migration_required = false
```

## Row Count Comparison

| table | before | after | unchanged |
|---|---:|---:|---|
| `stock_condition_basis` | 22016 | 22016 | true |
| `index_condition_basis` | 322 | 322 | true |
| `board_condition_basis` | 1712 | 1712 | true |
| `stock_condition_pool` | 36102 | 36102 | true |
| `index_condition_pool` | 335 | 335 | true |
| `board_condition_pool` | 2556 | 2556 | true |
| `stock_minute_target_scope` | 23294 | 23294 | true |
| `index_minute_target_scope` | 80 | 80 | true |
| `board_minute_target_scope` | 1235 | 1235 | true |
| `common_condition_run` | 4 | 4 | true |
| `common_condition_quality_item` | 269 | 269 | true |
| `common_event_outbox` | 26652 | 26652 | true |

## Active Run

```text
active_condition_run_unchanged = true
active_condition_run_count_before = 1
active_condition_run_count_after = 1
active_run_id = condition_layer_20260522_to_20260525_20260524181321_execute
active_status = passed
```

## 9-Table Column Presence

| table | up_sell_reference_period | down_buy_reference_period | clear_sell_ref_period |
|---|---|---|---|
| `stock_condition_basis` | true | true | true |
| `index_condition_basis` | true | true | true |
| `board_condition_basis` | true | true | true |
| `stock_condition_pool` | true | true | true |
| `index_condition_pool` | true | true | true |
| `board_condition_pool` | true | true | true |
| `stock_minute_target_scope` | true | true | true |
| `index_minute_target_scope` | true | true | true |
| `board_minute_target_scope` | true | true | true |

## Checks

```text
missing_column_count_zero = true
type_mismatch_count_zero = true
required_columns_present_all_9_tables = true
condition_basis_pool_scope_row_counts_unchanged = true
common_condition_run_row_count_unchanged = true
common_condition_quality_item_row_count_unchanged = true
common_event_outbox_unchanged = true
active_condition_run_unchanged = true
no_condition_business_rows_written = true
overwrite_executed = false
entered_N3_N4_N5_N6 = false
P0/P1/P2 = 0/0/0
```

## Boundary

```text
old_system_touched: no
external_market_api_called: no
minute_k_pulled: no
worker_started: no
entered_N3_N4_N5_N6: no
common_event_outbox_written: no
n1_fact_modified: no
condition_overwrite_executed: no
```

## Rollback Note

012 is additive nullable schema only. Rollback is manual DROP COLUMN after explicit confirmation; no rollback SQL was executed.

## Validation

```text
python3 -m compileall scripts src tests: passed
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_condition_static_reference_period_chain.py': passed, 5 tests
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_condition_schema_migration_readiness.py': passed, 5 tests
git diff --check: passed
```

## Next Step

Stop here. Do not overwrite active condition run unless the user explicitly confirms the next N2-R3 overwrite stage.
