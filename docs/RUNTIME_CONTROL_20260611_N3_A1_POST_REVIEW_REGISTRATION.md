# Runtime Control 20260611 N3-A1 Post Review Registration

Result: `POST_REVIEW_PASS`

- subscription_run_id: `market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- preload_run_id: `previous_day_minute_preload_20260610_for_20260611__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- Stage 1 rows candidate/subscription/pull_plan: `5046/2666/9`
- Stage 2 minute rows stock/index/board: `60000/4560/3360`
- Stage 2 status rows stock/index/board: `250/19/14`
- duplicate minute key groups: `{'stock': 0, 'index': 0, 'board': 0}`
- refs total: `0`
- rollback_safe: `True`

## Boundary Proof

```json
{
  "transaction_read_only": "on",
  "refs": {
    "common_event_outbox": 0,
    "common_event_inbox": 0,
    "checkpoint": 0,
    "n4": 0,
    "n5": 0,
    "n6": 0
  },
  "refs_total": 0,
  "n3_b_c_b2_refs": 0,
  "market_data_pulled_stage1": false,
  "market_data_pulled_stage2_previous_day_only": true,
  "event_outbox_written": false,
  "downstream_layers_touched": false,
  "worker_started": false,
  "old_system_touched": false,
  "proposal_order_trade_sim_position_pnl_real_trade": false
}
```

## Rollback Summary

```json
{
  "path": "sql/N3_A1_previous_day_minute_20260611_rollback.sql",
  "rollback_safe": true,
  "covers_stage1_and_stage2": true,
  "hard_fail_before_delete": true,
  "no_drop_truncate_cascade": true
}
```
