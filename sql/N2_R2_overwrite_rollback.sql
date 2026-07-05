-- N2-R2 overwrite rollback SQL
-- Generated: 2026-05-24T18:17:04
-- Scope: rollback only N2 condition-layer rows for new run condition_layer_20260522_to_20260525_20260524181321_execute.
-- Does not touch common_event_outbox, N1 ingest facts, N3/N4/N5/N6 tables, market data, workers, or old system.
-- Execute only if the new N2-R2 run has not been consumed by downstream layers.

BEGIN;

DELETE FROM stock_minute_target_scope WHERE run_id = 'condition_layer_20260522_to_20260525_20260524181321_execute';
DELETE FROM board_minute_target_scope WHERE run_id = 'condition_layer_20260522_to_20260525_20260524181321_execute';
DELETE FROM index_minute_target_scope WHERE run_id = 'condition_layer_20260522_to_20260525_20260524181321_execute';
DELETE FROM board_condition_pool WHERE run_id = 'condition_layer_20260522_to_20260525_20260524181321_execute';
DELETE FROM index_condition_pool WHERE run_id = 'condition_layer_20260522_to_20260525_20260524181321_execute';
DELETE FROM stock_condition_pool WHERE run_id = 'condition_layer_20260522_to_20260525_20260524181321_execute';
DELETE FROM board_condition_basis WHERE run_id = 'condition_layer_20260522_to_20260525_20260524181321_execute';
DELETE FROM index_condition_basis WHERE run_id = 'condition_layer_20260522_to_20260525_20260524181321_execute';
DELETE FROM stock_condition_basis WHERE run_id = 'condition_layer_20260522_to_20260525_20260524181321_execute';
DELETE FROM board_monitor_target WHERE source_version = 'condition_layer_20260522_to_20260525_20260524181321_execute';
DELETE FROM index_monitor_target WHERE source_version = 'condition_layer_20260522_to_20260525_20260524181321_execute';
DELETE FROM stock_monitor_target WHERE source_version = 'condition_layer_20260522_to_20260525_20260524181321_execute';
DELETE FROM common_condition_quality_item WHERE run_id = 'condition_layer_20260522_to_20260525_20260524181321_execute';
DELETE FROM common_condition_run WHERE run_id = 'condition_layer_20260522_to_20260525_20260524181321_execute';

UPDATE common_condition_run
SET status = 'passed', updated_at = now()
WHERE run_id = 'condition_layer_20260522_to_20260525_20260524014029_execute';

COMMIT;

-- Verification after rollback:
-- SELECT run_id, status FROM common_condition_run WHERE run_id IN ('condition_layer_20260522_to_20260525_20260524181321_execute', 'condition_layer_20260522_to_20260525_20260524014029_execute');
-- SELECT count(*) FROM common_event_outbox; -- must remain unchanged by rollback.
