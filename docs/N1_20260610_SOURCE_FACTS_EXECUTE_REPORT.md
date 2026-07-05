# N1 20260610 Source Facts Execute Report

Result: `EXECUTE_PASS`

- layer_role: `N1_ingestion`
- execute_authorized: `True`
- official_daily_batch_id: `official_daily_ingest_20260610_v1`
- condition_source_batch_id: `condition_source_activation_20260610_v1`

## Row Counts

```json
{
  "official_daily": {
    "stock": 5510,
    "index": 83,
    "board": 428,
    "total": 6021
  },
  "condition_source": {
    "stock_daily_basic": 5510,
    "stock_financial": 5510,
    "index_membership": 12841,
    "board_membership": 56962,
    "total": 80823
  },
  "combined_total": 86844
}
```

## Skip Policy

```json
{
  "policy": "skip_missing_stock_identity_when_count_lte_10",
  "threshold": 10,
  "skipped_identities": [
    {
      "ts_code": "920206.BJ",
      "canonical_identity_key": "stock:BJ:920206",
      "asset_kind": "stock",
      "reason": "stock_identity_missing_below_threshold",
      "policy_name": "skip_missing_stock_identity_when_count_lte_10",
      "source_presence": [
        "tushare.daily",
        "tushare.daily_basic"
      ],
      "severity": "P1",
      "writes_stock_daily_bar_fact": false,
      "writes_stock_daily_basic": false,
      "writes_stock_financial_metrics_fact": false,
      "action": "exclude_from_20260608_source_facts"
    }
  ]
}
```

Rollback SQL: `sql/N1_20260610_source_facts_guarded_runner_rollback.sql`
