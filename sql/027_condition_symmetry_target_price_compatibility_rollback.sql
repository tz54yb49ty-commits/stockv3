-- Rollback draft for sql/027_condition_symmetry_target_price_compatibility_migration.sql.
-- Do not execute unless the 027 migration has been applied and no downstream
-- compatibility work depends on the canonical symmetry target columns.
--
-- Scope:
--   drops only the nullable columns and CHECK constraints added by 027.
--
-- Boundary:
--   schema-only DDL draft
--   no INSERT / UPDATE / DELETE
--   no business row cleanup
--   no N1/N3/N4/N5/N6 changes

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
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_target_price_trace_json_check');
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_secondary_target_price_check');
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_reference_target_price_check');
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_base_price_check');
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_base_price_policy_check');
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_a_segment_amplitude_check');
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_a_segment_low_check');
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_a_segment_high_check');
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_a_segment_end_date_check');
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_a_segment_start_date_check');
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_amplitude_source_period_check');
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_secondary_symmetry_anchor_check');
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', t, t || '_symmetry_anchor_check');

    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS target_price_trace_json', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS secondary_target_price', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS reference_target_price', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS base_price', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS base_price_policy', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS a_segment_amplitude', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS a_segment_low', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS a_segment_high', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS a_segment_end_date', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS a_segment_start_date', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS amplitude_source_period', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS secondary_symmetry_anchor', t);
    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS symmetry_anchor', t);
  END LOOP;
END $$;

COMMIT;
