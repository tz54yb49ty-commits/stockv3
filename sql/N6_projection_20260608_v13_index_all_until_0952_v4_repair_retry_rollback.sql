-- N6 projection shadow execute business rollback for 20260608 v13 index-all until 09:52 v4 repair retry.
-- Generated from sql/N6_projection_business_rollback.sql with a reviewed scoped run id.
-- Do not execute without explicit user confirmation and a reviewed
-- user_projection_run_id.
--
-- Scope: delete only N6 projection rows created by one future shadow
-- projection execute run.
--
-- Boundary: no N1-N5 mutation, no N5 outbox status update, no N5
-- inbox/checkpoint update, no admin/profile rollback, no session rollback,
-- no watchlist rollback, no sim rollback, no push/voice/mobile rollback,
-- and no real trade rollback.
--
-- Usage draft:
--   1. Review the target user_projection_run_id.
--   2. Uncomment the SET LOCAL line below and replace the placeholder.
--   3. Execute the file only under a reviewed N6 rollback gate.

BEGIN;

SET LOCAL n6.rollback_user_projection_run_id = 'user_projection_shadow_20260608_v13_index_all_until_0952_v4_repair_retry__action_consumer_execute_20260608_v13_index_all_until_0952_v4_repair_retry';

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
    RAISE EXCEPTION 'N6 projection rollback blocked: n6.rollback_user_projection_run_id is not set';
  END IF;

  SELECT count(*) INTO v_count
    FROM user_projection_run
   WHERE user_projection_run_id = v_run_id;
  IF v_count <> 1 THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: expected 1 user_projection_run row for %, found %', v_run_id, v_count;
  END IF;

  SELECT source_action_run_id INTO v_source_action_run_id
    FROM user_projection_run
   WHERE user_projection_run_id = v_run_id;

  SELECT count(*) INTO v_count
    FROM user_signal_decision d
    JOIN user_signal_projection p
      ON p.user_signal_projection_id = d.user_signal_projection_id
   WHERE p.user_projection_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: user_signal_decision has % rows for run %', v_count, v_run_id;
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
    RAISE EXCEPTION 'N6 projection rollback blocked: user_sim_order has % rows linked to run %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_sim_trade
   WHERE sim_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: user_sim_trade has % rows linked to run %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_sim_position
   WHERE sim_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: user_sim_position has % rows linked to run %', v_count, v_run_id;
  END IF;

  -- Future voice/mobile/position tables are optional in early N6 deployments.
  -- They must not make this rollback fail merely because the tables are absent,
  -- but any linked downstream refs must hard-fail before the first DELETE.
  FOR v_guard IN
    SELECT category, table_name
      FROM (VALUES
        ('voice', 'user_voice_delivery'),
        ('voice', 'user_voice_queue'),
        ('voice', 'user_voice_delivery_log'),
        ('mobile', 'user_mobile_delivery'),
        ('mobile', 'user_mobile_queue'),
        ('mobile', 'user_device_ack'),
        ('mobile', 'user_notification_delivery'),
        ('position', 'user_position_projection'),
        ('position', 'user_position_state'),
        ('position', 'common_position_state'),
        ('position', 'common_position_event')
      ) AS guard(category, table_name)
  LOOP
    v_guard_table := to_regclass('public.' || quote_ident(v_guard.table_name));
    IF v_guard_table IS NULL THEN
      CONTINUE;
    END IF;

    v_predicates := ARRAY[]::TEXT[];

    IF EXISTS (
      SELECT 1 FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = v_guard.table_name
         AND column_name = 'user_projection_run_id'
    ) THEN
      v_predicates := v_predicates || format('%I = %L', 'user_projection_run_id', v_run_id);
    END IF;

    IF EXISTS (
      SELECT 1 FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = v_guard.table_name
         AND column_name = 'projection_run_id'
    ) THEN
      v_predicates := v_predicates || format('%I = %L', 'projection_run_id', v_run_id);
    END IF;

    IF v_source_action_run_id IS NOT NULL AND EXISTS (
      SELECT 1 FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = v_guard.table_name
         AND column_name = 'source_action_run_id'
    ) THEN
      v_predicates := v_predicates || format('%I = %L', 'source_action_run_id', v_source_action_run_id);
    END IF;

    IF EXISTS (
      SELECT 1 FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = v_guard.table_name
         AND column_name = 'user_signal_projection_id'
    ) THEN
      v_predicates := v_predicates || format(
        '%I IN (SELECT user_signal_projection_id FROM user_signal_projection WHERE user_projection_run_id = %L)',
        'user_signal_projection_id',
        v_run_id
      );
    END IF;

    IF EXISTS (
      SELECT 1 FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = v_guard.table_name
         AND column_name = 'user_signal_card_id'
    ) THEN
      v_predicates := v_predicates || format(
        '%I IN (SELECT user_signal_card_id FROM user_signal_card WHERE user_projection_run_id = %L)',
        'user_signal_card_id',
        v_run_id
      );
    END IF;

    IF EXISTS (
      SELECT 1 FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = v_guard.table_name
         AND column_name = 'user_notification_queue_id'
    ) THEN
      v_predicates := v_predicates || format(
        '%I IN (SELECT user_notification_queue_id FROM user_notification_queue WHERE user_projection_run_id = %L)',
        'user_notification_queue_id',
        v_run_id
      );
    END IF;

    IF EXISTS (
      SELECT 1 FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = v_guard.table_name
         AND column_name = 'source_event_id'
    ) THEN
      v_predicates := v_predicates || format(
        '%I IN (SELECT source_event_id FROM user_signal_projection WHERE user_projection_run_id = %L)',
        'source_event_id',
        v_run_id
      );
    END IF;

    IF EXISTS (
      SELECT 1 FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = v_guard.table_name
         AND column_name = 'source_action_event_id'
    ) THEN
      v_predicates := v_predicates || format(
        '%I IN (SELECT source_action_event_id FROM user_signal_projection WHERE user_projection_run_id = %L)',
        'source_action_event_id',
        v_run_id
      );
    END IF;

    IF array_length(v_predicates, 1) IS NULL THEN
      CONTINUE;
    END IF;

    EXECUTE format(
      'SELECT count(*) FROM %s WHERE %s',
      v_guard_table,
      array_to_string(v_predicates, ' OR ')
    )
    INTO v_count;

    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N6 projection rollback blocked: linked % refs found in %, rows=%, run=%',
        v_guard.category, v_guard.table_name, v_count, v_run_id;
    END IF;
  END LOOP;

  DELETE FROM user_notification_queue
   WHERE user_projection_run_id = v_run_id;
  GET DIAGNOSTICS v_deleted_notifications = ROW_COUNT;

  DELETE FROM user_signal_card
   WHERE user_projection_run_id = v_run_id;
  GET DIAGNOSTICS v_deleted_cards = ROW_COUNT;

  DELETE FROM user_signal_projection
   WHERE user_projection_run_id = v_run_id;
  GET DIAGNOSTICS v_deleted_projections = ROW_COUNT;

  DELETE FROM user_projection_run
   WHERE user_projection_run_id = v_run_id;
  GET DIAGNOSTICS v_deleted_runs = ROW_COUNT;

  IF v_deleted_runs <> 1 THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: expected to delete 1 projection run, deleted %', v_deleted_runs;
  END IF;

  RAISE NOTICE 'N6 projection rollback completed for %, notification_rows=%, card_rows=%, projection_rows=%, run_rows=%',
    v_run_id, v_deleted_notifications, v_deleted_cards, v_deleted_projections, v_deleted_runs;
END $$;

COMMIT;
