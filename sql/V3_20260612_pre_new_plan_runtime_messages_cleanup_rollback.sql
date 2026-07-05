-- Rollback draft for V3 20260612 pre-new-plan runtime cleanup.
-- Restores rows from common_runtime_cleanup_backup for the scoped cleanup run.
-- Blocked by default. Execute only in a dedicated rollback gate.

BEGIN;

DO $$
DECLARE
    v_cleanup_run_id text := 'v3_20260612_pre_new_plan_runtime_messages_cleanup_v1';
    v_backup_rows bigint;
BEGIN
    IF current_setting('ashare_v3.allow_v3_20260612_pre_new_plan_cleanup_rollback', true) <> 'true' THEN
        RAISE EXCEPTION 'cleanup rollback blocked: SET ashare_v3.allow_v3_20260612_pre_new_plan_cleanup_rollback = true is required';
    END IF;

    RAISE EXCEPTION 'cleanup rollback blocked by default; remove this line only in an approved rollback gate after refreshing live refs';

    SELECT count(*) INTO v_backup_rows
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id;
    IF v_backup_rows = 0 THEN
        RAISE EXCEPTION 'no backup rows found for cleanup_run_id=%', v_cleanup_run_id;
    END IF;

    INSERT INTO common_market_data_run
    SELECT (jsonb_populate_record(NULL::common_market_data_run, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'common_market_data_run';
    INSERT INTO common_market_data_quality_item
    SELECT (jsonb_populate_record(NULL::common_market_data_quality_item, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'common_market_data_quality_item';
    INSERT INTO stock_realtime_daily_snapshot
    SELECT (jsonb_populate_record(NULL::stock_realtime_daily_snapshot, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'stock_realtime_daily_snapshot';
    INSERT INTO index_realtime_daily_snapshot
    SELECT (jsonb_populate_record(NULL::index_realtime_daily_snapshot, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'index_realtime_daily_snapshot';
    INSERT INTO board_realtime_daily_snapshot
    SELECT (jsonb_populate_record(NULL::board_realtime_daily_snapshot, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'board_realtime_daily_snapshot';
    INSERT INTO stock_realtime_projection_metric
    SELECT (jsonb_populate_record(NULL::stock_realtime_projection_metric, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'stock_realtime_projection_metric';
    INSERT INTO index_realtime_projection_metric
    SELECT (jsonb_populate_record(NULL::index_realtime_projection_metric, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'index_realtime_projection_metric';
    INSERT INTO board_realtime_projection_metric
    SELECT (jsonb_populate_record(NULL::board_realtime_projection_metric, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'board_realtime_projection_metric';

    INSERT INTO common_trigger_run
    SELECT (jsonb_populate_record(NULL::common_trigger_run, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'common_trigger_run';
    INSERT INTO common_trigger_quality_item
    SELECT (jsonb_populate_record(NULL::common_trigger_quality_item, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'common_trigger_quality_item';
    INSERT INTO common_trigger_state
    SELECT (jsonb_populate_record(NULL::common_trigger_state, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'common_trigger_state';
    INSERT INTO common_trigger_match
    SELECT (jsonb_populate_record(NULL::common_trigger_match, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'common_trigger_match';

    INSERT INTO common_action_run
    SELECT (jsonb_populate_record(NULL::common_action_run, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'common_action_run';
    INSERT INTO common_action_quality_item
    SELECT (jsonb_populate_record(NULL::common_action_quality_item, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'common_action_quality_item';
    INSERT INTO stock_action_fact
    SELECT (jsonb_populate_record(NULL::stock_action_fact, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'stock_action_fact';
    INSERT INTO index_action_fact
    SELECT (jsonb_populate_record(NULL::index_action_fact, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'index_action_fact';
    INSERT INTO board_action_fact
    SELECT (jsonb_populate_record(NULL::board_action_fact, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'board_action_fact';
    INSERT INTO common_action_event
    SELECT (jsonb_populate_record(NULL::common_action_event, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'common_action_event';

    INSERT INTO common_event_outbox
    SELECT (jsonb_populate_record(NULL::common_event_outbox, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'common_event_outbox';
    INSERT INTO common_event_inbox
    SELECT (jsonb_populate_record(NULL::common_event_inbox, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'common_event_inbox';
    INSERT INTO common_event_consumer_checkpoint
    SELECT (jsonb_populate_record(NULL::common_event_consumer_checkpoint, row_json)).*
      FROM common_runtime_cleanup_backup
     WHERE cleanup_run_id = v_cleanup_run_id AND table_name = 'common_event_consumer_checkpoint';
END $$;

COMMIT;
