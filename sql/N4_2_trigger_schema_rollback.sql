-- A-share monitor v3 N4 trigger schema rollback preview.
-- Generated in N4-1 for review only. Do not execute unless N4-2 migration
-- has been explicitly confirmed and no N4 business rows have been written.
-- This rollback drops only N4 trigger-layer schema objects.

BEGIN;

DROP TABLE IF EXISTS common_trigger_match;
DROP TABLE IF EXISTS common_trigger_state;
DROP TABLE IF EXISTS board_trigger_context_snapshot;
DROP TABLE IF EXISTS index_trigger_context_snapshot;
DROP TABLE IF EXISTS stock_trigger_context_snapshot;
DROP TABLE IF EXISTS common_trigger_quality_item;
DROP TABLE IF EXISTS common_trigger_run;

COMMIT;

-- Boundary:
-- - Does not touch common_condition_run or condition tables.
-- - Does not touch common_market_data_* or market data fact tables.
-- - Does not touch common_event_outbox.
-- - Does not touch action/user/voice/sim/position tables.
