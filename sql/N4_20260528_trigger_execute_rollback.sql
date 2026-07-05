-- N4 20260528 standard trigger execute rollback draft.
-- Scope:
--   execute_run_id: trigger_execute_20260528_condition_layer_20260527_source_20260527_v1
--
-- This rollback only clears N4 outputs created by the future execute run.
-- It does not touch N4 context snapshot rows, N3 facts, N2 condition rows,
-- N5/N6/action/user/voice/mobile/sim/position, workers, or real trades.

BEGIN;

DO $$
DECLARE
  v_execute_run_id TEXT := 'trigger_execute_20260528_condition_layer_20260527_source_20260527_v1';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_execute_run_id
    AND status IN ('delivering', 'delivered');
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 rollback blocked: outbox delivering/delivered rows for % = %', v_execute_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_execute_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 rollback blocked: downstream inbox rows for % = %', v_execute_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer = 'N4_trigger'
    AND checkpoint_payload::text LIKE '%' || v_execute_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 rollback blocked: checkpoint refs for % = %', v_execute_run_id, v_count;
  END IF;

  IF to_regclass('public.common_action_run') IS NOT NULL THEN
    SELECT count(*) INTO v_count
    FROM common_action_run
    WHERE source_trigger_run_id = v_execute_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 rollback blocked: N5 action run refs for % = %', v_execute_run_id, v_count;
    END IF;
  END IF;
END $$;

DELETE FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = 'trigger_execute_20260528_condition_layer_20260527_source_20260527_v1';

DELETE FROM common_trigger_match
WHERE run_id = 'trigger_execute_20260528_condition_layer_20260527_source_20260527_v1';

DELETE FROM common_trigger_state
WHERE run_id = 'trigger_execute_20260528_condition_layer_20260527_source_20260527_v1';

DELETE FROM common_trigger_quality_item
WHERE run_id = 'trigger_execute_20260528_condition_layer_20260527_source_20260527_v1';

DELETE FROM common_trigger_run
WHERE run_id = 'trigger_execute_20260528_condition_layer_20260527_source_20260527_v1';

COMMIT;
