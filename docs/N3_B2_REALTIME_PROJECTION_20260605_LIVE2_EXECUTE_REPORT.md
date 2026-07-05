# N3-B2 Realtime Projection Execute Report

## Summary

- projection_run_id: `realtime_projection_metric_20260605_live2_compat__realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`
- status: `passed`
- projection_rows_written: `2389`
- ready_by_asset: `{"stock": 969}`
- not_ready_by_asset: `{"board": 428, "index": 9, "stock": 983}`
- projection_signal_status: `{"down_volume_expanding": 464, "down_volume_flat": 281, "down_volume_shrinking": 319, "flat": 581, "unknown": 428, "up_volume_expanding": 169, "up_volume_flat": 65, "up_volume_shrinking": 82}`
- P0/P1/P2: `0/4/0`
- rollback_sql_path: `sql/N3_B2_realtime_projection_20260605_live2_compat_rollback.sql`

## Boundary

- writes_outbox: `false`
- updates_market_snapshot_payload: `false`
- outbox_consumed: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
