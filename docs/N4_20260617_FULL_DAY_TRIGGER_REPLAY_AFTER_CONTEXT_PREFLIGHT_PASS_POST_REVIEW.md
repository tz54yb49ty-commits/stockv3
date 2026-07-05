# N4 20260617 Full-Day Trigger Replay Post Review

Result: `N4_TRIGGER_REPLAY_PASS`

- execute_run_id: `trigger_action_confirmation_metric_execute_20260617_full_day_after_n3_full_day_b2_pass__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- trigger_context_run_id: `trigger_context_snapshot_20260617_full_day__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- source_metric_run_id: `action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- common_trigger_state: `1020871`
- common_trigger_match: `1661`
- common_event_outbox: `1032632`
- persisted_event_distribution: `{"TriggerMatched": 1661, "TriggerPendingMarketData": 1017925, "TriggerStateChanged": 13046}`
- outbox_status_distribution: `{"pending": 1032632}`
- state_status_distribution: `{"inactive": 1285, "matched": 1661, "pending_market_data": 1017925}`
- n4_state_family_distribution: `{"BUY:FULL": 26400, "BUY_HINT": 10673, "SELL:FULL": 6720, "SELL_HINT": 26674, "ordinary_BUY": 465362, "ordinary_SELL": 485042}`
- n4_match_family_distribution: `{"BUY_HINT": 246, "SELL_HINT": 1415}`
- hint_calibrated_path: `[{"c": 246, "calibrated_status": "passed", "condition_key": "BUY_HINT", "metric_policy": "previous_day_same_window_elapsed_ratio_v1", "trigger_mark_candidate": "30m_volume", "trigger_period": "30m"}, {"c": 1415, "calibrated_status": "passed", "condition_key": "SELL_HINT", "metric_policy": "previous_day_same_window_elapsed_ratio_v1", "trigger_mark_candidate": "30m_shrink", "trigger_period": "30m"}]`
- y_triggered_count: `0`
- always_true_for_Y_count: `0`
- pending_state_joined_to_common_trigger_match: `0`
- pending_outbox_joined_to_common_trigger_match: `0`
- state_changed_outbox_joined_to_common_trigger_match: `0`
- n5_refs: `{"board_action_fact": 0, "common_action_event": 0, "common_action_run": 0, "index_action_fact": 0, "stock_action_fact": 0}`
- inbox_refs: `0`
- checkpoint_refs: `0`
- rollback_sql: `sql/N4_20260617_full_day_trigger_replay_after_n3_full_day_b2_pass_rollback.sql`

Errors: `[]`
