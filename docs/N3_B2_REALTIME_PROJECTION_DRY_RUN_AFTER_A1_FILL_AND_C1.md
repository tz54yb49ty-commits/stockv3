# N3-B2 Realtime Projection Dry-run After A1 Fill + C1

## Summary

- result: `DRY_RUN_PASS`
- layer_role: `N3_market_data`
- snapshot_run_id: `realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- current_preload_run_id: `previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- today_minute_run_id: `today_minute_bar_1m_20260525_until_1411__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- projection_run_id_candidate: `realtime_projection_metric_20260525__realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- P0/P1/P2: `0/3/0`

## Input Row Counts

- snapshot rows: `{"board": 127, "index": 9, "stock": 2052, "total": 2188}`
- today minute rows: `{"board": 24257, "index": 1719, "stock": 390213}`
- current preload previous-day rows: `{"board": 30480, "index": 2160, "stock": 490320}`
- snapshot outbox MarketSnapshotUpdated rows: `2188`
- input inbox rows: `0`

## Projection Distribution

- expected projection rows: `{"board": 127, "index": 9, "stock": 2052, "total": 2188}`
- ready/not_ready by asset: `{"not_ready_by_asset": {"board": 127, "stock": 9}, "ready_by_asset": {"index": 9, "stock": 2043}}`
- projection_status: `{"not_ready": 136, "ready": 2052}`
- projection_quality_status: `{"blocked": 136, "passed": 2052}`
- trace_status: `{"blocked": 136, "passed": 2052}`
- price_direction_status: `{"down": 349, "flat": 577, "unknown": 136, "up": 1126}`
- projection_signal_status: `{"down_volume_expanding": 96, "down_volume_flat": 79, "down_volume_shrinking": 174, "flat": 577, "unknown": 136, "up_volume_expanding": 305, "up_volume_flat": 342, "up_volume_shrinking": 479}`
- not_ready_reason: `{"amount_projection_ratio_not_computable": 136, "missing_current_lineage_previous_day_elapsed": 9, "missing_current_lineage_previous_day_window": 9, "missing_today_minute_elapsed": 136, "price_direction_unknown": 136, "snapshot_time_after_c1_latest_closed_minute": 127}`

## Metric Computability

- amount_projection_ratio computable rows: `2052`
- price_direction_status computable rows: `2052`
- trace complete rows: `2052`
- amount_projection_ratio summary: `{"avg": "1.334149", "max": "213.432633", "min": "0.009978", "p50": "0.809224"}`
- price_change_pct summary: `{"avg": "0.00185", "max": "0.033912", "min": "-0.018011", "p50": "0.001341"}`

## Board Readiness

- board rows: `127`
- board ready: `0`
- board not_ready: `127`
- board snapshot_time_after_c1_latest_closed_minute: `127`
- conclusion: board snapshot_time is `15:00`, while C1 today minute facts stop at `14:11`; board rows remain explicit `not_ready`, not silent ready.

## Missing Object Handling

- BJ 920xxx missing/not_ready count: `9`
- policy: `not_ready/warning; never silently ready`

## Blockers

- none

## Future Execute Contract

- execute_preflight_allowed: `True`
- execute_allowed_now: `false`
- allowed_write_tables: `["common_market_data_run", "common_market_data_quality_item", "stock_realtime_projection_metric", "index_realtime_projection_metric", "board_realtime_projection_metric"]`
- writes_outbox: `false`
- updates_market_snapshot_payload: `false`

## Boundary

- database_changed: `false`
- projection_fact_written: `false`
- quality_item_written: `false`
- market_snapshot_payload_modified: `false`
- outbox_written: `false`
- outbox_consumed: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
