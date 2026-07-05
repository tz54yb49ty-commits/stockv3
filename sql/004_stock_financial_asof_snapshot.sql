-- A-share monitor v3 stock financial as-of snapshot migration.
-- Boundary: raw-ingestion fact table shape only; no condition calculation.

BEGIN;

ALTER TABLE stock_financial_metrics_fact
  ADD COLUMN IF NOT EXISTS source_trade_date TEXT,
  ADD COLUMN IF NOT EXISTS announcement_date TEXT,
  ADD COLUMN IF NOT EXISTS pe_core NUMERIC,
  ADD COLUMN IF NOT EXISTS total_mv NUMERIC,
  ADD COLUMN IF NOT EXISTS circ_mv NUMERIC,
  ADD COLUMN IF NOT EXISTS score NUMERIC,
  ADD COLUMN IF NOT EXISTS warning TEXT,
  ADD COLUMN IF NOT EXISTS quality_status TEXT DEFAULT 'passed';

UPDATE stock_financial_metrics_fact
SET
  source_trade_date = COALESCE(source_trade_date, asof_date),
  announcement_date = COALESCE(announcement_date, asof_date),
  quality_status = COALESCE(quality_status, 'passed')
WHERE source_trade_date IS NULL
   OR announcement_date IS NULL
   OR quality_status IS NULL;

ALTER TABLE stock_financial_metrics_fact
  ALTER COLUMN source_trade_date SET NOT NULL,
  ALTER COLUMN quality_status SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'chk_stock_financial_source_trade_date'
  ) THEN
    ALTER TABLE stock_financial_metrics_fact
      ADD CONSTRAINT chk_stock_financial_source_trade_date
      CHECK (source_trade_date ~ '^[0-9]{8}$');
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'chk_stock_financial_announcement_date'
  ) THEN
    ALTER TABLE stock_financial_metrics_fact
      ADD CONSTRAINT chk_stock_financial_announcement_date
      CHECK (announcement_date IS NULL OR announcement_date ~ '^[0-9]{8}$');
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'chk_stock_financial_quality_status'
  ) THEN
    ALTER TABLE stock_financial_metrics_fact
      ADD CONSTRAINT chk_stock_financial_quality_status
      CHECK (quality_status IN ('passed', 'warning', 'failed'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_stock_financial_source_trade_date
ON stock_financial_metrics_fact(source_trade_date);

CREATE INDEX IF NOT EXISTS idx_stock_financial_source_trade_version
ON stock_financial_metrics_fact(source_trade_date, source_version);

COMMIT;
