-- Scoped rollback for 20260629 14:55 N3P current_period_avg supersession target.
-- Do not execute unless a later rollback gate explicitly authorizes it.
\set target_run_id 'realtime_action_confirmation_metric_20260629_until_1455__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__market_data_subscription_20260629_condition_layer_20260626_source_20260626_for_20260629_v1'

BEGIN;

DO $$
DECLARE
  target text := 'realtime_action_confirmation_metric_20260629_until_1455__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__market_data_subscription_20260629_condition_layer_20260626_source_20260626_for_20260629_v1';
BEGIN
  IF EXISTS (
    SELECT 1 FROM common_event_outbox
    WHERE source_run_id = target AND status IN ('delivering', 'delivered')
  ) THEN
    RAISE EXCEPTION 'Refuse rollback: delivered/delivering outbox refs exist for %', target;
  END IF;

  IF EXISTS (
    SELECT 1 FROM common_event_inbox
    WHERE source_run_id = target OR payload_json::text LIKE '%' || target || '%'
  ) THEN
    RAISE EXCEPTION 'Refuse rollback: inbox refs exist for %', target;
  END IF;

  IF EXISTS (
    SELECT 1 FROM common_event_consumer_checkpoint
    WHERE checkpoint_payload::text LIKE '%' || target || '%'
  ) THEN
    RAISE EXCEPTION 'Refuse rollback: checkpoint refs exist for %', target;
  END IF;

  IF EXISTS (
    SELECT 1 FROM common_trigger_run
    WHERE source_market_data_run_id = target OR raw_json::text LIKE '%' || target || '%'
  ) THEN
    RAISE EXCEPTION 'Refuse rollback: N4 refs exist for %', target;
  END IF;

  IF EXISTS (
    SELECT 1 FROM common_action_run
    WHERE raw_json::text LIKE '%' || target || '%'
  ) THEN
    RAISE EXCEPTION 'Refuse rollback: N5 refs exist for %', target;
  END IF;
END $$;

DELETE FROM stock_action_confirmation_projection_metric
WHERE projection_run_id = :'target_run_id';

DELETE FROM index_action_confirmation_projection_metric
WHERE projection_run_id = :'target_run_id';

DELETE FROM board_action_confirmation_projection_metric
WHERE projection_run_id = :'target_run_id';

DELETE FROM common_market_data_quality_item
WHERE run_id = :'target_run_id';

DELETE FROM common_market_data_run
WHERE run_id = :'target_run_id';

COMMIT;
