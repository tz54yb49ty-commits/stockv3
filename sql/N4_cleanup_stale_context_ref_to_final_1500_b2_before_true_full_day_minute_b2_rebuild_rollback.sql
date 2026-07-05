-- N4 stale context snapshot rollback before true full-day minute B2 rebuild.
-- Scope: trigger_context_run_id=trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
-- Does not touch N2/N3 metric facts, N4 execute rows, N5/N6/user/sim/position/order tables.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
  v_count BIGINT;
BEGIN
  IF current_setting('ashare_v3.allow_n4_context_snapshot_rollback_run_id', true) <> v_run_id THEN
    RAISE EXCEPTION 'hard-fail: set ashare_v3.allow_n4_context_snapshot_rollback_run_id=% before DELETE', v_run_id;
  END IF;

  SELECT count(*) INTO v_count FROM common_trigger_run WHERE run_id <> v_run_id AND raw_json->>'trigger_context_run_id' = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 context rollback blocked: child N4 execute refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_trigger_state WHERE run_id = v_run_id OR raw_json::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 context rollback blocked: trigger state refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_trigger_match WHERE run_id = v_run_id OR raw_json::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 context rollback blocked: trigger match refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_event_outbox WHERE source_layer = 'N4_trigger' AND (source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%');
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 context rollback blocked: N4 outbox refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_event_inbox WHERE source_layer = 'N4_trigger' AND source_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 context rollback blocked: downstream inbox refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_event_consumer_checkpoint WHERE source_layer = 'N4_trigger' AND checkpoint_payload::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 context rollback blocked: checkpoint refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_action_run WHERE source_trigger_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 context rollback blocked: N5 action run refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_action_event WHERE source_trigger_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 context rollback blocked: N5 action event refs = %', v_count;
  END IF;
END $$;

DELETE FROM common_trigger_quality_item WHERE run_id = 'trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM stock_trigger_context_snapshot WHERE run_id = 'trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM index_trigger_context_snapshot WHERE run_id = 'trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM board_trigger_context_snapshot WHERE run_id = 'trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM common_trigger_run WHERE run_id = 'trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';

COMMIT;
