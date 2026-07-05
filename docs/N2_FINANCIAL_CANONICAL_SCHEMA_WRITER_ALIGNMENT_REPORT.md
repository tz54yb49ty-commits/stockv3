# N2 Financial Canonical Schema/Writer Alignment

Result: IMPLEMENTATION_PASS

## Scope
- layer_role: `N2_condition`
- source_trade_date / for_trade_date / prev_trade_date: `20260529` / `20260601` / `20260529`
- current active N2 run: `condition_layer_20260529_source_20260529_v1`
- proposed post-migration run_id: `condition_layer_20260529_source_20260529_v2`
- active N1 stock_financial: `stock_financial_20260529_v2`

## Migration Draft
- migration: `sql/029_condition_stock_financial_canonical_columns_migration.sql`
- rollback: `sql/029_condition_stock_financial_canonical_columns_rollback.sql`
- additive nullable only: true
- DML/backfill: false
- target tables: stock_condition_basis, stock_condition_pool, stock_minute_target_scope, stock_condition_display_basis
- index/board financial columns added: false

## Writer Alignment
- condition_basis reads N1 active `stock_financial_metrics_fact` canonical fields.
- condition_pool inherits financial fields from basis.
- minute_target_scope inherits financial fields from pool.
- condition_display_basis inherits financial fields from basis.
- N2 does not recalculate financial metrics.
- `locked_target_price` / `target_lock_status` remain absent.

## Dry-Run Summary
```json
{
  "condition_basis": {
    "stock": 5506,
    "index": 83,
    "board": 428
  },
  "condition_pool": {
    "stock": 4106,
    "index": 21,
    "board": 284
  },
  "minute_target_scope": {
    "stock": 4106,
    "index": 21,
    "board": 284
  },
  "condition_display_basis": {
    "stock": 1871,
    "index": 9,
    "board": 127
  }
}
```

P0/P1/P2: `0` / `6` / `3`

## Preflight Summary
- execute_allowed: `False`
- blocked_reasons: `['schema_not_migrated', 'stock_financial_schema_not_ready']`
- stock_financial_fields_ready: `False`
- will_execute_sql: `False`
- writes_performed: `False`

Missing DB columns before 029 migration:
```json
{
  "stock_condition_basis": [
    "cash_realization_rate",
    "revenue_yoy_pct",
    "core_profit_yoy_pct",
    "report_core_revenue",
    "report_core_profit",
    "core_profit_ttm",
    "core_gt_revenue_yoy",
    "revenue_growth_streak_q",
    "core_growth_streak_q",
    "core_gt_revenue_streak_q",
    "forecast_type",
    "forecast_score",
    "score_breakdown_json",
    "financial_warning_json",
    "financial_metric_version"
  ],
  "stock_condition_pool": [
    "cash_realization_rate",
    "revenue_yoy_pct",
    "core_profit_yoy_pct",
    "report_core_revenue",
    "report_core_profit",
    "core_profit_ttm",
    "core_gt_revenue_yoy",
    "revenue_growth_streak_q",
    "core_growth_streak_q",
    "core_gt_revenue_streak_q",
    "forecast_type",
    "forecast_score",
    "score_breakdown_json",
    "financial_warning_json",
    "financial_metric_version",
    "pe_core",
    "score",
    "financial_quality_status"
  ],
  "stock_minute_target_scope": [
    "cash_realization_rate",
    "revenue_yoy_pct",
    "core_profit_yoy_pct",
    "report_core_revenue",
    "report_core_profit",
    "core_profit_ttm",
    "core_gt_revenue_yoy",
    "revenue_growth_streak_q",
    "core_growth_streak_q",
    "core_gt_revenue_streak_q",
    "forecast_type",
    "forecast_score",
    "score_breakdown_json",
    "financial_warning_json",
    "financial_metric_version",
    "pe_core",
    "score",
    "financial_quality_status"
  ],
  "stock_condition_display_basis": [
    "cash_realization_rate",
    "revenue_yoy_pct",
    "core_profit_yoy_pct",
    "report_core_revenue",
    "report_core_profit",
    "core_profit_ttm",
    "core_gt_revenue_yoy",
    "revenue_growth_streak_q",
    "core_growth_streak_q",
    "core_gt_revenue_streak_q",
    "forecast_type",
    "forecast_score",
    "score_breakdown_json",
    "financial_warning_json",
    "financial_metric_version"
  ]
}
```

## Next
Allowed next step: `N2 financial canonical schema migration final gate`.
Do not execute N2 active supersede until 029 migration is explicitly confirmed and post-migration preflight is rerun.
