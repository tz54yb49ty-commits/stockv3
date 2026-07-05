-- Rollback draft for N2 level_up_score / level_down_score additive columns.
-- Scope: drop only the columns added by 031 from N2 condition tables.
-- Boundary: DDL only; no business row cleanup; not executed in this gate.

BEGIN;

ALTER TABLE stock_condition_basis
  DROP COLUMN IF EXISTS level_up_score,
  DROP COLUMN IF EXISTS level_down_score;

ALTER TABLE index_condition_basis
  DROP COLUMN IF EXISTS level_up_score,
  DROP COLUMN IF EXISTS level_down_score;

ALTER TABLE board_condition_basis
  DROP COLUMN IF EXISTS level_up_score,
  DROP COLUMN IF EXISTS level_down_score;

ALTER TABLE stock_condition_pool
  DROP COLUMN IF EXISTS level_up_score,
  DROP COLUMN IF EXISTS level_down_score;

ALTER TABLE index_condition_pool
  DROP COLUMN IF EXISTS level_up_score,
  DROP COLUMN IF EXISTS level_down_score;

ALTER TABLE board_condition_pool
  DROP COLUMN IF EXISTS level_up_score,
  DROP COLUMN IF EXISTS level_down_score;

ALTER TABLE stock_minute_target_scope
  DROP COLUMN IF EXISTS level_up_score,
  DROP COLUMN IF EXISTS level_down_score;

ALTER TABLE index_minute_target_scope
  DROP COLUMN IF EXISTS level_up_score,
  DROP COLUMN IF EXISTS level_down_score;

ALTER TABLE board_minute_target_scope
  DROP COLUMN IF EXISTS level_up_score,
  DROP COLUMN IF EXISTS level_down_score;

ALTER TABLE stock_condition_display_basis
  DROP COLUMN IF EXISTS level_up_score,
  DROP COLUMN IF EXISTS level_down_score;

ALTER TABLE index_condition_display_basis
  DROP COLUMN IF EXISTS level_up_score,
  DROP COLUMN IF EXISTS level_down_score;

ALTER TABLE board_condition_display_basis
  DROP COLUMN IF EXISTS level_up_score,
  DROP COLUMN IF EXISTS level_down_score;

COMMIT;
