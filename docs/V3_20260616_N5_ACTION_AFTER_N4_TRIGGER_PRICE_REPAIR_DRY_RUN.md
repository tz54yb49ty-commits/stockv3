# N5_ACTION_20260616_AFTER_N4_TRIGGER_PRICE_REPAIR_READINESS_CONTRACT_GATE Action Consumer Run-Once Dry-Run Report

## Summary

- stage: N5_ACTION_20260616_AFTER_N4_TRIGGER_PRICE_REPAIR_READINESS_CONTRACT_GATE
- layer_role: N5_action
- consumer_name: n5_action_consumer_v1_20260616_trigger_price_repair_replay
- source_trigger_run_id: v3_n4_trigger_replay_20260616_until_1401_v1
- action_run_id: v3_n5_action_replay_20260616_after_n4_trigger_price_repair_v1
- for_trade_date: 20260616
- rollback_sql_path: sql/V3_20260616_n5_action_after_n4_trigger_price_repair_rollback.sql
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

- baseline_report_path: docs/V3_20260616_N5_ACTION_AFTER_N4_TRIGGER_PRICE_REPAIR_BASELINE.json
- baseline_available: True
- explainable: True
- current_read_event_count: 4698
- baseline_read_event_count: 4698
- read_event_count_delta: 0
- explanation: N5-5 read_event_count and distributions match the N5-1 baseline for the same N4 run

## N4 Outbox Statistics

- outbox_row_count: 4698
- source_run_id: {'v3_n4_trigger_replay_20260616_until_1401_v1': 4698}
- only_expected_source_run_id: True
- unexpected_source_run_id_count: 0
- by_event_type: {'TriggerMatched': 540, 'TriggerPendingMarketData': 4158}
- by_signal_type: {'B_BUY': 2076, 'S_SELL': 2622}
- by_asset_kind: {'board': 307, 'index': 183, 'stock': 4208}
- by_direction: {'buy': 2076, 'sell': 2622}
- TriggerMatched: 540
- TriggerPendingMarketData: 4158
- TriggerStateChanged: 0
- BUY_HINT runtime signal matched/pending/total: 0/0/0
- SELL_HINT runtime signal matched/pending/total: 0/0/0
- BUY_HINT trace matched/pending/total: 3/41/44
- SELL_HINT trace matched/pending/total: 156/434/590

## Period Trigger Baseline Trace

- present_count: 4698
- missing_count: 0
- null_count: 0
- empty_object_count: 0
- present_flag_true_count: 4698
- present_flag_false_count: 0
- required_period_not_ready_count: 0
- by_trigger_period: {'30m': 634, 'D': 221, 'M': 497, 'Q': 351, 'W': 272, 'Y': 2723}
- present_by_trigger_period: {'30m': 634, 'D': 221, 'M': 497, 'Q': 351, 'W': 272, 'Y': 2723}
- missing_by_trigger_period: {}
- baseline_versions: {'N2-R4-period-trigger-baseline-v1': 4698}

## Consumer Plan

- read_event_count: 4698
- planned_receive_count: 4698
- skipped_count: 0
- ordering: ['partition_key', 'event_time', 'outbox_id', 'event_id']
- partition_count: 2032
- checkpoint_write_plan_count: 2032
- would_insert_inbox_count: 4698
- would_update_checkpoint_count: 2032
- would_consume_outbox_count: 0

## Action Write Plan

- candidate_count: 4698
- action_candidate_count: 540
- quality_plan_count: 4158
- planned_action_fact_count: 540
- quality_plan_only_count: 4158
- by_target_action_fact_table: {'board_action_fact': 44, 'index_action_fact': 18, 'stock_action_fact': 478}
- planned_action_fact_by_signal_type: {'B_BUY': 200, 'S_SELL': 340}
- planned_action_fact_by_direction: {'buy': 200, 'sell': 340}
- action_state: {'blocked': 4680, 'executed': 18}
- confirmation_status: {'failed': 522, 'passed': 18, 'pending': 4158}
- BUY_HINT planned action fact count: 3
- SELL_HINT planned action fact count: 156
- BUY_HINT trace count: 44
- SELL_HINT trace count: 590
- deprecated_runtime_signal_type_count: 0
- deprecated_hint_event_plan_count: 0
- pending_action_fact_plan_count: 0
- duplicate_source_trigger_match_id_skipped_count: 0
- duplicate_source_trigger_match_id_planned_count: 0
- physical_split_error_count: 0

## N5 Output Event Plan

- event_type_contract: ['ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped']
- by_event_type: {'ActionEligible': 0, 'ActionBlocked': 522, 'ActionExecuted': 18, 'ActionSkipped': 0}
- planned_event_count: 540
- common_event_outbox_written: False
- executed_count: 0

## Row Count Guards

- before_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 653711, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 187331, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 59693, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 35, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 40070, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 56596, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 2797, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 4659, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 64052, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}
- after_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 653711, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 187331, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 59693, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 35, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 40070, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 56596, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 2797, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 4659, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 64052, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}

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