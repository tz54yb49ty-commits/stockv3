# N4 Projection Matcher 20260608 v13 index-all Rollback SQL Regeneration Report

- result: `REGENERATION_PASS`
- layer_role: `runtime_control`
- generated_at: `2026-06-08T14:06:24+08:00`
- target_run_id: `trigger_projection_matcher_execute_20260608_v13_index_all_until_0952`
- rollback_sql_path: `sql/N4_projection_matcher_20260608_v13_index_all_until_0952_v4_breach_repair_rollback.sql`

## Live Readiness Proof

- N6 rollback post-review: `POST_REVIEW_PASS`
- N5 rollback post-review: `POST_REVIEW_PASS`
- N5 scoped rows are zero: `{'common_action_run': 0, 'common_action_quality_item': 0, 'stock_action_fact': 0, 'index_action_fact': 0, 'board_action_fact': 0, 'common_action_event': 0, 'n5_common_event_outbox': 0, 'n5_consumer_inbox_for_n4': 0, 'n5_checkpoint_refs_for_n4': 0}`
- N6 scoped rows are zero: `{'user_projection_run': 0, 'user_signal_projection': 0, 'user_signal_card': 0, 'user_notification_queue': 0}`
- N4 run remains: `{'run_id': 'trigger_projection_matcher_execute_20260608_v13_index_all_until_0952', 'status': 'passed', 'p0_count': 0, 'p1_count': 0, 'p2_count': 0, 'trigger_state_row_count': 3920, 'trigger_match_row_count': 3920, 'trigger_event_outbox_count': 3920}`
- N4 outbox remains: `[{'event_type': 'TriggerMatched', 'status': 'pending', 'count': 320}, {'event_type': 'TriggerPendingMarketData', 'status': 'pending', 'count': 3600}]`
- N4 trigger_match/state/quality: `3920/3920/10`
- N4 consumer inbox/checkpoint for target execute: `2155/2155`
- N4 outbox delivered/delivering: `0`
- downstream N5/N6/user/sim/position refs: zero outside target N4 own event rows.

## Rollback Guard Proof

- hard-fail before first DELETE/UPDATE: `True`
- first DML keyword: `DELETE`
- delete targets: `['COMMON_EVENT_OUTBOX', 'COMMON_TRIGGER_MATCH', 'COMMON_TRIGGER_STATE', 'COMMON_TRIGGER_QUALITY_ITEM', 'COMMON_EVENT_INBOX', 'COMMON_EVENT_CONSUMER_CHECKPOINT', 'COMMON_TRIGGER_RUN']`
- forbidden tokens absent: `True/True/True`
- guard strings: `{'delivered_delivering': True, 'event_ledger_guard': True, 'downstream_inbox_guard': True, 'delivery_attempt_guard': True, 'downstream_table_guard': True, 'non_target_checkpoint_guard': True}`

## Planned Delete Scope

- common_event_outbox for target N4 run
- common_trigger_match for target N4 run
- common_trigger_state for target N4 run
- common_trigger_quality_item for target N4 run
- common_event_inbox for n4_projection_matcher_consumer_v1 target execute run
- common_event_consumer_checkpoint for n4_projection_matcher_consumer_v1 target execute run
- common_trigger_run target row

## Preservation Scope

- N3 facts and N3 outbox
- N2/N1 facts
- N5 rows already rolled back remain zero
- N6 rows already rolled back remain zero

## Forbidden Scope Proof

- `rollback_executed` = `False`
- `business_db_write_performed` = `False`
- `n4_execute_performed` = `False`
- `n5_n6_execute_performed` = `False`
- `outbox_inbox_checkpoint_consumed_or_updated` = `False`
- `worker_started` = `False`
- `delivery_push_voice_mobile` = `False`
- `sim_position_pnl_real_trade` = `False`
- `proposal_order_trade` = `False`
- `old_system_touched` = `False`

## Validation Summary

- JSON parse: `PASS`
- rollback SQL static check: `PASS`
- live DB readiness proof: `PASS`
- git diff check: `PASS`

Recommended next gate: `N4_PROJECTION_MATCHER_20260608_V13_INDEX_ALL_UNTIL_0952_ROLLBACK_FINAL_GATE_REVIEW`
