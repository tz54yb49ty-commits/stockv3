-- N6 20260603 delivery / notification materialization rollback draft.
-- Do not execute without explicit user confirmation and a reviewed
-- delivery_materialization_run_id.
--
-- Scope: delete only future no-op delivery materialization rows appended to
-- user_notification_queue. This rollback must not delete the original
-- n5_action_blocked / queued_only projection queue rows.
--
-- Boundary: no N5 outbox update, no N5 inbox/checkpoint update, no N1-N5
-- mutation, no provider delivery rollback, no push/voice/mobile/sim/position
-- rollback, and no real trade rollback.

BEGIN;

-- SET LOCAL n6.delivery_materialization_run_id = '<reviewed_delivery_materialization_run_id>';

DO $$
DECLARE
  v_delivery_run_id TEXT := current_setting('n6.delivery_materialization_run_id', true);
  v_count BIGINT;
  v_guard RECORD;
  v_guard_table REGCLASS;
  v_predicates TEXT[];
  v_deleted_notifications INTEGER;
BEGIN
  IF v_delivery_run_id IS NULL OR btrim(v_delivery_run_id) = '' THEN
    RAISE EXCEPTION 'N6 delivery rollback blocked: n6.delivery_materialization_run_id is not set';
  END IF;

  SELECT count(*) INTO v_count
    FROM user_notification_queue
   WHERE notification_source = 'n6_delivery_materialized_noop'
     AND notification_payload_json->>'delivery_materialization_run_id' = v_delivery_run_id;

  IF v_count = 0 THEN
    RAISE EXCEPTION 'N6 delivery rollback blocked: no materialized notification rows found for %', v_delivery_run_id;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_notification_queue
   WHERE notification_source = 'n6_delivery_materialized_noop'
     AND notification_payload_json->>'delivery_materialization_run_id' = v_delivery_run_id
     AND queue_status <> 'ready_for_future_push';

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 delivery rollback blocked: % materialized rows are no longer ready_for_future_push for %', v_count, v_delivery_run_id;
  END IF;

  -- Optional future delivery/push/voice/mobile/sim/position tables must not
  -- make rollback fail merely because they are absent, but linked refs must
  -- hard-fail before the first DELETE.
  FOR v_guard IN
    SELECT category, table_name
      FROM (VALUES
        ('event_delivery', 'common_event_delivery_attempt'),
        ('notification_delivery', 'user_notification_delivery'),
        ('voice', 'user_voice_delivery'),
        ('voice', 'user_voice_queue'),
        ('voice', 'user_voice_delivery_log'),
        ('mobile', 'user_mobile_delivery'),
        ('mobile', 'user_mobile_queue'),
        ('mobile', 'user_device_ack'),
        ('mobile', 'user_notification_delivery'),
        ('position', 'user_position_projection'),
        ('position', 'user_position_state'),
        ('sim', 'user_sim_order'),
        ('sim', 'user_sim_trade'),
        ('sim', 'user_sim_position')
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
         AND column_name = 'delivery_materialization_run_id'
    ) THEN
      v_predicates := v_predicates || format('%I = %L', 'delivery_materialization_run_id', v_delivery_run_id);
    END IF;

    IF EXISTS (
      SELECT 1 FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = v_guard.table_name
         AND column_name = 'delivery_run_id'
    ) THEN
      v_predicates := v_predicates || format('%I = %L', 'delivery_run_id', v_delivery_run_id);
    END IF;

    IF EXISTS (
      SELECT 1 FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = v_guard.table_name
         AND column_name = 'user_notification_queue_id'
    ) THEN
      v_predicates := v_predicates || format(
        '%I IN (SELECT user_notification_queue_id FROM user_notification_queue WHERE notification_source = %L AND notification_payload_json->>%L = %L)',
        'user_notification_queue_id',
        'n6_delivery_materialized_noop',
        'delivery_materialization_run_id',
        v_delivery_run_id
      );
    END IF;

    IF EXISTS (
      SELECT 1 FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = v_guard.table_name
         AND column_name = 'raw_json'
    ) THEN
      v_predicates := v_predicates || format('%I::text LIKE %L', 'raw_json', '%' || v_delivery_run_id || '%');
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
      RAISE EXCEPTION 'N6 delivery rollback blocked: linked % refs found in %, rows=%, delivery_run=%',
        v_guard.category, v_guard.table_name, v_count, v_delivery_run_id;
    END IF;
  END LOOP;

  DELETE FROM user_notification_queue
   WHERE notification_source = 'n6_delivery_materialized_noop'
     AND notification_payload_json->>'delivery_materialization_run_id' = v_delivery_run_id;
  GET DIAGNOSTICS v_deleted_notifications = ROW_COUNT;

  RAISE NOTICE 'N6 delivery rollback deleted materialized notification rows: %', v_deleted_notifications;
END $$;

COMMIT;
