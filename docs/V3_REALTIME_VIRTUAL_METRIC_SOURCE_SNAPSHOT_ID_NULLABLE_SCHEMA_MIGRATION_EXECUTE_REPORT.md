# V3 Realtime Virtual Metric Source Snapshot ID Nullable Schema Migration Execute Report

- result: `MIGRATION_PASS`
- migration_sql: `sql/V3_realtime_virtual_metric_source_snapshot_id_nullable_compatibility.sql`
- rollback_sql: `sql/V3_realtime_virtual_metric_source_snapshot_id_nullable_compatibility_rollback.sql`

## Execution

The first psql attempt did not execute the migration because it connected to the default local database `chuanfuchen`. The successful command explicitly used the local `ashare_v3` connection string and returned:

```text
ALTER TABLE
COMMENT
ALTER TABLE
COMMENT
ALTER TABLE
COMMENT
```

## Schema Proof

- stock/index/board `source_snapshot_id.is_nullable`: `YES/YES/YES`
- FK constraints remain present for stock/index/board snapshot references.

## Business Row Proof

Global metric table row counts remained unchanged:

```text
stock=2914
index=214
board=499
```

Target writer run scoped rows remain zero:

```text
common_market_data_run=0
common_market_data_quality_item=0
stock/index/board metric rows=0/0/0
```

## Boundary

No writer/N4/N5/N6 execution, no business row insert/update/delete, no outbox/inbox/checkpoint consumption or update, and no voice/mobile/sim/trade path.

## Validation

- JSON parse: `PASS`
- git diff --check: `PASS`
