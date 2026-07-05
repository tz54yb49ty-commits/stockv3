# N2 Active Status Migration Review

status = IMPLEMENTATION_PASS_PENDING_MIGRATION

## Decision

N2 canonical active condition run status is `passed_active`.

Legacy `passed` remains readable for existing lineage. It is not batch-migrated in this step.

## State Machine

```text
planned -> running -> passed_active
running -> failed / blocked
passed_active -> superseded / rolled_back
passed -> superseded / rolled_back
```

`passed` is retained as legacy active compatibility. Active selection must prefer `passed_active` before `passed`.

## Schema Plan

Migration:

```text
sql/015_condition_run_passed_active_status_migration.sql
```

Changes:

```text
common_condition_run.status CHECK adds passed_active
ux_common_condition_run_one_passed_active unique partial index:
  source_trade_date + for_trade_date
  WHERE status = 'passed_active'
```

The migration does not update, insert, or delete condition business data.

## Rollback Plan

Rollback:

```text
sql/015_condition_run_passed_active_status_rollback.sql
```

Rollback is guarded. It refuses to remove `passed_active` support if any `common_condition_run` rows still have `status='passed_active'`.

## Code Policy

```text
fetch active run:
  status IN ('passed_active', 'passed')
  ORDER BY passed_active first, then finished_at/created_at

execute success:
  new run status = passed_active

overwrite:
  previous active run -> superseded
  new run -> passed_active

preflight:
  BLOCKED if schema CHECK does not support passed_active
  BLOCKED if same source_trade_date + for_trade_date has more than one passed_active row
```

## N2 V2 Rerun Impact

`condition_layer_20260526_source_20260526_v2` remains not executed. It must stay blocked until 015 is explicitly executed and a final execute gate is rerun.

N3 lineage does not auto-switch.

## Boundary

```text
N2 rerun execute: not performed
condition tables: not written
existing run statuses: not changed
N3/N4/N5/N6: not touched
outbox/inbox/checkpoint: not touched
worker: not started
```
