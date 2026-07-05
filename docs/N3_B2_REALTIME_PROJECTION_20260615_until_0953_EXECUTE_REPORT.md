# N3-B2 Realtime Projection Execute Report

## Summary

- result: `EXECUTE_PASS`
- projection_run_id: `realtime_projection_metric_20260615_until_0953__realtime_daily_snapshot_20260615_until_0953__market_data_subscription_20260615_condition_layer_20260612_source_20260612_for_20260615_v1`
- status: `passed`
- projection_rows_written: `2104`
- ready_by_asset: `{}`
- not_ready_by_asset: `{"board": 127, "index": 83, "stock": 1894}`
- projection_signal_status: `{"down_volume_expanding": 43, "down_volume_flat": 30, "down_volume_shrinking": 19, "flat": 30, "unknown": 1583, "up_volume_expanding": 220, "up_volume_flat": 119, "up_volume_shrinking": 60}`
- P0/P1/P2: `0/4/0`
- rollback_sql_path: `sql/N3_B2_realtime_projection_20260615_until_0953_rollback.sql`

## Boundary

- writes_outbox: `false`
- updates_market_snapshot_payload: `false`
- outbox_consumed: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
