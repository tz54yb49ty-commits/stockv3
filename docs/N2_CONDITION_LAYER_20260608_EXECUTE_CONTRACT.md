# N2 Condition Layer 20260526 Execute Contract

status = DESIGN_PASS

```text
source_trade_date = 20260605
for_trade_date = 20260608
prev_trade_date = 20260605
execute_run_id_template = condition_layer_{source_trade_date}_to_{for_trade_date}_{yyyymmddHHMMSS}_execute
run_id_suggestion = condition_layer_20260605_to_20260608_20260608013900_execute
execute_request_allowed = False
writes_performed = false
will_execute_sql = false
common_event_outbox_written = false
```

## Expected Rows With Display

```json
{
  "board_condition_basis": 428,
  "board_condition_display_basis": 428,
  "board_condition_pool": 923,
  "board_minute_target_scope": 923,
  "board_monitor_target": 428,
  "common_condition_quality_item": 106,
  "common_condition_run": 1,
  "index_condition_basis": 83,
  "index_condition_display_basis": 9,
  "index_condition_pool": 24,
  "index_minute_target_scope": 24,
  "index_monitor_target": 83,
  "stock_condition_basis": 5514,
  "stock_condition_display_basis": 1945,
  "stock_condition_pool": 4268,
  "stock_minute_target_scope": 4241,
  "stock_monitor_target": 5514
}
```
