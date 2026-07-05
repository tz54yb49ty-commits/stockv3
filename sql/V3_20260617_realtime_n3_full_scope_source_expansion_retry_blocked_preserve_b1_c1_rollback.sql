-- V3 20260617 N3 source-expansion retry blocked rollback.
-- Scope: preserve passed B1/C1; remove only source-expansion control rows and no-op target rows if operator chooses cleanup.
-- B1 preserved: realtime_daily_snapshot_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_v1
-- C1 preserved: today_minute_bar_1m_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_v1

BEGIN;

DO $$
DECLARE
  v_count BIGINT;
  v_run_ids TEXT[] := ARRAY['market_data_subscription_20260617_full_scope_source_expansion__condition_layer_20260616_source_20260616_for_20260617_v1','historical_closed_minute_source_expansion_20260617_until_1352_full_scope_missing__condition_layer_20260616_source_20260616_for_20260617_v1','action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_v1'];
  v_run_id TEXT;
BEGIN
  FOREACH v_run_id IN ARRAY v_run_ids LOOP
    SELECT count(*) INTO v_count FROM common_event_outbox WHERE source_run_id = v_run_id;
    IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: outbox has % refs for %', v_count, v_run_id; END IF;
    SELECT count(*) INTO v_count FROM common_event_inbox WHERE source_run_id = v_run_id;
    IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: inbox has % refs for %', v_count, v_run_id; END IF;
    SELECT count(*) INTO v_count FROM common_event_consumer_checkpoint WHERE checkpoint_payload::text LIKE '%' || v_run_id || '%';
    IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: checkpoint has % refs for %', v_count, v_run_id; END IF;
    SELECT count(*) INTO v_count FROM common_market_data_run WHERE run_id = v_run_id AND (COALESCE(downstream_layers_touched,false) OR COALESCE(worker_started,false));
    IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: downstream/worker flags set for %', v_run_id; END IF;
  END LOOP;
END $$;

-- B2 metric was not executed; these are no-op scoped guards.
DELETE FROM stock_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_v1';
DELETE FROM index_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_v1';
DELETE FROM board_action_confirmation_projection_metric WHERE projection_run_id = 'action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_v1';
DELETE FROM common_market_data_quality_item WHERE run_id = 'action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_v1';
DELETE FROM common_market_data_run WHERE run_id = 'action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_v1';

-- Source-expansion facts were not written because retry blocked before DB write; no-op scoped guards.
DELETE FROM stock_minute_bar_1m WHERE run_id = 'historical_closed_minute_source_expansion_20260617_until_1352_full_scope_missing__condition_layer_20260616_source_20260616_for_20260617_v1';
DELETE FROM index_minute_bar_1m WHERE run_id = 'historical_closed_minute_source_expansion_20260617_until_1352_full_scope_missing__condition_layer_20260616_source_20260616_for_20260617_v1';
DELETE FROM board_minute_bar_1m WHERE run_id = 'historical_closed_minute_source_expansion_20260617_until_1352_full_scope_missing__condition_layer_20260616_source_20260616_for_20260617_v1';
DELETE FROM common_market_data_quality_item WHERE run_id = 'historical_closed_minute_source_expansion_20260617_until_1352_full_scope_missing__condition_layer_20260616_source_20260616_for_20260617_v1';
DELETE FROM common_market_data_run WHERE run_id = 'historical_closed_minute_source_expansion_20260617_until_1352_full_scope_missing__condition_layer_20260616_source_20260616_for_20260617_v1';

-- Optional cleanup of additive source-expansion subscription control rows only.
DELETE FROM common_market_data_pull_plan WHERE run_id = 'market_data_subscription_20260617_full_scope_source_expansion__condition_layer_20260616_source_20260616_for_20260617_v1';
DELETE FROM common_market_data_subscription WHERE run_id = 'market_data_subscription_20260617_full_scope_source_expansion__condition_layer_20260616_source_20260616_for_20260617_v1';
DELETE FROM common_market_data_subscription_candidate WHERE run_id = 'market_data_subscription_20260617_full_scope_source_expansion__condition_layer_20260616_source_20260616_for_20260617_v1';
DELETE FROM common_market_data_quality_item WHERE run_id = 'market_data_subscription_20260617_full_scope_source_expansion__condition_layer_20260616_source_20260616_for_20260617_v1';
DELETE FROM common_market_data_run
WHERE run_id = 'market_data_subscription_20260617_full_scope_source_expansion__condition_layer_20260616_source_20260616_for_20260617_v1'
  AND COALESCE(market_data_pulled,false)=false
  AND COALESCE(market_data_fact_written,false)=false
  AND COALESCE(downstream_layers_touched,false)=false
  AND COALESCE(worker_started,false)=false;

COMMIT;
