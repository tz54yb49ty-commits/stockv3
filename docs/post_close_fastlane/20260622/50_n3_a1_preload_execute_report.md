# N3-A1 Previous-Day Minute Preload Execute Report

## Summary

- stage: `N3-A1`
- layer_role: `N3_market_data`
- source_run_id: `market_data_subscription_20260622_condition_layer_20260618_source_20260618_for_20260622_v1`
- preload_run_id: `previous_day_minute_preload_20260618_for_20260622__market_data_subscription_20260622_condition_layer_20260618_source_20260618_for_20260622_v1`
- previous_day_minute_date: `20260618`
- objects_processed: `137`
- minute_rows_written: `32880`
- preload_status_rows_written: `137`
- quality_item_rows_written: `12`
- event_outbox_rows_written: `0`
- P0/P1/P2: `0/0/0`

## Asset Counts

- stock: objects=`120` minute_rows=`28800` passed=`120` partial=`0` missing=`0` failed=`0`
- index: objects=`0` minute_rows=`0` passed=`0` partial=`0` missing=`0` failed=`0`
- board: objects=`17` minute_rows=`4080` passed=`17` partial=`0` missing=`0` failed=`0`

## Post Checks

- n3_a1_asset_object_count_matches_a0: `True`
- n3_a1_expected_status_counts: `{'stock': 120, 'index': 0, 'board': 17}`
- n3_a1_actual_status_counts: `{'stock': 120, 'index': 0, 'board': 17}`
- n3_a1_minute_rows_reasonable: `True`
- n3_a1_total_minute_rows_present: `True`
- n3_a1_expected_minute_rows_by_asset: `{'stock': 28800, 'index': 0, 'board': 4080}`
- n3_a1_actual_minute_rows_by_asset: `{'stock': 28800, 'index': 0, 'board': 4080}`
- n3_a1_duplicate_minute_key_zero: `True`
- n3_a1_duplicate_minute_key_count_by_asset: `{'stock': 0, 'index': 0, 'board': 0}`
- n3_a1_missing_object_not_silent: `True`
- n3_a1_object_status_counts: `{'passed': 137}`
- n3_a1_physical_table_isolation: `True`
- n3_a1_physical_isolation_violation_count_by_asset: `{'stock': 0, 'index': 0, 'board': 0}`
- n3_a1_scoped_event_refs_zero: `True`
- n3_a1_scoped_event_ref_counts_before: `{'common_event_outbox': 0, 'common_event_inbox': 0, 'common_event_consumer_checkpoint': 0}`
- n3_a1_scoped_event_ref_counts_after: `{'common_event_outbox': 0, 'common_event_inbox': 0, 'common_event_consumer_checkpoint': 0}`
- n3_a1_global_event_counts_unchanged: `True`
- n3_a1_global_event_counts_before: `{'common_event_outbox': 1695645, 'common_event_inbox': 187981, 'common_event_consumer_checkpoint': 57848}`
- n3_a1_global_event_counts_after: `{'common_event_outbox': 1695645, 'common_event_inbox': 187981, 'common_event_consumer_checkpoint': 57848}`
- n3_a1_n1_n2_active_snapshot_unchanged: `True`

## Boundary

- writes_performed: `True`
- migration_executed: `False`
- market_data_pulled: `True`
- market_data_fact_written: `True`
- event_outbox_written: `False`
- downstream_layers_touched: `False`
- worker_started: `False`
- old_system_touched: `False`

## Rollback

- rollback_sql_path: `sql/N3_A1_previous_day_minute_rollback.sql`
- rollback key: `source_run_id + preload_run_id`
- common_event_outbox is not touched by N3-A1 rollback.
