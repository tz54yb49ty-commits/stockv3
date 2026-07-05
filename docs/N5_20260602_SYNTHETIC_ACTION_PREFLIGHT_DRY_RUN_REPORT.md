# N5-0 Action Preflight / Dry-Run Report

## Summary

- stage: N5-0
- layer_role: N5_action
- source_trigger_run_id: trigger_context_preflight_20260602_condition_layer_20260601_source_20260601_v1_dry_run
- action_run_id: action_preflight_20260602_mock_from_n4_projection_matcher_dry_run
- for_trade_date: 20260602
- P0/P1/P2: 0/0/1

## N4 Outbox Statistics

- outbox_row_count: 40
- by_event_type: {'TriggerMatched': 20, 'TriggerPendingMarketData': 20}
- by_signal_type: {'B_BUY': 16, 'S_SELL': 24}
- by_asset_kind: {'stock': 40}
- by_direction: {'buy': 16, 'sell': 24}
- TriggerMatched: 20
- TriggerPendingMarketData: 20
- TriggerCleared: 0
- BUY_HINT matched/pending/total: 0/0/0
- SELL_HINT matched/pending/total: 0/0/0

## Action Candidate Dry-Run

- candidate_count: 40
- action_candidate_count: 20
- quality_plan_count: 20
- planned_output_event_type: {'ActionEligible': 20}
- by_action_type: {'buy_candidate': 10, 'pending_market_data': 20, 'sell_candidate': 10}
- by_lane: {'policy_pending': 40}
- by_decision_status: {'pending_confirmation': 20, 'quality_only': 20}
- BUY_HINT candidate count: 10
- SELL_HINT candidate count: 10
- pending_generates_action_event_count: 0
- unclosed_minute_generates_action_event_count: 0

## Boundary Confirmation

- writes_performed: False
- action_fact_written: False
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