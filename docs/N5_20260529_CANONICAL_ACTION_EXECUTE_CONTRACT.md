# N5 20260529 Canonical Action Execute Contract

## Summary

- status: CONTRACT_REFRESHED
- layer_role: N5_action
- action_run_id: action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1
- source_trigger_run_id: trigger_execute_20260529_condition_layer_20260528_source_20260528_v1
- consumer_name: n5_action_consumer_v1
- execute_authorized: False
- execute_requires_final_gate: True
- runner_ready_for_20260529_execute_final_gate: True

## Planned Writes After A Future Final Gate

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

## Output Event Plan

- ActionEligible: 0
- ActionBlocked: 4309
- ActionExecuted: 0
- ActionSkipped: 0

## Canonical Payload Rules

- runtime_signal_type_allowed: ['B_BUY', 'S_SELL']
- deprecated_runtime_signal_count: 0
- BUY_HINT / SELL_HINT: condition_key/original_condition_key/trace only; no HintEvent in canonical N5
- final_action_mark_non_null_count_in_current_plan: 0
- legacy_output_event_count: 0

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
- rollback_sql_executed: false
