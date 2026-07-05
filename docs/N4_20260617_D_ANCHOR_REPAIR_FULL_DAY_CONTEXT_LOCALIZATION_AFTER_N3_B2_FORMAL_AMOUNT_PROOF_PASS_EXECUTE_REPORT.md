# N4_20260617_D_ANCHOR_REPAIR_FULL_DAY_CONTEXT_LOCALIZATION_AFTER_N3_B2_FORMAL_AMOUNT_PROOF_PASS Trigger Context Snapshot Execute Report

## Summary

- stage: N4_20260617_D_ANCHOR_REPAIR_FULL_DAY_CONTEXT_LOCALIZATION_AFTER_N3_B2_FORMAL_AMOUNT_PROOF_PASS
- layer_role: N4_trigger
- run_id: trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
- source_condition_run_id: condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
- source_market_data_run_id: action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
- for_trade_date: 20260617
- source_trade_date: 20260616
- rollback_sql_path: sql/N4_20260617_d_anchor_repair_full_day_context_after_b2_formal_amount_proof_pass_rollback.sql
- started_at: 2026-06-18T12:30:11.317999+00:00
- finished_at: 2026-06-18T12:32:25.392476+00:00
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

- common_trigger_run: before=151 after=152
- common_trigger_quality_item: before=1775 after=1844
- stock_trigger_context_snapshot: before=79415 after=83297
- index_trigger_context_snapshot: before=2185 after=2358
- board_trigger_context_snapshot: before=7181 after=7452
- common_trigger_state: before=1769969 after=1769969
- common_trigger_match: before=240906 after=240906
- common_event_outbox: before=1695645 after=1695645

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
- market_data_run_source_condition_run_id: condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
- market_subscription_trace_summary: {'market_data_run_id': 'market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1', 'context_row_count': 4326, 'traced_context_row_count': 4326, 'untraced_context_row_count': 0, 'subscription_row_count': 4324, 'subscription_object_count': 2051, 'subscription_required_data_kind_counts': {'minute_bar_1m': 224, 'previous_day_minute_bar_1m': 2049, 'realtime_daily_snapshot': 2051}, 'primary_required_data_kind': 'realtime_daily_snapshot', 'untraced_sample': []}

## Existing N4 Lineage

- old_trigger_run_count: 151
- common_event_outbox_baseline_count: 1695645

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

Rollback SQL: sql/N4_20260617_d_anchor_repair_full_day_context_after_b2_formal_amount_proof_pass_rollback.sql

Use it only before N4-4/N4-5 consumes this context run. It deletes only this run_id from common_trigger_quality_item, stock/index/board_trigger_context_snapshot, and common_trigger_run.
