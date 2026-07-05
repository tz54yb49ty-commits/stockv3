# N2-E8 Condition Layer 005 Migration Report

## Summary

- migration_executed: true
- sql_executed: `sql/005_condition_layer_policy_columns_migration.sql`
- migration_type: additive schema migration
- business_data_written: false
- overwrite_performed: false
- minute_kline_pulled: false
- downstream_layers_touched: false

## Backup

- schema_only_backup_before: `backups/condition_schema_before_005_20260523_215631.json`
- schema_snapshot_after: `backups/condition_schema_after_005_20260523_215726.json`
- pg_dump_available: false
- backup_method: PostgreSQL catalog metadata snapshot for condition-layer tables, constraints, indexes, row counts, and active run sample.

## SQL Statements Executed

```text
BEGIN
ALTER TABLE stock_condition_basis
ALTER TABLE stock_condition_pool
ALTER TABLE index_condition_pool
ALTER TABLE board_condition_pool
COMMIT
```

Only `ADD COLUMN IF NOT EXISTS` clauses from `005` were executed.

## Schema Gap

Before migration:

```text
missing_column_count=16
type_mismatch_count=0
```

After migration:

```text
missing_column_count=0
type_mismatch_count=0
```

New column checks after migration:

```text
stock_condition_basis:
  is_st=true
  stock_status=true
  official_daily_proof=true
  financial_quality_status=true

stock_condition_pool:
  policy_name=true
  policy_hash=true
  selected_reason=true
  excluded_reason=true

index_condition_pool:
  policy_name=true
  policy_hash=true
  selected_reason=true
  excluded_reason=true

board_condition_pool:
  policy_name=true
  policy_hash=true
  selected_reason=true
  excluded_reason=true
```

## Row Counts

Before and after row counts are unchanged:

```text
common_condition_run=1
common_condition_quality_item=62
stock_monitor_target=5504
index_monitor_target=80
board_monitor_target=428
stock_condition_basis=5504
index_condition_basis=80
board_condition_basis=428
stock_condition_pool=20246
index_condition_pool=273
board_condition_pool=1575
stock_minute_target_scope=7438
index_minute_target_scope=18
board_minute_target_scope=254
```

Active run sample count remained:

```text
recent_active_run_count=1
```

## Postchecks

```text
plan_condition_schema_gap.py:
  migration_required=false
  missing_column_count=0
  type_mismatch_count=0

plan_condition_schema_migration.py:
  static_ready=true
  failed_static_gates=[]

review_condition_migration.py:
  migration_safe_to_apply=false
  reason=no remaining schema gap after migration
  missing_column_count=0
  type_mismatch_count=0
```

## Rollback Note

This migration is additive. Automatic rollback was not performed.

Manual rollback, if ever required after compatibility review:

```sql
ALTER TABLE stock_condition_basis DROP COLUMN IF EXISTS is_st;
ALTER TABLE stock_condition_basis DROP COLUMN IF EXISTS stock_status;
ALTER TABLE stock_condition_basis DROP COLUMN IF EXISTS official_daily_proof;
ALTER TABLE stock_condition_basis DROP COLUMN IF EXISTS financial_quality_status;
ALTER TABLE stock_condition_pool DROP COLUMN IF EXISTS policy_name;
ALTER TABLE stock_condition_pool DROP COLUMN IF EXISTS policy_hash;
ALTER TABLE stock_condition_pool DROP COLUMN IF EXISTS selected_reason;
ALTER TABLE stock_condition_pool DROP COLUMN IF EXISTS excluded_reason;
ALTER TABLE index_condition_pool DROP COLUMN IF EXISTS policy_name;
ALTER TABLE index_condition_pool DROP COLUMN IF EXISTS policy_hash;
ALTER TABLE index_condition_pool DROP COLUMN IF EXISTS selected_reason;
ALTER TABLE index_condition_pool DROP COLUMN IF EXISTS excluded_reason;
ALTER TABLE board_condition_pool DROP COLUMN IF EXISTS policy_name;
ALTER TABLE board_condition_pool DROP COLUMN IF EXISTS policy_hash;
ALTER TABLE board_condition_pool DROP COLUMN IF EXISTS selected_reason;
ALTER TABLE board_condition_pool DROP COLUMN IF EXISTS excluded_reason;
```

## Boundary Confirmation

- Did not touch the old system.
- Did not write condition_basis / condition_pool / minute_target_scope business rows.
- Did not overwrite active run.
- Did not pull market data or minute K.
- Did not enter N3 / trigger / action / voice / mobile / sim / worker.
