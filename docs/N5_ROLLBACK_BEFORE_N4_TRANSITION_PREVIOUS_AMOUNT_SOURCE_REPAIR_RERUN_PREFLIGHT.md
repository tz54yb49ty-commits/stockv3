# N5 Rollback Before N4 Transition Previous Amount Source Repair Rerun Preflight

Result: **PASS**

## Scope

- layer_role: `N5_action`
- trade_date: `20260617`
- stale_action_run_id: `action_consumer_execute_20260617_until_1352_after_n4_formal_transition_gate_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_formal_transition_gate_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- stale_source_trigger_run_id: `trigger_action_confirmation_metric_execute_20260617_until_1352_formal_transition_gate_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- rollback_sql_path: `sql/N5_action_rerun_after_n4_formal_transition_gate_repair_rollback.sql`
- rollback SQL executed in this preflight: `false`

## Required Proofs

1. Stale action run exists: `1`; source trigger run distribution is only `trigger_action_confirmation_metric_execute_20260617_until_1352_formal_transition_gate_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1=302`.
2. Source event type distribution is only `TriggerMatched=302`.
3. Current N5 row counts match stale post-review: `common_action_run=1`, `stock_action_fact=240`, `index_action_fact=16`, `board_action_fact=46`, `common_action_event=302`, `N5 outbox=302`, `N4 source inbox refs=302`, `checkpoint scoped refs=301`.
4. N5 outbox delivered/delivering: `0`; pending distribution is `ActionBlocked=290`, `ActionExecuted=12`.
5. N6/user/voice/mobile/sim/position/order/real trade downstream refs: `0`; N5 outbox downstream inbox/checkpoint refs are also `0`.
6. Rollback SQL static scope deletes only scoped N5 action facts/events/outbox/ledger, this consumer's N4 inbox rows, and scoped checkpoints. It does not update N4 outbox status and has no N1/N2/N3 DML.
7. N4 transition previous amount source repair is recorded as reason/proof only. The action confirmation metric path reads previous amount from N2 baseline allowed fields and records `trigger_previous_amount_baseline/current_*_seed` as forbidden/ignored fields; this preflight did not rerun N4.

## N4 Previous Amount Source Code Proof

- `src/ashare_v3/trigger/action_confirmation_metric_matcher.py:133` defines allowed previous amount fields from N2 baseline.
- `src/ashare_v3/trigger/action_confirmation_metric_matcher.py:146` defines forbidden fields: `trigger_previous_amount_baseline`, `current_amount_seed`, `current_avg_amount_seed`, `current_amount_total_seed`.
- `src/ashare_v3/trigger/action_confirmation_metric_matcher.py:1136` reads previous transition amount only through `formal_transition_previous_amount_value` and records forbidden fields as ignored.
- `src/ashare_v3/trigger/action_confirmation_metric_matcher.py:1180` uses the N3 current formal metric amount and the N2 previous amount reader for the transition gate.

## Forbidden Scope Proof

- N4 rollback/rerun: `not_entered`
- N6: `not_entered`
- N5 outbox consumption: `not_consumed`
- N4 outbox status update: `not_updated`
- scheduler/worker: `not_started`
- voice/mobile/sim/position/order/real trade: `not_touched`
- old system: `not_read_or_modified`

## Allowed Execute Prompt

```text
layer_role=N5_action.
Enter N5_ROLLBACK_BEFORE_N4_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_RERUN_EXECUTE.

Use:
- rollback_sql_path=sql/N5_action_rerun_after_n4_formal_transition_gate_repair_rollback.sql
- preflight_artifact=docs/N5_ROLLBACK_BEFORE_N4_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_RERUN_PREFLIGHT.json
- planned_post_review_artifact=docs/N5_ROLLBACK_BEFORE_N4_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_RERUN_POST_REVIEW.json
- action_run_id=action_consumer_execute_20260617_until_1352_after_n4_formal_transition_gate_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_formal_transition_gate_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- source_trigger_run_id=trigger_action_confirmation_metric_execute_20260617_until_1352_formal_transition_gate_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- consumer_name=n5_action_consumer_v1

Execute this rollback SQL only.

Boundaries:
- Do not enter N4 rollback/rerun.
- Do not enter N6.
- Do not update N4 outbox status.
- Do not consume N5 outbox.
- Do not start scheduler/worker.
- Do not touch voice/mobile/sim/position/order/real trade.
- Do not read or modify old system.
```
