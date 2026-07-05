# N2-R4 Overwrite Execute Report

layer_role = N2_condition
status = passed

## Run

```text
new_active_run_id = condition_layer_20260522_to_20260525_20260525003855_execute
old_run_id = condition_layer_20260522_to_20260525_20260524205747_execute
old_run_status = superseded
source_trade_date = 20260522
for_trade_date = 20260525
prev_trade_date = 20260522
```

## Artifacts

- before_snapshot: `backups/N2_R4_overwrite_before_snapshot_20260525.json`
- after_snapshot: `backups/N2_R4_overwrite_after_snapshot_20260525.json`
- raw_execute_report: `docs/N2_R4_overwrite_execute_raw_report.json`
- json_report: `docs/N2_R4_overwrite_execute_report.json`
- rollback_sql: `sql/N2_R4_overwrite_rollback.sql`

## Row Counts

| Table | New run rows |
|---|---:|
| common_condition_run | 1 |
| common_condition_quality_item | 76 |
| stock_monitor_target | 5504 |
| stock_condition_basis | 5504 |
| index_monitor_target | 81 |
| index_condition_basis | 81 |
| board_monitor_target | 428 |
| board_condition_basis | 428 |
| stock_condition_pool | 4236 |
| index_condition_pool | 18 |
| board_condition_pool | 258 |
| index_minute_target_scope | 18 |
| board_minute_target_scope | 258 |
| stock_minute_target_scope | 4236 |

## Baseline Checks

| Table | rows | baseline_missing | invalid_shape | required_period_not_ready | all_period_not_ready |
|---|---:|---:|---:|---:|---:|
| stock_condition_basis | 5504 | 0 | 0 | 0 | 62 |
| index_condition_basis | 81 | 0 | 0 | 0 | 0 |
| board_condition_basis | 428 | 0 | 0 | 0 | 1 |
| stock_condition_pool | 4236 | 0 | 0 | 0 | 40 |
| index_condition_pool | 18 | 0 | 0 | 0 | 0 |
| board_condition_pool | 258 | 0 | 0 | 0 | 0 |
| stock_minute_target_scope | 4236 | 0 | 0 | 0 | 40 |
| index_minute_target_scope | 18 | 0 | 0 | 0 | 0 |
| board_minute_target_scope | 258 | 0 | 0 | 0 | 0 |

## Fixed 9 Index

| Table | present | valid_shape | ready |
|---|---:|---:|---:|
| index_condition_basis | 9/9 | 9/9 | 9/9 |
| index_condition_pool | 9/9 | 9/9 | 9/9 |
| index_minute_target_scope | 9/9 | 9/9 | 9/9 |

## Quality

```text
run_quality_P0/P1/P2 = 0/6/3
N2_R4_acceptance_P0/P1/P2 = 0/0/0
```

Non-blocking quality items are retained as warnings. They are not N2-R4 baseline blockers:

- P1 condition_basis.amount_baseline_missing: 63
- P1 condition_basis.for_trade_calendar_row_missing: missing
- P1 condition_basis.period_trigger_baseline_partial_readiness: 63
- P1 condition_basis.static_structure_partial_coverage: 4915
- P1 condition_pool.for_trade_calendar_row_missing: missing
- P1 condition_run.aggregate_p1_confirmation: 6
- P1 condition_run.for_trade_calendar_row_exists: false
- P1 minute_target_scope.for_trade_calendar_row_missing: missing
- P2 condition_basis.monitor_target_pending: None
- P2 condition_pool.source_condition_basis_id_unavailable: None
- P2 condition_run.aggregate_p2_recorded: 3
- P2 minute_target_scope.source_condition_pool_id_unavailable_in_dry_run: None

## Boundary

```text
common_event_outbox: 26652 -> 26652
overwrite_executed=true
migration_executed=false
entered_N3_N4_N5_N6=false
market_data_pulled=false
old_system_touched=false
worker_started=false
```
