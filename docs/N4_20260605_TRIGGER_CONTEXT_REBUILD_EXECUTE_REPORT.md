# N4-R4 Trigger Context Snapshot Execute Report

## Summary

- stage: N4-R4
- layer_role: N4_trigger
- run_id: trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1
- source_condition_run_id: condition_layer_20260604_source_20260604_v1
- source_market_data_run_id: realtime_snapshot_20260605_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1
- for_trade_date: 20260605
- source_trade_date: 20260604
- rollback_sql_path: sql/N4_20260605_trigger_context_rebuild_rollback.sql
- started_at: 2026-06-05T02:16:26.298252+00:00
- finished_at: 2026-06-05T02:16:43.974452+00:00
- P0/P1/P2: 0/0/0

## Write Counts

- common_trigger_run: 1
- common_trigger_quality_item: 62
- stock_trigger_context_snapshot: 4186
- index_trigger_context_snapshot: 20
- board_trigger_context_snapshot: 912
- common_trigger_state: 0
- common_trigger_match: 0
- common_event_outbox: 0
- context_snapshot_total: 5118

## Before / After Row Counts

- common_trigger_run: before=19 after=20
- common_trigger_quality_item: before=702 after=764
- stock_trigger_context_snapshot: before=38708 after=42894
- index_trigger_context_snapshot: before=522 after=542
- board_trigger_context_snapshot: before=3737 after=4649
- common_trigger_state: before=74961 after=74961
- common_trigger_match: before=110497 after=110497
- common_event_outbox: before=187526 after=187526

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

- row_count: 5118
- row_count_by_asset_kind: {'stock': 4186, 'index': 20, 'board': 912}
- direction_distribution: {'buy': 2601, 'sell': 2517}
- buy_hint_row_count: 212
- sell_hint_row_count: 130
- period_trigger_baseline_json_missing: 0
- required_period_not_ready_rows: 0
- source_market_subscription_id_nonnull_count: 5118
- source_market_subscription_id_null_count: 0

## Upstream Trace

- market_data_run_status: passed
- market_data_run_source_condition_run_id: condition_layer_20260604_source_20260604_v1
- market_subscription_trace_summary: {'market_data_run_id': 'market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1', 'context_row_count': 5118, 'traced_context_row_count': 5118, 'untraced_context_row_count': 0, 'subscription_row_count': 3073, 'subscription_object_count': 2389, 'subscription_required_data_kind_counts': {'minute_bar_1m': 342, 'previous_day_minute_bar_1m': 342, 'realtime_daily_snapshot': 2389}, 'primary_required_data_kind': 'realtime_daily_snapshot', 'untraced_sample': []}

## Existing N4 Lineage

- old_trigger_run_count: 19
- common_event_outbox_baseline_count: 187526

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

Rollback SQL: sql/N4_20260605_trigger_context_rebuild_rollback.sql

Use it only before N4-4/N4-5 consumes this context run. It deletes only this run_id from common_trigger_quality_item, stock/index/board_trigger_context_snapshot, and common_trigger_run.
