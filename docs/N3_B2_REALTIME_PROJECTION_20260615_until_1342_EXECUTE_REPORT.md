# N3-B2 Realtime Projection Execute Report

## Summary

- result: `EXECUTE_PASS`
- projection_run_id: `realtime_projection_metric_20260615_until_1342__realtime_daily_snapshot_20260615_until_1342__market_data_subscription_20260615_condition_layer_20260612_source_20260612_for_20260615_v1`
- status: `passed`
- projection_rows_written: `2104`
- ready_by_asset: `{}`
- not_ready_by_asset: `{"board": 127, "index": 83, "stock": 1894}`
- projection_signal_status: `{"down_volume_expanding": 27, "down_volume_flat": 28, "down_volume_shrinking": 43, "flat": 119, "unknown": 1583, "up_volume_expanding": 64, "up_volume_flat": 107, "up_volume_shrinking": 133}`
- P0/P1/P2: `0/4/0`
- rollback_sql_path: `sql/N3_B2_realtime_projection_20260615_until_1342_rollback.sql`

## Boundary

- writes_outbox: `false`
- updates_market_snapshot_payload: `false`
- outbox_consumed: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
