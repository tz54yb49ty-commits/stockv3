-- N2-R4 overwrite rollback preview.
-- Do not execute without explicit user confirmation.
-- This removes the new N2-R4 condition run and restores the previous active run status.

BEGIN;

DELETE FROM stock_minute_target_scope WHERE run_id = 'condition_layer_20260522_to_20260525_20260525003855_execute';
DELETE FROM board_minute_target_scope WHERE run_id = 'condition_layer_20260522_to_20260525_20260525003855_execute';
DELETE FROM index_minute_target_scope WHERE run_id = 'condition_layer_20260522_to_20260525_20260525003855_execute';

DELETE FROM board_condition_pool WHERE run_id = 'condition_layer_20260522_to_20260525_20260525003855_execute';
DELETE FROM index_condition_pool WHERE run_id = 'condition_layer_20260522_to_20260525_20260525003855_execute';
DELETE FROM stock_condition_pool WHERE run_id = 'condition_layer_20260522_to_20260525_20260525003855_execute';

DELETE FROM board_condition_basis WHERE run_id = 'condition_layer_20260522_to_20260525_20260525003855_execute';
DELETE FROM index_condition_basis WHERE run_id = 'condition_layer_20260522_to_20260525_20260525003855_execute';
DELETE FROM stock_condition_basis WHERE run_id = 'condition_layer_20260522_to_20260525_20260525003855_execute';

DELETE FROM board_monitor_target WHERE source_version = 'condition_layer_20260522_to_20260525_20260525003855_execute';
DELETE FROM index_monitor_target WHERE source_version = 'condition_layer_20260522_to_20260525_20260525003855_execute';
DELETE FROM stock_monitor_target WHERE source_version = 'condition_layer_20260522_to_20260525_20260525003855_execute';

DELETE FROM common_condition_quality_item WHERE run_id = 'condition_layer_20260522_to_20260525_20260525003855_execute';
DELETE FROM common_condition_run WHERE run_id = 'condition_layer_20260522_to_20260525_20260525003855_execute';

UPDATE common_condition_run
SET status = 'passed', updated_at = now()
WHERE run_id = 'condition_layer_20260522_to_20260525_20260524205747_execute';

COMMIT;
