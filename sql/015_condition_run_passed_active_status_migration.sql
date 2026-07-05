-- N2 condition run active-status migration.
-- Purpose: allow canonical active runs to use status='passed_active' while
-- keeping legacy status='passed' readable.
-- Boundary: schema only; no condition business data writes.

BEGIN;

ALTER TABLE common_condition_run
  DROP CONSTRAINT IF EXISTS common_condition_run_status_check;

ALTER TABLE common_condition_run
  ADD CONSTRAINT common_condition_run_status_check
  CHECK (
    status IN (
      'planned',
      'running',
      'passed',
      'passed_active',
      'failed',
      'blocked',
      'superseded',
      'rolled_back'
    )
  );

CREATE UNIQUE INDEX IF NOT EXISTS ux_common_condition_run_one_passed_active
ON common_condition_run(source_trade_date, for_trade_date)
WHERE status = 'passed_active';

COMMIT;
