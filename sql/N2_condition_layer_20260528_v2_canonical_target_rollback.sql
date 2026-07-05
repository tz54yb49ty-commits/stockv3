-- Rollback draft for N2 canonical target condition run v2.
-- Do not execute without explicit user confirmation.
--
-- Scope:
--   Delete only condition_layer_20260528_source_20260528_v2 rows.
--   Restore condition_layer_20260528_source_20260528_v1 to passed_active.
--
-- Boundary:
--   Does not touch N1 source_version.
--   Does not touch N3/N4/N5/N6 rows.
--   Blocks if v2 already has downstream references.

BEGIN;

DO $$
DECLARE
  v2_run_id text := 'condition_layer_20260528_source_20260528_v2';
  downstream_refs bigint := 0;
BEGIN
  SELECT
      (SELECT count(*) FROM common_market_data_run WHERE source_condition_run_id = v2_run_id OR run_id LIKE '%' || v2_run_id || '%')
    + (SELECT count(*) FROM common_trigger_run WHERE source_condition_run_id = v2_run_id OR run_id LIKE '%' || v2_run_id || '%')
    + (SELECT count(*) FROM common_action_run WHERE source_condition_run_id = v2_run_id OR run_id LIKE '%' || v2_run_id || '%')
  INTO downstream_refs;

  IF downstream_refs > 0 THEN
    RAISE EXCEPTION 'rollback blocked: downstream refs exist for % (% rows)', v2_run_id, downstream_refs;
  END IF;
END $$;

DELETE FROM stock_condition_display_basis WHERE run_id = 'condition_layer_20260528_source_20260528_v2';
DELETE FROM index_condition_display_basis WHERE run_id = 'condition_layer_20260528_source_20260528_v2';
DELETE FROM board_condition_display_basis WHERE run_id = 'condition_layer_20260528_source_20260528_v2';

DELETE FROM stock_minute_target_scope WHERE run_id = 'condition_layer_20260528_source_20260528_v2';
DELETE FROM index_minute_target_scope WHERE run_id = 'condition_layer_20260528_source_20260528_v2';
DELETE FROM board_minute_target_scope WHERE run_id = 'condition_layer_20260528_source_20260528_v2';

DELETE FROM stock_condition_pool WHERE run_id = 'condition_layer_20260528_source_20260528_v2';
DELETE FROM index_condition_pool WHERE run_id = 'condition_layer_20260528_source_20260528_v2';
DELETE FROM board_condition_pool WHERE run_id = 'condition_layer_20260528_source_20260528_v2';

DELETE FROM stock_condition_basis WHERE run_id = 'condition_layer_20260528_source_20260528_v2';
DELETE FROM index_condition_basis WHERE run_id = 'condition_layer_20260528_source_20260528_v2';
DELETE FROM board_condition_basis WHERE run_id = 'condition_layer_20260528_source_20260528_v2';

DELETE FROM stock_monitor_target WHERE source_version = 'condition_layer_20260528_source_20260528_v2';
DELETE FROM index_monitor_target WHERE source_version = 'condition_layer_20260528_source_20260528_v2';
DELETE FROM board_monitor_target WHERE source_version = 'condition_layer_20260528_source_20260528_v2';

DELETE FROM common_condition_quality_item WHERE run_id = 'condition_layer_20260528_source_20260528_v2';
DELETE FROM common_condition_run WHERE run_id = 'condition_layer_20260528_source_20260528_v2';

UPDATE common_condition_run
SET status = 'passed_active', updated_at = now()
WHERE run_id = 'condition_layer_20260528_source_20260528_v1'
  AND status = 'superseded';

COMMIT;
