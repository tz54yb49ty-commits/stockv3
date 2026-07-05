-- Rollback V3 20260612 N5 action replay after N4 state-machine v3.
-- Scope:
--   action_run_id = v3_n5_action_replay_20260612_after_n4_state_machine_v3
--   source_trigger_run_id = v3_n4_trigger_replay_20260612_after_n3_full_day_metric_state_machine_v3
--   consumer_name = v3_n5_action_replay_20260612_state_machine_consumer_v3
--
-- Safety:
--   Default hard-fails before any row removal.
--   Does not touch N3/N4 facts or N4 outbox status.
--   Blocks if N5 outbox has been delivered/delivering or if N6/user/sim/position refs exist.

DO $$
DECLARE
  v_action_run_id TEXT := 'v3_n5_action_replay_20260612_after_n4_state_machine_v3';
  v_source_trigger_run_id TEXT := 'v3_n4_trigger_replay_20260612_after_n3_full_day_metric_state_machine_v3';
  v_consumer_name TEXT := 'v3_n5_action_replay_20260612_state_machine_consumer_v3';
  v_count BIGINT;
BEGIN
  IF current_setting('ashare_v3.allow_v3_20260612_n5_state_machine_replay_rollback', true) <> 'true' THEN
    RAISE EXCEPTION
      'rollback blocked: set ashare_v3.allow_v3_20260612_n5_state_machine_replay_rollback=true in this session';
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = v_action_run_id
    AND status IN ('delivered', 'delivering');
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: delivered/delivering N5 outbox rows exist: %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = v_action_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: downstream inbox refs for N5 action run exist: %', v_count;
  END IF;

  SELECT
      COALESCE((SELECT count(*) FROM user_signal_projection WHERE source_action_run_id = v_action_run_id), 0)
    + COALESCE((SELECT count(*) FROM user_signal_card WHERE source_action_run_id = v_action_run_id), 0)
    + COALESCE((SELECT count(*) FROM user_notification_queue WHERE source_action_run_id = v_action_run_id), 0)
  INTO v_count;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: N6/user refs for N5 action run exist: %', v_count;
  END IF;

  SELECT
      COALESCE((SELECT count(*) FROM common_position_state), 0)
    + COALESCE((SELECT count(*) FROM common_position_event), 0)
  INTO v_count;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: position refs exist: %', v_count;
  END IF;

  DELETE FROM common_event_consumer_checkpoint
  WHERE consumer_name = v_consumer_name;

  DELETE FROM common_event_inbox
  WHERE consumer_name = v_consumer_name
    AND source_layer = 'N4_trigger'
    AND source_run_id = v_source_trigger_run_id;

  DELETE FROM common_event_outbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = v_action_run_id;

  DELETE FROM common_action_event
  WHERE run_id = v_action_run_id;

  DELETE FROM stock_action_fact
  WHERE run_id = v_action_run_id;

  DELETE FROM index_action_fact
  WHERE run_id = v_action_run_id;

  DELETE FROM board_action_fact
  WHERE run_id = v_action_run_id;

  DELETE FROM common_action_quality_item
  WHERE run_id = v_action_run_id;

  DELETE FROM common_action_run
  WHERE run_id = v_action_run_id;
END $$;
