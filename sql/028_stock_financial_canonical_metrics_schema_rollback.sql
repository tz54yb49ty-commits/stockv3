-- Rollback draft for 028 stock financial canonical metrics schema.
-- Layer: N1_ingestion.
-- Drops only constraints, indexes, and nullable fields introduced by 028.
-- Do not run without explicit rollback final gate.

BEGIN;

DROP INDEX IF EXISTS idx_stock_financial_report_period_028;
DROP INDEX IF EXISTS idx_stock_financial_metric_version_028;

ALTER TABLE stock_financial_metrics_fact
  DROP CONSTRAINT IF EXISTS chk_stock_financial_warning_json_028,
  DROP CONSTRAINT IF EXISTS chk_stock_financial_score_breakdown_json_028,
  DROP CONSTRAINT IF EXISTS chk_stock_financial_metric_version_028,
  DROP CONSTRAINT IF EXISTS chk_stock_financial_asof_no_future_028,
  DROP CONSTRAINT IF EXISTS chk_stock_financial_core_gt_revenue_streak_q_028,
  DROP CONSTRAINT IF EXISTS chk_stock_financial_core_growth_streak_q_028,
  DROP CONSTRAINT IF EXISTS chk_stock_financial_revenue_growth_streak_q_028,
  DROP CONSTRAINT IF EXISTS chk_stock_financial_forecast_score_028,
  DROP CONSTRAINT IF EXISTS chk_stock_financial_score_028,
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
