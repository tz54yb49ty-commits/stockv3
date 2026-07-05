BEGIN;

DO $$
DECLARE
  v_run_id text := 'realtime_daily_snapshot_20260612_until_1422__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1';
  v_count integer;
BEGIN
  IF current_setting('ashare_v3.allow_n3_b1_20260612_interrupted_cleanup', true) IS DISTINCT FROM 'true' THEN
    RAISE EXCEPTION 'cleanup blocked by default; set ashare_v3.allow_n3_b1_20260612_interrupted_cleanup=true in this session';
  END IF;

  SELECT count(*) INTO v_count
  FROM common_market_data_run
  WHERE run_id = v_run_id
    AND status = 'running'
    AND market_data_pulled = false
    AND market_data_fact_written = false
    AND downstream_layers_touched = false
    AND worker_started = false;
  IF v_count <> 1 THEN
    RAISE EXCEPTION 'unexpected interrupted run target count: %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_market_data_quality_item WHERE run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'quality refs exist for interrupted run: %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_event_outbox WHERE source_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'outbox refs exist for interrupted run: %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_event_inbox WHERE source_run_id = v_run_id OR raw_json::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'inbox refs exist for interrupted run: %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM stock_realtime_projection_metric WHERE source_snapshot_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'stock B2 refs exist for interrupted run: %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM index_realtime_projection_metric WHERE source_snapshot_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'index B2 refs exist for interrupted run: %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM board_realtime_projection_metric WHERE source_snapshot_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'board B2 refs exist for interrupted run: %', v_count;
  END IF;
END $$;

DELETE FROM stock_realtime_daily_snapshot
WHERE run_id = 'realtime_daily_snapshot_20260612_until_1422__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1';

DELETE FROM index_realtime_daily_snapshot
WHERE run_id = 'realtime_daily_snapshot_20260612_until_1422__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1';

DELETE FROM board_realtime_daily_snapshot
WHERE run_id = 'realtime_daily_snapshot_20260612_until_1422__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1';

DELETE FROM common_market_data_run
WHERE run_id = 'realtime_daily_snapshot_20260612_until_1422__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1'
  AND status = 'running'
  AND market_data_pulled = false
  AND market_data_fact_written = false
  AND downstream_layers_touched = false
  AND worker_started = false;

COMMIT;
