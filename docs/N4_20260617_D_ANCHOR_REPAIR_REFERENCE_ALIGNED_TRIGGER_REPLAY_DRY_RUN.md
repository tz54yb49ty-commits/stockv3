# N4 Action-Confirmation Metric Dry-Run Report

- result: DRY_RUN_PASS
- projection_run_id: action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
- trigger_context_run_id: trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
- source_condition_run_id: condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
- for_trade_date: 20260617
- candidate_count: 4326
- would_trigger_count: 550
- would_pending_count: 3776
- quality_only_count: 0
- by_output_event_type: {'TriggerMatched': 550, 'TriggerPendingMarketData': 3776}
- by_signal_type: {'B_BUY': 2110, 'S_SELL': 2216}
- by_trigger_mark_candidate: {'30m_shrink': 26, '30m_volume': 620, 'normal': 3680}
- metric_ready_candidate_count: 4322
- pending_trigger_live_false_count: 3776
- canonical_payload_invalid_count: 0
- P0/P1/P2: 0/1/0

## Boundary

- writes_database: False
- consumes_outbox: False
- raw_minute_tables_read: False
- market_data_pulled: False
- worker_started: False
- downstream_layers_touched: False
