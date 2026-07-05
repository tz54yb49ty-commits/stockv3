# N4 20260617 Full-Day Context Localization Report

- result: `CONTEXT_LOCALIZATION_PASS`
- trigger_context_run_id: `trigger_context_snapshot_20260617_full_day__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- source_condition_run_id: `condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- source_market_data_run_id: `action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- row_count_by_asset_kind: `{'stock': 3882, 'index': 173, 'board': 271}`
- canonical_distribution_full_scope_context: `{'BUY_HINT': 59, 'BUY': 1941, 'BUY:FULL': 110, 'SELL_HINT': 165, 'SELL': 2023, 'SELL:FULL': 28}`
- trigger_previous_semantic_proof: `{'period_rows': 21630, 'trigger_prev_present': 21630, 'trigger_prev_matches_previous': 21549, 'trigger_prev_matches_classification_previous': 21549, 'trigger_prev_equals_current_seed': 774, 'current_seed_trace_present': 21630, 'source_trade_date_matched': 21630}`
- downstream_ref_counts: `{'common_trigger_state': 0, 'common_trigger_match': 0, 'common_event_outbox': 0, 'common_event_inbox': 0, 'common_event_consumer_checkpoint': 0, 'common_action_run': 0}`
- rollback_sql_path: `sql/N4_20260617_full_day_context_after_n3_full_day_b2_pass_rollback.sql`
