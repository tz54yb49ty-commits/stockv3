# N5 20260602 11:05 Live After N4 Execute Dry-run

## Summary

- stage: N5-20260602-1105-live-after-n4-execute-dry-run
- layer_role: N5_action
- source_trigger_run_id: trigger_projection_matcher_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
- action_run_id: action_consumer_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
- consumer_name: n5_action_consumer_v1
- result: DRY_RUN_PASS
- passed: True
- P0/P1/P2: 0/0/0

## Baseline Comparison

- baseline_kind: N4_projection_matcher_execute_preflight
- same_trigger_run: True
- current_read_event_count: 3962
- baseline_read_event_count: 3962
- read_event_count_delta: 0
- same_event_distribution: True
- same_signal_distribution: True
- explanation: N5 current-real dry-run read_event_count and distributions match the N4 projection matcher execute preflight

## Consumer Plan

- read_event_count: 3962
- would_insert_inbox_count: 3962
- checkpoint_write_plan_count: 1969

## Action Plan

- planned_action_fact_count: 478
- quality_plan_only_count: 3484
- would_insert_common_action_event_count: 478
- by_target_action_fact_table: {'index_action_fact': 2, 'stock_action_fact': 476}

## Output Event Plan

- by_event_type: {'ActionEligible': 478, 'ActionBlocked': 0, 'ActionExecuted': 0, 'ActionSkipped': 0}

## Boundary

- dry-run/preflight only: no DB writes
- N6/voice/sim/mobile/real trade not touched
- worker not started
