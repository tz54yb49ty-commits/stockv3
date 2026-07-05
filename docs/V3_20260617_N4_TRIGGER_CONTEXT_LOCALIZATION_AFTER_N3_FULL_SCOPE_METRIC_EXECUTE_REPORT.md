# V3_20260617_N4_TRIGGER_CONTEXT_LOCALIZATION_AFTER_N3_FULL_SCOPE_METRIC Trigger Context Snapshot Execute Report

## Summary

- stage: V3_20260617_N4_TRIGGER_CONTEXT_LOCALIZATION_AFTER_N3_FULL_SCOPE_METRIC
- layer_role: N4_trigger
- run_id: trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_v1
- source_condition_run_id: condition_layer_20260616_source_20260616_for_20260617_v1
- source_market_data_run_id: action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_v1
- for_trade_date: 20260617
- source_trade_date: 20260616
- rollback_sql_path: sql/V3_20260617_N4_trigger_context_localization_after_n3_full_scope_metric_rollback.sql
- started_at: 2026-06-17T07:14:30.199528+00:00
- finished_at: 2026-06-17T07:19:17.035169+00:00
- P0/P1/P2: 0/0/0

## Write Counts

- common_trigger_run: 1
- common_trigger_quality_item: 69
- stock_trigger_context_snapshot: 3882
- index_trigger_context_snapshot: 173
- board_trigger_context_snapshot: 271
- common_trigger_state: 0
- common_trigger_match: 0
- common_event_outbox: 0
- context_snapshot_total: 4326

## Before / After Row Counts

- common_trigger_run: before=145 after=146
- common_trigger_quality_item: before=1556 after=1625
- stock_trigger_context_snapshot: before=67769 after=71651
- index_trigger_context_snapshot: before=1666 after=1839
- board_trigger_context_snapshot: before=6368 after=6639
- common_trigger_state: before=740446 after=740446
- common_trigger_match: before=237595 after=237595
- common_event_outbox: before=653870 after=653870

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

- row_count: 4326
- row_count_by_asset_kind: {'stock': 3882, 'index': 173, 'board': 271}
- direction_distribution: {'buy': 2110, 'sell': 2216}
- buy_hint_row_count: 59
- sell_hint_row_count: 165
- period_trigger_baseline_json_missing: 0
- required_period_not_ready_rows: 0
- source_market_subscription_id_nonnull_count: 4326
- source_market_subscription_id_null_count: 0

## Upstream Trace

- market_data_run_status: passed
- market_data_run_source_condition_run_id: condition_layer_20260616_source_20260616_for_20260617_v1
- market_subscription_trace_summary: {'market_data_run_id': 'market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_v1', 'context_row_count': 4326, 'traced_context_row_count': 4326, 'untraced_context_row_count': 0, 'subscription_row_count': 2499, 'subscription_object_count': 2051, 'subscription_required_data_kind_counts': {'minute_bar_1m': 224, 'previous_day_minute_bar_1m': 224, 'realtime_daily_snapshot': 2051}, 'primary_required_data_kind': 'realtime_daily_snapshot', 'untraced_sample': []}

## Existing N4 Lineage

- old_trigger_run_count: 145
- common_event_outbox_baseline_count: 653870

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

Rollback SQL: sql/V3_20260617_N4_trigger_context_localization_after_n3_full_scope_metric_rollback.sql

Use it only before N4-4/N4-5 consumes this context run. It deletes only this run_id from common_trigger_quality_item, stock/index/board_trigger_context_snapshot, and common_trigger_run.
