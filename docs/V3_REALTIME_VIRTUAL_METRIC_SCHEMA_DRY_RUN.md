# V3 Realtime Virtual Metric Schema Dry Run

Result: `DRY_RUN_PASS`

This dry-run only validates the additive schema draft and contract. It does not execute migration, write DB, write outbox/inbox/checkpoint, start a worker, execute N4/N5, or enter N6.

Artifacts:

- schema draft: [039_v3_realtime_virtual_metric_schema_draft.sql](/Users/chuanfuchen/Documents/A股监控系统v3/sql/039_v3_realtime_virtual_metric_schema_draft.sql)
- rollback draft: [039_v3_realtime_virtual_metric_schema_rollback_draft.sql](/Users/chuanfuchen/Documents/A股监控系统v3/sql/039_v3_realtime_virtual_metric_schema_rollback_draft.sql)
- contract: [V3_REALTIME_VIRTUAL_METRIC_SCHEMA_CONTRACT.json](/Users/chuanfuchen/Documents/A股监控系统v3/docs/V3_REALTIME_VIRTUAL_METRIC_SCHEMA_CONTRACT.json)

Coverage:

- physical stock/index/board metric tables
- `1m / 5m / 30m / 120m / D / W / M / Q / Y`
- `snapshot_id / event_id / quality_status`
- `deterministic_pass_flags`
- no N4/N5 business rule change

## Field name canonicalization

- DB columns use PostgreSQL lowercase identifiers.
- Display aliases such as `current_D_body_high` map to lowercase DB columns such as `current_d_body_high`.
- Mixed-case DB identifiers are not allowed.
