# N3-C2B Closed Signal Enrichment Execute Preflight

- result: `PREFLIGHT_PASS`
- layer_role: `N3_market_data`
- c2b_run_id: `closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- runner_readiness: `ready`
- execute_authorized: `False`
- c2b_execute_allowed_now: `False`
- c2b_execute_allowed_reason: `awaiting_final_gate_user_confirmation`
- blockers: `[]`
- expected_enrichment_rows: `{'stock': 16416, 'index': 72, 'board': 1016, 'total': 17504}`
- signal_distribution: `{'down_volume_expanding': 2806, 'down_volume_flat': 2408, 'down_volume_shrinking': 2011, 'flat': 2653, 'unknown': 72, 'up_volume_expanding': 2800, 'up_volume_flat': 2494, 'up_volume_shrinking': 2260}`
- baseline_guard: `{'run_exists': False, 'enrichment_rows_for_c2b_run': {'stock': 0, 'index': 0, 'board': 0}, 'quality_rows_for_c2b_run': 0, 'outbox_rows_for_c2b_run': 0, 'inbox_rows_for_c2b_run': 0, 'checkpoint_rows_for_c2b_run': 0}`
- c3_outbox_status: `{'pending': 17432}`
- writes_outbox: `False`
- consumes_c3_outbox: `False`
- rollback_sql_path: `sql/N3_C2B_closed_signal_enrichment_business_rollback.sql`

## Boundary

- allowed_writes: `['common_market_data_run', 'common_market_data_quality_item', 'stock_closed_30m_signal_enrichment', 'index_closed_30m_signal_enrichment', 'board_closed_30m_signal_enrichment']`
- forbidden_writes: `['common_event_outbox', 'common_event_inbox', 'common_event_consumer_checkpoint', 'common_event_delivery_attempt', 'stock_closed_30m_summary', 'index_closed_30m_summary', 'board_closed_30m_summary', 'stock_minute_bar_1m', 'index_minute_bar_1m', 'board_minute_bar_1m', 'stock_realtime_projection_metric', 'index_realtime_projection_metric', 'board_realtime_projection_metric', 'stock_realtime_daily_snapshot', 'index_realtime_daily_snapshot', 'board_realtime_daily_snapshot', 'condition tables', 'trigger tables', 'action tables', 'user tables', 'voice/mobile/sim/position tables', 'N4/N5/N6', 'worker', 'old system']`
- side_effects: `{'read_only_database_checks': True, 'writes_performed': False, 'enrichment_rows_written': False, 'quality_written': False, 'event_outbox_written': False, 'outbox_consumed': False, 'inbox_or_checkpoint_written': False, 'downstream_layers_touched': False, 'worker_started': False, 'old_system_touched': False}`
