# N2-R4 013 Migration Execution Report

layer_role = N2_condition
generated_at = 2026-05-24T23:54:15+08:00
status = passed

## Scope

Executed exactly:

```text
sql/013_condition_period_trigger_baseline_migration.sql
```

The migration is additive and nullable only. It adds `period_trigger_baseline_json JSONB` to the 9 N2 condition tables.

No condition business data was overwritten. No `condition_basis`, `condition_pool`, or `minute_target_scope` rows were inserted, updated, or deleted by this phase.

## Snapshots

Before snapshot:

```text
backups/N2_R4_013_migration_before_snapshot_20260524235330.json
```

After snapshot:

```text
backups/N2_R4_013_migration_after_snapshot_20260524235415.json
```

Post schema gap report:

```text
tmp/N2_R4_013_post_schema_gap_report.json
```

## Schema Result

| Check | Before | After |
|---|---:|---:|
| missing_column_count | 9 | 0 |
| type_mismatch_count | n/a | 0 |
| migration_required | yes | no |

The field exists on all 9 required tables after migration:

```text
stock_condition_basis
index_condition_basis
board_condition_basis
stock_condition_pool
index_condition_pool
board_condition_pool
stock_minute_target_scope
index_minute_target_scope
board_minute_target_scope
```

Each column is `jsonb`, nullable, and has no default expression.

## Row Count Guard

| Table | Before | After | Changed |
|---|---:|---:|---:|
| stock_condition_basis | 27520 | 27520 | 0 |
| index_condition_basis | 403 | 403 | 0 |
| board_condition_basis | 2140 | 2140 | 0 |
| stock_condition_pool | 40338 | 40338 | 0 |
| index_condition_pool | 353 | 353 | 0 |
| board_condition_pool | 2814 | 2814 | 0 |
| stock_minute_target_scope | 27530 | 27530 | 0 |
| index_minute_target_scope | 98 | 98 | 0 |
| board_minute_target_scope | 1493 | 1493 | 0 |

`common_event_outbox` row count:

```text
26652 -> 26652
```

Active condition run remained unchanged:

```text
condition_layer_20260522_to_20260525_20260524205747_execute
```

## Quality

Migration validation:

```text
P0=0
P1=0
P2=0
```

The active condition run itself was not modified and therefore retains its existing run quality metadata:

```text
p0_count=0
p1_count=5
p2_count=3
```

## Boundary Confirmation

```text
overwrite_executed=false
condition_business_rows_written=false
common_event_outbox_changed=false
entered_N3_N4_N5_N6=false
market_data_pulled=false
old_system_touched=false
worker_started=false
```

## Verification

```text
python3 -m compileall scripts src tests
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_condition_static_reference_period_chain.py'
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_condition_schema_migration_readiness.py'
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_condition_basis.py'
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_condition_pool.py'
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_minute_target_scope.py'
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n2_web_policy.py'
git diff --check
```

All listed validations passed.

## Rollback Note

This was an additive schema-only migration. Automatic rollback was not executed.

Manual rollback, if explicitly confirmed later, is documented in:

```text
sql/N2_R4_013_manual_rollback.sql
```

Rollback would drop `period_trigger_baseline_json` from the 9 N2 tables. It should only be used before any dependent overwrite/run relies on this field.
