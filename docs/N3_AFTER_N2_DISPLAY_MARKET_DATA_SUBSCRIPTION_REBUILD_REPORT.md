# N3 Subscription Rebuild After N2-Display Report

## Summary

- rebuild_stage: N3 subscription rebuild after N2-Display
- stage: N3-6
- layer_role: N3_market_data
- market_data_run_id: market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
- source_condition_run_id: condition_layer_20260522_to_20260525_20260525102249_execute
- for_trade_date: 20260525
- source_trade_date: 20260522
- prev_trade_date: 20260522
- started_at: 2026-05-25T02:40:11.413715+00:00
- finished_at: 2026-05-25T02:40:14.295834+00:00
- P0/P1/P2: 0/1/0

## N2-Display Lineage

- new_active_condition_run_id: condition_layer_20260522_to_20260525_20260525102249_execute
- old_condition_run_id: condition_layer_20260522_to_20260525_20260525003855_execute
- active_passed_run_count: 1
- condition_display_basis_input_to_n3: false
- n3_input_tables: stock_minute_target_scope, index_minute_target_scope, board_minute_target_scope
- old_n3_subscription_run: market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525003855_execute
- old_n3_subscription_status: stale_after_n2_display_overwrite

## Precheck

- new_condition_run_status: passed
- target_n3_run_existed_before_execute: false
- scope_row_count_expected: {'stock': 4236, 'index': 18, 'board': 258}
- condition_pool_period_trigger_baseline_missing: 0
- minute_target_scope_period_trigger_baseline_missing: 0
- condition_pool_required_period_not_ready_rows: 0
- minute_target_scope_required_period_not_ready_rows: 0

## Dry-Run Input

- source_scope_row_count: 4512
- source_scope_row_count_by_asset_kind: {'stock': 4236, 'index': 18, 'board': 258}
- subscription_candidate_count: 13536
- dedup_subscription_count: 6564
- subscription_object_count: 2188
- object_count_by_asset_kind: {'stock': 2052, 'index': 9, 'board': 127}
- required_data_kind_counts: {'minute_bar_1m': 2188, 'previous_day_minute_bar_1m': 2188, 'realtime_daily_snapshot': 2188}
- previous_day_minute_required_count: 4512
- previous_day_minute_date_counts: {'20260522': 4512}
- dedup_ratio: 0.484929
- market_data_pull_plan_row_count: 9

## Rows Written

- common_market_data_run: 1
- common_market_data_quality_item: 34
- common_market_data_subscription_candidate: 13536
- common_market_data_subscription: 6564
- common_market_data_pull_plan: 9
- market_data_fact_rows_written: 0
- event_outbox_rows_written: 0

## Post Checks

- n3_6_preflight_p0_zero: true
- n3_6_target_run_created_once: true
- n3_6_candidate_row_count_matches: true
- n3_6_subscription_row_count_matches: true
- n3_6_pull_plan_row_count_matches: true
- n3_6_quality_item_count_matches: true
- n3_6_run_id_matches_expected: true
- n3_6_run_mode_execute: true
- n3_6_run_status_passed: true
- n3_6_run_flags_no_market_pull_or_fact: true
- n3_6_n1_n2_active_snapshot_unchanged: true
- n3_6_no_market_fact_or_event_rows_written: true

## Boundary Confirmation

- writes_performed: true
- migration_executed: false
- market_data_pulled: false
- market_data_fact_written: false
- event_outbox_written: false
- downstream_layers_touched: false
- worker_started: false
- old_system_touched: false

## Rollback

Delete this N3-6 run by run_id in dependency order. This removes only N3 control rows:

- rollback_sql: sql/N3_after_N2_DISPLAY_market_data_subscription_rollback.sql

```sql
DELETE FROM common_market_data_pull_plan WHERE run_id = 'market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM common_market_data_subscription WHERE run_id = 'market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM common_market_data_subscription_candidate WHERE run_id = 'market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM common_market_data_quality_item WHERE run_id = 'market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM common_market_data_run WHERE run_id = 'market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
```
