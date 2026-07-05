-- N3 board-lineage scoped subscription control rollback.
-- Scope: delete only subscription control rows for run_id=market_data_subscription_20260605_action_metric_board_lineage_repair_condition_layer_20260604_source_20260604_v1.
-- Hard-fail before DELETE when pull plans were executed, minute facts or metric-v2 rows exist,
-- event infra/downstream refs exist, or worker/downstream flags indicate consumption.

\set ON_ERROR_STOP on
\set subscription_run_id 'market_data_subscription_20260605_action_metric_board_lineage_repair_condition_layer_20260604_source_20260604_v1'
\set previous_day_run_id 'previous_day_minute_preload_20260604_for_20260605_action_metric_board_lineage_repair__market_data_subscription_20260605_action_metric_board_lineage_repair_condition_layer_20260604_source_20260604_v1'
\set today_minute_run_id 'today_minute_bar_1m_20260605_until_1127_action_metric_board_lineage_repair__market_data_subscription_20260605_action_metric_board_lineage_repair_condition_layer_20260604_source_20260604_v1'
\set metric_run_id 'action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1'

SELECT set_config('app.subscription_run_id', :'subscription_run_id', false);
SELECT set_config('app.previous_day_run_id', :'previous_day_run_id', false);
SELECT set_config('app.today_minute_run_id', :'today_minute_run_id', false);
SELECT set_config('app.metric_run_id', :'metric_run_id', false);

DO $$
DECLARE
  target_run_id TEXT := current_setting('app.subscription_run_id');
  prev_run_id TEXT := current_setting('app.previous_day_run_id');
  today_run_id TEXT := current_setting('app.today_minute_run_id');
  metric_target_run_id TEXT := current_setting('app.metric_run_id');
  outbox_refs BIGINT;
  inbox_refs BIGINT;
  checkpoint_refs BIGINT;
  trigger_refs BIGINT;
  action_refs BIGINT;
  n6_refs BIGINT := 0;
  v_count BIGINT;
  pull_plan_executed_refs BIGINT;
  minute_fact_refs BIGINT;
  preload_status_refs BIGINT;
  metric_v2_refs BIGINT;
  touched_refs BIGINT;
  worker_refs BIGINT;
BEGIN
  SELECT count(*) INTO outbox_refs
  FROM common_event_outbox
  WHERE source_run_id IN (target_run_id, prev_run_id, today_run_id, metric_target_run_id)
     OR payload_json::TEXT LIKE '%' || target_run_id || '%'
     OR payload_json::TEXT LIKE '%' || prev_run_id || '%'
     OR payload_json::TEXT LIKE '%' || today_run_id || '%'
     OR payload_json::TEXT LIKE '%' || metric_target_run_id || '%';

  SELECT count(*) INTO inbox_refs
  FROM common_event_inbox
  WHERE source_run_id IN (target_run_id, prev_run_id, today_run_id, metric_target_run_id)
     OR payload_json::TEXT LIKE '%' || target_run_id || '%'
     OR payload_json::TEXT LIKE '%' || prev_run_id || '%'
     OR payload_json::TEXT LIKE '%' || today_run_id || '%'
     OR payload_json::TEXT LIKE '%' || metric_target_run_id || '%'
     OR raw_json::TEXT LIKE '%' || target_run_id || '%'
     OR raw_json::TEXT LIKE '%' || prev_run_id || '%'
     OR raw_json::TEXT LIKE '%' || today_run_id || '%'
     OR raw_json::TEXT LIKE '%' || metric_target_run_id || '%';

  SELECT count(*) INTO checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || target_run_id || '%'
     OR checkpoint_payload::TEXT LIKE '%' || prev_run_id || '%'
     OR checkpoint_payload::TEXT LIKE '%' || today_run_id || '%'
     OR checkpoint_payload::TEXT LIKE '%' || metric_target_run_id || '%'
     OR last_event_id LIKE '%' || target_run_id || '%'
     OR last_event_id LIKE '%' || prev_run_id || '%'
     OR last_event_id LIKE '%' || today_run_id || '%'
     OR last_event_id LIKE '%' || metric_target_run_id || '%';

  SELECT count(*) INTO trigger_refs
  FROM common_trigger_match
  WHERE raw_json::TEXT LIKE '%' || target_run_id || '%'
     OR raw_json::TEXT LIKE '%' || prev_run_id || '%'
     OR raw_json::TEXT LIKE '%' || today_run_id || '%'
     OR raw_json::TEXT LIKE '%' || metric_target_run_id || '%';

  SELECT count(*) INTO action_refs
  FROM common_action_event
  WHERE trace_json::TEXT LIKE '%' || target_run_id || '%'
     OR trace_json::TEXT LIKE '%' || prev_run_id || '%'
     OR trace_json::TEXT LIKE '%' || today_run_id || '%'
     OR trace_json::TEXT LIKE '%' || metric_target_run_id || '%';

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

  SELECT count(*) INTO pull_plan_executed_refs
  FROM common_market_data_pull_plan
  WHERE run_id = target_run_id
    AND (execute_allowed = true OR plan_status IN ('executed', 'running', 'pulled', 'completed'));

  SELECT count(*) INTO minute_fact_refs
  FROM board_minute_bar_1m
  WHERE run_id IN (prev_run_id, today_run_id)
     OR raw_json::TEXT LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO preload_status_refs
  FROM board_previous_day_minute_preload_status
  WHERE run_id = prev_run_id OR raw_json::TEXT LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO metric_v2_refs
  FROM board_action_confirmation_projection_metric
  WHERE projection_run_id = metric_target_run_id
     OR source_minute_refs::TEXT LIKE '%' || target_run_id || '%'
     OR previous_day_minute_refs::TEXT LIKE '%' || target_run_id || '%'
     OR source_fact_ids::TEXT LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO touched_refs
  FROM common_market_data_run
  WHERE run_id = target_run_id AND downstream_layers_touched = true;

  SELECT count(*) INTO worker_refs
  FROM common_market_data_run
  WHERE run_id = target_run_id AND worker_started = true;

  IF outbox_refs <> 0 OR inbox_refs <> 0 OR checkpoint_refs <> 0
     OR trigger_refs <> 0 OR action_refs <> 0 OR n6_refs <> 0
     OR pull_plan_executed_refs <> 0 OR minute_fact_refs <> 0
     OR preload_status_refs <> 0 OR metric_v2_refs <> 0
     OR touched_refs <> 0 OR worker_refs <> 0 THEN
    RAISE EXCEPTION
      'N3 board-lineage subscription rollback blocked for %, outbox=%, inbox=%, checkpoint=%, trigger=%, action=%, n6=%, pull_plan_executed=%, minute=%, preload_status=%, metric_v2=%, downstream_touched=%, worker=%',
      target_run_id, outbox_refs, inbox_refs, checkpoint_refs, trigger_refs, action_refs, n6_refs,
      pull_plan_executed_refs, minute_fact_refs, preload_status_refs, metric_v2_refs, touched_refs, worker_refs;
  END IF;
END $$;

BEGIN;

DELETE FROM common_market_data_pull_plan
WHERE run_id = :'subscription_run_id';

DELETE FROM common_market_data_subscription
WHERE run_id = :'subscription_run_id';

DELETE FROM common_market_data_subscription_candidate
WHERE run_id = :'subscription_run_id';

DELETE FROM common_market_data_quality_item
WHERE run_id = :'subscription_run_id';

DELETE FROM common_market_data_run
WHERE run_id = :'subscription_run_id'
  AND downstream_layers_touched = false
  AND worker_started = false;

COMMIT;
