-- N2 stock financial canonical pass-through schema rollback draft.
-- Layer: N2_condition.
-- Scope: remove only columns introduced for stock financial pass-through.
-- Review downstream compatibility before running. This rollback performs no DML.

BEGIN;

ALTER TABLE stock_condition_display_basis
  DROP COLUMN IF EXISTS financial_metric_version,
  DROP COLUMN IF EXISTS financial_warning_json,
  DROP COLUMN IF EXISTS score_breakdown_json,
  DROP COLUMN IF EXISTS forecast_score,
  DROP COLUMN IF EXISTS forecast_type,
  DROP COLUMN IF EXISTS core_gt_revenue_streak_q,
  DROP COLUMN IF EXISTS core_growth_streak_q,
  DROP COLUMN IF EXISTS revenue_growth_streak_q,
  DROP COLUMN IF EXISTS core_gt_revenue_yoy,
  DROP COLUMN IF EXISTS core_profit_ttm,
  DROP COLUMN IF EXISTS report_core_profit,
  DROP COLUMN IF EXISTS report_core_revenue,
  DROP COLUMN IF EXISTS core_profit_yoy_pct,
  DROP COLUMN IF EXISTS revenue_yoy_pct,
  DROP COLUMN IF EXISTS cash_realization_rate;

ALTER TABLE stock_minute_target_scope
  DROP COLUMN IF EXISTS financial_metric_version,
  DROP COLUMN IF EXISTS financial_warning_json,
  DROP COLUMN IF EXISTS score_breakdown_json,
  DROP COLUMN IF EXISTS forecast_score,
  DROP COLUMN IF EXISTS forecast_type,
  DROP COLUMN IF EXISTS core_gt_revenue_streak_q,
  DROP COLUMN IF EXISTS core_growth_streak_q,
  DROP COLUMN IF EXISTS revenue_growth_streak_q,
  DROP COLUMN IF EXISTS core_gt_revenue_yoy,
  DROP COLUMN IF EXISTS core_profit_ttm,
  DROP COLUMN IF EXISTS report_core_profit,
  DROP COLUMN IF EXISTS report_core_revenue,
  DROP COLUMN IF EXISTS core_profit_yoy_pct,
  DROP COLUMN IF EXISTS revenue_yoy_pct,
  DROP COLUMN IF EXISTS cash_realization_rate,
  DROP COLUMN IF EXISTS financial_quality_status,
  DROP COLUMN IF EXISTS score,
  DROP COLUMN IF EXISTS pe_core;

ALTER TABLE stock_condition_pool
  DROP COLUMN IF EXISTS financial_metric_version,
  DROP COLUMN IF EXISTS financial_warning_json,
  DROP COLUMN IF EXISTS score_breakdown_json,
  DROP COLUMN IF EXISTS forecast_score,
  DROP COLUMN IF EXISTS forecast_type,
  DROP COLUMN IF EXISTS core_gt_revenue_streak_q,
  DROP COLUMN IF EXISTS core_growth_streak_q,
  DROP COLUMN IF EXISTS revenue_growth_streak_q,
  DROP COLUMN IF EXISTS core_gt_revenue_yoy,
  DROP COLUMN IF EXISTS core_profit_ttm,
  DROP COLUMN IF EXISTS report_core_profit,
  DROP COLUMN IF EXISTS report_core_revenue,
  DROP COLUMN IF EXISTS core_profit_yoy_pct,
  DROP COLUMN IF EXISTS revenue_yoy_pct,
  DROP COLUMN IF EXISTS cash_realization_rate,
  DROP COLUMN IF EXISTS financial_quality_status,
  DROP COLUMN IF EXISTS score,
  DROP COLUMN IF EXISTS pe_core;

ALTER TABLE stock_condition_basis
  DROP COLUMN IF EXISTS financial_metric_version,
  DROP COLUMN IF EXISTS financial_warning_json,
  DROP COLUMN IF EXISTS score_breakdown_json,
  DROP COLUMN IF EXISTS forecast_score,
  DROP COLUMN IF EXISTS forecast_type,
  DROP COLUMN IF EXISTS core_gt_revenue_streak_q,
  DROP COLUMN IF EXISTS core_growth_streak_q,
  DROP COLUMN IF EXISTS revenue_growth_streak_q,
  DROP COLUMN IF EXISTS core_gt_revenue_yoy,
  DROP COLUMN IF EXISTS core_profit_ttm,
  DROP COLUMN IF EXISTS report_core_profit,
  DROP COLUMN IF EXISTS report_core_revenue,
  DROP COLUMN IF EXISTS core_profit_yoy_pct,
  DROP COLUMN IF EXISTS revenue_yoy_pct,
  DROP COLUMN IF EXISTS cash_realization_rate;

COMMIT;
