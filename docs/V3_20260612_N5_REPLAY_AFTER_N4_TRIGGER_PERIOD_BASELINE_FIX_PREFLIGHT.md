# V3 20260612 N5 Replay After N4 Trigger Period Baseline Fix Preflight

- result: `PREFLIGHT_PASS`
- source_trigger_run_id: `v3_n4_trigger_replay_20260612_after_trigger_period_baseline_fix_v1`
- action_run_id: `v3_n5_action_replay_20260612_after_n4_trigger_period_baseline_fix_v1`
- consumer_name: `v3_n5_action_replay_20260612_after_n4_trigger_period_baseline_fix_consumer_v1`
- source_event_types: `TriggerMatched`
- read_event_count: `1187`
- metric_join_coverage: `1187/1187`
- planned writes: `{'common_action_run': 1, 'common_action_quality_item': 0, 'stock_action_fact': 965, 'index_action_fact': 154, 'board_action_fact': 68, 'common_action_event': 1187, 'common_event_outbox': 1187, 'common_event_inbox': 1187, 'common_event_consumer_checkpoint': 235, 'accepted_event_count': 1187, 'checkpoint_plan_entry_count': 235, 'checkpoint_physical_watermark_rows': 235, 'common_position_state': 0, 'common_position_event': 0}`
- expected action distribution: `{'ActionEligible': 0, 'ActionBlocked': 911, 'ActionExecuted': 276, 'ActionSkipped': 0}`
- fabricated formal period count: `0`
- ordinary formal action fact count: `0`
- hint action fact count: `1187`
- target scoped baseline: `{'common_action_run': 0, 'common_action_quality_item': 0, 'stock_action_fact': 0, 'index_action_fact': 0, 'board_action_fact': 0, 'common_action_event': 0, 'n5_common_event_outbox': 0, 'consumer_inbox': 0, 'consumer_checkpoint': 0, 'n6_user_refs': 0}`

## Boundary

- N5 consumes only fixed N4 `TriggerMatched` rows.
- TriggerPendingMarketData / TriggerStateChanged are not consumed for action confirmation.
- N4 outbox status is not updated.
- N6/user/voice/mobile/sim/position/order/real trade are untouched.
