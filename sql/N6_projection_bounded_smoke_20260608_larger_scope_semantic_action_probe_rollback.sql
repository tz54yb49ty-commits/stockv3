-- N6 projection bounded smoke rollback guard.
-- Scope: scoped N6 projection smoke rows for one reviewed user_projection_run_id.
-- Boundary: preserve N5 action facts/outbox status, N4 trigger facts, N3/N2/N1 facts, existing N5 lineages, delivery, sim, order, trade, position, and old system.

BEGIN;

DO $$
BEGIN
  IF current_setting('n6.rollback_authorized', true) IS DISTINCT FROM 'CONFIRMED_N6_PROJECTION_BOUNDED_SMOKE_20260608' THEN
    RAISE EXCEPTION 'N6 projection bounded smoke rollback is disabled by default; require reviewed rollback final gate and SET n6.rollback_authorized=CONFIRMED_N6_PROJECTION_BOUNDED_SMOKE_20260608';
  END IF;
END $$;

SET LOCAL n6.rollback_user_projection_run_id = 'user_projection_bounded_smoke_20260608_larger_scope_semantic_action_probe__n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe';
SET LOCAL n6.rollback_source_action_run_id = 'n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe';

DO $$
DECLARE
  v_run_id TEXT := current_setting('n6.rollback_user_projection_run_id', true);
  v_expected_source_action_run_id TEXT := current_setting('n6.rollback_source_action_run_id', true);
  v_source_action_run_id TEXT;
  v_count BIGINT;
  v_guard RECORD;
  v_guard_table REGCLASS;
  v_predicates TEXT[];
  v_removed_notifications INTEGER;
  v_removed_cards INTEGER;
  v_removed_projections INTEGER;
  v_removed_runs INTEGER;
BEGIN
  IF v_run_id IS NULL OR btrim(v_run_id) = '' THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: n6.rollback_user_projection_run_id is not set';
  END IF;
  IF v_expected_source_action_run_id IS NULL OR btrim(v_expected_source_action_run_id) = '' THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: n6.rollback_source_action_run_id is not set';
  END IF;

  SELECT count(*) INTO v_count FROM user_projection_run WHERE user_projection_run_id = v_run_id;
  IF v_count <> 1 THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: expected 1 user_projection_run row for %, found %', v_run_id, v_count;
  END IF;

  SELECT source_action_run_id INTO v_source_action_run_id FROM user_projection_run WHERE user_projection_run_id = v_run_id;
  IF v_source_action_run_id IS DISTINCT FROM v_expected_source_action_run_id THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: source_action_run_id mismatch for %, expected %, actual %', v_run_id, v_expected_source_action_run_id, v_source_action_run_id;
  END IF;

  SELECT count(*) INTO v_count
    FROM common_event_outbox
   WHERE source_layer = 'N5_action'
     AND source_run_id = v_expected_source_action_run_id
     AND event_type IN ('ActionBlocked', 'ActionExecuted')
     AND status IN ('delivered', 'delivering');
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: N5 source outbox delivered/delivering rows found for source %, rows=%', v_expected_source_action_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_signal_decision d
    JOIN user_signal_projection p ON p.user_signal_projection_id = d.user_signal_projection_id
   WHERE p.user_projection_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: user_signal_decision has % rows for run %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_sim_order o
   WHERE o.sim_run_id = v_run_id
      OR o.user_signal_projection_id IN (SELECT user_signal_projection_id FROM user_signal_projection WHERE user_projection_run_id = v_run_id);
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: user_sim_order has % rows linked to run %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count FROM user_sim_trade WHERE sim_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: user_sim_trade has % rows linked to run %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count FROM user_sim_position WHERE sim_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: user_sim_position has % rows linked to run %', v_count, v_run_id;
  END IF;

  FOR v_guard IN
    SELECT category, table_name
      FROM (VALUES
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
        ('virtual', 'n6_virtual_pnl_snapshot')
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
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = v_guard.table_name AND column_name = 'source_action_run_id') THEN
      v_predicates := v_predicates || format('%I = %L', 'source_action_run_id', v_expected_source_action_run_id);
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = v_guard.table_name AND column_name = 'source_run_id') THEN
      v_predicates := v_predicates || format('%I = %L', 'source_run_id', v_run_id);
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = v_guard.table_name AND column_name = 'run_id') THEN
      v_predicates := v_predicates || format('%I = %L', 'run_id', v_run_id);
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = v_guard.table_name AND column_name = 'sim_run_id') THEN
      v_predicates := v_predicates || format('%I = %L', 'sim_run_id', v_run_id);
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = v_guard.table_name AND column_name = 'rollback_scope') THEN
      v_predicates := v_predicates || format('%I = %L', 'rollback_scope', v_run_id);
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
      RAISE EXCEPTION 'N6 projection rollback blocked: linked % refs found in %, rows=%, run=%', v_guard.category, v_guard.table_name, v_count, v_run_id;
    END IF;
  END LOOP;

  DELETE FROM user_notification_queue WHERE user_projection_run_id = v_run_id;
  GET DIAGNOSTICS v_removed_notifications = ROW_COUNT;
  DELETE FROM user_signal_card WHERE user_projection_run_id = v_run_id;
  GET DIAGNOSTICS v_removed_cards = ROW_COUNT;
  DELETE FROM user_signal_projection WHERE user_projection_run_id = v_run_id;
  GET DIAGNOSTICS v_removed_projections = ROW_COUNT;
  DELETE FROM user_projection_run WHERE user_projection_run_id = v_run_id;
  GET DIAGNOSTICS v_removed_runs = ROW_COUNT;

  IF v_removed_runs <> 1 THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: expected to remove 1 projection run, removed %', v_removed_runs;
  END IF;

  RAISE NOTICE 'N6 projection rollback completed for %, notification_rows=%, card_rows=%, projection_rows=%, run_rows=%',
    v_run_id, v_removed_notifications, v_removed_cards, v_removed_projections, v_removed_runs;
END $$;

COMMIT;
