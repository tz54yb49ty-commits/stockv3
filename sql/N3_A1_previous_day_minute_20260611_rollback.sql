-- N3-A1 20260611 staged rollback plan.
-- Review before execution. Generated/updated by N3_A1_20260611_ROLLBACK_SCOPE_REPAIR_GATE; not executed in this gate.
-- Scope: Stage 2 previous-day minute preload rows plus Stage 1 subscription control rows for the scoped run ids.
-- Forbidden: N2 facts, N3-B/C/B2 facts, N4/N5/N6 facts, event infrastructure DML, old system, worker, delivery, sim/position/PnL, and real trading.

\set ON_ERROR_STOP on
\set subscription_run_id 'market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1'
\set source_run_id 'market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1'
\set preload_run_id 'previous_day_minute_preload_20260610_for_20260611__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1'
\set previous_day_minute_date '20260610'
\set source_condition_run_id 'condition_layer_20260610_source_20260610_for_20260611_v1'

BEGIN;

DO $$
DECLARE
  v_subscription_run_id TEXT := 'market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1';
  v_preload_run_id TEXT := 'previous_day_minute_preload_20260610_for_20260611__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1';
  v_run_ids TEXT[] := ARRAY[
    'market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1',
    'previous_day_minute_preload_20260610_for_20260611__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1'
  ];
  v_run_id TEXT;
  v_count BIGINT;
  v_table TEXT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_market_data_run
  WHERE run_id = ANY(v_run_ids)
    AND (downstream_layers_touched = true OR worker_started = true);

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N3-A1 rollback: common_market_data_run has downstream/worker flags for staged run ids in % rows', v_count;
  END IF;

  FOREACH v_run_id IN ARRAY v_run_ids LOOP
    SELECT count(*) INTO v_count
    FROM common_event_outbox
    WHERE source_run_id = v_run_id
       OR payload_json::TEXT LIKE '%' || v_run_id || '%';

    IF v_count <> 0 THEN
      RAISE EXCEPTION 'Refusing N3-A1 rollback: common_event_outbox has % rows for %', v_count, v_run_id;
    END IF;

    SELECT count(*) INTO v_count
    FROM common_event_inbox
    WHERE source_run_id = v_run_id
       OR payload_json::TEXT LIKE '%' || v_run_id || '%'
       OR raw_json::TEXT LIKE '%' || v_run_id || '%';

    IF v_count <> 0 THEN
      RAISE EXCEPTION 'Refusing N3-A1 rollback: common_event_inbox has % rows for %', v_count, v_run_id;
    END IF;

    SELECT count(*) INTO v_count
    FROM common_event_consumer_checkpoint
    WHERE checkpoint_payload::TEXT LIKE '%' || v_run_id || '%'
       OR last_event_id LIKE '%' || v_run_id || '%';

    IF v_count <> 0 THEN
      RAISE EXCEPTION 'Refusing N3-A1 rollback: common_event_consumer_checkpoint references % in % rows', v_run_id, v_count;
    END IF;
  END LOOP;

  FOREACH v_table IN ARRAY ARRAY[
    'stock_realtime_daily_snapshot',
    'index_realtime_daily_snapshot',
    'board_realtime_daily_snapshot',
    'common_trigger_run',
    'common_trigger_state',
    'common_trigger_match',
    'common_trigger_quality_item',
    'common_action_run',
    'common_action_event',
    'common_action_quality_item',
    'user_projection_run',
    'user_signal_projection',
    'user_signal_card',
    'user_market_projection',
    'user_card_projection',
    'user_voice_delivery',
    'user_notification_queue',
    'sim_projection',
    'position_projection',
    'real_trade_order',
    'user_sim_order',
    'user_sim_trade',
    'user_sim_position',
    'n6_virtual_account',
    'n6_virtual_order',
    'n6_virtual_trade',
    'n6_virtual_position',
    'n6_virtual_position_event',
    'n6_virtual_pnl_snapshot',
    'stock_closed_30m_summary',
    'index_closed_30m_summary',
    'board_closed_30m_summary',
    'stock_closed_30m_signal_enrichment',
    'index_closed_30m_signal_enrichment',
    'board_closed_30m_signal_enrichment',
    'stock_realtime_projection_metric',
    'index_realtime_projection_metric',
    'board_realtime_projection_metric',
    'stock_projection_enrichment_v4_metric',
    'index_projection_enrichment_v4_metric',
    'board_projection_enrichment_v4_metric',
    'stock_action_confirmation_projection_metric',
    'index_action_confirmation_projection_metric',
    'board_action_confirmation_projection_metric'
  ] LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE format('SELECT count(*) FROM %I t WHERE row_to_json(t)::TEXT LIKE ''%%'' || $1 || ''%%'' OR row_to_json(t)::TEXT LIKE ''%%'' || $2 || ''%%''', v_table)
        INTO v_count
        USING v_subscription_run_id, v_preload_run_id;

      IF v_count <> 0 THEN
        RAISE EXCEPTION 'Refusing N3-A1 rollback: downstream table % references staged run ids in % rows', v_table, v_count;
      END IF;
    END IF;
  END LOOP;
END $$;

DELETE FROM stock_previous_day_minute_preload_status
WHERE run_id = :'preload_run_id'
  AND trade_date = :'previous_day_minute_date'
  AND source_condition_run_id = :'source_condition_run_id'
  AND raw_json ->> 'source_run_id' = :'source_run_id'
  AND raw_json ->> 'preload_run_id' = :'preload_run_id';

DELETE FROM stock_minute_bar_1m
WHERE run_id = :'preload_run_id'
  AND trade_date = :'previous_day_minute_date'
  AND source_condition_run_id = :'source_condition_run_id'
  AND is_previous_day_preload = true
  AND stock_identity_key LIKE 'stock:%'
  AND raw_json ->> 'source_run_id' = :'source_run_id'
  AND raw_json ->> 'preload_run_id' = :'preload_run_id';

DELETE FROM index_previous_day_minute_preload_status
WHERE run_id = :'preload_run_id'
  AND trade_date = :'previous_day_minute_date'
  AND source_condition_run_id = :'source_condition_run_id'
  AND raw_json ->> 'source_run_id' = :'source_run_id'
  AND raw_json ->> 'preload_run_id' = :'preload_run_id';

DELETE FROM index_minute_bar_1m
WHERE run_id = :'preload_run_id'
  AND trade_date = :'previous_day_minute_date'
  AND source_condition_run_id = :'source_condition_run_id'
  AND is_previous_day_preload = true
  AND index_identity_key LIKE 'index:%'
  AND raw_json ->> 'source_run_id' = :'source_run_id'
  AND raw_json ->> 'preload_run_id' = :'preload_run_id';

DELETE FROM board_previous_day_minute_preload_status
WHERE run_id = :'preload_run_id'
  AND trade_date = :'previous_day_minute_date'
  AND source_condition_run_id = :'source_condition_run_id'
  AND raw_json ->> 'source_run_id' = :'source_run_id'
  AND raw_json ->> 'preload_run_id' = :'preload_run_id';

DELETE FROM board_minute_bar_1m
WHERE run_id = :'preload_run_id'
  AND trade_date = :'previous_day_minute_date'
  AND source_condition_run_id = :'source_condition_run_id'
  AND is_previous_day_preload = true
  AND board_identity_key LIKE 'board:%'
  AND raw_json ->> 'source_run_id' = :'source_run_id'
  AND raw_json ->> 'preload_run_id' = :'preload_run_id';

DELETE FROM common_market_data_quality_item
WHERE run_id = :'preload_run_id'
  AND source_condition_run_id = :'source_condition_run_id'
  AND details ->> 'source_run_id' = :'source_run_id'
  AND details ->> 'preload_run_id' = :'preload_run_id';

DELETE FROM common_market_data_run
WHERE run_id = :'preload_run_id'
  AND source_condition_run_id = :'source_condition_run_id'
  AND raw_json ->> 'source_run_id' = :'source_run_id'
  AND raw_json ->> 'preload_run_id' = :'preload_run_id'
  AND downstream_layers_touched = false
  AND worker_started = false;

DELETE FROM common_market_data_pull_plan
WHERE run_id = :'subscription_run_id'
  AND source_condition_run_id = :'source_condition_run_id';

DELETE FROM common_market_data_subscription
WHERE run_id = :'subscription_run_id'
  AND source_condition_run_id = :'source_condition_run_id';

DELETE FROM common_market_data_subscription_candidate
WHERE run_id = :'subscription_run_id'
  AND source_condition_run_id = :'source_condition_run_id';

DELETE FROM common_market_data_quality_item
WHERE run_id = :'subscription_run_id'
  AND source_condition_run_id = :'source_condition_run_id';

DELETE FROM common_market_data_run
WHERE run_id = :'subscription_run_id'
  AND source_condition_run_id = :'source_condition_run_id'
  AND downstream_layers_touched = false
  AND worker_started = false;

COMMIT;
