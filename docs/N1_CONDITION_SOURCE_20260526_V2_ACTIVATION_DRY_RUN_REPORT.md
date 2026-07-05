# N1 Condition Source 20260526 V2 Activation Dry-Run Report

Result: `DRY_RUN_PASS`

- blocked: `false`
- blockers: `[]`
- source_batch_id: `condition_source_activation_20260526_v2`
- P0/P1/P2: `0/1/1`

## Expected Rows

```json
{
  "stock_daily_basic": 5504,
  "stock_financial": 5504,
  "index_membership": 12841,
  "board_membership": 56872,
  "total": 80721
}
```

## Evidence

V1 activation execute reached real source fetch / validation but blocked before commit. Its fetched source rows were:

```text
stock_daily_basic = 5504
stock_financial = 5504
index_membership = 12841
board_membership = 56872
```

The missing 16 stocks are suspended supplemental official daily-bar rows. They have `stock_daily_20260526_v2` facts, Tushare `suspend_d(20260526)` evidence, and Tushare `bak_daily(20260526)` rows, but no Tushare `daily_basic(20260526)`. V2 records them in the P1 manifest and excludes them from the condition stock universe.

Board membership local TDX txt currently has `10` unmapped raw rows / `7` unique identities, filtered as P2.

## Side Effects

```json
{
  "writes_postgres": false,
  "writes_parquet": false,
  "updates_active_source_version": false,
  "writes_outbox": false,
  "writes_inbox_or_checkpoint": false,
  "enters_n2_n3_n4_n5_n6": false,
  "worker_started": false,
  "old_system_touched": false,
  "real_trading": false
}
```

Rollback SQL: `sql/N1_condition_source_20260526_v2_activation_rollback.sql`
