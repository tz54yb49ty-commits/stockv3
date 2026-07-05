# N4 Projection Matcher Execute Preflight Report

## Summary

- result: PREFLIGHT_PASS
- layer_role: N4_trigger
- execute_run_id: trigger_projection_matcher_execute_20260608_v13_index_all_until_0952
- trigger_context_run_id: trigger_context_snapshot_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute
- projection_run_id: realtime_projection_metric_20260608_until_0952__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute
- snapshot_run_id: realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute
- accepted_source_event_count: 2155
- matched_output_count: 320
- pending_output_count: 3600
- inbox_write_plan_count: 2155
- checkpoint_write_plan_count: 2155
- P0/P1/P2: 0/0/0

## Boundary

- preflight writes_performed=false
- execute requires --execute and --user-confirmed
- N3 outbox status update is not planned
- N5/N6/action/user/voice/sim/real trade are forbidden

## Rollback

- rollback_sql_path: sql/N4_projection_matcher_20260608_v13_index_all_until_0952_rollback.sql
