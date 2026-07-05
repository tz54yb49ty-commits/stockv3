-- N2 level score v6 rollback draft.
-- Target run_id: condition_layer_20260529_source_20260529_v6
-- Restores previous active run: condition_layer_20260529_source_20260529_v5
-- Guard: do not rollback if v6 has downstream N3/N4/N5/N6 references.

BEGIN;

DO $$
DECLARE
  downstream_ref_count integer := 0;
BEGIN
  SELECT COALESCE((SELECT COUNT(*) FROM common_market_data_run WHERE source_condition_run_id = 'condition_layer_20260529_source_20260529_v6'), 0)
       + COALESCE((SELECT COUNT(*) FROM common_trigger_run WHERE source_condition_run_id = 'condition_layer_20260529_source_20260529_v6'), 0)
       + COALESCE((SELECT COUNT(*) FROM common_action_run WHERE source_condition_run_id = 'condition_layer_20260529_source_20260529_v6'), 0)
    INTO downstream_ref_count;
  IF downstream_ref_count > 0 THEN
    RAISE EXCEPTION 'Rollback blocked: downstream refs exist for condition_layer_20260529_source_20260529_v6: %', downstream_ref_count;
  END IF;
END $$;

DELETE FROM stock_condition_display_basis WHERE run_id = 'condition_layer_20260529_source_20260529_v6';
DELETE FROM index_condition_display_basis WHERE run_id = 'condition_layer_20260529_source_20260529_v6';
DELETE FROM board_condition_display_basis WHERE run_id = 'condition_layer_20260529_source_20260529_v6';
DELETE FROM stock_minute_target_scope WHERE run_id = 'condition_layer_20260529_source_20260529_v6';
DELETE FROM board_minute_target_scope WHERE run_id = 'condition_layer_20260529_source_20260529_v6';
DELETE FROM index_minute_target_scope WHERE run_id = 'condition_layer_20260529_source_20260529_v6';
DELETE FROM board_condition_pool WHERE run_id = 'condition_layer_20260529_source_20260529_v6';
DELETE FROM index_condition_pool WHERE run_id = 'condition_layer_20260529_source_20260529_v6';
DELETE FROM stock_condition_pool WHERE run_id = 'condition_layer_20260529_source_20260529_v6';
DELETE FROM board_condition_basis WHERE run_id = 'condition_layer_20260529_source_20260529_v6';
DELETE FROM index_condition_basis WHERE run_id = 'condition_layer_20260529_source_20260529_v6';
DELETE FROM stock_condition_basis WHERE run_id = 'condition_layer_20260529_source_20260529_v6';
DELETE FROM board_monitor_target WHERE source_version = 'condition_layer_20260529_source_20260529_v6';
DELETE FROM index_monitor_target WHERE source_version = 'condition_layer_20260529_source_20260529_v6';
DELETE FROM stock_monitor_target WHERE source_version = 'condition_layer_20260529_source_20260529_v6';
DELETE FROM common_condition_quality_item WHERE run_id = 'condition_layer_20260529_source_20260529_v6';
DELETE FROM common_condition_run WHERE run_id = 'condition_layer_20260529_source_20260529_v6';

UPDATE common_condition_run
SET status = 'passed_active', updated_at = now()
WHERE run_id = 'condition_layer_20260529_source_20260529_v5';

COMMIT;
