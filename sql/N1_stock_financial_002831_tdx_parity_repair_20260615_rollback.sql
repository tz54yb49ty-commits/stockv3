-- Rollback draft for future N1 stock_financial 002831 TDX parity repair.
-- Scope: source_trade_date=20260615, source_batch_id=stock_financial_002831_tdx_parity_repair_20260615_v1,
-- source_version=stock_financial_20260615_v3.
-- This rollback intentionally hard-fails before any destructive statement.
-- Remove the guard only inside a reviewed rollback gate.

DO $$
BEGIN
  RAISE EXCEPTION 'manual rollback guard: review downstream refs and remove this guard before rolling back stock_financial_20260615_v3';
END $$;

DO $$
DECLARE
  ref record;
  scoped_count bigint;
  total_ref_count bigint := 0;
BEGIN
  FOR ref IN
    SELECT table_name, column_name
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name ~ '^(common_condition|stock_condition|index_condition|board_condition|common_market|stock_realtime|index_realtime|board_realtime|common_trigger|stock_trigger|index_trigger|board_trigger|common_action|stock_action|index_action|board_action|user_|n6_|common_event_outbox|common_event_inbox|common_event_consumer_checkpoint)'
      AND data_type IN ('text', 'json', 'jsonb', 'character varying')
  LOOP
    EXECUTE format(
      'SELECT count(*) FROM %I WHERE %I::text LIKE %L',
      ref.table_name,
      ref.column_name,
      '%stock_financial_20260615_v3%'
    )
    INTO scoped_count;
    total_ref_count := total_ref_count + scoped_count;
  END LOOP;

  IF total_ref_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: downstream or boundary refs to stock_financial_20260615_v3 exist: %', total_ref_count;
  END IF;
END $$;

BEGIN;

DELETE FROM stock_financial_metrics_fact
WHERE source_trade_date = '20260615'
  AND source_batch_id = 'stock_financial_002831_tdx_parity_repair_20260615_v1'
  AND source_version = 'stock_financial_20260615_v3';

DELETE FROM common_quality_gate_result
WHERE source_batch_id = 'stock_financial_002831_tdx_parity_repair_20260615_v1'
  AND source_version = 'stock_financial_20260615_v3'
  AND data_domain = 'stock'
  AND data_type = 'stock_financial_canonical_metrics';

UPDATE common_active_source_version
SET source_version = 'stock_financial_20260615_v2',
    source_batch_id = 'stock_financial_canonical_20260615_v1',
    previous_source_version = 'stock_financial_20260615_v1',
    activated_by = 'rollback.stock_financial_002831_tdx_parity_repair_20260615_v3'
WHERE data_domain = 'stock'
  AND data_type = 'stock_financial'
  AND scope_key = '20260615'
  AND source_version = 'stock_financial_20260615_v3'
  AND source_batch_id = 'stock_financial_002831_tdx_parity_repair_20260615_v1';

DELETE FROM common_ingest_batch
WHERE batch_id = 'stock_financial_002831_tdx_parity_repair_20260615_v1'
  AND trade_date = '20260615'
  AND data_domain = 'stock'
  AND data_type = 'stock_financial_canonical_metrics'
  AND source_version = 'stock_financial_20260615_v3';

COMMIT;
