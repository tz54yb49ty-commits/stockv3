-- N3 A1/C1 board minute lineage pull combined rollback plan.
-- Scope: only scoped A1 previous-day and C1 today board minute/status/quality/run rows.
-- Does not delete subscription control rows for market_data_subscription_20260605_action_metric_board_lineage_repair_condition_layer_20260604_source_20260604_v1.
-- Hard-fails before DELETE if metric_v2 rows, event infra, N4/N5/N6 refs, worker, or downstream flags exist.
\set ON_ERROR_STOP on
\set subscription_run_id 'market_data_subscription_20260605_action_metric_board_lineage_repair_condition_layer_20260604_source_20260604_v1'
\set previous_day_run_id 'previous_day_minute_preload_20260604_for_20260605_action_metric_board_lineage_repair__market_data_subscription_20260605_action_metric_board_lineage_repair_condition_layer_20260604_source_20260604_v1'
\set today_minute_run_id 'today_minute_bar_1m_20260605_until_1127_action_metric_board_lineage_repair__market_data_subscription_20260605_action_metric_board_lineage_repair_condition_layer_20260604_source_20260604_v1'
\set metric_run_id 'action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1'

SELECT set_config('app.subscription_run_id', :'subscription_run_id', false);
SELECT set_config('app.previous_day_run_id', :'previous_day_run_id', false);
SELECT set_config('app.today_minute_run_id', :'today_minute_run_id', false);
SELECT set_config('app.metric_run_id', :'metric_run_id', false);

DO $$
DECLARE
  subscription_run_id TEXT := current_setting('app.subscription_run_id');
  prev_run_id TEXT := current_setting('app.previous_day_run_id');
  today_run_id TEXT := current_setting('app.today_minute_run_id');
  metric_run_id TEXT := current_setting('app.metric_run_id');
  v_count BIGINT;
  v_table TEXT;
BEGIN
  SELECT count(*) INTO v_count FROM board_action_confirmation_projection_metric
  WHERE projection_run_id = metric_run_id
     OR source_subscription_run_id = subscription_run_id
     OR source_previous_day_minute_run_id = prev_run_id
     OR source_today_minute_run_id = today_run_id
     OR source_minute_refs::TEXT LIKE '%' || today_run_id || '%'
     OR previous_day_minute_refs::TEXT LIKE '%' || prev_run_id || '%'
     OR source_fact_ids::TEXT LIKE '%' || subscription_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing A1/C1 board-lineage rollback: metric_v2/action-confirmation refs exist: %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_event_outbox
  WHERE source_run_id IN (prev_run_id, today_run_id, metric_run_id)
     OR payload_json::TEXT LIKE '%' || prev_run_id || '%'
     OR payload_json::TEXT LIKE '%' || today_run_id || '%'
     OR payload_json::TEXT LIKE '%' || metric_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing A1/C1 rollback: outbox refs=%', v_count; END IF;

  SELECT count(*) INTO v_count FROM common_event_inbox
  WHERE source_run_id IN (prev_run_id, today_run_id, metric_run_id)
     OR payload_json::TEXT LIKE '%' || prev_run_id || '%'
     OR payload_json::TEXT LIKE '%' || today_run_id || '%'
     OR payload_json::TEXT LIKE '%' || metric_run_id || '%'
     OR raw_json::TEXT LIKE '%' || prev_run_id || '%'
     OR raw_json::TEXT LIKE '%' || today_run_id || '%'
     OR raw_json::TEXT LIKE '%' || metric_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing A1/C1 rollback: inbox refs=%', v_count; END IF;

  SELECT count(*) INTO v_count FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || prev_run_id || '%'
     OR checkpoint_payload::TEXT LIKE '%' || today_run_id || '%'
     OR checkpoint_payload::TEXT LIKE '%' || metric_run_id || '%'
     OR last_event_id LIKE '%' || prev_run_id || '%'
     OR last_event_id LIKE '%' || today_run_id || '%'
     OR last_event_id LIKE '%' || metric_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing A1/C1 rollback: checkpoint refs=%', v_count; END IF;

  SELECT count(*) INTO v_count FROM common_market_data_run
  WHERE run_id IN (prev_run_id, today_run_id) AND (downstream_layers_touched = true OR worker_started = true);
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing A1/C1 rollback: downstream/worker flags exist=%', v_count; END IF;

  FOREACH v_table IN ARRAY ARRAY[
    'common_trigger_run','common_trigger_state','common_trigger_match','common_trigger_quality_item',
    'common_action_run','common_action_event','common_action_quality_item',
    'user_projection_run','user_signal_projection','user_signal_card','user_notification_queue',
    'user_sim_order','user_sim_trade','user_sim_position','n6_virtual_order','n6_virtual_trade','n6_virtual_position',
    'stock_closed_30m_summary','index_closed_30m_summary','board_closed_30m_summary',
    'stock_realtime_projection_metric','index_realtime_projection_metric','board_realtime_projection_metric'
  ] LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE 'SELECT count(*) FROM public.' || quote_ident(v_table) || ' t WHERE to_jsonb(t)::TEXT LIKE $1 OR to_jsonb(t)::TEXT LIKE $2'
        INTO v_count USING '%' || prev_run_id || '%', '%' || today_run_id || '%';
      IF v_count <> 0 THEN
        RAISE EXCEPTION 'Refusing A1/C1 rollback: downstream table % refs=%', v_table, v_count;
      END IF;
    END IF;
  END LOOP;
END $$;

BEGIN;

DELETE FROM board_previous_day_minute_preload_status
WHERE run_id = :'previous_day_run_id'
  AND trade_date = '20260604';

DELETE FROM board_minute_bar_1m
WHERE run_id = :'previous_day_run_id'
  AND trade_date = '20260604'
  AND is_previous_day_preload = true;

DELETE FROM board_minute_bar_1m
WHERE run_id = :'today_minute_run_id'
  AND trade_date = '20260605'
  AND is_previous_day_preload = false;

DELETE FROM common_market_data_quality_item
WHERE run_id IN (:'previous_day_run_id', :'today_minute_run_id');

DELETE FROM common_market_data_run
WHERE run_id IN (:'previous_day_run_id', :'today_minute_run_id')
  AND downstream_layers_touched = false
  AND worker_started = false;

COMMIT;
