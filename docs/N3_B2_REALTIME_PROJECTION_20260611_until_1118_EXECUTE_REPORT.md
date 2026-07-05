# N3-B2 Realtime Projection Execute Report

## Summary

- projection_run_id: `realtime_projection_metric_20260611_until_1118__realtime_daily_snapshot_20260611_until_1118__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- status: `passed`
- projection_rows_written: `2100`
- ready_by_asset: `{}`
- not_ready_by_asset: `{"board": 127, "index": 83, "stock": 1890}`
- projection_signal_status: `{"down_volume_expanding": 57, "down_volume_flat": 48, "down_volume_shrinking": 58, "flat": 40, "unknown": 1831, "up_volume_expanding": 27, "up_volume_flat": 12, "up_volume_shrinking": 27}`
- P0/P1/P2: `0/4/0`
- rollback_sql_path: `sql/N3_B2_realtime_projection_20260611_until_1118_rollback.sql`

## Boundary

- writes_outbox: `false`
- updates_market_snapshot_payload: `false`
- outbox_consumed: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
