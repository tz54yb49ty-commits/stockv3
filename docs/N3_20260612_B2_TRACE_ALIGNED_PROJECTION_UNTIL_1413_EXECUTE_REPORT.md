# N3-B2 Realtime Projection Execute Report

## Summary

- result: `EXECUTE_PASS`
- projection_run_id: `realtime_projection_metric_20260612_trace_aligned_standard_outbox_until_1413__realtime_daily_snapshot_20260612_standard_outbox_until_1413__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1`
- status: `passed`
- projection_rows_written: `2082`
- ready_by_asset: `{"board": 19, "index": 33, "stock": 245}`
- not_ready_by_asset: `{"board": 108, "index": 50, "stock": 1627}`
- projection_signal_status: `{"down_volume_expanding": 53, "down_volume_flat": 25, "down_volume_shrinking": 22, "flat": 100, "unknown": 1785, "up_volume_expanding": 52, "up_volume_flat": 28, "up_volume_shrinking": 17}`
- P0/P1/P2: `0/4/0`
- rollback_sql_path: `sql/N3_20260612_B2_trace_aligned_realtime_projection_metric_for_standard_outbox_until_1413_rollback.sql`

## Boundary

- writes_outbox: `false`
- updates_market_snapshot_payload: `false`
- outbox_consumed: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
