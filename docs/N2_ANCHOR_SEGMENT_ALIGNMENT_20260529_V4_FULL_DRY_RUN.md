# N2 Anchor Segment Alignment 20260529 V4 Full Dry-Run

Status: FULL_DRY_RUN_PASS

```text
source_trade_date = 20260529
for_trade_date = 20260601
prev_trade_date = 20260529
target_run_id = condition_layer_20260529_source_20260529_v4
previous_active_run_id = condition_layer_20260529_source_20260529_v3
will_execute_sql = false
writes_performed = false
minute_kline_pulled = false
downstream_layers_touched = false
```

## Expected Rows

```json
{
  "common_condition_run": 1,
  "common_condition_quality_item": 106,
  "stock_monitor_target": 5506,
  "index_monitor_target": 83,
  "board_monitor_target": 428,
  "stock_condition_basis": 5506,
  "index_condition_basis": 83,
  "board_condition_basis": 428,
  "stock_condition_pool": 4106,
  "index_condition_pool": 187,
  "board_condition_pool": 942,
  "index_minute_target_scope": 187,
  "board_minute_target_scope": 942,
  "stock_minute_target_scope": 4087,
  "stock_condition_display_basis": 1862,
  "index_condition_display_basis": 83,
  "board_condition_display_basis": 428
}
```

## Golden Proof

- 000600: 12.93 / segment 20260518 -> 20260529
- 000543: 10.82
- 000027: 8.45

```text
P0/P1/P2 = 0/6/3
target_price_changed_count_vs_active_run = 3803
```
