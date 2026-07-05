# Runtime 20260608 N3-to-N6 One-shot Closeout

- result: `CLOSEOUT_PASS`
- layer_role: `runtime_control`
- registered_at: `2026-06-08T13:01:22+08:00`
- scope: 20260608 v13 index-all lineage through N3 A1/B1/C1/B2, N4 context/matcher, N5 action confirmation, and N6 readonly shadow projection/card until 09:52.

## Lineage

- `n2_active_condition_run`: `condition_layer_20260605_to_20260608_v13_index_all_execute`
- `n3_subscription_run`: `market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- `n3_a1_previous_day_minute_preload_run`: `previous_day_minute_preload_20260605__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- `n3_b1_realtime_snapshot_run`: `realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- `n3_c1_today_minute_run`: `today_minute_bar_1m_20260608_until_0952__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- `n3_b2_realtime_projection_run`: `realtime_projection_metric_20260608_until_0952__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- `n4_context_refresh_run`: `trigger_context_snapshot_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- `n4_projection_matcher_run`: `trigger_projection_matcher_execute_20260608_v13_index_all_until_0952`
- `n5_action_confirmation_run`: `action_consumer_execute_20260608_v13_index_all_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952`
- `n6_shadow_projection_run`: `user_projection_shadow_20260608_v13_index_all_until_0952__action_consumer_execute_20260608_v13_index_all_until_0952`

## Stage Summary

| stage | status | key rows | quality | outbox |
|---|---|---|---|---|
| N3-A1 previous-day minute preload | `passed` | minute_total=89280, status_total=372 | `0/0/0` | rows_written=0 |
| N3-B1 realtime daily snapshot | `passed` | snapshot_total=2155 | `0/0/0` | MarketSnapshotUpdated_pending=2155 |
| N3-C1 today minute until 09:52 | `passed` | minute_total=8184 | `0/0/0` | rows_written=0 |
| N3-B2 realtime projection until 09:52 | `passed` | projection_total=2155, ready=359, not_ready=1796 | `0/4/0` | rows_written=0 |
| N4 context refresh | `passed` | context_total=4677 | `0/0/0` | rows_written=0 |
| N4 projection matcher | `passed` | trigger_state=3920, trigger_match=3920 | `0/0/0` | TriggerMatched_pending=320, TriggerPendingMarketData_pending=3600 |
| N5 action confirmation | `passed` | action_events=201, stock_action_fact=195, index_action_fact=6, board_action_fact=0 | `0/0/0` | ActionEligible_pending=201 |
| N6 readonly shadow projection/card | `passed` | user_signal_projection=201, user_signal_card=201, user_notification_queue=0 | `0/5/2` | rows_written=- |

## N4 Matcher Note

- `common_trigger_match_actual=3920`
- `TriggerMatched=320`
- `TriggerPendingMarketData=3600`
- closeout treatment: accepted_for_this_lineage_as reviewed outcome persistence; N5 produced actions only from canonical TriggerMatched/eligible path and N6 projected only ActionEligible.

## N6 Projection/Card Proof

- `user_projection_run` = `1`
- `user_signal_projection` = `201`
- `user_signal_card` = `201`
- `user_notification_queue` = `0`
- N5 outbox remains pending and was not consumed by N6 shadow projection.

## Rollback Registry Summary

- `sql/N3_B1_realtime_snapshot_20260608_v13_index_all_rollback.sql`: hard_fail_before_DML=`True`, no_cascade/drop/truncate=`True/True/True`
- `sql/N3_C1_today_minute_bar_1m_20260608_v13_index_all_until_0952_rollback.sql`: hard_fail_before_DML=`True`, no_cascade/drop/truncate=`True/True/True`
- `sql/N3_B2_realtime_projection_20260608_v13_index_all_until_0952_rollback.sql`: hard_fail_before_DML=`True`, no_cascade/drop/truncate=`True/True/True`
- `sql/N4_trigger_context_refresh_20260608_v13_index_all_rollback.sql`: hard_fail_before_DML=`True`, no_cascade/drop/truncate=`True/True/True`
- `sql/N4_projection_matcher_20260608_v13_index_all_until_0952_rollback.sql`: hard_fail_before_DML=`True`, no_cascade/drop/truncate=`True/True/True`
- `sql/N5_action_confirmation_20260608_v13_index_all_until_0952_rollback.sql`: hard_fail_before_DML=`True`, no_cascade/drop/truncate=`True/True/True`
- `sql/N6_projection_20260608_v13_index_all_until_0952_rollback.sql`: hard_fail_before_DML=`True`, no_cascade/drop/truncate=`True/True/True`

## Forbidden Scope Final Proof

- `runtime_control_executed_business_command` = `False`
- `rollback_executed` = `False`
- `n5_outbox_consumed_by_n6` = `False`
- `n5_outbox_updated_by_n6` = `False`
- `notification_queue_written_for_n6_run` = `False`
- `worker_started` = `False`
- `delivery_push_voice_mobile` = `False`
- `sim_order_trade_position_pnl` = `False`
- `proposal_order_trade` = `False`
- `real_trade` = `False`
- `old_system_touched` = `False`

## UI Readonly Closeout

- `http://127.0.0.1:8786/n6/action-events` -> `200` / `ok`
- `http://127.0.0.1:8786/api/n6/ui/v1/signals?source_run_id=user_projection_shadow_20260608_v13_index_all_until_0952__action_consumer_execute_20260608_v13_index_all_until_0952` -> `401` / `auth_required_no_bypass`
- `http://127.0.0.1:8786/api/n6/ui/v1/lineage-stats` -> `401` / `auth_required_no_bypass`

## Validation Summary

- `rollback_static_check`: `PASS`
- `compileall`: `PASS`
- `targeted_runtime_tests`: `PASS: 81 tests OK`
- `n6_user_app_tests`: `PASS: 80 tests OK`
- `key_json_parse`: `PASS`
- `new_artifact_json_parse`: `PASS`
- `git_diff_check`: `PASS`

Recommended next gate: `OPTIONAL_N6_AUTHENTICATED_UI_READONLY_SMOKE_GATE_OR_END_20260608_0952_LINEAGE`
