-- Rollback for N2 condition run active-status migration.
-- This rollback is guarded: it refuses to remove passed_active support while
-- any rows still use status='passed_active'.

BEGIN;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM common_condition_run
    WHERE status = 'passed_active'
    LIMIT 1
  ) THEN
    RAISE EXCEPTION 'cannot rollback 015: common_condition_run contains passed_active rows';
  END IF;
END $$;

DROP INDEX IF EXISTS ux_common_condition_run_one_passed_active;

ALTER TABLE common_condition_run
  DROP CONSTRAINT IF EXISTS common_condition_run_status_check;

ALTER TABLE common_condition_run
  ADD CONSTRAINT common_condition_run_status_check
  CHECK (
    status IN (
      'planned',
      'running',
      'passed',
      'failed',
      'blocked',
      'superseded',
      'rolled_back'
    )
  );

COMMIT;
