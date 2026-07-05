-- N3 20260605 B2 stock/index minute lineage expansion subscription rollback.
-- Scope: market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1
-- Deletes only additive N3 subscription/candidate/pull_plan/control rows for this expansion run.
-- Hard-fails before DELETE if any event, fact, B2, N4, N5, N6, worker, or downstream reference exists.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1';
  v_count BIGINT;
  v_table TEXT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = v_run_id OR payload_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N3 B2 lineage expansion rollback: common_event_outbox has % refs for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = v_run_id OR payload_json::TEXT LIKE '%' || v_run_id || '%' OR raw_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N3 B2 lineage expansion rollback: common_event_inbox has % refs for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N3 B2 lineage expansion rollback: checkpoint has % refs for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_market_data_run
  WHERE run_id = v_run_id
    AND (COALESCE(market_data_pulled, false)
      OR COALESCE(market_data_fact_written, false)
      OR COALESCE(downstream_layers_touched, false)
      OR COALESCE(worker_started, false));
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N3 B2 lineage expansion rollback: run flags indicate facts/downstream/worker for %', v_run_id;
  END IF;

  FOREACH v_table IN ARRAY ARRAY[
    'stock_minute_bar_1m', 'index_minute_bar_1m', 'board_minute_bar_1m',
    'stock_previous_day_minute_preload_status', 'index_previous_day_minute_preload_status', 'board_previous_day_minute_preload_status',
    'stock_realtime_daily_snapshot', 'index_realtime_daily_snapshot', 'board_realtime_daily_snapshot',
    'stock_realtime_projection_metric', 'index_realtime_projection_metric', 'board_realtime_projection_metric',
    'stock_projection_enrichment_v4_metric', 'index_projection_enrichment_v4_metric', 'board_projection_enrichment_v4_metric',
    'stock_action_confirmation_projection_metric', 'index_action_confirmation_projection_metric', 'board_action_confirmation_projection_metric',
    'common_trigger_run', 'common_trigger_state', 'common_trigger_match', 'common_trigger_quality_item',
    'common_action_run', 'common_action_event', 'common_action_quality_item',
    'user_card_projection', 'user_market_projection', 'user_voice_delivery', 'user_signal_projection',
    'user_projection_run', 'user_notification_queue', 'sim_projection', 'position_projection', 'real_trade_order'
  ] LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE 'SELECT count(*) FROM public.' || quote_ident(v_table) || ' t WHERE to_jsonb(t)::TEXT LIKE $1'
        INTO v_count
        USING '%' || v_run_id || '%';
      IF v_count <> 0 THEN
        RAISE EXCEPTION 'Refusing N3 B2 lineage expansion rollback: downstream/fact table % has % refs for %', v_table, v_count, v_run_id;
      END IF;
    END IF;
  END LOOP;
END $$;

DELETE FROM common_market_data_pull_plan
WHERE run_id = 'market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1';

DELETE FROM common_market_data_subscription
WHERE run_id = 'market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1';

DELETE FROM common_market_data_subscription_candidate
WHERE run_id = 'market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1';

DELETE FROM common_market_data_quality_item
WHERE run_id = 'market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1';

DELETE FROM common_market_data_run
WHERE run_id = 'market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1'
  AND COALESCE(market_data_pulled, false) = false
  AND COALESCE(market_data_fact_written, false) = false
  AND COALESCE(downstream_layers_touched, false) = false
  AND COALESCE(worker_started, false) = false;

COMMIT;

-- Boundary proof:
-- - Does not touch source subscription: market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1
-- - Does not touch source B1 snapshot: realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1
-- - Does not touch current C1: today_minute_bar_1m_20260605_until_1127__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1
-- - Does not touch A1/C1 minute facts, B2 projection facts, outbox/inbox/checkpoint, N4/N5/N6.
