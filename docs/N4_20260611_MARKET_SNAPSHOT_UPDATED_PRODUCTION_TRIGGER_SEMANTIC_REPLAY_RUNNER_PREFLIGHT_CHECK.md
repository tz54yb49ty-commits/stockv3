# N4 Projection Matcher Execute Preflight Report

## Summary

- result: PREFLIGHT_PASS
- layer_role: N4_trigger
- execute_run_id: n4_production_semantic_replay_20260611_market_snapshot_updated_v1
- trigger_context_run_id: trigger_context_snapshot_20260611_condition_layer_20260610_source_20260610_for_20260611_v1
- projection_run_id: realtime_projection_metric_20260611_trace_aligned_standard_outbox__realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1
- snapshot_run_id: realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1
- accepted_source_event_count: 2100
- matched_output_count: 548
- pending_output_count: 251
- inbox_write_plan_count: 2100
- checkpoint_write_plan_count: 2100
- P0/P1/P2: 0/0/0

## Boundary

- preflight writes_performed=false
- execute requires --execute and --user-confirmed
- N3 outbox status update is not planned
- N5/N6/action/user/voice/sim/real trade are forbidden

## Rollback

- rollback_sql_path: sql/N4_20260611_market_snapshot_updated_production_trigger_semantic_replay_runner_generated_rollback.sql
