# N3-B2 Realtime Projection Execute Report

## Summary

- result: `EXECUTE_PASS`
- projection_run_id: `realtime_projection_metric_20260615_trace_aligned_standard_outbox_until_0947__realtime_daily_snapshot_20260615_standard_outbox_until_0947__market_data_subscription_20260615_condition_layer_20260612_source_20260612_for_20260615_v1`
- status: `passed`
- projection_rows_written: `2104`
- ready_by_asset: `{"board": 43, "index": 39, "stock": 439}`
- not_ready_by_asset: `{"board": 84, "index": 44, "stock": 1455}`
- projection_signal_status: `{"down_volume_expanding": 51, "down_volume_flat": 24, "down_volume_shrinking": 8, "flat": 27, "unknown": 1583, "up_volume_expanding": 287, "up_volume_flat": 96, "up_volume_shrinking": 28}`
- P0/P1/P2: `0/4/0`
- rollback_sql_path: `sql/N3_20260615_B2_trace_aligned_realtime_projection_metric_for_standard_outbox_until_0947_rollback.sql`

## Boundary

- writes_outbox: `false`
- updates_market_snapshot_payload: `false`
- outbox_consumed: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
