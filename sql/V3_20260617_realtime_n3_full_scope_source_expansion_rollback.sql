-- V3 20260617 N3 full-scope source expansion rollback.
-- Scope: historical_closed_minute_source_expansion_20260617_until_1352_full_scope_missing__condition_layer_20260616_source_20260616_for_20260617_v1
-- Deletes only this N3 source expansion run's minute facts/run/quality after hard safety checks.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'historical_closed_minute_source_expansion_20260617_until_1352_full_scope_missing__condition_layer_20260616_source_20260616_for_20260617_v1';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count FROM common_event_outbox WHERE source_run_id = v_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: outbox has % refs for %', v_count, v_run_id; END IF;
  SELECT count(*) INTO v_count FROM common_event_inbox WHERE source_run_id = v_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: inbox has % refs for %', v_count, v_run_id; END IF;
  SELECT count(*) INTO v_count FROM common_event_consumer_checkpoint WHERE checkpoint_payload::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: checkpoint has % refs for %', v_count, v_run_id; END IF;
  SELECT count(*) INTO v_count FROM common_trigger_run WHERE run_id = v_run_id OR raw_json::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: trigger refs exist for %', v_run_id; END IF;
  SELECT count(*) INTO v_count FROM common_action_run WHERE run_id = v_run_id OR raw_json::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: action refs exist for %', v_run_id; END IF;
END $$;

DELETE FROM stock_minute_bar_1m WHERE run_id = 'historical_closed_minute_source_expansion_20260617_until_1352_full_scope_missing__condition_layer_20260616_source_20260616_for_20260617_v1';
DELETE FROM index_minute_bar_1m WHERE run_id = 'historical_closed_minute_source_expansion_20260617_until_1352_full_scope_missing__condition_layer_20260616_source_20260616_for_20260617_v1';
DELETE FROM board_minute_bar_1m WHERE run_id = 'historical_closed_minute_source_expansion_20260617_until_1352_full_scope_missing__condition_layer_20260616_source_20260616_for_20260617_v1';
DELETE FROM common_market_data_quality_item WHERE run_id = 'historical_closed_minute_source_expansion_20260617_until_1352_full_scope_missing__condition_layer_20260616_source_20260616_for_20260617_v1';
DELETE FROM common_market_data_run WHERE run_id = 'historical_closed_minute_source_expansion_20260617_until_1352_full_scope_missing__condition_layer_20260616_source_20260616_for_20260617_v1' AND COALESCE(downstream_layers_touched,false)=false AND COALESCE(worker_started,false)=false;

COMMIT;
