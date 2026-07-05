-- N3 20260608 scoped metric coverage repair subscription rollback.
-- Scope: subscription control rows only for market_data_subscription_20260608_action_metric_coverage_repair_v1__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry.
-- Review before execution.

\set repair_subscription_run_id 'market_data_subscription_20260608_action_metric_coverage_repair_v1__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry'

DO $$
DECLARE
  target_run_id TEXT := :'repair_subscription_run_id';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count FROM common_market_data_run
  WHERE run_id = target_run_id AND (downstream_layers_touched OR worker_started);
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing rollback: downstream/worker flags set for %', target_run_id;
  END IF;

  SELECT count(*) INTO v_count FROM common_event_outbox
  WHERE source_run_id = target_run_id OR payload_json::TEXT LIKE '%' || target_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: outbox refs exist for %', target_run_id; END IF;

  SELECT count(*) INTO v_count FROM common_event_inbox
  WHERE source_run_id = target_run_id OR payload_json::TEXT LIKE '%' || target_run_id || '%' OR raw_json::TEXT LIKE '%' || target_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: inbox refs exist for %', target_run_id; END IF;

  SELECT count(*) INTO v_count FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || target_run_id || '%' OR last_event_id LIKE '%' || target_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: checkpoint refs exist for %', target_run_id; END IF;

  SELECT count(*) INTO v_count FROM stock_minute_bar_1m WHERE run_id IN ('previous_day_minute_preload_20260605_for_20260608_action_metric_coverage_repair_v1__market_data_subscription_20260608_action_metric_coverage_repair_v1', 'today_minute_bar_1m_20260608_until_1500_action_metric_coverage_repair_v1__market_data_subscription_20260608_action_metric_coverage_repair_v1');
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: stock minute rows already materialized'; END IF;
  SELECT count(*) INTO v_count FROM index_minute_bar_1m WHERE run_id IN ('previous_day_minute_preload_20260605_for_20260608_action_metric_coverage_repair_v1__market_data_subscription_20260608_action_metric_coverage_repair_v1', 'today_minute_bar_1m_20260608_until_1500_action_metric_coverage_repair_v1__market_data_subscription_20260608_action_metric_coverage_repair_v1');
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: index minute rows already materialized'; END IF;
  SELECT count(*) INTO v_count FROM board_minute_bar_1m WHERE run_id IN ('previous_day_minute_preload_20260605_for_20260608_action_metric_coverage_repair_v1__market_data_subscription_20260608_action_metric_coverage_repair_v1', 'today_minute_bar_1m_20260608_until_1500_action_metric_coverage_repair_v1__market_data_subscription_20260608_action_metric_coverage_repair_v1');
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: board minute rows already materialized'; END IF;

  SELECT count(*) INTO v_count FROM stock_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_metric_20260608_scoped_coverage_repair_v1__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: stock metric repair rows exist'; END IF;
  SELECT count(*) INTO v_count FROM index_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_metric_20260608_scoped_coverage_repair_v1__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: index metric repair rows exist'; END IF;
  SELECT count(*) INTO v_count FROM board_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_metric_20260608_scoped_coverage_repair_v1__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: board metric repair rows exist'; END IF;

  SELECT count(*) INTO v_count FROM common_trigger_state WHERE raw_json::TEXT LIKE '%' || target_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: common_trigger_state refs exist'; END IF;
  SELECT count(*) INTO v_count FROM common_trigger_match WHERE raw_json::TEXT LIKE '%' || target_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: common_trigger_match refs exist'; END IF;
  SELECT count(*) INTO v_count FROM common_action_event WHERE payload_json::TEXT LIKE '%' || target_run_id || '%' OR trace_json::TEXT LIKE '%' || target_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: common_action_event refs exist'; END IF;
END $$;

DELETE FROM common_market_data_pull_plan WHERE run_id = :'repair_subscription_run_id';
DELETE FROM common_market_data_subscription WHERE run_id = :'repair_subscription_run_id';
DELETE FROM common_market_data_subscription_candidate WHERE run_id = :'repair_subscription_run_id';
DELETE FROM common_market_data_quality_item WHERE run_id = :'repair_subscription_run_id';
DELETE FROM common_market_data_run WHERE run_id = :'repair_subscription_run_id';
