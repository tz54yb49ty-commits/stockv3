-- N3-C2 closed minute / closed 30m business rollback.
-- Scope: closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
DO $$
DECLARE
  v_c2_run_id TEXT := 'closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count FROM common_event_outbox WHERE source_run_id = v_c2_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing C2 rollback: common_event_outbox has % rows for %', v_count, v_c2_run_id;
  END IF;
  SELECT count(*) INTO v_count FROM common_event_inbox WHERE source_run_id = v_c2_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing C2 rollback: common_event_inbox has % rows for %', v_count, v_c2_run_id;
  END IF;
  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || v_c2_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing C2 rollback: common_event_consumer_checkpoint references % in % rows', v_c2_run_id, v_count;
  END IF;
END $$;

DELETE FROM stock_closed_30m_summary WHERE run_id = 'closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM index_closed_30m_summary WHERE run_id = 'closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM board_closed_30m_summary WHERE run_id = 'closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';

DELETE FROM stock_minute_bar_1m WHERE run_id = 'closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute' AND is_previous_day_preload = false;
DELETE FROM index_minute_bar_1m WHERE run_id = 'closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute' AND is_previous_day_preload = false;
DELETE FROM board_minute_bar_1m WHERE run_id = 'closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute' AND is_previous_day_preload = false;

DELETE FROM common_market_data_quality_item WHERE run_id = 'closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM common_market_data_run WHERE run_id = 'closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
