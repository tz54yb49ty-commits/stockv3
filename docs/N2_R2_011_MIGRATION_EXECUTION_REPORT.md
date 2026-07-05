# N2-R2 011 Migration Execution Report

Date: 2026-05-24T17:36:49
Layer: N2_condition
Migration: `sql/011_condition_static_reference_period_migration.sql`
Status: executed

## Result

- before_snapshot: `/Users/chuanfuchen/Documents/A股监控系统v3/backups/N2_R2_011_before_migration_snapshot_20260524172940.json`
- after_snapshot: `/Users/chuanfuchen/Documents/A股监控系统v3/backups/N2_R2_011_after_migration_snapshot_20260524173648.json`
- active_condition_run_unchanged: `True`
- condition_row_counts_unchanged: `True`
- common_event_outbox_unchanged: `True`
- P0/P1/P2: `0/0/0`

## Target Columns

- `stock_condition_basis`: present `['down_buy_reference_period', 'up_sell_reference_period']`, missing `[]`
- `index_condition_basis`: present `['down_buy_reference_period', 'up_sell_reference_period']`, missing `[]`
- `board_condition_basis`: present `['down_buy_reference_period', 'up_sell_reference_period']`, missing `[]`
- `stock_condition_pool`: present `['down_buy_reference_period', 'up_sell_reference_period']`, missing `[]`

## Active Condition Run

```json
{
  "before": [
    "condition_layer_20260522_to_20260525_20260524014029_execute"
  ],
  "after": [
    "condition_layer_20260522_to_20260525_20260524014029_execute"
  ]
}
```

## Row Counts

| table | before | after |
|---|---:|---:|
| `stock_condition_basis` | 16512 | 16512 |
| `index_condition_basis` | 241 | 241 |
| `board_condition_basis` | 1284 | 1284 |
| `stock_condition_pool` | 31866 | 31866 |
| `index_condition_pool` | 317 | 317 |
| `board_condition_pool` | 2298 | 2298 |
| `stock_minute_target_scope` | 19058 | 19058 |
| `index_minute_target_scope` | 62 | 62 |
| `board_minute_target_scope` | 977 | 977 |

## common_event_outbox

```json
{
  "before": {
    "exists": true,
    "row_count": 26652,
    "fingerprint": "36dc307f7fddaff0f55193defc7b4972"
  },
  "after": {
    "exists": true,
    "row_count": 26652,
    "fingerprint": "36dc307f7fddaff0f55193defc7b4972"
  }
}
```

## Boundary

```text
old_system_touched: no
condition_basis/condition_pool/minute_target_scope business rows written: no
active condition run overwritten: no
N3/N4/N5/N6 entered: no
market data pulled: no
minute K pulled: no
worker started: no
```

## Next Step

Stop here. Do not run N2 full dry-run or overwrite until the user explicitly requests the next step.
