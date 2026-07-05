-- Scoped rollback for:
-- realtime_action_confirmation_metric_20260630_until_1500__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1
--
-- This rollback intentionally does not delete the source payload lineage run:
-- n3p_mixed_realtime_source_payload_20260630_until_1500_v1

BEGIN;

DO $$
DECLARE
    target_run_id text := 'realtime_action_confirmation_metric_20260630_until_1500__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1';
BEGIN
    IF EXISTS (
        SELECT 1
        FROM common_event_outbox
        WHERE source_run_id = target_run_id
          AND status IN ('delivering', 'delivered')
    ) THEN
        RAISE EXCEPTION 'rollback blocked: delivered/delivering outbox exists for %', target_run_id;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM common_event_inbox
        WHERE source_run_id = target_run_id
           OR payload_json::text LIKE '%' || target_run_id || '%'
    ) THEN
        RAISE EXCEPTION 'rollback blocked: inbox refs exist for %', target_run_id;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM common_event_consumer_checkpoint
        WHERE checkpoint_payload::text LIKE '%' || target_run_id || '%'
    ) THEN
        RAISE EXCEPTION 'rollback blocked: checkpoint refs exist for %', target_run_id;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM common_trigger_run
        WHERE source_market_data_run_id = target_run_id
           OR raw_json::text LIKE '%' || target_run_id || '%'
    ) THEN
        RAISE EXCEPTION 'rollback blocked: N4 trigger refs exist for %', target_run_id;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM common_action_run
        WHERE raw_json::text LIKE '%' || target_run_id || '%'
    ) THEN
        RAISE EXCEPTION 'rollback blocked: N5/action refs exist for %', target_run_id;
    END IF;
END $$;

DELETE FROM stock_action_confirmation_projection_metric
WHERE projection_run_id = 'realtime_action_confirmation_metric_20260630_until_1500__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1';

DELETE FROM index_action_confirmation_projection_metric
WHERE projection_run_id = 'realtime_action_confirmation_metric_20260630_until_1500__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1';

DELETE FROM board_action_confirmation_projection_metric
WHERE projection_run_id = 'realtime_action_confirmation_metric_20260630_until_1500__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1';

DELETE FROM common_market_data_quality_item
WHERE run_id = 'realtime_action_confirmation_metric_20260630_until_1500__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1';

DELETE FROM common_market_data_run
WHERE run_id = 'realtime_action_confirmation_metric_20260630_until_1500__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1';

COMMIT;
