-- N5-3 rollback preview for sql/011_action_layer_schema.sql.
-- Preview only. Do not execute unless N5 migration execution has been explicitly approved and needs rollback.
BEGIN;
DROP TABLE IF EXISTS common_position_event CASCADE;
DROP TABLE IF EXISTS common_position_state CASCADE;
DROP TABLE IF EXISTS common_action_event CASCADE;
DROP TABLE IF EXISTS board_action_fact CASCADE;
DROP TABLE IF EXISTS index_action_fact CASCADE;
DROP TABLE IF EXISTS stock_action_fact CASCADE;
DROP TABLE IF EXISTS common_action_quality_item CASCADE;
DROP TABLE IF EXISTS common_action_run CASCADE;
COMMIT;
