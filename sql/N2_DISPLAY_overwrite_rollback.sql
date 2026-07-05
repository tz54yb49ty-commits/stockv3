-- N2-Display overwrite rollback plan
-- Generated 2026-05-25T10:24:15
-- New run to delete: condition_layer_20260522_to_20260525_20260525102249_execute
-- Previous active run to restore: condition_layer_20260522_to_20260525_20260525003855_execute
-- Review before executing. This does not touch common_event_outbox, N1, N3, N4, N5, or N6.

BEGIN;

DELETE FROM stock_condition_display_basis WHERE run_id = 'condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM index_condition_display_basis WHERE run_id = 'condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM board_condition_display_basis WHERE run_id = 'condition_layer_20260522_to_20260525_20260525102249_execute';

DELETE FROM stock_minute_target_scope WHERE run_id = 'condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM board_minute_target_scope WHERE run_id = 'condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM index_minute_target_scope WHERE run_id = 'condition_layer_20260522_to_20260525_20260525102249_execute';

DELETE FROM board_condition_pool WHERE run_id = 'condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM index_condition_pool WHERE run_id = 'condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM stock_condition_pool WHERE run_id = 'condition_layer_20260522_to_20260525_20260525102249_execute';

DELETE FROM board_condition_basis WHERE run_id = 'condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM index_condition_basis WHERE run_id = 'condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM stock_condition_basis WHERE run_id = 'condition_layer_20260522_to_20260525_20260525102249_execute';

DELETE FROM board_monitor_target WHERE source_version = 'condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM index_monitor_target WHERE source_version = 'condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM stock_monitor_target WHERE source_version = 'condition_layer_20260522_to_20260525_20260525102249_execute';

DELETE FROM common_condition_quality_item WHERE run_id = 'condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM common_condition_run WHERE run_id = 'condition_layer_20260522_to_20260525_20260525102249_execute';

UPDATE common_condition_run
SET status = 'passed', updated_at = now()
WHERE run_id = 'condition_layer_20260522_to_20260525_20260525003855_execute';

COMMIT;
