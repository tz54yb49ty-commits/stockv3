-- N2-R4 additive migration draft: period trigger baseline across basis/pool/scope.
-- Do not execute without explicit user confirmation.
-- Additive only: no UPDATE / INSERT / DELETE / overwrite / constraint enforcement.

BEGIN;

ALTER TABLE stock_condition_basis
  ADD COLUMN IF NOT EXISTS period_trigger_baseline_json JSONB;

ALTER TABLE index_condition_basis
  ADD COLUMN IF NOT EXISTS period_trigger_baseline_json JSONB;

ALTER TABLE board_condition_basis
  ADD COLUMN IF NOT EXISTS period_trigger_baseline_json JSONB;

ALTER TABLE stock_condition_pool
  ADD COLUMN IF NOT EXISTS period_trigger_baseline_json JSONB;

ALTER TABLE index_condition_pool
  ADD COLUMN IF NOT EXISTS period_trigger_baseline_json JSONB;

ALTER TABLE board_condition_pool
  ADD COLUMN IF NOT EXISTS period_trigger_baseline_json JSONB;

ALTER TABLE stock_minute_target_scope
  ADD COLUMN IF NOT EXISTS period_trigger_baseline_json JSONB;

ALTER TABLE index_minute_target_scope
  ADD COLUMN IF NOT EXISTS period_trigger_baseline_json JSONB;

ALTER TABLE board_minute_target_scope
  ADD COLUMN IF NOT EXISTS period_trigger_baseline_json JSONB;

-- Deferred until after overwrite validation:
--   NOT NULL constraints.
--   JSON shape checks.
--   Backfill for old active runs.

COMMIT;
