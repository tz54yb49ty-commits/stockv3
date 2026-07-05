# N5-3 Action Schema Migration Review

## Summary

- stage: N5-3
- layer_role: N5_action
- execution_mode: static_review_no_db_no_migration
- schema_path: sql/011_action_layer_schema.sql
- schema_hash: 9f4bbc1f045a81111c741b1f2c7c9409d56f44f23a2997218857508427b43db3
- P0/P1/P2: 0/0/1
- passed: True
- migration_ready: True

## SQL Scope

- created_tables: ['common_action_run', 'common_action_quality_item', 'stock_action_fact', 'index_action_fact', 'board_action_fact', 'common_action_event', 'common_position_state', 'common_position_event']
- created_indexes: [{'index_name': 'idx_common_action_run_trigger', 'table_name': 'common_action_run'}, {'index_name': 'idx_common_action_run_date_status', 'table_name': 'common_action_run'}, {'index_name': 'idx_common_action_quality_run', 'table_name': 'common_action_quality_item'}, {'index_name': 'idx_common_action_quality_status', 'table_name': 'common_action_quality_item'}, {'index_name': 'idx_stock_action_fact_lookup', 'table_name': 'stock_action_fact'}, {'index_name': 'idx_stock_action_fact_source', 'table_name': 'stock_action_fact'}, {'index_name': 'idx_index_action_fact_lookup', 'table_name': 'index_action_fact'}, {'index_name': 'idx_index_action_fact_source', 'table_name': 'index_action_fact'}, {'index_name': 'idx_board_action_fact_lookup', 'table_name': 'board_action_fact'}, {'index_name': 'idx_board_action_fact_source', 'table_name': 'board_action_fact'}, {'index_name': 'idx_common_action_event_run_type', 'table_name': 'common_action_event'}, {'index_name': 'idx_common_action_event_identity', 'table_name': 'common_action_event'}, {'index_name': 'idx_common_position_state_identity', 'table_name': 'common_position_state'}, {'index_name': 'idx_common_position_event_run', 'table_name': 'common_position_event'}]
- referenced_tables: ['board_identity', 'common_action_run', 'common_condition_run', 'common_market_data_run', 'common_position_state', 'common_trigger_run', 'index_identity', 'stock_identity']
- missing_required_tables: []
- extra_created_tables: []
- index_target_violations: []
- non_n5_dependency_references: []

## Additive Review

- additive_only: True
- unsafe_statements: []
- unsupported_statements: []
- business_data_write_statements: []

## Boundary Review

- n6_table_violations: []
- true_trade_field_violations: []
- forbidden_boundary_findings: []

## Contract Review

- payload_contract_missing: []
- buy_sell_hint_contract: {'buy_signal_types': ['B_BUY_30M_VOL', 'B_BUY', 'BUY_HINT'], 'sell_signal_types': ['S_SELL_30M_SHRINK', 'S_SELL', 'SELL_HINT'], 'buy_present': True, 'sell_present': True, 'buy_direction_guard': True, 'sell_direction_guard': True, 'forced_hint_only': False, 'passed': True}

## Rollback Preview

- path: sql/011_action_layer_schema_rollback_preview.sql
- generated: True
- executed: False

## Boundary Confirmation

- will_execute_sql: False
- migration_executed: False
- writes_performed: False
- business_data_written: False
- action_fact_written: False
- n5_outbox_written: False
- common_event_inbox_updated: False
- consumer_checkpoint_updated: False
- real_n4_outbox_consumed: False
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

- N5-3 is static migration review only.
- No SQL was executed and no database connection was opened.
- Rollback preview was generated for later human review only.