\set ON_ERROR_STOP on

-- Scoped rollback for V3 20260616 corrected metric ordinary/FULL source-expansion control rows.
-- Default hard-fail: runtime_control must explicitly SET the session flag before execution.
BEGIN;

DO $$
BEGIN
  IF current_setting('ashare_v3.allow_v3_20260616_historical_source_expansion_control_rows_rollback', true) IS DISTINCT FROM 'true' THEN
    RAISE EXCEPTION 'hard-fail: set ashare_v3.allow_v3_20260616_historical_source_expansion_control_rows_rollback=true before executing this rollback';
  END IF;
END $$;

DO $$
DECLARE
  v_run_id text := 'market_data_subscription_20260616_corrected_metric_ordinary_full_source_expansion__condition_layer_20260615_source_20260615_for_20260616_v4';
  v_expansion_run_id text := 'historical_source_expansion_20260616_until_1401_corrected_metric_ordinary_full__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';
  v_refs bigint;
BEGIN
  SELECT count(*) INTO v_refs FROM stock_minute_bar_1m WHERE run_id = v_expansion_run_id;
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: stock_minute_bar_1m expansion rows exist for %', v_expansion_run_id; END IF;
  SELECT count(*) INTO v_refs FROM index_minute_bar_1m WHERE run_id = v_expansion_run_id;
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: index_minute_bar_1m expansion rows exist for %', v_expansion_run_id; END IF;
  SELECT count(*) INTO v_refs FROM board_minute_bar_1m WHERE run_id = v_expansion_run_id;
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: board_minute_bar_1m expansion rows exist for %', v_expansion_run_id; END IF;

  SELECT count(*) INTO v_refs FROM common_event_outbox WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%';
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: common_event_outbox refs exist for %', v_run_id; END IF;
  SELECT count(*) INTO v_refs FROM common_event_inbox WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%' OR raw_json::text LIKE '%' || v_run_id || '%';
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: common_event_inbox refs exist for %', v_run_id; END IF;
  SELECT count(*) INTO v_refs FROM common_event_consumer_checkpoint WHERE coalesce(checkpoint_payload::text, '') LIKE '%' || v_run_id || '%';
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: common_event_consumer_checkpoint refs exist for %', v_run_id; END IF;
  SELECT count(*) INTO v_refs FROM common_trigger_run WHERE source_market_data_run_id = v_run_id;
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: common_trigger_run refs exist for %', v_run_id; END IF;
  SELECT count(*) INTO v_refs FROM common_action_run WHERE source_trigger_run_id = v_run_id;
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: common_action_run refs exist for %', v_run_id; END IF;
  SELECT count(*) INTO v_refs FROM common_market_data_run WHERE run_id = v_run_id AND (downstream_layers_touched OR worker_started);
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: downstream/worker flags set for %', v_run_id; END IF;
END $$;

DELETE FROM common_market_data_pull_plan WHERE run_id = 'market_data_subscription_20260616_corrected_metric_ordinary_full_source_expansion__condition_layer_20260615_source_20260615_for_20260616_v4';
DELETE FROM common_market_data_subscription WHERE run_id = 'market_data_subscription_20260616_corrected_metric_ordinary_full_source_expansion__condition_layer_20260615_source_20260615_for_20260616_v4';
DELETE FROM common_market_data_subscription_candidate WHERE run_id = 'market_data_subscription_20260616_corrected_metric_ordinary_full_source_expansion__condition_layer_20260615_source_20260615_for_20260616_v4';
DELETE FROM common_market_data_quality_item WHERE run_id = 'market_data_subscription_20260616_corrected_metric_ordinary_full_source_expansion__condition_layer_20260615_source_20260615_for_20260616_v4';
DELETE FROM common_market_data_run WHERE run_id = 'market_data_subscription_20260616_corrected_metric_ordinary_full_source_expansion__condition_layer_20260615_source_20260615_for_20260616_v4';

COMMIT;
