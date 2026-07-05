# N2 030 Symmetry Secondary Anchor Schema Migration Final Gate

Status: **PASS**

## Scope

- migration: `sql/030_condition_symmetry_secondary_anchor_columns_migration.sql`
- rollback: `sql/030_condition_symmetry_secondary_anchor_columns_rollback.sql`
- target tables: 12 N2 condition tables
- new columns per table: 16 explicit up/down secondary-anchor fields

## Checks

- migration file exists: `True`
- rollback file exists: `True`
- target tables exist: `True`
- 030 columns currently missing: `True`
- uncommented migration DML present: `False`
- uncommented rollback DML present: `False`
- locked target fields in executable SQL: `False`
- NOT NULL in executable SQL: `False`
- DROP COLUMN in migration executable SQL: `False`
- obvious concurrent condition execute: `False`

## Baseline Row Counts

- stock_condition_basis: `110102`
- index_condition_basis: `1570`
- board_condition_basis: `8560`
- stock_condition_pool: `104021`
- index_condition_pool: `1611`
- board_condition_pool: `10711`
- stock_minute_target_scope: `91097`
- index_minute_target_scope: `1356`
- board_minute_target_scope: `9390`
- stock_condition_display_basis: `52138`
- index_condition_display_basis: `1012`
- board_condition_display_basis: `5691`
- common_event_outbox: `151341`
- common_event_inbox: `56170`
- common_event_consumer_checkpoint: `4368`

## Risk

- migration risk: medium-low; ALTER TABLE / ADD CHECK can take short locks, existing rows keep NULL in new columns and satisfy checks.
- rollback risk: low before any new active N2 run uses these columns. After v5 or downstream consumption, rollback needs a separate guard gate.

## Execute Candidate

```bash
psql "$ASHARE_V3_POSTGRES_DSN" -v ON_ERROR_STOP=1 \
  -f sql/030_condition_symmetry_secondary_anchor_columns_migration.sql
```

## Next Step

If the user explicitly confirms, execute only 030 migration, then run 030 post-review. Do not execute N2 active supersede until migration post-review and full dry-run/preflight pass.
