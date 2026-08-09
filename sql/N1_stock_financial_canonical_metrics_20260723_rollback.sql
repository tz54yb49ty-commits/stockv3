-- Rollback for stock_financial canonical metrics 20260723 v2 execute.
-- Generated and verified before database commit. Execute only under a separate authorized rollback gate.
-- Scope: only stock_financial_canonical_20260723_v1 / stock_financial_20260723_v2.

BEGIN;

DO $$
DECLARE
  v_active_count bigint;
  v_target_row_count bigint;
  v_target_identity_count bigint;
  v_previous_row_count bigint;
  v_previous_identity_count bigint;
  v_quality_row_count bigint;
  v_batch_count bigint;
  v_affected_count bigint;
BEGIN
  SELECT count(*) INTO v_active_count
  FROM common_active_source_version
  WHERE data_domain = 'stock'
    AND data_type = 'stock_financial'
    AND scope_key = '20260723'
    AND source_version = 'stock_financial_20260723_v2'
    AND source_batch_id = 'stock_financial_canonical_20260723_v1';

  SELECT count(*), count(DISTINCT stock_identity_key)
  INTO v_target_row_count, v_target_identity_count
  FROM stock_financial_metrics_fact
  WHERE source_trade_date = '20260723'
    AND source_batch_id = 'stock_financial_canonical_20260723_v1'
    AND source_version = 'stock_financial_20260723_v2';

  SELECT count(*), count(DISTINCT stock_identity_key)
  INTO v_previous_row_count, v_previous_identity_count
  FROM stock_financial_metrics_fact
  WHERE source_trade_date = '20260723'
    AND source_batch_id = 'condition_source_activation_20260723_v1'
    AND source_version = 'stock_financial_20260723_v1';

  SELECT count(*) INTO v_quality_row_count
  FROM common_quality_gate_result
  WHERE source_batch_id = 'stock_financial_canonical_20260723_v1'
    AND source_version = 'stock_financial_20260723_v2'
    AND data_domain = 'stock'
    AND data_type = 'stock_financial_canonical_metrics';

  SELECT count(*) INTO v_batch_count
  FROM common_ingest_batch
  WHERE batch_id = 'stock_financial_canonical_20260723_v1'
    AND trade_date = '20260723'
    AND source_version = 'stock_financial_20260723_v2'
    AND data_domain = 'stock'
    AND data_type = 'stock_financial_canonical_metrics'
    AND status = 'passed'
    AND row_count = 5509;

  IF v_active_count <> 1
     OR v_target_row_count <> 5509
     OR v_target_identity_count <> 5509
     OR v_previous_row_count <> 5509
     OR v_previous_identity_count <> 5509
     OR v_quality_row_count <> 9
     OR v_batch_count <> 1 THEN
    RAISE EXCEPTION
      'Refusing stock_financial canonical rollback: active %, target rows %, target identities %, previous rows %, previous identities %, quality %, batch %',
      v_active_count, v_target_row_count, v_target_identity_count,
      v_previous_row_count, v_previous_identity_count, v_quality_row_count, v_batch_count;
  END IF;

  DELETE FROM stock_financial_metrics_fact
  WHERE source_trade_date = '20260723'
    AND source_batch_id = 'stock_financial_canonical_20260723_v1'
    AND source_version = 'stock_financial_20260723_v2';
  GET DIAGNOSTICS v_affected_count = ROW_COUNT;
  IF v_affected_count <> 5509 THEN
    RAISE EXCEPTION 'Rollback fact delete count mismatch: %', v_affected_count;
  END IF;

  DELETE FROM common_quality_gate_result
  WHERE source_batch_id = 'stock_financial_canonical_20260723_v1'
    AND source_version = 'stock_financial_20260723_v2'
    AND data_domain = 'stock'
    AND data_type = 'stock_financial_canonical_metrics';
  GET DIAGNOSTICS v_affected_count = ROW_COUNT;
  IF v_affected_count <> 9 THEN
    RAISE EXCEPTION 'Rollback quality delete count mismatch: %', v_affected_count;
  END IF;

  UPDATE common_active_source_version
  SET source_version = 'stock_financial_20260723_v1',
      previous_source_version = NULL,
      source_batch_id = 'condition_source_activation_20260723_v1',
      activated_at = now(),
      activated_by = 'rollback.stock_financial_20260723_v2'
  WHERE data_domain = 'stock'
    AND data_type = 'stock_financial'
    AND scope_key = '20260723'
    AND source_version = 'stock_financial_20260723_v2'
    AND source_batch_id = 'stock_financial_canonical_20260723_v1';
  GET DIAGNOSTICS v_affected_count = ROW_COUNT;
  IF v_affected_count <> 1 THEN
    RAISE EXCEPTION 'Rollback active update count mismatch: %', v_affected_count;
  END IF;

  DELETE FROM common_ingest_batch
  WHERE batch_id = 'stock_financial_canonical_20260723_v1'
    AND trade_date = '20260723'
    AND source_version = 'stock_financial_20260723_v2'
    AND data_domain = 'stock'
    AND data_type = 'stock_financial_canonical_metrics'
    AND status = 'passed'
    AND row_count = 5509;
  GET DIAGNOSTICS v_affected_count = ROW_COUNT;
  IF v_affected_count <> 1 THEN
    RAISE EXCEPTION 'Rollback batch delete count mismatch: %', v_affected_count;
  END IF;
END $$;

COMMIT;
