# N4-R4 Trigger Context Snapshot Execute Report

## Summary

- stage: N4-R4
- layer_role: N4_trigger
- run_id: trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
- source_condition_run_id: condition_layer_20260522_to_20260525_20260525102249_execute
- source_market_data_run_id: market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
- for_trade_date: 20260525
- source_trade_date: 20260522
- rollback_sql_path: sql/N4_CURRENT_trigger_context_rebuild_rollback.sql
- started_at: 2026-05-25T06:46:40.945344+00:00
- finished_at: 2026-05-25T06:46:45.876484+00:00
- P0/P1/P2: 0/0/0

## Write Counts

- common_trigger_run: 1
- common_trigger_quality_item: 59
- stock_trigger_context_snapshot: 4236
- index_trigger_context_snapshot: 18
- board_trigger_context_snapshot: 258
- common_trigger_state: 0
- common_trigger_match: 0
- common_event_outbox: 0
- context_snapshot_total: 4512

## Before / After Row Counts

- common_trigger_run: before=3 after=4
- common_trigger_quality_item: before=215 after=274
- stock_trigger_context_snapshot: before=12708 after=16944
- index_trigger_context_snapshot: before=54 after=72
- board_trigger_context_snapshot: before=774 after=1032
- common_trigger_state: before=17768 after=17768
- common_trigger_match: before=53304 after=53304
- common_event_outbox: before=55492 after=55492

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

- row_count: 4512
- row_count_by_asset_kind: {'stock': 4236, 'index': 18, 'board': 258}
- direction_distribution: {'buy': 2258, 'sell': 2254}
- buy_hint_row_count: 71
- sell_hint_row_count: 69
- period_trigger_baseline_json_missing: 0
- required_period_not_ready_rows: 0
- source_market_subscription_id_nonnull_count: 4512
- source_market_subscription_id_null_count: 0

## Upstream Trace

- market_data_run_status: passed
- market_data_run_source_condition_run_id: condition_layer_20260522_to_20260525_20260525102249_execute
- market_subscription_trace_summary: {'market_data_run_id': 'market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute', 'context_row_count': 4512, 'traced_context_row_count': 4512, 'untraced_context_row_count': 0, 'subscription_row_count': 6564, 'subscription_object_count': 2188, 'subscription_required_data_kind_counts': {'minute_bar_1m': 2188, 'previous_day_minute_bar_1m': 2188, 'realtime_daily_snapshot': 2188}, 'primary_required_data_kind': 'realtime_daily_snapshot', 'untraced_sample': []}

## Existing N4 Lineage

- old_trigger_run_count: 3
- common_event_outbox_baseline_count: 55492

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

Rollback SQL: sql/N4_CURRENT_trigger_context_rebuild_rollback.sql

Use it only before N4-4/N4-5 consumes this context run. It deletes only this run_id from common_trigger_quality_item, stock/index/board_trigger_context_snapshot, and common_trigger_run.
