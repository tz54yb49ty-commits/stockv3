# N5 20260528 Canonical Action Execute Preflight

## Summary

- status: PREFLIGHT_PASS
- layer_role: N5_action
- action_run_id: action_consumer_canonical_20260528_trigger_execute_20260528_condition_layer_20260527_source_20260527_v2
- source_trigger_run_id: trigger_execute_20260528_condition_layer_20260527_source_20260527_v2
- execute_authorized: False
- allow_execute_final_gate: True
- P0/P1/P2: 0/1/0

## Source N4 Outbox

- status_counts: {'pending': 17774}
- by_event_type: {'TriggerMatched': 4285, 'TriggerPendingMarketData': 4602, 'TriggerStateChanged': 8887}
- delivered_delivering_count: 0
- TriggerStateChanged by trigger_live: {'false': 4602, 'true': 4285}
- TriggerStateChanged by current_status: {'matched': 4285, 'pending_market_data': 4602}

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
- common_action_quality_item: 4602
- stock_action_fact: 4013
- index_action_fact: 18
- board_action_fact: 254
- common_action_event: 4285
- common_event_outbox: 4285
- common_event_inbox: 17774
- common_event_consumer_checkpoint: 2146
- common_position_state: 0
- common_position_event: 0

## Schema Readiness

- schema_ready: True
- live_db_025_columns_present: {'stock_action_fact': True, 'index_action_fact': True, 'board_action_fact': True, 'common_action_event': True}
- source_trigger_event_type_check_compatible: {'stock_action_fact': True, 'index_action_fact': True, 'board_action_fact': True}
- common_action_event_event_type_check_compatible: True

## Static Drift

- severity: P1
- findings: ['schema missing N5 output event type: ActionEligible', 'schema missing N5 output event type: ActionBlocked', 'schema missing N5 output event type: ActionExecuted', 'schema missing N5 output event type: ActionSkipped', 'schema missing N5 input trigger event type: TriggerStateChanged']

## Runner Readiness

- ready_for_canonical_execute: True
- blockers: []
- execute_authorized_false_reason: waiting_for_user_final_gate_only

## Rollback

- rollback_sql_path: sql/N5_20260528_canonical_action_execute_rollback.sql
- rollback_executed: false
- rollback_scope: N5 rows by action_run_id/source_run_id/consumer_name only; N6 refs guarded; 025 schema not rolled back.

## Boundary Confirmation

- writes_performed: false
- n4_outbox_consumed: false
- common_event_inbox_updated: false
- consumer_checkpoint_updated: false
- action_fact_written: false
- common_action_event_written: false
- common_event_outbox_written: false
- n6_user_layer_touched: false
- worker_started: false
- real_trade_touched: false
