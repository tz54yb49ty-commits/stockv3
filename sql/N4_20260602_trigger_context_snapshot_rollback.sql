-- A-share monitor v3 N4 trigger context rollback.
-- Execute only after confirming this N4 context run has not been consumed downstream.
-- This rollback deletes only N4 trigger context/run/quality rows for one run_id.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'trigger_context_snapshot_20260602_condition_layer_20260601_source_20260601_v1';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N4 context rollback: outbox has % rows for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = v_run_id
     OR raw_json::TEXT LIKE '%' || v_run_id || '%'
     OR payload_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N4 context rollback: inbox has % rows for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N4 context rollback: checkpoint has % rows for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_trigger_match
  WHERE run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N4 context rollback: trigger_match has % rows for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_trigger_state
  WHERE run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N4 context rollback: trigger_state has % rows for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_action_run
  WHERE source_trigger_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N4 context rollback: N5 action_run has % rows for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_action_event
  WHERE source_trigger_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N4 context rollback: N5 action_event has % rows for %', v_count, v_run_id;
  END IF;
END $$;

DELETE FROM common_trigger_quality_item WHERE run_id = 'trigger_context_snapshot_20260602_condition_layer_20260601_source_20260601_v1';
DELETE FROM stock_trigger_context_snapshot WHERE run_id = 'trigger_context_snapshot_20260602_condition_layer_20260601_source_20260601_v1';
DELETE FROM index_trigger_context_snapshot WHERE run_id = 'trigger_context_snapshot_20260602_condition_layer_20260601_source_20260601_v1';
DELETE FROM board_trigger_context_snapshot WHERE run_id = 'trigger_context_snapshot_20260602_condition_layer_20260601_source_20260601_v1';
DELETE FROM common_trigger_run WHERE run_id = 'trigger_context_snapshot_20260602_condition_layer_20260601_source_20260601_v1';

COMMIT;

-- Boundary:
-- - Does not touch common_condition_run or condition tables.
-- - Does not touch common_market_data_* or market data fact tables.
-- - Does not touch common_event_outbox.
-- - Does not touch trigger_state / trigger_match because N4-3 never writes them.
-- - Does not touch action/user/voice/sim/position tables.
