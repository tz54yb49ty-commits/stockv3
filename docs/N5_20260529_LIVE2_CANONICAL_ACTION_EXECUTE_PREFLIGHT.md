# N5 20260529 Live2 Canonical Action Execute Preflight

## Summary

- status: PREFLIGHT_PASS
- layer_role: N5_action
- source_trigger_run_id: trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1
- action_run_id: action_consumer_canonical_20260529_live2_trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1
- execute_authorized: False
- allow_execute_final_gate: True
- P0/P1/P2: 0/0/0

## Source N4 Outbox

- by_event_type_pending: {'TriggerMatched': 4309, 'TriggerPendingMarketData': 4552, 'TriggerStateChanged': 8861}
- delivered_delivering_count: 0

## Baseline Scoped Refs

- common_action_run: 0
- common_action_quality_item: 0
- stock_action_fact: 0
- index_action_fact: 0
- board_action_fact: 0
- common_action_event: 0
- common_event_outbox_for_action_run_id: 0
- common_event_inbox_for_source_run_id: 0
- common_event_inbox_for_action_run_id: 0
- common_event_consumer_checkpoint_payload_action_run_id: 0
- n6_inbox_refs_for_action_run_id: 0
- user_projection_run: 0
- user_signal_projection: 0
- user_signal_card: 0
- user_notification_queue: 0

## Planned Writes

- common_action_run: 1
- common_action_quality_item: 4552
- stock_action_fact: 4037
- index_action_fact: 18
- board_action_fact: 254
- common_action_event: 4309
- common_event_outbox: 4309
- common_event_inbox: 17722
- common_event_consumer_checkpoint: 2157
- common_position_state: 0
- common_position_event: 0

## Dry-run Plan Summary

- read_event_count: 17722
- planned_action_fact_count: 4309
- quality_plan_only_count: 4552
- state_gate_only_count: 8861
- pending_action_fact_plan_count: 0
- deprecated_runtime_signal_count: 0
- legacy_output_event_count: 0
- runtime_signal_distribution: {'B_BUY': 2157, 'S_SELL': 2152}
- final_action_mark_non_null_count: 0

## Rollback

- rollback_sql_path: sql/N5_20260529_live2_canonical_action_execute_rollback.sql
- rollback_sql_exists: False
- rollback_executed: false

## Boundary Confirmation

- writes_performed: False
- n4_outbox_consumed: False
- n4_outbox_status_updated: False
- common_event_inbox_updated: False
- consumer_checkpoint_updated: False
- action_fact_written: False
- common_action_event_written: False
- common_event_outbox_written: False
- n6_user_layer_touched: False
- worker_started: False
- real_trade_touched: False
- position_written: False
- voice_mobile_sim_touched: False
