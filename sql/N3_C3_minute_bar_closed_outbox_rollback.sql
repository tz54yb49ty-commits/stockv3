-- N3-C3 MinuteBarClosed outbox rollback.
-- Scope: minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
-- Safe only before downstream replay/consumption. Does not touch C2 summaries,
-- C2 delta minute rows, B1/B2/N4/N5 runtime, or user/action/trigger tables.

DO $$
DECLARE
  v_c3_run_id TEXT := 'minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
  v_delivered_count BIGINT;
  v_inbox_count BIGINT;
  v_checkpoint_count BIGINT;
BEGIN
  SELECT count(*) INTO v_delivered_count
  FROM common_event_outbox
  WHERE source_run_id = v_c3_run_id
    AND status IN ('delivering', 'delivered');

  IF v_delivered_count > 0 THEN
    RAISE EXCEPTION 'N3-C3 rollback blocked: delivered/delivering outbox rows exist for %', v_c3_run_id;
  END IF;

  SELECT count(*) INTO v_inbox_count
  FROM common_event_inbox
  WHERE source_run_id = v_c3_run_id;

  IF v_inbox_count > 0 THEN
    RAISE EXCEPTION 'N3-C3 rollback blocked: inbox rows exist for %', v_c3_run_id;
  END IF;

  SELECT count(*) INTO v_checkpoint_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || v_c3_run_id || '%';

  IF v_checkpoint_count > 0 THEN
    RAISE EXCEPTION 'N3-C3 rollback blocked: checkpoint references exist for %', v_c3_run_id;
  END IF;

  DELETE FROM common_event_outbox WHERE source_run_id = 'minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
  DELETE FROM common_market_data_quality_item WHERE run_id = 'minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
  DELETE FROM common_market_data_run WHERE run_id = 'minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
END $$;
