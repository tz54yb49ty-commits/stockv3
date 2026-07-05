-- N3 market data subscription rebuild 20260608 v13 index-all rollback.
-- Scope: market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute
\set ON_ERROR_STOP on
\set rollback_run_id 'market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute'

DO $$
DECLARE
  v_run_id text := 'market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute';
  v_count bigint;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_market_data_run
  WHERE run_id = v_run_id
    AND (coalesce(downstream_layers_touched, false) OR coalesce(worker_started, false));
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: N3 subscription run has downstream or worker flags set for %', v_run_id;
  END IF;

  SELECT count(*) INTO v_count FROM stock_realtime_daily_snapshot WHERE run_id = v_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: stock realtime snapshot rows exist for %', v_run_id; END IF;
  SELECT count(*) INTO v_count FROM index_realtime_daily_snapshot WHERE run_id = v_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: index realtime snapshot rows exist for %', v_run_id; END IF;
  SELECT count(*) INTO v_count FROM board_realtime_daily_snapshot WHERE run_id = v_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: board realtime snapshot rows exist for %', v_run_id; END IF;

  SELECT count(*) INTO v_count FROM stock_minute_bar_1m WHERE run_id = v_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: stock minute rows exist for %', v_run_id; END IF;
  SELECT count(*) INTO v_count FROM index_minute_bar_1m WHERE run_id = v_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: index minute rows exist for %', v_run_id; END IF;
  SELECT count(*) INTO v_count FROM board_minute_bar_1m WHERE run_id = v_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: board minute rows exist for %', v_run_id; END IF;

  SELECT count(*) INTO v_count FROM stock_previous_day_minute_preload_status WHERE run_id = v_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: stock preload status rows exist for %', v_run_id; END IF;
  SELECT count(*) INTO v_count FROM index_previous_day_minute_preload_status WHERE run_id = v_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: index preload status rows exist for %', v_run_id; END IF;
  SELECT count(*) INTO v_count FROM board_previous_day_minute_preload_status WHERE run_id = v_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: board preload status rows exist for %', v_run_id; END IF;

  SELECT count(*) INTO v_count FROM stock_realtime_projection_metric WHERE projection_run_id = v_run_id OR source_snapshot_run_id = v_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: stock projection rows reference %', v_run_id; END IF;
  SELECT count(*) INTO v_count FROM index_realtime_projection_metric WHERE projection_run_id = v_run_id OR source_snapshot_run_id = v_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: index projection rows reference %', v_run_id; END IF;
  SELECT count(*) INTO v_count FROM board_realtime_projection_metric WHERE projection_run_id = v_run_id OR source_snapshot_run_id = v_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: board projection rows reference %', v_run_id; END IF;

  SELECT count(*) INTO v_count FROM common_event_outbox WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: outbox refs exist for %', v_run_id; END IF;
  SELECT count(*) INTO v_count FROM common_event_inbox WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: inbox refs exist for %', v_run_id; END IF;
  SELECT count(*) INTO v_count FROM common_event_consumer_checkpoint WHERE row_to_json(common_event_consumer_checkpoint)::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: checkpoint refs exist for %', v_run_id; END IF;

  SELECT count(*) INTO v_count FROM common_trigger_match WHERE row_to_json(common_trigger_match)::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: trigger match refs exist for %', v_run_id; END IF;
  SELECT count(*) INTO v_count FROM common_trigger_state WHERE row_to_json(common_trigger_state)::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: trigger state refs exist for %', v_run_id; END IF;
  SELECT count(*) INTO v_count FROM common_action_event WHERE row_to_json(common_action_event)::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: action refs exist for %', v_run_id; END IF;

  IF to_regclass('public.user_card_projection') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_card_projection WHERE row_to_json(user_card_projection)::text LIKE $1' INTO v_count USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: user card refs exist for %', v_run_id; END IF;
  END IF;
  IF to_regclass('public.user_signal_projection') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_signal_projection WHERE row_to_json(user_signal_projection)::text LIKE $1' INTO v_count USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: user signal projection refs exist for %', v_run_id; END IF;
  END IF;
  IF to_regclass('public.user_signal_card') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_signal_card WHERE row_to_json(user_signal_card)::text LIKE $1' INTO v_count USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: user signal card refs exist for %', v_run_id; END IF;
  END IF;
  IF to_regclass('public.user_notification_queue') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_notification_queue WHERE row_to_json(user_notification_queue)::text LIKE $1' INTO v_count USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: user notification refs exist for %', v_run_id; END IF;
  END IF;
  IF to_regclass('public.user_sim_order') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_sim_order WHERE row_to_json(user_sim_order)::text LIKE $1' INTO v_count USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: user sim order refs exist for %', v_run_id; END IF;
  END IF;
  IF to_regclass('public.user_sim_trade') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_sim_trade WHERE row_to_json(user_sim_trade)::text LIKE $1' INTO v_count USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: user sim trade refs exist for %', v_run_id; END IF;
  END IF;
  IF to_regclass('public.user_sim_position') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_sim_position WHERE row_to_json(user_sim_position)::text LIKE $1' INTO v_count USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: user sim position refs exist for %', v_run_id; END IF;
  END IF;
  IF to_regclass('public.n6_virtual_account') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM n6_virtual_account WHERE row_to_json(n6_virtual_account)::text LIKE $1' INTO v_count USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: virtual account refs exist for %', v_run_id; END IF;
  END IF;
  IF to_regclass('public.n6_virtual_order') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM n6_virtual_order WHERE row_to_json(n6_virtual_order)::text LIKE $1' INTO v_count USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: virtual order refs exist for %', v_run_id; END IF;
  END IF;
  IF to_regclass('public.n6_virtual_trade') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM n6_virtual_trade WHERE row_to_json(n6_virtual_trade)::text LIKE $1' INTO v_count USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: virtual trade refs exist for %', v_run_id; END IF;
  END IF;
  IF to_regclass('public.n6_virtual_position') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM n6_virtual_position WHERE row_to_json(n6_virtual_position)::text LIKE $1' INTO v_count USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: virtual position refs exist for %', v_run_id; END IF;
  END IF;
  IF to_regclass('public.n6_virtual_position_event') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM n6_virtual_position_event WHERE row_to_json(n6_virtual_position_event)::text LIKE $1' INTO v_count USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: virtual position event refs exist for %', v_run_id; END IF;
  END IF;
  IF to_regclass('public.n6_virtual_pnl_snapshot') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM n6_virtual_pnl_snapshot WHERE row_to_json(n6_virtual_pnl_snapshot)::text LIKE $1' INTO v_count USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: virtual pnl refs exist for %', v_run_id; END IF;
  END IF;
END $$;

DELETE FROM common_market_data_pull_plan
WHERE run_id = :'rollback_run_id';

DELETE FROM common_market_data_subscription
WHERE run_id = :'rollback_run_id';

DELETE FROM common_market_data_subscription_candidate
WHERE run_id = :'rollback_run_id';

DELETE FROM common_market_data_quality_item
WHERE run_id = :'rollback_run_id';

DELETE FROM common_market_data_run
WHERE run_id = :'rollback_run_id';
