-- A-share monitor v3 N4-5 trigger run-once rollback.
-- Execute only before downstream layers consume this N4 outbox.
-- This rollback deletes only N4-5 state/match/quality/outbox rows for one run_id.

BEGIN;

DELETE FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = 'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute';

DELETE FROM common_trigger_match WHERE run_id = 'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute';
DELETE FROM common_trigger_state WHERE run_id = 'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute';
DELETE FROM common_trigger_quality_item
WHERE run_id = 'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute'
  AND gate_code LIKE 'n4_5_%';

COMMIT;

-- Boundary:
-- - Does not touch common_trigger_run or trigger_context_snapshot rows.
-- - Does not touch common_condition_run or condition tables.
-- - Does not touch common_market_data_* or market data fact tables.
-- - Does not touch downstream layer tables.
