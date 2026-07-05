# N3-A0 Previous-Day Minute Preload Dry-Run

## Result

- source_condition_run_id: `condition_layer_20260522_to_20260525_20260524014029_execute`
- source_trade_date: `20260522`
- for_trade_date: `20260525`
- prev_trade_date / data_trade_date: `20260522`
- blocked: `True`
- execute_ready: `False`
- n2_scope_error: `False`
- P0/P1/P2: `1/0/0`

## Subscription Input

- N3-0 passed: `True`
- source_scope_row_count: `4512`
- candidate_row_count: `13536`
- subscription_row_count: `6564`
- subscription_object_count: `2188`
- required_data_kind_counts: `{'minute_bar_1m': 2188, 'previous_day_minute_bar_1m': 2188, 'realtime_daily_snapshot': 2188}`
- dedup_ratio: `0.484929`

## Preload Plan

- previous_day_minute_subscription_count: `2188`
- previous_day_minute_object_count: `2188`
- previous_day_minute_object_count_by_asset_kind: `{'stock': 2052, 'index': 9, 'board': 127}`
- expected_minute_bar_count_per_object: `240`
- estimated_minute_bar_row_count: `525120`
- estimated_minute_bar_row_count_by_asset_kind: `{'stock': 492480, 'index': 2160, 'board': 30480}`
- preload_pull_plan_row_count: `3`

## Schema / Execute Readiness

- schema_path: `sql/007_market_data_fact_schema.sql`
- all_n3a_execute_tables_exist: `False`
- missing_n3a_execute_tables: `['common_market_data_run', 'common_market_data_quality_item', 'common_market_data_subscription_candidate', 'common_market_data_subscription', 'common_market_data_pull_plan', 'stock_minute_bar_1m', 'index_minute_bar_1m', 'board_minute_bar_1m', 'stock_previous_day_minute_preload_status', 'index_previous_day_minute_preload_status', 'board_previous_day_minute_preload_status']`

## Quality Items

- P0 passed n3_subscription_plan_clean: expected=subscription plan passed and P0=0 actual=passed=True p0=0
- P0 passed previous_day_minute_subscriptions_present: expected=>0 actual=2188
- P0 passed previous_day_subscription_trade_date_matches_prev_trade_date: expected=20260522 actual=matched
- P0 passed previous_day_subscription_trace_present: expected=trace arrays present actual=present
- P0 failed n3a_execute_tables_exist: expected=all required N3-A execute tables exist actual=common_market_data_run,common_market_data_quality_item,common_market_data_subscription_candidate,common_market_data_subscription,common_market_data_pull_plan,stock_minute_bar_1m,index_minute_bar_1m,board_minute_bar_1m,stock_previous_day_minute_preload_status,index_previous_day_minute_preload_status,board_previous_day_minute_preload_status
- P0 passed n3a_dry_run_no_adapter_call: expected=None actual=None
- P0 passed n3a_dry_run_no_database_write: expected=None actual=None
- P0 passed n3a_dry_run_no_downstream_layers: expected=None actual=None

## Boundary

- old_system_touched: `False`
- migration_executed: `False`
- writes_performed: `False`
- market_data_pulled: `False`
- market_data_fact_written: `False`
- downstream_layers_touched: `False`
- worker_started: `False`

## Rollback

No database rows were written in N3-A0. Rollback is deleting this report and the newly added dry-run code/schema draft files.
