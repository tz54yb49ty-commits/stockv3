# N2-E10 Condition Pool Overwrite Execute Report

## Summary

- stage: N2-E10 condition_pool 收口 overwrite execute
- source_trade_date: `20260522`
- for_trade_date: `20260525`
- prev_trade_date: `20260522`
- execute_run_id: `condition_layer_20260522_to_20260525_20260523223042_execute`
- previous_active_run_id: `condition_layer_20260522_to_20260525_20260523191307_execute`
- overwrite_executed: true
- business_data_written: true
- migration_executed: false
- minute_kline_pulled: false
- downstream_layers_touched: false

## Inputs

```text
AGENTS.md
docs/V3_CONDITION_LAYER_DEVELOPMENT_DESIGN.md
docs/V3_LAYERED_SYSTEM_ARCHITECTURE.md
docs/N2_E9_CONDITION_POOL_OVERWRITE_PREFLIGHT_REPORT.md
```

## Backup And Snapshots

Before execute:

```text
backups/condition_layer_before_N2_E10_overwrite_20260523_222631.json
docs/N2_E10_pre_execute_preflight.json
docs/N2_E10_pre_execute_schema_gap.json
```

After execute:

```text
backups/condition_layer_after_N2_E10_overwrite_20260523_223509.json
docs/N2_E10_overwrite_execute_report.json
docs/N2_E10_post_execute_scope_audit.json
docs/N2_E10_post_execute_schema_gap.json
```

## Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_condition_layer_execute.py \
  --source-trade-date 20260522 \
  --execute \
  --overwrite \
  --user-confirmed \
  --operator codex \
  --confirmation-note N2-E10-condition-pool-scope-overwrite \
  --report-path docs/N2_E10_overwrite_execute_report.json
```

## Pre-Execute Gates

```text
schema_ready=true
migration_required=false
missing_column_count=0
type_mismatch_count=0
active_run_exists=true
blocked_by_active_run=false
overwrite=true
user_confirmed=true
execute_allowed=true
P0=0
P1=5
P2=3
will_execute_sql=false
writes_performed=false
```

## Written Rows

Actual rows written by the new execute run:

```text
common_condition_run=1
common_condition_quality_item=67
stock_monitor_target=5504
index_monitor_target=80
board_monitor_target=428
stock_condition_basis=5504
index_condition_basis=80
board_condition_basis=428
stock_condition_pool=7384
index_condition_pool=26
board_condition_pool=465
stock_minute_target_scope=7384
index_minute_target_scope=26
board_minute_target_scope=465
```

Expected row counts matched actual row counts before commit.

## Active Run Switch

Before N2-E10:

```text
condition_layer_20260522_to_20260525_20260523191307_execute: passed
```

After N2-E10:

```text
condition_layer_20260522_to_20260525_20260523191307_execute: superseded
condition_layer_20260522_to_20260525_20260523223042_execute: passed
active_passed_run_count=1
```

The new run stores:

```text
previous_active_run_id=condition_layer_20260522_to_20260525_20260523191307_execute
```

## New Active Audit

Post-execute `condition_pool` audit:

```text
P0=0
P1=0
P2=0
needs_remediation=false
```

condition_pool:

```text
index_condition_pool:
  objects=8
  rows=26
  out_of_range_rows=0

board_condition_pool:
  objects=127
  rows=465
  out_of_range_rows=0

stock_condition_pool:
  objects=2052
  rows=7384
  out_of_range_rows=0
```

minute_target_scope:

```text
index_minute_target_scope:
  rows=26
  pool_link_violations=0
  scope_source={condition_pool: 26}

board_minute_target_scope:
  rows=465
  pool_link_violations=0
  scope_source={condition_pool: 465}

stock_minute_target_scope:
  rows=7384
  pool_link_violations=0
  market_value_violations=0
  scope_source={condition_pool: 7384}
```

## Database Row Counts After Execute

Total condition-layer table row counts after retaining the superseded run:

```text
common_condition_run=2
common_condition_quality_item=129
stock_monitor_target=11008
index_monitor_target=160
board_monitor_target=856
stock_condition_basis=11008
index_condition_basis=160
board_condition_basis=856
stock_condition_pool=27630
index_condition_pool=299
board_condition_pool=2040
stock_minute_target_scope=14822
index_minute_target_scope=44
board_minute_target_scope=719
```

These totals include both the superseded run and the new active run.

## Schema Postcheck

```text
migration_required=false
missing_column_count=0
type_mismatch_count=0
not_null_risk_count=0
constraint_deferred_count=0
```

N2-E10 did not execute any migration.

## Rollback

Concrete rollback SQL:

```text
sql/N2_E10_condition_layer_overwrite_rollback.sql
```

Rollback intent:

```text
1. Delete rows for execute_run_id=condition_layer_20260522_to_20260525_20260523223042_execute.
2. Restore previous_active_run_id=condition_layer_20260522_to_20260525_20260523191307_execute to status=passed.
3. Verify exactly one passed active run remains for 20260522 -> 20260525.
```

Rollback was not executed.

## Boundary Confirmation

- Only worked inside v3 project.
- Did not touch the old system.
- Did not pull market data or minute K.
- Did not enter N3 / trigger / action / mobile / voice / sim / worker.
- Did not start services.
- Did not execute migration.
- Did write v3 development condition-layer business tables as explicitly confirmed by the user.
