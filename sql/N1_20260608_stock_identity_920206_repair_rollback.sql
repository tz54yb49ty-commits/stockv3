-- N1 stock_identity 920206.BJ 20260608 repair rollback draft.
-- Scope: stock_identity_refresh_20260608_920206_v1 / stock_identity_20260608_v1.
-- This rollback is intentionally hard-failed until an operator re-reviews
-- downstream refs and removes the first RAISE EXCEPTION in the correct
-- N1_ingestion rollback gate.
--
-- It must not touch official daily facts, condition source, N2/N3/N4/N5/N6,
-- outbox/inbox/checkpoint, Parquet, worker state, old system state, or trading.

BEGIN;

DO $$
BEGIN
  RAISE EXCEPTION 'Refusing N1 stock_identity 920206 20260608 rollback: manual N1_ingestion rollback gate required before DELETE/UPDATE';
END $$;

DO $$
DECLARE
  v_identity_key text := 'stock:BJ:920206';
  v_ts_code text := '920206.BJ';
  v_batch_id text := 'stock_identity_refresh_20260608_920206_v1';
  v_source_version text := 'stock_identity_20260608_v1';
  daily_ref_count integer;
  condition_ref_count integer;
  quality_ref_count integer;
  event_ref_count integer;
  downstream_ref_count integer;
BEGIN
  SELECT COUNT(*)
  INTO daily_ref_count
  FROM stock_daily_bar_fact
  WHERE stock_identity_key = v_identity_key;

  SELECT
    (SELECT COUNT(*) FROM stock_daily_basic WHERE stock_identity_key = v_identity_key)
    + (SELECT COUNT(*) FROM stock_financial_metrics_fact WHERE stock_identity_key = v_identity_key)
  INTO condition_ref_count;

  SELECT COUNT(*)
  INTO quality_ref_count
  FROM common_quality_gate_result
  WHERE source_batch_id <> v_batch_id
    AND (
      details::text LIKE '%' || v_identity_key || '%'
      OR details::text LIKE '%' || v_ts_code || '%'
    );

  SELECT
    (SELECT COUNT(*) FROM common_event_outbox WHERE source_run_id = v_batch_id OR payload_json::text LIKE '%' || v_identity_key || '%' OR payload_json::text LIKE '%' || v_ts_code || '%')
    + (SELECT COUNT(*) FROM common_event_inbox WHERE source_run_id = v_batch_id OR payload_json::text LIKE '%' || v_identity_key || '%' OR raw_json::text LIKE '%' || v_identity_key || '%' OR payload_json::text LIKE '%' || v_ts_code || '%' OR raw_json::text LIKE '%' || v_ts_code || '%')
    + (SELECT COUNT(*) FROM common_event_consumer_checkpoint WHERE checkpoint_payload::text LIKE '%' || v_identity_key || '%' OR checkpoint_payload::text LIKE '%' || v_ts_code || '%')
  INTO event_ref_count;

  SELECT
    (SELECT COUNT(*) FROM common_condition_run WHERE source_versions::text LIKE '%' || v_identity_key || '%' OR source_versions::text LIKE '%' || v_source_version || '%' OR input_ingest_batch_id = v_batch_id)
    + (SELECT COUNT(*) FROM common_market_data_run WHERE raw_json::text LIKE '%' || v_identity_key || '%' OR raw_json::text LIKE '%' || v_ts_code || '%' OR raw_json::text LIKE '%' || v_batch_id || '%')
    + (SELECT COUNT(*) FROM common_trigger_run WHERE raw_json::text LIKE '%' || v_identity_key || '%' OR raw_json::text LIKE '%' || v_ts_code || '%' OR raw_json::text LIKE '%' || v_batch_id || '%')
    + (SELECT COUNT(*) FROM common_action_run WHERE raw_json::text LIKE '%' || v_identity_key || '%' OR raw_json::text LIKE '%' || v_ts_code || '%' OR raw_json::text LIKE '%' || v_batch_id || '%')
    + (SELECT COUNT(*) FROM user_projection_run WHERE quality_summary_json::text LIKE '%' || v_identity_key || '%' OR source_action_run_id LIKE '%' || v_batch_id || '%')
  INTO downstream_ref_count;

  IF daily_ref_count > 0
     OR condition_ref_count > 0
     OR quality_ref_count > 0
     OR event_ref_count > 0
     OR downstream_ref_count > 0 THEN
    RAISE EXCEPTION
      'Refusing N1 stock_identity 920206 rollback: daily %, condition %, quality %, event %, downstream %',
      daily_ref_count, condition_ref_count, quality_ref_count, event_ref_count, downstream_ref_count;
  END IF;
END $$;

DELETE FROM common_active_source_version
WHERE data_domain = 'stock'
  AND data_type = 'stock_identity'
  AND scope_key = 'A_STOCK:20260608'
  AND source_batch_id = 'stock_identity_refresh_20260608_920206_v1'
  AND source_version = 'stock_identity_20260608_v1';

DELETE FROM stock_identity
WHERE stock_identity_key = 'stock:BJ:920206'
  AND ts_code = '920206.BJ'
  AND source_batch_id = 'stock_identity_refresh_20260608_920206_v1'
  AND source_version = 'stock_identity_20260608_v1';

DELETE FROM common_quality_gate_result
WHERE source_batch_id = 'stock_identity_refresh_20260608_920206_v1'
   OR source_version = 'stock_identity_20260608_v1';

DELETE FROM common_ingest_batch
WHERE batch_id = 'stock_identity_refresh_20260608_920206_v1'
   OR source_version = 'stock_identity_20260608_v1';

COMMIT;
