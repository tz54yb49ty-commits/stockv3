# N2-Display-2b 014b Quality CHECK Migration Execution Report

layer_role = N2_condition
status = EXECUTED

## Scope

Executed only:

```text
/opt/homebrew/Cellar/postgresql@16/16.14/bin/psql "$ASHARE_V3_POSTGRES_DSN" -v ON_ERROR_STOP=1 -f sql/014b_condition_display_quality_check.sql
```

Note: plain `psql` was not in PATH in this shell, so the same SQL was executed with the Homebrew PostgreSQL 16 psql binary used by prior migrations.

Not executed:

```text
overwrite active condition run
condition_basis / condition_pool / minute_target_scope / condition_display_basis business writes
N3/N4/N5/N6 tasks
service / worker
```

## CHECK Definition

Before:

```text
CHECK ((layer_scope = ANY (ARRAY['monitor_target'::text, 'condition_basis'::text, 'condition_pool'::text, 'minute_target_scope'::text, 'condition_run'::text])))
```

After:

```text
CHECK ((layer_scope = ANY (ARRAY['monitor_target'::text, 'condition_basis'::text, 'condition_pool'::text, 'minute_target_scope'::text, 'condition_display_basis'::text, 'condition_run'::text])))
```

## Verification

| Check | Before | After | Result |
|---|---:|---:|---|
| common_condition_quality_item row_count | 415 | 415 | unchanged |
| common_event_outbox row_count | 53304 | 53304 | unchanged |
| common_condition_run total | 6 | 6 | unchanged |
| passed condition run count | 1 | 1 | unchanged |
| stock_condition_display_basis | 0 | 0 | empty |
| index_condition_display_basis | 0 | 0 | empty |
| board_condition_display_basis | 0 | 0 | empty |

## Layer Scope Distribution

| layer_scope | Before | After |
|---|---:|---:|
| condition_basis | 121 | 121 |
| condition_pool | 131 | 131 |
| condition_run | 60 | 60 |
| minute_target_scope | 103 | 103 |

## Acceptance

```text
condition_display_basis_allowed = true
old_layer_scope_values_allowed = true
common_condition_quality_item_row_count_unchanged = true
common_event_outbox_unchanged = true
display_tables_still_empty = true
overwrite_performed = false
blockers = []
```

## Rollback Hint

Manual schema rollback only. Before reverting, verify:

```sql
SELECT count(*) FROM common_condition_quality_item WHERE layer_scope = 'condition_display_basis';
```

It must be 0 before dropping the new CHECK and re-adding the old CHECK without `condition_display_basis`.

## Next Step

```text
must_rerun_n2_display_4_overwrite_preflight = true
```

## Artifacts

- before_snapshot: `backups/N2_DISPLAY_2B_014b_before_snapshot_20260525.json`
- after_snapshot: `backups/N2_DISPLAY_2B_014b_after_snapshot_20260525.json`
- json_report: `docs/N2_DISPLAY_2B_014B_MIGRATION_EXECUTION_REPORT.json`
