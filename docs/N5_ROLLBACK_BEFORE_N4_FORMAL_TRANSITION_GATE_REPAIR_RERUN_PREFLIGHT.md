# N5 Rollback Before N4 Formal Transition Gate Repair Rerun Preflight

- Result: PASS
- stale_action_run_id: `action_consumer_execute_20260617_until_1352_after_n4_y_amount_semantic_repair_rerun__trigger_action_confirmation_metric_execute_20260617_until_1352_y_amount_semantic_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- stale_source_trigger_run_id: `trigger_action_confirmation_metric_execute_20260617_until_1352_y_amount_semantic_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- rollback_sql_path: `sql/N5_action_after_n4_y_amount_semantic_repair_rerun_rollback.sql`

## Proof
- old-v1 residue post-review PASS and live scoped rows/checkpoints zero: `True`
- stale action run exists: `True`
- stale expected refs match 1/662/39/63/764/764/757/764: `True`
- consumed only TriggerMatched from stale source run: `True`
- N5 outbox delivered/delivering=0: `True`
- N6/user/sim/position/order/real trade downstream refs=0: `True`
- rollback SQL scope safe for stale run only: `True`

## Rollback SQL Scope
- candidate_checkpoint_delete_count_by_partition: `757`
- candidate_checkpoint_payload_refs_stale: `757`
- candidate_checkpoint_payload_refs_old_v1: `0`
- candidate_checkpoint_payload_refs_other: `0`

## Boundary
- No rollback executed.
- No N4 rollback/rerun entered.
- No N6 entered.
- No N5 outbox consumed.
- No N4 outbox status updated.
- No scheduler/worker started.
- No voice/mobile/sim/position/order/real trade/old system touched.

## Allowed Next Prompt
```text
layer_role=N5_action.
Enter N5_ROLLBACK_BEFORE_N4_FORMAL_TRANSITION_GATE_REPAIR_RERUN_EXECUTE.

Use:
- rollback_sql_path=sql/N5_action_after_n4_y_amount_semantic_repair_rerun_rollback.sql
- preflight_artifact=docs/N5_ROLLBACK_BEFORE_N4_FORMAL_TRANSITION_GATE_REPAIR_RERUN_PREFLIGHT.json
- planned_post_review_artifact=docs/N5_ROLLBACK_BEFORE_N4_FORMAL_TRANSITION_GATE_REPAIR_RERUN_POST_REVIEW.json
- action_run_id=action_consumer_execute_20260617_until_1352_after_n4_y_amount_semantic_repair_rerun__trigger_action_confirmation_metric_execute_20260617_until_1352_y_amount_semantic_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- source_trigger_run_id=trigger_action_confirmation_metric_execute_20260617_until_1352_y_amount_semantic_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- consumer_name=n5_action_consumer_v1

Execute this rollback SQL only. Do not enter N4 rollback/rerun. Do not enter N6. Do not update N4 outbox status. Do not consume N5 outbox. Do not start scheduler/worker. Do not touch voice/mobile/sim/position/order/real trade/old system.
```
