# V3 20260612 Stale N5 Action Mark Rollback Checkpoint Guard Repair Report

Result: `REPAIR_PASS`

Generated at: `2026-06-13 09:46:17 +0800`

This gate did not execute rollback, did not write database rows, did not consume or update outbox/inbox/checkpoint, and did not enter N4/N5/N6/voice/mobile/sim/trade.

## Scope

- Layer role: `N5_action`
- Stale N5 action run: `v3_n5_action_consumer_20260612_from_n4_action_confirmation_metric_after_n3_writer_v1`
- Source N4 trigger run: `v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1`
- Scoped N5 consumer: `n5_action_consumer_v1`
- Rollback SQL: `sql/V3_20260612_n5_action_consumer_after_n4_action_confirmation_metric_rollback.sql`

## Root Cause

The previous rollback SQL hard-failed when non-scoped consumer checkpoint rows existed for partitions of the preserved N4 source run.

Final gate live proof showed:

- N5 outbox delivered/delivering: `0`
- N5 downstream inbox/checkpoint refs: `0/0`
- N6/user/sim/voice/mobile/position refs: `0`
- non-scoped consumer checkpoint refs for the preserved N4 source: `6279`

Because this rollback route preserves the N4 run and deletes only the stale N5 run plus the scoped `n5_action_consumer_v1` inbox/checkpoint rows for the scoped N4 source, those non-scoped N4 checkpoint rows are not downstream refs to the stale N5 action run. They must not be deleted, and they must not block the scoped N5 rollback.

## SQL Repair

Changed file:

- `sql/V3_20260612_n5_action_consumer_after_n4_action_confirmation_metric_rollback.sql`

The repair removed the hard-fail guard that counted:

```sql
common_event_consumer_checkpoint
WHERE source_layer = 'N4_trigger'
  AND consumer_name <> v_consumer_name
  AND partition_key IN (...)
```

The SQL now documents that non-scoped consumer checkpoints on the preserved N4 source run remain untouched and are not rollback blockers.

## Preserved Guards

The rollback SQL still hard-fails before the first `DELETE` when any of the following are present:

- scoped N5 outbox rows with `status IN ('delivering', 'delivered')`
- downstream inbox refs to the scoped N5 outbox/run
- downstream checkpoint refs to the scoped N5 outbox/run
- downstream user / voice / mobile / sim / position refs containing the action run or source trigger run

## Delete Scope

The delete scope remains unchanged:

- stale N5 action rows for `run_id = v3_n5_action_consumer_20260612_from_n4_action_confirmation_metric_after_n3_writer_v1`
- N5 outbox / ledger rows for `source_layer='N5_action'` and the stale action run
- `n5_action_consumer_v1` inbox rows for the scoped N4 source run
- `n5_action_consumer_v1` checkpoint rows only for partitions derived from those scoped inbox rows

The rollback SQL still does not delete:

- N4 trigger facts
- N4 outbox rows or status
- N3 metric / market-data facts
- N2/N1 facts
- N6/user/voice/mobile/sim/position/trade facts
- non-scoped consumer checkpoint rows for the preserved N4 source

## Tests

Added:

- `tests/test_v3_20260612_stale_n5_action_mark_rollback_guard.py`

The test covers:

- hard-fail guard exists before the first destructive statement
- preserved N4 non-scoped checkpoint refs do not block rollback
- checkpoint deletion remains scoped to `n5_action_consumer_v1` and the scoped N4 source partitions
- N5 downstream and user-layer guards remain present
- rollback does not delete N4/N3/downstream business facts

## Validation

Completed:

```text
PYTHONPATH=src python3 -m unittest tests/test_v3_20260612_stale_n5_action_mark_rollback_guard.py
```

Result: `PASS`

Additional validation is recorded in the companion JSON artifact.

## Forbidden Scope Proof

- rollback executed: `false`
- database written: `false`
- outbox consumed or updated: `false`
- inbox/checkpoint consumed or updated: `false`
- N4 modified: `false`
- N5 execute run started: `false`
- N6 entered: `false`
- worker started: `false`
- voice/mobile/sim/position/real trade touched: `false`
- old system touched: `false`

## Next Gate

Allowed next gate:

`V3_20260612_STALE_N5_ACTION_MARK_RUN_ROLLBACK_FINAL_GATE_REVIEW_RETRY`

That gate should re-run runtime_control read-only final gate review against the repaired rollback SQL before any rollback execute confirmation.
