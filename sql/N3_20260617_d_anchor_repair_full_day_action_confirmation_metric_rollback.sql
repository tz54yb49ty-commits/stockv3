-- Rollback for N3_20260617_D_ANCHOR_REPAIR_FULL_DAY_ACTION_CONFIRMATION_METRIC_EXECUTE_AFTER_SUBSCRIPTION_C1_PASS
-- Scope: planned_metric_run_id=action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
-- Generated: 2026-06-18T08:59:17.516268+00:00
-- Deletes only B2 metric rows, B2 quality rows, and the B2 common_market_data_run row.
-- Hard-blocks if outbox/inbox/checkpoint or downstream refs exist.

BEGIN;

DO $$
DECLARE
  v_metric_run_id text := 'action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
  v_count bigint;
BEGIN
  SELECT count(*) INTO v_count FROM common_event_outbox WHERE source_run_id = v_metric_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: common_event_outbox refs exist for %: %', v_metric_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_event_inbox WHERE source_run_id = v_metric_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: common_event_inbox refs exist for %: %', v_metric_run_id, v_count;
  END IF;

  IF to_regclass('public.common_event_consumer_checkpoint') IS NOT NULL THEN
    IF EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema='public' AND table_name='common_event_consumer_checkpoint' AND column_name='checkpoint_payload'
    ) THEN
      SELECT count(*) INTO v_count
      FROM common_event_consumer_checkpoint
      WHERE COALESCE(checkpoint_payload::text, '') LIKE '%' || v_metric_run_id || '%';
      IF v_count <> 0 THEN
        RAISE EXCEPTION 'rollback blocked: common_event_consumer_checkpoint refs exist for %: %', v_metric_run_id, v_count;
      END IF;
    END IF;
  END IF;

  IF EXISTS (
    SELECT 1 FROM common_market_data_run
    WHERE run_id = v_metric_run_id
      AND (downstream_layers_touched OR worker_started)
  ) THEN
    RAISE EXCEPTION 'rollback blocked: downstream_layers_touched/worker_started true for %', v_metric_run_id;
  END IF;
END $$;

DELETE FROM stock_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM index_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM board_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM common_market_data_quality_item WHERE run_id = 'action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM common_market_data_run WHERE run_id = 'action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';

COMMIT;
