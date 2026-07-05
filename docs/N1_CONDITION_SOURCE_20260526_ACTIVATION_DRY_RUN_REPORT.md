# N1 Condition Source 20260526 Activation Dry-Run Report

Result: `DRY_RUN_PASS`

- blocked: `False`
- blockers: `[]`
- source_batch_id: `condition_source_activation_20260526_v1`
- P0/P1/P2: `0/0/1`

Expected rows:

```json
{
  "stock_daily_basic": 5520,
  "stock_financial": 5520,
  "index_membership": 12841,
  "board_membership": 56872,
  "total": 80753
}
```

Stock scope policy:

```json
{
  "expected_stock_rows": 5520,
  "active_stock_identity_rows": 5523,
  "basis": "active stock_daily official v2 fact scope for 20260526",
  "stale_identity_excluded": [
    "stock:SZ:300114"
  ],
  "official_no_trade_excluded": [
    "stock:BJ:920058",
    "stock:BJ:920305"
  ],
  "requires_no_trade_bj_daily_basic_rows": false,
  "requires_stale_300114_rows": false
}
```

Side effects:

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
