-- V3 20260615 N3 action-confirmation metric rollback.
-- Scope: only target projection_run_id action_confirmation_projection_metric_20260615_until_1000_from_n4_production_semantic_replay_v1. Hard-fails before DELETE if event/downstream refs exist.
\set ON_ERROR_STOP on
BEGIN;
DO $$
DECLARE v_run_id TEXT := 'action_confirmation_projection_metric_20260615_until_1000_from_n4_production_semantic_replay_v1'; v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count FROM common_event_outbox WHERE source_run_id=v_run_id OR payload_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: outbox refs for % rows=%', v_run_id, v_count; END IF;
  SELECT count(*) INTO v_count FROM common_event_inbox WHERE source_run_id=v_run_id OR payload_json::TEXT LIKE '%' || v_run_id || '%' OR raw_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: inbox refs for % rows=%', v_run_id, v_count; END IF;
  SELECT count(*) INTO v_count FROM common_event_consumer_checkpoint WHERE checkpoint_payload::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: checkpoint refs for % rows=%', v_run_id, v_count; END IF;
  SELECT count(*) INTO v_count FROM common_action_event WHERE source_run_id=v_run_id OR trace_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: action refs for % rows=%', v_run_id, v_count; END IF;
END $$;
DELETE FROM stock_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260615_until_1000_from_n4_production_semantic_replay_v1';
DELETE FROM index_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260615_until_1000_from_n4_production_semantic_replay_v1';
DELETE FROM board_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260615_until_1000_from_n4_production_semantic_replay_v1';
DELETE FROM common_market_data_quality_item WHERE run_id = 'action_confirmation_projection_metric_20260615_until_1000_from_n4_production_semantic_replay_v1';
DELETE FROM common_market_data_run WHERE run_id = 'action_confirmation_projection_metric_20260615_until_1000_from_n4_production_semantic_replay_v1';
COMMIT;
