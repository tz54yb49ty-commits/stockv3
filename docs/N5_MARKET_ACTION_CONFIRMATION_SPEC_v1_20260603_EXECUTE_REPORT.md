# N5 Market Action Confirmation Spec v1 20260603 Execute Report

- result: `EXECUTE_PASS`
- action_run_id: `action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`
- common_action_run.status: `passed`
- P0/P1/P2: `0/0/0`
- actual_rows: `{'common_action_run': 1, 'common_action_quality_item': 0, 'stock_action_fact': 680, 'index_action_fact': 34, 'board_action_fact': 149, 'common_action_event': 863, 'common_event_outbox': 863, 'common_event_inbox': 863, 'common_event_consumer_checkpoint': 822}`
- event_distribution: `[{'event_type': 'ActionBlocked', 'row_count': 863}]`
- n5_outbox: `[{'event_type': 'ActionBlocked', 'status': 'pending', 'row_count': 863}]`
- blocked_reason_distribution: `[{'blocked_reason': 'amount_confirmation_failed', 'row_count': 25}, {'blocked_reason': 'price_confirmation_failed', 'row_count': 838}]`
- action_mark_final_only: `{'blocked_action_mark_non_null': 0}`
- invalid_user_layer_blocked_reason_count: `0`
- N4 outbox unchanged: `[{'event_type': 'TriggerMatched', 'status': 'pending', 'row_count': 863}]`
- BJ/FULL blocked proof: `{'bj_quality_visible_proof': {'dry_run_quality_blocked_rows': 4, 'passed': True, 'recognized_bj_identity_keys': ['index:BJ:899050', 'index:BJ:899601'], 'trigger_matched_rows': 0}, 'full_blocked_proof': {'dry_run_blocked_rows': 92, 'passed': True, 'trigger_matched_rows': 0}}`
- downstream_refs: `{'user_projection_run': 0, 'user_signal_projection': 0, 'user_signal_decision': 0, 'user_notification_queue': 0, 'user_sim_order': 0, 'user_sim_trade': 0, 'user_sim_position': 0, 'common_position_state': 0, 'common_position_event': 0}`
- rollback_safe: `True`
- rollback_sql: `sql/N5_market_action_confirmation_spec_v1_20260603_execute_rollback.sql`

No N5 outbox was consumed. N6/user/voice/mobile/sim/position/real trade paths were not touched. No worker was started by this run.
