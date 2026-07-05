# N5 Rollback 20260617 Stale Transition Previous Amount Source Repair Before N4 Cleanup

Result: `BLOCKED`

## Scope

- `stale_action_run_id`: `action_consumer_execute_20260617_until_1352_after_n4_transition_previous_amount_source_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- `stale_source_trigger_run_id`: `trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- `consumer_name`: `n5_action_consumer_v1`
- rollback SQL: `sql/N5_action_rerun_after_n4_transition_previous_amount_source_repair_rollback.sql`

## Preflight Proof

The stale N5 run exists and exactly matches the requested source trigger run:

- `common_action_run`: 1
- wrong source rows: 0
- status: `passed`
- stock/index/board action facts: 418 / 17 / 56
- `common_action_event`: 491
- N5 outbox: 491 pending
- N4 consumer inbox rows: 491

N5 outbox safety passed:

- delivered/delivering: 0
- downstream inbox refs to N5 outbox: 0
- downstream checkpoint refs to N5 outbox: 0

Rollback SQL scope passed static checks:

- contains the requested stale action run id
- contains the requested stale source trigger run id
- contains `n5_action_consumer_v1`
- has `BEGIN` / `COMMIT`
- does not delete `common_trigger*`
- does not update N4 `common_event_outbox`
- has no DDL or privilege statements

## Blocker

N6/user downstream refs are not zero:

- `user_projection_run.source_action_run_id`: 1
- `user_signal_card.source_action_run_id`: 22
- `user_signal_projection.source_action_run_id`: 22
- `user_signal_projection.source_payload_json`: 22

Total downstream refs: 67.

Because downstream refs exist, this gate did not execute rollback SQL.

## Forbidden Scope Proof

No N6 was entered. No N5 outbox was consumed. No N4 outbox was updated. No inbox/checkpoint write was performed. No worker or scheduler was started. No voice/mobile/sim/position/order/real trade or old-system scope was touched.

## Handoff

`blocked_by_layer=N6_user`

`source_layer=N5_action`

N4 cleanup is not allowed yet. First clear the scoped N6/user projections for this `source_action_run_id`, then retry this N5 rollback gate.
