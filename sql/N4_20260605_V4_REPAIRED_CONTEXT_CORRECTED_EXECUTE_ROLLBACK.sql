-- N4 v4 corrected execute rollback.
-- Scope: execute_run_id=trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
-- Use only before downstream N5/N6 consumption. Does not touch upstream facts or context snapshots.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'trigger_execute_20260605_condition_layer_20260604_source_20260604_v1';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_run_id
    AND status IN ('delivering', 'delivered');
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: outbox delivered/delivering refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: downstream inbox refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer = 'N4_trigger'
    AND checkpoint_payload::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: downstream checkpoint refs = %', v_count;
  END IF;

  IF to_regclass('public.common_action_run') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_action_run WHERE source_trigger_run_id = $1'
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: N5 action run refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_action_event') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_action_event WHERE source_trigger_run_id = $1'
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: N5 action event refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_projection_run') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_projection_run
      WHERE source_action_run_id = $1
         OR source_n5_outbox_range::TEXT LIKE '%' || $1 || '%'
         OR quality_summary_json::TEXT LIKE '%' || $1 || '%'
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: N6 user_projection_run refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_signal_projection') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_signal_projection
      WHERE source_action_run_id = $1
         OR source_event_id = $1
         OR source_payload_json::TEXT LIKE '%' || $1 || '%'
         OR display_payload_json::TEXT LIKE '%' || $1 || '%'
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: N6 user_signal_projection refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_signal_card') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_signal_card
      WHERE source_action_run_id = $1
         OR source_event_id = $1
         OR card_payload_json::TEXT LIKE '%' || $1 || '%'
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: N6 user_signal_card refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_notification_queue') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_notification_queue
      WHERE source_action_run_id = $1
         OR source_event_id = $1
         OR notification_payload_json::TEXT LIKE '%' || $1 || '%'
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: N6 user_notification_queue refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_sim_order') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_sim_order
      WHERE sim_run_id = $1
         OR order_payload_json::TEXT LIKE '%' || $1 || '%'
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: N6 user_sim_order refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_sim_trade') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_sim_trade
      WHERE sim_run_id = $1
         OR trade_payload_json::TEXT LIKE '%' || $1 || '%'
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: N6 user_sim_trade refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_sim_position') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_sim_position
      WHERE sim_run_id = $1
         OR position_payload_json::TEXT LIKE '%' || $1 || '%'
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: N6 user_sim_position refs = %', v_count;
    END IF;
  END IF;
END $$;

DELETE FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = 'trigger_execute_20260605_condition_layer_20260604_source_20260604_v1';

DELETE FROM common_trigger_match
WHERE run_id = 'trigger_execute_20260605_condition_layer_20260604_source_20260604_v1';

DELETE FROM common_trigger_state
WHERE run_id = 'trigger_execute_20260605_condition_layer_20260604_source_20260604_v1';

DELETE FROM common_trigger_quality_item
WHERE run_id = 'trigger_execute_20260605_condition_layer_20260604_source_20260604_v1';

DELETE FROM common_trigger_run
WHERE run_id = 'trigger_execute_20260605_condition_layer_20260604_source_20260604_v1';

COMMIT;
