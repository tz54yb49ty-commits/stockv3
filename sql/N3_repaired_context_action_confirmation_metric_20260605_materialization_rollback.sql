-- N3 action-confirmation metric 20260605 repaired-context materialization business rollback.
-- Scope: delete only rows for projection_run_id=action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1.
-- Hard-fail before DELETE when event infra, downstream N4/N5/N6 refs,
-- downstream_layers_touched, or worker_started indicate consumption.

\set ON_ERROR_STOP on
\set projection_run_id 'action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1'

SELECT set_config('app.projection_run_id', :'projection_run_id', false);

DO $$
DECLARE
  target_run_id TEXT := current_setting('app.projection_run_id');
  outbox_refs BIGINT;
  inbox_refs BIGINT;
  checkpoint_refs BIGINT;
  trigger_refs BIGINT;
  action_refs BIGINT;
  n6_refs BIGINT;
  v_count BIGINT;
  touched_refs BIGINT;
  worker_refs BIGINT;
BEGIN
  n6_refs := 0;

  SELECT count(*) INTO outbox_refs
  FROM common_event_outbox
  WHERE source_run_id = target_run_id OR payload_json::TEXT LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO inbox_refs
  FROM common_event_inbox
  WHERE source_run_id = target_run_id OR payload_json::TEXT LIKE '%' || target_run_id || '%' OR raw_json::TEXT LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || target_run_id || '%' OR last_event_id LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO trigger_refs
  FROM common_trigger_match
  WHERE raw_json::TEXT LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO action_refs
  FROM common_action_event
  WHERE trace_json::TEXT LIKE '%' || target_run_id || '%';

  IF to_regclass('public.user_card_projection') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.user_card_projection AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count
      USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.user_signal_projection') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.user_signal_projection AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count
      USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.user_signal_card') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.user_signal_card AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count
      USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.user_notification_queue') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.user_notification_queue AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count
      USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.user_sim_order') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.user_sim_order AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count
      USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.user_sim_trade') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.user_sim_trade AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count
      USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.user_sim_position') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.user_sim_position AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count
      USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.n6_virtual_account') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.n6_virtual_account AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count
      USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.n6_virtual_order') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.n6_virtual_order AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count
      USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.n6_virtual_trade') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.n6_virtual_trade AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count
      USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.n6_virtual_position') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.n6_virtual_position AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count
      USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.n6_virtual_position_event') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.n6_virtual_position_event AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count
      USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.n6_virtual_pnl_snapshot') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.n6_virtual_pnl_snapshot AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count
      USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;

  SELECT count(*) INTO touched_refs
  FROM common_market_data_run
  WHERE run_id = target_run_id AND downstream_layers_touched = true;

  SELECT count(*) INTO worker_refs
  FROM common_market_data_run
  WHERE run_id = target_run_id AND worker_started = true;

  IF outbox_refs <> 0 OR inbox_refs <> 0 OR checkpoint_refs <> 0
     OR trigger_refs <> 0 OR action_refs <> 0 OR n6_refs <> 0
     OR touched_refs <> 0 OR worker_refs <> 0 THEN
    RAISE EXCEPTION
      'N3 action metric rollback blocked for %, outbox=%, inbox=%, checkpoint=%, trigger=%, action=%, n6=%, downstream_touched=%, worker=%',
      target_run_id, outbox_refs, inbox_refs, checkpoint_refs, trigger_refs, action_refs, n6_refs, touched_refs, worker_refs;
  END IF;
END $$;

BEGIN;

DELETE FROM stock_action_confirmation_projection_metric
WHERE projection_run_id = :'projection_run_id';

DELETE FROM index_action_confirmation_projection_metric
WHERE projection_run_id = :'projection_run_id';

DELETE FROM board_action_confirmation_projection_metric
WHERE projection_run_id = :'projection_run_id';

DELETE FROM common_market_data_quality_item
WHERE run_id = :'projection_run_id'
  AND layer_scope = 'market_data_run'
  AND details ->> 'metric_scope' = 'action_confirmation_projection_metric';

DELETE FROM common_market_data_run
WHERE run_id = :'projection_run_id'
  AND downstream_layers_touched = false
  AND worker_started = false;

COMMIT;
