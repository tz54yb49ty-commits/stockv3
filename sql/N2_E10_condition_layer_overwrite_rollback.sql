-- Rollback for N2-E10 condition layer overwrite.
-- Generated: 2026-05-24T01:42:00
-- Scope: v3 development database only.
-- New run to delete: condition_layer_20260522_to_20260525_20260524014029_execute
-- Previous active run to restore: condition_layer_20260522_to_20260525_20260523223042_execute
-- This SQL does not touch old systems, market data, trigger/action/mobile/voice/sim tables, or N3 tables.

BEGIN;

-- Delete minute target scopes for the new run.
DELETE FROM stock_minute_target_scope WHERE run_id = 'condition_layer_20260522_to_20260525_20260524014029_execute';
DELETE FROM board_minute_target_scope WHERE run_id = 'condition_layer_20260522_to_20260525_20260524014029_execute';
DELETE FROM index_minute_target_scope WHERE run_id = 'condition_layer_20260522_to_20260525_20260524014029_execute';

-- Delete condition pools for the new run.
DELETE FROM board_condition_pool WHERE run_id = 'condition_layer_20260522_to_20260525_20260524014029_execute';
DELETE FROM index_condition_pool WHERE run_id = 'condition_layer_20260522_to_20260525_20260524014029_execute';
DELETE FROM stock_condition_pool WHERE run_id = 'condition_layer_20260522_to_20260525_20260524014029_execute';

-- Delete condition basis rows for the new run.
DELETE FROM board_condition_basis WHERE run_id = 'condition_layer_20260522_to_20260525_20260524014029_execute';
DELETE FROM index_condition_basis WHERE run_id = 'condition_layer_20260522_to_20260525_20260524014029_execute';
DELETE FROM stock_condition_basis WHERE run_id = 'condition_layer_20260522_to_20260525_20260524014029_execute';

-- Delete monitor target snapshots for the new run. These tables track execute_run_id in source_version.
DELETE FROM board_monitor_target WHERE source_version = 'condition_layer_20260522_to_20260525_20260524014029_execute';
DELETE FROM index_monitor_target WHERE source_version = 'condition_layer_20260522_to_20260525_20260524014029_execute';
DELETE FROM stock_monitor_target WHERE source_version = 'condition_layer_20260522_to_20260525_20260524014029_execute';

-- Delete quality items and the run row for the new run.
DELETE FROM common_condition_quality_item WHERE run_id = 'condition_layer_20260522_to_20260525_20260524014029_execute';
DELETE FROM common_condition_run WHERE run_id = 'condition_layer_20260522_to_20260525_20260524014029_execute';

-- Restore previous active run.
UPDATE common_condition_run
SET status = 'passed', updated_at = now()
WHERE run_id = 'condition_layer_20260522_to_20260525_20260523223042_execute'
  AND status = 'superseded';

COMMIT;
