# V3 Realtime Virtual Metric Source Snapshot ID Nullable Schema Migration Post Review Registration

- result: `POST_REVIEW_PASS`
- layer_role: `runtime_control`
- generated_at: `2026-06-12T22:27:18+08:00`

## Migration Registry

- migration result: `MIGRATION_PASS`
- migration SQL: `sql/V3_realtime_virtual_metric_source_snapshot_id_nullable_compatibility.sql`
- scope: schema-only `source_snapshot_id DROP NOT NULL`
- business rows written: `false`
- writer executed: `false`
- N4/N5 executed: `false`
- outbox/inbox/checkpoint consumed or updated: `false`
- N6/voice/mobile/sim/trade touched: `false`

## Live Schema Registry

- `stock_action_confirmation_projection_metric.source_snapshot_id`: `bigint`, nullable `YES`, FK retained to `stock_realtime_daily_snapshot(snapshot_id)`
- `index_action_confirmation_projection_metric.source_snapshot_id`: `bigint`, nullable `YES`, FK retained to `index_realtime_daily_snapshot(snapshot_id)`
- `board_action_confirmation_projection_metric.source_snapshot_id`: `bigint`, nullable `YES`, FK retained to `board_realtime_daily_snapshot(snapshot_id)`

## Business Row Registry

Target writer run scoped rows remain zero:

- `common_market_data_run=0`
- `common_market_data_quality_item=0`
- `stock_action_confirmation_projection_metric=0`
- `index_action_confirmation_projection_metric=0`
- `board_action_confirmation_projection_metric=0`

## Rollback Registry

- rollback SQL: `sql/V3_realtime_virtual_metric_source_snapshot_id_nullable_compatibility_rollback.sql`
- rollback executed: `false`
- hard-fail before `ALTER`: `true`
- null-ref check before `SET NOT NULL`: `true`
- no `DROP` / `TRUNCATE` / `CASCADE`

## Writer State

The live DB schema blocker is resolved, but the writer preflight artifact still carries the stale blocker:

- stale blocker: `source_snapshot_id_nullable_schema_migration_required`
- direct writer execute without preflight refresh: `false`
- next allowed gate: `V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_PREFLIGHT_REFRESH_AFTER_SOURCE_SNAPSHOT_ID_SCHEMA_MIGRATION_GATE`

## Forbidden Scope Proof

This registration gate did not start a scheduler, execute writer/N3/N4/N5, write business rows, consume or update outbox/inbox/checkpoint, enter N6, or touch voice/mobile/sim/trade.
