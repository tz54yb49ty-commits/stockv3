# N2 20260611 Condition Layer Execute Report

Result: `EXECUTE_PASS`

- run_id: `condition_layer_20260610_source_20260610_for_20260611_v1`
- source_trade_date: `20260610`
- for_trade_date: `20260611`
- status: `passed_active`
- P0/P1/P2: `0/6/3`

## Row Counts

```json
{
  "expected": {
    "common_condition_run": 1,
    "common_condition_quality_item": 106,
    "stock_monitor_target": 5510,
    "index_monitor_target": 83,
    "board_monitor_target": 428,
    "stock_condition_basis": 5510,
    "index_condition_basis": 83,
    "board_condition_basis": 428,
    "stock_condition_pool": 4046,
    "index_condition_pool": 185,
    "board_condition_pool": 268,
    "index_minute_target_scope": 185,
    "board_minute_target_scope": 268,
    "stock_minute_target_scope": 4027,
    "stock_condition_display_basis": 1890,
    "index_condition_display_basis": 83,
    "board_condition_display_basis": 127
  },
  "actual": {
    "common_condition_run": 1,
    "common_condition_quality_item": 106,
    "stock_monitor_target": 5510,
    "stock_condition_basis": 5510,
    "index_monitor_target": 83,
    "index_condition_basis": 83,
    "board_monitor_target": 428,
    "board_condition_basis": 428,
    "stock_condition_pool": 4046,
    "index_condition_pool": 185,
    "board_condition_pool": 268,
    "index_minute_target_scope": 185,
    "board_minute_target_scope": 268,
    "stock_minute_target_scope": 4027,
    "stock_condition_display_basis": 1890,
    "index_condition_display_basis": 83,
    "board_condition_display_basis": 127
  },
  "matched": true
}
```

## Boundary

```json
{
  "transaction_read_only": "on",
  "refs": {
    "common_event_outbox": 0,
    "common_event_inbox": 0,
    "common_event_consumer_checkpoint": 0,
    "N3_common_market_data_run": 0,
    "N4_common_trigger_run": 0,
    "N5_common_action_run": 0,
    "N6_user_projection_run": 0
  },
  "refs_total": 0,
  "market_data_pulled": false,
  "downstream_layers_touched": false,
  "worker_started": false,
  "old_system_touched": false,
  "proposal_order_trade_sim_position_pnl_real_trade": false
}
```
