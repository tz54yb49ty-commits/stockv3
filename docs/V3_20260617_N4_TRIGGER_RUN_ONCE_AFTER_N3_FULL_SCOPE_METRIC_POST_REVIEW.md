# V3 20260617 N4 Trigger Run-Once After N3 Full-Scope Metric Post Review

- result: `BLOCKED`
- trigger_context_run_id: `trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_v1`
- trigger_replay_run_id / execute_run_id: `trigger_action_confirmation_metric_execute_20260617_until_1352__condition_layer_20260616_source_20260616_for_20260617_v1`
- source_condition_run_id: `condition_layer_20260616_source_20260616_for_20260617_v1`
- source_subscription_run_id: `market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_v1`
- source_snapshot_run_id: `realtime_daily_snapshot_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_v1`
- source_today_minute_run_id: `today_minute_bar_1m_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_v1`
- source_expansion_run_id: `historical_closed_minute_source_expansion_20260617_until_1352_full_scope_missing__condition_layer_20260616_source_20260616_for_20260617_v1`
- source_metric_run_id: `action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_v1`

## Distribution
- TriggerMatched: `1130`
- TriggerPendingMarketData: `3196`
- TriggerStateChanged: `0`
- common_trigger_match: `1130`

## Inclusion Proof
- ordinary BUY/SELL: passed; BUY rows 1941 -> 313 matched / 1628 pending, SELL rows 2023 -> 763 matched / 1260 pending.
- BUY:FULL/SELL:FULL: passed; BUY:FULL rows 110 -> 38 matched / 72 pending, SELL:FULL rows 28 -> 16 matched / 12 pending.
- BUY_HINT/SELL_HINT: blocked; N3 full-scope metric has 59/165 context-compatible rows and 7/22 calibrated-pass candidates, but N4 emitted 0 hint TriggerMatched rows.

## Pending Proof
- TriggerPendingMarketData rows: `3196`
- pending writes_common_trigger_match=true: `0`
- pending is_n5_action_entry=true: `0`
- pending common_trigger_match rows: `0`
- N5 refs: `0`

## Rollback
- execute rollback SQL: `sql/V3_20260617_N4_trigger_run_once_after_n3_full_scope_metric_rollback.sql`
- context rollback SQL: `sql/V3_20260617_N4_trigger_context_localization_after_n3_full_scope_metric_rollback.sql`
- rollback_executed: `false`

## Blocker
- Current N4 matcher does not use `raw_json.full_scope_condition_rows` for context-specific BUY_HINT/SELL_HINT scope matching.
- Do not enter N5/N6 from this run.
