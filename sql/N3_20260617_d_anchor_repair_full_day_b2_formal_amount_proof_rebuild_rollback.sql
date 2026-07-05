-- N3 20260617 D-anchor full-day B2 formal amount proof rollback.
-- Scope: projection_run_id=action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
BEGIN;
SET LOCAL ashare_v3.allow_n3_20260617_d_anchor_b2_formal_amount_rollback = 'true';
DO $$
DECLARE
  v_run_id text := 'action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
  v_refs bigint;
BEGIN
  IF current_setting('ashare_v3.allow_n3_20260617_d_anchor_b2_formal_amount_rollback', true) <> 'true' THEN
    RAISE EXCEPTION 'rollback blocked: set scoped session flag';
  END IF;
  SELECT count(*) INTO v_refs FROM common_event_outbox WHERE source_run_id = v_run_id;
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: common_event_outbox refs=%', v_refs; END IF;
  SELECT count(*) INTO v_refs FROM common_event_inbox WHERE source_run_id = v_run_id;
  IF v_refs <> 0 THEN RAISE EXCEPTION 'rollback blocked: common_event_inbox refs=%', v_refs; END IF;
END $$;
DELETE FROM stock_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM index_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM board_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM common_market_data_quality_item WHERE run_id = 'action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM common_market_data_run WHERE run_id = 'action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
COMMIT;
