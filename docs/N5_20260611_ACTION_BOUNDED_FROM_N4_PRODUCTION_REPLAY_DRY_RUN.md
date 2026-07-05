# N5-20260611-action-bounded-from-n4-production-replay Action Consumer Run-Once Dry-Run Report

## Summary

- stage: N5-20260611-action-bounded-from-n4-production-replay
- layer_role: N5_action
- consumer_name: n5_action_consumer_v1
- source_trigger_run_id: n4_production_semantic_replay_20260611_market_snapshot_updated_v1
- action_run_id: n5_action_bounded_20260611_from_n4_production_semantic_replay_v1
- for_trade_date: 20260611
- rollback_sql_path: sql/N5_20260611_action_bounded_from_n4_production_replay_rollback.sql
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

- baseline_report_path: docs/N4_20260611_MARKET_SNAPSHOT_UPDATED_PRODUCTION_TRIGGER_SEMANTIC_REPLAY_EXECUTE_REPORT.json
- baseline_available: True
- explainable: True
- current_read_event_count: 799
- baseline_read_event_count: 799
- read_event_count_delta: 0
- explanation: N5 current-real dry-run read_event_count and distributions match the N4 projection matcher execute preflight

## N4 Outbox Statistics

- outbox_row_count: 799
- source_run_id: {'n4_production_semantic_replay_20260611_market_snapshot_updated_v1': 799}
- only_expected_source_run_id: True
- unexpected_source_run_id_count: 0
- by_event_type: {'TriggerMatched': 548, 'TriggerPendingMarketData': 251}
- by_signal_type: {'B_BUY': 615, 'S_SELL': 184}
- by_asset_kind: {'board': 253, 'index': 54, 'stock': 492}
- by_direction: {'buy': 615, 'sell': 184}
- TriggerMatched: 548
- TriggerPendingMarketData: 251
- TriggerCleared: 0
- BUY_HINT runtime signal matched/pending/total: 0/0/0
- SELL_HINT runtime signal matched/pending/total: 0/0/0
- BUY_HINT trace matched/pending/total: 18/0/18
- SELL_HINT trace matched/pending/total: 9/0/9

## Period Trigger Baseline Trace

- present_count: 799
- missing_count: 0
- null_count: 0
- empty_object_count: 0
- present_flag_true_count: 799
- present_flag_false_count: 0
- required_period_not_ready_count: 0
- by_trigger_period: {'30m': 278, 'D': 149, 'M': 123, 'Q': 83, 'W': 81, 'Y': 85}
- present_by_trigger_period: {'30m': 278, 'D': 149, 'M': 123, 'Q': 83, 'W': 81, 'Y': 85}
- missing_by_trigger_period: {}
- baseline_versions: {'N2-R4-period-trigger-baseline-v1': 799}

## Consumer Plan

- read_event_count: 799
- planned_receive_count: 799
- skipped_count: 0
- ordering: ['partition_key', 'event_time', 'outbox_id', 'event_id']
- partition_count: 668
- checkpoint_write_plan_count: 668
- would_insert_inbox_count: 799
- would_update_checkpoint_count: 668
- would_consume_outbox_count: 0

## Action Write Plan

- candidate_count: 799
- action_candidate_count: 548
- quality_plan_count: 251
- planned_action_fact_count: 548
- quality_plan_only_count: 251
- by_target_action_fact_table: {'board_action_fact': 2, 'index_action_fact': 54, 'stock_action_fact': 492}
- planned_action_fact_by_signal_type: {'B_BUY': 489, 'S_SELL': 59}
- planned_action_fact_by_direction: {'buy': 489, 'sell': 59}
- action_state: {'blocked': 799}
- confirmation_status: {'failed': 548, 'pending': 251}
- BUY_HINT planned action fact count: 18
- SELL_HINT planned action fact count: 9
- BUY_HINT trace count: 18
- SELL_HINT trace count: 9
- deprecated_runtime_signal_type_count: 0
- deprecated_hint_event_plan_count: 0
- pending_action_fact_plan_count: 0
- duplicate_source_trigger_match_id_skipped_count: 0
- duplicate_source_trigger_match_id_planned_count: 0
- physical_split_error_count: 0

## N5 Output Event Plan

- event_type_contract: ['ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped']
- by_event_type: {'ActionEligible': 0, 'ActionBlocked': 548, 'ActionExecuted': 0, 'ActionSkipped': 0}
- planned_event_count: 548
- common_event_outbox_written: False
- executed_count: 0

## Row Count Guards

- before_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 201543, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 117111, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 25811, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 18, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 36123, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 16765, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 366, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 1600, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 18731, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}
- after_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 201543, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 117111, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 25811, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 18, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 36123, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 16765, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 366, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 1600, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 18731, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}

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