# N1 Condition Source 20260528 Activation Dry-Run

Result: `DRY_RUN_PASS`

- layer_role: `N1_ingestion`
- trade_date: `20260528`
- source_batch_id: `condition_source_activation_20260528_v1`
- P0/P1/P2: `0/3/1`
- official_no_trade excluded: `18`
- stale identity manifest rows: `1`

Expected rows:

```json
{
  "stock_daily_basic": 5506,
  "stock_financial": 5506,
  "index_membership": 12841,
  "board_membership": 56958,
  "total": 80811
}
```

Rollback SQL: `sql/N1_condition_source_20260528_activation_rollback.sql`
