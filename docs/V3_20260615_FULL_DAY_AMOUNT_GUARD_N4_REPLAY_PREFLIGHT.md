# N4 Projection Matcher Execute Preflight Report

## Summary

- result: PREFLIGHT_PASS
- layer_role: N4_trigger
- execute_run_id: n4_production_semantic_replay_20260615_market_snapshot_updated_until_1500_amount_guard_fix_v1
- trigger_context_run_id: trigger_context_snapshot_20260615_condition_layer_20260612_source_20260612_for_20260615_v1
- projection_run_id: realtime_projection_metric_20260615_trace_aligned_standard_outbox_until_1500__realtime_daily_snapshot_20260615_standard_outbox_until_1500__market_data_subscription_20260615_condition_layer_20260612_source_20260612_for_20260615_v1
- snapshot_run_id: realtime_daily_snapshot_20260615_standard_outbox_until_1500__market_data_subscription_20260615_condition_layer_20260612_source_20260612_for_20260615_v1
- accepted_source_event_count: 2104
- matched_output_count: 25
- pending_output_count: 4203
- inbox_write_plan_count: 2104
- checkpoint_write_plan_count: 2104
- P0/P1/P2: 0/0/0

## Boundary

- preflight writes_performed=false
- execute requires --execute and --user-confirmed
- N3 outbox status update is not planned
- N5/N6/action/user/voice/sim/real trade are forbidden

## Rollback

- rollback_sql_path: sql/V3_20260615_full_day_amount_guard_n4_replay_rollback.sql
