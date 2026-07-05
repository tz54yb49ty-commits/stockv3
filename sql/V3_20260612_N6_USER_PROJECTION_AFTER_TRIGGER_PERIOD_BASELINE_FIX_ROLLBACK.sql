-- V3 20260612 N6 user projection after trigger-period baseline fix rollback.
-- Scope: only the fixed projection run below.
-- Boundary: no N5/N4/N3/N2/N1 mutation, no N5 outbox/inbox/checkpoint
-- mutation, no scheduler/worker, no delivery/push/voice/mobile, no
-- sim/position/PnL, no proposal/order/trade, no real trade, and no old system
-- touch.

BEGIN;

SET LOCAL n6.rollback_user_projection_run_id =
  'v3_n6_user_projection_20260612_after_n5_trigger_period_baseline_fix_v1';

DO $$
DECLARE
  v_run_id TEXT := current_setting('n6.rollback_user_projection_run_id', true);
  v_source_action_run_id TEXT;
  v_count BIGINT;
  v_guard RECORD;
  v_guard_table REGCLASS;
  v_predicates TEXT[];
  v_deleted_notifications INTEGER;
  v_deleted_cards INTEGER;
  v_deleted_projections INTEGER;
  v_deleted_runs INTEGER;
BEGIN
  IF v_run_id IS NULL OR btrim(v_run_id) = '' THEN
    RAISE EXCEPTION 'V3 20260612 N6 rollback blocked: n6.rollback_user_projection_run_id is not set';
  END IF;

  IF v_run_id <> 'v3_n6_user_projection_20260612_after_n5_trigger_period_baseline_fix_v1' THEN
    RAISE EXCEPTION 'V3 20260612 N6 rollback blocked: unexpected run id %', v_run_id;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_projection_run
   WHERE user_projection_run_id = v_run_id;
  IF v_count <> 1 THEN
    RAISE EXCEPTION 'V3 20260612 N6 rollback blocked: expected 1 user_projection_run row for %, found %', v_run_id, v_count;
  END IF;

  SELECT source_action_run_id INTO v_source_action_run_id
    FROM user_projection_run
   WHERE user_projection_run_id = v_run_id;

  IF v_source_action_run_id <> 'v3_n5_action_replay_20260612_after_n4_trigger_period_baseline_fix_v1' THEN
    RAISE EXCEPTION 'V3 20260612 N6 rollback blocked: unexpected source_action_run_id % for run %', v_source_action_run_id, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_signal_decision d
    LEFT JOIN user_signal_projection p
      ON p.user_signal_projection_id = d.user_signal_projection_id
    LEFT JOIN user_signal_card c
      ON c.user_signal_card_id = d.user_signal_card_id
   WHERE p.user_projection_run_id = v_run_id
      OR c.user_projection_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'V3 20260612 N6 rollback blocked: user_signal_decision has % rows linked to run %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_sim_order o
   WHERE o.sim_run_id = v_run_id
      OR o.user_signal_projection_id IN (
           SELECT user_signal_projection_id
             FROM user_signal_projection
            WHERE user_projection_run_id = v_run_id
         );
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'V3 20260612 N6 rollback blocked: user_sim_order has % rows linked to run %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count FROM user_sim_trade WHERE sim_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'V3 20260612 N6 rollback blocked: user_sim_trade has % rows linked to run %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count FROM user_sim_position WHERE sim_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'V3 20260612 N6 rollback blocked: user_sim_position has % rows linked to run %', v_count, v_run_id;
  END IF;

  FOR v_guard IN
    SELECT category, table_name
      FROM (VALUES
        ('delivery', 'common_event_delivery_attempt'),
        ('delivery', 'user_notification_delivery'),
        ('delivery', 'user_delivery_event'),
        ('push', 'user_push_delivery'),
        ('voice', 'user_voice_delivery'),
        ('voice', 'user_voice_queue'),
        ('voice', 'user_voice_delivery_log'),
        ('mobile', 'user_mobile_delivery'),
        ('mobile', 'user_mobile_queue'),
        ('mobile', 'user_device_ack'),
        ('position', 'user_position_projection'),
        ('position', 'user_position_state'),
        ('position', 'common_position_state'),
        ('position', 'common_position_event'),
        ('virtual', 'n6_virtual_order'),
        ('virtual', 'n6_virtual_trade'),
        ('virtual', 'n6_virtual_position'),
        ('virtual', 'n6_virtual_position_event'),
        ('virtual', 'n6_virtual_pnl_snapshot'),
        ('proposal', 'n6_virtual_order_proposal'),
        ('order', 'n6_virtual_order'),
        ('trade', 'n6_virtual_trade'),
        ('real_trade', 'real_trade_order'),
        ('real_trade', 'real_trade_execution')
      ) AS guard(category, table_name)
  LOOP
    v_guard_table := to_regclass('public.' || quote_ident(v_guard.table_name));
    IF v_guard_table IS NULL THEN
      CONTINUE;
    END IF;

    v_predicates := ARRAY[]::TEXT[];

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = v_guard.table_name AND column_name = 'user_projection_run_id') THEN
      v_predicates := v_predicates || format('%I = %L', 'user_projection_run_id', v_run_id);
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = v_guard.table_name AND column_name = 'projection_run_id') THEN
      v_predicates := v_predicates || format('%I = %L', 'projection_run_id', v_run_id);
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = v_guard.table_name AND column_name = 'run_id') THEN
      v_predicates := v_predicates || format('%I = %L', 'run_id', v_run_id);
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = v_guard.table_name AND column_name = 'sim_run_id') THEN
      v_predicates := v_predicates || format('%I = %L', 'sim_run_id', v_run_id);
    END IF;
    IF v_source_action_run_id IS NOT NULL AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = v_guard.table_name AND column_name = 'source_action_run_id') THEN
      v_predicates := v_predicates || format('%I = %L', 'source_action_run_id', v_source_action_run_id);
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = v_guard.table_name AND column_name = 'source_run_id') THEN
      v_predicates := v_predicates || format('%I = %L', 'source_run_id', v_run_id);
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = v_guard.table_name AND column_name = 'user_signal_projection_id') THEN
      v_predicates := v_predicates || format('%I IN (SELECT user_signal_projection_id FROM user_signal_projection WHERE user_projection_run_id = %L)', 'user_signal_projection_id', v_run_id);
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = v_guard.table_name AND column_name = 'user_signal_card_id') THEN
      v_predicates := v_predicates || format('%I IN (SELECT user_signal_card_id FROM user_signal_card WHERE user_projection_run_id = %L)', 'user_signal_card_id', v_run_id);
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = v_guard.table_name AND column_name = 'user_notification_queue_id') THEN
      v_predicates := v_predicates || format('%I IN (SELECT user_notification_queue_id FROM user_notification_queue WHERE user_projection_run_id = %L)', 'user_notification_queue_id', v_run_id);
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = v_guard.table_name AND column_name = 'source_event_id') THEN
      v_predicates := v_predicates || format('%I IN (SELECT source_event_id FROM user_signal_projection WHERE user_projection_run_id = %L)', 'source_event_id', v_run_id);
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = v_guard.table_name AND column_name = 'source_action_event_id') THEN
      v_predicates := v_predicates || format('%I IN (SELECT source_action_event_id FROM user_signal_projection WHERE user_projection_run_id = %L)', 'source_action_event_id', v_run_id);
    END IF;

    IF array_length(v_predicates, 1) IS NULL THEN
      CONTINUE;
    END IF;

    EXECUTE format('SELECT count(*) FROM %s WHERE %s', v_guard_table, array_to_string(v_predicates, ' OR ')) INTO v_count;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'V3 20260612 N6 rollback blocked: linked % refs found in %, rows=%, run=%', v_guard.category, v_guard.table_name, v_count, v_run_id;
    END IF;
  END LOOP;

  DELETE FROM user_notification_queue WHERE user_projection_run_id = v_run_id;
  GET DIAGNOSTICS v_deleted_notifications = ROW_COUNT;
  DELETE FROM user_signal_card WHERE user_projection_run_id = v_run_id;
  GET DIAGNOSTICS v_deleted_cards = ROW_COUNT;
  DELETE FROM user_signal_projection WHERE user_projection_run_id = v_run_id;
  GET DIAGNOSTICS v_deleted_projections = ROW_COUNT;
  DELETE FROM user_projection_run WHERE user_projection_run_id = v_run_id;
  GET DIAGNOSTICS v_deleted_runs = ROW_COUNT;

  IF v_deleted_runs <> 1 THEN
    RAISE EXCEPTION 'V3 20260612 N6 rollback blocked: expected to delete 1 projection run, deleted %', v_deleted_runs;
  END IF;

  RAISE NOTICE 'V3 20260612 N6 rollback completed for %, notification_rows=%, card_rows=%, projection_rows=%, run_rows=%',
    v_run_id, v_deleted_notifications, v_deleted_cards, v_deleted_projections, v_deleted_runs;
END $$;

COMMIT;
