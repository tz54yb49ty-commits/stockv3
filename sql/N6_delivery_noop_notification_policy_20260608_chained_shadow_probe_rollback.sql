BEGIN;

DO $$
DECLARE
  v_delivery_materialization_run_id CONSTANT TEXT := 'n6_delivery_noop_materialization_20260608_chained_shadow_probe';
  v_source_projection_run_id CONSTANT TEXT := 'n4_n5_n6_chained_shadow_smoke_20260608_projection_probe';
  v_source_action_run_id CONSTANT TEXT := 'n4_n5_n6_chained_shadow_smoke_20260608_action_probe';
  v_count BIGINT;
  v_guard RECORD;
  v_guard_table REGCLASS;
  v_predicates TEXT[];
  v_removed INTEGER;
BEGIN
  IF current_setting('n6.rollback_user_confirmed', true) IS DISTINCT FROM 'true' THEN
    RAISE EXCEPTION 'N6 delivery noop rollback blocked: set n6.rollback_user_confirmed=true only in an approved rollback final gate';
  END IF;

  SELECT count(*) INTO v_count
    FROM common_event_outbox
   WHERE source_layer = 'N5_action'
     AND source_run_id = v_source_action_run_id
     AND status IN ('delivered', 'delivering');

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 delivery noop rollback blocked: N5 source outbox has delivered or delivering rows: %', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_notification_queue
   WHERE user_projection_run_id = v_source_projection_run_id
     AND notification_source = 'n5_action_blocked'
     AND queue_status = 'queued_only'
     AND channel = 'broadcast_queue';

  IF v_count <> 50 THEN
    RAISE EXCEPTION 'N6 delivery noop rollback blocked: source queued-only row count changed: %', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_notification_queue
   WHERE user_projection_run_id = v_source_projection_run_id
     AND notification_source = 'n6_delivery_materialized_noop'
     AND projection_policy = 'noop_local_preview_materialized_no_delivery'
     AND notification_payload_json->>'delivery_materialization_run_id' = v_delivery_materialization_run_id;

  IF v_count = 0 THEN
    RAISE EXCEPTION 'N6 delivery noop rollback blocked: no target noop rows found for %', v_delivery_materialization_run_id;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_notification_queue
   WHERE user_projection_run_id = v_source_projection_run_id
     AND notification_source = 'n6_delivery_materialized_noop'
     AND projection_policy = 'noop_local_preview_materialized_no_delivery'
     AND notification_payload_json->>'delivery_materialization_run_id' = v_delivery_materialization_run_id
     AND queue_status <> 'ready_for_future_push';

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 delivery noop rollback blocked: target noop rows changed status: %', v_count;
  END IF;

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
        ('sim', 'user_sim_position'),
        ('order_trade', 'common_order'),
        ('order_trade', 'common_trade')
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
      v_predicates := v_predicates || format('%I = %L', 'delivery_materialization_run_id', v_delivery_materialization_run_id);
    END IF;

    IF EXISTS (
      SELECT 1 FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = v_guard.table_name
         AND column_name = 'delivery_run_id'
    ) THEN
      v_predicates := v_predicates || format('%I = %L', 'delivery_run_id', v_delivery_materialization_run_id);
    END IF;

    IF EXISTS (
      SELECT 1 FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = v_guard.table_name
         AND column_name = 'user_notification_queue_id'
    ) THEN
      v_predicates := v_predicates || format(
        '%I IN (SELECT user_notification_queue_id FROM user_notification_queue WHERE user_projection_run_id = %L AND notification_source = %L AND notification_payload_json->>%L = %L)',
        'user_notification_queue_id',
        v_source_projection_run_id,
        'n6_delivery_materialized_noop',
        'delivery_materialization_run_id',
        v_delivery_materialization_run_id
      );
    END IF;

    IF EXISTS (
      SELECT 1 FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = v_guard.table_name
         AND column_name = 'raw_json'
    ) THEN
      v_predicates := v_predicates || format('%I::text LIKE %L', 'raw_json', '%' || v_delivery_materialization_run_id || '%');
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
      RAISE EXCEPTION 'N6 delivery noop rollback blocked: linked % refs found in %, rows=%, delivery_run=%',
        v_guard.category, v_guard.table_name, v_count, v_delivery_materialization_run_id;
    END IF;
  END LOOP;

  DELETE FROM user_notification_queue
   WHERE user_projection_run_id = v_source_projection_run_id
     AND notification_source = 'n6_delivery_materialized_noop'
     AND projection_policy = 'noop_local_preview_materialized_no_delivery'
     AND notification_payload_json->>'delivery_materialization_run_id' = v_delivery_materialization_run_id;
  GET DIAGNOSTICS v_removed = ROW_COUNT;

  RAISE NOTICE 'N6 delivery noop rollback removed target rows: %', v_removed;
END $$;

COMMIT;
