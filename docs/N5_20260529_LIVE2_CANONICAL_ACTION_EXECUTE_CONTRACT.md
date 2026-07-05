# N5 20260529 Live2 Canonical Action Execute Contract

## Summary

- status: CONTRACT_REFRESHED
- layer_role: N5_action
- source_trigger_run_id: trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1
- action_run_id: action_consumer_canonical_20260529_live2_trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1
- execute_authorized: False
- execute_requires_final_gate: True

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

## Runner Readiness

- explicit_source_run_id_supported: True
- explicit_action_run_id_supported: True
- ready_for_live2_execute_preflight: True
- blockers: []

## Rollback

- rollback_sql_path: sql/N5_20260529_live2_canonical_action_execute_rollback.sql
- rollback_sql_executed: false
