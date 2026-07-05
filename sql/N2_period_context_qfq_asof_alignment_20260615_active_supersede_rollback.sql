-- N2 period context QFQ/as-of alignment active supersede rollback.
-- Scope: remove only condition_layer_20260615_source_20260615_for_20260616_v2 rows and restore condition_layer_20260615_source_20260615_for_20260616_v1 to passed_active.
-- Boundary: no N1 facts, no N3/N4/N5/N6 facts, no outbox/inbox/checkpoint mutation.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'condition_layer_20260615_source_20260615_for_20260616_v2';
  v_restore_run_id TEXT := 'condition_layer_20260615_source_20260615_for_20260616_v1';
  v_downstream_refs BIGINT := 0;
  v_event_refs BIGINT := 0;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM common_condition_run WHERE run_id = v_run_id) THEN
    RAISE EXCEPTION 'rollback blocked: N2 run % does not exist', v_run_id;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM common_condition_run WHERE run_id = v_restore_run_id) THEN
    RAISE EXCEPTION 'rollback blocked: restore N2 run % does not exist', v_restore_run_id;
  END IF;

  SELECT
      COALESCE((SELECT count(*) FROM common_market_data_run WHERE source_condition_run_id = v_run_id OR run_id LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_trigger_run WHERE source_condition_run_id = v_run_id OR run_id LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_action_run WHERE source_condition_run_id = v_run_id OR run_id LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM user_projection_run WHERE source_display_condition_run_id = v_run_id OR user_projection_run_id LIKE '%' || v_run_id || '%'), 0)
  INTO v_downstream_refs;

  IF v_downstream_refs > 0 THEN
    RAISE EXCEPTION 'rollback blocked: downstream N3/N4/N5/N6 refs exist for % (% rows)', v_run_id, v_downstream_refs;
  END IF;

  SELECT
      COALESCE((SELECT count(*) FROM common_event_outbox WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_event_inbox WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%' OR raw_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_event_consumer_checkpoint WHERE last_event_id LIKE '%' || v_run_id || '%' OR checkpoint_payload::text LIKE '%' || v_run_id || '%'), 0)
  INTO v_event_refs;

  IF v_event_refs > 0 THEN
    RAISE EXCEPTION 'rollback blocked: event infra refs exist for % (% rows)', v_run_id, v_event_refs;
  END IF;
END $$;

DELETE FROM stock_condition_display_basis WHERE run_id = 'condition_layer_20260615_source_20260615_for_20260616_v2';
DELETE FROM index_condition_display_basis WHERE run_id = 'condition_layer_20260615_source_20260615_for_20260616_v2';
DELETE FROM board_condition_display_basis WHERE run_id = 'condition_layer_20260615_source_20260615_for_20260616_v2';

DELETE FROM stock_minute_target_scope WHERE run_id = 'condition_layer_20260615_source_20260615_for_20260616_v2';
DELETE FROM index_minute_target_scope WHERE run_id = 'condition_layer_20260615_source_20260615_for_20260616_v2';
DELETE FROM board_minute_target_scope WHERE run_id = 'condition_layer_20260615_source_20260615_for_20260616_v2';

DELETE FROM stock_condition_pool WHERE run_id = 'condition_layer_20260615_source_20260615_for_20260616_v2';
DELETE FROM index_condition_pool WHERE run_id = 'condition_layer_20260615_source_20260615_for_20260616_v2';
DELETE FROM board_condition_pool WHERE run_id = 'condition_layer_20260615_source_20260615_for_20260616_v2';

DELETE FROM stock_condition_basis WHERE run_id = 'condition_layer_20260615_source_20260615_for_20260616_v2';
DELETE FROM index_condition_basis WHERE run_id = 'condition_layer_20260615_source_20260615_for_20260616_v2';
DELETE FROM board_condition_basis WHERE run_id = 'condition_layer_20260615_source_20260615_for_20260616_v2';

DELETE FROM stock_monitor_target WHERE source_version = 'condition_layer_20260615_source_20260615_for_20260616_v2';
DELETE FROM index_monitor_target WHERE source_version = 'condition_layer_20260615_source_20260615_for_20260616_v2';
DELETE FROM board_monitor_target WHERE source_version = 'condition_layer_20260615_source_20260615_for_20260616_v2';

DELETE FROM common_condition_quality_item WHERE run_id = 'condition_layer_20260615_source_20260615_for_20260616_v2';
DELETE FROM common_condition_run WHERE run_id = 'condition_layer_20260615_source_20260615_for_20260616_v2';

UPDATE common_condition_run
SET status = 'passed_active'
WHERE run_id = 'condition_layer_20260615_source_20260615_for_20260616_v1';

COMMIT;
