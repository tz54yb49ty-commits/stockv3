# N3-5 Market Data 009 Migration Report

## Summary

- stage: N3-5
- layer_role: N3_market_data
- sql_path: sql/009_market_data_schema_migration.sql
- migration_executed: true
- pre_backup_path: docs/N3_5_schema_backup_before_009.json
- post_backup_path: docs/N3_5_schema_backup_after_009.json
- started_at: 2026-05-24T02:25:07.641639+00:00
- finished_at: 2026-05-24T02:25:07.906007+00:00
- P0/P1/P2: 0/0/0

## Preconditions

- N3-3 migration_safe_to_apply: true
- N3-3 P0: 0
- N3-4 passed: true
- N3-4 P0/P1/P2: 0/0/0

## Schema Gap

- before missing_tables: ['common_market_data_run', 'common_market_data_quality_item', 'common_market_data_subscription_candidate', 'common_market_data_subscription', 'common_market_data_pull_plan', 'stock_realtime_daily_snapshot', 'index_realtime_daily_snapshot', 'board_realtime_daily_snapshot', 'stock_minute_bar_1m', 'index_minute_bar_1m', 'board_minute_bar_1m', 'stock_previous_day_minute_preload_status', 'index_previous_day_minute_preload_status', 'board_previous_day_minute_preload_status', 'common_event_ledger', 'common_event_outbox', 'common_event_inbox', 'common_event_consumer_checkpoint', 'common_event_delivery_attempt']
- after missing_tables: []
- after missing_columns_count: 0
- after type_mismatch_count: 0
- after missing_unique_constraints_count: 0

## Post Checks

- missing_tables_zero: true
- missing_columns_zero: true
- type_mismatch_zero: true
- missing_unique_constraints_zero: true
- n3_target_tables_exist: true
- n3_target_tables_row_count_zero: true
- n1_n2_active_run_unchanged: true
- no_market_fact_or_outbox_business_events: true
- n3_4_review_still_passed: true

## N3 Target Row Counts

- common_market_data_run: exists=true row_count=0
- common_market_data_quality_item: exists=true row_count=0
- common_market_data_subscription_candidate: exists=true row_count=0
- common_market_data_subscription: exists=true row_count=0
- common_market_data_pull_plan: exists=true row_count=0
- stock_realtime_daily_snapshot: exists=true row_count=0
- index_realtime_daily_snapshot: exists=true row_count=0
- board_realtime_daily_snapshot: exists=true row_count=0
- stock_minute_bar_1m: exists=true row_count=0
- index_minute_bar_1m: exists=true row_count=0
- board_minute_bar_1m: exists=true row_count=0
- stock_previous_day_minute_preload_status: exists=true row_count=0
- index_previous_day_minute_preload_status: exists=true row_count=0
- board_previous_day_minute_preload_status: exists=true row_count=0
- common_event_ledger: exists=true row_count=0
- common_event_outbox: exists=true row_count=0
- common_event_inbox: exists=true row_count=0
- common_event_consumer_checkpoint: exists=true row_count=0
- common_event_delivery_attempt: exists=true row_count=0

## Quality

- P0 passed n3_5_missing_tables_zero: expected=true actual=true
- P0 passed n3_5_missing_columns_zero: expected=true actual=true
- P0 passed n3_5_type_mismatch_zero: expected=true actual=true
- P0 passed n3_5_missing_unique_constraints_zero: expected=true actual=true
- P0 passed n3_5_n3_target_tables_exist: expected=true actual=true
- P0 passed n3_5_n3_target_tables_row_count_zero: expected=true actual=true
- P0 passed n3_5_n1_n2_active_run_unchanged: expected=true actual=true
- P0 passed n3_5_no_market_fact_or_outbox_business_events: expected=true actual=true
- P0 passed n3_5_n3_4_review_still_passed: expected=true actual=true
- P0 passed n3_5_no_market_data_pull: expected=None actual=None
- P0 passed n3_5_no_worker_or_downstream: expected=None actual=None
- P0 passed n3_5_no_old_system_touch: expected=None actual=None

## Boundary Confirmation

- migration_executed: true
- writes_performed: false
- market_data_pulled: false
- market_data_fact_written: false
- downstream_layers_touched: false
- worker_started: false
- old_system_touched: false

## Rollback

009 created additive schema objects only. If rollback is required before any N3 business rows are written, drop the N3 target tables in dependency order after confirming no dependent objects or rows exist.
