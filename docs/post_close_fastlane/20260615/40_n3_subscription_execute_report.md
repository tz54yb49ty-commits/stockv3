# N3-6 Market Data Subscription Execute Report

## Summary

- stage: N3-6
- layer_role: N3_market_data
- market_data_run_id: market_data_subscription_20260615_condition_layer_20260612_source_20260612_for_20260615_v1
- source_condition_run_id: condition_layer_20260612_source_20260612_for_20260615_v1
- for_trade_date: 20260615
- source_trade_date: 20260612
- prev_trade_date: 20260612
- started_at: 2026-06-12T10:06:33.569550+00:00
- finished_at: 2026-06-12T10:09:48.782388+00:00
- P0/P1/P2: 0/0/0

## Dry-Run Input

- source_scope_row_count: 4725
- source_scope_row_count_by_asset_kind: {'stock': 4223, 'index': 205, 'board': 297}
- subscription_candidate_count: 5767
- dedup_subscription_count: 3146
- subscription_object_count: 2104
- object_count_by_asset_kind: {'stock': 1894, 'index': 83, 'board': 127}
- required_data_kind_counts: {'minute_bar_1m': 521, 'previous_day_minute_bar_1m': 521, 'realtime_daily_snapshot': 2104}
- previous_day_minute_required_count: 521
- previous_day_minute_date_counts: {'20260612': 521}
- dedup_ratio: 0.545518
- market_data_pull_plan_row_count: 9

## Rows Written

- common_market_data_run: 1
- common_market_data_quality_item: 34
- common_market_data_subscription_candidate: 5767
- common_market_data_subscription: 3146
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

```sql
DELETE FROM common_market_data_pull_plan WHERE run_id = 'market_data_subscription_20260615_condition_layer_20260612_source_20260612_for_20260615_v1';
DELETE FROM common_market_data_subscription WHERE run_id = 'market_data_subscription_20260615_condition_layer_20260612_source_20260612_for_20260615_v1';
DELETE FROM common_market_data_subscription_candidate WHERE run_id = 'market_data_subscription_20260615_condition_layer_20260612_source_20260612_for_20260615_v1';
DELETE FROM common_market_data_quality_item WHERE run_id = 'market_data_subscription_20260615_condition_layer_20260612_source_20260612_for_20260615_v1';
DELETE FROM common_market_data_run WHERE run_id = 'market_data_subscription_20260615_condition_layer_20260612_source_20260612_for_20260615_v1';
```
