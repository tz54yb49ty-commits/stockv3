# N2 Condition Layer 20260526 Execute Preflight

status = BLOCKED

```text
source_trade_date = 20260529
for_trade_date = 20260601
prev_trade_date = 20260529
schema_ready = False
active_exists = True
execute_allowed = False
blocked_reasons = ['active_run_exists', 'schema_not_migrated', 'user_confirmation_required']
writes_performed = false
will_execute_sql = false
common_event_outbox_written = false
```

## Expected Rows With Display

```json
{
  "board_condition_basis": 428,
  "board_condition_display_basis": 127,
  "board_condition_pool": 284,
  "board_minute_target_scope": 284,
  "board_monitor_target": 428,
  "common_condition_quality_item": 106,
  "common_condition_run": 1,
  "index_condition_basis": 83,
  "index_condition_display_basis": 9,
  "index_condition_pool": 21,
  "index_minute_target_scope": 21,
  "index_monitor_target": 83,
  "stock_condition_basis": 5506,
  "stock_condition_display_basis": 1871,
  "stock_condition_pool": 4106,
  "stock_minute_target_scope": 4106,
  "stock_monitor_target": 5506
}
```
