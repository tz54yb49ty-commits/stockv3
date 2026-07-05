-- N2-R3 additive migration draft: static reference periods across basis/pool/scope.
-- Do not execute without explicit user confirmation.
-- Additive only: no UPDATE / INSERT / DELETE / overwrite / constraint enforcement.

BEGIN;

ALTER TABLE stock_condition_basis
  ADD COLUMN IF NOT EXISTS up_sell_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS down_buy_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS clear_sell_ref_period TEXT;

ALTER TABLE index_condition_basis
  ADD COLUMN IF NOT EXISTS up_sell_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS down_buy_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS clear_sell_ref_period TEXT;

ALTER TABLE board_condition_basis
  ADD COLUMN IF NOT EXISTS up_sell_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS down_buy_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS clear_sell_ref_period TEXT;

ALTER TABLE stock_condition_pool
  ADD COLUMN IF NOT EXISTS up_sell_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS down_buy_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS clear_sell_ref_period TEXT;

ALTER TABLE index_condition_pool
  ADD COLUMN IF NOT EXISTS up_sell_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS down_buy_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS clear_sell_ref_period TEXT;

ALTER TABLE board_condition_pool
  ADD COLUMN IF NOT EXISTS up_sell_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS down_buy_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS clear_sell_ref_period TEXT;

ALTER TABLE stock_minute_target_scope
  ADD COLUMN IF NOT EXISTS up_sell_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS down_buy_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS clear_sell_ref_period TEXT;

ALTER TABLE index_minute_target_scope
  ADD COLUMN IF NOT EXISTS up_sell_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS down_buy_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS clear_sell_ref_period TEXT;

ALTER TABLE board_minute_target_scope
  ADD COLUMN IF NOT EXISTS up_sell_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS down_buy_reference_period TEXT,
  ADD COLUMN IF NOT EXISTS clear_sell_ref_period TEXT;

-- Deferred until after overwrite validation:
--   NOT NULL constraints for up_sell_reference_period / down_buy_reference_period.
--   CHECK constraints limiting values to Y/Q/M/W/D.
--   Compatibility check clear_sell_ref_period = up_sell_reference_period.

COMMIT;
