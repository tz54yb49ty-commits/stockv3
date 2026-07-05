# N5 20260603 Failed-Run Rollback Report

## Summary

- result: ROLLBACK_PASS
- layer_role: N5_action
- generated_at: 2026-06-03T16:00:11+08:00
- target_db: ashare_v3 / ashare_v3_user / 127.0.0.1:5432
- action_run_id: action_consumer_canonical_20260603_trigger_execute_20260603_condition_layer_20260602_source_20260602_v1
- source_trigger_run_id: trigger_execute_20260603_condition_layer_20260602_source_20260602_v1
- consumer_name: n5_action_consumer_v1
- rollback_sql_path: sql/N5_20260603_canonical_action_execute_rollback.sql

## Pre-Rollback Scope

- common_action_run.status: failed
- common_action_run P0/P1/P2: 1/0/0
- N5 outbox pending/delivered/delivering: 1252/0/0
- downstream N5 inbox refs: 0
- non-scoped consumer inbox/checkpoint refs: 0/0
- N6/user/position refs: 0

## Deleted Rows

- common_event_consumer_checkpoint: 2474
- common_event_inbox: 20334
- common_event_outbox: 1252
- common_action_event: 1252
- board_action_fact: 170
- index_action_fact: 26
- stock_action_fact: 1056
- common_action_quality_item: 8915
- common_action_run: 1

## Cleanup Summary

- common_action_run: 0
- common_action_quality_item: 0
- stock/index/board_action_fact: 0/0/0
- common_action_event: 0
- N5 common_event_outbox: 0
- N5 consumer inbox: 0
- N5 consumer scoped checkpoint: 0

## N4 Preservation Proof

- common_trigger_run/state/match/outbox: 1/10167/10167/20334
- TriggerMatched pending: 1252
- TriggerPendingMarketData pending: 8915
- TriggerStateChanged pending: 10167
- N4 outbox pending/delivered/delivering: 20334/0/0

## Downstream Refs

- user_projection_run: 0
- user_signal_projection: 0
- user_signal_card: 0
- user_notification_queue: 0
- common_position_state/event: 0/0

## Boundary

- N5 code fixed: false
- N5 retry executed: false
- N5 outbox consumed: false
- N4 rollback executed: false
- N4 outbox status updated: false
- N6 entered: false
- worker started: false
- delivery / notification / push / voice / mobile / sim / position / real trade: false

## Next Gate

- allow_runtime_control_post_rollback_review: true
