# N4-20260528-v2-context-rebuild Trigger Context Snapshot Execute Report

## Summary

- stage: N4-20260528-v2-context-rebuild
- layer_role: N4_trigger
- run_id: trigger_context_snapshot_20260528_condition_layer_20260527_source_20260527_v2
- source_condition_run_id: condition_layer_20260527_source_20260527_v2
- source_market_data_run_id: realtime_snapshot_20260528_market_data_subscription_20260528_condition_layer_20260527_source_20260527_v2
- for_trade_date: 20260528
- source_trade_date: 20260527
- rollback_sql_path: sql/N4_20260528_V2_trigger_context_rebuild_rollback.sql
- started_at: 2026-05-28T09:23:35.078201+00:00
- finished_at: 2026-05-28T09:23:39.162475+00:00
- P0/P1/P2: 0/0/0

## Write Counts

- common_trigger_run: 1
- common_trigger_quality_item: 62
- stock_trigger_context_snapshot: 4307
- index_trigger_context_snapshot: 22
- board_trigger_context_snapshot: 273
- common_trigger_state: 0
- common_trigger_match: 0
- common_event_outbox: 0
- context_snapshot_total: 4602

## Before / After Row Counts

- common_trigger_run: before=8 after=9
- common_trigger_quality_item: before=373 after=435
- stock_trigger_context_snapshot: before=21251 after=25558
- index_trigger_context_snapshot: before=94 after=116
- board_trigger_context_snapshot: before=1305 after=1578
- common_trigger_state: before=27419 after=27419
- common_trigger_match: before=62955 after=62955
- common_event_outbox: before=83063 after=83063

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
- source_market_data_run_id_traceable: true
- source_market_subscription_trace_complete: true

## Context Summary

- row_count: 4602
- row_count_by_asset_kind: {'stock': 4307, 'index': 22, 'board': 273}
- direction_distribution: {'buy': 2431, 'sell': 2171}
- buy_hint_row_count: 286
- sell_hint_row_count: 31
- period_trigger_baseline_json_missing: 0
- required_period_not_ready_rows: 0
- source_market_subscription_id_nonnull_count: 4602
- source_market_subscription_id_null_count: 0

## Upstream Trace

- market_data_run_status: passed
- market_data_run_source_condition_run_id: condition_layer_20260527_source_20260527_v2
- market_subscription_trace_summary: {'market_data_run_id': 'market_data_subscription_20260528_condition_layer_20260527_source_20260527_v2', 'context_row_count': 4602, 'traced_context_row_count': 4602, 'untraced_context_row_count': 0, 'subscription_row_count': 2780, 'subscription_object_count': 2146, 'subscription_required_data_kind_counts': {'minute_bar_1m': 317, 'previous_day_minute_bar_1m': 317, 'realtime_daily_snapshot': 2146}, 'primary_required_data_kind': 'realtime_daily_snapshot', 'untraced_sample': []}

## Existing N4 Lineage

- old_trigger_run_count: 8
- common_event_outbox_baseline_count: 83063

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

Rollback SQL: sql/N4_20260528_V2_trigger_context_rebuild_rollback.sql

Use it only before N4-4/N4-5 consumes this context run. It deletes only this run_id from common_trigger_quality_item, stock/index/board_trigger_context_snapshot, and common_trigger_run.
