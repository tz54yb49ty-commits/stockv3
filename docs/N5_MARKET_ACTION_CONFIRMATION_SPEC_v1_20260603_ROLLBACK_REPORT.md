# N5 Market Action Confirmation Spec v1 Rollback Report

Result: `ROLLBACK_PASS`

- action_run_id: `action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`
- rollback_sql: `sql/N5_market_action_confirmation_spec_v1_20260603_execute_rollback.sql`
- scoped rows cleared: `true`
- N4 outbox: `TriggerMatched pending=863`
- N3 metric rows: `stock/index/board=640/34/148`
- downstream refs: `0` for existing user/sim/position tables
- rollback_safe_after_state: `true`

## Scoped Rows After Rollback

```json
{
  "common_action_run": 0,
  "common_action_quality_item": 0,
  "stock_action_fact": 0,
  "index_action_fact": 0,
  "board_action_fact": 0,
  "common_action_event": 0,
  "n5_common_event_outbox": 0,
  "n5_common_event_inbox": 0,
  "n5_common_event_consumer_checkpoint_scoped": 0,
  "n5_downstream_inbox_refs": 0,
  "n5_downstream_checkpoint_refs": 0
}
```

## N4 Preservation Proof

```json
{
  "common_trigger_run_rows": 1,
  "common_trigger_match_rows": 863,
  "common_event_outbox": [
    {
      "event_type": "TriggerMatched",
      "status": "pending",
      "c": 863
    }
  ],
  "n4_outbox_status_updated": false
}
```

## Boundary Proof

```json
{
  "n5_retry_executed": false,
  "outbox_consumed": false,
  "n6_entered": false,
  "worker_started": false,
  "delivery_notification_push_voice_mobile_sim_position_real_trade": false,
  "n4_outbox_modified": false,
  "n3_n2_facts_modified": false
}
```
