# N5 Canonical Action Execute Contract

## Summary

- stage: N5-worker-semantic-action-smoke
- layer_role: N5_action
- runner_mode: run_once
- source_trigger_run_id: n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000
- action_run_id: n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1000_v1
- consumer_name: n5_action_bounded_consumer_20260615_after_n3_metric_until_1000_v1
- execute: True
- user_confirmed: True
- P0/P1/P2: 0/0/0
- allow_execute: True

## Guards

- source_run_guard: {'configured': True, 'allowed_source_run_ids': ['n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000'], 'denied_source_run_ids': ['trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute', 'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute'], 'trigger_run_id': 'n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000', 'trigger_run_denied': False, 'trigger_run_not_allowed': False, 'observed_source_run_ids': {'n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000': 835}, 'denied_observed_source_run_ids': [], 'outside_allowlist_source_run_ids': [], 'passed': True}
- pending_only_guard: {'allowed_statuses': ['pending'], 'by_status': {'pending': 835}, 'total_row_count': 835, 'pending_count': 835, 'non_pending_count': 0, 'non_pending_sample': [], 'passed': True}
- blockers: []

## Planned Write Scope

- common_action_run: 1
- common_action_quality_item: 0
- stock_action_fact: 834
- index_action_fact: 0
- board_action_fact: 1
- common_action_event: 835
- common_event_outbox: 835
- common_event_inbox: 835
- common_event_consumer_checkpoint: 819
- common_position_state: 0
- common_position_event: 0

## Event Mapping

- output_event_plan: {'ActionEligible': 0, 'ActionBlocked': 786, 'ActionExecuted': 49, 'ActionSkipped': 0}
- BUY_HINT / SELL_HINT remain condition trace only; they do not emit HintEvent.
- B_BUY / S_SELL are the only runtime signal_type values accepted by canonical N5 planning.
- final action_mark is normal / 30m_volume / 30m_shrink only after N5 confirmation passes.
- ActionBlocked means market action not confirmed / 市场动作未确认; it is not a user trade failure.
- TriggerPendingMarketData writes quality only.
- Execute is still gated by --execute, --user-confirmed, and a separate final gate.

## Boundary

- side_effects: {'will_execute_sql': True, 'writes_performed': True, 'common_event_inbox_updated': True, 'consumer_checkpoint_updated': True, 'action_run_written': True, 'action_quality_written': True, 'action_fact_written': True, 'action_event_written': True, 'common_event_outbox_written': True, 'n5_outbox_written': True, 'n4_outbox_status_updated': False, 'n4_outbox_consumed': False, 'position_state_written': False, 'position_event_written': False, 'market_data_pulled': False, 'n1_n2_n3_n4_modified': False, 'n6_user_layer_touched': False, 'user_layer_touched': False, 'voice_touched': False, 'sim_touched': False, 'mobile_touched': False, 'real_trade_touched': False, 'worker_started': False, 'old_system_touched': False}