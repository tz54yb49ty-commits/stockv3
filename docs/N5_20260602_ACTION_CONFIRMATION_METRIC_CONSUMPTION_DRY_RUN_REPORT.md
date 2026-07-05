# N5-20260602-action-confirmation-metric-consumption Action Consumer Run-Once Dry-Run Report

## Summary

- stage: N5-20260602-action-confirmation-metric-consumption
- layer_role: N5_action
- consumer_name: n5_action_consumer_v1
- source_trigger_run_id: trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
- action_run_id: action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
- for_trade_date: 20260602
- rollback_sql_path: sql/N5_20260602_action_confirmation_metric_execute_rollback.sql
- P0/P1/P2: 0/0/0
- passed: True

## Source Run Guard

- configured: True
- passed: True
- allowed_source_run_ids: ['trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1']
- denied_source_run_ids: ['trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute', 'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute', 'trigger_execute_20260528_condition_layer_20260527_source_20260527_v2', 'trigger_execute_20260529_condition_layer_20260528_source_20260528_v1', 'trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249']
- denied_observed_source_run_ids: []
- outside_allowlist_source_run_ids: []

## Baseline Check

- baseline_report_path: docs/N4_action_confirmation_metric_business_execute_contract.json
- baseline_available: True
- explainable: True
- current_read_event_count: 5941
- baseline_read_event_count: 5941
- read_event_count_delta: 0
- explanation: N5 action-confirmation metric dry-run read_event_count and distributions match the N4 metric execute contract

## N4 Outbox Statistics

- outbox_row_count: 5941
- source_run_id: {'trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1': 5941}
- only_expected_source_run_id: True
- unexpected_source_run_id_count: 0
- by_event_type: {'TriggerMatched': 6, 'TriggerPendingMarketData': 5935}
- by_signal_type: {'B_BUY': 3074, 'S_SELL': 2867}
- by_asset_kind: {'board': 1006, 'index': 220, 'stock': 4715}
- by_direction: {'buy': 3074, 'sell': 2867}
- TriggerMatched: 6
- TriggerPendingMarketData: 5935
- TriggerCleared: 0
- BUY_HINT runtime signal matched/pending/total: 0/0/0
- SELL_HINT runtime signal matched/pending/total: 0/0/0
- BUY_HINT trace matched/pending/total: 1/586/587
- SELL_HINT trace matched/pending/total: 0/382/382

## Period Trigger Baseline Trace

- present_count: 5941
- missing_count: 0
- null_count: 0
- empty_object_count: 0
- present_flag_true_count: 5941
- present_flag_false_count: 0
- required_period_not_ready_count: 0
- by_trigger_period: {'30m': 5941}
- present_by_trigger_period: {'30m': 5941}
- missing_by_trigger_period: {}
- baseline_versions: {'N2-R4-period-trigger-baseline-v1': 5941}

## Consumer Plan

- read_event_count: 5941
- planned_receive_count: 5941
- skipped_count: 0
- ordering: ['partition_key', 'event_time', 'outbox_id', 'event_id']
- partition_count: 2487
- checkpoint_write_plan_count: 2487
- would_insert_inbox_count: 5941
- would_update_checkpoint_count: 2487
- would_consume_outbox_count: 0

## Action Write Plan

- candidate_count: 5941
- action_candidate_count: 6
- quality_plan_count: 5935
- planned_action_fact_count: 5
- quality_plan_only_count: 5935
- by_target_action_fact_table: {'index_action_fact': 4, 'stock_action_fact': 1}
- planned_action_fact_by_signal_type: {'B_BUY': 1, 'S_SELL': 4}
- planned_action_fact_by_direction: {'buy': 1, 'sell': 4}
- action_state: {'blocked': 5937, 'executed': 4}
- confirmation_status: {'failed': 2, 'passed': 4, 'pending': 5935}
- BUY_HINT planned action fact count: 1
- SELL_HINT planned action fact count: 0
- BUY_HINT trace count: 587
- SELL_HINT trace count: 382
- deprecated_runtime_signal_type_count: 0
- deprecated_hint_event_plan_count: 0
- pending_action_fact_plan_count: 0
- duplicate_source_trigger_match_id_skipped_count: 0
- duplicate_source_trigger_match_id_planned_count: 0
- physical_split_error_count: 0

## N5 Output Event Plan

- event_type_contract: ['ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped']
- by_event_type: {'ActionEligible': 0, 'ActionBlocked': 1, 'ActionExecuted': 4, 'ActionSkipped': 0}
- planned_event_count: 5
- common_event_outbox_written: False
- executed_count: 0

## Row Count Guards

- before_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 164209, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 62619, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 5115, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 5, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 17466, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 13051, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 56, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 762, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 13869, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}
- after_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 164209, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 62619, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 5115, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 5, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 17466, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 13051, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 56, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 762, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 13869, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}

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