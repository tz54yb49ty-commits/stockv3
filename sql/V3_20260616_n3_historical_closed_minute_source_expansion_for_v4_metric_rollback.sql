-- Scoped rollback draft for historical_closed_minute_source_expansion_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4
-- Scope is limited to target N3 historical closed-minute source expansion rows/run/quality.

DO $$
DECLARE
  target_run_id text := 'historical_closed_minute_source_expansion_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';
BEGIN
  IF current_setting('ashare_v3.allow_v3_20260616_n3_historical_closed_minute_source_expansion_rollback', true) <> 'true' THEN
    RAISE EXCEPTION 'hard-fail: set ashare_v3.allow_v3_20260616_n3_historical_closed_minute_source_expansion_rollback=true before this rollback';
  END IF;

  IF EXISTS (SELECT 1 FROM common_event_outbox WHERE source_run_id = target_run_id OR payload_json::text LIKE '%' || target_run_id || '%') THEN
    RAISE EXCEPTION 'hard-fail: event outbox refs exist for %', target_run_id;
  END IF;

  IF EXISTS (SELECT 1 FROM common_event_inbox WHERE source_run_id = target_run_id OR payload_json::text LIKE '%' || target_run_id || '%' OR raw_json::text LIKE '%' || target_run_id || '%') THEN
    RAISE EXCEPTION 'hard-fail: event inbox refs exist for %', target_run_id;
  END IF;

  IF EXISTS (SELECT 1 FROM common_event_consumer_checkpoint WHERE checkpoint_payload::text LIKE '%' || target_run_id || '%') THEN
    RAISE EXCEPTION 'hard-fail: event checkpoint refs exist for %', target_run_id;
  END IF;

  IF EXISTS (SELECT 1 FROM common_trigger_run WHERE source_market_data_run_id = target_run_id OR raw_json::text LIKE '%' || target_run_id || '%') THEN
    RAISE EXCEPTION 'hard-fail: N4 refs exist for %', target_run_id;
  END IF;

  IF EXISTS (SELECT 1 FROM common_action_run WHERE raw_json::text LIKE '%' || target_run_id || '%') THEN
    RAISE EXCEPTION 'hard-fail: N5 refs exist for %', target_run_id;
  END IF;

  IF to_regclass('public.user_signal_projection') IS NOT NULL AND EXISTS (SELECT 1 FROM user_signal_projection WHERE source_payload_json::text LIKE '%' || target_run_id || '%' OR trace_json::text LIKE '%' || target_run_id || '%') THEN
    RAISE EXCEPTION 'hard-fail: user projection refs exist for %', target_run_id;
  END IF;

  IF to_regclass('public.user_signal_card') IS NOT NULL AND EXISTS (SELECT 1 FROM user_signal_card WHERE card_payload_json::text LIKE '%' || target_run_id || '%' OR trace_json::text LIKE '%' || target_run_id || '%') THEN
    RAISE EXCEPTION 'hard-fail: user card refs exist for %', target_run_id;
  END IF;

  IF to_regclass('public.user_notification_queue') IS NOT NULL AND EXISTS (SELECT 1 FROM user_notification_queue WHERE notification_payload_json::text LIKE '%' || target_run_id || '%' OR trace_json::text LIKE '%' || target_run_id || '%') THEN
    RAISE EXCEPTION 'hard-fail: user notification refs exist for %', target_run_id;
  END IF;
END $$;

DELETE FROM stock_minute_bar_1m WHERE run_id = 'historical_closed_minute_source_expansion_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';
DELETE FROM index_minute_bar_1m WHERE run_id = 'historical_closed_minute_source_expansion_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';
DELETE FROM board_minute_bar_1m WHERE run_id = 'historical_closed_minute_source_expansion_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';
DELETE FROM common_market_data_quality_item WHERE run_id = 'historical_closed_minute_source_expansion_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';
DELETE FROM common_market_data_run WHERE run_id = 'historical_closed_minute_source_expansion_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';
