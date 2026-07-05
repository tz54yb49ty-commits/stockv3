# N3-B2 Realtime Projection Execute Report

## Summary

- projection_run_id: `realtime_projection_metric_20260525__realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- status: `passed`
- projection_rows_written: `2188`
- ready_by_asset: `{"index": 9, "stock": 2043}`
- not_ready_by_asset: `{"board": 127, "stock": 9}`
- projection_signal_status: `{"down_volume_expanding": 96, "down_volume_flat": 79, "down_volume_shrinking": 174, "flat": 577, "unknown": 136, "up_volume_expanding": 305, "up_volume_flat": 342, "up_volume_shrinking": 479}`
- P0/P1/P2: `0/3/0`
- rollback_sql_path: `sql/N3_B2_realtime_projection_rollback.sql`

## Boundary

- writes_outbox: `false`
- updates_market_snapshot_payload: `false`
- outbox_consumed: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
