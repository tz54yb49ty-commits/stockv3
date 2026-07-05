# N5-R4 Action Execute Preflight Report

## Summary

- stage: N5-R4-execute-preflight
- layer_role: N5_action
- source_trigger_run_id: trigger_projection_matcher_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
- action_run_id: action_consumer_20260602_1105__trigger_projection_matcher_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
- consumer_name: n5_action_consumer_v1
- P0/P1/P2: 2/1/0
- allow_execute: False

## Source Outbox

- read_event_count: 0
- source_run_id_summary: {'expected_source_run_id': 'trigger_projection_matcher_execute_20260602_1105__condition_layer_20260601_source_20260601_v1', 'by_source_run_id': {}, 'only_expected_source_run_id': False, 'unexpected_source_run_id_count': 0, 'unexpected_source_run_ids': {}}
- by_event_type: {}
- by_signal_type: {}
- BUY_HINT matched/pending/total: 0/0/0
- SELL_HINT matched/pending/total: 0/0/0

## Event Type Mapping

- rules: {'TriggerMatched': 'action_fact plan', 'TriggerPendingMarketData': 'quality only, no action fact and no N5 outbox event', 'BUY_HINT': 'condition trace only; runtime signal_type remains B_BUY', 'SELL_HINT': 'condition trace only; runtime signal_type remains S_SELL', 'B_BUY': 'canonical buy runtime signal', 'S_SELL': 'canonical sell runtime signal', 'canonical_outputs': 'ActionEligible, ActionBlocked, ActionExecuted, ActionSkipped'}
- by_signal_type_and_output_event_type: {}
- hint_signal_action_fact_count: 0
- ordinary_signal_action_fact_count: 0
- pending_action_fact_plan_count: 0
- mapping_violation_count: 0

## Trace Mapping

- rule: period_trigger_baseline_trace is carried inside source_market_trace JSONB; no dedicated action fact column
- target_field: source_market_trace.period_trigger_baseline_trace
- planned_action_fact_count: 0
- trace_present_in_action_fact_plan_count: 0
- trace_missing_in_action_fact_plan_count: 0
- source_market_trace_missing_tables: []
- dedicated_period_trace_columns: {'stock_action_fact': [], 'index_action_fact': [], 'board_action_fact': []}

## Idempotency / Checkpoint Plan

- ordering: ['partition_key', 'event_time', 'outbox_id', 'event_id']
- dedup_keys: ['consumer_name + event_id', 'consumer_name + source_layer + event_type + source_run_id + dedup_key + event_schema_version']
- checkpoint_key: consumer_name + partition_key + source_layer
- checkpoint_write_plan_count: 0
- would_insert_inbox_count: 0
- would_update_checkpoint_count: 0
- would_consume_outbox_count: 0
- action_key_stable_on_recompute: True
- duplicate_action_key_count: 0
- duplicate_dedup_key_count: 0
- executed: False

## Row Count Guards

- before_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 153828, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 56170, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 4368, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 4, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 13982, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 12575, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 54, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 762, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 13391, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}
- after_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 153828, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 56170, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 4368, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 4, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 13982, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 12575, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 54, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 762, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 13391, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}

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

- allow_execute: False
- This preflight did not execute database writes or consume outbox rows.