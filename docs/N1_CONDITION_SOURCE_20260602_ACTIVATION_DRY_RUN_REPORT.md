# N1 Condition Source 20260528 Activation Dry-Run

Result: `DRY_RUN_PASS`

- layer_role: `N1_ingestion`
- trade_date: `20260602`
- source_batch_id: `condition_source_activation_20260602_v1`
- P0/P1/P2: `0/2/1`
- official_no_trade excluded: `18`
- stale identity manifest rows: `1`

Expected rows:

```json
{
  "stock_daily_basic": 5507,
  "stock_financial": 5507,
  "index_membership": 12841,
  "board_membership": 56960,
  "total": 80815
}
```

Rollback SQL: `sql/N1_condition_source_20260602_activation_rollback.sql`
