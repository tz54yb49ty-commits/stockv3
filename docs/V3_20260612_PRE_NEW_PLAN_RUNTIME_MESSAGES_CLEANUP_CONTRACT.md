# V3 20260612 Pre-New-Plan Runtime Messages Cleanup Contract

Result: `CONTRACT_PASS`

This gate only prepares the scoped cleanup contract. It does not execute cleanup, write the database, execute rollback, restart a scheduler, consume or update outbox/inbox/checkpoint, enter N6, or touch voice/mobile/sim/position/PnL/real trade.

## Objective

Clean only the 2026-06-12 runtime messages and derived rows created before the new realtime signal/action plan is rebuilt.

The cleanup is intentionally not a broad "delete today's data" operation. It preserves source facts and only targets pre-new-plan derived runtime rows:

- N5 action rows and N5 outbox/inbox/checkpoint
- N4 trigger rows and N4 outbox/inbox/checkpoint
- N3 standard `MarketSnapshotUpdated` outbox snapshot runs
- N3 trace-aligned B2 realtime projection rows generated from those standard outbox runs

## Required Order

Cleanup must run in reverse dependency order:

1. Guard N6/user/sim/virtual refs.
2. Delete scoped N5 action rows and N5 event ledger rows.
3. Assert N5 refs to N4 are zero.
4. Delete scoped N4 trigger rows and N4 event ledger rows.
5. Assert downstream refs to scoped N3 standard outbox are zero.
6. Delete scoped N3 derived standard outbox snapshots, trace-aligned B2 projections, quality rows, run rows, and `MarketSnapshotUpdated` outbox rows.

## Preserve Scope

The cleanup contract must not delete or rewrite:

- N1/N2 source facts or condition context
- N3 `market_data_subscription` / pull plans
- N3 previous-day preload
- N3 today `*_minute_bar_1m` source facts
- N3 fact-only B1/C1/B2 runs not listed in the target scope
- old system files or `/Users/chuanfuchen/stock_monitor_isolated`

## Target Scope

N3 standard outbox runs: 11

N3 trace-aligned B2 runs: 4

N4 production semantic replay runs: 4

N5 action bounded runs: 3

Consumers:

- N4 consumers: the 4 N4 production replay run IDs
- N5 consumers: 3 `n5_action_bounded_consumer_20260612_from_n4_until_*` consumers

Full target run IDs are recorded in:

- `docs/V3_20260612_PRE_NEW_PLAN_RUNTIME_MESSAGES_CLEANUP_CONTRACT.json`
- `sql/V3_20260612_pre_new_plan_runtime_messages_cleanup.sql`

## SQL Registry

Cleanup SQL:

`sql/V3_20260612_pre_new_plan_runtime_messages_cleanup.sql`

Rollback SQL:

`sql/V3_20260612_pre_new_plan_runtime_messages_cleanup_rollback.sql`

Both SQL files are blocked by default. The cleanup SQL requires:

```sql
SET LOCAL ashare_v3.allow_v3_20260612_pre_new_plan_cleanup = 'true';
```

and still contains a default `RAISE EXCEPTION` before the first mutation. A later execute final gate must refresh live refs and explicitly authorize removal of that default hard-fail before cleanup can run.

The rollback SQL requires:

```sql
SET LOCAL ashare_v3.allow_v3_20260612_pre_new_plan_cleanup_rollback = 'true';
```

and also hard-fails before the first restore mutation.

## Backup Policy

The cleanup SQL backs up scoped rows into:

`common_runtime_cleanup_backup`

before any scoped deletes. The rollback SQL restores rows from that backup table for the cleanup run ID:

`v3_20260612_pre_new_plan_runtime_messages_cleanup_v1`

## Forbidden Scope

This contract gate did not:

- execute cleanup
- write database rows
- execute rollback
- modify or restart scheduler
- manually execute wrapper/N3/N4/N5
- consume or update outbox/inbox/checkpoint
- enter N6
- touch voice/mobile/sim/position/PnL/real trade

Next gate:

`V3_20260612_PRE_NEW_PLAN_RUNTIME_MESSAGES_CLEANUP_EXECUTE_FINAL_GATE_REVIEW`
