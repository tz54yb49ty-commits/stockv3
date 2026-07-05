# N4-4 Synthetic Trigger Dry-Run Report

## Summary

- stage: N4-4
- layer_role: N4_trigger
- trigger_context_run_id: trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute
- source_condition_run_id: condition_layer_20260522_to_20260525_20260525003855_execute
- source_market_data_run_id: market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525003855_execute
- for_trade_date: 20260525
- context_candidate_count: 4512
- period_trigger_baseline_json_missing: 0
- required_period_not_ready_rows: 0
- period_trigger_baseline_trace_count: 26652
- candidate_count: 26652
- matched_count: 8884
- pending_count: 17768
- P0/P1/P2: 0/0/0

## Distribution

- by_asset_kind: {'board': 1536, 'index': 108, 'stock': 25008}
- by_direction: {'buy': 13335, 'sell': 13317}
- by_signal_type: {'BUY_HINT': 213, 'B_BUY': 6561, 'B_BUY_30M_VOL': 6561, 'SELL_HINT': 207, 'S_SELL': 6555, 'S_SELL_30M_SHRINK': 6555}
- by_event_type: {'MarketDataDelayed': 8884, 'MarketDataMissing': 8884, 'MarketSnapshotUpdated': 4372, 'MinuteBarClosed': 4512}
- trigger_period_distribution: {'30m': 13536, 'D': 11022, 'M': 765, 'Q': 258, 'W': 903, 'Y': 168}
- matched_by_signal_type: {'BUY_HINT': 71, 'B_BUY': 2187, 'B_BUY_30M_VOL': 2187, 'SELL_HINT': 69, 'S_SELL': 2185, 'S_SELL_30M_SHRINK': 2185}
- pending_by_event_type: {'MarketDataDelayed': 8884, 'MarketDataMissing': 8884}
- buy_hint_matched_count: 71
- sell_hint_matched_count: 69

## Planned Output Events

- matched_output_event_types: {'TriggerMatched': 8884}
- pending_output_event_types: {'TriggerPendingMarketData': 17768}

## Outbox Lineage

- common_event_outbox_baseline_count: 26652
- current_context_run_outbox_count: 0
- stale_n4_outbox_count: 26652
- stale_n4_outbox_by_source_run: [{'source_run_id': 'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute', 'event_type': 'TriggerMatched', 'row_count': 8884}, {'source_run_id': 'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute', 'event_type': 'TriggerPendingMarketData', 'row_count': 17768}]
- current_run_has_n5_usable_outbox: false
- n5_use_guidance: Existing N4 outbox rows belong to prior trigger context runs. This dry-run creates no current-run outbox, so N5 must not consume the stale baseline.

## Quality

- P0 passed n4_4_trigger_context_run_ready: expected=trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute actual=trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute
- P0 passed n4_4_local_context_rows_available: expected=>0 actual=4512
- P0 passed n4_4_period_trigger_baseline_json_present: expected=missing=0 actual=0
- P0 passed n4_4_required_period_baseline_ready: expected=required_period_not_ready_rows=0 actual=0
- P0 passed n4_4_plan_payload_traces_period_baseline: expected=26652 actual=26652
- P0 passed n4_4_uses_synthetic_event_types: expected=MarketSnapshotUpdated,MinuteBarClosed,MarketDataDelayed,MarketDataMissing actual=MarketDataDelayed,MarketDataMissing,MarketSnapshotUpdated,MinuteBarClosed
- P0 passed n4_4_snapshot_matches_ordinary_buy_sell: expected=matched ordinary B_BUY/S_SELL > 0 actual=4372
- P0 passed n4_4_minute_matches_buy_sell_hint: expected=BUY_HINT and SELL_HINT matched > 0 actual=BUY_HINT=71 SELL_HINT=69
- P0 passed n4_4_market_data_missing_pending_only: expected=pending>0 matched=0 actual=pending=8884 matched=0
- P0 passed n4_4_market_data_delayed_pending_only: expected=pending>0 matched=0 actual=pending=8884 matched=0
- P0 passed n4_4_no_database_rows_written: expected=before row counts equal after row counts actual=unchanged
- P0 passed n4_4_no_current_context_outbox_available: expected=0 actual=0
- P0 passed n4_4_existing_outbox_is_prior_run_only: expected=current context run outbox is absent actual=old_n4_outbox_count=26652 current_context_run_outbox_count=0
- P0 passed n4_4_no_real_outbox_consumption: expected=None actual=None
- P0 passed n4_4_no_market_data_pull: expected=None actual=None
- P0 passed n4_4_no_trigger_fact_write: expected=None actual=None
- P0 passed n4_4_no_downstream_write: expected=None actual=None
- P0 passed n4_4_no_external_n2_runtime_path: expected=None actual=None

## Boundary Confirmation

- read_only_database_checks: true
- will_execute_sql: false
- writes_performed: false
- trigger_state_written: false
- trigger_match_written: false
- event_outbox_written: false
- market_data_pulled: false
- real_n3_event_consumed: false
- real_common_event_outbox_consumed: false
- downstream_layers_touched: false
- action_user_voice_sim_written: false
- worker_started: false
- old_system_touched: false
- external_n2_runtime_path_accessed: false

## Rollback

No DB rows are written in N4-4. Rollback is deleting this dry-run report if needed.
