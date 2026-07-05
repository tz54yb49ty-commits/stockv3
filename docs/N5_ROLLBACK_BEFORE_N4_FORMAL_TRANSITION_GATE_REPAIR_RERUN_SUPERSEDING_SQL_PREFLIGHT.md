# N5 Rollback Before N4 Formal Transition Gate Repair Rerun Superseding SQL Preflight

- Result: PASS
- superseding rollback SQL: `sql/N5_action_after_n4_y_amount_semantic_repair_rerun_checkpoint_scoped_superseding_rollback.sql`
- superseded rollback SQL: `sql/N5_action_after_n4_y_amount_semantic_repair_rerun_rollback.sql`
- stale_action_run_id: `action_consumer_execute_20260617_until_1352_after_n4_y_amount_semantic_repair_rerun__trigger_action_confirmation_metric_execute_20260617_until_1352_y_amount_semantic_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- stale_source_trigger_run_id: `trigger_action_confirmation_metric_execute_20260617_until_1352_y_amount_semantic_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`

## Required Proof
- blocked execute no DELETE/no COMMIT: `True`
- stale N5 rows complete: `True`
- old-v1 remains clean: `True`
- N5 outbox delivered/delivering=0: `True`
- N6/user/sim/position/order/real trade downstream refs=0: `True`
- blocking 5331 rows are partition overlap only: `True`
- new SQL checkpoint scope safe: `True`

## Exact Delete Candidate Counts
- common_action_run: `1`
- stock_action_fact: `662`
- index_action_fact: `39`
- board_action_fact: `63`
- common_action_event: `764`
- common_event_outbox_n5: `764`
- common_event_ledger_n5: `0`
- common_event_inbox_n5_consumer: `764`
- common_event_checkpoint_exact_delete_candidates: `757`
- common_action_quality_item: `0`

## Checkpoint Classification
- non_scoped_partition_overlap_total: `5331`
- payload_refs_stale_action_or_trigger: `0`
- event_or_outbox_refs_stale_n4_events: `0`
- payload_refs_old_v1_action_or_trigger: `0`
- payload_refs_other_only: `5331`

## Boundary
- No rollback SQL executed.
- No N4 rollback/rerun entered.
- No N6 entered.
- No N5 outbox consumed.
- No N4 outbox status updated.
- No scheduler/worker started.
- No voice/mobile/sim/position/order/real trade/old system touched.

## Allowed Next Prompt
```text
layer_role=N5_action.
Enter N5_ROLLBACK_BEFORE_N4_FORMAL_TRANSITION_GATE_REPAIR_RERUN_SUPERSEDING_SQL_EXECUTE.

Use:
- rollback_sql_path=sql/N5_action_after_n4_y_amount_semantic_repair_rerun_checkpoint_scoped_superseding_rollback.sql
- preflight_artifact=docs/N5_ROLLBACK_BEFORE_N4_FORMAL_TRANSITION_GATE_REPAIR_RERUN_SUPERSEDING_SQL_PREFLIGHT.json
- action_run_id=action_consumer_execute_20260617_until_1352_after_n4_y_amount_semantic_repair_rerun__trigger_action_confirmation_metric_execute_20260617_until_1352_y_amount_semantic_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- source_trigger_run_id=trigger_action_confirmation_metric_execute_20260617_until_1352_y_amount_semantic_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- consumer_name=n5_action_consumer_v1

Execute this rollback SQL only. Do not use the superseded rollback SQL. Do not enter N4 rollback/rerun. Do not enter N6. Do not update N4 outbox status. Do not consume N5 outbox. Do not start scheduler/worker. Do not touch voice/mobile/sim/position/order/real trade/old system.
```
