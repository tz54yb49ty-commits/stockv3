# N3-C2B Closed Signal Enrichment Dry-Run Report

- result: `DRY_RUN_PASS`
- layer_role: `N3_market_data`
- c2b_run_id: `closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- c2_run_id: `closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- expected_rows: `{'stock': 16416, 'index': 72, 'board': 1016, 'total': 17504}`
- current_summary_rows: `{'stock': 16416, 'index': 72, 'board': 1016, 'total': 17504}`
- computable_rows: `17432`
- unknown_rows: `72`
- missing_rows: `72`
- baseline_missing_rows: `72`
- signal_distribution: `{'unknown': 72, 'up_volume_flat': 2494, 'up_volume_shrinking': 2260, 'flat': 2653, 'down_volume_expanding': 2806, 'down_volume_shrinking': 2011, 'down_volume_flat': 2408, 'up_volume_expanding': 2800}`
- price_direction_distribution: `{'unknown': 72, 'up': 7554, 'flat': 2653, 'down': 7225}`
- quality_distribution: `{'missing': 72, 'passed': 17432}`
- P0/P1/P2: `0/3/0`

## N4 Replay Unblock Estimate

- before: `35952`
- after: `0`
- c3_event_missing_remains: `18`

## Boundary

- side_effects: `{'read_only_database_checks': True, 'will_execute_sql': False, 'migration_executed': False, 'writes_performed': False, 'market_data_pulled': False, 'enrichment_rows_written': False, 'quality_written': False, 'event_outbox_written': False, 'outbox_consumed': False, 'inbox_or_checkpoint_written': False, 'downstream_layers_touched': False, 'worker_started': False, 'old_system_touched': False}`
- write_scope_contract: `{'allowed_future_execute_write_tables': ['common_market_data_run', 'common_market_data_quality_item', 'stock_closed_30m_signal_enrichment', 'index_closed_30m_signal_enrichment', 'board_closed_30m_signal_enrichment'], 'forbidden_write_tables': ['common_event_outbox', 'common_event_inbox', 'common_event_consumer_checkpoint', 'common_event_delivery_attempt', 'stock_closed_30m_summary', 'index_closed_30m_summary', 'board_closed_30m_summary', 'stock_minute_bar_1m', 'index_minute_bar_1m', 'board_minute_bar_1m', 'stock_realtime_projection_metric', 'index_realtime_projection_metric', 'board_realtime_projection_metric', 'stock_realtime_daily_snapshot', 'index_realtime_daily_snapshot', 'board_realtime_daily_snapshot', 'N4/N5/N6', 'worker', 'old system'], 'writes_outbox': False, 'consumes_outbox': False, 'writes_inbox_or_checkpoint': False, 'updates_closed_30m_summary': False, 'updates_minute_bar_1m': False, 'updates_realtime_projection_metric': False, 'updates_realtime_daily_snapshot': False, 'downstream_layers_touched': False, 'worker_started': False}`

## Decision

`DRY_RUN_PASS`.
