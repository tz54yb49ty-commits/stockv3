-- N2-R2 additive migration draft: static reference periods.
-- Do not execute without explicit user confirmation.
-- Adds canonical N2 reference period fields and keeps clear_sell_ref_period as legacy alias.

BEGIN;

ALTER TABLE stock_condition_basis
  ADD COLUMN IF NOT EXISTS up_sell_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS down_buy_reference_period TEXT;

ALTER TABLE index_condition_basis
  ADD COLUMN IF NOT EXISTS up_sell_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS down_buy_reference_period TEXT;

ALTER TABLE board_condition_basis
  ADD COLUMN IF NOT EXISTS up_sell_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS down_buy_reference_period TEXT;

ALTER TABLE stock_condition_pool
  ADD COLUMN IF NOT EXISTS up_sell_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS down_buy_reference_period TEXT;

-- Deferred after backfill / overwrite validation:
--   NOT NULL checks for up_sell_reference_period and down_buy_reference_period.
--   CHECK constraints limiting values to Y/Q/M/W/D.
--   Compatibility validation: clear_sell_ref_period = up_sell_reference_period.

COMMIT;
