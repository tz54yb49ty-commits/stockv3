-- N2 condition 20260701 rerun rollback.
-- Scope: remove only condition_layer_20260630_source_20260630_for_20260701_v1 rows.
-- Do not execute without a separate rollback final gate.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'condition_layer_20260630_source_20260630_for_20260701_v1';
  v_event_refs BIGINT := 0;
  v_downstream_refs BIGINT := 0;
BEGIN
  IF NOT EXISTS (
    SELECT 1
      FROM common_condition_run
     WHERE run_id = v_run_id
       AND source_trade_date = DATE '2026-06-30'
       AND for_trade_date = DATE '2026-07-01'
  ) THEN
    RAISE EXCEPTION 'rollback blocked: expected N2 run is missing or date-mismatched: %', v_run_id;
  END IF;

  SELECT
      COALESCE((SELECT count(*) FROM common_event_outbox WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_event_inbox WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%' OR raw_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_event_consumer_checkpoint WHERE last_event_id::text LIKE '%' || v_run_id || '%' OR checkpoint_payload::text LIKE '%' || v_run_id || '%'), 0)
    INTO v_event_refs;

  IF v_event_refs > 0 THEN
    RAISE EXCEPTION 'rollback blocked: event infra refs exist for % (% rows)', v_run_id, v_event_refs;
  END IF;

  SELECT
      COALESCE((SELECT count(*) FROM common_market_data_run WHERE source_condition_run_id = v_run_id OR run_id LIKE '%' || v_run_id || '%' OR raw_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_trigger_run WHERE source_condition_run_id = v_run_id OR run_id LIKE '%' || v_run_id || '%' OR raw_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_action_run WHERE source_condition_run_id = v_run_id OR run_id LIKE '%' || v_run_id || '%' OR raw_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM user_projection_run WHERE to_jsonb(user_projection_run)::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM user_signal_projection WHERE source_condition_display_run_id = v_run_id OR to_jsonb(user_signal_projection)::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM user_signal_card WHERE to_jsonb(user_signal_card)::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM user_notification_queue WHERE to_jsonb(user_notification_queue)::text LIKE '%' || v_run_id || '%'), 0)
    INTO v_downstream_refs;

  IF v_downstream_refs > 0 THEN
    RAISE EXCEPTION 'rollback blocked: downstream N3/N4/N5/N6 refs exist for % (% rows)', v_run_id, v_downstream_refs;
  END IF;
END $$;

DELETE FROM stock_condition_display_basis WHERE run_id = 'condition_layer_20260630_source_20260630_for_20260701_v1';
DELETE FROM index_condition_display_basis WHERE run_id = 'condition_layer_20260630_source_20260630_for_20260701_v1';
DELETE FROM board_condition_display_basis WHERE run_id = 'condition_layer_20260630_source_20260630_for_20260701_v1';

DELETE FROM stock_minute_target_scope WHERE run_id = 'condition_layer_20260630_source_20260630_for_20260701_v1';
DELETE FROM index_minute_target_scope WHERE run_id = 'condition_layer_20260630_source_20260630_for_20260701_v1';
DELETE FROM board_minute_target_scope WHERE run_id = 'condition_layer_20260630_source_20260630_for_20260701_v1';

DELETE FROM stock_condition_pool WHERE run_id = 'condition_layer_20260630_source_20260630_for_20260701_v1';
DELETE FROM index_condition_pool WHERE run_id = 'condition_layer_20260630_source_20260630_for_20260701_v1';
DELETE FROM board_condition_pool WHERE run_id = 'condition_layer_20260630_source_20260630_for_20260701_v1';

DELETE FROM stock_condition_basis WHERE run_id = 'condition_layer_20260630_source_20260630_for_20260701_v1';
DELETE FROM index_condition_basis WHERE run_id = 'condition_layer_20260630_source_20260630_for_20260701_v1';
DELETE FROM board_condition_basis WHERE run_id = 'condition_layer_20260630_source_20260630_for_20260701_v1';

DELETE FROM stock_monitor_target WHERE source_version = 'condition_layer_20260630_source_20260630_for_20260701_v1';
DELETE FROM index_monitor_target WHERE source_version = 'condition_layer_20260630_source_20260630_for_20260701_v1';
DELETE FROM board_monitor_target WHERE source_version = 'condition_layer_20260630_source_20260630_for_20260701_v1';

DELETE FROM common_condition_quality_item WHERE run_id = 'condition_layer_20260630_source_20260630_for_20260701_v1';
DELETE FROM common_condition_run WHERE run_id = 'condition_layer_20260630_source_20260630_for_20260701_v1';

COMMIT;
