-- N3 20260617 full-day B2 action-confirmation projection metric rollback.
-- Scope: projection_run_id=action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
-- Does not touch C1 minute facts, N2, N4/N5/N6, outbox/inbox/checkpoint consumption, voice/mobile/sim/order/real trade.
-- Required reviewed session variable:
--   SET LOCAL ashare_v3.allow_n3_20260617_full_day_b2_metric_rollback = 'true';

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
  v_count BIGINT;
BEGIN
  IF current_setting('ashare_v3.allow_n3_20260617_full_day_b2_metric_rollback', true) <> 'true' THEN
    RAISE EXCEPTION 'rollback blocked: missing reviewed session variable ashare_v3.allow_n3_20260617_full_day_b2_metric_rollback=true';
  END IF;
  SELECT count(*) INTO v_count FROM common_event_outbox WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: outbox refs=%', v_count; END IF;
  SELECT count(*) INTO v_count FROM common_event_inbox WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%' OR raw_json::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: inbox refs=%', v_count; END IF;
  IF to_regclass('public.common_event_consumer_checkpoint') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM common_event_consumer_checkpoint WHERE checkpoint_payload::text LIKE '%' || v_run_id || '%';
    IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: checkpoint refs=%', v_count; END IF;
  END IF;
  IF to_regclass('public.common_trigger_run') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM common_trigger_run WHERE COALESCE(source_market_data_run_id, '') = v_run_id OR raw_json::text LIKE '%' || v_run_id || '%';
    IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: N4 refs=%', v_count; END IF;
  END IF;
  IF to_regclass('public.common_action_run') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM common_action_run WHERE COALESCE(source_trigger_run_id, '') = v_run_id OR raw_json::text LIKE '%' || v_run_id || '%';
    IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: N5 refs=%', v_count; END IF;
  END IF;
END $$;

DELETE FROM board_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM index_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM stock_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM common_market_data_quality_item WHERE run_id = 'action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM common_market_data_run WHERE run_id = 'action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';

COMMIT;
