# N5-20260602-1105-mock-from-N4-preflight Action Consumer Run-Once Dry-Run Report

## Summary

- stage: N5-20260602-1105-mock-from-N4-preflight
- layer_role: N5_action
- consumer_name: n5_action_consumer_v1
- source_trigger_run_id: trigger_projection_matcher_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
- action_run_id: action_consumer_20260602_1105_mock_from_n4_projection_matcher_preflight
- for_trade_date: 20260602
- rollback_sql_path: sql/N5_20260602_1105_mock_noop_rollback.sql
- P0/P1/P2: 0/0/0
- passed: True

## Source Run Guard

- configured: True
- passed: True
- allowed_source_run_ids: ['trigger_projection_matcher_execute_20260602_1105__condition_layer_20260601_source_20260601_v1']
- denied_source_run_ids: []
- denied_observed_source_run_ids: []
- outside_allowlist_source_run_ids: []

## Baseline Check

- baseline_report_path: docs/N4_20260602_projection_matcher_1105_after_context_execute_preflight.json
- baseline_available: True
- explainable: True
- current_read_event_count: 3962
- baseline_read_event_count: 3962
- read_event_count_delta: 0
- explanation: N5 current-real dry-run read_event_count and distributions match the N4 projection matcher execute preflight

## N4 Outbox Statistics

- outbox_row_count: 3962
- source_run_id: {'trigger_projection_matcher_execute_20260602_1105__condition_layer_20260601_source_20260601_v1': 3962}
- only_expected_source_run_id: True
- unexpected_source_run_id_count: 0
- by_event_type: {'TriggerMatched': 478, 'TriggerPendingMarketData': 3484}
- by_signal_type: {'B_BUY': 1888, 'S_SELL': 2074}
- by_asset_kind: {'board': 1006, 'index': 60, 'stock': 2896}
- by_direction: {'buy': 1888, 'sell': 2074}
- TriggerMatched: 478
- TriggerPendingMarketData: 3484
- TriggerCleared: 0
- BUY_HINT runtime signal matched/pending/total: 0/0/0
- SELL_HINT runtime signal matched/pending/total: 0/0/0
- BUY_HINT trace matched/pending/total: 71/66/137
- SELL_HINT trace matched/pending/total: 106/84/190

## Period Trigger Baseline Trace

- present_count: 3962
- missing_count: 0
- null_count: 0
- empty_object_count: 0
- present_flag_true_count: 3962
- present_flag_false_count: 0
- required_period_not_ready_count: 0
- by_trigger_period: {'30m': 3962}
- present_by_trigger_period: {'30m': 3962}
- missing_by_trigger_period: {}
- baseline_versions: {'N2-R4-period-trigger-baseline-v1': 3962}

## Consumer Plan

- read_event_count: 3962
- planned_receive_count: 3962
- skipped_count: 0
- ordering: ['partition_key', 'event_time', 'outbox_id', 'event_id']
- partition_count: 1969
- checkpoint_write_plan_count: 1969
- would_insert_inbox_count: 3962
- would_update_checkpoint_count: 1969
- would_consume_outbox_count: 0

## Action Write Plan

- candidate_count: 3962
- action_candidate_count: 478
- quality_plan_count: 3484
- planned_action_fact_count: 478
- quality_plan_only_count: 3484
- by_target_action_fact_table: {'index_action_fact': 2, 'stock_action_fact': 476}
- planned_action_fact_by_signal_type: {'B_BUY': 154, 'S_SELL': 324}
- planned_action_fact_by_direction: {'buy': 154, 'sell': 324}
- action_state: {'blocked': 3484, 'eligible': 478}
- confirmation_status: {'pending': 3962}
- BUY_HINT planned action fact count: 71
- SELL_HINT planned action fact count: 106
- BUY_HINT trace count: 137
- SELL_HINT trace count: 190
- deprecated_runtime_signal_type_count: 0
- deprecated_hint_event_plan_count: 0
- pending_action_fact_plan_count: 0
- duplicate_source_trigger_match_id_skipped_count: 0
- duplicate_source_trigger_match_id_planned_count: 0
- physical_split_error_count: 0

## N5 Output Event Plan

- event_type_contract: ['ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped']
- by_event_type: {'ActionEligible': 478, 'ActionBlocked': 0, 'ActionExecuted': 0, 'ActionSkipped': 0}
- planned_event_count: 478
- common_event_outbox_written: False
- executed_count: 0

## Row Count Guards

- before_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 153828, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 56170, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 4368, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 4, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 13982, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 12575, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 54, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 762, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 13391, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}
- after_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 153828, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 56170, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 4368, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 4, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 13982, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 12575, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 54, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 762, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 13391, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}

## Boundary Confirmation

- writes_performed: False
- common_event_inbox_updated: False
- consumer_checkpoint_updated: False
- action_fact_written: False
- action_event_written: False
- common_event_outbox_written: False
- n5_outbox_written: False
- n4_outbox_consumed: False
- market_data_pulled: False
- n1_n2_n3_n4_modified: False
- n6_user_layer_touched: False
- voice_touched: False
- sim_touched: False
- mobile_touched: False
- real_trade_touched: False
- worker_started: False
- old_system_touched: False

## Notes

- This report is a run-once dry-run only. It plans action writes but executes none of them.
- Canonical mode accepts only B_BUY / S_SELL as runtime signal_type.
- BUY_HINT / SELL_HINT are condition trace only and do not map to HintEvent in N5 canonical runtime.
- Source-run allowlist and historical synthetic/current-real denylist are enforced by this gate.
## Mock Input

```text
mocked = true
source = docs/N4_20260602_projection_matcher_1105_after_context_execute_preflight.json
production_outbox_written = false
```
