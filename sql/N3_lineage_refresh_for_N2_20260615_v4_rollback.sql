-- N3 lineage refresh for N2 20260615 v4 rollback plan.
-- Scope: only new v4 N3 subscription control rows and new v4 A1 previous-day preload rows.
-- Preserves previous v1/v2/v3 lineage rows and all N2/N4/N5/N6 facts.
-- Not executed by contract/preflight/final gate.

\set ON_ERROR_STOP on
\set subscription_run_id 'market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4'
\set preload_run_id 'previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4'
\set source_condition_run_id 'condition_layer_20260615_source_20260615_for_20260616_v4'
\set data_trade_date '20260615'

BEGIN;

DO $$
BEGIN
  IF current_setting('ashare_v3.allow_n3_lineage_refresh_20260615_v4_rollback', true) IS DISTINCT FROM 'true' THEN
    RAISE EXCEPTION 'Refusing N3 lineage refresh v4 rollback: set ashare_v3.allow_n3_lineage_refresh_20260615_v4_rollback=true after runtime_control approval';
  END IF;
END $$;

DO $$
DECLARE
  v_subscription_run_id TEXT := 'market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';
  v_preload_run_id TEXT := 'previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';
  v_count BIGINT;
  v_table TEXT;
  v_run_ids TEXT[] := ARRAY[v_subscription_run_id, v_preload_run_id];
BEGIN
  SELECT count(*) INTO v_count
  FROM common_market_data_run
  WHERE run_id = ANY(v_run_ids)
    AND (downstream_layers_touched = true OR worker_started = true);
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N3 lineage refresh v4 rollback: downstream/worker flags set for target runs, count=%', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = ANY(v_run_ids)
     OR payload_json::TEXT LIKE '%' || v_subscription_run_id || '%'
     OR payload_json::TEXT LIKE '%' || v_preload_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N3 lineage refresh v4 rollback: outbox refs exist, count=%', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = ANY(v_run_ids)
     OR payload_json::TEXT LIKE '%' || v_subscription_run_id || '%'
     OR payload_json::TEXT LIKE '%' || v_preload_run_id || '%'
     OR raw_json::TEXT LIKE '%' || v_subscription_run_id || '%'
     OR raw_json::TEXT LIKE '%' || v_preload_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N3 lineage refresh v4 rollback: inbox refs exist, count=%', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || v_subscription_run_id || '%'
     OR checkpoint_payload::TEXT LIKE '%' || v_preload_run_id || '%'
     OR last_event_id LIKE '%' || v_subscription_run_id || '%'
     OR last_event_id LIKE '%' || v_preload_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N3 lineage refresh v4 rollback: checkpoint refs exist, count=%', v_count;
  END IF;

  FOREACH v_table IN ARRAY ARRAY[
    'stock_realtime_daily_snapshot', 'index_realtime_daily_snapshot', 'board_realtime_daily_snapshot',
    'stock_realtime_projection_metric', 'index_realtime_projection_metric', 'board_realtime_projection_metric',
    'stock_action_confirmation_projection_metric', 'index_action_confirmation_projection_metric', 'board_action_confirmation_projection_metric',
    'common_trigger_run', 'common_trigger_state', 'common_trigger_match', 'common_trigger_quality_item',
    'common_action_run', 'common_action_event', 'common_action_quality_item',
    'user_projection_run', 'user_signal_projection', 'user_signal_card', 'user_notification_queue',
    'user_sim_order', 'user_sim_trade', 'user_sim_position',
    'n6_virtual_account', 'n6_virtual_order', 'n6_virtual_trade', 'n6_virtual_position',
    'n6_virtual_position_event', 'n6_virtual_pnl_snapshot'
  ] LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE format('SELECT count(*) FROM %I t WHERE row_to_json(t)::TEXT LIKE ''%%'' || $1 || ''%%'' OR row_to_json(t)::TEXT LIKE ''%%'' || $2 || ''%%''', v_table)
        INTO v_count
        USING v_subscription_run_id, v_preload_run_id;
      IF v_count <> 0 THEN
        RAISE EXCEPTION 'Refusing N3 lineage refresh v4 rollback: downstream table % references target runs, count=%', v_table, v_count;
      END IF;
    END IF;
  END LOOP;
END $$;

-- Stage 2 A1 preload rows first.
DELETE FROM stock_previous_day_minute_preload_status
WHERE run_id = :'preload_run_id'
  AND trade_date = :'data_trade_date'
  AND source_condition_run_id = :'source_condition_run_id';

DELETE FROM index_previous_day_minute_preload_status
WHERE run_id = :'preload_run_id'
  AND trade_date = :'data_trade_date'
  AND source_condition_run_id = :'source_condition_run_id';

DELETE FROM board_previous_day_minute_preload_status
WHERE run_id = :'preload_run_id'
  AND trade_date = :'data_trade_date'
  AND source_condition_run_id = :'source_condition_run_id';

DELETE FROM stock_minute_bar_1m
WHERE run_id = :'preload_run_id'
  AND trade_date = :'data_trade_date'
  AND source_condition_run_id = :'source_condition_run_id'
  AND is_previous_day_preload = true;

DELETE FROM index_minute_bar_1m
WHERE run_id = :'preload_run_id'
  AND trade_date = :'data_trade_date'
  AND source_condition_run_id = :'source_condition_run_id'
  AND is_previous_day_preload = true;

DELETE FROM board_minute_bar_1m
WHERE run_id = :'preload_run_id'
  AND trade_date = :'data_trade_date'
  AND source_condition_run_id = :'source_condition_run_id'
  AND is_previous_day_preload = true;

DELETE FROM common_market_data_quality_item
WHERE run_id = :'preload_run_id'
  AND source_condition_run_id = :'source_condition_run_id';

DELETE FROM common_market_data_run
WHERE run_id = :'preload_run_id'
  AND source_condition_run_id = :'source_condition_run_id'
  AND downstream_layers_touched = false
  AND worker_started = false;

-- Stage 1 subscription control rows after dependent A1 rows.
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
