# N5-R4 Action Execute Preflight Report

## Summary

- stage: N5-R4-execute-preflight
- layer_role: N5_action
- source_trigger_run_id: trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute
- action_run_id: action_consumer_run_once_dry_run_20260525_trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855
- consumer_name: n5_action_consumer_v1
- P0/P1/P2: 0/0/1
- allow_execute: True

## Source Outbox

- read_event_count: 26652
- source_run_id_summary: {'expected_source_run_id': 'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute', 'by_source_run_id': {'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute': 26652}, 'only_expected_source_run_id': True, 'unexpected_source_run_id_count': 0, 'unexpected_source_run_ids': {}}
- by_event_type: {'TriggerMatched': 8884, 'TriggerPendingMarketData': 17768}
- by_signal_type: {'BUY_HINT': 213, 'B_BUY': 6561, 'B_BUY_30M_VOL': 6561, 'SELL_HINT': 207, 'S_SELL': 6555, 'S_SELL_30M_SHRINK': 6555}
- BUY_HINT matched/pending/total: 71/142/213
- SELL_HINT matched/pending/total: 69/138/207

## Event Type Mapping

- rules: {'TriggerMatched': 'action_fact plan', 'TriggerPendingMarketData': 'quality only, no action fact and no N5 outbox event', 'BUY_HINT': 'action_fact + HintEvent', 'SELL_HINT': 'action_fact + HintEvent', 'B_BUY': 'action_fact + ActionEvent', 'B_BUY_30M_VOL': 'action_fact + ActionEvent', 'S_SELL': 'action_fact + ActionEvent', 'S_SELL_30M_SHRINK': 'action_fact + ActionEvent'}
- by_signal_type_and_output_event_type: {'BUY_HINT': {'HintEvent': 71}, 'B_BUY': {'ActionEvent': 2187}, 'B_BUY_30M_VOL': {'ActionEvent': 2187}, 'SELL_HINT': {'HintEvent': 69}, 'S_SELL': {'ActionEvent': 2185}, 'S_SELL_30M_SHRINK': {'ActionEvent': 2185}}
- hint_signal_action_fact_count: 140
- ordinary_signal_action_fact_count: 8744
- pending_action_fact_plan_count: 0
- mapping_violation_count: 0

## Trace Mapping

- rule: period_trigger_baseline_trace is carried inside source_market_trace JSONB; no dedicated action fact column
- target_field: source_market_trace.period_trigger_baseline_trace
- planned_action_fact_count: 8884
- trace_present_in_action_fact_plan_count: 8884
- trace_missing_in_action_fact_plan_count: 0
- source_market_trace_missing_tables: []
- dedicated_period_trace_columns: {'stock_action_fact': [], 'index_action_fact': [], 'board_action_fact': []}

## Idempotency / Checkpoint Plan

- ordering: ['partition_key', 'event_time', 'outbox_id', 'event_id']
- dedup_keys: ['consumer_name + event_id', 'consumer_name + source_layer + event_type + source_run_id + dedup_key + event_schema_version']
- checkpoint_key: consumer_name + partition_key + source_layer
- checkpoint_write_plan_count: 2188
- would_insert_inbox_count: 26652
- would_update_checkpoint_count: 2188
- would_consume_outbox_count: 0
- action_key_stable_on_recompute: True
- duplicate_action_key_count: 0
- duplicate_dedup_key_count: 0
- executed: False

## Row Count Guards

- before_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 53304, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 0, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}
- after_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 53304, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 0, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}

## Boundary Confirmation

- writes_performed: False
- n4_outbox_consumed: False
- common_event_inbox_updated: False
- consumer_checkpoint_updated: False
- action_fact_written: False
- action_event_written: False
- n5_outbox_written: False
- n6_user_layer_touched: False
- voice_touched: False
- sim_touched: False
- mobile_touched: False
- real_trade_touched: False
- market_data_pulled: False
- worker_started: False
- old_system_touched: False

## Decision

- allow_execute: True
- This preflight did not execute database writes or consume outbox rows.