-- A-share monitor v3 condition-layer schema gap migration plan.
-- Stage N2-E6 only: review before running in any PostgreSQL database.
-- This plan is additive: ADD COLUMN IF NOT EXISTS only.
-- It intentionally does not add NOT NULL, DEFAULT, CHECK, FK, DROP, or data backfill.

BEGIN;

ALTER TABLE stock_condition_basis
  ADD COLUMN IF NOT EXISTS is_st BOOLEAN,
  ADD COLUMN IF NOT EXISTS stock_status TEXT,
  ADD COLUMN IF NOT EXISTS official_daily_proof BOOLEAN,
  ADD COLUMN IF NOT EXISTS financial_quality_status TEXT;

ALTER TABLE stock_condition_pool
  ADD COLUMN IF NOT EXISTS policy_name TEXT,
  ADD COLUMN IF NOT EXISTS policy_hash TEXT,
  ADD COLUMN IF NOT EXISTS selected_reason TEXT[],
  ADD COLUMN IF NOT EXISTS excluded_reason TEXT[];

ALTER TABLE index_condition_pool
  ADD COLUMN IF NOT EXISTS policy_name TEXT,
  ADD COLUMN IF NOT EXISTS policy_hash TEXT,
  ADD COLUMN IF NOT EXISTS selected_reason TEXT[],
  ADD COLUMN IF NOT EXISTS excluded_reason TEXT[];

ALTER TABLE board_condition_pool
  ADD COLUMN IF NOT EXISTS policy_name TEXT,
  ADD COLUMN IF NOT EXISTS policy_hash TEXT,
  ADD COLUMN IF NOT EXISTS selected_reason TEXT[],
  ADD COLUMN IF NOT EXISTS excluded_reason TEXT[];

COMMIT;

-- Deferred target-schema constraints/defaults for later review:
-- 1. stock_condition_basis.stock_status target CHECK:
--    stock_status IN ('active', 'delisted', 'paused', 'unknown')
-- 2. stock_condition_basis.financial_quality_status target CHECK:
--    financial_quality_status IS NULL OR financial_quality_status IN ('passed', 'warning', 'failed')
-- 3. condition_pool policy fields target NOT NULL/default behavior is deferred until existing rows are backfilled.
--
-- Rollback note:
-- Additive columns are not automatically dropped. If manual rollback is required,
-- review downstream compatibility first, then run DROP COLUMN commands explicitly.
-- ALTER TABLE stock_condition_basis DROP COLUMN IF EXISTS is_st;
-- ALTER TABLE stock_condition_basis DROP COLUMN IF EXISTS stock_status;
-- ALTER TABLE stock_condition_basis DROP COLUMN IF EXISTS official_daily_proof;
-- ALTER TABLE stock_condition_basis DROP COLUMN IF EXISTS financial_quality_status;
-- ALTER TABLE stock_condition_pool DROP COLUMN IF EXISTS policy_name;
-- ALTER TABLE stock_condition_pool DROP COLUMN IF EXISTS policy_hash;
-- ALTER TABLE stock_condition_pool DROP COLUMN IF EXISTS selected_reason;
-- ALTER TABLE stock_condition_pool DROP COLUMN IF EXISTS excluded_reason;
-- ALTER TABLE index_condition_pool DROP COLUMN IF EXISTS policy_name;
-- ALTER TABLE index_condition_pool DROP COLUMN IF EXISTS policy_hash;
-- ALTER TABLE index_condition_pool DROP COLUMN IF EXISTS selected_reason;
-- ALTER TABLE index_condition_pool DROP COLUMN IF EXISTS excluded_reason;
-- ALTER TABLE board_condition_pool DROP COLUMN IF EXISTS policy_name;
-- ALTER TABLE board_condition_pool DROP COLUMN IF EXISTS policy_hash;
-- ALTER TABLE board_condition_pool DROP COLUMN IF EXISTS selected_reason;
-- ALTER TABLE board_condition_pool DROP COLUMN IF EXISTS excluded_reason;
