# N3-0C Market Data Schema Migration Review

## Summary

- schema_path: sql/006_market_data_layer_schema.sql
- migration_required: true
- ready_for_first_apply: true
- ready_for_user_migration_review: true
- migration_safe_to_apply_after_user_confirmation: true
- manual_review_required: false
- user_confirmation_required: true

## Static SQL Review

- schema_hash: 5bf1e4aa9cdd9b9a59bf7d63731d5966082d32fe468cc571fe4716360d49c92e
- static_ready: true
- additive_create_only: true
- created_tables: ['common_market_data_run', 'common_market_data_quality_item', 'common_market_data_subscription_candidate', 'common_market_data_subscription', 'common_market_data_pull_plan']
- required_tables_missing: []
- extra_created_tables: []
- forbidden_created_tables: []
- unsafe_sql_hits: []
- required_data_kind_whitelist_present: true
- trace_columns_present: true
- dry_run_guard_columns_present: true

## Database Status

- read_only_database_checks: true
- market_tables_existing: []
- market_tables_missing: ['common_market_data_run', 'common_market_data_quality_item', 'common_market_data_subscription_candidate', 'common_market_data_subscription', 'common_market_data_pull_plan']
- dependency_missing: []
- partial_market_tables_existing: false
- missing_columns_existing_tables: {}

## Planned Migration

- strategy: first_apply_additive_create_tables
- create_order: ['common_market_data_run', 'common_market_data_quality_item', 'common_market_data_subscription_candidate', 'common_market_data_subscription', 'common_market_data_pull_plan']
- will_execute_sql: false
- will_write_business_rows: false
- will_pull_market_data: false

## Quality

- P0: 0
- P1: 0
- P2: 0

Quality items:
- P0 passed market_schema_static_ready: expected=static_ready=true actual=true
- P0 passed market_schema_required_tables_present: expected=common_market_data_run,common_market_data_quality_item,common_market_data_subscription_candidate,common_market_data_subscription,common_market_data_pull_plan actual=present
- P0 passed market_schema_no_fact_or_downstream_tables: expected=common_market_data_* control tables only actual=none
- P0 passed market_schema_no_destructive_or_dml_sql: expected=no DROP/INSERT/UPDATE/DELETE/TRUNCATE/COPY/ALTER/trigger actual=none
- P0 passed market_schema_dependencies_exist: expected=common_condition_run,stock_minute_target_scope,index_minute_target_scope,board_minute_target_scope actual=present
- P1 passed market_schema_partial_existing_tables: expected=all missing for first apply, or all existing actual=not_partial
- P1 passed market_schema_existing_table_column_gaps: expected=no existing table column gaps actual=none
- P0 passed market_schema_review_no_execute: expected=None actual=None
- P0 passed market_schema_review_no_market_data_pull: expected=None actual=None
- P0 passed market_schema_review_no_downstream_layers: expected=None actual=None

## Boundary Confirmation

- old_system_touched: false
- migration_executed: false
- will_execute_sql: false
- writes_performed: false
- market_data_pulled: false
- market_data_fact_written: false
- downstream_layers_touched: false
- worker_started: false

## Rollback

N3-0C did not execute a migration and did not write database rows. Rollback for this review stage is deleting this report and the review code if needed.

If a later user-confirmed migration applies 006, rollback must be reviewed separately and limited to the new common_market_data_* control tables.
