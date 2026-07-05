# N5-R4 Action Consumer Run-Once Dry-Run Report

## Summary

- stage: N5-R4
- layer_role: N5_action
- consumer_name: n5_action_consumer_v1
- source_trigger_run_id: trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute
- action_run_id: action_consumer_run_once_dry_run_20260525_trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855
- for_trade_date: 20260525
- P0/P1/P2: 0/0/1
- passed: True

## Baseline Check

- baseline_report_path: docs/N4_R4_synthetic_trigger_execute_report.json
- baseline_available: True
- explainable: True
- current_read_event_count: 26652
- baseline_read_event_count: 26652
- read_event_count_delta: 0
- explanation: N5 dry-run read_event_count and distributions match the N4 execute report for the same run

## N4 Outbox Statistics

- outbox_row_count: 26652
- source_run_id: {'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute': 26652}
- only_expected_source_run_id: True
- unexpected_source_run_id_count: 0
- by_event_type: {'TriggerMatched': 8884, 'TriggerPendingMarketData': 17768}
- by_signal_type: {'BUY_HINT': 213, 'B_BUY': 6561, 'B_BUY_30M_VOL': 6561, 'SELL_HINT': 207, 'S_SELL': 6555, 'S_SELL_30M_SHRINK': 6555}
- by_asset_kind: {'board': 1536, 'index': 108, 'stock': 25008}
- by_direction: {'buy': 13335, 'sell': 13317}
- TriggerMatched: 8884
- TriggerPendingMarketData: 17768
- TriggerCleared: 0
- BUY_HINT matched/pending/total: 71/142/213
- SELL_HINT matched/pending/total: 69/138/207

## Period Trigger Baseline Trace

- present_count: 26652
- missing_count: 0
- null_count: 0
- empty_object_count: 0
- present_flag_true_count: 26652
- present_flag_false_count: 0
- required_period_not_ready_count: 0
- by_trigger_period: {'30m': 13536, 'D': 11022, 'M': 765, 'Q': 258, 'W': 903, 'Y': 168}
- present_by_trigger_period: {'30m': 13536, 'D': 11022, 'M': 765, 'Q': 258, 'W': 903, 'Y': 168}
- missing_by_trigger_period: {}
- baseline_versions: {'N2-R4-period-trigger-baseline-v1': 26652}

## Consumer Plan

- read_event_count: 26652
- planned_receive_count: 26652
- skipped_count: 0
- ordering: ['partition_key', 'event_time', 'outbox_id', 'event_id']
- partition_count: 2188
- checkpoint_write_plan_count: 2188
- would_insert_inbox_count: 26652
- would_update_checkpoint_count: 2188
- would_consume_outbox_count: 0

## Action Write Plan

- candidate_count: 26652
- action_candidate_count: 8884
- quality_plan_count: 17768
- planned_action_fact_count: 8884
- quality_plan_only_count: 17768
- by_target_action_fact_table: {'board_action_fact': 512, 'index_action_fact': 36, 'stock_action_fact': 8336}
- planned_action_fact_by_signal_type: {'BUY_HINT': 71, 'B_BUY': 2187, 'B_BUY_30M_VOL': 2187, 'SELL_HINT': 69, 'S_SELL': 2185, 'S_SELL_30M_SHRINK': 2185}
- planned_action_fact_by_direction: {'buy': 4445, 'sell': 4439}
- BUY_HINT planned action fact count: 71
- SELL_HINT planned action fact count: 69
- pending_action_fact_plan_count: 0
- duplicate_source_trigger_match_id_skipped_count: 0
- duplicate_source_trigger_match_id_planned_count: 0
- physical_split_error_count: 0

## N5 Output Event Plan

- event_type_contract: ['ActionEvent', 'HintEvent', 'RiskEvent', 'PositionEvent']
- by_event_type: {'ActionEvent': 8744, 'HintEvent': 140, 'RiskEvent': 0, 'PositionEvent': 0}
- planned_event_count: 8884
- common_event_outbox_written: False
- executed_count: 0

## Row Count Guards

- before_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 53304, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 0, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}
- after_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 53304, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 0, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}

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
- The current N4 outbox is synthetic/sample run-once material for N5 development validation.