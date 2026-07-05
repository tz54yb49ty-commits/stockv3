# V3_20260615_N5_REPLAY_AFTER_N4_REPAIRED_FORMAL_PRICE_AMOUNT_CHAIN_AND_N3_COVERAGE_REPAIR_CONTRACT_PREFLIGHT_GATE Action Consumer Run-Once Dry-Run Report

## Summary

- stage: V3_20260615_N5_REPLAY_AFTER_N4_REPAIRED_FORMAL_PRICE_AMOUNT_CHAIN_AND_N3_COVERAGE_REPAIR_CONTRACT_PREFLIGHT_GATE
- layer_role: N5_action
- consumer_name: n5_action_consumer_v1
- source_trigger_run_id: n4_20260615_repaired_formal_price_amount_chain_replay_after_n3_coverage_repair_v1
- action_run_id: v3_n5_action_replay_20260615_after_n4_repaired_formal_price_amount_chain_and_n3_coverage_repair_v1
- for_trade_date: 20260615
- rollback_sql_path: sql/V3_20260615_n5_replay_after_n4_repaired_formal_price_amount_chain_and_n3_coverage_repair_rollback.sql
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

- baseline_report_path: docs/V3_20260615_N5_REPLAY_AFTER_N4_REPAIRED_FORMAL_PRICE_AMOUNT_CHAIN_AND_N3_COVERAGE_REPAIR_BASELINE.json
- baseline_available: True
- explainable: True
- current_read_event_count: 4725
- baseline_read_event_count: 4725
- read_event_count_delta: 0
- explanation: N5-5 read_event_count and distributions match the N5-1 baseline for the same N4 run

## N4 Outbox Statistics

- outbox_row_count: 4725
- source_run_id: {'n4_20260615_repaired_formal_price_amount_chain_replay_after_n3_coverage_repair_v1': 4725}
- only_expected_source_run_id: True
- unexpected_source_run_id_count: 0
- by_event_type: {'TriggerMatched': 1029, 'TriggerPendingMarketData': 3696}
- by_signal_type: {'B_BUY': 2210, 'S_SELL': 2515}
- by_asset_kind: {'board': 297, 'index': 205, 'stock': 4223}
- by_direction: {'buy': 2210, 'sell': 2515}
- TriggerMatched: 1029
- TriggerPendingMarketData: 3696
- TriggerStateChanged: 0
- BUY_HINT runtime signal matched/pending/total: 0/0/0
- SELL_HINT runtime signal matched/pending/total: 0/0/0
- BUY_HINT trace matched/pending/total: 33/73/106
- SELL_HINT trace matched/pending/total: 5/410/415

## Period Trigger Baseline Trace

- present_count: 4725
- missing_count: 0
- null_count: 0
- empty_object_count: 0
- present_flag_true_count: 4725
- present_flag_false_count: 0
- required_period_not_ready_count: 0
- by_trigger_period: {'30m': 521, 'D': 350, 'M': 723, 'Q': 286, 'W': 164, 'Y': 2681}
- present_by_trigger_period: {'30m': 521, 'D': 350, 'M': 723, 'Q': 286, 'W': 164, 'Y': 2681}
- missing_by_trigger_period: {}
- baseline_versions: {'N2-R4-period-trigger-baseline-v1': 4725}

## Consumer Plan

- read_event_count: 4725
- planned_receive_count: 4725
- skipped_count: 0
- ordering: ['partition_key', 'event_time', 'outbox_id', 'event_id']
- partition_count: 2104
- checkpoint_write_plan_count: 2104
- would_insert_inbox_count: 4725
- would_update_checkpoint_count: 2104
- would_consume_outbox_count: 0

## Action Write Plan

- candidate_count: 4725
- action_candidate_count: 1029
- quality_plan_count: 3696
- planned_action_fact_count: 1029
- quality_plan_only_count: 3696
- by_target_action_fact_table: {'board_action_fact': 68, 'index_action_fact': 51, 'stock_action_fact': 910}
- planned_action_fact_by_signal_type: {'B_BUY': 834, 'S_SELL': 195}
- planned_action_fact_by_direction: {'buy': 834, 'sell': 195}
- action_state: {'blocked': 4657, 'executed': 68}
- confirmation_status: {'failed': 961, 'passed': 68, 'pending': 3696}
- BUY_HINT planned action fact count: 33
- SELL_HINT planned action fact count: 5
- BUY_HINT trace count: 106
- SELL_HINT trace count: 415
- deprecated_runtime_signal_type_count: 0
- deprecated_hint_event_plan_count: 0
- pending_action_fact_plan_count: 0
- duplicate_source_trigger_match_id_skipped_count: 0
- duplicate_source_trigger_match_id_planned_count: 0
- physical_split_error_count: 0

## N5 Output Event Plan

- event_type_contract: ['ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped']
- by_event_type: {'ActionEligible': 0, 'ActionBlocked': 961, 'ActionExecuted': 68, 'ActionSkipped': 0}
- planned_event_count: 1029
- common_event_outbox_written: False
- executed_count: 0

## Row Count Guards

- before_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 647984, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 182606, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 57597, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 34, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 36374, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 55686, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 2746, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 4591, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 63023, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}
- after_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 647984, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 182606, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 57597, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 34, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 36374, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 55686, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 2746, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 4591, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 63023, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}

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