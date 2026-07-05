# N5 20260529 Canonical Action Execute Preflight

## Summary

- status: PREFLIGHT_PASS
- layer_role: N5_action
- action_run_id: action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1
- source_trigger_run_id: trigger_execute_20260529_condition_layer_20260528_source_20260528_v1
- execute_authorized: False
- allow_execute_preflight_next: True
- allow_execute_final_gate: True
- P0/P1/P2: 0/0/0

## Source N4 Outbox

- status_counts: {'pending': 17722}
- by_event_type: {'TriggerMatched': 4309, 'TriggerPendingMarketData': 4552, 'TriggerStateChanged': 8861}
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

## Schema Readiness

- schema_ready: True
- live_db_025_columns_present: {'stock_action_fact': True, 'index_action_fact': True, 'board_action_fact': True, 'common_action_event': True}
- source_trigger_event_type_check_compatible: {'stock_action_fact': True, 'index_action_fact': True, 'board_action_fact': True}
- common_action_event_event_type_check_compatible: True
- static_sql_011_drift: P1 known follow-up; live DB 025 is authoritative for this gate

## Runner Readiness

- dry_run_planner_ready: True
- execute_runner: scripts/run_action_consumer_once.py
- source_run_argument_present: True
- action_run_argument_present: True
- default_source_run_id_is_20260529: True
- execute_allowlist_contains_20260529: True
- stale_20260528_source_denied_for_20260529: True
- ready_for_20260529_execute_final_gate: True
- blockers: []

## Rollback

- rollback_sql_path: sql/N5_20260529_canonical_action_execute_rollback.sql
- rollback_sql_exists: True
- rollback_executed: false
- rollback_scope: N5 rows by action_run_id/source_run_id/consumer_name only; N6 refs guarded; 025 schema not rolled back.

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
