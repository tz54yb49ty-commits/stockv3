-- N1 stock_identity 20260529 refresh rollback draft.
-- Scope: stock_identity_refresh_20260529_v1 / stock_identity_20260529_v1.
-- This rollback only removes stock:BJ:920218 and this batch/quality/active
-- metadata. It does not touch daily facts, condition source, N2/N3/N4/N5/N6,
-- outbox/inbox/checkpoint, Parquet, worker, old system, or trading state.

BEGIN;

DO $$
DECLARE
  missing_previous_batch_count integer;
BEGIN
  SELECT COUNT(*)
  INTO missing_previous_batch_count
  FROM common_active_source_version a
  WHERE a.data_domain = 'stock'
    AND a.data_type = 'stock_identity'
    AND a.scope_key = 'A_STOCK:20260529'
    AND a.source_batch_id = 'stock_identity_refresh_20260529_v1'
    AND a.source_version = 'stock_identity_20260529_v1'
    AND a.previous_source_version IS NOT NULL
    AND NOT EXISTS (
      SELECT 1
      FROM common_ingest_batch b
      WHERE b.data_domain = a.data_domain
        AND b.data_type = a.data_type
        AND b.source_version = a.previous_source_version
        AND b.status = 'passed'
    );

  IF missing_previous_batch_count > 0 THEN
    RAISE EXCEPTION 'Refusing stock_identity 20260529 rollback: previous_source_version cannot be resolved';
  END IF;
END $$;

UPDATE common_active_source_version a
SET source_version = a.previous_source_version,
    source_batch_id = (
      SELECT b.batch_id
      FROM common_ingest_batch b
      WHERE b.data_domain = a.data_domain
        AND b.data_type = a.data_type
        AND b.source_version = a.previous_source_version
        AND b.status = 'passed'
      ORDER BY b.finished_at DESC NULLS LAST, b.started_at DESC, b.batch_id DESC
      LIMIT 1
    ),
    previous_source_version = NULL,
    activated_at = now(),
    activated_by = 'rollback:n1_stock_identity_refresh_20260529_v1'
WHERE a.data_domain = 'stock'
  AND a.data_type = 'stock_identity'
  AND a.scope_key = 'A_STOCK:20260529'
  AND a.source_batch_id = 'stock_identity_refresh_20260529_v1'
  AND a.source_version = 'stock_identity_20260529_v1'
  AND a.previous_source_version IS NOT NULL;

DELETE FROM common_active_source_version
WHERE data_domain = 'stock'
  AND data_type = 'stock_identity'
  AND scope_key = 'A_STOCK:20260529'
  AND source_batch_id = 'stock_identity_refresh_20260529_v1'
  AND source_version = 'stock_identity_20260529_v1'
  AND previous_source_version IS NULL;

DELETE FROM stock_identity
WHERE stock_identity_key = 'stock:BJ:920218'
  AND ts_code = '920218.BJ'
  AND source_batch_id = 'stock_identity_refresh_20260529_v1'
  AND source_version = 'stock_identity_20260529_v1';

DELETE FROM common_quality_gate_result
WHERE source_batch_id = 'stock_identity_refresh_20260529_v1'
   OR source_version = 'stock_identity_20260529_v1';

DELETE FROM common_ingest_batch
WHERE batch_id = 'stock_identity_refresh_20260529_v1'
   OR source_version = 'stock_identity_20260529_v1';

COMMIT;
