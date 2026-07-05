# V3_20260612_N5_ACTION_MARK_ALIGNED_REPLAY Action Consumer Run-Once Dry-Run Report

## Summary

- stage: V3_20260612_N5_ACTION_MARK_ALIGNED_REPLAY
- layer_role: N5_action
- consumer_name: n5_action_consumer_v1
- source_trigger_run_id: v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1
- action_run_id: v3_n5_action_mark_aligned_replay_20260612_from_n4_action_confirmation_metric_after_n3_repair_v1
- for_trade_date: 20260612
- rollback_sql_path: sql/V3_20260612_n5_action_mark_aligned_replay_rollback.sql
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

- baseline_report_path: docs/V3_20260612_N5_ACTION_CONSUMER_DRY_RUN_AFTER_N4_ACTION_CONFIRMATION_METRIC.json
- baseline_available: True
- explainable: True
- current_read_event_count: 4454
- baseline_read_event_count: 4454
- read_event_count_delta: 0
- explanation: N5-5 read_event_count and distributions match the N5-1 baseline for the same N4 run

## N4 Outbox Statistics

- outbox_row_count: 4454
- source_run_id: {'v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1': 4454}
- only_expected_source_run_id: True
- unexpected_source_run_id_count: 0
- by_event_type: {'TriggerMatched': 49, 'TriggerPendingMarketData': 4405}
- by_signal_type: {'B_BUY': 2220, 'S_SELL': 2234}
- by_asset_kind: {'board': 273, 'index': 199, 'stock': 3982}
- by_direction: {'buy': 2220, 'sell': 2234}
- TriggerMatched: 49
- TriggerPendingMarketData: 4405
- TriggerStateChanged: 0
- BUY_HINT runtime signal matched/pending/total: 0/0/0
- SELL_HINT runtime signal matched/pending/total: 0/0/0
- BUY_HINT trace matched/pending/total: 5/133/138
- SELL_HINT trace matched/pending/total: 1/158/159

## Period Trigger Baseline Trace

- present_count: 4454
- missing_count: 0
- null_count: 0
- empty_object_count: 0
- present_flag_true_count: 4454
- present_flag_false_count: 0
- required_period_not_ready_count: 0
- by_trigger_period: {'30m': 4454}
- present_by_trigger_period: {'30m': 4454}
- missing_by_trigger_period: {}
- baseline_versions: {'N2-R4-period-trigger-baseline-v1': 4454}

## Consumer Plan

- read_event_count: 4454
- planned_receive_count: 4454
- skipped_count: 0
- ordering: ['partition_key', 'event_time', 'outbox_id', 'event_id']
- partition_count: 2082
- checkpoint_write_plan_count: 2082
- would_insert_inbox_count: 4454
- would_update_checkpoint_count: 2082
- would_consume_outbox_count: 0

## Action Write Plan

- candidate_count: 4454
- action_candidate_count: 49
- quality_plan_count: 4405
- planned_action_fact_count: 43
- quality_plan_only_count: 4405
- by_target_action_fact_table: {'board_action_fact': 10, 'stock_action_fact': 33}
- planned_action_fact_by_signal_type: {'B_BUY': 39, 'S_SELL': 4}
- planned_action_fact_by_direction: {'buy': 39, 'sell': 4}
- action_state: {'blocked': 4405, 'executed': 49}
- confirmation_status: {'passed': 49, 'pending': 4405}
- BUY_HINT planned action fact count: 5
- SELL_HINT planned action fact count: 1
- BUY_HINT trace count: 138
- SELL_HINT trace count: 159
- deprecated_runtime_signal_type_count: 0
- deprecated_hint_event_plan_count: 0
- pending_action_fact_plan_count: 0
- duplicate_source_trigger_match_id_skipped_count: 0
- duplicate_source_trigger_match_id_planned_count: 0
- physical_split_error_count: 0

## N5 Output Event Plan

- event_type_contract: ['ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped']
- by_event_type: {'ActionEligible': 0, 'ActionBlocked': 0, 'ActionExecuted': 43, 'ActionSkipped': 0}
- planned_event_count: 43
- common_event_outbox_written: False
- executed_count: 0

## Row Count Guards

- before_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 236749, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 128675, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 36386, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 22, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 36374, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 19693, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 420, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 1603, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 21716, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}
- after_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 236749, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 128675, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 36386, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 22, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 36374, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 19693, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 420, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 1603, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 21716, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}

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
- BUY_HINT / SELL_HINT are condition trace only and do not map to legacy hint events in N5 canonical runtime.
- Source-run allowlist and historical synthetic/current-real denylist are enforced by this gate.