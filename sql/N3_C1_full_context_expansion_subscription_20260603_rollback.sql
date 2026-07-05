-- N3 C1 full-context expansion subscription rollback.
-- Scope: market_data_subscription_20260603_full_context_expansion_condition_layer_20260602_source_20260602_v1
-- This rollback deletes only additive N3 subscription control rows.
-- It hard-fails before DELETE if any market fact/event/downstream reference exists.

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
    RAISE EXCEPTION 'Refusing N3 expansion subscription rollback: outbox has % refs for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = v_run_id OR payload_json::TEXT LIKE '%' || v_run_id || '%' OR raw_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N3 expansion subscription rollback: inbox has % refs for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N3 expansion subscription rollback: checkpoint has % refs for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_market_data_run
  WHERE run_id = v_run_id
    AND (COALESCE(market_data_pulled, false)
      OR COALESCE(market_data_fact_written, false)
      OR COALESCE(downstream_layers_touched, false)
      OR COALESCE(worker_started, false));
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N3 expansion subscription rollback: run flags indicate downstream/fact usage for %', v_run_id;
  END IF;

  FOREACH v_table IN ARRAY ARRAY[
    'stock_minute_bar_1m', 'index_minute_bar_1m', 'board_minute_bar_1m',
    'stock_realtime_daily_snapshot', 'index_realtime_daily_snapshot', 'board_realtime_daily_snapshot',
    'stock_realtime_projection_metric', 'index_realtime_projection_metric', 'board_realtime_projection_metric',
    'stock_action_confirmation_projection_metric', 'index_action_confirmation_projection_metric', 'board_action_confirmation_projection_metric',
    'common_trigger_run', 'common_trigger_state', 'common_trigger_match', 'common_trigger_quality_item',
    'common_action_run', 'common_action_event', 'common_action_quality_item',
    'user_card_projection', 'user_market_projection', 'user_voice_delivery', 'user_signal_projection',
    'sim_projection', 'position_projection', 'real_trade_order'
  ] LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE 'SELECT count(*) FROM public.' || quote_ident(v_table) || ' t WHERE to_jsonb(t)::TEXT LIKE $1'
        INTO v_count
        USING '%' || v_run_id || '%';
      IF v_count <> 0 THEN
        RAISE EXCEPTION 'Refusing N3 expansion subscription rollback: downstream table % has % refs for %', v_table, v_count, v_run_id;
      END IF;
    END IF;
  END LOOP;
END $$;

DELETE FROM common_market_data_pull_plan
WHERE run_id = 'market_data_subscription_20260603_full_context_expansion_condition_layer_20260602_source_20260602_v1';

DELETE FROM common_market_data_subscription
WHERE run_id = 'market_data_subscription_20260603_full_context_expansion_condition_layer_20260602_source_20260602_v1';

DELETE FROM common_market_data_subscription_candidate
WHERE run_id = 'market_data_subscription_20260603_full_context_expansion_condition_layer_20260602_source_20260602_v1';

DELETE FROM common_market_data_quality_item
WHERE run_id = 'market_data_subscription_20260603_full_context_expansion_condition_layer_20260602_source_20260602_v1';

DELETE FROM common_market_data_run
WHERE run_id = 'market_data_subscription_20260603_full_context_expansion_condition_layer_20260602_source_20260602_v1'
  AND COALESCE(market_data_pulled, false) = false
  AND COALESCE(market_data_fact_written, false) = false
  AND COALESCE(downstream_layers_touched, false) = false
  AND COALESCE(worker_started, false) = false;

COMMIT;

-- Boundary:
-- - Does not touch original subscription run: market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
-- - Does not touch current C1 run: today_minute_bar_1m_20260603_until_1500__market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
-- - Does not touch minute/snapshot/projection facts, outbox/inbox/checkpoint, N4/N5/N6.
