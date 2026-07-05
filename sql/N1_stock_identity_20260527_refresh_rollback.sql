-- N1 stock_identity 20260527 refresh rollback draft.
-- Scope: stock_identity_refresh_20260527_v1 / stock_identity_20260527_v1.
-- This rollback only removes the two new 20260527 identity rows and this batch/quality/active metadata.
-- It does not touch historical identity rows, stock:SZ:300114, daily facts, condition source,
-- N2/N3/N4/N5/N6, outbox/inbox/checkpoint, Parquet, worker, old system, or trading state.

BEGIN;

DELETE FROM common_active_source_version
WHERE data_domain = 'stock'
  AND data_type = 'stock_identity'
  AND scope_key = 'A_STOCK:20260527'
  AND source_batch_id = 'stock_identity_refresh_20260527_v1'
  AND source_version = 'stock_identity_20260527_v1';

DELETE FROM stock_identity
WHERE source_batch_id = 'stock_identity_refresh_20260527_v1'
  AND source_version = 'stock_identity_20260527_v1'
  AND stock_identity_key IN ('stock:SH:688635', 'stock:BJ:920161')
  AND ts_code IN ('688635.SH', '920161.BJ');

DELETE FROM common_quality_gate_result
WHERE source_batch_id = 'stock_identity_refresh_20260527_v1'
   OR source_version = 'stock_identity_20260527_v1';

DELETE FROM common_ingest_batch
WHERE batch_id = 'stock_identity_refresh_20260527_v1'
   OR source_version = 'stock_identity_20260527_v1';

COMMIT;
