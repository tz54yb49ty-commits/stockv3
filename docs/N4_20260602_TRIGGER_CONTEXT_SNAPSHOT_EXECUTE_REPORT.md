# N4-3 Trigger Context Snapshot Execute Report

## Summary

- stage: N4-3
- layer_role: N4_trigger
- run_id: trigger_context_snapshot_20260602_condition_layer_20260601_source_20260601_v1
- source_condition_run_id: condition_layer_20260601_source_20260601_v1
- source_market_data_run_id: None
- for_trade_date: 20260602
- source_trade_date: 20260601
- rollback_sql_path: sql/N4_20260602_trigger_context_snapshot_rollback.sql
- started_at: 2026-06-02T04:17:46.439817+00:00
- finished_at: 2026-06-02T04:18:02.212281+00:00
- P0/P1/P2: 0/0/0

## Write Counts

- common_trigger_run: 1
- common_trigger_quality_item: 53
- stock_trigger_context_snapshot: 4715
- index_trigger_context_snapshot: 220
- board_trigger_context_snapshot: 1006
- common_trigger_state: 0
- common_trigger_match: 0
- common_event_outbox: 0
- context_snapshot_total: 5941

## Before / After Row Counts

- common_trigger_run: before=13 after=14
- common_trigger_quality_item: before=546 after=599
- stock_trigger_context_snapshot: before=29829 after=34544
- index_trigger_context_snapshot: before=134 after=354
- board_trigger_context_snapshot: before=1841 after=2847
- common_trigger_state: before=54028 after=54028
- common_trigger_match: before=89564 after=89564
- common_event_outbox: before=153828 after=153828

## Post Checks

- run_id_written: true
- context_snapshot_row_count_matches_preflight: true
- context_snapshot_asset_distribution_matches_preflight: true
- context_snapshot_direction_distribution_matches_preflight: true
- context_snapshot_condition_key_distribution_matches_preflight: true
- buy_hint_and_sell_hint_present: true
- source_condition_run_id_traceable: true
- period_trigger_baseline_json_localized: true
- required_period_not_ready_rows_zero: true
- inserted_count_matches_allowed_n4_delta: true
- trigger_state_match_outbox_unchanged: true
- n2_active_run_unchanged: true
- n3_facts_and_outbox_unchanged: true
- trigger_run_status_passed: true

## Context Summary

- row_count: 5941
- row_count_by_asset_kind: {'stock': 4715, 'index': 220, 'board': 1006}
- direction_distribution: {'buy': 3074, 'sell': 2867}
- buy_hint_row_count: 587
- sell_hint_row_count: 382
- period_trigger_baseline_json_missing: 0
- required_period_not_ready_rows: 0
- source_market_subscription_id_nonnull_count: 0
- source_market_subscription_id_null_count: 5941

## Upstream Trace

- market_data_run_status: None
- market_data_run_source_condition_run_id: None
- market_subscription_trace_summary: {}

## Existing N4 Lineage

- old_trigger_run_count: 13
- common_event_outbox_baseline_count: 153828

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

Rollback SQL: sql/N4_20260602_trigger_context_snapshot_rollback.sql

Use it only before N4-4/N4-5 consumes this context run. It deletes only this run_id from common_trigger_quality_item, stock/index/board_trigger_context_snapshot, and common_trigger_run.
