# N2-E10 condition layer overwrite execute report

## Result

- execute_run_id: `condition_layer_20260522_to_20260525_20260524014029_execute`
- previous_active_run_id: `condition_layer_20260522_to_20260525_20260523223042_execute`
- source_trade_date: `20260522`
- for_trade_date: `20260525`
- prev_trade_date: `20260522`
- run_status: `passed`
- active_run_count: `1`
- rollback_sql: `/Users/chuanfuchen/Documents/A股监控系统v3/sql/N2_E10_condition_layer_overwrite_rollback.sql`
- before_snapshot: `/Users/chuanfuchen/Documents/A股监控系统v3/backups/N2_E10_before_overwrite_active_condition_snapshot_20260524013810.json`

## Preflight

- schema_missing_column_count: `0`
- schema_type_mismatch_count: `0`
- schema_migration_required: `False`
- execute_allowed: `True`
- blocked_reasons: `[]`
- P0/P1/P2: `0/5/3`

## Source Versions

```json
{
  "stock_daily": "stock_daily_20260522_v1",
  "stock_daily_basic": "stock_daily_basic_20260522_v1",
  "stock_financial": "stock_financial_20260522_v2",
  "index_daily": "index_daily_20260522_v4",
  "index_membership": "index_membership_20260522_v1",
  "board_daily": "board_daily_20260522_v1",
  "board_membership": "board_membership_20260522_v1"
}
```

## Row Counts

| table | rows |
|---|---:|
| `common_condition_run` | 1 |
| `common_condition_quality_item` | 70 |
| `stock_monitor_target` | 5504 |
| `stock_condition_basis` | 5504 |
| `index_monitor_target` | 81 |
| `index_condition_basis` | 81 |
| `board_monitor_target` | 428 |
| `board_condition_basis` | 428 |
| `stock_condition_pool` | 4236 |
| `index_condition_pool` | 18 |
| `board_condition_pool` | 258 |
| `index_minute_target_scope` | 18 |
| `board_minute_target_scope` | 258 |
| `stock_minute_target_scope` | 4236 |


## Fixed 9 Index Golden Audit

- fixed9_rows: `9`
- missing_codes: `[]`
- match_count: `9`
- diff_count: `0`
- index_condition_pool rows: `18`

## Pool / Scope Audit

- index_pool: objects `9`, rows `18`, out_of_range `0`
- board_pool: objects `127`, rows `258`, out_of_range `0`
- stock_pool: objects `2052`, rows `4236`, out_of_range `0`
- index_scope rows `18`, pool_link_violations `0`
- board_scope rows `258`, pool_link_violations `0`
- stock_scope rows `4236`, pool_link_violations `0`, market_value_violations `0`
- audit P0/P1/P2: `0/0/0`

## Boundary

- old_system_touched: `false`
- external_market_data_pulled: `false`
- N3_entered: `false`
- worker_started: `false`
- trigger/action/mobile/voice/sim_written: `false`
- migration_performed: `False`
- minute_kline_pulled: `False`
