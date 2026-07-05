-- N3-C1 today minute_bar_1m rollback plan.
-- Scope:
--   today_minute_run_id:
--     today_minute_bar_1m_20260602_until_1105__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
-- Boundary:
--   Deletes only C1 scoped N3 minute facts, market-data quality rows, and the
--   C1 market-data run row. It does not touch N1/N2 facts, N4 trigger facts,
--   N5 action facts/outbox, N6 user projection, worker state, delivery,
--   notification, push, voice, mobile, sim, position, or real_trade rows.

\set ON_ERROR_STOP on
\set today_minute_run_id 'today_minute_bar_1m_20260602_until_1105__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1'

SELECT set_config('app.today_minute_run_id', :'today_minute_run_id', false);

-- Hard-fail guard: every check below runs before the first DELETE.
DO $$
DECLARE
  target_run_id TEXT := current_setting('app.today_minute_run_id');
  v_count BIGINT := 0;
  v_table_name TEXT;
  v_table_regclass REGCLASS;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_market_data_run
  WHERE run_id = target_run_id
    AND (downstream_layers_touched IS TRUE OR worker_started IS TRUE);
  IF v_count > 0 THEN
    RAISE EXCEPTION
      'N3-C1 rollback blocked: common_market_data_run downstream_layers_touched/worker_started true for % (%)',
      target_run_id,
      v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = target_run_id
     OR payload_json::TEXT LIKE '%' || target_run_id || '%';
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N3-C1 rollback blocked: outbox refs exist for % (%)', target_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = target_run_id
     OR payload_json::TEXT LIKE '%' || target_run_id || '%';
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N3-C1 rollback blocked: inbox refs exist for % (%)', target_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || target_run_id || '%';
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N3-C1 rollback blocked: checkpoint refs exist for % (%)', target_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE event_type IN ('MinuteBarClosed', 'MinuteBarCorrected')
    AND payload_json::TEXT LIKE '%' || target_run_id || '%';
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N3-C1 rollback blocked: MinuteBarClosed/MinuteBarCorrected refs exist for % (%)', target_run_id, v_count;
  END IF;

  FOREACH v_table_name IN ARRAY ARRAY[
    'stock_closed_30m_summary',
    'index_closed_30m_summary',
    'board_closed_30m_summary',
    'stock_closed_30m_signal_enrichment',
    'index_closed_30m_signal_enrichment',
    'board_closed_30m_signal_enrichment',
    'stock_action_confirmation_projection_metric',
    'index_action_confirmation_projection_metric',
    'board_action_confirmation_projection_metric',
    'common_trigger_run',
    'common_trigger_quality_item',
    'common_trigger_state',
    'common_trigger_match',
    'common_action_run',
    'common_action_quality_item',
    'stock_action_fact',
    'index_action_fact',
    'board_action_fact',
    'common_action_event',
    'common_event_outbox',
    'user_projection_run',
    'user_signal_projection',
    'user_signal_card',
    'user_signal_decision',
    'user_notification_queue',
    'user_notification_projection',
    'user_voice_delivery',
    'voice_delivery_queue',
    'mobile_projection',
    'mobile_notification_queue',
    'user_device_ack',
    'sim_projection',
    'sim_order',
    'sim_trade',
    'user_sim_order',
    'user_sim_trade',
    'user_sim_position',
    'common_position_state',
    'common_position_event',
    'position_state',
    'position_event',
    'real_trade_order',
    'real_trade_execution'
  ]
  LOOP
    v_table_regclass := to_regclass('public.' || v_table_name);
    IF v_table_regclass IS NOT NULL THEN
      EXECUTE format('SELECT count(*) FROM %s t WHERE to_jsonb(t)::TEXT LIKE $1', v_table_regclass)
      INTO v_count
      USING '%' || target_run_id || '%';
      IF v_count > 0 THEN
        RAISE EXCEPTION 'N3-C1 rollback blocked: downstream table % has refs for % (%)',
          v_table_name,
          target_run_id,
          v_count;
      END IF;
    END IF;
  END LOOP;
END $$;

BEGIN;

DELETE FROM common_market_data_quality_item
WHERE run_id = :'today_minute_run_id';

DELETE FROM stock_minute_bar_1m
WHERE run_id = :'today_minute_run_id'
  AND is_previous_day_preload = false;

DELETE FROM index_minute_bar_1m
WHERE run_id = :'today_minute_run_id'
  AND is_previous_day_preload = false;

DELETE FROM board_minute_bar_1m
WHERE run_id = :'today_minute_run_id'
  AND is_previous_day_preload = false;

DELETE FROM common_market_data_run
WHERE run_id = :'today_minute_run_id'
  AND downstream_layers_touched = false
  AND worker_started = false;

COMMIT;
