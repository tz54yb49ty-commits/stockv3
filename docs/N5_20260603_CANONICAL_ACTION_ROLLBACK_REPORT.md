# N5 20260603 Canonical Action Rollback Report

## Summary

- result: ROLLBACK_PASS
- layer_role: N5_action
- generated_at: 2026-06-03T13:00:58+08:00
- action_run_id: action_consumer_canonical_20260603_trigger_execute_20260603_condition_layer_20260602_source_20260602_v1
- source_trigger_run_id: trigger_execute_20260603_condition_layer_20260602_source_20260602_v1
- consumer_name: n5_action_consumer_v1
- rollback_sql_path: sql/N5_20260603_canonical_action_execute_rollback.sql

## Pre-Execute Guard

- N5 outbox delivered/delivering: 0
- downstream N5 inbox refs: 0
- non-scoped consumer inbox/checkpoint refs: 0/0
- N6/user/position refs: 0
- hard-fail before first DELETE: true

## Rollback Cleanup

- common_event_consumer_checkpoint deleted: 2474
- common_event_inbox deleted: 20334
- common_event_outbox deleted: 4945
- common_action_event deleted: 4945
- board_action_fact deleted: 856
- index_action_fact deleted: 166
- stock_action_fact deleted: 3923
- common_action_quality_item deleted: 5222
- common_action_run deleted: 1

## Post-Review Scoped Rows

- common_action_run: 0
- common_action_quality_item: 0
- stock/index/board_action_fact: 0/0/0
- common_action_event: 0
- N5 common_event_outbox: 0
- N5 consumer inbox: 0
- N5 consumer scoped checkpoint: 0

## N4 Preservation Proof

- common_trigger_run/common_trigger_state/common_trigger_match/common_event_outbox: 1/10167/10167/20334
- TriggerMatched pending: 4945
- TriggerPendingMarketData pending: 5222
- TriggerStateChanged pending: 10167
- N4 outbox delivered/delivering: 0/0

## Boundary

- N4 rollback executed: false
- N4 matcher fixed: false
- N4/N5 outbox consumed: false/false
- N6 executed: false
- worker started: false
- delivery / notification / push / voice / mobile / sim / position / real trade: false
- old system touched: false

## Next Gate

- allow_runtime_control_post_rollback_review: true
