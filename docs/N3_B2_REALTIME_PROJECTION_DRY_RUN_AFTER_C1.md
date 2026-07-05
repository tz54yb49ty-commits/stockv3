# N3-B2 Realtime Projection Dry-run After C1

## Summary

- result: `DRY_RUN_BLOCKED`
- layer_role: `N3_market_data`
- snapshot_run_id: `realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- current_preload_run_id: `previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- today_minute_run_id: `today_minute_bar_1m_20260525_until_1411__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- projection_run_id_candidate: `realtime_projection_metric_20260525__realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- P0/P1/P2: `2/3/1`

## Input Row Counts

- snapshot rows: `{'stock': 2052, 'index': 9, 'board': 127, 'total': 2188}`
- today minute rows: `{'stock': 390213, 'index': 1719, 'board': 24257}`
- current preload previous-day rows: `{'stock': 0, 'index': 0, 'board': 0}`
- stale preload previous-day rows observed but not used: `{'stock': {'rows': 490320, 'objects': 2043}, 'index': {'rows': 2160, 'objects': 9}, 'board': {'rows': 30480, 'objects': 127}}`
- C1 outbox rows: `0`
- input inbox rows: `0`

## Projection Distribution

- expected projection rows: `{'stock': 2052, 'index': 9, 'board': 127, 'total': 2188}`
- projection_status: `{'not_ready': 2188}`
- projection_quality_status: `{'blocked': 2188}`
- trace_status: `{'blocked': 2188}`
- price_direction_status: `{'unknown': 136, 'flat': 489, 'down': 289, 'up': 1274}`
- projection_signal_status: `{'unknown': 2188}`
- not_ready_reason: `{'missing_today_minute_elapsed': 136, 'missing_current_lineage_previous_day_elapsed': 2188, 'amount_projection_ratio_not_computable': 2188, 'price_direction_unknown': 136, 'snapshot_time_after_c1_latest_closed_minute': 127}`

## Metric Computability

- amount_projection_ratio computable rows: `0`
- price_direction_status computable rows: `2052`
- trace complete rows: `0`

## Missing Object Handling

- issue_object_count: `2188`
- BJ 920xxx today minute missing count: `9`
- policy: `not_ready/warning; never silently ready`

## Blockers

- `n3_b2_current_preload_fact_rows_present` expected=`current A1 previous-day minute fact rows > 0` actual=`0`
- `n3_b2_no_ready_projection_rows` expected=`ready_projection_rows > 0` actual=`0`

## Future Execute Contract

- execute_allowed: `False`
- allowed_write_tables: `['common_market_data_run', 'common_market_data_quality_item', 'stock_realtime_projection_metric', 'index_realtime_projection_metric', 'board_realtime_projection_metric']`
- writes_outbox: `false`
- updates_market_snapshot_payload: `false`

## Rollback Plan

- rollback by `projection_run_id` before downstream consumption.
- no outbox rollback required because B2 execute contract keeps `writes_outbox=false`.

## Boundary

- database_changed: `false`
- projection_fact_written: `false`
- quality_item_written: `false`
- market_snapshot_payload_modified: `false`
- outbox_consumed: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
