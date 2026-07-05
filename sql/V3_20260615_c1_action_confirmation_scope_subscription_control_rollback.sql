-- V3 20260615 C1 action-confirmation scoped subscription control rollback.
-- Scope: delete only subscription control rows for run_id=market_data_subscription_20260615_action_confirmation_c1_1005_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1.
-- This rollback must not delete minute facts, N4/N5/N6 facts, event infra, or existing subscription runs.

\set target_subscription_run_id 'market_data_subscription_20260615_action_confirmation_c1_1005_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1'
\set target_c1_run_id 'today_minute_bar_1m_20260615_until_1005_action_confirmation_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1'

DO $$
DECLARE
  sub_run TEXT := :'target_subscription_run_id';
  c1_run TEXT := :'target_c1_run_id';
  v_count BIGINT;
  allow_flag TEXT;
BEGIN
  allow_flag := current_setting('ashare_v3.allow_v3_20260615_c1_action_scope_subscription_rollback', true);
  IF allow_flag IS DISTINCT FROM 'true' THEN
    RAISE EXCEPTION 'Refusing rollback: set ashare_v3.allow_v3_20260615_c1_action_scope_subscription_rollback=true after final gate review';
  END IF;

  SELECT count(*) INTO v_count FROM common_market_data_run
  WHERE run_id = sub_run AND (downstream_layers_touched OR worker_started);
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: downstream/worker flags set for %', sub_run; END IF;

  SELECT count(*) INTO v_count FROM common_event_outbox
  WHERE source_run_id IN (sub_run, c1_run) OR payload_json::TEXT LIKE '%' || sub_run || '%' OR payload_json::TEXT LIKE '%' || c1_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: outbox refs exist for scoped subscription/C1 runs'; END IF;

  SELECT count(*) INTO v_count FROM common_event_inbox
  WHERE source_run_id IN (sub_run, c1_run) OR payload_json::TEXT LIKE '%' || sub_run || '%' OR payload_json::TEXT LIKE '%' || c1_run || '%' OR raw_json::TEXT LIKE '%' || sub_run || '%' OR raw_json::TEXT LIKE '%' || c1_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: inbox refs exist for scoped subscription/C1 runs'; END IF;

  SELECT count(*) INTO v_count FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || sub_run || '%' OR checkpoint_payload::TEXT LIKE '%' || c1_run || '%' OR last_event_id LIKE '%' || sub_run || '%' OR last_event_id LIKE '%' || c1_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: checkpoint refs exist for scoped subscription/C1 runs'; END IF;

  SELECT count(*) INTO v_count FROM stock_minute_bar_1m WHERE run_id = c1_run OR raw_json::TEXT LIKE '%' || sub_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: stock minute rows already materialized for scoped subscription/C1'; END IF;
  SELECT count(*) INTO v_count FROM index_minute_bar_1m WHERE run_id = c1_run OR raw_json::TEXT LIKE '%' || sub_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: index minute rows already materialized for scoped subscription/C1'; END IF;
  SELECT count(*) INTO v_count FROM board_minute_bar_1m WHERE run_id = c1_run OR raw_json::TEXT LIKE '%' || sub_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: board minute rows already materialized for scoped subscription/C1'; END IF;

  SELECT count(*) INTO v_count FROM stock_realtime_projection_metric WHERE projection_run_id = c1_run OR raw_json::TEXT LIKE '%' || sub_run || '%' OR raw_json::TEXT LIKE '%' || c1_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: stock B2 projection refs exist'; END IF;
  SELECT count(*) INTO v_count FROM index_realtime_projection_metric WHERE projection_run_id = c1_run OR raw_json::TEXT LIKE '%' || sub_run || '%' OR raw_json::TEXT LIKE '%' || c1_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: index B2 projection refs exist'; END IF;
  SELECT count(*) INTO v_count FROM board_realtime_projection_metric WHERE projection_run_id = c1_run OR raw_json::TEXT LIKE '%' || sub_run || '%' OR raw_json::TEXT LIKE '%' || c1_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: board B2 projection refs exist'; END IF;

  SELECT count(*) INTO v_count FROM common_trigger_state WHERE raw_json::TEXT LIKE '%' || sub_run || '%' OR raw_json::TEXT LIKE '%' || c1_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: N4 trigger state refs exist'; END IF;
  SELECT count(*) INTO v_count FROM common_trigger_match WHERE raw_json::TEXT LIKE '%' || sub_run || '%' OR raw_json::TEXT LIKE '%' || c1_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: N4 trigger match refs exist'; END IF;
  SELECT count(*) INTO v_count FROM common_action_event WHERE payload_json::TEXT LIKE '%' || sub_run || '%' OR payload_json::TEXT LIKE '%' || c1_run || '%' OR trace_json::TEXT LIKE '%' || sub_run || '%' OR trace_json::TEXT LIKE '%' || c1_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: N5 action refs exist'; END IF;

  IF to_regclass('user_signal_projection') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_signal_projection WHERE raw_json::TEXT LIKE $1 OR raw_json::TEXT LIKE $2' INTO v_count USING '%' || sub_run || '%', '%' || c1_run || '%';
    IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: user_signal_projection refs exist'; END IF;
  END IF;
  IF to_regclass('user_signal_card') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_signal_card WHERE raw_json::TEXT LIKE $1 OR raw_json::TEXT LIKE $2' INTO v_count USING '%' || sub_run || '%', '%' || c1_run || '%';
    IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: user_signal_card refs exist'; END IF;
  END IF;
  IF to_regclass('n6_virtual_order') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM n6_virtual_order WHERE raw_json::TEXT LIKE $1 OR raw_json::TEXT LIKE $2' INTO v_count USING '%' || sub_run || '%', '%' || c1_run || '%';
    IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: N6 virtual refs exist'; END IF;
  END IF;
END $$;

DELETE FROM common_market_data_pull_plan WHERE run_id = :'target_subscription_run_id';
DELETE FROM common_market_data_subscription WHERE run_id = :'target_subscription_run_id';
DELETE FROM common_market_data_subscription_candidate WHERE run_id = :'target_subscription_run_id';
DELETE FROM common_market_data_quality_item WHERE run_id = :'target_subscription_run_id';
DELETE FROM common_market_data_run WHERE run_id = :'target_subscription_run_id';
