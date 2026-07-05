# N4 20260617 Full-Day Context Localization After N3 Full-Day B2 Pass Preflight

- result: `N4_PREFLIGHT_PASS`
- trigger_context_run_id: `trigger_context_snapshot_20260617_full_day__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- planned_execute_run_id: `trigger_action_confirmation_metric_execute_20260617_full_day_after_n3_full_day_b2_pass__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- metric rows: `{'stock': 441840, 'index': 19440, 'board': 30480}`, total=`491760`, ready=`491760`, not_ready=`0`
- per_identity_minmax: `{'stock': {'min': 240, 'max': 240}, 'index': {'min': 240, 'max': 240}, 'board': {'min': 240, 'max': 240}}`
- canonical included distribution: `{'BUY': 1939, 'BUY:FULL': 110, 'BUY_HINT': 59, 'SELL': 2021, 'SELL:FULL': 28, 'SELL_HINT': 165}`
- BJ metric rows: `0`
- target_execute_baseline: `{'execute_run_common_trigger_run': 0, 'execute_run_quality': 0, 'execute_run_state': 0, 'execute_run_match': 0, 'execute_run_outbox': 0, 'execute_run_outbox_delivered_or_delivering': 0, 'execute_run_inbox': 0, 'execute_run_checkpoint_refs': 0, 'downstream_inbox_for_execute_run': 0, 'downstream_checkpoint_refs': 0, 'n5_action_run_refs': 0}`
- planned_upper_bound: `{'context_rows': 4326, 'metric_rows': 491760, 'metric_rows_per_identity': 240, 'max_candidate_evaluations': 1037284, 'max_state_rows': 4326, 'actual_distribution_deferred_to_execute': True}`
- rollback SQL: `sql/N4_20260617_full_day_trigger_replay_after_n3_full_day_b2_pass_rollback.sql`

## Allowed Next Prompt
```text
layer_role=N4_trigger. Enter N4_20260617_FULL_DAY_TRIGGER_REPLAY_EXECUTE_AFTER_CONTEXT_PREFLIGHT_PASS. Use trade_date=20260617; trigger_context_run_id=trigger_context_snapshot_20260617_full_day__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1; source_metric_run_id=action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1; source_condition_run_id=condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1; source_subscription_run_id=market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1; source_today_minute_run_id=today_minute_bar_1m_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1; execute_run_id=trigger_action_confirmation_metric_execute_20260617_full_day_after_n3_full_day_b2_pass__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1; rollback_sql=sql/N4_20260617_full_day_trigger_replay_after_n3_full_day_b2_pass_rollback.sql. Execute bounded N4 full-day trigger replay only; do not enter N5/N6; do not consume outbox/inbox/checkpoint; do not pull market data; output TriggerMatched/TriggerPendingMarketData/TriggerStateChanged distribution and post-review artifact.
```
