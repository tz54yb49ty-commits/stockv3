# N4 Projection Matcher 20260608 v13 index-all Rollback Post Review

- result: `POST_REVIEW_PASS`
- layer_role: `runtime_control`
- generated_at: `2026-06-08T14:29:07+08:00`
- target_run_id: `trigger_projection_matcher_execute_20260608_v13_index_all_until_0952`
- rollback_executed_by_this_gate: `False`

## Rollback Proof Summary

- rollback report: `ROLLBACK_PASS`
- SQL exit code: `0`
- deleted rows: `{"common_event_consumer_checkpoint": 2155, "common_event_inbox": 2155, "common_event_outbox": 3920, "common_trigger_match": 3920, "common_trigger_quality_item": 10, "common_trigger_run": 1, "common_trigger_state": 3920}`
- report scoped post-check: `{"common_event_consumer_checkpoint": 0, "common_event_inbox": 0, "common_event_outbox": 0, "common_trigger_match": 0, "common_trigger_quality_item": 0, "common_trigger_run": 0, "common_trigger_state": 0}`

## Live Post-Check Proof

Target run scoped rows are all zero:

- common_trigger_run: `0`
- common_trigger_quality_item: `0`
- common_trigger_match: `0`
- common_trigger_state: `0`
- N4 common_event_outbox: `0`
- N4 consumer inbox: `0`
- N4 consumer checkpoint: `0`

## Upstream Preserved Proof

- N3 MarketSnapshotUpdated outbox: `{"MarketSnapshotUpdated": {"pending": 2155}}`
- N3 snapshot facts: `{"board_realtime_daily_snapshot": 127, "index_realtime_daily_snapshot": 83, "stock_realtime_daily_snapshot": 1945}`
- N3 projection facts: `{"board_realtime_projection_metric": 127, "index_realtime_projection_metric": 83, "stock_realtime_projection_metric": 1945}`
- N3 run status: `{"realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute": {"P0": 0, "P1": 0, "P2": 0, "status": "passed"}, "realtime_projection_metric_20260608_until_0952__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute": {"P0": 0, "P1": 4, "P2": 0, "status": "passed"}}`
- N2/N1 facts unchanged basis: rollback SQL delete scope contains only N4 trigger/event-infra target rows.

## Downstream Clean Proof

- downstream refs: `{"board_action_fact": 0, "common_action_event": 0, "common_action_run": 0, "index_action_fact": 0, "n5_checkpoint_refs_for_source_n4": 0, "n5_common_event_inbox_for_source_n4": 0, "n5_common_event_outbox": 0, "stock_action_fact": 0, "user_notification_queue": 0, "user_projection_run": 0, "user_signal_card": 0, "user_signal_projection": 0, "user_sim_order": 0, "user_sim_position": 0, "user_sim_trade": 0}`
- N5 rollback post-review: `POST_REVIEW_PASS`
- N6 rollback post-review: `POST_REVIEW_PASS`

## Rollback SQL Static Check

- SQL path: `sql/N4_projection_matcher_20260608_v13_index_all_until_0952_v4_breach_repair_rollback.sql`
- hard-fail before first DELETE/UPDATE: `True`
- delete targets exact: `True`
- no CASCADE/DROP/TRUNCATE: `True/True/True`
- guards present: `{"delivered_delivering": true, "delivery_attempt": true, "downstream_table_scan": true, "event_ledger": true, "non_target_checkpoint": true}`

## Forbidden Scope Proof

- repair_executed_by_this_gate=false
- n4_matcher_rerun_by_this_gate=false
- n5_entered_by_this_gate=false
- n6_entered_by_this_gate=false
- n3_outbox_status_updated_by_this_gate=false
- outbox_consumed_by_this_gate=false
- worker_started=false
- delivery/push/voice/mobile=false
- sim/position/pnl/real_trade=false
- proposal/order/trade=false
- old_system_touched=false

## Validation Summary

- rollback report JSON parse: `PASS`
- new artifact JSON parse: `PASS`
- live DB post-check: `PASS`
- rollback SQL static check: `PASS`
- git diff check: `PASS`

Recommended next gate: `N4_PROJECTION_MATCHER_V4_ENFORCEMENT_REPAIR_IMPLEMENTATION_GATE`
