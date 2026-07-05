# N3 20260611 B1 MarketSnapshotUpdated Standard Outbox Rollback SQL Hard-Fail Repair

## Result

REPAIR_PASS

## Scope

Layer role: N3_market_data.

This gate only repairs rollback SQL and static tests. It does not execute rollback SQL, does not write database rows, does not consume or update outbox/inbox/checkpoint, does not start workers, and does not enter N4/N5/N6.

## Root Cause

`sql/N3_20260611_B1_market_snapshot_updated_standard_outbox_rollback.sql` retained scoped guards, but the default manual hard-fail had been removed by the previous approved rollback execution gate. After the later failed partial retry, runtime_control requires the rollback artifact to default-block again before any DELETE/UPDATE.

## Repair

Restored an executable default hard-fail inside the guard `DO $$` block and before the first DELETE:

```sql
RAISE EXCEPTION
  'rollback blocked by default for %. Remove the default hard-fail only after runtime_control final gate review authorizes this exact scoped rollback.',
  v_snapshot_run_id;
```

The existing scoped guard checks were preserved:

- `common_event_outbox` delivered/delivering guard
- `common_event_inbox` refs guard
- `common_event_consumer_checkpoint` refs guard
- N3-B/C/B2 refs guard
- N4/N5/N6/user/sim/virtual refs guard
- `downstream_layers_touched` / `worker_started` guard

## Scope Proof

Delete scope remains limited to the target snapshot run:

- `common_event_outbox` scoped to pending/failed/dead-letter `MarketSnapshotUpdated`
- `stock_realtime_daily_snapshot` by `run_id`
- `index_realtime_daily_snapshot` by `run_id`
- `board_realtime_daily_snapshot` by `run_id`
- `common_market_data_quality_item` by `run_id`
- `common_market_data_run` by `run_id`

The SQL contains no `DROP`, `TRUNCATE`, or `CASCADE`.

## Validation

Fresh validation passed:

- `PYTHONPATH=src:scripts python3 -m unittest tests.test_n3_b1_20260611_standard_outbox_rollback_hard_fail`
- rollback static check: default hard-fail before first DELETE/UPDATE
- rollback static check: scoped delete targets present
- rollback static check: no forbidden DDL

## Decision

Allow returning to runtime_control for:

```text
N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_PARTIAL_WRITE_ROLLBACK_FINAL_GATE_REVIEW_AFTER_SOURCE_TIME_GUARD
```
