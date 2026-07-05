# N4-3 Trigger Context Snapshot Execute Report

## Summary

- stage: N4-3
- layer_role: N4_trigger
- run_id: trigger_context_snapshot_20260615_condition_layer_20260612_source_20260612_for_20260615_v1
- source_condition_run_id: condition_layer_20260612_source_20260612_for_20260615_v1
- source_market_data_run_id: None
- for_trade_date: 20260615
- source_trade_date: 20260612
- rollback_sql_path: sql/N4_20260615_trigger_context_localization_rollback.sql
- started_at: 2026-06-14T15:15:06.613092+00:00
- finished_at: 2026-06-14T15:16:35.483048+00:00
- P0/P1/P2: 0/0/0

## Write Counts

- common_trigger_run: 1
- common_trigger_quality_item: 60
- stock_trigger_context_snapshot: 4223
- index_trigger_context_snapshot: 205
- board_trigger_context_snapshot: 297
- common_trigger_state: 0
- common_trigger_match: 0
- common_event_outbox: 0
- context_snapshot_total: 4725

## Before / After Row Counts

- common_trigger_run: before=128 after=129
- common_trigger_quality_item: before=1241 after=1301
- stock_trigger_context_snapshot: before=55144 after=59367
- index_trigger_context_snapshot: before=1095 after=1300
- board_trigger_context_snapshot: before=5457 after=5754
- common_trigger_state: before=230106 after=230106
- common_trigger_match: before=195971 after=195971
- common_event_outbox: before=356324 after=356324

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

- row_count: 4725
- row_count_by_asset_kind: {'stock': 4223, 'index': 205, 'board': 297}
- direction_distribution: {'buy': 2210, 'sell': 2515}
- buy_hint_row_count: 106
- sell_hint_row_count: 415
- period_trigger_baseline_json_missing: 0
- required_period_not_ready_rows: 0
- source_market_subscription_id_nonnull_count: 0
- source_market_subscription_id_null_count: 4725

## Upstream Trace

- market_data_run_status: None
- market_data_run_source_condition_run_id: None
- market_subscription_trace_summary: {}

## Existing N4 Lineage

- old_trigger_run_count: 128
- common_event_outbox_baseline_count: 356324

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

Rollback SQL: sql/N4_20260615_trigger_context_localization_rollback.sql

Use it only before N4-4/N4-5 consumes this context run. It deletes only this run_id from common_trigger_quality_item, stock/index/board_trigger_context_snapshot, and common_trigger_run.
