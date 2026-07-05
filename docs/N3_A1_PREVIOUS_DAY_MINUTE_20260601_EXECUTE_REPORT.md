# N3-A1 Previous-Day Minute Preload Execute Report

## Summary

- stage: `N3-A1`
- layer_role: `N3_market_data`
- source_run_id: `market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6`
- preload_run_id: `previous_day_minute_preload_20260529_for_20260601__market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6`
- previous_day_minute_date: `20260529`
- objects_processed: `473`
- minute_rows_written: `113520`
- preload_status_rows_written: `473`
- quality_item_rows_written: `12`
- event_outbox_rows_written: `0`
- P0/P1/P2: `0/1/0`

## Asset Counts

- stock: objects=`366` minute_rows=`87840` passed=`366` partial=`0` missing=`0` failed=`0`
- index: objects=`21` minute_rows=`5040` passed=`21` partial=`0` missing=`0` failed=`0`
- board: objects=`86` minute_rows=`20640` passed=`86` partial=`0` missing=`0` failed=`0`

## Post Checks

- n3_a1_asset_object_count_matches_a0: `True`
- n3_a1_expected_status_counts: `{'stock': 366, 'index': 21, 'board': 86}`
- n3_a1_actual_status_counts: `{'stock': 366, 'index': 21, 'board': 86}`
- n3_a1_minute_rows_reasonable: `True`
- n3_a1_total_minute_rows_present: `True`
- n3_a1_expected_minute_rows_by_asset: `{'stock': 87840, 'index': 5040, 'board': 20640}`
- n3_a1_actual_minute_rows_by_asset: `{'stock': 87840, 'index': 5040, 'board': 20640}`
- n3_a1_duplicate_minute_key_zero: `True`
- n3_a1_duplicate_minute_key_count_by_asset: `{'stock': 0, 'index': 0, 'board': 0}`
- n3_a1_missing_object_not_silent: `True`
- n3_a1_object_status_counts: `{'passed': 473}`
- n3_a1_physical_table_isolation: `True`
- n3_a1_physical_isolation_violation_count_by_asset: `{'stock': 0, 'index': 0, 'board': 0}`
- n3_a1_scoped_event_refs_zero: `True`
- n3_a1_scoped_event_ref_counts_before: `{'common_event_outbox': 0, 'common_event_inbox': 0, 'common_event_consumer_checkpoint': 0}`
- n3_a1_scoped_event_ref_counts_after: `{'common_event_outbox': 0, 'common_event_inbox': 0, 'common_event_consumer_checkpoint': 0}`
- n3_a1_global_event_counts_unchanged: `True`
- n3_a1_global_event_counts_before: `{'common_event_outbox': 151341, 'common_event_inbox': 56170, 'common_event_consumer_checkpoint': 4368}`
- n3_a1_global_event_counts_after: `{'common_event_outbox': 151341, 'common_event_inbox': 56170, 'common_event_consumer_checkpoint': 4368}`
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
