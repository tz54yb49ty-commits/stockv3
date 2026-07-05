# N5-0 Action Preflight / Dry-Run Report

## Summary

- stage: N5-0
- layer_role: N5_action
- source_trigger_run_id: trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute
- action_run_id: action_preflight_20260525_trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029
- for_trade_date: 20260525
- P0/P1/P2: 0/0/1

## N4 Outbox Statistics

- outbox_row_count: 26652
- by_event_type: {'TriggerMatched': 8884, 'TriggerPendingMarketData': 17768}
- by_signal_type: {'BUY_HINT': 213, 'B_BUY': 6561, 'B_BUY_30M_VOL': 6561, 'SELL_HINT': 207, 'S_SELL': 6555, 'S_SELL_30M_SHRINK': 6555}
- by_asset_kind: {'board': 1536, 'index': 108, 'stock': 25008}
- by_direction: {'buy': 13335, 'sell': 13317}
- TriggerMatched: 8884
- TriggerPendingMarketData: 17768
- TriggerCleared: 0
- BUY_HINT matched/pending/total: 71/142/213
- SELL_HINT matched/pending/total: 69/138/207

## Action Candidate Dry-Run

- candidate_count: 26652
- action_candidate_count: 8884
- quality_plan_count: 17768
- planned_output_event_type: {'ActionEvent': 8336, 'HintEvent': 548}
- by_action_type: {'buy_candidate': 4445, 'pending_market_data': 17768, 'sell_candidate': 4439}
- by_lane: {'hint': 420, 'market_alert': 1632, 'policy_pending': 24600}
- by_decision_status: {'candidate': 544, 'pending_market_data': 17768, 'policy_pending': 8340}
- BUY_HINT candidate count: 71
- SELL_HINT candidate count: 69
- pending_generates_action_event_count: 0
- unclosed_minute_generates_action_event_count: 0

## Boundary Confirmation

- writes_performed: False
- action_decision_written: False
- action_event_written: False
- common_event_inbox_updated: False
- consumer_checkpoint_updated: False
- market_data_pulled: False
- real_n4_outbox_consumed: False
- user_layer_touched: False
- voice_touched: False
- sim_touched: False
- real_trade_touched: False
- worker_started: False
- old_system_touched: False

## Notes

- This report reads the N4 run-once synthetic/sample outbox for N5 development validation only.
- It does not execute migration, write action facts, consume outbox, or advance to N5-1/N6.