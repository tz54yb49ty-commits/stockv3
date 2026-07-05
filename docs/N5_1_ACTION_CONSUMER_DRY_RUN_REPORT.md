# N5-1 Action Consumer Dry-Run Report

## Summary

- stage: N5-1
- layer_role: N5_action
- consumer_name: n5_action_consumer_v1
- source_trigger_run_id: trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute
- action_run_id: action_consumer_dry_run_20260525_trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029
- for_trade_date: 20260525
- P0/P1/P2: 0/0/1

## Consumer Plan

- read_event_count: 26652
- planned_receive_count: 26652
- skipped_count: 0
- skip_reasons: {}
- ordering: ['partition_key', 'event_time', 'outbox_id', 'event_id']
- partition_count: 2188
- accepted_partition_count: 2188
- checkpoint_write_plan_count: 2188
- would_insert_inbox_count: 26652
- would_update_checkpoint_count: 2188
- would_consume_outbox_count: 0

## N4 Event Distribution

- by_event_type: {'TriggerMatched': 8884, 'TriggerPendingMarketData': 17768}
- by_signal_type: {'BUY_HINT': 213, 'B_BUY': 6561, 'B_BUY_30M_VOL': 6561, 'SELL_HINT': 207, 'S_SELL': 6555, 'S_SELL_30M_SHRINK': 6555}
- by_asset_kind: {'board': 1536, 'index': 108, 'stock': 25008}
- by_direction: {'buy': 13335, 'sell': 13317}
- BUY_HINT matched/pending/total: 71/142/213
- SELL_HINT matched/pending/total: 69/138/207

## Action Candidate Dry-Run

- candidate_count: 26652
- action_candidate_count: 8884
- quality_plan_count: 17768
- planned_output_event_type: {'ActionEvent': 8336, 'HintEvent': 548}
- pending_generates_action_event_count: 0
- BUY_HINT candidate count: 71
- SELL_HINT candidate count: 69

## Boundary Confirmation

- writes_performed: False
- common_event_inbox_updated: False
- consumer_checkpoint_updated: False
- n4_outbox_status_updated: False
- action_decision_written: False
- action_event_written: False
- market_data_pulled: False
- user_layer_touched: False
- voice_touched: False
- sim_touched: False
- real_trade_touched: False
- worker_started: False
- old_system_touched: False

## Notes

- This report plans N5 consumer behavior only; it does not execute inbox/checkpoint writes.
- The current N4 outbox is synthetic/sample run-once material for N5 development validation.