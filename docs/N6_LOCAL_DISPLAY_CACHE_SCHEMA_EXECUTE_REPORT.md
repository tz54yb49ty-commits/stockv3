# N6_LOCAL_DISPLAY_CACHE_SCHEMA_EXECUTE_REPORT

Status: EXECUTE_PASS

Layer role: runtime_control

Execute date: 2026-06-07

Scope: schema-only creation of N6 local display cache tables. This execution
did not sync N2/N1 data, did not activate cache, did not touch N3/N4/N5/N6
action flow, did not consume outbox, and did not start a worker.

## Inputs

- Schema SQL: `sql/N6_local_display_cache_schema.sql`
- Rollback SQL: `sql/N6_local_display_cache_schema_rollback.sql`
- Mapping repair: `docs/N6_LOCAL_DISPLAY_CACHE_MAPPING_REPAIR.json`
- Mapping dry-run: `docs/N6_LOCAL_DISPLAY_CACHE_MAPPING_REPAIR_DRY_RUN.json`

Target DB proof:

```text
database=ashare_v3
user=ashare_v3_user
host=127.0.0.1/32
port=5432
```

## Execute Command

```bash
/opt/homebrew/Cellar/postgresql@16/16.14/bin/psql \
  'postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3' \
  -v ON_ERROR_STOP=1 -X \
  -f sql/N6_local_display_cache_schema.sql
```

Result: command returned `0`.

## Created Tables

| Table | Exists | Row count |
|---|---:|---:|
| `n6_display_cache_run` | true | 0 |
| `n6_stock_display_cache` | true | 0 |
| `n6_index_display_cache` | true | 0 |
| `n6_board_display_cache` | true | 0 |
| `n6_index_membership_display_cache` | true | 0 |
| `n6_board_membership_display_cache` | true | 0 |

All six tables are empty. No cache rows were synced.

## Constraint / Index Proof

Constraint summary:

```text
pk_count=6
fk_count=5
check_count=34
constraint_count=45
index_count=42
```

Required unique / primary indexes exist:

```text
n6_display_cache_run_pkey=true
n6_stock_display_cache_pkey=true
n6_index_display_cache_pkey=true
n6_board_display_cache_pkey=true
n6_index_membership_display_cache_pkey=true
n6_board_membership_display_cache_pkey=true
n6_display_cache_run_active_once=true
uq_n6_stock_display_cache_source_fanout=true
uq_n6_index_display_cache_source_fanout=true
uq_n6_board_display_cache_source_fanout=true
```

The five child cache tables have FK references to `n6_display_cache_run`.

## Rollback Proof

Rollback SQL:

```text
sql/N6_local_display_cache_schema_rollback.sql
```

Static checks:

```text
hard_fail_before_drop=true
no_cascade=true
rollback_scope_only_n6_cache_tables=true
source_tables_touched=false
n3_n4_n5_tables_touched=false
n6_projection_or_card_touched=false
outbox_inbox_checkpoint_touched=false
```

Rollback first counts all six cache tables and raises before any `DROP TABLE`
if any cache table is non-empty.

## Forbidden Scope Proof

This execution did not:

- sync N2/N1 data
- activate cache
- write cache rows
- modify N3/N4/N5/N6 action flow
- generate proposal/order/trade
- update position/PnL
- submit real trade
- start worker
- consume or update outbox

Event infra scoped proof:

```text
common_event_outbox refs for N6_display_cache=0
common_event_inbox refs for N6_display_cache=0
common_event_consumer_checkpoint refs for n6_display_cache%=0
```

## Validation

```text
schema_exists=PASS
row_count_zero=PASS
rollback_static_check=PASS
JSON parse=PASS
compileall=PASS
git diff --check=PASS
```

## Decision

EXECUTE_PASS.

Allowed next gate:

```text
N6_LOCAL_DISPLAY_CACHE_SYNC_DRY_RUN_REFRESH_GATE
```

Still forbidden:

```text
N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE_GATE
```

A fresh sync dry-run/preflight must be generated against the live schema before
any cache data sync execute is considered.
