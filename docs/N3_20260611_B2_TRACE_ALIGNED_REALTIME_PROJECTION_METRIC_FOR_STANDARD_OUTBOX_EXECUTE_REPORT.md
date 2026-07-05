# N3-B2 Realtime Projection Execute Report

## Summary

- projection_run_id: `realtime_projection_metric_20260611_trace_aligned_standard_outbox__realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- status: `passed`
- projection_rows_written: `2100`
- ready_by_asset: `{"board": 14, "index": 19, "stock": 250}`
- not_ready_by_asset: `{"board": 113, "index": 64, "stock": 1640}`
- projection_signal_status: `{"down_volume_expanding": 18, "down_volume_flat": 19, "down_volume_shrinking": 24, "flat": 89, "unknown": 1817, "up_volume_expanding": 45, "up_volume_flat": 41, "up_volume_shrinking": 47}`
- P0/P1/P2: `0/4/0`
- rollback_sql_path: `sql/N3_20260611_B2_trace_aligned_realtime_projection_metric_for_standard_outbox_rollback.sql`

## Boundary

- writes_outbox: `false`
- updates_market_snapshot_payload: `false`
- outbox_consumed: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
