# N2 Canonical Signal CHECK Migration Readiness

## Scope

Layer role: `N2_condition`.

This gate only changes signal whitelist CHECK constraints on these nine N2 tables:

```text
stock_condition_pool
index_condition_pool
board_condition_pool
stock_minute_target_scope
index_minute_target_scope
board_minute_target_scope
stock_condition_display_basis
index_condition_display_basis
board_condition_display_basis
```

It does not write business rows, does not modify `common_condition_run.status`, does not change v1/v2 run status, and does not touch N3/N4/N5/N6 or event infrastructure.

## Current CHECK

Current database CHECK constraints only allow the legacy signal whitelist:

```text
B_BUY_30M_VOL
B_BUY
S_SELL_30M_SHRINK
S_SELL
BUY_HINT
SELL_HINT
```

This blocks canonical N2 v2 writes because current N2 output now uses:

```text
BUY
BUY:FULL
SELL
SELL:FULL
BUY_HINT
SELL_HINT
```

## Historical Rows

Historical N2 rows still contain deprecated signal values across pool, scope, and display tables. Therefore the migration must use a compatible superset instead of immediately narrowing to canonical-only values.

Compatible whitelist:

```text
BUY
BUY:FULL
SELL
SELL:FULL
BUY_HINT
SELL_HINT
B_BUY
B_BUY_30M_VOL
S_SELL
S_SELL_30M_SHRINK
```

Future write quality gates and N2 code still prohibit deprecated values in new canonical runs.

## Files

```text
sql/022_condition_canonical_signal_check_migration.sql
sql/022_condition_canonical_signal_check_rollback.sql
```

Rollback restores the legacy whitelist and includes a guard that blocks rollback if canonical-only rows already exist.

## Readiness

```text
readiness: PASS
execute_performed: false
business_rows_written: false
schema_migration_executed: false
requires_user_confirmation: true
```

Next allowed step: user explicitly confirms execution of `sql/022_condition_canonical_signal_check_migration.sql`.
