# N2 Condition Source Refresh for Stock Financial 20260615 v3 Readiness

Result: `READINESS_PASS`

## Scope

- layer_role: `N2_condition`
- source_trade_date: `20260615`
- for_trade_date: `20260616`
- active_stock_financial_source_version: `stock_financial_20260615_v3`
- previous_condition_run_id: `condition_layer_20260615_source_20260615_for_20260616_v3`
- target_condition_run_id: `condition_layer_20260615_source_20260615_for_20260616_v4`
- mode: readiness only; no execute; no database writes

## Prerequisite Proof

- N1 002831 repair post-review: `POST_REVIEW_PASS`
- N1 execute report: `EXECUTE_PASS`
- N2 current active post-review artifact: `POST_REVIEW_PASS`
- DB transaction mode: `default_transaction_read_only=on`

## N1 Active Financial Source Proof

- active stock_financial source_version: `stock_financial_20260615_v3`
- v3 fact rows: `5504`
- v2 fact rows preserved: `5504`
- semantic changed rows vs v2: `1`
- changed identity keys: `stock:SZ:002831`

### 002831 Financial Row Proof

```json
{
  "stock_identity_key": "stock:SZ:002831",
  "source": "stock_financial_canonical.tdx_mootdx_first.tdx_financial_package",
  "report_period": "20260331",
  "announcement_date": "20260428",
  "pe_core": "20.2506996374",
  "total_mv": "3929409.6385",
  "score": "87",
  "cash_realization_rate": "1.9254856573",
  "revenue_yoy_pct": "2.55",
  "core_profit_yoy_pct": "57.1302091953",
  "report_core_revenue": "3793342067.38",
  "report_core_profit": "3.4158605E+8",
  "core_profit_ttm": "1940382164",
  "core_gt_revenue_yoy": true,
  "revenue_growth_streak_q": 9,
  "core_growth_streak_q": 4,
  "core_gt_revenue_streak_q": 2,
  "forecast_type": null,
  "forecast_score": "0",
  "financial_metric_version": "financial_metric_v1",
  "financial_warning_json": {
    "warnings": [
      "forecast_missing"
    ],
    "source_type": "tdx_financial_package",
    "tdx_parity_repair": true,
    "interest_expense_used": "19744658"
  },
  "source_type": "tdx_financial_package",
  "interest_expense": "19744658",
  "operating_cashflow": "657719040"
}
```

## Current N2 Lineage Proof

- current active run: `condition_layer_20260615_source_20260615_for_20260616_v3`
- current active status: `passed_active`
- active run count for date pair: `1`
- current active N2 source_versions.stock_financial: `stock_financial_20260615_v2`
- refresh reason: current N2 v3 still consumed `stock_financial_20260615_v2` while N1 active is `stock_financial_20260615_v3`.

### Current v3 Rows

```json
{
  "stock_condition_basis": 5504,
  "index_condition_basis": 83,
  "board_condition_basis": 427,
  "stock_condition_pool": 4215,
  "index_condition_pool": 183,
  "board_condition_pool": 307,
  "stock_minute_target_scope": 4194,
  "index_minute_target_scope": 183,
  "board_minute_target_scope": 307,
  "stock_condition_display_basis": 1822,
  "index_condition_display_basis": 83,
  "board_condition_display_basis": 127,
  "stock_monitor_target": 5504,
  "index_monitor_target": 83,
  "board_monitor_target": 427,
  "common_condition_quality_item": 103
}
```

### Current v3 002831 Financial Fields

```json
{
  "stock_identity_key": "stock:SZ:002831",
  "financial_source_version": "stock_financial_20260615_v2",
  "financial_quality_status": "warning",
  "pe_core": "0.0009382111",
  "total_mv": "3929409.6385",
  "score": "65.6617734382",
  "cash_realization_rate": "2.2436682482",
  "revenue_yoy_pct": "2.550315514",
  "core_profit_yoy_pct": "15.7585516772",
  "report_core_revenue": "3793341905.18",
  "report_core_profit": "293144510.81",
  "core_profit_ttm": "4188193627.27",
  "core_gt_revenue_yoy": true,
  "revenue_growth_streak_q": 9,
  "core_growth_streak_q": 1,
  "core_gt_revenue_streak_q": 0,
  "forecast_type": null,
  "forecast_score": null,
  "financial_metric_version": "financial_metric_v1",
  "financial_warning_json": {
    "warnings": [
      "forecast_missing",
      "interest_expense_missing_finance_expense_used",
      "tushare_fallback_used"
    ],
    "ttm_annualized": false
  }
}
```

## Target v4 Baseline Proof

- `common_condition_run` rows for target v4: `0`
- all target v4 N2 table rows are zero: `True`
- N3/N4/N5/N6 refs for target v4: `{'common_market_data_run': 0, 'common_trigger_run': 0, 'common_action_run': 0, 'user_projection_run': 0}`
- event infra refs for target v4: `{'common_event_outbox': 0, 'common_event_inbox': 0, 'common_event_consumer_checkpoint': 0}`

```json
{
  "stock_condition_basis": 0,
  "index_condition_basis": 0,
  "board_condition_basis": 0,
  "stock_condition_pool": 0,
  "index_condition_pool": 0,
  "board_condition_pool": 0,
  "stock_minute_target_scope": 0,
  "index_minute_target_scope": 0,
  "board_minute_target_scope": 0,
  "stock_condition_display_basis": 0,
  "index_condition_display_basis": 0,
  "board_condition_display_basis": 0,
  "stock_monitor_target": 0,
  "index_monitor_target": 0,
  "board_monitor_target": 0,
  "common_condition_quality_item": 0
}
```

## Proposed N2 v4 Supersede Scope

- overwrite: `true`
- overwrite_semantics: `lineage_supersede_only`
- previous_active_run_id: `condition_layer_20260615_source_20260615_for_20260616_v3`
- target_run_id: `condition_layer_20260615_source_20260615_for_20260616_v4`
- delete_previous_rows: `false`
- update_previous_rows: `false`
- n3_lineage_auto_switch: `false`
- expected primary semantic change: `stock:SZ:002831` financial pass-through fields after consuming `stock_financial_20260615_v3`.

## Safety Requirements

Future execute, if later authorized, must write only N2 condition-layer tables and metadata:

```json
[
  "common_condition_run",
  "common_condition_quality_item",
  "stock_condition_basis",
  "index_condition_basis",
  "board_condition_basis",
  "stock_condition_pool",
  "index_condition_pool",
  "board_condition_pool",
  "stock_minute_target_scope",
  "index_minute_target_scope",
  "board_minute_target_scope",
  "stock_condition_display_basis",
  "index_condition_display_basis",
  "board_condition_display_basis",
  "stock_monitor_target",
  "index_monitor_target",
  "board_monitor_target"
]
```

Forbidden scopes remain:

```json
[
  "N1 facts/source versions",
  "N3/N4/N5/N6 facts",
  "common_event_outbox",
  "common_event_inbox",
  "common_event_consumer_checkpoint",
  "market data pull",
  "worker",
  "old system",
  "real trading"
]
```

## Rollback Planning

- rollback SQL to generate in next gate: `sql/N2_condition_source_refresh_stock_financial_20260615_v3_v4_rollback.sql`
- rollback must delete only target v4 rows.
- rollback must restore `condition_layer_20260615_source_20260615_for_20260616_v3` to `passed_active` if v4 rollback is authorized later.
- rollback must hard-guard event infra and N3/N4/N5/N6 refs before DELETE/UPDATE.
- rollback must not touch N1 facts, `stock_financial_20260615_v3`, or existing v3 rows.

## Quality Summary

- readiness blocker P0/P1/P2: `0/0/0` if result remains READINESS_PASS
- N1 repair P0/P1/P2: `0/1/0`
- current N2 v3 common_condition_run P0/P1/P2: `0/3/3`
- target v4 P0/P1/P2 must be recomputed in the contract/dry-run gate.

## Decision

- blocked_reasons: `[]`
- next gate: `N2_CONDITION_SOURCE_REFRESH_FOR_STOCK_FINANCIAL_20260615_V3_CONTRACT_GATE`
