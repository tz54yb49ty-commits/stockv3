# N5 Old-v1 Y Trigger Residue Rollback Supersession Preflight

- Result: PASS
- old_action_run_id: `action_consumer_execute_20260617_until_1352_after_n4_hint_full_scope_pass__trigger_action_confirmation_metric_execute_20260617_until_1352__condition_layer_20260616_source_20260616_for_20260617_v1`
- old_source_trigger_run_id: `trigger_action_confirmation_metric_execute_20260617_until_1352__condition_layer_20260616_source_20260616_for_20260617_v1`
- suspect_trigger_match_id: `333223`
- suspect_action_event_row_id: `194331`
- candidate rollback SQL: `sql/V3_20260617_n5_action_confirmation_after_n4_hint_full_scope_pass_rollback.sql` -> `UNSAFE_SUPERSEDED`
- superseding rollback SQL: `sql/N5_old_v1_y_trigger_residue_checkpoint_scoped_superseding_rollback.sql`

## Key Proof
- Trigger match 333223 belongs to old source trigger run: `True`
- Trigger match 333223 binds old condition run: `True`
- Action event 194331 exists as ActionExecuted for source_trigger_match_id=333223: `True`
- Suspect N5 outbox: `ActionExecuted.pending`, outbox_id=`1508912`.
- N5 downstream inbox/checkpoint/delivery-attempt refs from old N5 outbox: all `0`.
- Forbidden N6/user/voice/mobile/sim/position/order/real-trade tables scanned: `35`, nonzero refs: `0`.
- New y_amount chain isolation: no `common_trigger_match` for `stock:SZ:300687 BUY:Y,M,D`; existing N4 outbox row is `TriggerPendingMarketData.pending` with `triggered_periods=[]`.

## Checkpoint Supersession
- old_partitions: `1141`
- new_partitions: `757`
- overlapping_partitions: `682`
- candidate_checkpoint_delete_count_by_partition_only: `994`
- checkpoint_rows_with_old_ref: `312`
- checkpoint_rows_with_new_ref: `682`
- checkpoint_rows_with_old_ref_and_no_new_ref: `312`
- checkpoint_rows_with_new_ref_and_no_old_ref: `682`
- checkpoint_rows_with_both_refs: `0`

The original candidate rollback is not safe because it deletes checkpoints by partition overlap. The superseding SQL deletes only old-ref checkpoints and hard-fails if any checkpoint row contains both old-v1 and protected y_amount refs.

## Boundary
- No DELETE executed.
- No N6 entered.
- No N5 outbox consumed.
- No N4 outbox status updated.
- No scheduler/worker started.
- No voice/mobile/sim/position/order/real trade/old system touched.

## Allowed Next Prompt
```text
layer_role=N5_action.
Enter N5_OLD_V1_Y_TRIGGER_RESIDUE_ROLLBACK_SUPERSESSION_EXECUTE.

Use:
- rollback_sql_path=sql/N5_old_v1_y_trigger_residue_checkpoint_scoped_superseding_rollback.sql
- preflight_artifact=docs/N5_OLD_V1_Y_TRIGGER_RESIDUE_ROLLBACK_SUPERSESSION_PREFLIGHT.json
- action_run_id=action_consumer_execute_20260617_until_1352_after_n4_hint_full_scope_pass__trigger_action_confirmation_metric_execute_20260617_until_1352__condition_layer_20260616_source_20260616_for_20260617_v1
- source_trigger_run_id=trigger_action_confirmation_metric_execute_20260617_until_1352__condition_layer_20260616_source_20260616_for_20260617_v1
- consumer_name=n5_action_consumer_v1

Execute this rollback SQL only. Do not use the superseded candidate rollback SQL. Do not enter N4/N6. Do not update N4 outbox status. Do not consume N5 outbox. Do not start scheduler/worker. Do not rollback repaired/y_amount semantic-repair lineage. Do not touch voice/mobile/sim/position/order/real trade/old system.
```
