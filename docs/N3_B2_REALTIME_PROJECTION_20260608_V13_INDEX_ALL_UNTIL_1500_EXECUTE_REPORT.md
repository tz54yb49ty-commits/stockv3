# N3-B2 Realtime Projection Execute Report

## Summary

- projection_run_id: `realtime_projection_metric_20260608_until_1500__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- status: `passed`
- projection_rows_written: `2155`
- ready_by_asset: `{"board": 13, "index": 6, "stock": 353}`
- not_ready_by_asset: `{"board": 114, "index": 77, "stock": 1592}`
- projection_signal_status: `{"down_volume_expanding": 40, "down_volume_flat": 24, "down_volume_shrinking": 12, "flat": 14, "unknown": 1783, "up_volume_expanding": 197, "up_volume_flat": 67, "up_volume_shrinking": 18}`
- P0/P1/P2: `0/4/0`
- rollback_sql_path: `sql/N3_B2_realtime_projection_20260608_v13_index_all_until_1500_rollback.sql`

## Boundary

- writes_outbox: `false`
- updates_market_snapshot_payload: `false`
- outbox_consumed: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
