# N4-3 Trigger Context Snapshot Execute Report

## Summary

- stage: N4-3
- layer_role: N4_trigger
- run_id: trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute
- source_condition_run_id: condition_layer_20260522_to_20260525_20260524014029_execute
- for_trade_date: 20260525
- source_trade_date: 20260522
- rollback_sql_path: sql/N4_3_trigger_context_snapshot_rollback.sql
- started_at: 2026-05-24T06:21:31.034094+00:00
- finished_at: 2026-05-24T06:21:32.718993+00:00
- P0/P1/P2: 0/0/0

## Write Counts

- common_trigger_run: 1
- common_trigger_quality_item: 49
- stock_trigger_context_snapshot: 4236
- index_trigger_context_snapshot: 18
- board_trigger_context_snapshot: 258
- common_trigger_state: 0
- common_trigger_match: 0
- common_event_outbox: 0
- context_snapshot_total: 4512

## Before / After Row Counts

- common_trigger_run: before=0 after=1
- common_trigger_quality_item: before=0 after=49
- stock_trigger_context_snapshot: before=0 after=4236
- index_trigger_context_snapshot: before=0 after=18
- board_trigger_context_snapshot: before=0 after=258
- common_trigger_state: before=0 after=0
- common_trigger_match: before=0 after=0
- common_event_outbox: before=0 after=0

## Post Checks

- run_id_written: true
- context_snapshot_row_count_matches_preflight: true
- context_snapshot_asset_distribution_matches_preflight: true
- context_snapshot_direction_distribution_matches_preflight: true
- context_snapshot_condition_key_distribution_matches_preflight: true
- buy_hint_and_sell_hint_present: true
- source_condition_run_id_traceable: true
- inserted_count_matches_allowed_n4_delta: true
- trigger_state_match_outbox_unchanged: true
- n2_active_run_unchanged: true
- n3_facts_and_outbox_unchanged: true
- trigger_run_status_passed: true

## Context Summary

- row_count: 4512
- row_count_by_asset_kind: {'stock': 4236, 'index': 18, 'board': 258}
- direction_distribution: {'buy': 2258, 'sell': 2254}
- buy_hint_row_count: 71
- sell_hint_row_count: 69

## Boundary Confirmation

- will_execute_sql: true
- migration_executed: false
- writes_performed: true
- trigger_context_snapshot_written: true
- trigger_run_written: true
- trigger_quality_item_written: true
- trigger_state_written: false
- trigger_match_written: false
- event_outbox_written: false
- market_data_pulled: false
- n3_event_consumed: false
- downstream_layers_touched: false
- worker_started: false
- old_system_touched: false
- external_n2_runtime_path_accessed: false

## Rollback

Rollback SQL: sql/N4_3_trigger_context_snapshot_rollback.sql

Use it only before N4-4/N4-5 consumes this context run. It deletes only this run_id from common_trigger_quality_item, stock/index/board_trigger_context_snapshot, and common_trigger_run.
