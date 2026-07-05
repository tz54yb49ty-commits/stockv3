\set ON_ERROR_STOP on

BEGIN;

DO $$
DECLARE
    v_run_id text := 'condition_layer_20260604_source_20260604_v1';
    v_downstream_refs bigint;
    v_event_refs bigint;
BEGIN
    SELECT
        (SELECT count(*) FROM common_market_data_run WHERE source_condition_run_id = v_run_id)
      + (SELECT count(*) FROM common_trigger_run WHERE source_condition_run_id = v_run_id)
      + (SELECT count(*) FROM common_action_run WHERE source_condition_run_id = v_run_id)
      + (SELECT count(*) FROM common_condition_context_enrichment_run WHERE source_condition_run_id = v_run_id)
      + (SELECT count(*) FROM common_position_event WHERE source_condition_run_id = v_run_id)
    INTO v_downstream_refs;

    SELECT
        (SELECT count(*) FROM common_event_outbox WHERE source_run_id = v_run_id)
      + (SELECT count(*) FROM common_event_inbox WHERE source_run_id = v_run_id)
    INTO v_event_refs;

    IF v_downstream_refs <> 0 THEN
        RAISE EXCEPTION
            'rollback blocked: downstream refs exist for condition run %, refs=%',
            v_run_id, v_downstream_refs;
    END IF;

    IF v_event_refs <> 0 THEN
        RAISE EXCEPTION
            'rollback blocked: outbox/inbox refs exist for condition run %, refs=%',
            v_run_id, v_event_refs;
    END IF;
END $$;

DELETE FROM stock_condition_display_basis WHERE run_id = 'condition_layer_20260604_source_20260604_v1';
DELETE FROM index_condition_display_basis WHERE run_id = 'condition_layer_20260604_source_20260604_v1';
DELETE FROM board_condition_display_basis WHERE run_id = 'condition_layer_20260604_source_20260604_v1';

DELETE FROM stock_minute_target_scope WHERE run_id = 'condition_layer_20260604_source_20260604_v1';
DELETE FROM board_minute_target_scope WHERE run_id = 'condition_layer_20260604_source_20260604_v1';
DELETE FROM index_minute_target_scope WHERE run_id = 'condition_layer_20260604_source_20260604_v1';

DELETE FROM board_condition_pool WHERE run_id = 'condition_layer_20260604_source_20260604_v1';
DELETE FROM index_condition_pool WHERE run_id = 'condition_layer_20260604_source_20260604_v1';
DELETE FROM stock_condition_pool WHERE run_id = 'condition_layer_20260604_source_20260604_v1';

DELETE FROM board_condition_basis WHERE run_id = 'condition_layer_20260604_source_20260604_v1';
DELETE FROM index_condition_basis WHERE run_id = 'condition_layer_20260604_source_20260604_v1';
DELETE FROM stock_condition_basis WHERE run_id = 'condition_layer_20260604_source_20260604_v1';

DELETE FROM board_monitor_target WHERE source_version = 'condition_layer_20260604_source_20260604_v1';
DELETE FROM index_monitor_target WHERE source_version = 'condition_layer_20260604_source_20260604_v1';
DELETE FROM stock_monitor_target WHERE source_version = 'condition_layer_20260604_source_20260604_v1';

DELETE FROM common_condition_quality_item WHERE run_id = 'condition_layer_20260604_source_20260604_v1';
DELETE FROM common_condition_run WHERE run_id = 'condition_layer_20260604_source_20260604_v1';

COMMIT;
