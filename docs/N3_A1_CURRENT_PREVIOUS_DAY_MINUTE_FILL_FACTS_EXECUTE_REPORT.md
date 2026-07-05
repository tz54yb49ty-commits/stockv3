# N3-A1 Current-Lineage Previous-Day Minute Fill-Facts Execute Report

## Summary

- stage: `N3-A1-current-lineage-fill-facts`
- layer_role: `N3_market_data`
- source_run_id: `market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- preload_run_id: `previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- previous_day_minute_date: `20260522`
- objects_processed: `2188`
- minute_rows_written: `522960`
- preload_status_rows_written: `2188`
- quality_item_rows_written: `12`
- event_outbox_rows_written: `0`
- P0/P1/P2: `0/2/0`

## Asset Counts

- stock: objects=`2052` minute_rows=`490320` passed=`2043` partial=`0` missing=`9` failed=`0`
- index: objects=`9` minute_rows=`2160` passed=`9` partial=`0` missing=`0` failed=`0`
- board: objects=`127` minute_rows=`30480` passed=`127` partial=`0` missing=`0` failed=`0`

## Post Checks

- n3_a1_asset_object_count_matches_a0: `True`
- n3_a1_expected_status_counts: `{'stock': 2052, 'index': 9, 'board': 127}`
- n3_a1_actual_status_counts: `{'stock': 2052, 'index': 9, 'board': 127}`
- n3_a1_minute_rows_reasonable: `True`
- n3_a1_total_minute_rows_present: `True`
- n3_a1_expected_minute_rows_by_asset: `{'stock': 492480, 'index': 2160, 'board': 30480}`
- n3_a1_actual_minute_rows_by_asset: `{'stock': 490320, 'index': 2160, 'board': 30480}`
- n3_a1_duplicate_minute_key_zero: `True`
- n3_a1_duplicate_minute_key_count_by_asset: `{'stock': 0, 'index': 0, 'board': 0}`
- n3_a1_missing_object_not_silent: `True`
- n3_a1_object_status_counts: `{'passed': 2179, 'missing': 9}`
- n3_a1_physical_table_isolation: `True`
- n3_a1_physical_isolation_violation_count_by_asset: `{'stock': 0, 'index': 0, 'board': 0}`
- n3_a1_outbox_rows_zero: `True`
- n3_a1_n1_n2_active_snapshot_unchanged: `True`
- n3_a1_inbox_rows_zero: `True`
- n3_a1_global_outbox_count_observed_not_blocking: `{'before': 55492, 'after': 55492}`

## Boundary

- writes_performed: `True`
- migration_executed: `False`
- market_data_pulled: `True`
- market_data_fact_written: `True`
- event_outbox_written: `False`
- event_inbox_written: `False`
- projection_written: `False`
- downstream_layers_touched: `False`
- worker_started: `False`
- old_system_touched: `False`

## Rollback

- rollback_sql_path: `sql/N3_A1_AFTER_N2_DISPLAY_current_previous_day_minute_rollback.sql`
- rollback key: current `preload_run_id + trade_date + is_previous_day_preload=true`.
- status rows restore from the captured metadata-only snapshot.
- common_event_outbox is not touched by N3-A1 fill-facts rollback.

## Fill-Facts Resume

- status_snapshot_path: `docs/N3_A1_current_previous_day_minute_fill_status_snapshot_before.json`
- common_event_outbox is not written or consumed by this runner.
