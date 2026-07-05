-- N2 level_up_score / level_down_score additive schema draft.
-- Scope: N2 condition_basis / condition_pool / minute_target_scope / condition_display_basis
--        for stock / index / board only.
-- Boundary: DDL only; no INSERT / UPDATE / DELETE / backfill; not executed in this gate.

BEGIN;

ALTER TABLE stock_condition_basis
  ADD COLUMN IF NOT EXISTS level_up_score INTEGER CHECK (level_up_score IS NULL OR (level_up_score >= 0 AND level_up_score <= 3124)),
  ADD COLUMN IF NOT EXISTS level_down_score INTEGER CHECK (level_down_score IS NULL OR (level_down_score >= 0 AND level_down_score <= 3124));

ALTER TABLE index_condition_basis
  ADD COLUMN IF NOT EXISTS level_up_score INTEGER CHECK (level_up_score IS NULL OR (level_up_score >= 0 AND level_up_score <= 3124)),
  ADD COLUMN IF NOT EXISTS level_down_score INTEGER CHECK (level_down_score IS NULL OR (level_down_score >= 0 AND level_down_score <= 3124));

ALTER TABLE board_condition_basis
  ADD COLUMN IF NOT EXISTS level_up_score INTEGER CHECK (level_up_score IS NULL OR (level_up_score >= 0 AND level_up_score <= 3124)),
  ADD COLUMN IF NOT EXISTS level_down_score INTEGER CHECK (level_down_score IS NULL OR (level_down_score >= 0 AND level_down_score <= 3124));

ALTER TABLE stock_condition_pool
  ADD COLUMN IF NOT EXISTS level_up_score INTEGER CHECK (level_up_score IS NULL OR (level_up_score >= 0 AND level_up_score <= 3124)),
  ADD COLUMN IF NOT EXISTS level_down_score INTEGER CHECK (level_down_score IS NULL OR (level_down_score >= 0 AND level_down_score <= 3124));

ALTER TABLE index_condition_pool
  ADD COLUMN IF NOT EXISTS level_up_score INTEGER CHECK (level_up_score IS NULL OR (level_up_score >= 0 AND level_up_score <= 3124)),
  ADD COLUMN IF NOT EXISTS level_down_score INTEGER CHECK (level_down_score IS NULL OR (level_down_score >= 0 AND level_down_score <= 3124));

ALTER TABLE board_condition_pool
  ADD COLUMN IF NOT EXISTS level_up_score INTEGER CHECK (level_up_score IS NULL OR (level_up_score >= 0 AND level_up_score <= 3124)),
  ADD COLUMN IF NOT EXISTS level_down_score INTEGER CHECK (level_down_score IS NULL OR (level_down_score >= 0 AND level_down_score <= 3124));

ALTER TABLE stock_minute_target_scope
  ADD COLUMN IF NOT EXISTS level_up_score INTEGER CHECK (level_up_score IS NULL OR (level_up_score >= 0 AND level_up_score <= 3124)),
  ADD COLUMN IF NOT EXISTS level_down_score INTEGER CHECK (level_down_score IS NULL OR (level_down_score >= 0 AND level_down_score <= 3124));

ALTER TABLE index_minute_target_scope
  ADD COLUMN IF NOT EXISTS level_up_score INTEGER CHECK (level_up_score IS NULL OR (level_up_score >= 0 AND level_up_score <= 3124)),
  ADD COLUMN IF NOT EXISTS level_down_score INTEGER CHECK (level_down_score IS NULL OR (level_down_score >= 0 AND level_down_score <= 3124));

ALTER TABLE board_minute_target_scope
  ADD COLUMN IF NOT EXISTS level_up_score INTEGER CHECK (level_up_score IS NULL OR (level_up_score >= 0 AND level_up_score <= 3124)),
  ADD COLUMN IF NOT EXISTS level_down_score INTEGER CHECK (level_down_score IS NULL OR (level_down_score >= 0 AND level_down_score <= 3124));

ALTER TABLE stock_condition_display_basis
  ADD COLUMN IF NOT EXISTS level_up_score INTEGER CHECK (level_up_score IS NULL OR (level_up_score >= 0 AND level_up_score <= 3124)),
  ADD COLUMN IF NOT EXISTS level_down_score INTEGER CHECK (level_down_score IS NULL OR (level_down_score >= 0 AND level_down_score <= 3124));

ALTER TABLE index_condition_display_basis
  ADD COLUMN IF NOT EXISTS level_up_score INTEGER CHECK (level_up_score IS NULL OR (level_up_score >= 0 AND level_up_score <= 3124)),
  ADD COLUMN IF NOT EXISTS level_down_score INTEGER CHECK (level_down_score IS NULL OR (level_down_score >= 0 AND level_down_score <= 3124));

ALTER TABLE board_condition_display_basis
  ADD COLUMN IF NOT EXISTS level_up_score INTEGER CHECK (level_up_score IS NULL OR (level_up_score >= 0 AND level_up_score <= 3124)),
  ADD COLUMN IF NOT EXISTS level_down_score INTEGER CHECK (level_down_score IS NULL OR (level_down_score >= 0 AND level_down_score <= 3124));

COMMIT;
