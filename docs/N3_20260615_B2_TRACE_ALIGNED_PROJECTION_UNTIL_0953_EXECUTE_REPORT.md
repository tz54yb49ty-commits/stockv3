# N3-B2 Realtime Projection Execute Report

## Summary

- result: `EXECUTE_PASS`
- projection_run_id: `realtime_projection_metric_20260615_trace_aligned_standard_outbox_until_0953__realtime_daily_snapshot_20260615_standard_outbox_until_0953__market_data_subscription_20260615_condition_layer_20260612_source_20260612_for_20260615_v1`
- status: `passed`
- projection_rows_written: `2104`
- ready_by_asset: `{"board": 43, "index": 39, "stock": 439}`
- not_ready_by_asset: `{"board": 84, "index": 44, "stock": 1455}`
- projection_signal_status: `{"down_volume_expanding": 48, "down_volume_flat": 28, "down_volume_shrinking": 16, "flat": 30, "unknown": 1583, "up_volume_expanding": 243, "up_volume_flat": 109, "up_volume_shrinking": 47}`
- P0/P1/P2: `0/4/0`
- rollback_sql_path: `sql/N3_20260615_B2_trace_aligned_realtime_projection_metric_for_standard_outbox_until_0953_rollback.sql`

## Boundary

- writes_outbox: `false`
- updates_market_snapshot_payload: `false`
- outbox_consumed: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
