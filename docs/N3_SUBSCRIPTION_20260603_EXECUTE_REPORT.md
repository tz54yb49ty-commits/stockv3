# N3-6 Market Data Subscription Execute Report

## Summary

- stage: N3-6
- layer_role: N3_market_data
- market_data_run_id: market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
- source_condition_run_id: condition_layer_20260602_source_20260602_v1
- for_trade_date: 20260603
- source_trade_date: 20260602
- prev_trade_date: 20260602
- started_at: 2026-06-03T00:37:44.759712+00:00
- finished_at: 2026-06-03T00:37:48.732572+00:00
- P0/P1/P2: 0/1/0

## Dry-Run Input

- source_scope_row_count: 5222
- source_scope_row_count_by_asset_kind: {'stock': 4164, 'index': 168, 'board': 890}
- subscription_candidate_count: 5776
- dedup_subscription_count: 3028
- subscription_object_count: 2474
- object_count_by_asset_kind: {'stock': 1963, 'index': 83, 'board': 428}
- required_data_kind_counts: {'minute_bar_1m': 277, 'previous_day_minute_bar_1m': 277, 'realtime_daily_snapshot': 2474}
- previous_day_minute_required_count: 277
- previous_day_minute_date_counts: {'20260602': 277}
- dedup_ratio: 0.524238
- market_data_pull_plan_row_count: 9

## Rows Written

- common_market_data_run: 1
- common_market_data_quality_item: 34
- common_market_data_subscription_candidate: 5776
- common_market_data_subscription: 3028
- common_market_data_pull_plan: 9
- market_data_fact_rows_written: 0
- event_outbox_rows_written: 0

## Post Checks

- n3_6_preflight_p0_zero: true
- n3_6_target_run_created_once: true
- n3_6_candidate_row_count_matches: true
- n3_6_subscription_row_count_matches: true
- n3_6_pull_plan_row_count_matches: true
- n3_6_quality_item_count_matches: true
- n3_6_run_id_matches_expected: true
- n3_6_run_mode_execute: true
- n3_6_run_status_passed: true
- n3_6_run_flags_no_market_pull_or_fact: true
- n3_6_n1_n2_active_snapshot_unchanged: true
- n3_6_no_market_fact_or_event_rows_written: true

## Boundary Confirmation

- writes_performed: true
- migration_executed: false
- market_data_pulled: false
- market_data_fact_written: false
- event_outbox_written: false
- downstream_layers_touched: false
- worker_started: false
- old_system_touched: false

## Rollback

Rollback SQL:

`sql/N3_subscription_20260603_rollback.sql`

The rollback SQL is scoped to `market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`. It hard-fails before any DELETE if there are scoped outbox / inbox / checkpoint refs, downstream N3 fact refs, action-confirmation projection refs, or N4/N5/N6/user refs. If guards pass, it deletes only N3 subscription control rows: pull_plan, subscription, subscription_candidate, quality, and run.
