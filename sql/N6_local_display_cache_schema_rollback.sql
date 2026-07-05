-- A-share monitor v3 N6 local display cache schema rollback.
-- Scope: rollback only the empty N6 local display cache schema created by
-- sql/N6_local_display_cache_schema.sql.

\set ON_ERROR_STOP on

DO $$
DECLARE
  v_table TEXT;
  v_count BIGINT;
  v_total BIGINT := 0;
  v_counts JSONB := '{}'::JSONB;
BEGIN
  FOREACH v_table IN ARRAY ARRAY[
    'n6_stock_display_cache',
    'n6_index_display_cache',
    'n6_board_display_cache',
    'n6_index_membership_display_cache',
    'n6_board_membership_display_cache',
    'n6_display_cache_run'
  ]
  LOOP
    IF to_regclass(v_table) IS NOT NULL THEN
      EXECUTE format('SELECT count(*)::bigint FROM %I', v_table) INTO v_count;
      v_total := v_total + v_count;
      v_counts := v_counts || jsonb_build_object(v_table, v_count);
    END IF;
  END LOOP;

  IF v_total <> 0 THEN
    RAISE EXCEPTION
      'N6 local display cache schema rollback blocked: cache tables are not empty; total=%, counts=%',
      v_total,
      v_counts;
  END IF;
END $$;

BEGIN;

DROP TABLE IF EXISTS n6_board_membership_display_cache;
DROP TABLE IF EXISTS n6_index_membership_display_cache;
DROP TABLE IF EXISTS n6_board_display_cache;
DROP TABLE IF EXISTS n6_index_display_cache;
DROP TABLE IF EXISTS n6_stock_display_cache;
DROP TABLE IF EXISTS n6_display_cache_run;

COMMIT;
