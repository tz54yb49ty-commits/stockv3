# N2 Condition Layer 20260529 Dry-run Report

- source_trade_date: `20260529`
- for_trade_date: `20260601`
- prev_trade_date: `20260529`
- run_id_suggestion: `condition_layer_20260529_source_20260529_v1`
- status: `DRY_RUN_PASS`
- P0/P1/P2: `0/9/3`
- policy_source: `8782_console`
- writes_performed: `false`

```json
{
  "active_source_versions": {
    "board_daily": "board_daily_20260529_v1",
    "board_membership": "board_membership_20260529_v1",
    "index_daily": "index_daily_20260529_v1",
    "index_membership": "index_membership_20260529_v1",
    "stock_daily": "stock_daily_20260529_v1",
    "stock_daily_basic": "stock_daily_basic_20260529_v1",
    "stock_financial": "stock_financial_20260529_v1"
  },
  "expected_row_counts_by_stage": {
    "condition_basis": {
      "board": 428,
      "index": 83,
      "stock": 5506
    },
    "condition_display_basis": {
      "board": 428,
      "index": 83,
      "stock": 1973
    },
    "condition_pool": {
      "board": 942,
      "index": 187,
      "stock": 4342
    },
    "minute_target_scope": {
      "board": 942,
      "index": 187,
      "stock": 4323
    },
    "monitor_target": {
      "board": 428,
      "index": 83,
      "stock": 5506
    },
    "quality_item": 109
  }
}
```
