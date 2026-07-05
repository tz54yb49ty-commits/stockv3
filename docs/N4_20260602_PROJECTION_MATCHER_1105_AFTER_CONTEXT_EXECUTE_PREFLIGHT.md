# N4 Projection Matcher Execute Preflight Report

## Summary

- result: PREFLIGHT_PASS
- layer_role: N4_trigger
- execute_run_id: trigger_projection_matcher_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
- trigger_context_run_id: trigger_context_snapshot_20260602_condition_layer_20260601_source_20260601_v1
- projection_run_id: realtime_projection_metric_20260602_live3__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
- snapshot_run_id: realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
- accepted_source_event_count: 2487
- matched_output_count: 478
- pending_output_count: 3484
- inbox_write_plan_count: 2487
- checkpoint_write_plan_count: 2487
- P0/P1/P2: 0/0/0

## Boundary

- preflight writes_performed=false
- execute requires --execute and --user-confirmed
- N3 outbox status update is not planned
- N5/N6/action/user/voice/sim/real trade are forbidden

## Rollback

- rollback_sql_path: sql/N4_20260602_projection_matcher_1105_rollback.sql
