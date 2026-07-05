-- V3 20260617 N3 repaired-N2 source-expansion subscription rollback
-- Scope: only source-expansion control rows for market_data_subscription_20260617_full_scope_source_expansion__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1.
-- Hard guard: abort if event infra references this run id.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'market_data_subscription_20260617_full_scope_source_expansion__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
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

DELETE FROM common_market_data_pull_plan WHERE run_id = 'market_data_subscription_20260617_full_scope_source_expansion__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM common_market_data_subscription WHERE run_id = 'market_data_subscription_20260617_full_scope_source_expansion__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM common_market_data_subscription_candidate WHERE run_id = 'market_data_subscription_20260617_full_scope_source_expansion__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM common_market_data_quality_item WHERE run_id = 'market_data_subscription_20260617_full_scope_source_expansion__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
DELETE FROM common_market_data_run WHERE run_id = 'market_data_subscription_20260617_full_scope_source_expansion__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';

COMMIT;
