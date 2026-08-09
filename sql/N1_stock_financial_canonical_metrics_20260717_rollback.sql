-- Rollback for stock_financial canonical metrics 20260717 v2 execute.
-- Generated and verified after database commit. Execute only under a separate
-- authorized rollback gate after every downstream reference is zero.
-- Scope: only stock_financial_canonical_20260717_v1 / stock_financial_20260717_v2.

BEGIN;

DO $rollback$
DECLARE
  v_trade_date text := '20260717';
  v_target_batch_id text := 'stock_financial_canonical_20260717_v1';
  v_target_source_version text := 'stock_financial_20260717_v2';
  v_previous_batch_id text := 'condition_source_activation_20260717_v1';
  v_previous_source_version text := 'stock_financial_20260717_v1';
  v_expected_row_count bigint := 5507;
  v_active_count bigint;
  v_target_row_count bigint;
  v_target_identity_count bigint;
  v_previous_row_count bigint;
  v_previous_identity_count bigint;
  v_quality_row_count bigint;
  v_batch_count bigint;
  v_outbox_refs bigint;
  v_inbox_refs bigint;
  v_checkpoint_refs bigint;
  v_n2_refs bigint;
  v_n3_refs bigint;
  v_n4_refs bigint;
  v_n5_refs bigint;
  v_n6_refs bigint;
  v_affected_count bigint;
BEGIN
  SELECT count(*) INTO v_active_count
  FROM common_active_source_version
  WHERE data_domain = 'stock'
    AND data_type = 'stock_financial'
    AND scope_key = v_trade_date
    AND source_version = v_target_source_version
    AND previous_source_version = v_previous_source_version
    AND source_batch_id = v_target_batch_id;

  SELECT count(*), count(DISTINCT stock_identity_key)
  INTO v_target_row_count, v_target_identity_count
  FROM stock_financial_metrics_fact
  WHERE source_trade_date = v_trade_date
    AND source_batch_id = v_target_batch_id
    AND source_version = v_target_source_version;

  SELECT count(*), count(DISTINCT stock_identity_key)
  INTO v_previous_row_count, v_previous_identity_count
  FROM stock_financial_metrics_fact
  WHERE source_trade_date = v_trade_date
    AND source_batch_id = v_previous_batch_id
    AND source_version = v_previous_source_version;

  SELECT count(*) INTO v_quality_row_count
  FROM common_quality_gate_result
  WHERE source_batch_id = v_target_batch_id
    AND source_version = v_target_source_version
    AND data_domain = 'stock'
    AND data_type = 'stock_financial_canonical_metrics';

  SELECT count(*) INTO v_batch_count
  FROM common_ingest_batch
  WHERE batch_id = v_target_batch_id
    AND trade_date = v_trade_date
    AND source_version = v_target_source_version
    AND data_domain = 'stock'
    AND data_type = 'stock_financial_canonical_metrics'
    AND status = 'passed'
    AND row_count = v_expected_row_count;

  IF v_active_count <> 1
     OR v_target_row_count <> v_expected_row_count
     OR v_target_identity_count <> v_expected_row_count
     OR v_previous_row_count <> v_expected_row_count
     OR v_previous_identity_count <> v_expected_row_count
     OR v_quality_row_count <> 9
     OR v_batch_count <> 1 THEN
    RAISE EXCEPTION
      'Refusing stock_financial 20260717 rollback: active %, target rows %, target identities %, previous rows %, previous identities %, quality %, batch %',
      v_active_count, v_target_row_count, v_target_identity_count,
      v_previous_row_count, v_previous_identity_count, v_quality_row_count, v_batch_count;
  END IF;

  SELECT count(*) INTO v_outbox_refs
  FROM common_event_outbox
  WHERE source_run_id IN (v_target_batch_id, v_target_source_version)
     OR payload_json::text LIKE '%' || v_target_batch_id || '%'
     OR payload_json::text LIKE '%' || v_target_source_version || '%';

  SELECT count(*) INTO v_inbox_refs
  FROM common_event_inbox
  WHERE source_run_id IN (v_target_batch_id, v_target_source_version)
     OR payload_json::text LIKE '%' || v_target_batch_id || '%'
     OR raw_json::text LIKE '%' || v_target_batch_id || '%'
     OR payload_json::text LIKE '%' || v_target_source_version || '%'
     OR raw_json::text LIKE '%' || v_target_source_version || '%';

  SELECT count(*) INTO v_checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%' || v_target_batch_id || '%'
     OR checkpoint_payload::text LIKE '%' || v_target_source_version || '%';

  SELECT count(*) INTO v_n2_refs
  FROM common_condition_run
  WHERE input_ingest_batch_id = v_target_batch_id
     OR source_versions::text LIKE '%' || v_target_batch_id || '%'
     OR source_versions::text LIKE '%' || v_target_source_version || '%';

  SELECT count(*) INTO v_n3_refs
  FROM common_market_data_run
  WHERE raw_json::text LIKE '%' || v_target_batch_id || '%'
     OR raw_json::text LIKE '%' || v_target_source_version || '%';

  SELECT count(*) INTO v_n4_refs
  FROM common_trigger_run
  WHERE raw_json::text LIKE '%' || v_target_batch_id || '%'
     OR raw_json::text LIKE '%' || v_target_source_version || '%';

  SELECT count(*) INTO v_n5_refs
  FROM common_action_run
  WHERE raw_json::text LIKE '%' || v_target_batch_id || '%'
     OR raw_json::text LIKE '%' || v_target_source_version || '%';

  SELECT count(*) INTO v_n6_refs
  FROM user_projection_run
  WHERE source_action_run_id LIKE '%' || v_target_batch_id || '%'
     OR source_action_run_id LIKE '%' || v_target_source_version || '%'
     OR quality_summary_json::text LIKE '%' || v_target_batch_id || '%'
     OR quality_summary_json::text LIKE '%' || v_target_source_version || '%';

  IF v_outbox_refs <> 0
     OR v_inbox_refs <> 0
     OR v_checkpoint_refs <> 0
     OR v_n2_refs <> 0
     OR v_n3_refs <> 0
     OR v_n4_refs <> 0
     OR v_n5_refs <> 0
     OR v_n6_refs <> 0 THEN
    RAISE EXCEPTION
      'Refusing stock_financial 20260717 rollback: outbox %, inbox %, checkpoint %, N2 %, N3 %, N4 %, N5 %, N6 %',
      v_outbox_refs, v_inbox_refs, v_checkpoint_refs,
      v_n2_refs, v_n3_refs, v_n4_refs, v_n5_refs, v_n6_refs;
  END IF;

  DELETE FROM stock_financial_metrics_fact
  WHERE source_trade_date = v_trade_date
    AND source_batch_id = v_target_batch_id
    AND source_version = v_target_source_version;
  GET DIAGNOSTICS v_affected_count = ROW_COUNT;
  IF v_affected_count <> v_expected_row_count THEN
    RAISE EXCEPTION 'Rollback fact delete count mismatch: %', v_affected_count;
  END IF;

  DELETE FROM common_quality_gate_result
  WHERE source_batch_id = v_target_batch_id
    AND source_version = v_target_source_version
    AND data_domain = 'stock'
    AND data_type = 'stock_financial_canonical_metrics';
  GET DIAGNOSTICS v_affected_count = ROW_COUNT;
  IF v_affected_count <> 9 THEN
    RAISE EXCEPTION 'Rollback quality delete count mismatch: %', v_affected_count;
  END IF;

  UPDATE common_active_source_version
  SET source_version = v_previous_source_version,
      previous_source_version = NULL,
      source_batch_id = v_previous_batch_id,
      activated_at = now(),
      activated_by = 'rollback.stock_financial_canonical_20260717_v2'
  WHERE data_domain = 'stock'
    AND data_type = 'stock_financial'
    AND scope_key = v_trade_date
    AND source_version = v_target_source_version
    AND previous_source_version = v_previous_source_version
    AND source_batch_id = v_target_batch_id;
  GET DIAGNOSTICS v_affected_count = ROW_COUNT;
  IF v_affected_count <> 1 THEN
    RAISE EXCEPTION 'Rollback active update count mismatch: %', v_affected_count;
  END IF;

  DELETE FROM common_ingest_batch
  WHERE batch_id = v_target_batch_id
    AND trade_date = v_trade_date
    AND source_version = v_target_source_version
    AND data_domain = 'stock'
    AND data_type = 'stock_financial_canonical_metrics'
    AND status = 'passed'
    AND row_count = v_expected_row_count;
  GET DIAGNOSTICS v_affected_count = ROW_COUNT;
  IF v_affected_count <> 1 THEN
    RAISE EXCEPTION 'Rollback batch delete count mismatch: %', v_affected_count;
  END IF;

  SELECT count(*) INTO v_target_row_count
  FROM stock_financial_metrics_fact
  WHERE source_trade_date = v_trade_date
    AND source_batch_id = v_target_batch_id
    AND source_version = v_target_source_version;

  SELECT count(*) INTO v_quality_row_count
  FROM common_quality_gate_result
  WHERE source_batch_id = v_target_batch_id
    AND source_version = v_target_source_version
    AND data_domain = 'stock'
    AND data_type = 'stock_financial_canonical_metrics';

  SELECT count(*) INTO v_batch_count
  FROM common_ingest_batch
  WHERE batch_id = v_target_batch_id
    AND source_version = v_target_source_version;

  SELECT count(*) INTO v_active_count
  FROM common_active_source_version
  WHERE data_domain = 'stock'
    AND data_type = 'stock_financial'
    AND scope_key = v_trade_date
    AND source_version = v_previous_source_version
    AND previous_source_version IS NULL
    AND source_batch_id = v_previous_batch_id
    AND activated_by = 'rollback.stock_financial_canonical_20260717_v2';

  IF v_target_row_count <> 0
     OR v_quality_row_count <> 0
     OR v_batch_count <> 0
     OR v_active_count <> 1 THEN
    RAISE EXCEPTION
      'Rollback postflight mismatch: target %, quality %, batch %, active %',
      v_target_row_count, v_quality_row_count, v_batch_count, v_active_count;
  END IF;
END
$rollback$;

COMMIT;
