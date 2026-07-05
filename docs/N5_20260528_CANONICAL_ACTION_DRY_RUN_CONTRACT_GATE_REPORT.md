# N5-20260528-canonical-action-dry-run-contract-gate Action Consumer Run-Once Dry-Run Report

## Summary

- stage: N5-20260528-canonical-action-dry-run-contract-gate
- layer_role: N5_action
- consumer_name: n5_action_consumer_v1
- source_trigger_run_id: trigger_execute_20260528_condition_layer_20260527_source_20260527_v2
- action_run_id: action_consumer_canonical_dry_run_20260528_trigger_execute_20260528_condition_layer_20260527_source_20260527_v2
- for_trade_date: 20260528
- rollback_sql_path: None
- P0/P1/P2: 0/0/0
- passed: True

## Source Run Guard

- configured: True
- passed: True
- allowed_source_run_ids: ['trigger_execute_20260528_condition_layer_20260527_source_20260527_v2']
- denied_source_run_ids: ['trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute', 'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute', 'trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249']
- denied_observed_source_run_ids: []
- outside_allowlist_source_run_ids: []

## Baseline Check

- baseline_report_path: inline:N4_20260528_V2_canonical_trigger_execute_contract
- baseline_available: True
- explainable: True
- current_read_event_count: 17774
- baseline_read_event_count: 17774
- read_event_count_delta: 0
- explanation: N5 dry-run read_event_count and distributions match the N4 execute report for the same run

## N4 Outbox Statistics

- outbox_row_count: 17774
- source_run_id: {'trigger_execute_20260528_condition_layer_20260527_source_20260527_v2': 17774}
- only_expected_source_run_id: True
- unexpected_source_run_id_count: 0
- by_event_type: {'TriggerMatched': 4285, 'TriggerPendingMarketData': 4602, 'TriggerStateChanged': 8887}
- by_signal_type: {'B_BUY': 9152, 'S_SELL': 8622}
- by_asset_kind: {'board': 1054, 'index': 80, 'stock': 16640}
- by_direction: {'buy': 9152, 'sell': 8622}
- TriggerMatched: 4285
- TriggerPendingMarketData: 4602
- TriggerCleared: 0
- BUY_HINT runtime signal matched/pending/total: 0/0/0
- SELL_HINT runtime signal matched/pending/total: 0/0/0
- BUY_HINT trace matched/pending/total: 0/286/572
- SELL_HINT trace matched/pending/total: 0/31/62

## Period Trigger Baseline Trace

- present_count: 17774
- missing_count: 0
- null_count: 0
- empty_object_count: 0
- present_flag_true_count: 17774
- present_flag_false_count: 0
- required_period_not_ready_count: 0
- by_trigger_period: {'30m': 9204, 'D': 6436, 'M': 738, 'Q': 160, 'W': 1154, 'Y': 82}
- present_by_trigger_period: {'30m': 9204, 'D': 6436, 'M': 738, 'Q': 160, 'W': 1154, 'Y': 82}
- missing_by_trigger_period: {}
- baseline_versions: {'N2-R4-period-trigger-baseline-v1': 17774}

## Consumer Plan

- read_event_count: 17774
- planned_receive_count: 17774
- skipped_count: 0
- ordering: ['partition_key', 'event_time', 'outbox_id', 'event_id']
- partition_count: 2146
- checkpoint_write_plan_count: 2146
- would_insert_inbox_count: 17774
- would_update_checkpoint_count: 2146
- would_consume_outbox_count: 0

## Action Write Plan

- candidate_count: 17774
- action_candidate_count: 4285
- quality_plan_count: 4602
- planned_action_fact_count: 4285
- quality_plan_only_count: 4602
- by_target_action_fact_table: {'board_action_fact': 254, 'index_action_fact': 18, 'stock_action_fact': 4013}
- planned_action_fact_by_signal_type: {'B_BUY': 2145, 'S_SELL': 2140}
- planned_action_fact_by_direction: {'buy': 2145, 'sell': 2140}
- action_state: {'blocked': 8887, 'eligible': 4285, 'expired': 4602}
- confirmation_status: {'expired': 4602, 'failed': 4285, 'pending': 8887}
- BUY_HINT planned action fact count: 0
- SELL_HINT planned action fact count: 0
- BUY_HINT trace count: 572
- SELL_HINT trace count: 62
- deprecated_runtime_signal_type_count: 0
- deprecated_hint_event_plan_count: 0
- pending_action_fact_plan_count: 0
- duplicate_source_trigger_match_id_skipped_count: 0
- duplicate_source_trigger_match_id_planned_count: 0
- physical_split_error_count: 0

## N5 Output Event Plan

- event_type_contract: ['ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped']
- by_event_type: {'ActionEligible': 0, 'ActionBlocked': 4285, 'ActionExecuted': 0, 'ActionSkipped': 0}
- planned_event_count: 4285
- common_event_outbox_written: False
- executed_count: 0

## Row Count Guards

- before_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 100837, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 2952, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 2803, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 1, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 276, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 488, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 488, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}
- after_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 100837, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 2952, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 2803, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 1, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 276, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 488, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 488, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}

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