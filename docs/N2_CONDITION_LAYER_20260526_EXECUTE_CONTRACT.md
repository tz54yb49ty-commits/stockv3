# N2 Condition Layer 20260526 Execute Contract

status = DESIGN_PASS

```text
source_trade_date = 20260526
for_trade_date = 20260527
prev_trade_date = 20260526
execute_run_id_template = condition_layer_{source_trade_date}_to_{for_trade_date}_{yyyymmddHHMMSS}_execute
run_id_suggestion = condition_layer_20260526_source_20260526_v1
execute_request_allowed = True
writes_performed = false
will_execute_sql = false
common_event_outbox_written = false
```

## Expected Rows With Display

```json
{
  "board_condition_basis": 428,
  "board_condition_display_basis": 428,
  "board_condition_pool": 264,
  "board_minute_target_scope": 264,
  "board_monitor_target": 428,
  "common_condition_quality_item": 110,
  "common_condition_run": 1,
  "index_condition_basis": 9,
  "index_condition_display_basis": 9,
  "index_condition_pool": 19,
  "index_minute_target_scope": 19,
  "index_monitor_target": 9,
  "stock_condition_basis": 5504,
  "stock_condition_display_basis": 5504,
  "stock_condition_pool": 4291,
  "stock_minute_target_scope": 4291,
  "stock_monitor_target": 5504
}
```
