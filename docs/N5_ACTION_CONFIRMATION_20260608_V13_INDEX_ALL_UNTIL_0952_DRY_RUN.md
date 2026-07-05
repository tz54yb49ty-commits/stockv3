# N5-action-confirmation-20260608-v13-index-all-readiness Action Consumer Run-Once Dry-Run Report

## Summary

- stage: N5-action-confirmation-20260608-v13-index-all-readiness
- layer_role: N5_action
- consumer_name: n5_action_consumer_v1
- source_trigger_run_id: trigger_projection_matcher_execute_20260608_v13_index_all_until_0952
- action_run_id: action_consumer_dry_run_20260608_v13_index_all_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952
- for_trade_date: 20260608
- rollback_sql_path: None
- P0/P1/P2: 0/0/0
- passed: True

## Source Run Guard

- configured: False
- passed: True
- allowed_source_run_ids: []
- denied_source_run_ids: []
- denied_observed_source_run_ids: []
- outside_allowlist_source_run_ids: []

## Baseline Check

- baseline_report_path: docs/N4_PROJECTION_MATCHER_20260608_V13_INDEX_ALL_UNTIL_0952_N5_BASELINE.json
- baseline_available: True
- explainable: True
- current_read_event_count: 3920
- baseline_read_event_count: 3920
- read_event_count_delta: 0
- explanation: N5 current-real dry-run read_event_count and distributions match the N4 projection matcher report

## N4 Outbox Statistics

- outbox_row_count: 3920
- source_run_id: {'trigger_projection_matcher_execute_20260608_v13_index_all_until_0952': 3920}
- only_expected_source_run_id: True
- unexpected_source_run_id_count: 0
- by_event_type: {'TriggerMatched': 320, 'TriggerPendingMarketData': 3600}
- by_signal_type: {'B_BUY': 2116, 'S_SELL': 1804}
- by_asset_kind: {'board': 267, 'index': 163, 'stock': 3490}
- by_direction: {'buy': 2116, 'sell': 1804}
- TriggerMatched: 320
- TriggerPendingMarketData: 3600
- TriggerCleared: 0
- BUY_HINT runtime signal matched/pending/total: 0/0/0
- SELL_HINT runtime signal matched/pending/total: 0/0/0
- BUY_HINT trace matched/pending/total: 116/9/125
- SELL_HINT trace matched/pending/total: 3/4/7

## Period Trigger Baseline Trace

- present_count: 3920
- missing_count: 0
- null_count: 0
- empty_object_count: 0
- present_flag_true_count: 3920
- present_flag_false_count: 0
- required_period_not_ready_count: 0
- by_trigger_period: {'30m': 3920}
- present_by_trigger_period: {'30m': 3920}
- missing_by_trigger_period: {}
- baseline_versions: {'N2-R4-period-trigger-baseline-v1': 3920}

## Consumer Plan

- read_event_count: 3920
- planned_receive_count: 3920
- skipped_count: 0
- ordering: ['partition_key', 'event_time', 'outbox_id', 'event_id']
- partition_count: 1997
- checkpoint_write_plan_count: 1997
- would_insert_inbox_count: 3920
- would_update_checkpoint_count: 1997
- would_consume_outbox_count: 0

## Action Write Plan

- candidate_count: 3920
- action_candidate_count: 320
- quality_plan_count: 3600
- planned_action_fact_count: 201
- quality_plan_only_count: 3600
- by_target_action_fact_table: {'index_action_fact': 6, 'stock_action_fact': 195}
- planned_action_fact_by_signal_type: {'B_BUY': 197, 'S_SELL': 4}
- planned_action_fact_by_direction: {'buy': 197, 'sell': 4}
- action_state: {'blocked': 3600, 'eligible': 320}
- confirmation_status: {'pending': 3920}
- BUY_HINT planned action fact count: 116
- SELL_HINT planned action fact count: 3
- BUY_HINT trace count: 125
- SELL_HINT trace count: 7
- deprecated_runtime_signal_type_count: 0
- deprecated_hint_event_plan_count: 0
- pending_action_fact_plan_count: 0
- duplicate_source_trigger_match_id_skipped_count: 0
- duplicate_source_trigger_match_id_planned_count: 0
- physical_split_error_count: 0

## N5 Output Event Plan

- event_type_contract: ['ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped']
- by_event_type: {'ActionEligible': 201, 'ActionBlocked': 0, 'ActionExecuted': 0, 'ActionSkipped': 0}
- planned_event_count: 201
- common_event_outbox_written: False
- executed_count: 0

## Row Count Guards

- before_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 194811, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 92517, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 5184, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 9, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 32316, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 15360, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 120, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 1114, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 16594, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}
- after_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 194811, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 92517, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 5184, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 9, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 32316, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 15360, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 120, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 1114, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 16594, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}

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