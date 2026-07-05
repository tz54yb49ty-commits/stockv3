# N5 20260603 Canonical Action Execute Preflight

## Summary

- result: PREFLIGHT_PASS
- layer_role: N5_action
- source_n4_execute_run_id: trigger_execute_20260603_condition_layer_20260602_source_20260602_v1
- action_run_id: action_consumer_canonical_20260603_trigger_execute_20260603_condition_layer_20260602_source_20260602_v1
- consumer_name: n5_action_consumer_v1
- execute_authorized: false
- allow_execute_final_gate: True
- P0/P1/P2: 0/0/0

## N4 Input Readiness

- trigger_run_status: passed
- outbox_by_event_status: [{'event_type': 'TriggerMatched', 'status': 'pending', 'c': 1252}, {'event_type': 'TriggerPendingMarketData', 'status': 'pending', 'c': 8915}, {'event_type': 'TriggerStateChanged', 'status': 'pending', 'c': 10167}]
- outbox_totals: {'total': 20334, 'pending': 20334, 'delivered': 0, 'delivering': 0}

## Baseline Scoped Refs

- common_action_run: 0
- common_action_quality_item: 0
- stock_action_fact: 0
- index_action_fact: 0
- board_action_fact: 0
- common_action_event: 0
- common_event_outbox_for_action_run_id: 0
- common_event_inbox_for_source_run_id: 0
- common_event_consumer_checkpoint_refs: 0

## Planned Writes

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

## Output Events

- ActionEligible: 0
- ActionBlocked: 1252
- ActionExecuted: 0
- ActionSkipped: 0

## Rollback

- rollback_sql_path: sql/N5_20260603_canonical_action_execute_rollback.sql
- rollback_sql_exists: True
- hard_fail_before_delete: True
- rollback_touches_N4_N3_N2_N6: False

## Boundary

- writes_performed: false
- n4_outbox_consumed: false
- n4_outbox_status_updated: false
- n6_entered: false
- worker_started: false