# N2 031 Level Score Schema Migration Final Gate

Status: `PASS`

Layer: `N2_condition`

This final gate was read-only. It did not execute migration 031, did not execute
an N2 condition run, did not write `condition_*` business rows, did not pull
market data, did not enter N3/N4/N5/N6, and did not start a worker.

## Scope

Migration SQL:

```text
sql/031_condition_level_score_columns_migration.sql
```

Rollback SQL:

```text
sql/031_condition_level_score_columns_rollback.sql
```

Target tables are exactly the 12 N2 condition tables:

```text
stock/index/board_condition_basis
stock/index/board_condition_pool
stock/index/board_minute_target_scope
stock/index/board_condition_display_basis
```

The migration adds nullable integer columns:

```text
level_up_score
level_down_score
```

Each column is constrained to `NULL` or `[0, 3124]`.

## Read-Only Checks

```text
existing level-score columns before migration = 0 / 24
expected missing columns before migration = 24
INSERT/UPDATE/DELETE/TRUNCATE/COPY = none
N1 stock_financial_metrics_fact touched = false
outbox/inbox/checkpoint touched = false
N3/N4/N5/N6 tables touched = false
locked_target_price / target_lock_status = absent
```

Event table baseline:

```text
common_event_outbox = 151341
common_event_inbox = 56170
common_event_consumer_checkpoint = 4368
```

## Rollback

Rollback is DDL-only and drops only the two 031 columns from the same 12 N2
tables. It does not clean business rows and does not touch runtime events or
downstream layers.

## Risk

```text
migration risk = low-to-medium
rollback risk = low before N2 rows depend on level score columns
```

The main risk is short table locks from `ALTER TABLE`; no business row backfill
is planned.

## Execute User Confirmation Point

Allowed only after explicit user confirmation:

```bash
psql "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3" \
  -v ON_ERROR_STOP=1 \
  -f sql/031_condition_level_score_columns_migration.sql
```

If local `psql` is unavailable, execute the same SQL file through the existing
`psycopg` fallback pattern, with all statements in one transaction and
`ON_ERROR_STOP` behavior.

After execute, do only 031 schema migration post-review. Do not run N2 active
supersede and do not enter N3.
