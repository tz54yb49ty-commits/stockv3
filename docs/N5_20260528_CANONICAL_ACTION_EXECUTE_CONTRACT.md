# N5 20260528 Canonical Action Execute Contract

## Summary

- status: CONTRACT_REFRESHED
- layer_role: N5_action
- action_run_id: action_consumer_canonical_20260528_trigger_execute_20260528_condition_layer_20260527_source_20260527_v2
- source_trigger_run_id: trigger_execute_20260528_condition_layer_20260527_source_20260527_v2
- consumer_name: n5_action_consumer_v1
- execute_authorized: False
- execute_requires_final_gate: True
- runner_ready_for_canonical_execute: True

## Canonical Input Rules

- TriggerMatched: unique action confirmation entry; may create action fact plan
- TriggerPendingMarketData: quality-only/no-op/state-gate; must not create action fact
- TriggerStateChanged: live/state gate only; must not create action confirmation alone
- live_false: stops tracking; does not delete history

## Planned Writes After A Future Final Gate

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

## Output Event Plan

- ActionEligible: 0
- ActionBlocked: 4285
- ActionExecuted: 0
- ActionSkipped: 0

## Canonical Payload Rules

- runtime_signal_type_allowed: ['B_BUY', 'S_SELL']
- deprecated_runtime_signal_count: 0
- BUY_HINT / SELL_HINT: condition_key/original_condition_key/trace only; no HintEvent in canonical N5
- final_action_mark_non_null_count_in_current_plan: 0
- legacy_output_event_count: 0

## Runner Readiness

- existing_runner: scripts/run_action_consumer_once.py
- runner_mode: run_once
- has_double_confirmation: True
- source_run_parameterized_for_canonical_20260528: True
- default_source_run_id: trigger_execute_20260528_condition_layer_20260527_source_20260527_v2
- stale_20260525_source_denied: True
- synthetic_source_run_denied: True
- active_hardcoded_current_real_20260525_source_default_present: False
- contract_blocker_still_present: False
- insert_action_fact_populates_025_columns: True
- insert_common_action_event_populates_025_columns: True
- deprecated_output_event_path_count_in_runner: 9
- deprecated_output_event_path_role: guard/count only
- blockers: []
- ready_for_canonical_execute: True

## Rollback

- rollback_sql_path: sql/N5_20260528_canonical_action_execute_rollback.sql
- rollback_sql_executed: false
