# N5 20260617 Full-Day Runtime Rollback Supersession Preflight

Result: `PREFLIGHT_PASS`

## Rollback Coverage Proof

Post-review result is `EXECUTE_PASS_DOWNSTREAM_DEFERRED`.

The current rollback SQL is tracking-only:

`sql/N5_20260617_full_day_trigger_state_closed_loop_tracking_runtime_rollback.sql`

It does not cover action facts/events, N5 outbox, N4 inbox, or checkpoints.

Superseding rollback SQL:

`sql/N5_20260617_full_day_trigger_state_closed_loop_runtime_scoped_superseding_rollback.sql`

Exact delete candidates:

- `common_action_tracking_state=216`
- `stock_action_fact=1481`
- `index_action_fact=49`
- `board_action_fact=131`
- `common_action_event=1661`
- `N5 common_event_outbox=1661`
- `N4 source common_event_inbox=14707`
- `common_event_consumer_checkpoint=2051`
- `common_action_run=1`
- `common_action_quality_item=0`
- `common_event_ledger=0`
- `common_event_delivery_attempt=0`

## Downstream Safety Proof

- N5 outbox delivered/delivering: `0`
- downstream inbox refs to N5 outbox: `0`
- downstream checkpoint refs to N5 outbox: `0`
- non-scoped N4 inbox refs: `0`
- wrong-source action run refs: `0`
- N6/user/voice/mobile/sim/position/order/real trade refs: `0`

## SQL Scope Proof

The superseding SQL is scoped by:

- `action_run_id`
- `source_trigger_run_id`
- `consumer_name`

Hard-fail guards are present for:

- N5 outbox delivered/delivering rows
- downstream inbox refs to N5 outbox
- downstream checkpoint refs to N5 outbox
- non-scoped consumer refs to the N4 source run
- wrong source-trigger lineage rows
- unexpected `TriggerPendingMarketData` N4 inbox rows
- N6/user/voice/mobile/sim/position/order/real trade refs

The SQL does not use partition-key-only delete, does not update N4 outbox status, and does not delete downstream user/voice/mobile/sim/position/order/real trade rows.

## Forbidden Scope Proof

- rollback SQL executed: `false`
- N6 entered: `false`
- N5 outbox consumed: `false`
- N4 outbox status updated: `false`
- worker/scheduler started: `false`
- voice/mobile/sim/position/order/real trade touched: `false`
- old system read/modified: `false`

## Allowed Next Prompt

```text
layer_role=N5_action.
Enter N5_20260617_FULL_DAY_TRIGGER_STATE_CLOSED_LOOP_RUNTIME_ROLLBACK_SUPERSESSION_EXECUTE.

Use:
- rollback_sql_path=sql/N5_20260617_full_day_trigger_state_closed_loop_runtime_scoped_superseding_rollback.sql
- preflight_artifact=docs/N5_20260617_FULL_DAY_TRIGGER_STATE_CLOSED_LOOP_RUNTIME_ROLLBACK_SUPERSESSION_PREFLIGHT_AFTER_EXECUTE_PASS.json
- action_run_id=action_consumer_dry_run_20260617_full_day_state_closed_loop__trigger_action_confirmation_metric_execute_20260617_full_day_after_n3_full_day_b2_pass__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- source_trigger_run_id=trigger_action_confirmation_metric_execute_20260617_full_day_after_n3_full_day_b2_pass__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- consumer_name=n5_action_consumer_v1

Execute this rollback SQL only.
Do not use the tracking-only rollback SQL.
Do not enter N6.
Do not consume N5 outbox.
Do not update N4 outbox status.
Do not start worker/scheduler.
Do not touch voice/mobile/sim/position/order/real trade/old system.
```
