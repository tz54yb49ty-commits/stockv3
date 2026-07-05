# N5 Rollback Retry After N6 Rollback

Result: `N5_ROLLBACK_PASS`

## Scope

- `stale_action_run_id`: `action_consumer_execute_20260617_until_1352_after_n4_transition_previous_amount_source_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- `source_trigger_run_id`: `trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- rollback SQL: `sql/N5_action_rerun_after_n4_transition_previous_amount_source_repair_rollback.sql`
- N6 rollback post-review: `docs/N6_ROLLBACK_20260617_STALE_N5_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_BEFORE_N5_N4_CLEANUP_POST_REVIEW.json`

## Preflight

Preflight passed:

- N6 rollback post-review result: `N6_ROLLBACK_PASS`
- N6/user/voice/mobile/sim/position/order/real-trade refs: 0
- stale N5 run exists and source trigger run matches exactly
- N5 outbox delivered/delivering: 0
- N5 outbox downstream inbox/checkpoint refs: 0
- rollback SQL contains the requested stale action run id, source trigger run id, and consumer name
- rollback SQL does not delete `common_trigger*`, does not update N4 outbox, and contains no DDL or privilege statements

Delete candidates before rollback:

- `common_action_run`: 1
- stock/index/board facts: 418 / 17 / 56
- `common_action_event`: 491
- N5 outbox: 491
- N4 consumer inbox rows: 491
- scoped checkpoint refs: 0

## Execution

The scoped rollback SQL was executed and committed. The SQL file's `BEGIN`, `COMMIT`, and hard-fail guards were preserved.

## Post-Review

Scoped N5 rows after rollback:

- `common_action_run`: 0
- stock/index/board facts: 0 / 0 / 0
- `common_action_event`: 0
- N5 outbox: 0
- N4 consumer inbox rows: 0
- scoped checkpoint refs: 0

N4 source trigger output was preserved:

- `TriggerMatched`: pending 491
- `TriggerPendingMarketData`: pending 3835
- delivered/delivering: 0
- `common_trigger_match`: 491
- `common_trigger_state`: 4326

No N4 cleanup was entered. No N6 was entered. No N5 outbox was consumed. No worker or scheduler was started. No voice/mobile/sim/position/order/real trade or old-system scope was touched.

## Allowed Next Prompt

```text
layer_role=N4_trigger.
Enter N4_CLEANUP_20260617_STALE_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_AFTER_N5_ROLLBACK_PASS.

Use:
- source_trigger_run_id=trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- n5_rollback_post_review=docs/N5_ROLLBACK_20260617_STALE_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_BEFORE_N4_CLEANUP_RETRY_AFTER_N6_ROLLBACK_POST_REVIEW.json

Run N4 stale cleanup preflight first.
Do not enter N5/N6.
Do not consume outbox.
Do not start worker/scheduler.
Do not touch voice/mobile/sim/position/order/real trade/old system.
```
