-- N2 condition layer 20260526 rollback draft.
-- Suggested run_id: condition_layer_20260601_source_20260601_v1
-- Usage:
--   psql "$ASHARE_V3_POSTGRES_DSN" -v ON_ERROR_STOP=1 -v run_id='ACTUAL_N2_RUN_ID' -f sql/N2_condition_layer_20260526_rollback.sql
-- Does not touch N1 source_version, event outbox/inbox/checkpoint, N3-N6, workers, or old system.

BEGIN;

DELETE FROM stock_condition_display_basis WHERE run_id = :'run_id';
DELETE FROM index_condition_display_basis WHERE run_id = :'run_id';
DELETE FROM board_condition_display_basis WHERE run_id = :'run_id';

DELETE FROM stock_minute_target_scope WHERE run_id = :'run_id';
DELETE FROM board_minute_target_scope WHERE run_id = :'run_id';
DELETE FROM index_minute_target_scope WHERE run_id = :'run_id';

DELETE FROM board_condition_pool WHERE run_id = :'run_id';
DELETE FROM index_condition_pool WHERE run_id = :'run_id';
DELETE FROM stock_condition_pool WHERE run_id = :'run_id';

DELETE FROM board_condition_basis WHERE run_id = :'run_id';
DELETE FROM index_condition_basis WHERE run_id = :'run_id';
DELETE FROM stock_condition_basis WHERE run_id = :'run_id';

DELETE FROM board_monitor_target WHERE source_version = :'run_id';
DELETE FROM index_monitor_target WHERE source_version = :'run_id';
DELETE FROM stock_monitor_target WHERE source_version = :'run_id';

DELETE FROM common_condition_quality_item WHERE run_id = :'run_id';
DELETE FROM common_condition_run WHERE run_id = :'run_id';

COMMIT;
