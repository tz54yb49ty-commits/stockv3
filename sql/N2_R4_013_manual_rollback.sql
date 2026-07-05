-- N2-R4 013 manual rollback.
-- Do not execute without explicit user confirmation.
-- This drops the additive period_trigger_baseline_json column from the 9 N2 tables.
-- It should only be used before any dependent overwrite/run relies on this field.

BEGIN;

ALTER TABLE stock_condition_basis
  DROP COLUMN IF EXISTS period_trigger_baseline_json;

ALTER TABLE index_condition_basis
  DROP COLUMN IF EXISTS period_trigger_baseline_json;

ALTER TABLE board_condition_basis
  DROP COLUMN IF EXISTS period_trigger_baseline_json;

ALTER TABLE stock_condition_pool
  DROP COLUMN IF EXISTS period_trigger_baseline_json;

ALTER TABLE index_condition_pool
  DROP COLUMN IF EXISTS period_trigger_baseline_json;

ALTER TABLE board_condition_pool
  DROP COLUMN IF EXISTS period_trigger_baseline_json;

ALTER TABLE stock_minute_target_scope
  DROP COLUMN IF EXISTS period_trigger_baseline_json;

ALTER TABLE index_minute_target_scope
  DROP COLUMN IF EXISTS period_trigger_baseline_json;

ALTER TABLE board_minute_target_scope
  DROP COLUMN IF EXISTS period_trigger_baseline_json;

COMMIT;
