-- V3 20260612 N5 action replay rollback after N4 ordinary-trigger / 30m mark-only fix.
-- Scope:
--   action_run_id=v3_n5_action_replay_20260612_after_n4_mark_only_fix_v2
--   source_trigger_run_id=v3_n4_trigger_replay_20260612_after_n3_full_day_metric_mark_only_fix_v2
--   consumer_name=v3_n5_action_replay_20260612_mark_only_fix_consumer_v2
-- Default hard-fails before any row removal. Does not touch N3/N4 facts,
-- N4 outbox status, N6/user/sim/position/order/trade rows, or old system data.

BEGIN;

DO $$
DECLARE
  target_run_id text := 'v3_n5_action_replay_20260612_after_n4_mark_only_fix_v2';
  source_trigger_run_id text := 'v3_n4_trigger_replay_20260612_after_n3_full_day_metric_mark_only_fix_v2';
  target_consumer_name text := 'v3_n5_action_replay_20260612_mark_only_fix_consumer_v2';
  v_count bigint;
BEGIN
  IF current_setting('ashare_v3.allow_v3_20260612_n5_action_replay_after_n4_mark_only_fix_rollback', true) <> 'true' THEN
    RAISE EXCEPTION 'hard-fail: set ashare_v3.allow_v3_20260612_n5_action_replay_after_n4_mark_only_fix_rollback=true before DELETE';
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = target_run_id
    AND status IN ('delivering', 'delivered');
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: N5 outbox delivered/delivering refs=%', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = target_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: downstream inbox refs to N5 outbox=%', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE consumer_name <> target_consumer_name
    AND checkpoint_payload::text LIKE '%' || target_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: downstream checkpoint refs to N5 run=%', v_count;
  END IF;

  IF to_regclass('public.user_signal_projection') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_signal_projection WHERE row_to_json(user_signal_projection)::text LIKE $1'
    INTO v_count
    USING '%' || target_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'rollback blocked: user_signal_projection refs=%', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_signal_card') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_signal_card WHERE row_to_json(user_signal_card)::text LIKE $1'
    INTO v_count
    USING '%' || target_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'rollback blocked: user_signal_card refs=%', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_notification_queue') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_notification_queue WHERE row_to_json(user_notification_queue)::text LIKE $1'
    INTO v_count
    USING '%' || target_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'rollback blocked: user_notification_queue refs=%', v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_position_state') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_position_state WHERE row_to_json(common_position_state)::text LIKE $1'
    INTO v_count
    USING '%' || target_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'rollback blocked: common_position_state refs=%', v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_position_event') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_position_event WHERE row_to_json(common_position_event)::text LIKE $1'
    INTO v_count
    USING '%' || target_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'rollback blocked: common_position_event refs=%', v_count;
    END IF;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = source_trigger_run_id
    AND consumer_name NOT IN (target_consumer_name);
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: non-scoped consumer inbox refs to source N4 run=%', v_count;
  END IF;
END $$;

DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = 'v3_n5_action_replay_20260612_mark_only_fix_consumer_v2'
  AND source_layer = 'N4_trigger';

DELETE FROM common_event_inbox
WHERE consumer_name = 'v3_n5_action_replay_20260612_mark_only_fix_consumer_v2'
  AND source_run_id = 'v3_n4_trigger_replay_20260612_after_n3_full_day_metric_mark_only_fix_v2';

DELETE FROM common_event_outbox
WHERE source_run_id = 'v3_n5_action_replay_20260612_after_n4_mark_only_fix_v2';

DELETE FROM common_action_event
WHERE run_id = 'v3_n5_action_replay_20260612_after_n4_mark_only_fix_v2';

DELETE FROM stock_action_fact
WHERE run_id = 'v3_n5_action_replay_20260612_after_n4_mark_only_fix_v2';

DELETE FROM index_action_fact
WHERE run_id = 'v3_n5_action_replay_20260612_after_n4_mark_only_fix_v2';

DELETE FROM board_action_fact
WHERE run_id = 'v3_n5_action_replay_20260612_after_n4_mark_only_fix_v2';

DELETE FROM common_action_quality_item
WHERE run_id = 'v3_n5_action_replay_20260612_after_n4_mark_only_fix_v2';

DELETE FROM common_action_run
WHERE run_id = 'v3_n5_action_replay_20260612_after_n4_mark_only_fix_v2';

COMMIT;
