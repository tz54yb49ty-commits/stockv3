# N5-current-real Action Consumer Run-Once Dry-Run Report

## Summary

- stage: N5-current-real
- layer_role: N5_action
- consumer_name: n5_action_consumer_v1
- source_trigger_run_id: trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249
- action_run_id: action_consumer_current_real_dry_run_20260525_trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249
- for_trade_date: 20260525
- rollback_sql_path: sql/N5_current_real_action_execute_rollback.sql
- P0/P1/P2: 0/0/0
- passed: True

## Source Run Guard

- configured: True
- passed: True
- allowed_source_run_ids: ['trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249']
- denied_source_run_ids: ['trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute', 'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute']
- denied_observed_source_run_ids: []
- outside_allowlist_source_run_ids: []

## Baseline Check

- baseline_report_path: docs/N4_PROJECTION_MATCHER_EXECUTE_PREFLIGHT_REPORT.json
- baseline_available: True
- explainable: True
- current_read_event_count: 764
- baseline_read_event_count: 764
- read_event_count_delta: 0
- explanation: N5 current-real dry-run read_event_count and distributions match the N4 projection matcher execute preflight

## N4 Outbox Statistics

- outbox_row_count: 764
- source_run_id: {'trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249': 764}
- only_expected_source_run_id: True
- unexpected_source_run_id_count: 0
- by_event_type: {'TriggerMatched': 488, 'TriggerPendingMarketData': 276}
- by_signal_type: {'BUY_HINT': 6, 'B_BUY_30M_VOL': 441, 'SELL_HINT': 7, 'S_SELL_30M_SHRINK': 310}
- by_asset_kind: {'board': 258, 'stock': 506}
- by_direction: {'buy': 447, 'sell': 317}
- TriggerMatched: 488
- TriggerPendingMarketData: 276
- TriggerCleared: 0
- BUY_HINT matched/pending/total: 6/0/6
- SELL_HINT matched/pending/total: 3/4/7

## Period Trigger Baseline Trace

- present_count: 764
- missing_count: 0
- null_count: 0
- empty_object_count: 0
- present_flag_true_count: 764
- present_flag_false_count: 0
- required_period_not_ready_count: 0
- by_trigger_period: {'30m': 764}
- present_by_trigger_period: {'30m': 764}
- missing_by_trigger_period: {}
- baseline_versions: {'N2-R4-period-trigger-baseline-v1': 764}

## Consumer Plan

- read_event_count: 764
- planned_receive_count: 764
- skipped_count: 0
- ordering: ['partition_key', 'event_time', 'outbox_id', 'event_id']
- partition_count: 615
- checkpoint_write_plan_count: 615
- would_insert_inbox_count: 764
- would_update_checkpoint_count: 615
- would_consume_outbox_count: 0

## Action Write Plan

- candidate_count: 764
- action_candidate_count: 488
- quality_plan_count: 276
- planned_action_fact_count: 488
- quality_plan_only_count: 276
- by_target_action_fact_table: {'stock_action_fact': 488}
- planned_action_fact_by_signal_type: {'BUY_HINT': 6, 'B_BUY_30M_VOL': 305, 'SELL_HINT': 3, 'S_SELL_30M_SHRINK': 174}
- planned_action_fact_by_direction: {'buy': 311, 'sell': 177}
- BUY_HINT planned action fact count: 6
- SELL_HINT planned action fact count: 3
- pending_action_fact_plan_count: 0
- duplicate_source_trigger_match_id_skipped_count: 0
- duplicate_source_trigger_match_id_planned_count: 0
- physical_split_error_count: 0

## N5 Output Event Plan

- event_type_contract: ['ActionEvent', 'HintEvent', 'RiskEvent', 'PositionEvent']
- by_event_type: {'ActionEvent': 479, 'HintEvent': 9, 'RiskEvent': 0, 'PositionEvent': 0}
- planned_event_count: 488
- common_event_outbox_written: False
- executed_count: 0

## Row Count Guards

- before_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 56256, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 2188, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 2188, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 0, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}
- after_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 56256, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 2188, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 2188, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 0, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}

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
- Current-real mode must use the registered N4 projection matcher source_run_id and must reject the synthetic denylist.