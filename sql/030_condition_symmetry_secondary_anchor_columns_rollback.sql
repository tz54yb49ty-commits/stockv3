-- Roll back N2 symmetry secondary-anchor explicit columns migration draft.
-- Do not execute without explicit user confirmation.
--
-- Scope:
--   drop only 030-added columns and constraints
--   no business row cleanup
--   no N1/N3/N4/N5/N6 changes

BEGIN;

DO $$
DECLARE
  t text;
  field text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'stock_condition_basis',
    'index_condition_basis',
    'board_condition_basis',
    'stock_condition_pool',
    'index_condition_pool',
    'board_condition_pool',
    'stock_minute_target_scope',
    'index_minute_target_scope',
    'board_minute_target_scope',
    'stock_condition_display_basis',
    'index_condition_display_basis',
    'board_condition_display_basis'
  ]
  LOOP
    FOREACH field IN ARRAY ARRAY[
      'up_secondary_anchor',
      'up_secondary_reference_period',
      'up_secondary_trend_start_date',
      'up_secondary_trend_end_date',
      'up_secondary_amplitude',
      'up_secondary_base_price',
      'up_secondary_target_price',
      'down_secondary_anchor',
      'down_secondary_reference_period',
      'down_secondary_trend_start_date',
      'down_secondary_trend_end_date',
      'down_secondary_amplitude',
      'down_secondary_base_price',
      'down_secondary_target_price'
    ]
    LOOP
      EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_' || field || '_check');
    END LOOP;

    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS down_secondary_expected_return_pct', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS down_secondary_target_price', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS down_secondary_base_price', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS down_secondary_amplitude', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS down_secondary_trend_end_date', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS down_secondary_trend_start_date', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS down_secondary_reference_period', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS down_secondary_anchor', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS up_secondary_expected_return_pct', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS up_secondary_target_price', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS up_secondary_base_price', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS up_secondary_amplitude', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS up_secondary_trend_end_date', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS up_secondary_trend_start_date', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS up_secondary_reference_period', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS up_secondary_anchor', t);
  END LOOP;
END $$;

COMMIT;
