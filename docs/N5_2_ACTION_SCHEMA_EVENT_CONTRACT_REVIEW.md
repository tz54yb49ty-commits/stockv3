# N5-2 Action Schema / Event Contract Review

## Summary

- stage: N5-2
- layer_role: N5_action
- execution_mode: static_review_no_db_no_migration
- schema_path: sql/011_action_layer_schema.sql
- schema_hash: a68fd142552be2bb222d08ab867c11ff509f771b808a9f61801371e78d239383
- P0/P1/P2: 0/0/1
- passed: True

## Schema Contract

- required_tables: ['common_action_run', 'common_action_quality_item', 'stock_action_fact', 'index_action_fact', 'board_action_fact', 'common_action_event', 'common_position_state', 'common_position_event']
- created_tables: ['common_action_run', 'common_action_quality_item', 'stock_action_fact', 'index_action_fact', 'board_action_fact', 'common_action_event', 'common_position_state', 'common_position_event']
- missing_tables: []
- missing_columns_by_table: {}
- missing_required_literals: []
- physical_action_fact_tables: ['stock_action_fact', 'index_action_fact', 'board_action_fact']
- dedup_contract: UNIQUE(run_id, dedup_key) and UNIQUE(run_id, action_key)

## Event Contract

- input_event_types: ['TriggerMatched', 'TriggerPendingMarketData', 'TriggerStateChanged']
- output_event_types: ['ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped']
- payload_required_keys: ['run_id', 'source_trigger_event_id', 'source_trigger_run_id', 'source_trigger_state_id', 'source_trigger_match_id', 'source_condition_run_id', 'action_key', 'dedup_key', 'identity_key', 'asset_kind', 'direction', 'signal_type', 'condition_key', 'original_condition_key', 'trigger_period', 'action_state', 'confirmation_status', 'action_policy', 'trace_json', 'data_quality_status', 'event_schema_version', 'source_market_data_run_id', 'source_market_trace']
- market_trace_rule: payload must include source_market_data_run_id or source_market_trace
- action_key_rule: action_key is stable and paired with dedup_key for idempotent N5 output
- buy_signal_types: ['B_BUY']
- sell_signal_types: ['S_SELL']
- normalization: {'B_BUY': 'canonical buy runtime signal', 'S_SELL': 'canonical sell runtime signal', 'BUY_HINT': 'condition_key/original_condition_key trace only; not an N5 output type', 'SELL_HINT': 'condition_key/original_condition_key trace only; not an N5 output type', 'B_BUY_30M_VOL': 'deprecated runtime signal; represented by action_mark=30m_volume after N5 confirmation', 'S_SELL_30M_SHRINK': 'deprecated runtime signal; represented by action_mark=30m_shrink after N5 confirmation'}

## N6 Boundary

- n6_decision_boundary: ['whether to present a hint', 'whether to speak voice', 'whether to write mobile/card projection', 'whether to enter sim shadow']
- n5_forbidden_execution: ['no user projection', 'no voice', 'no sim', 'no true trading interface']

## Boundary Confirmation

- will_execute_sql: False
- migration_executed: False
- writes_performed: False
- action_fact_written: False
- action_event_written: False
- common_event_outbox_written: False
- common_event_inbox_updated: False
- consumer_checkpoint_updated: False
- real_n4_outbox_consumed: False
- market_data_pulled: False
- n6_user_layer_touched: False
- voice_touched: False
- sim_touched: False
- real_trade_touched: False
- worker_started: False
- old_system_touched: False

## Notes

- N5-2 is schema and event contract review only.
- No migration, N4 outbox consumption, inbox/checkpoint update, N5 outbox write, N6 write, worker, market pull, voice, sim, or true trade was executed.