# N1 Condition Source 20260527 Activation Dry-Run Report

Result: `DRY_RUN_PASS`

- layer_role: `N1_ingestion`
- blocked: `false`
- blockers: `[]`
- source_batch_id: `condition_source_activation_20260527_v1`
- P0/P1/P2: `0/3/1`

## Expected Rows

```json
{
  "stock_daily_basic": 5506,
  "stock_financial": 5506,
  "index_membership": 12841,
  "board_membership": 56958,
  "total": 80811
}
```

## Evidence

20260527 active daily facts are ready:

```text
stock_daily_20260527_v1 = 5506
index_daily_20260527_v1 = 83
board_daily_20260527_v1 = 428
```

Current 20260527 condition source rows and target source_version conflicts are all `0`.

Local TDX txt was read in dry-run:

```text
index_membership raw=12841 filtered=12841 duplicates=0
board_membership raw=56970 filtered=56958 duplicates=0
board unmapped raw filtered=12 / unique missing stock identities=8
```

## Stock Universe

The condition stock universe is:

```text
eligible stock_daily
∩ stock_daily_basic
∩ stock_financial
```

The 18 `official_no_trade` stocks remain `exclude_from_condition_universe`; no placeholder rows are planned for `stock_daily_basic` or `stock_financial`.

`stock:SZ:300114 -> stock:SZ:302132` remains a stale identity manifest only. This gate does not modify identity.

## Boundary

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

Rollback SQL: `sql/N1_condition_source_20260527_activation_rollback.sql`
