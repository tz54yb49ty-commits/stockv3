# N2 Condition Layer 20260526 Execute Contract

status = DESIGN_PASS

```text
source_trade_date = 20260602
for_trade_date = 20260603
prev_trade_date = 20260602
execute_run_id_template = condition_layer_{source_trade_date}_to_{for_trade_date}_{yyyymmddHHMMSS}_execute
run_id_suggestion = condition_layer_20260602_source_20260602_v1
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
  "board_condition_pool": 890,
  "board_minute_target_scope": 890,
  "board_monitor_target": 428,
  "common_condition_quality_item": 109,
  "common_condition_run": 1,
  "index_condition_basis": 83,
  "index_condition_display_basis": 83,
  "index_condition_pool": 168,
  "index_minute_target_scope": 168,
  "index_monitor_target": 83,
  "stock_condition_basis": 5507,
  "stock_condition_display_basis": 1963,
  "stock_condition_pool": 4182,
  "stock_minute_target_scope": 4164,
  "stock_monitor_target": 5507
}
```
