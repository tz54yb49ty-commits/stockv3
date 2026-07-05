# N3-B2 Realtime Projection Execute Report

## Summary

- result: `EXECUTE_PASS`
- projection_run_id: `realtime_projection_metric_20260615_until_1458__realtime_daily_snapshot_20260615_until_1458__market_data_subscription_20260615_condition_layer_20260612_source_20260612_for_20260615_v1`
- status: `passed`
- projection_rows_written: `2104`
- ready_by_asset: `{}`
- not_ready_by_asset: `{"board": 127, "index": 83, "stock": 1894}`
- projection_signal_status: `{"down_volume_expanding": 6, "down_volume_flat": 8, "down_volume_shrinking": 13, "flat": 50, "unknown": 1583, "up_volume_expanding": 65, "up_volume_flat": 188, "up_volume_shrinking": 191}`
- P0/P1/P2: `0/4/0`
- rollback_sql_path: `sql/N3_B2_realtime_projection_20260615_until_1458_rollback.sql`

## Boundary

- writes_outbox: `false`
- updates_market_snapshot_payload: `false`
- outbox_consumed: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
