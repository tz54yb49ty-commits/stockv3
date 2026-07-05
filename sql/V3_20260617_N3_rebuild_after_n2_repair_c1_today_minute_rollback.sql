-- N3-C1 today minute_bar_1m rollback plan.
-- Safe only before downstream MinuteBarClosed/C2 consumption; C1 itself writes no outbox.
-- Hard-fail before DELETE when scoped event infra, C2/projection, N4/N5/N6, downstream, or worker refs exist.
\set ON_ERROR_STOP on
\set today_minute_run_id 'today_minute_bar_1m_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1'

SELECT set_config('app.today_minute_run_id', :'today_minute_run_id', false);

DO $$
DECLARE
  target_run_id TEXT := current_setting('app.today_minute_run_id');
  outbox_refs BIGINT := 0;
  inbox_refs BIGINT := 0;
  checkpoint_refs BIGINT := 0;
  closed_30m_refs BIGINT := 0;
  realtime_projection_refs BIGINT := 0;
  trigger_refs BIGINT := 0;
  trigger_state_refs BIGINT := 0;
  action_refs BIGINT := 0;
  n6_refs BIGINT := 0;
  downstream_touched_refs BIGINT := 0;
  worker_started_refs BIGINT := 0;
BEGIN
  SELECT count(*) INTO outbox_refs
  FROM common_event_outbox
  WHERE source_run_id = target_run_id OR payload_json::TEXT LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO inbox_refs
  FROM common_event_inbox
  WHERE source_run_id = target_run_id
     OR payload_json::TEXT LIKE '%' || target_run_id || '%'
     OR raw_json::TEXT LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || target_run_id || '%'
     OR last_event_id LIKE '%' || target_run_id || '%';

  IF to_regclass('stock_closed_30m_summary') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM stock_closed_30m_summary WHERE to_jsonb(stock_closed_30m_summary)::TEXT LIKE $1'
      INTO closed_30m_refs USING '%' || target_run_id || '%';
  END IF;
  IF to_regclass('index_closed_30m_summary') IS NOT NULL THEN
    EXECUTE 'SELECT $1 + count(*) FROM index_closed_30m_summary WHERE to_jsonb(index_closed_30m_summary)::TEXT LIKE $2'
      INTO closed_30m_refs USING closed_30m_refs, '%' || target_run_id || '%';
  END IF;
  IF to_regclass('board_closed_30m_summary') IS NOT NULL THEN
    EXECUTE 'SELECT $1 + count(*) FROM board_closed_30m_summary WHERE to_jsonb(board_closed_30m_summary)::TEXT LIKE $2'
      INTO closed_30m_refs USING closed_30m_refs, '%' || target_run_id || '%';
  END IF;

  IF to_regclass('stock_realtime_projection_metric') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM stock_realtime_projection_metric WHERE to_jsonb(stock_realtime_projection_metric)::TEXT LIKE $1'
      INTO realtime_projection_refs USING '%' || target_run_id || '%';
  END IF;
  IF to_regclass('index_realtime_projection_metric') IS NOT NULL THEN
    EXECUTE 'SELECT $1 + count(*) FROM index_realtime_projection_metric WHERE to_jsonb(index_realtime_projection_metric)::TEXT LIKE $2'
      INTO realtime_projection_refs USING realtime_projection_refs, '%' || target_run_id || '%';
  END IF;
  IF to_regclass('board_realtime_projection_metric') IS NOT NULL THEN
    EXECUTE 'SELECT $1 + count(*) FROM board_realtime_projection_metric WHERE to_jsonb(board_realtime_projection_metric)::TEXT LIKE $2'
      INTO realtime_projection_refs USING realtime_projection_refs, '%' || target_run_id || '%';
  END IF;

  SELECT count(*) INTO trigger_refs
  FROM common_trigger_match
  WHERE raw_json::TEXT LIKE '%' || target_run_id || '%'
     OR source_event_id LIKE '%' || target_run_id || '%';

  IF to_regclass('common_trigger_state') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_trigger_state WHERE to_jsonb(common_trigger_state)::TEXT LIKE $1'
      INTO trigger_state_refs USING '%' || target_run_id || '%';
  END IF;

  SELECT count(*) INTO action_refs
  FROM common_action_event
  WHERE source_market_data_run_id = target_run_id
     OR source_market_trace::TEXT LIKE '%' || target_run_id || '%'
     OR payload_json::TEXT LIKE '%' || target_run_id || '%'
     OR trace_json::TEXT LIKE '%' || target_run_id || '%';

  IF to_regclass('user_projection_run') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_projection_run WHERE to_jsonb(user_projection_run)::TEXT LIKE $1'
      INTO n6_refs USING '%' || target_run_id || '%';
  END IF;
  IF to_regclass('user_signal_projection') IS NOT NULL THEN
    EXECUTE 'SELECT $1 + count(*) FROM user_signal_projection WHERE to_jsonb(user_signal_projection)::TEXT LIKE $2'
      INTO n6_refs USING n6_refs, '%' || target_run_id || '%';
  END IF;
  IF to_regclass('user_signal_card') IS NOT NULL THEN
    EXECUTE 'SELECT $1 + count(*) FROM user_signal_card WHERE to_jsonb(user_signal_card)::TEXT LIKE $2'
      INTO n6_refs USING n6_refs, '%' || target_run_id || '%';
  END IF;
  IF to_regclass('user_notification_queue') IS NOT NULL THEN
    EXECUTE 'SELECT $1 + count(*) FROM user_notification_queue WHERE to_jsonb(user_notification_queue)::TEXT LIKE $2'
      INTO n6_refs USING n6_refs, '%' || target_run_id || '%';
  END IF;

  SELECT count(*) INTO downstream_touched_refs
  FROM common_market_data_run
  WHERE run_id = target_run_id AND downstream_layers_touched = true;

  SELECT count(*) INTO worker_started_refs
  FROM common_market_data_run
  WHERE run_id = target_run_id AND worker_started = true;

  IF outbox_refs <> 0
     OR inbox_refs <> 0
     OR checkpoint_refs <> 0
     OR closed_30m_refs <> 0
     OR realtime_projection_refs <> 0
     OR trigger_refs <> 0
     OR trigger_state_refs <> 0
     OR action_refs <> 0
     OR n6_refs <> 0
     OR downstream_touched_refs <> 0
     OR worker_started_refs <> 0 THEN
    RAISE EXCEPTION
      'N3-C1 rollback blocked for %, outbox=%, inbox=%, checkpoint=%, closed_30m=%, realtime_projection=%, trigger=%, trigger_state=%, action=%, n6=%, downstream_touched=%, worker=%',
      target_run_id, outbox_refs, inbox_refs, checkpoint_refs, closed_30m_refs, realtime_projection_refs,
      trigger_refs, trigger_state_refs, action_refs, n6_refs, downstream_touched_refs, worker_started_refs;
  END IF;
END $$;

BEGIN;

DELETE FROM common_market_data_quality_item WHERE run_id = 'today_minute_bar_1m_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM stock_minute_bar_1m WHERE run_id = 'today_minute_bar_1m_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1' AND is_previous_day_preload = false;
DELETE FROM index_minute_bar_1m WHERE run_id = 'today_minute_bar_1m_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1' AND is_previous_day_preload = false;
DELETE FROM board_minute_bar_1m WHERE run_id = 'today_minute_bar_1m_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1' AND is_previous_day_preload = false;
DELETE FROM common_market_data_run WHERE run_id = 'today_minute_bar_1m_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1' AND downstream_layers_touched = false AND worker_started = false;

COMMIT;
