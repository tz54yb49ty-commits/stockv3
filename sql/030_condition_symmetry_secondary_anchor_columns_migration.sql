-- N2 symmetry secondary-anchor explicit columns migration draft.
-- Do not execute without explicit user confirmation.
--
-- Scope:
--   stock/index/board condition_basis
--   stock/index/board condition_pool
--   stock/index/board minute_target_scope
--   stock/index/board condition_display_basis
--
-- Boundary:
--   schema-only additive DDL draft
--   no INSERT / UPDATE / DELETE / TRUNCATE / COPY
--   no business row backfill
--   no N1/N3/N4/N5/N6 changes
--   no locked_target_price / target_lock_status

BEGIN;

DO $$
DECLARE
  t text;
  numeric_field text;
  date_field text;
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
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS up_secondary_anchor TEXT', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS up_secondary_reference_period TEXT', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS up_secondary_trend_start_date TEXT', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS up_secondary_trend_end_date TEXT', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS up_secondary_amplitude NUMERIC', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS up_secondary_base_price NUMERIC', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS up_secondary_target_price NUMERIC', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS up_secondary_expected_return_pct NUMERIC', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS down_secondary_anchor TEXT', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS down_secondary_reference_period TEXT', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS down_secondary_trend_start_date TEXT', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS down_secondary_trend_end_date TEXT', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS down_secondary_amplitude NUMERIC', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS down_secondary_base_price NUMERIC', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS down_secondary_target_price NUMERIC', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS down_secondary_expected_return_pct NUMERIC', t);

    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_up_secondary_anchor_check');
    EXECUTE format(
      'ALTER TABLE %I ADD CONSTRAINT %I CHECK (up_secondary_anchor IS NULL OR up_secondary_anchor IN (''Y'', ''Q'', ''M'', ''W''))',
      t,
      t || '_up_secondary_anchor_check'
    );
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_down_secondary_anchor_check');
    EXECUTE format(
      'ALTER TABLE %I ADD CONSTRAINT %I CHECK (down_secondary_anchor IS NULL OR down_secondary_anchor IN (''Y'', ''Q'', ''M'', ''W''))',
      t,
      t || '_down_secondary_anchor_check'
    );
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_up_secondary_reference_period_check');
    EXECUTE format(
      'ALTER TABLE %I ADD CONSTRAINT %I CHECK (up_secondary_reference_period IS NULL OR up_secondary_reference_period IN (''Q'', ''M'', ''W'', ''D''))',
      t,
      t || '_up_secondary_reference_period_check'
    );
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_down_secondary_reference_period_check');
    EXECUTE format(
      'ALTER TABLE %I ADD CONSTRAINT %I CHECK (down_secondary_reference_period IS NULL OR down_secondary_reference_period IN (''Q'', ''M'', ''W'', ''D''))',
      t,
      t || '_down_secondary_reference_period_check'
    );

    FOREACH date_field IN ARRAY ARRAY[
      'up_secondary_trend_start_date',
      'up_secondary_trend_end_date',
      'down_secondary_trend_start_date',
      'down_secondary_trend_end_date'
    ]
    LOOP
      EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_' || date_field || '_check');
      EXECUTE format(
        'ALTER TABLE %I ADD CONSTRAINT %I CHECK (%I IS NULL OR %I ~ ''^[0-9]{8}$'')',
        t,
        t || '_' || date_field || '_check',
        date_field,
        date_field
      );
    END LOOP;

    FOREACH numeric_field IN ARRAY ARRAY[
      'up_secondary_amplitude',
      'up_secondary_base_price',
      'up_secondary_target_price',
      'down_secondary_amplitude',
      'down_secondary_base_price',
      'down_secondary_target_price'
    ]
    LOOP
      EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_' || numeric_field || '_check');
      EXECUTE format(
        'ALTER TABLE %I ADD CONSTRAINT %I CHECK (%I IS NULL OR %I >= 0)',
        t,
        t || '_' || numeric_field || '_check',
        numeric_field,
        numeric_field
      );
    END LOOP;
  END LOOP;
END $$;

COMMIT;
