# N4 Formal Amount Guard 20260615 N5 Replay Baseline

- result: BASELINE_PASS
- source_trigger_run_id: `n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_amount_guard_fix_v1`
- action_run_id: `n5_action_bounded_20260615_after_n4_amount_guard_fix_until_1000_v1`
- consumer_name: `n5_action_bounded_consumer_20260615_after_n4_amount_guard_fix_until_1000_v1`
- metric_run_id: `action_confirmation_projection_metric_20260615_until_1000_after_n4_amount_guard_fix_v1`
- expected_event_distribution: `TriggerMatched=30`
- boundary: no N6 / voice / mobile / sim / position / order / real trade
