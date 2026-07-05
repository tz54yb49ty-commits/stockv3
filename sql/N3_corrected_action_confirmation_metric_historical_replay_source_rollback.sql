\set ON_ERROR_STOP on
BEGIN;

DO $$
BEGIN
  IF current_setting('ashare_v3.allow_n3_corrected_metric_historical_replay_source_rollback', true) IS DISTINCT FROM 'true' THEN
    RAISE EXCEPTION 'hard-fail: set ashare_v3.allow_n3_corrected_metric_historical_replay_source_rollback=true before running this scoped rollback';
  END IF;
END $$;

DO $$
DECLARE
  v_run_id text := 'action_confirmation_projection_metric_20260616_until_1401_historical_replay_formal_amount_chain_unit_proof__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';
  v_refs bigint;
BEGIN
  SELECT count(*) INTO v_refs FROM common_event_outbox WHERE source_run_id = v_run_id;
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: common_event_outbox refs exist for %', v_run_id; END IF;
  SELECT count(*) INTO v_refs FROM common_event_inbox WHERE source_run_id = v_run_id;
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: common_event_inbox refs exist for %', v_run_id; END IF;
  SELECT count(*) INTO v_refs FROM common_event_consumer_checkpoint WHERE position(v_run_id in coalesce(checkpoint_payload::text, '')) > 0;
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: common_event_consumer_checkpoint refs exist for %', v_run_id; END IF;
  SELECT count(*) INTO v_refs FROM common_trigger_run WHERE source_market_data_run_id = v_run_id;
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: common_trigger_run refs exist for %', v_run_id; END IF;
  SELECT count(*) INTO v_refs FROM common_action_run WHERE coalesce(source_trigger_run_id, '') = v_run_id;
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: common_action_run refs exist for %', v_run_id; END IF;
END $$;

DELETE FROM stock_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260616_until_1401_historical_replay_formal_amount_chain_unit_proof__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';
DELETE FROM index_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260616_until_1401_historical_replay_formal_amount_chain_unit_proof__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';
DELETE FROM board_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260616_until_1401_historical_replay_formal_amount_chain_unit_proof__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';
DELETE FROM common_market_data_quality_item WHERE run_id = 'action_confirmation_projection_metric_20260616_until_1401_historical_replay_formal_amount_chain_unit_proof__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';
DELETE FROM common_market_data_run WHERE run_id = 'action_confirmation_projection_metric_20260616_until_1401_historical_replay_formal_amount_chain_unit_proof__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';

COMMIT;
