# N2 Financial Canonical Pass-Through Gate 20260529

Result: BLOCKED

## Summary
- source_trade_date / for_trade_date / prev_trade_date: `20260529` / `20260601` / `20260529`
- current active N2 run: `condition_layer_20260529_source_20260529_v1`
- proposed active supersede run_id: `condition_layer_20260529_source_20260529_v2`
- active N1 stock_financial: `stock_financial_20260529_v2` rows=5506
- N1 financial_metric_version: `{'financial_metric_v1': 5506}`
- rollback SQL draft: `sql/N2_condition_layer_20260529_financial_v2_rollback.sql`

## N1 Financial Field Coverage
- cash_realization_rate: 5385/5506
- pe_core: 5385/5506
- revenue_yoy_pct: 5288/5506
- core_profit_yoy_pct: 5288/5506
- report_core_revenue: 5385/5506
- report_core_profit: 5385/5506
- core_profit_ttm: 5385/5506
- core_gt_revenue_yoy: 5288/5506
- revenue_growth_streak_q: 5385/5506
- core_growth_streak_q: 5385/5506
- core_gt_revenue_streak_q: 5385/5506
- forecast_type: 0/5506
- forecast_score: 0/5506
- score: 5385/5506
- score_breakdown_json: 5506/5506
- financial_warning_json: 5506/5506
- financial_metric_version: 5506/5506
- finance-sector warning rows: 120
- pre-revenue warning rows: 1

## Blocker
N1 canonical financial v2 is ready, but N2 stock condition tables and writer are not ready for full pass-through.

Missing fields by N2 table:
- `stock_condition_basis`: cash_realization_rate, revenue_yoy_pct, core_profit_yoy_pct, report_core_revenue, report_core_profit, core_profit_ttm, core_gt_revenue_yoy, revenue_growth_streak_q, core_growth_streak_q, core_gt_revenue_streak_q, forecast_type, forecast_score, score_breakdown_json, financial_warning_json, financial_metric_version
- `stock_condition_pool`: cash_realization_rate, pe_core, revenue_yoy_pct, core_profit_yoy_pct, report_core_revenue, report_core_profit, core_profit_ttm, core_gt_revenue_yoy, revenue_growth_streak_q, core_growth_streak_q, core_gt_revenue_streak_q, forecast_type, forecast_score, score, score_breakdown_json, financial_warning_json, financial_metric_version
- `stock_minute_target_scope`: cash_realization_rate, pe_core, revenue_yoy_pct, core_profit_yoy_pct, report_core_revenue, report_core_profit, core_profit_ttm, core_gt_revenue_yoy, revenue_growth_streak_q, core_growth_streak_q, core_gt_revenue_streak_q, forecast_type, forecast_score, score, score_breakdown_json, financial_warning_json, financial_metric_version
- `stock_condition_display_basis`: cash_realization_rate, revenue_yoy_pct, core_profit_yoy_pct, report_core_revenue, report_core_profit, core_profit_ttm, core_gt_revenue_yoy, revenue_growth_streak_q, core_growth_streak_q, core_gt_revenue_streak_q, forecast_type, forecast_score, score_breakdown_json, financial_warning_json, financial_metric_version

Current N2 basis dry-run reads active `stock_financial_20260529_v2`, but only carries `pe_core` and `score`; the other canonical financial fields are absent from basis rows, so execute is blocked.

## Dry-Run Counts
- stock_condition_basis: 5506
- index_condition_basis: 83
- board_condition_basis: 428
- stock_condition_pool: 4106
- index_condition_pool: 21
- board_condition_pool: 284
- stock_minute_target_scope: 4106
- index_minute_target_scope: 21
- board_minute_target_scope: 284
- stock_condition_display_basis: 1871
- index_condition_display_basis: 9
- board_condition_display_basis: 127
- common_condition_quality_item: 106
- P0/P1/P2: 0/6/3

## Boundary
- writes_performed=false
- will_execute_sql=false
- minute_kline_pulled=false
- downstream_layers_touched=false
- n3_lineage_auto_switch=false

## Next Required Steps
- 新增 N2 additive migration：stock_condition_basis / stock_condition_pool / stock_minute_target_scope / stock_condition_display_basis 增加 canonical financial 字段。
- 更新 N2 basis SQL：从 active stock_financial_metrics_fact 读取所有 canonical financial 字段；不在 N2 重算。
- 更新 pool/scope/display writer：只透传 basis 字段，policy 若引用 score/pe_core/cash_realization_rate 必须使用 N1 字段。
- 新增/更新测试：字段覆盖、v2 source_version、no recompute、finance-sector/pre-revenue warning 透传、active supersede rollback guard。
- 重新 dry-run / contract / preflight，通过后再请求用户确认 execute。
