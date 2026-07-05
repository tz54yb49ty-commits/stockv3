-- V3 20260616 intraday N3 source+metric staged rollback.
-- Scope: B1 snapshot run, C1 today-minute run, metric run only. Does not delete subscription or previous-day preload.
\set ON_ERROR_STOP on

DO $$
BEGIN
  IF current_setting('ashare_v3.allow_v3_20260616_intraday_n3_bundle_rollback', true) <> 'true' THEN
    RAISE EXCEPTION 'V3 20260616 N3 bundle rollback hard-fail: set ashare_v3.allow_v3_20260616_intraday_n3_bundle_rollback=true after final gate review';
  END IF;
END $$;

DO $$
DECLARE
  target_run_ids TEXT[] := ARRAY['realtime_daily_snapshot_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1','today_minute_bar_1m_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1','action_confirmation_projection_metric_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1'];
  outbox_refs BIGINT := 0;
  inbox_refs BIGINT := 0;
  checkpoint_refs BIGINT := 0;
  n4_refs BIGINT := 0;
  n5_refs BIGINT := 0;
  n6_refs BIGINT := 0;
  downstream_refs BIGINT := 0;
  worker_refs BIGINT := 0;
BEGIN
  SELECT count(*) INTO outbox_refs FROM common_event_outbox WHERE EXISTS (SELECT 1 FROM unnest(target_run_ids) r WHERE source_run_id = r OR payload_json::TEXT LIKE '%' || r || '%');
  SELECT count(*) INTO inbox_refs FROM common_event_inbox WHERE EXISTS (SELECT 1 FROM unnest(target_run_ids) r WHERE source_run_id = r OR payload_json::TEXT LIKE '%' || r || '%' OR raw_json::TEXT LIKE '%' || r || '%');
  SELECT count(*) INTO checkpoint_refs FROM common_event_consumer_checkpoint WHERE EXISTS (SELECT 1 FROM unnest(target_run_ids) r WHERE checkpoint_payload::TEXT LIKE '%' || r || '%' OR last_event_id LIKE '%' || r || '%');
  IF to_regclass('common_trigger_match') IS NOT NULL THEN EXECUTE 'SELECT count(*) FROM common_trigger_match WHERE EXISTS (SELECT 1 FROM unnest($1::text[]) r WHERE to_jsonb(common_trigger_match)::TEXT LIKE ''%'' || r || ''%'')' INTO n4_refs USING target_run_ids; END IF;
  IF to_regclass('common_trigger_state') IS NOT NULL THEN EXECUTE 'SELECT $1 + count(*) FROM common_trigger_state WHERE EXISTS (SELECT 1 FROM unnest($2::text[]) r WHERE to_jsonb(common_trigger_state)::TEXT LIKE ''%'' || r || ''%'')' INTO n4_refs USING n4_refs, target_run_ids; END IF;
  IF to_regclass('common_action_event') IS NOT NULL THEN EXECUTE 'SELECT count(*) FROM common_action_event WHERE EXISTS (SELECT 1 FROM unnest($1::text[]) r WHERE to_jsonb(common_action_event)::TEXT LIKE ''%'' || r || ''%'')' INTO n5_refs USING target_run_ids; END IF;
  IF to_regclass('user_signal_projection') IS NOT NULL THEN EXECUTE 'SELECT count(*) FROM user_signal_projection WHERE EXISTS (SELECT 1 FROM unnest($1::text[]) r WHERE to_jsonb(user_signal_projection)::TEXT LIKE ''%'' || r || ''%'')' INTO n6_refs USING target_run_ids; END IF;
  IF to_regclass('user_signal_card') IS NOT NULL THEN EXECUTE 'SELECT $1 + count(*) FROM user_signal_card WHERE EXISTS (SELECT 1 FROM unnest($2::text[]) r WHERE to_jsonb(user_signal_card)::TEXT LIKE ''%'' || r || ''%'')' INTO n6_refs USING n6_refs, target_run_ids; END IF;
  SELECT count(*) INTO downstream_refs FROM common_market_data_run WHERE run_id = ANY(target_run_ids) AND downstream_layers_touched = true;
  SELECT count(*) INTO worker_refs FROM common_market_data_run WHERE run_id = ANY(target_run_ids) AND worker_started = true;
  IF outbox_refs <> 0 OR inbox_refs <> 0 OR checkpoint_refs <> 0 OR n4_refs <> 0 OR n5_refs <> 0 OR n6_refs <> 0 OR downstream_refs <> 0 OR worker_refs <> 0 THEN
    RAISE EXCEPTION 'V3 N3 bundle rollback blocked, outbox=%, inbox=%, checkpoint=%, n4=%, n5=%, n6=%, downstream=%, worker=%', outbox_refs, inbox_refs, checkpoint_refs, n4_refs, n5_refs, n6_refs, downstream_refs, worker_refs;
  END IF;
END $$;

BEGIN;
DELETE FROM stock_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1';
DELETE FROM index_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1';
DELETE FROM board_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1';
DELETE FROM stock_minute_bar_1m WHERE run_id = 'today_minute_bar_1m_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1' AND is_previous_day_preload = false;
DELETE FROM index_minute_bar_1m WHERE run_id = 'today_minute_bar_1m_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1' AND is_previous_day_preload = false;
DELETE FROM board_minute_bar_1m WHERE run_id = 'today_minute_bar_1m_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1' AND is_previous_day_preload = false;
DELETE FROM stock_realtime_daily_snapshot WHERE run_id = 'realtime_daily_snapshot_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1';
DELETE FROM index_realtime_daily_snapshot WHERE run_id = 'realtime_daily_snapshot_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1';
DELETE FROM board_realtime_daily_snapshot WHERE run_id = 'realtime_daily_snapshot_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1';
DELETE FROM common_market_data_quality_item WHERE run_id IN ('realtime_daily_snapshot_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1','today_minute_bar_1m_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1','action_confirmation_projection_metric_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1');
DELETE FROM common_market_data_run WHERE run_id IN ('realtime_daily_snapshot_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1','today_minute_bar_1m_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1','action_confirmation_projection_metric_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1') AND downstream_layers_touched = false AND worker_started = false;
COMMIT;
