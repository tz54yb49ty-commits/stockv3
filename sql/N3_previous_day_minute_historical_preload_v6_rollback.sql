\set ON_ERROR_STOP on
\set preload_run_id 'previous_day_minute_preload_20260528__market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6'
\set source_subscription_run_id 'market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6'
\set source_condition_run_id 'condition_layer_20260528_source_20260528_v6'
\set data_trade_date '20260528'
\set for_trade_date '20260529'

BEGIN;

DO $$
BEGIN
  RAISE EXCEPTION 'Hard fail: review sql/N3_previous_day_minute_historical_preload_v6_rollback.sql guards and remove this exception only after explicit runtime_control approval.';
END $$;

DO $$
DECLARE
  v_preload_run_id text := :'preload_run_id';
  v_source_subscription_run_id text := :'source_subscription_run_id';
  v_ref_count bigint;
BEGIN
  SELECT count(*) INTO v_ref_count
  FROM common_market_data_run
  WHERE run_id = v_preload_run_id
    AND (downstream_layers_touched OR worker_started);
  IF v_ref_count <> 0 THEN
    RAISE EXCEPTION 'Blocked: preload run has downstream or worker flags';
  END IF;

  SELECT count(*) INTO v_ref_count
  FROM common_event_outbox
  WHERE source_run_id = v_preload_run_id
     OR payload_json::text LIKE '%' || v_preload_run_id || '%';
  IF v_ref_count <> 0 THEN
    RAISE EXCEPTION 'Blocked: scoped outbox refs exist';
  END IF;

  SELECT count(*) INTO v_ref_count
  FROM common_event_inbox
  WHERE source_run_id = v_preload_run_id
     OR payload_json::text LIKE '%' || v_preload_run_id || '%'
     OR raw_json::text LIKE '%' || v_preload_run_id || '%';
  IF v_ref_count <> 0 THEN
    RAISE EXCEPTION 'Blocked: scoped inbox refs exist';
  END IF;

  SELECT count(*) INTO v_ref_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%' || v_preload_run_id || '%';
  IF v_ref_count <> 0 THEN
    RAISE EXCEPTION 'Blocked: scoped checkpoint refs exist';
  END IF;

  SELECT count(*) INTO v_ref_count
  FROM stock_realtime_projection_metric
  WHERE source_snapshot_run_id = v_preload_run_id
     OR raw_json::text LIKE '%' || v_preload_run_id || '%';
  IF v_ref_count <> 0 THEN
    RAISE EXCEPTION 'Blocked: stock projection refs exist';
  END IF;

  SELECT count(*) INTO v_ref_count
  FROM index_realtime_projection_metric
  WHERE source_snapshot_run_id = v_preload_run_id
     OR raw_json::text LIKE '%' || v_preload_run_id || '%';
  IF v_ref_count <> 0 THEN
    RAISE EXCEPTION 'Blocked: index projection refs exist';
  END IF;

  SELECT count(*) INTO v_ref_count
  FROM board_realtime_projection_metric
  WHERE source_snapshot_run_id = v_preload_run_id
     OR raw_json::text LIKE '%' || v_preload_run_id || '%';
  IF v_ref_count <> 0 THEN
    RAISE EXCEPTION 'Blocked: board projection refs exist';
  END IF;

  SELECT count(*) INTO v_ref_count
  FROM common_trigger_run
  WHERE source_market_data_run_id = v_preload_run_id
     OR raw_json::text LIKE '%' || v_preload_run_id || '%'
     OR raw_json::text LIKE '%' || v_source_subscription_run_id || '%';
  IF v_ref_count <> 0 THEN
    RAISE EXCEPTION 'Blocked: N4 refs exist';
  END IF;

  SELECT count(*) INTO v_ref_count
  FROM common_action_run
  WHERE raw_json::text LIKE '%' || v_preload_run_id || '%';
  IF v_ref_count <> 0 THEN
    RAISE EXCEPTION 'Blocked: N5 refs exist';
  END IF;

  SELECT count(*) INTO v_ref_count
  FROM user_projection_run
  WHERE source_action_run_id = v_preload_run_id
     OR source_n5_outbox_range::text LIKE '%' || v_preload_run_id || '%';
  IF v_ref_count <> 0 THEN
    RAISE EXCEPTION 'Blocked: N6 projection run refs exist';
  END IF;

  SELECT count(*) INTO v_ref_count
  FROM user_signal_projection
  WHERE source_payload_json::text LIKE '%' || v_preload_run_id || '%'
     OR display_payload_json::text LIKE '%' || v_preload_run_id || '%'
     OR trace_json::text LIKE '%' || v_preload_run_id || '%';
  IF v_ref_count <> 0 THEN
    RAISE EXCEPTION 'Blocked: N6 signal projection refs exist';
  END IF;

  SELECT count(*) INTO v_ref_count
  FROM user_signal_card
  WHERE card_payload_json::text LIKE '%' || v_preload_run_id || '%'
     OR trace_json::text LIKE '%' || v_preload_run_id || '%';
  IF v_ref_count <> 0 THEN
    RAISE EXCEPTION 'Blocked: N6 signal card refs exist';
  END IF;

  SELECT count(*) INTO v_ref_count
  FROM user_notification_queue
  WHERE notification_payload_json::text LIKE '%' || v_preload_run_id || '%'
     OR trace_json::text LIKE '%' || v_preload_run_id || '%';
  IF v_ref_count <> 0 THEN
    RAISE EXCEPTION 'Blocked: notification refs exist';
  END IF;
END $$;

DELETE FROM stock_previous_day_minute_preload_status
WHERE run_id = :'preload_run_id'
  AND source_condition_run_id = :'source_condition_run_id'
  AND trade_date = :'data_trade_date'
  AND raw_json::text LIKE '%' || :'source_subscription_run_id' || '%';

DELETE FROM index_previous_day_minute_preload_status
WHERE run_id = :'preload_run_id'
  AND source_condition_run_id = :'source_condition_run_id'
  AND trade_date = :'data_trade_date'
  AND raw_json::text LIKE '%' || :'source_subscription_run_id' || '%';

DELETE FROM board_previous_day_minute_preload_status
WHERE run_id = :'preload_run_id'
  AND source_condition_run_id = :'source_condition_run_id'
  AND trade_date = :'data_trade_date'
  AND raw_json::text LIKE '%' || :'source_subscription_run_id' || '%';

DELETE FROM stock_minute_bar_1m
WHERE run_id = :'preload_run_id'
  AND source_condition_run_id = :'source_condition_run_id'
  AND trade_date = :'data_trade_date'
  AND for_trade_date = :'for_trade_date'
  AND is_previous_day_preload = true
  AND raw_json::text LIKE '%' || :'source_subscription_run_id' || '%';

DELETE FROM index_minute_bar_1m
WHERE run_id = :'preload_run_id'
  AND source_condition_run_id = :'source_condition_run_id'
  AND trade_date = :'data_trade_date'
  AND for_trade_date = :'for_trade_date'
  AND is_previous_day_preload = true
  AND raw_json::text LIKE '%' || :'source_subscription_run_id' || '%';

DELETE FROM board_minute_bar_1m
WHERE run_id = :'preload_run_id'
  AND source_condition_run_id = :'source_condition_run_id'
  AND trade_date = :'data_trade_date'
  AND for_trade_date = :'for_trade_date'
  AND is_previous_day_preload = true
  AND raw_json::text LIKE '%' || :'source_subscription_run_id' || '%';

DELETE FROM common_market_data_quality_item
WHERE run_id = :'preload_run_id'
  AND source_condition_run_id = :'source_condition_run_id'
  AND for_trade_date = :'for_trade_date';

DELETE FROM common_market_data_run
WHERE run_id = :'preload_run_id'
  AND source_condition_run_id = :'source_condition_run_id'
  AND for_trade_date = :'for_trade_date';

COMMIT;
