-- Rollback for N3 20260617 D-anchor previous-day same-window preload and additive control rows
-- Scope: preload_run_id=previous_day_same_window_preload_20260616_for_20260617__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
-- Source subscription run: market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
-- Generated: 2026-06-18T11:46:38.418560+00:00

BEGIN;

DO $$
DECLARE
  v_preload_run_id text := 'previous_day_same_window_preload_20260616_for_20260617__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
  v_subscription_run_id text := 'market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
  v_count bigint;
BEGIN
  SELECT count(*) INTO v_count FROM common_event_outbox WHERE source_run_id IN (v_preload_run_id, v_subscription_run_id);
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: common_event_outbox refs exist: %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_event_inbox WHERE source_run_id IN (v_preload_run_id, v_subscription_run_id);
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: common_event_inbox refs exist: %', v_count;
  END IF;

  IF to_regclass('public.common_event_ledger') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM common_event_ledger WHERE source_run_id IN (v_preload_run_id, v_subscription_run_id);
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'rollback blocked: common_event_ledger refs exist: %', v_count;
    END IF;
  END IF;

  SELECT count(*) INTO v_count FROM stock_action_confirmation_projection_metric WHERE source_previous_day_minute_run_id = v_preload_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: stock B2 refs exist: %', v_count; END IF;
  SELECT count(*) INTO v_count FROM index_action_confirmation_projection_metric WHERE source_previous_day_minute_run_id = v_preload_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: index B2 refs exist: %', v_count; END IF;
  SELECT count(*) INTO v_count FROM board_action_confirmation_projection_metric WHERE source_previous_day_minute_run_id = v_preload_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: board B2 refs exist: %', v_count; END IF;
END $$;

DELETE FROM stock_minute_bar_1m WHERE run_id = 'previous_day_same_window_preload_20260616_for_20260617__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM index_minute_bar_1m WHERE run_id = 'previous_day_same_window_preload_20260616_for_20260617__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM board_minute_bar_1m WHERE run_id = 'previous_day_same_window_preload_20260616_for_20260617__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM stock_previous_day_minute_preload_status WHERE run_id = 'previous_day_same_window_preload_20260616_for_20260617__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM index_previous_day_minute_preload_status WHERE run_id = 'previous_day_same_window_preload_20260616_for_20260617__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM board_previous_day_minute_preload_status WHERE run_id = 'previous_day_same_window_preload_20260616_for_20260617__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM common_market_data_quality_item WHERE run_id = 'previous_day_same_window_preload_20260616_for_20260617__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';
DELETE FROM common_market_data_run WHERE run_id = 'previous_day_same_window_preload_20260616_for_20260617__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1';

DELETE FROM common_market_data_subscription
WHERE run_id = 'market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1'
  AND required_data_kind = 'previous_day_minute_bar_1m'
  AND raw_json ->> 'd_anchor_same_window_control_expansion' = 'true';

DELETE FROM common_market_data_subscription_candidate
WHERE run_id = 'market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1'
  AND required_data_kind = 'previous_day_minute_bar_1m'
  AND raw_json ->> 'd_anchor_same_window_control_expansion' = 'true';

COMMIT;
