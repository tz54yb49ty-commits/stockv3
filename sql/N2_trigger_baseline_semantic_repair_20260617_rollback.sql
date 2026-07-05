\set ON_ERROR_STOP on

BEGIN;

DO $$
DECLARE
    v_run_id text := 'condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
    v_previous_active_run_id text := 'condition_layer_20260616_source_20260616_for_20260617_v1';
    v_target_status text;
    v_previous_status text;
    v_downstream_refs bigint;
    v_event_refs bigint;
    v_checkpoint_refs bigint;
BEGIN
    SELECT status
    INTO v_target_status
    FROM common_condition_run
    WHERE run_id = v_run_id;

    IF v_target_status IS DISTINCT FROM 'passed_active' THEN
        RAISE EXCEPTION
            'rollback blocked: target N2 run % status is %, expected passed_active',
            v_run_id, v_target_status;
    END IF;

    SELECT status
    INTO v_previous_status
    FROM common_condition_run
    WHERE run_id = v_previous_active_run_id;

    IF v_previous_status IS DISTINCT FROM 'superseded' THEN
        RAISE EXCEPTION
            'rollback blocked: previous active N2 run % status is %, expected superseded',
            v_previous_active_run_id, v_previous_status;
    END IF;

    SELECT
        (SELECT count(*) FROM common_market_data_run WHERE source_condition_run_id = v_run_id)
      + (SELECT count(*) FROM common_trigger_run WHERE source_condition_run_id = v_run_id)
      + (SELECT count(*) FROM common_action_run WHERE source_condition_run_id = v_run_id)
      + (SELECT count(*) FROM common_condition_context_enrichment_run WHERE source_condition_run_id = v_run_id)
      + (SELECT count(*) FROM common_position_event WHERE source_condition_run_id = v_run_id)
    INTO v_downstream_refs;

    SELECT
        (SELECT count(*) FROM common_event_outbox WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%')
      + (SELECT count(*) FROM common_event_inbox WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%' OR raw_json::text LIKE '%' || v_run_id || '%')
    INTO v_event_refs;

    SELECT count(*)
    INTO v_checkpoint_refs
    FROM common_event_consumer_checkpoint
    WHERE checkpoint_payload::text LIKE '%' || v_run_id || '%'
       OR last_event_id LIKE '%' || v_run_id || '%';

    IF v_downstream_refs <> 0 THEN
        RAISE EXCEPTION
            'rollback blocked: downstream refs exist for N2 condition run %, refs=%',
            v_run_id, v_downstream_refs;
    END IF;

    IF v_event_refs <> 0 THEN
        RAISE EXCEPTION
            'rollback blocked: outbox/inbox refs exist for N2 condition run %, refs=%',
            v_run_id, v_event_refs;
    END IF;

    IF v_checkpoint_refs <> 0 THEN
        RAISE EXCEPTION
            'rollback blocked: checkpoint refs exist for N2 condition run %, refs=%',
            v_run_id, v_checkpoint_refs;
    END IF;
END $$;

DELETE FROM stock_condition_display_basis WHERE run_id = 'condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM index_condition_display_basis WHERE run_id = 'condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM board_condition_display_basis WHERE run_id = 'condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';

DELETE FROM stock_minute_target_scope WHERE run_id = 'condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM board_minute_target_scope WHERE run_id = 'condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM index_minute_target_scope WHERE run_id = 'condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';

DELETE FROM board_condition_pool WHERE run_id = 'condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM index_condition_pool WHERE run_id = 'condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM stock_condition_pool WHERE run_id = 'condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';

DELETE FROM board_condition_basis WHERE run_id = 'condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM index_condition_basis WHERE run_id = 'condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM stock_condition_basis WHERE run_id = 'condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';

DELETE FROM board_monitor_target WHERE source_version = 'condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM index_monitor_target WHERE source_version = 'condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM stock_monitor_target WHERE source_version = 'condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';

DELETE FROM common_condition_quality_item WHERE run_id = 'condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM common_condition_run WHERE run_id = 'condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';

UPDATE common_condition_run
SET status = 'passed_active', updated_at = now()
WHERE run_id = 'condition_layer_20260616_source_20260616_for_20260617_v1'
  AND status = 'superseded';

COMMIT;
