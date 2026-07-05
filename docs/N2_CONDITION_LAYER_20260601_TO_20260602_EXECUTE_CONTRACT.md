# N2 Condition Layer 20260526 Execute Contract

status = DESIGN_PASS

```text
source_trade_date = 20260601
for_trade_date = 20260602
prev_trade_date = 20260601
execute_run_id_template = condition_layer_{source_trade_date}_to_{for_trade_date}_{yyyymmddHHMMSS}_execute
run_id_suggestion = condition_layer_20260601_source_20260601_v1
execute_request_allowed = False
writes_performed = false
will_execute_sql = false
common_event_outbox_written = false
```

## Expected Rows With Display

```json
{
  "board_condition_basis": 428,
  "board_condition_display_basis": 127,
  "board_condition_pool": 307,
  "board_minute_target_scope": 307,
  "board_monitor_target": 428,
  "common_condition_quality_item": 106,
  "common_condition_run": 1,
  "index_condition_basis": 83,
  "index_condition_display_basis": 9,
  "index_condition_pool": 26,
  "index_minute_target_scope": 26,
  "index_monitor_target": 83,
  "stock_condition_basis": 5508,
  "stock_condition_display_basis": 1983,
  "stock_condition_pool": 4732,
  "stock_minute_target_scope": 4732,
  "stock_monitor_target": 5508
}
```
