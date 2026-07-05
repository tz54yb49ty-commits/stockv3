\set ON_ERROR_STOP on

-- Scoped rollback for V3 20260616 corrected N3 metric scope expansion for ordinary/FULL.
-- Default hard-fail: runtime_control must explicitly SET the session flag before execution.
BEGIN;

DO $$
BEGIN
  IF current_setting('ashare_v3.allow_v3_20260616_n3_corrected_metric_scope_expansion_rollback', true) IS DISTINCT FROM 'true' THEN
    RAISE EXCEPTION 'hard-fail: set ashare_v3.allow_v3_20260616_n3_corrected_metric_scope_expansion_rollback=true before executing this rollback';
  END IF;
END $$;

DO $$
DECLARE
  v_run_id text := 'action_confirmation_projection_metric_20260616_until_1401_historical_replay_formal_amount_chain_scope_expansion_v1__trigger_context_snapshot_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';
  v_refs bigint;
BEGIN
  SELECT count(*) INTO v_refs FROM common_event_outbox WHERE source_run_id = v_run_id;
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: common_event_outbox refs exist for %', v_run_id; END IF;

  SELECT count(*) INTO v_refs FROM common_event_inbox WHERE source_run_id = v_run_id;
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: common_event_inbox refs exist for %', v_run_id; END IF;

  SELECT count(*) INTO v_refs
  FROM common_event_consumer_checkpoint
  WHERE coalesce(checkpoint_payload::text, '') LIKE '%' || v_run_id || '%';
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: common_event_consumer_checkpoint refs exist for %', v_run_id; END IF;

  SELECT count(*) INTO v_refs FROM common_trigger_run WHERE source_market_data_run_id = v_run_id;
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: common_trigger_run refs exist for %', v_run_id; END IF;

  SELECT count(*) INTO v_refs FROM common_action_run WHERE source_trigger_run_id = v_run_id;
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: common_action_run refs exist for %', v_run_id; END IF;

  SELECT count(*) INTO v_refs
  FROM common_market_data_run
  WHERE run_id = v_run_id AND (downstream_layers_touched OR worker_started);
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: downstream/worker flags set for %', v_run_id; END IF;
END $$;

DELETE FROM stock_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260616_until_1401_historical_replay_formal_amount_chain_scope_expansion_v1__trigger_context_snapshot_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';
DELETE FROM index_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260616_until_1401_historical_replay_formal_amount_chain_scope_expansion_v1__trigger_context_snapshot_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';
DELETE FROM board_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260616_until_1401_historical_replay_formal_amount_chain_scope_expansion_v1__trigger_context_snapshot_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';
DELETE FROM common_market_data_quality_item WHERE run_id = 'action_confirmation_projection_metric_20260616_until_1401_historical_replay_formal_amount_chain_scope_expansion_v1__trigger_context_snapshot_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';
DELETE FROM common_market_data_run WHERE run_id = 'action_confirmation_projection_metric_20260616_until_1401_historical_replay_formal_amount_chain_scope_expansion_v1__trigger_context_snapshot_20260616_condition_layer_20260615_source_20260615_for_20260616_v4';

COMMIT;
