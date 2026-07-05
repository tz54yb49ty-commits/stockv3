# N2-Display Overwrite Execute Report

layer_role = N2_condition
status = EXECUTED

## Boundary

```text
writes_performed = true
will_execute_sql = true
common_event_outbox_written = false
N3_N4_N5_written = false
service_started = false
worker_started = false
old_system_touched = false
```

## Runs

```text
old_active_run_id = condition_layer_20260522_to_20260525_20260525003855_execute
new_active_run_id = condition_layer_20260522_to_20260525_20260525102249_execute
active_passed_run_count = 1
new_run_status = passed
old_run_status = superseded
```

## Row Count Validation

| Table | Expected | Actual | Result |
|---|---:|---:|---|
| common_condition_quality_item | 104 | 104 | OK |
| stock_monitor_target | 5504 | 5504 | OK |
| index_monitor_target | 81 | 81 | OK |
| board_monitor_target | 428 | 428 | OK |
| stock_condition_basis | 5504 | 5504 | OK |
| index_condition_basis | 81 | 81 | OK |
| board_condition_basis | 428 | 428 | OK |
| stock_condition_pool | 4236 | 4236 | OK |
| index_condition_pool | 18 | 18 | OK |
| board_condition_pool | 258 | 258 | OK |
| stock_minute_target_scope | 4236 | 4236 | OK |
| index_minute_target_scope | 18 | 18 | OK |
| board_minute_target_scope | 258 | 258 | OK |
| stock_condition_display_basis | 5504 | 5504 | OK |
| index_condition_display_basis | 81 | 81 | OK |
| board_condition_display_basis | 428 | 428 | OK |

## Event And Downstream Guard

```text
common_event_outbox_before = 53304
common_event_outbox_after = 53304
common_event_outbox_unchanged = true
```

| Table | Before | After | Delta |
|---|---:|---:|---:|
| common_market_data_run | 4 | 4 | 0 |
| common_market_data_subscription_candidate | 40608 | 40608 | 0 |
| common_market_data_subscription | 19692 | 19692 | 0 |
| common_market_data_pull_plan | 27 | 27 | 0 |
| common_trigger_run | 3 | 3 | 0 |
| common_trigger_state | 17768 | 17768 | 0 |
| common_trigger_match | 53304 | 53304 | 0 |
| common_action_run | 0 | 0 | 0 |
| common_action_event | 0 | 0 | 0 |
| common_position_state | 0 | 0 | 0 |

## Quality Items

| layer_scope | rows |
|---|---:|
| condition_basis | 22 |
| condition_display_basis | 28 |
| condition_pool | 25 |
| condition_run | 10 |
| minute_target_scope | 19 |

## Checks

```json
{
  "active_passed_run_count_equals_1": true,
  "new_run_status_passed": true,
  "old_run_status_superseded": true,
  "row_counts_match_preflight": true,
  "common_event_outbox_unchanged": true,
  "n3_n4_n5_row_counts_unchanged": true
}
```

## Artifacts

- before_snapshot: `backups/N2_DISPLAY_OVERWRITE_before_snapshot_20260525102022.json`
- after_snapshot: `backups/N2_DISPLAY_OVERWRITE_after_snapshot_20260525102415.json`
- raw_execute_report: `docs/N2_DISPLAY_OVERWRITE_execute_raw_report.json`
- json_report: `docs/N2_DISPLAY_OVERWRITE_execute_report.json`
- rollback_sql: `sql/N2_DISPLAY_overwrite_rollback.sql`

## Rollback Plan

如需回滚，先人工复核 `sql/N2_DISPLAY_overwrite_rollback.sql`，再删除新 run 的 display/scope/pool/basis/monitor/quality/run 行，并恢复旧 run 为 `passed`。回滚 SQL 不触碰 `common_event_outbox`、N1、N3、N4、N5、N6。

## Stop Point

本阶段只完成 N2-Display overwrite execute。未重建 N3 subscription，未进入 N3/N4/N5/N6。
