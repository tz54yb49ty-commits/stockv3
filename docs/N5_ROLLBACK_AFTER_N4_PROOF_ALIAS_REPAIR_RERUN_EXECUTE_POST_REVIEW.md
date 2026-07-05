# N5 Rollback After N4 Proof Alias Repair Rerun Execute Post-Review

Result: `ROLLBACK_EXECUTE_PASS`

## Scope

- `action_run_id`: `action_consumer_execute_20260617_after_n4_proof_alias_repair_rerun__trigger_action_confirmation_metric_execute_20260617_full_day_proof_alias_repair__condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- `source_trigger_run_id`: `trigger_action_confirmation_metric_execute_20260617_full_day_proof_alias_repair__condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- `consumer_name`: `n5_action_consumer_v1`
- rollback SQL: `sql/N5_20260617_after_n4_proof_alias_repair_rerun_rollback.sql`

## Execution Proof

The scoped rollback SQL was executed and committed. `psql` was unavailable in the local shell, so the same SQL file was executed through `psycopg` after psql variable substitution; the SQL file's `BEGIN`, `COMMIT`, and hard-fail guards were preserved.

Hard-fail guards did not trip.

## Scoped N5 Remaining Counts

All scoped N5 rows are now zero:

- `common_action_run`: 0
- `stock_action_fact`: 0
- `index_action_fact`: 0
- `board_action_fact`: 0
- `common_action_event`: 0
- `common_action_tracking_state`: 0
- `common_event_outbox` for this N5 run: 0
- `common_event_inbox` for this N5 consumer and N4 source run: 0
- scoped checkpoint payload refs: 0

## N4 Preservation Proof

N4 source outbox remains pending-only:

- `TriggerMatched`: pending 550
- `TriggerPendingMarketData`: pending 3776
- `TriggerStateChanged`: pending 4326
- delivered/delivering: 0

N4 facts remain present:

- `common_trigger_match`: 550
- `common_trigger_state`: 4326
- `common_trigger_run.status`: `passed`

The rollback did not update N4 outbox status and did not touch N4 facts.

## Downstream Safety

- N5 outbox rows for this action run: 0
- downstream inbox refs: 0
- downstream checkpoint refs: 0
- N6/user/voice/mobile/sim/position/order/real-trade refs: 0

## Forbidden Scope Proof

No N4 rerun was entered. No N6 was entered. No N5 outbox was consumed. No N4 outbox status was updated. No worker or scheduler was started. No voice/mobile/sim/position/order/real trade or old-system scope was touched.

## Next Gate

No N6 prompt is emitted from this gate. If the pipeline must continue, switch explicitly to the next authorized N4/N5 gate and use this artifact as stale N5 rollback proof.
