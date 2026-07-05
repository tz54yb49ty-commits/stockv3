# N4-5 Trigger Run-Once Execute Report

## Summary

- stage: N4-5
- layer_role: N4_trigger
- run_id: trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute
- source_condition_run_id: condition_layer_20260522_to_20260525_20260524014029_execute
- for_trade_date: 20260525
- rollback_sql_path: sql/N4_5_trigger_run_once_rollback.sql
- started_at: 2026-05-24T07:01:42.057829+00:00
- finished_at: 2026-05-24T07:02:01.549189+00:00
- P0/P1/P2: 0/0/0

## Dry-Run Match

- dry_run_candidate_count: 26652
- dry_run_matched_count: 8884
- dry_run_pending_count: 17768
- executed_matched_count: 8884
- executed_pending_count: 17768

## Write Counts

- common_trigger_state: 8884
- common_trigger_match: 26652
- common_event_outbox: 26652
- common_trigger_quality_item: 25

## Output Summary

- match_by_output_event_type: {'TriggerMatched': 8884, 'TriggerPendingMarketData': 17768}
- outbox_by_event_type: {'TriggerMatched': 8884, 'TriggerPendingMarketData': 17768}
- matched_by_signal_type: {'BUY_HINT': 71, 'B_BUY': 2187, 'B_BUY_30M_VOL': 2187, 'SELL_HINT': 69, 'S_SELL': 2185, 'S_SELL_30M_SHRINK': 2185}
- pending_by_signal_type: {'BUY_HINT': 142, 'B_BUY': 4374, 'B_BUY_30M_VOL': 4374, 'SELL_HINT': 138, 'S_SELL': 4370, 'S_SELL_30M_SHRINK': 4370}
- trigger_period_distribution: {'30m': 13536, 'D': 11022, 'M': 765, 'Q': 258, 'W': 903, 'Y': 168}
- buy_hint_matched_count: 71
- sell_hint_matched_count: 69
- payload_contract_violation_count: 0
- disallowed_outbox_event_types: []

## Before / After Row Counts

- common_trigger_state: before=0 after=8884
- common_trigger_match: before=0 after=26652
- common_trigger_quality_item: before=49 after=74
- common_event_outbox: before=0 after=26652

## Post Checks

- trigger_state_delta_matches_plan: true
- trigger_match_delta_matches_plan: true
- event_outbox_delta_matches_plan: true
- matched_count_matches_dry_run: true
- pending_count_matches_dry_run: true
- buy_hint_and_sell_hint_written: true
- outbox_event_types_allowed: true
- outbox_payload_contract_passed: true
- n2_active_run_unchanged: true
- n3_fact_rows_unchanged: true
- n3_outbox_rows_unchanged: true
- downstream_rows_unchanged: true
- trigger_run_not_updated: true
- quality_item_delta_matches_plan: true

## Boundary Confirmation

- will_execute_sql: true
- writes_performed: true
- trigger_state_written: true
- trigger_match_written: true
- trigger_quality_item_written: true
- event_outbox_written: true
- trigger_context_snapshot_written: false
- trigger_run_updated: false
- market_data_pulled: false
- real_n3_event_consumed: false
- real_common_event_outbox_consumed: false
- downstream_layers_touched: false
- action_user_voice_sim_written: false
- worker_started: false
- old_system_touched: false
- external_n2_runtime_path_accessed: false

## Rollback

Rollback SQL: sql/N4_5_trigger_run_once_rollback.sql

Use it only before downstream consumption. It deletes this run_id's N4-5 common_event_outbox, common_trigger_match, common_trigger_state, and n4_5_* quality rows.
