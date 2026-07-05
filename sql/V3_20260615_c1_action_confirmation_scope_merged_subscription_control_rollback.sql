-- V3 20260615 C1 action-confirmation merged subscription control-row rollback.
-- Default hard-fail: runtime_control must explicitly set
--   SET LOCAL ashare_v3.allow_v3_20260615_c1_action_scope_merged_subscription_rollback = 'true';
-- before executing this file in a reviewed rollback gate.

BEGIN;

DO $$
DECLARE
  target_run_id text := 'market_data_subscription_20260615_action_confirmation_c1_1005_merged_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1';
  target_c1_run_id text := 'today_minute_bar_1m_20260615_until_1005_action_confirmation_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1';
  allow_rollback text := current_setting('ashare_v3.allow_v3_20260615_c1_action_scope_merged_subscription_rollback', true);
  minute_ref_count bigint := 0;
  outbox_ref_count bigint := 0;
  inbox_ref_count bigint := 0;
  checkpoint_ref_count bigint := 0;
  b2_ref_count bigint := 0;
  n4_ref_count bigint := 0;
  n5_ref_count bigint := 0;
  n6_user_sim_virtual_ref_count bigint := 0;
  run_flag_count bigint := 0;
BEGIN
  IF allow_rollback IS DISTINCT FROM 'true' THEN
    RAISE EXCEPTION 'HARD_FAIL: set ashare_v3.allow_v3_20260615_c1_action_scope_merged_subscription_rollback=true only inside approved rollback gate';
  END IF;

  SELECT count(*) INTO minute_ref_count
  FROM (
    SELECT m.bar_id FROM stock_minute_bar_1m m JOIN common_market_data_subscription s ON s.subscription_id = m.subscription_id WHERE s.run_id = target_run_id
    UNION ALL SELECT m.bar_id FROM index_minute_bar_1m m JOIN common_market_data_subscription s ON s.subscription_id = m.subscription_id WHERE s.run_id = target_run_id
    UNION ALL SELECT m.bar_id FROM board_minute_bar_1m m JOIN common_market_data_subscription s ON s.subscription_id = m.subscription_id WHERE s.run_id = target_run_id
    UNION ALL SELECT m.bar_id FROM stock_minute_bar_1m m WHERE m.run_id = target_c1_run_id
    UNION ALL SELECT m.bar_id FROM index_minute_bar_1m m WHERE m.run_id = target_c1_run_id
    UNION ALL SELECT m.bar_id FROM board_minute_bar_1m m WHERE m.run_id = target_c1_run_id
  ) refs;

  SELECT count(*) INTO outbox_ref_count FROM common_event_outbox WHERE source_run_id = target_run_id OR payload_json::text LIKE '%' || target_run_id || '%';
  SELECT count(*) INTO inbox_ref_count FROM common_event_inbox WHERE source_run_id = target_run_id OR payload_json::text LIKE '%' || target_run_id || '%' OR raw_json::text LIKE '%' || target_run_id || '%';
  SELECT count(*) INTO checkpoint_ref_count FROM common_event_consumer_checkpoint WHERE checkpoint_payload::text LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO b2_ref_count
  FROM (
    SELECT projection_id FROM stock_realtime_projection_metric WHERE raw_json::text LIKE '%' || target_run_id || '%'
    UNION ALL SELECT projection_id FROM index_realtime_projection_metric WHERE raw_json::text LIKE '%' || target_run_id || '%'
    UNION ALL SELECT projection_id FROM board_realtime_projection_metric WHERE raw_json::text LIKE '%' || target_run_id || '%'
  ) refs;

  SELECT count(*) INTO n4_ref_count
  FROM (
    SELECT trigger_match_id FROM common_trigger_match WHERE raw_json::text LIKE '%' || target_run_id || '%'
    UNION ALL SELECT trigger_state_id FROM common_trigger_state WHERE raw_json::text LIKE '%' || target_run_id || '%'
  ) refs;

  SELECT count(*) INTO n5_ref_count
  FROM (
    SELECT action_event_row_id FROM common_action_event cae WHERE to_jsonb(cae)::text LIKE '%' || target_run_id || '%'
    UNION ALL SELECT action_fact_id FROM stock_action_fact saf WHERE to_jsonb(saf)::text LIKE '%' || target_run_id || '%'
    UNION ALL SELECT action_fact_id FROM index_action_fact iaf WHERE to_jsonb(iaf)::text LIKE '%' || target_run_id || '%'
    UNION ALL SELECT action_fact_id FROM board_action_fact baf WHERE to_jsonb(baf)::text LIKE '%' || target_run_id || '%'
    UNION ALL SELECT action_confirmation_metric_id FROM stock_action_confirmation_projection_metric sacpm WHERE to_jsonb(sacpm)::text LIKE '%' || target_run_id || '%'
    UNION ALL SELECT action_confirmation_metric_id FROM index_action_confirmation_projection_metric iacpm WHERE to_jsonb(iacpm)::text LIKE '%' || target_run_id || '%'
    UNION ALL SELECT action_confirmation_metric_id FROM board_action_confirmation_projection_metric bacpm WHERE to_jsonb(bacpm)::text LIKE '%' || target_run_id || '%'
  ) refs;

  SELECT count(*) INTO n6_user_sim_virtual_ref_count
  FROM (
    SELECT 1 FROM user_signal_projection usp WHERE to_jsonb(usp)::text LIKE '%' || target_run_id || '%'
    UNION ALL SELECT 1 FROM user_signal_card usc WHERE to_jsonb(usc)::text LIKE '%' || target_run_id || '%'
    UNION ALL SELECT 1 FROM user_notification_queue unq WHERE to_jsonb(unq)::text LIKE '%' || target_run_id || '%'
    UNION ALL SELECT 1 FROM user_sim_order uso WHERE to_jsonb(uso)::text LIKE '%' || target_run_id || '%'
    UNION ALL SELECT 1 FROM user_sim_trade ust WHERE to_jsonb(ust)::text LIKE '%' || target_run_id || '%'
    UNION ALL SELECT 1 FROM user_sim_position usp2 WHERE to_jsonb(usp2)::text LIKE '%' || target_run_id || '%'
    UNION ALL SELECT 1 FROM n6_virtual_order nvo WHERE to_jsonb(nvo)::text LIKE '%' || target_run_id || '%'
    UNION ALL SELECT 1 FROM n6_virtual_trade nvt WHERE to_jsonb(nvt)::text LIKE '%' || target_run_id || '%'
    UNION ALL SELECT 1 FROM n6_virtual_position nvp WHERE to_jsonb(nvp)::text LIKE '%' || target_run_id || '%'
    UNION ALL SELECT 1 FROM n6_virtual_position_event nvpe WHERE to_jsonb(nvpe)::text LIKE '%' || target_run_id || '%'
    UNION ALL SELECT 1 FROM n6_virtual_pnl_snapshot nvps WHERE to_jsonb(nvps)::text LIKE '%' || target_run_id || '%'
  ) refs;

  SELECT count(*) INTO run_flag_count FROM common_market_data_run
  WHERE run_id = target_run_id
    AND (market_data_pulled IS TRUE OR market_data_fact_written IS TRUE OR downstream_layers_touched IS TRUE OR worker_started IS TRUE);

  IF minute_ref_count <> 0 OR outbox_ref_count <> 0 OR inbox_ref_count <> 0 OR checkpoint_ref_count <> 0
     OR b2_ref_count <> 0 OR n4_ref_count <> 0 OR n5_ref_count <> 0 OR n6_user_sim_virtual_ref_count <> 0 OR run_flag_count <> 0 THEN
    RAISE EXCEPTION 'Rollback blocked: refs minute=%, outbox=%, inbox=%, checkpoint=%, b2=%, n4=%, n5=%, n6_user_sim_virtual=%, run_flags=%',
      minute_ref_count, outbox_ref_count, inbox_ref_count, checkpoint_ref_count, b2_ref_count, n4_ref_count,
      n5_ref_count, n6_user_sim_virtual_ref_count, run_flag_count;
  END IF;
END $$;

DELETE FROM common_market_data_pull_plan WHERE run_id = 'market_data_subscription_20260615_action_confirmation_c1_1005_merged_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1';
DELETE FROM common_market_data_subscription WHERE run_id = 'market_data_subscription_20260615_action_confirmation_c1_1005_merged_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1';
DELETE FROM common_market_data_subscription_candidate WHERE run_id = 'market_data_subscription_20260615_action_confirmation_c1_1005_merged_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1';
DELETE FROM common_market_data_quality_item WHERE run_id = 'market_data_subscription_20260615_action_confirmation_c1_1005_merged_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1';
DELETE FROM common_market_data_run WHERE run_id = 'market_data_subscription_20260615_action_confirmation_c1_1005_merged_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1';

COMMIT;
