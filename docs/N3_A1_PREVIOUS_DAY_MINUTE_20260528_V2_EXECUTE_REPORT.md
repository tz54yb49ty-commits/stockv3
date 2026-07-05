# N3-A1 Previous-Day Minute Preload Execute Report

## Summary

- stage: `N3-A1`
- layer_role: `N3_market_data`
- source_run_id: `market_data_subscription_20260528_condition_layer_20260527_source_20260527_v2`
- preload_run_id: `previous_day_minute_preload_20260527_for_20260528__market_data_subscription_20260528_condition_layer_20260527_source_20260527_v2`
- previous_day_minute_date: `20260527`
- objects_processed: `317`
- minute_rows_written: `75600`
- preload_status_rows_written: `317`
- quality_item_rows_written: `12`
- event_outbox_rows_written: `0`
- P0/P1/P2: `0/1/0`

## Asset Counts

- stock: objects=`294` minute_rows=`70080` passed=`292` partial=`0` missing=`2` failed=`0`
- index: objects=`4` minute_rows=`960` passed=`4` partial=`0` missing=`0` failed=`0`
- board: objects=`19` minute_rows=`4560` passed=`19` partial=`0` missing=`0` failed=`0`

## Post Checks

- n3_a1_asset_object_count_matches_a0: `True`
- n3_a1_expected_status_counts: `{'stock': 294, 'index': 4, 'board': 19}`
- n3_a1_actual_status_counts: `{'stock': 294, 'index': 4, 'board': 19}`
- n3_a1_minute_rows_reasonable: `True`
- n3_a1_total_minute_rows_present: `True`
- n3_a1_expected_minute_rows_by_asset: `{'stock': 70560, 'index': 960, 'board': 4560}`
- n3_a1_actual_minute_rows_by_asset: `{'stock': 70080, 'index': 960, 'board': 4560}`
- n3_a1_duplicate_minute_key_zero: `True`
- n3_a1_duplicate_minute_key_count_by_asset: `{'stock': 0, 'index': 0, 'board': 0}`
- n3_a1_missing_object_not_silent: `True`
- n3_a1_object_status_counts: `{'passed': 315, 'missing': 2}`
- n3_a1_physical_table_isolation: `True`
- n3_a1_physical_isolation_violation_count_by_asset: `{'stock': 0, 'index': 0, 'board': 0}`
- n3_a1_scoped_event_refs_zero: `True`
- n3_a1_scoped_event_ref_counts_before: `{'common_event_outbox': 0, 'common_event_inbox': 0, 'common_event_consumer_checkpoint': 0}`
- n3_a1_scoped_event_ref_counts_after: `{'common_event_outbox': 0, 'common_event_inbox': 0, 'common_event_consumer_checkpoint': 0}`
- n3_a1_global_event_counts_unchanged: `True`
- n3_a1_global_event_counts_before: `{'common_event_outbox': 83063, 'common_event_inbox': 2952, 'common_event_consumer_checkpoint': 2803}`
- n3_a1_global_event_counts_after: `{'common_event_outbox': 83063, 'common_event_inbox': 2952, 'common_event_consumer_checkpoint': 2803}`
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
