# N2 Condition Layer 20260527 Execute Preflight

status = BLOCKED

```text
source_trade_date = 20260527
for_trade_date = 20260528
prev_trade_date = 20260527
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
  "board_condition_display_basis": 428,
  "board_condition_pool": 273,
  "board_minute_target_scope": 273,
  "board_monitor_target": 428,
  "common_condition_quality_item": 109,
  "common_condition_run": 1,
  "index_condition_basis": 83,
  "index_condition_display_basis": 83,
  "index_condition_pool": 22,
  "index_minute_target_scope": 22,
  "index_monitor_target": 83,
  "stock_condition_basis": 5506,
  "stock_condition_display_basis": 5506,
  "stock_condition_pool": 4307,
  "stock_minute_target_scope": 4307,
  "stock_monitor_target": 5506
}
```
