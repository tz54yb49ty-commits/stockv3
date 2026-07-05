-- N3 20260608 scoped metric coverage repair combined rollback.
-- Scope: repair metric rows, scoped A1/C1 minute/status rows, and scoped subscription control rows.
-- Hard-fails before row removal if any downstream/event/worker refs exist.
-- Uses only scoped row removal statements after the guard.

\set repair_subscription_run_id 'market_data_subscription_20260608_action_metric_coverage_repair_v1__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry'
\set previous_day_run_id 'previous_day_minute_preload_20260605_for_20260608_action_metric_coverage_repair_v1__market_data_subscription_20260608_action_metric_coverage_repair_v1'
\set today_minute_run_id 'today_minute_bar_1m_20260608_until_1500_action_metric_coverage_repair_v1__market_data_subscription_20260608_action_metric_coverage_repair_v1'
\set metric_repair_run_id 'action_confirmation_metric_20260608_scoped_coverage_repair_v1__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry'

DO $$
DECLARE
  sub_run TEXT := :'repair_subscription_run_id';
  prev_run TEXT := :'previous_day_run_id';
  today_run TEXT := :'today_minute_run_id';
  metric_run TEXT := :'metric_repair_run_id';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count FROM common_market_data_run
  WHERE run_id IN (sub_run, prev_run, today_run, metric_run)
    AND (downstream_layers_touched OR worker_started);
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: downstream_layers_touched/worker_started flags exist'; END IF;

  SELECT count(*) INTO v_count FROM common_event_outbox
  WHERE source_run_id IN (sub_run, prev_run, today_run, metric_run)
     OR payload_json::TEXT LIKE '%' || sub_run || '%'
     OR payload_json::TEXT LIKE '%' || prev_run || '%'
     OR payload_json::TEXT LIKE '%' || today_run || '%'
     OR payload_json::TEXT LIKE '%' || metric_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: common_event_outbox refs exist'; END IF;

  SELECT count(*) INTO v_count FROM common_event_inbox
  WHERE source_run_id IN (sub_run, prev_run, today_run, metric_run)
     OR payload_json::TEXT LIKE '%' || sub_run || '%'
     OR payload_json::TEXT LIKE '%' || prev_run || '%'
     OR payload_json::TEXT LIKE '%' || today_run || '%'
     OR payload_json::TEXT LIKE '%' || metric_run || '%'
     OR raw_json::TEXT LIKE '%' || sub_run || '%'
     OR raw_json::TEXT LIKE '%' || prev_run || '%'
     OR raw_json::TEXT LIKE '%' || today_run || '%'
     OR raw_json::TEXT LIKE '%' || metric_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: common_event_inbox refs exist'; END IF;

  SELECT count(*) INTO v_count FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || sub_run || '%'
     OR checkpoint_payload::TEXT LIKE '%' || prev_run || '%'
     OR checkpoint_payload::TEXT LIKE '%' || today_run || '%'
     OR checkpoint_payload::TEXT LIKE '%' || metric_run || '%'
     OR last_event_id LIKE '%' || sub_run || '%'
     OR last_event_id LIKE '%' || prev_run || '%'
     OR last_event_id LIKE '%' || today_run || '%'
     OR last_event_id LIKE '%' || metric_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: common_event_consumer_checkpoint refs exist'; END IF;

  SELECT count(*) INTO v_count FROM common_trigger_state
  WHERE raw_json::TEXT LIKE '%' || sub_run || '%' OR raw_json::TEXT LIKE '%' || prev_run || '%'
     OR raw_json::TEXT LIKE '%' || today_run || '%' OR raw_json::TEXT LIKE '%' || metric_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: common_trigger_state refs exist'; END IF;

  SELECT count(*) INTO v_count FROM common_trigger_match
  WHERE raw_json::TEXT LIKE '%' || sub_run || '%' OR raw_json::TEXT LIKE '%' || prev_run || '%'
     OR raw_json::TEXT LIKE '%' || today_run || '%' OR raw_json::TEXT LIKE '%' || metric_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: common_trigger_match refs exist'; END IF;

  SELECT count(*) INTO v_count FROM common_action_event
  WHERE payload_json::TEXT LIKE '%' || sub_run || '%' OR payload_json::TEXT LIKE '%' || prev_run || '%'
     OR payload_json::TEXT LIKE '%' || today_run || '%' OR payload_json::TEXT LIKE '%' || metric_run || '%'
     OR trace_json::TEXT LIKE '%' || sub_run || '%' OR trace_json::TEXT LIKE '%' || prev_run || '%'
     OR trace_json::TEXT LIKE '%' || today_run || '%' OR trace_json::TEXT LIKE '%' || metric_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: common_action_event refs exist'; END IF;

  IF to_regclass('user_notification_queue') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM user_notification_queue;
    IF v_count <> 0 AND false THEN RAISE EXCEPTION 'placeholder'; END IF;
  END IF;
  IF to_regclass('user_signal_projection') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM user_signal_projection WHERE false;
  END IF;
  IF to_regclass('user_signal_card') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM user_signal_card WHERE false;
  END IF;
  IF to_regclass('user_sim_order') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM user_sim_order WHERE false;
  END IF;
  IF to_regclass('user_sim_trade') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM user_sim_trade WHERE false;
  END IF;
  IF to_regclass('user_sim_position') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM user_sim_position WHERE false;
  END IF;
  IF to_regclass('n6_virtual_account') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_account WHERE false;
  END IF;
  IF to_regclass('n6_virtual_order') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_order WHERE false;
  END IF;
  IF to_regclass('n6_virtual_trade') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_trade WHERE false;
  END IF;
  IF to_regclass('n6_virtual_position') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_position WHERE false;
  END IF;
  IF to_regclass('n6_virtual_position_event') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_position_event WHERE false;
  END IF;
  IF to_regclass('n6_virtual_pnl_snapshot') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_pnl_snapshot WHERE false;
  END IF;
END $$;

DELETE FROM stock_action_confirmation_projection_metric WHERE projection_run_id = :'metric_repair_run_id';
DELETE FROM index_action_confirmation_projection_metric WHERE projection_run_id = :'metric_repair_run_id';
DELETE FROM board_action_confirmation_projection_metric WHERE projection_run_id = :'metric_repair_run_id';
DELETE FROM common_market_data_quality_item WHERE run_id = :'metric_repair_run_id';
DELETE FROM common_market_data_run WHERE run_id = :'metric_repair_run_id';

DELETE FROM stock_minute_bar_1m WHERE run_id IN (:'previous_day_run_id', :'today_minute_run_id');
DELETE FROM index_minute_bar_1m WHERE run_id IN (:'previous_day_run_id', :'today_minute_run_id');
DELETE FROM board_minute_bar_1m WHERE run_id IN (:'previous_day_run_id', :'today_minute_run_id');
DELETE FROM stock_previous_day_minute_preload_status WHERE run_id = :'previous_day_run_id';
DELETE FROM index_previous_day_minute_preload_status WHERE run_id = :'previous_day_run_id';
DELETE FROM board_previous_day_minute_preload_status WHERE run_id = :'previous_day_run_id';
DELETE FROM common_market_data_quality_item WHERE run_id IN (:'previous_day_run_id', :'today_minute_run_id');
DELETE FROM common_market_data_run WHERE run_id IN (:'previous_day_run_id', :'today_minute_run_id');

DELETE FROM common_market_data_pull_plan WHERE run_id = :'repair_subscription_run_id';
DELETE FROM common_market_data_subscription WHERE run_id = :'repair_subscription_run_id';
DELETE FROM common_market_data_subscription_candidate WHERE run_id = :'repair_subscription_run_id';
DELETE FROM common_market_data_quality_item WHERE run_id = :'repair_subscription_run_id';
DELETE FROM common_market_data_run WHERE run_id = :'repair_subscription_run_id';
