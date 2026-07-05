-- N3 previous-day full-context expansion subscription scope rollback.
-- Scope: only previous_day_minute_bar_1m control rows for market_data_subscription_20260603_full_context_expansion_condition_layer_20260602_source_20260602_v1.
-- Hard-fails before DELETE if previous-day business rows, event infra, or downstream refs exist.

\set ON_ERROR_STOP on
\set run_id 'market_data_subscription_20260603_full_context_expansion_condition_layer_20260602_source_20260602_v1'
\set required_data_kind 'previous_day_minute_bar_1m'

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'market_data_subscription_20260603_full_context_expansion_condition_layer_20260602_source_20260602_v1';
  v_count BIGINT;
  v_table TEXT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = v_run_id OR payload_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing previous-day full-context scope rollback: outbox has % refs for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = v_run_id OR payload_json::TEXT LIKE '%' || v_run_id || '%' OR raw_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing previous-day full-context scope rollback: inbox has % refs for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || v_run_id || '%' OR last_event_id LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing previous-day full-context scope rollback: checkpoint has % refs for %', v_count, v_run_id;
  END IF;

  FOREACH v_table IN ARRAY ARRAY[
    'stock_minute_bar_1m', 'index_minute_bar_1m', 'board_minute_bar_1m',
    'stock_previous_day_minute_preload_status', 'index_previous_day_minute_preload_status', 'board_previous_day_minute_preload_status',
    'stock_action_confirmation_projection_metric', 'index_action_confirmation_projection_metric', 'board_action_confirmation_projection_metric',
    'common_trigger_run', 'common_trigger_state', 'common_trigger_match', 'common_trigger_quality_item',
    'common_action_run', 'common_action_event', 'common_action_quality_item',
    'user_signal_projection', 'user_signal_card', 'user_notification_queue'
  ] LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE 'SELECT count(*) FROM public.' || quote_ident(v_table) || ' t WHERE to_jsonb(t)::TEXT LIKE $1'
        INTO v_count
        USING '%' || v_run_id || '%';
      IF v_count <> 0 THEN
        RAISE EXCEPTION 'Refusing previous-day full-context scope rollback: table % has % refs for %', v_table, v_count, v_run_id;
      END IF;
    END IF;
  END LOOP;
END $$;

DELETE FROM common_market_data_pull_plan
WHERE run_id = :'run_id'
  AND required_data_kind = 'previous_day_minute_bar_1m';

DELETE FROM common_market_data_subscription
WHERE run_id = :'run_id'
  AND required_data_kind = 'previous_day_minute_bar_1m';

DELETE FROM common_market_data_subscription_candidate
WHERE run_id = :'run_id'
  AND required_data_kind = 'previous_day_minute_bar_1m';

COMMIT;
