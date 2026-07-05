-- N2 symmetry target price canonical compatibility migration draft.
-- Do not execute without explicit user confirmation.
--
-- Scope:
--   stock/index/board condition_basis
--   stock/index/board condition_pool
--   stock/index/board minute_target_scope
--   stock/index/board condition_display_basis
--
-- Boundary:
--   schema-only DDL draft
--   no INSERT / UPDATE / DELETE
--   no business row backfill
--   no N1/N3/N4/N5/N6 changes
--   no locked_target_price / target_lock_status

BEGIN;

DO $$
DECLARE
  t text;
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
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS symmetry_anchor TEXT', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS secondary_symmetry_anchor TEXT', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS amplitude_source_period TEXT', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS a_segment_start_date TEXT', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS a_segment_end_date TEXT', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS a_segment_high NUMERIC', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS a_segment_low NUMERIC', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS a_segment_amplitude NUMERIC', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS base_price_policy TEXT', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS base_price NUMERIC', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS reference_target_price NUMERIC', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS secondary_target_price NUMERIC', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS target_price_trace_json JSONB', t);

    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_symmetry_anchor_check');
    EXECUTE format(
      'ALTER TABLE %I ADD CONSTRAINT %I CHECK (symmetry_anchor IS NULL OR symmetry_anchor IN (''Y'', ''Q'', ''M'', ''W''))',
      t,
      t || '_symmetry_anchor_check'
    );

    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_secondary_symmetry_anchor_check');
    EXECUTE format(
      'ALTER TABLE %I ADD CONSTRAINT %I CHECK (secondary_symmetry_anchor IS NULL OR secondary_symmetry_anchor IN (''Y'', ''Q'', ''M'', ''W''))',
      t,
      t || '_secondary_symmetry_anchor_check'
    );

    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_amplitude_source_period_check');
    EXECUTE format(
      'ALTER TABLE %I ADD CONSTRAINT %I CHECK (amplitude_source_period IS NULL OR amplitude_source_period IN (''Y'', ''Q'', ''M'', ''W''))',
      t,
      t || '_amplitude_source_period_check'
    );

    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_a_segment_start_date_check');
    EXECUTE format(
      'ALTER TABLE %I ADD CONSTRAINT %I CHECK (a_segment_start_date IS NULL OR a_segment_start_date ~ ''^[0-9]{8}$'')',
      t,
      t || '_a_segment_start_date_check'
    );

    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_a_segment_end_date_check');
    EXECUTE format(
      'ALTER TABLE %I ADD CONSTRAINT %I CHECK (a_segment_end_date IS NULL OR a_segment_end_date ~ ''^[0-9]{8}$'')',
      t,
      t || '_a_segment_end_date_check'
    );

    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_a_segment_high_check');
    EXECUTE format(
      'ALTER TABLE %I ADD CONSTRAINT %I CHECK (a_segment_high IS NULL OR a_segment_high >= 0)',
      t,
      t || '_a_segment_high_check'
    );

    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_a_segment_low_check');
    EXECUTE format(
      'ALTER TABLE %I ADD CONSTRAINT %I CHECK (a_segment_low IS NULL OR a_segment_low >= 0)',
      t,
      t || '_a_segment_low_check'
    );

    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_a_segment_amplitude_check');
    EXECUTE format(
      'ALTER TABLE %I ADD CONSTRAINT %I CHECK (a_segment_amplitude IS NULL OR a_segment_amplitude >= 0)',
      t,
      t || '_a_segment_amplitude_check'
    );

    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_base_price_policy_check');
    EXECUTE format(
      'ALTER TABLE %I ADD CONSTRAINT %I CHECK (base_price_policy IS NULL OR base_price_policy = ''MIN_CLOSE_AFTER_LAST_LOWER_UP_SEGMENT_PLUS_TRIGGER_OPEN'')',
      t,
      t || '_base_price_policy_check'
    );

    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_base_price_check');
    EXECUTE format(
      'ALTER TABLE %I ADD CONSTRAINT %I CHECK (base_price IS NULL OR base_price >= 0)',
      t,
      t || '_base_price_check'
    );

    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_reference_target_price_check');
    EXECUTE format(
      'ALTER TABLE %I ADD CONSTRAINT %I CHECK (reference_target_price IS NULL OR reference_target_price >= 0)',
      t,
      t || '_reference_target_price_check'
    );

    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_secondary_target_price_check');
    EXECUTE format(
      'ALTER TABLE %I ADD CONSTRAINT %I CHECK (secondary_target_price IS NULL OR secondary_target_price >= 0)',
      t,
      t || '_secondary_target_price_check'
    );

    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_target_price_trace_json_check');
    EXECUTE format(
      'ALTER TABLE %I ADD CONSTRAINT %I CHECK (target_price_trace_json IS NULL OR jsonb_typeof(target_price_trace_json) = ''object'')',
      t,
      t || '_target_price_trace_json_check'
    );
  END LOOP;
END $$;

COMMIT;
