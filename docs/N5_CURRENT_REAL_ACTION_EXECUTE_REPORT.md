# N5 Current-Real Action Execute Contract

## Summary

- stage: N5-current-real-action-execute-runner-implementation
- layer_role: N5_action
- runner_mode: run_once
- source_trigger_run_id: trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249
- action_run_id: action_consumer_current_real_execute_20260525_trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249
- consumer_name: n5_action_consumer_v1
- execute: True
- user_confirmed: True
- P0/P1/P2: 0/0/0
- allow_execute: True

## Guards

- source_run_guard: {'configured': True, 'allowed_source_run_ids': ['trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249'], 'denied_source_run_ids': ['trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute', 'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute'], 'trigger_run_id': 'trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249', 'trigger_run_denied': False, 'trigger_run_not_allowed': False, 'observed_source_run_ids': {'trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249': 764}, 'denied_observed_source_run_ids': [], 'outside_allowlist_source_run_ids': [], 'passed': True}
- pending_only_guard: {'allowed_statuses': ['pending'], 'by_status': {'pending': 764}, 'total_row_count': 764, 'pending_count': 764, 'non_pending_count': 0, 'non_pending_sample': [], 'passed': True}
- blockers: []

## Planned Write Scope

- common_action_run: 1
- common_action_quality_item: 276
- stock_action_fact: 488
- index_action_fact: 0
- board_action_fact: 0
- common_action_event: 488
- common_event_outbox: 488
- common_event_inbox: 764
- common_event_consumer_checkpoint: 615
- common_position_state: 0
- common_position_event: 0

## Event Mapping

- output_event_plan: {'ActionEvent': 479, 'HintEvent': 9, 'RiskEvent': 0, 'PositionEvent': 0}
- BUY_HINT / SELL_HINT write action facts and emit HintEvent.
- B_BUY_30M_VOL / S_SELL_30M_SHRINK emit ActionEvent.
- TriggerPendingMarketData writes quality only.

## Boundary

- side_effects: {'will_execute_sql': True, 'writes_performed': True, 'common_event_inbox_updated': True, 'consumer_checkpoint_updated': True, 'action_run_written': True, 'action_quality_written': True, 'action_fact_written': True, 'action_event_written': True, 'common_event_outbox_written': True, 'n5_outbox_written': True, 'n4_outbox_status_updated': False, 'n4_outbox_consumed': False, 'position_state_written': False, 'position_event_written': False, 'market_data_pulled': False, 'n1_n2_n3_n4_modified': False, 'n6_user_layer_touched': False, 'user_layer_touched': False, 'voice_touched': False, 'sim_touched': False, 'mobile_touched': False, 'real_trade_touched': False, 'worker_started': False, 'old_system_touched': False}