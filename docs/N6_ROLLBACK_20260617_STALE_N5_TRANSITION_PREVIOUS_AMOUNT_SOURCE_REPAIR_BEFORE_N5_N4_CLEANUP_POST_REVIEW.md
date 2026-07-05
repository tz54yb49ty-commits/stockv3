# N6 Rollback 20260617 Stale N5 Transition Previous Amount Source Repair Post Review

## Result

N6_ROLLBACK_PASS

## Scope

- layer_role: N6_user
- projection_run_id: `v3_n6_user_projection_20260617_after_n5_transition_previous_amount_source_repair_pass_v1`
- stale_action_run_id: `action_consumer_execute_20260617_until_1352_after_n4_transition_previous_amount_source_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- source_trigger_run_id: `trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- rollback_sql_path: `sql/N6_user_projection_20260617_after_n5_transition_previous_amount_source_repair_pass_rollback.sql`

## Preflight Proof

- user_projection_run.source_action_run_id: 1
- user_signal_projection.source_action_run_id: 22
- user_signal_projection.source_payload_json refs: 22
- user_signal_card.source_action_run_id: 22
- user_notification_queue refs: 0
- delivered/delivering user notification refs: 0
- downstream decision/sim/position/order/virtual/delivery refs: 0

## Execution Proof

Rollback SQL executed successfully with exit code 0.

Deleted rows:

- user_notification_queue: 0
- user_signal_card: 22
- user_signal_projection: 22
- user_projection_run: 1

## Post-Check Proof

N6 refs for stale_action_run_id after rollback:

- user_projection_run: 0
- user_signal_projection: 0
- user_signal_projection.source_payload_json refs: 0
- user_signal_card: 0
- user_notification_queue: 0

N5 unchanged:

- common_action_run: 1, status=passed
- stock_action_fact: 418
- index_action_fact: 17
- board_action_fact: 56
- common_action_event: 491
- N5 outbox: ActionBlocked pending=469, ActionExecuted pending=22
- N5 delivered/delivering: 0

N4 unchanged:

- N4 outbox: TriggerMatched pending=491, TriggerPendingMarketData pending=3835
- N4 delivered/delivering: 0

## Forbidden Scope Proof

- N4/N5 facts not deleted or updated
- N4/N5 outbox status not consumed or updated
- inbox/checkpoint not consumed or updated
- worker/scheduler not started
- voice/mobile/sim/position/order/real trade not touched
- old system not read or modified

## Next Gate

Allowed next prompt only:

`N5_ROLLBACK_20260617_STALE_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_BEFORE_N4_CLEANUP_RETRY_AFTER_N6_ROLLBACK`
