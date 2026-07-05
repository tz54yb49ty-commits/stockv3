-- N3 20260615 action-confirmation metric coverage repair rollback.
-- Scope: delete only additive repair rows for:
-- action_confirmation_projection_metric_20260615_repaired_formal_price_amount_chain_coverage_repair_v1__n4_20260615_repaired_formal_price_amount_chain_replay_v1
-- This rollback must not delete the old 25-row metric run, N4 trigger facts/outbox,
-- N5/N6/user/sim/virtual rows, source N3 facts, or event infra rows.

\set ON_ERROR_STOP on

DO $$
DECLARE
  target_run_id TEXT := 'action_confirmation_projection_metric_20260615_repaired_formal_price_amount_chain_coverage_repair_v1__n4_20260615_repaired_formal_price_amount_chain_replay_v1';
  outbox_refs BIGINT := 0;
  inbox_refs BIGINT := 0;
  checkpoint_refs BIGINT := 0;
  trigger_refs BIGINT := 0;
  action_refs BIGINT := 0;
  n6_refs BIGINT := 0;
  v_count BIGINT := 0;
  touched_refs BIGINT := 0;
  worker_refs BIGINT := 0;
BEGIN
  IF current_setting('ashare_v3.allow_n3_20260615_metric_coverage_repair_rollback', true) <> 'true' THEN
    RAISE EXCEPTION
      'N3 20260615 metric coverage repair rollback hard-fail: set ashare_v3.allow_n3_20260615_metric_coverage_repair_rollback=true after final gate approval';
  END IF;

  IF to_regclass('public.common_event_outbox') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.common_event_outbox AS t WHERE t.source_run_id = $1 OR t.payload_json::TEXT LIKE $2'
      INTO outbox_refs
      USING target_run_id, '%' || target_run_id || '%';
  END IF;

  IF to_regclass('public.common_event_inbox') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.common_event_inbox AS t WHERE t.source_run_id = $1 OR t.payload_json::TEXT LIKE $2 OR t.raw_json::TEXT LIKE $2'
      INTO inbox_refs
      USING target_run_id, '%' || target_run_id || '%';
  END IF;

  IF to_regclass('public.common_event_consumer_checkpoint') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.common_event_consumer_checkpoint AS t WHERE t.checkpoint_payload::TEXT LIKE $1 OR t.last_event_id LIKE $1'
      INTO checkpoint_refs
      USING '%' || target_run_id || '%';
  END IF;

  IF to_regclass('public.common_trigger_match') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.common_trigger_match AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO trigger_refs
      USING '%' || target_run_id || '%';
  END IF;

  IF to_regclass('public.common_trigger_state') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.common_trigger_state AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count
      USING '%' || target_run_id || '%';
    trigger_refs := trigger_refs + COALESCE(v_count, 0);
  END IF;

  IF to_regclass('public.common_action_event') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.common_action_event AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO action_refs
      USING '%' || target_run_id || '%';
  END IF;

  IF to_regclass('public.user_card_projection') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.user_card_projection AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.user_signal_projection') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.user_signal_projection AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.user_signal_card') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.user_signal_card AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.user_notification_queue') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.user_notification_queue AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.user_sim_order') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.user_sim_order AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.user_sim_trade') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.user_sim_trade AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.user_sim_position') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.user_sim_position AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.n6_virtual_account') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.n6_virtual_account AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.n6_virtual_order') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.n6_virtual_order AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.n6_virtual_trade') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.n6_virtual_trade AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.n6_virtual_position') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.n6_virtual_position AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.n6_virtual_position_event') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.n6_virtual_position_event AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;
  IF to_regclass('public.n6_virtual_pnl_snapshot') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.n6_virtual_pnl_snapshot AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;

  IF to_regclass('public.common_market_data_run') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.common_market_data_run WHERE run_id = $1 AND downstream_layers_touched = true'
      INTO touched_refs
      USING target_run_id;

    EXECUTE 'SELECT count(*) FROM public.common_market_data_run WHERE run_id = $1 AND worker_started = true'
      INTO worker_refs
      USING target_run_id;
  END IF;

  IF outbox_refs <> 0 OR inbox_refs <> 0 OR checkpoint_refs <> 0
     OR trigger_refs <> 0 OR action_refs <> 0 OR n6_refs <> 0
     OR touched_refs <> 0 OR worker_refs <> 0 THEN
    RAISE EXCEPTION
      'N3 20260615 metric coverage repair rollback blocked for %, outbox=%, inbox=%, checkpoint=%, trigger=%, action=%, n6_user_sim_virtual=%, downstream_touched=%, worker=%',
      target_run_id, outbox_refs, inbox_refs, checkpoint_refs, trigger_refs, action_refs, n6_refs, touched_refs, worker_refs;
  END IF;
END $$;

BEGIN;

DELETE FROM stock_action_confirmation_projection_metric
WHERE projection_run_id = 'action_confirmation_projection_metric_20260615_repaired_formal_price_amount_chain_coverage_repair_v1__n4_20260615_repaired_formal_price_amount_chain_replay_v1';

DELETE FROM index_action_confirmation_projection_metric
WHERE projection_run_id = 'action_confirmation_projection_metric_20260615_repaired_formal_price_amount_chain_coverage_repair_v1__n4_20260615_repaired_formal_price_amount_chain_replay_v1';

DELETE FROM board_action_confirmation_projection_metric
WHERE projection_run_id = 'action_confirmation_projection_metric_20260615_repaired_formal_price_amount_chain_coverage_repair_v1__n4_20260615_repaired_formal_price_amount_chain_replay_v1';

DELETE FROM common_market_data_quality_item
WHERE run_id = 'action_confirmation_projection_metric_20260615_repaired_formal_price_amount_chain_coverage_repair_v1__n4_20260615_repaired_formal_price_amount_chain_replay_v1'
  AND layer_scope = 'market_data_run'
  AND details ->> 'metric_scope' = 'action_confirmation_projection_metric';

DELETE FROM common_market_data_run
WHERE run_id = 'action_confirmation_projection_metric_20260615_repaired_formal_price_amount_chain_coverage_repair_v1__n4_20260615_repaired_formal_price_amount_chain_replay_v1'
  AND downstream_layers_touched = false
  AND worker_started = false;

COMMIT;
