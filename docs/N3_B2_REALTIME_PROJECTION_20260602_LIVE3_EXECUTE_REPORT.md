# N3-B2 Realtime Projection Execute Report

## Summary

- projection_run_id: `realtime_projection_metric_20260602_live3__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`
- status: `passed`
- projection_rows_written: `2487`
- ready_by_asset: `{"index": 54, "stock": 765}`
- not_ready_by_asset: `{"board": 428, "index": 29, "stock": 1211}`
- projection_signal_status: `{"down_volume_expanding": 55, "down_volume_flat": 93, "down_volume_shrinking": 218, "flat": 127, "unknown": 1668, "up_volume_expanding": 83, "up_volume_flat": 125, "up_volume_shrinking": 118}`
- P0/P1/P2: `0/3/0`
- rollback_sql_path: `sql/N3_B2_realtime_projection_20260602_live3_rollback.sql`

## Boundary

- writes_outbox: `false`
- updates_market_snapshot_payload: `false`
- outbox_consumed: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
