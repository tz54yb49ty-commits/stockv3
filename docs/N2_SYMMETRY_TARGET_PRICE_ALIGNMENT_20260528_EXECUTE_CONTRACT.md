# N2 Condition Layer 20260526 Execute Contract

status = DESIGN_PASS

```text
source_trade_date = 20260528
for_trade_date = 20260529
prev_trade_date = 20260528
execute_run_id_template = condition_layer_{source_trade_date}_to_{for_trade_date}_{yyyymmddHHMMSS}_execute
run_id_suggestion = condition_layer_20260528_source_20260528_target_alignment_dry_run
execute_request_allowed = True
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
