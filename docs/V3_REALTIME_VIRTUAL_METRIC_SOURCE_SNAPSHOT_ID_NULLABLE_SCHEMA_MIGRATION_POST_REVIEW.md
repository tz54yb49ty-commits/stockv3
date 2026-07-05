# V3 Realtime Virtual Metric Source Snapshot ID Nullable Schema Migration Post Review

- result: `POST_REVIEW_PASS`
- execute_report: `docs/V3_REALTIME_VIRTUAL_METRIC_SOURCE_SNAPSHOT_ID_NULLABLE_SCHEMA_MIGRATION_EXECUTE_REPORT.json`

## Proof

- `source_snapshot_id` is nullable on stock/index/board action-confirmation projection metric tables.
- FK constraints remain present.
- Target writer run scoped rows remain zero.
- Global metric table row counts are unchanged.
- Rollback SQL remains available and guarded.

## Decision

Allowed to return to runtime_control for migration post-review registration and writer execute retry final gate review.
