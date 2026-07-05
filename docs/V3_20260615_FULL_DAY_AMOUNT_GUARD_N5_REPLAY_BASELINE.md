# V3 20260615 Full-Day Amount Guard N5 Replay Baseline

```json
{
  "action_run_id": "n5_action_bounded_20260615_after_n4_amount_guard_fix_until_1500_v1",
  "boundary": {
    "does_not_consume_outbox_status": true,
    "does_not_enter_n6": true,
    "does_not_touch_voice_mobile_sim_position_order_trade": true
  },
  "consumer_name": "n5_action_bounded_consumer_20260615_after_n4_amount_guard_fix_until_1500_v1",
  "consumer_strategy": {
    "dedicated_consumer_name": "n5_action_bounded_consumer_20260615_after_n4_amount_guard_fix_until_1500_v1",
    "uses_dedicated_consumer": true
  },
  "created_at": "2026-06-15T19:29:30.942010",
  "dedicated_consumer_name": "n5_action_bounded_consumer_20260615_after_n4_amount_guard_fix_until_1500_v1",
  "expected_event_distribution": {
    "TriggerMatched": 25
  },
  "expected_read_event_count": 25,
  "metric_run_id": "action_confirmation_projection_metric_20260615_until_1500_after_n4_amount_guard_fix_v1",
  "metric_run_ids": [
    "action_confirmation_projection_metric_20260615_until_1500_after_n4_amount_guard_fix_v1"
  ],
  "n3_action_metric_run_id": "action_confirmation_projection_metric_20260615_until_1500_after_n4_amount_guard_fix_v1",
  "result": "BASELINE_PASS",
  "rollback_sql_path": "sql/V3_20260615_full_day_amount_guard_n5_replay_rollback.sql",
  "source_event_types": [
    "TriggerMatched"
  ],
  "source_trigger_run_id": "n4_production_semantic_replay_20260615_market_snapshot_updated_until_1500_amount_guard_fix_v1",
  "stage": "V3_20260615_FULL_DAY_AMOUNT_GUARD_N5_REPLAY_BASELINE"
}
```
