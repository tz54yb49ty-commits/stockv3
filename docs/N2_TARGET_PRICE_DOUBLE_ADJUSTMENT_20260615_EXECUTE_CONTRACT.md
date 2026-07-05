# N2 Condition Layer 20260526 Execute Contract

status = DESIGN_PASS

```text
source_trade_date = 20260615
for_trade_date = 20260616
prev_trade_date = 20260615
execute_run_id_template = condition_layer_{source_trade_date}_to_{for_trade_date}_{yyyymmddHHMMSS}_execute
run_id_suggestion = condition_layer_20260615_source_20260615_for_20260616_v3
execute_request_allowed = False
writes_performed = false
will_execute_sql = false
common_event_outbox_written = false
```

## Expected Rows With Display

```json
{
  "board_condition_basis": 427,
  "board_condition_display_basis": 127,
  "board_condition_pool": 307,
  "board_minute_target_scope": 307,
  "board_monitor_target": 427,
  "common_condition_quality_item": 103,
  "common_condition_run": 1,
  "index_condition_basis": 83,
  "index_condition_display_basis": 83,
  "index_condition_pool": 183,
  "index_minute_target_scope": 183,
  "index_monitor_target": 83,
  "stock_condition_basis": 5504,
  "stock_condition_display_basis": 1822,
  "stock_condition_pool": 4215,
  "stock_minute_target_scope": 4194,
  "stock_monitor_target": 5504
}
```
