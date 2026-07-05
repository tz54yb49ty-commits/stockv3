# N2 Condition Layer 20260526 Execute Preflight

status = BLOCKED

```text
source_trade_date = 20260615
for_trade_date = 20260616
prev_trade_date = 20260615
schema_ready = True
active_exists = True
execute_allowed = False
blocked_reasons = ['active_run_exists', 'user_confirmation_required']
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
