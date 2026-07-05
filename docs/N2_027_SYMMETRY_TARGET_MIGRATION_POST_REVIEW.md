# N2 027 Symmetry Target Price Migration Post-Review

Status: **EXECUTED**

Layer: `N2_condition`

## Command

```bash
export DATABASE_URL='postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3'
/opt/homebrew/Cellar/postgresql@16/16.14/bin/psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/027_condition_symmetry_target_price_compatibility_migration.sql
```

## Database

- database: `ashare_v3`
- user: `ashare_v3_user`
- before snapshot: `docs/N2_027_symmetry_target_migration_before_snapshot.json`

## Schema Result

- all_new_fields_present: `true`
- all_expected_constraints_present: `true`
- all_constraints_validated: `true`
- forbidden_columns_present: `0`
- new_fields_nonnull_total: `0`

## Row Count Delta

| table | delta |
|---|---:|
| stock_condition_basis | 0 |
| index_condition_basis | 0 |
| board_condition_basis | 0 |
| stock_condition_pool | 0 |
| index_condition_pool | 0 |
| board_condition_pool | 0 |
| stock_minute_target_scope | 0 |
| index_minute_target_scope | 0 |
| board_minute_target_scope | 0 |
| stock_condition_display_basis | 0 |
| index_condition_display_basis | 0 |
| board_condition_display_basis | 0 |


## Event Boundary

| table | delta |
|---|---:|
| common_event_outbox | 0 |
| common_event_inbox | 0 |
| common_event_consumer_checkpoint | 0 |


## Rollback

- rollback_safe: `true`
- rollback SQL: `sql/027_condition_symmetry_target_price_compatibility_rollback.sql`

## Boundary Proof

```text
business_rows_written=false
business_row_backfill=false
outbox_inbox_checkpoint_changed=false
N1/N3/N4/N5/N6_execute=false
worker_started=false
old_system_touched=false
locked_target_price_added=false
target_lock_status_added=false
```
