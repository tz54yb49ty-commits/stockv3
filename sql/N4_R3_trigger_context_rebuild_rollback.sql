-- A-share monitor v3 N4 trigger context rollback.
-- Execute only after confirming this N4 context run has not been consumed downstream.
-- This rollback deletes only N4 trigger context/run/quality rows for one run_id.

BEGIN;

DELETE FROM common_trigger_quality_item WHERE run_id = 'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524205747_execute';
DELETE FROM stock_trigger_context_snapshot WHERE run_id = 'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524205747_execute';
DELETE FROM index_trigger_context_snapshot WHERE run_id = 'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524205747_execute';
DELETE FROM board_trigger_context_snapshot WHERE run_id = 'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524205747_execute';
DELETE FROM common_trigger_run WHERE run_id = 'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524205747_execute';

COMMIT;

-- Boundary:
-- - Does not touch common_condition_run or condition tables.
-- - Does not touch common_market_data_* or market data fact tables.
-- - Does not touch common_event_outbox.
-- - Does not touch trigger_state / trigger_match because N4-3 never writes them.
-- - Does not touch action/user/voice/sim/position tables.
