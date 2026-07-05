# V3_20260612_N5_REPLAY_AFTER_N4_TRIGGER_PERIOD_BASELINE_FIX_CONTRACT Action Consumer Run-Once Dry-Run Report

## Summary

- stage: V3_20260612_N5_REPLAY_AFTER_N4_TRIGGER_PERIOD_BASELINE_FIX_CONTRACT
- layer_role: N5_action
- consumer_name: v3_n5_action_replay_20260612_after_n4_trigger_period_baseline_fix_consumer_v1
- source_trigger_run_id: v3_n4_trigger_replay_20260612_after_trigger_period_baseline_fix_v1
- action_run_id: v3_n5_action_replay_20260612_after_n4_trigger_period_baseline_fix_v1
- for_trade_date: 20260612
- rollback_sql_path: sql/V3_20260612_n5_replay_after_n4_trigger_period_baseline_fix_rollback.sql
- P0/P1/P2: 1/0/0
- passed: False

## Source Run Guard

- configured: True
- passed: True
- allowed_source_run_ids: ['v3_n4_trigger_replay_20260612_after_trigger_period_baseline_fix_v1']
- denied_source_run_ids: ['v3_n4_trigger_replay_20260612_after_n3_full_day_metric_state_machine_v3', 'v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1']
- denied_observed_source_run_ids: []
- outside_allowlist_source_run_ids: []

## Baseline Check

- baseline_report_path: docs/V3_20260612_N5_REPLAY_AFTER_N4_TRIGGER_PERIOD_BASELINE_FIX_BASELINE.json
- baseline_available: True
- explainable: False
- current_read_event_count: 1187
- baseline_read_event_count: 0
- read_event_count_delta: 1187
- explanation: N5-5 read_event_count differs from N5-1 or uses a different trigger run

## N4 Outbox Statistics

- outbox_row_count: 1187
- source_run_id: {'v3_n4_trigger_replay_20260612_after_trigger_period_baseline_fix_v1': 1187}
- only_expected_source_run_id: True
- unexpected_source_run_id_count: 0
- by_event_type: {'TriggerMatched': 1187}
- by_signal_type: {'B_BUY': 778, 'S_SELL': 409}
- by_asset_kind: {'board': 68, 'index': 154, 'stock': 965}
- by_direction: {'buy': 778, 'sell': 409}
- TriggerMatched: 1187
- TriggerPendingMarketData: 0
- TriggerStateChanged: 0
- BUY_HINT runtime signal matched/pending/total: 0/0/0
- SELL_HINT runtime signal matched/pending/total: 0/0/0
- BUY_HINT trace matched/pending/total: 778/0/778
- SELL_HINT trace matched/pending/total: 409/0/409

## Period Trigger Baseline Trace

- present_count: 1187
- missing_count: 0
- null_count: 0
- empty_object_count: 0
- present_flag_true_count: 1187
- present_flag_false_count: 0
- required_period_not_ready_count: 0
- by_trigger_period: {'30m': 1187}
- present_by_trigger_period: {'30m': 1187}
- missing_by_trigger_period: {}
- baseline_versions: {'N2-R4-period-trigger-baseline-v1': 1187}

## Consumer Plan

- read_event_count: 1187
- planned_receive_count: 1187
- skipped_count: 0
- ordering: ['partition_key', 'event_time', 'outbox_id', 'event_id']
- partition_count: 235
- checkpoint_write_plan_count: 235
- would_insert_inbox_count: 1187
- would_update_checkpoint_count: 235
- would_consume_outbox_count: 0

## Action Write Plan

- candidate_count: 1187
- action_candidate_count: 1187
- quality_plan_count: 0
- planned_action_fact_count: 1187
- quality_plan_only_count: 0
- by_target_action_fact_table: {'board_action_fact': 68, 'index_action_fact': 154, 'stock_action_fact': 965}
- planned_action_fact_by_signal_type: {'B_BUY': 778, 'S_SELL': 409}
- planned_action_fact_by_direction: {'buy': 778, 'sell': 409}
- action_state: {'blocked': 911, 'executed': 276}
- confirmation_status: {'failed': 911, 'passed': 276}
- BUY_HINT planned action fact count: 778
- SELL_HINT planned action fact count: 409
- BUY_HINT trace count: 778
- SELL_HINT trace count: 409
- deprecated_runtime_signal_type_count: 0
- deprecated_hint_event_plan_count: 0
- pending_action_fact_plan_count: 0
- duplicate_source_trigger_match_id_skipped_count: 0
- duplicate_source_trigger_match_id_planned_count: 0
- physical_split_error_count: 0

## N5 Output Event Plan

- event_type_contract: ['ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped']
- by_event_type: {'ActionEligible': 0, 'ActionBlocked': 911, 'ActionExecuted': 276, 'ActionSkipped': 0}
- planned_event_count: 1187
- common_event_outbox_written: False
- executed_count: 0

## Row Count Guards

- before_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 405454, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 145223, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 52837, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 29, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 36374, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 25706, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 427, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 1611, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 27744, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}
- after_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 405454, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 145223, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 52837, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 29, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 36374, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 25706, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 427, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 1611, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 27744, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}

## Boundary Confirmation

- writes_performed: False
- common_event_inbox_updated: False
- consumer_checkpoint_updated: False
- action_fact_written: False
- action_event_written: False
- common_event_outbox_written: False
- n5_outbox_written: False
- n4_outbox_consumed: False
- market_data_pulled: False
- n1_n2_n3_n4_modified: False
- n6_user_layer_touched: False
- voice_touched: False
- sim_touched: False
- mobile_touched: False
- real_trade_touched: False
- worker_started: False
- old_system_touched: False

## Notes

- This report is a run-once dry-run only. It plans action writes but executes none of them.
- Canonical mode accepts only B_BUY / S_SELL as runtime signal_type.
- BUY_HINT / SELL_HINT are condition trace only and do not map to legacy hint events in N5 canonical runtime.
- Source-run allowlist and historical synthetic/current-real denylist are enforced by this gate.

## Formal Period Passthrough Audit

```json
{
  "planned_action_fact_count": 1187,
  "ordinary_formal_action_fact_count": 0,
  "hint_action_fact_count": 1187,
  "fabricated_formal_period_count": 0,
  "fabricated_formal_period_sample": [],
  "hint_30m_rows": 1187,
  "ordinary_missing_proof_blocked_count": 0
}
```
