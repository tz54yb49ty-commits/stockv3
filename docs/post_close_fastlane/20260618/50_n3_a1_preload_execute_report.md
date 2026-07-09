# N3-A1 Previous-Day Minute Preload Execute Report

## Summary

- stage: `N3-A1`
- layer_role: `N3_market_data`
- source_run_id: `market_data_subscription_20260618_condition_layer_20260617_source_20260617_for_20260618_v1`
- preload_run_id: `previous_day_minute_preload_20260617_for_20260618__market_data_subscription_20260618_condition_layer_20260617_source_20260617_for_20260618_v1`
- previous_day_minute_date: `20260617`
- objects_processed: `177`
- minute_rows_written: `42480`
- preload_status_rows_written: `177`
- quality_item_rows_written: `12`
- event_outbox_rows_written: `0`
- P0/P1/P2: `0/0/0`

## Asset Counts

- stock: objects=`163` minute_rows=`39120` passed=`163` partial=`0` missing=`0` failed=`0`
- index: objects=`3` minute_rows=`720` passed=`3` partial=`0` missing=`0` failed=`0`
- board: objects=`11` minute_rows=`2640` passed=`11` partial=`0` missing=`0` failed=`0`

## Post Checks

- n3_a1_asset_object_count_matches_a0: `True`
- n3_a1_expected_status_counts: `{'stock': 163, 'index': 3, 'board': 11}`
- n3_a1_actual_status_counts: `{'stock': 163, 'index': 3, 'board': 11}`
- n3_a1_minute_rows_reasonable: `True`
- n3_a1_total_minute_rows_present: `True`
- n3_a1_expected_minute_rows_by_asset: `{'stock': 39120, 'index': 720, 'board': 2640}`
- n3_a1_actual_minute_rows_by_asset: `{'stock': 39120, 'index': 720, 'board': 2640}`
- n3_a1_duplicate_minute_key_zero: `True`
- n3_a1_duplicate_minute_key_count_by_asset: `{'stock': 0, 'index': 0, 'board': 0}`
- n3_a1_missing_object_not_silent: `True`
- n3_a1_object_status_counts: `{'passed': 177}`
- n3_a1_physical_table_isolation: `True`
- n3_a1_physical_isolation_violation_count_by_asset: `{'stock': 0, 'index': 0, 'board': 0}`
- n3_a1_scoped_event_refs_zero: `True`
- n3_a1_scoped_event_ref_counts_before: `{'common_event_outbox': 0, 'common_event_inbox': 0, 'common_event_consumer_checkpoint': 0}`
- n3_a1_scoped_event_ref_counts_after: `{'common_event_outbox': 0, 'common_event_inbox': 0, 'common_event_consumer_checkpoint': 0}`
- n3_a1_global_event_counts_unchanged: `True`
- n3_a1_global_event_counts_before: `{'common_event_outbox': 663681, 'common_event_inbox': 188649, 'common_event_consumer_checkpoint': 58923}`
- n3_a1_global_event_counts_after: `{'common_event_outbox': 663681, 'common_event_inbox': 188649, 'common_event_consumer_checkpoint': 58923}`
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
