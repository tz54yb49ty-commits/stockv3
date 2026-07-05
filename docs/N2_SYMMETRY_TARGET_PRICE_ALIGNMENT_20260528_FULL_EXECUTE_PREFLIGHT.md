# N2 Condition Layer 20260526 Execute Preflight

status = BLOCKED

```text
source_trade_date = 20260528
for_trade_date = 20260529
prev_trade_date = 20260528
schema_ready = True
active_exists = True
execute_allowed = False
blocked_reasons = ['active_run_exists']
writes_performed = false
will_execute_sql = false
common_event_outbox_written = false
```

## Expected Rows With Display

```json
{
  "board_condition_basis": 428,
  "board_condition_display_basis": 127,
  "board_condition_pool": 263,
  "board_minute_target_scope": 263,
  "board_monitor_target": 428,
  "common_condition_quality_item": 103,
  "common_condition_run": 1,
  "index_condition_basis": 83,
  "index_condition_display_basis": 9,
  "index_condition_pool": 18,
  "index_minute_target_scope": 18,
  "index_monitor_target": 83,
  "stock_condition_basis": 5506,
  "stock_condition_display_basis": 2021,
  "stock_condition_pool": 4271,
  "stock_minute_target_scope": 4271,
  "stock_monitor_target": 5506
}
```
