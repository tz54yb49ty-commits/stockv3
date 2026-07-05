-- N4 20260528 local trigger dry-run rollback guard.
-- Dry-run writes no database rows. No DELETE is required for N4 facts or events.
-- Report artifacts may be discarded from docs/sql if this dry-run is superseded.

BEGIN;

DO $$
DECLARE
  v_context_run_id TEXT := 'trigger_context_snapshot_20260529_condition_layer_20260528_source_20260528_v1';
  v_snapshot_run_id TEXT := 'realtime_snapshot_20260529_live2_outbox_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_context_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 local dry-run rollback guard blocked: N4 output outbox refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = v_snapshot_run_id
    AND NOT (
      source_layer = 'N3_market_data'
      AND event_type = 'MarketSnapshotUpdated'
      AND status = 'pending'
    );
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 local dry-run rollback guard blocked: non-allowlisted upstream input outbox refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id IN (v_context_run_id, v_snapshot_run_id);
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 local dry-run rollback guard blocked: scoped inbox refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%' || v_context_run_id || '%'
     OR checkpoint_payload::text LIKE '%' || v_snapshot_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 local dry-run rollback guard blocked: checkpoint refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_trigger_match WHERE run_id = v_context_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 local dry-run rollback guard blocked: trigger_match refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_trigger_state WHERE run_id = v_context_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 local dry-run rollback guard blocked: trigger_state refs = %', v_count;
  END IF;
END $$;

COMMIT;
