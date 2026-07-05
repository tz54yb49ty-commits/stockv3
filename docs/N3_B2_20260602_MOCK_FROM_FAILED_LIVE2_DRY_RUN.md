# N3-B2 20260602 Mock Projection Dry-Run From Failed B1 live2

## Summary

- result: DRY_RUN_PASS
- production_status: BLOCKED_BY_FAILED_B1_LIVE2_SOURCE
- projection_run_id: realtime_projection_metric_20260602_mock_from_failed_live2__realtime_snapshot_20260602_live2_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
- snapshot_run_id: realtime_snapshot_20260602_live2_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
- today_minute_run_id: today_minute_bar_1m_20260602_until_1018__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
- total_rows: 2485
- rows_by_asset: {'stock': 1976, 'index': 81, 'board': 428}
- projection_status: {'not_ready': 2485}
- projection_signal_status: {'unknown': 1666, 'up_volume_flat': 201, 'down_volume_expanding': 92, 'up_volume_shrinking': 153, 'flat': 70, 'down_volume_flat': 110, 'down_volume_shrinking': 104, 'up_volume_expanding': 89}
- P0/P1/P2: 0/3/0

## Boundary

- writes_performed: false
- projection_fact_written: false
- event_outbox_written: false
- downstream_layers_touched: false
- worker_started: false

## Notes

- Current source snapshot run is failed and is not production-consumable.
- This dry-run builds projection rows in memory only to continue N4/N5 validation.
- All projection rows are not_ready under current C1/latest snapshot timing, so production N4 would remain pending.