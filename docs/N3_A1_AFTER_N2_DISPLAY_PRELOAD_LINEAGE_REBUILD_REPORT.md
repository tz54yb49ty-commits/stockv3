# N3-A1 After N2-Display Preload Lineage Rebuild Report

## Summary

- result: `PASS`
- layer_role: `N3_market_data`
- new_preload_run_id: `previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- current_n2_run_id: `condition_layer_20260522_to_20260525_20260525102249_execute`
- current_n3_subscription_run_id: `market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- old_stale_preload_run_id: `previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260524014029_execute`
- for_trade_date: `20260525`
- previous_day_minute_date: `20260522`
- P0/P1/P2: `0/2/0`
- allow_rerun_n3_b1_readiness: `true`

## Preload Counts

- stock: total=`2052` passed=`2043` missing=`9` actual_rows=`490320` expected_rows=`492480`
- index: total=`9` passed=`9` missing=`0` actual_rows=`2160` expected_rows=`2160`
- board: total=`127` passed=`127` missing=`0` actual_rows=`30480` expected_rows=`30480`

## Lineage Proof

- new run source_condition_run_id: `condition_layer_20260522_to_20260525_20260525102249_execute`
- new run source subscription run: `market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- previous_day check: `20260522`
- for_trade_date check: `20260525`
- object_set_diff: `{"stock": {"current_not_in_old": 0, "old_not_in_current": 0}, "index": {"current_not_in_old": 0, "old_not_in_current": 0}, "board": {"current_not_in_old": 0, "old_not_in_current": 0}}`
- old preload stale marking: `common_market_data_run.status=superseded`

## Boundary

- db_writes_performed: `true`
- n3_control_run_written: `true`
- n3_preload_status_metadata_written: `true`
- old_preload_marked_superseded: `true`
- market_data_pulled: `false`
- minute_bar_1m_written: `false`
- realtime_snapshot_written: `false`
- common_event_outbox_written: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
- old_system_touched: `false`
- outbox_count_before: `53304`
- outbox_count_after: `53304`
- new_preload_fact_rows_before: `{'stock': 0, 'index': 0, 'board': 0}`
- new_preload_fact_rows_after: `{'stock': 0, 'index': 0, 'board': 0}`

## Rollback

- rollback SQL: `sql/N3_A1_AFTER_N2_DISPLAY_preload_lineage_rebuild_rollback.sql`
