# V3 20260612 Stale N5 Action Mark Rollback Scope Repair Include Realtime Engine Consumer Report

Result: `REPAIR_PASS`

Generated at: `2026-06-13 10:13:39 +0800`

This gate did not execute rollback, did not write database rows, did not consume or update outbox/inbox/checkpoint, and did not enter N4/N5/N6/voice/mobile/sim/position/trade.

## Scope

- Stale N5 action run: `v3_n5_action_consumer_20260612_from_n4_action_confirmation_metric_after_n3_writer_v1`
- Preserved N4 source run: `v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1`
- Rollback SQL: `sql/V3_20260612_n5_action_consumer_after_n4_action_confirmation_metric_rollback.sql`
- N4 run preservation: required
- N3 projection run preservation: required

## Root Cause

The previous rollback execute partially cleaned the original scoped consumer `n5_action_consumer_v1`, but post-review showed a production wrapper consumer had written refs for the same stale N5 lineage:

- consumer: `v3_realtime_engine_n5_consumer_20260612`
- inbox refs: `49`
- checkpoint refs expected by this repair route: `43`

Because these refs belong to the reviewed stale N5 lineage, they should be included in the stale rollback scope. They are not N4 rollback refs and do not justify modifying the preserved N4 run.

## SQL Repair

Changed file:

- `sql/V3_20260612_n5_action_consumer_after_n4_action_confirmation_metric_rollback.sql`

The rollback SQL now defines the reviewed stale consumers as:

```text
n5_action_consumer_v1
v3_realtime_engine_n5_consumer_20260612
```

The hard-fail inbox guard now blocks only consumers outside that reviewed stale set:

```text
NOT (consumer_name = ANY(v_stale_consumer_names))
```

The checkpoint and inbox delete scope now includes only those reviewed stale consumers for the scoped N4 source run:

```text
consumer_name = ANY(ARRAY[:'consumer_name', :'wrapper_consumer_name'])
source_layer = 'N4_trigger'
source_run_id = :'source_trigger_run_id'
```

## Preserved Guards

The SQL still hard-fails before the first `DELETE` and continues to block:

- scoped N5 outbox `delivered` / `delivering`
- downstream inbox refs to the scoped N5 outbox/run
- downstream checkpoint refs to the scoped N5 outbox/run
- N6/user/sim/voice/mobile/position refs
- non-stale consumer inbox refs for the preserved N4 source run

Non-stale consumer checkpoints on preserved N4 partitions remain untouched and do not block rollback, matching the previous checkpoint guard repair.

## Delete Scope

Allowed delete scope remains limited to:

- stale N5 action run rows
- stale N5 action facts/events/outbox/ledger/delivery attempts
- reviewed stale consumers' inbox/checkpoint rows for the scoped N4 source run

Forbidden scope remains:

- no N4 trigger facts
- no N4 outbox status update
- no N3 projection or metric facts
- no N2/N1 facts
- no N6/user/voice/mobile/sim/position/trade facts
- no old system writes

## Tests

Updated:

- `tests/test_v3_20260612_stale_n5_action_mark_rollback_guard.py`

Coverage:

- hard-fail guard still precedes destructive statements
- reviewed stale consumer set includes `n5_action_consumer_v1`
- reviewed stale consumer set includes `v3_realtime_engine_n5_consumer_20260612`
- checkpoint delete scope uses reviewed stale consumers and scoped N4 source partitions
- N5 downstream / user-layer guards remain present
- rollback does not delete N4/N3/downstream business facts

## Validation

Completed:

```text
PYTHONPATH=src python3 -m unittest tests/test_v3_20260612_stale_n5_action_mark_rollback_guard.py
```

Result: `PASS`

Additional validation is recorded in the companion JSON artifact.

## Boundary Proof

- rollback executed: `false`
- database written: `false`
- outbox consumed or updated: `false`
- inbox/checkpoint consumed or updated: `false`
- N4 modified: `false`
- N3 modified: `false`
- N5 execute run started: `false`
- N6 entered: `false`
- worker started by this gate: `false`
- voice/mobile/sim/position/trade touched: `false`

## Next Gate

Allowed next gate:

`V3_20260612_STALE_N5_ACTION_MARK_RUN_ROLLBACK_FINAL_GATE_REVIEW_INCLUDE_REALTIME_ENGINE_CONSUMER`

That gate should perform a read-only runtime_control final gate review of the repaired rollback SQL before any execute confirmation.
