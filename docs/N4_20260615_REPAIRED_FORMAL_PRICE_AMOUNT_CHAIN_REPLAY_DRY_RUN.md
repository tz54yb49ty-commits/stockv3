# N4 Action-Confirmation Metric Dry-Run Report

- result: DRY_RUN_PASS
- projection_run_id: action_confirmation_projection_metric_20260615_until_1500_after_n4_amount_guard_fix_v1
- trigger_context_run_id: trigger_context_snapshot_20260615_condition_layer_20260612_source_20260612_for_20260615_v1
- source_condition_run_id: condition_layer_20260612_source_20260612_for_20260615_v1
- for_trade_date: 20260615
- candidate_count: 4725
- would_trigger_count: 0
- would_pending_count: 4725
- quality_only_count: 0
- by_output_event_type: {'TriggerPendingMarketData': 4725}
- by_signal_type: {'B_BUY': 2210, 'S_SELL': 2515}
- by_trigger_mark_candidate: {'30m_shrink': 2, '30m_volume': 13, 'normal': 4710}
- metric_ready_candidate_count: 75
- pending_trigger_live_false_count: 4725
- canonical_payload_invalid_count: 0
- P0/P1/P2: 0/1/0

## Boundary

- writes_database: False
- consumes_outbox: False
- raw_minute_tables_read: False
- market_data_pulled: False
- worker_started: False
- downstream_layers_touched: False
