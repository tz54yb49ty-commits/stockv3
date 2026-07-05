-- Rollback for N3_20260617_D_ANCHOR_REPAIR_SUBSCRIPTION_AND_FULL_DAY_C1_EXECUTE_FINAL_GATE_REVIEW
-- Scope: D-anchor N3 subscription/control rows and full-day C1 minute facts only.
-- Generated: 2026-06-18T08:42:51.035477+00:00
-- Does not delete or execute B2 metric rows; it hard-blocks if B2/downstream refs exist.

BEGIN;

DO $$
DECLARE
  v_subscription_run_id text := 'market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
  v_today_minute_run_id text := 'today_minute_bar_1m_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
  v_metric_run_id text := 'action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
  v_count bigint;
BEGIN
  SELECT count(*) INTO v_count FROM common_market_data_run WHERE run_id = v_metric_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: planned B2 metric run exists: % rows', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM stock_action_confirmation_projection_metric WHERE projection_run_id = v_metric_run_id;
  SELECT v_count + (SELECT count(*) FROM index_action_confirmation_projection_metric WHERE projection_run_id = v_metric_run_id)
                 + (SELECT count(*) FROM board_action_confirmation_projection_metric WHERE projection_run_id = v_metric_run_id)
    INTO v_count;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: planned B2 metric facts exist: % rows', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id IN (v_subscription_run_id, v_today_minute_run_id, v_metric_run_id);
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: common_event_outbox refs exist: % rows', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id IN (v_subscription_run_id, v_today_minute_run_id, v_metric_run_id);
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: common_event_inbox refs exist: % rows', v_count;
  END IF;

  IF to_regclass('public.common_event_consumer_checkpoint') IS NOT NULL THEN
    IF EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'common_event_consumer_checkpoint'
        AND column_name = 'checkpoint_payload'
    ) THEN
      SELECT count(*) INTO v_count
      FROM common_event_consumer_checkpoint
      WHERE COALESCE(checkpoint_payload::text, '') LIKE '%' || v_subscription_run_id || '%'
         OR COALESCE(checkpoint_payload::text, '') LIKE '%' || v_today_minute_run_id || '%'
         OR COALESCE(checkpoint_payload::text, '') LIKE '%' || v_metric_run_id || '%';
      IF v_count <> 0 THEN
        RAISE EXCEPTION 'rollback blocked: common_event_consumer_checkpoint refs exist: % rows', v_count;
      END IF;
    END IF;
  END IF;
END $$;

DELETE FROM stock_minute_bar_1m WHERE run_id = 'today_minute_bar_1m_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1' AND is_previous_day_preload = false;
DELETE FROM index_minute_bar_1m WHERE run_id = 'today_minute_bar_1m_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1' AND is_previous_day_preload = false;
DELETE FROM board_minute_bar_1m WHERE run_id = 'today_minute_bar_1m_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1' AND is_previous_day_preload = false;
DELETE FROM common_market_data_quality_item WHERE run_id = 'today_minute_bar_1m_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM common_market_data_run WHERE run_id = 'today_minute_bar_1m_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';

DELETE FROM common_market_data_pull_plan WHERE run_id = 'market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM common_market_data_subscription WHERE run_id = 'market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM common_market_data_subscription_candidate WHERE run_id = 'market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM common_market_data_quality_item WHERE run_id = 'market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM common_market_data_run WHERE run_id = 'market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';

COMMIT;
