-- 028 stock financial canonical metrics schema draft.
-- Layer: N1_ingestion.
-- Boundary: schema-only additive draft for stock_financial_metrics_fact.
-- Do not run without explicit migration final gate.

BEGIN;

ALTER TABLE stock_financial_metrics_fact
  ADD COLUMN IF NOT EXISTS cash_realization_rate NUMERIC,
  ADD COLUMN IF NOT EXISTS revenue_yoy_pct NUMERIC,
  ADD COLUMN IF NOT EXISTS core_profit_yoy_pct NUMERIC,
  ADD COLUMN IF NOT EXISTS report_core_revenue NUMERIC,
  ADD COLUMN IF NOT EXISTS report_core_profit NUMERIC,
  ADD COLUMN IF NOT EXISTS core_profit_ttm NUMERIC,
  ADD COLUMN IF NOT EXISTS core_gt_revenue_yoy BOOLEAN,
  ADD COLUMN IF NOT EXISTS revenue_growth_streak_q INTEGER,
  ADD COLUMN IF NOT EXISTS core_growth_streak_q INTEGER,
  ADD COLUMN IF NOT EXISTS core_gt_revenue_streak_q INTEGER,
  ADD COLUMN IF NOT EXISTS forecast_type TEXT,
  ADD COLUMN IF NOT EXISTS forecast_score NUMERIC,
  ADD COLUMN IF NOT EXISTS score_breakdown_json JSONB,
  ADD COLUMN IF NOT EXISTS financial_warning_json JSONB,
  ADD COLUMN IF NOT EXISTS financial_metric_version TEXT;

ALTER TABLE stock_financial_metrics_fact
  DROP CONSTRAINT IF EXISTS chk_stock_financial_score_028;
ALTER TABLE stock_financial_metrics_fact
  ADD CONSTRAINT chk_stock_financial_score_028
  CHECK (score IS NULL OR (score >= 0 AND score <= 100)) NOT VALID;

ALTER TABLE stock_financial_metrics_fact
  DROP CONSTRAINT IF EXISTS chk_stock_financial_forecast_score_028;
ALTER TABLE stock_financial_metrics_fact
  ADD CONSTRAINT chk_stock_financial_forecast_score_028
  CHECK (forecast_score IS NULL OR (forecast_score >= 0 AND forecast_score <= 3)) NOT VALID;

ALTER TABLE stock_financial_metrics_fact
  DROP CONSTRAINT IF EXISTS chk_stock_financial_revenue_growth_streak_q_028;
ALTER TABLE stock_financial_metrics_fact
  ADD CONSTRAINT chk_stock_financial_revenue_growth_streak_q_028
  CHECK (revenue_growth_streak_q IS NULL OR revenue_growth_streak_q >= 0) NOT VALID;

ALTER TABLE stock_financial_metrics_fact
  DROP CONSTRAINT IF EXISTS chk_stock_financial_core_growth_streak_q_028;
ALTER TABLE stock_financial_metrics_fact
  ADD CONSTRAINT chk_stock_financial_core_growth_streak_q_028
  CHECK (core_growth_streak_q IS NULL OR core_growth_streak_q >= 0) NOT VALID;

ALTER TABLE stock_financial_metrics_fact
  DROP CONSTRAINT IF EXISTS chk_stock_financial_core_gt_revenue_streak_q_028;
ALTER TABLE stock_financial_metrics_fact
  ADD CONSTRAINT chk_stock_financial_core_gt_revenue_streak_q_028
  CHECK (core_gt_revenue_streak_q IS NULL OR core_gt_revenue_streak_q >= 0) NOT VALID;

ALTER TABLE stock_financial_metrics_fact
  DROP CONSTRAINT IF EXISTS chk_stock_financial_asof_no_future_028;
ALTER TABLE stock_financial_metrics_fact
  ADD CONSTRAINT chk_stock_financial_asof_no_future_028
  CHECK (announcement_date IS NULL OR announcement_date <= source_trade_date) NOT VALID;

ALTER TABLE stock_financial_metrics_fact
  DROP CONSTRAINT IF EXISTS chk_stock_financial_metric_version_028;
ALTER TABLE stock_financial_metrics_fact
  ADD CONSTRAINT chk_stock_financial_metric_version_028
  CHECK (financial_metric_version IS NULL OR financial_metric_version IN ('financial_metric_v1')) NOT VALID;

ALTER TABLE stock_financial_metrics_fact
  DROP CONSTRAINT IF EXISTS chk_stock_financial_score_breakdown_json_028;
ALTER TABLE stock_financial_metrics_fact
  ADD CONSTRAINT chk_stock_financial_score_breakdown_json_028
  CHECK (score_breakdown_json IS NULL OR jsonb_typeof(score_breakdown_json) = 'object') NOT VALID;

ALTER TABLE stock_financial_metrics_fact
  DROP CONSTRAINT IF EXISTS chk_stock_financial_warning_json_028;
ALTER TABLE stock_financial_metrics_fact
  ADD CONSTRAINT chk_stock_financial_warning_json_028
  CHECK (financial_warning_json IS NULL OR jsonb_typeof(financial_warning_json) = 'object') NOT VALID;

CREATE INDEX IF NOT EXISTS idx_stock_financial_metric_version_028
ON stock_financial_metrics_fact(financial_metric_version);

CREATE INDEX IF NOT EXISTS idx_stock_financial_report_period_028
ON stock_financial_metrics_fact(report_period);

COMMIT;
