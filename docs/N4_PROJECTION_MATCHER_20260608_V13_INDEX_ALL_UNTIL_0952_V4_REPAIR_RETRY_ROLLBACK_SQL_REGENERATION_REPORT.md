# N4 Projection Matcher V4 Repair Retry Rollback SQL Regeneration Report

- result: `REGENERATION_PASS`
- target_run_id: `trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry`
- rollback_sql_path: `sql/N4_projection_matcher_20260608_v13_index_all_until_0952_v4_repair_retry_rollback.sql`

## Live Readiness Proof
- target rows: `{"common_trigger_run": 1, "common_trigger_quality_item": 9, "common_trigger_state": 3920, "common_trigger_match": 119, "common_event_outbox": 3920, "common_event_inbox": 2155, "common_event_consumer_checkpoint": 2155}`
- outbox status: `{"pending": 3920, "delivering": 0, "delivered": 0}`
- downstream refs: `{"common_action_run": 0, "common_action_event": 0, "stock_action_fact": 0, "index_action_fact": 0, "board_action_fact": 0, "user_projection_run": 0, "user_signal_projection": 0, "user_signal_card": 0, "user_notification_queue": 0, "user_sim_order": 0, "user_sim_position": 0, "user_sim_trade": 0, "common_position_state": 0, "common_position_event": 0, "non_scoped_inbox_refs": 0, "non_scoped_checkpoint_refs": 0}`
- N3 MarketSnapshotUpdated: `{"MarketSnapshotUpdated_pending": 2155, "MarketSnapshotUpdated_delivering": 0, "MarketSnapshotUpdated_delivered": 0}`

## Rollback Guard Proof
- hard_fail_before_first_delete_or_update: `True`
- delete_targets_exact: `True`
- guards_delivered_delivering: `True`
- guards_event_ledger_if_exists: `True`
- guards_delivery_attempts_if_exists: `True`
- guards_n5_action_refs: `True`
- guards_n5_event_refs: `True`
- guards_n6_user_refs: `True`
- guards_sim_order_trade_position_pnl_refs: `True`
- guards_non_scoped_consumer_refs: `True`
- blocks_non_scoped_refs_same_table: `True`
- no CASCADE/DROP/TRUNCATE: `True / True / True`

## Forbidden Scope Proof
- rollback_executed: `false`
- business_db_written: `false`
- N5/N6 entered: `false / false`
- N3 outbox consumed or updated: `false`
- worker_started: `false`
- delivery/push/voice/mobile: `false`
- sim/position/pnl/real trade: `false`
- proposal/order/trade: `false`
- old_system_touched: `false`

## Decision
Allowed to re-enter `N4_PROJECTION_MATCHER_20260608_V13_INDEX_ALL_UNTIL_0952_V4_REPAIR_RETRY_POST_REVIEW_GATE`: `True`.
