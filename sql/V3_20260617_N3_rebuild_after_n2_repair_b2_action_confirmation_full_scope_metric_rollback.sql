-- V3 20260617 N3 repaired-N2 B2 action-confirmation metric rollback
-- Scope: projection_run_id=action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1.
-- Hard guard: abort if event infra references this metric run.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
  v_refs BIGINT;
BEGIN
  SELECT
    (SELECT count(*) FROM common_event_outbox WHERE source_run_id = v_run_id)
    + (SELECT count(*) FROM common_event_inbox WHERE source_run_id = v_run_id)
    + (SELECT count(*) FROM common_event_consumer_checkpoint WHERE checkpoint_payload::text LIKE '%' || v_run_id || '%')
  INTO v_refs;
  IF v_refs <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: event infra refs exist for % refs=%', v_run_id, v_refs;
  END IF;
END $$;

DELETE FROM stock_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM index_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM board_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM common_market_data_quality_item WHERE run_id = 'action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM common_market_data_run WHERE run_id = 'action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';

COMMIT;
