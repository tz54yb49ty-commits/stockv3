# N2-Display-2 014 Migration Execution Report

layer_role = N2_condition
status = EXECUTED

## Scope

Executed only the N2-Display 014 main migration:

```text
/opt/homebrew/Cellar/postgresql@16/16.14/bin/psql "$ASHARE_V3_POSTGRES_DSN" -v ON_ERROR_STOP=1 -f sql/014_condition_display_basis_schema.sql
```

Not executed:

```text
sql/014b_condition_display_quality_check.sql
```

No condition business rows were written. No N3/N4/N5/N6 task was entered. No service or worker was started.

## Artifacts

- before_snapshot: `backups/N2_DISPLAY_2_before_014_snapshot_20260525.json`
- after_snapshot: `backups/N2_DISPLAY_2_after_014_snapshot_20260525.json`
- json_report: `docs/N2_DISPLAY_2_014_MIGRATION_EXECUTION_REPORT.json`
- rollback_sql: `sql/014_condition_display_basis_rollback.sql`

## Display Tables

| Table | Before | After | Changed |
|---|---:|---:|---|
| stock_condition_display_basis | missing | 0 | yes |
| index_condition_display_basis | missing | 0 | yes |
| board_condition_display_basis | missing | 0 | yes |

## Existing N2 Row Counts

| Table | Before | After | Changed |
|---|---:|---:|---|
| stock_condition_basis | 33024 | 33024 | no |
| index_condition_basis | 484 | 484 | no |
| board_condition_basis | 2568 | 2568 | no |
| stock_condition_pool | 44574 | 44574 | no |
| index_condition_pool | 371 | 371 | no |
| board_condition_pool | 3072 | 3072 | no |
| stock_minute_target_scope | 31766 | 31766 | no |
| index_minute_target_scope | 116 | 116 | no |
| board_minute_target_scope | 1751 | 1751 | no |

## Common Event Outbox

| Table | Before | After | Changed |
|---|---:|---:|---|
| common_event_outbox | 53304 | 53304 | no |

## N3 Key Tables

| Table | Before | After | Changed |
|---|---:|---:|---|
| common_market_data_run | 4 | 4 | no |
| common_market_data_quality_item | 113 | 113 | no |
| common_market_data_subscription_candidate | 40608 | 40608 | no |
| common_market_data_subscription | 19692 | 19692 | no |
| common_market_data_pull_plan | 27 | 27 | no |
| stock_realtime_daily_snapshot | 0 | 0 | no |
| index_realtime_daily_snapshot | 0 | 0 | no |
| board_realtime_daily_snapshot | 0 | 0 | no |
| stock_minute_bar_1m | 490320 | 490320 | no |
| index_minute_bar_1m | 2160 | 2160 | no |
| board_minute_bar_1m | 30480 | 30480 | no |
| stock_previous_day_minute_preload_status | 2052 | 2052 | no |
| index_previous_day_minute_preload_status | 9 | 9 | no |
| board_previous_day_minute_preload_status | 127 | 127 | no |

## N4 Key Tables

| Table | Before | After | Changed |
|---|---:|---:|---|
| common_trigger_run | 3 | 3 | no |
| common_trigger_quality_item | 215 | 215 | no |
| stock_trigger_context_snapshot | 12708 | 12708 | no |
| index_trigger_context_snapshot | 54 | 54 | no |
| board_trigger_context_snapshot | 774 | 774 | no |
| common_trigger_state | 17768 | 17768 | no |
| common_trigger_match | 53304 | 53304 | no |

## N5 Key Tables

| Table | Before | After | Changed |
|---|---:|---:|---|
| common_action_run | 0 | 0 | no |
| common_action_quality_item | 0 | 0 | no |
| stock_action_fact | 0 | 0 | no |
| index_action_fact | 0 | 0 | no |
| board_action_fact | 0 | 0 | no |
| common_action_event | 0 | 0 | no |
| common_position_state | 0 | 0 | no |
| common_position_event | 0 | 0 | no |

## Verification

```text
stock_condition_display_basis exists and row_count=0: passed
index_condition_display_basis exists and row_count=0: passed
board_condition_display_basis exists and row_count=0: passed
existing N2 row counts unchanged: passed
common_event_outbox row_count unchanged: passed
N3/N4/N5 key row counts unchanged: passed
014b executed: false
row_count_anomaly: false
```

## Decision

```text
can_enter_n2_display_3_dry_run=true
```

## Rollback

Manual rollback draft:

```text
sql/014_condition_display_basis_rollback.sql
```

It drops only:

```text
stock_condition_display_basis
index_condition_display_basis
board_condition_display_basis
```

It does not alter condition_basis / condition_pool / minute_target_scope and does not touch N3/N4/N5.
