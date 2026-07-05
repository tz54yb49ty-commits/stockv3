-- Scoped rollback for N3 C1 full-day excluding-BJ-blocker backfill.
-- run_id=today_minute_bar_1m_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
BEGIN;
DO $$
DECLARE
  v_run_id text := 'today_minute_bar_1m_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
  v_trade_date text := '20260617';
  v_count bigint;
BEGIN
  IF current_setting('ashare_v3.allow_n3_20260617_excluding_bj_c1_rollback', true) <> 'true' THEN
    RAISE EXCEPTION 'rollback blocked: set ashare_v3.allow_n3_20260617_excluding_bj_c1_rollback=true in an approved N3 rollback gate';
  END IF;
  SELECT count(*) INTO v_count FROM common_market_data_run WHERE run_id=v_run_id AND (downstream_layers_touched=true OR worker_started=true);
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: downstream/worker refs for %', v_run_id; END IF;
  SELECT count(*) INTO v_count FROM common_event_outbox WHERE source_run_id=v_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: outbox refs for %', v_run_id; END IF;
  SELECT count(*) INTO v_count FROM common_event_inbox WHERE source_run_id=v_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: inbox refs for %', v_run_id; END IF;
  SELECT count(*) INTO v_count FROM common_event_consumer_checkpoint WHERE checkpoint_payload::text LIKE '%' || v_run_id || '%' OR last_event_id LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: checkpoint refs for %', v_run_id; END IF;
  DELETE FROM stock_minute_bar_1m WHERE run_id=v_run_id AND trade_date=v_trade_date AND is_previous_day_preload=false;
  DELETE FROM index_minute_bar_1m WHERE run_id=v_run_id AND trade_date=v_trade_date AND is_previous_day_preload=false;
  DELETE FROM board_minute_bar_1m WHERE run_id=v_run_id AND trade_date=v_trade_date AND is_previous_day_preload=false;
  DELETE FROM common_market_data_quality_item WHERE run_id=v_run_id;
  DELETE FROM common_market_data_run WHERE run_id=v_run_id AND downstream_layers_touched=false AND worker_started=false;
END $$;
COMMIT;
