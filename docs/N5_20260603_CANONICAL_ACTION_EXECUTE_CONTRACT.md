# N5 Canonical Action Execute Contract

## Summary

- stage: N5-canonical-20260603-after-n4-matcher-fix-execute-contract
- layer_role: N5_action
- runner_mode: run_once
- source_trigger_run_id: trigger_execute_20260603_condition_layer_20260602_source_20260602_v1
- action_run_id: action_consumer_canonical_20260603_trigger_execute_20260603_condition_layer_20260602_source_20260602_v1
- consumer_name: n5_action_consumer_v1
- execute: True
- user_confirmed: True
- P0/P1/P2: 0/0/0
- allow_execute: True

## Guards

- source_run_guard: {'configured': True, 'allowed_source_run_ids': ['trigger_execute_20260603_condition_layer_20260602_source_20260602_v1'], 'denied_source_run_ids': ['trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute', 'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute'], 'trigger_run_id': 'trigger_execute_20260603_condition_layer_20260602_source_20260602_v1', 'trigger_run_denied': False, 'trigger_run_not_allowed': False, 'observed_source_run_ids': {'trigger_execute_20260603_condition_layer_20260602_source_20260602_v1': 20334}, 'denied_observed_source_run_ids': [], 'outside_allowlist_source_run_ids': [], 'passed': True}
- pending_only_guard: {'allowed_statuses': ['pending'], 'by_status': {'pending': 20334}, 'total_row_count': 20334, 'pending_count': 20334, 'non_pending_count': 0, 'non_pending_sample': [], 'passed': True}
- blockers: []

## Planned Write Scope

- common_action_run: 1
- common_action_quality_item: 8915
- stock_action_fact: 1056
- index_action_fact: 26
- board_action_fact: 170
- common_action_event: 1252
- common_event_outbox: 1252
- common_event_inbox: 20334
- common_event_consumer_checkpoint: 2474
- common_position_state: 0
- common_position_event: 0

## Event Mapping

- output_event_plan: {'ActionEligible': 0, 'ActionBlocked': 1252, 'ActionExecuted': 0, 'ActionSkipped': 0}
- BUY_HINT / SELL_HINT remain condition trace only; they do not emit HintEvent.
- B_BUY / S_SELL are the only runtime signal_type values accepted by canonical N5 planning.
- final action_mark is normal / 30m_volume / 30m_shrink only after N5 confirmation passes.
- TriggerPendingMarketData writes quality only.
- Execute is still gated by --execute, --user-confirmed, and a separate final gate.

## Boundary

- side_effects: {'will_execute_sql': False, 'writes_performed': False, 'common_event_inbox_updated': False, 'consumer_checkpoint_updated': False, 'action_run_written': False, 'action_quality_written': False, 'action_fact_written': False, 'action_event_written': False, 'common_event_outbox_written': False, 'n5_outbox_written': False, 'n4_outbox_status_updated': False, 'n4_outbox_consumed': False, 'position_state_written': False, 'position_event_written': False, 'market_data_pulled': False, 'n1_n2_n3_n4_modified': False, 'n6_user_layer_touched': False, 'user_layer_touched': False, 'voice_touched': False, 'sim_touched': False, 'mobile_touched': False, 'real_trade_touched': False, 'worker_started': False, 'old_system_touched': False}