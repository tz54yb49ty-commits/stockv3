-- V3 20260612 N3 full-day action-confirmation metric rollback.
-- Scope: projection_run_id=v3_n3_action_confirmation_metric_20260612_full_day_replay_v1
-- Does not touch source minute facts, N4/N5/N6, outbox/inbox/checkpoint.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'v3_n3_action_confirmation_metric_20260612_full_day_replay_v1';
  v_count BIGINT;
BEGIN
  RAISE EXCEPTION 'V3 full-day metric rollback hard-fail: set reviewed session variable before DELETE';

  SELECT count(*) INTO v_count FROM common_event_outbox
  WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: outbox refs=%', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_event_inbox
  WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: inbox refs=%', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: checkpoint refs=%', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_trigger_run
  WHERE source_market_data_run_id = v_run_id OR raw_json::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: N4 refs=%', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_action_run
  WHERE source_trigger_run_id = v_run_id OR raw_json::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: N5 refs=%', v_count;
  END IF;
END $$;

DELETE FROM board_action_confirmation_projection_metric WHERE projection_run_id = 'v3_n3_action_confirmation_metric_20260612_full_day_replay_v1';
DELETE FROM index_action_confirmation_projection_metric WHERE projection_run_id = 'v3_n3_action_confirmation_metric_20260612_full_day_replay_v1';
DELETE FROM stock_action_confirmation_projection_metric WHERE projection_run_id = 'v3_n3_action_confirmation_metric_20260612_full_day_replay_v1';
DELETE FROM common_market_data_quality_item WHERE run_id = 'v3_n3_action_confirmation_metric_20260612_full_day_replay_v1';
DELETE FROM common_market_data_run WHERE run_id = 'v3_n3_action_confirmation_metric_20260612_full_day_replay_v1';

COMMIT;
