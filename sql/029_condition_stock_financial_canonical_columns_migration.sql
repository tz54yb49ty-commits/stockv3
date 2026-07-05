-- N2 stock financial canonical pass-through schema draft.
-- Layer: N2_condition.
-- Scope: additive nullable columns for stock N2 tables only.
-- Boundary: no DML, no backfill, no N1/N3/N4/N5/N6 writes.
-- Do not execute without an explicit schema migration final gate.

BEGIN;

ALTER TABLE stock_condition_basis
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

ALTER TABLE stock_condition_pool
  ADD COLUMN IF NOT EXISTS pe_core NUMERIC,
  ADD COLUMN IF NOT EXISTS score NUMERIC,
  ADD COLUMN IF NOT EXISTS financial_quality_status TEXT,
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

ALTER TABLE stock_minute_target_scope
  ADD COLUMN IF NOT EXISTS pe_core NUMERIC,
  ADD COLUMN IF NOT EXISTS score NUMERIC,
  ADD COLUMN IF NOT EXISTS financial_quality_status TEXT,
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

ALTER TABLE stock_condition_display_basis
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

COMMIT;
