-- N4 canonical trigger execute rollback.
-- Scope: execute_run_id=trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1
-- Use only before downstream N5/N6 consumption. Does not touch N2/N3 facts or context snapshots.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_run_id
    AND status IN ('delivering', 'delivered');
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 canonical trigger execute rollback blocked: outbox delivered/delivering refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 canonical trigger execute rollback blocked: downstream inbox refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer = 'N4_trigger'
    AND checkpoint_payload::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 canonical trigger execute rollback blocked: downstream checkpoint refs = %', v_count;
  END IF;

  IF to_regclass('public.common_action_run') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_action_run WHERE source_trigger_run_id = $1'
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 canonical trigger execute rollback blocked: N5 action run refs = %', v_count;
    END IF;
  END IF;
END $$;

DELETE FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = 'trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1';

DELETE FROM common_trigger_match
WHERE run_id = 'trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1';

DELETE FROM common_trigger_state
WHERE run_id = 'trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1';

DELETE FROM common_trigger_quality_item
WHERE run_id = 'trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1';

DELETE FROM common_trigger_run
WHERE run_id = 'trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1';

COMMIT;
