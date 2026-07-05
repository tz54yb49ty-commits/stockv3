# N1 20260608 Source Facts Execute Final Gate Review

Result: `FINAL_GATE_PASS`

- layer_role: `N1_ingestion`
- trade_date: `20260608`
- for_trade_date: `20260609`
- target fact rows before execute: `0`
- metadata conflicts: `0`
- event refs: `0`
- downstream refs: `0`
- rollback_static_check: `True`

## Expected Rows

```json
{
  "official_daily": {
    "stock_daily_bar_fact": 5514,
    "index_daily_bar_fact": 83,
    "board_daily_bar_fact": 428,
    "total_daily_fact": 6025
  },
  "condition_source": {
    "stock_daily_basic": 5514,
    "stock_financial_metrics_fact": 5514,
    "index_membership_fact": 12841,
    "board_membership_fact": 56962,
    "total_condition_source_fact": 80831
  },
  "combined_total": 86856
}
```

## Skip Policy

```json
{
  "policy": "skip_missing_stock_identity_when_count_lte_10",
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

## Blockers

```json
[]
```

## Execute Command If Pass

```bash
PYTHONPATH=src python3 scripts/run_n1_20260608_source_facts_once.py --trade-date 20260608 --execute --user-confirmed --source-fetch-enabled --postgres-commit-enabled
```
