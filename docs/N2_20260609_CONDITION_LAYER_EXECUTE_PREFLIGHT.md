# N2 Condition Layer 20260526 Execute Preflight

status = BLOCKED

```text
source_trade_date = 20260608
for_trade_date = 20260609
prev_trade_date = 20260608
schema_ready = True
active_exists = False
execute_allowed = False
blocked_reasons = ['user_confirmation_required']
writes_performed = false
will_execute_sql = false
common_event_outbox_written = false
```

## Expected Rows With Display

```json
{
  "board_condition_basis": 428,
  "board_condition_display_basis": 127,
  "board_condition_pool": 265,
  "board_minute_target_scope": 265,
  "board_monitor_target": 428,
  "common_condition_quality_item": 106,
  "common_condition_run": 1,
  "index_condition_basis": 83,
  "index_condition_display_basis": 83,
  "index_condition_pool": 216,
  "index_minute_target_scope": 216,
  "index_monitor_target": 83,
  "stock_condition_basis": 5514,
  "stock_condition_display_basis": 1880,
  "stock_condition_pool": 4063,
  "stock_minute_target_scope": 4043,
  "stock_monitor_target": 5514
}
```
