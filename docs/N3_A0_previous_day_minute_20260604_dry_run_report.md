# N3-A0 Previous-Day Minute Preload Dry-Run

## Result

- market_data_run_id: `market_data_subscription_20260604_condition_layer_20260603_source_20260603_v1`
- source_condition_run_id: `condition_layer_20260603_source_20260603_v1`
- source_trade_date: `20260603`
- for_trade_date: `20260604`
- prev_trade_date / data_trade_date: `20260603`
- expected_previous_day_minute_date: `20260603`
- blocked: `False`
- execute_ready: `True`
- n2_scope_error: `False`
- n3_subscription_error: `False`
- P0/P1/P2: `0/0/0`

## Subscription Input

- persisted N3-6 passed: `True`
- market_data_run_id: `market_data_subscription_20260604_condition_layer_20260603_source_20260603_v1`
- source_scope_row_count: `5113`
- candidate_row_count: `5757`
- subscription_row_count: `3041`
- subscription_object_count: `2397`
- required_data_kind_counts: `{'minute_bar_1m': 322, 'previous_day_minute_bar_1m': 322, 'realtime_daily_snapshot': 2397}`
- dedup_ratio: `0.528227`

## Preload Plan

- previous_day_minute_subscription_count: `322`
- previous_day_minute_object_count: `322`
- previous_day_minute_object_count_by_asset_kind: `{'stock': 284, 'index': 2, 'board': 36}`
- previous_day_minute_date_counts: `{'20260603': 322}`
- expected_minute_bar_count_per_object: `240`
- estimated_minute_bar_row_count: `77280`
- estimated_minute_bar_row_count_by_asset_kind: `{'stock': 68160, 'index': 480, 'board': 8640}`
- preload_pull_plan_row_count: `3`

## Source Adapter Plan

- board: adapter=`BoardMarketDataAdapter` subscriptions=`36` objects=`36` previous_day_minute_date=`20260603` expected_minute_bar_rows=`8640`
- index: adapter=`IndexMarketDataAdapter` subscriptions=`2` objects=`2` previous_day_minute_date=`20260603` expected_minute_bar_rows=`480`
- stock: adapter=`StockMarketDataAdapter` subscriptions=`284` objects=`284` previous_day_minute_date=`20260603` expected_minute_bar_rows=`68160`

## Estimated Write Tables

- schema_path: `sql/007_market_data_fact_schema.sql`
- estimated_write_tables: `['board_minute_bar_1m', 'board_previous_day_minute_preload_status', 'index_minute_bar_1m', 'index_previous_day_minute_preload_status', 'stock_minute_bar_1m', 'stock_previous_day_minute_preload_status']`
- estimated_write_tables_by_asset_kind: `{'stock': {'minute_fact_table': 'stock_minute_bar_1m', 'preload_status_table': 'stock_previous_day_minute_preload_status'}, 'index': {'minute_fact_table': 'index_minute_bar_1m', 'preload_status_table': 'index_previous_day_minute_preload_status'}, 'board': {'minute_fact_table': 'board_minute_bar_1m', 'preload_status_table': 'board_previous_day_minute_preload_status'}}`
- event_outbox_write_planned: `False`
- generated_event_types: `[]`

## Quality Items

- P0 passed n3_6_subscription_run_clean: expected=N3-6 subscription run passed and P0=0 actual=passed=True p0=0
- P1 passed n3_6_subscription_run_p1_carried: expected=0 actual=0
- P2 passed n3_6_subscription_run_p2_carried: expected=0 actual=0
- P0 passed previous_day_minute_subscriptions_present: expected=>0 actual=322
- P0 passed previous_day_subscription_trade_date_matches_expected: expected=20260603 actual=matched
- P0 passed expected_previous_day_minute_date_matches_prev_trade_date: expected=20260603 actual=20260603
- P0 passed previous_day_pull_plan_trade_date_matches_expected: expected=20260603 actual=matched
- P0 passed previous_day_subscription_trace_present: expected=trace arrays present actual=present
- P0 passed previous_day_pull_plan_asset_coverage: expected=pull plan for each asset kind in subscriptions actual=covered
- P0 passed previous_day_pull_plan_counts_match_subscriptions: expected=counts match actual=matched
- P0 passed previous_day_pull_plan_execute_not_allowed: expected=execute_allowed=false actual=false
- P0 passed previous_day_estimated_tables_physically_separated: expected=stock/index/board target table prefixes actual=separated
- P0 passed n3a_no_runtime_table_names: expected=no *_runtime identifiers actual=none
- P0 passed n3a_no_event_outbox_write_plan: expected=common_event_outbox absent actual=absent
- P0 passed n3a_no_user_event_names: expected=no User* events actual=none
- P0 passed n3a_dry_run_no_adapter_call: expected=None actual=None
- P0 passed n3a_dry_run_no_database_write: expected=None actual=None
- P0 passed n3a_dry_run_no_event_outbox_write: expected=None actual=None
- P0 passed n3a_dry_run_no_downstream_layers: expected=None actual=None

## Boundary

- old_system_touched: `False`
- migration_executed: `False`
- writes_performed: `False`
- market_data_pulled: `False`
- market_data_fact_written: `False`
- event_outbox_written: `False`
- downstream_layers_touched: `False`
- worker_started: `False`

## Rollback

No database rows were written in N3-A0. Rollback is deleting this report and the newly added dry-run code/report files.
