-- N2-Display-1 separate migration draft for condition quality layer_scope CHECK.
-- Do not execute without explicit user confirmation.
-- This is intentionally separate from 014 because it changes an existing CHECK.

BEGIN;

DO $$
DECLARE
  constraint_record RECORD;
BEGIN
  FOR constraint_record IN
    SELECT conname
    FROM pg_constraint
    WHERE conrelid = 'common_condition_quality_item'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%layer_scope%'
  LOOP
    EXECUTE format(
      'ALTER TABLE common_condition_quality_item DROP CONSTRAINT IF EXISTS %I',
      constraint_record.conname
    );
  END LOOP;
END $$;

ALTER TABLE common_condition_quality_item
  ADD CONSTRAINT common_condition_quality_item_layer_scope_check
  CHECK (
    layer_scope IN (
      'monitor_target',
      'condition_basis',
      'condition_pool',
      'minute_target_scope',
      'condition_display_basis',
      'condition_run'
    )
  );

COMMIT;
