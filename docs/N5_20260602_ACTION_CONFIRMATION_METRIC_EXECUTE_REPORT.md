# N5 Canonical Action Execute Contract

## Summary

- stage: N5-canonical-execute-contract
- layer_role: N5_action
- runner_mode: run_once
- source_trigger_run_id: trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
- action_run_id: action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
- consumer_name: n5_action_consumer_v1
- execute: True
- user_confirmed: True
- P0/P1/P2: 0/0/0
- allow_execute: True

## Guards

- source_run_guard: {'configured': True, 'allowed_source_run_ids': ['trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1'], 'denied_source_run_ids': ['trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute', 'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute', 'trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249', 'trigger_execute_20260528_condition_layer_20260527_source_20260527_v2', 'trigger_execute_20260529_condition_layer_20260528_source_20260528_v1'], 'trigger_run_id': 'trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1', 'trigger_run_denied': False, 'trigger_run_not_allowed': False, 'observed_source_run_ids': {'trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1': 5941}, 'denied_observed_source_run_ids': [], 'outside_allowlist_source_run_ids': [], 'passed': True}
- pending_only_guard: {'allowed_statuses': ['pending'], 'by_status': {'pending': 5941}, 'total_row_count': 5941, 'pending_count': 5941, 'non_pending_count': 0, 'non_pending_sample': [], 'passed': True}
- blockers: []

## Planned Write Scope

- common_action_run: 1
- common_action_quality_item: 5935
- stock_action_fact: 1
- index_action_fact: 4
- board_action_fact: 0
- common_action_event: 5
- common_event_outbox: 5
- common_event_inbox: 5941
- common_event_consumer_checkpoint: 2487
- common_position_state: 0
- common_position_event: 0

## Event Mapping

- output_event_plan: {'ActionEligible': 0, 'ActionBlocked': 1, 'ActionExecuted': 4, 'ActionSkipped': 0}
- BUY_HINT / SELL_HINT remain condition trace only; they do not emit HintEvent.
- B_BUY / S_SELL are the only runtime signal_type values accepted by canonical N5 planning.
- final action_mark is normal / 30m_volume / 30m_shrink only after N5 confirmation passes.
- TriggerPendingMarketData writes quality only.
- Execute is still gated by --execute, --user-confirmed, and a separate final gate.

## Boundary

- side_effects: {'will_execute_sql': True, 'writes_performed': True, 'common_event_inbox_updated': True, 'consumer_checkpoint_updated': True, 'action_run_written': True, 'action_quality_written': True, 'action_fact_written': True, 'action_event_written': True, 'common_event_outbox_written': True, 'n5_outbox_written': True, 'n4_outbox_status_updated': False, 'n4_outbox_consumed': False, 'position_state_written': False, 'position_event_written': False, 'market_data_pulled': False, 'n1_n2_n3_n4_modified': False, 'n6_user_layer_touched': False, 'user_layer_touched': False, 'voice_touched': False, 'sim_touched': False, 'mobile_touched': False, 'real_trade_touched': False, 'worker_started': False, 'old_system_touched': False}