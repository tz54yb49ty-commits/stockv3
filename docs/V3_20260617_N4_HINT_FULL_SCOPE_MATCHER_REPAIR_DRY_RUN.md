# N4 Action-Confirmation Metric Dry-Run Report

- result: DRY_RUN_PASS
- projection_run_id: action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_v1
- trigger_context_run_id: trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_v1
- source_condition_run_id: condition_layer_20260616_source_20260616_for_20260617_v1
- for_trade_date: 20260617
- candidate_count: 4326
- would_trigger_count: 1159
- would_pending_count: 3167
- quality_only_count: 0
- by_output_event_type: {'TriggerMatched': 1159, 'TriggerPendingMarketData': 3167}
- by_signal_type: {'B_BUY': 2110, 'S_SELL': 2216}
- by_trigger_mark_candidate: {'30m_shrink': 377, '30m_volume': 356, 'normal': 3593}
- metric_ready_candidate_count: 4320
- pending_trigger_live_false_count: 3167
- canonical_payload_invalid_count: 0
- P0/P1/P2: 0/1/0

## Boundary

- writes_database: False
- consumes_outbox: False
- raw_minute_tables_read: False
- market_data_pulled: False
- worker_started: False
- downstream_layers_touched: False
