# N3-0D Market Data Schema Migration Plan

## Summary

- migration_plan_id: market_data_schema_006_first_apply_plan
- schema_path: sql/006_market_data_layer_schema.sql
- migration_required: true
- ready_for_user_confirmation: true
- user_confirmation_required: true
- user_confirmation_present: false
- execute_allowed: false
- not_ready_reasons: ['pending_explicit_user_confirmation']

## Review Input

- N3-0C ready_for_user_migration_review: true
- N3-0C P0/P1/P2: 0/0/0
- market_tables_existing: []
- market_tables_missing: ['common_market_data_run', 'common_market_data_quality_item', 'common_market_data_subscription_candidate', 'common_market_data_subscription', 'common_market_data_pull_plan']
- dependency_missing: []

## Subscription Input

- report_exists: true
- source_condition_run_id: condition_layer_20260522_to_20260525_20260523223042_execute
- for_trade_date: 20260525
- source_scope_row_count: 7875
- candidate_row_count: 23625
- subscription_row_count: 6561
- subscription_object_count: 2187
- required_data_kind_counts: {'minute_bar_1m': 2187, 'previous_day_minute_bar_1m': 2187, 'realtime_daily_snapshot': 2187}
- dedup_ratio: 0.277714
- P0/P1/P2: 0/0/0

## Future Execution Plan

- strategy: apply_006_common_market_data_control_tables
- will_create_tables: ['common_market_data_run', 'common_market_data_quality_item', 'common_market_data_subscription_candidate', 'common_market_data_subscription', 'common_market_data_pull_plan']
- will_create_market_data_fact_tables: false
- will_write_business_rows: false
- will_pull_market_data: false
- will_start_worker: false

Execution order if a later explicit authorization is provided:
1. confirm explicit user authorization
2. capture schema-only backup or equivalent DDL snapshot
3. open short PostgreSQL migration connection to v3 development database
4. execute sql/006_market_data_layer_schema.sql in one transaction
5. postcheck common_market_data_* tables and required columns
6. confirm N2 condition run and scope tables remain unchanged
7. write migration report

## Post-Migration Verification Plan

- all common_market_data_* control tables exist
- required columns exist
- no market data fact tables are created by 006
- no trigger/action/mobile/voice/sim/worker objects are created
- condition-layer active run count is unchanged
- market data business row count remains zero until a later execute

## Rollback SQL Preview

```sql
-- Only for a later user-confirmed first-apply migration, before business rows exist.
BEGIN;
DROP TABLE IF EXISTS common_market_data_pull_plan;
DROP TABLE IF EXISTS common_market_data_subscription;
DROP TABLE IF EXISTS common_market_data_subscription_candidate;
DROP TABLE IF EXISTS common_market_data_quality_item;
DROP TABLE IF EXISTS common_market_data_run;
COMMIT;
```

## Quality

- P0: 0
- P1: 1
- P2: 0

Quality items:
- P0 passed n3_0c_schema_review_ready: expected=ready_for_user_migration_review=true and P0=0 actual=ready=True p0=0
- P0 passed n3_0_subscription_plan_ready: expected=subscription plan report exists and P0=0 actual=p0=0 passed=True
- P1 warning explicit_user_confirmation_required: expected=允许执行 N3-0D market data schema migration actual=missing
- P0 passed migration_plan_no_execute: expected=None actual=None
- P0 passed migration_plan_no_market_data_pull: expected=None actual=None
- P0 passed migration_plan_no_downstream_layers: expected=None actual=None

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

N3-0D did not execute migration and did not write database rows. Rollback for this dry-run stage is deleting this report and the plan code if needed.
