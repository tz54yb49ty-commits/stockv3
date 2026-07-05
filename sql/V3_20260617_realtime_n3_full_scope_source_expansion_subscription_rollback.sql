-- V3 20260617 N3 full-scope source expansion subscription rollback.
-- Scope: market_data_subscription_20260617_full_scope_source_expansion__condition_layer_20260616_source_20260616_for_20260617_v1
-- Deletes only additive N3 subscription control rows. Hard-fails if facts/events/downstream refs exist.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'market_data_subscription_20260617_full_scope_source_expansion__condition_layer_20260616_source_20260616_for_20260617_v1';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count FROM common_event_outbox WHERE source_run_id = v_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: outbox has % refs for %', v_count, v_run_id; END IF;
  SELECT count(*) INTO v_count FROM common_event_inbox WHERE source_run_id = v_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: inbox has % refs for %', v_count, v_run_id; END IF;
  SELECT count(*) INTO v_count FROM common_market_data_run
   WHERE run_id = v_run_id AND (COALESCE(market_data_pulled,false) OR COALESCE(market_data_fact_written,false) OR COALESCE(downstream_layers_touched,false) OR COALESCE(worker_started,false));
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: run flags indicate fact/downstream use for %', v_run_id; END IF;
END $$;

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
