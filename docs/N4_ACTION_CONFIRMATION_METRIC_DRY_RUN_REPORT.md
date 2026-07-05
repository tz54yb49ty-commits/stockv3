# N4 Action-Confirmation Metric Dry-Run Report

- result: DRY_RUN_PASS
- projection_run_id: action_confirmation_projection_metric_20260602_1105__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
- trigger_context_run_id: trigger_context_snapshot_20260602_condition_layer_20260601_source_20260601_v1
- source_condition_run_id: condition_layer_20260601_source_20260601_v1
- for_trade_date: 20260602
- candidate_count: 5941
- would_trigger_count: 6
- would_pending_count: 5935
- quality_only_count: 0
- by_output_event_type: {'TriggerMatched': 6, 'TriggerPendingMarketData': 5935}
- by_signal_type: {'B_BUY': 3074, 'S_SELL': 2867}
- by_trigger_mark_candidate: {'30m_shrink': 2485, '30m_volume': 2488, 'normal': 968}
- metric_ready_candidate_count: 2907
- pending_trigger_live_false_count: 5935
- canonical_payload_invalid_count: 0
- P0/P1/P2: 0/1/0

## Boundary

- writes_database: False
- consumes_outbox: False
- raw_minute_tables_read: False
- market_data_pulled: False
- worker_started: False
- downstream_layers_touched: False
