-- Rollback draft for future stock_financial canonical metrics 20260529 v2 execute.
-- Do not run unless stock_financial_20260529_v2 has been committed.
-- Scope: only stock_financial_canonical_20260529_v1 / stock_financial_20260529_v2.

BEGIN;

DELETE FROM stock_financial_metrics_fact
WHERE source_trade_date = '20260529'
  AND source_batch_id = 'stock_financial_canonical_20260529_v1'
  AND source_version = 'stock_financial_20260529_v2';

DELETE FROM common_quality_gate_result
WHERE source_batch_id = 'stock_financial_canonical_20260529_v1'
  AND source_version = 'stock_financial_20260529_v2';

UPDATE common_active_source_version
SET source_version = 'stock_financial_20260529_v1',
    previous_source_version = NULL,
    source_batch_id = 'condition_source_activation_20260529_v1',
    activated_by = 'rollback.stock_financial_canonical_20260529_v2'
WHERE data_domain = 'stock'
  AND data_type = 'stock_financial'
  AND scope_key = '20260529'
  AND source_version = 'stock_financial_20260529_v2'
  AND source_batch_id = 'stock_financial_canonical_20260529_v1';

DELETE FROM common_ingest_batch
WHERE batch_id = 'stock_financial_canonical_20260529_v1'
  AND source_version = 'stock_financial_20260529_v2'
  AND data_domain = 'stock'
  AND data_type = 'stock_financial_canonical_metrics';

COMMIT;
