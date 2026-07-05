# N1 Official Daily 20260526 V2 Ingestion Execute Preflight

日期：2026-05-27
layer_role：`N1_ingestion`
状态：`PREFLIGHT_PASS`

## Summary

```text
trade_date = 20260526
source_batch_id = official_daily_ingest_20260526_v2
blocked = False
blockers = none
P0/P1/P2 = 0/19/0
runner_readiness = ready_for_final_gate
source_fetch_implemented = True
postgres_commit_implemented = True
execute_authorized = false
```

## V2 Expected Rows

```json
{
  "stock_daily_bar_fact": 5520,
  "index_daily_bar_fact": 9,
  "board_daily_bar_fact": 428,
  "total_daily_fact": 5957
}
```

## Execute Pipeline

```json
{
  "wired": true,
  "enabled_for_this_run": true,
  "sequence": [
    "load_contract",
    "refresh_db_baseline",
    "fetch_tushare_stock_daily_and_adj_factor",
    "fetch_tdx_mootdx_supplemental_stock_daily",
    "fetch_official_no_trade_manifest",
    "fetch_index_daily",
    "fetch_board_daily",
    "validate_source_bundle",
    "validate_commit_preconditions",
    "build_commit_plan",
    "execute_commit_transaction"
  ],
  "tests_use_mock_source": true
}
```

No `official_no_trade` rows are written to `stock_daily_bar_fact`; they remain manifest/quality details only.
