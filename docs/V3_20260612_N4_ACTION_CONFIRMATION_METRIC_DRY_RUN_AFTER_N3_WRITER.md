# N4 Action-Confirmation Metric Dry-Run Report

- result: DRY_RUN_PASS
- projection_run_id: action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__condition_layer_20260611_source_20260611_for_20260612_v1
- trigger_context_run_id: trigger_context_snapshot_20260612_condition_layer_20260611_source_20260611_for_20260612_v1
- source_condition_run_id: condition_layer_20260611_source_20260611_for_20260612_v1
- for_trade_date: 20260612
- candidate_count: 4454
- would_trigger_count: 49
- would_pending_count: 4405
- quality_only_count: 0
- by_output_event_type: {'TriggerMatched': 49, 'TriggerPendingMarketData': 4405}
- by_signal_type: {'B_BUY': 2220, 'S_SELL': 2234}
- by_trigger_mark_candidate: {'30m_shrink': 2076, '30m_volume': 2087, 'normal': 291}
- metric_ready_candidate_count: 95
- pending_trigger_live_false_count: 4405
- canonical_payload_invalid_count: 0
- P0/P1/P2: 0/1/0

## Boundary

- writes_database: False
- consumes_outbox: False
- raw_minute_tables_read: False
- market_data_pulled: False
- worker_started: False
- downstream_layers_touched: False
