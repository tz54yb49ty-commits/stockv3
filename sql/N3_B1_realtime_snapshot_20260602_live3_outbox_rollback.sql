-- N3-B1 realtime_daily_snapshot rollback plan.
-- Scope:
--   source_run_id:
--     market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
--   snapshot_run_id:
--     realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
-- Boundary:
--   Deletes only B1 scoped N3 snapshot facts, scoped pending/failed/dead_letter
--   N3 outbox rows, market-data quality rows, and the B1 market-data run row.
--   It does not touch N1/N2 facts, N4 trigger facts, N5 action facts/outbox,
--   N6 user projection, worker state, delivery, notification, push, voice,
--   mobile, sim, position, or real_trade rows.

\set ON_ERROR_STOP on
\set source_run_id 'market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1'
\set snapshot_run_id 'realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1'
\set for_trade_date '20260602'
\set source_condition_run_id 'condition_layer_20260601_source_20260601_v1'

SELECT set_config('app.b1_source_run_id', :'source_run_id', false);
SELECT set_config('app.b1_snapshot_run_id', :'snapshot_run_id', false);
SELECT set_config('app.b1_for_trade_date', :'for_trade_date', false);
SELECT set_config('app.b1_source_condition_run_id', :'source_condition_run_id', false);

-- Hard-fail guard: every check below runs before the first DELETE.
DO $$
DECLARE
  target_source_run_id TEXT := current_setting('app.b1_source_run_id');
  target_snapshot_run_id TEXT := current_setting('app.b1_snapshot_run_id');
  target_for_trade_date TEXT := current_setting('app.b1_for_trade_date');
  target_condition_run_id TEXT := current_setting('app.b1_source_condition_run_id');
  v_count BIGINT := 0;
  v_table_name TEXT;
  v_table_regclass REGCLASS;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_market_data_run
  WHERE run_id = target_snapshot_run_id
    AND source_condition_run_id = target_condition_run_id
    AND for_trade_date = target_for_trade_date
    AND (downstream_layers_touched IS TRUE OR worker_started IS TRUE);
  IF v_count > 0 THEN
    RAISE EXCEPTION
      'N3-B1 rollback blocked: common_market_data_run downstream_layers_touched/worker_started true for % (%)',
      target_snapshot_run_id,
      v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N3_market_data'
    AND source_run_id = target_snapshot_run_id
    AND status IN ('delivering', 'delivered');
  IF v_count > 0 THEN
    RAISE EXCEPTION
      'N3-B1 rollback blocked: scoped N3 outbox has delivered/delivering rows for % (%)',
      target_snapshot_run_id,
      v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N3_market_data'
    AND source_run_id = target_snapshot_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N3-B1 rollback blocked: downstream inbox refs exist for % (%)',
      target_snapshot_run_id,
      v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || target_snapshot_run_id || '%'
     OR checkpoint_payload::TEXT LIKE '%' || target_source_run_id || '%';
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N3-B1 rollback blocked: checkpoint refs exist for % (%)',
      target_snapshot_run_id,
      v_count;
  END IF;

  FOREACH v_table_name IN ARRAY ARRAY[
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
      EXECUTE format(
        'SELECT count(*) FROM %s t WHERE to_jsonb(t)::TEXT LIKE $1 OR to_jsonb(t)::TEXT LIKE $2',
        v_table_regclass
      )
      INTO v_count
      USING '%' || target_snapshot_run_id || '%', '%' || target_source_run_id || '%';
      IF v_count > 0 THEN
        RAISE EXCEPTION 'N3-B1 rollback blocked: downstream table % has refs for % / % (%)',
          v_table_name,
          target_snapshot_run_id,
          target_source_run_id,
          v_count;
      END IF;
    END IF;
  END LOOP;
END $$;

BEGIN;

DELETE FROM common_event_outbox
WHERE source_layer = 'N3_market_data'
  AND source_run_id = :'snapshot_run_id'
  AND status IN ('pending', 'failed', 'dead_letter');

DELETE FROM stock_realtime_daily_snapshot
WHERE run_id = :'snapshot_run_id'
  AND for_trade_date = :'for_trade_date'
  AND trade_date = :'for_trade_date'
  AND source_condition_run_id = :'source_condition_run_id'
  AND stock_identity_key LIKE 'stock:%'
  AND raw_json ->> 'source_run_id' = :'source_run_id'
  AND raw_json ->> 'snapshot_run_id' = :'snapshot_run_id';

DELETE FROM index_realtime_daily_snapshot
WHERE run_id = :'snapshot_run_id'
  AND for_trade_date = :'for_trade_date'
  AND trade_date = :'for_trade_date'
  AND source_condition_run_id = :'source_condition_run_id'
  AND index_identity_key LIKE 'index:%'
  AND raw_json ->> 'source_run_id' = :'source_run_id'
  AND raw_json ->> 'snapshot_run_id' = :'snapshot_run_id';

DELETE FROM board_realtime_daily_snapshot
WHERE run_id = :'snapshot_run_id'
  AND for_trade_date = :'for_trade_date'
  AND trade_date = :'for_trade_date'
  AND source_condition_run_id = :'source_condition_run_id'
  AND board_identity_key LIKE 'board:%'
  AND raw_json ->> 'source_run_id' = :'source_run_id'
  AND raw_json ->> 'snapshot_run_id' = :'snapshot_run_id';

DELETE FROM common_market_data_quality_item
WHERE run_id = :'snapshot_run_id'
  AND source_condition_run_id = :'source_condition_run_id'
  AND for_trade_date = :'for_trade_date'
  AND layer_scope = 'market_data_run'
  AND details ->> 'source_run_id' = :'source_run_id'
  AND details ->> 'snapshot_run_id' = :'snapshot_run_id';

DELETE FROM common_market_data_run
WHERE run_id = :'snapshot_run_id'
  AND source_condition_run_id = :'source_condition_run_id'
  AND for_trade_date = :'for_trade_date'
  AND raw_json ->> 'source_run_id' = :'source_run_id'
  AND (raw_json ->> 'snapshot_run_id' = :'snapshot_run_id' OR raw_json ->> 'run_id' = :'snapshot_run_id')
  AND downstream_layers_touched = false
  AND worker_started = false;

COMMIT;
