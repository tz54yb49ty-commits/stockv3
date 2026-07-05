# N2 Canonical Signal CHECK 022 Execution Report

## Result

```text
EXECUTED
layer_role=N2_condition
sql_file=sql/022_condition_canonical_signal_check_migration.sql
execution_method=psycopg fallback; psql was not available in PATH
```

## Scope

Only the signal whitelist CHECK constraints were changed on these nine tables:

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

No business rows were inserted, updated, or deleted.

## Post-Review

All nine CHECK constraints now support the compatible superset:

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

Historical deprecated rows remain valid under the compatible CHECK.

## Row Count Proof

Business row counts were unchanged by the migration:

```text
common_condition_run=10
common_condition_quality_item=842
stock_monitor_target=55042
index_monitor_target=740
board_monitor_target=4280
stock_condition_basis=55042
index_condition_basis=740
board_condition_basis=4280
stock_condition_pool=61699
index_condition_pool=449
board_condition_pool=4131
stock_minute_target_scope=48891
index_minute_target_scope=194
board_minute_target_scope=2810
stock_condition_display_basis=22018
index_condition_display_basis=256
board_condition_display_basis=1712
```

Run status remained unchanged:

```text
condition_layer_20260527_source_20260527_v1 = passed_active
condition_layer_20260527_source_20260527_v2 = not present
```

Event infrastructure remained unchanged:

```text
common_event_outbox=83063
common_event_inbox=2952
common_event_consumer_checkpoint=2803
```

## Rollback

Rollback SQL:

```text
sql/022_condition_canonical_signal_check_rollback.sql
```

Rollback is safe only before canonical-only rows exist. The rollback SQL includes a guard that blocks restoration of legacy-only CHECK constraints if canonical rows are present.

## Next Gate

Allowed next step:

```text
re-enter N2 canonical v2 execute gate for condition_layer_20260527_source_20260527_v2
```

Still prohibited in this migration gate:

```text
N2 v2 execute
N3/N4/N5/N6
worker
outbox/inbox/checkpoint writes
N1 writes
old system
```
