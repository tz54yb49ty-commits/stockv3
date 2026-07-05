# N4 Action-Confirmation Metric Dry-Run Report

- result: DRY_RUN_PASS
- projection_run_id: action_confirmation_projection_metric_20260616_until_1401_historical_replay_formal_amount_chain_unit_proof__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4
- trigger_context_run_id: trigger_context_snapshot_20260616_condition_layer_20260615_source_20260615_for_20260616_v4
- source_condition_run_id: condition_layer_20260615_source_20260615_for_20260616_v4
- for_trade_date: 20260616
- candidate_count: 4684
- would_trigger_count: 157
- would_pending_count: 4527
- quality_only_count: 0
- by_output_event_type: {'TriggerMatched': 157, 'TriggerPendingMarketData': 4527}
- by_signal_type: {'B_BUY': 2078, 'S_SELL': 2606}
- by_trigger_mark_candidate: {'30m_shrink': 154, '30m_volume': 3, 'normal': 4527}
- metric_ready_candidate_count: 1860
- pending_trigger_live_false_count: 4527
- canonical_payload_invalid_count: 0
- P0/P1/P2: 0/1/0

## Boundary

- writes_database: False
- consumes_outbox: False
- raw_minute_tables_read: False
- market_data_pulled: False
- worker_started: False
- downstream_layers_touched: False
