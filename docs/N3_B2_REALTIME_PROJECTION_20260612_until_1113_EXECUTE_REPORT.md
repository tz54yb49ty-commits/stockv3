# N3-B2 Realtime Projection Execute Report

## Summary

- projection_run_id: `realtime_projection_metric_20260612_until_1113__realtime_daily_snapshot_20260612_until_1113__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1`
- status: `passed`
- projection_rows_written: `2082`
- ready_by_asset: `{}`
- not_ready_by_asset: `{"board": 127, "index": 83, "stock": 1872}`
- projection_signal_status: `{"down_volume_expanding": 75, "down_volume_flat": 30, "down_volume_shrinking": 24, "flat": 67, "unknown": 1785, "up_volume_expanding": 79, "up_volume_flat": 13, "up_volume_shrinking": 9}`
- P0/P1/P2: `0/4/0`
- rollback_sql_path: `sql/N3_B2_realtime_projection_20260612_until_1113_rollback.sql`

## Boundary

- writes_outbox: `false`
- updates_market_snapshot_payload: `false`
- outbox_consumed: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
